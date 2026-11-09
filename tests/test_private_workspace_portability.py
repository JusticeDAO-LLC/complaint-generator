"""Encrypted workspace export, recovery import, and crash-safe key rotation."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

from integrations.private_storage import (
    DATA_ROTATION_PHASES,
    PrivateArtifactIntegrityError,
    PrivatePortabilityError,
    PrivateRevisionInterrupted,
    UNRECOVERED_KEY_EXPLANATION,
    UserOwnedKeySession,
    WRAP_ROTATION_PHASES,
    read_private_workspace_generation,
    stage_private_workspace,
)
from complaint_generator.workspace import (
    export_encrypted_workspace,
    import_encrypted_workspace,
    revoke_retained_keys,
    rotate_data_key,
    rotate_wrapping_key,
)

PASSPHRASE = "sentinel-passphrase-do-not-persist"
RECOVERY = "sentinel-recovery-do-not-persist"
NEW_WRAP = "sentinel-new-wrap-do-not-persist"
TENANT = "tenant-a"
CASE = "case-a"
PRINCIPAL = "principal-a"
REVISION = "rev-7"
COMPLAINT = b"synthetic-complaint-revision"
GRAPH = b"synthetic-fact-graph-revision"
PROOF = b"synthetic-proof-revision"


def _digest_tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    found = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            found[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def _stage(tmp_path: Path, name: str = "case"):
    store = tmp_path / name / "keys"
    repository = tmp_path / name / "repository"
    session = UserOwnedKeySession(store)
    session.create(protection="passphrase", passphrase=PASSPHRASE)
    staged = stage_private_workspace(
        repository,
        session,
        tenant_id=TENANT,
        case_id=CASE,
        principal_id=PRINCIPAL,
        revision=REVISION,
        complaint=COMPLAINT,
        fact_graph=GRAPH,
        proof=PROOF,
    )
    return session, store, repository, staged


def _payload(opened: dict) -> tuple:
    return opened["revision"], opened["complaint"], opened["fact_graph"], opened["proof"]


def test_export_manifest_and_fresh_process_restore(tmp_path: Path) -> None:
    session, _store, repository, staged = _stage(tmp_path)
    export_dir = tmp_path / "export"
    recovery = tmp_path / "recovery" / "case.cgpe"
    master = session._master
    assert master is not None
    with pytest.raises(Exception):
        export_encrypted_workspace(
            repository, export_dir, export_dir / "nested.cgpe", session,
            tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, recovery_passphrase=RECOVERY,
        )
    receipt = export_encrypted_workspace(
        repository, export_dir, recovery, session,
        tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, recovery_passphrase=RECOVERY,
    )
    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["manifest_version"] == 1
    assert manifest["revision"] == staged["revision"] == REVISION
    assert manifest["roles"] == ["complaint", "fact_graph", "proof"]
    assert manifest["recovery_included"] is False
    assert manifest["unwrapped_master_included"] is False
    assert receipt["recovery_separated"] is True
    assert receipt["unwrapped_master_included"] is False
    frame = (export_dir / "ciphertext.frame").read_bytes()
    assert hashlib.sha256(frame).hexdigest() == manifest["ciphertext_sha256"]
    assert master not in frame
    assert _b64(master) not in (export_dir / "manifest.json").read_bytes()
    recovery_bytes = recovery.read_bytes()
    assert master not in recovery_bytes
    assert b"master_key" not in recovery_bytes
    assert export_dir.resolve() not in recovery.resolve().parents

    out = tmp_path / "restored.json"
    child = """
import hashlib, json, sys
from pathlib import Path
from integrations.private_storage import import_encrypted_workspace
recovery_passphrase, store_passphrase = sys.stdin.read().splitlines()[:2]
store, repository, export_dir, recovery_path, tenant, case_id, principal, destination = sys.argv[1:9]
restored = import_encrypted_workspace(
    repository, export_dir, recovery_path, store,
    tenant_id=tenant, case_id=case_id, principal_id=principal,
    recovery_passphrase=recovery_passphrase, store_passphrase=store_passphrase,
)
Path(destination).write_text(json.dumps({
    "revision": restored["revision"],
    "complaint": hashlib.sha256(restored["complaint"]).hexdigest(),
    "fact_graph": hashlib.sha256(restored["fact_graph"]).hexdigest(),
    "proof": hashlib.sha256(restored["proof"]).hexdigest(),
    "keys_reconstructed": restored["keys_reconstructed"],
}))
"""
    completed = subprocess.run(
        [
            sys.executable, "-c", child,
            str(tmp_path / "fresh-keys"), str(tmp_path / "fresh-repository"),
            str(export_dir), str(recovery), TENANT, CASE, PRINCIPAL, str(out),
        ],
        input=f"{RECOVERY}\n{PASSPHRASE}\n",
        text=True,
        check=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
    )
    assert completed.returncode == 0
    restored = json.loads(out.read_text(encoding="utf-8"))
    assert restored == {
        "revision": REVISION,
        "complaint": hashlib.sha256(COMPLAINT).hexdigest(),
        "fact_graph": hashlib.sha256(GRAPH).hexdigest(),
        "proof": hashlib.sha256(PROOF).hexdigest(),
        "keys_reconstructed": False,
    }
    fresh = UserOwnedKeySession(tmp_path / "fresh-keys")
    fresh.unlock_passphrase(PASSPHRASE)
    opened = read_private_workspace_generation(
        tmp_path / "fresh-repository", fresh,
        tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL,
    )
    assert _payload(opened) == (REVISION, COMPLAINT, GRAPH, PROOF)


def test_wrong_passphrase_and_missing_recovery_do_not_reset(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    session, store, repository, _staged = _stage(tmp_path)
    export_dir = tmp_path / "export"
    recovery = tmp_path / "recovery.cgpe"
    caplog.set_level(logging.INFO, logger="integrations.private_storage.portability")
    export_encrypted_workspace(
        repository, export_dir, recovery, session,
        tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, recovery_passphrase=RECOVERY,
    )
    assert session._master is not None
    assert _b64(session._master).decode("ascii") not in caplog.text
    assert session._master.hex() not in caplog.text
    before_repo = _digest_tree(repository)
    before_store = _digest_tree(store)
    before_export = _digest_tree(export_dir)
    with pytest.raises(PrivatePortabilityError) as wrong:
        import_encrypted_workspace(
            repository, export_dir, recovery, store,
            tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL,
            recovery_passphrase="wrong-passphrase", store_passphrase="unused",
        )
    assert wrong.value.public_state()["data_reset"] is False
    assert wrong.value.public_state()["keys_reconstructed"] is False
    assert UNRECOVERED_KEY_EXPLANATION in wrong.value.message
    assert "retry_passphrase" in wrong.value.actions
    assert _digest_tree(repository) == before_repo
    assert _digest_tree(store) == before_store
    assert _digest_tree(export_dir) == before_export
    with pytest.raises(PrivatePortabilityError) as missing:
        import_encrypted_workspace(
            repository, export_dir, tmp_path / "missing.cgpe", tmp_path / "other-keys",
            tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL,
            recovery_passphrase=RECOVERY, store_passphrase=PASSPHRASE,
        )
    assert missing.value.code == "recovery_key_missing"
    assert UNRECOVERED_KEY_EXPLANATION in missing.value.message
    assert missing.value.public_state()["data_reset"] is False
    assert not (tmp_path / "other-keys").exists()
    assert _digest_tree(repository) == before_repo


@pytest.mark.parametrize("phase", WRAP_ROTATION_PHASES)
def test_wrapping_rotation_crash_keeps_a_readable_generation(tmp_path: Path, phase: str) -> None:
    session, store, repository, _staged = _stage(tmp_path, phase)
    frame_before = (repository / "replica-ledger" / "primary.frame").read_bytes()
    key_before = session._data_keys[(TENANT, CASE)][0]
    try:
        state = rotate_wrapping_key(
            session, NEW_WRAP, policy="revoke_after_verified_migration", crash_at=phase,
        )
    except PrivateRevisionInterrupted as exc:
        assert exc.boundary == phase
        state = {"rotation_phase": phase}
    else:
        assert phase == "committed"
        assert state["operation"] == "rewrap"
        assert state["reencrypt"] is False
        assert state["revoked"] is False
        assert state["previous_wrapping_retained"] is True
    fresh = UserOwnedKeySession(store)
    if phase == "committed":
        fresh.unlock_passphrase(NEW_WRAP)
        retained = UserOwnedKeySession(store)
        retained.unlock_passphrase(PASSPHRASE)
    else:
        fresh.unlock_passphrase(PASSPHRASE)
        with pytest.raises(PrivateArtifactIntegrityError):
            UserOwnedKeySession(store).unlock_passphrase(NEW_WRAP)
    opened = read_private_workspace_generation(
        repository, fresh, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL,
    )
    assert _payload(opened) == (REVISION, COMPLAINT, GRAPH, PROOF)
    assert opened["data_key_id"] == key_before
    assert (repository / "replica-ledger" / "primary.frame").read_bytes() == frame_before
    journal = (store / "rotation-wrapping.json").read_bytes()
    assert session._master not in journal
    assert state["rotation_phase"] == phase


@pytest.mark.parametrize("phase", DATA_ROTATION_PHASES)
def test_data_rotation_crash_keeps_a_readable_generation(tmp_path: Path, phase: str) -> None:
    session, store, repository, _staged = _stage(tmp_path, "data-" + phase)
    frame_before = (repository / "replica-ledger" / "primary.frame").read_bytes()
    key_before = session._data_keys[(TENANT, CASE)][0]
    try:
        state = rotate_data_key(
            session, TENANT, CASE, repository, PRINCIPAL, policy="retain", crash_at=phase,
        )
    except PrivateRevisionInterrupted as exc:
        assert exc.boundary == phase
        state = {"rotation_phase": phase, "reencrypt": True}
    else:
        assert state["operation"] == "reencrypt"
        assert state["reencrypt"] is True
        assert state["data_key_changed"] is True
        assert state["previous_data_key_retained"] is True
        assert state["revoked"] is False
    fresh = UserOwnedKeySession(store)
    fresh.unlock_passphrase(PASSPHRASE)
    opened = read_private_workspace_generation(
        repository, fresh, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL,
    )
    assert _payload(opened) == (REVISION, COMPLAINT, GRAPH, PROOF)
    primary = (repository / "replica-ledger" / "primary.frame").read_bytes()
    if phase == "committed":
        assert opened["data_key_id"] != key_before
        assert primary != frame_before
        assert fresh._retained_data_keys[(TENANT, CASE)]
    else:
        assert opened["data_key_id"] == key_before
        assert primary == frame_before
    assert state["reencrypt"] is True


def test_revocation_requires_verified_migration_and_keeps_recovery_file(tmp_path: Path) -> None:
    session, store, repository, _staged = _stage(tmp_path, "revoke")
    rotate_wrapping_key(session, NEW_WRAP, policy="retain")
    rotate_data_key(session, TENANT, CASE, repository, PRINCIPAL, policy="retain")
    export_dir = tmp_path / "migrated-export"
    recovery = tmp_path / "migrated-recovery.cgpe"
    export_encrypted_workspace(
        repository, export_dir, recovery, session,
        tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, recovery_passphrase=RECOVERY,
    )
    recovery_bytes = recovery.read_bytes()
    with pytest.raises(PrivatePortabilityError) as unproven:
        revoke_retained_keys(
            session, TENANT, CASE, repository,
            policy="revoke_after_verified_migration",
            verified_backup_migration=False,
            export_dir=export_dir,
            recovery_path=recovery,
        )
    assert unproven.value.code == "revocation_requires_verified_migration"
    assert recovery.read_bytes() == recovery_bytes
    UserOwnedKeySession(store).unlock_passphrase(PASSPHRASE)
    with pytest.raises(PrivatePortabilityError) as only_path:
        revoke_retained_keys(
            session, TENANT, CASE, repository,
            policy="retain",
            verified_backup_migration=True,
            export_dir=export_dir,
            recovery_path=recovery,
        )
    assert only_path.value.code == "retention_policy"
    revoked = revoke_retained_keys(
        session, TENANT, CASE, repository,
        policy="revoke_after_verified_migration",
        verified_backup_migration=True,
        export_dir=export_dir,
        recovery_path=recovery,
    )
    assert revoked["revoked"] is True
    assert revoked["only_recovery_path_erased"] is False
    assert recovery.read_bytes() == recovery_bytes
    with pytest.raises(PrivateArtifactIntegrityError):
        UserOwnedKeySession(store).unlock_passphrase(PASSPHRASE)
    fresh = UserOwnedKeySession(store)
    fresh.unlock_passphrase(NEW_WRAP)
    opened = read_private_workspace_generation(
        repository, fresh, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL,
    )
    assert _payload(opened) == (REVISION, COMPLAINT, GRAPH, PROOF)
    retained_frame = next((repository / "replica-ledger" / "generations").glob("*.frame"))
    assert retained_frame.is_file()


def test_cli_export_receipt_omits_unwrapped_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    session, store, repository, _staged = _stage(tmp_path, "cli")
    session.lock()
    export_dir = tmp_path / "cli-export"
    recovery = tmp_path / "cli-recovery.cgpe"
    prompts = iter([PASSPHRASE, RECOVERY])
    import applications.complaint_workspace as workspace

    monkeypatch.setattr(workspace, "_SESSION_DIR", tmp_path / "isolated-cli-workspace")
    from complaint_generator import cli

    monkeypatch.setattr(cli, "_prompt", lambda _label: next(prompts))
    cli.workspace_export(
        str(store), TENANT, CASE, PRINCIPAL, str(repository), str(export_dir), str(recovery),
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "export"
    assert payload["unwrapped_master_included"] is False
    assert payload["recovery_separated"] is True
    assert "master_key" not in payload
    monkeypatch.setattr(sys, "argv", ["complaint", "workspace-export", "--passphrase", "secret"])
    with pytest.raises(SystemExit):
        cli.workspace_export(str(store), TENANT, CASE, PRINCIPAL, str(repository), str(export_dir), str(recovery))


def _b64(secret: bytes) -> bytes:
    import base64
    return base64.b64encode(secret)
