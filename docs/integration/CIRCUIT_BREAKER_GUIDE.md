# Circuit Breaker Integration Guide

**Updated:** 2026-02-25  
**Phase:** Session 84 - Phase 4 (Observability Integration)

---

## Table of Contents

1. [Overview](#overview)
2. [When to Use](#when-to-use)
3. [Getting Started](#getting-started)
4. [Configuration](#configuration)
5. [Usage Patterns](#usage-patterns)
6. [With Structured Logging](#with-structured-logging)
7. [With Prometheus](#with-prometheus-metrics)
8. [Fallback Strategies](#fallback-strategies)
9. [Testing](#testing)
10. [Troubleshooting](#troubleshooting)

---

## Overview

A circuit breaker protects your application from cascading failures when calling external services. It acts like an electrical circuit breaker: when too many failures occur, it "trips" and stops sending requests until the service recovers.

### States

The circuit breaker has three states:

```
┌─────────────────────────────────────────┐
│            CLOSED (Normal)              │ All requests pass through
├─────────────────────────────────────────┤
│  - All requests succeed                 │
│  - Failures < threshold (5%)            │
│  - Timeout not exceeded                 │
└────────────────┬────────────────────────┘
                 │ Too many failures
                 ▼
┌─────────────────────────────────────────┐
│             OPEN (Trip)                 │ Requests fail immediately
├─────────────────────────────────────────┤
│  - Failures >= threshold (5%)           │
│  - All requests rejected with error     │
│  - Waits for timeout period (10s)       │
└────────────────┬────────────────────────┘
                 │ Timeout elapsed
                 ▼
┌─────────────────────────────────────────┐
│          HALF_OPEN (Testing)            │ Test requests
├─────────────────────────────────────────┤
│  - Allow limited requests (1 per call)  │
│  - If succeed → back to CLOSED          │
│  - If fail → back to OPEN               │
└─────────────────────────────────────────┘
```

---

## When to Use

**Perfect for:**
- External API calls (payment processors, SMS services, etc.)
- Database connections to remote systems
- Third-party LLM API calls
- Any "hard dependency" that can fail

**Not needed for:**
- Local in-process operations
- Operations that must never fail
- Operations with built-in retry logic

---

## Getting Started

### Step 1: Import

```python
from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    get_circuit_breaker,
    CircuitBreakerOpenError,
)
```

### Step 2: Get or Create

```python
# Get the circuit breaker for a specific service
cb = get_circuit_breaker("payment_api")

# The circuit breaker is a singleton per name - same instance everywhere
cb2 = get_circuit_breaker("payment_api")
assert cb is cb2  # True
```

### Step 3: Protect Calls

```python
# Option A: Manual call()
try:
    result = cb.call(payment_api.charge, amount=100.0)
except CircuitBreakerOpenError:
    # Handle failure - use fallback or abort
    result = use_fallback_payment(amount=100.0)

# Option B: Decorator
@cb.protected
def charge_payment(amount):
    return payment_api.charge(amount)

# Decorator will raise CircuitBreakerOpenError if open
try:
    result = charge_payment(100.0)
except CircuitBreakerOpenError:
    # Handle
    pass
```

---

## Configuration

Circuit breakers are configured with sensible defaults, but can be customized:

```python
from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    LLMCircuitBreaker,
    FailureThreshold,
)

# Custom configuration
cb = LLMCircuitBreaker(
    name="slow_api",
    failure_threshold=FailureThreshold(
        count=10,           # Trip after 10 failures
        percentage=10.0,    # Or 10% failure rate
    ),
    timeout_seconds=30.0,   # Wait 30s before trying again
    exponential_backoff=True,  # Increase timeout on repeated failures
)

# Register globally so all code can access it
from ipfs_datasets_py.logic.security.llm_circuit_breaker import _circuit_breakers
_circuit_breakers["slow_api"] = cb
```

---

## Usage Patterns

### Pattern 1: Simple Sync Call

```python
def send_email(to, subject, body):
    cb = get_circuit_breaker("email_service")
    try:
        result = cb.call(email_api.send, to=to, subject=subject, body=body)
        return result
    except CircuitBreakerOpenError:
        # Email service is down - queue for retry
        save_to_retry_queue({"to": to, "subject": subject})
        return None
```

### Pattern 2: With Timeout Handling

```python
def call_external_api(endpoint, **kwargs):
    cb = get_circuit_breaker("external_api")
    try:
        result = cb.call(
            requests.get,
            endpoint,
            timeout=5.0,  # Don't wait forever
            **kwargs
        )
        return result
    except CircuitBreakerOpenError:
        # Circuit is open - return cached/default response
        return get_cached_response(endpoint)
    except TimeoutError:
        # Timeout is treated as failure - circuit tracks it
        return get_cached_response(endpoint)
```

### Pattern 3: With Fallback

```python
def get_user_profile(user_id):
    cb = get_circuit_breaker("user_service")
    try:
        return cb.call(user_api.get_profile, user_id)
    except CircuitBreakerOpenError:
        # Return minimal profile from cache
        return {
            "id": user_id,
            "cached": True,
            "name": get_cached_name(user_id),
        }
```

### Pattern 4: Decorator Pattern

```python
from functools import wraps

def require_circuit_breaker(service_name):
    """Decorator to automatically protect a function."""
    def decorator(func):
        cb = get_circuit_breaker(service_name)
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return cb.call(func, *args, **kwargs)
            except CircuitBreakerOpenError:
                raise RuntimeError(f"{service_name} is currently unavailable")
        return wrapper
    return decorator

# Usage:
@require_circuit_breaker("payment_api")
def process_payment(amount):
    return payment_api.charge(amount)
```

### Pattern 5: Graceful Degradation

```python
def enrich_user_data(user):
    """Add extra fields, but don't fail if enrichment service is down."""
    cb = get_circuit_breaker("enrichment_service")
    
    enriched = dict(user)
    try:
        extra = cb.call(enrichment_api.get_extra, user_id=user["id"])
        enriched.update(extra)
    except CircuitBreakerOpenError:
        # Service is down - continue without enrichment
        enriched["enrichment_available"] = False
    
    return enriched
```

---

## With Structured Logging

Integrate circuit breaker with structured logging for observability:

```python
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

def process_payment_with_logging(user_id, amount):
    with LogContext(component="payment_processor", request_id=user_id):
        cb = get_circuit_breaker("payment_api")
        
        log_event("payment_started", {"amount": amount})
        
        try:
            with log_performance("payment_api_call"):
                result = cb.call(payment_api.charge, amount=amount)
            
            log_event("payment_succeeded", {
                "amount": amount,
                "transaction_id": result.id,
            })
            return result
            
        except CircuitBreakerOpenError:
            log_error("payment_failed", 
                     Exception("Payment service circuit breaker is open"))
            # Handle fallback...
```

All logs automatically include:
- `request_id`: user_id
- `component`: payment_processor
- `timestamp`: automatic
- `level`: info/error

---

## With Prometheus Metrics

Track circuit breaker health with Prometheus:

```python
from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    get_circuit_breaker,
    CircuitBreakerOpenError,
)
from ipfs_datasets_py.logic.observability.metrics_prometheus import (
    get_prometheus_collector,
)

def call_with_metrics(service_name, func, *args, **kwargs):
    """Call a function through circuit breaker, recording metrics."""
    cb = get_circuit_breaker(service_name)
    metrics = get_prometheus_collector()
    
    import time
    start = time.time()
    
    try:
        result = cb.call(func, *args, **kwargs)
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call(service_name, elapsed, success=True)
        metrics.record_circuit_breaker_state(service_name, "closed")
        return result
        
    except CircuitBreakerOpenError:
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call(service_name, elapsed, success=False)
        metrics.record_circuit_breaker_state(service_name, "open")
        raise
    except Exception as e:
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call(service_name, elapsed, success=False)
        raise

# Export metrics for Prometheus scraping
metrics = get_prometheus_collector()
prometheus_text = metrics.export_prometheus_format()
# Send to Prometheus or write to file
```

---

## With OpenTelemetry

Trace circuit breaker calls across distributed systems:

```python
from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    get_circuit_breaker,
    CircuitBreakerOpenError,
)
from ipfs_datasets_py.logic.observability.otel_integration import (
    get_otel_tracer,
    EventType,
)

def call_with_tracing(service_name, func, *args, **kwargs):
    """Call with distributed tracing."""
    cb = get_circuit_breaker(service_name)
    tracer = get_otel_tracer()
    
    with tracer.span_context(f"{service_name}_call", {"service": service_name}) as span:
        try:
            tracer.record_event(span, EventType.CIRCUIT_BREAKER_CALL, {
                "component": service_name,
                "action": "call",
            })
            result = cb.call(func, *args, **kwargs)
            return result
            
        except CircuitBreakerOpenError:
            tracer.record_event(span, EventType.CIRCUIT_BREAKER_STATE_CHANGE, {
                "component": service_name,
                "state": "open",
            })
            raise
        except Exception as e:
            tracer.record_error(span, str(e), type(e).__name__)
            raise
```

This creates spans that Jaeger can visualize as traces:
```
request_123
  ├─ payment_api_call (span_1)
  │  ├─ circuit_breaker.call (event)
  │  └─ 52ms
  ├─ email_api_call (span_2)
  │  ├─ circuit_breaker.state_change → open (event)
  │  └─ 0.5ms (rejected)
```

---

## Fallback Strategies

### Strategy 1: Cached Fallback

```python
import functools

def get_with_cache(key, fetch_func, cache_ttl=3600):
    """Fetch with fallback to cache."""
    cb = get_circuit_breaker("fetch_service")
    
    try:
        return cb.call(fetch_func)
    except CircuitBreakerOpenError:
        return CACHE.get(key)  # 1 hour old is better than nothing

# Usage:
user = get_with_cache(f"user_{user_id}", 
                     lambda: user_api.get(user_id))
```

### Strategy 2: Default Fallback

```python
def get_enrichment(user_id, default=None):
    """Get enrichment, or return default if unavailable."""
    cb = get_circuit_breaker("enrichment")
    
    try:
        return cb.call(enrichment_api.get, user_id)
    except CircuitBreakerOpenError:
        return default or {}
```

### Strategy 3: Queue for Retry

```python
def send_notification(user_id, message):
    """Send notification, or queue if service is down."""
    cb = get_circuit_breaker("notification_service")
    
    try:
        return cb.call(notif_api.send, user_id, message)
    except CircuitBreakerOpenError:
        # Queue for later
        RETRY_QUEUE.put({"user_id": user_id, "message": message})
        return {"queued": True}
```

### Strategy 4: Degrade Features

```python
def get_recommendations(user_id, require_fresh=False):
    """Get recommendations. If service down, return cached."""
    cb = get_circuit_breaker("recommendation_service")
    
    try:
        return cb.call(recom_api.get, user_id)
    except CircuitBreakerOpenError:
        if require_fresh:
            raise
        # Degrade to cached/popular recommendations
        return get_cached_recommendations(user_id)
```

---

## Testing

### Test 1: Circuit Opens on Failures

```python
import pytest
from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    LLMCircuitBreaker,
    CircuitBreakerOpenError,
    FailureThreshold,
)

def test_circuit_opens_on_repeated_failures():
    cb = LLMCircuitBreaker(
        "test_service",
        failure_threshold=FailureThreshold(count=3),
    )
    
    def failing_func():
        raise ValueError("Service error")
    
    # First 3 calls fail and are recorded
    for i in range(3):
        with pytest.raises(ValueError):
            cb.call(failing_func)
    
    # 4th call should be rejected immediately (circuit open)
    with pytest.raises(CircuitBreakerOpenError):
        cb.call(failing_func)
```

### Test 2: Circuit Recovers

```python
def test_circuit_recovers_after_timeout():
    cb = LLMCircuitBreaker("test_service", timeout_seconds=0.1)
    
    def failing_func():
        raise ValueError("Transient error")
    
    # Fail until circuit opens
    for _ in range(5):
        try:
            cb.call(failing_func)
        except (ValueError, CircuitBreakerOpenError):
            pass
    
    # Wait for timeout
    import time
    time.sleep(0.15)
    
    # Should now allow one test request (HALF_OPEN)
    def succeeding_func():
        return "success"
    
    result = cb.call(succeeding_func)
    assert result == "success"
    # Circuit should be CLOSED now
```

### Test 3: Metrics Recording

```python
def test_metrics_are_recorded():
    from ipfs_datasets_py.logic.observability.metrics_prometheus import (
        PrometheusMetricsCollector
    )
    
    cb = LLMCircuitBreaker("test_service")
    metrics = PrometheusMetricsCollector()
    
    # Record a successful call
    start = time.time()
    try:
        cb.call(lambda: "success")
    except:
        pass
    elapsed = time.time() - start
    metrics.record_circuit_breaker_call("test_service", elapsed, success=True)
    
    # Check metrics
    summary = metrics.get_metrics_summary("test_service")
    assert summary["successful_calls"] == 1
    assert summary["total_calls"] == 1
```

---

## Troubleshooting

### Issue: "CircuitBreakerOpenError not being caught"

**Solution:** Make sure you're importing the class:

```python
from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    CircuitBreakerOpenError
)

try:
    result = cb.call(my_func)
except CircuitBreakerOpenError:  # ✓ Correct
    handle_failure()
```

### Issue: "Circuit stays open forever"

**Cause:** Timeout might be too long or exceptions aren't being counted  
**Solution:** Check the timeout and ensure exceptions are reaching the circuit breaker:

```python
# Set shorter timeout for testing
cb = LLMCircuitBreaker("service", timeout_seconds=10)

# Verify exceptions are propagating
try:
    cb.call(my_func)
except CircuitBreakerOpenError as e:
    print(f"Circuit open: {e}")  # Debug info
```

### Issue: "Circuit breaker doesn't seem to be protecting"

**Cause:** Function might not be raising exceptions  
**Solution:** Ensure your wrapped function raises exceptions on failure:

```python
# ❌ Wrong - doesn't raise, circuit never counts it
def my_api_call():
    try:
        return requests.get(url)
    except:
        return None  # Silently swallows error

# ✅ Correct - raises, circuit can count it
def my_api_call():
    return requests.get(url)  # Raises on failure
```

---

## Next Steps

1. **Add to your main request handler**
2. **Configure Prometheus metrics export**
3. **Set up OpenTelemetry tracing**
4. **Enable structured logging**
5. **Test with `pytest-timeout` for realistic scenarios**
6. **Monitor with Prometheus/Grafana**

---

## Related Docs

- [Structured Logging Migration Guide](LOGGING_MIGRATION_GUIDE.md)
- [Prometheus Metrics Guide](../metrics/prometheus-guide.md)
- [OpenTelemetry Tracing Guide](../tracing/otel-guide.md)
- [API Reference](../../ipfs_datasets_py/ipfs_datasets_py/logic/security/llm_circuit_breaker.py)
