"""Server-side case action policy for HTTP, MCP, review, and download.

One decision checks the actor, the case tenant, the resource case, the
action, membership, and the expected revision. The same function serves every
boundary. A lawyer role or an operational-admin role does not grant case
content. ``trusted_local`` is rejected and is not a production workaround.

Owner content follows an owner-only case recorded by ``CaseDirectory``. An
assigned lawyer receives content only from an explicit accepted grant created
by the case owner through ``grant_assigned_lawyer``. That table is process
memory. Durable grant ids, expiry, and revocation belong to CIMP-GUI-10.
Operational admins may read assignment metadata and authorize role assignment.
Those decisions never permit case content and never return case plaintext.

The actor principal stays distinct from the canonical encrypted owner, which
is the case tenant on the directory record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from applications.case_directory import CaseDirectory, CaseDirectoryError, CaseNamespace
from applications.principal_store import PrincipalStore, PrincipalStoreError

TASK_ID = "CIMP-GUI-09"
BOUNDARIES = ("http", "mcp", "review", "download")

OWNER_ACTIONS = frozenset({
    "case.read",
    "case.update",
    "case.select",
    "case.review",
    "case.download",
    "case.message.send",
    "case.membership.invite",
    "case.processing.choose",
})
ASSIGNED_LAWYER_ACTIONS = frozenset({
    "case.read",
    "case.review",
    "case.download",
    "case.message.send",
})
OPERATIONAL_ADMIN_ACTIONS = frozenset({
    "account.metadata.read",
    "assignment.metadata.read",
    "role.assign",
})
CONTENT_ACTIONS = frozenset(OWNER_ACTIONS | ASSIGNED_LAWYER_ACTIONS)
KNOWN_ACTIONS = frozenset(CONTENT_ACTIONS | OPERATIONAL_ADMIN_ACTIONS)

PRIVILEGE_BODY_FIELDS = frozenset({
    "trusted_local",
    "trust",
    "role",
    "roles",
    "staff_role",
    "is_admin",
    "is_staff",
    "is_lawyer",
    "membership",
    "grant",
    "actions",
    "case_plaintext",
    "credentials",
    "credential",
    "narrative",
    "evidence",
})


class CaseAccessError(Exception):
    """Fail-closed authorization error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


@dataclass(frozen=True)
class AssignedMembership:
    """Explicit accepted case grant. Roles do not create this record."""

    lawyer_principal_id: str
    owner_principal_id: str
    tenant_id: str
    case_id: str
    resource_id: str
    actions: tuple[str, ...]
    case_revision: int
    revision: int
    status: str


@dataclass(frozen=True)
class AuthorizationDecision:
    """Allow result. Denials raise ``CaseAccessError`` and do not return content."""

    boundary: str
    actor_principal_id: str
    tenant_id: str
    case_id: str
    resource_id: str
    action: str
    membership: str
    revision: int
    membership_revision: int
    actor_is_encrypted_owner: bool
    canonical_owner_principal_id: str
    permits_case_content: bool

    def without_boundary(self) -> tuple[Any, ...]:
        return (
            self.actor_principal_id,
            self.tenant_id,
            self.case_id,
            self.resource_id,
            self.action,
            self.membership,
            self.revision,
            self.membership_revision,
            self.actor_is_encrypted_owner,
            self.canonical_owner_principal_id,
            self.permits_case_content,
        )


class CaseActionAuthorizer:
    """Authorize one case action the same way on every production boundary."""

    def __init__(self, principals: PrincipalStore, cases: CaseDirectory) -> None:
        if not isinstance(principals, PrincipalStore) or not isinstance(cases, CaseDirectory):
            raise CaseAccessError("authority_owners")
        self._principals = principals
        self._cases = cases
        self._grants: dict[tuple[str, str], AssignedMembership] = {}

    def grant_assigned_lawyer(
        self,
        *,
        owner_principal_id: str,
        lawyer_principal_id: str,
        case_id: str,
        resource_id: str,
        tenant_id: str,
        actions: frozenset[str] | set[str],
        expected_case_revision: int,
    ) -> AssignedMembership:
        """Owner-installed accepted grant. Request mappings cannot call this."""

        owner = self._active_principal(owner_principal_id)
        lawyer = self._active_principal(lawyer_principal_id)
        if "lawyer" not in lawyer.roles:
            raise CaseAccessError("lawyer_role_required")
        if lawyer.principal_id == owner.principal_id:
            raise CaseAccessError("actor_not_owner")
        case = self._select(owner.principal_id, case_id)
        if case.owner_principal_id != owner.principal_id:
            raise CaseAccessError("actor_not_owner")
        self._expect_case(case, tenant_id=tenant_id, resource_id=resource_id, expected_revision=expected_case_revision)
        granted = self._action_set(actions, allowed=ASSIGNED_LAWYER_ACTIONS, code="action_not_permitted")
        key = (lawyer.principal_id, case.case_id)
        existing = self._grants.get(key)
        if existing is not None:
            if existing.actions == granted and existing.case_revision == case.revision:
                return existing
            raise CaseAccessError("membership_exists")
        record = AssignedMembership(
            lawyer_principal_id=lawyer.principal_id,
            owner_principal_id=owner.principal_id,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            actions=granted,
            case_revision=case.revision,
            revision=1,
            status="accepted",
        )
        self._grants[key] = record
        return record

    def authorize(
        self,
        *,
        boundary: str,
        actor_principal_id: str | None,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        action: str,
        expected_revision: int,
        expected_membership_revision: int | None = None,
        owner_principal_id: str | None = None,
        trust: str = "authenticated",
    ) -> AuthorizationDecision:
        """Decide one action. ``trust='trusted_local'`` always fails closed."""

        channel = self._boundary(boundary)
        if trust == "trusted_local":
            raise CaseAccessError("trusted_local_not_production")
        if trust != "authenticated":
            raise CaseAccessError("unauthenticated")
        if not isinstance(actor_principal_id, str) or actor_principal_id.strip() == "":
            raise CaseAccessError("unauthenticated")
        requested = self._one_action(action)
        if type(expected_revision) is not int:
            raise CaseAccessError("revision_conflict")
        actor = self._active_principal(actor_principal_id)
        if requested in OPERATIONAL_ADMIN_ACTIONS:
            return self._authorize_admin(
                channel,
                actor_id=actor.principal_id,
                roles=actor.roles,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=requested,
                expected_revision=expected_revision,
                owner_principal_id=owner_principal_id,
            )
        if requested in ASSIGNED_LAWYER_ACTIONS or requested in OWNER_ACTIONS:
            return self._authorize_content(
                channel,
                actor_id=actor.principal_id,
                roles=actor.roles,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=requested,
                expected_revision=expected_revision,
                expected_membership_revision=expected_membership_revision,
            )
        raise CaseAccessError("unknown_action")

    def authorize_request(self, boundary: str, body: Mapping[str, Any]) -> AuthorizationDecision:
        """HTTP/MCP/review/download body. Privilege fields and trusted_local fail closed."""

        self._boundary(boundary)
        if not isinstance(body, Mapping):
            raise CaseAccessError("request_body")
        if body.get("trusted_local") is True or body.get("trust") == "trusted_local" or "trusted_local" in body:
            raise CaseAccessError("trusted_local_not_production")
        if any(name in body for name in PRIVILEGE_BODY_FIELDS):
            raise CaseAccessError("request_cannot_mint_authority")
        membership_revision = body.get("expected_membership_revision")
        if membership_revision is not None and type(membership_revision) is not int:
            raise CaseAccessError("revision_conflict")
        return self.authorize(
            boundary=boundary,
            actor_principal_id=body.get("actor_principal_id") if isinstance(body.get("actor_principal_id"), str) else None,
            tenant_id=str(body.get("tenant_id") or ""),
            case_id=str(body.get("case_id") or ""),
            resource_id=str(body.get("resource_id") or ""),
            action=str(body.get("action") or ""),
            expected_revision=body.get("expected_revision") if type(body.get("expected_revision")) is int else -1,
            expected_membership_revision=membership_revision if type(membership_revision) is int else None,
            owner_principal_id=body.get("owner_principal_id") if isinstance(body.get("owner_principal_id"), str) else None,
            trust="authenticated",
        )

    def authorize_access(
        self,
        access: Any,
        *,
        boundary: str,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        action: str,
        expected_revision: int,
        expected_membership_revision: int | None = None,
        owner_principal_id: str | None = None,
    ) -> AuthorizationDecision:
        """Workspace access object. ``trusted_local`` is never admitted."""

        trust = getattr(access, "trust", None)
        if trust == "trusted_local":
            raise CaseAccessError("trusted_local_not_production")
        bound_case = getattr(access, "case_id", None)
        if bound_case is not None and bound_case != case_id:
            raise CaseAccessError("case_mismatch")
        return self.authorize(
            boundary=boundary,
            actor_principal_id=getattr(access, "principal_id", None),
            tenant_id=tenant_id,
            case_id=case_id,
            resource_id=resource_id,
            action=action,
            expected_revision=expected_revision,
            expected_membership_revision=expected_membership_revision,
            owner_principal_id=owner_principal_id,
            trust=str(trust or ""),
        )

    def _authorize_content(
        self,
        boundary: str,
        *,
        actor_id: str,
        roles: tuple[str, ...],
        tenant_id: str,
        case_id: str,
        resource_id: str,
        action: str,
        expected_revision: int,
        expected_membership_revision: int | None,
    ) -> AuthorizationDecision:
        owned = self._owned_case(actor_id, case_id)
        if owned is not None and owned.owner_principal_id == actor_id:
            if action not in OWNER_ACTIONS:
                raise CaseAccessError("action_not_permitted")
            self._expect_case(owned, tenant_id=tenant_id, resource_id=resource_id, expected_revision=expected_revision)
            return self._decision(
                boundary,
                actor_id=actor_id,
                case=owned,
                action=action,
                membership="owner",
                membership_revision=0,
                permits_case_content=True,
            )
        grant = self._grants.get((actor_id, case_id))
        if grant is None or grant.status != "accepted":
            if "lawyer" in roles or "operational_admin" in roles:
                raise CaseAccessError("role_does_not_grant_case_access")
            raise CaseAccessError("missing_case")
        if action not in grant.actions:
            raise CaseAccessError("action_not_permitted")
        if type(expected_membership_revision) is not int or expected_membership_revision != grant.revision:
            raise CaseAccessError("revision_conflict")
        case = self._select(grant.owner_principal_id, grant.case_id)
        if case.tenant_id != grant.tenant_id or case.resource_id != grant.resource_id:
            raise CaseAccessError("membership_required")
        if case.revision != grant.case_revision:
            raise CaseAccessError("revision_conflict")
        self._expect_case(case, tenant_id=tenant_id, resource_id=resource_id, expected_revision=expected_revision)
        return self._decision(
            boundary,
            actor_id=actor_id,
            case=case,
            action=action,
            membership="assigned-lawyer",
            membership_revision=grant.revision,
            permits_case_content=True,
        )

    def _authorize_admin(
        self,
        boundary: str,
        *,
        actor_id: str,
        roles: tuple[str, ...],
        tenant_id: str,
        case_id: str,
        resource_id: str,
        action: str,
        expected_revision: int,
        owner_principal_id: str | None,
    ) -> AuthorizationDecision:
        if "operational_admin" not in roles:
            raise CaseAccessError("action_not_permitted")
        if not isinstance(owner_principal_id, str) or owner_principal_id.strip() == "":
            raise CaseAccessError("missing_case")
        case = self._select(owner_principal_id, case_id)
        self._expect_case(case, tenant_id=tenant_id, resource_id=resource_id, expected_revision=expected_revision)
        return self._decision(
            boundary,
            actor_id=actor_id,
            case=case,
            action=action,
            membership="operational-admin",
            membership_revision=0,
            permits_case_content=False,
        )

    def _decision(
        self,
        boundary: str,
        *,
        actor_id: str,
        case: CaseNamespace,
        action: str,
        membership: str,
        membership_revision: int,
        permits_case_content: bool,
    ) -> AuthorizationDecision:
        return AuthorizationDecision(
            boundary=boundary,
            actor_principal_id=actor_id,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action=action,
            membership=membership,
            revision=case.revision,
            membership_revision=membership_revision,
            actor_is_encrypted_owner=case.owner_principal_id == case.tenant_id,
            canonical_owner_principal_id=case.tenant_id,
            permits_case_content=permits_case_content,
        )

    def _expect_case(
        self,
        case: CaseNamespace,
        *,
        tenant_id: str,
        resource_id: str,
        expected_revision: int,
    ) -> None:
        if tenant_id != case.tenant_id:
            raise CaseAccessError("tenant_mismatch")
        if resource_id != case.resource_id:
            raise CaseAccessError("resource_mismatch")
        if expected_revision != case.revision:
            raise CaseAccessError("revision_conflict")

    def _owned_case(self, actor_id: str, case_id: str) -> CaseNamespace | None:
        try:
            return self._cases.select_case(actor_principal_id=actor_id, case_id=case_id)
        except CaseDirectoryError as exc:
            if exc.code == "missing_case":
                return None
            raise CaseAccessError(exc.code) from exc

    def _select(self, actor_id: str, case_id: str) -> CaseNamespace:
        found = self._owned_case(actor_id, case_id)
        if found is None:
            raise CaseAccessError("missing_case")
        return found

    def _active_principal(self, principal_id: str):
        try:
            record = self._principals.load(principal_id)
        except PrincipalStoreError as exc:
            raise CaseAccessError("missing_principal") from exc
        if record.status != "active":
            raise CaseAccessError("inactive_principal")
        return record

    def _boundary(self, boundary: str) -> str:
        if boundary not in BOUNDARIES:
            raise CaseAccessError("unknown_boundary")
        return boundary

    def _one_action(self, action: str) -> str:
        if not isinstance(action, str) or action not in KNOWN_ACTIONS:
            raise CaseAccessError("unknown_action")
        return action

    def _action_set(self, actions: frozenset[str] | set[str], *, allowed: frozenset[str], code: str) -> tuple[str, ...]:
        if not isinstance(actions, (set, frozenset)) or not actions:
            raise CaseAccessError(code)
        if any(not isinstance(item, str) for item in actions) or not set(actions) <= allowed:
            raise CaseAccessError(code)
        return tuple(sorted(actions))
