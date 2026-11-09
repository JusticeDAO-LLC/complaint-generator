"""CIMP-CON-10: document optimization body lives under complaint_phases."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "complaint_phases" / "document_optimization.py"
SHIM_PATH = ROOT / "document_optimization.py"


def test_complaint_phases_document_optimization_holds_optimizer():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert len(source.splitlines()) >= 4700
    tree = ast.parse(source)
    class_names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert "AgenticDocumentOptimizer" in class_names


def test_root_document_optimization_shim_defines_no_class():
    source = SHIM_PATH.read_text(encoding="utf-8")
    assert len(source.splitlines()) <= 30
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(tree)
    )
