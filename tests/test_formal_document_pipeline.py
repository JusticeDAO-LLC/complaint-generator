import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
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
            'canonical_facts': [
                {
                    'fact_id': 'fact:1',
                    'text': 'Plaintiff reported repeated sexual harassment to management on January 5, 2026.',
                    'fact_type': 'timeline',
                    'predicate_family': 'protected_activity',
                    'event_label': 'Protected activity',
                    'event_date_or_range': 'January 5, 2026',
                    'temporal_context': {
                        'raw_text': 'January 5, 2026',
                        'start_date': '2026-01-05',
                        'end_date': '2026-01-05',
                        'granularity': 'day',
                        'is_approximate': False,
                        'is_range': False,
                        'relative_markers': [],
                        'sortable_date': '2026-01-05',
                        'matched_text': 'January 5, 2026',
                    },
                },
                {
                    'fact_id': 'fact:2',
                    'text': 'Defendant terminated Plaintiff on January 20, 2026 after she made the report.',
                    'fact_type': 'timeline',
                    'predicate_family': 'adverse_action',
                    'event_label': 'Adverse action',
                    'event_date_or_range': 'January 20, 2026',
                    'temporal_context': {
                        'raw_text': 'January 20, 2026',
                        'start_date': '2026-01-20',
                        'end_date': '2026-01-20',
                        'granularity': 'day',
                        'is_approximate': False,
                        'is_range': False,
                        'relative_markers': [],
                        'sortable_date': '2026-01-20',
                        'matched_text': 'January 20, 2026',
                    },
                },
            ],
            'timeline_relations': [
                {
                    'relation_id': 'timeline_relation_001',
                    'source_fact_id': 'fact:1',
                    'target_fact_id': 'fact:2',
                    'relation_type': 'before',
                    'source_start_date': '2026-01-05',
                    'source_end_date': '2026-01-05',
                    'target_start_date': '2026-01-20',
                    'target_end_date': '2026-01-20',
                    'confidence': 'high',
                }
            ],
            'temporal_issue_registry': [],
            'proof_leads': [{'lead_id': 'lead:1'}],
            'blocker_follow_up_summary': {
                'blocking_item_count': 1,
                'blocking_objectives': ['exact_dates', 'response_dates'],
                'extraction_targets': ['timeline_anchors', 'response_timeline'],
                'workflow_phases': ['graph_analysis', 'intake_questioning', 'document_generation'],
                'blocking_items': [
                    {
                        'blocker_id': 'missing_response_timing',
                        'reason': 'Response or non-response events are described without date anchors.',
                        'primary_objective': 'response_dates',
                        'blocker_objectives': ['response_dates', 'exact_dates'],
                        'extraction_targets': ['response_timeline', 'timeline_anchors'],
                        'workflow_phases': ['graph_analysis', 'intake_questioning', 'document_generation'],
                        'issue_family': 'response_timeline',
                    }
                ],
            },
            'open_items': [
                {
                    'open_item_id': 'blocker:missing_response_timing',
                    'kind': 'blocker_follow_up',
                    'reason': 'Response or non-response events are described without date anchors.',
                    'primary_objective': 'response_dates',
                    'blocker_objectives': ['response_dates', 'exact_dates'],
                    'extraction_targets': ['response_timeline', 'timeline_anchors'],
                    'workflow_phases': ['graph_analysis', 'intake_questioning', 'document_generation'],
                    'issue_family': 'response_timeline',
                }
            ],
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
    assert complaint['legal_claims'][0]['supporting_facts'][0] == 'The chronology shows protected activity on January 5, 2026 before adverse action on January 20, 2026.'
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
    assert complaint['anchored_chronology_summary'] == [
        'Protected activity on January 5, 2026 preceded adverse action on January 20, 2026.'
    ]
    assert all('lost my pay' not in allegation.lower() for allegation in complaint['factual_allegations'])
    assert all(' and i was ' not in allegation.lower() for allegation in complaint['factual_allegations'])
    assert all(' and i lost ' not in allegation.lower() for allegation in complaint['factual_allegations'])
    assert all(
        not allegation.lower().startswith('plaintiff seeks reinstatement')
        for allegation in complaint['factual_allegations']
    )
    assert 'PROTECTED ACTIVITY AND COMPLAINTS' in complaint['draft_text']
    assert 'ADVERSE ACTION AND RETALIATORY CONDUCT' in complaint['draft_text']
    assert 'ANCHORED CHRONOLOGY' in complaint['draft_text']
    assert '1. Protected activity on January 5, 2026 preceded adverse action on January 20, 2026.' in complaint['draft_text']
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


def test_generate_formal_complaint_adds_claim_temporal_gap_hints():
    mediator = _build_seeded_mediator()
    intake_case_file = dict(mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {})
    intake_case_file['temporal_issue_registry'] = [
        {
            'summary': 'Timeline fact fact:2 only has relative ordering and still needs anchoring.',
            'status': 'open',
            'claim_types': ['retaliation'],
            'element_tags': ['causation'],
        }
    ]
    intake_case_file['blocker_follow_up_summary'] = {
        'blocking_items': [
            {
                'reason': 'Protected activity and adverse action still need tighter causation sequencing.',
                'primary_objective': 'causation_sequence',
                'blocker_objectives': ['causation_sequence', 'exact_dates'],
                'issue_family': 'causation',
            }
        ]
    }
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', intake_case_file)

    result = mediator.generate_formal_complaint(
        district='New Mexico',
        county='Santa Fe County',
        plaintiff_names=['Jane Doe'],
        defendant_names=['Acme Corporation'],
    )

    missing_requirements = result['formal_complaint']['legal_claims'][0]['missing_requirements']
    assert {
        'name': 'Chronology gap',
        'citation': '',
        'suggested_action': 'Timeline fact fact:2 only has relative ordering and still needs anchoring.',
    } in missing_requirements
    assert {
        'name': 'Chronology gap',
        'citation': '',
        'suggested_action': 'Protected activity and adverse action still need tighter causation sequencing.',
    } in missing_requirements


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
            'document_optimization': {
                'intake_priorities': {
                    'claim_temporal_gap_count': 2,
                    'claim_temporal_gap_summary': [
                        {
                            'claim_type': 'retaliation',
                            'gap_count': 2,
                            'gaps': [
                                'Chronology gap: Timeline fact fact:2 only has relative ordering and still needs anchoring.',
                                'Chronology gap: Protected activity and adverse action still need tighter causation sequencing.',
                            ],
                        }
                    ],
                }
            },
        },
        mediator=mediator,
        user_id='Jane Doe',
    )

    assert payload['intake_summary_handoff']['current_phase'] == ComplaintPhase.FORMALIZATION.value
    assert payload['intake_summary_handoff']['complainant_summary_confirmation']['confirmed'] is True
    assert payload['document_optimization']['intake_summary_handoff'] == payload['intake_summary_handoff']
    assert payload['review_links']['intake_status']['intake_summary_handoff'] == payload['intake_summary_handoff']
    assert payload['review_links']['intake_case_summary']['intake_summary_handoff'] == payload['intake_summary_handoff']
    assert payload['review_links']['intake_case_summary']['blocker_follow_up_summary']['blocking_objectives'] == ['exact_dates', 'response_dates']
    assert payload['review_links']['intake_case_summary']['open_items'][0]['primary_objective'] == 'response_dates'
    assert payload['review_links']['intake_case_summary']['claim_temporal_gap_count'] == 2
    assert payload['review_links']['intake_case_summary']['claim_temporal_gap_summary'] == [
        {
            'claim_type': 'retaliation',
            'gap_count': 2,
            'gaps': [
                'Chronology gap: Timeline fact fact:2 only has relative ordering and still needs anchoring.',
                'Chronology gap: Protected activity and adverse action still need tighter causation sequencing.',
            ],
        }
    ]
    assert payload['review_links']['intake_case_summary']['temporal_issue_registry_summary'] == {
        'count': 0,
        'issues': [],
        'status_counts': {},
        'severity_counts': {},
        'lane_counts': {},
        'issue_type_counts': {},
        'claim_type_counts': {},
        'element_tag_counts': {},
        'resolved_count': 0,
        'unresolved_count': 0,
        'issue_ids': [],
        'missing_temporal_predicates': [],
        'required_provenance_kinds': [],
    }
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
            'claim chronology gaps: 2',
            'chronology focus: Retaliation',
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


def test_document_api_annotation_promotes_document_drafting_next_action_into_review_links():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="Jane Doe", hashed_username=None)
    mediator.get_three_phase_status.return_value = {
        "current_phase": "evidence",
        "intake_readiness": {
            "score": 0.82,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "criteria": {"complainant_summary_confirmed": True},
            "blockers": [],
            "contradictions": [],
            "candidate_claim_count": 1,
            "canonical_fact_count": 2,
            "proof_lead_count": 1,
        },
        "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.9}],
        "intake_sections": {},
        "canonical_fact_summary": {"count": 2, "facts": []},
        "proof_lead_summary": {"count": 1, "proof_leads": []},
        "question_candidate_summary": {},
        "document_workflow_execution_summary": {
            "iteration_count": 2,
            "accepted_iteration_count": 1,
            "first_focus_section": "claims_for_relief",
            "first_targeted_claim_element": "causation",
            "first_preferred_support_kind": "testimony",
        },
        "document_execution_drift_summary": {
            "drift_flag": True,
            "top_targeted_claim_element": "protected_activity",
            "first_executed_claim_element": "causation",
            "first_focus_section": "claims_for_relief",
            "first_preferred_support_kind": "testimony",
        },
        "next_action": {"action": "complete_evidence"},
    }

    payload = _annotate_review_links(
        {
            "draft": {
                "title": "Jane Doe v. Acme Corporation",
                "source_context": {"user_id": "Jane Doe"},
                "factual_allegation_paragraphs": [
                    {
                        "number": 1,
                        "text": "Days after the complaint, Defendant terminated Plaintiff in retaliation.",
                        "document_focus": {
                            "focus_source": "document_grounding_improvement_next_action",
                            "action": "retarget_document_grounding",
                            "target_claim_element_id": "causation",
                            "original_claim_element_id": "protected_activity",
                            "preferred_support_kind": "testimony",
                        },
                        "document_focus_priority_rank": 1,
                    }
                ],
                "document_provenance_summary": {
                    "summary_fact_count": 2,
                    "claim_supporting_fact_count": 3,
                },
            },
            "drafting_readiness": {
                "status": "warning",
                "workflow_phase_plan": {
                    "recommended_order": ["document_generation"],
                    "phases": {
                        "document_generation": {
                            "status": "warning",
                            "summary": "Document generation still needs targeted revision before filing.",
                            "recommended_actions": [
                                "Review claims-for-relief and factual allegations before filing.",
                            ],
                        },
                    },
                },
                "sections": {
                    "claims_for_relief": {
                        "status": "warning",
                        "title": "Claims For Relief",
                    }
                },
                "claims": [
                    {
                        "claim_type": "retaliation",
                        "status": "warning",
                    }
                ],
            },
            "document_optimization": {},
        },
        mediator=mediator,
        user_id="Jane Doe",
    )

    assert payload["review_links"]["document_drafting_next_action"] == {
        "action": "realign_document_drafting",
        "phase_name": "document_generation",
        "description": "Realign drafting to protected_activity before further revisions; the draft loop acted on causation first.",
        "claim_element_id": "protected_activity",
        "executed_claim_element_id": "causation",
        "focus_section": "claims_for_relief",
        "preferred_support_kind": "testimony",
    }
    assert payload["review_links"]["workflow_priority"] == {
        "status": "warning",
        "title": "Realign drafting before further revisions",
        "description": "Realign drafting to protected_activity before further revisions; the draft loop acted on causation first.",
        "action_label": "Open formal complaint builder",
        "action_url": "/claim-support-review?user_id=Jane+Doe&claim_type=retaliation&section=claims_for_relief&follow_up_support_kind=authority",
        "action_kind": "link",
        "dashboard_url": "/claim-support-review?user_id=Jane+Doe",
        "chip_labels": [
            "target element: Protected Activity",
            "executed first: Causation",
            "focus section: Claims For Relief",
            "support lane: Testimony",
        ],
    }
    assert payload["review_links"]["document_provenance_summary"] == {
        "summary_fact_count": 2,
        "claim_supporting_fact_count": 3,
    }
    assert payload["review_links"]["document_focus_preview"] == [
        {
            "section": "factual_allegations",
            "text": "Days after the complaint, Defendant terminated Plaintiff in retaliation.",
            "focus_source": "document_grounding_improvement_next_action",
            "action": "retarget_document_grounding",
            "target_claim_element_id": "causation",
            "original_claim_element_id": "protected_activity",
            "preferred_support_kind": "testimony",
            "priority_rank": 1,
        }
    ]


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
    monkeypatch.setattr(optimizer, '_build_upstream_optimizer_metadata', lambda **kwargs: {'selected_provider': 'test-provider'})
    monkeypatch.setattr(
        optimizer,
        '_build_upstream_optimizer_metadata',
        lambda **kwargs: {'selected_provider': 'test-provider'},
    )
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


def test_build_package_applies_document_drafting_focus_to_claims_for_relief():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "document_drafting_next_action": {
            "action": "realign_document_drafting",
            "phase_name": "document_generation",
            "claim_element_id": "protected_activity",
            "executed_claim_element_id": "causation",
            "focus_section": "claims_for_relief",
            "preferred_support_kind": "testimony",
        }
    }
    builder = FormalComplaintDocumentBuilder(mediator)
    builder.build_draft = Mock(
        return_value={
            "summary_of_facts": ["Plaintiff suffered harm."],
            "claims_for_relief": [
                {
                    "claim_type": "retaliation",
                    "count_title": "Retaliation",
                    "supporting_facts": [
                        "Plaintiff was terminated shortly after the complaint.",
                        "Plaintiff reported discrimination to HR and requested a hearing review.",
                    ],
                },
                {
                    "claim_type": "discrimination",
                    "count_title": "Discrimination",
                    "supporting_facts": [
                        "Plaintiff suffered adverse action.",
                    ],
                },
            ],
        }
    )
    builder._build_drafting_readiness = Mock(
        return_value={"status": "ready", "sections": {}, "claims": [], "warning_count": 0}
    )
    builder._build_runtime_workflow_phase_plan = Mock(return_value={})
    builder._build_filing_checklist = Mock(return_value=[])
    builder._annotate_filing_checklist_review_links = Mock()
    builder._build_affidavit = Mock(return_value={})
    builder._build_claim_support_temporal_handoff = Mock(return_value={})
    builder._build_intake_summary_handoff = Mock(return_value={})
    builder.render_artifacts = Mock(return_value={})

    result = builder.build_package(
        district="Northern District of California",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        output_formats=["txt"],
    )

    draft = result["draft"]
    assert draft["document_drafting_next_action"]["action"] == "realign_document_drafting"
    assert draft["document_drafting_focus_section"] == "claims_for_relief"
    assert draft["document_drafting_focus_claim_element_id"] == "protected_activity"
    assert draft["claims_for_relief"][0]["supporting_facts"][0] == (
        "Plaintiff reported discrimination to HR and requested a hearing review."
    )


def test_build_package_applies_document_drafting_focus_to_factual_allegations():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "document_drafting_next_action": {
            "action": "realign_document_drafting",
            "phase_name": "document_generation",
            "claim_element_id": "causation",
            "executed_claim_element_id": "protected_activity",
            "focus_section": "factual_allegations",
            "preferred_support_kind": "testimony",
        }
    }
    builder = FormalComplaintDocumentBuilder(mediator)
    builder.build_draft = Mock(
        return_value={
            "summary_of_facts": [
                "Plaintiff engaged in protected activity.",
                "Days after the complaint, Defendant terminated Plaintiff in retaliation.",
            ],
            "factual_allegations": [
                "Plaintiff engaged in protected activity.",
                "Days after the complaint, Defendant terminated Plaintiff in retaliation.",
            ],
            "claims_for_relief": [],
        }
    )
    builder._build_drafting_readiness = Mock(
        return_value={"status": "ready", "sections": {}, "claims": [], "warning_count": 0}
    )
    builder._build_runtime_workflow_phase_plan = Mock(return_value={})
    builder._build_filing_checklist = Mock(return_value=[])
    builder._annotate_filing_checklist_review_links = Mock()
    builder._build_affidavit = Mock(return_value={})
    builder._build_claim_support_temporal_handoff = Mock(return_value={})
    builder._build_intake_summary_handoff = Mock(return_value={})
    builder.render_artifacts = Mock(return_value={})

    result = builder.build_package(
        district="Northern District of California",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        output_formats=["txt"],
    )

    draft = result["draft"]
    assert draft["document_drafting_focus_section"] == "factual_allegations"
    assert draft["factual_allegations"][0] == (
        "Days after the complaint, Defendant terminated Plaintiff in retaliation."
    )


def test_build_package_uses_grounding_retarget_action_for_initial_focus():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "document_grounding_improvement_next_action": {
            "action": "retarget_document_grounding",
            "phase_name": "document_generation",
            "claim_element_id": "protected_activity",
            "suggested_claim_element_id": "causation",
            "focus_section": "factual_allegations",
            "preferred_support_kind": "testimony",
        }
    }
    builder = FormalComplaintDocumentBuilder(mediator)
    builder.build_draft = Mock(
        return_value={
            "summary_of_facts": [
                "Plaintiff engaged in protected activity.",
                "Days after the complaint, Defendant terminated Plaintiff in retaliation.",
            ],
            "factual_allegations": [
                "Plaintiff engaged in protected activity.",
                "Days after the complaint, Defendant terminated Plaintiff in retaliation.",
            ],
            "claims_for_relief": [],
        }
    )
    builder._build_drafting_readiness = Mock(
        return_value={"status": "ready", "sections": {}, "claims": [], "warning_count": 0}
    )
    builder._build_runtime_workflow_phase_plan = Mock(return_value={})
    builder._build_filing_checklist = Mock(return_value=[])
    builder._annotate_filing_checklist_review_links = Mock()
    builder._build_affidavit = Mock(return_value={})
    builder._build_claim_support_temporal_handoff = Mock(return_value={})
    builder._build_intake_summary_handoff = Mock(return_value={})
    builder.render_artifacts = Mock(return_value={})

    result = builder.build_package(
        district="Northern District of California",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        output_formats=["txt"],
    )

    draft = result["draft"]
    assert draft["document_grounding_improvement_next_action"]["action"] == "retarget_document_grounding"
    assert draft["document_drafting_focus_source"] == "document_grounding_improvement_next_action"
    assert draft["document_drafting_focus_claim_element_id"] == "causation"
    assert draft["summary_of_fact_entries"][0]["document_focus"]["focus_source"] == "document_grounding_improvement_next_action"
    assert draft["summary_of_fact_entries"][0]["document_focus"]["original_claim_element_id"] == "protected_activity"
    assert draft["summary_of_fact_entries"][0]["document_focus"]["target_claim_element_id"] == "causation"
    assert draft["factual_allegation_paragraphs"][0]["document_focus"]["focus_source"] == "document_grounding_improvement_next_action"
    assert draft["factual_allegations"][0] == (
        "Days after the complaint, Defendant terminated Plaintiff in retaliation."
    )


def test_build_package_uses_claim_registry_keywords_for_document_drafting_focus():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "document_drafting_next_action": {
            "action": "realign_document_drafting",
            "phase_name": "document_generation",
            "claim_element_id": "protected_trait",
            "executed_claim_element_id": "adverse_action",
            "focus_section": "claims_for_relief",
            "preferred_support_kind": "personnel_record",
        }
    }
    builder = FormalComplaintDocumentBuilder(mediator)
    builder.build_draft = Mock(
        return_value={
            "claims_for_relief": [
                {
                    "claim_type": "employment_discrimination",
                    "count_title": "Employment Discrimination",
                    "supporting_facts": [
                        "Plaintiff was terminated after the investigation.",
                        "Plaintiff is Black and disclosed that protected trait to HR.",
                    ],
                },
                {
                    "claim_type": "retaliation",
                    "count_title": "Retaliation",
                    "supporting_facts": [
                        "Plaintiff complained to HR and was later terminated.",
                    ],
                },
            ],
        }
    )
    builder._build_drafting_readiness = Mock(
        return_value={"status": "ready", "sections": {}, "claims": [], "warning_count": 0}
    )
    builder._build_runtime_workflow_phase_plan = Mock(return_value={})
    builder._build_filing_checklist = Mock(return_value=[])
    builder._annotate_filing_checklist_review_links = Mock()
    builder._build_affidavit = Mock(return_value={})
    builder._build_claim_support_temporal_handoff = Mock(return_value={})
    builder._build_intake_summary_handoff = Mock(return_value={})
    builder.render_artifacts = Mock(return_value={})

    result = builder.build_package(
        district="Northern District of California",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        output_formats=["txt"],
    )

    draft = result["draft"]
    assert draft["claims_for_relief"][0]["claim_type"] == "employment_discrimination"
    assert draft["claims_for_relief"][0]["supporting_facts"][0] == (
        "Plaintiff is Black and disclosed that protected trait to HR."
    )


def test_build_package_uses_claim_support_packets_to_resolve_document_focus_claim():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "document_drafting_next_action": {
            "action": "realign_document_drafting",
            "phase_name": "document_generation",
            "claim_element_id": "protected_activity",
            "executed_claim_element_id": "causation",
            "focus_section": "claims_for_relief",
            "preferred_support_kind": "testimony",
        }
    }
    mediator.phase_manager = Mock()
    mediator.phase_manager.get_phase_data.side_effect = lambda phase, key: (
        {
            "retaliation": {
                "claim_type": "retaliation",
                "elements": [
                    {
                        "element_id": "protected_activity",
                        "element_text": "Protected activity",
                        "support_status": "partially_supported",
                        "preferred_evidence_classes": ["complaint_record", "timeline_record"],
                        "required_fact_bundle": ["protected_activity", "timeline"],
                        "missing_fact_bundle": ["timeline"],
                    }
                ],
            }
        }
        if key == "claim_support_packets"
        else {}
    )
    builder = FormalComplaintDocumentBuilder(mediator)
    builder.build_draft = Mock(
        return_value={
            "claims_for_relief": [
                {
                    "claim_type": "discrimination",
                    "count_title": "Discrimination",
                    "supporting_facts": [
                        "Plaintiff was treated unfairly.",
                    ],
                },
                {
                    "claim_type": "retaliation",
                    "count_title": "Retaliation",
                    "supporting_facts": [
                        "Plaintiff engaged in activity and later experienced consequences.",
                    ],
                },
            ],
        }
    )
    builder._build_drafting_readiness = Mock(
        return_value={"status": "ready", "sections": {}, "claims": [], "warning_count": 0}
    )
    builder._build_runtime_workflow_phase_plan = Mock(return_value={})
    builder._build_filing_checklist = Mock(return_value=[])
    builder._annotate_filing_checklist_review_links = Mock()
    builder._build_affidavit = Mock(return_value={})
    builder._build_claim_support_temporal_handoff = Mock(return_value={})
    builder._build_intake_summary_handoff = Mock(return_value={})
    builder.render_artifacts = Mock(return_value={})

    result = builder.build_package(
        district="Northern District of California",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        output_formats=["txt"],
    )

    draft = result["draft"]
    assert draft["claims_for_relief"][0]["claim_type"] == "retaliation"


def test_build_summary_fact_entries_include_canonical_fact_provenance():
    mediator = _build_seeded_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)

    entries = builder._build_summary_fact_entries(
        generated_complaint={},
        classification={},
        state=mediator.state,
    )

    protected_activity_entry = next(
        entry for entry in entries if entry["text"].startswith("Plaintiff reported repeated sexual harassment")
    )
    assert protected_activity_entry["fact_ids"] == ["fact:1"]
    assert protected_activity_entry["claim_element_ids"] == ["protected_activity"]
    assert protected_activity_entry["source_kind"] == "canonical_fact"


def test_build_package_prioritizes_supporting_fact_entries_with_matching_packet_fact_ids():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "document_drafting_next_action": {
            "action": "realign_document_drafting",
            "phase_name": "document_generation",
            "claim_element_id": "protected_activity",
            "executed_claim_element_id": "causation",
            "focus_section": "claims_for_relief",
            "preferred_support_kind": "testimony",
        }
    }
    mediator.phase_manager = Mock()
    mediator.phase_manager.get_phase_data.side_effect = lambda phase, key: (
        {
            "retaliation": {
                "claim_type": "retaliation",
                "elements": [
                    {
                        "element_id": "protected_activity",
                        "element_text": "Protected activity",
                        "support_status": "partially_supported",
                        "canonical_fact_ids": ["fact:protected"],
                    }
                ],
            }
        }
        if key == "claim_support_packets"
        else {}
    )
    builder = FormalComplaintDocumentBuilder(mediator)
    builder.build_draft = Mock(
        return_value={
            "claims_for_relief": [
                {
                    "claim_type": "retaliation",
                    "count_title": "Retaliation",
                    "supporting_facts": [
                        "Plaintiff was terminated shortly after the complaint.",
                        "Plaintiff engaged in protected conduct before the termination.",
                    ],
                    "supporting_fact_entries": [
                        {
                            "text": "Plaintiff was terminated shortly after the complaint.",
                            "fact_ids": ["fact:adverse"],
                        },
                        {
                            "text": "Plaintiff engaged in protected conduct before the termination.",
                            "fact_ids": ["fact:protected"],
                        },
                    ],
                }
            ],
        }
    )
    builder._build_drafting_readiness = Mock(
        return_value={"status": "ready", "sections": {}, "claims": [], "warning_count": 0}
    )
    builder._build_runtime_workflow_phase_plan = Mock(return_value={})
    builder._build_filing_checklist = Mock(return_value=[])
    builder._annotate_filing_checklist_review_links = Mock()
    builder._build_affidavit = Mock(return_value={})
    builder._build_claim_support_temporal_handoff = Mock(return_value={})
    builder._build_intake_summary_handoff = Mock(return_value={})
    builder.render_artifacts = Mock(return_value={})

    result = builder.build_package(
        district="Northern District of California",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        output_formats=["txt"],
    )

    draft = result["draft"]
    assert draft["claims_for_relief"][0]["supporting_facts"][0] == (
        "Plaintiff engaged in protected conduct before the termination."
    )
    assert draft["claims_for_relief"][0]["supporting_fact_entries"][0]["fact_ids"] == ["fact:protected"]


def test_build_package_adds_claim_support_provenance_and_document_provenance_summary():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {}
    builder = FormalComplaintDocumentBuilder(mediator)
    builder.build_draft = Mock(
        return_value={
            "summary_of_facts": [
                "Plaintiff reported discrimination to HR.",
            ],
            "summary_of_fact_entries": [
                {
                    "text": "Plaintiff reported discrimination to HR.",
                    "fact_ids": ["fact:summary:1"],
                    "source_artifact_ids": ["artifact:hr-complaint"],
                }
            ],
            "factual_allegations": [
                "Plaintiff reported discrimination to HR.",
            ],
            "factual_allegation_entries": [
                {
                    "text": "Plaintiff reported discrimination to HR.",
                    "fact_ids": ["fact:summary:1"],
                    "source_artifact_ids": ["artifact:hr-complaint"],
                    "claim_element_ids": ["protected_activity"],
                }
            ],
            "claims_for_relief": [
                {
                    "claim_type": "retaliation",
                    "count_title": "Retaliation",
                    "supporting_facts": [
                        "Plaintiff reported discrimination to HR.",
                    ],
                    "supporting_fact_entries": [
                        {
                            "text": "Plaintiff reported discrimination to HR.",
                            "fact_ids": ["fact:summary:1"],
                            "source_artifact_ids": ["artifact:hr-complaint"],
                            "claim_element_ids": ["protected_activity"],
                            "support_trace_ids": ["trace:1"],
                        }
                    ],
                }
            ],
        }
    )
    builder._build_drafting_readiness = Mock(
        return_value={"status": "ready", "sections": {}, "claims": [], "warning_count": 0}
    )
    builder._build_runtime_workflow_phase_plan = Mock(return_value={})
    builder._build_filing_checklist = Mock(return_value=[])
    builder._annotate_filing_checklist_review_links = Mock()
    builder._build_affidavit = Mock(return_value={})
    builder._build_claim_support_temporal_handoff = Mock(return_value={})
    builder._build_intake_summary_handoff = Mock(return_value={})
    builder.render_artifacts = Mock(return_value={})

    result = builder.build_package(
        district="Northern District of California",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        output_formats=["txt"],
    )

    draft = result["draft"]
    assert draft["claims_for_relief"][0]["supporting_fact_provenance"][0]["fact_ids"] == ["fact:summary:1"]
    assert draft["claims_for_relief"][0]["supporting_fact_provenance"][0]["support_trace_ids"] == ["trace:1"]
    assert draft["factual_allegation_paragraphs"][0]["fact_ids"] == ["fact:summary:1"]
    assert draft["document_provenance_summary"] == {
        "summary_fact_count": 1,
        "summary_fact_backed_count": 1,
        "summary_fact_exhibit_backed_count": 0,
        "factual_allegation_paragraph_count": 1,
        "factual_allegation_fact_backed_count": 1,
        "factual_allegation_exhibit_backed_count": 0,
        "claim_count": 1,
        "claim_supporting_fact_count": 1,
        "claim_supporting_fact_backed_count": 1,
        "claim_supporting_fact_exhibit_backed_count": 0,
        "fact_id_count": 1,
        "source_artifact_id_count": 1,
        "fact_backed_ratio": 1.0,
        "low_grounding_flag": False,
        "focused_entry_count": 0,
        "focus_source_counts": {},
        "claims": [
            {
                "claim_type": "retaliation",
                "supporting_fact_count": 1,
                "fact_backed_supporting_fact_count": 1,
                "artifact_backed_supporting_fact_count": 1,
                "exhibit_backed_supporting_fact_count": 0,
                "fact_ids": ["fact:summary:1"],
                "source_artifact_ids": ["artifact:hr-complaint"],
            }
        ],
    }
    assert result["document_provenance_summary"] == draft["document_provenance_summary"]


def test_document_api_annotation_prioritizes_document_provenance_grounding_warning():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "formalization",
        "intake_readiness": {
            "score": 0.9,
            "ready_to_advance": True,
            "remaining_gap_count": 0,
            "contradiction_count": 0,
            "criteria": {},
            "blockers": [],
            "contradictions": [],
        },
        "next_action": {"action": "complete_evidence"},
    }
    payload = _annotate_review_links(
        {
            "draft": {
                "title": "Jane Doe v. Acme Corporation",
                "source_context": {"user_id": "Jane Doe"},
                "document_provenance_summary": {
                    "summary_fact_count": 4,
                    "summary_fact_backed_count": 1,
                    "claim_supporting_fact_count": 3,
                    "claim_supporting_fact_backed_count": 1,
                    "fact_backed_ratio": 0.33,
                    "low_grounding_flag": True,
                },
            },
            "drafting_readiness": {
                "status": "warning",
                "workflow_phase_plan": {"recommended_order": ["document_generation"], "phases": {}},
                "sections": {"factual_allegations": {"status": "warning", "title": "Factual Allegations"}},
                "claims": [{"claim_type": "retaliation", "status": "warning"}],
            },
            "document_optimization": {},
        },
        mediator=mediator,
        user_id="Jane Doe",
    )

    assert payload["review_links"]["workflow_priority"] == {
        "status": "warning",
        "title": "Strengthen document grounding before further revisions",
        "description": "Increase canonical-fact and artifact-backed support in the draft before broadening revisions.",
        "action_label": "Review factual allegations grounding",
        "action_url": "/claim-support-review?user_id=Jane+Doe&section=factual_allegations",
        "action_kind": "link",
        "dashboard_url": "/claim-support-review?user_id=Jane+Doe",
        "chip_labels": [
            "fact-backed ratio: 0.33",
            "summary facts grounded: 1/4",
            "claim support grounded: 1/3",
        ],
    }


def test_document_api_annotation_promotes_document_grounding_recovery_action_into_workflow_priority():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "formalization",
        "intake_readiness": {
            "score": 0.5,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "blockers": [],
            "criteria": {},
        },
        "document_provenance_summary": {"fact_backed_ratio": 0.25, "low_grounding_flag": True},
        "document_grounding_recovery_action": {
            "action": "recover_document_grounding",
            "phase_name": "document_generation",
            "description": "Strengthen draft grounding for protected_activity before formalization.",
            "claim_type": "retaliation",
            "claim_element_id": "protected_activity",
            "focus_section": "factual_allegations",
            "preferred_support_kind": "authority",
            "fact_backed_ratio": 0.25,
            "missing_fact_bundle": ["Complaint timing", "Manager knowledge"],
            "recovery_source": "alignment_evidence_task",
        },
        "next_action": {"action": "complete_evidence"},
    }
    payload = _annotate_review_links(
        {
            "draft": {
                "title": "Jane Doe v. Acme Corporation",
                "source_context": {"user_id": "Jane Doe"},
                "document_provenance_summary": {
                    "summary_fact_count": 4,
                    "summary_fact_backed_count": 1,
                    "claim_supporting_fact_count": 3,
                    "claim_supporting_fact_backed_count": 1,
                    "fact_backed_ratio": 0.25,
                    "low_grounding_flag": True,
                },
            },
            "drafting_readiness": {
                "status": "warning",
                "workflow_phase_plan": {"recommended_order": ["document_generation"], "phases": {}},
                "sections": {"factual_allegations": {"status": "warning", "title": "Factual Allegations"}},
                "claims": [{"claim_type": "retaliation", "status": "warning"}],
            },
            "document_optimization": {},
        },
        mediator=mediator,
        user_id="Jane Doe",
    )

    assert payload["review_links"]["document_grounding_recovery_action"] == {
        "action": "recover_document_grounding",
        "phase_name": "document_generation",
        "description": "Strengthen draft grounding for protected_activity before formalization.",
        "claim_type": "retaliation",
        "claim_element_id": "protected_activity",
        "focus_section": "factual_allegations",
        "preferred_support_kind": "authority",
        "fact_backed_ratio": 0.25,
        "missing_fact_bundle": ["Complaint timing", "Manager knowledge"],
        "recovery_source": "alignment_evidence_task",
    }


def test_document_api_annotation_promotes_document_grounding_improvement_next_action_into_workflow_priority():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "formalization",
        "intake_readiness": {
            "score": 0.5,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "blockers": [],
            "criteria": {},
        },
        "document_provenance_summary": {"fact_backed_ratio": 0.25, "low_grounding_flag": True},
        "document_grounding_improvement_summary": {
            "initial_fact_backed_ratio": 0.25,
            "final_fact_backed_ratio": 0.25,
            "fact_backed_ratio_delta": 0.0,
            "stalled_flag": True,
            "targeted_claim_elements": ["protected_activity"],
            "preferred_support_kinds": ["authority"],
            "recovery_attempted_flag": True,
        },
        "document_grounding_lane_outcome_summary": {
            "attempted_support_kind": "authority",
            "outcome_status": "stalled",
            "recommended_future_support_kind": "testimony",
        },
        "document_grounding_recovery_action": {
            "action": "recover_document_grounding",
            "phase_name": "document_generation",
            "description": "Strengthen draft grounding for protected_activity before formalization.",
            "claim_type": "retaliation",
            "claim_element_id": "protected_activity",
            "focus_section": "factual_allegations",
            "preferred_support_kind": "authority",
            "fact_backed_ratio": 0.25,
            "missing_fact_bundle": ["Complaint timing"],
            "recovery_source": "alignment_evidence_task",
        },
        "next_action": {"action": "complete_evidence"},
    }
    payload = _annotate_review_links(
        {
            "draft": {
                "title": "Jane Doe v. Acme Corporation",
                "source_context": {"user_id": "Jane Doe"},
                "document_provenance_summary": {
                    "summary_fact_count": 4,
                    "summary_fact_backed_count": 1,
                    "claim_supporting_fact_count": 3,
                    "claim_supporting_fact_backed_count": 1,
                    "fact_backed_ratio": 0.25,
                    "low_grounding_flag": True,
                },
            },
            "drafting_readiness": {
                "status": "warning",
                "workflow_phase_plan": {"recommended_order": ["document_generation"], "phases": {}},
                "sections": {"factual_allegations": {"status": "warning", "title": "Factual Allegations"}},
                "claims": [{"claim_type": "retaliation", "status": "warning"}],
            },
            "document_optimization": {},
        },
        mediator=mediator,
        user_id="Jane Doe",
    )

    assert payload["review_links"]["document_grounding_improvement_next_action"] == {
        "action": "refine_document_grounding_strategy",
        "phase_name": "document_generation",
        "description": "Grounding recovery stalled; switch support lanes or retarget the next grounding cycle for protected_activity by trying testimony instead of authority.",
        "status": "stalled",
        "claim_type": "retaliation",
        "claim_element_id": "protected_activity",
        "focus_section": "factual_allegations",
        "preferred_support_kind": "authority",
        "suggested_support_kind": "testimony",
        "alternate_support_kinds": ["testimony", "evidence"],
        "initial_fact_backed_ratio": 0.25,
        "final_fact_backed_ratio": 0.25,
        "fact_backed_ratio_delta": 0.0,
        "recovery_attempted_flag": True,
        "targeted_claim_elements": ["protected_activity"],
        "preferred_support_kinds": ["authority"],
        "learned_support_kind": "testimony",
        "learned_support_lane_attempted_flag": False,
        "learned_support_lane_effective_flag": False,
    }
    assert payload["review_links"]["document_grounding_lane_outcome_summary"] == {
        "attempted_support_kind": "authority",
        "outcome_status": "stalled",
        "recommended_future_support_kind": "testimony",
    }
    assert payload["review_links"]["workflow_priority"] == {
        "status": "warning",
        "title": "Refine document grounding strategy",
        "description": "Grounding recovery stalled; switch support lanes or retarget the next grounding cycle for protected_activity by trying testimony instead of authority. Learned lane preference now favors Testimony.",
        "action_label": "Review grounding strategy",
        "action_url": "/claim-support-review?user_id=Jane+Doe&claim_type=retaliation&section=factual_allegations&follow_up_support_kind=testimony",
        "action_kind": "link",
        "dashboard_url": "/claim-support-review?user_id=Jane+Doe",
        "chip_labels": [
            "grounding status: Stalled",
            "target element: Protected Activity",
            "current support lane: Authority",
            "learned next lane: Testimony",
            "grounding delta: +0.00",
        ],
    }


def test_document_api_annotation_promotes_document_grounding_retargeting_into_workflow_priority():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "formalization",
        "intake_readiness": {
            "score": 0.5,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "blockers": [],
            "criteria": {},
        },
        "document_provenance_summary": {"fact_backed_ratio": 0.25, "low_grounding_flag": True},
        "document_grounding_improvement_summary": {
            "initial_fact_backed_ratio": 0.25,
            "final_fact_backed_ratio": 0.2,
            "fact_backed_ratio_delta": -0.05,
            "regressed_flag": True,
            "targeted_claim_elements": ["protected_activity"],
            "preferred_support_kinds": ["authority"],
            "recovery_attempted_flag": True,
        },
        "document_grounding_lane_outcome_summary": {
            "attempted_support_kind": "testimony",
            "outcome_status": "regressed",
            "recommended_future_support_kind": "testimony",
            "recommended_future_claim_element": "causation",
            "learned_support_lane_attempted_flag": True,
            "learned_support_lane_effective_flag": False,
        },
        "document_grounding_recovery_action": {
            "action": "recover_document_grounding",
            "phase_name": "document_generation",
            "description": "Strengthen draft grounding for protected_activity before formalization.",
            "claim_type": "retaliation",
            "claim_element_id": "protected_activity",
            "focus_section": "factual_allegations",
            "preferred_support_kind": "authority",
            "fact_backed_ratio": 0.25,
            "missing_fact_bundle": ["Complaint timing"],
            "recovery_source": "alignment_evidence_task",
        },
        "next_action": {"action": "complete_evidence"},
    }
    payload = _annotate_review_links(
        {
            "draft": {
                "title": "Jane Doe v. Acme Corporation",
                "source_context": {"user_id": "Jane Doe"},
                "document_provenance_summary": {
                    "summary_fact_count": 4,
                    "summary_fact_backed_count": 1,
                    "claim_supporting_fact_count": 3,
                    "claim_supporting_fact_backed_count": 1,
                    "fact_backed_ratio": 0.25,
                    "low_grounding_flag": True,
                },
            },
            "drafting_readiness": {
                "status": "warning",
                "workflow_phase_plan": {"recommended_order": ["document_generation"], "phases": {}},
                "sections": {"factual_allegations": {"status": "warning", "title": "Factual Allegations"}},
                "claims": [{"claim_type": "retaliation", "status": "warning"}],
            },
            "document_optimization": {},
        },
        mediator=mediator,
        user_id="Jane Doe",
    )

    assert payload["review_links"]["document_grounding_improvement_next_action"]["action"] == "retarget_document_grounding"
    assert payload["review_links"]["document_grounding_improvement_next_action"]["suggested_claim_element_id"] == "causation"
    assert payload["review_links"]["workflow_priority"]["title"] == "Retarget document grounding"
    assert payload["review_links"]["workflow_priority"]["action_label"] == "Review grounding retargeting"
    assert "next target element: Causation" in payload["review_links"]["workflow_priority"]["chip_labels"]


def test_document_optimizer_prioritizes_graph_phase_for_unresolved_blockers():
    optimizer = document_optimization.AgenticDocumentOptimizer(
        mediator=_build_seeded_mediator(),
        max_iterations=1,
        target_score=0.95,
        persist_artifacts=False,
    )

    review = optimizer._heuristic_review(
        draft={
            'title': 'Jane Doe v. Acme Corporation',
            'factual_allegations': ['Defendant denied assistance.'],
            'claims_for_relief': [{'claim_type': 'retaliation', 'supporting_facts': []}],
            'requested_relief': ['Compensatory damages.'],
            'affidavit': {
                'intro': 'I make this affidavit from personal knowledge.',
                'facts': ['Defendant denied assistance.'],
                'jurat': 'Subscribed and sworn.',
                'supporting_exhibits': [{'label': 'Exhibit A'}],
            },
            'certificate_of_service': {
                'text': 'I certify service on Defendant.',
                'recipients': ['Defense Counsel'],
                'recipient_details': [{'recipient': 'Defense Counsel', 'method': 'Email'}],
                'dated': '2026-03-20',
            },
        },
        drafting_readiness={'status': 'warning', 'sections': {}},
        support_context={
            'claims': [],
            'evidence': [],
            'packet_projection': {
                'section_presence': {
                    'nature_of_action': True,
                    'summary_of_facts': True,
                    'factual_allegations': True,
                    'claims_for_relief': True,
                    'requested_relief': True,
                },
                'section_counts': {
                    'nature_of_action': 1,
                    'summary_of_facts': 1,
                    'factual_allegations': 1,
                    'claims_for_relief': 1,
                    'requested_relief': 1,
                },
                'has_affidavit': True,
                'has_certificate_of_service': True,
            },
            'intake_priorities': {
                'uncovered_objectives': ['exact_dates', 'staff_names_titles', 'response_dates'],
                'critical_unresolved_objectives': ['exact_dates', 'staff_names_titles', 'response_dates'],
                'unresolved_objectives': ['exact_dates', 'staff_names_titles', 'response_dates'],
                'objective_question_counts': {'exact_dates': 0, 'staff_names_titles': 0, 'response_dates': 0},
            },
        },
    )

    assert review['prioritized_workflow_phase'] == 'graph_analysis'
    assert review['workflow_phase_order'][0] == 'graph_analysis'
    assert review['workflow_phase_target_sections']['graph_analysis'] == 'factual_allegations'
    assert review['recommended_focus'] == 'factual_allegations'


def test_drafting_readiness_flags_low_document_grounding_for_formalization():
    mediator = _build_seeded_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)

    draft = {
        "source_context": {"claim_types": ["retaliation"]},
        "summary_of_facts": ["Plaintiff reported harassment.", "Plaintiff was terminated."],
        "claims_for_relief": [
            {
                "claim_type": "retaliation",
                "supporting_facts": ["Plaintiff engaged in protected activity."],
            }
        ],
        "requested_relief": ["Compensatory damages."],
        "jurisdiction_statement": ["Jurisdiction is proper."],
        "venue_statement": ["Venue is proper."],
        "exhibits": [],
        "document_provenance_summary": {
            "summary_fact_count": 2,
            "summary_fact_backed_count": 0,
            "factual_allegation_paragraph_count": 0,
            "factual_allegation_fact_backed_count": 0,
            "claim_count": 1,
            "claim_supporting_fact_count": 1,
            "claim_supporting_fact_backed_count": 0,
            "fact_id_count": 0,
            "source_artifact_id_count": 0,
            "fact_backed_ratio": 0.0,
            "low_grounding_flag": True,
            "claims": [],
        },
    }

    readiness = builder._build_drafting_readiness(user_id="Jane Doe", draft=draft)

    assert readiness["document_low_grounding_flag"] is True
    assert readiness["document_fact_backed_ratio"] == 0.0
    assert "document_provenance_grounding_needed" in readiness["blockers"]
    assert any(
        warning["code"] == "document_provenance_grounding_thin"
        for warning in readiness["sections"]["summary_of_facts"]["warnings"]
    )

    gate = builder._build_formalization_gate_payload(readiness)
    assert gate["document_low_grounding_flag"] is True
    assert gate["document_fact_backed_ratio"] == 0.0
    assert gate["ready_for_formalization"] is False


def test_build_support_context_carries_blocker_metadata_from_intake_case_file():
    mediator = _build_seeded_mediator()
    optimizer = document_optimization.AgenticDocumentOptimizer(mediator=mediator)

    support_context = optimizer._build_support_context(
        user_id='Jane Doe',
        draft={
            'claims_for_relief': [{'claim_type': 'retaliation', 'support_summary': {}}],
        },
        drafting_readiness={'status': 'warning', 'claims': [], 'sections': {}},
    )

    priorities = support_context['intake_priorities']
    assert priorities['blocker_count'] == 1
    assert priorities['blocking_objectives'] == ['exact_dates', 'response_dates']
    assert priorities['blocker_extraction_targets'] == ['timeline_anchors', 'response_timeline']
    assert priorities['blocker_workflow_phases'] == ['graph_analysis', 'intake_questioning', 'document_generation']
    assert priorities['blocker_issue_families'] == ['response_timeline']
    assert priorities['anchored_chronology_summary'] == [
        'Protected activity on January 5, 2026 preceded adverse action on January 20, 2026.'
    ]
    assert priorities['temporal_issue_count'] == 0
    assert any('Response or non-response events are described without date anchors.' in prompt for prompt in priorities['recommended_follow_up_prompts'])


def test_build_support_context_projects_claim_temporal_gap_hints():
    mediator = _build_seeded_mediator()
    intake_case_file = dict(mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {})
    intake_case_file['temporal_issue_registry'] = [
        {
            'summary': 'Timeline fact fact:2 only has relative ordering and still needs anchoring.',
            'status': 'open',
            'claim_types': ['retaliation'],
            'element_tags': ['causation'],
        }
    ]
    intake_case_file['blocker_follow_up_summary'] = {
        'blocking_items': [
            {
                'reason': 'Protected activity and adverse action still need tighter causation sequencing.',
                'primary_objective': 'causation_sequence',
                'blocker_objectives': ['causation_sequence', 'exact_dates'],
                'issue_family': 'causation',
            }
        ]
    }
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', intake_case_file)
    optimizer = document_optimization.AgenticDocumentOptimizer(mediator=mediator)

    support_context = optimizer._build_support_context(
        user_id='Jane Doe',
        draft={
            'claims_for_relief': [{'claim_type': 'retaliation', 'support_summary': {}}],
        },
        drafting_readiness={'status': 'warning', 'claims': [], 'sections': {}},
    )

    claim_context = support_context['claims'][0]
    assert 'Chronology gap: Timeline fact fact:2 only has relative ordering and still needs anchoring.' in claim_context['missing_elements']
    assert 'Chronology gap: Protected activity and adverse action still need tighter causation sequencing.' in claim_context['missing_elements']
    assert claim_context['support_summary']['temporal_gap_hint_count'] == 2
    assert support_context['intake_priorities']['claim_temporal_gap_count'] == 2
    assert support_context['intake_priorities']['claim_temporal_gap_summary'] == [
        {
            'claim_type': 'retaliation',
            'gap_count': 2,
            'gaps': [
                'Chronology gap: Timeline fact fact:2 only has relative ordering and still needs anchoring.',
                'Chronology gap: Protected activity and adverse action still need tighter causation sequencing.',
            ],
        }
    ]


def test_build_support_context_preserves_resolved_temporal_history_without_open_gap_penalty():
    mediator = _build_seeded_mediator()
    intake_case_file = dict(mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {})
    intake_case_file['temporal_issue_registry'] = [
        {
            'issue_id': 'timeline-gap-resolved-001',
            'summary': 'Protected activity and adverse action were previously missing exact chronology anchors.',
            'status': 'resolved',
            'current_resolution_status': 'resolved',
            'claim_types': ['retaliation'],
            'element_tags': ['causation'],
        }
    ]
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', intake_case_file)
    optimizer = document_optimization.AgenticDocumentOptimizer(mediator=mediator)

    support_context = optimizer._build_support_context(
        user_id='Jane Doe',
        draft={
            'claims_for_relief': [{'claim_type': 'retaliation', 'support_summary': {}}],
        },
        drafting_readiness={'status': 'warning', 'claims': [], 'sections': {}},
    )

    priorities = support_context['intake_priorities']
    assert priorities['temporal_issue_count'] == 1
    assert priorities['unresolved_temporal_issue_count'] == 0
    assert priorities['resolved_temporal_issue_count'] == 1
    assert priorities['temporal_issue_status_counts'] == {'resolved': 1}


def test_score_intake_questioning_treats_resolved_temporal_history_as_context_not_open_gap():
    optimizer = document_optimization.AgenticDocumentOptimizer(mediator=_build_seeded_mediator())
    factual_allegations = [
        'On January 5, 2026, Plaintiff reported repeated sexual harassment to management.',
        'On January 20, 2026, Defendant terminated Plaintiff after she made the report.',
    ]

    resolved_history_score = optimizer._score_intake_questioning(
        factual_allegations=factual_allegations,
        support_context={
            'intake_priorities': {
                'covered_objectives': [],
                'uncovered_objectives': [],
                'unresolved_objectives': [],
                'objective_question_counts': {},
                'anchored_chronology_summary': ['Protected activity on January 5, 2026 preceded adverse action on January 20, 2026.'],
                'temporal_issue_count': 1,
                'unresolved_temporal_issue_count': 0,
                'resolved_temporal_issue_count': 1,
            }
        },
    )
    open_gap_score = optimizer._score_intake_questioning(
        factual_allegations=factual_allegations,
        support_context={
            'intake_priorities': {
                'covered_objectives': [],
                'uncovered_objectives': [],
                'unresolved_objectives': [],
                'objective_question_counts': {},
                'anchored_chronology_summary': [],
                'temporal_issue_count': 1,
                'unresolved_temporal_issue_count': 1,
                'resolved_temporal_issue_count': 0,
            }
        },
    )

    assert resolved_history_score > open_gap_score


def test_workflow_optimization_guidance_surfaces_resolved_chronology_history():
    optimizer = document_optimization.AgenticDocumentOptimizer(mediator=_build_seeded_mediator())

    guidance = optimizer._build_workflow_optimization_guidance(
        drafting_readiness={'status': 'ready', 'warnings': [], 'sections': {}},
        support_context={
            'claims': [{'claim_type': 'retaliation', 'missing_elements': [], 'partially_supported_elements': []}],
            'evidence': [{'type': 'document'}],
            'intake_priorities': {'uncovered_objectives': []},
        },
        intake_status={'phase': ComplaintPhase.FORMALIZATION.value, 'ready_to_advance': True},
        intake_case_summary={
            'candidate_claims': [{'claim_type': 'retaliation'}],
            'intake_sections': {},
            'question_candidate_summary': {},
            'proof_lead_summary': {},
            'temporal_issue_registry_summary': {
                'count': 1,
                'issues': [
                    {
                        'issue_id': 'timeline-gap-resolved-001',
                        'status': 'resolved',
                        'current_resolution_status': 'resolved',
                    }
                ],
                'status_counts': {'resolved': 1},
                'resolved_count': 1,
                'unresolved_count': 0,
            },
        },
        claim_reasoning_review={},
        claim_support_temporal_handoff={},
    )

    assert guidance['phase_scorecards']['graph_analysis']['unresolved_temporal_issue_count'] == 0
    assert guidance['phase_scorecards']['graph_analysis']['resolved_temporal_issue_count'] == 1
    assert guidance['cross_phase_findings'] == [
        'Resolved chronology history is retained and should still be preserved in factual allegations and claim support to maintain the causation sequence.'
    ]


def test_document_review_workflow_phase_priority_surfaces_resolved_chronology_history():
    mediator = _build_seeded_mediator()
    intake_case_file = dict(mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {})
    intake_case_file['temporal_issue_registry'] = [
        {
            'issue_id': 'timeline-gap-open-001',
            'summary': 'Adverse action chronology still needs tighter anchoring.',
            'status': 'open',
            'claim_types': ['retaliation'],
        },
        {
            'issue_id': 'timeline-gap-resolved-001',
            'summary': 'Protected activity chronology was resolved from newly submitted records.',
            'status': 'resolved',
            'current_resolution_status': 'resolved',
            'claim_types': ['retaliation'],
        },
    ]
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', intake_case_file)

    payload = _annotate_review_links(
        {
            'draft': {
                'title': 'Jane Doe v. Acme Corporation',
                'claims_for_relief': [{'claim_type': 'retaliation', 'count_title': 'Count I - Retaliation'}],
                'drafting_readiness': {
                    'status': 'warning',
                    'sections': {'claims_for_relief': {'status': 'warning', 'title': 'Claims For Relief'}},
                    'claims': [{'claim_type': 'retaliation', 'status': 'warning'}],
                },
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
                            ],
                        },
                        'document_generation': {
                            'status': 'warning',
                            'summary': 'Document generation should wait until evidence review and packet blockers are reduced further.',
                            'recommended_actions': [],
                        },
                    },
                },
                'sections': {'claims_for_relief': {'status': 'warning', 'title': 'Claims For Relief'}},
                'claims': [{'claim_type': 'retaliation', 'status': 'warning'}],
            },
        },
        mediator=mediator,
        user_id='Jane Doe',
    )

    assert payload['review_links']['workflow_phase_priority']['chip_labels'] == [
        'workflow phase: Graph Analysis',
        'phase status: Warning',
        'recommended action: Resolve remaining intake graph gaps and refresh graph projections before filing.',
        'unresolved chronology issues: 1',
        'resolved chronology issues: 1',
    ]


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
    assert result['draft']['anchored_chronology_summary'] == [
        'Protected activity on January 5, 2026 preceded adverse action on January 20, 2026.'
    ]
    assert result['draft']['claims_for_relief'][0]['supporting_facts'][0] == 'The chronology shows protected activity on January 5, 2026 before adverse action on January 20, 2026.'
    assert 'ANCHORED CHRONOLOGY' in result['draft']['draft_text']


def test_document_package_adds_claim_temporal_gap_hints(tmp_path):
    mediator = _build_seeded_mediator()
    intake_case_file = dict(mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {})
    intake_case_file['temporal_issue_registry'] = [
        {
            'summary': 'Timeline fact fact:2 only has relative ordering and still needs anchoring.',
            'status': 'open',
            'claim_types': ['retaliation'],
            'element_tags': ['causation'],
        }
    ]
    intake_case_file['blocker_follow_up_summary'] = {
        'blocking_items': [
            {
                'reason': 'Protected activity and adverse action still need tighter causation sequencing.',
                'primary_objective': 'causation_sequence',
                'blocker_objectives': ['causation_sequence', 'exact_dates'],
                'issue_family': 'causation',
            }
        ]
    }
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', intake_case_file)
    builder = FormalComplaintDocumentBuilder(mediator)

    result = builder.build_package(
        district='New Mexico',
        county='Santa Fe County',
        plaintiff_names=['Jane Doe'],
        defendant_names=['Acme Corporation'],
        output_dir=str(tmp_path),
        output_formats=['txt'],
    )

    missing_elements = result['draft']['claims_for_relief'][0]['missing_elements']
    assert 'Chronology gap: Timeline fact fact:2 only has relative ordering and still needs anchoring.' in missing_elements
    assert 'Chronology gap: Protected activity and adverse action still need tighter causation sequencing.' in missing_elements
    assert result['draft']['claims_for_relief'][0]['support_summary']['temporal_gap_hint_count'] == 2
    assert result['drafting_readiness']['claims'][0]['temporal_gap_hint_count'] == 2
    assert any(
        warning.get('code') == 'chronology_gaps_present'
        for warning in result['drafting_readiness']['claims'][0]['warnings']
    )


def test_filing_checklist_claim_entries_inherit_claim_chip_labels():
    mediator = _build_seeded_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)

    drafting_readiness = {
        'status': 'warning',
        'sections': {
            'claims_for_relief': {
                'status': 'warning',
                'title': 'Claims for Relief',
                'warnings': [],
            },
        },
        'claims': [
            {
                'claim_type': 'retaliation',
                'status': 'warning',
                'temporal_gap_hint_count': 2,
                'proof_gap_count': 1,
                'warnings': [
                    {
                        'code': 'chronology_gaps_present',
                        'severity': 'warning',
                        'message': 'Retaliation still has 2 chronology gap(s) that should be resolved before filing.',
                    },
                ],
            },
        ],
    }

    filing_checklist = builder._build_filing_checklist(drafting_readiness)
    builder._annotate_filing_checklist_review_links(
        filing_checklist=filing_checklist,
        drafting_readiness=drafting_readiness,
        user_id='Jane Doe',
    )

    claim_item = next(item for item in filing_checklist if item['scope'] == 'claim')
    assert claim_item['review_url'] == '/claim-support-review?user_id=Jane+Doe&claim_type=retaliation'
    assert claim_item['review_context'] == {
        'user_id': 'Jane Doe',
        'claim_type': 'retaliation',
    }
    assert claim_item['chip_labels'] == [
        'claim status: Warning',
        'chronology gaps: 2',
        'proof gaps: 1',
    ]

    section_item = next(item for item in filing_checklist if item['scope'] == 'section')
    assert section_item['review_url'] == '/claim-support-review?user_id=Jane+Doe&section=claims_for_relief'
    assert section_item.get('chip_labels') is None


def test_document_package_uses_claim_reasoning_proof_artifact_chronology_fallback(tmp_path):
    mediator = _build_seeded_mediator()
    intake_case_file = dict(mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {})
    intake_case_file['canonical_facts'] = []
    intake_case_file['timeline_relations'] = []
    intake_case_file['temporal_issue_registry'] = []
    intake_case_file['blocker_follow_up_summary'] = {'blocking_items': []}
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', intake_case_file)
    mediator.get_claim_support_facts = Mock(return_value=[])
    mediator.get_claim_support_validation = Mock(return_value={
        'claims': {
            'retaliation': {
                'claim_type': 'retaliation',
                'elements': [
                    {
                        'element_id': 'retaliation:causation',
                        'element_text': 'Causal connection',
                        'reasoning_diagnostics': {
                            'hybrid_reasoning': {
                                'result': {
                                    'proof_artifact': {
                                        'available': True,
                                        'status': 'available',
                                        'proof_id': 'proof-retaliation-fallback-001',
                                        'proof_status': 'success',
                                        'sentence': 'Protected activity preceded termination',
                                        'theorem_export_metadata': {
                                            'chronology_blocked': True,
                                            'chronology_task_count': 1,
                                            'unresolved_temporal_issue_ids': ['temporal_issue_001'],
                                            'temporal_proof_objectives': ['causation_sequence'],
                                        },
                                    },
                                },
                            },
                        },
                    }
                ],
            }
        }
    })
    draft_builder = ComplaintDocumentBuilder(mediator)
    draft = draft_builder.build(
        district='New Mexico',
        county='Santa Fe County',
        plaintiff_names=['Jane Doe'],
        defendant_names=['Acme Corporation'],
    )

    claim = draft['claims_for_relief'][0]
    assert claim['supporting_facts'][0] == 'Protected activity preceded termination.'
    assert any(
        requirement == {
            'name': 'Chronology gap',
            'citation': '',
            'suggested_action': 'Causal connection still carries 1 unresolved chronology issue(s) and 1 chronology task(s) in the proof handoff. Focus on causation sequence.',
        }
        for requirement in claim['missing_requirements']
    )

    package_builder = FormalComplaintDocumentBuilder(mediator)
    result = package_builder.build_package(
        district='New Mexico',
        county='Santa Fe County',
        plaintiff_names=['Jane Doe'],
        defendant_names=['Acme Corporation'],
        output_dir=str(tmp_path),
        output_formats=['txt'],
    )

    package_claim = result['draft']['claims_for_relief'][0]
    assert package_claim['supporting_facts'][0] == 'Protected activity preceded termination.'
    assert 'Chronology gap' in package_claim['missing_elements']
    assert package_claim['support_summary']['temporal_gap_hint_count'] == 1


def test_legacy_claim_fact_collection_includes_chronology_support():
    mediator = _build_seeded_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)

    claim_facts = builder._collect_claim_facts('retaliation', 'Jane Doe', {})

    assert claim_facts[0] == 'The chronology shows protected activity on January 5, 2026 before adverse action on January 20, 2026.'


def test_score_claims_section_penalizes_temporal_and_proof_gap_pressure():
    optimizer = document_optimization.AgenticDocumentOptimizer(mediator=_build_seeded_mediator())
    claims = [
        {
            'claim_type': 'retaliation',
            'supporting_facts': ['Plaintiff reported discrimination to HR.', 'Defendant terminated Plaintiff two days later.'],
        }
    ]

    baseline = optimizer._score_claims_section(
        claims,
        support_context={
            'claims': [
                {
                    'claim_type': 'retaliation',
                    'missing_elements': [],
                    'temporal_gap_hint_count': 0,
                    'proof_gap_count': 0,
                }
            ]
        },
    )
    penalized = optimizer._score_claims_section(
        claims,
        support_context={
            'claims': [
                {
                    'claim_type': 'retaliation',
                    'missing_elements': [],
                    'temporal_gap_hint_count': 2,
                    'proof_gap_count': 1,
                }
            ]
        },
    )

    assert penalized < baseline


def test_legacy_builder_exposes_anchored_chronology_summary():
    mediator = _build_seeded_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)

    chronology = builder._build_anchored_chronology_summary()

    assert chronology == [
        'Protected activity on January 5, 2026 preceded adverse action on January 20, 2026.'
    ]


def test_legacy_builder_condenses_linear_notice_hearing_response_chronology():
    mediator = _build_seeded_mediator()
    mediator.phase_manager.update_phase_data(
        ComplaintPhase.INTAKE,
        'intake_case_file',
        {
            'canonical_facts': [
                {
                    'fact_id': 'fact:notice',
                    'predicate_family': 'notice_chain',
                    'event_label': 'Notice communication',
                    'temporal_context': {'start_date': '2025-01-05'},
                },
                {
                    'fact_id': 'fact:hearing',
                    'predicate_family': 'hearing_process',
                    'event_label': 'Hearing request event',
                    'temporal_context': {'start_date': '2025-01-08'},
                },
                {
                    'fact_id': 'fact:response',
                    'predicate_family': 'response_timeline',
                    'event_label': 'Response event',
                    'temporal_context': {'start_date': '2025-01-20'},
                },
            ],
            'timeline_relations': [
                {
                    'relation_type': 'before',
                    'source_fact_id': 'fact:notice',
                    'target_fact_id': 'fact:hearing',
                    'source_start_date': '2025-01-05',
                    'target_start_date': '2025-01-08',
                },
                {
                    'relation_type': 'before',
                    'source_fact_id': 'fact:hearing',
                    'target_fact_id': 'fact:response',
                    'source_start_date': '2025-01-08',
                    'target_start_date': '2025-01-20',
                },
            ],
        },
    )
    builder = FormalComplaintDocumentBuilder(mediator)

    chronology = builder._build_anchored_chronology_summary()

    assert chronology == [
        'Notice communication on January 5, 2025, Hearing request event on January 8, 2025, and Response event on January 20, 2025 occurred in sequence.'
    ]


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
