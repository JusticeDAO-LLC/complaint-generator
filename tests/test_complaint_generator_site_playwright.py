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
    import applications.document_api as document_api_module

    mediator = _build_dashboard_mediator()
    artifact_dir = Path(tempfile.mkdtemp(prefix="complaint-site-playwright-"))
    mediator.build_formal_complaint_document_package = Mock(return_value=_build_document_package(artifact_dir))

    trace_bytes = json.dumps(TRACE_PAYLOAD).encode("utf-8")

    def fake_retrieve_bytes(cid: str) -> dict:
        if cid == TRACE_CID:
            return {"status": "available", "data": trace_bytes, "size": len(trace_bytes)}
        return {"status": "missing", "error": "unknown cid"}

    monkeypatch.setattr(document_api_module, "retrieve_bytes", fake_retrieve_bytes)

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
                "() => typeof window.ComplaintMcpSdk.ComplaintMcpClient.prototype.analyzeComplaintOutput === 'function'"
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