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
    build_mediator_prompt,
    build_ui_ux_review_prompt,
    create_identity,
    run_closed_loop_ui_ux_improvement,
    run_end_to_end_complaint_browser_audit,
    create_review_dashboard_app,
    create_ui_review_report,
    create_review_surface_app,
    export_complaint_packet,
    generate_decentralized_id,
    generate_complaint,
    get_workflow_capabilities,
    handle_jsonrpc_message,
    list_claim_elements,
    list_intake_questions,
    list_mcp_tools,
    reset_session,
    review_case,
    run_iterative_ui_ux_workflow,
    run_playwright_screenshot_audit,
    save_evidence,
    start_session,
    submit_intake_answers,
    tool_list_payload,
    update_case_synopsis,
    update_draft,
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
    assert callable(create_identity)
    assert callable(start_session)
    assert callable(list_intake_questions)
    assert callable(list_claim_elements)
    assert callable(submit_intake_answers)
    assert callable(save_evidence)
    assert callable(review_case)
    assert callable(build_mediator_prompt)
    assert callable(get_workflow_capabilities)
    assert callable(generate_complaint)
    assert callable(update_draft)
    assert callable(export_complaint_packet)
    assert callable(update_case_synopsis)
    assert callable(reset_session)
    assert callable(list_mcp_tools)
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


def test_package_workspace_wrappers_execute_full_complaint_flow(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "package-wrapper-sessions")

    identity_payload = create_identity(service=service)
    assert str(identity_payload["did"]).startswith("did:key:")

    session_payload = start_session("package-wrapper-user", service=service)
    assert session_payload["session"]["user_id"] == "package-wrapper-user"

    questions_payload = list_intake_questions(service=service)
    claim_elements_payload = list_claim_elements(service=service)
    assert questions_payload["questions"][0]["id"] == "party_name"
    assert claim_elements_payload["claim_elements"][0]["id"] == "protected_activity"

    intake_payload = submit_intake_answers(
        "package-wrapper-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10.",
            "harm": "Lost wages and emotional distress.",
        },
        service=service,
    )
    assert intake_payload["session"]["intake_answers"]["party_name"] == "Jordan Example"

    evidence_payload = save_evidence(
        "package-wrapper-user",
        kind="document",
        claim_element_id="causation",
        title="Termination email",
        content="Termination followed immediately after the report.",
        source="Inbox export",
        attachment_names=["termination-email.txt"],
        service=service,
    )
    assert evidence_payload["saved"]["title"] == "Termination email"

    synopsis_payload = update_case_synopsis(
        "package-wrapper-user",
        "Jordan Example alleges retaliation after reporting discrimination to HR.",
        service=service,
    )
    assert synopsis_payload["session"]["case_synopsis"].startswith("Jordan Example alleges retaliation")

    review_payload = review_case("package-wrapper-user", service=service)
    mediator_payload = build_mediator_prompt("package-wrapper-user", service=service)
    capabilities_payload = get_workflow_capabilities("package-wrapper-user", service=service)
    assert "case_synopsis" in review_payload["review"]
    assert "Mediator, help turn this into testimony-ready narrative" in mediator_payload["prefill_message"]
    assert any(item["id"] == "complaint_packet" for item in capabilities_payload["capabilities"])

    draft_payload = generate_complaint(
        "package-wrapper-user",
        requested_relief=["Back pay", "Injunctive relief"],
        title_override="Package wrapper complaint",
        service=service,
    )
    assert draft_payload["draft"]["title"] == "Package wrapper complaint"

    updated_payload = update_draft(
        "package-wrapper-user",
        title="Edited package wrapper complaint",
        body="Edited body from package wrapper flow.",
        requested_relief=["Reinstatement"],
        service=service,
    )
    assert updated_payload["draft"]["title"] == "Edited package wrapper complaint"

    export_payload = export_complaint_packet("package-wrapper-user", service=service)
    tools_payload = list_mcp_tools(service=service)
    assert export_payload["packet_summary"]["has_draft"] is True
    assert any(tool["name"] == "complaint.run_browser_audit" for tool in tools_payload["tools"])

    reset_payload = reset_session("package-wrapper-user", service=service)
    assert reset_payload["session"]["intake_answers"] == {}


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
