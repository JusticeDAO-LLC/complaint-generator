"""HTTP and MCP carry the shared WorkflowActionService inquiry contract.

A real workspace transition supplies the pending inquiry id, question
revision, interview action, explanation, graph targets, and expected updates.
A stale revision or a different inquiry id is an explicit conflict and leaves
the current graph revision in place. Omitting the expected revision still
follows the service rule and may advance. Multi-chunk ASGI bodies are not
rewritten, and this module does not claim WebSocket or SSE support.
"""

from __future__ import annotations

import json
import os
import hashlib
import time
from contextvars import copy_context
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.case_routes import (
    INQUIRY_CONFLICT_STATUS,
    _inquiry_conflict_send,
    shared_inquiry_conflict,
)
from applications.complaint_mcp_protocol import tool_list_payload
from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import create_complaint_workspace_router
from applications.browser_sessions import (BrowserSessionConfiguration, BrowserSessionService,
    PrincipalStoreCredentialAdapter, SESSION_COOKIE)
from applications.case_access import CaseActionAuthorizer
from applications.case_directory import CaseDirectory, legacy_owner_only_binding
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from applications.complaint_workspace import WorkspaceAccess, WorkspaceAuthorizationDenied, workspace_access_scope
from applications.workspace_case_authority import (WorkspaceCaseAuthority, WorkspaceCaseAuthorityError,
    issue_workspace_case_authority, workspace_case_authority_scope)
from integrations.private_storage import PrivateArtifactBinding, seal_private_artifact

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

USER_ID = "synthetic-gui-14"
NARRATIVE = "On March 4, 2024 supervisor Alex Rivera fired me after I reported safety concerns."
ANSWER = "Alex Rivera was my supervisor at Northwind Tools and fired me on March 4, 2024."
PASSPHRASE = "synthetic-gui-14-passphrase"


def _service(tmp_path: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(USER_ID, USER_ID)
    return service


def _client(service: ComplaintWorkspaceService) -> TestClient:
    app = FastAPI()
    app.include_router(create_complaint_workspace_router(service, trusted_local=True))
    return TestClient(app)


def _fingerprint(body: dict) -> tuple:
    interview = body.get("interview") if isinstance(body.get("interview"), dict) else {}
    graph = interview.get("graph") if isinstance(interview.get("graph"), dict) else {}
    return (
        interview.get("session_revision"),
        interview.get("expected_question_revision"),
        interview.get("answered_count"),
        graph.get("graph_version"),
        graph.get("entity_count"),
        (interview.get("inquiry") or {}).get("inquiry_id") if isinstance(interview.get("inquiry"), dict) else None,
    )


def _assert_contract(body: dict) -> dict:
    interview = body["interview"]
    inquiry = interview["inquiry"]
    assert body["pending_inquiry_id"] == inquiry["inquiry_id"]
    assert body["pending_inquiry_id"].startswith("inq-")
    assert body["inquiry"]["inquiry_id"] == inquiry["inquiry_id"]
    assert body["expected_question_revision"] == interview["expected_question_revision"]
    assert body["expected_question_revision"] == inquiry["revision"]
    assert body["interview_action"] == interview["action"]
    assert body["explanation"]["source"] == "WorkflowActionService"
    assert body["explanation"]["why_it_matters"] == inquiry.get("why_it_matters")
    assert body["explanation"]["grounding_status"] == inquiry.get("grounding_status")
    targets = body["graph_targets"]
    assert targets["objective_id"] == inquiry.get("objective_id")
    assert targets["target_id"] == inquiry.get("target_id")
    assert targets["target_revision"] == inquiry.get("target_revision")
    assert targets["graph_id"] == interview["graph"]["graph_id"]
    assert targets["graph_version"] == interview["graph"]["graph_version"]
    assert targets["session_revision"] == interview["session_revision"]
    assert targets["legal_sufficiency"] is False
    assert body["expected_updates"] == inquiry.get("expected_update_contract")
    assert body["legal_sufficiency"] is False
    return inquiry


def test_http_carries_service_inquiry_and_conflicts_do_not_advance(tmp_path: Path) -> None:
    client = _client(_service(tmp_path))
    started = client.post(
        "/api/complaint-workspace/intake-chat",
        json={"user_id": USER_ID, "message": NARRATIVE, "question_id": "original_complaint", "interview_action": "start"},
    )
    assert started.status_code == 200, started.text
    started_body = started.json()
    inquiry = _assert_contract(started_body)
    assert started_body["interview_action"] == "start"
    assert started_body["conflict"] is None
    assert started_body["interview"]["status"] == "awaiting_user"
    before = _fingerprint(started_body)

    stale = client.post(
        "/api/complaint-workspace/intake-chat",
        json={
            "user_id": USER_ID,
            "message": "This stale answer must not change the graph.",
            "question_id": inquiry["inquiry_id"],
            "expected_question_revision": int(inquiry["revision"]) + 3,
            "interview_action": "answer",
        },
    )
    assert stale.status_code == INQUIRY_CONFLICT_STATUS
    stale_body = stale.json()
    _assert_contract(stale_body)
    assert stale_body["conflict"] == "stale_question"
    assert stale_body["interview"]["status"] == "refused"
    assert stale_body["interview"]["error"]["code"] == "stale_question"
    assert stale_body["interview_action"] == "answer"
    assert _fingerprint(stale_body) == before

    mismatched = client.post(
        "/api/complaint-workspace/intake-chat",
        json={
            "user_id": USER_ID,
            "message": "This answer names a different inquiry.",
            "question_id": "inq-not-the-pending-question",
            "expected_question_revision": inquiry["revision"],
            "interview_action": "answer",
        },
    )
    assert mismatched.status_code == INQUIRY_CONFLICT_STATUS
    mismatched_body = mismatched.json()
    assert mismatched_body["conflict"] == "stale_question"
    assert mismatched_body["pending_inquiry_id"] == inquiry["inquiry_id"]
    assert _fingerprint(mismatched_body) == before

    status = client.post(
        "/api/complaint-workspace/intake-chat",
        json={"user_id": USER_ID, "interview_action": "status"},
    )
    assert status.status_code == 200
    status_body = status.json()
    _assert_contract(status_body)
    assert status_body["interview_action"] == "status"
    assert status_body["conflict"] is None
    assert _fingerprint(status_body) == before

    advanced = client.post(
        "/api/complaint-workspace/intake-chat",
        json={
            "user_id": USER_ID,
            "message": ANSWER,
            "question_id": inquiry["inquiry_id"],
            "interview_action": "answer",
        },
    )
    assert advanced.status_code == 200, advanced.text
    advanced_body = advanced.json()
    _assert_contract(advanced_body)
    assert advanced_body["conflict"] is None
    error = advanced_body["interview"].get("error")
    if error is not None:
        assert error["code"] == "provider_unavailable"
        assert error["resumable"] is True
    assert _fingerprint(advanced_body) != before
    assert advanced_body["interview"]["answered_count"] == started_body["interview"]["answered_count"] + 1
    assert advanced_body["interview"]["session_revision"] == started_body["interview"]["session_revision"] + 1
    client.close()


def test_mcp_schema_and_stale_call_conflict(tmp_path: Path) -> None:
    service = _service(tmp_path)
    listed = tool_list_payload(service)
    schema = next(item["inputSchema"] for item in listed["tools"] if item["name"] == "complaint.run_intake_chat_turn")
    assert "expected_question_revision" in schema["properties"]
    assert "interview_action" in schema["properties"]
    assert "question_id" in schema["properties"]

    client = _client(service)
    started = client.post(
        "/api/complaint-workspace/mcp/rpc",
        json={
            "jsonrpc": "2.0",
            "id": "start-1",
            "method": "tools/call",
            "params": {
                "name": "complaint.run_intake_chat_turn",
                "arguments": {
                    "user_id": USER_ID,
                    "message": NARRATIVE,
                    "question_id": "original_complaint",
                    "interview_action": "start",
                },
            },
        },
    )
    assert started.status_code == 200, started.text
    started_result = started.json()["result"]
    assert started_result["isError"] is False
    started_body = started_result["structuredContent"]
    inquiry = _assert_contract(started_body)
    before = _fingerprint(started_body)

    stale = client.post(
        "/api/complaint-workspace/mcp/call",
        json={
            "tool_name": "complaint.run_intake_chat_turn",
            "arguments": {
                "user_id": USER_ID,
                "message": "MCP stale answer",
                "question_id": inquiry["inquiry_id"],
                "expected_question_revision": int(inquiry["revision"]) + 9,
                "interview_action": "answer",
            },
        },
    )
    assert stale.status_code == INQUIRY_CONFLICT_STATUS
    stale_body = stale.json()
    assert stale_body["isError"] is True
    assert stale_body["conflict"] == "stale_question"
    _assert_contract(stale_body)
    assert _fingerprint(stale_body) == before

    current = client.post(
        "/api/complaint-workspace/mcp/rpc",
        json={
            "jsonrpc": "2.0",
            "id": "status-1",
            "method": "tools/call",
            "params": {
                "name": "complaint.run_intake_chat_turn",
                "arguments": {"user_id": USER_ID, "interview_action": "status"},
            },
        },
    )
    assert current.status_code == 200
    current_body = current.json()["result"]["structuredContent"]
    assert current.json()["result"]["isError"] is False
    assert _fingerprint(current_body) == before

    matched = client.post(
        "/api/complaint-workspace/mcp/rpc",
        json={
            "jsonrpc": "2.0",
            "id": "answer-1",
            "method": "tools/call",
            "params": {
                "name": "complaint.run_intake_chat_turn",
                "arguments": {
                    "user_id": USER_ID,
                    "message": ANSWER,
                    "question_id": inquiry["inquiry_id"],
                    "expected_question_revision": inquiry["revision"],
                    "interview_action": "answer",
                },
            },
        },
    )
    assert matched.status_code == 200, matched.text
    matched_result = matched.json()["result"]
    assert matched_result["isError"] is False
    assert matched_result["conflict"] is None
    matched_body = matched_result["structuredContent"]
    _assert_contract(matched_body)
    assert matched_body["interview"]["session_revision"] == started_body["interview"]["session_revision"] + 1
    assert "MCP stale answer" not in matched.text
    client.close()


def test_route_boundary_rewrites_stale_inquiry_to_conflict() -> None:
    assert shared_inquiry_conflict({"interview": {"status": "awaiting_user", "error": None}}) is False
    assert shared_inquiry_conflict({"status": "refused", "error": {"code": "stale_question"}}) is False

    payload = {
        "interview": {
            "action": "answer",
            "status": "refused",
            "inquiry": {"inquiry_id": "inq-current", "revision": 2},
            "expected_question_revision": 2,
            "error": {"code": "stale_question", "resumable": True},
        }
    }
    ok_payload = {"interview": {"action": "status", "status": "awaiting_user", "error": None}}

    def _exchange(path: str, body: dict) -> list:
        captured = []

        async def send(message):
            captured.append(message)

        wrapped = _inquiry_conflict_send(path, send)
        encoded = json.dumps(body).encode("utf-8")
        import asyncio
        asyncio.run(wrapped({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]}))
        asyncio.run(wrapped({"type": "http.response.body", "body": encoded, "more_body": False}))
        return captured

    conflict = _exchange("/api/complaint-workspace/intake-chat", payload)
    assert conflict[0]["status"] == INQUIRY_CONFLICT_STATUS
    echoed = json.loads(conflict[1]["body"])
    assert echoed["interview"]["inquiry"]["inquiry_id"] == "inq-current"
    assert shared_inquiry_conflict(echoed) is True

    unchanged = _exchange("/api/complaint-workspace/session", payload)
    assert unchanged[0]["status"] == 200

    healthy = _exchange("/api/complaint-workspace/mcp/rpc", ok_payload)
    assert healthy[0]["status"] == 200


def _asgi_stale_inquiry_bytes() -> bytes:
    return json.dumps({"interview": {"action": "answer", "status": "refused",
        "error": {"code": "stale_question", "resumable": True}}}).encode()


def _asgi_response_messages(path, status, chunks):
    """Run a real ASGI exchange with a strict response-message consumer."""
    import asyncio
    headers = [(b"content-type", b"application/json"), (b"x-synthetic", b"preserved"),
        (b"set-cookie", b"one=1"), (b"set-cookie", b"two=2"),
        (b"content-length", str(sum(len(body) for body, _more in chunks)).encode())]
    expected = [{"type": "http.response.start", "status": status, "headers": headers}]
    expected.extend({"type": "http.response.body", "body": body, "more_body": more}
        for body, more in chunks)
    observed = []

    async def app(scope, receive, send):
        wrapped = _inquiry_conflict_send(scope["path"], send)
        for message in expected:
            await wrapped(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            assert not any(item["type"] == "http.response.start" for item in observed), "duplicate ASGI response start"
        if message["type"] == "http.response.body":
            assert observed and observed[0]["type"] == "http.response.start"
        observed.append(message)

    asyncio.run(app({"type": "http", "path": path, "method": "POST"}, receive, send))
    return observed, expected


@pytest.mark.parametrize("path,status,chunks", [
    ("/api/complaint-workspace/intake-chat", 200, [(b"stream-prefix", True), (_asgi_stale_inquiry_bytes(), False)]),
    ("/api/complaint-workspace/mcp/rpc", 202, [(b"\x00\xff", True), (_asgi_stale_inquiry_bytes(), False)]),
    ("/api/complaint-workspace/intake-chat", 409, [(b"stream-prefix", True), (_asgi_stale_inquiry_bytes(), False)]),
    ("/api/complaint-workspace/intake-chat", 200, [(b"", True), (_asgi_stale_inquiry_bytes(), False)]),
    ("/api/complaint-workspace/mcp/call", 200, [(b"\x00", True), (b"\xff\xfe", True), (b"", False)]),
    ("/api/complaint-workspace/session", 200, [(b"stream-prefix", True), (_asgi_stale_inquiry_bytes(), False)]),
])
def test_asgi_stream_forwards_exactly_one_start_and_all_original_chunks(path, status, chunks):
    assert shared_inquiry_conflict(json.loads(_asgi_stale_inquiry_bytes())) is True
    observed, expected = _asgi_response_messages(path, status, chunks)
    assert observed == expected
    assert sum(message["type"] == "http.response.start" for message in observed) == 1


@pytest.mark.parametrize("path,status,body", [
    ("/api/complaint-workspace/intake-chat", 403, _asgi_stale_inquiry_bytes()),
    ("/api/complaint-workspace/mcp/rpc", 422, _asgi_stale_inquiry_bytes()),
    ("/api/complaint-workspace/session", 200, _asgi_stale_inquiry_bytes()),
    ("/api/complaint-workspace/intake-chat", 200, b"\x00\xffnot-json\xfe"),
])
def test_asgi_single_body_preserves_non_success_unrelated_and_raw_responses(path, status, body):
    observed, expected = _asgi_response_messages(path, status, [(body, False)])
    assert observed == expected


def _composed_case_world(tmp_path, *, legacy=False):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    stranger = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    if legacy:
        legacy_payload = json.dumps({"user_id": owner.principal_id, "synthetic": True}).encode()
        envelope = seal_private_artifact(legacy_payload, binding=legacy_owner_only_binding(owner.principal_id),
            key=case_key, key_id="case-key")
        case, _ = cases.adopt_owner_only_case(actor_principal_id=owner.principal_id, envelope=envelope)
    else:
        case = cases.create_case(actor_principal_id=owner.principal_id)
    second = cases.create_case(actor_principal_id=owner.principal_id)
    foreign = cases.create_case(actor_principal_id=stranger.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    clock = {"now": time.time()}
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {"synthetic-owner-credential": owner.principal_id,
            "synthetic-stranger-credential": stranger.principal_id, "synthetic-lawyer-credential": lawyer.principal_id}),
        signing_key=os.urandom(32), ttl_seconds=300), clock=lambda: clock["now"])
    handlers = CaseHandlerRegistry()
    services = {}
    for selected in (case, second, foreign):
        service = ComplaintWorkspaceService(root_dir=tmp_path / "workspaces" / selected.case_id)
        # Operator fixture provisioning happens before any request. The app
        # uses real browser sessions throughout, with no trusted-local router.
        service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
        service.ensure_private_case_key(selected.tenant_id, selected.case_id)
        handlers.bind(selected, mediator=service, workspace_service=service,
            authorize_delegated=lambda _decision: True)
        services[selected.case_id] = service
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        include_review=False, include_document=False)
    return SimpleNamespace(principals=principals, owner=owner, stranger=stranger, lawyer=lawyer,
        cases=cases, case=case, second=second, foreign=foreign, authorizer=authorizer,
        sessions=sessions, handlers=handlers, services=services, app=app, clock=clock)


def _composed_headers(case, csrf=None):
    headers = {"x-tenant-id": case.tenant_id, "x-case-id": case.case_id,
        "x-resource-id": case.resource_id, "x-expected-revision": str(case.revision)}
    if csrf is not None:
        headers["x-csrf-token"] = csrf
    return headers


def _composed_login(client, credential="synthetic-owner-credential"):
    login = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert login.status_code == 200
    assert client.cookies.get(SESSION_COOKIE)
    return login.json()["csrf_token"]


def _composed_ciphertext_snapshot(service):
    root = service._session_dir / "joined-revisions"
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()}


def test_composed_cookie_http_mcp_inquiry_uses_canonical_owner_and_read_only_session(tmp_path):
    world = _composed_case_world(tmp_path)
    case = world.case
    assert case.tenant_id != world.owner.principal_id
    with TestClient(world.app, base_url="https://testserver") as client:
        denied = client.post("/api/complaint-workspace/intake-chat", headers=_composed_headers(case),
            json={"message": NARRATIVE, "interview_action": "start"})
        assert denied.status_code == 401
        csrf = _composed_login(client)
        no_csrf = client.post("/api/complaint-workspace/intake-chat", headers=_composed_headers(case),
            json={"message": NARRATIVE, "interview_action": "start"})
        assert no_csrf.status_code == 403
        headers = _composed_headers(case, csrf)
        started = client.post("/api/complaint-workspace/intake-chat", headers=headers,
            json={"message": NARRATIVE, "question_id": "original_complaint", "interview_action": "start"})
        assert started.status_code == 200, started.text
        body = started.json()
        inquiry = _assert_contract(body)
        assert body["interview"]["graph"]["entity_count"] > 0
        before = _fingerprint(body)
        service = world.services[case.case_id]
        ciphertext = _composed_ciphertext_snapshot(service)
        assert ciphertext
        assert any(path.is_file() and path.read_bytes().startswith(b"CGPE")
            for path in (service._session_dir / "joined-revisions").rglob("*"))
        session = client.get("/api/complaint-workspace/session", headers=_composed_headers(case))
        assert session.status_code == 200, session.text
        state = session.json()["session"]
        assert state["user_id"] == case.tenant_id
        assert state["case_id"] == case.case_id
        graph = state["shared_interview"]
        assert graph["knowledge_graph"]["entities"]
        assert graph["dependency_graph"].get("nodes") or graph["dependency_graph"].get("requirements")
        assert _composed_ciphertext_snapshot(service) == ciphertext
        identity = client.get("/api/complaint-workspace/auth/session")
        assert identity.status_code == 200
        assert identity.json()["principal_id"] == world.owner.principal_id
        stale = client.post("/api/complaint-workspace/mcp/call", headers=headers, json={
            "tool_name": "complaint.run_intake_chat_turn", "arguments": {"message": "synthetic stale answer",
                "question_id": inquiry["inquiry_id"], "expected_question_revision": inquiry["revision"] + 1,
                "interview_action": "answer"}})
        assert stale.status_code == 409, stale.text
        assert _fingerprint(stale.json()) == before
        answered = client.post("/api/complaint-workspace/mcp/rpc", headers=headers, json={
            "jsonrpc": "2.0", "id": "composed-answer", "method": "tools/call", "params": {
                "name": "complaint.run_intake_chat_turn", "arguments": {"message": ANSWER,
                    "question_id": inquiry["inquiry_id"], "expected_question_revision": inquiry["revision"],
                    "interview_action": "answer"}}})
        assert answered.status_code == 200, answered.text
        result = answered.json()["result"]
        assert result["isError"] is False
        updated = result["structuredContent"]
        _assert_contract(updated)
        assert updated["interview"]["answered_count"] == body["interview"]["answered_count"] + 1
        assert updated["interview"]["session_revision"] == body["interview"]["session_revision"] + 1


def test_composed_cross_actor_case_and_delegated_policy_cannot_use_owner_master(tmp_path):
    world = _composed_case_world(tmp_path)
    case = world.case
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        headers = _composed_headers(case, csrf)
        for damage in ({"user_id": case.tenant_id}, {"user_id": world.stranger.principal_id},
                {"actor_principal_id": world.stranger.principal_id}):
            denied = client.post("/api/complaint-workspace/intake-chat", headers=headers,
                json={"message": NARRATIVE, "interview_action": "start", **damage})
            assert denied.status_code == 403
        wrong = _composed_headers(case)
        wrong["x-resource-id"] = world.foreign.resource_id
        assert client.get("/api/complaint-workspace/session", headers=wrong).status_code == 403
        assert client.get("/api/complaint-workspace/session", headers=_composed_headers(world.foreign)).status_code == 403
        _composed_login(client, "synthetic-stranger-credential")
        assert client.get("/api/complaint-workspace/session", headers=_composed_headers(case)).status_code == 403
        grant = world.authorizer.grant_assigned_lawyer(owner_principal_id=world.owner.principal_id,
            lawyer_principal_id=world.lawyer.principal_id, case_id=case.case_id, resource_id=case.resource_id,
            tenant_id=case.tenant_id, actions={"case.read"}, expected_case_revision=case.revision)
        _composed_login(client, "synthetic-lawyer-credential")
        delegated_headers = {**_composed_headers(case), "x-expected-membership-revision": str(grant.revision)}
        denied = client.get("/api/complaint-workspace/session", headers=delegated_headers)
        assert denied.status_code == 403, denied.text
        assert not _composed_ciphertext_snapshot(world.services[case.case_id])


@pytest.mark.parametrize("legacy", [False, True])
def test_issued_case_authority_rejects_copies_wrong_scope_and_retained_handles(tmp_path, legacy):
    world = _composed_case_world(tmp_path, legacy=legacy)
    case = world.case
    issued = world.sessions.login({"credential": "synthetic-owner-credential"})
    decision = world.authorizer.authorize(boundary="http", actor_principal_id=world.owner.principal_id,
        tenant_id=case.tenant_id, case_id=case.case_id, resource_id=case.resource_id,
        action="case.update", expected_revision=case.revision)
    authority = issue_workspace_case_authority(authorizer=world.authorizer, sessions=world.sessions,
        token=issued.token, decision=decision, registry=world.handlers)
    class SpoofedAuthority(WorkspaceCaseAuthority):
        def __hash__(self):
            return hash(authority)

        def __eq__(self, other):
            return other is authority

    for fake in (replace(authority), SimpleNamespace(**authority.__dict__), SpoofedAuthority(**authority.__dict__)):
        with pytest.raises(WorkspaceCaseAuthorityError):
            with workspace_case_authority_scope(fake):
                pytest.fail("unissued context admitted")
    service = world.services[case.case_id]
    binding = PrivateArtifactBinding(tenant_id=case.tenant_id, case_id=case.case_id,
        principal_id=case.tenant_id, artifact_kind="session", revision="session-v1")
    with workspace_case_authority_scope(authority), workspace_access_scope(
            WorkspaceAccess.authenticated(world.owner.principal_id, case_id=case.case_id)):
        provider = service.private_key_provider()
        key_id, key = provider.resolve(binding)
        assert isinstance(key_id, str) and len(key) == 32
        with pytest.raises(WorkspaceAuthorizationDenied):
            world.services[world.second.case_id].private_key_provider()
        with workspace_access_scope(WorkspaceAccess.authenticated(world.stranger.principal_id, case_id=case.case_id)):
            with pytest.raises(WorkspaceAuthorizationDenied):
                service.private_key_provider()
        with workspace_access_scope(WorkspaceAccess.authenticated(world.owner.principal_id, case_id=world.second.case_id)):
            with pytest.raises(WorkspaceAuthorizationDenied):
                service.private_key_provider()
        copied = copy_context()
    assert world.sessions.authenticate_token(issued.token).principal_id == world.owner.principal_id
    with pytest.raises(WorkspaceAuthorizationDenied):
        provider.resolve(binding)
    other = world.second
    other_decision = world.authorizer.authorize(boundary="http", actor_principal_id=world.owner.principal_id,
        tenant_id=other.tenant_id, case_id=other.case_id, resource_id=other.resource_id,
        action="case.update", expected_revision=other.revision)
    other_authority = issue_workspace_case_authority(authorizer=world.authorizer, sessions=world.sessions,
        token=issued.token, decision=other_decision, registry=world.handlers)
    with workspace_case_authority_scope(other_authority), workspace_access_scope(
            WorkspaceAccess.authenticated(world.owner.principal_id, case_id=other.case_id)):
        with pytest.raises(WorkspaceAuthorizationDenied):
            provider.resolve(binding)
    with pytest.raises(WorkspaceAuthorizationDenied):
        copied.run(provider.resolve, binding)
    with pytest.raises(WorkspaceCaseAuthorityError):
        authority.revalidate(actor_principal_id=world.owner.principal_id)
    fresh = issue_workspace_case_authority(authorizer=world.authorizer, sessions=world.sessions,
        token=issued.token, decision=decision, registry=world.handlers)
    with workspace_case_authority_scope(fresh), workspace_access_scope(
            WorkspaceAccess.authenticated(world.owner.principal_id, case_id=case.case_id)):
        # The handle supplies no authority. A new real request may authorize
        # it again for the same exact service and canonical case/resource.
        assert provider.resolve(binding) == (key_id, key)
    with pytest.raises(WorkspaceAuthorizationDenied):
        provider.resolve(binding)


@pytest.mark.parametrize("change", ["logout", "rotation", "expiry", "registry"])
def test_live_session_revocation_rejects_an_already_issued_case_authority(tmp_path, change):
    world = _composed_case_world(tmp_path)
    case = world.case
    issued = world.sessions.login({"credential": "synthetic-owner-credential"})
    decision = world.authorizer.authorize(boundary="http", actor_principal_id=world.owner.principal_id,
        tenant_id=case.tenant_id, case_id=case.case_id, resource_id=case.resource_id,
        action="case.update", expected_revision=case.revision)
    authority = issue_workspace_case_authority(authorizer=world.authorizer, sessions=world.sessions,
        token=issued.token, decision=decision, registry=world.handlers)
    service = world.services[case.case_id]
    with workspace_case_authority_scope(authority), workspace_access_scope(
            WorkspaceAccess.authenticated(world.owner.principal_id, case_id=case.case_id)):
        provider = service.private_key_provider()
        if change == "logout":
            world.sessions.logout(issued.token, csrf_token=issued.csrf_token)
        elif change == "rotation":
            world.sessions.rotate(issued.token, csrf_token=issued.csrf_token)
        elif change == "expiry":
            world.clock["now"] += 301
        else:
            other = world.services[world.second.case_id]
            world.handlers._bindings[(case.tenant_id, case.case_id, case.resource_id)] = (other, other, None, None)
        with pytest.raises(WorkspaceAuthorizationDenied):
            provider.resolve(PrivateArtifactBinding(tenant_id=case.tenant_id, case_id=case.case_id,
                principal_id=case.tenant_id, artifact_kind="session", revision="session-v1"))
