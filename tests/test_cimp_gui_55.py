"""Adversarial multi-role and transport isolation.

Transport-probe cases below qualify outer route admission. The additional
``test_actual_*`` cases use real encrypted workspaces and actual recipient-key
review admission; a probe packet alone does not qualify those product paths.

Synthetic owner, lawyer, admin, and stranger contexts share one principal
store and one mediator per case. Legacy HTTP, workspace HTTP, MCP, review,
download, and message routes are the production handlers. WebSockets and
server-sent events stay denied. Account disable and staff demotion drop an
already-open browser session and a forged replay of that cookie.

Known limits: WebSocket and SSE sessions stay unqualified and are denied.
Demotion drops the live session and the staff role immediately. An owner-issued
case grant remains until the owner revokes that grant. The browser proof uses
the Task02 pipe bridge into the composed ASGI app and does not open a public
listener.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from applications.browser_sessions import SESSION_COOKIE
from applications.case_routes import MESSAGE_INBOX_PATH
from tests.gui_security_fixtures import (
    ADMIN_CREDENTIAL,
    LAWYER_CREDENTIAL,
    MESSAGE,
    OWNER_CREDENTIAL,
    OWNER_MARKER,
    STRANGER_CREDENTIAL,
    STRANGER_MARKER,
    build_security_world,
    case_headers,
    compose_security_app,
    csrf,
    login,
    open_browser,
    review_app,
    server_app,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

LEGACY = ("/cookies", "/load_profile", "/create_profile", "/api/chat", "/api/chat/fallback")


def _secret_absent(response):
    assert OWNER_MARKER not in response.text
    assert STRANGER_MARKER not in response.text
    assert MESSAGE not in response.text


def _content_headers(world, case, action):
    revision = world.policy_revision if case is world.case else None
    return case_headers(case, action, membership_revision=revision)


def test_roles_are_isolated_across_legacy_workspace_mcp_review_and_download(tmp_path):
    world = build_security_world(tmp_path)
    app = compose_security_app(world)
    assert world.owner.principal_id != world.case.tenant_id
    with TestClient(app, base_url="https://testserver") as owner, TestClient(app, base_url="https://testserver") as lawyer, TestClient(app, base_url="https://testserver") as admin, TestClient(app, base_url="https://testserver") as stranger:
        owner_token, owner_session = login(owner, OWNER_CREDENTIAL)
        lawyer_token, lawyer_session = login(lawyer, LAWYER_CREDENTIAL)
        admin_token, admin_session = login(admin, ADMIN_CREDENTIAL)
        stranger_token, _stranger_session = login(stranger, STRANGER_CREDENTIAL)
        assert owner_session["roles"] == ["complainant"]
        assert lawyer_session["roles"] == ["lawyer"]
        assert admin_session["roles"] == ["operational_admin"]

        cards = owner.get("/api/claim-support/element-proof-cards", headers=_content_headers(world, world.case, "case.review"))
        assert cards.status_code == 200, cards.text
        assert cards.json()["cards"] == [OWNER_MARKER]
        download = owner.get("/api/documents/download", params={"path": str(world.owner_document)}, headers=_content_headers(world, world.case, "case.download"))
        assert download.status_code == 200 and download.text == OWNER_MARKER
        tools = owner.get("/api/complaint-workspace/mcp/tools", headers=_content_headers(world, world.case, "case.read"))
        assert tools.status_code == 200
        assert tools.json()["tools"][0]["name"] == "complaint.review_case"
        rpc = owner.post("/api/complaint-workspace/mcp/rpc", headers={**_content_headers(world, world.case, "case.read"), **csrf(owner_token)}, json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
        assert rpc.status_code == 200 and rpc.json()["result"]["ok"] is True

        lawyer_cards = lawyer.get("/api/claim-support/element-proof-cards", headers=_content_headers(world, world.case, "case.review"))
        assert lawyer_cards.status_code == 200, lawyer_cards.text
        assert lawyer_cards.json()["cards"] == [OWNER_MARKER]
        lawyer_file = lawyer.get("/api/documents/download", params={"path": str(world.owner_document)}, headers=_content_headers(world, world.case, "case.download"))
        assert lawyer_file.status_code == 200 and lawyer_file.text == OWNER_MARKER
        workspace = lawyer.get("/api/cases/lawyer-workspace")
        assert workspace.status_code == 200, workspace.text
        assert workspace.json()["cases"][0]["case_id"] == world.case.case_id
        assert MESSAGE not in workspace.text
        assert workspace.json()["cases"][0]["actor_is_encrypted_owner"] is False

        forged = lawyer.get("/api/claim-support/element-proof-cards", headers={**_content_headers(world, world.case, "case.review"), "x-role": "operational_admin"})
        assert forged.status_code == 403 and forged.json()["error"] == "request_cannot_mint_authority"
        _secret_absent(forged)
        minted = lawyer.post("/api/complaint-workspace/mcp/call", headers={**_content_headers(world, world.case, "case.read"), **csrf(lawyer_token)}, json={"tool_name": "complaint.review_case", "arguments": {}, "roles": ["operational_admin"]})
        assert minted.status_code == 403 and minted.json()["error"] == "request_cannot_mint_authority"
        _secret_absent(minted)

        crossed = lawyer.get("/api/claim-support/element-proof-cards", headers=case_headers(world.case, "case.review", extra={"x-tenant-id": world.other.tenant_id}, membership_revision=world.policy_revision))
        assert crossed.status_code == 403 and crossed.json()["error"] == "tenant_mismatch"
        _secret_absent(crossed)
        other_file = lawyer.get("/api/documents/download", params={"path": str(world.stranger_document)}, headers=_content_headers(world, world.case, "case.download"))
        assert other_file.status_code == 403
        assert STRANGER_MARKER not in other_file.text
        other_case = lawyer.get("/api/claim-support/element-proof-cards", headers=case_headers(world.other, "case.review"))
        assert other_case.status_code == 403
        _secret_absent(other_case)

        stale = owner.post(
            "/api/complaint-workspace/mcp/call",
            headers={**case_headers(world.case, "case.update", revision=world.case.revision + 1), **csrf(owner_token)},
            json={"tool_name": "complaint.update_draft", "arguments": {}},
        )
        assert stale.status_code == 409 and stale.json()["error"] == "revision_conflict"
        _secret_absent(stale)
        assert ("call_mcp_tool", "complaint.update_draft", {}) not in world.owner_workspace.calls

        for client, token in ((stranger, stranger_token), (admin, admin_token)):
            denied_review = client.get("/api/claim-support/element-proof-cards", headers=case_headers(world.case, "case.review"))
            denied_download = client.get("/api/documents/download", params={"path": str(world.owner_document)}, headers=case_headers(world.case, "case.download"))
            denied_tools = client.get("/api/complaint-workspace/mcp/tools", headers=case_headers(world.case, "case.read"))
            denied_case = client.get(f"/api/cases/lawyer-workspace/{world.case.case_id}")
            assert denied_review.status_code == 403
            assert denied_download.status_code == 403
            assert denied_tools.status_code == 403
            assert denied_case.status_code >= 400
            for response in (denied_review, denied_download, denied_tools, denied_case):
                _secret_absent(response)
            del token

        directory = admin.get("/api/admin/accounts", headers=csrf(admin_token))
        assert directory.status_code == 200, directory.text
        _secret_absent(directory)
        assert directory.json()["case_content"] is None

        created = owner.post("/api/cases/messages/threads", headers=csrf(owner_token), json={"case_id": world.case.case_id, "idempotency_key": "security-thread"})
        assert created.status_code == 201, created.text
        assert created.json()["actor_is_encrypted_owner"] is False
        thread_id = created.json()["thread_id"]
        sent = owner.post(
            f"/api/cases/messages/threads/{thread_id}/messages",
            headers=csrf(owner_token),
            json={"case_id": world.case.case_id, "text": MESSAGE, "idempotency_key": "security-send"},
        )
        assert sent.status_code == 201, sent.text
        visible = lawyer.get(
            f"/api/cases/messages/threads/{thread_id}/messages",
            params={"case_id": world.case.case_id, "membership_grant_id": world.grant_id, "expected_membership_version": world.grant_version},
        )
        assert visible.status_code == 200, visible.text
        assert visible.json()["messages"][0]["text"] == MESSAGE
        stale_edit = lawyer.post(
            f"/api/cases/messages/threads/{thread_id}/messages/{sent.json()['message_id']}/revise",
            headers=csrf(lawyer_token),
            json={
                "case_id": world.case.case_id,
                "text": "synthetic-stale-edit",
                "expected_version": 9,
                "idempotency_key": "security-stale",
                "membership_grant_id": world.grant_id,
                "expected_membership_version": world.grant_version,
            },
        )
        assert stale_edit.status_code >= 400
        assert "synthetic-stale-edit" not in stale_edit.text
        leaked = stranger.get(f"/api/cases/messages/threads/{thread_id}/messages", params={"case_id": world.case.case_id})
        assert leaked.status_code >= 400
        _secret_absent(leaked)
        admin_leak = admin.get(f"/api/cases/messages/threads/{thread_id}/messages", params={"case_id": world.case.case_id})
        assert admin_leak.status_code >= 400
        _secret_absent(admin_leak)
        cross_message = stranger.get(
            f"/api/cases/messages/threads/{thread_id}/messages",
            params={"case_id": world.other.case_id, "membership_grant_id": world.grant_id, "expected_membership_version": world.grant_version},
        )
        assert cross_message.status_code >= 400
        _secret_absent(cross_message)

        direct = owner.get(f"/api/cases/audit-exports/synthetic-export")
        assert direct.status_code == 403 and direct.json()["error"] == "direct_download_denied"
        _secret_absent(direct)

        for path in LEGACY:
            method = owner.get if path == "/cookies" else owner.post
            kwargs = {"headers": case_headers(world.case)}
            if path != "/cookies":
                kwargs["json"] = {"message": MESSAGE, "password": OWNER_CREDENTIAL}
                kwargs["headers"] = {**kwargs["headers"], **csrf(owner_token)}
            retired = method(path, **kwargs)
            assert retired.status_code == 401 and retired.json()["error"] == "legacy_route_retired"
            _secret_absent(retired)
        with pytest.raises(Exception):
            with owner.websocket_connect("/api/chat") as socket:
                socket.receive_json()

    assert world.stranger_mediator.calls == []
    assert world.stranger_workspace.calls == []


def test_server_and_review_apps_share_the_same_owners(tmp_path):
    world = build_security_world(tmp_path)
    for app in (server_app(world), review_app(world)):
        with TestClient(app, base_url="https://testserver") as owner, TestClient(app, base_url="https://testserver") as stranger:
            login(owner, OWNER_CREDENTIAL)
            allowed = owner.get("/api/claim-support/element-proof-cards", headers=case_headers(world.case, "case.review"))
            assert allowed.status_code == 200 and allowed.json()["cards"] == [OWNER_MARKER]
            login(stranger, STRANGER_CREDENTIAL)
            denied = stranger.get("/api/documents/download", params={"path": str(world.owner_document)}, headers=case_headers(world.case, "case.download"))
            assert denied.status_code == 403
            _secret_absent(denied)
            forged = stranger.post(
                "/api/complaint-workspace/mcp/rpc",
                headers={**case_headers(world.case, "case.read"), **csrf(login(stranger, STRANGER_CREDENTIAL)[0])},
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "complaint.review_case", "arguments": {"role": "lawyer"}}},
            )
            assert forged.status_code == 403
            _secret_absent(forged)
            retired = stranger.post("/api/chat", json={"message": MESSAGE})
            assert retired.status_code == 401 and retired.json()["error"] == "legacy_route_retired"
    assert world.stranger_mediator.calls == []


def test_disable_and_demotion_invalidate_open_and_forged_api_sessions(tmp_path):
    world = build_security_world(tmp_path)
    app = compose_security_app(world)
    with TestClient(app, base_url="https://testserver") as admin, TestClient(app, base_url="https://testserver") as lawyer, TestClient(app, base_url="https://testserver") as forged:
        admin_token, _admin_session = login(admin, ADMIN_CREDENTIAL)
        lawyer_token, lawyer_session = login(lawyer, LAWYER_CREDENTIAL)
        assert lawyer_session["roles"] == ["lawyer"]
        stolen = lawyer.cookies.get(SESSION_COOKIE)
        forged.cookies.set(SESSION_COOKIE, stolen)
        assert lawyer.get("/api/claim-support/element-proof-cards", headers=_content_headers(world, world.case, "case.review")).status_code == 200

        demoted = admin.post(
            f"/api/admin/accounts/{world.lawyer.principal_id}/role",
            headers=csrf(admin_token),
            json={"account_kind": "complainant", "expected_revision": world.lawyer.revision},
        )
        assert demoted.status_code == 200, demoted.text
        assert demoted.json()["roles"] == ["complainant"]
        open_review = lawyer.get("/api/claim-support/element-proof-cards", headers=_content_headers(world, world.case, "case.review"))
        forged_review = forged.get("/api/documents/download", params={"path": str(world.owner_document)}, headers=_content_headers(world, world.case, "case.download"))
        assert open_review.status_code == 401
        assert forged_review.status_code == 401
        _secret_absent(open_review)
        _secret_absent(forged_review)
        rebound_token, rebound = login(lawyer, LAWYER_CREDENTIAL)
        assert rebound["roles"] == ["complainant"]
        # Staff authority is the session role. The owner-issued case grant remains
        # until the owner revokes it; a forged staff role still cannot mint access.
        staff_forged = lawyer.get(
            "/api/claim-support/element-proof-cards",
            headers={**case_headers(world.case, "case.review", membership_revision=world.policy_revision), "x-role": "lawyer"},
        )
        assert staff_forged.status_code == 403 and staff_forged.json()["error"] == "request_cannot_mint_authority"
        _secret_absent(staff_forged)
        assert lawyer.get("/api/admin/accounts", headers=csrf(rebound_token)).status_code == 403

        disabled = admin.post(
            f"/api/admin/accounts/{world.lawyer.principal_id}/status",
            headers=csrf(admin_token),
            json={"status": "disabled", "expected_revision": demoted.json()["revision"]},
        )
        assert disabled.status_code == 200, disabled.text
        stolen = lawyer.cookies.get(SESSION_COOKIE)
        forged.cookies.set(SESSION_COOKIE, stolen)
        after = lawyer.get("/api/cases", headers=csrf(rebound_token))
        forged_after = forged.get("/api/cases", headers=csrf(rebound_token))
        assert after.status_code == 401 and forged_after.status_code == 401
        _secret_absent(after)
        replay = lawyer.post("/api/complaint-workspace/auth/login", json={"credential": LAWYER_CREDENTIAL})
        assert replay.status_code == 401
        forged.cookies.clear()
        owner_token, _owner_session = login(forged, OWNER_CREDENTIAL)
        logged_out = forged.post("/api/complaint-workspace/auth/logout", headers=csrf(owner_token))
        assert logged_out.status_code == 200
        after_logout = forged.get("/api/claim-support/element-proof-cards", headers=case_headers(world.case, "case.review"))
        assert after_logout.status_code == 401
        _secret_absent(after_logout)


def test_open_browser_loses_authority_on_demotion_and_disable(tmp_path):
    from tests import gui_native_browser as browser

    try:
        browser.pin_executables()
    except browser.BrowserCapabilityError as exc:
        assert "not installed" in str(exc)
        _open_asgi_context_revocation(tmp_path)
        return
    _open_chromium_context_revocation(tmp_path)


def _open_asgi_context_revocation(tmp_path):
    """Already-open ASGI client when the Task02 Chromium driver is absent.

    This does not claim a DOM run. WebSocket upgrade is still denied by the app.
    """

    world = build_security_world(tmp_path)
    app = compose_security_app(world)
    with TestClient(app, base_url="https://testserver") as admin, TestClient(app, base_url="https://testserver") as lawyer, TestClient(app, base_url="https://testserver") as forged:
        admin_token, _session = login(admin, ADMIN_CREDENTIAL)
        lawyer_token, opened = login(lawyer, LAWYER_CREDENTIAL)
        assert opened["roles"] == ["lawyer"]
        stolen = lawyer.cookies.get(SESSION_COOKIE)
        forged.cookies.set(SESSION_COOKIE, stolen)
        headers = _content_headers(world, world.case, "case.review")
        assert lawyer.get("/api/claim-support/element-proof-cards", headers=headers).status_code == 200
        demoted = admin.post(
            f"/api/admin/accounts/{world.lawyer.principal_id}/role",
            headers=csrf(admin_token),
            json={"account_kind": "complainant", "expected_revision": world.lawyer.revision},
        )
        assert demoted.status_code == 200, demoted.text
        revoked = lawyer.get("/api/claim-support/element-proof-cards", headers=headers)
        forged_revoked = forged.get("/api/cases", headers=csrf(lawyer_token))
        assert revoked.status_code == 401 and forged_revoked.status_code == 401
        _secret_absent(revoked)
        _secret_absent(forged_revoked)
        rebound_token, rebound = login(lawyer, LAWYER_CREDENTIAL)
        assert rebound["roles"] == ["complainant"]
        disabled = admin.post(
            f"/api/admin/accounts/{world.lawyer.principal_id}/status",
            headers=csrf(admin_token),
            json={"status": "disabled", "expected_revision": demoted.json()["revision"]},
        )
        assert disabled.status_code == 200, disabled.text
        stolen = lawyer.cookies.get(SESSION_COOKIE)
        forged.cookies.clear()
        forged.cookies.set(SESSION_COOKIE, stolen)
        assert lawyer.get("/api/cases", headers=csrf(rebound_token)).status_code == 401
        assert forged.get("/api/cases", headers=csrf(rebound_token)).status_code == 401
        with pytest.raises(Exception):
            with lawyer.websocket_connect("/api/chat") as socket:
                socket.receive_json()


def _open_chromium_context_revocation(tmp_path):
    world = build_security_world(tmp_path)
    app = compose_security_app(world)
    with TestClient(app, base_url="https://testserver") as admin:
        admin_token, _session = login(admin, ADMIN_CREDENTIAL)
        with open_browser(tmp_path, app) as harness:
            page = harness.page
            page.goto(harness.browser.SAME_ORIGIN + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
            assert page.locator("body").count() == 1
            if harness.network_denial["af_unix_only"]:
                assert harness.network_denial["af_inet"]["opened"] is False

            def browser_login(credential):
                return page.evaluate(
                    """async (credential) => {
                        const response = await fetch('/api/complaint-workspace/auth/login', {
                            method: 'POST', credentials: 'include',
                            headers: {'content-type': 'application/json'},
                            body: JSON.stringify({credential})
                        });
                        const body = await response.json();
                        return {status: response.status, csrf: body.csrf_token || '', roles: body.roles || []};
                    }""",
                    credential,
                )

            def browser_get(path, headers):
                return page.evaluate(
                    """async ({path, headers}) => {
                        const response = await fetch(path, {credentials: 'include', headers});
                        return {status: response.status, text: await response.text()};
                    }""",
                    {"path": path, "headers": headers},
                )

            opened = browser_login(LAWYER_CREDENTIAL)
            assert opened["status"] == 200 and opened["roles"] == ["lawyer"]
            review_headers = _content_headers(world, world.case, "case.review")
            review_headers["x-csrf-token"] = opened["csrf"]
            admitted = browser_get("/api/claim-support/element-proof-cards", review_headers)
            assert admitted["status"] == 200 and OWNER_MARKER in admitted["text"]
            stolen = next(item["value"] for item in harness.context.cookies() if item["name"] == SESSION_COOKIE)

            demoted = admin.post(
                f"/api/admin/accounts/{world.lawyer.principal_id}/role",
                headers=csrf(admin_token),
                json={"account_kind": "complainant", "expected_revision": world.lawyer.revision},
            )
            assert demoted.status_code == 200, demoted.text
            revoked = browser_get("/api/claim-support/element-proof-cards", review_headers)
            assert revoked["status"] == 401
            assert OWNER_MARKER not in revoked["text"] and MESSAGE not in revoked["text"]
            _forged_browser_denied(harness, tmp_path / "forged-demotion", stolen, review_headers)

            rebound = browser_login(LAWYER_CREDENTIAL)
            assert rebound["status"] == 200 and rebound["roles"] == ["complainant"]
            rebound_headers = {**case_headers(world.case, "case.review", membership_revision=world.policy_revision), "x-role": "lawyer", "x-csrf-token": rebound["csrf"]}
            still_denied = browser_get("/api/claim-support/element-proof-cards", rebound_headers)
            assert still_denied["status"] == 403 and OWNER_MARKER not in still_denied["text"]
            rebound_cookie = next(item["value"] for item in harness.context.cookies() if item["name"] == SESSION_COOKIE)

            disabled = admin.post(
                f"/api/admin/accounts/{world.lawyer.principal_id}/status",
                headers=csrf(admin_token),
                json={"status": "disabled", "expected_revision": demoted.json()["revision"]},
            )
            assert disabled.status_code == 200, disabled.text
            closed = browser_get("/api/cases", {"x-csrf-token": rebound["csrf"]})
            assert closed["status"] == 401 and OWNER_MARKER not in closed["text"]
            _forged_browser_denied(harness, tmp_path / "forged-disable", rebound_cookie, {"x-csrf-token": rebound["csrf"]})
            failed_login = browser_login(LAWYER_CREDENTIAL)
            assert failed_login["status"] == 401

            legacy = page.evaluate(
                """async () => {
                    const response = await fetch('/api/chat', {method: 'POST', credentials: 'include', headers: {'content-type': 'application/json'}, body: '{}'});
                    return {status: response.status, text: await response.text()};
                }"""
            )
            assert legacy["status"] == 401 and "legacy_route_retired" in legacy["text"]
            page.evaluate("() => { try { new WebSocket('ws://127.0.0.1:41731/api/chat'); } catch (error) { return String(error); } }")
            page.evaluate("() => fetch('http://example.invalid/secret').catch(() => 'aborted')")
            assert harness.bridge.aborted_external
            assert harness.bridge.asgi_calls > 0


def _forged_browser_denied(harness, profile, cookie, headers):
    profile.mkdir(mode=0o700)
    context = harness.browser._launch_context(harness.playwright, harness.chromium_path, profile, harness.bridge)
    harness.observed |= harness.browser._with_descendants(harness.browser._matching_pids((str(profile),)))
    try:
        context.add_cookies([{
            "name": SESSION_COOKIE,
            "value": cookie,
            "url": harness.browser.SAME_ORIGIN + "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "Strict",
        }])
        page = context.new_page()
        page.goto(harness.browser.SAME_ORIGIN + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
        result = page.evaluate(
            """async (headers) => {
                const response = await fetch('/api/cases', {credentials: 'include', headers});
                return {status: response.status, text: await response.text()};
            }""",
            headers,
        )
        assert result["status"] == 401
        assert OWNER_MARKER not in result["text"] and MESSAGE not in result["text"]
    finally:
        context.close()


def test_actual_encrypted_workspaces_preserve_actor_case_and_mcp_isolation(tmp_path):
    from tests.gui_real_security_fixtures import actual_security_world, ADMIN_CREDENTIAL
    from tests.test_cimp_gui_14 import (NARRATIVE, PASSPHRASE, _composed_login,
        _composed_headers, _composed_ciphertext_snapshot)
    world = actual_security_world(tmp_path)
    world.owner_keys.unlock_passphrase(PASSPHRASE)
    world.service.unlock_private_keys(passphrase=PASSPHRASE)
    app = world.review_app
    with TestClient(app, base_url="https://testserver") as owner, TestClient(app, base_url="https://testserver") as stranger, TestClient(app, base_url="https://testserver") as admin:
        csrf_token = _composed_login(owner)
        headers = _composed_headers(world.case, csrf_token)
        session = owner.get('/api/complaint-workspace/session', headers=headers)
        assert session.status_code == 200, session.text
        state = session.json()['session']
        assert state['case_id'] == world.case.case_id
        assert state['user_id'] == world.case.tenant_id != world.owner.principal_id
        assert state['shared_interview']['knowledge_graph']['entities']
        assert NARRATIVE in session.text
        before = _composed_ciphertext_snapshot(world.service)
        assert before
        assert any(path.read_bytes().startswith(b'CGPE') for path in
            (world.service._session_dir/'joined-revisions').rglob('*') if path.is_file())
        for transport in ('call', 'rpc'):
            call = {'tool_name':'complaint.run_intake_chat_turn', 'arguments':{'message':'/why'}}
            if transport == 'rpc':
                call = {'jsonrpc':'2.0','id':'real55-why','method':'tools/call',
                    'params':{'name':call['tool_name'],'arguments':call['arguments']}}
            response = owner.post('/api/complaint-workspace/mcp/'+transport, headers=headers, json=call)
            assert response.status_code == 200, response.text
            assert world.case.case_id in response.text
            if transport == 'rpc':
                assert response.json()['result']['isError'] is False
        assert _composed_ciphertext_snapshot(world.service) == before
        _composed_login(stranger, 'synthetic-stranger-credential')
        _composed_login(admin, ADMIN_CREDENTIAL)
        for client in (stranger, admin):
            for path in ('/api/complaint-workspace/session', '/api/complaint-workspace/mcp/tools'):
                denied = client.get(path, headers=_composed_headers(world.case))
                assert denied.status_code == 403, denied.text
                assert NARRATIVE not in denied.text
        forged = owner.get('/api/complaint-workspace/session', headers={**headers,'x-role':'operational_admin'})
        assert forged.status_code == 403 and NARRATIVE not in forged.text
        cross = owner.get('/api/complaint-workspace/session', headers=_composed_headers(world.foreign))
        assert cross.status_code == 403 and NARRATIVE not in cross.text
        foreign_csrf = _composed_login(stranger, 'synthetic-stranger-credential')
        own_foreign = stranger.post('/api/complaint-workspace/intake-chat',
            headers=_composed_headers(world.foreign, foreign_csrf),
            json={'message':'Authored separate stranger complaint about an employment dismissal.', 'interview_action':'start'})
        assert own_foreign.status_code == 200, own_foreign.text
        assert own_foreign.json()['session']['case_id'] == world.foreign.case_id
        assert _composed_ciphertext_snapshot(world.service) == before


@pytest.mark.parametrize('invalidate', ['disable', 'demote'])
def test_actual_recipient_review_and_forged_cookie_lose_authority(tmp_path, invalidate):
    from tests.gui_real_security_fixtures import actual_security_world, ADMIN_CREDENTIAL
    from tests.test_cimp_gui_14 import _composed_login
    from tests.test_gui32_private_review_http import _headers, _propose, MARKER
    world = actual_security_world(tmp_path)
    assert not world.owner_keys.unlocked
    assert not world.service._private_key_session().unlocked
    with TestClient(world.review_app, base_url='https://testserver') as lawyer, TestClient(world.review_app, base_url='https://testserver') as admin, TestClient(world.review_app, base_url='https://testserver') as forged:
        lawyer_csrf = _composed_login(lawyer, 'synthetic-lawyer-credential')
        admin_csrf = _composed_login(admin, ADMIN_CREDENTIAL)
        _propose(lawyer, world, lawyer_csrf)
        path = '/api/legal-analysis/'+world.case.case_id+'/lawyer-reviews'
        positive = lawyer.get(path, headers=_headers(world))
        assert positive.status_code == 200 and MARKER in positive.text, positive.text
        forged.cookies.set(SESSION_COOKIE, lawyer.cookies.get(SESSION_COOKIE))
        if invalidate == 'disable':
            endpoint, body = 'status', {'status':'disabled'}
        else:
            endpoint, body = 'role', {'account_kind':'complainant'}
        body['expected_revision'] = world.lawyer.revision
        changed = admin.post('/api/admin/accounts/'+world.lawyer.principal_id+'/'+endpoint,
            headers={'x-csrf-token':admin_csrf}, json=body)
        assert changed.status_code == 200, changed.text
        for client in (lawyer, forged):
            denied = client.get(path, headers=_headers(world))
            assert denied.status_code == 401, denied.text
            assert MARKER not in denied.text
        if invalidate == 'demote':
            _composed_login(lawyer, 'synthetic-lawyer-credential')
            assert lawyer.get('/api/admin/accounts').status_code == 403
            # A case grant is independent of a staff role; server-owned role
            # demotion cannot mint a different grant or erase a valid one.
            assert world.memberships.load(world.membership.grant_id).version == world.membership.version


def test_actual_encrypted_owner_is_denied_in_already_open_chromium_after_disable(tmp_path):
    from tests.gui_real_security_fixtures import actual_security_world, ADMIN_CREDENTIAL
    from tests.test_cimp_gui_14 import NARRATIVE, PASSPHRASE, _composed_login, _composed_headers
    from tests.test_cimp_gui_46 import _browser
    from tests import gui_native_browser as actual_browser
    world = actual_security_world(tmp_path)
    world.owner_keys.unlock_passphrase(PASSPHRASE)
    world.service.unlock_private_keys(passphrase=PASSPHRASE)
    browser_root = tmp_path/'actual-browser';browser_root.mkdir()
    with _browser(browser_root, world.review_app) as page, TestClient(world.review_app, base_url='https://testserver') as admin:
        page.goto(actual_browser.SAME_ORIGIN+'/workspace', wait_until='domcontentloaded')
        assert page.locator('#adaptive-narrative').count() == 1
        issued = page.evaluate("""async () => {
            const response=await fetch('/api/complaint-workspace/auth/login',{method:'POST',credentials:'same-origin',
                headers:{'content-type':'application/json'},body:JSON.stringify({credential:'synthetic-owner-credential'})});
            if(response.status!==200)throw new Error('actual owner login failed');return await response.json();
        }""")
        assert issued['principal_id'] == world.owner.principal_id != world.case.tenant_id
        get_session = """async headers => {const response=await fetch('/api/complaint-workspace/session',
            {credentials:'same-origin',headers});return {status:response.status,text:await response.text()};}"""
        positive = page.evaluate(get_session, _composed_headers(world.case))
        assert positive['status'] == 200 and NARRATIVE in positive['text']
        csrf_token = _composed_login(admin, ADMIN_CREDENTIAL)
        changed = admin.post('/api/admin/accounts/'+world.owner.principal_id+'/status',
            headers={'x-csrf-token':csrf_token},json={'status':'disabled','expected_revision':world.owner.revision})
        assert changed.status_code == 200, changed.text
        denied = page.evaluate(get_session, _composed_headers(world.case))
        assert denied['status'] == 401 and NARRATIVE not in denied['text']
