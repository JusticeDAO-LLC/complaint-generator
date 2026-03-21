from types import SimpleNamespace
from unittest.mock import Mock

import pytest
BeautifulSoup = pytest.importorskip("bs4").BeautifulSoup
FastAPI = pytest.importorskip("fastapi").FastAPI
Response = pytest.importorskip("fastapi").Response

from applications.review_api import attach_claim_support_review_routes
from applications.review_ui import attach_claim_support_review_ui_routes
from claim_support_review import (
    ClaimSupportDocumentSaveRequest,
    ClaimSupportFollowUpExecuteRequest,
    ClaimSupportManualReviewResolveRequest,
    ClaimSupportReviewRequest,
    ClaimSupportTestimonySaveRequest,
)


pytestmark = pytest.mark.no_auto_network


def _build_dashboard_app(mediator: Mock) -> FastAPI:
    app = FastAPI()
    attach_claim_support_review_routes(app, mediator)
    attach_claim_support_review_ui_routes(app)
    return app


def _build_dashboard_mediator() -> Mock:
    mediator = Mock()
    mediator.state = SimpleNamespace(username="dashboard-user", hashed_username=None)
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "iteration_count": 3,
        "intake_readiness": {
            "score": 0.42,
            "ready_to_advance": False,
            "remaining_gap_count": 2,
            "contradiction_count": 1,
            "blockers": ["resolve_contradictions", "collect_missing_timeline_details"],
        },
        "intake_contradictions": [
            {
                "summary": "Complaint date conflicts with schedule-cut date",
                "left_text": "The complaint was made before the schedule change.",
                "right_text": "The schedule change came before the complaint.",
                "question": "What were the exact dates for the complaint and the schedule change?",
                "severity": "high",
                "category": "timeline",
            }
        ],
        "alignment_task_updates": [
            {
                "task_id": "retaliation:causation:resolve_support_conflicts",
                "claim_type": "retaliation",
                "claim_element_id": "causal_connection",
                "action": "resolve_support_conflicts",
                "previous_support_status": "unsupported",
                "current_support_status": "contradicted",
                "previous_missing_fact_bundle": ["Event sequence", "Manager knowledge"],
                "current_missing_fact_bundle": ["Event sequence"],
                "resolution_status": "needs_manual_review",
                "status": "active",
                "evidence_artifact_id": "artifact-conflict",
            }
        ],
        "alignment_task_update_history": [
            {
                "task_id": "retaliation:causation:fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "causal_connection",
                "action": "fill_evidence_gaps",
                "previous_support_status": "",
                "current_support_status": "unsupported",
                "previous_missing_fact_bundle": [],
                "current_missing_fact_bundle": ["Event sequence", "Manager knowledge"],
                "resolution_status": "still_open",
                "status": "active",
                "evidence_artifact_id": "artifact-open",
                "evidence_sequence": 1,
            },
            {
                "task_id": "retaliation:causation:resolve_support_conflicts",
                "claim_type": "retaliation",
                "claim_element_id": "causal_connection",
                "action": "resolve_support_conflicts",
                "previous_support_status": "unsupported",
                "current_support_status": "contradicted",
                "previous_missing_fact_bundle": ["Event sequence", "Manager knowledge"],
                "current_missing_fact_bundle": ["Event sequence"],
                "resolution_status": "needs_manual_review",
                "status": "active",
                "evidence_artifact_id": "artifact-conflict",
                "evidence_sequence": 2,
            }
        ],
    }
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "total_elements": 2,
                "total_links": 2,
                "total_facts": 3,
                "support_by_kind": {"evidence": 1, "authority": 1},
                "authority_treatment_summary": {
                    "authority_link_count": 1,
                    "treated_authority_link_count": 1,
                    "supportive_authority_link_count": 0,
                    "adverse_authority_link_count": 1,
                    "uncertain_authority_link_count": 0,
                    "treatment_type_counts": {
                        "questioned": 1,
                    },
                    "max_treatment_confidence": 0.82,
                },
                "support_packet_summary": {
                    "total_packet_count": 3,
                    "fact_packet_count": 3,
                    "link_only_packet_count": 0,
                    "historical_capture_count": 2,
                    "artifact_family_counts": {
                        "archived_web_page": 2,
                        "legal_authority_reference": 1,
                    },
                    "content_origin_counts": {
                        "historical_archive_capture": 2,
                        "authority_reference_fallback": 1,
                    },
                    "capture_source_counts": {
                        "archived_domain_scrape": 2,
                    },
                    "fallback_mode_counts": {
                        "citation_title_only": 1,
                    },
                    "content_source_field_counts": {
                        "citation_title_fallback": 1,
                    },
                },
                "status_counts": {
                    "covered": 1,
                    "partially_supported": 0,
                    "missing": 1,
                },
                "elements": [
                    {
                        "element_id": "retaliation:1",
                        "element_text": "Protected activity",
                        "status": "covered",
                        "fact_count": 2,
                        "total_links": 2,
                        "authority_treatment_summary": {
                            "authority_link_count": 1,
                            "treated_authority_link_count": 1,
                            "supportive_authority_link_count": 0,
                            "adverse_authority_link_count": 1,
                            "uncertain_authority_link_count": 0,
                            "treatment_type_counts": {
                                "questioned": 1,
                            },
                            "max_treatment_confidence": 0.82,
                        },
                        "missing_support_kinds": [],
                        "support_packet_summary": {
                            "total_packet_count": 3,
                            "fact_packet_count": 3,
                            "link_only_packet_count": 0,
                            "historical_capture_count": 2,
                            "content_origin_counts": {
                                "historical_archive_capture": 2,
                                "authority_reference_fallback": 1,
                            },
                            "fallback_mode_counts": {
                                "citation_title_only": 1,
                            },
                        },
                        "support_packets": [
                            {
                                "support_kind": "evidence",
                                "support_ref": "QmTimelineEmail",
                                "support_label": "Timeline email",
                                "fact": {
                                    "fact_id": "fact:timeline-email",
                                    "text": "Employee preserved the retaliation timeline in an archived email.",
                                    "confidence": 0.98,
                                },
                                "lineage_summary": {
                                    "content_origin": "historical_archive_capture",
                                    "historical_capture": True,
                                    "capture_source": "archived_domain_scrape",
                                    "archive_url": "https://web.archive.org/web/20240101120000/https://example.com/timeline-email",
                                    "original_url": "https://example.com/timeline-email",
                                    "fallback_mode": "",
                                    "content_source_field": "content",
                                },
                            },
                            {
                                "support_kind": "authority",
                                "support_ref": "42 U.S.C. § 2000e-3",
                                "support_label": "Retaliation citation",
                                "fact": {
                                    "fact_id": "fact:retaliation-citation",
                                    "text": "Title and citation fallback preserved the retaliation authority reference.",
                                    "confidence": 0.91,
                                },
                                "lineage_summary": {
                                    "content_origin": "authority_reference_fallback",
                                    "historical_capture": False,
                                    "capture_source": "",
                                    "archive_url": "",
                                    "original_url": "",
                                    "fallback_mode": "citation_title_only",
                                    "content_source_field": "citation_title_fallback",
                                },
                            },
                        ],
                        "links_by_kind": {
                            "evidence": [
                                {
                                    "support_label": "Timeline email",
                                    "graph_summary": {
                                        "entity_count": 2,
                                        "relationship_count": 1,
                                    },
                                }
                            ]
                        },
                    },
                    {
                        "element_id": "retaliation:2",
                        "element_text": "Causal connection",
                        "status": "partially_supported",
                        "fact_count": 1,
                        "total_links": 1,
                        "authority_treatment_summary": {},
                        "missing_support_kinds": ["authority"],
                        "support_packet_summary": {},
                        "support_packets": [],
                        "links_by_kind": {},
                        "links": [],
                    }
                ],
            }
        }
    }
    mediator.get_claim_overview.return_value = {
        "claims": {
            "retaliation": {
                "missing": [{"element_text": "Causal connection"}],
                "partially_supported": [],
            }
        }
    }
    mediator.get_claim_support_diagnostic_snapshots.return_value = {"claims": {}}
    mediator.get_claim_support_gaps.return_value = {
        "claims": {
            "retaliation": {
                "unresolved_count": 1,
                "unresolved_elements": [
                    {
                        "element_id": "retaliation:2",
                        "element_text": "Causal connection",
                        "status": "missing",
                        "missing_support_kinds": ["authority"],
                        "total_links": 0,
                        "fact_count": 0,
                        "recommended_action": "collect_initial_support",
                    }
                ],
            }
        }
    }
    mediator.get_claim_contradiction_candidates.return_value = {
        "claims": {
            "retaliation": {
                "candidate_count": 1,
                "candidates": [
                    {
                        "claim_element_id": "retaliation:2",
                        "claim_element_text": "Causal connection",
                        "fact_ids": ["fact:causal-contradiction", "fact:causal-support"],
                        "overlap_terms": ["complaint", "schedule"],
                    }
                ],
            }
        }
    }
    mediator.get_claim_support_validation.return_value = {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "proof_diagnostics": {
                    "reasoning": {
                        "adapter_status_counts": {
                            "logic_proof": {"implemented": 1},
                            "logic_contradictions": {"implemented": 1},
                            "hybrid_reasoning": {"implemented": 1},
                            "ontology_build": {"implemented": 1},
                            "ontology_validation": {"implemented": 1},
                        },
                        "backend_available_count": 4,
                        "predicate_count": 4,
                        "ontology_entity_count": 0,
                        "ontology_relationship_count": 0,
                        "fallback_ontology_count": 0,
                        "hybrid_bridge_available_count": 1,
                        "hybrid_tdfol_formula_count": 2,
                        "hybrid_dcec_formula_count": 1,
                        "temporal_fact_count": 2,
                        "temporal_relation_count": 1,
                        "temporal_issue_count": 1,
                        "temporal_partial_order_ready_count": 0,
                        "temporal_warning_count": 1,
                        "temporal_rule_profile_available_count": 1,
                        "temporal_rule_profile_satisfied_count": 0,
                        "temporal_rule_profile_partial_count": 1,
                        "temporal_rule_profile_failed_count": 0,
                        "temporal_proof_bundle_count": 1,
                    },
                    "decision": {
                        "decision_source_counts": {
                            "logic_proof_supported": 1,
                            "heuristic_contradictions": 1,
                        },
                    },
                },
                "claim_temporal_issue_count": 2,
                "claim_unresolved_temporal_issue_count": 1,
                "claim_resolved_temporal_issue_count": 1,
                "claim_temporal_issue_status_counts": {"open": 1, "resolved": 1},
                "elements": [
                    {
                        "element_id": "retaliation:1",
                        "element_text": "Protected activity",
                        "validation_status": "supported",
                        "recommended_action": "review_existing_support",
                        "proof_gap_count": 0,
                        "proof_gaps": [],
                        "proof_decision_trace": {
                            "decision_source": "logic_proof_supported",
                        },
                        "proof_diagnostics": {
                            "decision_source": "logic_proof_supported",
                        },
                        "reasoning_diagnostics": {
                            "predicate_count": 4,
                            "backend_available_count": 4,
                            "used_fallback_ontology": False,
                            "adapter_statuses": {
                                "logic_proof": {
                                    "backend_available": True,
                                    "implementation_status": "implemented",
                                },
                                "logic_contradictions": {
                                    "backend_available": True,
                                    "implementation_status": "implemented",
                                },
                                "hybrid_reasoning": {
                                    "backend_available": True,
                                    "implementation_status": "implemented",
                                    "operation": "run_hybrid_reasoning",
                                },
                                "ontology_build": {
                                    "backend_available": True,
                                    "implementation_status": "implemented",
                                },
                                "ontology_validation": {
                                    "backend_available": True,
                                    "implementation_status": "implemented",
                                },
                            },
                            "hybrid_reasoning": {
                                "status": "success",
                                "result": {
                                    "formalism": "tdfol_dcec_bridge_v1",
                                    "reasoning_mode": "temporal_bridge",
                                    "compiler_bridge_available": True,
                                    "compiler_bridge_path": "ipfs_datasets_py.ipfs_datasets_py.processors.legal_data.reasoner.hybrid_v2_blueprint",
                                    "tdfol_formulas": [
                                        "Before(fact_1,fact_2)",
                                        "forall t (AtTime(t,t_2026_03_10) -> Fact(fact_1,t))",
                                    ],
                                    "dcec_formulas": [
                                        "Happens(fact_1,t_2026_03_10)",
                                    ],
                                },
                            },
                            "temporal_summary": {
                                "fact_count": 2,
                                "proof_lead_count": 1,
                                "relation_count": 1,
                                "issue_count": 1,
                                "partial_order_ready": False,
                                "warning_count": 1,
                                "warnings": [
                                    "Some timeline facts only express relative ordering and still need anchoring.",
                                ],
                                "relation_type_counts": {"before": 1},
                                "relation_preview": ["fact_001 before fact_termination"],
                            },
                            "temporal_rule_profile": {
                                "available": True,
                                "profile_id": "retaliation_temporal_profile_v1",
                                "rule_frame_id": "retaliation_temporal_frame",
                                "status": "partial",
                                "blocking_reasons": [
                                    "Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.",
                                ],
                                "warnings": [
                                    "Protected activity and adverse action are both present but lack an ordering relation.",
                                ],
                                "recommended_follow_ups": [
                                    {
                                        "lane": "clarify_with_complainant",
                                        "reason": "Clarify whether the protected activity occurred before the adverse action.",
                                    }
                                ],
                            },
                            "temporal_proof_bundle": {
                                "proof_bundle_id": "retaliation:retaliation_1:retaliation_temporal_profile_v1",
                                "status": "partial",
                                "temporal_fact_ids": ["fact_001", "fact_termination"],
                                "temporal_relation_ids": ["timeline_relation_001"],
                                "temporal_issue_ids": ["temporal_issue_001"],
                                "theorem_exports": {
                                    "tdfol_formulas": [
                                        "ProtectedActivity(fact_001)",
                                        "AdverseAction(fact_termination)",
                                    ],
                                    "dcec_formulas": [
                                        "Happens(fact_001,t_2026_03_10)",
                                        "Happens(fact_termination,t_2026_03_24)",
                                    ],
                                    "theorem_export_metadata": {
                                        "contract_version": "claim_support_temporal_handoff_v1",
                                        "claim_type": "retaliation",
                                        "claim_element_id": "retaliation:1",
                                        "proof_bundle_id": "retaliation:retaliation_1:retaliation_temporal_profile_v1",
                                        "rule_frame_id": "retaliation_temporal_frame",
                                        "chronology_blocked": True,
                                        "chronology_task_count": 1,
                                        "unresolved_temporal_issue_ids": ["temporal_issue_001"],
                                        "event_ids": ["fact_001", "fact_termination"],
                                        "temporal_fact_ids": ["fact_001", "fact_termination"],
                                        "temporal_relation_ids": ["timeline_relation_001"],
                                        "timeline_issue_ids": ["temporal_issue_001"],
                                        "temporal_issue_ids": ["temporal_issue_001"],
                                        "temporal_proof_bundle_ids": ["retaliation:retaliation_1:retaliation_temporal_profile_v1"],
                                        "temporal_proof_objectives": ["retaliation_temporal_frame"],
                                    },
                                },
                            },
                        },
                        "contradiction_candidates": [],
                    },
                    {
                        "element_id": "retaliation:2",
                        "element_text": "Causal connection",
                        "validation_status": "contradicted",
                        "recommended_action": "resolve_contradiction",
                        "proof_gap_count": 1,
                        "proof_gaps": [
                            {
                                "gap_type": "contradiction_candidates",
                                "message": "Conflicting support facts require operator review.",
                            }
                        ],
                        "proof_decision_trace": {
                            "decision_source": "heuristic_contradictions",
                        },
                        "proof_diagnostics": {
                            "decision_source": "heuristic_contradictions",
                        },
                        "contradiction_candidates": [
                            {
                                "fact_ids": ["fact:causal-contradiction", "fact:causal-support"],
                                "overlap_terms": ["complaint", "schedule"],
                            }
                        ],
                    }
                ],
            }
        }
    }
    mediator.get_claim_support_facts.side_effect = lambda **kwargs: [
        {
            "fact_id": "fact:timeline-email",
            "fact_text": "Employee preserved the retaliation timeline in an archived email.",
            "support_kind": "evidence",
            "source_table": "evidence",
            "source_family": "evidence",
            "source_ref": "QmDashboardDoc1",
            "artifact_family": "document",
            "content_origin": "operator_document_intake",
            "quality_tier": "high",
            "record_id": 81,
        },
        {
            "fact_id": "fact:retaliation-citation",
            "fact_text": "Title and citation fallback preserved the retaliation authority reference.",
            "support_kind": "authority",
            "source_table": "legal_authorities",
            "source_family": "legal_authority",
            "source_ref": "42 U.S.C. § 2000e-3",
            "artifact_family": "legal_authority_reference",
            "content_origin": "authority_reference_fallback",
            "quality_tier": "high",
            "record_id": 44,
        },
    ] if kwargs.get("claim_element_text") == "Protected activity" else ([
        {
            "fact_id": "fact:causal-contradiction",
            "fact_text": "The schedule reduction happened before the complaint.",
            "support_kind": "authority",
            "source_table": "legal_authorities",
            "source_family": "legal_authority",
            "source_ref": "Contrary Source",
            "artifact_family": "legal_authority_reference",
            "content_origin": "authority_reference_fallback",
            "quality_tier": "high",
            "record_id": 44,
        }
        ,
        {
            "fact_id": "fact:causal-support",
            "fact_text": "The schedule reduction followed the complaint.",
            "support_kind": "evidence",
            "source_table": "evidence",
            "source_family": "evidence",
            "source_ref": "QmDashboardDoc1",
            "artifact_family": "document",
            "content_origin": "operator_document_intake",
            "quality_tier": "high",
            "record_id": 81,
        }
    ] if kwargs.get("claim_element_text") == "Causal connection" else [])
    mediator.get_recent_claim_follow_up_execution.return_value = {
        "claims": {
            "retaliation": [
                {
                    "execution_id": 21,
                    "claim_type": "retaliation",
                    "claim_element_id": "retaliation:2",
                    "claim_element_text": "Adverse action",
                    "support_kind": "manual_review",
                    "query_text": "manual_review::retaliation::retaliation:2::resolve_contradiction",
                    "status": "skipped_manual_review",
                    "timestamp": "2026-03-12T12:35:00",
                    "execution_mode": "manual_review",
                    "follow_up_focus": "contradiction_resolution",
                    "query_strategy": "standard_gap_targeted",
                    "resolution_applied": "",
                },
                {
                    "execution_id": 44,
                    "claim_type": "retaliation",
                    "claim_element_id": "retaliation:2",
                    "claim_element_text": "Causal connection",
                    "support_kind": "authority",
                    "query_text": '"retaliation" "Causal connection" statute',
                    "status": "executed",
                    "timestamp": "2026-03-12T12:30:00",
                    "execution_mode": "retrieve_support",
                    "follow_up_focus": "parse_quality_improvement",
                    "query_strategy": "quality_gap_targeted",
                    "resolution_applied": "manual_review_resolved",
                    "source_family": "legal_authority",
                    "record_scope": "legal_authority",
                    "artifact_family": "legal_authority_reference",
                    "corpus_family": "legal_authority",
                    "content_origin": "authority_reference_fallback",
                    "selected_search_program_type": "element_definition_search",
                    "selected_search_program_bias": "uncertain",
                    "selected_search_program_rule_bias": "procedural_prerequisite",
                },
                {
                    "execution_id": 45,
                    "claim_type": "retaliation",
                    "claim_element_id": "retaliation:2",
                    "claim_element_text": "Causal connection",
                    "support_kind": "testimony",
                    "query_text": "clarify retaliation chronology",
                    "status": "escalated",
                    "timestamp": "2026-03-12T13:00:00",
                    "execution_mode": "resolution_handoff",
                    "follow_up_focus": "temporal_gap_closure",
                    "query_strategy": "temporal_gap_targeted",
                    "primary_missing_fact": "Event sequence",
                    "missing_fact_bundle": ["Event sequence"],
                    "satisfied_fact_bundle": [],
                    "resolution_status": "awaiting_testimony",
                    "resolution_applied": "skipped_resolution_handoff",
                    "intake_proof_leads": [
                        {
                            "lead_id": "lead:complainant:chronology",
                            "owner": "complainant",
                            "recommended_support_kind": "testimony",
                            "description": "Chronology clarification from complainant",
                        }
                    ],
                    "temporal_rule_profile_id": "retaliation_temporal_profile_v1",
                    "temporal_rule_status": "partial",
                    "temporal_rule_blocking_reasons": [
                        "Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.",
                    ],
                    "temporal_rule_follow_ups": [
                        "Clarify whether the protected activity occurred before the adverse action.",
                    ],
                }
            ]
        }
    }
    mediator.resolve_claim_follow_up_manual_review.return_value = {
        "recorded": True,
        "status": "resolved_manual_review",
        "execution_id": 91,
    }
    mediator.save_claim_testimony_record.return_value = {
        "recorded": True,
        "testimony_id": "testimony:retaliation:dash-1",
    }
    mediator.save_claim_support_document.return_value = {
        "record_id": 81,
        "cid": "QmDashboardDoc1",
        "recorded": True,
    }
    mediator.get_claim_testimony_records.return_value = {
        "claims": {
            "retaliation": [
                {
                    "testimony_id": "testimony:retaliation:dash-1",
                    "claim_type": "retaliation",
                    "claim_element_id": "retaliation:2",
                    "claim_element_text": "Causal connection",
                    "raw_narrative": "I complained on Monday and my schedule was cut on Wednesday.",
                    "event_date": "2026-03-10",
                    "actor": "Supervisor",
                    "act": "cut schedule",
                    "target": "work hours",
                    "harm": "lost pay",
                    "firsthand_status": "firsthand",
                    "source_confidence": 0.88,
                    "timestamp": "2026-03-14T12:00:00+00:00",
                }
            ]
        },
        "summary": {
            "retaliation": {
                "record_count": 1,
                "linked_element_count": 1,
                "firsthand_status_counts": {"firsthand": 1},
                "confidence_bucket_counts": {"high": 1},
            }
        },
    }
    mediator.get_user_evidence.return_value = [
        {
            "id": 81,
            "cid": "QmDashboardDoc1",
            "type": "document",
            "claim_type": "retaliation",
            "claim_element_id": "retaliation:2",
            "claim_element": "Causal connection",
            "description": "Schedule reduction memo",
            "timestamp": "2026-03-14T12:05:00+00:00",
            "source_url": "https://example.com/schedule-memo",
            "parse_status": "parsed",
            "chunk_count": 2,
            "fact_count": 1,
            "parsed_text_preview": "The memo describes a schedule reduction after the complaint.",
            "parse_metadata": {"quality_tier": "high", "quality_score": 93.0},
            "graph_status": "ready",
            "graph_entity_count": 3,
            "graph_relationship_count": 1,
        }
    ]
    mediator.get_evidence_chunks.return_value = [
        {"chunk_id": "chunk-0", "index": 0, "text": "Schedule reduction followed the complaint."},
    ]
    mediator.get_evidence_facts.return_value = [
        {
            "fact_id": "fact:schedule-memo:1",
            "text": "The schedule reduction followed the complaint.",
            "confidence": 0.89,
            "quality_tier": "high",
        }
    ]
    mediator.get_evidence_graph.return_value = {
        "status": "ready",
        "entities": [
            {"id": "entity:complaint", "type": "event", "name": "Complaint"},
            {"id": "entity:schedule", "type": "employment_action", "name": "Schedule reduction"},
        ],
        "relationships": [
            {
                "id": "rel:after",
                "source_id": "entity:schedule",
                "target_id": "entity:complaint",
                "relation_type": "after",
            }
        ],
    }
    mediator.get_claim_follow_up_plan.return_value = {
        "claims": {
            "retaliation": {
                "task_count": 2,
                "blocked_task_count": 0,
                "tasks": [
                    {
                        "claim_element": "Causal connection",
                        "status": "missing",
                        "priority": "high",
                        "recommended_action": "improve_parse_quality",
                        "graph_support": {
                            "summary": {
                                "semantic_cluster_count": 1,
                                "semantic_duplicate_count": 0,
                                "support_by_kind": {
                                    "authority": 1,
                                },
                            },
                            "results": [
                                {
                                    "source_family": "legal_authority",
                                    "record_scope": "legal_authority",
                                    "artifact_family": "legal_authority_reference",
                                    "corpus_family": "legal_authority",
                                    "content_origin": "authority_reference_fallback",
                                }
                            ],
                        },
                        "authority_search_program_summary": {
                            "program_count": 1,
                            "program_type_counts": {
                                "element_definition_search": 1,
                            },
                            "authority_intent_counts": {
                                "support": 1,
                            },
                            "primary_program_id": "legal_search_program:dashboard-1",
                            "primary_program_type": "element_definition_search",
                            "primary_program_bias": "uncertain",
                            "primary_program_rule_bias": "procedural_prerequisite",
                        },
                        "follow_up_focus": "parse_quality_improvement",
                        "query_strategy": "quality_gap_targeted",
                        "missing_support_kinds": ["authority"],
                        "blocked_by_cooldown": False,
                        "should_suppress_retrieval": False,
                        "resolution_applied": "manual_review_resolved",
                    },
                    {
                        "claim_element": "Causal connection",
                        "claim_element_id": "retaliation:2",
                        "status": "missing",
                        "priority": "high",
                        "recommended_action": "review_existing_support",
                        "graph_support": {
                            "summary": {},
                            "results": [],
                        },
                        "follow_up_focus": "temporal_gap_closure",
                        "query_strategy": "temporal_gap_targeted",
                        "missing_support_kinds": ["testimony"],
                        "primary_missing_fact": "Event sequence",
                        "missing_fact_bundle": ["Event sequence"],
                        "satisfied_fact_bundle": [],
                        "blocked_by_cooldown": False,
                        "should_suppress_retrieval": False,
                        "resolution_status": "awaiting_testimony",
                        "intake_proof_leads": [
                            {
                                "lead_id": "lead:complainant:chronology",
                                "owner": "complainant",
                                "recommended_support_kind": "testimony",
                                "description": "Chronology clarification from complainant",
                            }
                        ],
                        "temporal_rule_profile_id": "retaliation_temporal_profile_v1",
                        "temporal_rule_status": "partial",
                        "temporal_rule_blocking_reasons": [
                            "Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.",
                        ],
                        "temporal_rule_follow_ups": [
                            "Clarify whether the protected activity occurred before the adverse action.",
                        ],
                    }
                ],
            }
        }
    }
    mediator.summarize_claim_support.return_value = {
        "claims": {
            "retaliation": {
                "total_links": 2,
                "support_by_kind": {"evidence": 1, "authority": 1},
            }
        }
    }
    mediator.execute_claim_follow_up_plan.return_value = {
        "claims": {
            "retaliation": {
                "task_count": 1,
                "tasks": [
                    {
                        "claim_element": "Causal connection",
                        "follow_up_focus": "parse_quality_improvement",
                        "query_strategy": "quality_gap_targeted",
                        "graph_support": {
                            "summary": {
                                "semantic_cluster_count": 1,
                                "semantic_duplicate_count": 0,
                                "support_by_kind": {
                                    "authority": 1,
                                },
                            },
                            "results": [
                                {
                                    "source_family": "legal_authority",
                                    "record_scope": "legal_authority",
                                    "artifact_family": "legal_authority_reference",
                                    "corpus_family": "legal_authority",
                                    "content_origin": "authority_reference_fallback",
                                }
                            ],
                        },
                    }
                ],
                "skipped_tasks": [],
            }
        }
    }
    return mediator


async def test_claim_support_review_dashboard_flow_serves_page_and_supports_api_round_trip():
    mediator = _build_dashboard_mediator()
    app = _build_dashboard_app(mediator)
    page_route = next(
        route for route in app.routes if getattr(route, "path", None) == "/claim-support-review"
    )
    review_route = next(
        route for route in app.routes if getattr(route, "path", None) == "/api/claim-support/review"
    )
    execute_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/claim-support/execute-follow-up"
    )
    resolve_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/claim-support/resolve-manual-review"
    )
    testimony_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/claim-support/save-testimony"
    )
    document_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/claim-support/save-document"
    )

    page_html = await page_route.endpoint()

    soup = BeautifulSoup(page_html, "html.parser")
    assert soup.find(id="claim-type") is not None
    assert soup.find(id="required-kinds") is not None
    assert soup.find(id="review-button") is not None
    assert soup.find(id="execute-button") is not None
    assert soup.find(id="resolve-button") is not None
    assert soup.find(id="save-testimony-button") is not None
    assert soup.find(id="save-document-button") is not None
    assert soup.find(id="document-file-input") is not None
    assert soup.find(id="question-list") is not None
    assert soup.find(id="testimony-list") is not None
    assert soup.find(id="testimony-summary-chips") is not None
    assert soup.find(id="document-list") is not None
    assert soup.find(id="document-summary-chips") is not None
    assert soup.find(id="clear-resolution-button") is not None
    assert soup.find(id="resolution-element-id") is not None
    assert soup.find(id="resolution-notes") is not None
    assert soup.find(id="resolution-result-card") is not None
    assert soup.find(id="resolution-result-status") is not None
    assert soup.find(id="resolution-result-chips") is not None
    assert soup.find(id="execution-result-card") is not None
    assert soup.find(id="execution-result-status") is not None
    assert soup.find(id="signal-plan-normalized") is not None
    assert soup.find(id="signal-history-normalized") is not None
    assert soup.find(id="signal-follow-up-source-context") is not None
    assert soup.find(id="signal-temporal-gap-tasks") is not None
    assert soup.find(id="intake-status-chips") is not None
    assert soup.find(id="intake-contradiction-list") is not None
    assert soup.find(id="signal-archive-captures") is not None
    assert soup.find(id="signal-fallback-authorities") is not None
    assert soup.find(id="signal-low-quality-records") is not None
    assert soup.find(id="signal-parse-quality-tasks") is not None
    assert soup.find(id="follow-up-task-filter") is not None
    assert soup.find(id="follow-up-task-sort") is not None
    assert soup.find(id="task-filter-summary") is not None
    assert soup.find(id="follow-up-history-filter") is not None
    assert soup.find(id="follow-up-history-sort") is not None
    assert soup.find(id="history-filter-summary") is not None
    assert soup.find(id="history-list") is not None
    assert soup.find(id="history-summary-chips") is not None
    assert "authority program ${task.authority_search_program_summary.primary_program_type}" in page_html
    assert "authority bias ${task.authority_search_program_summary.primary_program_bias}" in page_html
    assert "rule bias ${task.authority_search_program_summary.primary_program_rule_bias}" in page_html
    assert "No graph source context" in page_html
    assert "History programs: ${selectedProgramTypes.map(([label, count]) => `${label}=${count}`).join(', ')}" in page_html
    assert "History biases: ${selectedProgramBiases.map(([label, count]) => `${label}=${count}`).join(', ')}" in page_html
    assert "History rule biases: ${selectedProgramRuleBiases.map(([label, count]) => `${label}=${count}`).join(', ')}" in page_html
    assert "History source context:" in page_html
    assert "Chronology follow-up tasks" in page_html
    assert "Chronology tasks:" in page_html
    assert "Chronology targeted:" in page_html
    assert "Chronology status" in page_html
    assert "Chronology blockers" in page_html
    assert "Chronology handoffs" in page_html
    assert "Alignment chronology summary" in page_html
    assert "packet chronology tasks:" in page_html
    assert "packet chronology targeted:" in page_html
    assert "packet chronology status:" in page_html
    assert "packet chronology blockers:" in page_html
    assert "packet chronology handoffs:" in page_html
    assert "chronology follow-up" in page_html
    assert "chronology targeted" in page_html
    assert "chronology profile:" in page_html
    assert "chronology blocker:" in page_html
    assert "Follow-Up Plan Filter" in page_html
    assert "Follow-Up Plan Sort" in page_html
    assert "Follow-Up History Filter" in page_html
    assert "Follow-Up History Sort" in page_html
    assert "follow_up_task_filter" in page_html
    assert "follow_up_task_sort" in page_html
    assert "follow_up_history_filter" in page_html
    assert "follow_up_history_sort" in page_html
    assert "No follow-up tasks match the selected filter." in page_html
    assert "No follow-up history matches the selected filter." in page_html
    assert "program: ${entry.selected_search_program_type}" in page_html
    assert "rule bias: ${entry.selected_search_program_rule_bias}" in page_html
    assert "family: ${entry.source_family}" in page_html
    assert "artifact: ${entry.artifact_family}" in page_html
    assert "origin: ${entry.content_origin}" in page_html
    assert "View lineage packets" in page_html
    assert "packet-details" in page_html
    assert "All packets" in page_html
    assert "Archived only" in page_html
    assert "Fallback only" in page_html
    assert "data-packet-filter-button" in page_html
    assert "packet-filter-count" in page_html
    assert "data-packet-filter-summary" in page_html
    assert "data-packet-url-action" in page_html
    assert "supportPackets.length" in page_html
    assert "archivedPacketCount" in page_html
    assert "fallbackPacketCount" in page_html
    assert "Showing ${supportPackets.length} of ${supportPackets.length} packets" in page_html
    assert "Showing ${visibleCount} of ${totalCount} packets" in page_html
    assert "Open archive" in page_html
    assert "Copy archive" in page_html
    assert "Open original" in page_html
    assert "Copy original" in page_html
    assert "copyPacketUrl" in page_html
    assert "openPacketUrl" in page_html
    assert "data-packet-action-feedback" in page_html
    assert "setPacketActionFeedback" in page_html
    assert "packetSortRank" in page_html
    assert "sortSupportPackets" in page_html
    assert "Save Testimony" in page_html
    assert "Save Document" in page_html
    assert "buildDocumentUploadFormData" in page_html
    assert "postFormData" in page_html
    assert "renderIntakeStatus" in page_html
    assert "renderQuestionRecommendations" in page_html
    assert "renderTestimonyRecords" in page_html
    assert "renderDocumentArtifacts" in page_html
    assert "Timeline Ordering" in page_html
    assert "intake-timeline-summary-chips" in page_html
    assert "intake-timeline-relation-list" in page_html
    assert "renderTimelineOrdering" in page_html
    assert "No timeline ordering diagnostics available." in page_html
    assert "Timeline ordering diagnostics are not available for this intake summary." in page_html
    assert "Timeline consistency warnings" in page_html
    assert "partial order ready" in page_html
    assert "Hybrid Reasoning Diagnostics" in page_html
    assert "claim-reasoning-summary-chips" in page_html
    assert "claim-reasoning-flagged-list" in page_html
    assert "renderClaimReasoningReview" in page_html
    assert "Temporal proof handoff" in page_html
    assert "Temporal relation preview" in page_html
    assert "Temporal warnings" in page_html
    assert "Temporal rule profiles" in page_html
    assert "Temporal proof bundles" in page_html
    assert "Temporal rule blockers" in page_html
    assert "Temporal rule follow-ups" in page_html
    assert "Temporal proof bundle TDFOL preview" in page_html
    assert "Temporal proof bundle DCEC preview" in page_html
    assert "packet temporal facts" in page_html
    assert "packet temporal relations" in page_html
    assert "packet temporal issues" in page_html
    assert "packet temporal warnings" in page_html
    assert "Claim-level hybrid bridge" in page_html
    assert "No hybrid reasoning bridge diagnostics surfaced for this claim." in page_html
    assert "TDFOL preview" in page_html
    assert "DCEC preview" in page_html
    assert "Alignment Task Updates" in page_html
    assert "Task Update Filter" in page_html
    assert "alignment-task-update-filter" in page_html
    assert "alignment-task-update-filter-summary" in page_html
    assert "pending_review" in page_html
    assert "alignment-task-manual-review-summary" in page_html
    assert "alignment-task-manual-review-list" in page_html
    assert "alignment-task-pending-review-summary" in page_html
    assert "alignment-task-pending-review-list" in page_html
    assert "manual review blockers: ${manualReviewBlockers.length}" in page_html
    assert "claims impacted: ${manualReviewClaims.size}" in page_html
    assert "Manual review blocker for ${update.claim_type || 'claim'}" in page_html
    assert "Load Into Resolution Form" in page_html
    assert "Manual review blockers: none currently escalated." in page_html
    assert "pending review items: ${pendingReviewItems.length}" in page_html
    assert "claims impacted: ${pendingReviewClaims.size}" in page_html
    assert "Pending review item for ${update.claim_type || 'claim'}" in page_html
    assert "Load Into Testimony Form" in page_html
    assert "Load Into Document Form" in page_html
    assert "Pending review items: none currently awaiting operator confirmation." in page_html
    assert "alignment_task_update_filter" in page_html
    assert "Task Update Sort" in page_html
    assert "alignment-task-update-sort" in page_html
    assert "pending_review_first" in page_html
    assert "alignment_task_update_sort" in page_html
    assert "alignment-task-update-list" in page_html
    assert "Alignment task updates: no recent evidence-driven task changes recorded." in page_html
    assert "filter: ${taskUpdateFilterValue}" in page_html
    assert "sort: ${taskUpdateSortValue}" in page_html
    assert "visible updates: ${filteredAlignmentTaskUpdates.length}" in page_html
    assert "total updates: ${visibleAlignmentTaskUpdates.length}" in page_html
    assert "Alignment update for ${update.claim_type || 'claim'}" in page_html
    assert "evidence event: ${update.evidence_sequence}" in page_html
    assert "previous support: ${update.previous_support_status}" in page_html
    assert "current support: ${update.current_support_status}" in page_html
    assert "previous gap: ${factNeed}" in page_html
    assert "current gap: ${factNeed}" in page_html
    assert "artifact: ${update.evidence_artifact_id}" in page_html
    assert "filterAlignmentTaskUpdates" in page_html
    assert "sortAlignmentTaskUpdates" in page_html
    assert "prefill-testimony-button" in page_html

    review_payload = await review_route.endpoint(
        ClaimSupportReviewRequest(
            claim_type="retaliation",
            required_support_kinds=["evidence", "authority"],
            include_follow_up_plan=True,
            include_support_summary=True,
            include_overview=True,
            execute_follow_up=False,
            follow_up_cooldown_seconds=3600,
            follow_up_max_tasks_per_claim=2,
        ),
        Response(),
    )
    assert review_payload["user_id"] == "dashboard-user"
    assert review_payload["intake_status"]["current_phase"] == "intake"
    assert review_payload["intake_status"]["contradiction_count"] == 1
    assert review_payload["intake_status"]["blockers"] == [
        "resolve_contradictions",
        "collect_missing_timeline_details",
    ]
    assert review_payload["intake_case_summary"]["alignment_task_updates"] == [
        {
            "task_id": "retaliation:causation:resolve_support_conflicts",
            "claim_type": "retaliation",
            "claim_element_id": "causal_connection",
            "action": "resolve_support_conflicts",
            "previous_support_status": "unsupported",
            "current_support_status": "contradicted",
            "previous_missing_fact_bundle": ["Event sequence", "Manager knowledge"],
            "current_missing_fact_bundle": ["Event sequence"],
            "resolution_status": "needs_manual_review",
            "status": "active",
            "evidence_artifact_id": "artifact-conflict",
        }
    ]
    assert review_payload["intake_case_summary"]["alignment_task_update_history"][0]["evidence_sequence"] == 1
    assert review_payload["intake_case_summary"]["alignment_task_update_history"][1]["evidence_sequence"] == 2
    assert review_payload["intake_status"]["contradictions"][0]["question"] == (
        "What were the exact dates for the complaint and the schedule change?"
    )
    assert review_payload["claim_coverage_summary"]["retaliation"]["missing_elements"] == [
        "Causal connection"
    ]
    assert review_payload["claim_coverage_summary"]["retaliation"]["parse_quality_recommendation"] == ""
    assert review_payload["claim_coverage_summary"]["retaliation"]["authority_treatment_summary"] == {
        "authority_link_count": 1,
        "treated_authority_link_count": 1,
        "supportive_authority_link_count": 0,
        "adverse_authority_link_count": 1,
        "uncertain_authority_link_count": 0,
        "treatment_type_counts": {
            "questioned": 1,
        },
        "max_treatment_confidence": 0.82,
    }
    assert review_payload["claim_coverage_summary"]["retaliation"]["support_packet_summary"] == {
        "total_packet_count": 3,
        "fact_packet_count": 3,
        "link_only_packet_count": 0,
        "historical_capture_count": 2,
        "artifact_family_counts": {
            "archived_web_page": 2,
            "legal_authority_reference": 1,
        },
        "content_origin_counts": {
            "historical_archive_capture": 2,
            "authority_reference_fallback": 1,
        },
        "capture_source_counts": {
            "archived_domain_scrape": 2,
        },
        "fallback_mode_counts": {
            "citation_title_only": 1,
        },
        "content_source_field_counts": {
            "citation_title_fallback": 1,
        },
    }
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["support_packets"][0]["lineage_summary"]["archive_url"] == "https://web.archive.org/web/20240101120000/https://example.com/timeline-email"
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["support_packets"][1]["lineage_summary"]["fallback_mode"] == "citation_title_only"
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["authority_treatment_summary"]["adverse_authority_link_count"] == 1
    assert review_payload["follow_up_plan_summary"]["retaliation"]["task_count"] == 2
    assert review_payload["follow_up_plan_summary"]["retaliation"]["parse_quality_task_count"] == 1
    assert review_payload["follow_up_plan_summary"]["retaliation"]["quality_gap_targeted_task_count"] == 1
    assert review_payload["follow_up_plan_summary"]["retaliation"]["temporal_gap_task_count"] == 1
    assert review_payload["follow_up_plan_summary"]["retaliation"]["temporal_gap_targeted_task_count"] == 1
    assert review_payload["follow_up_plan_summary"]["retaliation"]["authority_search_program_task_count"] == 1
    assert review_payload["follow_up_plan_summary"]["retaliation"]["authority_search_program_type_counts"] == {
        "element_definition_search": 1,
    }
    assert review_payload["question_recommendations"]["retaliation"]
    assert review_payload["testimony_summary"]["retaliation"]["record_count"] == 1
    assert review_payload["document_summary"]["retaliation"]["record_count"] == 1
    assert review_payload["document_summary"]["retaliation"]["total_fact_count"] == 1
    assert review_payload["claim_coverage_summary"]["retaliation"]["document_record_count"] == 1
    assert review_payload["claim_coverage_summary"]["retaliation"]["document_total_fact_count"] == 1
    assert review_payload["claim_coverage_summary"]["retaliation"]["reasoning_hybrid_bridge_available_count"] == 1
    assert review_payload["claim_coverage_summary"]["retaliation"]["reasoning_hybrid_tdfol_formula_count"] == 2
    assert review_payload["claim_coverage_summary"]["retaliation"]["reasoning_hybrid_dcec_formula_count"] == 1
    assert review_payload["claim_coverage_summary"]["retaliation"]["reasoning_temporal_fact_count"] == 2
    assert review_payload["claim_coverage_summary"]["retaliation"]["reasoning_temporal_relation_count"] == 1
    assert review_payload["claim_coverage_summary"]["retaliation"]["reasoning_temporal_issue_count"] == 1
    assert review_payload["claim_coverage_summary"]["retaliation"]["reasoning_temporal_partial_order_ready_count"] == 0
    assert review_payload["claim_coverage_summary"]["retaliation"]["reasoning_temporal_warning_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["hybrid_bridge_element_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["hybrid_bridge_available_element_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["hybrid_tdfol_formula_count"] == 2
    assert review_payload["claim_reasoning_review"]["retaliation"]["hybrid_dcec_formula_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["hybrid_tdfol_formula_preview"] == [
        "Before(fact_1,fact_2)",
        "forall t (AtTime(t,t_2026_03_10) -> Fact(fact_1,t))",
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["hybrid_dcec_formula_preview"] == [
        "Happens(fact_1,t_2026_03_10)",
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["hybrid_formalism"] == "tdfol_dcec_bridge_v1"
    assert review_payload["claim_reasoning_review"]["retaliation"]["hybrid_reasoning_mode"] == "temporal_bridge"
    assert review_payload["claim_reasoning_review"]["retaliation"]["hybrid_compiler_bridge_path"] == (
        "ipfs_datasets_py.ipfs_datasets_py.processors.legal_data.reasoner.hybrid_v2_blueprint"
    )
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_element_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_fact_count"] == 2
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_relation_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_issue_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_partial_order_ready_element_count"] == 0
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_warning_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_warning_preview"] == [
        "Some timeline facts only express relative ordering and still need anchoring.",
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_relation_type_counts"] == {"before": 1}
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_relation_preview"] == [
        "fact_001 before fact_termination"
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_rule_profile_available_element_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_rule_profile_satisfied_element_count"] == 0
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_rule_profile_partial_element_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_rule_profile_failed_element_count"] == 0
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_proof_bundle_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["temporal_proof_bundle_status_counts"] == {"partial": 1}
    assert review_payload["claim_reasoning_review"]["retaliation"]["claim_temporal_issue_count"] == 2
    assert review_payload["claim_reasoning_review"]["retaliation"]["claim_unresolved_temporal_issue_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["claim_resolved_temporal_issue_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["claim_temporal_issue_status_counts"] == {"open": 1, "resolved": 1}
    assert review_payload["claim_reasoning_review"]["retaliation"]["theorem_export_blocked_element_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["theorem_export_chronology_task_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["hybrid_bridge_available"] is True
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["hybrid_tdfol_formula_preview"] == [
        "Before(fact_1,fact_2)",
        "forall t (AtTime(t,t_2026_03_10) -> Fact(fact_1,t))",
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["hybrid_dcec_formula_preview"] == [
        "Happens(fact_1,t_2026_03_10)",
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["hybrid_formalism"] == "tdfol_dcec_bridge_v1"
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["hybrid_reasoning_mode"] == "temporal_bridge"
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["hybrid_compiler_bridge_path"] == (
        "ipfs_datasets_py.ipfs_datasets_py.processors.legal_data.reasoner.hybrid_v2_blueprint"
    )
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_fact_count"] == 2
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_relation_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_issue_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_partial_order_ready"] is False
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_warning_count"] == 1
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_warnings"] == [
        "Some timeline facts only express relative ordering and still need anchoring.",
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_relation_type_counts"] == {"before": 1}
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_relation_preview"] == [
        "fact_001 before fact_termination"
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_rule_profile_id"] == "retaliation_temporal_profile_v1"
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_rule_frame_id"] == "retaliation_temporal_frame"
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_rule_status"] == "partial"
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_rule_blocking_reasons"] == [
        "Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.",
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_rule_warnings"] == [
        "Protected activity and adverse action are both present but lack an ordering relation.",
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_rule_follow_ups"] == [
        {
            "lane": "clarify_with_complainant",
            "reason": "Clarify whether the protected activity occurred before the adverse action.",
        }
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_proof_bundle_id"] == "retaliation:retaliation_1:retaliation_temporal_profile_v1"
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_proof_bundle_status"] == "partial"
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_proof_bundle_fact_ids"] == ["fact_001", "fact_termination"]
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_proof_bundle_relation_ids"] == ["timeline_relation_001"]
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_proof_bundle_issue_ids"] == ["temporal_issue_001"]
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_proof_bundle_tdfol_preview"] == [
        "ProtectedActivity(fact_001)",
        "AdverseAction(fact_termination)",
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["temporal_proof_bundle_dcec_preview"] == [
        "Happens(fact_001,t_2026_03_10)",
        "Happens(fact_termination,t_2026_03_24)",
    ]
    assert review_payload["claim_reasoning_review"]["retaliation"]["flagged_elements"][0]["theorem_export_metadata"] == {
        "contract_version": "claim_support_temporal_handoff_v1",
        "claim_type": "retaliation",
        "claim_element_id": "retaliation:1",
        "proof_bundle_id": "retaliation:retaliation_1:retaliation_temporal_profile_v1",
        "rule_frame_id": "retaliation_temporal_frame",
        "chronology_blocked": True,
        "chronology_task_count": 1,
        "unresolved_temporal_issue_ids": ["temporal_issue_001"],
        "event_ids": ["fact_001", "fact_termination"],
        "temporal_fact_ids": ["fact_001", "fact_termination"],
        "temporal_relation_ids": ["timeline_relation_001"],
        "timeline_issue_ids": ["temporal_issue_001"],
        "temporal_issue_ids": ["temporal_issue_001"],
        "temporal_proof_bundle_ids": ["retaliation:retaliation_1:retaliation_temporal_profile_v1"],
        "temporal_proof_objectives": ["retaliation_temporal_frame"],
    }
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["validation_status"] == "supported"
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["support_fact_packet_count"] == 2
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["support_fact_status_counts"] == {
        "supporting": 2,
        "contradicting": 0,
        "unresolved": 0,
    }
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["document_fact_packet_count"] == 1
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["document_fact_status_counts"] == {
        "supporting": 1,
        "contradicting": 0,
        "unresolved": 0,
    }
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["document_fact_packets"][0]["fact_id"] == "fact:timeline-email"
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["document_fact_packets"][0]["proof_status"] == "supporting"
    assert review_payload["document_artifacts"]["retaliation"][0]["fact_previews"][0]["fact_id"] == "fact:schedule-memo:1"
    assert review_payload["document_artifacts"]["retaliation"][0]["graph_preview"]["relationship_count"] == 1
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][1]["contradiction_pair_count"] == 1
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][1]["contradiction_pairs"][0]["left_fact"]["fact_id"] == "fact:causal-contradiction"
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][1]["contradiction_pairs"][0]["right_fact"]["fact_id"] == "fact:causal-support"
    assert any(
        item.get("question_lane") == "contradiction_resolution"
        for item in review_payload["question_recommendations"]["retaliation"]
    )

    testimony_payload = await testimony_route.endpoint(
        ClaimSupportTestimonySaveRequest(
            claim_type="retaliation",
            claim_element_id="retaliation:2",
            claim_element="Causal connection",
            raw_narrative="I complained on Monday and my schedule was cut on Wednesday.",
            firsthand_status="firsthand",
            source_confidence=0.88,
        )
    )
    assert testimony_payload["recorded"] is True
    assert testimony_payload["post_save_review"]["testimony_summary"]["retaliation"]["record_count"] == 1
    assert testimony_payload["post_save_review"]["testimony_summary"]["retaliation"]["linked_element_count"] == 1
    assert testimony_payload["post_save_review"]["testimony_records"]["retaliation"][0]["claim_element_id"] == "retaliation:2"
    assert testimony_payload["post_save_review"]["testimony_records"]["retaliation"][0]["claim_element_text"] == "Causal connection"
    assert testimony_payload["post_save_review"]["claim_coverage_matrix"]["retaliation"]["elements"][1]["contradiction_pair_count"] == 1
    assert any(
        item.get("question_lane") == "contradiction_resolution"
        and item.get("target_claim_element_id") == "retaliation:2"
        for item in testimony_payload["post_save_review"]["question_recommendations"]["retaliation"]
    )

    document_payload = await document_route.endpoint(
        ClaimSupportDocumentSaveRequest(
            claim_type="retaliation",
            claim_element_id="retaliation:2",
            claim_element="Causal connection",
            document_label="Schedule reduction memo",
            source_url="https://example.com/schedule-memo",
            document_text="Schedule reduction followed the complaint.",
        )
    )
    assert document_payload["recorded"] is True
    assert document_payload["post_save_review"]["document_summary"]["retaliation"]["record_count"] == 1
    assert review_payload["follow_up_plan_summary"]["retaliation"]["primary_authority_program_bias_counts"] == {
        "uncertain": 1,
    }
    assert review_payload["follow_up_plan_summary"]["retaliation"]["primary_authority_program_rule_bias_counts"] == {
        "procedural_prerequisite": 1,
    }
    assert review_payload["follow_up_plan_summary"]["retaliation"]["support_by_kind"] == {
        "authority": 1,
    }
    assert review_payload["follow_up_plan_summary"]["retaliation"]["source_family_counts"] == {
        "legal_authority": 1,
    }
    assert review_payload["follow_up_plan_summary"]["retaliation"]["artifact_family_counts"] == {
        "legal_authority_reference": 1,
    }
    assert review_payload["follow_up_plan_summary"]["retaliation"]["resolution_applied_counts"] == {
        "manual_review_resolved": 1,
    }
    assert review_payload["follow_up_plan_summary"]["retaliation"]["temporal_rule_status_counts"] == {
        "partial": 1,
    }
    assert review_payload["follow_up_plan_summary"]["retaliation"]["temporal_rule_blocking_reason_counts"] == {
        "Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.": 1,
    }
    assert review_payload["follow_up_plan_summary"]["retaliation"]["temporal_resolution_status_counts"] == {
        "awaiting_testimony": 1,
    }
    assert review_payload["follow_up_history_summary"]["retaliation"]["manual_review_entry_count"] == 1
    assert review_payload["follow_up_history_summary"]["retaliation"]["temporal_gap_task_count"] == 1
    assert review_payload["follow_up_history_summary"]["retaliation"]["temporal_gap_targeted_task_count"] == 1
    assert review_payload["follow_up_history_summary"]["retaliation"]["selected_authority_program_type_counts"] == {
        "element_definition_search": 1,
    }
    assert review_payload["follow_up_history_summary"]["retaliation"]["selected_authority_program_bias_counts"] == {
        "uncertain": 1,
    }
    assert review_payload["follow_up_history_summary"]["retaliation"]["selected_authority_program_rule_bias_counts"] == {
        "procedural_prerequisite": 1,
    }
    assert review_payload["follow_up_history_summary"]["retaliation"]["source_family_counts"] == {
        "legal_authority": 1,
    }
    assert review_payload["follow_up_history_summary"]["retaliation"]["artifact_family_counts"] == {
        "legal_authority_reference": 1,
    }
    assert review_payload["follow_up_history"]["retaliation"][1]["source_family"] == "legal_authority"
    assert any(
        entry.get("resolution_applied") == "manual_review_resolved"
        for entry in review_payload["follow_up_history"]["retaliation"]
    )
    assert review_payload["follow_up_history_summary"]["retaliation"]["resolution_applied_counts"] == {
        "skipped_resolution_handoff": 1,
        "manual_review_resolved": 1,
    }
    assert review_payload["follow_up_history_summary"]["retaliation"]["temporal_rule_status_counts"] == {
        "partial": 1,
    }
    assert review_payload["follow_up_history_summary"]["retaliation"]["temporal_rule_blocking_reason_counts"] == {
        "Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.": 1,
    }
    assert review_payload["follow_up_history_summary"]["retaliation"]["temporal_resolution_status_counts"] == {
        "awaiting_testimony": 1,
    }
    assert any(
        entry.get("temporal_rule_profile_id") == "retaliation_temporal_profile_v1"
        and entry.get("temporal_rule_status") == "partial"
        for entry in review_payload["follow_up_history"]["retaliation"]
    )

    resolution_payload = await resolve_route.endpoint(
        ClaimSupportManualReviewResolveRequest(
            claim_type="retaliation",
            claim_element_id="retaliation:2",
            claim_element="Adverse action",
            resolution_status="resolved_supported",
            resolution_notes="Operator reconciled the contradiction from the dashboard.",
            related_execution_id=21,
        ),
    )
    assert resolution_payload["resolution_result"]["status"] == "resolved_manual_review"
    assert resolution_payload["post_resolution_review"]["follow_up_history_summary"]["retaliation"]["resolution_applied_counts"] == {
        "skipped_resolution_handoff": 1,
        "manual_review_resolved": 1,
    }

    execute_payload = await execute_route.endpoint(
        ClaimSupportFollowUpExecuteRequest(
            claim_type="retaliation",
            required_support_kinds=["evidence", "authority"],
            follow_up_support_kind="authority",
            follow_up_max_tasks_per_claim=1,
            follow_up_force=False,
            include_post_execution_review=True,
            include_support_summary=True,
            include_overview=True,
            include_follow_up_plan=True,
        ),
    )
    assert execute_payload["follow_up_execution"]["retaliation"]["task_count"] == 1
    assert execute_payload["follow_up_execution_summary"]["retaliation"]["support_by_kind"] == {
        "authority": 1,
    }
    assert execute_payload["follow_up_execution_summary"]["retaliation"]["source_family_counts"] == {
        "legal_authority": 1,
    }
    assert execute_payload["follow_up_execution_summary"]["retaliation"]["artifact_family_counts"] == {
        "legal_authority_reference": 1,
    }
    assert execute_payload["execution_quality_summary"]["retaliation"]["quality_improvement_status"] == "unchanged"
    assert execute_payload["execution_quality_summary"]["retaliation"]["parse_quality_task_count"] == 1
    assert execute_payload["execution_quality_summary"]["retaliation"]["recommended_next_action"] == ""
    assert execute_payload["post_execution_review"]["claim_coverage_summary"]["retaliation"][
        "missing_elements"
    ] == ["Causal connection"]
