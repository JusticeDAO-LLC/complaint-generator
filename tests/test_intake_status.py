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
            "contradictions": [{"summary": "Timeline conflict"}],
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
        "blockers": ["missing_proof_leads"],
        "contradictions": [
            {
                "summary": "Timeline conflict",
                "left_text": "",
                "right_text": "",
                "question": "",
                "severity": "",
                "category": "",
            }
        ],
    }


def test_build_intake_case_review_summary_returns_additive_structured_fields():
    mediator = Mock()
    mediator.get_three_phase_status.return_value = {
        "candidate_claims": [{"claim_type": "retaliation"}],
        "intake_sections": {"chronology": {"status": "complete", "missing_items": []}},
        "canonical_fact_summary": {"count": 2, "facts": [{"fact_id": "fact_1"}]},
        "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_1"}]},
        "intake_matching_summary": {
            "claim_count": 1,
            "claims": {"retaliation": {"missing_requirement_count": 2, "matcher_confidence": 0.0}},
            "total_missing_requirements": 2,
            "max_missing_requirements": 2,
            "average_matcher_confidence": 0.0,
        },
        "question_candidate_summary": {
            "count": 1,
            "candidates": [{"candidate_source": "intake_proof_gap"}],
            "source_counts": {"intake_proof_gap": 1},
            "question_goal_counts": {"identify_supporting_proof": 1},
            "phase1_section_counts": {"proof_leads": 1},
            "blocking_level_counts": {"important": 1},
        },
        "claim_support_packet_summary": {
            "claim_count": 1,
            "element_count": 2,
            "status_counts": {"supported": 1, "unsupported": 1},
            "recommended_actions": ["collect_documentary_support"],
        },
    }

    summary = build_intake_case_review_summary(mediator)

    assert summary["candidate_claims"] == [{"claim_type": "retaliation"}]
    assert summary["intake_sections"]["chronology"]["status"] == "complete"
    assert summary["canonical_fact_summary"]["count"] == 2
    assert summary["proof_lead_summary"]["count"] == 1
    assert summary["intake_matching_summary"]["claim_count"] == 1
    assert summary["question_candidate_summary"]["count"] == 1
    assert summary["question_candidate_summary"]["source_counts"]["intake_proof_gap"] == 1
    assert summary["claim_support_packet_summary"]["claim_count"] == 1
