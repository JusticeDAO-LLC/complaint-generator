"""CIMP-CON-21: workspace draft methods delegate to complaint_workspace_drafting."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "applications" / "complaint_workspace.py"
DRAFTING = REPO_ROOT / "applications" / "complaint_workspace_drafting.py"
EXTRACTED = (
    "_build_draft",
    "_analyze_complaint_output",
    "sync_mike_final_draft",
    "build_mike_handoff",
)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _service_methods(tree: ast.AST) -> dict:
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ComplaintWorkspaceService"
    )
    return {
        node.name: node
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
    }


def test_extracted_draft_methods_are_single_return_calls():
    owner_text = OWNER.read_text(encoding="utf-8")
    drafting_text = DRAFTING.read_text(encoding="utf-8")
    methods = _service_methods(_parse(OWNER))
    defined = {
        node.name
        for node in _parse(DRAFTING).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert len(owner_text.splitlines()) <= 18300
    assert len(drafting_text.splitlines()) >= 1250
    assert "improve_draft" in methods
    for name in EXTRACTED:
        method = methods[name]
        assert len(method.body) == 1, name
        statement = method.body[0]
        assert isinstance(statement, ast.Return), name
        assert isinstance(statement.value, ast.Call), name
        assert name in defined


def test_improve_draft_stays_on_the_service():
    methods = _service_methods(_parse(OWNER))
    moved = {
        node.name
        for node in _parse(DRAFTING).body
        if isinstance(node, ast.FunctionDef)
    }
    assert "improve_draft" in methods
    assert "improve_draft" not in moved
    assert len(methods["improve_draft"].body) > 1
