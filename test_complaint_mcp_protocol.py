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
