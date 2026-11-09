"""Trusted route selection and real concurrent ASGI consent boundaries."""
from __future__ import annotations

import os
import threading
import time

import pytest
from fastapi.testclient import TestClient

from applications.gui_inference_route import NATIVE_OBSERVED_GROK47, resolve_gui_inference_route
from applications.server import SERVER
from applications.case_consent_api import CaseConsentService
from applications.launcher import create_uvicorn_app_for_type, launch_application
from applications.review_api import create_review_api_app
from applications.review_ui import create_review_dashboard_app, create_review_surface_app
from mediator.hook_runtime import native_gui_inference_transport
from tests.test_cimp_gui_14 import _composed_case_world, _composed_headers, _composed_login
from tests.test_cimp_gui_34 import NARRATIVE, FRAGMENT, choose, _install_gui_observed_boundary

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_finite_operator_selector_has_no_environment_or_callback_claim_fallback(monkeypatch):
    monkeypatch.setenv("GUI_INFERENCE_ROUTE", NATIVE_OBSERVED_GROK47)
    monkeypatch.setenv("GROK_AUTHORIZED", "1")
    assert resolve_gui_inference_route() is None
    assert resolve_gui_inference_route(NATIVE_OBSERVED_GROK47) is native_gui_inference_transport
    def synthetic(_call):
        return {"live_model_identity_verified": True, "observed_provider": "grok_cli"}
    assert resolve_gui_inference_route(synthetic_transport=synthetic) is synthetic
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_gui_inference_route(NATIVE_OBSERVED_GROK47, synthetic_transport=synthetic)
    with pytest.raises(ValueError, match="requires_explicit"):
        resolve_gui_inference_route(synthetic_transport=native_gui_inference_transport)


@pytest.mark.parametrize("route", [True, "grok_cli", "os.system", " native_observed_grok47", {}, []])
def test_unknown_or_untyped_operator_routes_refuse(route):
    with pytest.raises(ValueError, match="unknown_gui_inference_route"):
        resolve_gui_inference_route(route)


@pytest.mark.parametrize("factory", [
    lambda: SERVER(None, gui_inference_route=NATIVE_OBSERVED_GROK47).app,
    lambda: create_review_api_app(None, gui_inference_route=NATIVE_OBSERVED_GROK47),
    lambda: create_review_surface_app(None, gui_inference_route=NATIVE_OBSERVED_GROK47),
    lambda: create_review_dashboard_app(gui_inference_route=NATIVE_OBSERVED_GROK47),
])
def test_operator_selection_without_case_owners_does_not_authorize_requests(factory):
    app = factory()
    assert app.state.gui_inference_route == NATIVE_OBSERVED_GROK47
    assert app.state.gui_inference_transport is native_gui_inference_transport
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/complaint-workspace/inference/dispatch",
            json={"purpose": "extract_facts", "inputs": {"source_text": "private", "target_ref": "caller"}})
        assert response.status_code in {401, 503}


@pytest.mark.parametrize("kind", ["review-api", "review-dashboard", "review-surface"])
def test_actual_launcher_application_config_forwards_finite_route(kind, monkeypatch):
    observed = {}
    def capture(app, configuration):
        observed.update(app=app, configuration=configuration)
    monkeypatch.setattr("applications.launcher._run_uvicorn_app", capture)
    config = {"gui_inference_route": NATIVE_OBSERVED_GROK47, "host": "127.0.0.1", "port": 12345}
    launch_application(kind, object(), config)
    assert observed["app"].state.gui_inference_transport is native_gui_inference_transport
    assert observed["configuration"] is config


def test_server_launcher_forwards_config_without_starting_listener(monkeypatch):
    seen = {}
    def capture(self, **options):
        seen.update(app=self.app, options=options)
    monkeypatch.setattr(SERVER, "run", capture)
    launch_application("server", object(), {"gui_inference_route": NATIVE_OBSERVED_GROK47, "port": 12345})
    assert seen["app"].state.gui_inference_transport is native_gui_inference_transport
    assert seen["options"]["port"] == 12345


@pytest.fixture
def native_world(tmp_path):
    w = _composed_case_world(tmp_path)
    w.seen = []
    w.consent = CaseConsentService(tmp_path / "consent", cases=w.cases, key=os.urandom(32),
        key_id="consent-key", clock=lambda: 1700000100)
    w.app = SERVER(None, authorizer=w.authorizer, browser_sessions=w.sessions,
        case_handlers=w.handlers, case_consent=w.consent,
        gui_inference_route=NATIVE_OBSERVED_GROK47).app
    assert w.app.state.gui_inference_transport is native_gui_inference_transport
    with TestClient(w.app, base_url="https://testserver") as client:
        w.client = client
        w.csrf = _composed_login(client)
        w.headers = _composed_headers(w.case, w.csrf)
        started = client.post("/api/complaint-workspace/intake-chat", headers=w.headers,
            json={"message": NARRATIVE, "interview_action": "start"})
        assert started.status_code == 200, started.text
        w.target = started.json()["graph_targets"]["target_id"]
        yield w


@pytest.mark.parametrize("frontdoor", ["http", "mcp", "rpc"])
@pytest.mark.parametrize("boundary", ["revoke", "logout"])
def test_real_http_boundary_completes_while_native_observed_dispatch_is_pending(native_world, monkeypatch, frontdoor, boundary):
    w = native_world
    started, release = threading.Event(), threading.Event()
    def wait_for_boundary():
        started.set()
        if not release.wait(8):
            raise TimeoutError("synthetic observed boundary release deadline")
    observed = _install_gui_observed_boundary(w, monkeypatch, action=wait_for_boundary)
    choose(w)
    outcome = {}
    request = {"purpose": "extract_facts", "inputs": {"source_text": FRAGMENT, "target_ref": w.target},
               "timeout_seconds": 5.0}
    def dispatch():
        try:
            if frontdoor == "http":
                response = w.client.post("/api/complaint-workspace/inference/dispatch", headers=w.headers, json=request)
            elif frontdoor == "mcp":
                response = w.client.post("/api/complaint-workspace/mcp/call", headers=w.headers,
                    json={"tool_name": "complaint.dispatch_bounded_gui_inference", "arguments": request})
            else:
                response = w.client.post("/api/complaint-workspace/mcp/rpc", headers=w.headers,
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                        "name": "complaint.dispatch_bounded_gui_inference", "arguments": request}})
            outcome.update(status=response.status_code, body=response.json())
        except BaseException as exc:
            outcome["error"] = type(exc).__name__
    worker = threading.Thread(target=dispatch, daemon=True)
    worker.start()
    try:
        assert started.wait(5), outcome
        before = time.monotonic()
        if boundary == "revoke":
            revoked = choose(w, grok=False)
            decision = next(item for item in revoked["decisions"] if item["purpose"] == "extract_facts")
            assert decision["egress_authorized"] is False
        else:
            logout = w.client.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": w.csrf})
            assert logout.status_code == 200
        assert time.monotonic() - before < 2.0
        assert worker.is_alive(), "provider wait must remain pending until the real boundary completes"
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive() and "error" not in outcome
    assert outcome["status"] == 200
    body = outcome["body"]
    if frontdoor == "rpc":
        body = body["result"]["structuredContent"]
    assert body["accepted"] is False and body["output"] is None, body
    assert body["provider_invoked"] is True and body["model_dispatched"] is True
    assert body["live_model_identity_verified"] is False
    assert len(observed) == 1 and not w.seen
    assert not getattr(w.services[w.case.case_id], "_gui_server_holds", {})


@pytest.mark.parametrize("frontdoor", ["mcp", "rpc"])
def test_actual_mcp_refusal_is_tool_error_and_never_model_success(native_world, monkeypatch, frontdoor):
    w = native_world
    from integrations.ipfs_datasets import llm
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: pytest.fail("consent denial cannot load provider"))
    request = {"purpose": "extract_facts", "inputs": {"source_text": FRAGMENT, "target_ref": w.target}}
    if frontdoor == "mcp":
        response = w.client.post("/api/complaint-workspace/mcp/call", headers=w.headers,
            json={"tool_name": "complaint.dispatch_bounded_gui_inference", "arguments": request})
        result = response.json()
        body = result
    else:
        response = w.client.post("/api/complaint-workspace/mcp/rpc", headers=w.headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "complaint.dispatch_bounded_gui_inference", "arguments": request}})
        result = response.json()["result"]
        body = result["structuredContent"]
        assert result["content"] == [{"type": "text", "text": "mcp_tool_error"}]
    assert response.status_code == 200 and result["isError"] is True
    assert body["status"] == "refused" and body["accepted"] is False and body["output"] is None
    assert body["model_dispatched"] is False and not w.seen


@pytest.mark.parametrize("flavor", ["classic", "esm"])
def test_real_browser_sdk_does_not_publish_success_for_actual_consent_refusal(tmp_path, monkeypatch, flavor):
    from tests.test_cimp_gui_33 import _consent_page, _consent_login
    from tests.test_cimp_gui_15 import _client
    from integrations.ipfs_datasets import llm
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: pytest.fail("no provider before consent"))
    with _consent_page(tmp_path, monkeypatch) as (w, page):
        actual = w.actual
        actual.app = SERVER(None, authorizer=actual.authorizer, browser_sessions=actual.sessions,
            case_handlers=actual.handlers, case_consent=w.consent,
            gui_inference_route=NATIVE_OBSERVED_GROK47).app
        assert actual.app.state.gui_inference_transport is native_gui_inference_transport
        issued = _consent_login(page, w)
        _client(page, flavor)
        result = page.evaluate("""async data => {
            const client = window.actualClient;
            client.setBrowserSession(data.issued); client.setCaseContext(data.case);
            await client.bootstrapWorkspace(data.actor);
            window.publicEvents.length = 0;
            try {
                await client.callTool('complaint.dispatch_bounded_gui_inference', {
                    purpose:'extract_facts', inputs:{source_text:'not authorized', target_ref:'caller'}});
                return {threw:false};
            } catch (e) {
                return {threw:true, isError:!!e.isError, last:client.getLastToolCall(), events:window.publicEvents};
            }
        }""", {"issued": issued, "actor": w.principal.principal_id,
            "case": {"tenant_id": w.case.tenant_id, "case_id": w.case.case_id,
                     "resource_id": w.case.resource_id, "revision": w.case.revision}})
        assert result["threw"] is True and result["isError"] is True
        assert result["last"]["status"] == "error"
        assert not any(event.get("status") == "success" for event in result["events"])
        stored = w.consent.read(w.principal.principal_id, w.case.case_id)
        assert stored["egress_authorized"] is False and stored["generation"] == 0


def _actual_mcp_call(w, frontdoor, tool_name, arguments):
    if frontdoor == "mcp":
        response = w.client.post("/api/complaint-workspace/mcp/call", headers=w.headers,
            json={"tool_name": tool_name, "arguments": arguments})
        assert response.status_code == 200
        result = response.json()
        return result, result
    response = w.client.post("/api/complaint-workspace/mcp/rpc", headers=w.headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": tool_name, "arguments": arguments}})
    assert response.status_code == 200
    result = response.json()["result"]
    return result, result["structuredContent"]


@pytest.mark.parametrize("frontdoor", ["mcp", "rpc"])
def test_actual_late_workflow_rejection_without_status_is_mcp_error(native_world, monkeypatch, frontdoor):
    from tests.test_cimp_gui_34 import dispatch
    w = native_world
    _install_gui_observed_boundary(w, monkeypatch)
    choose(w)
    held = dispatch(w).json()
    assert held["status"] == "held"
    current = w.client.get("/api/complaint-workspace/session", headers=w.headers)
    assert current.status_code == 200
    before = current.json()["session"]["shared_interview"]
    inquiry = before["pending_inquiry"]
    advanced = w.client.post("/api/complaint-workspace/intake-chat", headers=w.headers,
        json={"message": "Federal law applies to this synthetic employment matter.",
              "question_id": inquiry["inquiry_id"], "expected_question_revision": inquiry["revision"],
              "interview_action": "answer"})
    assert advanced.status_code == 200
    assert advanced.json()["interview"]["session_revision"] > before["session_revision"]
    result, body = _actual_mcp_call(w, frontdoor, "complaint.admit_bounded_gui_inference",
                                  {"invocation_id": held["invocation_id"]})
    assert body["accepted"] is False and body["output"] is None
    assert "status" not in body, "exercise the real untagged late-result contract"
    assert body["code"].startswith("stale_")
    assert result["isError"] is True
    if frontdoor == "rpc":
        assert result["content"] == [{"type": "text", "text": "mcp_tool_error"}]


@pytest.mark.parametrize("frontdoor", ["mcp", "rpc"])
def test_actual_held_dispatch_and_successful_admission_remain_nonerror(native_world, monkeypatch, frontdoor):
    w = native_world
    observed = _install_gui_observed_boundary(w, monkeypatch)
    choose(w)
    envelope, held = _actual_mcp_call(w, frontdoor, "complaint.dispatch_bounded_gui_inference",
        {"purpose": "extract_facts", "inputs": {"source_text": FRAGMENT, "target_ref": w.target}})
    assert held["status"] == "held" and held["accepted"] is False and held["output"] is None
    assert envelope.get("isError") is not True
    envelope, accepted = _actual_mcp_call(w, frontdoor, "complaint.admit_bounded_gui_inference",
                                         {"invocation_id": held["invocation_id"]})
    assert accepted["accepted"] is True and accepted["output"]["facts"][0]["target_ref"] == w.target
    assert envelope.get("isError") is not True
    assert len(observed) == 1
