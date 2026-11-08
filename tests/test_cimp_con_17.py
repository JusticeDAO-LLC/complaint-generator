"""CIMP-CON-17: claim-support review builders live in the sections module."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNER_PATH = ROOT / "mediator" / "claim_support_review.py"
SECTIONS_PATH = ROOT / "mediator" / "claim_support_review_sections.py"
EXTRACTED_NAMES = (
    "_build_review_workflow_priority",
    "summarize_claim_reasoning_review",
    "build_claim_support_review_payload",
)
OWNER_LINE_LIMIT = 4700
SECTIONS_LINE_FLOOR = 1600


def _module_function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _bound_from_sections(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    bound: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith(
            "claim_support_review_sections"
        ):
            bound.update(alias.name for alias in node.names)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound.add(target.id)
    if "claim_support_review_sections" not in text:
        return set()
    return bound


def test_owner_moves_review_builders_and_keeps_follow_up_history() -> None:
    owner_text = OWNER_PATH.read_text(encoding="utf-8")
    owner_names = _module_function_names(OWNER_PATH)
    assert len(owner_text.splitlines()) <= OWNER_LINE_LIMIT
    assert "summarize_follow_up_history_claim" in owner_names
    for name in EXTRACTED_NAMES:
        assert name not in owner_names
    assert set(EXTRACTED_NAMES) <= _bound_from_sections(OWNER_PATH)


def test_sections_module_defines_extracted_review_builders() -> None:
    sections_text = SECTIONS_PATH.read_text(encoding="utf-8")
    sections_names = _module_function_names(SECTIONS_PATH)
    assert len(sections_text.splitlines()) >= SECTIONS_LINE_FLOOR
    for name in EXTRACTED_NAMES:
        assert name in sections_names
