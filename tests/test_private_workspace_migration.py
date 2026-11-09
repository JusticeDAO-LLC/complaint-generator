"""Private workspace migration stays inside the envelope boundary.

Synthetic complaints only. No live IPFS, provider calls, or user home data.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from applications.complaint_workspace import (
    ComplaintWorkspaceService,
    WorkspaceAccess,
    WorkspacePersistenceError,
    WorkspaceAuthorizationDenied,
    workspace_access_scope,
)
from complaint_generator.legacy_session_migration import (
    PrivateMigrationError,
    PrivateMigrationInterrupted,
    migrate_private_workspace,
)
from integrations.ipfs_datasets.draft_logic_pipeline import pin_proof_report_to_ipfs
from integrations.ipfs_datasets.graphs import persist_graph_snapshot
from integrations.private_storage import open_private_artifact, parse_private_envelope
from integrations.private_storage import PrivateArtifactBinding

SENTINEL = "SENTINEL-PRIV-DUR002-7f3a9c"
KEY_A = bytes(range(32))
KEY_B = bytes(range(32, 64))
KEY_A_ID = "case-key-a"
KEY_B_ID = "case-key-b"


class _HermeticBytes:
    measurement_label = "measured-hermetic"

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.seen: list[bytes] = []
        self._n = 0

    def add_bytes(self, data, pin=True):
        del pin
        blob = bytes(data)
        self.seen.append(blob)
        self._n += 1
        cid = f"bafyhermetic{self._n:04d}"
        self.blobs[cid] = blob
        return {"success": True, "cid": cid, "pinned": False}

    def cat(self, cid):
        return self.blobs[cid]

    def pin(self, cid):
        return {"success": True, "cid": cid, "pinned": True}


def _access(principal: str, case_id: str) -> WorkspaceAccess:
    return WorkspaceAccess.authenticated(principal, case_id=case_id)


def _artifact(root: Path, name: str, payload: bytes, *, tenant: str, case_id: str, kind: str, key: bytes, key_id: str, revision: str = "rev-1") -> dict:
    source = root / name
    source.write_bytes(payload)
    return {
        "tenant_id": tenant,
        "case_id": case_id,
        "principal_id": tenant,
        "artifact_kind": kind,
        "revision": revision,
        "source_path": source,
        "key": key,
        "key_id": key_id,
        "access": _access(tenant, case_id),
        "owner_record": {"owner": tenant, "case_id": case_id},
    }


def _scan(roots: list[Path], sentinel: str = SENTINEL) -> list[str]:
    hits: list[str] = []
    needle = sentinel.encode("utf-8")
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if sentinel in path.name:
                hits.append(str(path))
            if path.is_file() and not path.is_symlink():
                if needle in path.read_bytes():
                    hits.append(str(path))
    return hits


def test_migration_seals_every_class_and_resumes(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "legacy"
    dest = tmp_path / "private"
    catalog = tmp_path / "graph-catalog"
    cache = tmp_path / "cache"
    backups = tmp_path / "backups"
    logs = tmp_path / "logs"
    for path in (source, catalog, cache, backups, logs):
        path.mkdir()
    log_file = logs / "migration.log"
    log_file.write_text("migration start\n", encoding="utf-8")
    monkeypatch.setenv("COMPLAINT_GENERATOR_GRAPH_CATALOG", str(catalog))
    kinds = [
        "session", "answers", "attachment", "extracted-text", "assertion-envelope",
        "fact-graph", "rule-evaluation", "annotation", "draft", "proof-history",
        "theorem-source", "index", "backup-manifest",
    ]
    artifacts = []
    for tenant, case_id, key, key_id in (
        ("tenant-a", "case-a", KEY_A, KEY_A_ID),
        ("tenant-b", "case-b", KEY_B, KEY_B_ID),
    ):
        for kind in kinds:
            payload = json.dumps({
                "kind": kind,
                "tenant": tenant,
                "source_text": SENTINEL,
                "source_span": SENTINEL,
                "lean4": SENTINEL,
            }).encode("utf-8")
            artifacts.append(_artifact(
                source, f"{tenant}-{kind}.bin", payload,
                tenant=tenant, case_id=case_id, kind=kind, key=key, key_id=key_id,
            ))
    originals = {str(item["source_path"]): Path(item["source_path"]).read_bytes() for item in artifacts}
    with pytest.raises(PrivateMigrationInterrupted) as interrupted:
        migrate_private_workspace(
            source_root=source,
            destination_root=dest,
            artifacts=artifacts,
            fail_after_committed=1,
        )
    assert interrupted.value.partial["committed"] == 1
    for path, payload in originals.items():
        assert Path(path).read_bytes() == payload
    resumed = migrate_private_workspace(source_root=source, destination_root=dest, artifacts=artifacts)
    assert resumed["status"] == "complete"
    assert resumed["complete"] is True
    assert resumed["cleanup_performed"] is False
    manifest = json.loads((dest / "private_migration_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "complaint-private-migration/v1"
    assert len(manifest["entries"]) == len(artifacts)
    for entry in manifest["entries"]:
        assert set(entry) == {"artifact_ref", "ciphertext_name", "ciphertext_sha256", "readback", "status"}
        assert entry["readback"] == "verified"
        assert SENTINEL not in json.dumps(entry)
    assert _scan([dest, catalog, cache, backups, logs]) == []
    for path, payload in originals.items():
        assert Path(path).read_bytes() == payload
    again = migrate_private_workspace(source_root=source, destination_root=dest, artifacts=artifacts)
    assert again["status"] == "complete"
    assert again["committed"] == len(artifacts)


def test_locked_corrupt_owner_and_cleanup(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    dest = tmp_path / "private"
    snap = tmp_path / "snap"
    source.mkdir()
    snap.mkdir()
    artifact = _artifact(
        source, "session.json", f"answers {SENTINEL}".encode("utf-8"),
        tenant="tenant-a", case_id="case-a", kind="session", key=KEY_A, key_id=KEY_A_ID,
    )
    locked = dict(artifact)
    locked["locked"] = True
    locked["key"] = None
    before = Path(artifact["source_path"]).read_bytes()
    locked_result = migrate_private_workspace(source_root=source, destination_root=dest, artifacts=[locked])
    assert locked_result["status"] == "unlock_needed"
    assert Path(artifact["source_path"]).read_bytes() == before
    assert list(dest.glob("*.bin")) == []

    done = migrate_private_workspace(source_root=source, destination_root=dest, artifacts=[artifact])
    assert done["complete"] is True
    dest_file = next(dest.glob("*.bin"))
    sealed = dest_file.read_bytes()
    dest_file.write_bytes(sealed[:-1] + bytes([sealed[-1] ^ 0x01]))
    corrupt_dest = dest_file.read_bytes()
    corrupt = migrate_private_workspace(source_root=source, destination_root=dest, artifacts=[artifact])
    assert corrupt["status"] == "recoverable"
    assert dest_file.read_bytes() == corrupt_dest
    assert Path(artifact["source_path"]).read_bytes() == before
    dest_file.write_bytes(sealed)

    wrong = dict(artifact)
    wrong["key"] = KEY_B
    wrong["key_id"] = KEY_B_ID
    preserved = dest_file.read_bytes()
    rejected = migrate_private_workspace(source_root=source, destination_root=dest, artifacts=[wrong])
    assert rejected["status"] == "recoverable"
    assert dest_file.read_bytes() == preserved
    assert Path(artifact["source_path"]).read_bytes() == before

    mismatched = dict(artifact)
    mismatched["owner_record"] = {"owner": "other", "case_id": "case-a"}
    mismatched["source_path"] = source / "tenant-b-looking-name.json"
    Path(mismatched["source_path"]).write_bytes(before)
    owner = migrate_private_workspace(
        source_root=source, destination_root=dest, artifacts=[mismatched],
    )
    assert owner["complete"] is False
    assert Path(mismatched["source_path"]).read_bytes() == before

    link = snap / "hardlink"
    os.link(artifact["source_path"], link)
    copy = snap / "copy"
    copy.write_bytes(before)
    copied = dict(artifact)
    copied["copy_paths"] = [copy]
    outside = tmp_path / "outside-link"
    os.link(artifact["source_path"], outside)
    blocked = migrate_private_workspace(
        source_root=source, destination_root=dest, artifacts=[copied],
        snapshot_roots=[snap], cleanup=True,
    )
    assert blocked["cleanup_complete"] is False
    assert Path(artifact["source_path"]).read_bytes() == before
    assert outside.read_bytes() == before
    outside.unlink()
    cleaned = migrate_private_workspace(
        source_root=source, destination_root=dest, artifacts=[copied],
        snapshot_roots=[snap], cleanup=True,
    )
    assert cleaned["cleanup_performed"] is True
    assert cleaned["cleanup_complete"] is True
    assert not Path(artifact["source_path"]).exists()
    assert not link.exists()
    assert not copy.exists()
    assert _scan([dest, snap]) == []

    manifest = dest / "private_migration_manifest.json"
    manifest.write_text("{", encoding="utf-8")
    fresh = source / "fresh.json"
    fresh.write_bytes(b"keep-me")
    broken = dict(artifact)
    broken["source_path"] = fresh
    with pytest.raises(PrivateMigrationError) as caught:
        migrate_private_workspace(source_root=source, destination_root=dest, artifacts=[broken])
    assert caught.value.code == "malformed_manifest"
    assert fresh.read_bytes() == b"keep-me"


def test_workspace_session_graph_proof_and_export(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    access = _access("tenant-a", "case-a")
    service = ComplaintWorkspaceService(root)
    service.initialize_private_keys(protection="passphrase", passphrase="synthetic service passphrase")
    service.ensure_private_case_key("tenant-a", "case-a")
    with workspace_access_scope(access):
        missing = service._load_state("tenant-a")
        assert missing["missing_new_session"] is True
        assert missing["session_readable"] is True
        missing["intake_answers"] = {"harm": SENTINEL}
        missing["draft"] = {"body": SENTINEL}
        service._save_state(missing)
        session_file = next(root.glob("p-*.json"))
        assert SENTINEL.encode("utf-8") not in session_file.read_bytes()
        assert session_file.read_bytes().startswith(b"CGPE")
        reloaded = service._load_state("tenant-a")
        assert reloaded["intake_answers"]["harm"] == SENTINEL
        sealed = session_file.read_bytes()

        with workspace_access_scope(WorkspaceAccess.trusted_local()):
            service.lock_private_keys()
        with pytest.raises(WorkspacePersistenceError) as locked:
            service._load_state("tenant-a")
        assert locked.value.public_status == "unlock_needed"
        with pytest.raises(WorkspacePersistenceError):
            service._save_state({"user_id": "tenant-a", "case_id": "case-a", "intake_answers": {}})
        assert session_file.read_bytes() == sealed
        with workspace_access_scope(WorkspaceAccess.trusted_local()):
            service.unlock_private_keys(passphrase="synthetic service passphrase")

        session_file.write_bytes(b"not-json-and-not-envelope")
        with pytest.raises(WorkspacePersistenceError) as corrupt:
            service._load_state("tenant-a")
        assert corrupt.value.public_status == "recoverable"
        assert corrupt.value.code == "corrupt_session"
        with pytest.raises(WorkspacePersistenceError):
            service._save_state({"user_id": "tenant-a", "case_id": "case-a", "intake_answers": {"harm": "empty"}})
        assert session_file.read_bytes() == b"not-json-and-not-envelope"
        session_file.write_bytes(sealed)

        backend = _HermeticBytes()
        catalog = tmp_path / "catalog"
        catalog.mkdir()
        monkeypatch.setenv("COMPLAINT_GENERATOR_GRAPH_CATALOG", str(catalog))
        graph = persist_graph_snapshot(
            {"entities": [{"text": SENTINEL, "source_text": SENTINEL}], "relationships": []},
            graph_id="case-graph",
            private_context={
                "access": access,
                "tenant_id": "tenant-a",
                "case_id": "case-a",
                "principal_id": "tenant-a",
                "key": KEY_A,
                "key_id": KEY_A_ID,
                "revision": "fact-graph-1",
                "backend": backend,
                "destination_dir": tmp_path / "graphs",
            },
        )
        assert graph["private_indexing"] == "unsupported"
        assert graph["plaintext_catalog"] is False
        assert graph["verified"] is True
        report = pin_proof_report_to_ipfs(
            {
                "proof_status": "blocked",
                "errors": [SENTINEL],
                "theorem_export": {"lean4": f"theorem sentinel : {SENTINEL}", "coq": SENTINEL},
                "source_text": SENTINEL,
            },
            claim_id="claim-1",
            private_context={
                "access": access,
                "tenant_id": "tenant-a",
                "case_id": "case-a",
                "principal_id": "tenant-a",
                "key": KEY_A,
                "key_id": KEY_A_ID,
                "revision": "proof-1",
                "backend": backend,
            },
        )
        assert report["private_artifact"] is True
        assert report["verified"] is True
        assert report["plaintext_exported"] is False
        materials = service.persist_private_case_materials(
            "tenant-a",
            {
                "answers": f"answers {SENTINEL}".encode("utf-8"),
                "assertion-envelope": json.dumps({"source_text": SENTINEL, "source_span": SENTINEL}).encode("utf-8"),
                "rule-evaluation": f"rule {SENTINEL}".encode("utf-8"),
                "annotation": f"note {SENTINEL}".encode("utf-8"),
                "draft": f"draft {SENTINEL}".encode("utf-8"),
                "index": f"index {SENTINEL}".encode("utf-8"),
                "backup-manifest": f"backup {SENTINEL}".encode("utf-8"),
                "attachment": f"file {SENTINEL}".encode("utf-8"),
                "extracted-text": f"text {SENTINEL}".encode("utf-8"),
            },
            case_id="case-a",
            backend=backend,
        )
        assert materials["written"] is True
        memory = service.ingest_memory_evidence(
            "tenant-a",
            files=[{"filename": "note.txt", "data": f"upload {SENTINEL}".encode("utf-8")}],
            backend=backend,
        )
        assert memory["plaintext_disk"] is False
        assert memory["imported"][0]["extraction"]["method"] == "ephemeral-memory"
        filing = tmp_path / "filing" / "complaint.txt"
        with workspace_access_scope(WorkspaceAccess.trusted_local()):
            exported = service.export_readable_filing(
                "tenant-a",
                destination=filing,
                protection="user_chosen_plaintext",
                case_id="case-a",
                content=f"filing {SENTINEL}".encode("utf-8"),
            )
            assert exported["automatic"] is False
            assert exported["protection"] == "user_chosen_plaintext"
            assert filing.read_text(encoding="utf-8").endswith(SENTINEL)
            with pytest.raises(WorkspacePersistenceError):
                service.export_readable_filing(
                    "tenant-a",
                    destination=root / "hidden.txt",
                    protection="user_chosen_plaintext",
                    content=b"nope",
                )
        assert _scan([root, catalog, tmp_path / "graphs"]) == []
        assert all(SENTINEL.encode("utf-8") not in blob for blob in backend.seen)
        opened = open_private_artifact(
            backend.seen[0],
            binding=PrivateArtifactBinding(
                tenant_id="tenant-a",
                case_id="case-a",
                artifact_kind="fact-graph",
                revision="fact-graph-1",
                principal_id="tenant-a",
            ),
            key=KEY_A,
            expected_key_id=KEY_A_ID,
        )
        assert SENTINEL.encode("utf-8") in opened
        assert parse_private_envelope(backend.seen[0])["key_id"] == KEY_A_ID


def test_migration_rejects_source_outside_explicit_root(tmp_path):
    source = tmp_path / "source"
    outside = tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    artifact = _artifact(outside, "foreign.txt", b"synthetic outside source", tenant="tenant-a", case_id="case-a", kind="session", key=KEY_A, key_id=KEY_A_ID)
    with pytest.raises(PrivateMigrationError) as caught:
        migrate_private_workspace(source_root=source, destination_root=tmp_path / "destination", artifacts=[artifact])
    assert caught.value.code == "path_outside_source"
    assert Path(artifact["source_path"]).read_bytes() == b"synthetic outside source"


def test_migration_cleanup_preserves_unrelated_declared_copy(tmp_path):
    source = tmp_path / "source"
    snapshots = tmp_path / "snapshots"
    source.mkdir()
    snapshots.mkdir()
    artifact = _artifact(source, "original.txt", b"synthetic original", tenant="tenant-a", case_id="case-a", kind="session", key=KEY_A, key_id=KEY_A_ID)
    unrelated = snapshots / "unrelated.txt"
    unrelated.write_bytes(b"different synthetic record")
    artifact["copy_paths"] = [unrelated]
    result = migrate_private_workspace(source_root=source, destination_root=tmp_path / "destination", artifacts=[artifact], snapshot_roots=[snapshots], cleanup=True)
    assert result["cleanup_performed"] is False
    assert Path(artifact["source_path"]).read_bytes() == b"synthetic original"
    assert unrelated.read_bytes() == b"different synthetic record"


def test_deliberate_encrypted_filing_actually_seals_bytes(tmp_path):
    service = ComplaintWorkspaceService(tmp_path / "workspace")
    service.initialize_private_keys(protection="passphrase", passphrase="synthetic correct horse battery staple")
    service.ensure_private_case_key("tenant-a", "case-a")
    destination = tmp_path / "filing" / "encrypted.bin"
    result = service.export_readable_filing("tenant-a", case_id="case-a", destination=destination, protection="user_chosen_encrypted", content=b"synthetic confidential filing")
    assert result["protection"] == "user_chosen_encrypted"
    assert destination.read_bytes().startswith(b"CGPE")
    assert b"synthetic confidential filing" not in destination.read_bytes()
    binding = PrivateArtifactBinding(tenant_id="tenant-a", case_id="case-a", artifact_kind="filing-export", revision="filing-export-v1", principal_id="tenant-a")
    key_id, key = service.private_key_provider().resolve(binding)
    assert open_private_artifact(destination.read_bytes(), binding=binding, key=key, expected_key_id=key_id) == b"synthetic confidential filing"


def _genuine_service(root: Path, user="tenant-a", case="case-a"):
    service = ComplaintWorkspaceService(root)
    service.initialize_private_keys(protection="passphrase", passphrase="synthetic workspace protection phrase")
    service.ensure_private_case_key(user, case)
    return service


def test_missing_keys_never_creates_plaintext_session(tmp_path):
    root = tmp_path / "workspace"
    service = ComplaintWorkspaceService(root)
    with workspace_access_scope(_access("tenant-a", "case-a")):
        with pytest.raises(WorkspacePersistenceError) as load:
            service.get_session("tenant-a")
        assert load.value.public_status == "unlock_needed"
        with pytest.raises(WorkspacePersistenceError) as save:
            service._save_state({"user_id": "tenant-a", "case_id": "case-a", "intake_answers": {"harm": SENTINEL}})
        assert save.value.public_status == "unlock_needed"
    assert list(root.glob("p-*")) == []
    assert _scan([root]) == []


def test_genuine_vault_resume_lock_and_owner_guards(tmp_path):
    root = tmp_path / "workspace"
    service = _genuine_service(root)
    with workspace_access_scope(_access("tenant-a", "case-a")):
        state = service._load_state("tenant-a")
        state["intake_answers"] = {"harm": SENTINEL}
        service._save_state(state)
        receipt = service.remember_private_reference("tenant-a", case_id="case-a", cid="synthetic-ciphertext-reference")
        assert receipt["at_rest_protection"] == "private_envelope"
    original = next(root.glob("p-*.json")).read_bytes()
    fresh = ComplaintWorkspaceService(root)
    with workspace_access_scope(_access("tenant-a", "case-a")):
        with pytest.raises(WorkspacePersistenceError) as locked:
            fresh.get_session("tenant-a")
        assert locked.value.code == "unlock_needed"
    fresh.unlock_private_keys(passphrase="synthetic workspace protection phrase")
    with workspace_access_scope(_access("tenant-a", "case-a")):
        assert fresh.get_session("tenant-a")["session"]["intake_answers"]["harm"] == SENTINEL
    with workspace_access_scope(_access("tenant-b", "case-b")):
        with pytest.raises(WorkspaceAuthorizationDenied):
            fresh.get_session("tenant-a")
    before_locked = next(root.glob("p-*.json")).read_bytes()
    fresh.lock_private_keys()
    with workspace_access_scope(_access("tenant-a", "case-a")):
        with pytest.raises(WorkspacePersistenceError):
            fresh._save_state(state)
    assert next(root.glob("p-*.json")).read_bytes() == before_locked
    assert original.startswith(b"CGPE")
    assert _scan([root]) == []


def test_session_staged_readback_failure_preserves_existing(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    service = _genuine_service(root)
    with workspace_access_scope(_access("tenant-a", "case-a")):
        state = service._load_state("tenant-a")
        state["intake_answers"] = {"harm": SENTINEL}
        service._save_state(state)
        path = next(root.glob("p-*.json"))
        before = path.read_bytes()
        read = service._read_bytes_nofollow
        def faulty_read(relative):
            return b"invalid staged ciphertext" if relative.endswith(".tmp") else read(relative)
        monkeypatch.setattr(service, "_read_bytes_nofollow", faulty_read)
        state["intake_answers"]["harm"] = "synthetic replacement"
        with pytest.raises(WorkspacePersistenceError) as failed:
            service._save_state(state)
        assert failed.value.code == "readback_mismatch"
        assert path.read_bytes() == before
        assert list(root.glob("*.tmp")) == []


def test_explicit_owned_legacy_migration_preserves_original_and_resumes(tmp_path):
    root = tmp_path / "workspace"
    service = _genuine_service(root)
    legacy = root / "tenant-a.json"
    original = json.dumps({"user_id": "tenant-a", "case_id": "case-a", "intake_answers": {"harm": SENTINEL}}).encode()
    legacy.write_bytes(original)
    with workspace_access_scope(_access("tenant-a", "case-a")):
        with pytest.raises(WorkspacePersistenceError) as required:
            service.get_session("tenant-a")
        assert required.value.code == "migration_required"
        assert list(root.glob("p-*.json")) == []
        result = service.migrate_legacy_private_session("tenant-a")
        assert result["complete"] and result["private_session_verified"]
        assert result["legacy_plaintext_retained"] and result["source_bytes_preserved"]
        assert not result["cleanup_performed"]
        assert service.get_session("tenant-a")["session"]["intake_answers"]["harm"] == SENTINEL
        assert service.migrate_legacy_private_session("tenant-a")["complete"]
    assert legacy.read_bytes() == original
    successor = next(root.glob("p-*.json.cgpe"))
    assert successor.read_bytes().startswith(b"CGPE")
    assert SENTINEL.encode() not in successor.read_bytes()
    assert _scan([root / "private-migrations", root / "private-keys"]) == []


@pytest.mark.parametrize("invalid", [b"[]", b"null", b"{", b"not json"])
def test_existing_invalid_session_cannot_be_replaced(tmp_path, invalid):
    service = _genuine_service(tmp_path / "workspace")
    from applications.complaint_workspace import namespace_filename
    path = tmp_path / "workspace" / namespace_filename("tenant-a")
    path.write_bytes(invalid)
    with workspace_access_scope(_access("tenant-a", "case-a")):
        for operation in (lambda: service.get_session("tenant-a"), lambda: service._save_state({"user_id": "tenant-a", "case_id": "case-a", "intake_answers": {"harm": SENTINEL}})):
            with pytest.raises(WorkspacePersistenceError) as refused:
                operation()
            assert refused.value.code == "corrupt_session"
            assert path.read_bytes() == invalid


def test_contained_files_are_authenticated_bound_and_locked(tmp_path):
    root = tmp_path / "workspace"
    service = _genuine_service(root)
    with workspace_access_scope(_access("tenant-a", "case-a")):
        result = service.write_contained_workspace_file("tenant-a", "evidence/note.bin", SENTINEL.encode())
        assert result["at_rest_protection"] == "private_envelope"
        assert service.read_contained_workspace_file("tenant-a", "evidence/note.bin") == SENTINEL.encode()
        service.write_contained_workspace_file("tenant-a", "evidence/other.bin", b"other synthetic record")
    paths = list((root / "private-files").rglob("*.bin"))
    note = next(path for path in paths if path.name == "note.bin")
    other = next(path for path in paths if path.name == "other.bin")
    before = note.read_bytes()
    assert before.startswith(b"CGPE") and SENTINEL.encode() not in before
    note.write_bytes(other.read_bytes())
    with workspace_access_scope(_access("tenant-a", "case-a")):
        for operation in (lambda: service.read_contained_workspace_file("tenant-a", "evidence/note.bin"), lambda: service.write_contained_workspace_file("tenant-a", "evidence/note.bin", b"replacement")):
            with pytest.raises(WorkspacePersistenceError) as refused:
                operation()
            assert refused.value.code == "authentication_failed"
        assert note.read_bytes() == other.read_bytes()
    note.write_bytes(before)
    with workspace_access_scope(_access("tenant-b", "case-b")):
        with pytest.raises(WorkspaceAuthorizationDenied):
            service.read_contained_workspace_file("tenant-a", "evidence/note.bin")
    service.lock_private_keys()
    with workspace_access_scope(_access("tenant-a", "case-a")):
        with pytest.raises(WorkspacePersistenceError) as locked:
            service.read_contained_workspace_file("tenant-a", "evidence/note.bin")
        assert locked.value.public_status == "unlock_needed"
    assert note.read_bytes() == before
    assert _scan([root]) == []


@pytest.mark.parametrize("relative", ["../escape", "/absolute", "nested/../escape", "nested\\escape"])
def test_contained_traversal_rejected_without_outside_effect(tmp_path, relative):
    service = _genuine_service(tmp_path / "workspace")
    outside = tmp_path / "escape"
    outside.write_bytes(b"synthetic unchanged")
    with workspace_access_scope(_access("tenant-a", "case-a")):
        with pytest.raises(WorkspaceAuthorizationDenied):
            service.write_contained_workspace_file("tenant-a", relative, SENTINEL.encode())
    assert outside.read_bytes() == b"synthetic unchanged"


def test_contained_symlink_rejected_before_outside_read_or_write(tmp_path):
    service = _genuine_service(tmp_path / "workspace")
    with workspace_access_scope(_access("tenant-a", "case-a")):
        service.write_contained_workspace_file("tenant-a", "note.bin", b"initial")
        note = next((tmp_path / "workspace" / "private-files").rglob("note.bin"))
        note.unlink()
        outside = tmp_path / "outside"
        outside.write_bytes(b"synthetic outside unchanged")
        note.symlink_to(outside)
        for operation in (lambda: service.read_contained_workspace_file("tenant-a", "note.bin"), lambda: service.write_contained_workspace_file("tenant-a", "note.bin", SENTINEL.encode())):
            with pytest.raises(WorkspaceAuthorizationDenied):
                operation()
    assert outside.read_bytes() == b"synthetic outside unchanged"


def test_authenticated_caller_cannot_export_to_host_path(tmp_path):
    service = _genuine_service(tmp_path / "workspace")
    destination = tmp_path / "host-file"
    destination.write_bytes(b"synthetic host unchanged")
    with workspace_access_scope(_access("tenant-a", "case-a")):
        with pytest.raises(WorkspaceAuthorizationDenied):
            service.export_readable_filing("tenant-a", destination=destination, protection="user_chosen_plaintext", content=SENTINEL.encode())
    assert destination.read_bytes() == b"synthetic host unchanged"


def test_owned_local_artifact_reports_local_only(tmp_path):
    service = _genuine_service(tmp_path / "workspace")
    with workspace_access_scope(_access("tenant-a", "case-a")):
        result = service.persist_private_case_materials("tenant-a", {"draft": SENTINEL.encode()}, case_id="case-a")
    artifact = result["artifacts"]["draft"]
    assert artifact["verified"] is True
    assert artifact["stored_local"] is True
    assert artifact["uploaded"] is False
    assert artifact["pinned"] is False
    assert artifact["replicated"] is False
    assert artifact["receipt"]["network_durable"] is False
    assert _scan([tmp_path / "workspace"]) == []


def test_migration_rejects_all_owners_before_reading_any_source(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    good = _artifact(source, "owned.txt", b"synthetic owned", tenant="tenant-a", case_id="case-a", kind="session", key=KEY_A, key_id=KEY_A_ID)
    wrong = {**good, "owner_record": {"owner": "tenant-b", "case_id": "case-a"}}
    import complaint_generator.legacy_session_migration as migration
    def forbidden(_artifact):
        pytest.fail("source was opened before all owners were admitted")
    monkeypatch.setattr(migration, "_artifact_bytes", forbidden)
    destination = tmp_path / "destination"
    result = migrate_private_workspace(source_root=source, destination_root=destination, artifacts=[good, wrong])
    assert not result["complete"]
    assert result["status"] == "owner_mismatch"
    assert not destination.exists()


def test_migration_failure_never_restores_over_concurrent_source_edit(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    artifact = _artifact(source, "original.txt", b"synthetic original", tenant="tenant-a", case_id="case-a", kind="session", key=KEY_A, key_id=KEY_A_ID)
    import integrations.private_storage as private
    seal = private.seal_private_artifact
    def external_edit(*args, **kwargs):
        Path(artifact["source_path"]).write_bytes(b"synthetic concurrent edit")
        return seal(*args, **kwargs)
    monkeypatch.setattr(private, "seal_private_artifact", external_edit)
    result = migrate_private_workspace(source_root=source, destination_root=tmp_path / "destination", artifacts=[artifact], cleanup=True)
    assert result["complete"] is False
    assert result["code"] == "source_changed"
    assert result["source_bytes_preserved"] is False
    assert result["cleanup_performed"] is False
    assert Path(artifact["source_path"]).read_bytes() == b"synthetic concurrent edit"


@pytest.mark.parametrize("change", ["version", "duplicate", "path", "digest", "readback"])
def test_migration_strict_manifest_preserves_invalid_bytes(tmp_path, change):
    source = tmp_path / "source"
    source.mkdir()
    artifact = _artifact(source, "original.txt", b"synthetic original", tenant="tenant-a", case_id="case-a", kind="session", key=KEY_A, key_id=KEY_A_ID)
    destination = tmp_path / "destination"
    migrate_private_workspace(source_root=source, destination_root=destination, artifacts=[artifact])
    manifest = destination / "private_migration_manifest.json"
    payload = json.loads(manifest.read_bytes())
    if change == "version":
        payload["schema_version"] = True
    elif change == "duplicate":
        payload["entries"].append(payload["entries"][0])
    elif change == "path":
        payload["entries"][0]["ciphertext_name"] = "../outside"
    elif change == "digest":
        payload["entries"][0]["ciphertext_sha256"] = "not a digest"
    else:
        payload["entries"][0]["readback"] = "not verified"
    invalid = json.dumps(payload).encode()
    manifest.write_bytes(invalid)
    with pytest.raises(PrivateMigrationError) as refused:
        migrate_private_workspace(source_root=source, destination_root=destination, artifacts=[artifact])
    assert refused.value.code == "malformed_manifest"
    assert manifest.read_bytes() == invalid
    assert Path(artifact["source_path"]).read_bytes() == b"synthetic original"


def test_encrypted_successor_probe_io_error_is_typed_and_preserved(tmp_path, monkeypatch):
    service = _genuine_service(tmp_path / "workspace")
    read = service._read_bytes_nofollow
    def failed_probe(relative):
        if relative.endswith(".json.cgpe"):
            raise OSError("synthetic IO marker must remain private")
        return read(relative)
    monkeypatch.setattr(service, "_read_bytes_nofollow", failed_probe)
    with workspace_access_scope(_access("tenant-a", "case-a")):
        with pytest.raises(WorkspacePersistenceError) as refused:
            service.get_session("tenant-a")
        assert refused.value.code == "read_error"
        assert refused.value.public_status == "unavailable"
        assert "synthetic IO marker" not in str(refused.value)
    assert list((tmp_path / "workspace").glob("p-*")) == []


def test_service_proof_caller_passes_live_private_provider(tmp_path, monkeypatch):
    service = _genuine_service(tmp_path / "workspace")
    report = {"source_text": SENTINEL, "theorem_export": {"lean4": SENTINEL}}
    monkeypatch.setattr(service, "get_draft_proof_report", lambda *_args, **_kwargs: {"status": "ok", "proof_report": report})
    import integrations.ipfs_datasets.draft_logic_pipeline as pipeline
    import integrations.ipfs_datasets.storage as storage
    seen = []
    def private_adapter(proof_report, *, claim_id, private_context):
        # This isolates the caller seam; the graph/proof adapter is independently
        # qualified on its corrective child and again on the combined source.
        assert proof_report == report and claim_id == "synthetic-claim"
        assert "key" not in private_context and "key_id" not in private_context
        assert private_context["pin_content"] is False
        seen.append(storage.store_automatic_private_artifact(json.dumps(proof_report).encode(), artifact_kind="proof-history", **private_context))
        return {"verified": seen[0]["verified"], "private_artifact": True}
    monkeypatch.setattr(pipeline, "pin_proof_report_to_ipfs", private_adapter)
    with workspace_access_scope(_access("tenant-a", "case-a")):
        result = service.pin_draft_proof_report("tenant-a", claim_id="synthetic-claim")
        assert result["pin_result"]["verified"] is True
    assert seen[0]["stored_local"] and not seen[0]["uploaded"]
    assert _scan([tmp_path / "workspace"]) == []


@pytest.mark.parametrize("escape", ["source_symlink", "outside_copy"])
def test_migration_admits_all_paths_before_reading_sources(tmp_path, monkeypatch, escape):
    source = tmp_path / "source"
    source.mkdir()
    artifact = _artifact(source, "original.txt", b"synthetic original", tenant="tenant-a", case_id="case-a", kind="session", key=KEY_A, key_id=KEY_A_ID)
    outside = tmp_path / "outside"
    outside.write_bytes(b"synthetic outside unchanged")
    if escape == "source_symlink":
        Path(artifact["source_path"]).unlink()
        Path(artifact["source_path"]).symlink_to(outside)
    else:
        artifact["copy_paths"] = [outside]
    import complaint_generator.legacy_session_migration as migration
    monkeypatch.setattr(migration, "_artifact_bytes", lambda *_args: pytest.fail("source read before path admission"))
    with pytest.raises(PrivateMigrationError) as refused:
        migrate_private_workspace(source_root=source, destination_root=tmp_path / "destination", artifacts=[artifact], cleanup=True)
    assert refused.value.code in {"unsafe_path", "path_outside_source"}
    assert outside.read_bytes() == b"synthetic outside unchanged"
    assert not (tmp_path / "destination").exists()


@pytest.mark.parametrize("failure", ["ciphertext_file", "ciphertext_directory", "existing_manifest_file"])
def test_migration_sync_failure_never_claims_completion_or_erases_sources(tmp_path, monkeypatch, failure):
    import stat
    source = tmp_path / "source"
    source.mkdir()
    artifact = _artifact(source, "original.txt", b"synthetic original", tenant="tenant-a", case_id="case-a", kind="session", key=KEY_A, key_id=KEY_A_ID)
    destination = tmp_path / "destination"
    manifest = destination / "private_migration_manifest.json"
    previous_manifest = None
    if failure == "existing_manifest_file":
        assert migrate_private_workspace(source_root=source, destination_root=destination, artifacts=[artifact])["complete"]
        previous_manifest = manifest.read_bytes()
    sync = os.fsync
    def failed_sync(fd):
        directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        if directory == (failure == "ciphertext_directory"):
            raise OSError("synthetic fsync fault")
        return sync(fd)
    monkeypatch.setattr(os, "fsync", failed_sync)
    result = migrate_private_workspace(source_root=source, destination_root=destination, artifacts=[artifact], cleanup=True)
    assert result["status"] == "recoverable"
    assert result["complete"] is False
    assert result["manifest_durable"] is False
    assert result["cleanup_performed"] is False
    assert result["source_bytes_preserved"] is True
    assert Path(artifact["source_path"]).read_bytes() == b"synthetic original"
    if failure == "ciphertext_directory":
        assert result["code"] == "publication_indeterminate"
        assert result["publication_indeterminate"] is True
        assert len(list(destination.glob("*.bin"))) == 1
    else:
        assert result["code"] == "publication_failed"
        assert result["publication_indeterminate"] is False
    if previous_manifest is not None:
        assert manifest.read_bytes() == previous_manifest
    elif failure == "ciphertext_file":
        assert list(destination.glob("*.bin")) == []
    assert not list(destination.glob("*.tmp"))


def test_migration_completion_syncs_ciphertext_and_manifest_names(tmp_path, monkeypatch):
    import stat
    source = tmp_path / "source"
    source.mkdir()
    artifact = _artifact(source, "original.txt", b"synthetic original", tenant="tenant-a", case_id="case-a", kind="session", key=KEY_A, key_id=KEY_A_ID)
    sync = os.fsync
    observed = []
    def measured_sync(fd):
        observed.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        return sync(fd)
    monkeypatch.setattr(os, "fsync", measured_sync)
    result = migrate_private_workspace(source_root=source, destination_root=tmp_path / "destination", artifacts=[artifact])
    assert result["complete"] and result["manifest_durable"]
    assert observed.count("file") >= 2
    assert observed.count("directory") >= 2


def test_migration_rerun_preserves_newer_authenticated_session(tmp_path):
    root = tmp_path / "workspace"
    service = _genuine_service(root)
    legacy = root / "tenant-a.json"
    original = json.dumps({"user_id": "tenant-a", "case_id": "case-a", "intake_answers": {"harm": "synthetic old answer"}}).encode()
    legacy.write_bytes(original)
    with workspace_access_scope(_access("tenant-a", "case-a")):
        assert service.migrate_legacy_private_session("tenant-a")["complete"]
        state = service._load_state("tenant-a")
        state["intake_answers"]["harm"] = SENTINEL
        service._save_state(state)
        successor = next(root.glob("p-*.json.cgpe"))
        before = successor.read_bytes()
        result = service.migrate_legacy_private_session("tenant-a")
        assert result["complete"] and result["existing_private_preserved"]
        assert successor.read_bytes() == before
        assert service._load_state("tenant-a")["intake_answers"]["harm"] == SENTINEL
    assert legacy.read_bytes() == original


def test_migration_rejects_untrusted_bound_identity_before_source_read(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    artifact = _artifact(source, "original.txt", b"synthetic original", tenant="tenant-a", case_id="case-a", kind="session", key=KEY_A, key_id=KEY_A_ID)
    artifact["access"] = WorkspaceAccess("unauthenticated", "tenant-a", "case-a")
    import complaint_generator.legacy_session_migration as migration
    monkeypatch.setattr(migration, "_artifact_bytes", lambda *_args: pytest.fail("untrusted source read"))
    destination = tmp_path / "destination"
    result = migrate_private_workspace(source_root=source, destination_root=destination, artifacts=[artifact])
    assert result["status"] == "owner_mismatch" and not result["complete"]
    assert not destination.exists()
    assert Path(artifact["source_path"]).read_bytes() == b"synthetic original"
