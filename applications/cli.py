import json
import shlex
from pathlib import Path
from urllib import request
from adversarial_harness.demo_autopatch import run_adversarial_autopatch_batch
from lib.log import make_logger
from mediator.exceptions import UserPresentableException
from datetime import datetime
from glob import glob

log = make_logger('cli')


class CLI:
	def __init__(self, mediator):
		self.mediator = mediator

		log.info('created CLI app')

		print('')
		print('*** JusticeDAO / Complaint Generator v1.0 ***')
		print('')
		print('commands are:')
		self.print_commands()
		print('')

		self.feed()
		self.loop()


	def loop(self):
		while True:
			
			if self.mediator.state.hashed_username is not None and self.mediator.state.hashed_password is not None:
				profile = self.mediator.state.load_profile(self, {"hashed_username": self.mediator.state.hashed_username, "hashed_password": self.mediator.state.hashed_password})
			else:
				if self.mediator.state.username is None:	
					self.mediator.state.username = input('Username:\n> ')
			
				if self.mediator.state.password is None:
					self.mediator.state.password = input('Password:\n> ')
				profile = self.mediator.state.load_profile(self, {"username": self.mediator.state.username, "password": self.mediator.state.password})

			last_question = self.mediator.state.last_question

			text = input(last_question + '> ')
			self.mediator.state.answered_questions["last_question"] = text

			if text == '':
				self.feed()
			elif text[0] != '!':
				self.feed(text)
			else:
				self.interpret_command(text[len(last_question + '> '):])

			self.mediator.state.last_question.pop(0)
			self.mediator.state.store_profile(self, profile)

	def feed(self, text=None):
		try:
			self.print_response(self.mediator.io(text))
		except UserPresentableException as exception:
			self.print_error(exception.description)
		except Exception as exception:
			self.print_error('error occured: %s' % exception)
			print('\ninternal state may be corrupted. proceed with caution.')



	def interpret_command(self, line):
		parts = shlex.split(line)
		if not parts:
			self.print_error('command unknown, available commands are:')
			self.print_commands()
			return
		command = parts[0]

		if command == 'reset':
			self.mediator.reset()
			self.feed()
		elif command == 'save':
			self.save()
		elif command == 'resume':
			self.resume()
		elif command == 'claim-review':
			self.claim_review(parts[1:])
		elif command == 'execute-follow-up':
			self.execute_follow_up(parts[1:])
		elif command == 'export-complaint':
			self.export_complaint(parts[1:])
		elif command == 'adversarial-autopatch':
			self.adversarial_autopatch(parts[1:])
		else:
			self.print_error('command unknown, available commands are:')
			self.print_commands()

	def _parse_command_options(self, args):
		options = {}
		positionals = []
		for arg in args:
			if '=' not in arg:
				positionals.append(arg)
				continue
			key, value = arg.split('=', 1)
			value = value.strip()
			lowered = value.lower()
			if lowered in ('true', 'false'):
				parsed_value = lowered == 'true'
			elif key.replace('-', '_') in {'affidavit_venue_lines', 'affidavit_notary_block', 'affidavit_facts'}:
				if value.startswith('['):
					try:
						loaded = json.loads(value)
					except ValueError as error:
						raise UserPresentableException(f'{key} must be valid JSON or a comma-delimited list') from error
					parsed_value = [str(item).strip() for item in loaded if str(item).strip()] if isinstance(loaded, list) else []
				else:
					parsed_value = [item.strip() for item in value.split(',') if item.strip()]
			elif key.replace('-', '_') in {
				'required_support_kinds',
				'output_formats',
				'plaintiff_names',
				'defendant_names',
				'requested_relief',
				'service_recipients',
			}:
				parsed_value = [item.strip() for item in value.split(',') if item.strip()]
			else:
				try:
					parsed_value = int(value)
				except ValueError:
					parsed_value = value
			options[key.replace('-', '_')] = parsed_value
		return positionals, options

	def claim_review(self, args):
		positionals, options = self._parse_command_options(args)
		claim_type = options.get('claim_type')
		if claim_type is None and positionals:
			claim_type = ' '.join(positionals)
		payload = self.mediator.build_claim_support_review_payload(
			claim_type=claim_type,
			user_id=options.get('user_id'),
			required_support_kinds=options.get('required_support_kinds'),
			follow_up_cooldown_seconds=options.get('follow_up_cooldown_seconds', 3600),
			include_support_summary=options.get('include_support_summary', True),
			include_overview=options.get('include_overview', True),
			include_follow_up_plan=options.get('include_follow_up_plan', True),
			execute_follow_up=options.get('execute_follow_up', False),
			follow_up_support_kind=options.get('follow_up_support_kind'),
			follow_up_max_tasks_per_claim=options.get('follow_up_max_tasks_per_claim', 3),
		)
		self.print_response(self._format_claim_review_output(payload))

	def _format_claim_review_output(self, payload):
		sections = []
		claim_coverage_summary = payload.get('claim_coverage_summary', {}) if isinstance(payload, dict) else {}
		if isinstance(claim_coverage_summary, dict) and claim_coverage_summary:
			sections.append(self._format_claim_review_quality_summary(claim_coverage_summary))
		follow_up_plan_summary = payload.get('follow_up_plan_summary', {}) if isinstance(payload, dict) else {}
		if isinstance(follow_up_plan_summary, dict) and follow_up_plan_summary:
			sections.append(
				self._format_authority_search_program_summary(
					'follow-up plan authority search summary:',
					follow_up_plan_summary,
				)
			)
		follow_up_history_summary = payload.get('follow_up_history_summary', {}) if isinstance(payload, dict) else {}
		if isinstance(follow_up_history_summary, dict) and follow_up_history_summary:
			sections.append(
				self._format_authority_search_history_summary(
					'follow-up history authority search summary:',
					follow_up_history_summary,
				)
			)
		sections.append(json.dumps(payload, indent=2, default=str))
		return '\n\n'.join(section for section in sections if section)

	def _format_claim_review_quality_summary(self, claim_coverage_summary):
		lines = ['claim review quality summary:']
		for claim_type in sorted(claim_coverage_summary.keys()):
			summary = claim_coverage_summary.get(claim_type, {})
			if not isinstance(summary, dict):
				continue
			low_quality_count = int(summary.get('low_quality_parsed_record_count', 0) or 0)
			issue_count = int(summary.get('parse_quality_issue_element_count', 0) or 0)
			avg_quality = float(summary.get('avg_parse_quality_score', 0.0) or 0.0)
			issue_elements = summary.get('parse_quality_issue_elements', []) if isinstance(summary.get('parse_quality_issue_elements'), list) else []
			recommendation = str(summary.get('parse_quality_recommendation') or '')
			authority_summary = summary.get('authority_treatment_summary', {}) if isinstance(summary.get('authority_treatment_summary'), dict) else {}
			supportive_authority_count = int(authority_summary.get('supportive_authority_link_count', 0) or 0)
			adverse_authority_count = int(authority_summary.get('adverse_authority_link_count', 0) or 0)
			uncertain_authority_count = int(authority_summary.get('uncertain_authority_link_count', 0) or 0)
			lines.append(
				f'- {claim_type}: low_quality={low_quality_count} issue_elements={issue_count} avg_quality={avg_quality:.2f} '
				f'authority_supportive={supportive_authority_count} authority_adverse={adverse_authority_count} '
				f'authority_uncertain={uncertain_authority_count}'
			)
			if issue_elements:
				lines.append(f"  refresh: {', '.join(str(element) for element in issue_elements)}")
			if authority_summary.get('treatment_type_counts'):
				treatment_labels = ', '.join(
					f"{kind}={count}" for kind, count in sorted(authority_summary.get('treatment_type_counts', {}).items())
				)
				lines.append(f'  authority_treatments: {treatment_labels}')
			if recommendation:
				lines.append(f'  recommendation: {recommendation}')
		return '\n'.join(lines)

	def _format_authority_search_program_summary(self, title, follow_up_summary):
		lines = [title]
		for claim_type in sorted(follow_up_summary.keys()):
			summary = follow_up_summary.get(claim_type, {})
			if not isinstance(summary, dict):
				continue
			program_task_count = int(summary.get('authority_search_program_task_count', 0) or 0)
			program_count = int(summary.get('authority_search_program_count', 0) or 0)
			program_type_counts = summary.get('authority_search_program_type_counts', {}) if isinstance(summary.get('authority_search_program_type_counts'), dict) else {}
			intent_counts = summary.get('authority_search_intent_counts', {}) if isinstance(summary.get('authority_search_intent_counts'), dict) else {}
			primary_program_counts = summary.get('primary_authority_program_type_counts', {}) if isinstance(summary.get('primary_authority_program_type_counts'), dict) else {}
			primary_program_bias_counts = summary.get('primary_authority_program_bias_counts', {}) if isinstance(summary.get('primary_authority_program_bias_counts'), dict) else {}
			primary_program_rule_bias_counts = summary.get('primary_authority_program_rule_bias_counts', {}) if isinstance(summary.get('primary_authority_program_rule_bias_counts'), dict) else {}
			if not (
				program_task_count > 0
				or program_count > 0
				or program_type_counts
				or intent_counts
				or primary_program_counts
				or primary_program_bias_counts
				or primary_program_rule_bias_counts
			):
				continue
			lines.append(
				f'- {claim_type}: authority_program_tasks={program_task_count} authority_programs={program_count}'
			)
			if program_type_counts:
				program_labels = ', '.join(
					f"{program_type}={count}" for program_type, count in sorted(program_type_counts.items())
				)
				lines.append(f'  program_types: {program_labels}')
			if intent_counts:
				intent_labels = ', '.join(
					f"{intent}={count}" for intent, count in sorted(intent_counts.items())
				)
				lines.append(f'  search_intents: {intent_labels}')
			if primary_program_counts:
				primary_labels = ', '.join(
					f"{program_type}={count}" for program_type, count in sorted(primary_program_counts.items())
				)
				lines.append(f'  primary_programs: {primary_labels}')
			if primary_program_bias_counts:
				bias_labels = ', '.join(
					f"{bias}={count}" for bias, count in sorted(primary_program_bias_counts.items())
				)
				lines.append(f'  primary_biases: {bias_labels}')
			if primary_program_rule_bias_counts:
				rule_bias_labels = ', '.join(
					f"{bias}={count}" for bias, count in sorted(primary_program_rule_bias_counts.items())
				)
				lines.append(f'  primary_rule_biases: {rule_bias_labels}')
			source_context_summary = self._format_follow_up_source_context_summary(summary)
			if source_context_summary:
				lines.append(f'  source_context: {source_context_summary}')
		return '' if len(lines) == 1 else '\n'.join(lines)

	def _format_authority_search_history_summary(self, title, follow_up_history_summary):
		lines = [title]
		for claim_type in sorted(follow_up_history_summary.keys()):
			summary = follow_up_history_summary.get(claim_type, {})
			if not isinstance(summary, dict):
				continue
			selected_program_type_counts = summary.get('selected_authority_program_type_counts', {}) if isinstance(summary.get('selected_authority_program_type_counts'), dict) else {}
			selected_program_bias_counts = summary.get('selected_authority_program_bias_counts', {}) if isinstance(summary.get('selected_authority_program_bias_counts'), dict) else {}
			selected_program_rule_bias_counts = summary.get('selected_authority_program_rule_bias_counts', {}) if isinstance(summary.get('selected_authority_program_rule_bias_counts'), dict) else {}
			history_program_entry_count = sum(int(count or 0) for count in selected_program_type_counts.values())
			if not (
				history_program_entry_count > 0
				or selected_program_bias_counts
				or selected_program_rule_bias_counts
			):
				continue
			lines.append(
				f'- {claim_type}: history_program_entries={history_program_entry_count}'
			)
			if selected_program_type_counts:
				program_labels = ', '.join(
					f"{program_type}={count}" for program_type, count in sorted(selected_program_type_counts.items())
				)
				lines.append(f'  selected_programs: {program_labels}')
			if selected_program_bias_counts:
				bias_labels = ', '.join(
					f"{bias}={count}" for bias, count in sorted(selected_program_bias_counts.items())
				)
				lines.append(f'  selected_biases: {bias_labels}')
			if selected_program_rule_bias_counts:
				rule_bias_labels = ', '.join(
					f"{bias}={count}" for bias, count in sorted(selected_program_rule_bias_counts.items())
				)
				lines.append(f'  selected_rule_biases: {rule_bias_labels}')
			source_context_summary = self._format_follow_up_source_context_summary(summary)
			if source_context_summary:
				lines.append(f'  source_context: {source_context_summary}')
		return '' if len(lines) == 1 else '\n'.join(lines)

	def _format_follow_up_source_context_summary(self, summary):
		if not isinstance(summary, dict):
			return ''
		segments = []
		support_by_kind = summary.get('support_by_kind', {}) if isinstance(summary.get('support_by_kind'), dict) else {}
		source_family_counts = summary.get('source_family_counts', {}) if isinstance(summary.get('source_family_counts'), dict) else {}
		artifact_family_counts = summary.get('artifact_family_counts', {}) if isinstance(summary.get('artifact_family_counts'), dict) else {}
		content_origin_counts = summary.get('content_origin_counts', {}) if isinstance(summary.get('content_origin_counts'), dict) else {}
		if support_by_kind:
			segments.append(
				'lane ' + ', '.join(f"{label}={count}" for label, count in sorted(support_by_kind.items()))
			)
		if source_family_counts:
			segments.append(
				'family ' + ', '.join(f"{label}={count}" for label, count in sorted(source_family_counts.items()))
			)
		if artifact_family_counts:
			segments.append(
				'artifact ' + ', '.join(f"{label}={count}" for label, count in sorted(artifact_family_counts.items()))
			)
		elif content_origin_counts:
			segments.append(
				'origin ' + ', '.join(f"{label}={count}" for label, count in sorted(content_origin_counts.items()))
			)
		return '; '.join(segments)

	def execute_follow_up(self, args):
		positionals, options = self._parse_command_options(args)
		claim_type = options.get('claim_type')
		if claim_type is None and positionals:
			claim_type = ' '.join(positionals)
		payload = self.mediator.build_claim_support_follow_up_execution_payload(
			claim_type=claim_type,
			user_id=options.get('user_id'),
			required_support_kinds=options.get('required_support_kinds'),
			follow_up_cooldown_seconds=options.get('follow_up_cooldown_seconds', 3600),
			follow_up_support_kind=options.get('follow_up_support_kind'),
			follow_up_max_tasks_per_claim=options.get('follow_up_max_tasks_per_claim', 3),
			follow_up_force=options.get('follow_up_force', False),
			include_post_execution_review=options.get('include_post_execution_review', True),
			include_support_summary=options.get('include_support_summary', True),
			include_overview=options.get('include_overview', True),
			include_follow_up_plan=options.get('include_follow_up_plan', True),
		)
		self.print_response(self._format_execute_follow_up_output(payload))

	def _format_execute_follow_up_output(self, payload):
		sections = []
		execution_quality_summary = payload.get('execution_quality_summary', {}) if isinstance(payload, dict) else {}
		if isinstance(execution_quality_summary, dict) and execution_quality_summary:
			sections.append(self._format_execution_quality_summary(execution_quality_summary))
		follow_up_execution_summary = payload.get('follow_up_execution_summary', {}) if isinstance(payload, dict) else {}
		if isinstance(follow_up_execution_summary, dict) and follow_up_execution_summary:
			sections.append(
				self._format_authority_search_program_summary(
					'follow-up execution authority search summary:',
					follow_up_execution_summary,
				)
			)
		post_execution_review = payload.get('post_execution_review', {}) if isinstance(payload, dict) else {}
		post_execution_history_summary = post_execution_review.get('follow_up_history_summary', {}) if isinstance(post_execution_review, dict) else {}
		if isinstance(post_execution_history_summary, dict) and post_execution_history_summary:
			sections.append(
				self._format_authority_search_history_summary(
					'follow-up history authority search summary:',
					post_execution_history_summary,
				)
			)
		sections.append(json.dumps(payload, indent=2, default=str))
		return '\n\n'.join(section for section in sections if section)

	def _format_execution_quality_summary(self, execution_quality_summary):
		lines = ['follow-up execution quality summary:']
		for claim_type in sorted(execution_quality_summary.keys()):
			summary = execution_quality_summary.get(claim_type, {})
			if not isinstance(summary, dict):
				continue
			status = str(summary.get('quality_improvement_status') or 'unknown')
			pre_count = int(summary.get('pre_low_quality_parsed_record_count', 0) or 0)
			post_count = int(summary.get('post_low_quality_parsed_record_count', 0) or 0)
			parse_task_count = int(summary.get('parse_quality_task_count', 0) or 0)
			resolved_elements = summary.get('resolved_parse_quality_issue_elements', []) if isinstance(summary.get('resolved_parse_quality_issue_elements'), list) else []
			remaining_elements = summary.get('remaining_parse_quality_issue_elements', []) if isinstance(summary.get('remaining_parse_quality_issue_elements'), list) else []
			recommended_next_action = str(summary.get('recommended_next_action') or '')
			lines.append(f'- {claim_type}: status={status} low_quality={pre_count}->{post_count} parse_tasks={parse_task_count}')
			if resolved_elements:
				lines.append(f"  resolved: {', '.join(str(element) for element in resolved_elements)}")
			if remaining_elements:
				lines.append(f"  remaining: {', '.join(str(element) for element in remaining_elements)}")
			if recommended_next_action:
				lines.append(f'  recommendation: {recommended_next_action} still needed')
		return '\n'.join(lines)

	def export_complaint(self, args):
		positionals, options = self._parse_command_options(args)
		output_dir = options.get('output_dir')
		if output_dir is None and positionals:
			output_dir = positionals[0]
		service_recipient_details = options.get('service_recipient_details')
		if isinstance(service_recipient_details, str):
			try:
				service_recipient_details = json.loads(service_recipient_details)
			except ValueError as error:
				raise UserPresentableException('service_recipient_details must be valid JSON') from error
		additional_signers = options.get('additional_signers')
		if isinstance(additional_signers, str):
			try:
				additional_signers = json.loads(additional_signers)
			except ValueError as error:
				raise UserPresentableException('additional_signers must be valid JSON') from error
		affidavit_supporting_exhibits = options.get('affidavit_supporting_exhibits')
		if isinstance(affidavit_supporting_exhibits, str):
			try:
				affidavit_supporting_exhibits = json.loads(affidavit_supporting_exhibits)
			except ValueError as error:
				raise UserPresentableException('affidavit_supporting_exhibits must be valid JSON') from error
		payload = self.mediator.build_formal_complaint_document_package(
			user_id=options.get('user_id'),
			court_name=options.get('court_name', 'United States District Court'),
			district=options.get('district', ''),
			county=options.get('county'),
			division=options.get('division'),
			court_header_override=options.get('court_header_override'),
			case_number=options.get('case_number'),
			lead_case_number=options.get('lead_case_number'),
			related_case_number=options.get('related_case_number'),
			assigned_judge=options.get('assigned_judge'),
			courtroom=options.get('courtroom'),
			title_override=options.get('title_override'),
			plaintiff_names=options.get('plaintiff_names'),
			defendant_names=options.get('defendant_names'),
			requested_relief=options.get('requested_relief'),
			jury_demand=options.get('jury_demand'),
			jury_demand_text=options.get('jury_demand_text'),
			signer_name=options.get('signer_name'),
			signer_title=options.get('signer_title'),
			signer_firm=options.get('signer_firm'),
			signer_bar_number=options.get('signer_bar_number'),
			signer_contact=options.get('signer_contact'),
			additional_signers=additional_signers,
			declarant_name=options.get('declarant_name'),
			service_method=options.get('service_method'),
			service_recipients=options.get('service_recipients'),
			service_recipient_details=service_recipient_details,
			signature_date=options.get('signature_date'),
			verification_date=options.get('verification_date'),
			service_date=options.get('service_date'),
			affidavit_title=options.get('affidavit_title'),
			affidavit_intro=options.get('affidavit_intro'),
			affidavit_facts=options.get('affidavit_facts'),
			affidavit_supporting_exhibits=affidavit_supporting_exhibits,
			affidavit_include_complaint_exhibits=options.get('affidavit_include_complaint_exhibits'),
			affidavit_venue_lines=options.get('affidavit_venue_lines'),
			affidavit_jurat=options.get('affidavit_jurat'),
			affidavit_notary_block=options.get('affidavit_notary_block'),
			output_dir=output_dir,
			output_formats=options.get('output_formats'),
		)
		self.print_response(self._format_export_complaint_output(payload))

	def _format_export_complaint_output(self, payload):
		draft = payload.get('draft', {}) if isinstance(payload, dict) else {}
		artifacts = payload.get('artifacts', {}) if isinstance(payload, dict) else {}
		lines = ['formal complaint export:']
		if draft:
			lines.append(f"title: {draft.get('title', 'Untitled complaint')}")
			lines.append(f"court: {draft.get('court_header', 'unknown court')}")
			caption = draft.get('case_caption', {}) if isinstance(draft.get('case_caption'), dict) else {}
			lines.append(f"case_number: {caption.get('case_number', '________________')}")
			lines.append(f"claims: {len(draft.get('claims_for_relief', []) or [])}")
			lines.append(f"exhibits: {len(draft.get('exhibits', []) or [])}")
		if artifacts:
			lines.append('artifacts:')
			for output_format in sorted(artifacts.keys()):
				artifact = artifacts.get(output_format, {}) if isinstance(artifacts.get(output_format), dict) else {}
				lines.append(f"- {output_format}: {artifact.get('path', '')}")
		lines.append(json.dumps(payload, indent=2, default=str))
		return '\n'.join(lines)

	def adversarial_autopatch(self, args):
		positionals, options = self._parse_command_options(args)
		output_dir = options.get('output_dir')
		if output_dir is None and positionals:
			output_dir = positionals[0]
		if output_dir is None:
			output_dir = str(Path(__file__).resolve().parent.parent / 'tmp' / 'cli_adversarial_autopatch')
		payload = run_adversarial_autopatch_batch(
			project_root=Path(__file__).resolve().parent.parent,
			output_dir=output_dir,
			target_file=options.get('target_file', 'adversarial_harness/session.py'),
			num_sessions=options.get('num_sessions', 1),
			max_turns=options.get('max_turns', 2),
			max_parallel=options.get('max_parallel', 1),
			session_state_dir=options.get('session_state_dir'),
			marker_prefix='CLI autopatch recommendation',
			demo_backend=options.get('demo_backend', True),
			backends=getattr(self.mediator, 'backends', None),
		)
		self.print_response(self._format_adversarial_autopatch_output(payload))

	def _format_adversarial_autopatch_output(self, payload):
		report = payload.get('report', {}) if isinstance(payload, dict) else {}
		autopatch = payload.get('autopatch', {}) if isinstance(payload, dict) else {}
		lines = ['adversarial autopatch:']
		lines.append(f"sessions: {payload.get('num_results', 0)}")
		if isinstance(report, dict) and report:
			lines.append(f"average_score: {float(report.get('average_score', 0.0) or 0.0):.4f}")
			lines.append(f"score_trend: {report.get('score_trend', 'unknown')}")
		if isinstance(autopatch, dict) and autopatch:
			lines.append(f"success: {bool(autopatch.get('success', False))}")
			lines.append(f"patch_path: {autopatch.get('patch_path', '')}")
			lines.append(f"patch_cid: {autopatch.get('patch_cid', '')}")
		lines.append(json.dumps(payload, indent=2, default=str))
		return '\n'.join(lines)


	def save(self):
		request = dict({"username": self.mediator.state.username, "password": self.mediator.state.password})
		profile = self.mediator.state.load_profile(self, request)
		profile["data"] = self.mediator.state.answered_questions
		profile["data"]["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		self.mediator.state.store_profile(self, profile)
		print("Profile saved")
	
	def resume(self):
		request = dict({"username": self.mediator.state.username, "password": self.mediator.state.password})
		profile = self.mediator.state.load_profile(self,request)
		print('')
		print('[resumed state]')
		print('')

		self.feed()

			


	def print_response(self, text):
		print('\033[1m%s\033[0m' % text)

	def print_error(self, text):
		print('\033[91m%s\033[0m' % text)

	def print_commands(self):
		print('!reset      wipe current state and start over')
		print('!resume     resumes from a statefile from disk')
		print('!save       saves current state to disk')
		print('!claim-review [claim_type] [key=value]')
		print('!execute-follow-up [claim_type] [key=value]')
		print('!export-complaint [output_dir] [key=value]')
		print('!adversarial-autopatch [output_dir] [key=value]')