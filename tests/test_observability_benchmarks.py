"""Focused tests for the observability benchmark example."""

import importlib.util
from pathlib import Path

import pytest


def _load_observability_benchmarks_module():
    path = Path(__file__).resolve().parents[1] / "examples" / "observability_benchmarks.py"
    spec = importlib.util.spec_from_file_location("observability_benchmarks", path)
    assert spec and spec.loader, f"Failed to load spec for: {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_observability_benchmarks = _load_observability_benchmarks_module()


def test_latency_under_load_does_not_swallow_worker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker_error = RuntimeError("load worker failed")

    class StubFuture:
        def __init__(self, error: Exception | None = None) -> None:
            self.error = error

        def result(self, timeout: float | None = None) -> None:
            assert timeout == 5
            if self.error is not None:
                raise self.error

    class StubExecutor:
        def __init__(self, max_workers: int) -> None:
            assert max_workers == 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> bool:
            return False

        def submit(self, worker):
            if worker.__name__ == "load_worker":
                return StubFuture(worker_error)
            return StubFuture()

    monkeypatch.setattr(_observability_benchmarks, "ThreadPoolExecutor", StubExecutor)
    monkeypatch.setattr(_observability_benchmarks, "get_prometheus_collector", object)
    monkeypatch.setattr(_observability_benchmarks.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="load worker failed"):
        _observability_benchmarks.benchmark_latency_under_load(
            load_threads=1,
            test_duration=0,
        )
