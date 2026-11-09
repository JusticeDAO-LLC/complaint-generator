# REF-115 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/observability_benchmarks.py:513`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-115-codebase-scan-35bb81f1968c.md`

## Decision

The flagged handler waited for the measurement and load-generator futures after
requesting that their loops stop. A future can raise either the exception that
terminated its worker or a timeout when it does not stop within five seconds.
Neither outcome produces a valid benchmark run.

The bare handler silently discarded every such outcome, including
`KeyboardInterrupt` and `SystemExit`, and allowed the benchmark to return empty
or partial latency statistics as though the run had completed successfully.
Future results are now retrieved without a catch-all handler. Worker failures
and completion timeouts therefore propagate to the caller while successful
workers retain the existing bounded wait.

## Focused Validation

`tests/test_observability_benchmarks.py` uses a deterministic executor stub to
verify that a load-worker failure propagates from
`benchmark_latency_under_load` instead of being swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/observability_benchmarks.py
```
