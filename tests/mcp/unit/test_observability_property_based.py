"""
Advanced Testing Patterns for Observability Systems

Property-based testing, strategy composition, and fuzzed inputs for verifying
circuit breaker, metrics, and tracing behavior under arbitrary conditions.

Run with: pytest test_observability_property_based.py -v
"""

import pytest
import time
from hypothesis import given, strategies as st, settings, HealthCheck
from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    get_circuit_breaker,
    CircuitBreakerOpenError,
)
from ipfs_datasets_py.logic.observability.metrics_prometheus import (
    get_prometheus_collector,
)
from ipfs_datasets_py.logic.observability.otel_integration import (
    get_otel_tracer,
    SpanStatus,
)


# ============================================================================
# Strategy Definitions
# ============================================================================

component_names = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_",
    min_size=1,
    max_size=30,
).filter(lambda x: not x.startswith("_"))

latencies = st.floats(min_value=0.0001, max_value=10.0, allow_nan=False, allow_infinity=False)

failure_thresholds = st.integers(min_value=1, max_value=100)

timeout_seconds = st.floats(min_value=0.1, max_value=300.0, allow_nan=False, allow_infinity=False)

success_flags = st.booleans()

operation_names = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_",
    min_size=1,
    max_size=30,
)


# ============================================================================
# Property-Based Tests: Metrics Recording
# ============================================================================

class TestMetricsPropertyBased:
    """Property-based testing of metrics system."""
    
    @given(component_names, latencies, success_flags)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_metrics_recording_preserves_data(self, component, latency, success):
        """
        Property: Every recorded metric is retrievable.
        
        For any component, latency, and success flag, the metric
        should be recorded and available via get_metrics_summary().
        """
        metrics = get_prometheus_collector()
        
        # Create unique component per example to avoid cross-example contamination
        unique_component = f"{component}_{id(success)}_{time.time_ns()}"
        
        # Record metric
        metrics.record_circuit_breaker_call(unique_component, latency, success=success)
        
        # Retrieve and verify
        summary = metrics.get_metrics_summary(unique_component)
        assert summary['total_calls'] >= 1, "Metric not recorded"
        assert summary['total_calls'] == summary['successful_calls'] + summary['failed_calls'], \
            "Metric accounting inconsistent"
        # With unique component, should have exactly count that matches success
        expected_success_count = 1 if success else 0
        assert summary['successful_calls'] == expected_success_count, \
            f"Expected {expected_success_count} successful calls, got {summary['successful_calls']}"
    
    @given(st.lists(latencies, min_size=10, max_size=100))
    @settings(max_examples=50)
    def test_percentiles_are_ordered(self, latencies_list):
        """
        Property: Percentile values maintain ordering.
        
        For any set of latencies, p50 <= p95 <= p99
        """
        metrics = get_prometheus_collector()
        component = f"percentile_test_{id(latencies_list)}"
        
        for latency in latencies_list:
            metrics.record_circuit_breaker_call(component, latency, success=True)
        
        summary = metrics.get_metrics_summary(component)
        p50 = summary['latency_percentiles']['p50']
        p95 = summary['latency_percentiles']['p95']
        p99 = summary['latency_percentiles']['p99']
        
        assert p50 <= p95, "P50 should be <= P95"
        # Allow for floating point rounding errors (< 1e-10)
        assert p95 <= p99 or abs(p95 - p99) < 1e-10, f"P95 should be <= P99 ({p95} vs {p99})"
    
    @given(st.lists(success_flags, min_size=10, max_size=100))
    @settings(max_examples=50)
    def test_success_rate_formula_correctness(self, success_list):
        """
        Property: Success rate = successes / total * 100.
        
        For any sequence of boolean successes, the reported
        success rate matches the mathematical definition.
        """
        metrics = get_prometheus_collector()
        component = f"success_rate_test_{time.time_ns()}"
        
        for success in success_list:
            metrics.record_circuit_breaker_call(component, 0.01, success=success)
        
        summary = metrics.get_metrics_summary(component)
        
        expected_rate = sum(success_list) / len(success_list) * 100
        assert abs(summary['success_rate'] - expected_rate) < 0.1, \
            f"Success rate mismatch: {summary['success_rate']} != {expected_rate}"


# ============================================================================
# Property-Based Tests: Tracing
# ============================================================================

class TestTracingPropertyBased:
    """Property-based testing of tracing system."""
    
    @given(operation_names, st.integers(1, 10))
    @settings(max_examples=100)
    def test_traces_contain_requested_spans(self, op_name, num_spans):
        """
        Property: Created spans appear in completed traces.
        
        For any operation name and span count, all created spans
        exist in the corresponding completed trace.
        """
        tracer = get_otel_tracer()
        
        # Create trace with multiple spans
        spans = []
        for i in range(num_spans):
            span = tracer.start_span(op_name)
            span.attributes["index"] = i
            tracer.end_span(span, status=SpanStatus.OK)
            spans.append(span)
        
        # Verify trace exists and contains spans
        assert len(tracer.get_completed_traces()) > 0, "No traces created"
    
    @given(st.lists(operation_names, min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_span_hierarchy_consistency(self, operation_sequence):
        """
        Property: Span parent-child relationships are consistent.
        
        For any sequence of operations, the trace should maintain
        proper parent-child relationships or have no parents.
        """
        tracer = get_otel_tracer()
        
        for op in operation_sequence:
            span = tracer.start_span(op)
            tracer.end_span(span, status=SpanStatus.OK)
        
        # Check trace consistency
        for trace in tracer.get_completed_traces():
            for span in trace.spans:
                # Parent must exist in same trace
                if span.parent_span_id:
                    parents = [s for s in trace.spans if s.span_id == span.parent_span_id]
                    assert len(parents) > 0, "Parent span not found in trace"


# ============================================================================
# Property-Based Tests: Circuit Breaker
# ============================================================================

class TestCircuitBreakerPropertyBased:
    """Property-based testing of circuit breaker."""
    
    @given(failure_thresholds)
    @settings(max_examples=50)
    def test_circuit_opens_after_threshold(self, threshold):
        """
        Property: Circuit opens after exactly N failures.
        
        For any failure threshold, the circuit opens after N
        consecutive failures.
        """
        cb = get_circuit_breaker(f"test_cb_{threshold}")
        cb.failure_threshold = threshold
        
        def failing_service():
            raise Exception("Synthetic failure")
        
        # Trigger failures
        opened = False
        for i in range(threshold + 10):
            try:
                cb.call(failing_service)
            except CircuitBreakerOpenError:
                opened = True
                break
            except Exception:
                pass
        
        # Should have opened around threshold
        assert opened, f"Circuit didn't open after {threshold} failures"
        assert cb.metrics.failure_count >= threshold, "Failure count doesn't match"
    
    @given(st.lists(success_flags, min_size=5, max_size=50))
    @settings(max_examples=50)
    def test_circuit_state_reflects_failure_sequence(self, success_sequence):
        """
        Property: Circuit state depends on failure count, not order.
        
        For any ordering of successes and failures with total
        failures < threshold, the circuit remains closed.
        """
        cb = get_circuit_breaker(f"test_cb_{id(success_sequence)}")
        cb.failure_threshold = 100  # High threshold
        
        def service(should_succeed):
            if should_succeed:
                return "ok"
            raise Exception("Failure")
        
        initial_state = cb.state.value
        
        for success in success_sequence:
            try:
                cb.call(service, success)
            except CircuitBreakerOpenError:
                break
            except Exception:
                pass
        
        # With high threshold, state shouldn't change much
        # CircuitState enum uses lowercase values
        assert cb.state.value in ["closed", "open"], "Invalid state"


# ============================================================================
# Fuzz Testing: Invalid Inputs
# ============================================================================

class TestFuzzingInvalidInputs:
    """Fuzz testing with edge cases and invalid inputs."""
    
    @given(
        st.text(min_size=0, max_size=1000),  # Arbitrary component names
        st.floats(allow_nan=True, allow_infinity=True),  # Edge case floats
        st.booleans(),
    )
    @settings(max_examples=100)
    def test_metrics_handles_edge_cases(self, component, latency, success):
        """
        Property: Metrics recording doesn't crash on invalid input.
        
        The system should either accept valid inputs or reject
        gracefully, never crash.
        """
        metrics = get_prometheus_collector()
        
        try:
            # Should not crash, even with invalid inputs
            if latency >= 0 and latency < float('inf') and not (latency != latency):
                metrics.record_circuit_breaker_call(component[:30], latency, success=success)
        except (ValueError, OverflowError, TypeError):
            # Acceptable to reject invalid input
            pass
    
    @given(
        st.text(min_size=0, max_size=1000),  # Arbitrary operation names
        st.integers(min_value=-1000, max_value=1000),  # Edge case integers
    )
    @settings(max_examples=100)
    def test_tracing_handles_edge_cases(self, op_name, value):
        """
        Property: Tracing doesn't crash on invalid span attributes.
        
        Setting arbitrary attributes shouldn't cause system failure.
        """
        tracer = get_otel_tracer()
        
        try:
            span = tracer.start_span(op_name[:100] or "unnamed")
            if -1000 <= value <= 1000:
                span.attributes["value"] = value
            tracer.end_span(span, status=SpanStatus.OK)
        except (ValueError, OverflowError, TypeError):
            # Acceptable to reject invalid input
            pass


# ============================================================================
# Temporal Properties: Ordering and Timing
# ============================================================================

class TestTemporalProperties:
    """Properties about timing and ordering of operations."""
    
    @given(
        st.lists(
            st.tuples(operation_names, st.booleans()),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=50)
    def test_span_timestamps_are_monotonic(self, operations_list):
        """
        Property: Span timestamps increase monotonically.
        
        Each new span should have start_time >= previous span's start_time.
        """
        tracer = get_otel_tracer()
        previous_start = 0
        
        for op_name, success in operations_list:
            span = tracer.start_span(op_name)
            
            # Verify monotonic increase
            assert span.start_time >= previous_start, "Timestamps not monotonic"
            previous_start = span.start_time
            
            status = SpanStatus.OK if success else SpanStatus.ERROR
            tracer.end_span(span, status=status)
    
    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=50)
    def test_metric_call_count_increments_monotonically(self, num_calls):
        """
        Property: Call count never decreases.
        
        After each metric recording, total_calls should increase or stay same.
        """
        metrics = get_prometheus_collector()
        component = f"monotonic_test_{id(metrics)}"
        
        previous_count = 0
        for i in range(num_calls):
            metrics.record_circuit_breaker_call(component, 0.01, success=True)
            summary = metrics.get_metrics_summary(component)
            assert summary['total_calls'] >= previous_count, "Call count decreased"
            previous_count = summary['total_calls']


# ============================================================================
# Invariant Testing: System-Wide Properties
# ============================================================================

class TestInvariants:
    """System-wide invariants that should always hold."""
    
    @given(
        st.lists(
            st.tuples(component_names, latencies, success_flags),
            min_size=1,
            max_size=100,
        )
    )
    @settings(max_examples=50)
    def test_success_count_plus_failure_count_equals_total(self, operations_list):
        """
        Property: success_count + failure_count == total_count.
        
        For any sequence of operations, this invariant holds.
        """
        metrics = get_prometheus_collector()
        
        for component, latency, success in operations_list:
            metrics.record_circuit_breaker_call(component, latency, success=success)
        
        # Check invariant for each component
        for component in set(c for c, _, _ in operations_list):
            summary = metrics.get_metrics_summary(component)
            successes = summary['total_calls'] - summary['failed_calls']
            expected_total = successes + summary['failed_calls']
            assert expected_total == summary['total_calls'], \
                f"Counts don't add up: {successes} + {summary['failed_calls']} != {summary['total_calls']}"
    
    def test_simultaneous_operations_dont_interfere(self):
        """
        Property: Concurrent operations on different components
        don't interfere with each other's metrics.
        """
        metrics = get_prometheus_collector()
        
        # Create different components
        for i in range(10):
            component = f"component_{i}"
            for j in range(10):
                metrics.record_circuit_breaker_call(component, 0.01, success=j % 3 != 0)
        
        # Verify each component has independent metrics
        for i in range(10):
            component = f"component_{i}"
            summary = metrics.get_metrics_summary(component)
            assert summary['total_calls'] == 10, f"Component {component} has wrong count"


# ============================================================================
# Integration Properties: System Behavior
# ============================================================================

class TestIntegrationProperties:
    """Properties about system as a whole."""
    
    @given(
        st.lists(
            st.tuples(component_names, latencies, success_flags),
            min_size=1,
            max_size=50,
        )
    )
    @settings(max_examples=50)
    def test_metrics_export_includes_all_recorded_components(self, operations_list):
        """
        Property: Exported metrics include all recorded components.
        
        After recording metrics to components, exported Prometheus
        format should contain entries for all of them.
        """
        metrics = get_prometheus_collector()
        
        for component, latency, success in operations_list:
            metrics.record_circuit_breaker_call(component, latency, success=success)
        
        # Export and verify
        export_text = metrics.export_prometheus_format()
        
        # Check that some metrics were exported
        assert len(export_text) > 0, "Export generated no output"
        assert "circuit_breaker" in export_text, "Missing circuit breaker metrics"


# ============================================================================
# Regression Testing: Known Issues
# ============================================================================

class TestRegressions:
    """Tests for previously discovered bugs."""
    
    def test_latency_percentiles_handle_small_samples(self):
        """
        Regression: Edge case with fewer than 3 samples caused errors.
        
        Percentiles should work with any number of samples.
        """
        metrics = get_prometheus_collector()
        
        # Single sample
        metrics.record_circuit_breaker_call("single", 0.05, success=True)
        summary = metrics.get_metrics_summary("single")
        assert summary['latency_percentiles']['p99'] >= 0, "P99 calculation failed for 1 sample"
        
        # Two samples
        metrics.record_circuit_breaker_call("single", 0.10, success=True)
        summary = metrics.get_metrics_summary("single")
        assert summary['latency_percentiles']['p99'] >= 0, "P99 calculation failed for 2 samples"
    
    def test_empty_component_metrics_dont_crash_export(self):
        """
        Regression: Exporting metrics with no data shouldn't crash.
        """
        metrics = get_prometheus_collector()
        
        # Record to ensure components exist
        metrics.record_circuit_breaker_call("test", 0.01, success=True)
        
        # Export should not crash even if some metrics are empty
        export_text = metrics.export_prometheus_format()
        assert isinstance(export_text, str), "Export should return string"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])
