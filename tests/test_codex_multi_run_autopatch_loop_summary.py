"""Focused tests for autopatch-loop summary loading."""

import importlib.util
import json
import os

import pytest


def _load_codex_multi_run_autopatch_loop_module():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "examples", "codex_multi_run_autopatch_loop.py")
    spec = importlib.util.spec_from_file_location(
        "codex_multi_run_autopatch_loop_summary", path
    )
    assert spec and spec.loader, f"Failed to load spec for: {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


_autopatch_loop = _load_codex_multi_run_autopatch_loop_module()


def test_load_orchestrator_id_from_summary(tmp_path) -> None:
    summary_path = tmp_path / "autopatch_summary.json"
    summary_path.write_text(
        json.dumps({"orchestrator_id": "autopatch_loop_0001"}),
        encoding="utf-8",
    )

    assert (
        _autopatch_loop._load_orchestrator_id(str(summary_path))
        == "autopatch_loop_0001"
    )


def test_load_orchestrator_id_allows_omitted_field(tmp_path) -> None:
    summary_path = tmp_path / "autopatch_summary.json"
    summary_path.write_text("{}", encoding="utf-8")

    assert _autopatch_loop._load_orchestrator_id(str(summary_path)) is None


@pytest.mark.parametrize(
    ("payload", "invalid_type"),
    [
        ("[]", "list"),
        ('{"orchestrator_id": 123}', "int"),
    ],
)
def test_load_orchestrator_id_rejects_invalid_summary_contract(
    tmp_path, payload: str, invalid_type: str
) -> None:
    summary_path = tmp_path / "autopatch_summary.json"
    summary_path.write_text(payload, encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=rf"autopatch_summary\.json.*{invalid_type}",
    ):
        _autopatch_loop._load_orchestrator_id(str(summary_path))


def test_load_orchestrator_id_does_not_swallow_malformed_summary(tmp_path) -> None:
    summary_path = tmp_path / "autopatch_summary.json"
    summary_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        _autopatch_loop._load_orchestrator_id(str(summary_path))


def test_load_orchestrator_id_does_not_swallow_read_failures(monkeypatch) -> None:
    def fail_open(*args, **kwargs):
        raise PermissionError("summary artifact is unreadable")

    monkeypatch.setattr("builtins.open", fail_open)

    with pytest.raises(PermissionError, match="summary artifact is unreadable"):
        _autopatch_loop._load_orchestrator_id("autopatch_summary.json")
