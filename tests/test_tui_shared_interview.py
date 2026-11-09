"""Shared interview transition over the existing three-phase engine.

Callers share one versioned session, inquiry id, and question revision.
Tests use the real mediator, workspace, package facade, and legacy CLI with a
deterministic backend, temporary databases, and network/process guards.
"""

from __future__ import annotations

from copy import deepcopy
import importlib
import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

from applications.cli import CLI
from applications.complaint_workspace import ComplaintWorkspaceService
from complaint_generator.workspace import run_intake_chat_turn
from integrations.ipfs_datasets.llm import privacy_policy_for_mode
from mediator.exceptions import UserPresentableException
from mediator.mediator import Mediator

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

NARRATIVE = "On March 4, 2024 supervisor Alex Rivera fired me after I reported safety concerns."
ANSWER = "Alex Rivera was my supervisor at Northwind Tools and fired me on March 4, 2024."


def _block_external(monkeypatch) -> None:
    def blocked(*_args, **_kwargs):
        raise RuntimeError("external operation blocked")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, blocked)


def _backend_factory():
    calls = []

    def backend(prompt, complaint_privacy_context=None, **kwargs):
        calls.append({"prompt": prompt, "privacy": complaint_privacy_context, "kwargs": kwargs})
        return '{"entities":[],"relationships":[]}'

    return backend, calls


def _mediator(tmp_path: Path, *, backend=None):
    db_dir = tmp_path / "dbs"
    db_dir.mkdir(parents=True, exist_ok=True)
    if backend is None:
        backend, _calls = _backend_factory()
    mediator = Mediator(
        [backend],
        evidence_db_path=str(db_dir / "evidence.db"),
        legal_authority_db_path=str(db_dir / "legal-authority.db"),
        claim_support_db_path=str(db_dir / "claim-support.db"),
    )
    mediator.state.username = "synthetic-user"
    mediator.workflow_actions.bind_interview_privacy(
        privacy_policy_for_mode("synthetic-user", "synthetic-user", "local"),
        user_id="synthetic-user",
        case_id="synthetic-user",
    )
    return mediator


def _service(tmp_path: Path, user_id: str) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase="synthetic-shared-interview-passphrase")
    service.ensure_private_case_key(user_id, user_id)
    return service


def _assert_refused_state_unchanged(before, after):
    for field in ("shared_interview", "intake_router", "intake_answers", "intake_history"):
        assert after.get(field) == before.get(field), field


def _assert_local_role_failure(receipt):
    assert receipt["error"]["code"] == "provider_unavailable"
    assert receipt["error"]["resumable"] is True
    assert set(receipt["error"]["router_failures"].values()) == {"privacy_denied"}
    assert receipt["intake_complete"] is False
    assert receipt["readiness"]["ready_to_advance"] is False


def _graph_fingerprint(mediator) -> tuple:
    from complaint_phases import ComplaintPhase

    kg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    dg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    return (
        tuple(sorted(getattr(kg, "entities", {}))),
        tuple(sorted(getattr(dg, "nodes", {}))),
        mediator.phase_manager.iteration_count,
        len(mediator.denoiser.questions_asked),
    )


def test_graph_answer_updates_provenance_and_shared_inquiry(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    mediator = _mediator(tmp_path)
    started = mediator.transition_shared_interview(action="start", narrative=NARRATIVE)
    assert started["contract_version"] == "interview-transition-v1"
    assert started["status"] == "awaiting_user"
    assert started["legal_sufficiency"] is False
    assert started["narrative_extraction_count"] == 1
    inquiry_id = started["inquiry"]["inquiry_id"]
    revision = started["expected_question_revision"]
    assert inquiry_id.startswith("inq-")
    assert revision == 1
    before = _graph_fingerprint(mediator)
    answered = mediator.transition_shared_interview(
        action="answer",
        answer=ANSWER,
        inquiry_id=inquiry_id,
        expected_question_revision=revision,
    )
    assert answered["error"] is None
    assert answered["inquiry"]["inquiry_id"] != inquiry_id or answered["expected_question_revision"] != revision
    assert answered["session_id"] == started["session_id"]
    assert answered["session_revision"] == started["session_revision"] + 1
    assert answered["legal_sufficiency"] is False
    after = _graph_fingerprint(mediator)
    assert after[2] > before[2]
    assert after[3] > before[3]
    assert isinstance(answered["graph"]["provenance"], dict)
    status = mediator.transition_shared_interview(action="status")
    assert status["inquiry"]["inquiry_id"] == answered["inquiry"]["inquiry_id"]
    assert status["expected_question_revision"] == answered["expected_question_revision"]
    saved = mediator.get_state()
    assert saved["shared_interview"]["schema_version"] == "shared-interview-session-v1"
    assert "prompt" not in (answered.get("error") or {})


def test_stale_question_refuses_without_mutation(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    mediator = _mediator(tmp_path)
    started = mediator.transition_shared_interview(action="start", narrative=NARRATIVE)
    before = _graph_fingerprint(mediator)
    refused = mediator.transition_shared_interview(
        action="answer",
        answer="A different and stale body that must be ignored.",
        inquiry_id=started["inquiry"]["inquiry_id"],
        expected_question_revision=int(started["expected_question_revision"]) + 4,
    )
    assert refused["status"] == "refused"
    assert refused["error"]["code"] == "stale_question"
    assert refused["error"]["resumable"] is True
    assert _graph_fingerprint(mediator) == before
    assert mediator.workflow_actions.export_session_projection()["session_revision"] == started["session_revision"]


def test_fresh_instance_resume_keeps_answered_state(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    mediator = _mediator(tmp_path)
    started = mediator.transition_shared_interview(action="start", narrative=NARRATIVE)
    mediator.transition_shared_interview(
        action="answer",
        answer=ANSWER,
        inquiry_id=started["inquiry"]["inquiry_id"],
        expected_question_revision=started["expected_question_revision"],
    )
    projection = mediator.workflow_actions.export_session_projection()
    extraction_count = projection["narrative_extraction_count"]
    answered = projection["answered_inquiries"]
    fresh = _mediator(tmp_path / "fresh")
    resumed = fresh.transition_shared_interview(action="resume", session_projection=projection)
    assert resumed["error"] is None
    assert resumed["narrative_extraction_count"] == extraction_count == 1
    restored = fresh.workflow_actions.export_session_projection()
    assert restored["answered_inquiries"] == answered
    assert restored["knowledge_graph"]["entities"].keys() == projection["knowledge_graph"]["entities"].keys()
    assert fresh.phase_manager.iteration_count == mediator.phase_manager.iteration_count
    assert len(fresh.denoiser.questions_asked) == len(mediator.denoiser.questions_asked)


def test_optional_dependency_failure_is_structured_and_resumable(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    mediator = _mediator(tmp_path)

    original_build = mediator.kg_builder.build_from_text

    def broken(_text):
        raise ImportError("optional graph extra")

    monkeypatch.setattr(mediator.kg_builder, "build_from_text", broken)
    failed = mediator.transition_shared_interview(action="start", narrative=NARRATIVE)
    assert failed["status"] == "unavailable"
    assert failed["error"]["code"] == "capability_unavailable"
    assert failed["error"]["resumable"] is True
    assert failed["error"]["error_type"] == "ImportError"
    assert "optional graph extra" not in json.dumps(failed)
    assert mediator.workflow_actions.interview_started is False
    monkeypatch.setattr(mediator.kg_builder, "build_from_text", original_build)
    started = mediator.transition_shared_interview(action="start", narrative=NARRATIVE)
    assert started["status"] == "awaiting_user"
    assert started["narrative_extraction_count"] == 1


def test_local_privacy_refuses_before_backend_call(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    backend, calls = _backend_factory()
    mediator = _mediator(tmp_path, backend=backend)
    with pytest.raises(UserPresentableException) as caught:
        mediator.query_backend("do not send this synthetic prompt")
    assert caught.value.description.startswith("privacy_denied")
    assert calls == []
    serialized = json.dumps(mediator.get_state())
    assert "do not send this synthetic prompt" not in serialized


def test_legacy_finalize_returns_honest_workflow_result(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    mediator = _mediator(tmp_path)
    result = mediator.finalize()
    assert result["status"] == "workflow_result"
    assert result["legal_sufficiency"] is False
    assert result["error"] is None
    assert "not-implemented" not in json.dumps(result).lower()
    rendered = []
    cli = CLI.__new__(CLI)
    cli.mediator = mediator
    cli.print_response = rendered.append
    cli.print_error = rendered.append
    cli.feed(NARRATIVE)
    assert rendered
    assert "awaiting_user" in rendered[-1]
    assert "inq-" in rendered[-1]


def test_workspace_package_and_resume_share_inquiry(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    user_id = "shared-interview-user"
    service = _service(tmp_path, user_id)
    opened = run_intake_chat_turn(user_id, message=NARRATIVE, service=service)
    interview = opened["interview"]
    assert interview["status"] == "awaiting_user"
    assert interview["narrative_extraction_count"] == 1
    assert opened["original_complaint"]["text"] == NARRATIVE
    assert opened["legacy_inquiry"]["question_id"] == "party_name"
    assert opened["inquiry"]["question_id"] == interview["inquiry"]["inquiry_id"]
    inquiry_id = interview["inquiry"]["inquiry_id"]
    revision = interview["expected_question_revision"]
    before_stale = deepcopy(service.get_session(user_id)["session"])
    from integrations.ipfs_datasets import llm
    def no_stale_provider():
        pytest.fail("stale answer entered the native provider loader")
    with monkeypatch.context() as stale_guard:
        stale_guard.setattr(llm, "load_observed_llm_symbols", no_stale_provider)
        stale_guard.setattr(service._interview_mediators[(user_id, user_id)], "request_intake_candidates",
                            lambda *args, **kwargs: pytest.fail("stale answer entered a typed request"))
        stale = service.run_intake_chat_turn(
            user_id,
            message="stale body",
            question_id=inquiry_id,
            expected_question_revision=revision + 3,
        )
    _assert_refused_state_unchanged(before_stale, service.get_session(user_id)["session"])
    assert stale["interview"]["error"]["code"] == "stale_question"
    assert stale["interview"]["session_revision"] == interview["session_revision"]
    answered = run_intake_chat_turn(
        user_id,
        message=ANSWER,
        question_id=inquiry_id,
        expected_question_revision=revision,
        service=service,
    )
    _assert_local_role_failure(answered["interview"])
    assert sum(item.get("answer") == ANSWER for item in answered["session"]["shared_interview"]["denoiser_history"]) == 1
    assert answered["interview"]["session_revision"] == interview["session_revision"] + 1
    fresh = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    fresh.unlock_private_keys(passphrase="synthetic-shared-interview-passphrase")
    resumed = fresh.run_intake_chat_turn(user_id, interview_action="resume")
    assert resumed["interview"]["narrative_extraction_count"] == 1
    assert resumed["interview"]["inquiry"]["inquiry_id"] == answered["interview"]["inquiry"]["inquiry_id"]
    assert resumed["interview"]["expected_question_revision"] == answered["interview"]["expected_question_revision"]
    assert resumed["original_complaint"]["text"] == NARRATIVE
    assert resumed["session"]["shared_interview"]["denoiser_history"] == answered["session"]["shared_interview"]["denoiser_history"]
    _assert_local_role_failure(resumed["interview"])


def test_complaint_cli_import_uses_isolated_session_dir(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    import applications.complaint_workspace as workspace

    isolated = tmp_path / "isolated-sessions"
    monkeypatch.setattr(workspace, "_SESSION_DIR", isolated)
    module_name = "applications.complaint_cli"
    import sys

    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    assert Path(module.service._session_dir) == isolated.resolve()
    assert os.environ.get("HOME", "") != ""


# Independent frozen-candidate regressions use genuine public key/session APIs.
def _independent_service(tmp_path, user="synthetic-user"):
    value = ComplaintWorkspaceService(root_dir=tmp_path/"sessions")
    value.initialize_private_keys(protection="passphrase",passphrase="synthetic-independent-interview")
    value.ensure_private_case_key(user,user)
    return value

def test_actual_package_top_level_question_is_current_graph_question(tmp_path,monkeypatch):
    _block_external(monkeypatch); value=_independent_service(tmp_path)
    opened=run_intake_chat_turn("synthetic-user",message=NARRATIVE,service=value)
    assert opened["interview"]["status"] == "awaiting_user"
    assert opened["inquiry"]["question_id"] == opened["interview"]["inquiry"]["inquiry_id"]

def test_first_answer_after_fresh_unlock_is_applied_not_only_resumed(tmp_path,monkeypatch):
    _block_external(monkeypatch); value=_independent_service(tmp_path)
    opened=run_intake_chat_turn("synthetic-user",message=NARRATIVE,service=value)["interview"]
    fresh=ComplaintWorkspaceService(root_dir=tmp_path/"sessions")
    fresh.unlock_private_keys(passphrase="synthetic-independent-interview")
    answered_payload=run_intake_chat_turn("synthetic-user",message=ANSWER,question_id=opened["inquiry"]["inquiry_id"],expected_question_revision=opened["expected_question_revision"],service=fresh)
    answered=answered_payload["interview"]
    _assert_local_role_failure(answered)
    assert sum(item.get("answer") == ANSWER for item in answered_payload["session"]["shared_interview"]["denoiser_history"]) == 1
    assert answered["session_revision"] == opened["session_revision"] + 1
    assert answered["answered_count"] == 1

def test_stale_explicit_answer_does_not_mutate_legacy_answers_or_history(tmp_path,monkeypatch):
    _block_external(monkeypatch); value=_independent_service(tmp_path)
    opened=run_intake_chat_turn("synthetic-user",message=NARRATIVE,service=value)["interview"]
    before=deepcopy(value.get_session("synthetic-user")["session"])
    from integrations.ipfs_datasets import llm
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: pytest.fail("stale answer entered provider loader"))
    monkeypatch.setattr(value._interview_mediators[("synthetic-user", "synthetic-user")], "request_intake_candidates",
                        lambda *args, **kwargs: pytest.fail("stale answer entered a typed request"))
    response=run_intake_chat_turn("synthetic-user",message="must not persist",question_id="party_name",expected_question_revision=opened["expected_question_revision"]+9,interview_action="answer",service=value)
    assert response["interview"]["status"] == "refused"
    after=value.get_session("synthetic-user")["session"]
    _assert_refused_state_unchanged(before, after)
    assert after["intake_answers"] == before["intake_answers"]
    assert after["intake_history"] == before["intake_history"]
    assert response["accepted_answer"] is None

def test_default_authorized_generation_uses_real_shared_router_seam(tmp_path,monkeypatch):
    _block_external(monkeypatch); value=_independent_service(tmp_path)
    value.set_privacy_policy("synthetic-user","grok")
    from integrations.ipfs_datasets import llm
    calls=[]
    def generated(prompt, **kwargs):
        calls.append(kwargs)
        return {"status":"success","text":'{"entities":[],"relationships":[]}',"privacy_decision":"allowed"}
    monkeypatch.setattr(llm,"generate_text_with_metadata",generated)
    opened=run_intake_chat_turn("synthetic-user",message=NARRATIVE,service=value)
    assert opened["interview"]["status"] == "awaiting_user"
    assert calls, "Production interview must not replace configured inference with an unconditional empty fixture backend"
    assert all(c.get("provider") == "grok_cli" and c.get("model_name") == "grok-4.7" for c in calls)
    assert all(c.get("complaint_privacy_context",{}).get("case_id") == "synthetic-user" for c in calls)

def test_mediator_cache_is_bound_to_owner_and_case(tmp_path,monkeypatch):
    _block_external(monkeypatch); value=_independent_service(tmp_path)
    value.ensure_private_case_key("synthetic-user","case-two")
    first=value._mediator_for_shared_interview("synthetic-user","synthetic-user")
    second=value._mediator_for_shared_interview("synthetic-user","case-two")
    assert first is not second


def test_real_adapter_available_status_is_consumed_and_context_is_preserved(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    value = _independent_service(tmp_path)
    value.set_privacy_policy("synthetic-user", "grok")
    from integrations.ipfs_datasets import llm
    calls = []
    def generated(prompt, **kwargs):
        calls.append(kwargs)
        return {"status": "available", "text": "synthetic adapter output", "privacy_decision": "allowed"}
    monkeypatch.setattr(llm, "generate_text_with_metadata", generated)
    mediator = value._mediator_for_shared_interview("synthetic-user", "synthetic-user")
    mediator.workflow_actions.bind_interview_privacy(
        privacy_policy_for_mode("synthetic-user", "synthetic-user", "grok"),
        user_id="synthetic-user", case_id="synthetic-user",
    )
    assert mediator.query_backend("synthetic prompt") == "synthetic adapter output"
    assert len(calls) == 1
    assert calls[0]["provider"] == "grok_cli" and calls[0]["model_name"] == "grok-4.7"
    assert calls[0]["complaint_privacy_context"]["case_id"] == "synthetic-user"


def test_backend_type_error_is_not_retried_without_bound_context(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    calls = []
    def backend(prompt, **kwargs):
        calls.append(kwargs)
        raise TypeError("synthetic backend failure after invocation")
    mediator = _mediator(tmp_path, backend=backend)
    mediator.workflow_actions.bind_interview_privacy(
        privacy_policy_for_mode("synthetic-user", "synthetic-user", "grok"),
        user_id="synthetic-user", case_id="synthetic-user",
    )
    with pytest.raises(TypeError):
        mediator.query_backend("synthetic prompt")
    assert len(calls) == 1
    assert calls[0]["complaint_privacy_context"]["case_id"] == "synthetic-user"


def test_explicit_docx_request_is_not_silently_removed_when_optional_backend_missing(monkeypatch):
    from unittest.mock import Mock
    _block_external(monkeypatch)
    real_find = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **kw: None if name == "docx" else real_find(name, *a, **kw))
    mediator = Mock()
    mediator.build_formal_complaint_document_package.return_value = {"draft": {}, "artifacts": {}, "errors": {"docx": "unavailable"}}
    cli = CLI.__new__(CLI)
    cli.mediator = mediator
    cli.print_response = Mock()
    cli.print_error = Mock()
    cli.export_complaint(["output_formats=docx,pdf"])
    assert mediator.build_formal_complaint_document_package.call_args.kwargs["output_formats"] == ["docx", "pdf"]
    assert "requested docx" in cli.print_error.call_args.args[0]


@pytest.mark.parametrize("channel", ["mcp", "http"])
def test_stale_revision_reaches_same_transition_from_every_entrypoint(tmp_path, monkeypatch, channel):
    import asyncio
    from applications.complaint_workspace import WorkspaceAccess, workspace_access_scope
    from applications.complaint_workspace_api import create_complaint_workspace_router, IntakeChatTurnRequest
    _block_external(monkeypatch)
    value = _independent_service(tmp_path)
    current = value.run_intake_chat_turn("synthetic-user", message=NARRATIVE)["interview"]
    before = deepcopy(value.get_session("synthetic-user")["session"])
    from integrations.ipfs_datasets import llm
    monkeypatch.setattr(llm, "load_observed_llm_symbols", lambda: pytest.fail("stale answer entered provider loader"))
    monkeypatch.setattr(value._interview_mediators[("synthetic-user", "synthetic-user")], "request_intake_candidates",
                        lambda *args, **kwargs: pytest.fail("stale answer entered a typed request"))
    args = {"user_id": "synthetic-user", "message": ANSWER,
        "question_id": current["inquiry"]["inquiry_id"],
        "expected_question_revision": current["expected_question_revision"] + 1,
        "interview_action": "answer"}
    with workspace_access_scope(WorkspaceAccess.authenticated("synthetic-user", case_id="synthetic-user")):
        if channel == "mcp":
            response = value.call_mcp_tool("complaint.run_intake_chat_turn", args)
        else:
            router = create_complaint_workspace_router(value)
            endpoint = next(route.endpoint for route in router.routes if route.path == "/api/complaint-workspace/intake-chat")
            response = asyncio.run(endpoint(IntakeChatTurnRequest(**args)))
    assert response["interview"]["status"] == "refused"
    assert response["interview"]["error"]["code"] == "stale_question"
    assert response["interview"]["session_revision"] == current["session_revision"]
    after = value.get_session("synthetic-user")["session"]
    _assert_refused_state_unchanged(before, after)
    assert after["shared_interview"]["answered_inquiries"] == []


def test_empty_current_answer_error_precedes_previous_provider_failure(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    value = _independent_service(tmp_path)
    opened = value.run_intake_chat_turn("synthetic-user", message=NARRATIVE)
    current = opened["interview"]
    _assert_local_role_failure(current)
    before = deepcopy(opened["session"])
    monkeypatch.setattr(value._interview_mediators[("synthetic-user", "synthetic-user")], "request_intake_candidates",
                        lambda *args, **kwargs: pytest.fail("empty answer entered a typed request"))
    response = value.run_intake_chat_turn(
        "synthetic-user", interview_action="answer",
        question_id=current["inquiry"]["inquiry_id"],
        expected_question_revision=current["expected_question_revision"],
    )
    assert response["interview"]["error"]["code"] == "answer_required"
    assert response["interview"]["status"] == "awaiting_user"
    assert response["interview"]["error"]["resumable"] is True
    _assert_refused_state_unchanged(before, response["session"])
    assert response["accepted_answer"] is None
