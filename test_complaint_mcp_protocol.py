from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import complaint_generator
from applications.complaint_mcp_protocol import handle_jsonrpc_message
from applications.complaint_workspace import ComplaintWorkspaceService


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


def test_public_package_exports_workspace_service():
    assert complaint_generator.ComplaintWorkspaceService is ComplaintWorkspaceService
    assert complaint_generator.DEFAULT_INTAKE_QUESTIONS[0]["id"] == "party_name"
    assert complaint_generator.DEFAULT_CLAIM_ELEMENTS[0]["id"] == "protected_activity"


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

    assert "Mediator, help turn this into testimony-ready narrative" in mediator_response["result"]["structuredContent"]["prefill_message"]
    assert export_response["result"]["structuredContent"]["packet"]["draft"]["body"]
