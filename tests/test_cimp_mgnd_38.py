"""Finite source, evidence, and review actions after interview saturation.

Synthetic private fixtures only. Shortcuts and a completed hook do not prove
the complaint. A stalled worker is not an awaiting-user session.
"""

from __future__ import annotations

import pytest

from applications.complaint_workspace import publish_workspace_dependency_action
from complaint_phases.denoiser import ComplaintDenoiser
from mediator.workflow_service import WorkflowActionService

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def _cases():
    return (
        "six-stopping-distinctions",
        "shortcuts-are-not-sufficiency",
        "saturated-questions-publish-one-bounded-action",
        "attempt-budget-and-stalled-worker-terminate",
        "workspace-resumes-the-same-action",
        "missing-denoiser-stays-unavailable",
    )


def _question(denoiser, target_id, text="What date do you recall?"):
    return denoiser._bind_unresolved_target(denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text=text,
        context={"requirement_id": target_id, "target_revision": "scope-a"},
        priority="high",
    ))


def _dependency(lane, target_id):
    return {
        "target_id": target_id,
        "target_revision": "rev-1",
        "lane": lane,
        "kind": lane,
    }


def _assert_not_sufficient(stop):
    assert stop["legal_sufficiency"] is False
    assert stop["core_facts_complete"] is False
    assert stop["proof_requirements_satisfied"] is False
    assert stop["filing_ready"] is False
    assert stop["busy_loop"] is False
    assert stop["reads_developer_stdin"] is False


def _service(denoiser=None):
    mediator = type("Mediator", (), {})()
    mediator.denoiser = ComplaintDenoiser() if denoiser is None else denoiser
    return WorkflowActionService(mediator), mediator.denoiser


def test_case_list_is_nonempty():
    assert len(_cases()) >= 6


def test_stopping_distinctions_reuse_existing_outcomes():
    denoiser = ComplaintDenoiser()
    waiting = _question(denoiser, "req-date")
    user = denoiser.evaluate_interview_stop(open_questions=[waiting])
    assert user["outcome"] == "awaiting_user"
    assert user["stopping_distinction"] == "awaiting_user"
    assert user["awaiting_user"] is True
    assert user["worker_stalled"] is False

    answered = ComplaintDenoiser()
    question = _question(answered, "req-date")
    answered.record_question_disposition(question, "March 1, 2024", disposition="answered")
    source = answered.evaluate_interview_stop(
        open_questions=[question],
        pool_empty=True,
        open_dependencies=[_dependency("legal_source", "dep-statute")],
    )
    evidence = answered.evaluate_interview_stop(
        open_questions=[question],
        pool_empty=True,
        open_dependencies=[_dependency("evidence", "dep-notice")],
    )
    review = answered.evaluate_interview_stop(
        open_questions=[question],
        pool_empty=True,
        open_dependencies=[_dependency("review", "dep-conflict")],
    )
    blocked = denoiser.evaluate_interview_stop(open_questions=[waiting], provider_status="provider_unavailable")
    stalled = denoiser.evaluate_interview_stop(open_questions=[waiting], worker_stalled=True)
    assert source["stopping_distinction"] == "source_research"
    assert source["outcome"] == "saturated"
    assert source["resumable_next_action"]["action"] == "acquire_legal_sources"
    assert evidence["stopping_distinction"] == "evidence_request"
    assert evidence["outcome"] == "deferred_needs_evidence"
    assert evidence["resumable_next_action"]["action"] == "ingest_private_evidence"
    assert review["stopping_distinction"] == "review"
    assert review["outcome"] == "needs_review"
    assert review["resumable_next_action"]["action"] == "refresh_grounding"
    assert blocked["stopping_distinction"] == "unavailable_provider"
    assert blocked["outcome"] == "blocked_provider"
    assert blocked["awaiting_user"] is False
    assert stalled["stopping_distinction"] == "no_progress"
    assert stalled["outcome"] == "no_progress"
    assert stalled["awaiting_user"] is False
    assert stalled["worker_stalled"] is True
    for stop in (user, source, evidence, review, blocked, stalled):
        _assert_not_sufficient(stop)


def test_shortcuts_cannot_establish_sufficiency():
    denoiser = ComplaintDenoiser()
    denoiser.questions_pool.clear()
    denoiser.questions_asked.extend({"question": {"question": "q"}} for _ in range(51))
    capped = denoiser.evaluate_interview_stop(open_questions=[], loss_converged=True, pool_empty=True)
    assert capped["outcome"] == "no_progress"
    assert "question_count_limit" in capped["unresolved_issue_summary"]["rejected_shortcuts"]
    assert "loss_convergence" in capped["unresolved_issue_summary"]["rejected_shortcuts"]
    assert "empty_question_list" in capped["unresolved_issue_summary"]["rejected_shortcuts"]
    _assert_not_sufficient(capped)

    fresh = ComplaintDenoiser()
    plateau = fresh.evaluate_interview_stop(
        open_questions=[],
        loss_converged=True,
        pool_empty=True,
        iteration_count=4,
        iteration_cap=4,
    )
    assert plateau["outcome"] == "no_progress"
    assert "iteration_cap" in plateau["unresolved_issue_summary"]["rejected_shortcuts"]
    _assert_not_sufficient(plateau)

    skipped = ComplaintDenoiser()
    question = _question(skipped, "req-date")
    skipped.record_question_disposition(question, "skip", disposition="skipped")
    unknown = skipped.evaluate_interview_stop(open_questions=[question], pool_empty=True, hook_completed=True)
    shortcuts = set(unknown["unresolved_issue_summary"]["rejected_shortcuts"])
    assert "skipped_or_unknown_answer" in shortcuts
    assert "completed_hook" in shortcuts
    assert unknown["intake_complete"] is False
    _assert_not_sufficient(unknown)


def test_saturated_questions_publish_a_concrete_bounded_action():
    service, denoiser = _service()
    question = _question(denoiser, "req-date")
    denoiser.record_question_disposition(question, "March 1, 2024", disposition="answered")
    context = {
        "case_id": "case-synthetic-38",
        "target_id": "dep-statute",
        "target_revision": "rev-1",
        "graph_revision": "graph-7",
        "session_revision": 2,
    }
    first = service.publish_finite_dependency_action(
        open_questions=[question],
        open_dependencies=[_dependency("legal_source", "dep-statute")],
        context=context,
        pool_empty=True,
        hook_completed=True,
    )
    assert first["status"] == "published"
    assert first["authorized"] is True
    assert first["published"] is True
    assert first["operation"] == "acquire_legal_sources"
    assert first["bounded"] is True
    assert first["attempt"] == 1
    assert first["max_attempts"] == 3
    assert first["resumable_context"]["case_id"] == "case-synthetic-38"
    assert first["resumable_context"]["graph_revision"] == "graph-7"
    assert first["resumable_context"]["attempt"] == 1
    assert first["hook_completed_is_sufficiency"] is False
    assert first["legal_sufficiency"] is False
    assert first["awaiting_user"] is False
    assert first["busy_loop"] is False
    assert first["reads_developer_stdin"] is False
    assert first["interview_stop"]["outcome"] == "saturated"

    still_open = service.publish_finite_dependency_action(
        open_questions=[_question(denoiser, "req-open")],
        open_dependencies=[_dependency("legal_source", "dep-statute")],
        context=context,
    )
    assert still_open["status"] == "withheld"
    assert still_open["authorized"] is False
    assert still_open["awaiting_user"] is True


def test_budget_and_attempt_bounds_terminate_without_a_user_wait():
    service, denoiser = _service()
    question = _question(denoiser, "req-date")
    denoiser.record_question_disposition(question, "March 1, 2024", disposition="answered")
    context = {"case_id": "case-synthetic-38", "target_id": "dep-notice"}
    published = []
    for _ in range(3):
        packet = service.publish_finite_dependency_action(
            open_questions=[question],
            open_dependencies=[_dependency("evidence", "dep-notice")],
            context=context,
            pool_empty=True,
        )
        published.append(packet)
    assert [item["status"] for item in published] == ["published", "published", "published"]
    assert [item["operation"] for item in published] == ["ingest_private_evidence"] * 3
    stopped = service.publish_finite_dependency_action(
        open_questions=[question],
        open_dependencies=[_dependency("evidence", "dep-notice")],
        context=context,
        pool_empty=True,
    )
    assert stopped["status"] == "terminated"
    assert stopped["published"] is False
    assert stopped["authorized"] is False
    assert stopped["operation_terminated"] is True
    assert stopped["awaiting_user"] is False
    assert stopped["reason"] == "attempt_bound"
    assert stopped["reads_developer_stdin"] is False
    assert stopped["busy_loop"] is False

    budget = service.publish_finite_dependency_action(
        open_questions=[_question(denoiser, "req-open")],
        budget_exhausted=True,
        context={"case_id": "case-budget", "target_id": "dep-statute"},
    )
    assert budget["status"] == "terminated"
    assert budget["awaiting_user"] is False
    assert budget["interview_stop"]["stopping_distinction"] == "no_progress"
    assert budget["legal_sufficiency"] is False

    stalled = service.publish_finite_dependency_action(
        open_questions=[_question(denoiser, "req-open")],
        worker_stalled=True,
        provider_status="stalled",
    )
    assert stalled["status"] == "terminated"
    assert stalled["awaiting_user"] is False
    assert stalled["worker_stalled"] is True


def test_workspace_publishes_resumable_review_action():
    state = {
        "open_dependencies": [_dependency("review", "dep-conflict")],
        "hook_completed": True,
        "dependency_action_context": {
            "case_id": "case-workspace-38",
            "target_id": "dep-conflict",
            "target_revision": "rev-1",
            "graph_revision": "graph-3",
            "session_revision": 4,
            "attempt": 1,
        },
    }
    packet = publish_workspace_dependency_action(state)
    assert packet["status"] == "published"
    assert packet["operation"] == "refresh_grounding"
    assert packet["authorized"] is True
    assert packet["attempt"] == 2
    assert packet["resumable_context"]["session_revision"] == 4
    assert packet["hook_completed_is_sufficiency"] is False
    assert packet["legal_sufficiency"] is False
    assert packet["reads_developer_stdin"] is False

    exhausted = publish_workspace_dependency_action({
        **state,
        "dependency_action_context": {**state["dependency_action_context"], "attempt": 3},
    })
    assert exhausted["status"] == "terminated"
    assert exhausted["published"] is False
    assert exhausted["awaiting_user"] is False


def test_missing_denoiser_is_an_unavailable_result():
    mediator = type("Mediator", (), {"denoiser": None})()
    service = WorkflowActionService(mediator)
    packet = service.publish_finite_dependency_action(
        open_dependencies=[_dependency("legal_source", "dep-statute")],
        context={"case_id": "case-missing"},
    )
    assert packet["status"] == "unavailable"
    assert packet["published"] is False
    assert packet["authorized"] is False
    assert packet["reason"] == "denoiser_unavailable"
    assert packet["legal_sufficiency"] is False
    assert packet["awaiting_user"] is False
    assert packet["busy_loop"] is False
    assert packet["reads_developer_stdin"] is False
