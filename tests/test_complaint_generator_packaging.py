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
    import_gmail_evidence,
    import_local_evidence,
    run_intake_chat_turn,
    run_gmail_duckdb_pipeline,
    run_main,
    search_email_duckdb_corpus,
    tool_list_payload,
)
from applications import complaint_cli as complaint_cli_impl
from complaint_generator import cli as complaint_cli_module
from complaint_generator import entrypoints as complaint_entrypoints
from complaint_generator import mcp as complaint_mcp_module
from complaint_generator import mcp_server as complaint_mcp_server_module
from complaint_generator import workspace as complaint_workspace_module


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
    assert "ipfs_datasets_py[file_conversion,ipld,knowledge_graphs,logic,scraping,vectors]" in pyproject_text
    assert "ipfs_datasets_py[file_conversion,ipld,knowledge_graphs,logic,scraping,vectors]" in setup_text

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


def test_ipfs_datasets_symbolicai_dependency_is_automatic():
    ipfs_setup_text = (REPO_ROOT / "ipfs_datasets_py" / "setup.py").read_text()
    ipfs_pyproject_text = (REPO_ROOT / "ipfs_datasets_py" / "pyproject.toml").read_text()

    assert "'symbolicai>=1.14.0,<2.0.0'" in ipfs_setup_text
    assert '"symbolicai>=1.14.0,<2.0.0"' in ipfs_pyproject_text
    assert "logic = [" in ipfs_pyproject_text
    assert "elif component in {'logic', 'symbolicai'}" in (
        REPO_ROOT / "ipfs_datasets_py" / "ipfs_datasets_py" / "auto_installer.py"
    ).read_text()


def test_ipfs_datasets_ipld_dependency_is_automatic():
    ipfs_setup_text = (REPO_ROOT / "ipfs_datasets_py" / "setup.py").read_text()
    ipfs_pyproject_text = (REPO_ROOT / "ipfs_datasets_py" / "pyproject.toml").read_text()
    auto_installer_text = (
        REPO_ROOT / "ipfs_datasets_py" / "ipfs_datasets_py" / "auto_installer.py"
    ).read_text()

    for dependency in (
        "libipld>=3.3.2",
        "ipld-car>=0.0.1",
        "ipld-dag-pb>=0.0.1",
        "dag-cbor>=0.3.3",
        "multiformats>=0.3.0",
    ):
        assert dependency in ipfs_setup_text
        assert dependency in ipfs_pyproject_text
        assert dependency in auto_installer_text
    assert "elif component == 'ipld'" in auto_installer_text


def test_package_exports_expose_workspace_review_and_entrypoint_helpers():
    assert ComplaintWorkspaceService is not None
    assert attach_complaint_workspace_routes is not None
    assert create_complaint_workspace_router is not None
    assert create_review_surface_app is not None
    assert handle_jsonrpc_message is not None
    assert import_gmail_evidence is not None
    assert import_local_evidence is not None
    assert run_gmail_duckdb_pipeline is not None
    assert search_email_duckdb_corpus is not None
    assert tool_list_payload is not None
    assert ComplaintWorkspaceService is complaint_workspace_module.ComplaintWorkspaceService
    assert handle_jsonrpc_message is complaint_mcp_module.handle_jsonrpc_message
    assert tool_list_payload is complaint_mcp_module.tool_list_payload
    assert complaint_cli_main is complaint_cli_module.main
    assert complaint_mcp_server_main is complaint_mcp_server_module.main
    assert complaint_generator_main is complaint_entrypoints.main
    assert run_main is complaint_entrypoints.run_main

    commonjs_sdk = (REPO_ROOT / "static" / "complaint_mcp_sdk.js").read_text(encoding="utf-8")
    esm_sdk = (REPO_ROOT / "static" / "complaint_mcp_sdk.mjs").read_text(encoding="utf-8")

    assert "ComplaintMcpSdk =" in commonjs_sdk
    assert "module.exports = ComplaintMcpSdk" in commonjs_sdk

    for method_name in (
        "getClientReleaseGate",
        "getFilingProvenance",
        "getFormalDiagnostics",
        "importGmailEvidence",
        "importLocalEvidence",
        "getProviderDiagnostics",
        "getToolingContract",
        "runIntakeChatTurn",
        "updateClaimType",
        "_extractToolDiagnostics",
        "_buildToolDiagnosticSummary",
    ):
        assert method_name in commonjs_sdk
        assert method_name in esm_sdk

    shell_sdk = (REPO_ROOT / "static" / "complaint_app_shell.js").read_text(encoding="utf-8")
    assert "Latest retrieval warning:" in shell_sdk
    assert "Retrieval warning details:" in shell_sdk
    assert "diagnostic_summary" in shell_sdk


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


def test_package_interview_turn_exposes_graph_inquiry_and_provenance(tmp_path):
    """Package entry uses the same interview transition the acceptance suite drives."""

    from tests.test_tui_interview_acceptance import COHERENT, _assert_graph_case, _service

    service = _service(tmp_path, "pkg-accept-user")
    payload = run_intake_chat_turn("pkg-accept-user", message=COHERENT, service=service)
    assert run_intake_chat_turn is complaint_workspace_module.run_intake_chat_turn
    _assert_graph_case(payload, COHERENT)
    assert payload["interview"]["inquiry"]["inquiry_id"].startswith("inq-")
    assert payload["stopping_policy"]["legal_sufficiency"] is False
    assert payload["interview"]["graph"]["provenance"]["keys"]


def test_package_exposes_shared_intake_chat_turn_wrapper(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "workspace-chat-sessions")
    service.initialize_private_keys(protection="passphrase", passphrase="synthetic-package-fixture-passphrase")
    service.ensure_private_case_key("pkg-chat-user", "pkg-chat-user")

    opening = run_intake_chat_turn("pkg-chat-user", service=service)
    assert opening["inquiry"]["question_id"] == "original_complaint"
    assert opening["accepted_answer"] is None

    narrative = run_intake_chat_turn("pkg-chat-user", message="My employer retaliated after a report.", service=service)
    assert narrative["accepted_answer"]["question_id"] == "original_complaint"
    assert narrative["next_question"]["id"] == "party_name"
    assert narrative["session"]["intake_answers"].get("party_name") in {None, ""}
    follow_up = run_intake_chat_turn("pkg-chat-user", message="Jordan Example", service=service)
    assert follow_up["accepted_answer"]["question_id"] == "party_name"
    assert follow_up["next_question"]["id"] == "opposing_party"


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
    assert lines[0]["result"]["protocolVersion"] == "2025-06-18"
    assert any(tool["name"] == "complaint.generate_complaint" for tool in lines[1]["result"]["tools"])
