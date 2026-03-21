from complaint_phases import Entity, KnowledgeGraph, KnowledgeGraphBuilder
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
    assert intake_case_file["event_ledger"] == [
        {
            **intake_case_file["temporal_fact_registry"][0],
            "event_id": "fact:1",
            "temporal_fact_id": "fact:1",
            "ledger_version": "event_ledger.v1",
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
    assert refreshed["event_ledger"][0]["event_id"] == "fact_1"
    assert refreshed["event_ledger"][0]["ledger_version"] == "event_ledger.v1"
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
            "summary": "Timeline fact fact_3 only has relative ordering (after) and still needs anchoring.",
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


def test_build_intake_case_file_adds_blocker_follow_up_summary_and_open_items():
    knowledge_graph = KnowledgeGraph()
    knowledge_graph.add_entity(
        Entity(
            id="claim:ret",
            type="claim",
            name="Retaliation Claim",
            attributes={"claim_type": "retaliation", "description": "Retaliation after complaint."},
        )
    )
    knowledge_graph.add_entity(
        Entity(
            id="fact:hear",
            type="fact",
            name="Hearing request",
            attributes={"fact_type": "timeline", "description": "I requested a hearing."},
        )
    )

    complaint_text = (
        "I complained to HR and was terminated soon after. "
        "I requested a hearing and received no response. "
        "I got a notice but I do not have a copy."
    )
    intake_case_file = build_intake_case_file(knowledge_graph, complaint_text)

    blocker_summary = intake_case_file["blocker_follow_up_summary"]
    assert blocker_summary["blocking_item_count"] >= 3
    blocker_ids = {item["blocker_id"] for item in blocker_summary["blocking_items"]}
    assert "missing_written_notice_chain" in blocker_ids
    assert "missing_hearing_request_timing" in blocker_ids
    assert "missing_response_timing" in blocker_ids
    assert "exact_dates" in blocker_summary["blocking_objectives"]
    assert "timeline_anchors" in blocker_summary["extraction_targets"]
    assert blocker_summary["workflow_phases"] == [
        "graph_analysis",
        "intake_questioning",
        "document_generation",
    ]

    hearing_blocker = next(
        item for item in blocker_summary["blocking_items"]
        if item["blocker_id"] == "missing_hearing_request_timing"
    )
    assert hearing_blocker["primary_objective"] == "hearing_request_timing"
    assert hearing_blocker["blocker_objectives"] == ["hearing_request_timing", "exact_dates"]
    assert hearing_blocker["extraction_targets"] == ["hearing_process", "timeline_anchors"]

    blocker_open_items = [
        item for item in intake_case_file["open_items"]
        if item.get("kind") == "blocker_follow_up"
    ]
    assert blocker_open_items
    response_open_item = next(
        item for item in blocker_open_items
        if item["open_item_id"] == "blocker:missing_response_timing"
    )
    assert response_open_item["primary_objective"] == "response_dates"
    assert response_open_item["blocker_objectives"] == ["response_dates", "exact_dates"]
    assert response_open_item["extraction_targets"] == ["response_timeline", "timeline_anchors"]
    assert response_open_item["workflow_phases"] == [
        "graph_analysis",
        "intake_questioning",
        "document_generation",
    ]


def test_build_intake_case_file_uses_sentence_level_retaliation_facts_to_clear_sequence_blocker():
    builder = KnowledgeGraphBuilder()
    complaint_text = (
        "On March 1, 2025, I complained to HR about discrimination. "
        "On March 15, 2025, my employer terminated me two weeks after I complained."
    )

    knowledge_graph = builder.build_from_text(complaint_text)
    intake_case_file = build_intake_case_file(knowledge_graph, complaint_text)

    fact_entities = knowledge_graph.get_entities_by_type("fact")
    protected_facts = [entity for entity in fact_entities if entity.attributes.get("predicate_family") == "protected_activity"]
    adverse_facts = [entity for entity in fact_entities if entity.attributes.get("predicate_family") == "adverse_action"]
    causation_facts = [entity for entity in fact_entities if entity.attributes.get("predicate_family") == "causation"]

    assert any(fact.attributes.get("event_date_or_range") == "March 1, 2025" for fact in protected_facts)
    assert any(fact.attributes.get("event_date_or_range") == "March 15, 2025" for fact in adverse_facts)
    assert any(fact.attributes.get("event_date_or_range") == "March 15, 2025" for fact in causation_facts)

    blocker_ids = {
        item["blocker_id"]
        for item in intake_case_file["blocker_follow_up_summary"]["blocking_items"]
    }
    assert "missing_retaliation_causation_sequence" not in blocker_ids


def test_refresh_intake_case_file_preserves_quantified_relative_markers_in_temporal_issues():
    intake_case_file = {
        "candidate_claims": [],
        "intake_sections": {},
        "canonical_facts": [
            {
                "fact_id": "fact_4",
                "text": "Employer terminated Plaintiff two weeks after the complaint.",
                "fact_type": "timeline",
                "claim_types": ["retaliation"],
                "element_tags": ["causation"],
                "event_date_or_range": "two weeks after the complaint",
            }
        ],
        "proof_leads": [],
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

    issue = refreshed["temporal_issue_registry"][0]
    assert issue["issue_type"] == "relative_only_ordering"
    assert issue["relative_markers"] == ["two weeks after", "after"]
    assert "two weeks after" in issue["summary"]


def test_knowledge_graph_builder_extracts_quantified_relative_event_dates():
    builder = KnowledgeGraphBuilder()
    graph = builder.build_from_text("Two weeks after I complained to HR, my employer terminated me.")

    fact_entities = graph.get_entities_by_type("fact")
    causation_facts = [entity for entity in fact_entities if entity.attributes.get("predicate_family") == "causation"]
    adverse_facts = [entity for entity in fact_entities if entity.attributes.get("predicate_family") == "adverse_action"]

    assert any(fact.attributes.get("event_date_or_range") == "Two weeks after" for fact in causation_facts)
    assert any(fact.attributes.get("event_date_or_range") == "Two weeks after" for fact in adverse_facts)


def test_build_intake_case_file_merges_duplicate_relative_only_temporal_issues_for_same_sentence():
    builder = KnowledgeGraphBuilder()
    complaint_text = "Two weeks after I complained to HR, my employer terminated me."

    intake_case_file = build_intake_case_file(builder.build_from_text(complaint_text), complaint_text)

    issues = intake_case_file["temporal_issue_registry"]
    assert len(issues) == 1
    assert issues[0]["issue_type"] == "relative_only_ordering"
    assert issues[0]["relative_markers"] == ["two weeks after", "after"]
    assert len(issues[0]["fact_ids"]) >= 2


def test_build_intake_case_file_derives_anchor_dates_from_quantified_relative_retaliation_sequence():
    builder = KnowledgeGraphBuilder()
    complaint_text = (
        "On March 1, 2025, I complained to HR about discrimination. "
        "Two weeks after I complained to HR, my employer terminated me."
    )

    intake_case_file = build_intake_case_file(builder.build_from_text(complaint_text), complaint_text)

    canonical_facts = intake_case_file["canonical_facts"]
    adverse_facts = [fact for fact in canonical_facts if fact.get("predicate_family") == "adverse_action"]
    causation_facts = [fact for fact in canonical_facts if fact.get("predicate_family") == "causation"]

    assert any(
        fact.get("temporal_context", {}).get("start_date") == "2025-03-15"
        and fact.get("temporal_context", {}).get("derivation_mode") == "relative_anchor_offset"
        for fact in adverse_facts
    )
    assert any(
        fact.get("temporal_context", {}).get("start_date") == "2025-03-15"
        and fact.get("temporal_context", {}).get("anchor_predicate_family") == "protected_activity"
        for fact in causation_facts
    )

    fact_by_id = {
        fact.get("fact_id"): fact
        for fact in canonical_facts
        if fact.get("fact_id")
    }
    assert any(
        relation.get("relation_type") == "before"
        and fact_by_id.get(relation.get("source_fact_id"), {}).get("predicate_family") == "protected_activity"
        and fact_by_id.get(relation.get("target_fact_id"), {}).get("predicate_family") == "adverse_action"
        for relation in intake_case_file["timeline_relations"]
    )
    assert intake_case_file["temporal_issue_registry"] == []


def test_knowledge_graph_builder_extracts_named_staff_role_titles():
    builder = KnowledgeGraphBuilder()
    graph = builder.build_from_text(
        "Regional Manager Jane Smith denied my transfer request. Later, John Carter was the hearing officer on my appeal."
    )

    person_entities = {entity.name: entity for entity in graph.get_entities_by_type("person")}
    assert person_entities["Jane Smith"].attributes["role"] == "regional manager"
    assert person_entities["John Carter"].attributes["role"] == "hearing officer"


def test_knowledge_graph_builder_extracts_notice_hearing_and_response_events_with_dates():
    builder = KnowledgeGraphBuilder()
    graph = builder.build_from_text(
        "On January 5, 2026, I received a termination notice by email from the housing authority. "
        "On January 8, 2026, I requested a grievance hearing. "
        "The agency denied my appeal on January 20, 2026."
    )

    fact_entities = graph.get_entities_by_type("fact")
    notice_facts = [entity for entity in fact_entities if entity.attributes.get("predicate_family") == "notice_chain"]
    hearing_facts = [entity for entity in fact_entities if entity.attributes.get("predicate_family") == "hearing_process"]
    response_facts = [entity for entity in fact_entities if entity.attributes.get("predicate_family") == "response_timeline"]

    assert any(fact.attributes.get("event_date_or_range") == "January 5, 2026" for fact in notice_facts)
    assert any(fact.attributes.get("event_label") == "Hearing request event" and fact.attributes.get("event_date_or_range") == "January 8, 2026" for fact in hearing_facts)
    assert any(fact.attributes.get("event_date_or_range") == "January 20, 2026" for fact in response_facts)
