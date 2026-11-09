import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

from applications.complaint_mcp_protocol import handle_jsonrpc_message
from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import create_complaint_workspace_router


def _intake(service: ComplaintWorkspaceService, user_id: str) -> None:
    service.submit_intake_answers(
        user_id,
        {
            "party_name": "Taylor Smith",
            "opposing_party": "Acme Logistics",
            "protected_activity": "Reported safety violations",
            "adverse_action": "Termination",
            "timeline": "Reported on April 2; terminated on April 5",
            "harm": "Lost wages",
        },
    )


def test_initialize_echoes_supported_version_and_get_handoff_is_structured(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    user_id = "mcp-handshake-user"
    _intake(service, user_id)

    initialized = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "pytest", "version": "1"}},
        },
    )
    assert initialized["result"]["protocolVersion"] == "2025-06-18"
    assert initialized["result"]["serverInfo"]["name"] == "complaint-workspace-mcp"

    listed = handle_jsonrpc_message(
        service,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert {
        "complaint.generate_grounded_text",
        "complaint.search_corpus",
        "complaint.get_handoff",
        "complaint.sync_draft",
    }.issubset(names)

    called = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "complaint.get_handoff", "arguments": {"user_id": user_id}},
        },
    )
    assert called["result"]["isError"] is False
    assert called["result"]["content"][0]["type"] == "text"
    assert called["result"]["structuredContent"]["user_id"] == user_id


def test_unsupported_protocol_version_falls_back_to_default(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    missing = handle_jsonrpc_message(
        service,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    unknown = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {"protocolVersion": "1999-01-01"},
        },
    )
    assert missing["result"]["protocolVersion"] == "2025-06-18"
    assert unknown["result"]["protocolVersion"] == "2025-06-18"


def test_rpc_route_requires_bearer_only_when_token_is_configured(tmp_path, monkeypatch):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    app = FastAPI()
    app.include_router(create_complaint_workspace_router(service))
    client = TestClient(app)
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

    monkeypatch.delenv("COMPLAINT_MCP_AUTH_TOKEN", raising=False)
    open_response = client.post("/api/complaint-workspace/mcp/rpc", json=body)
    assert open_response.status_code == 200
    assert open_response.headers["content-type"].startswith("application/json")
    assert "complaint.get_handoff" in {tool["name"] for tool in open_response.json()["result"]["tools"]}

    monkeypatch.setenv("COMPLAINT_MCP_AUTH_TOKEN", "desk-token")
    rejected = client.post("/api/complaint-workspace/mcp/rpc", json=body)
    assert rejected.status_code == 401
    accepted = client.post(
        "/api/complaint-workspace/mcp/rpc",
        json=body,
        headers={"Authorization": "Bearer desk-token"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["result"]["tools"]


def test_handoff_setup_text_names_streamable_https_registration():
    text = ComplaintWorkspaceService._mike_connector_setup_text(True)
    unavailable = ComplaintWorkspaceService._mike_connector_setup_text(False)
    for sample in (text, unavailable):
        assert "Streamable HTTP" in sample
        assert "public https" in sample
        assert "localhost" in sample
        assert "COMPLAINT_MCP_AUTH_TOKEN" in sample
        assert "compatibility-only" in sample
        assert "/api/complaint-workspace/mcp/rpc" in sample
    assert "unavailable" in unavailable
    assert "connector" in unavailable
    assert "routers" in unavailable
