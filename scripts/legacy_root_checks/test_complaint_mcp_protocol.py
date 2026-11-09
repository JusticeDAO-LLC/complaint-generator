from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import complaint_generator
from complaint_generator.mcp import handle_jsonrpc_message
from complaint_generator.workspace import ComplaintWorkspaceService


def test_tools_list_uses_jsonrpc_shape(tmp_path):
    service = ComplaintWorkspaceService(tmp_path)
    response = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        },
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "result" in response
    assert response["result"]["tools"]
    assert response["result"]["tools"][0]["name"].startswith("complaint.")
    tools_by_name = {tool["name"]: tool for tool in response["result"]["tools"]}
    assert tools_by_name["complaint.build_mike_handoff"]["inputSchema"]["properties"]["generate_draft_if_missing"]["type"] == "boolean"
    assert tools_by_name["complaint.build_mike_handoff"]["inputSchema"]["properties"]["grounding_mode"]["type"] == "string"
    assert tools_by_name["complaint.sync_mike_final_draft"]["inputSchema"]["required"] == ["body"]
    assert tools_by_name["complaint.sync_mike_final_draft"]["inputSchema"]["properties"]["assertion_annotations"]["type"] == "array"
    assert tools_by_name["complaint.sync_mike_final_draft"]["inputSchema"]["properties"]["authority_links"]["type"] == "array"


def test_public_package_exports_workspace_service():
    assert complaint_generator.ComplaintWorkspaceService is ComplaintWorkspaceService
    assert complaint_generator.DEFAULT_INTAKE_QUESTIONS[0]["id"] == "party_name"
    assert complaint_generator.DEFAULT_CLAIM_ELEMENTS[0]["id"] == "protected_activity"
    assert complaint_generator.get_complaint_readiness is not None
    assert complaint_generator.get_ui_readiness is not None
    assert complaint_generator.get_client_release_gate is not None


def test_tools_call_returns_structured_content(tmp_path):
    service = ComplaintWorkspaceService(tmp_path)
    response = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "complaint.submit_intake",
                "arguments": {
                    "user_id": "demo-user",
                    "answers": {
                        "party_name": "Jane Doe",
                    },
                },
            },
        },
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 2
    assert response["result"]["isError"] is False
    assert response["result"]["structuredContent"]["session"]["intake_answers"]["party_name"] == "Jane Doe"


def test_mcp_protocol_exposes_mediator_prompt_and_packet_export(tmp_path):
    service = ComplaintWorkspaceService(tmp_path)
    service.submit_intake_answers(
        "demo-user",
        {
            "party_name": "Jane Doe",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Termination two days later",
        },
    )
    mediator_response = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "complaint.build_mediator_prompt",
                "arguments": {"user_id": "demo-user"},
            },
        },
    )
    export_response = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "complaint.export_complaint_packet",
                "arguments": {"user_id": "demo-user"},
            },
        },
    )
    readiness_response = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "complaint.get_complaint_readiness",
                "arguments": {"user_id": "demo-user"},
            },
        },
    )
    service._persist_ui_readiness(
        "demo-user",
        {
            "review": {
                "summary": "Persisted UI review.",
                "critic_review": {"verdict": "warning", "acceptance_checks": ["Keep the end-to-end complaint browser path passing."]},
                "complaint_journey": {"release_blockers": ["Fix the draft handoff before sending legal clients here."]},
            }
        },
    )
    cached_ui_response = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "complaint.get_ui_readiness",
                "arguments": {"user_id": "demo-user"},
            },
        },
    )
    combined_release_gate = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "complaint.get_client_release_gate",
                "arguments": {"user_id": "demo-user"},
            },
        },
    )
    mike_handoff = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "complaint.build_mike_handoff",
                "arguments": {
                    "user_id": "demo-user",
                    "project_id": "project-demo",
                    "workspace_id": "workspace-demo",
                },
            },
        },
    )
    handoff_id = mike_handoff["result"]["structuredContent"]["handoff_id"]
    mike_status_after_handoff = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "complaint.get_mike_integration_status",
                "arguments": {"user_id": "demo-user"},
            },
        },
    )
    mike_sync = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "complaint.sync_mike_final_draft",
                "arguments": {
                    "user_id": "demo-user",
                    "handoff_id": handoff_id,
                    "title": "Mike Synced Draft",
                    "body": "This draft was synced from Mike.",
                    "citation_links": [
                        {"citation_id": "cite-1", "claim_element_id": "causation"},
                        {"citation_id": "cite-1", "claim_element_id": "harm"},
                        {"citation_id": "cite-2", "claim_element_id": "unknown"},
                    ],
                    "structured_deltas": [
                        {"op": "replace", "target": "paragraph-001", "before": "old", "after": "new"},
                    ],
                    "editor_metadata": {
                        "editor_user_id": "editor-mcp",
                        "editor_session_id": "session-mcp",
                    },
                    "sync_provenance": {
                        "editor_version": "mike-web",
                        "skill_asset_ids": ["complaint-grounding", "complaint-logic"],
                        "redline_metadata": {"summary": "Applied citation-safe edits."},
                    },
                },
            },
        },
    )
    mike_status_after_sync = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "complaint.get_mike_integration_status",
                "arguments": {"user_id": "demo-user"},
            },
        },
    )

    assert "Mediator, help turn this into testimony-ready narrative" in mediator_response["result"]["structuredContent"]["prefill_message"]
    assert export_response["result"]["structuredContent"]["packet"]["draft"]["body"]
    assert readiness_response["result"]["structuredContent"]["verdict"] in {
        "Not ready to draft",
        "Still building the record",
        "Ready for first draft",
        "Draft in progress",
    }
    assert cached_ui_response["result"]["structuredContent"]["verdict"] in {
        "No UI verdict cached",
        "Needs repair",
        "Client-safe",
        "Do not send to clients yet",
    }
    assert combined_release_gate["result"]["structuredContent"]["verdict"] in {
        "client_safe",
        "warning",
        "blocked",
    }
    assert handoff_id.startswith("mike-handoff-")
    assert mike_handoff["result"]["structuredContent"]["mike"]["launch_url"]
    actual_asset_ids = mike_handoff["result"]["structuredContent"]["handoff_payload"]["skill_asset_manifest"]["asset_ids"]
    for expected_id in [
        "complaint-grounding",
        "complaint-logic",
        "complaint-corpus-search",
        "complaint-policy-rules",
        "complaint-authority-graphs",
        "complaint-router",
        "complaint-draft-logic-pipeline",
        "complaint-corpus-containment",
        "complaint-mike-llm-patch",
    ]:
        assert expected_id in actual_asset_ids, f"Expected skill asset '{expected_id}' in manifest"
    handoff_status_payload = mike_status_after_handoff["result"]["structuredContent"]
    assert handoff_status_payload["pending_sync"] is True
    assert handoff_status_payload["status_contract_version"] == "complaint-mike-status-v4"
    assert handoff_status_payload["workflow_state"]["key"] == "handoff_pending_sync"
    assert handoff_status_payload["latest_sync_handoff_id"] is None
    assert handoff_status_payload["has_citation_link_conflicts"] is False
    assert handoff_status_payload["citation_link_conflict_count"] == 0
    assert handoff_status_payload["citation_link_unknown_element_count"] == 0
    assert (
        "Latest Mike handoff has not been synced yet."
        in handoff_status_payload["recommended_action"]
    )
    assert mike_sync["result"]["structuredContent"]["draft"]["sync_source"] == "mike"
    assert mike_sync["result"]["structuredContent"]["sync_record"]["citation_link_conflict_count"] == 1
    assert mike_sync["result"]["structuredContent"]["sync_record"]["structured_delta_count"] == 1
    assert mike_sync["result"]["structuredContent"]["sync_record"]["editor_user_id"] == "editor-mcp"
    assert mike_sync["result"]["structuredContent"]["sync_record"]["editor_version"] == "mike-web"
    assert mike_sync["result"]["structuredContent"]["sync_provenance"]["enabled_skill_ids"] == [
        "complaint-grounding",
        "complaint-logic",
    ]
    assert mike_sync["result"]["structuredContent"]["redline_metadata"]["structured_delta_count"] == 1
    assert mike_sync["result"]["structuredContent"]["sync_diagnostics"]["severity"] == "error"
    assert mike_sync["result"]["structuredContent"]["citation_link_check"]["has_conflicts"] is True
    assert mike_sync["result"]["structuredContent"]["citation_link_check"]["unknown_claim_element_ids"] == ["unknown"]
    assert mike_sync["result"]["structuredContent"]["citation_link_check"]["conflicts"] == [
        {"citation_id": "cite-1", "claim_element_ids": ["causation", "harm"]}
    ]
    assert mike_status_after_sync["result"]["structuredContent"]["pending_sync"] is False
    assert mike_status_after_sync["result"]["structuredContent"]["workflow_state"]["key"] == "synced_with_conflicts"
    assert mike_status_after_sync["result"]["structuredContent"]["latest_sync_handoff_id"] == handoff_id
    assert mike_status_after_sync["result"]["structuredContent"]["has_citation_link_conflicts"] is True
    assert mike_status_after_sync["result"]["structuredContent"]["citation_link_conflict_count"] == 1
    assert mike_status_after_sync["result"]["structuredContent"]["citation_link_unknown_element_count"] == 1
    assert (
        "Resolve conflicts in Mike and sync again before export."
        in mike_status_after_sync["result"]["structuredContent"]["recommended_action"]
    )
