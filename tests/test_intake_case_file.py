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
    temporal_fact = intake_case_file["temporal_fact_registry"][0]
    assert temporal_fact["fact_id"] == "fact:1"
    assert temporal_fact["temporal_fact_id"] == "fact:1"
    assert temporal_fact["registry_version"] == "temporal_fact_registry.v1"
    assert temporal_fact["claim_types"] == []
    assert temporal_fact["element_tags"] == []
    assert temporal_fact["actor_ids"] == []
    assert temporal_fact["target_ids"] == []
    assert temporal_fact["event_label"] == "Employer terminated Plaintiff on January 20, 2026."
    assert temporal_fact["predicate_family"] == "timeline"
    assert temporal_fact["start_time"] == "2026-01-20"
    assert temporal_fact["end_time"] == "2026-01-20"
    assert temporal_fact["granularity"] == "day"
    assert temporal_fact["is_approximate"] is False
    assert temporal_fact["is_range"] is False
    assert temporal_fact["relative_markers"] == []
    assert temporal_fact["timeline_anchor_ids"] == [timeline_anchor["anchor_id"]]
    assert temporal_fact["temporal_context"] == timeline_fact["temporal_context"]
    assert temporal_fact["temporal_status"] == "anchored"
    assert temporal_fact["source_artifact_ids"] == []
    assert temporal_fact["testimony_record_ids"] == []
    assert temporal_fact["source_span_refs"] == []
    assert temporal_fact["confidence"] == 1.0
    assert temporal_fact["validation_status"] == "accepted"
    assert temporal_fact["source_kind"] == "knowledge_graph_entity"
    assert temporal_fact["source_ref"] == "fact:1"
    assert temporal_fact["event_support_refs"] == ["fact:fact:1"]
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
            "current_resolution_status": "open",
            "relative_markers": ["after"],
            "missing_temporal_predicates": ["Anchored(fact_3)"],
            "required_provenance_kinds": ["testimony_record"],
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
            "current_resolution_status": "open",
            "missing_temporal_predicates": [],
            "required_provenance_kinds": ["document_artifact"],
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


def test_refresh_intake_case_file_skips_policy_and_checklist_timeline_noise_in_temporal_registry():
    intake_case_file = {
        "candidate_claims": [],
        "intake_sections": {},
        "canonical_facts": [
            {
                "fact_id": "fact_policy",
                "text": "From what I understand, the Administrative Plan says residents must get notice of the ability to request an informal hearing, including under 24 CFR 982.555.",
                "fact_type": "timeline",
                "predicate_family": "hearing_process",
            },
            {
                "fact_id": "fact_checklist",
                "text": "The exact dates of my complaint, HACC notices, my hearing/review request, and any denial or termination decision.",
                "fact_type": "timeline",
                "predicate_family": "timeline",
            },
            {
                "fact_id": "fact_event",
                "text": "I requested a hearing and received no response.",
                "fact_type": "timeline",
                "predicate_family": "hearing_process",
            },
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

    fact_ids = {item["fact_id"] for item in refreshed["timeline_anchors"]}
    assert "fact_event" in fact_ids
    assert "fact_policy" not in fact_ids
    assert "fact_checklist" not in fact_ids
    assert [issue["fact_ids"] for issue in refreshed["temporal_issue_registry"]] == [["fact_event"]]


def test_refresh_intake_case_file_downgrades_sequenced_structured_steps_without_dates():
    intake_case_file = {
        "candidate_claims": [],
        "intake_sections": {},
        "canonical_facts": [
            {
                "fact_id": "fact_anchor",
                "text": "I complained in early 2025.",
                "fact_type": "timeline",
                "predicate_family": "protected_activity",
                "structured_timeline_group": "group_1",
                "sequence_index": 1,
                "event_date_or_range": "early 2025",
            },
            {
                "fact_id": "fact_follow_up",
                "text": "I requested a grievance hearing after that action.",
                "fact_type": "timeline",
                "predicate_family": "hearing_process",
                "structured_timeline_group": "group_1",
                "sequence_index": 2,
                "event_date_or_range": None,
            },
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

    issue = next(item for item in refreshed["temporal_issue_registry"] if item["fact_ids"] == ["fact_follow_up"])
    assert issue["issue_type"] == "missing_anchor"
    assert issue["severity"] == "warning"
    assert issue["blocking"] is False
    assert issue["recommended_resolution_lane"] == "capture_testimony"
    assert issue["required_provenance_kinds"] == ["testimony_record", "document_artifact"]


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
    assert issues[0]["missing_temporal_predicates"] == [
        f"Before({issues[0]['fact_ids'][0]},{issues[0]['fact_ids'][-1]})"
    ]
    assert issues[0]["required_provenance_kinds"] == ["testimony_record"]


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


def test_build_intake_case_file_derives_sequence_relations_from_structured_timeline_group():
    knowledge_graph = KnowledgeGraph()
    knowledge_graph.add_entity(
        Entity(
            id="fact:protected",
            type="fact",
            name="Protected activity: grievance",
            attributes={
                "description": "Me raised concerns and used the grievance process. Artifact: grievance request email",
                "fact_type": "timeline",
                "predicate_family": "protected_activity",
                "event_label": "Protected activity",
                "event_date_or_range": "January 5, 2026",
                "event_id": "structured_event_001",
                "sequence_index": 1,
                "structured_timeline_group": "structured_timeline_demo",
                "source_artifact_ids": ["grievance request email"],
                "event_support_refs": ["grievance request email"],
            },
        )
    )
    knowledge_graph.add_entity(
        Entity(
            id="fact:adverse",
            type="fact",
            name="Adverse action: voucher status",
            attributes={
                "description": "HACC staff communicated an adverse action affecting voucher status. Artifact: status change notice",
                "fact_type": "timeline",
                "predicate_family": "adverse_action",
                "event_label": "Adverse action",
                "event_id": "structured_event_002",
                "sequence_index": 2,
                "structured_timeline_group": "structured_timeline_demo",
                "source_artifact_ids": ["status change notice"],
                "event_support_refs": ["status change notice"],
            },
        )
    )
    knowledge_graph.add_entity(
        Entity(
            id="fact:hearing",
            type="fact",
            name="Hearing request: informal hearing",
            attributes={
                "description": "Me requested an informal hearing after that action. Artifact: hearing request form",
                "fact_type": "timeline",
                "predicate_family": "hearing_process",
                "event_label": "Hearing request event",
                "event_date_or_range": "after that action",
                "event_id": "structured_event_003",
                "sequence_index": 3,
                "structured_timeline_group": "structured_timeline_demo",
                "source_artifact_ids": ["hearing request form"],
                "event_support_refs": ["hearing request form"],
            },
        )
    )

    intake_case_file = build_intake_case_file(knowledge_graph)

    canonical_fact_by_id = {fact["fact_id"]: fact for fact in intake_case_file["canonical_facts"]}
    assert canonical_fact_by_id["fact:protected"]["sequence_index"] == 1
    assert canonical_fact_by_id["fact:protected"]["source_artifact_ids"] == ["grievance request email"]
    assert canonical_fact_by_id["fact:hearing"]["event_date_or_range"] == "after that action"

    relation_pairs = {
        (relation["source_fact_id"], relation["target_fact_id"], relation.get("inference_basis"))
        for relation in intake_case_file["timeline_relations"]
    }
    assert ("fact:protected", "fact:adverse", "structured_timeline_sequence") in relation_pairs
    assert ("fact:adverse", "fact:hearing", "structured_timeline_sequence") in relation_pairs

    relation_registry = intake_case_file["temporal_relation_registry"]
    assert any(
        relation["source_fact_id"] == "fact:protected"
        and relation["target_fact_id"] == "fact:adverse"
        and relation["inference_mode"] == "derived_from_structured_sequence"
        for relation in relation_registry
    )


def test_build_intake_case_file_does_not_promote_structured_timeline_description_into_pseudo_date():
    knowledge_graph = KnowledgeGraph()
    knowledge_graph.add_entity(
        Entity(
            id="fact:response",
            type="fact",
            name="Response event: delayed hearing response",
            attributes={
                "description": "HACC response to hearing/review request was delayed and unclear. Artifact: response email.",
                "fact_type": "timeline",
                "predicate_family": "response_timeline",
                "event_label": "Response event",
                "event_id": "structured_event_response",
                "sequence_index": 5,
                "structured_timeline_group": "structured_timeline_demo",
                "event_date_or_range": "",
                "source_artifact_ids": ["response email"],
                "event_support_refs": ["response email"],
            },
        )
    )

    intake_case_file = build_intake_case_file(knowledge_graph)
    response_fact = intake_case_file["canonical_facts"][0]

    assert response_fact["event_date_or_range"] is None
    assert response_fact["temporal_context"]["raw_text"] == ""
    assert response_fact["temporal_context"]["start_date"] is None


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
