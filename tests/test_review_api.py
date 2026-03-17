import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import duckdb
from datetime import datetime, timezone

from fastapi import Response
from fastapi.testclient import TestClient
from claim_support_review import (
    ClaimSupportDocumentSaveRequest,
    ClaimSupportFollowUpExecuteRequest,
    ClaimSupportIntakeSummaryConfirmRequest,
    ClaimSupportManualReviewResolveRequest,
    ClaimSupportReviewRequest,
    ClaimSupportTestimonySaveRequest,
    _summarize_follow_up_execution_claim,
    _summarize_follow_up_plan_claim,
    build_claim_support_document_payload,
    build_claim_support_follow_up_execution_payload,
    build_claim_support_intake_summary_confirmation_payload,
    build_claim_support_manual_review_resolution_payload,
    build_claim_support_review_payload,
    build_claim_support_testimony_payload,
)
from applications.review_api import (
    REVIEW_EXECUTION_SUNSET,
    create_review_api_app,
)


def _build_hook_backed_review_api_mediator(db_path: str):
    try:
        from mediator.claim_support_hooks import ClaimSupportHook
    except ImportError as exc:
        pytest.skip(f"ClaimSupportHook requires dependencies: {exc}")

    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.log = Mock()

    hook = ClaimSupportHook(mediator, db_path=db_path)
    hook.register_claim_requirements(
        "state-user",
        {"retaliation": ["Protected activity", "Adverse action"]},
    )

    mediator.save_claim_testimony_record.side_effect = lambda **kwargs: hook.save_testimony_record(**kwargs)
    mediator.get_claim_testimony_records.side_effect = lambda user_id, claim_type=None, limit=100: hook.get_claim_testimony_records(
        user_id,
        claim_type,
        limit=limit,
    )
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}
    }
    mediator.get_claim_overview.return_value = {"claims": {"retaliation": {}}}
    mediator.get_claim_support_diagnostic_snapshots.return_value = {"claims": {}}
    mediator.get_claim_support_gaps.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "unresolved_elements": []}}
    }
    mediator.get_claim_contradiction_candidates.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "candidates": []}}
    }
    mediator.get_claim_support_validation.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}
    }
    mediator.get_recent_claim_follow_up_execution.return_value = {"claims": {"retaliation": []}}
    mediator.get_claim_follow_up_plan.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "tasks": []}}
    }
    mediator.get_user_evidence.return_value = []
    mediator.summarize_claim_support.return_value = {"claims": {"retaliation": {}}}
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "iteration_count": 1,
        "intake_readiness": {
            "score": 1.0,
            "ready_to_advance": True,
            "remaining_gap_count": 0,
            "contradiction_count": 0,
            "criteria": {"complainant_summary_confirmed": True},
            "blockers": [],
            "contradictions": [],
            "candidate_claim_count": 1,
            "canonical_fact_count": 1,
            "proof_lead_count": 1,
        },
        "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.9}],
        "intake_sections": {},
        "canonical_fact_summary": {"count": 1, "facts": []},
        "canonical_fact_intent_summary": {},
        "proof_lead_summary": {"count": 1, "proof_leads": []},
        "proof_lead_intent_summary": {},
        "timeline_anchor_summary": {"count": 0, "anchors": []},
        "harm_profile": {},
        "remedy_profile": {},
        "complainant_summary_confirmation": {
            "status": "confirmed",
            "confirmed": True,
            "confirmed_at": "2026-03-17T10:00:00+00:00",
            "confirmation_note": "ready for evidence handoff",
            "confirmation_source": "dashboard",
            "summary_snapshot_index": 0,
            "current_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
            "confirmed_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
        },
        "question_candidate_summary": {},
        "claim_support_packet_summary": {},
        "intake_evidence_alignment_summary": {},
        "alignment_evidence_tasks": [],
        "alignment_task_updates": [],
        "alignment_task_update_history": [],
    }

    return mediator, hook


def test_claim_support_review_payload_returns_matrix_and_summary():
    with patch(
        "claim_support_review._utcnow",
        return_value=datetime(2026, 3, 12, 12, 0, 0, tzinfo=timezone.utc),
    ):
        mediator = Mock()
        mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
        mediator.get_three_phase_status.return_value = {
            "current_phase": "intake",
            "iteration_count": 2,
            "intake_readiness": {
                "score": 0.5,
                "ready_to_advance": False,
                "remaining_gap_count": 1,
                "contradiction_count": 1,
                "blockers": ["resolve_contradictions"],
                "criteria": {
                    "case_theory_coherent": True,
                    "minimum_proof_path_present": True,
                    "claim_disambiguation_resolved": False,
                },
                "candidate_claim_count": 2,
                "canonical_fact_count": 2,
                "proof_lead_count": 1,
            },
            "intake_contradictions": [
                {
                    "summary": "Complaint timing conflicts with employer timeline",
                    "left_text": "The complaint came first.",
                    "right_text": "The schedule cut came first.",
                    "question": "Which event happened first?",
                    "severity": "high",
                }
            ],
            "candidate_claims": [
                {
                    "claim_type": "retaliation",
                    "label": "Retaliation",
                    "confidence": 0.8,
                    "ambiguity_flags": ["timing_overlap"],
                },
                {
                    "claim_type": "wrongful_termination",
                    "label": "Wrongful Termination",
                    "confidence": 0.72,
                },
            ],
            "intake_sections": {
                "chronology": {"status": "complete", "missing_items": []},
                "proof_leads": {"status": "partial", "missing_items": ["documents"]},
            },
            "canonical_fact_summary": {
                "count": 2,
                "facts": [{"fact_id": "fact_001"}, {"fact_id": "fact_002"}],
            },
            "proof_lead_summary": {
                "count": 1,
                "proof_leads": [{"lead_id": "lead_001"}],
            },
            "timeline_anchor_summary": {
                "count": 1,
                "anchors": [{"anchor_id": "timeline_anchor_001"}],
            },
            "timeline_relation_summary": {
                "count": 1,
                "relations": [{"relation_id": "timeline_relation_001", "relation_type": "before"}],
            },
            "timeline_consistency_summary": {
                "event_count": 2,
                "anchor_count": 1,
                "ordered_fact_count": 2,
                "unsequenced_fact_count": 0,
                "approximate_fact_count": 0,
                "range_fact_count": 0,
                "relation_count": 1,
                "relation_type_counts": {"before": 1},
                "missing_temporal_fact_ids": [],
                "relative_only_fact_ids": [],
                "warnings": [],
                "partial_order_ready": True,
            },
            "harm_profile": {
                "count": 1,
                "categories": ["economic"],
            },
            "remedy_profile": {
                "count": 1,
                "categories": ["monetary"],
            },
            "claim_support_packet_summary": {
                "claim_count": 1,
                "element_count": 3,
                "status_counts": {
                    "supported": 1,
                    "partially_supported": 1,
                    "unsupported": 1,
                    "contradicted": 0,
                },
                "support_quality_counts": {
                    "draft_ready": 1,
                    "credible": 1,
                    "suggestive": 0,
                    "unsupported": 1,
                    "contradicted": 0,
                },
                "recommended_actions": ["collect_missing_support_kind"],
            },
            "alignment_task_updates": [
                {
                    "task_id": "retaliation:adverse_action:fill_evidence_gaps",
                    "claim_type": "retaliation",
                    "claim_element_id": "adverse_action",
                    "resolution_status": "partially_addressed",
                    "status": "active",
                }
            ],
            "alignment_task_update_history": [
                {
                    "task_id": "retaliation:adverse_action:fill_evidence_gaps",
                    "claim_type": "retaliation",
                    "claim_element_id": "adverse_action",
                    "resolution_status": "still_open",
                    "status": "active",
                    "evidence_sequence": 1,
                },
                {
                    "task_id": "retaliation:adverse_action:fill_evidence_gaps",
                    "claim_type": "retaliation",
                    "claim_element_id": "adverse_action",
                    "resolution_status": "partially_addressed",
                    "status": "active",
                    "evidence_sequence": 2,
                }
            ],
        }
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
                            "status": "covered",
                            "missing_support_kinds": [],
                            "total_links": 2,
                            "support_trace_summary": {},
                            "links": [],
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
                        },
                        {
                            "element_id": "retaliation:2",
                            "element_text": "Adverse action",
                            "status": "partially_supported",
                            "support_by_kind": {"authority": 1},
                            "authority_treatment_summary": {},
                            "authority_rule_candidate_summary": {},
                            "total_links": 1,
                            "fact_count": 1,
                            "missing_support_kinds": ["evidence"],
                            "links_by_kind": {},
                            "support_trace_summary": {},
                            "support_packet_summary": {},
                            "support_packets": [],
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
                    "candidates": [{"claim_element_text": "Adverse action", "fact_ids": ["fact:authority:adverse", "fact:evidence:adverse"], "overlap_terms": ["termination", "complaint"]}],
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
                            "contradiction_candidates": [],
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
                        },
                        {
                            "element_id": "retaliation:2",
                            "element_text": "Adverse action",
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
                            "contradiction_candidate_count": 1,
                            "contradiction_candidates": [
                                {
                                    "fact_ids": ["fact:authority:adverse", "fact:evidence:adverse"],
                                    "overlap_terms": ["termination", "complaint"],
                                }
                            ],
                            "reasoning_diagnostics": {
                                "predicate_count": 2,
                                "used_fallback_ontology": False,
                                "backend_available_count": 2,
                                "adapter_statuses": {},
                            },
                        }
                    ],
                }
            }
        }
        mediator.get_claim_support_facts.side_effect = lambda **kwargs: [
            {
                "fact_id": "fact:dashboard:1",
                "fact_text": "Employee reported discrimination to HR in writing.",
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
                "fact_id": "fact:authority:1",
                "fact_text": "Protected activity is covered by retaliation doctrine.",
                "support_kind": "authority",
                "source_table": "legal_authorities",
                "source_family": "legal_authority",
                "source_ref": "42 U.S.C. § 2000e-3",
                "artifact_family": "legal_authority_reference",
                "content_origin": "authority_reference_fallback",
                "quality_tier": "high",
                "record_id": 41,
            },
        ] if kwargs.get("claim_element_id") == "retaliation:1" else ([
            {
                "fact_id": "fact:evidence:adverse",
                "fact_text": "The adverse action happened after the complaint.",
                "support_kind": "evidence",
                "source_table": "evidence",
                "source_family": "evidence",
                "source_ref": "QmAdverseTimeline",
                "artifact_family": "document",
                "content_origin": "operator_document_intake",
                "quality_tier": "high",
                "record_id": 53,
            },
            {
                "fact_id": "fact:authority:adverse",
                "fact_text": "The record says the adverse action happened before any complaint.",
                "support_kind": "authority",
                "source_table": "legal_authorities",
                "source_family": "legal_authority",
                "source_ref": "Contrary Source",
                "artifact_family": "legal_authority_reference",
                "content_origin": "authority_reference_fallback",
                "quality_tier": "high",
                "record_id": 52,
            }
        ] if kwargs.get("claim_element_id") == "retaliation:2" else [])
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
                        "primary_missing_fact": "Adverse action details",
                        "missing_fact_bundle": ["Adverse action details"],
                        "satisfied_fact_bundle": ["Protected activity"],
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
                        "primary_missing_fact": "Manager knowledge",
                        "missing_fact_bundle": ["Manager knowledge", "Event sequence"],
                        "satisfied_fact_bundle": ["Protected activity"],
                        "adaptive_retry_applied": True,
                        "adaptive_retry_reason": "repeated_zero_result_reasoning_gap",
                        "adaptive_query_strategy": "standard_gap_targeted",
                        "adaptive_priority_penalty": 1,
                        "zero_result": True,
                        "resolution_applied": "manual_review_resolved",
                        "selected_search_program_type": "adverse_authority_search",
                        "selected_search_program_bias": "adverse",
                        "selected_search_program_rule_bias": "exception",
                        "source_family": "legal_authority",
                        "record_scope": "legal_authority",
                        "artifact_family": "legal_authority_reference",
                        "corpus_family": "legal_authority",
                        "content_origin": "authority_reference_fallback",
                    },
                ]
            }
        }
        mediator.get_claim_testimony_records.return_value = {
            "claims": {
                "retaliation": [
                    {
                        "testimony_id": "testimony:retaliation:001",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:1",
                        "claim_element_text": "Protected activity",
                        "raw_narrative": "I reported discrimination to HR before my supervisor retaliated.",
                        "event_date": "2026-03-10",
                        "actor": "HR",
                        "act": "received complaint",
                        "target": "discrimination report",
                        "harm": "retaliation followed",
                        "firsthand_status": "firsthand",
                        "source_confidence": 0.92,
                        "timestamp": "2026-03-12T11:00:00+00:00",
                    }
                ]
            },
            "summary": {
                "retaliation": {
                    "record_count": 1,
                    "linked_element_count": 1,
                    "firsthand_status_counts": {"firsthand": 1},
                    "confidence_bucket_counts": {"high": 1},
                    "latest_timestamp": "2026-03-12T11:00:00+00:00",
                }
            },
        }
        mediator.get_user_evidence.return_value = [
            {
                "id": 81,
                "cid": "QmDashboardDoc1",
                "type": "document",
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:1",
                "claim_element": "Protected activity",
                "description": "HR complaint memo",
                "timestamp": "2026-03-12T11:45:00+00:00",
                "source_url": "https://example.com/hr-memo",
                "parse_status": "parsed",
                "chunk_count": 3,
                "fact_count": 2,
                "parsed_text_preview": "Employee reported discrimination to HR in writing.",
                "parse_metadata": {
                    "quality_tier": "high",
                    "quality_score": 94.0,
                },
                "graph_status": "ready",
                "graph_entity_count": 4,
                "graph_relationship_count": 2,
            }
        ]
        mediator.get_evidence_chunks.return_value = [
            {"chunk_id": "chunk-0", "index": 0, "text": "Employee reported discrimination to HR."},
            {"chunk_id": "chunk-1", "index": 1, "text": "The memo was sent the same day."},
        ]
        mediator.get_evidence_facts.return_value = [
            {
                "fact_id": "fact:dashboard:1",
                "text": "Employee reported discrimination to HR in writing.",
                "confidence": 0.97,
                "quality_tier": "high",
            }
        ]
        mediator.get_evidence_graph.return_value = {
            "status": "ready",
            "entities": [
                {"id": "entity:employee", "type": "person", "name": "Employee"},
                {"id": "entity:hr", "type": "organization", "name": "HR"},
            ],
            "relationships": [
                {
                    "id": "rel:reported_to",
                    "source_id": "entity:employee",
                    "target_id": "entity:hr",
                    "relation_type": "reported_to",
                }
            ],
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
                            "primary_missing_fact": "Manager knowledge",
                            "missing_fact_bundle": ["Manager knowledge", "Event sequence"],
                            "satisfied_fact_bundle": ["Protected activity"],
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
                            "primary_missing_fact": "Adverse action details",
                            "missing_fact_bundle": ["Adverse action details"],
                            "satisfied_fact_bundle": ["Protected activity"],
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
                            "primary_missing_fact": "Manager knowledge",
                            "missing_fact_bundle": ["Manager knowledge", "Event sequence"],
                            "satisfied_fact_bundle": ["Protected activity"],
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
        assert payload["intake_status"] == {
            "current_phase": "intake",
            "iteration_count": 2,
            "ready_to_advance": False,
            "score": 0.5,
            "remaining_gap_count": 1,
            "contradiction_count": 1,
            "contradiction_summary": {
                "count": 1,
                "lane_counts": {},
                "status_counts": {},
                "severity_counts": {"high": 1},
                "corroboration_required_count": 0,
                "affected_claim_type_counts": {},
                "affected_element_counts": {},
            },
            "blockers": ["resolve_contradictions"],
            "criteria": {
                "case_theory_coherent": True,
                "minimum_proof_path_present": True,
                "claim_disambiguation_resolved": False,
            },
            "contradictions": [
                {
                    "contradiction_id": "",
                    "summary": "Complaint timing conflicts with employer timeline",
                    "left_text": "The complaint came first.",
                    "right_text": "The schedule cut came first.",
                    "category": "",
                    "severity": "high",
                    "question": "Which event happened first?",
                    "recommended_resolution_lane": "",
                    "current_resolution_status": "",
                    "external_corroboration_required": False,
                    "affected_claim_types": [],
                    "affected_element_ids": [],
                }
            ],
            "blocking_contradictions": [],
            "candidate_claim_count": 2,
            "canonical_fact_count": 2,
            "proof_lead_count": 1,
        }
        assert payload["intake_contradiction_summary"] == {
            "count": 1,
            "lane_counts": {},
            "status_counts": {},
            "severity_counts": {"high": 1},
            "corroboration_required_count": 0,
            "affected_claim_type_counts": {},
            "affected_element_counts": {},
        }
        intake_case_summary = payload["intake_case_summary"]
        assert intake_case_summary["candidate_claims"] == [
            {
                "claim_type": "retaliation",
                "label": "Retaliation",
                "confidence": 0.8,
                "ambiguity_flags": ["timing_overlap"],
            },
            {"claim_type": "wrongful_termination", "label": "Wrongful Termination", "confidence": 0.72},
        ]
        assert intake_case_summary["candidate_claim_summary"] == {
            "count": 2,
            "claim_types": ["retaliation", "wrongful_termination"],
            "average_confidence": 0.76,
            "top_claim_type": "retaliation",
            "top_confidence": 0.8,
            "ambiguous_claim_count": 1,
            "ambiguity_flag_count": 1,
            "ambiguity_flag_counts": {"timing_overlap": 1},
            "close_leading_claims": True,
        }
        assert intake_case_summary["intake_sections"] == {
            "chronology": {"status": "complete", "missing_items": []},
            "proof_leads": {"status": "partial", "missing_items": ["documents"]},
        }
        assert intake_case_summary["canonical_fact_summary"] == {
            "count": 2,
            "facts": [{"fact_id": "fact_001"}, {"fact_id": "fact_002"}],
        }
        assert intake_case_summary["canonical_fact_intent_summary"] == {}
        assert intake_case_summary["proof_lead_summary"] == {
            "count": 1,
            "proof_leads": [{"lead_id": "lead_001"}],
        }
        assert intake_case_summary["proof_lead_intent_summary"] == {}
        assert intake_case_summary["complainant_summary_confirmation"] == {}
        assert intake_case_summary["contradiction_summary"] == {
            "count": 1,
            "lane_counts": {},
            "status_counts": {},
            "severity_counts": {"high": 1},
            "corroboration_required_count": 0,
            "affected_claim_type_counts": {},
            "affected_element_counts": {},
        }
        assert intake_case_summary["timeline_anchor_summary"] == {
            "count": 1,
            "anchors": [{"anchor_id": "timeline_anchor_001"}],
        }
        assert intake_case_summary["timeline_relation_summary"] == {
            "count": 1,
            "relations": [{"relation_id": "timeline_relation_001", "relation_type": "before"}],
        }
        assert intake_case_summary["timeline_consistency_summary"] == {
            "event_count": 2,
            "anchor_count": 1,
            "ordered_fact_count": 2,
            "unsequenced_fact_count": 0,
            "approximate_fact_count": 0,
            "range_fact_count": 0,
            "relation_count": 1,
            "relation_type_counts": {"before": 1},
            "missing_temporal_fact_ids": [],
            "relative_only_fact_ids": [],
            "warnings": [],
            "partial_order_ready": True,
        }
        assert intake_case_summary["harm_profile"] == {
            "count": 1,
            "categories": ["economic"],
        }
        assert intake_case_summary["remedy_profile"] == {
            "count": 1,
            "categories": ["monetary"],
        }
        assert intake_case_summary["question_candidate_summary"] == {}
        assert intake_case_summary.get("intake_matching_summary") == {}
        assert intake_case_summary.get("intake_legal_targeting_summary") == {}
        assert intake_case_summary.get("intake_evidence_alignment_summary") == {}
        assert intake_case_summary["alignment_task_updates"] == [
            {
                "task_id": "retaliation:adverse_action:fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "adverse_action",
                "resolution_status": "partially_addressed",
                "status": "active",
            }
        ]
        assert intake_case_summary["alignment_task_update_history"][1]["evidence_sequence"] == 2
        assert intake_case_summary["alignment_task_update_summary"] == {
            "count": 2,
            "status_counts": {"active": 2},
            "resolution_status_counts": {
                "still_open": 1,
                "partially_addressed": 1,
            },
            "promoted_testimony_count": 0,
            "promoted_document_count": 0,
        }
        claim_support_packet_summary = intake_case_summary["claim_support_packet_summary"]
        assert claim_support_packet_summary["claim_count"] == 1
        assert claim_support_packet_summary["element_count"] == 3
        assert claim_support_packet_summary["status_counts"] == {
            "supported": 1,
            "partially_supported": 1,
            "unsupported": 1,
            "contradicted": 0,
        }
        assert claim_support_packet_summary["support_quality_counts"] == {
            "draft_ready": 1,
            "credible": 1,
            "suggestive": 0,
            "unsupported": 1,
            "contradicted": 0,
        }
        assert claim_support_packet_summary["recommended_actions"] == ["collect_missing_support_kind"]
        if "credible_support_ratio" in claim_support_packet_summary:
            assert claim_support_packet_summary["credible_support_ratio"] == 0.667
        if "supported_blocking_element_ratio" in claim_support_packet_summary:
            assert claim_support_packet_summary["supported_blocking_element_ratio"] == 0.333
        if "draft_ready_element_ratio" in claim_support_packet_summary:
            assert claim_support_packet_summary["draft_ready_element_ratio"] == 0.333
        if "high_quality_parse_ratio" in claim_support_packet_summary:
            assert claim_support_packet_summary["high_quality_parse_ratio"] == 0.333
        if "reviewable_escalation_ratio" in claim_support_packet_summary:
            assert claim_support_packet_summary["reviewable_escalation_ratio"] == 0.0
        if "claim_support_reviewable_escalation_count" in claim_support_packet_summary:
            assert claim_support_packet_summary["claim_support_reviewable_escalation_count"] == 0
        if "claim_support_unresolved_without_review_path_count" in claim_support_packet_summary:
            assert claim_support_packet_summary["claim_support_unresolved_without_review_path_count"] == 2
        if "proof_readiness_score" in claim_support_packet_summary:
            assert claim_support_packet_summary["proof_readiness_score"] == 0.45
        if "evidence_completion_ready" in claim_support_packet_summary:
            assert claim_support_packet_summary["evidence_completion_ready"] is False
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
        assert payload["claim_coverage_summary"]["retaliation"]["reasoning_hybrid_bridge_available_count"] == 0
        assert payload["claim_coverage_summary"]["retaliation"]["reasoning_hybrid_tdfol_formula_count"] == 0
        assert payload["claim_coverage_summary"]["retaliation"]["reasoning_hybrid_dcec_formula_count"] == 0
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
        assert payload["question_recommendations"]["retaliation"][0]["question_lane"] == "contradiction_resolution"
        assert payload["testimony_summary"]["retaliation"]["record_count"] == 1
        assert payload["document_summary"]["retaliation"]["record_count"] == 1
        assert payload["document_summary"]["retaliation"]["total_chunk_count"] == 3
        assert payload["document_summary"]["retaliation"]["total_fact_count"] == 2
        assert payload["document_summary"]["retaliation"]["graph_ready_record_count"] == 1
        assert payload["claim_coverage_summary"]["retaliation"]["testimony_record_count"] == 1
        assert payload["claim_coverage_summary"]["retaliation"]["document_record_count"] == 1
        assert payload["claim_coverage_summary"]["retaliation"]["document_total_fact_count"] == 2
        assert payload["claim_coverage_summary"]["retaliation"]["document_graph_ready_record_count"] == 1
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["testimony_record_count"] == 1
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["document_record_count"] == 1
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["document_fact_count"] == 2
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["validation_status"] == "supported"
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["proof_decision_trace"]["decision_source"] == "logic_proof_supported"
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["support_fact_packet_count"] == 2
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["support_fact_status_counts"] == {
            "supporting": 2,
            "contradicting": 0,
            "unresolved": 0,
        }
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["document_fact_packet_count"] == 1
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["document_fact_status_counts"] == {
            "supporting": 1,
            "contradicting": 0,
            "unresolved": 0,
        }
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["support_fact_packets"][0]["proof_status"] == "supporting"
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["document_fact_packets"][0]["fact_id"] == "fact:dashboard:1"
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["document_fact_packets"][0]["proof_status"] == "supporting"
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][1]["contradiction_pair_count"] == 1
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][1]["contradiction_pairs"][0]["left_fact"]["fact_id"] == "fact:authority:adverse"
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][1]["contradiction_pairs"][0]["right_fact"]["fact_id"] == "fact:evidence:adverse"
        assert payload["document_artifacts"]["retaliation"][0]["fact_previews"][0]["fact_id"] == "fact:dashboard:1"
        assert payload["document_artifacts"]["retaliation"][0]["graph_preview"]["entity_count"] == 2
        assert any(
            item.get("question_lane") == "contradiction_resolution"
            for item in payload["question_recommendations"]["retaliation"]
        )
        assert payload["follow_up_history"]["retaliation"][0]["support_kind"] == "manual_review"
        assert payload["follow_up_history"]["retaliation"][1]["primary_missing_fact"] == "Manager knowledge"
        assert payload["follow_up_history"]["retaliation"][1]["missing_fact_bundle"] == [
            "Manager knowledge",
            "Event sequence",
        ]
        assert payload["follow_up_history"]["retaliation"][1]["satisfied_fact_bundle"] == ["Protected activity"]
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
            "source_family_counts": {
                "legal_authority": 1,
            },
            "record_scope_counts": {
                "legal_authority": 1,
            },
            "artifact_family_counts": {
                "legal_authority_reference": 1,
            },
            "corpus_family_counts": {
                "legal_authority": 1,
            },
            "content_origin_counts": {
                "authority_reference_fallback": 1,
            },
            "primary_missing_fact_counts": {
                "Adverse action details": 1,
                "Manager knowledge": 1,
            },
            "missing_fact_bundle_counts": {
                "Adverse action details": 1,
                "Manager knowledge": 1,
                "Event sequence": 1,
            },
            "satisfied_fact_bundle_counts": {
                "Protected activity": 2,
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
        reasoning_review = payload["claim_reasoning_review"]["retaliation"]
        assert reasoning_review["claim_type"] == "retaliation"
        assert reasoning_review["total_element_count"] == 2
        assert reasoning_review["flagged_element_count"] == 2
        assert reasoning_review["fallback_ontology_element_count"] == 1
        assert reasoning_review["unavailable_backend_element_count"] == 1
        assert reasoning_review["degraded_adapter_element_count"] == 1
        assert reasoning_review["hybrid_bridge_element_count"] == 0
        assert reasoning_review["hybrid_bridge_available_element_count"] == 0
        assert reasoning_review["hybrid_tdfol_formula_count"] == 0
        assert reasoning_review["hybrid_dcec_formula_count"] == 0
        assert reasoning_review["hybrid_tdfol_formula_preview"] == []
        assert reasoning_review["hybrid_dcec_formula_preview"] == []
        assert reasoning_review["hybrid_formalism"] == ""
        assert reasoning_review["hybrid_reasoning_mode"] == ""
        assert reasoning_review["hybrid_compiler_bridge_path"] == ""
        assert any(
            item == {
                "element_id": "retaliation:1",
                "element_text": "Protected activity",
                "validation_status": "supported",
                "predicate_count": 4,
                "used_fallback_ontology": True,
                "backend_available_count": 3,
                "unavailable_adapters": ["logic_contradictions"],
                "degraded_adapters": ["logic_contradictions", "logic_proof"],
                "hybrid_bridge_used": False,
                "hybrid_bridge_available": False,
                "hybrid_tdfol_formula_count": 0,
                "hybrid_dcec_formula_count": 0,
                "hybrid_tdfol_formula_preview": [],
                "hybrid_dcec_formula_preview": [],
                "hybrid_formalism": "",
                "hybrid_reasoning_mode": "",
                "hybrid_compiler_bridge_path": "",
            }
            for item in reasoning_review["flagged_elements"]
        )
        assert any(
            item["element_id"] == "retaliation:2"
            and item["validation_status"] == "contradicted"
            for item in reasoning_review["flagged_elements"]
        )
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
        assert payload["follow_up_plan"]["retaliation"]["tasks"][0]["primary_missing_fact"] == "Manager knowledge"
        assert payload["follow_up_plan"]["retaliation"]["tasks"][0]["missing_fact_bundle"] == [
            "Manager knowledge",
            "Event sequence",
        ]
        assert payload["follow_up_plan"]["retaliation"]["tasks"][0]["satisfied_fact_bundle"] == ["Protected activity"]
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
        assert payload["follow_up_execution"]["retaliation"]["tasks"][0]["primary_missing_fact"] == "Manager knowledge"
        assert payload["follow_up_execution"]["retaliation"]["tasks"][0]["missing_fact_bundle"] == [
            "Manager knowledge",
            "Event sequence",
        ]
        assert payload["follow_up_execution"]["retaliation"]["tasks"][0]["satisfied_fact_bundle"] == ["Protected activity"]
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
        "hybrid_bridge_element_count": 0,
        "hybrid_bridge_available_element_count": 0,
        "hybrid_tdfol_formula_count": 0,
        "hybrid_dcec_formula_count": 0,
        "hybrid_tdfol_formula_preview": [],
        "hybrid_dcec_formula_preview": [],
        "hybrid_formalism": "",
        "hybrid_reasoning_mode": "",
        "hybrid_compiler_bridge_path": "",
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
        "hybrid_bridge_element_count": 0,
        "hybrid_bridge_available_element_count": 0,
        "hybrid_tdfol_formula_count": 0,
        "hybrid_dcec_formula_count": 0,
        "hybrid_tdfol_formula_preview": [],
        "hybrid_dcec_formula_preview": [],
        "hybrid_formalism": "",
        "hybrid_reasoning_mode": "",
        "hybrid_compiler_bridge_path": "",
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
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "iteration_count": 1,
        "intake_readiness": {
            "score": 0.5,
            "ready_to_advance": False,
            "remaining_gap_count": 1,
            "contradiction_count": 0,
            "criteria": {"complainant_summary_confirmed": True},
            "blockers": ["collect_evidence"],
            "contradictions": [],
            "candidate_claim_count": 1,
            "canonical_fact_count": 1,
            "proof_lead_count": 1,
        },
        "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.9}],
        "intake_sections": {},
        "canonical_fact_summary": {"count": 1, "facts": []},
        "canonical_fact_intent_summary": {},
        "proof_lead_summary": {"count": 1, "proof_leads": []},
        "proof_lead_intent_summary": {},
        "timeline_anchor_summary": {"count": 0, "anchors": []},
        "harm_profile": {},
        "remedy_profile": {},
        "complainant_summary_confirmation": {
            "status": "confirmed",
            "confirmed": True,
            "confirmed_at": "2026-03-17T10:00:00+00:00",
            "confirmation_note": "ready for evidence handoff",
            "confirmation_source": "dashboard",
            "summary_snapshot_index": 0,
            "current_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
            "confirmed_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
        },
        "question_candidate_summary": {},
        "claim_support_packet_summary": {},
        "intake_evidence_alignment_summary": {},
        "alignment_evidence_tasks": [],
        "alignment_task_updates": [],
        "alignment_task_update_history": [],
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
                        "proof_decision_source": "logic_unprovable",
                        "primary_missing_fact": "Manager knowledge",
                        "missing_fact_bundle": ["Manager knowledge", "Event sequence"],
                        "satisfied_fact_bundle": ["Protected activity"],
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
                        "primary_missing_fact": "Witness corroboration",
                        "missing_fact_bundle": ["Witness corroboration"],
                        "satisfied_fact_bundle": ["Protected activity"],
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
    assert payload["intake_summary_handoff"] == {
        "current_phase": "intake",
        "ready_to_advance": False,
        "complainant_summary_confirmation": {
            "status": "confirmed",
            "confirmed": True,
            "confirmed_at": "2026-03-17T10:00:00+00:00",
            "confirmation_note": "ready for evidence handoff",
            "confirmation_source": "dashboard",
            "summary_snapshot_index": 0,
            "current_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
            "confirmed_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
        },
    }
    assert payload["follow_up_support_kind"] == "evidence"
    assert payload["follow_up_force"] is True
    assert payload["follow_up_execution"]["retaliation"]["task_count"] == 1
    assert payload["follow_up_execution"]["retaliation"]["tasks"][0]["primary_missing_fact"] == "Manager knowledge"
    assert payload["follow_up_execution"]["retaliation"]["tasks"][0]["missing_fact_bundle"] == [
        "Manager knowledge",
        "Event sequence",
    ]
    assert payload["follow_up_execution"]["retaliation"]["tasks"][0]["satisfied_fact_bundle"] == ["Protected activity"]
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
        "support_by_kind": {},
        "support_by_source": {},
        "source_family_counts": {},
        "record_scope_counts": {},
        "artifact_family_counts": {},
        "corpus_family_counts": {},
        "content_origin_counts": {},
        "primary_missing_fact_counts": {
            "Manager knowledge": 1,
            "Witness corroboration": 1,
        },
        "missing_fact_bundle_counts": {
            "Manager knowledge": 1,
            "Event sequence": 1,
            "Witness corroboration": 1,
        },
        "satisfied_fact_bundle_counts": {
            "Protected activity": 2,
        },
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
        "resolution_status_counts": {},
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
    assert payload["post_execution_review"]["intake_summary_handoff"] == payload["intake_summary_handoff"]
    assert payload["post_execution_review"]["intake_status"]["intake_summary_handoff"] == payload["intake_summary_handoff"]
    assert payload["post_execution_review"]["intake_case_summary"]["intake_summary_handoff"] == payload["intake_summary_handoff"]
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


def test_claim_support_review_payload_includes_confirmed_handoff_metadata():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "iteration_count": 1,
        "intake_readiness": {
            "score": 1.0,
            "ready_to_advance": True,
            "remaining_gap_count": 0,
            "contradiction_count": 0,
            "criteria": {"complainant_summary_confirmed": True},
            "blockers": [],
            "contradictions": [],
            "candidate_claim_count": 1,
            "canonical_fact_count": 1,
            "proof_lead_count": 1,
        },
        "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.9}],
        "intake_sections": {},
        "canonical_fact_summary": {"count": 1, "facts": []},
        "canonical_fact_intent_summary": {},
        "proof_lead_summary": {"count": 1, "proof_leads": []},
        "proof_lead_intent_summary": {},
        "timeline_anchor_summary": {"count": 0, "anchors": []},
        "harm_profile": {},
        "remedy_profile": {},
        "complainant_summary_confirmation": {
            "status": "confirmed",
            "confirmed": True,
            "confirmed_at": "2026-03-17T10:00:00+00:00",
            "confirmation_note": "ready for evidence handoff",
            "confirmation_source": "dashboard",
            "summary_snapshot_index": 0,
            "current_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
            "confirmed_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
        },
        "question_candidate_summary": {},
        "claim_support_packet_summary": {},
        "intake_evidence_alignment_summary": {},
        "alignment_evidence_tasks": [],
        "alignment_task_updates": [],
        "alignment_task_update_history": [],
    }
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}
    }
    mediator.get_claim_overview.return_value = {"claims": {"retaliation": {}}}
    mediator.get_claim_support_diagnostic_snapshots.return_value = {"claims": {}}
    mediator.get_claim_support_gaps.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "unresolved_elements": []}}
    }
    mediator.get_claim_contradiction_candidates.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "candidates": []}}
    }
    mediator.get_claim_support_validation.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}
    }
    mediator.get_recent_claim_follow_up_execution.return_value = {"claims": {"retaliation": []}}
    mediator.get_claim_follow_up_plan.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "tasks": []}}
    }
    mediator.get_user_evidence.return_value = []
    mediator.summarize_claim_support.return_value = {"claims": {"retaliation": {}}}

    payload = build_claim_support_review_payload(
        mediator,
        ClaimSupportReviewRequest(claim_type="retaliation"),
    )

    assert payload["intake_summary_handoff"] == {
        "current_phase": "intake",
        "ready_to_advance": True,
        "complainant_summary_confirmation": {
            "status": "confirmed",
            "confirmed": True,
            "confirmed_at": "2026-03-17T10:00:00+00:00",
            "confirmation_note": "ready for evidence handoff",
            "confirmation_source": "dashboard",
            "summary_snapshot_index": 0,
            "current_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
            "confirmed_summary_snapshot": {
                "candidate_claim_count": 1,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
        },
    }
    assert payload["intake_status"]["intake_summary_handoff"] == payload["intake_summary_handoff"]
    assert payload["intake_case_summary"]["intake_summary_handoff"] == payload["intake_summary_handoff"]


def test_claim_support_follow_up_execution_payload_summarizes_escalation_outcomes():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.execute_claim_follow_up_plan.return_value = {
        "claims": {
            "retaliation": {
                "task_count": 1,
                "tasks": [
                    {
                        "claim_element": "Manager knowledge",
                        "follow_up_focus": "support_gap_closure",
                        "query_strategy": "standard_gap_targeted",
                        "proof_decision_source": "missing_support",
                        "primary_missing_fact": "Manager knowledge",
                        "missing_fact_bundle": ["Manager knowledge"],
                        "satisfied_fact_bundle": [],
                        "resolution_applied": "insufficient_support_after_search",
                        "graph_support": {"summary": {}},
                    }
                ],
                "skipped_tasks": [
                    {
                        "claim_element": "Causation",
                        "follow_up_focus": "support_gap_closure",
                        "query_strategy": "standard_gap_targeted",
                        "proof_decision_source": "missing_support",
                        "primary_missing_fact": "Witness corroboration",
                        "missing_fact_bundle": ["Witness corroboration"],
                        "satisfied_fact_bundle": [],
                        "resolution_status": "awaiting_testimony",
                        "resolution_applied": "awaiting_testimony",
                        "skipped": {
                            "escalation": {
                                "reason": "awaiting_testimony_collection",
                                "resolution_status": "awaiting_testimony",
                            }
                        },
                        "graph_support": {"summary": {}},
                    }
                ],
            }
        }
    }

    payload = build_claim_support_follow_up_execution_payload(
        mediator,
        ClaimSupportFollowUpExecuteRequest(
            claim_type="retaliation",
            include_post_execution_review=False,
        ),
    )

    assert payload["follow_up_execution_summary"]["retaliation"]["executed_task_count"] == 1
    assert payload["follow_up_execution_summary"]["retaliation"]["skipped_task_count"] == 1
    assert payload["follow_up_execution_summary"]["retaliation"]["resolution_status_counts"] == {
        "awaiting_testimony": 1,
    }
    assert payload["follow_up_execution_summary"]["retaliation"]["resolution_applied_counts"] == {
        "insufficient_support_after_search": 1,
        "awaiting_testimony": 1,
    }


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
                    "source_family": "legal_authority",
                    "record_scope": "legal_authority",
                    "artifact_family": "legal_authority_reference",
                    "corpus_family": "legal_authority",
                    "content_origin": "authority_reference_fallback",
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
        route.path == "/api/claim-support/confirm-intake-summary"
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
        route.path == "/api/claim-support/save-testimony"
        and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/claim-support/save-document"
        and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/claim-support/upload-document"
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


def test_claim_support_testimony_payload_persists_and_refreshes_review():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.save_claim_testimony_record.return_value = {
        "recorded": True,
        "testimony_id": "testimony:retaliation:abc123",
    }
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}
    }
    mediator.get_claim_overview.return_value = {"claims": {"retaliation": {}}}
    mediator.get_claim_support_diagnostic_snapshots.return_value = {"claims": {}}
    mediator.get_claim_support_gaps.return_value = {"claims": {"retaliation": {"unresolved_elements": []}}}
    mediator.get_claim_contradiction_candidates.return_value = {"claims": {"retaliation": {"candidates": []}}}
    mediator.get_claim_support_validation.return_value = {"claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}}
    mediator.get_recent_claim_follow_up_execution.return_value = {"claims": {"retaliation": []}}
    mediator.get_claim_follow_up_plan.return_value = {"claims": {"retaliation": {"tasks": []}}}
    mediator.get_claim_testimony_records.return_value = {
        "claims": {
            "retaliation": [
                {
                    "testimony_id": "testimony:retaliation:abc123",
                    "claim_type": "retaliation",
                    "claim_element_id": "retaliation:2",
                    "claim_element_text": "Adverse action",
                    "raw_narrative": "My supervisor cut my hours after I complained.",
                    "firsthand_status": "firsthand",
                    "source_confidence": 0.9,
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
    mediator.get_user_evidence.return_value = []
    mediator.summarize_claim_support.return_value = {"claims": {"retaliation": {}}}

    payload = build_claim_support_testimony_payload(
        mediator,
        ClaimSupportTestimonySaveRequest(
            claim_type="retaliation",
            claim_element_id="retaliation:2",
            claim_element="Adverse action",
            raw_narrative="My supervisor cut my hours after I complained.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        ),
    )

    assert payload["recorded"] is True
    assert payload["testimony_result"]["testimony_id"] == "testimony:retaliation:abc123"
    assert payload["post_save_review"]["testimony_summary"]["retaliation"]["record_count"] == 1
    mediator.save_claim_testimony_record.assert_called_once_with(
        claim_type="retaliation",
        user_id="state-user",
        claim_element_id="retaliation:2",
        claim_element_text="Adverse action",
        raw_narrative="My supervisor cut my hours after I complained.",
        event_date=None,
        actor=None,
        act=None,
        target=None,
        harm=None,
        firsthand_status="firsthand",
        source_confidence=0.9,
        metadata={},
    )


def test_claim_support_intake_summary_confirmation_payload_refreshes_review():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.confirm_intake_summary.return_value = {
        "complainant_summary_confirmation": {
            "confirmed": True,
            "confirmation_note": "reviewed with complainant",
            "confirmation_source": "dashboard",
        },
        "intake_readiness": {
            "ready_to_advance": True,
            "criteria": {"complainant_summary_confirmed": True},
        },
    }
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}
    }
    mediator.get_claim_overview.return_value = {"claims": {"retaliation": {}}}
    mediator.get_claim_support_diagnostic_snapshots.return_value = {"claims": {}}
    mediator.get_claim_support_gaps.return_value = {"claims": {"retaliation": {"unresolved_elements": []}}}
    mediator.get_claim_contradiction_candidates.return_value = {"claims": {"retaliation": {"candidates": []}}}
    mediator.get_claim_support_validation.return_value = {"claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}}
    mediator.get_recent_claim_follow_up_execution.return_value = {"claims": {"retaliation": []}}
    mediator.get_claim_follow_up_plan.return_value = {"claims": {"retaliation": {"tasks": []}}}
    mediator.get_claim_testimony_records.return_value = {"claims": {}, "summary": {}}
    mediator.get_user_evidence.return_value = []
    mediator.summarize_claim_support.return_value = {"claims": {"retaliation": {}}}
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "iteration_count": 1,
        "intake_readiness": {
            "score": 1.0,
            "ready_to_advance": True,
            "remaining_gap_count": 0,
            "contradiction_count": 0,
            "criteria": {"complainant_summary_confirmed": True},
            "blockers": [],
            "contradictions": [],
            "candidate_claim_count": 1,
            "canonical_fact_count": 1,
            "proof_lead_count": 1,
        },
        "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.9}],
        "intake_sections": {},
        "canonical_fact_summary": {"count": 1, "facts": []},
        "canonical_fact_intent_summary": {},
        "proof_lead_summary": {"count": 1, "proof_leads": []},
        "proof_lead_intent_summary": {},
        "timeline_anchor_summary": {"count": 0, "anchors": []},
        "harm_profile": {},
        "remedy_profile": {},
        "complainant_summary_confirmation": {
            "confirmed": True,
            "confirmation_note": "reviewed with complainant",
            "confirmation_source": "dashboard",
        },
        "question_candidate_summary": {},
        "claim_support_packet_summary": {},
        "intake_evidence_alignment_summary": {},
        "alignment_evidence_tasks": [],
        "alignment_task_updates": [],
        "alignment_task_update_history": [],
    }

    payload = build_claim_support_intake_summary_confirmation_payload(
        mediator,
        ClaimSupportIntakeSummaryConfirmRequest(
            claim_type="retaliation",
            confirmation_note="reviewed with complainant",
            confirmation_source="dashboard",
        ),
    )

    assert payload["confirmed"] is True
    assert payload["confirmation_result"]["confirmation_note"] == "reviewed with complainant"
    assert payload["post_confirmation_review"]["intake_case_summary"]["complainant_summary_confirmation"]["confirmed"] is True
    mediator.confirm_intake_summary.assert_called_once_with(
        confirmation_note="reviewed with complainant",
        confirmation_source="dashboard",
    )


def test_claim_support_document_payload_persists_and_refreshes_review():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.save_claim_support_document.return_value = {
        "record_id": 81,
        "cid": "QmDashboardDoc1",
        "recorded": True,
    }
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}
    }
    mediator.get_claim_overview.return_value = {"claims": {"retaliation": {}}}
    mediator.get_claim_support_diagnostic_snapshots.return_value = {"claims": {}}
    mediator.get_claim_support_gaps.return_value = {"claims": {"retaliation": {"unresolved_elements": []}}}
    mediator.get_claim_contradiction_candidates.return_value = {"claims": {"retaliation": {"candidates": []}}}
    mediator.get_claim_support_validation.return_value = {"claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}}
    mediator.get_recent_claim_follow_up_execution.return_value = {"claims": {"retaliation": []}}
    mediator.get_claim_follow_up_plan.return_value = {"claims": {"retaliation": {"tasks": []}}}
    mediator.get_claim_testimony_records.return_value = {"claims": {}, "summary": {}}
    mediator.get_user_evidence.return_value = [
        {
            "id": 81,
            "cid": "QmDashboardDoc1",
            "type": "document",
            "claim_type": "retaliation",
            "claim_element_id": "retaliation:2",
            "claim_element": "Adverse action",
            "description": "Termination memo",
            "timestamp": "2026-03-14T12:00:00+00:00",
            "source_url": "https://example.com/termination-memo",
            "parse_status": "parsed",
            "chunk_count": 2,
            "fact_count": 1,
            "parsed_text_preview": "The memo describes a termination after the complaint.",
            "parse_metadata": {"quality_tier": "high", "quality_score": 92.0},
            "graph_status": "ready",
            "graph_entity_count": 3,
            "graph_relationship_count": 1,
        }
    ]
    mediator.get_evidence_chunks.return_value = [
        {"chunk_id": "chunk-0", "index": 0, "text": "Termination followed the complaint."},
    ]
    mediator.summarize_claim_support.return_value = {"claims": {"retaliation": {}}}
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "iteration_count": 1,
        "intake_readiness": {"ready_to_advance": True},
        "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.9}],
        "intake_sections": {},
        "canonical_fact_summary": {"count": 1, "facts": []},
        "canonical_fact_intent_summary": {},
        "proof_lead_summary": {"count": 1, "proof_leads": []},
        "proof_lead_intent_summary": {},
        "timeline_anchor_summary": {"count": 0, "anchors": []},
        "harm_profile": {},
        "remedy_profile": {},
        "complainant_summary_confirmation": {
            "status": "confirmed",
            "confirmed": True,
            "confirmed_at": "2026-03-17T10:00:00+00:00",
            "confirmation_note": "ready for evidence handoff",
            "confirmation_source": "dashboard",
            "summary_snapshot_index": 0,
            "current_summary_snapshot": {"candidate_claim_count": 1, "canonical_fact_count": 1, "proof_lead_count": 1},
            "confirmed_summary_snapshot": {"candidate_claim_count": 1, "canonical_fact_count": 1, "proof_lead_count": 1},
        },
        "question_candidate_summary": {},
        "claim_support_packet_summary": {},
        "intake_evidence_alignment_summary": {},
        "alignment_evidence_tasks": [],
        "alignment_task_updates": [],
        "alignment_task_update_history": [],
    }

    payload = build_claim_support_document_payload(
        mediator,
        ClaimSupportDocumentSaveRequest(
            claim_type="retaliation",
            claim_element_id="retaliation:2",
            claim_element="Adverse action",
            document_label="Termination memo",
            source_url="https://example.com/termination-memo",
            document_text="Termination followed the complaint.",
        ),
    )

    assert payload["recorded"] is True
    assert payload["document_result"]["cid"] == "QmDashboardDoc1"
    assert payload["post_save_review"]["document_summary"]["retaliation"]["record_count"] == 1
    mediator.save_claim_support_document.assert_called_once_with(
        claim_type="retaliation",
        user_id="state-user",
        claim_element_id="retaliation:2",
        claim_element_text="Adverse action",
        document_text="Termination followed the complaint.",
        document_label="Termination memo",
        source_url="https://example.com/termination-memo",
        filename=None,
        mime_type=None,
        evidence_type="document",
        metadata={
            "intake_summary_handoff": {
                "current_phase": "intake",
                "ready_to_advance": True,
                "complainant_summary_confirmation": {
                    "status": "confirmed",
                    "confirmed": True,
                    "confirmed_at": "2026-03-17T10:00:00+00:00",
                    "confirmation_note": "ready for evidence handoff",
                    "confirmation_source": "dashboard",
                    "summary_snapshot_index": 0,
                    "current_summary_snapshot": {"candidate_claim_count": 1, "canonical_fact_count": 1, "proof_lead_count": 1},
                    "confirmed_summary_snapshot": {"candidate_claim_count": 1, "canonical_fact_count": 1, "proof_lead_count": 1},
                },
            },
        },
    )


def test_claim_support_upload_document_route_accepts_multipart_file():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.save_claim_support_document.return_value = {
        "record_id": 91,
        "cid": "QmUploadedDoc1",
        "recorded": True,
    }
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "iteration_count": 1,
        "intake_readiness": {"ready_to_advance": True},
        "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.9}],
        "intake_sections": {},
        "canonical_fact_summary": {"count": 1, "facts": []},
        "canonical_fact_intent_summary": {},
        "proof_lead_summary": {"count": 1, "proof_leads": []},
        "proof_lead_intent_summary": {},
        "timeline_anchor_summary": {"count": 0, "anchors": []},
        "harm_profile": {},
        "remedy_profile": {},
        "complainant_summary_confirmation": {
            "status": "confirmed",
            "confirmed": True,
            "confirmed_at": "2026-03-17T10:00:00+00:00",
            "confirmation_note": "ready for evidence handoff",
            "confirmation_source": "dashboard",
            "summary_snapshot_index": 0,
            "current_summary_snapshot": {"candidate_claim_count": 1, "canonical_fact_count": 1, "proof_lead_count": 1},
            "confirmed_summary_snapshot": {"candidate_claim_count": 1, "canonical_fact_count": 1, "proof_lead_count": 1},
        },
        "question_candidate_summary": {},
        "claim_support_packet_summary": {},
        "intake_evidence_alignment_summary": {},
        "alignment_evidence_tasks": [],
        "alignment_task_updates": [],
        "alignment_task_update_history": [],
    }

    app = create_review_api_app(mediator)
    client = TestClient(app)

    response = client.post(
        "/api/claim-support/upload-document",
        data={
            "claim_type": "retaliation",
            "claim_element_id": "retaliation:2",
            "claim_element": "Adverse action",
            "document_label": "Termination memo",
            "source_url": "https://example.com/termination-memo",
            "include_post_save_review": "false",
        },
        files={
            "file": ("termination-memo.txt", b"Termination followed the complaint.", "text/plain"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recorded"] is True
    assert payload["document_result"]["cid"] == "QmUploadedDoc1"
    mediator.save_claim_support_document.assert_called_once_with(
        claim_type="retaliation",
        user_id="state-user",
        claim_element_id="retaliation:2",
        claim_element_text="Adverse action",
        document_text=None,
        document_bytes=b"Termination followed the complaint.",
        document_label="Termination memo",
        source_url="https://example.com/termination-memo",
        filename="termination-memo.txt",
        mime_type="text/plain",
        evidence_type="document",
        metadata={
            "intake_summary_handoff": {
                "current_phase": "intake",
                "ready_to_advance": True,
                "complainant_summary_confirmation": {
                    "status": "confirmed",
                    "confirmed": True,
                    "confirmed_at": "2026-03-17T10:00:00+00:00",
                    "confirmation_note": "ready for evidence handoff",
                    "confirmation_source": "dashboard",
                    "summary_snapshot_index": 0,
                    "current_summary_snapshot": {"candidate_claim_count": 1, "canonical_fact_count": 1, "proof_lead_count": 1},
                    "confirmed_summary_snapshot": {"candidate_claim_count": 1, "canonical_fact_count": 1, "proof_lead_count": 1},
                },
            },
        },
    )


def test_claim_support_confirm_intake_summary_route_returns_refreshed_review():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.confirm_intake_summary.return_value = {
        "complainant_summary_confirmation": {
            "confirmed": True,
            "confirmation_note": "ready for evidence handoff",
            "confirmation_source": "dashboard",
        }
    }
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}
    }
    mediator.get_claim_overview.return_value = {"claims": {"retaliation": {}}}
    mediator.get_claim_support_diagnostic_snapshots.return_value = {"claims": {}}
    mediator.get_claim_support_gaps.return_value = {"claims": {"retaliation": {"unresolved_elements": []}}}
    mediator.get_claim_contradiction_candidates.return_value = {"claims": {"retaliation": {"candidates": []}}}
    mediator.get_claim_support_validation.return_value = {"claims": {"retaliation": {"claim_type": "retaliation", "elements": []}}}
    mediator.get_recent_claim_follow_up_execution.return_value = {"claims": {"retaliation": []}}
    mediator.get_claim_follow_up_plan.return_value = {"claims": {"retaliation": {"tasks": []}}}
    mediator.get_claim_testimony_records.return_value = {"claims": {}, "summary": {}}
    mediator.get_user_evidence.return_value = []
    mediator.summarize_claim_support.return_value = {"claims": {"retaliation": {}}}
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "iteration_count": 1,
        "intake_readiness": {
            "score": 1.0,
            "ready_to_advance": True,
            "remaining_gap_count": 0,
            "contradiction_count": 0,
            "criteria": {"complainant_summary_confirmed": True},
            "blockers": [],
            "contradictions": [],
            "candidate_claim_count": 1,
            "canonical_fact_count": 1,
            "proof_lead_count": 1,
        },
        "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.9}],
        "intake_sections": {},
        "canonical_fact_summary": {"count": 1, "facts": []},
        "canonical_fact_intent_summary": {},
        "proof_lead_summary": {"count": 1, "proof_leads": []},
        "proof_lead_intent_summary": {},
        "timeline_anchor_summary": {"count": 0, "anchors": []},
        "harm_profile": {},
        "remedy_profile": {},
        "complainant_summary_confirmation": {
            "confirmed": True,
            "confirmation_note": "ready for evidence handoff",
            "confirmation_source": "dashboard",
        },
        "question_candidate_summary": {},
        "claim_support_packet_summary": {},
        "intake_evidence_alignment_summary": {},
        "alignment_evidence_tasks": [],
        "alignment_task_updates": [],
        "alignment_task_update_history": [],
    }

    app = create_review_api_app(mediator)
    client = TestClient(app)

    response = client.post(
        "/api/claim-support/confirm-intake-summary",
        json={
            "claim_type": "retaliation",
            "confirmation_note": "ready for evidence handoff",
            "confirmation_source": "dashboard",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["confirmed"] is True
    assert payload["confirmation_result"]["confirmation_source"] == "dashboard"
    assert payload["post_confirmation_review"]["intake_case_summary"]["complainant_summary_confirmation"]["confirmed"] is True


def test_claim_support_save_testimony_route_canonicalizes_text_only_claim_element():
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_review_api_mediator(db_path)
        app = create_review_api_app(mediator)
        client = TestClient(app)

        response = client.post(
            "/api/claim-support/save-testimony",
            json={
                "claim_type": "retaliation",
                "claim_element": "Protected activity",
                "raw_narrative": "The HR complaint email does not exist.",
                "firsthand_status": "firsthand",
                "source_confidence": 0.92,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["recorded"] is True
        assert payload["testimony_result"]["claim_element_id"] == "retaliation:1"
        assert payload["testimony_result"]["claim_element_text"] == "Protected activity"
        assert payload["post_save_review"]["testimony_records"]["retaliation"][0]["claim_element_id"] == "retaliation:1"
        assert payload["post_save_review"]["testimony_summary"]["retaliation"]["linked_element_count"] == 1
        handoff_metadata = payload["post_save_review"]["testimony_records"]["retaliation"][0]["metadata"]["intake_summary_handoff"]
        assert handoff_metadata["current_phase"] == "intake"
        assert handoff_metadata["ready_to_advance"] is True
        assert handoff_metadata["complainant_summary_confirmation"]["confirmed"] is True
        assert handoff_metadata["complainant_summary_confirmation"]["confirmation_source"] == "dashboard"
        assert handoff_metadata["complainant_summary_confirmation"]["confirmed_summary_snapshot"]["candidate_claim_count"] == 1
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_route_backfills_legacy_unlinked_testimony_rows():
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_review_api_mediator(db_path)
        conn = duckdb.connect(db_path)
        conn.execute(
            """
            INSERT INTO claim_testimony (
                testimony_id,
                user_id,
                claim_type,
                claim_element_id,
                claim_element_text,
                raw_narrative,
                firsthand_status,
                source_confidence,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "testimony:retaliation:legacy-route",
                "state-user",
                "retaliation",
                None,
                "Protected activity",
                "Discrimination complaint email to HR does not exist.",
                "firsthand",
                0.9,
                json.dumps({"source": "legacy-route"}),
            ],
        )
        conn.close()

        app = create_review_api_app(mediator)
        client = TestClient(app)

        response = client.post(
            "/api/claim-support/review",
            json={
                "claim_type": "retaliation",
                "include_support_summary": False,
                "include_overview": False,
                "include_follow_up_plan": False,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["testimony_records"]["retaliation"][0]["claim_element_id"] == "retaliation:1"
        assert payload["testimony_records"]["retaliation"][0]["claim_element_text"] == "Protected activity"
        assert payload["testimony_summary"]["retaliation"]["linked_element_count"] == 1

        conn = duckdb.connect(db_path)
        persisted = conn.execute(
            "SELECT claim_element_id, claim_element_text FROM claim_testimony WHERE testimony_id = ?",
            ["testimony:retaliation:legacy-route"],
        ).fetchone()
        conn.close()

        assert persisted == ("retaliation:1", "Protected activity")
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_route_surfaces_proactively_repaired_legacy_testimony_rows():
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, hook = _build_hook_backed_review_api_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="state-user",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="The HR complaint email does not exist.",
            firsthand_status="firsthand",
            source_confidence=0.92,
        )

        conn = duckdb.connect(db_path)
        conn.execute(
            """
            INSERT INTO claim_testimony (
                testimony_id,
                user_id,
                claim_type,
                claim_element_id,
                claim_element_text,
                raw_narrative,
                firsthand_status,
                source_confidence,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "testimony:retaliation:legacy-ui",
                "state-user",
                "retaliation",
                None,
                "Protected activity",
                "The HR complaint email does not exist.",
                "firsthand",
                0.92,
                json.dumps({"source": "legacy-ui"}),
            ],
        )
        conn.close()

        backfill_result = hook.backfill_claim_testimony_links("state-user", "retaliation")
        assert backfill_result["updated_count"] == 1
        assert backfill_result["records"][0]["claim_element_id"] == "retaliation:1"

        def _coverage_matrix(*, claim_type=None, user_id=None, required_support_kinds=None):
            records_payload = mediator.get_claim_testimony_records(
                user_id or "state-user",
                claim_type or "retaliation",
            )
            records = records_payload["claims"]["retaliation"]
            testimony_links = [
                {
                    "claim_type": "retaliation",
                    "claim_element_id": record["claim_element_id"],
                    "claim_element_text": record["claim_element_text"],
                    "support_kind": "testimony",
                    "support_ref": record["testimony_id"],
                    "support_label": f"Testimony for {record['claim_element_text']}",
                    "source_table": "claim_testimony",
                    "support_strength": record["source_confidence"],
                    "timestamp": record["timestamp"],
                    "testimony_record_id": record["record_id"],
                }
                for record in records
            ]
            return {
                "claims": {
                    "retaliation": {
                        "claim_type": "retaliation",
                        "required_support_kinds": required_support_kinds or ["evidence", "authority"],
                        "total_elements": 3,
                        "status_counts": {"covered": 0, "partially_supported": 1, "missing": 2},
                        "total_links": len(testimony_links),
                        "total_facts": len(testimony_links),
                        "support_by_kind": {"testimony": len(testimony_links)},
                        "support_trace_summary": {},
                        "support_packet_summary": {},
                        "elements": [
                            {
                                "element_id": "retaliation:1",
                                "element_text": "Protected activity",
                                "status": "partially_supported",
                                "total_links": len(testimony_links),
                                "fact_count": len(testimony_links),
                                "support_by_kind": {"testimony": len(testimony_links)},
                                "missing_support_kinds": ["evidence", "authority"],
                                "links": testimony_links,
                            },
                            {
                                "element_id": "retaliation:2",
                                "element_text": "Adverse action",
                                "status": "missing",
                                "total_links": 0,
                                "fact_count": 0,
                                "support_by_kind": {},
                                "missing_support_kinds": ["evidence", "authority"],
                                "links": [],
                            },
                            {
                                "element_id": "retaliation:3",
                                "element_text": "Causal connection",
                                "status": "missing",
                                "total_links": 0,
                                "fact_count": 0,
                                "support_by_kind": {},
                                "missing_support_kinds": ["evidence", "authority"],
                                "links": [],
                            },
                        ],
                    }
                }
            }

        mediator.get_claim_coverage_matrix.side_effect = _coverage_matrix
        mediator.get_claim_overview.side_effect = lambda **kwargs: {
            "claims": {
                "retaliation": {
                    "covered": [],
                    "partially_supported": [{"element_text": "Protected activity"}],
                    "missing": [
                        {"element_text": "Adverse action"},
                        {"element_text": "Causal connection"},
                    ],
                }
            }
        }
        mediator.get_claim_support_gaps.side_effect = lambda **kwargs: {
            "claims": {
                "retaliation": {
                    "claim_type": "retaliation",
                    "unresolved_count": 3,
                    "unresolved_elements": [
                        {"element_text": "Protected activity", "recommended_action": "collect_missing_support_kind"},
                        {"element_text": "Adverse action", "recommended_action": "collect_initial_support"},
                        {"element_text": "Causal connection", "recommended_action": "collect_initial_support"},
                    ],
                }
            }
        }
        mediator.get_claim_contradiction_candidates.side_effect = lambda **kwargs: {
            "claims": {"retaliation": {"claim_type": "retaliation", "candidate_count": 0, "candidates": []}}
        }
        mediator.get_claim_support_validation.side_effect = lambda **kwargs: {
            "claims": {
                "retaliation": {
                    "claim_type": "retaliation",
                    "validation_status": "incomplete",
                    "validation_status_counts": {
                        "supported": 0,
                        "incomplete": 1,
                        "missing": 2,
                        "contradicted": 0,
                    },
                    "proof_gap_count": 6,
                    "elements_requiring_follow_up": [
                        "Protected activity",
                        "Adverse action",
                        "Causal connection",
                    ],
                    "elements": [],
                }
            }
        }
        mediator.get_claim_support_facts.side_effect = lambda **kwargs: []

        app = create_review_api_app(mediator)
        client = TestClient(app)

        response = client.post(
            "/api/claim-support/review",
            json={
                "claim_type": "retaliation",
                "include_support_summary": True,
                "include_overview": True,
                "include_follow_up_plan": False,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["claim_coverage_summary"]["retaliation"]["status_counts"] == {
            "covered": 0,
            "partially_supported": 1,
            "missing": 2,
        }
        assert payload["testimony_summary"]["retaliation"]["record_count"] == 2
        assert payload["testimony_summary"]["retaliation"]["linked_element_count"] == 1
        assert payload["testimony_summary"]["retaliation"]["firsthand_status_counts"] == {
            "firsthand": 2,
        }
        assert payload["claim_coverage_summary"]["retaliation"]["testimony_record_count"] == 2
        assert payload["claim_coverage_summary"]["retaliation"]["testimony_linked_element_count"] == 1
        assert payload["claim_overview"]["retaliation"]["partially_supported"] == [
            {"element_text": "Protected activity"}
        ]
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["testimony_record_count"] == 2
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["element_text"] == "Protected activity"
        assert payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["status"] == "partially_supported"
        assert all(
            record["claim_element_id"] == "retaliation:1"
            for record in payload["testimony_records"]["retaliation"]
        )
        assert all(
            record["claim_element_text"] == "Protected activity"
            for record in payload["testimony_records"]["retaliation"]
        )
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


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
                    "primary_missing_fact": "Manager knowledge",
                    "missing_fact_bundle": ["Manager knowledge", "Event sequence"],
                    "satisfied_fact_bundle": ["Protected activity"],
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
                    "graph_support": {
                        "summary": {
                            "semantic_cluster_count": 1,
                            "semantic_duplicate_count": 0,
                            "support_by_kind": {"evidence": 1},
                            "support_by_source": {"evidence": 1},
                        },
                        "results": [
                            {
                                "source_family": "evidence",
                                "record_scope": "evidence",
                                "artifact_family": "archived_web_page",
                                "corpus_family": "web_page",
                                "content_origin": "historical_archive_capture",
                            }
                        ],
                    },
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
                    "primary_missing_fact": "Adverse treatment timing",
                    "missing_fact_bundle": ["Adverse treatment timing"],
                    "satisfied_fact_bundle": ["Adverse action"],
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
                    "graph_support": {
                        "summary": {
                            "semantic_cluster_count": 2,
                            "semantic_duplicate_count": 1,
                            "support_by_kind": {"authority": 1},
                            "support_by_source": {"legal_authorities": 1},
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
                    "primary_missing_fact": "Manager knowledge",
                    "missing_fact_bundle": ["Manager knowledge", "Event sequence"],
                    "satisfied_fact_bundle": ["Protected activity"],
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
                    "graph_support": {
                        "summary": {
                            "semantic_cluster_count": 1,
                            "semantic_duplicate_count": 0,
                            "support_by_kind": {"evidence": 1},
                            "support_by_source": {"evidence": 1},
                        },
                        "results": [
                            {
                                "source_family": "evidence",
                                "record_scope": "evidence",
                                "artifact_family": "archived_web_page",
                                "corpus_family": "web_page",
                                "content_origin": "historical_archive_capture",
                            }
                        ],
                    },
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
                    "primary_missing_fact": "Adverse treatment timing",
                    "missing_fact_bundle": ["Adverse treatment timing"],
                    "satisfied_fact_bundle": ["Adverse action"],
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
                    "graph_support": {
                        "summary": {
                            "semantic_cluster_count": 2,
                            "semantic_duplicate_count": 1,
                            "support_by_kind": {"authority": 1},
                            "support_by_source": {"legal_authorities": 1},
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
    assert plan_summary["support_by_kind"] == {"evidence": 1, "authority": 1}
    assert plan_summary["support_by_source"] == {"evidence": 1, "legal_authorities": 1}
    assert plan_summary["source_family_counts"] == {"evidence": 1, "legal_authority": 1}
    assert plan_summary["record_scope_counts"] == {"evidence": 1, "legal_authority": 1}
    assert plan_summary["artifact_family_counts"] == {
        "archived_web_page": 1,
        "legal_authority_reference": 1,
    }
    assert plan_summary["corpus_family_counts"] == {"web_page": 1, "legal_authority": 1}
    assert plan_summary["content_origin_counts"] == {
        "historical_archive_capture": 1,
        "authority_reference_fallback": 1,
    }
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
    assert plan_summary["primary_missing_fact_counts"] == {
        "Adverse treatment timing": 1,
        "Manager knowledge": 1,
    }
    assert plan_summary["missing_fact_bundle_counts"] == {
        "Adverse treatment timing": 1,
        "Event sequence": 1,
        "Manager knowledge": 1,
    }
    assert plan_summary["satisfied_fact_bundle_counts"] == {
        "Adverse action": 1,
        "Protected activity": 1,
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
    assert execution_summary["support_by_kind"] == {"evidence": 1, "authority": 1}
    assert execution_summary["support_by_source"] == {"evidence": 1, "legal_authorities": 1}
    assert execution_summary["source_family_counts"] == {"evidence": 1, "legal_authority": 1}
    assert execution_summary["record_scope_counts"] == {"evidence": 1, "legal_authority": 1}
    assert execution_summary["artifact_family_counts"] == {
        "archived_web_page": 1,
        "legal_authority_reference": 1,
    }
    assert execution_summary["corpus_family_counts"] == {"web_page": 1, "legal_authority": 1}
    assert execution_summary["content_origin_counts"] == {
        "historical_archive_capture": 1,
        "authority_reference_fallback": 1,
    }
    assert execution_summary["primary_missing_fact_counts"] == {
        "Adverse treatment timing": 1,
        "Manager knowledge": 1,
    }
    assert execution_summary["missing_fact_bundle_counts"] == {
        "Adverse treatment timing": 1,
        "Event sequence": 1,
        "Manager knowledge": 1,
    }
    assert execution_summary["satisfied_fact_bundle_counts"] == {
        "Adverse action": 1,
        "Protected activity": 1,
    }
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
