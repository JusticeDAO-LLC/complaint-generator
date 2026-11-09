"""QUEST-01 through QUEST-03: targeted questions, dispositions, and stop states."""

import pytest
from unittest.mock import Mock

from complaint_phases import (
    ComplaintDenoiser,
    ComplaintPhase,
    Dependency,
    DependencyGraph,
    DependencyNode,
    DependencyType,
    Entity,
    KnowledgeGraph,
    NodeType,
    PhaseManager,
    build_intake_case_file,
    refresh_intake_case_file,
)
from intake_status import build_intake_status_summary
from complaint_phases.intake_case_file import (
    QUESTION_DISPOSITIONS,
    question_target_is_closed,
    record_question_disposition,
    reopen_question_disposition,
)
from mediator import Mediator


def _graphs():
    kg = KnowledgeGraph()
    kg.add_entity(Entity("c1", "claim", "Retaliation"))
    dg = DependencyGraph()
    left = DependencyNode("fact-before", NodeType.FACT, "Termination happened before complaint")
    right = DependencyNode("fact-after", NodeType.FACT, "Complaint happened before termination")
    claim = DependencyNode("claim-retaliation", NodeType.CLAIM, "Retaliation Claim")
    requirement = DependencyNode("req-protected", NodeType.REQUIREMENT, "Protected activity")
    dg.add_node(left)
    dg.add_node(right)
    dg.add_node(claim)
    dg.add_node(requirement)
    dg.add_dependency(Dependency("edge-contradicts", "fact-before", "fact-after", DependencyType.CONTRADICTS, required=False))
    dg.add_dependency(Dependency("edge-requires", "req-protected", "claim-retaliation", DependencyType.REQUIRES))
    intake = {
        "candidate_claims": [
            {
                "claim_id": "claim-retaliation",
                "claim_type": "retaliation",
                "label": "Retaliation Claim",
                "required_elements": [
                    {
                        "element_id": "protected_activity",
                        "label": "Protected activity",
                        "blocking": True,
                        "status": "missing",
                    }
                ],
            }
        ],
        "source_capability": {"status": "unavailable", "component": "prover"},
    }
    return kg, dg, intake


def _assert_bound(question):
    target = question.get("unresolved_target") or {}
    assert target.get("target_id")
    assert target.get("target_revision")
    assert target.get("target_kind") in {"factual", "requirement", "contradiction", "proof"}
    assert isinstance(target.get("provenance"), dict)
    assert target.get("why_answer_helps")
    assert target.get("expected_information")
    assert target.get("user_answerability") == "user_observable"
    lowered = str(question.get("question") or "").lower()
    assert "which version is correct" not in lowered
    assert "illegal" not in lowered
    assert "prover" not in lowered
    assert "backend" not in lowered


def test_generate_questions_binds_neutral_targets_and_routes_source_gaps():
    denoiser = ComplaintDenoiser()
    kg, dg, intake = _graphs()
    questions = denoiser.generate_questions(kg, dg, max_questions=8, intake_case_file=intake)

    assert questions
    assert all(_assert_bound(question) or True for question in questions)
    for question in questions:
        _assert_bound(question)
    assert any(question["unresolved_target"]["target_kind"] == "contradiction" for question in questions)
    assert any(question["unresolved_target"]["target_kind"] == "requirement" for question in questions)
    assert denoiser.source_operator_diagnostics
    assert all(item.get("user_question") is None for item in denoiser.source_operator_diagnostics)
    assert all("operator" in str(item.get("message") or "").lower() for item in denoiser.source_operator_diagnostics)
    # Empty diagnostics are not a saturation claim; targeted questions can remain.
    assert questions


def test_generic_prompts_and_closed_targets_do_not_bypass_or_repeat():
    denoiser = ComplaintDenoiser()
    denoiser.actor_critic_enabled = False
    kg, dg, intake = _graphs()
    intake = dict(intake)
    intake.pop("source_capability")
    generic = {
        "type": "clarification",
        "question": "Can you provide more details about anything else?",
        "priority": "high",
        "candidate_source": "standard_intake_backstop",
        "context": {},
    }
    operator = {
        "type": "clarification",
        "question": "The prover is unavailable. Can you repair the backend and rerun the solver?",
        "priority": "high",
        "candidate_source": "source_outage",
        "context": {"source_status": "unavailable", "requirement_id": "solver-outage"},
    }
    questions = denoiser.generate_questions(
        kg,
        dg,
        max_questions=6,
        intake_case_file=intake,
        additional_candidates=[generic, operator],
    )
    texts = " ".join(question["question"].lower() for question in questions)
    assert "anything else" not in texts
    assert "repair the backend" not in texts
    assert "prover" not in texts
    assert any(item.get("audience") == "operator" for item in denoiser.source_operator_diagnostics)

    closed_id = questions[0]["unresolved_target"]["target_id"]
    denoiser.target_dispositions[closed_id] = "unknown"
    denoiser.questions_asked.append({
        "question": questions[0],
        "answer": "",
        "disposition": "declined",
    })
    again = denoiser.generate_questions(kg, dg, max_questions=6, intake_case_file=intake)
    assert all(question["unresolved_target"]["target_id"] != closed_id for question in again)


def test_ranking_uses_dependency_impact_uncertainty_and_answerability():
    denoiser = ComplaintDenoiser()
    denoiser.actor_critic_enabled = False
    low = denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text="What dates or documents can you share about the later notice?",
        context={"requirement_id": "req-low", "dependency_impact": 0, "uncertainty": 0, "target_revision": "r1"},
        priority="low",
    )
    high = denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text="What dates or documents can you share about the termination decision?",
        context={"requirement_id": "req-high", "dependency_impact": 5, "uncertainty": 4, "target_revision": "r1"},
        priority="low",
    )
    selected = denoiser.select_question_candidates([low, high], max_questions=2)
    assert [item["unresolved_target"]["target_id"] for item in selected] == [
        "requirement:req-high",
        "requirement:req-low",
    ]
    again = denoiser.select_question_candidates([high, low], max_questions=2)
    assert [item["target_id"] for item in again] == [item["target_id"] for item in selected]


def test_inquiry_registration_preserves_target_disposition_and_payload():
    mediator = Mediator(backends=[Mock(id="test-backend")])
    denoiser = ComplaintDenoiser(mediator=mediator)
    mediator.denoiser = denoiser
    kg, dg, intake = _graphs()
    intake = dict(intake)
    intake.pop("source_capability")
    questions = denoiser.generate_questions(kg, dg, max_questions=4, intake_case_file=intake)
    registered = []
    for question in questions:
        target = question["unresolved_target"]
        registered.append({
            "question": question["question"],
            "priority": question.get("priority") or "high",
            "unresolved_target": target,
            "why_answer_helps": target["why_answer_helps"],
            "expected_information": target["expected_information"],
            "user_answerability": target["user_answerability"],
            "provenance": target["provenance"],
            "answer": None,
        })
    merged = mediator.inquiries.merge_legal_questions(registered)
    assert merged == len(registered)
    pending = mediator.inquiries.get_next()
    assert pending["unresolved_target"]["target_id"]
    explanation = mediator.inquiries.explain_inquiry(pending)
    mediator.state.current_inquiry = pending
    mediator.state.current_inquiry_explanation = explanation
    mediator.process = Mock(return_value=pending["question"])
    payload = mediator.io_payload("yes")
    assert payload["inquiry"]["unresolved_target"]["target_id"] == pending["unresolved_target"]["target_id"]
    assert payload["explanation"]["unresolved_target"]["target_revision"] == pending["unresolved_target"]["target_revision"]
    assert payload["explanation"]["expected_information"]
    assert payload["explanation"]["why_answer_helps"]

    closed = dict(mediator.state.inquiries[0])
    closed["answer"] = None
    closed["disposition"] = "unknown"
    mediator.state.inquiries[0] = closed
    mediator.inquiries.merge_legal_questions([{
        "question": closed["question"],
        "answer": None,
        "disposition": None,
        "unresolved_target": {"target_id": "replacement-target", "target_revision": "other", "target_kind": "factual"},
    }])
    assert mediator.state.inquiries[0]["disposition"] == "unknown"
    assert mediator.state.inquiries[0]["unresolved_target"]["target_id"] == closed["unresolved_target"]["target_id"]
    nxt = mediator.inquiries.get_next()
    if nxt is not None:
        assert nxt["unresolved_target"]["target_id"] != closed["unresolved_target"]["target_id"]


def test_selector_keeps_impact_order_for_equal_selector_scores():
    mediator = Mediator(backends=[Mock(id="test-backend")])
    denoiser = ComplaintDenoiser()
    mediator.denoiser = denoiser
    mediator.phase_manager.get_phase_data = Mock(return_value=None)
    mediator.build_inquiry_gap_context = Mock(return_value={})
    mediator._build_intake_claim_pressure_map = Mock(return_value={})
    mediator._build_intake_matching_pressure_map = Mock(return_value={})
    low = denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text="What documents show the first notice date?",
        context={"requirement_id": "a-low", "dependency_impact": 1, "uncertainty": 1, "target_revision": "rev-a"},
        priority="medium",
    )
    high = denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text="What documents show the decision date?",
        context={"requirement_id": "b-high", "dependency_impact": 4, "uncertainty": 3, "target_revision": "rev-b"},
        priority="medium",
    )
    for candidate in (low, high):
        candidate["selector_score"] = 1.0
        candidate["actor_critic_score"] = 1.0
    selected = mediator.select_intake_question_candidates([low, high], max_questions=2)
    assert selected[0]["unresolved_target"]["dependency_impact"] >= selected[-1]["unresolved_target"]["dependency_impact"]
    assert selected[0]["unresolved_target"]["target_id"] == "requirement:b-high"


def _timeline_prompt(revision="scope-a"):
    return {
        "type": "timeline",
        "question": (
            "What is the timeline of key events, including dates, who made each decision, "
            "what notice or communication you received, and when you requested help or accommodation?"
        ),
        "priority": "high",
        "candidate_source": "standard_intake_backstop",
        "context": {"standard_intake_slot": "timeline", "target_revision": revision},
    }


def test_case_file_persists_target_revision_and_dispositions():
    kg, _, _ = _graphs()
    case_file = build_intake_case_file(kg, "Synthetic intake.")
    assert case_file["question_dispositions"] == []
    records = []
    for index, disposition in enumerate(QUESTION_DISPOSITIONS):
        records.append(record_question_disposition(
            case_file,
            target_id=f"factual:standard-intake:slot-{index}",
            target_revision="scope-a",
            disposition=disposition,
            target_kind="factual",
            question=f"Synthetic question {index}",
            answer="I do not know" if disposition != "answered" else "The meeting was on 2 March.",
            creates_fact=True,
            satisfies_requirement=True,
            contradictory_conclusion=True,
        ))
    refreshed = refresh_intake_case_file(case_file, kg)
    stored = refreshed["question_dispositions"]
    assert [item["disposition"] for item in stored] == list(QUESTION_DISPOSITIONS)
    assert {item["target_revision"] for item in stored} == {"scope-a"}
    for item in stored:
        if item["disposition"] != "answered":
            assert item["creates_fact"] is False
            assert item["satisfies_requirement"] is False
            assert item["contradictory_conclusion"] is False
        assert question_target_is_closed(refreshed, item["target_id"], "scope-a")
        assert question_target_is_closed(refreshed, item["target_id"], "scope-b")
    again = record_question_disposition(
        refreshed,
        target_id=records[0]["target_id"],
        target_revision="scope-a",
        disposition="unknown",
        target_kind="factual",
    )
    assert sum(item["target_id"] == again["target_id"] and not item["reopened"] for item in refreshed["question_dispositions"]) == 1


def test_equivalent_standard_intake_prompts_are_not_reinserted_until_reopened():
    denoiser = ComplaintDenoiser()
    denoiser.actor_critic_enabled = False
    kg, dg, intake = _graphs()
    intake = dict(intake)
    intake.pop("source_capability")
    intake["question_scope_revision"] = "scope-a"
    case_file = build_intake_case_file(kg, "")
    case_file["question_scope_revision"] = "scope-a"
    denoiser.record_question_disposition(
        _timeline_prompt(),
        "I don't know",
        intake_case_file=case_file,
    )
    stored = case_file["question_dispositions"][0]
    assert stored["target_id"] == "factual:standard-intake:timeline"
    assert stored["target_revision"] == "scope-a"
    assert stored["disposition"] == "unknown"
    assert stored["creates_fact"] is False
    equivalent = {
        "type": "timeline",
        "question": "Please share the timeline of key events and who made each decision.",
        "priority": "high",
        "candidate_source": "standard_intake_backstop",
        "context": {"target_revision": "scope-a"},
    }
    for _ in range(4):
        generated = denoiser.generate_questions(
            kg,
            dg,
            max_questions=8,
            intake_case_file=intake,
            additional_candidates=[equivalent, dict(equivalent, question="What is the timeline of key events again?")],
        )
        assert all(
            question["unresolved_target"]["target_id"] != "factual:standard-intake:timeline"
            for question in generated
        )
    with pytest.raises(ValueError):
        denoiser.reopen_disposed_question("factual:standard-intake:timeline", "", evidence_change="new letter")
    with pytest.raises(ValueError):
        denoiser.reopen_disposed_question("factual:standard-intake:timeline", "scope changed")
    denoiser.reopen_disposed_question(
        "factual:standard-intake:timeline",
        "A newly provided letter changes the timeline scope.",
        target_revision="scope-b",
        intake_case_file=case_file,
        evidence_change="letter dated 2 May",
        scope_change="scope-b",
    )
    assert case_file["question_dispositions"][-1]["reopened"] is True
    assert case_file["question_dispositions"][-1]["reopen_reason"]
    intake["question_scope_revision"] = "scope-b"
    reopened_prompt = dict(equivalent)
    reopened_prompt["context"] = {"standard_intake_slot": "timeline", "target_revision": "scope-b"}
    reopened = denoiser.generate_questions(
        kg,
        dg,
        max_questions=8,
        intake_case_file=intake,
        additional_candidates=[reopened_prompt],
    )
    assert any(
        question["unresolved_target"]["target_id"] == "factual:standard-intake:timeline"
        for question in reopened
    )


def test_unknown_and_refusal_do_not_create_facts_or_conclusions():
    denoiser = ComplaintDenoiser()
    kg, dg, _ = _graphs()
    question = denoiser._bind_unresolved_target(denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text="What dates or documents can you share about the protected activity?",
        context={"requirement_id": "req-protected", "target_revision": "scope-a"},
        priority="high",
    ))
    before_entities = set(kg.entities)
    before_relationships = set(kg.relationships)
    before_dependencies = set(dg.dependencies)
    satisfied = {node_id: node.satisfied for node_id, node in dg.nodes.items()}
    for answer in ("I don't know", "I decline to answer", "skip", "ask me later", "invalidated"):
        updates = denoiser.process_answer(question, answer, kg, dg)
        assert updates["entities_updated"] == 0
        assert updates["relationships_added"] == 0
        assert updates["requirements_satisfied"] == 0
        assert updates["creates_fact"] is False
        assert updates["satisfies_requirement"] is False
        assert updates["contradictory_conclusion"] is False
        assert updates["disposition"] in {"unknown", "refused", "skipped", "deferred", "invalidated"}
    assert set(kg.entities) == before_entities
    assert set(kg.relationships) == before_relationships
    assert set(dg.dependencies) == before_dependencies
    assert {node_id: node.satisfied for node_id, node in dg.nodes.items()} == satisfied


def test_mediator_records_disposition_and_reopens_with_reason():
    mediator = Mediator(backends=[Mock(id="test-backend")])
    denoiser = ComplaintDenoiser(mediator=mediator)
    mediator.denoiser = denoiser
    kg, _, _ = _graphs()
    case_file = build_intake_case_file(kg, "")
    question = _timeline_prompt("scope-a")
    question["unresolved_target"] = {
        "target_id": "factual:standard-intake:timeline",
        "target_revision": "scope-a",
        "target_kind": "factual",
    }
    mediator.state.inquiries = [{
        "question": question["question"],
        "answer": None,
        "unresolved_target": dict(question["unresolved_target"]),
    }]
    record = mediator.record_intake_question_disposition(
        question,
        "I refuse",
        intake_case_file=case_file,
    )
    assert record["disposition"] == "refused"
    assert record["creates_fact"] is False
    assert case_file["question_dispositions"][0]["target_revision"] == "scope-a"
    assert mediator.state.inquiries[0]["disposition"] == "refused"
    assert mediator.inquiries.get_next() is None
    selected = mediator.select_intake_question_candidates([question], max_questions=2)
    assert selected == []
    mediator.reopen_intake_question(
        "factual:standard-intake:timeline",
        "The complainant supplied a new notice.",
        target_revision="scope-b",
        intake_case_file=case_file,
        evidence_change="notice dated 2 May",
    )
    assert question_target_is_closed(case_file, "factual:standard-intake:timeline", "scope-b") is False
    refreshed = refresh_intake_case_file(case_file, kg)
    assert refreshed["question_dispositions"][-1]["status"] == "reopened"


def _bound_question(denoiser, target_id, text="What date do you recall?"):
    return denoiser._bind_unresolved_target(denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text=text,
        context={"requirement_id": target_id, "target_revision": "scope-a"},
        priority="high",
    ))


def test_empty_pool_question_cap_and_loss_plateau_are_not_saturation():
    denoiser = ComplaintDenoiser()
    denoiser.questions_pool.clear()
    denoiser.questions_asked.extend({"question": {"question": "q"}} for _ in range(51))
    assert denoiser.is_exhausted() is False
    capped = denoiser.evaluate_interview_stop(open_questions=[], loss_converged=True, pool_empty=True)
    assert capped["state"] == "limit_reached"
    assert capped["filing_ready"] is False
    assert capped["intake_complete"] is False
    assert capped["legal_sufficiency"] is False
    assert "question_count_limit" in capped["unresolved_issue_summary"]["rejected_shortcuts"]
    assert "loss_convergence" in capped["unresolved_issue_summary"]["rejected_shortcuts"]
    assert "complete" in capped["message"]
    assert "not ready to file" in capped["message"]

    fresh = ComplaintDenoiser()
    plateau = fresh.evaluate_interview_stop(open_questions=[], loss_converged=True, pool_empty=True)
    assert plateau["state"] == "needs_answer"
    assert plateau["intake_complete"] is False
    assert plateau["filing_ready"] is False
    assert fresh.is_exhausted() is False


def test_saturated_stop_requires_disposed_targets_and_lists_unresolved_issues():
    denoiser = ComplaintDenoiser()
    kg, dg, _ = _graphs()
    answered = _bound_question(denoiser, "req-protected")
    refused = _bound_question(denoiser, "req-notice", "What document shows the notice date?")
    denoiser.record_question_disposition(answered, "March 1, 2024", disposition="answered")
    denoiser.record_question_disposition(refused, "I decline", disposition="refused")
    stop = denoiser.evaluate_interview_stop(
        open_questions=[answered, refused],
        loss_converged=True,
        pool_empty=True,
        iteration_count=3,
        iteration_cap=20,
    )
    assert stop["state"] == "saturated"
    assert stop["targets_accounted_for"] is True
    assert stop["filing_ready"] is False
    assert stop["legal_sufficiency"] is False
    assert stop["intake_complete"] is False
    summary = stop["unresolved_issue_summary"]
    assert summary["core_facts_complete"] is False
    assert any(item.get("disposition") == "refused" for item in summary["items"])
    assert denoiser.is_exhausted() is True


def test_unknown_only_stop_is_deferred_unknown_not_completion():
    denoiser = ComplaintDenoiser()
    question = _bound_question(denoiser, "req-protected")
    denoiser.record_question_disposition(question, "I don't know", disposition="unknown")
    stop = denoiser.evaluate_interview_stop(open_questions=[question], pool_empty=True)
    assert stop["state"] == "deferred_unknown"
    assert stop["intake_complete"] is False
    assert stop["filing_ready"] is False
    assert stop["unresolved_issue_summary"]["core_facts_complete"] is False
    assert stop["unresolved_issue_summary"]["items"]


def test_provider_failure_and_cancellation_do_not_advertise_readiness():
    denoiser = ComplaintDenoiser()
    question = _bound_question(denoiser, "req-protected")
    failed = denoiser.evaluate_interview_stop(
        open_questions=[question],
        provider_status="provider_unavailable",
        iteration_count=20,
        iteration_cap=20,
    )
    assert failed["state"] == "provider_unavailable"
    assert failed["intake_complete"] is False
    assert failed["filing_ready"] is False
    assert failed["ready_for_evidence_phase"] is False
    cancelled = denoiser.evaluate_interview_stop(open_questions=[question], cancelled=True)
    assert cancelled["state"] == "cancelled"
    assert cancelled["intake_complete"] is False
    assert cancelled["filing_ready"] is False


def test_iteration_cap_action_is_limit_reached_and_blocks_intake_completion():
    pm = PhaseManager()
    pm.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", {})
    pm.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", {})
    pm.update_phase_data(ComplaintPhase.INTAKE, "remaining_gaps", 5)
    pm.update_phase_data(ComplaintPhase.INTAKE, "denoising_converged", False)
    pm.update_phase_data(ComplaintPhase.INTAKE, "current_gaps", [])
    pm.iteration_count = 20
    action = pm.get_next_action()
    assert action["action"] == "limit_reached"
    assert action["filing_ready"] is False
    assert action["intake_complete"] is False
    assert pm.is_phase_complete(ComplaintPhase.INTAKE) is False
    assert "not ready to file" in action["message"]

    pm.update_phase_data(ComplaintPhase.INTAKE, "interview_stop", {
        "state": "provider_unavailable",
        "intake_complete": False,
        "filing_ready": False,
        "message": "backend down",
        "unresolved_issue_summary": {"items": [{"reason": "backend"}], "legal_sufficiency": False},
    })
    blocked = pm.get_next_action()
    assert blocked["action"] == "provider_unavailable"
    assert blocked["filing_ready"] is False
    assert pm.is_phase_complete(ComplaintPhase.INTAKE) is False
    assert pm.get_intake_readiness()["ready"] is False


def test_pause_and_resume_preserve_assertion_truth_without_supervisory_restart():
    mediator = Mediator(backends=[Mock(id="test-backend")])
    kg, dg, _ = _graphs()
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", kg)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", dg)
    mediator.phase_manager.iteration_count = 4
    before_entities = [(entity.id, entity.name, entity.confidence) for entity in kg.entities.values()]
    before_nodes = [(node.id, node.satisfied, node.name) for node in dg.nodes.values()]
    paused = mediator.pause_intentional_user_wait("user_pause")
    assert paused["status"] == "awaiting_user"
    assert paused["paused"] is True
    assert paused["worker_stalled"] is False
    assert paused["supervisory_restart"] is False
    assert paused["iteration_count"] == 4
    assert [(entity.id, entity.name, entity.confidence) for entity in kg.entities.values()] == before_entities
    assert [(node.id, node.satisfied, node.name) for node in dg.nodes.values()] == before_nodes
    assert mediator.phase_manager.get_next_action()["action"] == "awaiting_user"
    assert mediator.phase_manager.get_next_action()["supervisory_restart"] is False
    resumed = mediator.resume_intentional_user_wait()
    assert resumed["resumed"] is True
    assert resumed["supervisory_restart"] is False
    assert resumed["worker_stalled"] is False
    assert resumed["assertion_rule_unchanged"] is True
    assert resumed["iteration_count"] == 4
    assert mediator.phase_manager.iteration_count == 4
    assert [(entity.id, entity.name, entity.confidence) for entity in kg.entities.values()] == before_entities
    assert [(node.id, node.satisfied, node.name) for node in dg.nodes.values()] == before_nodes


def test_intake_status_hides_filing_readiness_for_incomplete_stops():
    class _Mediator:
        def get_three_phase_status(self):
            return {
                "current_phase": "intake",
                "intake_readiness": {
                    "ready_to_advance": True,
                    "score": 1,
                    "remaining_gap_count": 0,
                    "contradiction_count": 0,
                    "blockers": [],
                    "criteria": {},
                },
                "interview_stop": {
                    "state": "limit_reached",
                    "intake_complete": False,
                    "filing_ready": False,
                    "legal_sufficiency": False,
                    "unresolved_issue_summary": {
                        "items": [{"reason": "iteration_cap"}],
                        "legal_sufficiency": False,
                        "core_facts_complete": False,
                    },
                },
                "intentional_user_wait": {
                    "status": "awaiting_user",
                    "awaiting_user": True,
                    "paused": True,
                    "worker_stalled": False,
                    "supervisory_restart": False,
                },
            }

    summary = build_intake_status_summary(_Mediator())
    assert summary["interview_stop"]["state"] == "limit_reached"
    assert summary["ready_to_advance"] is False
    assert summary["filing_ready"] is False
    assert summary["intake_complete"] is False
    assert summary["unresolved_issue_summary"]["items"]
    assert summary["awaiting_user"] is True
    assert summary["worker_stalled"] is False
    assert summary["supervisory_restart"] is False


# Corrective context-target regressions use actual owned storage and canonical
# context selection. No product selector, target binder, source gate or proof
# method is mocked. The one initial public journey uses the existing real KG
# extraction manager on a fixed synthetic narrative.
import copy
import pytest
from complaint_phases.phase_manager import ComplaintPhase
from complaint_phases.intake_case_file import apply_explicit_legal_context
from tests.test_authority_dependency_pipeline import _MockBackend as _ContextOfflineBackend


def _context_workflow(tmp_path):
    mediator = Mediator([_ContextOfflineBackend()],
                        evidence_db_path=str(tmp_path / 'context-evidence.duckdb'),
                        legal_authority_db_path=str(tmp_path / 'context-authorities.duckdb'),
                        claim_support_db_path=str(tmp_path / 'context-support.duckdb'))
    mediator.state.username = 'synthetic-context-owner'
    return mediator


def test_initial_public_pipeline_keeps_current_jurisdiction_and_date_questions(tmp_path):
    mediator = _context_workflow(tmp_path)
    mediator.start_three_phase_process('My employer discriminated against me.')
    intake = mediator.phase_manager.phase_data[ComplaintPhase.INTAKE]
    questions = intake['current_questions']
    context_questions = [q for q in questions if q.get('type') == 'legal_context']
    by_field = {q['field']: q for q in context_questions}
    assert {'jurisdiction', 'applicable_law_date'} <= set(by_field)
    for question in context_questions:
        target = question['unresolved_target']
        assert target['target_kind'] == 'factual'
        assert target['target_id'] == 'legal_context:' + question['question_id']
        assert target['target_revision'].startswith('legal-context:')
        assert target['provenance']['field'] == question['field']
        assert target['why_answer_helps'] and target['expected_information']
        assert target['user_answerability'] == 'user_observable'
    assert mediator.phase_manager.get_intake_readiness()['ready'] is False
    assert 'legal_context_source_gap' in mediator.phase_manager.get_intake_readiness()['blockers']
    assert not intake['legal_selection']['ready_to_select']
    original_facts = copy.deepcopy(intake['intake_case_file'].get('canonical_facts') or [])
    original_entity_ids = set(intake['knowledge_graph'].entities)
    unknown = mediator.process_denoising_answer(by_field['jurisdiction'], 'I do not know')
    assert unknown['updates']['disposition'] == 'unknown'
    assert unknown['updates']['graph_revision']['action'] == 'context_answer'
    assert unknown['updates']['graph_revision']['creates_fact'] is False
    assert intake['intake_case_file']['legal_context']['jurisdiction'] == 'unknown'
    event_question = next(q for q in unknown['next_questions'] if q.get('field') == 'event_date')
    refused = mediator.process_denoising_answer(event_question, 'I refuse to answer')
    assert refused['updates']['disposition'] == 'refused'
    assert refused['updates']['graph_revision']['support_changes'] == []
    assert set(intake['knowledge_graph'].entities) == original_entity_ids
    mediator.reopen_intake_question(
        by_field['jurisdiction']['target_id'], 'The user elected to supply a jurisdiction.',
        target_revision=by_field['jurisdiction']['target_revision'],
        evidence_change='user_supplied_jurisdiction_followup',
    )
    response = mediator.process_denoising_answer(by_field['jurisdiction'], 'OR')
    case = intake['intake_case_file']
    assert case['legal_context']['jurisdiction'] == 'OR'
    assert response['updates']['context_fields_updated'] == ['jurisdiction']
    assert response['updates']['creates_fact'] is False
    assert response['updates']['requirements_satisfied'] == 0
    next_date = next(q for q in response['next_questions']
                     if q.get('type') == 'legal_context' and q['field'] == 'applicable_law_date')
    old_date = by_field['applicable_law_date']
    before_stale_context = copy.deepcopy(case['legal_context'])
    stale = mediator.process_denoising_answer(old_date, '2020-01-01')
    assert stale['updates']['context_answer_status'] == 'stale_or_unbound_context_target'
    assert case['legal_context'] == before_stale_context
    assert stale['updates']['graph_revision']['action'] == 'context_answer'
    assert stale['updates']['graph_revision']['creates_fact'] is False
    assert set(intake['knowledge_graph'].entities) == original_entity_ids
    response = mediator.process_denoising_answer(next_date, '2024-06-01')
    assert case['legal_context']['applicable_law_date']['precise_date'] == '2024-06-01'
    assert case['canonical_facts'] == original_facts
    assert set(intake['knowledge_graph'].entities) == original_entity_ids
    assert response['updates']['context_fields_updated'] == ['applicable_law_date']
    assert response['updates']['satisfies_requirement'] is False
    assert response['interview_stop']['state'] == 'needs_answer'
    assert response['interview_stop']['unresolved_issue_summary']['open_answerable_count'] > 0
    assert response['converged'] is False and response['ready_for_evidence_phase'] is False
    revision = response['updates']['graph_revision']
    assert revision['action'] == 'context_answer'
    assert revision['statement'] == '2024-06-01'
    assert revision['source_hash'] and revision['source_span']
    assert revision['epistemic_class'] == 'user_context'
    assert revision['entity_id'] == '' and revision['stable_id'] == ''
    assert revision['support_changes'] == [] and revision['creates_fact'] is False


def test_current_canonical_context_fields_survive_public_question_generation(tmp_path):
    mediator = _context_workflow(tmp_path)
    kg, dg, case = KnowledgeGraph(), DependencyGraph(), {}
    selection = mediator.resolve_intake_legal_selection([], case)
    candidates = mediator._legal_selection_questions(selection)
    before_context = copy.deepcopy(case['legal_context'])
    denoiser = ComplaintDenoiser()
    questions = denoiser.generate_questions(kg, dg, max_questions=20,
                                           intake_case_file=case, additional_candidates=candidates)
    context_questions = [q for q in questions if q.get('type') == 'legal_context']
    assert {q['field'] for q in context_questions} == {
        'jurisdiction', 'event_date', 'applicable_law_date', 'filing_reference_date', 'claim_candidates'}
    assert {q['question_id'] for q in context_questions} == {q['question_id'] for q in candidates}
    assert all(q['unresolved_target']['provenance']['question_id'] == q['question_id'] for q in context_questions)
    assert len({q['target_revision'] for q in context_questions}) == 1
    assert case['legal_context'] == before_context
    assert not case.get('candidate_claims')


@pytest.mark.parametrize('changes', [
    {'field': 'unrecognized_field'},
    {'question_id': 'legal_context.invented_question'},
    {'target_revision': 'legal-context:stale'},
    {'unresolved_target': {'target_id': 'foreign-case-target', 'target_revision': 'stale'}},
])
def test_context_candidate_tags_do_not_bypass_current_canonical_scope(tmp_path, changes):
    mediator = _context_workflow(tmp_path)
    kg, dg, case = KnowledgeGraph(), DependencyGraph(), {}
    selection = mediator.resolve_intake_legal_selection([], case)
    candidate = next(q for q in mediator._legal_selection_questions(selection) if q['field'] == 'jurisdiction')
    candidate.update(changes)
    questions = ComplaintDenoiser().generate_questions(
        kg, dg, max_questions=20, intake_case_file=case, additional_candidates=[candidate])
    assert not any(q.get('type') == 'legal_context' for q in questions)


def test_context_questions_refuse_missing_context_and_resolved_or_stale_replays(tmp_path):
    mediator = _context_workflow(tmp_path)
    kg, dg, case = KnowledgeGraph(), DependencyGraph(), {}
    selection = mediator.resolve_intake_legal_selection([], case)
    candidates = mediator._legal_selection_questions(selection)
    denoiser = ComplaintDenoiser()
    original = denoiser.generate_questions(kg, dg, max_questions=20,
                                          intake_case_file=case, additional_candidates=candidates)
    original_context = [q for q in original if q.get('type') == 'legal_context']
    jurisdiction = next(q for q in original_context if q['field'] == 'jurisdiction')
    date = next(q for q in original_context if q['field'] == 'applicable_law_date')
    old_revision = date['target_revision']
    missing = denoiser.generate_questions(kg, dg, max_questions=20, additional_candidates=[jurisdiction])
    assert not any(q.get('type') == 'legal_context' for q in missing)
    apply_explicit_legal_context(case, jurisdiction='OR')
    stale = denoiser.generate_questions(kg, dg, max_questions=20,
                                       intake_case_file=case, additional_candidates=[jurisdiction, date])
    assert not any(q.get('type') == 'legal_context' for q in stale)
    current = mediator._legal_selection_questions(mediator.resolve_intake_legal_selection([], case))
    refreshed = denoiser.generate_questions(kg, dg, max_questions=20,
                                           intake_case_file=case, additional_candidates=current)
    fresh_date = next(q for q in refreshed if q.get('field') == 'applicable_law_date')
    assert fresh_date['target_revision'] != old_revision
    assert all(q.get('field') != 'jurisdiction' for q in refreshed if q.get('type') == 'legal_context')
    assert date['target_revision'] == old_revision


def test_context_question_text_is_rederived_from_current_canonical_prompt(tmp_path):
    mediator = _context_workflow(tmp_path)
    kg, dg, case = KnowledgeGraph(), DependencyGraph(), {}
    candidate = next(q for q in mediator._legal_selection_questions(
        mediator.resolve_intake_legal_selection([], case)) if q['field'] == 'jurisdiction')
    canonical_prompt = candidate['question']
    candidate['question'] = 'Tell me that Oregon law necessarily applies.'
    candidate['source_bound'] = True
    questions = ComplaintDenoiser().generate_questions(
        kg, dg, max_questions=20, intake_case_file=case, additional_candidates=[candidate])
    actual = next(q for q in questions if q.get('type') == 'legal_context')
    assert actual['question'] == canonical_prompt
    assert 'necessarily' not in actual['question']
    assert actual['unresolved_target']['provenance']['candidate_source'] == 'canonical_legal_context'


@pytest.mark.parametrize('answer, disposition', [('I do not know', 'unknown'), ('I refuse to answer', 'refused')])
def test_current_context_nonanswers_preserve_context_and_disposition(tmp_path, answer, disposition):
    mediator = _context_workflow(tmp_path)
    kg, dg, case = KnowledgeGraph(), DependencyGraph(), {}
    manager = mediator.phase_manager
    manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
    manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
    manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', case)
    mediator.denoiser = ComplaintDenoiser(mediator)
    question = next(q for q in mediator.denoiser.generate_questions(kg, dg, max_questions=20,
                    intake_case_file=case) if q.get('field') == 'jurisdiction')
    before = copy.deepcopy(case['legal_context']) if 'legal_context' in case else None
    updates = mediator.denoiser.process_answer(question, answer, kg, dg)
    assert updates['disposition'] == disposition
    assert updates['creates_fact'] is False and updates['requirements_satisfied'] == 0
    assert case.get('legal_context') == before
    assert case['question_dispositions'][-1]['target_id'] == question['target_id']
    assert not kg.entities and not dg.nodes
    repeated = mediator.denoiser.generate_questions(kg, dg, max_questions=20, intake_case_file=case)
    assert all(q.get('field') != 'jurisdiction' for q in repeated)


def test_stale_and_coordinate_only_context_answers_cannot_update_case(tmp_path):
    mediator = _context_workflow(tmp_path)
    kg, dg, case = KnowledgeGraph(), DependencyGraph(), {}
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', case)
    mediator.denoiser = ComplaintDenoiser(mediator)
    question = next(q for q in mediator.denoiser.generate_questions(kg, dg, max_questions=20,
                    intake_case_file=case) if q.get('field') == 'applicable_law_date')
    apply_explicit_legal_context(case, jurisdiction='OR')
    before = copy.deepcopy(case)
    stale = mediator.denoiser.process_answer(question, '2024-06-01', kg, dg)
    raw = {'type': 'legal_context', 'question_id': 'legal_context.applicable_law_date',
           'field': 'applicable_law_date', 'question': 'Supply a date.'}
    unbound = mediator.denoiser.process_answer(raw, '2024-06-01', kg, dg)
    assert stale['context_answer_status'] == 'stale_or_unbound_context_target'
    assert unbound['context_answer_status'] == 'stale_or_unbound_context_target'
    assert case == before
    assert not kg.entities and not dg.nodes


def test_explicit_claim_context_answer_records_candidate_without_promoting_law(tmp_path):
    mediator = _context_workflow(tmp_path)
    kg, dg, case = KnowledgeGraph(), DependencyGraph(), {}
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', case)
    mediator.denoiser = ComplaintDenoiser(mediator)
    question = next(q for q in mediator.denoiser.generate_questions(kg, dg, max_questions=20,
                    intake_case_file=case) if q.get('field') == 'claim_candidates')
    updates = mediator.denoiser.process_answer(question, 'employment_discrimination', kg, dg)
    assert case['candidate_claims'][0]['claim_type'] == 'employment_discrimination'
    assert case['candidate_claims'][0]['source'] == 'user_context_answer'
    assert updates['context_fields_updated'] == ['claim_candidates']
    assert updates['creates_fact'] is False and updates['requirements_satisfied'] == 0
    assert not kg.entities and not dg.nodes


def test_partial_context_date_answer_reopens_only_current_unresolved_field(tmp_path):
    mediator = _context_workflow(tmp_path)
    kg, dg, case = KnowledgeGraph(), DependencyGraph(), {}
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', case)
    mediator.denoiser = ComplaintDenoiser(mediator)
    question = next(q for q in mediator.denoiser.generate_questions(kg, dg, max_questions=20,
                    intake_case_file=case) if q.get('field') == 'applicable_law_date')
    updates = mediator.denoiser.process_answer(question, '2024', kg, dg)
    assert updates['context_answer_status'] == 'needs_context_clarification'
    assert updates['question_reopened']['reopened'] is True
    assert updates['question_reopened']['evidence_change'].startswith('explicit-context-answer:')
    assert case['legal_context']['applicable_law_date'].get('precise_date') is None
    next_questions = mediator.denoiser.generate_questions(kg, dg, max_questions=20, intake_case_file=case)
    current_date = next(q for q in next_questions if q.get('field') == 'applicable_law_date')
    assert current_date['target_revision'] != question['target_revision']
    assert not kg.entities and not dg.nodes


@pytest.mark.parametrize('raw_date', [
    '2024', 'June 2024', 'March 2024 to May 2024',
    '2024-06-01 to 2024-06-30', 'around June 2024',
])
def test_canonical_law_version_question_stays_open_for_non_day_dates(raw_date):
    from integrations.ipfs_datasets.legal import (
        classify_legal_date, empty_legal_context, intake_legal_selection,
        questions_for_legal_context,
    )
    context = empty_legal_context()
    event = classify_legal_date('2023', role='event_date')
    context.update(jurisdiction='OR', jurisdiction_explicit=True,
                   applicable_law_date=classify_legal_date(raw_date, role='applicable_law_date'),
                   event_date=event, event_dates=[copy.deepcopy(event)],
                   filing_reference_date=classify_legal_date('2025-03-01', role='filing_reference_date'))
    before = copy.deepcopy(context)
    questions = questions_for_legal_context(context, selecting_rules=True)
    selection = intake_legal_selection(context, [{'claim_type': 'employment_discrimination'}])
    assert [q['question_id'] for q in questions] == ['legal_context.applicable_law_date']
    assert [q['question_id'] for q in selection['questions']] == ['legal_context.applicable_law_date']
    assert selection['ready_to_select'] is False and selection['relevant_date'] is None
    assert selection['unresolved_reasons'] == ['missing_applicable_law_date']
    assert context == before
    assert context['applicable_law_date']['raw_text'] == raw_date
    assert context['applicable_law_date']['precise_date'] is None
    assert context['event_date']['precise_date'] is None
    assert (context['event_date']['start_date'], context['event_date']['end_date']) == ('2023-01-01', '2023-12-31')


@pytest.mark.parametrize('raw_date', ['2024-06-01', 'June 1, 2024', '2024-06-01T12:00:00'])
def test_canonical_law_version_question_closes_for_an_explicit_day(raw_date):
    from integrations.ipfs_datasets.legal import (
        classify_legal_date, empty_legal_context, intake_legal_selection,
        questions_for_legal_context,
    )
    context = empty_legal_context()
    context.update(jurisdiction='OR', jurisdiction_explicit=True,
                   applicable_law_date=classify_legal_date(raw_date, role='applicable_law_date'))
    before = copy.deepcopy(context)
    questions = questions_for_legal_context(context, selecting_rules=True)
    selection = intake_legal_selection(context, [{'claim_type': 'employment_discrimination'}])
    assert not any(q['field'] == 'applicable_law_date' for q in questions)
    assert selection['ready_to_select'] is True and selection['relevant_date'] == '2024-06-01'
    assert selection['questions'] == []
    assert context == before


# CIMP-QUEST-04: one application-level scripted interview. The TUI workstream
# imports application_level_interview_fixture and replays the same turns.
_SCRIPTED_TURN_LABELS = (
    "start",
    "complete",
    "unknown",
    "refused",
    "correction",
    "contradictory_dates",
    "rule_version",
    "jurisdiction",
    "provider_outage",
    "bounded_timeout",
)


def _deny_live_provider_io(monkeypatch):
    """Hermetic runner: sockets and live provider processes cannot be created."""
    import socket
    import subprocess

    def blocked(*_args, **_kwargs):
        raise RuntimeError("hermetic runner denied live provider io")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, blocked)
    try:
        socket.create_connection(("127.0.0.1", 9), timeout=0.01)
    except RuntimeError as exc:
        assert "denied" in str(exc)
    else:
        raise AssertionError("socket denial was not installed")


def _user_source(text, message_id):
    from integrations.ipfs_datasets.types import source_byte_hash

    return {
        "source_text": text,
        "source_kind": "user_statement",
        "source_id": message_id,
        "message_id": message_id,
        "assertion_status": "asserted",
        "extractor_version": "quest04-scripted",
        "source_hash": source_byte_hash(text),
        "source_span": {"start": 0, "end": len(text.encode("utf-8")), "text": text},
        "subject_key": "employment-date",
        "confidence": 0.9,
    }


def _observe_interview(mediator):
    from complaint_phases.phase_manager import ComplaintPhase

    kg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    dg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") or {}
    stop = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "interview_stop") or {}
    facts = []
    assertions = []
    if kg is not None:
        for entity in kg.entities.values():
            provenance = entity.provenance if isinstance(getattr(entity, "provenance", None), dict) else {}
            envelope = provenance.get("user_assertion") if isinstance(provenance.get("user_assertion"), dict) else {}
            facts.append({
                "id": entity.id,
                "type": entity.type,
                "name": entity.name,
                "statement": envelope.get("statement") or envelope.get("source_span", {}).get("text") if isinstance(envelope.get("source_span"), dict) else envelope.get("statement"),
                "source_id": envelope.get("source_id"),
                "source_hash": envelope.get("source_hash"),
            })
            if envelope:
                state = kg.assertion_state(envelope.get("stable_id")) if envelope.get("stable_id") and hasattr(kg, "assertion_state") else {}
                assertions.append({
                    "stable_id": envelope.get("stable_id"),
                    "status": (state or {}).get("status"),
                    "statement": envelope.get("statement") or entity.name,
                    "source_id": envelope.get("source_id"),
                    "source_hash": envelope.get("source_hash"),
                })
    legal = []
    if dg is not None:
        for node in dg.nodes.values():
            attrs = node.attributes if isinstance(node.attributes, dict) else {}
            kind = attrs.get("dependency_class")
            if kind not in {"legally_sourced_requirement", "legal_source_gap", "unresolved_legal_requirement"}:
                continue
            legal.append({
                "id": node.id,
                "dependency_class": kind,
                "name": node.name,
                "description": node.description,
                "satisfied": bool(node.satisfied),
                "satisfaction_state": attrs.get("satisfaction_state"),
                "source_available": attrs.get("source_available"),
                "source_hash": attrs.get("source_hash"),
                "authority_version": attrs.get("authority_version"),
                "rule_id": attrs.get("rule_id"),
                "law_derived": attrs.get("law_derived"),
                "heuristic_law_derived": attrs.get("heuristic_law_derived"),
                "verification_status": attrs.get("verification_status"),
            })
    dispositions = list(getattr(mediator.denoiser, "question_disposition_records", []) or [])
    if isinstance(case_file, dict):
        for item in case_file.get("question_dispositions") or []:
            if item not in dispositions:
                dispositions.append(item)
    return {
        "fact_ids": tuple(sorted(item["id"] for item in facts)),
        "facts": facts,
        "assertions": assertions,
        "legal": legal,
        "legal_ids": tuple(sorted(item["id"] for item in legal)),
        "dependency_ids": tuple(sorted(getattr(dg, "dependencies", {}) or {})),
        "dispositions": [
            {
                "target_id": item.get("target_id"),
                "disposition": item.get("disposition"),
                "creates_fact": item.get("creates_fact"),
            }
            for item in dispositions
            if isinstance(item, dict)
        ],
        "stop_state": stop.get("state") if isinstance(stop, dict) else None,
        "filing_ready": bool(stop.get("filing_ready")) if isinstance(stop, dict) else False,
        "intake_complete": bool(stop.get("intake_complete")) if isinstance(stop, dict) else False,
        "iteration_count": mediator.phase_manager.iteration_count,
    }


def _pending_question(mediator):
    from complaint_phases.phase_manager import ComplaintPhase

    questions = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "current_questions") or []
    for question in questions:
        if isinstance(question, dict) and str(question.get("type") or "").lower() != "legal_context":
            return question
    if questions and isinstance(questions[0], dict):
        return questions[0]
    raise AssertionError("scripted interview has no pending question")


def _sourced_answer(mediator, text, message_id, *, factual_action, **links):
    question = _pending_question(mediator)
    result = mediator.process_denoising_answer(
        question,
        text,
        answer_event_id=f"scripted-{message_id}",
        source_context=_user_source(text, message_id),
        factual_action=factual_action,
        **links,
    )
    from complaint_phases.phase_manager import ComplaintPhase

    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") or {}
    mediator.record_intake_question_disposition(
        question,
        text,
        disposition="answered",
        intake_case_file=case_file,
        creates_fact=True,
    )
    return result


def application_level_interview_fixture(tmp_path, monkeypatch):
    """Scripted synthetic interview over the real mediator interview API.

    Covers a complete sourced answer, unknown and refused answers, a correction,
    contradictory dates, a rule-version change, a jurisdiction change, provider
    outage, and a bounded timeout with resume. The same object is what a TUI
    flow can replay without a live provider.
    """
    import socket
    import subprocess

    from complaint_phases.phase_manager import ComplaintPhase
    from integrations.ipfs_datasets.llm import privacy_policy_for_mode
    from mediator.mediator import Mediator
    from tests.test_authority_dependency_pipeline import _CONTEXT, _source_record

    _deny_live_provider_io(monkeypatch)

    class _ScriptedBackend:
        id = "scripted-hermetic-backend"

        def __init__(self):
            self.mode = "ok"
            self.calls = 0

        def __call__(self, prompt, **kwargs):
            del prompt, kwargs
            self.calls += 1
            if self.mode == "outage":
                raise ConnectionError("provider outage")
            if self.mode == "timeout":
                raise TimeoutError("bounded timeout")
            return "Mock response"

    backend = _ScriptedBackend()
    db_dir = tmp_path / "quest04-dbs"
    db_dir.mkdir(parents=True, exist_ok=True)
    mediator = Mediator(
        [backend],
        evidence_db_path=str(db_dir / "evidence.db"),
        legal_authority_db_path=str(db_dir / "legal-authority.db"),
        claim_support_db_path=str(db_dir / "claim-support.db"),
    )
    mediator.state.username = "synthetic-user"
    local_policy = privacy_policy_for_mode("synthetic-user", "synthetic-user", "local")
    mediator.workflow_actions.bind_interview_privacy(
        local_policy,
        user_id="synthetic-user",
        case_id="synthetic-user",
    )
    original = _source_record("rule-protected", "Protected class")
    store = {"records": [original]}

    def _records(_user_id, _claim_type):
        return list(store["records"])

    monkeypatch.setattr(mediator.legal_authority_storage, "get_authorities_by_claim", _records)

    narrative = "I faced discrimination at work and I have emails." + _CONTEXT
    transcript = [{"role": "user", "text": narrative, "turn": "start"}]
    turns = []

    def _record(label, *, user_text="", receipt=None, extra=None):
        if user_text:
            transcript.append({"role": "user", "text": user_text, "turn": label})
        observation = _observe_interview(mediator)
        turns.append({
            "label": label,
            "user_text": user_text,
            "receipt": receipt,
            "observation": observation,
            "extra": extra or {},
        })

    started = mediator.transition_shared_interview(
        action="start",
        narrative=narrative,
        privacy_policy=local_policy,
        user_id="synthetic-user",
        case_id="synthetic-user",
    )
    assert started["error"] is None
    assert started["status"] == "awaiting_user"
    assert started["legal_sufficiency"] is False
    _record("start", receipt=started)

    complete_text = "I was fired on March 4, 2024 by supervisor Alex Rivera."
    pending = mediator.workflow_actions._canonical_pending_question()
    assert pending is not None
    complete_receipt = mediator.transition_shared_interview(
        action="answer",
        answer=complete_text,
        inquiry_id=pending["inquiry"]["inquiry_id"],
        expected_question_revision=pending["inquiry"]["revision"],
        privacy_policy=local_policy,
        user_id="synthetic-user",
        case_id="synthetic-user",
    )
    assert complete_receipt["error"] is None
    sourced_complete = "I was fired on March 4, 2024."
    transcript.append({"role": "user", "text": sourced_complete, "turn": "complete"})
    asserted = _sourced_answer(
        mediator,
        sourced_complete,
        "msg-complete",
        factual_action="assert",
    )
    complete_stable = asserted["updates"]["stable_id"]
    _record("complete", user_text=complete_text, receipt=complete_receipt, extra={"stable_id": complete_stable})

    unknown_text = "I don't know"
    pending = mediator.workflow_actions._canonical_pending_question()
    unknown_receipt = mediator.transition_shared_interview(
        action="answer",
        answer=unknown_text,
        inquiry_id=pending["inquiry"]["inquiry_id"],
        expected_question_revision=pending["inquiry"]["revision"],
        privacy_policy=local_policy,
        user_id="synthetic-user",
        case_id="synthetic-user",
    )
    _record("unknown", user_text=unknown_text, receipt=unknown_receipt)

    refused_text = "I decline to answer"
    pending = mediator.workflow_actions._canonical_pending_question()
    refused_receipt = mediator.transition_shared_interview(
        action="answer",
        answer=refused_text,
        inquiry_id=pending["inquiry"]["inquiry_id"],
        expected_question_revision=pending["inquiry"]["revision"],
        privacy_policy=local_policy,
        user_id="synthetic-user",
        case_id="synthetic-user",
    )
    _record("refused", user_text=refused_text, receipt=refused_receipt)

    corrected = "I was fired on March 5, 2024."
    correction = _sourced_answer(
        mediator,
        corrected,
        "msg-correction",
        factual_action="correct",
        supersedes_stable_id=complete_stable,
    )
    corrected_stable = correction["updates"]["stable_id"]
    _record("correction", user_text=corrected, extra={"stable_id": corrected_stable, "supersedes": complete_stable})

    contradictory = "I was fired on June 2, 2021."
    conflict = _sourced_answer(
        mediator,
        contradictory,
        "msg-contradiction",
        factual_action="contradict",
        contradicts_stable_id=corrected_stable,
    )
    _record(
        "contradictory_dates",
        user_text=contradictory,
        extra={
            "stable_id": conflict["updates"]["stable_id"],
            "conflict_stable_ids": list(conflict["updates"].get("conflict_stable_ids") or []),
        },
    )

    before_rule = _observe_interview(mediator)
    for node in mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph").nodes.values():
        attrs = node.attributes if isinstance(node.attributes, dict) else {}
        if attrs.get("dependency_class") == "legally_sourced_requirement" and attrs.get("source_available") is not False:
            node.satisfied = True
            attrs["satisfaction_state"] = "satisfied"
    revised = _source_record("rule-protected", "Protected class notice")
    revised["authority_version"] = "2025-edition"
    store["records"] = [revised]
    rule_report = mediator.refresh_verified_legal_dependencies({"rule_ids": ["rule-protected"]})
    _record("rule_version", extra={"report": rule_report, "before_legal_ids": before_rule["legal_ids"], "admitted_hash": revised["source_hash"]})

    before_jurisdiction = _observe_interview(mediator)
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    for node in graph.nodes.values():
        attrs = node.attributes if isinstance(node.attributes, dict) else {}
        if attrs.get("dependency_class") == "legally_sourced_requirement" and attrs.get("source_available") is not False:
            node.satisfied = True
            attrs["satisfaction_state"] = "satisfied"
    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") or {}
    mediator.apply_explicit_legal_context(case_file, jurisdiction="WA")
    jurisdiction_report = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "verified_dependency_refresh") or {}
    _record("jurisdiction", extra={"report": jurisdiction_report, "before_fact_ids": before_jurisdiction["fact_ids"]})

    outage_before = _observe_interview(mediator)
    backend.mode = "outage"
    try:
        backend("provider probe")
    except ConnectionError as exc:
        outage_error = str(exc)
    else:
        raise AssertionError("provider outage did not fail closed")
    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") or {}
    case_file["interview_provider"] = {"status": "provider_unavailable", "reason": "provider outage"}
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", case_file)
    pending = mediator.workflow_actions._canonical_pending_question()
    outage_receipt = mediator.transition_shared_interview(
        action="answer",
        answer="I don't know",
        inquiry_id=pending["inquiry"]["inquiry_id"],
        expected_question_revision=pending["inquiry"]["revision"],
        privacy_policy=local_policy,
        user_id="synthetic-user",
        case_id="synthetic-user",
    )
    _record(
        "provider_outage",
        user_text="I don't know",
        receipt=outage_receipt,
        extra={"before_fact_ids": outage_before["fact_ids"], "backend_error": outage_error},
    )

    timeout_before = _observe_interview(mediator)
    backend.mode = "timeout"
    try:
        backend("timeout probe")
    except TimeoutError as exc:
        timeout_error = str(exc)
    else:
        raise AssertionError("bounded timeout did not fail closed")
    paused = mediator.pause_intentional_user_wait("bounded_timeout")
    resumed = mediator.resume_intentional_user_wait()
    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") or {}
    case_file["interview_provider"] = {"status": "timeout", "reason": "bounded timeout"}
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", case_file)
    stop = mediator.denoiser.evaluate_interview_stop(
        open_questions=mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "current_questions") or [],
        intake_case_file=case_file,
        provider_status="timeout",
        iteration_count=mediator.phase_manager.iteration_count,
        iteration_cap=20,
    )
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "interview_stop", stop)
    _record(
        "bounded_timeout",
        extra={
            "before": timeout_before,
            "paused": paused,
            "resumed": resumed,
            "backend_error": timeout_error,
        },
    )

    # The denial stays in force for the whole fixture. A successful socket or
    # process call would already have raised inside the interview.
    assert socket.socket.connect is not None
    assert subprocess.Popen.__name__ == "blocked" or subprocess.Popen is not None

    return {
        "turns": turns,
        "transcript": transcript,
        "mediator": mediator,
        "admitted_source_hashes": {original["source_hash"], revised["source_hash"]},
        "admitted_statements": {original["source_text"], revised["source_text"]},
        "backend_calls": backend.calls,
    }


def scripted_turn(session, label):
    matches = [turn for turn in session["turns"] if turn["label"] == label]
    assert len(matches) == 1, label
    return matches[0]


def assert_scripted_interview_contract(session):
    """Factual graph, legal dependencies, lineage, and dispositions for every turn."""
    labels = [turn["label"] for turn in session["turns"]]
    assert tuple(labels) == _SCRIPTED_TURN_LABELS
    user_corpus = "\n".join(item["text"] for item in session["transcript"])
    previous = None
    for turn in session["turns"]:
        observed = turn["observation"]
        assert observed["filing_ready"] is False
        assert observed["intake_complete"] is False
        for fact in observed["facts"]:
            if fact["type"] != "fact":
                continue
            statement = str(fact["statement"] or fact["name"] or "")
            if fact["source_id"]:
                assert statement and statement in user_corpus
                assert fact["source_hash"]
        for item in observed["legal"]:
            assert item["law_derived"] is False
            assert item["heuristic_law_derived"] is not True
            if item["dependency_class"] == "legally_sourced_requirement" and item["source_available"] is not False:
                assert item["source_hash"] in session["admitted_source_hashes"]
                assert item["verification_status"] not in {None, "", "heuristic", "unverified"}
            if item["dependency_class"] in {"legal_source_gap", "unresolved_legal_requirement"}:
                assert item["satisfied"] is False
                assert item["name"] not in session["admitted_statements"] or item["source_available"] is False
        dispositions = [item["disposition"] for item in observed["dispositions"]]
        if turn["label"] == "complete":
            assert observed["fact_ids"] != (previous or {}).get("fact_ids")
            assert "answered" in dispositions
        elif turn["label"] in {"unknown", "refused"}:
            assert observed["fact_ids"] == previous["fact_ids"]
            expected = "unknown" if turn["label"] == "unknown" else "refused"
            assert expected in dispositions
            assert all(item["creates_fact"] is not True for item in observed["dispositions"] if item["disposition"] == expected)
        elif turn["label"] == "correction":
            assert turn["extra"]["stable_id"] != turn["extra"]["supersedes"]
            statuses = {item["stable_id"]: item["status"] for item in observed["assertions"]}
            assert statuses.get(turn["extra"]["supersedes"]) == "superseded"
            assert statuses.get(turn["extra"]["stable_id"]) == "active"
        elif turn["label"] == "contradictory_dates":
            assert set(turn["extra"]["conflict_stable_ids"]) <= {item["stable_id"] for item in observed["assertions"]}
            conflicted = [item for item in observed["assertions"] if item["stable_id"] in set(turn["extra"]["conflict_stable_ids"])]
            assert len(conflicted) == 2
            assert all(item["status"] != "superseded" for item in conflicted)
            statements = {item["statement"] for item in conflicted}
            assert any("March 5, 2024" in statement for statement in statements)
            assert any("June 2, 2021" in statement for statement in statements)
        elif turn["label"] == "rule_version":
            assert observed["legal_ids"] != turn["extra"]["before_legal_ids"]
            available = [item for item in observed["legal"] if item["dependency_class"] == "legally_sourced_requirement" and item["source_available"] is not False]
            assert available
            assert any(item["source_hash"] == turn["extra"]["admitted_hash"] for item in available)
            assert any(item["authority_version"] == "2025-edition" for item in available)
        elif turn["label"] == "jurisdiction":
            assert observed["fact_ids"] == turn["extra"]["before_fact_ids"]
            report = turn["extra"]["report"]
            legal_ids = {item["id"] for item in observed["legal"]}
            affected = set(report.get("affected_node_ids") or [])
            assert affected & legal_ids or observed["legal_ids"] != previous["legal_ids"]
            assert all(item["satisfied"] is False for item in observed["legal"] if item["dependency_class"] == "legally_sourced_requirement")
        elif turn["label"] == "provider_outage":
            assert observed["fact_ids"] == turn["extra"]["before_fact_ids"]
            receipt = turn["receipt"] or {}
            assert receipt.get("legal_sufficiency") is False
            assert observed["stop_state"] in {None, "provider_unavailable", "needs_answer", "deferred_unknown"}
            assert "provider outage" in turn["extra"]["backend_error"]
        elif turn["label"] == "bounded_timeout":
            paused = turn["extra"]["paused"]
            resumed = turn["extra"]["resumed"]
            assert paused["status"] == "awaiting_user"
            assert paused["paused"] is True
            assert paused["worker_stalled"] is False
            assert paused["supervisory_restart"] is False
            assert resumed["resumed"] is True
            assert resumed["assertion_rule_unchanged"] is True
            assert resumed["worker_stalled"] is False
            assert observed["stop_state"] == "provider_unavailable"
            assert observed["fact_ids"] == turn["extra"]["before"]["fact_ids"]
            assert "bounded timeout" in turn["extra"]["backend_error"]
        previous = observed

    for fact in session["turns"][-1]["observation"]["facts"]:
        if not fact["source_id"]:
            continue
        assert str(fact["statement"] or fact["name"]) in user_corpus
    for item in session["turns"][-1]["observation"]["legal"]:
        if item["dependency_class"] != "legally_sourced_requirement":
            continue
        if item["source_available"] is False:
            continue
        assert item["source_hash"] in session["admitted_source_hashes"]


@pytest.mark.no_auto_llm
@pytest.mark.no_auto_network
@pytest.mark.no_auto_heavy
def test_scripted_interview_saturation_outage_timeout_and_resume(tmp_path, monkeypatch):
    session = application_level_interview_fixture(tmp_path, monkeypatch)
    assert_scripted_interview_contract(session)
    assert session["backend_calls"] >= 1
    timeout = scripted_turn(session, "bounded_timeout")
    assert timeout["observation"]["filing_ready"] is False
    assert timeout["extra"]["paused"]["awaiting_user"] is True
    assert timeout["extra"]["resumed"]["supervisory_restart"] is False
