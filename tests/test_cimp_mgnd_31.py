"""Private evidence hook bytes use the encrypted artifact owner.

Cases are synthetic. No test is skipped. Local deterministic identifiers
are not treated as remote durability, and a failed store does not invent one.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService, WorkspacePersistenceError
from integrations.private_storage import InjectedCaseKeyProvider
from mediator.evidence_hooks import EvidenceRetrievalError, EvidenceStorageError, EvidenceStorageHook
from tests.mgnd_fixtures import CASE_LABELS, PASSPHRASE, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_OWNER = "synthetic-owner"


class _Mediator:
    def __init__(self) -> None:
        self.events = []

    def log(self, *args, **kwargs) -> None:
        self.events.append((args, kwargs))

    def get_three_phase_status(self) -> dict:
        return {}


class _MemoryBackend:
    measurement_label = "measured-hermetic"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[bytes] = []
        self.blobs: dict[str, bytes] = {}

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


def _provider(case_id: str, key_id: str, key: bytes) -> InjectedCaseKeyProvider:
    return InjectedCaseKeyProvider({(_OWNER, case_id): (key_id, key)})


def _hook(case_id: str, backend: _MemoryBackend, provider: InjectedCaseKeyProvider | None, *, unavailable: str = ""):
    hook = EvidenceStorageHook(_Mediator())
    context = None
    if provider is not None:
        context = {
            "access": _access(case_id),
            "tenant_id": _OWNER,
            "case_id": case_id,
            "principal_id": _OWNER,
            "key_provider": provider,
            "backend": backend,
            "backend_name": "local_cache",
            "pin_content": False,
        }
    hook.bind_private_artifact_context(context, unavailable_code=unavailable)
    return hook


def _private_bytes(case) -> bytes:
    marker = case.narrative.evidence_markers[0].marker_id if case.narrative.evidence_markers else case.label
    return f"PRIVATE-EVIDENCE-{case.case_id}-{marker}".encode("utf-8")


def test_catalog_is_nonempty_and_private_route_roundtrips():
    import mediator.evidence_hooks as hooks

    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    raw_calls = []

    def _reject_raw(*_args, **_kwargs):
        raw_calls.append("add_bytes")
        raise AssertionError("legacy add_bytes used for private evidence")

    original = hooks.add_bytes
    hooks.add_bytes = _reject_raw
    try:
        stored = []
        for case in cases:
            if not case.storage_available:
                continue
            key = os.urandom(32)
            key_id = f"key-{case.label}"
            private_backend = _MemoryBackend()
            public_backend = _MemoryBackend()
            hook = _hook(case.case_id, private_backend, _provider(case.case_id, key_id, key))
            secret = _private_bytes(case)
            metadata = {
                "parse_document": False,
                "source_url": f"synthetic://{case.case_id}",
                "acquisition_method": "submitted",
                "jurisdiction": case.narrative.jurisdiction,
                "backend": private_backend,
                "backend_name": "local_cache",
                "pin_content": False,
            }
            result = hook.store_evidence(secret, "document", metadata)
            assert result["private_artifact"] is True
            assert result["classification"] == "private_evidence"
            assert result["case_id"] == case.case_id
            assert result["tenant_id"] == _OWNER
            assert result["key_id"] == key_id
            assert result["cid_kind"] == "pseudo_cid"
            assert result["network_durable"] is False
            assert result["remote_durable"] is False
            assert result["storage_status"] == "local_only"
            assert not str(result["cid"]).startswith("Qm")
            assert result["provenance"]["content_hash"] == hashlib.sha256(secret).hexdigest()
            assert private_backend.events
            assert private_backend.events[0].startswith(b"CGPE")
            assert secret not in private_backend.events[0]
            assert secret not in b"".join(private_backend.events)
            opened = hook.retrieve_evidence(result["cid"])
            assert opened == secret
            with pytest.raises(EvidenceStorageError) as denied:
                hook.enable_public_user_evidence_ingestion()
            assert denied.value.code == "public_user_evidence_disabled"
            if case.sources:
                public = hook.store_evidence(
                    case.sources[0].source_bytes,
                    "legal_authority_text",
                    {
                        "parse_document": False,
                        "content_origin": "authority_full_text",
                        "corpus_family": "legal_authority",
                        "storage_class": "public_legal_corpus",
                        "backend": public_backend,
                        "backend_name": "local_cache",
                        "pin_content": False,
                    },
                )
                assert public["private_artifact"] is False
                assert public["classification"] == "public_legal_corpus"
                assert public_backend.events == [case.sources[0].source_bytes]
                assert public_backend.events[0] not in private_backend.events
                assert hook.retrieve_evidence(public["cid"]) == case.sources[0].source_bytes
            stored.append(case.label)
        assert stored
    finally:
        hooks.add_bytes = original
    assert raw_calls == []


def test_missing_key_and_storage_failure_do_not_write_plaintext():
    cases = [case for case in meaningful_cases() if case.label in {"baseline", "storage_outage"}]
    assert len(cases) == 2
    for case in cases:
        secret = _private_bytes(case)
        if case.label == "baseline":
            backend = _MemoryBackend()
            hook = _hook(case.case_id, backend, _provider("other-case", "key-other", os.urandom(32)))
            with pytest.raises(EvidenceStorageError) as missing:
                hook.store_evidence(secret, "document", {"parse_document": False, "backend": backend})
            assert missing.value.code == "key_unavailable"
            assert backend.events == []
            assert backend.blobs == {}
            assert "Qm" not in str(missing.value)
        else:
            backend = _MemoryBackend(fail=True)
            key = os.urandom(32)
            hook = _hook(case.case_id, backend, _provider(case.case_id, "key-outage", key))
            with pytest.raises(EvidenceStorageError) as failed:
                hook.store_evidence(secret, "document", {"parse_document": False, "backend": backend, "backend_name": "local_cache"})
            assert failed.value.code == "artifact_unavailable"
            assert backend.blobs == {}
            assert backend.events
            assert backend.events[0].startswith(b"CGPE")
            assert secret not in backend.events[0]
            assert "Qm" not in str(failed.value)
            assert secret.decode("utf-8") not in str(failed.value)


def test_wrong_key_and_case_preserve_bytes_and_provenance():
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    secret = _private_bytes(case)
    key = os.urandom(32)
    other = os.urandom(32)
    key_id = "key-baseline"
    backend = _MemoryBackend()
    hook = _hook(case.case_id, backend, _provider(case.case_id, key_id, key))
    result = hook.store_evidence(
        secret,
        "attachment",
        {
            "parse_document": False,
            "revision": "attachment-baseline",
            "source_url": "synthetic://baseline",
            "backend": backend,
            "backend_name": "local_cache",
        },
    )
    provenance = dict(result["provenance"])
    blob = backend.blobs[result["cid"]]
    with pytest.raises(EvidenceRetrievalError) as wrong_key:
        hook.retrieve_evidence(result["cid"], key=other, key_id=key_id)
    assert wrong_key.value.code
    assert hook.retrieve_evidence(result["cid"]) == secret
    wrong_case = "mgnd-04-other-case"
    with pytest.raises(EvidenceRetrievalError) as wrong_case_error:
        hook.retrieve_evidence(
            result["cid"],
            case_id=wrong_case,
            access=_access(wrong_case),
            key=key,
            key_id=key_id,
        )
    assert wrong_case_error.value.code
    assert backend.blobs[result["cid"]] == blob
    assert hook._private_records[result["cid"]]["provenance"]["content_hash"] == provenance["content_hash"]
    assert hook.retrieve_evidence(result["cid"]) == secret
    assert result["remote_durable"] is False


def test_workspace_activation_injects_private_context(tmp_path):
    case = next(item for item in meaningful_cases() if item.storage_available and item.sources)
    locked = ComplaintWorkspaceService(tmp_path / "locked")
    locked_hook = EvidenceStorageHook(_Mediator())

    class _Carrier:
        def __init__(self, hook):
            self.evidence_storage = hook

    locked_receipt = locked.activate_private_evidence_hook(_Carrier(locked_hook), _OWNER, case.case_id)
    assert locked_receipt["status"] == "unavailable"
    assert locked_receipt["plaintext_fallback"] is False
    with pytest.raises(EvidenceStorageError) as locked_store:
        locked_hook.store_evidence(_private_bytes(case), "document", {"parse_document": False})
    assert locked_store.value.code in {"key_unavailable", "unlock_needed"}
    assert not list((tmp_path / "locked").rglob("*.cgpe"))

    opened = ComplaintWorkspaceService(tmp_path / "opened")
    created = opened.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    assert created.get("unlocked") is True or created.get("status") in {"available", "ready"}
    unlocked = opened.unlock_private_keys(passphrase=PASSPHRASE)
    assert unlocked.get("awaiting_user") is not True
    ready = opened.ensure_private_case_key(_OWNER, case.case_id)
    assert ready.get("data_key_id")
    hook = EvidenceStorageHook(_Mediator())
    receipt = opened.activate_private_evidence_hook(_Carrier(hook), _OWNER, case.case_id)
    assert receipt["status"] == "available"
    assert receipt["tenant_id"] == _OWNER
    assert receipt["case_id"] == case.case_id
    assert receipt["plaintext_fallback"] is False
    secret = _private_bytes(case)
    stored = hook.store_evidence(secret, "document", {"parse_document": False, "source_url": "synthetic://activated"})
    assert stored["private_artifact"] is True
    assert stored["remote_durable"] is False
    assert hook.retrieve_evidence(stored["cid"]) == secret
    written = [path.read_bytes() for path in (tmp_path / "opened").rglob("*") if path.is_file()]
    assert any(blob.startswith(b"CGPE") and secret not in blob for blob in written)
    assert all(secret not in blob for blob in written)
    with pytest.raises(WorkspacePersistenceError):
        opened._private_artifact_context(_OWNER, "missing-case-for-control")
