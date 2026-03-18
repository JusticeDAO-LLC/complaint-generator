from complaint_phases import Entity, KnowledgeGraph
from complaint_phases.intake_case_file import build_intake_case_file, refresh_intake_case_file


def test_build_intake_case_file_adds_structured_temporal_context_and_anchor_fields():
    knowledge_graph = KnowledgeGraph()
    knowledge_graph.add_entity(
        Entity(
            id="fact:1",
            type="fact",
            name="Termination event",
            attributes={
                "description": "Employer terminated Plaintiff on January 20, 2026.",
                "fact_type": "timeline",
                "event_date_or_range": "January 20, 2026",
                "location": "Dallas office",
            },
        )
    )
    knowledge_graph.add_entity(
        Entity(
            id="evidence:1",
            type="evidence",
            name="Termination letter",
            attributes={
                "description": "Termination letter dated January 20, 2026",
                "evidence_type": "document",
                "temporal_scope": "January 2026",
            },
        )
    )

    intake_case_file = build_intake_case_file(knowledge_graph)

    timeline_fact = intake_case_file["canonical_facts"][0]
    assert timeline_fact["event_date_or_range"] == "January 20, 2026"
    assert timeline_fact["temporal_context"] == {
        "raw_text": "January 20, 2026",
        "start_date": "2026-01-20",
        "end_date": "2026-01-20",
        "granularity": "day",
        "is_approximate": False,
        "is_range": False,
        "relative_markers": [],
        "sortable_date": "2026-01-20",
        "matched_text": "January 20, 2026",
    }

    timeline_anchor = intake_case_file["timeline_anchors"][0]
    assert timeline_anchor["anchor_text"] == "January 20, 2026"
    assert timeline_anchor["start_date"] == "2026-01-20"
    assert timeline_anchor["end_date"] == "2026-01-20"
    assert timeline_anchor["granularity"] == "day"
    assert timeline_anchor["is_approximate"] is False
    assert timeline_anchor["sort_key"] == "2026-01-20"

    proof_lead = intake_case_file["proof_leads"][0]
    assert proof_lead["temporal_scope"] == "January 2026"
    assert proof_lead["temporal_context"] == {
        "raw_text": "January 2026",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "granularity": "month",
        "is_approximate": False,
        "is_range": False,
        "relative_markers": [],
        "sortable_date": "2026-01-01",
        "matched_text": "January 2026",
    }
    assert proof_lead["timeline_anchor_ids"] == []
    assert intake_case_file["temporal_fact_registry"] == [
        {
            **timeline_fact,
            "fact_id": "fact:1",
            "temporal_fact_id": "fact:1",
            "registry_version": "temporal_fact_registry.v1",
            "claim_types": [],
            "element_tags": [],
            "actor_ids": [],
            "target_ids": [],
            "event_label": "Employer terminated Plaintiff on January 20, 2026.",
            "predicate_family": "timeline",
            "start_time": "2026-01-20",
            "end_time": "2026-01-20",
            "granularity": "day",
            "is_approximate": False,
            "is_range": False,
            "relative_markers": [],
            "timeline_anchor_ids": [timeline_anchor["anchor_id"]],
            "temporal_context": timeline_fact["temporal_context"],
            "temporal_status": "anchored",
            "source_artifact_ids": [],
            "testimony_record_ids": [],
            "source_span_refs": [],
            "confidence": 1.0,
            "validation_status": "accepted",
            "source_kind": "knowledge_graph_entity",
            "source_ref": "fact:1",
        }
    ]
    assert intake_case_file["temporal_relation_registry"] == []
    assert intake_case_file["temporal_issue_registry"] == []
    assert intake_case_file["timeline_relations"] == []
    assert intake_case_file["timeline_consistency_summary"] == {
        "event_count": 1,
        "anchor_count": 1,
        "ordered_fact_count": 1,
        "unsequenced_fact_count": 0,
        "approximate_fact_count": 0,
        "range_fact_count": 0,
        "relation_count": 0,
        "relation_type_counts": {},
        "missing_temporal_fact_ids": [],
        "relative_only_fact_ids": [],
        "warnings": [],
        "partial_order_ready": True,
    }


def test_refresh_intake_case_file_backfills_temporal_context_and_links_proof_leads():
    intake_case_file = {
        "candidate_claims": [],
        "intake_sections": {},
        "canonical_facts": [
            {
                "fact_id": "fact_1",
                "text": "Employer suspended Plaintiff around March 2025.",
                "fact_type": "timeline",
                "event_date_or_range": "around March 2025",
            },
            {
                "fact_id": "fact_2",
                "text": "Employer terminated Plaintiff on April 15, 2025.",
                "fact_type": "timeline",
                "event_date_or_range": "April 15, 2025",
            }
        ],
        "proof_leads": [
            {
                "lead_id": "lead_1",
                "lead_type": "email",
                "description": "Email exchange covering the suspension period.",
                "related_fact_ids": ["fact_1"],
                "temporal_scope": "March 2025 to April 2025",
            }
        ],
        "timeline_anchors": [],
        "harm_profile": {},
        "remedy_profile": {},
        "contradiction_queue": [],
        "open_items": [],
        "summary_snapshots": [],
        "complainant_summary_confirmation": {},
        "source_complaint_text": "",
    }

    refreshed = refresh_intake_case_file(intake_case_file, None)

    timeline_fact = refreshed["canonical_facts"][0]
    assert timeline_fact["temporal_context"]["start_date"] == "2025-03-01"
    assert timeline_fact["temporal_context"]["end_date"] == "2025-03-31"
    assert timeline_fact["temporal_context"]["granularity"] == "month"
    assert timeline_fact["temporal_context"]["is_approximate"] is True

    timeline_anchor = refreshed["timeline_anchors"][0]
    assert timeline_anchor["fact_id"] == "fact_1"
    assert timeline_anchor["start_date"] == "2025-03-01"
    assert timeline_anchor["end_date"] == "2025-03-31"
    assert timeline_anchor["granularity"] == "month"
    assert timeline_anchor["is_approximate"] is True

    proof_lead = refreshed["proof_leads"][0]
    assert proof_lead["timeline_anchor_ids"] == [timeline_anchor["anchor_id"]]
    assert proof_lead["temporal_context"]["start_date"] == "2025-03-01"
    assert proof_lead["temporal_context"]["end_date"] == "2025-04-30"
    assert proof_lead["temporal_context"]["granularity"] == "month"
    assert proof_lead["temporal_context"]["is_range"] is True

    assert refreshed["timeline_relations"] == [
        {
            "relation_id": "timeline_relation_001",
            "source_fact_id": "fact_1",
            "target_fact_id": "fact_2",
            "relation_type": "before",
            "source_start_date": "2025-03-01",
            "source_end_date": "2025-03-31",
            "target_start_date": "2025-04-15",
            "target_end_date": "2025-04-15",
            "confidence": "medium",
        }
    ]
    assert refreshed["temporal_fact_registry"][0]["temporal_fact_id"] == "fact_1"
    assert refreshed["temporal_fact_registry"][0]["timeline_anchor_ids"] == [timeline_anchor["anchor_id"]]
    assert refreshed["temporal_relation_registry"] == [
        {
            "relation_id": "timeline_relation_001",
            "registry_version": "temporal_relation_registry.v1",
            "source_fact_id": "fact_1",
            "target_fact_id": "fact_2",
            "source_temporal_fact_id": "fact_1",
            "target_temporal_fact_id": "fact_2",
            "relation_type": "before",
            "source_start_date": "2025-03-01",
            "source_end_date": "2025-03-31",
            "target_start_date": "2025-04-15",
            "target_end_date": "2025-04-15",
            "confidence": "medium",
            "claim_types": [],
            "element_tags": [],
            "source_fact_text": "Employer suspended Plaintiff around March 2025.",
            "target_fact_text": "Employer terminated Plaintiff on April 15, 2025.",
            "source_artifact_ids": [],
            "testimony_record_ids": [],
            "source_span_refs": [],
            "inference_mode": "derived_from_temporal_context",
            "inference_basis": "normalized_temporal_context",
            "explanation": "fact_1 before fact_2 based on normalized temporal context.",
        }
    ]
    assert refreshed["temporal_issue_registry"] == []
    assert refreshed["timeline_consistency_summary"] == {
        "event_count": 2,
        "anchor_count": 2,
        "ordered_fact_count": 2,
        "unsequenced_fact_count": 0,
        "approximate_fact_count": 1,
        "range_fact_count": 1,
        "relation_count": 1,
        "relation_type_counts": {"before": 1},
        "missing_temporal_fact_ids": [],
        "relative_only_fact_ids": [],
        "warnings": [],
        "partial_order_ready": True,
    }


def test_refresh_intake_case_file_builds_temporal_issue_registry_for_relative_and_contradicted_facts():
    intake_case_file = {
        "candidate_claims": [],
        "intake_sections": {},
        "canonical_facts": [
            {
                "fact_id": "fact_3",
                "text": "Supervisor acted after the complaint.",
                "fact_type": "timeline",
                "claim_types": ["retaliation"],
                "element_tags": ["causation"],
                "event_date_or_range": "after the complaint",
            }
        ],
        "proof_leads": [],
        "timeline_anchors": [],
        "harm_profile": {},
        "remedy_profile": {},
        "contradiction_queue": [
            {
                "contradiction_id": "temporal_reverse_before_001",
                "category": "temporal_reverse_before",
                "summary": "The complaint and adverse action are ordered inconsistently.",
                "affected_claim_types": ["retaliation"],
                "affected_element_ids": ["causation"],
                "severity": "blocking",
                "recommended_resolution_lane": "request_document",
                "left_node_name": "Supervisor acted after the complaint.",
                "right_node_name": "Employee complained to HR.",
            }
        ],
        "open_items": [],
        "summary_snapshots": [],
        "complainant_summary_confirmation": {},
        "source_complaint_text": "",
    }

    refreshed = refresh_intake_case_file(intake_case_file, None)

    assert refreshed["temporal_issue_registry"] == [
        {
            "issue_id": "temporal_issue:relative_only_ordering:fact_3",
            "registry_version": "temporal_issue_registry.v1",
            "issue_type": "relative_only_ordering",
            "category": "relative_only_ordering",
            "summary": "Timeline fact fact_3 only has relative ordering and still needs anchoring.",
            "severity": "blocking",
            "blocking": True,
            "recommended_resolution_lane": "clarify_with_complainant",
            "fact_ids": ["fact_3"],
            "claim_types": ["retaliation"],
            "element_tags": ["causation"],
            "left_node_name": "Supervisor acted after the complaint.",
            "right_node_name": None,
            "status": "open",
            "relative_markers": ["after"],
            "source_kind": "temporal_fact_registry",
            "source_ref": "fact_3",
            "inference_mode": "derived_from_temporal_context",
        },
        {
            "issue_id": "temporal_reverse_before_001",
            "registry_version": "temporal_issue_registry.v1",
            "issue_type": "temporal_reverse_before",
            "category": "temporal_reverse_before",
            "summary": "The complaint and adverse action are ordered inconsistently.",
            "severity": "blocking",
            "blocking": True,
            "recommended_resolution_lane": "request_document",
            "fact_ids": [],
            "claim_types": ["retaliation"],
            "element_tags": ["causation"],
            "left_node_name": "Supervisor acted after the complaint.",
            "right_node_name": "Employee complained to HR.",
            "status": "open",
            "source_kind": "contradiction_queue",
            "source_ref": "temporal_reverse_before_001",
            "inference_mode": "imported_temporal_contradiction",
        },
    ]