# OpenTelemetry Distributed Tracing Guide

**Updated:** 2026-02-25  
**Phase:** Session 84 - Observability Integration

---

## Distributed Tracing with OpenTelemetry and Jaeger

This guide covers how to use OpenTelemetry for tracing requests across your distributed system.

---

## Table of Contents

1. [Overview](#overview)
2. [Setup & Configuration](#setup--configuration)
3. [Instrument Your Application](#instrument-your-application)
4. [Trace Visualization](#trace-visualization)
5. [Advanced Patterns](#advanced-patterns)
6. [Performance Tips](#performance-tips)
7. [Troubleshooting](#troubleshooting)

---

## Overview

### What is Distributed Tracing?

Distributed tracing helps you understand the flow of a request through your system. Each request generates a **trace**, which contains multiple **spans** representing work done by different services.

```
Client Request
    ├─ API Gateway [span_1]
    │  ├─ Authenticate user [span_2]
    │  └─ Route to service [span_3]
    │
    ├─ Complaint Processor [span_4]
    │  ├─ Load complaint [span_5]
    │  ├─ Analyze with LLM [span_6]
    │  └─ Store result [span_7]
    │
    └─ Notification Service [span_8]
       └─ Send email [span_9]
```

Each span captures:
- **Duration:** How long the operation took
- **Status:** Success or error
- **Events:** Important happenings (state changes, milestones)
- **Links:** Relationships to other spans
- **Attributes:** Metadata (user_id, component, etc.)

---

## Setup & Configuration

### Step 1: Initialize OpenTelemetry

```python
from ipfs_datasets_py.logic.observability.otel_integration import (
    setup_otel_tracer,
)

# Initialize at application startup
tracer = setup_otel_tracer("complaint-generator")
```

### Step 2: Create Root Span for Each Request

```python
def handle_request(request_data):
    """Process request with tracing."""
    tracer = get_otel_tracer()
    
    # Create root span for entire request
    with tracer.span_context("handle_request", {
        "request_id": request_data.get("id"),
        "user_id": request_data.get("user_id"),
    }) as root_span:
        # All child spans are automatically linked
        process_complaint(request_data)
```

### Step 3: Wire Up Services

```python
# service_a.py
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer

def process_complaint(complaint_id):
    tracer = get_otel_tracer()
    
    # This becomes a child span of the parent context
    with tracer.span_context("process_complaint") as span:
        # This span is automatically linked to the parent
        tracer.set_span_attribute(span, "complaint_id", complaint_id)
        
        # Do work...
        analyze_complaint(complaint_id)
```

---

## Instrument Your Application

### Pattern 1: Simple Operations

```python
def fetch_user(user_id):
    tracer = get_otel_tracer()
    
    with tracer.span_context("fetch_user") as span:
        tracer.set_span_attribute(span, "user_id", user_id)
        
        # Do the work
        user = database.get_user(user_id)
        
        # Record the result
        tracer.set_span_attribute(span, "user_found", user is not None)
        return user
```

### Pattern 2: With Error Handling

```python
def validate_complaint(complaint):
    tracer = get_otel_tracer()
    
    with tracer.span_context("validate_complaint") as span:
        try:
            tracer.record_event(span, EventType.LOG_ENTRY, {
                "action": "validation_started",
            })
            
            # Validation logic
            if not complaint.get("id"):
                raise ValueError("Missing complaint ID")
            
            tracer.record_event(span, EventType.LOG_ENTRY, {
                "action": "validation_succeeded",
            })
            return True
            
        except ValueError as e:
            # Record error in span
            tracer.record_error(span, str(e), "ValueError")
            tracer.record_event(span, EventType.ERROR, {
                "error_message": str(e),
            })
            raise
```

### Pattern 3: Multi-Step Operations

```python
def process_with_multiple_steps(data):
    tracer = get_otel_tracer()
    
    with tracer.span_context("multi_step_process") as parent:
        # Step 1: Load
        with tracer.span_context("load_data") as step1:
            time.sleep(0.1)
            tracer.record_event(step1, EventType.LOG_ENTRY, {"step": 1})
        
        # Step 2: Transform
        with tracer.span_context("transform_data") as step2:
            time.sleep(0.2)
            tracer.record_event(step2, EventType.LOG_ENTRY, {"step": 2})
        
        # Step 3: Validate
        with tracer.span_context("validate_data") as step3:
            time.sleep(0.05)
            tracer.record_event(step3, EventType.LOG_ENTRY, {"step": 3})
        
        tracer.record_event(parent, EventType.LOG_ENTRY, {
            "status": "all_steps_completed",
        })
```

### Pattern 4: Conditional Tracing

```python
def call_external_service(endpoint, with_trace=True):
    tracer = get_otel_tracer()
    
    if with_trace:
        ctx = tracer.span_context("external_call", {"endpoint": endpoint})
    else:
        # No-op context manager
        from contextlib import nullcontext
        ctx = nullcontext()
    
    with ctx as span:
        result = requests.get(endpoint)
        if span:
            tracer.set_span_attribute(span, "status_code", result.status_code)
        return result
```

### Pattern 5: Integration with Circuit Breaker

```python
def protected_external_call():
    tracer = get_otel_tracer()
    cb = get_circuit_breaker("external_api")
    
    with tracer.span_context("external_call") as span:
        try:
            # Record the attempt
            tracer.record_event(span, EventType.CIRCUIT_BREAKER_CALL, {
                "component": "external_api",
            })
            
            # Call through circuit breaker
            result = cb.call(external_api.get_data)
            
            # Record success
            tracer.set_span_attribute(span, "status", "success")
            return result
            
        except CircuitBreakerOpenError:
            # Record CB trip
            tracer.record_event(span, EventType.CIRCUIT_BREAKER_STATE_CHANGE, {
                "state": "open",
            })
            tracer.set_span_attribute(span, "status", "circuit_open")
            raise
```

---

## Trace Visualization

### Export to Jaeger

```python
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer

# After your request completes
tracer = get_otel_tracer()

# Export completed traces as Jaeger JSON
jaeger_json = tracer.export_jaeger_format()
print(jaeger_json)

# In production, send to Jaeger collector:
import requests
requests.post(
    "http://jaeger-collector:14268/api/traces",
    json=json.loads(jaeger_json)
)
```

### Jaeger Docker Setup

```yaml
version: '3'
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # UI
      - "14268:14268"  # Collector
      - "14250:14250"  # gRPC
    environment:
      - COLLECTOR_ZIPKIN_HOST_PORT=:9411

  app:
    build: .
    environment:
      - JAEGER_ENDPOINT=http://jaeger:14268/api/traces
    depends_on:
      - jaeger
```

### FastAPI Integration

```python
from fastapi import FastAPI, Request
from ipfs_datasets_py.logic.observability.otel_integration import (
    setup_otel_tracer,
    get_otel_tracer,
)

app = FastAPI()
tracer = setup_otel_tracer("complaint-generator")

@app.middleware("http")
async def tracing_middleware(request: Request, call_next):
    """Trace all requests automatically."""
    tracer = get_otel_tracer()
    
    # Create root span for request
    with tracer.span_context("http_request", {
        "method": request.method,
        "path": request.url.path,
        "query": str(request.url.query),
    }) as span:
        response = await call_next(request)
        tracer.set_span_attribute(span, "status_code", response.status_code)
        return response

@app.post("/complaints")
async def create_complaint(data: dict):
    """Create complaint - automatically traced by middleware."""
    tracer = get_otel_tracer()
    
    # This becomes a child of the HTTP request span
    with tracer.span_context("create_complaint") as span:
        tracer.set_span_attribute(span, "complaint_type", data.get("type"))
        
        # Process...
        result = save_complaint(data)
        
        tracer.set_span_attribute(span, "complaint_id", result["id"])
        return result

@app.get("/traces")
async def get_traces():
    """Return recent traces."""
    tracer = get_otel_tracer()
    traces = tracer.get_completed_traces()
    
    return {
        "trace_count": len(traces),
        "traces": [
            {
                "id": t.trace_id,
                "span_count": len(t.spans),
                "duration_ms": t.duration_ms(),
            }
            for t in traces[-20:]  # Last 20
        ]
    }
```

---

## Advanced Patterns

### Pattern 1: Cross-Service Context Propagation

```python
# service_a.py - Generate trace
tracer = get_otel_tracer()

def call_service_b(user_id):
    with tracer.span_context("call_service_b") as span:
        # Get current trace context
        trace_id = tracer._get_current_trace_id()
        
        # Send request with trace ID
        response = requests.post(
            "http://service-b:8000/process",
            json={"user_id": user_id},
            headers={"X-Trace-ID": trace_id},  # Pass trace ID
        )
        return response

# service_b.py - Receive and use trace
from fastapi import FastAPI, Header

app = FastAPI()
tracer = get_otel_tracer()

@app.post("/process")
async def process_user(data: dict, x_trace_id: str = Header(None)):
    """Continue the trace from service A."""
    if x_trace_id:
        # Continue existing trace
        tracer.set_trace_context(x_trace_id)
    
    with tracer.span_context("process_user") as span:
        # This spans will be part of the same trace
        result = do_work(data)
        return result
```

### Pattern 2: Record Custom Events

```python
def machine_learning_inference(text):
    tracer = get_otel_tracer()
    
    with tracer.span_context("ml_inference", {"model": "bert"}) as span:
        # Record preprocessing
        tracer.record_event(span, EventType.LOG_ENTRY, {
            "action": "preprocessing",
            "text_length": len(text),
        })
        
        preprocessed = preprocess(text)
        
        # Record model load
        tracer.record_event(span, EventType.LOG_ENTRY, {
            "action": "model_loaded",
        })
        
        model = load_model("bert")
        
        # Record inference
        tracer.record_event(span, EventType.LOG_ENTRY, {
            "action": "inference_started",
        })
        
        result = model.predict(preprocessed)
        
        # Record result
        tracer.record_event(span, EventType.LOG_ENTRY, {
            "action": "inference_completed",
            "result_type": str(type(result)),
        })
        
        return result
```

### Pattern 3: Performance Profiling

```python
def slow_operation(iterations):
    tracer = get_otel_tracer()
    
    with tracer.span_context("slow_operation") as parent:
        for i in range(iterations):
            with tracer.span_context(f"iteration_{i}") as child_span:
                time_start = time.time()
                
                # Do work
                do_expensive_work()
                
                duration = time.time() - time_start
                tracer.set_span_attribute(child_span, "duration_ms", duration * 1000)
```

---

## Performance Tips

### 1. Sampling

```python
# Only trace 10% of requests in production
import random

def should_trace():
    return random.random() < 0.1

def request_handler():
    tracer = get_otel_tracer()
    
    if should_trace():
        with tracer.span_context("request"):
            handle_request()
    else:
        handle_request()
```

### 2. Span Limits

```python
# Limit number of completed traces in memory
tracer = OTelTracer("service")
# max_completed_traces defaults to 100
# Adjust based on your memory budget
```

### 3. Batch Export

```python
# Instead of exporting every trace
# Collect and export in batches

batch_size = 10
batch = []

def export_batch():
    jaeger_json = tracer.export_jaeger_format()
    requests.post(JAEGER_URL, json=json.loads(jaeger_json))

def handle_trace_completion():
    global batch
    batch.append(tracer.get_completed_traces()[-1])
    
    if len(batch) >= batch_size:
        export_batch()
        batch = []
```

---

## Troubleshooting

### No Traces Appearing in Jaeger

1. Check tracer initialization: `setup_otel_tracer("service")`
2. Verify spans are being created: Check logs
3. Export format: Validate Jaeger JSON structure
4. Network: Check Jaeger collector is accessible

### Traces Missing Spans

1. Ensure parent span exists before creating child
2. Check trace ID propagation
3. Verify span context managers are properly nested

### Memory Usage High

1. Reduce `max_completed_traces` limit
2. Implement sampling (trace 10% instead of 100%)
3. Export and clear completed traces more frequently

---

## Best Practices

### 1. Always Include Identifiers

```python
# Always include request/user/object IDs
with tracer.span_context("operation") as span:
    tracer.set_span_attribute(span, "request_id", request_id)
    tracer.set_span_attribute(span, "user_id", user_id)
    tracer.set_span_attribute(span, "object_id", object_id)
```

### 2. Use Meaningful Names

```python
# ✅ Good
tracer.span_context("load_user_from_db")
tracer.span_context("validate_email_format")
tracer.span_context("call_payment_processor")

# ❌ Bad
tracer.span_context("do_thing")
tracer.span_context("step_1")
tracer.span_context("operation")
```

### 3. Record Errors Consistently

```python
with tracer.span_context("operation") as span:
    try:
        do_work()
    except CustomError as e:
        # Always record the error
        tracer.record_error(span, str(e), "CustomError")
        raise
```

### 4. Reference Related Spans

```python
# Link related operations
with tracer.span_context("retry_attempt_1") as span1:
    # ...
    
with tracer.span_context("retry_attempt_2") as span2:
    # Attempt 2 is related to attempt 1
    tracer.set_span_attribute(span2, "previous_attempt", span1.span_id)
```

---

## Related Documentation

- [Prometheus Metrics Guide](prometheus-guide.md)
- [Logging Migration Guide](LOGGING_MIGRATION_GUIDE.md)
- [Circuit Breaker Integration](CIRCUIT_BREAKER_GUIDE.md)
- [OpenTelemetry Docs](https://opentelemetry.io/)
- [Jaeger Docs](https://www.jaegertracing.io/)
