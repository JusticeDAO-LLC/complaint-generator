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
    return json.loads(result.stdout)


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
        "complaint.start_session",
        "complaint.submit_intake",
        "complaint.save_evidence",
        "complaint.review_case",
        "complaint.generate_complaint",
        "complaint.update_draft",
        "complaint.reset_session",
    ]
    assert all("inputSchema" in tool for tool in payload["tools"])


def test_all_cli_commands_are_exercised_end_to_end(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "cli-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)

    session_payload = _invoke_cli(runner, "session", "--user-id", "cli-user")
    assert session_payload["session"]["user_id"] == "cli-user"
    assert session_payload["next_question"]["id"] == "party_name"

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
    )
    assert evidence_payload["saved"]["kind"] == "document"
    assert evidence_payload["saved"]["title"] == "Termination email"

    review_payload = _invoke_cli(runner, "review", "--user-id", "cli-user")
    assert review_payload["review"]["claim_type"] == "retaliation"
    assert review_payload["session"]["user_id"] == "cli-user"

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

    reset_payload = _invoke_cli(runner, "reset", "--user-id", "cli-user")
    assert reset_payload["session"]["user_id"] == "cli-user"
    assert reset_payload["session"]["draft"] is None
    assert reset_payload["session"]["intake_answers"] == {}


def test_all_mcp_server_tools_are_exercised_via_jsonrpc(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "mcp-tool-sessions")

    start_payload = _call_mcp_tool(service, 1, "complaint.start_session", {"user_id": "mcp-user"})
    assert start_payload["session"]["user_id"] == "mcp-user"
    assert start_payload["next_question"]["id"] == "party_name"

    intake_payload = _call_mcp_tool(
        service,
        2,
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
        3,
        "complaint.save_evidence",
        {
            "user_id": "mcp-user",
            "kind": "testimony",
            "claim_element_id": "causation",
            "title": "Witness statement",
            "content": "A witness saw the termination happen immediately after the report.",
            "source": "Witness interview",
        },
    )
    assert evidence_payload["saved"]["title"] == "Witness statement"
    assert evidence_payload["saved"]["kind"] == "testimony"

    review_payload = _call_mcp_tool(service, 4, "complaint.review_case", {"user_id": "mcp-user"})
    assert review_payload["review"]["overview"]["testimony_items"] == 1
    assert review_payload["session"]["user_id"] == "mcp-user"

    generate_payload = _call_mcp_tool(
        service,
        5,
        "complaint.generate_complaint",
        {
            "user_id": "mcp-user",
            "requested_relief": ["Back pay", "Compensatory damages"],
            "title_override": "MCP generated complaint",
        },
    )
    assert generate_payload["draft"]["title"] == "MCP generated complaint"
    assert generate_payload["draft"]["requested_relief"] == ["Back pay", "Compensatory damages"]

    update_payload = _call_mcp_tool(
        service,
        6,
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

    reset_payload = _call_mcp_tool(service, 7, "complaint.reset_session", {"user_id": "mcp-user"})
    assert reset_payload["session"]["user_id"] == "mcp-user"
    assert reset_payload["session"]["draft"] is None
    assert reset_payload["session"]["intake_answers"] == {}
