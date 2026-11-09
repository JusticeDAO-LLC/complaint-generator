"""Finite interview stops must name a truthful outcome and a resumable next step.

Saturation means no further answerable question is waiting. It does not mean
the facts, proof requirements, or legal elements are satisfied.
"""

from complaint_phases.denoiser import ComplaintDenoiser, project_stopping_policy
from complaint_phases.phase_manager import ComplaintPhase, PhaseManager
from applications.complaint_workspace import _workspace_stopping_policy
from mediator.mediator import Mediator


def _question(denoiser, target_id, text="What date do you recall?"):
    return denoiser._bind_unresolved_target(denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text=text,
        context={"requirement_id": target_id, "target_revision": "scope-a"},
        priority="high",
    ))


def _assert_not_legally_complete(stop):
    summary = stop["unresolved_issue_summary"]
    assert stop["legal_sufficiency"] is False
    assert stop["filing_ready"] is False
    assert stop["core_facts_complete"] is False
    assert stop["proof_requirements_satisfied"] is False
    assert summary["legal_sufficiency"] is False
    assert summary["core_facts_complete"] is False
    assert summary["proof_requirements_satisfied"] is False
    assert stop["remaining_issues"]
    assert stop["resumable_next_action"]["resumable"] is True
    assert stop["resumable_next_action"]["worker_stalled"] is False


def test_loss_plateau_question_cap_and_empty_pool_do_not_satisfy_legal_requirements():
    denoiser = ComplaintDenoiser()
    denoiser.questions_pool.clear()
    denoiser.questions_asked.extend({"question": {"question": "q"}} for _ in range(51))
    capped = denoiser.evaluate_interview_stop(open_questions=[], loss_converged=True, pool_empty=True)
    assert capped["state"] == "limit_reached"
    assert capped["outcome"] == "no_progress"
    assert capped["intake_complete"] is False
    _assert_not_legally_complete(capped)
    assert "question_count_limit" in capped["unresolved_issue_summary"]["rejected_shortcuts"]
    assert "loss_convergence" in capped["unresolved_issue_summary"]["rejected_shortcuts"]

    fresh = ComplaintDenoiser()
    plateau = fresh.evaluate_interview_stop(open_questions=[], loss_converged=True, pool_empty=True)
    assert plateau["state"] == "needs_answer"
    assert plateau["outcome"] == "no_progress"
    assert plateau["intake_complete"] is False
    _assert_not_legally_complete(plateau)
    assert fresh.is_exhausted() is False


def test_saturated_and_complete_do_not_claim_legal_sufficiency():
    denoiser = ComplaintDenoiser()
    answered = _question(denoiser, "req-protected")
    other = _question(denoiser, "req-notice", "What document shows the notice date?")
    denoiser.record_question_disposition(answered, "March 1, 2024", disposition="answered")
    denoiser.record_question_disposition(other, "March 2, 2024", disposition="answered")
    complete = denoiser.evaluate_interview_stop(open_questions=[answered, other], pool_empty=True, loss_converged=True)
    assert complete["state"] == "saturated"
    assert complete["outcome"] == "complete"
    assert complete["targets_accounted_for"] is True
    _assert_not_legally_complete(complete)
    assert "legal sufficiency" in complete["message"]

    refused = ComplaintDenoiser()
    left = _question(refused, "req-protected")
    right = _question(refused, "req-notice", "What document shows the notice date?")
    refused.record_question_disposition(left, "March 1, 2024", disposition="answered")
    refused.record_question_disposition(right, "I decline", disposition="refused")
    saturated = refused.evaluate_interview_stop(open_questions=[left, right], pool_empty=True)
    assert saturated["outcome"] == "saturated"
    assert saturated["intake_complete"] is False
    _assert_not_legally_complete(saturated)
    assert any(item.get("disposition") == "refused" for item in saturated["remaining_issues"])


def test_unknown_only_session_never_claims_core_facts_are_complete():
    denoiser = ComplaintDenoiser()
    question = _question(denoiser, "req-protected")
    denoiser.record_question_disposition(question, "I don't know", disposition="unknown")
    stop = denoiser.evaluate_interview_stop(open_questions=[question], pool_empty=True)
    assert stop["state"] == "deferred_unknown"
    assert stop["outcome"] == "deferred_needs_evidence"
    assert stop["unresolved_issue_summary"]["core_facts_complete"] is False
    _assert_not_legally_complete(stop)
    assert stop["resumable_next_action"]["action"] == "collect_evidence_then_resume"


def test_pause_provider_review_and_bounds_are_distinct_outcomes():
    paused = project_stopping_policy({"state": "needs_answer"}, paused=True)
    assert paused["outcome"] == "paused"
    assert paused["resumable_next_action"]["action"] == "resume_when_user_returns"
    assert paused["resumable_next_action"]["worker_stalled"] is False

    denoiser = ComplaintDenoiser()
    question = _question(denoiser, "req-protected")
    blocked = denoiser.evaluate_interview_stop(open_questions=[question], provider_status="provider_unavailable")
    assert blocked["state"] == "provider_unavailable"
    assert blocked["outcome"] == "blocked_provider"
    _assert_not_legally_complete(blocked)

    review = denoiser.evaluate_interview_stop(
        open_questions=[],
        needs_review=True,
        contradictions=[{"reason": "dates conflict"}],
    )
    assert review["outcome"] == "needs_review"
    assert review["state"] == "needs_review"
    assert review["resumable_next_action"]["action"] == "manual_review_then_resume"

    spinning = ComplaintDenoiser()
    repeated = _question(spinning, "req-protected")
    for _ in range(3):
        spinning.record_question_disposition(repeated, "I don't know")
    for _ in range(2):
        spinning.note_model_retry("timeout")
    bounded = spinning.evaluate_interview_stop(open_questions=[repeated], pool_empty=True)
    assert bounded["outcome"] == "no_progress"
    assert bounded["state"] == "no_progress"
    assert bounded["intake_complete"] is False
    _assert_not_legally_complete(bounded)
    shortcuts = set(bounded["unresolved_issue_summary"]["rejected_shortcuts"])
    assert "repeat_attempt_bound" in shortcuts
    assert "no_information_bound" in shortcuts
    assert "model_retry_bound" in shortcuts
    assert bounded["resumable_next_action"]["action"] == "review_unresolved_issues_then_resume"


def test_phase_manager_and_mediator_surface_the_same_policy():
    phase_manager = PhaseManager()
    phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intentional_user_wait", {
        "paused": True,
        "intentional": True,
        "awaiting_user": True,
    })
    paused_action = phase_manager.get_next_action()
    assert paused_action["action"] == "awaiting_user"
    assert paused_action["outcome"] == "paused"
    assert paused_action["worker_stalled"] is False
    assert paused_action["core_facts_complete"] is False

    phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intentional_user_wait", {})
    phase_manager.update_phase_data(ComplaintPhase.INTAKE, "interview_stop", {
        "state": "provider_unavailable",
        "outcome": "blocked_provider",
        "intake_complete": False,
        "filing_ready": False,
        "legal_sufficiency": False,
        "message": "backend down",
        "remaining_issues": [{"reason": "backend"}],
        "resumable_next_action": {"action": "retry_when_provider_available", "resumable": True, "worker_stalled": False},
        "unresolved_issue_summary": {
            "items": [{"reason": "backend"}],
            "legal_sufficiency": False,
            "core_facts_complete": False,
        },
    })
    blocked = phase_manager.get_next_action()
    assert blocked["action"] == "provider_unavailable"
    assert blocked["outcome"] == "blocked_provider"
    assert phase_manager.is_phase_complete(ComplaintPhase.INTAKE) is False

    host = type("Host", (), {"phase_manager": phase_manager})()
    policy = Mediator._current_stopping_policy(host)
    assert policy["outcome"] == "blocked_provider"
    assert policy["legal_sufficiency"] is False
    assert policy["filing_ready"] is False


def test_workspace_empty_question_list_is_saturation_not_core_fact_completion():
    answers = {
        "party_name": "Ada",
        "opposing_party": "Example Agency",
        "protected_activity": "reported a hazard",
        "adverse_action": "suspended",
        "timeline": "March 2024",
        "harm": "lost wages",
        "court_header": "unsure",
    }
    policy = _workspace_stopping_policy({"intentional_user_wait": {}}, active_question=None, answers=answers)
    assert policy["outcome"] == "saturated"
    assert policy["legal_sufficiency"] is False
    assert policy["core_facts_complete"] is False
    assert policy["proof_requirements_satisfied"] is False
    assert policy["filing_ready"] is False
    assert policy["resumable_next_action"]["resumable"] is True

    unknown = {key: "I don't know" for key in answers}
    deferred = _workspace_stopping_policy({}, active_question=None, answers=unknown)
    assert deferred["outcome"] == "deferred_needs_evidence"
    assert deferred["core_facts_complete"] is False

    waiting = _workspace_stopping_policy({}, active_question={"id": "timeline"}, answers={})
    assert waiting["outcome"] == "awaiting_user"
