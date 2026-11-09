# REF-234 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/mcp/integration/test_integration_observability_core.py:391`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-234-codebase-scan-e6ab5d273248.md`

## Decision

The recovery integration test intentionally drives the complaint analyzer
through failures, an open circuit, and a successful half-open probe. The
flagged bare handler silently accepted every `BaseException` while opening the
circuit, including interrupts and test-framework control exceptions. A second
bare handler also converted an unsuccessful recovery probe into a metric and
allowed the test to pass after merely checking that some metric existed. The
test therefore did not prove the recovery behavior described by its name.

The mock analyzer now raises the concrete `RuntimeError` used by this scenario.
The test explicitly asserts those operation failures until the configured
threshold, asserts rejection with `CircuitBreakerOpenError` while the circuit is
open, and lets any unexpected recovery-probe failure propagate. It then verifies
the successful probe result, the transition back to `CLOSED`, and the recorded
success metric. The observability fixture now resets the singleton metrics and
named breakers, including breaker configuration, before and after each test.
The recovery scenario also uses `monkeypatch` for its non-default thresholds.
Together these changes prevent test order from altering the expected exception
path or polluting metric assertions.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/mcp/integration/test_integration_observability_core.py
```

Focused behavioral validation:

```text
python3 -m pytest tests/mcp/integration/test_integration_observability_core.py::TestCircuitBreakerWithObservability::test_circuit_breaker_recovery_tracked -q
```

Validation results:

- PASS — `python3 -m py_compile tests/mcp/integration/test_integration_observability_core.py`
- PASS — focused recovery test (1 passed)
- PASS — `python3 -m pytest tests/mcp/integration/test_integration_observability_core.py -q`
  (9 passed; one unrelated pytest-asyncio configuration deprecation warning)
