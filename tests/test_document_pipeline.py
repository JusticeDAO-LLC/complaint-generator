from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import os
import json
import zipfile
import document_optimization

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from applications.review_api import create_review_api_app
from applications.review_ui import create_review_surface_app
from document_pipeline import DEFAULT_OUTPUT_DIR, FormalComplaintDocumentBuilder


pytestmark = pytest.mark.no_auto_network


def _live_hf_token() -> str:
    return (
        os.getenv("HF_TOKEN", "").strip()
        or os.getenv("HUGGINGFACE_HUB_TOKEN", "").strip()
        or os.getenv("HUGGINGFACE_API_KEY", "").strip()
        or os.getenv("HF_API_TOKEN", "").strip()
    )


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
                "support_packet_summary": {
                    "source_family_counts": {"evidence": 2, "legal_authority": 1},
                    "artifact_family_counts": {"archived_web_page": 2, "legal_authority_reference": 1},
                    "content_origin_counts": {"historical_archive_capture": 2, "authority_reference_fallback": 1},
                },
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
                "support_packet_summary": {
                    "source_family_counts": {"evidence": 1, "legal_authority": 1},
                    "artifact_family_counts": {"document": 1, "legal_authority_reference": 1},
                    "content_origin_counts": {"user_uploaded_document": 1, "authority_reference_fallback": 1},
                },
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
        county="San Francisco County",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        case_number="25-cv-00001",
        lead_case_number="24-cv-00077",
        related_case_number="24-cv-00110",
        assigned_judge="Hon. Maria Valdez",
        courtroom="Courtroom 4A",
        signer_name="Jane Doe, Esq.",
        signer_title="Counsel for Plaintiff",
        signer_firm="Doe Legal Advocacy PLLC",
        signer_bar_number="CA-54321",
        signer_contact="123 Main Street\nSan Francisco, CA 94105",
        additional_signers=[
            {
                "name": "John Roe, Esq.",
                "title": "Co-Counsel for Plaintiff",
                "firm": "Roe Civil Rights Group",
                "bar_number": "CA-67890",
                "contact": "456 Side Street\nOakland, CA 94607",
            }
        ],
        declarant_name="Jane Doe",
        affidavit_title="AFFIDAVIT OF JANE DOE REGARDING RETALIATION",
        affidavit_intro="I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation.",
        affidavit_facts=[
            "I reported discrimination to human resources on March 3, 2026.",
            "Defendant terminated my employment two days later.",
        ],
        affidavit_supporting_exhibits=[
            {
                "label": "Affidavit Ex. 1",
                "title": "HR Complaint Email",
                "link": "https://example.org/hr-email.pdf",
                "summary": "Email reporting discrimination to HR.",
            }
        ],
        affidavit_include_complaint_exhibits=False,
        affidavit_venue_lines=["State of California", "County of San Francisco"],
        affidavit_jurat="Subscribed and sworn to before me on March 13, 2026 by Jane Doe.",
        affidavit_notary_block=[
            "__________________________________",
            "Notary Public for the State of California",
            "My commission expires: March 13, 2029",
        ],
        service_method="CM/ECF",
        service_recipients=["Registered Agent for Acme Corporation", "Defense Counsel"],
        service_recipient_details=[
            {"recipient": "Defense Counsel", "method": "Email", "address": "counsel@example.com"},
            {"recipient": "Registered Agent for Acme Corporation", "method": "Certified Mail", "address": "123 Main Street"},
        ],
        jury_demand=True,
        jury_demand_text="Plaintiff demands a trial by jury on all issues so triable.",
        signature_date="2026-03-12",
        verification_date="2026-03-12",
        service_date="2026-03-13",
        output_dir=str(tmp_path),
        output_formats=["docx", "pdf", "txt", "checklist"],
    )

    assert result["draft"]["court_header"] == (
        "IN THE UNITED STATES DISTRICT COURT FOR THE NORTHERN DISTRICT OF CALIFORNIA"
    )
    assert result["draft"]["case_caption"]["plaintiffs"] == ["Jane Doe"]
    assert result["draft"]["case_caption"]["defendants"] == ["Acme Corporation"]
    assert result["draft"]["case_caption"]["county"] == "SAN FRANCISCO COUNTY"
    assert result["draft"]["case_caption"]["lead_case_number"] == "24-cv-00077"
    assert result["draft"]["case_caption"]["related_case_number"] == "24-cv-00110"
    assert result["draft"]["case_caption"]["assigned_judge"] == "Hon. Maria Valdez"
    assert result["draft"]["case_caption"]["courtroom"] == "Courtroom 4A"
    assert result["draft"]["case_caption"]["jury_demand_notice"] == "JURY TRIAL DEMANDED"
    assert result["draft"]["case_caption"]["case_number_label"] == "Civil Action No."
    assert "subject-matter jurisdiction" in result["draft"]["jurisdiction_statement"].lower()
    assert "venue is proper" in result["draft"]["venue_statement"].lower()
    assert len(result["draft"]["claims_for_relief"]) == 2
    assert len(result["draft"]["exhibits"]) >= 2
    assert len(result["draft"]["factual_allegations"]) >= 2
    assert any(
        "Plaintiff was fired two days later and lost pay and benefits" in allegation
        or "I was fired two days later and lost pay and benefits" in allegation
        for allegation in result["draft"]["factual_allegations"]
    )
    assert any(
        allegation.startswith("After Plaintiff complained to human resources about race discrimination")
        for allegation in result["draft"]["factual_allegations"]
    )
    assert all(
        not allegation.lower().startswith("what happened after you reported discrimination?:")
        for allegation in result["draft"]["factual_allegations"]
    )
    assert all("lost my pay" not in allegation.lower() for allegation in result["draft"]["factual_allegations"])
    assert all(
        not allegation.lower().startswith("plaintiff seeks reinstatement")
        for allegation in result["draft"]["factual_allegations"]
    )
    assert all(
        "evidence shows facts supporting" not in allegation.lower()
        for allegation in result["draft"]["factual_allegations"]
    )
    assert all(
        not allegation.startswith("As a direct result of Defendant's conduct, Plaintiff lost pay and benefits")
        for allegation in result["draft"]["factual_allegations"]
    )
    assert all(
        "reported discrimination to human resources and was terminated two days later" not in allegation.lower()
        for allegation in result["draft"]["factual_allegations"]
    )
    assert all(" and i was " not in allegation.lower() for allegation in result["draft"]["factual_allegations"])
    assert all(" and i lost " not in allegation.lower() for allegation in result["draft"]["factual_allegations"])
    assert result["draft"]["factual_allegation_paragraphs"][0]["number"] == 1
    assert result["draft"]["factual_allegation_paragraphs"][0]["text"] == result["draft"]["factual_allegations"][0]
    assert result["draft"]["factual_allegation_groups"][0]["title"] == "Protected Activity and Complaints"
    assert "COMPLAINT" in result["draft"]["draft_text"]
    assert "EXHIBITS" in result["draft"]["draft_text"]
    assert "FACTUAL ALLEGATIONS" in result["draft"]["draft_text"]
    assert "PROTECTED ACTIVITY AND COMPLAINTS" in result["draft"]["draft_text"]
    assert "ADVERSE ACTION AND RETALIATORY CONDUCT" in result["draft"]["draft_text"]
    assert "Plaintiff repeats and realleges ¶" in result["draft"]["draft_text"]
    assert "and incorporates Exhibit" in result["draft"]["draft_text"]
    assert "as if fully set forth herein." in result["draft"]["draft_text"]
    assert "Claim-Specific Support:" in result["draft"]["draft_text"]
    assert any("terminated" in allegation.lower() for allegation in result["draft"]["factual_allegations"])
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
    assert result["draft"]["signature_block"]["additional_signers"][0]["signature_line"] == "/s/ John Roe, Esq."
    assert result["draft"]["signature_block"]["additional_signers"][0]["firm"] == "Roe Civil Rights Group"
    assert result["draft"]["verification"]["signature_line"] == "/s/ Jane Doe"
    assert result["draft"]["verification"]["text"].startswith("I, Jane Doe, declare under penalty of perjury")
    assert result["draft"]["verification"]["dated"] == "Executed on: 2026-03-12"
    employment_claim = next(
        claim for claim in result["draft"]["claims_for_relief"] if claim["claim_type"] == "employment discrimination"
    )
    assert employment_claim["support_summary"]["source_family_counts"] == {"evidence": 2, "legal_authority": 1}
    assert employment_claim["support_summary"]["artifact_family_counts"] == {
        "archived_web_page": 2,
        "legal_authority_reference": 1,
    }
    assert result["draft"]["affidavit"]["title"] == "AFFIDAVIT OF JANE DOE REGARDING RETALIATION"
    assert result["draft"]["affidavit"]["intro"] == "I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation."
    assert result["draft"]["affidavit"]["venue_lines"] == ["State of California", "County of San Francisco"]
    assert result["draft"]["affidavit"]["facts"] == [
        "I reported discrimination to human resources on March 3, 2026.",
        "Defendant terminated my employment two days later.",
    ]
    assert result["draft"]["affidavit"]["supporting_exhibits"] == [
        {
            "label": "Affidavit Ex. 1",
            "title": "HR Complaint Email",
            "link": "https://example.org/hr-email.pdf",
            "summary": "Email reporting discrimination to HR.",
        }
    ]
    assert result["draft"]["affidavit"]["jurat"] == "Subscribed and sworn to before me on March 13, 2026 by Jane Doe."
    assert result["draft"]["affidavit"]["notary_block"][1] == "Notary Public for the State of California"
    assert result["draft"]["certificate_of_service"]["recipients"] == ["Registered Agent for Acme Corporation", "Defense Counsel"]
    assert result["draft"]["certificate_of_service"]["recipient_details"][0]["recipient"] == "Defense Counsel"
    assert "Defense Counsel | Method: Email | Address: counsel@example.com" in result["draft"]["certificate_of_service"]["detail_lines"]
    assert result["draft"]["certificate_of_service"]["dated"] == "Service date: 2026-03-13"
    assert "following recipients" in result["draft"]["certificate_of_service"]["text"]
    assert result["draft"]["jury_demand"]["title"] == "Jury Demand"
    assert result["draft"]["jury_demand"]["text"] == "Plaintiff demands a trial by jury on all issues so triable."
    assert "JURY DEMAND" in result["draft"]["draft_text"]
    assert "AFFIDAVIT OF JANE DOE REGARDING RETALIATION" in result["draft"]["draft_text"]


def test_formal_complaint_document_builder_can_optimize_draft_with_agentic_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mediator = _build_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)
    calls = {"critic": 0, "actor": 0}
    llm_invocations = []

    class _FakeEmbeddingsRouter:
        def embed_text(self, text: str):
            lowered = text.lower()
            return [
                float("retaliation" in lowered),
                float("terminated" in lowered or "fired" in lowered),
                float(len(text.split())),
            ]

    def _fake_generate_text(prompt: str, *, provider=None, model_name=None, **kwargs):
        llm_invocations.append({"provider": provider, "model_name": model_name, "kwargs": dict(kwargs)})
        if document_optimization.AgenticDocumentOptimizer.CRITIC_PROMPT_TAG in prompt:
            calls["critic"] += 1
            if calls["critic"] == 1:
                payload = {
                    "overall_score": 0.52,
                    "dimension_scores": {
                        "completeness": 0.55,
                        "grounding": 0.6,
                        "coherence": 0.45,
                        "procedural": 0.7,
                        "renderability": 0.3,
                    },
                    "strengths": ["Support packets are available."],
                    "weaknesses": ["Factual allegations should be more pleading-ready."],
                    "suggestions": ["Rewrite factual allegations into declarative prose anchored in the support record."],
                    "recommended_focus": "factual_allegations",
                }
            else:
                payload = {
                    "overall_score": 0.91,
                    "dimension_scores": {
                        "completeness": 0.9,
                        "grounding": 0.92,
                        "coherence": 0.9,
                        "procedural": 0.93,
                        "renderability": 0.9,
                    },
                    "strengths": ["Factual allegations now read like pleading paragraphs."],
                    "weaknesses": [],
                    "suggestions": [],
                    "recommended_focus": "claims_for_relief",
                }
            return {
                "status": "available",
                "text": json.dumps(payload),
                "provider_name": provider,
                "model_name": model_name,
                "effective_provider_name": "openrouter",
                "effective_model_name": "meta-llama/Llama-3.3-70B-Instruct",
                "router_base_url": kwargs.get("base_url"),
                "arch_router_status": "selected",
                "arch_router_selected_route": "legal_reasoning",
                "arch_router_selected_model": "meta-llama/Llama-3.3-70B-Instruct",
                "arch_router_model_name": "katanemo/Arch-Router-1.5B",
            }
        calls["actor"] += 1
        payload = {
            "factual_allegations": [
                "Plaintiff reported discrimination to human resources.",
                "Plaintiff was fired two days later and lost pay and benefits.",
                "As to Retaliation, Defendant terminated Plaintiff shortly after the protected complaint.",
            ],
            "claim_supporting_facts": {
                "retaliation": [
                    "Plaintiff complained to human resources about race discrimination.",
                    "Defendant terminated Plaintiff shortly after the complaint.",
                ]
            },
        }
        return {
            "status": "available",
            "text": json.dumps(payload),
            "provider_name": provider,
            "model_name": model_name,
            "effective_provider_name": "openrouter",
            "effective_model_name": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
            "router_base_url": kwargs.get("base_url"),
            "arch_router_status": "selected",
            "arch_router_selected_route": "drafting",
            "arch_router_selected_model": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
            "arch_router_model_name": "katanemo/Arch-Router-1.5B",
        }

    def _fake_store_bytes(data: bytes, *, pin_content: bool = True):
        return {"status": "available", "cid": "bafy-doc-opt-report", "size": len(data), "pinned": pin_content}

    monkeypatch.setattr(document_optimization, "LLM_ROUTER_AVAILABLE", True)
    monkeypatch.setattr(document_optimization, "EMBEDDINGS_AVAILABLE", True)
    monkeypatch.setattr(document_optimization, "IPFS_AVAILABLE", True)
    monkeypatch.setattr(document_optimization, "generate_text_with_metadata", _fake_generate_text)
    monkeypatch.setattr(document_optimization, "get_embeddings_router", lambda *args, **kwargs: _FakeEmbeddingsRouter())
    monkeypatch.setattr(document_optimization, "store_bytes", _fake_store_bytes)

    result = builder.build_package(
        district="Northern District of California",
        county="San Francisco County",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        enable_agentic_optimization=True,
        optimization_max_iterations=2,
        optimization_target_score=0.9,
        optimization_provider="test-provider",
        optimization_model_name="test-model",
        optimization_llm_config={
            "base_url": "https://router.huggingface.co/v1",
            "headers": {"X-Title": "Complaint Generator Tests"},
            "arch_router": {
                "enabled": True,
                "routes": {
                    "legal_reasoning": "meta-llama/Llama-3.3-70B-Instruct",
                    "drafting": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
                },
            },
        },
        optimization_persist_artifacts=True,
        output_dir=str(tmp_path),
        output_formats=["txt"],
    )

    report = result["document_optimization"]
    assert report["status"] == "optimized"
    assert report["accepted_iterations"] >= 1
    assert report["initial_score"] < report["final_score"]
    assert report["artifact_cid"] == "bafy-doc-opt-report"
    assert report["packet_projection"]["section_presence"]["factual_allegations"] is True
    assert report["packet_projection"]["has_affidavit"] is True
    assert report["section_history"]
    assert report["section_history"][0]["focus_section"] == "factual_allegations"
    assert report["section_history"][0]["critic_llm_metadata"]["arch_router_selected_route"] == "legal_reasoning"
    assert report["section_history"][0]["actor_llm_metadata"]["arch_router_selected_route"] == "drafting"
    assert report["section_history"][0]["selected_support_context"]["focus_section"] == "factual_allegations"
    assert report["initial_review"]["llm_metadata"]["effective_model_name"] == "meta-llama/Llama-3.3-70B-Instruct"
    assert report["final_review"]["llm_metadata"]["arch_router_selected_route"] == "legal_reasoning"
    assert "selected_provider" in report["upstream_optimizer"]
    assert calls["actor"] >= 1
    assert calls["critic"] >= 2
    assert llm_invocations
    assert all(entry["provider"] == "test-provider" for entry in llm_invocations)
    assert all(entry["model_name"] == "test-model" for entry in llm_invocations)
    assert all(entry["kwargs"].get("base_url") == "https://router.huggingface.co/v1" for entry in llm_invocations)
    assert all(entry["kwargs"].get("headers", {}).get("X-Title") == "Complaint Generator Tests" for entry in llm_invocations)
    assert any(
        "Plaintiff was fired two days later and lost pay and benefits" in allegation
        for allegation in result["draft"]["factual_allegations"]
    )
    assert "Plaintiff was fired two days later and lost pay and benefits." in result["draft"]["draft_text"]
    assert result["draft"]["affidavit"]["title"] == "AFFIDAVIT OF JANE DOE IN SUPPORT OF COMPLAINT"
    assert result["draft"]["verification"]["text"].startswith("I, Jane Doe, declare under penalty of perjury")
    assert result["drafting_readiness"]["status"] == "warning"
    assert result["draft"]["drafting_readiness"]["status"] == "warning"
    assert result["filing_checklist"] == result["draft"]["filing_checklist"]
    assert any(item["status"] == "warning" for item in result["filing_checklist"])
    assert any(item["scope"] == "claim" for item in result["filing_checklist"])
    assert result["drafting_readiness"]["sections"]["claims_for_relief"]["status"] == "warning"
    assert result["drafting_readiness"]["sections"]["summary_of_facts"]["status"] == "ready"
    assert any(
        entry["claim_type"] == "employment discrimination" and entry["status"] == "warning"
        for entry in result["drafting_readiness"]["claims"]
    )
    employment_readiness = next(
        entry for entry in result["drafting_readiness"]["claims"] if entry["claim_type"] == "employment discrimination"
    )
    assert employment_readiness["source_family_counts"] == {"evidence": 2, "legal_authority": 1}
    assert employment_readiness["artifact_family_counts"] == {
        "archived_web_page": 2,
        "legal_authority_reference": 1,
    }
    assert any(
        warning["code"] == "unresolved_elements"
        for entry in result["drafting_readiness"]["claims"]
        for warning in entry["warnings"]
    )

    txt_path = Path(result["artifacts"]["txt"]["path"])
    affidavit_txt_path = Path(result["artifacts"]["affidavit_txt"]["path"])
    assert txt_path.exists()
    assert affidavit_txt_path.exists()
    assert "JURISDICTION AND VENUE" in txt_path.read_text(encoding="utf-8")
    affidavit_text = affidavit_txt_path.read_text(encoding="utf-8")
    assert "AFFIDAVIT OF JANE DOE IN SUPPORT OF COMPLAINT" in affidavit_text
    assert "Notary Public" in affidavit_text


def test_formal_complaint_document_builder_uses_state_court_opening_language(tmp_path: Path):
    mediator = _build_mediator()
    mediator.state.legal_classification["jurisdiction"] = "state"
    mediator.state.legal_classification["legal_areas"] = ["employment law", "state civil rights law"]
    mediator.state.applicable_statutes = [
        {
            "citation": "Cal. Gov. Code § 12940",
            "title": "California Fair Employment and Housing Act",
            "relevance": "Prohibits discrimination and retaliation in employment.",
        }
    ]
    builder = FormalComplaintDocumentBuilder(mediator)

    result = builder.build_package(
        court_name="Superior Court of California",
        district="County of Los Angeles",
        county="Los Angeles County",
        lead_case_number="JCCP-5123",
        related_case_number="24STCV10001",
        assigned_judge="Hon. Elena Park",
        courtroom="Dept. 12",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        output_dir=str(tmp_path),
        output_formats=["txt"],
    )

    assert "state court" in result["draft"]["nature_of_action"][0].lower()
    assert "governing state law" in result["draft"]["nature_of_action"][0].lower()
    assert "governing state law" in result["draft"]["jurisdiction_statement"].lower()
    assert "within this court's authority" in result["draft"]["jurisdiction_statement"].lower()
    assert result["draft"]["court_header"] == "IN THE SUPERIOR COURT OF CALIFORNIA FOR THE COUNTY OF LOS ANGELES"
    assert result["draft"]["case_caption"]["case_number_label"] == "Case No."
    assert result["draft"]["case_caption"]["lead_case_number_label"] == "Related Proceeding No."
    assert result["draft"]["case_caption"]["related_case_number_label"] == "Coordination No."
    assert result["draft"]["case_caption"]["assigned_judge_label"] == "Judicial Officer"
    assert result["draft"]["case_caption"]["courtroom_label"] == "Department"
    assert result["draft"]["verification"]["text"].startswith(
        "I, Jane Doe, verify that I have reviewed this Complaint and know its contents."
    )
    assert result["draft"]["verification"]["dated"] == "Verified on: __________________"
    assert result["draft"]["certificate_of_service"]["title"] == "Proof of Service"
    assert "I declare that a true and correct copy" in result["draft"]["certificate_of_service"]["text"]
    assert "General and special damages according to proof." in result["draft"]["requested_relief"]
    assert result["draft"]["affidavit"]["intro"].startswith(
        "I, Jane Doe, being duly sworn, state that I am competent to testify"
    )
    assert result["draft"]["affidavit"]["dated"] == "Verified on: __________________"
    assert result["draft"]["affidavit"]["jurat"] == "Subscribed and sworn to before me on __________________ by Jane Doe."
    assert result["draft"]["venue_statement"] == (
        "Venue is proper in this Court because a substantial part of the events or omissions giving rise "
        "to these claims occurred in Los Angeles County."
    )
    assert "NATURE OF THE ACTION" in result["draft"]["draft_text"]
    assert "JURISDICTION AND VENUE" in result["draft"]["draft_text"]
    assert "Case No. ________________" in result["draft"]["draft_text"]
    assert "Plaintiff Jane Doe is a party bringing this civil action in this Court." in result["draft"]["draft_text"]
    assert "Defendant Acme Corporation is named as the party from whom relief is sought." in result["draft"]["draft_text"]
    assert "Wherefore, Plaintiff prays for judgment against Defendant as follows:" in result["draft"]["draft_text"]
    assert "General and special damages according to proof." in result["draft"]["draft_text"]
    assert "verify that I have reviewed this Complaint and know its contents" in result["draft"]["draft_text"]
    assert "being duly sworn, state that I am competent to testify" in result["draft"]["draft_text"]
    assert "Subscribed and sworn to before me on __________________ by Jane Doe." in result["draft"]["draft_text"]
    closing_block = result["draft"]["draft_text"].rsplit("SIGNATURE BLOCK", 1)[-1]
    assert "Dated: __________________" in closing_block
    assert "Respectfully submitted," in closing_block
    assert closing_block.index("Dated: __________________") < closing_block.index("Respectfully submitted,")
    assert "Related Proceeding No. JCCP-5123" in result["draft"]["draft_text"]
    assert "Coordination No. 24STCV10001" in result["draft"]["draft_text"]
    assert "Judicial Officer: Hon. Elena Park" in result["draft"]["draft_text"]
    assert "Department: Dept. 12" in result["draft"]["draft_text"]


def test_formal_complaint_document_builder_handles_structured_complaint_payloads_without_dict_leak(tmp_path: Path):
    mediator = _build_mediator()
    mediator.state.complaint = {
        "summary": (
            "I told my supervisor and HR that I needed accommodation for my disability after surgery. "
            "They cut my shifts, blamed me for treatment-related absences, and fired me after I complained again."
        ),
        "facts": [
            "Plaintiff informed her supervisor and human resources that she needed workplace accommodation after surgery.",
            "Defendant cut Plaintiff's shifts, blamed her for treatment-related absences, and fired her after she complained again.",
        ],
    }
    mediator.state.original_complaint = mediator.state.complaint["summary"]
    mediator.state.legal_classification["key_facts"] = [
        "Plaintiff requested workplace accommodation after surgery.",
        "Defendant reduced Plaintiff's shifts and terminated her employment after renewed complaints.",
    ]
    mediator.state.inquiries = [
        {
            "question": "What happened after you renewed your complaint?",
            "answer": "They cut my shifts, blamed me for treatment-related absences, and fired me after I complained again.",
        }
    ]
    mediator.get_claim_support_facts.side_effect = lambda claim_type=None, user_id=None: [
        {"text": "Plaintiff requested accommodation after surgery."},
        {"text": "Defendant reduced Plaintiff's shifts and terminated her employment after renewed complaints."},
    ]

    builder = FormalComplaintDocumentBuilder(mediator)
    result = builder.build_package(
        district="Northern District of California",
        county="San Francisco County",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        output_dir=str(tmp_path),
        output_formats=["txt"],
    )

    assert all("{'summary':" not in allegation for allegation in result["draft"]["factual_allegations"])
    assert all("after i complained again" not in allegation.lower() for allegation in result["draft"]["factual_allegations"])
    assert all(" that i " not in allegation.lower() for allegation in result["draft"]["factual_allegations"])
    assert all(not allegation.startswith("They ") for allegation in result["draft"]["factual_allegations"])
    assert all("Plaintiff told Plaintiff's supervisor" not in allegation for allegation in result["draft"]["factual_allegations"])
    assert all(not allegation.startswith("Defendant cut Plaintiff's shifts") for allegation in result["draft"]["factual_allegations"])
    assert all(not allegation.startswith("As to Employment Discrimination, Plaintiff requested") for allegation in result["draft"]["factual_allegations"])
    assert any(
        "after Plaintiff complained again" in allegation
        or "after renewed complaints" in allegation.lower()
        for allegation in result["draft"]["factual_allegations"]
    )


def test_formal_complaint_document_builder_pluralizes_caption_party_labels(tmp_path: Path):
    mediator = _build_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)

    result = builder.build_package(
        district="Northern District of California",
        plaintiff_names=["Jane Doe", "John Roe"],
        defendant_names=["Acme Corporation", "Beta LLC"],
        output_dir=str(tmp_path),
        output_formats=["txt"],
    )

    assert result["draft"]["case_caption"]["plaintiff_caption_label"] == "Plaintiffs"
    assert result["draft"]["case_caption"]["defendant_caption_label"] == "Defendants"
    assert result["draft"]["case_caption"]["caption_party_lines"] == [
        "Jane Doe\nJohn Roe, Plaintiffs,",
        "v.",
        "Acme Corporation\nBeta LLC, Defendants.",
    ]
    assert "Jane Doe\nJohn Roe, Plaintiffs," in result["draft"]["draft_text"]
    assert "Acme Corporation\nBeta LLC, Defendants." in result["draft"]["draft_text"]


def test_formal_complaint_document_builder_applies_affidavit_overrides_to_canonical_output(tmp_path: Path):
    mediator = Mock()
    mediator.state = SimpleNamespace(username="test-user", hashed_username=None)
    mediator.generate_formal_complaint.return_value = {
        "formal_complaint": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT FOR THE NORTHERN DISTRICT OF CALIFORNIA",
            "caption": {
                "case_number": "25-cv-00001",
                "county_line": "SAN FRANCISCO COUNTY",
                "document_title": "COMPLAINT",
            },
            "title": "Jane Doe v. Acme Corporation",
            "nature_of_action": ["This action seeks relief for retaliation."],
            "parties": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "jurisdiction_statement": "This Court has jurisdiction.",
            "venue_statement": "Venue is proper in this district.",
            "factual_allegations": ["Plaintiff reported discrimination and was terminated two days later."],
            "summary_of_facts": ["Plaintiff reported discrimination and was terminated two days later."],
            "legal_claims": [],
            "legal_standards": [],
            "requested_relief": ["Back pay."],
            "exhibits": [],
            "signature_block": {
                "name": "Jane Doe, Esq.",
                "signature_line": "/s/ Jane Doe, Esq.",
                "dated": "Dated: 2026-03-12",
            },
            "verification": {
                "signature_line": "/s/ Jane Doe",
                "dated": "Executed on: 2026-03-12",
            },
            "certificate_of_service": {},
        }
    }
    builder = FormalComplaintDocumentBuilder(mediator)

    result = builder.build_package(
        district="Northern District of California",
        county="San Francisco County",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        affidavit_title="AFFIDAVIT OF JANE DOE REGARDING RETALIATION",
        affidavit_intro="I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation.",
        affidavit_facts=[
            "I reported discrimination to human resources on March 3, 2026.",
            "Defendant terminated my employment two days later.",
        ],
        affidavit_supporting_exhibits=[
            {
                "label": "Affidavit Ex. 1",
                "title": "HR Complaint Email",
                "link": "https://example.org/hr-email.pdf",
                "summary": "Email reporting discrimination to HR.",
            }
        ],
        affidavit_venue_lines=["State of California", "County of San Francisco"],
        affidavit_jurat="Subscribed and sworn to before me on March 13, 2026 by Jane Doe.",
        affidavit_notary_block=[
            "__________________________________",
            "Notary Public for the State of California",
            "My commission expires: March 13, 2029",
        ],
        output_dir=str(tmp_path),
        output_formats=["txt"],
    )

    assert result["draft"]["affidavit"]["title"] == "AFFIDAVIT OF JANE DOE REGARDING RETALIATION"
    assert result["draft"]["affidavit"]["intro"] == "I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation."
    assert result["draft"]["affidavit"]["facts"] == [
        "I reported discrimination to human resources on March 3, 2026.",
        "Defendant terminated my employment two days later.",
    ]
    assert result["draft"]["affidavit"]["supporting_exhibits"] == [
        {
            "label": "Affidavit Ex. 1",
            "title": "HR Complaint Email",
            "link": "https://example.org/hr-email.pdf",
            "summary": "Email reporting discrimination to HR.",
        }
    ]
    assert result["draft"]["affidavit"]["venue_lines"] == ["State of California", "County of San Francisco"]
    assert result["draft"]["affidavit"]["jurat"] == "Subscribed and sworn to before me on March 13, 2026 by Jane Doe."
    assert result["draft"]["affidavit"]["notary_block"][1] == "Notary Public for the State of California"
    assert "AFFIDAVIT OF JANE DOE REGARDING RETALIATION" in result["draft"]["draft_text"]


def test_formal_complaint_document_builder_can_suppress_mirrored_affidavit_exhibits(tmp_path):
    mediator = _build_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)

    result = builder.build_package(
        district="Northern District of California",
        county="San Francisco County",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        affidavit_include_complaint_exhibits=False,
        output_dir=str(tmp_path),
        output_formats=["txt"],
    )

    assert result["draft"]["exhibits"]
    assert result["draft"]["affidavit"]["supporting_exhibits"] == []


def test_formal_complaint_document_builder_generates_filing_packet_json(tmp_path: Path):
    mediator = _build_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)

    result = builder.build_package(
        district="Northern District of California",
        county="San Francisco County",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        output_dir=str(tmp_path),
        output_formats=["txt", "packet"],
    )

    packet_path = Path(result["artifacts"]["packet"]["path"])
    assert packet_path.exists()
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["court_header"] == "IN THE UNITED STATES DISTRICT COURT FOR THE NORTHERN DISTRICT OF CALIFORNIA"
    assert packet["case_caption"]["plaintiffs"] == ["Jane Doe"]
    assert packet["sections"]["summary_of_facts"]
    assert packet["sections"]["claims_for_relief"]
    assert packet["affidavit"]["knowledge_graph_note"].startswith(
        "This affidavit is generated from the complaint intake knowledge graph"
    )
    assert packet["certificate_of_service"]["title"] == "Certificate of Service"
    assert packet["artifacts"]["txt"]["filename"].endswith(".txt")


def test_review_api_registers_formal_complaint_document_route():
    mediator = Mock()
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = DEFAULT_OUTPUT_DIR / 'test-formal-complaint.docx'
    artifact_path.write_bytes(b'test artifact')
    try:
        mediator.build_formal_complaint_document_package.return_value = {
            "draft": {"title": "Jane Doe v. Acme Corporation"},
            "filing_checklist": [
                {"scope": "claim", "key": "retaliation", "title": "Retaliation", "status": "ready", "summary": "Retaliation is ready for filing review."}
            ],
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
                "county": "Washington County",
                "plaintiff_names": ["Jane Doe"],
                "defendant_names": ["Acme Corporation"],
                "lead_case_number": "24-cv-00077",
                "related_case_number": "24-cv-00110",
                "assigned_judge": "Hon. Maria Valdez",
                "courtroom": "Courtroom 4A",
                "signer_name": "Jane Doe",
                "signer_title": "Counsel for Plaintiff",
                "signer_firm": "Doe Legal Advocacy PLLC",
                "signer_bar_number": "DC-10101",
                "signer_contact": "123 Main Street\nWashington, DC 20001",
                "additional_signers": [
                    {
                        "name": "John Roe, Esq.",
                        "title": "Co-Counsel for Plaintiff",
                        "firm": "Roe Civil Rights Group",
                        "bar_number": "DC-20202",
                        "contact": "456 Side Street\nWashington, DC 20002",
                    }
                ],
                "declarant_name": "Jane Doe",
                "affidavit_title": "AFFIDAVIT OF JANE DOE REGARDING RETALIATION",
                "affidavit_intro": "I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation.",
                "affidavit_facts": [
                    "I reported discrimination to human resources on March 3, 2026.",
                    "Defendant terminated my employment two days later.",
                ],
                "affidavit_supporting_exhibits": [
                    {
                        "label": "Affidavit Ex. 1",
                        "title": "HR Complaint Email",
                        "link": "https://example.org/hr-email.pdf",
                        "summary": "Email reporting discrimination to HR.",
                    }
                ],
                "affidavit_include_complaint_exhibits": False,
                "affidavit_venue_lines": ["State of California", "County of San Francisco"],
                "affidavit_jurat": "Subscribed and sworn to before me on March 13, 2026 by Jane Doe.",
                "affidavit_notary_block": [
                    "__________________________________",
                    "Notary Public for the State of California",
                    "My commission expires: March 13, 2029",
                ],
                "service_method": "CM/ECF",
                "service_recipients": ["Registered Agent for Acme Corporation", "Defense Counsel"],
                "service_recipient_details": [
                    {"recipient": "Defense Counsel", "method": "Email", "address": "counsel@example.com"},
                    {"recipient": "Registered Agent for Acme Corporation", "method": "Certified Mail", "address": "123 Main Street"},
                ],
                "jury_demand": True,
                "jury_demand_text": "Plaintiff demands a trial by jury on all issues so triable.",
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
        assert response.json()["review_links"]["claims"][0]["review_intent"] == {
            "user_id": None,
            "claim_type": "retaliation",
            "section": None,
            "follow_up_support_kind": None,
            "review_url": "/claim-support-review?claim_type=retaliation",
        }
        assert response.json()["review_links"]["sections"] == []
        assert response.json()["filing_checklist"][0]["review_url"] == "/claim-support-review?claim_type=retaliation"
        assert response.json()["filing_checklist"][0]["review_context"] == {
            "user_id": None,
            "claim_type": "retaliation",
        }
        assert response.json()["filing_checklist"][0]["review_intent"] == {
            "user_id": None,
            "claim_type": "retaliation",
            "section": None,
            "follow_up_support_kind": None,
            "review_url": "/claim-support-review?claim_type=retaliation",
        }
        assert response.json()["drafting_readiness"]["claims"][0]["review_context"] == {
            "user_id": None,
            "claim_type": "retaliation",
        }
        assert response.json()["drafting_readiness"]["claims"][0]["review_intent"] == {
            "user_id": None,
            "claim_type": "retaliation",
            "section": None,
            "follow_up_support_kind": None,
            "review_url": "/claim-support-review?claim_type=retaliation",
        }
        assert response.json()["review_intent"] == {
            "user_id": None,
            "claim_type": None,
            "section": None,
            "follow_up_support_kind": None,
            "review_url": "/claim-support-review",
        }
        mediator.build_formal_complaint_document_package.assert_called_once_with(
            user_id=None,
            court_name="United States District Court",
            district="District of Columbia",
            county="Washington County",
            division=None,
            court_header_override=None,
            case_number=None,
            lead_case_number="24-cv-00077",
            related_case_number="24-cv-00110",
            assigned_judge="Hon. Maria Valdez",
            courtroom="Courtroom 4A",
            title_override=None,
            plaintiff_names=["Jane Doe"],
            defendant_names=["Acme Corporation"],
            requested_relief=[],
            jury_demand=True,
            jury_demand_text="Plaintiff demands a trial by jury on all issues so triable.",
            signer_name="Jane Doe",
            signer_title="Counsel for Plaintiff",
            signer_firm="Doe Legal Advocacy PLLC",
            signer_bar_number="DC-10101",
            signer_contact="123 Main Street\nWashington, DC 20001",
            additional_signers=[
                {
                    "name": "John Roe, Esq.",
                    "title": "Co-Counsel for Plaintiff",
                    "firm": "Roe Civil Rights Group",
                    "bar_number": "DC-20202",
                    "contact": "456 Side Street\nWashington, DC 20002",
                }
            ],
            declarant_name="Jane Doe",
            affidavit_title="AFFIDAVIT OF JANE DOE REGARDING RETALIATION",
            affidavit_intro="I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation.",
            affidavit_facts=[
                "I reported discrimination to human resources on March 3, 2026.",
                "Defendant terminated my employment two days later.",
            ],
            affidavit_supporting_exhibits=[
                {
                    "label": "Affidavit Ex. 1",
                    "title": "HR Complaint Email",
                    "link": "https://example.org/hr-email.pdf",
                    "summary": "Email reporting discrimination to HR.",
                }
            ],
            affidavit_include_complaint_exhibits=False,
            affidavit_venue_lines=["State of California", "County of San Francisco"],
            affidavit_jurat="Subscribed and sworn to before me on March 13, 2026 by Jane Doe.",
            affidavit_notary_block=[
                "__________________________________",
                "Notary Public for the State of California",
                "My commission expires: March 13, 2029",
            ],
            enable_agentic_optimization=False,
            optimization_max_iterations=2,
            optimization_target_score=0.9,
            optimization_provider=None,
            optimization_model_name=None,
            optimization_persist_artifacts=False,
            service_method="CM/ECF",
            service_recipients=["Registered Agent for Acme Corporation", "Defense Counsel"],
            service_recipient_details=[
                {"recipient": "Defense Counsel", "method": "Email", "address": "counsel@example.com"},
                {"recipient": "Registered Agent for Acme Corporation", "method": "Certified Mail", "address": "123 Main Street"},
            ],
            signature_date="2026-03-12",
            verification_date="2026-03-12",
            service_date="2026-03-13",
            output_dir=None,
            output_formats=["docx"],
        )
    finally:
        artifact_path.unlink(missing_ok=True)


def test_review_api_applies_full_affidavit_override_payload_end_to_end(tmp_path):
    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )

    app = create_review_api_app(mediator)
    client = TestClient(app)

    response = client.post(
        "/api/documents/formal-complaint",
        json={
            "district": "Northern District of California",
            "county": "San Francisco County",
            "plaintiff_names": ["Jane Doe"],
            "defendant_names": ["Acme Corporation"],
            "declarant_name": "Jane Doe",
            "affidavit_title": "AFFIDAVIT OF JANE DOE REGARDING RETALIATION",
            "affidavit_intro": "I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation.",
            "affidavit_facts": [
                "I reported discrimination to human resources on March 3, 2026.",
                "Defendant terminated my employment two days later.",
            ],
            "affidavit_supporting_exhibits": [
                {
                    "label": "Affidavit Ex. 1",
                    "title": "HR Complaint Email",
                    "link": "https://example.org/hr-email.pdf",
                    "summary": "Email reporting discrimination to HR.",
                }
            ],
            "affidavit_include_complaint_exhibits": False,
            "affidavit_venue_lines": ["State of California", "County of San Francisco"],
            "affidavit_jurat": "Subscribed and sworn to before me on March 13, 2026 by Jane Doe.",
            "affidavit_notary_block": [
                "__________________________________",
                "Notary Public for the State of California",
                "My commission expires: March 13, 2029",
            ],
            "output_formats": ["txt"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    affidavit = payload["draft"]["affidavit"]

    assert affidavit["title"] == "AFFIDAVIT OF JANE DOE REGARDING RETALIATION"
    assert affidavit["intro"] == "I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation."
    assert affidavit["facts"] == [
        "I reported discrimination to human resources on March 3, 2026.",
        "Defendant terminated my employment two days later.",
    ]
    assert affidavit["supporting_exhibits"] == [
        {
            "label": "Affidavit Ex. 1",
            "title": "HR Complaint Email",
            "link": "https://example.org/hr-email.pdf",
            "summary": "Email reporting discrimination to HR.",
        }
    ]
    assert affidavit["venue_lines"] == ["State of California", "County of San Francisco"]
    assert affidavit["jurat"] == "Subscribed and sworn to before me on March 13, 2026 by Jane Doe."
    assert affidavit["notary_block"] == [
        "__________________________________",
        "Notary Public for the State of California",
        "My commission expires: March 13, 2029",
    ]
    assert payload["draft"]["exhibits"]
    assert affidavit["supporting_exhibits"][0]["label"] == "Affidavit Ex. 1"
    assert payload["artifacts"]["txt"]["path"]

    Path(payload["artifacts"]["txt"]["path"]).unlink(missing_ok=True)


def test_review_api_forwards_optimization_llm_config_to_mediator():
    mediator = Mock()
    mediator.build_formal_complaint_document_package.return_value = {
        "draft": {"title": "Jane Doe v. Acme Corporation"},
        "drafting_readiness": {"status": "ready", "sections": {}, "claims": [], "warning_count": 0},
        "filing_checklist": [],
        "artifacts": {},
        "output_formats": ["txt"],
        "generated_at": "2026-03-13T12:00:00+00:00",
    }

    app = create_review_api_app(mediator)
    client = TestClient(app)

    response = client.post(
        "/api/documents/formal-complaint",
        json={
            "district": "Northern District of California",
            "county": "San Francisco County",
            "plaintiff_names": ["Jane Doe"],
            "defendant_names": ["Acme Corporation"],
            "enable_agentic_optimization": True,
            "optimization_provider": "huggingface_router",
            "optimization_model_name": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
            "optimization_llm_config": {
                "base_url": "https://router.huggingface.co/v1",
                "headers": {"X-Title": "Complaint Generator API Test"},
                "arch_router": {
                    "enabled": True,
                    "routes": {
                        "legal_reasoning": "meta-llama/Llama-3.3-70B-Instruct",
                        "drafting": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
                    },
                },
            },
            "output_formats": ["txt"],
        },
    )

    assert response.status_code == 200
    mediator.build_formal_complaint_document_package.assert_called_once()
    kwargs = mediator.build_formal_complaint_document_package.call_args.kwargs
    assert kwargs["enable_agentic_optimization"] is True
    assert kwargs["optimization_provider"] == "huggingface_router"
    assert kwargs["optimization_model_name"] == "Qwen/Qwen3-Coder-480B-A35B-Instruct"
    assert kwargs["optimization_llm_config"] == {
        "base_url": "https://router.huggingface.co/v1",
        "headers": {"X-Title": "Complaint Generator API Test"},
        "arch_router": {
            "enabled": True,
            "routes": {
                "legal_reasoning": "meta-llama/Llama-3.3-70B-Instruct",
                "drafting": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
            },
        },
    }


def test_review_api_returns_document_optimization_contract_end_to_end(monkeypatch: pytest.MonkeyPatch):
    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )

    calls = {"critic": 0, "actor": 0}

    class _FakeEmbeddingsRouter:
        def embed_text(self, text: str):
            lowered = text.lower()
            return [
                float("retaliation" in lowered),
                float("terminated" in lowered or "fired" in lowered),
                float(len(text.split())),
            ]

    def _fake_generate_text(prompt: str, *, provider=None, model_name=None, **kwargs):
        if document_optimization.AgenticDocumentOptimizer.CRITIC_PROMPT_TAG in prompt:
            calls["critic"] += 1
            if calls["critic"] == 1:
                payload = {
                    "overall_score": 0.52,
                    "dimension_scores": {
                        "completeness": 0.55,
                        "grounding": 0.6,
                        "coherence": 0.45,
                        "procedural": 0.7,
                        "renderability": 0.3,
                    },
                    "strengths": ["Support packets are available."],
                    "weaknesses": ["Factual allegations should be more pleading-ready."],
                    "suggestions": ["Rewrite factual allegations into declarative prose anchored in the support record."],
                    "recommended_focus": "factual_allegations",
                }
            else:
                payload = {
                    "overall_score": 0.91,
                    "dimension_scores": {
                        "completeness": 0.9,
                        "grounding": 0.92,
                        "coherence": 0.9,
                        "procedural": 0.93,
                        "renderability": 0.9,
                    },
                    "strengths": ["Factual allegations now read like pleading paragraphs."],
                    "weaknesses": [],
                    "suggestions": [],
                    "recommended_focus": "claims_for_relief",
                }
            return {
                "status": "available",
                "text": json.dumps(payload),
                "provider_name": provider,
                "model_name": model_name,
                "effective_provider_name": "openrouter",
                "effective_model_name": "meta-llama/Llama-3.3-70B-Instruct",
                "router_base_url": kwargs.get("base_url"),
                "arch_router_status": "selected",
                "arch_router_selected_route": "legal_reasoning",
                "arch_router_selected_model": "meta-llama/Llama-3.3-70B-Instruct",
                "arch_router_model_name": "katanemo/Arch-Router-1.5B",
            }

        calls["actor"] += 1
        payload = {
            "factual_allegations": [
                "Plaintiff reported discrimination to human resources.",
                "Plaintiff was fired two days later and lost pay and benefits.",
                "As to Retaliation, Defendant terminated Plaintiff shortly after the protected complaint.",
            ],
            "claim_supporting_facts": {
                "retaliation": [
                    "Plaintiff complained to human resources about race discrimination.",
                    "Defendant terminated Plaintiff shortly after the complaint.",
                ]
            },
        }
        return {
            "status": "available",
            "text": json.dumps(payload),
            "provider_name": provider,
            "model_name": model_name,
            "effective_provider_name": "openrouter",
            "effective_model_name": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
            "router_base_url": kwargs.get("base_url"),
            "arch_router_status": "selected",
            "arch_router_selected_route": "drafting",
            "arch_router_selected_model": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
            "arch_router_model_name": "katanemo/Arch-Router-1.5B",
        }

    def _fake_store_bytes(data: bytes, *, pin_content: bool = True):
        return {"status": "available", "cid": "bafy-doc-opt-report", "size": len(data), "pinned": pin_content}

    monkeypatch.setattr(document_optimization, "LLM_ROUTER_AVAILABLE", True)
    monkeypatch.setattr(document_optimization, "EMBEDDINGS_AVAILABLE", True)
    monkeypatch.setattr(document_optimization, "IPFS_AVAILABLE", True)
    monkeypatch.setattr(document_optimization, "generate_text_with_metadata", _fake_generate_text)
    monkeypatch.setattr(document_optimization, "get_embeddings_router", lambda *args, **kwargs: _FakeEmbeddingsRouter())
    monkeypatch.setattr(document_optimization, "store_bytes", _fake_store_bytes)

    app = create_review_api_app(mediator)
    client = TestClient(app)

    response = client.post(
        "/api/documents/formal-complaint",
        json={
            "district": "Northern District of California",
            "county": "San Francisco County",
            "plaintiff_names": ["Jane Doe"],
            "defendant_names": ["Acme Corporation"],
            "enable_agentic_optimization": True,
            "optimization_max_iterations": 2,
            "optimization_target_score": 0.9,
            "optimization_provider": "test-provider",
            "optimization_model_name": "test-model",
            "optimization_llm_config": {
                "base_url": "https://router.huggingface.co/v1",
                "headers": {"X-Title": "Complaint Generator API Contract Test"},
                "arch_router": {
                    "enabled": True,
                    "routes": {
                        "legal_reasoning": "meta-llama/Llama-3.3-70B-Instruct",
                        "drafting": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
                    },
                },
                "timeout": 45,
            },
            "optimization_persist_artifacts": True,
            "output_formats": ["txt"],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    report = payload["document_optimization"]

    assert report["status"] == "optimized"
    assert report["method"] == "actor_mediator_critic_optimizer"
    assert report["optimizer_backend"] in {"upstream_agentic", "local_fallback"}
    assert report["initial_score"] < report["final_score"]
    assert report["iteration_count"] >= 1
    assert report["accepted_iterations"] >= 1
    assert report["optimized_sections"] == ["factual_allegations"]
    assert report["artifact_cid"] == "bafy-doc-opt-report"
    assert report["trace_storage"] == {
        "status": "available",
        "cid": "bafy-doc-opt-report",
        "size": report["trace_storage"]["size"],
        "pinned": True,
    }
    assert report["router_status"] == {
        "llm_router": "available",
        "embeddings_router": "available",
        "ipfs_router": "available",
        "optimizers_agentic": report["router_status"]["optimizers_agentic"],
    }
    assert report["router_status"]["optimizers_agentic"] in {"available", "unavailable"}
    assert report["upstream_optimizer"]["available"] in {True, False}
    assert "selected_provider" in report["upstream_optimizer"]
    assert "selected_method" in report["upstream_optimizer"]
    assert "control_loop" in report["upstream_optimizer"]
    assert report["packet_projection"]["section_presence"]["factual_allegations"] is True
    assert report["packet_projection"]["has_affidavit"] is True
    assert report["packet_projection"]["has_certificate_of_service"] is True
    assert len(report["section_history"]) >= 1
    assert report["section_history"][0]["focus_section"] == "factual_allegations"
    assert report["section_history"][0]["accepted"] is True
    assert report["section_history"][0]["overall_score"] >= 0.0
    assert report["section_history"][0]["critic_llm_metadata"]["arch_router_selected_route"] == "legal_reasoning"
    assert report["section_history"][0]["actor_llm_metadata"]["arch_router_selected_route"] == "drafting"
    assert report["section_history"][0]["selected_support_context"]["focus_section"] == "factual_allegations"
    assert report["initial_review"]["llm_metadata"]["effective_provider_name"] == "openrouter"
    assert report["final_review"]["llm_metadata"]["arch_router_model_name"] == "katanemo/Arch-Router-1.5B"
    assert report["draft"]["draft_text"]
    assert "Plaintiff was fired two days later and lost pay and benefits." in report["draft"]["draft_text"]
    assert payload["draft"]["draft_text"] == report["draft"]["draft_text"]
    assert payload["artifacts"]["txt"]["path"]
    assert calls["critic"] >= 2
    assert calls["actor"] >= 1

    Path(payload["artifacts"]["txt"]["path"]).unlink(missing_ok=True)
    Path(payload["artifacts"]["affidavit_txt"]["path"]).unlink(missing_ok=True)


@pytest.mark.llm
@pytest.mark.network
def test_review_api_live_huggingface_router_optimization_smoke(tmp_path):
    if not document_optimization.LLM_ROUTER_AVAILABLE:
        pytest.skip("llm_router unavailable for live optimization smoke test")

    if not _live_hf_token():
        pytest.skip("Set HF_TOKEN or HUGGINGFACE_HUB_TOKEN to run the live Hugging Face router API smoke test")

    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )

    app = create_review_api_app(mediator)
    client = TestClient(app)
    model_name = os.getenv("HF_ROUTER_SMOKE_MODEL", "meta-llama/Llama-3.1-8B-Instruct")

    response = client.post(
        "/api/documents/formal-complaint",
        json={
            "district": "Northern District of California",
            "county": "San Francisco County",
            "plaintiff_names": ["Jane Doe"],
            "defendant_names": ["Acme Corporation"],
            "enable_agentic_optimization": True,
            "optimization_max_iterations": 1,
            "optimization_target_score": 1.1,
            "optimization_provider": "huggingface_router",
            "optimization_model_name": model_name,
            "optimization_llm_config": {
                "base_url": "https://router.huggingface.co/v1",
                "headers": {"X-Title": "Complaint Generator API Smoke Test"},
                "timeout": 45,
            },
            "output_dir": str(tmp_path),
            "output_formats": ["txt"],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["document_optimization"]["router_status"]["llm_router"] == "available"
    assert payload["document_optimization"]["iteration_count"] == 1
    assert payload["document_optimization"]["initial_score"] >= 0.0
    assert payload["document_optimization"]["final_score"] >= 0.0
    assert payload["document_optimization"]["trace_storage"]["status"] == "disabled"
    assert payload["document_optimization"]["draft"]["draft_text"]
    assert payload["artifacts"]["txt"]["path"]

    Path(payload["artifacts"]["txt"]["path"]).unlink(missing_ok=True)


def test_review_api_generated_docx_preserves_grouped_factual_headings_end_to_end(tmp_path):
    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )

    app = create_review_api_app(mediator)
    client = TestClient(app)

    response = client.post(
        "/api/documents/formal-complaint",
        json={
            "district": "Northern District of California",
            "county": "San Francisco County",
            "plaintiff_names": ["Jane Doe"],
            "defendant_names": ["Acme Corporation"],
            "output_dir": str(tmp_path),
            "output_formats": ["docx"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    docx_path = Path(payload["artifacts"]["docx"]["path"])
    assert docx_path.exists()
    with zipfile.ZipFile(docx_path) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "Protected Activity and Complaints" in document_xml
    assert "Adverse Action and Retaliatory Conduct" in document_xml

    docx_path.unlink(missing_ok=True)


def test_review_api_can_suppress_mirrored_affidavit_exhibits_end_to_end(tmp_path):
    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )

    app = create_review_api_app(mediator)
    client = TestClient(app)

    response = client.post(
        "/api/documents/formal-complaint",
        json={
            "district": "Northern District of California",
            "county": "San Francisco County",
            "plaintiff_names": ["Jane Doe"],
            "defendant_names": ["Acme Corporation"],
            "declarant_name": "Jane Doe",
            "affidavit_include_complaint_exhibits": False,
            "output_formats": ["txt"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["draft"]["exhibits"]
    assert payload["draft"]["affidavit"]["supporting_exhibits"] == []
    assert payload["artifacts"]["txt"]["path"]

    Path(payload["artifacts"]["txt"]["path"]).unlink(missing_ok=True)


def test_review_api_multiclaim_section_links_include_targeted_claim_urls():
    mediator = Mock()
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = DEFAULT_OUTPUT_DIR / 'multi-claim-formal-complaint.docx'
    artifact_path.write_bytes(b'test artifact')
    try:
        mediator.build_formal_complaint_document_package.return_value = {
            "draft": {"title": "Jane Doe v. Acme Corporation"},
            "filing_checklist": [
                {"scope": "section", "key": "claims_for_relief", "title": "Claims for Relief", "status": "warning", "summary": "Review Claims for Relief before filing."},
                {"scope": "claim", "key": "retaliation", "title": "Retaliation", "status": "warning", "summary": "Review Retaliation before filing."},
            ],
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
        assert payload["review_links"]["sections"][0]["review_intent"] == {
            "user_id": None,
            "claim_type": None,
            "section": "claims_for_relief",
            "follow_up_support_kind": "authority",
            "review_url": "/claim-support-review?section=claims_for_relief",
        }
        assert payload["review_links"]["sections"][0]["claim_links"] == [
            {
                "claim_type": "employment discrimination",
                "review_url": "/claim-support-review?claim_type=employment+discrimination&section=claims_for_relief",
                "review_intent": {
                    "user_id": None,
                    "claim_type": "employment discrimination",
                    "section": "claims_for_relief",
                    "follow_up_support_kind": "authority",
                    "review_url": "/claim-support-review?claim_type=employment+discrimination&section=claims_for_relief",
                },
            },
            {
                "claim_type": "retaliation",
                "review_url": "/claim-support-review?claim_type=retaliation&section=claims_for_relief",
                "review_intent": {
                    "user_id": None,
                    "claim_type": "retaliation",
                    "section": "claims_for_relief",
                    "follow_up_support_kind": "authority",
                    "review_url": "/claim-support-review?claim_type=retaliation&section=claims_for_relief",
                },
            },
        ]
        assert payload["drafting_readiness"]["sections"]["claims_for_relief"]["review_context"] == {
            "user_id": None,
            "section": "claims_for_relief",
            "claim_type": None,
        }
        assert payload["drafting_readiness"]["sections"]["claims_for_relief"]["review_intent"] == {
            "user_id": None,
            "claim_type": None,
            "section": "claims_for_relief",
            "follow_up_support_kind": "authority",
            "review_url": "/claim-support-review?section=claims_for_relief",
        }
        assert payload["filing_checklist"][0]["review_url"] == "/claim-support-review?section=claims_for_relief"
        assert payload["filing_checklist"][0]["review_intent"] == {
            "user_id": None,
            "claim_type": None,
            "section": "claims_for_relief",
            "follow_up_support_kind": "authority",
            "review_url": "/claim-support-review?section=claims_for_relief",
        }
        assert payload["filing_checklist"][1]["review_url"] == "/claim-support-review?claim_type=retaliation"
        assert payload["filing_checklist"][1]["review_intent"] == {
            "user_id": None,
            "claim_type": "retaliation",
            "section": None,
            "follow_up_support_kind": None,
            "review_url": "/claim-support-review?claim_type=retaliation",
        }
        assert payload["drafting_readiness"]["sections"]["claims_for_relief"]["claim_links"] == [
            {
                "claim_type": "employment discrimination",
                "review_url": "/claim-support-review?claim_type=employment+discrimination&section=claims_for_relief",
                "review_intent": {
                    "user_id": None,
                    "claim_type": "employment discrimination",
                    "section": "claims_for_relief",
                    "follow_up_support_kind": "authority",
                    "review_url": "/claim-support-review?claim_type=employment+discrimination&section=claims_for_relief",
                },
            },
            {
                "claim_type": "retaliation",
                "review_url": "/claim-support-review?claim_type=retaliation&section=claims_for_relief",
                "review_intent": {
                    "user_id": None,
                    "claim_type": "retaliation",
                    "section": "claims_for_relief",
                    "follow_up_support_kind": "authority",
                    "review_url": "/claim-support-review?claim_type=retaliation&section=claims_for_relief",
                },
            },
        ]
        assert payload["review_intent"] == {
            "user_id": None,
            "claim_type": "employment discrimination",
            "section": "claims_for_relief",
            "follow_up_support_kind": "authority",
            "review_url": "/claim-support-review?claim_type=employment+discrimination&section=claims_for_relief",
        }
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
                    "county": "WASHINGTON COUNTY",
                    "lead_case_number": "24-cv-00077",
                    "related_case_number": "24-cv-00110",
                    "assigned_judge": "Hon. Maria Valdez",
                    "courtroom": "Courtroom 4A",
                    "jury_demand_notice": "JURY TRIAL DEMANDED",
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
        assert 'value="checklist"' in page_html
        assert 'value="packet"' in page_html
        assert 'Drafting Readiness' in page_html
        assert 'Pre-Filing Checklist' in page_html
        assert 'Open Checklist Review' in page_html
        assert 'Section Readiness' in page_html
        assert 'Claim Readiness' in page_html
        assert 'Source Drilldown' in page_html
        assert 'Source Context:' in page_html
        assert 'Source families:' in page_html
        assert 'Factual Allegations' in page_html
        assert 'Incorporated Support' in page_html
        assert 'Supporting Exhibit Details' in page_html
        assert 'Open filing warnings' in page_html
        assert 'pleading-paragraphs' in page_html
        assert 'Verification Declarant' in page_html
        assert 'Service Recipients' in page_html
        assert 'Enable agentic draft optimization before rendering artifacts' in page_html
        assert 'Optimization Iterations' in page_html
        assert 'Optimization Target Score' in page_html
        assert 'Optimization Provider' in page_html
        assert 'Optimization Model' in page_html
        assert 'Optimization Router Base URL' in page_html
        assert 'Optimization Timeout (seconds)' in page_html
        assert 'Persist optimization trace through the IPFS adapter' in page_html
        assert 'Document Optimization' in page_html
        assert 'Optimized Sections' in page_html
        assert 'Trace CID' in page_html
        assert 'Section History' in page_html

        api_response = client.post(
            '/api/documents/formal-complaint',
            json={
                'district': 'District of Columbia',
                'county': 'Washington County',
                'case_number': '25-cv-00001',
                'lead_case_number': '24-cv-00077',
                'related_case_number': '24-cv-00110',
                'assigned_judge': 'Hon. Maria Valdez',
                'courtroom': 'Courtroom 4A',
                'plaintiff_names': ['Jane Doe'],
                'defendant_names': ['Acme Corporation'],
                'output_formats': ['docx'],
            },
        )

        assert api_response.status_code == 200
        payload = api_response.json()
        assert payload['draft']['title'] == 'Jane Doe v. Acme Corporation'
        assert payload['draft']['case_caption']['case_number'] == '25-cv-00001'
        assert payload['draft']['case_caption']['county'] == 'WASHINGTON COUNTY'
        assert payload['draft']['case_caption']['lead_case_number'] == '24-cv-00077'
        assert payload['draft']['case_caption']['related_case_number'] == '24-cv-00110'
        assert payload['draft']['case_caption']['assigned_judge'] == 'Hon. Maria Valdez'
        assert payload['draft']['case_caption']['courtroom'] == 'Courtroom 4A'
        assert payload['draft']['case_caption']['jury_demand_notice'] == 'JURY TRIAL DEMANDED'
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


def test_review_surface_document_builder_supports_affidavit_exhibit_controls_end_to_end(tmp_path):
    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )
    app = create_review_surface_app(mediator)
    client = TestClient(app)

    page_response = client.get('/document')

    assert page_response.status_code == 200
    page_html = page_response.text
    assert 'Mirror complaint exhibits into affidavit when no affidavit-specific exhibit list is provided' in page_html
    assert 'Affidavit Exhibit Source:' in page_html

    api_response = client.post(
        '/api/documents/formal-complaint',
        json={
            'district': 'Northern District of California',
            'county': 'San Francisco County',
            'plaintiff_names': ['Jane Doe'],
            'defendant_names': ['Acme Corporation'],
            'declarant_name': 'Jane Doe',
            'affidavit_title': 'AFFIDAVIT OF JANE DOE REGARDING RETALIATION',
            'affidavit_intro': "I, Jane Doe, make this affidavit from personal knowledge regarding Defendant's retaliation.",
            'affidavit_facts': [
                'I reported discrimination to human resources on March 3, 2026.',
                'Defendant terminated my employment two days later.',
            ],
            'affidavit_supporting_exhibits': [
                {
                    'label': 'Affidavit Ex. 1',
                    'title': 'HR Complaint Email',
                    'link': 'https://example.org/hr-email.pdf',
                    'summary': 'Email reporting discrimination to HR.',
                }
            ],
            'affidavit_include_complaint_exhibits': False,
            'affidavit_venue_lines': ['State of California', 'County of San Francisco'],
            'affidavit_jurat': 'Subscribed and sworn to before me on March 13, 2026 by Jane Doe.',
            'affidavit_notary_block': [
                '__________________________________',
                'Notary Public for the State of California',
                'My commission expires: March 13, 2029',
            ],
            'output_formats': ['txt'],
        },
    )

    assert api_response.status_code == 200
    payload = api_response.json()
    assert payload['draft']['affidavit']['title'] == 'AFFIDAVIT OF JANE DOE REGARDING RETALIATION'
    assert payload['draft']['affidavit']['supporting_exhibits'] == [
        {
            'label': 'Affidavit Ex. 1',
            'title': 'HR Complaint Email',
            'link': 'https://example.org/hr-email.pdf',
            'summary': 'Email reporting discrimination to HR.',
        }
    ]
    assert payload['draft']['exhibits']
    assert payload['artifacts']['txt']['download_url'].startswith('/api/documents/download?path=')

    Path(payload['artifacts']['txt']['path']).unlink(missing_ok=True)


def test_review_surface_document_builder_forwards_optimization_llm_config_to_mediator():
    mediator = Mock()
    mediator.build_formal_complaint_document_package.return_value = {
        "draft": {"title": "Jane Doe v. Acme Corporation"},
        "drafting_readiness": {"status": "ready", "sections": {}, "claims": [], "warning_count": 0},
        "filing_checklist": [],
        "artifacts": {},
        "output_formats": ["txt"],
        "generated_at": "2026-03-13T12:00:00+00:00",
    }

    app = create_review_surface_app(mediator)
    client = TestClient(app)

    response = client.post(
        '/api/documents/formal-complaint',
        json={
            'district': 'Northern District of California',
            'county': 'San Francisco County',
            'plaintiff_names': ['Jane Doe'],
            'defendant_names': ['Acme Corporation'],
            'enable_agentic_optimization': True,
            'optimization_provider': 'huggingface_router',
            'optimization_model_name': 'Qwen/Qwen3-Coder-480B-A35B-Instruct',
            'optimization_llm_config': {
                'base_url': 'https://router.huggingface.co/v1',
                'headers': {'X-Title': 'Complaint Generator Review Surface Test'},
                'arch_router': {
                    'enabled': True,
                    'routes': {
                        'legal_reasoning': 'meta-llama/Llama-3.3-70B-Instruct',
                        'drafting': 'Qwen/Qwen3-Coder-480B-A35B-Instruct',
                    },
                },
            },
            'output_formats': ['txt'],
        },
    )

    assert response.status_code == 200
    mediator.build_formal_complaint_document_package.assert_called_once()
    kwargs = mediator.build_formal_complaint_document_package.call_args.kwargs
    assert kwargs['enable_agentic_optimization'] is True
    assert kwargs['optimization_provider'] == 'huggingface_router'
    assert kwargs['optimization_model_name'] == 'Qwen/Qwen3-Coder-480B-A35B-Instruct'
    assert kwargs['optimization_llm_config'] == {
        'base_url': 'https://router.huggingface.co/v1',
        'headers': {'X-Title': 'Complaint Generator Review Surface Test'},
        'arch_router': {
            'enabled': True,
            'routes': {
                'legal_reasoning': 'meta-llama/Llama-3.3-70B-Instruct',
                'drafting': 'Qwen/Qwen3-Coder-480B-A35B-Instruct',
            },
        },
    }


def test_review_surface_returns_document_optimization_contract_end_to_end(monkeypatch: pytest.MonkeyPatch):
    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )

    calls = {'critic': 0, 'actor': 0}

    class _FakeEmbeddingsRouter:
        def embed_text(self, text: str):
            lowered = text.lower()
            return [
                float('retaliation' in lowered),
                float('terminated' in lowered or 'fired' in lowered),
                float(len(text.split())),
            ]

    def _fake_generate_text(prompt: str, *, provider=None, model_name=None, **kwargs):
        if document_optimization.AgenticDocumentOptimizer.CRITIC_PROMPT_TAG in prompt:
            calls['critic'] += 1
            if calls['critic'] == 1:
                payload = {
                    'overall_score': 0.52,
                    'dimension_scores': {
                        'completeness': 0.55,
                        'grounding': 0.6,
                        'coherence': 0.45,
                        'procedural': 0.7,
                        'renderability': 0.3,
                    },
                    'strengths': ['Support packets are available.'],
                    'weaknesses': ['Factual allegations should be more pleading-ready.'],
                    'suggestions': ['Rewrite factual allegations into declarative prose anchored in the support record.'],
                    'recommended_focus': 'factual_allegations',
                }
            else:
                payload = {
                    'overall_score': 0.91,
                    'dimension_scores': {
                        'completeness': 0.9,
                        'grounding': 0.92,
                        'coherence': 0.9,
                        'procedural': 0.93,
                        'renderability': 0.9,
                    },
                    'strengths': ['Factual allegations now read like pleading paragraphs.'],
                    'weaknesses': [],
                    'suggestions': [],
                    'recommended_focus': 'claims_for_relief',
                }
            return {
                'status': 'available',
                'text': json.dumps(payload),
                'provider_name': provider,
                'model_name': model_name,
                'effective_provider_name': 'openrouter',
                'effective_model_name': 'meta-llama/Llama-3.3-70B-Instruct',
                'router_base_url': kwargs.get('base_url'),
                'arch_router_status': 'selected',
                'arch_router_selected_route': 'legal_reasoning',
                'arch_router_selected_model': 'meta-llama/Llama-3.3-70B-Instruct',
                'arch_router_model_name': 'katanemo/Arch-Router-1.5B',
            }

        calls['actor'] += 1
        payload = {
            'factual_allegations': [
                'Plaintiff reported discrimination to human resources.',
                'Plaintiff was fired two days later and lost pay and benefits.',
                'As to Retaliation, Defendant terminated Plaintiff shortly after the protected complaint.',
            ],
            'claim_supporting_facts': {
                'retaliation': [
                    'Plaintiff complained to human resources about race discrimination.',
                    'Defendant terminated Plaintiff shortly after the complaint.',
                ]
            },
        }
        return {
            'status': 'available',
            'text': json.dumps(payload),
            'provider_name': provider,
            'model_name': model_name,
            'effective_provider_name': 'openrouter',
            'effective_model_name': 'Qwen/Qwen3-Coder-480B-A35B-Instruct',
            'router_base_url': kwargs.get('base_url'),
            'arch_router_status': 'selected',
            'arch_router_selected_route': 'drafting',
            'arch_router_selected_model': 'Qwen/Qwen3-Coder-480B-A35B-Instruct',
            'arch_router_model_name': 'katanemo/Arch-Router-1.5B',
        }

    def _fake_store_bytes(data: bytes, *, pin_content: bool = True):
        return {'status': 'available', 'cid': 'bafy-doc-opt-report', 'size': len(data), 'pinned': pin_content}

    monkeypatch.setattr(document_optimization, 'LLM_ROUTER_AVAILABLE', True)
    monkeypatch.setattr(document_optimization, 'EMBEDDINGS_AVAILABLE', True)
    monkeypatch.setattr(document_optimization, 'IPFS_AVAILABLE', True)
    monkeypatch.setattr(document_optimization, 'generate_text_with_metadata', _fake_generate_text)
    monkeypatch.setattr(document_optimization, 'get_embeddings_router', lambda *args, **kwargs: _FakeEmbeddingsRouter())
    monkeypatch.setattr(document_optimization, 'store_bytes', _fake_store_bytes)

    app = create_review_surface_app(mediator)
    client = TestClient(app)

    page_response = client.get('/document')

    assert page_response.status_code == 200
    assert '/api/documents/formal-complaint' in page_response.text

    api_response = client.post(
        '/api/documents/formal-complaint',
        json={
            'district': 'Northern District of California',
            'county': 'San Francisco County',
            'plaintiff_names': ['Jane Doe'],
            'defendant_names': ['Acme Corporation'],
            'enable_agentic_optimization': True,
            'optimization_max_iterations': 2,
            'optimization_target_score': 0.9,
            'optimization_provider': 'test-provider',
            'optimization_model_name': 'test-model',
            'optimization_llm_config': {
                'base_url': 'https://router.huggingface.co/v1',
                'headers': {'X-Title': 'Complaint Generator Review Surface Contract Test'},
                'arch_router': {
                    'enabled': True,
                    'routes': {
                        'legal_reasoning': 'meta-llama/Llama-3.3-70B-Instruct',
                        'drafting': 'Qwen/Qwen3-Coder-480B-A35B-Instruct',
                    },
                },
                'timeout': 45,
            },
            'optimization_persist_artifacts': True,
            'output_formats': ['txt'],
        },
    )

    assert api_response.status_code == 200, api_response.text
    payload = api_response.json()
    report = payload['document_optimization']

    assert report['status'] == 'optimized'
    assert report['method'] == 'actor_mediator_critic_optimizer'
    assert report['optimizer_backend'] in {'upstream_agentic', 'local_fallback'}
    assert report['initial_score'] < report['final_score']
    assert report['iteration_count'] >= 1
    assert report['accepted_iterations'] >= 1
    assert report['optimized_sections'] == ['factual_allegations']
    assert report['artifact_cid'] == 'bafy-doc-opt-report'
    assert report['trace_storage'] == {
        'status': 'available',
        'cid': 'bafy-doc-opt-report',
        'size': report['trace_storage']['size'],
        'pinned': True,
    }
    assert report['router_status'] == {
        'llm_router': 'available',
        'embeddings_router': 'available',
        'ipfs_router': 'available',
        'optimizers_agentic': report['router_status']['optimizers_agentic'],
    }
    assert report['router_status']['optimizers_agentic'] in {'available', 'unavailable'}
    assert report['upstream_optimizer']['available'] in {True, False}
    assert 'selected_provider' in report['upstream_optimizer']
    assert 'selected_method' in report['upstream_optimizer']
    assert 'control_loop' in report['upstream_optimizer']
    assert report['packet_projection']['section_presence']['factual_allegations'] is True
    assert report['packet_projection']['has_affidavit'] is True
    assert report['packet_projection']['has_certificate_of_service'] is True
    assert len(report['section_history']) >= 1
    assert report['section_history'][0]['focus_section'] == 'factual_allegations'
    assert report['section_history'][0]['accepted'] is True
    assert report['section_history'][0]['overall_score'] >= 0.0
    assert report['section_history'][0]['critic_llm_metadata']['arch_router_selected_route'] == 'legal_reasoning'
    assert report['section_history'][0]['actor_llm_metadata']['arch_router_selected_route'] == 'drafting'
    assert report['section_history'][0]['selected_support_context']['focus_section'] == 'factual_allegations'
    assert report['initial_review']['llm_metadata']['effective_provider_name'] == 'openrouter'
    assert report['final_review']['llm_metadata']['arch_router_model_name'] == 'katanemo/Arch-Router-1.5B'
    assert report['draft']['draft_text']
    assert 'Plaintiff was fired two days later and lost pay and benefits.' in report['draft']['draft_text']
    assert payload['draft']['draft_text'] == report['draft']['draft_text']
    assert payload['artifacts']['txt']['download_url'].startswith('/api/documents/download?path=')
    assert calls['critic'] >= 2
    assert calls['actor'] >= 1

    Path(payload['artifacts']['txt']['path']).unlink(missing_ok=True)
    Path(payload['artifacts']['affidavit_txt']['path']).unlink(missing_ok=True)


@pytest.mark.llm
@pytest.mark.network
def test_review_surface_live_huggingface_router_optimization_smoke(tmp_path):
    if not document_optimization.LLM_ROUTER_AVAILABLE:
        pytest.skip('llm_router unavailable for live review-surface smoke test')

    if not _live_hf_token():
        pytest.skip('Set HF_TOKEN or HUGGINGFACE_HUB_TOKEN to run the live Hugging Face router review-surface smoke test')

    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )

    app = create_review_surface_app(mediator)
    client = TestClient(app)
    model_name = os.getenv('HF_ROUTER_SMOKE_MODEL', 'meta-llama/Llama-3.1-8B-Instruct')

    page_response = client.get('/document')

    assert page_response.status_code == 200
    assert '/api/documents/formal-complaint' in page_response.text

    api_response = client.post(
        '/api/documents/formal-complaint',
        json={
            'district': 'Northern District of California',
            'county': 'San Francisco County',
            'plaintiff_names': ['Jane Doe'],
            'defendant_names': ['Acme Corporation'],
            'enable_agentic_optimization': True,
            'optimization_max_iterations': 1,
            'optimization_target_score': 1.1,
            'optimization_provider': 'huggingface_router',
            'optimization_model_name': model_name,
            'optimization_llm_config': {
                'base_url': 'https://router.huggingface.co/v1',
                'headers': {'X-Title': 'Complaint Generator Review Surface Smoke Test'},
                'timeout': 45,
            },
            'output_dir': str(tmp_path),
            'output_formats': ['txt'],
        },
    )

    assert api_response.status_code == 200, api_response.text
    payload = api_response.json()
    assert payload['document_optimization']['router_status']['llm_router'] == 'available'
    assert payload['document_optimization']['iteration_count'] == 1
    assert payload['document_optimization']['initial_score'] >= 0.0
    assert payload['document_optimization']['final_score'] >= 0.0
    assert payload['document_optimization']['trace_storage']['status'] == 'disabled'
    assert payload['draft']['draft_text']
    assert payload['artifacts']['txt']['download_url'].startswith('/api/documents/download?path=')

    Path(payload['artifacts']['txt']['path']).unlink(missing_ok=True)


def test_review_surface_document_builder_returns_packet_artifact_end_to_end(tmp_path):
    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )
    app = create_review_surface_app(mediator)
    client = TestClient(app)

    api_response = client.post(
        '/api/documents/formal-complaint',
        json={
            'district': 'Northern District of California',
            'county': 'San Francisco County',
            'plaintiff_names': ['Jane Doe'],
            'defendant_names': ['Acme Corporation'],
            'output_formats': ['packet'],
        },
    )

    assert api_response.status_code == 200
    payload = api_response.json()
    assert payload['artifacts']['packet']['download_url'].startswith('/api/documents/download?path=')
    packet_path = Path(payload['artifacts']['packet']['path'])
    packet = json.loads(packet_path.read_text(encoding='utf-8'))
    assert packet['sections']['requested_relief']
    assert packet['affidavit']['facts']

    packet_path.unlink(missing_ok=True)


def test_review_surface_generated_docx_preserves_grouped_factual_headings_end_to_end(tmp_path):
    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )
    app = create_review_surface_app(mediator)
    client = TestClient(app)

    api_response = client.post(
        '/api/documents/formal-complaint',
        json={
            'district': 'Northern District of California',
            'county': 'San Francisco County',
            'plaintiff_names': ['Jane Doe'],
            'defendant_names': ['Acme Corporation'],
            'output_dir': str(tmp_path),
            'output_formats': ['docx'],
        },
    )

    assert api_response.status_code == 200
    payload = api_response.json()
    docx_path = Path(payload['artifacts']['docx']['path'])
    assert docx_path.exists()
    with zipfile.ZipFile(docx_path) as archive:
        document_xml = archive.read('word/document.xml').decode('utf-8')
    assert 'Protected Activity and Complaints' in document_xml
    assert 'Adverse Action and Retaliatory Conduct' in document_xml

    docx_path.unlink(missing_ok=True)


def test_review_surface_document_builder_can_suppress_mirrored_affidavit_exhibits_end_to_end(tmp_path):
    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )
    app = create_review_surface_app(mediator)
    client = TestClient(app)

    api_response = client.post(
        '/api/documents/formal-complaint',
        json={
            'district': 'Northern District of California',
            'county': 'San Francisco County',
            'plaintiff_names': ['Jane Doe'],
            'defendant_names': ['Acme Corporation'],
            'declarant_name': 'Jane Doe',
            'affidavit_include_complaint_exhibits': False,
            'output_formats': ['txt'],
        },
    )

    assert api_response.status_code == 200
    payload = api_response.json()
    assert payload['draft']['exhibits']
    assert payload['draft']['affidavit']['supporting_exhibits'] == []
    assert payload['artifacts']['txt']['download_url'].startswith('/api/documents/download?path=')

    Path(payload['artifacts']['txt']['path']).unlink(missing_ok=True)