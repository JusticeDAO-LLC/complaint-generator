"""CIMP-CON-09: document pipeline body lives under complaint_phases."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BODY_PATH = ROOT / "complaint_phases" / "document_pipeline.py"
SHIM_PATH = ROOT / "document_pipeline.py"


def test_complaint_phases_document_pipeline_holds_builder_body() -> None:
    text = BODY_PATH.read_text(encoding="utf-8")
    assert len(text.splitlines()) >= 11000
    tree = ast.parse(text, filename=str(BODY_PATH))
    class_names = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
    assert "FormalComplaintDocumentBuilder" in class_names


def test_root_document_pipeline_is_reexport_shim() -> None:
    text = SHIM_PATH.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    assert line_count <= 30
    tree = ast.parse(text, filename=str(SHIM_PATH))
    assert not any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
    assert not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree))


def test_root_import_reaches_relocated_builder() -> None:
    import document_pipeline
    from document_pipeline import FormalComplaintDocumentBuilder

    assert FormalComplaintDocumentBuilder is document_pipeline.FormalComplaintDocumentBuilder
    assert document_pipeline.FormalComplaintDocumentBuilder.__module__ == "complaint_phases.document_pipeline"
