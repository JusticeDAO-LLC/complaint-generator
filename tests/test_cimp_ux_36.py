"""Case conversation composer over qualified HTTP polling.

Chromium composes and reads private case messages, keeps human and AI
attribution on the server record type, and retries one failed send with the
same idempotency key. WebSocket and server-sent events are not used.
Membership revocation clears rendered plaintext.
"""

from __future__ import annotations

from contextlib import contextmanager
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
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
from applications.case_routes import MESSAGE_INBOX_PATH, CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore
from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
STRANGER_CREDENTIAL = "synthetic-refresh-token"
HOSTILE = '<img src=x onerror="window.__xss=1"><script>window.__xss=1</script>'
AI_TEXT = "synthetic mediator question"
COMPOSED = "synthetic-composed-reply"
STATIC_ROOT = Path(__file__).resolve().parents[1] / "static"


class _Workspace:
    def __init__(self) -> None:
        self.turns: list[dict] = []

    def authorized_correspondence_activity(self, *, actor_principal_id, case_id, tenant_id, resource_id):
        del actor_principal_id, tenant_id, resource_id
        return {
            "mediator_turns": [dict(item) for item in self.turns if item.get("case_id") == case_id],
            "review_decisions": [],
        }


def _world(tmp_path):
    now = {"t": 1_700_000_360}

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
    handlers = CaseHandlerRegistry()
    app = FastAPI()
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_assignments=assignments, case_messages=CaseMessageService(messages),
        case_handlers=handlers,
        include_workspace=False, include_review=False, include_document=False,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_ROOT)), name="correspondence-static")
    return SimpleNamespace(
        app=app, owner=owner, lawyer=lawyer, stranger=stranger, now=now, cases=cases,
        messages=messages, handlers=handlers, workspace=_Workspace(),
    )


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _seed(world, owner_client, lawyer_client):
    owner_token = _login(owner_client, OWNER_CREDENTIAL)
    lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
    created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "conversation"})
    assert created.status_code == 201, created.text
    case = created.json()
    invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
        "case_id": case["case_id"],
        "member_principal_id": world.lawyer.principal_id,
        "scope": ["case.read", "case.message.send"],
        "expires_at": world.now["t"] + 500,
        "expected_case_revision": case["directory_revision"],
        "idempotency_key": "composer-invite",
    })
    assert invited.status_code == 201, invited.text
    grant_id = invited.json()["grant_id"]
    accepted = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
        "scope": ["case.read", "case.message.send"],
        "expected_version": 1,
        "idempotency_key": "composer-accept",
    })
    assert accepted.status_code == 200, accepted.text
    namespace = world.cases.select_case(actor_principal_id=world.owner.principal_id, case_id=case["case_id"])
    world.handlers.bind(namespace, mediator=object(), workspace_service=world.workspace)
    world.workspace.turns.append({
        "record_type": "ai_mediator_turn",
        "source_id": "turn-composer",
        "case_id": case["case_id"],
        "canonical_owner_principal_id": namespace.tenant_id,
        "actor_principal_id": "mediator-model",
        "invocation_id": "invoke-composer",
        "target_kind": "intake_question",
        "target_id": "question-composer",
        "revision": 2,
        "occurred_at": 100,
        "text": AI_TEXT,
        "adopts_evidence": False,
        "adopts_answer": False,
    })
    thread = owner_client.post("/api/cases/messages/threads", headers=_csrf(owner_token), json={
        "case_id": case["case_id"], "idempotency_key": "composer-thread",
    })
    assert thread.status_code == 201, thread.text
    thread_id = thread.json()["thread_id"]
    hostile = owner_client.post(f"/api/cases/messages/threads/{thread_id}/messages", headers=_csrf(owner_token), json={
        "case_id": case["case_id"], "text": HOSTILE, "idempotency_key": "composer-hostile",
    })
    assert hostile.status_code == 201, hostile.text
    return SimpleNamespace(
        case=case, thread_id=thread_id, grant_id=grant_id, version=accepted.json()["version"],
        owner_token=owner_token, lawyer_token=lawyer_token,
    )


def test_composer_shell_rejects_unauthenticated_and_non_member_reads(tmp_path):
    world = _world(tmp_path)
    script = (STATIC_ROOT / "complaint_correspondence.js").read_text(encoding="utf-8")
    style = (STATIC_ROOT / "complaint_correspondence.css").read_text(encoding="utf-8")
    assert "new WebSocket" not in script and "EventSource" not in script
    assert "fetch(" in script and "textContent" in script and "idempotency_key" in script
    assert ":focus-visible" in style and 'data-attribution="ai"' in style
    with TestClient(world.app, base_url="https://testserver") as client:
        page = client.get(MESSAGE_INBOX_PATH)
        assert page.status_code == 200
        assert page.headers["cache-control"] == "no-store"
        assert 'data-message-transport="http-polling"' in page.text
        assert 'data-websocket="unsupported"' in page.text
        assert 'data-sse="unsupported"' in page.text
        assert "WebSocket and server-sent events are not used" in page.text
        assert "/static/complaint_correspondence.js" in page.text
        assert "/static/complaint_correspondence.css" in page.text
        asset = client.get("/static/complaint_correspondence.js")
        assert asset.status_code == 200
        assert "javascript" in asset.headers["content-type"]
        assert asset.content.decode("utf-8") == script
        css = client.get("/static/complaint_correspondence.css")
        assert css.status_code == 200
        assert css.content.decode("utf-8") == style
        denied = client.get("/api/cases/correspondence", params={"case_id": "missing"})
        assert denied.status_code == 401
        assert HOSTILE not in denied.text and AI_TEXT not in denied.text
        stranger = _login(client, STRANGER_CREDENTIAL)
        blocked = client.get("/api/cases/messages/threads", params={"case_id": "missing"}, headers={"x-csrf-token": stranger})
        assert blocked.status_code in {403, 404}
        assert HOSTILE not in blocked.text


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


class _FirstMessagePostUnavailable:
    """Hold the first composer POST, answer 503, then forward the retry."""

    def __init__(self, app):
        self.app = app
        self.bodies: list[bytes] = []

    async def __call__(self, scope, receive, send):
        path = scope.get("path") or ""
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or "/messages/threads/" not in path
            or not path.endswith("/messages")
        ):
            await self.app(scope, receive, send)
            return
        chunks = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            chunks.append(message.get("body") or b"")
            if not message.get("more_body"):
                break
        body = b"".join(chunks)
        self.bodies.append(body)
        if len(self.bodies) == 1:
            await asyncio.sleep(1.2)
            payload = b'{"error":"temporary_unavailable"}'
            await send({
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                ],
            })
            await send({"type": "http.response.body", "body": payload})
            return
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay, send)


def _sign_in(page, credential):
    page.goto(browser.SAME_ORIGIN + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
    assert page.get_attribute("body", "data-message-transport") == "http-polling"
    assert page.get_attribute("body", "data-websocket") == "unsupported"
    assert page.get_attribute("body", "data-sse") == "unsupported"
    page.locator("#inbox-credential").fill(credential)
    page.locator("#inbox-login button").click()
    page.wait_for_function("() => document.getElementById('inbox-auth-status').textContent === 'Signed in'")


def _open_owner(page, case_id):
    page.locator("#case-select").select_option(case_id)
    assert page.locator("#case-id").input_value() == case_id
    page.locator("#poll-ms").fill("500")
    page.locator("#load-threads").click()
    page.locator("#thread-list button").click()
    page.locator("#inbox-status").wait_for()
    page.wait_for_function("() => document.getElementById('inbox-status').textContent === 'Opened thread'")


def test_composer_attributes_retries_and_clears_on_revocation(tmp_path, monkeypatch):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(
        world.app, base_url="https://testserver"
    ) as lawyer_client:
        seed = _seed(world, owner_client, lawyer_client)
    gate = _FirstMessagePostUnavailable(world.app)
    with _browser(tmp_path, monkeypatch, gate) as session:
        owner = session.pages["owner"]
        lawyer = session.pages["lawyer"]
        stranger = session.pages["stranger"]
        _sign_in(owner, OWNER_CREDENTIAL)
        _open_owner(owner, seed.case["case_id"])
        ai = owner.locator("[data-record-type='ai_mediator_turn']")
        assert ai.get_attribute("data-attribution") == "ai"
        assert ai.locator(".message-text").inner_text() == AI_TEXT
        assert "Not a human message" in ai.inner_text()
        assert "invoke-composer" in ai.inner_text()
        assert owner.locator("[data-record-type='ai_mediator_turn'][data-attribution='human']").count() == 0
        hostile = owner.locator("[data-record-type='human_message']")
        assert hostile.get_attribute("data-attribution") == "human"
        assert hostile.locator(".message-text").inner_text() == HOSTILE
        assert "<script" not in hostile.locator(".message-text").inner_html()
        assert "Not evidence" in hostile.inner_text()
        assert owner.evaluate("() => window.__xss") is None
        owner.locator("#message-text").fill(COMPOSED)
        owner.locator("#message-text").press("Control+Enter")
        owner.wait_for_selector("#send-message[data-state='pending']")
        assert owner.locator("#send-button").is_disabled()
        owner.wait_for_function(
            """(text) => {
                const nodes = Array.from(document.querySelectorAll("[data-record-type='human_message'] .message-text"));
                return nodes.filter((node) => node.textContent === text).length === 1;
            }""",
            arg=COMPOSED,
        )
        owner.wait_for_function("() => document.activeElement && document.activeElement.id === 'message-text'")
        assert len(gate.bodies) == 2
        parsed = [json.loads(item) for item in gate.bodies]
        assert parsed[0]["idempotency_key"] == parsed[1]["idempotency_key"]
        assert parsed[0]["text"] == COMPOSED
        assert parsed[0]["case_id"] == seed.case["case_id"]
        with TestClient(world.app, base_url="https://testserver") as owner_client:
            owner_token = _login(owner_client, OWNER_CREDENTIAL)
            page = owner_client.get(
                f"/api/cases/messages/threads/{seed.thread_id}/messages",
                params={"case_id": seed.case["case_id"], "limit": 20},
                headers={"x-csrf-token": owner_token},
            )
            assert page.status_code == 200, page.text
            texts = [item["text"] for item in page.json()["messages"]]
            assert texts.count(COMPOSED) == 1
            assert texts.count(HOSTILE) == 1
            replay = owner_client.post(
                f"/api/cases/messages/threads/{seed.thread_id}/messages",
                headers=_csrf(owner_token),
                json={
                    "case_id": seed.case["case_id"],
                    "text": COMPOSED,
                    "idempotency_key": parsed[0]["idempotency_key"],
                },
            )
            assert replay.status_code == 201, replay.text
            assert replay.json()["message_id"] == page.json()["messages"][-1]["message_id"]
        _sign_in(lawyer, LAWYER_CREDENTIAL)
        lawyer.locator("#case-id").fill(seed.case["case_id"])
        lawyer.locator("#membership-grant-id").fill(seed.grant_id)
        lawyer.locator("#membership-version").fill(str(seed.version))
        lawyer.locator("#poll-ms").fill("500")
        lawyer.locator("#load-threads").click()
        lawyer.locator("#thread-list button").click()
        lawyer.wait_for_function(
            """(text) => document.body.innerText.includes(text)""",
            arg=COMPOSED,
        )
        assert lawyer.locator("[data-record-type='ai_mediator_turn']").get_attribute("data-attribution") == "ai"
        human_text = "\n".join(lawyer.locator("[data-attribution='human']").all_inner_texts())
        assert COMPOSED in human_text
        assert HOSTILE in human_text
        _sign_in(stranger, STRANGER_CREDENTIAL)
        stranger.locator("#case-id").fill(seed.case["case_id"])
        stranger.locator("#load-threads").click()
        stranger.locator("#inbox-error").wait_for()
        assert stranger.locator("#inbox-error").inner_text() != ""
        assert COMPOSED not in stranger.locator("body").inner_text()
        assert HOSTILE not in stranger.locator("body").inner_text()
        assert AI_TEXT not in stranger.locator("body").inner_text()
        with TestClient(world.app, base_url="https://testserver") as owner_client:
            owner_token = _login(owner_client, OWNER_CREDENTIAL)
            revoked = owner_client.post(
                f"/api/cases/assignments/{seed.grant_id}/change",
                headers=_csrf(owner_token),
                json={
                    "confirm_grant_change": True,
                    "revoke": True,
                    "expected_version": seed.version,
                    "idempotency_key": "composer-revoke",
                },
            )
            assert revoked.status_code == 200, revoked.text
            assert revoked.json()["revoked"] is True
        lawyer.wait_for_function(
            """(text) => !document.body.innerText.includes(text)
                && document.getElementById('inbox-error').textContent === 'membership_removed'""",
            arg=COMPOSED,
            timeout=10000,
        )
        assert HOSTILE not in lawyer.locator("body").inner_text()
        assert AI_TEXT not in lawyer.locator("body").inner_text()
        assert session.bridge.aborted_unqualified["websocket"] == []
        assert session.bridge.aborted_unqualified["sse"] == []
        assert "/static/complaint_correspondence.js" in session.bridge.same_origin_paths
        assert "/static/complaint_correspondence.css" in session.bridge.same_origin_paths
