"""Cold reconstruction of encrypted workflow continuity.

Services and the wallet descriptor resume from the encrypted revision, not from
a browser cache. Missing keys, wrong key ids, tampered heads, interrupted
writes, and WAL recovery stay explicit. Durability proved here is local private
storage, not qualified remote storage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService, WorkspacePersistenceError
from integrations.private_storage import (
    PrivateRevisionInterrupted,
    _prefer_vendored_kit,
    reconstruct_workflow_continuity,
)

_prefer_vendored_kit()
from ipfs_kit_py.core.wal.coordinator import WALTransactionCrash

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

PASSPHRASE = "synthetic-workflow-passphrase-ux59"
OWNER = "owner-ux59"
CASE = "case-ux59"
SECRET = "synthetic-draft-sentence-ux59-not-a-cache"
OTHER_KEY = bytes(range(32))


def _workflow(text: str = SECRET, question: str = "q-pending") -> dict:
    return {
        "services": [{"service_id": "svc-evidence", "kind": "evidence", "label": "Evidence"}],
        "wallet": {"wallet_id": "wallet-owner", "key_id": "filled-by-store", "protection": "passphrase", "case_id": CASE},
        "pending_questions": [{"inquiry_id": question, "prompt": "Which date?"}],
        "evidence_annotations": [{"annotation_id": "an-1", "note": SECRET}],
        "evidence_links": [{"annotation_id": "an-1", "evidence_id": "ev-1"}],
        "source_context": {"source_id": "src-1", "citation": "synthetic statute section"},
        "draft": {"text": text, "revision": "3"},
        "correspondence": [{"message_id": "msg-1", "body": SECRET, "actor": "owner"}],
    }


def _open(root: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root)
    created = service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    assert created["unlocked"] is True
    ready = service.ensure_private_case_key(OWNER, CASE)
    assert ready["data_key_id"]
    return service


def _bound(service: ComplaintWorkspaceService, text: str = SECRET, question: str = "q-pending") -> dict:
    document = _workflow(text, question)
    _context, key_id, _key = service._joined_key(OWNER, CASE)
    document["wallet"]["key_id"] = key_id
    return document


def _crash(boundary: str):
    def inject(name: str, transaction_id: str | None = None) -> None:
        del transaction_id
        if name == boundary:
            raise WALTransactionCrash(name)

    return inject


def _assert_local(receipt: dict) -> None:
    durability = receipt["durability"]
    assert durability["durability_scope"] == "local_private"
    assert durability["local_durable"] is True
    assert durability["remote_durable"] is False
    assert durability["qualified_remote_storage"] is False
    assert durability["local_copy_establishes_remote_durability"] is False
    assert "not qualified remote storage" in durability["statement"]


def _assert_absent(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            assert SECRET.encode("utf-8") not in path.read_bytes()
            assert PASSPHRASE.encode("utf-8") not in path.read_bytes()


def test_cold_process_reconstructs_workflow_without_browser_cache(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    service = _open(root)
    sealed = service.seal_encrypted_workflow_continuity(OWNER, _bound(service), case_id=CASE)
    assert sealed["committed"] is True
    assert sealed["browser_cache_used"] is False
    assert sealed["empty_case_created"] is False
    assert sealed["network_pinned"] is False
    _assert_local(sealed)
    _assert_absent(root)

    cold = ComplaintWorkspaceService(root)
    cold._workflow_memory = {"services": [{"service_id": "from-memory"}]}
    browser = {"draft": {"text": "browser-cache-draft"}, "services": [{"service_id": "from-browser"}]}
    locked = cold.reconstruct_encrypted_workflow(OWNER, case_id=CASE, browser_cache=browser)
    assert locked["resumed"] is False
    assert locked["code"] == "missing_key"
    assert locked["empty_case_created"] is False
    assert locked["reconstructed_from_browser_cache"] is False
    assert SECRET not in json.dumps(locked)
    assert "from-browser" not in json.dumps(locked)

    unlocked = cold.unlock_private_keys(passphrase=PASSPHRASE)
    assert unlocked["unlocked"] is True
    resumed = cold.reconstruct_encrypted_workflow(OWNER, case_id=CASE, browser_cache=browser)
    assert resumed["resumed"] is True
    assert resumed["browser_cache_ignored"] is True
    assert resumed["reconstructed_from_browser_cache"] is False
    assert resumed["services"] == [{
        "service_id": "svc-evidence",
        "kind": "evidence",
        "label": "Evidence",
        "source": "encrypted_store",
    }]
    assert resumed["services"][0]["service_id"] != "from-browser"
    assert resumed["wallet"]["source"] == "encrypted_store"
    assert resumed["wallet"]["case_id"] == CASE
    assert resumed["wallet"]["wallet_id"] == "wallet-owner"
    assert resumed["wallet"]["key_id"] and resumed["wallet"]["key_id"] != sealed["wallet_binding"]
    assert resumed["pending_questions"][0]["inquiry_id"] == "q-pending"
    assert resumed["evidence_annotations"][0]["note"] == SECRET
    assert resumed["evidence_links"][0]["evidence_id"] == "ev-1"
    assert resumed["source_context"]["source_id"] == "src-1"
    assert resumed["draft"]["text"] == SECRET
    assert resumed["correspondence"][0]["message_id"] == "msg-1"
    _assert_local(resumed)
    assert cold._workflow_memory is None


def test_wrong_key_and_tampered_head_do_not_resume(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    service = _open(root)
    service.seal_encrypted_workflow_continuity(OWNER, _bound(service), case_id=CASE)
    _context, key_id, key = service._joined_key(OWNER, CASE)
    repository = service.workflow_continuity_repository(OWNER, CASE)

    wrong = reconstruct_workflow_continuity(
        repository,
        tenant_id=OWNER,
        case_id=CASE,
        principal_id=OWNER,
        key=OTHER_KEY,
        key_id="other-key-id",
        browser_cache={"draft": {"text": SECRET}},
    )
    assert wrong["resumed"] is False
    assert wrong["code"] == "wrong_key"
    assert wrong["draft"] is None
    assert SECRET not in json.dumps(wrong)

    presented_as_real_id = reconstruct_workflow_continuity(
        repository,
        tenant_id=OWNER,
        case_id=CASE,
        principal_id=OWNER,
        key=OTHER_KEY,
        key_id=key_id,
    )
    assert presented_as_real_id["resumed"] is False
    assert presented_as_real_id["code"] == "tampered_head"
    assert presented_as_real_id["services"] == []

    head = repository / "head.cgpe"
    original = head.read_bytes()
    flipped = bytearray(original)
    flipped[-1] ^= 0x01
    head.write_bytes(bytes(flipped))
    tampered = reconstruct_workflow_continuity(
        repository,
        tenant_id=OWNER,
        case_id=CASE,
        principal_id=OWNER,
        key=key,
        key_id=key_id,
    )
    assert tampered["resumed"] is False
    assert tampered["code"] == "tampered_head"
    assert tampered["empty_case_created"] is False
    assert tampered["durability"]["qualified_remote_storage"] is False
    assert tampered["durability"]["local_durable"] is False
    assert SECRET not in json.dumps(tampered)
    head.write_bytes(original)
    restored = reconstruct_workflow_continuity(
        repository,
        tenant_id=OWNER,
        case_id=CASE,
        principal_id=OWNER,
        key=key,
        key_id=key_id,
    )
    assert restored["resumed"] is True
    assert restored["draft"]["text"] == SECRET


def test_interrupted_write_and_wal_recovery_keep_the_last_committed_head(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    service = _open(root)
    first = service.seal_encrypted_workflow_continuity(
        OWNER, _bound(service, question="q-first"), case_id=CASE, transaction_id="tx-first", effect_id="ef-first",
    )
    assert first["committed"] is True

    with pytest.raises(PrivateRevisionInterrupted):
        service.seal_encrypted_workflow_continuity(
            OWNER,
            _bound(service, text="interrupted-draft-ux59", question="q-lost"),
            case_id=CASE,
            crash_injector=_crash("before_commit"),
            transaction_id="tx-lost",
            effect_id="ef-lost",
        )
    recovered = service.recover_encrypted_workflow(OWNER, case_id=CASE)
    assert recovered["wal_recovery"]["state"] == "compensated"
    assert recovered["resumed"] is True
    assert recovered["pending_questions"][0]["inquiry_id"] == "q-first"
    assert recovered["draft"]["text"] == SECRET
    assert "interrupted-draft-ux59" not in json.dumps(recovered)
    assert recovered["durability"]["qualified_remote_storage"] is False

    with pytest.raises(PrivateRevisionInterrupted):
        service.seal_encrypted_workflow_continuity(
            OWNER,
            _bound(service, text="committed-after-ack-ux59", question="q-second"),
            case_id=CASE,
            crash_injector=_crash("after_commit"),
            transaction_id="tx-acked",
            effect_id="ef-acked",
        )
    replayed = service.recover_encrypted_workflow(OWNER, case_id=CASE)
    assert replayed["wal_recovery"]["committed"] is True
    assert replayed["resumed"] is True
    assert replayed["pending_questions"][0]["inquiry_id"] == "q-second"
    assert replayed["draft"]["text"] == "committed-after-ack-ux59"
    assert replayed["evidence_links"][0]["annotation_id"] == "an-1"
    assert replayed["correspondence"][0]["actor"] == "owner"
    _assert_local(replayed)
    again = service.recover_encrypted_workflow(OWNER, case_id=CASE)
    assert again["wal_recovery"]["replayed"] == 0
    assert again["draft"]["text"] == "committed-after-ack-ux59"


def test_locked_wallet_recovery_does_not_create_a_case(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    service = _open(root)
    service.seal_encrypted_workflow_continuity(OWNER, _bound(service), case_id=CASE)
    service.lock_private_keys()
    refused = service.recover_encrypted_workflow(OWNER, case_id=CASE)
    assert refused["code"] == "missing_key"
    assert refused["resumed"] is False
    assert refused["empty_case_created"] is False
    assert refused["durability"]["remote_durable"] is False
    assert refused["durability"]["qualified_remote_storage"] is False
    with pytest.raises(WorkspacePersistenceError):
        service.seal_encrypted_workflow_continuity(OWNER, _bound(service), case_id=CASE)
