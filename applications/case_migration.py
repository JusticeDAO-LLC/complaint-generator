"""Resumable migration of explicitly selected cases.

Only case ids named by the caller are admitted. The service never walks a
directory, never reads a path that was not named on an admitted artifact, and
never rewrites the case directory. Each artifact is sealed with the canonical
owner binding already stored for that case (tenant, case, principal, kind, and
revision). The actor principal is not that owner.

A missing or locked key does not mint a data key and does not publish an empty
replacement. Cleanup of a named synthetic source runs only after ciphertext
readback and a separate recovery copy are durable.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from applications.case_directory import CaseDirectory, CaseDirectoryError
from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    PrivateKeyLockedError,
    PrivateKeyMaterialError,
    PrivateStorageError,
    UserOwnedKeySession,
    open_private_artifact,
    seal_private_artifact,
)

MIGRATION_SCHEMA = "complaint-case-migration/v1"
MIGRATION_SCHEMA_VERSION = 1
_JOURNAL_NAME = "case_migration_journal.json"
_RECOVERY_JOURNAL = "recovery_journal.json"
_MAX_SOURCE_BYTES = 256 * 1024
_ENTRY_FIELDS = (
    "artifact_ref",
    "case_id",
    "tenant_id",
    "principal_id",
    "owner_principal_id",
    "actor_principal_id",
    "artifact_kind",
    "revision",
    "resource_id",
    "source_storage_version",
    "migration_schema_version",
    "ciphertext_name",
    "ciphertext_sha256",
    "readback",
    "status",
    "owner_binding_preserved",
    "actor_is_encrypted_owner",
    "recovery_name",
)
LIMITATIONS = (
    "explicit_selection_only",
    "no_directory_scan",
    "old_owner_binding_preserved",
    "cleanup_only_after_recovery_evidence",
    "does_not_rewrite_case_directory",
    "actor_is_not_canonical_owner",
    "no_empty_replacement_on_missing_key",
    "no_real_user_data_in_campaign_validation",
)


class CaseMigrationError(Exception):
    """Fail-closed migration error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


class CaseMigrationInterrupted(CaseMigrationError):
    """Progress is durable through the last verified artifact."""

    def __init__(self, partial: Mapping[str, Any]) -> None:
        super().__init__("interrupted")
        self.partial = dict(partial)


def _label(value: Any, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseMigrationError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseMigrationError(code)
    return value


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact_ref(tenant_id: str, case_id: str, kind: str, revision: str) -> str:
    material = "\0".join((tenant_id, case_id, kind, revision)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _directory(path: Path) -> Path:
    root = Path(os.path.abspath(path))
    if root.is_symlink():
        raise CaseMigrationError("unsafe_path")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
        raise CaseMigrationError("unsafe_path")
    return root


def _regular_file(path: Path, *, root: Path) -> Path:
    candidate = Path(os.path.abspath(path))
    if candidate.is_symlink() or not candidate.is_relative_to(root):
        raise CaseMigrationError("path_outside_workspace")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(candidate, flags)
    except OSError as exc:
        raise CaseMigrationError("unsafe_path") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise CaseMigrationError("unsafe_path")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise CaseMigrationError("unsafe_path")
        blob = os.read(fd, _MAX_SOURCE_BYTES + 1)
    finally:
        os.close(fd)
    if not blob or len(blob) > _MAX_SOURCE_BYTES:
        raise CaseMigrationError("empty_or_oversized_source")
    return candidate


def _read_exact(path: Path) -> bytes:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
            raise CaseMigrationError("unsafe_path")
        return os.read(fd, _MAX_SOURCE_BYTES + 1)
    finally:
        os.close(fd)


def _write_bytes(path: Path, payload: bytes, *, exclusive: bool) -> None:
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    temporary_name = f".{path.name}.{os.getpid()}.tmp"
    fd = -1
    published = False
    try:
        fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent_fd,
        )
        os.write(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        temporary = path.parent / temporary_name
        if _read_exact(temporary) != payload:
            raise CaseMigrationError("readback_failed")
        if exclusive:
            os.link(temporary_name, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
        else:
            os.replace(temporary, path)
        published = True
        os.fsync(parent_fd)
    except FileExistsError as exc:
        raise CaseMigrationError("destination_preserved") from exc
    except OSError as exc:
        raise CaseMigrationError("publication_failed") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        if not published or exclusive:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except OSError:
                pass
        os.close(parent_fd)


def _binding_of(case_tenant: str, case_id: str, kind: str, revision: str) -> PrivateArtifactBinding:
    return PrivateArtifactBinding(
        tenant_id=case_tenant,
        case_id=case_id,
        artifact_kind=kind,
        revision=revision,
        principal_id=case_tenant,
    )


def _public_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {name: entry[name] for name in _ENTRY_FIELDS}


class CaseMigrationService:
    """Migrate named cases with the owner's unlocked data key."""

    def __init__(
        self,
        directory: CaseDirectory,
        session: UserOwnedKeySession,
        destination_root: str | Path,
        recovery_root: str | Path,
        *,
        synthetic_root: str | Path,
    ) -> None:
        if not isinstance(directory, CaseDirectory) or not isinstance(session, UserOwnedKeySession):
            raise CaseMigrationError("migration_unavailable")
        self._directory = directory
        self._session = session
        self._destination = _directory(Path(destination_root))
        self._recovery = _directory(Path(recovery_root))
        self._synthetic = _directory(Path(synthetic_root))
        if self._destination == self._recovery or self._destination == self._synthetic or self._recovery == self._synthetic:
            raise CaseMigrationError("workspace_overlap")
        self._journal_path = self._destination / _JOURNAL_NAME
        self._recovery_journal_path = self._recovery / _RECOVERY_JOURNAL

    def migrate(
        self,
        actor_principal_id: str,
        selected_case_ids: Sequence[str],
        artifacts: Sequence[Mapping[str, Any]],
        *,
        cleanup: bool = False,
        fail_after_verified: int | None = None,
        before_cleanup: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        actor = _label(actor_principal_id, "actor")
        selected = self._selection(selected_case_ids)
        admitted = self._admit(actor, selected, artifacts)
        journal = self._load_journal(self._journal_path)
        originals = {item["source_path"]: _read_exact(item["source_path"]) for item in admitted}
        authorized = self._authorize(admitted)
        if authorized is None:
            return self._result(
                status="unlock_needed" if not self._session.unlocked else "unauthorized_key",
                code="unlock_needed" if not self._session.unlocked else "unauthorized_key",
                admitted=admitted,
                entries=list(journal["entries"]),
                committed=0,
                cleanup=False,
            )
        entries = {item["artifact_ref"]: item for item in journal["entries"]}
        committed_now = 0
        for item in admitted:
            ref = item["ref"]
            target = self._destination / f"{ref}.bin"
            existing = entries.get(ref)
            try:
                if existing is not None and existing.get("readback") == "verified" and target.is_file():
                    self._require_readback(item, authorized[ref], target, existing["ciphertext_sha256"], originals[item["source_path"]])
                    continue
                if fail_after_verified is not None and committed_now >= fail_after_verified:
                    partial = self._publish(journal, entries, admitted, committed=self._verified_count(entries, admitted), complete=False)
                    raise CaseMigrationInterrupted(partial)
                envelope = self._seal_or_copy(item, authorized[ref], originals[item["source_path"]], target)
                digest = _sha256(envelope)
                recovery_name = f"{ref}.bin"
                recovery_path = self._recovery / recovery_name
                _write_bytes(recovery_path, envelope, exclusive=not recovery_path.exists())
                if _read_exact(recovery_path) != envelope:
                    raise CaseMigrationError("readback_failed")
                opened = open_private_artifact(
                    envelope,
                    binding=item["binding"],
                    key=authorized[ref][1],
                    expected_key_id=authorized[ref][0],
                )
                if opened != originals[item["source_path"]]:
                    raise CaseMigrationError("readback_failed")
                if not target.is_file():
                    _write_bytes(target, envelope, exclusive=True)
                stored = _read_exact(target)
                if stored != envelope or open_private_artifact(
                    stored, binding=item["binding"], key=authorized[ref][1], expected_key_id=authorized[ref][0]
                ) != originals[item["source_path"]]:
                    raise CaseMigrationError("readback_failed")
                entries[ref] = self._entry(item, digest, recovery_name)
                committed_now += 1
                self._publish(journal, entries, admitted, committed=self._verified_count(entries, admitted), complete=False)
                self._publish_recovery(entries)
            except CaseMigrationInterrupted:
                raise
            except CaseMigrationError as exc:
                return self._result(
                    "recoverable",
                    exc.code,
                    admitted,
                    list(entries.values()),
                    self._verified_count(entries, admitted),
                    False,
                )
        complete = bool(admitted) and all(item["ref"] in entries for item in admitted)
        result = self._publish(journal, entries, admitted, committed=self._verified_count(entries, admitted), complete=complete)
        if not complete:
            return result
        if cleanup:
            self._cleanup(admitted, originals, entries, before_cleanup)
            result = self._result("complete", "", admitted, list(entries.values()), len(admitted), True)
            result["recovery_retained"] = True
            return result
        result["recovery_retained"] = True
        result["cleanup_performed"] = False
        return result

    def _selection(self, selected_case_ids: Sequence[str]) -> tuple[str, ...]:
        if not isinstance(selected_case_ids, Sequence) or isinstance(selected_case_ids, (str, bytes)) or not selected_case_ids:
            raise CaseMigrationError("selection_required")
        chosen: list[str] = []
        seen: set[str] = set()
        for case_id in selected_case_ids:
            label = _label(case_id, "case_id")
            if label in seen:
                raise CaseMigrationError("duplicate_selection")
            seen.add(label)
            chosen.append(label)
        return tuple(chosen)

    def _admit(self, actor: str, selected: Sequence[str], artifacts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(artifacts, Sequence) or isinstance(artifacts, (str, bytes)) or not artifacts:
            raise CaseMigrationError("selection_required")
        allowed = set(selected)
        by_case: dict[str, int] = {case_id: 0 for case_id in selected}
        admitted: list[dict[str, Any]] = []
        refs: set[str] = set()
        for raw in artifacts:
            if not isinstance(raw, Mapping):
                raise CaseMigrationError("artifact_rejected")
            if any(name in raw for name in ("key", "passphrase", "key_bytes", "user_id", "resource_id")):
                raise CaseMigrationError("selector_rejected")
            case_id = _label(raw.get("case_id"), "case_id")
            if case_id not in allowed:
                raise CaseMigrationError("unselected_case")
            try:
                case = self._directory.select_case(actor_principal_id=actor, case_id=case_id)
            except CaseDirectoryError as exc:
                raise CaseMigrationError("missing_case" if exc.code == "missing_case" else "not_owner") from exc
            tenant_id = _label(raw.get("tenant_id"), "tenant_id")
            principal_id = _label(raw.get("principal_id"), "principal_id")
            kind = _label(raw.get("artifact_kind"), "artifact_kind")
            revision = _label(raw.get("revision"), "revision")
            storage_version = raw.get("storage_version")
            if type(storage_version) is not int or storage_version != case.storage_version:
                raise CaseMigrationError("version_mismatch")
            if tenant_id != case.tenant_id or principal_id != case.tenant_id:
                raise CaseMigrationError("owner_binding_mismatch")
            if case.owner_principal_id != actor:
                raise CaseMigrationError("not_owner")
            source = raw.get("source_path")
            if not isinstance(source, (str, Path)):
                raise CaseMigrationError("source_required")
            path = _regular_file(Path(source), root=self._synthetic)
            binding = _binding_of(case.tenant_id, case.case_id, kind, revision)
            ref = _artifact_ref(case.tenant_id, case.case_id, kind, revision)
            if ref in refs:
                raise CaseMigrationError("duplicate_binding")
            refs.add(ref)
            by_case[case_id] += 1
            admitted.append({
                "case": case,
                "binding": binding,
                "ref": ref,
                "source_path": path,
                "actor": actor,
                "kind": kind,
                "revision": revision,
            })
        if any(count == 0 for count in by_case.values()):
            raise CaseMigrationError("incomplete_selection")
        admitted.sort(key=lambda item: (item["case"].case_id, item["kind"], item["revision"]))
        return admitted

    def _authorize(self, admitted: Sequence[Mapping[str, Any]]) -> dict[str, tuple[str, bytes]] | None:
        if not self._session.unlocked:
            return None
        found: dict[str, tuple[str, bytes]] = {}
        try:
            provider = self._session.provider()
        except PrivateKeyLockedError:
            return None
        for item in admitted:
            try:
                key_id, key = provider.resolve(item["binding"])
            except (PrivateKeyMaterialError, PrivateKeyLockedError):
                return None
            if not isinstance(key, (bytes, bytearray)) or len(bytes(key)) != 32:
                return None
            found[item["ref"]] = (key_id, bytes(key))
        return found

    def _seal_or_copy(self, item: Mapping[str, Any], material: tuple[str, bytes], payload: bytes, target: Path) -> bytes:
        key_id, key = material
        binding = item["binding"]
        if target.is_file():
            existing = _read_exact(target)
            opened = open_private_artifact(existing, binding=binding, key=key, expected_key_id=key_id)
            if opened != payload:
                raise CaseMigrationError("destination_preserved")
            return existing
        envelope = seal_private_artifact(payload, binding=binding, key=key, key_id=key_id)
        if open_private_artifact(envelope, binding=binding, key=key, expected_key_id=key_id) != payload:
            raise CaseMigrationError("readback_failed")
        return envelope

    def _require_readback(self, item: Mapping[str, Any], material: tuple[str, bytes], target: Path, digest: str, payload: bytes) -> None:
        key_id, key = material
        blob = _read_exact(target)
        if _sha256(blob) != digest:
            raise CaseMigrationError("readback_failed")
        opened = open_private_artifact(blob, binding=item["binding"], key=key, expected_key_id=key_id)
        if opened != payload:
            raise CaseMigrationError("readback_failed")
        recovery = self._recovery / f"{item['ref']}.bin"
        if not recovery.is_file() or _read_exact(recovery) != blob:
            _write_bytes(recovery, blob, exclusive=not recovery.exists())

    def _entry(self, item: Mapping[str, Any], digest: str, recovery_name: str) -> dict[str, Any]:
        case = item["case"]
        binding = item["binding"]
        preserved = (
            binding.tenant_id == case.tenant_id
            and binding.case_id == case.case_id
            and binding.principal_id == case.tenant_id
            and binding.artifact_kind == item["kind"]
            and binding.revision == item["revision"]
        )
        if not preserved:
            raise CaseMigrationError("owner_binding_mismatch")
        return {
            "artifact_ref": item["ref"],
            "case_id": case.case_id,
            "tenant_id": case.tenant_id,
            "principal_id": case.tenant_id,
            "owner_principal_id": case.owner_principal_id,
            "actor_principal_id": item["actor"],
            "artifact_kind": item["kind"],
            "revision": item["revision"],
            "resource_id": case.resource_id,
            "source_storage_version": case.storage_version,
            "migration_schema_version": MIGRATION_SCHEMA_VERSION,
            "ciphertext_name": item["ref"] + ".bin",
            "ciphertext_sha256": digest,
            "readback": "verified",
            "status": "processed",
            "owner_binding_preserved": True,
            "actor_is_encrypted_owner": case.owner_principal_id == case.tenant_id,
            "recovery_name": recovery_name,
        }

    def _load_journal(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"schema": MIGRATION_SCHEMA, "schema_version": MIGRATION_SCHEMA_VERSION, "entries": [], "complete": False}
        try:
            payload = json.loads(_read_exact(path).decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CaseMigrationError("malformed_journal") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != MIGRATION_SCHEMA
            or payload.get("schema_version") != MIGRATION_SCHEMA_VERSION
            or not isinstance(payload.get("entries"), list)
            or type(payload.get("complete")) is not bool
        ):
            raise CaseMigrationError("malformed_journal")
        seen: set[str] = set()
        for entry in payload["entries"]:
            if not isinstance(entry, dict) or set(entry) != set(_ENTRY_FIELDS):
                raise CaseMigrationError("malformed_journal")
            if entry["artifact_ref"] in seen or entry["readback"] != "verified" or entry["status"] != "processed":
                raise CaseMigrationError("malformed_journal")
            if entry["owner_binding_preserved"] is not True or entry["migration_schema_version"] != MIGRATION_SCHEMA_VERSION:
                raise CaseMigrationError("malformed_journal")
            if entry["principal_id"] != entry["tenant_id"]:
                raise CaseMigrationError("malformed_journal")
            seen.add(entry["artifact_ref"])
        return payload

    def _publish(
        self,
        journal: dict[str, Any],
        entries: Mapping[str, Mapping[str, Any]],
        admitted: Sequence[Mapping[str, Any]],
        *,
        committed: int,
        complete: bool,
    ) -> dict[str, Any]:
        body = {
            "schema": MIGRATION_SCHEMA,
            "schema_version": MIGRATION_SCHEMA_VERSION,
            "entries": [_public_entry(entries[item["ref"]]) for item in admitted if item["ref"] in entries],
            "complete": complete,
        }
        _write_bytes(self._journal_path, json.dumps(body, sort_keys=True).encode("utf-8"), exclusive=False)
        journal["entries"] = body["entries"]
        journal["complete"] = complete
        return self._result("complete" if complete else "partial", "", admitted, body["entries"], committed, False)

    def _publish_recovery(self, entries: Mapping[str, Mapping[str, Any]]) -> None:
        body = {
            "schema": MIGRATION_SCHEMA,
            "schema_version": MIGRATION_SCHEMA_VERSION,
            "entries": [_public_entry(entry) for entry in entries.values()],
            "recovery_only": True,
        }
        _write_bytes(self._recovery_journal_path, json.dumps(body, sort_keys=True).encode("utf-8"), exclusive=False)

    def _cleanup(
        self,
        admitted: Sequence[Mapping[str, Any]],
        originals: Mapping[Path, bytes],
        entries: Mapping[str, Mapping[str, Any]],
        before_cleanup: Callable[[Mapping[str, Any]], None] | None,
    ) -> None:
        for item in admitted:
            entry = entries[item["ref"]]
            recovery = self._recovery / str(entry["recovery_name"])
            blob = _read_exact(recovery)
            if _sha256(blob) != entry["ciphertext_sha256"]:
                raise CaseMigrationError("recovery_missing")
            if _read_exact(item["source_path"]) != originals[item["source_path"]]:
                raise CaseMigrationError("source_changed")
        evidence = {
            "recovery_journal": str(self._recovery_journal_path),
            "sources_present": [str(item["source_path"]) for item in admitted],
            "recovery_files": [str(self._recovery / entries[item["ref"]]["recovery_name"]) for item in admitted],
        }
        if before_cleanup is not None:
            before_cleanup(evidence)
        for item in admitted:
            if _read_exact(item["source_path"]) != originals[item["source_path"]]:
                raise CaseMigrationError("source_changed")
            os.unlink(item["source_path"])

    def _verified_count(self, entries: Mapping[str, Any], admitted: Sequence[Mapping[str, Any]]) -> int:
        return sum(1 for item in admitted if item["ref"] in entries)

    def _result(
        self,
        status: str,
        code: str,
        admitted: Sequence[Mapping[str, Any]],
        entries: Sequence[Mapping[str, Any]],
        committed: int,
        cleanup: bool,
    ) -> dict[str, Any]:
        return {
            "schema": MIGRATION_SCHEMA,
            "schema_version": MIGRATION_SCHEMA_VERSION,
            "status": status,
            "code": code,
            "complete": status == "complete",
            "committed": committed,
            "total": len(admitted),
            "entries": [dict(entry) for entry in entries],
            "cleanup_performed": cleanup,
            "cleanup_complete": cleanup,
            "recovery_retained": bool(entries),
            "source_scan": False,
            "directory_rewritten": False,
            "empty_replacement": False,
            "limitations": LIMITATIONS,
        }


def migrate_selected_cases(
    *,
    actor_principal_id: str,
    directory: CaseDirectory,
    session: UserOwnedKeySession,
    destination_root: str | Path,
    recovery_root: str | Path,
    synthetic_root: str | Path,
    selected_case_ids: Sequence[str],
    artifacts: Sequence[Mapping[str, Any]],
    cleanup: bool = False,
    fail_after_verified: int | None = None,
    before_cleanup: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Public entry: resume or start migration for ``selected_case_ids`` only."""

    service = CaseMigrationService(
        directory,
        session,
        destination_root,
        recovery_root,
        synthetic_root=synthetic_root,
    )
    return service.migrate(
        actor_principal_id,
        selected_case_ids,
        artifacts,
        cleanup=cleanup,
        fail_after_verified=fail_after_verified,
        before_cleanup=before_cleanup,
    )
