import json
import os
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

try:
    import python_multipart  # type: ignore  # noqa: F401
    HAS_MULTIPART = True
except ModuleNotFoundError:
    HAS_MULTIPART = False

from complaint_generator import (
    ComplaintWorkspaceService,
    build_ui_ux_review_prompt,
    run_closed_loop_ui_ux_improvement,
    run_end_to_end_complaint_browser_audit,
    create_review_dashboard_app,
    create_ui_review_report,
    create_review_surface_app,
    generate_decentralized_id,
    handle_jsonrpc_message,
    run_iterative_ui_ux_workflow,
    run_playwright_screenshot_audit,
    tool_list_payload,
)
from complaint_generator import cli as cli_module
from applications import complaint_cli as applications_cli_module


REPO_ROOT = Path(__file__).resolve().parents[1]


def _script_path(script_name: str) -> Path:
    scripts_dir = Path(sys.executable).parent
    suffix = ".exe" if sys.platform.startswith("win") else ""
    return scripts_dir / f"{script_name}{suffix}"


def _ensure_editable_console_scripts() -> None:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", ".", "--no-deps"],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _extract_json_payload(stdout: str) -> dict:
    lines = [line for line in (stdout or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("{"):
            return json.loads("\n".join(lines[index:]))
    raise AssertionError(f"No JSON payload found in stdout: {stdout!r}")


def test_complaint_generator_package_exports_workspace_review_and_mcp_surfaces(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)

    session_payload = service.get_session("package-user")
    tool_payload = tool_list_payload(service)
    initialize_payload = handle_jsonrpc_message(
        service,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert session_payload["session"]["user_id"] == "package-user"
    assert any(tool["name"] == "complaint.generate_complaint" for tool in tool_payload["tools"])
    assert any(tool["name"] == "complaint.update_case_synopsis" for tool in tool_payload["tools"])
    assert any(tool["name"] == "complaint.review_ui" for tool in tool_payload["tools"])
    assert any(tool["name"] == "complaint.optimize_ui" for tool in tool_payload["tools"])
    assert any(tool["name"] == "complaint.run_browser_audit" for tool in tool_payload["tools"])
    assert initialize_payload["result"]["serverInfo"]["name"] == "complaint-workspace-mcp"
    assert callable(generate_decentralized_id)
    assert callable(build_ui_ux_review_prompt)
    assert callable(create_ui_review_report)
    assert callable(create_review_dashboard_app)
    assert callable(run_closed_loop_ui_ux_improvement)
    assert callable(run_end_to_end_complaint_browser_audit)
    assert callable(run_iterative_ui_ux_workflow)
    assert callable(run_playwright_screenshot_audit)
    if HAS_MULTIPART:
        app = create_review_surface_app(mediator=object())
        assert any(
            getattr(route, "path", None) == "/workspace"
            for route in app.routes
        )
        dashboard_app = create_review_dashboard_app()
        assert any(
            getattr(route, "path", None) == "/claim-support-review"
            for route in dashboard_app.routes
        )
    else:
        assert callable(create_review_surface_app)


def test_complaint_generator_cli_wrapper_exposes_workspace_commands(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(applications_cli_module, "service", ComplaintWorkspaceService(root_dir=tmp_path))

    result = runner.invoke(cli_module.app, ["session", "--user-id", "package-cli-user"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["session"]["user_id"] == "package-cli-user"


def test_installed_console_scripts_expose_cli_and_mcp_entrypoints(tmp_path):
    _ensure_editable_console_scripts()

    workspace_script = _script_path("complaint-workspace")
    workspace_alias_script = _script_path("complaint-generator-workspace")
    generator_script = _script_path("complaint-generator")
    mcp_script = _script_path("complaint-mcp-server")
    mcp_alias_script = _script_path("complaint-generator-mcp")
    workflow_script = _script_path("complaint-ui-ux-workflow")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)

    workspace_result = subprocess.run(
        [str(workspace_script), "session", "--user-id", "installed-script-user"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    workspace_alias_result = subprocess.run(
        [str(workspace_alias_script), "session", "--user-id", "alias-script-user"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    generator_help_result = subprocess.run(
        [str(generator_script), "--help"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    workflow_help_result = subprocess.run(
        [str(workflow_script), "--help"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    mcp_result = subprocess.run(
        [str(mcp_script)],
        cwd=REPO_ROOT,
        env=env,
        input='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n{"jsonrpc":"2.0","id":2,"method":"exit","params":{}}\n',
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    mcp_alias_result = subprocess.run(
        [str(mcp_alias_script)],
        cwd=REPO_ROOT,
        env=env,
        input='{"jsonrpc":"2.0","id":3,"method":"initialize","params":{}}\n{"jsonrpc":"2.0","id":4,"method":"exit","params":{}}\n',
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    workspace_payload = _extract_json_payload(workspace_result.stdout)
    workspace_alias_payload = _extract_json_payload(workspace_alias_result.stdout)
    mcp_initialize_payload = _extract_json_payload(mcp_result.stdout)
    mcp_alias_initialize_payload = _extract_json_payload(mcp_alias_result.stdout)

    assert workspace_script.exists()
    assert workspace_alias_script.exists()
    assert generator_script.exists()
    assert mcp_script.exists()
    assert mcp_alias_script.exists()
    assert workflow_script.exists()
    assert workspace_payload["session"]["user_id"] == "installed-script-user"
    assert workspace_alias_payload["session"]["user_id"] == "alias-script-user"
    assert "Complaint Generator" in generator_help_result.stdout
    assert "screenshot audit" in workflow_help_result.stdout.lower()
    assert mcp_initialize_payload["result"]["serverInfo"]["name"] == "complaint-workspace-mcp"
    assert mcp_alias_initialize_payload["result"]["serverInfo"]["name"] == "complaint-workspace-mcp"
