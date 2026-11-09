"""Pytest configuration for MCP unit tests."""

import pytest


def _reset_observability_state() -> None:
    """Reset required observability state, surfacing isolation failures to pytest."""
    from ipfs_datasets_py.logic.observability.metrics_prometheus import (
        get_prometheus_collector,
    )
    from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer

    get_prometheus_collector().reset_all()

    # OTelTracer does not expose a public reset API. Keep this deliberate private
    # access visible so an incompatible tracer change fails instead of silently
    # disabling test isolation.
    get_otel_tracer()._completed_traces.clear()


@pytest.fixture(autouse=True)
def reset_observability_singletons():
    """Reset observability singletons to prevent cross-test contamination."""
    _reset_observability_state()
    try:
        yield
    finally:
        _reset_observability_state()
