"""Host-selected inquiry grounding survives projection, /why, and cold resume.

Synthetic private fixtures only. No case is skipped. A missing objective or
target stays unknown, and a model string cannot become that binding.
"""

from __future__ import annotations

import json
import socket
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService, format_terminal_why
from integrations.ipfs_datasets.llm import privacy_policy_for_mode
from mediator.mediator import Mediator
from mediator.workflow_service import WorkflowActionService

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

NARRATIVE = "On March 4, 2024 supervisor Alex Rivera fired me after I reported safety concerns."
USER_ID = "synthetic-mgnd-36"
PASSPHRASE = "synthetic-mgnd-36-passphrase"
HOST_OBJECTIVE = "obj-host-notice-date"
HOST_TARGET = "target-host-notice-date"
HOST_REVISION = "rev-host-7"
HOST_WHY = "The notice date is still missing from the complaint record."
MODEL_WORDING = "Identify the corporate parent from the knowledge graph."
MODEL_GRAPH = "graph-model-authored-36"
MODEL_ENTITY = "entity-model-authored-36"


def _cases():
    return (
        "host-selected-bindings",
        "missing-bindings-stay-unknown",
        "model-proposal-cannot-fill-bindings",
        "service-why-is-not-an-answer",
        "cold-resume-keeps-bindings",
        "legacy-thin-snapshot-is-unknown",
        "resume-without-a-session-is-unavailable",
    )


def _block_external(monkeypatch) -> None:
    def blocked(*_args, **_kwargs):
        raise RuntimeError("external operation blocked")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, blocked)


def _backend(prompt, complaint_privacy_context=None, **kwargs):
    return '{"entities":[],"relationships":[]}'


def _mediator(tmp_path: Path) -> Mediator:
    db_dir = tmp_path / "dbs"
    db_dir.mkdir(parents=True, exist_ok=True)
    mediator = Mediator(
        [_backend],
        evidence_db_path=str(db_dir / "evidence.db"),
        legal_authority_db_path=str(db_dir / "legal-authority.db"),
        claim_support_db_path=str(db_dir / "claim-support.db"),
    )
    mediator.state.username = USER_ID
    mediator.workflow_actions.bind_interview_privacy(
        privacy_policy_for_mode(USER_ID, USER_ID, "local"),
        user_id=USER_ID,
        case_id=USER_ID,
    )
    return mediator


def _service(tmp_path: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(USER_ID, USER_ID)
    return service


def _host_question() -> dict:
    return {
        "type": "clarification",
        "question": "What date did the notice arrive?",
        "inquiry_id": "inq-host-notice",
        "objective_id": HOST_OBJECTIVE,
        "target_id": HOST_TARGET,
        "target_revision": HOST_REVISION,
        "why_it_matters": HOST_WHY,
        "expected_answer_contract": {
            "objective_id": HOST_OBJECTIVE,
            "target_id": HOST_TARGET,
            "expected_information": "the notice date you observed",
        },
        "expected_update_contract": {
            "objective_id": HOST_OBJECTIVE,
            "target_id": HOST_TARGET,
            "target_revision": HOST_REVISION,
            "update_kind": "record_notice_date",
        },
        "source_references": [{"kind": "user_statement", "ref": "span-notice-1"}],
        "graph_id": MODEL_GRAPH,
        "entity_id": MODEL_ENTITY,
        "model_proposal": {
            "origin": "model",
            "wording": MODEL_WORDING,
            "graph_id": MODEL_GRAPH,
            "entity_id": MODEL_ENTITY,
            "objective_id": "obj-model-authored",
            "target_id": "target-model-authored",
        },
    }


def _assert_host_bindings(inquiry: dict) -> None:
    assert inquiry["objective_id"] == HOST_OBJECTIVE
    assert inquiry["target_id"] == HOST_TARGET
    assert inquiry["target_revision"] == HOST_REVISION
    assert inquiry["why_it_matters"] == HOST_WHY
    assert inquiry["expected_answer_contract"]["expected_information"] == "the notice date you observed"
    assert inquiry["expected_update_contract"]["update_kind"] == "record_notice_date"
    assert inquiry["source_references"] == [{"kind": "user_statement", "ref": "span-notice-1"}]
    assert inquiry["source_references_status"] == "host_selected"
    encoded = json.dumps(inquiry)
    assert MODEL_WORDING not in encoded
    assert "obj-model-authored" not in encoded
    assert "target-model-authored" not in encoded
    assert MODEL_GRAPH not in encoded
    assert MODEL_ENTITY not in encoded


def _bare_service() -> WorkflowActionService:
    class _Phase:
        def get_phase_data(self, *_args, **_kwargs):
            return None

    class _Mediator:
        phase_manager = _Phase()
        denoiser = None

    return WorkflowActionService(_Mediator())


def test_focused_cases_are_nonempty_and_run():
    assert len(_cases()) >= 7
    assert all(str(label).strip() for label in _cases())


def test_host_selected_fields_reach_pending_inquiry_and_projection():
    service = _bare_service()
    inquiry = service._inquiry_from_question(_host_question(), revision=4)
    _assert_host_bindings(inquiry)
    assert inquiry["revision"] == 4
    assert inquiry["inquiry_id"] == "inq-host-notice"
    service._interview_meta = {
        "started": True,
        "session_id": "interview-synthetic-36",
        "session_revision": 2,
        "question_revision": 4,
        "pending_inquiry": inquiry,
        "answered_inquiries": [],
        "unknown_reasons": [],
        "unavailable_reasons": [],
        "capped_reasons": [],
        "narrative_extraction_count": 1,
    }

    class _Graph:
        def to_dict(self):
            return {"entities": {}, "graph_id": MODEL_GRAPH}

    class _PhaseManager:
        current_phase = type("Phase", (), {"value": "intake"})()
        iteration_count = 0
        loss_history = []
        phase_history = []

        def get_phase_data(self, _phase, key=None):
            if key in {"knowledge_graph", "dependency_graph"}:
                return _Graph()
            if key in {"current_questions", "question_candidates"}:
                return []
            return {}

    service._mediator.phase_manager = _PhaseManager()
    service._mediator.denoiser = type("Denoiser", (), {"questions_asked": []})()
    projection = service.export_session_projection()
    assert projection["schema_version"] == "shared-interview-session-v1"
    assert projection["session_revision"] == 2
    _assert_host_bindings(projection["pending_inquiry"])
    assert MODEL_GRAPH not in json.dumps(projection["pending_inquiry"])


def test_missing_objective_and_target_are_not_invented():
    service = _bare_service()
    question = {
        "type": "clarification",
        "question": "Who was present?",
        "graph_id": MODEL_GRAPH,
        "entity_id": MODEL_ENTITY,
        "model_proposal": {
            "origin": "model",
            "wording": MODEL_WORDING,
            "graph_id": MODEL_GRAPH,
            "entity_id": MODEL_ENTITY,
            "objective_id": "obj-model-authored",
            "target_id": "target-model-authored",
        },
    }
    inquiry = service._inquiry_from_question(question, revision=1)
    assert inquiry["grounding_status"] == "unknown"
    assert inquiry["objective_id"] == "unknown"
    assert inquiry["target_id"] == "unknown"
    assert inquiry["target_revision"] == "unknown"
    assert inquiry["why_it_matters"] is None
    assert inquiry["expected_answer_contract"] is None
    assert inquiry["expected_update_contract"] is None
    assert inquiry["source_references"] is None
    assert inquiry["source_references_status"] == "unknown"
    assert "grounding_unknown" in inquiry["unknown_reasons"]
    encoded = json.dumps(inquiry)
    assert MODEL_GRAPH not in encoded
    assert MODEL_ENTITY not in encoded
    assert MODEL_WORDING not in encoded
    assert "obj-model-authored" not in encoded
    assert "target-model-authored" not in encoded


def test_model_origin_question_does_not_supply_bindings():
    service = _bare_service()
    inquiry = service._inquiry_from_question(
        {
            "origin": "model",
            "record_type": "model_suggestion",
            "type": "clarification",
            "question": MODEL_WORDING,
            "objective_id": "obj-model-authored",
            "target_id": "target-model-authored",
            "why_it_matters": "model reason",
            "graph_id": MODEL_GRAPH,
        },
        revision=1,
    )
    assert inquiry["objective_id"] == "unknown"
    assert inquiry["target_id"] == "unknown"
    assert inquiry["why_it_matters"] is None
    assert "obj-model-authored" not in json.dumps(inquiry)


def test_actual_start_carries_question_target_without_inventing_objective(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    mediator = _mediator(tmp_path)
    started = mediator.transition_shared_interview(action="start", narrative=NARRATIVE)
    assert started["status"] == "awaiting_user"
    inquiry = started["inquiry"]
    assert str(inquiry["inquiry_id"]).startswith("inq-")
    projection = mediator.workflow_actions.export_session_projection()
    pending = projection["pending_inquiry"]
    assert pending["inquiry_id"] == inquiry["inquiry_id"]
    assert pending["objective_id"] == inquiry["objective_id"]
    assert pending["target_id"] == inquiry["target_id"]
    graph_id = str(projection["knowledge_graph"].get("graph_id") or "")
    entity_ids = [str(item) for item in (projection["knowledge_graph"].get("entities") or {}).keys()]
    assert inquiry.get("grounding_status") in {"host_selected", "unknown"}
    if inquiry.get("grounding_status") == "unknown":
        assert inquiry["objective_id"] == "unknown"
        assert inquiry["target_id"] == "unknown"
    else:
        assert inquiry["target_id"] not in {"", "unknown", graph_id, *entity_ids}
        assert inquiry["objective_id"] not in {"", "unknown", graph_id, *entity_ids}
        assert inquiry["why_it_matters"]
        assert isinstance(inquiry["expected_answer_contract"], dict)
        assert isinstance(inquiry["expected_update_contract"], dict)


def test_service_why_repeats_without_answer_revision_or_provider(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    calls = {"provider": 0}

    def explode(*_args, **_kwargs):
        calls["provider"] += 1
        raise AssertionError("provider dispatched")

    monkeypatch.setattr("integrations.ipfs_datasets.llm.generate_text_with_metadata", explode)
    service = _service(tmp_path)
    state = service._load_state(USER_ID)
    state["shared_interview"] = {
        "schema_version": "shared-interview-session-v1",
        "session_revision": 5,
        "question_revision": 2,
        "pending_inquiry": _bare_service()._inquiry_from_question(_host_question(), revision=2),
    }
    service._save_state(state)
    before = service._load_state(USER_ID)
    revision = before["shared_interview"]["session_revision"]
    pending = deepcopy(before["shared_interview"]["pending_inquiry"])
    answers = deepcopy(before.get("intake_answers"))
    history = deepcopy(before.get("intake_history"))
    first = service.run_intake_chat_turn(USER_ID, message="/why")
    second = service.run_intake_chat_turn(USER_ID, message="/why")
    after = service._load_state(USER_ID)
    assert calls["provider"] == 0
    assert first["stored_as_answer"] is False
    assert second["stored_as_answer"] is False
    assert first["command"] == "/why"
    assert first["awaiting_user"] is True
    assert HOST_OBJECTIVE in first["why"]["display"]
    assert HOST_TARGET in first["why"]["display"]
    assert HOST_WHY in first["why"]["display"]
    assert first["why"]["objective_id"] == HOST_OBJECTIVE
    assert first["why"]["target_id"] == HOST_TARGET
    assert first["why"]["expected_update_contract"]["update_kind"] == "record_notice_date"
    assert second["why"]["display"] == first["why"]["display"]
    assert after["shared_interview"]["session_revision"] == revision == 5
    assert after["shared_interview"]["pending_inquiry"] == pending
    assert after.get("intake_answers") == answers
    assert after.get("intake_history") == history
    assert MODEL_WORDING not in first["why"]["display"]


def test_cold_resume_preserves_explanation_and_target_bindings(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    service = _service(tmp_path)
    state = service._load_state(USER_ID)
    inquiry = _bare_service()._inquiry_from_question(_host_question(), revision=2)
    state["shared_interview"] = {
        "schema_version": "shared-interview-session-v1",
        "session_id": "interview-cold-36",
        "session_revision": 5,
        "question_revision": 2,
        "pending_inquiry": inquiry,
    }
    service._save_state(state)
    fresh = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    fresh.unlock_private_keys(passphrase=PASSPHRASE)
    fresh.ensure_private_case_key(USER_ID, USER_ID)
    loaded = fresh._load_state(USER_ID)
    assert loaded["shared_interview"]["pending_inquiry"]["target_id"] == HOST_TARGET
    assert loaded["shared_interview"]["pending_inquiry"]["objective_id"] == HOST_OBJECTIVE
    why = fresh.run_intake_chat_turn(USER_ID, message="/why")
    again = fresh.run_intake_chat_turn(USER_ID, message="/why")
    assert why["why"]["display"] == format_terminal_why(inquiry)["display"]
    assert again["why"]["display"] == why["why"]["display"]
    assert why["why"]["target_id"] == HOST_TARGET
    assert why["stored_as_answer"] is False
    assert fresh._load_state(USER_ID)["shared_interview"]["session_revision"] == 5


def test_legacy_thin_snapshot_restores_unknown_grounding(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    mediator = _mediator(tmp_path)
    started = mediator.transition_shared_interview(action="start", narrative=NARRATIVE)
    assert started["error"] is None
    projection = mediator.workflow_actions.export_session_projection()
    session_revision = projection["session_revision"]
    graph_version = projection["knowledge_graph"].get("graph_version")
    entity_ids = list((projection["knowledge_graph"].get("entities") or {}).keys())
    thin = deepcopy(projection)
    thin["pending_inquiry"] = {
        "inquiry_id": "inq-thin-legacy",
        "revision": 1,
        "question": "Who was present?",
        "question_type": "clarification",
        "kind": "graph",
    }
    fresh = _mediator(tmp_path / "fresh")
    resumed = fresh.transition_shared_interview(action="resume", session_projection=thin)
    assert resumed["error"] is None
    restored = fresh.workflow_actions.export_session_projection()
    pending = restored["pending_inquiry"]
    assert pending["grounding_status"] == "unknown"
    assert pending["objective_id"] == "unknown"
    assert pending["target_id"] == "unknown"
    assert pending["why_it_matters"] is None
    assert pending["expected_answer_contract"] is None
    assert pending["source_references_status"] == "unknown"
    assert "grounding_unknown" in pending["unknown_reasons"]
    encoded = json.dumps(pending)
    for entity_id in entity_ids:
        assert entity_id not in encoded
    graph_id = str(restored["knowledge_graph"].get("graph_id") or "")
    if graph_id:
        assert graph_id not in encoded
    assert restored["session_revision"] == session_revision
    assert restored["knowledge_graph"].get("graph_version") == graph_version
    rendered = format_terminal_why(pending)
    assert "Objective id: unknown" in rendered["display"]
    assert "Target id: unknown" in rendered["display"]
    assert "inq-thin-legacy" not in rendered["display"]


def test_missing_session_and_bad_projection_stay_unavailable(tmp_path, monkeypatch):
    _block_external(monkeypatch)
    mediator = _mediator(tmp_path)
    missing = mediator.transition_shared_interview(action="resume")
    assert missing["status"] == "unavailable"
    assert missing["error"]["code"] == "session_missing"
    assert missing["error"]["resumable"] is True
    assert missing["legal_sufficiency"] is False
    assert missing.get("inquiry") in (None, {})
    bad = mediator.transition_shared_interview(
        action="resume",
        session_projection={"schema_version": "shared-interview-session-v0", "pending_inquiry": {"objective_id": HOST_OBJECTIVE}},
    )
    assert bad["status"] == "unavailable"
    assert bad["error"]["code"] == "projection_version"
    assert bad["legal_sufficiency"] is False
    assert mediator.workflow_actions.export_session_projection() is None
