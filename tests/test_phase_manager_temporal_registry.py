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


def test_intake_readiness_blocks_on_incomplete_chronology_coverage():
    pm = PhaseManager()

    pm.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", {})
    pm.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", {})
    pm.update_phase_data(ComplaintPhase.INTAKE, "remaining_gaps", 0)
    pm.update_phase_data(ComplaintPhase.INTAKE, "denoising_converged", True)
    pm.update_phase_data(
        ComplaintPhase.INTAKE,
        "intake_case_file",
        {
            "candidate_claims": [{"claim_type": "retaliation", "confidence": 0.9}],
            "canonical_facts": [{"fact_id": "fact_001"}],
            "proof_leads": [{"lead_id": "lead_001"}],
            "intake_sections": {
                "chronology": {"status": "complete", "missing_items": []},
                "actors": {"status": "complete", "missing_items": []},
                "conduct": {"status": "complete", "missing_items": []},
                "harm": {"status": "complete", "missing_items": []},
                "remedy": {"status": "complete", "missing_items": []},
                "proof_leads": {"status": "complete", "missing_items": []},
                "claim_elements": {"status": "complete", "missing_items": []},
            },
            "event_ledger": [
                {"event_id": "fact_001", "timeline_anchor_ids": []},
            ],
            "temporal_issue_registry": [
                {
                    "issue_id": "temporal_issue_001",
                    "status": "open",
                    "blocking": True,
                    "missing_temporal_predicates": ["Anchored(fact_001)"],
                    "required_provenance_kinds": ["document_artifact"],
                }
            ],
        },
    )

    readiness = pm.get_intake_readiness()

    assert readiness["ready"] is False
    assert readiness["criteria"]["chronology_anchor_coverage_complete"] is False
    assert "chronology_anchor_coverage_incomplete" in readiness["blockers"]
    assert "chronology_predicate_coverage_incomplete" in readiness["blockers"]
    assert "chronology_provenance_coverage_incomplete" in readiness["blockers"]
    assert pm.get_phase_data(ComplaintPhase.INTAKE, "intake_chronology_readiness")["anchor_coverage_ratio"] == 0.0
    assert pm.get_phase_data(ComplaintPhase.INTAKE, "intake_chronology_failure_reasons")


def test_evidence_phase_surfaces_chronology_coverage_ratios_and_failure_reasons_from_task_snapshots():
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
                "intake_chronology_readiness": {
                    "anchor_coverage_ratio": 0.5,
                    "predicate_coverage_ratio": 0.25,
                    "provenance_coverage_ratio": 0.5,
                    "ready_for_temporal_formalization": False,
                },
            }
        ],
    )

    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "chronology_anchor_coverage_ratio") == 0.5
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "chronology_predicate_coverage_ratio") == 0.25
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "chronology_provenance_coverage_ratio") == 0.5
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "chronology_readiness_score") == 0.417
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "chronology_ready_for_formalization") is False
    assert pm.get_phase_data(ComplaintPhase.EVIDENCE, "proof_readiness_score") == 0.848
    assert any(
        reason == "anchor coverage ratio remains 0.50"
        for reason in pm.get_phase_data(ComplaintPhase.EVIDENCE, "chronology_failure_reasons")
    )
