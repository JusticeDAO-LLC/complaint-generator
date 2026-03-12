from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from applications.review_api import create_review_api_app
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
        output_dir=str(tmp_path),
    )

    assert result["draft"]["court_header"] == (
        "IN THE UNITED STATES DISTRICT COURT FOR THE NORTHERN DISTRICT OF CALIFORNIA"
    )
    assert result["draft"]["case_caption"]["plaintiffs"] == ["Jane Doe"]
    assert result["draft"]["case_caption"]["defendants"] == ["Acme Corporation"]
    assert len(result["draft"]["claims_for_relief"]) == 2
    assert len(result["draft"]["exhibits"]) >= 2

    docx_path = Path(result["artifacts"]["docx"]["path"])
    pdf_path = Path(result["artifacts"]["pdf"]["path"])
    assert docx_path.exists()
    assert pdf_path.exists()
    assert docx_path.read_bytes()[:2] == b"PK"
    assert pdf_path.read_bytes()[:4] == b"%PDF"


def test_review_api_registers_formal_complaint_document_route():
    mediator = Mock()
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = DEFAULT_OUTPUT_DIR / 'test-formal-complaint.docx'
    artifact_path.write_bytes(b'test artifact')
    mediator.build_formal_complaint_document_package.return_value = {
        "draft": {"title": "Jane Doe v. Acme Corporation"},
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
    assert response.json()["draft"]["title"] == "Jane Doe v. Acme Corporation"
    assert response.json()["artifacts"]["docx"]["download_url"].startswith('/api/documents/download?path=')
    mediator.build_formal_complaint_document_package.assert_called_once()


def test_review_api_downloads_generated_document_artifact():
    mediator = Mock()
    app = create_review_api_app(mediator)
    client = TestClient(app)

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = DEFAULT_OUTPUT_DIR / 'downloadable-formal-complaint.pdf'
    artifact_path.write_bytes(b'%PDF-1.4\nmock pdf')

    response = client.get('/api/documents/download', params={'path': str(artifact_path)})

    assert response.status_code == 200
    assert response.content.startswith(b'%PDF-1.4')