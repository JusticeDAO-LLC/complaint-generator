import sys
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import document_optimization
from complaint_phases import ComplaintPhase
from complaint_phases.dependency_graph import DependencyGraph, DependencyNode, NodeType
from complaint_phases.knowledge_graph import Entity, KnowledgeGraph
from complaint_phases.legal_graph import LegalElement, LegalGraph
from complaint_phases.neurosymbolic_matcher import NeurosymbolicMatcher
from applications.document_api import _annotate_review_links
from document_pipeline import FormalComplaintDocumentBuilder
from mediator import Mediator
from mediator.formal_document import ComplaintDocumentBuilder, HAS_DOCX


pytestmark = pytest.mark.no_auto_network


def _build_seeded_mediator():
    backend = Mock()
    backend.id = 'test-backend'
    mediator = Mediator(backends=[backend])
    mediator.state.username = 'Jane Doe'

    kg = KnowledgeGraph()
    kg.add_entity(Entity(id='person:1', type='person', name='Jane Doe', attributes={'role': 'plaintiff'}))
    kg.add_entity(Entity(id='org:1', type='organization', name='Acme Corporation', attributes={'role': 'defendant'}))
    kg.add_entity(Entity(id='fact:1', type='fact', name='Plaintiff reported repeated sexual harassment to management on January 5, 2026.'))
    kg.add_entity(Entity(id='fact:2', type='fact', name='Defendant terminated Plaintiff on January 20, 2026 after she made the report.'))

    dg = DependencyGraph()
    dg.add_node(
        DependencyNode(
            id='claim:1',
            node_type=NodeType.CLAIM,
            name='Retaliation',
            attributes={'claim_type': 'retaliation'},
            satisfied=False,
            confidence=0.7,
        )
    )

    legal_graph = LegalGraph()
    legal_graph.add_element(
        LegalElement(
            id='req:1',
            element_type='requirement',
            name='Protected Activity',
            description='Plaintiff engaged in protected activity by opposing unlawful discrimination.',
            citation='42 U.S.C. § 2000e-3(a)',
            jurisdiction='federal',
            attributes={'applicable_claim_types': ['retaliation']},
        )
    )
    legal_graph.add_element(
        LegalElement(
            id='req:2',
            element_type='requirement',
            name='Adverse Action',
            description='Defendant took materially adverse action against Plaintiff.',
            citation='Burlington N. & Santa Fe Ry. Co. v. White',
            jurisdiction='federal',
            attributes={'applicable_claim_types': ['retaliation']},
        )
    )

    matching_results = NeurosymbolicMatcher().match_claims_to_law(kg, dg, legal_graph)

    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
    mediator.phase_manager.update_phase_data(
        ComplaintPhase.INTAKE,
        'intake_case_file',
        {
            'candidate_claims': [{'claim_type': 'retaliation'}],
            'canonical_facts': [{'fact_id': 'fact:1'}],
            'proof_leads': [{'lead_id': 'lead:1'}],
            'complainant_summary_confirmation': {
                'status': 'confirmed',
                'confirmed': True,
                'confirmed_at': '2026-03-17T18:00:00+00:00',
                'confirmation_note': 'ready for formal complaint generation',
                'confirmation_source': 'complainant',
                'summary_snapshot_index': 0,
                'current_summary_snapshot': {
                    'candidate_claim_count': 1,
                    'canonical_fact_count': 1,
                    'proof_lead_count': 1,
                },
                'confirmed_summary_snapshot': {
                    'candidate_claim_count': 1,
                    'canonical_fact_count': 1,
                    'proof_lead_count': 1,
                },
            },
        },
    )
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_gaps', [])
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_gap_types', [])
    mediator.phase_manager.current_phase = ComplaintPhase.FORMALIZATION
    mediator.phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph', legal_graph)
    mediator.phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'matching_results', matching_results)

    mediator.state.inquiries = [
        {
            'question': 'What happened?',
            'answer': 'I was fired after reporting sexual harassment to HR.',
        },
        {
            'question': 'What relief do you want?',
            'answer': 'I want reinstatement and damages.',
        },
    ]

    mediator.get_user_evidence = Mock(return_value=[
        {
            'cid': 'bafy-test-exhibit',
            'type': 'document',
            'description': 'Termination letter',
            'claim_type': 'retaliation',
            'parsed_text_preview': 'Letter confirming Plaintiff was terminated effective immediately.',
            'metadata': {'filename': 'termination_letter.pdf'},
            'source_url': 'https://example.org/termination-letter.pdf',
            'fact_count': 2,
        }
    ])
    mediator.get_legal_authorities = Mock(return_value=[
        {
            'claim_type': 'retaliation',
            'citation': '42 U.S.C. § 2000e-3(a)',
            'title': 'Title VII anti-retaliation provision',
            'url': 'https://www.law.cornell.edu/uscode/text/42/2000e-3',
            'relevance_score': 0.95,
        }
    ])
    mediator.get_claim_support = Mock(return_value=[
        {
            'claim_type': 'retaliation',
            'support_ref': 'bafy-test-exhibit',
            'claim_element_text': 'Protected Activity',
        }
    ])
    mediator.get_claim_support_facts = Mock(return_value=[
        {
            'text': 'Plaintiff complained to HR about harassment before Defendant terminated her.',
        }
    ])
    return mediator


def test_generate_formal_complaint_builds_court_style_sections():
    mediator = _build_seeded_mediator()

    result = mediator.generate_formal_complaint(
        district='New Mexico',
        county='Santa Fe County',
        case_number='1:26-cv-12345',
        lead_case_number='1:25-cv-00077',
        related_case_number='1:25-cv-00091',
        assigned_judge='Hon. Maria Valdez',
        courtroom='Courtroom 4A',
        signer_name='Jane Doe, Esq.',
        signer_title='Counsel for Plaintiff',
        signer_firm='Doe Legal Advocacy PLLC',
        signer_bar_number='NM-12345',
        signer_contact='123 Main Street\nSanta Fe, NM 87501',
        additional_signers=[
            {
                'name': 'John Roe, Esq.',
                'title': 'Co-Counsel for Plaintiff',
                'firm': 'Roe Civil Rights Group',
                'bar_number': 'NM-54321',
                'contact': '456 Side Street\nSanta Fe, NM 87505',
            }
        ],
        declarant_name='Jane Doe',
        affidavit_title='Affidavit of Jane Doe Regarding Retaliation',
        affidavit_intro="I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation.",
        affidavit_facts=[
            'I reported discrimination to human resources on March 3, 2026.',
            'Defendant terminated my employment two days later.',
        ],
        affidavit_supporting_exhibits=[
            {
                'label': 'Affidavit Ex. 1',
                'title': 'HR Complaint Email',
                'link': 'https://example.org/hr-email.pdf',
                'summary': 'Email reporting discrimination to HR.',
            }
        ],
        affidavit_include_complaint_exhibits=False,
        affidavit_venue_lines=['State of New Mexico', 'County: SANTA FE COUNTY'],
        affidavit_jurat='Subscribed and sworn to before me on March 13, 2026 by Jane Doe.',
        affidavit_notary_block=[
            '__________________________________',
            'Notary Public for the State of New Mexico',
            'My commission expires: March 13, 2029',
        ],
        service_method='CM/ECF',
        service_recipients=['Registered Agent for Acme Corporation', 'Defense Counsel'],
        service_recipient_details=[
            {'recipient': 'Defense Counsel', 'method': 'Email', 'address': 'counsel@example.com'},
            {'recipient': 'Registered Agent for Acme Corporation', 'method': 'Certified Mail', 'address': '123 Main Street'},
        ],
        jury_demand=True,
        jury_demand_text='Plaintiff demands a trial by jury on all issues so triable.',
        signature_date='2026-03-12',
        verification_date='2026-03-12',
        service_date='2026-03-13',
    )

    complaint = result['formal_complaint']
    assert result['intake_summary_handoff']['current_phase'] == ComplaintPhase.FORMALIZATION.value
    assert result['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
    assert complaint['court_header'] == 'IN THE UNITED STATES DISTRICT COURT FOR THE DISTRICT OF NEW MEXICO'
    assert complaint['caption']['case_number'] == '1:26-cv-12345'
    assert complaint['caption']['county_line'] == 'SANTA FE COUNTY'
    assert complaint['caption']['lead_case_number'] == '1:25-cv-00077'
    assert complaint['caption']['related_case_number'] == '1:25-cv-00091'
    assert complaint['caption']['assigned_judge'] == 'Hon. Maria Valdez'
    assert complaint['caption']['courtroom'] == 'Courtroom 4A'
    assert complaint['caption']['jury_demand_notice'] == 'JURY TRIAL DEMANDED'
    assert complaint['nature_of_action']
    assert complaint['legal_claims'][0]['title'] == 'COUNT I - RETALIATION'
    assert complaint['legal_claims'][0]['legal_standard_elements'][0]['citation'] == '42 U.S.C. § 2000e-3(a)'
    assert complaint['exhibits'][0]['label'] == 'Exhibit A'
    assert complaint['exhibits'][0]['reference'] == 'https://example.org/termination-letter.pdf'
    assert complaint['verification']['title'] == 'Verification'
    assert 'under penalty of perjury' in complaint['verification']['text']
    assert complaint['affidavit']['title'] == 'Affidavit of Jane Doe Regarding Retaliation'
    assert complaint['affidavit']['knowledge_graph_note'].startswith('This affidavit is generated from the complaint intake knowledge graph')
    assert complaint['affidavit']['intro'] == "I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation."
    assert complaint['affidavit']['venue_lines'] == ['State of New Mexico', 'County: SANTA FE COUNTY']
    assert complaint['affidavit']['facts'] == [
        'I reported discrimination to human resources on March 3, 2026.',
        'Defendant terminated my employment two days later.',
    ]
    assert complaint['affidavit']['supporting_exhibits'] == [
        {
            'label': 'Affidavit Ex. 1',
            'title': 'HR Complaint Email',
            'link': 'https://example.org/hr-email.pdf',
            'summary': 'Email reporting discrimination to HR.',
        }
    ]
    assert complaint['affidavit']['jurat'] == 'Subscribed and sworn to before me on March 13, 2026 by Jane Doe.'
    assert complaint['affidavit']['notary_block'][1] == 'Notary Public for the State of New Mexico'
    assert all('What happened?' not in fact for fact in complaint['affidavit']['facts'])
    assert any(
        'Plaintiff was fired after reporting sexual harassment to HR.' == allegation
        or 'I was fired after reporting sexual harassment to HR.' == allegation
        for allegation in complaint['factual_allegations']
    )
    assert any(
        allegation.startswith('After Plaintiff reported repeated sexual harassment to management on January 5, 2026')
        for allegation in complaint['factual_allegations']
    )
    assert complaint['factual_allegation_groups'][0]['title'] == 'Protected Activity and Complaints'
    assert all('lost my pay' not in allegation.lower() for allegation in complaint['factual_allegations'])
    assert all(' and i was ' not in allegation.lower() for allegation in complaint['factual_allegations'])
    assert all(' and i lost ' not in allegation.lower() for allegation in complaint['factual_allegations'])
    assert all(
        not allegation.lower().startswith('plaintiff seeks reinstatement')
        for allegation in complaint['factual_allegations']
    )
    assert 'PROTECTED ACTIVITY AND COMPLAINTS' in complaint['draft_text']
    assert 'ADVERSE ACTION AND RETALIATORY CONDUCT' in complaint['draft_text']
    assert complaint['certificate_of_service']['title'] == 'Certificate of Service'
    assert complaint['signature_block']['signature_line'] == '/s/ Jane Doe, Esq.'
    assert complaint['signature_block']['title'] == 'Counsel for Plaintiff'
    assert complaint['signature_block']['firm'] == 'Doe Legal Advocacy PLLC'
    assert complaint['signature_block']['bar_number'] == 'NM-12345'
    assert complaint['signature_block']['contact'] == '123 Main Street\nSanta Fe, NM 87501'
    assert complaint['signature_block']['dated'] == 'Dated: 2026-03-12'
    assert complaint['signature_block']['additional_signers'][0]['signature_line'] == '/s/ John Roe, Esq.'
    assert complaint['signature_block']['additional_signers'][0]['firm'] == 'Roe Civil Rights Group'
    assert complaint['verification']['signature_line'] == '/s/ Jane Doe'
    assert complaint['verification']['text'].startswith('I, Jane Doe, declare under penalty of perjury')
    assert complaint['verification']['dated'] == 'Executed on: 2026-03-12'
    assert complaint['certificate_of_service']['recipients'] == ['Registered Agent for Acme Corporation', 'Defense Counsel']
    assert complaint['certificate_of_service']['recipient_details'][0]['recipient'] == 'Defense Counsel'
    assert complaint['certificate_of_service']['recipient_details'][0]['method'] == 'Email'
    assert 'Defense Counsel | Method: Email | Address: counsel@example.com' in complaint['certificate_of_service']['detail_lines']
    assert complaint['certificate_of_service']['dated'] == 'Service date: 2026-03-13'
    assert 'following recipients' in complaint['certificate_of_service']['text']
    assert complaint['jury_demand']['title'] == 'Jury Demand'
    assert complaint['jury_demand']['text'] == 'Plaintiff demands a trial by jury on all issues so triable.'
    assert 'IN THE UNITED STATES DISTRICT COURT FOR THE DISTRICT OF NEW MEXICO' in result['draft_text']
    assert 'Assigned to: Hon. Maria Valdez' in result['draft_text']
    assert 'Lead Case No.: 1:25-cv-00077' in result['draft_text']
    assert 'Related Case No.: 1:25-cv-00091' in result['draft_text']
    assert 'Courtroom: Courtroom 4A' in result['draft_text']
    assert 'JURY TRIAL DEMANDED' in result['draft_text']
    assert 'AFFIDAVIT OF JANE DOE REGARDING RETALIATION' in result['draft_text']
    assert 'complaint intake knowledge graph' in result['draft_text']
    assert 'Subscribed and sworn to before me on March 13, 2026 by Jane Doe.' in result['draft_text']
    assert 'VERIFICATION' in result['draft_text']
    assert 'CERTIFICATE OF SERVICE' in result['draft_text']
    assert '/s/ Jane Doe, Esq.' in result['draft_text']
    assert 'Doe Legal Advocacy PLLC' in result['draft_text']
    assert '/s/ John Roe, Esq.' in result['draft_text']
    assert 'Roe Civil Rights Group' in result['draft_text']
    assert 'Bar No. NM-54321' in result['draft_text']
    assert 'Bar No. NM-12345' in result['draft_text']
    assert 'JURY DEMAND' in result['draft_text']
    assert 'Plaintiff demands a trial by jury on all issues so triable.' in result['draft_text']
    assert '/s/ Jane Doe' in result['draft_text']
    assert 'Defense Counsel | Method: Email | Address: counsel@example.com' in result['draft_text']
    assert 'Dated: 2026-03-12' in result['draft_text']
    assert 'Defense Counsel' in result['draft_text']
    assert 'Service date: 2026-03-13' in result['draft_text']
    assert result['ready_to_file'] is True


def test_generate_formal_complaint_can_suppress_mirrored_affidavit_exhibits():
    mediator = _build_seeded_mediator()

    result = mediator.generate_formal_complaint(
        district='New Mexico',
        county='Santa Fe County',
        plaintiff_names=['Jane Doe'],
        defendant_names=['Acme Corporation'],
        affidavit_include_complaint_exhibits=False,
    )

    complaint = result['formal_complaint']
    assert complaint['exhibits']
    assert complaint['affidavit']['supporting_exhibits'] == []


def test_document_api_annotation_promotes_confirmed_intake_handoff():
    mediator = _build_seeded_mediator()

    payload = _annotate_review_links(
        {
            'draft': {
                'title': 'Jane Doe v. Acme Corporation',
                'source_context': {'user_id': 'Jane Doe'},
            },
            'drafting_readiness': {
                'status': 'warning',
                'workflow_phase_plan': {
                    'recommended_order': ['graph_analysis', 'document_generation'],
                    'phases': {
                        'graph_analysis': {
                            'status': 'warning',
                            'summary': 'Graph analysis still shows 0 unresolved gap(s) or unprojected evidence updates.',
                            'recommended_actions': [
                                'Resolve remaining intake graph gaps and refresh graph projections before filing.',
                                'Project newly collected evidence into the complaint knowledge graph.',
                            ],
                        },
                        'document_generation': {
                            'status': 'warning',
                            'summary': 'Document generation still has 1 section warning(s) and 1 claim warning(s) to review.',
                            'recommended_actions': [
                                'Review claims-for-relief, exhibits, and requested-relief warnings before filing.',
                            ],
                        },
                    },
                },
                'sections': {
                    'claims_for_relief': {
                        'status': 'warning',
                        'title': 'Claims For Relief',
                    }
                },
                'claims': [
                    {
                        'claim_type': 'retaliation',
                        'status': 'warning',
                    }
                ],
            },
            'document_optimization': {},
        },
        mediator=mediator,
        user_id='Jane Doe',
    )

    assert payload['intake_summary_handoff']['current_phase'] == ComplaintPhase.FORMALIZATION.value
    assert payload['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
    assert payload['document_optimization']['intake_summary_handoff'] == payload['intake_summary_handoff']
    assert payload['review_links']['intake_status']['intake_summary_handoff'] == payload['intake_summary_handoff']
    assert payload['review_links']['intake_case_summary']['intake_summary_handoff'] == payload['intake_summary_handoff']
    assert payload['review_links']['workflow_priority'] == {
        'status': 'warning',
        'title': 'Review matching inputs before drafting',
        'description': 'Formal claim-to-law matching is still pending, so the draft may outrun the current legal targeting.',
        'action_label': 'Review matching inputs',
        'action_url': '/claim-support-review?user_id=Jane+Doe&claim_type=retaliation&section=claims_for_relief&follow_up_support_kind=authority&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first',
        'action_kind': 'link',
        'dashboard_url': '/claim-support-review?user_id=Jane+Doe',
        'chip_labels': [
            'recommended action: perform_neurosymbolic_matching',
            'focus claim: Retaliation',
        ],
    }
    assert payload['review_links']['workflow_phase_priority'] == {
        'phase_name': 'graph_analysis',
        'status': 'warning',
        'title': 'Resolve graph analysis before drafting',
        'description': 'Graph analysis still shows 0 unresolved gap(s) or unprojected evidence updates.',
        'action_label': 'Review graph inputs',
        'action_url': '/claim-support-review?user_id=Jane+Doe&claim_type=retaliation&section=summary_of_facts&follow_up_support_kind=evidence',
        'action_kind': 'link',
        'dashboard_url': '/claim-support-review?user_id=Jane+Doe',
        'recommended_actions': [
            'Resolve remaining intake graph gaps and refresh graph projections before filing.',
            'Project newly collected evidence into the complaint knowledge graph.',
        ],
        'chip_labels': [
            'workflow phase: Graph Analysis',
            'phase status: Warning',
            'recommended action: Resolve remaining intake graph gaps and refresh graph projections before filing.',
        ],
    }


def test_document_optimizer_report_promotes_confirmed_intake_handoff(monkeypatch):
    mediator = _build_seeded_mediator()
    optimizer = document_optimization.AgenticDocumentOptimizer(
        mediator=mediator,
        max_iterations=1,
        target_score=0.95,
        persist_artifacts=True,
    )

    stored_trace_payloads = []

    monkeypatch.setattr(
        optimizer,
        '_build_support_context',
        lambda **kwargs: {'packet_projection': {'section_presence': {'factual_allegations': True}}},
    )

    critic_responses = iter(
        [
            {'overall_score': 0.25, 'llm_metadata': {}},
            {'overall_score': 0.55, 'llm_metadata': {}},
        ]
    )
    monkeypatch.setattr(optimizer, '_run_critic', lambda **kwargs: next(critic_responses))
    monkeypatch.setattr(optimizer, '_choose_focus_section', lambda **kwargs: 'factual_allegations')
    monkeypatch.setattr(optimizer, '_run_actor', lambda **kwargs: {'llm_metadata': {}, 'factual_allegations': ['Improved fact']})
    monkeypatch.setattr(optimizer, '_apply_actor_payload', lambda draft, **kwargs: {**draft, 'factual_allegations': ['Improved fact']})
    monkeypatch.setattr(
        optimizer,
        '_build_iteration_change_manifest',
        lambda **kwargs: [{'field': 'factual_allegations', 'before_count': 1, 'after_count': 1}],
    )
    monkeypatch.setattr(optimizer, '_select_support_context', lambda **kwargs: {'focus_section': 'factual_allegations'})
    monkeypatch.setattr(optimizer, '_build_upstream_optimizer_metadata', lambda: {'selected_provider': 'test-provider'})
    monkeypatch.setattr(optimizer, '_router_status', lambda: {'available': False})
    monkeypatch.setattr(optimizer, '_router_usage_summary', lambda: {'llm_calls': 0})
    monkeypatch.setattr(
        optimizer,
        '_store_trace',
        lambda payload: (stored_trace_payloads.append(payload) or {'cid': 'bafy-doc-opt', 'status': 'stored'}),
    )

    report = optimizer.optimize_draft(
        draft={'title': 'Jane Doe v. Acme Corporation', 'factual_allegations': ['Original fact']},
        user_id='Jane Doe',
        drafting_readiness={},
        config={},
    )

    assert report['intake_summary_handoff']['current_phase'] == ComplaintPhase.FORMALIZATION.value
    assert report['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
    assert stored_trace_payloads[0]['intake_summary_handoff'] == report['intake_summary_handoff']
    assert stored_trace_payloads[0]['intake_status']['intake_summary_handoff'] == report['intake_summary_handoff']
    assert stored_trace_payloads[0]['intake_case_summary']['intake_summary_handoff'] == report['intake_summary_handoff']


def test_score_factual_allegations_rewards_timing_and_staff_detail():
    optimizer = document_optimization.AgenticDocumentOptimizer(
        mediator=_build_seeded_mediator(),
        max_iterations=1,
        target_score=0.95,
        persist_artifacts=False,
    )

    baseline_score = optimizer._score_factual_allegations(
        [
            'Plaintiff engaged in protected activity.',
            'Defendant later took adverse action.',
        ],
        [],
    )
    enhanced_score = optimizer._score_factual_allegations(
        [
            'On January 5, 2026, Plaintiff requested a hearing review from Case Manager Jordan Lee.',
            'Housing Director Maya Chen responded on January 12, 2026 with the decision date for the hearing outcome.',
            'Days after Plaintiff made the protected complaint, HACC took adverse action.',
        ],
        [],
    )

    assert enhanced_score > baseline_score


def test_document_package_promotes_confirmed_intake_handoff(tmp_path):
    mediator = _build_seeded_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)

    result = builder.build_package(
        district='New Mexico',
        county='Santa Fe County',
        plaintiff_names=['Jane Doe'],
        defendant_names=['Acme Corporation'],
        output_dir=str(tmp_path),
        output_formats=['txt'],
    )

    assert result['intake_summary_handoff']['current_phase'] == ComplaintPhase.FORMALIZATION.value
    assert result['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
    assert result['draft']['drafting_readiness'] == result['drafting_readiness']


def test_factual_allegations_merge_overlapping_adverse_action_narratives():
    builder = ComplaintDocumentBuilder(Mock())

    allegations = builder._build_factual_allegations(
        [
            'Plaintiff complained to human resources and regional management about race discrimination and unequal pay.',
            'After those complaints, Defendant removed Plaintiff from key accounts, cut her overtime, and then terminated her employment.',
            'Plaintiff lost wages, benefits, and future career opportunities as a result.',
            'My major accounts were taken away, my overtime was cut, and I was fired within weeks after complaining to HR and regional management.',
            'I lost wages, benefits, and future career opportunities.',
            'Plaintiff reported race discrimination and unequal pay to human resources and regional management before Defendant terminated her employment.',
            'After Plaintiff made those complaints, Defendant stripped her of major accounts and overtime before ending her employment.',
        ],
        None,
        [],
    )

    assert allegations[:2] == [
        'After Plaintiff complained to human resources and regional management about race discrimination and unequal pay, Defendant removed Plaintiff from key accounts, cut her overtime, and then terminated her employment.',
        "As a direct result of Defendant's conduct, Plaintiff lost wages, benefits, and future career opportunities.",
    ]
    assert 'On or about [date], HACC communicated the adverse action described in this complaint.' in allegations
    assert 'HACC decision-makers for intake, review, hearing, and adverse-action steps should be identified by name or title.' in allegations
    assert 'After Plaintiff engaged in protected activity, HACC took adverse action, and the available timeline supports a causal connection.' in allegations


def test_export_formal_complaint_pdf_writes_file(tmp_path):
    mediator = _build_seeded_mediator()
    output_path = tmp_path / 'formal_complaint.pdf'

    result = mediator.export_formal_complaint(
        str(output_path),
        district='New Mexico',
        case_number='1:26-cv-12345',
    )

    assert result['intake_summary_handoff']['current_phase'] == ComplaintPhase.FORMALIZATION.value
    assert result['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
    assert result['export']['format'] == 'pdf'
    assert output_path.exists()
    assert output_path.stat().st_size > 0


@pytest.mark.skipif(not HAS_DOCX, reason='python-docx not installed')
def test_export_formal_complaint_docx_writes_file(tmp_path):
    mediator = _build_seeded_mediator()
    output_path = tmp_path / 'formal_complaint.docx'

    result = mediator.export_formal_complaint(
        str(output_path),
        district='New Mexico',
        case_number='1:26-cv-12345',
    )

    assert result['intake_summary_handoff']['current_phase'] == ComplaintPhase.FORMALIZATION.value
    assert result['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
    assert result['export']['format'] == 'docx'
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    with zipfile.ZipFile(output_path) as archive:
        document_xml = archive.read('word/document.xml').decode('utf-8')
    assert 'Protected Activity and Complaints' in document_xml
    assert 'Adverse Action and Retaliatory Conduct' in document_xml