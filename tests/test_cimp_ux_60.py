"""Recipient-bound collaboration keys use distinct owner and lawyer wallets.

A lawyer role, an assigned-lawyer policy row, or an accepted membership label
does not unwrap owner-locked content. Opening requires the accepted grant,
the current key epoch, and a wrap held only by that recipient's wallet.
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
from applications.case_review_store import CaseReviewService, CaseReviewStoreError
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.complaint_workspace import ComplaintWorkspaceService
from applications.principal_store import PrincipalStore
from applications.workspace_case_authority import WorkspaceCaseAuthorityError, issue_workspace_case_authority
from integrations.private_collaboration import CaseResourceKeyGrantError, CaseResourceKeyGrantStore
from integrations.private_storage import (
    PrivateArtifactBinding,
    UserOwnedKeySession,
    seal_private_artifact,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
OTHER_LAWYER_CREDENTIAL = "synthetic-refresh-token"
NOTE = b"synthetic-ux60-owner-note"
KIND = "case-note"
REVISION = "ux60-v1"


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
    memberships = CaseMembershipStore(
        tmp_path / "memberships", key=os.urandom(32), key_id="membership-key",
        principals=principals, cases=cases, clock=clock,
    )
    key_grants = CaseResourceKeyGrantStore(
        tmp_path / "key-grants", key=os.urandom(32), key_id="resource-grant-key",
        principals=principals, cases=cases, memberships=memberships,
    )
    owner_session = UserOwnedKeySession(tmp_path / "owner-wallet")
    owner_session.create(protection="passphrase", passphrase="owner-passphrase")
    lawyer_session = UserOwnedKeySession(tmp_path / "lawyer-wallet")
    lawyer_session.create(protection="passphrase", passphrase="lawyer-passphrase")
    other_session = UserOwnedKeySession(tmp_path / "other-lawyer-wallet")
    other_session.create(protection="passphrase", passphrase="other-passphrase")
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            OTHER_LAWYER_CREDENTIAL: other.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=600,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    assignments = CaseAssignmentService(
        principals=principals, cases=cases, memberships=memberships, key_grants=key_grants,
        sessions={
            owner.principal_id: owner_session,
            lawyer.principal_id: lawyer_session,
            other.principal_id: other_session,
        },
        clock=clock,
    )
    app = FastAPI()
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_assignments=assignments, include_workspace=False, include_review=False, include_document=False,
    )
    return SimpleNamespace(
        app=app, owner=owner, lawyer=lawyer, other=other, cases=cases, authorizer=authorizer,
        assignments=assignments, key_grants=key_grants, memberships=memberships,
        owner_session=owner_session, lawyer_session=lawyer_session, other_session=other_session,
        browser=sessions, now=now, tmp_path=tmp_path,
    )


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _invite(client, token, world, case, member_id, *, scope, expires_at, idempotency_key):
    response = client.post("/api/cases/assignments", headers=_csrf(token), json={
        "case_id": case["case_id"],
        "member_principal_id": member_id,
        "scope": scope,
        "expires_at": expires_at,
        "expected_case_revision": case["directory_revision"],
        "idempotency_key": idempotency_key,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _accept(client, token, grant_id, scope, version, idempotency_key):
    response = client.post(f"/api/cases/assignments/{grant_id}/accept", headers=_csrf(token), json={
        "scope": scope,
        "expected_version": version,
        "idempotency_key": idempotency_key,
    })
    assert response.status_code == 200, response.text
    return response.json()


def _seal(world, case, plaintext, revision):
    world.owner_session.ensure_data_key(case["tenant_id"], case["case_id"])
    binding = PrivateArtifactBinding(
        tenant_id=case["tenant_id"], case_id=case["case_id"], artifact_kind=KIND,
        revision=revision, principal_id=case["tenant_id"],
    )
    key_id, key = world.owner_session.provider().resolve(binding)
    envelope = seal_private_artifact(plaintext, binding=binding, key=key, key_id=key_id)
    world.assignments.bind_artifact(
        case_id=case["case_id"], artifact_kind=KIND, artifact_revision=revision, envelope=envelope,
    )
    return key_id, envelope


def _open(client, token, grant_id, key_grant_id, version, revision=REVISION):
    return client.post(f"/api/cases/assignments/{grant_id}/content", headers=_csrf(token), json={
        "key_grant_id": key_grant_id,
        "artifact_kind": KIND,
        "artifact_revision": revision,
        "expected_version": version,
    })


def test_distinct_wallets_prove_scope_epoch_rotation_expiry_and_revocation(tmp_path):
    world = _world(tmp_path)
    owner_wrap = world.owner_session.ensure_recipient_wrap_key()
    lawyer_wrap = world.lawyer_session.ensure_recipient_wrap_key()
    other_wrap = world.other_session.ensure_recipient_wrap_key()
    assert len({world.owner.principal_id, world.lawyer.principal_id, world.other.principal_id}) == 3
    assert len({owner_wrap, lawyer_wrap, other_wrap}) == 3
    assert world.owner_session.path != world.lawyer_session.path
    assert world.lawyer_session.path != world.other_session.path
    assert "lawyer" in world.lawyer.roles
    assert "lawyer" not in world.owner.roles

    with TestClient(world.app, base_url="https://testserver") as owner_client, TestClient(world.app, base_url="https://testserver") as lawyer_client, TestClient(world.app, base_url="https://testserver") as other_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        other_token = _login(other_client, OTHER_LAWYER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "ux60"})
        assert created.status_code == 201, created.text
        case = created.json()
        _seal(world, case, NOTE, REVISION)

        role_only = lawyer_client.post("/api/cases/assignments", headers=_csrf(lawyer_token), json={
            "case_id": case["case_id"],
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read"],
            "role": "lawyer",
            "expires_at": world.now["t"] + 5000,
            "expected_case_revision": case["directory_revision"],
            "idempotency_key": "role-invite",
        })
        assert role_only.status_code == 403
        assert role_only.json()["error"] == "request_cannot_mint_authority"
        assert NOTE.decode() not in role_only.text

        invited = _invite(
            owner_client, owner_token, world, case, world.lawyer.principal_id,
            scope=["case.read"], expires_at=world.now["t"] + 5000, idempotency_key="invite-lawyer",
        )
        other_invited = _invite(
            owner_client, owner_token, world, case, world.other.principal_id,
            scope=["case.read"], expires_at=world.now["t"] + 5000, idempotency_key="invite-other",
        )
        assert invited["state"] == "pending"
        assert invited["scope"] == ["case.read"]
        assert invited["plaintext_available"] is False
        wrong_scope = lawyer_client.post(
            f"/api/cases/assignments/{invited['grant_id']}/accept", headers=_csrf(lawyer_token), json={
                "scope": ["case.read", "case.review"],
                "expected_version": invited["version"],
                "idempotency_key": "accept-wider",
            })
        assert wrong_scope.status_code == 403
        assert wrong_scope.json()["error"] == "scope_mismatch"
        pending_open = _open(lawyer_client, lawyer_token, invited["grant_id"], "0" * 32, invited["version"])
        assert pending_open.status_code == 403
        assert pending_open.json()["error"] == "membership_required"
        assert NOTE.decode() not in pending_open.text

        accepted = _accept(lawyer_client, lawyer_token, invited["grant_id"], ["case.read"], invited["version"], "accept-lawyer")
        other_accepted = _accept(other_client, other_token, other_invited["grant_id"], ["case.read"], other_invited["version"], "accept-other")
        assert accepted["state"] == "accepted"
        assert accepted["scope"] == ["case.read"]
        inspected = owner_client.get(f"/api/cases/assignments/{accepted['grant_id']}")
        assert inspected.status_code == 200, inspected.text
        assert inspected.json()["scope"] == ["case.read"]
        assert inspected.json()["expires_at"] == world.now["t"] + 5000
        assert inspected.json()["state"] == "accepted"

        outside = lawyer_client.post(f"/api/cases/assignments/{accepted['grant_id']}/use", headers=_csrf(lawyer_token), json={
            "surface": "api",
            "action": "case.review",
            "expected_version": accepted["version"],
        })
        assert outside.status_code == 403
        assert outside.json()["error"] == "action_not_permitted"
        inside = lawyer_client.post(f"/api/cases/assignments/{accepted['grant_id']}/use", headers=_csrf(lawyer_token), json={
            "surface": "api",
            "action": "case.read",
            "expected_version": accepted["version"],
        })
        assert inside.status_code == 200, inside.text
        assert inside.json()["admitted"] is True
        assert inside.json()["actor_is_encrypted_owner"] is False

        unlabeled = lawyer_client.post(f"/api/cases/assignments/{accepted['grant_id']}/content", headers=_csrf(lawyer_token), json={
            "key_grant_id": "0" * 32,
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "expected_version": accepted["version"],
            "role": "lawyer",
            "membership": "accepted",
        })
        assert unlabeled.status_code == 403
        assert unlabeled.json()["error"] == "request_cannot_mint_authority"

        issued = owner_client.post(f"/api/cases/assignments/{accepted['grant_id']}/key-grant", headers=_csrf(owner_token), json={
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "idempotency_key": "epoch-lawyer",
        })
        assert issued.status_code == 201, issued.text
        other_issued = owner_client.post(f"/api/cases/assignments/{other_accepted['grant_id']}/key-grant", headers=_csrf(owner_token), json={
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "idempotency_key": "epoch-other",
        })
        assert other_issued.status_code == 201, other_issued.text
        assert issued.json()["generation"] == 1
        assert other_issued.json()["generation"] == 1
        assert issued.json()["data_key_id"] == other_issued.json()["data_key_id"]
        assert issued.json()["recipient_wrap_key_id"] == lawyer_wrap
        assert other_issued.json()["recipient_wrap_key_id"] == other_wrap
        assert issued.json()["recipient_principal_id"] == world.lawyer.principal_id
        assert issued.json()["canonical_owner_principal_id"] == case["tenant_id"]
        assert issued.json()["actor_is_encrypted_owner"] is False
        epoch_key = issued.json()["data_key_id"]

        opened = _open(lawyer_client, lawyer_token, accepted["grant_id"], issued.json()["key_grant_id"], accepted["version"])
        assert opened.status_code == 200, opened.text
        assert opened.json()["text"] == NOTE.decode()
        assert opened.json()["actor_is_encrypted_owner"] is False
        assert opened.json()["canonical_owner_principal_id"] == case["tenant_id"]
        other_opened = _open(other_client, other_token, other_accepted["grant_id"], other_issued.json()["key_grant_id"], other_accepted["version"])
        assert other_opened.status_code == 200, other_opened.text
        assert other_opened.json()["text"] == NOTE.decode()
        crossed = _open(lawyer_client, lawyer_token, accepted["grant_id"], other_issued.json()["key_grant_id"], accepted["version"])
        assert crossed.status_code == 404
        assert crossed.json()["error"] == "missing_grant"
        assert NOTE.decode() not in crossed.text

        expiring = _invite(
            owner_client, owner_token, world, case, world.lawyer.principal_id,
            scope=["case.read"], expires_at=world.now["t"] + 40, idempotency_key="invite-expiring",
        )
        expiring_accepted = _accept(
            lawyer_client, lawyer_token, expiring["grant_id"], ["case.read"], expiring["version"], "accept-expiring",
        )
        expiring_key = owner_client.post(f"/api/cases/assignments/{expiring_accepted['grant_id']}/key-grant", headers=_csrf(owner_token), json={
            "artifact_kind": KIND,
            "artifact_revision": REVISION,
            "idempotency_key": "epoch-expiring",
        })
        assert expiring_key.status_code == 201, expiring_key.text
        world.now["t"] += 50
        expired_view = lawyer_client.get(f"/api/cases/assignments/{expiring_accepted['grant_id']}")
        assert expired_view.status_code == 200, expired_view.text
        assert expired_view.json()["state"] == "expired"
        expired_use = lawyer_client.post(
            f"/api/cases/assignments/{expiring_accepted['grant_id']}/use", headers=_csrf(lawyer_token), json={
                "surface": "api",
                "action": "case.read",
                "expected_version": expiring_accepted["version"],
            })
        assert expired_use.status_code == 403
        assert expired_use.json()["error"] == "grant_expired"
        expired = _open(
            lawyer_client, lawyer_token, expiring_accepted["grant_id"],
            expiring_key.json()["key_grant_id"], expiring_accepted["version"],
        )
        assert expired.status_code == 403
        assert expired.json()["error"] == "membership_required"
        assert NOTE.decode() not in expired.text
        still_current = _open(other_client, other_token, other_accepted["grant_id"], other_issued.json()["key_grant_id"], other_accepted["version"])
        assert still_current.status_code == 200, still_current.text

        revoked = owner_client.post(f"/api/cases/assignments/{accepted['grant_id']}/change", headers=_csrf(owner_token), json={
            "confirm_grant_change": True,
            "expected_version": accepted["version"],
            "revoke": True,
            "idempotency_key": "revoke-lawyer",
        })
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["state"] == "removed"
        effect = revoked.json()["change"]["effect_metadata"]
        assert effect["future_access_revoked"] is True
        assert effect["data_key_rotated"] is True
        assert effect["generation"] == 2
        assert effect["previous_data_key_id"] == epoch_key
        assert effect["data_key_id"] != epoch_key
        assert issued.json()["key_grant_id"] in effect["revoked_key_grant_ids"]
        assert other_issued.json()["key_grant_id"] in effect["rewrapped_key_grant_ids"]

        denied = _open(lawyer_client, lawyer_token, accepted["grant_id"], issued.json()["key_grant_id"], accepted["version"])
        assert denied.status_code == 403
        assert NOTE.decode() not in denied.text
        with pytest.raises(CaseResourceKeyGrantError) as late:
            world.key_grants.admit_late_result(
                actor_principal_id=world.other.principal_id,
                membership_grant_id=other_accepted["grant_id"],
                membership_version=other_accepted["version"],
                key_grant_id=other_issued.json()["key_grant_id"],
                case_id=case["case_id"],
                tenant_id=case["tenant_id"],
                resource_id=case["resource_id"],
                artifact_kind=KIND,
                artifact_revision=REVISION,
                prepared_generation=1,
                envelope=world.assignments._artifacts[(case["case_id"], KIND, REVISION)],
                recipient_session=world.other_session,
            )
        assert late.value.code == "late_result_after_cutoff"

        rotated_revision = "ux60-v2"
        new_key_id, _envelope = _seal(world, case, b"synthetic-ux60-rotated-note", rotated_revision)
        assert new_key_id == effect["data_key_id"]
        reissued = owner_client.post(f"/api/cases/assignments/{other_accepted['grant_id']}/key-grant", headers=_csrf(owner_token), json={
            "artifact_kind": KIND,
            "artifact_revision": rotated_revision,
            "idempotency_key": "epoch-other-rotated",
        })
        assert reissued.status_code == 201, reissued.text
        assert reissued.json()["generation"] == 2
        assert reissued.json()["data_key_id"] == effect["data_key_id"]
        rotated_open = _open(
            other_client, other_token, other_accepted["grant_id"], reissued.json()["key_grant_id"],
            other_accepted["version"], rotated_revision,
        )
        assert rotated_open.status_code == 200, rotated_open.text
        assert rotated_open.json()["text"] == "synthetic-ux60-rotated-note"
        stale_epoch = _open(
            other_client, other_token, other_accepted["grant_id"], other_issued.json()["key_grant_id"],
            other_accepted["version"], rotated_revision,
        )
        assert stale_epoch.status_code == 403
        assert "synthetic-ux60-rotated-note" not in stale_epoch.text


def test_role_and_membership_labels_do_not_open_owner_locked_review(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "ux60-review"})
        assert created.status_code == 201, created.text
        case_body = created.json()
    case = world.cases.select_case(actor_principal_id=world.owner.principal_id, case_id=case_body["case_id"])
    workspace = ComplaintWorkspaceService(root_dir=world.tmp_path / "review-workspace")
    reviews = CaseReviewService(
        world.tmp_path / "reviews", cases=world.cases, authorizer=world.authorizer,
        memberships=world.memberships, grants=world.key_grants,
        sessions={world.owner.principal_id: world.owner_session, world.lawyer.principal_id: world.lawyer_session},
    )
    reviews.bind_case(case, workspace)
    policy = world.authorizer.grant_assigned_lawyer(
        owner_principal_id=world.owner.principal_id,
        lawyer_principal_id=world.lawyer.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions={"case.read", "case.review"},
        expected_case_revision=case.revision,
    )
    assert policy.status == "accepted"
    decision = world.authorizer.authorize(
        boundary="review",
        actor_principal_id=world.lawyer.principal_id,
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        action="case.read",
        expected_revision=case.revision,
        expected_membership_revision=policy.revision,
    )
    assert decision.membership == "assigned-lawyer"
    world.lawyer_session.ensure_data_key(world.lawyer.principal_id, world.lawyer.principal_id)
    with pytest.raises(CaseReviewStoreError) as review_error:
        reviews.authorize_bound(decision)
    assert review_error.value.code in {"review_unavailable", "review_key_grant_required", "review_key_locked"}
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=workspace, workspace_service=workspace, authorize_delegated=reviews.authorize_bound)
    issued = world.browser.login({"credential": LAWYER_CREDENTIAL})
    with pytest.raises(WorkspaceCaseAuthorityError) as authority_error:
        issue_workspace_case_authority(
            authorizer=world.authorizer, sessions=world.browser, token=issued.token,
            decision=decision, registry=handlers,
        )
    assert str(authority_error.value) == "workspace_case_authority_unavailable"
    assert NOTE.decode() not in str(authority_error.value)
