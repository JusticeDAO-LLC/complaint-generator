from types import SimpleNamespace
from unittest.mock import Mock, patch

from datetime import datetime, timezone

from fastapi import Response
from claim_support_review import (
    ClaimSupportFollowUpExecuteRequest,
    ClaimSupportManualReviewResolveRequest,
    ClaimSupportReviewRequest,
    _summarize_follow_up_execution_claim,
    _summarize_follow_up_plan_claim,
    build_claim_support_follow_up_execution_payload,
    build_claim_support_manual_review_resolution_payload,
    build_claim_support_review_payload,
)
from applications.review_api import (
    REVIEW_EXECUTION_SUNSET,
    create_review_api_app,
)


def test_claim_support_review_payload_returns_matrix_and_summary():
    with patch(
        "claim_support_review._utcnow",
        return_value=datetime(2026, 3, 12, 12, 0, 0, tzinfo=timezone.utc),
    ):
        mediator = Mock()
        mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
        mediator.get_claim_coverage_matrix.return_value = {
            "claims": {
                "retaliation": {
                    "claim_type": "retaliation",
                    "total_elements": 3,
                    "total_links": 2,
                    "total_facts": 4,
                    "support_by_kind": {"evidence": 1, "authority": 1},
                    "authority_treatment_summary": {
                        "authority_link_count": 2,
                        "supportive_authority_link_count": 1,
                        "adverse_authority_link_count": 1,
                        "uncertain_authority_link_count": 0,
                        "treatment_type_counts": {
                            "questioned": 1,
                            "adverse": 1,
                        },
                    },
                    "authority_rule_candidate_summary": {
                        "authority_link_count": 2,
                        "authority_links_with_rule_candidates": 2,
                        "total_rule_candidate_count": 3,
                        "matched_claim_element_rule_count": 2,
                        "rule_type_counts": {
                            "element": 2,
                            "exception": 1,
                        },
                        "max_extraction_confidence": 0.78,
                    },
                    "support_trace_summary": {
                        "trace_count": 3,
                        "fact_trace_count": 3,
                        "link_only_trace_count": 0,
                        "unique_fact_count": 3,
                        "unique_graph_id_count": 2,
                        "unique_record_count": 2,
                        "parsed_record_count": 2,
                        "support_by_kind": {"evidence": 2, "authority": 1},
                        "support_by_source": {"evidence": 2, "legal_authorities": 1},
                        "parse_source_counts": {"bytes": 2, "legal_authority": 1},
                        "parse_input_format_counts": {"email": 1, "html": 1},
                        "parse_quality_tier_counts": {"high": 2},
                        "avg_parse_quality_score": 95.5,
                        "graph_status_counts": {"available": 3},
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
                        "partially_supported": 1,
                        "missing": 1,
                    },
                    "elements": [
                        {
                            "element_id": "retaliation:1",
                            "element_text": "Protected activity",
                            "links": [
                                {
                                    "support_kind": "evidence",
                                    "graph_trace": {
                                        "source_table": "evidence",
                                        "summary": {"status": "available"},
                                        "snapshot": {
                                            "graph_id": "graph:evidence-1",
                                            "created": True,
                                            "reused": False,
                                        },
                                    },
                                },
                                {
                                    "support_kind": "authority",
                                    "graph_trace": {
                                        "source_table": "legal_authorities",
                                        "summary": {"status": "available"},
                                        "snapshot": {
                                            "graph_id": "graph:authority-1",
                                            "created": False,
                                            "reused": True,
                                        },
                                    },
                                },
                            ],
                        }
                    ],
                }
            }
        }
        mediator.get_claim_overview.return_value = {
            "claims": {
                "retaliation": {
                    "missing": [{"element_text": "Causal connection"}],
                    "partially_supported": [{"element_text": "Adverse action"}],
                }
            }
        }
        mediator.get_claim_support_gaps.return_value = {
            "claims": {
                "retaliation": {
                    "unresolved_count": 2,
                    "unresolved_elements": [
                        {
                            "element_text": "Causal connection",
                            "recommended_action": "collect_initial_support",
                        },
                        {
                            "element_text": "Adverse action",
                            "recommended_action": "collect_missing_support_kind",
                        },
                    ],
                }
            }
        }
        mediator.get_claim_contradiction_candidates.return_value = {
            "claims": {
                "retaliation": {
                    "candidate_count": 1,
                    "candidates": [{"claim_element_text": "Adverse action"}],
                }
            }
        }
        mediator.get_claim_support_validation.return_value = {
            "claims": {
                "retaliation": {
                    "claim_type": "retaliation",
                    "validation_status": "contradicted",
                    "validation_status_counts": {
                        "supported": 0,
                        "incomplete": 1,
                        "missing": 1,
                        "contradicted": 1,
                    },
                    "proof_gap_count": 3,
                    "elements_requiring_follow_up": [
                        "Adverse action",
                        "Causal connection",
                    ],
                    "proof_diagnostics": {
                        "reasoning": {
                            "adapter_status_counts": {
                                "logic_proof": {"not_implemented": 1},
                                "logic_contradictions": {"not_implemented": 1},
                                "ontology_build": {"implemented": 1},
                                "ontology_validation": {"implemented": 1},
                            },
                            "backend_available_count": 4,
                            "predicate_count": 6,
                            "ontology_entity_count": 5,
                            "ontology_relationship_count": 4,
                            "fallback_ontology_count": 1,
                        },
                        "decision": {
                            "decision_source_counts": {
                                "heuristic_contradictions": 1,
                                "partial_support": 1,
                                "missing_support": 1,
                            },
                            "adapter_contradicted_element_count": 0,
                            "fallback_ontology_element_count": 1,
                            "proof_supported_element_count": 0,
                            "logic_unprovable_element_count": 0,
                            "ontology_invalid_element_count": 0,
                        },
                    },
                    "elements": [
                        {
                            "element_id": "retaliation:2",
                            "element_text": "Adverse action",
                            "validation_status": "contradicted",
                            "reasoning_diagnostics": {
                                "predicate_count": 4,
                                "used_fallback_ontology": True,
                                "backend_available_count": 3,
                                "adapter_statuses": {
                                    "logic_proof": {
                                        "backend_available": True,
                                        "implementation_status": "not_implemented",
                                    },
                                    "logic_contradictions": {
                                        "backend_available": False,
                                        "implementation_status": "unavailable",
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
                            },
                        }
                    ],
                }
            }
        }
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
                        "timestamp": "2026-03-12T10:15:00",
                        "execution_mode": "manual_review",
                        "validation_status": "contradicted",
                        "follow_up_focus": "contradiction_resolution",
                        "query_strategy": "standard_gap_targeted",
                    },
                    {
                        "execution_id": 20,
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:3",
                        "claim_element_text": "Causal connection",
                        "support_kind": "authority",
                        "query_text": "\"retaliation\" \"Causal connection\" case law",
                        "status": "executed",
                        "timestamp": "2026-03-12T09:45:00",
                        "execution_mode": "retrieve_support",
                        "validation_status": "incomplete",
                        "follow_up_focus": "support_gap_closure",
                        "query_strategy": "standard_gap_targeted",
                        "adaptive_retry_applied": True,
                        "adaptive_retry_reason": "repeated_zero_result_reasoning_gap",
                        "adaptive_query_strategy": "standard_gap_targeted",
                        "adaptive_priority_penalty": 1,
                        "zero_result": True,
                        "resolution_applied": "manual_review_resolved",
                        "selected_search_program_type": "adverse_authority_search",
                        "selected_search_program_bias": "adverse",
                        "selected_search_program_rule_bias": "exception",
                    },
                ]
            }
        }
        mediator.summarize_claim_support.return_value = {
            "claims": {
                "retaliation": {
                    "support_by_kind": {"evidence": 1, "authority": 1},
                    "total_links": 2,
                }
            }
        }
        mediator.get_claim_follow_up_plan.return_value = {
            "claims": {
                "retaliation": {
                    "task_count": 2,
                    "blocked_task_count": 1,
                    "tasks": [
                        {
                            "claim_element": "Causal connection",
                            "recommended_action": "retrieve_more_support",
                            "authority_search_program_summary": {
                                "program_count": 2,
                                "program_type_counts": {
                                    "fact_pattern_search": 1,
                                    "treatment_check_search": 1,
                                },
                                "authority_intent_counts": {
                                    "support": 1,
                                    "confirm_good_law": 1,
                                },
                                "primary_program_id": "legal_search_program:plan-1",
                                "primary_program_type": "fact_pattern_search",
                                "primary_program_bias": "uncertain",
                                "primary_program_rule_bias": "",
                            },
                            "has_graph_support": True,
                            "should_suppress_retrieval": False,
                            "resolution_applied": "manual_review_resolved",
                            "adaptive_retry_state": {
                                "applied": True,
                                "priority_penalty": 1,
                                "adaptive_query_strategy": "standard_gap_targeted",
                                "reason": "repeated_zero_result_reasoning_gap",
                                "latest_attempted_at": "2026-03-12T09:45:00",
                            },
                            "graph_support": {
                                "summary": {
                                    "semantic_cluster_count": 2,
                                    "semantic_duplicate_count": 3,
                                }
                            },
                        },
                        {
                            "claim_element": "Adverse action",
                            "recommended_action": "target_missing_support_kind",
                            "has_graph_support": False,
                            "should_suppress_retrieval": True,
                            "graph_support": {"summary": {}},
                        },
                    ],
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
                            "resolution_applied": "manual_review_resolved",
                            "authority_search_program_summary": {
                                "program_count": 2,
                                "program_type_counts": {
                                    "fact_pattern_search": 1,
                                    "treatment_check_search": 1,
                                },
                                "authority_intent_counts": {
                                    "support": 1,
                                    "confirm_good_law": 1,
                                },
                                "primary_program_id": "legal_search_program:exec-1",
                                "primary_program_type": "fact_pattern_search",
                                "primary_program_bias": "uncertain",
                                "primary_program_rule_bias": "",
                            },
                            "adaptive_retry_state": {
                                "applied": True,
                                "priority_penalty": 1,
                                "adaptive_query_strategy": "standard_gap_targeted",
                                "reason": "repeated_zero_result_reasoning_gap",
                                "latest_attempted_at": "2026-03-12T09:45:00",
                            },
                            "graph_support": {
                                "summary": {
                                    "semantic_cluster_count": 1,
                                    "semantic_duplicate_count": 2,
                                }
                            },
                        }
                    ],
                    "skipped_tasks": [
                        {
                            "claim_element": "Adverse action",
                            "graph_support": {
                                "summary": {
                                    "semantic_cluster_count": 2,
                                    "semantic_duplicate_count": 1,
                                }
                            },
                            "skipped": {
                                "suppressed": {"reason": "existing_support_high_duplication"}
                            },
                        },
                        {
                            "claim_element": "Protected activity",
                            "graph_support": {
                                "summary": {
                                    "semantic_cluster_count": 0,
                                    "semantic_duplicate_count": 1,
                                }
                            },
                            "skipped": {
                                "authority": {"reason": "duplicate_within_cooldown"}
                            },
                        },
                    ],
                }
            }
        }

        payload = build_claim_support_review_payload(
            mediator,
            ClaimSupportReviewRequest(
                claim_type="retaliation",
                execute_follow_up=True,
                follow_up_support_kind="authority",
                follow_up_max_tasks_per_claim=2,
            ),
        )

        assert payload["user_id"] == "state-user"
        assert (
            payload["claim_coverage_matrix"]["retaliation"]["status_counts"]["covered"]
            == 1
        )
        assert payload["claim_coverage_summary"]["retaliation"]["missing_elements"] == [
            "Causal connection"
        ]
        assert payload["claim_coverage_summary"]["retaliation"][
            "partially_supported_elements"
        ] == ["Adverse action"]
        assert payload["claim_coverage_summary"]["retaliation"]["unresolved_element_count"] == 2
        assert payload["claim_coverage_summary"]["retaliation"]["unresolved_elements"] == [
            "Causal connection",
            "Adverse action",
        ]
        assert payload["claim_coverage_summary"]["retaliation"]["recommended_gap_actions"] == {
            "collect_initial_support": 1,
            "collect_missing_support_kind": 1,
        }
        assert payload["claim_coverage_summary"]["retaliation"]["contradiction_candidate_count"] == 1
        assert payload["claim_coverage_summary"]["retaliation"]["contradicted_elements"] == [
            "Adverse action"
        ]
        assert payload["claim_coverage_summary"]["retaliation"]["validation_status"] == "contradicted"
        assert payload["claim_coverage_summary"]["retaliation"]["proof_gap_count"] == 3
        assert payload["claim_coverage_summary"]["retaliation"]["reasoning_backend_available_count"] == 4
        assert payload["claim_coverage_summary"]["retaliation"]["reasoning_adapter_status_counts"]["ontology_build"] == {
            "implemented": 1
        }
        assert payload["claim_coverage_summary"]["retaliation"]["reasoning_predicate_count"] == 6
        assert payload["claim_coverage_summary"]["retaliation"]["reasoning_ontology_entity_count"] == 5
        assert payload["claim_coverage_summary"]["retaliation"]["reasoning_ontology_relationship_count"] == 4
        assert payload["claim_coverage_summary"]["retaliation"]["reasoning_fallback_ontology_count"] == 1
        assert payload["claim_coverage_summary"]["retaliation"]["decision_source_counts"] == {
            "heuristic_contradictions": 1,
            "partial_support": 1,
            "missing_support": 1,
        }
        assert payload["claim_coverage_summary"]["retaliation"]["adapter_contradicted_element_count"] == 0
        assert payload["claim_coverage_summary"]["retaliation"]["decision_fallback_ontology_element_count"] == 1
        assert payload["claim_coverage_summary"]["retaliation"]["proof_supported_element_count"] == 0
        assert payload["claim_coverage_summary"]["retaliation"]["logic_unprovable_element_count"] == 0
        assert payload["claim_coverage_summary"]["retaliation"]["ontology_invalid_element_count"] == 0
        assert payload["claim_coverage_summary"]["retaliation"]["low_quality_parsed_record_count"] == 0
        assert payload["claim_coverage_summary"]["retaliation"]["parse_quality_issue_element_count"] == 0
        assert payload["claim_coverage_summary"]["retaliation"]["parse_quality_recommendation"] == ""
        assert payload["claim_coverage_summary"]["retaliation"]["authority_treatment_summary"] == {
            "authority_link_count": 2,
            "supportive_authority_link_count": 1,
            "adverse_authority_link_count": 1,
            "uncertain_authority_link_count": 0,
            "treatment_type_counts": {
                "questioned": 1,
                "adverse": 1,
            },
        }
        assert payload["claim_coverage_summary"]["retaliation"]["authority_rule_candidate_summary"] == {
            "authority_link_count": 2,
            "authority_links_with_rule_candidates": 2,
            "total_rule_candidate_count": 3,
            "matched_claim_element_rule_count": 2,
            "rule_type_counts": {
                "element": 2,
                "exception": 1,
            },
            "max_extraction_confidence": 0.78,
        }
        assert payload["claim_support_validation"]["retaliation"]["validation_status"] == "contradicted"
        assert payload["claim_support_snapshot_summary"]["retaliation"] == {
            "total_snapshot_count": 0,
            "fresh_snapshot_count": 0,
            "stale_snapshot_count": 0,
            "snapshot_kinds": [],
            "fresh_snapshot_kinds": [],
            "stale_snapshot_kinds": [],
            "retention_limits": [],
            "total_pruned_snapshot_count": 0,
        }
        assert payload["follow_up_history"]["retaliation"][0]["support_kind"] == "manual_review"
        assert payload["follow_up_history_summary"]["retaliation"] == {
            "total_entry_count": 2,
            "status_counts": {
                "skipped_manual_review": 1,
                "executed": 1,
            },
            "support_kind_counts": {
                "manual_review": 1,
                "authority": 1,
            },
            "execution_mode_counts": {
                "manual_review": 1,
                "retrieve_support": 1,
            },
            "query_strategy_counts": {
                "standard_gap_targeted": 2,
            },
            "follow_up_focus_counts": {
                "contradiction_resolution": 1,
                "support_gap_closure": 1,
            },
            "resolution_status_counts": {},
            "resolution_applied_counts": {
                "manual_review_resolved": 1,
            },
            "adaptive_retry_entry_count": 1,
            "priority_penalized_entry_count": 1,
            "adaptive_query_strategy_counts": {
                "standard_gap_targeted": 1,
            },
            "adaptive_retry_reason_counts": {
                "repeated_zero_result_reasoning_gap": 1,
            },
            "selected_authority_program_type_counts": {
                "adverse_authority_search": 1,
            },
            "selected_authority_program_bias_counts": {
                "adverse": 1,
            },
            "selected_authority_program_rule_bias_counts": {
                "exception": 1,
            },
            "last_adaptive_retry": {
                "claim_element_id": "retaliation:3",
                "claim_element_text": "Causal connection",
                "timestamp": "2026-03-12T09:45:00",
                "adaptive_query_strategy": "standard_gap_targeted",
                "reason": "repeated_zero_result_reasoning_gap",
                "recency_bucket": "fresh",
                "is_stale": False,
            },
            "zero_result_entry_count": 1,
            "manual_review_entry_count": 1,
            "resolved_entry_count": 0,
            "contradiction_related_entry_count": 1,
            "latest_attempted_at": "2026-03-12T10:15:00",
        }
        assert payload["claim_reasoning_review"]["retaliation"] == {
            "claim_type": "retaliation",
            "total_element_count": 1,
            "flagged_element_count": 1,
            "fallback_ontology_element_count": 1,
            "unavailable_backend_element_count": 1,
            "degraded_adapter_element_count": 1,
            "flagged_elements": [
                {
                    "element_id": "retaliation:2",
                    "element_text": "Adverse action",
                    "validation_status": "contradicted",
                    "predicate_count": 4,
                    "used_fallback_ontology": True,
                    "backend_available_count": 3,
                    "unavailable_adapters": ["logic_contradictions"],
                    "degraded_adapters": ["logic_contradictions", "logic_proof"],
                }
            ],
        }
        assert payload["claim_coverage_summary"]["retaliation"]["support_trace_summary"]["trace_count"] == 3
        assert payload["claim_coverage_summary"]["retaliation"]["support_trace_summary"]["parse_input_format_counts"] == {
            "email": 1,
            "html": 1,
        }
        assert payload["claim_coverage_summary"]["retaliation"]["support_trace_summary"]["avg_parse_quality_score"] == 95.5
        assert payload["claim_coverage_summary"]["retaliation"]["authority_treatment_summary"] == {
            "authority_link_count": 2,
            "supportive_authority_link_count": 1,
            "adverse_authority_link_count": 1,
            "uncertain_authority_link_count": 0,
            "treatment_type_counts": {
                "questioned": 1,
                "adverse": 1,
            },
        }
        assert payload["claim_coverage_summary"]["retaliation"]["authority_rule_candidate_summary"]["rule_type_counts"] == {
            "element": 2,
            "exception": 1,
        }
        assert payload["claim_coverage_summary"]["retaliation"]["support_packet_summary"] == {
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
        assert payload["claim_coverage_summary"]["retaliation"]["graph_trace_summary"] == {
            "traced_link_count": 2,
            "snapshot_created_count": 1,
            "snapshot_reused_count": 1,
            "source_table_counts": {"evidence": 1, "legal_authorities": 1},
            "graph_status_counts": {"available": 2},
            "graph_id_count": 2,
        }
        assert payload["claim_support_gaps"]["retaliation"]["unresolved_count"] == 2
        assert payload["claim_contradiction_candidates"]["retaliation"]["candidate_count"] == 1
        assert payload["support_summary"]["retaliation"]["total_links"] == 2
        assert payload["claim_overview"]["retaliation"]["missing"][0]["element_text"] == "Causal connection"
        assert payload["follow_up_plan"]["retaliation"]["task_count"] == 2
        assert payload["follow_up_plan_summary"]["retaliation"]["blocked_task_count"] == 1
        assert payload["follow_up_plan_summary"]["retaliation"]["suppressed_task_count"] == 1
        assert payload["follow_up_plan_summary"]["retaliation"]["contradiction_task_count"] == 0
        assert payload["follow_up_plan_summary"]["retaliation"]["reasoning_gap_task_count"] == 0
        assert payload["follow_up_plan_summary"]["retaliation"]["fact_gap_task_count"] == 0
        assert payload["follow_up_plan_summary"]["retaliation"]["adverse_authority_task_count"] == 0
        assert payload["follow_up_plan_summary"]["retaliation"]["parse_quality_task_count"] == 0
        assert payload["follow_up_plan_summary"]["retaliation"]["quality_gap_targeted_task_count"] == 0
        assert payload["follow_up_plan_summary"]["retaliation"]["semantic_cluster_count"] == 2
        assert payload["follow_up_plan_summary"]["retaliation"]["follow_up_focus_counts"] == {
            "unknown": 2,
        }
        assert payload["follow_up_plan_summary"]["retaliation"]["query_strategy_counts"] == {
            "unknown": 2,
        }
        assert payload["follow_up_plan_summary"]["retaliation"]["proof_decision_source_counts"] == {
            "unknown": 2,
        }
        assert payload["follow_up_plan_summary"]["retaliation"]["resolution_applied_counts"] == {
            "manual_review_resolved": 1,
        }
        assert payload["follow_up_plan_summary"]["retaliation"]["adaptive_retry_task_count"] == 1
        assert payload["follow_up_plan_summary"]["retaliation"]["priority_penalized_task_count"] == 1
        assert payload["follow_up_plan_summary"]["retaliation"]["adaptive_query_strategy_counts"] == {
            "standard_gap_targeted": 1,
        }
        assert payload["follow_up_plan_summary"]["retaliation"]["adaptive_retry_reason_counts"] == {
            "repeated_zero_result_reasoning_gap": 1,
        }
        assert payload["follow_up_plan_summary"]["retaliation"]["authority_search_program_task_count"] == 1
        assert payload["follow_up_plan_summary"]["retaliation"]["authority_search_program_count"] == 2
        assert payload["follow_up_plan_summary"]["retaliation"]["authority_search_program_type_counts"] == {
            "fact_pattern_search": 1,
            "treatment_check_search": 1,
        }
        assert payload["follow_up_plan_summary"]["retaliation"]["authority_search_intent_counts"] == {
            "support": 1,
            "confirm_good_law": 1,
        }
        assert payload["follow_up_plan_summary"]["retaliation"]["primary_authority_program_type_counts"] == {
            "fact_pattern_search": 1,
        }
        assert payload["follow_up_plan_summary"]["retaliation"]["primary_authority_program_bias_counts"] == {
            "uncertain": 1,
        }
        assert payload["follow_up_plan_summary"]["retaliation"]["primary_authority_program_rule_bias_counts"] == {}
        assert payload["follow_up_plan_summary"]["retaliation"]["rule_candidate_backed_task_count"] == 0
        assert payload["follow_up_plan_summary"]["retaliation"]["total_rule_candidate_count"] == 0
        assert payload["follow_up_plan_summary"]["retaliation"]["matched_claim_element_rule_count"] == 0
        assert payload["follow_up_plan_summary"]["retaliation"]["rule_candidate_type_counts"] == {}
        assert payload["follow_up_plan_summary"]["retaliation"]["last_adaptive_retry"] == {
            "claim_element_id": None,
            "claim_element_text": "Causal connection",
            "timestamp": "2026-03-12T09:45:00",
            "adaptive_query_strategy": "standard_gap_targeted",
            "reason": "repeated_zero_result_reasoning_gap",
            "recency_bucket": "fresh",
            "is_stale": False,
        }
        assert payload["follow_up_plan_summary"]["retaliation"]["recommended_actions"] == {
            "retrieve_more_support": 1,
            "target_missing_support_kind": 1,
        }
        assert payload["follow_up_execution"]["retaliation"]["task_count"] == 1
        assert payload["follow_up_execution_summary"]["retaliation"]["executed_task_count"] == 1
        assert payload["follow_up_execution_summary"]["retaliation"]["skipped_task_count"] == 2
        assert payload["follow_up_execution_summary"]["retaliation"]["suppressed_task_count"] == 1
        assert payload["follow_up_execution_summary"]["retaliation"]["cooldown_skipped_task_count"] == 1
        assert payload["follow_up_execution_summary"]["retaliation"]["fact_gap_task_count"] == 0
        assert payload["follow_up_execution_summary"]["retaliation"]["adverse_authority_task_count"] == 0
        assert payload["follow_up_execution_summary"]["retaliation"]["semantic_cluster_count"] == 3
        assert payload["follow_up_execution_summary"]["retaliation"]["semantic_duplicate_count"] == 4
        assert payload["follow_up_execution_summary"]["retaliation"]["adaptive_retry_task_count"] == 1
        assert payload["follow_up_execution_summary"]["retaliation"]["priority_penalized_task_count"] == 1
        assert payload["follow_up_execution_summary"]["retaliation"]["adaptive_query_strategy_counts"] == {
            "standard_gap_targeted": 1,
        }
        assert payload["follow_up_execution_summary"]["retaliation"]["resolution_applied_counts"] == {
            "manual_review_resolved": 1,
        }
        assert payload["follow_up_execution_summary"]["retaliation"]["adaptive_retry_reason_counts"] == {
            "repeated_zero_result_reasoning_gap": 1,
        }
        assert payload["follow_up_execution_summary"]["retaliation"]["authority_search_program_task_count"] == 1
        assert payload["follow_up_execution_summary"]["retaliation"]["authority_search_program_count"] == 2
        assert payload["follow_up_execution_summary"]["retaliation"]["authority_search_program_type_counts"] == {
            "fact_pattern_search": 1,
            "treatment_check_search": 1,
        }
        assert payload["follow_up_execution_summary"]["retaliation"]["authority_search_intent_counts"] == {
            "support": 1,
            "confirm_good_law": 1,
        }
        assert payload["follow_up_execution_summary"]["retaliation"]["primary_authority_program_type_counts"] == {
            "fact_pattern_search": 1,
        }
        assert payload["follow_up_execution_summary"]["retaliation"]["primary_authority_program_bias_counts"] == {
            "uncertain": 1,
        }
        assert payload["follow_up_execution_summary"]["retaliation"]["primary_authority_program_rule_bias_counts"] == {}
        assert payload["follow_up_execution_summary"]["retaliation"]["rule_candidate_backed_task_count"] == 0
        assert payload["follow_up_execution_summary"]["retaliation"]["total_rule_candidate_count"] == 0
        assert payload["follow_up_execution_summary"]["retaliation"]["matched_claim_element_rule_count"] == 0
        assert payload["follow_up_execution_summary"]["retaliation"]["rule_candidate_type_counts"] == {}
        assert payload["follow_up_execution_summary"]["retaliation"]["last_adaptive_retry"] == {
            "claim_element_id": None,
            "claim_element_text": "Causal connection",
            "timestamp": "2026-03-12T09:45:00",
            "adaptive_query_strategy": "standard_gap_targeted",
            "reason": "repeated_zero_result_reasoning_gap",
            "recency_bucket": "fresh",
            "is_stale": False,
        }
        mediator.get_claim_coverage_matrix.assert_called_once_with(
            claim_type="retaliation",
            user_id="state-user",
            required_support_kinds=["evidence", "authority"],
        )
        mediator.get_claim_follow_up_plan.assert_called_once_with(
            claim_type="retaliation",
            user_id="state-user",
            required_support_kinds=["evidence", "authority"],
            cooldown_seconds=3600,
        )
        mediator.get_claim_support_gaps.assert_called_once_with(
            claim_type="retaliation",
            user_id="state-user",
            required_support_kinds=["evidence", "authority"],
        )
        mediator.get_claim_contradiction_candidates.assert_called_once_with(
            claim_type="retaliation",
            user_id="state-user",
        )
        mediator.get_claim_support_validation.assert_called_once_with(
            claim_type="retaliation",
            user_id="state-user",
            required_support_kinds=["evidence", "authority"],
        )
        mediator.get_recent_claim_follow_up_execution.assert_called_once_with(
            claim_type="retaliation",
            user_id="state-user",
            limit=10,
        )
        mediator.execute_claim_follow_up_plan.assert_called_once_with(
            claim_type="retaliation",
            user_id="state-user",
            support_kind="authority",
            max_tasks_per_claim=2,
            cooldown_seconds=3600,
        )


def test_claim_support_review_endpoint_allows_explicit_user_and_optional_sections():
    mediator = Mock()
    mediator.state = SimpleNamespace(username=None, hashed_username="hashed-user")
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {
            "civil rights": {
                "claim_type": "civil rights",
                "total_elements": 1,
                "total_links": 1,
                "total_facts": 1,
                "support_by_kind": {"authority": 1},
                "status_counts": {
                    "covered": 0,
                    "partially_supported": 1,
                    "missing": 0,
                },
                "elements": [],
            }
        }
    }
    mediator.get_claim_overview.return_value = {
        "claims": {
            "civil rights": {
                "missing": [],
                "partially_supported": [{"element_text": "Protected activity"}],
            }
        }
    }
    mediator.get_claim_support_gaps.return_value = {
        "claims": {
            "civil rights": {
                "unresolved_count": 1,
                "unresolved_elements": [
                    {
                        "element_text": "Protected activity",
                        "recommended_action": "collect_missing_support_kind",
                    }
                ],
            }
        }
    }
    mediator.get_claim_contradiction_candidates.return_value = {
        "claims": {
            "civil rights": {
                "candidate_count": 0,
                "candidates": [],
            }
        }
    }
    mediator.get_claim_support_validation.return_value = {
        "claims": {
            "civil rights": {
                "claim_type": "civil rights",
                "validation_status": "incomplete",
                "validation_status_counts": {
                    "supported": 0,
                    "incomplete": 1,
                    "missing": 0,
                    "contradicted": 0,
                },
                "proof_gap_count": 1,
                "elements_requiring_follow_up": ["Protected activity"],
                "elements": [],
            }
        }
    }
    mediator.get_claim_follow_up_plan.return_value = {"claims": {}}

    payload = build_claim_support_review_payload(
        mediator,
        ClaimSupportReviewRequest(
            user_id="api-user",
            claim_type="civil rights",
            required_support_kinds=["authority"],
            include_support_summary=False,
            include_overview=False,
            include_follow_up_plan=False,
        ),
    )

    assert payload["user_id"] == "api-user"
    assert payload["required_support_kinds"] == ["authority"]
    assert payload["claim_support_gaps"]["civil rights"]["unresolved_count"] == 1
    assert payload["claim_contradiction_candidates"]["civil rights"]["candidate_count"] == 0
    assert payload["claim_support_validation"]["civil rights"]["validation_status"] == "incomplete"
    assert "support_summary" not in payload
    assert "claim_overview" not in payload
    assert "follow_up_plan" not in payload
    assert "follow_up_plan_summary" not in payload
    assert "follow_up_execution" not in payload
    assert "follow_up_execution_summary" not in payload
    assert payload["claim_coverage_summary"]["civil rights"][
        "partially_supported_elements"
    ] == ["Protected activity"]
    mediator.summarize_claim_support.assert_not_called()
    mediator.get_claim_follow_up_plan.assert_not_called()
    mediator.execute_claim_follow_up_plan.assert_not_called()
    mediator.get_claim_overview.assert_called_once_with(
        claim_type="civil rights",
        user_id="api-user",
        required_support_kinds=["authority"],
    )


def test_claim_support_review_payload_reuses_persisted_diagnostic_snapshots():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "total_elements": 1,
                "total_links": 1,
                "total_facts": 1,
                "support_by_kind": {"evidence": 1},
                "status_counts": {
                    "covered": 0,
                    "partially_supported": 1,
                    "missing": 0,
                },
                "elements": [],
            }
        }
    }
    mediator.get_claim_overview.return_value = {
        "claims": {
            "retaliation": {
                "missing": [],
                "partially_supported": [{"element_text": "Protected activity"}],
            }
        }
    }
    mediator.get_claim_support_diagnostic_snapshots.return_value = {
        "claims": {
            "retaliation": {
                "gaps": {
                    "claim_type": "retaliation",
                    "unresolved_count": 1,
                    "unresolved_elements": [
                        {
                            "element_text": "Protected activity",
                            "recommended_action": "collect_missing_support_kind",
                        }
                    ],
                },
                "contradictions": {
                    "claim_type": "retaliation",
                    "candidate_count": 1,
                    "candidates": [
                        {"claim_element_text": "Protected activity"}
                    ],
                },
                "snapshots": {
                    "gaps": {"snapshot_id": 11},
                    "contradictions": {"snapshot_id": 12},
                },
            }
        }
    }
    mediator.get_claim_support_gaps.side_effect = AssertionError("should reuse persisted gap snapshot")
    mediator.get_claim_contradiction_candidates.side_effect = AssertionError(
        "should reuse persisted contradiction snapshot"
    )
    mediator.get_claim_follow_up_plan.return_value = {"claims": {}}
    mediator.summarize_claim_support.return_value = {"claims": {}}

    payload = build_claim_support_review_payload(
        mediator,
        ClaimSupportReviewRequest(claim_type="retaliation", include_follow_up_plan=False),
    )

    assert payload["claim_support_gaps"]["retaliation"]["unresolved_count"] == 1
    assert payload["claim_contradiction_candidates"]["retaliation"]["candidate_count"] == 1
    assert payload["claim_support_snapshots"]["retaliation"]["gaps"]["snapshot_id"] == 11
    assert payload["claim_support_snapshots"]["retaliation"]["contradictions"]["snapshot_id"] == 12
    assert payload["claim_support_snapshot_summary"]["retaliation"] == {
        "total_snapshot_count": 2,
        "fresh_snapshot_count": 2,
        "stale_snapshot_count": 0,
        "snapshot_kinds": ["contradictions", "gaps"],
        "fresh_snapshot_kinds": ["contradictions", "gaps"],
        "stale_snapshot_kinds": [],
        "retention_limits": [],
        "total_pruned_snapshot_count": 0,
    }
    assert payload["claim_reasoning_review"]["retaliation"] == {
        "claim_type": "",
        "total_element_count": 0,
        "flagged_element_count": 0,
        "fallback_ontology_element_count": 0,
        "unavailable_backend_element_count": 0,
        "degraded_adapter_element_count": 0,
        "flagged_elements": [],
    }
    mediator.get_claim_support_diagnostic_snapshots.assert_called_once_with(
        claim_type="retaliation",
        user_id="state-user",
        required_support_kinds=["evidence", "authority"],
    )
    mediator.get_claim_support_gaps.assert_not_called()
    mediator.get_claim_contradiction_candidates.assert_not_called()


def test_claim_support_review_payload_recomputes_stale_diagnostic_snapshots():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "total_elements": 1,
                "total_links": 1,
                "total_facts": 1,
                "support_by_kind": {"evidence": 1},
                "status_counts": {
                    "covered": 0,
                    "partially_supported": 1,
                    "missing": 0,
                },
                "elements": [],
            }
        }
    }
    mediator.get_claim_overview.return_value = {
        "claims": {
            "retaliation": {
                "missing": [],
                "partially_supported": [{"element_text": "Protected activity"}],
            }
        }
    }
    mediator.get_claim_support_diagnostic_snapshots.return_value = {
        "claims": {
            "retaliation": {
                "gaps": {"claim_type": "retaliation", "unresolved_count": 99},
                "contradictions": {"claim_type": "retaliation", "candidate_count": 99},
                "snapshots": {
                    "gaps": {"snapshot_id": 11, "is_stale": True},
                    "contradictions": {"snapshot_id": 12, "is_stale": True},
                },
            }
        }
    }
    mediator.get_claim_support_gaps.return_value = {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "unresolved_count": 1,
                "unresolved_elements": [
                    {
                        "element_text": "Protected activity",
                        "recommended_action": "collect_missing_support_kind",
                    }
                ],
            }
        }
    }
    mediator.get_claim_contradiction_candidates.return_value = {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "candidate_count": 0,
                "candidates": [],
            }
        }
    }
    mediator.get_claim_support_validation.return_value = {"claims": {"retaliation": {"validation_status": "incomplete"}}}
    mediator.get_claim_follow_up_plan.return_value = {"claims": {}}
    mediator.summarize_claim_support.return_value = {"claims": {}}

    payload = build_claim_support_review_payload(
        mediator,
        ClaimSupportReviewRequest(claim_type="retaliation", include_follow_up_plan=False),
    )

    assert payload["claim_support_gaps"]["retaliation"]["unresolved_count"] == 1
    assert payload["claim_contradiction_candidates"]["retaliation"]["candidate_count"] == 0
    assert payload["claim_support_snapshots"]["retaliation"]["gaps"]["is_stale"] is True
    assert payload["claim_support_snapshots"]["retaliation"]["contradictions"]["is_stale"] is True
    assert payload["claim_support_snapshot_summary"]["retaliation"] == {
        "total_snapshot_count": 2,
        "fresh_snapshot_count": 0,
        "stale_snapshot_count": 2,
        "snapshot_kinds": ["contradictions", "gaps"],
        "fresh_snapshot_kinds": [],
        "stale_snapshot_kinds": ["contradictions", "gaps"],
        "retention_limits": [],
        "total_pruned_snapshot_count": 0,
    }
    assert payload["claim_reasoning_review"]["retaliation"] == {
        "claim_type": "",
        "total_element_count": 0,
        "flagged_element_count": 0,
        "fallback_ontology_element_count": 0,
        "unavailable_backend_element_count": 0,
        "degraded_adapter_element_count": 0,
        "flagged_elements": [],
    }
    mediator.get_claim_support_gaps.assert_called_once_with(
        claim_type="retaliation",
        user_id="state-user",
        required_support_kinds=["evidence", "authority"],
    )
    mediator.get_claim_contradiction_candidates.assert_called_once_with(
        claim_type="retaliation",
        user_id="state-user",
    )


def test_claim_support_follow_up_execution_payload_returns_post_execution_review():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.execute_claim_follow_up_plan.return_value = {
        "claims": {
            "retaliation": {
                "task_count": 1,
                "tasks": [
                    {
                        "claim_element": "Causal connection",
                        "follow_up_focus": "parse_quality_improvement",
                        "query_strategy": "quality_gap_targeted",
                        "proof_decision_source": "logic_unprovable",
                        "graph_support": {
                            "summary": {
                                "semantic_cluster_count": 1,
                                "semantic_duplicate_count": 0,
                            }
                        },
                    }
                ],
                "skipped_tasks": [
                    {
                        "claim_element": "Protected activity",
                        "execution_mode": "manual_review",
                        "follow_up_focus": "contradiction_resolution",
                        "query_strategy": "contradiction_targeted",
                        "proof_decision_source": "contradiction_candidates",
                        "skipped": {
                            "manual_review": {
                                "reason": "contradiction_requires_resolution",
                            }
                        },
                    }
                ],
            }
        }
    }
    mediator.get_claim_coverage_matrix.side_effect = [
        {
            "claims": {
                "retaliation": {
                    "claim_type": "retaliation",
                    "total_elements": 3,
                    "total_links": 3,
                    "total_facts": 5,
                    "support_by_kind": {"evidence": 2, "authority": 1},
                    "support_trace_summary": {
                        "parsed_record_count": 2,
                        "parse_quality_tier_counts": {"empty": 1, "high": 1},
                        "avg_parse_quality_score": 47.5,
                    },
                    "status_counts": {
                        "covered": 2,
                        "partially_supported": 0,
                        "missing": 1,
                    },
                    "elements": [],
                }
            }
        },
        {
            "claims": {
                "retaliation": {
                    "claim_type": "retaliation",
                    "total_elements": 3,
                    "total_links": 3,
                    "total_facts": 5,
                    "support_by_kind": {"evidence": 2, "authority": 1},
                    "support_trace_summary": {
                        "parsed_record_count": 2,
                        "parse_quality_tier_counts": {"high": 2},
                        "avg_parse_quality_score": 96.0,
                    },
                    "status_counts": {
                        "covered": 2,
                        "partially_supported": 0,
                        "missing": 1,
                    },
                    "elements": [],
                }
            }
        },
    ]
    mediator.get_claim_overview.return_value = {
        "claims": {
            "retaliation": {
                "missing": [{"element_text": "Causal connection"}],
                "partially_supported": [],
            }
        }
    }
    mediator.get_claim_support_gaps.return_value = {
        "claims": {
            "retaliation": {
                "unresolved_count": 1,
                "unresolved_elements": [
                    {
                        "element_text": "Causal connection",
                        "recommended_action": "collect_initial_support",
                    }
                ],
            }
        }
    }
    mediator.get_claim_contradiction_candidates.return_value = {
        "claims": {
            "retaliation": {
                "candidate_count": 0,
                "candidates": [],
            }
        }
    }
    mediator.get_claim_support_validation.side_effect = [
        {
            "claims": {
                "retaliation": {
                    "claim_type": "retaliation",
                    "validation_status": "incomplete",
                    "validation_status_counts": {
                        "supported": 2,
                        "incomplete": 0,
                        "missing": 1,
                        "contradicted": 0,
                    },
                    "proof_gap_count": 1,
                    "elements_requiring_follow_up": ["Causal connection"],
                    "elements": [
                        {
                            "element_text": "Causal connection",
                            "recommended_action": "improve_parse_quality",
                            "proof_decision_trace": {"decision_source": "low_quality_parse"},
                        }
                    ],
                }
            }
        },
        {
            "claims": {
                "retaliation": {
                    "claim_type": "retaliation",
                    "validation_status": "incomplete",
                    "validation_status_counts": {
                        "supported": 2,
                        "incomplete": 0,
                        "missing": 1,
                        "contradicted": 0,
                    },
                    "proof_gap_count": 1,
                    "elements_requiring_follow_up": ["Causal connection"],
                    "elements": [],
                }
            }
        },
    ]
    mediator.get_claim_follow_up_plan.return_value = {
        "claims": {
            "retaliation": {
                "task_count": 1,
                "blocked_task_count": 0,
                "tasks": [],
            }
        }
    }
    mediator.summarize_claim_support.return_value = {
        "claims": {
            "retaliation": {
                "total_links": 3,
                "support_by_kind": {"evidence": 2, "authority": 1},
            }
        }
    }

    payload = build_claim_support_follow_up_execution_payload(
        mediator,
        ClaimSupportFollowUpExecuteRequest(
            claim_type="retaliation",
            follow_up_support_kind="evidence",
            follow_up_max_tasks_per_claim=1,
            follow_up_force=True,
        ),
    )

    assert payload["user_id"] == "state-user"
    assert payload["follow_up_support_kind"] == "evidence"
    assert payload["follow_up_force"] is True
    assert payload["follow_up_execution"]["retaliation"]["task_count"] == 1
    assert payload["follow_up_execution_summary"]["retaliation"] == {
        "executed_task_count": 1,
        "skipped_task_count": 1,
        "suppressed_task_count": 0,
        "manual_review_task_count": 1,
        "cooldown_skipped_task_count": 0,
        "contradiction_task_count": 1,
        "reasoning_gap_task_count": 0,
        "fact_gap_task_count": 0,
        "adverse_authority_task_count": 0,
        "parse_quality_task_count": 1,
        "quality_gap_targeted_task_count": 1,
        "semantic_cluster_count": 1,
        "semantic_duplicate_count": 0,
        "follow_up_focus_counts": {
            "parse_quality_improvement": 1,
            "contradiction_resolution": 1,
        },
        "query_strategy_counts": {
            "quality_gap_targeted": 1,
            "contradiction_targeted": 1,
        },
        "proof_decision_source_counts": {
            "logic_unprovable": 1,
            "contradiction_candidates": 1,
        },
        "resolution_applied_counts": {},
        "adaptive_retry_task_count": 0,
        "priority_penalized_task_count": 0,
        "adaptive_query_strategy_counts": {},
        "adaptive_retry_reason_counts": {},
        "last_adaptive_retry": None,
        "authority_search_program_task_count": 0,
        "authority_search_program_count": 0,
        "authority_search_program_type_counts": {},
        "authority_search_intent_counts": {},
        "primary_authority_program_type_counts": {},
        "primary_authority_program_bias_counts": {},
        "primary_authority_program_rule_bias_counts": {},
        "rule_candidate_backed_task_count": 0,
        "total_rule_candidate_count": 0,
        "matched_claim_element_rule_count": 0,
        "rule_candidate_type_counts": {},
    }
    assert payload["execution_quality_summary"]["retaliation"] == {
        "pre_low_quality_parsed_record_count": 1,
        "post_low_quality_parsed_record_count": 0,
        "low_quality_parsed_record_delta": -1,
        "pre_parse_quality_issue_element_count": 1,
        "post_parse_quality_issue_element_count": 0,
        "parse_quality_issue_element_delta": -1,
        "pre_parse_quality_issue_elements": ["Causal connection"],
        "post_parse_quality_issue_elements": [],
        "resolved_parse_quality_issue_elements": ["Causal connection"],
        "remaining_parse_quality_issue_elements": [],
        "newly_flagged_parse_quality_issue_elements": [],
        "parse_quality_task_count": 1,
        "quality_gap_targeted_task_count": 1,
        "quality_improvement_status": "improved",
        "recommended_next_action": "",
    }
    assert payload["post_execution_review"]["claim_coverage_summary"]["retaliation"]["status_counts"]["covered"] == 2
    assert payload["post_execution_review"]["claim_coverage_summary"]["retaliation"]["low_quality_parsed_record_count"] == 0
    assert payload["post_execution_review"]["claim_support_gaps"]["retaliation"]["unresolved_count"] == 1
    assert payload["post_execution_review"]["claim_contradiction_candidates"]["retaliation"]["candidate_count"] == 0
    assert payload["post_execution_review"]["claim_support_validation"]["retaliation"]["proof_gap_count"] == 1
    mediator.execute_claim_follow_up_plan.assert_called_once_with(
        claim_type="retaliation",
        user_id="state-user",
        support_kind="evidence",
        max_tasks_per_claim=1,
        cooldown_seconds=3600,
        force=True,
    )


def test_claim_support_follow_up_execution_payload_can_skip_post_review():
    mediator = Mock()
    mediator.state = SimpleNamespace(username=None, hashed_username="hashed-user")
    mediator.execute_claim_follow_up_plan.return_value = {"claims": {}}

    payload = build_claim_support_follow_up_execution_payload(
        mediator,
        ClaimSupportFollowUpExecuteRequest(
            user_id="api-user",
            claim_type="civil rights",
            include_post_execution_review=False,
        ),
    )

    assert payload["user_id"] == "api-user"
    assert "post_execution_review" not in payload
    assert "execution_quality_summary" not in payload
    mediator.get_claim_coverage_matrix.assert_not_called()
    mediator.get_claim_overview.assert_not_called()
    mediator.get_claim_follow_up_plan.assert_not_called()


def test_claim_support_manual_review_resolution_payload_returns_post_resolution_review():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.resolve_claim_follow_up_manual_review.return_value = {
        "recorded": True,
        "execution_id": 91,
        "claim_type": "retaliation",
        "claim_element_id": "retaliation:2",
        "claim_element_text": "Adverse action",
        "support_kind": "manual_review",
        "status": "resolved_manual_review",
        "query_text": "manual_review_resolution::retaliation::retaliation:2::resolved_supported",
        "metadata": {
            "resolution_status": "resolved_supported",
            "resolution_notes": "Operator confirmed the contradiction was reconciled.",
            "related_execution_id": 21,
        },
    }
    mediator.get_claim_coverage_matrix.return_value = {"claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}}
    mediator.get_claim_overview.return_value = {"claims": {"retaliation": {"missing": [], "partially_supported": []}}}
    mediator.get_claim_support_diagnostic_snapshots.return_value = {"claims": {}}
    mediator.get_claim_support_gaps.return_value = {"claims": {"retaliation": {"unresolved_count": 0, "unresolved_elements": []}}}
    mediator.get_claim_contradiction_candidates.return_value = {"claims": {"retaliation": {"candidate_count": 0, "candidates": []}}}
    mediator.get_claim_support_validation.return_value = {"claims": {"retaliation": {"validation_status": "supported", "proof_diagnostics": {"reasoning": {}, "decision": {}}}}}
    mediator.get_recent_claim_follow_up_execution.return_value = {
        "claims": {
            "retaliation": [
                {
                    "execution_id": 91,
                    "support_kind": "manual_review",
                    "status": "resolved_manual_review",
                    "timestamp": "2026-03-12T11:05:00",
                    "execution_mode": "manual_review_resolution",
                    "follow_up_focus": "contradiction_resolution",
                    "query_strategy": "manual_review_resolution",
                    "resolution_status": "resolved_supported",
                    "resolution_applied": "manual_review_resolved",
                    "selected_search_program_type": "adverse_authority_search",
                    "selected_search_program_bias": "adverse",
                    "selected_search_program_rule_bias": "exception",
                }
            ]
        }
    }
    mediator.get_claim_follow_up_plan.return_value = {"claims": {}}
    mediator.summarize_claim_support.return_value = {"claims": {"retaliation": {"total_links": 2}}}

    payload = build_claim_support_manual_review_resolution_payload(
        mediator,
        ClaimSupportManualReviewResolveRequest(
            claim_type="retaliation",
            claim_element_id="retaliation:2",
            claim_element="Adverse action",
            resolution_status="resolved_supported",
            resolution_notes="Operator confirmed the contradiction was reconciled.",
            related_execution_id=21,
            resolution_metadata={"reviewer": "case-analyst"},
        ),
    )

    assert payload["user_id"] == "state-user"
    assert payload["resolution_result"]["status"] == "resolved_manual_review"
    assert payload["post_resolution_review"]["follow_up_history_summary"]["retaliation"]["resolved_entry_count"] == 1
    assert payload["post_resolution_review"]["follow_up_history_summary"]["retaliation"]["resolution_status_counts"] == {
        "resolved_supported": 1,
    }
    assert payload["post_resolution_review"]["follow_up_history_summary"]["retaliation"]["resolution_applied_counts"] == {
        "manual_review_resolved": 1,
    }
    assert payload["post_resolution_review"]["follow_up_history_summary"]["retaliation"]["selected_authority_program_type_counts"] == {
        "adverse_authority_search": 1,
    }
    assert payload["post_resolution_review"]["follow_up_history_summary"]["retaliation"]["selected_authority_program_bias_counts"] == {
        "adverse": 1,
    }
    assert payload["post_resolution_review"]["follow_up_history_summary"]["retaliation"]["selected_authority_program_rule_bias_counts"] == {
        "exception": 1,
    }
    mediator.resolve_claim_follow_up_manual_review.assert_called_once_with(
        claim_type="retaliation",
        user_id="state-user",
        claim_element_id="retaliation:2",
        claim_element="Adverse action",
        resolution_status="resolved_supported",
        resolution_notes="Operator confirmed the contradiction was reconciled.",
        related_execution_id=21,
        metadata={"reviewer": "case-analyst"},
    )


def test_claim_support_manual_review_resolution_payload_can_skip_post_review():
    mediator = Mock()
    mediator.state = SimpleNamespace(username=None, hashed_username="hashed-user")
    mediator.resolve_claim_follow_up_manual_review.return_value = {"recorded": True, "status": "resolved_manual_review"}

    payload = build_claim_support_manual_review_resolution_payload(
        mediator,
        ClaimSupportManualReviewResolveRequest(
            user_id="api-user",
            claim_type="civil rights",
            include_post_resolution_review=False,
        ),
    )

    assert payload["user_id"] == "api-user"
    assert "post_resolution_review" not in payload
    mediator.get_claim_coverage_matrix.assert_not_called()
    mediator.get_claim_overview.assert_not_called()
    mediator.get_claim_follow_up_plan.assert_not_called()


def test_claim_support_review_payload_summarizes_manual_review_tasks():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.get_claim_coverage_matrix.return_value = {"claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}}
    mediator.get_claim_overview.return_value = {"claims": {"retaliation": {"missing": [], "partially_supported": []}}}
    mediator.get_claim_support_diagnostic_snapshots.return_value = {"claims": {}}
    mediator.get_claim_support_gaps.return_value = {"claims": {"retaliation": {"unresolved_count": 0, "unresolved_elements": []}}}
    mediator.get_claim_contradiction_candidates.return_value = {"claims": {"retaliation": {"candidate_count": 1, "candidates": []}}}
    mediator.get_claim_support_validation.return_value = {
        "claims": {
            "retaliation": {
                "validation_status": "contradicted",
                "proof_gap_count": 1,
                "proof_diagnostics": {"reasoning": {}},
            }
        }
    }
    mediator.get_claim_follow_up_plan.return_value = {
        "claims": {
            "retaliation": {
                "task_count": 1,
                "blocked_task_count": 0,
                "tasks": [
                    {
                        "claim_element": "Protected activity",
                        "recommended_action": "resolve_contradiction",
                        "execution_mode": "manual_review",
                        "has_graph_support": True,
                        "should_suppress_retrieval": False,
                        "graph_support": {"summary": {"semantic_cluster_count": 1, "semantic_duplicate_count": 0}},
                    }
                ],
            }
        }
    }
    mediator.execute_claim_follow_up_plan.return_value = {
        "claims": {
            "retaliation": {
                "task_count": 0,
                "tasks": [],
                "skipped_tasks": [
                    {
                        "claim_element": "Protected activity",
                        "execution_mode": "manual_review",
                        "graph_support": {"summary": {"semantic_cluster_count": 1, "semantic_duplicate_count": 0}},
                        "skipped": {"manual_review": {"reason": "contradiction_requires_resolution"}},
                    }
                ],
            }
        }
    }
    mediator.summarize_claim_support.return_value = {"claims": {"retaliation": {"total_links": 2}}}

    payload = build_claim_support_review_payload(
        mediator,
        ClaimSupportReviewRequest(claim_type="retaliation", execute_follow_up=True),
    )

    assert payload["follow_up_plan_summary"]["retaliation"]["manual_review_task_count"] == 1
    assert payload["follow_up_execution_summary"]["retaliation"]["manual_review_task_count"] == 1
    assert payload["follow_up_plan_summary"]["retaliation"]["recommended_actions"] == {"resolve_contradiction": 1}


def test_claim_support_review_endpoint_is_registered_on_app():
    mediator = Mock()

    app = create_review_api_app(mediator)

    assert any(
        route.path == "/api/claim-support/review" and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/claim-support/execute-follow-up"
        and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/claim-support/resolve-manual-review"
        and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/documents/formal-complaint"
        and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/documents/download"
        and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )


def test_follow_up_summaries_aggregate_fact_gap_and_adverse_authority_metrics():
    plan_summary = _summarize_follow_up_plan_claim(
        {
            "task_count": 2,
            "blocked_task_count": 0,
            "tasks": [
                {
                    "follow_up_focus": "fact_gap_closure",
                    "query_strategy": "rule_fact_targeted",
                    "recommended_action": "collect_fact_support",
                    "authority_search_program_summary": {
                        "program_count": 2,
                        "program_type_counts": {
                            "fact_pattern_search": 1,
                            "adverse_authority_search": 1,
                        },
                        "authority_intent_counts": {
                            "support": 1,
                            "oppose": 1,
                        },
                        "primary_program_id": "legal_search_program:1",
                        "primary_program_type": "adverse_authority_search",
                        "primary_program_bias": "",
                        "primary_program_rule_bias": "exception",
                    },
                    "proof_decision_source": "partial_support",
                    "has_graph_support": True,
                    "should_suppress_retrieval": False,
                    "graph_support": {"summary": {"semantic_cluster_count": 1, "semantic_duplicate_count": 0}},
                    "authority_rule_candidate_summary": {
                        "total_rule_candidate_count": 2,
                        "matched_claim_element_rule_count": 2,
                        "rule_type_counts": {"element": 1, "exception": 1},
                    },
                },
                {
                    "follow_up_focus": "adverse_authority_review",
                    "query_strategy": "adverse_authority_targeted",
                    "recommended_action": "review_adverse_authority",
                    "authority_search_program_summary": {
                        "program_count": 2,
                        "program_type_counts": {
                            "adverse_authority_search": 1,
                            "treatment_check_search": 1,
                        },
                        "authority_intent_counts": {
                            "oppose": 1,
                            "confirm_good_law": 1,
                        },
                        "primary_program_id": "legal_search_program:2",
                        "primary_program_type": "adverse_authority_search",
                        "primary_program_bias": "adverse",
                        "primary_program_rule_bias": "",
                    },
                    "proof_decision_source": "partial_support",
                    "has_graph_support": True,
                    "should_suppress_retrieval": False,
                    "graph_support": {"summary": {"semantic_cluster_count": 2, "semantic_duplicate_count": 1}},
                    "authority_rule_candidate_summary": {
                        "total_rule_candidate_count": 1,
                        "matched_claim_element_rule_count": 1,
                        "rule_type_counts": {"element": 1},
                    },
                },
            ],
        }
    )

    execution_summary = _summarize_follow_up_execution_claim(
        {
            "tasks": [
                {
                    "follow_up_focus": "fact_gap_closure",
                    "query_strategy": "rule_fact_targeted",
                    "authority_search_program_summary": {
                        "program_count": 2,
                        "program_type_counts": {
                            "fact_pattern_search": 1,
                            "adverse_authority_search": 1,
                        },
                        "authority_intent_counts": {
                            "support": 1,
                            "oppose": 1,
                        },
                        "primary_program_id": "legal_search_program:1",
                        "primary_program_type": "adverse_authority_search",
                        "primary_program_bias": "",
                        "primary_program_rule_bias": "exception",
                    },
                    "proof_decision_source": "partial_support",
                    "graph_support": {"summary": {"semantic_cluster_count": 1, "semantic_duplicate_count": 0}},
                    "authority_rule_candidate_summary": {
                        "total_rule_candidate_count": 2,
                        "matched_claim_element_rule_count": 2,
                        "rule_type_counts": {"element": 1, "exception": 1},
                    },
                }
            ],
            "skipped_tasks": [
                {
                    "follow_up_focus": "adverse_authority_review",
                    "query_strategy": "adverse_authority_targeted",
                    "authority_search_program_summary": {
                        "program_count": 2,
                        "program_type_counts": {
                            "adverse_authority_search": 1,
                            "treatment_check_search": 1,
                        },
                        "authority_intent_counts": {
                            "oppose": 1,
                            "confirm_good_law": 1,
                        },
                        "primary_program_id": "legal_search_program:2",
                        "primary_program_type": "adverse_authority_search",
                        "primary_program_bias": "adverse",
                        "primary_program_rule_bias": "",
                    },
                    "proof_decision_source": "partial_support",
                    "skipped": {"manual_review": {"reason": "adverse_authority_requires_review"}},
                    "graph_support": {"summary": {"semantic_cluster_count": 2, "semantic_duplicate_count": 1}},
                    "authority_rule_candidate_summary": {
                        "total_rule_candidate_count": 1,
                        "matched_claim_element_rule_count": 1,
                        "rule_type_counts": {"element": 1},
                    },
                }
            ],
        }
    )

    assert plan_summary["fact_gap_task_count"] == 1
    assert plan_summary["adverse_authority_task_count"] == 1
    assert plan_summary["rule_candidate_backed_task_count"] == 2
    assert plan_summary["total_rule_candidate_count"] == 3
    assert plan_summary["matched_claim_element_rule_count"] == 3
    assert plan_summary["rule_candidate_type_counts"] == {"element": 2, "exception": 1}
    assert plan_summary["primary_authority_program_bias_counts"] == {"adverse": 1}
    assert plan_summary["primary_authority_program_rule_bias_counts"] == {"exception": 1}
    assert plan_summary["follow_up_focus_counts"] == {
        "fact_gap_closure": 1,
        "adverse_authority_review": 1,
    }
    assert plan_summary["query_strategy_counts"] == {
        "rule_fact_targeted": 1,
        "adverse_authority_targeted": 1,
    }
    assert plan_summary["recommended_actions"] == {
        "collect_fact_support": 1,
        "review_adverse_authority": 1,
    }

    assert execution_summary["fact_gap_task_count"] == 1
    assert execution_summary["adverse_authority_task_count"] == 1
    assert execution_summary["manual_review_task_count"] == 1
    assert execution_summary["rule_candidate_backed_task_count"] == 2
    assert execution_summary["total_rule_candidate_count"] == 3
    assert execution_summary["matched_claim_element_rule_count"] == 3
    assert execution_summary["rule_candidate_type_counts"] == {"element": 2, "exception": 1}
    assert execution_summary["primary_authority_program_bias_counts"] == {"adverse": 1}
    assert execution_summary["primary_authority_program_rule_bias_counts"] == {"exception": 1}
    assert execution_summary["follow_up_focus_counts"] == {
        "fact_gap_closure": 1,
        "adverse_authority_review": 1,
    }
    assert execution_summary["query_strategy_counts"] == {
        "rule_fact_targeted": 1,
        "adverse_authority_targeted": 1,
    }


async def test_claim_support_review_route_marks_execute_follow_up_as_deprecated():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.get_claim_coverage_matrix.return_value = {"claims": {}}
    mediator.get_claim_overview.return_value = {"claims": {}}
    mediator.get_claim_support_gaps.return_value = {"claims": {}}
    mediator.get_claim_contradiction_candidates.return_value = {"claims": {}}
    mediator.get_claim_follow_up_plan.return_value = {"claims": {}}
    mediator.execute_claim_follow_up_plan.return_value = {"claims": {}}
    mediator.summarize_claim_support.return_value = {"claims": {}}

    app = create_review_api_app(mediator)
    review_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/claim-support/review"
    )
    response = Response()

    payload = await review_route.endpoint(
        ClaimSupportReviewRequest(claim_type="retaliation", execute_follow_up=True),
        response,
    )

    assert payload["compatibility_notice"]["deprecated"] is True
    assert (
        payload["compatibility_notice"]["replacement_route"]
        == "/api/claim-support/execute-follow-up"
    )
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Sunset"] == REVIEW_EXECUTION_SUNSET
    assert response.headers["Link"] == (
        '</api/claim-support/execute-follow-up>; rel="successor-version"'
    )
    assert "execute_follow_up on /api/claim-support/review is deprecated" in response.headers[
        "Warning"
    ]