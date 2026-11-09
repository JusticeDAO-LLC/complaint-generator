"""Complete encrypted case revisions on the existing private manifest CAS.

Positive cases seal knowledge and dependency graphs, inquiries, proof
references, grants, and workflow revisions with the existing case roles.
Negative cases cover a missing owner, a crash before the head moves, a
concurrent writer, and a replay that must not mint an empty replacement.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService, WorkspacePersistenceError

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ACTOR = "principal-case-revision"
PASSPHRASE = "synthetic complete case revision passphrase"
ROLES = (
    "answer",
    "fact_graph",
    "legal_rule_source",
    "evaluation",
    "proof",
    "knowledge_graph",
    "dependency_graph",
    "inquiries",
    "proof_references",
    "grants",
    "workflow_revisions",
)


def _service(tmp_path: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(tmp_path / "sessions")
    created = service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    assert created.get("unlocked") is True or created.get("status") in {"available", "ready"}
    service.ensure_private_case_key(ACTOR, ACTOR)
    return service


def _snapshot(marker: str, revision: str) -> dict:
    owners = {}
    for name in ROLES:
        owners[name] = {
            "body": f"{name}:{marker}".encode(),
            "revision": f"{name}-{revision}",
        }
    owners["knowledge_graph"]["body"] = f'{{"entities":["{marker}"],"revision":"{revision}"}}'.encode()
    owners["dependency_graph"]["body"] = f'{{"edges":["{marker}"]}}'.encode()
    owners["inquiries"]["body"] = f'{{"inquiry_id":"inq-{revision}","text":"{marker}"}}'.encode()
    owners["proof_references"]["body"] = f'{{"proof_id":"proof-{revision}","marker":"{marker}"}}'.encode()
    owners["grants"]["body"] = f'{{"grant_id":"grant-{revision}","marker":"{marker}"}}'.encode()
    owners["workflow_revisions"]["body"] = f'{{"workflow_revision":"wf-{revision}","marker":"{marker}"}}'.encode()
    return owners


def _commit(service: ComplaintWorkspaceService, marker: str, revision: str, **kwargs):
    return service.commit_complete_encrypted_case_revision(
        ACTOR,
        _snapshot(marker, revision),
        private_names={"filename": f"{marker}.txt"},
        **kwargs,
    )


def test_complete_snapshot_seals_graphs_inquiries_proofs_grants_and_workflow(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = _commit(service, "synthetic-alpha", "1")
    assert first["committed"] is True
    assert first["complete"] is True
    assert first["empty_replacement"] is False
    assert first["generation"] and len(first["generation"]) == 64
    assert first["parent_generation"] is None
    opened = service.read_complete_encrypted_case_revision(ACTOR)
    assert opened is not None and opened["complete"] is True
    for name in ROLES:
        assert b"synthetic-alpha" in opened["roles"][name]
    assert b"entities" in opened["roles"]["knowledge_graph"]
    assert b"edges" in opened["roles"]["dependency_graph"]
    assert b"inq-1" in opened["roles"]["inquiries"]
    assert b"proof-1" in opened["roles"]["proof_references"]
    assert b"grant-1" in opened["roles"]["grants"]
    assert b"wf-1" in opened["roles"]["workflow_revisions"]
    assert opened["private_names"]["filename"] == "synthetic-alpha.txt"
    second = _commit(
        service,
        "synthetic-beta",
        "2",
        expected_head=first["generation"],
        expected_hash=first["manifest_hash"],
    )
    assert second["parent_generation"] == first["generation"]
    reread = service.read_complete_encrypted_case_revision(ACTOR)
    assert b"synthetic-beta" in reread["roles"]["workflow_revisions"]
    assert b"wf-2" in reread["roles"]["workflow_revisions"]


def test_missing_owner_does_not_replace_an_acknowledged_revision(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = _commit(service, "kept", "1")
    partial = _snapshot("dropped", "2")
    del partial["grants"]
    with pytest.raises(WorkspacePersistenceError) as rejected:
        service.commit_complete_encrypted_case_revision(
            ACTOR,
            partial,
            expected_head=first["generation"],
            expected_hash=first["manifest_hash"],
        )
    assert rejected.value.code == "role_missing"
    opened = service.read_complete_encrypted_case_revision(ACTOR)
    assert opened["generation"] == first["generation"]
    assert b"kept" in opened["roles"]["grants"]
    with pytest.raises(WorkspacePersistenceError) as empty:
        service.commit_complete_encrypted_case_revision(ACTOR, {})
    assert empty.value.code == "role_missing"
    assert service.read_complete_encrypted_case_revision(ACTOR)["generation"] == first["generation"]


def test_crash_before_head_preserves_the_acknowledged_revision(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = _commit(service, "durable", "1")
    with pytest.raises(WorkspacePersistenceError) as crashed:
        _commit(
            service,
            "unacknowledged",
            "2",
            expected_head=first["generation"],
            expected_hash=first["manifest_hash"],
            fail_before_head=True,
        )
    assert crashed.value.code == "interrupted"
    opened = service.read_complete_encrypted_case_revision(ACTOR)
    assert opened["generation"] == first["generation"]
    assert opened["manifest_hash"] == first["manifest_hash"]
    assert b"durable" in opened["roles"]["knowledge_graph"]
    assert b"unacknowledged" not in opened["roles"]["answer"]
    replay = service.replay_acknowledged_encrypted_case_revision(
        ACTOR,
        generation=first["generation"],
        manifest_hash=first["manifest_hash"],
    )
    assert replay["state"] == "replayed"
    assert replay["committed"] is False
    assert replay["empty_replacement"] is False
    assert service.read_complete_encrypted_case_revision(ACTOR)["generation"] == first["generation"]


def test_concurrent_writers_keep_one_acknowledged_revision(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = _commit(service, "base", "1")
    barrier = threading.Barrier(2)
    results: list = []

    def attempt(marker: str, revision: str) -> None:
        barrier.wait()
        try:
            results.append(_commit(
                service,
                marker,
                revision,
                expected_head=first["generation"],
                expected_hash=first["manifest_hash"],
            ))
        except WorkspacePersistenceError as exc:
            results.append(exc)

    threads = [
        threading.Thread(target=attempt, args=("left", "2")),
        threading.Thread(target=attempt, args=("right", "3")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    committed = [item for item in results if isinstance(item, dict)]
    conflicts = [item for item in results if isinstance(item, WorkspacePersistenceError)]
    assert len(committed) == 1
    assert len(conflicts) == 1
    assert conflicts[0].code == "manifest_conflict"
    opened = service.read_complete_encrypted_case_revision(ACTOR)
    assert opened["generation"] == committed[0]["generation"]
    assert opened["generation"] != first["generation"]
    body = b"".join(opened["roles"].values())
    assert (b"left" in body) ^ (b"right" in body)
    assert b"base" not in opened["roles"]["answer"]
    replay = service.replay_acknowledged_encrypted_case_revision(
        ACTOR,
        generation=first["generation"],
        manifest_hash=first["manifest_hash"],
    )
    assert replay["state"] == "preserved"
    assert replay["generation"] == opened["generation"]
    assert service.read_complete_encrypted_case_revision(ACTOR)["roles"]["answer"] == opened["roles"]["answer"]


def test_replay_of_a_missing_acknowledgement_does_not_start_an_empty_case(tmp_path: Path) -> None:
    service = _service(tmp_path)
    assert service.read_complete_encrypted_case_revision(ACTOR) is None
    missing = service.replay_acknowledged_encrypted_case_revision(
        ACTOR,
        generation="ab" * 32,
        manifest_hash="cd" * 32,
    )
    assert missing["committed"] is False
    assert missing["state"] == "recoverable"
    assert missing["generation"] is None
    assert service.read_complete_encrypted_case_revision(ACTOR) is None
    repository = service.case_manifest_repository(ACTOR, ACTOR)
    manifest_root = repository / "case-manifest"
    if manifest_root.exists():
        names = [path.name for path in manifest_root.rglob("*") if path.is_file()]
        assert "case-head" not in names
