from pathlib import Path
from types import SimpleNamespace

import pytest

from adversarial_harness import CriticScore, OptimizationReport, Optimizer, SessionResult


def _session_result(session_id, overall_score, final_state):
    return SessionResult(
        session_id=session_id,
        timestamp="2024-01-01",
        seed_complaint={},
        initial_complaint_text="Test",
        conversation_history=[],
        num_questions=3,
        num_turns=2,
        final_state=final_state,
        critic_score=CriticScore(
            overall_score=overall_score,
            question_quality=overall_score,
            information_extraction=overall_score,
            empathy=overall_score,
            efficiency=overall_score,
            coverage=overall_score,
            feedback="Test feedback",
            strengths=[],
            weaknesses=[],
            suggestions=[],
        ),
        success=True,
    )


def test_top_uncovered_intake_objectives_prefers_low_coverage_then_frequency():
    report = OptimizationReport(
        timestamp="2024-01-01T00:00:00+00:00",
        num_sessions_analyzed=2,
        average_score=0.7,
        score_trend="stable",
        question_quality_avg=0.7,
        information_extraction_avg=0.7,
        empathy_avg=0.7,
        efficiency_avg=0.7,
        coverage_avg=0.7,
        common_weaknesses=[],
        common_strengths=[],
        recommendations=[],
        priority_improvements=[],
        intake_priority_performance={
            "coverage_by_objective": {
                "documents": {"expected": 2, "covered": 0, "uncovered": 2, "coverage_rate": 0.0},
                "timeline": {"expected": 3, "covered": 1, "uncovered": 2, "coverage_rate": 1 / 3},
                "actors": {"expected": 1, "covered": 1, "uncovered": 0, "coverage_rate": 1.0},
            }
        },
    )

    assert Optimizer._top_uncovered_intake_objectives(report) == ["documents", "timeline"]


def test_build_agentic_patch_task_includes_intake_priority_summary():
    optimizer = Optimizer()
    results = [
        _session_result(
            "session_1",
            0.72,
            {
                "adversarial_intake_priority_summary": {
                    "expected_objectives": ["timeline", "documents", "harm_remedy"],
                    "covered_objectives": ["timeline"],
                    "uncovered_objectives": ["documents", "harm_remedy"],
                }
            },
        ),
        _session_result(
            "session_2",
            0.66,
            {
                "adversarial_intake_priority_summary": {
                    "expected_objectives": ["timeline", "documents"],
                    "covered_objectives": [],
                    "uncovered_objectives": ["timeline", "documents"],
                }
            },
        ),
    ]

    task, report = optimizer.build_agentic_patch_task(
        results,
        target_files=["adversarial_harness/session.py"],
        method="actor_critic",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
    )

    assert report.intake_priority_performance["coverage_by_objective"]["documents"]["coverage_rate"] == 0.0
    assert task.method == "ACTOR_CRITIC"
    assert task.target_files == [Path("adversarial_harness/session.py")]
    assert "documents, harm_remedy, timeline" in task.description
    assert task.metadata["report_summary"]["weakest_intake_objectives"] == ["documents", "harm_remedy", "timeline"]
    assert task.metadata["report_summary"]["sessions_with_full_intake_coverage"] == 0
    assert task.metadata["report_summary"]["recommended_target_files"] == [
        "adversarial_harness/session.py",
        "mediator/mediator.py",
        "adversarial_harness/complainant.py",
    ]
    assert "recommendations" in task.metadata["report_summary"]


def test_build_agentic_patch_task_can_autoselect_targets_from_intake_gaps():
    optimizer = Optimizer()
    results = [
        _session_result(
            "session_auto",
            0.61,
            {
                "adversarial_intake_priority_summary": {
                    "expected_objectives": ["actors", "anchor_appeal_rights"],
                    "covered_objectives": [],
                    "uncovered_objectives": ["actors", "anchor_appeal_rights"],
                }
            },
        )
    ]

    task, report = optimizer.build_agentic_patch_task(
        results,
        target_files=[],
        method="actor_critic",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
    )

    assert report.intake_priority_performance["coverage_by_objective"]["actors"]["coverage_rate"] == 0.0
    assert task.target_files == [
        Path("adversarial_harness/session.py"),
        Path("mediator/mediator.py"),
        Path("adversarial_harness/complainant.py"),
    ]
    assert "Target files: adversarial_harness/session.py, mediator/mediator.py, adversarial_harness/complainant.py." in task.description
