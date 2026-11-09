"""Intake-question methods delegated from Mediator.

The functions keep the original method bodies. The class methods forward here.
"""

from __future__ import annotations

from complaint_phases import ComplaintPhase, NodeType


def _summarize_intake_evidence_alignment(
	self,
	intake_case_file: Any,
	claim_support_packets: Any,
) -> Dict[str, Any]:
	summary = {
		'claim_count': 0,
		'aligned_element_count': 0,
		'unsupported_shared_count': 0,
		'claims': {},
	}
	intake_case = intake_case_file if isinstance(intake_case_file, dict) else {}
	packets = claim_support_packets if isinstance(claim_support_packets, dict) else {}
	intake_chronology_readiness = self._build_intake_chronology_readiness(intake_case)
	candidate_claims = intake_case.get('candidate_claims', []) if isinstance(intake_case.get('candidate_claims'), list) else []
	proof_leads = intake_case.get('proof_leads', []) if isinstance(intake_case.get('proof_leads'), list) else []
	open_items = intake_case.get('open_items', []) if isinstance(intake_case.get('open_items'), list) else []
	event_ledger = intake_case.get('event_ledger', []) if isinstance(intake_case.get('event_ledger'), list) else []
	temporal_issue_registry = intake_case.get('temporal_issue_registry', []) if isinstance(intake_case.get('temporal_issue_registry'), list) else []
	if not temporal_issue_registry and isinstance(intake_case.get('timeline_issues'), list):
		temporal_issue_registry = intake_case.get('timeline_issues')
	timeline_anchor_ids_by_fact_id = self._build_timeline_anchor_ids_by_fact_id(intake_case)
	temporal_relation_formulas_by_id = self._build_temporal_relation_formulas_by_id(intake_case)
	proof_lead_map = {
		str(lead.get('lead_id') or '').strip(): lead
		for lead in proof_leads
		if isinstance(lead, dict) and str(lead.get('lead_id') or '').strip()
	}
	relation_ids_by_claim_element: Dict[tuple[str, str], List[str]] = {}
	for relation in intake_case.get('temporal_relation_registry', []) if isinstance(intake_case.get('temporal_relation_registry'), list) else []:
		if not isinstance(relation, dict):
			continue
		relation_id = str(relation.get('relation_id') or '').strip()
		if not relation_id:
			continue
		for claim_type_value in (relation.get('claim_types') or []):
			normalized_claim_type = str(claim_type_value or '').strip().lower()
			if not normalized_claim_type:
				continue
			for element_tag in (relation.get('element_tags') or []):
				normalized_element_tag = str(element_tag or '').strip().lower()
				if not normalized_element_tag:
					continue
				relation_ids_by_claim_element.setdefault((normalized_claim_type, normalized_element_tag), [])
				if relation_id not in relation_ids_by_claim_element[(normalized_claim_type, normalized_element_tag)]:
					relation_ids_by_claim_element[(normalized_claim_type, normalized_element_tag)].append(relation_id)
	event_ids_by_claim_element: Dict[tuple[str, str], List[str]] = {}
	for event in event_ledger:
		if not isinstance(event, dict):
			continue
		event_id = str(event.get('event_id') or event.get('temporal_fact_id') or event.get('fact_id') or '').strip()
		if not event_id:
			continue
		for claim_type_value in (event.get('claim_types') or []):
			normalized_claim_type = str(claim_type_value or '').strip().lower()
			if not normalized_claim_type:
				continue
			for element_tag in (event.get('element_tags') or []):
				normalized_element_tag = str(element_tag or '').strip().lower()
				if not normalized_element_tag:
					continue
				event_ids_by_claim_element.setdefault((normalized_claim_type, normalized_element_tag), [])
				if event_id not in event_ids_by_claim_element[(normalized_claim_type, normalized_element_tag)]:
					event_ids_by_claim_element[(normalized_claim_type, normalized_element_tag)].append(event_id)
	issue_ids_by_claim_element: Dict[tuple[str, str], List[str]] = {}
	issue_records_by_id: Dict[str, Dict[str, Any]] = {}
	for issue in temporal_issue_registry:
		if not isinstance(issue, dict):
			continue
		issue_id = str(issue.get('issue_id') or '').strip()
		if not issue_id:
			continue
		issue_records_by_id[issue_id] = dict(issue)
		for claim_type_value in (issue.get('claim_types') or []):
			normalized_claim_type = str(claim_type_value or '').strip().lower()
			if not normalized_claim_type:
				continue
			for element_tag in (issue.get('element_tags') or []):
				normalized_element_tag = str(element_tag or '').strip().lower()
				if not normalized_element_tag:
					continue
				issue_ids_by_claim_element.setdefault((normalized_claim_type, normalized_element_tag), [])
				if issue_id not in issue_ids_by_claim_element[(normalized_claim_type, normalized_element_tag)]:
					issue_ids_by_claim_element[(normalized_claim_type, normalized_element_tag)].append(issue_id)

	claim_types = set(packets.keys())
	for claim in candidate_claims:
		if isinstance(claim, dict) and claim.get('claim_type'):
			claim_types.add(str(claim.get('claim_type')))

	for claim_type in sorted(claim_types):
		candidate = next(
			(
				item for item in candidate_claims
				if isinstance(item, dict) and str(item.get('claim_type') or '') == str(claim_type)
			),
			{},
		)
		required_elements = candidate.get('required_elements', []) if isinstance(candidate, dict) else []
		intake_elements = []
		for element in required_elements:
			if not isinstance(element, dict):
				continue
			element_id = str(element.get('element_id') or '').strip()
			if not element_id:
				continue
			intake_elements.append(
				{
					'element_id': element_id,
					'label': str(element.get('label') or element_id).strip(),
					'blocking': bool(element.get('blocking', True)),
					'evidence_classes': list(element.get('evidence_classes', []) or []),
				}
			)
		intake_element_ids = [item['element_id'] for item in intake_elements]

		packet = packets.get(claim_type, {}) if isinstance(packets, dict) else {}
		packet_elements = packet.get('elements', []) if isinstance(packet, dict) else []
		packet_status_by_element: Dict[str, str] = {}
		packet_element_map: Dict[str, Dict[str, Any]] = {}
		for element in packet_elements if isinstance(packet_elements, list) else []:
			if not isinstance(element, dict):
				continue
			element_id = str(element.get('element_id') or '').strip()
			if not element_id:
				continue
			packet_status_by_element[element_id] = str(element.get('support_status') or '').strip().lower()
			packet_element_map[element_id] = element

		shared_elements = []
		for intake_element in intake_elements:
			element_id = intake_element['element_id']
			if element_id not in packet_status_by_element:
				continue
			support_status = packet_status_by_element[element_id]
			packet_element = packet_element_map.get(element_id, {}) if isinstance(packet_element_map.get(element_id), dict) else {}
			reasoning_diagnostics = packet_element.get('reasoning_diagnostics', {}) if isinstance(packet_element.get('reasoning_diagnostics'), dict) else {}
			temporal_proof_bundle = reasoning_diagnostics.get('temporal_proof_bundle', {}) if isinstance(reasoning_diagnostics.get('temporal_proof_bundle'), dict) else {}
			theorem_exports = temporal_proof_bundle.get('theorem_exports', {}) if isinstance(temporal_proof_bundle.get('theorem_exports'), dict) else {}
			theorem_export_metadata = theorem_exports.get('theorem_export_metadata', {}) if isinstance(theorem_exports.get('theorem_export_metadata'), dict) else {}
			temporal_fact_ids = [
				str(item).strip()
				for item in (temporal_proof_bundle.get('temporal_fact_ids') or [])
				if str(item).strip()
			]
			proof_temporal_fact_ids = list(temporal_fact_ids)
			if not temporal_fact_ids:
				temporal_fact_ids = list(event_ids_by_claim_element.get((str(claim_type).strip().lower(), element_id.lower()), []))
			temporal_relation_ids = [
				str(item).strip()
				for item in (temporal_proof_bundle.get('temporal_relation_ids') or [])
				if str(item).strip()
			]
			proof_temporal_relation_ids = list(temporal_relation_ids)
			if not temporal_relation_ids:
				temporal_relation_ids = list(
					relation_ids_by_claim_element.get((str(claim_type).strip().lower(), element_id.lower()), [])
				)
			proof_temporal_issue_ids = [
				str(item).strip()
				for item in (temporal_proof_bundle.get('temporal_issue_ids') or [])
				if str(item).strip()
			]
			authored_temporal_issue_ids = list(
				issue_ids_by_claim_element.get((str(claim_type).strip().lower(), element_id.lower()), [])
			)
			temporal_issue_ids = list(dict.fromkeys(authored_temporal_issue_ids + proof_temporal_issue_ids))
			timeline_anchor_ids: List[str] = []
			for fact_id in temporal_fact_ids:
				for anchor_id in timeline_anchor_ids_by_fact_id.get(str(fact_id).strip(), []):
					if anchor_id not in timeline_anchor_ids:
						timeline_anchor_ids.append(anchor_id)
			temporal_relation_formulas = [
				formula
				for relation_id in temporal_relation_ids
				for formula in [temporal_relation_formulas_by_id.get(str(relation_id).strip(), '')]
				if formula
			]
			temporal_theorem_formulas = [
				str(formula).strip()
				for formula in ((theorem_exports.get('tdfol_formulas') or []) + (theorem_exports.get('dcec_formulas') or []))
				if str(formula).strip()
			]
			temporal_proof_objectives = [
				str(item).strip()
				for item in (theorem_export_metadata.get('temporal_proof_objectives') or [])
				if str(item).strip()
			]
			matching_issue_records = [
				issue_records_by_id.get(issue_id)
				for issue_id in temporal_issue_ids
				if isinstance(issue_records_by_id.get(issue_id), dict)
			]
			fallback_temporal_rule_blocking_reasons = [
				str(issue.get('summary') or '').strip()
				for issue in matching_issue_records
				if str(issue.get('summary') or '').strip()
			]
			fallback_temporal_rule_follow_ups = [
				{
					'lane': str(issue.get('recommended_resolution_lane') or '').strip(),
					'reason': str(issue.get('summary') or '').strip(),
				}
				for issue in matching_issue_records
				if str(issue.get('recommended_resolution_lane') or '').strip() and str(issue.get('summary') or '').strip()
			]
			if not temporal_proof_objectives:
				temporal_proof_objectives = list(dict.fromkeys(
					[
						f"resolve_{str(issue.get('issue_type') or 'chronology').strip().lower()}"
						for issue in matching_issue_records
						if str(issue.get('issue_type') or '').strip()
					]
				))
				if not temporal_proof_objectives and temporal_issue_ids:
					temporal_proof_objectives = [f'resolve_{element_id.lower()}_chronology']
			temporal_rule_status = str(packet_element.get('temporal_rule_status') or '').strip()
			if not temporal_rule_status and temporal_issue_ids:
				temporal_rule_status = 'partial'
			temporal_rule_blocking_reasons = list(packet_element.get('temporal_rule_blocking_reasons', []) or [])
			if not temporal_rule_blocking_reasons:
				temporal_rule_blocking_reasons = fallback_temporal_rule_blocking_reasons
			temporal_rule_follow_ups = list(packet_element.get('temporal_rule_follow_ups', []) or [])
			if not temporal_rule_follow_ups:
				temporal_rule_follow_ups = fallback_temporal_rule_follow_ups
			shared_missing_temporal_predicates = [
				str(item).strip()
				for item in (theorem_export_metadata.get('missing_temporal_predicates') or [])
				if str(item).strip()
			]
			if not shared_missing_temporal_predicates:
				for issue in matching_issue_records:
					for predicate in (issue.get('missing_temporal_predicates') if isinstance(issue.get('missing_temporal_predicates'), list) else []):
						normalized_predicate = str(predicate).strip()
						if normalized_predicate and normalized_predicate not in shared_missing_temporal_predicates:
							shared_missing_temporal_predicates.append(normalized_predicate)
			shared_required_provenance_kinds = [
				str(item).strip()
				for item in (theorem_export_metadata.get('required_provenance_kinds') or [])
				if str(item).strip()
			]
			if not shared_required_provenance_kinds:
				for issue in matching_issue_records:
					for provenance_kind in (issue.get('required_provenance_kinds') if isinstance(issue.get('required_provenance_kinds'), list) else []):
						normalized_provenance_kind = str(provenance_kind).strip()
						if normalized_provenance_kind and normalized_provenance_kind not in shared_required_provenance_kinds:
							shared_required_provenance_kinds.append(normalized_provenance_kind)
			temporal_next_actions = self._build_temporal_next_actions_for_task(
				claim_type=claim_type,
				claim_element_id=element_id,
				claim_element_label=intake_element['label'],
				temporal_rule_profile_id=packet_element.get('temporal_rule_profile_id'),
				temporal_rule_status=temporal_rule_status,
				temporal_rule_follow_ups=temporal_rule_follow_ups,
				temporal_rule_blocking_reasons=temporal_rule_blocking_reasons,
				temporal_issue_records=matching_issue_records,
				temporal_fact_ids=temporal_fact_ids,
				temporal_relation_ids=temporal_relation_ids,
				temporal_issue_ids=temporal_issue_ids,
				missing_temporal_predicates=shared_missing_temporal_predicates,
				required_provenance_kinds=shared_required_provenance_kinds,
				temporal_proof_bundle=temporal_proof_bundle,
				packet_temporal_next_actions=packet_element.get('temporal_next_actions'),
			)
			has_authored_chronology = bool(
				authored_temporal_issue_ids
				or (not proof_temporal_fact_ids and temporal_fact_ids)
				or (not proof_temporal_relation_ids and temporal_relation_ids)
			)
			has_proof_chronology = bool(
				proof_temporal_issue_ids
				or proof_temporal_fact_ids
				or proof_temporal_relation_ids
				or temporal_theorem_formulas
				or str(packet_element.get('temporal_rule_profile_id') or '').strip()
				or str(packet_element.get('temporal_rule_status') or '').strip()
				or list(packet_element.get('temporal_rule_blocking_reasons', []) or [])
				or list(packet_element.get('temporal_rule_follow_ups', []) or [])
			)
			chronology_source = ''
			if has_authored_chronology and has_proof_chronology:
				chronology_source = 'authored_intake_registry+proof_diagnostics'
			elif has_authored_chronology:
				chronology_source = 'authored_intake_registry'
			elif has_proof_chronology:
				chronology_source = 'proof_diagnostics'
			matching_open_item_ids = [
				str(item.get('open_item_id') or '')
				for item in open_items
				if isinstance(item, dict)
				and str(item.get('target_claim_type') or '').strip().lower() == str(claim_type).strip().lower()
				and str(item.get('target_element_id') or '').strip().lower() == element_id.lower()
			]
			matching_proof_lead_ids = [
				str(lead.get('lead_id') or '')
				for lead in proof_leads
				if isinstance(lead, dict)
				and (
					element_id.lower() in [str(item).strip().lower() for item in (lead.get('element_targets') or []) if str(item).strip()]
				)
			]
			matching_proof_leads = []
			for lead_id in matching_proof_lead_ids:
				lead = proof_lead_map.get(lead_id)
				if not isinstance(lead, dict):
					continue
				matching_proof_leads.append(
					{
						'lead_id': lead_id,
						'lead_type': str(lead.get('lead_type') or '').strip(),
						'owner': str(lead.get('owner') or '').strip(),
						'custodian': str(lead.get('custodian') or '').strip(),
						'availability': str(lead.get('availability') or '').strip(),
						'availability_details': str(lead.get('availability_details') or '').strip(),
						'recommended_support_kind': str(lead.get('recommended_support_kind') or '').strip(),
						'source_quality_target': str(lead.get('source_quality_target') or '').strip(),
					}
				)
			shared_elements.append(
				{
					'element_id': element_id,
					'label': intake_element['label'],
					'blocking': intake_element['blocking'],
					'support_status': support_status,
					'support_quality': str(packet_element.get('support_quality') or self._derive_packet_support_quality(packet_element)).strip().lower(),
					'support_lane_label': str(packet_element.get('support_lane_label') or self._derive_support_lane_label(packet_element)).strip().lower(),
					'preferred_evidence_classes': list(packet_element.get('preferred_evidence_classes', []) or intake_element.get('evidence_classes', []) or []),
					'required_fact_bundle': list(packet_element.get('required_fact_bundle', []) or []),
					'satisfied_fact_bundle': list(packet_element.get('satisfied_fact_bundle', []) or []),
					'missing_fact_bundle': list(packet_element.get('missing_fact_bundle', []) or []),
					'missing_support_kinds': list(packet_element.get('missing_support_kinds', []) or []),
					'temporal_proof_bundle_id': str(temporal_proof_bundle.get('proof_bundle_id') or '').strip(),
					'temporal_fact_ids': temporal_fact_ids,
					'proof_temporal_fact_ids': proof_temporal_fact_ids,
					'timeline_anchor_ids': timeline_anchor_ids,
					'temporal_relation_ids': temporal_relation_ids,
					'proof_temporal_relation_ids': proof_temporal_relation_ids,
					'temporal_relation_formulas': temporal_relation_formulas,
					'temporal_issue_ids': temporal_issue_ids,
					'authored_temporal_issue_ids': authored_temporal_issue_ids,
					'proof_temporal_issue_ids': proof_temporal_issue_ids,
					'temporal_issue_records': matching_issue_records,
					'temporal_theorem_formulas': temporal_theorem_formulas,
					'temporal_proof_objectives': temporal_proof_objectives,
					'chronology_source': chronology_source,
					'intake_chronology_readiness': {
						'contract_version': str(intake_chronology_readiness.get('contract_version') or ''),
						'ready_for_temporal_formalization': bool(intake_chronology_readiness.get('ready_for_temporal_formalization', False)),
						'anchor_coverage_ratio': float(intake_chronology_readiness.get('anchor_coverage_ratio', 0.0) or 0.0),
						'predicate_coverage_ratio': float(intake_chronology_readiness.get('predicate_coverage_ratio', 0.0) or 0.0),
						'provenance_coverage_ratio': float(intake_chronology_readiness.get('provenance_coverage_ratio', 0.0) or 0.0),
						'open_issue_count': int(intake_chronology_readiness.get('open_issue_count', 0) or 0),
						'blocking_issue_count': int(intake_chronology_readiness.get('blocking_issue_count', 0) or 0),
					},
					'temporal_rule_profile_id': str(packet_element.get('temporal_rule_profile_id') or ''),
					'temporal_rule_status': temporal_rule_status,
					'temporal_rule_blocking_reasons': temporal_rule_blocking_reasons,
					'temporal_rule_follow_ups': temporal_rule_follow_ups,
					'temporal_next_actions': temporal_next_actions,
					'temporal_next_action_count': len(temporal_next_actions),
					'temporal_missingness_kind': 'temporal_gap' if temporal_next_actions else '',
					'recommended_next_step': str(packet_element.get('recommended_next_step') or '').strip(),
					'intake_open_item_ids': [item_id for item_id in matching_open_item_ids if item_id],
					'intake_proof_lead_ids': [lead_id for lead_id in matching_proof_lead_ids if lead_id],
					'intake_proof_leads': matching_proof_leads,
				}
			)
			summary['aligned_element_count'] += 1
			if support_status in {'unsupported', 'contradicted', 'partially_supported'}:
				summary['unsupported_shared_count'] += 1

		evidence_only_element_ids = [
			element_id
			for element_id in packet_status_by_element
			if element_id not in intake_element_ids
		]
		intake_only_element_ids = [
			element_id
			for element_id in intake_element_ids
			if element_id not in packet_status_by_element
		]
		lane_label_counts: Dict[str, int] = {}
		quality_counts: Dict[str, int] = {}
		for elem in shared_elements:
			if not isinstance(elem, dict):
				continue
			lane = str(elem.get('support_lane_label') or '').strip().lower()
			if lane:
				lane_label_counts[lane] = lane_label_counts.get(lane, 0) + 1
			quality = str(elem.get('support_quality') or '').strip().lower()
			if quality:
				quality_counts[quality] = quality_counts.get(quality, 0) + 1
		summary['claim_count'] += 1
		summary['claims'][str(claim_type)] = {
			'intake_required_element_ids': intake_element_ids,
			'packet_element_statuses': packet_status_by_element,
			'shared_elements': shared_elements,
			'intake_only_element_ids': intake_only_element_ids,
			'evidence_only_element_ids': evidence_only_element_ids,
			'support_lane_label_counts': lane_label_counts,
			'support_quality_counts': quality_counts,
		}
	return summary


def _annotate_intake_question_candidate(
	self,
	candidate: Dict[str, Any],
	claim_pressure: Dict[str, Dict[str, Any]],
	matching_pressure: Dict[str, Dict[str, Any]],
	*,
	gap_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
	annotated = dict(candidate)
	explanation = dict(candidate.get('ranking_explanation', {}) if isinstance(candidate.get('ranking_explanation'), dict) else {})
	gap_context = gap_context if isinstance(gap_context, dict) else {}
	target_claim_type = str(
		explanation.get('target_claim_type')
		or candidate.get('target_claim_type')
		or ''
	).strip().lower()
	context = candidate.get('context') if isinstance(candidate.get('context'), dict) else {}
	claim_id = str(context.get('claim_id') or '')
	dependency_graph = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
	verified_mode = (dependency_graph is not None
		and dependency_graph.metadata.get('legal_requirement_mode') == 'verified_sources')
	claim_bound = False
	if verified_mode:
		claim = dependency_graph.get_node(claim_id)
		claim_bound = claim is not None and claim.node_type == NodeType.CLAIM
		target_id = str(context.get('requirement_id') or explanation.get('target_element_id')
			or candidate.get('target_element_id') or '')
		target = dependency_graph.get_node(target_id)
		source_obligation = (target is not None
			and target.attributes.get('dependency_class') == 'legally_sourced_requirement')
		if claim_bound:
			target_claim_type = str(claim.attributes.get('claim_type') or '').strip().lower()
		elif claim_id or source_obligation:
			target_claim_type = ''
		# Generic factual/proof-lead routing may retain its advisory claim
		# type. A sourced-law match still requires an actual current claim.
		annotated['target_claim_type'] = target_claim_type
		explanation['target_claim_type'] = target_claim_type
	claim_state = claim_pressure.get(target_claim_type, {})
	matching_state = matching_pressure.get(target_claim_type, {})
	if verified_mode:
		matching_state = matching_state.get('claim_obligations', {}).get(claim_id, {}) if claim_bound else {}
	elif claim_id and 'claim_obligations' in matching_state:
		matching_state = matching_state['claim_obligations'].get(claim_id, {})
	missing_count = int(claim_state.get('missing_count', 0) or 0)
	satisfaction_ratio = float(claim_state.get('satisfaction_ratio', 0.0) or 0.0)
	matcher_missing_requirement_count = int(matching_state.get('missing_requirement_count', 0) or 0)
	matcher_confidence = float(matching_state.get('matcher_confidence', 0.0) or 0.0)
	missing_requirement_element_ids = [
		str(item).strip().lower()
		for item in (matching_state.get('missing_requirement_element_ids') or [])
		if item
	]
	blocking_level = str(explanation.get('blocking_level') or candidate.get('blocking_level') or '').strip().lower()
	question_goal = str(explanation.get('question_goal') or candidate.get('question_goal') or '').strip().lower()
	candidate_source = str(explanation.get('candidate_source') or candidate.get('candidate_source') or '').strip().lower()
	proof_priority_value = candidate.get('proof_priority')
	proof_priority = int(proof_priority_value) if proof_priority_value is not None else 99
	question_objective = str(
		candidate.get('question_objective')
		or explanation.get('question_objective')
		or ''
	).strip().lower()
	question_type = str(candidate.get('type') or explanation.get('type') or '').strip().lower()
	expected_proof_gain = str(candidate.get('expected_proof_gain') or '').strip().lower()
	actor_critic_score = float(
		candidate.get('actor_critic_score', explanation.get('actor_critic_score', 0.0)) or 0.0
	)
	target_element_id = str(
		explanation.get('target_element_id')
		or candidate.get('target_element_id')
		or ''
	).strip().lower()
	direct_legal_target_match = bool(target_element_id and target_element_id in missing_requirement_element_ids)
	question_text = str(candidate.get('question') or '').strip().lower()
	date_anchor_timeline_match = bool(
		(
			any(token in question_text for token in ('when', 'date', 'timeline', 'chronolog', 'sequence'))
			and any(token in question_text for token in ('who', 'decision', 'decisionmaker', 'manager', 'supervisor', 'person'))
		)
		or (
			(question_objective in {'establish_chronology', 'timeline'} or question_type == 'timeline')
			and any(token in question_text for token in ('who', 'decision', 'decisionmaker', 'manager', 'supervisor', 'person'))
		)
		or 'actor-by-actor' in question_text
		or 'actor by actor' in question_text
	)
	causation_match = bool(
		any(token in question_text for token in ('protected activity', 'complaint', 'accommodation', 'reported'))
		and any(token in question_text for token in ('adverse', 'retaliat', 'denial', 'termination', 'disciplin'))
		and any(token in question_text for token in ('because', 'after', 'linked', 'caus', 'reason'))
	)
	if not causation_match:
		causation_match = bool(
			question_objective in {'establish_causation', 'link_protected_activity_to_adverse_action'}
			or question_type in {'retaliation', 'causation'}
			or 'caus' in question_goal
		)
	phase1_section = str(explanation.get('phase1_section') or candidate.get('phase1_section') or '').strip().lower()
	workflow_phase = str(explanation.get('workflow_phase') or candidate.get('workflow_phase') or phase1_section or '').strip().lower()
	phase_focus_rank = self._phase_focus_rank(workflow_phase)
	phase_focus_bonus = self._phase_focus_bonus(workflow_phase)
	exact_dates_closure_match = self._is_exact_dates_closure_match(
		question_text,
		question_objective,
		question_type,
	)
	staff_names_titles_closure_match = self._is_staff_names_titles_closure_match(question_text)
	hearing_request_timing_closure_match = self._is_hearing_request_timing_closure_match(question_text)
	response_dates_closure_match = self._is_response_dates_closure_match(question_text)
	causation_sequence_match = self._is_causation_sequence_match(
		question_text,
		question_objective,
		question_type,
	)
	blocker_closure_match_count = sum(
		1
		for matched in (
			exact_dates_closure_match,
			staff_names_titles_closure_match,
			hearing_request_timing_closure_match,
			response_dates_closure_match,
		)
		if matched
	)
	expected_objectives = [
		str(value).strip().lower()
		for value in (
			gap_context.get('intake_expected_objectives')
			or gap_context.get('intake_uncovered_objectives')
			or []
		)
		if str(value).strip()
	]
	uncovered_objectives = [
		str(value).strip().lower()
		for value in (gap_context.get('intake_uncovered_objectives') or [])
		if str(value).strip()
	]
	chronology_objective_matches = self._match_chronology_objective_ledger(
		annotated,
		gap_context,
		question_text=question_text,
		question_objective=question_objective,
		question_type=question_type,
		target_claim_type=target_claim_type,
		target_element_id=target_element_id,
	)
	chronology_objective_match_count = int(chronology_objective_matches.get('chronology_objective_match_count', 0) or 0)
	if not expected_objectives:
		expected_objectives = list(uncovered_objectives)
	ordered_priority_objectives: List[str] = []
	for objective in uncovered_objectives + expected_objectives:
		if objective and objective not in ordered_priority_objectives:
			ordered_priority_objectives.append(objective)
	anchor_selection_criteria_match = bool(
		question_objective == 'anchor_selection_criteria'
		or question_type == 'anchor_selection_criteria'
		or any(
			token in question_text
			for token in (
				'selection criteria',
				'selection process',
				'not selected',
				'criteria were used',
				'qualifications',
			)
		)
	)
	causation_step_by_step_match = bool(
		causation_sequence_match
		and any(token in question_text for token in ('step by step', 'walk me through', 'what happened first', 'then what happened', 'next'))
	)
	if not causation_step_by_step_match:
		causation_step_by_step_match = bool(
			causation_sequence_match
			and all(
				any(token in question_text for token in token_group)
				for token_group in (
					('protected activity', 'complaint', 'reported', 'accommodation request', 'grievance', 'appeal'),
					('response', 'respond', 'decision', 'notice', 'management did', 'what they did'),
					('adverse', 'retaliat', 'denial', 'termination', 'disciplin', 'harm'),
				)
			)
		)
	policy_or_file_evidence_match = bool(
		any(token in question_text for token in ('policy', 'handbook', 'written rule', 'procedure', 'document', 'file', 'email', 'attachment'))
		or any(token in expected_proof_gain for token in ('policy_document', 'file_evidence', 'policy', 'document', 'file'))
	)
	needs_exhibit_grounding = bool(gap_context.get('needs_exhibit_grounding'))
	exhibit_ready_document_match = self._is_document_question_candidate(candidate)
	generic_catch_all_prompt = bool(
		question_type in {'general', 'open_ended', 'open-ended', 'general_intake_clarification', 'clarification'}
		or any(
			token in question_text
			for token in (
				'anything else',
				'any other details',
				'tell me more',
				'is there anything else',
				'any additional information',
			)
		)
	)
	weak_claim_generalization_match = bool(
		target_claim_type in {'housing_discrimination', 'hacc_research_engine'}
		or any(token in question_text for token in ('housing', 'lease', 'tenant', 'voucher', 'hacc'))
	)
	intake_priority_match: List[str] = []
	for objective in ordered_priority_objectives:
		if objective == 'anchor_selection_criteria' and anchor_selection_criteria_match:
			intake_priority_match.append(objective)
			continue
		if objective == 'causation_sequence' and (causation_sequence_match or causation_step_by_step_match):
			intake_priority_match.append(objective)
			continue
		if objective in {question_objective, question_type} and objective not in intake_priority_match:
			intake_priority_match.append(objective)
	intake_priority_rank = (
		ordered_priority_objectives.index(intake_priority_match[0])
		if intake_priority_match
		else None
	)
	intake_priority_match_count = len(intake_priority_match)
	priority_anchor_uncovered = 'anchor_selection_criteria' in uncovered_objectives

	# Derive an explicit claim_criticality label from coverage signals so callers can
	# filter or display it without re-deriving it themselves.
	if satisfaction_ratio < 0.3 or missing_count >= 3 or question_type == 'contradiction':
		claim_criticality = 'critical'
	elif satisfaction_ratio < 0.7 or missing_count >= 1:
		claim_criticality = 'important'
	else:
		claim_criticality = 'supplemental'

	score = 0.0
	score += max(0, 10 - proof_priority) * 2.0
	score += {
		'blocking': 20.0,
		'important': 10.0,
		'informational': 0.0,
	}.get(blocking_level, 0.0)
	score += {
		'dependency_graph_contradiction': 48.0,
		'intake_claim_element_gap': 18.0,
		'intake_claim_temporal_gap': 16.0,
		'intake_proof_gap': 12.0,
		'dependency_graph_requirement': 10.0,
		'knowledge_graph_gap': 6.0,
	}.get(candidate_source, 0.0)
	score += {
		'establish_element': 8.0,
		'identify_supporting_proof': 5.0,
		'resolve_factual_contradiction': 12.0,
	}.get(question_goal, 0.0)
	score += min(missing_count, 5) * 2.0
	score += max(0.0, 1.0 - satisfaction_ratio) * 5.0
	score += min(matcher_missing_requirement_count, 5) * 3.0
	score += max(0.0, 1.0 - matcher_confidence) * 4.0
	if direct_legal_target_match:
		score += 15.0
	score += max(-3.0, min(6.0, actor_critic_score)) * (4.0 if intake_priority_match else 3.0)
	if question_type == 'contradiction':
		score += 12.0
	score += max(-3.0, min(6.0, actor_critic_score)) * 3.0
	if date_anchor_timeline_match:
		score += 11.0
	if causation_match:
		score += 12.0
	if exact_dates_closure_match:
		score += 14.0
	if staff_names_titles_closure_match:
		score += 13.0
	if hearing_request_timing_closure_match:
		score += 12.0
	if response_dates_closure_match:
		score += 12.0
	if causation_sequence_match:
		score += 14.0
	if causation_step_by_step_match:
		score += 16.0
	if anchor_selection_criteria_match:
		score += 18.0
	if policy_or_file_evidence_match:
		score += 10.0
	if exhibit_ready_document_match and needs_exhibit_grounding:
		score += 14.0
	if weak_claim_generalization_match:
		score += 5.0
	if intake_priority_match:
		score += 20.0
		if intake_priority_rank is not None:
			score += max(0.0, 8.0 - float(intake_priority_rank) * 2.0)
	if chronology_objective_match_count:
		score += chronology_objective_match_count * 12.0
	if bool(chronology_objective_matches.get('chronology_objective_direct_issue_match', False)):
		score += 18.0
	if generic_catch_all_prompt:
		score -= 12.0
	if priority_anchor_uncovered and generic_catch_all_prompt and not anchor_selection_criteria_match:
		score -= 16.0
	score += blocker_closure_match_count * 4.0
	if question_type == 'contradiction' or candidate_source == 'dependency_graph_contradiction':
		score += 20.0
	if any(token in expected_proof_gain for token in ('date', 'timeline', 'chronolog', 'caus', 'because', 'adverse', 'protected activity')):
		score += 4.0
	score += phase_focus_bonus
	workflow_action_queue = self._build_intake_workflow_action_queue(
		self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {},
		claim_pressure,
		matching_pressure,
	)
	workflow_action_matches = self._build_question_workflow_action_matches(annotated, workflow_action_queue)
	workflow_action_rank = workflow_action_matches.get('workflow_action_rank')
	workflow_action_match_count = int(workflow_action_matches.get('workflow_action_match_count', 0) or 0)
	if workflow_action_match_count:
		score += workflow_action_match_count * 5.0
	if workflow_action_rank is not None:
		score += max(0.0, 5.0 - float(workflow_action_rank))

	selector_signals = {
		'candidate_source': candidate_source,
		'blocking_level': blocking_level,
		'question_goal': question_goal,
		'proof_priority': proof_priority,
		'claim_missing_dependency_count': missing_count,
		'claim_satisfaction_ratio': satisfaction_ratio,
		'matcher_missing_requirement_count': matcher_missing_requirement_count,
		'matcher_confidence': matcher_confidence,
		'matcher_missing_requirement_element_ids': missing_requirement_element_ids,
		'direct_legal_target_match': direct_legal_target_match,
		'actor_critic_score': actor_critic_score,
		'date_anchor_timeline_match': date_anchor_timeline_match,
		'protected_activity_causation_match': causation_match,
		'question_objective': question_objective,
		'question_type': question_type,
		'phase1_section': phase1_section,
		'workflow_phase': workflow_phase,
		'phase_focus_rank': phase_focus_rank,
		'exact_dates_closure_match': exact_dates_closure_match,
		'staff_names_titles_closure_match': staff_names_titles_closure_match,
		'hearing_request_timing_closure_match': hearing_request_timing_closure_match,
		'response_dates_closure_match': response_dates_closure_match,
		'causation_sequence_match': causation_sequence_match,
		'causation_step_by_step_match': causation_step_by_step_match,
		'blocker_closure_match_count': blocker_closure_match_count,
		'anchor_selection_criteria_match': anchor_selection_criteria_match,
		'generic_catch_all_prompt': generic_catch_all_prompt,
		'policy_or_file_evidence_match': policy_or_file_evidence_match,
		'exhibit_ready_document_match': exhibit_ready_document_match,
		'needs_exhibit_grounding': needs_exhibit_grounding,
		'weak_claim_generalization_match': weak_claim_generalization_match,
		'intake_expected_objectives': expected_objectives,
		'intake_uncovered_objectives': uncovered_objectives,
		'intake_priority_match': intake_priority_match,
		'intake_priority_rank': intake_priority_rank,
		'intake_priority_match_count': intake_priority_match_count,
		'chronology_objective_match_count': chronology_objective_match_count,
		'chronology_objective_issue_ids': list(chronology_objective_matches.get('chronology_objective_issue_ids') or []),
		'chronology_objective_prompt_families': list(chronology_objective_matches.get('chronology_objective_prompt_families') or []),
		'chronology_objective_preferred_objectives': list(chronology_objective_matches.get('chronology_objective_preferred_objectives') or []),
		'chronology_objective_direct_issue_match': bool(chronology_objective_matches.get('chronology_objective_direct_issue_match', False)),
		'workflow_action_match_count': workflow_action_match_count,
		'workflow_action_rank': workflow_action_rank,
		'workflow_action_phase': workflow_action_matches.get('workflow_action_phase', ''),
		'workflow_action_focus_areas': list(workflow_action_matches.get('workflow_action_focus_areas') or []),
		'claim_criticality': claim_criticality,
	}
	annotated['selector_score'] = score
	annotated['claim_criticality'] = claim_criticality
	annotated['selector_signals'] = selector_signals
	explanation['selector_score'] = score
	explanation['claim_criticality'] = claim_criticality
	explanation['selector_signals'] = selector_signals
	explanation['actor_critic_score'] = actor_critic_score
	explanation['date_anchor_timeline_match'] = date_anchor_timeline_match
	explanation['protected_activity_causation_match'] = causation_match
	explanation['exact_dates_closure_match'] = exact_dates_closure_match
	explanation['staff_names_titles_closure_match'] = staff_names_titles_closure_match
	explanation['hearing_request_timing_closure_match'] = hearing_request_timing_closure_match
	explanation['response_dates_closure_match'] = response_dates_closure_match
	explanation['causation_sequence_match'] = causation_sequence_match
	explanation['causation_step_by_step_match'] = causation_step_by_step_match
	explanation['anchor_selection_criteria_match'] = anchor_selection_criteria_match
	explanation['generic_catch_all_prompt'] = generic_catch_all_prompt
	explanation['policy_or_file_evidence_match'] = policy_or_file_evidence_match
	explanation['exhibit_ready_document_match'] = exhibit_ready_document_match
	explanation['needs_exhibit_grounding'] = needs_exhibit_grounding
	explanation['weak_claim_generalization_match'] = weak_claim_generalization_match
	explanation['intake_expected_objectives'] = expected_objectives
	explanation['intake_uncovered_objectives'] = uncovered_objectives
	explanation['intake_priority_match'] = intake_priority_match
	explanation['intake_priority_rank'] = intake_priority_rank
	explanation['intake_priority_match_count'] = intake_priority_match_count
	explanation['blocker_closure_match_count'] = blocker_closure_match_count
	annotated['ranking_explanation'] = explanation
	denoiser = getattr(self, 'denoiser', None)
	if denoiser is not None and hasattr(denoiser, '_annotate_proof_directed_candidate'):
		annotated = denoiser._annotate_proof_directed_candidate(annotated)
	return annotated


def select_intake_question_candidates(
	self,
	candidates: List[Dict[str, Any]],
	*,
	max_questions: int = 10,
) -> List[Dict[str, Any]]:
	"""Default intake-question selector using explicit reasoning signals and a fallback heuristic."""
	normalized_candidates = [candidate for candidate in (candidates or []) if isinstance(candidate, dict)]
	case_file = self._intake_case_file_for_questions()
	denoiser = getattr(self, "denoiser", None)
	if case_file is not None and denoiser is not None and hasattr(denoiser, "load_question_dispositions"):
		denoiser.load_question_dispositions(case_file)
	if denoiser is not None and hasattr(denoiser, "is_question_target_closed"):
		filtered_candidates = []
		for candidate in normalized_candidates:
			target_id, revision = self._question_target_identity(candidate)
			if target_id and denoiser.is_question_target_closed(target_id, revision):
				continue
			filtered_candidates.append(candidate)
		normalized_candidates = filtered_candidates
	elif case_file is not None:
		from complaint_phases.intake_case_file import question_target_is_closed
		normalized_candidates = [
			candidate for candidate in normalized_candidates
			if not question_target_is_closed(case_file, *self._question_target_identity(candidate)[:1], self._question_target_identity(candidate)[1])
		]
	if not normalized_candidates:
		return []
	dg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
	kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
	intake_case_file = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
	gap_context = self.build_inquiry_gap_context()
	claim_pressure = self._build_intake_claim_pressure_map(dg)
	matching_pressure = self._build_intake_matching_pressure_map(kg, dg, intake_case_file)
	scored_candidates = [
		self._annotate_intake_question_candidate(
			candidate,
			claim_pressure,
			matching_pressure,
			gap_context=gap_context,
		)
		for candidate in normalized_candidates
	]
	uncovered_objectives = {
		str(value).strip().lower()
		for value in (
			gap_context.get('intake_uncovered_objectives')
			or gap_context.get('intake_expected_objectives')
			or []
		)
		if str(value).strip()
	}
	weak_claim_types = {
		str(value).strip().lower()
		for value in (gap_context.get('weak_claim_types') or [])
		if str(value).strip()
	}
	weak_modalities = {
		str(value).strip().lower()
		for value in (gap_context.get('weak_evidence_modalities') or [])
		if str(value).strip()
	}
	needs_exhibit_grounding = bool(gap_context.get('needs_exhibit_grounding'))

	def _signals(candidate: Dict[str, Any]) -> Dict[str, Any]:
		signals = candidate.get('selector_signals')
		return signals if isinstance(signals, dict) else {}

	def _text_blob(candidate: Dict[str, Any], signals: Dict[str, Any]) -> str:
		parts = (
			candidate.get('question'),
			candidate.get('expected_proof_gain'),
			candidate.get('question_objective'),
			candidate.get('type'),
			signals.get('question_objective'),
			signals.get('question_type'),
		)
		return ' '.join(str(value or '').strip().lower() for value in parts if str(value or '').strip())

	def _matches_any(text: str, token_sets: List[List[str]]) -> bool:
		for tokens in token_sets:
			if all(token in text for token in tokens):
				return True
		return False

	def _anchor_appeal_rights_match(candidate: Dict[str, Any], signals: Dict[str, Any], text: str) -> bool:
		question_objective = str(
			candidate.get('question_objective')
			or signals.get('question_objective')
			or ''
		).strip().lower()
		question_type = str(candidate.get('type') or signals.get('question_type') or '').strip().lower()
		return bool(
			signals.get('anchor_appeal_rights_match', False)
			or question_objective == 'anchor_appeal_rights'
			or question_type == 'anchor_appeal_rights'
			or _matches_any(
				text,
				[
					['appeal', 'right'],
					['right to appeal'],
					['appeal rights'],
					['appeal', 'deadline'],
					['notice', 'appeal'],
				],
			)
		)

	def _anchor_grievance_hearing_match(candidate: Dict[str, Any], signals: Dict[str, Any], text: str) -> bool:
		question_objective = str(
			candidate.get('question_objective')
			or signals.get('question_objective')
			or ''
		).strip().lower()
		question_type = str(candidate.get('type') or signals.get('question_type') or '').strip().lower()
		return bool(
			signals.get('anchor_grievance_hearing_match', False)
			or question_objective == 'anchor_grievance_hearing'
			or question_type == 'anchor_grievance_hearing'
			or _matches_any(
				text,
				[
					['grievance', 'hearing'],
					['hearing', 'request'],
					['hearing officer'],
					['grievance process'],
					['informal hearing'],
				],
			)
		)

	def _anchor_selection_criteria_match(candidate: Dict[str, Any], signals: Dict[str, Any], text: str) -> bool:
		question_objective = str(
			candidate.get('question_objective')
			or signals.get('question_objective')
			or ''
		).strip().lower()
		question_type = str(candidate.get('type') or signals.get('question_type') or '').strip().lower()
		return bool(
			signals.get('anchor_selection_criteria_match', False)
			or question_objective == 'anchor_selection_criteria'
			or question_type == 'anchor_selection_criteria'
			or _matches_any(
				text,
				[
					['selection criteria'],
					['selection process'],
					['criteria', 'used'],
					['not selected'],
					['qualifications'],
				],
			)
		)

	def _generic_catch_all_prompt(signals: Dict[str, Any], text: str) -> bool:
		return bool(
			signals.get('generic_catch_all_prompt', False)
			or _matches_any(
				text,
				[
					['anything else'],
					['any other details'],
					['tell me more'],
					['is there anything else'],
					['any additional information'],
				],
			)
		)

	def _anchor_specific_fallback_probe(
		signals: Dict[str, Any],
		candidate_source: str,
		anchor_match: bool,
		generic_prompt: bool,
	) -> bool:
		return bool(
			anchor_match
			and (
				generic_prompt
				or 'fallback' in candidate_source
				or candidate_source in {'intake_proof_gap', 'knowledge_graph_gap', 'dependency_graph_requirement'}
			)
		)

	def _anchor_grievance_fallback_probe(candidate: Dict[str, Any], signals: Dict[str, Any], text: str) -> bool:
		candidate_source = str(
			signals.get('candidate_source')
			or candidate.get('candidate_source')
			or ''
		).strip().lower()
		anchor_match = _anchor_grievance_hearing_match(candidate, signals, text)
		generic_prompt = _generic_catch_all_prompt(signals, text)
		return _anchor_specific_fallback_probe(signals, candidate_source, anchor_match, generic_prompt)

	def _anchor_selection_fallback_probe(candidate: Dict[str, Any], signals: Dict[str, Any], text: str) -> bool:
		candidate_source = str(
			signals.get('candidate_source')
			or candidate.get('candidate_source')
			or ''
		).strip().lower()
		anchor_match = _anchor_selection_criteria_match(candidate, signals, text)
		generic_prompt = _generic_catch_all_prompt(signals, text)
		return _anchor_specific_fallback_probe(signals, candidate_source, anchor_match, generic_prompt)

	def _hearing_request_timing_triplet_match(candidate: Dict[str, Any], signals: Dict[str, Any], text: str) -> bool:
		question_objective = str(
			candidate.get('question_objective')
			or signals.get('question_objective')
			or ''
		).strip().lower()
		question_type = str(candidate.get('type') or signals.get('question_type') or '').strip().lower()
		if question_objective == 'hearing_request_timing' or question_type == 'hearing_request_timing':
			return True
		requested_when = _matches_any(
			text,
			[
				['when', 'requested', 'hearing'],
				['when', 'requested', 'review'],
				['request date', 'hearing'],
				['requested', 'appeal', 'when'],
			],
		)
		request_method = _matches_any(
			text,
			[
				['how', 'requested'],
				['request method'],
				['requested', 'in writing'],
				['requested', 'email'],
				['requested', 'portal'],
				['requested', 'phone'],
			],
		)
		hacc_response_when = _matches_any(
			text,
			[
				['when', 'hacc', 'responded'],
				['hacc', 'response date'],
				['when', 'management', 'responded'],
				['response', 'to', 'request', 'when'],
			],
		)
		return requested_when and request_method and hacc_response_when

	def _actor_critic_priority_score(candidate: Dict[str, Any]) -> float:
		signals = _signals(candidate)
		text = _text_blob(candidate, signals)
		candidate_source = str(
			signals.get('candidate_source')
			or candidate.get('candidate_source')
			or ''
		).strip().lower()
		target_claim_type = str(
			candidate.get('target_claim_type')
			or (
				candidate.get('ranking_explanation', {})
				if isinstance(candidate.get('ranking_explanation'), dict)
				else {}
			).get('target_claim_type')
			or ''
		).strip().lower()
		anchor_appeal_match = _anchor_appeal_rights_match(candidate, signals, text)
		anchor_grievance_match = _anchor_grievance_hearing_match(candidate, signals, text)
		anchor_selection_match = _anchor_selection_criteria_match(candidate, signals, text)
		anchor_match = anchor_appeal_match or anchor_grievance_match or anchor_selection_match
		generic_prompt = _generic_catch_all_prompt(signals, text)
		anchor_fallback_probe = _anchor_specific_fallback_probe(signals, candidate_source, anchor_match, generic_prompt)
		anchor_grievance_fallback = _anchor_grievance_fallback_probe(candidate, signals, text)
		anchor_selection_fallback = _anchor_selection_fallback_probe(candidate, signals, text)
		causation_sequence_match = bool(signals.get('causation_sequence_match', False))
		hearing_request_timing_match = bool(
			signals.get('hearing_request_timing_closure_match', False)
			or _matches_any(
				text,
				[
					['hearing', 'request', 'when'],
					['grievance', 'request', 'date'],
					['appeal', 'requested', 'when'],
				],
			)
		)
		hearing_request_timing_triplet_match = _hearing_request_timing_triplet_match(candidate, signals, text)
		policy_or_file_evidence_match = bool(
			signals.get('policy_or_file_evidence_match', False)
			or any(token in text for token in ('policy document', 'written policy', 'file evidence', 'case file', 'notice attachment'))
		)
		exhibit_ready_document_match = bool(
			signals.get('exhibit_ready_document_match', False)
			or self._is_document_question_candidate(candidate, signals)
		)
		weak_claim_generalization_match = bool(
			signals.get('weak_claim_generalization_match', False)
			or target_claim_type in {'housing_discrimination', 'hacc_research_engine'}
		)

		actor_critic_score = float(
			candidate.get('actor_critic_score', signals.get('actor_critic_score', 0.0)) or 0.0
		)
		adjustment = 0.0
		if anchor_fallback_probe and (
			'anchor_appeal_rights' in uncovered_objectives
			or 'anchor_grievance_hearing' in uncovered_objectives
			or 'anchor_selection_criteria' in uncovered_objectives
		):
			adjustment += 1.5
		if anchor_grievance_fallback and 'anchor_grievance_hearing' in uncovered_objectives:
			adjustment += 1.25
		if anchor_selection_fallback and 'anchor_selection_criteria' in uncovered_objectives:
			adjustment += 1.25
		if causation_sequence_match and 'causation_sequence' in uncovered_objectives:
			adjustment += 0.75
		if hearing_request_timing_match and 'hearing_request_timing' in uncovered_objectives:
			adjustment += 0.75
		if hearing_request_timing_triplet_match and 'hearing_request_timing' in uncovered_objectives:
			adjustment += 1.25
		if policy_or_file_evidence_match and weak_modalities.intersection({'policy_document', 'file_evidence'}):
			adjustment += 1.0
		if exhibit_ready_document_match and needs_exhibit_grounding:
			adjustment += 1.75
		if weak_claim_generalization_match and target_claim_type in weak_claim_types:
			adjustment += 1.0
		return actor_critic_score + adjustment

	def _sort_key(candidate: Dict[str, Any]):
		signals = _signals(candidate)
		text = _text_blob(candidate, signals)
		candidate_source = str(signals.get('candidate_source') or candidate.get('candidate_source') or '').strip().lower()
		anchor_appeal_match = _anchor_appeal_rights_match(candidate, signals, text)
		anchor_grievance_match = _anchor_grievance_hearing_match(candidate, signals, text)
		anchor_selection_match = _anchor_selection_criteria_match(candidate, signals, text)
		anchor_match = anchor_appeal_match or anchor_grievance_match or anchor_selection_match
		generic_prompt = _generic_catch_all_prompt(signals, text)
		anchor_fallback_probe = _anchor_specific_fallback_probe(
			signals,
			candidate_source,
			anchor_match,
			generic_prompt,
		)
		anchor_grievance_fallback = _anchor_grievance_fallback_probe(candidate, signals, text)
		anchor_selection_fallback = _anchor_selection_fallback_probe(candidate, signals, text)
		hearing_request_timing_triplet_match = _hearing_request_timing_triplet_match(candidate, signals, text)
		return (
			int(candidate.get('type') != 'legal_context'),
			-float(candidate.get('selector_score', 0.0) or 0.0),
			int(signals.get('phase_focus_rank', 99) or 99),
			-int(signals.get('blocker_closure_match_count', 0) or 0),
			-int(signals.get('intake_priority_match_count', 0) or 0),
			-int(bool(anchor_appeal_match)),
			-int(bool(anchor_grievance_match)),
			-int(bool(anchor_selection_match)),
			-int(bool(anchor_fallback_probe)),
			-int(bool(anchor_grievance_fallback and 'anchor_grievance_hearing' in uncovered_objectives)),
			-int(bool(anchor_selection_fallback and 'anchor_selection_criteria' in uncovered_objectives)),
			-int(bool(hearing_request_timing_triplet_match and 'hearing_request_timing' in uncovered_objectives)),
			int(bool(generic_prompt and not anchor_match)),
			-int(bool(signals.get('causation_sequence_match', False))),
			-int(bool(signals.get('hearing_request_timing_closure_match', False))),
			-int(bool(signals.get('policy_or_file_evidence_match', False))),
			-int(bool(signals.get('weak_claim_generalization_match', False))),
			-_actor_critic_priority_score(candidate),
			int(candidate.get('proof_priority', 99) or 99),
			*_target_rank_tuple(candidate),
		)

	denoiser = getattr(self, 'denoiser', None)

	def _target_rank_tuple(candidate: Dict[str, Any]):
		ranker = getattr(denoiser, '_target_rank_tuple', None) if denoiser is not None else None
		if callable(ranker):
			return ranker(candidate)
		target = candidate.get('unresolved_target') if isinstance(candidate.get('unresolved_target'), dict) else {}
		answerability = str(target.get('user_answerability') or 'user_observable')
		answer_rank = {'user_observable': 0, 'partial': 1, 'not_answerable': 2, 'operator_only': 3}.get(answerability, 2)
		return (
			-int(target.get('dependency_impact') or 0),
			-int(target.get('uncertainty') or 0),
			answer_rank,
			str(target.get('target_id') or ''),
		)

	scored_candidates.sort(key=_sort_key)
	if denoiser is not None and hasattr(denoiser, '_select_proof_directed_candidates'):
		selected = denoiser._select_proof_directed_candidates(
			scored_candidates,
			max_questions=max_questions,
			preserve_order=True,
		)
	else:
		selected = scored_candidates[:max_questions]
	return self._apply_exhibit_ready_intake_questioning(
		selected,
		gap_context=gap_context,
	)


def process_denoising_answer(
	self,
	question: Dict[str, Any],
	answer: str,
	answer_event_id: Optional[str] = None,
	source_context: Optional[Dict[str, Any]] = None,
	factual_action: Optional[str] = None,
	supersedes_stable_id: Optional[str] = None,
	retracts_stable_id: Optional[str] = None,
	contradicts_stable_id: Optional[str] = None,
	transition_id: Optional[str] = None,
) -> Dict[str, Any]:
	"""
	Process an answer to a denoising question in Phase 1.

	Args:
		question: The question that was asked
		answer: The user's answer

	Returns:
		Updated status with next questions or phase transition info
	"""
	if transition_id and not answer_event_id:
		answer_event_id = f"transition:{transition_id}"
	kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
	dg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
	from complaint_phases.knowledge_graph import answer_event_payload
	event_payload = answer_event_payload(
		question=question,
		answer=answer,
		source_context=source_context,
		factual_action=factual_action,
		supersedes_stable_id=supersedes_stable_id,
		retracts_stable_id=retracts_stable_id,
		contradicts_stable_id=contradicts_stable_id,
	)
	if answer_event_id and kg is not None and hasattr(kg, "begin_answer_event"):
		prior = kg.begin_answer_event(answer_event_id, event_payload)
		if prior is not None and prior.get("mediator_result") is not None:
			return prior["mediator_result"]

	from integrations.ipfs_datasets.graphs import (
		requirement_definition_snapshot,
		restore_requirement_definition,
	)
	definition_snapshots = {}
	if dg is not None:
		for node in dg.nodes.values():
			definition_snapshots[node.id] = {
				"definition": requirement_definition_snapshot(node),
				"satisfied": bool(node.satisfied),
			}

	# Process the answer
	updates = self.denoiser.process_answer(
		question,
		answer,
		kg,
		dg,
		answer_event_id=answer_event_id,
		source_context=source_context,
		factual_action=factual_action,
		supersedes_stable_id=supersedes_stable_id,
		retracts_stable_id=retracts_stable_id,
		contradicts_stable_id=contradicts_stable_id,
	)
	self._update_intake_contradiction_state(dg)
	intake_case_file = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
	is_context_answer = str((question or {}).get('type') or '').strip().lower() == 'legal_context'
	if not is_context_answer:
		intake_case_file = self._apply_intake_answer_to_case_file(
			question,
			answer,
			intake_case_file,
			kg,
			factual_action=factual_action,
		)
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', intake_case_file)
	dg = self.dg_builder.sync_intake_timeline_to_graph(dg, intake_case_file)
	question_type = str((question or {}).get('type') or '').strip().lower()
	clarification_keys = {
		'timeline': ['timeline', 'decision_timeline', 'notice', 'hearing'],
		'responsible_party': ['actor', 'responsible_party', 'decision_timeline'],
		'clarification': ['clarification'],
		'contradiction': ['contradiction'],
	}.get(question_type, [])
	fact_ids = [str(updates[key]) for key in ('stable_id', 'entity_id', 'superseded_stable_id', 'retracted_stable_id') if updates.get(key)]
	fact_ids.extend(str(item) for item in (updates.get('conflict_stable_ids') or []))
	if dg is not None and (clarification_keys or fact_ids):
		self.refresh_verified_legal_dependencies({
			'fact_change': True, 'clarification_keys': clarification_keys,
			'fact_ids': fact_ids, 'factual_revision': updates.get('revision'),
		})
		dg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph') or dg

	from complaint_phases.intake_case_file import project_graph_revision_view
	if is_context_answer:
		# A context answer retains exact user-input provenance, but a bare
		# jurisdiction/date/claim label is not a factual assertion or support.
		from integrations.ipfs_datasets.graphs import exact_statement_provenance
		answer_source = source_context if isinstance(source_context, dict) else {}
		source_text = answer_source.get('source_text')
		if not isinstance(source_text, str) or not source_text:
			source_text = str(answer or '')
		provenance = exact_statement_provenance(source_text, str(answer or ''))
		if kg is not None and hasattr(kg, 'append_revision'):
			revision = kg.append_revision({
				'action': 'context_answer', 'event_id': answer_event_id or '',
				'statement': provenance.get('statement') or str(answer or ''),
				'source_hash': provenance.get('source_hash'),
				'source_span': provenance.get('source_span'),
				'deficiency': provenance.get('deficiency') or '',
				'epistemic_class': 'user_context', 'value_status': 'context_only',
				'question': dict(question) if isinstance(question, dict) else {},
				'disposition': updates.get('disposition'),
				'context_answer_status': updates.get('context_answer_status') or updates.get('disposition'),
				'context_fields_updated': list(updates.get('context_fields_updated') or []),
				'creates_fact': False, 'satisfies_requirement': False,
				'support_changes': [], 'entity_id': '', 'stable_id': '',
				'audit_retained': True,
				'provenance': dict(provenance),
			})
			updates = dict(updates, graph_revision=revision,
			               epistemic_class='user_context', value_status='context_only', support_changes=[])
	else:
		from complaint_phases.knowledge_graph import record_answer_graph_revision
		from integrations.ipfs_datasets.graphs import classify_epistemic_class, statement_value_status
		question_context = (question or {}).get("context") if isinstance((question or {}).get("context"), dict) else {}
		explicit_class = str(question_context.get("epistemic_class") or (question or {}).get("epistemic_class") or "")
		if explicit_class == "legal_authority":
			explicit_class = ""
		epistemic_class = classify_epistemic_class(answer, explicit=explicit_class)
		value_status = statement_value_status(answer)
		non_fact_dispositions = {"unknown", "refused", "skipped", "deferred", "invalidated"}
		if isinstance(updates, dict) and str(updates.get("disposition") or "") in non_fact_dispositions:
			value_status = str(updates.get("disposition") or value_status or "unknown")
			explicit_class = ""
			epistemic_class = "user_non_answer"
		target_ids = {
			str(item).strip()
			for item in (
				question_context.get("requirement_id"),
				question_context.get("target_element_id"),
				question_context.get("node_id"),
				(question or {}).get("target_element_id"),
			)
			if str(item or "").strip()
		}
		support_changes = []
		if dg is not None:
			for node_id, snapshot in definition_snapshots.items():
				node = dg.nodes.get(node_id)
				if node is None:
					continue
				restore_requirement_definition(node, snapshot["definition"])
				if node_id in target_ids and value_status == "unknown":
					node.satisfied = snapshot["satisfied"]
					node.attributes["value_status"] = "unknown"
					node.attributes["unknown_value"] = answer
				elif node_id in target_ids and value_status == "contradiction":
					node.attributes["value_status"] = "contradiction"
					node.attributes["contradiction_value"] = answer
			for target_id in sorted(target_ids):
				node = dg.nodes.get(target_id)
				if node is None:
					continue
				change = {
					"requirement_id": node.id,
					"epistemic_class": epistemic_class,
					"statement": answer,
					"value_status": value_status,
					"definition_unchanged": True,
				}
				node.attributes["element_support"] = list(node.attributes.get("element_support") or []) + [change]
				support_changes.append(change)
		if kg is not None and hasattr(kg, "append_revision"):
			answer_source = source_context if isinstance(source_context, dict) else {}
			source_text = answer_source.get("source_text") if isinstance(answer_source.get("source_text"), str) and answer_source.get("source_text") else str(answer or "")
			revision = record_answer_graph_revision(
				kg,
				answer=str(answer or ""),
				source_text=source_text,
				source_context=answer_source,
				question=question if isinstance(question, dict) else {},
				event_id=answer_event_id or "",
				epistemic_class=epistemic_class,
				value_status=value_status,
				support_changes=support_changes,
			)
			if isinstance(updates, dict):
				updates = dict(updates)
				updates["graph_revision"] = revision
				updates["epistemic_class"] = epistemic_class
				updates["value_status"] = value_status
				updates["support_changes"] = support_changes
	intake_case_file = project_graph_revision_view(intake_case_file, kg)
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', intake_case_file)

	# Generate next questions
	max_questions = 5
	try:
		if hasattr(self.denoiser, "is_stagnating") and self.denoiser.is_stagnating():
			max_questions = 8
	except Exception as exc:
		self.log(
			'denoising_stagnation_check_degraded',
			operation='is_stagnating',
			error=str(exc),
			error_type=type(exc).__name__,
		)
		max_questions = 5
	question_candidates = self.denoiser.collect_question_candidates(
		kg,
		dg,
		max_questions=max_questions,
		intake_case_file=intake_case_file,
	)
	intake_matching_pressure = self._build_intake_matching_pressure_map(kg, dg, intake_case_file)
	intake_workflow_action_queue = self._build_intake_workflow_action_queue(
		intake_case_file,
		self._build_intake_claim_pressure_map(dg),
		intake_matching_pressure,
	)
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_matching_pressure', intake_matching_pressure)
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_workflow_action_queue', intake_workflow_action_queue)
	questions = self.denoiser.generate_questions(
		kg,
		dg,
		max_questions=max_questions,
		intake_case_file=intake_case_file,
	)
	if kg is not None and hasattr(kg, "factual_ledger"):
		reopened = list(kg.factual_ledger().get("reopened_questions") or [])
		if reopened:
			questions = reopened + [
				question_item for question_item in questions
				if question_item not in reopened
			]
	questions = self._intake_question_proposals(questions, source_text=answer)
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'question_candidates', question_candidates)
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_questions', questions)

	# Update graphs in phase data
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)

	# Calculate new noise level
	noise = self.denoiser.calculate_noise_level(kg, dg)
	kg_gaps = kg.find_gaps()
	gaps = len(kg_gaps)
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_gaps', kg_gaps)
	self.phase_manager.update_phase_data(
		ComplaintPhase.INTAKE,
		'intake_gap_types',
		[gap.get('type') for gap in kg_gaps if isinstance(gap, dict) and gap.get('type')]
		+ (['legal_context_source_gap'] if dg.metadata.get('legal_source_gaps') else []),
	)
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', gaps)

	# Record iteration
	self.phase_manager.record_iteration(noise, {
		'entities': len(kg.entities),
		'relationships': len(kg.relationships),
		'gaps': gaps,
		'updates': updates,
		'denoiser_policy': self.denoiser.get_policy_state() if hasattr(self.denoiser, 'get_policy_state') else None,
	})

	# Loss plateaus, an empty question list, and the question-count cap are
	# explicit incomplete stops. They do not mark the interview converged.
	from complaint_phases.phase_manager import _DENOISING_MAX_ITERATIONS
	provider_status = None
	if isinstance(intake_case_file, dict):
		interview_provider = intake_case_file.get('interview_provider')
		if isinstance(interview_provider, dict):
			provider_status = interview_provider.get('status')
	interview_stop = self.denoiser.evaluate_interview_stop(
		open_questions=questions,
		intake_case_file=intake_case_file if isinstance(intake_case_file, dict) else None,
		provider_status=provider_status,
		iteration_count=self.phase_manager.iteration_count,
		iteration_cap=_DENOISING_MAX_ITERATIONS,
		loss_converged=self.phase_manager.has_converged(),
		pool_empty=len(getattr(self.denoiser, 'questions_pool', []) or []) == 0,
	)
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'interview_stop', interview_stop)
	from complaint_phases.denoiser import project_stopping_policy
	stopping_policy = project_stopping_policy(interview_stop)
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'stopping_policy', stopping_policy)
	converged = (
		interview_stop.get('state') == 'saturated'
		and bool(interview_stop.get('intake_complete'))
	)
	self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', converged)

	result = {
		'updates': updates,
		'noise_level': noise,
		'gaps_remaining': gaps,
		'converged': converged,
		'interview_stop': interview_stop,
		'stopping_policy': stopping_policy,
		'filing_ready': False,
		'intake_complete': bool(interview_stop.get('intake_complete')),
		'intake_matching_summary': self._summarize_intake_matching_pressure(intake_matching_pressure),
		'intake_workflow_action_queue': intake_workflow_action_queue,
		'intake_workflow_action_summary': self._summarize_intake_workflow_action_queue(intake_workflow_action_queue),
		'intake_legal_targeting_summary': self._summarize_intake_legal_targeting(
			intake_matching_pressure,
			question_candidates,
		),
		'question_candidates': question_candidates,
		'next_questions': questions,
		'iteration': self.phase_manager.iteration_count,
		'intake_readiness': self.phase_manager.get_intake_readiness(),
		'next_action': self.phase_manager.get_next_action(),
	}

	# Check if ready to advance to Phase 2. Incomplete stops never say so.
	incomplete_stop = interview_stop.get('state') in {
		'needs_answer', 'deferred_unknown', 'provider_unavailable', 'cancelled', 'limit_reached',
		'no_progress', 'needs_review',
	} or interview_stop.get('outcome') in {
		'paused', 'awaiting_user', 'deferred_needs_evidence', 'blocked_provider',
		'no_progress', 'needs_review', 'saturated',
	}
	if incomplete_stop or not interview_stop.get('intake_complete'):
		result['ready_for_evidence_phase'] = False
		result['filing_ready'] = False
		result['message'] = interview_stop.get('message')
	elif self.phase_manager.is_phase_complete(ComplaintPhase.INTAKE):
		result['ready_for_evidence_phase'] = True
		result['filing_ready'] = False
		result['message'] = 'Initial intake complete. Ready to gather evidence.'
	if answer_event_id and kg is not None and hasattr(kg, "finish_answer_event"):
		kg.finish_answer_event(
			answer_event_id,
			event_payload,
			denoiser_updates=dict(updates) if isinstance(updates, dict) else updates,
			mediator_result=result,
		)
	return result

