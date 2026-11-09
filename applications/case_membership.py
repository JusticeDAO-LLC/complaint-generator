"""Durable explicit case membership and scoped action grants.

Owner approval creates a pending membership. The recipient accepts or declines.
Only an accepted grant authorizes its explicit actions, and only until expiry.
Grant identifiers stay stable across version changes. A request body cannot
mint a grant, set a status, or supply actions.

The authenticated actor stays distinct from the canonical encrypted owner,
which is the case tenant. This store does not issue recipient key grants,
rewrite ``CaseActionAuthorizer`` process memory, or erase a download that
already completed. Revocation and removal deny later use.

Storage is one sealed envelope per grant. Routing hints are untrusted until
the injected key opens the envelope under the expected tenant, case, and
revision. Concurrent edits use an exclusive lock and an expected version.
"""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
import base64
from copy import deepcopy
import hashlib
import json
import os
import stat
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from applications.case_access import ASSIGNED_LAWYER_ACTIONS
from applications.case_directory import CaseDirectory, CaseDirectoryError
from applications.principal_store import PrincipalStore, PrincipalStoreError
from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)

TASK_ID = "CIMP-GUI-10"
SCHEMA_VERSION = 1
OWNER_OPERATION_LIMIT = 128
OWNER_OPERATION_SCAN_LIMIT = 4096
_RECORD_LIMIT = 16 * 1024 * 1024
_RECORD_SCHEMA = "case-membership-grant-record@2"
ARTIFACT_KIND = "case-membership-grant"
GRANT_ACTIONS = ASSIGNED_LAWYER_ACTIONS
STATUSES = frozenset({"pending", "accepted", "declined", "removed"})
CALLER_MINT_FIELDS = frozenset({
    "trusted_local",
    "trust",
    "role",
    "roles",
    "staff_role",
    "is_admin",
    "is_staff",
    "is_lawyer",
    "is_member",
    "membership",
    "grant",
    "grant_id",
    "actions",
    "status",
    "expires_at",
    "version",
    "accepted",
    "case_plaintext",
    "credentials",
    "credential",
    "narrative",
    "evidence",
})


class CaseMembershipError(Exception):
    """Fail-closed membership error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


@dataclass(frozen=True)
class _CanonicalAccess:
    trust: str
    principal_id: str
    case_id: str


@dataclass(frozen=True)
class OpenRequest:
    request_id: str
    actor_principal_id: str
    action: str
    grant_version: int


@dataclass(frozen=True)
class MembershipGrant:
    """Owner-approved membership. ``grant_id`` does not change when ``version`` does."""

    grant_id: str
    version: int
    status: str
    owner_principal_id: str
    member_principal_id: str
    tenant_id: str
    case_id: str
    resource_id: str
    actions: tuple[str, ...]
    expires_at: int
    case_revision: int
    invite_key: str
    decision_key: str | None
    open_requests: tuple[OpenRequest, ...]
    original_invite_fingerprint: str | None = None
    owner_changes: tuple[dict[str, Any], ...] = ()

    def public_view(self) -> dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "version": self.version,
            "status": self.status,
            "owner_principal_id": self.owner_principal_id,
            "member_principal_id": self.member_principal_id,
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "resource_id": self.resource_id,
            "actions": list(self.actions),
            "expires_at": self.expires_at,
            "case_revision": self.case_revision,
            "schema_version": SCHEMA_VERSION,
            "open_request_ids": [item.request_id for item in self.open_requests],
        }


@dataclass(frozen=True)
class MembershipDecision:
    """Allow result for one explicit action. Denials raise ``CaseMembershipError``."""

    grant_id: str
    version: int
    action: str
    actor_principal_id: str
    tenant_id: str
    case_id: str
    resource_id: str
    expires_at: int
    canonical_owner_principal_id: str
    actor_is_encrypted_owner: bool
    permits_case_content: bool


@dataclass(frozen=True)
class OpenCaseRequest:
    """In-flight use of an accepted grant. Removal invalidates ``finish``."""

    request_id: str
    grant_id: str
    grant_version: int
    actor_principal_id: str
    action: str
    tenant_id: str
    case_id: str


def _opaque_id() -> str:
    return uuid.uuid4().hex


def _label(value: str, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseMembershipError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseMembershipError(code)
    return value


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CaseMembershipStore:
    """File-backed membership grants for one injected data key."""

    def __init__(
        self,
        root: str | Path,
        *,
        key: bytes,
        key_id: str,
        principals: PrincipalStore,
        cases: CaseDirectory,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview):
            raise CaseMembershipError("key_material")
        if len(bytes(key)) != 32:
            raise CaseMembershipError("key_material")
        if not isinstance(principals, PrincipalStore) or not isinstance(cases, CaseDirectory):
            raise CaseMembershipError("authority_owners")
        self._key = bytes(key)
        self._key_id = _label(key_id, "key_id")
        self._principals = principals
        self._cases = cases
        self._clock = clock or (lambda: int(time.time()))
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        os.chmod(self._root, 0o700)
        self._lock_path = self._root / ".lock"
        self._lock_path.touch(mode=0o600)
        (self._root / "grants").mkdir(mode=0o700, exist_ok=True)
        (self._root / "idem").mkdir(mode=0o700, exist_ok=True)

    @contextmanager
    def owner_change_scope(self):
        """Serialize owner change workflows without holding the Member lock.

        External key rotation belongs inside this coordination scope, outside
        ``_locked``. The separate publication scope below is acquired only
        after a caller's KeyGrant lock, preserving Grant → Member → Keys.
        """
        path = self._root / "owner-change.lock"
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            info = os.fstat(fd)
            named = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                    or (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino)):
                raise CaseMembershipError("owner_change_lock")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def prepare_owner_change(self, *, owner_principal_id: str, grant_id: str,
                             expected_version: int, idempotency_key: str,
                             actions=None, expires_at=None, revoke=False,
                             revoke_cutoff=None, before_publish=None) -> dict[str, Any]:
        """Persist an exact owner-approved intent before external key effects.

        Cutoff is a server-derived value, retained for retries but excluded
        from the request fingerprint. This metadata cannot issue a key grant.
        """
        actor = self._active(owner_principal_id).principal_id
        identity = _label(grant_id, "grant_id")
        key = _label(idempotency_key, "idempotency_key")
        if type(expected_version) is not int or expected_version < 1:
            raise CaseMembershipError("revision_conflict")
        if type(revoke) is not bool or revoke and (actions is not None or expires_at is not None):
            raise CaseMembershipError("empty_update")
        if not revoke and actions is None and expires_at is None:
            raise CaseMembershipError("empty_update")
        scope = None if actions is None else self._actions(actions)
        if expires_at is not None and type(expires_at) is not int:
            raise CaseMembershipError("expiry")
        request = {"actor_principal_id":actor,"grant_id":identity,"expected_version":expected_version,
                   "revoke":revoke,"scope":None if scope is None else list(scope),"expires_at":expires_at}
        fingerprint = _fingerprint(request)
        key_hash = _fingerprint({"actor_principal_id":actor,"idempotency_key":key})
        with self._locked():
            current = self._load(identity)
            self._owner_case(current, actor)
            prior = self._find_owner_change(actor, key_hash)
            if prior is not None:
                stored_grant, operation = prior
                if (stored_grant.grant_id != identity or operation["request_fingerprint"] != fingerprint
                        or operation["idempotency_key"] != key):
                    raise CaseMembershipError("replay_mismatch")
                self._owner_before_publish(current,actor,before_publish)()
                return {"grant":current,"operation":deepcopy(operation),"replayed":True}
            self._no_pending_owner_change(current)
            if current.status not in {"pending","accepted"}:
                raise CaseMembershipError("membership_terminal")
            self._expect_version(current, expected_version)
            if expires_at is not None:
                self._expiry(expires_at)
            if revoke and (type(revoke_cutoff) is not int or revoke_cutoff < 1):
                raise CaseMembershipError("cutoff_invalid")
            if not revoke and revoke_cutoff is not None:
                raise CaseMembershipError("cutoff_invalid")
            if len(current.owner_changes) >= OWNER_OPERATION_LIMIT:
                raise CaseMembershipError("owner_change_history_full")
            operation = {"operation_id":_opaque_id(),"actor_principal_id":actor,"grant_id":identity,
                "tenant_id":current.tenant_id,"case_id":current.case_id,"resource_id":current.resource_id,
                "idempotency_key":key,"idempotency_key_sha256":key_hash,"request_fingerprint":fingerprint,
                "operation":"revocation" if revoke else "scope_and_expiry" if scope is not None and expires_at is not None
                    else "scope" if scope is not None else "expiry",
                "phase":"prepared","from_revision":current.version,"target_revision":current.version+1,
                "prior_scope":list(current.actions),"prior_expires_at":current.expires_at,
                "scope":list(current.actions if scope is None else scope),
                "expires_at":current.expires_at if expires_at is None else expires_at,
                "revoke":revoke,"revoke_cutoff":revoke_cutoff,"audit_id":_opaque_id(),"request":request}
            updated = _replace(current,owner_changes=current.owner_changes+(operation,))
            self._seal(updated,before_publish=self._owner_before_publish(current,actor,before_publish))
            return {"grant":updated,"operation":deepcopy(operation),"replayed":False}

    def finish_owner_change(self, *, owner_principal_id: str, grant_id: str, operation_id: str,
                            effect_metadata=None, before_publish=None) -> dict[str, Any]:
        """Apply only the stored intent and commit its audit in the same record."""
        actor = self._active(owner_principal_id).principal_id
        with self._locked():
            current = self._load(_label(grant_id,"grant_id"))
            self._owner_case(current,actor)
            operation = self._owner_operation(current,_label(operation_id,"operation_id"),actor)
            if operation["phase"] == "complete":
                self._owner_before_publish(current,actor,before_publish)()
                return {"grant":current,"operation":deepcopy(operation),"replayed":True}
            self._expect_version(current,operation["from_revision"])
            if current.status not in {"pending","accepted"}:
                raise CaseMembershipError("membership_terminal")
            effects = _owner_effect_metadata(effect_metadata)
            if "cutoff" in effects and effects["cutoff"] != operation["revoke_cutoff"]:
                raise CaseMembershipError("operation_effect_metadata")
            completed = {**operation,"phase":"complete","revision":operation["target_revision"],
                         "effect_metadata":effects}
            completed["audit"] = {"audit_id":operation["audit_id"],"grant_id":current.grant_id,
                "actor_principal_id":actor,"operation":operation["operation"],
                "from_revision":operation["from_revision"],"revision":operation["target_revision"],
                "prior_scope":operation["prior_scope"],"scope":operation["scope"],
                "prior_expires_at":operation["prior_expires_at"],"expires_at":operation["expires_at"],
                "revoked":operation["revoke"],"confirmed":True,"idempotency_key":operation["idempotency_key"],
                "effect_metadata":effects}
            changes = tuple(completed if item["operation_id"]==operation["operation_id"] else item
                            for item in current.owner_changes)
            updated = _replace(current,version=operation["target_revision"],actions=tuple(operation["scope"]),
                expires_at=operation["expires_at"],status="removed" if operation["revoke"] else current.status,
                owner_changes=changes)
            self._seal(updated,before_publish=self._owner_before_publish(current,actor,before_publish))
            return {"grant":updated,"operation":deepcopy(completed),"replayed":False}

    @contextmanager
    def owner_change_publication_scope(self, *, owner_principal_id: str, grant_id: str, operation_id: str):
        """Hold one exact pending owner intent after the caller's KeyGrant lock."""
        actor = self._active(owner_principal_id).principal_id
        with self._locked():
            current = self._load(_label(grant_id,"grant_id"))
            self._owner_case(current,actor)
            operation = self._owner_operation(current,_label(operation_id,"operation_id"),actor)
            if operation["phase"] != "prepared":
                raise CaseMembershipError("owner_change_not_pending")
            self._expect_version(current,operation["from_revision"])
            if current.status not in {"pending","accepted"}:
                raise CaseMembershipError("membership_terminal")
            yield current

    def _owner_case(self, grant, actor):
        self._active(actor)
        case = self._select(actor,grant.case_id)
        if (grant.owner_principal_id!=actor or case.owner_principal_id!=actor
                or case.tenant_id!=grant.tenant_id or case.resource_id!=grant.resource_id):
            raise CaseMembershipError("actor_not_owner")

    def _owner_before_publish(self, grant, actor, callback):
        if callback is not None and not callable(callback):
            raise CaseMembershipError("publication_callback")
        def reprove():
            self._owner_case(grant,actor)
            _publication_callback(callback)
        return reprove

    def _owner_operation(self, grant, identity, actor):
        matches = [item for item in grant.owner_changes if item["operation_id"]==identity]
        if len(matches)!=1 or matches[0]["actor_principal_id"]!=actor:
            raise CaseMembershipError("owner_change_missing")
        return matches[0]

    def _no_pending_owner_change(self, grant):
        if any(item["phase"]=="prepared" for item in grant.owner_changes):
            raise CaseMembershipError("owner_change_pending")

    def _find_owner_change(self, actor, key_hash):
        found = None
        paths = []
        with os.scandir(self._root/"grants") as entries:
            for entry in entries:
                if entry.name.endswith(".envelope"):
                    paths.append(entry.name)
                    if len(paths)>OWNER_OPERATION_SCAN_LIMIT:
                        raise CaseMembershipError("owner_change_registry_full")
        for name in sorted(paths):
            record = self._load(name[:-len(".envelope")])
            for operation in record.owner_changes:
                if operation["actor_principal_id"]==actor and operation["idempotency_key_sha256"]==key_hash:
                    if found is not None:
                        raise CaseMembershipError("owner_change_integrity")
                    found = record,operation
        return found

    def invite(
        self,
        *,
        owner_principal_id: str,
        member_principal_id: str,
        case_id: str,
        resource_id: str,
        tenant_id: str,
        actions: frozenset[str] | set[str],
        expires_at: int,
        expected_case_revision: int,
        idempotency_key: str,
        before_publish=None,
    ) -> MembershipGrant:
        """Owner creates one pending grant. The same key replays the same grant id."""

        owner = self._active(owner_principal_id)
        member = self._active(member_principal_id)
        if "lawyer" not in member.roles:
            raise CaseMembershipError("lawyer_role_required")
        if member.principal_id == owner.principal_id:
            raise CaseMembershipError("actor_not_owner")
        granted = self._actions(actions)
        if type(expires_at) is not int:
            raise CaseMembershipError("expiry")
        expiry = expires_at
        key = _label(idempotency_key, "idempotency_key")
        case = self._select(owner.principal_id, case_id)
        if case.owner_principal_id != owner.principal_id:
            raise CaseMembershipError("actor_not_owner")
        if tenant_id != case.tenant_id:
            raise CaseMembershipError("tenant_mismatch")
        if resource_id != case.resource_id:
            raise CaseMembershipError("resource_mismatch")
        if type(expected_case_revision) is not int or expected_case_revision != case.revision:
            raise CaseMembershipError("revision_conflict")
        fingerprint = _fingerprint({
            "owner_principal_id": owner.principal_id,
            "member_principal_id": member.principal_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "tenant_id": case.tenant_id,
            "actions": list(granted),
            "expires_at": expiry,
            "case_revision": case.revision,
        })
        with self._locked():
            existing_id = self._idem_grant(key)
            if existing_id is not None:
                existing = self._load(existing_id)
                if existing.invite_key != key or _invite_fingerprint(existing) != fingerprint:
                    raise CaseMembershipError("replay_mismatch")
                _publication_callback(before_publish)
                return existing
            self._expiry(expiry)
            record = MembershipGrant(
                grant_id=_opaque_id(),
                version=1,
                status="pending",
                owner_principal_id=owner.principal_id,
                member_principal_id=member.principal_id,
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                resource_id=case.resource_id,
                actions=granted,
                expires_at=expiry,
                case_revision=case.revision,
                invite_key=key,
                decision_key=None,
                open_requests=(),
                original_invite_fingerprint=fingerprint,
            )
            self._seal(record,before_publish=before_publish)
            self._write_idem(key, record.grant_id)
            return record

    def accept(
        self,
        *,
        member_principal_id: str,
        grant_id: str,
        expected_version: int,
        idempotency_key: str,
        before_publish=None,
    ) -> MembershipGrant:
        return self._decide(
            member_principal_id=member_principal_id,
            grant_id=grant_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            status="accepted",
            before_publish=before_publish,
        )

    def decline(
        self,
        *,
        member_principal_id: str,
        grant_id: str,
        expected_version: int,
        idempotency_key: str,
        before_publish=None,
    ) -> MembershipGrant:
        return self._decide(
            member_principal_id=member_principal_id,
            grant_id=grant_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            status="declined",
            before_publish=before_publish,
        )

    def update_scope(
        self,
        *,
        owner_principal_id: str,
        grant_id: str,
        expected_version: int,
        actions: frozenset[str] | set[str] | None = None,
        expires_at: int | None = None,
        before_publish=None,
    ) -> MembershipGrant:
        """Owner edits actions or expiry. The grant id stays the same."""

        owner = self._active(owner_principal_id)
        if actions is None and expires_at is None:
            raise CaseMembershipError("empty_update")
        granted = None if actions is None else self._actions(actions)
        expiry = None if expires_at is None else self._expiry(expires_at)
        with self._locked():
            current = self._load(_label(grant_id, "grant_id"))
            if current.owner_principal_id != owner.principal_id:
                raise CaseMembershipError("actor_not_owner")
            self._no_pending_owner_change(current)
            if current.status not in {"pending", "accepted"}:
                raise CaseMembershipError("membership_terminal")
            self._expect_version(current, expected_version)
            updated = _replace(
                current,
                version=current.version + 1,
                actions=current.actions if granted is None else granted,
                expires_at=current.expires_at if expiry is None else expiry,
            )
            self._seal(updated,before_publish=before_publish)
            return updated

    def remove(
        self,
        *,
        owner_principal_id: str,
        grant_id: str,
        expected_version: int,
        before_publish=None,
    ) -> MembershipGrant:
        """Owner withdraws a pending or accepted grant, including during an open request."""

        owner = self._active(owner_principal_id)
        with self._locked():
            current = self._load(_label(grant_id, "grant_id"))
            if current.owner_principal_id != owner.principal_id:
                raise CaseMembershipError("actor_not_owner")
            self._no_pending_owner_change(current)
            if current.status not in {"pending", "accepted"}:
                raise CaseMembershipError("membership_terminal")
            self._expect_version(current, expected_version)
            updated = _replace(current, version=current.version + 1, status="removed")
            self._seal(updated,before_publish=before_publish)
            return updated

    def authorize(
        self,
        *,
        actor_principal_id: str,
        grant_id: str,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        action: str,
        expected_version: int,
    ) -> MembershipDecision:
        """Authorize one explicit action. Pending, declined, removed, and expired grants fail."""

        actor = self._active(actor_principal_id)
        requested = self._one_action(action)
        with self._locked():
            grant = self._usable(
                actor_id=actor.principal_id,
                grant_id=grant_id,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=requested,
                expected_version=expected_version,
            )
            return MembershipDecision(
                grant_id=grant.grant_id,
                version=grant.version,
                action=requested,
                actor_principal_id=actor.principal_id,
                tenant_id=grant.tenant_id,
                case_id=grant.case_id,
                resource_id=grant.resource_id,
                expires_at=grant.expires_at,
                canonical_owner_principal_id=grant.tenant_id,
                actor_is_encrypted_owner=False,
                permits_case_content=True,
            )

    @contextmanager
    def authorization_scope(self, *, actor_principal_id: str, grant_id: str,
                            tenant_id: str, case_id: str, resource_id: str,
                            action: str, expected_version: int):
        """Hold current membership through a trusted synchronous admission.

        Crypto and external work belong before this scope. Removal and scope
        renewal share this lock, so they cannot finish between the final
        membership check and the consumer's admission point.
        """
        actor = self._active(actor_principal_id)
        requested = self._one_action(action)
        with self._locked():
            grant = self._usable(actor_id=actor.principal_id, grant_id=grant_id,
                tenant_id=tenant_id, case_id=case_id, resource_id=resource_id,
                action=requested, expected_version=expected_version)
            yield MembershipDecision(grant_id=grant.grant_id, version=grant.version,
                action=requested, actor_principal_id=actor.principal_id,
                tenant_id=grant.tenant_id, case_id=grant.case_id,
                resource_id=grant.resource_id, expires_at=grant.expires_at,
                canonical_owner_principal_id=grant.tenant_id,
                actor_is_encrypted_owner=False, permits_case_content=True)

    def begin_request(
        self,
        *,
        actor_principal_id: str,
        grant_id: str,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        action: str,
        expected_version: int,
        request_id: str,
    ) -> OpenCaseRequest:
        """Record an open use. A later removal makes ``finish_request`` fail."""

        actor = self._active(actor_principal_id)
        requested = self._one_action(action)
        identity = _label(request_id, "request_id")
        with self._locked():
            grant = self._usable(
                actor_id=actor.principal_id,
                grant_id=grant_id,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=requested,
                expected_version=expected_version,
            )
            for item in grant.open_requests:
                if item.request_id == identity:
                    if item.actor_principal_id != actor.principal_id or item.action != requested:
                        raise CaseMembershipError("replay_mismatch")
                    return _ticket(grant, item)
            opened = OpenRequest(
                request_id=identity,
                actor_principal_id=actor.principal_id,
                action=requested,
                grant_version=grant.version,
            )
            updated = _replace(grant, open_requests=grant.open_requests + (opened,))
            self._seal(updated)
            return _ticket(updated, opened)

    def finish_request(self, ticket: OpenCaseRequest) -> MembershipDecision:
        """Complete an open request. Removal or a version change after begin denies it."""

        if not isinstance(ticket, OpenCaseRequest):
            raise CaseMembershipError("request_ticket")
        with self._locked():
            grant = self._load(ticket.grant_id)
            self._no_pending_owner_change(grant)
            match = None
            for item in grant.open_requests:
                if item.request_id == ticket.request_id:
                    match = item
                    break
            if match is None or match.grant_version != ticket.grant_version:
                raise CaseMembershipError("replay_mismatch")
            if grant.status == "removed" or grant.version != ticket.grant_version:
                raise CaseMembershipError("membership_removed")
            if grant.status != "accepted":
                raise CaseMembershipError(f"membership_{grant.status}")
            if self._now() >= grant.expires_at:
                raise CaseMembershipError("grant_expired")
            if ticket.tenant_id != grant.tenant_id:
                raise CaseMembershipError("tenant_mismatch")
            if ticket.case_id != grant.case_id or ticket.actor_principal_id != match.actor_principal_id:
                raise CaseMembershipError("case_mismatch")
            remaining = tuple(item for item in grant.open_requests if item.request_id != ticket.request_id)
            updated = _replace(grant, open_requests=remaining)
            self._seal(updated)
            return MembershipDecision(
                grant_id=grant.grant_id,
                version=grant.version,
                action=match.action,
                actor_principal_id=match.actor_principal_id,
                tenant_id=grant.tenant_id,
                case_id=grant.case_id,
                resource_id=grant.resource_id,
                expires_at=grant.expires_at,
                canonical_owner_principal_id=grant.tenant_id,
                actor_is_encrypted_owner=False,
                permits_case_content=True,
            )

    def invite_from_request(self, body: Mapping[str, Any]) -> MembershipGrant:
        """Request mappings cannot mint grants. Flags and a well-formed body both fail."""

        if not isinstance(body, Mapping):
            raise CaseMembershipError("request_body")
        if any(name in body for name in CALLER_MINT_FIELDS):
            raise CaseMembershipError("request_cannot_mint_grant")
        if body.get("trusted_local") is True or body.get("trust") == "trusted_local":
            raise CaseMembershipError("request_cannot_mint_grant")
        raise CaseMembershipError("request_cannot_mint_grant")

    def load(self, grant_id: str) -> MembershipGrant:
        with self._locked():
            return self._load(_label(grant_id, "grant_id"))

    def recover(self) -> tuple[MembershipGrant, ...]:
        with self._locked():
            records: list[MembershipGrant] = []
            for path in sorted((self._root / "grants").glob("*.envelope")):
                if not path.is_file() or path.is_symlink():
                    raise CaseMembershipError("unexpected_path")
                records.append(self._load(path.name[: -len(".envelope")]))
            return tuple(records)

    def _decide(
        self,
        *,
        member_principal_id: str,
        grant_id: str,
        expected_version: int,
        idempotency_key: str,
        status: str,
        before_publish=None,
    ) -> MembershipGrant:
        member = self._active(member_principal_id)
        key = _label(idempotency_key, "idempotency_key")
        with self._locked():
            current = self._load(_label(grant_id, "grant_id"))
            if current.member_principal_id != member.principal_id:
                raise CaseMembershipError("actor_not_member")
            self._no_pending_owner_change(current)
            if current.decision_key == key and current.status == status:
                _publication_callback(before_publish)
                return current
            if current.decision_key is not None or current.status != "pending":
                if current.status == "removed":
                    raise CaseMembershipError("membership_removed")
                raise CaseMembershipError("membership_replay")
            self._expect_version(current, expected_version)
            if self._now() >= current.expires_at:
                raise CaseMembershipError("grant_expired")
            updated = _replace(
                current,
                version=current.version + 1,
                status=status,
                decision_key=key,
            )
            self._seal(updated,before_publish=before_publish)
            return updated

    def _usable(
        self,
        *,
        actor_id: str,
        grant_id: str,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        action: str,
        expected_version: int,
    ) -> MembershipGrant:
        grant = self._load(_label(grant_id, "grant_id"))
        if grant.member_principal_id != actor_id:
            raise CaseMembershipError("actor_not_member")
        if tenant_id != grant.tenant_id:
            raise CaseMembershipError("tenant_mismatch")
        if case_id != grant.case_id or resource_id != grant.resource_id:
            raise CaseMembershipError("case_mismatch")
        self._no_pending_owner_change(grant)
        if grant.status == "pending":
            raise CaseMembershipError("membership_pending")
        if grant.status == "declined":
            raise CaseMembershipError("membership_declined")
        if grant.status == "removed":
            raise CaseMembershipError("membership_removed")
        if grant.status != "accepted":
            raise CaseMembershipError("membership_required")
        self._expect_version(grant, expected_version)
        if action not in grant.actions:
            raise CaseMembershipError("action_not_permitted")
        if self._now() >= grant.expires_at:
            raise CaseMembershipError("grant_expired")
        case = self._select(grant.owner_principal_id, grant.case_id)
        if case.tenant_id != grant.tenant_id or case.resource_id != grant.resource_id:
            raise CaseMembershipError("membership_required")
        if case.revision != grant.case_revision:
            raise CaseMembershipError("revision_conflict")
        return grant

    def _select(self, actor_id: str, case_id: str):
        try:
            return self._cases.select_case(actor_principal_id=actor_id, case_id=case_id)
        except CaseDirectoryError as exc:
            raise CaseMembershipError(exc.code) from exc

    def _active(self, principal_id: str):
        try:
            record = self._principals.load(principal_id)
        except PrincipalStoreError as exc:
            raise CaseMembershipError("missing_principal") from exc
        if record.status != "active":
            raise CaseMembershipError("inactive_principal")
        return record

    def _actions(self, actions: frozenset[str] | set[str]) -> tuple[str, ...]:
        if not isinstance(actions, (set, frozenset)) or not actions:
            raise CaseMembershipError("action_not_permitted")
        if any(not isinstance(item, str) for item in actions) or not set(actions) <= GRANT_ACTIONS:
            raise CaseMembershipError("action_not_permitted")
        return tuple(sorted(actions))

    def _one_action(self, action: str) -> str:
        if not isinstance(action, str) or action not in GRANT_ACTIONS:
            raise CaseMembershipError("action_not_permitted")
        return action

    def _expiry(self, expires_at: int) -> int:
        if type(expires_at) is not int or expires_at <= self._now():
            raise CaseMembershipError("expiry")
        return expires_at

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int:
            raise CaseMembershipError("clock")
        return value

    def _expect_version(self, grant: MembershipGrant, expected_version: int) -> None:
        if type(expected_version) is not int or expected_version != grant.version:
            raise CaseMembershipError("revision_conflict")

    def _load(self, grant_id: str) -> MembershipGrant:
        path = self._grant_path(grant_id)
        if not path.is_file() or path.is_symlink():
            raise CaseMembershipError("missing_grant")
        raw = _read_owned_record(path,_RECORD_LIMIT)
        upgraded = raw.startswith(b"{")
        if upgraded:
            try:
                wrapper = json.loads(raw,object_pairs_hook=_unique_object)
                if (type(wrapper) is not dict or set(wrapper)!={"schema","tenant_id","case_id","version","envelope"}
                        or wrapper["schema"]!=_RECORD_SCHEMA or type(wrapper["version"]) is not int
                        or wrapper["version"]<1 or type(wrapper["envelope"]) is not str):
                    raise ValueError("record")
                revision = wrapper["version"]
                tenant_id = _label(wrapper["tenant_id"],"tenant_id")
                case_id = _label(wrapper["case_id"],"case_id")
                envelope = base64.b64decode(wrapper["envelope"],validate=True)
            except (ValueError,TypeError,KeyError) as exc:
                raise CaseMembershipError("integrity") from exc
        else:
            pointer = self._root / "grants" / f"{grant_id}.revision"
            tenant_path = self._root / "grants" / f"{grant_id}.tenant"
            case_path = self._root / "grants" / f"{grant_id}.case"
            if not pointer.is_file() or not tenant_path.is_file() or not case_path.is_file():
                raise CaseMembershipError("missing_revision")
            revision_text = pointer.read_text(encoding="utf-8").strip()
            if not revision_text.isdigit():
                raise CaseMembershipError("revision_pointer")
            revision = int(revision_text)
            tenant_id = tenant_path.read_text(encoding="utf-8").strip()
            case_id = case_path.read_text(encoding="utf-8").strip()
            envelope = raw
        binding = PrivateArtifactBinding(
            tenant_id=tenant_id,
            case_id=case_id,
            artifact_kind=ARTIFACT_KIND,
            revision=str(revision),
            principal_id=tenant_id,
        )
        access = _CanonicalAccess("authenticated", tenant_id, case_id)
        assert_access_matches_binding(access, binding)
        try:
            plaintext = open_private_artifact(
                envelope,
                binding=binding,
                key=self._key,
                expected_key_id=self._key_id,
            )
        except PrivateArtifactIntegrityError as exc:
            raise CaseMembershipError("integrity") from exc
        try:
            grant = _grant_from_document(json.loads(plaintext.decode("utf-8"),object_pairs_hook=_unique_object))
        except (ValueError,TypeError,KeyError) as exc:
            raise CaseMembershipError("integrity") from exc
        if grant.grant_id != grant_id or grant.tenant_id != tenant_id or grant.case_id != case_id:
            raise CaseMembershipError("binding_mismatch")
        if grant.version != revision:
            raise CaseMembershipError("revision_mismatch")
        if upgraded and not grant.owner_changes:
            raise CaseMembershipError("owner_change_integrity")
        return grant

    def _seal(self, grant: MembershipGrant, *, before_publish=None) -> None:
        if before_publish is not None and not callable(before_publish):
            raise CaseMembershipError("publication_callback")
        binding = PrivateArtifactBinding(
            tenant_id=grant.tenant_id,
            case_id=grant.case_id,
            artifact_kind=ARTIFACT_KIND,
            revision=str(grant.version),
            principal_id=grant.tenant_id,
        )
        access = _CanonicalAccess("authenticated", grant.tenant_id, grant.case_id)
        assert_access_matches_binding(access, binding)
        payload = json.dumps(_grant_document(grant), sort_keys=True, separators=(",", ":")).encode("utf-8")
        envelope = seal_private_artifact(payload, binding=binding, key=self._key, key_id=self._key_id)
        directory = self._root / "grants"
        path = directory / f"{grant.grant_id}.envelope"
        upgraded = bool(grant.owner_changes)
        if upgraded:
            envelope = json.dumps({"schema":_RECORD_SCHEMA,"tenant_id":grant.tenant_id,"case_id":grant.case_id,
                "version":grant.version,"envelope":base64.b64encode(envelope).decode("ascii")},
                sort_keys=True,separators=(",",":")).encode()
        if len(envelope)>_RECORD_LIMIT:
            raise CaseMembershipError("record_size_limit")
        fd,temporary = tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=directory)
        try:
            with os.fdopen(fd,"wb") as handle:
                handle.write(envelope);handle.flush();os.fsync(handle.fileno())
            _publication_callback(before_publish)
            os.replace(temporary,path)
            parent = os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        finally:
            Path(temporary).unlink(missing_ok=True)
        if not upgraded:
            # Unchanged legacy format. Upgraded records authenticate their
            # routing fields in the one authoritative envelope; old sidecars
            # are ignored and cannot roll back the completed operation.
            self._write_text(directory / f"{grant.grant_id}.revision", str(grant.version))
            self._write_text(directory / f"{grant.grant_id}.tenant", grant.tenant_id)
            self._write_text(directory / f"{grant.grant_id}.case", grant.case_id)

    def _idem_grant(self, key: str) -> str | None:
        path = self._idem_path(key)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8").strip() or None

    def _write_idem(self, key: str, grant_id: str) -> None:
        self._write_text(self._idem_path(key), grant_id)

    def _idem_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._root / "idem" / digest

    def _grant_path(self, grant_id: str) -> Path:
        return self._root / "grants" / f"{grant_id}.envelope"

    def _write_text(self, path: Path, text: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    def _locked(self):
        return _FileLock(self._lock_path)


class _FileLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: Any = None

    def __enter__(self) -> _FileLock:
        self._handle = self._path.open("a+")
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


def _replace(grant: MembershipGrant, **changes: Any) -> MembershipGrant:
    data = {
        "grant_id": grant.grant_id,
        "version": grant.version,
        "status": grant.status,
        "owner_principal_id": grant.owner_principal_id,
        "member_principal_id": grant.member_principal_id,
        "tenant_id": grant.tenant_id,
        "case_id": grant.case_id,
        "resource_id": grant.resource_id,
        "actions": grant.actions,
        "expires_at": grant.expires_at,
        "case_revision": grant.case_revision,
        "invite_key": grant.invite_key,
        "decision_key": grant.decision_key,
        "open_requests": grant.open_requests,
        "original_invite_fingerprint": grant.original_invite_fingerprint,
        "owner_changes": grant.owner_changes,
    }
    data.update(changes)
    return MembershipGrant(**data)


def _ticket(grant: MembershipGrant, item: OpenRequest) -> OpenCaseRequest:
    return OpenCaseRequest(
        request_id=item.request_id,
        grant_id=grant.grant_id,
        grant_version=item.grant_version,
        actor_principal_id=item.actor_principal_id,
        action=item.action,
        tenant_id=grant.tenant_id,
        case_id=grant.case_id,
    )


def _invite_fingerprint(grant: MembershipGrant) -> str:
    # Legacy records never authenticated the original invite payload. Current
    # actions/expiry may have changed, so they cannot establish replay identity.
    if grant.original_invite_fingerprint is None:
        raise CaseMembershipError("invite_replay_unverifiable")
    return grant.original_invite_fingerprint


def _grant_document(grant: MembershipGrant) -> dict[str, Any]:
    document = {
        "schema_version": SCHEMA_VERSION,
        "grant_id": grant.grant_id,
        "version": grant.version,
        "status": grant.status,
        "owner_principal_id": grant.owner_principal_id,
        "member_principal_id": grant.member_principal_id,
        "tenant_id": grant.tenant_id,
        "case_id": grant.case_id,
        "resource_id": grant.resource_id,
        "actions": list(grant.actions),
        "expires_at": grant.expires_at,
        "case_revision": grant.case_revision,
        "invite_key": grant.invite_key,
        "decision_key": grant.decision_key,
        "open_requests": [
            {
                "request_id": item.request_id,
                "actor_principal_id": item.actor_principal_id,
                "action": item.action,
                "grant_version": item.grant_version,
            }
            for item in grant.open_requests
        ],
    }
    if grant.original_invite_fingerprint is not None:
        document["original_invite_fingerprint"] = grant.original_invite_fingerprint
    if grant.owner_changes:
        document["owner_changes"] = deepcopy(list(grant.owner_changes))
    return document


def _grant_from_document(document: Mapping[str, Any]) -> MembershipGrant:
    if not isinstance(document,Mapping):
        raise CaseMembershipError("schema")
    if int(document.get("schema_version") or 0) != SCHEMA_VERSION:
        raise CaseMembershipError("schema")
    version = document.get("version")
    expires_at = document.get("expires_at")
    case_revision = document.get("case_revision")
    if type(version) is not int or version < 1:
        raise CaseMembershipError("revision")
    if type(expires_at) is not int or type(case_revision) is not int:
        raise CaseMembershipError("schema")
    status = str(document.get("status") or "")
    if status not in STATUSES:
        raise CaseMembershipError("schema")
    actions = tuple(str(item) for item in document.get("actions") or ())
    if not actions or any(item not in GRANT_ACTIONS for item in actions):
        raise CaseMembershipError("action_not_permitted")
    opens: list[OpenRequest] = []
    for item in document.get("open_requests") or ():
        if not isinstance(item, Mapping):
            raise CaseMembershipError("schema")
        opened_version = item.get("grant_version")
        if type(opened_version) is not int:
            raise CaseMembershipError("schema")
        opens.append(OpenRequest(
            request_id=_label(str(item.get("request_id") or ""), "request_id"),
            actor_principal_id=_label(str(item.get("actor_principal_id") or ""), "principal_id"),
            action=_label(str(item.get("action") or ""), "action"),
            grant_version=opened_version,
        ))
    decision = document.get("decision_key")
    original_fingerprint = document.get("original_invite_fingerprint")
    if original_fingerprint is not None and (
        not isinstance(original_fingerprint, str)
        or len(original_fingerprint) != 64
        or any(char not in "0123456789abcdef" for char in original_fingerprint)
    ):
        raise CaseMembershipError("invite_fingerprint")
    grant = MembershipGrant(
        grant_id=_label(str(document.get("grant_id") or ""), "grant_id"),
        version=version,
        status=status,
        owner_principal_id=_label(str(document.get("owner_principal_id") or ""), "principal_id"),
        member_principal_id=_label(str(document.get("member_principal_id") or ""), "principal_id"),
        tenant_id=_label(str(document.get("tenant_id") or ""), "tenant_id"),
        case_id=_label(str(document.get("case_id") or ""), "case_id"),
        resource_id=_label(str(document.get("resource_id") or ""), "resource_id"),
        actions=tuple(sorted(actions)),
        expires_at=expires_at,
        case_revision=case_revision,
        invite_key=_label(str(document.get("invite_key") or ""), "idempotency_key"),
        decision_key=None if decision is None else _label(str(decision), "idempotency_key"),
        open_requests=tuple(opens),
        original_invite_fingerprint=original_fingerprint,
    )
    return _replace(grant,owner_changes=_owner_changes_from_document(document.get("owner_changes",()),grant))


def _unique_object(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise ValueError("duplicate membership field")
        result[key] = value
    return result


def _publication_callback(callback):
    if callback is not None:
        if not callable(callback):
            raise CaseMembershipError("publication_callback")
        if callback() is False:
            raise CaseMembershipError("publication_denied")


def _read_owned_record(path,maximum):
    descriptor = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_nlink!=1
                or stat.S_IMODE(before.st_mode)!=0o600 or not 0<before.st_size<=maximum):
            raise CaseMembershipError("integrity")
        raw = bytearray()
        while len(raw)<before.st_size:
            part = os.read(descriptor,min(1024*1024,before.st_size-len(raw)))
            if not part:
                raise CaseMembershipError("integrity")
            raw.extend(part)
        fields = ('st_dev','st_ino','st_size','st_uid','st_mode','st_nlink','st_mtime_ns','st_ctime_ns')
        if any(getattr(before,key)!=getattr(other,key) for other in (os.fstat(descriptor),path.lstat()) for key in fields):
            raise CaseMembershipError("integrity")
        return bytes(raw)
    finally:
        os.close(descriptor)


def _owner_effect_metadata(value):
    if value is None:
        return {}
    if type(value) is not dict:
        raise CaseMembershipError("operation_effect_metadata")
    numbers = {"generation","cutoff"}
    labels = {"operation_id","data_key_id","previous_data_key_id"}
    lists = {"revoked_key_grant_ids","rewrapped_key_grant_ids"}
    flags = {"data_key_rotated","grant_wrap_rotated","future_access_revoked"}
    if set(value)-numbers-labels-lists-flags:
        raise CaseMembershipError("operation_effect_metadata")
    result = {}
    for key,item in value.items():
        if key in numbers:
            if type(item) is not int or item<1:
                raise CaseMembershipError("operation_effect_metadata")
            result[key] = item
        elif key in labels:
            result[key] = _label(item,"operation_effect_metadata")
            if len(item)>512:
                raise CaseMembershipError("operation_effect_metadata")
        elif key in lists:
            if type(item) not in (tuple,list) or len(item)>1024:
                raise CaseMembershipError("operation_effect_metadata")
            result[key] = [_label(member,"operation_effect_metadata") for member in item]
            if len(set(result[key]))!=len(result[key]) or any(len(member)>512 for member in result[key]):
                raise CaseMembershipError("operation_effect_metadata")
        else:
            if type(item) is not bool:
                raise CaseMembershipError("operation_effect_metadata")
            result[key] = item
    if len(json.dumps(result,separators=(",",":")).encode())>65536:
        raise CaseMembershipError("operation_effect_metadata")
    return result


def _owner_changes_from_document(value,grant):
    if type(value) not in (list,tuple) or len(value)>OWNER_OPERATION_LIMIT:
        raise CaseMembershipError("owner_change_integrity")
    required = {"operation_id","actor_principal_id","grant_id","tenant_id","case_id","resource_id",
        "idempotency_key","idempotency_key_sha256","request_fingerprint","operation","phase",
        "from_revision","target_revision","prior_scope","prior_expires_at","scope","expires_at",
        "revoke","revoke_cutoff","audit_id","request"}
    result = [];identities=set();keys=set();pending=0
    for item in value:
        if type(item) is not dict:
            raise CaseMembershipError("owner_change_integrity")
        phase = item.get('phase')
        extra = {'revision','effect_metadata','audit'} if phase=='complete' else set()
        if set(item)!=required|extra or phase not in {'prepared','complete'}:
            raise CaseMembershipError("owner_change_integrity")
        op = deepcopy(item)
        for field in ('operation_id','actor_principal_id','grant_id','tenant_id','case_id','resource_id','idempotency_key','audit_id'):
            _label(op[field],"owner_change_integrity")
        if (any(op[k]!=getattr(grant,k) for k in ('grant_id','tenant_id','case_id','resource_id'))
                or op['actor_principal_id']!=grant.owner_principal_id
                or type(op['from_revision']) is not int or op['from_revision']<1
                or type(op['target_revision']) is not int or op['target_revision']!=op['from_revision']+1
                or type(op['revoke']) is not bool
                or any(type(op[k]) is not int for k in ('prior_expires_at','expires_at'))):
            raise CaseMembershipError("owner_change_integrity")
        for field in ('prior_scope','scope'):
            actions = op[field]
            if (type(actions) is not list or not actions or any(type(action) is not str for action in actions)
                    or actions!=sorted(set(actions)) or not set(actions)<=GRANT_ACTIONS):
                raise CaseMembershipError("owner_change_integrity")
        request = op['request']
        if (type(request) is not dict or set(request)!={'actor_principal_id','grant_id','expected_version','revoke','scope','expires_at'}
                or request['actor_principal_id']!=op['actor_principal_id'] or request['grant_id']!=grant.grant_id
                or type(request['expected_version']) is not int or request['expected_version']!=op['from_revision']
                or type(request['revoke']) is not bool or request['revoke']!=op['revoke']
                or _fingerprint(request)!=op['request_fingerprint']
                or _fingerprint({'actor_principal_id':op['actor_principal_id'],'idempotency_key':op['idempotency_key']})!=op['idempotency_key_sha256']):
            raise CaseMembershipError("owner_change_integrity")
        scope = request['scope'];expiry = request['expires_at']
        if (scope is not None and (type(scope) is not list or scope!=op['scope'])
                or scope is None and op['scope']!=op['prior_scope']
                or expiry is not None and (type(expiry) is not int or expiry!=op['expires_at'])
                or expiry is None and op['expires_at']!=op['prior_expires_at']):
            raise CaseMembershipError("owner_change_integrity")
        expected_operation = ('revocation' if op['revoke'] else 'scope_and_expiry' if scope is not None and expiry is not None
            else 'scope' if scope is not None else 'expiry')
        if (op['operation']!=expected_operation or op['revoke'] and (scope is not None or expiry is not None
                    or type(op['revoke_cutoff']) is not int or op['revoke_cutoff']<1)
                or not op['revoke'] and (scope is None and expiry is None or op['revoke_cutoff'] is not None)):
            raise CaseMembershipError("owner_change_integrity")
        if op['operation_id'] in identities or op['idempotency_key_sha256'] in keys:
            raise CaseMembershipError("owner_change_integrity")
        identities.add(op['operation_id']);keys.add(op['idempotency_key_sha256'])
        if phase=='prepared':
            pending+=1
            if (op['from_revision']!=grant.version or tuple(op['prior_scope'])!=grant.actions
                    or op['prior_expires_at']!=grant.expires_at or grant.status not in {'pending','accepted'}):
                raise CaseMembershipError("owner_change_integrity")
        else:
            if type(op['revision']) is not int or op['revision']!=op['target_revision'] or op['revision']>grant.version:
                raise CaseMembershipError("owner_change_integrity")
            effects = _owner_effect_metadata(op['effect_metadata'])
            expected_audit = {"audit_id":op["audit_id"],"grant_id":grant.grant_id,
                "actor_principal_id":op['actor_principal_id'],"operation":op["operation"],
                "from_revision":op["from_revision"],"revision":op["target_revision"],
                "prior_scope":op["prior_scope"],"scope":op["scope"],"prior_expires_at":op["prior_expires_at"],
                "expires_at":op["expires_at"],"revoked":op["revoke"],"confirmed":True,
                "idempotency_key":op["idempotency_key"],"effect_metadata":effects}
            if _fingerprint(op['audit'])!=_fingerprint(expected_audit):
                raise CaseMembershipError("owner_change_integrity")
        result.append(op)
    if pending>1:
        raise CaseMembershipError("owner_change_integrity")
    return tuple(result)
