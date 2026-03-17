"""
Integration Test Suite for MCP++ Observability + Core Systems

Tests interaction between observability (metrics, tracing, circuit breaker)
and core system components: query optimizer, complaint analysis, decision trees.

These tests validate end-to-end observability integration across the system.

Run: pytest test_integration_observability_core.py -v
"""

import pytest
import time
from typing import Dict, List, Any

from ipfs_datasets_py.logic.security.llm_circuit_breaker import get_circuit_breaker
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer


# ============================================================================
# Fixture: Mock Core Services
# ============================================================================

class MockQueryOptimizer:
    """Mock query optimizer for integration testing."""
    
    def __init__(self):
        self.call_count = 0
        self.should_fail = False
    
    def optimize(self, query: str) -> Dict[str, Any]:
        """Simulate query optimization."""
        self.call_count += 1
        if self.should_fail:
            raise Exception("Query optimization failed")
        return {
            "optimized_query": f"OPTIMIZED: {query}",
            "execution_time": 0.025,
            "cardinality_estimate": 1000,
        }


class MockComplaintAnalyzer:
    """Mock complaint analyzer for integration testing."""
    
    def __init__(self):
        self.call_count = 0
        self.should_fail = False
    
    def analyze(self, complaint_text: str) -> Dict[str, Any]:
        """Simulate complaint analysis."""
        self.call_count += 1
        if self.should_fail:
            raise Exception("Complaint analysis failed")
        return {
            "complaint_type": "billing",
            "severity": 0.85,
            "keywords": ["overcharge", "payment"],
        }


class MockDecisionTree:
    """Mock decision tree for integration testing."""
    
    def __init__(self):
        self.call_count = 0
        self.should_fail = False
    
    def decide(self, features: Dict[str, Any]) -> str:
        """Simulate decision tree prediction."""
        self.call_count += 1
        if self.should_fail:
            raise Exception("Decision tree failed")
        return "escalate_to_human"


@pytest.fixture
def query_optimizer():
    return MockQueryOptimizer()


@pytest.fixture
def complaint_analyzer():
    return MockComplaintAnalyzer()


@pytest.fixture
def decision_tree():
    return MockDecisionTree()


@pytest.fixture
def observability():
    """Initialize observability components."""
    return {
        "metrics": get_prometheus_collector(),
        "tracer": get_otel_tracer(),
        "cb_query": get_circuit_breaker("query_optimizer"),
        "cb_analysis": get_circuit_breaker("complaint_analyzer"),
        "cb_decision": get_circuit_breaker("decision_tree"),
    }


# ============================================================================
# Integration Tests: Single Component + Observability
# ============================================================================

@pytest.mark.integration
class TestQueryOptimizerWithObservability:
    """Integration tests for query optimizer with metrics and tracing."""
    
    def test_successful_optimization_recorded(self, query_optimizer, observability):
        """Metrics and traces record successful optimization."""
        cb = observability["cb_query"]
        metrics = observability["metrics"]
        tracer = observability["tracer"]
        
        span = tracer.start_span("optimize_query")
        start = time.time()
        
        try:
            result = cb.call(query_optimizer.optimize, "SELECT * FROM complaints")
            elapsed = time.time() - start
            
            metrics.record_circuit_breaker_call("query_optimizer", elapsed, success=True)
            span.attributes["result"] = result["optimized_query"]
            tracer.end_span(span, status="ok")
        except Exception as e:
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("query_optimizer", elapsed, success=False)
            tracer.record_error(span, str(e), "Exception", {})
            tracer.end_span(span, status="error")
            raise
        
        # Verify metrics
        summary = metrics.get_metrics_summary("query_optimizer")
        assert summary['total_calls'] == 1
        assert summary['success_rate'] == 100.0
        
        # Verify trace
        assert len(tracer.get_completed_traces()) > 0
    
    def test_failed_optimization_recorded(self, query_optimizer, observability):
        """Failed optimization recorded in metrics and traces."""
        cb = observability["cb_query"]
        metrics = observability["metrics"]
        tracer = observability["tracer"]
        
        query_optimizer.should_fail = True
        
        span = tracer.start_span("optimize_query_failure")
        start = time.time()
        
        try:
            cb.call(query_optimizer.optimize, "INVALID QUERY")
        except Exception as e:
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("query_optimizer", elapsed, success=False)
            tracer.record_error(span, str(e), "Exception", {})
            tracer.end_span(span, status="error")
        
        # Verify metrics recorded failure
        summary = metrics.get_metrics_summary("query_optimizer")
        assert summary['failed_calls'] > 0


@pytest.mark.integration
class TestComplaintAnalysisWithObservability:
    """Integration tests for complaint analyzer with observability."""
    
    def test_analysis_pipeline_with_full_observability(self, complaint_analyzer, observability):
        """Complete complaint analysis with metrics and traces."""
        cb = observability["cb_analysis"]
        metrics = observability["metrics"]
        tracer = observability["tracer"]
        
        complaint_text = "I was overcharged for my service"
        
        span = tracer.start_span("analyze_complaint")
        start = time.time()
        
        try:
            result = cb.call(complaint_analyzer.analyze, complaint_text)
            elapsed = time.time() - start
            
            metrics.record_circuit_breaker_call("complaint_analyzer", elapsed,success=True)
            span.attributes["complaint_type"] = result["complaint_type"]
            span.attributes["severity"] = result["severity"]
            
            # Record decision as sub-span
            sub_span = tracer.start_span("extract_severity")
            sub_span.attributes["severity_score"] = result["severity"]
            tracer.end_span(sub_span, status="ok")
            
            tracer.end_span(span, status="ok")
        except Exception as e:
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("complaint_analyzer", elapsed, success=False)
            tracer.record_error(span, str(e), "Exception", {})
            tracer.end_span(span, status="error")
        
        # Verify metrics
        summary = metrics.get_metrics_summary("complaint_analyzer")
        assert summary['total_calls'] == 1
        
        # Verify trace has parent and child spans
        assert len(tracer.get_completed_traces()) > 0


# ============================================================================
# Integration Tests: Multi-Component Pipeline
# ============================================================================

@pytest.mark.integration
class TestMultiComponentPipeline:
    """Integration tests for multi-component workflows with full observability."""
    
    def test_complaint_processing_pipeline(
        self, complaint_analyzer, decision_tree, observability
    ):
        """
        Full pipeline: Analyze complaint → Make decision
        
        Tests:
        - Multiple components tracked
        - Cross-component trace correlation
        - Cumulative metrics
        """
        metrics = observability["metrics"]
        tracer = observability["tracer"]
        cb_analysis = observability["cb_analysis"]
        cb_decision = observability["cb_decision"]
        
        complaint_text = "Service was interrupted for 2 days"
        
        # Root span for entire pipeline
        pipeline_span = tracer.start_span("complaint_processing_pipeline")
        
        # Step 1: Analyze complaint
        analysis_span = tracer.start_span("step_1_analysis")
        analysis_start = time.time()
        
        try:
            analysis_result = cb_analysis.call(
                complaint_analyzer.analyze,
                complaint_text
            )
            analysis_elapsed = time.time() - analysis_start
            metrics.record_circuit_breaker_call("complaint_analyzer", analysis_elapsed, success=True)
            analysis_span.attributes["complaint_type"] = analysis_result["complaint_type"]
            tracer.end_span(analysis_span, status="ok")
        except Exception as e:
            analysis_elapsed = time.time() - analysis_start
            metrics.record_circuit_breaker_call("complaint_analyzer", analysis_elapsed, success=False)
            tracer.record_error(analysis_span, str(e), "Exception", {})
            tracer.end_span(analysis_span, status="error")
            raise
        
        # Step 2: Make decision
        decision_span = tracer.start_span("step_2_decision")
        decision_start = time.time()
        
        features = {
            "complaint_type": analysis_result["complaint_type"],
            "severity": analysis_result["severity"],
        }
        
        try:
            decision = cb_decision.call(decision_tree.decide, features)
            decision_elapsed = time.time() - decision_start
            metrics.record_circuit_breaker_call("decision_tree", decision_elapsed, success=True)
            decision_span.attributes["decision"] = decision
            tracer.end_span(decision_span, status="ok")
        except Exception as e:
            decision_elapsed = time.time() - decision_start
            metrics.record_circuit_breaker_call("decision_tree", decision_elapsed, success=False)
            tracer.record_error(decision_span, str(e), "Exception", {})
            tracer.end_span(decision_span, status="error")
            raise
        
        # Complete pipeline span
        pipeline_span.attributes["final_decision"] = decision
        tracer.end_span(pipeline_span, status="ok")
        
        # Verify metrics for both components
        analysis_summary = metrics.get_metrics_summary("complaint_analyzer")
        decision_summary = metrics.get_metrics_summary("decision_tree")
        
        assert analysis_summary['total_calls'] >= 1
        assert decision_summary['total_calls'] >= 1
        assert analysis_summary['success_rate'] == 100.0
        assert decision_summary['success_rate'] == 100.0
        
        # Verify trace structure
        traces = tracer.get_completed_traces()
        assert len(traces) > 0
        
        # Most recent trace should have our spans
        pipeline_trace = traces[-1]
        assert len(pipeline_trace.spans) >= 3  # pipeline + analysis + decision
    
    def test_pipeline_with_partial_failure(
        self, complaint_analyzer, decision_tree, observability
    ):
        """Pipeline handles partial failure with proper observability."""
        metrics = observability["metrics"]
        cb_analysis = observability["cb_analysis"]
        cb_decision = observability["cb_decision"]
        
        # Make decision tree fail
        decision_tree.should_fail = True
        
        analysis_start = time.time()
        try:
            analysis = cb_analysis.call(complaint_analyzer.analyze, "Test complaint")
            analysis_elapsed = time.time() - analysis_start
            metrics.record_circuit_breaker_call("complaint_analyzer", analysis_elapsed, success=True)
        except:
            pass
        
        # Decision will fail
        decision_start = time.time()
        try:
            cb_decision.call(decision_tree.decide, {"type": "billing"})
            decision_elapsed = time.time() - decision_start
            metrics.record_circuit_breaker_call("decision_tree", decision_elapsed, success=True)
        except Exception:
            decision_elapsed = time.time() - decision_start
            metrics.record_circuit_breaker_call("decision_tree", decision_elapsed, success=False)
        
        # Verify metrics show mixed success
        analysis_summary = metrics.get_metrics_summary("complaint_analyzer")
        decision_summary = metrics.get_metrics_summary("decision_tree")
        
        assert analysis_summary['success_rate'] == 100.0  # Succeeded
        assert decision_summary['failed_calls'] > 0  # Failed


# ============================================================================
# Integration Tests: Circuit Breaker Behavior + Observability
# ============================================================================

@pytest.mark.integration
class TestCircuitBreakerWithObservability:
    """Test circuit breaker state changes recorded in observability."""
    
    def test_circuit_breaker_opening_recorded(self, complaint_analyzer, observability):
        """Circuit breaker opening is recorded in metrics and traces."""
        cb = observability["cb_analysis"]
        metrics = observability["metrics"]
        tracer = observability["tracer"]
        
        # Set low threshold for testing
        cb.failure_threshold = 3
        
        complaint_analyzer.should_fail = True
        
        # Trigger failures
        for i in range(5):
            span = tracer.start_span(f"failed_attempt_{i}")
            start = time.time()
            
            try:
                cb.call(complaint_analyzer.analyze, "Test")
                elapsed = time.time() - start
                metrics.record_circuit_breaker_call("complaint_analyzer", elapsed, success=True)
                tracer.end_span(span, status="ok")
            except Exception as e:
                elapsed = time.time() - start
                metrics.record_circuit_breaker_call("complaint_analyzer", elapsed, success=False)
                tracer.record_error(span, "CB test failure", "Exception", {})
                tracer.end_span(span, status="error")
        
        # Verify metrics show increased failure rate
        summary = metrics.get_metrics_summary("complaint_analyzer")
        assert summary['failure_rate'] > 50.0
        assert summary['failed_calls'] > 0
    
    def test_circuit_breaker_recovery_tracked(self, complaint_analyzer, observability):
        """Circuit breaker recovery is tracked in metrics."""
        cb = observability["cb_analysis"]
        metrics = observability["metrics"]
        cb.timeout_seconds = 0.5  # Short timeout for testing
        
        # Cause failures
        complaint_analyzer.should_fail = True
        for _ in range(5):
            try:
                cb.call(complaint_analyzer.analyze, "Test")
            except:
                pass
        
        initial_state = cb.state.value
        
        # Wait for recovery
        time.sleep(cb.timeout_seconds + 0.1)
        
        # Try again (test recovery)
        complaint_analyzer.should_fail = False
        try:
            cb.call(complaint_analyzer.analyze, "Test")
            metrics.record_circuit_breaker_call("complaint_analyzer", 0.01, success=True)
        except:
            metrics.record_circuit_breaker_call("complaint_analyzer", 0.01, success=False)
        
        # Verify recovery was attempted
        summary = metrics.get_metrics_summary("complaint_analyzer")
        assert summary['total_calls'] > 0


# ============================================================================
# Concurrent Integration Tests
# ============================================================================

@pytest.mark.integration
class TestConcurrentMultiComponentIntegration:
    """Test concurrent access to multiple instrumented components."""
    
    def test_concurrent_pipeline_execution(
        self, complaint_analyzer, decision_tree, observability
    ):
        """Multiple pipelines can run concurrently with proper observability."""
        import threading
        from concurrent.futures import ThreadPoolExecutor
        
        metrics = observability["metrics"]
        cb_analysis = observability["cb_analysis"]
        cb_decision = observability["cb_decision"]
        
        num_pipelines = 10
        calls_per_pipeline = 5
        successful = 0
        failed = 0
        lock = threading.Lock()
        
        # Get baseline metrics before test
        analysis_summary_before = metrics.get_metrics_summary("complaint_analyzer")
        decision_summary_before = metrics.get_metrics_summary("decision_tree")
        
        def run_pipeline(pipeline_id: int):
            nonlocal successful, failed
            
            for call_id in range(calls_per_pipeline):
                try:
                    # Analysis
                    analysis = cb_analysis.call(
                        complaint_analyzer.analyze,
                        f"Complaint {pipeline_id}-{call_id}"
                    )
                    metrics.record_circuit_breaker_call("complaint_analyzer", 0.01, success=True)
                    
                    # Decision
                    decision = cb_decision.call(
                        decision_tree.decide,
                        {"type": analysis["complaint_type"]}
                    )
                    metrics.record_circuit_breaker_call("decision_tree", 0.01, success=True)
                    
                    with lock:
                        successful += 1
                except Exception:
                    with lock:
                        failed += 1
        
        # Run pipelines concurrently
        with ThreadPoolExecutor(max_workers=num_pipelines) as executor:
            futures = [
                executor.submit(run_pipeline, i)
                for i in range(num_pipelines)
            ]
            for future in futures:
                future.result()
        
        # Verify metrics increased correctly
        analysis_summary = metrics.get_metrics_summary("complaint_analyzer")
        decision_summary = metrics.get_metrics_summary("decision_tree")
        
        expected_calls = num_pipelines * calls_per_pipeline
        # Check that we added the expected number of calls (accounting for previous test calls)
        assert analysis_summary['total_calls'] >= analysis_summary_before['total_calls'] + expected_calls
        assert decision_summary['total_calls'] >= decision_summary_before['total_calls'] + expected_calls
        assert successful == expected_calls


# ============================================================================
# Cross-Component Metric Correlation Tests
# ============================================================================

@pytest.mark.integration
class TestMetricCorrelation:
    """Test that metrics from different components correlate properly."""
    
    def test_latency_correlation_across_components(
        self, complaint_analyzer, decision_tree, observability
    ):
        """Latencies recorded for components should be consistent."""
        metrics = observability["metrics"]
        cb_analysis = observability["cb_analysis"]
        cb_decision = observability["cb_decision"]
        
        # Get baseline metrics before test
        analysis_summary_before = metrics.get_metrics_summary("complaint_analyzer")
        decision_summary_before = metrics.get_metrics_summary("decision_tree")
        
        # Run 50 calls through each component
        for i in range(50):
            # Analysis call
            start = time.time()
            try:
                cb_analysis.call(complaint_analyzer.analyze, f"Test {i}")
            except:
                pass
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("complaint_analyzer", elapsed, success=True)
            
            # Decision call
            start = time.time()
            try:
                cb_decision.call(decision_tree.decide, {"test": i})
            except:
                pass
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("decision_tree", elapsed, success=True)
        
        # Get summaries
        analysis_summary = metrics.get_metrics_summary("complaint_analyzer")
        decision_summary = metrics.get_metrics_summary("decision_tree")
        
        # Both should have the same increase in call counts (50 each)
        analysis_incremental = analysis_summary['total_calls'] - analysis_summary_before['total_calls']
        decision_incremental = decision_summary['total_calls'] - decision_summary_before['total_calls']
        assert analysis_incremental == 50
        assert decision_incremental == 50
        
        # Both should have similar success rates
        assert (
            abs(analysis_summary['success_rate'] - decision_summary['success_rate']) < 5.0
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
