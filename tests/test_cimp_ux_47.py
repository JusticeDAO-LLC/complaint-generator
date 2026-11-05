"""Bound interface requests and refuse stale results.

Case, actor, key, and consent changes abort queued and in-flight work.
A late payload is not published as completion. Request slots stay inside the
declared budget. The ASGI bridge still aborts unqualified origins, and owned
browser processes are reaped without raising the existing worker deadlines.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "static"
PAGE = """<!doctype html><html><body>
<main>
<div id="complaint-case-shell"></div>
<input id="message-text" value="">
</main>
<script src="/static/complaint_case_shell.js"></script>
<script src="/static/complaint_mcp_sdk.js"></script>
</body></html>"""


def _app(hold: threading.Event) -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

    @app.get("/workspace")
    def workspace():
        return HTMLResponse(PAGE)

    @app.get("/api/complaint-workspace/auth/session")
    def signed_out():
        return JSONResponse(status_code=401, content={"error": "session_required", "authenticated": False})

    @app.get("/api/ux47/hold")
    def hold_request():
        released = hold.wait(timeout=5)
        return {"status": "completed" if released else "unavailable", "late": True}

    @app.get("/api/ux47/missing")
    def missing():
        return JSONResponse(status_code=503, content={"error": "unavailable", "status": "unavailable"})

    return app


def test_sdk_budget_refuses_late_results_for_both_module_formats():
    node = __import__("shutil").which("node")
    if node is None:
        pytest.fail("Node.js is required to exercise interface request budgets")
    script = r"""
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const sdkPath = process.argv[2];
const sdk = sdkPath.endsWith('.mjs')
    ? await import(pathToFileURL(sdkPath).href)
    : createRequire(import.meta.url)(sdkPath);
assert.equal(sdk.MAX_BOUNDED_INFERENCE_RETRIES, 2);
assert.deepEqual(sdk.INTERFACE_REQUEST_BUDGET, {maxInFlight: 4, maxQueued: 8, deadlineMs: 8000});
const storage = new Map();
globalThis.localStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
};
let release;
const gate = new Promise(resolve => { release = resolve; });
let calls = 0;
const client = new sdk.ComplaintMcpClient({
    fetchImpl: (url, request) => new Promise((resolve, reject) => {
        calls += 1;
        const fail = () => reject(Object.assign(new Error('aborted'), {name: 'AbortError'}));
        if (request.signal.aborted) fail();
        else request.signal.addEventListener('abort', fail, {once: true});
        gate.then(() => resolve({ok: true, status: 200, json: async () => ({status: 'success', completed: true})}));
    }),
});
client.noteInterfaceBinding({actorId: 'actor-ux47', caseId: 'case-ux47', keyRevision: 'k1', consentRevision: 'c1'});
const budget = client.interfaceRequestView().budget;
const pending = [];
for (let index = 0; index < budget.maxInFlight + budget.maxQueued; index += 1) {
    pending.push(client._request('/api/complaint-workspace/session').then(
        () => ({ok: true}),
        error => ({ok: false, lifecycle: error.lifecycle, published: error.published, late: error.late === true}),
    ));
}
await new Promise(resolve => setTimeout(resolve, 30));
const queued = client.interfaceRequestView();
assert.equal(queued.inFlight, budget.maxInFlight);
assert.equal(queued.queued, budget.maxQueued);
assert.equal(calls, budget.maxInFlight);
assert.ok(queued.records.some(row => row.lifecycle === 'pending' && row.published === false));
const overflow = await client._request('/api/complaint-workspace/session').then(
    () => ({ok: true}),
    error => ({ok: false, lifecycle: error.lifecycle, published: error.published}),
);
assert.deepEqual(overflow, {ok: false, lifecycle: 'unavailable', published: false});
assert.equal(calls, budget.maxInFlight);
const before = client.getLastToolCall();
client.noteInterfaceBinding({actorId: 'actor-ux47', caseId: 'case-ux47', keyRevision: 'k2', consentRevision: 'c1'});
client.noteInterfaceBinding({actorId: 'actor-ux47-b', caseId: 'case-ux47', keyRevision: 'k2', consentRevision: 'c2'});
release();
const settled = await Promise.all(pending);
assert.ok(settled.every(row => row.ok === false && row.lifecycle === 'cancelled' && row.published === false));
const after = client.interfaceRequestView();
assert.equal(after.records.some(row => row.lifecycle === 'completed' && row.published === true), false);
assert.equal(client.getLastToolCall(), before);
const fresh = new sdk.ComplaintMcpClient({
    fetchImpl: async () => ({ok: true, status: 200, json: async () => ({result: {structuredContent: {status: 'ok'}}})}),
});
fresh.noteInterfaceBinding({actorId: 'actor-ux47', caseId: 'case-ux47', keyRevision: 'k1', consentRevision: 'c1'});
const completed = await fresh._request('/api/complaint-workspace/mcp/rpc', {method: 'POST', body: '{}'});
assert.equal(completed.result.structuredContent.status, 'ok');
assert.equal(fresh.interfaceRequestView().records.some(row => row.lifecycle === 'completed' && row.published === true), true);
console.log(JSON.stringify({calls, cancelled: settled.length, overflow: overflow.lifecycle}));
"""
    import subprocess
    for name in ("complaint_mcp_sdk.js", "complaint_mcp_sdk.mjs"):
        result = subprocess.run(
            [node, "--input-type=module", "-", str(ROOT / "static" / name)],
            input=script, text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report["calls"] == 4
        assert report["cancelled"] == 12
        assert report["overflow"] == "unavailable"


def test_shell_cancels_stale_work_and_reaps_the_browser(tmp_path, monkeypatch):
    assert browser._ASGI_REQUEST_SECONDS == 30
    assert browser._ASGI_THREAD_JOIN_SECONDS == 35
    sdk = (STATIC_ROOT / "complaint_mcp_sdk.js").read_text(encoding="utf-8")
    assert "const MAX_BOUNDED_INFERENCE_RETRIES = 2;" in sdk
    denial = browser.probe_inherited_network_denial()
    assert denial["af_unix_only"], "the trusted executor must fence this child"
    hold = threading.Event()
    app = _app(hold)
    bridge = browser.SameOriginAsgiBridge(app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux47-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        assert opened is not None and opened.status == 200
        page.wait_for_selector("#complaint-interface-requests")
        page.wait_for_function("() => document.getElementById('complaint-case-shell').dataset.refreshState === 'settled'")
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        budget = page.evaluate("() => window.complaintCaseShell.requestBudget()")
        assert budget == {"maxInFlight": 4, "maxQueued": 8, "deadlineMs": 8000}
        page.evaluate(
            """() => window.complaintCaseShell.noteInterfaceBinding({
                actor: 'actor-ux47', caseId: 'case-ux47', keyRevision: 'k1', consentRevision: 'c1'
            })"""
        )
        burst = page.evaluate(
            """async () => {
                const shell = window.complaintCaseShell;
                const budget = shell.requestBudget();
                const before = document.getElementById('complaint-interface-requests').dataset.completions;
                const jobs = [];
                for (let index = 0; index < budget.maxInFlight + budget.maxQueued + 1; index += 1) {
                    jobs.push(fetch('/api/ux47/hold').then(
                        async response => ({status: response.status, body: await response.json()}),
                        error => ({status: 0, name: error.name}),
                    ));
                }
                await new Promise(resolve => setTimeout(resolve, 50));
                const node = document.getElementById('complaint-interface-requests');
                const pending = {lifecycle: node.dataset.lifecycle, inFlight: node.dataset.inFlight, queued: node.dataset.queued, published: node.dataset.published};
                shell.noteInterfaceBinding({actor: 'actor-ux47', caseId: 'case-ux47', keyRevision: 'k1', consentRevision: 'c2'});
                shell.applyKeyCoherence({status: 'locked', epoch: 2, clear_plaintext: true, recovery_guidance: 'Unlock the key outside this page.'});
                const settled = await Promise.all(jobs);
                return {before, pending, settled, after: {
                    lifecycle: node.dataset.lifecycle,
                    published: node.dataset.published,
                    completions: node.dataset.completions,
                    lateRefused: node.dataset.lateRefused,
                }};
            }"""
        )
        assert burst["pending"]["lifecycle"] == "unavailable"
        assert burst["pending"]["published"] == "false"
        assert int(burst["pending"]["inFlight"]) == 4
        assert int(burst["pending"]["queued"]) == 8
        unavailable = [row for row in burst["settled"] if row.get("status") == 503]
        assert len(unavailable) == 1
        assert unavailable[0]["body"]["lifecycle"] == "unavailable"
        assert all(row.get("status") != 200 for row in burst["settled"])
        assert burst["after"]["published"] == "false"
        assert burst["after"]["lifecycle"] == "cancelled"
        assert burst["after"]["completions"] == burst["before"]
        refused = page.evaluate(
            """async () => {
                try {
                    await fetch('https://example.invalid/ux47');
                    return 'completed';
                } catch (error) {
                    return 'aborted';
                }
            }"""
        )
        assert refused == "aborted"
        assert bridge.aborted_external
        missing = page.evaluate(
            """async () => {
                const response = await fetch('/api/ux47/missing');
                const body = await response.json();
                const surface = document.getElementById('complaint-state-surface');
                return {status: response.status, error: body.error, kind: surface.dataset.kind, ready: surface.dataset.ready, verified: surface.dataset.verified};
            }"""
        )
        assert missing["status"] == 503
        assert missing["error"] == "unavailable"
        assert missing["kind"] == "unavailable"
        assert missing["ready"] == "false"
        assert missing["verified"] == "false"
    finally:
        hold.set()
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []
