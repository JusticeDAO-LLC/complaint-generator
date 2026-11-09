"""Correspondence opens exact workflow context and adopts only by an authorized action.

Human messages stay conversation. Displaying AI text does not relabel it as a
human message or turn it into evidence or an accepted fact.
"""

from __future__ import annotations

from contextlib import contextmanager
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
AI_TEXT = "synthetic mediator question about the span"
HUMAN_TEXT = "synthetic human note that cites the span"
EVIDENCE_ID = "artifact-synthetic-37"
EVIDENCE_REVISION = 4
EVIDENCE_SPAN = "page-2-span-9"
INQUIRY_ID = "question-synthetic-37"
DRAFT_ID = "draft-synthetic-37"
DRAFT_SECTION = "section-facts"
STATIC_ROOT = Path(__file__).resolve().parents[1] / "static"


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
    now = {"t": 1_700_000_370}

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
    created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "workflow-adoption"})
    assert created.status_code == 201, created.text
    case = created.json()
    invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
        "case_id": case["case_id"],
        "member_principal_id": world.lawyer.principal_id,
        "scope": ["case.read", "case.message.send"],
        "expires_at": world.now["t"] + 500,
        "expected_case_revision": case["directory_revision"],
        "idempotency_key": "adopt-invite",
    })
    assert invited.status_code == 201, invited.text
    grant_id = invited.json()["grant_id"]
    accepted = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
        "scope": ["case.read", "case.message.send"],
        "expected_version": 1,
        "idempotency_key": "adopt-accept",
    })
    assert accepted.status_code == 200, accepted.text
    namespace = world.cases.select_case(actor_principal_id=world.owner.principal_id, case_id=case["case_id"])
    world.handlers.bind(namespace, mediator=object(), workspace_service=world.workspace)
    world.workspace.turns.append({
        "record_type": "ai_mediator_turn",
        "source_id": "turn-workflow-37",
        "case_id": case["case_id"],
        "canonical_owner_principal_id": namespace.tenant_id,
        "actor_principal_id": "mediator-model",
        "invocation_id": "invoke-workflow-37",
        "target_kind": "intake_question",
        "target_id": INQUIRY_ID,
        "revision": 6,
        "occurred_at": 100,
        "text": AI_TEXT,
        "adopts_evidence": False,
        "adopts_answer": False,
    })
    thread = owner_client.post("/api/cases/messages/threads", headers=_csrf(owner_token), json={
        "case_id": case["case_id"], "idempotency_key": "adopt-thread",
    })
    assert thread.status_code == 201, thread.text
    thread_id = thread.json()["thread_id"]
    sent = owner_client.post(f"/api/cases/messages/threads/{thread_id}/messages", headers=_csrf(owner_token), json={
        "case_id": case["case_id"], "text": HUMAN_TEXT, "idempotency_key": "adopt-human",
    })
    assert sent.status_code == 201, sent.text
    message = sent.json()
    assert message["disposition"] == "conversation"
    return SimpleNamespace(
        case=case, thread_id=thread_id, message=message, grant_id=grant_id,
        version=accepted.json()["version"], owner_token=owner_token, lawyer_token=lawyer_token,
        owner_id=namespace.tenant_id,
    )


def _project(client, case_id):
    return client.get("/api/cases/correspondence", params={"case_id": case_id})


def _entry(payload, record_type):
    matches = [item for item in payload["entries"] if item["record_type"] == record_type]
    assert len(matches) == 1
    return matches[0]


def test_display_keeps_conversation_and_ai_attribution_until_authorized_adoption(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(
        world.app, base_url="https://testserver"
    ) as lawyer_client, TestClient(world.app, base_url="https://testserver") as stranger_client:
        seed = _seed(world, owner_client, lawyer_client)
        before = _project(owner_client, seed.case["case_id"])
        assert before.status_code == 200, before.text
        body = before.json()
        assert body["adopts_evidence"] is False
        assert body["adopts_answer"] is False
        assert body["projection_is_authority"] is False
        human = _entry(body, "human_message")
        ai = _entry(body, "ai_mediator_turn")
        assert human["disposition"] == "conversation"
        assert human["attribution"] == "human"
        assert human["adopts_evidence"] is False
        assert human["workflow"]["exact"] is False
        assert human["workflow"]["eligible"] is False
        assert human["workflow"]["adopted"] is False
        assert human["workflow"]["reason"] == "human_message_stays_conversation"
        assert ai["attribution"] == "ai"
        assert ai["actor_principal_id"] == "mediator-model"
        assert ai["workflow"]["exact"] is True
        assert ai["workflow"]["context_kind"] == "inquiry"
        assert ai["workflow"]["context_id"] == INQUIRY_ID
        assert ai["workflow"]["context_revision"] == 6
        assert ai["workflow"]["eligible"] is False
        assert ai["workflow"]["adopted"] is False
        assert ai["workflow"]["navigation"]["case_id"] == seed.case["case_id"]
        assert ai["text"] == AI_TEXT
        assert ai["adopts_evidence"] is False
        assert ai["adopts_answer"] is False

        naked = owner_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/{seed.message['message_id']}/workflow-adoption",
            headers=_csrf(seed.owner_token),
            json={
                "case_id": seed.case["case_id"],
                "idempotency_key": "no-context",
                "context_kind": "evidence",
                "context_id": EVIDENCE_ID,
                "context_revision": EVIDENCE_REVISION,
                "span": EVIDENCE_SPAN,
                "expected_message_version": 1,
            },
        )
        assert naked.status_code == 403, naked.text
        assert naked.json()["error"] == "workflow_context_required"

        displayed = owner_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/{seed.message['message_id']}/workflow-context",
            headers=_csrf(seed.owner_token),
            json={
                "case_id": seed.case["case_id"],
                "idempotency_key": "display-link",
                "context_kind": "evidence",
                "context_id": EVIDENCE_ID,
                "context_revision": EVIDENCE_REVISION,
                "span": EVIDENCE_SPAN,
                "by_display": True,
            },
        )
        assert displayed.status_code == 403, displayed.text
        assert displayed.json()["error"] == "display_is_not_adoption"

        relabel = owner_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/turn-workflow-37/workflow-adoption",
            headers=_csrf(seed.owner_token),
            json={
                "case_id": seed.case["case_id"],
                "idempotency_key": "relabel-ai",
                "context_kind": "inquiry",
                "context_id": INQUIRY_ID,
                "context_revision": 6,
                "expected_message_version": 1,
                "attribution": "human",
                "record_type": "ai_mediator_turn",
            },
        )
        assert relabel.status_code == 403, relabel.text
        assert relabel.json()["error"] == "request_cannot_mint_authority"

        linked = owner_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/{seed.message['message_id']}/workflow-context",
            headers=_csrf(seed.owner_token),
            json={
                "case_id": seed.case["case_id"],
                "idempotency_key": "link-evidence",
                "context_kind": "evidence",
                "context_id": EVIDENCE_ID,
                "context_revision": EVIDENCE_REVISION,
                "span": EVIDENCE_SPAN,
            },
        )
        assert linked.status_code == 201, linked.text
        link_body = linked.json()
        assert link_body["adopted"] is False
        assert link_body["disposition"] == "conversation"
        assert link_body["navigation"] == {
            "surface": "evidence",
            "case_id": seed.case["case_id"],
            "context_kind": "evidence",
            "context_id": EVIDENCE_ID,
            "context_revision": EVIDENCE_REVISION,
            "section_id": None,
            "span": EVIDENCE_SPAN,
        }
        shown = _project(owner_client, seed.case["case_id"]).json()
        human = _entry(shown, "human_message")
        ai = _entry(shown, "ai_mediator_turn")
        assert human["workflow"]["eligible"] is True
        assert human["workflow"]["adopted"] is False
        assert human["workflow"]["navigation"]["span"] == EVIDENCE_SPAN
        assert human["disposition"] == "conversation"
        assert human["adopts_evidence"] is False
        assert ai["attribution"] == "ai"
        assert ai["workflow"]["adopted"] is False
        assert ai["workflow"]["eligible"] is False

        stale = owner_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/{seed.message['message_id']}/workflow-adoption",
            headers=_csrf(seed.owner_token),
            json={
                "case_id": seed.case["case_id"],
                "idempotency_key": "stale-evidence",
                "context_kind": "evidence",
                "context_id": EVIDENCE_ID,
                "context_revision": EVIDENCE_REVISION - 1,
                "span": EVIDENCE_SPAN,
                "expected_message_version": 1,
            },
        )
        assert stale.status_code == 403, stale.text
        assert stale.json()["error"] == "workflow_context_mismatch"

        denied = lawyer_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/{seed.message['message_id']}/workflow-adoption",
            headers=_csrf(seed.lawyer_token),
            json={
                "case_id": seed.case["case_id"],
                "membership_grant_id": seed.grant_id,
                "expected_membership_version": seed.version,
                "idempotency_key": "lawyer-adopt",
                "context_kind": "evidence",
                "context_id": EVIDENCE_ID,
                "context_revision": EVIDENCE_REVISION,
                "span": EVIDENCE_SPAN,
                "expected_message_version": 1,
            },
        )
        assert denied.status_code == 403, denied.text
        assert denied.json()["error"] == "action_not_permitted"
        assert _entry(_project(owner_client, seed.case["case_id"]).json(), "human_message")["workflow"]["adopted"] is False

        stranger = _login(stranger_client, STRANGER_CREDENTIAL)
        blocked = stranger_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/{seed.message['message_id']}/workflow-adoption",
            headers=_csrf(stranger),
            json={
                "case_id": seed.case["case_id"],
                "idempotency_key": "stranger-adopt",
                "context_kind": "evidence",
                "context_id": EVIDENCE_ID,
                "context_revision": EVIDENCE_REVISION,
                "span": EVIDENCE_SPAN,
                "expected_message_version": 1,
            },
        )
        assert blocked.status_code in {403, 404}
        assert HUMAN_TEXT not in blocked.text
        assert AI_TEXT not in blocked.text

        adopted = owner_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/{seed.message['message_id']}/workflow-adoption",
            headers=_csrf(seed.owner_token),
            json={
                "case_id": seed.case["case_id"],
                "idempotency_key": "owner-adopt",
                "context_kind": "evidence",
                "context_id": EVIDENCE_ID,
                "context_revision": EVIDENCE_REVISION,
                "span": EVIDENCE_SPAN,
                "expected_message_version": 1,
            },
        )
        assert adopted.status_code == 200, adopted.text
        decision = adopted.json()
        assert decision["adopted"] is True
        assert decision["explicit"] is True
        assert decision["authorized_action"] == "case.review"
        assert decision["accepted_by_display"] is False
        assert decision["disposition"] == "conversation"
        assert decision["attribution"] == "human"
        assert decision["wrote_evidence_artifact"] is False
        assert decision["wrote_intake_answer"] is False
        assert decision["ai_text_became_human"] is False
        assert decision["ai_text_became_fact"] is False
        assert decision["context"]["context_id"] == EVIDENCE_ID
        assert decision["context"]["span"] == EVIDENCE_SPAN
        replay = owner_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/{seed.message['message_id']}/workflow-adoption",
            headers=_csrf(seed.owner_token),
            json={
                "case_id": seed.case["case_id"],
                "idempotency_key": "owner-adopt",
                "context_kind": "evidence",
                "context_id": EVIDENCE_ID,
                "context_revision": EVIDENCE_REVISION,
                "span": EVIDENCE_SPAN,
                "expected_message_version": 1,
            },
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["message_id"] == decision["message_id"]
        assert replay.json()["context"] == decision["context"]
        conflict = owner_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/{seed.message['message_id']}/workflow-adoption",
            headers=_csrf(seed.owner_token),
            json={
                "case_id": seed.case["case_id"],
                "idempotency_key": "owner-adopt",
                "context_kind": "draft",
                "context_id": DRAFT_ID,
                "context_revision": 2,
                "section_id": DRAFT_SECTION,
                "expected_message_version": 1,
            },
        )
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["error"] == "replay_mismatch"

        after = _project(owner_client, seed.case["case_id"]).json()
        human = _entry(after, "human_message")
        ai = _entry(after, "ai_mediator_turn")
        assert after["adopts_evidence"] is False
        assert after["adopts_answer"] is False
        assert human["disposition"] == "conversation"
        assert human["attribution"] == "human"
        assert human["text"] == HUMAN_TEXT
        assert human["workflow"]["adopted"] is True
        assert human["workflow"]["explicit"] is True
        assert human["workflow"]["accepted_by_display"] is False
        assert human["adopts_evidence"] is False
        assert human["recorded_as_evidence_artifact"] is False
        assert ai["attribution"] == "ai"
        assert ai["workflow"]["adopted"] is False
        assert ai["workflow"]["eligible"] is False
        assert ai["text"] == AI_TEXT
        stored = owner_client.get(
            f"/api/cases/messages/threads/{seed.thread_id}/messages",
            params={"case_id": seed.case["case_id"], "limit": 20},
            headers={"x-csrf-token": seed.owner_token},
        )
        assert stored.status_code == 200, stored.text
        assert stored.json()["messages"][0]["disposition"] == "conversation"
        assert stored.json()["messages"][0]["text"] == HUMAN_TEXT


def test_draft_context_is_exact_and_unlinked_inquiry_is_not_eligible(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(
        world.app, base_url="https://testserver"
    ) as lawyer_client:
        seed = _seed(world, owner_client, lawyer_client)
        linked = owner_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/{seed.message['message_id']}/workflow-context",
            headers=_csrf(seed.owner_token),
            json={
                "case_id": seed.case["case_id"],
                "idempotency_key": "link-draft",
                "context_kind": "draft",
                "context_id": DRAFT_ID,
                "context_revision": "rev-2",
                "section_id": DRAFT_SECTION,
            },
        )
        assert linked.status_code == 201, linked.text
        assert linked.json()["adopted"] is False
        assert linked.json()["navigation"]["section_id"] == DRAFT_SECTION
        assert linked.json()["navigation"]["context_revision"] == "rev-2"
        shown = _entry(_project(owner_client, seed.case["case_id"]).json(), "human_message")
        assert shown["workflow"]["context_kind"] == "draft"
        assert shown["workflow"]["context_id"] == DRAFT_ID
        assert shown["workflow"]["section_id"] == DRAFT_SECTION
        assert shown["workflow"]["eligible"] is True
        assert shown["workflow"]["adopted"] is False
        assert shown["disposition"] == "conversation"
        adopted = owner_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/{seed.message['message_id']}/workflow-adoption",
            headers=_csrf(seed.owner_token),
            json={
                "case_id": seed.case["case_id"],
                "idempotency_key": "adopt-draft",
                "context_kind": "draft",
                "context_id": DRAFT_ID,
                "context_revision": "rev-2",
                "section_id": DRAFT_SECTION,
                "expected_message_version": 1,
            },
        )
        assert adopted.status_code == 200, adopted.text
        assert adopted.json()["disposition"] == "conversation"
        assert adopted.json()["context"]["section_id"] == DRAFT_SECTION
        inquiry = _entry(_project(owner_client, seed.case["case_id"]).json(), "ai_mediator_turn")
        assert inquiry["workflow"]["context_kind"] == "inquiry"
        assert inquiry["workflow"]["eligible"] is False
        assert inquiry["attribution"] == "ai"


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


def _sign_in(page, credential):
    page.goto(browser.SAME_ORIGIN + MESSAGE_INBOX_PATH, wait_until="domcontentloaded")
    page.locator("#inbox-credential").fill(credential)
    page.locator("#inbox-login button").click()
    page.wait_for_function("() => document.getElementById('inbox-auth-status').textContent === 'Signed in'")


def _open_case(page, seed, *, lawyer=False):
    if lawyer:
        page.locator("#case-id").fill(seed.case["case_id"])
        page.locator("#membership-grant-id").fill(seed.grant_id)
        page.locator("#membership-version").fill(str(seed.version))
    else:
        page.locator("#case-select").select_option(seed.case["case_id"])
    page.locator("#poll-ms").fill("4000")
    page.locator("#load-threads").click()
    page.locator("#thread-list button").click()
    page.wait_for_function("() => document.getElementById('inbox-status').textContent === 'Opened thread'")


def test_browser_opens_exact_context_and_adopts_only_through_the_action(tmp_path, monkeypatch):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(
        world.app, base_url="https://testserver"
    ) as lawyer_client:
        seed = _seed(world, owner_client, lawyer_client)
        linked = owner_client.post(
            f"/api/cases/messages/threads/{seed.thread_id}/messages/{seed.message['message_id']}/workflow-context",
            headers=_csrf(seed.owner_token),
            json={
                "case_id": seed.case["case_id"],
                "idempotency_key": "browser-link",
                "context_kind": "evidence",
                "context_id": EVIDENCE_ID,
                "context_revision": EVIDENCE_REVISION,
                "span": EVIDENCE_SPAN,
            },
        )
        assert linked.status_code == 201, linked.text
    with _browser(tmp_path, monkeypatch, world.app) as session:
        owner = session.pages["owner"]
        lawyer = session.pages["lawyer"]
        _sign_in(owner, OWNER_CREDENTIAL)
        _open_case(owner, seed)
        human = owner.locator("[data-record-type='human_message']")
        ai = owner.locator("[data-record-type='ai_mediator_turn']")
        assert human.get_attribute("data-attribution") == "human"
        assert human.get_attribute("data-disposition") == "conversation"
        assert human.get_attribute("data-adopted") == "false"
        assert human.locator(".message-text").inner_text() == HUMAN_TEXT
        assert ai.get_attribute("data-attribution") == "ai"
        assert ai.get_attribute("data-adopted") == "false"
        assert ai.locator(".correspondence__adopt").count() == 0
        assert owner.locator("[data-record-type='ai_mediator_turn'][data-attribution='human']").count() == 0
        ai.locator(".correspondence__context-open").click()
        owner.wait_for_selector("#workflow-context[data-context-kind='inquiry']")
        panel = owner.locator("#workflow-context")
        assert panel.get_attribute("data-context-id") == INQUIRY_ID
        assert panel.get_attribute("data-context-revision") == "6"
        assert panel.get_attribute("data-adopted") == "false"
        assert panel.get_attribute("data-attribution") == "ai"
        assert "does not adopt" in panel.inner_text()
        assert ai.get_attribute("data-attribution") == "ai"
        assert human.get_attribute("data-adopted") == "false"
        human.locator(".correspondence__context-open").click()
        owner.wait_for_selector("#workflow-context[data-context-kind='evidence']")
        assert panel.get_attribute("data-context-id") == EVIDENCE_ID
        assert panel.get_attribute("data-context-revision") == str(EVIDENCE_REVISION)
        assert panel.get_attribute("data-span") == EVIDENCE_SPAN
        assert panel.get_attribute("data-case-id") == seed.case["case_id"]
        assert panel.get_attribute("data-adopted") == "false"
        assert EVIDENCE_SPAN in panel.inner_text()
        assert human.get_attribute("data-disposition") == "conversation"
        _sign_in(lawyer, LAWYER_CREDENTIAL)
        _open_case(lawyer, seed, lawyer=True)
        lawyer.locator("[data-record-type='human_message'] .correspondence__adopt").click()
        lawyer.locator("#inbox-error").wait_for()
        assert lawyer.locator("#inbox-error").inner_text() == "action_not_permitted"
        assert lawyer.locator("[data-record-type='human_message']").get_attribute("data-adopted") == "false"
        assert lawyer.locator("[data-record-type='human_message']").get_attribute("data-disposition") == "conversation"
        assert HUMAN_TEXT in lawyer.locator("[data-record-type='human_message']").inner_text()
        assert lawyer.locator("[data-record-type='ai_mediator_turn']").get_attribute("data-attribution") == "ai"
        assert AI_TEXT in lawyer.locator("[data-record-type='ai_mediator_turn']").inner_text()
        human.locator(".correspondence__adopt").click()
        owner.wait_for_function(
            """() => {
                const row = document.querySelector("[data-record-type='human_message']");
                const open = document.querySelector("#workflow-context");
                return row && row.getAttribute("data-adopted") === "true"
                    && row.getAttribute("data-disposition") === "conversation"
                    && open && open.getAttribute("data-adopted") === "true"
                    && open.getAttribute("data-context-id") === "artifact-synthetic-37";
            }"""
        )
        assert owner.locator("[data-record-type='ai_mediator_turn']").get_attribute("data-attribution") == "ai"
        assert owner.locator("[data-record-type='ai_mediator_turn']").get_attribute("data-adopted") == "false"
        assert owner.locator("[data-record-type='human_message'] .correspondence__adopt").count() == 0
        assert "explicit authorized action" in panel.inner_text()
        lawyer.wait_for_function(
            """() => document.querySelector("[data-record-type='human_message']")
                && document.querySelector("[data-record-type='human_message']").getAttribute("data-adopted") === "true"
                && document.querySelector("[data-record-type='human_message']").getAttribute("data-disposition") === "conversation" """,
            timeout=10000,
        )
        assert lawyer.locator("[data-record-type='ai_mediator_turn']").get_attribute("data-attribution") == "ai"
        assert session.bridge.aborted_unqualified["websocket"] == []
        assert session.bridge.aborted_unqualified["sse"] == []
