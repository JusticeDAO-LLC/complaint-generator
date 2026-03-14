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


def _build_hook_backed_browser_mediator(db_path: str):
    try:
        from mediator.claim_support_hooks import ClaimSupportHook
    except ImportError as exc:
        pytest.skip(f"ClaimSupportHook requires dependencies: {exc}")

    mediator = Mock()
    mediator.state = SimpleNamespace(username="browser-smoke-text-link", hashed_username=None)
    mediator.log = Mock()

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