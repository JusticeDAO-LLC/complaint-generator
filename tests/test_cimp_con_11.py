"""CIMP-CON-11: claim-support review body lives under mediator."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BODY_PATH = ROOT / "mediator" / "claim_support_review.py"
SHIM_PATH = ROOT / "claim_support_review.py"


def test_mediator_claim_support_review_holds_payload_builder() -> None:
    text = BODY_PATH.read_text(encoding="utf-8")
    assert len(text.splitlines()) >= 6000
    tree = ast.parse(text, filename=str(BODY_PATH))
    function_names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert "build_claim_support_review_payload" in function_names


def test_root_claim_support_review_is_reexport_shim() -> None:
    text = SHIM_PATH.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 30
    tree = ast.parse(text, filename=str(SHIM_PATH))
    assert not any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree)
    )


def test_root_import_reaches_relocated_payload_builder() -> None:
    import claim_support_review
    from claim_support_review import build_claim_support_review_payload

    assert build_claim_support_review_payload is claim_support_review.build_claim_support_review_payload
    assert build_claim_support_review_payload.__module__ == "mediator.claim_support_review"
