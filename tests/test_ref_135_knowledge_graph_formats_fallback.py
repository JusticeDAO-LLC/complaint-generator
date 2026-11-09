"""Focused validation for the standalone knowledge-graph format fallback."""

import importlib.util
import sys
from pathlib import Path

import pytest

from integrations.ipfs_datasets import loader as loader_module


MODULE_PATH = Path(__file__).parents[1] / "lib" / "knowledge_graph_formats.py"


@pytest.fixture()
def fallback_formats(monkeypatch):
    """Load the shim while making the optional upstream package unavailable."""

    def unavailable_formats(module_name):
        assert module_name == "ipfs_datasets_py.knowledge_graphs.migration.formats"
        return None, ImportError("ipfs_datasets_py intentionally unavailable")

    monkeypatch.setattr(loader_module, "import_module_optional", unavailable_formats)
    module_name = "_ref_135_knowledge_graph_formats_fallback"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(module_name, None)


@pytest.mark.parametrize("operation", ["save", "load"])
def test_unregistered_format_has_actionable_runtime_error(
    fallback_formats, tmp_path, operation
):
    graph = fallback_formats.GraphData()
    filepath = str(tmp_path / "graph.car")

    with pytest.raises(ValueError) as exc_info:
        if operation == "save":
            graph.save_to_file(filepath, fallback_formats.MigrationFormat.CAR)
        else:
            fallback_formats.GraphData.load_from_file(
                filepath, fallback_formats.MigrationFormat.CAR
            )

    message = str(exc_info.value)
    assert f"Unsupported {operation} format 'car'" in message
    assert f"Available {operation} formats: dag-json, jsonlines" in message
    assert "Call register_format()" in message


def test_unregistered_non_enum_format_does_not_mask_error(fallback_formats, tmp_path):
    with pytest.raises(ValueError, match="Unsupported save format 'yaml'"):
        fallback_formats.GraphData().save_to_file(str(tmp_path / "graph"), "yaml")
