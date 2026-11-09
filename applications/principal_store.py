"""Durable principal and tenant roster bound to the private-storage key boundary.

Identifiers are opaque and server-generated. Role changes are server-owned:
a request mapping cannot create a staff role. Record bytes are AES-GCM
envelopes from ``integrations.private_storage``. The data key is injected by
the caller and is never written. Operational admin metadata is a projection
that omits case plaintext and credential material.

Actual actors are checked separately from the canonical encrypted owner, which
is the tenant identifier on the artifact binding. This module does not issue
sessions, mount HTTP, or open case artifacts. Rollback of a whole prior
envelope pair is not covered by the case-revision WAL; integrity here is
authentication under the caller-expected binding and key.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)

SCHEMA_VERSION = 1
TASK_ID = "CIMP-GUI-04"
DIRECTORY_CASE_ID = "principal-roster"
ARTIFACT_KIND = "principal-record"
CANONICAL_ROLE = "complainant"
STAFF_ROLES = frozenset({"lawyer", "operational_admin"})
KNOWN_ROLES = frozenset({CANONICAL_ROLE, *STAFF_ROLES})
REQUEST_ROLE_FIELDS = (
    "role",
    "roles",
    "staff_role",
    "is_admin",
    "is_staff",
    "is_lawyer",
)
EXCLUDED_REQUEST_FIELDS = frozenset({
    "case_plaintext",
    "credentials",
    "credential",
    "narrative",
    "evidence",
    "message",
    "summary",
    *REQUEST_ROLE_FIELDS,
})


class PrincipalStoreError(Exception):
    """Fail-closed roster error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


@dataclass(frozen=True)
class _CanonicalAccess:
    """Access object consumed by ``assert_access_matches_binding``."""

    trust: str
    principal_id: str
    case_id: str


@dataclass(frozen=True)
class PrincipalRecord:
    principal_id: str
    tenant_id: str
    roles: tuple[str, ...]
    status: str
    revision: int
    role_authority: str
    excluded_fields: tuple[str, ...]

    def operational_metadata(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "roles": list(self.roles),
            "status": self.status,
            "revision": self.revision,
            "role_authority": self.role_authority,
            "excluded_fields": list(self.excluded_fields),
        }


def _opaque_id() -> str:
    return uuid.uuid4().hex


def _label(value: str, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise PrincipalStoreError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise PrincipalStoreError(code)
    return value


class PrincipalStore:
    """File-backed roster of sealed principal records for one injected data key."""

    def __init__(self, root: str | Path, *, key: bytes, key_id: str) -> None:
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview):
            raise PrincipalStoreError("key_material")
        self._key = bytes(key)
        self._key_id = _label(key_id, "key_id")
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        os.chmod(self._root, 0o700)

    def register_from_request(self, body: Mapping[str, Any]) -> PrincipalRecord:
        """Create a complainant. Staff roles in the body are rejected and not stored."""

        if not isinstance(body, Mapping):
            raise PrincipalStoreError("request_body")
        requested = _roles_from_request(body)
        if requested & STAFF_ROLES or _staff_flag(body):
            raise PrincipalStoreError("request_body_cannot_assign_staff_role")
        if requested - {CANONICAL_ROLE}:
            raise PrincipalStoreError("unknown_role")
        excluded = tuple(sorted(name for name in body if name in EXCLUDED_REQUEST_FIELDS))
        return self._write_new(roles=(CANONICAL_ROLE,), excluded_fields=excluded)

    def install_server_role(self, *, role: str) -> PrincipalRecord:
        """Server-owned assignment. This entry point does not accept a request body."""

        assigned = _label(role, "role")
        if assigned not in KNOWN_ROLES:
            raise PrincipalStoreError("unknown_role")
        return self._write_new(roles=(assigned,), excluded_fields=())

    def assign_role(
        self,
        *,
        actor_principal_id: str,
        subject_principal_id: str,
        role: str,
        expected_revision: int,
    ) -> PrincipalRecord:
        """Replace the subject's roles when the actor already holds operational_admin."""

        actor = self.load(actor_principal_id)
        if "operational_admin" not in actor.roles or actor.status != "active":
            raise PrincipalStoreError("actor_lacks_role_authority")
        assigned = _label(role, "role")
        if assigned not in KNOWN_ROLES:
            raise PrincipalStoreError("unknown_role")
        subject = self.load(subject_principal_id)
        if type(expected_revision) is not int or expected_revision != subject.revision:
            raise PrincipalStoreError("revision_conflict")
        if actor.principal_id == subject.principal_id and assigned != "operational_admin":
            raise PrincipalStoreError("actor_cannot_drop_own_staff_role")
        updated = PrincipalRecord(
            principal_id=subject.principal_id,
            tenant_id=subject.tenant_id,
            roles=(assigned,),
            status=subject.status,
            revision=subject.revision + 1,
            role_authority="server",
            excluded_fields=subject.excluded_fields,
        )
        self._seal(updated)
        return updated

    def load(self, principal_id: str) -> PrincipalRecord:
        identity = _label(principal_id, "principal_id")
        path = self._path(identity)
        if not path.is_file():
            raise PrincipalStoreError("missing_principal")
        return self._open_envelope(path.read_bytes(), expected_principal_id=identity)

    def recover(self) -> tuple[PrincipalRecord, ...]:
        """Re-open every sealed record with the injected key. Tamper fails closed."""

        records: list[PrincipalRecord] = []
        for path in sorted(self._root.glob("*.envelope")):
            if not path.is_file() or path.is_symlink():
                raise PrincipalStoreError("unexpected_path")
            records.append(self._open_envelope(path.read_bytes(), expected_principal_id=path.name[: -len(".envelope")]))
        return tuple(records)

    def operational_metadata(self, principal_id: str) -> dict[str, Any]:
        return self.load(principal_id).operational_metadata()

    def _write_new(self, *, roles: tuple[str, ...], excluded_fields: tuple[str, ...]) -> PrincipalRecord:
        record = PrincipalRecord(
            principal_id=_opaque_id(),
            tenant_id=_opaque_id(),
            roles=roles,
            status="active",
            revision=1,
            role_authority="server",
            excluded_fields=excluded_fields,
        )
        if record.principal_id == record.tenant_id:
            raise PrincipalStoreError("identifier_collision")
        self._seal(record)
        return record

    def _seal(self, record: PrincipalRecord) -> None:
        binding = self._binding(record)
        access = _CanonicalAccess("authenticated", record.tenant_id, DIRECTORY_CASE_ID)
        assert_access_matches_binding(access, binding)
        payload = json.dumps(_record_document(record), sort_keys=True, separators=(",", ":")).encode("utf-8")
        envelope = seal_private_artifact(payload, binding=binding, key=self._key, key_id=self._key_id)
        self._replace(record, envelope)

    def _open_envelope(self, envelope: bytes, *, expected_principal_id: str) -> PrincipalRecord:
        # Revision is inside the plaintext. Try a bounded window of revisions by
        # reading a sibling pointer written only after a successful seal.
        pointer = self._pointer(expected_principal_id)
        if not pointer.is_file():
            raise PrincipalStoreError("missing_revision")
        revision_text = pointer.read_text(encoding="utf-8").strip()
        if not revision_text.isdigit():
            raise PrincipalStoreError("revision_pointer")
        revision = int(revision_text)
        tenant_hint = self._tenant_hint(expected_principal_id)
        if tenant_hint is None:
            raise PrincipalStoreError("missing_tenant_hint")
        binding = PrivateArtifactBinding(
            tenant_id=tenant_hint,
            case_id=DIRECTORY_CASE_ID,
            artifact_kind=ARTIFACT_KIND,
            revision=str(revision),
            principal_id=tenant_hint,
        )
        access = _CanonicalAccess("authenticated", tenant_hint, DIRECTORY_CASE_ID)
        assert_access_matches_binding(access, binding)
        try:
            plaintext = open_private_artifact(
                envelope,
                binding=binding,
                key=self._key,
                expected_key_id=self._key_id,
            )
        except PrivateArtifactIntegrityError as exc:
            raise PrincipalStoreError("integrity") from exc
        record = _record_from_document(json.loads(plaintext.decode("utf-8")))
        if record.principal_id != expected_principal_id or record.tenant_id != tenant_hint:
            raise PrincipalStoreError("binding_mismatch")
        if record.revision != revision:
            raise PrincipalStoreError("revision_mismatch")
        return record

    def _binding(self, record: PrincipalRecord) -> PrivateArtifactBinding:
        return PrivateArtifactBinding(
            tenant_id=record.tenant_id,
            case_id=DIRECTORY_CASE_ID,
            artifact_kind=ARTIFACT_KIND,
            revision=str(record.revision),
            principal_id=record.tenant_id,
        )

    def _replace(self, record: PrincipalRecord, envelope: bytes) -> None:
        """Persist ciphertext, then the unauthenticated routing hints.

        Hints are not trusted by themselves. Open rebuilds associated data from
        them and rejects the envelope unless the injected key agrees.
        """

        path = self._path(record.principal_id)
        temporary = path.with_suffix(".envelope.tmp")
        temporary.write_bytes(envelope)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        self._write_text(self._pointer(record.principal_id), str(record.revision))
        self._write_text(self._tenant_path(record.principal_id), record.tenant_id)

    def _path(self, principal_id: str) -> Path:
        return self._root / f"{principal_id}.envelope"

    def _pointer(self, principal_id: str) -> Path:
        return self._root / f"{principal_id}.revision"

    def _tenant_path(self, principal_id: str) -> Path:
        return self._root / f"{principal_id}.tenant"

    def _tenant_hint(self, principal_id: str) -> str | None:
        path = self._tenant_path(principal_id)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8").strip()

    def _write_text(self, path: Path, text: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)


def _roles_from_request(body: Mapping[str, Any]) -> set[str]:
    found: set[str] = set()
    role = body.get("role")
    if isinstance(role, str) and role.strip():
        found.add(role.strip())
    roles = body.get("roles")
    if isinstance(roles, str) and roles.strip():
        found.add(roles.strip())
    elif isinstance(roles, (list, tuple)):
        for item in roles:
            if isinstance(item, str) and item.strip():
                found.add(item.strip())
    staff = body.get("staff_role")
    if isinstance(staff, str) and staff.strip():
        found.add(staff.strip())
    return found


def _staff_flag(body: Mapping[str, Any]) -> bool:
    for name in ("is_admin", "is_staff", "is_lawyer"):
        if body.get(name) is True:
            return True
    return False


def _record_document(record: PrincipalRecord) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "principal_id": record.principal_id,
        "tenant_id": record.tenant_id,
        "roles": list(record.roles),
        "status": record.status,
        "revision": record.revision,
        "role_authority": record.role_authority,
        "excluded_fields": list(record.excluded_fields),
    }


def _record_from_document(document: Mapping[str, Any]) -> PrincipalRecord:
    if int(document.get("schema_version") or 0) != SCHEMA_VERSION:
        raise PrincipalStoreError("schema")
    roles = tuple(str(item) for item in document.get("roles") or ())
    if not roles or any(role not in KNOWN_ROLES for role in roles):
        raise PrincipalStoreError("unknown_role")
    excluded = tuple(str(item) for item in document.get("excluded_fields") or ())
    revision = document.get("revision")
    if type(revision) is not int or revision < 1:
        raise PrincipalStoreError("revision")
    return PrincipalRecord(
        principal_id=_label(str(document.get("principal_id") or ""), "principal_id"),
        tenant_id=_label(str(document.get("tenant_id") or ""), "tenant_id"),
        roles=roles,
        status=_label(str(document.get("status") or ""), "status"),
        revision=revision,
        role_authority=_label(str(document.get("role_authority") or ""), "role_authority"),
        excluded_fields=excluded,
    )
