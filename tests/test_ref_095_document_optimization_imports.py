from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCUMENT_OPTIMIZATION_PATH = REPO_ROOT / "document_optimization.py"
LOADER_MODULE = "integrations.ipfs_datasets.loader"


def test_optional_import_loader_is_required_infrastructure() -> None:
    """Repository-owned import diagnostics must not silently degrade away."""

    tree = ast.parse(
        DOCUMENT_OPTIMIZATION_PATH.read_text(encoding="utf-8"),
        filename=str(DOCUMENT_OPTIMIZATION_PATH),
    )
    loader_imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == LOADER_MODULE
    ]

    assert len(loader_imports) == 1
    assert [alias.name for alias in loader_imports[0].names] == ["import_attr_optional"]
    assert not any(
        isinstance(node, ast.Try)
        and any(
            isinstance(child, ast.ImportFrom) and child.module == LOADER_MODULE
            for child in node.body
        )
        for node in tree.body
    ), "document_optimization must expose failures in its repository-owned import adapter"
