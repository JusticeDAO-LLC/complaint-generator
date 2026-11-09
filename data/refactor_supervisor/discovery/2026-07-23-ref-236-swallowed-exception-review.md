# REF-236 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/mcp/integration/test_integration_observability_core.py:521`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-236-codebase-scan-e9742a965847.md`

## Decision

The decision-tree call in the cross-component latency test is expected to
succeed. Its bare exception handler previously caught every throwable and
silently continued, after which the test recorded the failed call as successful.
That behavior could hide decision-tree or circuit-breaker regressions and produce
misleading latency and success-rate metrics.

The unnecessary handler has been removed. An unexpected decision failure now
propagates directly to pytest with its original traceback, and the success metric
is recorded only after the call returns. REF-233 added nine lines before the
finding after the scan was generated, so the original line 521 maps to the
decision stage at the current line 530. The analysis-stage handler is the
separate REF-235 finding and remains available for its own backlog review.

## Focused Validation

The corrected latency-correlation integration test exercises all 50 required
decision calls. Since those calls are no longer caught, a failure stops the test
at the source instead of being mislabeled as a success.

Required syntax validation:

```text
python3 -m py_compile tests/mcp/integration/test_integration_observability_core.py
```

Validation results:

- PASS — `python3 -m py_compile tests/mcp/integration/test_integration_observability_core.py`
- PASS — focused latency-correlation integration test (1 passed)
- PASS — full integration module (9 passed)

The pytest runs emitted one existing `pytest-asyncio` configuration deprecation
warning about its future default fixture loop scope.
