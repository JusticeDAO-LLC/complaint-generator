"""Resumable migration of explicitly selected synthetic cases.

Positive cases seal a legacy owner-only case and a namespaced case with the
owner's authorized data key, resume after an interruption, and delete a source
only after recovery ciphertext is durable. Negative cases refuse an empty
selection, an unselected path, a missing key, a foreign actor, a rewritten
owner binding, and a corrupted destination. Nothing in this module scans a
user home or rewrites an unselected file.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from applications.case_directory import (
    LEGACY_OWNER_ONLY_VERSION,
    NAMESPACED_CASE_VERSION,
    CaseDirectory,
    legacy_owner_only_binding,
)
from applications.case_migration import (
    LIMITATIONS,
    MIGRATION_SCHEMA_VERSION,
    CaseMigrationError,
    CaseMigrationInterrupted,
    migrate_selected_cases,
)
from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    open_private_artifact,
    seal_private_artifact,
)
from integrations.private_storage import UserOwnedKeySession

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

PASSPHRASE = "synthetic-migration-passphrase"
DIRECTORY_KEY_ID = "synthetic-directory-key"


def _file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    path.write_bytes(payload)
    os.chmod(path, 0o600)
    return path


def _session(path: Path) -> UserOwnedKeySession:
    session = UserOwnedKeySession(path)
    session.create(protection="passphrase", passphrase=PASSPHRASE)
    assert session.unlocked is True
    return session


def _dirs(tmp_path: Path) -> dict[str, Path]:
    paths = {}
    for name in ("sources", "destination", "recovery", "cases", "keys"):
        path = tmp_path / name
        path.mkdir(mode=0o700)
        os.chmod(path, 0o700)
        paths[name] = path
    return paths


def _directory(path: Path) -> tuple[CaseDirectory, bytes]:
    key = os.urandom(32)
    return CaseDirectory(path, key=key, key_id=DIRECTORY_KEY_ID), key


def _namespaced(tmp_path: Path):
    paths = _dirs(tmp_path)
    directory, directory_key = _directory(paths["cases"])
    session = _session(paths["keys"])
    actor = "synthetic-owner"
    case = directory.create_case(actor_principal_id=actor)
    assert case.storage_version == NAMESPACED_CASE_VERSION
    assert case.tenant_id != actor
    session.ensure_data_key(case.tenant_id, case.case_id)
    return paths, directory, directory_key, session, actor, case


def _artifact(case, source: Path, *, kind: str, revision: str) -> dict:
    return {
        "case_id": case.case_id,
        "tenant_id": case.tenant_id,
        "principal_id": case.tenant_id,
        "artifact_kind": kind,
        "revision": revision,
        "storage_version": case.storage_version,
        "source_path": source,
    }


def _selected_ids(case) -> list[str]:
    if isinstance(case, (list, tuple)):
        return [item.case_id for item in case]
    return [case.case_id]


def _run(paths, directory, session, actor, case, artifacts, **kwargs):
    return migrate_selected_cases(
        actor_principal_id=actor,
        directory=directory,
        session=session,
        destination_root=paths["destination"],
        recovery_root=paths["recovery"],
        synthetic_root=paths["sources"],
        selected_case_ids=_selected_ids(case),
        artifacts=artifacts,
        **kwargs,
    )


def _open_entry(paths, session, entry, binding_case) -> bytes:
    blob = (paths["destination"] / entry["ciphertext_name"]).read_bytes()
    binding = PrivateArtifactBinding(
        tenant_id=entry["tenant_id"],
        case_id=entry["case_id"],
        artifact_kind=entry["artifact_kind"],
        revision=entry["revision"],
        principal_id=entry["principal_id"],
    )
    assert binding.principal_id == binding_case.tenant_id
    assert binding.principal_id != entry["actor_principal_id"] or binding_case.storage_version == LEGACY_OWNER_ONLY_VERSION
    key_id, key = session.provider().resolve(binding)
    return open_private_artifact(blob, binding=binding, key=key, expected_key_id=key_id)


def test_module_does_not_scan_or_rewrite_unselected_bytes(tmp_path: Path) -> None:
    source = Path("applications/case_migration.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "rglob" not in attributes
    assert "walk" not in attributes
    assert "scandir" not in names
    assert "glob" not in names
    paths, directory, _, session, actor, case = _namespaced(tmp_path)
    decoy = _file(paths["sources"] / "not-selected.bin", b"do-not-migrate-synthetic")
    selected = _file(paths["sources"] / "selected.bin", b"selected-synthetic-body")
    before = directory.list_cases(actor_principal_id=actor)
    with pytest.raises(CaseMigrationError) as rejected:
        migrate_selected_cases(
            actor_principal_id=actor,
            directory=directory,
            session=session,
            destination_root=paths["destination"],
            recovery_root=paths["recovery"],
            synthetic_root=paths["sources"],
            selected_case_ids=[],
            artifacts=[_artifact(case, selected, kind="note", revision="1")],
        )
    assert rejected.value.code == "selection_required"
    with pytest.raises(CaseMigrationError) as unselected:
        migrate_selected_cases(
            actor_principal_id=actor,
            directory=directory,
            session=session,
            destination_root=paths["destination"],
            recovery_root=paths["recovery"],
            synthetic_root=paths["sources"],
            selected_case_ids=[case.case_id],
            artifacts=[
                {
                    "case_id": "some-other-case",
                    "tenant_id": case.tenant_id,
                    "principal_id": case.tenant_id,
                    "artifact_kind": "note",
                    "revision": "1",
                    "storage_version": case.storage_version,
                    "source_path": decoy,
                },
                _artifact(case, selected, kind="note", revision="1"),
            ],
        )
    assert unselected.value.code == "unselected_case"
    assert decoy.read_bytes() == b"do-not-migrate-synthetic"
    assert selected.read_bytes() == b"selected-synthetic-body"
    assert directory.list_cases(actor_principal_id=actor) == before
    assert list(paths["destination"].glob("*.bin")) == []


def test_selected_cases_resume_and_preserve_owner_binding(tmp_path: Path) -> None:
    paths, directory, _, session, actor, first_case = _namespaced(tmp_path)
    second_case = directory.create_case(actor_principal_id=actor)
    untouched = directory.create_case(actor_principal_id=actor)
    session.ensure_data_key(second_case.tenant_id, second_case.case_id)
    assert first_case.tenant_id == second_case.tenant_id != actor
    first = _file(paths["sources"] / "one.txt", b"synthetic-one")
    second = _file(paths["sources"] / "two.txt", b"synthetic-two")
    decoy = _file(paths["sources"] / "untouched.txt", b"synthetic-untouched")
    directory_before = {path.name: path.read_bytes() for path in paths["cases"].iterdir() if path.is_file()}
    artifacts = [
        _artifact(second_case, second, kind="note", revision="2"),
        _artifact(first_case, first, kind="note", revision="1"),
    ]
    with pytest.raises(CaseMigrationInterrupted) as interrupted:
        _run(paths, directory, session, actor, (first_case, second_case), artifacts, fail_after_verified=1)
    partial = interrupted.value.partial
    assert partial["schema_version"] == MIGRATION_SCHEMA_VERSION
    assert partial["complete"] is False
    assert partial["committed"] == 1
    assert partial["source_scan"] is False
    assert partial["directory_rewritten"] is False
    assert partial["empty_replacement"] is False
    first_digest = (paths["destination"] / partial["entries"][0]["ciphertext_name"]).read_bytes()
    resumed = _run(paths, directory, session, actor, (first_case, second_case), artifacts)
    assert resumed["status"] == "complete"
    assert resumed["complete"] is True
    assert resumed["committed"] == 2
    assert resumed["cleanup_performed"] is False
    assert resumed["recovery_retained"] is True
    assert resumed["limitations"] == LIMITATIONS
    assert (paths["destination"] / partial["entries"][0]["ciphertext_name"]).read_bytes() == first_digest
    by_case = {entry["case_id"]: entry for entry in resumed["entries"]}
    assert untouched.case_id not in by_case
    assert _open_entry(paths, session, by_case[first_case.case_id], first_case) == b"synthetic-one"
    assert _open_entry(paths, session, by_case[second_case.case_id], second_case) == b"synthetic-two"
    for entry, record in ((by_case[first_case.case_id], first_case), (by_case[second_case.case_id], second_case)):
        assert entry["owner_binding_preserved"] is True
        assert entry["principal_id"] == record.tenant_id
        assert entry["actor_principal_id"] == actor
        assert entry["actor_is_encrypted_owner"] is False
        assert entry["source_storage_version"] == NAMESPACED_CASE_VERSION
        assert entry["migration_schema_version"] == MIGRATION_SCHEMA_VERSION
    wrong = PrivateArtifactBinding(
        tenant_id=actor,
        case_id=first_case.case_id,
        artifact_kind="note",
        revision="1",
        principal_id=actor,
    )
    key_id, key = session.provider().resolve(
        PrivateArtifactBinding(
            tenant_id=first_case.tenant_id,
            case_id=first_case.case_id,
            artifact_kind="note",
            revision="1",
            principal_id=first_case.tenant_id,
        )
    )
    with pytest.raises(PrivateArtifactIntegrityError):
        open_private_artifact(
            (paths["destination"] / by_case[first_case.case_id]["ciphertext_name"]).read_bytes(),
            binding=wrong,
            key=key,
            expected_key_id=key_id,
        )
    journal = (paths["destination"] / "case_migration_journal.json").read_text(encoding="utf-8")
    assert PASSPHRASE not in journal
    assert key.hex() not in journal
    assert {path.name: path.read_bytes() for path in paths["cases"].iterdir() if path.is_file()} == directory_before
    assert first.read_bytes() == b"synthetic-one"
    assert decoy.read_bytes() == b"synthetic-untouched"
    again = _run(paths, directory, session, actor, (first_case, second_case), artifacts)
    assert again["committed"] == 2
    saved = by_case[first_case.case_id]
    assert (paths["destination"] / saved["ciphertext_name"]).read_bytes() == (
        paths["recovery"] / saved["recovery_name"]
    ).read_bytes()


def test_legacy_owner_binding_is_preserved(tmp_path: Path) -> None:
    paths = _dirs(tmp_path)
    directory, directory_key = _directory(paths["cases"])
    session = _session(paths["keys"])
    actor = "synthetic-legacy-owner"
    legacy_payload = json.dumps({"user_id": actor, "narrative": "synthetic-legacy"}).encode("utf-8")
    legacy_envelope = seal_private_artifact(
        legacy_payload,
        binding=legacy_owner_only_binding(actor),
        key=directory_key,
        key_id=DIRECTORY_KEY_ID,
    )
    legacy, opened = directory.adopt_owner_only_case(actor_principal_id=actor, envelope=legacy_envelope)
    assert opened["narrative"] == "synthetic-legacy"
    assert legacy.tenant_id == legacy.case_id == actor
    session.ensure_data_key(legacy.tenant_id, legacy.case_id)
    source = _file(paths["sources"] / "legacy.txt", b"synthetic-legacy-body")
    directory_before = {path.name: path.read_bytes() for path in paths["cases"].iterdir() if path.is_file()}
    result = _run(
        paths,
        directory,
        session,
        actor,
        legacy,
        [_artifact(legacy, source, kind="session", revision="session-v1")],
    )
    assert result["complete"] is True
    entry = result["entries"][0]
    assert entry["owner_binding_preserved"] is True
    assert entry["principal_id"] == actor
    assert entry["actor_is_encrypted_owner"] is True
    assert entry["source_storage_version"] == LEGACY_OWNER_ONLY_VERSION
    assert _open_entry(paths, session, entry, legacy) == b"synthetic-legacy-body"
    assert {path.name: path.read_bytes() for path in paths["cases"].iterdir() if path.is_file()} == directory_before
    assert source.read_bytes() == b"synthetic-legacy-body"


def test_cleanup_waits_for_recovery_evidence(tmp_path: Path) -> None:
    paths, directory, _, session, actor, case = _namespaced(tmp_path)
    source = _file(paths["sources"] / "body.txt", b"synthetic-cleanup-body")
    artifact = [_artifact(case, source, kind="note", revision="9")]
    seen = {}

    def _observe(evidence):
        seen["source"] = Path(evidence["sources_present"][0]).read_bytes()
        seen["recovery"] = Path(evidence["recovery_files"][0]).read_bytes()
        raise RuntimeError("retain-evidence")

    with pytest.raises(RuntimeError, match="retain-evidence"):
        _run(paths, directory, session, actor, case, artifact, cleanup=True, before_cleanup=_observe)
    assert seen["source"] == b"synthetic-cleanup-body"
    assert source.read_bytes() == b"synthetic-cleanup-body"
    binding = PrivateArtifactBinding(
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        artifact_kind="note",
        revision="9",
        principal_id=case.tenant_id,
    )
    key_id, key = session.provider().resolve(binding)
    assert open_private_artifact(seen["recovery"], binding=binding, key=key, expected_key_id=key_id) == b"synthetic-cleanup-body"
    finished = _run(paths, directory, session, actor, case, artifact, cleanup=True)
    assert finished["cleanup_performed"] is True
    assert finished["recovery_retained"] is True
    assert source.exists() is False
    assert open_private_artifact(
        (paths["recovery"] / finished["entries"][0]["recovery_name"]).read_bytes(),
        binding=binding,
        key=key,
        expected_key_id=key_id,
    ) == b"synthetic-cleanup-body"


def test_missing_key_foreign_actor_and_corrupt_destination_do_not_replace(tmp_path: Path) -> None:
    paths, directory, _, session, actor, case = _namespaced(tmp_path)
    source = _file(paths["sources"] / "kept.txt", b"synthetic-kept")
    artifact = [_artifact(case, source, kind="note", revision="3")]
    locked = UserOwnedKeySession(tmp_path / "other-keys")
    locked.create(protection="passphrase", passphrase="other-synthetic-passphrase")
    refused = _run(paths, directory, locked, actor, case, artifact)
    assert refused["status"] == "unauthorized_key"
    assert refused["empty_replacement"] is False
    assert refused["committed"] == 0
    assert list(paths["destination"].glob("*.bin")) == []
    assert source.read_bytes() == b"synthetic-kept"
    session.lock()
    locked_result = _run(paths, directory, session, actor, case, artifact)
    assert locked_result["status"] == "unlock_needed"
    assert locked_result["committed"] == 0
    session.unlock_passphrase(PASSPHRASE)
    stranger = "synthetic-stranger"
    with pytest.raises(CaseMigrationError) as foreign:
        _run(paths, directory, session, stranger, case, artifact)
    assert foreign.value.code == "missing_case"
    mismatched = dict(artifact[0])
    mismatched["principal_id"] = actor
    with pytest.raises(CaseMigrationError) as binding:
        _run(paths, directory, session, actor, case, [mismatched])
    assert binding.value.code == "owner_binding_mismatch"
    assert source.read_bytes() == b"synthetic-kept"
    done = _run(paths, directory, session, actor, case, artifact)
    assert done["complete"] is True
    target = paths["destination"] / done["entries"][0]["ciphertext_name"]
    blob = bytearray(target.read_bytes())
    blob[-1] ^= 0x01
    target.write_bytes(bytes(blob))
    os.chmod(target, 0o600)
    failed = _run(paths, directory, session, actor, case, artifact, cleanup=True)
    assert failed["status"] == "recoverable"
    assert failed["code"] == "readback_failed"
    assert failed["cleanup_performed"] is False
    assert source.read_bytes() == b"synthetic-kept"
    assert (paths["recovery"] / done["entries"][0]["recovery_name"]).is_file()
