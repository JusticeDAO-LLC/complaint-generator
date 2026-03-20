from types import SimpleNamespace

from complaint_phases import ComplaintPhase

from workflow_phase_guidance import (
    build_drafting_document_generation_phase_guidance,
    build_graph_analysis_phase_guidance,
    build_review_document_generation_phase_guidance,
    build_workflow_phase_plan,
    build_workflow_phase_warning_entries,
)


def test_build_graph_analysis_phase_guidance_supports_review_and_drafting_audiences():
    phase_data = {
        (ComplaintPhase.INTAKE, "knowledge_graph"): {"nodes": ["claim"]},
        (ComplaintPhase.INTAKE, "dependency_graph"): {"edges": ["support"]},
        (ComplaintPhase.INTAKE, "current_gaps"): [{"gap_id": "gap_001"}],
        (ComplaintPhase.INTAKE, "remaining_gaps"): 1,
        (ComplaintPhase.EVIDENCE, "knowledge_graph_enhanced"): False,
    }

    phase_manager = SimpleNamespace(get_phase_data=lambda phase, key: phase_data.get((phase, key)))

    review_phase = build_graph_analysis_phase_guidance(phase_manager, audience="review")
    drafting_phase = build_graph_analysis_phase_guidance(phase_manager, audience="drafting")

    assert review_phase["status"] == "warning"
    assert review_phase["summary"] == "Graph analysis still has 1 unresolved gap(s) or pending evidence-to-graph updates."
    assert review_phase["recommended_actions"] == [
        "Review intake graph inputs and refresh graph-backed evidence projections before final drafting.",
    ]
    assert review_phase["signals"]["remaining_gap_count"] == 1
    assert review_phase["signals"]["knowledge_graph_enhanced"] is False

    assert drafting_phase["status"] == "warning"
    assert drafting_phase["summary"] == "Graph analysis still shows 1 unresolved gap(s) or unprojected evidence updates."
    assert drafting_phase["recommended_actions"] == [
        "Resolve remaining intake graph gaps and refresh graph projections before filing.",
        "Project newly collected evidence into the complaint knowledge graph.",
    ]


def test_build_workflow_phase_plan_orders_and_warns_by_status_priority():
    plan = build_workflow_phase_plan(
        {
            "document_generation": {
                "priority": 1,
                "status": "ready",
                "summary": "Drafting is ready.",
                "recommended_actions": [],
            },
            "graph_analysis": {
                "priority": 0,
                "status": "warning",
                "summary": "Graph cleanup still needed.",
                "recommended_actions": ["Refresh graph projections."],
            },
        }
    )

    assert plan["recommended_order"] == ["graph_analysis", "document_generation"]
    assert build_workflow_phase_warning_entries(plan) == [
        {
            "code": "workflow_graph_analysis_warning",
            "severity": "warning",
            "message": "Graph cleanup still needed.",
            "phase": "graph_analysis",
            "recommended_actions": ["Refresh graph projections."],
        }
    ]


def test_document_generation_phase_guidance_supports_review_and_drafting_contexts():
    review_phase = build_review_document_generation_phase_guidance(
        intake_status={"next_action": {"action": "generate_formal_complaint"}},
        intake_case_summary={
            "claim_support_packet_summary": {
                "proof_readiness_score": 0.9,
                "claim_support_unresolved_temporal_issue_count": 0,
                "claim_support_unresolved_without_review_path_count": 0,
            }
        },
    )
    drafting_phase = build_drafting_document_generation_phase_guidance(
        drafting_readiness={
            "status": "warning",
            "warning_count": 2,
            "sections": {"claims_for_relief": {"status": "warning"}},
            "claims": [{"claim_type": "retaliation", "status": "warning"}],
        },
        document_optimization={"final_score": 0.62, "target_score": 0.8},
    )

    assert review_phase["status"] == "ready"
    assert review_phase["summary"] == "Review state indicates the complaint can move into formal complaint drafting."
    assert review_phase["signals"]["proof_readiness_score"] == 0.9

    assert drafting_phase["status"] == "warning"
    assert drafting_phase["summary"] == "Document generation still has 1 section warning(s) and 1 claim warning(s) to review."
    assert drafting_phase["recommended_actions"] == [
        "Review claims-for-relief, exhibits, and requested-relief warnings before filing.",
        "Run another document-optimization pass or accept the draft with recorded review warnings.",
    ]
    assert drafting_phase["signals"]["optimization_final_score"] == 0.62