"""Focused tests for multi-run autopatch progress-state loading."""

import importlib.util
import json
import os
import sys
from types import ModuleType
from unittest.mock import patch

import pytest


def _load_codex_multi_run_autopatch_module():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "examples", "codex_multi_run_autopatch.py")

    # This test exercises a standalone persistence helper. Stub the runtime-only
    # integrations so importing the example does not initialize backend stacks.
    stubs = {}
    for module_name, exported_names in {
        "adversarial_harness": ("AdversarialHarness", "Optimizer"),
        "backends": ("LLMRouterBackend",),
        "mediator": ("Mediator",),
    }.items():
        stub = ModuleType(module_name)
        for exported_name in exported_names:
            setattr(stub, exported_name, type(exported_name, (), {}))
        stubs[module_name] = stub

    spec = importlib.util.spec_from_file_location("codex_multi_run_autopatch_progress", path)
    assert spec and spec.loader, f"Failed to load spec for: {path}"
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


_autopatch = _load_codex_multi_run_autopatch_module()


def test_load_json_or_none_returns_none_for_missing_progress_file(tmp_path) -> None:
    assert _autopatch._load_json_or_none(str(tmp_path / "missing.json")) is None


def test_load_json_or_none_loads_progress_object(tmp_path) -> None:
    progress_path = tmp_path / "progress.json"
    progress_path.write_text('{"next_run_index": 3}', encoding="utf-8")

    assert _autopatch._load_json_or_none(str(progress_path)) == {"next_run_index": 3}


def test_load_json_or_none_rejects_non_object_progress(tmp_path) -> None:
    progress_path = tmp_path / "progress.json"
    progress_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match=r"Expected a JSON object.*progress\.json.*list"):
        _autopatch._load_json_or_none(str(progress_path))


def test_load_json_or_none_does_not_swallow_malformed_progress(tmp_path) -> None:
    progress_path = tmp_path / "progress.json"
    progress_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        _autopatch._load_json_or_none(str(progress_path))


def test_load_json_or_none_does_not_swallow_read_failures(monkeypatch) -> None:
    def fail_open(*args, **kwargs):
        raise PermissionError("progress state is unreadable")

    monkeypatch.setattr("builtins.open", fail_open)

    with pytest.raises(PermissionError, match="progress state is unreadable"):
        _autopatch._load_json_or_none("progress.json")
