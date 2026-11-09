"""Public intake context and legal-storage faults with owned synthetic users.

Every turn uses the shared service's emitted inquiry and revision. No test
seeds graph classifications, legal satisfaction, or a substitute backend.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService
from complaint_phases.phase_manager import ComplaintPhase
from tests.private_session_assertions import assert_private_session_frame, private_session_path
from tests.test_tui_interview_acceptance import (
    PASSPHRASE,
    _block_network_and_provider_subprocesses,
    _entities,
    _nodes,
    _provenance_spans_match_narrative,
    _service,
    _support_endpoints_resolve,
)

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

NARRATIVE = (
    "On March 4, 2024 supervisor Alex Rivera at Northwind Tools "
    "discriminated against me at work."
)


@pytest.fixture(autouse=True)
def _offline_only(monkeypatch, _block_network_and_provider_subprocesses):
    """Keep the existing class-preserving socket/provider guard unconditional."""
    monkeypatch.delenv("COMPLAINT_TUI_LIVE_SYNTHETIC_CANARY", raising=False)


def _shared(payload: dict) -> dict:
    return payload["session"]["shared_interview"]


def _assert_unresolved(payload: dict) -> None:
    policy = payload["stopping_policy"]
    assert payload["interview"]["legal_sufficiency"] is False
    assert policy["legal_sufficiency"] is False
    assert policy["filing_ready"] is False
    assert policy["proof_requirements_satisfied"] is False
    assert policy["outcome"] != "complete"
    assert policy["resumable_next_action"]["resumable"] is True


def _assert_encrypted(service: ComplaintWorkspaceService, user_id: str, narrative: str) -> None:
    directory = Path(service._session_dir)
    assert_private_session_frame(private_session_path(directory, user_id).read_bytes(), narrative)
    for path in directory.rglob("*"):
        if path.is_file():
            assert narrative.encode("utf-8") not in path.read_bytes(), path.relative_to(directory)


def _cold_resume(service: ComplaintWorkspaceService, user_id: str, before: dict) -> dict:
    fresh = ComplaintWorkspaceService(root_dir=service._session_dir)
    unlocked = fresh.unlock_private_keys(passphrase=PASSPHRASE)
    assert unlocked.get("code") != "authentication_failed"
    resumed = fresh.run_intake_chat_turn(user_id, interview_action="resume")
    prior, restored = _shared(before), _shared(resumed)
    for field in (
        "knowledge_graph", "dependency_graph", "intake_case_file", "current_questions",
        "pending_inquiry", "denoiser_history", "answered_inquiries", "unknown_reasons",
        "session_revision", "question_revision", "narrative_extraction_count",
    ):
        assert restored[field] == prior[field], field
    assert resumed["interview"]["inquiry"] == before["interview"]["inquiry"]
    assert resumed["original_complaint"]["text"] == before["original_complaint"]["text"]
    _assert_unresolved(resumed)
    _assert_encrypted(fresh, user_id, before["original_complaint"]["text"])
    return resumed


def test_public_pending_legal_context_answers_survive_encrypted_cold_resume(tmp_path: Path):
    user_id = "synthetic-public-context"
    service = _service(tmp_path, user_id)
    payload = service.run_intake_chat_turn(user_id, message=NARRATIVE)
    assert payload["session"]["privacy_policy"]["cloud_processing_enabled"] is False
    initial = _shared(payload)
    assert initial["intake_case_file"]["legal_context"]["jurisdiction"] == "unknown"
    assert not initial["intake_case_file"]["legal_context"]["applicable_law_date"].get("precise_date")
    original_entity_ids = {entity["id"] for entity in _entities(initial["knowledge_graph"])}
    assert original_entity_ids
    _provenance_spans_match_narrative(initial["knowledge_graph"], NARRATIVE)
    _support_endpoints_resolve(initial["knowledge_graph"])

    answers = {
        "jurisdiction": "OR",
        "event_date": "2024-03-04",
        "applicable_law_date": "2024-06-01",
        "filing_reference_date": "2024-07-01",
        "claim_candidates": "employment_discrimination",
    }
    answered_context: set[str] = set()
    accepted_targets: set[tuple[str, int]] = set()
    for _ in range(12):
        if {"jurisdiction", "applicable_law_date"} <= answered_context:
            break
        projection = _shared(payload)
        question = projection["current_questions"][0]
        inquiry = payload["interview"]["inquiry"]
        revision = payload["interview"]["expected_question_revision"]
        target = (inquiry["inquiry_id"], revision)
        assert target not in accepted_targets, "a submitted inquiry did not advance"
        accepted_targets.add(target)
        if question.get("type") == "legal_context":
            field = question["field"]
            assert field in answers, f"unexpected legal-context field: {field}"
            answer = answers[field]
        else:
            field = None
            answer = "I don't know"
        payload = service.run_intake_chat_turn(
            user_id,
            message=answer,
            question_id=inquiry["inquiry_id"],
            expected_question_revision=revision,
        )
        assert payload["interview"]["status"] != "refused"
        if field is not None:
            answered_context.add(field)
        _assert_unresolved(payload)
        assert {entity["id"] for entity in _entities(_shared(payload)["knowledge_graph"])} == original_entity_ids

    assert {"jurisdiction", "applicable_law_date"} <= answered_context
    projection = _shared(payload)
    context = projection["intake_case_file"]["legal_context"]
    assert context["jurisdiction"] == "OR"
    assert context["applicable_law_date"]["precise_date"] == "2024-06-01"
    assert projection["narrative_extraction_count"] == 1
    context_history = [
        item for item in projection["denoiser_history"]
        if item.get("question", {}).get("type") == "legal_context"
    ]
    assert context_history
    assert all(item["creates_fact"] is False and item["satisfies_requirement"] is False for item in context_history)
    requirements = [node for node in _nodes(projection["dependency_graph"]) if node["node_type"] == "requirement"]
    assert requirements and all(node["satisfied"] is False for node in requirements)
    _assert_encrypted(service, user_id, NARRATIVE)
    _cold_resume(service, user_id, payload)


def test_public_legal_storage_outage_preserves_nonempty_unresolved_graph(tmp_path: Path, monkeypatch):
    user_id = "synthetic-public-source-outage"
    service = _service(tmp_path, user_id)
    mediator = service._mediator_for_shared_interview(user_id, user_id)
    lookups: list[tuple[str, str]] = []
    failure_marker = "SYNTHETIC_PRIVATE_LEGAL_STORAGE_FAILURE"

    def unavailable(owner_id: str, claim_type: str):
        lookups.append((owner_id, claim_type))
        raise ConnectionError(failure_marker)

    # Only the storage read fails; source admission, graph construction,
    # question selection, service persistence, and restoration stay real.
    monkeypatch.setattr(mediator.legal_authority_storage, "get_authorities_by_claim", unavailable)
    narrative = NARRATIVE + " Under Oregon law. Applicable law date: 2024-06-01."
    payload = service.run_intake_chat_turn(user_id, message=narrative)
    assert payload["session"]["privacy_policy"]["cloud_processing_enabled"] is False
    assert lookups and all(owner_id == user_id and claim_type for owner_id, claim_type in lookups)
    assert mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "legal_source_status") == "unavailable"
    projection = _shared(payload)
    context = projection["intake_case_file"]["legal_context"]
    assert context["jurisdiction"] == "OR"
    assert context["applicable_law_date"]["precise_date"] == "2024-06-01"
    assert _entities(projection["knowledge_graph"])
    _provenance_spans_match_narrative(projection["knowledge_graph"], narrative)
    _support_endpoints_resolve(projection["knowledge_graph"])
    nodes = _nodes(projection["dependency_graph"])
    gaps = [node for node in nodes if node.get("attributes", {}).get("dependency_class") == "legal_source_gap"]
    assert gaps and all(node["satisfied"] is False for node in gaps)
    assert all(node.get("attributes", {}).get("source_available") is not True for node in gaps)
    assert not [node for node in nodes if node.get("attributes", {}).get("dependency_class") == "legally_sourced_requirement"]
    assert projection["pending_inquiry"]["inquiry_id"] == payload["interview"]["inquiry"]["inquiry_id"]
    assert failure_marker not in str(payload)
    _assert_unresolved(payload)
    _assert_encrypted(service, user_id, narrative)
    _cold_resume(service, user_id, payload)
