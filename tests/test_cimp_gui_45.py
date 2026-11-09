"""Assigned-lawyer case review lists only authorized grants.

Factual assertions, legal source text, unresolved work, the timeline, and
private messages render as separate sections. Expired and revoked grants
disappear and deny a later read on the same session. An operational-admin
session does not open case content through this view.
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
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.lawyer_workspace_api import LAWYER_WORKSPACE_API, LAWYER_WORKSPACE_PAGE
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
OTHER_CREDENTIAL = "synthetic-refresh-token"
STRANGER_CREDENTIAL = "synthetic-access-token"
ADMIN_CREDENTIAL = "synthetic-session-token"
FACT = "The notice arrived on Monday."
RULE = "Notice must be written."
GAP = "No copy of the notice is in the file."
WHEN = "2024-01-02"
EVENT = "Notice delivered."
NOTE = "private-lawyer-note"
HOSTILE = '<script>window.__xss=1</script>'
SCOPE = ["case.read", "case.message.send"]


def _world(tmp_path):
    now = {"t": 1_700_000_000}

    def clock():
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    other = principals.install_server_role(role="lawyer")
    stranger = principals.register_from_request({})
    admin = principals.install_server_role(role="operational_admin")
    memberships = CaseMembershipStore(
        tmp_path / "memberships", key=os.urandom(32), key_id="membership-key",
        principals=principals, cases=cases, clock=clock,
    )
    messages = CaseMessageStore(
        tmp_path / "messages", key=os.urandom(32), key_id="message-key",
        principals=principals, cases=cases, memberships=memberships, clock=clock,
    )
    assignments = CaseAssignmentService(
        principals=principals, cases=cases, memberships=memberships,
        key_grants=CaseResourceKeyGrantStore(
            tmp_path / "key-grants", key=os.urandom(32), key_id="resource-grant-key",
            principals=principals, cases=cases, memberships=memberships,
        ),
        sessions={}, clock=clock,
    )
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            OTHER_CREDENTIAL: other.principal_id,
            STRANGER_CREDENTIAL: stranger.principal_id,
            ADMIN_CREDENTIAL: admin.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=600,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    handlers = CaseHandlerRegistry()
    app = FastAPI()
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions,
        case_catalog=CaseCatalog(cases, authorizer, key=case_key, key_id="case-key"),
        case_assignments=assignments, case_messages=CaseMessageService(messages),
        case_handlers=handlers, include_workspace=False, include_review=False, include_document=False,
    )
    return SimpleNamespace(
        app=app, owner=owner, lawyer=lawyer, other=other, stranger=stranger, admin=admin,
        cases=cases, authorizer=authorizer, handlers=handlers, now=now,
    )


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _mediator():
    return SimpleNamespace(intake_case_file={
        "review_fact_anchor": [FACT],
        "review_source_anchor": {"source_identity": "synthetic-source-45", "source_text": RULE},
        "proof_trace_display": {"obligations": [{
            "obligation_id": "notice",
            "proof_status": "not_executed",
            "source_identity": "synthetic-source-45",
        }]},
        "unresolved_work": [{"work_id": "gap-notice", "kind": "missing_evidence", "summary": GAP}],
        "case_timeline": [{"event_id": "delivery", "at": WHEN, "summary": EVENT}],
    })


def _create(client, token, label):
    created = client.post("/api/cases", headers=_csrf(token), json={"label": label})
    assert created.status_code == 201, created.text
    return created.json()


def _assign(world, owner_client, lawyer_client, owner_token, lawyer_token, case, *, lawyer, expires_at, key, authorize=True):
    if authorize:
        record = world.cases.select_case(actor_principal_id=world.owner.principal_id, case_id=case["case_id"])
        world.authorizer.grant_assigned_lawyer(
            owner_principal_id=world.owner.principal_id,
            lawyer_principal_id=lawyer.principal_id,
            case_id=record.case_id,
            resource_id=record.resource_id,
            tenant_id=record.tenant_id,
            actions=frozenset(SCOPE),
            expected_case_revision=record.revision,
        )
        world.handlers.bind(
            record, mediator=_mediator(), workspace_service=SimpleNamespace(case_id=record.case_id),
            authorize_delegated=lambda decision: decision.membership == "assigned-lawyer",
        )
    invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
        "case_id": case["case_id"],
        "member_principal_id": lawyer.principal_id,
        "scope": SCOPE,
        "expires_at": expires_at,
        "expected_case_revision": case["directory_revision"],
        "idempotency_key": key,
    })
    assert invited.status_code == 201, invited.text
    accepted = lawyer_client.post(
        f"/api/cases/assignments/{invited.json()['grant_id']}/accept",
        headers=_csrf(lawyer_token),
        json={"scope": SCOPE, "expected_version": 1, "idempotency_key": key + "-accept"},
    )
    assert accepted.status_code == 200, accepted.text
    return invited.json()["grant_id"], accepted.json()["version"]


def _section(page: str, element_id: str, following: str) -> str:
    return page.split(f'id="{element_id}"', 1)[1].split(f'id="{following}"', 1)[0]


def test_workspace_shell_names_the_review_sections_without_a_stream():
    assert LAWYER_WORKSPACE_API.startswith("/api/cases/")
    from pathlib import Path
    html = Path("templates/lawyer_workspace.html").read_text(encoding="utf-8")
    for element_id in ("assigned-cases", "factual-graph", "legal-graph", "unresolved-work", "timeline", "private-messages"):
        assert element_id in html or "__ASSIGNED_REVIEW_HTML__" in html
    assert "WebSocket or SSE" in html
    assert "Human legal review" in html


def test_assigned_lawyer_sees_only_authorized_cases_and_distinct_review_sections(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(world.app, base_url="https://testserver") as lawyer_client, TestClient(world.app, base_url="https://testserver") as other_client, TestClient(world.app, base_url="https://testserver") as stranger_client, TestClient(world.app, base_url="https://testserver") as admin_client:
        assert lawyer_client.get(LAWYER_WORKSPACE_API).status_code == 401
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        other_token = _login(other_client, OTHER_CREDENTIAL)
        stranger_token = _login(stranger_client, STRANGER_CREDENTIAL)
        admin_token = _login(admin_client, ADMIN_CREDENTIAL)
        primary = _create(owner_client, owner_token, "primary")
        other_case = _create(owner_client, owner_token, "other")
        ungranted = _create(owner_client, owner_token, "membership-only")
        primary_grant, _version = _assign(
            world, owner_client, lawyer_client, owner_token, lawyer_token, primary,
            lawyer=world.lawyer, expires_at=world.now["t"] + 500, key="primary",
        )
        _assign(
            world, owner_client, other_client, owner_token, other_token, other_case,
            lawyer=world.other, expires_at=world.now["t"] + 500, key="other",
        )
        _assign(
            world, owner_client, lawyer_client, owner_token, lawyer_token, ungranted,
            lawyer=world.lawyer, expires_at=world.now["t"] + 500, key="ungranted", authorize=False,
        )
        pending = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": other_case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": SCOPE,
            "expires_at": world.now["t"] + 500,
            "expected_case_revision": other_case["directory_revision"],
            "idempotency_key": "pending-for-primary-lawyer",
        })
        assert pending.status_code == 403 or pending.status_code == 409 or pending.status_code == 201
        thread = owner_client.post("/api/cases/messages/threads", headers=_csrf(owner_token), json={
            "case_id": primary["case_id"], "idempotency_key": "review-thread",
        })
        assert thread.status_code == 201, thread.text
        for index, text in enumerate((NOTE, HOSTILE)):
            sent = owner_client.post(
                f"/api/cases/messages/threads/{thread.json()['thread_id']}/messages",
                headers=_csrf(owner_token),
                json={"case_id": primary["case_id"], "text": text, "idempotency_key": f"note-{index}"},
            )
            assert sent.status_code == 201, sent.text

        listed = lawyer_client.get(LAWYER_WORKSPACE_API)
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["admin_bypass"] is False
        assert body["permits_operational_admin"] is False
        assert body["transport"]["websocket"] is False
        assert body["transport"]["sse"] is False
        assert [item["case_id"] for item in body["cases"]] == [primary["case_id"]]
        assert all(item["plaintext_available"] is False for item in body["cases"])
        assert FACT not in listed.text
        assert RULE not in listed.text

        stranger = stranger_client.get(LAWYER_WORKSPACE_API)
        assert stranger.status_code == 200, stranger.text
        assert stranger.json()["cases"] == []
        other_list = other_client.get(LAWYER_WORKSPACE_API)
        assert [item["case_id"] for item in other_list.json()["cases"]] == [other_case["case_id"]]

        opened = lawyer_client.get(f"{LAWYER_WORKSPACE_API}/{primary['case_id']}")
        assert opened.status_code == 200, opened.text
        review = opened.json()
        assert review["membership"] == "assigned-lawyer"
        assert review["actor_is_encrypted_owner"] is False
        assert review["actor_principal_id"] != review["canonical_owner_principal_id"]
        assert review["graphs_are_distinct"] is True
        assert review["factual_graph"]["graph_kind"] == "factual"
        assert review["legal_graph"]["graph_kind"] == "legal"
        assert review["factual_graph"]["rewrites_legal_rules"] is False
        assert review["legal_graph"]["user_facts_are_not_law"] is True
        assert review["legal_graph"]["governing_legal_authority"] is False
        assert [item["text"] for item in review["factual_graph"]["items"]] == [FACT]
        assert [item["text"] for item in review["legal_graph"]["items"]] == [RULE]
        assert GAP in [item["text"] for item in review["unresolved_work"]]
        assert any(item["status"] == "not_executed" for item in review["unresolved_work"])
        assert review["timeline"][0]["at"] == WHEN
        assert review["timeline"][0]["text"] == EVENT
        texts = [item["text"] for item in review["private_messages"]]
        assert NOTE in texts and HOSTILE in texts
        assert all(item["disposition"] == "conversation" and item["adopted_as_evidence"] is False for item in review["private_messages"])

        page = lawyer_client.get(f"{LAWYER_WORKSPACE_API}/{primary['case_id']}/page")
        assert page.status_code == 200, page.text
        factual = _section(page.text, "factual-graph", "legal-graph")
        legal = _section(page.text, "legal-graph", "unresolved-work")
        unresolved = _section(page.text, "unresolved-work", "timeline")
        timeline = _section(page.text, "timeline", "private-messages")
        messages = page.text.split('id="private-messages"', 1)[1]
        assert FACT in factual and RULE not in factual
        assert RULE in legal and FACT not in legal
        assert GAP in unresolved and "not_executed" in unresolved
        assert WHEN in timeline and EVENT in timeline
        assert NOTE in messages
        assert "<script>window.__xss=1</script>" not in page.text
        assert "&lt;script&gt;window.__xss=1&lt;/script&gt;" in messages

        denied_other = lawyer_client.get(f"{LAWYER_WORKSPACE_API}/{other_case['case_id']}")
        assert denied_other.status_code == 403
        assert denied_other.json()["case_content"] is False
        assert FACT not in denied_other.text
        denied_ungranted = lawyer_client.get(f"{LAWYER_WORKSPACE_API}/{ungranted['case_id']}")
        assert denied_ungranted.status_code == 403
        assert denied_ungranted.json()["error"] == "role_does_not_grant_case_access"
        assert RULE not in denied_ungranted.text

        admin_list = admin_client.get(LAWYER_WORKSPACE_API)
        assert admin_list.status_code == 200, admin_list.text
        assert admin_list.json()["cases"] == []
        assert admin_list.json()["admin_bypass"] is False
        admin_open = admin_client.get(f"{LAWYER_WORKSPACE_API}/{primary['case_id']}")
        assert admin_open.status_code == 403
        assert admin_open.json()["admin_bypass"] is False
        assert admin_open.json()["case_content"] is False
        assert FACT not in admin_open.text and NOTE not in admin_open.text
        shell = admin_client.get(LAWYER_WORKSPACE_PAGE)
        assert shell.status_code == 200
        assert 'id="factual-graph"' in shell.text
        assert FACT not in shell.text
        assert "websocket" in shell.text

        world.now["t"] += 500
        expired = lawyer_client.get(LAWYER_WORKSPACE_API)
        assert expired.status_code == 200, expired.text
        assert expired.json()["cases"] == []
        expired_open = lawyer_client.get(f"{LAWYER_WORKSPACE_API}/{primary['case_id']}")
        assert expired_open.status_code == 403
        assert expired_open.json()["error"] == "grant_expired"
        assert expired_open.json()["case_content"] is False
        assert FACT not in expired_open.text and NOTE not in expired_open.text
        expired_page = lawyer_client.get(f"{LAWYER_WORKSPACE_API}/{primary['case_id']}/page")
        assert expired_page.status_code == 403
        assert FACT not in expired_page.text

        world.now["t"] -= 500
        removed = owner_client.post(
            f"/api/cases/assignments/{primary_grant}/remove",
            headers=_csrf(owner_token),
            json={"expected_version": _version},
        )
        assert removed.status_code == 200, removed.text
        after = lawyer_client.get(LAWYER_WORKSPACE_API)
        assert [item["case_id"] for item in after.json()["cases"]] == []
        revoked = lawyer_client.get(f"{LAWYER_WORKSPACE_API}/{primary['case_id']}")
        assert revoked.status_code == 403
        assert revoked.json()["error"] == "membership_removed"
        assert revoked.json()["admin_bypass"] is False
        assert FACT not in revoked.text and RULE not in revoked.text
        assert lawyer_token and stranger_token and admin_token
