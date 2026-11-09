# REF-240 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:203`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-240-codebase-scan-640593b50d2e.md`

## Decision

The failure branch of the metrics-consistency property deliberately divides by
zero so the circuit breaker records a failed protected call. Its broad exception
handler silently accepted every exception from `LLMCircuitBreaker.call`, allowing
an unexpected circuit-breaker defect to be treated as the intended operation
failure.

The branch now uses `pytest.raises` to require the specific
`ZeroDivisionError` and message produced by the test callable. The assertion
still permits the circuit breaker to record the failure before re-raising it,
while any different exception fails the property test with its original
traceback. The neighboring success-branch handler is the separate REF-239
finding and is intentionally outside this review.

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
- PASS — full property module with random-order seed 240 (10 passed)

An initial unseeded full-module run hit the existing timing-sensitive Hypothesis
`HealthCheck.too_slow` check in
`test_context_fields_never_leak_between_threads`; all other tests, including the
changed property, passed in that run. The seeded full-module rerun passed. Pytest
also emitted the repository's existing `pytest-asyncio` configuration
deprecation warning.
