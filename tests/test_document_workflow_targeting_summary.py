from unittest.mock import Mock

from document_pipeline import (
    FormalComplaintDocumentBuilder,
    _build_runtime_workflow_optimization_guidance,
    _build_workflow_optimization_warning_entries,
)


def test_runtime_workflow_guidance_preserves_workflow_targeting_summary():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "workflow_targeting_summary": {
            "count": 3,
            "phase_counts": {
                "intake_questioning": 2,
                "graph_analysis": 1,
                "document_generation": 0,
            },
        },
        "document_workflow_execution_summary": {
            "iteration_count": 1,
            "first_focus_section": "claims_for_relief",
            "first_targeted_claim_element": "causation",
        },
        "document_execution_drift_summary": {
            "drift_flag": True,
            "top_targeted_claim_element": "protected_activity",
            "first_executed_claim_element": "causation",
        },
        "document_grounding_improvement_summary": {
            "initial_fact_backed_ratio": 0.2,
            "final_fact_backed_ratio": 0.45,
            "fact_backed_ratio_delta": 0.25,
            "improved_flag": True,
        },
        "document_drafting_next_action": {
            "action": "realign_document_drafting",
            "focus_section": "claims_for_relief",
            "claim_element_id": "protected_activity",
            "executed_claim_element_id": "causation",
            "preferred_support_kind": "testimony",
        },
        "evidence_workflow_action_queue": [],
        "evidence_workflow_action_summary": {},
    }

    guidance = _build_runtime_workflow_optimization_guidance(
        mediator=mediator,
        drafting_readiness={"status": "warning", "sections": {}, "warning_count": 1},
        workflow_phase_plan={"recommended_order": ["intake_questioning", "graph_analysis"]},
        document_optimization={
            "workflow_targeting_summary": {
                "count": 4,
                "phase_counts": {
                    "intake_questioning": 2,
                    "graph_analysis": 1,
                    "document_generation": 1,
                },
            },
            "document_workflow_execution_summary": {
                "iteration_count": 2,
                "first_focus_section": "factual_allegations",
                "first_targeted_claim_element": "protected_activity",
            },
            "document_execution_drift_summary": {
                "drift_flag": False,
                "top_targeted_claim_element": "protected_activity",
                "first_executed_claim_element": "protected_activity",
            },
            "document_grounding_improvement_summary": {
                "initial_fact_backed_ratio": 0.25,
                "final_fact_backed_ratio": 0.5,
                "fact_backed_ratio_delta": 0.25,
                "improved_flag": True,
            },
        },
    )

    assert guidance["workflow_targeting_summary"]["count"] == 4
    assert guidance["workflow_targeting_summary"]["phase_counts"]["document_generation"] == 1
    assert guidance["document_workflow_execution_summary"]["iteration_count"] == 2
    assert guidance["document_execution_drift_summary"]["drift_flag"] is False
    assert guidance["document_grounding_improvement_summary"]["improved_flag"] is True
    assert guidance["document_drafting_next_action"]["action"] == "realign_document_drafting"
    assert guidance["document_drafting_next_action"]["focus_section"] == "claims_for_relief"


def test_build_package_carries_workflow_targeting_summary_into_draft_and_payload():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "workflow_targeting_summary": {
            "count": 2,
            "phase_counts": {
                "intake_questioning": 1,
                "graph_analysis": 1,
                "document_generation": 0,
            },
        },
        "document_workflow_execution_summary": {
            "iteration_count": 1,
            "first_focus_section": "claims_for_relief",
            "first_targeted_claim_element": "causation",
        },
        "document_execution_drift_summary": {
            "drift_flag": True,
            "top_targeted_claim_element": "protected_activity",
            "first_executed_claim_element": "causation",
        },
        "document_grounding_improvement_summary": {
            "initial_fact_backed_ratio": 0.2,
            "final_fact_backed_ratio": 0.55,
            "fact_backed_ratio_delta": 0.35,
            "improved_flag": True,
        },
        "evidence_workflow_action_queue": [],
        "evidence_workflow_action_summary": {},
    }
    builder = FormalComplaintDocumentBuilder(mediator)
    builder.build_draft = Mock(return_value={"summary_of_facts": [], "claims_for_relief": []})
    builder._build_drafting_readiness = Mock(
        return_value={"status": "ready", "sections": {}, "claims": [], "warning_count": 0}
    )
    builder._build_filing_checklist = Mock(return_value=[])
    builder._annotate_filing_checklist_review_links = Mock()
    builder._build_affidavit = Mock(return_value={})
    builder._build_claim_support_temporal_handoff = Mock(return_value={})
    builder._build_intake_summary_handoff = Mock(return_value={})
    builder.render_artifacts = Mock(return_value={})

    result = builder.build_package(
        district="Northern District of California",
        plaintiff_names=["Jane Doe"],
        defendant_names=["Acme Corporation"],
        output_formats=["txt"],
    )

    assert result["workflow_targeting_summary"]["count"] == 2
    assert result["draft"]["workflow_targeting_summary"] == result["workflow_targeting_summary"]
    assert result["workflow_optimization_guidance"]["workflow_targeting_summary"] == result["workflow_targeting_summary"]
    assert result["document_workflow_execution_summary"]["first_targeted_claim_element"] == "causation"
    assert result["draft"]["document_workflow_execution_summary"] == result["document_workflow_execution_summary"]
    assert result["workflow_optimization_guidance"]["document_workflow_execution_summary"] == result["document_workflow_execution_summary"]
    assert result["document_execution_drift_summary"]["drift_flag"] is True
    assert result["draft"]["document_execution_drift_summary"] == result["document_execution_drift_summary"]
    assert result["workflow_optimization_guidance"]["document_execution_drift_summary"] == result["document_execution_drift_summary"]
    assert result["document_grounding_improvement_summary"]["improved_flag"] is True
    assert result["draft"]["document_grounding_improvement_summary"] == result["document_grounding_improvement_summary"]
    assert result["workflow_optimization_guidance"]["document_grounding_improvement_summary"] == result["document_grounding_improvement_summary"]
    assert result["workflow_optimization_guidance"]["workflow_action_queue"][0]["action"] == (
        "Realign drafting to the top targeted claim element before further revisions."
    )
    assert result["workflow_optimization_guidance"]["workflow_action_queue"][0]["phase_name"] == "document_generation"


def test_runtime_workflow_guidance_prioritizes_document_execution_drift_action():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "workflow_targeting_summary": {
            "count": 2,
            "phase_counts": {
                "intake_questioning": 1,
                "graph_analysis": 1,
                "document_generation": 0,
            },
        },
        "document_workflow_execution_summary": {
            "iteration_count": 1,
            "first_focus_section": "claims_for_relief",
            "first_targeted_claim_element": "causation",
        },
        "document_execution_drift_summary": {
            "drift_flag": True,
            "top_targeted_claim_element": "protected_activity",
            "first_executed_claim_element": "causation",
        },
        "evidence_workflow_action_queue": [
            {
                "rank": 1,
                "phase_name": "graph_analysis",
                "status": "warning",
                "action": "Collect testimony for protected activity.",
                "focus_areas": ["protected_activity"],
            }
        ],
        "evidence_workflow_action_summary": {"count": 1},
    }

    guidance = _build_runtime_workflow_optimization_guidance(
        mediator=mediator,
        drafting_readiness={"status": "warning", "sections": {}, "warning_count": 1},
        workflow_phase_plan={"recommended_order": ["document_generation", "graph_analysis"]},
        document_optimization=None,
    )

    assert guidance["workflow_action_queue"][0]["phase_name"] == "document_generation"
    assert guidance["workflow_action_queue"][0]["top_targeted_claim_element"] == "protected_activity"
    assert guidance["workflow_action_queue"][0]["first_executed_claim_element"] == "causation"


def test_workflow_optimization_warning_entries_include_document_execution_drift():
    warnings = _build_workflow_optimization_warning_entries(
        {
            "document_execution_drift_summary": {
                "drift_flag": True,
                "top_targeted_claim_element": "protected_activity",
                "first_executed_claim_element": "causation",
            }
        }
    )

    drift_warning = next(
        warning for warning in warnings if warning["code"] == "workflow_document_execution_drift_warning"
    )
    assert drift_warning["phase"] == "document_generation"
    assert "wrong claim element first" in drift_warning["message"]
    assert drift_warning["focus_areas"] == ["protected_activity", "causation"]
