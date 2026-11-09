"""Resume the current authenticated browser transport without issuing authority."""
from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest
from fastapi.testclient import TestClient

from applications.browser_sessions import BrowserSessionError, SESSION_COOKIE
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
PATH = "/api/complaint-workspace/auth/session"


def _login(client):
    response = client.post("/api/complaint-workspace/auth/login",
        json={"credential": "synthetic-owner-credential"})
    assert response.status_code == 200, response.text
    return response.json()


def _ciphertext(world):
    return {str(p.relative_to(world.root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in world.root.rglob("*") if p.is_file()}


def _status(client, world, csrf=None):
    return client.post("/api/complaint-workspace/mcp/rpc",
        headers=_composed_headers(world.case, csrf), json={"jsonrpc": "2.0", "id": "resumed-status",
            "method": "tools/call", "params": {"name": "complaint.get_complaint_readiness", "arguments": {}}})


def test_resume_current_cookie_supplies_transport_csrf_without_changing_identity_or_case(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with TestClient(world.app, base_url="https://testserver") as client:
        issued = _login(client)
        cookie = client.cookies.get(SESSION_COOKIE)
        bound = world.sessions.authenticate_token(cookie)
        assert "csrf_token" not in bound.public_view()
        before = _ciphertext(world)
        resumed = client.get(PATH, headers={"origin": "https://testserver", "sec-fetch-site": "same-origin"})
        assert resumed.status_code == 200, resumed.text
        assert resumed.json() == issued
        assert resumed.headers.get_list("set-cookie") == []
        assert client.cookies.get(SESSION_COOKIE) == cookie
        assert world.sessions.authenticate_token(cookie) == bound
        assert cookie not in resumed.text and "synthetic-owner-credential" not in resumed.text
        assert set(resumed.headers["cache-control"].split(", ")) == {"private", "no-store"}
        assert resumed.headers["pragma"] == "no-cache" and resumed.headers["expires"] == "0"
        assert _ciphertext(world) == before
        for csrf in (None, "wrong-csrf-token"):
            denied = _status(client, world, csrf)
            assert denied.status_code == 403
            assert denied.json()["error"] == "csrf_rejected"
        status = _status(client, world, resumed.json()["csrf_token"])
        assert status.status_code == 200, status.text
        result = status.json()["result"]
        assert result["isError"] is False
        assert result["structuredContent"]["user_id"] == world.case.tenant_id
        assert _ciphertext(world) == before
        assert client.cookies.get(SESSION_COOKIE) == cookie


@pytest.mark.parametrize("headers", [
    {"origin": "null"}, {"origin": "https://other.test"},
    {"origin": "http://testserver"}, {"origin": "https://testserver:444"},
    {"origin": "https://testserver.evil.test"}, {"origin": "https://user@testserver"},
    {"origin": "https://testserver/path"}, {"origin": "https://testserver#fragment"},
    {"origin": "https://testserver", "sec-fetch-site": "cross-site"},
    {"sec-fetch-site": "same-site"}, {"sec-fetch-site": "cross-site"},
    {"origin": "https://other.test", "forwarded": "proto=https;host=other.test",
        "x-forwarded-host": "other.test", "x-forwarded-proto": "https"},
])
def test_resume_rejects_cross_origin_metadata_without_exposing_current_csrf(tmp_path, headers):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with TestClient(world.app, base_url="https://testserver") as client:
        issued = _login(client)
        cookie = client.cookies.get(SESSION_COOKIE)
        before = _ciphertext(world)
        denied = client.get(PATH, headers=headers)
        assert denied.status_code == 403
        assert issued["csrf_token"] not in denied.text and "principal_id" not in denied.json()
        assert denied.headers.get_list("set-cookie") == []
        assert client.cookies.get(SESSION_COOKIE) == cookie
        assert _ciphertext(world) == before
        assert _status(client, world, issued["csrf_token"]).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"sec-fetch-site": "none"},
    {"origin": "https://TESTSERVER:443", "sec-fetch-site": "same-origin"}])
def test_resume_normalizes_real_request_origin_and_allows_metadata_free_clients(tmp_path, headers):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with TestClient(world.app, base_url="https://testserver") as client:
        issued = _login(client)
        resumed = client.get(PATH, headers=headers)
        assert resumed.status_code == 200
        assert resumed.json() == issued


def test_resume_reauthenticates_generation_and_refuses_replaced_or_revoked_cookie(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with TestClient(world.app, base_url="https://testserver") as client:
        assert client.get(PATH).status_code == 401
        issued = _login(client)
        first_cookie = client.cookies.get(SESSION_COOKIE)
        first_bound = world.sessions.authenticate_token(first_cookie)
        with pytest.raises(BrowserSessionError):
            world.sessions.resume(first_cookie, bound=replace(first_bound, generation=first_bound.generation + 1))
        rotated = client.post("/api/complaint-workspace/auth/rotate", headers={"x-csrf-token": issued["csrf_token"]})
        assert rotated.status_code == 200
        current = rotated.json()
        assert current["generation"] == issued["generation"] + 1
        assert current["csrf_token"] != issued["csrf_token"]
        new_cookie = client.cookies.get(SESSION_COOKIE)
        assert new_cookie != first_cookie
        assert client.get(PATH).json() == current
        assert _status(client, world, issued["csrf_token"]).status_code == 403
        assert _status(client, world, current["csrf_token"]).status_code == 200
        with pytest.raises(BrowserSessionError):
            world.sessions.resume(new_cookie, bound=first_bound)
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, first_cookie)
        stale = client.get(PATH)
        assert stale.status_code == 401 and current["csrf_token"] not in stale.text
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, new_cookie)
        logged_out = client.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": current["csrf_token"]})
        assert logged_out.status_code == 200
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, new_cookie)
        revoked = client.get(PATH)
        assert revoked.status_code == 401 and current["csrf_token"] not in revoked.text


def test_resume_does_not_extend_expiry(tmp_path):
    world = owner_lawyer_journey_world(tmp_path / "world")
    with TestClient(world.app, base_url="https://testserver") as client:
        issued = _login(client)
        world.now["t"] = issued["expires_at"] - 1
        assert client.get(PATH).json() == issued
        world.now["t"] = issued["expires_at"]
        expired = client.get(PATH)
        assert expired.status_code == 401 and issued["csrf_token"] not in expired.text


def test_real_browser_bridge_resumes_cookie_and_current_csrf(tmp_path, monkeypatch):
    from tests import gui_native_browser as browser
    from tests.test_cimp_ux_06 import _open, _close
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        assert page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded").status == 200
        result = page.evaluate("""async () => {
          const login = await fetch('/api/complaint-workspace/auth/login', {method: 'POST',
            headers: {'content-type':'application/json'}, credentials: 'same-origin',
            body: JSON.stringify({credential:'synthetic-owner-credential'})});
          const issued = await login.json();
          const resumed = await fetch('/api/complaint-workspace/auth/session', {credentials:'same-origin'});
          const body = await resumed.json();
          return {login:login.status, resumed:resumed.status, equal:Object.keys(issued).length===Object.keys(body).length && Object.entries(issued).every(([k,v]) => JSON.stringify(v)===JSON.stringify(body[k])),
            cache:resumed.headers.get('cache-control'), setCookie:resumed.headers.get('set-cookie')};
        }""")
        assert result == {"login": 200, "resumed": 200, "equal": True,
            "cache": "private, no-store", "setCookie": None}
        assert page.evaluate("() => document.cookie.includes('cg_session')") is False
    finally:
        _close(playwright, context, node, profile, observed)
