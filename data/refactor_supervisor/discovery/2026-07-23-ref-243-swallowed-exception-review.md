# REF-243 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/mcp/unit/test_observability_property_based.py:213`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-243-codebase-scan-421d34ca5ec8.md`

## Decision

The circuit-opening property deliberately invokes a service that fails until
the configured threshold. Its broad `except Exception` handler previously
discarded every non-open exception, so a defect in `LLMCircuitBreaker.call`
could be mistaken for the expected synthetic failure. The loose iteration
limit and lower-bound metric assertion also verified only that the circuit
eventually opened, despite the property's claim that it opens after exactly the
configured number of failures.

The synthetic service now raises a concrete `RuntimeError`, and every
threshold-producing call is checked with `pytest.raises`. After each call, the
test verifies the exact failure count and the expected closed/open state. The
next call must raise `CircuitBreakerOpenError` without adding another service
failure. Because named breakers are process-wide singletons, the breaker is
reset at the start of every Hypothesis example so shrinking or repeated values
cannot inherit open state or metrics from an earlier example.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/mcp/unit/test_observability_property_based.py
```

Focused behavioral validation:

```text
python3 -m pytest tests/mcp/unit/test_observability_property_based.py::TestCircuitBreakerPropertyBased::test_circuit_opens_after_threshold -q
```

Validation results:

- PASS — `python3 -m py_compile tests/mcp/unit/test_observability_property_based.py`
- PASS — focused circuit-opening property (1 passed)
- PASS — full property-based observability module (16 passed)

The pytest runs emitted the repository's existing `pytest-asyncio`
configuration deprecation warning; no test warnings were introduced by this
change.
