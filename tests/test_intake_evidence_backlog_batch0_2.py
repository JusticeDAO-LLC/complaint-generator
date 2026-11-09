"""Tests for INTAKE_EVIDENCE_EXECUTION_BACKLOG Batch 0, 1, and 2 items.

Covers:
  - Batch 0: timeline_issues canonical alias, event record upsert, order_assumption_unsupported blocker
  - Batch 1: target_linkage on proof leads, target_element_metadata on open items
  - Batch 2: claim_criticality signal, duplicate objective suppression
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mediator_with_case_file(case_file: Dict[str, Any]) -> Any:
    """Build a minimal Mediator stub with a populated intake case file."""
    from mediator.mediator import Mediator

    mediator = Mediator.__new__(Mediator)
    mediator.log = MagicMock()

    # Minimal phase_manager stub
    phase_manager = MagicMock()
    phase_manager.get_phase_data = MagicMock(return_value=case_file)
    mediator.phase_manager = phase_manager
    return mediator


# ---------------------------------------------------------------------------
# Batch 0: timeline_issues canonical alias
# ---------------------------------------------------------------------------

class TestTimelineIssuesAlias:
    def _author_case_file(self, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run _author_temporal_case_file_state and return the mutated case file."""
        from mediator.mediator import Mediator

        mediator = Mediator.__new__(Mediator)
        mediator.log = MagicMock()
        case_file: Dict[str, Any] = {
            'canonical_facts': [
                {
                    'fact_id': 'f001',
                    'fact_type': 'timeline',
                    'text': 'I was denied housing on June 1.',
                    'event_date_or_range': '2024-06-01',
                }
            ],
        }
        # Inject pre-built issues so they survive the merge
        case_file['temporal_issue_registry'] = issues
        # Build minimal mock dependencies
        from complaint_phases import intake_case_file as icf_module
        mediator._author_temporal_case_file_state = lambda *a, **kw: Mediator._author_temporal_case_file_state(
            mediator, *a, **kw
        )
        mediator._author_temporal_case_file_state(case_file)
        return case_file

    def test_timeline_issues_present_after_authoring(self):
        case_file = self._author_case_file([])
        assert 'timeline_issues' in case_file
        assert isinstance(case_file['timeline_issues'], list)

    def test_timeline_issues_matches_temporal_issue_registry(self):
        """timeline_issues must be the same object as temporal_issue_registry."""
        case_file = self._author_case_file([])
        assert case_file['timeline_issues'] is case_file['temporal_issue_registry']

    def test_get_three_phase_status_exposes_timeline_issues(self):
        """get_three_phase_status must include timeline_issues and timeline_issues_summary."""
        from mediator.mediator import Mediator
        from complaint_phases.phase_manager import PhaseManager

        mediator = Mediator.__new__(Mediator)
        mediator.log = MagicMock()
        # Build enough state for the method
        phase_manager = MagicMock()
        phase_manager.iteration_count = 0
        phase_manager.loss_history = []
        phase_manager.get_current_phase = MagicMock(
            return_value=type('Phase', (), {'value': 'intake'})()
        )
        phase_manager.get_intake_readiness = MagicMock(return_value={
            'score': 0.0, 'blockers': [], 'criteria': {}, 'ready': False,
            'ready_to_advance': False, 'remaining_gap_count': 0,
            'contradiction_count': 0, 'contradictions': [],
            'intake_sections': {}, 'candidate_claim_count': 0,
            'canonical_fact_count': 0, 'proof_lead_count': 0,
            'blocking_contradictions': [], 'escalated_blocking_contradictions': [],
            'complainant_summary_confirmation': {},
        })
        mediator.phase_manager = phase_manager
        # Inject a timeline_issues alias into the intake_case_file
        issues = [{'issue_id': 'ti001', 'issue_type': 'relative_only_ordering', 'status': 'open'}]
        case_file = {
            'candidate_claims': [],
            'canonical_facts': [],
            'proof_leads': [],
            'open_items': [],
            'event_ledger': [],
            'temporal_fact_registry': [],
            'temporal_relation_registry': [],
            'temporal_issue_registry': issues,
            'timeline_issues': issues,
            'timeline_anchors': [],
            'timeline_relations': [],
        }
        phase_manager.get_phase_data = MagicMock(side_effect=lambda phase, key=None: {
            None: case_file,
            'intake_case_file': case_file,
        }.get(key, {}))
        # Stub helpers
        mediator._summarize_claim_support_packets = MagicMock(return_value={})
        mediator._summarize_alignment_evidence_tasks = MagicMock(return_value={})
        mediator._build_intake_chronology_readiness = MagicMock(return_value={})
        mediator._summarize_recent_validation_outcome = MagicMock(return_value={})
        mediator._summarize_alignment_task_update_status = MagicMock(return_value={})
        mediator._summarize_alignment_validation_focus = MagicMock(return_value={})
        mediator._summarize_intake_matching_pressure = MagicMock(return_value={})
        mediator._summarize_intake_workflow_action_queue = MagicMock(return_value={})
        mediator._summarize_evidence_workflow_action_queue = MagicMock(return_value={})
        mediator._get_confirmed_intake_summary_handoff = MagicMock(return_value={})
        mediator._summarize_intake_record_intents = MagicMock(return_value={})
        mediator.state = MagicMock()
        mediator.state.username = 'test'
        mediator.get_reranker_metrics = MagicMock(return_value={})

        status = Mediator.get_three_phase_status(mediator)
        assert 'timeline_issues' in status
        assert 'timeline_issues_summary' in status
        assert status['timeline_issues_summary']['count'] == 1


# ---------------------------------------------------------------------------
# Batch 0: event record upsert
# ---------------------------------------------------------------------------

class TestTimelineEventUpsert:
    def _make_minimal_mediator(self) -> Any:
        from mediator.mediator import Mediator

        mediator = Mediator.__new__(Mediator)
        mediator.log = MagicMock()
        return mediator

    def _stub_helpers(self, mediator: Any) -> None:
        from mediator.mediator import Mediator
        # Wire through real implementations we need
        for method in (
            '_normalize_intake_text',
            '_extract_date_or_range_from_text',
            '_extract_fact_participants_from_answer',
            '_extract_location_from_text',
            '_resolve_answer_claim_types',
            '_resolve_answer_element_targets',
            '_build_intake_question_intent_snapshot',
            '_append_canonical_fact',
            '_build_authored_event_support_refs',
            '_record_case_file_contradiction',
            '_merge_intake_question_intent',
            '_author_temporal_case_file_state',
        ):
            setattr(mediator, method, getattr(Mediator, method).__get__(mediator, Mediator))
        # Stub parts that talk to graphs
        mediator._next_intake_record_id = MagicMock(side_effect=lambda prefix, lst: f'{prefix}_{len(lst)+1:03d}')
        from complaint_phases import intake_case_file as icf_module
        mediator._apply_intake_answer_to_case_file = lambda q, a, cf, kg: Mediator._apply_intake_answer_to_case_file(
            mediator, q, a, cf, kg
        )

    def test_second_timeline_answer_same_text_does_not_duplicate(self):
        from mediator.mediator import Mediator
        import complaint_phases.intake_case_file as icf_module

        mediator = self._make_minimal_mediator()
        self._stub_helpers(mediator)

        question = {
            'type': 'timeline',
            'context': {},
        }
        case_file: Dict[str, Any] = {
            'canonical_facts': [],
            'proof_leads': [],
            'candidate_claims': [],
        }
        kg = MagicMock()
        kg.get_all_entities = MagicMock(return_value=[])
        kg.find_gaps = MagicMock(return_value=[])

        answer = 'I was denied housing on June 1, 2024.'
        # Patch refresh_intake_case_file to be a no-op so we control the case file
        import complaint_phases.intake_case_file as icf_module
        orig_refresh = icf_module.refresh_intake_case_file
        icf_module.refresh_intake_case_file = lambda cf, kg, **kw: cf
        try:
            mediator._apply_intake_answer_to_case_file(question, answer, case_file, kg)
            fact_count_after_first = len(case_file['canonical_facts'])
            mediator._apply_intake_answer_to_case_file(question, answer, case_file, kg)
            fact_count_after_second = len(case_file['canonical_facts'])
        finally:
            icf_module.refresh_intake_case_file = orig_refresh

        assert fact_count_after_first == 1
        # Re-answering with the same text should NOT add a new fact
        assert fact_count_after_second == 1, (
            'Identical timeline answer should upsert the existing record, not append a new one'
        )

    def test_second_timeline_answer_different_text_adds_new_fact(self):
        from mediator.mediator import Mediator
        import complaint_phases.intake_case_file as icf_module

        mediator = self._make_minimal_mediator()
        self._stub_helpers(mediator)

        question = {'type': 'timeline', 'context': {}}
        case_file: Dict[str, Any] = {
            'canonical_facts': [],
            'proof_leads': [],
            'candidate_claims': [],
        }
        kg = MagicMock()
        kg.get_all_entities = MagicMock(return_value=[])
        kg.find_gaps = MagicMock(return_value=[])

        orig_refresh = icf_module.refresh_intake_case_file
        icf_module.refresh_intake_case_file = lambda cf, kg, **kw: cf
        try:
            mediator._apply_intake_answer_to_case_file(
                question, 'I was denied housing on June 1, 2024.', case_file, kg
            )
            mediator._apply_intake_answer_to_case_file(
                question, 'Management responded on July 3, 2024.', case_file, kg
            )
            fact_count = len(case_file['canonical_facts'])
        finally:
            icf_module.refresh_intake_case_file = orig_refresh

        assert fact_count == 2, 'Different timeline answers should each produce a distinct fact record'


# ---------------------------------------------------------------------------
# Batch 0: order_assumption_unsupported blocker
# ---------------------------------------------------------------------------

class TestOrderAssumptionBlocker:
    def _build_readiness(self, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
        from complaint_phases.phase_manager import PhaseManager

        pm = PhaseManager.__new__(PhaseManager)
        case_file = {
            'temporal_issue_registry': issues,
            'event_ledger': [{'event_id': 'e1', 'start_date': ''}],
        }
        return pm._build_intake_chronology_readiness(case_file)

    def test_relative_only_ordering_sets_unsupported_count(self):
        issues = [
            {
                'issue_id': 'i001',
                'issue_type': 'relative_only_ordering',
                'status': 'open',
                'blocking': True,
                'severity': 'blocking',
            }
        ]
        result = self._build_readiness(issues)
        assert result['unsupported_order_assumption_count'] == 1

    def test_no_ordering_issues_gives_zero_count(self):
        issues = [
            {
                'issue_id': 'i002',
                'issue_type': 'missing_actor',
                'status': 'open',
                'blocking': False,
            }
        ]
        result = self._build_readiness(issues)
        assert result['unsupported_order_assumption_count'] == 0

    def test_order_assumption_unsupported_blocker_in_readiness(self):
        from complaint_phases.phase_manager import PhaseManager
        from unittest.mock import patch

        pm = PhaseManager.__new__(PhaseManager)
        pm.phase_data = {}

        issues = [
            {
                'issue_id': 'i003',
                'issue_type': 'relative_only_ordering',
                'current_resolution_status': 'open',
                'severity': 'blocking',
                'blocking': True,
            }
        ]
        case_file = {
            'candidate_claims': [],
            'canonical_facts': [],
            'proof_leads': [],
            'temporal_issue_registry': issues,
            'event_ledger': [{'event_id': 'e1', 'start_date': ''}],
        }
        # Patch _collect_intake_section_blockers to return minimal stub so we can test the blocker
        with patch.object(
            PhaseManager,
            '_collect_intake_section_blockers',
            return_value={
                'sections': {},
                'blockers': [],
                'criteria': {},
                'candidate_claim_count': 0,
                'canonical_fact_count': 0,
                'proof_lead_count': 0,
                'blocking_contradictions': [],
                'escalated_blocking_contradictions': [],
                'active_contradictions': [],
                'complainant_summary_confirmation': {},
            },
        ):
            data = {
                'intake_case_file': case_file,
                'knowledge_graph': MagicMock(),
                'dependency_graph': MagicMock(),
                'remaining_gaps': 0,
                'denoising_converged': True,
            }
            result = pm._build_intake_readiness(data)

        assert 'order_assumption_unsupported' in result['intake_readiness_blockers']


# ---------------------------------------------------------------------------
# Batch 1: target_linkage on proof leads
# ---------------------------------------------------------------------------

class TestProofLeadTargetLinkage:
    def _make_mediator(self) -> Any:
        from mediator.mediator import Mediator

        mediator = Mediator.__new__(Mediator)
        mediator.log = MagicMock()
        for method in (
            '_next_intake_record_id',
            '_proof_lead_expected_format',
            '_proof_lead_retrieval_path',
            '_merge_intake_question_intent',
            '_append_proof_lead',
            '_build_proof_lead_target_linkage',
        ):
            setattr(mediator, method, getattr(Mediator, method).__get__(mediator, Mediator))
        mediator._next_intake_record_id = MagicMock(side_effect=lambda p, lst: f'{p}_{len(lst)+1:03d}')
        return mediator

    def test_new_proof_lead_has_target_linkage(self):
        mediator = self._make_mediator()
        case_file: Dict[str, Any] = {
            'proof_leads': [],
            'candidate_claims': [{'claim_type': 'retaliation'}],
        }
        lead = mediator._append_proof_lead(
            case_file,
            text='My supervisor sent me a termination email on July 5.',
            lead_type='document',
            element_targets=['adverse_action'],
            related_fact_ids=['f001'],
        )
        assert 'target_linkage' in lead
        linkage = lead['target_linkage']
        assert linkage['has_element_target'] is True
        assert 'adverse_action' in linkage['element_ids']
        assert 'f001' in linkage['fact_ids']

    def test_proof_lead_dedup_refreshes_target_linkage(self):
        mediator = self._make_mediator()
        case_file: Dict[str, Any] = {
            'proof_leads': [],
            'candidate_claims': [],
        }
        # Add lead once
        mediator._append_proof_lead(
            case_file,
            text='Policy document from HR.',
            lead_type='document',
            element_targets=['written_policy'],
            related_fact_ids=['f010'],
        )
        # Update with additional element target
        lead = mediator._append_proof_lead(
            case_file,
            text='Policy document from HR.',
            lead_type='document',
            element_targets=['grievance_procedure'],
            related_fact_ids=['f011'],
        )
        linkage = lead['target_linkage']
        assert 'written_policy' in linkage['element_ids']
        assert 'grievance_procedure' in linkage['element_ids']


# ---------------------------------------------------------------------------
# Batch 1: target_element_metadata on open items
# ---------------------------------------------------------------------------

class TestOpenItemTargetElementMetadata:
    def _build_open_items(
        self, candidate_claims: List[Dict], temporal_issues: List[Dict] | None = None
    ) -> List[Dict[str, Any]]:
        from complaint_phases.intake_case_file import build_open_items

        case_file: Dict[str, Any] = {
            'candidate_claims': candidate_claims,
            'canonical_facts': [],
            'proof_leads': [],
            'temporal_issue_registry': temporal_issues or [],
            'open_items': [],
        }
        return build_open_items(case_file)

    def test_open_item_has_target_element_metadata_field(self):
        claims = [
            {
                'claim_type': 'retaliation',
                'required_elements': [
                    {
                        'element_id': 'adverse_action',
                        'label': 'Adverse Action',
                        'blocking': True,
                        'evidence_classes': ['document', 'testimony'],
                    }
                ],
            }
        ]
        # Force an open item by injecting a temporal issue that maps to an element
        issues = [
            {
                'issue_id': 'ii001',
                'issue_type': 'missing_absolute_date',
                'status': 'open',
                'severity': 'important',
                'claim_types': ['retaliation'],
                'element_tags': ['adverse_action'],
                'blocking': False,
            }
        ]
        items = self._build_open_items(claims, issues)
        # Every open item must have the metadata field (even if empty dict)
        for item in items:
            assert 'target_element_metadata' in item, (
                f"Open item {item.get('open_item_id')} missing target_element_metadata"
            )

    def test_open_item_metadata_contains_label_when_element_found(self):
        claims = [
            {
                'claim_type': 'employment_discrimination',
                'required_elements': [
                    {
                        'element_id': 'protected_class',
                        'label': 'Protected Class',
                        'blocking': True,
                        'evidence_classes': ['testimony'],
                    }
                ],
            }
        ]
        issues = [
            {
                'issue_id': 'ii002',
                'issue_type': 'relative_only_ordering',
                'status': 'open',
                'severity': 'blocking',
                'blocking': True,
                'claim_types': ['employment_discrimination'],
                'element_tags': ['protected_class'],
            }
        ]
        items = self._build_open_items(claims, issues)
        target_items = [
            item for item in items
            if item.get('target_element_id') == 'protected_class'
        ]
        if target_items:
            metadata = target_items[0].get('target_element_metadata', {})
            assert metadata.get('label') == 'Protected Class'
            assert metadata.get('blocking') is True


# ---------------------------------------------------------------------------
# Batch 2: claim_criticality signal
# ---------------------------------------------------------------------------

class TestClaimCriticalitySignal:
    def _annotate(
        self,
        candidate: Dict[str, Any],
        satisfaction_ratio: float = 0.0,
        missing_count: int = 0,
    ) -> Dict[str, Any]:
        from mediator.mediator import Mediator

        mediator = Mediator.__new__(Mediator)
        mediator.log = MagicMock()
        for method in (
            '_annotate_intake_question_candidate',
            '_phase_focus_rank',
            '_phase_focus_bonus',
            '_is_exact_dates_closure_match',
            '_is_staff_names_titles_closure_match',
            '_is_hearing_request_timing_closure_match',
            '_is_response_dates_closure_match',
            '_is_causation_sequence_match',
            '_is_document_question_candidate',
            '_match_chronology_objective_ledger',
            '_build_intake_workflow_action_queue',
            '_build_question_workflow_action_matches',
        ):
            if hasattr(Mediator, method):
                setattr(mediator, method, getattr(Mediator, method).__get__(mediator, Mediator))
        # Stub phase manager
        mediator.phase_manager = MagicMock()
        mediator.phase_manager.get_phase_data = MagicMock(return_value={})
        claim_pressure = {
            'retaliation': {
                'missing_count': missing_count,
                'satisfaction_ratio': satisfaction_ratio,
            }
        }
        matching_pressure = {}
        return mediator._annotate_intake_question_candidate(
            candidate, claim_pressure, matching_pressure, gap_context={}
        )

    def test_low_satisfaction_ratio_gives_critical(self):
        candidate = {
            'type': 'requirement',
            'question': 'What specific adverse action did you experience?',
            'target_claim_type': 'retaliation',
            'ranking_explanation': {'target_claim_type': 'retaliation'},
            'proof_priority': 1,
        }
        result = self._annotate(candidate, satisfaction_ratio=0.2, missing_count=4)
        assert result['claim_criticality'] == 'critical'
        assert result['selector_signals']['claim_criticality'] == 'critical'

    def test_medium_satisfaction_ratio_gives_important(self):
        candidate = {
            'type': 'evidence',
            'question': 'Do you have any supporting documents?',
            'target_claim_type': 'retaliation',
            'ranking_explanation': {'target_claim_type': 'retaliation'},
            'proof_priority': 5,
        }
        result = self._annotate(candidate, satisfaction_ratio=0.5, missing_count=1)
        assert result['claim_criticality'] == 'important'

    def test_contradiction_type_gives_critical_regardless_of_ratio(self):
        candidate = {
            'type': 'contradiction',
            'question': 'There is a conflict in the timeline. Which date is correct?',
            'target_claim_type': 'retaliation',
            'ranking_explanation': {'target_claim_type': 'retaliation'},
            'proof_priority': 2,
        }
        result = self._annotate(candidate, satisfaction_ratio=0.9, missing_count=0)
        assert result['claim_criticality'] == 'critical'

    def test_high_satisfaction_gives_supplemental(self):
        candidate = {
            'type': 'clarification',
            'question': 'Any other details you want to add?',
            'target_claim_type': 'retaliation',
            'ranking_explanation': {'target_claim_type': 'retaliation'},
            'proof_priority': 9,
        }
        result = self._annotate(candidate, satisfaction_ratio=0.85, missing_count=0)
        assert result['claim_criticality'] == 'supplemental'


# ---------------------------------------------------------------------------
# Batch 2: duplicate objective suppression
# ---------------------------------------------------------------------------

class TestDuplicateObjectiveSuppression:
    def _make_denoiser(self) -> Any:
        from complaint_phases.denoiser import ComplaintDenoiser

        denoiser = ComplaintDenoiser.__new__(ComplaintDenoiser)
        denoiser.questions_asked = []
        denoiser.answers = []
        denoiser._phase1_proof_priority = lambda qt: 5
        return denoiser

    def _q(self, q_type: str, element_id: str, text: str = '', priority: str = 'high') -> Dict[str, Any]:
        return {
            'type': q_type,
            'question': text or f'Question about {element_id}',
            'priority': priority,
            'proof_priority': 2,
            'context': {'requirement_id': element_id},
        }

    def test_same_objective_key_deduplicated(self):
        from complaint_phases.denoiser import ComplaintDenoiser

        denoiser = self._make_denoiser()
        # Build two candidates with identical (type, element_id) objective keys
        candidates = [
            self._q('requirement', 'adverse_action', 'What adverse action?'),
            self._q('requirement', 'adverse_action', 'Describe the adverse action.'),
        ]

        kg = MagicMock()
        kg.find_gaps = MagicMock(return_value=[])
        dg = MagicMock()
        dg.find_unsatisfied_requirements = MagicMock(return_value=[])
        dg.get_blocker_follow_up_issues = MagicMock(return_value=[])

        # Stub internal build methods to return our candidate list + nothing else
        denoiser._build_contradiction_questions = MagicMock(return_value=[])
        denoiser._build_claim_element_questions = MagicMock(return_value=candidates)
        denoiser._build_proof_lead_questions = MagicMock(return_value=[])
        denoiser._build_claim_temporal_gap_questions = MagicMock(return_value=[])
        denoiser._build_history_follow_up_questions = MagicMock(return_value=[])

        result = denoiser.collect_question_candidates(kg, dg, max_questions=10)
        # Only one of the two duplicate-objective candidates should survive
        adverse_action_qs = [
            q for q in result
            if (q.get('context') or {}).get('requirement_id') == 'adverse_action'
        ]
        assert len(adverse_action_qs) == 1

    def test_different_element_ids_both_kept(self):
        from complaint_phases.denoiser import ComplaintDenoiser

        denoiser = self._make_denoiser()
        candidates = [
            self._q('requirement', 'adverse_action', 'What adverse action?'),
            self._q('requirement', 'protected_activity', 'Describe the protected activity.'),
        ]

        kg = MagicMock()
        kg.find_gaps = MagicMock(return_value=[])
        dg = MagicMock()
        dg.find_unsatisfied_requirements = MagicMock(return_value=[])
        dg.get_blocker_follow_up_issues = MagicMock(return_value=[])

        denoiser._build_contradiction_questions = MagicMock(return_value=[])
        denoiser._build_claim_element_questions = MagicMock(return_value=candidates)
        denoiser._build_proof_lead_questions = MagicMock(return_value=[])
        denoiser._build_claim_temporal_gap_questions = MagicMock(return_value=[])
        denoiser._build_history_follow_up_questions = MagicMock(return_value=[])

        result = denoiser.collect_question_candidates(kg, dg, max_questions=10)
        element_ids = {(q.get('context') or {}).get('requirement_id') for q in result}
        assert 'adverse_action' in element_ids
        assert 'protected_activity' in element_ids
