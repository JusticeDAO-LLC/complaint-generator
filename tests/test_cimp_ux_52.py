"""CIMP-UX-52: Kit-backed evidence storage, state, and analysis."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from integrations.private_storage import probe_kit_evidence_capability
from mediator.evidence_hooks import EvidenceRetrievalError, read_scoped_private_evidence
from mediator.hook_runtime import qualify_private_evidence_hooks


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

SECRET = b"Synthetic scoped evidence sentence for case actor review."
NOTE = b"Synthetic margin note that must stay an annotation."
KEY = bytes(range(32))
ACTOR = "actor-ux52"
CASE = "case-ux52"
TENANT = "tenant-ux52"


def _consent(**overrides):
    body = {
        "granted": True,
        "revoked": False,
        "case_id": CASE,
        "actor_id": ACTOR,
        "operations": ["qualify_private_evidence"],
    }
    body.update(overrides)
    return body


def _qualify(root: Path, **overrides):
    source = overrides.pop("source", SECRET)
    revision = overrides.pop("revision", "rev1")
    payload = dict(
        root=str(root),
        case_id=CASE,
        actor_id=ACTOR,
        tenant_id=TENANT,
        revision=revision,
        source=source,
        source_sha256=hashlib.sha256(source).hexdigest(),
        key=KEY,
        key_id="key-ux52",
        consent=_consent(),
        annotation=NOTE,
        annotation_sha256=hashlib.sha256(NOTE).hexdigest(),
        db_path=str(root / "evidence.duckdb"),
    )
    payload.update(overrides)
    return qualify_private_evidence_hooks(**payload)


def _assert_no_secret(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            blob = path.read_bytes()
            assert SECRET not in blob
            assert NOTE not in blob


def test_qualified_hooks_round_trip_chunks_without_annotation_conversion(tmp_path: Path) -> None:
    capability = probe_kit_evidence_capability()
    if capability["available"] is not True:
        pytest.fail("Kit ciphertext owner or AES-GCM is missing; qualification must not skip")
    receipt = _qualify(tmp_path)
    assert receipt["status"] == "qualified"
    assert receipt["workflow"] == "qualify_private_evidence_hooks"
    assert receipt["plaintext_fallback"] is False
    assert receipt["plaintext_persisted"] is False
    assert receipt["annotation_converted_to_evidence"] is False
    assert receipt["local_durable"] is True
    assert receipt["remote_durable"] is False
    assert receipt["evidence_count"] == 1
    assert receipt["annotation_count"] == 1
    assert receipt["chunk_count"] >= 1
    assert receipt["analysis_evidence_ids"] == ["ev-rev1"]
    assert receipt["analysis_annotation_ids"] == ["an-rev1"]
    assert receipt["storage_owner"] == "EvidenceStorageHook"
    assert receipt["state_owner"] == "EvidenceStateHook"
    assert receipt["analysis_owner"] == "EvidenceAnalysisHook"
    assert "parse_document_text" in receipt["dataset_owner"]
    assert "LiveLocalFilesystemAdapter" in receipt["kit_owner"]
    opened = read_scoped_private_evidence(
        str(tmp_path), case_id=CASE, actor_id=ACTOR, tenant_id=TENANT, revision="rev1", key=KEY,
    )
    assert opened == SECRET
    _assert_no_secret(tmp_path)


def test_key_lock_writes_nothing(tmp_path: Path) -> None:
    receipt = _qualify(tmp_path, key=None, key_locked=True)
    assert receipt["status"] == "refused"
    assert receipt["code"] == "key_locked"
    assert receipt["writes"] == 0
    assert list(tmp_path.rglob("*")) == []


def test_conflicting_revision_keeps_original_ciphertext(tmp_path: Path) -> None:
    first = _qualify(tmp_path)
    assert first["status"] == "qualified"
    other = b"A different synthetic sentence that conflicts with the stored revision."
    second = _qualify(tmp_path, source=other, source_sha256=hashlib.sha256(other).hexdigest())
    assert second["status"] == "refused"
    assert second["code"] == "conflicting_revision"
    assert second["writes"] == 0
    assert second["plaintext_fallback"] is False
    opened = read_scoped_private_evidence(
        str(tmp_path), case_id=CASE, actor_id=ACTOR, tenant_id=TENANT, revision="rev1", key=KEY,
    )
    assert opened == SECRET
    _assert_no_secret(tmp_path)


def test_source_integrity_mismatch_refuses(tmp_path: Path) -> None:
    receipt = _qualify(tmp_path, source_sha256="ab" * 32)
    assert receipt["status"] == "refused"
    assert receipt["code"] == "source_integrity"
    assert receipt["writes"] == 0
    _assert_no_secret(tmp_path)


def test_unsafe_content_refuses(tmp_path: Path) -> None:
    payload = b"Synthetic text <script>alert(1)</script> remains unsafe."
    receipt = _qualify(tmp_path, source=payload, source_sha256=hashlib.sha256(payload).hexdigest())
    assert receipt["status"] == "refused"
    assert receipt["code"] == "unsafe_content"
    assert receipt["writes"] == 0
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_missing_capability_is_unavailable_even_if_caller_claims_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "integrations.private_storage.probe_kit_evidence_capability",
        lambda: {"available": False, "code": "missing_capability", "owner": "missing-kit"},
    )
    receipt = _qualify(tmp_path, capability_available=True)
    assert receipt["status"] == "unavailable"
    assert receipt["code"] == "missing_capability"
    assert receipt["plaintext_fallback"] is False
    assert receipt["writes"] == 0
    _assert_no_secret(tmp_path)


def test_consent_revocation_and_wrong_actor_refuse(tmp_path: Path) -> None:
    revoked = _qualify(tmp_path, consent=_consent(revoked=True, granted=False))
    assert revoked["status"] == "refused"
    assert revoked["code"] == "consent_refused"
    assert revoked["writes"] == 0
    stored = _qualify(tmp_path / "stored")
    assert stored["status"] == "qualified"
    with pytest.raises(EvidenceRetrievalError) as opened:
        read_scoped_private_evidence(
            str(tmp_path / "stored"),
            case_id=CASE,
            actor_id="actor-other",
            tenant_id=TENANT,
            revision="rev1",
            key=KEY,
        )
    assert opened.value.code == "binding_mismatch"
    _assert_no_secret(tmp_path)
