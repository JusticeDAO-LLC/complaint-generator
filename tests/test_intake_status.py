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
        "proof_lead_intent_summary": {
            "count": 1,
            "question_objective_counts": {"identify_supporting_evidence": 1},
            "expected_update_kind_counts": {"proof_lead": 1},
            "target_claim_type_counts": {"retaliation": 1},
            "target_element_id_counts": {"protected_activity": 1},
        },
        "timeline_anchor_summary": {"count": 1, "anchors": [{"anchor_id": "timeline_anchor_001"}]},
        "timeline_relation_summary": {
            "count": 1,
            "relations": [{"relation_id": "timeline_relation_001", "relation_type": "before"}],
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
                "action": "fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "claim_element_label": "Protected activity",
                "support_status": "unsupported",
                "blocking": True,
                "preferred_support_kind": "evidence",
                "fallback_lanes": ["authority", "testimony"],
                "source_quality_target": "high_quality_document",
                "resolution_status": "still_open",
                "resolution_notes": "",
            }
        ],
        "alignment_task_updates": [
            {
                "task_id": "retaliation:protected_activity:fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "resolution_status": "partially_addressed",
                "status": "active",
            }
        ],
        "alignment_task_update_history": [
            {
                "task_id": "retaliation:protected_activity:fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "resolution_status": "still_open",
                "status": "active",
                "evidence_sequence": 1,
            },
            {
                "task_id": "retaliation:protected_activity:fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "protected_activity",
                "resolution_status": "partially_addressed",
                "status": "active",
                "evidence_sequence": 2,
            }
        ],
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
    assert summary["proof_lead_intent_summary"]["question_objective_counts"]["identify_supporting_evidence"] == 1
    assert summary["timeline_anchor_summary"]["count"] == 1
    assert summary["timeline_relation_summary"] == {
        "count": 1,
        "relations": [{"relation_id": "timeline_relation_001", "relation_type": "before"}],
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
    assert summary["alignment_evidence_tasks"][0]["source_quality_target"] == "high_quality_document"
    assert summary["alignment_task_updates"][0]["resolution_status"] == "partially_addressed"
    assert summary["alignment_task_update_history"][1]["evidence_sequence"] == 2
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
