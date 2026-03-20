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
    assert task.metadata["report_summary"]["workflow_phase_plan"]["recommended_order"]
    assert task.metadata["report_summary"]["workflow_phase_plan"]["phases"]["intake_questioning"]["status"] in {
        "critical",
        "warning",
    }
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


def test_analyze_builds_workflow_phase_plan_for_intake_graph_and_document_steps():
    optimizer = Optimizer()
    result = _session_result(
        "session_phase_plan",
        0.58,
        {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["documents", "harm_remedy", "timeline"],
                "covered_objectives": ["timeline"],
                "uncovered_objectives": ["documents", "harm_remedy"],
            }
        },
    )
    result.knowledge_graph_summary = {"total_entities": 0, "total_relationships": 0, "gaps": 4}
    result.dependency_graph_summary = {"total_nodes": 0, "total_dependencies": 0, "satisfaction_rate": 0.0}

    report = optimizer.analyze([result])

    phase_plan = report.workflow_phase_plan
    assert phase_plan["recommended_order"]
    assert phase_plan["phases"]["intake_questioning"]["status"] == "critical"
    assert phase_plan["phases"]["graph_analysis"]["status"] == "critical"
    assert phase_plan["phases"]["document_generation"]["status"] in {"critical", "warning"}
    assert "document_pipeline.py" in phase_plan["phases"]["document_generation"]["target_files"]
    assert any(
        action["focus"] == "exhibit_collection"
        for action in phase_plan["phases"]["document_generation"]["recommended_actions"]
    )


def test_build_phase_patch_tasks_emits_all_workflow_steps_by_default():
    optimizer = Optimizer()
    result = _session_result(
        "session_phase_tasks",
        0.58,
        {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["documents", "harm_remedy", "timeline"],
                "covered_objectives": ["timeline"],
                "uncovered_objectives": ["documents", "harm_remedy"],
            }
        },
    )
    result.knowledge_graph_summary = {"total_entities": 0, "total_relationships": 0, "gaps": 4}
    result.dependency_graph_summary = {"total_nodes": 0, "total_dependencies": 0, "satisfaction_rate": 0.0}

    tasks, report = optimizer.build_phase_patch_tasks(
        [result],
        method="actor_critic",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
    )

    ordered_names = report.workflow_phase_plan["recommended_order"]
    emitted_names = [task.metadata["workflow_phase"] for task in tasks]

    assert emitted_names == ordered_names
    assert any("document_pipeline.py" in [str(path) for path in task.target_files] for task in tasks)
    assert all(task.method == "ACTOR_CRITIC" for task in tasks)
    intake_task = next(task for task in tasks if task.metadata["workflow_phase"] == "intake_questioning")
    graph_task = next(task for task in tasks if task.metadata["workflow_phase"] == "graph_analysis")
    document_task = next(task for task in tasks if task.metadata["workflow_phase"] == "document_generation")
    assert "target_symbols" in intake_task.constraints
    assert any(path.endswith("session.py") for path in intake_task.constraints["target_symbols"])
    assert "workflow_capabilities" in intake_task.metadata
    assert "complainant_prompting" in intake_task.metadata["workflow_capabilities"]
    assert "target_symbols" in graph_task.constraints
    assert any(path.endswith("knowledge_graph.py") for path in graph_task.constraints["target_symbols"])
    assert "workflow_capabilities" in graph_task.metadata
    assert "knowledge_graph_population" in graph_task.metadata["workflow_capabilities"]
    assert "target_symbols" in document_task.constraints
    assert any(path.endswith("document_pipeline.py") for path in document_task.constraints["target_symbols"])
    assert "document_optimization" in document_task.metadata["workflow_capabilities"]


def test_build_phase_patch_tasks_can_skip_ready_workflow_steps():
    optimizer = Optimizer()
    result = _session_result(
        "session_phase_tasks_skip_ready",
        0.58,
        {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["documents", "harm_remedy", "timeline"],
                "covered_objectives": ["timeline"],
                "uncovered_objectives": ["documents", "harm_remedy"],
            }
        },
    )
    result.knowledge_graph_summary = {"total_entities": 0, "total_relationships": 0, "gaps": 4}
    result.dependency_graph_summary = {"total_nodes": 0, "total_dependencies": 0, "satisfaction_rate": 0.0}

    tasks, report = optimizer.build_phase_patch_tasks(
        [result],
        method="actor_critic",
        include_ready_phases=False,
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
    )

    ordered_names = report.workflow_phase_plan["recommended_order"]
    emitted_names = [task.metadata["workflow_phase"] for task in tasks]

    assert emitted_names == [
        phase_name
        for phase_name in ordered_names
        if report.workflow_phase_plan["phases"][phase_name]["status"] != "ready"
    ]


def test_build_workflow_optimization_bundle_exposes_all_phases():
    optimizer = Optimizer()
    result = _session_result(
        "session_workflow_bundle",
        0.55,
        {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["documents", "harm_remedy", "timeline"],
                "covered_objectives": ["timeline"],
                "uncovered_objectives": ["documents", "harm_remedy"],
            }
        },
    )
    result.knowledge_graph_summary = {"total_entities": 0, "total_relationships": 0, "gaps": 5}
    result.dependency_graph_summary = {"total_nodes": 1, "total_dependencies": 0, "satisfaction_rate": 0.0}

    bundle, report = optimizer.build_workflow_optimization_bundle(
        [result],
        method="actor_critic",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
    )

    payload = bundle.to_dict()
    assert report.workflow_phase_plan["recommended_order"] == payload["workflow_phase_plan"]["recommended_order"]
    assert payload["global_objectives"]
    assert len(payload["phase_tasks"]) == 3
    phase_names = [task["metadata"]["workflow_phase"] for task in payload["phase_tasks"]]
    assert phase_names == report.workflow_phase_plan["recommended_order"]
    assert [task["phase_name"] for task in payload["phase_tasks"]] == report.workflow_phase_plan["recommended_order"]
    assert any(
        "scripts/synthesize_hacc_complaint.py" in task["target_files"]
        for task in payload["phase_tasks"]
        if task["metadata"]["workflow_phase"] == "document_generation"
    )
    assert "coverage_remediation" in payload["shared_context"]
    assert "complaint_type_performance" in payload["shared_context"]
    assert "evidence_modality_performance" in payload["shared_context"]


def test_analyze_tracks_complaint_type_and_evidence_modality_performance():
    optimizer = Optimizer()

    policy_result = _session_result(
        "session_policy",
        0.62,
        {"adversarial_intake_priority_summary": {}},
    )
    policy_result.seed_complaint = {
        "type": "policy_grievance",
        "_meta": {"complaint_type": "housing_discrimination"},
        "key_facts": {
            "grounded_evidence_summary": "Grounded grievance support.",
            "matched_rules": [{"rule": "Some policy rule"}],
            "repository_evidence_candidates": [
                {"title": "ADMINISTRATIVE PLAN", "source_path": "/tmp/admin_plan.pdf", "snippet": "Notice language."}
            ],
        },
    }

    image_result = _session_result(
        "session_image",
        0.41,
        {"adversarial_intake_priority_summary": {}},
    )
    image_result.seed_complaint = {
        "type": "narrative_intake",
        "_meta": {"complaint_type": "retaliation"},
        "key_facts": {
            "repository_evidence_candidates": [
                {"title": "Photo evidence", "source_path": "/tmp/photo.jpg", "snippet": "Apartment condition photo."}
            ],
        },
    }

    report = optimizer.analyze([policy_result, image_result])

    assert "housing_discrimination" in report.complaint_type_performance
    assert "retaliation" in report.complaint_type_performance
    assert "uploaded_document" in report.evidence_modality_performance
    assert "image_evidence" in report.evidence_modality_performance
    assert any("complaint types" in recommendation for recommendation in report.recommendations)
    assert any("evidence modalities" in recommendation for recommendation in report.recommendations)


def test_analyze_without_successful_sessions_returns_critical_workflow_phase_plan():
    optimizer = Optimizer()
    result = _session_result("session_failed", 0.18, {})
    result.success = False

    report = optimizer.analyze([result])

    assert report.num_sessions_analyzed == 0
    assert report.common_weaknesses == ["All sessions failed"]
    assert report.workflow_phase_plan["recommended_order"] == [
        "intake_questioning",
        "graph_analysis",
        "document_generation",
    ]
    assert report.workflow_phase_plan["phases"]["intake_questioning"]["status"] == "critical"
    assert report.workflow_phase_plan["phases"]["graph_analysis"]["status"] == "critical"
    assert report.workflow_phase_plan["phases"]["document_generation"]["status"] == "critical"


def test_run_agentic_autopatch_caches_inner_generation_diagnostics_on_failure():
    optimizer = Optimizer()
    results = [_session_result("session_1", 0.72, {})]

    class FailingAgenticOptimizer:
        def __init__(self, *, agent_id, llm_router):
            self.agent_id = agent_id
            self.llm_router = llm_router
            self._last_generation_diagnostics = [
                {
                    "file": "mediator/inquiries.py",
                    "status": "error",
                    "mode": "symbol_level",
                    "error_message": "unexpected indent (<unknown>, line 3)",
                }
            ]

        def optimize(self, task):
            raise ValueError("unexpected indent (<unknown>, line 3)")

    optimizer._load_agentic_optimizer_components = lambda: {
        "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
        "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
        "OptimizerLLMRouter": lambda **kwargs: SimpleNamespace(**kwargs),
        "optimizer_classes": {"actor_critic": FailingAgenticOptimizer},
    }

    with pytest.raises(RuntimeError, match="generation diagnostics:"):
        optimizer.run_agentic_autopatch(
            results,
            target_files=["mediator/mediator.py"],
            method="actor_critic",
        )

    assert optimizer._last_agentic_generation_diagnostics == [
        {
            "file": "mediator/inquiries.py",
            "status": "error",
            "mode": "symbol_level",
            "error_message": "unexpected indent (<unknown>, line 3)",
        }
    ]
