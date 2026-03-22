from types import SimpleNamespace
from unittest.mock import Mock

from intake_status import build_intake_case_review_summary, build_intake_status_summary


def test_build_intake_status_summary_preserves_legacy_alias_fields():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "iteration_count": 4,
        "intake_readiness": {
            "score": 0.75,
            "ready": False,
            "ready_to_advance": False,
            "remaining_gap_count": 2,
            "contradiction_count": 1,
            "blockers": ["missing_proof_leads"],
            "criteria": {
                "case_theory_coherent": True,
                "minimum_proof_path_present": False,
            },
            "contradictions": [{"summary": "Timeline conflict"}],
            "blocking_contradictions": [{"summary": "Timeline conflict"}],
            "candidate_claim_count": 1,
            "canonical_fact_count": 2,
            "proof_lead_count": 0,
        },
        "next_action": {
            "action": "validate_promoted_support",
            "claim_type": "retaliation",
            "claim_element_id": "adverse_action",
            "validation_target_count": 2,
            "primary_validation_target": {
                "claim_type": "retaliation",
                "claim_element_id": "adverse_action",
                "promotion_kind": "document",
                "promotion_ref": "doc:retaliation:1",
            },
        },
    }

    summary = build_intake_status_summary(mediator, include_iteration_count=True)

    assert summary == {
        "current_phase": "intake",
        "iteration_count": 4,
        "ready_to_advance": False,
        "score": 0.75,
        "remaining_gap_count": 2,
        "contradiction_count": 1,
        "contradiction_summary": {
            "count": 1,
            "lane_counts": {},
            "status_counts": {},
            "severity_counts": {},
            "corroboration_required_count": 0,
            "affected_claim_type_counts": {},
            "affected_element_counts": {},
        },
        "blockers": ["missing_proof_leads"],
        "criteria": {
            "case_theory_coherent": True,
            "minimum_proof_path_present": False,
        },
        "next_action": {
            "action": "validate_promoted_support",
            "claim_type": "retaliation",
            "claim_element_id": "adverse_action",
            "validation_target_count": 2,
            "primary_validation_target": {
                "claim_type": "retaliation",
                "claim_element_id": "adverse_action",
                "promotion_kind": "document",
                "promotion_ref": "doc:retaliation:1",
            },
        },
        "document_drafting_next_action": {},
        "primary_validation_target": {
            "claim_type": "retaliation",
            "claim_element_id": "adverse_action",
            "promotion_kind": "document",
            "promotion_ref": "doc:retaliation:1",
        },
        "contradictions": [
            {
                "contradiction_id": "",
                "summary": "Timeline conflict",
                "left_text": "",
                "right_text": "",
                "question": "",
                "severity": "",
                "category": "",
                "recommended_resolution_lane": "",
                "current_resolution_status": "",
                "external_corroboration_required": False,
                "affected_claim_types": [],
                "affected_element_ids": [],
            }
        ],
        "blocking_contradictions": [{"summary": "Timeline conflict"}],
        "candidate_claim_count": 1,
        "canonical_fact_count": 2,
        "proof_lead_count": 0,
    }


def test_build_intake_status_summary_includes_document_drafting_next_action_from_drift():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "evidence",
        "intake_readiness": {
            "score": 0.61,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "blockers": [],
            "criteria": {},
            "candidate_claim_count": 1,
            "canonical_fact_count": 2,
            "proof_lead_count": 1,
        },
        "next_action": {
            "action": "validate_promoted_support",
            "validation_target_count": 1,
        },
        "document_execution_drift_summary": {
            "drift_flag": True,
            "top_targeted_claim_element": "protected_activity",
            "first_executed_claim_element": "causation",
            "first_focus_section": "claims_for_relief",
            "first_preferred_support_kind": "testimony",
        },
    }

    summary = build_intake_status_summary(mediator)

    assert summary["document_drafting_next_action"] == {
        "action": "realign_document_drafting",
        "phase_name": "document_generation",
        "description": "Realign drafting to protected_activity before further revisions; the draft loop acted on causation first.",
        "claim_element_id": "protected_activity",
        "executed_claim_element_id": "causation",
        "focus_section": "claims_for_relief",
        "preferred_support_kind": "testimony",
    }
    assert summary["next_action"]["document_drafting_next_action"] == summary["document_drafting_next_action"]


def test_build_intake_status_summary_includes_document_grounding_recovery_action():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "formalization",
        "intake_readiness": {
            "score": 0.42,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "blockers": [],
            "criteria": {},
            "candidate_claim_count": 1,
            "canonical_fact_count": 1,
            "proof_lead_count": 1,
        },
        "document_provenance_summary": {
            "fact_backed_ratio": 0.25,
            "low_grounding_flag": True,
        },
        "alignment_evidence_tasks": [
            {
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "fallback_lanes": ["authority", "testimony"],
                "missing_fact_bundle": ["Complaint timing", "Manager knowledge"],
            }
        ],
        "next_action": {"action": "complete_evidence"},
    }

    summary = build_intake_status_summary(mediator)

    assert summary["document_grounding_recovery_action"] == {
        "action": "recover_document_grounding",
        "phase_name": "document_generation",
        "description": "Strengthen draft grounding for protected_activity before formalization.",
        "claim_type": "retaliation",
        "claim_element_id": "protected_activity",
        "focus_section": "factual_allegations",
        "preferred_support_kind": "authority",
        "fact_backed_ratio": 0.25,
        "missing_fact_bundle": ["Complaint timing", "Manager knowledge"],
        "recovery_source": "alignment_evidence_task",
    }
    assert summary["next_action"]["document_grounding_recovery_action"] == summary["document_grounding_recovery_action"]


def test_build_intake_status_summary_includes_document_grounding_improvement_next_action():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "formalization",
        "intake_readiness": {
            "score": 0.51,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "blockers": [],
            "criteria": {},
            "candidate_claim_count": 1,
            "canonical_fact_count": 1,
            "proof_lead_count": 1,
        },
        "document_provenance_summary": {
            "fact_backed_ratio": 0.25,
            "low_grounding_flag": True,
        },
        "document_grounding_improvement_summary": {
            "initial_fact_backed_ratio": 0.25,
            "final_fact_backed_ratio": 0.25,
            "fact_backed_ratio_delta": 0.0,
            "stalled_flag": True,
            "targeted_claim_elements": ["protected_activity"],
            "preferred_support_kinds": ["authority"],
            "recovery_attempted_flag": True,
        },
        "alignment_evidence_tasks": [
            {
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "fallback_lanes": ["authority", "testimony"],
                "missing_fact_bundle": ["Complaint timing", "Manager knowledge"],
            }
        ],
        "next_action": {"action": "complete_evidence"},
    }

    summary = build_intake_status_summary(mediator)

    assert summary["document_grounding_improvement_next_action"] == {
        "action": "refine_document_grounding_strategy",
        "phase_name": "document_generation",
        "description": "Grounding recovery stalled; switch support lanes or retarget the next grounding cycle for protected_activity by trying testimony instead of authority.",
        "status": "stalled",
        "claim_type": "retaliation",
        "claim_element_id": "protected_activity",
        "focus_section": "factual_allegations",
        "preferred_support_kind": "authority",
        "suggested_support_kind": "testimony",
        "alternate_support_kinds": ["testimony", "evidence"],
        "initial_fact_backed_ratio": 0.25,
        "final_fact_backed_ratio": 0.25,
        "fact_backed_ratio_delta": 0.0,
        "recovery_attempted_flag": True,
        "targeted_claim_elements": ["protected_activity"],
        "preferred_support_kinds": ["authority"],
        "learned_support_lane_attempted_flag": False,
        "learned_support_lane_effective_flag": False,
    }
    assert summary["next_action"]["document_grounding_improvement_next_action"] == summary["document_grounding_improvement_next_action"]


def test_build_intake_status_summary_prefers_learned_grounding_support_lane():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "formalization",
        "intake_readiness": {
            "score": 0.51,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "blockers": [],
            "criteria": {},
            "candidate_claim_count": 1,
            "canonical_fact_count": 1,
            "proof_lead_count": 1,
        },
        "document_provenance_summary": {
            "fact_backed_ratio": 0.25,
            "low_grounding_flag": True,
        },
        "document_grounding_improvement_summary": {
            "initial_fact_backed_ratio": 0.25,
            "final_fact_backed_ratio": 0.25,
            "fact_backed_ratio_delta": 0.0,
            "stalled_flag": True,
            "targeted_claim_elements": ["protected_activity"],
            "preferred_support_kinds": ["authority"],
            "recovery_attempted_flag": True,
        },
        "document_grounding_lane_outcome_summary": {
            "recommended_future_support_kind": "testimony",
        },
        "alignment_evidence_tasks": [
            {
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "fallback_lanes": ["authority", "testimony"],
                "missing_fact_bundle": ["Complaint timing", "Manager knowledge"],
            }
        ],
        "next_action": {"action": "complete_evidence"},
    }

    summary = build_intake_status_summary(mediator)

    assert summary["document_grounding_improvement_next_action"]["suggested_support_kind"] == "testimony"
    assert summary["document_grounding_improvement_next_action"]["learned_support_kind"] == "testimony"
    assert "trying testimony instead of authority" in summary["document_grounding_improvement_next_action"]["description"]


def test_build_intake_status_summary_can_infer_learned_support_lane_from_stats():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "formalization",
        "intake_readiness": {
            "score": 0.51,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "blockers": [],
            "criteria": {},
            "candidate_claim_count": 1,
            "canonical_fact_count": 1,
            "proof_lead_count": 1,
        },
        "document_provenance_summary": {
            "fact_backed_ratio": 0.25,
            "low_grounding_flag": True,
        },
        "document_grounding_improvement_summary": {
            "initial_fact_backed_ratio": 0.25,
            "final_fact_backed_ratio": 0.25,
            "fact_backed_ratio_delta": 0.0,
            "stalled_flag": True,
            "targeted_claim_elements": ["protected_activity"],
            "preferred_support_kinds": ["authority"],
            "recovery_attempted_flag": True,
        },
        "document_grounding_lane_outcome_summary": {
            "support_kind_stats": {
                "authority": {
                    "count": 2,
                    "improved_count": 0,
                    "regressed_count": 1,
                    "stalled_count": 1,
                    "avg_fact_backed_ratio_delta": -0.05,
                    "targeted_claim_element_counts": {"protected_activity": 1},
                },
                "testimony": {
                    "count": 3,
                    "improved_count": 2,
                    "regressed_count": 0,
                    "stalled_count": 1,
                    "avg_fact_backed_ratio_delta": 0.18,
                    "targeted_claim_element_counts": {"protected_activity": 2},
                },
            },
        },
        "alignment_evidence_tasks": [
            {
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "fallback_lanes": ["authority", "testimony"],
                "missing_fact_bundle": ["Complaint timing", "Manager knowledge"],
            }
        ],
        "next_action": {"action": "complete_evidence"},
    }

    summary = build_intake_status_summary(mediator)

    assert summary["document_grounding_improvement_next_action"]["suggested_support_kind"] == "testimony"
    assert summary["document_grounding_improvement_next_action"]["learned_support_kind"] == "testimony"
    assert "trying testimony instead of authority" in summary["document_grounding_improvement_next_action"]["description"]


def test_build_intake_status_summary_can_infer_learned_claim_element_from_stats():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "formalization",
        "intake_readiness": {
            "score": 0.51,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "blockers": [],
            "criteria": {},
            "candidate_claim_count": 1,
            "canonical_fact_count": 1,
            "proof_lead_count": 1,
        },
        "document_provenance_summary": {
            "fact_backed_ratio": 0.25,
            "low_grounding_flag": True,
        },
        "document_grounding_improvement_summary": {
            "initial_fact_backed_ratio": 0.25,
            "final_fact_backed_ratio": 0.24,
            "fact_backed_ratio_delta": -0.01,
            "regressed_flag": True,
            "targeted_claim_elements": ["protected_activity"],
            "preferred_support_kinds": ["authority"],
            "recovery_attempted_flag": True,
        },
        "document_grounding_lane_outcome_summary": {
            "recommended_future_support_kind": "testimony",
            "learned_support_lane_attempted_flag": True,
            "learned_support_lane_effective_flag": False,
            "claim_element_stats": {
                "protected_activity": {
                    "count": 2,
                    "improved_count": 0,
                    "regressed_count": 1,
                    "stalled_count": 1,
                    "avg_fact_backed_ratio_delta": -0.04,
                },
                "causation": {
                    "count": 3,
                    "improved_count": 2,
                    "regressed_count": 0,
                    "stalled_count": 1,
                    "avg_fact_backed_ratio_delta": 0.18,
                },
            },
        },
        "alignment_evidence_tasks": [
            {
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "fallback_lanes": ["authority", "testimony"],
                "missing_fact_bundle": ["Complaint timing", "Manager knowledge"],
            }
        ],
        "next_action": {"action": "complete_evidence"},
    }

    summary = build_intake_status_summary(mediator)

    assert summary["document_grounding_improvement_next_action"]["action"] == "retarget_document_grounding"
    assert summary["document_grounding_improvement_next_action"]["suggested_claim_element_id"] == "causation"
    assert "toward causation" in summary["document_grounding_improvement_next_action"]["description"]


def test_build_intake_status_summary_retargets_after_failed_learned_lane():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "formalization",
        "intake_readiness": {
            "score": 0.51,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "blockers": [],
            "criteria": {},
            "candidate_claim_count": 1,
            "canonical_fact_count": 1,
            "proof_lead_count": 1,
        },
        "document_provenance_summary": {
            "fact_backed_ratio": 0.25,
            "low_grounding_flag": True,
        },
        "document_grounding_improvement_summary": {
            "initial_fact_backed_ratio": 0.25,
            "final_fact_backed_ratio": 0.24,
            "fact_backed_ratio_delta": -0.01,
            "regressed_flag": True,
            "targeted_claim_elements": ["protected_activity", "causation"],
            "preferred_support_kinds": ["authority"],
            "recovery_attempted_flag": True,
        },
        "document_grounding_lane_outcome_summary": {
            "recommended_future_support_kind": "testimony",
            "learned_support_lane_attempted_flag": True,
            "learned_support_lane_effective_flag": False,
        },
        "alignment_evidence_tasks": [
            {
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "fallback_lanes": ["authority", "testimony"],
                "missing_fact_bundle": ["Complaint timing", "Manager knowledge"],
            }
        ],
        "next_action": {"action": "complete_evidence"},
    }

    summary = build_intake_status_summary(mediator)

    assert summary["document_grounding_improvement_next_action"]["action"] == "retarget_document_grounding"
    assert summary["document_grounding_improvement_next_action"]["learned_support_kind"] == "testimony"
    assert summary["document_grounding_improvement_next_action"]["learned_support_lane_attempted_flag"] is True
    assert summary["document_grounding_improvement_next_action"]["learned_support_lane_effective_flag"] is False
    assert summary["document_grounding_improvement_next_action"]["suggested_claim_element_id"] == "causation"
    assert summary["document_grounding_improvement_next_action"]["alternate_claim_element_ids"] == ["causation"]
    assert "after trying testimony" in summary["document_grounding_improvement_next_action"]["description"]
    assert "toward causation" in summary["document_grounding_improvement_next_action"]["description"]


def test_build_intake_case_review_summary_returns_additive_structured_fields():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "candidate_claims": [
            {
                "claim_type": "retaliation",
                "confidence": 0.82,
                "ambiguity_flags": ["actor_identity"],
            },
            {
                "claim_type": "discrimination",
                "confidence": 0.74,
            },
        ],
        "intake_sections": {"chronology": {"status": "complete", "missing_items": []}},
        "canonical_fact_summary": {"count": 2, "facts": [{"fact_id": "fact_1"}]},
        "canonical_fact_intent_summary": {
            "count": 2,
            "question_objective_counts": {"satisfy_claim_requirement": 1},
            "expected_update_kind_counts": {"claim_element_fact": 1},
            "target_claim_type_counts": {"retaliation": 1},
            "target_element_id_counts": {"protected_activity": 1},
        },
        "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_1"}]},
        "blocker_follow_up_summary": {
            "blocking_item_count": 1,
            "blocking_objectives": ["exact_dates", "response_dates"],
            "blocking_items": [
                {
                    "blocker_id": "missing_response_timing",
                    "primary_objective": "response_dates",
                    "reason": "Response or non-response events are described without date anchors.",
                }
            ],
        },
        "open_items": [
            {
                "open_item_id": "blocker:missing_response_timing",
                "kind": "blocker_follow_up",
                "primary_objective": "response_dates",
                "reason": "Response or non-response events are described without date anchors.",
            }
        ],
        "proof_lead_intent_summary": {
            "count": 1,
            "question_objective_counts": {"identify_supporting_evidence": 1},
            "expected_update_kind_counts": {"proof_lead": 1},
            "target_claim_type_counts": {"retaliation": 1},
            "target_element_id_counts": {"protected_activity": 1},
        },
        "temporal_fact_registry_summary": {
            "count": 1,
            "facts": [{"temporal_fact_id": "fact_1", "temporal_status": "anchored"}],
        },
        "timeline_anchor_summary": {"count": 1, "anchors": [{"anchor_id": "timeline_anchor_001"}]},
        "temporal_relation_registry_summary": {
            "count": 1,
            "relations": [{"relation_id": "timeline_relation_001", "inference_basis": "normalized_temporal_context"}],
        },
        "timeline_relation_summary": {
            "count": 1,
            "relations": [{"relation_id": "timeline_relation_001", "relation_type": "before"}],
        },
        "temporal_issue_registry_summary": {
            "count": 1,
            "issues": [{"issue_id": "temporal_issue:relative_only_ordering:fact_3", "issue_type": "relative_only_ordering"}],
        },
        "timeline_consistency_summary": {
            "event_count": 2,
            "anchor_count": 1,
            "ordered_fact_count": 2,
            "unsequenced_fact_count": 0,
            "approximate_fact_count": 0,
            "range_fact_count": 0,
            "relation_count": 1,
            "relation_type_counts": {"before": 1},
            "missing_temporal_fact_ids": [],
            "relative_only_fact_ids": [],
            "warnings": [],
            "partial_order_ready": True,
        },
        "harm_profile": {"count": 1, "categories": ["economic"]},
        "remedy_profile": {"count": 1, "categories": ["monetary"]},
        "intake_matching_summary": {
            "claim_count": 1,
            "claims": {"retaliation": {"missing_requirement_count": 2, "matcher_confidence": 0.0}},
            "total_missing_requirements": 2,
            "max_missing_requirements": 2,
            "average_matcher_confidence": 0.0,
        },
        "intake_legal_targeting_summary": {
            "claim_count": 1,
            "total_open_elements": 2,
            "mapped_question_count": 1,
            "unmapped_claim_count": 0,
            "claims": {
                "retaliation": {
                    "missing_requirement_count": 2,
                    "matcher_confidence": 0.0,
                    "missing_requirement_names": ["Protected activity"],
                    "missing_requirement_element_ids": ["protected_activity", "causation"],
                    "mapped_candidates": [
                        {
                            "question": "What protected activity did you engage in?",
                            "target_element_id": "protected_activity",
                            "direct_legal_target_match": True,
                        }
                    ],
                    "unmapped_element_ids": ["causation"],
                }
            },
        },
        "intake_evidence_alignment_summary": {
            "claim_count": 1,
            "aligned_element_count": 1,
            "unsupported_shared_count": 1,
            "claims": {
                "retaliation": {
                    "intake_required_element_ids": ["protected_activity", "causation"],
                    "packet_element_statuses": {
                        "protected_activity": "unsupported",
                        "adverse_action": "supported",
                    },
                    "shared_elements": [
                        {
                            "element_id": "protected_activity",
                            "label": "Protected activity",
                            "blocking": True,
                            "support_status": "unsupported",
                        }
                    ],
                    "intake_only_element_ids": ["causation"],
                    "evidence_only_element_ids": ["adverse_action"],
                }
            },
        },
        "alignment_evidence_tasks": [
            {
                "action": "fill_temporal_chronology_gap",
                "task_id": "retaliation:protected_activity:fill_temporal_chronology_gap",
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "claim_element_label": "Protected activity",
                "support_status": "unsupported",
                "blocking": True,
                "preferred_support_kind": "testimony",
                "fallback_lanes": ["authority", "testimony"],
                "source_quality_target": "credible_testimony",
                "resolution_status": "awaiting_testimony",
                "resolution_notes": "",
                "temporal_rule_profile_id": "retaliation_temporal_profile_v1",
                "temporal_rule_status": "partial",
                "temporal_rule_blocking_reasons": [
                    "Retaliation chronology remains unresolved.",
                ],
                "temporal_rule_follow_ups": [
                    {
                        "lane": "clarify_with_complainant",
                        "reason": "Confirm the protected activity preceded the adverse action.",
                    }
                ],
            }
        ],
        "alignment_task_updates": [
            {
                "task_id": "retaliation:protected_activity:fill_temporal_chronology_gap",
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "resolution_status": "partially_addressed",
                "status": "active",
            }
        ],
        "alignment_task_update_history": [
            {
                "task_id": "retaliation:protected_activity:fill_temporal_chronology_gap",
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "resolution_status": "still_open",
                "status": "active",
                "evidence_sequence": 1,
            },
            {
                "task_id": "retaliation:protected_activity:fill_temporal_chronology_gap",
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "resolution_status": "partially_addressed",
                "status": "active",
                "evidence_sequence": 2,
            },
            {
                "task_id": "retaliation:protected_activity:fill_temporal_chronology_gap",
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "resolution_status": "promoted_to_testimony",
                "status": "resolved",
                "evidence_sequence": 3,
            },
            {
                "task_id": "retaliation:adverse_action:fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "adverse_action",
                "resolution_status": "promoted_to_document",
                "status": "resolved",
                "evidence_sequence": 4,
            }
        ],
        "recent_validation_outcome": {
            "claim_type": "retaliation",
            "claim_element_id": "protected_activity",
            "resolution_status": "resolved_supported",
            "current_support_status": "resolved_supported",
            "evidence_sequence": 4,
            "promotion_ref": "doc:retaliation:1",
            "promotion_kind": "document",
            "improved": True,
        },
        "alignment_promotion_drift_summary": {
            "promoted_count": 2,
            "resolved_supported_count": 0,
            "pending_conversion_count": 2,
            "proof_readiness_score": 0.5,
            "drift_ratio": 1.0,
            "drift_flag": True,
        },
        "alignment_validation_focus_summary": {
            "count": 2,
            "claim_type_counts": {"retaliation": 2},
            "promotion_kind_counts": {"testimony": 1, "document": 1},
            "primary_target": {
                "claim_type": "retaliation",
                "claim_element_id": "adverse_action",
                "promotion_kind": "document",
                "evidence_sequence": 4,
            },
            "targets": [
                {
                    "claim_type": "retaliation",
                    "claim_element_id": "adverse_action",
                    "promotion_kind": "document",
                    "evidence_sequence": 4,
                },
                {
                    "claim_type": "retaliation",
                    "claim_element_id": "protected_activity",
                    "promotion_kind": "testimony",
                    "evidence_sequence": 3,
                },
            ],
        },
        "evidence_workflow_action_queue": [
            {
                "rank": 1,
                "phase_name": "graph_analysis",
                "action": "Collect chronology support for protected activity.",
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "claim_element_label": "Protected activity",
                "focus_areas": ["protected_activity", "chronology"],
                "status": "warning",
            }
        ],
        "evidence_workflow_action_summary": {
            "count": 1,
            "phase_counts": {"graph_analysis": 1},
            "focus_area_counts": {"protected_activity": 1, "chronology": 1},
            "status_counts": {"warning": 1},
        },
        "workflow_targeting_summary": {
            "count": 4,
            "phase_counts": {
                "intake_questioning": 2,
                "graph_analysis": 1,
                "document_generation": 1,
            },
            "prioritized_phases": ["intake_questioning", "document_generation", "graph_analysis"],
            "shared_claim_element_counts": {"protected_activity": 2},
            "shared_focus_area_counts": {"timeline": 2},
        },
        "document_workflow_execution_summary": {
            "iteration_count": 2,
            "accepted_iteration_count": 1,
            "focus_section_counts": {"claims_for_relief": 1, "factual_allegations": 1},
            "top_support_kind_counts": {"workflow_targeting_claim_element": 1, "evidence_workflow_action": 1},
            "targeted_claim_element_counts": {"causation": 1, "protected_activity": 1},
            "preferred_support_kind_counts": {"testimony": 1, "document": 1},
            "first_focus_section": "claims_for_relief",
            "first_top_support_kind": "workflow_targeting_claim_element",
            "first_targeted_claim_element": "causation",
            "first_preferred_support_kind": "testimony",
        },
        "document_execution_drift_summary": {
            "drift_flag": True,
            "top_targeted_claim_element": "protected_activity",
            "first_executed_claim_element": "causation",
            "first_focus_section": "claims_for_relief",
            "first_preferred_support_kind": "testimony",
        },
        "next_action": {
            "action": "validate_promoted_support",
            "pending_conversion_count": 2,
            "promoted_count": 2,
            "drift_summary": {
                "drift_flag": True,
                "drift_ratio": 1.0,
            },
        },
        "question_candidate_summary": {
            "count": 1,
            "candidates": [{"candidate_source": "intake_proof_gap"}],
            "source_counts": {"intake_proof_gap": 1},
            "question_goal_counts": {"identify_supporting_proof": 1},
            "phase1_section_counts": {"proof_leads": 1},
            "blocking_level_counts": {"important": 1},
            "intake_priority_expected": ["anchor_adverse_action", "timeline"],
            "intake_priority_covered": ["anchor_adverse_action"],
            "intake_priority_uncovered": ["timeline"],
            "intake_priority_counts": {"anchor_adverse_action": 1},
        },
        "adversarial_intake_priority_summary": {
            "expected_objectives": ["anchor_adverse_action", "timeline"],
            "covered_objectives": ["anchor_adverse_action"],
            "uncovered_objectives": ["timeline"],
            "objective_question_counts": {"anchor_adverse_action": 1, "timeline": 0},
        },
        "complainant_summary_confirmation": {
            "status": "confirmed",
            "confirmed": True,
            "confirmation_source": "complainant",
        },
        "intake_readiness": {
            "contradictions": [
                {
                    "contradiction_id": "ctr_1",
                    "summary": "Timeline conflict",
                    "recommended_resolution_lane": "request_document",
                    "current_resolution_status": "open",
                    "external_corroboration_required": True,
                    "affected_claim_types": ["retaliation"],
                    "severity": "blocking",
                }
            ]
        },
        "claim_support_packet_summary": {
            "claim_count": 1,
            "element_count": 2,
            "status_counts": {"supported": 1, "unsupported": 1},
            "recommended_actions": ["collect_documentary_support"],
            "supported_blocking_element_ratio": 0.5,
            "credible_support_ratio": 0.5,
            "draft_ready_element_ratio": 0.5,
            "high_quality_parse_ratio": 0.5,
            "reviewable_escalation_ratio": 0.0,
            "claim_support_reviewable_escalation_count": 0,
            "claim_support_unresolved_without_review_path_count": 1,
            "proof_readiness_score": 0.5,
            "evidence_completion_ready": False,
        },
    }

    summary = build_intake_case_review_summary(mediator)

    assert summary["candidate_claims"][0]["claim_type"] == "retaliation"
    assert summary["candidate_claim_summary"] == {
        "count": 2,
        "claim_types": ["retaliation", "discrimination"],
        "average_confidence": 0.78,
        "top_claim_type": "retaliation",
        "top_confidence": 0.82,
        "ambiguous_claim_count": 1,
        "ambiguity_flag_count": 1,
        "ambiguity_flag_counts": {"actor_identity": 1},
        "close_leading_claims": True,
    }
    assert summary["intake_sections"]["chronology"]["status"] == "complete"
    assert summary["canonical_fact_summary"]["count"] == 2
    assert summary["canonical_fact_intent_summary"]["question_objective_counts"]["satisfy_claim_requirement"] == 1
    assert summary["proof_lead_summary"]["count"] == 1
    assert summary["blocker_follow_up_summary"]["blocking_objectives"] == ["exact_dates", "response_dates"]
    assert summary["open_items"][0]["primary_objective"] == "response_dates"
    assert summary["proof_lead_intent_summary"]["question_objective_counts"]["identify_supporting_evidence"] == 1
    assert summary["event_ledger_summary"] == {
        "count": 1,
        "events": [{"temporal_fact_id": "fact_1", "temporal_status": "anchored"}],
    }
    assert summary["event_ledger"] == []
    assert summary["temporal_fact_registry_summary"] == {
        "count": 1,
        "facts": [{"temporal_fact_id": "fact_1", "temporal_status": "anchored"}],
    }
    assert summary["temporal_fact_registry"] == []
    assert summary["timeline_anchor_summary"]["count"] == 1
    assert summary["timeline_anchors"] == []
    assert summary["temporal_relation_registry_summary"] == {
        "count": 1,
        "relations": [{"relation_id": "timeline_relation_001", "inference_basis": "normalized_temporal_context"}],
    }
    assert summary["temporal_relation_registry"] == []
    assert summary["timeline_relation_summary"] == {
        "count": 1,
        "relations": [{"relation_id": "timeline_relation_001", "relation_type": "before"}],
    }
    assert summary["timeline_relations"] == []
    assert summary["temporal_issue_registry"] == []
    assert summary["temporal_issue_registry_summary"] == {
        "count": 1,
        "issues": [{"issue_id": "temporal_issue:relative_only_ordering:fact_3", "issue_type": "relative_only_ordering"}],
        "issue_ids": ["temporal_issue:relative_only_ordering:fact_3"],
        "status_counts": {},
        "severity_counts": {},
        "lane_counts": {},
        "issue_type_counts": {"relative_only_ordering": 1},
        "claim_type_counts": {},
        "element_tag_counts": {},
        "missing_temporal_predicates": [],
        "required_provenance_kinds": [],
        "resolved_count": 0,
        "unresolved_count": 1,
    }
    assert summary["intake_chronology_readiness"] == {
        "contract_version": "intake_chronology_readiness.v1",
        "event_count": 1,
        "anchored_event_count": 1,
        "unanchored_event_count": 0,
        "relation_count": 1,
        "issue_count": 1,
        "blocking_issue_count": 0,
        "open_issue_count": 1,
        "resolved_issue_count": 0,
        "issue_ids": ["temporal_issue:relative_only_ordering:fact_3"],
        "blocking_issue_ids": [],
        "missing_temporal_predicates": [],
        "missing_temporal_predicate_count": 0,
        "required_provenance_kinds": [],
        "required_provenance_kind_count": 0,
        "resolution_lane_counts": {},
        "issue_type_counts": {"relative_only_ordering": 1},
        "issue_status_counts": {},
        "anchor_coverage_ratio": 1.0,
        "predicate_coverage_ratio": 1.0,
        "provenance_coverage_ratio": 1.0,
        "ready_for_temporal_formalization": False,
    }
    assert summary["timeline_consistency_summary"] == {
        "event_count": 2,
        "anchor_count": 1,
        "ordered_fact_count": 2,
        "unsequenced_fact_count": 0,
        "approximate_fact_count": 0,
        "range_fact_count": 0,
        "relation_count": 1,
        "relation_type_counts": {"before": 1},
        "missing_temporal_fact_ids": [],
        "relative_only_fact_ids": [],
        "warnings": [],
        "partial_order_ready": True,
    }
    assert summary["harm_profile"]["categories"] == ["economic"]
    assert summary["remedy_profile"]["categories"] == ["monetary"]
    assert summary["intake_matching_summary"]["claim_count"] == 1
    assert summary["intake_legal_targeting_summary"]["claim_count"] == 1
    assert summary["intake_legal_targeting_summary"]["mapped_question_count"] == 1
    assert summary["intake_legal_targeting_summary"]["claims"]["retaliation"]["mapped_candidates"][0]["target_element_id"] == "protected_activity"
    assert summary["intake_evidence_alignment_summary"]["aligned_element_count"] == 1
    assert summary["intake_evidence_alignment_summary"]["claims"]["retaliation"]["intake_only_element_ids"] == ["causation"]
    assert summary["alignment_evidence_tasks"][0]["claim_element_id"] == "protected_activity"
    assert summary["alignment_evidence_tasks"][0]["fallback_lanes"] == ["authority", "testimony"]
    assert summary["alignment_evidence_tasks"][0]["source_quality_target"] == "credible_testimony"
    assert summary["alignment_task_summary"] == {
        "count": 1,
        "status_counts": {"unsupported": 1},
        "resolution_status_counts": {"awaiting_testimony": 1},
        "temporal_gap_task_count": 1,
        "temporal_gap_targeted_task_count": 1,
        "temporal_rule_status_counts": {"partial": 1},
        "temporal_rule_blocking_reason_counts": {"Retaliation chronology remains unresolved.": 1},
        "temporal_resolution_status_counts": {"awaiting_testimony": 1},
    }
    assert summary["alignment_task_updates"][0]["resolution_status"] == "partially_addressed"
    assert summary["alignment_task_update_history"][1]["evidence_sequence"] == 2
    assert summary["alignment_task_update_summary"]["count"] == 4
    assert summary["alignment_task_update_summary"]["promoted_testimony_count"] == 1
    assert summary["alignment_task_update_summary"]["promoted_document_count"] == 1
    assert summary["alignment_task_update_summary"]["resolution_status_counts"]["promoted_to_testimony"] == 1
    assert summary["alignment_task_update_summary"]["temporal_gap_task_count"] == 3
    assert summary["alignment_task_update_summary"]["temporal_gap_targeted_task_count"] == 3
    assert summary["alignment_task_update_summary"]["temporal_rule_status_counts"] == {"partial": 3}
    assert summary["alignment_task_update_summary"]["temporal_rule_blocking_reason_counts"] == {
        "Retaliation chronology remains unresolved.": 3,
    }
    assert summary["alignment_task_update_summary"]["temporal_resolution_status_counts"] == {
        "still_open": 1,
        "partially_addressed": 1,
        "promoted_to_testimony": 1,
    }
    assert summary["alignment_validation_focus_summary"]["count"] == 2
    assert summary["alignment_validation_focus_summary"]["primary_target"]["claim_element_id"] == "adverse_action"
    assert summary["alignment_validation_focus_summary"]["promotion_kind_counts"] == {
        "testimony": 1,
        "document": 1,
    }
    assert summary["evidence_workflow_action_queue"][0]["claim_element_id"] == "protected_activity"
    assert summary["evidence_workflow_action_summary"]["count"] == 1
    assert summary["evidence_workflow_action_summary"]["phase_counts"] == {"graph_analysis": 1}
    assert summary["workflow_targeting_summary"]["count"] == 4
    assert summary["workflow_targeting_summary"]["phase_counts"]["intake_questioning"] == 2
    assert summary["document_workflow_execution_summary"]["iteration_count"] == 2
    assert summary["document_workflow_execution_summary"]["first_targeted_claim_element"] == "causation"
    assert summary["document_drafting_next_action"] == {
        "action": "realign_document_drafting",
        "phase_name": "document_generation",
        "description": "Realign drafting to protected_activity before further revisions; the draft loop acted on causation first.",
        "claim_element_id": "protected_activity",
        "executed_claim_element_id": "causation",
        "focus_section": "claims_for_relief",
        "preferred_support_kind": "testimony",
    }
    assert summary["recent_validation_outcome"]["resolution_status"] == "resolved_supported"
    assert summary["recent_validation_outcome"]["improved"] is True
    assert summary["alignment_promotion_drift_summary"]["promoted_count"] == 2
    assert summary["alignment_promotion_drift_summary"]["drift_flag"] is True
    assert summary["next_action"]["action"] == "validate_promoted_support"
    assert summary["question_candidate_summary"]["count"] == 1
    assert summary["question_candidate_summary"]["source_counts"]["intake_proof_gap"] == 1
    assert summary["question_candidate_summary"]["intake_priority_uncovered"] == ["timeline"]
    assert summary["adversarial_intake_priority_summary"]["covered_objectives"] == ["anchor_adverse_action"]
    assert summary["adversarial_intake_priority_summary"]["objective_question_counts"]["timeline"] == 0
    assert summary["complainant_summary_confirmation"]["confirmed"] is True
    assert summary["contradiction_summary"] == {
        "count": 1,
        "lane_counts": {"request_document": 1},
        "status_counts": {"open": 1},
        "severity_counts": {"blocking": 1},
        "corroboration_required_count": 1,
        "affected_claim_type_counts": {"retaliation": 1},
        "affected_element_counts": {},
    }
    assert summary["claim_support_packet_summary"]["claim_count"] == 1
    assert summary["claim_support_packet_summary"]["supported_blocking_element_ratio"] == 0.5
    assert summary["claim_support_packet_summary"]["proof_readiness_score"] == 0.5
    assert summary["claim_support_packet_summary"]["claim_support_unresolved_without_review_path_count"] == 1
    assert summary["claim_support_packet_summary"]["temporal_gap_task_count"] == 1
    assert summary["claim_support_packet_summary"]["temporal_gap_targeted_task_count"] == 1
    assert summary["claim_support_packet_summary"]["temporal_rule_status_counts"] == {"partial": 1}
    assert summary["claim_support_packet_summary"]["temporal_rule_blocking_reason_counts"] == {
        "Retaliation chronology remains unresolved.": 1,
    }
    assert summary["claim_support_packet_summary"]["temporal_resolution_status_counts"] == {
        "awaiting_testimony": 1,
    }
    assert summary["claim_support_packet_summary"]["evidence_completion_ready"] is False


def test_build_intake_status_summary_preserves_rich_contradiction_workflow_fields():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "intake_readiness": {
            "score": 0.5,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 1,
            "blockers": ["blocking_contradiction"],
            "contradictions": [
                {
                    "contradiction_id": "ctr_1",
                    "topic": "timeline",
                    "existing_text": "It happened on January 20, 2026.",
                    "new_text": "It happened on February 2, 2026.",
                    "severity": "blocking",
                    "recommended_resolution_lane": "request_document",
                    "current_resolution_status": "open",
                    "external_corroboration_required": True,
                    "affected_claim_types": ["retaliation"],
                    "affected_element_ids": ["causation"],
                }
            ],
        },
    }

    summary = build_intake_status_summary(mediator)

    assert summary["contradictions"][0]["contradiction_id"] == "ctr_1"
    assert summary["contradiction_summary"] == {
        "count": 1,
        "lane_counts": {"request_document": 1},
        "status_counts": {"open": 1},
        "severity_counts": {"blocking": 1},
        "corroboration_required_count": 1,
        "affected_claim_type_counts": {"retaliation": 1},
        "affected_element_counts": {"causation": 1},
    }
    assert summary["contradictions"][0]["recommended_resolution_lane"] == "request_document"
    assert summary["contradictions"][0]["current_resolution_status"] == "open"
    assert summary["contradictions"][0]["external_corroboration_required"] is True
    assert summary["contradictions"][0]["affected_claim_types"] == ["retaliation"]
    assert summary["contradictions"][0]["affected_element_ids"] == ["causation"]


def test_build_intake_status_summary_includes_confirmed_handoff_metadata():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "intake_readiness": {
            "ready_to_advance": True,
        },
        "complainant_summary_confirmation": {
            "status": "confirmed",
            "confirmed": True,
            "confirmed_at": "2026-03-17T10:00:00+00:00",
            "confirmation_source": "dashboard",
            "confirmed_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 2,
                "proof_lead_count": 1,
            },
        },
    }

    summary = build_intake_status_summary(mediator)

    assert summary["intake_summary_handoff"] == {
        "current_phase": "intake",
        "ready_to_advance": True,
        "complainant_summary_confirmation": {
            "status": "confirmed",
            "confirmed": True,
            "confirmed_at": "2026-03-17T10:00:00+00:00",
            "confirmation_source": "dashboard",
            "confirmed_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 2,
                "proof_lead_count": 1,
            },
        },
    }


def test_build_intake_case_review_summary_includes_confirmed_handoff_metadata():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "intake_readiness": {
            "ready_to_advance": True,
            "contradictions": [],
        },
        "complainant_summary_confirmation": {
            "status": "confirmed",
            "confirmed": True,
            "confirmed_at": "2026-03-17T10:00:00+00:00",
            "confirmation_source": "dashboard",
            "confirmed_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 2,
                "proof_lead_count": 1,
            },
        },
    }

    summary = build_intake_case_review_summary(mediator)

    assert summary["intake_summary_handoff"] == {
        "current_phase": "intake",
        "ready_to_advance": True,
        "complainant_summary_confirmation": {
            "status": "confirmed",
            "confirmed": True,
            "confirmed_at": "2026-03-17T10:00:00+00:00",
            "confirmation_source": "dashboard",
            "confirmed_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 2,
                "proof_lead_count": 1,
            },
        },
    }


def test_build_intake_status_summary_preserves_authored_chronology_readiness():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "intake_readiness": {
            "score": 0.5,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "blockers": [],
            "criteria": {},
            "candidate_claim_count": 1,
            "canonical_fact_count": 2,
            "proof_lead_count": 1,
        },
        "intake_chronology_readiness": {
            "contract_version": "intake_chronology_readiness.v1",
            "event_count": 2,
            "anchored_event_count": 1,
            "unanchored_event_count": 1,
            "relation_count": 1,
            "issue_count": 1,
            "blocking_issue_count": 1,
            "open_issue_count": 1,
            "resolved_issue_count": 0,
            "issue_ids": ["temporal_issue:missing_anchor:fact_2"],
            "blocking_issue_ids": ["temporal_issue:missing_anchor:fact_2"],
            "missing_temporal_predicates": ["Anchored(fact_2)"],
            "missing_temporal_predicate_count": 1,
            "required_provenance_kinds": ["testimony_record"],
            "required_provenance_kind_count": 1,
            "resolution_lane_counts": {"clarify_with_complainant": 1},
            "issue_type_counts": {"missing_anchor": 1},
            "issue_status_counts": {"open": 1},
            "anchor_coverage_ratio": 0.5,
            "predicate_coverage_ratio": 0.0,
            "provenance_coverage_ratio": 0.0,
            "ready_for_temporal_formalization": False,
        },
    }

    summary = build_intake_status_summary(mediator)

    assert summary["intake_chronology_readiness"] == mediator.get_three_phase_status.return_value["intake_chronology_readiness"]


    def test_build_intake_case_review_summary_preserves_precomputed_alignment_task_summary():
        mediator = Mock()
        mediator.get_three_phase_status.return_value = {
            "alignment_evidence_tasks": [
                {
                    "task_id": "retaliation:causation:fill_evidence_gaps",
                    "claim_type": "retaliation",
                    "claim_element_id": "causation",
                    "claim_element_label": "Causal connection",
                    "action": "fill_evidence_gaps",
                    "support_status": "unsupported",
                    "resolution_status": "still_open",
                }
            ],
            "alignment_task_summary": {
                "count": 1,
                "status_counts": {"unsupported": 1},
                "resolution_status_counts": {"still_open": 1},
                "temporal_gap_task_count": 1,
                "temporal_gap_targeted_task_count": 1,
                "temporal_rule_status_counts": {"partial": 1},
                "temporal_rule_blocking_reason_counts": {"Need retaliation chronology sequencing.": 1},
                "temporal_resolution_status_counts": {"still_open": 1},
            },
            "claim_support_packet_summary": {
                "claim_count": 1,
                "proof_readiness_score": 0.25,
            },
        }

        summary = build_intake_case_review_summary(mediator)

        assert summary["alignment_task_summary"] == {
            "count": 1,
            "status_counts": {"unsupported": 1},
            "resolution_status_counts": {"still_open": 1},
            "temporal_gap_task_count": 1,
            "temporal_gap_targeted_task_count": 1,
            "temporal_rule_status_counts": {"partial": 1},
            "temporal_rule_blocking_reason_counts": {"Need retaliation chronology sequencing.": 1},
            "temporal_resolution_status_counts": {"still_open": 1},
        }
        assert summary["claim_support_packet_summary"]["temporal_gap_task_count"] == 1
        assert summary["claim_support_packet_summary"]["temporal_rule_blocking_reason_counts"] == {
            "Need retaliation chronology sequencing.": 1,
        }
