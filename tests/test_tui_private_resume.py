"""Private durable interview snapshots for terminal resume.

Snapshots keep both graphs, provenance, the pending inquiry, revisions, the
schema version, the outcome reason, and explicit unknown or deferred items.
Encrypted sessions never fall back to plaintext.
"""

from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

import pytest

from applications.cli import CLI
from applications.complaint_workspace import ComplaintWorkspaceService, WorkspacePersistenceError
from integrations.ipfs_datasets.storage import (
    UNENCRYPTED_INTERVIEW_NAME,
    InterviewSnapshotError,
    assemble_interview_snapshot,
    load_interview_snapshot,
    migrate_unencrypted_interview_snapshot,
    persist_interview_snapshot,
)

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

COMPLAINT = "SYNTHETIC-COMPLAINT-TEXT-ALPHA supervisor fired the worker."
DURABILITY_TOKEN = "DURABILITY-PAYLOAD-TOKEN-BETA"
KEY = b"k" * 32
KEY_ID = "interview-key-1"
OTHER_KEY = b"m" * 32


def _snapshot(revision: str = "0") -> dict:
    return assemble_interview_snapshot(
        session_id="sess-synthetic-1",
        revision=revision,
        outcome_reason="user_pause",
        pending_inquiry={"inquiry_id": "inq-1", "objective_id": "dates", "question": "When did it happen?"},
        knowledge_graph={"entities": {"person-1": {"name": "Alex"}}, "provenance": {"extractor": "synthetic"}},
        dependency_graph={"nodes": {"req-1": {"status": "open"}}},
        provenance={"extractor": "synthetic", "status": "recorded"},
        unknown_items=[{"field": "date", "disposition": "unknown"}],
        deferred_items=[{"field": "damages", "disposition": "deferred"}],
        complaint_text=COMPLAINT,
        transcript=[{"sender": "user", "message": COMPLAINT}],
        exports={"filing": "not-written", "body": COMPLAINT},
        durability_payload={"token": DURABILITY_TOKEN, "status": "pending"},
        revisions={"session_revision": 2, "question_revision": 4, "graph_revision": 4},
    )


def _persist(directory: Path, snapshot: dict | None = None, **kwargs):
    params = dict(
        protection="user_chosen_encrypted",
        tenant_id="tenant-a",
        case_id="case-a",
        principal_id="tenant-a",
        key=KEY,
        key_id=KEY_ID,
        expected_revision=kwargs.pop("expected_revision", None),
    )
    params.update(kwargs)
    return persist_interview_snapshot(directory, snapshot or _snapshot(), **params)


def _load(directory: Path, **kwargs):
    params = dict(
        protection="user_chosen_encrypted",
        tenant_id="tenant-a",
        case_id="case-a",
        principal_id="tenant-a",
        key=KEY,
        key_id=KEY_ID,
    )
    params.update(kwargs)
    return load_interview_snapshot(directory, **params)


def _assert_private(directory: Path) -> None:
    mode = directory.stat().st_mode
    assert stat.S_ISDIR(mode)
    assert mode & 0o077 == 0
    for path in directory.rglob("*"):
        assert path.stat().st_mode & 0o077 == 0
        if path.is_file():
            blob = path.read_bytes()
            assert COMPLAINT.encode() not in blob
            assert DURABILITY_TOKEN.encode() not in blob
            assert KEY not in blob
            assert OTHER_KEY not in blob


def test_encrypted_snapshot_round_trip_keeps_graphs_and_dispositions(tmp_path: Path) -> None:
    saved = _persist(tmp_path / "snap")
    snapshot = saved["snapshot"]
    assert snapshot["schema_version"] == "interview-snapshot-v1"
    assert snapshot["outcome_reason"] == "user_pause"
    assert snapshot["graphs"]["knowledge_graph"]["entities"]["person-1"]["name"] == "Alex"
    assert snapshot["graphs"]["dependency_graph"]["nodes"]["req-1"]["status"] == "open"
    assert snapshot["provenance"]["extractor"] == "synthetic"
    assert snapshot["pending_inquiry"]["inquiry_id"] == "inq-1"
    assert snapshot["unknown_items"][0]["disposition"] == "unknown"
    assert snapshot["deferred_items"][0]["disposition"] == "deferred"
    assert snapshot["revisions"]["question_revision"] == 4
    assert saved["receipt"]["revision"] == "1"
    assert COMPLAINT not in json.dumps(saved["receipt"])
    assert KEY.hex() not in json.dumps(saved["receipt"])
    loaded = _load(tmp_path / "snap")
    assert loaded["snapshot"]["complaint_text"] == COMPLAINT
    assert loaded["snapshot"]["transcript"][0]["message"] == COMPLAINT
    assert loaded["snapshot"]["durability_payload"]["token"] == DURABILITY_TOKEN
    assert loaded["recovered"] is False
    _assert_private(tmp_path / "snap")


def test_wrong_key_and_locked_session_do_not_fall_back(tmp_path: Path) -> None:
    directory = tmp_path / "locked"
    _persist(directory)
    with pytest.raises(InterviewSnapshotError) as wrong:
        _load(directory, key=OTHER_KEY, key_id="interview-key-2")
    assert wrong.value.code == "authentication_failed"
    with pytest.raises(InterviewSnapshotError) as locked:
        _load(directory, key=None, key_id=None)
    assert locked.value.code == "unlock_needed"
    with pytest.raises(InterviewSnapshotError) as refused:
        _load(directory, protection="user_chosen_plaintext", key=None, key_id=None)
    assert refused.value.code == "plaintext_fallback_refused"
    empty = tmp_path / "missing-key"
    with pytest.raises(InterviewSnapshotError) as unsaved:
        persist_interview_snapshot(
            empty, _snapshot(), protection="user_chosen_encrypted",
            tenant_id="tenant-a", case_id="case-a", principal_id="tenant-a",
            key=None, key_id=None,
        )
    assert unsaved.value.code == "unlock_needed"
    assert not empty.exists()


def test_plaintext_snapshot_is_preserved_until_explicit_migration(tmp_path: Path) -> None:
    directory = tmp_path / "legacy"
    directory.mkdir()
    document = _snapshot("0")
    raw = json.dumps(document, sort_keys=True).encode("utf-8")
    legacy = directory / UNENCRYPTED_INTERVIEW_NAME
    legacy.write_bytes(raw)
    with pytest.raises(InterviewSnapshotError) as required:
        _persist(directory, document)
    assert required.value.code == "migration_required"
    assert legacy.read_bytes() == raw
    migrated = migrate_unencrypted_interview_snapshot(
        directory, tenant_id="tenant-a", case_id="case-a", principal_id="tenant-a", key=KEY, key_id=KEY_ID,
    )
    assert legacy.read_bytes() == raw
    assert migrated["snapshot"]["complaint_text"] == COMPLAINT
    again = migrate_unencrypted_interview_snapshot(
        directory, tenant_id="tenant-a", case_id="case-a", principal_id="tenant-a", key=KEY, key_id=KEY_ID,
    )
    assert again["existing_private_preserved"] is True
    assert legacy.read_bytes() == raw
    loaded = _load(directory)
    assert loaded["snapshot"]["graphs"]["dependency_graph"]["nodes"]["req-1"]["status"] == "open"
    with pytest.raises(InterviewSnapshotError) as wrong:
        _load(directory, key=OTHER_KEY, key_id="interview-key-2")
    assert wrong.value.code == "authentication_failed"


def test_failed_write_and_corruption_keep_the_last_valid_revision(tmp_path: Path) -> None:
    directory = tmp_path / "revisions"
    first = _persist(directory)
    assert first["snapshot"]["revision"] == "1"

    def fail_writer(_payload: bytes) -> None:
        raise OSError("synthetic durability write failure")

    with pytest.raises(OSError):
        _persist(directory, expected_revision="1", writer=fail_writer)
    assert _load(directory)["snapshot"]["revision"] == "1"
    with pytest.raises(InterviewSnapshotError) as unproven:
        _persist(directory, expected_revision="1", fail_before_head=True)
    assert unproven.value.code == "durability_unproven"
    assert _load(directory)["snapshot"]["revision"] == "1"
    second = _persist(directory, expected_revision="1")
    assert second["snapshot"]["revision"] == "2"
    head_path = directory / "head.json"
    head = json.loads(head_path.read_text())
    blob = directory / head["blob"]
    blob.write_bytes(b"corrupt-ciphertext")
    recovered = _load(directory)
    assert recovered["recovered"] is True
    assert recovered["snapshot"]["revision"] == "1"
    assert recovered["snapshot"]["complaint_text"] == COMPLAINT
    restarted = _load(directory)
    assert restarted["snapshot"]["revision"] == "1"


def test_concurrent_writers_do_not_lose_the_committed_revision(tmp_path: Path) -> None:
    directory = tmp_path / "concurrent"
    _persist(directory)
    codes: list[str] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        barrier.wait()
        try:
            _persist(directory, expected_revision="1")
            codes.append("committed")
        except InterviewSnapshotError as exc:
            codes.append(exc.code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(codes) == ["committed", "revision_conflict"]
    assert _load(directory)["snapshot"]["revision"] == "2"


def test_workspace_encrypted_resume_and_locked_refusal(tmp_path: Path) -> None:
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase="synthetic-interview-passphrase")
    service.ensure_private_case_key("tenant-a", "tenant-a")
    saved = service.persist_complete_interview_snapshot("tenant-a", _snapshot(), case_id="tenant-a")
    assert saved["receipt"]["status"] == "available"
    assert COMPLAINT not in json.dumps(saved["receipt"])
    loaded = service.load_complete_interview_snapshot("tenant-a", case_id="tenant-a")
    assert loaded["snapshot"]["outcome_reason"] == "user_pause"
    assert loaded["snapshot"]["graphs"]["knowledge_graph"]["entities"]["person-1"]["name"] == "Alex"
    service.lock_private_keys()
    with pytest.raises(WorkspacePersistenceError) as locked:
        service.load_complete_interview_snapshot("tenant-a", case_id="tenant-a")
    assert locked.value.code == "unlock_needed"
    directory = service.interview_snapshot_directory("tenant-a")
    assert COMPLAINT.encode() not in (directory / "head.json").read_bytes()


def test_cli_encrypted_save_and_resume_skip_plaintext(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    class _State:
        pass

    state = _State()
    state.answered_questions = {"date": "unknown", "damages": "skipped"}
    state.chat_history = {"1": {"sender": "user", "message": COMPLAINT}}
    state.original_complaint = COMPLAINT
    state.complaint_summary = None
    state.complaint = None
    state.current_inquiry = {"objective_id": "dates", "revision": 3, "inquiry_id": "inq-9"}
    state.username = "synthetic-user"

    class _Mediator:
        pass

    mediator = _Mediator()
    mediator.state = state
    mediator.workflow_actions = None
    cli = object.__new__(CLI)
    cli.mediator = mediator
    cli._terminal_stop_reason = "eof"
    cli._interview_protection = "user_chosen_encrypted"
    cli._interview_snapshot_dir = str(tmp_path / "cli-snap")
    cli._interview_key = KEY
    cli._interview_key_id = KEY_ID
    cli._interview_tenant_id = "tenant-a"
    cli._interview_case_id = "case-a"
    with caplog.at_level("INFO"):
        saved = cli.save()
    assert saved["receipt"]["outcome_reason"] == "eof"
    assert saved["snapshot"]["unknown_items"][0]["field"] == "date"
    assert saved["snapshot"]["deferred_items"][0]["field"] == "damages"
    assert saved["snapshot"]["graphs"]["knowledge_graph"]["status"] == "unknown"
    assert saved["snapshot"]["graphs"]["dependency_graph"]["status"] == "unknown"
    assert COMPLAINT not in json.dumps(saved["receipt"])
    assert COMPLAINT not in caplog.text
    assert KEY.hex() not in caplog.text
    assert not list((tmp_path / "cli-snap").rglob("*.json")) or (tmp_path / "cli-snap" / "head.json").is_file()
    for path in (tmp_path / "cli-snap").rglob("*"):
        if path.is_file() and path.name != "head.json":
            assert COMPLAINT.encode() not in path.read_bytes()
    fresh = object.__new__(CLI)
    fresh_state = _State()
    fresh_state.answered_questions = {}
    fresh_state.chat_history = {}
    fresh_state.original_complaint = None
    fresh.mediator = _Mediator()
    fresh.mediator.state = fresh_state
    fresh.mediator.workflow_actions = None
    fresh._interview_protection = "user_chosen_encrypted"
    fresh._interview_snapshot_dir = cli._interview_snapshot_dir
    fresh._interview_key = OTHER_KEY
    fresh._interview_key_id = "interview-key-2"
    fresh._interview_tenant_id = "tenant-a"
    fresh._interview_case_id = "case-a"
    with pytest.raises(InterviewSnapshotError) as wrong:
        fresh.resume()
    assert wrong.value.code == "authentication_failed"
    assert fresh_state.original_complaint is None
    fresh._interview_key = KEY
    fresh._interview_key_id = KEY_ID
    loaded = fresh.resume()
    assert loaded["snapshot"]["complaint_text"] == COMPLAINT
    assert fresh_state.original_complaint == COMPLAINT
    assert fresh._terminal_stop_reason == "eof"


def _configured_snapshot_cli(directory):
    from types import SimpleNamespace
    state = SimpleNamespace(username="tenant-a", original_complaint=COMPLAINT,
        complaint_summary=None, complaint=None, current_inquiry={"inquiry_id": "inq-1"},
        answered_questions={}, chat_history={})
    cli = object.__new__(CLI)
    cli.mediator = SimpleNamespace(state=state, workflow_actions=None)
    cli._interview_protection = "user_chosen_encrypted"
    cli._interview_snapshot_dir = str(directory)
    cli._interview_key = KEY
    cli._interview_key_id = KEY_ID
    cli._interview_tenant_id = "tenant-a"
    cli._interview_case_id = "case-a"
    return cli


def test_snapshot_cli_does_not_accept_raw_key_material_from_environment(monkeypatch):
    monkeypatch.setenv("COMPLAINT_INTERVIEW_KEY_HEX", KEY.hex())
    cli = object.__new__(CLI)
    assert cli._interview_protection_settings()["key"] is None


def test_encrypted_cli_save_advances_its_current_revision(tmp_path):
    cli = _configured_snapshot_cli(tmp_path / "case")
    first = cli.save()
    second = cli.save()
    assert first["receipt"]["revision"] == "1"
    assert second["receipt"]["revision"] == "2"
    assert _load(tmp_path / "case")["snapshot"]["revision"] == "2"


def test_snapshot_alias_refusal_does_not_chmod_the_target(tmp_path):
    target = tmp_path / "outside"
    target.mkdir(mode=0o755)
    target.chmod(0o755)
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    before = target.stat().st_mode
    with pytest.raises((InterviewSnapshotError, OSError)):
        _persist(alias)
    assert target.stat().st_mode == before
    assert list(target.iterdir()) == []


def test_snapshot_head_cannot_read_a_frame_outside_its_directory(tmp_path):
    directory = tmp_path / "case"
    result = _persist(directory)
    head_path = directory / "head.json"
    head = json.loads(head_path.read_text())
    original = directory / head["blob"]
    outside = tmp_path / "outside-frame.bin"
    outside.write_bytes(original.read_bytes())
    outside.chmod(0o600)
    original.unlink()
    head["history"][-1]["blob"] = "../outside-frame.bin"
    head["blob"] = "../outside-frame.bin"
    head_path.write_text(json.dumps(head))
    with pytest.raises(InterviewSnapshotError):
        _load(directory)
    assert outside.read_bytes()


def test_snapshot_wrong_owner_cannot_replace_a_committed_head(tmp_path):
    directory = tmp_path / "case"
    _persist(directory)
    before = {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    with pytest.raises(InterviewSnapshotError):
        _persist(directory, tenant_id="tenant-b", case_id="case-b", principal_id="tenant-b",
                 key=OTHER_KEY, key_id="other-key", expected_revision="1")
    assert {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()} == before
    assert _load(directory)["snapshot"]["revision"] == "1"


def test_distinct_cases_have_independent_snapshot_heads(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "service")
    service.initialize_private_keys(protection="passphrase", passphrase="synthetic-case-snapshot-passphrase")
    service.ensure_private_case_key("tenant-a", "case-a")
    service.ensure_private_case_key("tenant-a", "case-b")
    first = _snapshot()
    second = _snapshot()
    second["complaint_text"] = "SYNTHETIC independent second case"
    service.persist_complete_interview_snapshot("tenant-a", first, case_id="case-a")
    service.persist_complete_interview_snapshot("tenant-a", second, case_id="case-b")
    assert service.load_complete_interview_snapshot("tenant-a", case_id="case-a")["snapshot"]["complaint_text"] == COMPLAINT
    assert service.load_complete_interview_snapshot("tenant-a", case_id="case-b")["snapshot"]["complaint_text"] == second["complaint_text"]


def test_snapshot_public_metadata_does_not_expose_private_identifiers(tmp_path):
    document = _snapshot()
    secrets = ("PRIVATE-SESSION-NAME-SENTINEL", "PRIVATE-SNAPSHOT-NAME-SENTINEL", "PRIVATE-OUTCOME-SENTINEL")
    document.update(session_id=secrets[0], snapshot_id=secrets[1], outcome_reason=secrets[2])
    result = _persist(tmp_path / "case", document)
    public = json.dumps(result["receipt"]) + json.dumps(result["head"])
    assert all(secret not in public for secret in secrets)
    assert result["snapshot"]["session_id"] == secrets[0]


def test_snapshot_part_entries_are_fsynced_before_publishing_head(tmp_path, monkeypatch):
    import os
    synced = set()
    original = os.fsync
    def record(fd):
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode):
            synced.add((info.st_dev, info.st_ino))
        return original(fd)
    monkeypatch.setattr(os, "fsync", record)
    directory = tmp_path / "case"
    _persist(directory)
    parts = (directory / "parts").stat()
    assert (parts.st_dev, parts.st_ino) in synced
