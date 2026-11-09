"""Owners invite lawyers and recipients accept an explicit scope.

Both parties observe pending, declined, expired, and removed states. A lawyer
role, a client-supplied role, or a guessed case id does not open content.
Content is returned only after accepted membership and key-grant admission.
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
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import CaseResourceKeyGrantStore
from integrations.private_storage import (
    PrivateArtifactBinding,
    UserOwnedKeySession,
    seal_private_artifact,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
STRANGER_CREDENTIAL = "synthetic-access-token"
OTHER_LAWYER_CREDENTIAL = "synthetic-refresh-token"
NOTE = b"synthetic-assignment-note"
KIND = "case-note"
REVISION = "3"


def _world(tmp_path):
    now = {"t": 1_700_000_000}

    def clock():
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    other_lawyer = principals.install_server_role(role="lawyer")
    stranger = principals.register_from_request({})
    memberships = CaseMembershipStore(
        tmp_path / "memberships", key=os.urandom(32), key_id="membership-key",
        principals=principals, cases=cases, clock=clock,
    )
    key_grants = CaseResourceKeyGrantStore(
        tmp_path / "key-grants", key=os.urandom(32), key_id="resource-grant-key",
        principals=principals, cases=cases, memberships=memberships,
    )
    owner_session = UserOwnedKeySession(tmp_path / "owner-keys")
    owner_session.create(protection="passphrase", passphrase="owner-passphrase")
    lawyer_session = UserOwnedKeySession(tmp_path / "lawyer-keys")
    lawyer_session.create(protection="passphrase", passphrase="lawyer-passphrase")
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            OTHER_LAWYER_CREDENTIAL: other_lawyer.principal_id,
            STRANGER_CREDENTIAL: stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=120,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    assignments = CaseAssignmentService(
        principals=principals, cases=cases, memberships=memberships, key_grants=key_grants,
        sessions={owner.principal_id: owner_session, lawyer.principal_id: lawyer_session},
        clock=clock,
    )
    app = FastAPI()
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_assignments=assignments, include_workspace=False, include_review=False, include_document=False,
    )
    return SimpleNamespace(
        app=app, owner=owner, lawyer=lawyer, other_lawyer=other_lawyer, stranger=stranger,
        cases=cases, authorizer=authorizer, catalog=catalog, assignments=assignments,
        owner_session=owner_session, now=now,
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


def _states(client):
    listed = client.get("/api/cases/assignments")
    assert listed.status_code == 200, listed.text
    return {row["grant_id"]: row["state"] for row in listed.json()["assignments"]}


def _seal(world, case):
    world.owner_session.ensure_data_key(case["tenant_id"], case["case_id"])
    binding = PrivateArtifactBinding(
        tenant_id=case["tenant_id"], case_id=case["case_id"], artifact_kind=KIND,
        revision=REVISION, principal_id=case["tenant_id"],
    )
    key_id, key = world.owner_session.provider().resolve(binding)
    envelope = seal_private_artifact(NOTE, binding=binding, key=key, key_id=key_id)
    world.assignments.bind_artifact(
        case_id=case["case_id"], artifact_kind=KIND, artifact_revision=REVISION, envelope=envelope,
    )


def test_invite_accept_decline_expiry_and_removal_are_visible_to_both_parties(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(world.app, base_url="https://testserver") as lawyer_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        page = owner_client.get("/cases")
        assert page.status_code == 200
        assert "Invite lawyer" in page.text
        assert "Accept scope" in page.text
        lawyers = owner_client.get("/api/cases/lawyers")
        assert lawyers.status_code == 200
        assert world.lawyer.principal_id in {item["principal_id"] for item in lawyers.json()["lawyers"]}
        assert set(lawyers.json()["lawyers"][0]) == {"principal_id"}
        case = _create_case(owner_client, owner_token)
        invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read", "case.review"],
            "expires_at": world.now["t"] + 500,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "invite-read",
        })
        assert invited.status_code == 201, invited.text
        grant_id = invited.json()["grant_id"]
        assert invited.json()["state"] == "pending"
        assert invited.json()["scope"] == ["case.read", "case.review"]
        assert invited.json()["plaintext_available"] is False
        replay = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read", "case.review"],
            "expires_at": world.now["t"] + 500,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "invite-read",
        })
        assert replay.status_code == 201
        assert replay.json()["grant_id"] == grant_id
        assert _states(owner_client)[grant_id] == "pending"
        assert _states(lawyer_client)[grant_id] == "pending"
        mismatched = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
            "scope": ["case.read"],
            "expected_version": 1,
            "idempotency_key": "accept-narrow",
        })
        assert mismatched.status_code == 403
        assert mismatched.json()["error"] == "scope_mismatch"
        assert _states(lawyer_client)[grant_id] == "pending"
        accepted = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
            "scope": ["case.review", "case.read"],
            "expected_version": 1,
            "idempotency_key": "accept-read",
        })
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["state"] == "accepted"
        assert accepted.json()["scope"] == ["case.read", "case.review"]
        assert _states(owner_client)[grant_id] == "accepted"

        declining = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.download"],
            "expires_at": world.now["t"] + 500,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "invite-download",
        })
        assert declining.status_code == 201, declining.text
        declined_id = declining.json()["grant_id"]
        declined = lawyer_client.post(f"/api/cases/assignments/{declined_id}/decline", headers=_csrf(lawyer_token), json={
            "expected_version": 1,
            "idempotency_key": "decline-download",
        })
        assert declined.status_code == 200, declined.text
        assert declined.json()["state"] == "declined"
        assert _states(owner_client)[declined_id] == "declined"

        expiring = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.message.send"],
            "expires_at": world.now["t"] + 50,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "invite-message",
        })
        assert expiring.status_code == 201, expiring.text
        expired_id = expiring.json()["grant_id"]
        world.now["t"] += 60
        assert _states(owner_client)[expired_id] == "expired"
        assert _states(lawyer_client)[expired_id] == "expired"
        late = lawyer_client.post(f"/api/cases/assignments/{expired_id}/accept", headers=_csrf(lawyer_token), json={
            "scope": ["case.message.send"],
            "expected_version": 1,
            "idempotency_key": "accept-late",
        })
        assert late.status_code == 403
        assert late.json()["error"] == "grant_expired"
        world.now["t"] -= 60

        removing = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read"],
            "expires_at": world.now["t"] + 800,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "invite-remove",
        })
        assert removing.status_code == 201, removing.text
        removed_id = removing.json()["grant_id"]
        removed = owner_client.post(f"/api/cases/assignments/{removed_id}/remove", headers=_csrf(owner_token), json={
            "expected_version": 1,
        })
        assert removed.status_code == 200, removed.text
        assert removed.json()["state"] == "removed"
        assert _states(lawyer_client)[removed_id] == "removed"
        assert _states(owner_client) == {
            grant_id: "accepted",
            declined_id: "declined",
            expired_id: "pending",
            removed_id: "removed",
        }


def test_role_and_guessed_case_do_not_open_content_until_membership_and_key_grant(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(world.app, base_url="https://testserver") as lawyer_client, TestClient(world.app, base_url="https://testserver") as stranger_client, TestClient(world.app, base_url="https://testserver") as other_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        stranger_token = _login(stranger_client, STRANGER_CREDENTIAL)
        other_token = _login(other_client, OTHER_LAWYER_CREDENTIAL)
        case = _create_case(owner_client, owner_token)
        _seal(world, case)
        guessed = "0" * 32
        for client, token in ((lawyer_client, lawyer_token), (stranger_client, stranger_token), (other_client, other_token)):
            hidden = client.get(f"/api/cases/{case['case_id']}")
            assert hidden.status_code == 404
            assert hidden.json()["error"] == "missing_case"
            assert NOTE.decode() not in hidden.text
        minted = lawyer_client.post("/api/cases/assignments", headers=_csrf(lawyer_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read"],
            "role": "lawyer",
            "expires_at": world.now["t"] + 500,
            "expected_case_revision": 1,
            "idempotency_key": "self-invite",
        })
        assert minted.status_code == 403
        assert minted.json()["error"] == "request_cannot_mint_authority"
        guessed_case = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": guessed,
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read"],
            "expires_at": world.now["t"] + 500,
            "expected_case_revision": 1,
            "idempotency_key": "guess-case",
        })
        assert guessed_case.status_code == 404
        assert guessed_case.json()["error"] == "missing_case"
        stranger_invite = stranger_client.post("/api/cases/assignments", headers=_csrf(stranger_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read"],
            "expires_at": world.now["t"] + 500,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "stranger-invite",
        })
        assert stranger_invite.status_code == 404
        assert stranger_invite.json()["error"] == "missing_case"
        assert case["tenant_id"] not in stranger_invite.text
        invited = owner_client.post("/api/cases/assignments", headers=_csrf(owner_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read"],
            "expires_at": world.now["t"] + 500,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "invite-content",
        })
        assert invited.status_code == 201, invited.text
        grant_id = invited.json()["grant_id"]
        world.authorizer.grant_assigned_lawyer(
            owner_principal_id=world.owner.principal_id,
            lawyer_principal_id=world.lawyer.principal_id,
            case_id=case["case_id"],
            resource_id=case["resource_id"],
            tenant_id=case["tenant_id"],
            actions={"case.read"},
            expected_case_revision=case["directory_revision"],
        )
        premature = lawyer_client.post(f"/api/cases/assignments/{grant_id}/content", headers=_csrf(lawyer_token), json={
            "key_grant_id": guessed,
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "expected_version": 1,
        })
        assert premature.status_code == 403
        assert premature.json()["error"] == "membership_required"
        assert NOTE.decode() not in premature.text
        early_key = owner_client.post(f"/api/cases/assignments/{grant_id}/key-grant", headers=_csrf(owner_token), json={
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "idempotency_key": "too-soon",
        })
        assert early_key.status_code == 403
        assert early_key.json()["error"] == "membership_required"
        accepted = lawyer_client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(lawyer_token), json={
            "scope": ["case.read"],
            "expected_version": 1,
            "idempotency_key": "accept-content",
        })
        assert accepted.status_code == 200, accepted.text
        without_key = lawyer_client.post(f"/api/cases/assignments/{grant_id}/content", headers=_csrf(lawyer_token), json={
            "key_grant_id": guessed,
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "expected_version": accepted.json()["version"],
            "role": "lawyer",
            "is_lawyer": True,
        })
        assert without_key.status_code == 403
        assert without_key.json()["error"] == "request_cannot_mint_authority"
        still_closed = lawyer_client.post(f"/api/cases/assignments/{grant_id}/content", headers=_csrf(lawyer_token), json={
            "key_grant_id": guessed,
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "expected_version": accepted.json()["version"],
        })
        assert still_closed.status_code == 403, still_closed.text
        assert still_closed.json()["error"] == "key_grant_required"
        assert NOTE.decode() not in still_closed.text
        other_closed = other_client.get("/api/cases/assignments")
        assert other_closed.status_code == 200
        assert grant_id not in other_closed.text
        assert other_client.post(f"/api/cases/assignments/{grant_id}/content", headers=_csrf(other_token), json={
            "key_grant_id": guessed,
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "expected_version": accepted.json()["version"],
        }).status_code == 404
        issued = owner_client.post(f"/api/cases/assignments/{grant_id}/key-grant", headers=_csrf(owner_token), json={
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "idempotency_key": "admit-key",
            "browser_key": "raw",
        })
        assert issued.status_code == 403
        assert issued.json()["error"] == "request_cannot_mint_authority"
        issued = owner_client.post(f"/api/cases/assignments/{grant_id}/key-grant", headers=_csrf(owner_token), json={
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "idempotency_key": "admit-key",
        })
        assert issued.status_code == 201, issued.text
        assert issued.json()["plaintext_available"] is False
        assert "wrapped_ciphertext" not in issued.json()
        assert "owner-passphrase" not in issued.text
        opened = lawyer_client.post(f"/api/cases/assignments/{grant_id}/content", headers=_csrf(lawyer_token), json={
            "key_grant_id": issued.json()["key_grant_id"],
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "expected_version": accepted.json()["version"],
        })
        assert opened.status_code == 200, opened.text
        assert opened.json()["plaintext_available"] is True
        assert opened.json()["text"] == NOTE.decode()
        assert opened.json()["actor_is_encrypted_owner"] is False
        assert opened.json()["canonical_owner_principal_id"] == case["tenant_id"]
        assert opened.json()["key_grant"] == "admitted"
        owner_closed = owner_client.post(f"/api/cases/assignments/{grant_id}/content", headers=_csrf(owner_token), json={
            "key_grant_id": issued.json()["key_grant_id"],
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "expected_version": accepted.json()["version"],
        })
        assert owner_closed.status_code == 403
        assert owner_closed.json()["error"] == "membership_required"
        catalog = lawyer_client.get(f"/api/cases/{case['case_id']}")
        assert catalog.status_code == 404
        assert NOTE.decode() not in catalog.text
