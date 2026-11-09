"""Atomic encrypted grounded interview snapshots.

Synthetic private fixtures only. A commit binds the current graph revisions,
source references, conditional IR and proof statuses, hook receipts, pending
inquiry, and stop policy. Conflicts, interrupted writes, and corrupt
candidates leave the previous head readable. A cold read does not extract
narrative or replay hooks. Snapshot existence does not claim remote replicas.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService, WorkspacePersistenceError
from integrations.ipfs_datasets.storage import (
    InterviewSnapshotError,
    assemble_interview_snapshot,
    load_interview_snapshot,
    persist_interview_snapshot,
)
from tests.mgnd_fixtures import CASE_LABELS, PASSPHRASE, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_OWNER = "synthetic-mgnd-34"


def _identity(case_id: str) -> dict[str, str]:
    return {
        "protection": "user_chosen_encrypted",
        "tenant_id": _OWNER,
        "case_id": case_id,
        "principal_id": _OWNER,
    }


def _key(case_id: str) -> tuple[str, bytes]:
    return "mgnd34-" + case_id, hashlib.sha256(b"mgnd34-key\x00" + case_id.encode()).digest()


def _owners(case) -> dict:
    source_rows = []
    for source in case.sources:
        source_rows.append({
            "source_id": source.authority_id,
            "source_version": source.version,
            "content_hash": source.source_sha256,
            "span_start": 0,
            "span_end": len(source.source_bytes),
            "role": "retrieved_public_law",
            "text": source.source_text,
        })
    if case.label == "missing_authority":
        public_status = "external_missing"
        ir_status = "unavailable"
    elif case.label == "unknown":
        public_status = "external_unverified"
        ir_status = "unknown"
    elif case.label == "contradiction":
        public_status = "external_present"
        ir_status = "conditional"
    else:
        public_status = "external_present"
        ir_status = "not_compiled"
    proof = "unresolved" if case.label == "contradiction" else "not_run"
    reason = {
        "baseline": "awaiting_user",
        "missing_authority": "needs_answer",
        "contradiction": "awaiting_user",
        "unknown": "deferred_unknown",
        "cancellation": "cancelled",
        "storage_outage": "provider_unavailable",
    }[case.label]
    request_id = hashlib.sha256(case.case_id.encode()).hexdigest()[:32]
    return {
        "factual_graph": {
            "revision": "fact-" + case.label,
            "artifact_kind": "factual-graph",
            "artifact_revision": "fact-graph-1",
            "ciphertext_storage_id": "bafy" + hashlib.sha256(case.case_id.encode()).hexdigest()[:55],
            "graph_id": "graph-" + case.label,
            "content_hash": hashlib.sha256(b"fact-" + case.case_id.encode()).hexdigest(),
        },
        "legal_graph": {
            "revision": "law-" + case.label,
            "graph_id": "legal-" + case.label,
            "content_hash": hashlib.sha256(b"law-" + case.case_id.encode()).hexdigest(),
        },
        "source_references": source_rows,
        "conditional_ir": {"status": ir_status, "receipt_ref": "ir-" + case.label},
        "proof_statuses": [{"target_id": "element-" + case.label, "status": proof, "receipt_ref": "proof-" + case.label}],
        "hook_receipts": [{
            "operation": "extract_facts",
            "purpose": "extract_facts",
            "request_id": request_id,
            "status": "available",
            "accepted_graph_revision": "fact-" + case.label,
            "invocation_label": "fake",
            "live_model_identity_verified": False,
            "prompt": case.narrative.text,
            "provider_replayed": True,
        }],
        "pending_inquiry": {
            "inquiry_id": "inq-" + hashlib.sha256(case.label.encode()).hexdigest()[:16],
            "revision": 2,
            "objective_id": "objective-" + case.label,
            "target_id": "target-" + case.label,
            "target_revision": "target-rev-2",
            "status": "open",
            "source_references_status": "host_selected" if source_rows else "unknown",
            "grounding_status": "host_selected",
            "question": case.narrative.text,
        },
        "stop_policy": {
            "reason": reason,
            "action": "await_user" if reason == "awaiting_user" else "stop" if reason == "cancelled" else "unknown",
            "legal_sufficiency": False,
            "worker_stalled": reason == "awaiting_user",
        },
        "external_dependencies": {
            "public_law": {"status": public_status, "copied_into_snapshot": True},
            "ephemeral_index": {"status": "rebuildable", "durable": True},
            "remote_replicas": {"existence_claimed": True},
        },
    }


def _snapshot(case, owners: dict):
    return assemble_interview_snapshot(
        session_id="session-" + case.label,
        revision="0",
        outcome_reason=owners["stop_policy"]["reason"],
        pending_inquiry=owners["pending_inquiry"],
        knowledge_graph={"graph_id": "graph-" + case.label, "graph_version": "1", "entities": [{"id": "fact-" + case.label}]},
        dependency_graph={"graph_id": "legal-" + case.label, "graph_version": "1", "nodes": [{"id": "element-" + case.label}]},
        provenance={"source": "synthetic-mgnd-34"},
        unknown_items=[{"field": "forum"}] if case.label == "unknown" else [],
        deferred_items=[],
        complaint_text=case.narrative.text,
        transcript=[{"sender": "user", "message": case.narrative.text}],
        exports={"status": "not_filed"},
        durability_payload={"writer": "test"},
        revisions={"session_revision": 2, "question_revision": 2, "graph_revision": "fact-" + case.label},
        grounding=owners,
    )


def _head(directory: Path) -> dict:
    return json.loads((directory / "head.json").read_text(encoding="utf-8"))


def test_case_list_is_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS


def test_one_transaction_binds_current_owners_and_cold_read_matches(tmp_path):
    stored = []
    for case in meaningful_cases():
        if not case.storage_available:
            continue
        owners = _owners(case)
        document = _snapshot(case, owners)
        grounding = document["grounding"]
        assert grounding["schema"] == "grounded-snapshot-bindings-v1"
        assert grounding["recorded"] is True
        assert grounding["factual_graph"]["revision"] == "fact-" + case.label
        assert grounding["legal_graph"]["revision"] == "law-" + case.label
        assert grounding["conditional_ir"]["status"]
        assert grounding["proof_statuses"]
        assert grounding["hook_receipts"]
        assert grounding["pending_inquiry"]["inquiry_id"].startswith("inq-")
        assert grounding["stop_policy"]["reason"] == owners["stop_policy"]["reason"]
        assert grounding["stop_policy"]["legal_sufficiency"] is False
        assert grounding["replay"]["narrative_reextracted"] is False
        assert grounding["replay"]["hooks_replayed"] is False
        assert grounding["replay"]["model_calls"] == 0
        if grounding["stop_policy"]["awaiting_user"]:
            assert grounding["stop_policy"]["worker_stalled"] is False
        dependencies = grounding["external_dependencies"]
        assert dependencies["public_law"]["copied_into_snapshot"] is False
        assert dependencies["public_law"]["dependency"] == "external"
        assert dependencies["ephemeral_index"]["durable"] is False
        assert dependencies["remote_replicas"]["existence_claimed"] is False
        assert dependencies["remote_replicas"]["snapshot_is_replica_proof"] is False
        encoded = json.dumps(document)
        for source in case.sources:
            assert source.source_text not in encoded
        assert case.narrative.text not in json.dumps(grounding["hook_receipts"])
        assert grounding["hook_receipts"][0]["provider_replayed"] is False
        assert grounding["hook_receipts"][0]["prompt_logged"] is False
        directory = tmp_path / case.label
        key_id, key = _key(case.case_id)
        saved = persist_interview_snapshot(
            directory, document, key=key, key_id=key_id, expected_revision=None, **_identity(case.case_id),
        )
        head = _head(directory)
        assert head["remote_replicas_claimed"] is False
        assert head["snapshot_is_replica_proof"] is False
        assert case.narrative.text.encode() not in (directory / "head.json").read_bytes()
        loaded = load_interview_snapshot(directory, key=key, key_id=key_id, **_identity(case.case_id))
        assert loaded["cold_read"]["narrative_reextracted"] is False
        assert loaded["cold_read"]["hooks_replayed"] is False
        assert loaded["cold_read"]["model_calls"] == 0
        assert loaded["snapshot"]["grounding"] == saved["snapshot"]["grounding"]
        assert loaded["snapshot"]["graphs"] == saved["snapshot"]["graphs"]
        assert loaded["snapshot"]["complaint_text"] == case.narrative.text
        assert loaded["snapshot"]["revisions"]["factual_graph_revision"] == "fact-" + case.label
        assert loaded["snapshot"]["revisions"]["legal_graph_revision"] == "law-" + case.label
        stored.append(case.label)
    assert stored


def test_conflict_interrupt_and_corrupt_candidate_keep_the_prior_head(tmp_path):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    directory = tmp_path / "atomic"
    key_id, key = _key(case.case_id)
    identity = _identity(case.case_id)
    first = persist_interview_snapshot(
        directory, _snapshot(case, _owners(case)), key=key, key_id=key_id, **identity,
    )
    head_bytes = (directory / "head.json").read_bytes()
    revision = first["snapshot"]["revision"]

    with pytest.raises(InterviewSnapshotError) as conflict:
        persist_interview_snapshot(
            directory, _snapshot(case, _owners(case)), key=key, key_id=key_id,
            expected_revision="0", **identity,
        )
    assert conflict.value.code == "revision_conflict"
    assert (directory / "head.json").read_bytes() == head_bytes

    def _fail(_payload: bytes) -> None:
        raise OSError("synthetic interrupted write")

    with pytest.raises(OSError):
        persist_interview_snapshot(
            directory, _snapshot(case, _owners(case)), key=key, key_id=key_id,
            expected_revision=revision, writer=_fail, **identity,
        )
    assert (directory / "head.json").read_bytes() == head_bytes

    with pytest.raises(InterviewSnapshotError) as interrupted:
        persist_interview_snapshot(
            directory, _snapshot(case, _owners(case)), key=key, key_id=key_id,
            expected_revision=revision, fail_before_head=True, **identity,
        )
    assert interrupted.value.code == "durability_unproven"
    assert (directory / "head.json").read_bytes() == head_bytes

    def _corrupt(dir_fd: int, relative: str) -> None:
        parent_name, _, name = relative.partition("/")
        parent = os.open(parent_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
        try:
            handle = os.open(name, os.O_WRONLY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                os.write(handle, b"corrupt-candidate")
            finally:
                os.close(handle)
        finally:
            os.close(parent)

    with pytest.raises(InterviewSnapshotError) as corrupt:
        persist_interview_snapshot(
            directory, _snapshot(case, _owners(case)), key=key, key_id=key_id,
            expected_revision=revision, before_head=_corrupt, **identity,
        )
    assert corrupt.value.code == "corrupt_candidate"
    assert (directory / "head.json").read_bytes() == head_bytes
    loaded = load_interview_snapshot(directory, key=key, key_id=key_id, **identity)
    assert loaded["snapshot"]["revision"] == revision
    assert loaded["snapshot"]["grounding"] == first["snapshot"]["grounding"]
    assert loaded["recovered"] is False


def test_legacy_snapshot_does_not_invent_bindings(tmp_path):
    case = next(item for item in meaningful_cases() if item.label == "unknown")
    document = assemble_interview_snapshot(
        session_id="legacy-session",
        revision="0",
        outcome_reason="unknown",
        pending_inquiry={"status": "unknown"},
        knowledge_graph={"status": "unknown"},
        dependency_graph={"status": "unknown"},
        provenance={"status": "unknown"},
        unknown_items=[],
        deferred_items=[],
        complaint_text="",
        transcript=[],
        exports={"status": "unknown"},
        durability_payload={"status": "unknown"},
        revisions={"session_revision": "unknown", "question_revision": "unknown", "graph_revision": "unknown"},
    )
    assert document["grounding"]["recorded"] is False
    assert document["grounding"]["factual_graph"]["status"] == "unknown"
    assert document["grounding"]["factual_graph"]["revision"] == "unknown"
    assert document["grounding"]["legal_graph"]["revision"] == "unknown"
    assert document["grounding"]["pending_inquiry"]["inquiry_id"] == ""
    assert document["grounding"]["hook_receipts"] == []
    assert document["grounding"]["external_dependencies"]["remote_replicas"]["existence_claimed"] is False
    directory = tmp_path / "legacy"
    key_id, key = _key(case.case_id)
    persist_interview_snapshot(directory, document, key=key, key_id=key_id, **_identity(case.case_id))
    loaded = load_interview_snapshot(directory, key=key, key_id=key_id, **_identity(case.case_id))
    assert loaded["snapshot"]["grounding"]["recorded"] is False
    assert loaded["snapshot"]["grounding"]["factual_graph"]["revision"] == "unknown"
    assert loaded["cold_read"]["model_calls"] == 0


def test_storage_outage_does_not_publish_a_head(tmp_path):
    case = next(item for item in meaningful_cases() if item.label == "storage_outage")
    assert case.storage_available is False
    directory = tmp_path / "outage"

    def _unavailable(_payload: bytes) -> None:
        raise OSError("synthetic storage unavailable")

    with pytest.raises(OSError):
        persist_interview_snapshot(
            directory,
            _snapshot(case, _owners(case)),
            key=_key(case.case_id)[1],
            key_id=_key(case.case_id)[0],
            writer=_unavailable,
            **_identity(case.case_id),
        )
    assert not (directory / "head.json").exists()


def test_workspace_commit_uses_saved_owners_without_replay(tmp_path, monkeypatch):
    case = next(item for item in meaningful_cases() if item.label == "baseline")
    service = ComplaintWorkspaceService(tmp_path / "workspace")
    created = service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    assert created.get("unlocked") is True or created.get("status") in {"available", "ready"}
    service.unlock_private_keys(passphrase=PASSPHRASE)
    assert service.ensure_private_case_key(_OWNER, _OWNER).get("data_key_id")

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("snapshot commit replayed a mediator")

    monkeypatch.setattr("mediator.mediator.Mediator", _forbidden)
    state = service._load_state(_OWNER)
    owners = _owners(case)
    state["shared_interview"] = {
        "session_id": "session-baseline",
        "session_revision": 2,
        "knowledge_graph": {"graph_id": "graph-baseline", "graph_version": "1"},
        "dependency_graph": {"graph_id": "legal-baseline", "graph_version": "1"},
        "pending_inquiry": owners["pending_inquiry"],
        "unknown_reasons": [],
        "capped_reasons": [],
    }
    state["factual_graph_binding"] = owners["factual_graph"]
    state["legal_graph_binding"] = owners["legal_graph"]
    state["conditional_ir"] = owners["conditional_ir"]
    state["proof_history"] = owners["proof_statuses"]
    state["intake_router"] = {"receipts": owners["hook_receipts"]}
    state["stop_policy"] = owners["stop_policy"]
    state["external_dependencies"] = owners["external_dependencies"]
    state["source_references"] = owners["source_references"]
    narrative = state.get("original_complaint")
    if isinstance(narrative, dict):
        narrative["text"] = case.narrative.text
    service._save_state(state)
    calls = {"model": 0}

    def _model(*_args, **_kwargs):
        calls["model"] += 1
        raise AssertionError("model call")

    monkeypatch.setattr("integrations.ipfs_datasets.llm.generate_text_with_metadata", _model)
    saved = service.commit_complete_grounded_snapshot(_OWNER)
    assert calls["model"] == 0
    assert saved["provider_replayed"] is False
    assert saved["hooks_replayed"] is False
    assert saved["snapshot"]["grounding"]["factual_graph"]["revision"] == "fact-baseline"
    assert saved["snapshot"]["grounding"]["legal_graph"]["revision"] == "law-baseline"
    assert saved["snapshot"]["grounding"]["hook_receipts"][0]["request_id"]
    assert saved["snapshot"]["complaint_text"] == case.narrative.text
    fresh = ComplaintWorkspaceService(tmp_path / "workspace")
    fresh.unlock_private_keys(passphrase=PASSPHRASE)
    loaded = fresh.load_complete_interview_snapshot(_OWNER)
    assert loaded["cold_read"]["hooks_replayed"] is False
    assert loaded["snapshot"]["grounding"] == saved["snapshot"]["grounding"]
    assert calls["model"] == 0

    locked = ComplaintWorkspaceService(tmp_path / "locked")
    with pytest.raises(WorkspacePersistenceError) as denied:
        locked.commit_complete_grounded_snapshot(_OWNER)
    assert denied.value.code in {"unlock_needed", "key_unavailable", "private_crypto_unavailable"}
