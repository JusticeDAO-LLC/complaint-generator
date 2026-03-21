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
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "evidence_completion_ready") is False
    assert pm.is_phase_complete(ComplaintPhase.EVIDENCE) is False
