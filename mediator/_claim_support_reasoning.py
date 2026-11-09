"""Pure payload helpers for claim-support reasoning diagnostics.

This module deliberately contains no mediator, database, or reasoning-backend
access.  Keeping the aggregation functions pure makes the payload contract easy
to exercise while :class:`ClaimSupportHook` retains orchestration ownership and
its existing private-method compatibility surface.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from lib.formal_logic import capability_state_from_payload


def extract_logic_contradiction_count(reasoning_diagnostics: Optional[Dict[str, Any]]) -> int:
    """Return explicit contradiction results emitted by the logic adapter."""

    reasoning = reasoning_diagnostics if isinstance(reasoning_diagnostics, dict) else {}
    logic_contradictions = reasoning.get('logic_contradictions', {})
    if not isinstance(logic_contradictions, dict):
        return 0
    contradictions = logic_contradictions.get('contradictions', [])
    if isinstance(contradictions, list):
        return len(contradictions)
    if contradictions:
        return 1
    summary = (reasoning.get('adapter_statuses') or {}).get('logic_contradictions', {})
    if isinstance(summary, dict):
        return int(summary.get('contradictions_count', 0) or 0)
    return 0


def extract_logic_proof_counts(reasoning_diagnostics: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """Normalize explicit provable and unprovable element collections."""

    reasoning = reasoning_diagnostics if isinstance(reasoning_diagnostics, dict) else {}
    logic_proof = reasoning.get('logic_proof', {})
    if not isinstance(logic_proof, dict):
        return {
            'provable_count': 0,
            'unprovable_count': 0,
        }
    provable_elements = logic_proof.get('provable_elements', [])
    unprovable_elements = logic_proof.get('unprovable_elements', [])
    return {
        'provable_count': len(provable_elements) if isinstance(provable_elements, list) else int(bool(provable_elements)),
        'unprovable_count': len(unprovable_elements) if isinstance(unprovable_elements, list) else int(bool(unprovable_elements)),
    }


def extract_ontology_validation_signal(reasoning_diagnostics: Optional[Dict[str, Any]]) -> str:
    """Return a semantic validation signal, excluding adapter execution errors.

    Backend failures do not establish that an ontology is invalid.  Only an
    explicit result, or a completed adapter status, can produce a semantic
    ``valid``/``invalid`` signal.
    """

    reasoning = reasoning_diagnostics if isinstance(reasoning_diagnostics, dict) else {}
    ontology_validation = reasoning.get('ontology_validation', {})
    if not isinstance(ontology_validation, dict):
        return 'unknown'
    result = ontology_validation.get('result')

    def _normalize_validation_value(value: Any) -> Optional[str]:
        if isinstance(value, bool):
            return 'valid' if value else 'invalid'
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {'valid', 'validated', 'consistent', 'passed', 'pass', 'success', 'ok'}:
                return 'valid'
            if lowered in {'invalid', 'inconsistent', 'failed', 'fail', 'error'}:
                return 'invalid'
            return None
        if isinstance(value, dict):
            for key in ('valid', 'is_valid', 'consistent', 'passed', 'success'):
                if key in value:
                    nested = _normalize_validation_value(value.get(key))
                    if nested:
                        return nested
            for key in ('status', 'result', 'state', 'validation_status'):
                if key in value:
                    nested = _normalize_validation_value(value.get(key))
                    if nested:
                        return nested
        return None

    normalized = _normalize_validation_value(result)
    if normalized:
        return normalized
    status = str(ontology_validation.get('status') or '').strip().lower()
    if status == 'success':
        return 'valid'
    return 'unknown'


def summarize_adapter_result(
    adapter_result: Dict[str, Any],
    count_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Normalize one reasoning adapter result without exposing backend details."""

    adapter_result = adapter_result if isinstance(adapter_result, dict) else {}
    metadata = adapter_result.get('metadata', {}) if isinstance(adapter_result.get('metadata'), dict) else {}
    capability = adapter_result.get('capability')
    if not isinstance(capability, dict):
        capability = metadata.get('capability') if isinstance(metadata.get('capability'), dict) else {}
    capability_state = capability_state_from_payload(capability or metadata or adapter_result)
    summary = {
        'status': str(adapter_result.get('status') or ''),
        'operation': str(metadata.get('operation') or ''),
        'implementation_status': str(metadata.get('implementation_status') or ''),
        'backend_available': bool(metadata.get('backend_available', False)),
        'degraded_reason': str(metadata.get('degraded_reason') or adapter_result.get('degraded_reason') or ''),
    }
    if capability_state is not None:
        summary.update({
            'capability_available': capability_state.available,
            'capability_degraded': capability_state.degraded,
            'capability_implemented': capability_state.implemented,
        })
    if capability:
        summary['capability'] = dict(capability)
    for field in count_fields or []:
        if field not in adapter_result:
            continue
        value = adapter_result.get(field)
        if isinstance(value, list):
            summary[f'{field}_count'] = len(value)
        elif isinstance(value, dict):
            summary[f'{field}_key_count'] = len(value)
        elif value is not None:
            summary[field] = value
    return summary


def summarize_claim_reasoning_diagnostics(elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate element-level reasoning diagnostics for a claim payload."""

    adapter_status_counts: Dict[str, Dict[str, int]] = {
        'ontology_build': {},
        'logic_proof': {},
        'logic_contradictions': {},
        'hybrid_reasoning': {},
        'ontology_validation': {},
    }
    backend_available_count = 0
    predicate_count = 0
    ontology_entity_count = 0
    ontology_relationship_count = 0
    fallback_ontology_count = 0
    hybrid_bridge_available_count = 0
    hybrid_tdfol_formula_count = 0
    hybrid_dcec_formula_count = 0
    temporal_fact_count = 0
    temporal_relation_count = 0
    temporal_issue_count = 0
    temporal_partial_order_ready_count = 0
    temporal_warning_count = 0
    temporal_rule_profile_available_count = 0
    temporal_rule_profile_satisfied_count = 0
    temporal_rule_profile_partial_count = 0
    temporal_rule_profile_failed_count = 0
    temporal_proof_bundle_count = 0

    for element in elements:
        if not isinstance(element, dict):
            continue
        reasoning = element.get('reasoning_diagnostics', {})
        if not isinstance(reasoning, dict):
            continue
        predicate_count += int(reasoning.get('predicate_count', 0) or 0)
        ontology_entity_count += int(reasoning.get('ontology_entity_count', 0) or 0)
        ontology_relationship_count += int(reasoning.get('ontology_relationship_count', 0) or 0)
        backend_available_count += int(reasoning.get('backend_available_count', 0) or 0)
        if reasoning.get('used_fallback_ontology'):
            fallback_ontology_count += 1
        hybrid_reasoning = reasoning.get('hybrid_reasoning', {})
        if isinstance(hybrid_reasoning, dict):
            hybrid_result = hybrid_reasoning.get('result', {}) if isinstance(hybrid_reasoning.get('result'), dict) else {}
            if bool(hybrid_result.get('compiler_bridge_available', False)):
                hybrid_bridge_available_count += 1
            hybrid_tdfol_formula_count += len(hybrid_result.get('tdfol_formulas', []) or [])
            hybrid_dcec_formula_count += len(hybrid_result.get('dcec_formulas', []) or [])
        temporal_summary = reasoning.get('temporal_summary', {})
        if isinstance(temporal_summary, dict):
            temporal_fact_count += int(temporal_summary.get('fact_count', 0) or 0)
            temporal_relation_count += int(temporal_summary.get('relation_count', 0) or 0)
            temporal_issue_count += int(temporal_summary.get('issue_count', 0) or 0)
            temporal_warning_count += int(temporal_summary.get('warning_count', 0) or 0)
            if bool(temporal_summary.get('partial_order_ready', False)):
                temporal_partial_order_ready_count += 1
        temporal_rule_profile = reasoning.get('temporal_rule_profile', {})
        if isinstance(temporal_rule_profile, dict) and bool(temporal_rule_profile.get('available', False)):
            temporal_rule_profile_available_count += 1
            temporal_rule_status = str(temporal_rule_profile.get('status') or '')
            if temporal_rule_status == 'satisfied':
                temporal_rule_profile_satisfied_count += 1
            elif temporal_rule_status == 'partial':
                temporal_rule_profile_partial_count += 1
            elif temporal_rule_status == 'failed':
                temporal_rule_profile_failed_count += 1
        temporal_proof_bundle = reasoning.get('temporal_proof_bundle', {})
        if isinstance(temporal_proof_bundle, dict) and temporal_proof_bundle:
            temporal_proof_bundle_count += 1
        for adapter_name, summary in (reasoning.get('adapter_statuses') or {}).items():
            if not isinstance(summary, dict):
                continue
            status = str(summary.get('implementation_status') or summary.get('status') or 'unknown')
            adapter_counts = adapter_status_counts.setdefault(adapter_name, {})
            adapter_counts[status] = adapter_counts.get(status, 0) + 1

    return {
        'adapter_status_counts': adapter_status_counts,
        'backend_available_count': backend_available_count,
        'predicate_count': predicate_count,
        'ontology_entity_count': ontology_entity_count,
        'ontology_relationship_count': ontology_relationship_count,
        'fallback_ontology_count': fallback_ontology_count,
        'hybrid_bridge_available_count': hybrid_bridge_available_count,
        'hybrid_tdfol_formula_count': hybrid_tdfol_formula_count,
        'hybrid_dcec_formula_count': hybrid_dcec_formula_count,
        'temporal_fact_count': temporal_fact_count,
        'temporal_relation_count': temporal_relation_count,
        'temporal_issue_count': temporal_issue_count,
        'temporal_partial_order_ready_count': temporal_partial_order_ready_count,
        'temporal_warning_count': temporal_warning_count,
        'temporal_rule_profile_available_count': temporal_rule_profile_available_count,
        'temporal_rule_profile_satisfied_count': temporal_rule_profile_satisfied_count,
        'temporal_rule_profile_partial_count': temporal_rule_profile_partial_count,
        'temporal_rule_profile_failed_count': temporal_rule_profile_failed_count,
        'temporal_proof_bundle_count': temporal_proof_bundle_count,
    }


def summarize_claim_validation_decisions(elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate the proof-decision trail without changing its wire shape."""

    decision_source_counts: Counter[str] = Counter()
    adapter_contradicted_element_count = 0
    fallback_ontology_element_count = 0
    proof_supported_element_count = 0
    logic_unprovable_element_count = 0
    ontology_invalid_element_count = 0
    temporal_rule_gap_element_count = 0

    for element in elements:
        if not isinstance(element, dict):
            continue
        trace = element.get('proof_decision_trace', {})
        if not isinstance(trace, dict):
            continue
        source = str(trace.get('decision_source') or 'unknown')
        decision_source_counts[source] += 1
        if int(trace.get('logic_contradiction_count', 0) or 0) > 0:
            adapter_contradicted_element_count += 1
        if bool(trace.get('used_fallback_ontology')):
            fallback_ontology_element_count += 1
        if source in {'logic_proof_supported', 'ontology_validation_supported'}:
            proof_supported_element_count += 1
        if source == 'logic_unprovable':
            logic_unprovable_element_count += 1
        if str(trace.get('ontology_validation_signal') or '') == 'invalid':
            ontology_invalid_element_count += 1
        if str(trace.get('temporal_rule_status') or '') in {'failed', 'partial'}:
            temporal_rule_gap_element_count += 1

    return {
        'decision_source_counts': dict(sorted(decision_source_counts.items())),
        'adapter_contradicted_element_count': adapter_contradicted_element_count,
        'fallback_ontology_element_count': fallback_ontology_element_count,
        'proof_supported_element_count': proof_supported_element_count,
        'logic_unprovable_element_count': logic_unprovable_element_count,
        'ontology_invalid_element_count': ontology_invalid_element_count,
        'temporal_rule_gap_element_count': temporal_rule_gap_element_count,
    }
