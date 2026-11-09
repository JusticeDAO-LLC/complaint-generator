import importlib.util
from importlib import import_module
from pathlib import Path

import pytest


def _load_mcp_unit_conftest():
    conftest_path = Path(__file__).parent / "mcp" / "unit" / "conftest.py"
    spec = importlib.util.spec_from_file_location(
        "ref_237_mcp_unit_conftest", conftest_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reset_observability_state_resets_metrics_and_completed_traces():
    mcp_conftest = _load_mcp_unit_conftest()
    metrics_module = import_module(
        "ipfs_datasets_py.logic.observability.metrics_prometheus"
    )
    tracing_module = import_module(
        "ipfs_datasets_py.logic.observability.otel_integration"
    )
    metrics = metrics_module.get_prometheus_collector()
    tracer = tracing_module.get_otel_tracer()
    metrics.record_circuit_breaker_call("ref-237", 0.01, success=True)
    metrics.record_log_entry("ref-237")
    tracer._completed_traces.append(object())

    mcp_conftest._reset_observability_state()

    assert metrics.get_components() == set()
    assert metrics.export_prometheus_format().endswith(
        "# TYPE log_entries_by_level counter"
    )
    assert tracer.get_completed_traces() == []


def test_reset_observability_state_does_not_swallow_reset_failures(monkeypatch):
    mcp_conftest = _load_mcp_unit_conftest()

    class BrokenCollector:
        def reset_all(self):
            raise RuntimeError("collector reset failed")

    metrics_module = import_module(
        "ipfs_datasets_py.logic.observability.metrics_prometheus"
    )
    monkeypatch.setattr(
        metrics_module,
        "get_prometheus_collector",
        lambda: BrokenCollector(),
    )

    with pytest.raises(RuntimeError, match="collector reset failed"):
        mcp_conftest._reset_observability_state()


def test_reset_fixture_cleans_up_after_the_test(monkeypatch):
    mcp_conftest = _load_mcp_unit_conftest()
    reset_calls = []
    monkeypatch.setattr(
        mcp_conftest,
        "_reset_observability_state",
        lambda: reset_calls.append("reset"),
    )
    fixture = mcp_conftest.reset_observability_singletons.__wrapped__()

    next(fixture)
    with pytest.raises(StopIteration):
        next(fixture)

    assert reset_calls == ["reset", "reset"]
