"""User and lawyer conversation inbox over qualified HTTP polling.

Chromium exercises send, read, pagination, reload, and unread state against
the composed ASGI app. Message text is rendered as text. WebSocket and SSE
are not used.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    SESSION_COOKIE,
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_api import CaseCatalog
from applications.case_assignment_api import CaseAssignmentService
from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.case_message_api import CaseMessageService
from applications.case_messages import CaseMessageStore
from applications.case_routes import MESSAGE_INBOX_PATH, MESSAGE_INBOX_SCRIPT_PATH, compose_case_routes
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore
from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
STRANGER_CREDENTIAL = "synthetic-refresh-token"
HOSTILE = '<img src=x onerror="window.__xss=1"><script>window.__xss=1</script>'
PAGE_ONE = ("synthetic-inbox-alpha", "synthetic-inbox-beta")
LAWYER_TEXT = "synthetic-lawyer-reply"


def _world(tmp_path):
    now = {"t": 1_700_000_000}

    def clock():
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    stranger = principals.register_from_request({})
    memberships = CaseMembershipStore(
        tmp_path / "memberships", key=os.urandom(32), key_id="membership-key",
        principals=principals, cases=cases, clock=clock,
    )
    key_grants = CaseResourceKeyGrantStore(
        tmp_path / "key-grants", key=os.urandom(32), key_id="resource-grant-key",
        principals=principals, cases=cases, memberships=memberships,
    )
    messages = CaseMessageStore(
        tmp_path / "messages", key=os.urandom(32), key_id="message-key",
        principals=principals, cases=cases, memberships=memberships, clock=clock,
    )
    assignments = CaseAssignmentService(
        principals=principals, cases=cases, memberships=memberships, key_grants=key_grants,
        sessions={}, clock=clock,
    )
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            STRANGER_CREDENTIAL: stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=600,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    app = FastAPI()
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_assignments=assignments, case_messages=CaseMessageService(messages),
        include_workspace=False, include_review=False, include_document=False,
    )
    return SimpleNamespace(app=app, owner=owner, lawyer=lawyer, stranger=stranger, now=now)


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _seed(world):
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(world.app, base_url="https://testserver") as lawyer_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "inbox"})
        assert created.status_code == 201, created.text
        case = created.json()
        invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read", "case.message.send"],
            "expires_at": world.now["t"] + 500,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "inbox-invite",
        })
        assert invited.status_code == 201, invited.text
        grant_id = invited.json()["grant_id"]
        accepted = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
            "scope": ["case.read", "case.message.send"],
            "expected_version": 1,
            "idempotency_key": "inbox-accept",
        })
        assert accepted.status_code == 200, accepted.text
        thread = owner_client.post("/api/cases/messages/threads", headers=_csrf(owner_token), json={
            "case_id": case["case_id"], "idempotency_key": "inbox-thread",
        })
        assert thread.status_code == 201, thread.text
        thread_id = thread.json()["thread_id"]
        for index, text in enumerate(PAGE_ONE + (HOSTILE,)):
            sent = owner_client.post(f"/api/cases/messages/threads/{thread_id}/messages", headers=_csrf(owner_token), json={
                "case_id": case["case_id"], "text": text, "idempotency_key": f"seed-{index}",
            })
            assert sent.status_code == 201, sent.text
        return SimpleNamespace(case=case, thread_id=thread_id, grant_id=grant_id, version=accepted.json()["version"])


def test_inbox_shell_is_http_polling_and_api_stays_authenticated(tmp_path):
    world = _world(tmp_path)
    script = Path("static/complaint_case_messages.js").read_text(encoding="utf-8")
    assert "new WebSocket" not in script and "EventSource" not in script
    assert "fetch(" in script and "textContent" in script
    with TestClient(world.app, base_url="https://testserver") as client:
        page = client.get(MESSAGE_INBOX_PATH)
        assert page.status_code == 200
        assert "http-polling" in page.text
        assert MESSAGE_INBOX_SCRIPT_PATH in page.text
        assert "WebSocket" in page.text and "not used" in page.text
        asset = client.get(MESSAGE_INBOX_SCRIPT_PATH)
        assert asset.status_code == 200
        assert "javascript" in asset.headers["content-type"]
        assert asset.content.decode("utf-8") == script
        denied = client.get("/api/cases/messages/threads", params={"case_id": "missing"})
        assert denied.status_code == 401
        assert "synthetic-inbox-alpha" not in denied.text


@contextmanager
def _browser(tmp_path, monkeypatch, app):
    denial = browser.probe_inherited_network_denial()
    assert denial["af_unix_only"], "the trusted executor must fence this child"
    bridge = browser.SameOriginAsgiBridge(app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile_root = tmp_path / "browser-profiles"
    profile_root.mkdir(mode=0o700)
    playwright = None
    contexts = []
    observed = set()
    try:
        playwright = browser._load_sync_playwright()().start()
        pages = {}
        for name in ("owner", "lawyer", "stranger"):
            profile = profile_root / name
            profile.mkdir(mode=0o700)
            context = browser._launch_context(playwright, chromium.path, profile, bridge)
            contexts.append(context)
            browser._assert_process_custody(node, chromium, profile)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(15000)
            pages[name] = page
        observed |= browser._with_descendants(browser._matching_pids((str(profile_root), node.argv[1])))
        yield SimpleNamespace(pages=pages, bridge=bridge)
    finally:
        for context in contexts:
            context.close()
        if playwright is not None:
            playwright.stop()
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"


def _sign_in(page, credential):
    page.goto(browser.SAME_ORIGIN + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
    assert page.get_attribute("body", "data-message-transport") == "http-polling"
    assert page.get_attribute("body", "data-websocket") == "unsupported"
    page.fill("#inbox-credential", credential)
    page.click("#inbox-login button[type=submit]")
    page.wait_for_function("document.getElementById('inbox-auth-status').textContent === 'Signed in'")


def _open(page, seed, *, grant=False, limit="2", poll="300"):
    page.fill("#case-id", seed.case["case_id"])
    page.fill("#thread-id", seed.thread_id)
    page.fill("#page-limit", limit)
    page.fill("#poll-ms", poll)
    if grant:
        page.fill("#membership-grant-id", seed.grant_id)
        page.fill("#membership-version", str(seed.version))
    else:
        page.fill("#membership-grant-id", "")
        page.fill("#membership-version", "")
    page.click("#open-thread")


def _message_texts(page):
    return page.locator("#message-list .message-text").all_text_contents()


def test_user_and_lawyer_browser_inbox_send_read_page_reload_and_unread(tmp_path, monkeypatch):
    world = _world(tmp_path)
    seed = _seed(world)
    with _browser(tmp_path, monkeypatch, world.app) as session:
        owner = session.pages["owner"]
        lawyer = session.pages["lawyer"]
        stranger = session.pages["stranger"]
        _sign_in(owner, OWNER_CREDENTIAL)
        owner.select_option("#case-select", seed.case["case_id"])
        assert owner.input_value("#case-id") == seed.case["case_id"]
        _open(owner, seed)
        owner.wait_for_function("document.querySelectorAll('#message-list .message-text').length === 2")
        assert _message_texts(owner) == list(PAGE_ONE)
        assert owner.locator("#message-list [data-unread='true']").count() == 2
        assert HOSTILE not in owner.locator("#message-list").inner_text()
        owner.click("#next-page")
        owner.wait_for_function("document.querySelectorAll('#message-list .message-text').length === 1")
        assert _message_texts(owner) == [HOSTILE]
        assert owner.locator("#message-list img, #message-list script").count() == 0
        assert owner.evaluate("window.__xss") is None
        assert "no_websocket_or_sse" in owner.locator("#inbox-limitations").inner_text()
        owner.click("#mark-read")
        owner.wait_for_function("document.getElementById('unread-count').textContent === 'Unread 0'")
        stored = owner.evaluate("JSON.stringify({...sessionStorage})")
        assert HOSTILE not in stored and "synthetic-inbox-alpha" not in stored
        assert owner.evaluate("JSON.stringify({...localStorage})") in {"{}", "null"}
        owner.reload(wait_until="domcontentloaded")
        assert owner.locator("#inbox-auth-status").inner_text() == "Sign in required"
        _sign_in(owner, OWNER_CREDENTIAL)
        _open(owner, seed)
        owner.click("#next-page")
        owner.wait_for_function("document.getElementById('unread-count').textContent === 'Unread 0'")
        assert _message_texts(owner) == [HOSTILE]

        _sign_in(lawyer, LAWYER_CREDENTIAL)
        _open(lawyer, seed, grant=True)
        lawyer.click("#next-page")
        lawyer.wait_for_function("document.querySelectorAll('#message-list .message-text').length === 1")
        assert lawyer.locator("#message-list img").count() == 0
        lawyer.fill("#message-text", LAWYER_TEXT)
        lawyer.click("#send-message button[type=submit]")
        lawyer.wait_for_function(
            "Array.from(document.querySelectorAll('#message-list .message-text')).some(node => node.textContent === 'synthetic-lawyer-reply')"
        )
        assert lawyer.locator("#message-list [data-unread='true']").count() >= 1

        owner.wait_for_function(
            "Array.from(document.querySelectorAll('#message-list .message-text')).some(node => node.textContent === 'synthetic-lawyer-reply')"
        )
        assert owner.locator("#message-list [data-unread='true']").count() == 1
        assert any(path.startswith("/api/cases/messages/threads/") and path.endswith("/messages") for path in session.bridge.same_origin_paths)
        assert session.bridge.aborted_unqualified["websocket"] == []
        assert session.bridge.aborted_unqualified["sse"] == []

        _sign_in(stranger, STRANGER_CREDENTIAL)
        _open(stranger, seed)
        stranger.wait_for_function("document.getElementById('inbox-error').textContent.length > 0")
        assert stranger.locator("#message-list .message-text").count() == 0
        assert "synthetic-inbox-alpha" not in stranger.locator("body").inner_text()
        assert LAWYER_TEXT not in stranger.locator("body").inner_text()
        assert HOSTILE not in stranger.locator("body").inner_text()
