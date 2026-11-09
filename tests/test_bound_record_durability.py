"""Private record durability comes from the actual Kit storage producer."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import sys

import pytest

from applications.evidence_annotation_store import EvidenceAnnotationStore
from integrations.private_storage import (BoundPrivateRecordError, PrivateArtifactIntegrityError,
    open_private_artifact, parse_private_envelope)
from tests.test_cimp_ux_57 import KEY, SECRET, _binding

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


class _VolatileEchoBackend:
    """Adversarial byte echo, deliberately without a durable storage producer."""
    provider_id = "memory-only"
    failure_domain = "same-process"

    def __init__(self):
        self.objects = {}
        self.calls = 0

    def put(self, name, payload):
        self.calls += 1
        self.objects[name] = bytes(payload)
        return {"state": "queued"}

    def get(self, name):
        self.calls += 1
        return self.objects[name]


def test_queued_memory_echo_cannot_qualify_remote_durability(tmp_path):
    backend = _VolatileEchoBackend()
    store = EvidenceAnnotationStore(tmp_path / "records")
    receipt = store.put_evidence(record_id="echo-record", plaintext=SECRET,
        binding=_binding("evidence"), key=KEY, key_id="key-echo", remote_backend=backend)
    assert receipt["local_durable"] is True
    assert receipt["remote_durable"] is False
    assert receipt["counts_toward_desired"] is False
    assert backend.calls == 0
    assert store.read(record_id="echo-record", binding=_binding("evidence"), key=KEY) == SECRET


def test_actual_kit_ciphertext_is_the_host_envelope_and_survives_disk_reopen(tmp_path):
    from ipfs_kit_py.mcp.enterprise.encryption import EncryptionManager
    from ipfs_kit_py.assurance.local_durable import LiveLocalFilesystemAdapter
    store = EvidenceAnnotationStore(tmp_path / "records")
    produced = []
    previous = sys.getprofile()

    def observe_actual_producer(frame, event, value):
        if event == "return" and frame.f_code is EncryptionManager.encrypt.__code__:
            produced.append(value)

    # Observe the genuine return event; the SDK callable and result are unchanged.
    sys.setprofile(observe_actual_producer)
    try:
        receipt = store.put_evidence(record_id="kit-record", plaintext=SECRET,
            binding=_binding("evidence"), key=KEY, key_id="key-kit")
    finally:
        sys.setprofile(previous)
    assert len(produced) == 1
    record = json.loads((store._root / "journal/kit-record").read_text())
    locator = record["content_ref"]
    envelope = (store._root / "objects" / locator).read_bytes()
    parsed = parse_private_envelope(envelope)
    encrypted = produced[0]
    assert parsed["nonce"] == encrypted.initialization_vector
    assert parsed["ciphertext"] == encrypted.encrypted_data + encrypted.auth_tag
    assert receipt["local_durable"] is True and receipt["remote_durable"] is False
    assert "cid" not in receipt and "plaintext" not in receipt and "success" not in receipt
    assert SECRET not in envelope and KEY not in envelope
    assert open_private_artifact(envelope, binding=_binding("evidence"), key=KEY) == SECRET
    # This forces the cryptographic AAD check, independently of journal matching.
    with pytest.raises(PrivateArtifactIntegrityError):
        open_private_artifact(envelope, binding=replace(_binding("evidence"), case_id="foreign-case"), key=KEY)
    adapter = LiveLocalFilesystemAdapter.reopen(store._root)
    try:
        observed = adapter.get(locator)
        assert observed.data == envelope
        assert observed.resulting_content_cid == LiveLocalFilesystemAdapter.content_cid(envelope)
        assert observed.resulting_content_cid != locator
        assert adapter.digest(locator).data == envelope
    finally:
        adapter.close()
    # A newly constructed host reader uses the actual Kit manifest and sidecar.
    cold = EvidenceAnnotationStore(store._root)
    assert cold.read(record_id="kit-record", binding=_binding("evidence"), key=KEY) == SECRET


@pytest.mark.parametrize("damage", ["ciphertext", "digest-sidecar", "manifest"])
def test_host_reader_refuses_actual_kit_integrity_or_missing_durability_material(tmp_path, damage):
    store = EvidenceAnnotationStore(tmp_path / "records")
    store.put_evidence(record_id="damaged", plaintext=SECRET,
        binding=_binding("evidence"), key=KEY, key_id="key-damage")
    record = json.loads((store._root / "journal/damaged").read_text())
    target = store._root / "objects" / record["content_ref"]
    if damage == "ciphertext":
        payload = target.read_bytes()
        target.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
    elif damage == "digest-sidecar":
        target.with_name(target.name + ".cid").unlink()
    else:
        (store._root / "manifest.json").unlink()
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in store._root.rglob("*") if p.is_file()}
    with pytest.raises(BoundPrivateRecordError):
        EvidenceAnnotationStore(store._root).read(record_id="damaged", binding=_binding("evidence"), key=KEY)
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in store._root.rglob("*") if p.is_file()}
    assert after == before


def test_second_actual_local_kit_store_does_not_become_a_remote_replica(tmp_path):
    from ipfs_kit_py.assurance.local_durable import LiveLocalFilesystemAdapter
    local = LiveLocalFilesystemAdapter(tmp_path / "second-local")
    try:
        before = local.effect_count
        receipt = EvidenceAnnotationStore(tmp_path / "records").put_evidence(
            record_id="local-is-not-remote", plaintext=SECRET, binding=_binding("evidence"),
            key=KEY, key_id="key-local", remote_backend=local)
        assert receipt["local_durable"] is True
        assert receipt["remote_durable"] is False and receipt["counts_toward_desired"] is False
        assert receipt["code"] == "remote_unqualified"
        assert local.effect_count == before
    finally:
        local.close()
