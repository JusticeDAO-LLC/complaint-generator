"""
Phase Manager

Manages the three-phase complaint process and transitions between phases.
"""

import logging
from enum import Enum
from typing import Dict, Any, Callable, List
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

_INTAKE_GAPS_THRESHOLD = 3
_EVIDENCE_GAP_RATIO_THRESHOLD = 0.3
_DENOISING_MAX_ITERATIONS = 20
_EVIDENCE_REVIEWABLE_ESCALATION_STATUSES = {
    'awaiting_complainant_record',
    'awaiting_third_party_record',
    'awaiting_testimony',
    'needs_manual_legal_review',
    'insufficient_support_after_search',
    'needs_manual_review',
}
_INTAKE_ESCALATED_CONTRADICTION_STATUSES = {
    'awaiting_complainant_record',
    'awaiting_third_party_record',
    'awaiting_testimony',
    'needs_manual_legal_review',
    'needs_manual_review',
    'manual_review_pending',
    'escalated',
}
_INTAKE_RESOLVED_CONTRADICTION_STATUSES = {
    'resolved',
    'closed',
    'dismissed',
    'superseded',
}
_EVIDENCE_RESOLVED_STATUSES = {
    'resolved',
    'resolved_supported',
    'closed',
    'dismissed',
    'superseded',
}


def _coerce_ratio(value: Any, default: float = 1.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            return default
    return default


def _utc_now_isoformat() -> str:
    return datetime.now(UTC).isoformat()


class ComplaintPhase(Enum):
    """The three phases of complaint processing."""
    INTAKE = "intake"  # Phase 1: Initial intake and denoising
    EVIDENCE = "evidence"  # Phase 2: Evidence gathering
    FORMALIZATION = "formalization"  # Phase 3: Neurosymbolic matching and formalization


class PhaseManager:
    """
    Manages complaint processing phases and transitions.
    
    Tracks which phase the complaint is in, completion criteria for each phase,
    and orchestrates transitions between phases.
    """

    _PHASE_ACTION_GETTERS = {
        ComplaintPhase.INTAKE: '_get_intake_action',
        ComplaintPhase.EVIDENCE: '_get_evidence_action',
        ComplaintPhase.FORMALIZATION: '_get_formalization_action',
    }

    _PHASE_COMPLETION_CHECKS = {
        ComplaintPhase.INTAKE: '_is_intake_complete',
        ComplaintPhase.EVIDENCE: '_is_evidence_complete',
        ComplaintPhase.FORMALIZATION: '_is_formalization_complete',
    }
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.current_phase = ComplaintPhase.INTAKE
        self.phase_history = []
        self.phase_data = {
            ComplaintPhase.INTAKE: {},
            ComplaintPhase.EVIDENCE: {},
            ComplaintPhase.FORMALIZATION: {}
        }
        self.iteration_count = 0
        self.loss_history = []  # Track loss/noise over iterations
        self._phase_action_getters: Dict[ComplaintPhase, Callable[[], Dict[str, Any]]] = {
            ComplaintPhase.INTAKE: self._get_intake_action,
            ComplaintPhase.EVIDENCE: self._get_evidence_action,
            ComplaintPhase.FORMALIZATION: self._get_formalization_action,
        }
        self._phase_completion_checks: Dict[ComplaintPhase, Callable[[], bool]] = {
            ComplaintPhase.INTAKE: self._is_intake_complete,
            ComplaintPhase.EVIDENCE: self._is_evidence_complete,
            ComplaintPhase.FORMALIZATION: self._is_formalization_complete,
        }

    def _extract_intake_gap_types(self, data: Dict[str, Any]) -> List[str]:
        """Collect normalized intake gap types from stored phase state."""
        gap_types: List[str] = []

        explicit_gap_types = data.get('intake_gap_types') or []
        for gap_type in explicit_gap_types:
            normalized = str(gap_type or '').strip()
            if normalized and normalized not in gap_types:
                gap_types.append(normalized)

        current_gaps = data.get('current_gaps') or []
        for gap in current_gaps:
            if not isinstance(gap, dict):
                continue
            normalized = str(gap.get('type') or '').strip()
            if normalized and normalized not in gap_types:
                gap_types.append(normalized)

        return gap_types

    def _extract_intake_contradictions(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Normalize stored intake contradiction diagnostics into a candidate list."""
        contradictions = data.get('intake_contradictions')
        if isinstance(contradictions, dict):
            candidates = contradictions.get('candidates')
            if isinstance(candidates, list):
                return [candidate for candidate in candidates if isinstance(candidate, dict)]
            if contradictions:
                return [contradictions]
            return []
        if isinstance(contradictions, list):
            return [candidate for candidate in contradictions if isinstance(candidate, dict)]
        return []

    def _active_intake_contradictions(self, contradiction_queue: Any) -> List[Dict[str, Any]]:
        if not isinstance(contradiction_queue, list):
            return []
        return [
            item for item in contradiction_queue
            if isinstance(item, dict)
            and not self._is_intake_contradiction_resolved(item)
        ]

    def _is_intake_contradiction_resolved(self, contradiction: Dict[str, Any]) -> bool:
        status_value = str(
            contradiction.get('current_resolution_status')
            or contradiction.get('status')
            or 'open'
        ).strip().lower()
        return status_value in _INTAKE_RESOLVED_CONTRADICTION_STATUSES

    def _is_intake_contradiction_resolved_or_escalated(self, contradiction: Dict[str, Any]) -> bool:
        status_value = str(
            contradiction.get('current_resolution_status')
            or contradiction.get('status')
            or 'open'
        ).strip().lower()
        return (
            status_value in _INTAKE_RESOLVED_CONTRADICTION_STATUSES
            or status_value in _INTAKE_ESCALATED_CONTRADICTION_STATUSES
        )

    def _extract_intake_case_file(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Return the structured intake case file when present."""
        intake_case_file = data.get('intake_case_file')
        if isinstance(intake_case_file, dict):
            return intake_case_file
        return {}

    def _collect_intake_section_blockers(self, intake_case_file: Dict[str, Any]) -> Dict[str, Any]:
        """Derive blockers and counters from structured intake sections."""
        sections = intake_case_file.get('intake_sections')
        if not isinstance(sections, dict):
            sections = {}

        normalized_sections: Dict[str, Dict[str, Any]] = {}
        blockers: List[str] = []

        section_to_blocker = {
            'chronology': 'missing_core_chronology',
            'actors': 'missing_core_actor',
            'conduct': 'missing_conduct_details',
            'harm': 'missing_harm',
            'remedy': 'missing_remedy',
            'proof_leads': 'missing_proof_leads',
            'claim_elements': 'missing_claim_element_facts',
        }
        for name, raw_section in sections.items():
            if not isinstance(raw_section, dict):
                continue
            status = str(raw_section.get('status') or 'missing').strip().lower() or 'missing'
            missing_items = raw_section.get('missing_items')
            normalized_sections[name] = {
                'status': status,
                'missing_items': list(missing_items) if isinstance(missing_items, list) else [],
            }
            if status == 'missing':
                blocker = section_to_blocker.get(name)
                if blocker and blocker not in blockers:
                    blockers.append(blocker)

        contradiction_queue = intake_case_file.get('contradiction_queue')
        active_contradictions = self._active_intake_contradictions(contradiction_queue)
        blocking_contradictions = [
            item for item in active_contradictions
            if isinstance(item, dict)
            and str(item.get('severity') or 'important').strip().lower() == 'blocking'
            and not self._is_intake_contradiction_resolved_or_escalated(item)
        ]
        escalated_blocking_contradictions = [
            item for item in active_contradictions
            if isinstance(item, dict)
            and str(item.get('severity') or 'important').strip().lower() == 'blocking'
            and self._is_intake_contradiction_resolved_or_escalated(item)
        ]
        if blocking_contradictions:
            blockers.append('blocking_contradiction')

        candidate_claims = intake_case_file.get('candidate_claims')
        if not isinstance(candidate_claims, list):
            candidate_claims = []
        canonical_facts = intake_case_file.get('canonical_facts')
        if not isinstance(canonical_facts, list):
            canonical_facts = []
        proof_leads = intake_case_file.get('proof_leads')
        if not isinstance(proof_leads, list):
            proof_leads = []
        summary_confirmation = intake_case_file.get('complainant_summary_confirmation')
        summary_confirmation = summary_confirmation if isinstance(summary_confirmation, dict) else {}
        summary_snapshots = intake_case_file.get('summary_snapshots')
        summary_snapshots = summary_snapshots if isinstance(summary_snapshots, list) else []
        complainant_summary_confirmed = bool(summary_confirmation.get('confirmed', False))
        if summary_snapshots and not complainant_summary_confirmed:
            blockers.append('complainant_summary_confirmation_required')

        criteria = {
            'candidate_claim_identified': bool(candidate_claims),
            'core_chronology_present': normalized_sections.get('chronology', {}).get('status') != 'missing',
            'core_actors_identified': normalized_sections.get('actors', {}).get('status') != 'missing',
            'conduct_described': normalized_sections.get('conduct', {}).get('status') != 'missing',
            'harm_captured': normalized_sections.get('harm', {}).get('status') != 'missing',
            'remedy_captured': normalized_sections.get('remedy', {}).get('status') != 'missing',
            'proof_leads_captured': normalized_sections.get('proof_leads', {}).get('status') != 'missing',
            'claim_elements_captured': normalized_sections.get('claim_elements', {}).get('status') != 'missing',
            'blocking_contradictions_resolved': not bool(blocking_contradictions),
            'blocking_contradictions_resolved_or_escalated': not bool(blocking_contradictions),
            'complainant_summary_confirmed': complainant_summary_confirmed or not bool(summary_snapshots),
        }

        coherence_required_sections = ('chronology', 'actors', 'conduct', 'harm')
        criteria['case_theory_coherent'] = bool(candidate_claims) and all(
            normalized_sections.get(section_name, {}).get('status') != 'missing'
            for section_name in coherence_required_sections
        )
        criteria['minimum_proof_path_present'] = bool(proof_leads)

        ambiguity_flags_present = False
        confidence_pairs: List[tuple[float, str]] = []
        for claim in candidate_claims:
            if not isinstance(claim, dict):
                continue
            ambiguity_flags = claim.get('ambiguity_flags')
            if isinstance(ambiguity_flags, list) and ambiguity_flags:
                ambiguity_flags_present = True
            try:
                confidence_value = float(claim.get('confidence', 0.0) or 0.0)
            except (TypeError, ValueError):
                confidence_value = 0.0
            confidence_pairs.append((confidence_value, str(claim.get('claim_type') or '')))
        confidence_pairs.sort(reverse=True)
        close_leading_claims = (
            len(confidence_pairs) > 1
            and confidence_pairs[0][0] >= 0.5
            and (confidence_pairs[0][0] - confidence_pairs[1][0]) < 0.15
        )
        criteria['claim_disambiguation_resolved'] = not ambiguity_flags_present and not close_leading_claims

        return {
            'sections': normalized_sections,
            'blockers': blockers,
            'criteria': criteria,
            'candidate_claim_count': len(candidate_claims),
            'canonical_fact_count': len(canonical_facts),
            'proof_lead_count': len(proof_leads),
            'blocking_contradictions': blocking_contradictions,
            'escalated_blocking_contradictions': escalated_blocking_contradictions,
            'active_contradictions': active_contradictions,
            'complainant_summary_confirmation': summary_confirmation,
        }

    def _build_intake_chronology_readiness(self, intake_case_file: Dict[str, Any]) -> Dict[str, Any]:
        event_ledger = intake_case_file.get('event_ledger') if isinstance(intake_case_file.get('event_ledger'), list) else []
        temporal_fact_registry = intake_case_file.get('temporal_fact_registry') if isinstance(intake_case_file.get('temporal_fact_registry'), list) else []
        temporal_issue_registry = intake_case_file.get('temporal_issue_registry') if isinstance(intake_case_file.get('temporal_issue_registry'), list) else []
        timeline_consistency_summary = intake_case_file.get('timeline_consistency_summary') if isinstance(intake_case_file.get('timeline_consistency_summary'), dict) else {}

        event_records = temporal_fact_registry if temporal_fact_registry else event_ledger
        event_count = len(event_records)
        anchored_event_count = 0
        for event in event_records:
            if not isinstance(event, dict):
                continue
            temporal_context = event.get('temporal_context') if isinstance(event.get('temporal_context'), dict) else {}
            anchor_ids = event.get('timeline_anchor_ids') if isinstance(event.get('timeline_anchor_ids'), list) else []
            if anchor_ids or str(temporal_context.get('start_date') or '').strip() or str(event.get('start_date') or '').strip():
                anchored_event_count += 1
        if event_count <= 0 and timeline_consistency_summary:
            event_count = int(timeline_consistency_summary.get('event_count', 0) or 0)
            missing_fact_ids = timeline_consistency_summary.get('missing_temporal_fact_ids') if isinstance(timeline_consistency_summary.get('missing_temporal_fact_ids'), list) else []
            relative_only_fact_ids = timeline_consistency_summary.get('relative_only_fact_ids') if isinstance(timeline_consistency_summary.get('relative_only_fact_ids'), list) else []
            anchored_event_count = max(0, event_count - len(missing_fact_ids) - len(relative_only_fact_ids))
        unanchored_event_count = max(0, event_count - anchored_event_count)

        issue_count = len(temporal_issue_registry)
        open_issue_count = 0
        blocking_issue_count = 0
        missing_temporal_predicates: List[str] = []
        required_provenance_kinds: List[str] = []
        for issue in temporal_issue_registry:
            if not isinstance(issue, dict):
                continue
            status_value = str(issue.get('current_resolution_status') or issue.get('status') or 'open').strip().lower()
            if status_value != 'resolved':
                open_issue_count += 1
            if bool(issue.get('blocking')) or str(issue.get('severity') or '').strip().lower() == 'blocking':
                blocking_issue_count += 1
            for predicate in issue.get('missing_temporal_predicates') or []:
                normalized_predicate = str(predicate or '').strip()
                if normalized_predicate and normalized_predicate not in missing_temporal_predicates:
                    missing_temporal_predicates.append(normalized_predicate)
            for provenance_kind in issue.get('required_provenance_kinds') or []:
                normalized_provenance_kind = str(provenance_kind or '').strip()
                if normalized_provenance_kind and normalized_provenance_kind not in required_provenance_kinds:
                    required_provenance_kinds.append(normalized_provenance_kind)

        has_chronology_source = bool(event_count or issue_count or timeline_consistency_summary)
        anchor_coverage_ratio = round((anchored_event_count / event_count), 3) if event_count > 0 else 1.0
        predicate_coverage_ratio = round(max(0.0, 1.0 - (len(missing_temporal_predicates) / max(issue_count, 1))), 3) if issue_count > 0 else 1.0
        provenance_coverage_ratio = round(max(0.0, 1.0 - (len(required_provenance_kinds) / max(issue_count, 1))), 3) if issue_count > 0 else 1.0
        ready_for_temporal_formalization = bool(
            has_chronology_source
            and blocking_issue_count == 0
            and open_issue_count == 0
            and unanchored_event_count == 0
            and not missing_temporal_predicates
            and not required_provenance_kinds
        )

        failure_reasons: List[str] = []
        if unanchored_event_count > 0:
            failure_reasons.append(f'{unanchored_event_count} chronology event(s) still lack anchors')
        if blocking_issue_count > 0:
            failure_reasons.append(f'{blocking_issue_count} blocking chronology issue(s) remain open')
        elif open_issue_count > 0:
            failure_reasons.append(f'{open_issue_count} chronology issue(s) remain unresolved')
        if missing_temporal_predicates:
            failure_reasons.append(f'missing temporal predicates: {", ".join(missing_temporal_predicates[:3])}')
        if required_provenance_kinds:
            failure_reasons.append(f'required chronology provenance: {", ".join(required_provenance_kinds[:3])}')

        return {
            'has_chronology_source': has_chronology_source,
            'anchor_coverage_ratio': anchor_coverage_ratio,
            'predicate_coverage_ratio': predicate_coverage_ratio,
            'provenance_coverage_ratio': provenance_coverage_ratio,
            'ready_for_temporal_formalization': ready_for_temporal_formalization,
            'unanchored_event_count': unanchored_event_count,
            'open_issue_count': open_issue_count,
            'blocking_issue_count': blocking_issue_count,
            'missing_temporal_predicates': missing_temporal_predicates,
            'required_provenance_kinds': required_provenance_kinds,
            'failure_reasons': failure_reasons,
        }

    def _build_intake_readiness(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Derive intake readiness metrics and blockers from intake state."""
        has_knowledge_graph = 'knowledge_graph' in data
        has_dependency_graph = 'dependency_graph' in data
        gaps_addressed = data.get('remaining_gaps', float('inf')) <= 3
        converged = data.get('denoising_converged', False)
        gap_types = self._extract_intake_gap_types(data)
        contradiction_candidates = self._extract_intake_contradictions(data)
        intake_case_file = self._extract_intake_case_file(data)
        structured_readiness = self._collect_intake_section_blockers(intake_case_file) if intake_case_file else None
        chronology_readiness = self._build_intake_chronology_readiness(intake_case_file) if intake_case_file else {}
        if not contradiction_candidates and structured_readiness:
            contradiction_candidates = list(structured_readiness.get('active_contradictions', []))
        contradiction_count = len(contradiction_candidates)
        has_contradictions = bool(data.get('contradictions_unresolved') or contradiction_count)

        criteria: Dict[str, bool] = {
            'knowledge_graph_ready': has_knowledge_graph,
            'dependency_graph_ready': has_dependency_graph,
            'gaps_within_threshold': gaps_addressed,
            'denoising_converged': converged,
        }
        if gap_types:
            criteria['timeline_captured'] = 'missing_timeline' not in gap_types
            criteria['responsible_party_identified'] = 'missing_responsible_party' not in gap_types
            criteria['impact_or_remedy_captured'] = 'missing_impact_remedy' not in gap_types
            criteria['proof_leads_present'] = 'unsupported_claim' not in gap_types
        if has_contradictions or 'contradictions_resolved' in data:
            criteria['contradictions_resolved'] = not has_contradictions
        if structured_readiness:
            criteria.update(structured_readiness['criteria'])
        if chronology_readiness.get('has_chronology_source'):
            criteria['chronology_anchor_coverage_complete'] = chronology_readiness.get('unanchored_event_count', 0) == 0
            criteria['chronology_predicate_coverage_complete'] = not bool(chronology_readiness.get('missing_temporal_predicates'))
            criteria['chronology_provenance_coverage_complete'] = not bool(chronology_readiness.get('required_provenance_kinds'))
            criteria['chronology_ready_for_formalization'] = bool(chronology_readiness.get('ready_for_temporal_formalization', False))

        blockers: List[str] = []
        if not has_knowledge_graph:
            blockers.append('missing_knowledge_graph')
        if not has_dependency_graph:
            blockers.append('missing_dependency_graph')
        if not gaps_addressed:
            blockers.append('unresolved_gaps')
        if not converged:
            blockers.append('denoising_not_converged')
        if 'missing_timeline' in gap_types:
            blockers.append('missing_timeline')
        if 'missing_responsible_party' in gap_types:
            blockers.append('missing_actor')
        if 'missing_impact_remedy' in gap_types:
            blockers.append('missing_impact_or_remedy')
        if 'unsupported_claim' in gap_types:
            blockers.append('missing_proof_leads')
        if has_contradictions:
            blockers.append('contradiction_unresolved')
        if structured_readiness:
            for blocker in structured_readiness['blockers']:
                if blocker not in blockers:
                    blockers.append(blocker)
            if not structured_readiness['criteria'].get('case_theory_coherent', False):
                blockers.append('case_theory_incomplete')
            if not structured_readiness['criteria'].get('minimum_proof_path_present', False):
                blockers.append('missing_minimum_proof_path')
            if not structured_readiness['criteria'].get('claim_disambiguation_resolved', True):
                blockers.append('claim_disambiguation_required')
        if chronology_readiness.get('has_chronology_source'):
            if chronology_readiness.get('unanchored_event_count', 0) > 0:
                blockers.append('chronology_anchor_coverage_incomplete')
            if chronology_readiness.get('missing_temporal_predicates'):
                blockers.append('chronology_predicate_coverage_incomplete')
            if chronology_readiness.get('required_provenance_kinds'):
                blockers.append('chronology_provenance_coverage_incomplete')
            if chronology_readiness.get('open_issue_count', 0) > 0:
                blockers.append('chronology_open_issues')

        for blocker in data.get('intake_blockers', []) or []:
            normalized = str(blocker or '').strip()
            if normalized and normalized not in blockers:
                blockers.append(normalized)

        total_criteria = len(criteria)
        satisfied_criteria = sum(1 for satisfied in criteria.values() if satisfied)
        readiness_score = round(satisfied_criteria / total_criteria, 3) if total_criteria else 0.0

        return {
            'intake_readiness_score': readiness_score,
            'intake_readiness_blockers': blockers,
            'intake_readiness_criteria': criteria,
            'intake_ready': len(blockers) == 0,
            'ready_to_advance': len(blockers) == 0,
            'remaining_gap_count': int(data.get('remaining_gaps', 0) or 0),
            'intake_contradiction_count': contradiction_count,
            'intake_contradictions': contradiction_candidates,
            'intake_sections': structured_readiness['sections'] if structured_readiness else {},
            'candidate_claim_count': structured_readiness['candidate_claim_count'] if structured_readiness else 0,
            'canonical_fact_count': structured_readiness['canonical_fact_count'] if structured_readiness else 0,
            'proof_lead_count': structured_readiness['proof_lead_count'] if structured_readiness else 0,
            'blocking_contradictions': structured_readiness['blocking_contradictions'] if structured_readiness else [],
            'escalated_blocking_contradictions': structured_readiness['escalated_blocking_contradictions'] if structured_readiness else [],
            'complainant_summary_confirmation': structured_readiness['complainant_summary_confirmation'] if structured_readiness else {},
            'intake_chronology_readiness': chronology_readiness if chronology_readiness.get('has_chronology_source') else {},
            'intake_chronology_failure_reasons': list(chronology_readiness.get('failure_reasons') or []),
        }

    def _refresh_phase_derived_state(self, phase: ComplaintPhase):
        """Refresh derived readiness state after phase data changes."""
        if phase == ComplaintPhase.INTAKE:
            self.phase_data[phase].update(self._build_intake_readiness(self.phase_data[phase]))
        elif phase == ComplaintPhase.EVIDENCE:
            self.phase_data[phase].update(self._build_evidence_packet_summary(self.phase_data[phase]))

    def get_intake_readiness(self) -> Dict[str, Any]:
        """Return derived intake readiness state."""
        self._refresh_phase_derived_state(ComplaintPhase.INTAKE)
        data = self.phase_data[ComplaintPhase.INTAKE]
        return {
            'score': data.get('intake_readiness_score', 0.0),
            'blockers': list(data.get('intake_readiness_blockers', [])),
            'criteria': dict(data.get('intake_readiness_criteria', {})),
            'ready': bool(data.get('intake_ready', False)),
            'ready_to_advance': bool(data.get('ready_to_advance', data.get('intake_ready', False))),
            'remaining_gap_count': int(data.get('remaining_gap_count', data.get('remaining_gaps', 0)) or 0),
            'contradiction_count': int(data.get('intake_contradiction_count', 0) or 0),
            'contradictions': list(data.get('intake_contradictions', [])),
            'intake_sections': dict(data.get('intake_sections', {})),
            'candidate_claim_count': int(data.get('candidate_claim_count', 0) or 0),
            'canonical_fact_count': int(data.get('canonical_fact_count', 0) or 0),
            'proof_lead_count': int(data.get('proof_lead_count', 0) or 0),
            'blocking_contradictions': list(data.get('blocking_contradictions', [])),
            'escalated_blocking_contradictions': list(data.get('escalated_blocking_contradictions', [])),
            'complainant_summary_confirmation': dict(data.get('complainant_summary_confirmation', {})),
        }

    def _build_evidence_packet_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Derive evidence coverage metrics from claim-support packets when present."""
        packets = data.get('claim_support_packets')
        if not isinstance(packets, dict):
            packets = {}

        alignment_tasks = data.get('alignment_evidence_tasks')
        task_resolution_by_element: Dict[tuple[str, str], str] = {}
        temporal_gap_task_count = 0
        temporal_gap_targeted_task_count = 0
        temporal_rule_status_counts: Dict[str, int] = {}
        temporal_rule_blocking_reason_counts: Dict[str, int] = {}
        temporal_resolution_status_counts: Dict[str, int] = {}
        temporal_missing_anchor_task_count = 0
        temporal_missing_predicate_count = 0
        temporal_required_provenance_kind_count = 0
        chronology_anchor_coverage_ratio = 1.0
        chronology_predicate_coverage_ratio = 1.0
        chronology_provenance_coverage_ratio = 1.0
        chronology_ready_for_formalization = True
        chronology_snapshot_present = False
        for task in alignment_tasks if isinstance(alignment_tasks, list) else []:
            if not isinstance(task, dict):
                continue
            claim_type = str(task.get('claim_type') or '').strip().lower()
            element_id = str(task.get('claim_element_id') or '').strip().lower()
            if not claim_type or not element_id:
                continue
            task_resolution_by_element[(claim_type, element_id)] = self._normalize_evidence_escalation_status(
                task.get('resolution_status')
            )
            is_temporal_task = bool(
                str(task.get('action') or '').strip().lower() == 'fill_temporal_chronology_gap'
                or str(task.get('temporal_rule_profile_id') or '').strip()
                or str(task.get('temporal_rule_status') or '').strip()
                or list(task.get('temporal_rule_blocking_reasons', []) or [])
                or list(task.get('temporal_rule_follow_ups', []) or [])
            )
            if not is_temporal_task:
                continue
            temporal_gap_task_count += 1
            temporal_rule_status = str(task.get('temporal_rule_status') or '').strip().lower()
            if temporal_rule_status in {'partial', 'failed'}:
                temporal_gap_targeted_task_count += 1
            if temporal_rule_status:
                temporal_rule_status_counts[temporal_rule_status] = (
                    temporal_rule_status_counts.get(temporal_rule_status, 0) + 1
                )
            for reason in (task.get('temporal_rule_blocking_reasons') or []):
                normalized_reason = str(reason or '').strip()
                if not normalized_reason:
                    continue
                temporal_rule_blocking_reason_counts[normalized_reason] = (
                    temporal_rule_blocking_reason_counts.get(normalized_reason, 0) + 1
                )
            resolution_status = self._normalize_evidence_escalation_status(task.get('resolution_status'))
            if resolution_status:
                temporal_resolution_status_counts[resolution_status] = (
                    temporal_resolution_status_counts.get(resolution_status, 0) + 1
                )
            intake_chronology_readiness = task.get('intake_chronology_readiness') if isinstance(task.get('intake_chronology_readiness'), dict) else {}
            if intake_chronology_readiness:
                chronology_snapshot_present = True
                chronology_anchor_coverage_ratio = min(
                    chronology_anchor_coverage_ratio,
                    _coerce_ratio(intake_chronology_readiness.get('anchor_coverage_ratio'), 1.0),
                )
                chronology_predicate_coverage_ratio = min(
                    chronology_predicate_coverage_ratio,
                    _coerce_ratio(intake_chronology_readiness.get('predicate_coverage_ratio'), 1.0),
                )
                chronology_provenance_coverage_ratio = min(
                    chronology_provenance_coverage_ratio,
                    _coerce_ratio(intake_chronology_readiness.get('provenance_coverage_ratio'), 1.0),
                )
                chronology_ready_for_formalization = bool(
                    chronology_ready_for_formalization
                    and intake_chronology_readiness.get('ready_for_temporal_formalization', False)
                )
            support_status = str(task.get('support_status') or '').strip().lower()
            if (
                resolution_status not in _EVIDENCE_RESOLVED_STATUSES
                and support_status in {'unsupported', 'partially_supported', 'contradicted'}
            ):
                anchor_ids = self._normalize_temporal_task_values(
                    task.get('anchor_ids') or task.get('timeline_anchor_ids')
                )
                if not anchor_ids:
                    temporal_missing_anchor_task_count += 1
                temporal_missing_predicate_count += len(
                    self._normalize_temporal_task_values(task.get('missing_temporal_predicates'))
                )
                temporal_required_provenance_kind_count += len(
                    self._normalize_temporal_task_values(task.get('required_provenance_kinds'))
                )

        total_claims = 0
        total_elements = 0
        explicit_status_elements = 0
        unsupported_elements = 0
        supported_elements = 0
        partially_supported_elements = 0
        blocking_contradictions = 0
        next_steps: List[str] = []
        high_quality_ready_elements = 0
        reviewable_escalation_count = 0
        unresolved_without_review_path_count = 0

        for claim_key, claim_packet in packets.items():
            if not isinstance(claim_packet, dict):
                continue
            total_claims += 1
            claim_type = str(claim_packet.get('claim_type') or claim_key or '').strip().lower()
            elements = claim_packet.get('elements')
            if not isinstance(elements, list):
                continue
            for element in elements:
                if not isinstance(element, dict):
                    continue
                total_elements += 1
                status = str(element.get('support_status') or '').strip().lower()
                if status in {'supported', 'partially_supported', 'unsupported', 'contradicted'}:
                    explicit_status_elements += 1
                if status == 'supported':
                    supported_elements += 1
                elif status == 'partially_supported':
                    partially_supported_elements += 1
                if status == 'unsupported':
                    unsupported_elements += 1
                contradiction_count = int(element.get('contradiction_count', 0) or 0)
                if contradiction_count > 0 and status == 'contradicted':
                    blocking_contradictions += contradiction_count
                parse_quality_flags = element.get('parse_quality_flags', [])
                if status == 'supported' and not (parse_quality_flags if isinstance(parse_quality_flags, list) else []):
                    high_quality_ready_elements += 1
                element_id = str(element.get('element_id') or '').strip().lower()
                task_resolution_status = task_resolution_by_element.get((claim_type, element_id), '')
                escalation_status = self._resolve_evidence_escalation_status(element, task_resolution_status)
                if status in {'unsupported', 'partially_supported', 'contradicted'}:
                    if escalation_status in _EVIDENCE_REVIEWABLE_ESCALATION_STATUSES:
                        reviewable_escalation_count += 1
                    elif status != 'contradicted':
                        unresolved_without_review_path_count += 1
                next_step = str(element.get('recommended_next_step') or '').strip()
                if next_step and next_step not in next_steps:
                    next_steps.append(next_step)

        credible_support_ratio = 0.0
        draft_ready_element_ratio = 0.0
        high_quality_parse_ratio = 0.0
        supported_blocking_element_ratio = 0.0
        reviewable_escalation_ratio = 0.0
        if total_elements > 0:
            credible_support_ratio = round((supported_elements + partially_supported_elements) / total_elements, 3)
            draft_ready_element_ratio = round(supported_elements / total_elements, 3)
            high_quality_parse_ratio = round(high_quality_ready_elements / total_elements, 3)
            supported_blocking_element_ratio = round((supported_elements + reviewable_escalation_count) / total_elements, 3)
            reviewable_escalation_ratio = round(reviewable_escalation_count / total_elements, 3)
        contradiction_penalty = 0.15 if blocking_contradictions > 0 else 0.0
        unresolved_temporal_issue_ids = self._build_unresolved_temporal_issue_ids(data)
        unresolved_temporal_issue_count = len(unresolved_temporal_issue_ids)
        chronology_penalty = min(
            0.2,
            (unresolved_temporal_issue_count * 0.03)
            + (temporal_gap_task_count * 0.02)
            + (temporal_missing_anchor_task_count * 0.02)
            + (temporal_missing_predicate_count * 0.015)
            + (temporal_required_provenance_kind_count * 0.005),
        )
        chronology_coverage_penalty = 0.0
        if chronology_snapshot_present:
            chronology_coverage_penalty = min(
                0.2,
                ((1.0 - chronology_anchor_coverage_ratio) * 0.06)
                + ((1.0 - chronology_predicate_coverage_ratio) * 0.05)
                + ((1.0 - chronology_provenance_coverage_ratio) * 0.04),
            )
        proof_readiness_score = round(
            max(
                0.0,
                min(
                    1.0,
                    (credible_support_ratio * 0.45)
                    + (draft_ready_element_ratio * 0.4)
                    + (high_quality_parse_ratio * 0.15)
                    - contradiction_penalty
                    - chronology_penalty
                    - chronology_coverage_penalty,
                ),
            ),
            3,
        )
        chronology_failure_reasons: List[str] = []
        if unresolved_temporal_issue_count > 0:
            chronology_failure_reasons.append(f'{unresolved_temporal_issue_count} unresolved chronology issue id(s) remain')
        if temporal_missing_anchor_task_count > 0:
            chronology_failure_reasons.append(f'{temporal_missing_anchor_task_count} chronology task(s) still need anchors')
        if temporal_missing_predicate_count > 0:
            chronology_failure_reasons.append(f'{temporal_missing_predicate_count} required temporal predicate(s) remain missing')
        if temporal_required_provenance_kind_count > 0:
            chronology_failure_reasons.append(f'{temporal_required_provenance_kind_count} chronology provenance requirement(s) remain open')
        if chronology_snapshot_present and chronology_anchor_coverage_ratio < 1.0:
            chronology_failure_reasons.append(f'anchor coverage ratio remains {chronology_anchor_coverage_ratio:.2f}')
        if chronology_snapshot_present and chronology_predicate_coverage_ratio < 1.0:
            chronology_failure_reasons.append(f'predicate coverage ratio remains {chronology_predicate_coverage_ratio:.2f}')
        if chronology_snapshot_present and chronology_provenance_coverage_ratio < 1.0:
            chronology_failure_reasons.append(f'provenance coverage ratio remains {chronology_provenance_coverage_ratio:.2f}')
        chronology_readiness_score = round(
            max(0.0, min(1.0, (chronology_anchor_coverage_ratio + chronology_predicate_coverage_ratio + chronology_provenance_coverage_ratio) / 3.0)),
            3,
        )
        evidence_completion_ready = (
            total_elements > 0
            and explicit_status_elements == total_elements
            and blocking_contradictions == 0
            and unresolved_without_review_path_count == 0
            and not unresolved_temporal_issue_ids
            and temporal_missing_anchor_task_count == 0
            and temporal_missing_predicate_count == 0
            and temporal_required_provenance_kind_count == 0
            and chronology_ready_for_formalization
        )

        return {
            'claim_support_packet_count': total_claims,
            'claim_support_element_count': total_elements,
            'claim_support_explicit_status_count': explicit_status_elements,
            'claim_support_unsupported_count': unsupported_elements,
            'claim_support_blocking_contradictions': blocking_contradictions,
            'claim_support_recommended_actions': next_steps,
            'supported_blocking_element_ratio': supported_blocking_element_ratio,
            'credible_support_ratio': credible_support_ratio,
            'draft_ready_element_ratio': draft_ready_element_ratio,
            'high_quality_parse_ratio': high_quality_parse_ratio,
            'reviewable_escalation_ratio': reviewable_escalation_ratio,
            'claim_support_reviewable_escalation_count': reviewable_escalation_count,
            'claim_support_unresolved_without_review_path_count': unresolved_without_review_path_count,
            'claim_support_unresolved_temporal_issue_count': unresolved_temporal_issue_count,
            'claim_support_unresolved_temporal_issue_ids': unresolved_temporal_issue_ids,
            'temporal_gap_task_count': temporal_gap_task_count,
            'temporal_gap_targeted_task_count': temporal_gap_targeted_task_count,
            'temporal_missing_anchor_task_count': temporal_missing_anchor_task_count,
            'temporal_missing_predicate_count': temporal_missing_predicate_count,
            'temporal_required_provenance_kind_count': temporal_required_provenance_kind_count,
            'temporal_rule_status_counts': temporal_rule_status_counts,
            'temporal_rule_blocking_reason_counts': temporal_rule_blocking_reason_counts,
            'temporal_resolution_status_counts': temporal_resolution_status_counts,
            'chronology_anchor_coverage_ratio': round(chronology_anchor_coverage_ratio, 3),
            'chronology_predicate_coverage_ratio': round(chronology_predicate_coverage_ratio, 3),
            'chronology_provenance_coverage_ratio': round(chronology_provenance_coverage_ratio, 3),
            'chronology_readiness_score': chronology_readiness_score,
            'chronology_ready_for_formalization': chronology_ready_for_formalization and not chronology_failure_reasons,
            'chronology_failure_reasons': chronology_failure_reasons,
            'proof_readiness_score': proof_readiness_score,
            'evidence_completion_ready': evidence_completion_ready,
        }

    def _normalize_temporal_task_values(self, values: Any) -> List[str]:
        normalized_values: List[str] = []
        for value in values if isinstance(values, list) else []:
            normalized = str(value or '').strip()
            if normalized and normalized not in normalized_values:
                normalized_values.append(normalized)
        return normalized_values

    def _normalize_evidence_escalation_status(self, value: Any) -> str:
        return str(value or '').strip().lower()

    def _resolve_evidence_escalation_status(self, element: Dict[str, Any], task_resolution_status: str = '') -> str:
        for candidate in (
            element.get('escalation_status'),
            element.get('resolution_status'),
            task_resolution_status,
            element.get('recommended_next_step'),
        ):
            normalized = self._normalize_evidence_escalation_status(candidate)
            if normalized:
                return normalized
        return ''

    def _extract_temporal_issue_ids(self, candidate: Any) -> List[str]:
        if not isinstance(candidate, dict):
            return []

        issue_ids: List[str] = []

        def _append_issue_ids(values: Any):
            for value in values if isinstance(values, list) else []:
                normalized = str(value or '').strip()
                if normalized and normalized not in issue_ids:
                    issue_ids.append(normalized)

        _append_issue_ids(candidate.get('temporal_issue_ids'))
        _append_issue_ids(candidate.get('timeline_issue_ids'))

        temporal_proof_bundle = candidate.get('temporal_proof_bundle')
        if isinstance(temporal_proof_bundle, dict):
            _append_issue_ids(temporal_proof_bundle.get('temporal_issue_ids'))

        reasoning_diagnostics = candidate.get('reasoning_diagnostics')
        if isinstance(reasoning_diagnostics, dict):
            diagnostic_bundle = reasoning_diagnostics.get('temporal_proof_bundle')
            if isinstance(diagnostic_bundle, dict):
                _append_issue_ids(diagnostic_bundle.get('temporal_issue_ids'))

        return issue_ids

    def _build_unresolved_temporal_issue_ids(self, data: Dict[str, Any]) -> List[str]:
        issue_ids: List[str] = []

        def _append_issue_ids(values: List[str]):
            for value in values:
                if value not in issue_ids:
                    issue_ids.append(value)

        alignment_tasks = data.get('alignment_evidence_tasks')
        for task in alignment_tasks if isinstance(alignment_tasks, list) else []:
            if not isinstance(task, dict):
                continue
            resolution_status = self._normalize_evidence_escalation_status(task.get('resolution_status'))
            if resolution_status in _EVIDENCE_RESOLVED_STATUSES:
                continue
            _append_issue_ids(self._extract_temporal_issue_ids(task))

        packets = data.get('claim_support_packets')
        for claim_packet in packets.values() if isinstance(packets, dict) else []:
            if not isinstance(claim_packet, dict):
                continue
            elements = claim_packet.get('elements')
            for element in elements if isinstance(elements, list) else []:
                if not isinstance(element, dict):
                    continue
                support_status = str(element.get('support_status') or '').strip().lower()
                if support_status == 'supported':
                    continue
                _append_issue_ids(self._extract_temporal_issue_ids(element))

        temporal_issue_registry = data.get('temporal_issue_registry')
        for issue in temporal_issue_registry if isinstance(temporal_issue_registry, list) else []:
            if not isinstance(issue, dict):
                continue
            resolution_status = self._normalize_evidence_escalation_status(
                issue.get('current_resolution_status') or issue.get('status')
            )
            if resolution_status in _EVIDENCE_RESOLVED_STATUSES:
                continue
            for key in ('temporal_issue_id', 'issue_id', 'timeline_issue_id'):
                normalized = str(issue.get(key) or '').strip()
                if normalized:
                    _append_issue_ids([normalized])
                    break

        return issue_ids

    def _get_actionable_alignment_tasks(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        alignment_tasks = data.get('alignment_evidence_tasks')
        actionable_tasks: List[Dict[str, Any]] = []
        for task in alignment_tasks if isinstance(alignment_tasks, list) else []:
            if not isinstance(task, dict):
                continue
            support_status = str(task.get('support_status') or '').strip().lower()
            resolution_status = self._normalize_evidence_escalation_status(task.get('resolution_status'))
            if support_status not in {'unsupported', 'partially_supported', 'contradicted'}:
                continue
            temporal_issue_ids = self._extract_temporal_issue_ids(task)
            if support_status != 'contradicted' and resolution_status in _EVIDENCE_REVIEWABLE_ESCALATION_STATUSES and not temporal_issue_ids:
                continue
            actionable_tasks.append(task)
        return actionable_tasks

    def _get_alignment_promotion_drift_action(self, data: Dict[str, Any]) -> Dict[str, Any] | None:
        drift_summary = data.get('alignment_promotion_drift_summary')
        if not isinstance(drift_summary, dict):
            return None
        if not bool(drift_summary.get('drift_flag')):
            return None

        promoted_count = int(drift_summary.get('promoted_count', 0) or 0)
        pending_conversion_count = int(drift_summary.get('pending_conversion_count', 0) or 0)
        if promoted_count <= 0 and pending_conversion_count <= 0:
            return None

        latest_updates: Dict[str, Dict[str, Any]] = {}
        visible_updates = (
            data.get('alignment_task_update_history')
            if isinstance(data.get('alignment_task_update_history'), list) and data.get('alignment_task_update_history')
            else data.get('alignment_task_updates')
        )
        for index, update in enumerate(visible_updates if isinstance(visible_updates, list) else []):
            if not isinstance(update, dict):
                continue
            task_id = str(update.get('task_id') or '').strip()
            claim_type = str(update.get('claim_type') or '').strip()
            claim_element_id = str(update.get('claim_element_id') or '').strip()
            if not task_id and not (claim_type and claim_element_id):
                continue
            key = task_id or f'{claim_type}:{claim_element_id}'
            current_sequence = int(update.get('evidence_sequence', index) or index)
            previous = latest_updates.get(key)
            previous_sequence = int(previous.get('evidence_sequence', -1) or -1) if isinstance(previous, dict) else -1
            if previous is None or current_sequence >= previous_sequence:
                latest_updates[key] = dict(update)

        promoted_targets = [
            update for update in latest_updates.values()
            if self._normalize_evidence_escalation_status(update.get('resolution_status'))
            in {'promoted_to_testimony', 'promoted_to_document'}
        ]
        focused_claim_types = {
            str(update.get('claim_type') or '').strip()
            for update in promoted_targets
            if str(update.get('claim_type') or '').strip()
        }
        focused_element_keys = {
            (
                str(update.get('claim_type') or '').strip(),
                str(update.get('claim_element_id') or '').strip(),
            )
            for update in promoted_targets
            if str(update.get('claim_type') or '').strip()
            and str(update.get('claim_element_id') or '').strip()
        }

        action = {
            'action': 'validate_promoted_support',
            'recommended_actions': list(data.get('claim_support_recommended_actions', [])),
            'drift_summary': drift_summary,
            'pending_conversion_count': pending_conversion_count,
            'promoted_count': promoted_count,
        }
        validation_focus_summary = data.get('alignment_validation_focus_summary')
        if isinstance(validation_focus_summary, dict):
            action['validation_focus_summary'] = validation_focus_summary
            action['validation_target_count'] = int(validation_focus_summary.get('count', 0) or 0)
            primary_target = validation_focus_summary.get('primary_target')
            if isinstance(primary_target, dict) and primary_target:
                action['primary_validation_target'] = dict(primary_target)
            else:
                targets = validation_focus_summary.get('targets')
                if isinstance(targets, list) and targets and isinstance(targets[0], dict):
                    action['primary_validation_target'] = dict(targets[0])
        if len(focused_claim_types) == 1:
            action['claim_type'] = next(iter(focused_claim_types))
        if len(focused_element_keys) == 1:
            focused_claim_type, focused_element_id = next(iter(focused_element_keys))
            action['claim_type'] = focused_claim_type
            action['claim_element_id'] = focused_element_id
        elif isinstance(validation_focus_summary, dict):
            focused_target = action.get('primary_validation_target')
            if isinstance(focused_target, dict) and focused_target:
                focused_claim_type = str(focused_target.get('claim_type') or '').strip()
                focused_element_id = str(focused_target.get('claim_element_id') or '').strip()
                if focused_claim_type:
                    action['claim_type'] = focused_claim_type
                if focused_element_id:
                    action['claim_element_id'] = focused_element_id
        elif promoted_targets:
            promoted_targets.sort(
                key=lambda update: int(update.get('evidence_sequence', 0) or 0),
                reverse=True,
            )
            primary_target = promoted_targets[0]
            action['primary_validation_target'] = {
                'task_id': str(primary_target.get('task_id') or '').strip(),
                'claim_type': str(primary_target.get('claim_type') or '').strip(),
                'claim_element_id': str(primary_target.get('claim_element_id') or '').strip(),
                'promotion_kind': self._normalize_evidence_escalation_status(
                    str(primary_target.get('promotion_kind') or '').strip()
                    or str(primary_target.get('resolution_status') or '').strip().removeprefix('promoted_to_')
                ),
                'promotion_ref': str(primary_target.get('promotion_ref') or '').strip(),
                'evidence_sequence': int(primary_target.get('evidence_sequence', 0) or 0),
            }
        return action

    def _get_next_packet_evidence_action(self, packets: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any] | None:
        alignment_tasks = data.get('alignment_evidence_tasks')
        task_resolution_by_element: Dict[tuple[str, str], str] = {}
        for task in alignment_tasks if isinstance(alignment_tasks, list) else []:
            if not isinstance(task, dict):
                continue
            claim_type = str(task.get('claim_type') or '').strip().lower()
            element_id = str(task.get('claim_element_id') or '').strip().lower()
            if claim_type and element_id:
                task_resolution_by_element[(claim_type, element_id)] = self._normalize_evidence_escalation_status(
                    task.get('resolution_status')
                )

        for claim_key, claim_packet in packets.items():
            if not isinstance(claim_packet, dict):
                continue
            claim_type = str(claim_packet.get('claim_type') or claim_key or '').strip()
            for element in claim_packet.get('elements', []) or []:
                if not isinstance(element, dict):
                    continue
                support_status = str(element.get('support_status') or '').strip().lower()
                if support_status == 'supported':
                    continue
                task_resolution_status = task_resolution_by_element.get(
                    (claim_type.lower(), str(element.get('element_id') or '').strip().lower()),
                    '',
                )
                escalation_status = self._resolve_evidence_escalation_status(element, task_resolution_status)
                if support_status != 'contradicted' and escalation_status in _EVIDENCE_REVIEWABLE_ESCALATION_STATUSES:
                    continue
                action = str(element.get('recommended_next_step') or '').strip() or (
                    'resolve_support_conflicts' if support_status == 'contradicted' else 'fill_evidence_gaps'
                )
                return {
                    'action': action,
                    'claim_type': claim_type,
                    'claim_element_id': str(element.get('element_id') or '').strip(),
                    'support_status': support_status,
                    'recommended_actions': list(data.get('claim_support_recommended_actions', [])),
                }
        return None
    
    def get_current_phase(self) -> ComplaintPhase:
        """Get the current phase."""
        return self.current_phase
    
    def advance_to_phase(self, phase: ComplaintPhase) -> bool:
        """
        Advance to a new phase.
        
        Args:
            phase: The phase to advance to
            
        Returns:
            True if transition was successful, False otherwise
        """
        if self._can_advance_to(phase):
            self.phase_history.append({
                'from_phase': self.current_phase.value,
                'to_phase': phase.value,
                'timestamp': _utc_now_isoformat(),
                'iteration': self.iteration_count
            })
            self.current_phase = phase
            logger.info("Advanced to phase: %s", phase.value)
            return True
        else:
            logger.warning("Cannot advance to phase %s - requirements not met", phase.value)
            return False
    
    def _can_advance_to(self, phase: ComplaintPhase) -> bool:
        """Check if we can advance to a given phase."""
        if phase == ComplaintPhase.INTAKE:
            return True  # Can always go back to intake
        
        if phase == ComplaintPhase.EVIDENCE:
            # Can advance to evidence if intake is complete
            return self.is_phase_complete(ComplaintPhase.INTAKE)
        
        if phase == ComplaintPhase.FORMALIZATION:
            # Can advance to formalization if evidence gathering is sufficient
            return self.is_phase_complete(ComplaintPhase.EVIDENCE)
        
        return False
    
    def is_phase_complete(self, phase: ComplaintPhase) -> bool:
        """
        Check if a phase is complete.
        
        Args:
            phase: The phase to check
            
        Returns:
            True if phase is complete, False otherwise
        """
        completion_check = self._phase_completion_checks.get(phase)
        if completion_check is not None:
            return completion_check()
        method_name = self._PHASE_COMPLETION_CHECKS.get(phase)
        if method_name is None:
            return False
        return getattr(self, method_name)()
    
    def _is_intake_complete(self) -> bool:
        """
        Check if intake phase is complete.
        
        Intake is complete when:
        - Knowledge graph has been built
        - Dependency graph has been built
        - Gaps have been identified and addressed (or exhausted)
        - Denoising iterations have converged
        """
        readiness = self.get_intake_readiness()
        return readiness['ready']
    
    def _is_evidence_complete(self) -> bool:
        """
        Check if evidence gathering phase is complete.
        
        Evidence phase is complete when:
        - Evidence has been gathered for key claims
        - Knowledge graph has been enhanced with evidence
        - Critical evidence gaps are below threshold
        """
        data = self.phase_data[ComplaintPhase.EVIDENCE]
        
        evidence_gathered = data.get('evidence_count', 0) > 0
        kg_enhanced = data.get('knowledge_graph_enhanced', False)
        gap_ratio = data.get('evidence_gap_ratio', 1.0)
        packets = data.get('claim_support_packets')
        if isinstance(packets, dict) and packets:
            total_elements = int(data.get('claim_support_element_count', 0) or 0)
            explicit_status_count = int(data.get('claim_support_explicit_status_count', 0) or 0)
            blocking_contradictions = int(data.get('claim_support_blocking_contradictions', 0) or 0)
            unresolved_alignment_tasks = self._get_actionable_alignment_tasks(data)
            unresolved_without_review_path_count = int(data.get('claim_support_unresolved_without_review_path_count', 0) or 0)
            unresolved_temporal_issue_count = int(data.get('claim_support_unresolved_temporal_issue_count', 0) or 0)
            temporal_missing_anchor_task_count = int(data.get('temporal_missing_anchor_task_count', 0) or 0)
            temporal_missing_predicate_count = int(data.get('temporal_missing_predicate_count', 0) or 0)
            temporal_required_provenance_kind_count = int(
                data.get('temporal_required_provenance_kind_count', 0) or 0
            )
            return (
                total_elements > 0
                and explicit_status_count == total_elements
                and blocking_contradictions == 0
                and unresolved_without_review_path_count == 0
                and unresolved_temporal_issue_count == 0
                and temporal_missing_anchor_task_count == 0
                and temporal_missing_predicate_count == 0
                and temporal_required_provenance_kind_count == 0
                and not unresolved_alignment_tasks
            )

        return evidence_gathered and kg_enhanced and gap_ratio < _EVIDENCE_GAP_RATIO_THRESHOLD
    
    def _is_formalization_complete(self) -> bool:
        """
        Check if formalization phase is complete.
        
        Formalization is complete when:
        - Legal graph has been created
        - Neurosymbolic matching is done
        - Formal complaint has been generated
        """
        data = self.phase_data[ComplaintPhase.FORMALIZATION]
        
        has_legal_graph = 'legal_graph' in data
        matching_done = data.get('matching_complete', False)
        complaint_generated = data.get('formal_complaint', None) is not None
        
        return has_legal_graph and matching_done and complaint_generated
    
    def update_phase_data(self, phase: ComplaintPhase, key: str, value: Any):
        """Update data for a specific phase."""
        self.phase_data[phase][key] = value
        self._refresh_phase_derived_state(phase)
        logger.debug("Updated %s data: %s = %s", phase.value, key, value)
    
    def get_phase_data(self, phase: ComplaintPhase, key: str = None) -> Any:
        """Get data for a specific phase."""
        data = self.phase_data[phase]
        if key:
            return data.get(key)
        return data
    
    def record_iteration(self, loss: float, metrics: Dict[str, Any]):
        """
        Record an iteration with loss/noise metric.
        
        Args:
            loss: Current loss/noise value (lower is better)
            metrics: Additional metrics for this iteration
        """
        self.iteration_count += 1
        phase_value = self.current_phase.value
        self.loss_history.append({
            'iteration': self.iteration_count,
            'loss': loss,
            'phase': phase_value,
            'metrics': metrics,
            'timestamp': _utc_now_isoformat()
        })
        logger.info(
            "Iteration %s: loss=%.4f, phase=%s",
            self.iteration_count,
            loss,
            phase_value,
        )
    
    def has_converged(self, window: int = 5, threshold: float = 0.01) -> bool:
        """
        Check if iterations have converged.
        
        Args:
            window: Number of recent iterations to check
            threshold: Maximum change in loss to consider converged
            
        Returns:
            True if converged, False otherwise
        """
        if len(self.loss_history) < window:
            return False
        
        recent = self.loss_history[-window:]
        losses = [entry.get('loss', 0.0) for entry in recent]
        return (max(losses) - min(losses)) < threshold
    
    def get_next_action(self) -> Dict[str, Any]:
        """
        Get the next recommended action based on current phase and state.
        
        Returns:
            Dictionary with action type and parameters
        """
        action_getter = self._phase_action_getters.get(self.current_phase)
        if action_getter is not None:
            return action_getter()
        method_name = self._PHASE_ACTION_GETTERS.get(self.current_phase)
        if method_name is None:
            return {'action': 'unknown'}
        return getattr(self, method_name)()
    
    def _get_intake_action(self) -> Dict[str, Any]:
        """Get next action for intake phase."""
        data = self.phase_data[ComplaintPhase.INTAKE]

        readiness = self.get_intake_readiness()

        if 'knowledge_graph' not in data:
            return {
                'action': 'build_knowledge_graph',
                'intake_readiness_score': readiness['score'],
                'intake_blockers': readiness['blockers'],
            }

        if 'dependency_graph' not in data:
            return {
                'action': 'build_dependency_graph',
                'intake_readiness_score': readiness['score'],
                'intake_blockers': readiness['blockers'],
            }

        gaps = data.get('current_gaps', [])
        gap_threshold = _INTAKE_GAPS_THRESHOLD
        remaining_gaps = data.get('remaining_gaps', float('inf'))
        denoising_iteration_cap_hit = self.iteration_count >= _DENOISING_MAX_ITERATIONS
        if ((gaps and len(gaps) > 0) or remaining_gaps > gap_threshold) and not denoising_iteration_cap_hit:
            return {
                'action': 'address_gaps',
                'gaps': gaps,
                'intake_readiness_score': readiness['score'],
                'intake_blockers': readiness['blockers'],
            }

        semantic_blockers = [
            blocker for blocker in readiness['blockers']
            if blocker not in {
                'missing_knowledge_graph',
                'missing_dependency_graph',
                'unresolved_gaps',
                'denoising_not_converged',
            }
        ]
        if semantic_blockers:
            return {
                'action': 'address_gaps',
                'gaps': gaps,
                'intake_readiness_score': readiness['score'],
                'intake_blockers': readiness['blockers'],
            }

        if not data.get('denoising_converged', False) and not denoising_iteration_cap_hit:
            return {
                'action': 'continue_denoising',
                'intake_readiness_score': readiness['score'],
                'intake_blockers': readiness['blockers'],
            }

        if denoising_iteration_cap_hit or (data.get('denoising_converged', False) and remaining_gaps <= gap_threshold):
            return {
                'action': 'complete_intake',
                'intake_readiness_score': readiness['score'],
                'intake_blockers': readiness['blockers'],
            }

        return {
            'action': 'complete_intake',
            'intake_readiness_score': readiness['score'],
            'intake_blockers': readiness['blockers'],
        }
    
    def _get_evidence_action(self) -> Dict[str, Any]:
        """Get next action for evidence phase."""
        data = self.phase_data[ComplaintPhase.EVIDENCE]
        packets = data.get('claim_support_packets')
        prioritized_alignment_tasks = self._get_actionable_alignment_tasks(data)
        evidence_workflow_action_queue = (
            data.get('evidence_workflow_action_queue')
            if isinstance(data.get('evidence_workflow_action_queue'), list)
            else []
        )

        if isinstance(packets, dict) and packets:
            total_elements = int(data.get('claim_support_element_count', 0) or 0)
            explicit_status_count = int(data.get('claim_support_explicit_status_count', 0) or 0)
            if total_elements == 0 or explicit_status_count < total_elements:
                return {
                    'action': 'build_claim_support_packets',
                    'recommended_actions': list(data.get('claim_support_recommended_actions', [])),
                }
            if int(data.get('claim_support_blocking_contradictions', 0) or 0) > 0:
                return {
                    'action': 'resolve_support_conflicts',
                    'recommended_actions': list(data.get('claim_support_recommended_actions', [])),
                }
            drift_action = self._get_alignment_promotion_drift_action(data)
            if drift_action is not None:
                return drift_action
            for workflow_action in evidence_workflow_action_queue:
                if not isinstance(workflow_action, dict):
                    continue
                workflow_action_code = str(workflow_action.get('action_code') or '').strip().lower()
                if workflow_action_code not in {
                    'recover_document_grounding',
                    'refine_document_grounding_strategy',
                    'retarget_document_grounding',
                }:
                    continue
                response = {
                    'action': workflow_action_code,
                    'phase_name': 'document_generation',
                    'claim_type': str(workflow_action.get('claim_type') or ''),
                    'claim_element_id': str(workflow_action.get('claim_element_id') or ''),
                    'suggested_claim_element_id': str(workflow_action.get('suggested_claim_element_id') or ''),
                    'alternate_claim_element_ids': list(workflow_action.get('alternate_claim_element_ids') or [])[:3],
                    'claim_element_label': str(workflow_action.get('claim_element_label') or ''),
                    'preferred_support_kind': str(workflow_action.get('preferred_support_kind') or ''),
                    'missing_fact_bundle': list(workflow_action.get('missing_fact_bundle') or [])[:4],
                    'recommended_actions': list(data.get('claim_support_recommended_actions', [])),
                }
                if workflow_action_code == 'recover_document_grounding':
                    response['fact_backed_ratio'] = float(workflow_action.get('fact_backed_ratio') or 0.0)
                else:
                    response['suggested_support_kind'] = str(workflow_action.get('suggested_support_kind') or '')
                    response['learned_support_kind'] = str(workflow_action.get('learned_support_kind') or '')
                    response['alternate_support_kinds'] = list(workflow_action.get('alternate_support_kinds') or [])[:3]
                return response
            if prioritized_alignment_tasks:
                first_task = prioritized_alignment_tasks[0]
                return {
                    'action': str(first_task.get('action') or 'fill_evidence_gaps'),
                    'claim_type': str(first_task.get('claim_type') or ''),
                    'claim_element_id': str(first_task.get('claim_element_id') or ''),
                    'claim_element_label': str(first_task.get('claim_element_label') or ''),
                    'support_status': str(first_task.get('support_status') or ''),
                    'recommended_actions': list(data.get('claim_support_recommended_actions', [])),
                    'alignment_tasks': prioritized_alignment_tasks,
                }
            packet_action = self._get_next_packet_evidence_action(packets, data)
            if packet_action is not None:
                return packet_action
            if self._is_evidence_complete():
                return {
                    'action': 'complete_evidence',
                    'recommended_actions': list(data.get('claim_support_recommended_actions', [])),
                }
            if int(data.get('claim_support_unsupported_count', 0) or 0) > 0:
                return {
                    'action': 'fill_evidence_gaps',
                    'recommended_actions': list(data.get('claim_support_recommended_actions', [])),
                }
            return {
                'action': 'complete_evidence',
                'recommended_actions': list(data.get('claim_support_recommended_actions', [])),
            }
        
        if data.get('evidence_count', 0) == 0:
            return {'action': 'gather_evidence'}
        
        if not data.get('knowledge_graph_enhanced', False):
            return {'action': 'enhance_knowledge_graph'}
        
        gap_ratio = data.get('evidence_gap_ratio', 1.0)
        if gap_ratio > _EVIDENCE_GAP_RATIO_THRESHOLD:
            return {'action': 'fill_evidence_gaps', 'gap_ratio': gap_ratio}
        
        return {'action': 'complete_evidence'}
    
    def _get_formalization_action(self) -> Dict[str, Any]:
        """Get next action for formalization phase."""
        data = self.phase_data[ComplaintPhase.FORMALIZATION]
        
        if not data.get('legal_graph'):
            return {'action': 'build_legal_graph'}
        
        if not data.get('matching_complete', False):
            return {'action': 'perform_neurosymbolic_matching'}
        
        if not data.get('formal_complaint'):
            return {'action': 'generate_formal_complaint'}
        
        return {'action': 'complete_formalization'}
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'current_phase': self.current_phase.value,
            'phase_history': self.phase_history,
            'phase_data': {
                phase.value: data for phase, data in self.phase_data.items()
            },
            'iteration_count': self.iteration_count,
            'loss_history': self.loss_history
        }
    
    @classmethod
    def from_dict(cls, data: dict, mediator=None) -> 'PhaseManager':
        """Deserialize from dictionary."""
        manager = cls(mediator)
        manager.current_phase = ComplaintPhase(data['current_phase'])
        manager.phase_history = data['phase_history']
        manager.phase_data = {
            ComplaintPhase(phase_str): phase_data 
            for phase_str, phase_data in data['phase_data'].items()
        }
        manager.iteration_count = data['iteration_count']
        manager.loss_history = data['loss_history']
        return manager

    # ============================================================================
    # Batch 211: PhaseManager Analysis Methods
    # ============================================================================
    
    def total_phase_transitions(self) -> int:
        """Return the total number of phase transitions recorded.
        
        Returns:
            Count of phase transitions in history.
        """
        return len(self.phase_history)
    
    def transitions_to_phase(self, phase: ComplaintPhase) -> int:
        """Count transitions to a specific phase.
        
        Args:
            phase: The phase to count transitions to.
            
        Returns:
            Number of times transitioned to this phase.
        """
        phase_value = phase.value
        return sum(1 for t in self.phase_history if t.get('to_phase') == phase_value)
    
    def phase_transition_frequency(self) -> Dict[str, int]:
        """Calculate frequency distribution of phase transitions.
        
        Returns:
            Dict mapping phase names to transition counts.
        """
        freq = {}
        for transition in self.phase_history:
            to_phase = transition.get('to_phase')
            freq[to_phase] = freq.get(to_phase, 0) + 1
        return freq
    
    def most_visited_phase(self) -> str:
        """Find the phase that has been transitioned to most often.
        
        Returns:
            Phase name with most transitions, or 'none' if no transitions.
        """
        if not self.phase_history:
            return 'none'
        freq = self.phase_transition_frequency()
        return max(freq, key=freq.get)
    
    def total_iterations(self) -> int:
        """Return the total number of iterations recorded.
        
        Returns:
            Current iteration count.
        """
        return self.iteration_count
    
    def iterations_in_phase(self, phase: ComplaintPhase) -> int:
        """Count iterations that occurred in a specific phase.
        
        Args:
            phase: The phase to count iterations for.
            
        Returns:
            Number of iterations in this phase.
        """
        phase_value = phase.value
        return sum(1 for h in self.loss_history if h.get('phase') == phase_value)
    
    def average_loss(self) -> float:
        """Calculate the average loss across all recorded iterations.
        
        Returns:
            Mean loss value, or 0.0 if no iterations.
        """
        if not self.loss_history:
            return 0.0
        total_loss = sum(entry.get('loss', 0.0) for entry in self.loss_history)
        return total_loss / len(self.loss_history)
    
    def minimum_loss(self) -> float:
        """Find the minimum loss value across all iterations.
        
        Returns:
            Minimum loss achieved, or float('inf') if no iterations.
        """
        if not self.loss_history:
            return float('inf')
        return min(entry.get('loss', float('inf')) for entry in self.loss_history)
    
    def has_phase_data_key(self, phase: ComplaintPhase, key: str) -> bool:
        """Check if a specific data key exists for a phase.
        
        Args:
            phase: The phase to check.
            key: The data key to look for.
            
        Returns:
            True if the key exists in phase data, False otherwise.
        """
        return key in self.phase_data.get(phase, {})
    
    def phase_data_coverage(self) -> float:
        """Calculate what fraction of phases have any data recorded.
        
        Returns:
            Ratio of phases with data (0.0 to 1.0).
        """
        total_phases = len(self.phase_data)
        if total_phases == 0:
            return 0.0
        phases_with_data = sum(1 for data in self.phase_data.values() if data)
        return phases_with_data / total_phases
