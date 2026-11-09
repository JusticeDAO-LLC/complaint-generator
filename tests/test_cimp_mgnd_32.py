"""Private derived hook indexes stay off plaintext database rows.

Synthetic cases only. No test is skipped. Directory names and mode bits are
not encryption. A failed store does not write a plaintext fallback.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService, WorkspacePersistenceError
from integrations.private_storage import InjectedCaseKeyProvider
from mediator.claim_support_hooks import ClaimSupportHook
from mediator.evidence_hooks import EvidenceStateHook
from mediator.legal_authority_hooks import LegalAuthorityStorageHook as LegalHook
from tests.mgnd_fixtures import CASE_LABELS, PASSPHRASE, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_OWNER = "synthetic-owner"


class _Mediator:
    def log(self, *args, **kwargs) -> None:
        return None

    def get_three_phase_status(self) -> dict:
        return {}


class _MemoryBackend:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.blobs: dict[str, bytes] = {}
        self.events: list[bytes] = []

    def add_bytes(self, data, pin=True):
        payload = bytes(data)
        self.events.append(payload)
        if self.fail:
            raise OSError("storage_outage")
        cid = "bafy" + hashlib.sha256(payload).hexdigest()[:55]
        self.blobs[cid] = payload
        return {"success": True, "cid": cid, "pinned": False}

    def cat(self, cid):
        if self.fail or cid not in self.blobs:
            raise OSError("storage_outage")
        return self.blobs[cid]

    def pin(self, cid):
        return {"success": True, "cid": cid, "pinned": False}


def _access(case_id: str):
    from applications.complaint_workspace import WorkspaceAccess

    return WorkspaceAccess.trusted_local(_OWNER, case_id)


def _provider(case_id: str, key: bytes, key_id: str) -> InjectedCaseKeyProvider:
    return InjectedCaseKeyProvider({(_OWNER, case_id): (key_id, key)})


def _context(case_id: str, backend: _MemoryBackend, provider, *, mode: str) -> dict:
    return {
        "access": _access(case_id),
        "tenant_id": _OWNER,
        "case_id": case_id,
        "principal_id": _OWNER,
        "key_provider": provider,
        "backend": backend,
        "backend_name": "local_cache",
        "pin_content": False,
        "index_mode": mode,
    }


def _secret(case) -> str:
    marker = case.narrative.evidence_markers[0].marker_id if case.narrative.evidence_markers else case.label
    return f"PRIVATE-DERIVED-{case.case_id}-{marker}"


def _files(root: Path) -> set[Path]:
    return {path for path in root.rglob("*") if path.is_file()}


def test_catalog_and_durable_rows_omit_plaintext(tmp_path):
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    stored = []
    for case in cases:
        if not case.storage_available:
            continue
        secret = _secret(case)
        backend = _MemoryBackend()
        key = os.urandom(32)
        hook = EvidenceStateHook(_Mediator(), db_path=str(tmp_path / f"{case.label}-evidence.duckdb"))
        bound = hook.bind_private_derived_index(
            _context(case.case_id, backend, _provider(case.case_id, key, f"key-{case.label}"), mode="durable"),
            directory_mode_private=True,
        )
        assert bound["encrypted"] is True
        assert bound["encryption_from_path_or_mode_bits"] is False
        assert bound["directory_mode_private"] is True
        receipt = hook.commit_private_derived(case_id=case.case_id, kind="parsed_text_preview", text=secret)
        assert receipt["status"] == "available"
        assert receipt["plaintext_persisted"] is False
        assert receipt["row_persisted"] is True
        audit = hook.audit_new_derived_rows()
        assert audit["scope"] == "newly_created"
        assert audit["row_count"] >= 1
        assert audit["plaintext_private_columns"] == 0
        blob = Path(hook.db_path).read_bytes()
        assert secret.encode("utf-8") not in blob
        assert any(item.startswith(b"CGPE") and secret.encode("utf-8") not in item for item in backend.events)
        opened = hook.read_private_derived(receipt["token"])
        assert opened["text"] == secret
        assert opened["encrypted"] is True
        stored.append(case.case_id)
    assert stored


def test_directory_mode_is_not_encryption_and_unavailable_is_honest(tmp_path):
    case = next(item for item in meaningful_cases() if not item.storage_available)
    interview = tmp_path / "interview-db" / "owner-case"
    interview.mkdir(parents=True, mode=0o700)
    os.chmod(interview, 0o700)
    hook = ClaimSupportHook(_Mediator(), db_path=str(interview / "claim-support.db"))
    status = hook.bind_private_derived_index(None, unavailable_code="unlock_needed", directory_mode_private=True)
    assert status["encrypted"] is False
    assert status["encryption_from_path_or_mode_bits"] is False
    assert status["index_mode"] == "unavailable"
    secret = _secret(case)
    receipt = hook.commit_private_derived(case_id=case.case_id, kind="claim_element_text", text=secret)
    assert receipt["status"] == "unavailable"
    assert receipt["plaintext_persisted"] is False
    assert receipt["code"] == "unlock_needed"
    written = [path.read_bytes() for path in interview.rglob("*") if path.is_file()]
    assert all(secret.encode("utf-8") not in blob for blob in written)

    failing = _MemoryBackend(fail=True)
    available = next(item for item in meaningful_cases() if item.storage_available)
    key = os.urandom(32)
    durable = EvidenceStateHook(_Mediator(), db_path=str(tmp_path / "failed-evidence.duckdb"))
    durable.bind_private_derived_index(
        _context(available.case_id, failing, _provider(available.case_id, key, "key-fail"), mode="durable")
    )
    failed = durable.commit_private_derived(case_id=available.case_id, kind="fact_text", text=_secret(available))
    assert failed["status"] == "unavailable"
    assert failed["plaintext_persisted"] is False
    assert _secret(available).encode("utf-8") not in Path(durable.db_path).read_bytes()
    assert failing.blobs == {}


def test_ephemeral_rebuild_close_and_case_isolation(tmp_path):
    left, right = [item for item in meaningful_cases() if item.storage_available][:2]
    root = tmp_path / "ephemeral"
    root.mkdir()
    before = _files(root)
    left_hook = ClaimSupportHook(_Mediator(), db_path=str(root / "left.duckdb"))
    right_hook = ClaimSupportHook(_Mediator(), db_path=str(root / "right.duckdb"))
    left_hook.bind_private_derived_index(
        _context(left.case_id, _MemoryBackend(), None, mode="ephemeral"),
        directory_mode_private=True,
    )
    right_hook.bind_private_derived_index(
        _context(right.case_id, _MemoryBackend(), None, mode="ephemeral"),
        directory_mode_private=True,
    )
    assert left_hook.private_derived_index_status()["encrypted"] is False
    left_secret = _secret(left)
    right_secret = _secret(right)
    left_row = left_hook.commit_private_derived(case_id=left.case_id, kind="support_label", text=left_secret)
    right_row = right_hook.commit_private_derived(case_id=right.case_id, kind="support_label", text=right_secret)
    assert left_row["status"] == "available"
    assert right_row["encrypted"] is False
    mixed = left_hook.commit_private_derived(case_id=right.case_id, kind="support_label", text=right_secret)
    assert mixed["code"] == "case_mismatch"
    assert mixed["persisted"] is False
    assert left_hook.read_private_derived(left_row["token"])["text"] == left_secret
    cross = left_hook.read_private_derived(right_row["token"])
    assert cross.get("text") != right_secret
    assert left_hook.read_private_derived(left_row["token"], case_id=right.case_id)["code"] == "case_mismatch"
    rebuilt = left_hook.rebuild_private_derived_index()
    assert rebuilt["status"] == "available"
    assert rebuilt["case_id"] == left.case_id
    assert rebuilt["rebuilt"] == 1
    assert left_secret.encode("utf-8") not in Path(left_hook.db_path).read_bytes()
    assert right_secret.encode("utf-8") not in Path(left_hook.db_path).read_bytes()
    closed = left_hook.close_private_derived_index(crash=True)
    assert closed["plaintext_fallback_published"] is False
    assert left_hook.read_private_derived(left_row["token"])["code"] == "index_closed"
    crashed = left_hook.rebuild_private_derived_index()
    assert crashed["status"] == "unavailable"
    assert crashed["plaintext_fallback"] is False
    assert _files(root) == before | {Path(left_hook.db_path), Path(right_hook.db_path)}
    for path in _files(root):
        assert left_secret.encode("utf-8") not in path.read_bytes()
        assert right_secret.encode("utf-8") not in path.read_bytes()


def test_public_law_cache_is_separate_from_private_associations(tmp_path):
    case = next(item for item in meaningful_cases() if item.storage_available and item.sources)
    source = case.sources[0]
    public_text = f"PUBLIC-LAW-{source.citation}-{source.authority_id}"
    private_text = _secret(case)
    hook = LegalHook(_Mediator(), db_path=str(tmp_path / "legal.duckdb"))
    backend = _MemoryBackend()
    key = os.urandom(32)
    hook.bind_private_derived_index(
        _context(case.case_id, backend, _provider(case.case_id, key, "key-law"), mode="durable")
    )
    cached = hook.cache_public_law_source(citation=source.citation, text=public_text)
    assert cached["storage_class"] == "public_legal_corpus"
    assert cached["separated_from_private_associations"] is True
    association = hook.commit_private_derived(
        case_id=case.case_id,
        kind="claim_association",
        text=private_text,
        public_cache_id=cached["cache_id"],
    )
    assert association["status"] == "available"
    assert association["public_cache_id"] == cached["cache_id"]
    db_blob = Path(hook.db_path).read_bytes()
    assert private_text.encode("utf-8") not in db_blob
    assert public_text.encode("utf-8") not in db_blob
    assert hook.read_public_law_source(cached["cache_id"])["text"] == public_text
    assert hook.read_private_derived(association["token"])["text"] == private_text
    support = ClaimSupportHook(_Mediator(), db_path=str(tmp_path / "support.duckdb"))
    support.bind_private_derived_index(
        _context(case.case_id, backend, _provider(case.case_id, key, "key-law"), mode="durable")
    )
    support.add_support_link(
        user_id=_OWNER,
        claim_type="synthetic",
        claim_element_text=private_text,
        support_kind="authority",
        support_ref=cached["cache_id"],
        support_label=private_text,
    )
    support_blob = Path(support.db_path).read_bytes()
    assert private_text.encode("utf-8") not in support_blob
    assert public_text.encode("utf-8") not in support_blob


def test_workspace_activation_does_not_treat_interview_db_as_encryption(tmp_path):
    case = next(item for item in meaningful_cases() if item.storage_available)
    locked = ComplaintWorkspaceService(tmp_path / "locked")

    class _Carrier:
        def __init__(self) -> None:
            self.evidence_state = EvidenceStateHook(_Mediator(), db_path=str(tmp_path / "locked-evidence.duckdb"))
            self.claim_support = ClaimSupportHook(_Mediator(), db_path=str(tmp_path / "locked-support.duckdb"))
            self.legal_authority_storage = LegalHook(_Mediator(), db_path=str(tmp_path / "locked-legal.duckdb"))

    carrier = _Carrier()
    receipt = locked.activate_private_derived_indexes(carrier, _OWNER, case.case_id)
    assert receipt["status"] == "unavailable"
    assert receipt["encrypted"] is False
    assert receipt["encryption_from_path_or_mode_bits"] is False
    assert receipt["plaintext_fallback"] is False
    secret = _secret(case)
    denied = carrier.evidence_state.commit_private_derived(case_id=case.case_id, kind="preview", text=secret)
    assert denied["status"] == "unavailable"
    assert denied["plaintext_persisted"] is False

    opened = ComplaintWorkspaceService(tmp_path / "opened")
    created = opened.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    assert created.get("unlocked") is True or created.get("status") in {"available", "ready"}
    unlocked = opened.unlock_private_keys(passphrase=PASSPHRASE)
    assert unlocked.get("awaiting_user") is not True
    ready = opened.ensure_private_case_key(_OWNER, case.case_id)
    assert ready.get("data_key_id")
    active = _Carrier()
    activated = opened.activate_private_derived_indexes(active, _OWNER, case.case_id)
    assert activated["status"] == "available"
    assert activated["encrypted"] is True
    assert activated["encryption_from_path_or_mode_bits"] is False
    assert activated["remote_durable"] is False
    saved = active.evidence_state.commit_private_derived(case_id=case.case_id, kind="preview", text=secret)
    assert saved["status"] == "available"
    assert secret.encode("utf-8") not in Path(active.evidence_state.db_path).read_bytes()
    assert active.evidence_state.read_private_derived(saved["token"])["text"] == secret
    closed = active.evidence_state.close_private_derived_index(crash=True)
    assert closed["plaintext_fallback_published"] is False
    rebuilt = active.evidence_state.rebuild_private_derived_index()
    assert rebuilt["status"] == "available"
    assert rebuilt["rebuilt"] == 1
    assert active.evidence_state.read_private_derived(saved["token"])["text"] == secret
    with pytest.raises(WorkspacePersistenceError):
        opened._private_artifact_context(_OWNER, "missing-case-for-control")
