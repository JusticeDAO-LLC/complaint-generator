"""Adverse interview acceptance across package, API, MCP, and terminal surfaces.

The same synthetic sequence must yield the same inquiry id and graph revision.
Assertions read graph provenance, support links, and the stopping policy.
Network sockets and provider subprocesses stay blocked unless the live
synthetic canary is explicitly selected. Sessions live only under tmp paths.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import subprocess
import threading
from pathlib import Path

import pytest
from typer.testing import CliRunner

from applications.complaint_mcp_protocol import handle_jsonrpc_message
from applications.complaint_workspace import (
    ComplaintWorkspaceService,
    WorkspaceAccess,
    WorkspacePersistenceError,
    workspace_access_scope,
)
from applications.complaint_workspace_api import IntakeChatTurnRequest, create_complaint_workspace_router
from complaint_generator.workspace import run_intake_chat_turn
from integrations.ipfs_datasets.storage import (
    InterviewSnapshotError,
    assemble_interview_snapshot,
    load_interview_snapshot,
    persist_interview_snapshot,
)

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

PASSPHRASE = "synthetic-interview-acceptance-passphrase"
COHERENT = "On March 4, 2024 supervisor Alex Rivera fired me after I reported safety concerns."
CONTRADICTORY = "I was fired on March 4, 2024. I was also fired on January 2, 2020."
UNIDENTIFIED = "I was fired on March 4, 2024 after I reported a safety concern to management."
UNKNOWN_ANSWER = "I don't know"
_PROVIDER_BASENAMES = {
    "grok",
    "grok-cli",
    "codex",
    "claude",
    "openai",
    "curl",
    "wget",
    "ssh",
    "nc",
    "ncat",
    "socat",
}
_CANARY_ENV = "COMPLAINT_TUI_LIVE_SYNTHETIC_CANARY"


def _canary_selected() -> bool:
    return os.environ.get(_CANARY_ENV) == "1"


def _command_basename(args, kwargs) -> str:
    command = args[0] if args else kwargs.get("args")
    if command is None:
        return ""
    if isinstance(command, (str, bytes)):
        text = os.fsdecode(command)
        parts = text.split()
        token = parts[0] if parts else ""
    else:
        token = os.fsdecode(command[0]) if command else ""
    return Path(token).name.lower()


@pytest.fixture(autouse=True)
def _block_network_and_provider_subprocesses(monkeypatch):
    """Block remote sockets and provider CLIs. Local interpreter helpers still run."""

    def blocked_socket(*_args, **_kwargs):
        if _canary_selected():
            raise RuntimeError("live canary must not open a socket from this fixture")
        raise RuntimeError("network socket blocked")

    monkeypatch.setattr(socket.socket, "connect", blocked_socket)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked_socket)
    monkeypatch.setattr(socket, "create_connection", blocked_socket)

    def guarded(real):
        def wrapped(*args, **kwargs):
            name = _command_basename(args, kwargs)
            if name in _PROVIDER_BASENAMES and not _canary_selected():
                raise RuntimeError("provider subprocess blocked")
            return real(*args, **kwargs)

        return wrapped

    # Popen is also a generic class in dependency annotations. Keep that
    # interface while refusing provider executables before process creation.
    original_popen = subprocess.Popen

    class GuardedPopen(original_popen):
        def __init__(self, *args, **kwargs):
            if _command_basename(args, kwargs) in _PROVIDER_BASENAMES and not _canary_selected():
                raise RuntimeError("provider subprocess blocked")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", GuardedPopen)
    monkeypatch.setattr(subprocess, "run", guarded(subprocess.run))
    monkeypatch.setattr(subprocess, "call", guarded(subprocess.call))
    monkeypatch.setattr(subprocess, "check_call", guarded(subprocess.check_call))
    monkeypatch.setattr(subprocess, "check_output", guarded(subprocess.check_output))


def _service(tmp_path: Path, user_id: str) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions" / user_id)
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(user_id, user_id)
    assert Path(service._session_dir).is_relative_to(tmp_path)
    return service


def _entities(graph: dict) -> list[dict]:
    raw = graph.get("entities") or {}
    if isinstance(raw, dict):
        return list(raw.values())
    return list(raw)


def _relationships(graph: dict) -> list[dict]:
    raw = graph.get("relationships") or {}
    if isinstance(raw, dict):
        return list(raw.values())
    return list(raw)


def _nodes(graph: dict) -> list[dict]:
    raw = graph.get("nodes") or {}
    if isinstance(raw, dict):
        return list(raw.values())
    return list(raw)


def _dependencies(graph: dict) -> list[dict]:
    raw = graph.get("dependencies") or {}
    if isinstance(raw, dict):
        return list(raw.values())
    return list(raw)


def _assertion(record: dict) -> dict:
    provenance = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
    assertion = provenance.get("user_assertion")
    return assertion if isinstance(assertion, dict) else {}


def _support_endpoints_resolve(knowledge: dict) -> None:
    identities = {str(entity.get("id")) for entity in _entities(knowledge)}
    relationships = _relationships(knowledge)
    assert relationships, "knowledge graph has no support relationships"
    for relationship in relationships:
        assert str(relationship.get("source_id")) in identities
        assert str(relationship.get("target_id")) in identities
        assertion = _assertion(relationship)
        assert assertion.get("contract_version") == "user_assertion.v1"
        assert assertion.get("record_type") != "asserted_user_fact"


def _provenance_spans_match_narrative(knowledge: dict, narrative: str) -> None:
    raw = narrative.encode("utf-8")
    matched = False
    for entity in _entities(knowledge):
        assertion = _assertion(entity)
        if not assertion:
            continue
        assert assertion.get("source_hash")
        start = assertion.get("source_span_start")
        end = assertion.get("source_span_end")
        if isinstance(start, int) and isinstance(end, int) and end > start:
            assert raw[start:end].decode("utf-8") == assertion.get("source_span_text")
            assert assertion.get("source_span_text") in narrative
            matched = True
        elif assertion.get("source_span_text"):
            assert assertion.get("source_span_text") in narrative
            matched = True
    assert matched, "no entity provenance span matched the submitted narrative"


def _assert_not_legally_complete(payload: dict) -> None:
    policy = payload["stopping_policy"]
    interview = payload["interview"]
    assert interview["legal_sufficiency"] is False
    assert policy["legal_sufficiency"] is False
    assert policy["core_facts_complete"] is False
    assert policy["filing_ready"] is False
    assert policy["proof_requirements_satisfied"] is False
    assert policy["outcome"] != "complete"
    assert policy["resumable_next_action"]["resumable"] is True
    assert policy["resumable_next_action"]["worker_stalled"] is False
    assert interview.get("error") is None or interview["error"].get("legal_sufficiency") is False


def _graph_revision_fingerprint(payload: dict) -> tuple:
    shared = payload["session"]["shared_interview"]
    knowledge = shared["knowledge_graph"]
    dependency = shared["dependency_graph"]
    entity_rows = []
    for entity in _entities(knowledge):
        assertion = _assertion(entity)
        entity_rows.append(
            (
                entity.get("id"),
                entity.get("type") or entity.get("entity_type"),
                entity.get("name"),
                assertion.get("source_hash"),
                assertion.get("assertion_status"),
                assertion.get("source_kind"),
                assertion.get("record_type"),
            )
        )
    relation_rows = []
    for relationship in _relationships(knowledge):
        relation_rows.append(
            (
                relationship.get("id"),
                relationship.get("relation_type"),
                relationship.get("source_id"),
                relationship.get("target_id"),
                _assertion(relationship).get("source_hash"),
            )
        )
    node_rows = tuple(sorted(
        (node.get("id"), node.get("node_type"), node.get("name"), bool(node.get("satisfied")))
        for node in _nodes(dependency)
    ))
    digest = hashlib.sha256(
        json.dumps({"entities": sorted(entity_rows), "relationships": sorted(relation_rows), "nodes": node_rows}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    interview = payload["interview"]
    return (
        interview["inquiry"]["inquiry_id"],
        interview["expected_question_revision"],
        interview["graph"]["graph_version"],
        interview["graph"]["entity_count"],
        interview["graph"]["relationship_count"],
        digest,
    )


def _open_narrative(service: ComplaintWorkspaceService, user_id: str, narrative: str) -> dict:
    payload = run_intake_chat_turn(user_id, message=narrative, service=service)
    assert payload["original_complaint"]["text"] == narrative
    assert payload["interview"]["status"] in {"awaiting_user", "unavailable"}
    assert payload["interview"]["inquiry"]["inquiry_id"].startswith("inq-")
    return payload


def _assert_graph_case(payload: dict, narrative: str) -> None:
    shared = payload["session"]["shared_interview"]
    knowledge = shared["knowledge_graph"]
    dependency = shared["dependency_graph"]
    _assert_not_legally_complete(payload)
    _provenance_spans_match_narrative(knowledge, narrative)
    _support_endpoints_resolve(knowledge)
    requirements = [node for node in _nodes(dependency) if node.get("node_type") == "requirement"]
    assert requirements
    assert all(node.get("satisfied") is False for node in requirements)
    dependencies = _dependencies(dependency)
    assert dependencies
    node_ids = {str(node.get("id")) for node in _nodes(dependency)}
    for dependency_edge in dependencies:
        ends = {
            str(dependency_edge.get("source_id") or dependency_edge.get("source") or ""),
            str(dependency_edge.get("target_id") or dependency_edge.get("target") or ""),
        }
        assert ends & node_ids
    provenance = payload["interview"]["graph"]["provenance"]
    assert provenance.get("keys")
    assert payload["interview"]["narrative_extraction_count"] == 1
    assert shared["legal_sufficiency"] is False


def test_network_and_provider_subprocesses_stay_blocked_without_live_canary():
    assert _canary_selected() is False
    assert isinstance(subprocess.Popen, type)
    assert subprocess.Popen[bytes].__origin__ is subprocess.Popen
    with pytest.raises(RuntimeError, match="network socket blocked"):
        socket.create_connection(("192.0.2.1", 9), timeout=0.1)
    with pytest.raises(RuntimeError, match="provider subprocess blocked"):
        subprocess.run(["grok", "--version"], check=False)
    completed = subprocess.run(["/usr/bin/python3.12", "-c", "print('local-ok')"], capture_output=True, text=True, check=True)
    assert "local-ok" in completed.stdout


def test_coherent_complaint_keeps_provenance_support_and_unresolved_stop(tmp_path: Path):
    user_id = "coherent-user"
    payload = _open_narrative(_service(tmp_path, user_id), user_id, COHERENT)
    _assert_graph_case(payload, COHERENT)
    names = " ".join(str(entity.get("name") or "") for entity in _entities(payload["session"]["shared_interview"]["knowledge_graph"]))
    assert "Alex Rivera" in names
    assert payload["stopping_policy"]["outcome"] == "awaiting_user"
    assert payload["interview"]["error"]["code"] == "provider_unavailable"
    assert set(payload["interview"]["error"]["router_failures"].values()) == {"privacy_denied"}
    assert "prompt" not in payload["interview"]["error"]


def test_unknown_only_answer_does_not_complete_core_facts(tmp_path: Path):
    user_id = "unknown-user"
    service = _service(tmp_path, user_id)
    opened = _open_narrative(service, user_id, COHERENT)
    inquiry = opened["interview"]["inquiry"]
    answered = run_intake_chat_turn(
        user_id,
        message=UNKNOWN_ANSWER,
        question_id=inquiry["inquiry_id"],
        expected_question_revision=opened["interview"]["expected_question_revision"],
        service=service,
    )
    _assert_not_legally_complete(answered)
    assert "user_answer_unknown" in answered["interview"]["unknown_reasons"]
    assert answered["session"]["shared_interview"]["unknown_reasons"] == ["user_answer_unknown"]
    assert answered["interview"]["answered_count"] == 1
    assert answered["stopping_policy"]["outcome"] != "complete"
    history = answered["session"]["shared_interview"]["denoiser_history"]
    assert any(item.get("answer") == UNKNOWN_ANSWER for item in history)
    for entity in _entities(answered["session"]["shared_interview"]["knowledge_graph"]):
        assert _assertion(entity).get("assertion_status") != "accepted"


def test_contradictory_dates_remain_visible_and_unresolved(tmp_path: Path):
    user_id = "dates-user"
    payload = _open_narrative(_service(tmp_path, user_id), user_id, CONTRADICTORY)
    _assert_graph_case(payload, CONTRADICTORY)
    encoded = json.dumps(payload["session"]["shared_interview"]["knowledge_graph"])
    assert "March 4, 2024" in encoded
    assert "January 2, 2020" in encoded
    assert payload["stopping_policy"]["core_facts_complete"] is False
    assert payload["interview"]["legal_sufficiency"] is False


def test_unidentified_defendant_is_not_invented(tmp_path: Path):
    user_id = "defendant-user"
    payload = _open_narrative(_service(tmp_path, user_id), user_id, UNIDENTIFIED)
    _assert_graph_case(payload, UNIDENTIFIED)
    for entity in _entities(payload["session"]["shared_interview"]["knowledge_graph"]):
        name = str(entity.get("name") or "")
        lowered = name.lower()
        assert "john doe" not in lowered
        assert "jane doe" not in lowered
        assert "unknown defendant" not in lowered
        if name and name not in UNIDENTIFIED and entity.get("type") in {"person", "organization"}:
            assertion = _assertion(entity)
            assert assertion.get("assertion_status") != "accepted"
            assert assertion.get("source_kind") != "user_statement"


def test_missing_authority_does_not_satisfy_requirements(tmp_path: Path):
    user_id = "authority-user"
    payload = _open_narrative(_service(tmp_path, user_id), user_id, COHERENT)
    _assert_graph_case(payload, COHERENT)
    encoded = json.dumps(payload["session"]["shared_interview"])
    assert "42 U.S.C" not in encoded
    assert "citation" not in payload["interview"]["graph"]["provenance"]["keys"]
    dependency = payload["session"]["shared_interview"]["dependency_graph"]
    requirements = [node for node in _nodes(dependency) if node.get("node_type") == "requirement"]
    assert requirements
    assert all(node.get("satisfied") is False for node in requirements)
    assert payload["stopping_policy"]["proof_requirements_satisfied"] is False


def test_malformed_and_timeout_provider_output_keeps_the_session(tmp_path: Path, monkeypatch):
    from integrations.ipfs_datasets import llm

    user_id = "provider-user"
    service = _service(tmp_path, user_id)
    service.set_privacy_policy(user_id, "grok")
    calls = {"count": 0}

    def generated(prompt, **kwargs):
        calls["count"] += 1
        assert kwargs.get("provider") == "grok_cli"
        assert COHERENT in str(prompt) or kwargs.get("intake_source_text")
        kind = "malformed" if calls["count"] == 1 else "timeout"
        return {"status": kind, "failure_kind": kind, "text": "{", "error": kind, "privacy_decision": "allowed"}

    monkeypatch.setattr(llm, "generate_text_with_metadata", generated)
    opened = _open_narrative(service, user_id, COHERENT)
    assert calls["count"] >= 1
    failures = set(opened["interview"]["error"]["router_failures"].values())
    assert failures & {"malformed_output", "timeout", "provider_unavailable"}
    assert opened["original_complaint"]["text"] == COHERENT
    assert opened["interview"]["intake_complete"] is False
    _assert_graph_case(opened, COHERENT)
    resumed = service.run_intake_chat_turn(user_id, interview_action="resume")
    assert resumed["interview"]["inquiry"]["inquiry_id"] == opened["interview"]["inquiry"]["inquiry_id"]
    assert "timeout" in set(resumed["interview"]["error"]["router_failures"].values()) | failures


def test_replayed_transition_does_not_double_apply(tmp_path: Path):
    user_id = "replay-user"
    service = _service(tmp_path, user_id)
    opened = _open_narrative(service, user_id, COHERENT)
    inquiry = opened["interview"]["inquiry"]
    kwargs = dict(
        message=UNKNOWN_ANSWER,
        question_id=inquiry["inquiry_id"],
        expected_question_revision=opened["interview"]["expected_question_revision"],
        service=service,
    )
    first = run_intake_chat_turn(user_id, **kwargs)
    assert first["interview"]["answered_count"] == 1
    revision = first["interview"]["session_revision"]
    fingerprint = _graph_revision_fingerprint(first)
    second = run_intake_chat_turn(user_id, **kwargs)
    assert second["duplicate_answer_effect"] is True
    assert second.get("accepted_answer") is None
    replayed = second["session"]["shared_interview"]
    assert replayed["session_revision"] == revision
    assert replayed["answered_inquiries"] == first["session"]["shared_interview"]["answered_inquiries"]
    assert replayed["knowledge_graph"] == first["session"]["shared_interview"]["knowledge_graph"]
    assert replayed["dependency_graph"] == first["session"]["shared_interview"]["dependency_graph"]
    assert fingerprint == _graph_revision_fingerprint(first)


def test_concurrent_resume_preserves_one_inquiry(tmp_path: Path):
    user_id = "concurrent-user"
    root = tmp_path / "sessions" / user_id
    service = ComplaintWorkspaceService(root_dir=root)
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(user_id, user_id)
    opened = _open_narrative(service, user_id, COHERENT)
    inquiry_id = opened["interview"]["inquiry"]["inquiry_id"]
    found: list[str] = []
    errors: list[str] = []
    barrier = threading.Barrier(2)

    def resume() -> None:
        from integrations.private_storage import PrivateRevisionError

        barrier.wait()
        fresh = ComplaintWorkspaceService(root_dir=root)
        fresh.unlock_private_keys(passphrase=PASSPHRASE)
        try:
            payload = fresh.run_intake_chat_turn(user_id, interview_action="resume")
            found.append(payload["interview"]["inquiry"]["inquiry_id"])
        except WorkspacePersistenceError as exc:
            errors.append(exc.code)
        except PrivateRevisionError:
            errors.append("stale_revision")

    threads = [threading.Thread(target=resume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors or set(errors) <= {"revision_conflict", "write_error", "stale_revision"}
    assert inquiry_id in found
    reloaded = ComplaintWorkspaceService(root_dir=root)
    reloaded.unlock_private_keys(passphrase=PASSPHRASE)
    status = reloaded.run_intake_chat_turn(user_id, interview_action="status")
    assert status["interview"]["inquiry"]["inquiry_id"] == inquiry_id
    assert status["original_complaint"]["text"] == COHERENT
    assert status["stopping_policy"]["legal_sufficiency"] is False


def test_wrong_encryption_key_does_not_reveal_or_rewrite_the_session(tmp_path: Path):
    user_id = "locked-user"
    root = tmp_path / "sessions" / user_id
    service = ComplaintWorkspaceService(root_dir=root)
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(user_id, user_id)
    opened = _open_narrative(service, user_id, COHERENT)
    before = sorted((path, path.read_bytes()) for path in root.rglob("*") if path.is_file())
    fresh = ComplaintWorkspaceService(root_dir=root)
    refused = fresh.unlock_private_keys(passphrase="wrong-synthetic-passphrase")
    assert refused["code"] == "authentication_failed"
    assert refused["status"] == "unlock_needed"
    assert COHERENT not in json.dumps(refused)
    after = sorted((path, path.read_bytes()) for path in root.rglob("*") if path.is_file())
    assert after == before
    fresh.unlock_private_keys(passphrase=PASSPHRASE)
    loaded = fresh.run_intake_chat_turn(user_id, interview_action="resume")
    assert loaded["interview"]["inquiry"]["inquiry_id"] == opened["interview"]["inquiry"]["inquiry_id"]
    assert loaded["original_complaint"]["text"] == COHERENT


def test_interrupted_storage_write_keeps_the_last_valid_graph_revision(tmp_path: Path, monkeypatch):
    user_id = "interrupt-user"
    service = _service(tmp_path, user_id)
    opened = _open_narrative(service, user_id, COHERENT)
    shared = opened["session"]["shared_interview"]
    snapshot = assemble_interview_snapshot(
        session_id=shared["session_id"],
        revision="0",
        outcome_reason="awaiting_user",
        pending_inquiry=shared["pending_inquiry"],
        knowledge_graph=shared["knowledge_graph"],
        dependency_graph=shared["dependency_graph"],
        provenance={"keys": list(opened["interview"]["graph"]["provenance"].get("keys") or []), "status": "recorded"},
        unknown_items=[],
        deferred_items=[],
        complaint_text=COHERENT,
        transcript=[{"sender": "user", "message": COHERENT}],
        exports={"filing": "not-written"},
        durability_payload={"status": "pending"},
        revisions={
            "session_revision": shared["session_revision"],
            "question_revision": shared["question_revision"],
            "graph_revision": opened["interview"]["graph"]["graph_version"],
        },
    )
    directory = tmp_path / "snapshot"
    key = b"k" * 32
    saved = persist_interview_snapshot(
        directory, snapshot, protection="user_chosen_encrypted", tenant_id=user_id, case_id=user_id,
        principal_id=user_id, key=key, key_id="interview-key-1",
    )
    assert saved["snapshot"]["revision"] == "1"
    assert saved["receipt"]["outcome_reason"] == "awaiting_user"
    assert COHERENT not in json.dumps(saved["receipt"])

    def fail_writer(_payload: bytes) -> None:
        raise OSError("synthetic durability write failure")

    with pytest.raises(OSError, match="synthetic durability write failure"):
        persist_interview_snapshot(
            directory, snapshot, protection="user_chosen_encrypted", tenant_id=user_id, case_id=user_id,
            principal_id=user_id, key=key, key_id="interview-key-1", expected_revision="1", writer=fail_writer,
        )
    loaded = load_interview_snapshot(
        directory, protection="user_chosen_encrypted", tenant_id=user_id, case_id=user_id,
        principal_id=user_id, key=key, key_id="interview-key-1",
    )
    assert loaded["snapshot"]["revision"] == "1"
    assert loaded["snapshot"]["outcome_reason"] == "awaiting_user"
    assert loaded["snapshot"]["graphs"]["knowledge_graph"]["entities"]
    assert loaded["snapshot"]["pending_inquiry"]["inquiry_id"] == opened["interview"]["inquiry"]["inquiry_id"]
    with pytest.raises(InterviewSnapshotError) as wrong:
        load_interview_snapshot(
            directory, protection="user_chosen_encrypted", tenant_id=user_id, case_id=user_id,
            principal_id=user_id, key=b"m" * 32, key_id="interview-key-2",
        )
    assert wrong.value.code == "authentication_failed"

    def fail_session_write(*_args, **_kwargs):
        raise OSError("synthetic session write failure")

    with monkeypatch.context() as blocked_write:
        blocked_write.setattr("integrations.private_storage.commit_private_revision", fail_session_write)
        with pytest.raises(OSError, match="synthetic session write failure"):
            service.run_intake_chat_turn(user_id, interview_action="resume")
    reloaded = ComplaintWorkspaceService(root_dir=service._session_dir)
    reloaded.unlock_private_keys(passphrase=PASSPHRASE)
    status = reloaded.run_intake_chat_turn(user_id, interview_action="status")
    assert status["interview"]["inquiry"]["inquiry_id"] == opened["interview"]["inquiry"]["inquiry_id"]
    assert _graph_revision_fingerprint(status) == _graph_revision_fingerprint(opened)
    assert status["stopping_policy"]["outcome"] == opened["stopping_policy"]["outcome"]


def _api_turn(service: ComplaintWorkspaceService, user_id: str, narrative: str) -> dict:
    router = create_complaint_workspace_router(service)
    endpoint = next(route.endpoint for route in router.routes if str(route.path).endswith("/intake-chat"))
    with workspace_access_scope(WorkspaceAccess.authenticated(user_id, case_id=user_id)):
        return asyncio.run(endpoint(IntakeChatTurnRequest(user_id=user_id, message=narrative)))


def _mcp_turn(service: ComplaintWorkspaceService, user_id: str, narrative: str) -> dict:
    response = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "complaint.run_intake_chat_turn",
                "arguments": {"user_id": user_id, "message": narrative},
            },
        },
    )
    assert "error" not in response
    assert response["result"]["isError"] is False
    return response["result"]["structuredContent"]


def _terminal_turn(service: ComplaintWorkspaceService, user_id: str, narrative: str, monkeypatch) -> dict:
    import importlib
    import sys

    import applications.complaint_workspace as workspace

    monkeypatch.setattr(workspace, "_SESSION_DIR", Path(service._session_dir))
    sys.modules.pop("applications.complaint_cli", None)
    complaint_cli_impl = importlib.import_module("applications.complaint_cli")
    monkeypatch.setattr(complaint_cli_impl, "service", service)
    result = CliRunner().invoke(complaint_cli_impl.app, ["chat-turn", "--user-id", user_id, "--message", narrative])
    assert result.exit_code == 0, result.stdout
    lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.lstrip().startswith("{"):
            return json.loads("\n".join(lines[index:]))
    raise AssertionError(result.stdout)


def test_package_api_mcp_and_terminal_share_inquiry_and_graph_revision(tmp_path: Path, monkeypatch):
    narrative = COHERENT
    package_service = _service(tmp_path / "package", "package-user")
    api_service = _service(tmp_path / "api", "api-user")
    mcp_service = _service(tmp_path / "mcp", "mcp-user")
    terminal_service = _service(tmp_path / "terminal", "terminal-user")
    package_payload = _open_narrative(package_service, "package-user", narrative)
    api_payload = _api_turn(api_service, "api-user", narrative)
    mcp_payload = _mcp_turn(mcp_service, "mcp-user", narrative)
    terminal_payload = _terminal_turn(terminal_service, "terminal-user", narrative, monkeypatch)
    fingerprints = [
        _graph_revision_fingerprint(package_payload),
        _graph_revision_fingerprint(api_payload),
        _graph_revision_fingerprint(mcp_payload),
        _graph_revision_fingerprint(terminal_payload),
    ]
    assert len(set(fingerprints)) == 1
    for payload in (package_payload, api_payload, mcp_payload, terminal_payload):
        _assert_graph_case(payload, narrative)
        assert payload["stopping_policy"]["outcome"] == "awaiting_user"
        assert payload["interview"]["error"]["code"] == "provider_unavailable"
    assert {item[0] for item in fingerprints} == {package_payload["interview"]["inquiry"]["inquiry_id"]}


def test_pty_interview_matches_the_shared_graph_revision(tmp_path: Path):
    """The terminal PTY path is the same interview the package turn records."""

    from tests.test_complaint_intake_acceptance import drive_pty_interview

    user_id = "pty-shared-user"
    service = _service(tmp_path, user_id)
    transcript = drive_pty_interview(service, user_id, [COHERENT, "/quit"], max_turns=2)
    assert "plain language" in transcript or "Describe your complaint" in transcript
    status = service.run_intake_chat_turn(user_id, interview_action="status")
    _assert_graph_case(status, COHERENT)
    assert status["stopping_policy"]["outcome"] == "awaiting_user"
    assert "Alex Rivera" in json.dumps(status["session"]["shared_interview"]["knowledge_graph"])
