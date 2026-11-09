"""Faults, egress policy, and measurement receipts for private intake resume."""

from __future__ import annotations

import errno
import json
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from integrations.ipfs_datasets.storage import (
    InterviewSnapshotError,
    assemble_interview_snapshot,
    classify_intake_evidence,
    load_interview_snapshot,
    persist_interview_snapshot,
    run_one_gap_intake,
    source_binding,
)
from integrations.private_storage import (
    CaseManifestConflict,
    PrivateCryptoCapabilityError,
    count_verified_ciphertext_replicas,
    publish_case_manifest,
    read_case_manifest,
)

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

COMPLAINT = "SYNTHETIC-DUR006-COMPLAINT the assignment ended."
KEY = bytes(range(4, 36))
KEY_ID = "dur006-interview-key"
OTHER_KEY = bytes(range(40, 72))
ROOT = Path(__file__).resolve().parents[1]
IDENTITY = dict(
    protection="user_chosen_encrypted",
    tenant_id="dur006-tenant",
    case_id="dur006-case",
    principal_id="dur006-tenant",
)


def _snapshot(marker: str) -> dict:
    return assemble_interview_snapshot(
        session_id="dur006-session",
        revision="0",
        outcome_reason="awaiting_user",
        pending_inquiry={"question_id": "legal_context.event_date", "field": "event_date"},
        knowledge_graph={"entities": {"jurisdiction": {"fact_id": "fact-jurisdiction", "field": "jurisdiction", "value": marker}}, "provenance": {"source": "synthetic"}},
        dependency_graph={"mapping_status": "unresolved", "nodes": {}},
        provenance={"source": "synthetic"},
        unknown_items=[],
        deferred_items=[],
        complaint_text=COMPLAINT,
        transcript=[{"sender": "user", "message": marker}],
        exports={"status": "not_filed"},
        durability_payload={"facts": {"jurisdiction": {"fact_id": "fact-jurisdiction", "value": marker}}},
        revisions={"session_revision": 1, "question_revision": 1, "graph_revision": 1},
    )


def _persist(directory: Path, marker: str = "Oregon", **kwargs):
    return persist_interview_snapshot(
        directory, _snapshot(marker), key=KEY, key_id=KEY_ID, **IDENTITY, **kwargs,
    )


def _roles(marker: str) -> dict:
    body = f"role:{marker}".encode()
    return {
        name: {"body": body, "revision": name + "-1"}
        for name in ("answer", "fact_graph", "legal_rule_source", "evaluation", "proof")
    }


def test_local_mode_makes_no_socket_or_provider_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args, **_kwargs):
        raise AssertionError("local private intake opened a socket")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    result = run_one_gap_intake(
        tmp_path / "local", mode="local_private", key=KEY, key_id=KEY_ID, complaint_text=COMPLAINT, turns=1,
    )
    assert result["captures"] == []
    assert result["fact_ids"] == ["fact-jurisdiction"]


def test_fault_matrix_preserves_the_last_good_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "faults"
    first = _persist(directory, "Oregon")
    assert first["snapshot"]["revision"] == "1"
    second = _persist(directory, "Oregon", expected_revision="1")
    assert second["snapshot"]["revision"] == "2"

    with pytest.raises(InterviewSnapshotError) as wrong:
        load_interview_snapshot(directory, key=OTHER_KEY, key_id="other", **IDENTITY)
    assert wrong.value.code == "authentication_failed"
    assert load_interview_snapshot(directory, key=KEY, key_id=KEY_ID, **IDENTITY)["snapshot"]["revision"] == "2"

    head = directory / "head.json"
    recorded = json.loads(head.read_text())
    blob = directory / recorded["blob"]
    original = blob.read_bytes()
    blob.write_bytes(b"tampered-ciphertext")
    recovered = load_interview_snapshot(directory, key=KEY, key_id=KEY_ID, **IDENTITY)
    assert recovered["recovered"] is True
    assert recovered["snapshot"]["revision"] == "1"
    assert recovered["snapshot"]["graphs"]["knowledge_graph"]["entities"]["jurisdiction"]["value"] == "Oregon"
    blob.write_bytes(original)

    def no_crypto():
        raise PrivateCryptoCapabilityError("synthetic crypto missing")

    monkeypatch.setattr("integrations.private_storage.load_aesgcm", no_crypto)
    before = sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file())
    with pytest.raises(InterviewSnapshotError) as missing:
        _persist(directory, "Oregon-again", expected_revision="2")
    assert missing.value.code == "private_crypto_unavailable"
    after = sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file())
    assert after == before
    monkeypatch.undo()

    with pytest.raises(InterviewSnapshotError) as stale:
        _persist(directory, "Oregon", expected_revision="0")
    assert stale.value.code == "revision_conflict"
    assert load_interview_snapshot(directory, key=KEY, key_id=KEY_ID, **IDENTITY)["snapshot"]["revision"] == "2"

    codes: list[str] = []
    barrier = threading.Barrier(2)

    def contest() -> None:
        barrier.wait()
        try:
            _persist(directory, "Oregon", expected_revision="2")
            codes.append("committed")
        except InterviewSnapshotError as exc:
            codes.append(exc.code)

    threads = [threading.Thread(target=contest) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(codes) == ["committed", "revision_conflict"]
    assert load_interview_snapshot(directory, key=KEY, key_id=KEY_ID, **IDENTITY)["snapshot"]["revision"] == "3"

    def full_disk(_payload: bytes) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    with pytest.raises(OSError) as disk:
        _persist(directory, "Oregon", expected_revision="3", writer=full_disk)
    assert disk.value.errno == errno.ENOSPC
    assert load_interview_snapshot(directory, key=KEY, key_id=KEY_ID, **IDENTITY)["snapshot"]["revision"] == "3"

    with pytest.raises(InterviewSnapshotError) as crashed:
        _persist(directory, "replay-once", expected_revision="3", fail_before_head=True)
    assert crashed.value.code == "durability_unproven"
    assert load_interview_snapshot(directory, key=KEY, key_id=KEY_ID, **IDENTITY)["snapshot"]["revision"] == "3"
    replayed = _persist(directory, "replay-once", expected_revision="3")
    assert replayed["snapshot"]["revision"] == "4"
    assert replayed["snapshot"]["graphs"]["knowledge_graph"]["entities"]["jurisdiction"]["value"] == "replay-once"
    assert load_interview_snapshot(directory, key=KEY, key_id=KEY_ID, **IDENTITY)["snapshot"]["revision"] == "4"

    manifest_root = tmp_path / "manifest"
    published = publish_case_manifest(
        manifest_root, tenant_id="dur006-tenant", case_id="dur006-case", principal_id="dur006-tenant",
        key=KEY, key_id=KEY_ID, expected_head="", expected_hash="", artifacts=_roles("one"), private_names={"filename": "one.txt"},
    )
    with pytest.raises(CaseManifestConflict):
        publish_case_manifest(
            manifest_root, tenant_id="dur006-tenant", case_id="dur006-case", principal_id="dur006-tenant",
            key=KEY, key_id=KEY_ID, expected_head="", expected_hash="", artifacts=_roles("stale"), private_names={"filename": "stale.txt"},
        )
    current = read_case_manifest(
        manifest_root, tenant_id="dur006-tenant", case_id="dur006-case", principal_id="dur006-tenant", key=KEY, key_id=KEY_ID,
    )
    assert current["generation"] == published.generation
    replica = count_verified_ciphertext_replicas([
        {"provider_id": "remote-a", "state": "unavailable", "digest_match": False, "version_match": False},
        {"provider_id": "pin-b", "state": "deferred", "digest_match": False, "version_match": False},
    ])
    assert replica["verified_replicas"] == 0
    assert {row["state"] for row in replica["uncounted"]} == {"unavailable", "deferred"}


def test_fresh_process_reloads_the_same_facts(tmp_path: Path) -> None:
    directory = tmp_path / "fresh"
    run_one_gap_intake(directory, mode="local_private", key=KEY, key_id=KEY_ID, complaint_text=COMPLAINT, turns=2)
    script = """
import json, sys
from integrations.ipfs_datasets.storage import load_interview_snapshot
loaded = load_interview_snapshot(
    sys.argv[1], protection='user_chosen_encrypted', tenant_id='dur006-tenant',
    case_id='dur006-case', principal_id='dur006-tenant', key=bytes.fromhex(sys.argv[2]), key_id=sys.argv[3],
)
facts = loaded['snapshot']['durability_payload']['facts']
print(json.dumps({
    'asked': loaded['snapshot']['durability_payload']['asked'],
    'facts': sorted(facts),
    'pending': loaded['snapshot']['pending_inquiry'].get('question_id'),
    'mapping': loaded['snapshot']['graphs']['dependency_graph']['mapping_status'],
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(directory), KEY.hex(), KEY_ID],
        cwd=str(ROOT), check=False, capture_output=True, text=True, timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["facts"] == ["event_date", "jurisdiction"]
    assert payload["asked"] == ["legal_context.jurisdiction", "legal_context.event_dates"]
    assert payload["pending"] == "legal_context.applicable_law_date"
    assert payload["mapping"] == "unresolved"


def test_only_locally_measured_behavioral_receipts_are_complete() -> None:
    storage_binding = source_binding(ROOT / "integrations/ipfs_datasets/storage.py")
    legal_binding = source_binding(ROOT / "integrations/ipfs_datasets/legal.py")
    assert storage_binding["sha256"] == source_binding(ROOT / "integrations/ipfs_datasets/storage.py")["sha256"]
    assertions = [{
        "kind": "behavioral",
        "name": "fact-count",
        "expected": 5,
        "observed": 5,
    }]
    local = classify_intake_evidence(
        measurement="measured-local-node",
        assertions=assertions,
        source_bindings=[storage_binding, legal_binding],
        cid="bafyexamplelocalmeasured",
    )
    assert local["complete"] is True
    assert local["tier"] == "local_node"
    assert local["cid_closes_task"] is False
    hermetic = classify_intake_evidence(
        measurement="measured-hermetic",
        assertions=assertions,
        source_bindings=[storage_binding, legal_binding],
        cid="bafyhermeticnonempty",
    )
    remote = classify_intake_evidence(
        measurement="permitted-remote-provider",
        assertions=assertions,
        source_bindings=[storage_binding, legal_binding],
        cid="bafyremotenonempty",
    )
    unbound = classify_intake_evidence(
        measurement="measured-local-node",
        assertions=[{"kind": "substring", "name": "CIMP-DUR-006", "expected": "CIMP-DUR-006", "observed": "CIMP-DUR-006"}],
        source_bindings=[storage_binding],
        cid="bafynonemptycid",
    )
    mismatched = classify_intake_evidence(
        measurement="measured-local-node",
        assertions=[{"kind": "behavioral", "name": "fact-count", "expected": 5, "observed": 4}],
        source_bindings=[storage_binding, legal_binding],
        cid="bafynonemptycid",
    )
    assert hermetic["complete"] is False and hermetic["tier"] == "hermetic_fake"
    assert remote["complete"] is False and remote["tier"] == "remote_provider"
    assert unbound["complete"] is False
    assert mismatched["complete"] is False
    assert hermetic["cid"] and remote["cid"]
