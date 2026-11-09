"""Real Chromium SDK/workspace checks through the qualified HTTP-to-ASGI pipe.

The positive MCP fixture is explicitly a private synthetic trusted-local
operator surface. It proves SDK/service behavior, not production case admission.
Authentication/logout use the actual separately composed browser-session routes.
No DOM, fetch response, or MCP response is fabricated. WS/SSE are unqualified.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from applications.browser_sessions import BrowserSessionConfiguration, BrowserSessionService, PrincipalStoreCredentialAdapter
from applications.case_routes import compose_case_routes
from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import create_complaint_workspace_router
from applications.principal_store import PrincipalStore
from applications.review_ui import attach_static_asset_routes
from applications.site_ui import attach_core_site_ui_routes
from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
USER_ID = "synthetic-gui-15"
PASSPHRASE = "synthetic-gui-15-passphrase"
AUTH_TOKEN = "synthetic-auth-token"
MARKER = "Synthetic GUI15 narrative: On March 4, 2024 Alex Rivera fired me after I reported safety concerns."
PRIVATE_ERROR = "Jane Doe was evicted"
FALLBACK_DID = "did:key:fallback-" + "a" * 32


def _world(tmp_path, mode):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(USER_ID, USER_ID)
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="synthetic-principal-key")
    principal = principals.register_from_request({})
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {AUTH_TOKEN: principal.principal_id}),
        signing_key=os.urandom(32), ttl_seconds=120))
    auth = FastAPI()
    compose_case_routes(auth, authorizer=None, browser_sessions=sessions,
                        include_workspace=False, include_review=False, include_document=False)
    app = FastAPI()
    attach_static_asset_routes(app)
    attach_core_site_ui_routes(app)
    app.include_router(create_complaint_workspace_router(service,
        trusted_local=mode not in {"denied", "http403"},
        browser_sessions=sessions if mode == "http403" else None))
    calls = []
    async def application(scope, receive, send):
        captured = bytearray()
        async def tee():
            message = await receive()
            if message.get("type") == "http.request":
                captured.extend(message.get("body") or b"")
            return message
        target = auth if str(scope.get("path", "")).startswith("/api/complaint-workspace/auth/") else app
        await target(scope, tee, send)
        if str(scope.get("path", "")).endswith("/mcp/rpc"):
            calls.append(json.loads(bytes(captured)))
    return SimpleNamespace(service=service, sessions=sessions, principal=principal,
                           application=application, calls=calls)


def _typed_world(tmp_path):
    from tests.test_cimp_gui_14 import _composed_case_world
    actual = _composed_case_world(tmp_path)
    attach_static_asset_routes(actual.app)
    attach_core_site_ui_routes(actual.app)
    calls = []
    async def application(scope, receive, send):
        captured = bytearray()
        async def tee():
            message = await receive()
            if message.get("type") == "http.request":
                captured.extend(message.get("body") or b"")
            return message
        await actual.app(scope, tee, send)
        if captured and str(scope.get("path", "")).endswith("/mcp/rpc"):
            calls.append({"body": json.loads(bytes(captured)),
                          "headers": [(k.decode(), v.decode()) for k,v in scope["headers"]]})
    return SimpleNamespace(application=application, calls=calls, case=actual.case,
        principal=actual.owner, service=actual.services[actual.case.case_id], actual=actual)


@contextmanager
def _page(tmp_path, monkeypatch, mode="allowed"):
    assert browser.probe_inherited_network_denial()["af_unix_only"], "the trusted executor must fence this child"
    if mode == "http401":
        monkeypatch.setenv("COMPLAINT_MCP_AUTH_TOKEN", AUTH_TOKEN)
    else:
        monkeypatch.delenv("COMPLAINT_MCP_AUTH_TOKEN", raising=False)
    world = _typed_world(tmp_path) if mode == "typed_owner" else _world(tmp_path, mode)
    bridge = browser.SameOriginAsgiBridge(world.application)
    node, chromium = browser.pin_executables()
    profile = tmp_path / "real-browser-profile"
    profile.mkdir(mode=0o700)
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    playwright, context = None, None
    observed = set()
    try:
        playwright = browser._load_sync_playwright()().start()
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        browser._assert_process_custody(node, chromium, profile)
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(15000)
        page.goto(browser.SAME_ORIGIN + "/workspace?user_id=" + USER_ID, wait_until="domcontentloaded")
        page.wait_for_function("['ready', 'partial', 'denied', 'error'].includes(document.body.dataset.workspaceHydrated)")
        yield world, page
    finally:
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"


def _client(page, flavor):
    page.evaluate("""async flavor => {
        const sdk = flavor === 'esm' ? await import('/static/complaint_mcp_sdk.mjs') : window.ComplaintMcpSdk;
        window.actualSdk = sdk;
        window.actualClient = new sdk.ComplaintMcpClient({origin: location.origin});
        window.publicEvents = [];
        window.addEventListener('complaint-mcp-sync', e => window.publicEvents.push(e.detail));
        window.addEventListener('complaint-mcp-sdk-call', e => window.publicEvents.push(e.detail));
    }""", flavor)


def _login(page):
    issued = page.evaluate("""async credential => {
        const response = await fetch('/api/complaint-workspace/auth/login', {
            method: 'POST', credentials: 'same-origin', headers: {'content-type': 'application/json'},
            body: JSON.stringify({credential})});
        if (!response.ok) throw new Error('actual_login_failed_' + response.status);
        return await response.json();
    }""", AUTH_TOKEN)
    assert issued["authenticated"] is True and issued["csrf_token"]
    return issued


@pytest.mark.parametrize("flavor", ["classic", "esm"])
@pytest.mark.parametrize("mode,status", [("denied", None), ("http401", 401), ("http403", 403)])
def test_denied_is_error_bootstrap_never_reports_ready_or_synchronized(tmp_path, monkeypatch, flavor, mode, status):
    with _page(tmp_path, monkeypatch, mode) as (world, page):
        assert page.get_attribute("body", "data-workspace-hydrated") == "denied"
        assert all(word not in page.text_content("#workspace-status").lower() for word in ("ready", "synchron"))
        _client(page, flavor)
        if mode == "http403":
            _login(page)  # A real cookie without runtime CSRF must still fail.
        result = page.evaluate("""async user => {
            try { await window.actualClient.bootstrapWorkspace(user); return {threw:false}; }
            catch (e) { return {threw:true, isError:!!e.isError, denied:!!e.authorizationDenied,
                status:e.status || null, last:window.actualClient.getLastToolCall()}; }
        }""", USER_ID)
        assert result["threw"] and result["isError"] and result["denied"]
        if status is not None:
            assert result["status"] == status
        if result["last"]:
            assert result["last"]["status"] == "error"
        assert AUTH_TOKEN not in page.evaluate("JSON.stringify({...localStorage, ...sessionStorage})")
        assert world.calls or mode in {"http401", "http403"}


@pytest.mark.parametrize("flavor", ["classic", "esm"])
def test_revision_contract_redacts_storage_events_and_real_stale_conflict(tmp_path, monkeypatch, flavor):
    with _page(tmp_path, monkeypatch) as (world, page):
        assert page.get_attribute("body", "data-workspace-hydrated") in {"ready", "partial"}
        assert "synchronized" in page.text_content("#workspace-status").lower()
        _client(page, flavor)
        result = page.evaluate("""async data => {
            const client = window.actualClient;
            const started = await client.runIntakeChatTurn(data.user, data.marker, 'original_complaint', {interview_action:'start'});
            let stale;
            try { await client.runIntakeChatTurn(data.user, 'synthetic stale answer', started.pending_inquiry_id,
                {expected_question_revision:started.expected_question_revision + 9, interview_action:'answer'});
                stale = {threw:false};
            } catch(e) { stale = {threw:true, message:e.message, isError:!!e.isError,
                authorizationDenied:!!e.authorizationDenied, last:client.getLastToolCall()}; }
            const session = await client.getSession(data.user);
            const fallback = 'did:key:fallback-' + 'a'.repeat(32);
            const cachedFallback = client.cacheDid(fallback);
            const readFallback = client.getCachedDid();
            const rejectedCacheValues = [data.privateError, 'did:key:fallback-' + 'a'.repeat(31),
                'did:key:fallback-' + 'g'.repeat(32)].map(value => {
                    try { client.cacheDid(value); return false; } catch(e) { return true; }
                });
            localStorage.setItem(client.didStorageKey, data.privateError);
            const rejectedStoredPrivateText = client.getCachedDid() === null
                && localStorage.getItem(client.didStorageKey) === null;
            localStorage.setItem(client.didStorageKey, data.privateError);
            new window.actualSdk.ComplaintMcpClient({origin:location.origin});
            const constructorClearedLegacyDid = localStorage.getItem(client.didStorageKey) === null;
            const fallbackProjection = window.actualSdk.publishSyncEvent({event_type:'workspace.updated', user_id:fallback});
            const projected = window.actualSdk.publishSyncEvent({event_type:'workspace.updated',
                tool_name:'complaint.run_intake_chat_turn', expected_question_revision:{private:data.privateError},
                revision:{private:data.marker}, message:data.privateError,
                payload:{narrative:data.marker, token:data.token}});
            try { await client.callTool(data.privateError, {user_id:data.user, expected_question_revision:{private:data.privateError}}); } catch(e) {}
            return {started, stale, session, projected, fallback, cachedFallback, readFallback,
                rejectedCacheValues, rejectedStoredPrivateText, constructorClearedLegacyDid, fallbackProjection, events:window.publicEvents,
                last:client.getLastToolCall(), local:{...localStorage}, storedSession:{...sessionStorage}};
        }""", {"user": USER_ID, "marker": MARKER, "privateError": PRIVATE_ERROR, "token": AUTH_TOKEN})
        started = result["started"]
        assert started["interview_action"] == "start" and started["pending_inquiry_id"]
        assert type(started["expected_question_revision"]) is int
        assert result["cachedFallback"] == result["readFallback"] == result["fallback"]
        assert result["rejectedCacheValues"] == [True, True, True]
        assert result["rejectedStoredPrivateText"] is True
        assert result["constructorClearedLegacyDid"] is True
        assert result["fallbackProjection"]["user_id"] == result["fallback"]
        stale = result["stale"]
        assert stale["threw"] and stale["isError"] and not stale["authorizationDenied"]
        assert stale["message"] == "stale_question" and stale["last"]["status"] == "error"
        shared = result["session"]["session"]["shared_interview"]
        assert shared["pending_inquiry"]["inquiry_id"] == started["pending_inquiry_id"]
        assert shared["session_revision"] == started["interview"]["session_revision"]
        posted = [v.get("params", {}).get("arguments", {}) for v in world.calls if v.get("method") == "tools/call"]
        assert any(v.get("message") == MARKER and v.get("interview_action") == "start" for v in posted)
        assert any(v.get("expected_question_revision") == started["expected_question_revision"] + 9 and v.get("interview_action") == "answer" for v in posted)
        public = json.dumps({k:result[k] for k in ("events", "projected", "last", "local", "storedSession")})
        assert all(value not in public for value in (MARKER, PRIVATE_ERROR, AUTH_TOKEN))
        assert not isinstance(result["last"].get("expected_question_revision"), dict)
        assert not isinstance(result["projected"].get("revision"), dict)


def _seed_private(page):
    page.evaluate("""data => {
        localStorage.setItem('complaint-workspace-synopsis:' + data.user, data.marker);
        localStorage.setItem('complaintWorkspaceHandoff', JSON.stringify({summary:data.marker}));
        localStorage.setItem('complaintGenerator.did', data.did);
        sessionStorage.setItem('mcp-bearer-token', data.token);
        document.querySelector('#case-synopsis').value = data.marker;
        document.querySelector('#session-sync-summary').textContent = data.marker;
    }""", {"user": USER_ID, "marker": MARKER, "token": AUTH_TOKEN, "did": FALLBACK_DID})


def _assert_private_cleared(page):
    assert MARKER not in page.locator("body").text_content()
    assert MARKER not in page.locator("input,textarea").evaluate_all("nodes => JSON.stringify(nodes.map(n => n.value))")
    stored = page.evaluate("JSON.stringify({...localStorage, ...sessionStorage})")
    assert MARKER not in stored and AUTH_TOKEN not in stored


def test_real_workspace_clear_switch_and_verified_logout_remove_private_dom(tmp_path, monkeypatch):
    with _page(tmp_path, monkeypatch) as (world, page):
        issued = _login(page)
        page.evaluate("issued => window.workspaceClient.setBrowserSession(issued)", issued)
        _seed_private(page)
        page.locator("#workspace-clear-private-state").evaluate("node => node.click()")
        page.wait_for_function("document.body.dataset.workspaceHydrated === 'cleared'")
        _assert_private_cleared(page)
        assert page.evaluate("localStorage.getItem('complaintGenerator.did')") == FALLBACK_DID
        # Old SDK versions allowed arbitrary private text in the DID cache.
        # A clear boundary preserves only validated opaque identifiers.
        page.evaluate("value => localStorage.setItem('complaintGenerator.did', value)", MARKER)
        page.locator("#workspace-clear-private-state").evaluate("node => node.click()")
        _assert_private_cleared(page)
        assert page.evaluate("localStorage.getItem('complaintGenerator.did')") is None
        _seed_private(page)
        page.locator("#workspace-switch-user-id").evaluate("node => node.value = 'synthetic-gui-15-other'")
        page.locator("#workspace-switch-user").evaluate("node => node.click()")
        page.wait_for_function("document.body.dataset.workspaceHydrated === 'switched'")
        _assert_private_cleared(page)
        assert page.evaluate("localStorage.getItem('complaintGenerator.did')") is None
        page.evaluate("issued => window.workspaceClient.setBrowserSession(issued)", issued)
        _seed_private(page)
        page.locator("#workspace-logout").evaluate("node => node.click()")
        page.wait_for_function("document.body.dataset.workspaceHydrated === 'logged-out'")
        _assert_private_cleared(page)
        assert page.evaluate("async () => (await fetch('/api/complaint-workspace/auth/session', {credentials:'same-origin'})).status") == 401
        assert page.evaluate("localStorage.getItem('complaintGenerator.did')") is None
        assert all(word not in page.text_content("#workspace-status").lower() for word in ("ready", "synchron"))


@pytest.mark.parametrize("flavor", ["classic", "esm"])
def test_real_cookie_without_csrf_cannot_claim_server_logout(tmp_path, monkeypatch, flavor):
    with _page(tmp_path, monkeypatch) as (world, page):
        _login(page)
        _client(page, flavor)
        _seed_private(page)
        result = page.evaluate("""async () => {
            try { return {success:await window.actualClient.logout()}; }
            catch(e) { return {error:e.message}; }
        }""")
        assert result.get("error") == "csrf_required" and "success" not in result
        assert page.evaluate("async () => (await fetch('/api/complaint-workspace/auth/session', {credentials:'same-origin'})).status") == 200
        assert MARKER not in page.evaluate("JSON.stringify({...localStorage, ...sessionStorage})")


@pytest.mark.parametrize("flavor", ["classic", "esm"])
def test_typed_owner_cookie_case_scope_uses_actor_and_real_canonical_encrypted_service(tmp_path, monkeypatch, flavor):
    with _page(tmp_path, monkeypatch, "typed_owner") as (world, page):
        issued = page.evaluate("""async () => {
            const r=await fetch('/api/complaint-workspace/auth/login', {method:'POST', credentials:'same-origin',
              headers:{'content-type':'application/json'},body:JSON.stringify({credential:'synthetic-owner-credential'})});
            if(!r.ok) throw new Error('typed_owner_login_failed_'+r.status); return await r.json();
        }""")
        assert issued["principal_id"] == world.principal.principal_id
        assert world.case.tenant_id != issued["principal_id"]
        # The public page's initial unauthenticated bootstrap was denied.
        # Inspect only the explicitly authenticated, case-bound calls below.
        world.calls.clear()
        _client(page, flavor)
        result = page.evaluate("""async data => {
            const c=window.actualClient;
            c.setBrowserSession(data.issued);
            c.setCaseContext(data.case);
            const bootstrap=await c.bootstrapWorkspace(data.canonical);
            const started=await c.runIntakeChatTurn(data.canonical, data.marker, 'original_complaint', {interview_action:'start'});
            let stale;
            try { await c.runIntakeChatTurn(data.canonical,'synthetic stale answer',started.pending_inquiry_id,
                {expected_question_revision:started.expected_question_revision+1,interview_action:'answer'}); stale={threw:false}; }
            catch(e) { stale={threw:true,message:e.message,isError:!!e.isError}; }
            const session=await c.getSession(data.canonical);
            const auth=await (await fetch('/api/complaint-workspace/auth/session', {credentials:'same-origin'})).json();
            return {bootstrap,started,stale,session,auth,events:window.publicEvents,
                    local:{...localStorage},storedSession:{...sessionStorage}};
        }""", {"issued":issued,"case":{"tenant_id":world.case.tenant_id,"case_id":world.case.case_id,
            "resource_id":world.case.resource_id,"revision":world.case.revision},
            "canonical":world.case.tenant_id,"marker":MARKER})
        assert result["auth"]["principal_id"] == world.principal.principal_id
        assert result["stale"] == {"threw":True,"message":"stale_question","isError":True}
        session=result["session"]["session"]
        assert session["user_id"] == world.case.tenant_id and session["case_id"] == world.case.case_id
        shared=session["shared_interview"]
        assert shared["knowledge_graph"]["entities"]
        assert shared["dependency_graph"].get("nodes") or shared["dependency_graph"].get("requirements")
        assert shared["pending_inquiry"]["inquiry_id"] == result["started"]["pending_inquiry_id"]
        assert shared["session_revision"] == result["started"]["interview"]["session_revision"]
        assert world.calls
        for call in world.calls:
            headers=dict(call["headers"])
            assert headers["x-tenant-id"] == world.case.tenant_id
            assert headers["x-case-id"] == world.case.case_id
            assert headers["x-resource-id"] == world.case.resource_id
            assert headers["x-expected-revision"] == str(world.case.revision)
            assert "x-actor-principal-id" not in headers and "x-user-id" not in headers
            arguments=call["body"].get("params",{}).get("arguments",{})
            assert "user_id" not in arguments or arguments["user_id"] == world.principal.principal_id
            if call["body"].get("params", {}).get("name") == "complaint.run_intake_chat_turn":
                assert "user_id" not in arguments
        assert MARKER not in json.dumps({k:result[k] for k in ("events","local","storedSession")})


@pytest.mark.parametrize("flavor", ["classic", "esm"])
def test_privacy_clear_discards_late_real_response_without_success_event(tmp_path, monkeypatch, flavor):
    with _page(tmp_path, monkeypatch) as (world, page):
        _client(page, flavor)
        page.evaluate("""async data => {
            const realFetch = window.fetch.bind(window);
            window.lateDeliveryHeld = false;
            window.lateDeliveryResult = null;
            const heldFetch = async (...args) => {
                const response = await realFetch(...args);
                // Preserve the actual Response and body. Only its delivery to
                // this SDK instance is deferred; ASGI concurrency is not claimed.
                window.lateDeliveryHeld = true;
                await new Promise(resolve => { window.releaseLateDelivery = resolve; });
                return response;
            };
            window.actualClient = new window.actualSdk.ComplaintMcpClient({origin:location.origin,fetchImpl:heldFetch});
            window.actualClient.startSession(data.user).then(
                () => { window.lateDeliveryResult = {resolved:true}; },
                e => { window.lateDeliveryResult = {rejected:true,isError:!!e.isError}; });
        }""", {"user": USER_ID})
        page.wait_for_function("window.lateDeliveryHeld === true")
        try:
            page.evaluate("window.actualClient.clearPrivateBrowserState()")
        finally:
            page.evaluate("window.releaseLateDelivery()")
        page.wait_for_function("window.lateDeliveryResult !== null")
        result = page.evaluate("({outcome:window.lateDeliveryResult,last:window.actualClient.getLastToolCall(),events:window.publicEvents})")
        assert result["outcome"].get("rejected") is True and not result["outcome"].get("resolved")
        assert result["last"] is None
        assert not any(value.get("status") == "success" for value in result["events"])
