"""Joined intake revision recovery over the Kit WAL.

Synthetic repositories only. Upstream Kit WAL suites are a separate
compatibility qualification and do not replace these assertions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from applications.complaint_workspace import (
    ComplaintWorkspaceService,
    WorkspacePersistenceError,
    WorkspaceAccess,
    workspace_access_scope,
)
from integrations.private_storage import (
    PrivateRevisionError,
    PrivateRevisionInterrupted,
    _prefer_vendored_kit,
    commit_acknowledged_by_receipt,
    commit_private_revision,
    read_private_revision,
    recover_private_revision,
)

_prefer_vendored_kit()
from ipfs_kit_py.core.wal.contracts import WALAcknowledgementMode
from ipfs_kit_py.core.wal.coordinator import WALTransactionCrash
from ipfs_kit_py.core.wal.writer import WALQueueFullError, WALWriter

SENTINEL = "SENTINEL-DUR003-answer-7c1e"
KEY = bytes(range(1, 33))
KEY_ID = "k-opaque"
OTHER_KEY = bytes(range(33, 65))
TENANT = "tenant-a"
CASE = "case-a"
PRINCIPAL = "tenant-a"

BOUNDARIES = (
    "before_begin",
    "after_begin",
    "before_intent",
    "after_intent",
    "before_effect",
    "after_effect",
    "before_commit",
    "after_commit",
)

UPSTREAM_WAL_SUITES = (
    "tests/runtime_readiness/wal/test_wal_writer.py",
    "tests/runtime_readiness/wal/test_wal_recovery.py",
    "tests/runtime_readiness/wal/test_joined_crash_matrix.py",
)


def _payloads(answer: str, effect_id: str, revision: str) -> tuple[bytes, bytes, bytes]:
    session = {
        "intake_answers": {"harm": answer},
        "intake_history": [{"effect_id": effect_id, "question_id": "harm"}],
        "private_revision": revision,
    }
    graph = {"relationships": [{"id": effect_id, "kind": "intake-answer", "revision": revision}]}
    proof = {"entries": [{"effect_id": effect_id, "kind": "intake-revision", "revision": revision}]}
    return (
        json.dumps(session, sort_keys=True).encode("utf-8"),
        json.dumps(graph, sort_keys=True).encode("utf-8"),
        json.dumps(proof, sort_keys=True).encode("utf-8"),
    )


def _commit(root: Path, *, answer: str = SENTINEL, effect: str = "effect-1", transaction: str = "tx-1", expected: str | None = "0", **kwargs):
    revision = str(int(expected or "0") + 1)
    session, graph, proof = _payloads(answer, effect, revision)
    return commit_private_revision(
        root,
        tenant_id=TENANT,
        case_id=CASE,
        principal_id=PRINCIPAL,
        key=KEY,
        key_id=KEY_ID,
        expected_revision=expected,
        session=session,
        fact_graph=graph,
        proof=proof,
        transaction_id=transaction,
        effect_id=effect,
        **kwargs,
    )


def _crash(boundary: str):
    def inject(name: str, transaction_id: str | None = None) -> None:
        del transaction_id
        if name == boundary:
            raise WALTransactionCrash(name)

    return inject


def _scan(root: Path) -> list[str]:
    hits = []
    needle = SENTINEL.encode("utf-8")
    key_needle = KEY
    for path in root.rglob("*"):
        if SENTINEL in path.name or "passphrase" in path.name.lower() or path.name.endswith(".key"):
            hits.append(str(path))
        if path.is_file() and not path.is_symlink():
            data = path.read_bytes()
            if needle in data or key_needle in data:
                # Ciphertext may theoretically collide; authenticated plaintext must not.
                if path.suffix in {".jsonl", ".rev", ".tmp"} or "wal" in path.parts or path.name.startswith("."):
                    hits.append(str(path))
                elif path.parent.name != "o" and path.name != "head.cgpe":
                    hits.append(str(path))
    return hits


def _visible(root: Path) -> dict | None:
    return read_private_revision(
        root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )


def test_receipt_not_buffered_or_queued(tmp_path: Path) -> None:
    writer = WALWriter(tmp_path / "wal")
    try:
        buffered = writer.append("mutate", acknowledgement_mode=WALAcknowledgementMode.BUFFERED, record_key="b")
        queued = writer.append("mutate", acknowledgement_mode=WALAcknowledgementMode.QUEUED, record_key="q")
        durable = writer.append(
            "mutate",
            acknowledgement_mode=WALAcknowledgementMode.WAL_FSYNC_PARENT,
            record_key="d",
        )
    finally:
        writer.close()
    assert commit_acknowledged_by_receipt(buffered) is False
    assert commit_acknowledged_by_receipt(queued) is False
    assert buffered.fsync_receipt is None
    assert durable.fsync_receipt is not None
    assert commit_acknowledged_by_receipt(durable) is True
    assert durable.durable is True


def test_commit_publishes_one_revision_without_plaintext_journal(tmp_path: Path) -> None:
    publication = _commit(tmp_path)
    assert publication.committed is True
    assert publication.network_pinned is False
    assert publication.receipt_count >= 1
    assert publication.acknowledgement_mode == WALAcknowledgementMode.WAL_FSYNC_PARENT.value
    opened = _visible(tmp_path)
    assert opened is not None
    assert json.loads(opened["session"])["intake_answers"]["harm"] == SENTINEL
    assert len(json.loads(opened["fact_graph"])["relationships"]) == 1
    assert len(json.loads(opened["proof"])["entries"]) == 1
    assert opened["manifest"]["transaction_id"] == "tx-1"
    assert opened["manifest"]["effect_id"] == "effect-1"
    assert _scan(tmp_path) == []
    again = recover_private_revision(
        tmp_path, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    twice = recover_private_revision(
        tmp_path, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    assert again.committed is True
    assert twice.replayed == 0
    reopened = _visible(tmp_path)
    assert len(json.loads(reopened["fact_graph"])["relationships"]) == 1
    assert len(json.loads(reopened["proof"])["entries"]) == 1
    assert json.loads(reopened["session"])["intake_history"][0]["effect_id"] == "effect-1"


@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_crash_boundary_reopens_to_committed_or_compensated(tmp_path: Path, boundary: str) -> None:
    root = tmp_path / boundary
    with pytest.raises(PrivateRevisionInterrupted) as caught:
        _commit(root, crash_injector=_crash(boundary), transaction=f"tx-{boundary}", effect=f"ef-{boundary}")
    assert caught.value.committed is False
    assert caught.value.boundary == boundary
    first = recover_private_revision(
        root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    second = recover_private_revision(
        root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    assert first.state in {"committed", "compensated"}
    assert second.replayed == 0
    assert second.rolled_back == 0
    opened = _visible(root)
    if boundary == "after_commit":
        assert first.committed is True
        assert opened is not None
        session = json.loads(opened["session"])
        assert session["intake_answers"]["harm"] == SENTINEL
        assert len(json.loads(opened["fact_graph"])["relationships"]) == 1
        assert len(json.loads(opened["proof"])["entries"]) == 1
    elif boundary in {"before_begin", "after_begin", "before_intent", "after_intent", "before_effect", "after_effect", "before_commit"}:
        assert first.committed is False
        assert first.state == "compensated"
        assert opened is None or SENTINEL.encode("utf-8") not in opened["session"]
    assert _scan(root) == []


def test_ack_lost_after_effect_does_not_duplicate_on_second_recovery(tmp_path: Path) -> None:
    root = tmp_path / "ack-lost"
    with pytest.raises(PrivateRevisionInterrupted):
        _commit(root, crash_injector=_crash("after_effect"), effect="effect-lost", transaction="tx-lost")
    first = recover_private_revision(
        root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    second = recover_private_revision(
        root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    assert first.state == "compensated"
    assert first.committed is False
    assert second.rolled_back == 0
    assert _visible(root) is None


def test_corrupt_journal_preserves_bytes(tmp_path: Path) -> None:
    root = tmp_path / "corrupt"
    _commit(root)
    decisions = root / "wal" / "transaction-decisions.jsonl"
    original = decisions.read_bytes()
    lines = original.splitlines(keepends=True)
    lines.insert(1, b"{this is not json\n")
    decisions.write_bytes(b"".join(lines))
    preserved = decisions.read_bytes()
    with pytest.raises(PrivateRevisionError) as caught:
        recover_private_revision(
            root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
        )
    assert caught.value.code == "journal_corrupt"
    assert caught.value.committed is False
    assert decisions.read_bytes() == preserved
    assert (root / "head.cgpe").exists()


def test_torn_tail_stays_recoverable(tmp_path: Path) -> None:
    root = tmp_path / "torn"
    _commit(root)
    decisions = root / "wal" / "transaction-decisions.jsonl"
    decisions.write_bytes(decisions.read_bytes() + b'{"kind":"commit"')
    recovered = recover_private_revision(
        root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    assert recovered.state == "committed"
    assert json.loads(_visible(root)["session"])["intake_answers"]["harm"] == SENTINEL


def test_stale_revision_and_wrong_key_and_case(tmp_path: Path) -> None:
    root = tmp_path / "cas"
    _commit(root)
    with pytest.raises(PrivateRevisionError) as stale:
        _commit(root, expected="0", transaction="tx-2", effect="effect-2", answer="other-answer")
    assert stale.value.code == "revision_conflict"
    assert json.loads(_visible(root)["session"])["intake_answers"]["harm"] == SENTINEL
    with pytest.raises(PrivateRevisionError) as wrong_key:
        read_private_revision(
            root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=OTHER_KEY, key_id=KEY_ID,
        )
    assert wrong_key.value.code == "authentication_failed"
    with pytest.raises(PrivateRevisionError) as wrong_case:
        read_private_revision(
            root, tenant_id=TENANT, case_id="case-b", principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
        )
    assert wrong_case.value.code == "authentication_failed"
    assert (root / "head.cgpe").read_bytes()


def test_fsync_failure_is_not_a_commit(tmp_path: Path) -> None:
    def fail(_fd: int) -> None:
        raise OSError("injected fsync failure")

    root = tmp_path / "fsync"
    with pytest.raises(PrivateRevisionError) as caught:
        _commit(root, fsync_file=fail)
    assert caught.value.committed is False
    assert caught.value.code == "file_fsync_failed"
    assert not (root / "head.cgpe").exists()

    parent = tmp_path / "parent-fsync"
    with pytest.raises(PrivateRevisionError) as parent_caught:
        _commit(parent, fsync_directory=fail)
    assert parent_caught.value.committed is False
    assert parent_caught.value.code == "directory_fsync_failed"
    assert not (parent / "head.cgpe").exists()


def test_closed_writer_and_backpressure(tmp_path: Path) -> None:
    writer = WALWriter(tmp_path / "closed-writer")
    writer.close()
    with pytest.raises(PrivateRevisionError) as closed:
        _commit(tmp_path / "closed-repo", writer=writer)
    assert closed.value.code == "wal_closed"
    assert closed.value.committed is False

    class Full:
        def append(self, *args, **kwargs):
            del args, kwargs
            raise WALQueueFullError("bounded")

        def close(self) -> None:
            return None

    with pytest.raises(PrivateRevisionError) as blocked:
        _commit(tmp_path / "full-repo", writer=Full())
    assert blocked.value.code == "wal_backpressure"
    assert not (tmp_path / "full-repo" / "head.cgpe").exists()


def test_concurrent_answers_do_not_share_a_temp_name(tmp_path: Path) -> None:
    root = tmp_path / "race"
    barrier = threading.Barrier(2)
    outcomes: list[object] = []
    lock = threading.Lock()

    def attempt(name: str, effect: str) -> None:
        barrier.wait()
        try:
            result = _commit(root, answer=name, effect=effect, transaction=effect, expected="0")
            with lock:
                outcomes.append(result)
        except PrivateRevisionError as exc:
            with lock:
                outcomes.append(exc)
        except Exception as exc:  # surface unexpected races in the assertion below
            with lock:
                outcomes.append(exc)

    threads = [
        threading.Thread(target=attempt, args=("answer-one", "effect-a")),
        threading.Thread(target=attempt, args=("answer-two", "effect-b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    committed = [item for item in outcomes if getattr(item, "committed", False)]
    conflicts = [item for item in outcomes if getattr(item, "code", "") == "revision_conflict"]
    detail = [f"{type(item).__name__}:{getattr(item, 'code', '')}:{getattr(item, 'committed', '')}:{item}" for item in outcomes]
    assert len(committed) == 1, detail
    assert len(conflicts) == 1, detail
    opened = _visible(root)
    body = opened["session"]
    assert (b"answer-one" in body) ^ (b"answer-two" in body)
    temps = [path.name for path in root.rglob("*.tmp")]
    assert len(temps) == len(set(temps))
    assert "session.tmp" not in temps


def test_workspace_join_uses_the_same_revision_identity(tmp_path: Path) -> None:
    service = ComplaintWorkspaceService(tmp_path / "ws")

    class Provider:
        def resolve(self, binding):
            del binding
            return (KEY_ID, KEY)

    service.private_key_provider = lambda: Provider()
    with workspace_access_scope(WorkspaceAccess.trusted_local()):
        receipt = service.commit_joined_intake_revision(
            "tenant-a",
            question_id="harm",
            answer=SENTINEL,
            transaction_id="tx-ws",
            effect_id="effect-ws",
            case_id="case-a",
            expected_revision="0",
        )
    assert receipt["committed"] is True
    assert receipt["network_pinned"] is False
    assert receipt["transaction_id"] == "tx-ws"
    assert receipt["effect_id"] == "effect-ws"
    opened = read_private_revision(
        service.joined_revision_repository("tenant-a", "case-a"),
        tenant_id="tenant-a",
        case_id="case-a",
        principal_id="tenant-a",
        key=KEY,
        key_id=KEY_ID,
    )
    session = json.loads(opened["session"])
    assert session["intake_answers"]["harm"] == SENTINEL
    assert session["annotation_knowledge_graph"]["relationships"][0]["id"] == "effect-ws"
    assert session["proof_history"][0]["effect_id"] == "effect-ws"
    assert _scan(service.joined_revision_repository("tenant-a", "case-a")) == []
    with workspace_access_scope(WorkspaceAccess.trusted_local()):
        first = service.recover_joined_intake_revision("tenant-a", case_id="case-a")
        second = service.recover_joined_intake_revision("tenant-a", case_id="case-a")
    assert first["committed"] is True
    assert second["replayed"] == 0


def test_upstream_wal_suites_are_a_separate_qualification() -> None:
    """Availability is distinct from the separately executed Kit compatibility run.

    The primary crash-recovery suite runs every first-party assertion itself.
    It does not recursively invoke optional repository suites or count their
    presence as evidence that they passed. Run the three suites separately and
    preserve their real per-suite collection, phases, JUnit and source report.
    """
    root = Path(__file__).resolve().parents[1] / "external" / "ipfs_kit_py"
    report = [
        {"suite": relative, "counts_as_passed": False,
         "status": "available_unexecuted" if (root / relative).is_file() else "missing"}
        for relative in UPSTREAM_WAL_SUITES
    ]
    assert [item["suite"] for item in report] == list(UPSTREAM_WAL_SUITES)
    assert len(report) == 3
    assert all(item["status"] in {"available_unexecuted", "missing"} for item in report)
    assert all(item["counts_as_passed"] is False for item in report)



def _revision_service(directory: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(directory)
    class Provider:
        def resolve(self, binding):
            return KEY_ID, KEY
    service.private_key_provider = lambda: Provider()
    return service


def test_workspace_second_revision_is_canonical_after_fresh_service(tmp_path):
    directory = tmp_path / "canonical"
    service = _revision_service(directory)
    with workspace_access_scope(WorkspaceAccess.trusted_local(TENANT, CASE)):
        first = service.commit_joined_intake_revision(TENANT, question_id="harm", answer=SENTINEL,
            transaction_id="tx-first", effect_id="ef-first", case_id=CASE, expected_revision="0")
        reopened = _revision_service(directory)
        current = reopened._load_state(TENANT)
        assert current["private_revision"] == "1"
        assert current["intake_answers"]["harm"] == SENTINEL
        second = reopened.commit_joined_intake_revision(TENANT, question_id="timeline", answer="Synthetic second answer",
            transaction_id="tx-second", effect_id="ef-second", case_id=CASE, expected_revision="1")
        final = _revision_service(directory)._load_state(TENANT)
    assert first["committed"] and second["committed"]
    assert final["private_revision"] == "2"
    assert final["intake_answers"]["harm"] == SENTINEL
    assert final["intake_answers"]["timeline"] == "Synthetic second answer"
    assert [row["id"] for row in final["annotation_knowledge_graph"]["relationships"]] == ["ef-first", "ef-second"]
    assert [row["effect_id"] for row in final["proof_history"]] == ["ef-first", "ef-second"]


@pytest.mark.parametrize("boundary", ("after_effect", "after_commit"))
@pytest.mark.parametrize("wrong", ("key", "case", "tenant", "principal"))
def test_recovery_authenticates_before_any_replay_or_compensation(tmp_path, monkeypatch, boundary, wrong):
    import integrations.private_storage as storage
    root = tmp_path / "owner-before-effects"
    with pytest.raises(PrivateRevisionInterrupted):
        _commit(root, crash_injector=_crash(boundary))
    preserved = storage._snapshot_bytes(root)
    effects = []
    original = storage._apply_intent
    def observe(*args, **kwargs):
        effects.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(storage, "_apply_intent", observe)
    options = dict(tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    options[{"key": "key", "case": "case_id", "tenant": "tenant_id", "principal": "principal_id"}[wrong]] = OTHER_KEY if wrong == "key" else "foreign-owner"
    with pytest.raises(PrivateRevisionError) as rejected:
        recover_private_revision(root, **options)
    assert rejected.value.code == "authentication_failed"
    assert effects == []
    assert storage._snapshot_bytes(root) == preserved
    first = recover_private_revision(root, tenant_id=TENANT, case_id=CASE,
        principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    second = recover_private_revision(root, tenant_id=TENANT, case_id=CASE,
        principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert first.state == ("committed" if boundary == "after_commit" else "compensated")
    assert second.replayed == second.rolled_back == 0


def test_head_publication_is_one_atomic_revision_record(tmp_path, monkeypatch):
    import integrations.private_storage as storage
    root = tmp_path / "single-head"
    replacements = []
    original = storage.os.replace
    def replace(source, destination, *args, **kwargs):
        original(source, destination, *args, **kwargs)
        if Path(destination).name == "head.cgpe":
            _, revision = storage._head_record(root)
            replacements.append(revision)
            # The atomic effect is complete, but its later WAL commit has not
            # happened yet. Public readers must not publish it as committed.
            with pytest.raises(PrivateRevisionError) as pending:
                _visible(root)
            assert pending.value.code == "recovery_required"
    monkeypatch.setattr(storage.os, "replace", replace)
    _commit(root)
    _commit(root, expected="1", transaction="tx-two", effect="effect-two")
    assert replacements == ["1", "2"]
    opened = _visible(root)
    assert opened["revision"] == "2"
    assert json.loads(opened["session"])["private_revision"] == "2"
    assert json.loads(opened["fact_graph"])["relationships"][0]["revision"] == "2"
    assert json.loads(opened["proof"])["entries"][0]["revision"] == "2"
    assert not (root / "head.rev").exists()
    assert (root / "head.cgpe").read_bytes().startswith(storage._HEAD_RECORD_MAGIC)


def test_identifying_operation_labels_never_enter_plaintext_WAL(tmp_path):
    root = tmp_path / "opaque-labels"
    transaction = "Sensitive synthetic claimant address and case narrative"
    effect = "Sensitive synthetic source span and rule evaluation"
    publication = _commit(root, transaction=transaction, effect=effect)
    assert publication.committed
    assert _visible(root)["manifest"]["transaction_id"] == transaction
    assert _visible(root)["manifest"]["effect_id"] == effect
    for path in (root / "wal").rglob("*"):
        if path.is_file():
            raw = path.read_bytes()
            assert transaction.encode() not in raw
            assert effect.encode() not in raw
            assert SENTINEL.encode() not in raw
            assert KEY not in raw


def test_real_shared_chat_commits_then_resumes_without_duplicate_effect(tmp_path, monkeypatch):
    import socket
    def blocked(*args, **kwargs):
        raise RuntimeError("external effect refused")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    directory = tmp_path / "real-chat"
    service = _revision_service(directory)
    message = "Synthetic supervisor fired me after I reported unsafe conditions."
    with workspace_access_scope(WorkspaceAccess.trusted_local(TENANT, CASE)):
        result = service.run_intake_chat_turn(TENANT, message=message, question_id="original_complaint")
        reopened = _revision_service(directory)
        state = reopened._load_state(TENANT)
        before = json.loads(json.dumps(state))
        again = reopened.run_intake_chat_turn(TENANT, message=message, question_id="original_complaint")
        after = _revision_service(directory)._load_state(TENANT)
    assert result["session"]["private_revision"] == "1"
    assert state["original_complaint"]["text"] == message
    assert state["shared_interview"].get("contract_version") == "interview-transition-v1" or state["shared_interview"].get("schema_version") == "shared-interview-session-v1"
    assert again["duplicate_answer_effect"] is True
    for field in ("private_revision", "intake_history", "annotation_knowledge_graph", "proof_history", "shared_interview"):
        assert after[field] == before[field]
    assert len(after["proof_history"]) == 1
    assert len([row for row in after["annotation_knowledge_graph"]["relationships"] if row.get("kind") == "intake-answer"]) == 1
    assert _scan(service.joined_revision_repository(TENANT, CASE)) == []



@pytest.mark.parametrize("boundary", ("after_effect", "before_commit"))
def test_uncommitted_visible_effect_is_explicitly_recovery_required(tmp_path, boundary):
    root = tmp_path / "pending-head"
    with pytest.raises(PrivateRevisionInterrupted):
        _commit(root, crash_injector=_crash(boundary))
    with pytest.raises(PrivateRevisionError) as pending:
        _visible(root)
    assert pending.value.code == "recovery_required"
    assert pending.value.committed is False
    recovered = recover_private_revision(root, tenant_id=TENANT, case_id=CASE,
        principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert recovered.state == "compensated"
    assert _visible(root) is None


def test_history_recovery_authenticates_superseded_revision_without_reinstall(tmp_path, monkeypatch):
    import integrations.private_storage as storage
    root = tmp_path / "history"
    _commit(root)
    _commit(root, expected="1", transaction="tx-second", effect="effect-second")
    preserved_head = (root / "head.cgpe").read_bytes()
    publications = []
    original = storage._publish_head
    def publish(*args, **kwargs):
        publications.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(storage, "_publish_head", publish)
    first = recover_private_revision(root, tenant_id=TENANT, case_id=CASE,
        principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    second = recover_private_revision(root, tenant_id=TENANT, case_id=CASE,
        principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert first.committed is True
    assert first.replayed == 2
    assert second.replayed == second.rolled_back == 0
    assert publications == []
    assert (root / "head.cgpe").read_bytes() == preserved_head
    opened = _visible(root)
    assert opened["revision"] == "2"
    assert json.loads(opened["session"])["intake_history"][0]["effect_id"] == "effect-second"
    assert len(json.loads(opened["fact_graph"])["relationships"]) == 1
    assert len(json.loads(opened["proof"])["entries"]) == 1


def test_authenticated_foreign_fork_does_not_authorize_history_rollback(tmp_path, monkeypatch):
    import integrations.private_storage as storage
    root = tmp_path / "original"
    other = tmp_path / "other-branch"
    for directory, prefix in ((root, "original"), (other, "other")):
        _commit(directory, transaction=prefix + "-one", effect=prefix + "-one")
        _commit(directory, expected="1", transaction=prefix + "-two", effect=prefix + "-two")
    # Even an authentic same-owner revision number cannot substitute for the
    # exact ciphertext ancestry retained by this repository's real WAL.
    (root / "head.cgpe").write_bytes((other / "head.cgpe").read_bytes())
    preserved_head = (root / "head.cgpe").read_bytes()
    publications = []
    monkeypatch.setattr(storage, "_publish_head", lambda *args, **kwargs: publications.append(True))
    with pytest.raises(PrivateRevisionError) as refused:
        recover_private_revision(root, tenant_id=TENANT, case_id=CASE,
            principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert refused.value.committed is False
    assert publications == []
    assert (root / "head.cgpe").read_bytes() == preserved_head



@pytest.mark.parametrize("boundary", (
    "before_begin", "after_begin", "before_intent", "after_intent",
    "before_effect", "after_effect", "before_commit",
))
def test_fresh_service_requires_recovery_for_initialized_first_revision(tmp_path, boundary):
    import integrations.private_storage as storage
    directory = tmp_path / "initial-crash"
    service = _revision_service(directory)
    with workspace_access_scope(WorkspaceAccess.trusted_local(TENANT, CASE)):
        prior = service._load_state(TENANT)
        service._save_state(prior)
        with pytest.raises(PrivateRevisionInterrupted):
            service.commit_joined_intake_revision(TENANT, question_id="harm", answer=SENTINEL,
                transaction_id="tx-initial", effect_id="ef-initial", case_id=CASE,
                expected_revision="0", crash_injector=_crash(boundary))
        repository = service.joined_revision_repository(TENANT, CASE)
        preserved = storage._snapshot_bytes(repository)
        with pytest.raises(PrivateRevisionError) as direct_read:
            read_private_revision(repository, tenant_id=TENANT, case_id=CASE,
                principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
        assert direct_read.value.code == "recovery_required"
        fresh = _revision_service(directory)
        with pytest.raises(WorkspacePersistenceError) as read:
            fresh._load_state(TENANT)
        assert read.value.code == "recovery_required"
        with pytest.raises(WorkspacePersistenceError) as write:
            fresh._save_state(prior)
        assert write.value.code == "recovery_required"
        assert storage._snapshot_bytes(repository) == preserved
        recovered = fresh.recover_joined_intake_revision(TENANT, case_id=CASE)
        again = fresh.recover_joined_intake_revision(TENANT, case_id=CASE)
        after = _revision_service(directory)._load_state(TENANT)
    assert recovered["state"] == "compensated"
    assert again["replayed"] == again["rolled_back"] == 0
    assert after["intake_answers"].get("harm") is None
    assert str(after.get("private_revision") or "0") == "0"
    assert _scan(repository) == []


def test_committed_head_disappearance_is_recovery_required(tmp_path, monkeypatch):
    import integrations.private_storage as storage
    root = tmp_path / "head-disappeared"
    _commit(root)
    original = storage._open_head
    calls = []
    def open_once(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs) if len(calls) == 1 else None
    monkeypatch.setattr(storage, "_open_head", open_once)
    with pytest.raises(PrivateRevisionError) as refused:
        read_private_revision(root, tenant_id=TENANT, case_id=CASE,
            principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID)
    assert refused.value.code == "recovery_required"
    assert refused.value.committed is False
    assert len(calls) == 2
    assert (root / "head.cgpe").is_file()
