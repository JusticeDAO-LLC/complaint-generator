"""Explicit single-case migration of synthetic legacy private hook artifacts.

No test is skipped. The migration does not scan sessions or other trees.
A mode bit or local copy is not encryption or durability.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService, WorkspacePersistenceError
from integrations.private_storage import (
    LEGACY_HOOK_ARTIFACT_CLASS,
    commit_legacy_hook_migration,
    legacy_hook_migration_claim,
    open_legacy_hook_artifact,
    preflight_legacy_hook_migration,
)
from tests.mgnd_fixtures import CASE_LABELS, PASSPHRASE, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_OWNER = "synthetic-owner"


def _access(case_id: str):
    from applications.complaint_workspace import WorkspaceAccess

    return WorkspaceAccess.trusted_local(_OWNER, case_id)


def _payload(case) -> bytes:
    marker = case.narrative.evidence_markers[0].marker_id if case.narrative.evidence_markers else case.label
    return f"LEGACY-HOOK-{case.case_id}-{marker}".encode("utf-8")


def _preimage(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _key(seed: bytes) -> tuple[str, bytes]:
    material = hashlib.sha256(b"legacy-hook-key\x00" + seed).digest()
    return "legacy-hook-key", material


def _files(root: Path) -> dict[str, bytes]:
    found = {}
    if not root.exists():
        return found
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            found[str(path)] = path.read_bytes()
    return found


def test_catalog_preflight_and_commit_are_single_case(tmp_path):
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    committed = []
    for case in cases:
        payload = _payload(case)
        assert payload
        source = tmp_path / case.label / "legacy-hook.bin"
        source.parent.mkdir()
        source.write_bytes(payload)
        destination = tmp_path / case.label / "sealed"
        preimage = _preimage(payload)
        key_id, key = _key(case.case_id.encode("utf-8"))
        access = _access(case.case_id)
        if not case.storage_available:
            blocked = destination
            blocked.write_bytes(b"not-a-directory")
            receipt = commit_legacy_hook_migration(
                source,
                source_preimage=preimage,
                destination=blocked,
                access=access,
                tenant_id=_OWNER,
                case_id=case.case_id,
                principal_id=_OWNER,
                revision="legacy-hook-1",
                retention_policy="retain",
                key=key,
                key_id=key_id,
            )
            assert receipt["status"] == "unavailable"
            assert receipt["encrypted"] is False
            assert receipt["encryption_established"] is False
            assert receipt["network_durable"] is False
            assert receipt["automatic_scan"] is False
            assert source.read_bytes() == payload
            assert blocked.read_bytes() == b"not-a-directory"
            continue
        preview = preflight_legacy_hook_migration(
            source,
            source_preimage=preimage,
            destination=destination,
            access=access,
            tenant_id=_OWNER,
            case_id=case.case_id,
            principal_id=_OWNER,
            revision="legacy-hook-1",
            retention_policy="retain",
            key=key,
            key_id=key_id,
        )
        assert preview["status"] == "preflight"
        assert preview["pending"] is True
        assert preview["encrypted"] is False
        assert preview["encryption_established"] is False
        assert preview["pending_items"][0]["pending"] == "encryption"
        assert preview["destination_binding"]["artifact_class"] == LEGACY_HOOK_ARTIFACT_CLASS
        assert preview["destination_binding"]["case_id"] == case.case_id
        assert preview["source_preimage"] == preimage
        assert not destination.exists()
        os.chmod(source, 0o700)
        copied = tmp_path / case.label / "local-copy.bin"
        copied.write_bytes(source.read_bytes())
        claim = legacy_hook_migration_claim(mode_private=True, local_copy=True)
        assert claim["encrypted"] is False
        assert claim["durable"] is False
        assert claim["mode_bits_establish_encryption"] is False
        assert claim["local_copy_establishes_encryption"] is False
        assert claim["local_copy_establishes_durability"] is False
        receipt = commit_legacy_hook_migration(
            source,
            source_preimage=preimage,
            destination=destination,
            access=access,
            tenant_id=_OWNER,
            case_id=case.case_id,
            principal_id=_OWNER,
            revision="legacy-hook-1",
            retention_policy="retain",
            key=key,
            key_id=key_id,
        )
        assert receipt["status"] == "committed"
        assert receipt["encrypted"] is True
        assert receipt["encryption_established"] is True
        assert receipt["verified_commit"] is True
        assert receipt["pending_items"] == []
        assert receipt["plaintext_retired"] is False
        assert receipt["plaintext_retirement"] == "retained"
        assert receipt["network_durable"] is False
        assert receipt["durable"] is False
        assert receipt["single_case"] is True
        assert receipt["automatic_scan"] is False
        assert source.read_bytes() == payload
        opened = open_legacy_hook_artifact(
            destination,
            access=access,
            tenant_id=_OWNER,
            case_id=case.case_id,
            principal_id=_OWNER,
            revision="legacy-hook-1",
            key=key,
            key_id=key_id,
        )
        assert opened["data"] == payload
        assert opened["network_durable"] is False
        stored = b"".join(path.read_bytes() for path in destination.rglob("*") if path.is_file())
        assert payload not in stored
        assert legacy_hook_migration_claim(mode_private=True, local_copy=True, receipt=receipt)["durable"] is False
        committed.append(case.label)
    assert committed


def test_failures_preserve_source_and_last_head(tmp_path):
    case = next(item for item in meaningful_cases() if item.storage_available)
    payload = _payload(case)
    preimage = _preimage(payload)
    key_id, key = _key(b"primary")
    other_id, other = _key(b"other")
    access = _access(case.case_id)
    source = tmp_path / "source.bin"
    source.write_bytes(payload)
    destination = tmp_path / "sealed"
    common = dict(
        source_preimage=preimage,
        destination=destination,
        access=access,
        tenant_id=_OWNER,
        case_id=case.case_id,
        principal_id=_OWNER,
        revision="legacy-hook-1",
        key=key,
        key_id=key_id,
    )
    interrupted = commit_legacy_hook_migration(source, retention_policy="retain", interrupt_at="before_head", **common)
    assert interrupted["status"] == "interrupted"
    assert interrupted["encrypted"] is False
    assert interrupted["encryption_established"] is False
    assert source.read_bytes() == payload
    assert not (destination / "legacy-hook-head.json").exists()
    held = commit_legacy_hook_migration(source, retention_policy="retire_plaintext_after_verified_commit", interrupt_at="before_retire", **common)
    assert held["encrypted"] is True
    assert held["plaintext_retired"] is False
    assert held["pending_items"][0]["pending"] == "plaintext_retirement"
    assert source.read_bytes() == payload
    head = (destination / "legacy-hook-head.json").read_bytes()
    wrong = commit_legacy_hook_migration(
        source,
        source_preimage=preimage,
        destination=destination,
        access=access,
        tenant_id=_OWNER,
        case_id=case.case_id,
        principal_id=_OWNER,
        revision="legacy-hook-1",
        retention_policy="retire_plaintext_after_verified_commit",
        key=other,
        key_id=other_id,
    )
    assert wrong["code"] == "wrong_key"
    assert wrong["encryption_established"] is False
    assert wrong["plaintext_retired"] is False
    assert source.read_bytes() == payload
    assert (destination / "legacy-hook-head.json").read_bytes() == head
    source.write_bytes(payload + b"!")
    corrupt = commit_legacy_hook_migration(source, retention_policy="retire_plaintext_after_verified_commit", **common)
    assert corrupt["code"] == "corrupt_source"
    assert source.read_bytes() == payload + b"!"
    assert (destination / "legacy-hook-head.json").read_bytes() == head
    source.write_bytes(payload)
    link = tmp_path / "alias.bin"
    os.link(source, link)
    aliased = commit_legacy_hook_migration(source, retention_policy="retire_plaintext_after_verified_commit", **common)
    assert aliased["code"] == "aliased_source"
    assert source.read_bytes() == payload
    assert link.read_bytes() == payload
    assert (destination / "legacy-hook-head.json").read_bytes() == head
    link.unlink()
    pointer = tmp_path / "pointer.bin"
    pointer.symlink_to(source)
    pointed = commit_legacy_hook_migration(
        pointer,
        source_preimage=preimage,
        destination=destination,
        access=access,
        tenant_id=_OWNER,
        case_id=case.case_id,
        principal_id=_OWNER,
        revision="legacy-hook-1",
        retention_policy="retire_plaintext_after_verified_commit",
        key=key,
        key_id=key_id,
    )
    assert pointed["code"] == "aliased_source"
    assert source.read_bytes() == payload
    assert (destination / "legacy-hook-head.json").read_bytes() == head
    head_path = destination / "legacy-hook-head.json"
    head_path.write_bytes(b"{not-json")
    broken = commit_legacy_hook_migration(source, retention_policy="retire_plaintext_after_verified_commit", **common)
    assert broken["code"] == "corrupt_head"
    assert broken["last_valid_head_preserved"] is True
    assert source.read_bytes() == payload
    assert head_path.read_bytes() == b"{not-json"
    head_path.write_bytes(head)
    retired = commit_legacy_hook_migration(source, retention_policy="retire_plaintext_after_verified_commit", **common)
    assert retired["status"] == "committed"
    assert retired["plaintext_retired"] is True
    assert retired["plaintext_retirement"] == "retired"
    assert retired["encrypted_items"]
    assert not source.exists()
    opened = open_legacy_hook_artifact(
        destination,
        access=access,
        tenant_id=_OWNER,
        case_id=case.case_id,
        principal_id=_OWNER,
        revision="legacy-hook-1",
        key=key,
        key_id=key_id,
    )
    assert opened["data"] == payload
    assert payload not in (destination / "legacy-hook-head.json").read_bytes()


def test_workspace_commit_does_not_scan_or_rewrite_neighbors(tmp_path):
    case = next(item for item in meaningful_cases() if item.storage_available)
    other = next(item for item in meaningful_cases() if item.storage_available and item.case_id != case.case_id)
    locked = ComplaintWorkspaceService(tmp_path / "locked")
    source = tmp_path / "legacy-hook.bin"
    payload = _payload(case)
    source.write_bytes(payload)
    destination = tmp_path / "sealed"
    locked_receipt = locked.preflight_legacy_hook_artifact(
        _OWNER,
        source_path=source,
        source_preimage=_preimage(payload),
        destination=destination,
        revision="legacy-hook-1",
        case_id=case.case_id,
    )
    assert locked_receipt["status"] == "unavailable"
    assert locked_receipt["encrypted"] is False
    assert locked_receipt["automatic_scan"] is False
    assert source.read_bytes() == payload
    assert not destination.exists()

    opened = ComplaintWorkspaceService(tmp_path / "opened")
    created = opened.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    assert created.get("unlocked") is True or created.get("status") in {"available", "ready"}
    opened.unlock_private_keys(passphrase=PASSPHRASE)
    assert opened.ensure_private_case_key(_OWNER, case.case_id).get("data_key_id")
    session = opened._session_dir
    decoys = {
        session / "legacy-session.json": b'{"historical":"qualifier","secret":"do-not-migrate"}',
        session / "campaign-artifact.json": b'{"campaign":"untouched"}',
        session / "other-case-hook.bin": _payload(other),
    }
    for path, body in decoys.items():
        path.write_bytes(body)
    before = _files(session)
    preview = opened.preflight_legacy_hook_artifact(
        _OWNER,
        source_path=source,
        source_preimage=_preimage(payload),
        destination=destination,
        revision="legacy-hook-1",
        case_id=case.case_id,
        retention_policy="retain",
    )
    assert preview["status"] == "preflight"
    assert preview["encrypted"] is False
    assert preview["automatic_scan"] is False
    assert preview["rewrote_user_tree"] is False
    receipt = opened.commit_legacy_hook_artifact(
        _OWNER,
        source_path=source,
        source_preimage=_preimage(payload),
        destination=destination,
        revision="legacy-hook-1",
        case_id=case.case_id,
        retention_policy="retain",
    )
    assert receipt["status"] == "committed"
    assert receipt["encryption_established"] is True
    assert receipt["network_durable"] is False
    assert receipt["imported_sessions"] is False
    assert receipt["rewrote_campaign_artifacts"] is False
    assert receipt["rewrote_historical_qualifiers"] is False
    assert source.read_bytes() == payload
    after = _files(session)
    for path, body in decoys.items():
        assert after[str(path)] == body == before[str(path)]
    stored = b"".join(path.read_bytes() for path in destination.rglob("*") if path.is_file())
    assert payload not in stored
    with pytest.raises(WorkspacePersistenceError):
        opened.commit_legacy_hook_artifact(
            _OWNER,
            source_path=source,
            source_preimage="not-a-preimage",
            destination=destination,
            revision="legacy-hook-1",
            case_id=case.case_id,
            retention_policy="not-a-policy",
        )
