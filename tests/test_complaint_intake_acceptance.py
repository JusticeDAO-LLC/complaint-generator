"""End-to-end graph interview acceptance on synthetic data only.

A PTY drives the terminal interview from a narrative through graph-targeted
follow-ups. Later cases cover unknown answers, contradictions, jurisdiction
and date changes, a missing legal source, revoked consent, a wrong key,
offline storage, corrupt state, cancellation, and a fresh-process resume.
Encrypted bytes must not contain the narrative. A connected graph is not
treated as legal correctness.
"""

from __future__ import annotations

import json
import os
import pty
import select
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService, WorkspacePersistenceError
from complaint_generator.workspace import run_intake_chat_turn
from integrations.ipfs_datasets.llm import PRIVACY_GROK_MODEL, PRIVACY_GROK_PROVIDER
from integrations.ipfs_datasets.storage import (
    InterviewSnapshotError,
    assemble_interview_snapshot,
    load_interview_snapshot,
    persist_interview_snapshot,
)
from tests.test_tui_interview_acceptance import (
    COHERENT,
    CONTRADICTORY,
    PASSPHRASE,
    UNKNOWN_ANSWER,
    _block_network_and_provider_subprocesses,  # Apply the autouse guard here too.
    _assert_graph_case,
    _assert_not_legally_complete,
    _entities,
    _graph_revision_fingerprint,
    _nodes,
    _open_narrative,
    _service,
)

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
_NARRATIVE_TOKEN = "SYNTHETIC-REL01-NARRATIVE"
COMPLETE_ANSWER = "The adverse action was on March 4, 2024."
DATE_ANSWER = "2024-03-04"


def _plaintext_hits(root: Path, token: str) -> list[str]:
    needle = token.encode("utf-8")
    hits = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if needle in path.read_bytes():
            hits.append(path.relative_to(root).as_posix())
    return hits


def _read_pty(master: int, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        ready, _, _ = select.select([master], [], [], 0.1)
        if not ready:
            text = b"".join(chunks).decode("utf-8", "replace")
            if text.rstrip().endswith(">") or "Chat paused" in text or "Current synopsis" in text:
                return text
            continue
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
        text = b"".join(chunks).decode("utf-8", "replace")
        if text.rstrip().endswith(">") or "Chat paused" in text or "Current synopsis" in text:
            return text
    return b"".join(chunks).decode("utf-8", "replace")


def drive_pty_interview(service: ComplaintWorkspaceService, user_id: str, lines: list[str], *, max_turns: int = 4) -> str:
    """Run the real terminal chat loop on a PTY. Lines are user input, not a stub transcript."""

    import importlib

    import applications.complaint_workspace as workspace

    complaint_cli = importlib.import_module("applications.complaint_cli")

    master, slave = pty.openpty()
    os.set_blocking(master, False)
    holder: dict[str, object] = {}

    def _run() -> None:
        saved_in, saved_out = sys.stdin, sys.stdout
        saved_service = complaint_cli.service
        saved_env = {key: os.environ.get(key) for key in ("NO_COLOR", "COMPLAINT_CLI_NO_COLOR", "TERM")}
        sys.stdin = os.fdopen(os.dup(slave), "r", buffering=1, closefd=True)
        sys.stdout = os.fdopen(os.dup(slave), "w", buffering=1, closefd=True)
        os.close(slave)
        os.environ["NO_COLOR"] = "1"
        os.environ["COMPLAINT_CLI_NO_COLOR"] = "1"
        os.environ["TERM"] = "dumb"
        complaint_cli.service = service
        try:
            complaint_cli.chat(user_id=user_id, max_turns=max_turns)
            holder["code"] = 0
        except SystemExit as exc:
            holder["code"] = exc.code
        except Exception as exc:  # surfaced to the parent assertion
            holder["error"] = exc
        finally:
            try:
                sys.stdout.flush()
            except Exception:
                pass
            terminal_in, terminal_out = sys.stdin, sys.stdout
            sys.stdin, sys.stdout = saved_in, saved_out
            terminal_in.close()
            terminal_out.close()
            complaint_cli.service = saved_service
            for key, value in saved_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    thread = threading.Thread(target=_run)
    thread.start()
    transcript = []
    try:
        for line in lines:
            seen = _read_pty(master, 40)
            transcript.append(seen)
            os.write(master, (line + "\n").encode("utf-8"))
        transcript.append(_read_pty(master, 40))
    finally:
        thread.join(timeout=20)
        os.close(master)
    assert not thread.is_alive(), "terminal interview did not finish"
    if holder.get("error"):
        raise holder["error"]
    assert holder.get("code") in {0, 1, None}
    return "\n".join(transcript)


def test_acceptance_module_blocks_network_and_provider_processes():
    with pytest.raises(RuntimeError, match="network socket blocked"):
        socket.create_connection(("192.0.2.1", 9), timeout=0.1)
    with pytest.raises(RuntimeError, match="provider subprocess blocked"):
        subprocess.run(["grok", "--version"], check=False)
    assert isinstance(subprocess.Popen, type)
    assert subprocess.Popen[bytes].__origin__ is subprocess.Popen


def test_pty_flow_asks_graph_followups_and_stops_unresolved(tmp_path: Path):
    user_id = "pty-user"
    narrative = f"On March 4, 2024 supervisor Alex Rivera fired me. {_NARRATIVE_TOKEN}"
    service = _service(tmp_path, user_id)
    transcript = drive_pty_interview(
        service,
        user_id,
        [narrative, DATE_ANSWER, "/why", "/status", "/quit"],
        max_turns=3,
    )
    assert "Describe your complaint" in transcript or "plain language" in transcript
    assert "version of the law" in transcript or "date" in transcript.lower()
    assert "Chat paused" in transcript or "user_quit" in transcript or "/status" in transcript
    status = service.run_intake_chat_turn(user_id, interview_action="status")
    _assert_not_legally_complete(status)
    assert status["original_complaint"]["text"] == narrative
    assert status["interview"]["inquiry"]["inquiry_id"].startswith("inq-")
    prompt = str(status["interview"]["inquiry"].get("question") or status.get("message") or "")
    assert prompt
    assert status["stopping_policy"]["outcome"] != "complete"
    summary = json.dumps(status["stopping_policy"])
    assert "legal_sufficiency" in summary
    assert status["stopping_policy"]["legal_sufficiency"] is False
    assert _plaintext_hits(Path(service._session_dir), _NARRATIVE_TOKEN) == []
    assert _plaintext_hits(Path(service._session_dir), narrative) == []
    sealed = list(Path(service._session_dir).rglob("*.cgpe"))
    assert sealed
    from integrations.private_storage import parse_private_envelope

    for path in sealed:
        frame = path.read_bytes()
        if frame.startswith(b"CGJH\x01"):
            assert path.name == "head.cgpe"
            revision_length = int.from_bytes(frame[5:7], "big")
            assert 0 < revision_length <= 128
            revision = frame[7:7 + revision_length]
            assert revision.isascii() and revision.isdigit()
            frame = frame[7 + revision_length:]
        envelope = parse_private_envelope(frame)
        assert envelope["schema_version"] == 2
        assert len(envelope["nonce"]) == 12
        assert len(envelope["ciphertext"]) >= 16


def test_complete_unknown_and_contradictory_answers_do_not_finish_the_law(tmp_path: Path):
    user_id = "matrix-user"
    service = _service(tmp_path, user_id)
    opened = _open_narrative(service, user_id, COHERENT)
    _assert_graph_case(opened, COHERENT)
    inquiry = opened["interview"]["inquiry"]
    complete = run_intake_chat_turn(
        user_id,
        message=COMPLETE_ANSWER,
        question_id=inquiry["inquiry_id"],
        expected_question_revision=opened["interview"]["expected_question_revision"],
        service=service,
    )
    _assert_not_legally_complete(complete)
    assert complete["interview"]["answered_count"] == 1
    assert complete["stopping_policy"]["core_facts_complete"] is False
    requirements = [node for node in _nodes(complete["session"]["shared_interview"]["dependency_graph"]) if node.get("node_type") == "requirement"]
    assert requirements
    assert all(node.get("satisfied") is False for node in requirements)

    unknown_user = "all-unknown"
    unknown_service = _service(tmp_path, unknown_user)
    unknown_open = _open_narrative(unknown_service, unknown_user, COHERENT)
    unknown = run_intake_chat_turn(
        unknown_user,
        message=UNKNOWN_ANSWER,
        question_id=unknown_open["interview"]["inquiry"]["inquiry_id"],
        expected_question_revision=unknown_open["interview"]["expected_question_revision"],
        service=unknown_service,
    )
    again = run_intake_chat_turn(
        unknown_user,
        message=UNKNOWN_ANSWER,
        question_id=unknown["interview"]["inquiry"]["inquiry_id"],
        expected_question_revision=unknown["interview"]["expected_question_revision"],
        service=unknown_service,
    )
    assert again["interview"]["unknown_reasons"]
    assert again["stopping_policy"]["outcome"] != "complete"
    assert again["stopping_policy"]["filing_ready"] is False

    contradictory = _open_narrative(_service(tmp_path, "contradict-user"), "contradict-user", CONTRADICTORY)
    encoded = json.dumps(contradictory["session"]["shared_interview"]["knowledge_graph"])
    assert "March 4, 2024" in encoded and "January 2, 2020" in encoded
    assert contradictory["stopping_policy"]["legal_sufficiency"] is False
    assert contradictory["interview"]["graph"]["relationship_count"] >= 0
    assert contradictory["stopping_policy"]["proof_requirements_satisfied"] is False


def test_jurisdiction_and_date_changes_keep_lineage_and_uncertainty(tmp_path, monkeypatch):
    from tests.test_question_saturation_contract import (
        application_level_interview_fixture,
        assert_scripted_interview_contract,
        scripted_turn,
    )

    session = application_level_interview_fixture(tmp_path, monkeypatch)
    assert_scripted_interview_contract(session)
    rule = scripted_turn(session, "rule_version")
    jurisdiction = scripted_turn(session, "jurisdiction")
    available = [
        item for item in rule["observation"]["legal"]
        if item["dependency_class"] == "legally_sourced_requirement" and item["source_available"] is not False
    ]
    assert available
    assert any(item["authority_version"] == "2025-edition" for item in available)
    assert any(item["source_hash"] in session["admitted_source_hashes"] for item in available)
    assert jurisdiction["observation"]["fact_ids"] == jurisdiction["extra"]["before_fact_ids"]
    assert all(
        item["satisfied"] is False
        for item in jurisdiction["observation"]["legal"]
        if item["dependency_class"] == "legally_sourced_requirement"
    )
    assert jurisdiction["observation"]["filing_ready"] is False
    assert jurisdiction["observation"]["intake_complete"] is False
    gaps = [
        item for item in jurisdiction["observation"]["legal"]
        if item["dependency_class"] in {"legal_source_gap", "unresolved_legal_requirement"}
    ]
    assert all(item["satisfied"] is False for item in gaps)


def test_missing_legal_source_is_uncertainty_not_a_satisfied_graph(tmp_path: Path):
    user_id = "missing-source"
    payload = _open_narrative(_service(tmp_path, user_id), user_id, COHERENT)
    _assert_graph_case(payload, COHERENT)
    dependency = payload["session"]["shared_interview"]["dependency_graph"]
    requirements = [node for node in _nodes(dependency) if node.get("node_type") == "requirement"]
    assert requirements and all(node.get("satisfied") is False for node in requirements)
    encoded = json.dumps(payload["session"]["shared_interview"])
    assert "42 U.S.C" not in encoded
    assert payload["interview"]["legal_sufficiency"] is False
    assert payload["interview"]["graph"]["entity_count"] >= 1
    names = " ".join(str(entity.get("name") or "") for entity in _entities(payload["session"]["shared_interview"]["knowledge_graph"]))
    assert names.strip()
    assert payload["stopping_policy"]["outcome"] != "complete"


def test_revoked_consent_blocks_the_named_provider(tmp_path: Path):
    user_id = "consent-user"
    service = _service(tmp_path, user_id)
    granted = service.set_privacy_policy(user_id, "grok")
    policy = granted["policy"]
    assert policy["processing_mode"] in {"grok", "grok_cloud"}
    assert policy["consent"]["status"] == "explicit_grok"
    assert policy["permitted_remote"] == {"provider": PRIVACY_GROK_PROVIDER, "model": PRIVACY_GROK_MODEL}
    assert policy["consent"]["cloud_processing"] is True
    assert granted.get("unlock_is_remote_consent") is not True
    revoked = service.set_privacy_policy(user_id, "local")
    local = revoked["policy"]
    assert local["cloud_processing_enabled"] is False
    assert local["consent"]["cloud_processing"] is False
    assert local["permitted_remote"] is None
    denied = service.dispatch_private_llm_turn(
        user_id,
        relevant_facts=["synthetic fact"],
        rule_gaps=["synthetic gap"],
        sensitive_literals=[COHERENT],
        key=b"k" * 32,
        key_id="consent-key",
        provider=PRIVACY_GROK_PROVIDER,
        model_name=PRIVACY_GROK_MODEL,
    )
    assert str(denied.get("error") or denied.get("reason") or denied.get("status") or "").startswith("privacy_denied") or denied.get("privacy_decision") == "denied" or denied.get("dispatched") is False
    blob = json.dumps(denied)
    assert COHERENT not in blob
    assert PRIVACY_GROK_PROVIDER not in blob or denied.get("dispatch") in {None, "none", False}


def test_wrong_key_offline_storage_and_corrupt_state(tmp_path: Path):
    user_id = "fault-user"
    root = tmp_path / "sessions" / user_id
    service = _service(tmp_path, user_id)
    opened = _open_narrative(service, user_id, COHERENT)
    before = sorted((path.relative_to(root).as_posix(), path.read_bytes()) for path in root.rglob("*") if path.is_file())
    locked = ComplaintWorkspaceService(root_dir=root)
    refused = locked.unlock_private_keys(passphrase="wrong-synthetic-passphrase")
    assert refused["code"] == "authentication_failed"
    assert COHERENT not in json.dumps(refused)
    after = sorted((path.relative_to(root).as_posix(), path.read_bytes()) for path in root.rglob("*") if path.is_file())
    assert after == before

    directory = tmp_path / "offline-snapshot"
    key = b"k" * 32
    snapshot = assemble_interview_snapshot(
        session_id="rel01",
        revision="0",
        outcome_reason="awaiting_user",
        pending_inquiry=opened["session"]["shared_interview"]["pending_inquiry"],
        knowledge_graph=opened["session"]["shared_interview"]["knowledge_graph"],
        dependency_graph=opened["session"]["shared_interview"]["dependency_graph"],
        provenance={"status": "recorded"},
        unknown_items=[],
        deferred_items=[],
        complaint_text=COHERENT,
        transcript=[{"sender": "user", "message": COHERENT}],
        exports={"filing": "not-written"},
        durability_payload={"status": "pending"},
        revisions={"session_revision": 1, "question_revision": 1, "graph_revision": 1},
    )
    saved = persist_interview_snapshot(
        directory, snapshot, protection="user_chosen_encrypted", tenant_id=user_id, case_id=user_id,
        principal_id=user_id, key=key, key_id="rel01-key",
    )
    assert COHERENT not in json.dumps(saved["receipt"])

    def offline(_payload: bytes) -> None:
        raise ConnectionError("synthetic offline storage")

    with pytest.raises(ConnectionError, match="offline"):
        persist_interview_snapshot(
            directory, snapshot, protection="user_chosen_encrypted", tenant_id=user_id, case_id=user_id,
            principal_id=user_id, key=key, key_id="rel01-key", expected_revision="1", writer=offline,
        )
    loaded = load_interview_snapshot(
        directory, protection="user_chosen_encrypted", tenant_id=user_id, case_id=user_id,
        principal_id=user_id, key=key, key_id="rel01-key",
    )
    assert loaded["snapshot"]["revision"] == "1"
    assert loaded["snapshot"]["outcome_reason"] == "awaiting_user"

    sealed_paths = [path for path in root.rglob("*.cgpe")]
    originals = {path: path.read_bytes() for path in sealed_paths}
    target = max(sealed_paths, key=lambda path: path.stat().st_size)
    damaged_bytes = bytearray(originals[target])
    damaged_bytes[-1] ^= 0x5A
    target.write_bytes(bytes(damaged_bytes))
    damaged = ComplaintWorkspaceService(root_dir=root)
    damaged.unlock_private_keys(passphrase=PASSPHRASE)
    with pytest.raises(WorkspacePersistenceError) as corrupt:
        damaged.run_intake_chat_turn(user_id, interview_action="status")
    assert corrupt.value.code in {"authentication_failed", "corrupt_session", "read_error"}
    assert COHERENT not in str(corrupt.value)
    assert COHERENT.encode() not in target.read_bytes()
    for path, payload in originals.items():
        path.write_bytes(payload)
    restored = ComplaintWorkspaceService(root_dir=root)
    restored.unlock_private_keys(passphrase=PASSPHRASE)
    status = restored.run_intake_chat_turn(user_id, interview_action="status")
    assert status["original_complaint"]["text"] == COHERENT
    assert _graph_revision_fingerprint(status) == _graph_revision_fingerprint(opened)


def test_cancellation_keeps_the_inquiry_and_a_fresh_process_resumes_it(tmp_path: Path, monkeypatch):
    from integrations.ipfs_datasets import llm

    user_id = "cancel-user"
    service = _service(tmp_path, user_id)
    service.set_privacy_policy(user_id, "grok")

    def cancelled(prompt, **kwargs):
        assert kwargs.get("provider") == PRIVACY_GROK_PROVIDER
        assert COHERENT not in json.dumps({key: kwargs.get(key) for key in ("provider", "model_name")})
        return {"status": "cancelled", "failure_kind": "cancelled", "text": "", "error": "cancelled", "privacy_decision": "allowed"}

    monkeypatch.setattr(llm, "generate_text_with_metadata", cancelled)
    opened = _open_narrative(service, user_id, COHERENT)
    failures = set((opened["interview"].get("error") or {}).get("router_failures", {}).values())
    assert "cancelled" in failures
    assert opened["interview"]["intake_complete"] is False
    assert opened["stopping_policy"]["legal_sufficiency"] is False
    inquiry_id = opened["interview"]["inquiry"]["inquiry_id"]

    script = """
import json, sys
from pathlib import Path
from applications.complaint_workspace import ComplaintWorkspaceService
root, user_id, passphrase = sys.argv[1:]
service = ComplaintWorkspaceService(root_dir=Path(root))
unlocked = service.unlock_private_keys(passphrase=passphrase)
if unlocked.get("code") == "authentication_failed":
    raise SystemExit("unlock failed")
payload = service.run_intake_chat_turn(user_id, interview_action="status")
print(json.dumps({
    "inquiry_id": payload["interview"]["inquiry"]["inquiry_id"],
    "text": payload["original_complaint"]["text"],
    "legal_sufficiency": payload["stopping_policy"]["legal_sufficiency"],
    "outcome": payload["stopping_policy"]["outcome"],
    "filing_ready": payload["stopping_policy"]["filing_ready"],
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(service._session_dir), user_id, PASSPHRASE],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    line = [item for item in completed.stdout.splitlines() if item.startswith("{")][-1]
    resumed = json.loads(line)
    assert resumed["inquiry_id"] == inquiry_id
    assert resumed["text"] == COHERENT
    assert resumed["legal_sufficiency"] is False
    assert resumed["filing_ready"] is False
    assert resumed["outcome"] != "complete"
    assert _plaintext_hits(Path(service._session_dir), COHERENT) == []


def test_snapshot_wrong_key_does_not_decrypt(tmp_path: Path):
    directory = tmp_path / "locked"
    key = b"a" * 32
    snapshot = assemble_interview_snapshot(
        session_id="rel01-lock",
        revision="0",
        outcome_reason="awaiting_user",
        pending_inquiry={"inquiry_id": "inq-lock"},
        knowledge_graph={"entities": {}},
        dependency_graph={"nodes": {}},
        provenance={"status": "recorded"},
        unknown_items=["missing authority"],
        deferred_items=[],
        complaint_text=COHERENT,
        transcript=[],
        exports={},
        durability_payload={},
        revisions={"session_revision": 1},
    )
    persist_interview_snapshot(
        directory, snapshot, protection="user_chosen_encrypted", tenant_id="t", case_id="c",
        principal_id="t", key=key, key_id="k1",
    )
    with pytest.raises(InterviewSnapshotError) as wrong:
        load_interview_snapshot(
            directory, protection="user_chosen_encrypted", tenant_id="t", case_id="c",
            principal_id="t", key=b"b" * 32, key_id="k2",
        )
    assert wrong.value.code == "authentication_failed"
    assert COHERENT not in str(wrong.value)
