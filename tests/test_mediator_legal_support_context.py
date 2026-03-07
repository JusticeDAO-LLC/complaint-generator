import os
from unittest.mock import Mock, patch


def test_analyze_complaint_legal_issues_passes_support_context_to_question_generation():
    from mediator import Mediator

    mock_backend = Mock()
    mock_backend.id = 'test-backend'

    mediator = Mediator(backends=[mock_backend])
    mediator.state.complaint = 'I was terminated after reporting discrimination to HR.'

    mediator.legal_classifier.classify_complaint = Mock(return_value={
        'claim_types': ['employment retaliation'],
        'legal_areas': ['employment law'],
        'jurisdiction': 'federal',
        'key_facts': ['termination email', 'reported discrimination to HR'],
    })
    mediator.statute_retriever.retrieve_statutes_bundle = Mock(return_value={
        'raw': [
            {
                'citation': '42 U.S.C. § 2000e-3',
                'title': 'Title VII retaliation provision',
                'relevance': 'Protects employees who report discrimination',
            }
        ],
        'normalized': [
            {
                'citation': '42 U.S.C. § 2000e-3',
                'title': 'Title VII retaliation provision',
                'snippet': 'Protects employees who report discrimination',
                'metadata': {},
            }
        ],
        'support_bundle': {
            'top_mixed': [],
            'top_authorities': [
                {
                    'title': 'Title VII retaliation provision',
                    'snippet': 'Protects employees who report discrimination',
                }
            ],
            'top_evidence': [],
            'cross_supported': [
                {
                    'title': 'Title VII retaliation provision',
                    'snippet': 'Protects employees who report discrimination',
                }
            ],
            'hybrid_cross_supported': [
                {
                    'title': 'Title VII retaliation provision',
                    'snippet': 'Protects employees who report discrimination',
                }
            ],
            'summary': {
                'total_records': 1,
                'authority_count': 1,
                'evidence_count': 0,
                'cross_supported_count': 1,
                'hybrid_cross_supported_count': 1,
            },
        },
    })
    mediator.summary_judgment.generate_requirements = Mock(return_value={
        'employment retaliation': ['Protected activity'],
    })
    mediator.question_generator.generate_questions = Mock(return_value=[
        {
            'question': 'Do you have the email showing your HR complaint?',
            'claim_type': 'employment retaliation',
            'element': 'Protected activity',
            'priority': 'Medium',
            'support_gap_targeted': False,
            'provenance': {},
        }
    ])

    with patch.dict(os.environ, {
        'IPFS_DATASETS_ENHANCED_LEGAL': '1',
        'IPFS_DATASETS_ENHANCED_SEARCH': '1',
    }, clear=False):
        mediator.analyze_complaint_legal_issues()

    provenance_context = mediator.question_generator.generate_questions.call_args.kwargs['provenance_context']
    assert provenance_context['support_summary']['cross_supported_count'] == 1
    assert 'Title VII retaliation provision' in provenance_context['support_context']
    assert any(item.get('source') == 'legal_question' for item in mediator.state.inquiries)
    assert mediator.state.inquiries[0]['priority'] in {'Medium', 'High', 'Critical'}
    next_question = mediator.process(None)
    assert next_question == mediator.state.current_inquiry['question']
    assert mediator.state.current_inquiry_explanation['priority'] in {'Medium', 'High', 'Critical'}
    assert isinstance(mediator.state.current_inquiry_explanation['reasons'], list)
    payload = mediator.get_current_inquiry_payload()
    assert payload['question'] == next_question
    assert payload['explanation'] == mediator.state.current_inquiry_explanation