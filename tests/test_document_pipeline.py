from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from applications.review_api import create_review_api_app
from applications.review_ui import create_review_surface_app
from document_pipeline import DEFAULT_OUTPUT_DIR, FormalComplaintDocumentBuilder


pytestmark = pytest.mark.no_auto_network


def _build_mediator() -> Mock:
    mediator = Mock()
    mediator.state = SimpleNamespace(
        username="test-user",
        hashed_username=None,
        complaint=(
            "Plaintiff reported discrimination to human resources and was terminated two days later. "
            "Plaintiff seeks reinstatement, back pay, and injunctive relief."
        ),
        original_complaint="Plaintiff was terminated after reporting discrimination.",
        legal_classification={
            "claim_types": ["employment discrimination", "retaliation"],
            "jurisdiction": "federal",
            "legal_areas": ["employment law", "civil rights law"],
            "key_facts": [
                "Plaintiff complained to human resources about race discrimination.",
                "Defendant terminated Plaintiff shortly after the complaint.",
            ],
        },
        applicable_statutes=[
            {
                "citation": "42 U.S.C. § 2000e-2",
                "title": "Title VII of the Civil Rights Act",
                "relevance": "Prohibits discrimination in employment.",
            },
            {
                "citation": "42 U.S.C. § 2000e-3",
                "title": "Title VII anti-retaliation provision",
                "relevance": "Prohibits retaliation for protected complaints.",
            },
        ],
        summary_judgment_requirements={
            "employment discrimination": [
                "Membership in a protected class.",
                "Adverse employment action.",
                "Discriminatory motive or disparate treatment.",
            ],
            "retaliation": [
                "Protected activity.",
                "Materially adverse action.",
                "Causal connection between the activity and the adverse action.",
            ],
        },
        inquiries=[
            {
                "question": "What happened after you reported discrimination?",
                "answer": "I was fired two days later and lost my pay and benefits.",
            }
        ],
    )
    mediator.summarize_claim_support.return_value = {
        "claims": {
            "employment discrimination": {
                "total_elements": 3,
                "covered_elements": 2,
                "uncovered_elements": 1,
                "support_by_kind": {"evidence": 2, "authority": 1},
                "elements": [
                    {
                        "element_text": "Adverse employment action",
                        "links": [
                            {
                                "support_kind": "authority",
                                "citation": "42 U.S.C. § 2000e-2",
                                "title": "Title VII of the Civil Rights Act",
                                "support_ref": "https://www.eeoc.gov/statutes/title-vii-civil-rights-act-1964",
                            }
                        ],
                    }
                ],
            },
            "retaliation": {
                "total_elements": 3,
                "covered_elements": 2,
                "uncovered_elements": 1,
                "support_by_kind": {"evidence": 1, "authority": 1},
                "elements": [],
            },
        }
    }
    mediator.get_claim_support_facts.side_effect = lambda claim_type=None, user_id=None: [
        {
            "fact_text": f"Evidence shows facts supporting {claim_type}.",
            "summary": "Termination email and HR complaint timeline.",
        }
    ]
    mediator.get_claim_overview.side_effect = lambda claim_type=None, user_id=None, required_support_kinds=None: {
        "claims": {
            claim_type: {
                "missing": [{"element_text": "Discriminatory motive"}] if claim_type == "employment discrimination" else [],
                "partially_supported": [{"element_text": "Causal connection"}] if claim_type == "retaliation" else [],
            }
        }
    }
    mediator.get_user_evidence.return_value = [
        {
            "id": 1,
            "cid": "QmTerminationEmail",
            "type": "document",
            "claim_type": "employment discrimination",
            "description": "Termination email from Defendant.",
            "parsed_text_preview": "Email confirming termination effective immediately.",
        },
        {
            "id": 2,
            "cid": "QmHRComplaint",
            "type": "document",
            "claim_type": "retaliation",
            "description": "Human resources complaint email.",
            "parsed_text_preview": "Email to HR reporting discrimination.",
        },
    ]
    mediator.phase_manager = None
    return mediator


def test_formal_complaint_document_builder_generates_docx_and_pdf(tmp_path: Path):
    mediator = _build_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)

    result = builder.build_package(
        district="Northern District of California",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        case_number="25-cv-00001",
        signer_name="Jane Doe, Esq.",
        signer_title="Counsel for Plaintiff",
        signer_firm="Doe Legal Advocacy PLLC",
        signer_bar_number="CA-54321",
        signer_contact="123 Main Street\nSan Francisco, CA 94105",
        declarant_name="Jane Doe",
        service_method="CM/ECF",
        service_recipients=["Registered Agent for Acme Corporation", "Defense Counsel"],
        signature_date="2026-03-12",
        verification_date="2026-03-12",
        service_date="2026-03-13",
        output_dir=str(tmp_path),
        output_formats=["docx", "pdf", "txt"],
    )

    assert result["draft"]["court_header"] == (
        "IN THE UNITED STATES DISTRICT COURT FOR THE NORTHERN DISTRICT OF CALIFORNIA"
    )
    assert result["draft"]["case_caption"]["plaintiffs"] == ["Jane Doe"]
    assert result["draft"]["case_caption"]["defendants"] == ["Acme Corporation"]
    assert "subject-matter jurisdiction" in result["draft"]["jurisdiction_statement"].lower()
    assert "venue is proper" in result["draft"]["venue_statement"].lower()
    assert len(result["draft"]["claims_for_relief"]) == 2
    assert len(result["draft"]["exhibits"]) >= 2
    assert len(result["draft"]["factual_allegations"]) > len(result["draft"]["summary_of_facts"])
    assert result["draft"]["factual_allegation_paragraphs"][0]["number"] == 1
    assert result["draft"]["factual_allegation_paragraphs"][0]["text"] == result["draft"]["factual_allegations"][0]
    assert "COMPLAINT" in result["draft"]["draft_text"]
    assert "EXHIBITS" in result["draft"]["draft_text"]
    assert "FACTUAL ALLEGATIONS" in result["draft"]["draft_text"]
    assert "Plaintiff repeats and realleges ¶¶" in result["draft"]["draft_text"]
    assert "and incorporates Exhibit" in result["draft"]["draft_text"]
    assert "as if fully set forth herein." in result["draft"]["draft_text"]
    assert "Claim-Specific Support:" in result["draft"]["draft_text"]
    assert any(allegation.startswith("As to ") for allegation in result["draft"]["factual_allegations"])
    assert all(claim.get("allegation_references") for claim in result["draft"]["claims_for_relief"])
    assert any("See Exhibit" in fact for fact in result["draft"]["summary_of_facts"])
    assert any(
        "See Exhibit" in fact
        for claim in result["draft"]["claims_for_relief"]
        for fact in claim.get("supporting_facts", [])
    )
    assert result["draft"]["verification"]["title"] == "Verification"
    assert result["draft"]["certificate_of_service"]["title"] == "Certificate of Service"
    assert result["draft"]["signature_block"]["signature_line"] == "/s/ Jane Doe, Esq."
    assert result["draft"]["signature_block"]["title"] == "Counsel for Plaintiff"
    assert result["draft"]["signature_block"]["firm"] == "Doe Legal Advocacy PLLC"
    assert result["draft"]["signature_block"]["bar_number"] == "CA-54321"
    assert result["draft"]["signature_block"]["contact"] == "123 Main Street\nSan Francisco, CA 94105"
    assert result["draft"]["signature_block"]["dated"] == "Dated: 2026-03-12"
    assert result["draft"]["verification"]["signature_line"] == "/s/ Jane Doe"
    assert result["draft"]["verification"]["text"].startswith("I, Jane Doe, declare under penalty of perjury")
    assert result["draft"]["verification"]["dated"] == "Executed on: 2026-03-12"
    assert result["draft"]["certificate_of_service"]["recipients"] == ["Registered Agent for Acme Corporation", "Defense Counsel"]
    assert result["draft"]["certificate_of_service"]["dated"] == "Service date: 2026-03-13"
    assert "CM/ECF" in result["draft"]["certificate_of_service"]["text"]
    assert "Defense Counsel" in result["draft"]["certificate_of_service"]["text"]
    assert result["drafting_readiness"]["status"] == "warning"
    assert result["draft"]["drafting_readiness"]["status"] == "warning"
    assert result["drafting_readiness"]["sections"]["claims_for_relief"]["status"] == "warning"
    assert result["drafting_readiness"]["sections"]["summary_of_facts"]["status"] == "ready"
    assert any(
        entry["claim_type"] == "employment discrimination" and entry["status"] == "warning"
        for entry in result["drafting_readiness"]["claims"]
    )
    assert any(
        warning["code"] == "unresolved_elements"
        for entry in result["drafting_readiness"]["claims"]
        for warning in entry["warnings"]
    )

    docx_path = Path(result["artifacts"]["docx"]["path"])
    pdf_path = Path(result["artifacts"]["pdf"]["path"])
    txt_path = Path(result["artifacts"]["txt"]["path"])
    assert docx_path.exists()
    assert pdf_path.exists()
    assert txt_path.exists()
    assert docx_path.read_bytes()[:2] == b"PK"
    assert pdf_path.read_bytes()[:4] == b"%PDF"
    assert "JURISDICTION AND VENUE" in txt_path.read_text(encoding="utf-8")


def test_review_api_registers_formal_complaint_document_route():
    mediator = Mock()
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = DEFAULT_OUTPUT_DIR / 'test-formal-complaint.docx'
    artifact_path.write_bytes(b'test artifact')
    try:
        mediator.build_formal_complaint_document_package.return_value = {
            "draft": {"title": "Jane Doe v. Acme Corporation"},
            "drafting_readiness": {
                "status": "ready",
                "sections": {},
                "claims": [{"claim_type": "retaliation", "status": "ready", "warnings": []}],
                "warning_count": 0,
            },
            "artifacts": {"docx": {"path": str(artifact_path), "filename": artifact_path.name, "size_bytes": artifact_path.stat().st_size}},
            "output_formats": ["docx"],
            "generated_at": "2026-03-12T12:00:00+00:00",
        }

        app = create_review_api_app(mediator)
        client = TestClient(app)

        response = client.post(
            "/api/documents/formal-complaint",
            json={
                "district": "District of Columbia",
                "plaintiff_names": ["Jane Doe"],
                "defendant_names": ["Acme Corporation"],
                "signer_name": "Jane Doe",
                "signer_title": "Counsel for Plaintiff",
                "signer_firm": "Doe Legal Advocacy PLLC",
                "signer_bar_number": "DC-10101",
                "signer_contact": "123 Main Street\nWashington, DC 20001",
                "declarant_name": "Jane Doe",
                "service_method": "CM/ECF",
                "service_recipients": ["Registered Agent for Acme Corporation", "Defense Counsel"],
                "signature_date": "2026-03-12",
                "verification_date": "2026-03-12",
                "service_date": "2026-03-13",
                "output_formats": ["docx"],
            },
        )

        assert response.status_code == 200
        assert response.json()["draft"]["title"] == "Jane Doe v. Acme Corporation"
        assert response.json()["drafting_readiness"]["status"] == "ready"
        assert response.json()["artifacts"]["docx"]["download_url"].startswith('/api/documents/download?path=')
        assert response.json()["review_links"]["dashboard_url"] == "/claim-support-review"
        assert response.json()["review_links"]["claims"][0]["review_url"] == "/claim-support-review?claim_type=retaliation"
        assert response.json()["review_links"]["sections"] == []
        assert response.json()["drafting_readiness"]["claims"][0]["review_context"] == {
            "user_id": None,
            "claim_type": "retaliation",
        }
        mediator.build_formal_complaint_document_package.assert_called_once_with(
            user_id=None,
            court_name="United States District Court",
            district="District of Columbia",
            division=None,
            court_header_override=None,
            case_number=None,
            title_override=None,
            plaintiff_names=["Jane Doe"],
            defendant_names=["Acme Corporation"],
            requested_relief=[],
            signer_name="Jane Doe",
            signer_title="Counsel for Plaintiff",
            signer_firm="Doe Legal Advocacy PLLC",
            signer_bar_number="DC-10101",
            signer_contact="123 Main Street\nWashington, DC 20001",
            declarant_name="Jane Doe",
            service_method="CM/ECF",
            service_recipients=["Registered Agent for Acme Corporation", "Defense Counsel"],
            signature_date="2026-03-12",
            verification_date="2026-03-12",
            service_date="2026-03-13",
            output_dir=None,
            output_formats=["docx"],
        )
    finally:
        artifact_path.unlink(missing_ok=True)


def test_review_api_multiclaim_section_links_include_targeted_claim_urls():
    mediator = Mock()
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = DEFAULT_OUTPUT_DIR / 'multi-claim-formal-complaint.docx'
    artifact_path.write_bytes(b'test artifact')
    try:
        mediator.build_formal_complaint_document_package.return_value = {
            "draft": {"title": "Jane Doe v. Acme Corporation"},
            "drafting_readiness": {
                "status": "warning",
                "sections": {
                    "claims_for_relief": {"title": "Claims for Relief", "status": "warning", "warnings": []},
                },
                "claims": [
                    {"claim_type": "employment discrimination", "status": "warning", "warnings": []},
                    {"claim_type": "retaliation", "status": "warning", "warnings": []},
                ],
                "warning_count": 1,
            },
            "artifacts": {"docx": {"path": str(artifact_path), "filename": artifact_path.name, "size_bytes": artifact_path.stat().st_size}},
            "output_formats": ["docx"],
            "generated_at": "2026-03-12T12:00:00+00:00",
        }

        app = create_review_api_app(mediator)
        client = TestClient(app)

        response = client.post(
            "/api/documents/formal-complaint",
            json={
                "district": "District of Columbia",
                "plaintiff_names": ["Jane Doe"],
                "defendant_names": ["Acme Corporation"],
                "output_formats": ["docx"],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["review_links"]["sections"][0]["section_key"] == "claims_for_relief"
        assert payload["review_links"]["sections"][0]["review_url"] == "/claim-support-review?section=claims_for_relief"
        assert payload["review_links"]["sections"][0]["claim_links"] == [
            {
                "claim_type": "employment discrimination",
                "review_url": "/claim-support-review?claim_type=employment+discrimination&section=claims_for_relief",
            },
            {
                "claim_type": "retaliation",
                "review_url": "/claim-support-review?claim_type=retaliation&section=claims_for_relief",
            },
        ]
        assert payload["drafting_readiness"]["sections"]["claims_for_relief"]["review_context"] == {
            "user_id": None,
            "section": "claims_for_relief",
            "claim_type": None,
        }
        assert payload["drafting_readiness"]["sections"]["claims_for_relief"]["claim_links"] == [
            {
                "claim_type": "employment discrimination",
                "review_url": "/claim-support-review?claim_type=employment+discrimination&section=claims_for_relief",
            },
            {
                "claim_type": "retaliation",
                "review_url": "/claim-support-review?claim_type=retaliation&section=claims_for_relief",
            },
        ]
    finally:
        artifact_path.unlink(missing_ok=True)


def test_review_api_downloads_generated_document_artifact():
    mediator = Mock()
    app = create_review_api_app(mediator)
    client = TestClient(app)

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = DEFAULT_OUTPUT_DIR / 'downloadable-formal-complaint.pdf'
    artifact_path.write_bytes(b'%PDF-1.4\nmock pdf')
    try:
        response = client.get('/api/documents/download', params={'path': str(artifact_path)})

        assert response.status_code == 200
        assert response.content.startswith(b'%PDF-1.4')
    finally:
        artifact_path.unlink(missing_ok=True)


def test_review_surface_document_builder_flow_serves_page_and_supports_api_round_trip():
    mediator = Mock()
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = DEFAULT_OUTPUT_DIR / 'review-surface-formal-complaint.docx'
    artifact_path.write_bytes(b'PK\x03\x04mock-docx')
    try:
        mediator.build_formal_complaint_document_package.return_value = {
            "draft": {
                "title": "Jane Doe v. Acme Corporation",
                "court_header": "IN THE UNITED STATES DISTRICT COURT FOR THE DISTRICT OF COLUMBIA",
                "case_caption": {
                    "plaintiffs": ["Jane Doe"],
                    "defendants": ["Acme Corporation"],
                    "case_number": "25-cv-00001",
                    "document_title": "COMPLAINT",
                },
                "claims_for_relief": [{"count_title": "Count I - Retaliation"}],
                "requested_relief": ["Back pay."],
                "exhibits": [{"label": "Exhibit A", "title": "Termination email"}],
                "drafting_readiness": {
                    "status": "warning",
                    "sections": {
                        "claims_for_relief": {"status": "warning"},
                    },
                    "claims": [
                        {
                            "claim_type": "retaliation",
                            "status": "warning",
                            "warnings": [],
                        }
                    ],
                    "warning_count": 1,
                },
            },
            "drafting_readiness": {
                "status": "warning",
                "sections": {
                    "claims_for_relief": {"status": "warning"},
                },
                "claims": [
                    {
                        "claim_type": "retaliation",
                        "status": "warning",
                        "warnings": [],
                    }
                ],
                "warning_count": 1,
            },
            "artifacts": {
                "docx": {
                    "path": str(artifact_path),
                    "filename": artifact_path.name,
                    "size_bytes": artifact_path.stat().st_size,
                }
            },
            "output_formats": ["docx"],
            "generated_at": "2026-03-12T12:00:00+00:00",
        }

        app = create_review_surface_app(mediator)
        client = TestClient(app)

        page_response = client.get('/document')

        assert page_response.status_code == 200
        page_html = page_response.text
        soup = BeautifulSoup(page_html, 'html.parser')
        assert soup.find(id='documentForm') is not None
        assert soup.find(id='generateButton') is not None
        assert soup.find(id='previewRoot') is not None
        assert '/api/documents/formal-complaint' in page_html
        assert '/claim-support-review' in page_html
        assert 'Open Claim Support Review' in page_html
        assert 'Open Review Dashboard' in page_html
        assert 'Open Section Review' in page_html
        assert 'formalComplaintBuilderState' in page_html
        assert 'formalComplaintBuilderPreview' in page_html
        assert 'Pleading Text' in page_html
        assert 'Copy Pleading Text' in page_html
        assert 'value="txt"' in page_html
        assert 'Drafting Readiness' in page_html
        assert 'Section Readiness' in page_html
        assert 'Claim Readiness' in page_html
        assert 'Source Drilldown' in page_html
        assert 'Factual Allegations' in page_html
        assert 'Incorporated Support' in page_html
        assert 'Supporting Exhibit Details' in page_html
        assert 'Open filing warnings' in page_html
        assert 'pleading-paragraphs' in page_html
        assert 'Verification Declarant' in page_html
        assert 'Service Recipients' in page_html

        api_response = client.post(
            '/api/documents/formal-complaint',
            json={
                'district': 'District of Columbia',
                'case_number': '25-cv-00001',
                'plaintiff_names': ['Jane Doe'],
                'defendant_names': ['Acme Corporation'],
                'output_formats': ['docx'],
            },
        )

        assert api_response.status_code == 200
        payload = api_response.json()
        assert payload['draft']['title'] == 'Jane Doe v. Acme Corporation'
        assert payload['draft']['case_caption']['case_number'] == '25-cv-00001'
        assert payload['drafting_readiness']['status'] == 'warning'
        assert payload['review_links']['dashboard_url'] == '/claim-support-review'
        assert payload['review_links']['claims'][0]['review_url'] == '/claim-support-review?claim_type=retaliation'
        assert payload['review_links']['sections'][0]['section_key'] == 'claims_for_relief'
        assert payload['review_links']['sections'][0]['review_url'] == '/claim-support-review?claim_type=retaliation&section=claims_for_relief'
        assert payload['drafting_readiness']['claims'][0]['review_url'] == '/claim-support-review?claim_type=retaliation'
        assert payload['drafting_readiness']['sections']['claims_for_relief']['review_context'] == {
            'user_id': None,
            'section': 'claims_for_relief',
            'claim_type': 'retaliation',
        }
        assert payload['artifacts']['docx']['download_url'].startswith('/api/documents/download?path=')

        download_response = client.get('/api/documents/download', params={'path': str(artifact_path)})

        assert download_response.status_code == 200
        assert download_response.content.startswith(b'PK\x03\x04')
    finally:
        artifact_path.unlink(missing_ok=True)