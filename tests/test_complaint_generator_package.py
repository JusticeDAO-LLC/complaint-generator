from typer.testing import CliRunner

from complaint_generator import (
    ComplaintWorkspaceService,
    complaint_mcp_server_main,
    complaint_workspace_cli_main,
    create_complaint_workspace_router,
    create_review_dashboard_app,
    create_review_surface_app,
    handle_jsonrpc_message,
    tool_list_payload,
)
from complaint_generator.cli import app as complaint_workspace_cli_app
from complaint_generator.entrypoints import main as complaint_generator_main


def test_package_exports_unified_workspace_and_review_helpers():
    service = ComplaintWorkspaceService()

    assert create_complaint_workspace_router is not None
    assert create_review_dashboard_app is not None
    assert create_review_surface_app is not None
    assert complaint_workspace_cli_main is not None
    assert complaint_mcp_server_main is not None

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


def test_console_entrypoint_targets_run_main():
    assert complaint_generator_main is not None