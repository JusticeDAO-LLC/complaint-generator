from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import importlib
import os
import json
import zipfile
import document_optimization
from applications import document_api

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from applications.review_api import create_review_api_app
from applications.review_ui import create_review_surface_app
from document_pipeline import DEFAULT_OUTPUT_DIR, FormalComplaintDocumentBuilder


pytestmark = pytest.mark.no_auto_network


def _live_hf_token() -> str:
    token = (
        os.getenv("HF_TOKEN", "").strip()
        or os.getenv("HUGGINGFACE_HUB_TOKEN", "").strip()
        or os.getenv("HUGGINGFACE_API_KEY", "").strip()
        or os.getenv("HF_API_TOKEN", "").strip()
    )
    if token:
        return token

    try:
        hub = importlib.import_module("huggingface_hub")
        getter = getattr(hub, "get_token", None)
        resolved = getter() if callable(getter) else ""
        if resolved is not None and str(resolved).strip():
            return str(resolved).strip()
    except Exception:
        return ""
    return ""


def _live_hf_bill_to_header() -> dict:
    bill_to = (
        os.getenv("IPFS_DATASETS_PY_HF_BILL_TO", "").strip()
        or os.getenv("HUGGINGFACE_BILL_TO", "").strip()
        or os.getenv("HF_BILL_TO", "").strip()
        or os.getenv("HF_ORGANIZATION", "").strip()
        or os.getenv("HUGGINGFACE_ORG", "").strip()
        or os.getenv("OPENROUTER_HF_BILL_TO", "").strip()
    )
    return {"X-HF-Bill-To": bill_to} if bill_to else {}


def _is_provider_credit_error(payload_or_message: object) -> bool:
    text = str(payload_or_message or "")
    lowered = text.lower()
    return "402" in lowered and ("payment required" in lowered or "included credits" in lowered or "depleted" in lowered)


def _is_upstream_router_error(payload_or_message: object) -> bool:
    text = str(payload_or_message or "")
    lowered = text.lower()
    return (
        "openrouter http" in lowered
        or "payment required" in lowered
        or "included credits" in lowered
        or "depleted" in lowered
        or "access denied" in lowered
        or "browser_signature_banned" in lowered
        or "error 1010" in lowered
        or "owner_action_required" in lowered
    )


def _hf_router_smoke_models() -> list[str]:
    configured_models = [
        candidate.strip()
        for candidate in os.getenv("HF_ROUTER_SMOKE_MODELS", "").split(",")
        if candidate.strip()
    ]
    if configured_models:
        return configured_models

    configured_model = os.getenv("HF_ROUTER_SMOKE_MODEL", "").strip()
    if configured_model:
        return [configured_model]

    return [
        "meta-llama/Llama-3.1-8B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "google/gemma-2-9b-it",
    ]


def _upstream_failure_summary(payload_or_message: object) -> str:
    if isinstance(payload_or_message, dict):
        nested_candidates = [
            payload_or_message.get("error"),
            payload_or_message.get("arch_router_error"),
        ]
        document_optimization = payload_or_message.get("document_optimization") or {}
        if isinstance(document_optimization, dict):
            for review_key in ("initial_review", "final_review"):
                llm_metadata = (document_optimization.get(review_key) or {}).get("llm_metadata") or {}
                if isinstance(llm_metadata, dict):
                    nested_candidates.extend([llm_metadata.get("error"), llm_metadata.get("arch_router_error")])
            for section_entry in document_optimization.get("section_history") or []:
                if not isinstance(section_entry, dict):
                    continue
                for metadata_key in ("critic_llm_metadata", "actor_llm_metadata"):
                    llm_metadata = section_entry.get(metadata_key) or {}
                    if isinstance(llm_metadata, dict):
                        nested_candidates.extend([llm_metadata.get("error"), llm_metadata.get("arch_router_error")])
        for candidate in nested_candidates:
            if candidate:
                text = str(candidate)
                compact = " ".join(text.split())
                return compact[:280]
    text = str(payload_or_message or "")
    compact = " ".join(text.split())
    return compact[:280]


def _document_page_inline_script(page_html: str) -> str:
    soup = BeautifulSoup(page_html, 'html.parser')
    for script in soup.find_all('script'):
        script_text = script.string or script.get_text() or ''
        if 'function validateOptimizationAdvancedConfig()' in script_text:
            return script_text
    raise AssertionError('Expected inline document page script with optimization validation hooks.')


def _assert_normalized_intake_status(
    actual: dict,
    *,
    score: float,
    current_phase: str | None = "intake",
    remaining_gap_count: int = 2,
    contradiction_count: int = 1,
    blockers: list[str] | None = None,
    include_extended_fields: bool = True,
) -> None:
    expected_blockers = blockers or ["resolve_contradictions", "collect_missing_timeline_details"]

    if current_phase is None:
        assert "current_phase" not in actual
    else:
        assert actual["current_phase"] == current_phase
    assert actual["ready_to_advance"] is False
    assert actual["score"] == score
    assert actual["remaining_gap_count"] == remaining_gap_count
    assert actual["contradiction_count"] == contradiction_count
    assert actual["blockers"] == expected_blockers
    contradiction = actual["contradictions"][0]
    assert contradiction["summary"] == "Complaint date conflicts with schedule-cut date"
    assert contradiction["left_text"] == ""
    assert contradiction["right_text"] == ""
    assert contradiction["question"] == "What were the exact dates for the complaint and schedule change?"
    assert contradiction["severity"] == "high"
    assert contradiction["category"] == ""

    if include_extended_fields:
        assert actual["contradiction_summary"] == {
            "count": 1,
            "lane_counts": {},
            "status_counts": {},
            "severity_counts": {"high": 1},
            "corroboration_required_count": 0,
            "affected_claim_type_counts": {},
            "affected_element_counts": {},
        }
        assert contradiction["contradiction_id"] == ""
        assert contradiction["recommended_resolution_lane"] == ""
        assert contradiction["current_resolution_status"] == ""
        assert contradiction["external_corroboration_required"] is False
        assert contradiction["affected_claim_types"] == []
        assert contradiction["affected_element_ids"] == []
        assert actual["criteria"] == {}
        assert actual["blocking_contradictions"] == []
        assert actual["candidate_claim_count"] == 0
        assert actual["canonical_fact_count"] == 0
        assert actual["proof_lead_count"] == 0


def _build_live_hf_optimization_request(
    *,
    model_name: str,
    output_dir: str,
    page_title: str,
    include_arch_router: bool,
) -> dict:
    optimization_llm_config = {
        "base_url": "https://router.huggingface.co/v1",
        "headers": {"X-Title": page_title, **_live_hf_bill_to_header()},
        "timeout": 45,
    }
    if include_arch_router:
        reasoning_model_name = os.getenv("HF_ROUTER_ARCH_REASONING_MODEL", "").strip() or model_name
        optimization_llm_config["arch_router"] = {
            "enabled": True,
            "model": os.getenv("HF_ARCH_ROUTER_MODEL", "katanemo/Arch-Router-1.5B"),
            "context": "Complaint drafting, legal issue spotting, and filing packet generation.",
            "routes": {
                "legal_reasoning": reasoning_model_name,
                "drafting": model_name,
            },
        }

    return {
        "district": "Northern District of California",
        "county": "San Francisco County",
        "plaintiff_names": ["Jane Doe"],
        "defendant_names": ["Acme Corporation"],
        "enable_agentic_optimization": True,
        "optimization_max_iterations": 1,
        "optimization_target_score": 1.1,
        "optimization_provider": "huggingface_router",
        "optimization_model_name": model_name,
        "optimization_llm_config": optimization_llm_config,
        "output_dir": output_dir,
        "output_formats": ["txt"],
    }


def _post_live_hf_optimization_request(
    client: TestClient,
    *,
    output_dir: str,
    page_title: str,
    include_arch_router: bool,
) -> tuple[str, object, dict, bool]:
    def _attempt_models(use_arch_router: bool) -> tuple[str, object, dict, list[str]] | tuple[None, None, None, list[str]]:
        failures: list[str] = []
        for model_name in _hf_router_smoke_models():
            try:
                response = client.post(
                    "/api/documents/formal-complaint",
                    json=_build_live_hf_optimization_request(
                        model_name=model_name,
                        output_dir=output_dir,
                        page_title=page_title,
                        include_arch_router=use_arch_router,
                    ),
                )
            except RuntimeError as exc:
                if _is_upstream_router_error(exc):
                    failures.append(f"{model_name}: {_upstream_failure_summary(exc)}")
                    continue
                raise

            payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            if response.status_code == 200 and not _is_upstream_router_error(payload):
                return model_name, response, payload, failures
            if _is_upstream_router_error(payload) or _is_upstream_router_error(response.text):
                failures.append(f"{model_name}: {_upstream_failure_summary(payload or response.text)}")
                continue
            return model_name, response, payload, failures
        return None, None, None, failures

    model_name, response, payload, failures = _attempt_models(include_arch_router)
    if model_name is not None:
        return model_name, response, payload, include_arch_router

    attempted_modes = []
    if failures:
        attempted_modes.append(
            ("with arch router" if include_arch_router else "without arch router") + ": " + " | ".join(failures)
        )

    if include_arch_router:
        model_name, response, payload, fallback_failures = _attempt_models(False)
        if model_name is not None:
            return model_name, response, payload, False
        if fallback_failures:
            attempted_modes.append("without arch router: " + " | ".join(fallback_failures))

    pytest.skip("Hugging Face router live smoke unavailable after trying models: " + " ; ".join(attempted_modes))


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
    mediator.get_claim_support_validation.side_effect = lambda claim_type=None, user_id=None: {
        "claims": {
            claim_type: {
                "claim_type": claim_type,
                "elements": [
                    {
                        "element_id": f"{claim_type or 'claim'}_element_001",
                        "element_text": "Causal connection" if claim_type == "retaliation" else "Adverse employment action",
                        "validation_status": "supported",
                        "reasoning_diagnostics": (
                            {
                                "backend_available_count": 1,
                                "predicate_count": 2,
                                "hybrid_reasoning": {
                                    "result": {
                                        "compiler_bridge_available": True,
                                        "formalism": "tdfol_dcec_bridge_v1",
                                        "reasoning_mode": "temporal_bridge",
                                        "proof_artifact": {
                                            "available": True,
                                            "status": "available",
                                            "proof_id": "proof-retaliation-001",
                                            "proof_status": "success",
                                            "sentence": "show protected activity preceded termination",
                                            "explanation": {
                                                "format": "plain_text",
                                                "text": "Protected activity preceded termination.",
                                            },
                                        },
                                    }
                                },
                            }
                            if claim_type == "retaliation"
                            else {"backend_available_count": 0, "predicate_count": 0}
                        ),
                    }
                ],
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
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "iteration_count": 1,
        "candidate_claims": [
            {"claim_type": "employment discrimination", "label": "Employment Discrimination", "confidence": 0.82},
            {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.8},
        ],
        "intake_sections": {
            "chronology": {"status": "complete", "missing_items": []},
            "proof_leads": {"status": "partial", "missing_items": ["documents"]},
        },
        "canonical_fact_summary": {
            "count": 2,
            "facts": [{"fact_id": "fact_001"}, {"fact_id": "fact_002"}],
        },
        "proof_lead_summary": {
            "count": 1,
            "proof_leads": [{"lead_id": "lead_001"}],
        },
        "question_candidate_summary": {
            "count": 1,
            "candidates": [{"candidate_source": "intake_proof_gap"}],
            "source_counts": {"intake_proof_gap": 1},
            "question_goal_counts": {"identify_supporting_proof": 1},
            "phase1_section_counts": {"proof_leads": 1},
            "blocking_level_counts": {"important": 1},
        },
        "alignment_evidence_tasks": [
            {
                "task_id": "retaliation:causation:fill_evidence_gaps",
                "action": "fill_temporal_chronology_gap",
                "claim_type": "retaliation",
                "claim_element_id": "causation",
                "claim_element_label": "Causal connection",
                "support_status": "unsupported",
                "blocking": True,
                "preferred_support_kind": "evidence",
                "fallback_lanes": ["authority", "testimony"],
                "source_quality_target": "high_quality_document",
                "resolution_status": "still_open",
                "resolution_notes": "",
                "event_ids": ["event_001"],
                "temporal_fact_ids": ["fact_001"],
                "temporal_relation_ids": ["timeline_relation_001"],
                "timeline_issue_ids": ["temporal_issue_001"],
                "temporal_issue_ids": ["temporal_issue_001"],
                "temporal_proof_bundle_id": "retaliation:causation:bundle_001",
                "temporal_proof_objective": "establish_retaliation_sequence",
            }
        ],
        "alignment_task_summary": {
            "count": 1,
            "status_counts": {"unsupported": 1},
            "resolution_status_counts": {"still_open": 1},
            "temporal_gap_task_count": 1,
            "temporal_gap_targeted_task_count": 1,
            "temporal_rule_status_counts": {"partial": 1},
            "temporal_rule_blocking_reason_counts": {"Need retaliation chronology sequencing.": 1},
            "temporal_resolution_status_counts": {"still_open": 1},
        },
        "claim_support_packet_summary": {
            "claim_count": 2,
            "element_count": 6,
            "status_counts": {
                "supported": 2,
                "partially_supported": 1,
                "unsupported": 1,
                "contradicted": 0,
            },
            "recommended_actions": ["collect_missing_support_kind"],
            "supported_blocking_element_ratio": 0.5,
            "proof_readiness_score": 0.47,
            "claim_support_unresolved_without_review_path_count": 1,
            "claim_support_unresolved_temporal_issue_count": 1,
            "claim_support_unresolved_temporal_issue_ids": ["temporal_issue_001"],
            "evidence_completion_ready": False,
        },
        "intake_readiness": {
            "ready_to_advance": False,
            "score": 0.38,
            "remaining_gap_count": 2,
            "contradiction_count": 1,
            "blockers": ["resolve_contradictions", "collect_missing_timeline_details"],
        },
        "intake_contradictions": [
            {
                "summary": "Complaint date conflicts with schedule-cut date",
                "question": "What were the exact dates for the complaint and schedule change?",
                "severity": "high",
            }
        ],
    }
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


def test_collect_exhibits_uses_evidence_facts_when_preview_missing():
    mediator = Mock()
    mediator.get_user_evidence.return_value = [
        {
            "id": 7,
            "cid": "bafy-evidence",
            "description": "Hearing request email",
            "claim_type": "retaliation",
            "metadata": {
                "document_graph_summary": {
                    "entity_count": 2,
                    "relationship_count": 1,
                }
            },
        }
    ]
    mediator.get_evidence_facts.return_value = [
        {"text": "Email requested a grievance hearing on March 3, 2026."},
        {"text": "Response denied the request on March 10, 2026."},
    ]
    builder = FormalComplaintDocumentBuilder(mediator)

    exhibits = builder._collect_exhibits(
        user_id="user-1",
        claim_types=["retaliation"],
        support_claims={},
    )

    assert len(exhibits) == 1
    assert "Email requested a grievance hearing on March 3, 2026." in exhibits[0]["summary"]
    assert "Graph extraction: 2 entities, 1 relationships." in exhibits[0]["summary"]
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
    assert result["claim_support_temporal_handoff"] == {
        "unresolved_temporal_issue_count": 1,
        "unresolved_temporal_issue_ids": ["temporal_issue_001"],
        "chronology_task_count": 1,
        "event_ids": ["event_001"],
        "temporal_fact_ids": ["fact_001"],
        "temporal_relation_ids": ["timeline_relation_001"],
        "timeline_issue_ids": ["temporal_issue_001"],
        "temporal_issue_ids": ["temporal_issue_001"],
        "temporal_proof_bundle_ids": ["retaliation:causation:bundle_001"],
        "temporal_proof_objectives": ["establish_retaliation_sequence"],
    }
    assert result["claim_reasoning_review"]["retaliation"]["proof_artifact_element_count"] == 1
    assert result["claim_reasoning_review"]["retaliation"]["proof_artifact_preview"] == ["proof-retaliation-001"]
    assert result["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["proof_artifact_theorem_export_metadata"] == {
        "contract_version": "claim_support_temporal_handoff_v1",
        "claim_type": "retaliation",
        "claim_element_id": "causation",
        "proof_bundle_id": "retaliation:causation:bundle_001",
        "chronology_blocked": True,
        "chronology_task_count": 1,
        "unresolved_temporal_issue_ids": ["temporal_issue_001"],
        "event_ids": ["event_001"],
        "temporal_fact_ids": ["fact_001"],
        "temporal_relation_ids": ["timeline_relation_001"],
        "timeline_issue_ids": ["temporal_issue_001"],
        "temporal_issue_ids": ["temporal_issue_001"],
        "temporal_proof_bundle_ids": ["retaliation:causation:bundle_001"],
        "temporal_proof_objectives": ["establish_retaliation_sequence"],
    }
    assert result["draft"]["source_context"]["claim_support_temporal_handoff"] == result["claim_support_temporal_handoff"]
    assert result["draft"]["source_context"]["claim_reasoning_review"] == result["claim_reasoning_review"]


def test_collect_exhibits_uses_evidence_facts_when_preview_missing():
    mediator = Mock()
    mediator.get_user_evidence.return_value = [
        {
            "id": 7,
            "cid": "bafy-evidence",
            "description": "Hearing request email",
            "claim_type": "retaliation",
            "metadata": {
                "document_graph_summary": {
                    "entity_count": 2,
                    "relationship_count": 1,
                }
            },
        }
    ]
    mediator.get_evidence_facts.return_value = [
        {"text": "Email requested a grievance hearing on March 3, 2026."},
        {"text": "Response denied the request on March 10, 2026."},
    ]
    builder = FormalComplaintDocumentBuilder(mediator)

    exhibits = builder._collect_exhibits(
        user_id="user-1",
        claim_types=["retaliation"],
        support_claims={},
    )

    assert len(exhibits) == 1
    assert "Email requested a grievance hearing on March 3, 2026." in exhibits[0]["summary"]
    assert "Graph extraction: 2 entities, 1 relationships." in exhibits[0]["summary"]


def test_claim_support_temporal_handoff_falls_back_to_raw_intake_chronology_registries():
    intake_case_summary = {
        "claim_support_packet_summary": {},
        "alignment_evidence_tasks": [],
        "event_ledger": [
            {
                "event_id": "event-ledger-001",
                "temporal_fact_id": "fact-ledger-001",
            }
        ],
        "temporal_fact_registry": [
            {
                "temporal_fact_id": "fact-ledger-001",
            }
        ],
        "temporal_relation_registry": [
            {
                "relation_id": "relation-ledger-001",
            }
        ],
        "temporal_issue_registry": [
            {
                "temporal_issue_id": "issue-open-001",
                "status": "open",
            },
            {
                "temporal_issue_id": "issue-resolved-001",
                "status": "resolved",
            },
        ],
    }
    expected = {
        "unresolved_temporal_issue_count": 1,
        "unresolved_temporal_issue_ids": ["issue-open-001"],
        "chronology_task_count": 0,
        "event_ids": ["event-ledger-001"],
        "temporal_fact_ids": ["fact-ledger-001"],
        "temporal_relation_ids": ["relation-ledger-001"],
        "timeline_issue_ids": ["issue-open-001", "issue-resolved-001"],
        "temporal_issue_ids": ["issue-open-001", "issue-resolved-001"],
        "temporal_proof_bundle_ids": [],
        "temporal_proof_objectives": [],
    }

    assert document_optimization._build_claim_support_temporal_handoff(intake_case_summary) == expected

    builder = FormalComplaintDocumentBuilder(_build_mediator())
    assert builder._build_claim_support_temporal_handoff({"intake_case_summary": intake_case_summary}) == expected


def test_claim_reasoning_theorem_export_metadata_falls_back_to_raw_intake_chronology_registries():
    intake_case_summary = {
        "claim_support_packet_summary": {},
        "alignment_evidence_tasks": [
            {
                "claim_type": "retaliation",
                "claim_element_id": "causation",
            }
        ],
        "event_ledger": [
            {
                "event_id": "event-ledger-001",
                "temporal_fact_id": "fact-ledger-001",
            }
        ],
        "temporal_fact_registry": [
            {
                "temporal_fact_id": "fact-ledger-001",
            }
        ],
        "timeline_relations": [
            {
                "temporal_relation_id": "relation-ledger-001",
            }
        ],
        "temporal_issue_registry": [
            {
                "temporal_issue_id": "issue-open-001",
                "status": "open",
            }
        ],
    }

    assert document_optimization._build_claim_reasoning_theorem_export_metadata(
        intake_case_summary,
        claim_type="retaliation",
        claim_element_id="causation",
    ) == {
        "contract_version": "claim_support_temporal_handoff_v1",
        "claim_type": "retaliation",
        "claim_element_id": "causation",
        "proof_bundle_id": "",
        "chronology_blocked": True,
        "chronology_task_count": 0,
        "unresolved_temporal_issue_ids": ["issue-open-001"],
        "event_ids": ["event-ledger-001"],
        "temporal_fact_ids": ["fact-ledger-001"],
        "temporal_relation_ids": ["relation-ledger-001"],
        "timeline_issue_ids": ["issue-open-001"],
        "temporal_issue_ids": ["issue-open-001"],
        "temporal_proof_bundle_ids": [],
        "temporal_proof_objectives": [],
    }


def test_formal_complaint_document_builder_exposes_runtime_workflow_phase_plan_from_phase_state():
    mediator = _build_mediator()
    phase_values = {
        "knowledge_graph": {"entity_count": 4},
        "dependency_graph": {"claim_count": 2},
        "current_gaps": [{"gap_id": "gap_001", "summary": "Missing adverse-action date anchor"}],
        "remaining_gaps": 1,
        "knowledge_graph_enhanced": False,
    }
    mediator.phase_manager = SimpleNamespace(
        get_phase_data=lambda _phase, key: phase_values.get(key)
    )
    builder = FormalComplaintDocumentBuilder(mediator)

    result = builder.build_package(
        district="Northern District of California",
        county="San Francisco County",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        output_formats=["txt"],
    )

    workflow_phase_plan = result["workflow_phase_plan"]
    assert workflow_phase_plan["recommended_order"] == [
        "graph_analysis",
        "document_generation",
        "intake_questioning",
    ]
    assert workflow_phase_plan["phases"]["graph_analysis"]["status"] == "warning"
    assert workflow_phase_plan["phases"]["graph_analysis"]["signals"]["remaining_gap_count"] == 1
    assert workflow_phase_plan["phases"]["graph_analysis"]["signals"]["knowledge_graph_enhanced"] is False
    assert workflow_phase_plan["phases"]["document_generation"]["status"] == "blocked"
    assert workflow_phase_plan["phases"]["intake_questioning"]["status"] == "warning"
    missing_required_objectives = workflow_phase_plan["phases"]["intake_questioning"]["signals"]["missing_required_objectives"]
    assert "timeline" in missing_required_objectives
    assert "actors" in missing_required_objectives
    assert "causation_link" in missing_required_objectives
    assert workflow_phase_plan["phases"]["intake_questioning"]["signals"]["missing_required_objectives"] == [
        "timeline",
        "actors",
        "staff_names_titles",
        "causation_link",
        "anchor_adverse_action",
        "anchor_appeal_rights",
        "hearing_request_timing",
        "response_dates",
    ]
    assert result["draft"]["workflow_phase_plan"] == workflow_phase_plan
    assert result["draft"]["drafting_readiness"]["workflow_phase_plan"] == workflow_phase_plan
    assert result["workflow_optimization_guidance"]["workflow_phase_plan"] == workflow_phase_plan
    assert result["workflow_optimization_guidance"]["phase_scorecards"]["graph_analysis"]["status"] == "warning"
    assert any(
        warning.get("code") == "workflow_graph_analysis_warning"
        for warning in result["drafting_readiness"]["warnings"]
    )
    assert any(
        warning.get("code") == "workflow_document_generation_blocked"
        for warning in result["drafting_readiness"]["warnings"]
    )


def test_formal_complaint_document_builder_can_optimize_draft_with_agentic_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mediator = _build_mediator()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "candidate_claims": [
            {"claim_type": "employment discrimination", "label": "Employment Discrimination", "confidence": 0.82},
            {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.8},
        ],
        "intake_sections": {
            "chronology": {"status": "complete", "missing_items": []},
            "proof_leads": {"status": "partial", "missing_items": ["documents"]},
        },
        "canonical_fact_summary": {
            "count": 2,
            "facts": [{"fact_id": "fact_001"}, {"fact_id": "fact_002"}],
        },
        "proof_lead_summary": {
            "count": 1,
            "proof_leads": [{"lead_id": "lead_001"}],
        },
        "question_candidate_summary": {
            "count": 1,
            "candidates": [{"candidate_source": "intake_proof_gap"}],
            "source_counts": {"intake_proof_gap": 1},
            "question_goal_counts": {"identify_supporting_proof": 1},
            "phase1_section_counts": {"proof_leads": 1},
            "blocking_level_counts": {"important": 1},
        },
        "alignment_evidence_tasks": [
            {
                "task_id": "retaliation:causation:fill_evidence_gaps",
                "action": "fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "causation",
                "claim_element_label": "Causal connection",
                "support_status": "unsupported",
                "blocking": True,
                "preferred_support_kind": "evidence",
                "fallback_lanes": ["authority", "testimony"],
                "source_quality_target": "high_quality_document",
                "resolution_status": "still_open",
                "resolution_notes": "",
            }
        ],
        "alignment_task_summary": {
            "count": 1,
            "status_counts": {"unsupported": 1},
            "resolution_status_counts": {"still_open": 1},
            "temporal_gap_task_count": 1,
            "temporal_gap_targeted_task_count": 1,
            "temporal_rule_status_counts": {"partial": 1},
            "temporal_rule_blocking_reason_counts": {"Need retaliation chronology sequencing.": 1},
            "temporal_resolution_status_counts": {"still_open": 1},
        },
        "claim_support_packet_summary": {
            "claim_count": 2,
            "element_count": 6,
            "status_counts": {
                "supported": 2,
                "partially_supported": 1,
                "unsupported": 1,
                "contradicted": 0,
            },
            "recommended_actions": ["collect_missing_support_kind"],
            "supported_blocking_element_ratio": 0.5,
            "credible_support_ratio": 0.5,
            "draft_ready_element_ratio": 0.333,
            "high_quality_parse_ratio": 0.333,
            "reviewable_escalation_ratio": 0.167,
            "claim_support_reviewable_escalation_count": 1,
            "claim_support_unresolved_without_review_path_count": 1,
            "proof_readiness_score": 0.47,
            "evidence_completion_ready": False,
        },
        "intake_readiness": {
            "score": 0.44,
            "ready_to_advance": False,
            "remaining_gap_count": 2,
            "contradiction_count": 1,
            "blockers": ["resolve_contradictions", "collect_missing_timeline_details"],
        },
        "intake_contradictions": [
            {
                "summary": "Complaint date conflicts with schedule-cut date",
                "question": "What were the exact dates for the complaint and schedule change?",
                "severity": "high",
            }
        ],
    }
    builder = FormalComplaintDocumentBuilder(mediator)
    calls = {"critic": 0, "actor": 0}
    llm_invocations = []
    embed_calls = []
    stored_traces = []

    class _FakeEmbeddingsRouter:
        def embed_text(self, text: str):
            embed_calls.append(text)
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
        stored_traces.append(json.loads(data.decode("utf-8")))
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
    assert report["section_history"][0]["change_manifest"]
    assert report["section_history"][0]["change_manifest"][0]["field"] == "factual_allegations"
    assert report["section_history"][0]["change_manifest"][0]["before_count"] == 8
    assert report["section_history"][0]["change_manifest"][0]["after_count"] == 3
    assert report["section_history"][0]["selected_support_context"]["focus_section"] == "factual_allegations"
    assert report["section_history"][0]["selected_support_context"]["top_support"]
    assert report["section_history"][0]["selected_support_context"]["top_support"][0]["ranking_method"] == "embeddings_router_hybrid"
    assert report["initial_review"]["llm_metadata"]["effective_model_name"] == "meta-llama/Llama-3.3-70B-Instruct"
    assert report["final_review"]["llm_metadata"]["arch_router_selected_route"] == "legal_reasoning"
    assert "selected_provider" in report["upstream_optimizer"]
    assert report["router_usage"]["llm_calls"] >= 3
    assert report["router_usage"]["critic_calls"] >= 2
    assert report["router_usage"]["actor_calls"] >= 1
    assert report["router_usage"]["embedding_requests"] >= 1
    assert report["router_usage"]["embedding_rankings"] >= 1
    assert report["router_usage"]["ipfs_store_attempted"] is True
    assert report["router_usage"]["ipfs_store_succeeded"] is True
    assert report["router_usage"]["llm_providers_used"] == ["test-provider"]
    _assert_normalized_intake_status(report["intake_status"], score=0.44)
    assert report["intake_constraints"] == [
        {
            "severity": "warning",
            "code": "intake_blocker",
            "message": "Intake blocker: resolve_contradictions",
        },
        {
            "severity": "warning",
            "code": "intake_blocker",
            "message": "Intake blocker: collect_missing_timeline_details",
        },
        {
            "severity": "warning",
            "code": "intake_contradiction",
            "message": "Complaint date conflicts with schedule-cut date. Clarify: What were the exact dates for the complaint and schedule change?",
        },
    ]
    assert calls["actor"] >= 1
    assert calls["critic"] >= 2
    assert embed_calls
    assert llm_invocations
    assert all(entry["provider"] == "test-provider" for entry in llm_invocations)
    assert all(entry["model_name"] == "test-model" for entry in llm_invocations)
    assert all(entry["kwargs"].get("base_url") == "https://router.huggingface.co/v1" for entry in llm_invocations)
    assert all(entry["kwargs"].get("headers", {}).get("X-Title") == "Complaint Generator Tests" for entry in llm_invocations)
    assert stored_traces
    assert stored_traces[0]["user_id"] == "test-user"
    assert stored_traces[0]["config"]["router_usage"]["llm_calls"] >= 3
    assert stored_traces[0]["intake_status"] == report["intake_status"]
    assert stored_traces[0]["intake_constraints"] == report["intake_constraints"]
    assert stored_traces[0]["intake_case_summary"]["canonical_fact_summary"]["count"] == 2
    assert stored_traces[0]["intake_case_summary"]["proof_lead_summary"]["count"] == 1
    assert stored_traces[0]["intake_case_summary"]["question_candidate_summary"]["count"] == 1
    assert stored_traces[0]["intake_case_summary"]["question_candidate_summary"]["phase1_section_counts"]["proof_leads"] == 1
    assert stored_traces[0]["intake_case_summary"]["alignment_task_summary"]["temporal_gap_task_count"] == 1
    assert stored_traces[0]["intake_case_summary"]["alignment_task_summary"]["temporal_rule_blocking_reason_counts"] == {
        "Need retaliation chronology sequencing.": 1,
    }
    assert stored_traces[0]["intake_case_summary"]["claim_support_packet_summary"]["claim_count"] == 2
    assert stored_traces[0]["iterations"][0]["change_manifest"]
    assert stored_traces[0]["iterations"][0]["change_manifest"][0]["field"] == "factual_allegations"
    assert stored_traces[0]["iterations"][0]["change_manifest"][0]["before_count"] == 8
    assert stored_traces[0]["iterations"][0]["change_manifest"][0]["after_count"] == 3
    before_preview = " ".join(stored_traces[0]["iterations"][0]["change_manifest"][0]["before_preview"])
    after_preview = " ".join(stored_traces[0]["iterations"][0]["change_manifest"][0]["after_preview"])
    assert "chronology and actor sequence" in before_preview.lower()
    assert "human resources" in before_preview.lower()
    assert "terminated plaintiff" in before_preview.lower()
    assert "lost pay and benefits" in after_preview.lower()
    assert stored_traces[0]["iterations"][0]["change_manifest"][1]["field"] == "claim_supporting_facts"
    assert any(
        "Plaintiff was fired two days later and lost pay and benefits" in allegation
        for allegation in result["draft"]["factual_allegations"]
    )
    assert "Plaintiff was fired two days later and lost pay and benefits." in result["draft"]["draft_text"]
    assert result["draft"]["affidavit"]["title"] == "AFFIDAVIT OF JANE DOE IN SUPPORT OF COMPLAINT"
    assert result["draft"]["verification"]["text"].startswith("I, Jane Doe, declare under penalty of perjury")
    assert result["drafting_readiness"]["status"] == "blocked"
    assert result["draft"]["drafting_readiness"]["status"] == "blocked"
    assert result["filing_checklist"] == result["draft"]["filing_checklist"]
    assert any(item["status"] == "warning" for item in result["filing_checklist"])
    assert any(item["scope"] == "claim" for item in result["filing_checklist"])
    assert result["drafting_readiness"]["sections"]["claims_for_relief"]["status"] == "warning"
    assert result["drafting_readiness"]["sections"]["summary_of_facts"]["status"] == "warning"
    assert any(
        warning["code"] == "document_provenance_grounding_thin"
        for warning in result["drafting_readiness"]["sections"]["summary_of_facts"]["warnings"]
    )
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


def test_agentic_optimizer_tracks_claim_and_relief_manifest_deltas():
    optimizer = document_optimization.AgenticDocumentOptimizer(mediator=Mock())
    draft = {
        "factual_allegations": ["Plaintiff complained about discrimination."],
        "claims_for_relief": [
            {
                "claim_type": "retaliation",
                "count_title": "Count I - Retaliation",
                "legal_standards": ["Protected activity", "Adverse action"],
                "supporting_facts": ["Plaintiff reported discrimination to human resources."],
                "missing_elements": ["Causation details"],
                "partially_supported_elements": [],
                "support_summary": {"covered_elements": 1},
                "supporting_exhibits": [{"label": "Exhibit A", "title": "HR complaint"}],
            }
        ],
        "requested_relief": ["Back pay."],
    }
    actor_payload = {
        "claims_for_relief": [
            {
                "claim_type": "retaliation",
                "supporting_facts": [
                    "Plaintiff reported discrimination to human resources.",
                    "Defendant fired Plaintiff two days later.",
                ],
                "missing_elements": [],
            },
            {
                "claim_type": "wrongful termination",
                "count_title": "Count II - Wrongful Termination",
                "legal_standards": ["Termination", "Public policy violation"],
                "supporting_facts": ["Defendant fired Plaintiff after the protected complaint."],
            },
        ],
        "requested_relief": ["Back pay.", "Front pay.", "Compensatory damages."],
    }

    updated = optimizer._apply_actor_payload(
        draft=draft,
        actor_payload=actor_payload,
        focus_section="claims_for_relief",
    )
    manifest = optimizer._build_iteration_change_manifest(
        before_draft=draft,
        after_draft=updated,
        actor_payload=actor_payload,
        focus_section="claims_for_relief",
    )

    assert len(updated["claims_for_relief"]) == 2
    retaliation_claim = next(claim for claim in updated["claims_for_relief"] if claim["claim_type"] == "retaliation")
    assert retaliation_claim["legal_standards"] == ["Protected activity.", "Adverse action."]
    assert retaliation_claim["supporting_facts"] == [
        "Plaintiff reported discrimination to human resources.",
        "Defendant fired Plaintiff two days later.",
    ]
    assert updated["requested_relief"] == ["Back pay.", "Front pay.", "Compensatory damages."]

    claims_manifest = next(entry for entry in manifest if entry["field"] == "claims_for_relief")
    assert claims_manifest["changed_items"] == ["retaliation supporting facts 1 -> 2"]
    assert claims_manifest["added_items"] == ["wrongful termination (1 facts)"]
    assert claims_manifest["removed_items"] == []

    relief_manifest = next(entry for entry in manifest if entry["field"] == "requested_relief")
    assert relief_manifest["added_items"] == ["Compensatory damages.", "Front pay."]
    assert relief_manifest["removed_items"] == []


def test_agentic_optimizer_can_prioritize_requested_relief_focus():
    builder = Mock()
    builder._extract_requested_relief_from_facts.return_value = [
        "Back pay, front pay, and lost benefits.",
        "Injunctive relief to prevent continuing violations.",
    ]
    optimizer = document_optimization.AgenticDocumentOptimizer(mediator=Mock(), builder=builder)
    draft = {
        "factual_allegations": [
            "Plaintiff complained about discrimination.",
            "Defendant terminated Plaintiff two days later.",
            "Plaintiff lost wages and benefits.",
            "Plaintiff seeks reinstatement.",
        ],
        "claims_for_relief": [
            {
                "claim_type": "retaliation",
                "supporting_facts": [
                    "Plaintiff complained about discrimination.",
                    "Defendant terminated Plaintiff two days later.",
                ],
            }
        ],
        "requested_relief": [],
    }
    drafting_readiness = {
        "status": "warning",
        "sections": {
            "requested_relief": {
                "status": "warning",
                "warnings": [{"code": "requested_relief_missing", "message": "Requested relief should be confirmed before filing."}],
            }
        },
    }
    support_context = {
        "claims": [
            {
                "claim_type": "retaliation",
                "support_facts": [
                    "Plaintiff lost wages and benefits.",
                    "Plaintiff seeks reinstatement.",
                    "Continuing violations require injunctive relief.",
                ],
                "missing_elements": [],
            }
        ],
        "evidence": [],
        "packet_projection": {
            "section_presence": {
                "nature_of_action": True,
                "summary_of_facts": True,
                "factual_allegations": True,
                "claims_for_relief": True,
                "requested_relief": False,
            },
            "section_counts": {
                "nature_of_action": 1,
                "summary_of_facts": 1,
                "factual_allegations": 4,
                "claims_for_relief": 1,
                "requested_relief": 0,
            },
            "has_affidavit": True,
            "has_certificate_of_service": True,
        },
    }

    review = optimizer._heuristic_review(
        draft=draft,
        drafting_readiness=drafting_readiness,
        support_context=support_context,
    )
    actor_payload = optimizer._build_fallback_actor_payload(
        draft=draft,
        focus_section="requested_relief",
        support_context={
            "top_support": [
                {"text": "Plaintiff lost wages and benefits."},
                {"text": "Plaintiff seeks reinstatement."},
                {"text": "Continuing violations require injunctive relief."},
            ]
        },
    )

    assert review["recommended_focus"] == "requested_relief"
    assert actor_payload["requested_relief"] == [
        "Back pay, front pay, and lost benefits.",
        "Injunctive relief to prevent continuing violations.",
    ]


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
    assert packet["claim_support_temporal_handoff"] == result["claim_support_temporal_handoff"]
    assert packet["claim_reasoning_review"] == result["claim_reasoning_review"]
    assert packet["source_context"]["claim_support_temporal_handoff"] == result["claim_support_temporal_handoff"]
    assert packet["source_context"]["claim_reasoning_review"] == result["claim_reasoning_review"]
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
        assert "intake_summary_handoff" not in response.json()
        assert response.json()["review_links"]["dashboard_url"] == "/claim-support-review"
        assert response.json()["review_links"]["intake_status"] == {}
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
        assert response.json()["filing_checklist"][0].get("intake_status") is None
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


def test_review_api_openapi_exposes_arch_router_request_example():
    mediator = Mock()
    app = create_review_api_app(mediator)
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    request_schema = schema["components"]["schemas"]["FormalComplaintDocumentRequest"]
    example = request_schema["example"]
    assert example["optimization_provider"] == "huggingface_router"
    assert example["optimization_llm_config"]["arch_router"]["model"] == "katanemo/Arch-Router-1.5B"
    assert example["optimization_llm_config"]["arch_router"]["routes"]["legal_reasoning"] == "meta-llama/Llama-3.3-70B-Instruct"
    assert example["output_formats"] == ["txt", "packet"]


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
    assert report["section_history"][0]["selected_support_context"]["top_support"][0]["ranking_method"] == "embeddings_router_hybrid"
    assert report["initial_review"]["llm_metadata"]["effective_provider_name"] == "openrouter"
    assert report["final_review"]["llm_metadata"]["arch_router_model_name"] == "katanemo/Arch-Router-1.5B"
    assert report["router_usage"]["llm_calls"] >= 3
    assert report["router_usage"]["embedding_rankings"] >= 1
    assert report["router_usage"]["ipfs_store_succeeded"] is True
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
        pytest.skip("Set a Hugging Face token in the environment or log in with huggingface_hub to run the live Hugging Face router API smoke test")

    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )

    app = create_review_api_app(mediator)
    client = TestClient(app)
    model_name, response, payload, used_arch_router = _post_live_hf_optimization_request(
        client,
        output_dir=str(tmp_path),
        page_title="Complaint Generator API Smoke Test",
        include_arch_router=True,
    )

    assert response.status_code == 200, response.text
    assert payload["document_optimization"]["router_status"]["llm_router"] == "available"
    assert payload["document_optimization"]["iteration_count"] == 1
    assert payload["document_optimization"]["initial_score"] >= 0.0
    assert payload["document_optimization"]["final_score"] >= 0.0
    assert payload["document_optimization"]["trace_storage"]["status"] == "disabled"
    assert payload["document_optimization"]["draft"]["draft_text"]
    final_review_metadata = payload["document_optimization"]["final_review"].get("llm_metadata") or {}
    assert final_review_metadata.get("effective_provider_name") == "openrouter"
    assert final_review_metadata.get("effective_model_name") == model_name
    if used_arch_router:
        assert final_review_metadata.get("arch_router_model_name") == os.getenv("HF_ARCH_ROUTER_MODEL", "katanemo/Arch-Router-1.5B")
        assert final_review_metadata.get("arch_router_status") in {"selected", "fallback"}
        assert final_review_metadata.get("arch_router_selected_route") in {
            "legal_reasoning",
            "drafting",
            "route_legal_reasoning",
            "route_drafting",
            "unknown_path",
            None,
        }
        selected_model = final_review_metadata.get("arch_router_selected_model")
        assert selected_model in {model_name, os.getenv("HF_ROUTER_ARCH_REASONING_MODEL", "").strip() or model_name, ""}
    assert payload["artifacts"]["txt"]["path"]

    Path(payload["artifacts"]["txt"]["path"]).unlink(missing_ok=True)


def test_agentic_optimizer_uses_upstream_router_provider_selection_when_provider_is_unset(monkeypatch: pytest.MonkeyPatch):
    mediator = _build_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)
    llm_providers = []
    llm_invocations = []

    class _FakeOptimizerLLMRouter:
        def __init__(self, *args, **kwargs):
            self.calls = []

        def select_provider(self, method, complexity="medium"):
            self.calls.append((getattr(method, "value", str(method)), complexity))
            return SimpleNamespace(value="claude")

    class _FakeControlLoopConfig:
        def __init__(self, max_iterations=10, target_score=0.9, **kwargs):
            self.max_iterations = max_iterations
            self.target_score = target_score

    class _FakeOptimizationMethod:
        ACTOR_CRITIC = SimpleNamespace(value="actor_critic")

    calls = {"critic": 0, "actor": 0}

    def _fake_generate_text(prompt: str, *, provider=None, model_name=None, **kwargs):
        llm_providers.append(provider)
        llm_invocations.append(dict(kwargs))
        if document_optimization.AgenticDocumentOptimizer.CRITIC_PROMPT_TAG in prompt:
            calls["critic"] += 1
            payload = {
                "overall_score": 0.4 if calls["critic"] == 1 else 0.92,
                "recommended_focus": "factual_allegations",
            }
        else:
            calls["actor"] += 1
            payload = {
                "factual_allegations": [
                    "Plaintiff reported discrimination to human resources.",
                    "Defendant terminated Plaintiff two days later.",
                ]
            }
        return {
            "status": "available",
            "text": json.dumps(payload),
            "provider_name": provider,
            "model_name": model_name,
        }

    monkeypatch.setattr(document_optimization, "LLM_ROUTER_AVAILABLE", True)
    monkeypatch.setattr(document_optimization, "UPSTREAM_AGENTIC_AVAILABLE", True)
    monkeypatch.setattr(document_optimization, "OptimizerLLMRouter", _FakeOptimizerLLMRouter)
    monkeypatch.setattr(document_optimization, "ControlLoopConfig", _FakeControlLoopConfig)
    monkeypatch.setattr(document_optimization, "OptimizationMethod", _FakeOptimizationMethod)
    monkeypatch.setattr(document_optimization, "generate_text_with_metadata", _fake_generate_text)

    result = builder.build_package(
        district="Northern District of California",
        county="San Francisco County",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        enable_agentic_optimization=True,
        optimization_max_iterations=1,
        optimization_target_score=0.9,
        optimization_provider=None,
        optimization_model_name="test-model",
        output_formats=["txt"],
    )

    report = result["document_optimization"]
    assert calls["critic"] >= 2
    assert calls["actor"] >= 1
    assert llm_providers
    assert all(provider == "anthropic" for provider in llm_providers)
    assert llm_invocations
    assert all(
        invocation.get("timeout") == document_optimization.DEFAULT_OPTIMIZER_LLM_TIMEOUT_SECONDS
        for invocation in llm_invocations
    )
    assert report["router_usage"]["llm_providers_used"] == ["anthropic"]
    assert report["upstream_optimizer"]["stage_provider_selection"]["critic"]["resolved_provider"] == "anthropic"
    assert report["upstream_optimizer"]["stage_provider_selection"]["actor"]["resolved_provider"] == "anthropic"
    assert report["workflow_optimization_guidance"]["phase_scorecards"]["intake_questioning"]["status"] in {"warning", "ready"}
    assert report["workflow_optimization_guidance"]["document_handoff_summary"]["drafting_status"] in {"warning", "ready"}
    assert report["workflow_targeting_summary"] == report["workflow_optimization_guidance"]["workflow_targeting_summary"]
    assert result["workflow_optimization_guidance"]["phase_scorecards"]["document_generation"]["status"] in {"warning", "ready"}
    assert result["workflow_targeting_summary"] == result["workflow_optimization_guidance"]["workflow_targeting_summary"]
    assert result["draft"]["workflow_optimization_guidance"] == result["workflow_optimization_guidance"]
    assert result["draft"]["workflow_targeting_summary"] == result["workflow_targeting_summary"]


def test_actor_critic_guidance_enforces_requested_phase_order_at_priority_70():
    mediator = _build_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)

    guidance = builder._extract_actor_critic_guidance(
        {
            "optimization_method": "actor_critic",
            "priority": 70,
            "phase_focus_order": ["intake_questioning", "document_generation", "graph_analysis"],
            "final_review": {"section_scores": {"intake_questioning": 0.95}},
        }
    )

    assert guidance["phase_focus_order"][:3] == [
        "graph_analysis",
        "document_generation",
        "intake_questioning",
    ]
    assert guidance["priority"] == 70


def test_intake_guidance_promotes_chronology_and_decision_document_precision_from_latest_batch_priorities():
    mediator = _build_mediator()
    builder = FormalComplaintDocumentBuilder(mediator)

    guidance = builder._build_intake_questioning_phase_guidance(
        drafting_readiness={"status": "warning"},
        document_optimization={
            "optimization_method": "actor_critic",
            "priority": 70,
            "router_backed_question_quality": True,
            "latest_batch_priorities": [
                "Did not follow up to close critical chronology gaps (exact dates, response timing, sequence).",
                "Did not pin down specific decision-makers, adverse action details, or documentary artifacts with precision.",
            ],
            "final_review": {
                "section_scores": {"intake_questioning": 0.72},
                "dimension_scores": {
                    "coherence": 0.63,
                    "grounding": 0.61,
                    "completeness": 0.6,
                    "procedural": 0.7,
                },
            },
        },
    )

    assert guidance["signals"]["needs_chronology_closure"] is True
    assert guidance["signals"]["needs_decision_document_precision"] is True
    assert any("Close chronology gaps" in action for action in guidance["recommended_actions"])
    assert any("decision-precision follow-ups" in action for action in guidance["recommended_actions"])


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
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "intake_readiness": {
            "score": 0.44,
            "ready_to_advance": False,
            "remaining_gap_count": 2,
            "contradiction_count": 1,
            "blockers": ["resolve_contradictions", "collect_missing_timeline_details"],
        },
        "intake_contradictions": [
            {
                "summary": "Complaint date conflicts with schedule-cut date",
                "question": "What were the exact dates for the complaint and schedule change?",
                "severity": "high",
            }
        ],
    }
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
        assert any(
            warning.get("code") == "intake_blocker"
            and warning.get("message") == "Intake blocker: resolve_contradictions"
            for warning in payload["drafting_readiness"]["warnings"]
        )
        assert any(
            warning.get("code") == "intake_contradiction"
            and "Complaint date conflicts with schedule-cut date" in str(warning.get("message") or "")
            for warning in payload["drafting_readiness"]["warnings"]
        )
        assert any(
            warning.get("code") == "intake_blocker"
            for warning in payload["drafting_readiness"]["sections"]["claims_for_relief"]["warnings"]
        )
        assert any(
            warning.get("code") == "intake_blocker"
            for warning in payload["drafting_readiness"]["claims"][0]["warnings"]
        )
        assert any(
            warning.get("code") == "intake_blocker"
            for warning in payload["drafting_readiness"]["claims"][1]["warnings"]
        )
        assert payload["filing_checklist"][0]["review_url"] == "/claim-support-review?section=claims_for_relief"
        _assert_normalized_intake_status(
            payload["filing_checklist"][0]["intake_status"],
            score=0.44,
            current_phase=None,
            include_extended_fields=False,
        )
        assert payload["filing_checklist"][0]["review_intent"] == {
            "user_id": None,
            "claim_type": None,
            "section": "claims_for_relief",
            "follow_up_support_kind": "authority",
            "review_url": "/claim-support-review?section=claims_for_relief",
        }
        assert payload["filing_checklist"][1]["review_url"] == "/claim-support-review?claim_type=retaliation"
        _assert_normalized_intake_status(
            payload["filing_checklist"][1]["intake_status"],
            score=0.44,
            current_phase=None,
            include_extended_fields=False,
        )
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


def test_review_api_retrieves_persisted_optimization_trace(monkeypatch: pytest.MonkeyPatch):
    mediator = Mock()
    app = create_review_api_app(mediator)
    client = TestClient(app)

    def _fake_retrieve_bytes(cid: str):
        assert cid == 'bafy-doc-opt-report'
        return {
            'status': 'available',
            'cid': cid,
            'size': 128,
            'data': json.dumps(
                {
                    'user_id': 'state-user',
                    'workflow_phase_plan': {
                        'recommended_order': ['intake_questioning', 'graph_analysis', 'document_generation'],
                        'phases': {
                            'intake_questioning': {
                                'status': 'ready',
                                'summary': 'Intake objectives are adequately covered.',
                            },
                            'graph_analysis': {
                                'status': 'warning',
                                'summary': 'Knowledge graph gaps still need reduction before drafting.',
                                'signals': {
                                    'remaining_gap_count': 2,
                                    'knowledge_graph_enhanced': False,
                                },
                                'recommended_actions': [
                                    {'recommended_action': 'Fill unresolved graph gaps from intake evidence.'},
                                ],
                            },
                            'document_generation': {
                                'status': 'warning',
                                'summary': 'Drafting should wait for graph cleanup and contradiction resolution.',
                                'recommended_actions': [
                                    {'recommended_action': 'Re-run document optimization after graph improvements.'},
                                ],
                            },
                        },
                    },
                    'intake_status': {
                        'current_phase': 'intake',
                        'score': 0.38,
                        'remaining_gap_count': 2,
                        'contradiction_count': 1,
                        'ready_to_advance': False,
                        'blockers': ['resolve_contradictions'],
                        'contradictions': [
                            {
                                'summary': 'Complaint date conflicts with schedule-cut date',
                                'question': 'What were the exact dates for the complaint and schedule change?',
                            }
                        ],
                    },
                    'intake_constraints': [
                        {
                            'severity': 'warning',
                            'code': 'intake_blocker',
                            'message': 'Intake blocker: resolve_contradictions',
                        }
                    ],
                    'claim_support_temporal_handoff': {
                        'unresolved_temporal_issue_count': 1,
                        'unresolved_temporal_issue_ids': ['temporal_issue_001'],
                        'chronology_task_count': 1,
                        'event_ids': ['event_001'],
                        'temporal_fact_ids': ['fact_001'],
                        'temporal_relation_ids': ['timeline_relation_001'],
                        'timeline_issue_ids': ['temporal_issue_001'],
                        'temporal_issue_ids': ['temporal_issue_001'],
                        'temporal_proof_bundle_ids': ['retaliation:causation:bundle_001'],
                        'temporal_proof_objectives': ['establish_retaliation_sequence'],
                    },
                    'claim_reasoning_review': {
                        'retaliation': {
                            'proof_artifact_element_count': 1,
                            'proof_artifact_available_element_count': 1,
                            'proof_artifact_explanation_element_count': 1,
                            'proof_artifact_status_counts': {'available': 1},
                            'proof_artifact_preview': ['proof-retaliation-001'],
                            'flagged_elements': [
                                {
                                    'element_text': 'Causal connection',
                                    'proof_artifact_status': 'available',
                                    'proof_artifact_proof_status': 'success',
                                    'proof_artifact_proof_id': 'proof-retaliation-001',
                                    'proof_artifact_explanation_step_count': 1,
                                    'proof_artifact_explanation_text': 'Protected activity preceded termination.',
                                    'proof_artifact_theorem_export_metadata': {
                                        'contract_version': 'claim_support_temporal_handoff_v1',
                                        'claim_type': 'retaliation',
                                        'claim_element_id': 'causation',
                                        'proof_bundle_id': 'retaliation:causation:bundle_001',
                                        'chronology_blocked': True,
                                        'chronology_task_count': 1,
                                        'unresolved_temporal_issue_ids': ['temporal_issue_001'],
                                        'event_ids': ['event_001'],
                                        'temporal_fact_ids': ['fact_001'],
                                        'temporal_relation_ids': ['timeline_relation_001'],
                                        'timeline_issue_ids': ['temporal_issue_001'],
                                        'temporal_issue_ids': ['temporal_issue_001'],
                                        'temporal_proof_bundle_ids': ['retaliation:causation:bundle_001'],
                                        'temporal_proof_objectives': ['establish_retaliation_sequence'],
                                    },
                                }
                            ],
                        },
                    },
                    'intake_case_summary': {
                        'alignment_evidence_tasks': [
                            {
                                'task_id': 'retaliation:causation:fill_evidence_gaps',
                                'claim_type': 'retaliation',
                                'claim_element_id': 'causation',
                                'claim_element_label': 'Causal connection',
                                'action': 'fill_temporal_chronology_gap',
                                'preferred_support_kind': 'evidence',
                                'fallback_lanes': ['authority', 'testimony'],
                                'source_quality_target': 'high_quality_document',
                                'resolution_status': 'still_open',
                                'resolution_notes': '',
                                'event_ids': ['event_001'],
                                'temporal_fact_ids': ['fact_001'],
                                'temporal_relation_ids': ['timeline_relation_001'],
                                'timeline_issue_ids': ['temporal_issue_001'],
                                'temporal_issue_ids': ['temporal_issue_001'],
                                'temporal_proof_bundle_id': 'retaliation:causation:bundle_001',
                                'temporal_proof_objective': 'establish_retaliation_sequence',
                                'temporal_rule_profile_id': 'retaliation_temporal_profile_v1',
                                'temporal_rule_status': 'partial',
                                'temporal_rule_blocking_reasons': ['Need ordering between report and termination.'],
                            }
                        ],
                        'claim_support_packet_summary': {
                            'claim_count': 1,
                            'proof_readiness_score': 0.47,
                            'claim_support_unresolved_without_review_path_count': 1,
                            'claim_support_unresolved_temporal_issue_count': 1,
                            'claim_support_unresolved_temporal_issue_ids': ['temporal_issue_001'],
                            'evidence_completion_ready': False,
                            'temporal_gap_task_count': 1,
                            'temporal_gap_targeted_task_count': 1,
                            'temporal_rule_status_counts': {'partial': 1},
                            'temporal_rule_blocking_reason_counts': {'Need ordering between report and termination.': 1},
                            'temporal_resolution_status_counts': {'still_open': 1},
                        },
                    },
                }
            ).encode('utf-8'),
        }

    monkeypatch.setattr(document_api, 'retrieve_bytes', _fake_retrieve_bytes)

    response = client.get('/api/documents/optimization-trace', params={'cid': 'bafy-doc-opt-report'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'available'
    assert payload['cid'] == 'bafy-doc-opt-report'
    assert payload['size'] == 128
    assert payload['trace']['intake_status']['current_phase'] == 'intake'
    assert payload['trace']['workflow_phase_plan']['recommended_order'] == [
        'intake_questioning',
        'graph_analysis',
        'document_generation',
    ]
    assert payload['trace']['workflow_phase_plan']['phases']['graph_analysis']['status'] == 'warning'
    assert payload['trace']['intake_constraints'][0]['code'] == 'intake_blocker'
    assert payload['trace']['claim_support_temporal_handoff'] == {
        'unresolved_temporal_issue_count': 1,
        'unresolved_temporal_issue_ids': ['temporal_issue_001'],
        'chronology_task_count': 1,
        'event_ids': ['event_001'],
        'temporal_fact_ids': ['fact_001'],
        'temporal_relation_ids': ['timeline_relation_001'],
        'timeline_issue_ids': ['temporal_issue_001'],
        'temporal_issue_ids': ['temporal_issue_001'],
        'temporal_proof_bundle_ids': ['retaliation:causation:bundle_001'],
        'temporal_proof_objectives': ['establish_retaliation_sequence'],
    }
    assert payload['trace']['claim_reasoning_review']['retaliation']['proof_artifact_element_count'] == 1
    assert payload['trace']['claim_reasoning_review']['retaliation']['proof_artifact_preview'] == ['proof-retaliation-001']
    assert payload['trace']['claim_reasoning_review']['retaliation']['flagged_elements'][0]['proof_artifact_proof_id'] == 'proof-retaliation-001'
    assert payload['trace']['claim_reasoning_review']['retaliation']['flagged_elements'][0]['proof_artifact_theorem_export_metadata'] == {
        'contract_version': 'claim_support_temporal_handoff_v1',
        'claim_type': 'retaliation',
        'claim_element_id': 'causation',
        'proof_bundle_id': 'retaliation:causation:bundle_001',
        'chronology_blocked': True,
        'chronology_task_count': 1,
        'unresolved_temporal_issue_ids': ['temporal_issue_001'],
        'event_ids': ['event_001'],
        'temporal_fact_ids': ['fact_001'],
        'temporal_relation_ids': ['timeline_relation_001'],
        'timeline_issue_ids': ['temporal_issue_001'],
        'temporal_issue_ids': ['temporal_issue_001'],
        'temporal_proof_bundle_ids': ['retaliation:causation:bundle_001'],
        'temporal_proof_objectives': ['establish_retaliation_sequence'],
    }
    assert payload['trace']['intake_case_summary']['alignment_evidence_tasks'][0]['fallback_lanes'] == ['authority', 'testimony']
    assert payload['trace']['intake_case_summary']['claim_support_packet_summary']['proof_readiness_score'] == 0.47
    assert payload['trace']['intake_case_summary']['alignment_evidence_tasks'][0]['temporal_rule_status'] == 'partial'
    assert payload['trace']['intake_case_summary']['claim_support_packet_summary']['temporal_gap_task_count'] == 1


def test_review_surface_document_builder_flow_serves_page_and_supports_api_round_trip():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        'current_phase': 'intake',
        'intake_readiness': {
            'score': 0.38,
            'ready_to_advance': False,
            'remaining_gap_count': 2,
            'contradiction_count': 1,
            'blockers': ['resolve_contradictions', 'collect_missing_timeline_details'],
        },
        'intake_contradictions': [
            {
                'summary': 'Complaint date conflicts with schedule-cut date',
                'question': 'What were the exact dates for the complaint and schedule change?',
                'severity': 'high',
            }
        ],
        'complainant_summary_confirmation': {
            'status': 'confirmed',
            'confirmed': True,
            'confirmed_at': '2026-03-17T18:00:00+00:00',
            'confirmation_note': 'ready for document drafting review',
            'confirmation_source': 'dashboard',
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
    }
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = DEFAULT_OUTPUT_DIR / 'review-surface-formal-complaint.docx'
    artifact_path.write_bytes(b'PK\x03\x04mock-docx')
    try:
        mediator.build_formal_complaint_document_package.return_value = {
            "draft": {
                "title": "Jane Doe v. Acme Corporation",
                "source_context": {
                    "claim_support_temporal_handoff": {
                        "unresolved_temporal_issue_count": 1,
                        "unresolved_temporal_issue_ids": ["temporal_issue_001"],
                        "chronology_task_count": 1,
                        "event_ids": ["event_001"],
                        "temporal_fact_ids": ["fact_001"],
                        "temporal_relation_ids": ["timeline_relation_001"],
                        "timeline_issue_ids": ["temporal_issue_001"],
                        "temporal_issue_ids": ["temporal_issue_001"],
                        "temporal_proof_bundle_ids": ["retaliation:causation:bundle_001"],
                        "temporal_proof_objectives": ["establish_retaliation_sequence"],
                    },
                    "claim_reasoning_review": {
                        "retaliation": {
                            "proof_artifact_element_count": 1,
                            "proof_artifact_preview": ["proof-retaliation-001"],
                        }
                    },
                },
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
            "claim_support_temporal_handoff": {
                "unresolved_temporal_issue_count": 1,
                "unresolved_temporal_issue_ids": ["temporal_issue_001"],
                "chronology_task_count": 1,
                "event_ids": ["event_001"],
                "temporal_fact_ids": ["fact_001"],
                "temporal_relation_ids": ["timeline_relation_001"],
                "timeline_issue_ids": ["temporal_issue_001"],
                "temporal_issue_ids": ["temporal_issue_001"],
                "temporal_proof_bundle_ids": ["retaliation:causation:bundle_001"],
                "temporal_proof_objectives": ["establish_retaliation_sequence"],
            },
            "claim_reasoning_review": {
                "retaliation": {
                    "proof_artifact_element_count": 1,
                    "proof_artifact_preview": ["proof-retaliation-001"],
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
        assert 'Intake Review Signals' in page_html
        assert 'Intake blockers:' in page_html
        assert 'Tracked intake contradictions:' in page_html
        assert 'Intake Summary Handoff' in page_html
        assert 'Confirm intake summary' in page_html
        assert '/api/claim-support/confirm-intake-summary' in page_html
        assert 'Checklist Intake Signals' in page_html
        assert 'Checklist intake blockers:' in page_html
        assert 'Open Section Review' in page_html
        assert 'formalComplaintBuilderState' in page_html
        assert 'formalComplaintBuilderPreview' in page_html
        assert 'Pleading Text' in page_html
        assert 'Copy Pleading Text' in page_html
        assert 'value="txt"' in page_html
        assert 'value="checklist"' in page_html
        assert 'value="packet"' in page_html
        assert 'Drafting Readiness' in page_html
        assert 'Workflow Phase Guidance' in page_html
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
        assert 'Advanced Optimization LLM Config (JSON)' in page_html
        assert 'optimizationAdvancedConfigError' in page_html
        assert 'Advanced optimization config must be a valid JSON object.' in page_html
        assert 'Persist optimization trace through the IPFS adapter' in page_html
        assert 'Document Optimization' in page_html
        assert 'Persisted Trace Snapshot' in page_html
        assert 'Optimization Focus' in page_html
        assert 'Relief-targeted optimization' in page_html
        assert 'Accepted Changes' in page_html
        assert 'Rejected Changes' in page_html
        assert 'Intake Constraints' in page_html
        assert 'Optimized Sections' in page_html
        assert 'Trace CID' in page_html
        assert 'Persisted intake phase' in page_html
        assert 'Persisted intake contradictions' in page_html
        assert 'Router Usage' in page_html
        assert 'Claim Support Chronology Handoff' in page_html
        assert 'Claim support chronology handoff:' in page_html
        assert 'Claim support chronology tasks:' in page_html
        assert 'Claim Reasoning Review' in page_html
        assert 'Claim reasoning reviews:' in page_html
        assert 'theorem chronology:' in page_html
        assert 'Upstream Optimizer' in page_html
        assert 'Stage Provider Selection' in page_html
        assert 'Packet Projection' in page_html
        assert 'Initial Review' in page_html
        assert 'Final Review' in page_html
        assert 'Effective provider' in page_html
        assert 'Provider source' in page_html
        assert 'Task complexity' in page_html
        assert 'Selected route' in page_html
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
        assert payload['intake_summary_handoff'] == {
            'current_phase': 'intake',
            'ready_to_advance': False,
            'complainant_summary_confirmation': {
                'status': 'confirmed',
                'confirmed': True,
                'confirmed_at': '2026-03-17T18:00:00+00:00',
                'confirmation_note': 'ready for document drafting review',
                'confirmation_source': 'dashboard',
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
        }
        assert payload['claim_support_temporal_handoff'] == {
            'unresolved_temporal_issue_count': 1,
            'unresolved_temporal_issue_ids': ['temporal_issue_001'],
            'chronology_task_count': 1,
            'event_ids': ['event_001'],
            'temporal_fact_ids': ['fact_001'],
            'temporal_relation_ids': ['timeline_relation_001'],
            'timeline_issue_ids': ['temporal_issue_001'],
            'temporal_issue_ids': ['temporal_issue_001'],
            'temporal_proof_bundle_ids': ['retaliation:causation:bundle_001'],
            'temporal_proof_objectives': ['establish_retaliation_sequence'],
        }
        assert payload['claim_reasoning_review']['retaliation']['proof_artifact_element_count'] == 1
        assert payload['claim_reasoning_review']['retaliation']['proof_artifact_preview'] == ['proof-retaliation-001']
        assert payload['draft']['source_context']['claim_support_temporal_handoff'] == payload['claim_support_temporal_handoff']
        assert payload['draft']['source_context']['claim_reasoning_review'] == payload['claim_reasoning_review']
        _assert_normalized_intake_status(payload['review_links']['intake_status'], score=0.38)
        assert payload.get('document_optimization') in (None, {})
        assert any(
            warning.get('code') == 'intake_blocker'
            and warning.get('message') == 'Intake blocker: resolve_contradictions'
            for warning in payload['drafting_readiness']['warnings']
        )
        assert any(
            warning.get('code') == 'intake_contradiction'
            and 'Complaint date conflicts with schedule-cut date' in str(warning.get('message') or '')
            for warning in payload['drafting_readiness']['warnings']
        )
        assert any(
            warning.get('code') == 'intake_blocker'
            for warning in payload['drafting_readiness']['sections']['claims_for_relief']['warnings']
        )
        assert any(
            warning.get('code') == 'intake_blocker'
            for warning in payload['drafting_readiness']['claims'][0]['warnings']
        )
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


def test_review_surface_document_builder_serves_runtime_validation_contract():
    mediator = _build_mediator()
    app = create_review_surface_app(mediator)
    client = TestClient(app)

    page_response = client.get('/document')

    assert page_response.status_code == 200
    script = _document_page_inline_script(page_response.text)
    generate_document_start = script.index('async function generateDocument(event)')
    reset_form_start = script.index('function resetForm()')
    bootstrap_start = script.index('async function bootstrap()')
    event_binding_start = script.index("document.getElementById('documentForm').addEventListener('submit', generateDocument);")

    assert 'function setOptimizationAdvancedConfigError(message)' in script
    assert 'field.setCustomValidity(errorMessage);' in script
    assert "errorNode.classList.toggle('visible', Boolean(errorMessage));" in script
    assert 'function parseOptimizationAdvancedConfig(rawValue)' in script
    assert "throw new Error('Advanced optimization config must be a valid JSON object.');" in script
    assert 'function validateOptimizationAdvancedConfig()' in script
    assert "setOptimizationAdvancedConfigError(error.message || 'Advanced optimization config must be a valid JSON object.');" in script
    assert "let optimizationLlmConfig = { ...parseOptimizationAdvancedConfig(optimizationAdvancedConfigRaw) };" in script
    assert "showBox('errorBox', error.message || 'Invalid optimization configuration.');" in script[generate_document_start:reset_form_start]
    assert "setOptimizationAdvancedConfigError('');" in script[reset_form_start:bootstrap_start]
    assert script[bootstrap_start:event_binding_start].count('validateOptimizationAdvancedConfig();') == 2
    assert "document.getElementById('optimizationAdvancedConfig').addEventListener('input', validateOptimizationAdvancedConfig);" in script[event_binding_start:]
    assert "document.getElementById('optimizationAdvancedConfig').addEventListener('change', validateOptimizationAdvancedConfig);" in script[event_binding_start:]


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
    assert report['trace_download_url'] == '/api/documents/optimization-trace?cid=bafy-doc-opt-report'
    assert report['trace_view_url'] == '/document/optimization-trace?cid=bafy-doc-opt-report'
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
    assert report['intake_case_summary']['canonical_fact_summary']['count'] == 2
    assert report['intake_case_summary']['proof_lead_summary']['count'] == 1
    assert report['intake_case_summary']['question_candidate_summary']['count'] == 1
    assert report['intake_case_summary']['question_candidate_summary']['question_goal_counts']['identify_supporting_proof'] == 1
    assert report['intake_case_summary']['alignment_evidence_tasks'][0]['fallback_lanes'] == ['authority', 'testimony']
    assert report['intake_case_summary']['alignment_evidence_tasks'][0]['source_quality_target'] == 'high_quality_document'
    assert report['intake_case_summary']['alignment_task_summary']['temporal_gap_task_count'] == 1
    assert report['intake_case_summary']['alignment_task_summary']['temporal_rule_blocking_reason_counts'] == {
        'Need retaliation chronology sequencing.': 1,
    }
    assert report['intake_case_summary']['claim_support_packet_summary']['claim_count'] == 2
    assert report['intake_case_summary']['claim_support_packet_summary']['proof_readiness_score'] == 0.47
    assert report['intake_case_summary']['claim_support_packet_summary']['evidence_completion_ready'] is False
    assert report['claim_reasoning_review']['retaliation']['proof_artifact_element_count'] == 1
    assert report['claim_reasoning_review']['retaliation']['proof_artifact_available_element_count'] == 1
    assert report['claim_reasoning_review']['retaliation']['proof_artifact_status_counts'] == {'available': 1}
    assert report['claim_reasoning_review']['retaliation']['flagged_elements'][0]['proof_artifact_proof_id'] == 'proof-retaliation-001'
    assert report['claim_reasoning_review']['retaliation']['flagged_elements'][0]['proof_artifact_explanation_text'] == 'Protected activity preceded termination.'
    assert report['claim_reasoning_review']['retaliation']['flagged_elements'][0]['proof_artifact_theorem_export_metadata'] == {
        'contract_version': 'claim_support_temporal_handoff_v1',
        'claim_type': 'retaliation',
        'claim_element_id': 'causation',
        'proof_bundle_id': 'retaliation:causation:bundle_001',
        'chronology_blocked': True,
        'chronology_task_count': 1,
        'unresolved_temporal_issue_ids': ['temporal_issue_001'],
        'event_ids': ['event_001'],
        'temporal_fact_ids': ['fact_001'],
        'temporal_relation_ids': ['timeline_relation_001'],
        'timeline_issue_ids': ['temporal_issue_001'],
        'temporal_issue_ids': ['temporal_issue_001'],
        'temporal_proof_bundle_ids': ['retaliation:causation:bundle_001'],
        'temporal_proof_objectives': ['establish_retaliation_sequence'],
    }
    assert payload['claim_support_temporal_handoff'] == {
        'unresolved_temporal_issue_count': 1,
        'unresolved_temporal_issue_ids': ['temporal_issue_001'],
        'chronology_task_count': 1,
        'event_ids': ['event_001'],
        'temporal_fact_ids': ['fact_001'],
        'temporal_relation_ids': ['timeline_relation_001'],
        'timeline_issue_ids': ['temporal_issue_001'],
        'temporal_issue_ids': ['temporal_issue_001'],
        'temporal_proof_bundle_ids': ['retaliation:causation:bundle_001'],
        'temporal_proof_objectives': ['establish_retaliation_sequence'],
    }
    assert payload['claim_reasoning_review']['retaliation']['proof_artifact_element_count'] == 1
    assert payload['claim_reasoning_review']['retaliation']['flagged_elements'][0]['proof_artifact_theorem_export_metadata'] == {
        'contract_version': 'claim_support_temporal_handoff_v1',
        'claim_type': 'retaliation',
        'claim_element_id': 'causation',
        'proof_bundle_id': 'retaliation:causation:bundle_001',
        'chronology_blocked': True,
        'chronology_task_count': 1,
        'unresolved_temporal_issue_ids': ['temporal_issue_001'],
        'event_ids': ['event_001'],
        'temporal_fact_ids': ['fact_001'],
        'temporal_relation_ids': ['timeline_relation_001'],
        'timeline_issue_ids': ['temporal_issue_001'],
        'temporal_issue_ids': ['temporal_issue_001'],
        'temporal_proof_bundle_ids': ['retaliation:causation:bundle_001'],
        'temporal_proof_objectives': ['establish_retaliation_sequence'],
    }
    assert payload['draft']['source_context']['claim_support_temporal_handoff'] == payload['claim_support_temporal_handoff']
    assert payload['draft']['source_context']['claim_reasoning_review'] == payload['claim_reasoning_review']
    _assert_normalized_intake_status(report['intake_status'], score=0.38)
    assert report['intake_constraints'] == [
        {
            'severity': 'warning',
            'code': 'intake_blocker',
            'message': 'Intake blocker: resolve_contradictions',
        },
        {
            'severity': 'warning',
            'code': 'intake_blocker',
            'message': 'Intake blocker: collect_missing_timeline_details',
        },
        {
            'severity': 'warning',
            'code': 'intake_contradiction',
            'message': 'Complaint date conflicts with schedule-cut date. Clarify: What were the exact dates for the complaint and schedule change?',
        },
    ]
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
        pytest.skip('Set a Hugging Face token in the environment or log in with huggingface_hub to run the live Hugging Face router review-surface smoke test')

    mediator = _build_mediator()
    mediator.build_formal_complaint_document_package.side_effect = (
        lambda **kwargs: FormalComplaintDocumentBuilder(mediator).build_package(**kwargs)
    )

    app = create_review_surface_app(mediator)
    client = TestClient(app)
    page_response = client.get('/document')

    assert page_response.status_code == 200
    assert '/api/documents/formal-complaint' in page_response.text

    _, api_response, payload, _ = _post_live_hf_optimization_request(
        client,
        output_dir=str(tmp_path),
        page_title='Complaint Generator Review Surface Smoke Test',
        include_arch_router=False,
    )

    assert api_response.status_code == 200, api_response.text
    assert payload['document_optimization']['router_status']['llm_router'] == 'available'
    assert payload['document_optimization']['iteration_count'] == 1
    assert payload['document_optimization']['initial_score'] >= 0.0
    assert payload['document_optimization']['final_score'] >= 0.0
    assert payload['document_optimization']['trace_storage']['status'] == 'disabled'
    assert payload['draft']['draft_text']
    assert Path(payload['artifacts']['txt']['path']).exists()
    assert 'download_url' not in payload['artifacts']['txt']

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
