import json
import os
import socket
import tempfile
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
requests = pytest.importorskip("requests")
uvicorn = pytest.importorskip("uvicorn")
FastAPI = pytest.importorskip("fastapi").FastAPI

duckdb = pytest.importorskip("duckdb")

from applications.review_api import attach_claim_support_review_routes
from applications.document_ui import attach_document_ui_routes
from applications.review_ui import attach_claim_support_review_ui_routes, attach_review_health_routes


pytestmark = [pytest.mark.no_auto_network, pytest.mark.browser]

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False


def _build_browser_smoke_app(mediator: Mock) -> FastAPI:
    app = FastAPI(title="Claim Support Review Smoke")
    attach_claim_support_review_routes(app, mediator)
    attach_claim_support_review_ui_routes(app)
    attach_review_health_routes(app, "claim-support-review-smoke")
    return app


def _build_document_browser_smoke_app() -> FastAPI:
    app = FastAPI(title="Document Builder Smoke")
    attach_document_ui_routes(app)
    attach_review_health_routes(app, "document-builder-smoke")
    return app


def _build_document_review_browser_smoke_app(mediator: Mock) -> FastAPI:
    app = FastAPI(title="Document Review Flow Smoke")
    attach_document_ui_routes(app)
    attach_claim_support_review_routes(app, mediator)
    attach_claim_support_review_ui_routes(app)
    attach_review_health_routes(app, "document-review-flow-smoke")
    return app


def _build_hook_backed_browser_mediator(db_path: str):
    try:
        from mediator.claim_support_hooks import ClaimSupportHook
    except ImportError as exc:
        pytest.skip(f"ClaimSupportHook requires dependencies: {exc}")

    mediator = Mock()
    mediator.state = SimpleNamespace(username="browser-smoke-text-link", hashed_username=None)
    mediator.log = Mock()
    mediator.get_three_phase_status.return_value = {
        "current_phase": "intake",
        "iteration_count": 2,
        "intake_readiness": {
            "score": 0.41,
            "ready_to_advance": False,
            "remaining_gap_count": 2,
            "contradiction_count": 1,
            "blockers": ["collect_missing_support", "complainant_summary_confirmation_required"],
            "criteria": {
                "case_theory_coherent": True,
                "minimum_proof_path_present": True,
                "claim_disambiguation_resolved": False,
                "complainant_summary_confirmed": False,
            },
            "contradictions": [
                {
                    "summary": "Termination date conflicts with reported complaint timeline",
                    "question": "Which date is supported by the termination notice?",
                    "recommended_resolution_lane": "request_document",
                    "current_resolution_status": "open",
                    "external_corroboration_required": True,
                    "affected_claim_types": ["retaliation"],
                    "affected_element_ids": ["retaliation:3"],
                }
            ],
            "candidate_claim_count": 2,
            "canonical_fact_count": 1,
            "proof_lead_count": 1,
        },
        "candidate_claims": [
            {
                "claim_type": "retaliation",
                "label": "Retaliation",
                "confidence": 0.87,
                "ambiguity_flags": ["timing_overlap"],
            },
            {
                "claim_type": "wrongful_termination",
                "label": "Wrongful Termination",
                "confidence": 0.79,
            },
        ],
        "intake_sections": {
            "proof_leads": {"status": "partial", "missing_items": ["documents"]},
        },
        "canonical_fact_summary": {
            "count": 1,
            "facts": [{"fact_id": "fact_001", "text": "Protected activity timeline recorded."}],
        },
        "canonical_fact_intent_summary": {
            "count": 1,
            "question_objective_counts": {"establish_chronology": 1},
            "expected_update_kind_counts": {"timeline_anchor": 1},
            "target_claim_type_counts": {"retaliation": 1},
            "target_element_id_counts": {"retaliation:1": 1},
        },
        "proof_lead_summary": {
            "count": 1,
            "proof_leads": [{"lead_id": "lead_001", "description": "Archived HR complaint email"}],
        },
        "proof_lead_intent_summary": {
            "count": 1,
            "question_objective_counts": {"identify_supporting_evidence": 1},
            "expected_update_kind_counts": {"proof_lead": 1},
            "target_claim_type_counts": {"retaliation": 1},
            "target_element_id_counts": {"retaliation:3": 1},
        },
        "timeline_anchor_summary": {
            "count": 1,
            "anchors": [{"anchor_id": "timeline_anchor_001", "anchor_text": "2026-02-03 complaint email"}],
        },
        "timeline_relation_summary": {
            "count": 1,
            "relations": [
                {
                    "relation_id": "timeline_relation_001",
                    "source_fact_id": "fact_001",
                    "target_fact_id": "fact_termination",
                    "relation_type": "before",
                    "source_start_date": "2026-02-03",
                    "source_end_date": "2026-02-03",
                    "target_start_date": "2026-02-10",
                    "target_end_date": "2026-02-10",
                    "confidence": "high",
                }
            ],
        },
        "timeline_consistency_summary": {
            "event_count": 2,
            "anchor_count": 1,
            "ordered_fact_count": 1,
            "unsequenced_fact_count": 1,
            "approximate_fact_count": 0,
            "range_fact_count": 0,
            "relation_count": 1,
            "relation_type_counts": {"before": 1},
            "missing_temporal_fact_ids": ["fact_termination"],
            "relative_only_fact_ids": ["fact_termination"],
            "warnings": ["Some timeline facts only express relative ordering and still need anchoring."],
            "partial_order_ready": False,
        },
        "harm_profile": {
            "count": 1,
            "categories": ["economic"],
        },
        "remedy_profile": {
            "count": 1,
            "categories": ["monetary"],
        },
        "complainant_summary_confirmation": {
            "status": "pending",
            "confirmed": False,
            "confirmation_source": "complainant",
            "confirmation_note": "",
            "summary_snapshot_index": 0,
            "current_summary_snapshot": {
                "candidate_claim_count": 2,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
            "confirmed_summary_snapshot": {},
        },
        "intake_evidence_alignment_summary": {
            "aligned_element_count": 1,
            "claims": {
                "retaliation": {
                    "shared_elements": [
                        {"element_id": "retaliation:1", "support_status": "supported"},
                    ],
                    "intake_only_element_ids": ["retaliation:3"],
                    "evidence_only_element_ids": ["retaliation:2"],
                }
            },
        },
        "alignment_evidence_tasks": [
            {
                "task_id": "retaliation:retaliation:3:fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:3",
                "claim_element_label": "Causal connection",
                "support_status": "missing",
                "action": "fill_evidence_gaps",
                "blocking": True,
                "preferred_support_kind": "evidence",
                "fallback_lanes": ["authority", "testimony"],
                "source_quality_target": "high_quality_document",
                "task_priority": "high",
                "resolution_status": "still_open",
                "resolution_notes": "",
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
        "alignment_task_updates": [
            {
                "task_id": "retaliation:retaliation:3:fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:3",
                "action": "fill_evidence_gaps",
                "previous_support_status": "",
                "current_support_status": "missing",
                "previous_missing_fact_bundle": [],
                "current_missing_fact_bundle": ["Timeline evidence"],
                "resolution_status": "still_open",
                "status": "active",
                "evidence_artifact_id": "artifact-open",
            }
        ],
        "alignment_task_update_history": [
            {
                "task_id": "retaliation:retaliation:3:fill_evidence_gaps",
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:3",
                "action": "fill_evidence_gaps",
                "previous_support_status": "",
                "current_support_status": "missing",
                "previous_missing_fact_bundle": [],
                "current_missing_fact_bundle": ["Timeline evidence"],
                "resolution_status": "still_open",
                "status": "active",
                "evidence_artifact_id": "artifact-open",
                "evidence_sequence": 1,
            },
            {
                "task_id": "retaliation:retaliation:3:resolve_support_conflicts",
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:3",
                "action": "resolve_support_conflicts",
                "previous_support_status": "missing",
                "current_support_status": "contradicted",
                "previous_missing_fact_bundle": ["Timeline evidence"],
                "current_missing_fact_bundle": ["Timeline evidence"],
                "resolution_status": "needs_manual_review",
                "status": "active",
                "evidence_artifact_id": "artifact-conflict",
                "evidence_sequence": 2,
            }
        ],
        "question_candidate_summary": {},
        "claim_support_packet_summary": {
            "claim_count": 1,
            "element_count": 2,
            "status_counts": {"unsupported": 2},
            "recommended_actions": ["collect_missing_support_kind"],
            "supported_blocking_element_ratio": 0.5,
            "credible_support_ratio": 0.5,
            "draft_ready_element_ratio": 0.0,
            "high_quality_parse_ratio": 0.0,
            "reviewable_escalation_ratio": 0.5,
            "claim_support_reviewable_escalation_count": 1,
            "claim_support_unresolved_without_review_path_count": 1,
            "proof_readiness_score": 0.225,
            "evidence_completion_ready": False,
            "temporal_fact_count": 2,
            "temporal_relation_count": 1,
            "temporal_issue_count": 1,
            "temporal_partial_order_ready_element_count": 0,
            "temporal_warning_count": 1,
            "temporal_gap_task_count": 1,
            "temporal_gap_targeted_task_count": 1,
            "temporal_rule_status_counts": {"partial": 1},
            "temporal_rule_blocking_reason_counts": {
                "Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.": 1,
            },
            "temporal_resolution_status_counts": {"still_open": 1},
        },
    }

    hook = ClaimSupportHook(mediator, db_path=db_path)
    hook.register_claim_requirements(
        "browser-smoke-text-link",
        {"retaliation": ["Protected activity", "Adverse action", "Causal connection"]},
    )

    def _save_testimony_record(**kwargs):
        return hook.save_testimony_record(**kwargs)

    def _get_testimony_records(user_id=None, claim_type=None, limit=100, **kwargs):
        resolved_user_id = user_id or kwargs.get("user_id") or "browser-smoke-text-link"
        resolved_claim_type = claim_type or kwargs.get("claim_type")
        resolved_limit = limit if limit is not None else kwargs.get("limit", 100)
        return hook.get_claim_testimony_records(
            resolved_user_id,
            resolved_claim_type,
            limit=resolved_limit,
        )

    def _build_testimony_links(records):
        return [
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
                "graph_summary": {
                    "entity_count": 0,
                    "relationship_count": 0,
                },
                "graph_trace": {
                    "source_table": "claim_testimony",
                    "summary": {
                        "status": "not_available",
                    },
                    "snapshot": {},
                    "metadata": {},
                    "lineage": {},
                },
            }
            for record in records
        ]

    def _get_claim_coverage_matrix(*, claim_type=None, user_id=None, required_support_kinds=None):
        testimony_payload = _get_testimony_records(
            user_id=user_id,
            claim_type=claim_type or "retaliation",
            limit=25,
        )
        testimony_records = testimony_payload["claims"]["retaliation"]
        testimony_links = _build_testimony_links(testimony_records)
        required_kinds = required_support_kinds or ["evidence", "authority"]
        return {
            "claims": {
                "retaliation": {
                    "claim_type": "retaliation",
                    "required_support_kinds": required_kinds,
                    "total_elements": 3,
                    "status_counts": {
                        "covered": 0,
                        "partially_supported": 1,
                        "missing": 2,
                    },
                    "total_links": len(testimony_links),
                    "total_facts": len(testimony_links),
                    "support_by_kind": {"testimony": len(testimony_links)},
                    "support_trace_summary": {},
                    "support_packet_summary": {},
                    "authority_treatment_summary": {},
                    "authority_rule_candidate_summary": {},
                    "elements": [
                        {
                            "element_id": "retaliation:1",
                            "element_text": "Protected activity",
                            "status": "partially_supported",
                            "total_links": len(testimony_links),
                            "fact_count": len(testimony_links),
                            "support_by_kind": {"testimony": len(testimony_links)},
                            "missing_support_kinds": list(required_kinds),
                            "links": testimony_links,
                            "links_by_kind": {"testimony": testimony_links},
                            "support_packets": [],
                            "support_packet_summary": {},
                            "authority_treatment_summary": {},
                            "proof_gap_count": len(required_kinds),
                            "proof_gaps": [
                                {
                                    "gap_type": "missing_support_kind",
                                    "support_kind": kind,
                                    "message": f"Missing required {kind} support.",
                                }
                                for kind in required_kinds
                            ],
                            "support_fact_packets": [],
                            "support_fact_status_counts": {},
                            "document_fact_packets": [],
                            "document_fact_status_counts": {},
                            "contradiction_pairs": [],
                            "contradiction_pair_count": 0,
                        },
                        {
                            "element_id": "retaliation:2",
                            "element_text": "Adverse action",
                            "status": "missing",
                            "total_links": 0,
                            "fact_count": 0,
                            "support_by_kind": {},
                            "missing_support_kinds": list(required_kinds),
                            "links": [],
                            "links_by_kind": {},
                            "support_packets": [],
                            "support_packet_summary": {},
                            "authority_treatment_summary": {},
                            "proof_gap_count": len(required_kinds),
                            "proof_gaps": [
                                {
                                    "gap_type": "missing_support_kind",
                                    "support_kind": kind,
                                    "message": f"Missing required {kind} support.",
                                }
                                for kind in required_kinds
                            ],
                            "support_fact_packets": [],
                            "support_fact_status_counts": {},
                            "document_fact_packets": [],
                            "document_fact_status_counts": {},
                            "contradiction_pairs": [],
                            "contradiction_pair_count": 0,
                        },
                        {
                            "element_id": "retaliation:3",
                            "element_text": "Causal connection",
                            "status": "missing",
                            "total_links": 0,
                            "fact_count": 0,
                            "support_by_kind": {},
                            "missing_support_kinds": list(required_kinds),
                            "links": [],
                            "links_by_kind": {},
                            "support_packets": [],
                            "support_packet_summary": {},
                            "authority_treatment_summary": {},
                            "proof_gap_count": len(required_kinds),
                            "proof_gaps": [
                                {
                                    "gap_type": "missing_support_kind",
                                    "support_kind": kind,
                                    "message": f"Missing required {kind} support.",
                                }
                                for kind in required_kinds
                            ],
                            "support_fact_packets": [],
                            "support_fact_status_counts": {},
                            "document_fact_packets": [],
                            "document_fact_status_counts": {},
                            "contradiction_pairs": [],
                            "contradiction_pair_count": 0,
                        },
                    ],
                }
            }
        }

    mediator.save_claim_testimony_record.side_effect = _save_testimony_record
    mediator.get_claim_testimony_records.side_effect = _get_testimony_records
    mediator.get_claim_coverage_matrix.side_effect = _get_claim_coverage_matrix
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
    mediator.get_claim_support_diagnostic_snapshots.return_value = {"claims": {}}
    mediator.get_claim_support_gaps.side_effect = lambda **kwargs: {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "unresolved_count": 3,
                "unresolved_elements": [
                    {
                        "element_text": "Protected activity",
                        "recommended_action": "collect_missing_support_kind",
                    },
                    {
                        "element_text": "Adverse action",
                        "recommended_action": "collect_initial_support",
                    },
                    {
                        "element_text": "Causal connection",
                        "recommended_action": "collect_initial_support",
                    },
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
    mediator.get_claim_support_validation.side_effect = lambda **kwargs: {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "required_support_kinds": ["evidence", "authority"],
                "validation_status": "incomplete",
                "validation_status_counts": {
                    "supported": 1,
                    "incomplete": 0,
                    "missing": 2,
                    "contradicted": 0,
                },
                "proof_gap_count": 4,
                "elements_requiring_follow_up": [
                    "Adverse action",
                    "Causal connection",
                ],
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
                                },
                            },
                        },
                        "contradiction_candidates": [],
                    },
                    {
                        "element_id": "retaliation:2",
                        "element_text": "Adverse action",
                        "validation_status": "missing",
                        "recommended_action": "collect_initial_support",
                        "proof_gap_count": 2,
                        "proof_gaps": [
                            {
                                "gap_type": "missing_support_kind",
                                "support_kind": "evidence",
                                "message": "Missing required evidence support.",
                            },
                            {
                                "gap_type": "missing_support_kind",
                                "support_kind": "authority",
                                "message": "Missing required authority support.",
                            },
                        ],
                        "proof_decision_trace": {
                            "decision_source": "missing_support",
                        },
                        "proof_diagnostics": {
                            "decision_source": "missing_support",
                        },
                        "contradiction_candidates": [],
                    },
                    {
                        "element_id": "retaliation:3",
                        "element_text": "Causal connection",
                        "validation_status": "missing",
                        "recommended_action": "collect_initial_support",
                        "proof_gap_count": 2,
                        "proof_gaps": [
                            {
                                "gap_type": "missing_support_kind",
                                "support_kind": "evidence",
                                "message": "Missing required evidence support.",
                            },
                            {
                                "gap_type": "missing_support_kind",
                                "support_kind": "authority",
                                "message": "Missing required authority support.",
                            },
                        ],
                        "proof_decision_trace": {
                            "decision_source": "missing_support",
                        },
                        "proof_diagnostics": {
                            "decision_source": "missing_support",
                        },
                        "contradiction_candidates": [],
                    },
                ],
            }
        }
    }
    mediator.get_claim_support_facts.side_effect = lambda **kwargs: []
    mediator.get_recent_claim_follow_up_execution.return_value = {
        "claims": {
            "retaliation": [
                {
                    "execution_id": 44,
                    "claim_type": "retaliation",
                    "claim_element_id": "retaliation:3",
                    "claim_element_text": "Causal connection",
                    "support_kind": "authority",
                    "query_text": '"retaliation" "causal connection" statute',
                    "status": "executed",
                    "timestamp": "2026-03-12T12:30:00",
                    "execution_mode": "retrieve_support",
                    "follow_up_focus": "standard_gap_closure",
                    "query_strategy": "standard_gap_targeted",
                    "primary_missing_fact": "Manager knowledge",
                    "missing_fact_bundle": ["Manager knowledge", "Event sequence"],
                    "satisfied_fact_bundle": ["Protected activity"],
                    "resolution_status": "insufficient_support_after_search",
                    "resolution_applied": "insufficient_support_after_search",
                    "source_quality_target": "high_quality_document",
                    "intake_proof_leads": [
                        {
                            "lead_id": "lead:complainant:record",
                            "owner": "complainant",
                            "recommended_support_kind": "evidence",
                            "description": "Termination email held by complainant",
                        }
                    ],
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
                    "claim_element_id": "retaliation:3",
                    "claim_element_text": "Causal connection",
                    "support_kind": "testimony",
                    "query_text": 'clarify retaliation chronology',
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
                        "Retaliation causation lacks a clear temporal ordering from protected activity to adverse action."
                    ],
                    "temporal_rule_follow_ups": [
                        "Clarify whether the protected activity occurred before the adverse action."
                    ],
                }
            ]
        }
    }
    mediator.get_claim_follow_up_plan.side_effect = lambda **kwargs: {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "task_count": 2,
                "tasks": [
                    {
                        "claim_element_id": "retaliation:3",
                        "claim_element": "Causal connection",
                        "status": "missing",
                        "priority": "high",
                        "recommended_action": "collect_initial_support",
                        "follow_up_focus": "standard_gap_closure",
                        "query_strategy": "standard_gap_targeted",
                        "primary_missing_fact": "Manager knowledge",
                        "missing_fact_bundle": ["Manager knowledge", "Event sequence"],
                        "satisfied_fact_bundle": ["Protected activity"],
                        "missing_support_kinds": ["authority"],
                        "resolution_status": "awaiting_complainant_record",
                        "blocked_by_cooldown": False,
                        "should_suppress_retrieval": False,
                        "source_quality_target": "high_quality_document",
                        "intake_proof_leads": [
                            {
                                "lead_id": "lead:complainant:record",
                                "owner": "complainant",
                                "recommended_support_kind": "evidence",
                                "description": "Termination email held by complainant",
                            }
                        ],
                        "authority_search_program_summary": {
                            "program_count": 1,
                            "primary_program_type": "element_definition_search",
                            "primary_program_bias": "uncertain",
                            "primary_program_rule_bias": "procedural_prerequisite",
                        },
                        "graph_support": {
                            "summary": {
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
                    },
                    {
                        "claim_element_id": "retaliation:3",
                        "claim_element": "Causal connection",
                        "status": "missing",
                        "priority": "high",
                        "recommended_action": "review_existing_support",
                        "follow_up_focus": "temporal_gap_closure",
                        "query_strategy": "temporal_gap_targeted",
                        "primary_missing_fact": "Event sequence",
                        "missing_fact_bundle": ["Event sequence"],
                        "satisfied_fact_bundle": [],
                        "missing_support_kinds": ["testimony"],
                        "resolution_status": "awaiting_testimony",
                        "blocked_by_cooldown": False,
                        "should_suppress_retrieval": False,
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
                            "Retaliation causation lacks a clear temporal ordering from protected activity to adverse action."
                        ],
                        "temporal_rule_follow_ups": [
                            "Clarify whether the protected activity occurred before the adverse action."
                        ],
                        "graph_support": {
                            "summary": {},
                            "results": [],
                        },
                    }
                ],
            }
        }
    }
    mediator.get_user_evidence.return_value = []
    mediator.summarize_claim_support.return_value = {"claims": {"retaliation": {}}}

    def _confirm_intake_summary(confirmation_note="", confirmation_source="complainant"):
        status_payload = mediator.get_three_phase_status.return_value
        status_payload["complainant_summary_confirmation"] = {
            "status": "confirmed",
            "confirmed": True,
            "confirmed_at": "2026-03-16T12:00:00+00:00",
            "confirmation_source": confirmation_source,
            "confirmation_note": confirmation_note,
            "summary_snapshot_index": 0,
            "current_summary_snapshot": {
                "candidate_claim_count": 2,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
            "confirmed_summary_snapshot": {
                "candidate_claim_count": 2,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
        }
        intake_readiness = status_payload["intake_readiness"]
        criteria = intake_readiness.get("criteria", {})
        criteria["complainant_summary_confirmed"] = True
        intake_readiness["criteria"] = criteria
        intake_readiness["blockers"] = [
            blocker
            for blocker in intake_readiness.get("blockers", [])
            if blocker != "complainant_summary_confirmation_required"
        ]
        return status_payload

    mediator.confirm_intake_summary.side_effect = _confirm_intake_summary

    return mediator, hook


def _build_real_browser_upload_mediator(
    *,
    evidence_db_path: str,
    claim_support_db_path: str,
    legal_authority_db_path: str,
):
    try:
        from mediator import Mediator
    except ImportError as exc:
        pytest.skip(f"Mediator requires dependencies: {exc}")

    mock_backend = Mock()
    mock_backend.id = "browser-upload-backend"

    mediator = Mediator(
        backends=[mock_backend],
        evidence_db_path=evidence_db_path,
        claim_support_db_path=claim_support_db_path,
        legal_authority_db_path=legal_authority_db_path,
    )
    mediator.state.username = "browser-upload-user"
    mediator.claim_support.register_claim_requirements(
        "browser-upload-user",
        {"retaliation": ["Protected activity", "Adverse action", "Causal connection"]},
    )
    mediator.get_three_phase_status = Mock(
        return_value={
            "current_phase": "intake",
            "iteration_count": 1,
            "intake_readiness": {
                "score": 0.52,
                "ready_to_advance": False,
                "remaining_gap_count": 2,
                "contradiction_count": 0,
                "blockers": ["collect_missing_support"],
            },
            "candidate_claims": [
                {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.89},
            ],
            "intake_sections": {
                "proof_leads": {"status": "partial", "missing_items": ["documents"]},
            },
            "canonical_fact_summary": {
                "count": 1,
                "facts": [{"fact_id": "fact_001", "text": "Protected activity already recorded."}],
            },
            "proof_lead_summary": {
                "count": 1,
                "proof_leads": [{"lead_id": "lead_001", "description": "Upload documentary evidence"}],
            },
            "question_candidate_summary": {},
            "claim_support_packet_summary": {},
        }
    )
    return mediator


@contextmanager
def _serve_app(app: FastAPI):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://{host}:{port}"
    deadline = time.time() + 15
    last_error = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/health", timeout=0.5)
            if response.ok:
                break
        except Exception as exc:  # pragma: no cover - startup timing only
            last_error = exc
        time.sleep(0.1)
    else:  # pragma: no cover - hard failure path
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError(f"Timed out waiting for local review server: {last_error}")

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_claim_support_review_dashboard_smoke_shows_proactively_repaired_legacy_testimony_links():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
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
                "browser-smoke-text-link",
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

        result = hook.backfill_claim_testimony_links("browser-smoke-text-link", "retaliation")
        assert result["updated_count"] == 1

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.click("#review-button")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                summary_text = page.locator("#testimony-summary-chips").inner_text()
                testimony_text = page.locator("#testimony-list").inner_text()
                element_text = page.locator("#element-list").inner_text()

                assert "Records: 2" in summary_text
                assert "Linked elements: 1" in summary_text
                assert "firsthand: 2" in summary_text
                assert page.locator("#testimony-list .history-card").count() == 2
                assert testimony_text.count("Protected activity") == 2
                assert testimony_text.count("The HR complaint email does not exist.") == 2
                assert "Protected activity" in element_text
                assert "facts=2 links=2" in element_text
                assert "PARTIALLY_SUPPORTED" in element_text

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_preserves_support_kind_in_canonical_url():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for support-kind URL smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?"
                    "claim_type=retaliation&"
                    "user_id=browser-smoke-text-link&"
                    "section=claims_for_relief&"
                    "follow_up_support_kind=authority"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "follow_up_support_kind=authority" in page.url
                assert page.locator("#support-kind").input_value() == "authority"
                assert "Claims For Relief" in page.locator("#prefill-context-line").inner_text()
                assert "Focused lane: Authority." in page.locator("#prefill-context-line").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_document_builder_smoke_renders_question_review_links_with_section_aware_support_kind():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"sections": {}, "claims": [], "warnings": []},
        "filing_checklist": [],
        "review_links": {},
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 1,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support"],
                "criteria": {
                    "case_theory_coherent": True,
                    "minimum_proof_path_present": True,
                    "claim_disambiguation_resolved": False,
                },
                "contradictions": [
                    {
                        "summary": "Termination date conflicts with reported complaint timeline",
                        "question": "Which date is supported by the termination notice?",
                        "recommended_resolution_lane": "request_document",
                        "current_resolution_status": "open",
                        "external_corroboration_required": True,
                        "affected_claim_types": ["retaliation"],
                        "affected_element_ids": ["retaliation:2"],
                    }
                ],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.87, "ambiguity_flags": ["timing_overlap"]},
                    {"claim_type": "wrongful_termination", "label": "Wrongful Termination", "confidence": 0.79},
                ],
                "complainant_summary_confirmation": {
                    "status": "pending",
                    "confirmed": False,
                    "confirmation_source": "complainant",
                    "confirmation_note": "",
                    "summary_snapshot_index": 0,
                    "current_summary_snapshot": {
                        "candidate_claim_count": 2,
                        "canonical_fact_count": 1,
                        "proof_lead_count": 1,
                    },
                    "confirmed_summary_snapshot": {},
                },
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "canonical_fact_intent_summary": {
                    "count": 1,
                    "question_objective_counts": {"establish_chronology": 1},
                    "expected_update_kind_counts": {"timeline_anchor": 1},
                    "target_claim_type_counts": {"retaliation": 1},
                    "target_element_id_counts": {"retaliation:1": 1},
                },
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "proof_lead_intent_summary": {
                    "count": 1,
                    "question_objective_counts": {"identify_supporting_evidence": 1},
                    "expected_update_kind_counts": {"proof_lead": 1},
                    "target_claim_type_counts": {"retaliation": 1},
                    "target_element_id_counts": {"retaliation:3": 1},
                },
                "timeline_anchor_summary": {"count": 1, "anchors": [{"anchor_id": "timeline_anchor_001"}]},
                "harm_profile": {"count": 1, "categories": ["economic"]},
                "remedy_profile": {"count": 1, "categories": ["monetary"]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {"blocking": 1, "non_blocking": 1},
                },
                "alignment_evidence_tasks": [
                    {
                        "task_id": "retaliation:proof_leads:collect_complainant_record",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:3",
                        "claim_element_label": "Proof Leads",
                        "action": "fill_temporal_chronology_gap",
                        "preferred_support_kind": "evidence",
                        "fallback_lanes": ["authority", "testimony"],
                        "source_quality_target": "high_quality_document",
                        "resolution_status": "awaiting_complainant_record",
                        "temporal_rule_profile_id": "retaliation_temporal_profile_v1",
                        "temporal_rule_status": "partial",
                        "temporal_rule_blocking_reasons": [
                            "Retaliation chronology still needs documentary sequencing for the proof lead bundle.",
                        ],
                        "temporal_rule_follow_ups": [
                            "Confirm whether the protected activity report predates the termination email.",
                        ],
                        "intake_proof_leads": [
                            {
                                "lead_id": "lead:complainant:record",
                                "owner": "complainant",
                                "recommended_support_kind": "evidence",
                                "description": "Termination email held by complainant",
                            }
                        ],
                    }
                ],
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                    "supported_blocking_element_ratio": 0.5,
                    "credible_support_ratio": 0.5,
                    "draft_ready_element_ratio": 0.0,
                    "high_quality_parse_ratio": 0.0,
                    "reviewable_escalation_ratio": 0.5,
                    "claim_support_reviewable_escalation_count": 1,
                    "claim_support_unresolved_without_review_path_count": 1,
                    "proof_readiness_score": 0.225,
                    "evidence_completion_ready": False,
                    "temporal_fact_count": 2,
                    "temporal_relation_count": 1,
                    "temporal_issue_count": 1,
                    "temporal_partial_order_ready_element_count": 0,
                    "temporal_warning_count": 1,
                    "temporal_gap_task_count": 1,
                    "temporal_gap_targeted_task_count": 1,
                    "temporal_rule_status_counts": {"partial": 1},
                    "temporal_rule_blocking_reason_counts": {
                        "Retaliation chronology still needs documentary sequencing for the proof lead bundle.": 1,
                    },
                    "temporal_resolution_status_counts": {"awaiting_complainant_record": 1},
                },
                "alignment_task_update_history": [
                    {
                        "task_id": "retaliation:proof_leads:resolve_support_conflicts",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:3",
                        "claim_element_label": "Proof Leads",
                        "action": "resolve_support_conflicts",
                        "current_support_status": "contradicted",
                        "resolution_status": "needs_manual_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-conflict",
                        "evidence_sequence": 2,
                    },
                    {
                        "task_id": "retaliation:proof_leads:await_operator_confirmation",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:3",
                        "claim_element_label": "Proof Leads",
                        "action": "await_operator_confirmation",
                        "current_support_status": "partially_supported",
                        "resolution_status": "answered_pending_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-pending",
                        "evidence_sequence": 3,
                    }
                ],
            },
            "packet_projection": {
                "title": "Complaint Packet",
                "section_presence": {"factual_allegations": True},
                "has_affidavit": False,
                "has_certificate_of_service": False,
            },
            "section_history": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "overall_score": 0.7,
                }
            ],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    app = _build_document_browser_smoke_app()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.goto(f"{base_url}/document")
            page.evaluate("payload => window.renderPreview(payload)", payload)
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('#previewRoot a.inline-link')).some((node) => node.textContent.includes('Question Review'))"
            )

            question_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#previewRoot a.inline-link'))
                    .filter((node) => node.textContent.includes('Question Review'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )

            assert {
                "text": "Open Proof Leads Question Review (1)",
                "href": "/claim-support-review?section=proof_leads&follow_up_support_kind=evidence&alignment_task_update_filter=active&alignment_task_update_sort=newest_first",
            } in question_links
            assert {
                "text": "Open Claims For Relief Question Review (1)",
                "href": "/claim-support-review?section=claims_for_relief&follow_up_support_kind=authority&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first",
            } in question_links

            section_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#previewRoot a.inline-link'))
                    .filter((node) => node.textContent.includes('Intake Section Review'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )
            claim_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#previewRoot a.inline-link'))
                    .filter((node) => node.textContent.includes('Intake Claim Review'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )
            manual_review_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#previewRoot a.inline-link'))
                    .filter((node) => node.textContent.includes('Manual Review'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )
            pending_review_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#previewRoot a.inline-link'))
                    .filter((node) => node.textContent.includes('Pending Review'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )
            preview_text = page.locator("#previewRoot").inner_text()

            assert {
                "text": "Open Retaliation Intake Claim Review",
                "href": "/claim-support-review?claim_type=retaliation&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first",
            } in claim_links
            assert {
                "text": "Open Proof Leads Intake Section Review",
                "href": "/claim-support-review?section=proof_leads&follow_up_support_kind=evidence&alignment_task_update_filter=active&alignment_task_update_sort=newest_first",
            } in section_links
            assert {
                "text": "Open Claims For Relief Intake Section Review",
                "href": "/claim-support-review?section=claims_for_relief&follow_up_support_kind=authority&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first",
            } in section_links
            assert {
                "text": "Open Retaliation Manual Review",
                "href": "/claim-support-review?claim_type=retaliation&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first",
            } in manual_review_links
            assert {
                "text": "Open Retaliation Pending Review",
                "href": "/claim-support-review?claim_type=retaliation&alignment_task_update_filter=pending_review&alignment_task_update_sort=pending_review_first",
            } in pending_review_links
            assert "Candidate claim count: 2" in preview_text
            assert "Candidate claim average confidence: 0.83" in preview_text
            assert "Leading claim: Retaliation 0.87" in preview_text
            assert "Claim disambiguation: needed" in preview_text
            assert "Claim ambiguity flags: 1" in preview_text
            assert "Claim ambiguity details: Timing Overlap 1" in preview_text
            assert "Timeline anchors: 1" in preview_text
            assert "Harm profile: Economic" in preview_text
            assert "Remedy profile: Monetary" in preview_text
            assert "Canonical fact intent records: 1" in preview_text
            assert "Canonical fact objectives: Establish Chronology 1" in preview_text
            assert "Proof lead intent records: 1" in preview_text
            assert "Proof lead update kinds: Proof Lead 1" in preview_text
            assert "Persisted intake criteria: Case Theory Coherent ready, Minimum Proof Path Present ready, Claim Disambiguation Resolved needs work" in preview_text
            assert "Corroboration-required contradictions: 1" in preview_text
            assert "Contradiction lanes: Request Document 1" in preview_text
            assert "Contradiction target elements: Retaliation:2 1" in preview_text
            assert preview_text.count("Contradiction target elements: Retaliation:2 1") == 1
            assert "Termination date conflicts with reported complaint timeline | ask Which date is supported by the termination notice? | lane Request Document | status Open | external corroboration required | claims Retaliation" in preview_text
            assert "Persisted contradiction lanes: Request Document 1" in preview_text
            assert "Persisted corroboration-required contradictions: 1" in preview_text
            assert "Persisted contradiction target elements: Retaliation:2 1" in preview_text
            assert preview_text.count("Persisted contradiction target elements: Retaliation:2 1") == 1
            assert "Manual Review Blockers" in preview_text
            assert "Manual review blockers: 1" in preview_text
            assert "Claims impacted: 1" in preview_text
            assert "Evidence Handoffs" in preview_text
            assert "Evidence handoffs: 1" in preview_text
            assert "Retaliation: Proof Leads | status Awaiting Complainant Record | preferred lane Evidence | quality target High Quality Document | proof lead complainant / evidence / Termination email held by complainant" in preview_text
            assert "Retaliation: Proof Leads | action Resolve Support Conflicts | artifact artifact-conflict" in preview_text
            assert "Pending Review Items" in preview_text
            assert "Pending review items: 1" in preview_text
            assert "Retaliation: Proof Leads | action Await Operator Confirmation | artifact artifact-pending" in preview_text
            assert "Packet blocking covered: 0.50" in preview_text
            assert "Packet credible support: 0.50" in preview_text
            assert "Packet draft ready: 0.00" in preview_text
            assert "Packet parse quality: 0.00" in preview_text
            assert "Packet review escalations: 0.50" in preview_text
            assert "Packet escalations: 1" in preview_text
            assert "Packet proof readiness: 0.23" in preview_text
            assert "Packet unresolved without path: 1" in preview_text
            assert "Packet completion ready: no" in preview_text
            assert "Packet temporal facts: 2" in preview_text
            assert "Packet temporal relations: 1" in preview_text
            assert "Packet temporal issues: 1" in preview_text
            assert "Packet temporal ready elements: 0" in preview_text
            assert "Packet temporal warnings: 1" in preview_text
            assert "Alignment chronology tasks: 1" in preview_text
            assert "Alignment chronology targeted: 1" in preview_text
            assert "Alignment chronology status: Partial=1" in preview_text
            assert "Alignment chronology blockers: Retaliation chronology still needs documentary sequencing for the proof lead bundle.=1" in preview_text
            assert "Alignment chronology handoffs: Awaiting Complainant Record=1" in preview_text
            assert "Packet chronology tasks: 1" in preview_text
            assert "Packet chronology targeted: 1" in preview_text
            assert "Packet chronology status: Partial=1" in preview_text
            assert "Packet chronology blockers: Retaliation chronology still needs documentary sequencing for the proof lead bundle.=1" in preview_text
            assert "Packet chronology handoffs: Awaiting Complainant Record=1" in preview_text
            normalized_preview_text = preview_text.lower()
            assert "intake summary handoff" in normalized_preview_text
            assert "Status" in preview_text
            assert "Pending" in preview_text
            assert "Complainant Confirmed" in preview_text
            assert "no" in preview_text
            assert "Summary snapshot 1" in preview_text
            assert "Snapshot scope: candidate claims 2 | canonical facts 1 | proof leads 1" in preview_text
            assert "Confirm intake summary" in preview_text
            assert "Confirmation records the latest intake summary snapshot before evidence marshalling continues." in preview_text

            browser.close()


def test_document_builder_smoke_routes_workflow_priority_back_to_manual_review():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    next_action_summary = {
        "next_action": {
            "action": "resolve_support_conflicts",
            "claim_type": "retaliation",
            "claim_element_id": "retaliation:3",
            "support_status": "contradicted",
        },
        "contradiction_summary": {"count": 1},
        "question_candidate_summary": {"count": 2},
        "claim_support_packet_summary": {
            "claim_support_reviewable_escalation_count": 1,
            "proof_readiness_score": 0.45,
        },
    }
    payload = {
        "generated_at": "2026-03-16T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"status": "warning", "sections": {}, "claims": [], "warning_count": 1},
        "filing_checklist": [],
        "review_links": {
            "dashboard_url": "/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link",
            "intake_case_summary": next_action_summary,
            "intake_status": {
                "current_phase": "evidence",
                "score": 0.74,
                "remaining_gap_count": 0,
                "contradiction_count": 1,
                "ready_to_advance": False,
                "blockers": ["manual_review_pending"],
                "contradictions": [],
            },
        },
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.5,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "evidence",
                "score": 0.74,
                "remaining_gap_count": 0,
                "contradiction_count": 1,
                "ready_to_advance": False,
                "blockers": ["manual_review_pending"],
                "contradictions": [],
            },
            "intake_case_summary": next_action_summary,
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for document workflow-priority manual review coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document?claim_type=retaliation&user_id=browser-smoke-text-link")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => document.getElementById('document-workflow-priority') !== null"
                )

                workflow_text = page.locator("#document-workflow-priority").inner_text()

                assert "workflow priority" in workflow_text.lower()
                assert "Resolve support conflicts before drafting" in workflow_text
                assert "recommended action: resolve_support_conflicts" in workflow_text
                assert "focus claim: retaliation" in workflow_text.lower()
                assert "packet escalations: 1" in workflow_text

                page.click("#document-workflow-action-link")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "claim_type=retaliation" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.parametrize(
    (
        "action",
        "title_text",
        "expected_section",
        "expected_support_kind",
        "expected_filter",
        "expected_sort",
        "expected_focus_label",
        "expected_lane_label",
    ),
    [
        (
            "address_gaps",
            "Resolve intake gaps before drafting",
            "summary_of_facts",
            "evidence",
            "active",
            "newest_first",
            "Summary Of Facts",
            "Evidence",
        ),
        (
            "continue_denoising",
            "Continue intake denoising before drafting",
            "summary_of_facts",
            "evidence",
            "active",
            "newest_first",
            "Summary Of Facts",
            "Evidence",
        ),
        (
            "build_knowledge_graph",
            "Review intake graph inputs before drafting",
            "summary_of_facts",
            "evidence",
            "active",
            "newest_first",
            "Summary Of Facts",
            "Evidence",
        ),
        (
            "build_dependency_graph",
            "Review dependency inputs before drafting",
            "chronology",
            "evidence",
            "active",
            "newest_first",
            "Chronology",
            "Evidence",
        ),
        (
            "build_legal_graph",
            "Review legal graph inputs before drafting",
            "claims_for_relief",
            "authority",
            "manual_review",
            "manual_review_first",
            "Claims For Relief",
            "Authority",
        ),
        (
            "perform_neurosymbolic_matching",
            "Review matching inputs before drafting",
            "claims_for_relief",
            "authority",
            "manual_review",
            "manual_review_first",
            "Claims For Relief",
            "Authority",
        ),
    ],
)
def test_document_builder_smoke_routes_workflow_priority_to_focused_review_surface(
    action,
    title_text,
    expected_section,
    expected_support_kind,
    expected_filter,
    expected_sort,
    expected_focus_label,
    expected_lane_label,
):
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    next_action_summary = {
        "next_action": {
            "action": action,
            "claim_type": "retaliation",
        },
        "contradiction_summary": {"count": 1},
        "question_candidate_summary": {"count": 2},
        "claim_support_packet_summary": {
            "proof_readiness_score": 0.45,
        },
    }
    payload = {
        "generated_at": "2026-03-16T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"status": "warning", "sections": {}, "claims": [], "warning_count": 1},
        "filing_checklist": [],
        "review_links": {
            "dashboard_url": "/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link",
            "intake_case_summary": next_action_summary,
            "intake_status": {
                "current_phase": "formalization",
                "score": 0.74,
                "remaining_gap_count": 0,
                "contradiction_count": 1,
                "ready_to_advance": False,
                "blockers": ["review_inputs_pending"],
                "contradictions": [],
            },
        },
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.5,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "formalization",
                "score": 0.74,
                "remaining_gap_count": 0,
                "contradiction_count": 1,
                "ready_to_advance": False,
                "blockers": ["review_inputs_pending"],
                "contradictions": [],
            },
            "intake_case_summary": next_action_summary,
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for document workflow-priority focused review coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document?claim_type=retaliation&user_id=browser-smoke-text-link")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => document.getElementById('document-workflow-priority') !== null"
                )

                workflow_text = page.locator("#document-workflow-priority").inner_text()

                assert title_text in workflow_text
                assert f"recommended action: {action}" in workflow_text

                page.click("#document-workflow-action-link")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )
                page.wait_for_function(
                    f"() => document.getElementById('section-focus-chip-row').textContent.includes('{expected_focus_label}')"
                )

                focus_chips = page.locator("#section-focus-chip-row").inner_text()
                prefill_context = page.locator("#prefill-context-line").inner_text()

                assert f"section={expected_section}" in page.url
                assert f"follow_up_support_kind={expected_support_kind}" in page.url
                assert f"alignment_task_update_filter={expected_filter}" in page.url
                if expected_sort == "newest_first":
                    assert "alignment_task_update_sort=" not in page.url
                else:
                    assert f"alignment_task_update_sort={expected_sort}" in page.url
                assert page.locator("#support-kind").input_value() == expected_support_kind
                assert page.locator("#alignment-task-update-sort").input_value() == expected_sort
                assert expected_focus_label in focus_chips
                assert f"Focused lane: {expected_lane_label}." in prefill_context

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_document_builder_smoke_routes_workflow_priority_to_support_packet_review():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    next_action_summary = {
        "next_action": {
            "action": "build_claim_support_packets",
            "claim_type": "retaliation",
        },
        "contradiction_summary": {"count": 1},
        "question_candidate_summary": {"count": 1},
        "claim_support_packet_summary": {
            "proof_readiness_score": 0.45,
        },
    }
    payload = {
        "generated_at": "2026-03-16T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"status": "warning", "sections": {}, "claims": [], "warning_count": 1},
        "filing_checklist": [],
        "review_links": {
            "dashboard_url": "/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link",
            "intake_case_summary": next_action_summary,
            "intake_status": {
                "current_phase": "evidence",
                "score": 0.74,
                "remaining_gap_count": 0,
                "contradiction_count": 1,
                "ready_to_advance": False,
                "blockers": ["packet_build_pending"],
                "contradictions": [],
            },
        },
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.5,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "evidence",
                "score": 0.74,
                "remaining_gap_count": 0,
                "contradiction_count": 1,
                "ready_to_advance": False,
                "blockers": ["packet_build_pending"],
                "contradictions": [],
            },
            "intake_case_summary": next_action_summary,
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for support packet review routing coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document?claim_type=retaliation&user_id=browser-smoke-text-link")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => document.getElementById('document-workflow-priority') !== null"
                )

                workflow_text = page.locator("#document-workflow-priority").inner_text()

                assert "Build support packets before drafting" in workflow_text
                assert "recommended action: build_claim_support_packets" in workflow_text

                page.click("#document-workflow-action-link")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "claim_type=retaliation" in page.url
                assert "follow_up_support_kind=evidence" in page.url
                assert "alignment_task_update_filter=active" in page.url
                assert "alignment_task_update_sort=" not in page.url
                assert page.locator("#claim-type").input_value() == "retaliation"
                assert page.locator("#support-kind").input_value() == "evidence"
                assert page.locator("#alignment-task-update-sort").input_value() == "newest_first"
                assert "Opened from document workflow." in page.locator("#prefill-context-line").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_document_builder_smoke_marks_complete_evidence_as_ready_for_drafting():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    next_action_summary = {
        "next_action": {
            "action": "complete_evidence",
            "claim_type": "retaliation",
        },
        "contradiction_summary": {"count": 0},
        "question_candidate_summary": {"count": 0},
        "claim_support_packet_summary": {
            "proof_readiness_score": 0.94,
        },
    }
    payload = {
        "generated_at": "2026-03-16T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"status": "ready", "sections": {}, "claims": [], "warning_count": 0},
        "filing_checklist": [],
        "review_links": {
            "dashboard_url": "/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link",
            "intake_case_summary": next_action_summary,
            "intake_status": {
                "current_phase": "evidence",
                "score": 1.0,
                "remaining_gap_count": 0,
                "contradiction_count": 0,
                "ready_to_advance": True,
                "blockers": [],
                "contradictions": [],
            },
        },
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.5,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "evidence",
                "score": 1.0,
                "remaining_gap_count": 0,
                "contradiction_count": 0,
                "ready_to_advance": True,
                "blockers": [],
                "contradictions": [],
            },
            "intake_case_summary": next_action_summary,
        },
    }

    app = _build_document_browser_smoke_app()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.goto(f"{base_url}/document?claim_type=retaliation&user_id=browser-smoke-text-link")
            page.evaluate("payload => window.renderPreview(payload)", payload)
            page.wait_for_function(
                "() => document.getElementById('document-workflow-priority') !== null"
            )

            workflow_card = page.locator("#document-workflow-priority")
            workflow_text = workflow_card.inner_text()

            assert workflow_card.get_attribute("data-status") == "ready"
            assert "Evidence is ready for formal drafting" in workflow_text
            assert "recommended action: complete_evidence" in workflow_text
            assert "focus claim: retaliation" in workflow_text.lower()
            assert "proof readiness: 0.94" in workflow_text
            assert "Open Review Dashboard" in workflow_text

            browser.close()


def test_document_builder_smoke_marks_generate_formal_complaint_as_current_priority():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    next_action_summary = {
        "next_action": {
            "action": "generate_formal_complaint",
            "claim_type": "retaliation",
        },
        "contradiction_summary": {"count": 0},
        "question_candidate_summary": {"count": 0},
        "claim_support_packet_summary": {
            "proof_readiness_score": 0.98,
        },
    }
    payload = {
        "generated_at": "2026-03-16T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"status": "ready", "sections": {}, "claims": [], "warning_count": 0},
        "filing_checklist": [],
        "review_links": {
            "dashboard_url": "/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link",
            "intake_case_summary": next_action_summary,
            "intake_status": {
                "current_phase": "formalization",
                "score": 1.0,
                "remaining_gap_count": 0,
                "contradiction_count": 0,
                "ready_to_advance": True,
                "blockers": [],
                "contradictions": [],
            },
        },
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.5,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "formalization",
                "score": 1.0,
                "remaining_gap_count": 0,
                "contradiction_count": 0,
                "ready_to_advance": True,
                "blockers": [],
                "contradictions": [],
            },
            "intake_case_summary": next_action_summary,
        },
    }

    app = _build_document_browser_smoke_app()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.goto(f"{base_url}/document?claim_type=retaliation&user_id=browser-smoke-text-link")
            page.evaluate("payload => window.renderPreview(payload)", payload)
            page.wait_for_function(
                "() => document.getElementById('document-workflow-priority') !== null"
            )

            workflow_card = page.locator("#document-workflow-priority")
            workflow_text = workflow_card.inner_text()

            assert workflow_card.get_attribute("data-status") == "ready"
            assert "Drafting is the current workflow priority" in workflow_text
            assert "recommended action: generate_formal_complaint" in workflow_text
            assert "focus claim: retaliation" in workflow_text.lower()
            assert "proof readiness: 0.98" in workflow_text
            assert "Open Review Dashboard" in workflow_text

            browser.close()


def test_claim_support_review_dashboard_smoke_renders_intake_evidence_alignment():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for intake-evidence alignment smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                intake_status = page.locator("#intake-status-chips").inner_text()
                intake_readiness = page.locator("#intake-readiness-criteria-chips").inner_text()
                intake_claims = page.locator("#intake-case-claim-chips").inner_text()
                intake_claim_summary = page.locator("#intake-claim-summary-chips").inner_text()
                intake_context = page.locator("#intake-context-chips").inner_text()
                timeline_summary = page.locator("#intake-timeline-summary-chips").inner_text()
                timeline_relations = page.locator("#intake-timeline-relation-list").inner_text()
                intake_facts = page.locator("#intake-canonical-fact-list").inner_text()
                intake_proof_leads = page.locator("#intake-proof-lead-chips").inner_text()
                alignment_summary = page.locator("#intake-evidence-alignment-summary-list").inner_text()
                alignment_tasks = page.locator("#alignment-evidence-task-list").inner_text()
                manual_review_summary = page.locator("#alignment-task-manual-review-summary").inner_text()
                manual_review_list = page.locator("#alignment-task-manual-review-list").inner_text()
                alignment_updates = page.locator("#alignment-task-update-list").inner_text()
                alignment_update_filter_summary = page.locator("#alignment-task-update-filter-summary").inner_text()
                packet_summary = page.locator("#claim-support-packet-summary-chips").inner_text()
                reasoning_summary = page.locator("#claim-reasoning-summary-chips").inner_text()
                reasoning_flagged = page.locator("#claim-reasoning-flagged-list").inner_text()
                task_filter_summary = page.locator("#task-filter-summary").inner_text()
                task_summary = page.locator("#task-summary-chips").inner_text()
                follow_up_tasks = page.locator("#task-list").inner_text()
                history_filter_summary = page.locator("#history-filter-summary").inner_text()
                history_summary = page.locator("#history-summary-chips").inner_text()
                follow_up_history = page.locator("#history-list").inner_text()

                assert "phase: intake" in intake_status
                assert "score: 0.41" in intake_status
                assert "remaining gaps: 2" in intake_status
                assert "ready Case Theory Coherent" in intake_readiness
                assert "ready Minimum Proof Path Present" in intake_readiness
                assert "needs Claim Disambiguation Resolved" in intake_readiness
                assert "candidate claims: 2" in intake_readiness
                assert "canonical facts: 1" in intake_readiness
                assert "proof leads: 1" in intake_readiness
                assert "claim: Retaliation" in intake_claims
                assert "confidence: 0.87" in intake_claims
                assert "ambiguity: Timing Overlap" in intake_claims
                assert "claim: Wrongful Termination" in intake_claims
                assert "claim count: 2" in intake_claim_summary
                assert "average confidence: 0.83" in intake_claim_summary
                assert "leading claim: Retaliation" in intake_claim_summary
                assert "leading confidence: 0.87" in intake_claim_summary
                assert "ambiguity flags: 1" in intake_claim_summary
                assert "ambiguous claims: 1" in intake_claim_summary
                assert "claim disambiguation: needed" in intake_claim_summary
                assert "Timing Overlap: 1" in intake_claim_summary
                assert "timeline anchors: 1" in intake_context
                assert "harm profile: Economic" in intake_context
                assert "remedy profile: Monetary" in intake_context
                assert "relations: 1" in timeline_summary
                assert "timeline events: 2" in timeline_summary
                assert "ordered facts: 1" in timeline_summary
                assert "unsequenced facts: 1" in timeline_summary
                assert "partial order ready: no" in timeline_summary
                assert "Before: 1" in timeline_summary
                assert "Timeline consistency warnings" in timeline_relations
                assert "Some timeline facts only express relative ordering and still need anchoring." in timeline_relations
                assert "Timeline relation timeline_relation_001" in timeline_relations
                assert "fact_001 before fact_termination" in timeline_relations
                assert "confidence: high" in timeline_relations
                assert "source date: 2026-02-03" in timeline_relations
                assert "target date: 2026-02-10" in timeline_relations
                assert "corroboration-required contradictions: 1" in intake_readiness
                assert "contradiction lanes: Request Document=1" in intake_readiness
                assert "lane: Request Document" in page.locator("#intake-contradiction-list").inner_text()
                assert "affected elements: Retaliation:3" in page.locator("#intake-contradiction-list").inner_text()
                assert "Canonical Fact Intake Intent" in intake_facts
                assert "canonical fact objectives: Establish Chronology=1" in intake_facts
                assert "proof lead objectives: Identify Supporting Evidence=1" in intake_proof_leads
                assert "Cross-phase element alignment for retaliation" in alignment_summary
                assert "aligned retaliation:1: supported" in alignment_summary
                assert "intake only: retaliation:3" in alignment_summary
                assert "evidence only: retaliation:2" in alignment_summary
                assert "Alignment task for retaliation" in alignment_tasks
                assert "evidence action fill_evidence_gaps" in alignment_tasks
                assert "element: retaliation:3" in alignment_tasks
                assert "label: Causal connection" in alignment_tasks
                assert "blocking: yes" in alignment_tasks
                assert "preferred lane: evidence" in alignment_tasks
                assert "fallback lane: authority" in alignment_tasks
                assert "fallback lane: testimony" in alignment_tasks
                assert "quality target: high_quality_document" in alignment_tasks
                assert "priority: high" in alignment_tasks
                assert "resolution: still_open" in alignment_tasks
                assert "Alignment chronology summary" in alignment_tasks
                assert "Chronology tasks: 1" in alignment_tasks
                assert "Chronology targeted: 1" in alignment_tasks
                assert "Chronology status: Partial=1" in alignment_tasks
                assert "Chronology blockers: Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.=1" in alignment_tasks
                assert "Chronology handoffs: Still Open=1" in alignment_tasks
                assert "chronology follow-up" in alignment_tasks
                assert "chronology targeted" in alignment_tasks
                assert "temporal rule: Partial" in alignment_tasks
                assert "chronology profile: retaliation_temporal_profile_v1" in alignment_tasks
                assert "chronology blocker: Retaliation causation lacks a clear temporal ordering from protected activity to adverse action." in alignment_tasks
                assert "chronology follow-up: Clarify whether the protected activity occurred before the adverse action." in alignment_tasks
                assert "manual review blockers: 1" in manual_review_summary
                assert "claims impacted: 1" in manual_review_summary
                assert "Manual review blocker for retaliation" in manual_review_list
                assert "action: resolve_support_conflicts" in manual_review_list
                assert "current support: contradicted" in manual_review_list
                assert "artifact: artifact-conflict" in manual_review_list
                assert "latest evidence event: 2" in manual_review_list
                assert "Load Into Resolution Form" in manual_review_list
                assert "Alignment update for retaliation" in alignment_updates
                assert "resolution: still_open" in alignment_updates
                assert "resolution: needs_manual_review" in alignment_updates
                assert "evidence event: 1" in alignment_updates
                assert "evidence event: 2" in alignment_updates
                assert "artifact: artifact-conflict" in alignment_updates
                assert "filter: all" in alignment_update_filter_summary
                assert "sort: newest_first" in alignment_update_filter_summary
                assert "visible updates: 2" in alignment_update_filter_summary
                assert alignment_updates.index("evidence event: 2") < alignment_updates.index("evidence event: 1")
                assert "packet blocking covered: 0.50" in packet_summary
                assert "packet credible support: 0.50" in packet_summary
                assert "packet draft ready: 0.00" in packet_summary
                assert "packet parse quality: 0.00" in packet_summary
                assert "packet review escalations: 0.50" in packet_summary
                assert "packet escalations: 1" in packet_summary
                assert "packet unresolved without path: 1" in packet_summary
                assert "packet proof readiness: 0.23" in packet_summary
                assert "packet completion ready: no" in packet_summary
                assert "packet temporal facts: 2" in packet_summary
                assert "packet temporal relations: 1" in packet_summary
                assert "packet temporal issues: 1" in packet_summary
                assert "packet temporal ready elements: 0" in packet_summary
                assert "packet temporal warnings: 1" in packet_summary
                assert "packet chronology tasks: 1" in packet_summary
                assert "packet chronology targeted: 1" in packet_summary
                assert "packet chronology status: Partial=1" in packet_summary
                assert "packet chronology blockers: Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.=1" in packet_summary
                assert "packet chronology handoffs: Still Open=1" in packet_summary
                assert "Bridge elements: 1" in reasoning_summary
                assert "Bridge available: 1" in reasoning_summary
                assert "TDFOL formulas: 2" in reasoning_summary
                assert "DCEC formulas: 1" in reasoning_summary
                assert "Formalism: tdfol_dcec_bridge_v1" in reasoning_summary
                assert "Mode: temporal_bridge" in reasoning_summary
                assert "Temporal facts: 2" in reasoning_summary
                assert "Temporal relations: 1" in reasoning_summary
                assert "Temporal issues: 1" in reasoning_summary
                assert "Temporal warnings: 1" in reasoning_summary
                assert "Temporal rule profiles: 1" in reasoning_summary
                assert "Temporal proof bundles: 1" in reasoning_summary
                assert "Formalism: tdfol_dcec_bridge_v1" in reasoning_summary
                assert "Mode: temporal_bridge" in reasoning_summary
                assert "Temporal proof handoff" in reasoning_flagged
                assert "facts 2" in reasoning_flagged
                assert "relations 1" in reasoning_flagged
                assert "issues 1" in reasoning_flagged
                assert "warnings 1" in reasoning_flagged
                assert "rule profiles 1" in reasoning_flagged
                assert "rule partial 1" in reasoning_flagged
                assert "proof bundles 1" in reasoning_flagged
                assert "bundle Partial 1" in reasoning_flagged
                assert "Before 1" in reasoning_flagged
                assert "Claim-level hybrid bridge" in reasoning_flagged
                assert "Protected activity" in reasoning_flagged
                assert "temporal rule Partial" in reasoning_flagged
                assert "rule frame retaliation_temporal_frame" in reasoning_flagged
                assert "proof bundle Partial" in reasoning_flagged
                assert "formalism tdfol_dcec_bridge_v1" in reasoning_flagged
                assert "mode temporal_bridge" in reasoning_flagged
                assert "TDFOL preview" in reasoning_flagged
                assert "DCEC preview" in reasoning_flagged
                assert "Temporal rule blockers" in reasoning_flagged
                assert "Temporal rule follow-ups" in reasoning_flagged
                assert "Temporal proof bundle TDFOL preview" in reasoning_flagged
                assert "Temporal proof bundle DCEC preview" in reasoning_flagged
                assert "bridge path ipfs_datasets_py.ipfs_datasets_py.processors.legal_data.reasoner.hybrid_v2_blueprint" in reasoning_flagged

                page.locator("#claim-reasoning-flagged-list summary").filter(has_text="Temporal relation preview").first.click()
                page.locator("#claim-reasoning-flagged-list summary").filter(has_text="Temporal warnings").first.click()
                page.locator("#claim-reasoning-flagged-list summary").filter(has_text="TDFOL preview").first.click()
                page.locator("#claim-reasoning-flagged-list summary").filter(has_text="DCEC preview").first.click()
                page.locator("#claim-reasoning-flagged-list summary").filter(has_text="Temporal rule blockers").first.click()
                page.locator("#claim-reasoning-flagged-list summary").filter(has_text="Temporal rule follow-ups").first.click()
                page.locator("#claim-reasoning-flagged-list summary").filter(has_text="Temporal proof bundle TDFOL preview").first.click()
                page.locator("#claim-reasoning-flagged-list summary").filter(has_text="Temporal proof bundle DCEC preview").first.click()

                assert page.locator("#claim-reasoning-flagged-list").get_by_text("fact_001 before fact_termination").first.is_visible()
                assert page.locator("#claim-reasoning-flagged-list").get_by_text(
                    "Some timeline facts only express relative ordering and still need anchoring."
                ).first.is_visible()
                assert page.locator("#claim-reasoning-flagged-list").get_by_text(
                    "Retaliation causation lacks a clear temporal ordering from protected activity to adverse action."
                ).first.is_visible()
                assert page.locator("#claim-reasoning-flagged-list").get_by_text(
                    "Clarify With Complainant: Clarify whether the protected activity occurred before the adverse action."
                ).first.is_visible()
                assert page.locator("#claim-reasoning-flagged-list").get_by_text("Before(fact_1,fact_2)").first.is_visible()
                assert page.locator("#claim-reasoning-flagged-list").get_by_text(
                    "forall t (AtTime(t,t_2026_03_10) -> Fact(fact_1,t))"
                ).first.is_visible()
                assert page.locator("#claim-reasoning-flagged-list").get_by_text("Happens(fact_1,t_2026_03_10)").first.is_visible()
                assert page.locator("#claim-reasoning-flagged-list").get_by_text("ProtectedActivity(fact_001)").first.is_visible()
                assert page.locator("#claim-reasoning-flagged-list").get_by_text("AdverseAction(fact_termination)").first.is_visible()
                assert page.locator("#claim-reasoning-flagged-list").get_by_text("Happens(fact_termination,t_2026_03_24)").first.is_visible()
                assert "Tasks: 2" in task_summary
                assert "Chronology tasks: 1" in task_summary
                assert "Chronology targeted: 1" in task_summary
                assert "Primary gaps: Event sequence=1, Manager knowledge=1" in task_summary
                assert "Gap coverage: Event sequence=2, Manager knowledge=1" in task_summary
                assert "Covered facts: Protected activity=1" in task_summary
                assert "Handoffs: Awaiting Complainant Record=1, Awaiting Testimony=1" in task_summary
                assert "Chronology status: partial=1" in task_summary
                assert "Chronology blockers: Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.=1" in task_summary
                assert "Chronology handoffs: Awaiting Testimony=1" in task_summary
                assert "filter: all" in task_filter_summary
                assert "sort: section_focus" in task_filter_summary
                assert "visible tasks: 2" in task_filter_summary
                assert "Causal connection" in follow_up_tasks
                assert "handoff Awaiting Complainant Record" in follow_up_tasks
                assert "chronology follow-up" in follow_up_tasks
                assert "chronology targeted" in follow_up_tasks
                assert "handoff Awaiting Testimony" in follow_up_tasks
                assert "temporal rule Partial" in follow_up_tasks
                assert "chronology profile retaliation_temporal_profile_v1" in follow_up_tasks
                assert "chronology blocker: Retaliation causation lacks a clear temporal ordering from protected activity to adverse action." in follow_up_tasks
                assert "chronology follow-up: Clarify whether the protected activity occurred before the adverse action." in follow_up_tasks
                assert "quality target High Quality Document" in follow_up_tasks
                assert "proof lead complainant / evidence / Termination email held by complainant" in follow_up_tasks
                assert "proof lead complainant / testimony / Chronology clarification from complainant" in follow_up_tasks
                assert "primary gap Manager knowledge" in follow_up_tasks
                assert "gap: Manager knowledge" in follow_up_tasks
                assert "gap: Event sequence" in follow_up_tasks
                assert "covered facts 1" in follow_up_tasks
                assert "authority program element_definition_search" in follow_up_tasks
                assert "Primary gaps: Event sequence=1, Manager knowledge=1" in history_summary
                assert "Gap coverage: Event sequence=2, Manager knowledge=1" in history_summary
                assert "Covered facts: Protected activity=1" in history_summary
                assert "Handoffs: Awaiting Testimony=1" in history_summary
                assert "Chronology status: partial=1" in history_summary
                assert "Chronology blockers: Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.=1" in history_summary
                assert "Chronology handoffs: Awaiting Testimony=1" in history_summary
                assert "Outcomes:" in history_summary
                assert "Resolution Handoff=1" in history_summary
                assert "Search Exhausted=1" in history_summary
                assert "filter: all" in history_filter_summary
                assert "sort: section_focus" in history_filter_summary
                assert "visible history: 2" in history_filter_summary
                assert "Causal connection" in follow_up_history
                assert "chronology follow-up" in follow_up_history
                assert "chronology targeted" in follow_up_history
                assert "temporal rule: Partial" in follow_up_history
                assert "chronology profile: retaliation_temporal_profile_v1" in follow_up_history
                assert "chronology blocker: Retaliation causation lacks a clear temporal ordering from protected activity to adverse action." in follow_up_history
                assert "chronology follow-up: Clarify whether the protected activity occurred before the adverse action." in follow_up_history
                assert "resolution: Awaiting Testimony" in follow_up_history
                assert "resolution: Search Exhausted" in follow_up_history
                assert "quality target: High Quality Document" in follow_up_history
                assert "proof lead: complainant / evidence / Termination email held by complainant" in follow_up_history
                assert "proof lead: complainant / testimony / Chronology clarification from complainant" in follow_up_history
                assert "primary gap: Manager knowledge" in follow_up_history
                assert "gap: Manager knowledge" in follow_up_history
                assert "gap: Event sequence" in follow_up_history
                assert "covered facts: 1" in follow_up_history
                assert "program: element_definition_search" in follow_up_history

                page.select_option("#follow-up-task-filter", "chronology_only")
                page.wait_for_function(
                    "() => document.getElementById('task-filter-summary').textContent.includes('filter: chronology_only')"
                )

                filtered_task_summary = page.locator("#task-filter-summary").inner_text()
                filtered_follow_up_tasks = page.locator("#task-list").inner_text()

                assert "follow_up_task_filter=chronology_only" in page.url
                assert "visible tasks: 1" in filtered_task_summary
                assert "chronology follow-up" in filtered_follow_up_tasks
                assert "chronology profile retaliation_temporal_profile_v1" in filtered_follow_up_tasks
                assert "authority program element_definition_search" not in filtered_follow_up_tasks
                assert "handoff Awaiting Complainant Record" not in filtered_follow_up_tasks

                page.select_option("#follow-up-history-filter", "chronology_only")
                page.wait_for_function(
                    "() => document.getElementById('history-filter-summary').textContent.includes('filter: chronology_only')"
                )

                filtered_history_summary = page.locator("#history-filter-summary").inner_text()
                filtered_follow_up_history = page.locator("#history-list").inner_text()

                assert "follow_up_history_filter=chronology_only" in page.url
                assert "visible history: 1" in filtered_history_summary
                assert "chronology follow-up" in filtered_follow_up_history
                assert "resolution: Awaiting Testimony" in filtered_follow_up_history
                assert "Search Exhausted" not in filtered_follow_up_history

                page.reload()
                page.wait_for_function(
                    "() => document.getElementById('task-filter-summary').textContent.includes('filter: chronology_only') && document.getElementById('history-filter-summary').textContent.includes('filter: chronology_only')"
                )

                reloaded_task_filter_summary = page.locator("#task-filter-summary").inner_text()
                reloaded_history_filter_summary = page.locator("#history-filter-summary").inner_text()

                assert page.locator("#follow-up-task-filter").input_value() == "chronology_only"
                assert page.locator("#follow-up-history-filter").input_value() == "chronology_only"
                assert "visible tasks: 1" in reloaded_task_filter_summary
                assert "visible history: 1" in reloaded_history_filter_summary

                page.select_option("#follow-up-task-filter", "all")
                page.select_option("#follow-up-history-filter", "all")
                page.wait_for_function(
                    "() => document.getElementById('task-filter-summary').textContent.includes('filter: all') && document.getElementById('history-filter-summary').textContent.includes('filter: all')"
                )

                page.locator("#alignment-task-manual-review-list").get_by_text("Load Into Resolution Form").click()

                assert page.locator("#resolution-element-id").input_value() == "retaliation:3"
                assert page.locator("#resolution-element-text").input_value() == "retaliation:3"
                assert page.locator("#resolution-status").input_value() == "resolved_supported"

                page.select_option("#alignment-task-update-filter", "manual_review")
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('filter: manual_review')"
                )

                filtered_alignment_updates = page.locator("#alignment-task-update-list").inner_text()
                filtered_alignment_summary = page.locator("#alignment-task-update-filter-summary").inner_text()

                assert "alignment_task_update_filter=manual_review" in page.url
                assert "visible updates: 1" in filtered_alignment_summary
                assert "resolution: needs_manual_review" in filtered_alignment_updates
                assert "evidence event: 2" in filtered_alignment_updates
                assert "artifact: artifact-conflict" in filtered_alignment_updates
                assert "resolution: still_open" not in filtered_alignment_updates
                assert "evidence event: 1" not in filtered_alignment_updates

                page.select_option("#alignment-task-update-filter", "all")
                page.select_option("#alignment-task-update-sort", "oldest_first")
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('sort: oldest_first')"
                )

                oldest_first_updates = page.locator("#alignment-task-update-list").inner_text()
                oldest_first_summary = page.locator("#alignment-task-update-filter-summary").inner_text()

                assert "alignment_task_update_sort=oldest_first" in page.url
                assert "sort: oldest_first" in oldest_first_summary
                assert oldest_first_updates.index("evidence event: 1") < oldest_first_updates.index("evidence event: 2")

                page.reload()
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('sort: oldest_first')"
                )

                reloaded_alignment_updates = page.locator("#alignment-task-update-list").inner_text()
                reloaded_alignment_summary = page.locator("#alignment-task-update-filter-summary").inner_text()
                assert page.locator("#alignment-task-update-filter").input_value() == "all"
                assert page.locator("#alignment-task-update-sort").input_value() == "oldest_first"
                assert "alignment_task_update_sort=oldest_first" in page.url
                assert "sort: oldest_first" in reloaded_alignment_summary
                assert reloaded_alignment_updates.index("evidence event: 1") < reloaded_alignment_updates.index("evidence event: 2")

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_confirms_intake_summary():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for intake summary confirmation smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "Latest intake summary snapshot is awaiting complainant confirmation." in page.locator("#confirm-intake-summary-status").inner_text()
                page.fill("#confirm-intake-summary-note", "Reviewed with complainant for evidence handoff")
                page.click("#confirm-intake-summary-button")

                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Intake summary confirmed.')"
                )
                page.wait_for_function(
                    "() => document.getElementById('confirm-intake-summary-status').textContent.includes('Intake summary confirmed')"
                )

                intake_status = page.locator("#intake-status-chips").inner_text()
                intake_readiness = page.locator("#intake-readiness-criteria-chips").inner_text()
                intake_context = page.locator("#intake-context-chips").inner_text()
                confirmation_status = page.locator("#confirm-intake-summary-status").inner_text()
                browser.close()

        assert "summary confirmation: confirmed" in intake_status
        assert "ready Complainant Summary Confirmed" in intake_readiness
        assert "summary confirmation: Confirmed" in intake_context
        assert "note: Reviewed with complainant for evidence handoff" in confirmation_status
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_reviews_manual_conflicts_from_next_action_banner():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for manual-conflict next-action smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status_payload = mediator.get_three_phase_status.return_value
        status_payload["next_action"] = {
            "action": "resolve_support_conflicts",
            "claim_type": "retaliation",
            "claim_element_id": "retaliation:3",
            "claim_element_label": "Causal connection",
            "support_status": "contradicted",
            "recommended_actions": ["request_document", "manual_review"],
        }

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                next_action_banner = page.locator("#intake-next-action-banner").inner_text()

                assert "Resolve support conflicts" in next_action_banner
                assert "recommended action: resolve_support_conflicts" in next_action_banner
                assert "manual review blockers: 1" in next_action_banner
                assert "packet escalations: 1" in next_action_banner
                assert "focus claim: Retaliation" in next_action_banner
                assert "focus element: Retaliation:3" in next_action_banner
                assert "support status: Contradicted" in next_action_banner
                assert "recommended lane: Request Document" in next_action_banner

                page.click("#intake-next-action-review-conflicts")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Showing manual-review conflicts that are blocking evidence completion.')"
                )
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('filter: manual_review') && document.getElementById('alignment-task-update-filter-summary').textContent.includes('sort: manual_review_first')"
                )

                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url

                page.click("#intake-next-action-prefill-resolution")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Resolution form prefilled from blocking evidence conflict.')"
                )

                assert page.locator("#resolution-element-id").input_value() == "retaliation:3"
                assert page.locator("#resolution-element-text").input_value() == "Causal connection"
                assert page.locator("#resolution-status").input_value() == "resolved_supported"

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_filters_pending_review_alignment_updates():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for pending-review filter smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status = mediator.get_three_phase_status.return_value
        status["alignment_task_update_history"] = list(status.get("alignment_task_update_history") or []) + [
            {
                "task_id": "retaliation:retaliation:2:await_operator_confirmation",
                "claim_type": "retaliation",
                "claim_element_id": "retaliation:2",
                "claim_element_label": "Adverse action",
                "action": "await_operator_confirmation",
                "previous_support_status": "missing",
                "current_support_status": "partially_supported",
                "previous_missing_fact_bundle": ["Adverse action details"],
                "current_missing_fact_bundle": [],
                "resolution_status": "answered_pending_review",
                "status": "active",
                "evidence_artifact_id": "artifact-pending",
                "answer_preview": "Supervisor confirmed the demotion after the complaint.",
                "evidence_sequence": 1,
            }
        ]

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                pending_review_summary = page.locator("#alignment-task-pending-review-summary").inner_text()
                pending_review_list = page.locator("#alignment-task-pending-review-list").inner_text()

                assert "pending review items: 1" in pending_review_summary
                assert "claims impacted: 1" in pending_review_summary
                assert "Pending review item for retaliation" in pending_review_list
                assert "element: retaliation:2" in pending_review_list
                assert "action: await_operator_confirmation" in pending_review_list
                assert "current support: partially_supported" in pending_review_list
                assert "artifact: artifact-pending" in pending_review_list
                assert "latest evidence event: 1" in pending_review_list
                assert "Load Into Testimony Form" in pending_review_list
                assert "Load Into Document Form" in pending_review_list

                page.locator("#alignment-task-pending-review-list").get_by_text("Load Into Testimony Form").click()

                assert page.locator("#testimony-element-id").input_value() == "retaliation:2"
                assert page.locator("#testimony-element-text").input_value() == "Adverse action"
                assert page.locator("#testimony-narrative").input_value() == "Supervisor confirmed the demotion after the complaint."

                page.click("#clear-testimony-button")
                page.locator("#alignment-task-pending-review-list").get_by_text("Load Into Document Form").click()

                assert page.locator("#document-element-id").input_value() == "retaliation:2"
                assert page.locator("#document-element-text").input_value() == "Adverse action"
                assert page.locator("#document-label").input_value() == "Adverse action"
                assert page.locator("#document-text").input_value() == "Supervisor confirmed the demotion after the complaint."

                page.select_option("#alignment-task-update-filter", "pending_review")
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('filter: pending_review')"
                )

                filtered_alignment_updates = page.locator("#alignment-task-update-list").inner_text()
                filtered_alignment_summary = page.locator("#alignment-task-update-filter-summary").inner_text()

                assert "alignment_task_update_filter=pending_review" in page.url
                assert "visible updates: 1" in filtered_alignment_summary
                assert "ANSWERED, PENDING REVIEW" in filtered_alignment_updates
                assert "element: retaliation:2" in filtered_alignment_updates
                assert "artifact: artifact-pending" in filtered_alignment_updates
                assert "evidence event: 1" in filtered_alignment_updates
                assert "resolution: needs_manual_review" not in filtered_alignment_updates
                assert "resolution: still_open" not in filtered_alignment_updates

                page.select_option("#alignment-task-update-filter", "all")
                page.select_option("#alignment-task-update-sort", "pending_review_first")
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('sort: pending_review_first')"
                )

                pending_first_updates = page.locator("#alignment-task-update-list").inner_text()
                pending_first_summary = page.locator("#alignment-task-update-filter-summary").inner_text()

                assert "alignment_task_update_sort=pending_review_first" in page.url
                assert "sort: pending_review_first" in pending_first_summary
                assert pending_first_updates.index("artifact: artifact-pending") < pending_first_updates.index("artifact: artifact-conflict")
                assert pending_first_updates.index("artifact: artifact-pending") < pending_first_updates.index("artifact: artifact-open")

                page.reload()
                page.wait_for_function(
                    "() => document.getElementById('alignment-task-update-filter-summary').textContent.includes('sort: pending_review_first')"
                )

                reloaded_alignment_updates = page.locator("#alignment-task-update-list").inner_text()
                reloaded_alignment_summary = page.locator("#alignment-task-update-filter-summary").inner_text()
                assert page.locator("#alignment-task-update-filter").input_value() == "all"
                assert page.locator("#alignment-task-update-sort").input_value() == "pending_review_first"
                assert "alignment_task_update_sort=pending_review_first" in page.url
                assert "sort: pending_review_first" in reloaded_alignment_summary
                assert reloaded_alignment_updates.index("artifact: artifact-pending") < reloaded_alignment_updates.index("artifact: artifact-conflict")
                assert reloaded_alignment_updates.index("artifact: artifact-pending") < reloaded_alignment_updates.index("artifact: artifact-open")

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_reviews_intake_gaps_from_next_action_banner():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for intake gap banner smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status_payload = mediator.get_three_phase_status.return_value
        status_payload["alignment_promotion_drift_summary"] = {}
        status_payload["next_action"] = {
            "action": "address_gaps",
            "gaps": ["timeline", "manager_knowledge"],
            "intake_readiness_score": 0.41,
            "intake_blockers": ["collect_missing_support", "complainant_summary_confirmation_required"],
        }

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                next_action_banner = page.locator("#intake-next-action-banner").inner_text()

                assert "Review intake gaps" in next_action_banner
                assert "recommended action: address_gaps" in next_action_banner
                assert "gap count: 2" in next_action_banner
                assert "blockers: 2" in next_action_banner
                assert "contradictions: 1" in next_action_banner
                assert "question candidates: 0" in next_action_banner
                assert "readiness score: 0.41" in next_action_banner
                assert "gap: Timeline" in next_action_banner
                assert "gap: Manager Knowledge" in next_action_banner

                page.click("#intake-next-action-review-gaps")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Showing unresolved intake gaps and targeted questions.')"
                )
                page.wait_for_function(
                    "() => document.getElementById('section-focus-chip-row').textContent.includes('Summary Of Facts')"
                )

                focus_chips = page.locator("#section-focus-chip-row").inner_text()
                prefill_context = page.locator("#prefill-context-line").inner_text()

                assert "section=summary_of_facts" in page.url
                assert "follow_up_support_kind=evidence" in page.url
                assert "Summary Of Facts" in focus_chips
                assert "Evidence lane" in focus_chips
                assert "Focused lane: Evidence." in prefill_context

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_reviews_knowledge_graph_inputs_from_next_action_banner():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for knowledge-graph next-action smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status_payload = mediator.get_three_phase_status.return_value
        status_payload["next_action"] = {
            "action": "build_knowledge_graph",
            "intake_readiness_score": 0.41,
            "intake_blockers": ["missing_knowledge_graph"],
        }

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                next_action_banner = page.locator("#intake-next-action-banner").inner_text()

                assert "Build intake knowledge graph" in next_action_banner
                assert "recommended action: build_knowledge_graph" in next_action_banner
                assert "timeline anchors: 1" in next_action_banner
                assert "canonical facts: 1" in next_action_banner
                assert "question candidates: 0" in next_action_banner
                assert "readiness score: 0.41" in next_action_banner

                page.click("#intake-next-action-review-knowledge-graph")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Showing timeline and canonical fact inputs for intake graph building.')"
                )

                assert "Timeline Ordering" in page.locator("body").inner_text()
                assert page.locator("#intake-timeline-summary-chips").inner_text().count("timeline anchors") >= 0

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_reviews_dependency_inputs_from_next_action_banner():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for dependency-graph next-action smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status_payload = mediator.get_three_phase_status.return_value
        status_payload["next_action"] = {
            "action": "build_dependency_graph",
            "intake_readiness_score": 0.41,
            "intake_blockers": ["missing_dependency_graph"],
        }

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                next_action_banner = page.locator("#intake-next-action-banner").inner_text()

                assert "Build intake dependency graph" in next_action_banner
                assert "recommended action: build_dependency_graph" in next_action_banner
                assert "aligned elements: 1" in next_action_banner
                assert "alignment tasks: 1" in next_action_banner
                assert "contradictions: 1" in next_action_banner
                assert "readiness score: 0.41" in next_action_banner

                page.click("#intake-next-action-review-dependencies")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Showing alignment and contradiction inputs for dependency graph review.')"
                )

                assert "Cross-phase element alignment for retaliation" in page.locator("#intake-evidence-alignment-summary-list").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_reviews_denoising_queue_from_next_action_banner():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for denoising next-action smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status_payload = mediator.get_three_phase_status.return_value
        status_payload["next_action"] = {
            "action": "continue_denoising",
            "intake_readiness_score": 0.41,
            "intake_blockers": ["denoising_not_converged", "collect_missing_support"],
        }
        status_payload["question_candidate_summary"] = {
            "count": 2,
            "question_goal_counts": {"establish_element": 1, "identify_supporting_proof": 1},
            "phase1_section_counts": {"summary_of_facts": 2},
            "blocking_level_counts": {"blocking": 1, "non_blocking": 1},
        }

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                next_action_banner = page.locator("#intake-next-action-banner").inner_text()

                assert "Continue intake denoising" in next_action_banner
                assert "recommended action: continue_denoising" in next_action_banner
                assert "blockers: 2" in next_action_banner
                assert "contradictions: 1" in next_action_banner
                assert "question candidates: 2" in next_action_banner
                assert "readiness score: 0.41" in next_action_banner

                page.click("#intake-next-action-review-denoising")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Showing contradictions and targeted questions for continued intake denoising.')"
                )

                assert "Termination date conflicts with reported complaint timeline" in page.locator("#intake-contradiction-list").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_reviews_legal_graph_inputs_from_next_action_banner():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for legal-graph next-action smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status_payload = mediator.get_three_phase_status.return_value
        status_payload["next_action"] = {"action": "build_legal_graph"}
        status_payload["intake_legal_targeting_summary"] = {
            "claims": {
                "retaliation": {
                    "missing_requirement_count": 2,
                    "missing_requirement_names": ["Adverse action", "Causation"],
                    "missing_requirement_element_ids": ["retaliation:2", "retaliation:3"],
                    "mapped_candidates": [{"target_element_id": "retaliation:2"}],
                }
            }
        }
        status_payload["question_candidate_summary"] = {
            "count": 2,
            "candidates": [
                {"target_element_id": "retaliation:2", "question_goal": "establish_element"},
                {"target_element_id": "retaliation:3", "question_goal": "identify_supporting_proof"},
            ],
        }

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                next_action_banner = page.locator("#intake-next-action-banner").inner_text()

                assert "Build legal graph" in next_action_banner
                assert "recommended action: build_legal_graph" in next_action_banner
                assert "candidate claims: 2" in next_action_banner
                assert "targeted claims: 1" in next_action_banner
                assert "open legal elements: 2" in next_action_banner
                assert "question candidates: 2" in next_action_banner

                page.click("#intake-next-action-review-legal-graph")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Showing unresolved legal elements and question targets for legal graph review.')"
                )

                assert "Unresolved legal elements for retaliation" in page.locator("#intake-matching-summary-list").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_reviews_neurosymbolic_matching_from_next_action_banner():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for matching next-action smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status_payload = mediator.get_three_phase_status.return_value
        status_payload["next_action"] = {"action": "perform_neurosymbolic_matching"}
        status_payload["intake_matching_summary"] = {
            "claims": {
                "retaliation": {
                    "matcher_confidence": 0.52,
                    "missing_requirement_count": 2,
                    "missing_requirement_names": ["Adverse action", "Causation"],
                    "missing_requirement_element_ids": ["retaliation:2", "retaliation:3"],
                    "mapped_candidates": [
                        {"target_element_id": "retaliation:2"},
                        {"target_element_id": "retaliation:3"},
                    ],
                }
            }
        }
        status_payload["question_candidate_summary"] = {
            "count": 2,
            "candidates": [
                {"target_element_id": "retaliation:2", "question_goal": "establish_element"},
                {"target_element_id": "retaliation:3", "question_goal": "identify_supporting_proof"},
            ],
        }

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                next_action_banner = page.locator("#intake-next-action-banner").inner_text()

                assert "Perform neurosymbolic matching" in next_action_banner
                assert "recommended action: perform_neurosymbolic_matching" in next_action_banner
                assert "targeted claims: 1" in next_action_banner
                assert "open legal elements: 2" in next_action_banner
                assert "question candidates: 2" in next_action_banner

                page.click("#intake-next-action-review-matching")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Showing unresolved legal elements and question targets for neurosymbolic matching.')"
                )

                matching_text = page.locator("#intake-matching-summary-list").inner_text()
                assert "missing legal elements: 2" in matching_text
                assert "question target: retaliation:2" in matching_text

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_opens_formal_builder_from_generate_formal_complaint_banner():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for generate-formal-complaint next-action smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status_payload = mediator.get_three_phase_status.return_value
        status_payload["next_action"] = {"action": "generate_formal_complaint"}
        status_payload["claim_support_packet_summary"] = {
            **dict(status_payload.get("claim_support_packet_summary") or {}),
            "claim_count": 1,
            "element_count": 3,
            "draft_ready_element_ratio": 1.0,
            "proof_readiness_score": 0.98,
        }

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                next_action_banner = page.locator("#intake-next-action-banner").inner_text()

                assert "Generate formal complaint" in next_action_banner
                assert "recommended action: generate_formal_complaint" in next_action_banner
                assert "claims: 1" in next_action_banner
                assert "elements: 3" in next_action_banner
                assert "packet draft ready: 1.00" in next_action_banner
                assert "proof readiness: 0.98" in next_action_banner

                page.click("#intake-next-action-open-formal-generator")
                page.wait_for_url(f"{base_url}/document?claim_type=retaliation&user_id=browser-smoke-text-link")

                assert "Formal Complaint Builder" in page.locator("body").inner_text()
                assert "Generate Formal Complaint" in page.locator("body").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_reviews_evidence_gap_task_from_next_action_banner():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for evidence-gap next-action smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status_payload = mediator.get_three_phase_status.return_value
        status_payload["next_action"] = {
            "action": "fill_evidence_gaps",
            "claim_type": "retaliation",
            "claim_element_id": "retaliation:3",
            "claim_element_label": "Causal connection",
            "support_status": "missing",
            "alignment_tasks": list(status_payload.get("alignment_evidence_tasks") or []),
        }

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                next_action_banner = page.locator("#intake-next-action-banner").inner_text()

                assert "Fill evidence gaps" in next_action_banner
                assert "recommended action: fill_evidence_gaps" in next_action_banner
                assert "focus claim: Retaliation" in next_action_banner
                assert "focus element: Retaliation:3" in next_action_banner
                assert "support status: Missing" in next_action_banner
                assert "preferred lane: Evidence" in next_action_banner
                assert "quality target: High Quality Document" in next_action_banner
                assert "fallback lane: Authority" in next_action_banner
                assert "fallback lane: Testimony" in next_action_banner

                page.click("#intake-next-action-review-evidence-task")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Showing priority evidence task and preferred support lane.')"
                )

                assert "follow_up_support_kind=evidence" in page.url
                assert page.locator("#support-kind").input_value() == "evidence"
                assert "Alignment task for retaliation" in page.locator("#alignment-evidence-task-list").inner_text()
                assert "element: retaliation:3" in page.locator("#alignment-evidence-task-list").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_hands_off_complete_evidence_to_document_builder():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for complete-evidence handoff smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status_payload = mediator.get_three_phase_status.return_value
        status_payload["next_action"] = {
            "action": "complete_evidence",
            "recommended_actions": ["generate_formal_complaint"],
        }
        status_payload["claim_support_packet_summary"] = {
            **dict(status_payload.get("claim_support_packet_summary") or {}),
            "evidence_completion_ready": True,
            "proof_readiness_score": 0.94,
        }

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                next_action_banner = page.locator("#intake-next-action-banner").inner_text()

                assert "Begin formal complaint drafting" in next_action_banner
                assert "recommended action: complete_evidence" in next_action_banner
                assert "packet completion ready: yes" in next_action_banner
                assert "proof readiness: 0.94" in next_action_banner
                assert "recommended lane: Generate Formal Complaint" in next_action_banner

                page.click("#intake-next-action-open-document-builder")
                page.wait_for_url(f"{base_url}/document?claim_type=retaliation&user_id=browser-smoke-text-link")

                assert "Formal Complaint Builder" in page.locator("body").inner_text()
                assert "Generate Formal Complaint" in page.locator("body").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_builds_claim_support_packets_from_next_action_banner():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for packet-build next-action smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )
        status_payload = mediator.get_three_phase_status.return_value
        status_payload["next_action"] = {
            "action": "build_claim_support_packets",
            "recommended_actions": ["collect_missing_support_kind"],
        }
        status_payload["claim_support_packet_summary"] = {
            **dict(status_payload.get("claim_support_packet_summary") or {}),
            "claim_count": 1,
            "element_count": 3,
        }

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                next_action_banner = page.locator("#intake-next-action-banner").inner_text()

                assert "Build claim support packets" in next_action_banner
                assert "recommended action: build_claim_support_packets" in next_action_banner
                assert "claims: 1" in next_action_banner
                assert "elements: 3" in next_action_banner
                assert "recommended lane: Collect Missing Support Kind" in next_action_banner

                page.click("#intake-next-action-build-packets")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Follow-up execution completed.')"
                )

                assert page.locator("#execution-result-card").is_visible()
                assert "Execution completed" in page.locator("#execution-result-card").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_claim_support_review_dashboard_smoke_uploads_document_via_playwright_and_persists_evidence():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as evidence_handle:
        evidence_db_path = evidence_handle.name
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as claim_support_handle:
        claim_support_db_path = claim_support_handle.name
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as legal_handle:
        legal_authority_db_path = legal_handle.name
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as upload_handle:
        upload_handle.write(
            b"The schedule reduction memo confirms the adverse action happened two days after the complaint."
        )
        upload_path = upload_handle.name

    try:
        mediator = _build_real_browser_upload_mediator(
            evidence_db_path=evidence_db_path,
            claim_support_db_path=claim_support_db_path,
            legal_authority_db_path=legal_authority_db_path,
        )

        app = _build_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(
                    f"{base_url}/claim-support-review?claim_type=retaliation&user_id=browser-upload-user"
                )
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                page.fill("#document-element-id", "retaliation:2")
                page.fill("#document-element-text", "Adverse action")
                page.fill("#document-label", "Schedule reduction memo")
                page.fill("#document-source-url", "https://example.com/schedule-memo")
                page.set_input_files("#document-file-input", upload_path)
                page.click("#save-document-button")

                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Validation save')"
                )
                page.wait_for_function(
                    "() => document.getElementById('document-list').textContent.includes('Schedule reduction memo')"
                )

                document_list_text = page.locator("#document-list").inner_text()
                browser.close()

        assert "Schedule reduction memo" in document_list_text
        assert "Adverse action" in document_list_text

        evidence_conn = duckdb.connect(evidence_db_path, read_only=True)
        try:
            evidence_count = evidence_conn.execute(
                "SELECT COUNT(*) FROM evidence WHERE user_id = ?",
                ["browser-upload-user"],
            ).fetchone()[0]
        finally:
            evidence_conn.close()

        claim_support_conn = duckdb.connect(claim_support_db_path, read_only=True)
        try:
            support_count = claim_support_conn.execute(
                "SELECT COUNT(*) FROM claim_support WHERE user_id = ?",
                ["browser-upload-user"],
            ).fetchone()[0]
        finally:
            claim_support_conn.close()

        assert evidence_count >= 1
        assert support_count >= 1
    finally:
        for path in (
            evidence_db_path,
            claim_support_db_path,
            legal_authority_db_path,
            upload_path,
        ):
            if os.path.exists(path):
                os.unlink(path)


def test_optimization_trace_smoke_renders_question_review_links_with_support_kind():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-smoke",
        "size": 321,
        "trace": {
            "user_id": "trace-smoke-user",
            "intake_status": {
                "current_phase": "intake",
                "score": 0.52,
                "contradiction_count": 1,
                "blockers": ["collect_missing_support"],
                "criteria": {
                    "case_theory_coherent": True,
                    "minimum_proof_path_present": True,
                    "claim_disambiguation_resolved": False,
                },
                "contradictions": [
                    {
                        "summary": "Termination date conflicts with reported complaint timeline",
                        "question": "Which date is supported by the termination notice?",
                        "recommended_resolution_lane": "request_document",
                        "current_resolution_status": "open",
                        "external_corroboration_required": True,
                        "affected_claim_types": ["retaliation"],
                        "affected_element_ids": ["retaliation:2"],
                    }
                ],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.87, "ambiguity_flags": ["timing_overlap"]},
                    {"claim_type": "wrongful_termination", "label": "Wrongful Termination", "confidence": 0.79},
                ],
                "complainant_summary_confirmation": {
                    "status": "pending",
                    "confirmed": False,
                    "confirmation_source": "complainant",
                    "confirmation_note": "",
                    "summary_snapshot_index": 0,
                    "current_summary_snapshot": {
                        "candidate_claim_count": 2,
                        "canonical_fact_count": 1,
                        "proof_lead_count": 1,
                    },
                    "confirmed_summary_snapshot": {},
                },
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "canonical_fact_intent_summary": {
                    "count": 1,
                    "question_objective_counts": {"establish_chronology": 1},
                    "expected_update_kind_counts": {"timeline_anchor": 1},
                    "target_claim_type_counts": {"retaliation": 1},
                    "target_element_id_counts": {"retaliation:1": 1},
                },
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "proof_lead_intent_summary": {
                    "count": 1,
                    "question_objective_counts": {"identify_supporting_evidence": 1},
                    "expected_update_kind_counts": {"proof_lead": 1},
                    "target_claim_type_counts": {"retaliation": 1},
                    "target_element_id_counts": {"retaliation:2": 1},
                },
                "timeline_anchor_summary": {"count": 1, "anchors": [{"anchor_id": "timeline_anchor_001"}]},
                "harm_profile": {"count": 1, "categories": ["economic"]},
                "remedy_profile": {"count": 1, "categories": ["monetary"]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {
                        "blocking": 1,
                        "non_blocking": 1,
                    },
                },
                "alignment_evidence_tasks": [
                    {
                        "task_id": "retaliation:retaliation:2:fill_evidence_gaps",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "fill_temporal_chronology_gap",
                        "preferred_support_kind": "evidence",
                        "fallback_lanes": ["authority", "testimony"],
                        "source_quality_target": "high_quality_document",
                        "resolution_status": "awaiting_complainant_record",
                        "resolution_notes": "",
                        "temporal_rule_profile_id": "retaliation_temporal_profile_v1",
                        "temporal_rule_status": "partial",
                        "temporal_rule_blocking_reasons": [
                            "Retaliation timeline lacks a clear ordering between protected activity and termination.",
                        ],
                        "temporal_rule_follow_ups": [
                            "Confirm whether the protected activity occurred before the termination notice.",
                        ],
                        "intake_proof_leads": [
                            {
                                "lead_id": "lead:complainant:record",
                                "owner": "complainant",
                                "recommended_support_kind": "evidence",
                                "description": "Termination email held by complainant",
                            }
                        ],
                    }
                ],
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                    "supported_blocking_element_ratio": 0.5,
                    "credible_support_ratio": 0.5,
                    "draft_ready_element_ratio": 0.0,
                    "high_quality_parse_ratio": 0.0,
                    "reviewable_escalation_ratio": 0.5,
                    "claim_support_reviewable_escalation_count": 1,
                    "proof_readiness_score": 0.225,
                    "claim_support_unresolved_without_review_path_count": 1,
                    "evidence_completion_ready": False,
                    "temporal_fact_count": 2,
                    "temporal_relation_count": 1,
                    "temporal_issue_count": 1,
                    "temporal_partial_order_ready_element_count": 0,
                    "temporal_warning_count": 1,
                    "temporal_gap_task_count": 1,
                    "temporal_gap_targeted_task_count": 1,
                    "temporal_rule_status_counts": {"partial": 1},
                    "temporal_rule_blocking_reason_counts": {
                        "Retaliation timeline lacks a clear ordering between protected activity and termination.": 1,
                    },
                    "temporal_resolution_status_counts": {"awaiting_complainant_record": 1},
                },
                "alignment_task_update_history": [
                    {
                        "task_id": "retaliation:claims_for_relief:resolve_support_conflicts",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "resolve_support_conflicts",
                        "current_support_status": "contradicted",
                        "resolution_status": "needs_manual_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-conflict",
                        "evidence_sequence": 2,
                    },
                    {
                        "task_id": "retaliation:claims_for_relief:await_operator_confirmation",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "await_operator_confirmation",
                        "current_support_status": "partially_supported",
                        "resolution_status": "answered_pending_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-pending",
                        "evidence_sequence": 3,
                    }
                ],
            },
            "iterations": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "critic": {"overall_score": 0.73},
                }
            ],
            "initial_review": {"overall_score": 0.41},
            "final_review": {"overall_score": 0.73, "recommended_focus": "claims_for_relief"},
        },
    }

    app = _build_document_browser_smoke_app()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.goto(f"{base_url}/document/optimization-trace")
            page.evaluate("payload => window.renderTrace(payload)", payload)
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('#traceEvidenceQuestionTargets a.inline-link')).length >= 2"
            )

            question_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#traceEvidenceQuestionTargets a.inline-link'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )

            assert {
                "text": "Open Proof Leads Question Review (1)",
                "href": "/claim-support-review?user_id=trace-smoke-user&section=proof_leads&follow_up_support_kind=evidence&alignment_task_update_filter=active&alignment_task_update_sort=newest_first",
            } in question_links
            assert {
                "text": "Open Claims For Relief Question Review (1)",
                "href": "/claim-support-review?user_id=trace-smoke-user&section=claims_for_relief&follow_up_support_kind=authority&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first",
            } in question_links

            section_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#traceEvidenceLinks a.inline-link'))
                    .filter((node) => node.textContent.includes('Intake Section Review'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )
            claim_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#traceEvidenceLinks a.inline-link'))
                    .filter((node) => node.textContent.includes('Intake Claim Review'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )
            manual_review_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#traceEvidenceLinks a.inline-link'))
                    .filter((node) => node.textContent.includes('Manual Review'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )
            pending_review_links = page.evaluate(
                """() => Array.from(document.querySelectorAll('#traceEvidenceLinks a.inline-link'))
                    .filter((node) => node.textContent.includes('Pending Review'))
                    .map((node) => ({ text: node.textContent.trim(), href: node.getAttribute('href') || '' }))"""
            )
            trace_evidence = page.locator("#traceEvidenceList").inner_text()
            trace_text = page.locator("#traceEvidenceManualReview").inner_text()

            assert {
                "text": "Open Retaliation Intake Claim Review",
                "href": "/claim-support-review?user_id=trace-smoke-user&claim_type=retaliation&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first",
            } in claim_links
            assert {
                "text": "Open Proof Leads Intake Section Review",
                "href": "/claim-support-review?user_id=trace-smoke-user&section=proof_leads&follow_up_support_kind=evidence&alignment_task_update_filter=active&alignment_task_update_sort=newest_first",
            } in section_links
            assert {
                "text": "Open Claims For Relief Intake Section Review",
                "href": "/claim-support-review?user_id=trace-smoke-user&section=claims_for_relief&follow_up_support_kind=authority&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first",
            } in section_links
            assert {
                "text": "Open Retaliation Manual Review",
                "href": "/claim-support-review?user_id=trace-smoke-user&claim_type=retaliation&alignment_task_update_filter=manual_review&alignment_task_update_sort=manual_review_first",
            } in manual_review_links
            assert {
                "text": "Open Retaliation Pending Review",
                "href": "/claim-support-review?user_id=trace-smoke-user&claim_type=retaliation&alignment_task_update_filter=pending_review&alignment_task_update_sort=pending_review_first",
            } in pending_review_links
            assert "Alignment tasks: 1" in trace_evidence
            assert "Candidate claim count: 2" in trace_evidence
            assert "Candidate claim average confidence: 0.83" in trace_evidence
            assert "Leading claim: Retaliation 0.87" in trace_evidence
            assert "Claim disambiguation: needed" in trace_evidence
            assert "Claim ambiguity flags: 1" in trace_evidence
            assert "Claim ambiguity details: Timing Overlap 1" in trace_evidence
            assert "Timeline anchors: 1" in trace_evidence
            assert "Harm profile: Economic" in trace_evidence
            assert "Remedy profile: Monetary" in trace_evidence
            assert "Corroboration-required contradictions: 1" in trace_evidence
            assert "Contradiction lanes: Request Document 1" in trace_evidence
            assert "Canonical fact intent records: 1" in trace_evidence
            assert "Canonical fact target claims: Retaliation 1" in trace_evidence
            assert "Proof lead intent records: 1" in trace_evidence
            assert "Proof lead target elements: Retaliation:2 1" in trace_evidence
            assert "Alignment preferred lanes: Evidence 1" in trace_evidence
            assert "Alignment fallback lanes: Authority 1, Testimony 1" in trace_evidence
            assert "Alignment quality targets: High Quality Document 1" in trace_evidence
            assert "Alignment handoffs: Awaiting Complainant Record 1" in trace_evidence
            assert "Alignment chronology tasks: 1" in trace_evidence
            assert "Alignment chronology targeted: 1" in trace_evidence
            assert "Alignment chronology status: Partial=1" in trace_evidence
            assert "Alignment chronology blockers: Retaliation timeline lacks a clear ordering between protected activity and termination.=1" in trace_evidence
            assert "Alignment chronology handoffs: Awaiting Complainant Record=1" in trace_evidence
            assert "Packet blocking covered: 0.50" in trace_evidence
            assert "Packet credible support: 0.50" in trace_evidence
            assert "Packet draft ready: 0.00" in trace_evidence
            assert "Packet parse quality: 0.00" in trace_evidence
            assert "Packet review escalations: 0.50" in trace_evidence
            assert "Packet escalations: 1" in trace_evidence
            assert "Packet proof readiness: 0.23" in trace_evidence
            assert "Packet unresolved without path: 1" in trace_evidence
            assert "Packet completion ready: no" in trace_evidence
            assert "Packet temporal facts: 2" in trace_evidence
            assert "Packet temporal relations: 1" in trace_evidence
            assert "Packet temporal issues: 1" in trace_evidence
            assert "Packet temporal ready elements: 0" in trace_evidence
            assert "Packet temporal warnings: 1" in trace_evidence
            assert "Packet chronology tasks: 1" in trace_evidence
            assert "Packet chronology targeted: 1" in trace_evidence
            assert "Packet chronology status: Partial=1" in trace_evidence
            assert "Packet chronology blockers: Retaliation timeline lacks a clear ordering between protected activity and termination.=1" in trace_evidence
            assert "Packet chronology handoffs: Awaiting Complainant Record=1" in trace_evidence
            handoff_trace_text = page.locator("#traceEvidenceHandoffs").inner_text()
            assert "Evidence Handoffs" in handoff_trace_text
            assert "Evidence handoffs: 1" in handoff_trace_text
            assert "Retaliation: Claims For Relief | status Awaiting Complainant Record | preferred lane Evidence | quality target High Quality Document | proof lead complainant / evidence / Termination email held by complainant" in handoff_trace_text
            assert "Manual Review Blockers" in trace_text
            assert "Manual review blockers: 1" in trace_text
            assert "Claims impacted: 1" in trace_text
            assert "Retaliation: Claims For Relief | action Resolve Support Conflicts | artifact artifact-conflict" in trace_text
            pending_trace_text = page.locator("#traceEvidencePendingReview").inner_text()
            contradiction_trace_text = page.locator("#traceContradictionList").inner_text()
            assert "Pending Review Items" in pending_trace_text
            assert "Pending review items: 1" in pending_trace_text
            assert "Claims impacted: 1" in pending_trace_text
            assert "Retaliation: Claims For Relief | action Await Operator Confirmation | artifact artifact-pending" in pending_trace_text
            assert "Termination date conflicts with reported complaint timeline | Clarify: Which date is supported by the termination notice? | Lane Request Document | Status Open | External corroboration required | Claims Retaliation | Affected elements Retaliation:2" in contradiction_trace_text
            intake_confirmation_text = page.locator("#traceIntakeConfirmation").inner_text()
            normalized_intake_confirmation_text = intake_confirmation_text.lower()
            assert "intake summary handoff" in normalized_intake_confirmation_text
            assert normalized_intake_confirmation_text.count("intake summary handoff") == 1
            assert "status pending" in normalized_intake_confirmation_text
            assert "complainant confirmed no" in normalized_intake_confirmation_text
            assert "confirm on review dashboard" in normalized_intake_confirmation_text
            assert normalized_intake_confirmation_text.count("confirm on review dashboard") == 1

            browser.close()


def test_optimization_trace_smoke_renders_workflow_phase_guidance():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-workflow",
        "size": 512,
        "trace": {
            "user_id": "trace-workflow-user",
            "report_summary": {
                "workflow_phase_plan": {
                    "recommended_order": ["graph_analysis", "document_generation"],
                    "phases": {
                        "graph_analysis": {
                            "status": "warning",
                            "summary": "Knowledge graph gaps still need reduction before drafting.",
                            "signals": {
                                "remaining_gap_count": 2,
                                "knowledge_graph_enhanced": False,
                            },
                            "target_files": ["complaint_phases/knowledge_graph.py", "document_pipeline.py"],
                            "recommended_actions": [
                                {"recommended_action": "Fill unresolved graph gaps from intake evidence."},
                            ],
                        },
                        "document_generation": {
                            "status": "warning",
                            "summary": "Document drafting should wait for graph cleanup.",
                            "signals": {
                                "warning_count": 3,
                                "draft_ready": False,
                            },
                            "target_files": ["templates/document.html"],
                            "recommended_actions": [
                                {"recommended_action": "Re-run document optimization after graph improvements."},
                            ],
                        },
                    },
                },
            },
            "intake_status": {
                "current_phase": "intake",
                "score": 0.61,
                "contradiction_count": 0,
                "blockers": ["reduce_graph_gaps"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.88},
                ],
                "candidate_claim_summary": {
                    "count": 1,
                    "claim_types": ["retaliation"],
                    "average_confidence": 0.88,
                    "top_claim_type": "retaliation",
                    "top_confidence": 0.88,
                    "ambiguous_claim_count": 0,
                    "ambiguity_flag_count": 0,
                    "ambiguity_flag_counts": {},
                    "close_leading_claims": False,
                },
                "intake_sections": {},
                "canonical_fact_summary": {},
                "canonical_fact_intent_summary": {},
                "proof_lead_summary": {},
                "proof_lead_intent_summary": {},
                "timeline_anchor_summary": {},
                "harm_profile": {},
                "remedy_profile": {},
                "question_candidate_summary": {},
                "alignment_evidence_tasks": [],
                "alignment_task_update_history": [],
                "claim_support_packet_summary": {},
            },
            "iterations": [
                {
                    "iteration": 1,
                    "focus_section": "claims_for_relief",
                    "accepted": True,
                    "critic": {"overall_score": 0.68},
                }
            ],
            "initial_review": {"overall_score": 0.52},
            "final_review": {"overall_score": 0.68, "recommended_focus": "claims_for_relief"},
        },
    }

    app = _build_document_browser_smoke_app()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.goto(f"{base_url}/document/optimization-trace")
            page.evaluate("payload => window.renderTrace(payload)", payload)
            page.wait_for_function(
                "() => document.getElementById('traceWorkflowPhaseGuidance').innerText.includes('Recommended order')"
            )

            workflow_text = page.locator("#traceWorkflowPhaseGuidance").inner_text().lower()

            assert "recommended order:" in workflow_text
            assert "graph analysis -> document generation" in workflow_text
            assert "1. graph analysis" in workflow_text
            assert "knowledge graph gaps still need reduction before drafting." in workflow_text
            assert "remaining gap count: 2" in workflow_text
            assert "knowledge graph enhanced: no" in workflow_text
            assert "targets: complaint_phases/knowledge_graph.py, document_pipeline.py" in workflow_text
            assert "next actions: fill unresolved graph gaps from intake evidence." in workflow_text
            assert "2. document generation" in workflow_text
            assert "document drafting should wait for graph cleanup." in workflow_text
            assert "warning count: 3" in workflow_text
            assert "draft ready: no" in workflow_text
            assert "targets: templates/document.html" in workflow_text
            assert "next actions: re-run document optimization after graph improvements." in workflow_text

            browser.close()


def test_optimization_trace_smoke_renders_ready_workflow_phase_guidance():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-workflow-ready",
        "size": 544,
        "trace": {
            "user_id": "trace-workflow-ready-user",
            "workflow_phase_plan": {
                "recommended_order": ["graph_analysis", "document_generation"],
                "phases": {
                    "graph_analysis": {
                        "status": "ready",
                        "summary": "Graph analysis is available and does not show unresolved intake graph blockers.",
                        "signals": {
                            "remaining_gap_count": 0,
                            "current_gap_count": 0,
                            "knowledge_graph_enhanced": True,
                        },
                        "target_files": ["complaint_phases/knowledge_graph.py"],
                        "recommended_actions": [],
                    },
                    "document_generation": {
                        "status": "ready",
                        "summary": "Document generation is aligned with the current filing-readiness checks.",
                        "signals": {
                            "drafting_readiness_status": "ready",
                            "warning_count": 0,
                            "optimization_final_score": 0.92,
                        },
                        "target_files": ["document_pipeline.py"],
                        "recommended_actions": [],
                    },
                },
            },
            "intake_status": {
                "current_phase": "formalization",
                "score": 0.92,
                "contradiction_count": 0,
                "blockers": [],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.92},
                ],
                "candidate_claim_summary": {
                    "count": 1,
                    "claim_types": ["retaliation"],
                    "average_confidence": 0.92,
                    "top_claim_type": "retaliation",
                    "top_confidence": 0.92,
                    "ambiguous_claim_count": 0,
                    "ambiguity_flag_count": 0,
                    "ambiguity_flag_counts": {},
                    "close_leading_claims": False,
                },
                "intake_sections": {},
                "canonical_fact_summary": {},
                "canonical_fact_intent_summary": {},
                "proof_lead_summary": {},
                "proof_lead_intent_summary": {},
                "timeline_anchor_summary": {},
                "harm_profile": {},
                "remedy_profile": {},
                "question_candidate_summary": {},
                "alignment_evidence_tasks": [],
                "alignment_task_update_history": [],
                "claim_support_packet_summary": {},
            },
            "iterations": [
                {
                    "iteration": 1,
                    "focus_section": "claims_for_relief",
                    "accepted": True,
                    "critic": {"overall_score": 0.92},
                }
            ],
            "initial_review": {"overall_score": 0.84},
            "final_review": {"overall_score": 0.92, "recommended_focus": "requested_relief"},
        },
    }

    app = _build_document_browser_smoke_app()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.goto(f"{base_url}/document/optimization-trace")
            page.evaluate("payload => window.renderTrace(payload)", payload)
            page.wait_for_function(
                "() => document.getElementById('traceWorkflowPhaseGuidance').innerText.includes('Document Generation')"
            )

            workflow_text = page.locator("#traceWorkflowPhaseGuidance").inner_text().lower()

            assert "recommended order:" in workflow_text
            assert "graph analysis -> document generation" in workflow_text
            assert "1. graph analysis" in workflow_text
            assert "ready" in workflow_text
            assert "remaining gap count: 0" in workflow_text
            assert "current gap count: 0" in workflow_text
            assert "knowledge graph enhanced: yes" in workflow_text
            assert "targets: complaint_phases/knowledge_graph.py" in workflow_text
            assert "2. document generation" in workflow_text
            assert "document generation is aligned with the current filing-readiness checks." in workflow_text
            assert "drafting readiness status: ready" in workflow_text
            assert "warning count: 0" in workflow_text
            assert "optimization final score: 0.92" in workflow_text
            assert "targets: document_pipeline.py" in workflow_text
            assert "no workflow phase guidance recorded" not in workflow_text

            browser.close()


def test_document_builder_smoke_confirms_intake_summary_handoff():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    next_action_summary = {
        "next_action": {
            "action": "confirm_intake_summary",
            "claim_type": "retaliation",
        },
        "candidate_claims": [
            {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.87},
            {"claim_type": "wrongful_termination", "label": "Wrongful Termination", "confidence": 0.79},
        ],
        "candidate_claim_summary": {
            "count": 2,
            "claim_types": ["retaliation", "wrongful_termination"],
            "average_confidence": 0.83,
            "top_claim_type": "retaliation",
            "top_confidence": 0.87,
            "ambiguous_claim_count": 0,
            "ambiguity_flag_count": 0,
            "ambiguity_flag_counts": {},
            "close_leading_claims": False,
        },
        "complainant_summary_confirmation": {
            "status": "pending",
            "confirmed": False,
            "confirmation_source": "complainant",
            "confirmation_note": "",
            "summary_snapshot_index": 0,
            "current_summary_snapshot": {
                "candidate_claim_count": 2,
                "canonical_fact_count": 1,
                "proof_lead_count": 1,
            },
            "confirmed_summary_snapshot": {},
        },
    }
    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"sections": {}, "claims": [], "warnings": []},
        "filing_checklist": [],
        "review_links": {
            "dashboard_url": "/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link",
            "intake_case_summary": next_action_summary,
        },
        "review_intent": {
            "user_id": "browser-smoke-text-link",
            "claim_type": "retaliation",
            "review_url": "/claim-support-review?claim_type=retaliation&user_id=browser-smoke-text-link",
        },
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 1,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support", "complainant_summary_confirmation_required"],
                "criteria": {
                    "case_theory_coherent": True,
                    "minimum_proof_path_present": True,
                    "claim_disambiguation_resolved": False,
                    "complainant_summary_confirmed": False,
                },
                "contradictions": [
                    {
                        "summary": "Termination date conflicts with reported complaint timeline",
                        "question": "Which date is supported by the termination notice?",
                        "recommended_resolution_lane": "request_document",
                        "current_resolution_status": "open",
                        "external_corroboration_required": True,
                        "affected_claim_types": ["retaliation"],
                        "affected_element_ids": ["retaliation:2"],
                    }
                ],
            },
            "intake_constraints": [],
            "intake_case_summary": next_action_summary,
            "claim_support_packet_summary": {},
            "section_history": [],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for document handoff confirmation smoke coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => document.getElementById('document-workflow-priority') !== null"
                )

                assert "intake summary handoff" in page.locator("#previewRoot").inner_text().lower()
                workflow_text = page.locator("#document-workflow-priority").inner_text()
                assert "Confirm intake summary before drafting" in workflow_text
                assert "recommended action: confirm_intake_summary" in workflow_text
                assert "Confirm intake summary" in workflow_text

                page.fill("#confirm-intake-summary-note", "Reviewed with complainant for evidence handoff")
                page.click("#document-workflow-action-link")

                page.wait_for_function(
                    "() => document.getElementById('previewRoot').innerText.includes('Confirmed at')"
                )
                preview_text = page.locator("#previewRoot").inner_text()
                handoff_text = page.locator("#previewRoot .intake-handoff-card").inner_text()
                normalized_preview_text = preview_text.lower()
                normalized_handoff_text = handoff_text.lower()

                assert "Status" in preview_text
                assert "Confirmed" in preview_text
                assert "Complainant Confirmed" in preview_text
                assert "yes" in preview_text
                assert "Source Document" in preview_text
                assert "Note: Reviewed with complainant for evidence handoff" in preview_text
                assert "Open Review Dashboard" in preview_text
                assert normalized_handoff_text.count("intake summary handoff") == 1
                assert normalized_handoff_text.count("confirmed at") == 1
                assert normalized_handoff_text.count("source document") == 1
                assert normalized_handoff_text.count("open review dashboard") == 1

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_optimization_trace_smoke_renders_confirmed_intake_summary_handoff():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-confirmed",
        "size": 654,
        "trace": {
            "user_id": "trace-smoke-user",
            "intake_status": {
                "current_phase": "intake",
                "score": 1.0,
                "contradiction_count": 0,
                "blockers": [],
                "criteria": {
                    "case_theory_coherent": True,
                    "minimum_proof_path_present": True,
                    "claim_disambiguation_resolved": True,
                    "complainant_summary_confirmed": True,
                },
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.91},
                ],
                "candidate_claim_summary": {
                    "count": 1,
                    "claim_types": ["retaliation"],
                    "average_confidence": 0.91,
                    "top_claim_type": "retaliation",
                    "top_confidence": 0.91,
                    "ambiguous_claim_count": 0,
                    "ambiguity_flag_count": 0,
                    "ambiguity_flag_counts": {},
                    "close_leading_claims": False,
                },
                "complainant_summary_confirmation": {
                    "status": "confirmed",
                    "confirmed": True,
                    "confirmation_source": "dashboard",
                    "confirmation_note": "Reviewed with complainant for evidence handoff",
                    "confirmed_at": "2026-03-17T10:00:00+00:00",
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
                "intake_sections": {},
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "canonical_fact_intent_summary": {},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "proof_lead_intent_summary": {},
                "timeline_anchor_summary": {"count": 0, "anchors": []},
                "harm_profile": {},
                "remedy_profile": {},
                "question_candidate_summary": {},
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 1,
                    "status_counts": {"supported": 1},
                    "recommended_actions": [],
                    "supported_blocking_element_ratio": 1.0,
                    "credible_support_ratio": 1.0,
                    "draft_ready_element_ratio": 1.0,
                    "high_quality_parse_ratio": 1.0,
                    "reviewable_escalation_ratio": 0.0,
                    "claim_support_reviewable_escalation_count": 0,
                    "proof_readiness_score": 1.0,
                    "claim_support_unresolved_without_review_path_count": 0,
                    "evidence_completion_ready": True,
                },
                "alignment_evidence_tasks": [],
                "alignment_task_update_history": [],
            },
            "iterations": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "critic": {"overall_score": 0.91},
                }
            ],
            "initial_review": {"overall_score": 0.75},
            "final_review": {"overall_score": 0.91, "recommended_focus": "claims_for_relief"},
        },
    }

    app = _build_document_browser_smoke_app()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.goto(f"{base_url}/document/optimization-trace")
            page.evaluate("payload => window.renderTrace(payload)", payload)
            page.wait_for_function(
                "() => document.getElementById('traceIntakeConfirmation').innerText.includes('Open Review Dashboard')"
            )

            intake_confirmation_text = page.locator("#traceIntakeConfirmation").inner_text()
            normalized_intake_confirmation_text = intake_confirmation_text.lower()

            assert "intake summary handoff" in normalized_intake_confirmation_text
            assert normalized_intake_confirmation_text.count("intake summary handoff") == 1
            assert "status confirmed" in normalized_intake_confirmation_text
            assert "complainant confirmed yes" in normalized_intake_confirmation_text
            assert "summary snapshot 1" in normalized_intake_confirmation_text
            assert "snapshot scope: candidate claims 1 | canonical facts 1 | proof leads 1" in normalized_intake_confirmation_text
            assert "confirmed at 2026-03-17t10:00:00+00:00" in normalized_intake_confirmation_text
            assert "source dashboard" in normalized_intake_confirmation_text
            assert "note: reviewed with complainant for evidence handoff" in normalized_intake_confirmation_text
            assert "open review dashboard" in normalized_intake_confirmation_text
            assert normalized_intake_confirmation_text.count("open review dashboard") == 1

            browser.close()


def test_optimization_trace_smoke_renders_claim_support_temporal_handoff():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-chronology",
        "size": 812,
        "trace": {
            "user_id": "trace-smoke-user",
            "claim_support_temporal_handoff": {
                "unresolved_temporal_issue_count": 2,
                "unresolved_temporal_issue_ids": ["timeline-gap-001", "timeline-gap-002"],
                "chronology_task_count": 3,
                "event_ids": ["event-termination", "event-hr-report"],
                "temporal_fact_ids": ["fact-001"],
                "temporal_relation_ids": ["rel-before-001"],
                "timeline_issue_ids": ["issue-ledger-001"],
                "temporal_issue_ids": ["temporal-issue-001", "temporal-issue-002"],
                "temporal_proof_bundle_ids": ["retaliation:causation:bundle_001"],
                "temporal_proof_objectives": ["show protected activity preceded termination"],
            },
            "intake_status": {
                "current_phase": "evidence",
                "score": 0.94,
                "contradiction_count": 0,
                "blockers": [],
                "criteria": {
                    "case_theory_coherent": True,
                    "minimum_proof_path_present": True,
                    "claim_disambiguation_resolved": True,
                    "complainant_summary_confirmed": True,
                },
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.91},
                ],
                "candidate_claim_summary": {
                    "count": 1,
                    "claim_types": ["retaliation"],
                    "average_confidence": 0.91,
                    "top_claim_type": "retaliation",
                    "top_confidence": 0.91,
                    "ambiguous_claim_count": 0,
                    "ambiguity_flag_count": 0,
                    "ambiguity_flag_counts": {},
                    "close_leading_claims": False,
                },
                "intake_sections": {},
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "canonical_fact_intent_summary": {},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "proof_lead_intent_summary": {},
                "timeline_anchor_summary": {"count": 1, "anchors": [{"anchor_id": "anchor_001"}]},
                "harm_profile": {},
                "remedy_profile": {},
                "question_candidate_summary": {},
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 1,
                    "status_counts": {"needs_follow_up": 1},
                    "recommended_actions": ["fill_temporal_chronology_gap"],
                    "supported_blocking_element_ratio": 0.0,
                    "credible_support_ratio": 0.5,
                    "draft_ready_element_ratio": 0.0,
                    "high_quality_parse_ratio": 1.0,
                    "reviewable_escalation_ratio": 1.0,
                    "claim_support_reviewable_escalation_count": 1,
                    "proof_readiness_score": 0.43,
                    "claim_support_unresolved_without_review_path_count": 0,
                    "claim_support_unresolved_temporal_issue_count": 2,
                    "claim_support_unresolved_temporal_issue_ids": ["timeline-gap-001", "timeline-gap-002"],
                    "evidence_completion_ready": False,
                    "temporal_gap_task_count": 3,
                },
                "alignment_evidence_tasks": [],
                "alignment_task_update_history": [],
            },
            "iterations": [
                {
                    "iteration": 1,
                    "focus_section": "chronology",
                    "accepted": True,
                    "critic": {"overall_score": 0.88},
                }
            ],
            "initial_review": {"overall_score": 0.68},
            "final_review": {"overall_score": 0.88, "recommended_focus": "chronology"},
        },
    }

    app = _build_document_browser_smoke_app()
    with _serve_app(app) as base_url:
        with sync_playwright() as playwright_context:
            browser = playwright_context.chromium.launch()
            page = browser.new_page()
            page.goto(f"{base_url}/document/optimization-trace")
            page.evaluate("payload => window.renderTrace(payload)", payload)
            page.wait_for_function(
                "() => document.getElementById('traceTemporalHandoff').innerText.includes('Claim Support Chronology Handoff')"
            )

            temporal_handoff_text = page.locator("#traceTemporalHandoff").inner_text().lower()

            assert "claim support chronology handoff" in temporal_handoff_text
            assert temporal_handoff_text.count("claim support chronology handoff") == 1
            assert "status blocked" in temporal_handoff_text
            assert "unresolved chronology issues 2" in temporal_handoff_text
            assert "chronology tasks 3" in temporal_handoff_text
            assert "event refs 2" in temporal_handoff_text
            assert "temporal relations 1" in temporal_handoff_text
            assert "proof bundles 1" in temporal_handoff_text
            assert "unresolved issue ids: timeline-gap-001, timeline-gap-002" in temporal_handoff_text
            assert "temporal issue refs: temporal-issue-001, temporal-issue-002" in temporal_handoff_text
            assert "event refs: event-termination, event-hr-report" in temporal_handoff_text
            assert "temporal relation refs: rel-before-001" in temporal_handoff_text
            assert "temporal proof bundles: retaliation:causation:bundle_001" in temporal_handoff_text
            assert "temporal proof objectives: show protected activity preceded termination" in temporal_handoff_text
            assert "review chronology blockers" in temporal_handoff_text

            browser.close()


def test_document_builder_question_review_link_click_preserves_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"sections": {}, "claims": [], "warnings": []},
        "filing_checklist": [],
        "review_links": {},
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 0,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {"blocking": 1, "non_blocking": 1},
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
            },
            "packet_projection": {
                "title": "Complaint Packet",
                "section_presence": {"factual_allegations": True},
                "has_affidavit": False,
                "has_certificate_of_service": False,
            },
            "section_history": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "overall_score": 0.7,
                }
            ],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for document-to-review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#previewRoot a.inline-link')).some((node) => node.textContent.includes('Claims For Relief Question Review'))"
                )

                page.click("text=Open Claims For Relief Question Review (1)")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "section=claims_for_relief" in page.url
                assert "follow_up_support_kind=authority" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#support-kind").input_value() == "authority"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"
                assert "Claims For Relief" in page.locator("#prefill-context-line").inner_text()
                assert "Focused lane: Authority." in page.locator("#prefill-context-line").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_document_builder_pending_review_link_click_preserves_queue_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"sections": {}, "claims": [], "warnings": []},
        "filing_checklist": [],
        "review_links": {},
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 0,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation"}],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {"blocking": 1, "non_blocking": 1},
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
                "alignment_task_update_history": [
                    {
                        "task_id": "retaliation:claims_for_relief:await_operator_confirmation",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "await_operator_confirmation",
                        "current_support_status": "partially_supported",
                        "resolution_status": "answered_pending_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-pending",
                        "evidence_sequence": 3,
                    }
                ],
            },
            "packet_projection": {
                "title": "Complaint Packet",
                "section_presence": {"factual_allegations": True},
                "has_affidavit": False,
                "has_certificate_of_service": False,
            },
            "section_history": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "overall_score": 0.7,
                }
            ],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for document pending-review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#previewRoot a.inline-link')).some((node) => node.textContent.includes('Pending Review'))"
                )

                page.click("text=Open Retaliation Pending Review")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "claim_type=retaliation" in page.url
                assert "alignment_task_update_filter=pending_review" in page.url
                assert "alignment_task_update_sort=pending_review_first" in page.url
                assert page.locator("#claim-type").input_value() == "retaliation"
                assert page.locator("#alignment-task-update-filter").input_value() == "pending_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "pending_review_first"

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_document_builder_manual_review_link_click_preserves_queue_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"sections": {}, "claims": [], "warnings": []},
        "filing_checklist": [],
        "review_links": {},
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 0,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation"}],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {"blocking": 1, "non_blocking": 1},
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
                "alignment_task_update_history": [
                    {
                        "task_id": "retaliation:claims_for_relief:resolve_support_conflicts",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "resolve_support_conflicts",
                        "current_support_status": "contradicted",
                        "resolution_status": "needs_manual_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-conflict",
                        "evidence_sequence": 2,
                    }
                ],
            },
            "packet_projection": {
                "title": "Complaint Packet",
                "section_presence": {"factual_allegations": True},
                "has_affidavit": False,
                "has_certificate_of_service": False,
            },
            "section_history": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "overall_score": 0.7,
                }
            ],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for document manual-review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#previewRoot a.inline-link')).some((node) => node.textContent.includes('Manual Review'))"
                )

                page.click("text=Open Retaliation Manual Review")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "claim_type=retaliation" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#claim-type").input_value() == "retaliation"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_document_builder_intake_claim_review_link_prefers_manual_review_queue_focus():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"sections": {}, "claims": [], "warnings": []},
        "filing_checklist": [],
        "review_links": {},
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 0,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation"}],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {"blocking": 1, "non_blocking": 1},
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
                "alignment_task_update_history": [
                    {
                        "task_id": "retaliation:claims_for_relief:resolve_support_conflicts",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "resolve_support_conflicts",
                        "current_support_status": "contradicted",
                        "resolution_status": "needs_manual_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-conflict",
                        "evidence_sequence": 2,
                    },
                    {
                        "task_id": "retaliation:claims_for_relief:await_operator_confirmation",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "await_operator_confirmation",
                        "current_support_status": "partially_supported",
                        "resolution_status": "answered_pending_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-pending",
                        "evidence_sequence": 3,
                    }
                ],
            },
            "packet_projection": {
                "title": "Complaint Packet",
                "section_presence": {"factual_allegations": True},
                "has_affidavit": False,
                "has_certificate_of_service": False,
            },
            "section_history": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "overall_score": 0.7,
                }
            ],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for document intake-claim review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#previewRoot a.inline-link')).some((node) => node.textContent.includes('Intake Claim Review'))"
                )

                page.click("text=Open Retaliation Intake Claim Review")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "claim_type=retaliation" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#claim-type").input_value() == "retaliation"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_document_builder_claim_readiness_review_link_prefers_manual_review_queue_focus():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {
            "sections": {},
            "claims": [
                {
                    "claim_type": "retaliation",
                    "status": "needs_review",
                    "validation_status": "incomplete",
                    "covered_elements": 1,
                    "total_elements": 2,
                    "support_by_kind": {"authority": 1},
                    "unresolved_element_count": 1,
                    "proof_gap_count": 1,
                    "contradiction_candidate_count": 1,
                    "warnings": ["authority support incomplete"],
                }
            ],
            "warnings": [],
        },
        "filing_checklist": [],
        "review_links": {},
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 0,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation"}],
                "intake_sections": {
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {"count": 0, "question_goal_counts": {}, "phase1_section_counts": {}, "blocking_level_counts": {}},
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
                "alignment_task_update_history": [
                    {
                        "task_id": "retaliation:claims_for_relief:resolve_support_conflicts",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "resolve_support_conflicts",
                        "current_support_status": "contradicted",
                        "resolution_status": "needs_manual_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-conflict",
                        "evidence_sequence": 2,
                    }
                ],
            },
            "packet_projection": {
                "title": "Complaint Packet",
                "section_presence": {"factual_allegations": True},
                "has_affidavit": False,
                "has_certificate_of_service": False,
            },
            "section_history": [],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for document claim-readiness review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => document.querySelectorAll('.readiness-claim-stack a.inline-link').length > 0"
                )

                page.locator(".readiness-claim-stack").get_by_text("Open Claim Support Review").click()
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "claim_type=retaliation" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#claim-type").input_value() == "retaliation"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_optimization_trace_pending_review_link_click_preserves_queue_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-smoke",
        "size": 321,
        "trace": {
            "user_id": "browser-smoke-text-link",
            "intake_status": {
                "current_phase": "intake",
                "score": 0.52,
                "contradiction_count": 0,
                "blockers": ["collect_missing_support"],
                "criteria": {
                    "case_theory_coherent": True,
                    "minimum_proof_path_present": True,
                    "claim_disambiguation_resolved": False,
                },
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.87, "ambiguity_flags": ["timing_overlap"]},
                    {"claim_type": "wrongful_termination", "label": "Wrongful Termination", "confidence": 0.79},
                ],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "timeline_anchor_summary": {"count": 1, "anchors": [{"anchor_id": "timeline_anchor_001"}]},
                "harm_profile": {"count": 1, "categories": ["economic"]},
                "remedy_profile": {"count": 1, "categories": ["monetary"]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {
                        "blocking": 1,
                        "non_blocking": 1,
                    },
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
                "alignment_task_update_history": [
                    {
                        "task_id": "retaliation:claims_for_relief:await_operator_confirmation",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "await_operator_confirmation",
                        "current_support_status": "partially_supported",
                        "resolution_status": "answered_pending_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-pending",
                        "evidence_sequence": 3,
                    }
                ],
            },
            "iterations": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "critic": {"overall_score": 0.73},
                }
            ],
            "initial_review": {"overall_score": 0.41},
            "final_review": {"overall_score": 0.73, "recommended_focus": "claims_for_relief"},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for trace pending-review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document/optimization-trace")
                page.evaluate("payload => window.renderTrace(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#traceEvidenceLinks a.inline-link')).some((node) => node.textContent.includes('Pending Review'))"
                )

                page.click("text=Open Retaliation Pending Review")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "user_id=browser-smoke-text-link" in page.url
                assert "claim_type=retaliation" in page.url
                assert "alignment_task_update_filter=pending_review" in page.url
                assert "alignment_task_update_sort=pending_review_first" in page.url
                assert page.locator("#claim-type").input_value() == "retaliation"
                assert page.locator("#alignment-task-update-filter").input_value() == "pending_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "pending_review_first"

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_optimization_trace_intake_claim_review_link_prefers_manual_review_queue_focus():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-smoke",
        "size": 321,
        "trace": {
            "user_id": "browser-smoke-text-link",
            "intake_status": {
                "current_phase": "intake",
                "score": 0.52,
                "contradiction_count": 0,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation"},
                ],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {
                        "blocking": 1,
                        "non_blocking": 1,
                    },
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
                "alignment_task_update_history": [
                    {
                        "task_id": "retaliation:claims_for_relief:resolve_support_conflicts",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "resolve_support_conflicts",
                        "current_support_status": "contradicted",
                        "resolution_status": "needs_manual_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-conflict",
                        "evidence_sequence": 2,
                    },
                    {
                        "task_id": "retaliation:claims_for_relief:await_operator_confirmation",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "await_operator_confirmation",
                        "current_support_status": "partially_supported",
                        "resolution_status": "answered_pending_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-pending",
                        "evidence_sequence": 3,
                    }
                ],
            },
            "iterations": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "critic": {"overall_score": 0.73},
                }
            ],
            "initial_review": {"overall_score": 0.41},
            "final_review": {"overall_score": 0.73, "recommended_focus": "claims_for_relief"},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for trace intake-claim review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document/optimization-trace")
                page.evaluate("payload => window.renderTrace(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#traceEvidenceLinks a.inline-link')).some((node) => node.textContent.includes('Intake Claim Review'))"
                )

                page.click("text=Open Retaliation Intake Claim Review")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "user_id=browser-smoke-text-link" in page.url
                assert "claim_type=retaliation" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#claim-type").input_value() == "retaliation"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_optimization_trace_manual_review_link_click_preserves_queue_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-smoke",
        "size": 321,
        "trace": {
            "user_id": "browser-smoke-text-link",
            "intake_status": {
                "current_phase": "intake",
                "score": 0.52,
                "contradiction_count": 0,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation"},
                ],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {
                        "blocking": 1,
                        "non_blocking": 1,
                    },
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
                "alignment_task_update_history": [
                    {
                        "task_id": "retaliation:claims_for_relief:resolve_support_conflicts",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "resolve_support_conflicts",
                        "current_support_status": "contradicted",
                        "resolution_status": "needs_manual_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-conflict",
                        "evidence_sequence": 2,
                    }
                ],
            },
            "iterations": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "critic": {"overall_score": 0.73},
                }
            ],
            "initial_review": {"overall_score": 0.41},
            "final_review": {"overall_score": 0.73, "recommended_focus": "claims_for_relief"},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for trace manual-review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document/optimization-trace")
                page.evaluate("payload => window.renderTrace(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#traceEvidenceLinks a.inline-link')).some((node) => node.textContent.includes('Manual Review'))"
                )

                page.click("text=Open Retaliation Manual Review")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "user_id=browser-smoke-text-link" in page.url
                assert "claim_type=retaliation" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#claim-type").input_value() == "retaliation"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_document_builder_intake_section_review_link_click_preserves_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"sections": {}, "claims": [], "warnings": []},
        "filing_checklist": [],
        "review_links": {},
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 0,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {"blocking": 1, "non_blocking": 1},
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
            },
            "packet_projection": {
                "title": "Complaint Packet",
                "section_presence": {"factual_allegations": True},
                "has_affidavit": False,
                "has_certificate_of_service": False,
            },
            "section_history": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "overall_score": 0.7,
                }
            ],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for document section review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#previewRoot a.inline-link')).some((node) => node.textContent.includes('Proof Leads Intake Section Review'))"
                )

                page.click("text=Open Proof Leads Intake Section Review")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "section=proof_leads" in page.url
                assert "follow_up_support_kind=evidence" in page.url
                assert "alignment_task_update_filter=active" in page.url
                assert page.locator("#support-kind").input_value() == "evidence"
                assert page.locator("#alignment-task-update-filter").input_value() == "active"
                assert page.locator("#alignment-task-update-sort").input_value() == "newest_first"
                assert "Proof Leads" in page.locator("#prefill-context-line").inner_text()
                assert "Focused lane: Evidence." in page.locator("#prefill-context-line").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_document_builder_readiness_section_review_link_preserves_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {
            "sections": {
                "claims_for_relief": {
                    "title": "Claims For Relief",
                    "status": "needs_review",
                    "metrics": {"missing_authority": 1},
                    "warnings": [{"message": "Authority support incomplete."}],
                }
            },
            "claims": [],
            "warnings": [],
        },
        "filing_checklist": [],
        "review_links": {},
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 0,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [],
                "intake_sections": {
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 1,
                    "question_goal_counts": {"establish_element": 1},
                    "phase1_section_counts": {"claims_for_relief": 1},
                    "blocking_level_counts": {"blocking": 1},
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
            },
            "packet_projection": {
                "title": "Complaint Packet",
                "section_presence": {"factual_allegations": True},
                "has_affidavit": False,
                "has_certificate_of_service": False,
            },
            "section_history": [],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for readiness section review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => document.querySelectorAll('.readiness-detail-card a.inline-link').length > 0"
                )

                page.locator('.readiness-detail-card').get_by_text('Open Section Review').click()
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "section=claims_for_relief" in page.url
                assert "follow_up_support_kind=authority" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#support-kind").input_value() == "authority"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_document_builder_checklist_review_link_preserves_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "generated_at": "2026-03-15T20:00:00+00:00",
        "draft": {
            "court_header": "IN THE UNITED STATES DISTRICT COURT",
            "case_caption": {
                "plaintiffs": ["Jane Doe"],
                "defendants": ["Acme Corporation"],
            },
            "summary_of_facts": ["Plaintiff reported discrimination to HR."],
            "factual_allegation_paragraphs": ["1. Plaintiff reported discrimination to HR."],
            "legal_standards": ["Title VII prohibits retaliation."],
            "claims_for_relief": [],
            "requested_relief": ["Compensatory damages."],
            "draft_text": "Sample draft text.",
            "exhibits": [],
        },
        "drafting_readiness": {"sections": {}, "claims": [], "warnings": []},
        "filing_checklist": [
            {
                "scope": "claim",
                "title": "Authority support review",
                "status": "needs_review",
                "summary": "Claims for relief authority support is incomplete.",
                "section_key": "claims_for_relief",
                "claim_type": "retaliation",
                "review_url": "/claim-support-review?claim_type=retaliation&section=claims_for_relief",
                "intake_status": {
                    "score": 0.5,
                    "remaining_gap_count": 1,
                    "contradiction_count": 1,
                    "ready_to_advance": False,
                    "blockers": ["collect_missing_support"],
                    "contradictions": [
                        {
                            "summary": "Complaint date conflicts with HR intake record",
                            "question": "Which date is reflected in the HR complaint email?",
                            "recommended_resolution_lane": "request_document",
                            "current_resolution_status": "open",
                            "external_corroboration_required": True,
                            "affected_claim_types": ["retaliation"],
                            "affected_element_ids": ["retaliation:2"],
                        }
                    ],
                },
            }
        ],
        "review_links": {},
        "document_optimization": {
            "status": "optimized",
            "method": "actor_mediator_critic_optimizer",
            "optimizer_backend": "upstream_agentic",
            "initial_score": 0.4,
            "final_score": 0.7,
            "accepted_iterations": 1,
            "iteration_count": 1,
            "optimized_sections": ["factual_allegations"],
            "trace_storage": {"status": "available", "cid": "bafy-test", "size": 123, "pinned": True},
            "intake_status": {
                "current_phase": "intake",
                "score": 0.5,
                "remaining_gap_count": 1,
                "contradiction_count": 1,
                "ready_to_advance": False,
                "blockers": ["collect_missing_support"],
                "contradictions": [
                    {
                        "summary": "Complaint date conflicts with HR intake record",
                        "question": "Which date is reflected in the HR complaint email?",
                        "recommended_resolution_lane": "request_document",
                        "current_resolution_status": "open",
                        "external_corroboration_required": True,
                        "affected_claim_types": ["retaliation"],
                        "affected_element_ids": ["retaliation:2"],
                    }
                ],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [{"claim_type": "retaliation", "label": "Retaliation"}],
                "intake_sections": {
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 1,
                    "question_goal_counts": {"establish_element": 1},
                    "phase1_section_counts": {"claims_for_relief": 1},
                    "blocking_level_counts": {"blocking": 1},
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
                "alignment_task_update_history": [
                    {
                        "task_id": "retaliation:claims_for_relief:resolve_support_conflicts",
                        "claim_type": "retaliation",
                        "claim_element_id": "retaliation:2",
                        "claim_element_label": "Claims For Relief",
                        "action": "resolve_support_conflicts",
                        "current_support_status": "contradicted",
                        "resolution_status": "needs_manual_review",
                        "status": "active",
                        "evidence_artifact_id": "artifact-conflict",
                        "evidence_sequence": 2,
                    }
                ],
            },
            "packet_projection": {
                "title": "Complaint Packet",
                "section_presence": {"factual_allegations": True},
                "has_affidavit": False,
                "has_certificate_of_service": False,
            },
            "section_history": [],
            "initial_review": {},
            "final_review": {},
            "router_status": {},
            "upstream_optimizer": {},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for checklist review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document")
                page.evaluate("payload => window.renderPreview(payload)", payload)
                page.wait_for_function(
                    "() => document.querySelectorAll('.checklist-card a.inline-link').length > 0"
                )
                checklist_text = page.locator('.checklist-card').first.inner_text()
                normalized_checklist_text = checklist_text.lower()

                assert "checklist intake signals" in normalized_checklist_text
                assert "corroboration-required contradictions: 1" in normalized_checklist_text
                assert "contradiction lanes: request document 1" in normalized_checklist_text
                assert "contradiction target elements: retaliation:2 1" in normalized_checklist_text
                assert normalized_checklist_text.count("contradiction target elements: retaliation:2 1") == 1
                assert "complaint date conflicts with hr intake record | ask which date is reflected in the hr complaint email? | lane request document | status open | external corroboration required | claims retaliation" in normalized_checklist_text

                page.locator('.checklist-card').get_by_text('Open Checklist Review').click()
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "claim_type=retaliation" in page.url
                assert "section=claims_for_relief" in page.url
                assert "follow_up_support_kind=authority" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#claim-type").input_value() == "retaliation"
                assert page.locator("#support-kind").input_value() == "authority"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_optimization_trace_question_review_link_click_preserves_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-smoke",
        "size": 321,
        "trace": {
            "user_id": "browser-smoke-text-link",
            "intake_status": {
                "current_phase": "intake",
                "score": 0.52,
                "contradiction_count": 0,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation"},
                ],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {
                        "blocking": 1,
                        "non_blocking": 1,
                    },
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
            },
            "iterations": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "critic": {"overall_score": 0.73},
                }
            ],
            "initial_review": {"overall_score": 0.41},
            "final_review": {"overall_score": 0.73, "recommended_focus": "claims_for_relief"},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for trace-to-review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document/optimization-trace")
                page.evaluate("payload => window.renderTrace(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#traceEvidenceQuestionTargets a.inline-link')).some((node) => node.textContent.includes('Claims For Relief Question Review'))"
                )

                page.click("text=Open Claims For Relief Question Review (1)")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "user_id=browser-smoke-text-link" in page.url
                assert "section=claims_for_relief" in page.url
                assert "follow_up_support_kind=authority" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#support-kind").input_value() == "authority"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"
                assert "Claims For Relief" in page.locator("#prefill-context-line").inner_text()
                assert "Focused lane: Authority." in page.locator("#prefill-context-line").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_optimization_trace_intake_section_review_link_click_preserves_focus_on_review_page():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-smoke",
        "size": 321,
        "trace": {
            "user_id": "browser-smoke-text-link",
            "intake_status": {
                "current_phase": "intake",
                "score": 0.52,
                "contradiction_count": 0,
                "blockers": ["collect_missing_support"],
                "contradictions": [],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation"},
                ],
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                    "claims_for_relief": {"status": "partial", "missing_items": ["authority"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {
                    "count": 2,
                    "question_goal_counts": {
                        "identify_supporting_proof": 1,
                        "establish_element": 1,
                    },
                    "phase1_section_counts": {
                        "proof_leads": 1,
                        "claims_for_relief": 1,
                    },
                    "blocking_level_counts": {
                        "blocking": 1,
                        "non_blocking": 1,
                    },
                },
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 2,
                    "status_counts": {"unsupported": 2},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
            },
            "iterations": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "critic": {"overall_score": 0.73},
                }
            ],
            "initial_review": {"overall_score": 0.41},
            "final_review": {"overall_score": 0.73, "recommended_focus": "claims_for_relief"},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for trace section review click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document/optimization-trace")
                page.evaluate("payload => window.renderTrace(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#traceEvidenceLinks a.inline-link')).some((node) => node.textContent.includes('Claims For Relief Intake Section Review'))"
                )

                page.click("text=Open Claims For Relief Intake Section Review")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "user_id=browser-smoke-text-link" in page.url
                assert "section=claims_for_relief" in page.url
                assert "follow_up_support_kind=authority" in page.url
                assert "alignment_task_update_filter=manual_review" in page.url
                assert "alignment_task_update_sort=manual_review_first" in page.url
                assert page.locator("#support-kind").input_value() == "authority"
                assert page.locator("#alignment-task-update-filter").input_value() == "manual_review"
                assert page.locator("#alignment-task-update-sort").input_value() == "manual_review_first"
                assert "Claims For Relief" in page.locator("#prefill-context-line").inner_text()
                assert "Focused lane: Authority." in page.locator("#prefill-context-line").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_optimization_trace_intake_handoff_link_opens_review_dashboard_with_confirmation_context():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    payload = {
        "cid": "bafy-trace-smoke",
        "size": 321,
        "trace": {
            "user_id": "browser-smoke-text-link",
            "intake_status": {
                "current_phase": "intake",
                "score": 0.52,
                "contradiction_count": 1,
                "blockers": ["collect_missing_support", "complainant_summary_confirmation_required"],
                "contradictions": [
                    {
                        "summary": "Termination date conflicts with reported complaint timeline",
                        "question": "Which date is supported by the termination notice?",
                        "recommended_resolution_lane": "request_document",
                        "current_resolution_status": "open",
                        "external_corroboration_required": True,
                        "affected_claim_types": ["retaliation"],
                        "affected_element_ids": ["retaliation:2"],
                    }
                ],
            },
            "intake_constraints": [],
            "intake_case_summary": {
                "candidate_claims": [
                    {"claim_type": "retaliation", "label": "Retaliation", "confidence": 0.87},
                ],
                "candidate_claim_summary": {
                    "count": 1,
                    "claim_types": ["retaliation"],
                    "average_confidence": 0.87,
                    "top_claim_type": "retaliation",
                    "top_confidence": 0.87,
                    "ambiguous_claim_count": 0,
                    "ambiguity_flag_count": 0,
                    "ambiguity_flag_counts": {},
                    "close_leading_claims": False,
                },
                "complainant_summary_confirmation": {
                    "status": "pending",
                    "confirmed": False,
                    "confirmation_source": "complainant",
                    "confirmation_note": "",
                    "summary_snapshot_index": 0,
                    "current_summary_snapshot": {
                        "candidate_claim_count": 1,
                        "canonical_fact_count": 1,
                        "proof_lead_count": 1,
                    },
                    "confirmed_summary_snapshot": {},
                },
                "intake_sections": {
                    "proof_leads": {"status": "partial", "missing_items": ["documents"]},
                },
                "canonical_fact_summary": {"count": 1, "facts": [{"fact_id": "fact_001"}]},
                "proof_lead_summary": {"count": 1, "proof_leads": [{"lead_id": "lead_001"}]},
                "question_candidate_summary": {},
                "claim_support_packet_summary": {
                    "claim_count": 1,
                    "element_count": 1,
                    "status_counts": {"unsupported": 1},
                    "recommended_actions": ["collect_missing_support_kind"],
                },
            },
            "iterations": [
                {
                    "iteration": 1,
                    "focus_section": "factual_allegations",
                    "accepted": True,
                    "critic": {"overall_score": 0.73},
                }
            ],
            "initial_review": {"overall_score": 0.41},
            "final_review": {"overall_score": 0.73, "recommended_focus": "claims_for_relief"},
        },
    }

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as handle:
        db_path = handle.name

    try:
        mediator, _hook = _build_hook_backed_browser_mediator(db_path)
        mediator.save_claim_testimony_record(
            user_id="browser-smoke-text-link",
            claim_type="retaliation",
            claim_element_text="Protected activity",
            raw_narrative="Protected activity seed for trace handoff dashboard click-through coverage.",
            firsthand_status="firsthand",
            source_confidence=0.9,
        )

        app = _build_document_review_browser_smoke_app(mediator)
        with _serve_app(app) as base_url:
            with sync_playwright() as playwright_context:
                browser = playwright_context.chromium.launch()
                page = browser.new_page()
                page.goto(f"{base_url}/document/optimization-trace")
                page.evaluate("payload => window.renderTrace(payload)", payload)
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('#traceIntakeConfirmation a.inline-link')).some((node) => node.textContent.includes('Confirm on Review Dashboard'))"
                )

                page.click("text=Confirm on Review Dashboard")
                page.wait_for_url("**/claim-support-review?**")
                page.wait_for_function(
                    "() => document.getElementById('status-line').textContent.includes('Review payload loaded.')"
                )

                assert "user_id=browser-smoke-text-link" in page.url
                assert "claim_type=retaliation" in page.url
                assert page.locator("#claim-type").input_value() == "retaliation"
                assert "Latest intake summary snapshot is awaiting complainant confirmation." in page.locator("#confirm-intake-summary-status").inner_text()

                browser.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
