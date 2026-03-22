import json

from typer.testing import CliRunner

try:
    import python_multipart  # type: ignore  # noqa: F401
    HAS_MULTIPART = True
except ModuleNotFoundError:
    HAS_MULTIPART = False

from complaint_generator import (
    ComplaintWorkspaceService,
    create_review_surface_app,
    handle_jsonrpc_message,
    tool_list_payload,
)
from complaint_generator import cli as cli_module
from applications import complaint_cli as applications_cli_module


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
    assert initialize_payload["result"]["serverInfo"]["name"] == "complaint-workspace-mcp"
    if HAS_MULTIPART:
        app = create_review_surface_app(mediator=object())
        assert any(
            getattr(route, "path", None) == "/workspace"
            for route in app.routes
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