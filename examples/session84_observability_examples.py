"""
Comprehensive code examples for MCP++ Session 84 features.

Demonstrates usage of:
- Prometheus metrics collection
- OpenTelemetry distributed tracing
- Structured JSON logging (from Session 83)
- Circuit breaker pattern (from Session 83)

These examples show best practices and common integration patterns.
"""

import time
from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    get_circuit_breaker,
    CircuitBreakerOpenError,
)
from ipfs_datasets_py.logic.observability.structured_logging import (
    log_event,
    log_error,
    log_performance,
    LogContext,
)
from ipfs_datasets_py.logic.observability.metrics_prometheus import (
    PrometheusMetricsCollector,
    get_prometheus_collector,
)
from ipfs_datasets_py.logic.observability.otel_integration import (
    OTelTracer,
    EventType,
    get_otel_tracer,
)


# ============================================================================
# Example 1: Simple Circuit Breaker Usage
# ============================================================================

def example_basic_circuit_breaker():
    """Basic circuit breaker usage for a payment API."""
    
    def charge_card(amount: float) -> dict:
        """Simulate payment API call."""
        # In real code, this would call an actual payment processor
        return {"transaction_id": "txn_123", "amount": amount, "status": "success"}
    
    # Get the circuit breaker for this service
    cb = get_circuit_breaker("payment_processor")
    
    try:
        # All calls go through the circuit breaker
        result = cb.call(charge_card, amount=99.99)
        print(f"Payment successful: {result}")
    except CircuitBreakerOpenError:
        # Service is down - use fallback
        print("Payment service is temporarily unavailable. Please try again later.")
        result = {"status": "deferred", "amount": 99.99}


# ============================================================================
# Example 2: Structured Logging with Context
# ============================================================================

def example_structured_logging():
    """Using structured logging for all events."""
    
    # Begin a request context - all logs in this scope get the request_id
    with LogContext(component="user_service", request_id="req_abc123"):
        log_event("request_started", {"endpoint": "/users/123", "method": "GET"})
        
        # Simulate some work
        user = {"id": 123, "name": "Alice"}
        log_event("user_loaded", {"user_id": user["id"]})
        
        # Log performance metrics
        with log_performance("database_query", {"query": "SELECT user"}):
            time.sleep(0.05)  # Simulate DB work
            db_result = user
        
        # Automatic timing: logs show duration in milliseconds
        log_event("request_completed", {
            "status": 200,
            "user_count": 1,
        })


# ============================================================================
# Example 3: Error Handling with Logging
# ============================================================================

def example_error_logging():
    """Structured error logging."""
    
    def process_document(doc_id: str):
        """Simulate document processing."""
        if doc_id == "invalid":
            raise ValueError(f"Invalid document ID: {doc_id}")
        return {"doc_id": doc_id, "pages": 42}
    
    with LogContext(request_id="req_xyz789"):
        try:
            log_event("processing_started", {"doc_id": "doc_123"})
            result = process_document("doc_123")
            log_event("processing_succeeded", {"pages": result["pages"]})
        except ValueError as e:
            # Both logs the error and preserves stack trace
            log_error("processing_failed", e)
            # Could also use fallback or queue for retry


# ============================================================================
# Example 4: Prometheus Metrics Recording
# ============================================================================

def example_prometheus_metrics():
    """Recording metrics for Prometheus."""
    
    collector = PrometheusMetricsCollector()
    
    # Simulate 100 API calls with varying latencies
    for i in range(100):
        # Random latency from 10ms to 500ms
        latency = 0.010 + (i % 50) * 0.010
        success = i % 5 != 0  # 80% success rate
        
        collector.record_circuit_breaker_call("api_v1", latency, success=success)
    
    # Get a summary
    summary = collector.get_metrics_summary("api_v1")
    print(f"Total calls: {summary['total_calls']}")
    print(f"Success rate: {summary['success_rate']:.1f}%")
    print(f"Average latency: {summary['avg_latency']:.3f}s")
    print(f"P95 latency: {summary['latency_percentiles']['p95']:.3f}s")
    
    # Export for Prometheus
    prometheus_text = collector.export_prometheus_format()
    # In real code: POST to Prometheus or write to file


# ============================================================================
# Example 5: OpenTelemetry Distributed Tracing
# ============================================================================

def example_otel_tracing():
    """Using OpenTelemetry for distributed tracing."""
    
    tracer = OTelTracer("complaint_generator")
    
    # Create a parent span for the entire operation
    with tracer.span_context("process_complaint", {"complaint_id": "123"}) as parent:
        tracer.set_span_attribute(parent, "user_id", "user_abc")
        
        # Child span: load complaint data
        with tracer.span_context("load_complaint_data") as load_span:
            time.sleep(0.05)  # Simulate DB read
            tracer.record_event(load_span, EventType.CIRCUIT_BREAKER_CALL, {
                "database": "complaints_db",
                "rows_loaded": 1,
            })
        
        # Child span: analyze complaint
        with tracer.span_context("analyze_complaint") as analyze_span:
            time.sleep(0.10)  # Simulate analysis
            tracer.record_event(analyze_span, EventType.LOG_ENTRY, {
                "severity": "high",
                "analysis_result": "requires_action",
            })
        
        # Child span: send notification
        with tracer.span_context("send_notification") as notify_span:
            try:
                time.sleep(0.02)
                tracer.record_event(notify_span, EventType.CIRCUIT_BREAKER_CALL, {
                    "service": "email",
                    "recipients": 1,
                })
            except Exception as e:
                tracer.record_error(notify_span, str(e), type(e).__name__)
    
    # Export the trace
    traces = tracer.get_completed_traces()
    jaeger_json = tracer.export_jaeger_format()
    # In real code: send to Jaeger collector


# ============================================================================
# Example 6: Complete Integration Pattern
# ============================================================================

def example_complete_integration():
    """Best-practices integration of all components."""
    
    def external_api_call(endpoint: str, timeout: float = 5.0) -> dict:
        """Call external API with full observability."""
        
        # Get the circuit breaker and metrics collector
        cb = get_circuit_breaker("external_api")
        metrics = get_prometheus_collector()
        tracer = get_otel_tracer()
        
        # Use structured logging for this request
        with LogContext(component="api_client", request_id=f"call_{endpoint}"):
            log_event("api_call_starting", {
                "endpoint": endpoint,
                "timeout": timeout,
            })
            
            # Create a trace span for the entire operation
            with tracer.span_context("api_call", {"endpoint": endpoint}) as span:
                tracer.set_span_attribute(span, "timeout_seconds", timeout)
                
                # Record metrics while calling
                start = time.time()
                
                try:
                    # Log performance
                    with log_performance("http_request", {"endpoint": endpoint}):
                        # Protect with circuit breaker
                        response = cb.call(
                            _call_external_api,
                            endpoint,
                            timeout=timeout
                        )
                    
                    elapsed = time.time() - start
                    
                    # Record successful call
                    metrics.record_circuit_breaker_call(
                        "external_api",
                        elapsed,
                        success=True
                    )
                    metrics.record_circuit_breaker_state("external_api", "closed")
                    
                    # Log success
                    log_event("api_call_succeeded", {
                        "endpoint": endpoint,
                        "status_code": 200,
                        "duration_ms": elapsed * 1000,
                    })
                    
                    # Record event in trace
                    tracer.record_event(span, EventType.CIRCUIT_BREAKER_CALL, {
                        "status": "success",
                        "status_code": 200,
                    })
                    
                    return response
                
                except CircuitBreakerOpenError:
                    elapsed = time.time() - start
                    
                    # Record failure
                    metrics.record_circuit_breaker_call(
                        "external_api",
                        elapsed,
                        success=False
                    )
                    metrics.record_circuit_breaker_state("external_api", "open")
                    
                    # Log the circuit breaker trip
                    log_error(
                        "circuit_breaker_open",
                        Exception("External API circuit breaker is open")
                    )
                    
                    # Record error event
                    tracer.record_event(span, EventType.CIRCUIT_BREAKER_STATE_CHANGE, {
                        "state": "open",
                        "reason": "too_many_failures",
                    })
                    
                    # Return fallback
                    return {"data": None, "cached": True}
                
                except Exception as e:
                    elapsed = time.time() - start
                    
                    # Record failure
                    metrics.record_circuit_breaker_call(
                        "external_api",
                        elapsed,
                        success=False
                    )
                    
                    # Log and trace the error
                    log_error("api_call_failed", e)
                    tracer.record_error(span, str(e), type(e).__name__)
                    
                    raise
    
    # Call the function
    result = external_api_call("/v1/complaints")
    return result


def _call_external_api(endpoint: str, timeout: float) -> dict:
    """Simulate external API call."""
    # In real code, this would use requests.get() or similar
    if endpoint == "/error":
        raise Exception("API error")
    return {"status": "ok", "endpoint": endpoint}


# ============================================================================
# Example 7: Exposing Metrics
# ============================================================================

def example_prometheus_export():
    """Export metrics for Prometheus scraping."""
    
    collector = get_prometheus_collector()
    
    # Your application records metrics throughout its lifetime
    # (examples from other code)
    
    # When Prometheus scrapes /metrics endpoint:
    prometheus_text = collector.export_prometheus_format()
    
    # Output looks like:
    # # HELP circuit_breaker_calls_total Total calls to circuit breaker
    # # TYPE circuit_breaker_calls_total counter
    # circuit_breaker_calls_total{component="api_v1"} 1234
    # circuit_breaker_calls_success{component="api_v1"} 1100
    # circuit_breaker_calls_failed{component="api_v1"} 134
    # circuit_breaker_failure_rate{component="api_v1"} 10.87
    # ...
    
    print(prometheus_text)


# ============================================================================
# Example 8: Concurrent Usage (Thread-Safe)
# ============================================================================

def example_concurrent_usage():
    """Thread-safe concurrent usage of metrics and tracing."""
    import threading
    
    def worker(worker_id: int):
        """Simulate concurrent worker."""
        for i in range(5):
            with LogContext(request_id=f"worker_{worker_id}_req_{i}"):
                log_event("task_started", {"worker_id": worker_id})
                
                # Record metrics
                metrics = get_prometheus_collector()
                start = time.time()
                
                # Simulate work
                time.sleep(0.01)
                
                elapsed = time.time() - start
                metrics.record_circuit_breaker_call(
                    f"worker_{worker_id}",
                    elapsed,
                    success=True
                )
                
                log_event("task_completed", {"worker_id": worker_id})
    
    # Run 10 concurrent workers
    threads = [
        threading.Thread(target=worker, args=(i,))
        for i in range(10)
    ]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # Print summary
    metrics = get_prometheus_collector()
    for component in metrics.get_components():
        summary = metrics.get_metrics_summary(component)
        print(f"{component}: {summary['total_calls']} calls")


# ============================================================================
# Example 9: Fallback Strategies
# ============================================================================

def example_fallback_strategies():
    """Different fallback strategies for circuit breaker."""
    
    def cached_fallback():
        """Return cached data when service is down."""
        cb = get_circuit_breaker("user_service")
        
        try:
            user = cb.call(_fetch_user, user_id=123)
            # Update cache
            return user
        except CircuitBreakerOpenError:
            # Fallback to cache (might be stale, but better than error)
            cached = {"id": 123, "name": "Cached User", "stale": True}
            return cached
    
    def queue_fallback():
        """Queue the operation for retry."""
        cb = get_circuit_breaker("payment_service")
        
        try:
            result = cb.call(_process_payment, amount=100.0)
            return result
        except CircuitBreakerOpenError:
            # Queue for later
            _retry_queue.put({"amount": 100.0, "timestamp": time.time()})
            return {"status": "queued"}
    
    def degrade_fallback():
        """Provide reduced functionality."""
        cb = get_circuit_breaker("recommendation_engine")
        
        try:
            recommendations = cb.call(_get_recommendations, user_id=123)
            return recommendations
        except CircuitBreakerOpenError:
            # Downgrade to popular items instead of personalized
            return {"recommendations": ["popular_1", "popular_2"], "personalized": False}
    
    def fail_fast():
        """Fail immediately without waiting."""
        cb = get_circuit_breaker("critical_service")
        
        try:
            return cb.call(_critical_operation)
        except CircuitBreakerOpenError:
            # This operation requires the service - fail immediately
            raise RuntimeError("Critical service is unavailable")


def _fetch_user(user_id: int) -> dict:
    """Simulate user fetch."""
    return {"id": user_id, "name": f"User {user_id}"}


def _process_payment(amount: float) -> dict:
    """Simulate payment."""
    return {"transaction_id": "txn_123", "amount": amount}


def _get_recommendations(user_id: int) -> dict:
    """Simulate recommendations."""
    return {"user_id": user_id, "recommendations": ["item_1", "item_2"]}


def _critical_operation() -> dict:
    """Simulate critical operation."""
    return {"status": "ok"}


_retry_queue = __import__("queue").Queue()


# ============================================================================
# Example 10: Testing Patterns
# ============================================================================

def example_testing():
    """Patterns for testing with circuit breaker and observability."""
    import pytest
    
    def test_circuit_breaker_opens_on_failures():
        """Test that circuit breaker opens after threshold."""
        from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
            LLMCircuitBreaker,
            FailureThreshold,
        )
        
        cb = LLMCircuitBreaker(
            "test_service",
            failure_threshold=FailureThreshold(count=3)
        )
        
        def failing_func():
            raise ValueError("Service error")
        
        # Should fail 3 times before opening
        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(failing_func)
        
        # Should be open now
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(failing_func)
    
    def test_with_metrics():
        """Test that metrics are recorded correctly."""
        metrics = PrometheusMetricsCollector()
        
        # Record some calls
        for i in range(10):
            metrics.record_circuit_breaker_call(
                "test_api",
                latency=0.01 * (i + 1),
                success=i < 8  # 8 success, 2 failures
            )
        
        # Assert metrics
        summary = metrics.get_metrics_summary("test_api")
        assert summary["total_calls"] == 10
        assert summary["successful_calls"] == 8
        assert summary["failed_calls"] == 2
    
    def test_with_logging(caplog):
        """Test that logging is working."""
        with LogContext(request_id="test_123"):
            log_event("test_event", {"test": "data"})
        
        # Verify log was recorded
        # (In real tests, parse JSON logs or check log capture)


if __name__ == "__main__":
    print("=== Example 1: Basic Circuit Breaker ===")
    example_basic_circuit_breaker()
    
    print("\n=== Example 2: Structured Logging ===")
    example_structured_logging()
    
    print("\n=== Example 3: Error Handling ===")
    example_error_logging()
    
    print("\n=== Example 4: Prometheus Metrics ===")
    example_prometheus_metrics()
    
    print("\n=== Example 5: OpenTelemetry Tracing ===")
    example_otel_tracing()
    
    print("\n=== Example 6: Complete Integration ===")
    example_complete_integration()
    
    print("\n=== Example 7: Prometheus Export ===")
    example_prometheus_export()
    
    print("\n=== Example 8: Concurrent Usage ===")
    example_concurrent_usage()
    
    print("\n=== Example 9: Fallback Strategies ===")
    example_fallback_strategies()
