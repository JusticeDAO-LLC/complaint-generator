import json
import shlex
from urllib import request
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
			elif key.replace('-', '_') in {
				'required_support_kinds',
				'output_formats',
				'plaintiff_names',
				'defendant_names',
				'requested_relief',
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
		return '' if len(lines) == 1 else '\n'.join(lines)

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
		payload = self.mediator.build_formal_complaint_document_package(
			user_id=options.get('user_id'),
			court_name=options.get('court_name', 'United States District Court'),
			district=options.get('district', ''),
			division=options.get('division'),
			court_header_override=options.get('court_header_override'),
			case_number=options.get('case_number'),
			title_override=options.get('title_override'),
			plaintiff_names=options.get('plaintiff_names'),
			defendant_names=options.get('defendant_names'),
			requested_relief=options.get('requested_relief'),
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