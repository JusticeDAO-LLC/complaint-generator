"""Existing proof operations stay usable through each operator interface."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import complaint_generator as package
from applications import complaint_cli
from applications.complaint_workspace import ComplaintWorkspaceService


OPERATIONS = (
    ("get_draft_proof_report", "draft-proof-report", "no_draft"),
    ("get_draft_proof_report", "get-draft-proof-report", "no_draft"),
    ("render_draft_proof_report", "render-draft-proof-report", "no_draft"),
    ("pin_draft_proof_report", "pin-draft-proof-report", "no_draft"),
    ("score_draft_quality", "score-draft-quality", "no_draft"),
    ("improve_draft", "improve-draft", "no_draft"),
    ("get_proof_history", "proof-history", "ok"),
)


@pytest.mark.parametrize("operation,command,status", OPERATIONS)
def test_proof_operations_share_empty_session_behavior(
    tmp_path, monkeypatch, operation, command, status,
):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    monkeypatch.setattr(complaint_cli, "service", service)
    wrapper = getattr(package, operation)

    package_result = wrapper("empty-proof-user", service=service)
    cli_result = CliRunner().invoke(complaint_cli.app, [command, "--user-id", "empty-proof-user"])
    mcp_result = package.handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "name": "complaint." + operation,
                "arguments": {"user_id": "empty-proof-user"},
            },
        },
    )

    assert package_result["status"] == status
    assert cli_result.exit_code == 0, cli_result.output
    assert json.loads(cli_result.stdout) == package_result
    assert not mcp_result["result"]["isError"]
    assert mcp_result["result"]["structuredContent"] == package_result
    if operation == "get_proof_history":
        assert package_result["history"] == []
        assert package_result["run_count"] == 0


@pytest.mark.parametrize(
    "operation,command,options,cli_options",
    (
        (
            "get_draft_proof_report", "draft-proof-report",
            {"state_code": "CA", "allow_live_scrape_fallback": True},
            ["--state-code", "CA", "--allow-live-scrape-fallback"],
        ),
        (
            "render_draft_proof_report", "render-draft-proof-report",
            {"state_code": "CA", "claim_id": "claim-one"},
            ["--state-code", "CA", "--claim-id", "claim-one"],
        ),
        (
            "pin_draft_proof_report", "pin-draft-proof-report",
            {"state_code": "CA", "claim_id": "claim-one"},
            ["--state-code", "CA", "--claim-id", "claim-one"],
        ),
        (
            "score_draft_quality", "score-draft-quality",
            {"state_code": "CA", "persist": False},
            ["--state-code", "CA", "--no-persist"],
        ),
        (
            "improve_draft", "improve-draft",
            {
                "state_code": "CA", "provider": "fixture-provider", "model": "fixture-model",
                "config_path": "fixture.json", "backend_id": "fixture-backend", "max_suggestions": 2,
            },
            [
                "--state-code", "CA", "--provider", "fixture-provider", "--model", "fixture-model",
                "--config-path", "fixture.json", "--backend-id", "fixture-backend", "--max-suggestions", "2",
            ],
        ),
        ("get_proof_history", "proof-history", {}, []),
    ),
)
def test_proof_wrappers_preserve_explicit_operator_options(
    tmp_path, monkeypatch, operation, command, options, cli_options,
):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    calls = []

    def fake_operation(user_id, **kwargs):
        calls.append((user_id, kwargs))
        return {"status": "fixture", "operation": operation}

    monkeypatch.setattr(service, operation, fake_operation)
    monkeypatch.setattr(complaint_cli, "service", service)
    package_result = getattr(package, operation)("proof-user", service=service, **options)
    cli_result = CliRunner().invoke(
        complaint_cli.app, [command, "--user-id", "proof-user", *cli_options],
    )
    assert cli_result.exit_code == 0, cli_result.output
    assert json.loads(cli_result.stdout) == package_result
    assert calls == [("proof-user", options), ("proof-user", options)]


def test_tooling_contract_matches_actual_package_and_cli_bindings():
    contract = ComplaintWorkspaceService().get_tooling_contract()
    registered_commands = {command.name for command in complaint_cli.app.registered_commands}
    assert contract["surface_inventory"]["status"] == "verified"
    assert contract["missing_exposures"] == []
    for step in contract["core_flow_steps"]:
        assert callable(getattr(package, step["package_export"], None)), step
        assert step["cli_command"] in registered_commands, step


def test_tooling_contract_reports_unknown_when_sources_are_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ComplaintWorkspaceService, "_repo_root", staticmethod(lambda: Path(tmp_path)))
    contract = ComplaintWorkspaceService().get_tooling_contract()
    assert contract["surface_inventory"]["status"] == "unknown"
    assert contract["surface_inventory"]["unavailable_sources"]
    assert contract["all_core_flow_steps_exposed"] is False
    assert contract["package_exports"] == []
    assert contract["cli_commands"] == []
    assert contract["browser_sdk_methods"] == []


def test_tooling_inventory_accepts_exports_from_their_actual_source_module(tmp_path, monkeypatch):
    package_dir = tmp_path / "complaint_generator"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text(
        "from .reviews import review_ui\n__all__ = ['review_ui']\n"
    )
    (package_dir / "reviews.py").write_text("def review_ui():\n    pass\n")
    monkeypatch.setattr(ComplaintWorkspaceService, "_repo_root", staticmethod(lambda: tmp_path))
    members = ComplaintWorkspaceService._tooling_contract_source_members()
    assert "review_ui" in members["package_exports"]
