# REF-239 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:198`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-239-codebase-scan-cdafe5e4909b.md`

## Decision

The success branch of the metrics-consistency property invokes a
known-successful callable through a new, closed circuit breaker. Its broad
exception handler silently accepted every failure from
`LLMCircuitBreaker.call`, allowing a regression in the successful-call path to
pass as long as the resulting metrics remained internally additive.

The successful call now runs without an exception handler, so unexpected
failures propagate to pytest with their original traceback, and the returned
value is asserted. The final metrics checks also require the exact total,
success, and failure counts implied by the generated call count. This prevents
the original additive invariant from passing when a nominally successful call
is incorrectly recorded as a failure.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
```

Focused behavioral validation:

```text
python3 -m pytest tests/mcp/unit/test_mcplusplus_v39_session84_properties.py::TestCircuitBreakerProperties::test_metrics_consistency -q
```

Validation results:

- PASS — `python3 -m py_compile tests/mcp/unit/test_mcplusplus_v39_session84_properties.py`
- PASS — focused metrics-consistency property (1 passed)
- PASS — full property module with random-order seed 239 (10 passed)

An initial unseeded full-module run hit the existing timing-sensitive Hypothesis
`HealthCheck.too_slow` check in
`test_context_fields_never_leak_between_threads`; all other tests, including the
changed property, passed in that run. The seeded full-module rerun passed. Pytest
also emitted the repository's existing `pytest-asyncio` configuration
deprecation warning.
