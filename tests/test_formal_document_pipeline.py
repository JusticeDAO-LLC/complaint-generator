import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from complaint_phases import ComplaintPhase
from complaint_phases.dependency_graph import DependencyGraph, DependencyNode, NodeType
from complaint_phases.knowledge_graph import Entity, KnowledgeGraph
from complaint_phases.legal_graph import LegalElement, LegalGraph
from complaint_phases.neurosymbolic_matcher import NeurosymbolicMatcher
from mediator import Mediator
from mediator.formal_document import HAS_DOCX


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
        case_number='1:26-cv-12345',
        signer_name='Jane Doe, Esq.',
        signer_title='Counsel for Plaintiff',
        signer_firm='Doe Legal Advocacy PLLC',
        signer_bar_number='NM-12345',
        signer_contact='123 Main Street\nSanta Fe, NM 87501',
        declarant_name='Jane Doe',
        service_method='CM/ECF',
        service_recipients=['Registered Agent for Acme Corporation', 'Defense Counsel'],
        signature_date='2026-03-12',
        verification_date='2026-03-12',
        service_date='2026-03-13',
    )

    complaint = result['formal_complaint']
    assert complaint['court_header'] == 'IN THE UNITED STATES DISTRICT COURT FOR THE DISTRICT OF NEW MEXICO'
    assert complaint['caption']['case_number'] == '1:26-cv-12345'
    assert complaint['nature_of_action']
    assert complaint['legal_claims'][0]['title'] == 'COUNT I - RETALIATION'
    assert complaint['legal_claims'][0]['legal_standard_elements'][0]['citation'] == '42 U.S.C. § 2000e-3(a)'
    assert complaint['exhibits'][0]['label'] == 'Exhibit A'
    assert complaint['exhibits'][0]['reference'] == 'https://example.org/termination-letter.pdf'
    assert complaint['verification']['title'] == 'Verification'
    assert 'under penalty of perjury' in complaint['verification']['text']
    assert complaint['certificate_of_service']['title'] == 'Certificate of Service'
    assert complaint['signature_block']['signature_line'] == '/s/ Jane Doe, Esq.'
    assert complaint['signature_block']['title'] == 'Counsel for Plaintiff'
    assert complaint['signature_block']['firm'] == 'Doe Legal Advocacy PLLC'
    assert complaint['signature_block']['bar_number'] == 'NM-12345'
    assert complaint['signature_block']['contact'] == '123 Main Street\nSanta Fe, NM 87501'
    assert complaint['signature_block']['dated'] == 'Dated: 2026-03-12'
    assert complaint['verification']['signature_line'] == '/s/ Jane Doe'
    assert complaint['verification']['text'].startswith('I, Jane Doe, declare under penalty of perjury')
    assert complaint['verification']['dated'] == 'Executed on: 2026-03-12'
    assert complaint['certificate_of_service']['recipients'] == ['Registered Agent for Acme Corporation', 'Defense Counsel']
    assert complaint['certificate_of_service']['dated'] == 'Service date: 2026-03-13'
    assert 'CM/ECF' in complaint['certificate_of_service']['text']
    assert 'Registered Agent for Acme Corporation' in complaint['certificate_of_service']['text']
    assert 'IN THE UNITED STATES DISTRICT COURT FOR THE DISTRICT OF NEW MEXICO' in result['draft_text']
    assert 'VERIFICATION' in result['draft_text']
    assert 'CERTIFICATE OF SERVICE' in result['draft_text']
    assert '/s/ Jane Doe, Esq.' in result['draft_text']
    assert 'Doe Legal Advocacy PLLC' in result['draft_text']
    assert 'Bar No. NM-12345' in result['draft_text']
    assert '/s/ Jane Doe' in result['draft_text']
    assert 'Dated: 2026-03-12' in result['draft_text']
    assert 'Defense Counsel' in result['draft_text']
    assert 'Service date: 2026-03-13' in result['draft_text']
    assert result['ready_to_file'] is True


def test_export_formal_complaint_pdf_writes_file(tmp_path):
    mediator = _build_seeded_mediator()
    output_path = tmp_path / 'formal_complaint.pdf'

    result = mediator.export_formal_complaint(
        str(output_path),
        district='New Mexico',
        case_number='1:26-cv-12345',
    )

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

    assert result['export']['format'] == 'docx'
    assert output_path.exists()
    assert output_path.stat().st_size > 0