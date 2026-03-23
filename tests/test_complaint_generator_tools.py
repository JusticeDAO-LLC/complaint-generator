import json

import pytest
from typer.testing import CliRunner

from applications import complaint_cli as complaint_cli_impl
from applications.complaint_mcp_protocol import handle_jsonrpc_message, tool_list_payload
from complaint_generator import ComplaintWorkspaceService


pytestmark = [pytest.mark.no_auto_network]


def _invoke_cli(runner: CliRunner, *args: str):
    result = runner.invoke(complaint_cli_impl.app, list(args))
    assert result.exit_code == 0, result.stdout
    lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.lstrip().startswith("{"):
            return json.loads("\n".join(lines[index:]))
    raise AssertionError(f"No JSON payload found in stdout: {result.stdout!r}")


def _call_mcp_tool(service: ComplaintWorkspaceService, request_id: int, tool_name: str, arguments: dict):
    response = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        },
    )
    assert response is not None
    assert "error" not in response
    result = response["result"]
    assert result["isError"] is False
    return result["structuredContent"]


def test_tool_list_exposes_all_complaint_cli_and_mcp_tools(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "tool-list-sessions")
    payload = tool_list_payload(service)
    tool_names = [tool["name"] for tool in payload["tools"]]

    assert tool_names == [
        "complaint.create_identity",
        "complaint.list_intake_questions",
        "complaint.list_claim_elements",
        "complaint.start_session",
        "complaint.submit_intake",
        "complaint.save_evidence",
        "complaint.review_case",
        "complaint.build_mediator_prompt",
        "complaint.get_workflow_capabilities",
        "complaint.generate_complaint",
        "complaint.update_draft",
        "complaint.export_complaint_packet",
        "complaint.update_case_synopsis",
        "complaint.reset_session",
        "complaint.review_ui",
        "complaint.optimize_ui",
        "complaint.run_browser_audit",
    ]
    assert all("inputSchema" in tool for tool in payload["tools"])


def test_all_cli_commands_are_exercised_end_to_end(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "cli-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)

    session_payload = _invoke_cli(runner, "session", "--user-id", "cli-user")
    assert session_payload["session"]["user_id"] == "cli-user"
    assert session_payload["next_question"]["id"] == "party_name"

    identity_payload = _invoke_cli(runner, "identity")
    assert str(identity_payload["did"]).startswith("did:key:")

    questions_payload = _invoke_cli(runner, "questions")
    assert questions_payload["questions"][0]["id"] == "party_name"

    claim_elements_payload = _invoke_cli(runner, "claim-elements")
    assert claim_elements_payload["claim_elements"][0]["id"] == "protected_activity"

    tools_payload = _invoke_cli(runner, "tools")
    assert any(tool["name"] == "complaint.review_ui" for tool in tools_payload["tools"])
    assert any(tool["name"] == "complaint.optimize_ui" for tool in tools_payload["tools"])
    assert any(tool["name"] == "complaint.export_complaint_packet" for tool in tools_payload["tools"])

    answer_payload = _invoke_cli(
        runner,
        "answer",
        "--user-id",
        "cli-user",
        "--question-id",
        "protected_activity",
        "--answer-text",
        "Reported discrimination to HR",
    )
    assert answer_payload["session"]["intake_answers"]["protected_activity"] == "Reported discrimination to HR"

    evidence_payload = _invoke_cli(
        runner,
        "add-evidence",
        "--user-id",
        "cli-user",
        "--kind",
        "document",
        "--claim-element-id",
        "causation",
        "--title",
        "Termination email",
        "--content",
        "Termination followed immediately after the report.",
        "--source",
        "Inbox export",
        "--attachment-names",
        "termination-email.txt|timeline-notes.txt",
    )
    assert evidence_payload["saved"]["kind"] == "document"
    assert evidence_payload["saved"]["title"] == "Termination email"
    assert evidence_payload["saved"]["attachment_names"] == ["termination-email.txt", "timeline-notes.txt"]

    review_payload = _invoke_cli(runner, "review", "--user-id", "cli-user")
    assert review_payload["review"]["claim_type"] == "retaliation"
    assert review_payload["session"]["user_id"] == "cli-user"
    assert "case_synopsis" in review_payload
    assert "Reported discrimination to HR" in review_payload["review"]["case_synopsis"]

    mediator_payload = _invoke_cli(runner, "mediator-prompt", "--user-id", "cli-user")
    assert "Mediator, help turn this into testimony-ready narrative" in mediator_payload["prefill_message"]

    capabilities_payload = _invoke_cli(runner, "capabilities", "--user-id", "cli-user")
    assert any(item["id"] == "complaint_packet" for item in capabilities_payload["capabilities"])

    generate_payload = _invoke_cli(
        runner,
        "generate",
        "--user-id",
        "cli-user",
        "--requested-relief",
        "Back pay|Injunctive relief",
        "--title-override",
        "CLI generated complaint",
    )
    assert generate_payload["draft"]["title"] == "CLI generated complaint"
    assert generate_payload["draft"]["requested_relief"] == ["Back pay", "Injunctive relief"]
    assert "Working case synopsis:" in generate_payload["draft"]["body"]
    assert "Reported discrimination to HR" in generate_payload["draft"]["case_synopsis"]

    update_payload = _invoke_cli(
        runner,
        "update-draft",
        "--user-id",
        "cli-user",
        "--title",
        "Edited CLI complaint",
        "--body",
        "Edited complaint body from CLI.",
        "--requested-relief",
        "Reinstatement|Fees",
    )
    assert update_payload["draft"]["title"] == "Edited CLI complaint"
    assert update_payload["draft"]["body"] == "Edited complaint body from CLI."
    assert update_payload["draft"]["requested_relief"] == ["Reinstatement", "Fees"]

    export_payload = _invoke_cli(runner, "export-packet", "--user-id", "cli-user")
    assert export_payload["packet"]["draft"]["title"] == "Edited CLI complaint"
    assert export_payload["packet_summary"]["has_draft"] is True

    synopsis_payload = _invoke_cli(
        runner,
        "update-synopsis",
        "--user-id",
        "cli-user",
        "--synopsis",
        "Jordan Example alleges retaliation after reporting discrimination to HR and needs stronger causation support.",
    )
    assert synopsis_payload["case_synopsis"].startswith("Jordan Example alleges retaliation")
    assert synopsis_payload["session"]["case_synopsis"].startswith("Jordan Example alleges retaliation")

    reset_payload = _invoke_cli(runner, "reset", "--user-id", "cli-user")
    assert reset_payload["session"]["user_id"] == "cli-user"
    assert reset_payload["session"]["draft"] is None
    assert reset_payload["session"]["intake_answers"] == {}


def test_all_mcp_server_tools_are_exercised_via_jsonrpc(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "mcp-tool-sessions")

    start_payload = _call_mcp_tool(service, 1, "complaint.start_session", {"user_id": "mcp-user"})
    assert start_payload["session"]["user_id"] == "mcp-user"
    assert start_payload["next_question"]["id"] == "party_name"

    identity_payload = _call_mcp_tool(service, 10, "complaint.create_identity", {})
    assert str(identity_payload["did"]).startswith("did:key:")

    questions_payload = _call_mcp_tool(service, 11, "complaint.list_intake_questions", {})
    assert questions_payload["questions"][0]["id"] == "party_name"

    claim_elements_payload = _call_mcp_tool(service, 12, "complaint.list_claim_elements", {})
    assert claim_elements_payload["claim_elements"][0]["id"] == "protected_activity"

    intake_payload = _call_mcp_tool(
        service,
        20,
        "complaint.submit_intake",
        {
            "user_id": "mcp-user",
            "answers": {
                "party_name": "Jordan Example",
                "opposing_party": "Acme Corporation",
                "protected_activity": "Reported discrimination to HR",
                "adverse_action": "Terminated two days later",
            },
        },
    )
    assert intake_payload["session"]["intake_answers"]["party_name"] == "Jordan Example"
    assert intake_payload["session"]["intake_answers"]["adverse_action"] == "Terminated two days later"

    evidence_payload = _call_mcp_tool(
        service,
        21,
        "complaint.save_evidence",
        {
            "user_id": "mcp-user",
            "kind": "testimony",
            "claim_element_id": "causation",
            "title": "Witness statement",
            "content": "A witness saw the termination happen immediately after the report.",
            "source": "Witness interview",
            "attachment_names": ["witness-notes.txt"],
        },
    )
    assert evidence_payload["saved"]["title"] == "Witness statement"
    assert evidence_payload["saved"]["kind"] == "testimony"
    assert evidence_payload["saved"]["attachment_names"] == ["witness-notes.txt"]

    review_payload = _call_mcp_tool(service, 22, "complaint.review_case", {"user_id": "mcp-user"})
    assert review_payload["review"]["overview"]["testimony_items"] == 1
    assert review_payload["session"]["user_id"] == "mcp-user"
    assert "case_synopsis" in review_payload
    assert "Reported discrimination to HR" in review_payload["review"]["case_synopsis"]

    mediator_payload = _call_mcp_tool(service, 23, "complaint.build_mediator_prompt", {"user_id": "mcp-user"})
    assert "Mediator, help turn this into testimony-ready narrative" in mediator_payload["prefill_message"]

    capabilities_payload = _call_mcp_tool(service, 24, "complaint.get_workflow_capabilities", {"user_id": "mcp-user"})
    assert any(item["id"] == "complaint_packet" for item in capabilities_payload["capabilities"])

    generate_payload = _call_mcp_tool(
        service,
        25,
        "complaint.generate_complaint",
        {
            "user_id": "mcp-user",
            "requested_relief": ["Back pay", "Compensatory damages"],
            "title_override": "MCP generated complaint",
        },
    )
    assert generate_payload["draft"]["title"] == "MCP generated complaint"
    assert generate_payload["draft"]["requested_relief"] == ["Back pay", "Compensatory damages"]
    assert "Working case synopsis:" in generate_payload["draft"]["body"]
    assert "Reported discrimination to HR" in generate_payload["draft"]["case_synopsis"]

    update_payload = _call_mcp_tool(
        service,
        26,
        "complaint.update_draft",
        {
            "user_id": "mcp-user",
            "title": "Updated MCP complaint",
            "body": "Updated body from MCP.",
            "requested_relief": "Reinstatement\nAttorney fees",
        },
    )
    assert update_payload["draft"]["title"] == "Updated MCP complaint"
    assert update_payload["draft"]["body"] == "Updated body from MCP."
    assert update_payload["draft"]["requested_relief"] == ["Reinstatement", "Attorney fees"]

    export_payload = _call_mcp_tool(service, 27, "complaint.export_complaint_packet", {"user_id": "mcp-user"})
    assert export_payload["packet"]["draft"]["title"] == "Updated MCP complaint"
    assert export_payload["packet_summary"]["has_draft"] is True

    synopsis_payload = _call_mcp_tool(
        service,
        28,
        "complaint.update_case_synopsis",
        {
            "user_id": "mcp-user",
            "synopsis": "Jordan Example alleges retaliation after reporting discrimination and wants the shared case framing preserved.",
        },
    )
    assert synopsis_payload["case_synopsis"].startswith("Jordan Example alleges retaliation")
    assert synopsis_payload["session"]["case_synopsis"].startswith("Jordan Example alleges retaliation")

    reset_payload = _call_mcp_tool(service, 29, "complaint.reset_session", {"user_id": "mcp-user"})
    assert reset_payload["session"]["user_id"] == "mcp-user"
    assert reset_payload["session"]["draft"] is None
    assert reset_payload["session"]["intake_answers"] == {}


def test_review_ui_tool_can_be_invoked_through_cli_and_mcp(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "ui-review-sessions")

    def fake_run_ui_review_workflow(*args, **kwargs):
        return {
            "generated_at": "2026-03-23T00:00:00+00:00",
            "backend": {"strategy": "fallback"},
            "screenshots": [{"path": "/tmp/workspace.png"}],
            "review": {"summary": "Review completed."},
        }

    monkeypatch.setattr(complaint_cli_impl, "service", service)
    monkeypatch.setattr("applications.complaint_cli.run_ui_review_workflow", fake_run_ui_review_workflow)
    monkeypatch.setattr("applications.ui_review.run_ui_review_workflow", fake_run_ui_review_workflow)

    cli_payload = _invoke_cli(
        runner,
        "review-ui",
        str(tmp_path),
        "--artifact-path",
        str(tmp_path / "review.json"),
    )
    assert cli_payload["review"]["summary"] == "Review completed."

    mcp_payload = _call_mcp_tool(
        service,
        11,
        "complaint.review_ui",
        {"screenshot_dir": str(tmp_path)},
    )
    assert mcp_payload["review"]["summary"] == "Review completed."


def test_review_ui_tool_supports_iterative_workflow_through_mcp(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "ui-review-sessions")

    def fake_iterative(**kwargs):
        assert kwargs["iterations"] == 2
        assert str(kwargs["screenshot_dir"]) == str(tmp_path)
        assert kwargs["goals"] == ["reduce intake friction", "keep evidence and draft connected"]
        return {
            "iterations": 2,
            "screenshot_dir": str(tmp_path),
            "output_dir": str(tmp_path / "reviews"),
            "runs": [
                {
                    "iteration": 1,
                    "review_markdown_path": str(tmp_path / "reviews" / "iteration-01-review.md"),
                    "review_json_path": str(tmp_path / "reviews" / "iteration-01-review.json"),
                }
            ],
        }

    monkeypatch.setattr("complaint_generator.ui_ux_workflow.run_iterative_ui_ux_workflow", fake_iterative)

    mcp_payload = _call_mcp_tool(
        service,
        12,
        "complaint.review_ui",
        {
            "screenshot_dir": str(tmp_path),
            "iterations": 2,
            "output_path": str(tmp_path / "reviews"),
            "goals": ["reduce intake friction", "keep evidence and draft connected"],
        },
    )

    assert mcp_payload["iterations"] == 2
    assert mcp_payload["runs"][0]["iteration"] == 1


def test_optimize_ui_tool_supports_closed_loop_workflow_through_cli_and_mcp(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "ui-optimize-sessions")

    def fake_closed_loop(**kwargs):
        assert kwargs["method"] == "adversarial"
        assert kwargs["priority"] == 91
        assert kwargs["goals"] == ["make intake calmer", "surface every complaint-generator feature"]
        return {
            "workflow_type": "ui_ux_closed_loop",
            "max_rounds": kwargs["max_rounds"],
            "rounds_executed": 1,
            "stop_reason": "validation_review_stable",
            "cycles": [
                {
                    "round": 1,
                    "task": {"target_files": ["templates/workspace.html"]},
                    "optimizer_result": {"changed_files": ["templates/workspace.html"]},
                }
            ],
        }

    monkeypatch.setattr(complaint_cli_impl, "service", service)
    monkeypatch.setattr("complaint_generator.ui_ux_workflow.run_closed_loop_ui_ux_improvement", fake_closed_loop)

    cli_payload = _invoke_cli(
        runner,
        "optimize-ui",
        str(tmp_path),
        "--output-path",
        str(tmp_path / "closed-loop"),
        "--max-rounds",
        "2",
        "--method",
        "adversarial",
        "--priority",
        "91",
        "--goals",
        "make intake calmer\nsurface every complaint-generator feature",
    )
    assert cli_payload["workflow_type"] == "ui_ux_closed_loop"
    assert cli_payload["max_rounds"] == 2

    mcp_payload = _call_mcp_tool(
        service,
        13,
        "complaint.optimize_ui",
        {
            "screenshot_dir": str(tmp_path),
            "max_rounds": 2,
            "output_path": str(tmp_path / "closed-loop"),
            "method": "adversarial",
            "priority": 91,
            "goals": ["make intake calmer", "surface every complaint-generator feature"],
        },
    )
    assert mcp_payload["workflow_type"] == "ui_ux_closed_loop"
    assert mcp_payload["cycles"][0]["optimizer_result"]["changed_files"] == ["templates/workspace.html"]


def test_optimize_ui_defaults_to_feature_complete_audit_and_actor_critic_method(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "ui-optimize-default-sessions")
    captured = {}

    def fake_closed_loop(**kwargs):
        captured.update(kwargs)
        return {"workflow_type": "ui_ux_closed_loop", "rounds_executed": 1}

    monkeypatch.setattr(complaint_cli_impl, "service", service)
    monkeypatch.setattr(
        "complaint_generator.ui_ux_workflow.run_closed_loop_ui_ux_improvement",
        fake_closed_loop,
    )

    cli_payload = _invoke_cli(
        runner,
        "optimize-ui",
        str(tmp_path),
    )
    assert cli_payload["workflow_type"] == "ui_ux_closed_loop"
    assert captured["method"] == "actor_critic"
    assert captured["priority"] == 90
    assert captured["pytest_target"].endswith(
        "test_dashboard_end_to_end_complaint_journey_uses_chat_review_builder_and_optimizer"
    )


def test_browser_audit_is_exposed_through_cli_and_mcp(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "browser-audit-sessions")
    captured = {}

    def fake_browser_audit(**kwargs):
        captured.update(kwargs)
        return {
            "command": ["pytest", "-q", str(kwargs["pytest_target"])],
            "returncode": 0,
            "artifact_count": 3,
            "screenshot_dir": str(kwargs["screenshot_dir"]),
        }

    monkeypatch.setattr(complaint_cli_impl, "service", service)
    monkeypatch.setattr(
        "complaint_generator.ui_ux_workflow.run_end_to_end_complaint_browser_audit",
        fake_browser_audit,
    )
    monkeypatch.setattr(
        "complaint_generator.ui_ux_workflow.run_playwright_screenshot_audit",
        fake_browser_audit,
    )

    cli_payload = _invoke_cli(
        runner,
        "browser-audit",
        str(tmp_path / "screens"),
    )
    assert cli_payload["returncode"] == 0
    assert cli_payload["artifact_count"] == 3
    assert captured["pytest_target"].endswith(
        "test_dashboard_end_to_end_complaint_journey_uses_chat_review_builder_and_optimizer"
    )

    tool_names = [tool["name"] for tool in tool_list_payload(service)["tools"]]
    assert "complaint.run_browser_audit" in tool_names

    captured.clear()
    mcp_payload = _call_mcp_tool(
        service,
        15,
        "complaint.run_browser_audit",
        {
            "screenshot_dir": str(tmp_path / "screens"),
        },
    )
    assert mcp_payload["returncode"] == 0
    assert mcp_payload["artifact_count"] == 3
    assert captured["pytest_target"].endswith(
        "test_dashboard_end_to_end_complaint_journey_uses_chat_review_builder_and_optimizer"
    )
