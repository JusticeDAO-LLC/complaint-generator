import json
import os
import shutil
import zipfile
from io import BytesIO

import backends
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from typer.testing import CliRunner
from ipfs_datasets_py.processors.legal_data import DocketDatasetBuilder

from applications import complaint_cli as complaint_cli_impl
from applications.complaint_workspace_api import attach_complaint_workspace_routes
from applications.complaint_mcp_protocol import handle_jsonrpc_message, tool_list_payload
from complaint_generator import ComplaintWorkspaceService, analyze_complaint_output, get_client_release_gate, get_formal_diagnostics, get_packaged_docket_operator_dashboard, get_provider_diagnostics, get_tooling_contract, load_packaged_docket_operator_dashboard_report, optimize_ui, review_generated_exports, review_ui, run_browser_audit

try:
    import python_multipart  # type: ignore  # noqa: F401

    HAS_MULTIPART = True
except ModuleNotFoundError:
    HAS_MULTIPART = False


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


def _build_packaged_docket_manifest(tmp_path, *, routing_reason: str = "Workspace dashboard routing reason.") -> str:
    dataset = DocketDatasetBuilder().build_from_docket(
        {
            "docket_id": "workspace-docket-1",
            "case_name": "Workspace Packaged Docket",
            "court": "D. Example",
            "documents": [
                {
                    "id": "doc_1",
                    "title": "Complaint",
                    "text": "Plaintiff seeks relief under 42 U.S.C. § 1983.",
                },
                {
                    "id": "doc_2",
                    "title": "Notice of Hearing",
                    "date_filed": "2024-04-18",
                    "document_number": "12",
                    "text": "The court sets a hearing for May 1, 2024 at 10:00 a.m.",
                },
            ],
        }
    )
    dataset.metadata["latest_proof_packet_routing_explanation"] = {
        "routing_reason": routing_reason,
        "routing_evidence": [{"citation_text": "42 U.S.C. § 1983"}],
        "preferred_corpus_priority": ["us_code"],
        "preferred_state_codes": [],
        "authority_backed": True,
    }
    package = dataset.write_package(
        tmp_path / "workspace_packaged_docket_bundle",
        package_name="workspace_packaged_docket_bundle",
        include_car=False,
    )
    return str(package["manifest_json_path"])


def _build_single_docket_parquet(tmp_path) -> str:
    import pyarrow as pa
    import pyarrow.parquet as pq

    output_path = tmp_path / "single_parquet_docket.dataset.parquet"
    rows = [
        {
            "dataset_id": "docket_dataset_single-parquet-docket-1",
            "docket_id": "single-parquet-docket-1",
            "case_name": "Single Parquet Docket",
            "court": "D. Example",
            "section": "dataset_core",
            "row_index": 1,
            "row_id": "dataset_core_1",
            "title": "Single Parquet Docket",
            "document_number": "",
            "source_url": "",
            "text": "",
            "payload_json": json.dumps(
                {
                    "dataset_id": "docket_dataset_single-parquet-docket-1",
                    "docket_id": "single-parquet-docket-1",
                    "case_name": "Single Parquet Docket",
                    "court": "D. Example",
                    "metadata": {"fixture": "single-parquet"},
                },
                sort_keys=True,
            ),
        },
        {
            "dataset_id": "docket_dataset_single-parquet-docket-1",
            "docket_id": "single-parquet-docket-1",
            "case_name": "Single Parquet Docket",
            "court": "D. Example",
            "section": "documents",
            "row_index": 1,
            "row_id": "doc_1",
            "title": "Motion to Compel",
            "document_number": "21",
            "source_url": "",
            "text": "Plaintiff moves to compel production of the housing file.",
            "payload_json": json.dumps(
                {
                    "id": "doc_1",
                    "title": "Motion to Compel",
                    "document_number": "21",
                    "text": "Plaintiff moves to compel production of the housing file.",
                },
                sort_keys=True,
            ),
        },
        {
            "dataset_id": "docket_dataset_single-parquet-docket-1",
            "docket_id": "single-parquet-docket-1",
            "case_name": "Single Parquet Docket",
            "court": "D. Example",
            "section": "documents",
            "row_index": 2,
            "row_id": "doc_2",
            "title": "Notice of Hearing",
            "document_number": "22",
            "source_url": "",
            "text": "The court sets a hearing for April 21, 2026.",
            "payload_json": json.dumps(
                {
                    "id": "doc_2",
                    "title": "Notice of Hearing",
                    "date_filed": "2026-04-01",
                    "document_number": "22",
                    "text": "The court sets a hearing for April 21, 2026.",
                },
                sort_keys=True,
            ),
        },
        {
            "dataset_id": "docket_dataset_single-parquet-docket-1",
            "docket_id": "single-parquet-docket-1",
            "case_name": "Single Parquet Docket",
            "court": "D. Example",
            "section": "bm25_documents",
            "row_index": 1,
            "row_id": "doc_2",
            "title": "Notice of Hearing",
            "document_number": "22",
            "source_url": "",
            "text": "Notice of Hearing The court sets a hearing for April 21, 2026.",
            "payload_json": json.dumps(
                {
                    "document_id": "doc_2",
                    "title": "Notice of Hearing",
                    "text": "Notice of Hearing The court sets a hearing for April 21, 2026.",
                    "tokens": ["notice", "hearing", "court", "sets", "hearing", "april"],
                    "metadata": {"document_number": "22"},
                },
                sort_keys=True,
            ),
        },
    ]
    pq.write_table(pa.Table.from_pylist(rows), output_path)
    return str(output_path)


def test_tool_list_exposes_all_complaint_cli_and_mcp_tools(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "tool-list-sessions")
    payload = tool_list_payload(service)
    tools_by_name = {tool["name"]: tool for tool in payload["tools"]}
    tool_names = [tool["name"] for tool in payload["tools"]]

    expected_tool_names = [
        "complaint.create_identity",
        "complaint.list_intake_questions",
        "complaint.list_claim_elements",
        "complaint.start_session",
        "complaint.submit_intake",
        "complaint.run_intake_chat_turn",
        "complaint.save_evidence",
        "complaint.import_gmail_evidence",
        "complaint.run_gmail_duckdb_pipeline",
        "complaint.import_local_evidence",
        "complaint.search_email_duckdb_corpus",
        "complaint.review_case",
        "complaint.build_mediator_prompt",
        "complaint.get_complaint_readiness",
        "complaint.get_ui_readiness",
        "complaint.get_client_release_gate",
        "complaint.get_workflow_capabilities",
        "complaint.get_tooling_contract",
        "complaint.generate_complaint",
        "complaint.update_draft",
        "complaint.export_complaint_packet",
        "complaint.export_complaint_markdown",
        "complaint.export_complaint_docx",
        "complaint.export_complaint_pdf",
        "complaint.analyze_complaint_output",
        "complaint.get_formal_diagnostics",
        "complaint.get_filing_provenance",
        "complaint.get_provider_diagnostics",
        "complaint.get_packaged_docket_operator_dashboard",
        "complaint.load_packaged_docket_operator_dashboard_report",
        "complaint.review_generated_exports",
        "complaint.update_claim_type",
        "complaint.update_case_synopsis",
        "complaint.reset_session",
        "complaint.review_ui",
        "complaint.optimize_ui",
        "complaint.run_browser_audit",
    ]
    assert tool_names == expected_tool_names or sorted(tool_names) == sorted(expected_tool_names)
    assert len(tool_names) == len(set(tool_names))
    assert all("inputSchema" in tool for tool in payload["tools"])
    assert tools_by_name["complaint.get_tooling_contract"]["inputSchema"]["properties"] == {"user_id": {"type": "string"}}
    assert tools_by_name["complaint.get_filing_provenance"]["inputSchema"]["properties"] == {"user_id": {"type": "string"}}
    assert tools_by_name["complaint.get_packaged_docket_operator_dashboard"]["inputSchema"]["required"] == ["manifest_path"]
    assert tools_by_name["complaint.load_packaged_docket_operator_dashboard_report"]["inputSchema"]["required"] == ["manifest_path"]


def test_client_release_gate_is_exposed_across_package_cli_and_mcp(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "release-gate-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)

    service.submit_intake_answers(
        "gate-user",
        {
            "party_name": "Taylor Smith",
            "opposing_party": "Acme Logistics",
            "protected_activity": "Reported wage-and-hour violations to HR",
            "adverse_action": "Was terminated three days later",
            "timeline": "Report on April 2, termination on April 5",
            "harm": "Lost wages, benefits, and housing stability",
        },
    )
    service.save_evidence(
        "gate-user",
        kind="document",
        claim_element_id="causation",
        title="Termination email",
        content="Termination followed within days of the report.",
    )
    service.generate_complaint("gate-user", requested_relief=["Back pay"])
    service._persist_ui_readiness(
        "gate-user",
        {
            "review": {
                "summary": "The complaint journey is usable but still needs polish.",
                "critic_review": {"verdict": "warning", "acceptance_checks": ["Keep the draft and export path stable."]},
                "complaint_journey": {"tested_stages": ["intake", "evidence", "review", "draft", "export"]},
            }
        },
    )

    cli_payload = _invoke_cli(runner, "client-release-gate", "--user-id", "gate-user")
    assert cli_payload["verdict"] in {"client_safe", "warning", "blocked"}

    mcp_payload = _call_mcp_tool(service, 91, "complaint.get_client_release_gate", {"user_id": "gate-user"})
    assert mcp_payload["verdict"] in {"client_safe", "warning", "blocked"}
    assert mcp_payload["complaint_output_release_gate"]["verdict"] in {"pass", "warning", "blocked"}

    package_payload = get_client_release_gate("gate-user", service=service)
    assert package_payload["user_id"] == "gate-user"
    assert package_payload["complaint_readiness"]["has_draft"] is True


def test_tooling_contract_is_exposed_across_package_cli_and_mcp(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "tooling-contract-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)

    cli_payload = _invoke_cli(runner, "tooling-contract", "--user-id", "contract-user")
    assert cli_payload["all_core_flow_steps_exposed"] is True
    assert "generate" in cli_payload["cli_commands"]
    assert "import-gmail-evidence" in cli_payload["cli_commands"]
    assert "run-gmail-duckdb-pipeline" in cli_payload["cli_commands"]
    assert "import-local-evidence" in cli_payload["cli_commands"]
    assert "search-email-duckdb" in cli_payload["cli_commands"]
    assert "chat-turn" in cli_payload["cli_commands"]
    assert "tooling-contract" in cli_payload["cli_commands"]
    assert "workspace-data-schema" in cli_payload["cli_commands"]
    assert "migrate-legacy-workspace-data" in cli_payload["cli_commands"]
    assert "set-claim-type" in cli_payload["cli_commands"]
    assert "update-synopsis" in cli_payload["cli_commands"]

    mcp_payload = _call_mcp_tool(service, 92, "complaint.get_tooling_contract", {"user_id": "contract-user"})
    assert mcp_payload["all_core_flow_steps_exposed"] is True
    assert any(step["id"] == "draft_generation" for step in mcp_payload["core_flow_steps"])
    assert any(step["id"] == "gmail_evidence_import" for step in mcp_payload["core_flow_steps"])
    assert any(step["id"] == "local_evidence_import" for step in mcp_payload["core_flow_steps"])
    assert any(step["id"] == "tooling_contract" for step in mcp_payload["core_flow_steps"])
    assert any(step["id"] == "workspace_data_schema" for step in mcp_payload["core_flow_steps"])
    assert any(step["id"] == "workspace_data_migration" for step in mcp_payload["core_flow_steps"])

    package_payload = get_tooling_contract("contract-user", service=service)
    assert package_payload["all_core_flow_steps_exposed"] is True
    assert "complaint.generate_complaint" in package_payload["mcp_tools"]
    assert "import_gmail_evidence" in package_payload["package_exports"]
    assert "run_gmail_duckdb_pipeline" in package_payload["package_exports"]
    assert "import_local_evidence" in package_payload["package_exports"]
    assert "search_email_duckdb_corpus" in package_payload["package_exports"]
    assert "run_intake_chat_turn" in package_payload["package_exports"]
    assert "update_claim_type" in package_payload["package_exports"]
    assert "update_case_synopsis" in package_payload["package_exports"]
    assert "get_workspace_data_schema" in package_payload["package_exports"]
    assert "migrate_legacy_workspace_data" in package_payload["package_exports"]
    assert "importGmailEvidence" in package_payload["browser_sdk_methods"]
    assert "importLocalEvidence" in package_payload["browser_sdk_methods"]
    assert "runGmailDuckdbPipeline" in package_payload["browser_sdk_methods"]
    assert "searchEmailDuckdb" in package_payload["browser_sdk_methods"]
    assert "runIntakeChatTurn" in package_payload["browser_sdk_methods"]
    assert "updateClaimType" in package_payload["browser_sdk_methods"]
    assert "updateCaseSynopsis" in package_payload["browser_sdk_methods"]
    assert "getToolingContract" in package_payload["browser_sdk_methods"]
    assert "getWorkspaceDataSchema" in package_payload["browser_sdk_methods"]
    assert "migrateLegacyWorkspaceData" in package_payload["browser_sdk_methods"]
    assert any(step["id"] == "gmail_duckdb_pipeline" for step in package_payload["core_flow_steps"])
    assert any(step["id"] == "email_duckdb_search" for step in package_payload["core_flow_steps"])
    assert any(step["id"] == "intake_chat" for step in package_payload["core_flow_steps"])
    assert any(item["id"] == "workspace_schema_refresh" for item in package_payload["schema_guided_recommendations"])


def test_intake_chat_turn_is_exposed_across_cli_mcp_and_api(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "intake-chat-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)

    first_turn = _invoke_cli(runner, "chat-turn", "--user-id", "chat-user")
    assert first_turn["inquiry"]["question_id"] == "party_name"
    assert first_turn["accepted_answer"] is None

    cli_turn = _invoke_cli(
        runner,
        "chat-turn",
        "--user-id",
        "chat-user",
        "--message",
        "Jordan Example",
    )
    assert cli_turn["accepted_answer"]["question_id"] == "party_name"
    assert cli_turn["next_question"]["id"] == "opposing_party"

    mcp_turn = _call_mcp_tool(
        service,
        19_1,
        "complaint.run_intake_chat_turn",
        {
            "user_id": "chat-user",
            "message": "Acme Corporation",
            "question_id": "opposing_party",
        },
    )
    assert mcp_turn["accepted_answer"]["question_id"] == "opposing_party"
    assert mcp_turn["next_question"]["id"] == "protected_activity"

    app = FastAPI()
    attach_complaint_workspace_routes(app, service)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.post(
        "/api/complaint-workspace/intake-chat",
        json={
            "user_id": "chat-user",
            "message": "Reported discrimination to HR",
            "question_id": "protected_activity",
        },
    )

    assert response.status_code == 200
    api_turn = response.json()
    assert api_turn["accepted_answer"]["question_id"] == "protected_activity"
    assert api_turn["next_question"]["id"] == "adverse_action"


def test_generate_api_route_forwards_llm_router_options(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "generate-api-sessions")
    app = FastAPI()
    attach_complaint_workspace_routes(app, service)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    captured = {}

    def fake_generate_complaint(
        user_id,
        *,
        requested_relief=None,
        title_override=None,
        use_llm=False,
        provider=None,
        model=None,
        config_path=None,
        backend_id=None,
    ):
        captured.update(
            {
                "user_id": user_id,
                "requested_relief": list(requested_relief or []),
                "title_override": title_override,
                "use_llm": use_llm,
                "provider": provider,
                "model": model,
                "config_path": config_path,
                "backend_id": backend_id,
            }
        )
        return {
            "draft": {
                "title": title_override or "LLM complaint",
                "body": "IN THE UNITED STATES DISTRICT COURT\nCOMPLAINT FOR RETALIATION",
                "draft_strategy": "llm_router" if use_llm else "template",
            }
        }

    monkeypatch.setattr(service, "generate_complaint", fake_generate_complaint)

    response = client.post(
        "/api/complaint-workspace/generate",
        json={
            "user_id": "api-llm-user",
            "requested_relief": ["Back pay", "Injunctive relief"],
            "title_override": "API LLM Complaint",
            "use_llm": True,
            "provider": "codex_cli",
            "model": "gpt-5.3-codex",
            "config_path": "config.llm_router.json",
            "backend_id": "formal_complaint_reviewer",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert captured == {
        "user_id": "api-llm-user",
        "requested_relief": ["Back pay", "Injunctive relief"],
        "title_override": "API LLM Complaint",
        "use_llm": True,
        "provider": "codex_cli",
        "model": "gpt-5.3-codex",
        "config_path": "config.llm_router.json",
        "backend_id": "formal_complaint_reviewer",
    }


def test_upload_local_evidence_api_route_imports_files_and_note(tmp_path):
    if not HAS_MULTIPART:
        pytest.skip("python-multipart is not installed")

    service = ComplaintWorkspaceService(root_dir=tmp_path / "upload-local-evidence-sessions")
    app = FastAPI()
    attach_complaint_workspace_routes(app, service)
    client = TestClient(app)

    response = client.post(
        "/api/complaint-workspace/upload-local-evidence",
        data={
            "user_id": "upload-user",
            "claim_element_id": "causation",
            "kind": "document",
            "note_title": "Dashboard upload note",
            "note": "These files were added from the dashboard chat modal.",
            "source": "dashboard-chat-upload",
        },
        files=[
            (
                "files",
                ("timeline.txt", b"Termination email arrived two days after the HR report.", "text/plain"),
            ),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["imported_count"] == 1
    assert payload["uploaded_files"][0]["filename"] == "timeline.txt"
    assert payload["note_record"]["title"] == "Dashboard upload note"
    assert payload["note_record"]["attachment_names"] == ["timeline.txt"]
    assert payload["session"]["user_id"] == "upload-user"
    documents = payload["session"]["evidence"]["documents"]
    testimony = payload["session"]["evidence"]["testimony"]
    assert any("timeline.txt" in str(record["title"]) for record in documents)
    assert any(record["title"] == "Dashboard upload note" for record in testimony)


@pytest.mark.no_auto_llm
def test_workspace_session_reset_clears_uploaded_dashboard_state(tmp_path):
    if not HAS_MULTIPART:
        pytest.skip("python-multipart is not installed")

    service = ComplaintWorkspaceService(root_dir=tmp_path / "dashboard-reset-sessions")
    app = FastAPI()
    attach_complaint_workspace_routes(app, service)
    client = TestClient(app)

    upload_response = client.post(
        "/api/complaint-workspace/upload-local-evidence",
        data={
            "user_id": "dashboard-reset-user",
            "claim_element_id": "causation",
            "kind": "document",
            "note_title": "Reset verification note",
            "note": "This upload should disappear after reset.",
            "source": "dashboard-chat-upload",
        },
        files=[
            (
                "files",
                ("timeline.txt", b"The timeline changed after the hearing notice arrived.", "text/plain"),
            ),
        ],
    )
    assert upload_response.status_code == 200
    uploaded_payload = upload_response.json()
    assert uploaded_payload["session"]["evidence"]["documents"]
    assert uploaded_payload["session"]["evidence"]["testimony"]

    session_response = client.get(
        "/api/complaint-workspace/session",
        params={"user_id": "dashboard-reset-user"},
    )
    assert session_response.status_code == 200
    session_payload = session_response.json()
    assert len(session_payload["session"]["evidence"]["documents"]) == 1
    assert len(session_payload["session"]["evidence"]["testimony"]) == 1

    reset_response = client.post(
        "/api/complaint-workspace/reset",
        json={"user_id": "dashboard-reset-user"},
    )
    assert reset_response.status_code == 200

    refreshed_session_response = client.get(
        "/api/complaint-workspace/session",
        params={"user_id": "dashboard-reset-user"},
    )
    assert refreshed_session_response.status_code == 200
    refreshed_session_payload = refreshed_session_response.json()
    assert refreshed_session_payload["session"]["user_id"] == "dashboard-reset-user"
    assert refreshed_session_payload["session"]["evidence"]["documents"] == []
    assert refreshed_session_payload["session"]["evidence"]["testimony"] == []


def test_import_gmail_evidence_cli_command(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "gmail-import-cli-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)
    captured = {}

    async def fake_import_gmail_evidence(**kwargs):
        captured.update(kwargs)
        service.save_evidence(
            kwargs["user_id"],
            kind="document",
            claim_element_id=kwargs["claim_element_id"],
            title="Email import: Termination email",
            content="Imported from Gmail",
            source="gmail_imap_import",
            attachment_names=["message.eml", "termination.pdf", "message.json"],
        )
        return {
            "status": "success",
            "user_id": kwargs["user_id"],
            "claim_element_id": kwargs["claim_element_id"],
            "matched_addresses": list(kwargs["addresses"]),
            "searched_message_count": 3,
            "imported_count": 1,
            "evidence_root": str(kwargs["evidence_root"] or (tmp_path / "evidence")),
            "imported": [
                {
                    "subject": "Termination email",
                    "artifact_dir": str(tmp_path / "evidence" / "case"),
                }
            ],
        }

    monkeypatch.setattr(complaint_cli_impl, "import_gmail_evidence", fake_import_gmail_evidence)

    payload = _invoke_cli(
        runner,
        "import-gmail-evidence",
        "--user-id",
        "cli-user",
        "--address",
        "hr@example.com",
        "--address",
        "manager@example.com",
        "--claim-element-id",
        "causation",
        "--scan-folder",
        "[Gmail]/Sent Mail",
        "--years-back",
        "2",
        "--complaint-query",
        "termination retaliation hr complaint",
        "--complaint-keyword",
        "termination",
        "--complaint-keyword",
        "retaliation",
        "--min-relevance-score",
        "1.5",
        "--use-uid-checkpoint",
        "--checkpoint-name",
        "gmail-resume",
        "--uid-window-size",
        "250",
        "--gmail-user",
        "user@gmail.com",
        "--gmail-app-password",
        "app-password",
    )

    assert payload["status"] == "success"
    assert payload["matched_addresses"] == ["hr@example.com", "manager@example.com"]
    assert payload["imported_count"] == 1
    assert captured["folders"] == ["[Gmail]/Sent Mail"]
    assert captured["years_back"] == 2
    assert captured["complaint_query"] == "termination retaliation hr complaint"
    assert captured["complaint_keywords"] == ["termination", "retaliation"]
    assert captured["min_relevance_score"] == 1.5
    assert captured["use_uid_checkpoint"] is True
    assert captured["checkpoint_name"] == "gmail-resume"
    assert captured["uid_window_size"] == 250

    session = service.get_session("cli-user")["session"]
    documents = session["evidence"]["documents"]
    assert len(documents) == 1
    assert documents[0]["title"] == "Email import: Termination email"
    assert documents[0]["attachment_names"] == ["message.eml", "termination.pdf", "message.json"]


def test_import_gmail_evidence_mcp_tool(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "gmail-import-mcp-sessions")
    captured = {}

    def fake_import_gmail_evidence(
        user_id,
        *,
        addresses,
        claim_element_id="causation",
        folder="INBOX",
        folders=None,
        limit=None,
        date_after=None,
        date_before=None,
        years_back=None,
        evidence_root=None,
        gmail_user=None,
        gmail_app_password=None,
        complaint_query=None,
        complaint_keywords=None,
        min_relevance_score=0.0,
        use_uid_checkpoint=False,
        checkpoint_name=None,
        uid_window_size=None,
    ):
        captured.update(
            {
                "folders": folders,
                "years_back": years_back,
                "complaint_query": complaint_query,
                "complaint_keywords": complaint_keywords,
                "min_relevance_score": min_relevance_score,
                "use_uid_checkpoint": use_uid_checkpoint,
                "checkpoint_name": checkpoint_name,
                "uid_window_size": uid_window_size,
            }
        )
        service.save_evidence(
            user_id,
            kind="document",
            claim_element_id=claim_element_id,
            title="Email import: Termination email",
            content="Imported from Gmail via MCP",
            source="gmail_imap_import",
            attachment_names=["message.eml", "termination.pdf", "message.json"],
        )
        return {
            "status": "success",
            "user_id": user_id,
            "claim_element_id": claim_element_id,
            "matched_addresses": list(addresses),
            "searched_message_count": 2,
            "imported_count": 1,
            "evidence_root": str(evidence_root or (tmp_path / "evidence")),
            "imported": [
                {
                    "subject": "Termination email",
                    "artifact_dir": str(tmp_path / "evidence" / "case"),
                }
            ],
        }

    monkeypatch.setattr(service, "import_gmail_evidence", fake_import_gmail_evidence)

    payload = _call_mcp_tool(
        service,
        21_1,
        "complaint.import_gmail_evidence",
        {
            "user_id": "mcp-user",
            "addresses": ["hr@example.com", "manager@example.com"],
            "claim_element_id": "causation",
            "folders": ["[Gmail]/Sent Mail", "[Gmail]/All Mail"],
            "years_back": 2,
            "complaint_query": "termination retaliation hr complaint",
            "complaint_keywords": ["termination", "retaliation"],
            "min_relevance_score": 2.0,
            "use_uid_checkpoint": True,
            "checkpoint_name": "gmail-resume",
            "uid_window_size": 100,
            "gmail_user": "user@gmail.com",
            "gmail_app_password": "app-password",
        },
    )

    assert payload["status"] == "success"
    assert payload["matched_addresses"] == ["hr@example.com", "manager@example.com"]
    assert payload["imported_count"] == 1
    assert captured["folders"] == ["[Gmail]/Sent Mail", "[Gmail]/All Mail"]
    assert captured["years_back"] == 2
    assert captured["complaint_query"] == "termination retaliation hr complaint"
    assert captured["complaint_keywords"] == ["termination", "retaliation"]
    assert captured["min_relevance_score"] == 2.0
    assert captured["use_uid_checkpoint"] is True
    assert captured["checkpoint_name"] == "gmail-resume"
    assert captured["uid_window_size"] == 100

    session = service.get_session("mcp-user")["session"]
    documents = session["evidence"]["documents"]
    assert len(documents) == 1
    assert documents[0]["title"] == "Email import: Termination email"
    assert documents[0]["attachment_names"] == ["message.eml", "termination.pdf", "message.json"]


def test_import_gmail_evidence_api_route(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "gmail-import-api-sessions")
    app = FastAPI()
    attach_complaint_workspace_routes(app, service)
    from fastapi.testclient import TestClient

    client = TestClient(app)

    captured = {}

    def fake_import_gmail_evidence(
        user_id,
        *,
        addresses,
        claim_element_id="causation",
        folder="INBOX",
        folders=None,
        limit=None,
        date_after=None,
        date_before=None,
        years_back=None,
        evidence_root=None,
        gmail_user=None,
        gmail_app_password=None,
        complaint_query=None,
        complaint_keywords=None,
        min_relevance_score=0.0,
        use_uid_checkpoint=False,
        checkpoint_name=None,
        uid_window_size=None,
    ):
        captured.update(
            {
                "folders": folders,
                "years_back": years_back,
                "complaint_query": complaint_query,
                "complaint_keywords": complaint_keywords,
                "min_relevance_score": min_relevance_score,
                "use_uid_checkpoint": use_uid_checkpoint,
                "checkpoint_name": checkpoint_name,
                "uid_window_size": uid_window_size,
            }
        )
        service.save_evidence(
            user_id,
            kind="document",
            claim_element_id=claim_element_id,
            title="Email import: Termination email",
            content="Imported from Gmail via API",
            source="gmail_imap_import",
            attachment_names=["message.eml", "termination.pdf", "message.json"],
        )
        return {
            "status": "success",
            "user_id": user_id,
            "matched_addresses": list(addresses),
            "imported_count": 1,
            "searched_message_count": 2,
            "evidence_root": str(evidence_root or (tmp_path / "evidence")),
            "imported": [{"subject": "Termination email", "artifact_dir": str(tmp_path / "evidence" / "case")}],
        }

    monkeypatch.setattr(service, "import_gmail_evidence", fake_import_gmail_evidence)

    response = client.post(
        "/api/complaint-workspace/import-gmail-evidence",
        json={
            "user_id": "api-user",
            "addresses": ["hr@example.com", "manager@example.com"],
            "claim_element_id": "causation",
            "folders": ["[Gmail]/Sent Mail"],
            "years_back": 2,
            "complaint_query": "termination retaliation hr complaint",
            "complaint_keywords": ["termination", "retaliation"],
            "min_relevance_score": 1.25,
            "use_uid_checkpoint": True,
            "checkpoint_name": "gmail-resume",
            "uid_window_size": 50,
            "gmail_user": "user@gmail.com",
            "gmail_app_password": "app-password",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["matched_addresses"] == ["hr@example.com", "manager@example.com"]
    assert captured["folders"] == ["[Gmail]/Sent Mail"]
    assert captured["years_back"] == 2
    assert captured["complaint_query"] == "termination retaliation hr complaint"
    assert captured["complaint_keywords"] == ["termination", "retaliation"]
    assert captured["min_relevance_score"] == 1.25
    assert captured["use_uid_checkpoint"] is True
    assert captured["checkpoint_name"] == "gmail-resume"
    assert captured["uid_window_size"] == 50
    assert payload["imported_count"] == 1

    session = service.get_session("api-user")["session"]
    documents = session["evidence"]["documents"]
    assert len(documents) == 1
    assert documents[0]["title"] == "Email import: Termination email"
    assert documents[0]["attachment_names"] == ["message.eml", "termination.pdf", "message.json"]


def test_import_local_evidence_cli_command(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "local-import-cli-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)

    evidence_file = tmp_path / "timeline.txt"
    evidence_file.write_text("Timeline notes for the retaliation case.", encoding="utf-8")

    payload = _invoke_cli(
        runner,
        "import-local-evidence",
        "--user-id",
        "cli-user",
        "--path",
        str(evidence_file),
        "--claim-element-id",
        "causation",
    )

    assert payload["status"] == "success"
    assert payload["imported_count"] == 1
    session = service.get_session("cli-user")["session"]
    documents = session["evidence"]["documents"]
    assert len(documents) == 1
    assert documents[0]["title"] == "Local import: timeline.txt"


def test_run_gmail_duckdb_pipeline_cli_command(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "gmail-pipeline-cli-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)

    async def fake_run_gmail_duckdb_pipeline(**kwargs):
        return {
            "status": "success",
            "pipeline": "gmail_duckdb_pipeline",
            "user_id": kwargs["user_id"],
            "batch_count": 2,
            "total_imported_count": 3,
            "duckdb_index": {"duckdb_path": str(tmp_path / "duckdb" / "email_corpus.duckdb")},
            "bm25_search": {"query": "termination", "result_count": 2},
        }

    monkeypatch.setattr(complaint_cli_impl, "run_gmail_duckdb_pipeline", fake_run_gmail_duckdb_pipeline)

    payload = _invoke_cli(
        runner,
        "run-gmail-duckdb-pipeline",
        "--user-id",
        "cli-user",
        "--address",
        "hr@example.com",
        "--years-back",
        "2",
        "--uid-window-size",
        "250",
        "--max-batches",
        "5",
        "--gmail-user",
        "user@gmail.com",
        "--gmail-app-password",
        "app-password",
        "--bm25-search-query",
        "termination",
    )

    assert payload["status"] == "success"
    assert payload["pipeline"] == "gmail_duckdb_pipeline"
    assert payload["batch_count"] == 2
    assert payload["bm25_search"]["result_count"] == 2


def test_search_email_duckdb_cli_command(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "email-search-cli-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)
    monkeypatch.setattr(
        complaint_cli_impl,
        "search_email_duckdb_corpus",
        lambda **kwargs: {
            "status": "success",
            "query": kwargs["query"],
            "ranking": kwargs["ranking"],
            "result_count": 1,
            "results": [{"subject": "Termination email"}],
        },
    )

    payload = _invoke_cli(
        runner,
        "search-email-duckdb",
        "--index-path",
        str(tmp_path / "duckdb" / "email_corpus.duckdb"),
        "--query",
        "termination retaliation",
        "--ranking",
        "bm25",
    )

    assert payload["status"] == "success"
    assert payload["ranking"] == "bm25"
    assert payload["result_count"] == 1


def test_run_gmail_duckdb_pipeline_mcp_tool(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "gmail-pipeline-mcp-sessions")
    monkeypatch.setattr(
        service,
        "run_gmail_duckdb_pipeline",
        lambda user_id, **kwargs: {
            "status": "success",
            "pipeline": "gmail_duckdb_pipeline",
            "user_id": user_id,
            "years_back": kwargs["years_back"],
            "batch_count": 1,
        },
    )

    payload = _call_mcp_tool(
        service,
        23_1,
        "complaint.run_gmail_duckdb_pipeline",
        {
            "user_id": "mcp-user",
            "addresses": ["hr@example.com"],
            "years_back": 2,
        },
    )

    assert payload["status"] == "success"
    assert payload["years_back"] == 2
    assert payload["batch_count"] == 1


def test_search_email_duckdb_mcp_tool(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "email-search-mcp-sessions")
    monkeypatch.setattr(
        service,
        "search_email_duckdb_corpus",
        lambda **kwargs: {
            "status": "success",
            "query": kwargs["query"],
            "result_count": 1,
            "results": [{"subject": "Termination email"}],
        },
    )

    payload = _call_mcp_tool(
        service,
        24_1,
        "complaint.search_email_duckdb_corpus",
        {
            "index_path": str(tmp_path / "duckdb" / "email_corpus.duckdb"),
            "query": "termination",
        },
    )

    assert payload["status"] == "success"
    assert payload["result_count"] == 1


def test_run_gmail_duckdb_pipeline_api_route(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "gmail-pipeline-api-sessions")
    app = FastAPI()
    attach_complaint_workspace_routes(app, service)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    monkeypatch.setattr(
        service,
        "run_gmail_duckdb_pipeline",
        lambda user_id, **kwargs: {
            "status": "success",
            "pipeline": "gmail_duckdb_pipeline",
            "user_id": user_id,
            "batch_count": 2,
            "years_back": kwargs["years_back"],
        },
    )

    response = client.post(
        "/api/complaint-workspace/run-gmail-duckdb-pipeline",
        json={"user_id": "api-user", "addresses": ["hr@example.com"], "years_back": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["years_back"] == 2


def test_search_email_duckdb_api_route(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "email-search-api-sessions")
    app = FastAPI()
    attach_complaint_workspace_routes(app, service)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    monkeypatch.setattr(
        service,
        "search_email_duckdb_corpus",
        lambda **kwargs: {
            "status": "success",
            "ranking": kwargs["ranking"],
            "result_count": 1,
            "results": [{"subject": "Termination email"}],
        },
    )

    response = client.post(
        "/api/complaint-workspace/search-email-duckdb",
        json={"index_path": str(tmp_path / "duckdb" / "email_corpus.duckdb"), "query": "termination", "ranking": "bm25"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["ranking"] == "bm25"


def test_import_local_evidence_mcp_tool(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "local-import-mcp-sessions")
    evidence_file = tmp_path / "timeline.txt"
    evidence_file.write_text("Timeline notes for the retaliation case.", encoding="utf-8")

    payload = _call_mcp_tool(
        service,
        22_1,
        "complaint.import_local_evidence",
        {
            "user_id": "mcp-user",
            "paths": [str(evidence_file)],
            "claim_element_id": "causation",
        },
    )

    assert payload["status"] == "success"
    assert payload["imported_count"] == 1
    session = service.get_session("mcp-user")["session"]
    documents = session["evidence"]["documents"]
    assert len(documents) == 1
    assert documents[0]["title"] == "Local import: timeline.txt"


def test_import_local_evidence_api_route(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "local-import-api-sessions")
    app = FastAPI()
    attach_complaint_workspace_routes(app, service)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    evidence_file = tmp_path / "timeline.txt"
    evidence_file.write_text("Timeline notes for the retaliation case.", encoding="utf-8")

    response = client.post(
        "/api/complaint-workspace/import-local-evidence",
        json={
            "user_id": "api-user",
            "paths": [str(evidence_file)],
            "claim_element_id": "causation",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["imported_count"] == 1
    session = service.get_session("api-user")["session"]
    documents = session["evidence"]["documents"]
    assert len(documents) == 1
    assert documents[0]["title"] == "Local import: timeline.txt"


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
    assert any(tool["name"] == "complaint.export_complaint_markdown" for tool in tools_payload["tools"])
    assert any(tool["name"] == "complaint.export_complaint_pdf" for tool in tools_payload["tools"])
    assert any(tool["name"] == "complaint.export_complaint_docx" for tool in tools_payload["tools"])
    assert any(tool["name"] == "complaint.analyze_complaint_output" for tool in tools_payload["tools"])
    assert any(tool["name"] == "complaint.get_formal_diagnostics" for tool in tools_payload["tools"])
    assert any(tool["name"] == "complaint.review_generated_exports" for tool in tools_payload["tools"])
    assert any(tool["name"] == "complaint.update_claim_type" for tool in tools_payload["tools"])
    assert any(tool["name"] == "complaint.get_client_release_gate" for tool in tools_payload["tools"])
    assert any(tool["name"] == "complaint.get_tooling_contract" for tool in tools_payload["tools"])

    async def fake_import_gmail_evidence(**kwargs):
        service.save_evidence(
            kwargs["user_id"],
            kind="document",
            claim_element_id=kwargs["claim_element_id"],
            title="Email import: Termination email",
            content="Imported from Gmail",
            source="gmail_imap_import",
            attachment_names=["message.eml", "termination.pdf", "message.json"],
        )
        return {
            "status": "success",
            "user_id": kwargs["user_id"],
            "claim_element_id": kwargs["claim_element_id"],
            "matched_addresses": list(kwargs["addresses"]),
            "searched_message_count": 3,
            "imported_count": 1,
            "evidence_root": str(kwargs["evidence_root"] or (tmp_path / "evidence")),
            "imported": [
                {
                    "subject": "Termination email",
                    "artifact_dir": str(tmp_path / "evidence" / "case"),
                }
            ],
        }

    monkeypatch.setattr(complaint_cli_impl, "import_gmail_evidence", fake_import_gmail_evidence)

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

    chat_turn_payload = _invoke_cli(runner, "chat-turn", "--user-id", "cli-user")
    assert chat_turn_payload["inquiry"]["question_id"] == "party_name"

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

    gmail_import_payload = _invoke_cli(
        runner,
        "import-gmail-evidence",
        "--user-id",
        "cli-user",
        "--address",
        "hr@example.com",
        "--address",
        "manager@example.com",
        "--claim-element-id",
        "causation",
        "--gmail-user",
        "user@gmail.com",
        "--gmail-app-password",
        "app-password",
    )
    assert gmail_import_payload["status"] == "success"
    assert gmail_import_payload["matched_addresses"] == ["hr@example.com", "manager@example.com"]
    assert gmail_import_payload["imported_count"] == 1

    review_payload = _invoke_cli(runner, "review", "--user-id", "cli-user")
    assert review_payload["review"]["claim_type"] == "retaliation"
    assert review_payload["session"]["user_id"] == "cli-user"
    assert "case_synopsis" in review_payload
    assert "Reported discrimination to HR" in review_payload["review"]["case_synopsis"]

    mediator_payload = _invoke_cli(runner, "mediator-prompt", "--user-id", "cli-user")
    assert "Mediator, help turn this into testimony-ready narrative" in mediator_payload["prefill_message"]

    readiness_payload = _invoke_cli(runner, "complaint-readiness", "--user-id", "cli-user")
    assert readiness_payload["verdict"] in {"Not ready to draft", "Still building the record", "Ready for first draft", "Draft in progress"}
    assert isinstance(readiness_payload["score"], int)

    ui_readiness_payload = _invoke_cli(runner, "ui-readiness", "--user-id", "cli-user")
    assert ui_readiness_payload["verdict"] in {"No UI verdict cached", "Needs repair", "Client-safe", "Do not send to clients yet"}

    client_release_gate_payload = _invoke_cli(runner, "client-release-gate", "--user-id", "cli-user")
    assert client_release_gate_payload["verdict"] in {"client_safe", "warning", "blocked"}
    assert "complaint_readiness" in client_release_gate_payload
    assert "ui_readiness" in client_release_gate_payload

    capabilities_payload = _invoke_cli(runner, "capabilities", "--user-id", "cli-user")
    assert any(item["id"] == "complaint_packet" for item in capabilities_payload["capabilities"])
    assert "complaint_readiness" in capabilities_payload
    assert "ui_readiness" in capabilities_payload
    assert "client_release_gate" in capabilities_payload

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
    assert "Civil Action No. ________________" in generate_payload["draft"]["body"]
    assert "COMPLAINT FOR RETALIATION" in generate_payload["draft"]["body"]
    assert "JURISDICTION AND VENUE" in generate_payload["draft"]["body"]
    assert "FACTUAL ALLEGATIONS" in generate_payload["draft"]["body"]
    assert "EVIDENTIARY SUPPORT AND NOTICE" in generate_payload["draft"]["body"]
    assert "COUNT I - RETALIATION" in generate_payload["draft"]["body"]
    assert "PRAYER FOR RELIEF" in generate_payload["draft"]["body"]
    assert "JURY DEMAND" in generate_payload["draft"]["body"]
    assert "SIGNATURE BLOCK" in generate_payload["draft"]["body"]
    assert "Plaintiff, Pro Se" in generate_payload["draft"]["body"]
    assert "Address: ____________________" in generate_payload["draft"]["body"]
    assert "Email: ____________________" in generate_payload["draft"]["body"]
    assert "WORKING CASE SYNOPSIS" not in generate_payload["draft"]["body"]
    assert "proceeding pro se" in generate_payload["draft"]["body"]
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
    assert export_payload["packet_summary"]["artifact_formats"] == ["docx", "json", "markdown", "pdf"]
    assert export_payload["packet_summary"]["draft_strategy"] == "template"

    markdown_payload = _invoke_cli(runner, "export-markdown", "--user-id", "cli-user")
    assert markdown_payload["artifact"]["format"] == "markdown"
    assert markdown_payload["artifact"]["filename"].endswith(".md")
    assert "Edited complaint body from CLI." in markdown_payload["artifact"]["excerpt"]

    pdf_payload = _invoke_cli(runner, "export-pdf", "--user-id", "cli-user")
    assert pdf_payload["artifact"]["format"] == "pdf"
    assert pdf_payload["artifact"]["filename"].endswith(".pdf")
    assert isinstance(pdf_payload["artifact"]["header_b64"], str)

    docx_payload = _invoke_cli(runner, "export-docx", "--user-id", "cli-user")
    assert docx_payload["artifact"]["format"] == "docx"
    assert docx_payload["artifact"]["filename"].endswith(".docx")
    assert isinstance(docx_payload["artifact"]["header_b64"], str)

    output_analysis_payload = _invoke_cli(runner, "analyze-output", "--user-id", "cli-user")
    assert output_analysis_payload["ui_feedback"]["summary"].startswith("The exported complaint artifact was analyzed")
    assert output_analysis_payload["packet_summary"]["has_draft"] is True
    assert output_analysis_payload["artifact_analysis"]["draft_word_count"] >= 1
    assert output_analysis_payload["ui_feedback"]["filing_shape_score"] < 70
    assert output_analysis_payload["ui_feedback"]["formal_sections_present"]["civil_action_number"] is False
    assert output_analysis_payload["ui_feedback"]["formal_sections_present"]["evidentiary_support"] is False
    assert output_analysis_payload["ui_feedback"]["formal_sections_present"]["claim_count"] is False
    assert output_analysis_payload["ui_feedback"]["formal_sections_present"]["signature_block"] is False
    assert any(
        item["title"] == "Enforce formal pleading structure"
        for item in output_analysis_payload["ui_feedback"]["ui_suggestions"]
    )

    formal_diagnostics_payload = _invoke_cli(runner, "formal-diagnostics", "--user-id", "cli-user")
    assert formal_diagnostics_payload["packet_summary"]["has_draft"] is True
    assert formal_diagnostics_payload["formal_diagnostics"]["release_gate_verdict"] in {"pass", "warning", "blocked"}
    assert isinstance(formal_diagnostics_payload["release_gate"], dict)
    provider_diagnostics_payload = _invoke_cli(runner, "provider-diagnostics", "--user-id", "cli-user")
    assert provider_diagnostics_payload["default_order"][:4] == ["codex_cli", "copilot_cli", "openai", "hf_inference_api"]
    assert provider_diagnostics_payload["ui_review_default_provider"] == "codex_cli"
    assert provider_diagnostics_payload["ui_review_hf_fallback_model"] == "Qwen/Qwen2.5-VL-7B-Instruct"
    assert isinstance(provider_diagnostics_payload["providers"], list)

    claim_type_payload = _invoke_cli(
        runner,
        "set-claim-type",
        "--user-id",
        "cli-user",
        "--claim-type",
        "housing_discrimination",
    )
    assert claim_type_payload["claim_type"] == "housing_discrimination"
    assert claim_type_payload["claim_type_label"] == "Housing Discrimination"

    housing_generate_payload = _invoke_cli(
        runner,
        "generate",
        "--user-id",
        "cli-user",
        "--requested-relief",
        "Declaratory relief|Injunctive relief",
        "--title-override",
        "CLI housing complaint",
    )
    assert housing_generate_payload["draft"]["claim_type"] == "housing_discrimination"
    assert "COMPLAINT FOR HOUSING DISCRIMINATION" in housing_generate_payload["draft"]["body"]
    assert "COUNT I - HOUSING DISCRIMINATION" in housing_generate_payload["draft"]["body"]
    assert (
        "discriminatory denial, limitation, interference, or retaliation affecting housing rights or benefits"
        in housing_generate_payload["draft"]["body"]
    )

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

    readiness_payload = _call_mcp_tool(service, 24, "complaint.get_complaint_readiness", {"user_id": "mcp-user"})
    assert readiness_payload["verdict"] in {"Not ready to draft", "Still building the record", "Ready for first draft", "Draft in progress"}
    assert isinstance(readiness_payload["score"], int)

    ui_readiness_payload = _call_mcp_tool(service, 25, "complaint.get_ui_readiness", {"user_id": "mcp-user"})
    assert ui_readiness_payload["verdict"] in {"No UI verdict cached", "Needs repair", "Client-safe", "Do not send to clients yet"}

    capabilities_payload = _call_mcp_tool(service, 26, "complaint.get_workflow_capabilities", {"user_id": "mcp-user"})
    assert any(item["id"] == "complaint_packet" for item in capabilities_payload["capabilities"])
    assert "complaint_readiness" in capabilities_payload
    assert "ui_readiness" in capabilities_payload

    claim_type_payload = _call_mcp_tool(
        service,
        26_1,
        "complaint.update_claim_type",
        {"user_id": "mcp-user", "claim_type": "housing_discrimination"},
    )
    assert claim_type_payload["claim_type"] == "housing_discrimination"
    assert claim_type_payload["claim_type_label"] == "Housing Discrimination"

    generate_payload = _call_mcp_tool(
        service,
        27,
        "complaint.generate_complaint",
        {
            "user_id": "mcp-user",
            "requested_relief": ["Back pay", "Compensatory damages"],
            "title_override": "MCP generated complaint",
        },
    )
    assert generate_payload["draft"]["title"] == "MCP generated complaint"
    assert generate_payload["draft"]["requested_relief"] == ["Back pay", "Compensatory damages"]
    assert "Civil Action No. ________________" in generate_payload["draft"]["body"]
    assert "COMPLAINT FOR HOUSING DISCRIMINATION" in generate_payload["draft"]["body"]
    assert "JURISDICTION AND VENUE" in generate_payload["draft"]["body"]
    assert "FACTUAL ALLEGATIONS" in generate_payload["draft"]["body"]
    assert "EVIDENTIARY SUPPORT AND NOTICE" in generate_payload["draft"]["body"]
    assert "COUNT I - HOUSING DISCRIMINATION" in generate_payload["draft"]["body"]
    assert "PRAYER FOR RELIEF" in generate_payload["draft"]["body"]
    assert "JURY DEMAND" in generate_payload["draft"]["body"]
    assert "proceeding pro se" in generate_payload["draft"]["body"]
    assert (
        "discriminatory denial, limitation, interference, or retaliation affecting housing rights or benefits"
        in generate_payload["draft"]["body"]
    )
    assert "Reported discrimination to HR" in generate_payload["draft"]["case_synopsis"]

    update_payload = _call_mcp_tool(
        service,
        28,
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

    export_payload = _call_mcp_tool(service, 29, "complaint.export_complaint_packet", {"user_id": "mcp-user"})
    assert export_payload["packet"]["draft"]["title"] == "Updated MCP complaint"
    assert export_payload["packet_summary"]["has_draft"] is True
    assert "complaint_readiness" in export_payload["packet_summary"]
    assert export_payload["packet_summary"]["artifact_formats"] == ["docx", "json", "markdown", "pdf"]
    assert export_payload["packet"]["claim_type"] == "housing_discrimination"
    assert export_payload["artifacts"]["markdown"]["filename"].endswith(".md")
    assert "Updated body from MCP." in export_payload["artifacts"]["markdown"]["content"]
    assert export_payload["artifacts"]["pdf"]["filename"].endswith(".pdf")
    assert export_payload["ui_feedback"]["ui_suggestions"]

    markdown_export = _call_mcp_tool(service, 30, "complaint.export_complaint_markdown", {"user_id": "mcp-user"})
    assert markdown_export["artifact"]["format"] == "markdown"
    assert markdown_export["artifact"]["filename"].endswith(".md")
    assert "Updated body from MCP." in markdown_export["artifact"]["excerpt"]

    pdf_export = _call_mcp_tool(service, 31, "complaint.export_complaint_pdf", {"user_id": "mcp-user"})
    assert pdf_export["artifact"]["format"] == "pdf"
    assert pdf_export["artifact"]["filename"].endswith(".pdf")
    assert isinstance(pdf_export["artifact"]["header_b64"], str)

    docx_export = _call_mcp_tool(service, 31_1, "complaint.export_complaint_docx", {"user_id": "mcp-user"})
    assert docx_export["artifact"]["format"] == "docx"
    assert docx_export["artifact"]["filename"].endswith(".docx")
    assert isinstance(docx_export["artifact"]["header_b64"], str)

    output_analysis_payload = _call_mcp_tool(service, 32, "complaint.analyze_complaint_output", {"user_id": "mcp-user"})
    assert output_analysis_payload["ui_feedback"]["summary"].startswith("The exported complaint artifact was analyzed")
    assert output_analysis_payload["packet_summary"]["has_draft"] is True
    formal_diagnostics_payload = _call_mcp_tool(service, 33, "complaint.get_formal_diagnostics", {"user_id": "mcp-user"})
    assert formal_diagnostics_payload["packet_summary"]["has_draft"] is True
    assert formal_diagnostics_payload["formal_diagnostics"]["release_gate_verdict"] in {"pass", "warning", "blocked"}
    provider_diagnostics_payload = _call_mcp_tool(service, 34, "complaint.get_provider_diagnostics", {"user_id": "mcp-user"})
    assert provider_diagnostics_payload["default_order"][:4] == ["codex_cli", "copilot_cli", "openai", "hf_inference_api"]
    assert provider_diagnostics_payload["complaint_draft_default_order"] == ["codex_cli", "copilot_cli", "hf_inference_api"]
    assert provider_diagnostics_payload["effective_complaint_draft_provider"] == "codex_cli"
    assert provider_diagnostics_payload["ui_review_multimodal_rate_limit_fallbacks"]["codex_cli"] == ["copilot_cli", "hf_inference_api"]
    assert isinstance(provider_diagnostics_payload["providers"], list)


def test_provider_diagnostics_are_exposed_across_package_cli_and_mcp(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "provider-diagnostics-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)

    package_payload = get_provider_diagnostics("diag-user", service=service)
    cli_payload = _invoke_cli(runner, "provider-diagnostics", "--user-id", "diag-user")
    mcp_payload = _call_mcp_tool(service, 91, "complaint.get_provider_diagnostics", {"user_id": "diag-user"})

    for payload in (package_payload, cli_payload, mcp_payload):
        assert payload["default_order"][:4] == ["codex_cli", "copilot_cli", "openai", "hf_inference_api"]
        assert payload["complaint_draft_default_order"] == ["codex_cli", "copilot_cli", "hf_inference_api"]
        assert payload["effective_complaint_draft_provider"] == "codex_cli"
        assert payload["ui_review_default_provider"] == "codex_cli"
        assert payload["ui_review_hf_fallback_model"] == "Qwen/Qwen2.5-VL-7B-Instruct"
        assert isinstance(payload["providers"], list)
        assert "effective_default_provider" in payload
        codex_entry = next(item for item in payload["providers"] if item["name"] == "codex_cli")
        copilot_entry = next(item for item in payload["providers"] if item["name"] == "copilot_cli")
        assert codex_entry["draft_timeout_seconds"] == 90
        assert copilot_entry["draft_timeout_seconds"] == 45


def test_export_and_diagnostics_preserve_router_backend(monkeypatch, tmp_path):
    from applications import ui_review as ui_review_module

    service = ComplaintWorkspaceService(root_dir=tmp_path / "router-backend-sessions")

    service.submit_intake_answers(
        "router-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Report on April 2, termination on April 4",
            "harm": "Lost wages and benefits",
        },
    )
    service.save_evidence(
        "router-user",
        kind="document",
        claim_element_id="causation",
        title="Termination email",
        content="Termination followed immediately after the report.",
    )

    def fake_refine(self, draft, *args, **kwargs):
        updated = dict(draft)
        updated.setdefault("title", "Jordan Example v. Acme Corporation Retaliation Complaint")
        updated.setdefault("requested_relief", ["Back pay"])
        updated["body"] = str(updated.get("body") or "") + "\n\nSIGNATURE BLOCK"
        updated["draft_strategy"] = "llm_router"
        updated["draft_normalizations"] = list(updated.get("draft_normalizations") or [])
        return updated

    monkeypatch.setattr(ComplaintWorkspaceService, "_refine_draft_with_llm_router", fake_refine)
    service.generate_complaint("router-user", requested_relief=["Back pay"], use_llm=True, provider="llm_router", model="formal_complaint_reviewer")

    def fake_review(*args, **kwargs):
        return {
            "backend": {
                "strategy": "llm_router",
                "provider": "llm_router",
                "model": "formal_complaint_reviewer",
            },
            "review": {
                "summary": "Looks filing-shaped.",
                "filing_shape_score": 92,
                "claim_type_alignment_score": 95,
                "missing_formal_sections": [],
                "issues": [],
                "ui_suggestions": [{"title": "Keep filing diagnostics visible"}],
                "ui_priority_repairs": [{"priority": "high", "target_surface": "draft"}],
                "actor_risk_summary": "The actor still needs explicit filing readiness cues.",
                "critic_gate": {"verdict": "warning", "blocking_reason": "Keep diagnostics visible."},
            },
        }

    monkeypatch.setattr(ui_review_module, "review_complaint_output_with_llm_router", fake_review)

    export_payload = service.export_complaint_packet("router-user")
    assert export_payload["packet_summary"]["draft_strategy"] == "llm_router"
    assert export_payload["packet_summary"]["complaint_output_router_backend"]["strategy"] == "llm_router"
    assert export_payload["packet_summary"]["complaint_output_router_backend"]["model"] == "formal_complaint_reviewer"

    diagnostics_payload = service.get_formal_diagnostics("router-user")
    assert diagnostics_payload["router_backend"]["strategy"] == "llm_router"
    assert diagnostics_payload["packet_summary"]["complaint_output_router_backend"]["provider"] == "llm_router"


def test_filing_provenance_is_exposed_across_package_cli_and_mcp(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "filing-provenance-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)

    service.submit_intake_answers(
        "provenance-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Report on April 2, termination on April 4",
            "harm": "Lost wages and benefits",
        },
    )
    service.save_evidence(
        "provenance-user",
        kind="document",
        claim_element_id="causation",
        title="Termination email",
        content="Termination followed immediately after the report.",
    )
    service.generate_complaint("provenance-user", requested_relief=["Back pay"])
    service._persist_ui_readiness(
        "provenance-user",
        {
            "backend": {
                "strategy": "multimodal_router",
                "provider": "llm_router",
                "model": "multimodal_router",
            },
            "workflow_type": "ui_ux_closed_loop",
            "review": {
                "summary": "Cached UI audit.",
                "critic_review": {"verdict": "warning"},
                "complaint_journey": {"tested_stages": ["intake", "evidence", "review", "draft"]},
            },
        },
    )
    state = service._load_state("provenance-user")
    state["latest_export_critic"] = {
        "aggregate": {
            "router_backends": [
                {
                    "strategy": "llm_router",
                    "provider": "llm_router",
                    "model": "formal_complaint_reviewer",
                }
            ]
        }
    }
    service._save_state(state)

    cli_payload = _invoke_cli(runner, "filing-provenance", "--user-id", "provenance-user")
    assert cli_payload["has_draft"] is True
    assert cli_payload["ui_review_backend"]["strategy"] == "multimodal_router"

    mcp_payload = _call_mcp_tool(service, 93, "complaint.get_filing_provenance", {"user_id": "provenance-user"})
    assert mcp_payload["draft_strategy"] in {"template", "llm_router"}
    assert mcp_payload["export_critic_router_backends"][0]["model"] == "formal_complaint_reviewer"

    from complaint_generator import get_filing_provenance

    package_payload = get_filing_provenance("provenance-user", service=service)
    assert package_payload["ui_workflow_type"] == "ui_ux_closed_loop"


@pytest.mark.no_auto_llm
def test_packaged_docket_operator_dashboard_is_exposed_across_package_mcp_and_api(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "workspace-packaged-docket-tools")
    manifest_path = _build_packaged_docket_manifest(
        tmp_path,
        routing_reason="Workspace packaged dashboard routing reason.",
    )

    package_payload = get_packaged_docket_operator_dashboard(
        manifest_path,
        service=service,
    )
    assert package_payload["source"] == "complaint_workspace_packaged_operator_dashboard"
    assert package_payload["inspection"]["latest_routing_reason"] == "Workspace packaged dashboard routing reason."

    report_payload = load_packaged_docket_operator_dashboard_report(
        manifest_path,
        report_format="text",
        service=service,
    )
    assert report_payload["report_format"] == "text"
    assert "Packaged Docket Operator Dashboard" in report_payload["report"]

    mcp_payload = _call_mcp_tool(
        service,
        94,
        "complaint.get_packaged_docket_operator_dashboard",
        {"manifest_path": manifest_path},
    )
    assert mcp_payload["manifest_path"] == str(manifest_path)
    assert mcp_payload["inspection"]["latest_routing_reason"] == "Workspace packaged dashboard routing reason."

    mcp_report_payload = _call_mcp_tool(
        service,
        95,
        "complaint.load_packaged_docket_operator_dashboard_report",
        {"manifest_path": manifest_path, "report_format": "parsed"},
    )
    assert mcp_report_payload["report_format"] == "parsed"
    assert mcp_report_payload["report"]["source"] == "packaged_operator_dashboard"

    app = FastAPI()
    attach_complaint_workspace_routes(app, service)
    client = TestClient(app)

    dashboard_response = client.get(
        "/api/complaint-workspace/packaged-docket/operator-dashboard",
        params={"manifest_path": manifest_path},
    )
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["inspection"]["latest_routing_reason"] == "Workspace packaged dashboard routing reason."

    report_response = client.get(
        "/api/complaint-workspace/packaged-docket/operator-dashboard-report",
        params={"manifest_path": manifest_path, "report_format": "text"},
    )
    assert report_response.status_code == 200
    assert "Packaged Docket Operator Dashboard" in report_response.json()["report"]

    view_response = client.get(
        "/api/complaint-workspace/packaged-docket/view",
        params={"manifest_path": manifest_path, "include_document_text": True, "document_limit": 5},
    )
    assert view_response.status_code == 200
    assert view_response.json()["source"] == "complaint_workspace_docket_view"
    assert isinstance(view_response.json()["documents"], list)
    assert view_response.json()["case_calendar_summary"]["count"] == 1
    assert view_response.json()["case_calendar"][0]["kind"] == "hearing"
    assert view_response.json()["case_calendar"][0]["title"] == "Notice of Hearing"
    assert view_response.json()["case_calendar"][0]["date"] == "May 1, 2024"


@pytest.mark.no_auto_llm
def test_single_parquet_docket_dataset_dashboard_routes_use_ipfs_dataset_loader(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "single-parquet-docket-dashboard")
    parquet_path = _build_single_docket_parquet(tmp_path)

    view_payload = service.view_docket_dataset(
        parquet_path,
        input_type="single",
        include_document_text=True,
        document_limit=10,
    )
    assert view_payload["input_type"] == "single"
    assert view_payload["summary"]["case_name"] == "Single Parquet Docket"
    assert view_payload["summary"]["document_count"] == 2
    assert any(document["title"] == "Notice of Hearing" for document in view_payload["documents"])

    search_payload = service.search_docket_dataset(
        parquet_path,
        input_type="single",
        query="hearing",
        search_backend="bm25",
        top_k=5,
    )
    assert search_payload["source"] == "complaint_workspace_docket_search"
    assert search_payload["search_results"]["result_count"] >= 1

    app = FastAPI()
    attach_complaint_workspace_routes(app, service)
    client = TestClient(app)

    view_response = client.get(
        "/api/complaint-workspace/docket-dataset/view",
        params={
            "input_path": parquet_path,
            "input_type": "single",
            "include_document_text": True,
            "document_limit": 10,
        },
    )
    assert view_response.status_code == 200
    assert view_response.json()["summary"]["case_name"] == "Single Parquet Docket"
    assert view_response.json()["case_calendar_summary"]["count"] == 1
    assert view_response.json()["case_calendar"][0]["date"] == "April 21, 2026"

    search_response = client.get(
        "/api/complaint-workspace/docket-dataset/search",
        params={
            "input_path": parquet_path,
            "input_type": "single",
            "query": "hearing",
            "search_backend": "bm25",
        },
    )
    assert search_response.status_code == 200
    assert search_response.json()["search_results"]["result_count"] >= 1

    graph_response = client.get(
        "/api/complaint-workspace/docket-dataset/graph",
        params={"input_path": parquet_path, "input_type": "single"},
    )
    assert graph_response.status_code == 200
    assert graph_response.json()["source"] == "complaint_workspace_docket_graph"


def test_successful_llm_draft_persists_effective_router_backend_metadata(monkeypatch, tmp_path):
    from applications import ui_review as ui_review_module

    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-router-effective-backend")

    service.submit_intake_answers(
        "effective-backend-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Report on April 2, termination on April 4",
            "harm": "Lost wages and benefits",
        },
    )

    def fake_invoke(self, backend, prompt):
        backend.last_result_metadata = {
            "status": "available",
            "provider_name": "",
            "model_name": "",
            "effective_provider_name": "copilot_cli",
            "effective_model_name": "gpt-5-mini",
        }
        return json.dumps(
            {
                "title": "Jordan Example v. Acme Corporation Retaliation Complaint",
                "body": (
                    "IN THE UNITED STATES DISTRICT COURT\n"
                    "FOR THE NORTHERN DISTRICT OF CALIFORNIA\n\n"
                    "Jordan Example, Plaintiff,\n\n"
                    "v.\n\n"
                    "Acme Corporation, Defendant.\n\n"
                    "Civil Action No. ________________\n\n"
                    "COMPLAINT FOR RETALIATION\n\n"
                    "JURY TRIAL DEMANDED\n\n"
                    "NATURE OF THE ACTION\n"
                    "1. Plaintiff brings this retaliation complaint.\n\n"
                    "JURISDICTION AND VENUE\n"
                    "2. Jurisdiction and venue are proper.\n\n"
                    "PARTIES\n"
                    "3. The parties are identified above.\n\n"
                    "FACTUAL ALLEGATIONS\n"
                    "4. Plaintiff reported discrimination to HR and was terminated two days later.\n\n"
                    "EVIDENTIARY SUPPORT AND NOTICE\n"
                    "5. Plaintiff may rely on documentary exhibit testimony and personnel records.\n\n"
                    "CLAIM FOR RELIEF\n"
                    "COUNT I - RETALIATION\n"
                    "6. Defendant retaliated against Plaintiff for protected activity.\n\n"
                    "PRAYER FOR RELIEF\n"
                    "WHEREFORE, Plaintiff requests judgment.\n\n"
                    "JURY DEMAND\n"
                    "Plaintiff demands a jury trial.\n\n"
                    "SIGNATURE BLOCK\n"
                    "Jordan Example\n"
                ),
                "requested_relief": ["Back pay"],
            }
        )

    monkeypatch.setattr(ComplaintWorkspaceService, "_invoke_llm_draft_backend_with_timeout", fake_invoke)

    def fake_review(*args, **kwargs):
        return {
            "backend": {
                "strategy": "llm_router",
                "provider": "copilot_cli",
                "model": "gpt-5-mini",
            },
            "review": {
                "summary": "Looks filing-shaped.",
                "filing_shape_score": 94,
                "claim_type_alignment_score": 95,
                "missing_formal_sections": [],
                "issues": [],
                "ui_suggestions": [],
                "ui_priority_repairs": [],
                "actor_risk_summary": "Keep the draft flow visible.",
                "critic_gate": {"verdict": "pass", "blocking_reason": ""},
            },
        }

    monkeypatch.setattr(ui_review_module, "review_complaint_output_with_llm_router", fake_review)

    payload = service.generate_complaint(
        "effective-backend-user",
        requested_relief=["Back pay"],
        use_llm=True,
    )
    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert payload["draft"]["draft_backend"]["provider"] == "copilot_cli"
    assert payload["draft"]["draft_backend"]["model"] == "gpt-5-mini"
    assert payload["draft"]["draft_backend"]["id"] == "complaint-draft"

    export_payload = service.export_complaint_packet("effective-backend-user")
    assert export_payload["packet_summary"]["complaint_output_router_backend"]["strategy"] == "llm_router"
    assert export_payload["packet_summary"]["complaint_output_router_backend"]["provider"] == "copilot_cli"
    assert export_payload["packet_summary"]["complaint_output_router_backend"]["model"] == "gpt-5-mini"
    assert export_payload["packet_summary"]["complaint_output_router_backend"]["id"] == "complaint-draft"

    diagnostics_payload = service.get_formal_diagnostics("effective-backend-user")
    assert diagnostics_payload["router_backend"]["provider"] == "copilot_cli"
    assert diagnostics_payload["router_backend"]["model"] == "gpt-5-mini"
    assert diagnostics_payload["router_backend"]["id"] == "complaint-draft"


def test_live_codex_cli_can_generate_and_export_formal_complaint_when_available(tmp_path):
    if str(os.getenv("RUN_LLM_TESTS", "") or "").strip() not in {"1", "true", "True"}:
        pytest.skip("RUN_LLM_TESTS is not enabled for live router-backed drafting.")
    if shutil.which("codex") is None:
        pytest.skip("codex CLI is not available on PATH in this environment.")

    service = ComplaintWorkspaceService(root_dir=tmp_path / "live-codex-router-sessions")
    user_id = "live-codex-user"
    service.submit_intake_answers(
        user_id,
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Report on April 2, termination on April 4",
            "harm": "Lost wages and benefits",
            "court_header": "FOR THE NORTHERN DISTRICT OF CALIFORNIA",
        },
    )
    service.save_evidence(
        user_id,
        kind="document",
        claim_element_id="causation",
        title="Termination email",
        content="Termination followed immediately after the report.",
    )

    payload = service.generate_complaint(
        user_id,
        requested_relief=["Back pay"],
        use_llm=True,
        provider="codex_cli",
    )

    if payload["draft"]["draft_strategy"] != "llm_router":
        pytest.fail(
            "Expected live codex_cli drafting to stay on llm_router, "
            f"but got {payload['draft']['draft_strategy']!r} with fallback "
            f"{payload['draft'].get('draft_fallback_reason')!r}."
        )

    assert payload["draft"]["draft_backend"]["id"] == "complaint-draft"
    assert payload["draft"]["draft_backend"]["provider"] == "codex_cli"
    assert "COMPLAINT FOR RETALIATION" in payload["draft"]["body"]
    assert "JURISDICTION AND VENUE" in payload["draft"]["body"]
    assert "COUNT I - RETALIATION" in payload["draft"]["body"]

    export_payload = service.export_complaint_packet(user_id)
    assert export_payload["packet_summary"]["draft_strategy"] == "llm_router"
    assert export_payload["packet_summary"]["complaint_output_router_backend"]["id"] == "complaint-draft"
    assert export_payload["packet_summary"]["complaint_output_router_backend"]["provider"] == "codex_cli"
    assert export_payload["packet_summary"]["release_gate"]["verdict"] == "pass"
    assert export_payload["artifacts"]["markdown"]["filename"].endswith(".md")
    assert export_payload["artifacts"]["pdf"]["filename"].endswith(".pdf")


def test_cli_and_mcp_can_request_llm_backed_complaint_generation(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-draft-tool-sessions")
    monkeypatch.setattr(complaint_cli_impl, "service", service)

    service.submit_intake_answers(
        "llm-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10.",
            "harm": "Lost wages and emotional distress.",
        },
    )

    observed_calls = []

    def fake_refine(self, state, base_draft, **kwargs):
        observed_calls.append(dict(kwargs))
        return {
            **base_draft,
            "title": f"{base_draft['title']} (LLM)",
            "draft_strategy": "llm_router",
            "draft_backend": {
                "id": "complaint-draft",
                "provider": kwargs.get("provider") or "stub-provider",
                "model": kwargs.get("model") or "stub-model",
            },
        }

    monkeypatch.setattr(ComplaintWorkspaceService, "_refine_draft_with_llm_router", fake_refine)

    cli_payload = _invoke_cli(
        runner,
        "generate",
        "--user-id",
        "llm-user",
        "--requested-relief",
        "Back pay|Injunctive relief",
        "--use-llm",
        "--provider",
        "stub-provider",
        "--model",
        "stub-model",
    )
    assert cli_payload["draft"]["draft_strategy"] == "llm_router"
    assert cli_payload["draft"]["draft_backend"]["provider"] == "stub-provider"
    assert cli_payload["draft"]["draft_backend"]["model"] == "stub-model"

    mcp_payload = _call_mcp_tool(
        service,
        90,
        "complaint.generate_complaint",
        {
            "user_id": "llm-user",
            "requested_relief": ["Front pay", "Declaratory relief"],
            "use_llm": True,
            "provider": "stub-provider-2",
            "model": "stub-model-2",
        },
    )
    assert mcp_payload["draft"]["draft_strategy"] == "llm_router"
    assert mcp_payload["draft"]["draft_backend"]["provider"] == "stub-provider-2"
    assert mcp_payload["draft"]["draft_backend"]["model"] == "stub-model-2"
    assert observed_calls[0]["provider"] == "stub-provider"
    assert observed_calls[0]["model"] == "stub-model"
    assert observed_calls[1]["provider"] == "stub-provider-2"
    assert observed_calls[1]["model"] == "stub-model-2"


def test_generate_complaint_defaults_llm_backend_to_verified_codex_profile(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "default-llm-profile-sessions")
    service.submit_intake_answers(
        "default-llm-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10.",
            "harm": "Lost wages and emotional distress.",
        },
    )

    observed_kwargs = {}

    def fake_refine(self, state, base_draft, **kwargs):
        observed_kwargs.update(kwargs)
        return {
            **base_draft,
            "draft_strategy": "llm_router",
            "draft_backend": {
                "id": "complaint-draft",
                "provider": kwargs.get("provider"),
                "model": kwargs.get("model"),
                "requested_provider": None,
                "requested_model": None,
            },
        }

    monkeypatch.setattr(ComplaintWorkspaceService, "_refine_draft_with_llm_router", fake_refine)

    payload = service.generate_complaint(
        "default-llm-user",
        requested_relief=["Back pay"],
        use_llm=True,
    )

    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert observed_kwargs["provider"] == "codex_cli"
    assert observed_kwargs["model"] == "gpt-5.3-codex"
    assert observed_kwargs["requested_provider"] is None
    assert observed_kwargs["requested_model"] is None
    assert payload["draft"]["draft_backend"]["provider"] == "codex_cli"
    assert payload["draft"]["draft_backend"]["model"] == "gpt-5.3-codex"


def test_generate_complaint_uses_env_override_for_default_llm_backend(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "env-default-llm-profile-sessions")
    service.submit_intake_answers(
        "env-default-llm-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10.",
            "harm": "Lost wages and emotional distress.",
        },
    )

    observed_kwargs = {}

    def fake_refine(self, state, base_draft, **kwargs):
        observed_kwargs.update(kwargs)
        return {
            **base_draft,
            "draft_strategy": "llm_router",
            "draft_backend": {
                "id": "complaint-draft",
                "provider": kwargs.get("provider"),
                "model": kwargs.get("model"),
            },
        }

    monkeypatch.setattr(ComplaintWorkspaceService, "_refine_draft_with_llm_router", fake_refine)
    monkeypatch.setenv("COMPLAINT_GENERATOR_LLM_DRAFT_PROVIDER", "copilot_cli")
    monkeypatch.setenv("COMPLAINT_GENERATOR_LLM_DRAFT_MODEL_COPILOT_CLI", "gpt-5-mini")

    payload = service.generate_complaint(
        "env-default-llm-user",
        requested_relief=["Back pay"],
        use_llm=True,
    )

    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert observed_kwargs["provider"] == "copilot_cli"
    assert observed_kwargs["model"] == "gpt-5-mini"
    assert observed_kwargs["requested_provider"] is None
    assert observed_kwargs["requested_model"] is None


def test_generate_complaint_falls_back_through_verified_provider_chain(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "fallback-chain-sessions")
    service.submit_intake_answers(
        "fallback-chain-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10.",
            "harm": "Lost wages and emotional distress.",
        },
    )

    attempted = []

    def fake_refine(self, state, base_draft, **kwargs):
        attempted.append(str(kwargs.get("provider") or ""))
        if kwargs.get("provider") in {"codex_cli", "copilot_cli"}:
            self._last_draft_refinement_error = f"provider failed: {kwargs.get('provider')}"
            return None
        return {
            **base_draft,
            "draft_strategy": "llm_router",
            "draft_backend": {
                "id": "complaint-draft",
                "provider": kwargs.get("provider"),
                "model": kwargs.get("model"),
            },
        }

    monkeypatch.setattr(ComplaintWorkspaceService, "_refine_draft_with_llm_router", fake_refine)

    payload = service.generate_complaint(
        "fallback-chain-user",
        requested_relief=["Back pay"],
        use_llm=True,
    )

    assert attempted == ["codex_cli", "copilot_cli", "hf_inference_api"]
    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert payload["draft"]["draft_backend"]["provider"] == "hf_inference_api"
    assert payload["draft"]["draft_backend_fallback_chain"] == ["codex_cli", "copilot_cli", "hf_inference_api"]


def test_llm_draft_timeout_falls_back_to_template_with_reason(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-timeout-sessions")
    service.submit_intake_answers(
        "timeout-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10.",
            "harm": "Lost wages and emotional distress.",
        },
    )

    def fake_refine(self, state, base_draft, **kwargs):
        self._last_draft_refinement_error = "llm_router draft refinement timed out after 60s (codex_cli)"
        return None

    monkeypatch.setattr(ComplaintWorkspaceService, "_refine_draft_with_llm_router", fake_refine)

    payload = service.generate_complaint(
        "timeout-user",
        requested_relief=["Back pay"],
        use_llm=True,
        provider="codex_cli",
    )

    assert payload["draft"]["draft_strategy"] == "template"
    assert payload["draft"]["draft_fallback_reason"] == "llm_router draft refinement timed out after 60s (codex_cli)"
    assert "COMPLAINT FOR RETALIATION" in payload["draft"]["body"]

    export_payload = service.export_complaint_packet("timeout-user")
    assert export_payload["packet_summary"]["draft_strategy"] == "template"
    assert export_payload["packet_summary"]["draft_fallback_reason"] == "llm_router draft refinement timed out after 60s (codex_cli)"
    assert export_payload["packet_summary"]["formal_defect_count"] >= 0
    assert export_payload["packet_summary"]["high_severity_issue_count"] >= 0
    assert isinstance(export_payload["packet_summary"]["release_gate"], dict)
    assert "verdict" in export_payload["packet_summary"]["release_gate"]


def test_llm_draft_can_salvage_near_miss_formal_complaint_output(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-salvage-sessions")
    service.submit_intake_answers(
        "llm-salvage-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10.",
            "harm": "Lost wages and emotional distress.",
        },
    )

    class FakeBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "complaint-draft")
            self.provider = kwargs.get("provider", "stub-provider")
            self.model = kwargs.get("model", "stub-model")

        def __call__(self, prompt):
            assert "Match the tone and paragraph style of this example snippet" in prompt
            return json.dumps(
                {
                    "title": "Jordan Example v. Acme Corporation Complaint",
                    "body": (
                        "IN THE UNITED STATES DISTRICT COURT\n\n"
                        "Civil Action No. ________________\n"
                        "COMPLAINT FOR RETALIATION OVERVIEW\n"
                        "JURY TRIAL DEMANDED\n\n"
                        "NATURE OF THE ACTION\n"
                        "1. Plaintiff reported discrimination to HR.\n\n"
                        "JURISDICTION AND VENUE\n"
                        "2. Jurisdiction and venue are proper in this Court.\n\n"
                        "PARTIES\n"
                        "3. Plaintiff Jordan Example was employed by Defendant.\n\n"
                        "FACTUAL ALLEGATIONS\n"
                        "4. Plaintiff engaged in protected activity by reporting discrimination to HR.\n"
                        "5. Defendant terminated Plaintiff two days later.\n\n"
                        "EVIDENTIARY SUPPORT AND NOTICE\n"
                        "6. The current complaint record includes testimony and documents supporting causation.\n\n"
                        "CLAIM FOR RELIEF\n"
                        "COUNT I - WRONG HEADING\n"
                        "7. Defendant retaliated against Plaintiff for protected activity.\n\n"
                        "PRAYER FOR RELIEF\n"
                        "8. Plaintiff seeks back pay and damages.\n\n"
                        "JURY DEMAND\n"
                        "9. Plaintiff demands a jury trial.\n\n"
                        "SIGNATURE BLOCK\n"
                        "Jordan Example\n\n"
                        "APPENDIX A - CASE SYNOPSIS\n"
                        "Workflow summary prepared through the SDK."
                    ),
                    "requested_relief": ["Back pay", "Damages"],
                }
            )

    monkeypatch.setattr(backends, "LLMRouterBackend", FakeBackend)
    monkeypatch.setattr("applications.ui_review._load_backend_kwargs", lambda *args, **kwargs: {})

    payload = service.generate_complaint(
        "llm-salvage-user",
        requested_relief=["Back pay", "Damages"],
        use_llm=True,
        provider="stub-provider",
        model="stub-model",
    )

    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert payload["draft"]["draft_backend"]["provider"] == "stub-provider"
    assert payload["draft"]["draft_backend"]["model"] == "stub-model"
    assert "trimmed_workspace_appendices" in payload["draft"]["draft_normalizations"]
    assert "normalized_count_heading" in payload["draft"]["draft_normalizations"]
    assert "replaced:current complaint record" in payload["draft"]["draft_normalizations"]
    assert "COMPLAINT FOR RETALIATION" in payload["draft"]["body"]
    assert "COUNT I - RETALIATION" in payload["draft"]["body"]
    assert "APPENDIX A - CASE SYNOPSIS" not in payload["draft"]["body"]
    assert "workflow summary" not in payload["draft"]["body"].lower()
    assert "current complaint record" not in payload["draft"]["body"].lower()

    export_payload = service.export_complaint_packet("llm-salvage-user")
    assert export_payload["packet_summary"]["draft_strategy"] == "llm_router"
    assert export_payload["packet_summary"]["draft_normalization_count"] >= 1
    assert "trimmed_workspace_appendices" in export_payload["packet_summary"]["draft_normalizations"]
    assert isinstance(export_payload["packet_summary"]["formal_diagnostics"], dict)


def test_llm_draft_normalizes_claim_specific_headings_for_housing_output(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-housing-normalize-sessions")
    service.submit_intake_answers(
        "llm-housing-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Housing Group",
            "protected_activity": "Requested a reasonable accommodation and reported discriminatory housing treatment",
            "adverse_action": "Was denied a lease renewal and housing assistance",
            "timeline": "Requested accommodation in April and lost the housing opportunity in May.",
            "harm": "Lost stable housing and incurred relocation costs.",
        },
    )
    service.update_claim_type("llm-housing-user", "housing_discrimination")

    class FakeBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "complaint-draft")
            self.provider = kwargs.get("provider", "stub-provider")
            self.model = kwargs.get("model", "stub-model")

        def __call__(self, prompt):
            assert "Preferred complaint heading: COMPLAINT FOR HOUSING DISCRIMINATION" in prompt
            assert "Preferred count heading: COUNT I - HOUSING DISCRIMINATION" in prompt
            return json.dumps(
                {
                    "title": "Jordan Example v. Acme Housing Group Complaint",
                    "body": (
                        "IN THE UNITED STATES DISTRICT COURT\n\n"
                        "Civil Action No. ________________\n"
                        "COMPLAINT FOR RETALIATION OVERVIEW\n"
                        "JURY TRIAL DEMANDED\n\n"
                        "NATURE OF THE ACTION\n"
                        "1. Plaintiff sought equal housing access and a reasonable accommodation.\n\n"
                        "JURISDICTION AND VENUE\n"
                        "2. Jurisdiction and venue are proper in this Court.\n\n"
                        "PARTIES\n"
                        "3. Plaintiff Jordan Example sought to retain housing rights protected by law.\n\n"
                        "FACTUAL ALLEGATIONS\n"
                        "4. Plaintiff requested a reasonable accommodation and reported discriminatory housing treatment.\n"
                        "5. Defendant denied lease renewal and housing assistance soon after that protected activity.\n\n"
                        "EVIDENTIARY SUPPORT AND NOTICE\n"
                        "6. The current complaint record includes notices and correspondence supporting housing interference.\n\n"
                        "CLAIM FOR RELIEF\n"
                        "COUNT I - WRONG HEADING\n"
                        "7. Defendant interfered with Plaintiff's housing rights after protected conduct.\n\n"
                        "PRAYER FOR RELIEF\n"
                        "8. Plaintiff seeks injunctive relief and damages.\n\n"
                        "JURY DEMAND\n"
                        "9. Plaintiff demands a jury trial.\n\n"
                        "SIGNATURE BLOCK\n"
                        "Jordan Example\n\n"
                        "APPENDIX A - CASE SYNOPSIS\n"
                        "Workflow summary prepared through the SDK."
                    ),
                    "requested_relief": ["Injunctive relief", "Damages"],
                }
            )

    monkeypatch.setattr(backends, "LLMRouterBackend", FakeBackend)
    monkeypatch.setattr("applications.ui_review._load_backend_kwargs", lambda *args, **kwargs: {})

    payload = service.generate_complaint(
        "llm-housing-user",
        requested_relief=["Injunctive relief", "Damages"],
        use_llm=True,
        provider="stub-provider",
        model="stub-model",
    )

    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert payload["draft"]["draft_backend"]["provider"] == "stub-provider"
    assert payload["draft"]["draft_backend"]["model"] == "stub-model"
    assert "COMPLAINT FOR HOUSING DISCRIMINATION" in payload["draft"]["body"]
    assert "COUNT I - HOUSING DISCRIMINATION" in payload["draft"]["body"]
    assert "COMPLAINT FOR RETALIATION OVERVIEW" not in payload["draft"]["body"]
    assert "COUNT I - WRONG HEADING" not in payload["draft"]["body"]
    assert "APPENDIX A - CASE SYNOPSIS" not in payload["draft"]["body"]
    assert "workflow summary" not in payload["draft"]["body"].lower()
    assert "current complaint record" not in payload["draft"]["body"].lower()
    assert "present evidentiary record" in payload["draft"]["body"].lower()


def test_llm_draft_can_salvage_plain_text_complaint_with_preamble_and_markdown_headings(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-plain-text-salvage-sessions")
    service.submit_intake_answers(
        "llm-plain-text-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Consumer Systems",
            "protected_activity": "Reported deceptive billing practices and sought a refund",
            "adverse_action": "Was denied a refund and charged additional hidden fees",
            "timeline": "Reported the deceptive charges in June and was denied a refund in July.",
            "harm": "Suffered economic loss and account disruption.",
        },
    )
    service.update_claim_type("llm-plain-text-user", "consumer_protection")

    class FakeBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "complaint-draft")
            self.provider = kwargs.get("provider", "stub-provider")
            self.model = kwargs.get("model", "stub-model")

        def __call__(self, prompt):
            assert "Preferred complaint heading: COMPLAINT FOR CONSUMER PROTECTION" in prompt
            return (
                "Here is the revised complaint in plain text.\n\n"
                "## IN THE UNITED STATES DISTRICT COURT\n\n"
                "Civil Action No. ________________\n"
                "**COMPLAINT FOR RETALIATION OVERVIEW**\n"
                "JURY TRIAL DEMANDED\n\n"
                "## NATURE OF THE ACTION\n"
                "1. Plaintiff challenges deceptive billing and refund practices.\n\n"
                "## JURISDICTION AND VENUE\n"
                "2. Jurisdiction and venue are proper in this Court.\n\n"
                "## PARTIES\n"
                "3. Plaintiff Jordan Example purchased services from Defendant.\n\n"
                "## FACTUAL ALLEGATIONS\n"
                "4. Plaintiff reported deceptive billing practices and sought a refund.\n"
                "5. Defendant denied a refund and imposed additional hidden fees.\n\n"
                "## EVIDENTIARY SUPPORT AND NOTICE\n"
                "6. The current complaint record includes billing notices and account correspondence.\n\n"
                "## CLAIM FOR RELIEF\n"
                "**COUNT I - WRONG HEADING**\n"
                "7. Defendant used deceptive billing practices in connection with a consumer transaction.\n\n"
                "## PRAYER FOR RELIEF\n"
                "8. Plaintiff seeks restitution and damages.\n\n"
                "## JURY DEMAND\n"
                "9. Plaintiff demands a jury trial.\n\n"
                "## SIGNATURE BLOCK\n"
                "Jordan Example\n"
            )

    monkeypatch.setattr(backends, "LLMRouterBackend", FakeBackend)
    monkeypatch.setattr("applications.ui_review._load_backend_kwargs", lambda *args, **kwargs: {})

    payload = service.generate_complaint(
        "llm-plain-text-user",
        requested_relief=["Restitution", "Damages"],
        use_llm=True,
        provider="stub-provider",
        model="stub-model",
    )

    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert "trimmed_leading_preamble" in payload["draft"]["draft_normalizations"]
    assert "removed_markdown_heading_markup" in payload["draft"]["draft_normalizations"]
    assert "normalized_complaint_heading" in payload["draft"]["draft_normalizations"]
    assert "normalized_count_heading" in payload["draft"]["draft_normalizations"]
    assert "replaced:current complaint record" in payload["draft"]["draft_normalizations"]
    assert payload["draft"]["body"].startswith("IN THE UNITED STATES DISTRICT COURT")
    assert "COMPLAINT FOR CONSUMER PROTECTION" in payload["draft"]["body"]
    assert "COUNT I - CONSUMER PROTECTION" in payload["draft"]["body"]
    assert "Here is the revised complaint" not in payload["draft"]["body"]
    assert "## NATURE OF THE ACTION" not in payload["draft"]["body"]
    assert "**COUNT I - WRONG HEADING**" not in payload["draft"]["body"]
    assert "present evidentiary record" in payload["draft"]["body"].lower()


def test_llm_draft_can_parse_json_wrapped_in_explanatory_text(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-json-wrapper-sessions")
    service.submit_intake_answers(
        "llm-json-wrapper-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Consumer Systems",
            "protected_activity": "Reported deceptive billing practices and sought a refund",
            "adverse_action": "Was denied a refund and charged additional hidden fees",
            "timeline": "Reported the deceptive charges in June and was denied a refund in July.",
            "harm": "Suffered economic loss and account disruption.",
        },
    )
    service.update_claim_type("llm-json-wrapper-user", "consumer_protection")

    class FakeBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "complaint-draft")
            self.provider = kwargs.get("provider", "stub-provider")
            self.model = kwargs.get("model", "stub-model")

        def __call__(self, prompt):
            assert "Return strict JSON" in prompt
            return (
                "I revised the complaint below as requested.\n\n"
                "{\n"
                '  "title": "Jordan Example v. Acme Consumer Systems Complaint",\n'
                '  "body": "IN THE UNITED STATES DISTRICT COURT\\n\\nCivil Action No. ________________\\nCOMPLAINT FOR RETALIATION OVERVIEW\\nJURY TRIAL DEMANDED\\n\\nNATURE OF THE ACTION\\n1. Plaintiff challenges deceptive billing and refund practices.\\n\\nJURISDICTION AND VENUE\\n2. Jurisdiction and venue are proper in this Court.\\n\\nPARTIES\\n3. Plaintiff Jordan Example purchased services from Defendant.\\n\\nFACTUAL ALLEGATIONS\\n4. Plaintiff reported deceptive billing practices and sought a refund.\\n5. Defendant denied a refund and imposed additional hidden fees.\\n\\nEVIDENTIARY SUPPORT AND NOTICE\\n6. The current complaint record includes billing notices and account correspondence.\\n\\nCLAIM FOR RELIEF\\nCOUNT I - WRONG HEADING\\n7. Defendant used deceptive billing practices in connection with a consumer transaction.\\n\\nPRAYER FOR RELIEF\\n8. Plaintiff seeks restitution and damages.\\n\\nJURY DEMAND\\n9. Plaintiff demands a jury trial.\\n\\nSIGNATURE BLOCK\\nJordan Example",\n'
                '  "requested_relief": ["Restitution", "Damages"]\n'
                "}\n\n"
                "Thanks."
            )

    monkeypatch.setattr(backends, "LLMRouterBackend", FakeBackend)
    monkeypatch.setattr("applications.ui_review._load_backend_kwargs", lambda *args, **kwargs: {})

    payload = service.generate_complaint(
        "llm-json-wrapper-user",
        requested_relief=["Restitution", "Damages"],
        use_llm=True,
        provider="stub-provider",
        model="stub-model",
    )

    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert payload["draft"]["draft_backend"]["provider"] == "stub-provider"
    assert "COMPLAINT FOR CONSUMER PROTECTION" in payload["draft"]["body"]
    assert "COUNT I - CONSUMER PROTECTION" in payload["draft"]["body"]
    assert "RETALIATION OVERVIEW" not in payload["draft"]["body"]
    assert "current complaint record" not in payload["draft"]["body"].lower()
    assert payload["draft"]["requested_relief"] == ["Restitution", "Damages"]


def test_llm_draft_normalizes_parenthetical_numbered_paragraphs(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-numbered-paragraph-sessions")
    service.submit_intake_answers(
        "llm-numbered-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10.",
            "harm": "Lost wages and emotional distress.",
        },
    )

    class FakeBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "complaint-draft")
            self.provider = kwargs.get("provider", "stub-provider")
            self.model = kwargs.get("model", "stub-model")

        def __call__(self, prompt):
            assert "Number the factual allegations as pleading paragraphs" in prompt
            return json.dumps(
                {
                    "title": "Jordan Example v. Acme Corporation Complaint",
                    "body": (
                        "IN THE UNITED STATES DISTRICT COURT\n\n"
                        "Civil Action No. ________________\n"
                        "COMPLAINT FOR RETALIATION\n"
                        "JURY TRIAL DEMANDED\n\n"
                        "NATURE OF THE ACTION\n"
                        "1) Plaintiff reported discrimination to HR.\n\n"
                        "JURISDICTION AND VENUE\n"
                        "2) Jurisdiction and venue are proper in this Court.\n\n"
                        "PARTIES\n"
                        "3) Plaintiff Jordan Example was employed by Defendant.\n\n"
                        "FACTUAL ALLEGATIONS\n"
                        "4) Plaintiff engaged in protected activity by reporting discrimination to HR.\n"
                        "5) Defendant terminated Plaintiff two days later.\n\n"
                        "EVIDENTIARY SUPPORT AND NOTICE\n"
                        "6) The current complaint record includes testimony and documents supporting causation.\n\n"
                        "CLAIM FOR RELIEF\n"
                        "COUNT I - RETALIATION\n"
                        "7) Defendant retaliated against Plaintiff for protected activity.\n\n"
                        "PRAYER FOR RELIEF\n"
                        "8) Plaintiff seeks back pay and damages.\n\n"
                        "JURY DEMAND\n"
                        "9) Plaintiff demands a jury trial.\n\n"
                        "SIGNATURE BLOCK\n"
                        "Jordan Example\n"
                    ),
                    "requested_relief": ["Back pay", "Damages"],
                }
            )

    monkeypatch.setattr(backends, "LLMRouterBackend", FakeBackend)
    monkeypatch.setattr("applications.ui_review._load_backend_kwargs", lambda *args, **kwargs: {})

    payload = service.generate_complaint(
        "llm-numbered-user",
        requested_relief=["Back pay", "Damages"],
        use_llm=True,
        provider="stub-provider",
        model="stub-model",
    )

    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert "normalized_numbered_paragraphs" in payload["draft"]["draft_normalizations"]
    assert "1) Plaintiff reported discrimination to HR." not in payload["draft"]["body"]
    assert "1. Plaintiff reported discrimination to HR." in payload["draft"]["body"]
    assert "6. The present evidentiary record includes testimony and documents supporting causation." in payload["draft"]["body"]


def test_llm_draft_injects_missing_preferred_complaint_heading_when_body_is_otherwise_formal(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-heading-injection-sessions")
    service.submit_intake_answers(
        "llm-heading-injection-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10.",
            "harm": "Lost wages and emotional distress.",
        },
    )

    class FakeBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "complaint-draft")
            self.provider = kwargs.get("provider", "stub-provider")
            self.model = kwargs.get("model", "stub-model")
            self.last_result_metadata = {
                "effective_provider_name": self.provider,
                "effective_model_name": self.model,
            }

        def __call__(self, prompt):
            assert "Preferred complaint heading: COMPLAINT FOR RETALIATION" in prompt
            return json.dumps(
                {
                    "title": "Jordan Example v. Acme Corporation Complaint",
                    "body": (
                        "IN THE UNITED STATES DISTRICT COURT\n"
                        "FOR THE NORTHERN DISTRICT OF CALIFORNIA\n\n"
                        "Jordan Example, Plaintiff,\n\n"
                        "v.\n\n"
                        "Acme Corporation, Defendant.\n\n"
                        "Civil Action No. ________________\n\n"
                        "JURY TRIAL DEMANDED\n\n"
                        "NATURE OF THE ACTION\n"
                        "1. Plaintiff brings this retaliation complaint against Defendant.\n\n"
                        "JURISDICTION AND VENUE\n"
                        "2. Jurisdiction and venue are proper.\n\n"
                        "PARTIES\n"
                        "3. The parties are identified above.\n\n"
                        "FACTUAL ALLEGATIONS\n"
                        "4. Plaintiff reported discrimination to HR and was terminated two days later.\n\n"
                        "EVIDENTIARY SUPPORT AND NOTICE\n"
                        "5. Plaintiff may rely on documentary exhibit testimony and personnel records.\n\n"
                        "CLAIM FOR RELIEF\n"
                        "COUNT I - RETALIATION\n"
                        "6. Defendant retaliated against Plaintiff for protected activity.\n\n"
                        "PRAYER FOR RELIEF\n"
                        "WHEREFORE, Plaintiff requests judgment.\n\n"
                        "JURY DEMAND\n"
                        "Plaintiff demands a jury trial.\n\n"
                        "SIGNATURE BLOCK\n"
                        "Jordan Example\n"
                    ),
                    "requested_relief": ["Back pay"],
                }
            )

    monkeypatch.setattr(backends, "LLMRouterBackend", FakeBackend)
    monkeypatch.setattr("applications.ui_review._load_backend_kwargs", lambda *args, **kwargs: {})

    payload = service.generate_complaint(
        "llm-heading-injection-user",
        requested_relief=["Back pay"],
        use_llm=True,
        provider="stub-provider",
        model="stub-model",
    )

    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert payload["draft"]["draft_backend"]["provider"] == "stub-provider"
    assert "COMPLAINT FOR RETALIATION" in payload["draft"]["body"]
    assert "injected_missing_complaint_heading" in payload["draft"]["draft_normalizations"]


def test_llm_draft_normalizes_section_heading_colons_and_count_one(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-heading-punctuation-sessions")
    service.submit_intake_answers(
        "llm-heading-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Housing Group",
            "protected_activity": "Requested a reasonable accommodation and reported discriminatory housing treatment",
            "adverse_action": "Was denied a lease renewal and housing assistance",
            "timeline": "Requested accommodation in April and lost the housing opportunity in May.",
            "harm": "Lost stable housing and incurred relocation costs.",
        },
    )
    service.update_claim_type("llm-heading-user", "housing_discrimination")

    class FakeBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "complaint-draft")
            self.provider = kwargs.get("provider", "stub-provider")
            self.model = kwargs.get("model", "stub-model")

        def __call__(self, prompt):
            assert "Preferred count heading: COUNT I - HOUSING DISCRIMINATION" in prompt
            return json.dumps(
                {
                    "title": "Jordan Example v. Acme Housing Group Complaint",
                    "body": (
                        "IN THE UNITED STATES DISTRICT COURT\n\n"
                        "Civil Action No. ________________\n"
                        "COMPLAINT FOR HOUSING DISCRIMINATION\n"
                        "JURY TRIAL DEMANDED\n\n"
                        "NATURE OF THE ACTION:\n"
                        "1. Plaintiff sought equal housing access and a reasonable accommodation.\n\n"
                        "JURISDICTION AND VENUE:\n"
                        "2. Jurisdiction and venue are proper in this Court.\n\n"
                        "PARTIES:\n"
                        "3. Plaintiff Jordan Example sought to retain housing rights protected by law.\n\n"
                        "FACTUAL ALLEGATIONS:\n"
                        "4. Plaintiff requested a reasonable accommodation and reported discriminatory housing treatment.\n"
                        "5. Defendant denied lease renewal and housing assistance soon after that protected activity.\n\n"
                        "EVIDENTIARY SUPPORT AND NOTICE:\n"
                        "6. The current complaint record includes notices and correspondence supporting housing interference.\n\n"
                        "CLAIM FOR RELIEF:\n"
                        "Count One - Wrong Heading\n"
                        "7. Defendant interfered with Plaintiff's housing rights after protected conduct.\n\n"
                        "PRAYER FOR RELIEF:\n"
                        "8. Plaintiff seeks injunctive relief and damages.\n\n"
                        "JURY DEMAND:\n"
                        "9. Plaintiff demands a jury trial.\n\n"
                        "SIGNATURE BLOCK:\n"
                        "Jordan Example\n"
                    ),
                    "requested_relief": ["Injunctive relief", "Damages"],
                }
            )

    monkeypatch.setattr(backends, "LLMRouterBackend", FakeBackend)
    monkeypatch.setattr("applications.ui_review._load_backend_kwargs", lambda *args, **kwargs: {})

    payload = service.generate_complaint(
        "llm-heading-user",
        requested_relief=["Injunctive relief", "Damages"],
        use_llm=True,
        provider="stub-provider",
        model="stub-model",
    )

    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert "normalized_section_heading_punctuation" in payload["draft"]["draft_normalizations"]
    assert "normalized_count_heading" in payload["draft"]["draft_normalizations"]
    assert "NATURE OF THE ACTION:" not in payload["draft"]["body"]
    assert "Count One - Wrong Heading" not in payload["draft"]["body"]
    assert "NATURE OF THE ACTION\n" in payload["draft"]["body"]
    assert "COUNT I - HOUSING DISCRIMINATION" in payload["draft"]["body"]


def test_llm_draft_normalizes_count_numeric_and_roman_colon_variants(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-count-variant-sessions")
    service.submit_intake_answers(
        "llm-count-variant-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Consumer Systems",
            "protected_activity": "Reported deceptive billing practices and sought a refund",
            "adverse_action": "Was denied a refund and charged additional hidden fees",
            "timeline": "Reported the deceptive charges in June and was denied a refund in July.",
            "harm": "Suffered economic loss and account disruption.",
        },
    )
    service.update_claim_type("llm-count-variant-user", "consumer_protection")

    class FakeBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "complaint-draft")
            self.provider = kwargs.get("provider", "stub-provider")
            self.model = kwargs.get("model", "stub-model")

        def __call__(self, prompt):
            assert "Preferred count heading: COUNT I - CONSUMER PROTECTION" in prompt
            return json.dumps(
                {
                    "title": "Jordan Example v. Acme Consumer Systems Complaint",
                    "body": (
                        "IN THE UNITED STATES DISTRICT COURT\n\n"
                        "Civil Action No. ________________\n"
                        "COMPLAINT FOR CONSUMER PROTECTION\n"
                        "JURY TRIAL DEMANDED\n\n"
                        "NATURE OF THE ACTION\n"
                        "1. Plaintiff challenges deceptive billing and refund practices.\n\n"
                        "JURISDICTION AND VENUE\n"
                        "2. Jurisdiction and venue are proper in this Court.\n\n"
                        "PARTIES\n"
                        "3. Plaintiff Jordan Example purchased services from Defendant.\n\n"
                        "FACTUAL ALLEGATIONS\n"
                        "4. Plaintiff reported deceptive billing practices and sought a refund.\n"
                        "5. Defendant denied a refund and imposed additional hidden fees.\n\n"
                        "EVIDENTIARY SUPPORT AND NOTICE\n"
                        "6. The current complaint record includes billing notices and account correspondence.\n\n"
                        "CLAIM FOR RELIEF\n"
                        "COUNT 1: Wrong Heading\n"
                        "7. Defendant used deceptive billing practices in connection with a consumer transaction.\n\n"
                        "PRAYER FOR RELIEF\n"
                        "8. Plaintiff seeks restitution and damages.\n\n"
                        "JURY DEMAND\n"
                        "9. Plaintiff demands a jury trial.\n\n"
                        "SIGNATURE BLOCK\n"
                        "Jordan Example\n"
                    ),
                    "requested_relief": ["Restitution", "Damages"],
                }
            )

    monkeypatch.setattr(backends, "LLMRouterBackend", FakeBackend)
    monkeypatch.setattr("applications.ui_review._load_backend_kwargs", lambda *args, **kwargs: {})

    payload = service.generate_complaint(
        "llm-count-variant-user",
        requested_relief=["Restitution", "Damages"],
        use_llm=True,
        provider="stub-provider",
        model="stub-model",
    )

    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert "normalized_count_heading" in payload["draft"]["draft_normalizations"]
    assert "COUNT 1: Wrong Heading" not in payload["draft"]["body"]
    assert "COUNT I - CONSUMER PROTECTION" in payload["draft"]["body"]


def test_llm_draft_normalizes_title_case_pleading_headings(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-title-case-heading-sessions")
    service.submit_intake_answers(
        "llm-title-case-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Consumer Systems",
            "protected_activity": "Reported deceptive billing practices and sought a refund",
            "adverse_action": "Was denied a refund and charged additional hidden fees",
            "timeline": "Reported the deceptive charges in June and was denied a refund in July.",
            "harm": "Suffered economic loss and account disruption.",
        },
    )
    service.update_claim_type("llm-title-case-user", "consumer_protection")

    class FakeBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "complaint-draft")
            self.provider = kwargs.get("provider", "stub-provider")
            self.model = kwargs.get("model", "stub-model")

        def __call__(self, prompt):
            assert "Preferred complaint heading: COMPLAINT FOR CONSUMER PROTECTION" in prompt
            return json.dumps(
                {
                    "title": "Jordan Example v. Acme Consumer Systems Complaint",
                    "body": (
                        "IN THE UNITED STATES DISTRICT COURT\n\n"
                        "Civil Action No. ________________\n"
                        "Complaint for Consumer Protection\n"
                        "JURY TRIAL DEMANDED\n\n"
                        "Nature of the Action\n"
                        "1. Plaintiff challenges deceptive billing and refund practices.\n\n"
                        "Jurisdiction and Venue\n"
                        "2. Jurisdiction and venue are proper in this Court.\n\n"
                        "Parties\n"
                        "3. Plaintiff Jordan Example purchased services from Defendant.\n\n"
                        "Factual Allegations\n"
                        "4. Plaintiff reported deceptive billing practices and sought a refund.\n"
                        "5. Defendant denied a refund and imposed additional hidden fees.\n\n"
                        "Evidentiary Support and Notice\n"
                        "6. The current complaint record includes billing notices and account correspondence.\n\n"
                        "Claim for Relief\n"
                        "Count I - Wrong Heading\n"
                        "7. Defendant used deceptive billing practices in connection with a consumer transaction.\n\n"
                        "Prayer for Relief\n"
                        "8. Plaintiff seeks restitution and damages.\n\n"
                        "Jury Demand\n"
                        "9. Plaintiff demands a jury trial.\n\n"
                        "Signature Block\n"
                        "Jordan Example\n"
                    ),
                    "requested_relief": ["Restitution", "Damages"],
                }
            )

    monkeypatch.setattr(backends, "LLMRouterBackend", FakeBackend)
    monkeypatch.setattr("applications.ui_review._load_backend_kwargs", lambda *args, **kwargs: {})

    payload = service.generate_complaint(
        "llm-title-case-user",
        requested_relief=["Restitution", "Damages"],
        use_llm=True,
        provider="stub-provider",
        model="stub-model",
    )

    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert "normalized_section_heading_punctuation" in payload["draft"]["draft_normalizations"]
    assert "normalized_complaint_heading" in payload["draft"]["draft_normalizations"]
    assert "normalized_count_heading" in payload["draft"]["draft_normalizations"]
    assert "Complaint for Consumer Protection" not in payload["draft"]["body"]
    assert "Nature of the Action" not in payload["draft"]["body"]
    assert "Count I - Wrong Heading" not in payload["draft"]["body"]
    assert "COMPLAINT FOR CONSUMER PROTECTION" in payload["draft"]["body"]
    assert "NATURE OF THE ACTION" in payload["draft"]["body"]
    assert "COUNT I - CONSUMER PROTECTION" in payload["draft"]["body"]


def test_llm_draft_normalizes_title_case_court_caption_and_civil_action_heading(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "llm-court-caption-sessions")
    service.submit_intake_answers(
        "llm-court-caption-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10.",
            "harm": "Lost wages and emotional distress.",
        },
    )

    class FakeBackend:
        def __init__(self, **kwargs):
            self.id = kwargs.get("id", "complaint-draft")
            self.provider = kwargs.get("provider", "stub-provider")
            self.model = kwargs.get("model", "stub-model")

        def __call__(self, prompt):
            assert "Return strict JSON" in prompt
            return json.dumps(
                {
                    "title": "Jordan Example v. Acme Corporation Complaint",
                    "body": (
                        "Please use the revised complaint below.\n\n"
                        "In the United States District Court\n\n"
                        "Civil Action No.: ________________\n"
                        "Complaint for Retaliation\n"
                        "JURY TRIAL DEMANDED\n\n"
                        "Nature of the Action\n"
                        "1. Plaintiff reported discrimination to HR.\n\n"
                        "Jurisdiction and Venue\n"
                        "2. Jurisdiction and venue are proper in this Court.\n\n"
                        "Parties\n"
                        "3. Plaintiff Jordan Example was employed by Defendant.\n\n"
                        "Factual Allegations\n"
                        "4. Plaintiff engaged in protected activity by reporting discrimination to HR.\n"
                        "5. Defendant terminated Plaintiff two days later.\n\n"
                        "Evidentiary Support and Notice\n"
                        "6. The current complaint record includes testimony and documents supporting causation.\n\n"
                        "Claim for Relief\n"
                        "Count I - Wrong Heading\n"
                        "7. Defendant retaliated against Plaintiff for protected activity.\n\n"
                        "Prayer for Relief\n"
                        "8. Plaintiff seeks back pay and damages.\n\n"
                        "Jury Demand\n"
                        "9. Plaintiff demands a jury trial.\n\n"
                        "Signature Block\n"
                        "Jordan Example\n"
                    ),
                    "requested_relief": ["Back pay", "Damages"],
                }
            )

    monkeypatch.setattr(backends, "LLMRouterBackend", FakeBackend)
    monkeypatch.setattr("applications.ui_review._load_backend_kwargs", lambda *args, **kwargs: {})

    payload = service.generate_complaint(
        "llm-court-caption-user",
        requested_relief=["Back pay", "Damages"],
        use_llm=True,
        provider="stub-provider",
        model="stub-model",
    )

    assert payload["draft"]["draft_strategy"] == "llm_router"
    assert "trimmed_leading_preamble" in payload["draft"]["draft_normalizations"]
    assert "normalized_court_caption" in payload["draft"]["draft_normalizations"]
    assert "normalized_civil_action_heading" in payload["draft"]["draft_normalizations"]
    assert "normalized_complaint_heading" in payload["draft"]["draft_normalizations"]
    assert payload["draft"]["body"].startswith("IN THE UNITED STATES DISTRICT COURT")
    assert "Civil Action No.: ________________" not in payload["draft"]["body"]
    assert "Civil Action No. ________________" in payload["draft"]["body"]
    assert "COMPLAINT FOR RETALIATION" in payload["draft"]["body"]


def test_template_draft_deduplicates_repeated_evidence_references(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "dedupe-evidence-sessions")
    service.submit_intake_answers(
        "dedupe-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR and requested corrective action",
            "adverse_action": "Was sidelined, threatened with termination, and then terminated",
            "timeline": "Reported discrimination on March 8, was threatened on March 9, and terminated on March 10",
            "harm": "Lost wages, benefits, professional standing, and suffered emotional distress",
        },
    )
    for _ in range(3):
        service.save_evidence(
            "dedupe-user",
            kind="document",
            claim_element_id="causation",
            title="Termination email",
            content="The termination email followed within two days of the HR complaint.",
            source="Inbox export",
        )

    payload = service.generate_complaint(
        "dedupe-user",
        requested_relief=["Back pay", "Compensatory damages", "Injunctive relief"],
    )
    body = payload["draft"]["body"]

    assert body.count("Termination email (Causal link)") == 1
    assert body.count("Plaintiff identifies documentary exhibit 'Termination email' as presently supporting the causal link element.") == 1
    assert "16. Plaintiff identifies documentary exhibit 'Termination email' as presently supporting the causal link element." in body
    assert "17. Jordan Example repeats and realleges" in body
    assert "including reporting discrimination to HR and requesting corrective action" in body

    export_payload = service.export_complaint_packet("dedupe-user")
    diagnostics = export_payload["packet_summary"]["formal_diagnostics"]
    assert diagnostics["formal_defect_count"] >= 0
    assert diagnostics["release_gate_verdict"] in {"pass", "warning", "blocked"}


def test_formal_complaint_prompt_includes_claim_specific_pleading_requirements(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "prompt-sessions")
    service.submit_intake_answers(
        "prompt-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Housing Group",
            "protected_activity": "Requested a reasonable accommodation and reported discriminatory housing treatment",
            "adverse_action": "Was denied a lease renewal and housing assistance",
            "timeline": "Requested accommodation in April and lost the housing opportunity in May.",
            "harm": "Lost stable housing and incurred relocation costs.",
        },
    )
    service.update_claim_type("prompt-user", "housing_discrimination")
    state = service._load_state("prompt-user")
    base_draft = service._build_draft(state, use_llm=False)

    prompt = service._build_formal_complaint_generation_prompt(state, base_draft)

    assert "Preferred complaint heading: COMPLAINT FOR HOUSING DISCRIMINATION" in prompt
    assert "Preferred count heading: COUNT I - HOUSING DISCRIMINATION" in prompt
    assert "Number the factual allegations as pleading paragraphs like '1. ...', '2. ...'" in prompt
    assert "Do not write a memo, case summary, product explanation, workflow note, JSON explanation, SDK explanation, or support-matrix summary." in prompt
    assert "The complaint must expressly allege all of the following:" in prompt
    assert "Match the tone and paragraph style of this example snippet for the selected claim type:" in prompt
    assert "7. Plaintiff sought to rent, retain, or enjoy housing on equal terms protected by law." in prompt
    assert "Allege the housing-related denial, interference, limitation, or retaliation with specificity." in prompt
    assert "Allege the property, housing benefit, tenancy, or housing opportunity context clearly enough to read like a real housing pleading." in prompt
    assert "Return strict JSON with this shape:" in prompt


def test_complaint_output_analysis_flags_claim_type_mismatch(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "claim-mismatch-sessions")
    service.submit_intake_answers(
        "mismatch-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Housing Group",
            "protected_activity": "Requested a reasonable accommodation and reported discriminatory housing treatment",
            "adverse_action": "Was denied a lease renewal and housing assistance",
            "timeline": "Requested accommodation in April and lost the housing opportunity in May.",
            "harm": "Lost stable housing and incurred relocation costs.",
        },
    )
    service.update_claim_type("mismatch-user", "housing_discrimination")
    service.update_draft(
        "mismatch-user",
        title="Mismatched complaint",
        body=(
            "IN THE UNITED STATES DISTRICT COURT\n\n"
            "Civil Action No. ________________\n"
            "COMPLAINT FOR RETALIATION\n\n"
            "JURISDICTION AND VENUE\n"
            "FACTUAL ALLEGATIONS\n"
            "EVIDENTIARY SUPPORT AND NOTICE\n"
            "COUNT I - RETALIATION\n"
            "PRAYER FOR RELIEF\n"
            "JURY DEMAND\n"
            "SIGNATURE BLOCK\n"
        ),
        requested_relief=["Injunctive relief"],
    )

    payload = service.analyze_complaint_output("mismatch-user")

    assert payload["ui_feedback"]["claim_type_alignment"]["complaint_heading_matches"] is False
    assert payload["ui_feedback"]["claim_type_alignment"]["count_heading_matches"] is False
    assert payload["ui_feedback"]["claim_type_alignment_score"] == 0
    assert any(
        "selected claim type" in issue["finding"]
        for issue in payload["ui_feedback"]["issues"]
    )
    assert any(
        suggestion["title"] == "Keep the selected claim theory visible through drafting"
        for suggestion in payload["ui_feedback"]["ui_suggestions"]
    )
    assert payload["packet_summary"]["formal_defect_count"] >= 1


def test_complaint_output_analysis_flags_meta_summary_language_and_missing_numbering(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "meta-summary-sessions")
    service.submit_intake_answers(
        "meta-user",
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Was terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10.",
            "harm": "Lost wages and emotional distress.",
        },
    )
    service.update_draft(
        "meta-user",
        title="Meta complaint",
        body=(
            "IN THE UNITED STATES DISTRICT COURT\n\n"
            "Civil Action No. ________________\n"
            "COMPLAINT FOR RETALIATION\n\n"
            "JURISDICTION AND VENUE\n"
            "PARTIES\n"
            "FACTUAL ALLEGATIONS\n"
            "This complaint record is a workflow summary prepared through the SDK.\n"
            "EVIDENTIARY SUPPORT AND NOTICE\n"
            "CLAIM FOR RELIEF\n"
            "COUNT I - RETALIATION\n"
            "PRAYER FOR RELIEF\n"
            "JURY DEMAND\n"
            "SIGNATURE BLOCK\n"
        ),
        requested_relief=["Back pay"],
    )

    payload = service.analyze_complaint_output("meta-user")
    findings = [issue["finding"] for issue in payload["ui_feedback"]["issues"]]
    suggestion_titles = [item["title"] for item in payload["ui_feedback"]["ui_suggestions"]]

    assert any("missing numbered pleading paragraphs" in finding.lower() for finding in findings)
    assert any("internal product or workflow language" in finding.lower() for finding in findings)
    assert "Keep numbered complaint paragraphs visible in the draft" in suggestion_titles
    assert "Strip workflow language out of the complaint draft" in suggestion_titles
    assert payload["packet_summary"]["formal_defect_count"] >= 2


def test_deterministic_retaliation_draft_normalizes_activity_into_pleading_style(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "pleading-style-sessions")
    service.submit_intake_answers(
        "pleading-style-user",
        {
            "party_name": "Taylor Smith",
            "opposing_party": "Acme Logistics",
            "protected_activity": "Reported wage-and-hour violations to HR",
            "adverse_action": "Was terminated three days later",
            "timeline": "Report on April 2, termination on April 5",
            "harm": "Lost wages, benefits, and housing stability",
            "court_header": "FOR THE NORTHERN DISTRICT OF CALIFORNIA",
        },
    )
    service.save_evidence(
        "pleading-style-user",
        kind="document",
        claim_element_id="causation",
        title="Termination timeline email",
        content="Email records show the termination followed immediately after the HR report.",
    )

    payload = service.generate_complaint("pleading-style-user")
    body = payload["draft"]["body"]

    assert "FOR THE NORTHERN DISTRICT OF CALIFORNIA" in body
    assert "engaged in protected activity by reporting wage-and-hour violations to HR." in body
    assert "Plaintiff engaged in protected activity by reporting wage-and-hour violations to HR," in body
    assert "Within days of that protected activity, Defendant took materially adverse action against Plaintiff by terminating Plaintiff three days later." in body
    assert "The relevant chronology is as follows: Plaintiff made the report on April 2, and the termination occurred on April 5." in body
    assert "Plaintiff presently identifies the following documents, exhibits, or records in support of this pleading:" in body
    assert "documentary exhibit presently identified as 'Termination timeline email' on the causal link element." in body
    assert "Plaintiff expects to offer documentary exhibit 'Termination timeline email' in support of the causal link element." in body
    assert "the evidentiary basis for this pleading" in body
    assert "As a direct and proximate result of Defendant's retaliatory conduct, Plaintiff is entitled to recover damages, equitable relief, fees and costs where available, and such further relief as the Court deems just and proper." in body
    assert "Back pay and lost benefits." in body


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
        "--user-id",
        "cli-user",
        "--artifact-path",
        str(tmp_path / "review.json"),
    )
    assert cli_payload["review"]["summary"] == "Review completed."
    cached_cli_ui_payload = _invoke_cli(runner, "ui-readiness", "--user-id", "cli-user")
    assert cached_cli_ui_payload["status"] == "cached"

    mcp_payload = _call_mcp_tool(
        service,
        11,
        "complaint.review_ui",
        {"screenshot_dir": str(tmp_path), "user_id": "mcp-user"},
    )
    assert mcp_payload["review"]["summary"] == "Review completed."
    cached_mcp_ui_payload = _call_mcp_tool(service, 12, "complaint.get_ui_readiness", {"user_id": "mcp-user"})
    assert cached_mcp_ui_payload["status"] == "cached"


def test_review_ui_tool_supports_iterative_workflow_through_mcp(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "ui-review-sessions")
    service.update_case_synopsis(
        "iter-user",
        "Jordan Example alleges retaliation after protected complaints about safety and scheduling.",
    )
    service.generate_complaint("iter-user", requested_relief=["Back pay"])
    service._persist_ui_readiness(
        "iter-user",
        {
            "workflow_type": "iterative_actor_critic_review",
            "backend": {"strategy": "multimodal_router", "provider": "codex_cli", "model": "gpt-5.3-codex"},
            "review": {
                "summary": "Cached review says the draft stage still hides exports.",
                "critic_review": {"verdict": "warning", "acceptance_checks": ["Keep export controls visible."]},
                "complaint_journey": {"tested_stages": ["draft", "export"]},
            },
            "screenshot_findings": [
                {
                    "stage": "draft",
                    "surface": "workspace-draft",
                    "summary": "The export CTA drops below dense metadata.",
                    "criticisms": [{"problem": "Actors miss the next step after draft generation."}],
                }
            ],
            "optimization_targets": [
                {"title": "Pin export controls beside the complaint preview", "reason": "The actor should not hunt for the next action."}
            ],
            "playwright_followups": ["Verify exports remain visible after testimony updates."],
            "recommended_changes": ["Keep the export lane sticky within the draft panel."],
        },
    )

    def fake_iterative(**kwargs):
        assert kwargs["iterations"] == 2
        assert str(kwargs["screenshot_dir"]) == str(tmp_path)
        assert kwargs["goals"] == ["reduce intake friction", "keep evidence and draft connected"]
        assert kwargs["supplemental_artifacts"][0]["artifact_type"] == "complaint_export"
        assert "Tighten review-to-draft gatekeeping" in kwargs["supplemental_artifacts"][0]["ui_suggestions_excerpt"]
        assert kwargs["supplemental_artifacts"][1]["artifact_type"] == "ui_readiness_review"
        assert "Screenshot findings:" in kwargs["supplemental_artifacts"][1]["review_excerpt"]
        assert kwargs["supplemental_artifacts"][1]["screenshot_findings"][0]["surface"] == "workspace-draft"
        return {
            "iterations": 2,
            "screenshot_dir": str(tmp_path),
            "output_dir": str(tmp_path / "reviews"),
            "review": {
                "summary": "Audit found broken stage transitions around draft handoff.",
                "critic_review": {"verdict": "warning", "acceptance_checks": ["Keep every export action reachable from the draft review stage."]},
                "complaint_journey": {
                    "tested_stages": ["intake", "evidence", "review", "draft", "export"],
                    "sdk_tool_invocations": ["generateComplaint", "exportComplaintPdf"],
                },
            },
            "issues": [
                {
                    "severity": "high",
                    "stage": "draft",
                    "summary": "Primary export button becomes inert after review refresh.",
                }
            ],
            "recommended_changes": [
                "Keep the primary export action anchored beside the complaint draft preview."
            ],
            "playwright_followups": [
                "Assert the export control stays enabled after evidence edits."
            ],
            "stage_findings": {
                "draft": ["Export path looks disconnected from the complaint preview after a refresh."]
            },
            "screenshot_findings": [
                {
                    "artifact_path": str(tmp_path / "workspace-draft.png"),
                    "stage": "draft",
                    "surface": "workspace-draft",
                    "summary": "The draft page hides the export affordance below the fold.",
                    "criticisms": [
                        "The actor loses the next step after generating the complaint.",
                    ],
                }
            ],
            "optimization_targets": [
                {
                    "stage": "draft",
                    "target": "Keep export buttons visible next to the generated complaint.",
                }
            ],
            "carry_forward_assessment": {
                "prior_review_available": True,
                "unresolved_findings": [{"stage": "draft", "surface": "workspace-draft", "summary": "Export CTA still hidden."}],
                "resolved_findings": [],
                "continued_optimization_targets": [{"title": "Keep export buttons visible next to the generated complaint."}],
                "retired_optimization_targets": [],
                "summary": "1 prior screenshot finding still appears unresolved.",
            },
            "latest_review_markdown_path": str(tmp_path / "reviews" / "iteration-01-review.md"),
            "latest_review_json_path": str(tmp_path / "reviews" / "iteration-01-review.json"),
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
            "user_id": "iter-user",
            "screenshot_dir": str(tmp_path),
            "iterations": 2,
            "output_path": str(tmp_path / "reviews"),
            "goals": ["reduce intake friction", "keep evidence and draft connected"],
        },
    )

    assert mcp_payload["iterations"] == 2
    assert mcp_payload["runs"][0]["iteration"] == 1
    cached_payload = _call_mcp_tool(service, 13, "complaint.get_ui_readiness", {"user_id": "iter-user"})
    assert cached_payload["status"] == "cached"
    assert cached_payload["screenshot_findings"][0]["surface"] == "workspace-draft"
    assert cached_payload["optimization_targets"][0]["stage"] == "draft"
    assert cached_payload["playwright_followups"] == ["Assert the export control stays enabled after evidence edits."]
    assert cached_payload["carry_forward_assessment"]["unresolved_findings"][0]["surface"] == "workspace-draft"
    assert cached_payload["latest_review_json_path"] == str(tmp_path / "reviews" / "iteration-01-review.json")
    assert cached_payload["runs"][0]["iteration"] == 1


def test_ui_readiness_summary_preserves_screenshot_driven_optimizer_feedback(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "ui-readiness-summary")

    summarized = service._summarize_ui_readiness_result(
        {
            "workflow_type": "iterative_actor_critic_review",
            "backend": {"strategy": "multimodal_router", "provider": "codex_cli", "model": "gpt-5.3-codex"},
            "latest_review": "The draft stage needs a clearer export handoff.",
            "review": {
                "summary": "The draft stage needs a clearer export handoff.",
                "critic_review": {"verdict": "warning", "acceptance_checks": ["Keep export actions visible."]},
                "complaint_journey": {
                    "tested_stages": ["intake", "evidence", "review", "draft", "export"],
                    "sdk_tool_invocations": ["generateComplaint", "exportComplaintPdf"],
                },
            },
            "issues": [{"severity": "high", "summary": "Export CTA disappears after review."}],
            "recommended_changes": ["Pin export actions in the draft sidebar."],
            "playwright_followups": ["Verify PDF and markdown downloads remain reachable after testimony edits."],
            "stage_findings": {"draft": ["Draft stage loses the export CTA after a refresh."]},
            "screenshot_findings": [
                {
                    "artifact_path": str(tmp_path / "workspace-draft.png"),
                    "stage": "draft",
                    "surface": "workspace-draft",
                    "summary": "Export controls are visually buried beneath dense metadata.",
                    "criticisms": ["Actor cannot confidently continue from the draft stage."],
                }
            ],
            "optimization_targets": [
                {
                    "stage": "draft",
                    "target": "Move export controls adjacent to the complaint preview and mediator handoff panel.",
                }
            ],
            "carry_forward_assessment": {
                "prior_review_available": True,
                "unresolved_findings": [{"stage": "draft", "surface": "workspace-draft", "summary": "Export CTA still hidden."}],
                "resolved_findings": [{"stage": "review", "surface": "workspace-review", "summary": "Support gap cue looks improved."}],
                "continued_optimization_targets": [{"title": "Pin export actions in the draft sidebar."}],
                "retired_optimization_targets": [],
                "summary": "1 prior screenshot finding still appears unresolved. 1 prior screenshot finding looks improved or no longer visible.",
            },
            "latest_review_markdown_path": str(tmp_path / "iteration-01-review.md"),
            "latest_review_json_path": str(tmp_path / "iteration-01-review.json"),
            "runs": [{"iteration": 1, "optimization_target_count": 1}],
        }
    )

    assert summarized["workflow_type"] == "iterative_actor_critic_review"
    assert summarized["review_backend"]["provider"] == "codex_cli"
    assert summarized["issues"][0]["summary"] == "Export CTA disappears after review."
    assert summarized["recommended_changes"] == ["Pin export actions in the draft sidebar."]
    assert summarized["playwright_followups"] == ["Verify PDF and markdown downloads remain reachable after testimony edits."]
    assert summarized["stage_findings"]["draft"] == ["Draft stage loses the export CTA after a refresh."]
    assert summarized["screenshot_findings"][0]["artifact_path"] == str(tmp_path / "workspace-draft.png")
    assert summarized["optimization_targets"][0]["stage"] == "draft"
    assert summarized["carry_forward_assessment"]["resolved_findings"][0]["surface"] == "workspace-review"
    assert summarized["latest_review_markdown_path"] == str(tmp_path / "iteration-01-review.md")
    assert summarized["latest_review_json_path"] == str(tmp_path / "iteration-01-review.json")
    assert summarized["runs"][0]["optimization_target_count"] == 1


def test_optimize_ui_tool_supports_closed_loop_workflow_through_cli_and_mcp(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "ui-optimize-sessions")
    service.update_case_synopsis(
        "mcp-user",
        "Jordan Example alleges retaliation after reporting payroll fraud and safety violations.",
    )
    service.generate_complaint("mcp-user", requested_relief=["Back pay"])
    service._persist_ui_readiness(
        "cli-user",
        {
            "workflow_type": "iterative_actor_critic_review",
            "backend": {"strategy": "multimodal_router", "provider": "codex_cli", "model": "gpt-5.3-codex"},
            "review": {
                "summary": "Cached review says the workspace still needs calmer entry cues.",
                "critic_review": {"verdict": "warning"},
                "complaint_journey": {"tested_stages": ["intake", "draft", "export"]},
            },
            "screenshot_findings": [
                {
                    "stage": "intake",
                    "surface": "workspace-intake",
                    "summary": "The form hierarchy makes the next legal step feel unclear.",
                    "criticisms": [{"problem": "The actor loses confidence before the evidence stage."}],
                }
            ],
            "optimization_targets": [
                {"title": "Reduce intake clutter", "reason": "A calmer entry path should lower abandonment risk."}
            ],
            "playwright_followups": ["Capture the intake hero after the next UI pass."],
        },
    )
    service._persist_ui_readiness(
        "mcp-user",
        {
            "workflow_type": "iterative_actor_critic_review",
            "backend": {"strategy": "multimodal_router", "provider": "codex_cli", "model": "gpt-5.3-codex"},
            "review": {
                "summary": "Cached review says intake-to-draft flow still needs calmer cues.",
                "critic_review": {"verdict": "warning"},
                "complaint_journey": {"tested_stages": ["intake", "draft", "export"]},
            },
            "screenshot_findings": [
                {
                    "stage": "intake",
                    "surface": "workspace-intake",
                    "summary": "The form hierarchy makes the next legal step feel unclear.",
                    "criticisms": [{"problem": "The actor loses confidence before the evidence stage."}],
                }
            ],
            "optimization_targets": [
                {"title": "Reduce intake clutter", "reason": "A calmer entry path should lower abandonment risk."}
            ],
            "playwright_followups": ["Capture the intake hero after the next UI pass."],
        },
    )

    def fake_closed_loop(**kwargs):
        assert kwargs["method"] == "adversarial"
        assert kwargs["priority"] == 91
        assert kwargs["goals"] == ["make intake calmer", "surface every complaint-generator feature"]
        assert kwargs["supplemental_artifacts"][0]["artifact_type"] == "complaint_export"
        assert "Tighten review-to-draft gatekeeping" in kwargs["supplemental_artifacts"][0]["ui_suggestions_excerpt"]
        assert kwargs["supplemental_artifacts"][1]["artifact_type"] == "ui_readiness_review"
        assert kwargs["supplemental_artifacts"][1]["optimization_targets"][0]["title"] == "Reduce intake clutter"
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
        "--user-id",
        "cli-user",
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
    cached_cli_ui_payload = _invoke_cli(runner, "ui-readiness", "--user-id", "cli-user")
    assert cached_cli_ui_payload["status"] == "cached"

    mcp_payload = _call_mcp_tool(
        service,
        13,
        "complaint.optimize_ui",
        {
            "user_id": "mcp-user",
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
    cached_mcp_ui_payload = _call_mcp_tool(service, 14, "complaint.get_ui_readiness", {"user_id": "mcp-user"})
    assert cached_mcp_ui_payload["status"] == "cached"


def test_review_generated_exports_tool_supports_cli_mcp_and_package(monkeypatch, tmp_path):
    runner = CliRunner()
    service = ComplaintWorkspaceService(root_dir=tmp_path / "review-export-sessions")

    def fake_review_generated_exports(self, user_id, **kwargs):
        assert user_id == "artifact-user"
        return {
            "generated_at": "2026-03-23T00:00:00+00:00",
            "artifact_count": 1,
            "aggregate": {
                "average_filing_shape_score": 87,
                "average_claim_type_alignment_score": 91,
                "issue_findings": ["Venue allegations still read generic."],
                "ui_suggestions": [{"title": "Strengthen venue guidance in the draft UI"}],
            },
        }

    monkeypatch.setattr(complaint_cli_impl, "service", service)
    monkeypatch.setattr(ComplaintWorkspaceService, "review_generated_exports", fake_review_generated_exports)

    cli_payload = _invoke_cli(runner, "review-exports", "--user-id", "artifact-user")
    assert cli_payload["artifact_count"] == 1
    assert cli_payload["aggregate"]["average_filing_shape_score"] == 87

    mcp_payload = _call_mcp_tool(
        service,
        41,
        "complaint.review_generated_exports",
        {"user_id": "artifact-user"},
    )
    assert mcp_payload["artifact_count"] == 1
    assert mcp_payload["aggregate"]["average_claim_type_alignment_score"] == 91

    package_payload = review_generated_exports("artifact-user", service=service)
    assert package_payload["artifact_count"] == 1


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
    assert captured["pytest_target"] == "playwright/tests/complaint-flow.spec.js"


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
    assert captured["pytest_target"] == "playwright/tests/complaint-flow.spec.js"

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
    assert captured["pytest_target"] == "playwright/tests/complaint-flow.spec.js"


def test_ui_optimizer_daemon_cli_commands_delegate_to_daemon_module(monkeypatch, tmp_path):
    runner = CliRunner()
    captured = {}

    def fake_start(args):
        captured["start"] = args
        return {"status": "started", "user_id": args.user_id, "artifact_root": args.artifact_root}

    def fake_status(args):
        captured["status"] = args
        return {"status": "ok", "running": True, "artifact_root": args.artifact_root}

    def fake_stop(args):
        captured["stop"] = args
        return {"status": "stopping", "user_id": args.user_id, "artifact_root": args.artifact_root}

    monkeypatch.setattr("complaint_generator.ui_optimizer_daemon._start_daemon", fake_start)
    monkeypatch.setattr("complaint_generator.ui_optimizer_daemon._status_payload", fake_status)
    monkeypatch.setattr("complaint_generator.ui_optimizer_daemon._stop_daemon", fake_stop)

    start_payload = _invoke_cli(
        runner,
        "ui-optimizer-start",
        "--user-id",
        "daemon-user",
        "--artifact-root",
        str(tmp_path / "daemon"),
        "--goals",
        "seed goal one\nseed goal two",
        "--provider",
        "codex_cli",
        "--use-llm-draft",
    )
    status_payload = _invoke_cli(
        runner,
        "ui-optimizer-status",
        "--user-id",
        "daemon-user",
        "--artifact-root",
        str(tmp_path / "daemon"),
    )
    stop_payload = _invoke_cli(
        runner,
        "ui-optimizer-stop",
        "--user-id",
        "daemon-user",
        "--artifact-root",
        str(tmp_path / "daemon"),
    )

    assert start_payload["status"] == "started"
    assert status_payload["running"] is True
    assert stop_payload["status"] == "stopping"
    assert captured["start"].goals == ["seed goal one", "seed goal two"]
    assert captured["start"].provider == "codex_cli"
    assert captured["start"].use_llm_draft is True
    assert captured["status"].artifact_root == str(tmp_path / "daemon")
    assert captured["stop"].artifact_root == str(tmp_path / "daemon")


def test_package_wrappers_delegate_to_matching_ui_review_and_browser_tools(monkeypatch, tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "package-wrapper-sessions")
    captured_calls = []

    def fake_call_mcp_tool(tool_name, arguments=None):
        captured_calls.append((tool_name, dict(arguments or {})))
        return {"tool_name": tool_name, "arguments": dict(arguments or {})}

    monkeypatch.setattr(service, "call_mcp_tool", fake_call_mcp_tool)

    review_payload = review_ui(
        screenshot_dir=tmp_path / "screens",
        user_id="package-user",
        iterations=2,
        goals=["Repair broken buttons", "Keep the full complaint flow connected"],
        service=service,
    )
    optimize_payload = optimize_ui(
        screenshot_dir=tmp_path / "screens",
        user_id="package-user",
        max_rounds=3,
        iterations=2,
        service=service,
    )
    audit_payload = run_browser_audit(
        screenshot_dir=tmp_path / "screens",
        service=service,
    )

    assert review_payload["tool_name"] == "complaint.review_ui"
    assert review_payload["arguments"]["iterations"] == 2
    assert optimize_payload["tool_name"] == "complaint.optimize_ui"
    assert optimize_payload["arguments"]["max_rounds"] == 3
    assert audit_payload["tool_name"] == "complaint.run_browser_audit"
    assert [tool_name for tool_name, _arguments in captured_calls] == [
        "complaint.review_ui",
        "complaint.optimize_ui",
        "complaint.run_browser_audit",
    ]


def test_workspace_download_route_serves_json_markdown_and_pdf_exports(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "download-sessions")
    user_id = "download-user"
    service.submit_intake_answers(
        user_id,
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Threatened termination and then terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10",
            "harm": "Lost wages, benefits, and emotional distress",
        },
    )
    service.save_evidence(
        user_id,
        kind="document",
        claim_element_id="causation",
        title="Termination email",
        content="The termination email followed within two days of the HR complaint.",
        source="Inbox export",
    )
    service.generate_complaint(
        user_id,
        requested_relief=["Back pay", "Compensatory damages"],
        title_override="Jordan Example v. Acme Corporation Complaint",
    )

    app = FastAPI()
    attach_complaint_workspace_routes(app, service)
    from fastapi.testclient import TestClient

    client = TestClient(app)

    json_response = client.get(
        "/api/complaint-workspace/export/download",
        params={"user_id": user_id, "output_format": "json"},
    )
    assert json_response.status_code == 200
    assert json_response.headers["content-type"].startswith("application/json")
    assert 'filename="jordan-example-v.-acme-corporation-complaint.json"' in json_response.headers["content-disposition"]
    json_payload = json_response.json()
    assert json_payload["draft"]["title"] == "Jordan Example v. Acme Corporation Complaint"
    assert "COMPLAINT FOR RETALIATION" in json_payload["draft"]["body"]
    assert "Civil Action No. ________________" in json_payload["draft"]["body"]
    assert "Jordan Example brings this retaliation complaint against Acme Corporation." in json_payload["draft"]["body"]

    markdown_response = client.get(
        "/api/complaint-workspace/export/download",
        params={"user_id": user_id, "output_format": "markdown"},
    )
    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert 'filename="jordan-example-v.-acme-corporation-complaint.md"' in markdown_response.headers["content-disposition"]
    assert markdown_response.text.startswith("IN THE UNITED STATES DISTRICT COURT")
    assert "Jordan Example brings this retaliation complaint against Acme Corporation." in markdown_response.text
    assert "Civil Action No. ________________" in markdown_response.text
    assert "EVIDENTIARY SUPPORT AND NOTICE" in markdown_response.text
    assert "COUNT I - RETALIATION" in markdown_response.text
    assert "APPENDIX A - CASE SYNOPSIS" not in markdown_response.text

    pdf_response = client.get(
        "/api/complaint-workspace/export/download",
        params={"user_id": user_id, "output_format": "pdf"},
    )
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"].startswith("application/pdf")
    assert 'filename="jordan-example-v.-acme-corporation-complaint.pdf"' in pdf_response.headers["content-disposition"]
    assert pdf_response.content.startswith(b"%PDF-1.4")
    assert b"Jordan Example v. Acme Corporation Complaint" in pdf_response.content

    docx_response = client.get(
        "/api/complaint-workspace/export/download",
        params={"user_id": user_id, "output_format": "docx"},
    )
    assert docx_response.status_code == 200
    assert docx_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert 'filename="jordan-example-v.-acme-corporation-complaint.docx"' in docx_response.headers["content-disposition"]
    assert docx_response.content.startswith(b"PK")
    with zipfile.ZipFile(BytesIO(docx_response.content)) as docx_archive:
        document_xml = docx_archive.read("word/document.xml").decode("utf-8")
    assert "Jordan Example v. Acme Corporation Complaint" in document_xml
    assert "COMPLAINT FOR RETALIATION" in document_xml


def test_exported_packet_snapshot_is_restored_in_session_state(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "restored-export-sessions")
    user_id = "restored-export-user"
    service.submit_intake_answers(
        user_id,
        {
            "party_name": "Jordan Example",
            "opposing_party": "Acme Corporation",
            "protected_activity": "Reported discrimination to HR",
            "adverse_action": "Was terminated two days later",
            "timeline": "Reported discrimination on March 8 and was terminated on March 10",
            "harm": "Lost wages and benefits",
        },
    )
    service.save_evidence(
        user_id,
        kind="document",
        claim_element_id="causation",
        title="Termination email",
        content="The termination email followed within two days of the HR complaint.",
        source="Inbox export",
    )
    service.generate_complaint(
        user_id,
        requested_relief=["Back pay", "Compensatory damages"],
        title_override="Jordan Example v. Acme Corporation Complaint",
    )

    export_payload = service.export_complaint_packet(user_id)
    session_payload = service.get_session(user_id)
    restored_export = session_payload["session"]["latest_packet_export"]

    assert restored_export["packet"]["title"] == export_payload["packet"]["title"]
    assert restored_export["packet"]["claim_type"] == export_payload["packet"]["claim_type"]
    assert restored_export["packet"]["draft"]["body"] == export_payload["packet"]["draft"]["body"]
    assert restored_export["packet_summary"]["artifact_formats"] == export_payload["packet_summary"]["artifact_formats"]


def test_get_session_recovers_from_malformed_workspace_state(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "malformed-session-sessions")
    user_id = "malformed-session-user"
    session_path = service._session_path(user_id)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text("{")

    payload = service.get_session(user_id)

    assert payload["session"]["user_id"] == user_id
    assert payload["session"]["claim_type"] == "retaliation"
    assert payload["session"]["intake_answers"] == {}
    restored_payload = json.loads(session_path.read_text())
    assert restored_payload["user_id"] == user_id
    assert restored_payload["claim_type"] == "retaliation"
    assert restored_export["ui_feedback"]["release_gate"] == export_payload["ui_feedback"]["release_gate"]


def test_workspace_save_state_uses_stable_tmp_path(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "stable-save-sessions")
    user_id = "stable-save-user"

    state = service._load_state(user_id)
    saved = service._save_state(state)
    saved_again = service._save_state(saved)

    session_path = service._session_path(user_id)
    tmp_path_candidate = session_path.with_name(f"{session_path.name}.tmp")

    assert session_path.is_file()
    assert not tmp_path_candidate.exists()
    assert saved_again["user_id"] == user_id
