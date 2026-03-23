import io
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from complaint_generator import (
    ComplaintWorkspaceService,
    attach_complaint_workspace_routes,
    complaint_cli_main,
    complaint_generator_main,
    complaint_mcp_server_main,
    create_complaint_workspace_router,
    create_review_surface_app,
    handle_jsonrpc_message,
    run_main,
    tool_list_payload,
)
from applications import complaint_cli as complaint_cli_impl
from complaint_generator import cli as complaint_cli_module
from complaint_generator import entrypoints as complaint_entrypoints
from complaint_generator import mcp_server as complaint_mcp_server_module


REPO_ROOT = Path(__file__).resolve().parent.parent
pytestmark = [pytest.mark.no_auto_network]


def test_packaging_metadata_includes_playwright_and_console_entry_points():
    requirements_text = (REPO_ROOT / "requirements.txt").read_text()
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text()
    setup_text = (REPO_ROOT / "setup.py").read_text()
    manifest_text = (REPO_ROOT / "MANIFEST.in").read_text()

    assert "playwright>=" in requirements_text
    assert '"playwright>=' in pyproject_text
    assert '"playwright>=' in setup_text

    for script_name in (
        "complaint-generator",
        "complaint-workspace",
        "complaint-generator-workspace",
        "complaint-mcp-server",
        "complaint-generator-mcp",
        "complaint-ui-ux-workflow",
    ):
        assert script_name in pyproject_text
        assert script_name in setup_text

    assert "recursive-include templates *.html" in manifest_text
    assert "recursive-include static *.js *.mjs *.css" in manifest_text


def test_package_exports_expose_workspace_review_and_entrypoint_helpers():
    assert ComplaintWorkspaceService is not None
    assert attach_complaint_workspace_routes is not None
    assert create_complaint_workspace_router is not None
    assert create_review_surface_app is not None
    assert handle_jsonrpc_message is not None
    assert tool_list_payload is not None
    assert complaint_cli_main is complaint_cli_module.main
    assert complaint_mcp_server_main is complaint_mcp_server_module.main
    assert complaint_generator_main is complaint_entrypoints.main
    assert run_main is complaint_entrypoints.run_main


def test_workspace_cli_is_exposed_through_package_entrypoint(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "workspace-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)

    result = runner.invoke(
        complaint_cli_module.app,
        [
            "answer",
            "--user-id",
            "pkg-user",
            "--question-id",
            "protected_activity",
            "--answer-text",
            "Reported retaliation to HR",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["session"]["user_id"] == "pkg-user"
    assert payload["session"]["intake_answers"]["protected_activity"] == "Reported retaliation to HR"


def test_stdio_mcp_server_responds_with_initialize_and_tool_payload(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "mcp-sessions")
    stdin = io.StringIO(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "pytest", "version": "1.0"}},
            }
        )
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 3, "method": "exit", "params": {}})
        + "\n"
    )
    stdout = io.StringIO()

    monkeypatch.setattr("applications.complaint_mcp_server.ComplaintWorkspaceService", lambda: service)
    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr("sys.stdout", stdout)

    complaint_mcp_server_module.main()

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert lines[0]["result"]["serverInfo"]["name"] == "complaint-workspace-mcp"
    assert lines[0]["result"]["protocolVersion"] == "2026-03-22"
    assert any(tool["name"] == "complaint.generate_complaint" for tool in lines[1]["result"]["tools"])
