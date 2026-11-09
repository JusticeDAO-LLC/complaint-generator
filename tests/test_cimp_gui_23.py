"""Factual graph inspector renders authorized projection data only.

Positive cases show list and graph views, source details, revision diffs, and
contradiction links from the live case read. Negative cases refuse fabricated
support, hidden unresolved nodes, and fact copies in storage or analytics.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest
from fastapi.testclient import TestClient

from applications.review_ui import attach_static_asset_routes
from applications.site_ui import attach_core_site_ui_routes
from tests.test_cimp_gui_14 import NARRATIVE, _composed_case_world, _composed_headers, _composed_login

ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "static" / "complaint_graph_view.js"
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
SECRET = "Synthetic private fact that must stay inside the case view."


def _headers(case, csrf):
    return _composed_headers(case, csrf)


def _app(tmp_path):
    world = _composed_case_world(tmp_path)
    attach_static_asset_routes(world.app)
    attach_core_site_ui_routes(world.app)
    return world


def test_markup_keeps_support_unresolved_and_revision_text_from_the_payload():
    payload = {
        "case_id": "synthetic-case",
        "read_only": True,
        "user_statements": [{
            "kind": "user_statement", "text": "Synthetic arrival was nine.",
            "immutable_source_id": "src-nine", "assertion_id": "assert-nine",
            "source_identity": "message:nine", "provenance_status": "verified",
            "activity_status": "active", "authority": "user",
            "authority_is_user_fact": True, "admitted_user_fact": True,
        }],
        "hypotheses": [{
            "kind": "hypothesis", "text": "Synthetic model guess.",
            "immutable_source_id": "src-guess", "assertion_id": "assert-guess",
            "provenance_status": "unverified", "activity_status": "unverified",
            "authority": "hypothesis", "authority_is_user_fact": True, "admitted_user_fact": True,
        }],
        "allegations": [],
        "evidence_revisions": [],
        "revisions": [{
            "action": "supersede", "event_id": "event-1", "provenance_status": "verified",
            "previous_assertion_id": "assert-nine", "new_assertion_id": "assert-ten",
        }],
        "unresolved_conflicts": [{"action": "conflict", "assertion_ids": ["assert-ten", "assert-eight"], "status": "unresolved"}],
        "unresolved": [{"kind": "gap", "reason": "missing_immutable_source_id"}],
        "limitations": ["projection_is_read_only"],
        "client_support": {"assert-guess": True},
    }
    script = r'''
const view = require(process.argv[1]);
const payload = JSON.parse(process.argv[2]);
const html = view.renderFactualGraphInspector({innerHTML:"", dataset:{}}, payload, {hideUnresolved:true});
if (!html.includes('data-role="list-view"') || !html.includes('data-role="graph-view"')) process.exit(2);
if (!html.includes('data-role="source-details"') || !html.includes('src-nine')) process.exit(3);
if (!html.includes('data-role="revision-diff"') || !html.includes('Synthetic arrival was nine.')) process.exit(4);
if (!html.includes('data-role="contradiction-link"') || !html.includes('assert-ten')) process.exit(5);
if (!html.includes('data-role="unresolved-node"') || !html.includes('missing_immutable_source_id')) process.exit(6);
if (!html.includes('data-unresolved-hidden="false"') || !html.includes('data-hide-request-ignored="true"')) process.exit(7);
const hypothesis = html.split('Synthetic model guess.')[1] || "";
if (hypothesis.slice(0, 400).includes('data-support="true"')) process.exit(8);
if (view.fabricateGraphSupport().reason !== "client_cannot_fabricate_support") process.exit(9);
if (view.hideUnresolvedNodes().hidden !== false) process.exit(10);
if (view.persistPrivateFacts().stored !== false || view.reportAnalytics().stored !== false) process.exit(11);
if (view.authorizedFactualPath("../analytics") !== "") process.exit(12);
const law = view.renderLawDerivedDependencyGraph({innerHTML:""}, {requirements:[], factual_links:[], rejected_narratives:[]});
if (!law.includes('data-role="law-derived-dependency-graph"')) process.exit(13);
process.stdout.write("ok");
'''
    completed = subprocess.run(["node", "-e", script, str(VIEW), json.dumps(payload)], cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0 and completed.stdout == "ok", completed.stderr
    page = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    assert 'id="factual-graph-inspector"' in page
    assert "/static/complaint_graph_view.js" in page
    assert "localStorage" not in (ROOT / "static" / "complaint_graph_view.js").read_text(encoding="utf-8")


def test_http_projection_is_what_the_inspector_renders(tmp_path):
    world = _app(tmp_path)
    case = world.case
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        started = client.post("/api/complaint-workspace/intake-chat", headers=_headers(case, csrf),
                              json={"message": NARRATIVE, "interview_action": "start"})
        assert started.status_code == 200, started.text
        path = f"/api/graphs/{case.case_id}/factual"
        current = client.get(path, headers=_headers(case, csrf))
        assert current.status_code == 200, current.text
        body = current.json()
        revision = body["factual_review_revision"]
        proposed = client.post(path + "/reviews", headers=_headers(case, csrf), json={
            "review_action": "propose", "text": "Synthetic owner hypothesis about the schedule.",
            "origin": "model", "event_id": "synthetic-gui23-propose", "expected_graph_revision": revision,
        })
        assert proposed.status_code == 200, proposed.text
        admitted = client.post(path + "/reviews", headers=_headers(case, csrf), json={
            "review_action": "admit", "proposal_id": proposed.json()["proposal_id"],
            "source_text": "Synthetic admitted schedule change.", "message_id": "synthetic-gui23-admit",
            "event_id": "synthetic-gui23-admit", "expected_graph_revision": proposed.json()["graph_revision"], "text": "",
        })
        assert admitted.status_code == 200, admitted.text
        superseded = client.post(path + "/reviews", headers=_headers(case, csrf), json={
            "review_action": "supersede", "source_text": "Synthetic corrected arrival was ten.",
            "message_id": "synthetic-gui23-supersede", "target_stable_id": admitted.json()["stable_id"],
            "event_id": "synthetic-gui23-supersede", "expected_graph_revision": admitted.json()["graph_revision"], "origin": "user",
        })
        assert superseded.status_code == 200, superseded.text
        replacement = superseded.json()["stable_id"]
        current_revision = superseded.json()["graph_revision"]
        conflict = client.post(path + "/reviews", headers=_headers(case, csrf), json={
            "review_action": "contradict", "source_text": SECRET,
            "message_id": "synthetic-gui23-conflict", "target_stable_id": replacement,
            "event_id": "synthetic-gui23-conflict", "expected_graph_revision": current_revision, "origin": "user",
        })
        assert conflict.status_code == 200, conflict.text
        projected = client.get(path, headers=_headers(case, csrf))
        assert projected.status_code == 200, projected.text
        payload = projected.json()
        assert payload["unresolved_conflicts"]
        script = r'''
const view = require(process.argv[1]);
const payload = JSON.parse(process.argv[2]);
const html = view.factualInspectorMarkup(payload);
if (!html.includes(payload.case_id)) process.exit(2);
if (!html.includes("data-role=\"revision-diff\"")) process.exit(3);
if (!html.includes("data-role=\"contradiction-link\"")) process.exit(4);
const supported = html.split('data-support="true"').length - 1;
const authorized = payload.user_statements.filter(item => item.authority_is_user_fact === true && item.admitted_user_fact === true && item.activity_status === "active").length;
if (supported !== authorized * 2) process.exit(5);
process.stdout.write("ok");
'''
        completed = subprocess.run(["node", "-e", script, str(VIEW), json.dumps(payload)], cwd=ROOT, capture_output=True, text=True, timeout=15)
        assert completed.returncode == 0 and completed.stdout == "ok", completed.stderr
        denied = client.get(path, headers=_headers(world.second, csrf))
        assert denied.status_code == 403
        assert SECRET not in denied.text


def test_browser_script_loads_only_the_authorized_get_and_drops_denied_facts(tmp_path):
    """The workspace script is what the browser runs.

    Playwright and Chromium are not installed in this validation environment,
    so this case executes that script against the live projection instead of
    claiming a Chromium DOM pipe. WebSocket and SSE remain unqualified.
    """
    world = _app(tmp_path)
    case = world.case
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        assert client.post("/api/complaint-workspace/intake-chat", headers=_headers(case, csrf),
                           json={"message": NARRATIVE, "interview_action": "start"}).status_code == 200
        path = f"/api/graphs/{case.case_id}/factual"
        payload = client.get(path, headers=_headers(case, csrf)).json()
        denied = client.get(path, headers=_headers(world.second, csrf))
        assert denied.status_code == 403
    script = r'''
const view = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const calls = [];
const fetchImpl = async (url, options) => {
  const method = (options && options.method) || "GET";
  calls.push({url: String(url), method});
  if (method !== "GET" || String(url) !== input.path) return {ok: false, status: 403, json: async () => input.denied};
  return {ok: true, status: 200, json: async () => input.payload};
};
const mount = {innerHTML: "", dataset: {}};
(async () => {
  const loaded = await view.loadAuthorizedFactualGraph(mount, {caseId: input.caseId, fetchImpl, headers: input.headers});
  if (!loaded.ok || !mount.innerHTML.includes(input.narrative)) process.exit(2);
  if (!mount.innerHTML.includes('data-role="source-details"')) process.exit(3);
  const leaked = await view.loadAuthorizedFactualGraph(mount, {
    caseId: input.caseId, fetchImpl, analyticsUrl: "https://example.invalid/collect", clientSupport: {forced: true}});
  if (leaked.reason !== "private_boundary" || mount.innerHTML.includes(input.narrative)) process.exit(4);
  const posted = await view.loadAuthorizedFactualGraph(mount, {caseId: input.caseId, fetchImpl, method: "POST"});
  if (posted.reason !== "unauthorized_graph_request") process.exit(5);
  const foreign = await view.loadAuthorizedFactualGraph(mount, {caseId: input.caseId, fetchImpl: async () => ({ok: false, status: 403, json: async () => input.denied})});
  if (foreign.reason !== "graph_read_denied" || mount.innerHTML.includes(input.narrative) || !mount.innerHTML.includes("graph_read_denied")) process.exit(6);
  if (calls.some(call => call.method !== "GET" || call.url.includes("example.invalid") || !call.url.endsWith("/factual"))) process.exit(7);
  if (view.persistPrivateFacts(input.narrative).stored !== false) process.exit(8);
  process.stdout.write("ok");
})().catch(error => { console.error(error); process.exit(9); });
'''
    completed = subprocess.run(
        ["node", "-e", script, str(VIEW), json.dumps({
            "caseId": case.case_id, "path": f"/api/graphs/{case.case_id}/factual",
            "payload": payload, "denied": denied.json(), "narrative": NARRATIVE, "headers": _headers(case, csrf),
        })],
        cwd=ROOT, capture_output=True, text=True, timeout=15,
    )
    assert completed.returncode == 0 and completed.stdout == "ok", completed.stderr
