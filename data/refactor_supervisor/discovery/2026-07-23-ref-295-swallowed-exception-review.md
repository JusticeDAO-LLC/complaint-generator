# REF-295 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/mcp/unit/test_observability_property_based.py:251`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-295-codebase-scan-6499e27a6bbe.md`

## Decision

The failure-sequence property intentionally mixes successful service calls with
service calls that raise. Its broad `except Exception` handler silently accepted
every failure from the protected call, including circuit-breaker defects, and
the `CircuitBreakerOpenError` branch allowed the example to stop early. The
final assertion then accepted either a closed or open circuit even though every
generated sequence is shorter than the configured failure threshold. Together,
those conditions let the property pass without exercising the whole generated
sequence or proving its stated behavior.

The synthetic service now raises a concrete `RuntimeError`, and each failing
call must propagate that exact error. Successful calls must return their
expected value, while an unexpected open-circuit or implementation error
propagates directly to pytest. After every generated operation, the test checks
the exact total, success, and failure metrics and requires the circuit to remain
closed. The named singleton breaker is reset for each Hypothesis example so
state and metrics cannot leak between generated sequences.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/mcp/unit/test_observability_property_based.py
```

Focused behavioral validation:

```text
python3 -m pytest tests/mcp/unit/test_observability_property_based.py::TestCircuitBreakerPropertyBased::test_circuit_state_reflects_failure_sequence -q
```

Validation results:

- PASS — `python3 -m py_compile tests/mcp/unit/test_observability_property_based.py`
- PASS — focused failure-sequence property (1 passed)
- PASS — full property-based observability module (16 passed)

The pytest runs emitted the repository's existing `pytest-asyncio`
configuration deprecation warning; this change introduced no test warnings.
