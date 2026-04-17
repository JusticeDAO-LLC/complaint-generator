import json
import socket
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import Mock

import pytest

requests = pytest.importorskip("requests")
uvicorn = pytest.importorskip("uvicorn")
pytest.importorskip("multipart")

FastAPI = pytest.importorskip("fastapi").FastAPI
HTMLResponse = pytest.importorskip("fastapi.responses").HTMLResponse
JSONResponse = pytest.importorskip("fastapi.responses").JSONResponse
WebSocketDisconnect = pytest.importorskip("fastapi").WebSocketDisconnect

from applications.review_ui import create_review_surface_app
from tests.test_claim_support_review_dashboard_flow import _build_dashboard_mediator


pytestmark = [pytest.mark.no_auto_network, pytest.mark.browser]

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False


SAMPLE_COOKIES = {
    "hashed_username": "site-smoke-user",
    "hashed_password": "site-smoke-secret",
    "token": "None",
}

SAMPLE_PROFILE = {
    "hashed_username": "site-smoke-user",
    "hashed_password": "site-smoke-secret",
    "chat_history": {
        "2026-03-22T12:00:00Z": {
            "sender": "Bot:",
            "message": "Tell me what happened.",
            "explanation": {"summary": "Collect the intake narrative."},
        },
        "2026-03-22T12:01:00Z": {
            "sender": "site-smoke-user",
            "message": "I reported discrimination and was terminated two days later.",
        },
    },
    "complaint_summary": {
        "plaintiff-name": {"primary": "Jane Doe"},
        "defendant-name": {"primary": "Acme Corporation"},
        "district_name": "Northern District of California",
        "division_name": "San Francisco Division",
        "county_name": "San Francisco County",
        "relief": "Back pay, reinstatement, compensatory damages, and equitable relief.",
    },
}

TRACE_CID = "bafy-site-trace"
TRACE_PAYLOAD = {
    "user_id": "trace-smoke-user",
    "intake_status": {
        "current_phase": "intake",
        "score": 0.52,
        "contradiction_count": 1,
        "blockers": ["collect_missing_support"],
        "criteria": {
            "case_theory_coherent": True,
            "minimum_proof_path_present": True,
            "claim_disambiguation_resolved": False,
        },
        "contradictions": [
            {
                "summary": "Termination date conflicts with reported complaint timeline",
                "question": "Which date is supported by the termination notice?",
                "recommended_resolution_lane": "request_document",
                "current_resolution_status": "open",
                "external_corroboration_required": True,
                "affected_claim_types": ["retaliation"],
                "affected_element_ids": ["retaliation:2"],
            }
        ],
    },
    "intake_constraints": [],
    "intake_case_summary": {
        "candidate_claims": [
            {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.87},
            {"claim_type": "wrongful_termination", "label": "Wrongful Termination", "confidence": 0.79},
        ],
        "complainant_summary_confirmation": {
            "status": "pending",
            "confirmed": False,
            "confirmation_source": "complainant",
            "confirmation_note": "",
            "summary_snapshot_index": 0,
            "current_summary_snapshot": {
                "candidate_claim_count": 2,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
            "confirmed_summary_snapshot": {},
        },
        "intake_sections": {
            "proof_leads": {"status": "partial", "missing_items": ["documents"]},
            "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
        },
        "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
        "canonical_fact_intent_summary": {
            "count": 1,
            "question_objective_counts": {"establish_chronology": 1},
            "expected_update_kind_counts": {"timeline_anchor": 1},
            "target_claim_type_counts": {"retaliation": 1},
            "target_element_id_counts": {"retaliation:1": 1},
        },
        "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
        "proof_lead_intent_summary": {
            "count": 1,
            "question_objective_counts": {"identify_supporting_evidence": 1},
            "expected_update_kind_counts": {"proof_lead": 1},
            "target_claim_type_counts": {"retaliation": 1},
            "target_element_id_counts": {"retaliation:2": 1},
        },
        "timeline_anchor_summary": {"count": 1, "anchors": [{"anchor_id": "timeline_anchor_001"}]},
        "harm_profile": {"count": 1, "categories": ["economic"]},
        "remedy_profile": {"count": 1, "categories": ["monetary"]},
        "question_candidate_summary": {
            "count": 2,
            "question_goal_counts": {"identify_supporting_proof": 1, "establish_element": 1},
            "phase1_section_counts": {"proof_leads": 1, "claims_for_relief": 1},
            "blocking_level_counts": {"blocking": 1, "non_blocking": 1},
        },
        "alignment_evidence_tasks": [
            {
                "task_id": "retaliation:retaliation:2:fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:2",
                "claim_element_label": "Claims For Relief",
                "action": "fill_temporal_chronology_gap",
                "preferred_support_kind": "evidence",
                "fallback_lanes": ["authority", "testimony"],
                "source_quality_target": "high_quality_document",
                "resolution_status": "awaiting_complainant_record",
                "temporal_rule_profile_id": "retaliation_temporal_profile_v1",
                "temporal_rule_status": "partial",
                "temporal_rule_blocking_reasons": [
                    "Retaliation timeline lacks a clear ordering between protected activity and termination.",
                ],
            }
        ],
        "claim_support_packet_summary": {
            "claim_count": 1,
            "element_count": 2,
            "status_counts": {"unsupported": 2},
            "recommended_actions": ["collect_missing_support_kind"],
            "supported_blocking_element_ratio": 0.5,
            "credible_support_ratio": 0.5,
            "draft_ready_element_ratio": 0.0,
            "high_quality_parse_ratio": 0.0,
            "reviewable_escalation_ratio": 0.5,
            "claim_support_reviewable_escalation_count": 1,
            "proof_readiness_score": 0.225,
            "claim_support_unresolved_without_review_path_count": 1,
            "evidence_completion_ready": False,
            "temporal_fact_count": 2,
            "temporal_relation_count": 1,
            "temporal_issue_count": 1,
            "temporal_partial_order_ready_element_count": 0,
            "temporal_warning_count": 1,
            "temporal_gap_task_count": 1,
            "temporal_gap_targeted_task_count": 1,
            "temporal_rule_status_counts": {"partial": 1},
            "temporal_rule_blocking_reason_counts": {
                "Retaliation timeline lacks a clear ordering between protected activity and termination.": 1,
            },
            "temporal_resolution_status_counts": {"awaiting_complainant_record": 1},
        },
        "temporal_issue_registry_summary": {
            "count": 2,
            "unresolved_count": 1,
            "resolved_count": 1,
            "status_counts": {"open": 1, "resolved": 1},
            "issue_ids": ["timeline-gap-001", "timeline-gap-closed-001"],
        },
        "alignment_task_update_history": [
            {
                "task_id": "retaliation:claims_for_relief:resolve_support_conflicts",
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:2",
                "claim_element_label": "Claims For Relief",
                "action": "resolve_support_conflicts",
                "current_support_status": "contradicted",
                "resolution_status": "needs_manual_review",
                "status": "active",
                "evidence_artifact_id": "artifact-conflict",
                "evidence_sequence": 2,
            }
        ],
    },
    "iterations": [
        {
            "iteration": 1,
            "focus_section": "factual_allegations",
            "accepted": True,
            "critic": {"overall_score": 0.73},
        }
    ],
    "initial_review": {"overall_score": 0.41},
    "final_review": {"overall_score": 0.73, "recommended_focus": "claims_for_relief"},
}


@contextmanager
def _serve_app(app: FastAPI):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://{host}:{port}"
    deadline = time.time() + 15
    last_error = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/health", timeout=0.5)
            if response.ok:
                break
        except Exception as exc:  # pragma: no cover - startup timing only
            last_error = exc
        time.sleep(0.1)
    else:  # pragma: no cover - hard failure path
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError(f"Timed out waiting for local review server: {last_error}")

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _build_document_package(artifact_dir: Path) -> dict:
    docx_path = artifact_dir / "formal-complaint.docx"
    pdf_path = artifact_dir / "formal-complaint.pdf"
    docx_path.write_bytes(b"docx")
    pdf_path.write_bytes(b"pdf")
    return {
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT FOR THE NORTHERN DISTRICT OF CALIFORNIA",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
                "case_number": "26-cv-00001",
                "document_title": "COMPLAINT",
            },
            "nature_of_action": [
                "This action arises from retaliation after protected workplace complaints.",
            ],
            "summary_of_facts": [
                "Plaintiff reported discrimination to human resources.",
                "Defendant terminated Plaintiff two days later.",
            ],
            "factual_allegation_paragraphs": [
                "Plaintiff engaged in protected activity by reporting discrimination.",
                "Defendant terminated Plaintiff shortly after the complaint.",
            ],
            "legal_standards": [
                "Retaliation requires protected activity, adverse action, and causation.",
            ],
            "claims_for_relief": [
                {
                    "claim_type": "retaliation",
                    "title": "First Claim for Relief - Retaliation",
                    "paragraphs": [
                        "Plaintiff realleges the preceding allegations.",
                        "Defendant retaliated against Plaintiff after protected activity.",
                    ],
                }
            ],
            "requested_relief": [
                "Back pay.",
                "Compensatory damages.",
                "Injunctive relief.",
            ],
            "signature_block": {"name": "Jane Doe", "signature_line": "Jane Doe"},
            "verification": {"title": "Verification", "text": "I declare under penalty of perjury that the foregoing is true and correct."},
            "certificate_of_service": {"title": "Certificate of Service", "text": "I certify service on Defendant."},
            "draft_text": "Jane Doe alleges retaliation against Acme Corporation.",
            "exhibits": [],
        },
        "filing_checklist": [
            {
                "scope": "claim",
                "key": "retaliation",
                "title": "Retaliation",
                "status": "ready",
                "summary": "Retaliation is ready for filing review.",
            }
        ],
        "drafting_readiness": {
            "status": "ready",
            "sections": {},
            "claims": [{"claim_type": "retaliation", "status": "ready", "warnings": []}],
            "warning_count": 0,
        },
        "artifacts": {
            "docx": {"path": str(docx_path), "filename": docx_path.name, "size_bytes": docx_path.stat().st_size},
            "pdf": {"path": str(pdf_path), "filename": pdf_path.name, "size_bytes": pdf_path.stat().st_size},
        },
        "output_formats": ["docx", "pdf"],
        "generated_at": "2026-03-22T12:00:00+00:00",
    }


@pytest.fixture
def site_app(monkeypatch: pytest.MonkeyPatch):
    import applications.complaint_workspace as complaint_workspace_module
    import applications.document_api as document_api_module
    import applications.ui_review as ui_review_module
    import complaint_generator.ui_ux_workflow as ui_ux_workflow_module

    mediator = _build_dashboard_mediator()
    artifact_dir = Path(tempfile.mkdtemp(prefix="complaint-site-playwright-"))
    mediator.build_formal_complaint_document_package = Mock(return_value=_build_document_package(artifact_dir))

    trace_bytes = json.dumps(TRACE_PAYLOAD).encode("utf-8")

    def fake_retrieve_bytes(cid: str) -> dict:
        if cid == TRACE_CID:
            return {"status": "available", "data": trace_bytes, "size": len(trace_bytes)}
        return {"status": "missing", "error": "unknown cid"}

    monkeypatch.setattr(document_api_module, "retrieve_bytes", fake_retrieve_bytes)

    def fake_refine_draft_with_llm_router(self, state, base_draft, **kwargs):
        answers = dict(state.get("intake_answers") or {})
        plaintiff = str(answers.get("party_name") or "Jane Doe").strip()
        defendant = str(answers.get("opposing_party") or "Acme Corporation").strip()
        claim_type = str(base_draft.get("claim_type") or state.get("claim_type") or "retaliation").strip() or "retaliation"
        claim_label = "Housing Discrimination" if claim_type == "housing_discrimination" else "Retaliation"
        count_heading = "COUNT I - HOUSING DISCRIMINATION" if claim_type == "housing_discrimination" else "COUNT I - RETALIATION"
        relief = [str(item).strip() for item in list(base_draft.get("requested_relief") or ["Back pay", "Injunctive relief"]) if str(item).strip()]
        relief_lines = "\n".join(f"{index + 1}. {item}" for index, item in enumerate(relief))
        body = "\n\n".join(
            [
                "IN THE UNITED STATES DISTRICT COURT",
                str(answers.get("court_header") or "FOR THE NORTHERN DISTRICT OF CALIFORNIA").strip(),
                "",
                f"{plaintiff}, Plaintiff,",
                "v.",
                f"{defendant}, Defendant.",
                "",
                "Civil Action No. ________________",
                f"COMPLAINT FOR {claim_label.upper()}",
                "JURY TRIAL DEMANDED",
                "",
                "NATURE OF THE ACTION",
                f"{plaintiff} brings this {claim_label.lower()} complaint against {defendant}.",
                "",
                "JURISDICTION AND VENUE",
                "Jurisdiction and venue are proper because the events described here were directed into this district.",
                "",
                "PARTIES",
                f"1. Plaintiff {plaintiff} is the complainant injured by Defendant's conduct.",
                f"2. Defendant {defendant} is the opposing party responsible for the acts described below.",
                "",
                "FACTUAL ALLEGATIONS",
                f"3. Plaintiff engaged in protected activity by {str(answers.get('protected_activity') or 'reporting misconduct').strip().lower()}.",
                f"4. Defendant then took adverse action by {str(answers.get('adverse_action') or 'terminating Plaintiff').strip().lower()}.",
                f"5. The relevant chronology is as follows: {str(answers.get('timeline') or 'the complaint and retaliation occurred in close proximity').strip()}.",
                f"6. Plaintiff suffered harm including {str(answers.get('harm') or 'economic and emotional injury').strip().lower()}.",
                "",
                "EVIDENTIARY SUPPORT AND NOTICE",
                "7. Plaintiff has preserved testimony and documentary evidence supporting the chronology, causation, and resulting harm.",
                "8. Plaintiff will supplement authenticated exhibits and additional testimony as discovery proceeds.",
                "",
                "CLAIM FOR RELIEF",
                count_heading,
                "9. Plaintiff repeats and realleges the preceding paragraphs as if fully set forth herein.",
                "10. Defendant's conduct violated the governing anti-retaliation protections and entitles Plaintiff to relief.",
                "",
                "PRAYER FOR RELIEF",
                "Wherefore, Plaintiff respectfully requests judgment against Defendant and the following relief:",
                relief_lines or "1. Appropriate relief according to proof.",
                "",
                "JURY DEMAND",
                "Plaintiff demands a trial by jury on all issues so triable.",
                "",
                "SIGNATURE BLOCK",
                "Dated: ____________________",
                "",
                "Respectfully submitted,",
                "",
                plaintiff,
                "Plaintiff, Pro Se",
                "Address: ____________________",
                "Telephone: ____________________",
                "Email: ____________________",
            ]
        )
        return {
            **dict(base_draft or {}),
            "title": f"{plaintiff} v. {defendant} {claim_label} Complaint",
            "body": body,
            "requested_relief": relief,
            "draft_strategy": "llm_router",
            "draft_backend": {
                "id": "formal_complaint_reviewer",
                "provider": "llm_router",
                "model": "formal_complaint_reviewer",
                "requested_provider": kwargs.get("provider") or "llm_router",
                "requested_model": kwargs.get("model") or "formal_complaint_reviewer",
            },
            "draft_normalizations": [],
        }

    def fake_review_complaint_output_with_llm_router(markdown_text, **kwargs):
        claim_type = str(kwargs.get("claim_type") or "retaliation").strip() or "retaliation"
        return {
            "backend": {
                "strategy": "llm_router",
                "provider": "llm_router",
                "model": "formal_complaint_reviewer",
            },
            "review": {
                "summary": f"The {claim_type.replace('_', ' ')} complaint reads like a formal filing and is suitable for continued UI-guided review.",
                "filing_shape_score": 96,
                "claim_type_alignment_score": 95,
                "strengths": ["Caption is present", "Prayer for relief is present", "Signature posture is visible"],
                "missing_formal_sections": [],
                "issues": [
                    {
                        "severity": "low",
                        "finding": "Export warnings could still be more explicit before download.",
                        "complaint_impact": "The filing is strong, but users still need clearer readiness messaging.",
                        "ui_implication": "The draft and integrations surfaces should keep the release gate visible before export.",
                    }
                ],
                "ui_suggestions": [
                    {
                        "title": "Keep the release gate visible before export",
                        "target_surface": "draft,review,integrations",
                        "recommendation": "Show the filing-shape score and release verdict beside the download controls.",
                        "why_it_matters": "This keeps users from treating a draft as filing-ready without checking support and export posture.",
                    }
                ],
                "ui_priority_repairs": [
                    {
                        "priority": "high",
                        "target_surface": "draft,integrations",
                        "repair": "Preserve filing-shape and support warnings beside the export buttons.",
                        "filing_benefit": "Users are less likely to download a complaint without understanding readiness and support.",
                    }
                ],
                "actor_risk_summary": "The actor can now reach a formal complaint, but still needs explicit release-gate cues before export.",
                "critic_gate": {
                    "verdict": "pass",
                    "blocking_reason": "",
                    "required_repairs": ["Keep export readiness messaging visible."],
                },
            },
        }

    def fake_iterative_ui_ux_workflow(**kwargs):
        screenshot_dir = str(kwargs.get("screenshot_dir") or "artifacts/ui-audit/screenshots")
        output_dir = str(kwargs.get("output_dir") or "artifacts/ui-audit/reviews")
        return {
            "iterations": int(kwargs.get("iterations") or 1),
            "screenshot_dir": screenshot_dir,
            "output_dir": output_dir,
            "workflow_type": "iterative_ui_review",
            "backend": {
                "strategy": "multimodal_router",
                "provider": "llm_router",
                "model": "multimodal_router",
            },
            "latest_review": "Multimodal actor/critic review complete. Complaint-output suggestion carried into router review.",
            "review": {
                "summary": "Multimodal actor/critic review complete. Complaint-output suggestion carried into router review.",
                "issues": [
                    {
                        "severity": "medium",
                        "surface": "/workspace",
                        "problem": "The export controls still compete with draft-editing controls.",
                        "user_impact": "A complainant could download too early without noticing the release gate.",
                        "recommended_fix": "Keep export warnings and next-step guidance pinned near the download buttons.",
                    }
                ],
                "broken_controls": [
                    {
                        "surface": "/workspace",
                        "control": "Download Markdown",
                        "failure_mode": "Users may treat download as the primary CTA before reviewing readiness.",
                        "repair": "Pin the release gate and support summary beside the export controls.",
                    }
                ],
                "button_audit": [
                    {
                        "surface": "/workspace",
                        "control": "Run Iterative UX Review",
                        "expected_outcome": "Produce a multimodal actor/critic report for the current screenshot set.",
                        "status": "pass",
                        "notes": "The optimizer lane is exposed and actionable.",
                    }
                ],
                "route_handoffs": [
                    {
                        "from_surface": "workspace",
                        "to_surface": "chat",
                        "trigger": "handoff-chat-button",
                        "state_requirements": ["shared DID", "case synopsis"],
                        "status": "pass",
                    }
                ],
                "complaint_journey": {
                    "tested_stages": ["chat", "intake", "evidence", "review", "draft", "integrations", "optimizer"],
                    "journey_gaps": ["Export warnings should remain more prominent beside the download controls."],
                    "sdk_tool_invocations": ["complaint.generate_complaint", "complaint.review_generated_exports", "complaint.review_ui"],
                    "release_blockers": [],
                },
                "actor_plan": {
                    "primary_objective": "Keep the release gate visible until the complaint is downloaded.",
                    "repair_sequence": ["Pin release-gate messaging beside exports", "Reduce competing CTAs in the draft panel"],
                },
                "critic_review": {
                    "verdict": "warning",
                    "blocking_findings": ["Export controls still need stronger readiness framing."],
                    "acceptance_checks": ["Download controls must keep the release gate visible.", "The optimizer report must stay wired to MCP tool invocations."],
                },
                "actor_summary": "The actor can complete the complaint, but export messaging still needs to feel safer and more linear.",
                "critic_summary": "The critic accepts the flow, but wants a stronger release-gate emphasis near download controls.",
                "actor_path_breaks": ["Export feels slightly too easy relative to the readiness messaging."],
                "critic_test_obligations": ["Verify the release gate remains visible after complaint generation and before download."],
                "stage_findings": {
                    "Draft": "Complaint-output suggestion carried into router review.",
                    "Integration Discovery": "The MCP tool contract remains visible from the workspace integrations panel.",
                },
                "playwright_followups": ["Capture the draft panel after the release gate updates and before export."],
                "screenshot_findings": [
                    {
                        "name": "workspace-draft",
                        "stage": "Draft",
                        "surface": "/workspace?tab=draft",
                        "stage_finding": "The screenshot shows export controls overshadowing readiness guidance.",
                        "criticisms": [
                            {
                                "problem": "The export controls still compete with draft-editing controls.",
                                "recommended_fix": "Keep export warnings and next-step guidance pinned near the download buttons.",
                            }
                        ],
                    }
                ],
                "optimization_targets": [
                    {
                        "title": "Pin release-gate messaging beside exports",
                        "target_surface": "templates/workspace.html",
                        "reason": "The screenshot review shows the actor can download too early unless readiness stays visually dominant.",
                    }
                ],
            },
            "screenshot_findings": [
                {
                    "name": "workspace-draft",
                    "stage": "Draft",
                    "surface": "/workspace?tab=draft",
                    "stage_finding": "The screenshot shows export controls overshadowing readiness guidance.",
                    "criticisms": [
                        {
                            "problem": "The export controls still compete with draft-editing controls.",
                            "recommended_fix": "Keep export warnings and next-step guidance pinned near the download buttons.",
                        }
                    ],
                }
            ],
            "optimization_targets": [
                {
                    "title": "Pin release-gate messaging beside exports",
                    "target_surface": "templates/workspace.html",
                    "reason": "The screenshot review shows the actor can download too early unless readiness stays visually dominant.",
                }
            ],
            "carry_forward_assessment": {
                "prior_review_available": True,
                "unresolved_findings": [
                    {
                        "stage": "Draft",
                        "surface": "/workspace?tab=draft",
                        "summary": "Export messaging is still competing with other draft actions.",
                    }
                ],
                "resolved_findings": [
                    {
                        "stage": "Review",
                        "surface": "/workspace?tab=review",
                        "summary": "Support-gap guidance is more visible than it was before.",
                    }
                ],
                "continued_optimization_targets": [
                    {
                        "title": "Pin release-gate messaging beside exports",
                        "target_surface": "templates/workspace.html",
                        "reason": "The export lane still needs stronger readiness framing.",
                    }
                ],
                "retired_optimization_targets": [],
                "summary": "1 prior screenshot finding still appears unresolved. 1 prior screenshot finding looks improved or no longer visible. 1 optimization target carried forward into this pass.",
            },
            "runs": [
                {
                    "iteration": 1,
                    "review_excerpt": "Multimodal actor/critic review complete. Complaint-output suggestion carried into router review.",
                    "issues_count": 1,
                    "broken_controls_count": 1,
                    "optimization_target_count": 1,
                    "carry_forward_summary": "1 prior screenshot finding still appears unresolved.",
                }
            ],
        }

    def fake_browser_audit(**kwargs):
        return {
            "command": ["playwright", "test", "complaint-flow.spec.js"],
            "returncode": 0,
            "artifact_count": 6,
            "screenshot_dir": str(kwargs.get("screenshot_dir") or "artifacts/ui-audit/browser-audit"),
        }

    monkeypatch.setattr(
        complaint_workspace_module.ComplaintWorkspaceService,
        "_refine_draft_with_llm_router",
        fake_refine_draft_with_llm_router,
    )
    monkeypatch.setattr(ui_review_module, "review_complaint_output_with_llm_router", fake_review_complaint_output_with_llm_router)
    monkeypatch.setattr(ui_ux_workflow_module, "run_iterative_ui_ux_workflow", fake_iterative_ui_ux_workflow)
    monkeypatch.setattr(ui_ux_workflow_module, "run_end_to_end_complaint_browser_audit", fake_browser_audit)

    app = create_review_surface_app(mediator)

    @app.get("/cookies", response_class=HTMLResponse)
    async def read_cookies() -> str:
        return json.dumps(SAMPLE_COOKIES)

    @app.post("/load_profile")
    async def load_profile() -> JSONResponse:
        return JSONResponse({"data": json.dumps(SAMPLE_PROFILE)})

    @app.post("/search")
    async def search_stub() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.websocket("/api/chat")
    async def chat_socket(websocket):
        await websocket.accept()
        await websocket.send_json(
            {
                "sender": "System:",
                "message": "Connected to the complaint generator chat surface.",
                "explanation": {"summary": "Keep the browser contract alive during smoke navigation."},
            }
        )
        try:
            while True:
                payload = await websocket.receive_json()
                await websocket.send_json(payload)
        except WebSocketDisconnect:
            return

    return app


def _dismiss_dialog(dialog) -> None:
    dialog.dismiss()


def test_unified_navigation_connects_primary_pages(site_app: FastAPI):
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with _serve_app(site_app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.on("dialog", _dismiss_dialog)

            page.goto(f"{base_url}/")
            expect_texts = [
                ("Secure Intake", "/home", "Create Account"),
                ("Workspace", "/workspace", "Unified Complaint Workspace"),
                ("Review", "/claim-support-review", "Review whether the complaint is actually supported."),
                ("Builder", "/document", "Formal Complaint Builder"),
                ("Editor", "/mlwysiwyg", "Complaint Editor Workshop"),
                ("Trace", "/document/optimization-trace", "Optimization Trace Viewer"),
                ("Landing", "/", "Lex Publicus Complaint Generator"),
            ]

            for label, suffix, expected_text in expect_texts:
                href = page.get_by_role("link", name=label, exact=True).first.get_attribute("href")
                assert href
                parsed_href = urlparse(href)
                assert parsed_href.path == suffix
                destination = href if href.startswith(("http://", "https://")) else f"{base_url}{href}"
                page.goto(destination)
                page.wait_for_load_state("networkidle")
                assert expected_text in page.locator("body").inner_text()

            browser.close()


def test_document_generation_links_back_to_claim_review(site_app: FastAPI):
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with _serve_app(site_app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.on("dialog", _dismiss_dialog)

            page.goto(f"{base_url}/document")
            page.locator("#caseNumber").fill("26-cv-00001")
            page.locator("#plaintiffs").fill("Jane Doe")
            page.locator("#defendants").fill("Acme Corporation")
            page.locator("#generateButton").click()

            page.wait_for_function("() => document.getElementById('artifactMetric').textContent.includes('ready')")
            page.wait_for_function(
                '() => Array.from(document.querySelectorAll(\'a[href*="/claim-support-review?"]\')).length > 0'
            )

            review_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href*="/claim-support-review?"]'))
                    .map((node) => ({ text: (node.textContent || '').trim(), href: node.getAttribute('href') || '' }))"""
            )

            matching_links = [link for link in review_links if "claim_type=retaliation" in link["href"]]
            assert matching_links, review_links

            page.locator('a[href*="claim_type=retaliation"]').first.click()
            page.wait_for_url("**/claim-support-review?**claim_type=retaliation**")
            page.locator("#review-button").click()
            page.wait_for_function("() => document.getElementById('element-list').textContent.includes('Protected activity')")

            browser.close()


def test_optimization_trace_loads_review_handoff_links(site_app: FastAPI):
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with _serve_app(site_app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.on("dialog", _dismiss_dialog)

            page.goto(f"{base_url}/document/optimization-trace")
            page.locator("#traceCidInput").fill(TRACE_CID)
            page.locator("#loadTraceButton").click()

            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('#traceEvidenceQuestionTargets a.inline-link')).length >= 1"
            )

            trace_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#traceEvidenceQuestionTargets a.inline-link'))
                    .map((node) => ({ text: (node.textContent || '').trim(), href: node.getAttribute('href') || '' }))"""
            )

            matching_links = [link for link in trace_links if "section=proof_leads" in link["href"]]
            assert matching_links, trace_links

            page.locator('#traceEvidenceQuestionTargets a.inline-link[href*="section=proof_leads"]').first.click()
            page.wait_for_url("**/claim-support-review?**section=proof_leads**")
            assert "proof_leads" in page.url

            browser.close()


def test_workspace_page_uses_browser_mcp_sdk(site_app: FastAPI):
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with _serve_app(site_app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.on("dialog", _dismiss_dialog)

            page.goto(f"{base_url}/workspace?user_id=site-sdk-user")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').textContent.includes('site-sdk-user')"
            )

            assert page.evaluate(
                "() => typeof window.ComplaintMcpSdk?.ComplaintMcpClient === 'function'"
            )
            assert page.evaluate(
                "() => typeof window.ComplaintMcpSdk.ComplaintMcpClient.prototype.exportComplaintMarkdown === 'function'"
            )
            assert page.evaluate(
                "() => typeof window.ComplaintMcpSdk.ComplaintMcpClient.prototype.exportComplaintPdf === 'function'"
            )
            assert page.evaluate(
                "() => typeof window.ComplaintMcpSdk.ComplaintMcpClient.prototype.importGmailEvidence === 'function'"
            )
            assert page.evaluate(
                "() => typeof window.ComplaintMcpSdk.ComplaintMcpClient.prototype.analyzeComplaintOutput === 'function'"
            )
            assert page.evaluate(
                "() => typeof window.ComplaintMcpSdk.ComplaintMcpClient.prototype.getToolingContract === 'function'"
            )
            assert page.evaluate(
                "() => typeof window.ComplaintMcpSdk.ComplaintMcpClient.prototype.updateClaimType === 'function'"
            )

            page.locator('#intake-party_name').fill('Jane Doe')
            page.locator('#intake-opposing_party').fill('Acme Corporation')
            page.locator('#intake-protected_activity').fill('Reported discrimination to HR')
            page.locator('#intake-adverse_action').fill('Termination two days later')
            page.locator('#intake-timeline').fill('Report on March 8, termination on March 10')
            page.locator('#intake-harm').fill('Lost wages and emotional distress')
            page.locator('#save-intake-button').click()
            page.wait_for_function(
                "() => document.getElementById('workspace-status').textContent.includes('Intake answers saved.')"
            )

            page.get_by_role('button', name='Evidence', exact=True).click()
            page.locator('#evidence-title').fill('HR complaint email')
            page.locator('#evidence-content').fill('Email confirming the protected report and management response.')
            page.locator('#save-evidence-button').click()
            page.wait_for_function(
                "() => document.getElementById('workspace-status').textContent.includes('Evidence saved')"
            )

            page.get_by_role('button', name='Draft', exact=True).click()
            page.locator('#draft-mode').select_option('template')
            page.locator('#generate-draft-button').click()
            page.wait_for_function(
                "() => document.getElementById('workspace-status').textContent.includes('Complaint draft generated')"
            )
            page.wait_for_function(
                "() => { const text = document.getElementById('draft-preview').textContent || ''; return text.includes('COMPLAINT FOR RETALIATION') && text.includes('Jane Doe') && text.includes('Acme Corporation') && text.includes('PRAYER FOR RELIEF'); }"
            )

            tool_names = page.locator('#tool-list .item strong')
            tool_count = tool_names.count()
            assert tool_count >= 3
            assert any(
                'complaint.generate_complaint' in tool_names.nth(index).inner_text()
                for index in range(tool_count)
            )

            browser.close()


def test_dashboard_page_reacts_to_shared_workspace_sync_events(site_app: FastAPI):
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with _serve_app(site_app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.on("dialog", _dismiss_dialog)

            page.goto(f"{base_url}/dashboards?user_id=dashboard-sync-user")
            page.wait_for_function(
                "() => typeof window.ComplaintMcpSdk?.SYNC_EVENT_NAME === 'string'"
            )

            page.evaluate(
                """() => {
                    const detail = {
                        event_type: 'workspace.updated',
                        user_id: 'dashboard-sync-user',
                        payload: {
                            session: {
                                user_id: 'dashboard-sync-user',
                                claim_type: 'retaliation',
                                case_synopsis: 'Protected activity preceded the adverse action.',
                                intake_answers: {
                                    party_name: 'Jane Doe',
                                    opposing_party: 'Acme Corporation',
                                },
                                evidence: {
                                    testimony: [{ title: 'Timeline note' }],
                                    documents: [{ title: 'Termination notice' }],
                                },
                                draft: {
                                    title: 'Draft complaint',
                                },
                            },
                            review: {
                                overview: {
                                    missing_elements: 0,
                                },
                            },
                            complaint_readiness: {
                                recommended_route: '/workspace',
                            },
                        },
                    };
                    window.dispatchEvent(new CustomEvent(window.ComplaintMcpSdk.SYNC_EVENT_NAME, { detail }));
                }"""
            )

            page.wait_for_function(
                "() => document.getElementById('dashboard-workspace-session-chip').textContent.includes('dashboard-sync-user')"
            )
            assert page.locator("#dashboard-workspace-answered").text_content() == "2"
            assert page.locator("#dashboard-workspace-evidence").text_content() == "2"
            assert page.locator("#dashboard-workspace-draft").text_content() == "Yes"
            assert "Refine draft" in (page.locator("#dashboard-heads-up-action").text_content() or "")

            page.evaluate(
                """() => {
                    const detail = {
                        event_type: 'workspace.reset',
                        user_id: 'dashboard-sync-user',
                        payload: {
                            session: {
                                user_id: 'dashboard-sync-user',
                                claim_type: 'retaliation',
                                case_synopsis: '',
                                intake_answers: {},
                                evidence: {
                                    testimony: [],
                                    documents: [],
                                },
                            },
                            review: {
                                overview: {
                                    missing_elements: 0,
                                },
                            },
                            complaint_readiness: {
                                recommended_route: '/workspace',
                            },
                        },
                    };
                    window.dispatchEvent(new CustomEvent(window.ComplaintMcpSdk.SYNC_EVENT_NAME, { detail }));
                }"""
            )

            page.wait_for_function(
                "() => document.getElementById('dashboard-workspace-evidence').textContent.trim() === '0'"
            )
            assert page.locator("#dashboard-workspace-draft").text_content() == "No"
            assert "Continue intake" in (page.locator("#dashboard-heads-up-action").text_content() or "")

            browser.close()


def test_real_workspace_browser_flow_generates_formal_complaint_downloads_and_optimizer_feedback(site_app: FastAPI, tmp_path: Path):
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with _serve_app(site_app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.on("dialog", _dismiss_dialog)

            page.goto(f"{base_url}/workspace?user_id=site-full-flow-user")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').textContent.includes('site-full-flow-user')"
            )

            page.locator('#intake-party_name').fill('Jordan Example')
            page.locator('#intake-opposing_party').fill('Acme Corporation')
            page.locator('#intake-protected_activity').fill('Reported discrimination to HR')
            page.locator('#intake-adverse_action').fill('Was terminated two days later')
            page.locator('#intake-timeline').fill('Report on March 8, termination on March 10')
            page.locator('#intake-harm').fill('Lost wages and emotional distress')
            page.locator('#intake-court_header').fill('FOR THE NORTHERN DISTRICT OF CALIFORNIA')
            page.locator('#save-intake-button').click()
            page.wait_for_function(
                "() => document.getElementById('workspace-status').textContent.includes('Intake answers saved.')"
            )

            page.locator('#case-synopsis').fill(
                'Jordan Example alleges retaliation after reporting discrimination to HR, and the next step is to tie the evidence and chronology into a filing-ready complaint.'
            )
            page.locator('#save-synopsis-button').click()
            page.wait_for_function(
                "() => document.getElementById('workspace-status').textContent.includes('Shared case synopsis saved')"
            )

            page.locator('#handoff-chat-button').click()
            page.wait_for_url("**/chat?**")
            page.wait_for_function(
                "() => document.getElementById('chat-context-prefill').textContent.includes('Prepared mediator prompt')"
            )
            page.locator('#chat-form input').fill('I reported discrimination to HR, and my manager terminated me two days later.')
            page.get_by_role('button', name='Send').click()
            page.wait_for_function(
                "() => document.querySelector('#chat-form input').value === ''"
            )

            page.goto(f"{base_url}/workspace?user_id=site-full-flow-user")
            page.wait_for_function(
                "() => document.getElementById('workspace-status').textContent.includes('site-full-flow-user')"
            )
            page.wait_for_function(
                "() => document.getElementById('continuity-gating-summary').textContent.includes('same DID-backed complaint session') || document.getElementById('continuity-gating-summary').textContent.includes('same DID-backed') || document.getElementById('continuity-gating-summary').textContent.includes('shared complaint record')"
            )
            page.wait_for_function(
                "() => document.getElementById('continuity-phase-note').textContent.length > 20"
            )
            page.wait_for_function(
                "() => document.getElementById('workspace-nav-builder').getAttribute('aria-disabled') !== null"
            )
            page.wait_for_function(
                "() => document.getElementById('session-sync-summary').textContent.length > 40 && document.getElementById('session-sync-did-chip').textContent.includes('did:')"
            )
            page.wait_for_function(
                "() => document.getElementById('session-tool-activity-summary').textContent.includes('complaint.start_session') || document.getElementById('session-tool-activity-summary').textContent.includes('Latest MCP activity')"
            )

            page.get_by_role('button', name='Evidence', exact=True).click()
            page.locator('#evidence-kind').select_option('testimony')
            page.locator('#evidence-claim-element').select_option('causation')
            page.locator('#evidence-title').fill('Mediator testimony summary')
            page.locator('#evidence-source').fill('Chat mediator')
            page.locator('#evidence-content').fill('The termination followed immediately after the protected complaint to HR.')
            page.locator('#save-evidence-button').click()
            page.wait_for_function(
                "() => document.getElementById('evidence-list').textContent.includes('Mediator testimony summary')"
            )

            page.locator('#evidence-kind').select_option('document')
            page.locator('#evidence-claim-element').select_option('causation')
            page.locator('#evidence-title').fill('Termination email')
            page.locator('#evidence-source').fill('Email archive')
            page.locator('#evidence-content').fill('The archived email shows the termination immediately after the HR complaint.')
            page.locator('#evidence-attachment').set_input_files(
                files=[{"name": "termination-email.txt", "mimeType": "text/plain", "buffer": b"Termination email evidence"}]
            )
            page.locator('#save-evidence-button').click()
            page.wait_for_function(
                "() => document.getElementById('evidence-list').textContent.includes('termination-email.txt')"
            )

            page.get_by_role('button', name='Review', exact=True).click()
            page.wait_for_function(
                "() => document.getElementById('support-grid').textContent.includes('Protected activity')"
            )
            assert 'Jordan Example alleges retaliation' in page.locator('#review-synopsis-preview').inner_text()

            page.get_by_role('button', name='Draft', exact=True).click()
            page.locator('#draft-mode').select_option('llm_router')
            page.locator('#requested-relief').fill('Back pay\nInjunctive relief')
            page.locator('#generate-draft-button').click()
            page.wait_for_function(
                "() => document.getElementById('workspace-status').textContent.includes('llm_router formal complaint path')"
            )
            page.wait_for_function(
                "() => { const text = document.getElementById('draft-preview').textContent || ''; return text.includes('COMPLAINT FOR RETALIATION') && text.includes('COUNT I - RETALIATION') && text.includes('SIGNATURE BLOCK'); }"
            )
            page.wait_for_function(
                "() => !document.body.innerText.includes('No draft generated yet.')"
            )
            page.wait_for_function(
                "() => document.getElementById('handoff-builder-button').getAttribute('aria-disabled') === 'false'"
            )
            page.wait_for_function(
                "() => document.getElementById('workspace-nav-builder').getAttribute('aria-disabled') === 'false'"
            )

            page.locator('#export-packet-button').click()
            page.wait_for_function(
                "() => document.getElementById('packet-preview').textContent.includes('Jordan Example v. Acme Corporation Retaliation Complaint')"
            )

            with page.expect_download() as markdown_download_info:
                page.locator('#download-packet-markdown-button').click()
            markdown_download = markdown_download_info.value
            markdown_path = tmp_path / markdown_download.suggested_filename
            markdown_download.save_as(str(markdown_path))
            markdown_text = markdown_path.read_text(encoding='utf-8')
            assert 'IN THE UNITED STATES DISTRICT COURT' in markdown_text
            assert 'FOR THE NORTHERN DISTRICT OF CALIFORNIA' in markdown_text
            assert 'COMPLAINT FOR RETALIATION' in markdown_text
            assert 'PRAYER FOR RELIEF' in markdown_text
            assert 'SIGNATURE BLOCK' in markdown_text

            with page.expect_download() as pdf_download_info:
                page.locator('#download-packet-pdf-button').click()
            pdf_download = pdf_download_info.value
            pdf_path = tmp_path / pdf_download.suggested_filename
            pdf_download.save_as(str(pdf_path))
            pdf_bytes = pdf_path.read_bytes()
            assert pdf_bytes.startswith(b'%PDF-1.4')

            page.get_by_role('button', name='CLI + MCP', exact=True).click()
            page.wait_for_function(
                "() => document.getElementById('integrations-operations-preview').textContent.includes('Recommended tool workflow')"
            )
            page.wait_for_function(
                "() => document.getElementById('tool-list-summary').textContent.includes('MCP tools')"
            )
            page.wait_for_function(
                "() => document.getElementById('tool-list-phase-chips').textContent.includes('Draft + export')"
            )
            page.wait_for_function(
                "() => document.getElementById('tooling-parity-preview').textContent.includes('Browser SDK parity summary')"
            )
            page.wait_for_function(
                "() => document.getElementById('tooling-parity-preview').textContent.includes('parity verified')"
            )
            page.wait_for_function(
                "() => document.getElementById('operations-tool-readiness-button').getAttribute('aria-disabled') === 'false'"
            )
            page.wait_for_function(
                "() => document.getElementById('operations-ui-audit-tool-button').getAttribute('aria-disabled') === 'false'"
            )
            page.locator('#analyze-complaint-output-button').click()
            page.wait_for_function(
                "() => document.getElementById('complaint-output-analysis-preview').textContent.includes('\"filing_shape_score\": 96')"
            )
            page.wait_for_function(
                "() => document.getElementById('complaint-output-analysis-preview').textContent.includes('formal_complaint_reviewer')"
            )

            page.locator('#review-generated-exports-button').click()
            page.wait_for_function(
                "() => document.getElementById('workspace-status').textContent.includes('export critic')"
            )
            page.get_by_role('button', name='UX Audit', exact=True).click()
            page.wait_for_function(
                "() => document.getElementById('ux-review-repair-brief').textContent.includes('Recommended UI surfaces')"
            )
            page.locator('#run-ux-review-button').click()
            page.wait_for_function(
                "() => document.getElementById('ux-review-summary').textContent.includes('Multimodal actor/critic review complete')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-actor-critic').textContent.includes('Actor journey')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-stage-findings').textContent.includes('Complaint-output suggestion carried into router review')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-artifacts').textContent.includes('Screenshot critic: workspace-draft')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-repair-brief').textContent.includes('Screenshot-driven optimization target')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-metadata').textContent.includes('optimization targets: 1')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-repair-brief').textContent.includes('Carry-forward assessment')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-artifacts').textContent.includes('Carry-forward assessment')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-metadata').textContent.includes('unresolved prior findings: 1')"
            )

            page.reload()
            page.get_by_role('button', name='UX Audit', exact=True).click()
            page.wait_for_function(
                "() => document.getElementById('ux-review-summary').textContent.includes('Multimodal actor/critic review complete')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-artifacts').textContent.includes('Screenshot critic: workspace-draft')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-repair-brief').textContent.includes('Screenshot-driven optimization target')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-metadata').textContent.includes('optimization targets: 1')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-repair-brief').textContent.includes('Carry-forward assessment')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-artifacts').textContent.includes('Carry-forward assessment')"
            )
            page.wait_for_function(
                "() => document.getElementById('ux-review-metadata').textContent.includes('unresolved prior findings: 1')"
            )

            page.locator('#run-browser-audit-button').click()
            page.wait_for_function(
                "() => document.getElementById('ux-review-summary').textContent.includes('6 screenshot artifacts')"
            )

            browser.close()
