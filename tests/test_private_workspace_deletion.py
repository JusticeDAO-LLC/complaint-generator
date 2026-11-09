"""Scoped case deletion, unpin receipts, and key destruction."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

from applications.complaint_workspace import ComplaintWorkspaceService
from complaint_generator.workspace import delete_private_case, reset_session
from integrations.private_storage import (
    PrivateKeyMaterialError,
    PrivatePortabilityError,
    PrivateRevisionInterrupted,
    UserOwnedKeySession,
    bind_shared_legal_artifact,
    read_case_tombstone,
    record_managed_replica,
    stage_private_workspace,
    write_case_local_private_file,
)
from integrations.private_storage import export_encrypted_workspace, import_encrypted_workspace

PASSPHRASE = "sentinel-passphrase-do-not-persist"
RECOVERY = "sentinel-recovery-do-not-persist"
TENANT = "tenant-a"
OTHER_TENANT = "tenant-b"
CASE = "case-a"
OTHER_CASE = "case-b"
PRINCIPAL = "principal-a"


class _Replica:
    def __init__(self, deletion_status: str) -> None:
        self.deletion_status = deletion_status
        self.unpin_calls = 0
        self.delete_calls = 0

    def unpin(self, *, cid: str, timeout_seconds: float | None = None) -> dict:
        del cid, timeout_seconds
        self.unpin_calls += 1
        return {"status": "unpinned"}

    def request_deletion(self, *, cid: str, timeout_seconds: float | None = None) -> dict:
        del cid, timeout_seconds
        self.delete_calls += 1
        return {"status": self.deletion_status}


def _session(tmp_path: Path) -> tuple[UserOwnedKeySession, Path]:
    store = tmp_path / "keys"
    session = UserOwnedKeySession(store)
    session.create(protection="passphrase", passphrase=PASSPHRASE)
    return session, store


def _seed_two_cases(tmp_path: Path, session: UserOwnedKeySession) -> Path:
    repository = tmp_path / "repository"
    shared = b"shared-statute-text"
    bind_shared_legal_artifact(repository, tenant_id=TENANT, case_id=CASE, name="statute", payload=shared)
    bind_shared_legal_artifact(repository, tenant_id=OTHER_TENANT, case_id=OTHER_CASE, name="statute", payload=shared)
    write_case_local_private_file(
        repository, tenant_id=TENANT, case_id=CASE, kind="ciphertext", name="case.frame", payload=b"cipher-a"
    )
    write_case_local_private_file(
        repository, tenant_id=TENANT, case_id=CASE, kind="cache", name="cache.bin", payload=b"cache-a"
    )
    write_case_local_private_file(
        repository, tenant_id=TENANT, case_id=CASE, kind="temp", name="temp.bin", payload=b"temp-a"
    )
    write_case_local_private_file(
        repository, tenant_id=OTHER_TENANT, case_id=OTHER_CASE, kind="ciphertext", name="case.frame", payload=b"cipher-b"
    )
    record_managed_replica(repository, tenant_id=TENANT, case_id=CASE, cid="bafy-exclusive", provider_id="managed")
    record_managed_replica(repository, tenant_id=TENANT, case_id=CASE, cid="bafy-shared", provider_id="managed")
    record_managed_replica(repository, tenant_id=OTHER_TENANT, case_id=OTHER_CASE, cid="bafy-shared", provider_id="managed")
    session.ensure_data_key(TENANT, CASE)
    session.ensure_data_key(OTHER_TENANT, OTHER_CASE)
    stage_private_workspace(
        repository,
        session,
        tenant_id=TENANT,
        case_id=CASE,
        principal_id=PRINCIPAL,
        revision="rev-a",
        complaint=b"complaint-a",
        fact_graph=b"graph-a",
        proof=b"proof-a",
    )
    return repository


def test_scoped_cleanup_preserves_other_case_and_shared_source(tmp_path: Path) -> None:
    session, _store = _session(tmp_path)
    repository = _seed_two_cases(tmp_path, session)
    provider = _Replica("deleted")
    other_key = session.lookup_data_key(OTHER_TENANT, OTHER_CASE, session._data_keys[(OTHER_TENANT, OTHER_CASE)][0])
    receipt = delete_private_case(
        repository,
        session,
        tenant_id=TENANT,
        case_id=CASE,
        policy="destroy_case_keys",
        providers={"managed": provider},
    )
    steps = [step["step"] for step in receipt["steps"]]
    assert steps == [
        "remove_case_references",
        "delete_local_ciphertext_cache_temp",
        "unpin_managed_replicas",
        "request_remote_deletion",
        "destroy_case_keys",
    ]
    assert receipt["encryption_key_destroyed"] is True
    assert receipt["universal_erasure"] is False
    assert receipt["public_ipfs_erased"] is False
    assert "public IPFS" in receipt["external_replica_limitation"]
    assert any(row.get("kind") == "public_ipfs" and row.get("erased") is False for row in receipt["residual_replicas"])
    scope = repository / "deletion-scopes"
    case_dirs = list(scope.iterdir())
    assert len(case_dirs) == 2
    assert not any((path / "ciphertext").exists() and any((path / "ciphertext").iterdir()) for path in case_dirs if (path / "ciphertext" / "case.frame").exists() and (path / "ciphertext" / "case.frame").read_bytes() == b"cipher-a")
    preserved = [path for path in case_dirs if (path / "ciphertext" / "case.frame").exists()]
    assert len(preserved) == 1
    assert preserved[0].joinpath("ciphertext", "case.frame").read_bytes() == b"cipher-b"
    shared_files = list((repository / "shared-legal").iterdir())
    assert len(shared_files) == 1
    assert shared_files[0].read_bytes() == b"shared-statute-text"
    assert session.lookup_data_key(OTHER_TENANT, OTHER_CASE, session._data_keys[(OTHER_TENANT, OTHER_CASE)][0]) == other_key
    assert provider.unpin_calls == 1
    left = receipt["unpin_managed_replicas"]["left_in_place"]
    assert any(row["cid"] == "bafy-shared" for row in left)


def test_interrupted_deletion_resumes_and_second_call_is_idempotent(tmp_path: Path) -> None:
    session, _store = _session(tmp_path)
    repository = _seed_two_cases(tmp_path, session)
    provider = _Replica("pending")
    with pytest.raises(PrivateRevisionInterrupted) as caught:
        delete_private_case(
            repository,
            session,
            tenant_id=TENANT,
            case_id=CASE,
            policy="destroy_case_keys",
            providers={"managed": provider},
            crash_at="local_deleted",
        )
    assert caught.value.boundary == "local_deleted"
    assert read_case_tombstone(repository, TENANT, CASE) is None
    assert session.lookup_data_key(TENANT, CASE, session._data_keys[(TENANT, CASE)][0]) is not None
    resumed = delete_private_case(
        repository,
        session,
        tenant_id=TENANT,
        case_id=CASE,
        policy="destroy_case_keys",
        providers={"managed": provider},
    )
    assert resumed["resumed"] is True
    assert resumed["status"] == "completed"
    assert resumed["encryption_key_destroyed"] is True
    assert resumed["pending_remote_removals"]
    assert resumed["universal_erasure"] is False
    calls_after_resume = provider.delete_calls
    again = delete_private_case(
        repository,
        session,
        tenant_id=TENANT,
        case_id=CASE,
        policy="destroy_case_keys",
        providers={"managed": provider},
    )
    assert again["idempotent"] is True
    assert again["status"] == "completed"
    assert provider.delete_calls == calls_after_resume
    assert provider.unpin_calls == 1


def test_deleted_key_is_inaccessible_and_tombstone_blocks_recovery(tmp_path: Path) -> None:
    session, store = _session(tmp_path)
    repository = tmp_path / "repository"
    stage_private_workspace(
        repository,
        session,
        tenant_id=TENANT,
        case_id=CASE,
        principal_id=PRINCIPAL,
        revision="rev-a",
        complaint=b"complaint-a",
        fact_graph=b"graph-a",
        proof=b"proof-a",
    )
    export_dir = tmp_path / "export"
    recovery = tmp_path / "recovery.cgpe"
    export_encrypted_workspace(
        repository,
        export_dir,
        recovery,
        session,
        tenant_id=TENANT,
        case_id=CASE,
        principal_id=PRINCIPAL,
        recovery_passphrase=RECOVERY,
    )
    key_id = session._data_keys[(TENANT, CASE)][0]
    delete_private_case(
        repository,
        session,
        tenant_id=TENANT,
        case_id=CASE,
        policy="destroy_case_keys",
    )
    assert session.lookup_data_key(TENANT, CASE, key_id) is None
    with pytest.raises(PrivateKeyMaterialError) as key_error:
        session.ensure_data_key(TENANT, CASE)
    assert key_error.value.code == "case_key_destroyed"
    with pytest.raises(PrivatePortabilityError) as blocked:
        import_encrypted_workspace(
            repository,
            export_dir,
            recovery,
            store,
            tenant_id=TENANT,
            case_id=CASE,
            principal_id=PRINCIPAL,
            recovery_passphrase=RECOVERY,
        )
    assert blocked.value.code == "case_key_destroyed"
    tombstone = read_case_tombstone(repository, TENANT, CASE)
    assert tombstone is not None
    assert tombstone["public_ipfs_erased"] is False
    assert tombstone["universal_erasure"] is False


def test_unreachable_remote_removal_is_reported_without_claiming_erasure(tmp_path: Path) -> None:
    session, _store = _session(tmp_path)
    repository = _seed_two_cases(tmp_path, session)
    provider = _Replica("unreachable")
    receipt = delete_private_case(
        repository,
        session,
        tenant_id=TENANT,
        case_id=CASE,
        policy="retain_keys",
        providers={"managed": provider},
    )
    assert receipt["encryption_key_destroyed"] is False
    assert receipt["recovery_path_destroyed"] is False
    assert receipt["request_remote_deletion"]["status"] == "unreachable"
    assert receipt["unreachable_remote_removals"]
    assert receipt["universal_erasure"] is False
    assert receipt["public_ipfs_erased"] is False
    assert session.lookup_data_key(TENANT, CASE, session._data_keys[(TENANT, CASE)][0]) is not None
    with pytest.raises(PrivatePortabilityError) as blocked:
        stage_private_workspace(
            repository,
            session,
            tenant_id=TENANT,
            case_id=CASE,
            principal_id=PRINCIPAL,
            revision="rev-again",
            complaint=b"x",
            fact_graph=b"y",
            proof=b"z",
        )
    assert blocked.value.code == "tombstoned"


def test_legal_hold_and_workspace_need_refuse_deletion(tmp_path: Path) -> None:
    session, _store = _session(tmp_path)
    repository = _seed_two_cases(tmp_path, session)
    held = delete_private_case(
        repository,
        session,
        tenant_id=TENANT,
        case_id=CASE,
        policy="destroy_case_keys",
        legal_hold=True,
    )
    assert held["status"] == "refused"
    assert held["code"] == "legal_hold"
    assert held["encryption_key_destroyed"] is False
    needed = delete_private_case(
        repository,
        session,
        tenant_id=TENANT,
        case_id=CASE,
        policy="retain_keys",
        workspace_required=True,
    )
    assert needed["status"] == "refused"
    assert needed["code"] == "workspace_required"
    assert session._data_keys[(TENANT, CASE)][0]


def test_normal_reset_does_not_destroy_keys(tmp_path: Path) -> None:
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    created = service.ensure_private_case_key(TENANT, TENANT)
    reset = reset_session(TENANT, service=service)
    assert reset["session"]["intake_answers"] == {}
    assert reset["encryption_key_destroyed"] is False
    assert reset["recovery_path_destroyed"] is False
    assert reset["private_retention"]["key_destruction"] == "not_performed"
    assert reset["private_retention"]["irreversible_recovery_path_destroyed"] is False
    reloaded = UserOwnedKeySession(service._private_key_directory())
    reloaded.unlock_passphrase(PASSPHRASE)
    assert reloaded._data_keys[(TENANT, TENANT)][0] == created["data_key_id"]
    assert reloaded._case_was_destroyed(TENANT, TENANT) is False
