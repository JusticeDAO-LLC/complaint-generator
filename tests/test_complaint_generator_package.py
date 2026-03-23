from typer.testing import CliRunner

from complaint_generator import (
    ComplaintWorkspaceService,
    DEFAULT_CLAIM_ELEMENTS,
    DEFAULT_INTAKE_QUESTIONS,
    complaint_mcp_server_main,
    complaint_workspace_cli_main,
    create_complaint_workspace_router,
    get_complaint_readiness,
    handle_jsonrpc_message,
    tool_list_payload,
)
from complaint_generator.cli import app as complaint_workspace_cli_app
from complaint_generator.entrypoints import main as complaint_generator_main
from complaint_generator.review import create_review_dashboard_app, create_review_surface_app


def test_package_exports_unified_workspace_and_review_helpers():
    service = ComplaintWorkspaceService()

    assert DEFAULT_INTAKE_QUESTIONS[0]["id"] == "party_name"
    assert DEFAULT_CLAIM_ELEMENTS[0]["id"] == "protected_activity"
    assert create_complaint_workspace_router is not None
    assert create_review_dashboard_app is not None
    assert create_review_surface_app is not None
    assert complaint_workspace_cli_main is not None
    assert complaint_mcp_server_main is not None
    assert get_complaint_readiness is not None

    tool_payload = tool_list_payload(service)
    assert tool_payload["tools"]
    assert tool_payload["tools"][0]["name"].startswith("complaint.")

    response = handle_jsonrpc_message(
        service,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response is not None
    assert response["result"]["tools"]


def test_workspace_cli_is_packaged_through_top_level_module(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr("applications.complaint_cli.service", ComplaintWorkspaceService(tmp_path))

    result = runner.invoke(complaint_workspace_cli_app, ["session", "--user-id", "pkg-user"])

    assert result.exit_code == 0
    assert '"user_id": "pkg-user"' in result.stdout


def test_mcp_generate_complaint_returns_draft_for_new_session(tmp_path):
    service = ComplaintWorkspaceService(tmp_path)

    response = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "complaint.generate_complaint",
                "arguments": {"user_id": "pkg-user"},
            },
        },
    )

    assert response is not None
    assert response["result"]["isError"] is False
    assert response["result"]["structuredContent"]["draft"]["body"]
    assert response["result"]["structuredContent"]["draft"]["case_synopsis"]
    assert response["result"]["structuredContent"]["draft"]["review_snapshot"]["case_synopsis"]


def test_console_entrypoint_targets_run_main():
    assert complaint_generator_main is not None
