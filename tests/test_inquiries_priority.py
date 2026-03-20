from types import SimpleNamespace

from mediator.inquiries import Inquiries


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
