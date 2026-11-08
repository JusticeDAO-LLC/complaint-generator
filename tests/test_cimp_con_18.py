"""CIMP-CON-18: document-pipeline guidance functions live in their own module."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER_PATH = REPO_ROOT / "complaint_phases" / "document_pipeline.py"
GUIDANCE_PATH = REPO_ROOT / "complaint_phases" / "document_pipeline_guidance.py"

EXTRACTED_NAMES = (
    "_build_runtime_workflow_optimization_guidance",
    "build_drafting_guardrails",
    "build_drafting_support_bundles",
    "_build_anchored_chronology_summary_from_case_file",
)
OWNER_ONLY_NAME = "_extract_latest_adversarial_priority_findings"
OWNER_LINE_LIMIT = 11200
GUIDANCE_LINE_FLOOR = 800


def _module_function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_owner_line_count_and_remaining_definition() -> None:
    owner_names = _module_function_names(OWNER_PATH)
    assert _line_count(OWNER_PATH) <= OWNER_LINE_LIMIT
    assert OWNER_ONLY_NAME in owner_names
    for name in EXTRACTED_NAMES:
        assert name not in owner_names


def test_guidance_module_defines_extracted_functions() -> None:
    guidance_names = _module_function_names(GUIDANCE_PATH)
    assert _line_count(GUIDANCE_PATH) >= GUIDANCE_LINE_FLOOR
    for name in EXTRACTED_NAMES:
        assert name in guidance_names
    assert OWNER_ONLY_NAME not in guidance_names


def test_owner_imports_extracted_names() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"), filename=str(OWNER_PATH))
    imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "complaint_phases.document_pipeline_guidance":
            imported.update(alias.name for alias in node.names)
    assert set(EXTRACTED_NAMES) <= imported
