import json
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

try:
    import fastapi  # noqa: F401
except Exception as exc:  # pragma: no cover - optional dependency gate
    _FASTAPI_IMPORT_ERROR = exc
else:  # pragma: no cover - exercised indirectly in tests
    _FASTAPI_IMPORT_ERROR = None

try:
    import python_multipart  # noqa: F401
except Exception as exc:  # pragma: no cover - optional dependency gate
    _MULTIPART_IMPORT_ERROR = exc
else:  # pragma: no cover - exercised indirectly in tests
    _MULTIPART_IMPORT_ERROR = None

try:
    import uvicorn
except Exception as exc:  # pragma: no cover - optional dependency gate
    uvicorn = None
    _UVICORN_IMPORT_ERROR = exc
else:  # pragma: no cover - exercised indirectly in tests
    _UVICORN_IMPORT_ERROR = None

try:
    from playwright.sync_api import sync_playwright
except Exception as exc:  # pragma: no cover - optional dependency gate
    sync_playwright = None
    _PLAYWRIGHT_IMPORT_ERROR = exc
else:  # pragma: no cover - exercised indirectly in tests
    _PLAYWRIGHT_IMPORT_ERROR = None

from applications.dashboard_ui import _IPFS_DASHBOARD_ENTRIES
from applications.review_ui import create_review_surface_app


pytestmark = [pytest.mark.no_auto_network, pytest.mark.browser]


_IPFS_DASHBOARD_ROUTES = [
    (entry.slug, entry.title)
    for entry in _IPFS_DASHBOARD_ENTRIES
]


def _require_browser_stack() -> None:
    if _FASTAPI_IMPORT_ERROR is not None:
        pytest.skip(f"fastapi is unavailable: {_FASTAPI_IMPORT_ERROR}")
    if _MULTIPART_IMPORT_ERROR is not None:
        pytest.skip(f"python-multipart is unavailable: {_MULTIPART_IMPORT_ERROR}")
    if _UVICORN_IMPORT_ERROR is not None or uvicorn is None:
        pytest.skip(f"uvicorn is unavailable: {_UVICORN_IMPORT_ERROR}")
    if _PLAYWRIGHT_IMPORT_ERROR is not None or sync_playwright is None:
        pytest.skip(f"playwright is unavailable: {_PLAYWRIGHT_IMPORT_ERROR}")


class _SiteFlowMediator:
    def __init__(self, artifact_dir: Path):
        self.state = SimpleNamespace(username="site-flow-user", hashed_username=None)
        self.log = SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None)
        self._artifact_dir = artifact_dir
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        self._artifact_path = self._artifact_dir / "formal-complaint.txt"
        self._artifact_path.write_text("Complaint artifact", encoding="utf-8")
        self._sequence = 0
        self._testimony_records = []
        self._evidence_records = []
        self._evidence_chunks = {}
        self._evidence_facts = {}
        self._evidence_graphs = {}
        self._summary_confirmation = {
            "status": "pending",
            "confirmed": False,
            "current_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 0,
                "proof_lead_count": 0,
                "open_item_count": 1,
            },
            "confirmed_summary_snapshot": {},
        }

    def _next_id(self):
        self._sequence += 1
        return self._sequence

    def _timestamp(self):
        return f"2026-03-22T12:00:{self._sequence:02d}+00:00"

    def _filtered_testimony_records(self, claim_type=None):
        return [
            record
            for record in self._testimony_records
            if not claim_type or record.get("claim_type") == claim_type
        ]

    def _filtered_evidence_records(self, claim_type=None):
        return [
            record
            for record in self._evidence_records
            if not claim_type or record.get("claim_type") == claim_type
        ]

    def get_three_phase_status(self):
        return {
            "current_phase": "intake",
            "score": 0.94,
            "ready_to_advance": True,
            "intake_readiness": {
                "ready_to_advance": True,
            },
            "remaining_gap_count": 0,
            "contradiction_count": 0,
            "blockers": [],
            "criteria": {
                "case_theory_coherent": True,
                "minimum_proof_path_present": True,
            },
            "candidate_claims": [
                {
                    "claim_type": "retaliation",
                    "label": "Retaliation",
                    "confidence": 0.94,
                }
            ],
            "next_action": {
                "action": "generate_formal_complaint",
                "claim_type": "retaliation",
            },
            "complainant_summary_confirmation": dict(self._summary_confirmation),
        }

    def build_formal_complaint_document_package(self, **kwargs):
        user_id = kwargs.get("user_id") or self.state.username
        return {
            "draft": {
                "title": "Jane Doe v. Acme Corporation",
                "draft_text": "Plaintiff Jane Doe alleges retaliation after protected activity.",
                "source_context": {"user_id": user_id},
                "factual_allegations": [
                    "Plaintiff reported discrimination.",
                    "Defendant terminated Plaintiff shortly thereafter.",
                ],
                "requested_relief": ["Back pay", "Reinstatement"],
            },
            "drafting_readiness": {
                "status": "warning",
                "warning_count": 1,
                "claims": [
                    {
                        "claim_type": "retaliation",
                        "status": "warning",
                    }
                ],
                "sections": {
                    "summary_of_facts": {
                        "title": "Summary of Facts",
                        "status": "warning",
                    }
                },
            },
            "document_optimization": {
                "status": "optimized",
                "method": "test_optimizer",
                "optimizer_backend": "local_fallback",
                "initial_score": 0.58,
                "final_score": 0.92,
                "accepted_iterations": 1,
                "iteration_count": 1,
                "optimized_sections": ["summary_of_facts"],
                "trace_storage": {
                    "status": "available",
                    "cid": "bafy-site-flow-trace",
                    "size": 512,
                    "pinned": True,
                },
            },
            "filing_checklist": [
                {"label": "Civil cover sheet", "status": "warning"}
            ],
            "artifacts": {
                "txt": {
                    "path": str(self._artifact_path),
                    "filename": self._artifact_path.name,
                }
            },
            "output_formats": ["txt"],
            "generated_at": "2026-03-22T12:00:00+00:00",
        }

    def get_claim_coverage_matrix(self, **kwargs):
        return {
            "claims": {
                "retaliation": {
                    "claim_type": "retaliation",
                    "total_elements": 1,
                    "status_counts": {
                        "covered": 0,
                        "partially_supported": 0,
                        "missing": 1,
                    },
                    "support_by_kind": {},
                    "elements": [
                        {
                            "element_id": "retaliation:1",
                            "element_text": "Protected activity",
                            "status": "missing",
                            "fact_count": 0,
                            "total_links": 0,
                            "missing_support_kinds": ["evidence"],
                            "support_packets": [],
                            "links_by_kind": {},
                        }
                    ],
                }
            }
        }

    def get_claim_overview(self, **kwargs):
        return {
            "claims": {
                "retaliation": {
                    "missing": [{"element_text": "Protected activity"}],
                    "partially_supported": [],
                }
            }
        }

    def get_claim_support_diagnostic_snapshots(self, **kwargs):
        return {"claims": {}}

    def get_claim_support_gaps(self, **kwargs):
        return {"claims": {"retaliation": {"unresolved_count": 1, "unresolved_elements": []}}}

    def get_claim_contradiction_candidates(self, **kwargs):
        return {"claims": {"retaliation": {"candidate_count": 0, "candidates": []}}}

    def get_claim_support_validation(self, **kwargs):
        return {
            "claims": {
                "retaliation": {
                    "claim_type": "retaliation",
                    "proof_diagnostics": {},
                }
            }
        }

    def get_recent_claim_follow_up_execution(self, **kwargs):
        return {"claims": {}}

    def get_claim_follow_up_plan(self, **kwargs):
        return {"claims": {}}

    def summarize_claim_support(self, **kwargs):
        return {"claims": {}}

    def get_claim_testimony_records(self, claim_type=None, **kwargs):
        records = self._filtered_testimony_records(claim_type)
        firsthand_counts = {}
        linked_elements = set()
        for record in records:
            firsthand_status = str(record.get("firsthand_status") or "unknown")
            firsthand_counts[firsthand_status] = firsthand_counts.get(firsthand_status, 0) + 1
            if record.get("claim_element_id"):
                linked_elements.add(str(record["claim_element_id"]))
        claim_name = claim_type or "retaliation"
        return {
            "claims": {claim_name: records},
            "summary": {
                claim_name: {
                    "record_count": len(records),
                    "linked_element_count": len(linked_elements),
                    "firsthand_status_counts": firsthand_counts,
                    "confidence_bucket_counts": {},
                }
            },
        }

    def save_claim_testimony_record(
        self,
        *,
        claim_type,
        claim_element_id,
        claim_element_text,
        raw_narrative,
        event_date,
        actor,
        act,
        target,
        harm,
        firsthand_status,
        source_confidence,
        **kwargs,
    ):
        self._next_id()
        record = {
            "claim_type": claim_type,
            "claim_element_id": claim_element_id,
            "claim_element_text": claim_element_text,
            "raw_narrative": raw_narrative,
            "event_date": event_date,
            "actor": actor,
            "act": act,
            "target": target,
            "harm": harm,
            "firsthand_status": firsthand_status,
            "source_confidence": source_confidence,
            "timestamp": self._timestamp(),
        }
        self._testimony_records.append(record)
        return {
            "recorded": True,
            "claim_type": claim_type,
            "claim_element_id": claim_element_id,
        }

    def save_claim_support_document(
        self,
        *,
        claim_type,
        claim_element_id,
        claim_element_text,
        document_text,
        document_label,
        source_url,
        filename,
        mime_type,
        evidence_type,
        **kwargs,
    ):
        record_id = self._next_id()
        effective_text = document_text or "Document text unavailable."
        effective_filename = filename or "disciplinary-note.txt"
        effective_label = document_label or effective_filename
        effective_mime_type = mime_type or "text/plain"
        chunk_id = f"chunk-{record_id}"
        fact_id = f"fact-{record_id}"
        evidence_record = {
            "id": record_id,
            "cid": f"bafy-site-flow-doc-{record_id}",
            "type": evidence_type or "document",
            "claim_type": claim_type,
            "claim_element_id": claim_element_id,
            "claim_element": claim_element_text,
            "description": effective_label,
            "timestamp": self._timestamp(),
            "source_url": source_url,
            "metadata": {
                "filename": effective_filename,
                "mime_type": effective_mime_type,
            },
            "parse_status": "parsed",
            "chunk_count": 1,
            "fact_count": 1,
            "parsed_text_preview": effective_text[:160],
            "parse_metadata": {
                "quality_tier": "high",
                "mime_type": effective_mime_type,
            },
            "graph_status": "ready",
            "graph_entity_count": 1,
            "graph_relationship_count": 1,
        }
        self._evidence_records.append(evidence_record)
        self._evidence_chunks[record_id] = [
            {
                "chunk_id": chunk_id,
                "index": 0,
                "text": effective_text[:120],
            }
        ]
        self._evidence_facts[record_id] = [
            {
                "fact_id": fact_id,
                "text": "Supervisor issued discipline after protected report.",
                "quality_tier": "high",
                "confidence": 0.91,
                "source_chunk_ids": [chunk_id],
            }
        ]
        self._evidence_graphs[record_id] = {
            "status": "ready",
            "entity_count": 1,
            "relationship_count": 1,
            "entities": [
                {
                    "id": f"entity-{record_id}",
                    "name": "Supervisor",
                    "type": "person",
                }
            ],
            "relationships": [
                {
                    "id": f"relationship-{record_id}",
                    "relation_type": "issued_discipline",
                    "source_id": f"entity-{record_id}",
                    "target_id": claim_element_id or "retaliation:1",
                }
            ],
        }
        self._summary_confirmation["current_summary_snapshot"] = {
            "candidate_claim_count": 1,
            "canonical_fact_count": len(self._evidence_records),
            "proof_lead_count": len(self._evidence_records),
            "open_item_count": 0,
        }
        return {
            "record_id": record_id,
            "cid": evidence_record["cid"],
        }

    def get_user_evidence(self, **kwargs):
        claim_type = kwargs.get("claim_type")
        return list(self._filtered_evidence_records(claim_type))

    def get_evidence_chunks(self, record_id):
        return list(self._evidence_chunks.get(record_id, []))

    def get_evidence_facts(self, record_id):
        return list(self._evidence_facts.get(record_id, []))

    def get_evidence_graph(self, record_id):
        return dict(self._evidence_graphs.get(record_id, {}))

    def confirm_intake_summary(self, confirmation_note="", confirmation_source="dashboard"):
        confirmed_snapshot = dict(self._summary_confirmation.get("current_summary_snapshot") or {})
        self._summary_confirmation = {
            "status": "confirmed",
            "confirmed": True,
            "confirmation_note": confirmation_note,
            "confirmation_source": confirmation_source,
            "confirmed_at": "2026-03-22T12:30:00+00:00",
            "current_summary_snapshot": confirmed_snapshot,
            "confirmed_summary_snapshot": confirmed_snapshot,
        }
        return {
            "complainant_summary_confirmation": dict(self._summary_confirmation),
        }


@contextmanager
def _serve_app(app):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://{host}:{port}"
    deadline = time.time() + 10
    last_error = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                break
        except OSError as exc:  # pragma: no cover - readiness polling
            last_error = exc
            time.sleep(0.05)
    else:  # pragma: no cover - readiness polling
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError(f"Timed out waiting for test server: {last_error}")

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _wait_for_text(page, selector: str, expected_text: str) -> None:
    page.wait_for_function(
        """
        ({selector, expectedText}) => {
            const element = document.querySelector(selector);
            return Boolean(element && element.textContent && element.textContent.includes(expectedText));
        }
        """,
        arg={"selector": selector, "expectedText": expected_text},
    )


def _wait_for_input_value(page, selector: str, expected_value: str) -> None:
    page.wait_for_function(
        """
        ({selector, expectedValue}) => {
            const element = document.querySelector(selector);
            return Boolean(element && 'value' in element && element.value === expectedValue);
        }
        """,
        arg={"selector": selector, "expectedValue": expected_value},
    )


def test_review_surface_site_navigation_serves_all_operator_pages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _require_browser_stack()

    from applications import document_api

    trace_payload = {
        "draft": {"title": "Jane Doe v. Acme Corporation"},
        "drafting_readiness": {"status": "warning"},
        "document_optimization": {
            "status": "optimized",
            "optimized_sections": ["summary_of_facts"],
        },
    }
    trace_bytes = json.dumps(trace_payload).encode("utf-8")
    monkeypatch.setattr(
        document_api,
        "retrieve_bytes",
        lambda cid: {"status": "available", "data": trace_bytes, "size": len(trace_bytes)},
    )

    app = create_review_surface_app(_SiteFlowMediator(tmp_path / "artifacts"))

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            try:
                page.goto(f"{base_url}/", wait_until="domcontentloaded")
                expect_links = [
                    ("/", "a[href='/claim-support-review']", "a[href='/document']"),
                    ("/home", "a[href='/claim-support-review']", "a[href='/document']"),
                    ("/chat", "a[href='/claim-support-review']", "a[href='/document']"),
                    ("/results", "a[href='/claim-support-review']", "a[href='/document']"),
                    ("/profile", "a[href='/claim-support-review']", "a[href='/document/optimization-trace']"),
                ]
                for path, primary_selector, secondary_selector in expect_links:
                    page.goto(f"{base_url}{path}", wait_until="domcontentloaded")
                    assert page.locator(primary_selector).first.is_visible()
                    assert page.locator(secondary_selector).first.is_visible()

                page.goto(f"{base_url}/claim-support-review", wait_until="domcontentloaded")
                assert page.get_by_role("button", name="Load Review").is_visible()
                assert page.locator("a[href='/document']").first.is_visible()

                page.goto(f"{base_url}/document", wait_until="domcontentloaded")
                assert page.get_by_role("button", name="Generate Formal Complaint").is_visible()
                assert page.locator("a[href='/claim-support-review']").first.is_visible()

                page.goto(f"{base_url}/document/optimization-trace", wait_until="domcontentloaded")
                assert page.get_by_role("button", name="Load Trace").is_visible()
                assert page.locator("a[href='/document']").first.is_visible()

                page.goto(f"{base_url}/mlwysiwyg", wait_until="domcontentloaded")
                assert page.locator("h1").filter(has_text="Complaint Editor Workshop").is_visible()
                assert page.locator("a[href='/dashboards']").first.is_visible()

                page.goto(f"{base_url}/ipfs-datasets/sdk-playground", wait_until="domcontentloaded")
                assert page.locator("h1").filter(has_text="🎮 SDK Playground").is_visible()
                assert page.locator("a[href='/dashboards']").first.is_visible()

                page.goto(f"{base_url}/dashboards", wait_until="domcontentloaded")
                assert page.get_by_role("heading", name="Unified Dashboard Hub").is_visible()
                assert page.locator("a[href='/dashboards/ipfs-datasets/mcp']").first.is_visible()
            finally:
                browser.close()


def test_review_surface_site_navigation_supports_review_to_builder_to_trace_loop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    _require_browser_stack()

    from applications import document_api

    trace_payload = {
        "draft": {"title": "Jane Doe v. Acme Corporation"},
        "drafting_readiness": {
            "status": "warning",
            "sections": {"summary_of_facts": {"title": "Summary of Facts", "status": "warning"}},
            "claims": [{"claim_type": "retaliation", "status": "warning"}],
        },
        "document_optimization": {
            "status": "optimized",
            "optimized_sections": ["summary_of_facts"],
            "trace_storage": {"cid": "bafy-site-flow-trace"},
        },
    }
    trace_bytes = json.dumps(trace_payload).encode("utf-8")
    monkeypatch.setattr(
        document_api,
        "retrieve_bytes",
        lambda cid: {"status": "available", "data": trace_bytes, "size": len(trace_bytes)},
    )

    app = create_review_surface_app(_SiteFlowMediator(tmp_path / "artifacts"))

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            try:
                page.goto(f"{base_url}/", wait_until="domcontentloaded")
                review_href = page.locator("a[href='/claim-support-review']").first.get_attribute("href")
                assert review_href == "/claim-support-review"
                page.goto(f"{base_url}{review_href}", wait_until="domcontentloaded")
                assert page.url.startswith(f"{base_url}/claim-support-review")
                assert "claim_type=retaliation" in page.url
                assert page.get_by_role("button", name="Load Review").is_visible()

                page.locator("a[href='/document']").first.click(force=True)
                page.wait_for_url(f"{base_url}/document")
                page.locator("#district").fill("Northern District of California")
                page.locator("#plaintiffs").fill("Jane Doe")
                page.locator("#defendants").fill("Acme Corporation")
                page.locator("#enableAgenticOptimization").check()
                page.locator("#optimizationPersistArtifacts").check()
                page.get_by_role("button", name="Generate Formal Complaint").click()
                page.locator("#successBox").wait_for(state="visible")
                assert "generated successfully" in page.locator("#successBox").inner_text().lower()
                persisted_trace_link = page.get_by_role("link", name="Open Persisted Trace")
                assert persisted_trace_link.is_visible()

                with page.context.expect_page() as popup_info:
                    persisted_trace_link.click()
                trace_page = popup_info.value
                trace_page.wait_for_load_state("domcontentloaded")
                trace_page.wait_for_url("**/document/optimization-trace?cid=bafy-site-flow-trace")
                assert trace_page.locator("#traceCidInput").input_value() == "bafy-site-flow-trace"
                assert trace_page.get_by_role("button", name="Load Trace").is_visible()

                trace_page.locator("a[href='/document']").first.click(force=True)
                trace_page.wait_for_url(f"{base_url}/document")
                assert trace_page.get_by_role("button", name="Generate Formal Complaint").is_visible()

                trace_page.locator("a[href='/claim-support-review']").first.click(force=True)
                trace_page.wait_for_url(f"{base_url}/claim-support-review")
                assert trace_page.get_by_role("button", name="Load Review").is_visible()
                trace_page.close()
            finally:
                browser.close()


def test_review_surface_dashboard_actions_update_live_review(tmp_path: Path):
    _require_browser_stack()

    mediator = _SiteFlowMediator(tmp_path / "artifacts")
    app = create_review_surface_app(mediator)

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            try:
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation",
                    wait_until="domcontentloaded",
                )
                page.get_by_role("button", name="Load Review").click()
                _wait_for_text(page, "#status-line", "Review payload loaded.")
                _wait_for_text(page, "#confirm-intake-summary-status", "awaiting complainant confirmation")

                page.locator("#testimony-element-id").fill("retaliation:1")
                page.locator("#testimony-element-text").fill("Protected activity")
                page.locator("#testimony-actor").fill("Jane Doe")
                page.locator("#testimony-act").fill("Reported discrimination to HR")
                page.locator("#testimony-harm").fill("Supervisor retaliation")
                page.locator("#testimony-narrative").fill(
                    "I reported discrimination to HR, and my supervisor started retaliating the next day."
                )
                page.get_by_role("button", name="Save Testimony").click()
                _wait_for_text(page, "#testimony-summary-chips", "Records: 1")
                _wait_for_text(page, "#testimony-list", "Protected activity")
                _wait_for_text(page, "#testimony-list", "Reported discrimination to HR")

                page.locator("#document-element-id").fill("retaliation:1")
                page.locator("#document-element-text").fill("Protected activity")
                page.locator("#document-label").fill("Supervisor write-up")
                page.locator("#document-filename").fill("writeup.txt")
                page.locator("#document-text").fill(
                    "Supervisor issued a disciplinary write-up immediately after the protected report."
                )
                page.get_by_role("button", name="Save Document").click()
                _wait_for_text(page, "#document-summary-chips", "Documents: 1")
                _wait_for_text(page, "#document-list", "Supervisor write-up")
                _wait_for_text(page, "#document-list", "Fact previews")

                page.locator("#confirm-intake-summary-note").fill("Reviewed with complainant on the dashboard.")
                page.locator("#confirm-intake-summary-button").click()
                _wait_for_text(page, "#status-line", "Intake summary confirmed.")
                _wait_for_text(page, "#confirm-intake-summary-status", "Intake summary confirmed")
                assert page.locator("#confirm-intake-summary-button").is_disabled()
            finally:
                browser.close()


def test_review_surface_live_dashboard_captures_loaded_and_updated_review_screenshots(tmp_path: Path):
    _require_browser_stack()

    mediator = _SiteFlowMediator(tmp_path / "artifacts")
    app = create_review_surface_app(mediator)
    screenshot_dir = tmp_path / "review-surface-live-dashboard-snapshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            try:
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation",
                    wait_until="domcontentloaded",
                )
                page.get_by_role("button", name="Load Review").click()
                _wait_for_text(page, "#status-line", "Review payload loaded.")
                _wait_for_text(page, "#confirm-intake-summary-status", "awaiting complainant confirmation")
                _wait_for_text(page, "body", "Operator Review Surface")

                loaded_screenshot = screenshot_dir / "review-loaded.png"
                page.screenshot(path=str(loaded_screenshot), full_page=True)
                assert loaded_screenshot.exists()
                assert loaded_screenshot.stat().st_size > 0

                page.locator("#testimony-element-id").fill("retaliation:1")
                page.locator("#testimony-element-text").fill("Protected activity")
                page.locator("#testimony-actor").fill("Jane Doe")
                page.locator("#testimony-act").fill("Reported discrimination to HR")
                page.locator("#testimony-harm").fill("Supervisor retaliation")
                page.locator("#testimony-narrative").fill(
                    "I reported discrimination to HR, and my supervisor started retaliating the next day."
                )
                page.get_by_role("button", name="Save Testimony").click()
                _wait_for_text(page, "#testimony-summary-chips", "Records: 1")
                _wait_for_text(page, "#testimony-list", "Protected activity")

                page.locator("#document-element-id").fill("retaliation:1")
                page.locator("#document-element-text").fill("Protected activity")
                page.locator("#document-label").fill("Supervisor write-up")
                page.locator("#document-filename").fill("writeup.txt")
                page.locator("#document-text").fill(
                    "Supervisor issued a disciplinary write-up immediately after the protected report."
                )
                page.get_by_role("button", name="Save Document").click()
                _wait_for_text(page, "#document-summary-chips", "Documents: 1")
                _wait_for_text(page, "#document-list", "Supervisor write-up")

                page.locator("#confirm-intake-summary-note").fill("Reviewed with complainant on the dashboard.")
                page.locator("#confirm-intake-summary-button").click()
                _wait_for_text(page, "#status-line", "Intake summary confirmed.")
                _wait_for_text(page, "#confirm-intake-summary-status", "Intake summary confirmed")
                assert page.locator("#confirm-intake-summary-button").is_disabled()

                updated_screenshot = screenshot_dir / "review-updated.png"
                page.screenshot(path=str(updated_screenshot), full_page=True)
                assert updated_screenshot.exists()
                assert updated_screenshot.stat().st_size > 0
            finally:
                browser.close()


def test_review_surface_restores_review_focus_after_reopen(tmp_path: Path):
    _require_browser_stack()

    app = create_review_surface_app(_SiteFlowMediator(tmp_path / "artifacts"))

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            context = browser.new_context()
            try:
                page = context.new_page()
                page.goto(f"{base_url}/claim-support-review?claim_type=retaliation", wait_until="domcontentloaded")
                page.locator("#user-id").fill("resume-user")
                page.locator("#support-kind").select_option("evidence")
                page.get_by_role("button", name="Load Review").click()
                _wait_for_text(page, "#status-line", "Review payload loaded.")
                page.close()

                resumed_page = context.new_page()
                resumed_page.goto(f"{base_url}/claim-support-review", wait_until="domcontentloaded")
                _wait_for_input_value(resumed_page, "#claim-type", "retaliation")
                _wait_for_input_value(resumed_page, "#user-id", "resume-user")
                _wait_for_input_value(resumed_page, "#support-kind", "evidence")
                assert "claim_type=retaliation" in resumed_page.url
                assert "user_id=resume-user" in resumed_page.url
                assert "follow_up_support_kind=evidence" in resumed_page.url
                resumed_page.close()
            finally:
                context.close()
                browser.close()


def test_review_surface_restores_document_builder_state_and_review_resume_link(tmp_path: Path):
    _require_browser_stack()

    app = create_review_surface_app(_SiteFlowMediator(tmp_path / "artifacts"))

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            context = browser.new_context()
            try:
                review_page = context.new_page()
                review_page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation",
                    wait_until="domcontentloaded",
                )
                review_page.locator("#user-id").fill("resume-user")
                review_page.get_by_role("button", name="Load Review").click()
                _wait_for_text(review_page, "#status-line", "Review payload loaded.")
                review_page.locator("a[href='/document']").first.click(force=True)
                review_page.wait_for_url(f"{base_url}/document")
                review_page.locator("#district").fill("Northern District of California")
                review_page.locator("#plaintiffs").fill("Jane Doe")
                review_page.locator("#defendants").fill("Acme Corporation")
                review_page.locator("#enableAgenticOptimization").check()
                review_page.locator("#optimizationPersistArtifacts").check()
                review_page.get_by_role("button", name="Generate Formal Complaint").click()
                review_page.locator("#successBox").wait_for(state="visible")
                _wait_for_text(
                    review_page,
                    "#previewRoot",
                    "Plaintiff Jane Doe alleges retaliation after protected activity.",
                )
                review_page.close()

                resumed_builder = context.new_page()
                resumed_builder.goto(f"{base_url}/document", wait_until="domcontentloaded")
                _wait_for_input_value(resumed_builder, "#district", "Northern District of California")
                _wait_for_input_value(resumed_builder, "#plaintiffs", "Jane Doe")
                _wait_for_input_value(resumed_builder, "#defendants", "Acme Corporation")
                _wait_for_text(
                    resumed_builder,
                    "#previewRoot",
                    "Plaintiff Jane Doe alleges retaliation after protected activity.",
                )
                resume_link = resumed_builder.get_by_role("link", name="Resume Review Focus")
                assert resume_link.is_visible()
                resume_href = resume_link.get_attribute("href") or ""
                assert resume_href.startswith("/claim-support-review?")
                assert "claim_type=retaliation" in resume_href
                assert "user_id=resume-user" in resume_href

                resume_link.click()
                resumed_builder.wait_for_url("**/claim-support-review?*")
                _wait_for_input_value(resumed_builder, "#claim-type", "retaliation")
                _wait_for_input_value(resumed_builder, "#user-id", "resume-user")
            finally:
                context.close()
                browser.close()


def test_review_surface_resume_loop_captures_builder_and_review_screenshots(tmp_path: Path):
    _require_browser_stack()

    app = create_review_surface_app(_SiteFlowMediator(tmp_path / "artifacts"))
    screenshot_dir = tmp_path / "review-surface-resume-snapshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 1200})
            try:
                review_page = context.new_page()
                review_page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation",
                    wait_until="domcontentloaded",
                )
                review_page.locator("#user-id").fill("resume-user")
                review_page.get_by_role("button", name="Load Review").click()
                _wait_for_text(review_page, "#status-line", "Review payload loaded.")
                review_page.locator("a[href='/document']").first.click(force=True)
                review_page.wait_for_url(f"{base_url}/document")
                review_page.locator("#district").fill("Northern District of California")
                review_page.locator("#plaintiffs").fill("Jane Doe")
                review_page.locator("#defendants").fill("Acme Corporation")
                review_page.locator("#enableAgenticOptimization").check()
                review_page.locator("#optimizationPersistArtifacts").check()
                review_page.get_by_role("button", name="Generate Formal Complaint").click()
                review_page.locator("#successBox").wait_for(state="visible")
                _wait_for_text(
                    review_page,
                    "#previewRoot",
                    "Plaintiff Jane Doe alleges retaliation after protected activity.",
                )
                review_page.close()

                resumed_builder = context.new_page()
                resumed_builder.goto(f"{base_url}/document", wait_until="domcontentloaded")
                _wait_for_input_value(resumed_builder, "#district", "Northern District of California")
                _wait_for_input_value(resumed_builder, "#plaintiffs", "Jane Doe")
                _wait_for_input_value(resumed_builder, "#defendants", "Acme Corporation")
                _wait_for_text(
                    resumed_builder,
                    "#previewRoot",
                    "Plaintiff Jane Doe alleges retaliation after protected activity.",
                )
                resume_link = resumed_builder.get_by_role("link", name="Resume Review Focus")
                assert resume_link.is_visible()
                builder_screenshot = screenshot_dir / "builder-resume-link.png"
                resumed_builder.screenshot(path=str(builder_screenshot), full_page=True)
                assert builder_screenshot.exists()
                assert builder_screenshot.stat().st_size > 0

                resume_href = resume_link.get_attribute("href") or ""
                assert resume_href.startswith("/claim-support-review?")
                assert "claim_type=retaliation" in resume_href
                assert "user_id=resume-user" in resume_href

                resume_link.click()
                resumed_builder.wait_for_url("**/claim-support-review?*")
                _wait_for_input_value(resumed_builder, "#claim-type", "retaliation")
                _wait_for_input_value(resumed_builder, "#user-id", "resume-user")
                _wait_for_text(resumed_builder, "#status-line", "Review payload loaded.")
                review_screenshot = screenshot_dir / "review-resumed-focus.png"
                resumed_builder.screenshot(path=str(review_screenshot), full_page=True)
                assert review_screenshot.exists()
                assert review_screenshot.stat().st_size > 0
            finally:
                context.close()
                browser.close()


def test_review_surface_ipfs_dashboard_shells_render_all_registered_dashboards(tmp_path: Path):
    _require_browser_stack()

    app = create_review_surface_app(_SiteFlowMediator(tmp_path / "artifacts"))

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            try:
                page.goto(f"{base_url}/dashboards", wait_until="domcontentloaded")
                assert page.get_by_role("heading", name="Unified Dashboard Hub").is_visible()

                for slug, title in _IPFS_DASHBOARD_ROUTES:
                    page.goto(f"{base_url}/dashboards/ipfs-datasets/{slug}", wait_until="domcontentloaded")
                    assert page.get_by_role("heading", name=title).is_visible()
                    iframe = page.frame_locator("iframe")
                    iframe.locator("body").wait_for()
                    assert len(iframe.locator("body").inner_text().strip()) > 0
            finally:
                browser.close()


def test_review_surface_ipfs_dashboard_raw_routes_render_all_registered_dashboards(tmp_path: Path):
    _require_browser_stack()

    app = create_review_surface_app(_SiteFlowMediator(tmp_path / "artifacts"))

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            try:
                for slug, title in _IPFS_DASHBOARD_ROUTES:
                    response = page.goto(
                        f"{base_url}/dashboards/raw/ipfs-datasets/{slug}",
                        wait_until="domcontentloaded",
                    )
                    assert response is not None
                    assert response.ok
                    assert len(page.content()) > 500
                    body_text = page.locator("body").inner_text().strip()
                    assert body_text
                    assert page.title().strip()
            finally:
                browser.close()


def test_review_surface_workspace_sdk_flow_exercises_mcp_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    _require_browser_stack()

    from applications import complaint_workspace as complaint_workspace_module
    from applications import complaint_workspace_api as complaint_workspace_api_module

    workspace_root = tmp_path / ".complaint_workspace"
    monkeypatch.setattr(
        complaint_workspace_api_module,
        "ComplaintWorkspaceService",
        lambda: complaint_workspace_module.ComplaintWorkspaceService(root_dir=workspace_root),
    )
    monkeypatch.setattr(
        "complaint_generator.ui_ux_workflow.run_iterative_ui_ux_workflow",
        lambda **kwargs: {
            "iterations": int(kwargs.get("iterations") or 1),
            "screenshot_dir": str(kwargs.get("screenshot_dir") or workspace_root / "screens"),
            "output_dir": str(kwargs.get("output_dir") or workspace_root / "reviews"),
            "latest_review": "# Top Risks\n- Intake language needs calmer guidance for first-time complainants.\n\n# Stage Findings\n## Intake\nMarkdown fallback should not replace structured intake guidance.\n\n## Evidence\nMarkdown fallback should not replace structured evidence guidance.",
            "stage_findings": {
                "Intake": "First-time complainants need calmer prompts before being asked for exact detail.",
                "Evidence": "The evidence stage should explain what helps prove causation next.",
            },
            "latest_review_markdown_path": str(workspace_root / "reviews" / "iteration-01-review.md"),
            "runs": [
                {
                    "iteration": 1,
                    "artifact_count": 1,
                    "review_excerpt": "Intake language needs calmer guidance for first-time complainants.",
                    "review_markdown_path": str(workspace_root / "reviews" / "iteration-01-review.md"),
                    "review_json_path": str(workspace_root / "reviews" / "iteration-01-review.json"),
                }
            ],
        },
    )
    monkeypatch.setattr(
        "complaint_generator.ui_ux_workflow.run_closed_loop_ui_ux_improvement",
        lambda **kwargs: {
            "workflow_type": "ui_ux_closed_loop",
            "max_rounds": int(kwargs.get("max_rounds") or 2),
            "rounds_executed": 1,
            "stop_reason": "validation_review_stable",
            "latest_validation_review": "# Top Risks\n- Closed-loop pass recommends calmer intake guidance and clearer evidence sequencing.\n\n# Stage Findings\n## Integration Discovery\nMarkdown fallback should not replace the structured integration-discovery finding.",
            "stage_findings": {
                "Draft": "Draft readiness should remain visible after optimization.",
                "Integration Discovery": "The shared MCP SDK and optimizer path should remain discoverable from the dashboard.",
            },
            "cycles": [
                {
                    "round": 1,
                    "validation_review": {
                        "latest_review": "# Top Risks\n- Closed-loop pass recommends calmer intake guidance and clearer evidence sequencing.",
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        "complaint_generator.ui_ux_workflow.run_end_to_end_complaint_browser_audit",
        lambda **kwargs: {
            "command": ["pytest", "-q", str(kwargs.get("pytest_target") or "")],
            "returncode": 0,
            "artifact_count": 6,
            "screenshot_dir": str(kwargs.get("screenshot_dir") or ""),
            "stdout": "browser audit passed",
        },
    )

    app = create_review_surface_app(mediator=object())

    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            try:
                page.goto(f"{base_url}/workspace", wait_until="domcontentloaded")
                _wait_for_text(page, "#workspace-status", "Workspace synchronized for ")
                _wait_for_text(page, "#sdk-server-info", "did:key:")
                _wait_for_text(page, "#sdk-server-info", "complaint-workspace-mcp")
                _wait_for_text(page, "#tool-list", "complaint.generate_complaint")

                page.locator("#intake-party_name").fill("Jane Doe")
                page.locator("#intake-opposing_party").fill("Acme Corporation")
                page.locator("#intake-protected_activity").fill("Reported discrimination to HR")
                page.locator("#intake-adverse_action").fill("Termination two days later")
                page.locator("#intake-timeline").fill("Complaint on March 8, termination on March 10")
                page.locator("#intake-harm").fill("Lost wages and benefits")
                page.locator("#save-intake-button").click()
                _wait_for_text(page, "#workspace-status", "Intake answers saved.")
                _wait_for_text(page, "#next-question-label", "Intake complete.")

                page.get_by_role("button", name="Evidence", exact=True).click()
                page.locator("#evidence-kind").select_option("document")
                page.locator("#evidence-claim-element").select_option("causation")
                page.locator("#evidence-title").fill("Termination email")
                page.locator("#evidence-source").fill("Inbox export")
                page.locator("#evidence-content").fill("The termination followed the HR complaint within two days.")
                page.locator("#save-evidence-button").click()
                _wait_for_text(page, "#workspace-status", "Evidence saved and support review refreshed.")
                _wait_for_text(page, "#evidence-list", "Termination email")

                page.get_by_role("button", name="Draft", exact=True).click()
                page.locator("#draft-mode").select_option("template")
                page.locator("#draft-title").fill("Jane Doe v. Acme Corporation Complaint")
                page.locator("#requested-relief").fill("Back pay\nInjunctive relief")
                page.locator("#generate-draft-button").click()
                _wait_for_text(page, "#workspace-status", "Complaint draft generated from the deterministic template fallback.")
                _wait_for_text(page, "#draft-preview", "Jane Doe brings this retaliation complaint against Acme Corporation.")
                draft_body = page.locator("#draft-body").input_value()
                assert draft_body.startswith("IN THE UNITED STATES DISTRICT COURT")
                assert "Jane Doe brings this retaliation complaint against Acme Corporation." in draft_body

                page.get_by_role("button", name="CLI + MCP", exact=True).click()
                _wait_for_text(page, "#tool-list", "complaint.review_case")
                assert "complaint-workspace session" in page.locator("body").inner_text()
                assert "complaint-mcp-server" in page.locator("body").inner_text()

                page.locator("[data-tab-target='ux-review']").click()
                page.locator("#ux-review-screenshot-dir").fill(str(workspace_root / "screens"))
                page.locator("#ux-review-output-path").fill(str(workspace_root / "reviews"))
                page.locator("#ux-review-iterations").fill("2")
                page.locator("#run-ux-review-button").click()
                _wait_for_text(page, "#workspace-status", "Iterative UI/UX review completed.")
                _wait_for_text(page, "#ux-review-summary", "Top Risks")
                _wait_for_text(page, "#ux-review-metadata", "iterations: 2")
                _wait_for_text(page, "#ux-review-stage-findings", "First-time complainants need calmer prompts")
                iterative_stage_text = page.locator("#ux-review-stage-findings").inner_text()
                assert "Markdown fallback should not replace structured intake guidance." not in iterative_stage_text
                assert "Markdown fallback should not replace structured evidence guidance." not in iterative_stage_text

                page.locator("#run-ux-closed-loop-button").click()
                _wait_for_text(page, "#workspace-status", "Closed-loop UI/UX optimization completed.")
                _wait_for_text(page, "#ux-review-summary", "Closed-loop pass recommends calmer intake guidance")
                _wait_for_text(page, "#ux-review-metadata", "rounds: 1")
                _wait_for_text(page, "#ux-review-stage-findings", "shared MCP SDK and optimizer path should remain discoverable")
                closed_loop_stage_text = page.locator("#ux-review-stage-findings").inner_text()
                assert "Markdown fallback should not replace the structured integration-discovery finding." not in closed_loop_stage_text

                page.locator("#run-browser-audit-button").click()
                _wait_for_text(page, "#workspace-status", "End-to-end complaint browser audit completed.")
                _wait_for_text(page, "#ux-review-summary", "6 screenshot artifacts")
                _wait_for_text(page, "#ux-review-metadata", "browser audit")
                _wait_for_text(page, "#ux-review-runs", "pytest -q")
            finally:
                browser.close()
