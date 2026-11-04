"""Unified loading, empty, locked, conflict, and recovery states.

The workspace and conversation pages share one state surface. A failed call
keeps the composer text, offers a bounded retry or cancel, and never paints a
ready, supported, or verified outcome. Ordinary copy omits stacks, request
ids, and private content.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
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

OWNER_CREDENTIAL = "synthetic-owner-credential-ux44"
STRANGER_CREDENTIAL = "synthetic-stranger-credential-ux44"
PRIVATE = "synthetic-private-narrative-orchid-ux44"
STACK = 'Traceback (most recent call last):\n  File "/tmp/secret_case_ux44.py", line 3, in hidden\nNameError: private'
REQUEST_ID = "req-ux44-9f3c1a0b7e24"
INTENT = "synthetic-unsent-intent-ux44"
STATIC_ROOT = Path(__file__).resolve().parents[1] / "static"
ROOT = Path(__file__).resolve().parents[1]


def _world(tmp_path):
    now = {"t": 1_700_000_440}
    counts = {"assignments": 0}

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
            STRANGER_CREDENTIAL: stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=600,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    app = FastAPI()

    @app.get("/api/cases/key-access")
    async def locked_private_session():
        return JSONResponse(status_code=503, content={
            "status": "unavailable",
            "error": "key_unavailable",
            "session_readable": False,
            "stack": STACK,
            "request_id": REQUEST_ID,
            "narrative": PRIVATE,
        })

    @app.get("/api/cases/capability")
    async def missing_capability():
        return JSONResponse(status_code=503, content={
            "error": "message_unavailable",
            "stack": STACK,
            "request_id": REQUEST_ID,
            "narrative": PRIVATE,
        })

    @app.middleware("http")
    async def count_assignment_posts(request, call_next):
        if request.method == "POST" and request.url.path == "/api/cases/assignments":
            counts["assignments"] += 1
        return await call_next(request)

    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_assignments=assignments, case_messages=CaseMessageService(messages),
        case_handlers=CaseHandlerRegistry(),
        include_workspace=False, include_review=False, include_document=False,
    )

    @app.get("/workspace")
    async def workspace_page():
        html = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
        from fastapi.responses import HTMLResponse
        return HTMLResponse(html, headers={"cache-control": "no-store"})

    app.mount("/static", StaticFiles(directory=str(STATIC_ROOT)), name="ux44-static")
    return SimpleNamespace(app=app, owner=owner, lawyer=lawyer, stranger=stranger, counts=counts, cases=cases)


def _surface(page):
    page.wait_for_selector("#complaint-state-surface")
    return page.evaluate(
        """() => {
            const node = document.getElementById('complaint-state-surface');
            const text = node.innerText;
            return {
                kind: node.dataset.kind,
                outcome: node.dataset.outcome,
                retry: node.dataset.retryPermitted,
                cancel: node.dataset.cancelPermitted,
                count: node.dataset.retryCount,
                intent: node.dataset.intentPreserved,
                ready: node.dataset.ready,
                supported: node.dataset.supported,
                verified: node.dataset.verified,
                text,
            };
        }"""
    )


def test_templates_share_the_state_surface():
    workspace = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    messages = (ROOT / "templates" / "case_messages.html").read_text(encoding="utf-8")
    assert 'id="complaint-state-surface"' in workspace
    assert 'id="complaint-state-surface"' in messages
    assert "/static/complaint_case_shell.css" in workspace
    assert "/static/complaint_case_shell.css" in messages
    assert "/static/complaint_case_shell.js" in messages
    style = (STATIC_ROOT / "complaint_case_shell.css").read_text(encoding="utf-8")
    assert ".case-state" in style
    assert "prefers-reduced-motion" in style


def test_signed_out_catalog_is_access_not_ready(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        page = client.get(MESSAGE_INBOX_PATH)
        assert page.status_code == 200
        assert 'id="complaint-state-surface"' in page.text
        denied = client.get("/api/cases/messages/threads", params={"case_id": "missing-case"})
        assert denied.status_code == 401
        assert PRIVATE not in denied.text
        assert "Traceback" not in denied.text
        workspace = client.get("/workspace")
        assert workspace.status_code == 200
        assert 'id="complaint-state-surface"' in workspace.text
        assert 'data-ready="false"' in workspace.text


def test_browser_states_preserve_intent_and_bound_retry(tmp_path, monkeypatch):
    world = _world(tmp_path)
    denial = browser.probe_inherited_network_denial()
    assert denial["af_unix_only"], "the trusted executor must fence this child"
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux44-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    try:
        opened = page.goto(browser.SAME_ORIGIN + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
        assert opened.status == 200
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        assert page.evaluate("() => typeof window.complaintCaseShell.invalidate") == "function"
        login = page.evaluate(
            """async credential => {
                const response = await fetch('/api/complaint-workspace/auth/login', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'content-type': 'application/json'},
                    body: JSON.stringify({credential}),
                });
                return response.json();
            }""",
            OWNER_CREDENTIAL,
        )
        assert login["authenticated"] is True
        token = login["csrf_token"]
        created = page.evaluate(
            """async token => {
                const response = await fetch('/api/cases', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'content-type': 'application/json', 'x-csrf-token': token},
                    body: JSON.stringify({label: 'ux44-case'}),
                });
                return {status: response.status, body: await response.json()};
            }""",
            token,
        )
        assert created["status"] == 201, created
        case_id = created["body"]["case_id"]
        page.fill("#message-text", INTENT)
        page.evaluate(
            """async payload => {
                const response = await fetch('/api/cases/messages/threads?case_id=' + encodeURIComponent(payload.caseId), {
                    credentials: 'same-origin',
                    headers: {'x-csrf-token': payload.token},
                });
                return response.status;
            }""",
            {"caseId": case_id, "token": token},
        )
        page.wait_for_function("() => document.getElementById('complaint-state-surface').dataset.kind === 'empty'")
        empty = _surface(page)
        assert empty["outcome"] == "empty"
        assert empty["ready"] != "true"
        assert "verified" not in empty["text"].lower()
        assert page.input_value("#message-text") == INTENT

        conflict = page.evaluate(
            """async payload => {
                const response = await fetch('/api/cases/assignments', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'content-type': 'application/json', 'x-csrf-token': payload.token},
                    body: JSON.stringify({
                        case_id: payload.caseId,
                        member_principal_id: payload.member,
                        scope: ['case.read'],
                        expires_at: payload.expires,
                        expected_case_revision: 99999,
                        idempotency_key: 'ux44-conflict',
                    }),
                });
                const body = await response.json();
                return {status: response.status, body};
            }""",
            {
                "token": token,
                "caseId": case_id,
                "member": world.lawyer.principal_id,
                "expires": 1_700_000_900,
            },
        )
        assert conflict["status"] == 409, conflict
        assert conflict["body"]["error"] == "revision_conflict"
        page.wait_for_function("() => document.getElementById('complaint-state-surface').dataset.kind === 'conflict'")
        failed = _surface(page)
        assert failed["outcome"] == "failed"
        assert failed["retry"] == "true"
        assert failed["intent"] == "true"
        assert failed["ready"] == "false"
        assert failed["supported"] == "false"
        assert failed["verified"] == "false"
        assert INTENT not in failed["text"]
        assert PRIVATE not in failed["text"]
        assert "Traceback" not in failed["text"]
        assert REQUEST_ID not in failed["text"]
        assert case_id not in failed["text"]
        assert page.input_value("#message-text") == INTENT
        page.evaluate("() => { document.getElementById('composer-state').textContent = 'Ready'; }")
        page.wait_for_function("() => document.getElementById('composer-state').textContent === 'The action did not finish.'")
        assert page.evaluate("() => document.getElementById('send-message').dataset.state") == "failed"

        page.click("#complaint-state-retry")
        page.wait_for_function("() => document.getElementById('complaint-state-surface').dataset.retryCount === '2'")
        page.click("#complaint-state-retry")
        page.wait_for_function("() => document.getElementById('complaint-state-surface').dataset.kind === 'conflict' && document.getElementById('complaint-state-surface').dataset.retryPermitted === 'false'")
        limited = _surface(page)
        assert limited["count"] == "3"
        assert "Retry limit reached" in limited["text"]
        assert page.input_value("#message-text") == INTENT
        assert world.counts["assignments"] == 3

        key = page.evaluate(
            """async () => {
                const response = await fetch('/api/cases/key-access', {credentials: 'same-origin'});
                return {status: response.status, body: await response.json()};
            }"""
        )
        assert key["status"] == 503
        assert key["body"]["narrative"] == PRIVATE
        page.wait_for_function("() => document.getElementById('complaint-state-surface').dataset.kind === 'key'")
        locked = _surface(page)
        assert locked["retry"] == "false"
        assert locked["outcome"] == "failed"
        assert PRIVATE not in locked["text"]
        assert "Traceback" not in locked["text"]
        assert REQUEST_ID not in locked["text"]
        assert page.locator("#complaint-state-check-key").is_visible()
        readiness = page.evaluate(
            """() => {
                const node = document.getElementById('complaint-readiness');
                return node ? {
                    legal: node.dataset.legalSufficiency,
                    court: node.dataset.courtReady,
                    filing: node.dataset.filingSucceeded,
                } : null;
            }"""
        )
        assert readiness is None or readiness == {"legal": "false", "court": "false", "filing": "false"}

        missing = page.evaluate(
            """async () => {
                const response = await fetch('/api/cases/capability', {credentials: 'same-origin'});
                return response.status;
            }"""
        )
        assert missing == 503
        page.wait_for_function("() => document.getElementById('complaint-state-surface').dataset.kind === 'unavailable'")
        unavailable = _surface(page)
        assert unavailable["outcome"] == "failed"
        assert unavailable["retry"] == "true"
        assert "supported" not in unavailable["text"].lower()
        assert PRIVATE not in unavailable["text"]
        assert "Traceback" not in unavailable["text"]

        stranger = page.evaluate(
            """async (payload) => {
                const loggedOut = await fetch('/api/complaint-workspace/auth/logout', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'x-csrf-token': payload.ownerToken},
                });
                const login = await fetch('/api/complaint-workspace/auth/login', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'content-type': 'application/json'},
                    body: JSON.stringify({credential: payload.credential}),
                });
                const body = await login.json();
                const response = await fetch('/api/cases/messages/threads?case_id=' + encodeURIComponent(payload.caseId), {
                    credentials: 'same-origin',
                    headers: {'x-csrf-token': body.csrf_token},
                });
                return {logout: loggedOut.status, login: login.status, status: response.status, authenticated: body.authenticated};
            }""",
            {"ownerToken": token, "credential": STRANGER_CREDENTIAL, "caseId": case_id},
        )
        assert stranger["login"] == 200 and stranger["authenticated"] is True, stranger
        assert stranger["status"] in {403, 404}, stranger
        page.wait_for_function("() => document.getElementById('complaint-state-surface').dataset.kind === 'access'")
        access = _surface(page)
        assert access["retry"] == "false"
        assert access["ready"] == "false"
        assert "verified" not in access["text"].lower()

        page.evaluate(
            """() => {
                window.complaintCaseShell.invalidate();
                document.getElementById('complaint-state-cancel').click();
            }"""
        )
        cancelled = _surface(page)
        assert cancelled["kind"] == "cancelled"
        assert cancelled["outcome"] == "cancelled"
        assert cancelled["ready"] == "false"
        assert page.input_value("#message-text") == INTENT

        workspace = page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        assert workspace.status == 200
        page.wait_for_selector("#complaint-state-surface")
        assert page.locator("#complaint-case-shell").count() == 1
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
    finally:
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
        assert cleanup["remaining_pids"] == []
