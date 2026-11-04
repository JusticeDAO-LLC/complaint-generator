"""In-app correspondence attention: unread, review-needed, and update markers.

Badges and the operational log name the attention state and source id. They do
not copy complaint or message text. Acknowledgement is stored for the current
actor and case revision. Nothing is emailed or sent by SMS.
"""

from __future__ import annotations

from contextlib import contextmanager
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
from applications.case_routes import CASE_PAGE_PATH, MESSAGE_INBOX_PATH, CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore
from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
STRANGER_CREDENTIAL = "synthetic-refresh-token"
HUMAN_TEXT = "synthetic unread note for the inbox"
REVIEW_TEXT = "synthetic review note kept off the badge"
AI_TEXT = "synthetic mediator update kept off the badge"
STATIC_ROOT = Path(__file__).resolve().parents[1] / "static"
SECRETS = (HUMAN_TEXT, REVIEW_TEXT, AI_TEXT)


class _Workspace:
    def __init__(self) -> None:
        self.turns: list[dict] = []
        self.reviews: list[dict] = []

    def authorized_correspondence_activity(self, *, actor_principal_id, case_id, tenant_id, resource_id):
        del actor_principal_id, tenant_id, resource_id
        return {
            "mediator_turns": [dict(item) for item in self.turns if item.get("case_id") == case_id],
            "review_decisions": [dict(item) for item in self.reviews if item.get("case_id") == case_id],
        }


def _world(tmp_path):
    now = {"t": 1_700_000_380}

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
        handlers=handlers, workspace=_Workspace(),
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
    created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "attention-inbox"})
    assert created.status_code == 201, created.text
    case = created.json()
    invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
        "case_id": case["case_id"],
        "member_principal_id": world.lawyer.principal_id,
        "scope": ["case.read", "case.message.send"],
        "expires_at": world.now["t"] + 500,
        "expected_case_revision": case["directory_revision"],
        "idempotency_key": "attention-invite",
    })
    assert invited.status_code == 201, invited.text
    grant_id = invited.json()["grant_id"]
    accepted = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
        "scope": ["case.read", "case.message.send"],
        "expected_version": 1,
        "idempotency_key": "attention-accept",
    })
    assert accepted.status_code == 200, accepted.text
    namespace = world.cases.select_case(actor_principal_id=world.owner.principal_id, case_id=case["case_id"])
    world.handlers.bind(namespace, mediator=object(), workspace_service=world.workspace)
    world.workspace.turns.append({
        "record_type": "ai_mediator_turn",
        "source_id": "turn-attention-38",
        "case_id": case["case_id"],
        "canonical_owner_principal_id": namespace.tenant_id,
        "actor_principal_id": "mediator-model",
        "invocation_id": "invoke-attention-38",
        "target_kind": "draft_section",
        "target_id": "section-facts",
        "revision": 3,
        "occurred_at": 80,
        "text": AI_TEXT,
        "adopts_evidence": False,
        "adopts_answer": False,
    })
    world.workspace.reviews.append({
        "record_type": "review_decision",
        "source_id": "review-attention-38",
        "case_id": case["case_id"],
        "canonical_owner_principal_id": namespace.tenant_id,
        "actor_principal_id": world.lawyer.principal_id,
        "invocation_id": "invoke-review-38",
        "target_kind": "draft_section",
        "target_id": "section-facts",
        "revision": 4,
        "occurred_at": 90,
        "text": REVIEW_TEXT,
        "adopts_evidence": False,
        "adopts_answer": False,
    })
    thread = owner_client.post("/api/cases/messages/threads", headers=_csrf(owner_token), json={
        "case_id": case["case_id"], "idempotency_key": "attention-thread",
    })
    assert thread.status_code == 201, thread.text
    thread_id = thread.json()["thread_id"]
    sent = owner_client.post(f"/api/cases/messages/threads/{thread_id}/messages", headers=_csrf(owner_token), json={
        "case_id": case["case_id"], "text": HUMAN_TEXT, "idempotency_key": "attention-human",
    })
    assert sent.status_code == 201, sent.text
    return SimpleNamespace(
        case=case, thread_id=thread_id, message=sent.json(), grant_id=grant_id,
        version=accepted.json()["version"], owner_token=owner_token, lawyer_token=lawyer_token,
    )


def _project(client, case_id, **extra):
    params = {"case_id": case_id}
    params.update(extra)
    return client.get("/api/cases/correspondence", params=params)


def _entry(payload, record_type):
    matches = [item for item in payload["entries"] if item["record_type"] == record_type]
    assert len(matches) == 1, payload
    return matches[0]


def _flat_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _flat_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _flat_strings(item)


def _assert_no_complaint_content(payload):
    blob = "\n".join(_flat_strings(payload))
    for secret in SECRETS:
        assert secret not in blob
    assert "text" not in json.dumps(payload.get("items", []))
    for row in payload.get("operational_log") or []:
        assert "text" not in row
        assert row.get("external_delivery") is False
        assert row.get("email") is False
        assert row.get("sms") is False


def test_attention_is_scoped_and_badges_omit_complaint_content(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(
        world.app, base_url="https://testserver"
    ) as lawyer_client, TestClient(world.app, base_url="https://testserver") as stranger_client:
        seed = _seed(world, owner_client, lawyer_client)
        stranger_token = _login(stranger_client, STRANGER_CREDENTIAL)
        owner_view = _project(owner_client, seed.case["case_id"])
        assert owner_view.status_code == 200, owner_view.text
        owner_body = owner_view.json()
        human = _entry(owner_body, "human_message")
        assert human["attention"]["state"] == "none"
        assert human["text"] == HUMAN_TEXT
        assert _entry(owner_body, "ai_mediator_turn")["attention"]["state"] == "update"
        assert _entry(owner_body, "review_decision")["attention"]["state"] == "review_needed"
        assert owner_body["attention"]["unread_count"] == 0
        assert owner_body["attention"]["review_needed_count"] == 1
        assert owner_body["attention"]["update_count"] == 1
        assert owner_body["external_delivery"] is False

        lawyer_view = _project(
            lawyer_client, seed.case["case_id"],
            membership_grant_id=seed.grant_id, expected_membership_version=seed.version,
        )
        assert lawyer_view.status_code == 200, lawyer_view.text
        lawyer_human = _entry(lawyer_view.json(), "human_message")
        assert lawyer_human["attention"]["state"] == "unread"
        assert lawyer_human["attention"]["acknowledged"] is False
        assert lawyer_view.json()["attention"]["unread_count"] == 1

        denied = stranger_client.get("/api/cases/correspondence", params={"case_id": seed.case["case_id"]})
        assert denied.status_code in {403, 404}
        stranger_badge = stranger_client.get("/api/cases/correspondence/attention")
        assert stranger_badge.status_code == 200, stranger_badge.text
        assert stranger_badge.json()["badge"]["total_count"] == 0
        assert stranger_badge.json()["items"] == []
        assert stranger_badge.json()["operational_log"] == []
        _assert_no_complaint_content(stranger_badge.json())

        owner_badge = owner_client.get("/api/cases/correspondence/attention")
        assert owner_badge.status_code == 200, owner_badge.text
        assert owner_badge.json()["badge"]["unread_count"] == 0
        assert owner_badge.json()["badge"]["review_needed_count"] == 1
        assert owner_badge.json()["badge"]["update_count"] == 1
        assert owner_badge.json()["email"] is False
        assert owner_badge.json()["sms"] is False
        _assert_no_complaint_content(owner_badge.json())
        assert {item["source_id"] for item in owner_badge.json()["items"]} == {
            "turn-attention-38", "review-attention-38",
        }

        lawyer_badge = lawyer_client.get("/api/cases/correspondence/attention")
        assert lawyer_badge.json()["badge"]["unread_count"] == 1
        assert lawyer_badge.json()["badge"]["total_count"] == 3
        _assert_no_complaint_content(lawyer_badge.json())
        assert seed.message["message_id"] in {item["source_id"] for item in lawyer_badge.json()["items"]}

        own_ack = owner_client.post("/api/cases/correspondence/acknowledgements", headers=_csrf(seed.owner_token), json={
            "case_id": seed.case["case_id"],
            "source_id": seed.message["message_id"],
            "record_type": "human_message",
            "revision": lawyer_human["revision"],
        })
        assert own_ack.status_code == 403, own_ack.text
        assert own_ack.json()["error"] == "attention_not_required"

        leaked = lawyer_client.post("/api/cases/correspondence/acknowledgements", headers=_csrf(seed.lawyer_token), json={
            "case_id": seed.case["case_id"],
            "source_id": seed.message["message_id"],
            "record_type": "human_message",
            "revision": lawyer_human["revision"],
            "membership_grant_id": seed.grant_id,
            "expected_membership_version": seed.version,
            "text": HUMAN_TEXT,
        })
        assert leaked.status_code == 403
        assert leaked.json()["error"] == "complaint_text_rejected"

        stale = lawyer_client.post("/api/cases/correspondence/acknowledgements", headers=_csrf(seed.lawyer_token), json={
            "case_id": seed.case["case_id"],
            "source_id": seed.message["message_id"],
            "record_type": "human_message",
            "revision": int(lawyer_human["revision"]) + 9,
            "membership_grant_id": seed.grant_id,
            "expected_membership_version": seed.version,
        })
        assert stale.status_code == 409
        assert stale.json()["error"] == "revision_conflict"
        still = _project(
            lawyer_client, seed.case["case_id"],
            membership_grant_id=seed.grant_id, expected_membership_version=seed.version,
        )
        assert _entry(still.json(), "human_message")["attention"]["acknowledged"] is False

        stranger_ack = stranger_client.post("/api/cases/correspondence/acknowledgements", headers=_csrf(stranger_token), json={
            "case_id": seed.case["case_id"],
            "source_id": seed.message["message_id"],
            "record_type": "human_message",
            "revision": lawyer_human["revision"],
        })
        assert stranger_ack.status_code in {403, 404}

        acked = lawyer_client.post("/api/cases/correspondence/acknowledgements", headers=_csrf(seed.lawyer_token), json={
            "case_id": seed.case["case_id"],
            "source_id": seed.message["message_id"],
            "record_type": "human_message",
            "revision": lawyer_human["revision"],
            "membership_grant_id": seed.grant_id,
            "expected_membership_version": seed.version,
        })
        assert acked.status_code == 200, acked.text
        assert acked.json()["acknowledged"] is True
        assert acked.json()["replayed"] is False
        assert acked.json()["external_delivery"] is False
        assert acked.json()["email"] is False
        assert acked.json()["sms"] is False
        assert acked.json()["badge"]["unread_count"] == 0
        assert HUMAN_TEXT not in acked.text
        again = lawyer_client.post("/api/cases/correspondence/acknowledgements", headers=_csrf(seed.lawyer_token), json={
            "case_id": seed.case["case_id"],
            "source_id": seed.message["message_id"],
            "record_type": "human_message",
            "revision": lawyer_human["revision"],
            "membership_grant_id": seed.grant_id,
            "expected_membership_version": seed.version,
        })
        assert again.status_code == 200, again.text
        assert again.json()["replayed"] is True
        logged = lawyer_client.get("/api/cases/correspondence/attention")
        assert logged.json()["badge"]["unread_count"] == 0
        assert logged.json()["badge"]["review_needed_count"] == 1
        actions = [item["action"] for item in logged.json()["operational_log"]]
        assert actions == ["correspondence_acknowledged"]
        assert logged.json()["operational_log"][0]["source_id"] == seed.message["message_id"]
        _assert_no_complaint_content(logged.json())
        owner_after = owner_client.get("/api/cases/correspondence/attention")
        assert owner_after.json()["operational_log"] == []
        assert owner_after.json()["badge"]["unread_count"] == 0
        anonymous = TestClient(world.app, base_url="https://testserver")
        assert anonymous.get("/api/cases/correspondence/attention").status_code == 401


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
        for name in ("owner", "lawyer"):
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


def _sign_in_inbox(page, credential):
    page.goto(browser.SAME_ORIGIN + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
    page.locator("#inbox-credential").fill(credential)
    page.locator("#inbox-login button").click()
    page.wait_for_function("() => document.getElementById('inbox-auth-status').textContent === 'Signed in'")


def _open_case(page, seed, *, lawyer=False):
    page.locator("#poll-ms").fill("60000")
    if lawyer:
        page.locator("#case-id").fill(seed.case["case_id"])
        page.locator("#membership-grant-id").fill(seed.grant_id)
        page.locator("#membership-version").fill(str(seed.version))
    else:
        page.locator("#case-select").select_option(seed.case["case_id"])
    page.locator("#load-threads").click()
    page.locator("#thread-list button").click()
    page.wait_for_function("() => document.getElementById('inbox-status').textContent === 'Opened thread'")


def test_browser_acknowledges_attention_and_drops_stale_polls(tmp_path, monkeypatch):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(
        world.app, base_url="https://testserver"
    ) as lawyer_client:
        seed = _seed(world, owner_client, lawyer_client)
    with _browser(tmp_path, monkeypatch, world.app) as session:
        lawyer = session.pages["lawyer"]
        owner = session.pages["owner"]
        _sign_in_inbox(lawyer, LAWYER_CREDENTIAL)
        _open_case(lawyer, seed, lawyer=True)
        row = lawyer.locator("[data-record-type='human_message']")
        assert row.get_attribute("data-attention") == "unread"
        assert row.get_attribute("data-acknowledged") == "false"
        assert HUMAN_TEXT in row.locator(".message-text").inner_text()
        summary = lawyer.locator("#inbox-attention")
        assert summary.inner_text() == "Unread 1. Review needed 1. Updates 1. In-app only."
        assert HUMAN_TEXT not in summary.inner_text()
        assert REVIEW_TEXT not in summary.inner_text()
        assert AI_TEXT not in summary.inner_text()
        assert lawyer.locator("[data-record-type='review_decision']").get_attribute("data-attention") == "review_needed"
        assert lawyer.locator("[data-record-type='ai_mediator_turn']").get_attribute("data-attention") == "update"
        row.locator(".correspondence__acknowledge").click()
        lawyer.wait_for_function(
            """() => document.querySelector("[data-record-type='human_message']")
                && document.querySelector("[data-record-type='human_message']").getAttribute("data-acknowledged") === "true"
                && document.getElementById("inbox-attention").textContent.indexOf("Unread 0.") === 0"""
        )
        assert lawyer.locator("[data-record-type='human_message'] .correspondence__acknowledge").count() == 0

        _sign_in_inbox(owner, OWNER_CREDENTIAL)
        _open_case(owner, seed)
        assert owner.locator("[data-record-type='human_message']").get_attribute("data-attention") == "none"
        assert owner.locator("#inbox-attention").inner_text().startswith("Unread 0. Review needed 1. Updates 1.")
        owner.evaluate(
            """() => {
                const original = window.fetch.bind(window);
                window.__pendingCorrespondence = [];
                window.fetch = function (url, options) {
                    const target = String(url);
                    if (target.indexOf("/api/cases/correspondence") !== -1 && target.indexOf("acknowledgements") === -1 && target.indexOf("/attention") === -1) {
                        return new Promise((resolve, reject) => {
                            const release = () => { original(url, options).then(resolve, reject); };
                            const signal = options && options.signal;
                            if (signal && signal.aborted) { release(); return; }
                            window.__pendingCorrespondence.push(release);
                        });
                    }
                    return original(url, options);
                };
            }"""
        )
        owner.locator("#refresh-messages").click()
        owner.wait_for_function("() => window.__pendingCorrespondence && window.__pendingCorrespondence.length >= 1")
        owner.locator("#case-id").fill("case-left-behind")
        owner.wait_for_function("() => document.getElementById('message-list').childElementCount === 0")
        assert HUMAN_TEXT not in owner.locator("#message-log").inner_text()
        assert owner.locator("#inbox-attention").inner_text() == ""
        owner.evaluate("() => { window.__pendingCorrespondence.splice(0).forEach((release) => release()); }")
        owner.wait_for_timeout(300)
        assert owner.locator("#message-list").inner_text() == ""
        assert HUMAN_TEXT not in owner.locator("#message-log").inner_text()
        assert AI_TEXT not in owner.locator("#inbox-attention").inner_text()

        owner.goto(browser.SAME_ORIGIN + CASE_PAGE_PATH, wait_until="domcontentloaded")
        owner.locator("#case-credential").fill(OWNER_CREDENTIAL)
        owner.locator("#case-login button[type='submit']").click()
        owner.wait_for_function("() => document.getElementById('case-auth-status').textContent === 'Signed in'")
        owner.wait_for_function(
            """() => document.getElementById('correspondence-badge').dataset.reviewNeeded === '1'
                && document.getElementById('correspondence-badge').dataset.updates === '1'
                && document.getElementById('correspondence-badge').dataset.unread === '0'"""
        )
        panel = owner.locator("#correspondence-attention")
        assert HUMAN_TEXT not in panel.inner_text()
        assert REVIEW_TEXT not in panel.inner_text()
        assert AI_TEXT not in panel.inner_text()
        assert "turn-attention-38" in panel.inner_text()
        assert "review-attention-38" in panel.inner_text()
        assert owner.locator("#correspondence-badge").get_attribute("data-external-delivery") == "false"
        assert "email or SMS" in owner.locator("#correspondence-attention-notice").inner_text()
        owner.evaluate(
            """() => {
                const original = window.fetch.bind(window);
                window.__pendingAttention = [];
                window.fetch = function (url, options) {
                    if (String(url).indexOf("/api/cases/correspondence/attention") !== -1) {
                        return new Promise((resolve, reject) => {
                            const release = () => { original(url, options).then(resolve, reject); };
                            const signal = options && options.signal;
                            if (signal && signal.aborted) { release(); return; }
                            window.__pendingAttention.push(release);
                        });
                    }
                    return original(url, options);
                };
            }"""
        )
        owner.locator("#case-logout").click()
        owner.wait_for_function("() => document.getElementById('correspondence-badge').textContent === '0'")
        owner.wait_for_function("() => document.getElementById('case-auth-status').textContent === 'Sign in required'")
        owner.evaluate("() => { (window.__pendingAttention || []).splice(0).forEach((release) => release()); }")
        owner.wait_for_timeout(300)
        assert owner.locator("#correspondence-badge").inner_text() == "0"
        assert owner.locator("#correspondence-attention-list").inner_text() == ""
        assert HUMAN_TEXT not in owner.locator("#correspondence-attention").inner_text()
        assert session.bridge.aborted_unqualified["websocket"] == []
        assert session.bridge.aborted_unqualified["sse"] == []
