"""CIMP-CON-19: document-pipeline readiness methods delegate to a sibling module."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER_PATH = REPO_ROOT / "complaint_phases" / "document_pipeline.py"
READINESS_PATH = REPO_ROOT / "complaint_phases" / "document_pipeline_readiness.py"

EXTRACTED_NAMES = (
    "_build_drafting_readiness",
    "_build_intake_questioning_phase_guidance",
)
OWNER_METHOD_NAME = "build_package"
OWNER_LINE_LIMIT = 10200
READINESS_LINE_FLOOR = 950


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_methods(path: Path) -> dict[str, ast.FunctionDef]:
    tree = _parse(path)
    builder = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "FormalComplaintDocumentBuilder"
    )
    return {
        node.name: node
        for node in builder.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _module_function_names(path: Path) -> set[str]:
    tree = _parse(path)
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_owner_line_count_and_build_package_remains() -> None:
    methods = _class_methods(OWNER_PATH)
    assert _line_count(OWNER_PATH) <= OWNER_LINE_LIMIT
    assert OWNER_METHOD_NAME in methods


def test_extracted_methods_are_single_return_calls() -> None:
    methods = _class_methods(OWNER_PATH)
    for name in EXTRACTED_NAMES:
        method = methods[name]
        assert len(method.body) == 1
        statement = method.body[0]
        assert isinstance(statement, ast.Return)
        assert isinstance(statement.value, ast.Call)


def test_readiness_module_defines_extracted_functions() -> None:
    readiness_names = _module_function_names(READINESS_PATH)
    assert _line_count(READINESS_PATH) >= READINESS_LINE_FLOOR
    for name in EXTRACTED_NAMES:
        assert name in readiness_names
    assert OWNER_METHOD_NAME not in readiness_names
