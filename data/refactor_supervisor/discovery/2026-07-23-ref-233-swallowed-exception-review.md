# REF-233 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/mcp/integration/test_integration_observability_core.py:319`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-233-codebase-scan-808673069550.md`

## Decision

The analysis stage in the partial-failure integration test is expected to
succeed. Its bare `except` previously caught every throwable and silently
continued, allowing an unexpected analyzer or circuit-breaker failure to be
reported indirectly as a metrics mismatch—or to be hidden by metrics retained
by the process-wide collector.

The unnecessary handler has been removed so an unexpected analysis failure
propagates directly to pytest with its original traceback. The successful
analysis result is now passed into the intentionally failing decision stage,
which preserves the test's intended successful-analysis/failed-decision
pipeline boundary. The observability fixture now also resets the process-wide
metrics collector and named circuit breakers before each test. This prevents
prior metrics or an open breaker from masking the result when pytest randomizes
the module's execution order.

## Focused Validation

The corrected integration test exercises the successful analysis stage, uses
its output in the decision stage, and verifies the resulting mixed metrics.
Because the unexpected analysis path is no longer caught, any regression in
that stage fails the test at its source. The full integration module is also run
under randomized ordering to verify that each test receives clean observability
state.

Required syntax validation:

```text
python3 -m py_compile tests/mcp/integration/test_integration_observability_core.py
```

Validation results:

- PASS — `python3 -m py_compile tests/mcp/integration/test_integration_observability_core.py`
- PASS — focused partial-failure integration test (1 passed)
- PASS — full integration module with random seed 233 (9 passed)
- PASS — full integration module with random seed 808673 (9 passed)

The pytest runs emitted one unrelated configuration deprecation warning from
`pytest-asyncio` about its future default fixture loop scope.
