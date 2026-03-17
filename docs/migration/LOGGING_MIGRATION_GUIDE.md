# Migration Guide: From Legacy Logging to Structured JSON Logging

**Updated:** 2026-02-25  
**Phase:** Session 84 - Phase 4 (Observability Integration)

---

## Table of Contents

1. [Overview](#overview)
2. [Why Migrate?](#why-migrate)
3. [Step-by-Step Migration](#step-by-step-migration)
4. [Common Patterns](#common-patterns)
5. [Troubleshooting](#troubleshooting)
6. [Performance Considerations](#performance-considerations)

---

## Overview

The structured logging system replaces print statements and ad-hoc logging with unified JSON-format logs that can be easily parsed, filtered, and analyzed.

**Key Benefits:**
- **Searchable:** Parse JSON to find events by component, level, or fields
- **Structured:** All logs have consistent schema (timestamp, level, component, message)
- **Traceable:** All logs from the same operation share a `request_id`
- **Performant:** Context propagation and batching reduce I/O overhead
- **Distributed:** Log correlation IDs work across distributed systems

---

## Why Migrate?

### Legacy Print Statements

```python
# ❌ Before: Hard to parse, no structure
print(f"Started processing document {doc_id} at {time.time()}")
result = process_document(doc_id)
print(f"Document {doc_id} processing finished. Result: {result}")
```

**Problems:**
- No consistent format → hard to parse programmatically
- No log level (debug vs error?) → can't filter
- No timestamp → unclear timing
- No context → which request is this for?

### Structured Approach

```python
# ✅ After: Structured, queryable, traceable
from ipfs_datasets_py.logic.observability.structured_logging import log_event, LogContext

with LogContext(component="processor", request_id=doc_id):
    log_event("started", {"phase": "document_processing", "doc_id": doc_id})
    result = process_document(doc_id)
    log_event("completed", {"phase": "document_processing", "status": "success"})
```

**Benefits:**
- Consistent JSON format
- Fields are queryable (component, level, fields)
- Automatic request correlation
- Can be filtered/analyzed programmatically

---

## Step-by-Step Migration

### Phase 1: Setup (5 min)

Import the structured logging module:

```python
# Add to imports at top of file
from ipfs_datasets_py.logic.observability.structured_logging import (
    log_event,
    log_error,
    log_performance,
    LogContext,
    EventType,
)
```

### Phase 2: Replace Informational Prints (15 min)

**Before:**
```python
def fetch_data(query):
    print(f"Starting fetch for query: {query}")
    result = database.query(query)
    print(f"Query returned {len(result)} rows")
    return result
```

**After:**
```python
def fetch_data(query):
    log_event("query_started", {"query": query})
    result = database.query(query)
    log_event("query_completed", {"row_count": len(result)})
    return result
```

### Phase 3: Replace Error Prints (20 min)

**Before:**
```python
def validate_input(data):
    if not data:
        print(f"ERROR: Invalid input received")
        raise ValueError("Input cannot be empty")
```

**After:**
```python
def validate_input(data):
    if not data:
        log_error("validation_failed", ValueError("Input cannot be empty"))
        raise ValueError("Input cannot be empty")
```

### Phase 4: Replace Performance Prints (15 min)

**Before:**
```python
def parse_entities(text):
    start = time.time()
    entities = nlp(text)
    elapsed = time.time() - start
    print(f"Parsed {len(entities)} entities in {elapsed:.3f}s")
    return entities
```

**After:**
```python
def parse_entities(text):
    with log_performance("entity_parsing", {"text_length": len(text)}):
        entities = nlp(text)
        return entities
```

### Phase 5: Add Context for Requests (20 min)

**Before:**
```python
def process_complaint(complaint_id):
    print(f"Processing complaint {complaint_id}")
    # ... lots of processing ...
    print(f"Complaint {complaint_id} processed")
```

**After:**
```python
def process_complaint(complaint_id):
    with LogContext(component="complaint_processor", request_id=complaint_id):
        log_event("processing_started", {"complaint_id": complaint_id})
        # ... lots of processing ...
        # All logs in here automatically get request_id=complaint_id
        log_event("processing_completed", {"complaint_id": complaint_id})
```

---

## Common Patterns

### Pattern 1: Logging in a Loop

**Before:**
```python
for item in items:
    print(f"Processing item {item.id}")
    result = process(item)
    print(f"Item {item.id}: {result}")
```

**After:**
```python
for item in items:
    log_event("item_processing", {"item_id": item.id}, level="debug")
    result = process(item)
    log_event("item_result", {"item_id": item.id, "result": result})
```

### Pattern 2: Logging Exceptions

**Before:**
```python
try:
    risky_operation()
except Exception as e:
    print(f"ERROR: {e}")
    raise
```

**After:**
```python
try:
    risky_operation()
except Exception as e:
    log_error("operation_failed", e)
    raise
```

### Pattern 3: Conditional Debug Logging

**Before:**
```python
if DEBUG:
    print(f"Debug: internal state = {state}")
```

**After:**
```python
log_event("internal_state", {"state": state}, level="debug")
# This won't appear in logs if INFO level is set
```

### Pattern 4: Logging with Fields

**Before:**
```python
print(f"API call to {endpoint} with method {method} returned {status}")
```

**After:**
```python
log_event("api_call_completed", {
    "endpoint": endpoint,
    "method": method,
    "status": status
})
```

### Pattern 5: Performance Tracking

**Before:**
```python
start = time.time()
result = expensive_operation()
elapsed = time.time() - start
if elapsed > 1.0:
    print(f"WARNING: Operation took {elapsed:.2f}s")
```

**After:**
```python
with log_performance("expensive_operation", warnings_above=1.0):
    result = expensive_operation()
```

---

## Troubleshooting

### Issue: "Logs not appearing"

**Solution:** Check that structured logging is configured:

```python
import logging
from ipfs_datasets_py.logic.observability.structured_logging import configure_logging

# Configure at application startup
configure_logging(log_file="logs/app.json", level="INFO")

# Or with console output:
configure_logging(use_console=True, level="DEBUG")
```

### Issue: "Context fields not propagating"

**Solution:** Ensure you're using `LogContext` properly:

```python
# ❌ Wrong: Context is lost after exit
with LogContext(component="processor"):
    # Logs here have component="processor"
    log_event("started")

# ✅ Correct: All nested calls inherit context
with LogContext(component="processor", request_id="req_123"):
    log_event("started")  # Gets component and request_id
    helper_function()     # Also gets both
```

### Issue: "Missing request IDs in logs"

**Solution:** Set request_id at the entry point:

```python
# In main handler/view/route:
def handle_request(request_id):
    with LogContext(request_id=request_id):
        # Everything logged here gets the request_id
        process_payload(request.data)
```

### Issue: "Logs are hard to read in terminal"

**Solution:** Use a log viewer:

```bash
# Pretty-print JSON logs
cat logs/app.json | jq '.'

# Filter by component
cat logs/app.json | jq 'select(.component=="processor")'

# Filter by level
cat logs/app.json | jq 'select(.level=="error")'

# Timeline view
cat logs/app.json | jq -r '.timestamp, .message' | paste - -
```

---

## Performance Considerations

### Writing to Disk

Structured logging writes JSON to disk. Consider:

```python
# Asynchronous writing (recommended)
configure_logging(
    log_file="logs/app.json",
    async_write=True,           # Don't block on I/O
    buffer_size=1000            # Batch writes
)

# Or using syslog (even faster)
configure_logging(
    use_syslog=True,
    syslog_address="/dev/log"
)
```

### Sampling

For high-volume logs, reduce verbosity:

```python
# Log only 1% of debug events
log_event("low_importance", data, level="debug", sample_rate=0.01)

# Log all errors
log_event("critical_event", data, level="error", sample_rate=1.0)
```

### Memory Usage

Logs are buffered in memory before writing:

```python
# For high-throughput, use smaller buffer
configure_logging(buffer_size=100, flush_interval=0.1)

# For low-frequency, use larger buffer
configure_logging(buffer_size=10000, flush_interval=5.0)
```

---

## Integration with Circuit Breaker

The structured logging integrates seamlessly with the circuit breaker:

```python
from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    get_circuit_breaker,
)
from ipfs_datasets_py.logic.observability.structured_logging import (
    log_event, LogContext
)

# Create a protected API call
cb = get_circuit_breaker("payment_api")

with LogContext(request_id="txn_123"):
    try:
        with log_performance("payment_processing"):
            result = cb.call(payment_api.charge, amount=100.0)
            log_event("payment_succeeded", {"amount": 100.0})
    except Exception as e:
        log_error("payment_failed", e)
        raise
```

All logs will have:
- `request_id`: "txn_123" (from LogContext)
- `component`: "payment_processing" (from log_performance)
- Correlated timestamps for debugging

---

## Checklist

- [ ] Install/update `structured_logging` module
- [ ] Update imports in all production modules
- [ ] Replace top-level print statements with `log_event()`
- [ ] Replace exception prints with `log_error()`
- [ ] Replace performance prints with `log_performance()`
- [ ] Add `LogContext` to request handlers
- [ ] Test with `jq` to verify JSON format
- [ ] Set up log rotation (see ops guide)
- [ ] Monitor disk usage
- [ ] Update on-call docs with new log format

---

## Next Steps

1. **Prometheus Integration:** See [Prometheus Metrics Guide](../metrics/prometheus-guide.md)
2. **OpenTelemetry:** See [Distributed Tracing Guide](../tracing/otel-guide.md)
3. **Log Analysis:** See [Log Query Examples](../analysis/log-queries.md)
4. **Alerting:** Set up alerts on structured logs using ELK or Datadog

---

## Support

For questions or issues:
- See [Structured Logging API](../../ipfs_datasets_py/logic/observability/structured_logging.py)
- Check [examples/logging_examples.py](../../examples/logging_examples.py)
- File issues on the project tracker
