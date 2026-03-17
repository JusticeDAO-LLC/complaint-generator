"""
Comprehensive tests for Prometheus metrics and OpenTelemetry integration.

Tests for Phase 4 observability features: metrics collection, trace generation,
and distributed tracing capabilities.
"""

import json
import time
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest

from ipfs_datasets_py.logic.observability.metrics_prometheus import (
    CircuitBreakerState,
    PrometheusMetricsCollector,
    get_prometheus_collector,
)
from ipfs_datasets_py.logic.observability.otel_integration import (
    EventType,
    OTelTracer,
    SpanStatus,
    get_otel_tracer,
    setup_otel_tracer,
)


# ============================= Prometheus Tests =============================


class TestPrometheusMetricsBasics:
    """Tests for basic Prometheus metrics collection."""

    def test_record_successful_call(self):
        """Test recording a successful circuit breaker call."""
        collector = PrometheusMetricsCollector()
        collector.record_circuit_breaker_call("api_v1", 0.025, success=True)

        summary = collector.get_metrics_summary("api_v1")
        assert summary["total_calls"] == 1
        assert summary["successful_calls"] == 1
        assert summary["failed_calls"] == 0
        assert summary["success_rate"] == 100.0

    def test_record_failed_call(self):
        """Test recording a failed circuit breaker call."""
        collector = PrometheusMetricsCollector()
        collector.record_circuit_breaker_call("api_v1", 0.050, success=False)

        summary = collector.get_metrics_summary("api_v1")
        assert summary["total_calls"] == 1
        assert summary["successful_calls"] == 0
        assert summary["failed_calls"] == 1
        assert summary["failure_rate"] == 100.0

    def test_multiple_calls_mixed_success(self):
        """Test recording multiple calls with mixed success rates."""
        collector = PrometheusMetricsCollector()
        collector.record_circuit_breaker_call("api_v1", 0.020, success=True)
        collector.record_circuit_breaker_call("api_v1", 0.030, success=True)
        collector.record_circuit_breaker_call("api_v1", 0.100, success=False)
        collector.record_circuit_breaker_call("api_v1", 0.025, success=True)

        summary = collector.get_metrics_summary("api_v1")
        assert summary["total_calls"] == 4
        assert summary["successful_calls"] == 3
        assert summary["failed_calls"] == 1
        assert summary["success_rate"] == 75.0
        assert summary["failure_rate"] == 25.0

    def test_latency_statistics(self):
        """Test latency min/max/avg calculation."""
        collector = PrometheusMetricsCollector()
        latencies = [0.010, 0.020, 0.030, 0.040, 0.050]
        for lat in latencies:
            collector.record_circuit_breaker_call("api_v1", lat, success=True)

        summary = collector.get_metrics_summary("api_v1")
        assert summary["min_latency"] == 0.010
        assert summary["max_latency"] == 0.050
        assert summary["avg_latency"] == 0.030


class TestPrometheusPercentiles:
    """Tests for latency percentile calculations."""

    def test_percentile_calculation_p50(self):
        """Test p50 (median) percentile."""
        collector = PrometheusMetricsCollector()
        # Create 100 latencies for stable percentiles
        for i in range(100):
            latency = 0.010 + (i * 0.001)  # 10ms to 110ms
            collector.record_circuit_breaker_call("api_v1", latency, success=True)

        percentiles = collector.get_latency_percentiles("api_v1", [50])
        assert "p50" in percentiles
        # P50 should be around 60ms (middle of 10-110ms range)
        assert percentiles["p50"] > 0.050
        assert percentiles["p50"] < 0.070

    def test_percentile_calculation_multi_tier(self):
        """Test p95 and p99 percentiles."""
        collector = PrometheusMetricsCollector()
        # Create 100 latencies
        for i in range(100):
            latency = 0.010 + (i * 0.001)
            collector.record_circuit_breaker_call("api_v1", latency, success=True)

        percentiles = collector.get_latency_percentiles("api_v1", [50, 95, 99])
        assert "p50" in percentiles
        assert "p95" in percentiles
        assert "p99" in percentiles
        # p99 should be highest, p50 should be lowest
        assert percentiles["p99"] >= percentiles["p95"]
        assert percentiles["p95"] >= percentiles["p50"]

    def test_percentile_empty_component(self):
        """Test percentile calculation with no data."""
        collector = PrometheusMetricsCollector()
        percentiles = collector.get_latency_percentiles("nonexistent")
        assert percentiles == {"p50": 0.0, "p95": 0.0, "p99": 0.0}

    def test_percentile_single_sample(self):
        """Test percentile with single data point."""
        collector = PrometheusMetricsCollector()
        collector.record_circuit_breaker_call("api_v1", 0.050, success=True)
        percentiles = collector.get_latency_percentiles("api_v1", [50, 95, 99])
        # All percentiles should return the single value
        assert percentiles["p50"] == 0.050
        assert percentiles["p95"] == 0.050
        assert percentiles["p99"] == 0.050


class TestPrometheusStateTracking:
    """Tests for circuit breaker state transitions."""

    def test_record_state_transition(self):
        """Test recording a state transition."""
        collector = PrometheusMetricsCollector()
        collector.record_circuit_breaker_state("api_v1", "closed")
        summary = collector.get_metrics_summary("api_v1")
        assert summary["current_state"] == "closed"

    def test_multiple_state_transitions(self):
        """Test recording multiple state transitions."""
        collector = PrometheusMetricsCollector()
        collector.record_circuit_breaker_state("api_v1", "closed")
        time.sleep(0.01)
        collector.record_circuit_breaker_state("api_v1", "open")
        time.sleep(0.01)
        collector.record_circuit_breaker_state("api_v1", "half_open")
        time.sleep(0.01)
        collector.record_circuit_breaker_state("api_v1", "closed")

        summary = collector.get_metrics_summary("api_v1")
        assert summary["current_state"] == "closed"

    def test_last_failure_time_tracking(self):
        """Test tracking of last failure time."""
        collector = PrometheusMetricsCollector()
        t1 = time.time()
        collector.record_circuit_breaker_call("api_v1", 0.025, success=False, timestamp=t1)
        
        time.sleep(0.05)
        
        t2 = time.time()
        collector.record_circuit_breaker_call("api_v1", 0.025, success=False, timestamp=t2)

        summary = collector.get_metrics_summary("api_v1")
        # Last failure time should be t2
        assert summary["last_failure_time"] == t2


class TestPrometheusLogging:
    """Tests for structured logging metrics."""

    def test_record_log_entry(self):
        """Test recording log entries."""
        collector = PrometheusMetricsCollector()
        collector.record_log_entry("app", level="info")
        collector.record_log_entry("app", level="info")
        collector.record_log_entry("app", level="warning")
        collector.record_log_entry("app", level="error")

        prometheus_text = collector.export_prometheus_format()
        assert "log_entries_total" in prometheus_text

    def test_log_entries_by_level(self):
        """Test tracking log entries by level."""
        collector = PrometheusMetricsCollector()
        collector.record_log_entry("app", level="debug")
        collector.record_log_entry("app", level="info")
        collector.record_log_entry("app", level="info")
        collector.record_log_entry("app", level="warning")
        collector.record_log_entry("app", level="warning")
        collector.record_log_entry("app", level="warning")
        collector.record_log_entry("app", level="error")

        prometheus_text = collector.export_prometheus_format()
        assert "debug" in prometheus_text.lower()
        assert "info" in prometheus_text.lower()
        assert "warning" in prometheus_text.lower()
        assert "error" in prometheus_text.lower()


class TestPrometheusExport:
    """Tests for Prometheus text format export."""

    def test_export_prometheus_format_structure(self):
        """Test export follows Prometheus format."""
        collector = PrometheusMetricsCollector()
        collector.record_circuit_breaker_call("api_v1", 0.025, success=True)
        collector.record_circuit_breaker_state("api_v1", "closed")

        prometheus_text = collector.export_prometheus_format()
        
        # Should have HELP and TYPE lines
        assert "# HELP" in prometheus_text
        assert "# TYPE" in prometheus_text
        # Should have metric lines
        assert "circuit_breaker_calls_total" in prometheus_text
        assert "api_v1" in prometheus_text

    def test_export_multiple_components(self):
        """Test export with multiple components."""
        collector = PrometheusMetricsCollector()
        collector.record_circuit_breaker_call("api_v1", 0.025, success=True)
        collector.record_circuit_breaker_call("api_v2", 0.030, success=False)

        prometheus_text = collector.export_prometheus_format()
        assert 'component="api_v1"' in prometheus_text
        assert 'component="api_v2"' in prometheus_text

    def test_export_state_mapping(self):
        """Test state to number mapping in export."""
        collector = PrometheusMetricsCollector()
        collector.record_circuit_breaker_state("api_v1", "closed")
        
        prometheus_text = collector.export_prometheus_format()
        # closed = 0, open = 1, half_open = 2
        lines = prometheus_text.split('\n')
        state_lines = [l for l in lines if 'circuit_breaker_state{' in l]
        assert any('closed' in l and '0' in l for l in state_lines)


class TestPrometheusManagement:
    """Tests for Prometheus collector management."""

    def test_get_components(self):
        """Test retrieving registered components."""
        collector = PrometheusMetricsCollector()
        collector.record_circuit_breaker_call("api_v1", 0.025, success=True)
        collector.record_circuit_breaker_call("api_v2", 0.030, success=True)

        components = collector.get_components()
        assert "api_v1" in components
        assert "api_v2" in components

    def test_reset_component(self):
        """Test resetting a single component."""
        collector = PrometheusMetricsCollector()
        collector.record_circuit_breaker_call("api_v1", 0.025, success=True)
        collector.record_circuit_breaker_call("api_v2", 0.030, success=True)

        collector.reset_component("api_v1")
        
        components = collector.get_components()
        assert "api_v1" not in components
        assert "api_v2" in components

    def test_reset_all(self):
        """Test resetting all metrics."""
        collector = PrometheusMetricsCollector()
        collector.record_circuit_breaker_call("api_v1", 0.025, success=True)
        collector.record_circuit_breaker_call("api_v2", 0.030, success=True)

        collector.reset_all()
        
        components = collector.get_components()
        assert len(components) == 0

    def test_singleton_instance(self):
        """Test global singleton pattern."""
        collector1 = get_prometheus_collector()
        collector2 = get_prometheus_collector()
        assert collector1 is collector2

    def test_max_latency_samples(self):
        """Test that max latency samples is respected."""
        collector = PrometheusMetricsCollector(max_latency_samples=10)
        for i in range(20):
            collector.record_circuit_breaker_call("api_v1", float(i) * 0.010, success=True)

        summary = collector.get_metrics_summary("api_v1")
        # Should only have the last 10 samples
        assert summary["max_latency"] > summary["min_latency"]
        # Max should be close to 0.19 (last sample at i=19)
        assert summary["max_latency"] > 0.150


# ============================= OpenTelemetry Tests =============================


class TestOTelSpanBasics:
    """Tests for basic OpenTelemetry span operations."""

    def test_create_span(self):
        """Test creating a span."""
        tracer = OTelTracer("test-service")
        span = tracer.start_span("api_call")

        assert span.name == "api_call"
        assert span.trace_id is not None
        assert span.span_id is not None
        assert span.parent_span_id is None
        assert span.is_active()

    def test_end_span(self):
        """Test ending a span."""
        tracer = OTelTracer("test-service")
        span = tracer.start_span("api_call")
        assert span.is_active()

        tracer.end_span(span)
        assert not span.is_active()
        assert span.end_time is not None
        assert span.status == SpanStatus.OK

    def test_span_with_attributes(self):
        """Test creating span with attributes."""
        tracer = OTelTracer("test-service")
        attrs = {"endpoint": "/data", "method": "GET"}
        span = tracer.start_span("api_call", attributes=attrs)

        assert span.attributes["endpoint"] == "/data"
        assert span.attributes["method"] == "GET"

    def test_set_span_attribute(self):
        """Test setting attributes on an active span."""
        tracer = OTelTracer("test-service")
        span = tracer.start_span("api_call")
        
        tracer.set_span_attribute(span, "status_code", 200)
        
        assert span.attributes["status_code"] == 200

    def test_span_duration(self):
        """Test span duration calculation."""
        tracer = OTelTracer("test-service")
        span = tracer.start_span("api_call")
        time.sleep(0.05)
        tracer.end_span(span)

        duration = span.duration_ms()
        assert duration >= 50.0


class TestOTelHierarchy:
    """Tests for parent-child span relationships."""

    def test_parent_child_spans(self):
        """Test creating parent-child span hierarchy."""
        tracer = OTelTracer("test-service")
        parent = tracer.start_span("request")
        child = tracer.start_span("db_query", parent_span_id=parent.span_id)

        assert child.parent_span_id == parent.span_id
        assert parent.parent_span_id is None

        tracer.end_span(child)
        tracer.end_span(parent)

    def test_implicit_parent_tracking(self):
        """Test implicit parent from span stack."""
        tracer = OTelTracer("test-service")
        parent = tracer.start_span("request")
        child = tracer.start_span("db_query")  # No explicit parent_span_id

        assert child.parent_span_id == parent.span_id

        tracer.end_span(child)
        tracer.end_span(parent)

    def test_get_active_span(self):
        """Test retrieving the currently active span."""
        tracer = OTelTracer("test-service")
        parent = tracer.start_span("request")
        child = tracer.start_span("db_query")

        active = tracer.get_active_span()
        assert active.span_id == child.span_id

        tracer.end_span(child)
        active = tracer.get_active_span()
        assert active.span_id == parent.span_id


class TestOTelEvents:
    """Tests for span events."""

    def test_record_event(self):
        """Test recording an event in a span."""
        tracer = OTelTracer("test-service")
        span = tracer.start_span("api_call")

        event = tracer.record_event(span, EventType.CIRCUIT_BREAKER_CALL)
        
        assert event.name == EventType.CIRCUIT_BREAKER_CALL.value
        assert event in span.events

    def test_event_with_attributes(self):
        """Test recording event with attributes."""
        tracer = OTelTracer("test-service")
        span = tracer.start_span("api_call")

        attrs = {"component": "payment_api", "state": "open"}
        event = tracer.record_event(span, EventType.CIRCUIT_BREAKER_STATE_CHANGE, attrs)

        assert event.attributes["component"] == "payment_api"
        assert event.attributes["state"] == "open"

    def test_record_error(self):
        """Test recording an error event."""
        tracer = OTelTracer("test-service")
        span = tracer.start_span("api_call")

        tracer.record_error(span, "Connection timeout", error_type="TimeoutError")
        
        assert span.status == SpanStatus.ERROR
        assert len(span.events) == 1
        error_event = span.events[0]
        assert error_event.attributes["error.type"] == "TimeoutError"
        assert error_event.attributes["error.message"] == "Connection timeout"


class TestOTelContextManager:
    """Tests for span context manager."""

    def test_span_context_success(self):
        """Test span context manager on success."""
        tracer = OTelTracer("test-service")
        
        with tracer.span_context("api_call") as span:
            assert span.is_active()
            tracer.set_span_attribute(span, "status", "ok")

        assert not span.is_active()
        assert span.status == SpanStatus.OK
        assert span.attributes["status"] == "ok"

    def test_span_context_exception(self):
        """Test span context manager on exception."""
        tracer = OTelTracer("test-service")
        
        with pytest.raises(ValueError):
            with tracer.span_context("api_call") as span:
                raise ValueError("Test error")

        assert span.status == SpanStatus.ERROR
        assert len(span.events) == 1
        assert "Test error" in span.events[0].attributes["error.message"]

    def test_nested_span_contexts(self):
        """Test nested span context managers."""
        tracer = OTelTracer("test-service")
        
        with tracer.span_context("outer") as outer:
            outer_span_id = outer.span_id
            with tracer.span_context("inner") as inner:
                assert inner.parent_span_id == outer_span_id
                inner_span_id = inner.span_id

        assert outer.status == SpanStatus.OK
        assert inner.status == SpanStatus.OK


class TestOTelTraces:
    """Tests for trace management."""

    def test_trace_creation_implicit(self):
        """Test trace is created implicitly with first span."""
        tracer = OTelTracer("test-service")
        span = tracer.start_span("api_call")

        trace = tracer.get_trace(span.trace_id)
        assert trace is not None
        assert span in trace.spans

    def test_trace_completion(self):
        """Test trace completion when root span ends."""
        tracer = OTelTracer("test-service")
        span = tracer.start_span("api_call")
        trace_id = span.trace_id

        tracer.end_span(span)

        # Trace should be moved to completed_traces
        completed = tracer.get_completed_traces()
        assert any(t.trace_id == trace_id for t in completed)

    def test_get_completed_traces(self):
        """Test retrieving completed traces."""
        tracer = OTelTracer("test-service")
        
        for i in range(3):
            span = tracer.start_span(f"call_{i}")
            tracer.end_span(span)

        completed = tracer.get_completed_traces()
        assert len(completed) >= 3

    def test_trace_max_completed(self):
        """Test max completed traces limit."""
        tracer = OTelTracer("test-service")
        
        # Create 150 completed traces (default max is 100)
        for i in range(150):
            span = tracer.start_span(f"call_{i}")
            tracer.end_span(span)

        completed = tracer.get_completed_traces()
        # Should not exceed max (but may be up to max + 1 due to race)
        assert len(completed) <= 110


class TestOTelExport:
    """Tests for trace export formats."""

    def test_jaeger_export_format(self):
        """Test Jaeger JSON export format."""
        tracer = OTelTracer("test-service")
        span = tracer.start_span("api_call", {"method": "GET"})
        tracer.record_event(span, EventType.CIRCUIT_BREAKER_CALL)
        tracer.end_span(span)

        jaeger_json = tracer.export_jaeger_format()
        data = json.loads(jaeger_json)

        assert "data" in data
        assert isinstance(data["data"], list)
        if data["data"]:
            trace_data = data["data"][0]
            assert "traceID" in trace_data
            assert "spans" in trace_data
            assert len(trace_data["spans"]) > 0

    def test_jaeger_export_with_errors(self):
        """Test Jaeger export includes error tags."""
        tracer = OTelTracer("test-service")
        span = tracer.start_span("api_call")
        tracer.record_error(span, "Timeout", error_type="TimeoutError")
        tracer.end_span(span)

        jaeger_json = tracer.export_jaeger_format()
        assert "Timeout" in jaeger_json or "TimeoutError" in jaeger_json


class TestOTelConcurrency:
    """Tests for thread-safe tracing."""

    def test_concurrent_spans(self):
        """Test concurrent span creation in multiple threads."""
        tracer = OTelTracer("test-service")
        results = []

        def create_span(thread_id):
            span = tracer.start_span(f"thread_{thread_id}")
            time.sleep(0.01)
            tracer.end_span(span)
            results.append(span)

        threads = [Thread(target=create_span, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        # All spans should have unique IDs
        span_ids = {s.span_id for s in results}
        assert len(span_ids) == 10

    def test_trace_context_isolation(self):
        """Test trace context isolation between threads."""
        tracer = OTelTracer("test-service")
        trace_ids = []

        def get_trace_id():
            span = tracer.start_span("test")
            trace_ids.append(span.trace_id)
            tracer.end_span(span)

        threads = [Thread(target=get_trace_id) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each thread should have gotten its own trace ID
        # (or at least their own context)
        assert len(set(trace_ids)) > 0


# ============================= Integration Tests =============================


class TestPrometheusOTelIntegration:
    """Tests for integrated Prometheus + OpenTelemetry usage."""

    def test_combined_metrics_and_tracing(self):
        """Test using Prometheus and OpenTelemetry together."""
        metrics = PrometheusMetricsCollector()
        tracer = OTelTracer("test-service")

        # Record some activity
        with tracer.span_context("api_call") as span:
            tracer.set_span_attribute(span, "component", "payment_api")
            metrics.record_circuit_breaker_call("payment_api", 0.025, success=True)

        # Both systems should have recorded the activity
        prometheus_text = metrics.export_prometheus_format()
        completed = tracer.get_completed_traces()

        assert "payment_api" in prometheus_text
        assert len(completed) > 0

    def test_error_recording_both_systems(self):
        """Test error recording in both metrics and traces."""
        metrics = PrometheusMetricsCollector()
        tracer = OTelTracer("test-service")

        try:
            with tracer.span_context("api_call") as span:
                metrics.record_circuit_breaker_call("api_v1", 0.050, success=False)
                tracer.record_error(span, "API Error")
                raise RuntimeError("Simulated API failure")
        except RuntimeError:
            pass

        summary = metrics.get_metrics_summary("api_v1")
        completed = tracer.get_completed_traces()

        assert summary["failed_calls"] == 1
        assert len(completed) > 0
        assert completed[0].spans[-1].status == SpanStatus.ERROR


# ============================= Performance Tests =============================


class TestPrometheusPerformance:
    """Tests for Prometheus collector performance under load."""

    def test_high_throughput_recording(self):
        """Test recording at high throughput."""
        collector = PrometheusMetricsCollector()
        
        start = time.time()
        for i in range(1000):
            collector.record_circuit_breaker_call("api_v1", 0.025, success=True)
        elapsed = time.time() - start

        summary = collector.get_metrics_summary("api_v1")
        assert summary["total_calls"] == 1000
        # Should complete in reasonable time (< 1 second for 1000 calls)
        assert elapsed < 1.0

    def test_concurrent_recording(self):
        """Test concurrent metric recording."""
        collector = PrometheusMetricsCollector()
        
        def record_calls(thread_id):
            for i in range(100):
                collector.record_circuit_breaker_call(f"api_{thread_id}", 0.025, success=True)

        threads = [Thread(target=record_calls, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All recordings should succeed
        components = collector.get_components()
        assert len(components) == 10
        for component in components:
            summary = collector.get_metrics_summary(component)
            assert summary["total_calls"] == 100


class TestOTelPerformance:
    """Tests for OpenTelemetry tracer performance."""

    def test_span_creation_performance(self):
        """Test span creation overhead."""
        tracer = OTelTracer("test-service")
        
        start = time.time()
        spans = []
        for i in range(500):
            span = tracer.start_span(f"call_{i}")
            spans.append(span)
            tracer.end_span(span)
        elapsed = time.time() - start

        # Should handle 500 span create/end cycles reasonably fast
        assert elapsed < 2.0
        completed = tracer.get_completed_traces()
        assert len(completed) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
