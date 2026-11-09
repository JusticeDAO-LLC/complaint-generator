"""Graph, research, and collaboration errors stay distinct from confirmed states.

The workspace DOM uses the shared operation-surface entry points. Authorization,
conflict, unavailable, and pending states expose the current revisions and bounded
retry or cancel actions. A failed call, missing proof, unusable source, or queued
replica cannot be painted as ready, supported, or verified.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import FastAPI

from applications.review_ui import attach_static_asset_routes
from applications.site_ui import attach_core_site_ui_routes
from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

FORBIDDEN = ("ready", "supported", "verified")

_APPLY = """
(spec) => {
  const model = window.ComplaintOperationSurfaces.apply(spec.mount, spec.record);
  const node = document.getElementById(spec.mount);
  return {
    state: node.dataset.state,
    ready: node.dataset.ready,
    supported: node.dataset.supported,
    verified: node.dataset.verified,
    retry: node.dataset.retryRemaining,
    cancel: node.dataset.cancelEnabled,
    graph: node.dataset.graphRevision,
    session: node.dataset.sessionRevision,
    research: node.dataset.researchRevision,
    collaboration: node.dataset.collaborationRevision,
    text: node.textContent,
    classified: model.state,
    fallbackBlocked: model.fallbackBlocked,
  };
}
"""


@contextmanager
def _page(tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError(
            "Task 02 network fence is not active; Chromium cannot prove same-origin operation surfaces"
        )
    app = FastAPI()
    attach_static_asset_routes(app)
    attach_core_site_ui_routes(app)
    bridge = browser.SameOriginAsgiBridge(app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "operation-profile"
    profile.mkdir(mode=0o700)
    playwright = None
    context = None
    observed = set()
    try:
        playwright = browser._load_sync_playwright()().start()
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        browser._assert_process_custody(node, chromium, profile)
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(20000)
        yield page
    finally:
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"


def _assert_not_confirmed(view):
    assert view["ready"] == "false"
    assert view["supported"] == "false"
    assert view["verified"] == "false"
    lowered = view["text"].lower()
    for word in FORBIDDEN:
        assert word not in lowered
    assert view["fallbackBlocked"] is True or view["state"] in {"authorization", "conflict", "unavailable", "pending"}


def test_operation_surfaces_explain_states_and_bound_actions(tmp_path, monkeypatch):
    with _page(tmp_path, monkeypatch) as page:
        page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        page.wait_for_function("window.ComplaintOperationSurfaces && window.publishWorkspaceOperationSurface")
        rail = page.locator("#operation-error-rail")
        assert rail.get_attribute("data-task") == "CIMP-GUI-54"
        assert page.locator("#operation-error-graph").get_attribute("data-state") == "unavailable"
        assert page.locator("#operation-error-research").get_attribute("data-ready") == "false"
        assert page.locator("#operation-error-collaboration").get_attribute("data-verified") == "false"

        pending = page.evaluate(_APPLY, {
            "mount": "operation-error-collaboration",
            "record": {
                "surface": "collaboration",
                "status": "pending",
                "collaboration_revision": "col-4",
                "session_revision": "sess-9",
            },
        })
        assert pending["state"] == "pending"
        assert pending["cancel"] == "true"
        assert pending["retry"] == "3"
        assert pending["collaboration"] == "col-4"
        assert pending["session"] == "sess-9"
        assert "Pending" in pending["text"]
        page.locator("#operation-error-collaboration [data-operation-action='cancel']").click()
        cancelled = page.locator("#operation-error-collaboration")
        assert cancelled.get_attribute("data-state") == "unavailable"
        assert cancelled.get_attribute("data-cancel-enabled") == "false"
        assert "Cancelled" in cancelled.text_content()
        assert "col-4" in cancelled.text_content()
        assert cancelled.get_attribute("data-ready") == "false"

        conflict = page.evaluate(_APPLY, {
            "mount": "operation-error-graph",
            "record": {
                "surface": "graph",
                "status": "conflict",
                "code": "revision_conflict",
                "graph_revision": "g-12",
                "session_revision": "sess-3",
            },
        })
        assert conflict["state"] == "conflict"
        assert conflict["graph"] == "g-12"
        assert conflict["retry"] == "3"
        assert "Revision conflict" in conflict["text"]
        for _ in range(3):
            page.locator("#operation-error-graph [data-operation-action='retry']").click()
        exhausted = page.locator("#operation-error-graph")
        assert exhausted.get_attribute("data-retry-remaining") == "0"
        assert exhausted.locator("[data-operation-action='retry']").is_disabled()
        assert exhausted.get_attribute("data-graph-revision") == "g-12"
        assert exhausted.get_attribute("data-state") == "conflict"

        authorized = page.evaluate(_APPLY, {
            "mount": "operation-error-research",
            "record": {
                "surface": "research",
                "status": "authorization",
                "authorization_denied": True,
                "code": "authorization_denied",
                "research_revision": "r-2",
            },
        })
        assert authorized["state"] == "authorization"
        assert authorized["retry"] == "0"
        assert authorized["research"] == "r-2"
        assert page.locator("#operation-error-research [data-operation-action='retry']").is_disabled()
        assert "Authorization required" in authorized["text"]

        confirmed = page.evaluate(_APPLY, {
            "mount": "operation-error-graph",
            "record": {
                "surface": "graph",
                "status": "ready",
                "verified": True,
                "supported": True,
                "proof_present": True,
                "source_supported": True,
                "replica_status": "verified",
                "mcp_ok": True,
                "graph_revision": "g-20",
                "session_revision": "sess-20",
            },
        })
        assert confirmed["state"] == "ready"
        assert confirmed["ready"] == "true"
        assert confirmed["supported"] == "true"
        assert confirmed["verified"] == "true"
        assert confirmed["graph"] == "g-20"
        assert "Ready" in confirmed["text"]


def test_failed_calls_missing_proof_and_queued_replicas_stay_unconfirmed(tmp_path, monkeypatch):
    with _page(tmp_path, monkeypatch) as page:
        page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        page.wait_for_function("window.ComplaintOperationSurfaces")
        cases = [
            ("operation-error-graph", {
                "surface": "graph", "status": "ready", "verified": True, "supported": True,
                "mcp_failed": True, "mcp_ok": False, "graph_revision": "g-1", "session_revision": "s-1",
            }),
            ("operation-error-research", {
                "surface": "research", "status": "ready", "verified": True, "supported": True,
                "missing_proof": True, "proof_present": False, "proof_status": "not_executed",
                "research_revision": "r-1",
            }),
            ("operation-error-collaboration", {
                "surface": "collaboration", "status": "ready", "verified": True, "supported": True,
                "unsupported_source": True, "source_supported": False, "source_status": "unsupported",
                "collaboration_revision": "c-1",
            }),
            ("operation-error-graph", {
                "surface": "graph", "status": "pending", "verified": True, "supported": True,
                "queued_replica": True, "replica_status": "queued", "graph_revision": "g-2",
            }),
        ]
        for mount, record in cases:
            view = page.evaluate(_APPLY, {"mount": mount, "record": record})
            assert view["state"] == "unavailable"
            assert view["classified"] == "unavailable"
            assert view["fallbackBlocked"] is True
            _assert_not_confirmed(view)
            assert view["text"]
        assert "g-2" in page.locator("#operation-error-graph").text_content()
        assert page.locator("#operation-error-graph").get_attribute("data-state") != "ready"
        assert page.locator("#operation-error-research").get_attribute("data-supported") == "false"
        assert page.locator("#operation-error-collaboration").get_attribute("data-verified") == "false"
