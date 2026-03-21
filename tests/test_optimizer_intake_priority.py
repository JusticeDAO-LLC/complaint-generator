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


def test_build_agentic_patch_task_adds_graph_and_document_targets_for_blocker_objectives():
    optimizer = Optimizer()
    results = [
        _session_result(
            "session_blockers",
            0.49,
            {
                "adversarial_intake_priority_summary": {
                    "expected_objectives": ["exact_dates", "staff_names_titles", "response_dates", "causation_sequence"],
                    "covered_objectives": [],
                    "uncovered_objectives": ["exact_dates", "staff_names_titles", "response_dates", "causation_sequence"],
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

    assert report.workflow_phase_plan['phases']['graph_analysis']['status'] in {'critical', 'warning'}
    assert task.target_files == [
        Path('adversarial_harness/session.py'),
        Path('mediator/mediator.py'),
        Path('complaint_phases/denoiser.py'),
        Path('document_optimization.py'),
    ]


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
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(
                ACTOR_CRITIC="ACTOR_CRITIC",
                TEST_DRIVEN="TEST_DRIVEN",
            ),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
    )

    ordered_names = report.workflow_phase_plan["recommended_order"]
    emitted_names = [task.metadata["workflow_phase"] for task in tasks]

    assert emitted_names == ordered_names
    assert any(
        any(name in [str(path) for path in task.target_files] for name in ("document_pipeline.py", "scripts/synthesize_hacc_complaint.py", "document_optimization.py"))
        for task in tasks
    )
    assert all(task.method == "TEST_DRIVEN" for task in tasks)
    intake_task = next(task for task in tasks if task.metadata["workflow_phase"] == "intake_questioning")
    graph_task = next(task for task in tasks if task.metadata["workflow_phase"] == "graph_analysis")
    document_task = next(task for task in tasks if task.metadata["workflow_phase"] == "document_generation")
    assert "target_symbols" in intake_task.constraints
    assert any(path.endswith("session.py") for path in intake_task.constraints["target_symbols"])
    session_symbols = next(
        symbols
        for path, symbols in intake_task.constraints["target_symbols"].items()
        if path.endswith("session.py")
    )
    assert session_symbols == ["_inject_intake_prompt_questions"]
    assert "workflow_capabilities" in intake_task.metadata
    assert "complainant_prompting" in intake_task.metadata["workflow_capabilities"]
    assert "target_symbols" in graph_task.constraints
    assert any(path.endswith("dependency_graph.py") for path in graph_task.constraints["target_symbols"])
    dependency_graph_symbols = next(
        symbols
        for path, symbols in graph_task.constraints["target_symbols"].items()
        if path.endswith("dependency_graph.py")
    )
    assert dependency_graph_symbols == ["get_claim_readiness"]
    assert "workflow_capabilities" in graph_task.metadata
    assert "knowledge_graph_population" in graph_task.metadata["workflow_capabilities"]
    assert "target_symbols" in document_task.constraints
    assert len(graph_task.target_files) == 1
    assert graph_task.target_files[0].name in {"dependency_graph.py", "denoiser.py"}
    assert "graph analysis phase" in graph_task.description
    assert "phase_signal_context" in graph_task.metadata
    assert "dg_avg_satisfaction_rate" in graph_task.metadata["phase_signal_context"]
    assert any(
        path.endswith("document_pipeline.py")
        or path.endswith("synthesize_hacc_complaint.py")
        or path.endswith("document_optimization.py")
        for path in document_task.constraints["target_symbols"]
    )
    document_optimization_symbols = [
        symbols
        for path, symbols in document_task.constraints["target_symbols"].items()
        if path.endswith("document_optimization.py")
    ]
    if document_optimization_symbols:
        assert document_optimization_symbols[0] == ["_build_workflow_phase_targeting"]
    assert len(document_task.target_files) == 1
    assert document_task.target_files[0].name == "document_optimization.py"
    assert document_task.metadata["workflow_phase_secondary_target_files"]
    assert "synthesize_hacc_complaint.py" in document_task.metadata["workflow_phase_secondary_target_files"][0]
    secondary_constraints = document_task.metadata["workflow_phase_secondary_constraints"]
    assert "target_symbols" in secondary_constraints
    assert any(path.endswith("synthesize_hacc_complaint.py") for path in secondary_constraints["target_symbols"])
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
        include_ready_phases=False,
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(
                ACTOR_CRITIC="ACTOR_CRITIC",
                TEST_DRIVEN="TEST_DRIVEN",
            ),
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
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(
                ACTOR_CRITIC="ACTOR_CRITIC",
                TEST_DRIVEN="TEST_DRIVEN",
            ),
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
        any(
            candidate in task["target_files"]
            for candidate in (
                "scripts/synthesize_hacc_complaint.py",
                "document_optimization.py",
                "document_pipeline.py",
            )
        )
        for task in payload["phase_tasks"]
        if task["metadata"]["workflow_phase"] == "document_generation"
    )
    assert "coverage_remediation" in payload["shared_context"]
    assert "complaint_type_performance" in payload["shared_context"]
    assert "evidence_modality_performance" in payload["shared_context"]
    assert "phase_scorecards" in payload["shared_context"]
    assert "document_handoff_summary" in payload["shared_context"]
    assert payload["shared_context"]["workflow_action_queue"]
    assert payload["phase_scorecards"]["document_generation"]["status"] in {"critical", "warning", "ready"}
    assert payload["cross_phase_findings"]
    assert all(task["method"] == "TEST_DRIVEN" for task in payload["phase_tasks"])
    assert payload["workflow_action_queue"]
    assert payload["workflow_action_queue"][0]["phase_name"] == report.workflow_phase_plan["recommended_order"][0]


def test_analyze_builds_cross_phase_scorecards_and_document_handoff_summary():
    optimizer = Optimizer()
    low_result = _session_result(
        "session_cross_phase",
        0.44,
        {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["documents", "harm_remedy", "timeline", "witnesses"],
                "covered_objectives": ["timeline"],
                "uncovered_objectives": ["documents", "harm_remedy", "witnesses"],
            }
        },
    )
    low_result.critic_score.question_quality = 0.41
    low_result.critic_score.information_extraction = 0.39
    low_result.critic_score.efficiency = 0.43
    low_result.critic_score.coverage = 0.37
    low_result.seed_complaint = {
        "type": "narrative_intake",
        "_meta": {"complaint_type": "retaliation"},
        "key_facts": {
            "repository_evidence_candidates": [
                {"title": "Photo evidence", "source_path": "/tmp/photo.jpg", "snippet": "Apartment condition photo."}
            ],
        },
    }
    low_result.knowledge_graph_summary = {"total_entities": 1, "total_relationships": 0, "gaps": 5}
    low_result.dependency_graph_summary = {"total_nodes": 1, "total_dependencies": 0, "satisfaction_rate": 0.0}

    strong_result = _session_result(
        "session_cross_phase_strong",
        0.78,
        {"adversarial_intake_priority_summary": {"expected_objectives": ["timeline"], "covered_objectives": ["timeline"], "uncovered_objectives": []}},
    )
    strong_result.seed_complaint = {
        "type": "policy_grievance",
        "_meta": {"complaint_type": "housing_discrimination"},
        "key_facts": {
            "repository_evidence_candidates": [
                {"title": "Administrative Plan", "source_path": "/tmp/admin_plan.pdf", "snippet": "Notice language."}
            ],
        },
    }
    strong_result.knowledge_graph_summary = {"total_entities": 4, "total_relationships": 3, "gaps": 1}
    strong_result.dependency_graph_summary = {"total_nodes": 4, "total_dependencies": 2, "satisfaction_rate": 0.6}

    report = optimizer.analyze([low_result, strong_result])

    assert report.phase_scorecards["intake_questioning"]["focus_areas"]
    assert "retaliation" in report.phase_scorecards["graph_analysis"]["generalization_targets"]
    assert "image_evidence" in report.phase_scorecards["document_generation"]["evidence_targets"]
    assert report.document_handoff_summary["blockers"]
    assert report.document_handoff_summary["ready_for_document_optimization"] is False
    assert report.complaint_type_generalization_summary["weakest"][0]["name"] in {"retaliation", "narrative_intake"}
    assert report.evidence_modality_generalization_summary["weakest"][0]["name"] == "image_evidence"
    assert report.cross_phase_findings
    assert report.workflow_action_queue
    assert any(item["phase_name"] == "cross_phase" for item in report.workflow_action_queue)


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


def test_build_phase_patch_tasks_carries_generalization_targets():
    optimizer = Optimizer()

    policy_result = _session_result("session_generalize_policy", 0.72, {"adversarial_intake_priority_summary": {}})
    policy_result.seed_complaint = {
        "type": "policy_grievance",
        "_meta": {"complaint_type": "housing_discrimination"},
        "key_facts": {
            "repository_evidence_candidates": [
                {"title": "ADMINISTRATIVE PLAN", "source_path": "/tmp/admin_plan.pdf", "snippet": "Notice language."}
            ],
        },
    }
    policy_result.knowledge_graph_summary = {"total_entities": 2, "total_relationships": 1, "gaps": 2}
    policy_result.dependency_graph_summary = {"total_nodes": 3, "total_dependencies": 1, "satisfaction_rate": 0.1}

    image_result = _session_result("session_generalize_image", 0.38, {"adversarial_intake_priority_summary": {}})
    image_result.seed_complaint = {
        "type": "narrative_intake",
        "_meta": {"complaint_type": "retaliation"},
        "key_facts": {
            "repository_evidence_candidates": [
                {"title": "Photo evidence", "source_path": "/tmp/photo.jpg", "snippet": "Apartment condition photo."}
            ],
        },
    }
    image_result.knowledge_graph_summary = {"total_entities": 1, "total_relationships": 0, "gaps": 5}
    image_result.dependency_graph_summary = {"total_nodes": 2, "total_dependencies": 0, "satisfaction_rate": 0.0}

    tasks, _report = optimizer.build_phase_patch_tasks(
        [policy_result, image_result],
        method="actor_critic",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
    )

    graph_task = next(task for task in tasks if task.metadata["workflow_phase"] == "graph_analysis")
    assert "retaliation" in graph_task.metadata["weak_complaint_types"]
    assert "image_evidence" in graph_task.metadata["weak_evidence_modalities"]
    assert "Weak complaint types to generalize for" in graph_task.description
    assert "Weak evidence modalities to improve" in graph_task.description


def test_analyze_and_phase_tasks_carry_document_evidence_targeting_summary():
    optimizer = Optimizer()
    result = _session_result(
        "session_document_targets",
        0.52,
        {
            "workflow_optimization_guidance": {
                "document_evidence_targeting_summary": {
                    "count": 2,
                    "claim_element_counts": {"protected_activity": 2},
                    "support_kind_counts": {"testimony": 2},
                    "targets": [
                        {
                            "focus_section": "factual_allegations",
                            "claim_type": "retaliation",
                            "claim_element_id": "protected_activity",
                            "preferred_support_kind": "testimony",
                            "kind": "evidence_workflow_action",
                            "text": "Collect chronology support for protected activity.",
                        }
                    ],
                }
                ,
                "document_workflow_execution_summary": {
                    "iteration_count": 2,
                    "accepted_iteration_count": 1,
                    "focus_section_counts": {"claims_for_relief": 1},
                    "top_support_kind_counts": {"workflow_targeting_claim_element": 1},
                    "targeted_claim_element_counts": {"causation": 1},
                    "preferred_support_kind_counts": {"testimony": 1},
                    "first_focus_section": "claims_for_relief",
                    "first_top_support_kind": "workflow_targeting_claim_element",
                    "first_targeted_claim_element": "causation",
                    "first_preferred_support_kind": "testimony",
                },
                "document_provenance_summary": {
                    "summary_fact_count": 3,
                    "summary_fact_backed_count": 1,
                    "factual_allegation_paragraph_count": 3,
                    "factual_allegation_fact_backed_count": 1,
                    "claim_supporting_fact_count": 2,
                    "claim_supporting_fact_backed_count": 1,
                    "fact_backed_ratio": 0.4444,
                    "low_grounding_flag": True,
                },
                "document_grounding_improvement_summary": {
                    "initial_fact_backed_ratio": 0.2,
                    "final_fact_backed_ratio": 0.4444,
                    "fact_backed_ratio_delta": 0.2444,
                    "improved_flag": True,
                    "recovery_attempted_flag": True,
                    "targeted_claim_elements": ["protected_activity"],
                },
            },
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["timeline"],
                "covered_objectives": [],
                "uncovered_objectives": ["timeline"],
            },
        },
    )
    result.knowledge_graph_summary = {"total_entities": 2, "total_relationships": 1, "gaps": 3}
    result.dependency_graph_summary = {"total_nodes": 2, "total_dependencies": 1, "satisfaction_rate": 0.2}

    report = optimizer.analyze([result])
    assert report.document_evidence_targeting_summary["count"] == 1
    assert report.document_workflow_execution_summary["first_targeted_claim_element"] == "causation"
    assert report.document_provenance_summary["low_grounding_flag"] is True
    assert report.document_provenance_summary["avg_fact_backed_ratio"] == 0.3889
    assert report.document_grounding_improvement_summary["improved_session_count"] == 1
    assert report.document_grounding_improvement_summary["avg_fact_backed_ratio_delta"] == 0.2444
    assert report.document_execution_drift_summary["drift_flag"] is True
    assert report.document_execution_drift_summary["top_targeted_claim_element"] == "protected_activity"
    assert report.document_evidence_targeting_summary["claim_element_counts"] == {"protected_activity": 1}
    assert "protected_activity" in report.phase_scorecards["document_generation"]["targeted_claim_elements"]
    assert report.phase_scorecards["document_generation"]["execution_mismatch_flag"] is True
    assert report.phase_scorecards["document_generation"]["execution_drift_summary"]["drift_flag"] is True
    assert report.phase_scorecards["document_generation"]["document_low_grounding_flag"] is True
    assert report.phase_scorecards["document_generation"]["document_fact_backed_ratio"] == 0.3889
    assert report.phase_scorecards["document_generation"]["document_grounding_improved_flag"] is True
    assert report.phase_scorecards["document_generation"]["first_executed_claim_element"] == "causation"
    assert any("protected_activity" in recommendation for recommendation in report.recommendations)
    assert any("acting on the highest-priority targeted claim element first" in recommendation for recommendation in report.recommendations)
    assert any("Draft grounding is weak" in recommendation for recommendation in report.recommendations)
    assert any("Grounding recovery prompts are improving fact-backed ratios" in recommendation for recommendation in report.recommendations)

    tasks, _ = optimizer.build_phase_patch_tasks(
        [result],
        method="actor_critic",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
        report=report,
    )
    document_task = next(task for task in tasks if task.metadata["workflow_phase"] == "document_generation")
    assert "Draft loop evidence targets" in document_task.description
    assert "Preferred support lanes" in document_task.description
    assert len(document_task.target_files) == 1
    assert document_task.target_files[0].name == "document_optimization.py"
    assert "document_optimization.py" in document_task.constraints["target_symbols"]
    assert document_task.constraints["target_symbols"]["document_optimization.py"] == [
        "_build_workflow_phase_targeting"
    ]
    assert document_task.metadata["document_evidence_targeting_summary"]["count"] == 1
    assert document_task.metadata["document_provenance_summary"]["low_grounding_flag"] is True
    assert document_task.metadata["document_grounding_improvement_summary"]["improved_flag"] is True
    assert document_task.metadata["document_workflow_execution_summary"]["first_targeted_claim_element"] == "causation"
    assert document_task.metadata["document_execution_drift_summary"]["drift_flag"] is True
    assert document_task.metadata["report_summary"]["document_evidence_targeting_summary"]["claim_element_counts"] == {
        "protected_activity": 1,
    }
    assert document_task.metadata["report_summary"]["document_provenance_summary"]["avg_fact_backed_ratio"] == 0.3889
    assert document_task.metadata["report_summary"]["document_grounding_improvement_summary"]["avg_fact_backed_ratio_delta"] == 0.2444
    assert document_task.metadata["report_summary"]["document_workflow_execution_summary"]["first_targeted_claim_element"] == "causation"
    assert document_task.metadata["report_summary"]["document_execution_drift_summary"]["drift_flag"] is True

    bundle, bundle_report = optimizer.build_workflow_optimization_bundle(
        [result],
        method="actor_critic",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
        report=report,
    )
    payload = bundle.to_dict()
    assert payload["shared_context"]["document_evidence_targeting_summary"]["count"] == 1
    assert payload["shared_context"]["document_provenance_summary"]["low_grounding_flag"] is True
    assert payload["shared_context"]["document_grounding_improvement_summary"]["improved_flag"] is True
    assert payload["shared_context"]["document_workflow_execution_summary"]["first_targeted_claim_element"] == "causation"
    assert payload["shared_context"]["document_execution_drift_summary"]["drift_flag"] is True
    assert bundle_report.document_evidence_targeting_summary["claim_element_counts"] == {"protected_activity": 1}


def test_document_execution_mismatch_escalates_document_phase_priority():
    optimizer = Optimizer()
    result = _session_result(
        "session_document_mismatch",
        0.58,
        {
            "workflow_optimization_guidance": {
                "document_evidence_targeting_summary": {
                    "count": 2,
                    "claim_element_counts": {"protected_activity": 2},
                    "support_kind_counts": {"testimony": 2},
                },
                "document_workflow_execution_summary": {
                    "iteration_count": 1,
                    "accepted_iteration_count": 1,
                    "focus_section_counts": {"claims_for_relief": 1},
                    "top_support_kind_counts": {"workflow_targeting_claim_element": 1},
                    "targeted_claim_element_counts": {"causation": 1},
                    "preferred_support_kind_counts": {"testimony": 1},
                    "first_focus_section": "claims_for_relief",
                    "first_top_support_kind": "workflow_targeting_claim_element",
                    "first_targeted_claim_element": "causation",
                    "first_preferred_support_kind": "testimony",
                },
            },
            "adversarial_intake_priority_summary": {
                "expected_objectives": [],
                "covered_objectives": [],
                "uncovered_objectives": [],
            },
        },
    )
    result.knowledge_graph_summary = {"total_entities": 3, "total_relationships": 2, "gaps": 0}
    result.dependency_graph_summary = {"total_nodes": 3, "total_dependencies": 2, "satisfaction_rate": 0.9}

    report = optimizer.analyze([result])

    document_phase = report.workflow_phase_plan["phases"]["document_generation"]
    assert document_phase["status"] in {"critical", "warning"}
    assert "document_generation" in report.workflow_phase_plan["recommended_order"][:2]


def test_analyze_and_phase_tasks_carry_graph_element_targeting_summary():
    optimizer = Optimizer()
    result = _session_result(
        "session_graph_targets",
        0.49,
        {
            "evidence_workflow_action_queue": [
                {
                    "phase_name": "graph_analysis",
                    "claim_type": "retaliation",
                    "claim_element_id": "causation",
                    "focus_areas": ["timeline", "chronology"],
                    "action": "Resolve chronology support for causation.",
                }
            ],
            "intake_legal_targeting_summary": {
                "claims": {
                    "retaliation": {
                        "missing_requirement_element_ids": ["protected_activity"],
                    }
                }
            },
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["timeline"],
                "covered_objectives": [],
                "uncovered_objectives": ["timeline"],
            },
        },
    )
    result.knowledge_graph_summary = {"total_entities": 1, "total_relationships": 0, "gaps": 4}
    result.dependency_graph_summary = {"total_nodes": 1, "total_dependencies": 0, "satisfaction_rate": 0.0}

    report = optimizer.analyze([result])
    assert report.graph_element_targeting_summary["count"] == 2
    assert report.graph_element_targeting_summary["claim_element_counts"]["causation"] == 1
    assert report.graph_element_targeting_summary["claim_element_counts"]["protected_activity"] == 1
    assert "causation" in report.phase_scorecards["graph_analysis"]["targeted_claim_elements"]
    assert any("causation" in recommendation for recommendation in report.recommendations)

    tasks, _ = optimizer.build_phase_patch_tasks(
        [result],
        method="actor_critic",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
        report=report,
    )
    graph_task = next(task for task in tasks if task.metadata["workflow_phase"] == "graph_analysis")
    assert "Graph evidence targets" in graph_task.description
    assert "Graph focus areas" in graph_task.description
    assert len(graph_task.target_files) == 1
    assert graph_task.target_files[0].name in {"dependency_graph.py", "denoiser.py"}
    target_symbol_path = next(iter(graph_task.constraints["target_symbols"]))
    assert target_symbol_path.endswith(graph_task.target_files[0].name)
    assert graph_task.metadata["graph_element_targeting_summary"]["count"] == 2
    assert graph_task.metadata["report_summary"]["graph_element_targeting_summary"]["claim_element_counts"] == {
        "causation": 1,
        "protected_activity": 1,
    }

    bundle, bundle_report = optimizer.build_workflow_optimization_bundle(
        [result],
        method="actor_critic",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
        report=report,
    )
    payload = bundle.to_dict()
    assert payload["shared_context"]["graph_element_targeting_summary"]["count"] == 2
    assert bundle_report.graph_element_targeting_summary["claim_element_counts"]["causation"] == 1


def test_analyze_and_phase_tasks_carry_intake_targeting_summary():
    optimizer = Optimizer()
    result = _session_result(
        "session_intake_targets",
        0.55,
        {
            "adversarial_intake_priority_summary": {
                "expected_objectives": ["timeline", "documents", "harm_remedy"],
                "covered_objectives": [],
                "uncovered_objectives": ["timeline", "documents", "harm_remedy"],
            },
            "intake_workflow_action_queue": [
                {
                    "focus_areas": ["timeline", "proof_leads"],
                    "target_element_id": "protected_activity",
                    "action": "Clarify the retaliation timeline and collect proof leads.",
                }
            ],
            "intake_legal_targeting_summary": {
                "claims": {
                    "retaliation": {
                        "missing_requirement_element_ids": ["causation"],
                    }
                }
            },
        },
    )
    result.knowledge_graph_summary = {"total_entities": 2, "total_relationships": 1, "gaps": 2}
    result.dependency_graph_summary = {"total_nodes": 2, "total_dependencies": 1, "satisfaction_rate": 0.2}

    report = optimizer.analyze([result])
    assert report.intake_targeting_summary["count"] >= 3
    assert report.intake_targeting_summary["objective_counts"]["timeline"] >= 1
    assert report.intake_targeting_summary["claim_element_counts"]["protected_activity"] == 1
    assert report.intake_targeting_summary["claim_element_counts"]["causation"] == 1
    assert "timeline" in report.phase_scorecards["intake_questioning"]["targeted_intake_objectives"]
    assert any("timeline" in recommendation for recommendation in report.recommendations)

    tasks, _ = optimizer.build_phase_patch_tasks(
        [result],
        method="actor_critic",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
        report=report,
    )
    intake_task = next(task for task in tasks if task.metadata["workflow_phase"] == "intake_questioning")
    assert "Intake targets" in intake_task.description
    assert "Legal elements to probe" in intake_task.description
    assert len(intake_task.target_files) == 1
    assert intake_task.target_files[0].name == "session.py"
    assert "adversarial_harness/session.py" in intake_task.constraints["target_symbols"]
    assert intake_task.constraints["target_symbols"]["adversarial_harness/session.py"] == [
        "_inject_intake_prompt_questions"
    ]
    assert intake_task.metadata["intake_targeting_summary"]["claim_element_counts"]["causation"] == 1
    assert intake_task.metadata["report_summary"]["intake_targeting_summary"]["objective_counts"]["timeline"] >= 1

    bundle, bundle_report = optimizer.build_workflow_optimization_bundle(
        [result],
        method="actor_critic",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
        report=report,
    )
    payload = bundle.to_dict()
    assert payload["shared_context"]["workflow_targeting_summary"]["count"] >= 4
    assert payload["shared_context"]["workflow_targeting_summary"]["phase_counts"]["intake_questioning"] >= 3
    assert payload["shared_context"]["workflow_targeting_summary"]["phase_counts"]["graph_analysis"] >= 1
    assert payload["shared_context"]["workflow_targeting_summary"]["phase_counts"]["document_generation"] == 0
    assert payload["shared_context"]["intake_targeting_summary"]["count"] >= 3
    assert bundle_report.intake_targeting_summary["claim_element_counts"]["causation"] == 1
    assert bundle_report.workflow_targeting_summary["shared_claim_element_counts"]["causation"] >= 1


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


def test_build_phase_patch_tasks_limits_no_data_intake_phase_to_session_only():
    optimizer = Optimizer()
    result = _session_result("session_failed", 0.18, {})
    result.success = False

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

    intake_task = next(task for task in tasks if task.metadata["workflow_phase"] == "intake_questioning")
    assert report.num_sessions_analyzed == 0
    assert intake_task.target_files == [Path("adversarial_harness/session.py")]
    assert list(intake_task.constraints["target_symbols"].values()) == [[
        "_inject_intake_prompt_questions",
    ]]


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
