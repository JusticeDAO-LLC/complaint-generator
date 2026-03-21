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
			response = self.mediator.io(text)
			self.print_response(response)
			payload_getter = getattr(self.mediator, 'get_current_inquiry_payload', None)
			if callable(payload_getter):
				payload = payload_getter() or {}
				explanation = payload.get('explanation') or {}
				summary = str(explanation.get('summary') or '').strip()
				if summary:
					print('\033[90m%s\033[0m' % f"Why this question: {summary}")
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

	def _humanize_cli_label(self, value):
		text = str(value or '').strip()
		if not text:
			return ''
		return text.replace('_', ' ').replace('-', ' ').title()

	def _format_cli_count_labels(self, counts):
		if not isinstance(counts, dict):
			return ''
		return ', '.join(
			f"{self._humanize_cli_label(label)}={count}" for label, count in sorted(counts.items())
		)

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
		self.print_response(self._format_claim_review_output(payload, include_json=options.get('include_json', False)))

	def _format_claim_review_output(self, payload, include_json=True):
		sections = []
		intake_status = payload.get('intake_status', {}) if isinstance(payload, dict) else {}
		if isinstance(intake_status, dict) and intake_status:
			sections.append(self._format_intake_status_summary(intake_status))
		claim_coverage_summary = payload.get('claim_coverage_summary', {}) if isinstance(payload, dict) else {}
		if isinstance(claim_coverage_summary, dict) and claim_coverage_summary:
			sections.append(self._format_claim_review_quality_summary(claim_coverage_summary))
		follow_up_plan = payload.get('follow_up_plan', {}) if isinstance(payload, dict) else {}
		if isinstance(follow_up_plan, dict) and follow_up_plan:
			sections.append(
				self._format_follow_up_fact_targeting(
					'follow-up plan fact targeting:',
					follow_up_plan,
					entries_key='tasks',
				)
			)
		follow_up_plan_summary = payload.get('follow_up_plan_summary', {}) if isinstance(payload, dict) else {}
		if isinstance(follow_up_plan_summary, dict) and follow_up_plan_summary:
			sections.append(
				self._format_authority_search_program_summary(
					'follow-up plan authority search summary:',
					follow_up_plan_summary,
				)
			)
			sections.append(
				self._format_temporal_follow_up_summary(
					'follow-up plan chronology summary:',
					follow_up_plan_summary,
				)
			)
			sections.append(
				self._format_follow_up_fact_targeting_summary(
					'follow-up plan fact-target summary:',
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
			sections.append(
				self._format_temporal_follow_up_summary(
					'follow-up history chronology summary:',
					follow_up_history_summary,
				)
			)
			sections.append(
				self._format_follow_up_fact_targeting_summary(
					'follow-up history fact-target summary:',
					follow_up_history_summary,
				)
			)
		follow_up_history = payload.get('follow_up_history', {}) if isinstance(payload, dict) else {}
		if isinstance(follow_up_history, dict) and follow_up_history:
			sections.append(
				self._format_follow_up_fact_targeting(
					'follow-up history fact targeting:',
					follow_up_history,
				)
			)
		if include_json:
			sections.append(json.dumps(payload, indent=2, default=str))
		return '\n\n'.join(section for section in sections if section)

	def _format_intake_status_summary(self, intake_status):
		lines = ['intake status summary:']
		current_phase = str(intake_status.get('current_phase') or 'unknown')
		ready_to_advance = bool(intake_status.get('ready_to_advance', False))
		score = float(intake_status.get('score') or 0.0)
		remaining_gap_count = int(intake_status.get('remaining_gap_count', 0) or 0)
		contradiction_count = int(intake_status.get('contradiction_count', 0) or 0)
		lines.append(
			f'- phase={current_phase} ready={str(ready_to_advance).lower()} score={score:.2f} '
			f'gaps={remaining_gap_count} contradictions={contradiction_count}'
		)
		next_action = intake_status.get('next_action') if isinstance(intake_status.get('next_action'), dict) else {}
		if next_action:
			action = str(next_action.get('action') or '')
			validation_target_count = int(next_action.get('validation_target_count', 0) or 0)
			if action:
				line = f'  next_action: {action}'
				if validation_target_count:
					line += f' targets={validation_target_count}'
				lines.append(line)
		primary_validation_target = (
			intake_status.get('primary_validation_target')
			if isinstance(intake_status.get('primary_validation_target'), dict)
			else {}
		)
		if primary_validation_target:
			target_claim_type = str(primary_validation_target.get('claim_type') or '')
			target_element_id = str(primary_validation_target.get('claim_element_id') or '')
			promotion_kind = str(primary_validation_target.get('promotion_kind') or '')
			promotion_ref = str(primary_validation_target.get('promotion_ref') or '')
			target_parts = [part for part in (target_claim_type, target_element_id) if part]
			target_label = ' / '.join(self._humanize_cli_label(part) for part in target_parts) if target_parts else 'unspecified'
			target_line = f'  primary_validation_target: {target_label}'
			if promotion_kind:
				target_line += f' [{self._humanize_cli_label(promotion_kind)}]'
			if promotion_ref:
				target_line += f' ref={promotion_ref}'
			lines.append(target_line)
		document_workflow_execution_summary = (
			intake_status.get('document_workflow_execution_summary')
			if isinstance(intake_status.get('document_workflow_execution_summary'), dict)
			else {}
		)
		if document_workflow_execution_summary:
			first_focus_section = str(document_workflow_execution_summary.get('first_focus_section') or '')
			first_targeted_claim_element = str(document_workflow_execution_summary.get('first_targeted_claim_element') or '')
			first_preferred_support_kind = str(document_workflow_execution_summary.get('first_preferred_support_kind') or '')
			execution_target_parts = [part for part in (first_focus_section, first_targeted_claim_element) if part]
			execution_label = ' / '.join(self._humanize_cli_label(part) for part in execution_target_parts) if execution_target_parts else 'unspecified'
			execution_line = (
				f"  document_execution: iterations={int(document_workflow_execution_summary.get('iteration_count', 0) or 0)} "
				f"accepted={int(document_workflow_execution_summary.get('accepted_iteration_count', 0) or 0)} "
				f"first={execution_label}"
			)
			if first_preferred_support_kind:
				execution_line += f' [{self._humanize_cli_label(first_preferred_support_kind)}]'
			lines.append(execution_line)
		document_execution_drift_summary = (
			intake_status.get('document_execution_drift_summary')
			if isinstance(intake_status.get('document_execution_drift_summary'), dict)
			else {}
		)
		if bool(document_execution_drift_summary.get('drift_flag')):
			top_targeted_claim_element = str(document_execution_drift_summary.get('top_targeted_claim_element') or '')
			first_executed_claim_element = str(document_execution_drift_summary.get('first_executed_claim_element') or '')
			top_label = self._humanize_cli_label(top_targeted_claim_element) if top_targeted_claim_element else 'Unspecified'
			drift_line = f'  drafting_priority: realign to {top_label} before further revisions'
			if first_executed_claim_element:
				drift_line += f" (executed {self._humanize_cli_label(first_executed_claim_element)} first)"
			lines.append(drift_line)
		document_grounding_improvement_summary = (
			intake_status.get('document_grounding_improvement_summary')
			if isinstance(intake_status.get('document_grounding_improvement_summary'), dict)
			else {}
		)
		document_grounding_improvement_next_action = (
			intake_status.get('document_grounding_improvement_next_action')
			if isinstance(intake_status.get('document_grounding_improvement_next_action'), dict)
			else {}
		)
		if document_grounding_improvement_summary:
			delta = float(document_grounding_improvement_summary.get('fact_backed_ratio_delta') or 0.0)
			status = (
				'improved'
				if bool(document_grounding_improvement_summary.get('improved_flag'))
				else 'regressed'
				if bool(document_grounding_improvement_summary.get('regressed_flag'))
				else 'stalled'
			)
			initial_ratio = float(document_grounding_improvement_summary.get('initial_fact_backed_ratio') or 0.0)
			final_ratio = float(document_grounding_improvement_summary.get('final_fact_backed_ratio') or 0.0)
			grounding_line = (
				f"  grounding_recovery: {status} "
				f"delta={delta:+.2f} "
				f"from={initial_ratio:.2f} to={final_ratio:.2f}"
			)
			targeted_claim_elements = document_grounding_improvement_summary.get('targeted_claim_elements')
			if isinstance(targeted_claim_elements, list) and targeted_claim_elements:
				grounding_line += (
					f" target={self._humanize_cli_label(str(targeted_claim_elements[0] or ''))}"
				)
			suggested_claim_element_id = str(
				document_grounding_improvement_next_action.get('suggested_claim_element_id') or ''
			).strip()
			if suggested_claim_element_id:
				grounding_line += f" next_target={self._humanize_cli_label(suggested_claim_element_id)}"
			lines.append(grounding_line)
		document_grounding_lane_outcome_summary = (
			intake_status.get('document_grounding_lane_outcome_summary')
			if isinstance(intake_status.get('document_grounding_lane_outcome_summary'), dict)
			else {}
		)
		if document_grounding_lane_outcome_summary:
			attempted_support_kind = self._humanize_cli_label(
				document_grounding_lane_outcome_summary.get('attempted_support_kind')
			) or 'Unspecified'
			outcome_status = self._humanize_cli_label(
				document_grounding_lane_outcome_summary.get('outcome_status')
			) or 'Unknown'
			learned_support_kind = self._humanize_cli_label(
				document_grounding_lane_outcome_summary.get('learned_support_kind')
			)
			learned_lane_attempted = bool(
				document_grounding_lane_outcome_summary.get('learned_support_lane_attempted_flag')
			)
			learned_lane_effective = bool(
				document_grounding_lane_outcome_summary.get('learned_support_lane_effective_flag')
			)
			recommended_support_kind = self._humanize_cli_label(
				document_grounding_lane_outcome_summary.get('recommended_future_support_kind')
			)
			lane_line = f'  grounding_lane: attempted={attempted_support_kind} outcome={outcome_status}'
			if learned_support_kind:
				lane_line += f' learned={learned_support_kind}'
			if learned_lane_attempted:
				lane_line += ' learned_used=yes'
			if learned_lane_effective:
				lane_line += ' learned_effective=yes'
			if recommended_support_kind:
				lane_line += f' recommend={recommended_support_kind}'
			lines.append(lane_line)
		return '\n'.join(lines)

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
				treatment_labels = self._format_cli_count_labels(authority_summary.get('treatment_type_counts', {}))
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
				program_labels = self._format_cli_count_labels(program_type_counts)
				lines.append(f'  program_types: {program_labels}')
			if intent_counts:
				intent_labels = self._format_cli_count_labels(intent_counts)
				lines.append(f'  search_intents: {intent_labels}')
			if primary_program_counts:
				primary_labels = self._format_cli_count_labels(primary_program_counts)
				lines.append(f'  primary_programs: {primary_labels}')
			if primary_program_bias_counts:
				bias_labels = self._format_cli_count_labels(primary_program_bias_counts)
				lines.append(f'  primary_biases: {bias_labels}')
			if primary_program_rule_bias_counts:
				rule_bias_labels = self._format_cli_count_labels(primary_program_rule_bias_counts)
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
				program_labels = self._format_cli_count_labels(selected_program_type_counts)
				lines.append(f'  selected_programs: {program_labels}')
			if selected_program_bias_counts:
				bias_labels = self._format_cli_count_labels(selected_program_bias_counts)
				lines.append(f'  selected_biases: {bias_labels}')
			if selected_program_rule_bias_counts:
				rule_bias_labels = self._format_cli_count_labels(selected_program_rule_bias_counts)
				lines.append(f'  selected_rule_biases: {rule_bias_labels}')
			source_context_summary = self._format_follow_up_source_context_summary(summary)
			if source_context_summary:
				lines.append(f'  source_context: {source_context_summary}')
		return '' if len(lines) == 1 else '\n'.join(lines)

	def _format_temporal_follow_up_summary(self, title, follow_up_summary):
		lines = [title]
		for claim_type in sorted(follow_up_summary.keys()):
			summary = follow_up_summary.get(claim_type, {})
			if not isinstance(summary, dict):
				continue
			temporal_gap_task_count = int(summary.get('temporal_gap_task_count', 0) or 0)
			temporal_gap_targeted_task_count = int(summary.get('temporal_gap_targeted_task_count', 0) or 0)
			temporal_rule_status_counts = summary.get('temporal_rule_status_counts', {}) if isinstance(summary.get('temporal_rule_status_counts'), dict) else {}
			temporal_rule_blocking_reason_counts = summary.get('temporal_rule_blocking_reason_counts', {}) if isinstance(summary.get('temporal_rule_blocking_reason_counts'), dict) else {}
			temporal_resolution_status_counts = summary.get('temporal_resolution_status_counts', {}) if isinstance(summary.get('temporal_resolution_status_counts'), dict) else {}
			if not (
				temporal_gap_task_count > 0
				or temporal_gap_targeted_task_count > 0
				or temporal_rule_status_counts
				or temporal_rule_blocking_reason_counts
				or temporal_resolution_status_counts
			):
				continue
			lines.append(
				f'- {claim_type}: chronology_tasks={temporal_gap_task_count} chronology_targeted={temporal_gap_targeted_task_count}'
			)
			if temporal_rule_status_counts:
				status_labels = self._format_cli_count_labels(temporal_rule_status_counts)
				lines.append(f'  rule_status: {status_labels}')
			if temporal_rule_blocking_reason_counts:
				blocker_labels = ', '.join(
					f"{reason}={count}" for reason, count in sorted(temporal_rule_blocking_reason_counts.items())
				)
				lines.append(f'  blockers: {blocker_labels}')
			if temporal_resolution_status_counts:
				handoff_labels = self._format_cli_count_labels(temporal_resolution_status_counts)
				lines.append(f'  handoffs: {handoff_labels}')
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
				'lane ' + self._format_cli_count_labels(support_by_kind)
			)
		if source_family_counts:
			segments.append(
				'family ' + self._format_cli_count_labels(source_family_counts)
			)
		if artifact_family_counts:
			segments.append(
				'artifact ' + self._format_cli_count_labels(artifact_family_counts)
			)
		elif content_origin_counts:
			segments.append(
				'origin ' + self._format_cli_count_labels(content_origin_counts)
			)
		return '; '.join(segments)

	def _format_follow_up_fact_targeting_summary(self, title, follow_up_summary):
		lines = [title]
		for claim_type in sorted(follow_up_summary.keys()):
			summary = follow_up_summary.get(claim_type, {})
			if not isinstance(summary, dict):
				continue
			primary_missing_fact_counts = summary.get('primary_missing_fact_counts', {}) if isinstance(summary.get('primary_missing_fact_counts'), dict) else {}
			missing_fact_bundle_counts = summary.get('missing_fact_bundle_counts', {}) if isinstance(summary.get('missing_fact_bundle_counts'), dict) else {}
			satisfied_fact_bundle_counts = summary.get('satisfied_fact_bundle_counts', {}) if isinstance(summary.get('satisfied_fact_bundle_counts'), dict) else {}
			if not (primary_missing_fact_counts or missing_fact_bundle_counts or satisfied_fact_bundle_counts):
				continue
			lines.append(f'- {claim_type}:')
			if primary_missing_fact_counts:
				primary_labels = self._format_cli_count_labels(primary_missing_fact_counts)
				lines.append(f'  primary_gaps: {primary_labels}')
			if missing_fact_bundle_counts:
				missing_labels = self._format_cli_count_labels(missing_fact_bundle_counts)
				lines.append(f'  missing_bundle: {missing_labels}')
			if satisfied_fact_bundle_counts:
				satisfied_labels = self._format_cli_count_labels(satisfied_fact_bundle_counts)
				lines.append(f'  covered_bundle: {satisfied_labels}')
		return '' if len(lines) == 1 else '\n'.join(lines)

	def _format_follow_up_fact_targeting(self, title, follow_up_claims, entries_key=None):
		lines = [title]
		for claim_type in sorted(follow_up_claims.keys()):
			claim_payload = follow_up_claims.get(claim_type, {})
			if entries_key is None:
				entries = claim_payload if isinstance(claim_payload, list) else []
			else:
				entries = claim_payload.get(entries_key, []) if isinstance(claim_payload, dict) else []
			if not isinstance(entries, list):
				continue
			formatted_entries = []
			for entry in entries:
				if not isinstance(entry, dict):
					continue
				primary_gap = str(entry.get('primary_missing_fact') or '').strip()
				missing_bundle = [
					str(item).strip() for item in (entry.get('missing_fact_bundle') or [])
					if str(item).strip()
				]
				satisfied_bundle = [
					str(item).strip() for item in (entry.get('satisfied_fact_bundle') or [])
					if str(item).strip()
				]
				if not (primary_gap or missing_bundle or satisfied_bundle):
					continue
				entry_label = str(
					entry.get('claim_element')
					or entry.get('claim_element_text')
					or entry.get('claim_element_id')
					or 'unknown element'
				)
				segments = [self._humanize_cli_label(entry_label)]
				if primary_gap:
					segments.append(f'primary_gap={primary_gap}')
				if missing_bundle:
					segments.append('missing=' + ', '.join(missing_bundle[:2]))
				if len(missing_bundle) > 2:
					segments.append(f'missing_more={len(missing_bundle) - 2}')
				if satisfied_bundle:
					segments.append('covered=' + ', '.join(satisfied_bundle[:2]))
				if len(satisfied_bundle) > 2:
					segments.append(f'covered_more={len(satisfied_bundle) - 2}')
				formatted_entries.append(' | '.join(segments))
			if formatted_entries:
				lines.append(f'- {claim_type}:')
				for formatted_entry in formatted_entries:
					lines.append(f'  {formatted_entry}')
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
		self.print_response(self._format_execute_follow_up_output(payload, include_json=options.get('include_json', False)))

	def _format_execute_follow_up_output(self, payload, include_json=True):
		sections = []
		intake_status = payload.get('intake_status', {}) if isinstance(payload, dict) else {}
		if isinstance(intake_status, dict) and intake_status:
			sections.append(self._format_intake_status_summary(intake_status))
		execution_quality_summary = payload.get('execution_quality_summary', {}) if isinstance(payload, dict) else {}
		if isinstance(execution_quality_summary, dict) and execution_quality_summary:
			sections.append(self._format_execution_quality_summary(execution_quality_summary))
		follow_up_execution = payload.get('follow_up_execution', {}) if isinstance(payload, dict) else {}
		if isinstance(follow_up_execution, dict) and follow_up_execution:
			sections.append(
				self._format_follow_up_fact_targeting(
					'follow-up execution fact targeting:',
					follow_up_execution,
					entries_key='tasks',
				)
			)
		follow_up_execution_summary = payload.get('follow_up_execution_summary', {}) if isinstance(payload, dict) else {}
		if isinstance(follow_up_execution_summary, dict) and follow_up_execution_summary:
			sections.append(
				self._format_authority_search_program_summary(
					'follow-up execution authority search summary:',
					follow_up_execution_summary,
				)
			)
			sections.append(
				self._format_temporal_follow_up_summary(
					'follow-up execution chronology summary:',
					follow_up_execution_summary,
				)
			)
			sections.append(
				self._format_follow_up_fact_targeting_summary(
					'follow-up execution fact-target summary:',
					follow_up_execution_summary,
				)
			)
		post_execution_review = payload.get('post_execution_review', {}) if isinstance(payload, dict) else {}
		post_execution_history = post_execution_review.get('follow_up_history', {}) if isinstance(post_execution_review, dict) else {}
		if isinstance(post_execution_history, dict) and post_execution_history:
			sections.append(
				self._format_follow_up_fact_targeting(
					'follow-up history fact targeting:',
					post_execution_history,
				)
			)
		post_execution_history_summary = post_execution_review.get('follow_up_history_summary', {}) if isinstance(post_execution_review, dict) else {}
		if isinstance(post_execution_history_summary, dict) and post_execution_history_summary:
			sections.append(
				self._format_authority_search_history_summary(
					'follow-up history authority search summary:',
					post_execution_history_summary,
				)
			)
			sections.append(
				self._format_temporal_follow_up_summary(
					'follow-up history chronology summary:',
					post_execution_history_summary,
				)
			)
			sections.append(
				self._format_follow_up_fact_targeting_summary(
					'follow-up history fact-target summary:',
					post_execution_history_summary,
				)
			)
		if include_json:
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
			primary_validation_target = summary.get('primary_validation_target') if isinstance(summary.get('primary_validation_target'), dict) else {}
			lines.append(f'- {claim_type}: status={status} low_quality={pre_count}->{post_count} parse_tasks={parse_task_count}')
			if resolved_elements:
				lines.append(f"  resolved: {', '.join(str(element) for element in resolved_elements)}")
			if remaining_elements:
				lines.append(f"  remaining: {', '.join(str(element) for element in remaining_elements)}")
			if recommended_next_action:
				lines.append(f'  recommendation: {recommended_next_action} still needed')
			if primary_validation_target:
				target_claim_type = str(primary_validation_target.get('claim_type') or claim_type)
				target_element_id = str(primary_validation_target.get('claim_element_id') or '')
				promotion_kind = str(primary_validation_target.get('promotion_kind') or '')
				promotion_ref = str(primary_validation_target.get('promotion_ref') or '')
				target_parts = []
				if target_claim_type:
					target_parts.append(target_claim_type)
				if target_element_id:
					target_parts.append(target_element_id)
				target_label = ' / '.join(self._humanize_cli_label(part) for part in target_parts) if target_parts else self._humanize_cli_label(claim_type)
				target_line = f'  validation target: {target_label}'
				if promotion_kind:
					target_line += f' [{self._humanize_cli_label(promotion_kind)}]'
				if promotion_ref:
					target_line += f' ref={promotion_ref}'
				lines.append(target_line)
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
			phase_mode=options.get('phase_mode', 'single'),
			backends=getattr(self.mediator, 'backends', None),
		)
		self.print_response(self._format_adversarial_autopatch_output(payload))

	def _format_adversarial_autopatch_output(self, payload):
		report = payload.get('report', {}) if isinstance(payload, dict) else {}
		autopatch = payload.get('autopatch', {}) if isinstance(payload, dict) else {}
		runtime = payload.get('runtime', {}) if isinstance(payload, dict) else {}
		lines = ['adversarial autopatch:']
		lines.append(f"sessions: {payload.get('num_results', 0)}")
		if isinstance(report, dict) and report:
			lines.append(f"average_score: {float(report.get('average_score', 0.0) or 0.0):.4f}")
			lines.append(f"score_trend: {report.get('score_trend', 'unknown')}")
		if isinstance(runtime, dict) and runtime:
			lines.append(f"runtime_mode: {runtime.get('mode', 'unknown')}")
			preflight_warnings = runtime.get('preflight_warnings', []) if isinstance(runtime.get('preflight_warnings'), list) else []
			if preflight_warnings:
				lines.append('preflight_warnings:')
				for warning in preflight_warnings:
					lines.append(f"- {warning}")
		if isinstance(autopatch, dict) and autopatch:
			lines.append(f"success: {bool(autopatch.get('success', False))}")
			lines.append(f"patch_path: {autopatch.get('patch_path', '')}")
			lines.append(f"patch_cid: {autopatch.get('patch_cid', '')}")
		phase_mode = str(payload.get('phase_mode', 'single') or 'single')
		lines.append(f"phase_mode: {phase_mode}")
		phase_tasks = payload.get('phase_tasks', []) if isinstance(payload.get('phase_tasks'), list) else []
		if phase_tasks:
			lines.append(f"phase_tasks: {len(phase_tasks)}")
			for item in phase_tasks:
				if not isinstance(item, dict):
					continue
				lines.append(
					f"- {item.get('phase', '')}: success={bool(item.get('success', False))} patch_path={item.get('patch_path', '')}"
				)
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
		print('!claim-review [claim_type] [key=value]        summary-first output; use include_json=true for raw payload')
		print('!execute-follow-up [claim_type] [key=value]   summary-first output; use include_json=true for raw payload')
		print('!export-complaint [output_dir] [key=value]')
		print('!adversarial-autopatch [output_dir] [key=value]')
