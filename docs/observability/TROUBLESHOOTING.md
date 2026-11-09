# Observability Troubleshooting Guide

## Overview

This guide helps diagnose and resolve common issues with Prometheus metrics, OpenTelemetry tracing, circuit breaker integration, and the complete observability stack.

**Quick Reference:**
- [Long-Running Automation Stalls](#long-running-automation-stalls)
- [Metrics Not Appearing](#metrics-not-appearing)
- [High Memory Usage](#high-memory-usage)
- [Missing Traces](#missing-traces)
- [Circuit Breaker Issues](#circuit-breaker-issues)
- [Integration Problems](#integration-problems)

---

## Long-Running Automation Stalls

### Symptom: a daemon says running but work no longer advances

Start with the daemon's status command. Do not infer liveness from the presence
of a PID file alone, and do not infer a stall from a stable cycle count alone.
UI optimization and Gmail import cycles may legitimately spend their configured
poll interval in `sleeping`; error retries may spend the configured retry
interval in a backoff phase.

```bash
# Refactor supervisor
python scripts/refactor_agent_supervisor.py status

# UI optimizer (use the same --artifact-root if it was overridden at start)
python -m complaint_generator.ui_optimizer_daemon status \
  --user-id <user-id> --json

# Gmail/DuckDB importer (use the same --duckdb-output-dir if overridden)
python scripts/gmail_duckdb_daemon.py status \
  --user-id <user-id> --json
```

Read these fields together:

- Common fields: `status`, `pid`, `updated_at`, `artifacts`, and `last_error`.
- Refactor supervisor: `pid_alive`, `heartbeat_age_seconds`, `counts.queue`,
  `counts.todo`, `cycle`, `last_seed`, `next_tasks`, `parallel_scheduler`, and
  `parallel_lanes`. Its status command changes a nominal running state to
  `stale` when its PID file no longer identifies a live process.
- UI optimizer: top-level `running`, then `status_payload.phase`,
  `phase_elapsed_seconds`, `cycle_count`, `consecutive_errors`, `last_result`,
  and `recommendation_coverage`.
- Gmail importer: top-level `running`, then `status_payload.phase`,
  `cycle_count`, `consecutive_errors`, `last_result`, and `progress_summary`.
  Compare `progress_updated_at`, `checkpoint_updated_at`, `eml_file_count`, and
  `estimated_remaining_messages` across checks.

The refactor supervisor queue is
`data/refactor_supervisor/refactor_taskboard.duckdb`. UI and Gmail daemons do not
use that queue. UI's latest completed cycle is under
`status_payload.last_result`; Gmail's resumable work is in the checkpoint and
progress files named by `status_payload.artifacts`. The agentic scraper is an
in-process component and has no standalone PID, log, status, or queue file; the
host application must persist `ScraperDaemon.status_payload()` if it needs a
durable handoff.

### Locate logs and verify the process

Prefer the paths reported in `artifacts` because command-line overrides replace
the defaults. Without overrides, the files are:

| Automation | PID file | Status file | Log file | Queue/resume state |
|------------|----------|-------------|----------|--------------------|
| Refactor supervisor | `data/refactor_supervisor/refactor_supervisor.pid` | `data/refactor_supervisor/refactor_supervisor_status.json` | `data/refactor_supervisor/refactor_supervisor.log` | `data/refactor_supervisor/refactor_taskboard.duckdb` |
| UI optimizer | `artifacts/ui-optimizer-daemon/<user-id>/ui_optimizer_daemon.pid` | Same directory, `ui_optimizer_daemon_status.json` | Same directory, `ui_optimizer_daemon.log` | No queue; `artifacts.cycle_manifest_path` identifies the last cycle |
| Gmail/DuckDB importer | `output/email_duckdb/<user-id>/gmail_duckdb_daemon.pid` | Same directory, `gmail_duckdb_daemon_status.json` | Same directory, `gmail_duckdb_daemon.log` | No queue; use `artifacts.checkpoint_path` and `artifacts.progress_path` |

Background `start` commands redirect process output to these log files.
Foreground `run` commands write process output to the controlling terminal, so
an empty or absent log file is not evidence of a stalled foreground process.

Inspect the exact PID and recent log without changing runtime state:

```bash
PID_FILE='<path reported as artifacts.pid_file>'
LOG_FILE='<path reported as artifacts.log_file>'

if test -s "$PID_FILE"; then
  DAEMON_PID="$(tr -d '[:space:]' < "$PID_FILE")"
  ps -p "$DAEMON_PID" -o pid=,ppid=,stat=,etime=,args=
fi
tail -n 200 "$LOG_FILE"
```

Treat a status snapshot as stale when the recorded PID is not live, or when a
live matching process has stopped refreshing status beyond its expected
heartbeat/operation window. UI and Gmail status writers refresh roughly every
15 seconds. For the refactor supervisor, use its reported
`heartbeat_age_seconds` and configured supervisor interval. A long-running
implementation or validation may legitimately exceed a normal refill interval,
so also inspect the task/lane log and active worker before recovery.

Never send a signal based only on an old numeric PID: operating systems can
reuse PIDs. Confirm that the command printed by `ps` belongs to the expected
daemon, user ID, state directory, and artifact root.

### Clean recovery for a stale daemon

1. Save the current status and the last 200 log lines for diagnosis.
2. Request a clean stop with the daemon's CLI.
3. Confirm the CLI reports the process stopped and `ps` no longer shows the
   expected daemon. The refactor `stop` command also stops its managed worker.
4. Only after confirming no matching process is alive, remove a malformed or
   dead-process PID file if the daemon did not clean it up itself.
5. Restart with the original root/path and scheduling options, then verify that
   `updated_at` advances and `last_error` is clear or understood.

```bash
# Refactor supervisor
python scripts/refactor_agent_supervisor.py stop
python scripts/refactor_agent_supervisor.py start
python scripts/refactor_agent_supervisor.py status

# UI optimizer
python -m complaint_generator.ui_optimizer_daemon stop \
  --user-id <user-id> --json
python -m complaint_generator.ui_optimizer_daemon start \
  --user-id <user-id> <original-start-options> --json

# Gmail/DuckDB importer
python scripts/gmail_duckdb_daemon.py stop --user-id <user-id> --json
python scripts/gmail_duckdb_daemon.py start \
  --user-id <user-id> <original-source-and-auth-options> --json
```

For a parallel refactor scheduler, use
`python scripts/refactor_agent_supervisor.py stop-parallel` and restart with the
original `start-parallel` options. Do not run the serial `start` and
`start-parallel` recovery paths simultaneously unless the deployment was
deliberately configured that way.

### Recover a stale refactor queue task

A `counts.queue.running` value greater than zero is not sufficient evidence of
a stale task. First establish all of the following:

- the supervisor or lane that owned the row is stopped;
- no implementation, validation, or merge process is still using the task's
  worktree;
- the task's `updated_at` is older than the applicable implementation timeout;
- its `assigned_worker` no longer corresponds to a live worker; and
- the lane log and `data/refactor_supervisor/events.jsonl` show no new progress.

List running queue rows read-only. This uses the same task type filter as the
refactor supervisor and prints ISO timestamps so age is easy to assess:

```bash
PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python - <<'PY'
from datetime import UTC, datetime
from ipfs_accelerate_py.p2p_tasks import TaskQueue

queue = TaskQueue("data/refactor_supervisor/refactor_taskboard.duckdb")
try:
    for item in queue.list(
        status="running", limit=1000, task_types=("codex.todo_bundle",)
    ):
        updated = datetime.fromtimestamp(float(item["updated_at"]), tz=UTC)
        print(item["task_id"], item["assigned_worker"], updated.isoformat())
finally:
    queue.close()
PY
```

The implementation supervisor repairs dead active-execution markers during its
next maintenance cycle. Prefer a clean stop/start and recheck status before
manually releasing a queue row. If the row remains `running` after the owning
worker is confirmed dead, release exactly that row back to `queued` with its
recorded worker ID:

```bash
STALE_TASK_ID='<exact task_id from the read-only listing>'
STALE_WORKER_ID='<exact assigned_worker from the listing>'
export STALE_TASK_ID STALE_WORKER_ID

PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python - <<'PY'
import os
from ipfs_accelerate_py.p2p_tasks import TaskQueue

task_id = os.environ["STALE_TASK_ID"]
worker_id = os.environ["STALE_WORKER_ID"]
queue = TaskQueue("data/refactor_supervisor/refactor_taskboard.duckdb")
try:
    before = queue.get(task_id)
    if not before:
        raise SystemExit(f"task not found: {task_id}")
    if before.get("status") != "running":
        raise SystemExit(f"task is no longer running: {before.get('status')}")
    if before.get("assigned_worker") != worker_id:
        raise SystemExit("assigned worker changed; refusing to release")
    queue.release(
        task_id=task_id,
        worker_id=worker_id,
        reason="operator_recovery_after_confirmed_dead_worker",
    )
    after = queue.get(task_id)
    if not after or after.get("status") != "queued":
        raise SystemExit("release did not transition the task to queued")
    print(f"released {task_id} from {worker_id}; status=queued")
finally:
    queue.close()
PY
```

Release one verified row at a time. Do not edit the DuckDB file directly, do not
delete it, and do not release a row owned by a live worker; doing so can execute
the same task twice. Restart the same scheduler mode that previously owned the
task and confirm that `queue_counts.running`, `queue_counts.queued`, the task's
`updated_at`, and the relevant lane log begin moving again.

---

## Metrics Not Appearing

### Symptom: Prometheus scrape returns no metrics

**Root Causes & Solutions:**

#### 1. Collector Not Initialized

```python
# ❌ WRONG: Assuming global collector exists
from ipfs_datasets_py.logic.observability.metrics_prometheus import PrometheusMetricsCollector
metrics = PrometheusMetricsCollector()  # New instance, not globally registered

# ✅ CORRECT: Use singleton getter
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector
metrics = get_prometheus_collector()  # Returns global instance
```

**Diagnosis:**
```bash
# Check if collector registered
python -c "
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector
collector = get_prometheus_collector()
print(f'Registered components: {list(collector.metrics.keys())}')
"
```

#### 2. Records Not Being Made

```python
# ❌ WRONG: Forgetting to record metrics
def api_endpoint():
    result = service.call()
    return result

# ✅ CORRECT: Record the call
def api_endpoint():
    start = time.time()
    try:
        result = service.call()
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call("api", elapsed, success=True)
        return result
    except Exception as e:
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call("api", elapsed, success=False)
        raise
```

**Diagnosis:**
```python
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector

metrics = get_prometheus_collector()
metrics.record_circuit_breaker_call("test_component", 0.05, success=True)

# Check if recorded
for metric in metrics.get_metrics("test_component").values():
    print(f"Metric: {metric['name']}, Value: {metric['value']}")
```

#### 3. Prometheus Endpoint Configuration Issue

```python
# ❌ WRONG: Endpoint returns JSON metrics
@app.get("/metrics")
def metrics():
    metrics_obj = get_prometheus_collector()
    return metrics_obj.metrics  # Returns dict

# ✅ CORRECT: Endpoint returns Prometheus text format
@app.get("/metrics")
def metrics_endpoint():
    metrics_obj = get_prometheus_collector()
    return PlainTextResponse(metrics_obj.export_prometheus_format())
```

**Diagnosis:**
```bash
# Test endpoint directly
curl -s http://localhost:8000/metrics

# Should return Prometheus format:
# # HELP circuit_breaker_calls_total Total calls to circuit breaker
# # TYPE circuit_breaker_calls_total counter
# circuit_breaker_calls_total{component="api"} 42.0
```

#### 4. Missing Content-Type Header

```python
from fastapi import Response

# ❌ WRONG: Default content-type is application/json
@app.get("/metrics")
def metrics():
    return metrics_obj.export_prometheus_format()

# ✅ CORRECT: Set Prometheus text format
@app.get("/metrics")
def metrics():
    content = metrics_obj.export_prometheus_format()
    return Response(content=content, media_type="text/plain; charset=utf-8")
```

**Diagnosis:**
```bash
# Check content-type
curl -i http://localhost:8000/metrics | head -20
# Should show: Content-Type: text/plain; charset=utf-8
```

**Resolution Checklist:**
- [ ] `get_prometheus_collector()` returns same instance everywhere
- [ ] Metrics recorded after every service call with elapsed time
- [ ] Endpoint returns response with `media_type="text/plain"`
- [ ] Prometheus scrape interval matches update frequency
- [ ] Firewall allows Prometheus to reach endpoint

**Example Solution:**
```python
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector

app = FastAPI()

@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Prometheus metrics endpoint."""
    collector = get_prometheus_collector()
    return collector.export_prometheus_format()

# In request handlers:
@app.post("/api/call")
async def handle_call(request):
    metrics = get_prometheus_collector()
    start = time.time()
    try:
        result = await service.call()
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call("api", elapsed, success=True)
        return result
    except Exception as e:
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call("api", elapsed, success=False)
        raise
```

---

## High Memory Usage

### Symptom: Memory grows unbounded, reaches 1GB+

**Root Causes & Solutions:**

#### 1. Unchecked Latency History

```python
# ❌ WRONG: Latencies list never cleared
collector.latency_records["service"].append(0.001)  # Growth: 100k entries/hour

# ✅ CORRECT: Has max size limit
# PrometheusMetricsCollector internally maintains max_latency_samples = 1000
```

**Diagnosis:**
```python
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector

metrics = get_prometheus_collector()
for component, records in metrics.latency_records.items():
    print(f"{component}: {len(records)} latency samples")
    if len(records) > 1000:
        print(f"  ⚠️ WARN: Growing unbounded!")
```

#### 2. Unlimited Trace Buffering

```python
# ❌ WRONG: All traces kept indefinitely
traces_buffer = []  # No size limit

# ✅ CORRECT: Limited with deque
from collections import deque
traces_buffer = deque(maxlen=100)  # Keep only 100 recent traces
```

**Diagnosis:**
```python
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer

tracer = get_otel_tracer()
completed_traces = tracer.completed_traces
print(f"Completed traces in buffer: {len(completed_traces)}")
if len(completed_traces) > 100:
    print("⚠️ Trace buffer may be unbounded!")
```

#### 3. Component Name Cardinality

```python
# ❌ WRONG: Creating component name per user
for user_id in user_ids:
    metrics.record_circuit_breaker_call(f"api_user_{user_id}", 0.05, success=True)
# Results in 1M unique components!

# ✅ CORRECT: Fixed component names with labels
metrics.record_circuit_breaker_call("api", 0.05, success=True, user_id=user_id)
# Or: metrics.record_circuit_breaker_call("api_external", 0.05, success=True)
```

**Diagnosis:**
```python
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector

metrics = get_prometheus_collector()
num_components = len(metrics.metrics)
print(f"Unique components: {num_components}")
if num_components > 50:
    print("⚠️ High cardinality! Components created per-request?")
    for comp in list(metrics.metrics.keys())[:10]:
        print(f"  - {comp}")
```

#### 4. Shared State Growing

```python
# ❌ WRONG: Thread accumulation in custom logging
import logging
active_threads = []  # Thread references never removed

# ✅ CORRECT: Clean up references
active_threads = []
# Use WeakSet for threads that auto-cleanup when thread exits
from weakref import WeakSet
active_threads = WeakSet()
```

**Resolution Checklist:**
- [ ] Latency records capped at 1000 per component
- [ ] Completed traces limited to 100 maximum
- [ ] Component names are fixed, not per-request
- [ ] No unbounded lists/dicts growing over time
- [ ] Memory monitored with: `psutil.Process().memory_info().rss / 1e6` MB

**Example Memory Monitoring:**
```python
import psutil
import time
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector

def monitor_memory(interval_seconds=5, duration_seconds=60):
    """Monitor memory growth."""
    start_time = time.time()
    process = psutil.Process()
    
    while time.time() - start_time < duration_seconds:
        metrics = get_prometheus_collector()
        mem_mb = process.memory_info().rss / 1e6
        components = len(metrics.metrics)
        traces = len(get_otel_tracer().completed_traces)
        
        print(f"Memory: {mem_mb:.1f}MB | Components: {components} | Traces: {traces}")
        time.sleep(interval_seconds)

# Run: monitor_memory()
```

---

## Missing Traces

### Symptom: Traces not exported to Jaeger or truncated

**Root Causes & Solutions:**

#### 1. Tracer Not Initialized

```python
# ❌ WRONG: Creating new tracer instances
from ipfs_datasets_py.logic.observability.otel_integration import OTelTracer
tracer = OTelTracer()  # New instance, not global

# ✅ CORRECT: Use singleton
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer
tracer = get_otel_tracer()  # Returns global instance
```

**Diagnosis:**
```python
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer

tracer = get_otel_tracer()
print(f"Tracer service name: {tracer.service_name}")
print(f"Completed traces: {len(tracer.completed_traces)}")
```

#### 2. Spans Not Starting/Ending

```python
# ❌ WRONG: Span created but never used
span = tracer.start_span("operation")  # Created but not updated

# ✅ CORRECT: Complete span lifecycle
span = tracer.start_span("operation")
try:
    result = do_work()
    span.set_attribute("result", result)
    span.end(success=True)
except Exception as e:
    span.record_error(e)
    span.end(success=False)
    raise
```

**Diagnosis:**
```python
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer

tracer = get_otel_tracer()

# Check span status
for trace in tracer.completed_traces:
    for span in trace.spans:
        duration = (span.end_time - span.start_time) * 1000 if span.end_time else None
        print(f"Span: {span.operation_name}, Duration: {duration}ms, "
              f"Status: {span.status}")
```

#### 3. Traces Not Exported to Jaeger

```python
# ❌ WRONG: Traces created but never exported
tracer.start_span("op").end()
# Traces sit in memory indefinitely

# ✅ CORRECT: Export to Jaeger
tracer.start_span("op").end()
jaeger_json = tracer.export_to_jaeger_json()
# Send to Jaeger: POST /api/traces with JSON payload
```

**Diagnosis:**
```python
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer

tracer = get_otel_tracer()

# Generate sample traces
for i in range(3):
    span = tracer.start_span(f"operation_{i}")
    span.set_attribute("iteration", i)
    span.end(success=True)

# Export and check format
jaeger_json = tracer.export_to_jaeger_json()
print(f"Exported {len(jaeger_json)} traces to Jaeger format")

# Verify structure
import json
data = json.loads(jaeger_json)
if "data" in data and len(data["data"]) > 0:
    print("✓ Valid Jaeger format")
else:
    print("✗ Invalid format!")
```

#### 4. Jaeger Server Not Receiving Data

```bash
# Check Jaeger is reachable
curl -s http://localhost:14268/api/traces | head -20

# Should return valid responses or error codes
# If no response: Jaeger container not running

# Docker Compose syntax:
docker-compose ps
# All services should show healthy/running
```

**Resolution Checklist:**
- [ ] `get_otel_tracer()` called consistently
- [ ] Spans explicitly call `span.end()` with success/error status
- [ ] Traces exported with `export_to_jaeger_json()`
- [ ] Jaeger collector endpoint reachable: `http://localhost:14268`
- [ ] Jaeger UI accessible: `http://localhost:16686`

**Example Integration:**
```python
from fastapi import FastAPI, Request
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer

app = FastAPI()
tracer = get_otel_tracer()

@app.middleware("http")
async def otel_middleware(request: Request, call_next):
    """Trace all HTTP requests."""
    span = tracer.start_span(f"{request.method} {request.url.path}")
    span.set_attribute("http.method", request.method)
    span.set_attribute("http.url", str(request.url))
    
    try:
        response = await call_next(request)
        span.set_attribute("http.status_code", response.status_code)
        span.end(success=response.status_code < 400)
        return response
    except Exception as e:
        span.record_error(e)
        span.end(success=False)
        raise

@app.get("/export-traces")
def export_traces():
    """Export all completed traces."""
    jaeger_json = tracer.export_to_jaeger_json()
    return {"status": "ok", "traces_exported": len(tracer.completed_traces)}
```

---

## Circuit Breaker Issues

### Symptom: Circuit breaker not opening or stays open forever

**Root Causes & Solutions:**

#### 1. Threshold Not Configured

```python
# ❌ WRONG: Default threshold too high
cb = get_circuit_breaker("service")  # Default: 50 failures needed

# ✅ CORRECT: Lower threshold for testing
cb = get_circuit_breaker("service")
cb.failure_threshold = 5  # Open after 5 failures
```

**Diagnosis:**
```python
from ipfs_datasets_py.logic.security.llm_circuit_breaker import get_circuit_breaker

cb = get_circuit_breaker("service")
print(f"Failure threshold: {cb.failure_threshold}")
print(f"Current failures: {cb.failure_count}")
print(f"State: {cb.state.value}")
```

#### 2. Timeout Set Too Long

```python
# ❌ WRONG: Timeout so long the service recovers naturally
cb.timeout_seconds = 86400  # 1 day!

# ✅ CORRECT: Reasonable timeout for service recovery
cb.timeout_seconds = 5  # 5 seconds
```

**Diagnosis:**
```python
from ipfs_datasets_py.logic.security.llm_circuit_breaker import get_circuit_breaker

cb = get_circuit_breaker("service")
print(f"Timeout: {cb.timeout_seconds}s")
print(f"Last failure at: {cb.last_failure_time}")

import time
time_since_failure = time.time() - cb.last_failure_time if cb.last_failure_time else 0
print(f"Time since last failure: {time_since_failure:.1f}s")
if time_since_failure > cb.timeout_seconds:
    print("⚠️ Circuit should be in HALF_OPEN now")
```

#### 3. Circuit Breaker State Never Updates

```python
# ❌ WRONG: Exception not caught properly
try:
    cb.call(failing_service)
except:  # Catches SystemExit, KeyboardInterrupt!
    pass

# ✅ CORRECT: Catch specific exceptions
try:
    cb.call(failing_service)
except ApplicationError:
    pass
```

**Diagnosis:**
```python
from ipfs_datasets_py.logic.security.llm_circuit_breaker import get_circuit_breaker
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector

cb = get_circuit_breaker("service")
metrics = get_prometheus_collector()

# Manually check state transitions
print(f"CB state: {cb.state.value}")
print(f"Failure count: {cb.failure_count}")

metrics_summary = metrics.get_metrics_summary("service")
print(f"Metrics state: {metrics_summary['current_state']}")
print(f"Metrics failure rate: {metrics_summary['failure_rate']:.1f}%")
```

#### 4. Fallback Not Working

```python
# ❌ WRONG: Fallback returns same error
def fallback():
    raise Exception("Fallback also failed")

result = cb.call(service, fallback=fallback)

# ✅ CORRECT: Fallback returns safe default
def fallback():
    return {"cached": True, "data": last_known_good}

result = cb.call(service, fallback=fallback)
```

**Resolution Checklist:**
- [ ] `failure_threshold` is reasonable (5-20)
- [ ] `timeout_seconds` matches service recovery time (1-10s)
- [ ] Service exceptions caught specifically, not broadly
- [ ] Fallback function returns valid result, not None/error
- [ ] Metrics recorded for all calls

**Example Circuit Breaker Testing:**
```python
import time
from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    get_circuit_breaker,
    CircuitBreakerOpenError,
)

cb = get_circuit_breaker("test_service")
cb.failure_threshold = 3
cb.timeout_seconds = 2

def failing_service():
    raise Exception("Service error")

def fallback():
    return {"fallback": True}

print("Step 1: Trigger failures to open circuit")
for i in range(5):
    try:
        cb.call(failing_service)
    except CircuitBreakerOpenError:
        print(f"  Circuit opened at attempt {i}")
        break
    except Exception:
        print(f"  Failure {i+1}")

print(f"\nStep 2: Circuit state is now: {cb.state.value}")

print(f"\nStep 3: Wait {cb.timeout_seconds}s for recovery")
time.sleep(cb.timeout_seconds + 0.1)

print("Step 4: Try again with fallback")
result = cb.call(failing_service, fallback=fallback)
print(f"Result: {result}")
```

---

## Integration Problems

### Symptom: Metrics and traces exist but don't correlate

**Root Causes & Solutions:**

#### 1. Missing Trace Context in Metrics

```python
# ❌ WRONG: Separate recording, no correlation
cb.call(service)
tracer.start_span("operation").end()

# ✅ CORRECT: Record both with common context
span = tracer.start_span("operation")
try:
    elapsed = cb.call(service)
    metrics.record_circuit_breaker_call("service", elapsed, success=True)
    span.set_attribute("success", True)
    span.end(success=True)
except Exception as e:
    span.record_error(e)
    span.end(success=False)
    raise
```

**Diagnosis:**
```python
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer

tracer = get_otel_tracer()

# Check if spans have relevant attributes
for trace in tracer.completed_traces:
    for span in trace.spans:
        print(f"Span: {span.operation_name}")
        print(f"  Attributes: {span.attributes}")
        if "success" not in span.attributes:
            print("  ⚠️ Missing success attribute!")
```

#### 2. Timestamp Misalignment

```python
# ❌ WRONG: System clock skew between metrics and traces
# Metrics recorded at T, traces at T+1000ms (different systems)

# ✅ CORRECT: Use same clock source
import time
start = time.time()

elapsed = time.time() - start  # Same clock
metrics.record_circuit_breaker_call("service", elapsed, success=True)

# Traces also use time.time() internally
```

#### 3. Component Name Mismatch

```python
# ❌ WRONG: Different names for same service
metrics.record_circuit_breaker_call("api_v1", 0.05, success=True)
tracer.start_span("api_v2").end()  # Different!

# ✅ CORRECT: Consistent naming
component_name = "api_external"
metrics.record_circuit_breaker_call(component_name, 0.05, success=True)
tracer.start_span(component_name).end()
```

**Diagnosis:**
```python
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer

metrics = get_prometheus_collector()
tracer = get_otel_tracer()

metric_components = set(metrics.metrics.keys())
span_operations = set()
for trace in tracer.completed_traces:
    for span in trace.spans:
        span_operations.add(span.operation_name)

print(f"Metrics components: {metric_components}")
print(f"Span operations: {span_operations}")
print(f"Common: {metric_components & span_operations}")
print(f"Only in metrics: {metric_components - span_operations}")
print(f"Only in traces: {span_operations - metric_components}")
```

#### 4. Metrics Not in Prometheus While Tracing in Jaeger

```python
# ❌ WRONG: Jaeger endpoint reachable but Prometheus not scraping
# Result: Spans in Jaeger but no metrics in Prometheus

# ✅ CORRECT: Verify both endpoints working
# Prometheus: curl http://localhost:9090/api/v1/targets
# Jaeger: curl http://localhost:16686/api/traces
```

**Diagnosis:**
```bash
# Check Prometheus scrape targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[].labels'

# Check actual metrics in Prometheus
curl -s 'http://localhost:9090/api/v1/query?query=circuit_breaker_calls_total'

# Check Jaeger traces
curl -s http://localhost:16686/api/traces?service=mcp-plus-plus | jq '.data | length'
```

**Resolution Checklist:**
- [ ] Common component names used in metrics and traces
- [ ] Same time source (time.time()) for elapsed calculations
- [ ] Both metrics and traces recorded in same try/except block
- [ ] Prometheus discovering metrics endpoint in scrape config
- [ ] Jaeger collector receiving trace exports

**Example Integrated Logging:**
```python
import time
from ipfs_datasets_py.logic.security.llm_circuit_breaker import get_circuit_breaker
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer
import json

def call_external_service(service_name: str):
    """Call service with integrated metrics + tracing."""
    cb = get_circuit_breaker(service_name)
    metrics = get_prometheus_collector()
    tracer = get_otel_tracer()
    
    span = tracer.start_span(service_name)
    start = time.time()
    
    try:
        result = cb.call(mock_service)
        elapsed = time.time() - start
        
        # Record metrics and trace
        metrics.record_circuit_breaker_call(service_name, elapsed, success=True)
        span.set_attribute("elapsed_ms", elapsed * 1000)
        span.set_attribute("result", str(result)[:100])
        span.end(success=True)
        
        return result
    except Exception as e:
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call(service_name, elapsed, success=False)
        span.record_error(e)
        span.end(success=False)
        raise

# Usage
for i in range(5):
    try:
        call_external_service("backup_api")
    except Exception:
        pass
```

---

## Advanced Debugging

### Exporting Complete System State

When opening issues or debugging, export the complete observability state:

```python
import json
from datetime import datetime
from ipfs_datasets_py.logic.observability.metrics_prometheus import get_prometheus_collector
from ipfs_datasets_py.logic.observability.otel_integration import get_otel_tracer
from ipfs_datasets_py.logic.security.llm_circuit_breaker import get_circuit_breaker

def export_debug_state():
    """Export all metrics, traces, and circuit breaker state."""
    metrics = get_prometheus_collector()
    tracer = get_otel_tracer()
    
    state = {
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": {
            "components": list(metrics.metrics.keys()),
            "components_summary": {
                comp: metrics.get_metrics_summary(comp)
                for comp in metrics.metrics.keys()
            }
        },
        "tracing": {
            "completed_traces": len(tracer.completed_traces),
            "traces": [
                {
                    "trace_id": trace.trace_id,
                    "spans": len(trace.spans),
                    "span_names": [s.operation_name for s in trace.spans]
                }
                for trace in tracer.completed_traces[:10]  # First 10
            ]
        },
        "circuit_breakers": {}
    }
    
    # Add circuit breaker state for each service
    for component in metrics.metrics.keys():
        try:
            cb = get_circuit_breaker(component)
            state["circuit_breakers"][component] = {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "failure_threshold": cb.failure_threshold,
                "timeout_seconds": cb.timeout_seconds,
            }
        except:
            pass
    
    return json.dumps(state, indent=2, default=str)

# Export and save
debug_state = export_debug_state()
with open("observability_debug_state.json", "w") as f:
    f.write(debug_state)

print("Debug state exported to observability_debug_state.json")
```

---

## Quick Reference Checklist

**For Each Service Integration:**

- [ ] Initialize components: `get_circuit_breaker()`, `get_prometheus_collector()`, `get_otel_tracer()`
- [ ] Record metrics: `metrics.record_circuit_breaker_call(name, elapsed, success)`
- [ ] Create spans: `span = tracer.start_span(name); span.end(success=True/False)`
- [ ] Use same `time.time()` clock for elapsed calculations
- [ ] Use consistent component names across metrics and traces
- [ ] Prometheus endpoint returns `text/plain` format
- [ ] Jaeger endpoint reachable at `http://localhost:14268`
- [ ] Monitor memory: metrics capped at 1000 samples, traces at 100 completed

**For Production Deployment:**

- [ ] Set reasonable failure thresholds (5-20, not 50+)
- [ ] Configure short timeouts (1-10s, not 86400s)
- [ ] Export traces to Jaeger: `tracer.export_to_jaeger_json()`
- [ ] Set up Prometheus scraping from `/metrics` endpoint
- [ ] Configure alerting rules (open breaker, high latency, error rate)
- [ ] Set up Grafana dashboards from template
- [ ] Monitor memory growth with: `psutil.Process().memory_info().rss`
- [ ] Test fallback mechanisms for critical services
