"""CIMP-CON-20: document-optimization summary functions live in their own module."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER_PATH = REPO_ROOT / "complaint_phases" / "document_optimization.py"
SUMMARIES_PATH = REPO_ROOT / "complaint_phases" / "document_optimization_summaries.py"

EXTRACTED_NAMES = (
    "_build_claim_support_temporal_handoff",
    "_build_claim_reasoning_theorem_export_metadata",
    "_build_anchored_chronology_summary",
    "_build_document_grounding_improvement_summary",
    "_build_document_grounding_lane_outcome_summary",
    "_build_claim_temporal_gap_hints",
    "_build_workflow_targeting_summary",
)
OWNER_CLASS_NAME = "AgenticDocumentOptimizer"
OWNER_LINE_LIMIT = 4200
SUMMARIES_LINE_FLOOR = 650


def _module_function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _module_class_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, ast.ClassDef)}


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_owner_line_count_and_optimizer_class() -> None:
    owner_names = _module_function_names(OWNER_PATH)
    assert _line_count(OWNER_PATH) <= OWNER_LINE_LIMIT
    assert OWNER_CLASS_NAME in _module_class_names(OWNER_PATH)
    for name in EXTRACTED_NAMES:
        assert name not in owner_names


def test_summaries_module_defines_extracted_functions() -> None:
    summary_names = _module_function_names(SUMMARIES_PATH)
    assert _line_count(SUMMARIES_PATH) >= SUMMARIES_LINE_FLOOR
    for name in EXTRACTED_NAMES:
        assert name in summary_names
    assert OWNER_CLASS_NAME not in _module_class_names(SUMMARIES_PATH)


def test_owner_imports_extracted_names() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"), filename=str(OWNER_PATH))
    imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "complaint_phases.document_optimization_summaries":
            imported.update(alias.name for alias in node.names)
    assert set(EXTRACTED_NAMES) <= imported
