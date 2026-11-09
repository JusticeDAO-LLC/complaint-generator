"""Case action authorization across HTTP, MCP, review, and download.

Positive cases allow an owner and an explicitly granted lawyer, and allow an
operational admin to read assignment metadata. Negative cases deny lawyer and
admin roles without membership, reject trusted_local, and reject mismatched
tenant, resource, and revision. The same decision is required on every boundary.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from applications.case_access import (
    ASSIGNED_LAWYER_ACTIONS,
    BOUNDARIES,
    OPERATIONAL_ADMIN_ACTIONS,
    OWNER_ACTIONS,
    CaseAccessError,
    CaseActionAuthorizer,
)
from applications.case_directory import CaseDirectory
from applications.complaint_workspace import WorkspaceAccess
from applications.principal_store import PrincipalStore

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def _world(tmp_path: Path):
    key = os.urandom(32)
    principals = PrincipalStore(tmp_path / "principals", key=key, key_id="principal-key")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    admin = principals.install_server_role(role="operational_admin")
    stranger = principals.register_from_request({})
    case = cases.create_case(actor_principal_id=owner.principal_id)
    other = cases.create_case(actor_principal_id=stranger.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    return authorizer, principals, owner, lawyer, admin, stranger, case, other


def _owner_body(owner, case, action: str = "case.read") -> dict:
    return {
        "actor_principal_id": owner.principal_id,
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "action": action,
        "expected_revision": case.revision,
    }


def test_owner_decision_matches_on_every_boundary_and_roles_do_not_grant_content(tmp_path: Path) -> None:
    authorizer, _principals, owner, lawyer, admin, _stranger, case, _other = _world(tmp_path)
    assert case.tenant_id != owner.principal_id
    assert OWNER_ACTIONS.isdisjoint(OPERATIONAL_ADMIN_ACTIONS)
    assert ASSIGNED_LAWYER_ACTIONS < OWNER_ACTIONS

    decisions = []
    for boundary in BOUNDARIES:
        decision = authorizer.authorize_request(boundary, _owner_body(owner, case, "case.download"))
        access = authorizer.authorize_access(
            WorkspaceAccess.authenticated(owner.principal_id, case.case_id),
            boundary=boundary,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action="case.download",
            expected_revision=case.revision,
        )
        assert decision == access
        assert decision.permits_case_content is True
        assert decision.membership == "owner"
        assert decision.actor_principal_id == owner.principal_id
        assert decision.canonical_owner_principal_id == case.tenant_id
        assert decision.actor_is_encrypted_owner is False
        assert decision.revision == case.revision
        decisions.append(decision)

    assert {item.boundary for item in decisions} == set(BOUNDARIES)
    assert len({item.without_boundary() for item in decisions}) == 1

    for actor in (lawyer, admin):
        for boundary in BOUNDARIES:
            with pytest.raises(CaseAccessError) as denied:
                authorizer.authorize(
                    boundary=boundary,
                    actor_principal_id=actor.principal_id,
                    tenant_id=case.tenant_id,
                    case_id=case.case_id,
                    resource_id=case.resource_id,
                    action="case.read",
                    expected_revision=case.revision,
                )
            assert denied.value.code == "role_does_not_grant_case_access"


def test_assigned_lawyer_needs_an_explicit_grant_on_every_boundary(tmp_path: Path) -> None:
    authorizer, principals, owner, lawyer, admin, stranger, case, other = _world(tmp_path)
    before = {item.principal_id: item.roles for item in principals.recover()}
    with pytest.raises(CaseAccessError) as not_owner:
        authorizer.grant_assigned_lawyer(
            owner_principal_id=admin.principal_id,
            lawyer_principal_id=lawyer.principal_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            tenant_id=case.tenant_id,
            actions=set(ASSIGNED_LAWYER_ACTIONS),
            expected_case_revision=case.revision,
        )
    assert not_owner.value.code == "missing_case"
    with pytest.raises(CaseAccessError) as not_lawyer:
        authorizer.grant_assigned_lawyer(
            owner_principal_id=owner.principal_id,
            lawyer_principal_id=stranger.principal_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            tenant_id=case.tenant_id,
            actions={"case.read"},
            expected_case_revision=case.revision,
        )
    assert not_lawyer.value.code == "lawyer_role_required"

    grant = authorizer.grant_assigned_lawyer(
        owner_principal_id=owner.principal_id,
        lawyer_principal_id=lawyer.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions={"case.read", "case.review"},
        expected_case_revision=case.revision,
    )
    assert grant.status == "accepted"
    assert grant.revision == 1
    allowed = []
    for boundary in BOUNDARIES:
        decision = authorizer.authorize(
            boundary=boundary,
            actor_principal_id=lawyer.principal_id,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action="case.review",
            expected_revision=case.revision,
            expected_membership_revision=grant.revision,
        )
        assert decision.membership == "assigned-lawyer"
        assert decision.permits_case_content is True
        assert decision.actor_principal_id != decision.canonical_owner_principal_id
        allowed.append(decision.without_boundary())
    assert len(set(allowed)) == 1

    for boundary in BOUNDARIES:
        with pytest.raises(CaseAccessError) as update_denied:
            authorizer.authorize(
                boundary=boundary,
                actor_principal_id=lawyer.principal_id,
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                resource_id=case.resource_id,
                action="case.update",
                expected_revision=case.revision,
                expected_membership_revision=grant.revision,
            )
        assert update_denied.value.code == "action_not_permitted"
        with pytest.raises(CaseAccessError) as other_case:
            authorizer.authorize(
                boundary=boundary,
                actor_principal_id=lawyer.principal_id,
                tenant_id=other.tenant_id,
                case_id=other.case_id,
                resource_id=other.resource_id,
                action="case.read",
                expected_revision=other.revision,
                expected_membership_revision=grant.revision,
            )
        assert other_case.value.code == "role_does_not_grant_case_access"
        with pytest.raises(CaseAccessError) as stale:
            authorizer.authorize(
                boundary=boundary,
                actor_principal_id=lawyer.principal_id,
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                resource_id=case.resource_id,
                action="case.read",
                expected_revision=case.revision,
                expected_membership_revision=grant.revision + 1,
            )
        assert stale.value.code == "revision_conflict"
    assert {item.principal_id: item.roles for item in principals.recover()} == before


def test_admin_metadata_is_not_case_content_and_trusted_local_is_rejected(tmp_path: Path) -> None:
    authorizer, principals, owner, lawyer, admin, _stranger, case, _other = _world(tmp_path)
    marker = "complaint-body-must-stay-out"
    decisions = []
    for boundary in BOUNDARIES:
        decision = authorizer.authorize_request(boundary, {
            "actor_principal_id": admin.principal_id,
            "owner_principal_id": owner.principal_id,
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "action": "assignment.metadata.read",
            "expected_revision": case.revision,
        })
        assert decision.membership == "operational-admin"
        assert decision.permits_case_content is False
        assert marker not in repr(decision)
        decisions.append(decision.without_boundary())
        with pytest.raises(CaseAccessError) as content:
            authorizer.authorize(
                boundary=boundary,
                actor_principal_id=admin.principal_id,
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                resource_id=case.resource_id,
                action="case.download",
                expected_revision=case.revision,
                owner_principal_id=owner.principal_id,
            )
        assert content.value.code == "role_does_not_grant_case_access"
    assert len(set(decisions)) == 1
    assert "case.download" not in OPERATIONAL_ADMIN_ACTIONS

    body = _owner_body(owner, case)
    body["trusted_local"] = True
    for boundary in BOUNDARIES:
        with pytest.raises(CaseAccessError) as local_body:
            authorizer.authorize_request(boundary, body)
        assert local_body.value.code == "trusted_local_not_production"
        with pytest.raises(CaseAccessError) as local_access:
            authorizer.authorize_access(
                WorkspaceAccess.trusted_local(owner.principal_id, case.case_id),
                boundary=boundary,
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                resource_id=case.resource_id,
                action="case.read",
                expected_revision=case.revision,
            )
        assert local_access.value.code == "trusted_local_not_production"
        minted = _owner_body(lawyer, case)
        minted["is_lawyer"] = True
        with pytest.raises(CaseAccessError) as minted_denied:
            authorizer.authorize_request(boundary, minted)
        assert minted_denied.value.code == "request_cannot_mint_authority"

    with pytest.raises(CaseAccessError) as tenant:
        authorizer.authorize_request("http", {**_owner_body(owner, case), "tenant_id": owner.tenant_id})
    assert tenant.value.code == "tenant_mismatch"
    with pytest.raises(CaseAccessError) as resource:
        authorizer.authorize_request("mcp", {**_owner_body(owner, case), "resource_id": "case-resource:other"})
    assert resource.value.code == "resource_mismatch"
    with pytest.raises(CaseAccessError) as revision:
        authorizer.authorize_request("review", {**_owner_body(owner, case), "expected_revision": case.revision + 1})
    assert revision.value.code == "revision_conflict"
    with pytest.raises(CaseAccessError) as download_revision:
        authorizer.authorize_request("download", {**_owner_body(owner, case), "expected_revision": False})
    assert download_revision.value.code == "revision_conflict"
    with pytest.raises(CaseAccessError) as unbound:
        authorizer.authorize_access(
            WorkspaceAccess.authenticated(owner.principal_id, "other-case"),
            boundary="http",
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action="case.read",
            expected_revision=case.revision,
        )
    assert unbound.value.code == "case_mismatch"
    assert [item.roles for item in principals.recover() if item.principal_id == admin.principal_id] == [("operational_admin",)]


def test_owner_cannot_take_admin_actions_and_unknown_boundary_fails(tmp_path: Path) -> None:
    authorizer, _principals, owner, _lawyer, _admin, stranger, case, other = _world(tmp_path)
    with pytest.raises(CaseAccessError) as admin_action:
        authorizer.authorize(
            boundary="http",
            actor_principal_id=owner.principal_id,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action="role.assign",
            expected_revision=case.revision,
            owner_principal_id=owner.principal_id,
        )
    assert admin_action.value.code == "action_not_permitted"
    with pytest.raises(CaseAccessError) as foreign:
        authorizer.authorize_request("download", _owner_body(stranger, case))
    assert foreign.value.code == "missing_case"
    assert other.case_id != case.case_id
    with pytest.raises(CaseAccessError) as channel:
        authorizer.authorize(
            boundary="websocket",
            actor_principal_id=owner.principal_id,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action="case.read",
            expected_revision=case.revision,
        )
    assert channel.value.code == "unknown_boundary"
    with pytest.raises(CaseAccessError) as anonymous:
        authorizer.authorize_access(
            WorkspaceAccess.unauthenticated(),
            boundary="mcp",
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action="case.read",
            expected_revision=case.revision,
        )
    assert anonymous.value.code == "unauthenticated"
