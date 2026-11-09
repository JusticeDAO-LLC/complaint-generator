# Codebase Bundle: codebase/runtime/examples-observability_benchmarks

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-115 Review swallowed exception path in examples/observability_benchmarks.py:513

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, examples/observability_benchmarks.py
- Validation: python3 -m py_compile examples/observability_benchmarks.py
- Bundle: codebase/runtime/examples-observability_benchmarks
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-examples-observability_benchmarks.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/examples-observability_benchmarks
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: examples/observability_benchmarks.py
- AST symbols: __init__, add, benchmark circuit breaker decision, benchmark concurrent metrics, benchmark concurrent tracing, benchmark latency under load, benchmark memory growth, benchmark metrics export, benchmark metrics recording latency, benchmark trace creation, benchmark trace export, benchmark_circuit_breaker_decision, benchmark_concurrent_metrics, benchmark_concurrent_tracing, benchmark_latency_under_load, benchmark_memory_growth, benchmark_metrics_export, benchmark_metrics_recording_latency, benchmark_trace_creation, benchmark_trace_export, benchmarkresult, benchmarkresult add, benchmarkresult count, benchmarkresult error, benchmarkresult init, benchmarkresult max, benchmarkresult mean, benchmarkresult median, benchmarkresult memory delta mb, benchmarkresult min, benchmarkresult p95, benchmarkresult p99, benchmarkresult print summary, benchmarkresult stdev, benchmarkresult throughput, benchmarkresult total, benchmarkresult.__init__, benchmarkresult.add, benchmarkresult.count, benchmarkresult.error, benchmarkresult.max, benchmarkresult.mean, benchmarkresult.median, benchmarkresult.memory_delta_mb, benchmarkresult.min, benchmarkresult.p95, benchmarkresult.p99, benchmarkresult.print_summary, benchmarkresult.stdev, benchmarkresult.throughput, benchmarkresult.total, collections, collections defaultdict, collections.defaultdict, concurrent futures, concurrent futures as completed, concurrent futures threadpoolexecutor, concurrent.futures, concurrent.futures.as_completed, concurrent.futures.threadpoolexecutor, count, error, fast service, fast_service, init, ipfs datasets py logic observability metrics prometheus, ipfs datasets py logic observability metrics prometheus get prometheus collector, ipfs datasets py logic observability otel integration, ipfs datasets py logic observability otel integration get otel tracer, ipfs datasets py logic security llm circuit breaker, ipfs datasets py logic security llm circuit breaker circuitbreakeropenerror, ipfs datasets py logic security llm circuit breaker get circuit breaker, ipfs_datasets_py.logic.observability.metrics_prometheus, ipfs_datasets_py.logic.observability.metrics_prometheus.get_prometheus_collector, ipfs_datasets_py.logic.observability.otel_integration, ipfs_datasets_py.logic.observability.otel_integration.get_otel_tracer, ipfs_datasets_py.logic.security.llm_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.circuitbreakeropenerror, ipfs_datasets_py.logic.security.llm_circuit_breaker.get_circuit_breaker, json
- AST symbol scope: file
- Goal id: codebase/runtime/examples-observability_benchmarks
- Missing evidence: Review swallowed exception path in examples/observability_benchmarks.py:513
- Merge key: codebase/runtime/examples-observability_benchmarks
- Merge family: examples/observability_benchmarks.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 35bb81f1968ccae0
- Acceptance: Codebase scan filed this finding from examples/observability_benchmarks.py:513. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-115-codebase-scan-35bb81f1968c.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
