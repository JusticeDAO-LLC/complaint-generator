"""Case conversations stay encrypted, ordered, and idempotent.

Message text is conversation until an authorized adoption records evidence, an
answer, or a model input. Adoption does not execute a model or write evidence.
A lawyer role, a client role, or a guessed case id does not open a thread.
"""

from __future__ import annotations

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
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
READER_CREDENTIAL = "synthetic-access-token"
STRANGER_CREDENTIAL = "synthetic-refresh-token"
TEXT = "synthetic-conversation-alpha"
TEXT_B = "synthetic-conversation-beta"
TEXT_C = "synthetic-conversation-gamma"
REVISED = "synthetic-conversation-revised"


def _world(tmp_path):
    now = {"t": 1_700_000_000}

    def clock():
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    reader = principals.install_server_role(role="lawyer")
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
            READER_CREDENTIAL: reader.principal_id,
            STRANGER_CREDENTIAL: stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=120,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    service = CaseMessageService(messages)
    app = FastAPI()
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_assignments=assignments, case_messages=service,
        include_workspace=False, include_review=False, include_document=False,
    )
    return SimpleNamespace(
        app=app, owner=owner, lawyer=lawyer, reader=reader, stranger=stranger,
        messages=messages, service=service, now=now, memberships=memberships,
    )


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _create_case(client, token, label="owned"):
    created = client.post("/api/cases", headers=_csrf(token), json={"label": label})
    assert created.status_code == 201, created.text
    return created.json()


def _invite_accept(owner_client, owner_token, lawyer_client, lawyer_token, world, case, member_id, scope, key):
    invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
        "case_id": case["case_id"],
        "member_principal_id": member_id,
        "scope": scope,
        "expires_at": world.now["t"] + 500,
        "expected_case_revision": case["directory_revision"],
        "idempotency_key": key,
    })
    assert invited.status_code == 201, invited.text
    grant_id = invited.json()["grant_id"]
    accepted = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
        "scope": scope,
        "expected_version": 1,
        "idempotency_key": key + "-accept",
    })
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["state"] == "accepted"
    return grant_id, accepted.json()["version"]


def _thread(client, token, case, **extra):
    body = {"case_id": case["case_id"], "idempotency_key": extra.pop("idempotency_key", "thread-1"), **extra}
    response = client.post("/api/cases/messages/threads", headers=_csrf(token), json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _send(client, token, case, thread_id, text, key, **extra):
    body = {"case_id": case["case_id"], "text": text, "idempotency_key": key, **extra}
    response = client.post(f"/api/cases/messages/threads/{thread_id}/messages", headers=_csrf(token), json=body)
    return response


def _page(client, case, thread_id, **query):
    params = {"case_id": case["case_id"], **query}
    return client.get(f"/api/cases/messages/threads/{thread_id}/messages", params=params)


def test_ordered_idempotent_pages_and_encrypted_versions(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(world.app, base_url="https://testserver") as lawyer_client, TestClient(world.app, base_url="https://testserver") as reader_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        reader_token = _login(reader_client, READER_CREDENTIAL)
        case = _create_case(owner_client, owner_token)
        other = _create_case(owner_client, owner_token, label="other")
        send_grant, send_version = _invite_accept(
            owner_client, owner_token, lawyer_client, lawyer_token, world, case,
            world.lawyer.principal_id, ["case.read", "case.message.send", "case.review"], "invite-send",
        )
        read_grant, read_version = _invite_accept(
            owner_client, owner_token, reader_client, reader_token, world, case,
            world.reader.principal_id, ["case.read"], "invite-read",
        )
        created = _thread(owner_client, owner_token, case)
        thread_id = created["thread_id"]
        assert created["case_id"] == case["case_id"]
        assert created["actor_is_encrypted_owner"] is (created["actor_principal_id"] == created["canonical_owner_principal_id"])
        assert created["message_count"] == 0
        replay_thread = _thread(owner_client, owner_token, case)
        assert replay_thread["thread_id"] == thread_id
        mismatched_thread = owner_client.post("/api/cases/messages/threads", headers=_csrf(owner_token), json={
            "case_id": other["case_id"], "idempotency_key": "thread-1",
        })
        assert mismatched_thread.status_code == 409
        assert mismatched_thread.json()["error"] == "replay_mismatch"

        first = _send(lawyer_client, lawyer_token, case, thread_id, TEXT, "send-1",
                      membership_grant_id=send_grant, expected_membership_version=send_version)
        assert first.status_code == 201, first.text
        body = first.json()
        assert body["disposition"] == "conversation"
        assert body["sequence"] == 1
        assert body["version"] == 1
        assert body["text"] == TEXT
        assert body["sender_principal_id"] == world.lawyer.principal_id
        assert body["canonical_owner_principal_id"] == body["tenant_id"]
        assert body["adoption"] is None
        assert "adoption_does_not_execute_model_input" in body["limitations"]
        replay = _send(lawyer_client, lawyer_token, case, thread_id, TEXT, "send-1",
                       membership_grant_id=send_grant, expected_membership_version=send_version)
        assert replay.status_code == 201
        assert replay.json()["message_id"] == body["message_id"]
        assert replay.json()["sequence"] == 1
        clash = _send(lawyer_client, lawyer_token, case, thread_id, TEXT_B, "send-1",
                      membership_grant_id=send_grant, expected_membership_version=send_version)
        assert clash.status_code == 409
        assert clash.json()["error"] == "replay_mismatch"
        second = _send(owner_client, owner_token, case, thread_id, TEXT_B, "send-2")
        assert second.status_code == 201, second.text
        assert second.json()["sequence"] == 2
        assert second.json()["disposition"] == "conversation"
        third = _send(lawyer_client, lawyer_token, case, thread_id, TEXT_C, "send-3",
                      membership_grant_id=send_grant, expected_membership_version=send_version)
        assert third.status_code == 201, third.text
        assert [third.json()["sequence"], second.json()["sequence"], body["sequence"]] == [3, 2, 1]

        listed = owner_client.get("/api/cases/messages/threads", params={"case_id": case["case_id"]})
        assert listed.status_code == 200, listed.text
        assert listed.json()["threads"][0]["message_count"] == 3
        assert TEXT not in listed.text
        other_threads = owner_client.get("/api/cases/messages/threads", params={"case_id": other["case_id"]})
        assert other_threads.status_code == 200
        assert other_threads.json()["threads"] == []

        page = _page(reader_client, case, thread_id, limit=2, membership_grant_id=read_grant,
                     expected_membership_version=read_version)
        assert page.status_code == 200, page.text
        opened = page.json()
        assert [item["sequence"] for item in opened["messages"]] == [1, 2]
        assert [item["text"] for item in opened["messages"]] == [TEXT, TEXT_B]
        assert opened["next_cursor"] == 2
        assert opened["ordered"] is True
        rest = _page(reader_client, case, thread_id, limit=2, cursor=opened["next_cursor"],
                     membership_grant_id=read_grant, expected_membership_version=read_version)
        assert rest.status_code == 200, rest.text
        assert [item["sequence"] for item in rest.json()["messages"]] == [3]
        assert rest.json()["next_cursor"] is None
        unbounded = _page(reader_client, case, thread_id, limit=21, membership_grant_id=read_grant,
                          expected_membership_version=read_version)
        assert unbounded.status_code == 403
        assert unbounded.json()["error"] == "page_limit"
        denied_send = _send(reader_client, reader_token, case, thread_id, TEXT, "reader-send",
                            membership_grant_id=read_grant, expected_membership_version=read_version)
        assert denied_send.status_code == 403
        assert denied_send.json()["error"] == "action_not_permitted"

        revised = lawyer_client.post(
            f"/api/cases/messages/threads/{thread_id}/messages/{body['message_id']}/revise",
            headers=_csrf(lawyer_token),
            json={
                "case_id": case["case_id"],
                "text": REVISED,
                "expected_version": 1,
                "idempotency_key": "revise-1",
                "membership_grant_id": send_grant,
                "expected_membership_version": send_version,
            },
        )
        assert revised.status_code == 200, revised.text
        revised_body = revised.json()
        assert revised_body["version"] == 2
        assert revised_body["current_version"] == 2
        assert revised_body["text"] == REVISED
        assert revised_body["disposition"] == "conversation"
        assert [item["text"] for item in revised_body["versions"]] == [TEXT, REVISED]
        stale = lawyer_client.post(
            f"/api/cases/messages/threads/{thread_id}/messages/{body['message_id']}/revise",
            headers=_csrf(lawyer_token),
            json={
                "case_id": case["case_id"],
                "text": "synthetic-conversation-stale",
                "expected_version": 1,
                "idempotency_key": "revise-stale",
                "membership_grant_id": send_grant,
                "expected_membership_version": send_version,
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"] == "revision_conflict"
        envelopes = list((world.messages.root / "messages").glob("*.envelope"))
        assert len(envelopes) >= 2
        stored = b"".join(path.read_bytes() for path in world.messages.root.rglob("*") if path.is_file())
        assert TEXT.encode() not in stored
        assert REVISED.encode() not in stored
        assert TEXT_B.encode() not in stored

        premature = _send(owner_client, owner_token, case, thread_id, TEXT, "send-disposition", disposition="evidence")
        assert premature.status_code == 403
        assert premature.json()["error"] == "disposition_requires_transition"
        adopted = owner_client.post(
            f"/api/cases/messages/threads/{thread_id}/messages/{body['message_id']}/adopt",
            headers=_csrf(owner_token),
            json={"case_id": case["case_id"], "disposition": "model_input", "expected_version": 2, "idempotency_key": "adopt-1"},
        )
        assert adopted.status_code == 200, adopted.text
        adoption = adopted.json()
        assert adoption["disposition"] == "model_input"
        assert adoption["adoption"]["executed_as_model_input"] is False
        assert adoption["adoption"]["recorded_as_evidence_artifact"] is False
        assert adoption["adoption"]["recorded_as_intake_answer"] is False
        assert adoption["text"] == REVISED
        replay_adopt = owner_client.post(
            f"/api/cases/messages/threads/{thread_id}/messages/{body['message_id']}/adopt",
            headers=_csrf(owner_token),
            json={"case_id": case["case_id"], "disposition": "model_input", "expected_version": 2, "idempotency_key": "adopt-1"},
        )
        assert replay_adopt.status_code == 200
        assert replay_adopt.json()["disposition"] == "model_input"
        relabel = owner_client.post(
            f"/api/cases/messages/threads/{thread_id}/messages/{body['message_id']}/adopt",
            headers=_csrf(owner_token),
            json={"case_id": case["case_id"], "disposition": "evidence", "expected_version": 2, "idempotency_key": "adopt-2"},
        )
        assert relabel.status_code == 403
        assert relabel.json()["error"] == "disposition_locked"
        locked = lawyer_client.post(
            f"/api/cases/messages/threads/{thread_id}/messages/{body['message_id']}/revise",
            headers=_csrf(lawyer_token),
            json={
                "case_id": case["case_id"],
                "text": "synthetic-conversation-after",
                "expected_version": 2,
                "idempotency_key": "revise-locked",
                "membership_grant_id": send_grant,
                "expected_membership_version": send_version,
            },
        )
        assert locked.status_code == 403
        assert locked.json()["error"] == "disposition_locked"

        foreign = _page(owner_client, other, thread_id)
        assert foreign.status_code == 404
        assert foreign.json()["error"] == "missing_thread"
        assert TEXT not in foreign.text and REVISED not in foreign.text


def test_unauthorized_callers_cannot_page_or_mint_disposition(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(world.app, base_url="https://testserver") as lawyer_client, TestClient(world.app, base_url="https://testserver") as stranger_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        stranger_token = _login(stranger_client, STRANGER_CREDENTIAL)
        case = _create_case(owner_client, owner_token)
        grant_id, version = _invite_accept(
            owner_client, owner_token, lawyer_client, lawyer_token, world, case,
            world.lawyer.principal_id, ["case.read", "case.message.send"], "invite-member",
        )
        thread_id = _thread(owner_client, owner_token, case, idempotency_key="thread-auth")["thread_id"]
        sent = _send(owner_client, owner_token, case, thread_id, TEXT, "owner-send")
        assert sent.status_code == 201, sent.text
        guessed = _page(stranger_client, {"case_id": "guessed-case-id"}, thread_id)
        assert guessed.status_code == 404
        assert guessed.json()["error"] == "missing_case"
        role_only = lawyer_client.get(
            f"/api/cases/messages/threads/{thread_id}/messages",
            params={"case_id": case["case_id"]},
        )
        assert role_only.status_code == 404
        assert role_only.json()["error"] == "missing_case"
        minted = owner_client.post("/api/cases/messages/threads", headers=_csrf(owner_token), json={
            "case_id": case["case_id"], "idempotency_key": "thread-role", "role": "lawyer",
        })
        assert minted.status_code == 403
        assert minted.json()["error"] == "request_cannot_mint_authority"
        removed = owner_client.post(f"/api/cases/assignments/{grant_id}/remove", headers=_csrf(owner_token), json={
            "expected_version": version,
        })
        assert removed.status_code == 200, removed.text
        denied = _page(lawyer_client, case, thread_id, membership_grant_id=grant_id, expected_membership_version=version)
        assert denied.status_code == 403
        assert denied.json()["error"] == "membership_removed"
        assert TEXT.encode() not in denied.content

        world.now["t"] += 50_000
        fresh = _create_case(owner_client, owner_token, label="expiring")
        expiring_id, expiring_version = _invite_accept(
            owner_client, owner_token, lawyer_client, lawyer_token, world, fresh,
            world.lawyer.principal_id, ["case.read", "case.message.send"], "invite-expire",
        )
        # The invite used the already advanced clock, so move past that expiry.
        world.now["t"] += 50_000
        expired_thread = owner_client.post("/api/cases/messages/threads", headers=_csrf(owner_token), json={
            "case_id": fresh["case_id"], "idempotency_key": "thread-expire",
        })
        assert expired_thread.status_code == 201, expired_thread.text
        expired = lawyer_client.get(
            f"/api/cases/messages/threads/{expired_thread.json()['thread_id']}/messages",
            params={
                "case_id": fresh["case_id"],
                "membership_grant_id": expiring_id,
                "expected_membership_version": expiring_version,
            },
        )
        assert expired.status_code == 403
        assert expired.json()["error"] == "grant_expired"
