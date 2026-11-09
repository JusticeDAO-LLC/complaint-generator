"""Focused tests for diagnostic prompt construction."""

import importlib.util
import os

import pytest


def _load_codex_autopatch_module():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "examples", "codex_autopatch_from_run.py")
    spec = importlib.util.spec_from_file_location("codex_autopatch_prompt", path)
    assert spec and spec.loader, f"Failed to load spec for: {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


_codex_autopatch = _load_codex_autopatch_module()


def _build_prompt(optimizer_report):
    return _codex_autopatch._build_prompt(
        run_dir="run",
        cycle_summary_path="cycle_summary.json",
        cycle_summary={"optimizer_report": optimizer_report},
        sgd_report_path="sgd_report.json",
        sgd_report={},
        worst_sessions=[],
        worst_session_json_paths=[],
        context_mode="lean",
    )


def test_build_prompt_ignores_non_numeric_average_entity_metric() -> None:
    prompt = _build_prompt({"kg_avg_total_entities": "not-a-number"})

    assert "Knowledge graphs are very small on average" not in prompt


def test_build_prompt_does_not_swallow_unexpected_metric_conversion_failure() -> None:
    class BrokenMetric:
        def __float__(self) -> float:
            raise RuntimeError("unexpected metric conversion failure")

    with pytest.raises(RuntimeError, match="unexpected metric conversion failure"):
        _build_prompt({"kg_avg_total_entities": BrokenMetric()})


def test_build_prompt_ignores_non_numeric_entity_growth_metric() -> None:
    prompt = _build_prompt({"kg_avg_entities_delta_per_iter": "not-a-number"})

    assert "Knowledge graph is not growing per iteration" not in prompt


def test_build_prompt_flags_low_entity_growth_metric() -> None:
    prompt = _build_prompt({"kg_avg_entities_delta_per_iter": "0.05"})

    assert "Knowledge graph is not growing per iteration" in prompt


def test_build_prompt_does_not_swallow_unexpected_entity_growth_conversion_failure() -> None:
    class BrokenMetric:
        def __float__(self) -> float:
            raise RuntimeError("unexpected metric conversion failure")

    with pytest.raises(RuntimeError, match="unexpected metric conversion failure"):
        _build_prompt({"kg_avg_entities_delta_per_iter": BrokenMetric()})


def test_build_prompt_ignores_non_numeric_relationship_growth_metric() -> None:
    prompt = _build_prompt({"kg_avg_relationships_delta_per_iter": "not-a-number"})

    assert "Knowledge graph relationships are not growing per iteration" not in prompt


def test_build_prompt_flags_low_relationship_growth_metric() -> None:
    prompt = _build_prompt({"kg_avg_relationships_delta_per_iter": "0.04"})

    assert "Knowledge graph relationships are not growing per iteration" in prompt


def test_build_prompt_does_not_swallow_unexpected_relationship_growth_conversion_failure() -> None:
    class BrokenMetric:
        def __float__(self) -> float:
            raise RuntimeError("unexpected relationship metric conversion failure")

    with pytest.raises(RuntimeError, match="unexpected relationship metric conversion failure"):
        _build_prompt({"kg_avg_relationships_delta_per_iter": BrokenMetric()})


@pytest.mark.parametrize("metric", ["not-a-number", object()])
def test_build_prompt_ignores_non_numeric_average_dependency_node_metric(metric: object) -> None:
    prompt = _build_prompt({"dg_avg_total_nodes": metric})

    assert "Dependency graphs are very small on average" not in prompt


def test_build_prompt_flags_low_average_dependency_node_metric() -> None:
    prompt = _build_prompt({"dg_avg_total_nodes": "1.5"})

    assert "Dependency graphs are very small on average" in prompt


def test_build_prompt_does_not_swallow_unexpected_dependency_node_conversion_failure() -> None:
    class BrokenMetric:
        def __float__(self) -> float:
            raise RuntimeError("unexpected dependency node metric conversion failure")

    with pytest.raises(RuntimeError, match="unexpected dependency node metric conversion failure"):
        _build_prompt({"dg_avg_total_nodes": BrokenMetric()})


@pytest.mark.parametrize(
    "metric_name",
    [
        "kg_sessions_with_data",
        "dg_sessions_with_data",
        "kg_sessions_empty",
        "dg_sessions_empty",
        "kg_sessions_gaps_not_reducing",
    ],
)
def test_build_prompt_defaults_malformed_optimizer_counts_to_zero(metric_name: str) -> None:
    prompt = _build_prompt({metric_name: "not-a-count"})

    assert "Knowledge graphs are empty across analyzed sessions" not in prompt
    assert "Dependency graphs are empty across analyzed sessions" not in prompt
    assert "Knowledge graph gaps are not reducing across iterations" not in prompt


def test_build_prompt_malformed_count_does_not_suppress_other_diagnostics() -> None:
    prompt = _build_prompt(
        {
            "kg_sessions_with_data": "not-a-count",
            "dg_sessions_with_data": 2,
            "dg_sessions_empty": 2,
        }
    )

    assert "Dependency graphs are empty across analyzed sessions" in prompt


def test_build_prompt_does_not_swallow_unexpected_count_conversion_failure() -> None:
    class BrokenCount:
        def __int__(self) -> int:
            raise RuntimeError("unexpected count conversion failure")

    with pytest.raises(RuntimeError, match="unexpected count conversion failure"):
        _build_prompt({"kg_sessions_with_data": BrokenCount()})


@pytest.mark.parametrize("metric", ["not-a-number", object(), 10**1000])
def test_build_prompt_ignores_malformed_gap_delta_metric(metric: object) -> None:
    prompt = _build_prompt({"kg_avg_gaps_delta_per_iter": metric})

    assert "Knowledge graph gaps are flat/increasing per iteration" not in prompt


def test_build_prompt_flags_flat_or_increasing_gap_delta() -> None:
    prompt = _build_prompt({"kg_avg_gaps_delta_per_iter": "0.0"})

    assert "Knowledge graph gaps are flat/increasing per iteration" in prompt


def test_build_prompt_does_not_swallow_unexpected_gap_delta_conversion_failure() -> None:
    class BrokenMetric:
        def __float__(self) -> float:
            raise RuntimeError("unexpected gap delta conversion failure")

    with pytest.raises(RuntimeError, match="unexpected gap delta conversion failure"):
        _build_prompt({"kg_avg_gaps_delta_per_iter": BrokenMetric()})
