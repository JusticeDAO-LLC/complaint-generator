"""Resume corrections and research across real terminal sessions.

Synthetic private fixtures only. The public chat loop captures a narrative,
corrects a recorded fact, and runs one legal-research action. A new service
process restores the same pending inquiry and graph revision. Stale requests
and EOF, Ctrl-C, and quit do not extract or dispatch a second time.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from applications.complaint_cli import TerminalComplaintWorkspaceService

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

PASSPHRASE = "synthetic-mgnd-39-passphrase"
NARRATIVE = "On March 4, 2024 supervisor Alex Rivera ended the assignment. SYNTHETIC-MGND39-NARRATIVE"
ANSWER = "March 4, 2024"
CORRECTION = "March 5, 2024"


def _cases():
    return (
        "chat-corrects-researches-and-resumes",
        "stale-answer-edit-and-research-rejected",
        "eof-interrupt-and-quit-recover-without-redispatch",
    )


def _service(root: Path) -> TerminalComplaintWorkspaceService:
    service = TerminalComplaintWorkspaceService(root_dir=root)
    status = service.private_key_status()
    if status.get("protection") in {None, "", "missing"}:
        service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    if service.private_key_status().get("unlocked") is not True:
        service.unlock_private_keys(passphrase=PASSPHRASE)
    return service


def _prepare(service: TerminalComplaintWorkspaceService, user_id: str) -> None:
    service.ensure_private_case_key(user_id, user_id)
    service.prepare_private_terminal_case(user_id)


def _drive(service, user_id: str, lines: list[str], *, privacy_mode: str = "") -> tuple[int, str]:
    import applications.complaint_cli as cli

    remaining = list(lines)

    def fake_input(prompt: str = "") -> str:
        sys.stdout.write(str(prompt))
        if not remaining:
            raise EOFError
        return remaining.pop(0)

    saved = cli.service
    saved_stdin = sys.stdin
    cli.service = service
    sys.stdin = io.StringIO("")
    buffer = io.StringIO()
    code = 0
    try:
        with patch("builtins.input", fake_input), redirect_stdout(buffer):
            try:
                cli.chat(user_id=user_id, max_turns=0, privacy_mode=privacy_mode)
            except SystemExit as exc:
                code = int(exc.code or 0)
    finally:
        cli.service = saved
        sys.stdin = saved_stdin
    return code, buffer.getvalue()


def _projection(service, user_id: str) -> dict:
    state = service._load_state(user_id)
    projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
    return state, projection


def _pending_identity(projection: dict) -> dict:
    pending = projection.get("pending_inquiry") if isinstance(projection.get("pending_inquiry"), dict) else {}
    return {
        "inquiry_id": pending.get("inquiry_id"),
        "revision": pending.get("revision"),
        "question": pending.get("question"),
        "objective_id": pending.get("objective_id"),
        "target_id": pending.get("target_id"),
        "session_revision": projection.get("session_revision"),
        "question_revision": projection.get("question_revision"),
        "narrative_extraction_count": projection.get("narrative_extraction_count"),
    }


def _graph_token(projection: dict) -> str:
    from complaint_phases.knowledge_graph import KnowledgeGraph
    from mediator.hook_runtime import graph_revision_token

    graph = projection.get("knowledge_graph") if isinstance(projection.get("knowledge_graph"), dict) else {}
    return graph_revision_token(KnowledgeGraph.from_dict(graph))


def _plaintext_hits(root: Path, token: str) -> list[str]:
    needle = token.encode("utf-8")
    hits = []
    for path in root.rglob("*"):
        if path.is_file() and needle in path.read_bytes():
            hits.append(path.relative_to(root).as_posix())
    return hits


def test_case_list_is_nonempty():
    assert len(_cases()) >= 3


def test_chat_corrects_researches_and_resumes_in_a_fresh_service(tmp_path: Path):
    user_id = "mgnd39-resume"
    root = tmp_path / "sessions"
    service = _service(root)
    _prepare(service, user_id)
    code, transcript = _drive(
        service,
        user_id,
        [NARRATIVE, ANSWER, f"/edit {CORRECTION}", "/research", "/research", "/quit"],
        privacy_mode="local",
    )
    assert code == 0, transcript
    assert "Chat paused" in transcript
    assert "Edited the last recorded answer" in transcript
    state, projection = _projection(service, user_id)
    assert state["original_complaint"]["text"] == NARRATIVE
    assert projection["narrative_extraction_count"] == 1
    assert state["privacy_policy"]["processing_mode"] == "local_private"
    identity = _pending_identity(projection)
    token = _graph_token(projection)
    assert identity["inquiry_id"]
    graph_text = json.dumps(projection.get("knowledge_graph"))
    assert ANSWER in graph_text
    assert CORRECTION in graph_text
    research = state.get("legal_research") if isinstance(state.get("legal_research"), dict) else {}
    assert int(research.get("dispatch_count") or 0) == 1
    latest = (research.get("receipts") or {}).get(research.get("latest_fingerprint"))
    assert isinstance(latest, dict)
    assert latest["proof"] is False
    assert latest["legal_sufficiency"] is False
    assert latest["stored_as_answer"] is False
    assert latest.get("replayed") is True or latest.get("dispatched") is True
    edition = projection.get("dependency_graph")
    assert isinstance(edition, dict)
    assert _plaintext_hits(root, "SYNTHETIC-MGND39-NARRATIVE") == []

    fresh = _service(root)
    _prepare(fresh, user_id)
    resumed_code, resumed_transcript = _drive(fresh, user_id, ["/status", "/research", "/quit"])
    assert resumed_code == 0
    assert "Restored pending question" in resumed_transcript
    resumed_state, resumed_projection = _projection(fresh, user_id)
    assert _pending_identity(resumed_projection) == identity
    assert _graph_token(resumed_projection) == token
    assert resumed_projection.get("dependency_graph") == edition
    assert resumed_state["privacy_policy"] == state["privacy_policy"]
    assert int(resumed_state["legal_research"]["dispatch_count"]) == 1
    assert resumed_projection["narrative_extraction_count"] == 1

    env = os.environ.copy()
    env.update({
        "HF_HUB_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "MGND39_ROOT": str(root),
        "MGND39_USER": user_id,
        "MGND39_PASS": PASSPHRASE,
    })
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join([
                "import json, os",
                "from applications.complaint_cli import TerminalComplaintWorkspaceService",
                "service = TerminalComplaintWorkspaceService(root_dir=os.environ['MGND39_ROOT'])",
                "service.unlock_private_keys(passphrase=os.environ['MGND39_PASS'])",
                "state = service._load_state(os.environ['MGND39_USER'])",
                "projection = state['shared_interview']",
                "pending = projection['pending_inquiry']",
                "print(json.dumps({",
                "    'inquiry_id': pending.get('inquiry_id'),",
                "    'revision': pending.get('revision'),",
                "    'extraction': projection.get('narrative_extraction_count'),",
                "    'session_revision': projection.get('session_revision'),",
                "    'dispatch_count': state['legal_research']['dispatch_count'],",
                "    'processing_mode': state['privacy_policy']['processing_mode'],",
                "}))",
            ]),
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout.strip().splitlines()[-1])
    assert observed["inquiry_id"] == identity["inquiry_id"]
    assert observed["revision"] == identity["revision"]
    assert observed["extraction"] == 1
    assert observed["session_revision"] == identity["session_revision"]
    assert observed["dispatch_count"] == 1
    assert observed["processing_mode"] == "local_private"


def test_stale_answer_edit_and_research_do_not_change_accepted_state(tmp_path: Path):
    user_id = "mgnd39-stale"
    root = tmp_path / "sessions"
    service = _service(root)
    _prepare(service, user_id)
    code, _transcript = _drive(service, user_id, [NARRATIVE, ANSWER, "/quit"], privacy_mode="local")
    assert code == 0
    state, projection = _projection(service, user_id)
    identity = _pending_identity(projection)
    token = _graph_token(projection)
    session_revision = int(projection.get("session_revision") or 0)
    inquiry = projection.get("pending_inquiry") or {}
    before = json.dumps(projection, sort_keys=True, default=str)

    stale_answer = service.run_intake_chat_turn(
        user_id,
        message="A conflicting later answer.",
        question_id=str(inquiry.get("inquiry_id") or ""),
        expected_question_revision=int(inquiry.get("revision") or 0) + 9,
        interview_action="answer",
    )
    assert stale_answer["interview"]["status"] == "refused"
    assert stale_answer["interview"]["error"]["code"] == "stale_question"

    stale_edit = service.apply_terminal_graph_edit(
        user_id,
        "This stale edit must not land.",
        expected_graph_revision="gr_stale",
        expected_session_revision=session_revision,
    )
    assert stale_edit["status"] != "applied"
    assert stale_edit["error"]["code"] == "stale_target"

    stale_research = service.run_legal_research(
        user_id,
        expected_graph_revision="gr_stale",
        expected_session_revision=session_revision,
    )
    assert stale_research["status"] == "refused"
    assert stale_research["error_code"] == "stale_research"
    assert stale_research["dispatched"] is False

    reloaded, reloaded_projection = _projection(service, user_id)
    assert json.dumps(reloaded_projection, sort_keys=True, default=str) == before
    assert _pending_identity(reloaded_projection) == identity
    assert _graph_token(reloaded_projection) == token
    assert int((reloaded.get("legal_research") or {}).get("dispatch_count") or 0) == 0
    assert "This stale edit must not land." not in json.dumps(reloaded_projection.get("knowledge_graph"))
    assert "A conflicting later answer." not in json.dumps(reloaded)


def test_eof_interrupt_and_quit_recover_without_duplicate_dispatch(tmp_path: Path, monkeypatch):
    from mediator.legal_authority_hooks import LegalAuthoritySearchHook

    user_id = "mgnd39-signals"
    root = tmp_path / "sessions"
    service = _service(root)
    _prepare(service, user_id)
    eof_code, eof_transcript = _drive(service, user_id, [NARRATIVE])
    assert eof_code == 1
    assert "exit 1" in eof_transcript
    _state, projection = _projection(service, user_id)
    assert projection["narrative_extraction_count"] == 1
    identity = _pending_identity(projection)

    fresh = _service(root)
    _prepare(fresh, user_id)
    quit_code, quit_transcript = _drive(fresh, user_id, ["/quit"])
    assert quit_code == 0
    assert "Chat paused" in quit_transcript
    _state, after_quit = _projection(fresh, user_id)
    assert after_quit["narrative_extraction_count"] == 1
    assert _pending_identity(after_quit) == identity
    assert _state["terminal_controls"]["stop_reason"] == "user_quit"

    calls = {"count": 0}
    original = LegalAuthoritySearchHook.acquire_bounded_canonical_sources

    def interrupt_once(self, binding, **kwargs):
        calls["count"] += 1
        raise KeyboardInterrupt

    monkeypatch.setattr(LegalAuthoritySearchHook, "acquire_bounded_canonical_sources", interrupt_once)
    interrupted = _service(root)
    _prepare(interrupted, user_id)
    interrupt_code, interrupt_transcript = _drive(interrupted, user_id, ["/research"])
    assert interrupt_code == 130
    assert "exit 130" in interrupt_transcript
    assert calls["count"] == 1
    held, held_projection = _projection(interrupted, user_id)
    pending_operation = held["legal_research"]["pending_operation"]
    assert pending_operation["dispatched"] is True
    assert pending_operation["kind"] == "legal_research"
    assert held["terminal_controls"]["pending_operation"]["fingerprint"] == pending_operation["fingerprint"]
    assert held_projection["narrative_extraction_count"] == 1
    assert _pending_identity(held_projection) == identity

    monkeypatch.setattr(LegalAuthoritySearchHook, "acquire_bounded_canonical_sources", original)
    recovered = _service(root)
    _prepare(recovered, user_id)
    replay = recovered.run_legal_research(user_id)
    assert replay["dispatched"] is False
    assert replay["replayed"] is True
    assert calls["count"] == 1
    assert int(recovered._load_state(user_id)["legal_research"]["dispatch_count"]) == 1
    assert recovered._load_state(user_id)["shared_interview"]["narrative_extraction_count"] == 1
