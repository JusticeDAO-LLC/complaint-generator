"""Explained questions are selected from actionable graph gaps."""

import pytest

from applications.complaint_workspace import (
    ComplaintWorkspaceRequestHandlers,
    format_terminal_why,
    publish_explained_inquiry,
)
from complaint_phases.denoiser import ComplaintDenoiser
from complaint_phases.dependency_graph import Dependency, DependencyGraph, DependencyNode, DependencyType, NodeType
from complaint_phases.knowledge_graph import Entity, KnowledgeGraph
from complaint_phases.phase_manager import ComplaintPhase, PhaseManager


def _graphs():
    knowledge = KnowledgeGraph()
    knowledge.add_entity(Entity(id="person-pat", type="person", name="Pat Lee", confidence=0.2))
    knowledge.add_entity(Entity(id="claim-firing", type="claim", name="The firing lacked notice", confidence=0.4))

    dependency = DependencyGraph()
    dependency.add_node(DependencyNode(
        id="claim-employment",
        node_type=NodeType.CLAIM,
        name="Employment discrimination claim",
        satisfied=False,
    ))
    dependency.add_node(DependencyNode(
        id="element-notice",
        node_type=NodeType.LEGAL_ELEMENT,
        name="Notice of the action",
        description="The employer gave notice of the adverse action.",
        satisfied=False,
    ))
    dependency.add_node(DependencyNode(
        id="fact-fired-march",
        node_type=NodeType.FACT,
        name="Fired on March 3",
        satisfied=True,
    ))
    dependency.add_node(DependencyNode(
        id="fact-fired-april",
        node_type=NodeType.FACT,
        name="Fired on April 9",
        satisfied=True,
    ))
    dependency.add_dependency(Dependency(
        id="needs-notice",
        source_id="element-notice",
        target_id="claim-employment",
        dependency_type=DependencyType.REQUIRES,
    ))
    dependency.add_dependency(Dependency(
        id="dates-conflict",
        source_id="fact-fired-march",
        target_id="fact-fired-april",
        dependency_type=DependencyType.CONTRADICTS,
        required=False,
    ))
    case_file = {
        "candidate_claims": [
            {
                "claim_type": "employment_discrimination",
                "label": "Employment discrimination",
                "required_elements": [
                    {
                        "element_id": "adverse_action",
                        "label": "Adverse action",
                        "status": "missing",
                        "blocking": True,
                    }
                ],
            }
        ],
        "proof_leads": [],
    }
    return knowledge, dependency, case_file


def _select():
    denoiser = ComplaintDenoiser()
    knowledge, dependency, case_file = _graphs()
    inquiries = denoiser.select_explained_gap_inquiries(
        knowledge,
        dependency,
        intake_case_file=case_file,
        max_questions=8,
    )
    return denoiser, knowledge, dependency, case_file, inquiries


def test_selection_uses_gap_families_and_stable_contracts():
    denoiser, _, _, _, inquiries = _select()
    assert inquiries
    families = {item["gap_family"] for item in inquiries}
    assert families == {"factual_uncertainty", "legal_element_support", "contradiction", "evidence"}
    again = denoiser.select_explained_gap_inquiries(
        *_graphs()[:2],
        intake_case_file=_graphs()[2],
        max_questions=8,
    )
    first_by_target = {item["target_id"]: item for item in inquiries}
    second_by_target = {item["target_id"]: item for item in again}
    shared = set(first_by_target) & set(second_by_target)
    assert shared
    for target_id in shared:
        assert first_by_target[target_id]["objective_id"] == second_by_target[target_id]["objective_id"]
        assert first_by_target[target_id]["inquiry_id"] == second_by_target[target_id]["inquiry_id"]
    for inquiry in inquiries:
        assert inquiry["objective_id"].startswith("obj-")
        assert inquiry["target_id"]
        assert inquiry["why_it_matters"]
        assert "legal" not in inquiry["why_it_matters"].lower() or "element" in inquiry["why_it_matters"].lower() or inquiry["gap_family"] != "factual_uncertainty"
        contract = inquiry["expected_answer_contract"]
        update = inquiry["expected_update_contract"]
        assert contract["objective_id"] == inquiry["objective_id"]
        assert contract["target_id"] == inquiry["target_id"]
        assert contract["non_answer_effect"] == "record_disposition_without_satisfying_legal_requirement"
        assert update["satisfies_legal_requirement_on_non_answer"] is False
        assert update["on_answer"] == "update_or_remove_candidate"
        assert inquiry["candidate"]["candidate_source"]


def test_answering_one_issue_changes_the_next_question():
    denoiser, knowledge, dependency, case_file, inquiries = _select()
    current = inquiries[0]
    result = denoiser.apply_explained_inquiry_answer(
        "The notice was a letter dated March 3, 2024 from Grace Hopper.",
        knowledge,
        dependency,
        intake_case_file=case_file,
        inquiry=current,
    )
    assert result["removed_target_id"] == current["target_id"]
    assert result["recorded_as"] == "answered"
    assert result["next_inquiry"] is None or result["next_inquiry"]["target_id"] != current["target_id"]
    assert all(item["target_id"] != current["target_id"] for item in result["inquiries"])


@pytest.mark.parametrize("answer", ["I don't know", "I refuse", "skip"])
def test_non_answers_are_recorded_without_satisfying_the_legal_element(answer):
    denoiser, knowledge, dependency, case_file, inquiries = _select()
    requirement = next(item for item in inquiries if item["gap_family"] == "legal_element_support")
    notice = dependency.get_node("element-notice")
    assert notice.satisfied is False
    result = denoiser.apply_explained_inquiry_answer(
        answer,
        knowledge,
        dependency,
        intake_case_file=case_file,
        inquiry=requirement,
    )
    assert result["recorded_as"] in {"unknown", "refused", "skipped"}
    assert result["satisfies_requirement"] is False
    assert result["updates"]["requirements_satisfied"] == 0
    assert dependency.get_node("element-notice").satisfied is False
    assert denoiser.is_question_target_closed(requirement["target_id"], requirement["target_revision"])
    assert result["next_inquiry"] is None or result["next_inquiry"]["target_id"] != requirement["target_id"]
    recorded = denoiser.question_disposition_records[-1]
    assert recorded["disposition"] == result["recorded_as"]
    assert recorded["satisfies_requirement"] is False


def test_semantic_duplicate_objectives_stop_after_the_repeat_limit():
    denoiser, _, _, _, inquiries = _select()
    seed = dict(inquiries[0])
    clones = []
    for index in range(3):
        item = dict(seed)
        item["inquiry_id"] = f"{seed['inquiry_id']}-clone-{index}"
        item["question"] = seed["question"]
        clones.append(item)
    kept, suppressed = ComplaintDenoiser().apply_semantic_duplicate_repeat_policy(clones)
    assert len(kept) == ComplaintDenoiser.SEMANTIC_DUPLICATE_REPEAT_LIMIT
    assert len(suppressed) == 1
    assert suppressed[0]["suppressed_reason"] == "semantic_duplicate_repeat_limit"

    denoiser.objective_repeat_counts[seed["objective_id"]] = ComplaintDenoiser.SEMANTIC_DUPLICATE_REPEAT_LIMIT
    denoiser.semantic_repeat_counts[seed["semantic_key"]] = ComplaintDenoiser.SEMANTIC_DUPLICATE_REPEAT_LIMIT
    denoiser.presented_question_records.append({
        "objective_id": seed["objective_id"],
        "semantic_key": seed["semantic_key"],
        "question": seed["question"],
        "repeat_count": ComplaintDenoiser.SEMANTIC_DUPLICATE_REPEAT_LIMIT,
    })
    kept_again, suppressed_again = denoiser.apply_semantic_duplicate_repeat_policy([seed])
    assert kept_again == []
    assert suppressed_again[0]["objective_id"] == seed["objective_id"]


def test_phase_manager_why_is_understandable_and_workspace_does_not_store_it():
    denoiser = ComplaintDenoiser()
    knowledge, dependency, case_file = _graphs()
    manager = PhaseManager()
    manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", knowledge)
    manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", dependency)
    manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", case_file)
    selection = manager.select_explained_gap_questions(denoiser)
    why = manager.explain_current_inquiry()
    assert why["command"] == "/why"
    assert "Why this question:" in why["display"]
    assert selection["current"]["objective_id"] in why["display"]
    assert selection["current"]["target_id"] in why["display"]
    assert "does not satisfy the underlying legal requirement" in why["display"]
    assert "actor_critic" not in why["display"]

    state = {"user_id": "user-1", "intake_answers": {}, "intake_history": []}
    publish_explained_inquiry(state, selection)
    rendered = format_terminal_why(state=state)
    assert rendered["display"] == why["display"]
    assert rendered["stored_as_answer"] is False

    class _Workspace:
        def _load_state(self, user_id):
            return state

        def _build_intake_chat_payload(self, loaded, **kwargs):
            return {"message": "pending question", "session_user": loaded.get("user_id")}

        def _save_state(self, loaded):
            raise AssertionError("/why must not be stored as an answer")

    payload = ComplaintWorkspaceRequestHandlers(_Workspace()).run_intake_chat_turn("user-1", message="/why")
    assert payload["stored_as_answer"] is False
    assert payload["awaiting_user"] is True
    assert payload["command"] == "/why"
    assert state["intake_answers"] == {}
    assert state["intake_history"] == []
    assert "Why this question:" in payload["message"]

    answered = manager.apply_explained_inquiry_answer("skip", denoiser)
    assert answered["recorded_as"] == "skipped"
    assert answered["satisfies_requirement"] is False
    assert manager.get_phase_data(ComplaintPhase.INTAKE, "explained_answer_records")[-1]["recorded_as"] == "skipped"
    current = manager.get_phase_data(ComplaintPhase.INTAKE, "current_explained_inquiry")
    assert current is None or current["target_id"] != selection["current"]["target_id"]
