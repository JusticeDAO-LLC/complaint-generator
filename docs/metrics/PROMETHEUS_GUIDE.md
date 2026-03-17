# Prometheus Metrics Guide

**Updated:** 2026-02-25  
**Phase:** Session 84 - Advanced Observability

---

## Building and Exposing Prometheus Metrics

This guide shows how to integrate Prometheus metrics export into your application's HTTP server and monitoring stack.

---

## Table of Contents

1. [Basic Setup](#basic-setup)
2. [FastAPI Integration](#fastapi-integration)
3. [Metrics Endpoints](#metrics-endpoints)
4. [Prometheus Scraping](#prometheus-scraping)
5. [Grafana Dashboards](#grafana-dashboards)
6. [Alerting Rules](#alerting-rules)
7. [Best Practices](#best-practices)

---

## Basic Setup

### Step 1: Initialize Collector

```python
from ipfs_datasets_py.logic.observability.metrics_prometheus import (
    get_prometheus_collector,
)

# Get the global singleton
metrics = get_prometheus_collector()

# Or create custom instances
from ipfs_datasets_py.logic.observability.metrics_prometheus import (
    PrometheusMetricsCollector
)
custom_metrics = PrometheusMetricsCollector(max_latency_samples=500)
```

### Step 2: Record Metrics Throughout Your App

```python
def process_request(request_id, data):
    metrics = get_prometheus_collector()
    
    import time
    start = time.time()
    
    try:
        # Process the request
        result = handle_data(data)
        elapsed = time.time() - start
        
        # Record success
        metrics.record_circuit_breaker_call(
            "data_processor",
            elapsed,
            success=True
        )
    except Exception as e:
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call(
            "data_processor",
            elapsed,
            success=False
        )
        raise
```

---

## FastAPI Integration

### Expose Metrics Endpoint

```python
from fastapi import FastAPI
from ipfs_datasets_py.logic.observability.metrics_prometheus import (
    get_prometheus_collector,
)

app = FastAPI()

@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus scrape endpoint."""
    metrics = get_prometheus_collector()
    prometheus_text = metrics.export_prometheus_format()
    return prometheus_text

# Content-Type is important for Prometheus
@app.get("/metrics", response_class="text/plain")
async def metrics_endpoint():
    metrics = get_prometheus_collector()
    return metrics.export_prometheus_format()
```

### Middleware to Track All Requests

```python
from fastapi import FastAPI, Request
from ipfs_datasets_py.logic.observability.metrics_prometheus import (
    get_prometheus_collector,
)
import time

app = FastAPI()
metrics = get_prometheus_collector()

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Track all requests."""
    start = time.time()
    
    # Record which component handled this
    component = f"{request.method}_{request.url.path}"
    
    try:
        response = await call_next(request)
        elapsed = time.time() - start
        
        # Record success
        success = 200 <= response.status_code < 400
        metrics.record_circuit_breaker_call(component, elapsed, success=success)
        
        return response
    except Exception as e:
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call(component, elapsed, success=False)
        raise
```

### Complete Example

```python
from fastapi import FastAPI, HTTPException
from ipfs_datasets_py.logic.observability.metrics_prometheus import (
    get_prometheus_collector,
)
from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    get_circuit_breaker,
    CircuitBreakerOpenError,
)

app = FastAPI()
metrics = get_prometheus_collector()

@app.post("/process")
async def process_data(data: dict):
    """Process data with circuit breaker and metrics."""
    component = "data_processor"
    import time
    start = time.time()
    
    cb = get_circuit_breaker(component)
    
    try:
        # Process through circuit breaker
        def _process():
            return process_with_external_service(data)
        
        result = cb.call(_process)
        elapsed = time.time() - start
        
        # Record success
        metrics.record_circuit_breaker_call(component, elapsed, success=True)
        metrics.record_circuit_breaker_state(component, "closed")
        
        return {"status": "success", "result": result}
        
    except CircuitBreakerOpenError:
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call(component, elapsed, success=False)
        metrics.record_circuit_breaker_state(component, "open")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return metrics.export_prometheus_format()

@app.get("/health/metrics")
async def metrics_health():
    """Health check with current metrics summary."""
    components = metrics.get_components()
    stats = {
        name: metrics.get_metrics_summary(name)
        for name in components
    }
    return stats
```

---

## Metrics Endpoints

### JSON Health Check Endpoint

```python
@app.get("/health/metrics")
async def metrics_health():
    """Return metrics as JSON for monitoring."""
    metrics = get_prometheus_collector()
    components = metrics.get_components()
    
    if not components:
        return {"healthy": True, "components": {}}
    
    health = {
        "healthy": True,
        "components": {},
        "timestamp": time.time(),
    }
    
    for component in components:
        summary = metrics.get_metrics_summary(component)
        health["components"][component] = {
            "total_calls": summary["total_calls"],
            "success_rate": summary["success_rate"],
            "failure_rate": summary["failure_rate"],
            "avg_latency_ms": summary["avg_latency"] * 1000,
            "p99_latency_ms": summary["latency_percentiles"]["p99"] * 1000,
        }
        
        # Mark as unhealthy if failure rate > 50%
        if summary["failure_rate"] > 50.0:
            health["healthy"] = False
    
    return health
```

### Prometheus Query Endpoint

```python
@app.get("/prometheus/query")
async def query_metrics(q: str = ""):
    """Query metrics by component name."""
    metrics = get_prometheus_collector()
    
    if not q:
        # Return all
        components = list(metrics.get_components())
    else:
        # Filter by name pattern
        components = [c for c in metrics.get_components() if q in c]
    
    results = {}
    for component in components:
        results[component] = metrics.get_metrics_summary(component)
    
    return results
```

---

## Prometheus Scraping

### prometheus.yml Configuration

```yaml
# Add to your docker-compose.yml or prometheus.yml

global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'mcp_server'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 5s
    scrape_timeout: 10s
```

### Docker Compose Setup

```yaml
version: '3.8'

services:
  app:
    image: complaint-generator:latest
    ports:
      - "8000:8000"
    environment:
      - LOG_LEVEL=info
    depends_on:
      - prometheus

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'

volumes:
  prometheus_data:
```

---

## Grafana Dashboards

### Create a Dashboard

1. **Login to Grafana** (default: http://localhost:3000)
2. **Create new dashboard**
3. **Add panels** using the queries below

### Sample Queries

#### Circuit Breaker Success Rate Over Time

```
circuit_breaker_failure_rate{job="mcp_server"}
```

#### Latency P95 by Component

```
circuit_breaker_latency_seconds{component=~".+",quantile="0.95"}
```

#### Total Calls Gauge

```
circuit_breaker_calls_total{job="mcp_server"}
```

#### Rate of Failures (per minute)

```
rate(circuit_breaker_calls_failed{job="mcp_server"}[1m])
```

### Dashboard JSON

```json
{
  "dashboard": {
    "title": "MCP++ Observability Dashboard",
    "panels": [
      {
        "title": "Success Rate (%)",
        "targets": [
          {
            "expr": "100 - circuit_breaker_failure_rate"
          }
        ],
        "type": "graph"
      },
      {
        "title": "P99 Latency (ms)",
        "targets": [
          {
            "expr": "circuit_breaker_latency_seconds * 1000"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Circuit Breaker State",
        "targets": [
          {
            "expr": "circuit_breaker_state"
          }
        ],
        "type": "stat"
      }
    ]
  }
}
```

---

## Alerting Rules

### alerts.yml

```yaml
groups:
  - name: mcp_alerts
    interval: 30s
    rules:
      # Alert when circuit breaker opens
      - alert: CircuitBreakerOpen
        expr: circuit_breaker_state{state="open"} > 0
        for: 1m
        annotations:
          summary: "Circuit breaker is open for {{ $labels.component }}"
          description: "Service {{ $labels.component }} has tripped its circuit breaker"

      # Alert when failure rate is high
      - alert: HighFailureRate
        expr: circuit_breaker_failure_rate > 10
        for: 5m
        annotations:
          summary: "High failure rate for {{ $labels.component }}"
          description: "{{ $labels.component }} failure rate is {{ $value }}%"

      # Alert when latency spikes
      - alert: LatencySpike
        expr: circuit_breaker_latency_seconds_avg > 1.0
        for: 5m
        annotations:
          summary: "Latency spike for {{ $labels.component }}"
          description: "Average latency is {{ $value }}s"
```

### Prometheus Configuration with Alerts

```yaml
global:
  scrape_interval: 15s

rule_files:
  - 'alerts.yml'

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']

scrape_configs:
  - job_name: 'mcp'
    static_configs:
      - targets: ['localhost:8000']
```

---

## Best Practices

### 1. Cardinality Management

**❌ DON'T:** Create metrics with user IDs or request IDs as labels

```python
# BAD: Creates unbounded cardinality
metrics.record_circuit_breaker_call(f"user_{user_id}_api", latency, success)
```

**✅ DO:** Use fixed component names

```python
# GOOD: Fixed number of components
metrics.record_circuit_breaker_call("user_api", latency, success)
```

### 2. Scrape Interval Tuning

```yaml
# For high-volume services
scrape_interval: 5s

# For low-volume services
scrape_interval: 30s

# Balanced
scrape_interval: 15s
```

### 3. Retention Policy

```yaml
# In Prometheus config
--storage.tsdb.retention.time=30d  # Keep 30 days of data
--storage.tsdb.retention.size=50GB  # Or limit by size
```

### 4. Labeling Strategy

```python
# Use consistent, meaningful labels
metrics.record_circuit_breaker_call(
    "external_payment_api",  # component name (fixed)
    latency,
    success=success
)

# Labels are added by Prometheus automatically:
# - job (from scrape_configs)
# - instance (from targets)
# - component (from code)
```

### 5. Dashboard Organization

- **Overview:** Success rate, P99 latency, circuit breaker states
- **Performance:** Latency percentiles, throughput, request rates
- **Errors:** Failure rates, error types, recovery time
- **Capacity:** Memory usage, concurrent operations, queue depth

---

## Troubleshooting

### No Metrics Appearing in Prometheus

1. Check `/metrics` endpoint returns valid Prometheus text
2. Verify scrape_interval and scrape_timeout
3. Check Prometheus logs for scrape errors
4. Ensure container/network connectivity

### Metrics Disappearing After Minutes

- Check Prometheus retention settings
- Verify TSDB has enough storage
- Check for OOMKilled processes

### High Cardinality Issues

- Audit current metric labels
- Reduce dimensionality
- Use aggregation in dashboards

---

## Next Steps

1. Deploy to Prometheus instance
2. Create Grafana dashboard from examples
3. Set up alerting rules
4. Monitor production traffic
5. Adjust thresholds based on baseline

---

## Related Documentation

- [Circuit Breaker Guide](CIRCUIT_BREAKER_GUIDE.md)
- [Logging Migration Guide](LOGGING_MIGRATION_GUIDE.md)
- [OTel Integration Guide](otel-guide.md)
