from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_main_readme_documents_module_and_tooling_entrypoints() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert ".venv/bin/python -m complaint_generator.cli --help" in text
    assert ".venv/bin/python -m complaint_generator.mcp_server" in text
    assert "complaint-workspace-cli" in text
    assert "complaint-mcp-server" in text
    assert "Complaint Workspace CLI" in text
    assert "Complaint MCP Server" in text


def test_tests_readme_documents_module_and_tooling_entrypoints() -> None:
    text = (REPO_ROOT / "tests" / "README.md").read_text(encoding="utf-8")

    assert ".venv/bin/python -m complaint_generator.cli --help" in text
    assert ".venv/bin/python -m complaint_generator.mcp_server" in text
    assert "Complaint Workspace CLI" in text
    assert "Complaint MCP Server" in text
