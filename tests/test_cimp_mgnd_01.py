"""Characterize public chat grounding, edit, and encrypted resume.

This module records the current control path. It is not product acceptance
and it does not require a known defect to stay broken. Diagnostics carry
counts and classifications only, never synthetic narrative text.
"""

from __future__ import annotations

import hashlib
import importlib
import io
import json
import os
import signal
import socket
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from tests.private_session_assertions import assert_private_session_frame, private_session_path


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "docs" / "task_boards" / "complaint_mediator_grounding_baseline_receipt.json"
SOURCE_PATHS = (
    "applications/complaint_cli.py",
    "applications/complaint_workspace.py",
    "mediator/workflow_service.py",
)
PASSPHRASE = "synthetic-mgnd-01-passphrase"
USER_ID = "synthetic-mgnd-01"
NARRATIVE = "On 4 March 2024 Alex Rivera ended my job after I reported a safety concern."
EDIT_TEXT = "Synthetic Edited Answer"
UNKNOWN_ANSWER = "I don't know"
DEADLINE_SECONDS = 45
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
_GAP_CLASSIFICATIONS = frozenset({
    "observed_gap",
    "not_observed",
    "closed_by_later_fix",
    "dependency_unavailable",
})
_MECHANIC_CLASSIFICATION = "characterization_mechanic"


def _fail(message: str) -> None:
    raise AssertionError(message)


def _command_basename(args, kwargs) -> str:
    command = args[0] if args else kwargs.get("args")
    if command is None:
        return ""
    if isinstance(command, (str, bytes)):
        token = os.fsdecode(command).split()
        token = token[0] if token else ""
    else:
        token = os.fsdecode(command[0]) if command else ""
    return Path(token).name.lower()


def _bind_libmagic(monkeypatch: pytest.MonkeyPatch) -> None:
    library = Path("/usr/lib/x86_64-linux-gnu/libmagic.so.1.0.0")
    if not library.is_file():
        _fail("libmagic_dependency_unavailable")
    info = library.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
        _fail("libmagic_dependency_untrusted")
    import ctypes.util

    original = ctypes.util.find_library

    def find_library(name: str):
        if name == "magic":
            return str(library)
        return original(name)

    monkeypatch.setattr(ctypes.util, "find_library", find_library)


def _block_network_and_provider_subprocesses(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*_args, **_kwargs):
        raise RuntimeError("network socket blocked")

    monkeypatch.setattr(socket.socket, "connect", blocked_socket)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked_socket)
    monkeypatch.setattr(socket, "create_connection", blocked_socket)
    original_popen = subprocess.Popen

    class GuardedPopen(original_popen):
        def __init__(self, *args, **kwargs):
            if _command_basename(args, kwargs) in _PROVIDER_BASENAMES:
                raise RuntimeError("provider subprocess blocked")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", GuardedPopen)

    def guarded(real):
        def wrapped(*args, **kwargs):
            if _command_basename(args, kwargs) in _PROVIDER_BASENAMES:
                raise RuntimeError("provider subprocess blocked")
            return real(*args, **kwargs)

        return wrapped

    monkeypatch.setattr(subprocess, "run", guarded(subprocess.run))
    monkeypatch.setattr(subprocess, "call", guarded(subprocess.call))
    monkeypatch.setattr(subprocess, "check_call", guarded(subprocess.check_call))
    monkeypatch.setattr(subprocess, "check_output", guarded(subprocess.check_output))


def _source_generation(*, revision: str | None = None) -> dict:
    if revision is not None and (
        len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision)
    ):
        _fail("baseline_source_revision_invalid")
    digest = hashlib.sha256()
    files = []
    for relative in SOURCE_PATHS:
        if revision is None:
            data = (ROOT / relative).read_bytes()
        else:
            # The committed baseline is historical evidence. Read its actual
            # Git blobs without changing the checkout or refreshing receipts.
            data = subprocess.run(
                ["git", "--no-optional-locks", "-c", "core.hooksPath=/dev/null", "-C", str(ROOT),
                 "show", f"{revision}:{relative}"],
                check=True, capture_output=True, timeout=10,
            ).stdout
        file_hash = hashlib.sha256(data).hexdigest()
        files.append({"path": relative, "sha256": file_hash, "bytes": len(data)})
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
    return {
        "name": "cimp-mgnd-01-public-control-owners",
        "algorithm": "sha256",
        "digest": digest.hexdigest(),
        "files": files,
    }


def _rows(graph: dict, key: str) -> list:
    raw = graph.get(key) or {}
    if isinstance(raw, dict):
        return [item for item in raw.values() if isinstance(item, dict)]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _assertion(record: dict) -> dict:
    provenance = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
    assertion = provenance.get("user_assertion")
    return assertion if isinstance(assertion, dict) else {}


def _span_counts(graph: dict, narrative: str) -> dict:
    raw = narrative.encode("utf-8")
    matched = 0
    user_facts = 0
    present = 0
    for entity in _rows(graph, "entities"):
        assertion = _assertion(entity)
        if not assertion:
            continue
        present += 1
        if assertion.get("record_type") == "asserted_user_fact":
            user_facts += 1
        start = assertion.get("source_span_start")
        end = assertion.get("source_span_end")
        text = assertion.get("source_span_text")
        if isinstance(start, int) and isinstance(end, int) and isinstance(text, str) and end > start:
            try:
                excerpt = raw[start:end].decode("utf-8")
            except UnicodeDecodeError:
                excerpt = ""
            if excerpt == text and text in narrative:
                matched += 1
    return {
        "entity_count": len(_rows(graph, "entities")),
        "relationship_count": len(_rows(graph, "relationships")),
        "user_assertion_count": present,
        "user_fact_count": user_facts,
        "narrative_span_match_count": matched,
    }


def _dependency_gap(graph: dict) -> dict:
    nodes = _rows(graph, "nodes") or _rows(graph, "requirements") or _rows(graph, "dependencies")
    missing_source = 0
    for node in nodes:
        source = node.get("source") or node.get("source_id") or node.get("authority") or node.get("citation")
        if not source:
            missing_source += 1
    return {
        "node_count": len(nodes),
        "missing_source_count": missing_source,
        "graph_present": bool(graph),
    }


def _classify_gap(observed: bool) -> str:
    return "observed_gap" if observed else "not_observed"


def _install_synthetic_transport(monkeypatch: pytest.MonkeyPatch) -> dict:
    try:
        from ipfs_accelerate_py.cli_runtime.grok_invocation_observation import (
            GrokInvocationObservation,
            ObservedTextGeneration,
        )
    except Exception as exc:
        return {"available": False, "reason": type(exc).__name__, "calls": []}

    calls: list[dict] = []

    def generate(**kwargs):
        prompt = kwargs.get("prompt")
        if not isinstance(prompt, str):
            _fail("synthetic_transport_prompt_unavailable")
        decoder = json.JSONDecoder()
        start = prompt.find("{")
        if start < 0:
            _fail("synthetic_transport_control_unavailable")
        control, _end = decoder.raw_decode(prompt[start:])
        operation = control.get("operation")
        request_id = kwargs.get("observation_request_id")
        body = {
            "schema_version": control.get("schema_version"),
            "operation": operation,
            "request_id": request_id,
            "questions": [],
            "facts": [],
        }
        targets = control.get("allowed_targets") if isinstance(control.get("allowed_targets"), dict) else {}
        source_text = control.get("source_text") if isinstance(control.get("source_text"), str) else ""
        if operation == "extract_facts":
            needle = "4 March 2024"
            encoded = source_text.encode("utf-8")
            offset = encoded.find(needle.encode("utf-8"))
            for ref, meta in targets.items():
                if isinstance(meta, dict) and meta.get("field") == "date" and offset >= 0:
                    body["facts"] = [{
                        "field": "date",
                        "value": needle,
                        "source_start": offset,
                        "source_end": offset + len(needle.encode("utf-8")),
                        "target_ref": ref,
                    }]
                    break
        elif operation == "propose_questions":
            for ref, meta in targets.items():
                if not isinstance(meta, dict):
                    continue
                question_id = meta.get("question_id")
                prompt_text = meta.get("prompt")
                if isinstance(question_id, str) and isinstance(prompt_text, str) and prompt_text.strip():
                    body["questions"] = [{
                        "question_id": question_id,
                        "prompt": prompt_text[:500],
                        "target_ref": ref,
                    }]
                    break
        calls.append({
            "operation": operation,
            "request_id_present": isinstance(request_id, str) and len(request_id) == 32,
            "timeout": kwargs.get("timeout"),
            "provider": kwargs.get("provider"),
            "live_command": kwargs.get("grok_cli_cmd") == ["grok"],
        })
        observation = GrokInvocationObservation(
            invocation_id=hashlib.sha256(str(request_id).encode("utf-8")).hexdigest()[:32],
            request_id=request_id,
            native_dispatch_count=1,
            selected_provider_name="grok_cli",
            selected_model_name="grok-4.7",
            provider_reported_model="grok-4.7",
            process_returncode=0,
            stream_complete=True,
            wire_model_observed=True,
            evidence_class="native_final_end_model_usage",
        )
        return ObservedTextGeneration(json.dumps(body), observation)

    def loader():
        return generate, ObservedTextGeneration, GrokInvocationObservation

    import backends.llm_router_backend as backend_module
    from integrations.ipfs_datasets import llm

    monkeypatch.setattr(backend_module, "load_observed_llm_symbols", loader)
    monkeypatch.setattr(llm, "load_observed_llm_symbols", loader)
    return {"available": True, "reason": "", "calls": calls}


def _forbid_live_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden():
        raise AssertionError("live_provider_discovery")

    import backends.llm_router_backend as backend_module
    from integrations.ipfs_datasets import llm

    monkeypatch.setattr(backend_module, "load_observed_llm_symbols", forbidden)
    monkeypatch.setattr(llm, "load_observed_llm_symbols", forbidden)


def _owned_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _bind_libmagic(monkeypatch)
    _block_network_and_provider_subprocesses(monkeypatch)
    workspace = importlib.import_module("applications.complaint_workspace")
    monkeypatch.setattr(workspace, "_SESSION_DIR", tmp_path / "global-import")
    prior = sys.modules.pop("applications.complaint_cli", None)
    package = importlib.import_module("applications")
    previous_attribute = getattr(package, "complaint_cli", None)
    import applications.complaint_cli as cli

    service = cli.TerminalComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(USER_ID, USER_ID)
    monkeypatch.setattr(cli, "service", service)
    return cli, service, prior, package, previous_attribute


def _release_cli(prior, package, previous_attribute) -> None:
    sys.modules.pop("applications.complaint_cli", None)
    if prior is not None:
        sys.modules["applications.complaint_cli"] = prior
    if previous_attribute is not None:
        setattr(package, "complaint_cli", previous_attribute)
    elif hasattr(package, "complaint_cli"):
        delattr(package, "complaint_cli")


def _run_chat(cli, monkeypatch: pytest.MonkeyPatch, privacy_mode: str) -> int:
    script = "\n".join([NARRATIVE, ".", "/why", "/edit " + EDIT_TEXT, UNKNOWN_ANSWER, ""])
    monkeypatch.setattr(sys, "stdin", io.StringIO(script))
    previous_alarm = signal.getsignal(signal.SIGALRM)

    def _deadline(_signum, _frame):
        raise TimeoutError("terminal_deadline")

    signal.signal(signal.SIGALRM, _deadline)
    signal.alarm(DEADLINE_SECONDS)
    try:
        with pytest.raises(SystemExit) as exited:
            cli.chat(user_id=USER_ID, max_turns=2, privacy_mode=privacy_mode)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_alarm)
    code = exited.value.code
    if code != 0:
        _fail(f"chat_exit_{code}")
    return int(code)


def _measure(service, transport: dict, transcript: str) -> dict:
    session_payload = service.get_session(USER_ID)
    session = session_payload.get("session") if isinstance(session_payload.get("session"), dict) else {}
    projection = session.get("shared_interview") if isinstance(session.get("shared_interview"), dict) else {}
    knowledge = projection.get("knowledge_graph") if isinstance(projection.get("knowledge_graph"), dict) else {}
    dependency = projection.get("dependency_graph") if isinstance(projection.get("dependency_graph"), dict) else {}
    spans = _span_counts(knowledge, NARRATIVE)
    dependencies = _dependency_gap(dependency)
    why = service.run_intake_chat_turn(USER_ID, message="/why")
    why_meta = why.get("why") if isinstance(why.get("why"), dict) else {}
    controls = session.get("terminal_controls") if isinstance(session.get("terminal_controls"), dict) else {}
    # /why above may have saved nothing; reload after the command for edit state.
    edited = service.get_session(USER_ID)
    edited_session = edited.get("session") if isinstance(edited.get("session"), dict) else {}
    edited_controls = edited_session.get("terminal_controls") if isinstance(edited_session.get("terminal_controls"), dict) else controls
    edits = edited_controls.get("edits") if isinstance(edited_controls.get("edits"), list) else []
    answers = edited_session.get("intake_answers") if isinstance(edited_session.get("intake_answers"), dict) else {}
    edited_projection = edited_session.get("shared_interview") if isinstance(edited_session.get("shared_interview"), dict) else {}
    graph_blob = json.dumps(edited_projection.get("knowledge_graph") or {}, sort_keys=True)
    edit_in_answers = EDIT_TEXT in {str(value) for value in answers.values()} or any(
        isinstance(item, dict) and item.get("replacement") == EDIT_TEXT for item in edits
    )
    edit_in_graph = EDIT_TEXT in graph_blob
    receipts = ((session.get("router_trace") or {}).get("receipts") or []) if isinstance(session.get("router_trace"), dict) else []
    live_receipts = [
        item for item in receipts
        if isinstance(item, dict) and (item.get("router_receipt") or {}).get("live_canary") is True
    ]
    interview = why.get("interview") if isinstance(why.get("interview"), dict) else {}
    stalled = interview.get("worker_stalled")
    if stalled is None and isinstance(interview.get("stopping_policy"), dict):
        stalled = interview["stopping_policy"].get("worker_stalled")
    why_keys = sorted(key for key in ("command", "display", "stored_as_answer", "awaiting_user", "objective_id", "target_id", "why_it_matters") if key in why_meta)
    chat_saw_why = "Why this question:" in transcript or "There is no current question to explain." in transcript
    chat_saw_edit = (
        "Edited the last recorded answer." in transcript
        or "Nothing to edit yet." in transcript
        or "Edit needs replacement text." in transcript
    )
    return {
        "transport_available": transport["available"] is True,
        "transport_reason": transport.get("reason") or "",
        "synthetic_call_count": len(transport.get("calls") or []),
        "synthetic_operations": sorted({str(item.get("operation")) for item in transport.get("calls") or []}),
        "live_grok_call": bool(live_receipts),
        "chat_exit": 0,
        "projection_present": bool(projection),
        "session_id_present": bool(projection.get("session_id")),
        "legal_sufficiency": projection.get("legal_sufficiency"),
        "spans": spans,
        "dependencies": dependencies,
        "why_keys": why_keys,
        "why_stored_as_answer": why.get("stored_as_answer"),
        "why_awaiting_user": why.get("awaiting_user"),
        "why_command": why_meta.get("command"),
        "chat_saw_why": chat_saw_why,
        "chat_saw_edit": chat_saw_edit,
        "edit_in_terminal_state": edit_in_answers,
        "edit_in_shared_graph": edit_in_graph,
        "worker_stalled": stalled,
        "interview_status": interview.get("status") or why.get("status"),
    }


def test_public_chat_characterizes_grounding_edit_and_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """Drive the real terminal command, then a fresh encrypted service."""

    cli, service, prior, package, previous_attribute = _owned_cli(tmp_path, monkeypatch)
    try:
        transport = _install_synthetic_transport(monkeypatch)
        if transport["available"]:
            privacy_mode = "grok"
        else:
            privacy_mode = "local"
            _forbid_live_provider(monkeypatch)
        _run_chat(cli, monkeypatch, privacy_mode)
        captured = capsys.readouterr()
        measured = _measure(service, transport, captured.out + captured.err)
        if measured["live_grok_call"] is not False:
            _fail("live_grok_call_recorded")
        if measured["why_command"] != "/why" or measured["why_stored_as_answer"] is not False:
            _fail("why_metadata_missing")
        if measured["why_awaiting_user"] is not True:
            _fail("why_not_awaiting_user")
        if measured["chat_saw_why"] is not True or measured["chat_saw_edit"] is not True:
            _fail("terminal_commands_not_exercised")
        if measured["worker_stalled"] is True:
            _fail("awaiting_user_reported_as_stalled_worker")
        if transport["available"]:
            if measured["synthetic_call_count"] < 1:
                _fail("synthetic_transport_not_invoked")
            timeouts = [item.get("timeout") for item in transport["calls"]]
            if any(not isinstance(item, (int, float)) or item <= 0 or item > 60 for item in timeouts):
                _fail("synthetic_transport_deadline_unbounded")
        else:
            if measured["transport_reason"] == "":
                _fail("transport_unavailability_not_truthful")
        encrypted = private_session_path(service._session_dir, USER_ID)
        frame = encrypted.read_bytes()
        assert_private_session_frame(frame, NARRATIVE, EDIT_TEXT, PASSPHRASE)
        before = service.get_session(USER_ID)["session"]
        before_projection = before.get("shared_interview") if isinstance(before.get("shared_interview"), dict) else {}
        restarted = cli.TerminalComplaintWorkspaceService(root_dir=service._session_dir)
        if restarted is service:
            _fail("resume_reused_service_instance")
        restarted.unlock_private_keys(passphrase=PASSPHRASE)
        resumed = restarted.run_intake_chat_turn(USER_ID, interview_action="resume")
        resumed_session = resumed.get("session") if isinstance(resumed.get("session"), dict) else {}
        if resumed_session.get("user_id") != USER_ID:
            _fail("resume_user_mismatch")
        resumed_narrative = (resumed_session.get("original_complaint") or {}).get("text")
        if resumed_narrative != NARRATIVE:
            _fail("resume_narrative_mismatch")
        resumed_projection = resumed_session.get("shared_interview") if isinstance(resumed_session.get("shared_interview"), dict) else {}
        if before_projection.get("session_id") and resumed_projection.get("session_id") != before_projection.get("session_id"):
            _fail("resume_session_id_mismatch")
        if json.dumps(resumed_projection.get("knowledge_graph") or {}, sort_keys=True) != json.dumps(before_projection.get("knowledge_graph") or {}, sort_keys=True):
            _fail("resume_graph_mismatch")
        gaps = {
            "narrative_assertion_spans": _classify_gap(measured["spans"]["narrative_span_match_count"] == 0),
            "dependency_source": _classify_gap(
                not measured["dependencies"]["graph_present"] or measured["dependencies"]["missing_source_count"] > 0
            ),
            "edit_versus_shared_graph": _classify_gap(
                measured["edit_in_terminal_state"] and not measured["edit_in_shared_graph"]
            ),
            "observed_router": _classify_gap(not measured["transport_available"]),
        }
        summary = {
            "transport_available": measured["transport_available"],
            "transport_reason": measured["transport_reason"],
            "synthetic_call_count": measured["synthetic_call_count"],
            "synthetic_operations": measured["synthetic_operations"],
            "live_grok_call": False,
            "projection_present": measured["projection_present"],
            "legal_sufficiency": measured["legal_sufficiency"] is True,
            "entity_count": measured["spans"]["entity_count"],
            "user_assertion_count": measured["spans"]["user_assertion_count"],
            "narrative_span_match_count": measured["spans"]["narrative_span_match_count"],
            "dependency_node_count": measured["dependencies"]["node_count"],
            "dependency_missing_source_count": measured["dependencies"]["missing_source_count"],
            "why_keys": measured["why_keys"],
            "edit_in_terminal_state": measured["edit_in_terminal_state"],
            "edit_in_shared_graph": measured["edit_in_shared_graph"],
            "resume_encrypted": True,
            "gaps": gaps,
        }
        assert summary["live_grok_call"] is False
        assert summary["resume_encrypted"] is True
        assert set(gaps) == {"narrative_assertion_spans", "dependency_source", "edit_versus_shared_graph", "observed_router"}
        assert all(value in _GAP_CLASSIFICATIONS for value in gaps.values())
    finally:
        _release_cli(prior, package, previous_attribute)


def test_receipt_pins_source_generation_without_campaign_claim() -> None:
    """The receipt pins the declared historical baseline, not later fixes."""

    if not RECEIPT_PATH.is_file():
        _fail("baseline_receipt_absent")
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        _fail("baseline_receipt_not_object")
    if receipt.get("schema_version") != "complaint-generator.mediator-grounding-baseline-receipt.v1":
        _fail("baseline_receipt_schema")
    if receipt.get("task_id") != "CIMP-MGND-01":
        _fail("baseline_receipt_task")
    if receipt.get("product_acceptance") is not False:
        _fail("baseline_receipt_product_acceptance")
    if receipt.get("all_new_campaign_behavior_works") is not False:
        _fail("baseline_receipt_claims_campaign")
    if receipt.get("live_grok_call") is not False:
        _fail("baseline_receipt_claims_live_grok")
    generation = receipt.get("source_generation")
    if not isinstance(generation, dict) or not str(generation.get("name") or "").strip():
        _fail("baseline_receipt_source_generation_unnamed")
    spec = json.loads((ROOT / "docs/task_boards/complaint_mediator_grounding_spec.json").read_text(encoding="utf-8"))
    baseline = spec.get("baseline_commit")
    if not isinstance(baseline, str):
        _fail("baseline_source_revision_absent")
    historical = _source_generation(revision=baseline)
    if generation.get("algorithm") != "sha256" or generation.get("digest") != historical["digest"]:
        _fail("baseline_receipt_source_generation_mismatch")
    if generation.get("files") != historical["files"]:
        _fail("baseline_receipt_source_files_mismatch")
    if generation.get("name") != historical["name"]:
        _fail("baseline_receipt_source_name_mismatch")
    observations = receipt.get("observations")
    if not isinstance(observations, list) or len(observations) < 2:
        _fail("baseline_receipt_observations_empty")
    mechanics = []
    gaps = []
    for item in observations:
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            _fail("baseline_receipt_observation_identity")
        if not str(item.get("observation") or "").strip():
            _fail("baseline_receipt_observation_empty")
        if item.get("product_acceptance") is not False:
            _fail("baseline_receipt_observation_accepts_product")
        classification = item.get("classification")
        if classification == _MECHANIC_CLASSIFICATION:
            mechanics.append(item)
        elif classification in _GAP_CLASSIFICATIONS:
            gaps.append(item)
            if item.get("counts_as_characterization_pass") is not False:
                _fail("baseline_receipt_gap_folded_into_pass")
        else:
            _fail("baseline_receipt_classification")
    if not mechanics or not gaps:
        _fail("baseline_receipt_gaps_not_separate")
    if any(item.get("counts_as_characterization_pass") is not True for item in mechanics):
        _fail("baseline_receipt_mechanic_not_marked")
