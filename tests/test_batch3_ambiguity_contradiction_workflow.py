"""Batch 3: Claim ambiguity and contradiction workflow tests.

Covers:
- _detect_claim_ambiguity_flags: date_ambiguous, actor_unclear, conduct_vague,
  injury_unspecified detection from canonical facts.
- _apply_claim_ambiguity_flags: writes detected flags onto candidate_claims in
  place while preserving pre-existing external flags.
- _build_contradiction_tasks_from_queue: converts the contradiction_queue into
  alignment-style evidence tasks, routing each to the correct support lane.
- _build_alignment_evidence_tasks: merges contradiction tasks when
  intake_case_file is supplied.
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.abspath("."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mediator():
    """Return a bare Mediator instance with no dependencies initialised."""
    from mediator.mediator import Mediator

    return Mediator.__new__(Mediator)


def _make_intake(candidate_claims=None, canonical_facts=None, contradiction_queue=None):
    return {
        "candidate_claims": candidate_claims or [],
        "canonical_facts": canonical_facts or [],
        "contradiction_queue": contradiction_queue or [],
    }


# ---------------------------------------------------------------------------
# _detect_claim_ambiguity_flags
# ---------------------------------------------------------------------------

class TestDetectClaimAmbiguityFlags:
    def test_no_facts_returns_all_flags(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[{"claim_type": "employment_discrimination"}],
            canonical_facts=[],
        )
        flags = m._detect_claim_ambiguity_flags(intake)
        assert "employment_discrimination" in flags
        detected = flags["employment_discrimination"]
        # No facts at all → actor_unclear, conduct_vague, injury_unspecified
        assert "actor_unclear" in detected
        assert "conduct_vague" in detected
        assert "injury_unspecified" in detected

    def test_date_ambiguous_vague_token(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[{"claim_type": "retaliation"}],
            canonical_facts=[
                {
                    "fact_type": "timeline",
                    "text": "I was fired sometime last year",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "responsible_party",
                    "text": "my direct supervisor John Smith who managed the team",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "claim_element",
                    "text": "I filed a written complaint about workplace safety",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "impact",
                    "text": "I lost my salary and health benefits after termination",
                    "claim_types": ["retaliation"],
                },
            ],
        )
        flags = m._detect_claim_ambiguity_flags(intake)
        detected = flags.get("retaliation", [])
        assert "date_ambiguous" in detected
        # Other categories are well-specified in this fixture
        assert "actor_unclear" not in detected
        assert "conduct_vague" not in detected
        assert "injury_unspecified" not in detected

    def test_date_ambiguous_no_date_field(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[{"claim_type": "retaliation"}],
            canonical_facts=[
                {
                    "fact_type": "timeline",
                    "text": "I was terminated",
                    # No event_date_or_range field
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "responsible_party",
                    "text": "HR director Jane Doe",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "claim_element",
                    "text": "Employer terminated me after I filed a safety report",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "impact",
                    "text": "I lost wages and benefits",
                    "claim_types": ["retaliation"],
                },
            ],
        )
        flags = m._detect_claim_ambiguity_flags(intake)
        detected = flags.get("retaliation", [])
        assert "date_ambiguous" in detected

    def test_actor_unclear_vague_text(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[{"claim_type": "housing_discrimination"}],
            canonical_facts=[
                {
                    "fact_type": "timeline",
                    "text": "On March 5 2024 my application was denied",
                    "event_date_or_range": "March 5 2024",
                    "claim_types": ["housing_discrimination"],
                },
                {
                    "fact_type": "responsible_party",
                    # Vague single-word actor
                    "text": "management",
                    "claim_types": ["housing_discrimination"],
                },
                {
                    "fact_type": "claim_element",
                    "text": "My rental application was denied without explanation",
                    "claim_types": ["housing_discrimination"],
                },
                {
                    "fact_type": "impact",
                    "text": "I was denied housing and remained homeless for three months",
                    "claim_types": ["housing_discrimination"],
                },
            ],
        )
        flags = m._detect_claim_ambiguity_flags(intake)
        detected = flags.get("housing_discrimination", [])
        assert "actor_unclear" in detected

    def test_no_responsible_party_fact_gives_actor_unclear(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[{"claim_type": "retaliation"}],
            canonical_facts=[
                {
                    "fact_type": "timeline",
                    "text": "Fired on January 10 2024",
                    "event_date_or_range": "January 10, 2024",
                    "claim_types": ["retaliation"],
                },
            ],
        )
        flags = m._detect_claim_ambiguity_flags(intake)
        detected = flags.get("retaliation", [])
        assert "actor_unclear" in detected

    def test_conduct_vague_short_text(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[{"claim_type": "employment_discrimination"}],
            canonical_facts=[
                {
                    "fact_type": "claim_element",
                    "text": "bad thing",  # 2 words – too short
                    "claim_types": ["employment_discrimination"],
                },
                {
                    "fact_type": "responsible_party",
                    "text": "supervisor Frank Garcia in accounting",
                    "claim_types": ["employment_discrimination"],
                },
                {
                    "fact_type": "timeline",
                    "text": "Denied promotion on February 2 2024",
                    "event_date_or_range": "February 2, 2024",
                    "claim_types": ["employment_discrimination"],
                },
                {
                    "fact_type": "impact",
                    "text": "I lost a salary increase of five thousand dollars",
                    "claim_types": ["employment_discrimination"],
                },
            ],
        )
        flags = m._detect_claim_ambiguity_flags(intake)
        detected = flags.get("employment_discrimination", [])
        assert "conduct_vague" in detected

    def test_injury_unspecified_no_impact_facts(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[{"claim_type": "employment_discrimination"}],
            canonical_facts=[
                {
                    "fact_type": "timeline",
                    "text": "On April 3 2024 I was passed over for promotion",
                    "event_date_or_range": "April 3, 2024",
                    "claim_types": ["employment_discrimination"],
                },
                {
                    "fact_type": "responsible_party",
                    "text": "VP of Sales Robert Chen",
                    "claim_types": ["employment_discrimination"],
                },
                {
                    "fact_type": "claim_element",
                    "text": "Passed over for promotion in favour of less qualified white colleague",
                    "claim_types": ["employment_discrimination"],
                },
            ],
        )
        flags = m._detect_claim_ambiguity_flags(intake)
        detected = flags.get("employment_discrimination", [])
        assert "injury_unspecified" in detected

    def test_no_flags_when_all_well_specified(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[{"claim_type": "retaliation"}],
            canonical_facts=[
                {
                    "fact_type": "timeline",
                    "text": "Terminated on June 15 2024",
                    "event_date_or_range": "June 15, 2024",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "responsible_party",
                    "text": "Director of HR Angela Torres who signed the termination letter",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "claim_element",
                    "text": "Terminated within two weeks of filing an EEOC complaint about pay disparity",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "impact",
                    "text": "Lost annual salary of seventy thousand dollars and all health benefits",
                    "claim_types": ["retaliation"],
                },
            ],
        )
        flags = m._detect_claim_ambiguity_flags(intake)
        # Retaliation claim should have no flags when all categories are present
        assert flags.get("retaliation", []) == []

    def test_no_candidate_claims_returns_empty(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[],
            canonical_facts=[{"fact_type": "timeline", "text": "something happened"}],
        )
        flags = m._detect_claim_ambiguity_flags(intake)
        assert flags == {}

    def test_multi_claim_type_flags_are_independent(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[
                {"claim_type": "retaliation"},
                {"claim_type": "housing_discrimination"},
            ],
            canonical_facts=[
                # Only retaliation has an actor and impact
                {
                    "fact_type": "timeline",
                    "text": "On July 1 2024 I was demoted",
                    "event_date_or_range": "July 1, 2024",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "responsible_party",
                    "text": "CFO Maria Lopez who signed the demotion memo",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "claim_element",
                    "text": "Demoted after reporting accounting irregularities to management",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "impact",
                    "text": "Salary cut by twenty thousand dollars per year",
                    "claim_types": ["retaliation"],
                },
            ],
        )
        flags = m._detect_claim_ambiguity_flags(intake)
        # retaliation – all facts present with specific dates → no flags
        assert flags.get("retaliation", []) == []
        # housing_discrimination – no facts at all → multiple flags
        housing_flags = flags.get("housing_discrimination", [])
        assert "actor_unclear" in housing_flags
        assert "conduct_vague" in housing_flags
        assert "injury_unspecified" in housing_flags


# ---------------------------------------------------------------------------
# _apply_claim_ambiguity_flags
# ---------------------------------------------------------------------------

class TestApplyClaimAmbiguityFlags:
    def test_flags_written_onto_claim(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[{"claim_type": "retaliation"}],
            canonical_facts=[],  # No facts → all ambiguity flags
        )
        m._apply_claim_ambiguity_flags(intake)
        claim = intake["candidate_claims"][0]
        assert isinstance(claim.get("ambiguity_flags"), list)
        assert len(claim["ambiguity_flags"]) > 0

    def test_external_flags_preserved(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[
                {"claim_type": "retaliation", "ambiguity_flags": ["timing_overlap"]}
            ],
            canonical_facts=[],
        )
        m._apply_claim_ambiguity_flags(intake)
        claim = intake["candidate_claims"][0]
        assert "timing_overlap" in claim["ambiguity_flags"]

    def test_managed_flags_replaced_not_duplicated(self):
        m = _make_mediator()
        intake = _make_intake(
            candidate_claims=[
                {
                    "claim_type": "retaliation",
                    "ambiguity_flags": ["date_ambiguous", "timing_overlap"],
                }
            ],
            canonical_facts=[
                {
                    "fact_type": "timeline",
                    "text": "On September 1 2024 I was demoted",
                    "event_date_or_range": "September 1, 2024",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "responsible_party",
                    "text": "My manager Dr. Carlos Rivera who led our division",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "claim_element",
                    "text": "Demoted two weeks after I filed a wage-theft complaint",
                    "claim_types": ["retaliation"],
                },
                {
                    "fact_type": "impact",
                    "text": "Salary reduced by fifteen thousand dollars annually",
                    "claim_types": ["retaliation"],
                },
            ],
        )
        m._apply_claim_ambiguity_flags(intake)
        claim = intake["candidate_claims"][0]
        flags = claim["ambiguity_flags"]
        # timing_overlap preserved; date_ambiguous dropped (now well-specified)
        assert "timing_overlap" in flags
        assert flags.count("date_ambiguous") <= 1

    def test_no_candidate_claims_no_error(self):
        m = _make_mediator()
        intake = _make_intake(candidate_claims=[], canonical_facts=[])
        m._apply_claim_ambiguity_flags(intake)  # Should not raise

    def test_non_list_candidate_claims_no_error(self):
        m = _make_mediator()
        intake = {"candidate_claims": None, "canonical_facts": []}
        m._apply_claim_ambiguity_flags(intake)  # Should not raise


# ---------------------------------------------------------------------------
# _build_contradiction_tasks_from_queue
# ---------------------------------------------------------------------------

class TestBuildContradictionTasksFromQueue:
    def _make_entry(self, **kwargs):
        defaults = {
            "contradiction_id": "ctr:1",
            "severity": "blocking",
            "topic": "termination date",
            "status": "open",
            "current_resolution_status": "open",
            "recommended_resolution_lane": "request_document",
            "affected_claim_types": ["employment_discrimination"],
            "affected_element_ids": ["adverse_action"],
            "existing_text": "Fired in January",
            "new_text": "Fired in March",
            "external_corroboration_required": True,
            "resolution_notes": "",
        }
        defaults.update(kwargs)
        return defaults

    def test_basic_task_created(self):
        m = _make_mediator()
        intake = _make_intake(contradiction_queue=[self._make_entry()])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert len(tasks) == 1
        t = tasks[0]
        assert t["action"] == "resolve_contradiction"
        assert t["task_id"] == "contradiction:ctr:1"

    def test_resolved_entry_skipped(self):
        m = _make_mediator()
        entry = self._make_entry(
            current_resolution_status="resolved",
            status="resolved",
        )
        intake = _make_intake(contradiction_queue=[entry])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert tasks == []

    def test_escalated_entry_skipped(self):
        m = _make_mediator()
        entry = self._make_entry(current_resolution_status="escalated")
        intake = _make_intake(contradiction_queue=[entry])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert tasks == []

    def test_resolution_lane_request_document(self):
        m = _make_mediator()
        entry = self._make_entry(recommended_resolution_lane="request_document")
        intake = _make_intake(contradiction_queue=[entry])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert tasks[0]["preferred_support_kind"] == "document"
        assert tasks[0]["contradiction_resolution_lane"] == "request_document"

    def test_resolution_lane_capture_testimony(self):
        m = _make_mediator()
        entry = self._make_entry(
            contradiction_id="ctr:2",
            recommended_resolution_lane="capture_testimony",
        )
        intake = _make_intake(contradiction_queue=[entry])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert tasks[0]["preferred_support_kind"] == "testimony"
        assert tasks[0]["source_quality_target"] == "credible_testimony"

    def test_resolution_lane_seek_external_record(self):
        m = _make_mediator()
        entry = self._make_entry(
            contradiction_id="ctr:3",
            recommended_resolution_lane="seek_external_record",
        )
        intake = _make_intake(contradiction_queue=[entry])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert tasks[0]["preferred_support_kind"] == "external_record"

    def test_resolution_lane_clarify_with_complainant(self):
        m = _make_mediator()
        entry = self._make_entry(
            contradiction_id="ctr:4",
            recommended_resolution_lane="clarify_with_complainant",
        )
        intake = _make_intake(contradiction_queue=[entry])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert tasks[0]["preferred_support_kind"] == "testimony"

    def test_blocking_severity_sets_high_priority(self):
        m = _make_mediator()
        entry = self._make_entry(severity="blocking")
        intake = _make_intake(contradiction_queue=[entry])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert tasks[0]["task_priority"] == "high"
        assert tasks[0]["blocking"] is True

    def test_non_blocking_severity_sets_medium_priority(self):
        m = _make_mediator()
        entry = self._make_entry(contradiction_id="ctr:5", severity="warning")
        intake = _make_intake(contradiction_queue=[entry])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert tasks[0]["task_priority"] == "medium"
        assert tasks[0]["blocking"] is False

    def test_duplicate_ids_deduplicated(self):
        m = _make_mediator()
        entry1 = self._make_entry(contradiction_id="ctr:dup")
        entry2 = self._make_entry(contradiction_id="ctr:dup")
        intake = _make_intake(contradiction_queue=[entry1, entry2])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert len(tasks) == 1

    def test_task_carries_affected_claim_types(self):
        m = _make_mediator()
        entry = self._make_entry(
            affected_claim_types=["retaliation", "employment_discrimination"]
        )
        intake = _make_intake(contradiction_queue=[entry])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert tasks[0]["affected_claim_types"] == ["retaliation", "employment_discrimination"]
        assert tasks[0]["claim_type"] == "retaliation"

    def test_task_carries_success_criteria(self):
        m = _make_mediator()
        entry = self._make_entry(
            topic="termination date", external_corroboration_required=True
        )
        intake = _make_intake(contradiction_queue=[entry])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        criteria = tasks[0]["success_criteria"]
        assert any("termination date" in c for c in criteria)
        assert any("corroboration" in c.lower() for c in criteria)

    def test_empty_queue_returns_empty(self):
        m = _make_mediator()
        intake = _make_intake(contradiction_queue=[])
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert tasks == []

    def test_multiple_unresolved_entries(self):
        m = _make_mediator()
        entries = [
            self._make_entry(contradiction_id="ctr:a", topic="date"),
            self._make_entry(contradiction_id="ctr:b", topic="actor"),
        ]
        intake = _make_intake(contradiction_queue=entries)
        tasks = m._build_contradiction_tasks_from_queue(intake)
        assert len(tasks) == 2
        task_ids = {t["task_id"] for t in tasks}
        assert "contradiction:ctr:a" in task_ids
        assert "contradiction:ctr:b" in task_ids


# ---------------------------------------------------------------------------
# _build_alignment_evidence_tasks  (contradiction tasks merge)
# ---------------------------------------------------------------------------

class TestBuildAlignmentEvidenceTasksContradictionMerge:
    def test_contradiction_tasks_included_when_intake_passed(self):
        m = _make_mediator()
        alignment_summary = {"claims": {}}
        intake = _make_intake(
            contradiction_queue=[
                {
                    "contradiction_id": "ctr:merge:1",
                    "severity": "blocking",
                    "topic": "hire date",
                    "status": "open",
                    "current_resolution_status": "open",
                    "recommended_resolution_lane": "capture_testimony",
                    "affected_claim_types": ["retaliation"],
                    "affected_element_ids": ["causation"],
                    "existing_text": "Hired in 2019",
                    "new_text": "Hired in 2021",
                    "external_corroboration_required": False,
                    "resolution_notes": "",
                }
            ]
        )
        tasks = m._build_alignment_evidence_tasks(alignment_summary, intake)
        assert any(t["task_id"] == "contradiction:ctr:merge:1" for t in tasks)

    def test_no_contradiction_tasks_without_intake(self):
        m = _make_mediator()
        alignment_summary = {"claims": {}}
        tasks = m._build_alignment_evidence_tasks(alignment_summary)
        # No intake_case_file means no contradiction tasks added
        contradiction_tasks = [t for t in tasks if t.get("action") == "resolve_contradiction"]
        assert contradiction_tasks == []

    def test_contradiction_tasks_sorted_to_front(self):
        m = _make_mediator()
        alignment_summary = {"claims": {}}
        intake = _make_intake(
            contradiction_queue=[
                {
                    "contradiction_id": "ctr:sort:1",
                    "severity": "blocking",
                    "topic": "start date",
                    "status": "open",
                    "current_resolution_status": "open",
                    "recommended_resolution_lane": "request_document",
                    "affected_claim_types": ["employment_discrimination"],
                    "affected_element_ids": ["protected_class"],
                    "existing_text": "x",
                    "new_text": "y",
                    "external_corroboration_required": False,
                    "resolution_notes": "",
                }
            ]
        )
        tasks = m._build_alignment_evidence_tasks(alignment_summary, intake)
        ctask = next(
            (t for t in tasks if t.get("action") == "resolve_contradiction"), None
        )
        assert ctask is not None
        # Contradicted + blocking → sorted to front
        assert tasks[0]["support_status"] == "contradicted"

    def test_resolved_contradiction_not_included(self):
        m = _make_mediator()
        alignment_summary = {"claims": {}}
        intake = _make_intake(
            contradiction_queue=[
                {
                    "contradiction_id": "ctr:resolved:1",
                    "severity": "blocking",
                    "topic": "event",
                    "status": "resolved",
                    "current_resolution_status": "resolved",
                    "recommended_resolution_lane": "request_document",
                    "affected_claim_types": ["retaliation"],
                    "affected_element_ids": [],
                    "existing_text": "",
                    "new_text": "",
                    "external_corroboration_required": False,
                    "resolution_notes": "resolved",
                }
            ]
        )
        tasks = m._build_alignment_evidence_tasks(alignment_summary, intake)
        assert not any(t.get("contradiction_id") == "ctr:resolved:1" for t in tasks)
