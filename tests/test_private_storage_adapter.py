"""Ciphertext transport receipts for an injected measured-hermetic backend.

These tests do not start an IPFS daemon, install dependencies, or claim
replication, sessions, or deletion propagation.
"""

from __future__ import annotations

import pytest

from applications.complaint_workspace import WorkspaceAccess
from integrations.private_storage import (
    ENVELOPE_MAGIC,
    PrivateStorageError,
    store_private_artifact,
)


KEY = bytes(range(32))
KEY_ID = "case-key-a"
PLAINTEXT = b"synthetic-private-note"


def _access() -> WorkspaceAccess:
    return WorkspaceAccess.authenticated("tenant-a", case_id="case-a")


class _HermeticBytes:
    measurement_label = "measured-hermetic"

    def __init__(self, *, pin_ok: bool = True, readback: bytes | None = None, fail_add: bool = False):
        self.blobs: dict[str, bytes] = {}
        self.seen: list[bytes] = []
        self.pin_ok = pin_ok
        self.readback = readback
        self.fail_add = fail_add
        self.pin_calls = 0

    def add_bytes(self, data, pin=True):
        del pin
        blob = bytes(data)
        self.seen.append(blob)
        if self.fail_add:
            raise ConnectionError("backend offline")
        cid = "bafyhermeticprivatecid"
        self.blobs[cid] = self.readback if self.readback is not None else blob
        return {"success": True, "cid": cid, "pinned": False}

    def cat(self, cid):
        if cid not in self.blobs:
            raise FileNotFoundError(cid)
        return self.blobs[cid]

    def pin(self, cid):
        self.pin_calls += 1
        if not self.pin_ok:
            return {"success": False, "cid": cid, "pinned": False, "error": "pin failed"}
        return {"success": True, "cid": cid, "pinned": True}


def _store(backend, **overrides):
    return store_private_artifact(
        overrides.get("data", PLAINTEXT),
        access=_access(),
        tenant_id="tenant-a",
        case_id="case-a",
        artifact_kind="intake-note",
        revision="rev-1",
        key=KEY,
        key_id=KEY_ID,
        backend=backend,
        pin_content=overrides.get("pin_content", True),
        journal=overrides.get("journal"),
        replicate=overrides.get("replicate"),
    )


def test_backend_observes_ciphertext_only_and_readback_commits():
    backend = _HermeticBytes(pin_ok=True)
    receipt = _store(backend)
    assert backend.seen and backend.seen[0].startswith(ENVELOPE_MAGIC)
    assert PLAINTEXT not in backend.seen[0]
    assert receipt["verified"] is True
    assert receipt["verification"]["matched"] is True
    assert receipt["pinned"] is True
    assert receipt["uploaded"] is True
    assert receipt["stored_local"] is False
    assert receipt["replicated"] is False
    assert receipt["receipt"]["measurement"] == "measured-hermetic"
    assert receipt["receipt"]["network_durable"] is False


def test_readback_mismatch_does_not_commit():
    backend = _HermeticBytes(readback=b"not-the-ciphertext")
    with pytest.raises(PrivateStorageError) as caught:
        _store(backend)
    assert caught.value.code == "readback_mismatch"


def test_pin_failure_keeps_verified_store_unpinned():
    backend = _HermeticBytes(pin_ok=False)
    receipt = _store(backend)
    assert receipt["verified"] is True
    assert receipt["pinned"] is False
    assert receipt["receipt"]["network_durable"] is False
    assert backend.pin_calls == 1


def test_offline_backend_is_not_a_committed_receipt():
    backend = _HermeticBytes(fail_add=True)
    with pytest.raises(PrivateStorageError) as caught:
        _store(backend)
    assert caught.value.code == "backend_rejected"


def test_unpinned_store_is_distinct_from_verified_pin():
    unpinned = _store(_HermeticBytes(pin_ok=False), pin_content=True)
    pinned = _store(_HermeticBytes(pin_ok=True), pin_content=True)
    assert unpinned["verified"] is True and unpinned["pinned"] is False
    assert pinned["verified"] is True and pinned["pinned"] is True
    assert unpinned["stored_local"] is False and pinned["stored_local"] is False


@pytest.mark.parametrize("failure", [
    {"success": False}, {"success": "false"}, {"status": "rejected"},
    {"error": "read failed"}, {"success": True, "error": "read failed"},
])
def test_rejected_matching_ciphertext_does_not_journal_or_replicate(failure):
    class RejectedReadback(_HermeticBytes):
        def cat(self, cid):
            return {**failure, "cid": cid, "data": self.blobs[cid]}

    journal = []
    replicas = []
    with pytest.raises(PrivateStorageError) as caught:
        _store(RejectedReadback(), journal=journal.append, replicate=replicas.append)
    assert caught.value.code == "readback_mismatch"
    assert journal == []
    assert replicas == []
