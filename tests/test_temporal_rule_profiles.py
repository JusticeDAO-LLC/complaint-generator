"""Focused regression tests for temporal rule profiles (T6 coverage).

These tests protect the retaliation temporal rule profile against payload drift and
serve as gold cases for T6 in the temporal-timeline proof execution backlog:

  T6-1  Satisfied: full before-relation present (legal sufficiency gold case)
  T6-2  Satisfied: protected_activity element anchored
  T6-3  Satisfied: adverse_action element anchored
  T6-4  Failed: reverse-before relation (explicit ordering contradiction)
  T6-5  Contradictory-date downgrade for causal_connection
  T6-6  Relative-only ordering warning for protected_activity element
  T6-7  Relative-only ordering warning for adverse_action element
  T6-8  Limitations-risk warning triggered by issue registry entry
  T6-9  Limitations-risk warning triggered by reference_date computation
  T6-10 Non-retaliation claim returns not_applicable
  T6-11 Unknown element returns not_targeted
  T6-12 Missing protected-activity event blocks causal_connection
  T6-13 Missing adverse-action event blocks causal_connection
"""

from __future__ import annotations

from datetime import date

import pytest

from complaint_analysis.temporal_rule_profiles import evaluate_temporal_rule_profile


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_PROTECTED_FACT = {
    "fact_id": "fact_pa",
    "element_tags": ["protected_activity"],
    "temporal_context": {"start_date": "2025-03-01"},
}

_ADVERSE_FACT = {
    "fact_id": "fact_aa",
    "element_tags": ["adverse_action"],
    "temporal_context": {"start_date": "2025-06-15"},
}

_BEFORE_RELATION = {
    "relation_id": "rel_pa_before_aa",
    "source_fact_id": "fact_pa",
    "target_fact_id": "fact_aa",
    "relation_type": "before",
}

_REVERSE_BEFORE_RELATION = {
    "relation_id": "rel_aa_before_pa",
    "source_fact_id": "fact_aa",
    "target_fact_id": "fact_pa",
    "relation_type": "before",
}

_CAUSATION_ELEMENT = {
    "element_id": "causal_connection",
    "element_text": "Causal connection",
}

_PROTECTED_ACTIVITY_ELEMENT = {
    "element_id": "protected_activity",
    "element_text": "Protected activity",
}

_ADVERSE_ACTION_ELEMENT = {
    "element_id": "adverse_action",
    "element_text": "Adverse action",
}


# ---------------------------------------------------------------------------
# T6-1  Gold case: satisfied ordering (before-relation present)
# ---------------------------------------------------------------------------

def test_t6_1_satisfied_when_before_relation_confirmed():
    """Full before-relation yields satisfied status — legal sufficiency gold case."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _CAUSATION_ELEMENT,
        {
            "temporal_facts": [_PROTECTED_FACT, _ADVERSE_FACT],
            "temporal_relations": [_BEFORE_RELATION],
            "temporal_issues": [],
        },
    )

    assert profile["available"] is True
    assert profile["evaluated"] is True
    assert profile["status"] == "satisfied"
    assert profile["element_role"] == "causal_connection"
    assert profile["rule_frame_id"] == "retaliation_temporal_frame"
    assert profile["blocking_reasons"] == []
    assert profile["matched_relation_ids"] == ["rel_pa_before_aa"]
    assert profile["has_contradictory_dates"] is False
    assert profile["has_limitations_risk"] is False


# ---------------------------------------------------------------------------
# T6-2  Satisfied: protected_activity element anchored
# ---------------------------------------------------------------------------

def test_t6_2_protected_activity_satisfied_when_anchored():
    """Protected-activity element with a start_date anchor yields satisfied."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _PROTECTED_ACTIVITY_ELEMENT,
        {
            "temporal_facts": [_PROTECTED_FACT],
            "temporal_relations": [],
            "temporal_issues": [],
        },
    )

    assert profile["status"] == "satisfied"
    assert profile["element_role"] == "protected_activity"
    assert profile["blocking_reasons"] == []
    assert profile["matched_fact_ids"] == ["fact_pa"]
    assert profile["has_contradictory_dates"] is False
    assert profile["has_limitations_risk"] is False


# ---------------------------------------------------------------------------
# T6-3  Satisfied: adverse_action element anchored
# ---------------------------------------------------------------------------

def test_t6_3_adverse_action_satisfied_when_anchored():
    """Adverse-action element with a start_date anchor yields satisfied."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _ADVERSE_ACTION_ELEMENT,
        {
            "temporal_facts": [_ADVERSE_FACT],
            "temporal_relations": [],
            "temporal_issues": [],
        },
    )

    assert profile["status"] == "satisfied"
    assert profile["element_role"] == "adverse_action"
    assert profile["blocking_reasons"] == []
    assert profile["matched_fact_ids"] == ["fact_aa"]
    assert profile["has_limitations_risk"] is False


# ---------------------------------------------------------------------------
# T6-4  Failed: reverse-before relation (explicit ordering contradiction)
# ---------------------------------------------------------------------------

def test_t6_4_failed_when_reverse_before_relation():
    """Explicit reverse-before relation means adverse action predates protected activity — failed."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _CAUSATION_ELEMENT,
        {
            "temporal_facts": [_PROTECTED_FACT, _ADVERSE_FACT],
            "temporal_relations": [_REVERSE_BEFORE_RELATION],
            "temporal_issues": [],
        },
    )

    assert profile["status"] == "failed"
    assert profile["element_role"] == "causal_connection"
    assert any(
        "reverse-order" in reason or "before the protected activity" in reason
        for reason in profile["blocking_reasons"]
    )
    assert profile["has_contradictory_dates"] is False


def test_t6_4b_failed_when_temporal_reverse_before_issue():
    """temporal_reverse_before issue type also triggers failed status."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _CAUSATION_ELEMENT,
        {
            "temporal_facts": [_PROTECTED_FACT, _ADVERSE_FACT],
            "temporal_relations": [],
            "temporal_issues": [
                {
                    "issue_id": "temporal_issue:reverse_001",
                    "issue_type": "temporal_reverse_before",
                    "category": "temporal_reverse_before",
                }
            ],
        },
    )

    assert profile["status"] == "failed"


# ---------------------------------------------------------------------------
# T6-5  Contradictory-date: downgrades satisfied causal_connection
# ---------------------------------------------------------------------------

def test_t6_5_contradictory_dates_downgrades_satisfied_causal_connection():
    """contradictory_dates issue downgrades a satisfied causal_connection to partial."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _CAUSATION_ELEMENT,
        {
            "temporal_facts": [_PROTECTED_FACT, _ADVERSE_FACT],
            "temporal_relations": [_BEFORE_RELATION],
            "temporal_issues": [
                {
                    "issue_id": "temporal_issue:contradictory_001",
                    "issue_type": "contradictory_dates",
                    "category": "contradictory_dates",
                }
            ],
        },
    )

    assert profile["has_contradictory_dates"] is True
    # A satisfied ordering downgraded because dates are contradictory.
    assert profile["status"] == "partial"
    assert any("Contradictory date records" in w for w in profile["warnings"])
    assert any("Contradictory dates" in r for r in profile["blocking_reasons"])


def test_t6_5b_contradictory_dates_adds_warning_but_does_not_change_failed():
    """contradictory_dates warning is added even when status is already failed."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _CAUSATION_ELEMENT,
        {
            "temporal_facts": [_PROTECTED_FACT, _ADVERSE_FACT],
            "temporal_relations": [_REVERSE_BEFORE_RELATION],
            "temporal_issues": [
                {
                    "issue_id": "temporal_issue:contradictory_002",
                    "issue_type": "contradictory_dates",
                    "category": "contradictory_dates",
                }
            ],
        },
    )

    assert profile["has_contradictory_dates"] is True
    # Status should remain failed (not overwritten by contradictory-dates logic).
    assert profile["status"] == "failed"
    assert any("Contradictory date records" in w for w in profile["warnings"])


def test_t6_5c_contradictory_dates_adds_warning_to_partial_causal_connection():
    """contradictory_dates warning is added to an already-partial causal_connection."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _CAUSATION_ELEMENT,
        {
            "temporal_facts": [_PROTECTED_FACT, _ADVERSE_FACT],
            "temporal_relations": [],
            "temporal_issues": [
                {
                    "issue_id": "temporal_issue:contradictory_003",
                    "issue_type": "contradictory_dates",
                    "category": "contradictory_dates",
                }
            ],
        },
    )

    assert profile["has_contradictory_dates"] is True
    assert profile["status"] == "partial"
    assert any("Contradictory date records" in w for w in profile["warnings"])


# ---------------------------------------------------------------------------
# T6-6  Relative-only ordering for protected_activity element
# ---------------------------------------------------------------------------

def test_t6_6_relative_only_ordering_warning_for_protected_activity():
    """relative_only_ordering issue emits a warning for the protected_activity element."""
    protected_fact_relative = {
        "fact_id": "fact_pa_rel",
        "element_tags": ["protected_activity"],
        "temporal_context": {
            "start_date": "",
            "relative_markers": ["two weeks before termination"],
            "is_approximate": True,
        },
    }
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _PROTECTED_ACTIVITY_ELEMENT,
        {
            "temporal_facts": [protected_fact_relative],
            "temporal_relations": [],
            "temporal_issues": [
                {
                    "issue_id": "temporal_issue:relative_pa",
                    "issue_type": "relative_only_ordering",
                    "category": "relative_only_ordering",
                }
            ],
        },
    )

    assert profile["element_role"] == "protected_activity"
    # No start_date → no anchored facts → partial or missing
    assert profile["status"] in {"partial", "missing"}
    assert any("relative-only ordering" in w for w in profile["warnings"])


# ---------------------------------------------------------------------------
# T6-7  Relative-only ordering for adverse_action element
# ---------------------------------------------------------------------------

def test_t6_7_relative_only_ordering_warning_for_adverse_action():
    """relative_only_ordering issue emits a warning for the adverse_action element."""
    adverse_fact_relative = {
        "fact_id": "fact_aa_rel",
        "element_tags": ["adverse_action"],
        "temporal_context": {
            "start_date": "",
            "relative_markers": ["approximately three months later"],
            "is_approximate": True,
        },
    }
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _ADVERSE_ACTION_ELEMENT,
        {
            "temporal_facts": [adverse_fact_relative],
            "temporal_relations": [],
            "temporal_issues": [
                {
                    "issue_id": "temporal_issue:relative_aa",
                    "issue_type": "relative_only_ordering",
                    "category": "relative_only_ordering",
                }
            ],
        },
    )

    assert profile["element_role"] == "adverse_action"
    assert profile["status"] in {"partial", "missing"}
    assert any("relative-only ordering" in w for w in profile["warnings"])


# ---------------------------------------------------------------------------
# T6-8  Limitations-risk: triggered by issue registry entry
# ---------------------------------------------------------------------------

def test_t6_8_limitations_risk_triggered_by_issue_type():
    """limitations_risk issue type in the registry emits a warning regardless of dates."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _ADVERSE_ACTION_ELEMENT,
        {
            "temporal_facts": [_ADVERSE_FACT],
            "temporal_relations": [],
            "temporal_issues": [
                {
                    "issue_id": "temporal_issue:limitations_001",
                    "issue_type": "limitations_risk",
                    "category": "limitations_risk",
                }
            ],
        },
    )

    assert profile["has_limitations_risk"] is True
    assert any("limitations" in w.lower() or "filing window" in w.lower() for w in profile["warnings"])
    assert any(
        fu["lane"] == "seek_external_record"
        for fu in profile["recommended_follow_ups"]
    )


def test_t6_8b_limitations_risk_on_causal_connection():
    """limitations_risk issue type also surfaces on causal_connection element."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _CAUSATION_ELEMENT,
        {
            "temporal_facts": [_PROTECTED_FACT, _ADVERSE_FACT],
            "temporal_relations": [_BEFORE_RELATION],
            "temporal_issues": [
                {
                    "issue_id": "temporal_issue:limitations_002",
                    "issue_type": "limitations_risk",
                    "category": "limitations_risk",
                }
            ],
        },
    )

    assert profile["has_limitations_risk"] is True
    assert any("limitations" in w.lower() or "filing window" in w.lower() for w in profile["warnings"])
    assert any(
        fu["lane"] == "seek_external_record"
        for fu in profile["recommended_follow_ups"]
    )


# ---------------------------------------------------------------------------
# T6-9  Limitations-risk: triggered by reference_date computation (>180 days)
# ---------------------------------------------------------------------------

def test_t6_9_limitations_risk_triggered_by_reference_date_over_180_days():
    """Date-based limitations risk activates when adverse action > 180 days before reference_date."""
    adverse_fact_old = {
        "fact_id": "fact_aa_old",
        "element_tags": ["adverse_action"],
        "temporal_context": {"start_date": "2024-01-10"},
    }
    ref = date(2024, 8, 1)  # 203 days after the adverse action — beyond 180-day threshold
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _ADVERSE_ACTION_ELEMENT,
        {
            "temporal_facts": [adverse_fact_old],
            "temporal_relations": [],
            "temporal_issues": [],
        },
        reference_date=ref,
    )

    assert profile["has_limitations_risk"] is True
    assert any("203 days" in w or "approximately" in w.lower() or "days ago" in w for w in profile["warnings"])


def test_t6_9b_no_limitations_risk_when_reference_date_within_180_days():
    """Date-based limitations risk does not activate when adverse action is within 180 days."""
    adverse_fact_recent = {
        "fact_id": "fact_aa_recent",
        "element_tags": ["adverse_action"],
        "temporal_context": {"start_date": "2025-05-01"},
    }
    ref = date(2025, 7, 1)  # 61 days after adverse action — within 180-day window
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _ADVERSE_ACTION_ELEMENT,
        {
            "temporal_facts": [adverse_fact_recent],
            "temporal_relations": [],
            "temporal_issues": [],
        },
        reference_date=ref,
    )

    assert profile["has_limitations_risk"] is False


def test_t6_9c_no_limitations_risk_without_reference_date_even_when_dates_old():
    """Without reference_date, date-based limitations check is skipped entirely."""
    adverse_fact_old = {
        "fact_id": "fact_aa_old2",
        "element_tags": ["adverse_action"],
        "temporal_context": {"start_date": "2020-01-01"},  # very old date
    }
    # No reference_date provided; only the issue registry should trigger limitations_risk.
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _ADVERSE_ACTION_ELEMENT,
        {
            "temporal_facts": [adverse_fact_old],
            "temporal_relations": [],
            "temporal_issues": [],
        },
    )

    assert profile["has_limitations_risk"] is False


# ---------------------------------------------------------------------------
# T6-10  Non-retaliation claim returns not_applicable
# ---------------------------------------------------------------------------

def test_t6_10_non_retaliation_returns_not_applicable():
    """Non-retaliation claim types return not_applicable with available=False."""
    for claim_type in ("employment_discrimination", "housing_discrimination", "fair_housing", ""):
        profile = evaluate_temporal_rule_profile(
            claim_type,
            _CAUSATION_ELEMENT,
            {"temporal_facts": [], "temporal_relations": [], "temporal_issues": []},
        )
        assert profile["available"] is False, f"Expected available=False for claim_type={claim_type!r}"
        assert profile["status"] == "not_applicable"


# ---------------------------------------------------------------------------
# T6-11  Unknown element returns not_targeted
# ---------------------------------------------------------------------------

def test_t6_11_unknown_element_returns_not_targeted():
    """Elements not in the retaliation profile return not_targeted with evaluated=False."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        {"element_id": "damages", "element_text": "Requested damages"},
        {"temporal_facts": [], "temporal_relations": [], "temporal_issues": []},
    )

    assert profile["available"] is True
    assert profile["evaluated"] is False
    assert profile["status"] == "not_targeted"


# ---------------------------------------------------------------------------
# T6-12  Missing protected-activity event blocks causal_connection
# ---------------------------------------------------------------------------

def test_t6_12_missing_protected_activity_blocks_causal_connection():
    """No protected-activity facts blocks the causal_connection element."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _CAUSATION_ELEMENT,
        {
            "temporal_facts": [_ADVERSE_FACT],
            "temporal_relations": [],
            "temporal_issues": [],
        },
    )

    assert profile["status"] == "missing"
    assert profile["element_role"] == "causal_connection"
    assert any("protected activity event" in r for r in profile["blocking_reasons"])


# ---------------------------------------------------------------------------
# T6-13  Missing adverse-action event blocks causal_connection
# ---------------------------------------------------------------------------

def test_t6_13_missing_adverse_action_blocks_causal_connection():
    """No adverse-action facts blocks the causal_connection element."""
    profile = evaluate_temporal_rule_profile(
        "retaliation",
        _CAUSATION_ELEMENT,
        {
            "temporal_facts": [_PROTECTED_FACT],
            "temporal_relations": [],
            "temporal_issues": [],
        },
    )

    assert profile["status"] == "missing"
    assert profile["element_role"] == "causal_connection"
    assert any("adverse action event" in r for r in profile["blocking_reasons"])
