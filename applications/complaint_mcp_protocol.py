from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .case_routes import shared_inquiry_conflict
from .complaint_workspace import ComplaintWorkspaceService, WorkspaceAccess, WorkspaceAuthorizationDenied, workspace_access_scope


JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")
DEFAULT_MCP_PROTOCOL_VERSION = "2025-06-18"


def gui_inference_tool_failed(tool_name: str, payload: Any) -> bool:
    """A returned refusal is a tool error; a pending proposal is not."""
    if not isinstance(payload, dict):
        return False
    if tool_name == "complaint.admit_bounded_gui_inference":
        return payload.get("accepted") is not True
    return (tool_name == "complaint.dispatch_bounded_gui_inference"
            and payload.get("status") in {"refused", "unavailable", "timeout", "cancelled", "error", "failed"})


def negotiated_protocol_version(params: Any) -> str:
    """Echo a Mike-supported MCP version, or the default when the client omits one."""

    requested = params.get("protocolVersion") if isinstance(params, dict) else None
    if isinstance(requested, str) and requested in MCP_PROTOCOL_VERSIONS:
        return requested
    return DEFAULT_MCP_PROTOCOL_VERSION

_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "complaint.dispatch_bounded_gui_inference": {
        "type": "object", "additionalProperties": False,
        "properties": {"purpose": {"type": "string"}, "inputs": {"type": "object"},
                       "timeout_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 60}},
        "required": ["purpose", "inputs"],
    },
    "complaint.admit_bounded_gui_inference": {
        "type": "object", "additionalProperties": False,
        "properties": {"invocation_id": {"type": "string"}}, "required": ["invocation_id"],
    },
    "complaint.create_identity": {
        "type": "object",
        "properties": {},
    },
    "complaint.list_intake_questions": {
        "type": "object",
        "properties": {},
    },
    "complaint.list_claim_elements": {
        "type": "object",
        "properties": {},
    },
    "complaint.start_session": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.submit_intake": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "answers": {"type": "object"},
        },
        "required": ["answers"],
    },
    "complaint.run_intake_chat_turn": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "message": {"type": "string"},
            "question_id": {"type": "string"},
            "expected_question_revision": {"type": "integer", "minimum": 0},
            "interview_action": {"type": "string"},
        },
        "description": (
            "Answer or resume the shared WorkflowActionService inquiry. "
            "question_id is the pending inquiry id. expected_question_revision "
            "must match the current revision when supplied. A stale or "
            "mismatched answer is an explicit conflict and does not advance."
        ),
    },
    "complaint.save_evidence": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "kind": {"type": "string", "enum": ["testimony", "document"]},
            "claim_element_id": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "source": {"type": "string"},
            "attachment_names": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["kind", "claim_element_id", "title", "content"],
    },
    "complaint.tag_document_annotation": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "document_id": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "note": {"type": "string"},
            "claim_element_id": {"type": "string"},
            "title": {"type": "string"},
            "dataset_kind": {"type": "string"},
            "document_title": {"type": "string"},
            "document_text_preview": {"type": "string"},
            "document_metadata": {"type": "object"},
            "user_metadata": {"type": "object"},
            "source": {"type": "string"},
        },
        "required": ["document_id", "note"],
    },
    "complaint.get_document_annotation_graph": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.tag_workspace_dataset_document": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "document_id": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "note": {"type": "string"},
            "claim_element_id": {"type": "string"},
            "title": {"type": "string"},
            "document_title": {"type": "string"},
            "document_text_preview": {"type": "string"},
            "collection_id": {"type": "string"},
            "document_type": {"type": "string"},
            "claim_type": {"type": "string"},
            "source_type": {"type": "string"},
            "document_metadata": {"type": "object"},
            "user_metadata": {"type": "object"},
            "source": {"type": "string"},
        },
        "required": ["document_id", "note"],
    },
    "complaint.get_workspace_dataset_annotation_index": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.import_gmail_evidence": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "addresses": {
                "type": "array",
                "items": {"type": "string"},
            },
            "collect_all_messages": {"type": "boolean"},
            "claim_element_id": {"type": "string"},
            "folder": {"type": "string"},
            "folders": {
                "type": "array",
                "items": {"type": "string"},
            },
            "limit": {"type": "integer"},
            "date_after": {"type": "string"},
            "date_before": {"type": "string"},
            "years_back": {"type": "integer"},
            "evidence_root": {"type": "string"},
            "gmail_user": {"type": "string"},
            "gmail_app_password": {"type": "string"},
            "use_gmail_oauth": {"type": "boolean"},
            "gmail_oauth_client_secrets": {"type": "string"},
            "gmail_oauth_token_cache": {"type": "string"},
            "gmail_oauth_open_browser": {"type": "boolean"},
            "complaint_query": {"type": "string"},
            "complaint_keywords": {
                "type": "array",
                "items": {"type": "string"},
            },
            "min_relevance_score": {"type": "number"},
            "use_uid_checkpoint": {"type": "boolean"},
            "checkpoint_name": {"type": "string"},
            "uid_window_size": {"type": "integer"},
        },
    },
    "complaint.run_gmail_duckdb_pipeline": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "addresses": {"type": "array", "items": {"type": "string"}},
            "collect_all_messages": {"type": "boolean"},
            "claim_element_id": {"type": "string"},
            "folder": {"type": "string"},
            "folders": {"type": "array", "items": {"type": "string"}},
            "years_back": {"type": "integer"},
            "date_after": {"type": "string"},
            "date_before": {"type": "string"},
            "complaint_query": {"type": "string"},
            "complaint_keywords": {"type": "array", "items": {"type": "string"}},
            "min_relevance_score": {"type": "number"},
            "evidence_root": {"type": "string"},
            "gmail_user": {"type": "string"},
            "gmail_app_password": {"type": "string"},
            "use_gmail_oauth": {"type": "boolean"},
            "gmail_oauth_client_secrets": {"type": "string"},
            "gmail_oauth_token_cache": {"type": "string"},
            "gmail_oauth_open_browser": {"type": "boolean"},
            "checkpoint_name": {"type": "string"},
            "uid_window_size": {"type": "integer"},
            "duckdb_build_every_batches": {"type": "integer"},
            "max_batches": {"type": "integer"},
            "duckdb_output_dir": {"type": "string"},
            "append_to_existing_corpus": {"type": "boolean"},
            "bm25_search_query": {"type": "string"},
            "bm25_search_limit": {"type": "integer"},
        },
    },
    "complaint.import_local_evidence": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "paths": {
                "type": "array",
                "items": {"type": "string"},
            },
            "claim_element_id": {"type": "string"},
            "kind": {"type": "string", "enum": ["testimony", "document"]},
            "evidence_root": {"type": "string"},
        },
        "required": ["paths"],
    },
    "complaint.search_email_duckdb_corpus": {
        "type": "object",
        "properties": {
            "index_path": {"type": "string"},
            "query": {"type": "string"},
            "limit": {"type": "integer"},
            "ranking": {"type": "string"},
            "bm25_k1": {"type": "number"},
            "bm25_b": {"type": "number"},
        },
        "required": ["index_path", "query"],
    },
    "complaint.review_case": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.build_mediator_prompt": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.get_complaint_readiness": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.get_ui_readiness": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.get_client_release_gate": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.get_workflow_capabilities": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.get_tooling_contract": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.get_workspace_data_schema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "manifest_path": {"type": "string"},
            "statefile_path": {"type": "string"},
            "evidence_db_path": {"type": "string"},
            "legal_authority_db_path": {"type": "string"},
            "claim_support_db_path": {"type": "string"},
        },
    },
    "complaint.migrate_legacy_workspace_data": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "output_dir": {"type": "string"},
            "statefile_path": {"type": "string"},
            "evidence_db_path": {"type": "string"},
            "legal_authority_db_path": {"type": "string"},
            "claim_support_db_path": {"type": "string"},
            "package_name": {"type": "string"},
            "include_car": {"type": "boolean"},
        },
    },
    "complaint.search_workspace_dataset": {
        "type": "object",
        "properties": {
            "input_path": {"type": "string"},
            "manifest_path": {"type": "string"},
            "input_type": {"type": "string"},
            "query": {"type": "string"},
            "search_backend": {"type": "string"},
            "top_k": {"type": "integer"},
            "vector_dimension": {"type": "integer"},
            "collection_id": {"type": "string"},
            "document_type": {"type": "string"},
            "claim_type": {"type": "string"},
            "claim_element_id": {"type": "string"},
            "source_type": {"type": "string"},
        },
        "required": ["query"],
    },
    "complaint.view_workspace_dataset": {
        "type": "object",
        "properties": {
            "input_path": {"type": "string"},
            "manifest_path": {"type": "string"},
            "input_type": {"type": "string"},
            "include_document_text": {"type": "boolean"},
            "document_limit": {"type": "integer"},
            "collection_id": {"type": "string"},
            "document_type": {"type": "string"},
            "claim_type": {"type": "string"},
            "claim_element_id": {"type": "string"},
            "source_type": {"type": "string"},
        },
    },
    "complaint.build_mike_handoff": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "mike_base_url": {"type": "string"},
            "project_id": {"type": "string"},
            "workspace_id": {"type": "string"},
            "generate_draft_if_missing": {"type": "boolean"},
            "grounding_mode": {"type": "string"},
        },
    },
    "complaint.get_mike_integration_status": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
        },
    },
    "complaint.generate_grounded_text": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "prompt": {"type": "string"},
            "provider": {"type": "string"},
            "model_name": {"type": "string"},
            "grounding_mode": {"type": "string"},
        },
        "required": ["prompt"],
    },
    "complaint.search_corpus": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
    },
    "complaint.get_handoff": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "mike_base_url": {"type": "string"},
            "project_id": {"type": "string"},
            "workspace_id": {"type": "string"},
            "generate_draft_if_missing": {"type": "boolean"},
            "grounding_mode": {"type": "string"},
        },
    },
    "complaint.sync_draft": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "body": {"type": "string"},
            "title": {"type": "string"},
            "requested_relief": {"type": "array", "items": {"type": "string"}},
            "handoff_id": {"type": "string"},
            "project_id": {"type": "string"},
            "workspace_id": {"type": "string"},
            "mike_document_id": {"type": "string"},
            "citation_links": {"type": "array", "items": {"type": "object"}},
            "redline_summary": {"type": "string"},
            "source_updated_at": {"type": "string"},
            "structured_deltas": {"type": "array", "items": {"type": "object"}},
            "editor_metadata": {"type": "object"},
            "grounding_mode": {"type": "string"},
            "assertion_annotations": {"type": "array", "items": {"type": "object"}},
            "authority_links": {"type": "array", "items": {"type": "object"}},
            "sync_provenance": {"type": "object"},
        },
        "required": ["body"],
    },
    "complaint.sync_mike_final_draft": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "body": {"type": "string"},
            "title": {"type": "string"},
            "requested_relief": {"type": "array", "items": {"type": "string"}},
            "handoff_id": {"type": "string"},
            "project_id": {"type": "string"},
            "workspace_id": {"type": "string"},
            "mike_document_id": {"type": "string"},
            "citation_links": {"type": "array", "items": {"type": "object"}},
            "redline_summary": {"type": "string"},
            "source_updated_at": {"type": "string"},
            "structured_deltas": {"type": "array", "items": {"type": "object"}},
            "editor_metadata": {"type": "object"},
            "grounding_mode": {"type": "string"},
            "assertion_annotations": {"type": "array", "items": {"type": "object"}},
            "authority_links": {"type": "array", "items": {"type": "object"}},
            "sync_provenance": {"type": "object"},
        },
        "required": ["body"],
    },
    "complaint.generate_complaint": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "requested_relief": {
                "type": "array",
                "items": {"type": "string"},
            },
            "title_override": {"type": "string"},
            "use_llm": {"type": "boolean"},
            "provider": {"type": "string"},
            "model": {"type": "string"},
            "config_path": {"type": "string"},
            "backend_id": {"type": "string"},
        },
    },
    "complaint.update_draft": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "requested_relief": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
    "complaint.export_complaint_packet": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.export_complaint_markdown": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.export_complaint_docx": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.export_complaint_pdf": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.analyze_complaint_output": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.get_formal_diagnostics": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.get_filing_provenance": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.get_provider_diagnostics": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.view_docket_dataset": {
        "type": "object",
        "properties": {
            "input_path": {"type": "string"},
            "input_type": {"type": "string", "enum": ["packaged", "json"]},
            "include_document_text": {"type": "boolean"},
            "document_limit": {"type": "integer"},
        },
        "required": ["input_path"],
    },
    "complaint.search_docket_dataset": {
        "type": "object",
        "properties": {
            "input_path": {"type": "string"},
            "input_type": {"type": "string", "enum": ["packaged", "json"]},
            "query": {"type": "string"},
            "search_backend": {"type": "string", "enum": ["bm25", "vector"]},
            "top_k": {"type": "integer"},
            "vector_dimension": {"type": "integer"},
        },
        "required": ["input_path", "query"],
    },
    "complaint.get_docket_dataset_metadata": {
        "type": "object",
        "properties": {
            "input_path": {"type": "string"},
            "input_type": {"type": "string", "enum": ["packaged", "json"]},
        },
        "required": ["input_path"],
    },
    "complaint.get_docket_dataset_graph": {
        "type": "object",
        "properties": {
            "input_path": {"type": "string"},
            "input_type": {"type": "string", "enum": ["packaged", "json"]},
        },
        "required": ["input_path"],
    },
    "complaint.review_generated_exports": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "artifact_path": {"type": "string"},
            "artifact_dir": {"type": "string"},
            "notes": {"type": "string"},
            "provider": {"type": "string"},
            "model": {"type": "string"},
            "config_path": {"type": "string"},
            "backend_id": {"type": "string"},
        },
    },
    "complaint.get_packaged_docket_operator_dashboard": {
        "type": "object",
        "properties": {
            "manifest_path": {"type": "string"},
        },
        "required": ["manifest_path"],
    },
    "complaint.load_packaged_docket_operator_dashboard_report": {
        "type": "object",
        "properties": {
            "manifest_path": {"type": "string"},
            "report_format": {"type": "string", "enum": ["json", "markdown", "text", "parsed", "row"]},
        },
        "required": ["manifest_path"],
    },
    "complaint.execute_packaged_docket_proof_revalidation_queue": {
        "type": "object",
        "properties": {
            "manifest_path": {"type": "string"},
            "top_k": {"type": "integer"},
            "min_priority": {"type": "string"},
            "queue_limit": {"type": "integer"},
            "execution_top_k": {"type": "integer"},
            "chain_until_satisfied": {"type": "boolean"},
            "attach_refreshed_packets": {"type": "boolean"},
        },
        "required": ["manifest_path"],
    },
    "complaint.persist_packaged_docket_proof_revalidation_queue": {
        "type": "object",
        "properties": {
            "manifest_path": {"type": "string"},
            "output_dir": {"type": "string"},
            "package_name": {"type": "string"},
            "include_car": {"type": "boolean"},
            "top_k": {"type": "integer"},
            "min_priority": {"type": "string"},
            "queue_limit": {"type": "integer"},
            "execution_top_k": {"type": "integer"},
            "chain_until_satisfied": {"type": "boolean"},
        },
        "required": ["manifest_path", "output_dir"],
    },
    "complaint.update_claim_type": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "claim_type": {"type": "string"},
        },
        "required": ["claim_type"],
    },
    "complaint.update_case_synopsis": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "synopsis": {"type": "string"},
        },
        "required": ["synopsis"],
    },
    "complaint.reset_session": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
    },
    "complaint.review_ui": {
        "type": "object",
        "properties": {
            "screenshot_paths": {
                "type": "array",
                "items": {"type": "string"},
            },
            "user_id": {"type": "string"},
            "screenshot_dir": {"type": "string"},
            "notes": {"type": "string"},
            "goals": {
                "type": "array",
                "items": {"type": "string"},
            },
            "provider": {"type": "string"},
            "model": {"type": "string"},
            "config_path": {"type": "string"},
            "backend_id": {"type": "string"},
            "output_path": {"type": "string"},
            "iterations": {"type": "integer"},
            "pytest_target": {"type": "string"},
            "reuse_existing_screenshots": {"type": "boolean"},
        },
    },
    "complaint.optimize_ui": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "screenshot_dir": {"type": "string"},
            "output_path": {"type": "string"},
            "notes": {"type": "string"},
            "goals": {
                "type": "array",
                "items": {"type": "string"},
            },
            "provider": {"type": "string"},
            "model": {"type": "string"},
            "iterations": {"type": "integer"},
            "max_rounds": {"type": "integer"},
            "method": {"type": "string"},
            "priority": {"type": "integer"},
            "pytest_target": {"type": "string"},
            "reuse_existing_screenshots": {"type": "boolean"},
        },
        "required": ["screenshot_dir"],
    },
    "complaint.run_browser_audit": {
        "type": "object",
        "properties": {
            "screenshot_dir": {"type": "string"},
            "pytest_target": {"type": "string"},
        },
        "required": ["screenshot_dir"],
    },
}


def _service_inquiry(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    interview = payload.get("interview") if isinstance(payload.get("interview"), dict) else {}
    inquiry = interview.get("inquiry") if isinstance(interview.get("inquiry"), dict) else None
    if inquiry is not None:
        return inquiry
    session = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    projection = session.get("shared_interview") if isinstance(session.get("shared_interview"), dict) else {}
    pending = projection.get("pending_inquiry") if isinstance(projection.get("pending_inquiry"), dict) else None
    return pending


def project_shared_inquiry_contract(payload: Any) -> Any:
    """Copy pending identity, explanation, graph targets, and expected updates.

    Values come from the WorkflowActionService receipt already attached by the
    workspace. This projection does not invent a question, revision, or graph
    update. A stale refusal keeps the current inquiry and sets ``conflict``.
    """
    if not isinstance(payload, dict):
        return payload
    projected = dict(payload)
    inquiry = _service_inquiry(projected)
    interview = projected.get("interview") if isinstance(projected.get("interview"), dict) else {}
    if inquiry is None and not interview:
        return projected
    inquiry = inquiry or {}
    graph = interview.get("graph") if isinstance(interview.get("graph"), dict) else {}
    explanation = dict(projected.get("explanation") or {}) if isinstance(projected.get("explanation"), dict) else {}
    explanation.update({
        "why_it_matters": inquiry.get("why_it_matters"),
        "grounding_status": inquiry.get("grounding_status"),
        "unknown_reasons": list(inquiry.get("unknown_reasons") or []),
        "source": "WorkflowActionService",
    })
    graph_targets = {
        "objective_id": inquiry.get("objective_id"),
        "target_id": inquiry.get("target_id"),
        "target_revision": inquiry.get("target_revision"),
        "graph_id": graph.get("graph_id"),
        "graph_version": graph.get("graph_version"),
        "session_revision": interview.get("session_revision"),
        "legal_sufficiency": False,
    }
    public_inquiry = dict(projected.get("inquiry") or {}) if isinstance(projected.get("inquiry"), dict) else {}
    if inquiry:
        public_inquiry.update({
            "inquiry_id": inquiry.get("inquiry_id"),
            "question_id": inquiry.get("inquiry_id") or public_inquiry.get("question_id"),
            "revision": inquiry.get("revision"),
            "prompt": inquiry.get("question") or public_inquiry.get("prompt") or "",
            "kind": inquiry.get("kind") or public_inquiry.get("kind") or "graph",
            "why_it_matters": inquiry.get("why_it_matters"),
            "objective_id": inquiry.get("objective_id"),
            "target_id": inquiry.get("target_id"),
            "target_revision": inquiry.get("target_revision"),
            "expected_answer_contract": inquiry.get("expected_answer_contract"),
            "expected_update_contract": inquiry.get("expected_update_contract"),
            "grounding_status": inquiry.get("grounding_status"),
            "source_references": inquiry.get("source_references"),
            "legal_sufficiency": False,
        })
    revision = interview.get("expected_question_revision")
    if revision is None:
        revision = inquiry.get("revision")
    projected.update({
        "pending_inquiry_id": inquiry.get("inquiry_id"),
        "expected_question_revision": revision,
        "interview_action": interview.get("action"),
        "explanation": explanation,
        "graph_targets": graph_targets,
        "expected_updates": inquiry.get("expected_update_contract"),
        "inquiry": public_inquiry or projected.get("inquiry"),
        "legal_sufficiency": False,
        "conflict": "stale_question" if shared_inquiry_conflict(projected) else None,
    })
    return projected


def tool_list_payload(service: ComplaintWorkspaceService) -> Dict[str, Any]:
    return {
        "tools": [
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": _TOOL_SCHEMAS.get(tool["name"], {"type": "object"}),
            }
            for tool in service.list_mcp_tools().get("tools", [])
        ]
    }


def _success(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, data: Optional[Any] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        payload["error"]["data"] = data
    return payload


def handle_jsonrpc_message(
    service: ComplaintWorkspaceService,
    request: Any,
    *,
    access: Optional[WorkspaceAccess] = None,
) -> Optional[Dict[str, Any]]:
    """Dispatch one JSON-RPC message under the same principal contract as HTTP.

    ``access`` overrides the service default for this call. When it is omitted,
    the active request scope or the service's explicit trusted-local default applies.
    A tool argument ``user_id`` is never treated as authorization by itself.
    """

    if access is None:
        return _handle_jsonrpc_message(service, request)
    with workspace_access_scope(access):
        return _handle_jsonrpc_message(service, request)


def _handle_jsonrpc_message(
    service: ComplaintWorkspaceService,
    request: Any,
) -> Optional[Dict[str, Any]]:
    if not isinstance(request, dict):
        return _error(None, -32600, "Invalid Request", "JSON-RPC payload must be an object.")

    request_id = request.get("id")
    if request.get("jsonrpc") != JSONRPC_VERSION:
        return _error(request_id, -32600, "Invalid Request", "Expected jsonrpc='2.0'.")

    method = request.get("method")
    if not isinstance(method, str) or not method.strip():
        return _error(request_id, -32600, "Invalid Request", "Missing method.")

    params = request.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _error(request_id, -32602, "Invalid params", "Params must be an object.")

    is_notification = request_id is None

    if method == "notifications/initialized":
        return None if is_notification else _success(request_id, None)

    if method == "exit":
        return None

    if method == "ping":
        return None if is_notification else _success(request_id, {"ok": True})

    if method == "initialize":
        return _success(
            request_id,
            {
                "protocolVersion": negotiated_protocol_version(params),
                "serverInfo": {
                    "name": "complaint-workspace-mcp",
                    "version": "1.0.0",
                },
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "instructions": "Use tools/list and tools/call to drive the complaint workspace workflow.",
            },
        )

    if method == "shutdown":
        return None if is_notification else _success(request_id, None)

    if method == "tools/list":
        return _success(request_id, tool_list_payload(service))

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(tool_name, str) or not tool_name.strip():
            return _error(request_id, -32602, "Invalid params", "tools/call requires params.name.")
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "Invalid params", "tools/call arguments must be an object.")
        try:
            structured = service.call_mcp_tool(tool_name, arguments)
            if tool_name == "complaint.run_intake_chat_turn":
                structured = project_shared_inquiry_contract(structured)
            conflict = tool_name == "complaint.run_intake_chat_turn" and shared_inquiry_conflict(structured)
            inference_failed = gui_inference_tool_failed(tool_name, structured)
            text = "stale_question" if conflict else "mcp_tool_error" if inference_failed else json.dumps(structured, sort_keys=True)
            return _success(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                        }
                    ],
                    "structuredContent": structured,
                    "isError": conflict or inference_failed,
                    "conflict": "stale_question" if conflict else None,
                },
            )
        except Exception as exc:
            message = "authorization_denied" if isinstance(exc, WorkspaceAuthorizationDenied) else "workspace_operation_failed"
            return _success(
                request_id,
                {
                    "content": [{"type": "text", "text": message}],
                    "isError": True,
                },
            )

    return _error(request_id, -32601, "Method not found", method)
