"""Authenticated browser sessions fail closed without a declared verifier.

Positive cases log in through a principal-store credential adapter and receive
a server-issued cookie. Negative cases cover expiry, logout, rotation, forged
role and user identifiers, CSRF and cookie policy, and sanitized errors.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    SESSION_COOKIE,
    BrowserSessionConfiguration,
    BrowserSessionError,
    PrincipalStoreCredentialAdapter,
    VerifiedPrincipal,
    resolve_browser_session_service,
)
from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import attach_complaint_workspace_routes
from applications.principal_store import CANONICAL_ROLE, PrincipalStore

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

SECRET_MARKER = "synthetic-secret-marker"
PASSPHRASE = "synthetic-complainant-passphrase"
LAWYER_PASSPHRASE = "synthetic-lawyer-passphrase"


class _Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


class _ExplodingAdapter:
    def verify_credential(self, material: dict) -> VerifiedPrincipal:
        raise RuntimeError(f"provider blew up while checking {SECRET_MARKER}")


class _RecordingAdapter:
    def __init__(self, principal: VerifiedPrincipal) -> None:
        self.principal = principal
        self.materials: list[dict] = []

    def verify_credential(self, material: dict) -> VerifiedPrincipal:
        self.materials.append(dict(material))
        return self.principal


def _roster(tmp_path: Path) -> tuple[PrincipalStore, str, str]:
    store = PrincipalStore(tmp_path / "roster", key=os.urandom(32), key_id="gui05-roster")
    complainant = store.register_from_request({})
    lawyer = store.install_server_role(role="lawyer")
    return store, complainant.principal_id, lawyer.principal_id


def _service(tmp_path: Path, clock: _Clock, *, ttl: int = 60):
    store, complainant_id, lawyer_id = _roster(tmp_path)
    adapter = PrincipalStoreCredentialAdapter(
        store,
        {PASSPHRASE: complainant_id, LAWYER_PASSPHRASE: lawyer_id},
    )
    configuration = BrowserSessionConfiguration(adapter=adapter, signing_key=os.urandom(32), ttl_seconds=ttl)
    return resolve_browser_session_service(configuration, clock=clock), complainant_id, lawyer_id


def _client(tmp_path: Path, sessions, *, trusted_local: bool = False) -> TestClient:
    workspace = ComplaintWorkspaceService(tmp_path / "workspace")
    app = FastAPI()
    attach_complaint_workspace_routes(
        app,
        workspace,
        trusted_local=trusted_local,
        browser_sessions=sessions,
    )
    return TestClient(app, base_url="https://testserver")


def _cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def _assert_session_cookie(response, *, cleared: bool = False) -> str:
    issued = _cookie_headers(response)
    assert len(issued) == 1
    cookie = issued[0]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/" in cookie
    assert "Domain=" not in cookie
    value = cookie.split(";", 1)[0].split("=", 1)[1]
    if cleared:
        assert "Max-Age=0" in cookie
        return value
    assert "Max-Age=" in cookie
    assert "Max-Age=0" not in cookie
    session_id, mac = value.split(".", 1)
    assert session_id and len(mac) == 64
    assert value not in response.text
    return value


def _login(client: TestClient, passphrase: str = PASSPHRASE):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": passphrase})
    assert response.status_code == 200, response.text
    body = response.json()
    token = _assert_session_cookie(response)
    assert body["authenticated"] is True
    assert body["csrf_token"]
    assert token not in response.text
    assert passphrase not in response.text
    assert SECRET_MARKER not in response.text
    return body


def test_missing_provider_fails_closed_instead_of_trusted_local(tmp_path: Path) -> None:
    clock = _Clock()
    unavailable = resolve_browser_session_service(None, clock=clock)
    incomplete = resolve_browser_session_service(
        BrowserSessionConfiguration(adapter=None, signing_key=b"short", ttl_seconds=0),
        clock=clock,
    )
    undeclared = resolve_browser_session_service(
        BrowserSessionConfiguration(adapter=object(), signing_key=os.urandom(32), ttl_seconds=60),
        clock=clock,
    )
    assert unavailable.configured is False
    assert incomplete.configured is False
    assert undeclared.configured is False
    with pytest.raises(BrowserSessionError, match="authentication_unavailable"):
        unavailable.login({"credential": PASSPHRASE})

    client = _client(tmp_path, unavailable, trusted_local=True)
    login = client.post("/api/complaint-workspace/auth/login", json={"credential": PASSPHRASE})
    workspace = client.get("/api/complaint-workspace/session")
    whoami = client.get("/api/complaint-workspace/auth/session")
    for response in (login, workspace, whoami):
        assert response.status_code == 503
        assert response.json() == {"detail": "authentication_unavailable"}
        assert "trusted_local" not in response.text
        assert PASSPHRASE not in response.text
        assert _cookie_headers(response) == []


def test_login_uses_server_roles_and_cookie_policy(tmp_path: Path) -> None:
    clock = _Clock()
    sessions, complainant_id, lawyer_id = _service(tmp_path, clock)
    client = _client(tmp_path, sessions)
    denied = client.get("/api/complaint-workspace/auth/session")
    assert denied.status_code == 401
    assert denied.json()["detail"] == "session_required"

    complainant = _login(client, PASSPHRASE)
    assert complainant["principal_id"] == complainant_id
    assert complainant["roles"] == [CANONICAL_ROLE]
    assert complainant["generation"] == 1
    assert "lawyer" not in complainant["roles"]

    cookie = client.cookies.get(SESSION_COOKIE)
    bound = sessions.authenticate_token(cookie)
    assert "csrf_token" not in bound.public_view()
    whoami = client.get("/api/complaint-workspace/auth/session")
    assert whoami.status_code == 200
    assert whoami.json()["principal_id"] == complainant_id
    assert whoami.json() == complainant
    assert client.cookies.get(SESSION_COOKIE) == cookie
    assert sessions.authenticate_token(cookie) == bound
    assert _cookie_headers(whoami) == []

    # A browser session is not a private-case key grant and is not trusted-local.
    workspace = client.get("/api/complaint-workspace/session")
    assert workspace.status_code == 403
    assert workspace.json() == {"detail": "authorization_denied"}
    assert PASSPHRASE not in workspace.text

    client.cookies.clear()
    lawyer = _login(client, LAWYER_PASSPHRASE)
    assert lawyer["principal_id"] == lawyer_id
    assert lawyer["roles"] == ["lawyer"]
    assert lawyer["principal_id"] != complainant_id


def test_expiry_logout_and_rotation_bound_the_session(tmp_path: Path) -> None:
    clock = _Clock()
    sessions, complainant_id, _lawyer_id = _service(tmp_path, clock, ttl=30)
    client = _client(tmp_path, sessions)
    first = _login(client)
    assert first["absolute_expires_at"] - first["expires_at"] == 0
    original_cookie = client.cookies.get(SESSION_COOKIE)
    original_csrf = first["csrf_token"]

    clock.now += 20
    rotated = client.post(
        "/api/complaint-workspace/auth/rotate",
        headers={"x-csrf-token": original_csrf},
    )
    assert rotated.status_code == 200, rotated.text
    rotated_body = rotated.json()
    replacement = _assert_session_cookie(rotated)
    assert replacement != original_cookie
    assert rotated_body["generation"] == 2
    assert rotated_body["principal_id"] == complainant_id
    assert rotated_body["absolute_expires_at"] == first["absolute_expires_at"]
    assert rotated_body["csrf_token"] != original_csrf

    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, original_cookie)
    stale = client.get("/api/complaint-workspace/auth/session")
    assert stale.status_code == 401
    assert stale.json()["detail"] == "authentication_failed"
    assert original_csrf not in stale.text

    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, replacement)
    still_bound = client.get("/api/complaint-workspace/auth/session")
    assert still_bound.status_code == 200
    assert still_bound.json()["generation"] == 2

    clock.now = float(first["absolute_expires_at"])
    expired = client.get("/api/complaint-workspace/auth/session")
    assert expired.status_code == 401
    assert expired.json() == {"detail": "session_expired"}

    clock.now = 1_800_000_000.0
    client.cookies.clear()
    again = _login(client)
    logged_out = client.post(
        "/api/complaint-workspace/auth/logout",
        headers={"x-csrf-token": again["csrf_token"]},
    )
    assert logged_out.status_code == 200
    assert logged_out.json() == {"authenticated": False}
    _assert_session_cookie(logged_out, cleared=True)
    after = client.get("/api/complaint-workspace/auth/session")
    assert after.status_code == 401
    assert after.json()["detail"] in {"session_required", "authentication_failed"}
    assert complainant_id not in after.text


def test_forged_identifiers_and_csrf_are_rejected(tmp_path: Path) -> None:
    clock = _Clock()
    store, complainant_id, _lawyer_id = _roster(tmp_path)
    principal = VerifiedPrincipal(complainant_id, store.load(complainant_id).tenant_id, (CANONICAL_ROLE,))
    adapter = _RecordingAdapter(principal)
    sessions = resolve_browser_session_service(
        BrowserSessionConfiguration(adapter=adapter, signing_key=os.urandom(32), ttl_seconds=60),
        clock=clock,
    )
    client = _client(tmp_path, sessions)

    forged_role = client.post(
        "/api/complaint-workspace/auth/login",
        json={"credential": PASSPHRASE, "role": "operational_admin", "user_id": "forged-user"},
    )
    assert forged_role.status_code == 403
    assert forged_role.json() == {"detail": "identifier_rejected"}
    assert "operational_admin" not in forged_role.text
    assert "forged-user" not in forged_role.text
    assert adapter.materials == []
    assert _cookie_headers(forged_role) == []

    issued = _login(client)
    assert adapter.materials == [{"credential": PASSPHRASE}]
    forged_header = client.get(
        "/api/complaint-workspace/auth/session",
        headers={"x-role": "operational_admin"},
    )
    assert forged_header.status_code == 403
    assert forged_header.json()["detail"] == "identifier_rejected"

    forged_user = client.get(
        "/api/complaint-workspace/session",
        params={"user_id": "forged-user"},
    )
    assert forged_user.status_code == 403
    assert forged_user.json()["detail"] == "identifier_rejected"
    assert "forged-user" not in forged_user.text

    missing_csrf = client.post("/api/complaint-workspace/auth/rotate")
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["detail"] == "csrf_rejected"

    mismatched = client.post(
        "/api/complaint-workspace/auth/logout",
        headers={"x-csrf-token": "forged-csrf-token"},
    )
    assert mismatched.status_code == 403
    assert mismatched.json()["detail"] == "csrf_rejected"
    assert "forged-csrf-token" not in mismatched.text

    still = client.get("/api/complaint-workspace/auth/session")
    assert still.status_code == 200
    assert still.json()["principal_id"] == complainant_id
    assert still.json()["roles"] == [CANONICAL_ROLE]

    mac = client.cookies.get(SESSION_COOKIE).split(".", 1)[1]
    client.cookies.set(SESSION_COOKIE, f"forged-session.{mac}")
    forged_cookie = client.get("/api/complaint-workspace/auth/session")
    assert forged_cookie.status_code == 401
    assert forged_cookie.json()["detail"] == "authentication_failed"


def test_authentication_errors_are_sanitized(tmp_path: Path) -> None:
    clock = _Clock()
    sessions = resolve_browser_session_service(
        BrowserSessionConfiguration(adapter=_ExplodingAdapter(), signing_key=os.urandom(32), ttl_seconds=60),
        clock=clock,
    )
    client = _client(tmp_path, sessions)
    response = client.post(
        "/api/complaint-workspace/auth/login",
        json={"credential": SECRET_MARKER},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "authentication_failed"}
    assert SECRET_MARKER not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text
    assert _cookie_headers(response) == []

    unknown = client.post(
        "/api/complaint-workspace/auth/login",
        json={"credential": "not-a-registered-secret"},
    )
    store_sessions, _complainant_id, _lawyer_id = _service(tmp_path, clock)
    store_client = _client(tmp_path, store_sessions)
    unknown = store_client.post(
        "/api/complaint-workspace/auth/login",
        json={"credential": "not-a-registered-secret"},
    )
    assert unknown.status_code == 401
    assert unknown.json() == {"detail": "authentication_failed"}
    assert "missing_principal" not in unknown.text
    assert "not-a-registered-secret" not in unknown.text


