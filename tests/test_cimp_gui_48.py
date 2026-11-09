"""Recipient-scoped in-app notifications omit complaint and evidence text.

Assignment, message, and review events notify only the named recipient.
Repeating read, unread, or retry does not duplicate the effect. Email, SMS,
and external chat stay inactive.
"""

from __future__ import annotations

import json
import os
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
from applications.case_notifications import CaseNotificationService
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
STRANGER_CREDENTIAL = "synthetic-refresh-token"
COMPLAINT = "synthetic-complaint-narrative-should-not-leak"
EVIDENCE = "synthetic-evidence-excerpt-should-not-leak"


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
    notifications = CaseNotificationService(memberships=memberships, clock=clock)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            STRANGER_CREDENTIAL: stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=120,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    app = FastAPI()
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_assignments=assignments, case_messages=CaseMessageService(messages),
        case_notifications=notifications,
        include_workspace=False, include_review=False, include_document=False,
    )
    return SimpleNamespace(
        app=app, owner=owner, lawyer=lawyer, stranger=stranger, now=now,
        notifications=notifications, messages=messages,
    )


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _assert_private(payload):
    encoded = json.dumps(payload)
    assert COMPLAINT not in encoded
    assert EVIDENCE not in encoded
    assert "smtp" not in encoded.lower()
    lowered = encoded.lower()
    for token in ("\"email\"", "\"sms\"", "\"phone\""):
        assert token not in lowered
    assert _walk_external(payload)


def _walk_external(payload):
    if isinstance(payload, dict):
        if "external_delivery" in payload:
            assert payload["external_delivery"] is False
        if "channels" in payload:
            assert payload["channels"] == ["in_app"]
        for value in payload.values():
            _walk_external(value)
    elif isinstance(payload, list):
        for value in payload:
            _walk_external(value)
    return True


def _clients(world):
    owner = TestClient(world.app, base_url="https://testserver")
    lawyer = TestClient(world.app, base_url="https://testserver")
    stranger = TestClient(world.app, base_url="https://testserver")
    return (
        owner, _login(owner, OWNER_CREDENTIAL),
        lawyer, _login(lawyer, LAWYER_CREDENTIAL),
        stranger, _login(stranger, STRANGER_CREDENTIAL),
    )


def _case(owner, token):
    created = owner.post("/api/cases", headers=_csrf(token), json={"label": COMPLAINT})
    assert created.status_code == 201, created.text
    return created.json()


def _invite(owner, token, world, case, member_id):
    invited = owner.post("/api/cases/assignments", headers=_csrf(token), json={
        "case_id": case["case_id"],
        "member_principal_id": member_id,
        "scope": ["case.read", "case.message.send", "case.review"],
        "expires_at": world.now["t"] + 500,
        "expected_case_revision": case["directory_revision"],
        "idempotency_key": "invite-notice",
    })
    assert invited.status_code == 201, invited.text
    return invited.json()


def test_assignment_message_and_review_notices_are_recipient_scoped(tmp_path):
    world = _world(tmp_path)
    owner, owner_token, lawyer, lawyer_token, stranger, stranger_token = _clients(world)
    case = _case(owner, owner_token)
    grant = _invite(owner, owner_token, world, case, world.lawyer.principal_id)
    replay = _invite(owner, owner_token, world, case, world.lawyer.principal_id)
    assert replay["grant_id"] == grant["grant_id"]

    lawyer_rows = lawyer.get("/api/cases/notifications", headers=_csrf(lawyer_token))
    assert lawyer_rows.status_code == 200, lawyer_rows.text
    _assert_private(lawyer_rows.json())
    assert len(lawyer_rows.json()["notifications"]) == 1
    notice = lawyer_rows.json()["notifications"][0]
    assert notice["event_kind"] == "assignment"
    assert notice["recipient_principal_id"] == world.lawyer.principal_id
    assert notice["badge_label"] == "Assignment"
    assert notice["read"] is False
    assert notice["channel"] == "in_app"
    assert notice["external_delivery"] is False
    assert lawyer_rows.json()["badge"]["unread_count"] == 1
    assert lawyer_rows.json()["badge"]["badge_label"] == "1"

    owner_rows = owner.get("/api/cases/notifications", headers=_csrf(owner_token))
    assert owner_rows.status_code == 200
    assert owner_rows.json()["notifications"] == []
    stranger_rows = stranger.get("/api/cases/notifications", headers=_csrf(stranger_token))
    assert stranger_rows.json()["notifications"] == []
    hidden = stranger.post(f"/api/cases/notifications/{notice['notification_id']}/read", headers=_csrf(stranger_token), json={})
    assert hidden.status_code == 404
    assert hidden.json()["error"] == "missing_notification"

    accepted = lawyer.post(f"/api/cases/assignments/{grant['grant_id']}/accept", headers=_csrf(lawyer_token), json={
        "scope": ["case.read", "case.message.send", "case.review"],
        "expected_version": grant["version"],
        "idempotency_key": "invite-notice-accept",
    })
    assert accepted.status_code == 200, accepted.text
    owner_after = owner.get("/api/cases/notifications", headers=_csrf(owner_token))
    assert [item["event_kind"] for item in owner_after.json()["notifications"]] == ["assignment"]
    assert owner_after.json()["notifications"][0]["recipient_principal_id"] == world.owner.principal_id

    thread = owner.post("/api/cases/messages/threads", headers=_csrf(owner_token), json={
        "case_id": case["case_id"],
        "idempotency_key": "thread-notice",
    })
    assert thread.status_code == 201, thread.text
    sent = owner.post(
        f"/api/cases/messages/threads/{thread.json()['thread_id']}/messages",
        headers=_csrf(owner_token),
        json={"case_id": case["case_id"], "text": EVIDENCE, "idempotency_key": "send-notice"},
    )
    assert sent.status_code == 201, sent.text
    resent = owner.post(
        f"/api/cases/messages/threads/{thread.json()['thread_id']}/messages",
        headers=_csrf(owner_token),
        json={"case_id": case["case_id"], "text": EVIDENCE, "idempotency_key": "send-notice"},
    )
    assert resent.status_code == 201, resent.text
    lawyer_after = lawyer.get("/api/cases/notifications", headers=_csrf(lawyer_token))
    kinds = sorted(item["event_kind"] for item in lawyer_after.json()["notifications"])
    assert kinds == ["assignment", "message"]
    message_notice = next(item for item in lawyer_after.json()["notifications"] if item["event_kind"] == "message")
    assert message_notice["source_id"] == sent.json()["message_id"]
    _assert_private(lawyer_after.json())
    assert EVIDENCE not in json.dumps(message_notice)

    blocked = lawyer.post("/api/cases/notifications", headers=_csrf(lawyer_token), json={
        "event_kind": "review",
        "case_id": case["case_id"],
        "recipient_principal_id": world.owner.principal_id,
        "source_id": "review-item-1",
        "idempotency_key": "review-notice",
        "evidence": EVIDENCE,
    })
    assert blocked.status_code == 403
    assert blocked.json()["error"] == "request_cannot_mint_authority"
    review = lawyer.post("/api/cases/notifications", headers=_csrf(lawyer_token), json={
        "event_kind": "review",
        "case_id": case["case_id"],
        "recipient_principal_id": world.owner.principal_id,
        "source_id": "review-item-1",
        "idempotency_key": "review-notice",
        "text": COMPLAINT,
        "proposed_text": EVIDENCE,
    })
    assert review.status_code == 403
    assert review.json()["error"] == "complaint_text_rejected"
    clean = lawyer.post("/api/cases/notifications", headers=_csrf(lawyer_token), json={
        "event_kind": "review",
        "case_id": case["case_id"],
        "recipient_principal_id": world.owner.principal_id,
        "source_id": "review-item-1",
        "idempotency_key": "review-notice",
    })
    assert clean.status_code == 201, clean.text
    again = lawyer.post("/api/cases/notifications", headers=_csrf(lawyer_token), json={
        "event_kind": "review",
        "case_id": case["case_id"],
        "recipient_principal_id": world.owner.principal_id,
        "source_id": "review-item-1",
        "idempotency_key": "review-notice",
    })
    assert again.status_code == 201
    assert again.json()["replayed"] is True
    assert again.json()["notification_id"] == clean.json()["notification_id"]
    owner_review = owner.get("/api/cases/notifications", headers=_csrf(owner_token))
    assert any(item["event_kind"] == "review" and item["badge_label"] == "Review" for item in owner_review.json()["notifications"])
    _assert_private(owner_review.json())

    denied = stranger.post("/api/cases/notifications", headers=_csrf(stranger_token), json={
        "event_kind": "review",
        "case_id": case["case_id"],
        "recipient_principal_id": world.owner.principal_id,
        "source_id": "review-item-2",
        "idempotency_key": "stranger-review",
    })
    assert denied.status_code == 403
    assert denied.json()["error"] == "notification_denied"
    outside = stranger.post("/api/cases/notifications", headers=_csrf(stranger_token), json={
        "event_kind": "email",
        "case_id": case["case_id"],
        "recipient_principal_id": world.owner.principal_id,
        "source_id": "review-item-3",
        "idempotency_key": "email-review",
    })
    assert outside.status_code == 403
    assert outside.json()["external_delivery"] is False


def test_read_unread_and_retry_are_idempotent_without_external_delivery(tmp_path):
    world = _world(tmp_path)
    owner, owner_token, lawyer, lawyer_token, _stranger, _stranger_token = _clients(world)
    case = _case(owner, owner_token)
    _invite(owner, owner_token, world, case, world.lawyer.principal_id)
    listed = lawyer.get("/api/cases/notifications", headers=_csrf(lawyer_token))
    notice_id = listed.json()["notifications"][0]["notification_id"]

    first = lawyer.post(f"/api/cases/notifications/{notice_id}/read", headers=_csrf(lawyer_token), json={})
    second = lawyer.post(f"/api/cases/notifications/{notice_id}/read", headers=_csrf(lawyer_token), json={})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["read"] is True and first.json()["replayed"] is False
    assert second.json()["read"] is True and second.json()["replayed"] is True
    assert second.json()["badge"]["unread_count"] == 0
    assert second.json()["badge"]["badge_label"] == "0"
    assert second.json()["external_delivery"] is False
    _assert_private(second.json())

    unread = lawyer.post(f"/api/cases/notifications/{notice_id}/unread", headers=_csrf(lawyer_token), json={})
    unread_again = lawyer.post(f"/api/cases/notifications/{notice_id}/unread", headers=_csrf(lawyer_token), json={})
    assert unread.json()["read"] is False and unread.json()["replayed"] is False
    assert unread_again.json()["read"] is False and unread_again.json()["replayed"] is True
    badge = lawyer.get("/api/cases/notifications/badge", headers=_csrf(lawyer_token))
    assert badge.json()["unread_count"] == 1
    assert badge.json()["channel"] == "in_app"
    assert badge.json()["channels"] == ["in_app"]
    assert badge.json()["external_delivery"] is False
    assert COMPLAINT not in badge.text

    retry = lawyer.post(f"/api/cases/notifications/{notice_id}/retry", headers=_csrf(lawyer_token), json={
        "idempotency_key": "retry-1",
    })
    retry_again = lawyer.post(f"/api/cases/notifications/{notice_id}/retry", headers=_csrf(lawyer_token), json={
        "idempotency_key": "retry-1",
    })
    assert retry.status_code == 200, retry.text
    assert retry.json()["replayed"] is False
    assert retry.json()["attempt_count"] == 2
    assert retry.json()["channel"] == "in_app"
    assert retry.json()["channels"] == ["in_app"]
    assert retry.json()["external_delivery"] is False
    assert retry_again.json()["replayed"] is True
    assert retry_again.json()["attempt_count"] == 2
    assert retry_again.json()["external_delivery"] is False

    leaked = lawyer.post(f"/api/cases/notifications/{notice_id}/retry", headers=_csrf(lawyer_token), json={
        "idempotency_key": "retry-2",
        "sms": "555-0100",
        "text": EVIDENCE,
    })
    assert leaked.status_code == 403
    assert leaked.json()["error"] == "complaint_text_rejected"

    log = lawyer.get("/api/cases/notifications/log", headers=_csrf(lawyer_token))
    assert log.status_code == 200
    _assert_private(log.json())
    actions = [item["action"] for item in log.json()["entries"]]
    assert actions.count("notification_recorded") == 1
    assert "notification_read" in actions
    assert "notification_unread" in actions
    assert actions.count("notification_retry") == 1
    for entry in log.json()["entries"]:
        assert set(entry) == {
            "action", "notification_id", "event_kind", "recipient_principal_id",
            "actor_principal_id", "case_id", "source_id", "channel", "external_delivery",
        }
        assert entry["external_delivery"] is False
        assert entry["channel"] == "in_app"

    anonymous = TestClient(world.app, base_url="https://testserver")
    denied = anonymous.get("/api/cases/notifications")
    assert denied.status_code == 401


def test_cases_page_badge_does_not_activate_external_delivery():
    page = (os.path.dirname(__file__) + "/../templates/cases.html")
    html = open(os.path.normpath(page), encoding="utf-8").read()
    assert 'id="notification-badge"' in html
    assert 'data-channel="in_app"' in html
    assert "does not send email, SMS, or external chat" in html
    assert "complaint or evidence text" in html
    assert "/api/cases/notifications" in html
    assert "smtp" not in html.lower()
    assert "sms:" not in html.lower()
