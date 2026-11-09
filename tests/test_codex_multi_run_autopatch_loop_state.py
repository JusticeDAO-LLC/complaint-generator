"""Focused tests for autopatch-loop state loading."""

import importlib.util
import json
import os

import pytest


def _load_codex_multi_run_autopatch_loop_module():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "examples", "codex_multi_run_autopatch_loop.py")
    spec = importlib.util.spec_from_file_location(
        "codex_multi_run_autopatch_loop_state", path
    )
    assert spec and spec.loader, f"Failed to load spec for: {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_loop = _load_codex_multi_run_autopatch_loop_module()


def test_load_json_or_none_returns_none_for_missing_state_file(tmp_path) -> None:
    assert _loop._load_json_or_none(str(tmp_path / "missing.json")) is None


def test_load_json_or_none_loads_state_object(tmp_path) -> None:
    state_path = tmp_path / "loop-state.json"
    state_path.write_text(
        '{"loop_index": 3, "active_orchestrator_id": "run-3"}',
        encoding="utf-8",
    )

    assert _loop._load_json_or_none(str(state_path)) == {
        "loop_index": 3,
        "active_orchestrator_id": "run-3",
    }


def test_load_json_or_none_rejects_non_object_state(tmp_path) -> None:
    state_path = tmp_path / "loop-state.json"
    state_path.write_text("[]", encoding="utf-8")

    with pytest.raises(
        ValueError, match=r"Expected a JSON object.*loop-state\.json.*list"
    ):
        _loop._load_json_or_none(str(state_path))


def test_load_json_or_none_does_not_swallow_malformed_state(tmp_path) -> None:
    state_path = tmp_path / "loop-state.json"
    state_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        _loop._load_json_or_none(str(state_path))


def test_load_json_or_none_does_not_swallow_read_failures(monkeypatch) -> None:
    def fail_open(*args, **kwargs):
        raise PermissionError("loop state is unreadable")

    monkeypatch.setattr("builtins.open", fail_open)

    with pytest.raises(PermissionError, match="loop state is unreadable"):
        _loop._load_json_or_none("loop-state.json")
