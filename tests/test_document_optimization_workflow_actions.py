from unittest.mock import Mock

from document_optimization import (
    AgenticDocumentOptimizer,
    _build_document_execution_drift_summary,
    _build_workflow_targeting_summary,
)


def test_build_support_context_preserves_evidence_workflow_actions():
    mediator = Mock()
    mediator.summarize_claim_support.return_value = {}
    mediator.get_user_evidence.return_value = []
    mediator.get_three_phase_status.return_value = {
        "document_drafting_next_action": {
            "action": "realign_document_drafting",
            "focus_section": "claims_for_relief",
            "claim_element_id": "protected_activity",
            "executed_claim_element_id": "causation",
            "preferred_support_kind": "testimony",
        }
    }
    optimizer = AgenticDocumentOptimizer(mediator)

    support_context = optimizer._build_support_context(
        user_id="user-1",
        draft={"claims_for_relief": []},
        drafting_readiness={
            "workflow_optimization_guidance": {
                "evidence_workflow_action_queue": [
                    {
                        "rank": 1,
                        "phase_name": "graph_analysis",
                        "action": "Collect chronology support for protected activity.",
                        "claim_type": "retaliation",
                        "claim_element_id": "protected_activity",
                        "claim_element_label": "Protected activity",
                        "preferred_support_kind": "testimony",
                        "status": "warning",
                    }
                ],
                "evidence_workflow_action_summary": {"count": 1},
                "workflow_action_queue": [],
            }
        },
    )

    assert support_context["evidence_workflow_action_queue"][0]["claim_element_id"] == "protected_activity"
    assert support_context["evidence_workflow_action_summary"]["count"] == 1
    assert support_context["document_drafting_next_action"]["action"] == "realign_document_drafting"
    assert support_context["document_drafting_next_action"]["focus_section"] == "claims_for_relief"


def test_select_support_context_prioritizes_evidence_workflow_action_rows():
    mediator = Mock()
    optimizer = AgenticDocumentOptimizer(mediator)
    optimizer._rank_candidates = lambda *, query, candidates: list(candidates)

    selected = optimizer._select_support_context(
        focus_section="factual_allegations",
        draft={"summary_of_facts": []},
        support_context={
            "claims": [],
            "evidence": [],
            "intake_priorities": {},
            "workflow_action_queue": [],
            "evidence_workflow_action_queue": [
                {
                    "phase_name": "graph_analysis",
                    "action": "Collect chronology support for protected activity.",
                    "claim_type": "retaliation",
                    "claim_element_id": "protected_activity",
                    "claim_element_label": "Protected activity",
                    "preferred_support_kind": "testimony",
                    "status": "warning",
                }
            ],
        },
    )

    assert selected["top_support"]
    assert selected["top_support"][0]["kind"] == "evidence_workflow_action"
    assert "Protected activity" in selected["top_support"][0]["text"]
    assert selected["top_support"][0]["preferred_support_kind"] == "testimony"


def test_select_support_context_includes_document_drafting_next_action_rows():
    mediator = Mock()
    optimizer = AgenticDocumentOptimizer(mediator)
    optimizer._rank_candidates = lambda *, query, candidates: list(candidates)

    selected = optimizer._select_support_context(
        focus_section="claims_for_relief",
        draft={"claims_for_relief": []},
        support_context={
            "claims": [],
            "evidence": [],
            "intake_priorities": {},
            "workflow_action_queue": [],
            "evidence_workflow_action_queue": [],
            "document_drafting_next_action": {
                "action": "realign_document_drafting",
                "focus_section": "claims_for_relief",
                "claim_element_id": "protected_activity",
                "executed_claim_element_id": "causation",
                "preferred_support_kind": "testimony",
            },
        },
    )

    assert selected["top_support"]
    assert selected["top_support"][0]["kind"] == "document_drafting_next_action"
    assert selected["top_support"][0]["claim_element_id"] == "protected_activity"
    assert selected["top_support"][0]["preferred_support_kind"] == "testimony"


def test_select_support_context_includes_workflow_targeting_rows():
    mediator = Mock()
    optimizer = AgenticDocumentOptimizer(mediator)
    optimizer._rank_candidates = lambda *, query, candidates: list(candidates)

    selected = optimizer._select_support_context(
        focus_section="claims_for_relief",
        draft={"claims_for_relief": []},
        support_context={
            "claims": [],
            "evidence": [],
            "intake_priorities": {},
            "workflow_action_queue": [],
            "evidence_workflow_action_queue": [],
            "workflow_targeting_summary": {
                "shared_claim_element_counts": {"causation": 2},
                "shared_focus_area_counts": {"timeline": 1},
            },
        },
    )

    kinds = [row.get("kind") for row in selected["top_support"]]
    assert "workflow_targeting_claim_element" in kinds
    assert "workflow_targeting_focus_area" in kinds
    assert any(row.get("claim_element_id") == "causation" for row in selected["top_support"])


def test_choose_focus_section_can_use_workflow_targeting_summary():
    mediator = Mock()
    optimizer = AgenticDocumentOptimizer(mediator)

    focus = optimizer._choose_focus_section(
        current_review={},
        draft={"summary_of_facts": [], "claims_for_relief": []},
        drafting_readiness={},
        support_context={
            "workflow_targeting_summary": {
                "prioritized_phases": ["graph_analysis", "intake_questioning"],
                "shared_claim_element_counts": {"protected_activity": 2},
                "phase_summaries": {
                    "document_generation": {
                        "count": 1,
                        "focus_section_counts": {"claims_for_relief": 1},
                    }
                },
            }
        },
    )

    assert focus == "claims_for_relief"


def test_choose_focus_section_prefers_document_drafting_next_action_focus_section():
    mediator = Mock()
    optimizer = AgenticDocumentOptimizer(mediator)

    focus = optimizer._choose_focus_section(
        current_review={
            "workflow_phase_order": ["intake_questioning"],
            "workflow_phase_target_sections": {"intake_questioning": "factual_allegations"},
            "recommended_focus": "factual_allegations",
        },
        draft={"summary_of_facts": [], "claims_for_relief": []},
        drafting_readiness={},
        support_context={
            "document_drafting_next_action": {
                "action": "realign_document_drafting",
                "focus_section": "claims_for_relief",
                "claim_element_id": "protected_activity",
                "executed_claim_element_id": "causation",
            },
            "workflow_targeting_summary": {
                "prioritized_phases": ["intake_questioning"],
                "phase_summaries": {
                    "document_generation": {
                        "count": 1,
                        "focus_section_counts": {"factual_allegations": 1},
                    }
                },
            },
        },
    )

    assert focus == "claims_for_relief"


def test_build_document_evidence_targeting_summary_tracks_selected_targets():
    summary = AgenticDocumentOptimizer._build_document_evidence_targeting_summary(
        [
            {
                "focus_section": "factual_allegations",
                "selected_support_context": {
                    "top_support": [
                        {
                            "kind": "evidence_workflow_action",
                            "claim_type": "retaliation",
                            "claim_element_id": "protected_activity",
                            "preferred_support_kind": "testimony",
                            "text": "Collect chronology support for protected activity.",
                        }
                    ]
                },
            }
        ]
    )

    assert summary["count"] == 1
    assert summary["focus_section_counts"] == {"factual_allegations": 1}
    assert summary["claim_type_counts"] == {"retaliation": 1}
    assert summary["claim_element_counts"] == {"protected_activity": 1}
    assert summary["support_kind_counts"] == {"testimony": 1}
    assert summary["targets"][0]["kind"] == "evidence_workflow_action"


def test_build_document_workflow_execution_summary_tracks_first_choices():
    summary = AgenticDocumentOptimizer._build_document_workflow_execution_summary(
        [
            {
                "iteration": 1,
                "accepted": True,
                "focus_section": "claims_for_relief",
                "selected_support_context": {
                    "top_support": [
                        {
                            "kind": "workflow_targeting_claim_element",
                            "claim_element_id": "causation",
                            "preferred_support_kind": "testimony",
                        }
                    ]
                },
            },
            {
                "iteration": 2,
                "accepted": False,
                "focus_section": "factual_allegations",
                "selected_support_context": {
                    "top_support": [
                        {
                            "kind": "evidence_workflow_action",
                            "claim_element_id": "protected_activity",
                            "preferred_support_kind": "document",
                        }
                    ]
                },
            },
        ]
    )

    assert summary["iteration_count"] == 2
    assert summary["accepted_iteration_count"] == 1
    assert summary["focus_section_counts"] == {
        "claims_for_relief": 1,
        "factual_allegations": 1,
    }
    assert summary["top_support_kind_counts"] == {
        "workflow_targeting_claim_element": 1,
        "evidence_workflow_action": 1,
    }
    assert summary["targeted_claim_element_counts"] == {
        "causation": 1,
        "protected_activity": 1,
    }
    assert summary["preferred_support_kind_counts"] == {
        "testimony": 1,
        "document": 1,
    }
    assert summary["first_focus_section"] == "claims_for_relief"
    assert summary["first_top_support_kind"] == "workflow_targeting_claim_element"
    assert summary["first_targeted_claim_element"] == "causation"
    assert summary["first_preferred_support_kind"] == "testimony"


def test_build_workflow_targeting_summary_merges_document_targets():
    summary = _build_workflow_targeting_summary(
        existing_summary={
            "count": 3,
            "phase_counts": {
                "intake_questioning": 2,
                "graph_analysis": 1,
                "document_generation": 0,
            },
            "phase_summaries": {
                "intake_questioning": {
                    "count": 2,
                    "objective_counts": {"timeline": 2},
                    "claim_element_counts": {"protected_activity": 1},
                },
                "graph_analysis": {
                    "count": 1,
                    "focus_area_counts": {"chronology": 1},
                    "claim_element_counts": {"protected_activity": 1},
                },
            },
        },
        document_evidence_targeting_summary={
            "count": 1,
            "focus_section_counts": {"factual_allegations": 1},
            "claim_element_counts": {"protected_activity": 1},
            "support_kind_counts": {"testimony": 1},
        },
    )

    assert summary["count"] == 4
    assert summary["phase_counts"] == {
        "intake_questioning": 2,
        "graph_analysis": 1,
        "document_generation": 1,
    }
    assert summary["shared_claim_element_counts"] == {"protected_activity": 3}
    assert summary["shared_focus_area_counts"]["timeline"] == 2
    assert summary["shared_focus_area_counts"]["chronology"] == 1
    assert summary["shared_focus_area_counts"]["factual_allegations"] == 1
    assert summary["phase_summaries"]["document_generation"]["count"] == 1


def test_build_document_execution_drift_summary_detects_mismatch():
    summary = _build_document_execution_drift_summary(
        workflow_targeting_summary={
            "shared_claim_element_counts": {
                "protected_activity": 2,
                "causation": 1,
            }
        },
        document_workflow_execution_summary={
            "iteration_count": 2,
            "accepted_iteration_count": 1,
            "first_targeted_claim_element": "causation",
            "first_focus_section": "claims_for_relief",
            "first_preferred_support_kind": "testimony",
        },
    )

    assert summary["drift_flag"] is True
    assert summary["top_targeted_claim_element"] == "protected_activity"
    assert summary["first_executed_claim_element"] == "causation"
    assert summary["first_focus_section"] == "claims_for_relief"
