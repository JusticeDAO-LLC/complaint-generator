from complaint_phases.phase_manager import ComplaintPhase, PhaseManager


def test_evidence_phase_blocks_on_unresolved_temporal_issue_registry_entries():
    pm = PhaseManager()
    pm.current_phase = ComplaintPhase.EVIDENCE

    pm.update_phase_data(
        ComplaintPhase.EVIDENCE,
        "claim_support_packets",
        {
            "retaliation": {
                "claim_type": "retaliation",
                "elements": [
                    {
                        "element_id": "causation",
                        "support_status": "supported",
                        "recommended_next_step": "",
                        "contradiction_count": 0,
                    }
                ],
            }
        },
    )
    pm.update_phase_data(
        ComplaintPhase.EVIDENCE,
        "temporal_issue_registry",
        [
            {
                "temporal_issue_id": "temporal_issue_registry_001",
                "status": "open",
            },
            {
                "temporal_issue_id": "temporal_issue_registry_002",
                "status": "resolved",
            },
        ],
    )

    assert pm.get_phase_data(
        ComplaintPhase.EVIDENCE,
        "claim_support_unresolved_temporal_issue_ids",
    ) == ["temporal_issue_registry_001"]
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "proof_readiness_score") == 0.97
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "evidence_completion_ready") is False
    assert pm.is_phase_complete(ComplaintPhase.EVIDENCE) is False


def test_evidence_phase_penalizes_open_temporal_tasks_missing_anchor_predicate_and_provenance_coverage():
    pm = PhaseManager()
    pm.current_phase = ComplaintPhase.EVIDENCE

    pm.update_phase_data(
        ComplaintPhase.EVIDENCE,
        "claim_support_packets",
        {
            "retaliation": {
                "claim_type": "retaliation",
                "elements": [
                    {
                        "element_id": "causation",
                        "support_status": "supported",
                        "recommended_next_step": "",
                        "contradiction_count": 0,
                    }
                ],
            }
        },
    )
    pm.update_phase_data(
        ComplaintPhase.EVIDENCE,
        "alignment_evidence_tasks",
        [
            {
                "task_id": "retaliation:causation:fill_temporal_chronology_gap",
                "action": "fill_temporal_chronology_gap",
                "claim_type": "retaliation",
                "claim_element_id": "causation",
                "support_status": "partially_supported",
                "resolution_status": "awaiting_testimony",
                "temporal_rule_status": "partial",
                "missing_temporal_predicates": ["Before(fact_001,fact_termination)"],
                "required_provenance_kinds": ["testimony_record", "document_artifact"],
            }
        ],
    )

    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "temporal_gap_task_count") == 1
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "temporal_missing_anchor_task_count") == 1
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "temporal_missing_predicate_count") == 1
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "temporal_required_provenance_kind_count") == 2
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "proof_readiness_score") == 0.935
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "evidence_completion_ready") is False
    assert pm.is_phase_complete(ComplaintPhase.EVIDENCE) is False
