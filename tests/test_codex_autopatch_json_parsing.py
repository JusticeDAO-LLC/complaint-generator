"""Focused tests for parsing Codex tool and final JSON output."""

import importlib.util
import os

import pytest


def _load_codex_autopatch_module():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "examples", "codex_autopatch_from_run.py")
    spec = importlib.util.spec_from_file_location("codex_autopatch_json_parsing", path)
    assert spec and spec.loader, f"Failed to load spec for: {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


_codex_autopatch = _load_codex_autopatch_module()
_try_parse_json_object = _codex_autopatch._try_parse_json_object


@pytest.mark.parametrize(
    "text",
    (
        "{not valid JSON}",
        'model preamble\n{"type": "final",}',
    ),
)
def test_try_parse_json_object_rejects_malformed_model_output(text: str) -> None:
    assert _try_parse_json_object(text) is None


def test_try_parse_json_object_recovers_trailing_object() -> None:
    assert _try_parse_json_object('model preamble\n{"type": "tool", "name": "ls"}') == {
        "type": "tool",
        "name": "ls",
    }


def test_try_parse_json_object_does_not_swallow_unexpected_decoder_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_loads(_text: str):
        raise RuntimeError("unexpected JSON decoder failure")

    monkeypatch.setattr(_codex_autopatch.json, "loads", fail_loads)

    with pytest.raises(RuntimeError, match="unexpected JSON decoder failure"):
        _try_parse_json_object('{"type": "final"}')
