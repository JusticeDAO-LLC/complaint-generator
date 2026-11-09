"""Claim-support temporal and element reasoning diagnostics.

These functions own the bodies previously inlined on
:class:`mediator.claim_support_hooks.ClaimSupportHook`. Each function takes
the hook instance as ``self`` so existing private-method calls keep working
through one-line delegates on the class.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Dict, List, Optional

from complaint_analysis.temporal_rule_profiles import evaluate_temporal_rule_profile
from integrations.ipfs_datasets.graphrag import (
    build_ontology,
    build_validate_score_ontology,
    validate_ontology,
)
from integrations.ipfs_datasets.logic import (
    build_legal_ir_premise_inventory,
    check_contradictions,
    generate_bound_legal_ir_proof_obligations,
    proof_cache_identity,
    prove_claim_elements,
    replay_satisfied_element_proof,
    route_bound_legal_ir_proof,
    run_hybrid_reasoning,
)


def _build_temporal_proof_bundle(
    self,
    claim_type: str,
    element: Dict[str, Any],
    temporal_context: Optional[Dict[str, Any]],
    temporal_rule_profile: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    profile = temporal_rule_profile if isinstance(temporal_rule_profile, dict) else {}
    if not bool(profile.get('available', False)):
        return {}

    context = temporal_context if isinstance(temporal_context, dict) else {}
    facts = [fact for fact in (context.get('temporal_facts', []) or []) if isinstance(fact, dict)]
    relations = [relation for relation in (context.get('temporal_relations', []) or []) if isinstance(relation, dict)]
    issues = [issue for issue in (context.get('temporal_issues', []) or []) if isinstance(issue, dict)]

    fact_ids = [
        str(fact.get('fact_id') or '').strip()
        for fact in facts
        if str(fact.get('fact_id') or '').strip()
    ]
    timeline_anchor_ids: List[str] = []
    for fact in facts:
        for anchor_id in fact.get('timeline_anchor_ids', []) or []:
            normalized_anchor_id = str(anchor_id or '').strip()
            if normalized_anchor_id and normalized_anchor_id not in timeline_anchor_ids:
                timeline_anchor_ids.append(normalized_anchor_id)
    relation_ids = [
        str(relation.get('relation_id') or '').strip()
        for relation in relations
        if str(relation.get('relation_id') or '').strip()
    ]
    issue_ids = [
        str(issue.get('issue_id') or issue.get('contradiction_id') or issue.get('dependency_id') or '').strip()
        for issue in issues
        if str(issue.get('issue_id') or issue.get('contradiction_id') or issue.get('dependency_id') or '').strip()
    ]

    matched_fact_ids = [
        str(fact_id).strip()
        for fact_id in (profile.get('matched_fact_ids', []) or [])
        if str(fact_id).strip()
    ]
    matched_relation_ids = [
        str(relation_id).strip()
        for relation_id in (profile.get('matched_relation_ids', []) or [])
        if str(relation_id).strip()
    ]
    temporal_consistency_summary = (
        context.get('consistency_summary', {})
        if isinstance(context.get('consistency_summary'), dict)
        else {}
    )
    missing_temporal_predicates = [
        str(predicate).strip()
        for predicate in (temporal_consistency_summary.get('missing_temporal_predicates', []) or [])
        if str(predicate).strip()
    ]
    required_provenance_kinds = [
        str(kind).strip()
        for kind in (temporal_consistency_summary.get('required_provenance_kinds', []) or [])
        if str(kind).strip()
    ]

    source_artifact_ids: List[str] = []
    testimony_record_ids: List[str] = []
    for fact in facts:
        for artifact_id in fact.get('source_artifact_ids', []) or []:
            normalized_artifact_id = str(artifact_id or '').strip()
            if normalized_artifact_id and normalized_artifact_id not in source_artifact_ids:
                source_artifact_ids.append(normalized_artifact_id)
        for testimony_record_id in fact.get('testimony_record_ids', []) or []:
            normalized_testimony_record_id = str(testimony_record_id or '').strip()
            if normalized_testimony_record_id and normalized_testimony_record_id not in testimony_record_ids:
                testimony_record_ids.append(normalized_testimony_record_id)

    relation_formula_map = {
        'before': 'Before',
        'after': 'After',
        'same_time': 'SameTime',
        'overlaps': 'Overlaps',
        'during': 'During',
        'meets': 'Meets',
    }
    tdfol_formulas: List[str] = []
    dcec_formulas: List[str] = []
    # T3: track certainty per formula so operators and downstream consumers can
    # distinguish facts asserted directly from the record ("certain") versus
    # ordering relations inferred from date comparisons ("inferred").
    tdfol_formula_certainties: Dict[str, str] = {}
    dcec_formula_certainties: Dict[str, str] = {}
    role = str(profile.get('element_role') or '').strip()

    for fact in facts:
        fact_id = str(fact.get('fact_id') or '').strip()
        if not fact_id:
            continue
        if 'protected_activity' in [self._normalize_reasoning_key(tag) for tag in (fact.get('element_tags', []) or [])]:
            formula = f'ProtectedActivity({fact_id})'
            if formula not in tdfol_formulas:
                tdfol_formulas.append(formula)
                tdfol_formula_certainties[formula] = 'certain'
        if 'adverse_action' in [self._normalize_reasoning_key(tag) for tag in (fact.get('element_tags', []) or [])]:
            formula = f'AdverseAction({fact_id})'
            if formula not in tdfol_formulas:
                tdfol_formulas.append(formula)
                tdfol_formula_certainties[formula] = 'certain'
        temporal_context = fact.get('temporal_context', {}) if isinstance(fact.get('temporal_context'), dict) else {}
        start_date = str(temporal_context.get('start_date') or '').strip()
        if start_date:
            time_symbol = f"t_{start_date.replace('-', '_')}"
            formula = f'Happens({fact_id},{time_symbol})'
            if formula not in dcec_formulas:
                dcec_formulas.append(formula)
                dcec_formula_certainties[formula] = 'certain'

    for relation in relations:
        source_fact_id = str(relation.get('source_fact_id') or '').strip()
        target_fact_id = str(relation.get('target_fact_id') or '').strip()
        relation_type = self._normalize_reasoning_key(relation.get('relation_type'))
        if not source_fact_id or not target_fact_id:
            continue
        relation_predicate = relation_formula_map.get(relation_type)
        if relation_predicate:
            formula = f'{relation_predicate}({source_fact_id},{target_fact_id})'
            if formula not in tdfol_formulas:
                tdfol_formulas.append(formula)
                # T3: inferred relations carry inference_mode "derived_from_date_anchors";
                # all other explicit or context-derived relations are treated as certain.
                inference_mode = str(relation.get('inference_mode') or '').strip()
                certainty = 'inferred' if inference_mode == 'derived_from_date_anchors' else 'certain'
                tdfol_formula_certainties[formula] = certainty

    proof_bundle_id = ':'.join(
        part
        for part in [
            self._normalize_reasoning_key(claim_type) or 'claim',
            self._normalize_reasoning_key(element.get('element_id') or element.get('element_text')) or 'element',
            self._normalize_reasoning_key(profile.get('profile_id')) or 'temporal_rule_profile',
        ]
        if part
    )
    theorem_export_metadata = {
        'contract_version': 'claim_support_temporal_handoff_v1',
        'claim_type': str(claim_type or ''),
        'claim_element_id': str(element.get('element_id') or ''),
        'proof_bundle_id': proof_bundle_id,
        'rule_frame_id': str(profile.get('rule_frame_id') or ''),
        'chronology_blocked': bool(issue_ids or profile.get('blocking_reasons')),
        'chronology_task_count': len([
            follow_up
            for follow_up in (profile.get('recommended_follow_ups', []) or [])
            if isinstance(follow_up, dict)
        ]) or len([
            str(reason).strip()
            for reason in (profile.get('blocking_reasons', []) or [])
            if str(reason).strip()
        ]) or len(issue_ids),
        'unresolved_temporal_issue_ids': list(issue_ids),
        'event_ids': list(fact_ids),
        'temporal_fact_ids': list(fact_ids),
        'temporal_relation_ids': list(relation_ids),
        'timeline_anchor_ids': list(timeline_anchor_ids),
        'timeline_issue_ids': list(issue_ids),
        'temporal_issue_ids': list(issue_ids),
        'missing_temporal_predicates': list(missing_temporal_predicates),
        'required_provenance_kinds': list(required_provenance_kinds),
        'temporal_proof_bundle_ids': [proof_bundle_id] if proof_bundle_id else [],
        'temporal_proof_objectives': [str(profile.get('rule_frame_id') or '').strip()] if str(profile.get('rule_frame_id') or '').strip() else [],
    }

    relation_predicate_map = {
        'Before': 'before',
        'After': 'after',
        'SameTime': 'same_time',
        'Overlaps': 'overlaps',
        'During': 'during',
        'Meets': 'meets',
    }
    missing_relations: List[Dict[str, Any]] = []
    for predicate in missing_temporal_predicates:
        match = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\(([^,()]+),([^,()]+)\)\s*$', predicate)
        if not match:
            continue
        predicate_name = match.group(1)
        relation_type = relation_predicate_map.get(predicate_name, self._normalize_reasoning_key(predicate_name))
        source_fact_id = match.group(2).strip()
        target_fact_id = match.group(3).strip()
        missing_relations.append({
            'predicate': predicate,
            'relation_type': relation_type,
            'source_fact_id': source_fact_id,
            'target_fact_id': target_fact_id,
        })

    normalized_fact_tags = {
        str(fact.get('fact_id') or '').strip(): {
            self._normalize_reasoning_key(tag)
            for tag in (fact.get('element_tags', []) or [])
            if str(tag or '').strip()
        }
        for fact in facts
        if isinstance(fact, dict) and str(fact.get('fact_id') or '').strip()
    }
    present_roles = set()
    for tags in normalized_fact_tags.values():
        if 'protected_activity' in tags or 'protectedactivity' in tags:
            present_roles.add('protected_activity')
        if 'adverse_action' in tags or 'adverseaction' in tags:
            present_roles.add('adverse_action')
    required_roles = []
    if self._normalize_reasoning_key(claim_type) in {'retaliation', 'employment_retaliation'} or 'retaliation' in self._normalize_reasoning_key(claim_type).split('_'):
        required_roles = ['protected_activity', 'adverse_action']
    missing_fact_roles = [
        role_name
        for role_name in required_roles
        if role_name not in present_roles
    ]

    blocking_explanations: List[Dict[str, Any]] = []
    for reason in [
        str(reason).strip()
        for reason in (profile.get('blocking_reasons', []) or [])
        if str(reason).strip()
    ]:
        blocking_explanations.append({
            'reason': reason,
            'rule_frame_id': str(profile.get('rule_frame_id') or ''),
            'profile_id': str(profile.get('profile_id') or ''),
            'affected_fact_ids': list(matched_fact_ids or fact_ids),
            'missing_fact_roles': list(missing_fact_roles),
            'missing_relations': list(missing_relations),
            'temporal_issue_ids': list(issue_ids),
            'missing_temporal_predicates': list(missing_temporal_predicates),
            'required_provenance_kinds': list(required_provenance_kinds),
        })
    if not blocking_explanations and (issue_ids or missing_temporal_predicates or missing_fact_roles):
        blocking_explanations.append({
            'reason': 'Temporal proof bundle has unresolved chronology inputs.',
            'rule_frame_id': str(profile.get('rule_frame_id') or ''),
            'profile_id': str(profile.get('profile_id') or ''),
            'affected_fact_ids': list(matched_fact_ids or fact_ids),
            'missing_fact_roles': list(missing_fact_roles),
            'missing_relations': list(missing_relations),
            'temporal_issue_ids': list(issue_ids),
            'missing_temporal_predicates': list(missing_temporal_predicates),
            'required_provenance_kinds': list(required_provenance_kinds),
        })

    temporal_next_actions = self._build_temporal_next_actions(
        claim_type=claim_type,
        element=element,
        temporal_context=context,
        temporal_rule_profile=profile,
        fact_ids=fact_ids,
        relation_ids=relation_ids,
        issue_ids=issue_ids,
        missing_temporal_predicates=missing_temporal_predicates,
        required_provenance_kinds=required_provenance_kinds,
        missing_fact_roles=missing_fact_roles,
        missing_relations=missing_relations,
    )

    proof_input_digest_payload = {
        'contract_version': 'claim_support_temporal_proof_bundle_v1',
        'proof_bundle_id': proof_bundle_id,
        'claim_type': str(claim_type or ''),
        'claim_element_id': str(element.get('element_id') or ''),
        'profile_id': str(profile.get('profile_id') or ''),
        'rule_frame_id': str(profile.get('rule_frame_id') or ''),
        'temporal_fact_ids': fact_ids,
        'temporal_relation_ids': relation_ids,
        'temporal_issue_ids': issue_ids,
        'tdfol_formulas': tdfol_formulas,
        'dcec_formulas': dcec_formulas,
        'theorem_export_metadata': theorem_export_metadata,
    }
    bundle_digest = hashlib.sha256(
        json.dumps(proof_input_digest_payload, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
    ).hexdigest()

    return {
        'contract_version': 'claim_support_temporal_proof_bundle_v1',
        'proof_bundle_id': proof_bundle_id,
        'persistence_key': proof_bundle_id,
        'bundle_digest': bundle_digest,
        'proof_input_digest': bundle_digest,
        'claim_type': str(claim_type or ''),
        'claim_element_id': str(element.get('element_id') or ''),
        'claim_element_text': str(element.get('element_text') or ''),
        'profile_id': str(profile.get('profile_id') or ''),
        'rule_frame_id': str(profile.get('rule_frame_id') or ''),
        'element_role': role,
        'status': str(profile.get('status') or ''),
        'available': bool(profile.get('available', False)),
        'matched_fact_ids': matched_fact_ids,
        'matched_relation_ids': matched_relation_ids,
        'temporal_fact_ids': fact_ids,
        'temporal_relation_ids': relation_ids,
        'timeline_anchor_ids': timeline_anchor_ids,
        'temporal_issue_ids': issue_ids,
        'source_artifact_ids': source_artifact_ids,
        'testimony_record_ids': testimony_record_ids,
        'missing_temporal_predicates': missing_temporal_predicates,
        'required_provenance_kinds': required_provenance_kinds,
        'missing_fact_roles': missing_fact_roles,
        'missing_relations': missing_relations,
        'blocking_explanations': blocking_explanations,
        'blocking_reasons': [
            str(reason).strip()
            for reason in (profile.get('blocking_reasons', []) or [])
            if str(reason).strip()
        ],
        'warnings': [
            str(warning).strip()
            for warning in (profile.get('warnings', []) or [])
            if str(warning).strip()
        ],
        'recommended_follow_ups': [
            follow_up
            for follow_up in (profile.get('recommended_follow_ups', []) or [])
            if isinstance(follow_up, dict)
        ],
        'temporal_next_actions': temporal_next_actions,
        'temporal_next_action_count': len(temporal_next_actions),
        'theorem_exports': {
            'tdfol_formulas': tdfol_formulas,
            'dcec_formulas': dcec_formulas,
            'tdfol_preview': tdfol_formulas[:3],
            'dcec_preview': dcec_formulas[:3],
            'tdfol_formula_count': len(tdfol_formulas),
            'dcec_formula_count': len(dcec_formulas),
            # T3: per-formula certainty maps so consumers can distinguish facts asserted
            # directly ("certain") from relations inferred from date anchors ("inferred").
            'tdfol_formula_certainties': {
                formula: tdfol_formula_certainties.get(formula, 'certain')
                for formula in tdfol_formulas
            },
            'dcec_formula_certainties': {
                formula: dcec_formula_certainties.get(formula, 'certain')
                for formula in dcec_formulas
            },
            'theorem_export_metadata': theorem_export_metadata,
            'proof_execution_source': 'temporal_proof_bundle',
            'proof_bundle_digest': bundle_digest,
        },
        'theorem_export_counts': {
            'tdfol_formula_count': len(tdfol_formulas),
            'dcec_formula_count': len(dcec_formulas),
        },
        'proof_execution_inputs': {
            'source': 'temporal_proof_bundle',
            'tdfol_formulas': tdfol_formulas,
            'dcec_formulas': dcec_formulas,
            'theorem_export_metadata': theorem_export_metadata,
            'proof_bundle_digest': bundle_digest,
        },
    }


def _get_temporal_reasoning_context(
    self,
    claim_type: str,
    element: Dict[str, Any],
) -> Dict[str, Any]:
    status_getter = getattr(self.mediator, 'get_three_phase_status', None)
    if not callable(status_getter):
        return {}

    try:
        status = status_getter()
    except Exception:
        return {}
    if not isinstance(status, dict):
        return {}

    canonical_fact_summary = status.get('canonical_fact_summary', {})
    proof_lead_summary = status.get('proof_lead_summary', {})
    temporal_fact_registry_summary = status.get('temporal_fact_registry_summary', {})
    temporal_relation_registry_summary = status.get('temporal_relation_registry_summary', {})
    timeline_relation_summary = status.get('timeline_relation_summary', {})
    timeline_consistency_summary = status.get('timeline_consistency_summary', {})
    temporal_issue_registry_summary = status.get('temporal_issue_registry_summary', {})
    intake_contradictions = status.get('intake_contradictions', {})

    canonical_facts = temporal_fact_registry_summary.get('facts', []) if isinstance(temporal_fact_registry_summary, dict) else []
    if not isinstance(canonical_facts, list) or not canonical_facts:
        canonical_facts = canonical_fact_summary.get('facts', []) if isinstance(canonical_fact_summary, dict) else []
    proof_leads = proof_lead_summary.get('proof_leads', []) if isinstance(proof_lead_summary, dict) else []
    timeline_relations = temporal_relation_registry_summary.get('relations', []) if isinstance(temporal_relation_registry_summary, dict) else []
    if not isinstance(timeline_relations, list) or not timeline_relations:
        timeline_relations = timeline_relation_summary.get('relations', []) if isinstance(timeline_relation_summary, dict) else []
    contradiction_candidates = temporal_issue_registry_summary.get('issues', []) if isinstance(temporal_issue_registry_summary, dict) else []
    if not isinstance(contradiction_candidates, list) or not contradiction_candidates:
        contradiction_candidates = intake_contradictions.get('candidates', []) if isinstance(intake_contradictions, dict) else []

    claim_key = self._normalize_reasoning_key(claim_type)
    element_keys = {
        self._normalize_reasoning_key(element.get('element_id')),
        self._normalize_reasoning_key(element.get('element_text')),
    }
    element_keys.discard('')

    claim_temporal_graphs = status.get('claim_temporal_graphs', {})

    def _graph_to_temporal_context(graph: Dict[str, Any]) -> Dict[str, Any]:
        graph_record = graph if isinstance(graph, dict) else {}
        if not graph_record:
            return {}
        facts = [fact for fact in (graph_record.get('facts', []) or []) if isinstance(fact, dict)]
        relations = [relation for relation in (graph_record.get('relations', []) or []) if isinstance(relation, dict)]
        issues = [issue for issue in (graph_record.get('issues', []) or []) if isinstance(issue, dict)]
        if not facts and not relations and not issues:
            return {}
        consistency_summary = {
            'event_count': int(graph_record.get('fact_count', len(facts)) or 0),
            'proof_lead_count': 0,
            'relation_count': int(graph_record.get('relation_count', len(relations)) or 0),
            'issue_count': int(graph_record.get('issue_count', len(issues)) or 0),
            'partial_order_ready': bool(graph_record.get('partial_order_ready', False)),
            'warnings': list(graph_record.get('warnings', []) or []),
            'warning_count': int(graph_record.get('warning_count', len(graph_record.get('warnings', []) or [])) or 0),
            'relation_type_counts': dict(graph_record.get('relation_type_counts', {}) or {}),
            'timeline_anchor_ids': list(graph_record.get('timeline_anchor_ids', []) or []),
            'missing_temporal_predicates': list(graph_record.get('missing_temporal_predicates', []) or []),
            'required_provenance_kinds': list(graph_record.get('required_provenance_kinds', []) or []),
            'graph_id': str(graph_record.get('graph_id') or ''),
            'trace_fact_ids': list(graph_record.get('fact_ids', []) or []),
            'trace_relation_ids': list(graph_record.get('relation_ids', []) or []),
            'trace_issue_ids': list(graph_record.get('issue_ids', []) or []),
        }
        return {
            'temporal_graph': graph_record,
            'temporal_facts': facts,
            'temporal_proof_leads': [],
            'temporal_relations': relations,
            'temporal_issues': issues,
            'consistency_summary': consistency_summary,
        }

    graph_claims = claim_temporal_graphs.get('claims', {}) if isinstance(claim_temporal_graphs.get('claims'), dict) else {}
    selected_graph: Dict[str, Any] = {}
    if graph_claims:
        selected_graph = graph_claims.get(claim_key, {}) if claim_key else {}
        if not selected_graph:
            for graph in graph_claims.values():
                if not isinstance(graph, dict):
                    continue
                if self._normalize_reasoning_key(graph.get('claim_type')) == claim_key:
                    selected_graph = graph
                    break
        if selected_graph and element_keys:
            element_graphs = selected_graph.get('elements', {}) if isinstance(selected_graph.get('elements'), dict) else {}
            selected_element_graph = {}
            for element_key in element_keys:
                if element_key in element_graphs:
                    selected_element_graph = element_graphs[element_key]
                    break
            if not selected_element_graph:
                for graph in element_graphs.values():
                    if not isinstance(graph, dict):
                        continue
                    graph_element_keys = {
                        self._normalize_reasoning_key(graph.get('element_id')),
                        self._normalize_reasoning_key(graph.get('element_label')),
                    }
                    graph_element_keys.discard('')
                    if graph_element_keys & element_keys:
                        selected_element_graph = graph
                        break
            if selected_element_graph:
                selected_graph = selected_element_graph
    graph_context = _graph_to_temporal_context(selected_graph)
    if graph_context:
        return graph_context

    def _extract_temporal_context(record: Dict[str, Any]) -> Dict[str, Any]:
        return record.get('temporal_context', {}) if isinstance(record.get('temporal_context'), dict) else {}

    def _has_temporal_context(record: Dict[str, Any]) -> bool:
        temporal_context = _extract_temporal_context(record)
        return bool(
            temporal_context.get('start_date')
            or temporal_context.get('end_date')
            or temporal_context.get('relative_markers')
        )

    def _matches_claim(record: Dict[str, Any]) -> bool:
        if not claim_key or not isinstance(record, dict):
            return False
        intent = record.get('intake_question_intent', {}) if isinstance(record.get('intake_question_intent'), dict) else {}
        values: List[Any] = []
        values.extend(record.get('claim_types', []) if isinstance(record.get('claim_types'), list) else [])
        values.append(record.get('claim_type'))
        values.append(intent.get('target_claim_type'))
        normalized_values = {
            self._normalize_reasoning_key(item)
            for item in values
            if str(item or '').strip()
        }
        return claim_key in normalized_values

    def _matches_element(record: Dict[str, Any], field_names: List[str]) -> bool:
        if not element_keys or not isinstance(record, dict):
            return False
        intent = record.get('intake_question_intent', {}) if isinstance(record.get('intake_question_intent'), dict) else {}
        values: List[Any] = []
        for field_name in field_names:
            field_value = record.get(field_name)
            if isinstance(field_value, list):
                values.extend(field_value)
            elif str(field_value or '').strip():
                values.append(field_value)
        values.append(intent.get('target_element_id'))
        normalized_values = {
            self._normalize_reasoning_key(item)
            for item in values
            if str(item or '').strip()
        }
        return bool(element_keys & normalized_values)

    def _is_temporal_issue(record: Dict[str, Any]) -> bool:
        category = self._normalize_reasoning_key(record.get('category') or record.get('issue_type'))
        return category.startswith('temporal') or category in {
            'missing_anchor',
            'relative_only_ordering',
            'contradictory_dates',
            'limitations_risk',
        }

    element_temporal_facts: List[Dict[str, Any]] = []
    claim_temporal_facts: List[Dict[str, Any]] = []
    claim_fact_map: Dict[str, Dict[str, Any]] = {}
    for fact in canonical_facts if isinstance(canonical_facts, list) else []:
        if not isinstance(fact, dict) or not _has_temporal_context(fact):
            continue
        fact_id = str(fact.get('fact_id') or '').strip()
        if fact_id:
            claim_fact_map[fact_id] = fact
        if _matches_element(fact, ['element_tags']):
            element_temporal_facts.append(fact)
        elif _matches_claim(fact):
            claim_temporal_facts.append(fact)

    selected_temporal_facts = element_temporal_facts or claim_temporal_facts
    selected_fact_ids = {
        str(fact.get('fact_id') or '').strip()
        for fact in selected_temporal_facts
        if isinstance(fact, dict) and str(fact.get('fact_id') or '').strip()
    }

    element_temporal_leads: List[Dict[str, Any]] = []
    claim_temporal_leads: List[Dict[str, Any]] = []
    for lead in proof_leads if isinstance(proof_leads, list) else []:
        if not isinstance(lead, dict) or not _has_temporal_context(lead):
            continue
        if _matches_element(lead, ['element_targets', 'fact_targets']):
            element_temporal_leads.append(lead)
        elif _matches_claim(lead):
            claim_temporal_leads.append(lead)

    selected_temporal_leads = element_temporal_leads or claim_temporal_leads
    for lead in selected_temporal_leads:
        for fact_id in lead.get('related_fact_ids', []) if isinstance(lead.get('related_fact_ids'), list) else []:
            normalized_fact_id = str(fact_id or '').strip()
            if normalized_fact_id:
                selected_fact_ids.add(normalized_fact_id)

    selected_temporal_relations: List[Dict[str, Any]] = []
    for relation in timeline_relations if isinstance(timeline_relations, list) else []:
        if not isinstance(relation, dict):
            continue
        source_fact_id = str(relation.get('source_fact_id') or '').strip()
        target_fact_id = str(relation.get('target_fact_id') or '').strip()
        if selected_fact_ids and (source_fact_id in selected_fact_ids or target_fact_id in selected_fact_ids):
            selected_temporal_relations.append(relation)
            if source_fact_id:
                selected_fact_ids.add(source_fact_id)
            if target_fact_id:
                selected_fact_ids.add(target_fact_id)

    if selected_fact_ids:
        selected_temporal_facts = [
            fact for fact in claim_fact_map.values()
            if str(fact.get('fact_id') or '').strip() in selected_fact_ids
        ]

    selected_fact_labels = {
        str(fact.get('text') or '').strip()
        for fact in selected_temporal_facts
        if isinstance(fact, dict) and str(fact.get('text') or '').strip()
    }
    selected_temporal_issues: List[Dict[str, Any]] = []
    for candidate in contradiction_candidates if isinstance(contradiction_candidates, list) else []:
        if not isinstance(candidate, dict):
            continue
        if not _is_temporal_issue(candidate):
            continue
        issue_fact_ids = {
            str(item or '').strip()
            for item in candidate.get('fact_ids', [])
            if str(item or '').strip()
        } if isinstance(candidate.get('fact_ids'), list) else set()
        node_names = {
            str(candidate.get('left_node_name') or '').strip(),
            str(candidate.get('right_node_name') or '').strip(),
        }
        if _matches_element(candidate, ['element_tags', 'affected_element_ids']):
            selected_temporal_issues.append(candidate)
            continue
        if _matches_claim(candidate):
            selected_temporal_issues.append(candidate)
            continue
        if selected_fact_ids and issue_fact_ids and (selected_fact_ids & issue_fact_ids):
            selected_temporal_issues.append(candidate)
            continue
        if selected_fact_labels and not (selected_fact_labels & node_names):
            continue
        selected_temporal_issues.append(candidate)

    if not selected_temporal_facts and not selected_temporal_leads and not selected_temporal_relations and not selected_temporal_issues:
        return {}

    relation_type_counts: Dict[str, int] = {}
    for relation in selected_temporal_relations:
        relation_type = str(relation.get('relation_type') or '').strip()
        if relation_type:
            relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1

    timeline_anchor_ids: List[str] = []
    for fact in selected_temporal_facts:
        if not isinstance(fact, dict):
            continue
        for anchor_id in fact.get('timeline_anchor_ids', []) or []:
            normalized_anchor_id = str(anchor_id or '').strip()
            if normalized_anchor_id and normalized_anchor_id not in timeline_anchor_ids:
                timeline_anchor_ids.append(normalized_anchor_id)

    relation_formula_map = {
        'before': 'Before',
        'after': 'After',
        'same_time': 'SameTime',
        'overlaps': 'Overlaps',
        'during': 'During',
        'meets': 'Meets',
    }
    derived_missing_temporal_predicates: List[str] = []
    for relation in selected_temporal_relations:
        if not isinstance(relation, dict):
            continue
        source_fact_id = str(relation.get('source_fact_id') or '').strip()
        target_fact_id = str(relation.get('target_fact_id') or '').strip()
        relation_type = relation_formula_map.get(self._normalize_reasoning_key(relation.get('relation_type')))
        if not source_fact_id or not target_fact_id or not relation_type:
            continue
        formula = f'{relation_type}({source_fact_id},{target_fact_id})'
        if formula not in derived_missing_temporal_predicates:
            derived_missing_temporal_predicates.append(formula)

    issue_level_missing_temporal_predicates: List[str] = []
    issue_level_required_provenance_kinds: List[str] = []
    for issue in selected_temporal_issues:
        if not isinstance(issue, dict):
            continue
        for predicate in (issue.get('missing_temporal_predicates') if isinstance(issue.get('missing_temporal_predicates'), list) else []):
            normalized_predicate = str(predicate).strip()
            if normalized_predicate and normalized_predicate not in issue_level_missing_temporal_predicates:
                issue_level_missing_temporal_predicates.append(normalized_predicate)
        for required_kind in (issue.get('required_provenance_kinds') if isinstance(issue.get('required_provenance_kinds'), list) else []):
            normalized_required_kind = str(required_kind).strip()
            if normalized_required_kind and normalized_required_kind not in issue_level_required_provenance_kinds:
                issue_level_required_provenance_kinds.append(normalized_required_kind)

    consistency_payload = timeline_consistency_summary if isinstance(timeline_consistency_summary, dict) else {}
    missing_temporal_predicates = [
        str(predicate).strip()
        for predicate in (consistency_payload.get('missing_temporal_predicates', []) or [])
        if str(predicate).strip()
    ]
    if not missing_temporal_predicates:
        missing_temporal_predicates = list(issue_level_missing_temporal_predicates or derived_missing_temporal_predicates)
    required_provenance_kinds = [
        str(kind).strip()
        for kind in (consistency_payload.get('required_provenance_kinds', []) or [])
        if str(kind).strip()
    ]
    if not required_provenance_kinds:
        required_provenance_kinds = list(issue_level_required_provenance_kinds)
    if not required_provenance_kinds:
        for issue in selected_temporal_issues:
            if str((issue or {}).get('recommended_resolution_lane') or '').strip().lower() == 'request_document':
                required_provenance_kinds.append('document_artifact')
                break
    consistency_summary = {
        'event_count': len(selected_temporal_facts),
        'proof_lead_count': len(selected_temporal_leads),
        'relation_count': len(selected_temporal_relations),
        'issue_count': len(selected_temporal_issues),
        'partial_order_ready': bool(consistency_payload.get('partial_order_ready', not selected_temporal_issues)),
        'warnings': list(consistency_payload.get('warnings', []) if isinstance(consistency_payload.get('warnings'), list) else []),
        'relation_type_counts': relation_type_counts,
        'timeline_anchor_ids': timeline_anchor_ids,
        'missing_temporal_predicates': missing_temporal_predicates,
        'required_provenance_kinds': required_provenance_kinds,
    }
    consistency_summary['warning_count'] = len(consistency_summary['warnings'])

    return {
        'temporal_facts': selected_temporal_facts,
        'temporal_proof_leads': selected_temporal_leads,
        'temporal_relations': selected_temporal_relations,
        'temporal_issues': selected_temporal_issues,
        'consistency_summary': consistency_summary,
    }


def _run_element_reasoning_diagnostics(
    self,
    claim_type: str,
    element: Dict[str, Any],
    contradiction_candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    support_texts = [
        str(trace.get('fact_text') or trace.get('support_label') or '')
        for trace in element.get('support_traces', []) or []
        if isinstance(trace, dict) and (trace.get('fact_text') or trace.get('support_label'))
    ]
    ontology_seed_text = '\n'.join(
        part for part in [
            f"Claim type: {claim_type}",
            f"Claim element: {element.get('element_text') or ''}",
            'Support facts:',
            *support_texts,
        ]
        if part
    )
    temporal_context = self._get_temporal_reasoning_context(claim_type, element)
    temporal_seed_lines: List[str] = []
    for fact in temporal_context.get('temporal_facts', []) or []:
        if not isinstance(fact, dict):
            continue
        temporal_details = fact.get('temporal_context', {}) if isinstance(fact.get('temporal_context'), dict) else {}
        temporal_seed_lines.append(
            f"Timeline fact: {fact.get('text') or fact.get('fact_id') or 'timeline_fact'} [{temporal_details.get('start_date') or '?'} -> {temporal_details.get('end_date') or '?'}]"
        )
    for relation in temporal_context.get('temporal_relations', []) or []:
        if not isinstance(relation, dict):
            continue
        temporal_seed_lines.append(
            f"Timeline relation: {relation.get('source_fact_id') or '?'} {relation.get('relation_type') or 'related_to'} {relation.get('target_fact_id') or '?'}"
        )
    consistency_summary = temporal_context.get('consistency_summary', {}) if isinstance(temporal_context.get('consistency_summary'), dict) else {}
    if consistency_summary:
        temporal_seed_lines.append(
            f"Timeline consistency: partial_order_ready={bool(consistency_summary.get('partial_order_ready', False))}, warnings={int(consistency_summary.get('warning_count', 0) or 0)}"
        )
    for issue in temporal_context.get('temporal_issues', []) or []:
        if not isinstance(issue, dict):
            continue
        temporal_seed_lines.append(
            f"Temporal issue: {issue.get('summary') or issue.get('label') or issue.get('category') or 'temporal_issue'}"
        )
    if temporal_seed_lines:
        ontology_seed_text = '\n'.join([ontology_seed_text, *temporal_seed_lines]) if ontology_seed_text else '\n'.join(temporal_seed_lines)

    predicates = self._build_reasoning_predicates(
        claim_type,
        element,
        contradiction_candidates,
        temporal_context=temporal_context,
    )
    ontology_build = build_ontology(ontology_seed_text)
    fallback_ontology = self._build_reasoning_ontology_fallback(
        claim_type,
        element,
        contradiction_candidates,
        temporal_context=temporal_context,
    )
    ontology_payload = ontology_build.get('ontology') if isinstance(ontology_build, dict) else None
    ontology_for_validation = ontology_payload if ontology_payload not in (None, '') else fallback_ontology
    temporal_rule_profile = evaluate_temporal_rule_profile(claim_type, element, temporal_context)
    temporal_proof_bundle = self._build_temporal_proof_bundle(
        claim_type,
        element,
        temporal_context,
        temporal_rule_profile,
    )
    claim_support_temporal_handoff = self._build_claim_support_temporal_handoff(
        claim_type,
        element,
        temporal_context,
        temporal_proof_bundle,
        temporal_rule_profile,
    )
    reasoning_payload = {
        'predicates': predicates,
        'claim_support_temporal_handoff': claim_support_temporal_handoff,
        'temporal_proof_bundle': temporal_proof_bundle,
        'proof_bundles': {
            temporal_proof_bundle.get('persistence_key') or temporal_proof_bundle.get('proof_bundle_id'): temporal_proof_bundle
        } if isinstance(temporal_proof_bundle, dict) and temporal_proof_bundle.get('proof_bundle_id') else {},
    }
    logic_proof = prove_claim_elements(reasoning_payload)
    logic_contradictions = check_contradictions(reasoning_payload)
    hybrid_reasoning = run_hybrid_reasoning(reasoning_payload)
    obligation_inputs = self._legal_ir_inputs_for_element(claim_type, element, contradiction_candidates)
    if obligation_inputs['sample_or_document'] is None and not obligation_inputs['canonical_receipt']:
        inventory = build_legal_ir_premise_inventory(
            asserted_facts=obligation_inputs['asserted_facts'],
            disputed_facts=obligation_inputs['disputed_facts'],
            selected_legal_rules=obligation_inputs['selected_legal_rules'],
            assumptions=obligation_inputs['assumptions'],
            missing_facts=obligation_inputs['missing_facts'],
            source_text=obligation_inputs['source_text'] or '',
            coverage_status=obligation_inputs['coverage_status'],
        )
        legal_ir_proof_obligations = {
            'schema_version': 'legal-ir-bound-proof-obligations/v1',
            'status': 'unavailable',
            'support': 'unsupported',
            'reason': 'Modal IR document was not supplied for this claim element.',
            'backend': {
                'identity': 'ipfs_datasets_py.logic.integration.reasoning.legal_ir_obligations.generate_legal_ir_proof_obligations',
                'available': False,
            },
            'trust_level': 'unavailable',
            'structural_only': True,
            'substantive_entailment': False,
            'entails_claim_element': False,
            'coverage_status_promoted_to_proof': False,
            'premise_inventory': inventory,
            'assumptions': [
                {'premise_id': item.get('premise_id'), 'label': item.get('label')}
                for item in inventory.get('assumptions') or []
            ],
            'obligations': [],
            'native_obligation_ids': [],
            'operational_trace': [{'code': 'modal_ir_absent', 'status': 'unavailable'}],
        }
    else:
        try:
            legal_ir_proof_obligations = generate_bound_legal_ir_proof_obligations(
                obligation_inputs['sample_or_document'],
                canonical_receipt=obligation_inputs['canonical_receipt'],
                max_obligations=obligation_inputs['max_obligations'],
                claim_id=obligation_inputs['claim_id'],
                element_id=obligation_inputs['element_id'],
                asserted_facts=obligation_inputs['asserted_facts'],
                disputed_facts=obligation_inputs['disputed_facts'],
                selected_legal_rules=obligation_inputs['selected_legal_rules'],
                assumptions=obligation_inputs['assumptions'],
                missing_facts=obligation_inputs['missing_facts'],
                legal_context_version=obligation_inputs['legal_context_version'],
                coverage_status=obligation_inputs['coverage_status'],
                source_text=obligation_inputs['source_text'],
                requirement_id=obligation_inputs.get('requirement_id') or '',
                definition_binding=obligation_inputs.get('definition_handoff'),
                adverse_treatment=obligation_inputs.get('adverse_treatment'),
            )
        except Exception as exc:
            legal_ir_proof_obligations = {
                'schema_version': 'legal-ir-bound-proof-obligations/v1',
                'status': 'unavailable',
                'support': 'unsupported',
                'reason': 'Legal IR proof obligation generator failed.',
                'trust_level': 'unavailable',
                'structural_only': True,
                'substantive_entailment': False,
                'entails_claim_element': False,
                'operational_trace': [{'code': type(exc).__name__, 'status': 'unavailable'}],
                'obligations': [],
            }
    obligation_rows = legal_ir_proof_obligations.get('obligations') if isinstance(legal_ir_proof_obligations, dict) else None
    first_obligation = obligation_rows[0] if isinstance(obligation_rows, list) and obligation_rows else None
    inventory = legal_ir_proof_obligations.get('premise_inventory') if isinstance(legal_ir_proof_obligations, dict) else None
    identity = ''
    versions = {}
    if isinstance(legal_ir_proof_obligations, dict):
        versions = legal_ir_proof_obligations.get('versions') if isinstance(legal_ir_proof_obligations.get('versions'), dict) else {}
        identity = str(versions.get('execution_identity') or '')
    issue_labels = []
    if isinstance(temporal_context, dict):
        for issue in temporal_context.get('temporal_issues') or []:
            if isinstance(issue, dict):
                issue_labels.append(issue.get('issue_type') or issue.get('category') or '')
    profile_warnings = list((temporal_rule_profile or {}).get('warnings') or []) if isinstance(temporal_rule_profile, dict) else []
    relative_only = any('relative-only' in str(warning) or 'relative_only' in str(warning) for warning in profile_warnings)
    selected_rules = []
    for rule in obligation_inputs.get('selected_legal_rules') or []:
        if not isinstance(rule, dict):
            continue
        selected_rules.append({
            **deepcopy(rule),
            'rule_id': rule.get('rule_id') or rule.get('premise_id') or '',
            'version': rule.get('version') or rule.get('authority_version') or '',
            'source_id': rule.get('source_id') or rule.get('citation') or '',
            'source_version': rule.get('source_version') or rule.get('authority_version') or '',
            'superseded': bool(rule.get('superseded') or str(rule.get('status') or '').lower() == 'superseded'),
            'law_as_of': rule.get('law_as_of') or rule.get('effective_date') or '',
        })
    cache_identity = proof_cache_identity(
        claim_id=obligation_inputs.get('claim_id') or claim_type,
        element_id=obligation_inputs.get('element_id') or '',
        factual_revisions=versions.get('fact_revisions') or [],
        legal_source={
            'source_id': str(element.get('legal_source_id') or ''),
            'source_version': str(element.get('legal_source_version') or obligation_inputs.get('legal_context_version') or ''),
            'legal_context_version': obligation_inputs.get('legal_context_version') or '',
            'law_as_of': str(element.get('law_as_of') or element.get('applicable_law_date') or ''),
            'rules': selected_rules,
            'premise_inventory': deepcopy(inventory) if isinstance(inventory, dict) else {},
            'sample_or_document': deepcopy(obligation_inputs.get('sample_or_document')),
            'canonical_receipt': deepcopy(obligation_inputs.get('canonical_receipt')),
            'requirement_id': str(versions.get('requirement_id') or obligation_inputs.get('requirement_id') or ''),
            'definition_identity': str(versions.get('definition_identity') or ''),
            'assumption_identity': str(versions.get('assumption_identity') or ''),
            'adverse_treatment_identity': str(versions.get('adverse_treatment_identity') or ''),
            'source_identity': str(versions.get('source_identity') or versions.get('document_sha256') or ''),
        },
        compiler={
            'execution_identity': identity,
            'formula_identity': versions.get('formula_identity') or '',
            'source_map_identity': versions.get('source_map_identity') or '',
            'obligation_version': str(first_obligation.get('schema_version') or '') if isinstance(first_obligation, dict) else str(getattr(first_obligation, 'schema_version', '') or ''),
            'premise_version': str((inventory or {}).get('digest') or '') if isinstance(inventory, dict) else '',
            'canonical': (obligation_inputs.get('canonical_receipt') or {}).get('identities') if isinstance(obligation_inputs.get('canonical_receipt'), dict) else {},
        },
        compiler_config={
            'max_obligations': obligation_inputs.get('max_obligations'),
            'checker_version': versions.get('checker_version') or '',
        },
        proof_policy={
            'required_trust': 'kernel',
            'total_timeout_seconds': 1.5,
            'stage_timeout_seconds': {
                'deterministic': 0.25,
                'native_logic': 0.25,
                'smt_atp': 0.25,
                'lean_reconstruction': 0.25,
            },
        },
        chronology={
            'contradictory_dates': bool((temporal_rule_profile or {}).get('has_contradictory_dates')) if isinstance(temporal_rule_profile, dict) else False,
            'relative_only': relative_only,
            'issues': issue_labels,
        },
    )

    def _route_provider():
        return route_bound_legal_ir_proof(
            first_obligation,
            premise_inventory=inventory if isinstance(inventory, dict) else None,
            sample_or_document=obligation_inputs['sample_or_document'],
            goal_statement=str(element.get('element_text') or ''),
            execution_identity=identity,
            expected_execution_identity=identity,
            obligation_version=cache_identity['components']['compiler']['identities']['obligation_version'],
            expected_obligation_version=cache_identity['components']['compiler']['identities']['obligation_version'],
            premise_version=cache_identity['components']['compiler']['identities']['premise_version'],
            expected_premise_version=cache_identity['components']['compiler']['identities']['premise_version'],
            total_timeout_seconds=1.5,
            stage_timeout_seconds={
                'deterministic': 0.25,
                'native_logic': 0.25,
                'smt_atp': 0.25,
                'lean_reconstruction': 0.25,
            },
            required_trust='kernel',
            requirement_id=str(versions.get('requirement_id') or ''),
            expected_requirement_id=str(versions.get('requirement_id') or ''),
            definition_identity=str(versions.get('definition_identity') or ''),
            expected_definition_identity=str(versions.get('definition_identity') or ''),
            assumption_identity=str(versions.get('assumption_identity') or ''),
            expected_assumption_identity=str(versions.get('assumption_identity') or ''),
            adverse_treatment_identity=str(versions.get('adverse_treatment_identity') or ''),
            expected_adverse_treatment_identity=str(versions.get('adverse_treatment_identity') or ''),
            source_identity=str(versions.get('source_identity') or versions.get('document_sha256') or ''),
            expected_source_identity=str(versions.get('source_identity') or versions.get('document_sha256') or ''),
        )

    try:
        proof_evaluation = replay_satisfied_element_proof(cache_identity, provider=_route_provider)
    except Exception as exc:
        proof_evaluation = {
            'cache_identity': cache_identity.get('cache_identity'),
            'satisfied': False,
            'status': 'unavailable',
            'reason': type(exc).__name__,
            'provider_called': False,
            'reused': False,
            'recommended_follow_ups': [],
            'result': {
                'schema_version': 'legal-ir-bound-proof-routing/v1',
                'outcome': 'unavailable',
                'reason': type(exc).__name__,
                'substantive_trust_satisfied': False,
                'entails_claim_element': False,
            },
        }
    routed_result = proof_evaluation.get('result') if isinstance(proof_evaluation.get('result'), dict) else None
    if routed_result is None:
        legal_ir_proof_routing = {
            'schema_version': 'legal-ir-bound-proof-routing/v1',
            'outcome': 'unknown' if proof_evaluation.get('status') == 'uncertain' else str(proof_evaluation.get('status') or 'unknown'),
            'reason': str(proof_evaluation.get('reason') or 'chronology_uncertain'),
            'substantive_trust_satisfied': False,
            'entails_claim_element': False,
            'provider_called': False,
        }
    else:
        legal_ir_proof_routing = dict(routed_result)
    legal_ir_proof_routing['proof_cache'] = {
        'cache_identity': proof_evaluation.get('cache_identity') or cache_identity.get('cache_identity'),
        'reused': bool(proof_evaluation.get('reused')),
        'provider_called': bool(proof_evaluation.get('provider_called')),
        'satisfied': bool(proof_evaluation.get('satisfied')),
        'status': proof_evaluation.get('status'),
        'reason': proof_evaluation.get('reason'),
        'recommended_follow_ups': list(proof_evaluation.get('recommended_follow_ups') or []),
    }
    if proof_evaluation.get('status') == 'uncertain':
        legal_ir_proof_routing['substantive_trust_satisfied'] = False
        legal_ir_proof_routing['entails_claim_element'] = False
        legal_ir_proof_routing['outcome'] = 'unknown'
    ontology_validation = validate_ontology(ontology_for_validation)
    ontology_workflow = build_validate_score_ontology(
        ontology_seed_text,
        claim_type=claim_type,
    )
    ontology_quality = (
        dict(ontology_workflow.get('ontology_quality', {}))
        if isinstance(ontology_workflow, dict) and isinstance(ontology_workflow.get('ontology_quality'), dict)
        else {}
    )
    if isinstance(ontology_workflow, dict) and isinstance(ontology_workflow.get('gaps'), dict):
        ontology_quality['gaps'] = list(ontology_workflow['gaps'].get('gaps') or [])

    temporal_summary: Dict[str, Any] = {}
    if temporal_context:
        temporal_consistency_summary = (
            temporal_context.get('consistency_summary', {})
            if isinstance(temporal_context.get('consistency_summary'), dict)
            else {}
        )
        temporal_relation_type_counts = dict(
            temporal_consistency_summary.get('relation_type_counts', {}) or {}
        )
        temporal_warnings = list(temporal_consistency_summary.get('warnings', []) or [])
        temporal_relation_preview = []
        for relation in temporal_context.get('temporal_relations', []) or []:
            if not isinstance(relation, dict):
                continue
            source_fact_id = str(relation.get('source_fact_id') or '').strip()
            target_fact_id = str(relation.get('target_fact_id') or '').strip()
            relation_type = str(relation.get('relation_type') or '').strip().replace('_', ' ')
            preview = ' '.join(part for part in [source_fact_id, relation_type, target_fact_id] if part).strip()
            if preview and preview not in temporal_relation_preview:
                temporal_relation_preview.append(preview)
            if len(temporal_relation_preview) >= 3:
                break
        temporal_summary = {
            'fact_count': len(temporal_context.get('temporal_facts', []) or []),
            'proof_lead_count': len(temporal_context.get('temporal_proof_leads', []) or []),
            'relation_count': len(temporal_context.get('temporal_relations', []) or []),
            'issue_count': len(temporal_context.get('temporal_issues', []) or []),
            'partial_order_ready': bool(
                temporal_consistency_summary.get('partial_order_ready', False)
            ),
            'warning_count': int(temporal_consistency_summary.get('warning_count', 0) or 0),
            'warnings': temporal_warnings,
            'relation_type_counts': temporal_relation_type_counts,
            'relation_preview': temporal_relation_preview,
        }

    adapter_statuses = {
        'ontology_build': self._summarize_adapter_result(
            ontology_build,
            count_fields=['ontology'],
        ),
        'logic_proof': self._summarize_adapter_result(
            logic_proof,
            count_fields=['predicate_count', 'provable_elements', 'unprovable_elements'],
        ),
        'logic_contradictions': self._summarize_adapter_result(
            logic_contradictions,
            count_fields=['predicate_count', 'contradictions'],
        ),
        'hybrid_reasoning': self._summarize_adapter_result(
            hybrid_reasoning,
            count_fields=['predicate_count', 'result', 'temporal_reasoning_payload'],
        ),
        'ontology_validation': self._summarize_adapter_result(
            ontology_validation,
            count_fields=['result'],
        ),
        'ontology_workflow': self._summarize_adapter_result(
            ontology_workflow,
            count_fields=['ontology', 'quality', 'gaps'],
        ),
    }

    return {
        'predicate_count': len(predicates),
        'ontology_entity_count': len(fallback_ontology.get('entities', []) or []),
        'ontology_relationship_count': len(fallback_ontology.get('relationships', []) or []),
        'used_fallback_ontology': ontology_payload in (None, ''),
        'adapter_statuses': adapter_statuses,
        'backend_available_count': len(
            [summary for summary in adapter_statuses.values() if summary.get('backend_available')]
        ),
        'ontology_build': ontology_build,
        'logic_proof': logic_proof,
        'logic_contradictions': logic_contradictions,
        'hybrid_reasoning': hybrid_reasoning,
        'ontology_validation': ontology_validation,
        'ontology_workflow': ontology_workflow,
        'graphrag_quality': ontology_quality,
        'temporal_summary': temporal_summary,
        'temporal_rule_profile': temporal_rule_profile,
        'temporal_proof_bundle': temporal_proof_bundle,
        'claim_support_temporal_handoff': claim_support_temporal_handoff,
        'legal_ir_proof_obligations': legal_ir_proof_obligations,
        'legal_ir_proof_routing': legal_ir_proof_routing,
        'legacy_proof_heuristic': {
            'proof_status': logic_proof.get('proof_status') if isinstance(logic_proof, dict) else '',
            'labels_supported_coverage_provable': True,
            'no_contradiction_scan_can_read_passed': True,
            'is_substantive_entailment': False,
        },
        'substantive_entailment': False,
    }
