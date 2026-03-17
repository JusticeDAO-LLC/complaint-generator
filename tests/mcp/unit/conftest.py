"""
Pytest configuration for MCP unit tests.
"""
import pytest


@pytest.fixture(autouse=True)
def reset_observability_singletons():
    """Reset observability singletons between tests to prevent cross-test contamination."""
    # Reset BEFORE test runs
    try:
        from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector
        collector = get_prometheus_collector()
        collector.reset_all()
    except Exception:
        pass
    
    # Reset OTel tracer before test
    try:
        from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer
        tracer = get_otel_tracer()
        # Clear traces if possible
        if hasattr(tracer, '_completed_traces'):
            tracer._completed_traces.clear()
    except Exception:
        pass
    
    yield
    
    # Cleanup after test
    try:
        from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector
        collector = get_prometheus_collector()
        collector.reset_all()
    except Exception:
        pass
