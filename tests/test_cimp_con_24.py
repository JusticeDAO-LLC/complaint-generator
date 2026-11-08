"""CIMP-CON-24: claim-support diagnostics delegate to a sibling module."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "mediator" / "claim_support_hooks.py"
DIAGNOSTICS = REPO_ROOT / "mediator" / "claim_support_diagnostics.py"
EXTRACTED = (
    "_run_element_reasoning_diagnostics",
    "_build_temporal_proof_bundle",
    "_get_temporal_reasoning_context",
)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_methods(tree: ast.AST) -> dict:
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ClaimSupportHook"
    )
    return {
        node.name: node
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
    }


def test_extracted_methods_are_single_return_calls():
    owner_text = OWNER.read_text(encoding="utf-8")
    diagnostics_text = DIAGNOSTICS.read_text(encoding="utf-8")
    owner = _parse(OWNER)
    diagnostics = _parse(DIAGNOSTICS)
    methods = _class_methods(owner)
    defined = {
        node.name
        for node in diagnostics.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert len(owner_text.splitlines()) <= 9600
    assert len(diagnostics_text.splitlines()) >= 1050
    assert "upsert_support_link" in methods
    for name in EXTRACTED:
        method = methods[name]
        assert len(method.body) == 1
        statement = method.body[0]
        assert isinstance(statement, ast.Return)
        assert isinstance(statement.value, ast.Call)
        assert name in defined


def test_upsert_support_link_stays_on_the_class():
    methods = _class_methods(_parse(OWNER))
    diagnostics = _parse(DIAGNOSTICS)
    moved = {
        node.name
        for node in diagnostics.body
        if isinstance(node, ast.FunctionDef)
    }
    assert "upsert_support_link" in methods
    assert "upsert_support_link" not in moved
    assert len(methods["upsert_support_link"].body) > 1
