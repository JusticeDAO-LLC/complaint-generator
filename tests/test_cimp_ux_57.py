"""CIMP-UX-57: durable private evidence and annotation storage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from applications.evidence_annotation_store import EvidenceAnnotationStore
from integrations.private_collaboration import CaseResourceKeyGrantError, commit_linkage_record
from integrations.private_storage import (
    BoundPrivateRecordError,
    PrivateArtifactBinding,
    open_private_bound_record,
    qualify_content_address,
)


SECRET = b"SYNTHETIC-EVIDENCE-BODY-57"
KEY = bytes(range(32))
OTHER_KEY = bytes(reversed(range(32)))


def _binding(kind: str, revision: str = "rev-1", principal: str = "principal-owner") -> PrivateArtifactBinding:
    return PrivateArtifactBinding(
        tenant_id="tenant-ux57",
        case_id="case-ux57",
        artifact_kind=kind,
        revision=revision,
        principal_id=principal,
    )


class _Remote:
    def __init__(self, *, readback: bool, explode: bool = False) -> None:
        self.provider_id = "remote-replica"
        self.failure_domain = "remote-domain"
        self.readback = readback
        self.explode = explode
        self.seen: list[bytes] = []

    def put(self, name: str, payload: bytes) -> dict[str, str]:
        if self.explode:
            raise RuntimeError("remote down")
        self.seen.append(bytes(payload))
        return {"state": "queued", "name": name}

    def get(self, name: str):
        if not self.readback:
            return None
        return self.seen[-1]


def _assert_no_secret(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            blob = path.read_bytes()
            assert SECRET not in blob
            assert b"success" not in blob
            assert b"\"cid\"" not in blob


def test_evidence_annotation_classification_and_link_round_trip(tmp_path: Path) -> None:
    store = EvidenceAnnotationStore(tmp_path)
    evidence = store.put_evidence(
        record_id="evidence-1",
        plaintext=SECRET,
        binding=_binding("evidence"),
        key=KEY,
        key_id="key-evidence",
    )
    annotation = store.put_annotation(
        record_id="annotation-1",
        evidence_id="evidence-1",
        note="synthetic margin note",
        binding=_binding("annotation", "rev-a"),
        key=KEY,
        key_id="key-annotation",
    )
    revision = store.revise_classification(
        record_id="class-1",
        label="medical-record",
        previous_revision="rev-0",
        binding=_binding("classification_revision", "rev-2"),
        key=KEY,
        key_id="key-class",
    )
    link = store.link(
        record_id="link-1",
        actor_principal_id="principal-owner",
        evidence_id="evidence-1",
        annotation_id="annotation-1",
        binding=_binding("linkage", "rev-l"),
        key=KEY,
        key_id="key-link",
    )
    for receipt in (evidence, annotation, revision, link):
        assert receipt["local_durable"] is True
        assert receipt["remote_durable"] is False
        assert receipt["counts_toward_desired"] is True
        assert receipt["placement_intents"] == 0
        assert receipt["queued_can_claim_committed"] is False
        assert receipt["content_address_is_encryption"] is False
        assert "success" not in receipt
        assert "cid" not in receipt
    assert store.read(record_id="evidence-1", binding=_binding("evidence"), key=KEY) == SECRET
    opened = json.loads(store.read(record_id="annotation-1", binding=_binding("annotation", "rev-a"), key=KEY))
    assert opened["evidence_id"] == "evidence-1"
    opened_link = json.loads(store.read(record_id="link-1", binding=_binding("linkage", "rev-l"), key=KEY))
    assert opened_link["actor_principal_id"] == "principal-owner"
    _assert_no_secret(tmp_path)


def test_unqualified_remote_echo_queue_or_error_does_not_claim_durability(tmp_path: Path) -> None:
    store = EvidenceAnnotationStore(tmp_path / "verified")
    remote = _Remote(readback=True)
    receipt = store.put_evidence(
        record_id="evidence-remote",
        plaintext=SECRET,
        binding=_binding("evidence"),
        key=KEY,
        key_id="key-remote",
        remote_backend=remote,
    )
    assert receipt["local_durable"] is True
    assert receipt["remote_durable"] is False
    assert receipt["counts_toward_desired"] is False
    assert receipt["code"] == "remote_unqualified"
    assert remote.seen == []

    queued = EvidenceAnnotationStore(tmp_path / "queued")
    blind = _Remote(readback=False)
    blind_receipt = queued.put_evidence(
        record_id="evidence-queued",
        plaintext=SECRET,
        binding=_binding("evidence"),
        key=KEY,
        key_id="key-queued",
        remote_backend=blind,
    )
    assert blind_receipt["local_durable"] is True
    assert blind_receipt["remote_durable"] is False
    assert blind_receipt["code"] == "remote_unqualified"
    assert blind.seen == []
    assert blind_receipt["local_write_is_remote_durable"] is False

    down = EvidenceAnnotationStore(tmp_path / "down")
    failed = down.put_evidence(
        record_id="evidence-down",
        plaintext=SECRET,
        binding=_binding("evidence"),
        key=KEY,
        key_id="key-down",
        remote_backend=_Remote(readback=False, explode=True),
    )
    assert failed["remote_durable"] is False
    assert failed["code"] == "remote_unqualified"
    assert down.read(record_id="evidence-down", binding=_binding("evidence"), key=KEY) == SECRET


def test_content_address_wrong_binding_and_locked_key_do_not_open(tmp_path: Path) -> None:
    address = qualify_content_address(hashlib.sha256(SECRET).hexdigest())
    assert address["encrypted"] is False
    assert address["code"] == "content_address_is_not_encryption"
    store = EvidenceAnnotationStore(tmp_path)
    store.put_evidence(
        record_id="evidence-1",
        plaintext=SECRET,
        binding=_binding("evidence"),
        key=KEY,
        key_id="key-evidence",
    )
    digest_path = tmp_path / "objects" / address["code"]
    digest_path.write_bytes(hashlib.sha256(SECRET).digest())
    with pytest.raises(BoundPrivateRecordError):
        store.read(record_id="missing-record", binding=_binding("evidence"), key=KEY)
    with pytest.raises(BoundPrivateRecordError) as wrong_binding:
        store.read(record_id="evidence-1", binding=_binding("evidence", "rev-other"), key=KEY)
    assert wrong_binding.value.code == "binding_mismatch"
    with pytest.raises(BoundPrivateRecordError) as wrong_key:
        store.read(record_id="evidence-1", binding=_binding("evidence"), key=OTHER_KEY)
    assert wrong_key.value.code == "authentication_failed"
    with pytest.raises(BoundPrivateRecordError):
        store.revise_classification(
            record_id="class-same",
            label="medical-record",
            previous_revision="rev-2",
            binding=_binding("classification_revision", "rev-2"),
            key=KEY,
            key_id="key-class",
        )
    with pytest.raises(CaseResourceKeyGrantError):
        commit_linkage_record(
            tmp_path / "other",
            actor_principal_id="principal-stranger",
            evidence_id="evidence-1",
            annotation_id="annotation-1",
            binding=_binding("linkage"),
            key=KEY,
            key_id="key-link",
            record_id="link-stranger",
        )


def test_staged_record_recovers_once_and_then_exhausts(tmp_path: Path) -> None:
    store = EvidenceAnnotationStore(tmp_path)
    binding = _binding("evidence")
    staged = store.stage_evidence(
        record_id="evidence-staged",
        plaintext=SECRET,
        binding=binding,
        key=KEY,
        key_id="key-staged",
    )
    assert staged["local_durable"] is False
    assert staged["code"] == "staged_not_durable"
    with pytest.raises(BoundPrivateRecordError) as unavailable:
        store.read(record_id="evidence-staged", binding=binding, key=KEY)
    assert unavailable.value.code == "record_unavailable"
    first = store.recover(key=KEY, bindings={"evidence-staged": binding}, max_attempts=2)
    assert first["promoted"] == ["evidence-staged"]
    assert store.read(record_id="evidence-staged", binding=binding, key=KEY) == SECRET

    again = EvidenceAnnotationStore(tmp_path / "bounded")
    again.stage_evidence(
        record_id="evidence-bounded",
        plaintext=SECRET,
        binding=binding,
        key=KEY,
        key_id="key-bounded",
    )
    staging = tmp_path / "bounded" / "staging" / "evidence-bounded"
    saved = staging.read_bytes()
    staging.write_bytes(saved + b"tamper")
    missed = again.recover(key=KEY, bindings={"evidence-bounded": binding}, max_attempts=1)
    assert missed["exhausted"] == ["evidence-bounded"]
    assert missed["promoted"] == []
    staging.write_bytes(saved)
    still = again.recover(key=KEY, bindings={"evidence-bounded": binding}, max_attempts=1)
    assert still["exhausted"] == ["evidence-bounded"]
    with pytest.raises(BoundPrivateRecordError):
        open_private_bound_record(
            tmp_path / "bounded",
            record_id="evidence-bounded",
            binding=binding,
            key=KEY,
        )
    _assert_no_secret(tmp_path)
