"""Stable case namespaces for one authenticated principal.

A case is the triple ``(tenant_id, case_id, resource_id)``. ``tenant_id`` is
the canonical encrypted owner. ``case_id`` and ``resource_id`` are independent
of any request ``user_id``. Selection uses the authenticated principal plus an
explicit case id. A supplied ``user_id`` is never a lookup key.

Storage versions:

- ``1`` owner-only legacy. Historical sessions were sealed with
  ``tenant_id == case_id == principal_id``, artifact kind ``session``, and
  revision ``session-v1``. Those bytes stay readable when the injected key
  opens that binding. The directory records the identity and does not rewrite
  the session.
- ``2`` namespaced cases. New cases minted for a principal that has no legacy
  owner use a canonical tenant distinct from the actor. Additional cases for a
  principal that already adopted a legacy owner keep that historical tenant so
  existing associated data still matches, and receive new case and resource ids.

A missing or wrong key raises ``missing_key`` and does not write an empty case
or replace an existing directory envelope.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import fcntl
from contextlib import contextmanager
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    PrivateStorageError,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)

DIRECTORY_SCHEMA_VERSION = 2
LEGACY_OWNER_ONLY_VERSION = 1
NAMESPACED_CASE_VERSION = 2
DIRECTORY_CASE_ID = "case-directory"
DIRECTORY_ARTIFACT_KIND = "case-namespace"
LEGACY_ARTIFACT_KIND = "session"
LEGACY_REVISION = "session-v1"
MEMBERSHIP_OWNER_ONLY = "owner-only"
MIGRATION_RULES = (
    "storage_version_1_owner_only_readable",
    "legacy_tenant_preserved_for_additional_cases",
    "new_principal_tenant_distinct_from_actor",
    "missing_key_does_not_create_empty_case",
    "user_id_is_not_a_selector",
)


class CaseDirectoryError(Exception):
    """Fail-closed namespace error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


@dataclass(frozen=True)
class _CanonicalAccess:
    trust: str
    principal_id: str
    case_id: str


@dataclass(frozen=True)
class CaseNamespace:
    tenant_id: str
    case_id: str
    resource_id: str
    owner_principal_id: str
    storage_version: int
    membership: str
    revision: int

    def identity(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "resource_id": self.resource_id,
            "owner_principal_id": self.owner_principal_id,
            "storage_version": self.storage_version,
            "membership": self.membership,
            "revision": self.revision,
            "actor_is_encrypted_owner": self.owner_principal_id == self.tenant_id,
        }


def _opaque_id() -> str:
    return uuid.uuid4().hex


def _label(value: str, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseDirectoryError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseDirectoryError(code)
    return value


def legacy_owner_only_binding(owner_principal_id: str) -> PrivateArtifactBinding:
    """Binding declared for existing owner-only encrypted sessions."""

    owner = _label(owner_principal_id, "principal_id")
    return PrivateArtifactBinding(
        tenant_id=owner,
        case_id=owner,
        artifact_kind=LEGACY_ARTIFACT_KIND,
        revision=LEGACY_REVISION,
        principal_id=owner,
    )


def _legacy_resource_id(owner_principal_id: str) -> str:
    digest = hashlib.sha256(owner_principal_id.encode("utf-8")).hexdigest()
    return f"owner-only-session:{digest}"


class CaseDirectory:
    """Sealed index of owner-only cases for authenticated principals."""

    def __init__(self, root: str | Path, *, key: bytes, key_id: str) -> None:
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview):
            raise CaseDirectoryError("key_material")
        if len(bytes(key)) != 32:
            raise CaseDirectoryError("key_material")
        self._key = bytes(key)
        self._key_id = _label(key_id, "key_id")
        self._root = Path(root)
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def create_case(
        self,
        *,
        actor_principal_id: str,
        supplied_user_id: str | None = None,
        unreadable_legacy_envelope: bytes | None = None,
    ) -> CaseNamespace:
        actor = self._actor(actor_principal_id, supplied_user_id)
        with self._owner_lock(actor):
            return self._create_case_locked(actor_principal_id=actor,
                supplied_user_id=supplied_user_id, unreadable_legacy_envelope=unreadable_legacy_envelope)

    def _create_case_locked(
        self,
        *,
        actor_principal_id: str,
        supplied_user_id: str | None = None,
        unreadable_legacy_envelope: bytes | None = None,
    ) -> CaseNamespace:
        """Mint one owner-only case. Never treats ``supplied_user_id`` as the id."""

        actor = self._actor(actor_principal_id, supplied_user_id)
        if unreadable_legacy_envelope is not None:
            self._refuse_unreadable_legacy(actor, unreadable_legacy_envelope)
        document = self._load_document(actor)
        tenant_id = self._tenant_for_new_case(actor, document)
        case_id = _opaque_id()
        resource_id = f"case-resource:{_opaque_id()}"
        if case_id == tenant_id or case_id == actor or resource_id == case_id:
            raise CaseDirectoryError("identifier_collision")
        record = CaseNamespace(
            tenant_id=tenant_id,
            case_id=case_id,
            resource_id=resource_id,
            owner_principal_id=actor,
            storage_version=NAMESPACED_CASE_VERSION,
            membership=MEMBERSHIP_OWNER_ONLY,
            revision=1,
        )
        cases = list(document["cases"]) if document is not None else []
        if any(item["case_id"] == record.case_id or item["resource_id"] == record.resource_id for item in cases):
            raise CaseDirectoryError("identifier_collision")
        cases.append(_case_document(record))
        self._write_document(actor, tenant_id, cases, revision=1 if document is None else int(document["revision"]) + 1)
        return record

    def adopt_owner_only_case(
        self,
        *,
        actor_principal_id: str,
        envelope: bytes,
        supplied_user_id: str | None = None,
    ) -> tuple[CaseNamespace, dict[str, Any]]:
        actor = self._actor(actor_principal_id, supplied_user_id)
        with self._owner_lock(actor):
            return self._adopt_owner_only_case_locked(actor_principal_id=actor,
                envelope=envelope, supplied_user_id=supplied_user_id)

    def _adopt_owner_only_case_locked(
        self,
        *,
        actor_principal_id: str,
        envelope: bytes,
        supplied_user_id: str | None = None,
    ) -> tuple[CaseNamespace, dict[str, Any]]:
        """Record a legacy owner-only session after the injected key opens it.

        The session plaintext is returned to the caller and is not copied into
        the directory envelope. Failure leaves the directory unchanged.
        """

        actor = self._actor(actor_principal_id, supplied_user_id)
        payload = self._open_legacy(actor, envelope)
        document = self._load_document(actor)
        resource_id = _legacy_resource_id(actor)
        existing = None
        cases = [] if document is None else list(document["cases"])
        for item in cases:
            if item["storage_version"] == LEGACY_OWNER_ONLY_VERSION and item["resource_id"] == resource_id:
                existing = _case_from_document(item, actor)
                break
        if existing is not None:
            return existing, payload
        record = CaseNamespace(
            tenant_id=actor,
            case_id=actor,
            resource_id=resource_id,
            owner_principal_id=actor,
            storage_version=LEGACY_OWNER_ONLY_VERSION,
            membership=MEMBERSHIP_OWNER_ONLY,
            revision=1,
        )
        cases.append(_case_document(record))
        tenant_id = actor if document is None else str(document["canonical_tenant_id"])
        if document is not None and tenant_id != actor:
            raise CaseDirectoryError("legacy_tenant_conflict")
        revision = 1 if document is None else int(document["revision"]) + 1
        self._write_document(actor, actor, cases, revision=revision)
        return record, payload

    def read_owner_only_case(
        self,
        *,
        actor_principal_id: str,
        envelope: bytes,
        supplied_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Open a legacy envelope in memory. Does not create a case."""

        actor = self._actor(actor_principal_id, supplied_user_id)
        return self._open_legacy(actor, envelope)

    def list_cases(
        self,
        *,
        actor_principal_id: str,
        supplied_user_id: str | None = None,
    ) -> tuple[CaseNamespace, ...]:
        actor = self._actor(actor_principal_id, supplied_user_id)
        with self._owner_lock(actor):
            document = self._load_document(actor)
        if document is None:
            return ()
        return tuple(_case_from_document(item, actor) for item in document["cases"])

    def select_case(
        self,
        *,
        actor_principal_id: str,
        case_id: str,
        supplied_user_id: str | None = None,
    ) -> CaseNamespace:
        actor = self._actor(actor_principal_id, supplied_user_id, case_id=case_id)
        selected = _label(case_id, "case_id")
        if supplied_user_id is not None and selected == supplied_user_id and selected != actor:
            raise CaseDirectoryError("user_id_not_a_selector")
        for record in self.list_cases(actor_principal_id=actor):
            if record.case_id == selected:
                return record
        raise CaseDirectoryError("missing_case")

    def owned_revision_directory(self, *, actor_principal_id: str, case_id: str) -> Path:
        """Return a private revision-store slot for an already authorized owner.

        This is a storage locator, not a key grant. The encrypted directory is
        opened first; missing keys and foreign cases never create a new slot.
        Callers must retain their content binding and serialize writes there.
        """
        record = self.select_case(actor_principal_id=actor_principal_id, case_id=case_id)
        root = self._root.absolute()
        if root.resolve(strict=True) != root:
            raise CaseDirectoryError("unexpected_path")
        parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(parent)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
                raise CaseDirectoryError("unexpected_path")
            identity = json.dumps([record.tenant_id, record.case_id, record.resource_id], separators=(",", ":"))
            parts = ("case-revisions", hashlib.sha256(identity.encode()).hexdigest())
            for part in parts:
                try:
                    os.mkdir(part, 0o700, dir_fd=parent)
                    os.fsync(parent)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
                info = os.fstat(child)
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    os.close(child)
                    raise CaseDirectoryError("unexpected_path")
                os.close(parent)
                parent = child
            return root.joinpath(*parts)
        finally:
            os.close(parent)

    @contextmanager
    def _owner_lock(self, actor: str):
        root = self._root.absolute()
        if root.resolve(strict=True) != root:
            raise CaseDirectoryError("unexpected_path")
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        lock = None
        try:
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
                raise CaseDirectoryError("unexpected_path")
            try:
                os.mkdir("directory-locks", 0o700, dir_fd=directory)
                os.fsync(directory)
            except FileExistsError:
                pass
            locks = os.open("directory-locks", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=directory)
            os.close(directory)
            directory = locks
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise CaseDirectoryError("unexpected_path")
            lock = os.open(self._slot(actor) + ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                           0o600, dir_fd=directory)
            info = os.fstat(lock)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o600):
                raise CaseDirectoryError("unexpected_path")
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield
        finally:
            if lock is not None:
                os.close(lock)
            os.close(directory)

    def _actor(self, actor_principal_id: str, supplied_user_id: str | None, *, case_id: str | None = None) -> str:
        actor = _label(actor_principal_id, "principal_id")
        if supplied_user_id is None:
            return actor
        if not isinstance(supplied_user_id, str) or supplied_user_id.strip() == "":
            raise CaseDirectoryError("user_id_not_a_selector")
        if supplied_user_id != actor:
            raise CaseDirectoryError("user_id_not_a_selector")
        if case_id is not None and case_id == supplied_user_id and case_id != actor:
            raise CaseDirectoryError("user_id_not_a_selector")
        return actor

    def _refuse_unreadable_legacy(self, actor: str, envelope: bytes) -> None:
        try:
            self._open_legacy(actor, envelope)
        except CaseDirectoryError as exc:
            if exc.code == "missing_key":
                raise
            raise CaseDirectoryError("missing_key") from exc
        raise CaseDirectoryError("legacy_requires_adoption")

    def _open_legacy(self, actor: str, envelope: bytes) -> dict[str, Any]:
        if not isinstance(envelope, (bytes, bytearray)) or len(bytes(envelope)) == 0:
            raise CaseDirectoryError("missing_key")
        binding = legacy_owner_only_binding(actor)
        access = _CanonicalAccess("authenticated", actor, actor)
        assert_access_matches_binding(access, binding)
        try:
            plaintext = open_private_artifact(
                bytes(envelope),
                binding=binding,
                key=self._key,
                expected_key_id=self._key_id,
            )
            payload = json.loads(plaintext.decode("utf-8"))
        except (PrivateArtifactIntegrityError, PrivateStorageError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CaseDirectoryError("missing_key") from exc
        if not isinstance(payload, dict):
            raise CaseDirectoryError("legacy_corrupt")
        owner = payload.get("user_id")
        if owner is not None and owner != actor:
            raise CaseDirectoryError("foreign_owner")
        return payload

    def _tenant_for_new_case(self, actor: str, document: Mapping[str, Any] | None) -> str:
        if document is None:
            tenant_id = _opaque_id()
            if tenant_id == actor:
                raise CaseDirectoryError("identifier_collision")
            return tenant_id
        return _label(str(document["canonical_tenant_id"]), "tenant_id")

    def _load_document(self, actor: str) -> dict[str, Any] | None:
        path = self._path(actor)
        if not path.exists():
            return None
        if not path.is_file() or path.is_symlink():
            raise CaseDirectoryError("unexpected_path")
        pointer = self._pointer(actor)
        tenant_hint = self._tenant_hint(actor)
        if not pointer.is_file() or tenant_hint is None:
            raise CaseDirectoryError("missing_key")
        revision_text = pointer.read_text(encoding="utf-8").strip()
        if not revision_text.isdigit():
            raise CaseDirectoryError("revision_pointer")
        binding = self._binding(tenant_hint, int(revision_text))
        access = _CanonicalAccess("authenticated", tenant_hint, DIRECTORY_CASE_ID)
        assert_access_matches_binding(access, binding)
        try:
            plaintext = open_private_artifact(
                path.read_bytes(),
                binding=binding,
                key=self._key,
                expected_key_id=self._key_id,
            )
            document = json.loads(plaintext.decode("utf-8"))
        except (PrivateArtifactIntegrityError, PrivateStorageError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CaseDirectoryError("missing_key") from exc
        if not isinstance(document, dict):
            raise CaseDirectoryError("missing_key")
        if int(document.get("schema_version") or 0) != DIRECTORY_SCHEMA_VERSION:
            raise CaseDirectoryError("schema")
        if document.get("owner_principal_id") != actor or document.get("canonical_tenant_id") != tenant_hint:
            raise CaseDirectoryError("binding_mismatch")
        if document.get("revision") != int(revision_text):
            raise CaseDirectoryError("revision_mismatch")
        cases = document.get("cases")
        if not isinstance(cases, list) or not cases:
            raise CaseDirectoryError("empty_case_forbidden")
        return document

    def _write_document(self, actor: str, tenant_id: str, cases: list[dict[str, Any]], *, revision: int) -> None:
        if not cases:
            raise CaseDirectoryError("empty_case_forbidden")
        document = {
            "schema_version": DIRECTORY_SCHEMA_VERSION,
            "owner_principal_id": actor,
            "canonical_tenant_id": tenant_id,
            "revision": revision,
            "membership": MEMBERSHIP_OWNER_ONLY,
            "migration_rules": list(MIGRATION_RULES),
            "cases": cases,
        }
        binding = self._binding(tenant_id, revision)
        access = _CanonicalAccess("authenticated", tenant_id, DIRECTORY_CASE_ID)
        assert_access_matches_binding(access, binding)
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        envelope = seal_private_artifact(payload, binding=binding, key=self._key, key_id=self._key_id)
        path = self._path(actor)
        temporary = path.with_suffix(".envelope.tmp")
        temporary.write_bytes(envelope)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        self._write_text(self._pointer(actor), str(revision))
        self._write_text(self._tenant_path(actor), tenant_id)

    def _binding(self, tenant_id: str, revision: int) -> PrivateArtifactBinding:
        return PrivateArtifactBinding(
            tenant_id=tenant_id,
            case_id=DIRECTORY_CASE_ID,
            artifact_kind=DIRECTORY_ARTIFACT_KIND,
            revision=str(revision),
            principal_id=tenant_id,
        )

    def _slot(self, actor: str) -> str:
        return hashlib.sha256(actor.encode("utf-8")).hexdigest()

    def _path(self, actor: str) -> Path:
        return self._root / f"{self._slot(actor)}.envelope"

    def _pointer(self, actor: str) -> Path:
        return self._root / f"{self._slot(actor)}.revision"

    def _tenant_path(self, actor: str) -> Path:
        return self._root / f"{self._slot(actor)}.tenant"

    def _tenant_hint(self, actor: str) -> str | None:
        path = self._tenant_path(actor)
        if not path.is_file() or path.is_symlink():
            return None
        text = path.read_text(encoding="utf-8").strip()
        return text or None

    def _write_text(self, path: Path, text: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)


def _case_document(record: CaseNamespace) -> dict[str, Any]:
    return {
        "tenant_id": record.tenant_id,
        "case_id": record.case_id,
        "resource_id": record.resource_id,
        "storage_version": record.storage_version,
        "membership": record.membership,
        "revision": record.revision,
    }


def _case_from_document(document: Mapping[str, Any], actor: str) -> CaseNamespace:
    storage_version = document.get("storage_version")
    if storage_version not in {LEGACY_OWNER_ONLY_VERSION, NAMESPACED_CASE_VERSION}:
        raise CaseDirectoryError("schema")
    if document.get("membership") != MEMBERSHIP_OWNER_ONLY:
        raise CaseDirectoryError("membership")
    revision = document.get("revision")
    if type(revision) is not int or revision < 1:
        raise CaseDirectoryError("revision")
    return CaseNamespace(
        tenant_id=_label(str(document.get("tenant_id") or ""), "tenant_id"),
        case_id=_label(str(document.get("case_id") or ""), "case_id"),
        resource_id=_label(str(document.get("resource_id") or ""), "resource_id"),
        owner_principal_id=actor,
        storage_version=int(storage_version),
        membership=MEMBERSHIP_OWNER_ONLY,
        revision=revision,
    )
