"""Real app authentication/composition with encrypted synthetic identity owners.

Backend sentinels are explicitly injected per case. They measure routing and
non-dispatch, not legal support, live inference or complete GUI qualification.
"""
from __future__ import annotations

import os
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from applications.browser_sessions import (BrowserSessionConfiguration, BrowserSessionService,
    PrincipalStoreCredentialAdapter, SESSION_COOKIE)
from applications.case_access import CaseAccessError, CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_routes import (COMPOSITION_NAME, CaseHandlerRegistry, CaseJSONBodyLimits, compose_case_routes,
    register_case_route_module, unregister_case_route_module)
from applications.principal_store import PrincipalStore
from applications.review_api import create_review_api_app
from applications.review_ui import create_review_dashboard_app, create_review_surface_app
from applications.server import SERVER

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
_SECRET = "synthetic-case-marker"
OWNER_CREDENTIAL = "synthetic-password"
STRANGER_CREDENTIAL = "synthetic-access-token"
ADMIN_CREDENTIAL = "synthetic-api-key"
LAWYER_CREDENTIAL = "synthetic-auth-token"


class _Mediator:
    def __init__(self, marker=_SECRET):
        self.calls, self.marker = [], marker
        self.state = self

    def load_profile(self, payload):
        self.calls.append(("load_profile", payload))

    def store_profile(self, payload):
        self.calls.append(("store_profile", payload))

    def message(self, payload):
        self.calls.append(("message", payload))

    def io_payload(self, text):
        self.calls.append(("io_payload", text))
        return {"message": "synthetic-reply", "inquiry": {"marker": self.marker}}

    def io(self, text):
        self.calls.append(("io", text))
        return "synthetic-reply"

    def get_current_inquiry_payload(self):
        self.calls.append(("inquiry",))
        return {"inquiry": {"marker": self.marker}}

    def get_element_proof_cards(self, user, claim_type=None):
        self.calls.append(("cards", user, claim_type))
        return {"cards": [self.marker], "user": user}


class _Workspace:
    def __init__(self, marker=_SECRET):
        self.calls, self.marker = [], marker

    def list_mcp_tools(self):
        self.calls.append(("list_mcp_tools",))
        return {"tools": [{"name": "complaint.review_case", "description": "Synthetic case backend."}]}

    def call_mcp_tool(self, tool_name, arguments):
        self.calls.append(("call_mcp_tool", tool_name, arguments))
        return {"ok": True, "marker": self.marker}


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    owner = principals.register_from_request({})
    stranger = principals.register_from_request({})
    admin = principals.install_server_role(role="operational_admin")
    lawyer = principals.install_server_role(role="lawyer")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id, STRANGER_CREDENTIAL: stranger.principal_id,
            ADMIN_CREDENTIAL: admin.principal_id, LAWYER_CREDENTIAL: lawyer.principal_id}), signing_key=os.urandom(32), ttl_seconds=60))
    handlers, mediator, workspace = CaseHandlerRegistry(), _Mediator(), _Workspace()
    downloads = tmp_path / "case-downloads"
    downloads.mkdir()
    document = downloads / "synthetic.txt"
    document.write_text(_SECRET, encoding="utf-8")
    handlers.bind(case, mediator=mediator, workspace_service=workspace, download_root=downloads)
    return SimpleNamespace(principals=principals, cases=cases, owner=owner, stranger=stranger,
        admin=admin, lawyer=lawyer, case=case, sessions=sessions, authorizer=CaseActionAuthorizer(principals, cases),
        handlers=handlers, mediator=mediator, workspace=workspace, document=document)


def _headers(case, action=None, *, revision=None):
    values = {"x-tenant-id": case.tenant_id, "x-case-id": case.case_id,
              "x-resource-id": case.resource_id,
              "x-expected-revision": str(case.revision if revision is None else revision)}
    if action is not None:
        values["x-case-action"] = action
    return values


def _login(client, credential=OWNER_CREDENTIAL):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _app(world, variant="server", *, handlers=True, sessions=True, json_body_limits=None):
    kwargs = {"browser_sessions": world.sessions if sessions else None,
              "case_handlers": world.handlers if handlers else None, "json_body_limits": json_body_limits}
    if variant == "review":
        return create_review_api_app(world.mediator, world.authorizer, **kwargs)
    if variant == "surface":
        return create_review_surface_app(world.mediator, world.authorizer, **kwargs)
    if variant == "dashboard":
        return create_review_dashboard_app(world.authorizer, **kwargs)
    return SERVER(world.mediator, world.authorizer, **kwargs).app


def _mount_admin(app: FastAPI, authorizer):
    @app.get("/api/admin/assembly-probe")
    async def assembly_probe(request: Request):
        decision = request.state.case_authorization
        return {"ok": True, "actor": decision.actor_principal_id,
                "content": decision.permits_case_content,
                "same_authorizer": request.app.state.case_authorizer is authorizer}


def test_app_variants_call_the_shared_composition_seam(tmp_path):
    world = _world(tmp_path)
    register_case_route_module("admin", _mount_admin, protected_prefixes=("/api/admin",))
    try:
        apps = [_app(world, variant) for variant in ("server", "review", "surface", "dashboard")]
    finally:
        unregister_case_route_module(_mount_admin)
    # Removal from the assembly registry cannot unprotect an already-built app.
    for app in apps:
        assert app.state.case_route_composition == COMPOSITION_NAME
        assert app.state.case_authorizer is world.authorizer
        assert "admin" in app.state.case_route_extension_kinds
        with TestClient(app, base_url="https://testserver") as client:
            denied = client.get("/api/admin/assembly-probe")
            assert denied.status_code == 401
            _login(client, ADMIN_CREDENTIAL)
            headers = _headers(world.case)
            headers["x-owner-principal-id"] = world.owner.principal_id
            allowed = client.get("/api/admin/assembly-probe", headers=headers)
            assert allowed.status_code == 200
            assert allowed.json() == {"ok": True, "actor": world.admin.principal_id,
                                      "content": False, "same_authorizer": True}


def test_owner_routes_run_and_stranger_or_stale_revision_do_not(tmp_path):
    world = _world(tmp_path)
    assert world.owner.tenant_id != world.case.tenant_id
    with TestClient(_app(world), base_url="https://testserver") as client:
        csrf = _login(client)
        cards = client.get("/api/claim-support/element-proof-cards", headers=_headers(world.case, "case.review"))
        assert cards.status_code == 200 and cards.json()["cards"] == [_SECRET]
        assert world.mediator.calls[-1][0] == "cards"
        download = client.get("/api/documents/download", params={"path": str(world.document)}, headers=_headers(world.case, "case.download"))
        assert download.status_code == 200 and download.text == _SECRET
        tools = client.get("/api/complaint-workspace/mcp/tools", headers=_headers(world.case, "case.read"))
        assert tools.status_code == 200
        assert tools.json()["tools"][0]["name"] == "complaint.review_case"
        assert world.workspace.calls
        headers = {**_headers(world.case, "case.read"), "x-csrf-token": csrf}
        rpc = client.post("/api/complaint-workspace/mcp/rpc", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers=headers)
        assert rpc.status_code == 200 and rpc.json()["result"]["ok"] is True
        stale = client.get("/api/documents/download", params={"path": str(world.document)}, headers=_headers(world.case, "case.download", revision=world.case.revision + 1))
        assert stale.status_code == 409 and _SECRET not in stale.text
        count = len(world.mediator.calls)
        _login(client, STRANGER_CREDENTIAL)
        denied = client.get("/api/claim-support/element-proof-cards", headers=_headers(world.case, "case.review"))
        assert denied.status_code == 403 and _SECRET not in denied.text
        assert len(world.mediator.calls) == count


def test_legacy_profile_cookie_and_mediator_paths_do_not_disclose_or_mutate(tmp_path):
    world = _world(tmp_path)
    password = "synthetic-password"
    for variant in ("server", "surface"):
        with TestClient(_app(world, variant), base_url="https://testserver") as client:
            _login(client)
            for path, method in (("/cookies", "get"), ("/load_profile", "post"), ("/create_profile", "post"), ("/api/chat", "post"), ("/api/chat/fallback", "post")):
                kwargs = {"headers": _headers(world.case), "cookies": {"hashed_password": password}}
                if method == "post":
                    kwargs["json"] = {"message": "synthetic", "password": password}
                response = getattr(client, method)(path, **kwargs)
                assert response.status_code == 401
                assert response.json()["error"] == "legacy_route_retired"
                assert password not in response.text and _SECRET not in response.text
                assert "hashed_password" not in response.text
            with pytest.raises(Exception):
                with client.websocket_connect("/api/chat", headers=_headers(world.case)) as websocket:
                    websocket.receive_json()
    assert world.mediator.calls == []
    assert world.workspace.calls == []


def test_missing_authorizer_never_reaches_case_handlers(tmp_path):
    world = _world(tmp_path)
    app = FastAPI()
    compose_case_routes(app, authorizer=None, mediator=world.mediator, browser_sessions=world.sessions, case_handlers=world.handlers)
    with TestClient(app, base_url="https://testserver") as client:
        _login(client)
        for path in ("/api/claim-support/element-proof-cards", "/api/complaint-workspace/mcp/tools"):
            response = client.get(path, headers=_headers(world.case))
            assert response.status_code == 401 and response.json()["error"] == "authorizer_required"
    assert world.mediator.calls == [] and world.workspace.calls == []


def test_non_authorizer_object_is_rejected():
    with pytest.raises(CaseAccessError, match="authority_owners"):
        compose_case_routes(FastAPI(), authorizer=object())


@pytest.mark.parametrize("variant", ["server", "review", "surface"])
@pytest.mark.parametrize("claim", ["header", "body", "query"])
def test_claimed_owner_without_session_never_authenticates(tmp_path, variant, claim):
    world = _world(tmp_path)
    with TestClient(_app(world, variant), base_url="https://testserver") as client:
        headers = _headers(world.case)
        headers["x-actor-principal-id"] = world.owner.principal_id
        if claim == "body":
            response = client.post("/api/complaint-workspace/mcp/call", headers=headers,
                json={"actor_principal_id": world.owner.principal_id, "tool_name": "complaint.review_case", "arguments": {}})
        else:
            response = client.get("/api/claim-support/element-proof-cards", headers=headers,
                params={"actor_principal_id": world.owner.principal_id} if claim == "query" else {})
        assert response.status_code == 401 and _SECRET not in response.text
    assert world.mediator.calls == [] and world.workspace.calls == []


@pytest.mark.parametrize("claim", ["header", "body", "query", "nested_rpc"])
def test_stranger_session_cannot_be_replaced_by_claimed_owner(tmp_path, claim):
    world = _world(tmp_path)
    with TestClient(_app(world), base_url="https://testserver") as client:
        csrf = _login(client, STRANGER_CREDENTIAL)
        headers = {**_headers(world.case), "x-csrf-token": csrf}
        if claim == "header":
            headers["x-actor-principal-id"] = world.owner.principal_id
            response = client.get("/api/claim-support/element-proof-cards", headers=headers)
        elif claim == "query":
            response = client.get("/api/claim-support/element-proof-cards", headers=headers,
                params=[("actor_principal_id", world.owner.principal_id), ("actor_principal_id", world.stranger.principal_id)])
        else:
            payload = {"actor_principal_id": world.owner.principal_id} if claim == "body" else {
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "complaint.review_case", "arguments": {"user_id": world.owner.principal_id}}}
            response = client.post("/api/complaint-workspace/mcp/rpc", headers=headers, json=payload)
        assert response.status_code == 403 and response.json()["error"] == "actor_mismatch"
        assert _SECRET not in response.text
    assert world.mediator.calls == [] and world.workspace.calls == []


def test_cookies_csrf_logout_and_permission_cannot_be_substituted(tmp_path):
    world = _world(tmp_path)
    with TestClient(_app(world), base_url="https://testserver") as client:
        csrf = _login(client)
        headers = _headers(world.case, "case.read")
        rpc = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        missing = client.post("/api/complaint-workspace/mcp/rpc", json=rpc, headers=headers)
        assert missing.status_code == 403 and missing.json()["error"] == "csrf_rejected"
        weaker = client.post("/api/documents/formal-complaint", json={}, headers={**headers, "x-csrf-token": csrf})
        assert weaker.status_code == 403 and weaker.json()["error"] == "action_mismatch"
        trusted = client.post("/api/complaint-workspace/mcp/rpc", json={**rpc, "trusted_local": True}, headers={**headers, "x-csrf-token": csrf})
        assert trusted.status_code == 403 and trusted.json()["error"] == "trusted_local_not_production"
        logout = client.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": csrf})
        assert logout.status_code == 200
        denied = client.get("/api/claim-support/element-proof-cards", headers=_headers(world.case))
        assert denied.status_code == 401 and _SECRET not in denied.text
    assert world.mediator.calls == [] and world.workspace.calls == []


def test_missing_session_configuration_and_handler_mapping_fail_closed(tmp_path):
    world = _world(tmp_path)
    with TestClient(_app(world, sessions=False), base_url="https://testserver") as client:
        login = client.post("/api/complaint-workspace/auth/login", json={"credential": OWNER_CREDENTIAL})
        denied = client.get("/api/claim-support/element-proof-cards", headers=_headers(world.case))
        assert login.status_code == 503 and denied.status_code == 503
        assert denied.json()["error"] == "authentication_unavailable"
    with TestClient(_app(world, handlers=False), base_url="https://testserver") as client:
        _login(client)
        unavailable = client.get("/api/claim-support/element-proof-cards", headers=_headers(world.case))
        assert unavailable.status_code == 503 and unavailable.json()["error"] == "case_handler_unavailable"
    assert world.mediator.calls == [] and world.workspace.calls == []


def test_case_handlers_and_downloads_cannot_cross_case_boundaries(tmp_path):
    world = _world(tmp_path)
    other_case = world.cases.create_case(actor_principal_id=world.owner.principal_id)
    other_mediator, other_workspace = _Mediator("other-synthetic-case"), _Workspace("other-synthetic-case")
    other_root = tmp_path / "other-downloads"
    other_root.mkdir()
    other_document = other_root / "other.txt"
    other_document.write_text("other-synthetic-case", encoding="utf-8")
    world.handlers.bind(other_case, mediator=other_mediator, workspace_service=other_workspace, download_root=other_root)
    with TestClient(_app(world), base_url="https://testserver") as client:
        _login(client)
        first = client.get("/api/claim-support/element-proof-cards", headers=_headers(world.case))
        second = client.get("/api/claim-support/element-proof-cards", headers=_headers(other_case))
        assert first.json()["cards"] == [_SECRET]
        assert second.json()["cards"] == ["other-synthetic-case"]
        cross = client.get("/api/documents/download", params={"path": str(other_document)}, headers=_headers(world.case))
        assert cross.status_code == 403 and "other-synthetic-case" not in cross.text
        allowed = client.get("/api/documents/download", params={"path": str(other_document)}, headers=_headers(other_case))
        assert allowed.status_code == 200 and allowed.text == "other-synthetic-case"
        trace = client.get("/api/documents/optimization-trace", params={"cid": "unbound-synthetic-cid"}, headers=_headers(world.case))
        assert trace.status_code == 403 and trace.json()["detail"] == "trace_reference_not_bound"
    assert len(world.mediator.calls) == 1 and len(other_mediator.calls) == 1
    with pytest.raises(CaseAccessError, match="case_handler_reused"):
        _reuse_case_handler(world, other_case)


def _reuse_case_handler(world, other_case):
    registry = CaseHandlerRegistry()
    registry.bind(world.case, mediator=world.mediator, workspace_service=world.workspace)
    registry.bind(other_case, mediator=world.mediator, workspace_service=_Workspace())


def test_membership_requires_key_grant_and_mcp_method_cannot_downgrade_permission(tmp_path):
    world = _world(tmp_path)
    world.authorizer.grant_assigned_lawyer(owner_principal_id=world.owner.principal_id,
        lawyer_principal_id=world.lawyer.principal_id, case_id=world.case.case_id,
        resource_id=world.case.resource_id, tenant_id=world.case.tenant_id,
        actions={"case.read"}, expected_case_revision=world.case.revision)
    headers = _headers(world.case, "case.read")
    headers["x-expected-membership-revision"] = "1"
    with TestClient(_app(world), base_url="https://testserver") as client:
        csrf = _login(client, LAWYER_CREDENTIAL)
        denied = client.get("/api/complaint-workspace/mcp/tools", headers=headers)
        assert denied.status_code == 403 and denied.json()["error"] == "case_key_grant_required"
        forged = client.post("/api/complaint-workspace/mcp/call",
            json={"tool_name": "complaint.update_draft", "method": "ping", "arguments": {}},
            headers={**headers, "x-csrf-token": csrf})
        assert forged.status_code == 403 and forged.json()["error"] == "action_mismatch"
    assert world.mediator.calls == [] and world.workspace.calls == []


def test_uncomposed_legacy_review_and_document_routers_fail_closed(tmp_path):
    from applications.review_api import attach_claim_support_review_routes
    from applications.document_api import attach_document_routes
    world = _world(tmp_path)
    app = FastAPI()
    attach_claim_support_review_routes(app, world.mediator)
    attach_document_routes(app, world.mediator)
    with TestClient(app, base_url="https://testserver") as client:
        for path in ("/api/claim-support/element-proof-cards", "/api/documents/download?path=unbound"):
            response = client.get(path)
            assert response.status_code == 401 and response.json()["detail"] == "authorizer_required"
    assert world.mediator.calls == []


async def _asgi_post(app, path, headers, receive):
    sent = []

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
             "http_version": "1.1", "method": "POST", "scheme": "https", "path": path,
             "raw_path": path.encode(), "query_string": b"", "root_path": "",
             "server": ("testserver", 443), "client": ("synthetic", 1),
             "headers": [(key.lower().encode(), str(value).encode()) for key, value in headers.items()]}
    await app(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return start["status"], json.loads(body)


def _wire_credentials(client, csrf, case):
    return {**_headers(case), "cookie": f"{SESSION_COOKIE}={client.cookies.get(SESSION_COOKIE)}",
            "x-csrf-token": csrf, "content-type": "application/json"}


@pytest.mark.parametrize("mode", ["missing_cookie", "invalid_cookie", "missing_csrf"])
def test_private_body_is_never_read_before_session_and_csrf_verification(tmp_path, mode):
    world = _world(tmp_path)
    app = _app(world)
    reads = []

    async def forbidden_receive():
        reads.append(True)
        raise AssertionError("unauthenticated request body was read")

    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client)
        headers = _wire_credentials(client, csrf, world.case)
        headers["content-length"] = "999999999"
        if mode == "missing_cookie":
            headers.pop("cookie")
        elif mode == "invalid_cookie":
            headers["cookie"] = f"{SESSION_COOKIE}=synthetic-invalid-cookie"
        else:
            headers.pop("x-csrf-token")
        status, payload = asyncio.run(_asgi_post(app, "/api/complaint-workspace/mcp/rpc", headers, forbidden_receive))
    assert status == (403 if mode == "missing_csrf" else 401)
    assert payload["error"] in {"session_required", "authentication_failed", "csrf_rejected"}
    assert reads == []
    assert world.mediator.calls == [] and world.workspace.calls == []


def test_json_admission_bounds_actual_bytes_not_only_content_length(tmp_path):
    world = _world(tmp_path)
    app = _app(world, json_body_limits=CaseJSONBodyLimits(max_bytes=256, read_timeout_seconds=0.2))
    reads = []

    async def oversized_receive():
        reads.append(True)
        return {"type": "http.request", "body": b"{" + b" " * 1024 + b"}", "more_body": False}

    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client)
        headers = _wire_credentials(client, csrf, world.case)
        headers["content-length"] = "1"
        status, payload = asyncio.run(_asgi_post(app, "/api/complaint-workspace/mcp/rpc", headers, oversized_receive))
    assert status == 413 and payload["error"] == "request_body_too_large"
    assert len(reads) == 1
    assert world.mediator.calls == [] and world.workspace.calls == []


def test_declared_oversized_json_is_rejected_without_reading(tmp_path):
    world = _world(tmp_path)
    app = _app(world, json_body_limits=CaseJSONBodyLimits(max_bytes=256))
    reads = []

    async def forbidden_receive():
        reads.append(True)
        raise AssertionError("declared oversized body was read")

    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client)
        headers = _wire_credentials(client, csrf, world.case)
        headers["content-length"] = "257"
        status, payload = asyncio.run(_asgi_post(app, "/api/complaint-workspace/mcp/rpc", headers, forbidden_receive))
    assert status == 413 and payload["error"] == "request_body_too_large"
    assert reads == []
    assert world.mediator.calls == [] and world.workspace.calls == []


def test_slow_json_body_is_cancelled_at_admission_deadline(tmp_path):
    world = _world(tmp_path)
    app = _app(world, json_body_limits=CaseJSONBodyLimits(max_bytes=256, read_timeout_seconds=0.02))
    events = []

    async def slow_receive():
        events.append("read")
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            events.append("cancelled")
            raise
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def bounded_request(headers):
        return await asyncio.wait_for(_asgi_post(app, "/api/complaint-workspace/mcp/rpc", headers, slow_receive), timeout=1)

    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client)
        status, payload = asyncio.run(bounded_request(_wire_credentials(client, csrf, world.case)))
    assert status == 408 and payload["error"] == "request_body_timeout"
    assert events == ["read", "cancelled"]
    assert world.mediator.calls == [] and world.workspace.calls == []


def test_multipart_claimed_user_is_unqualified_and_never_reaches_mediator(tmp_path):
    world = _world(tmp_path)
    app = _app(world)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client)
        headers = {**_headers(world.case), "x-csrf-token": csrf}
        response = client.post("/api/claim-support/upload-document", headers=headers,
            data={"user_id": world.stranger.principal_id},
            files={"file": ("synthetic.txt", b"synthetic multipart marker", "text/plain")})
        assert response.status_code == 415
        assert response.json()["error"] == "upload_transport_unqualified"
        reads = []

        async def forbidden_receive():
            reads.append(True)
            raise AssertionError("unqualified multipart was parsed")

        wire = _wire_credentials(client, csrf, world.case)
        wire["content-type"] = "multipart/form-data; boundary=synthetic-boundary"
        status, payload = asyncio.run(_asgi_post(app, "/api/claim-support/upload-document", wire, forbidden_receive))
        assert status == 415 and payload["error"] == "upload_transport_unqualified"
        assert reads == []
    assert world.mediator.calls == [] and world.workspace.calls == []


def test_session_revocation_during_body_admission_is_rechecked(tmp_path):
    world = _world(tmp_path)
    app = _app(world)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client)
        token = client.cookies.get(SESSION_COOKIE)

        async def revoked_receive():
            world.sessions.logout(token, csrf_token=csrf)
            return {"type": "http.request", "body": b'{"jsonrpc":"2.0","id":1,"method":"ping"}', "more_body": False}

        status, payload = asyncio.run(_asgi_post(app, "/api/complaint-workspace/mcp/rpc",
            _wire_credentials(client, csrf, world.case), revoked_receive))
    assert status == 401 and payload["error"] == "authentication_failed"
    assert world.mediator.calls == [] and world.workspace.calls == []


def test_json_message_population_is_bounded_even_for_empty_chunks(tmp_path):
    world = _world(tmp_path)
    app = _app(world, json_body_limits=CaseJSONBodyLimits(max_bytes=256, max_messages=2))
    reads = []

    async def empty_receive():
        reads.append(True)
        return {"type": "http.request", "body": b"", "more_body": True}

    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client)
        status, payload = asyncio.run(_asgi_post(app, "/api/complaint-workspace/mcp/rpc",
            _wire_credentials(client, csrf, world.case), empty_receive))
    assert status == 413 and payload["error"] == "request_body_too_many_messages"
    assert len(reads) == 3
    assert world.mediator.calls == [] and world.workspace.calls == []


def test_anonymous_login_has_explicit_small_json_admission(tmp_path):
    world = _world(tmp_path)
    app = _app(world)
    reads = []

    async def forbidden_receive():
        reads.append(True)
        raise AssertionError("declared oversized login body was read")

    status, payload = asyncio.run(_asgi_post(app, "/api/complaint-workspace/auth/login",
        {"content-type": "application/json", "content-length": str(16 * 1024 + 1)}, forbidden_receive))
    assert status == 413 and payload["error"] == "request_body_too_large"
    assert reads == []
    assert world.mediator.calls == [] and world.workspace.calls == []
