"""Measure rendering and large-evidence interface budgets.

Synthetic case, evidence, fact, annotation, and message volumes stay
paginated. Detail text is loaded for the selection, provenance stays
reachable, and request guards keep their existing deadlines.
"""

from __future__ import annotations

import os

import pytest
from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pathlib import Path

from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "static"
PAGE_SIZE = 24
EVIDENCE_COUNT = 72
FACT_COUNT = 60
CONTRADICTION_COUNT = 30
MESSAGE_COUNT = 48
ANNOTATION_COUNT = 36
CASE_COUNT = 40

_STATE = {"evidence_locked": False, "messages_locked": False, "preview_calls": 0}


def _evidence_items():
    return [
        {
            "evidence_id": f"ev-{index:03d}",
            "original_filename": f"memo-{index:03d}.txt",
            "source_filename": f"memo-{index:03d}.txt",
            "ingestion_status": "sealed",
            "media_type": "text/plain",
            "current_version": 1,
            "artifact_versions": [{"version": 1, "recorded_at": "2024-02-02T00:00:00Z"}],
            "actor_principal_id": "actor-ux48",
            "integrity_verified": True,
            "notes": [{"actor_principal_id": "actor-ux48", "note": f"note-{index:03d}"}],
        }
        for index in range(EVIDENCE_COUNT)
    ]


def _facts():
    rows = []
    for index in range(FACT_COUNT):
        day = (index % 27) + 1
        rows.append({
            "assertion_id": f"fact-{index:03d}",
            "text": f"On 2024-01-{day:02d} the witness recorded fact {index:03d}",
            "admitted_user_fact": True,
            "activity_status": "recorded",
            "source_provenance": {
                "source_id": f"src-{index:03d}",
                "extractor_version": "extractor-ux48",
                "verified": False,
                "source_span": {"text": f"span-{index:03d}"},
            },
        })
    conflicts = [
        {"assertion_ids": [f"fact-{index:03d}", f"fact-{index + 1:03d}"]}
        for index in range(CONTRADICTION_COUNT)
    ]
    return {
        "status": "projected",
        "case_id": "case-ux48",
        "graph_id": "graph-ux48",
        "user_statements": rows,
        "adopted_evidence": [],
        "contradictions": conflicts,
    }


def _messages():
    return [
        {
            "id": f"msg-{index:03d}",
            "author": "owner-ux48",
            "subject": f"Subject {index:03d}",
            "body": f"message-body-{index:03d}",
            "provenance": f"thread-ux48:{index:03d}",
        }
        for index in range(MESSAGE_COUNT)
    ]


def _annotations():
    return [
        {
            "annotation_id": f"ann-{index:03d}",
            "kind": "page_span",
            "note": f"annotation-note-{index:03d}",
            "anchor": f"page-1-span-{index}",
            "actor_principal_id": "actor-ux48",
            "artifact_version": 1,
            "annotation_revision": "rev-ux48",
        }
        for index in range(ANNOTATION_COUNT)
    ]


def _cases():
    return [{"case_id": f"case-{index:03d}", "label": f"Case {index:03d}"} for index in range(CASE_COUNT)]


PAGE = """<!doctype html><html><body>
<main>
<div id="complaint-case-shell"></div>
<section id="evidence-library" data-state="empty" aria-label="Evidence library">
  <input id="evidence-library-search" type="search">
  <select id="evidence-library-status-filter"><option value=""></option></select>
  <button type="button" id="evidence-library-refresh">Refresh</button>
  <button type="button" id="evidence-library-clear">Clear</button>
  <button type="button" id="evidence-library-add">Add</button>
  <button type="button" id="evidence-library-show-list">List</button>
  <button type="button" id="evidence-library-show-detail">Detail</button>
  <p id="evidence-library-summary"></p>
  <div id="evidence-library-empty"></div>
  <div id="evidence-library-error" hidden><p id="evidence-library-error-detail"></p><button type="button" id="evidence-library-retry">Retry</button></div>
  <div id="evidence-library-locked" hidden><p id="evidence-library-locked-detail"></p><button type="button" id="evidence-library-unlock">Unlock</button></div>
  <div id="evidence-library-body">
    <div id="evidence-library-list" role="listbox" aria-label="Evidence artifacts"></div>
    <article id="evidence-library-detail">
      <h3 id="evidence-detail-title"></h3>
      <p id="evidence-detail-status"></p>
      <p id="evidence-detail-source"></p>
      <p id="evidence-detail-dates"></p>
      <p id="evidence-detail-notes"></p>
      <p id="evidence-detail-classification"></p>
      <p id="evidence-detail-links"></p>
    </article>
  </div>
</section>
<section id="complaint-facts">
  <button type="button" id="complaint-facts-mode-list" data-facts-mode="list">List</button>
  <button type="button" id="complaint-facts-mode-timeline" data-facts-mode="timeline">Timeline</button>
  <button type="button" id="complaint-facts-mode-graph" data-facts-mode="graph">Graph</button>
  <button type="button" id="complaint-facts-refresh">Refresh</button>
  <p id="complaint-facts-status"></p>
  <ul id="complaint-facts-questions"></ul>
  <div id="complaint-facts-empty"></div>
  <div id="complaint-facts-error" hidden></div>
  <div id="complaint-facts-locked" hidden></div>
  <ol id="complaint-facts-list"></ol>
  <ol id="complaint-facts-timeline" hidden></ol>
  <div id="complaint-facts-graph" data-role="facts-graph" hidden>
    <ol id="complaint-facts-graph-nodes"></ol>
    <ul id="complaint-facts-graph-links"></ul>
  </div>
  <article id="complaint-facts-provenance" tabindex="-1" hidden>
    <h3 id="complaint-facts-provenance-title"></h3>
    <p id="complaint-facts-source"></p>
    <p id="complaint-facts-version"></p>
    <p id="complaint-facts-span"></p>
    <p id="complaint-facts-uncertainty"></p>
    <p id="complaint-facts-corroboration"></p>
    <p id="complaint-facts-target"></p>
    <input id="complaint-facts-graph-revision">
    <input id="complaint-facts-session-revision">
    <button type="button" id="complaint-facts-correct">Correct</button>
    <button type="button" id="complaint-facts-unknown">Unknown</button>
    <button type="button" id="complaint-facts-close">Close</button>
    <p id="complaint-facts-edit-status"></p>
  </article>
</section>
<form id="evidence-annotation-form"></form>
<ul id="evidence-annotation-saved"></ul>
<div id="docket-annotation-list"></div>
</main>
<script src="/static/complaint_case_shell.js"></script>
<script src="/static/complaint_evidence.js"></script>
<script src="/static/complaint_facts.js"></script>
</body></html>"""


def _app() -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

    @app.get("/workspace")
    def workspace():
        return HTMLResponse(PAGE)

    @app.get("/api/complaint-workspace/auth/session")
    def signed_out():
        return JSONResponse(status_code=401, content={"error": "session_required", "authenticated": False})

    @app.get("/api/cases/session")
    def case_session():
        return {"cases": [], "actor_principal_id": ""}

    @app.get("/api/cases/assignments")
    def assignments():
        return {"assignments": [], "actor_principal_id": ""}

    @app.get("/api/cases/evidence")
    def evidence_catalog():
        if _STATE["evidence_locked"]:
            return JSONResponse(status_code=403, content={"error": "key_unavailable", "items": _evidence_items()})
        return {"items": _evidence_items()}

    @app.post("/api/cases/evidence/search")
    def evidence_search():
        return {"items": [], "chronology": [], "authority": False, "plaintext_persisted": False, "index_is_authority": False}

    @app.get("/api/cases/evidence/preview")
    def evidence_preview(evidence_id: str = ""):
        _STATE["preview_calls"] += 1
        return {"preview_kind": "text", "accessible_text": evidence_id, "pages": []}

    @app.get("/api/complaint-workspace/factual-graph")
    def factual_graph():
        return _facts()

    @app.get("/api/complaint-workspace/session")
    def workspace_session():
        return {"adaptive_inquiry": {"preserved_gaps": [], "factual_correction": {}}}

    @app.get("/api/ux48/messages")
    def messages():
        if _STATE["messages_locked"]:
            return JSONResponse(status_code=403, content={"locked": True, "messages": [{"id": "secret", "body": "should-not-render", "subject": "hidden"}]})
        return {"omit": True, "messages": _messages()}

    @app.get("/api/ux48/annotations")
    def annotations():
        return {"omit": True, "items": _annotations()}

    @app.get("/api/ux48/cases")
    def cases():
        return {"cases": _cases()}

    @app.post("/api/ux48/mode")
    def mode(payload: dict = Body(...)):
        _STATE.update({key: bool(payload.get(key)) for key in ("evidence_locked", "messages_locked") if key in payload})
        return {"evidence_locked": _STATE["evidence_locked"], "messages_locked": _STATE["messages_locked"], "preview_calls": _STATE["preview_calls"]}

    return app


def _ids(page, selector):
    return page.evaluate(
        """(selector) => Array.from(document.querySelectorAll(selector)).map(node => node.getAttribute('data-evidence-id') || node.dataset.key || node.dataset.messageId || node.dataset.annotationId || node.dataset.assertionIds || '')""",
        selector,
    )


def test_large_volumes_page_without_dropping_provenance_or_guards(tmp_path, monkeypatch):
    assert browser._ASGI_REQUEST_SECONDS == 30
    assert browser._ASGI_THREAD_JOIN_SECONDS == 35
    shell_source = (STATIC_ROOT / "complaint_case_shell.js").read_text(encoding="utf-8")
    assert "deadlineMs: 8000" in shell_source
    assert "maxInFlight: 4" in shell_source
    denial = browser.probe_inherited_network_denial()
    if os.environ.get("UX48_ALLOW_UNFENCED") != "1":
        assert denial["af_unix_only"], "the trusted executor must fence this child"
    _STATE.update(evidence_locked=False, messages_locked=False, preview_calls=0)
    bridge = browser.SameOriginAsgiBridge(_app())
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux48-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        assert opened is not None and opened.status == 200
        page.wait_for_function("() => document.getElementById('complaint-case-shell').dataset.refreshState === 'settled'")
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        assert page.evaluate("() => window.complaintCaseShell.requestBudget()") == {
            "maxInFlight": 4,
            "maxQueued": 8,
            "deadlineMs": 8000,
        }
        page.evaluate(
            """() => {
                window.workspaceClient = {
                    caseContext: {tenant_id: 'tenant-ux48', case_id: 'case-ux48', resource_id: 'resource-ux48'},
                    _privacyActive: true,
                    _privacyEpoch: 1,
                    activePrincipalId: 'actor-ux48',
                    csrfToken: 'csrf-ux48',
                    _request: async (url) => {
                        const response = await fetch(url, {headers: {accept: 'application/json'}});
                        if (!response.ok) {
                            const error = new Error('unavailable');
                            error.code = 'unavailable';
                            throw error;
                        }
                        return response.json();
                    },
                };
            }"""
        )
        page.evaluate("() => window.complaintEvidenceLibrary.refresh()")
        page.wait_for_function("() => document.getElementById('evidence-library').dataset.state === 'ready'")
        page.wait_for_function("() => document.getElementById('evidence-library-page-status')")
        evidence_budget = page.evaluate("() => window.complaintEvidenceLibrary.budget()")
        assert evidence_budget["pageSize"] == PAGE_SIZE
        assert evidence_budget["total"] == EVIDENCE_COUNT
        assert evidence_budget["retained"] == EVIDENCE_COUNT
        assert evidence_budget["visible"] == PAGE_SIZE
        assert evidence_budget["pages"] == 3
        assert evidence_budget["omitted"] is False
        assert evidence_budget["guardsDisabled"] is False
        assert evidence_budget["requests"] >= 2
        assert evidence_budget["renders"] >= 1
        assert evidence_budget["lastRenderMs"] >= 0
        assert evidence_budget["domNodes"] > 0
        assert _STATE["preview_calls"] == 1
        first_page = _ids(page, "#evidence-library-list [data-evidence-id]")
        assert first_page[0] == "ev-000"
        assert len(first_page) == PAGE_SIZE
        assert "note-000" in page.locator("#evidence-detail-notes").inner_text()
        page.click("#evidence-library-page-next")
        second_page = _ids(page, "#evidence-library-list [data-evidence-id]")
        assert second_page[0] == "ev-024"
        assert len(second_page) == PAGE_SIZE
        assert _STATE["preview_calls"] == 1
        page.click("#evidence-library-list [data-evidence-id='ev-030']")
        page.wait_for_function("() => document.getElementById('evidence-detail-title').textContent.includes('memo-030')")
        assert "note-030" in page.locator("#evidence-detail-notes").inner_text()
        assert _STATE["preview_calls"] == 2
        page.focus("#evidence-library-page-next")
        page.keyboard.press("End")
        last_page = _ids(page, "#evidence-library-list [data-evidence-id]")
        assert last_page[-1] == "ev-071"
        assert len(last_page) == EVIDENCE_COUNT - (2 * PAGE_SIZE)
        seen = set(first_page + second_page + last_page)
        assert len(seen) == EVIDENCE_COUNT
        assert page.evaluate("() => window.complaintEvidenceLibrary.budget().visible") == len(last_page)

        page.evaluate("() => window.complaintFacts.refresh()")
        page.wait_for_function("() => document.getElementById('complaint-facts').dataset.state === 'ready'")
        fact_budget = page.evaluate("() => window.complaintFacts.budget()")
        assert fact_budget["total"] == FACT_COUNT
        assert fact_budget["contradictions"] == CONTRADICTION_COUNT
        assert fact_budget["retained"] == FACT_COUNT
        assert fact_budget["visible"] == PAGE_SIZE
        assert fact_budget["omitted"] is False
        assert fact_budget["corroborationFabricated"] is False
        assert fact_budget["requests"] == 2
        assert fact_budget["lastRenderMs"] >= 0
        page.click("#complaint-facts-list [data-assertion-id='fact-000']")
        assert page.locator("#complaint-facts-provenance").is_visible()
        assert page.locator("#complaint-facts-source").inner_text() == "src-000"
        assert page.locator("#complaint-facts-version").inner_text() == "extractor-ux48"
        assert page.locator("#complaint-facts-span").inner_text() == "span-000"
        assert page.locator("#complaint-facts-corroboration").inner_text() == "Not corroborated."
        page.focus("#complaint-facts-list [data-assertion-id='fact-000']")
        page.keyboard.press("ArrowDown")
        assert page.evaluate("() => document.activeElement.dataset.assertionId") == "fact-001"
        page.click("#complaint-facts-mode-graph")
        assert page.locator("#complaint-facts").get_attribute("data-mode") == "graph"
        assert page.locator("[data-role='facts-graph']").count() == 1
        graph_ids = []
        for _ in range(3):
            graph_ids.extend(_ids(page, "#complaint-facts-graph-links [data-role='contradiction']"))
            if page.locator("#complaint-facts-page-next").is_disabled():
                break
            page.click("#complaint-facts-page-next")
        assert len([row for row in graph_ids if row]) == CONTRADICTION_COUNT
        assert page.evaluate("() => document.getElementById('complaint-facts').dataset.graphWrites") == "0"
        assert page.evaluate("() => window.complaintFacts.budget().visible") <= PAGE_SIZE

        message_budget = page.evaluate("() => window.complaintCaseShell.loadMessages()")
        assert message_budget["total"] == MESSAGE_COUNT
        assert message_budget["retained"] == MESSAGE_COUNT
        assert message_budget["visible"] == PAGE_SIZE
        assert message_budget["requests"] == 1
        assert message_budget["omitted"] is False
        assert message_budget["locked"] is False
        assert message_budget["requestBudget"]["deadlineMs"] == 8000
        assert message_budget["lastRenderMs"] >= 0
        assert "message-body-000" not in page.locator("#complaint-case-shell-messages").inner_text()
        page.click("#complaint-case-shell-messages [data-message-id='msg-000']")
        assert page.locator("#complaint-case-shell-message-detail").inner_text() == "message-body-000"
        assert page.locator("#complaint-case-shell-message-detail").get_attribute("data-provenance") == "thread-ux48:000"
        page.click("#complaint-case-shell-message-next")
        assert page.locator("#complaint-case-shell-messages [data-message-id='msg-024']").count() == 1
        assert page.locator("#complaint-case-shell-messages [data-message-id='msg-047']").count() == 1
        assert page.locator("#complaint-case-shell-message-next").is_disabled()
        assert page.evaluate("() => window.complaintCaseShell.volumeBudget().visible") == PAGE_SIZE

        annotation_report = page.evaluate(
            """async () => {
                const response = await fetch('/api/ux48/annotations', {headers: {accept: 'application/json'}});
                const body = await response.json();
                window.complaintEvidenceAnnotations.recordAnnotations(body.items);
                const before = document.getElementById('evidence-annotation-saved').innerText;
                document.querySelector("#evidence-annotation-saved [data-annotation-id='ann-001']").click();
                const selected = document.getElementById('evidence-annotation-saved').innerText;
                document.getElementById('evidence-annotation-page-next').focus();
                document.getElementById('evidence-annotation-page-next').dispatchEvent(new KeyboardEvent('keydown', {key: 'End', bubbles: true}));
                return {
                    status: response.status,
                    beforeHasLateNote: before.includes('annotation-note-030'),
                    selectedHasNote: selected.includes('annotation-note-001'),
                    author: selected.includes('Author: actor-ux48'),
                    last: document.getElementById('evidence-annotation-saved').innerText.includes('ann-035') || document.body.innerText.includes('Annotation page-1-span-35'),
                    budget: window.complaintEvidenceAnnotations.budget(),
                };
            }"""
        )
        assert annotation_report["status"] == 200
        assert annotation_report["beforeHasLateNote"] is False
        assert annotation_report["selectedHasNote"] is True
        assert annotation_report["author"] is True
        assert annotation_report["budget"]["retained"] == ANNOTATION_COUNT
        assert annotation_report["budget"]["visible"] <= PAGE_SIZE
        assert annotation_report["budget"]["omitted"] is False
        assert annotation_report["budget"]["renders"] >= 1
        assert "ann-035" in page.locator("#evidence-annotation-saved").inner_text() or "page-1-span-35" in page.locator("#evidence-annotation-saved").inner_text()

        catalog = page.evaluate(
            """async () => {
                const response = await fetch('/api/ux48/cases', {headers: {accept: 'application/json'}});
                const body = await response.json();
                window.complaintCaseShell.renderCatalog(body.cases, 'case-010');
                const options = Array.from(document.querySelectorAll('#complaint-case-shell-catalog option')).map(option => option.value).filter(Boolean);
                return {count: options.length, selected: document.getElementById('complaint-case-shell-catalog').value, budget: window.complaintCaseShell.volumeBudget()};
            }"""
        )
        assert catalog["count"] == CASE_COUNT
        assert catalog["selected"] == "case-010"
        assert catalog["budget"]["catalogRetained"] == CASE_COUNT
        assert catalog["budget"]["catalogOptions"] == CASE_COUNT
        assert catalog["budget"]["omitted"] is False
        assert catalog["budget"]["requestBudget"]["deadlineMs"] == 8000

        locked = page.evaluate(
            """async () => {
                await fetch('/api/ux48/mode', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({evidence_locked: true, messages_locked: true})});
                await window.complaintEvidenceLibrary.refresh();
                const messages = await window.complaintCaseShell.loadMessages();
                window.complaintFacts.render({status: 'unavailable', error: 'key_unavailable', user_statements: [], contradictions: [], graph_id: ''}, null);
                return {
                    evidence: document.getElementById('evidence-library').dataset.state,
                    evidenceIds: document.querySelectorAll('#evidence-library-list [data-evidence-id]').length,
                    messages,
                    messageText: document.getElementById('complaint-case-shell-volume').innerText,
                    facts: document.getElementById('complaint-facts').dataset.state,
                    corroborated: document.querySelectorAll('#complaint-facts [data-corroborated="true"]').length,
                    budget: window.complaintFacts.budget(),
                };
            }"""
        )
        assert locked["evidence"] == "locked"
        assert locked["evidenceIds"] == 0
        assert locked["messages"]["locked"] is True
        assert locked["messages"]["visible"] == 0
        assert "should-not-render" not in locked["messageText"]
        assert locked["facts"] == "locked"
        assert locked["corroborated"] == 0
        assert locked["budget"]["total"] == 0
        assert locked["budget"]["corroborationFabricated"] is False
        assert page.evaluate("() => window.complaintCaseShell.requestBudget().deadlineMs") == 8000
        assert _STATE["preview_calls"] == 2
    finally:
        context.close()
        playwright.stop()
        observed = browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []
