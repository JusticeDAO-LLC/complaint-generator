# REF-242 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:424`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-242-codebase-scan-dda87dcfba96.md`

## Decision

The singleton edge-case branch invokes a known-successful callable through a
new, closed circuit breaker. Its broad exception handler silently accepted
every failure from `LLMCircuitBreaker.call`, so an unexpected circuit-breaker
regression could be hidden as long as the metrics object still reported one
call.

The successful call now runs without an exception handler, allowing unexpected
failures to propagate to pytest with their original traceback. The property
also verifies the returned value and the exact success and failure counts, in
addition to the existing total-call assertion, so it proves that the singleton
call completed through the intended successful path. An explicit singleton
Hypothesis example makes this repaired branch deterministic instead of relying
on a small randomized sample to generate a one-item list.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
```

Focused behavioral validation:

```text
python3 -m pytest tests/mcp/unit/test_mcplusplus_v39_session84_properties.py::TestAdvancedProperties::test_empty_and_edge_case_sequences -q
```

Validation results:

- PASS — `python3 -m py_compile tests/mcp/unit/test_mcplusplus_v39_session84_properties.py`
- PASS — focused empty/singleton edge-case property (1 passed)
- PASS — full property-test module (10 passed)

The pytest runs emitted the repository's existing `pytest-asyncio`
configuration deprecation warning; this change introduced no test warnings.
