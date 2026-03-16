import json
import os
import socket
import tempfile
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import duckdb
import pytest
import requests
import uvicorn
from fastapi import FastAPI

from applications.review_api import attach_claim_support_review_routes
from applications.document_ui import attach_document_ui_routes
from applications.review_ui import attach_claim_support_review_ui_routes, attach_review_health_routes


pytestmark = [pytest.mark.no_auto_network, pytest.mark.browser]

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False


def _build_browser_smoke_app(mediator: Mock) -> FastAPI:
    app = FastAPI(title="Claim Support Review Smoke")
    attach_claim_support_review_routes(app, mediator)
    attach_claim_support_review_ui_routes(app)
    attach_review_health_routes(app, "claim-support-review-smoke")
    return app


def _build_document_browser_smoke_app() -> FastAPI:
    app = FastAPI(title="Document Builder Smoke")
    attach_document_ui_routes(app)
    attach_review_health_routes(app, "document-builder-smoke")
    return app


def _build_document_review_browser_smoke_app(mediator: Mock) -> FastAPI:
    app = FastAPI(title="Document Review Flow Smoke")
    attach_document_ui_routes(app)
    attach_claim_support_review_routes(app, mediator)
    attach_claim_support_review_ui_routes(app)
    attach_review_health_routes(app, "document-review-flow-smoke")
    return app


def _build_hook_backed_browser_mediator(db_path: str):
    try:
        from mediator.claim_support_hooks import ClaimSupportHook
    except ImportError as exc:
        pytest.skip(f"ClaimSupportHook requires dependencies: {exc}")

    mediator = Mock()
    mediator.state = SimpleNamespace(username="browser-smoke-text-link", hashed_username=None)
    mediator.log = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "iteration_count": 2,
        "intake_readiness": {
            "score": 0.41,
            "ready_to_advance": False,
            "remaining_gap_count": 2,
            "contradiction_count": 0,
            "blockers": ["collect_missing_support"],
        },
        "candidate_claims": [
            {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.87},
        ],
        "intake_sections": {
            "proof_leads": {"status": "partial", "missing_items": ["documents"]},
        },
        "canonical_fact_summary": {
            "count": 1,
            "facts": [{"fact_id": "fact_001", "text": "Protected activity timeline recorded."}],
        },
        "proof_lead_summary": {
            "count": 1,
            "proof_leads": [{"lead_id": "lead_001", "description": "Archived HR complaint email"}],
        },
        "intake_evidence_alignment_summary": {
            "aligned_element_count": 1,
            "claims": {
                "retaliation": {
                    "shared_elements": [
                        {"element_id": "retaliation:1", "support_status": "supported"},
                    ],
                    "intake_only_element_ids": ["retaliation:3"],
                    "evidence_only_element_ids": ["retaliation:2"],
                }
            },
        },
        "alignment_evidence_tasks": [
            {
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:3",
                "claim_element_label": "Causal connection",
                "support_status": "missing",
                "action": "fill_evidence_gaps",
                "blocking": True,
            }
        ],
        "alignment_task_updates": [
            {
                "task_id": "retaliation:retaliation:3:fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:3",
                "action": "fill_evidence_gaps",
                "previous_support_status": "",
                "current_support_status": "missing",
                "previous_missing_fact_bundle": [],
                "current_missing_fact_bundle": ["Timeline evidence"],
                "resolution_status": "still_open",
                "status": "active",
                "evidence_artifact_id": "artifact-open",
            }
        ],
        "alignment_task_update_history": [
            {
                "task_id": "retaliation:retaliation:3:fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:3",
                "action": "fill_evidence_gaps",
                "previous_support_status": "",
                "current_support_status": "missing",
                "previous_missing_fact_bundle": [],
                "current_missing_fact_bundle": ["Timeline evidence"],
                "resolution_status": "still_open",
                "status": "active",
                "evidence_artifact_id": "artifact-open",
                "evidence_sequence": 1,
            },
            {
                "task_id": "retaliation:retaliation:3:resolve_support_conflicts",
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:3",
                "action": "resolve_support_conflicts",
                "previous_support_status": "missing",
                "current_support_status": "contradicted",
                "previous_missing_fact_bundle": ["Timeline evidence"],
                "current_missing_fact_bundle": ["Timeline evidence"],
                "resolution_status": "needs_manual_review",
                "status": "active",
                "evidence_artifact_id": "artifact-conflict",
                "evidence_sequence": 2,
            }
        ],
        "question_candidate_summary": {},
        "claim_support_packet_summary": {},
    }

    hook = ClaimSupportHook(mediator, db_path=db_path)
    hook.register_claim_requirements(
        "browser-smoke-text-link",
        {"retaliation": ["Protected activity", "Adverse action", "Causal connection"]},
    )

    def _save_testimony_record(**kwargs):
        return hook.save_testimony_record(**kwargs)

    def _get_testimony_records(user_id=None, claim_type=None, limit=100, **kwargs):
        resolved_user_id = user_id or kwargs.get("user_id") or "browser-smoke-text-link"
        resolved_claim_type = claim_type or kwargs.get("claim_type")
        resolved_limit = limit if limit is not None else kwargs.get("limit", 100)
        return hook.get_claim_testimony_records(
            resolved_user_id,
            resolved_claim_type,
            limit=resolved_limit,
        )

    def _build_testimony_links(records):
        return [
            {
                "claim_type": "retaliation",
                "claim_element_id": record["claim_element_id"],
                "claim_element_text": record["claim_element_text"],
                "support_kind": "testimony",
                "support_ref": record["testimony_id"],
                "support_label": f"Testimony for {record['claim_element_text']}",
                "source_table": "claim_testimony",
                "support_strength": record["source_confidence"],
                "timestamp": record["timestamp"],
                "testimony_record_id": record["record_id"],
                "graph_summary": {
                    "entity_count": 0,
                    "relationship_count": 0,
                },
                "graph_trace": {
                    "source_table": "claim_testimony",
                    "summary": {
                        "status": "not_available",
                    },
                    "snapshot": {},
                    "metadata": {},
                    "lineage": {},
                },
            }
            for record in records
        ]

    def _get_claim_coverage_matrix(*, claim_type=None, user_id=None, required_support_kinds=None):
        testimony_payload = _get_testimony_records(
            user_id=user_id,
            claim_type=claim_type or "retaliation",
            limit=25,
        )
        testimony_records = testimony_payload["claims"]["retaliation"]
        testimony_links = _build_testimony_links(testimony_records)
        required_kinds = required_support_kinds or ["evidence", "authority"]
        return {
            "claims": {
                "retaliation": {
                    "claim_type": "retaliation",
                    "required_support_kinds": required_kinds,
                    "total_elements": 3,
                    "status_counts": {
                        "covered": 0,
                        "partially_supported": 1,
                        "missing": 2,
                    },
                    "total_links": len(testimony_links),
                    "total_facts": len(testimony_links),
                    "support_by_kind": {"testimony": len(testimony_links)},
                    "support_trace_summary": {},
                    "support_packet_summary": {},
                    "authority_treatment_summary": {},
                    "authority_rule_candidate_summary": {},
                    "elements": [
                        {
                            "element_id": "retaliation:1",
                            "element_text": "Protected activity",
                            "status": "partially_supported",
                            "total_links": len(testimony_links),
                            "fact_count": len(testimony_links),
                            "support_by_kind": {"testimony": len(testimony_links)},
                            "missing_support_kinds": list(required_kinds),
                            "links": testimony_links,
                            "links_by_kind": {"testimony": testimony_links},
                            "support_packets": [],
                            "support_packet_summary": {},
                            "authority_treatment_summary": {},
                            "proof_gap_count": len(required_kinds),
                            "proof_gaps": [
                                {
                                    "gap_type": "missing_support_kind",
                                    "support_kind": kind,
                                    "message": f"Missing required {kind} support.",
                                }
                                for kind in required_kinds
                            ],
                            "support_fact_packets": [],
                            "support_fact_status_counts": {},
                            "document_fact_packets": [],
                            "document_fact_status_counts": {},
                            "contradiction_pairs": [],
                            "contradiction_pair_count": 0,
                        },
                        {
                            "element_id": "retaliation:2",
                            "element_text": "Adverse action",
                            "status": "missing",
                            "total_links": 0,
                            "fact_count": 0,
                            "support_by_kind": {},
                            "missing_support_kinds": list(required_kinds),
                            "links": [],
                            "links_by_kind": {},
                            "support_packets": [],
                            "support_packet_summary": {},
                            "authority_treatment_summary": {},
                            "proof_gap_count": len(required_kinds),
                            "proof_gaps": [
                                {
                                    "gap_type": "missing_support_kind",
                                    "support_kind": kind,
                                    "message": f"Missing required {kind} support.",
                                }
                                for kind in required_kinds
                            ],
                            "support_fact_packets": [],
                            "support_fact_status_counts": {},
                            "document_fact_packets": [],
                            "document_fact_status_counts": {},
                            "contradiction_pairs": [],
                            "contradiction_pair_count": 0,
                        },
                        {
                            "element_id": "retaliation:3",
                            "element_text": "Causal connection",
                            "status": "missing",
                            "total_links": 0,
                            "fact_count": 0,
                            "support_by_kind": {},
                            "missing_support_kinds": list(required_kinds),
                            "links": [],
                            "links_by_kind": {},
                            "support_packets": [],
                            "support_packet_summary": {},
                            "authority_treatment_summary": {},
                            "proof_gap_count": len(required_kinds),
                            "proof_gaps": [
                                {
                                    "gap_type": "missing_support_kind",
                                    "support_kind": kind,
                                    "message": f"Missing required {kind} support.",
                                }
                                for kind in required_kinds
                            ],
                            "support_fact_packets": [],
                            "support_fact_status_counts": {},
                            "document_fact_packets": [],
                            "document_fact_status_counts": {},
                            "contradiction_pairs": [],
                            "contradiction_pair_count": 0,
                        },
                    ],
                }
            }
        }

    mediator.save_claim_testimony_record.side_effect = _save_testimony_record
    mediator.get_claim_testimony_records.side_effect = _get_testimony_records
    mediator.get_claim_coverage_matrix.side_effect = _get_claim_coverage_matrix
    mediator.get_claim_overview.side_effect = lambda **kwargs: {
        "claims": {
            "retaliation": {
                "covered": [],
                "partially_supported": [{"element_text": "Protected activity"}],
                "missing": [
                    {"element_text": "Adverse action"},
                    {"element_text": "Causal connection"},
                ],
            }
        }
    }
    mediator.get_claim_support_diagnostic_snapshots.return_value = {"claims": {}}
    mediator.get_claim_support_gaps.side_effect = lambda **kwargs: {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "unresolved_count": 3,
                "unresolved_elements": [
                    {
                        "element_text": "Protected activity",
                        "recommended_action": "collect_missing_support_kind",
                    },
                    {
                        "element_text": "Adverse action",
                        "recommended_action": "collect_initial_support",
                    },
                    {
                        "element_text": "Causal connection",
                        "recommended_action": "collect_initial_support",
                    },
                ],
            }
        }
    }
    mediator.get_claim_contradiction_candidates.return_value = {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "candidate_count": 0,
                "candidates": [],
            }
        }
    }
    mediator.get_claim_support_validation.side_effect = lambda **kwargs: {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "required_support_kinds": ["evidence", "authority"],
                "validation_status": "incomplete",
                "validation_status_counts": {
                    "supported": 0,
                    "incomplete": 1,
                    "missing": 2,
                    "contradicted": 0,
                },
                "proof_gap_count": 6,
                "elements_requiring_follow_up": [
                    "Protected activity",
                    "Adverse action",
                    "Causal connection",
                ],
                "elements": [],
            }
        }
    }
    mediator.get_claim_support_facts.side_effect = lambda **kwargs: []
    mediator.get_recent_claim_follow_up_execution.return_value = {
        "claims": {"retaliation": []}
    }
    mediator.get_claim_follow_up_plan.side_effect = lambda **kwargs: {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "task_count": 3,
                "tasks": [],
            }
        }
    }
    mediator.get_user_evidence.return_value = []
    mediator.summarize_claim_support.return_value = {"claims": {"retaliation": {}}}

    return mediator, hook


def _build_real_browser_upload_mediator(
    *,
    evidence_db_path: str,
    claim_support_db_path: str,
    legal_authority_db_path: str,
):
    try:
        from mediator import Mediator
    except ImportError as exc:
        pytest.skip(f"Mediator requires dependencies: {exc}")

    mock_backend = Mock()
    mock_backend.id = "browser-upload-backend"

    mediator = Mediator(
        backends=[mock_backend],
        evidence_db_path=evidence_db_path,
        claim_support_db_path=claim_support_db_path,
        legal_authority_db_path=legal_authority_db_path,
    )
    mediator.state.username = "browser-upload-user"
    mediator.claim_support.register_claim_requirements(
        "browser-upload-user",
        {"retaliation": ["Protected activity", "Adverse action", "Causal connection"]},
    )
    mediator.get_three_phase_status = Mock(
        return_value={
            "current_phase": "intake",
            "iteration_count": 1,
            "intake_readiness": {
                "score": 0.52,
                "ready_to_advance": False,
                "remaining_gap_count": 2,
                "contradiction_count": 0,
                "blockers": ["collect_missing_support"],
            },
            "candidate_claims": [
                {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.89},
            ],
            "intake_sections": {
                "proof_leads": {"status": "partial", "missing_items": ["documents"]},
            },
            "canonical_fact_summary": {
                "count": 1,
                "facts": [{"fact_id": "fact_001", "text": "Protected activity already recorded."}],
            },
            "proof_lead_summary": {
                "count": 1,
                "proof_leads": [{"lead_id": "lead_001", "description": "Upload documentary evidence"}],
            },
            "question_candidate_summary": {},
            "claim_support_packet_summary": {},
        }
    )
    return mediator


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


def test_claim_support_review_dashboard_smoke_shows_proactively_repaired_legacy_testimony_links():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="The HR complaint email does not exist.",
            firsthand_status="firsthand",
            source_confidence=0.92,
        )

        conn = duckdb.connect(db_path)
        conn.execute(
            """
            INSERT INTO claim_testimony (
                testimony_id,
                user_id,
                claim_type,
                claim_element_id,
                claim_element_text,
                raw_narrative,
                firsthand_status,
                source_confidence,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "testimony:retaliation:legacy-ui",
                "browser-smoke-text-link",
                "retaliation",
                None,
                "Protected activity",
                "The HR complaint email does not exist.",
                "firsthand",
                0.92,
                json.dumps({"source": "legacy-ui"}),
            ],
        )
        conn.close()

        result = hook.backfill_claim_testimony_links("browser-smoke-text-link", "retaliation")
        assert result["updated_count"] == 1

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.click("#review-button")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                summary_text = page.locator("#testimony-summary-chips").inner_text()
                testimony_text = page.locator("#testimony-list").inner_text()
                element_text = page.locator("#element-list").inner_text()

                assert "Records: 2" in summary_text
                assert "Linked elements: 1" in summary_text
                assert "firsthand: 2" in summary_text
                assert page.locator("#testimony-list .history-card").count() == 2
                assert testimony_text.count("Protected activity") == 2
                assert testimony_text.count("The HR complaint email does not exist.") == 2
                assert "Protected activity" in element_text
                assert "facts=2 links=2" in element_text
                assert "PARTIALLY_SUPPORTED" in element_text

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_preserves_support_kind_in_canonical_url():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for support-kind URL smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?"
                    "claim_type=retaliation&"
                    "user_id=browser-smoke-text-link&"
                    "section=claims_for_relief&"
                    "follow_up_support_kind=authority"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "follow_up_support_kind=authority" in page.url
                assert page.locator("#support-kind").input_value() == "authority"
                assert "Claims For Relief" in page.locator("#prefill-context-line").inner_text()
                assert "Focused lane: Authority." in page.locator("#prefill-context-line").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_document_builder_smoke_renders_question_review_links_with_section_aware_support_kind():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"sections": {}, "claims": [], "warnings": []},
        "filing_checklist": [],
        "review_links": {},
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 0,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {"blocking": 1, "non_blocking": 1},
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
                "alignment_task_update_history": [
                    {
                        "task_id": "retaliation:proof_leads:resolve_support_conflicts",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:3",
                        "claim_element_label": "Proof Leads",
                        "action": "resolve_support_conflicts",
                        "current_support_status": "contradicted",
                        "resolution_status": "needs_manual_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-conflict",
                        "evidence_sequence": 2,
                    }
                ],
            },
            "packet_projection": {
                "title": "Complaint Packet",
                "section_presence": {"factual_allegations": True},
                "has_affidavit": False,
                "has_certificate_of_service": False,
            },
            "section_history": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "overall_score": 0.7,
                }
            ],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    app = _build_document_browser_smoke_app()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.goto(f"{base_url}/document")
            page.evaluate("payload => window.renderPreview(payload)", payload)
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('#previewRoot a.inline-link')).some((node) => node.textContent.includes('Question Review'))"
            )

            question_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#previewRoot a.inline-link'))
                    .filter((node) => node.textContent.includes('Question Review'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )

            assert {
                "text": "Open Proof Leads Question Review (1)",
                "href": "/claim-support-review?section=proof_leads&follow_up_support_kind=evidence&alignment_task_update_filter=active&alignment_task_update_sort=newest_first",
            } in question_links
            assert {
                "text": "Open Claims For Relief Question Review (1)",
                "href": "/claim-support-review?section=claims_for_relief&follow_up_support_kind=authority&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first",
            } in question_links

            section_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#previewRoot a.inline-link'))
                    .filter((node) => node.textContent.includes('Intake Section Review'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )
            preview_text = page.locator("#previewRoot").inner_text()

            assert {
                "text": "Open Proof Leads Intake Section Review",
                "href": "/claim-support-review?section=proof_leads&follow_up_support_kind=evidence&alignment_task_update_filter=active&alignment_task_update_sort=newest_first",
            } in section_links
            assert {
                "text": "Open Claims For Relief Intake Section Review",
                "href": "/claim-support-review?section=claims_for_relief&follow_up_support_kind=authority&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first",
            } in section_links
            assert "Manual Review Blockers" in preview_text
            assert "Manual review blockers: 1" in preview_text
            assert "Claims impacted: 1" in preview_text
            assert "Retaliation: Proof Leads | action Resolve Support Conflicts | artifact artifact-conflict" in preview_text

            browser.close()


def test_claim_support_review_dashboard_smoke_renders_intake_evidence_alignment():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for intake-evidence alignment smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                alignment_summary = page.locator("#intake-evidence-alignment-summary-list").inner_text()
                alignment_tasks = page.locator("#alignment-evidence-task-list").inner_text()
                manual_review_summary = page.locator("#alignment-task-manual-review-summary").inner_text()
                manual_review_list = page.locator("#alignment-task-manual-review-list").inner_text()
                alignment_updates = page.locator("#alignment-task-update-list").inner_text()
                alignment_update_filter_summary = page.locator("#alignment-task-update-filter-summary").inner_text()

                assert "Cross-phase element alignment for retaliation" in alignment_summary
                assert "aligned retaliation:1: supported" in alignment_summary
                assert "intake only: retaliation:3" in alignment_summary
                assert "evidence only: retaliation:2" in alignment_summary
                assert "Alignment task for retaliation" in alignment_tasks
                assert "evidence action fill_evidence_gaps" in alignment_tasks
                assert "element: retaliation:3" in alignment_tasks
                assert "label: Causal connection" in alignment_tasks
                assert "blocking: yes" in alignment_tasks
                assert "manual review blockers: 1" in manual_review_summary
                assert "claims impacted: 1" in manual_review_summary
                assert "Manual review blocker for retaliation" in manual_review_list
                assert "action: resolve_support_conflicts" in manual_review_list
                assert "current support: contradicted" in manual_review_list
                assert "artifact: artifact-conflict" in manual_review_list
                assert "latest evidence event: 2" in manual_review_list
                assert "Alignment update for retaliation" in alignment_updates
                assert "resolution: still_open" in alignment_updates
                assert "resolution: needs_manual_review" in alignment_updates
                assert "evidence event: 1" in alignment_updates
                assert "evidence event: 2" in alignment_updates
                assert "artifact: artifact-conflict" in alignment_updates
                assert "filter: all" in alignment_update_filter_summary
                assert "sort: newest_first" in alignment_update_filter_summary
                assert "visible updates: 2" in alignment_update_filter_summary
                assert alignment_updates.index("evidence event: 2") < alignment_updates.index("evidence event: 1")

                page.select_option("#alignment-task-update-filter", "manual_review")
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('filter: manual_review')"
                )

                filtered_alignment_updates = page.locator("#alignment-task-update-list").inner_text()
                filtered_alignment_summary = page.locator("#alignment-task-update-filter-summary").inner_text()

                assert "alignment_task_update_filter=manual_review" in page.url
                assert "visible updates: 1" in filtered_alignment_summary
                assert "resolution: needs_manual_review" in filtered_alignment_updates
                assert "evidence event: 2" in filtered_alignment_updates
                assert "artifact: artifact-conflict" in filtered_alignment_updates
                assert "resolution: still_open" not in filtered_alignment_updates
                assert "evidence event: 1" not in filtered_alignment_updates

                page.select_option("#alignment-task-update-filter", "all")
                page.select_option("#alignment-task-update-sort", "oldest_first")
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('sort: oldest_first')"
                )

                oldest_first_updates = page.locator("#alignment-task-update-list").inner_text()
                oldest_first_summary = page.locator("#alignment-task-update-filter-summary").inner_text()

                assert "alignment_task_update_sort=oldest_first" in page.url
                assert "sort: oldest_first" in oldest_first_summary
                assert oldest_first_updates.index("evidence event: 1") < oldest_first_updates.index("evidence event: 2")

                page.reload()
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('sort: oldest_first')"
                )

                reloaded_alignment_updates = page.locator("#alignment-task-update-list").inner_text()
                reloaded_alignment_summary = page.locator("#alignment-task-update-filter-summary").inner_text()
                assert page.locator("#alignment-task-update-filter").input_value() == "all"
                assert page.locator("#alignment-task-update-sort").input_value() == "oldest_first"
                assert "alignment_task_update_sort=oldest_first" in page.url
                assert "sort: oldest_first" in reloaded_alignment_summary
                assert reloaded_alignment_updates.index("evidence event: 1") < reloaded_alignment_updates.index("evidence event: 2")

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_filters_pending_review_alignment_updates():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for pending-review filter smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status = mediator.get_three_phase_status.return_value
        status["alignment_task_update_history"] = list(status.get("alignment_task_update_history") or []) + [
            {
                "task_id": "retaliation:retaliation:2:await_operator_confirmation",
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:2",
                "claim_element_label": "Adverse action",
                "action": "await_operator_confirmation",
                "previous_support_status": "missing",
                "current_support_status": "partially_supported",
                "previous_missing_fact_bundle": ["Adverse action details"],
                "current_missing_fact_bundle": [],
                "resolution_status": "answered_pending_review",
                "status": "active",
                "evidence_artifact_id": "artifact-pending",
                "evidence_sequence": 1,
            }
        ]

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                pending_review_summary = page.locator("#alignment-task-pending-review-summary").inner_text()
                pending_review_list = page.locator("#alignment-task-pending-review-list").inner_text()

                assert "pending review items: 1" in pending_review_summary
                assert "claims impacted: 1" in pending_review_summary
                assert "Pending review item for retaliation" in pending_review_list
                assert "element: retaliation:2" in pending_review_list
                assert "action: await_operator_confirmation" in pending_review_list
                assert "current support: partially_supported" in pending_review_list
                assert "artifact: artifact-pending" in pending_review_list
                assert "latest evidence event: 1" in pending_review_list

                page.select_option("#alignment-task-update-filter", "pending_review")
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('filter: pending_review')"
                )

                filtered_alignment_updates = page.locator("#alignment-task-update-list").inner_text()
                filtered_alignment_summary = page.locator("#alignment-task-update-filter-summary").inner_text()

                assert "alignment_task_update_filter=pending_review" in page.url
                assert "visible updates: 1" in filtered_alignment_summary
                assert "ANSWERED, PENDING REVIEW" in filtered_alignment_updates
                assert "element: retaliation:2" in filtered_alignment_updates
                assert "artifact: artifact-pending" in filtered_alignment_updates
                assert "evidence event: 1" in filtered_alignment_updates
                assert "resolution: needs_manual_review" not in filtered_alignment_updates
                assert "resolution: still_open" not in filtered_alignment_updates

                page.select_option("#alignment-task-update-filter", "all")
                page.select_option("#alignment-task-update-sort", "pending_review_first")
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('sort: pending_review_first')"
                )

                pending_first_updates = page.locator("#alignment-task-update-list").inner_text()
                pending_first_summary = page.locator("#alignment-task-update-filter-summary").inner_text()

                assert "alignment_task_update_sort=pending_review_first" in page.url
                assert "sort: pending_review_first" in pending_first_summary
                assert pending_first_updates.index("artifact: artifact-pending") < pending_first_updates.index("artifact: artifact-conflict")
                assert pending_first_updates.index("artifact: artifact-pending") < pending_first_updates.index("artifact: artifact-open")

                page.reload()
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('sort: pending_review_first')"
                )

                reloaded_alignment_updates = page.locator("#alignment-task-update-list").inner_text()
                reloaded_alignment_summary = page.locator("#alignment-task-update-filter-summary").inner_text()
                assert page.locator("#alignment-task-update-filter").input_value() == "all"
                assert page.locator("#alignment-task-update-sort").input_value() == "pending_review_first"
                assert "alignment_task_update_sort=pending_review_first" in page.url
                assert "sort: pending_review_first" in reloaded_alignment_summary
                assert reloaded_alignment_updates.index("artifact: artifact-pending") < reloaded_alignment_updates.index("artifact: artifact-conflict")
                assert reloaded_alignment_updates.index("artifact: artifact-pending") < reloaded_alignment_updates.index("artifact: artifact-open")

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_uploads_document_via_playwright_and_persists_evidence():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as evidence_handle:
        evidence_db_path = evidence_handle.name
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as claim_support_handle:
        claim_support_db_path = claim_support_handle.name
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as legal_handle:
        legal_authority_db_path = legal_handle.name
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as upload_handle:
        upload_handle.write(
            b"The schedule reduction memo confirms the adverse action happened two days after the complaint."
        )
        upload_path = upload_handle.name

    try:
        mediator = _build_real_browser_upload_mediator(
            evidence_db_path=evidence_db_path,
            claim_support_db_path=claim_support_db_path,
            legal_authority_db_path=legal_authority_db_path,
        )

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-upload-user"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                page.fill("#document-element-text", "Adverse action")
                page.fill("#document-label", "Schedule reduction memo")
                page.fill("#document-source-url", "https://example.com/schedule-memo")
                page.set_input_files("#document-file-input", upload_path)
                page.click("#save-document-button")

                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Document uploaded and review payload refreshed.')"
                )
                page.wait_for_function(
                    "() => document.getElementById('document-list').textContent.includes('Schedule reduction memo')"
                )

                document_list_text = page.locator("#document-list").inner_text()
                browser.close()

        assert "Schedule reduction memo" in document_list_text
        assert "Adverse action" in document_list_text

        evidence_conn = duckdb.connect(evidence_db_path, read_only=True)
        try:
            evidence_count = evidence_conn.execute(
                "SELECT COUNT(*) FROM evidence WHERE user_id = ?",
                ["browser-upload-user"],
            ).fetchone()[0]
        finally:
            evidence_conn.close()

        claim_support_conn = duckdb.connect(claim_support_db_path, read_only=True)
        try:
            support_count = claim_support_conn.execute(
                "SELECT COUNT(*) FROM claim_support WHERE user_id = ?",
                ["browser-upload-user"],
            ).fetchone()[0]
        finally:
            claim_support_conn.close()

        assert evidence_count >= 1
        assert support_count >= 1
    finally:
        for path in (
            evidence_db_path,
            claim_support_db_path,
            legal_authority_db_path,
            upload_path,
        ):
            if os.path.exists(path):
                os.unlink(path)


def test_optimization_trace_smoke_renders_question_review_links_with_support_kind():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-smoke",
        "size": 321,
        "trace": {
            "user_id": "trace-smoke-user",
            "intake_status": {
                "current_phase": "intake",
                "score": 0.52,
                "contradiction_count": 0,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation"},
                ],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {
                        "blocking": 1,
                        "non_blocking": 1,
                    },
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
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
        },
    }

    app = _build_document_browser_smoke_app()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.goto(f"{base_url}/document/optimization-trace")
            page.evaluate("payload => window.renderTrace(payload)", payload)
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('#traceEvidenceQuestionTargets a.inline-link')).length >= 2"
            )

            question_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#traceEvidenceQuestionTargets a.inline-link'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )

            assert {
                "text": "Open Proof Leads Question Review (1)",
                "href": "/claim-support-review?user_id=trace-smoke-user&section=proof_leads&follow_up_support_kind=evidence&alignment_task_update_filter=active&alignment_task_update_sort=newest_first",
            } in question_links
            assert {
                "text": "Open Claims For Relief Question Review (1)",
                "href": "/claim-support-review?user_id=trace-smoke-user&section=claims_for_relief&follow_up_support_kind=authority&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first",
            } in question_links

            section_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#traceEvidenceLinks a.inline-link'))
                    .filter((node) => node.textContent.includes('Intake Section Review'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )
            trace_text = page.locator("#traceEvidenceManualReview").inner_text()

            assert {
                "text": "Open Proof Leads Intake Section Review",
                "href": "/claim-support-review?user_id=trace-smoke-user&section=proof_leads&follow_up_support_kind=evidence&alignment_task_update_filter=active&alignment_task_update_sort=newest_first",
            } in section_links
            assert {
                "text": "Open Claims For Relief Intake Section Review",
                "href": "/claim-support-review?user_id=trace-smoke-user&section=claims_for_relief&follow_up_support_kind=authority&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first",
            } in section_links
            assert "Manual Review Blockers" in trace_text
            assert "Manual review blockers: 1" in trace_text
            assert "Claims impacted: 1" in trace_text
            assert "Retaliation: Claims For Relief | action Resolve Support Conflicts | artifact artifact-conflict" in trace_text

            browser.close()


def test_document_builder_question_review_link_click_preserves_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"sections": {}, "claims": [], "warnings": []},
        "filing_checklist": [],
        "review_links": {},
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 0,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {"blocking": 1, "non_blocking": 1},
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
            },
            "packet_projection": {
                "title": "Complaint Packet",
                "section_presence": {"factual_allegations": True},
                "has_affidavit": False,
                "has_certificate_of_service": False,
            },
            "section_history": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "overall_score": 0.7,
                }
            ],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for document-to-review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#previewRoot a.inline-link')).some((node) => node.textContent.includes('Claims For Relief Question Review'))"
                )

                page.click("text=Open Claims For Relief Question Review (1)")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "section=claims_for_relief" in page.url
                assert "follow_up_support_kind=authority" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#support-kind").input_value() == "authority"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"
                assert "Claims For Relief" in page.locator("#prefill-context-line").inner_text()
                assert "Focused lane: Authority." in page.locator("#prefill-context-line").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_document_builder_intake_section_review_link_click_preserves_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"sections": {}, "claims": [], "warnings": []},
        "filing_checklist": [],
        "review_links": {},
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 0,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {"blocking": 1, "non_blocking": 1},
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
            },
            "packet_projection": {
                "title": "Complaint Packet",
                "section_presence": {"factual_allegations": True},
                "has_affidavit": False,
                "has_certificate_of_service": False,
            },
            "section_history": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "overall_score": 0.7,
                }
            ],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for document section review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#previewRoot a.inline-link')).some((node) => node.textContent.includes('Proof Leads Intake Section Review'))"
                )

                page.click("text=Open Proof Leads Intake Section Review")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "section=proof_leads" in page.url
                assert "follow_up_support_kind=evidence" in page.url
                assert "alignment_task_update_filter=active" in page.url
                assert page.locator("#support-kind").input_value() == "evidence"
                assert page.locator("#alignment-task-update-filter").input_value() == "active"
                assert page.locator("#alignment-task-update-sort").input_value() == "newest_first"
                assert "Proof Leads" in page.locator("#prefill-context-line").inner_text()
                assert "Focused lane: Evidence." in page.locator("#prefill-context-line").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_optimization_trace_question_review_link_click_preserves_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-smoke",
        "size": 321,
        "trace": {
            "user_id": "browser-smoke-text-link",
            "intake_status": {
                "current_phase": "intake",
                "score": 0.52,
                "contradiction_count": 0,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation"},
                ],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {
                        "blocking": 1,
                        "non_blocking": 1,
                    },
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
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
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for trace-to-review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document/optimization-trace")
                page.evaluate("payload => window.renderTrace(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#traceEvidenceQuestionTargets a.inline-link')).some((node) => node.textContent.includes('Claims For Relief Question Review'))"
                )

                page.click("text=Open Claims For Relief Question Review (1)")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "user_id=browser-smoke-text-link" in page.url
                assert "section=claims_for_relief" in page.url
                assert "follow_up_support_kind=authority" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#support-kind").input_value() == "authority"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"
                assert "Claims For Relief" in page.locator("#prefill-context-line").inner_text()
                assert "Focused lane: Authority." in page.locator("#prefill-context-line").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_optimization_trace_intake_section_review_link_click_preserves_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-smoke",
        "size": 321,
        "trace": {
            "user_id": "browser-smoke-text-link",
            "intake_status": {
                "current_phase": "intake",
                "score": 0.52,
                "contradiction_count": 0,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation"},
                ],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {
                        "blocking": 1,
                        "non_blocking": 1,
                    },
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
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
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for trace section review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document/optimization-trace")
                page.evaluate("payload => window.renderTrace(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#traceEvidenceLinks a.inline-link')).some((node) => node.textContent.includes('Claims For Relief Intake Section Review'))"
                )

                page.click("text=Open Claims For Relief Intake Section Review")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "user_id=browser-smoke-text-link" in page.url
                assert "section=claims_for_relief" in page.url
                assert "follow_up_support_kind=authority" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#support-kind").input_value() == "authority"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"
                assert "Claims For Relief" in page.locator("#prefill-context-line").inner_text()
                assert "Focused lane: Authority." in page.locator("#prefill-context-line").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
