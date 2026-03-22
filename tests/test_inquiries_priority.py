from types import SimpleNamespace

from mediator.inquiries import Inquiries
from mediator import Mediator
from complaint_phases import ComplaintPhase


def test_inquiries_prioritize_support_gap_targeted_legal_questions_first():
    mediator = SimpleNamespace(
        state=SimpleNamespace(
            inquiries=[
                {
                    'question': 'What happened?',
                    'answer': None,
                    'priority': 'Low',
                    'alternative_questions': [],
                },
                {
                    'question': 'Do you have the termination email?',
                    'answer': None,
                    'priority': 'Critical',
                    'support_gap_targeted': True,
                    'source': 'legal_question',
                    'alternative_questions': [],
                },
            ]
        )
    )
    inquiries = Inquiries(mediator)

    next_question = inquiries.get_next()

    assert next_question['question'] == 'Do you have the termination email?'


def test_inquiries_merge_legal_questions_dedupes_and_preserves_higher_priority():
    mediator = SimpleNamespace(
        state=SimpleNamespace(
            inquiries=[
                {
                    'question': 'Do you have the termination email?',
                    'answer': None,
                    'priority': 'High',
                    'alternative_questions': [],
                },
            ]
        )
    )
    inquiries = Inquiries(mediator)

    merged = inquiries.merge_legal_questions([
        {
            'question': 'Do you have the termination email?',
            'priority': 'Critical',
            'support_gap_targeted': True,
            'claim_type': 'employment retaliation',
            'element': 'Adverse action',
            'provenance': {'source_name': 'question-generator'},
        }
    ])

    assert merged == 1
    assert len(mediator.state.inquiries) == 1
    assert mediator.state.inquiries[0]['priority'] == 'Critical'
    assert mediator.state.inquiries[0]['support_gap_targeted'] is True
    assert mediator.state.inquiries[0]['source'] == 'legal_question'


def test_inquiries_dependency_gap_targeting_boosts_matching_question():
    mediator = SimpleNamespace(
        state=SimpleNamespace(
            inquiries=[]
        ),
        build_inquiry_gap_context=lambda: {
            'priority_terms': ['protected activity', 'termination email'],
            'gap_count': 2,
        },
    )
    inquiries = Inquiries(mediator)

    inquiries.merge_legal_questions([
        {
            'question': 'When did you report discrimination to HR as protected activity?',
            'priority': 'High',
            'support_gap_targeted': False,
            'claim_type': 'employment retaliation',
            'element': 'Protected activity',
            'provenance': {},
        },
        {
            'question': 'What damages have you suffered?',
            'priority': 'High',
            'support_gap_targeted': False,
            'claim_type': 'employment retaliation',
            'element': 'Damages',
            'provenance': {},
        },
    ])

    assert mediator.state.inquiries[0]['dependency_gap_targeted'] is True
    assert 'protected activity' in mediator.state.inquiries[0]['question'].lower()


def test_inquiries_explain_inquiry_reports_priority_and_gap_reasons():
    mediator = SimpleNamespace(
        state=SimpleNamespace(inquiries=[]),
        build_inquiry_gap_context=lambda: {'priority_terms': [], 'gap_count': 0},
    )
    inquiries = Inquiries(mediator)

    explanation = inquiries.explain_inquiry({
        'question': 'Do you have the termination email?',
        'priority': 'Critical',
        'support_gap_targeted': True,
        'dependency_gap_targeted': True,
        'source': 'legal_question',
        'claim_type': 'employment retaliation',
        'element': 'Adverse action',
    })

    assert explanation['priority'] == 'Critical'
    assert explanation['dependency_gap_targeted'] is True
    assert explanation['support_gap_targeted'] is True
    assert any('missing claim element' in reason for reason in explanation['reasons'])


def test_inquiries_get_next_prioritizes_uncovered_intake_objectives_before_plain_priority():
    mediator = SimpleNamespace(
        state=SimpleNamespace(
            inquiries=[
                {
                    'question': 'What damages have you suffered?',
                    'answer': None,
                    'priority': 'Critical',
                    'alternative_questions': [],
                },
                {
                    'question': 'Do you still have the denial notice or related emails?',
                    'answer': None,
                    'priority': 'High',
                    'alternative_questions': [],
                },
            ]
        ),
        build_inquiry_gap_context=lambda: {
            'priority_terms': [],
            'gap_count': 0,
            'intake_expected_objectives': ['documents', 'harm_remedy'],
            'intake_uncovered_objectives': ['documents'],
            'intake_covered_objectives': ['harm_remedy'],
        },
    )
    inquiries = Inquiries(mediator)

    next_question = inquiries.get_next()

    assert next_question['question'] == 'Do you still have the denial notice or related emails?'


def test_inquiries_merge_legal_questions_records_intake_priority_matches():
    mediator = SimpleNamespace(
        state=SimpleNamespace(inquiries=[]),
        build_inquiry_gap_context=lambda: {
            'priority_terms': [],
            'gap_count': 0,
            'intake_expected_objectives': ['anchor_adverse_action', 'timeline'],
            'intake_uncovered_objectives': ['anchor_adverse_action', 'timeline'],
            'intake_covered_objectives': [],
        },
    )
    inquiries = Inquiries(mediator)

    inquiries.merge_legal_questions([
        {
            'question': 'What adverse action did HACC take against you?',
            'priority': 'High',
            'support_gap_targeted': False,
            'claim_type': 'housing discrimination',
            'element': 'Adverse action',
            'provenance': {},
        },
        {
            'question': 'When did the first denial happen?',
            'priority': 'High',
            'support_gap_targeted': False,
            'claim_type': 'housing discrimination',
            'element': 'Timeline',
            'provenance': {},
        },
    ])

    assert mediator.state.inquiries[0]['intake_priority_targeted'] is True
    assert mediator.state.inquiries[0]['intake_priority_objectives'] == ['anchor_adverse_action']
    assert mediator.state.inquiries[0]['intake_priority_rank'] == 0
    assert mediator.state.inquiries[1]['intake_priority_objectives'] == ['timeline']
    assert mediator.state.inquiries[1]['intake_priority_rank'] == 1


def test_mediator_build_inquiry_gap_context_surfaces_chronology_and_proof_hints():
    class FakePhaseManager:
        def __init__(self, payloads):
            self.payloads = payloads

        def get_phase_data(self, phase, key):
            return self.payloads.get((phase, key))

    mediator = Mediator.__new__(Mediator)
    mediator.phase_manager = FakePhaseManager({
        (ComplaintPhase.INTAKE, 'intake_case_file'): {
            'candidate_claims': [],
            'temporal_issue_registry': [
                {
                    'issue_id': 'temporal_issue_001',
                    'issue_type': 'relative_only_ordering',
                    'claim_types': ['retaliation'],
                    'element_tags': ['causation'],
                    'recommended_resolution_lane': 'clarify_with_complainant',
                    'missing_temporal_predicates': ['Before(fact_001,fact_termination)'],
                    'required_provenance_kinds': ['testimony_record'],
                    'blocking': True,
                    'status': 'open',
                },
                {
                    'issue_id': 'temporal_issue_002',
                    'issue_type': 'missing_anchor',
                    'claim_types': ['retaliation'],
                    'element_tags': ['causation'],
                    'recommended_resolution_lane': 'seek_external_record',
                    'missing_temporal_predicates': ['Anchored(fact_termination)'],
                    'required_provenance_kinds': ['external_institutional_record'],
                    'blocking': True,
                    'status': 'open',
                },
            ],
        },
        (ComplaintPhase.EVIDENCE, 'claim_support_packets'): {},
        (ComplaintPhase.INTAKE, 'adversarial_intake_priority_summary'): {},
        (ComplaintPhase.INTAKE, 'workflow_optimization_guidance'): {
            'claim_support_temporal_handoff': {
                'unresolved_temporal_issue_count': 2,
                'chronology_task_count': 1,
                'temporal_proof_objectives': [
                    'protected activity to adverse action sequence',
                    'decision notice response date',
                ],
            },
            'claim_reasoning_review': {
                'retaliation': {
                    'proof_artifact_status_counts': {'missing': 2},
                }
            },
        },
    })

    context = Mediator.build_inquiry_gap_context(mediator)

    assert context['needs_chronology_closure'] is True
    assert context['needs_decision_document_precision'] is True
    assert context['unresolved_temporal_issue_count'] == 2
    assert context['chronology_task_count'] == 1
    assert context['missing_proof_artifact_count'] == 2
    assert 'timeline' in context['intake_uncovered_objectives']
    assert 'exact_dates' in context['intake_uncovered_objectives']
    assert 'causation_sequence' in context['intake_uncovered_objectives']
    assert 'response_dates' in context['intake_uncovered_objectives']
    assert 'documents' in context['intake_uncovered_objectives']
    assert 'decision notice' in [term.lower() for term in context['priority_terms']]
    assert context['chronology_objective_count'] == 2
    assert context['chronology_objective_ledger'][0]['issue_id'] == 'temporal_issue_001'
    assert context['chronology_objective_ledger'][0]['preferred_question_objective'] == 'establish_causation'
    assert context['chronology_objective_ledger'][0]['preferred_question_type'] == 'timeline'
    assert context['chronology_objective_ledger'][0]['suggested_prompt_family'] == 'causation_sequence'
    assert context['chronology_objective_ledger'][1]['preferred_question_objective'] == 'identify_supporting_proof'
    assert context['chronology_objective_ledger'][1]['preferred_question_type'] == 'evidence'
    assert context['chronology_objective_ledger'][1]['suggested_prompt_family'] == 'exhibit_grounding'


def test_select_intake_question_candidates_prefers_direct_chronology_objective_match():
    class MockBackend:
        id = 'mock_backend'

        def __call__(self, prompt):
            return 'Mock response'

    mediator = Mediator([MockBackend()])
    mediator.phase_manager.update_phase_data(
        ComplaintPhase.INTAKE,
        'intake_case_file',
        {
            'candidate_claims': [
                {
                    'claim_type': 'retaliation',
                    'label': 'Retaliation',
                    'required_elements': [],
                }
            ],
            'temporal_issue_registry': [
                {
                    'issue_id': 'temporal_issue_001',
                    'issue_type': 'relative_only_ordering',
                    'claim_types': ['retaliation'],
                    'element_tags': ['causation'],
                    'recommended_resolution_lane': 'clarify_with_complainant',
                    'missing_temporal_predicates': ['Before(fact_001,fact_termination)'],
                    'required_provenance_kinds': ['testimony_record'],
                    'blocking': True,
                    'status': 'open',
                }
            ],
        },
    )
    chronology_candidate = mediator.denoiser._question_candidate(
        source='intake_claim_temporal_gap',
        question_type='timeline',
        question_text=(
            'For your retaliation claim, what protected activity happened first, what adverse action followed, '
            'and on what exact dates did those events occur?'
        ),
        context={
            'claim_type': 'retaliation',
            'claim_name': 'Retaliation',
            'gap_id': 'temporal_issue_001',
            'target_element_id': 'causation',
            'temporal_issue_id': 'temporal_issue_001',
            'recommended_resolution_lane': 'clarify_with_complainant',
            'workflow_phase': 'graph_analysis',
        },
        priority='high',
    )
    chronology_candidate['question_objective'] = 'establish_causation'
    chronology_candidate['question_goal'] = 'establish_element'
    chronology_candidate['ranking_explanation']['question_objective'] = 'establish_causation'
    chronology_candidate['ranking_explanation']['question_goal'] = 'establish_element'

    generic_candidate = mediator.denoiser._question_candidate(
        source='knowledge_graph_gap',
        question_type='timeline',
        question_text='Can you walk me through the timeline generally?',
        context={
            'claim_type': 'retaliation',
            'claim_name': 'Retaliation',
            'target_element_id': 'causation',
            'workflow_phase': 'graph_analysis',
        },
        priority='high',
    )
    generic_candidate['question_objective'] = 'establish_chronology'
    generic_candidate['question_goal'] = 'establish_element'
    generic_candidate['ranking_explanation']['question_objective'] = 'establish_chronology'
    generic_candidate['ranking_explanation']['question_goal'] = 'establish_element'

    selected = mediator.select_intake_question_candidates(
        [generic_candidate, chronology_candidate],
        max_questions=2,
    )

    assert selected[0]['candidate_source'] == 'intake_claim_temporal_gap'
    assert selected[0]['selector_signals']['chronology_objective_direct_issue_match'] is True
    assert selected[0]['selector_signals']['chronology_objective_match_count'] == 1
    assert selected[0]['selector_signals']['chronology_objective_issue_ids'] == ['temporal_issue_001']
    assert selected[0]['selector_signals']['chronology_objective_preferred_objectives'] == ['establish_causation']
    assert 'causation_sequence' in selected[0]['selector_signals']['chronology_objective_prompt_families']
    assert selected[0]['selector_score'] > selected[1]['selector_score']


def test_inquiries_get_next_prioritizes_chronology_closure_before_documents():
    mediator = SimpleNamespace(
        state=SimpleNamespace(
            inquiries=[
                {
                    'question': 'Do you still have the denial notice or related emails?',
                    'answer': None,
                    'priority': 'High',
                    'alternative_questions': [],
                },
                {
                    'question': 'What exact date did the denial happen, and what happened next?',
                    'answer': None,
                    'priority': 'High',
                    'alternative_questions': [],
                },
            ]
        ),
        build_inquiry_gap_context=lambda: {
            'priority_terms': [],
            'gap_count': 0,
            'needs_chronology_closure': True,
            'needs_decision_document_precision': True,
            'intake_expected_objectives': ['documents', 'timeline', 'exact_dates'],
            'intake_uncovered_objectives': ['documents', 'timeline', 'exact_dates'],
            'intake_covered_objectives': [],
        },
    )
    inquiries = Inquiries(mediator)

    next_question = inquiries.get_next()

    assert next_question['question'] == 'What exact date did the denial happen, and what happened next?'


def test_inquiries_explain_inquiry_reports_chronology_and_document_reasons():
    mediator = SimpleNamespace(
        state=SimpleNamespace(inquiries=[]),
        build_inquiry_gap_context=lambda: {
            'priority_terms': [],
            'gap_count': 0,
            'needs_chronology_closure': True,
            'needs_decision_document_precision': True,
            'unresolved_temporal_issue_count': 2,
            'chronology_task_count': 1,
            'missing_proof_artifact_count': 3,
            'intake_expected_objectives': ['timeline', 'documents'],
            'intake_uncovered_objectives': ['timeline', 'documents'],
            'intake_covered_objectives': [],
        },
    )
    inquiries = Inquiries(mediator)

    explanation = inquiries.explain_inquiry({
        'question': 'When did you receive the denial notice?',
        'priority': 'High',
        'intake_priority_targeted': True,
        'intake_priority_objectives': ['timeline', 'documents'],
    })

    assert any('chronology gaps' in reason for reason in explanation['reasons'])
    assert any('missing decision or notice documents' in reason for reason in explanation['reasons'])
