# Production Deployment Checklist for MCP++ Observability

Comprehensive guide to deploying MCP++ circuit breaker, metrics, and tracing to production environments.

## Pre-Deployment Verification (Development & Staging)

### Code Integration
- [ ] Circuit breaker initialized with `get_circuit_breaker()`
- [ ] Metrics collection with `get_prometheus_collector()`
- [ ] Tracing initialized with `get_otel_tracer()`
- [ ] All async/await patterns use same globals consistently
- [ ] Exception handling preserves exception context
- [ ] Metrics recorded for every external call (success & failure paths)
- [ ] Trace spans have meaningful operation names
- [ ] All spans explicitly call `span.end()`

### Testing
- [ ] Unit tests pass: `pytest tests/mcp/unit/ -v`
- [ ] Integration tests pass with 3 circuit breaker instances minimum
- [ ] Concurrent tests pass (20+ thread count)
- [ ] Load tests pass (>5000 ops/sec throughput)
- [ ] Memory growth tests pass (<10MB/10s at 1000 ops/sec)
- [ ] All timing-sensitive tests documented
- [ ] Failover/fallback mechanisms tested
- [ ] Error paths logged and traced

### Configuration Review

#### Circuit Breaker Settings
```
✓ failure_threshold: Check for your service SLA
  - Web APIs: 20-50 failures
  - Critical services: 5-10 failures
  
✓ timeout_seconds: Based on service recovery time
  - API latency: 1-5 seconds
  - Database: 10-30 seconds
  - External service: 30-60 seconds
  
✓ exponential_backoff: True for APIs, False for fast operations
```

#### Metrics Configuration
```
✓ Component names: Fixed, not per-request
  - Good: "api_external", "db_primary"
  - Bad: "api_user_123", "db_connection_456"
  
✓ Max latency samples: 1000 per component
✓ Export interval: Every 5-10 seconds
```

#### Tracing Configuration
```
✓ Service name: Unique, lowercase with underscores
  - Example: "mcp_plus_plus_service"
  
✓ Max completed traces: 100 buffer
✓ Export to Jaeger: Every 30 seconds
```

---

## Infrastructure Setup (Staging → Production)

### Prerequisites
- [ ] Docker engine running
- [ ] Docker Compose v2.0+
- [ ] 4GB RAM minimum
- [ ] Persistent storage for Prometheus (optional but recommended)
- [ ] Network routes configured between services

### Monitoring Stack Deployment

#### 1. Docker Compose Configuration

Create `docker-compose.yml` for full stack:

```yaml
version: '3.8'

services:
  # Prometheus for metrics
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./alerts.yml:/etc/prometheus/alerts.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    networks:
      - observability

  # Grafana for dashboards
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_INSTALL_PLUGINS=grafana-piechart-panel
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana_dashboards:/etc/grafana/provisioning/dashboards
    networks:
      - observability

  # Jaeger for distributed tracing
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "5775:5775/udp"
      - "6831:6831/udp"
      - "16686:16686"  # UI
      - "14268:14268"  # Collector HTTP
    environment:
      - COLLECTOR_ZIPKIN_HOST_PORT=:9411
    networks:
      - observability

  # AlertManager for alerting
  alertmanager:
    image: prom/alertmanager:latest
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
      - alertmanager_data:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    networks:
      - observability

volumes:
  prometheus_data:
  grafana_data:
  alertmanager_data:

networks:
  observability:
    driver: bridge
```

#### 2. Prometheus Configuration

File: `prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'production'
    service: 'mcp-plus-plus'

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - localhost:9093

rule_files:
  - 'alerts.yml'

scrape_configs:
  - job_name: 'mcp-plus-plus'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 5s
    scrape_timeout: 5s
    
  - job_name: 'prometheus-server'
    static_configs:
      - targets: ['localhost:9090']
```

#### 3. Alert Rules Configuration

File: `alerts.yml`

```yaml
groups:
  - name: circuit_breaker_alerts
    interval: 1m
    rules:
      # Alert when circuit breaker is open
      - alert: CircuitBreakerOpen
        expr: circuit_breaker_state{state="1"} > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Circuit breaker {{ $labels.component }} is OPEN"
          description: "Service {{ $labels.component }} has too many failures"
      
      # Alert on high failure rate
      - alert: HighFailureRate
        expr: circuit_breaker_failure_rate{} > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High failure rate for {{ $labels.component }}"
          description: "Failure rate is {{ $value | humanizePercentage }}"
      
      # Alert on latency spike
      - alert: LatencySpike
        expr: histogram_quantile(0.99, circuit_breaker_latency_seconds{}) > 1.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Latency spike detected for {{ $labels.component }}"
          description: "P99 latency is {{ $value }}s"
```

#### 4. AlertManager Configuration

File: `alertmanager.yml`

```yaml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: 'critical'
      group_wait: 0s
      repeat_interval: 5m

receivers:
  - name: 'default'
    # Email, webhook, etc.
    
  - name: 'critical'
    # Critical notifications (page on-call, etc.)
```

---

## Application Configuration

### FastAPI Integration

```python
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from ipfs_datasets_py.logic.observability.metrics_prometheus import (
    get_prometheus_collector,
)
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer

app = FastAPI()

# Initialize observability
metrics = get_prometheus_collector()
tracer = get_otel_tracer()

# Middleware for tracing
@app.middleware("http")
async def tracing_middleware(request, call_next):
    """Trace all requests."""
    span = tracer.start_span(f"{request.method} {request.url.path}")
    span.set_attribute("http.method", request.method)
    span.set_attribute("http.url", str(request.url))
    
    start = time.time()
    try:
        response = await call_next(request)
        elapsed = time.time() - start
        span.set_attribute("http.status_code", response.status_code)
        span.end(success=response.status_code < 400)
        return response
    except Exception as e:
        elapsed = time.time() - start
        span.record_error(e)
        span.end(success=False)
        raise

# Metrics endpoint
@app.get("/metrics", response_class=Response)
async def metrics_endpoint():
    """Prometheus metrics."""
    content = metrics.export_prometheus_format()
    return Response(content=content, media_type="text/plain; charset=utf-8")

# Health check
@app.get("/health")
async def health_check():
    """Health check with observability state."""
    return {
        "status": "healthy",
        "metrics_components": len(metrics.metrics),
        "active_traces": len(tracer.completed_traces),
    }

# Graceful shutdown
@app.on_event("shutdown")
async def shutdown_event():
    """Export final traces on shutdown."""
    jaeger_json = tracer.export_to_jaeger_json()
    # Send to Jaeger or persist
    print(f"Exported {len(tracer.completed_traces)} traces on shutdown")
```

### Circuit Breaker Configuration

```python
from ipfs_datasets_py.logic.security.llm_circuit_breaker import get_circuit_breaker
import logging

logger = logging.getLogger(__name__)

def setup_circuit_breakers():
    """Configure circuit breakers for production."""
    
    # External API calls
    api_cb = get_circuit_breaker("external_api")
    api_cb.failure_threshold = 20
    api_cb.timeout_seconds = 5
    api_cb.exponential_backoff = True
    
    # Database connections
    db_cb = get_circuit_breaker("database")
    db_cb.failure_threshold = 10
    db_cb.timeout_seconds = 30
    db_cb.exponential_backoff = False
    
    # LLM service
    llm_cb = get_circuit_breaker("llm_service")
    llm_cb.failure_threshold = 5
    llm_cb.timeout_seconds = 60
    llm_cb.exponential_backoff = True
    
    logger.info("Circuit breakers configured for production")

async def call_external_api(endpoint: str, data: dict):
    """Call external API with circuit breaker."""
    cb = get_circuit_breaker("external_api")
    metrics = get_prometheus_collector()
    
    def fallback():
        logger.warning(f"Circuit open for {endpoint}, using cached response")
        return {"cached": True, "data": None}
    
    start = time.time()
    try:
        result = cb.call(
            make_api_request,
            endpoint,
            data,
            fallback=fallback,
            timeout=10
        )
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call("external_api", elapsed, success=True)
        return result
    except Exception as e:
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call("external_api", elapsed, success=False)
        logger.error(f"API call failed: {e}")
        raise
```

---

## Monitoring and Alerting

### Grafana Dashboard Setup

1. **Access Grafana:** `http://localhost:3000`
2. **Login:** admin/admin (change password!)
3. **Add Data Source:**
   - Type: Prometheus
   - URL: `http://prometheus:9090`
   - Save & Test

4. **Create Dashboard with Panels:**

```json
{
  "dashboard": {
    "title": "MCP++ Observability",
    "panels": [
      {
        "title": "Circuit Breaker States",
        "targets": [
          {"expr": "circuit_breaker_state"}
        ]
      },
      {
        "title": "Success Rate",
        "targets": [
          {"expr": "round(sum(circuit_breaker_calls_success) / sum(circuit_breaker_calls_total) * 100, 0.1)"}
        ]
      },
      {
        "title": "Latency P99",
        "targets": [
          {"expr": "histogram_quantile(0.99, circuit_breaker_latency_seconds{})"}
        ]
      },
      {
        "title": "Failed Calls",
        "targets": [
          {"expr": "rate(circuit_breaker_calls_failed[5m])"}
        ]
      }
    ]
  }
}
```

### Logging Best Practices

```python
import logging
import json
from datetime import datetime

class StructuredFormatter(logging.Formatter):
    """Structured JSON logging for observability."""
    
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add custom attributes if present
        if hasattr(record, "circuit_breaker"):
            log_obj["circuit_breaker"] = record.circuit_breaker
        if hasattr(record, "elapsed_ms"):
            log_obj["elapsed_ms"] = record.elapsed_ms
        if hasattr(record, "trace_id"):
            log_obj["trace_id"] = record.trace_id
        
        return json.dumps(log_obj)

# Configure logging
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Usage
logger.info("API call", extra={
    "circuit_breaker": "external_api",
    "elapsed_ms": 0.05,
    "trace_id": "xyz123"
})
```

---

## Performance Tuning

### Metrics Configuration

| Setting | Default | Production |
|---------|---------|-----------|
| Scrape interval | 15s | 5-10s |
| Evaluation interval | 15s | 10-30s |
| Retention period | 15d | 30d |
| Max latency samples | 1000 | 1000 |

### Tracing Configuration

| Setting | Default | Production |
|---------|---------|-----------|
| Max completed traces | 100 | 100-500 |
| Export interval | 30s | 10-30s |
| Sample rate | 100% | 10-50% |

### Circuit Breaker Tuning

```python
# Service-specific configurations
CIRCUIT_BREAKER_CONFIG = {
    "fast_api_call": {
        "failure_threshold": 50,
        "timeout_seconds": 2,
        "exponential_backoff": True,
    },
    "database": {
        "failure_threshold": 20,
        "timeout_seconds": 30,
        "exponential_backoff": False,
    },
    "payment_service": {
        "failure_threshold": 5,
        "timeout_seconds": 60,
        "exponential_backoff": True,
    },
}

def setup_circuit_breakers(config_dict):
    for service_name, config in config_dict.items():
        cb = get_circuit_breaker(service_name)
        for key, value in config.items():
            setattr(cb, key, value)
```

---

## Operational Runbooks

### Checking System Health

```bash
# Prometheus health
curl -s http://localhost:9090/-/healthy

# Jaeger health
curl -s http://localhost:16686/health

# Application metrics endpoint
curl -s http://localhost:8000/metrics | head -20

# Check circuit breaker state
curl -s http://localhost:8000/metrics | grep circuit_breaker_state
```

### Investigating High Latency

```python
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector

metrics = get_prometheus_collector()

for component in sorted(metrics.metrics.keys()):
    summary = metrics.get_metrics_summary(component)
    if summary['latency_percentiles']['p99'] > 1.0:  # >1 second
        print(f"\n⚠️ {component}:")
        print(f"   P99: {summary['latency_percentiles']['p99']*1000:.0f}ms")
        print(f"   Total calls: {summary['total_calls']}")
        print(f"   Success rate: {summary['success_rate']:.1f}%")
```

### Investigating Circuit Breaker Issues

```python
from ipfs_datasets_py.logic.security.llm_circuit_breaker import get_circuit_breaker

for service_name in ["api", "database", "llm"]:
    try:
        cb = get_circuit_breaker(service_name)
        print(f"\n{service_name}:")
        print(f"  State: {cb.state.value}")
        print(f"  Failures: {cb.failure_count}/{cb.failure_threshold}")
        print(f"  Last failure: {cb.last_failure_time}")
        print(f"  Timeout: {cb.timeout_seconds}s")
    except Exception as e:
        print(f"  Error: {e}")
```

---

## Security Considerations

### Metrics Endpoint Protection

```python
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from fastapi import Depends, HTTPException

security = HTTPBearer()

@app.get("/metrics", response_class=Response)
async def metrics_endpoint(credentials: HTTPAuthCredentials = Depends(security)):
    """Protected metrics endpoint."""
    if credentials.credentials != os.getenv("METRICS_TOKEN"):
        raise HTTPException(status_code=403)
    
    content = metrics.export_prometheus_format()
    return Response(content=content, media_type="text/plain; charset=utf-8")
```

### Jaeger API Security

- Restrict access to Jaeger UI (16686) to internal networks
- Use network policies/firewall rules
- Consider reverse proxy with authentication

### Sensitive Data in Traces

```python
# ❌ WRONG: Traces might contain passwords
span.set_attribute("user_input", user_password)

# ✅ CORRECT: Sanitize sensitive data
span.set_attribute("operation", "password_reset")
span.set_attribute("user_id", user_id)  # Not password!
```

---

## Rollback Procedures

### If Observability Breaks Production

1. **Disable tracing collection** (fastest recovery):
   ```python
   tracer = get_otel_tracer()
   tracer.completed_traces.clear()  # Clear buffer
   # New traces won't block requests
   ```

2. **Disable metrics collection** (if causing issues):
   ```python
   metrics = get_prometheus_collector()
   metrics.metrics.clear()  # Clear all metrics
   # Metrics endpoint returns empty
   ```

3. **Revert circuit breaker config**:
   ```python
   get_circuit_breaker("service").failure_threshold = 50
   get_circuit_breaker("service").timeout_seconds = 10
   # Reset to defaults
   ```

4. **Restart application** (full reset):
   ```bash
   docker-compose restart mcp-plus-plus-app
   ```

---

## Post-Deployment Verification

- [ ] Prometheus scraping metrics successfully (`/targets` shows UP)
- [ ] Grafana dashboards showing data
- [ ] AlertManager receiving alerts
- [ ] Jaeger showing traces for requests
- [ ] Circuit breaker transitions working (test with manual failure)
- [ ] Memory stable at 50-200MB
- [ ] Latency <5ms for metric operations
- [ ] Throughput >10,000 ops/sec
- [ ] No errors in application logs

## Success Indicators

✅ **Metrics working:**
- Prometheus scrape succeeds every 5s
- Grafana shows success rate, latency, errors
- Cardinality <50 components

✅ **Tracing working:**
- Jaeger UI shows traces for each request
- Trace completion time <100ms per request
- Max 100 traces buffered at any time

✅ **Alerts working:**
- Test alert triggers without false positives
- Critical alerts page on-call engineer
- Alert resolution tracked

✅ **Performance:**
- No memory growth over 1 hour baseline
- <5ms latency for metric operations
- <10ms latency for trace operations
- Application throughput unchanged

---

**For questions, refer to:**
- [Prometheus Guide](docs/metrics/PROMETHEUS_GUIDE.md)
- [OpenTelemetry Guide](docs/tracing/OTEL_GUIDE.md)
- [Troubleshooting Guide](docs/observability/TROUBLESHOOTING.md)
