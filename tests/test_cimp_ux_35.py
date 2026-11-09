"""Correspondence projection is a typed view, not a new authority.

Authorized mediator turns, human messages, review decisions, and case actions
appear in one stable order with actor, invocation, target, and revision
lineage. The projection keeps the encrypted owner and the original record
type, and it does not adopt evidence or an answer.
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
from applications.case_audit import CaseAuditStore, owner_grant_reference
from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.case_message_api import CaseMessageService
from applications.case_messages import CaseMessageStore
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
STRANGER_CREDENTIAL = "synthetic-refresh-token"
MESSAGE = "synthetic-human-message-alpha"
PURPOSE = "purpose:correspondence-review"


class _Workspace:
    def __init__(self) -> None:
        self.turns: list[dict] = []
        self.reviews: list[dict] = []

    def authorized_correspondence_activity(self, *, actor_principal_id, case_id, tenant_id, resource_id):
        del actor_principal_id, resource_id

        def same_case(item):
            return item.get("case_id") == case_id

        del tenant_id
        return {
            "mediator_turns": [dict(item) for item in self.turns if same_case(item)],
            "review_decisions": [dict(item) for item in self.reviews if same_case(item)],
        }


def _world(tmp_path):
    now = {"t": 1_700_000_200}

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
    audit = CaseAuditStore(
        tmp_path / "audit", key=os.urandom(32), key_id="audit-key",
        principals=principals, cases=cases, memberships=memberships, key_grants=key_grants,
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
        ttl_seconds=120,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    handlers = CaseHandlerRegistry()
    app = FastAPI()
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_assignments=assignments, case_messages=CaseMessageService(messages),
        case_handlers=handlers, case_audit=audit,
        include_workspace=False, include_review=False, include_document=False,
    )
    return SimpleNamespace(
        app=app, owner=owner, lawyer=lawyer, stranger=stranger, now=now, cases=cases,
        messages=messages, audit=audit, handlers=handlers, workspace=_Workspace(),
    )


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _project(client, case_id, **params):
    return client.get("/api/cases/correspondence", params={"case_id": case_id, **params})


def test_projection_orders_lineage_without_adopting(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(
        world.app, base_url="https://testserver"
    ) as lawyer_client, TestClient(world.app, base_url="https://testserver") as stranger_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        stranger_token = _login(stranger_client, STRANGER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "owned"})
        assert created.status_code == 201, created.text
        case = created.json()
        other = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "other"})
        assert other.status_code == 201, other.text
        other_case = other.json()
        invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read", "case.message.send"],
            "expires_at": world.now["t"] + 500,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "invite-read",
        })
        assert invited.status_code == 201, invited.text
        grant_id = invited.json()["grant_id"]
        accepted = lawyer_client.post(
            f"/api/cases/assignments/{grant_id}/accept",
            headers=_csrf(lawyer_token),
            json={"scope": ["case.read", "case.message.send"], "expected_version": 1, "idempotency_key": "invite-read-accept"},
        )
        assert accepted.status_code == 200, accepted.text
        version = accepted.json()["version"]
        namespace = world.cases.select_case(actor_principal_id=world.owner.principal_id, case_id=case["case_id"])
        world.handlers.bind(namespace, mediator=object(), workspace_service=world.workspace)
        owner_id = namespace.tenant_id
        world.workspace.turns.append({
            "record_type": "ai_mediator_turn",
            "source_id": "turn-alpha",
            "case_id": case["case_id"],
            "canonical_owner_principal_id": owner_id,
            "actor_principal_id": "mediator-model",
            "invocation_id": "invoke-turn-alpha",
            "target_kind": "intake_question",
            "target_id": "question-alpha",
            "revision": 3,
            "occurred_at": 100,
            "text": "synthetic mediator question",
            "adopts_evidence": False,
            "adopts_answer": False,
        })
        world.workspace.reviews.append({
            "record_type": "review_decision",
            "source_id": "review-alpha",
            "case_id": case["case_id"],
            "canonical_owner_principal_id": owner_id,
            "actor_principal_id": world.lawyer.principal_id,
            "invocation_id": "invoke-review-alpha",
            "target_kind": "draft_section",
            "target_id": "section-alpha",
            "revision": "rev-4",
            "occurred_at": 150,
            "text": "synthetic review note",
        })
        thread = owner_client.post("/api/cases/messages/threads", headers=_csrf(owner_token), json={
            "case_id": case["case_id"], "idempotency_key": "thread-1",
        })
        assert thread.status_code == 201, thread.text
        sent = lawyer_client.post(
            f"/api/cases/messages/threads/{thread.json()['thread_id']}/messages",
            headers=_csrf(lawyer_token),
            json={
                "case_id": case["case_id"],
                "text": MESSAGE,
                "idempotency_key": "send-1",
                "membership_grant_id": grant_id,
                "expected_membership_version": version,
            },
        )
        assert sent.status_code == 201, sent.text
        assert sent.json()["disposition"] == "conversation"
        assert sent.json()["adoption"] is None
        fresh = world.cases.select_case(actor_principal_id=world.owner.principal_id, case_id=case["case_id"])
        recorded = world.audit.record(
            actor_principal_id=world.owner.principal_id,
            case_id=fresh.case_id,
            tenant_id=fresh.tenant_id,
            resource_id=fresh.resource_id,
            action="case.review",
            expected_revision=fresh.revision,
            grant_id=owner_grant_reference(fresh.tenant_id),
            grant_kind="owner",
            purpose_ref=PURPOSE,
            idempotency_key="audit-correspondence-1",
        )
        before = len(world.audit.history(
            actor_principal_id=world.owner.principal_id,
            case_id=fresh.case_id,
            tenant_id=fresh.tenant_id,
            resource_id=fresh.resource_id,
            grant_id=owner_grant_reference(fresh.tenant_id),
            grant_kind="owner",
            expected_revision=fresh.revision,
        ))

        projected = _project(owner_client, case["case_id"])
        assert projected.status_code == 200, projected.text
        body = projected.json()
        assert body["projection_is_authority"] is False
        assert body["adopts_evidence"] is False
        assert body["adopts_answer"] is False
        assert body["canonical_owner_principal_id"] == owner_id
        assert body["actor_principal_id"] == world.owner.principal_id
        assert body["actor_is_encrypted_owner"] is (world.owner.principal_id == owner_id)
        assert [item["record_type"] for item in body["entries"]] == [
            "ai_mediator_turn", "review_decision", "human_message", "case_action",
        ]
        turn, review, message, action = body["entries"]
        assert turn["invocation_id"] == "invoke-turn-alpha"
        assert turn["target"] == {"kind": "intake_question", "id": "question-alpha"}
        assert turn["revision"] == 3
        assert turn["actor_principal_id"] == "mediator-model"
        assert turn["canonical_owner_principal_id"] == owner_id
        assert turn["actor_is_encrypted_owner"] is False
        assert turn["adopts_evidence"] is False
        assert review["invocation_id"] == "invoke-review-alpha"
        assert review["target"]["id"] == "section-alpha"
        assert review["revision"] == "rev-4"
        assert review["actor_principal_id"] == world.lawyer.principal_id
        assert message["source_id"] == sent.json()["message_id"]
        assert message["actor_principal_id"] == world.lawyer.principal_id
        assert message["revision"] == 1
        assert message["target"]["kind"] == "case_message"
        assert message["disposition"] == "conversation"
        assert message["text"] == MESSAGE
        assert message["invocation_id"] is None
        assert message["adoption_recorded_on_source"] is False
        assert message["recorded_as_evidence_artifact"] is False
        assert message["recorded_as_intake_answer"] is False
        assert action["source_id"] == recorded.event_id
        assert action["actor_principal_id"] == world.owner.principal_id
        assert action["canonical_owner_principal_id"] == owner_id
        assert action["actor_is_encrypted_owner"] is recorded.actor_is_encrypted_owner
        assert action["invocation_id"] is None
        assert action["revision"] == fresh.revision
        assert action["target"]["id"] == fresh.resource_id
        assert action["purpose_ref"] == PURPOSE
        assert action["adopts_answer"] is False
        assert body["sources"]["ai_mediator_turns"] == "available"
        assert body["sources"]["human_messages"] == "available"
        assert body["sources"]["review_decisions"] == "available"
        assert body["sources"]["case_actions"] == "available"
        again = _project(owner_client, case["case_id"])
        assert again.status_code == 200
        assert again.json()["entries"] == body["entries"]

        lawyer_view = _project(
            lawyer_client, case["case_id"],
            membership_grant_id=grant_id, expected_membership_version=version,
        )
        assert lawyer_view.status_code == 200, lawyer_view.text
        assert [item["source_id"] for item in lawyer_view.json()["entries"]] == [
            item["source_id"] for item in body["entries"]
        ]
        assert lawyer_view.json()["adopts_evidence"] is False

        reread = lawyer_client.get(
            f"/api/cases/messages/threads/{thread.json()['thread_id']}/messages",
            params={
                "case_id": case["case_id"],
                "membership_grant_id": grant_id,
                "expected_membership_version": version,
            },
        )
        assert reread.status_code == 200, reread.text
        assert reread.json()["messages"][0]["disposition"] == "conversation"
        assert reread.json()["messages"][0]["adoption"] is None
        after = world.audit.history(
            actor_principal_id=world.owner.principal_id,
            case_id=fresh.case_id,
            tenant_id=fresh.tenant_id,
            resource_id=fresh.resource_id,
            grant_id=owner_grant_reference(fresh.tenant_id),
            grant_kind="owner",
            expected_revision=fresh.revision,
        )
        assert len(after) == before == 1

        empty = _project(owner_client, other_case["case_id"])
        assert empty.status_code == 200, empty.text
        assert empty.json()["entries"] == []
        assert empty.json()["sources"]["human_messages"] == "empty"
        assert empty.json()["sources"]["ai_mediator_turns"] == "unavailable"
        assert MESSAGE not in empty.text

        denied = _project(stranger_client, case["case_id"])
        assert denied.status_code == 404
        assert denied.json()["error"] == "missing_case"
        assert MESSAGE not in denied.text
        minted = _project(owner_client, case["case_id"], canonical_owner_principal_id=world.lawyer.principal_id)
        assert minted.status_code == 403
        assert minted.json()["error"] == "request_cannot_mint_authority"
        posted = owner_client.post("/api/cases/correspondence", headers=_csrf(owner_token), json={"case_id": case["case_id"]})
        assert posted.status_code == 405
        anonymous = TestClient(world.app, base_url="https://testserver")
        assert anonymous.get("/api/cases/correspondence", params={"case_id": case["case_id"]}).status_code == 401

        world.workspace.turns.append({
            "record_type": "ai_mediator_turn",
            "source_id": "turn-foreign",
            "case_id": case["case_id"],
            "canonical_owner_principal_id": "other-owner",
            "actor_principal_id": "mediator-model",
            "invocation_id": "invoke-foreign",
            "target_kind": "intake_question",
            "target_id": "question-foreign",
            "revision": 1,
            "occurred_at": 90,
        })
        mismatch = _project(owner_client, case["case_id"])
        assert mismatch.status_code == 403
        assert mismatch.json()["error"] == "owner_mismatch"
        world.workspace.turns.pop()
        world.workspace.reviews.append({
            "record_type": "review_decision",
            "source_id": "review-adopt",
            "case_id": case["case_id"],
            "canonical_owner_principal_id": owner_id,
            "actor_principal_id": world.lawyer.principal_id,
            "invocation_id": "invoke-adopt",
            "target_kind": "draft_section",
            "target_id": "section-beta",
            "revision": 5,
            "occurred_at": 160,
            "adopts_evidence": True,
        })
        refused = _project(owner_client, case["case_id"])
        assert refused.status_code == 403
        assert refused.json()["error"] == "projection_cannot_adopt"
        assert reread.json()["messages"][0]["text"] == MESSAGE
        still = lawyer_client.get(
            f"/api/cases/messages/threads/{thread.json()['thread_id']}/messages",
            params={"case_id": case["case_id"], "membership_grant_id": grant_id, "expected_membership_version": version},
        )
        assert still.json()["messages"][0]["disposition"] == "conversation"
        assert still.json()["messages"][0]["adoption"] is None


def test_equal_timestamps_break_ties_by_record_type_and_source(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client:
        token = _login(owner_client, OWNER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(token), json={"label": "ties"})
        assert created.status_code == 201, created.text
        case = created.json()
        namespace = world.cases.select_case(actor_principal_id=world.owner.principal_id, case_id=case["case_id"])
        world.handlers.bind(namespace, mediator=object(), workspace_service=world.workspace)
        owner_id = namespace.tenant_id
        for source_id, record_type, target in (
            ("b-review", "review_decision", "section-b"),
            ("a-review", "review_decision", "section-a"),
            ("m-turn", "ai_mediator_turn", "question-m"),
        ):
            bucket = world.workspace.reviews if record_type == "review_decision" else world.workspace.turns
            bucket.append({
                "record_type": record_type,
                "source_id": source_id,
                "case_id": case["case_id"],
                "canonical_owner_principal_id": owner_id,
                "actor_principal_id": world.owner.principal_id,
                "invocation_id": "invoke-" + source_id,
                "target_kind": "item",
                "target_id": target,
                "revision": 1,
                "occurred_at": 150,
            })
        world.now["t"] = 150
        thread = owner_client.post("/api/cases/messages/threads", headers=_csrf(token), json={
            "case_id": case["case_id"], "idempotency_key": "thread-tie",
        })
        assert thread.status_code == 201, thread.text
        sent = owner_client.post(
            f"/api/cases/messages/threads/{thread.json()['thread_id']}/messages",
            headers=_csrf(token),
            json={"case_id": case["case_id"], "text": MESSAGE, "idempotency_key": "send-tie"},
        )
        assert sent.status_code == 201, sent.text
        projected = _project(owner_client, case["case_id"])
        assert projected.status_code == 200, projected.text
        assert [item["source_id"] for item in projected.json()["entries"]] == [
            "m-turn", sent.json()["message_id"], "a-review", "b-review",
        ]
        assert all(item["occurred_at"] == 150 for item in projected.json()["entries"])
        assert all(item["projection_is_authority"] is False for item in projected.json()["entries"])
