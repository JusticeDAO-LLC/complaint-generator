# REF-237 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/mcp/unit/conftest.py:15`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-237-codebase-scan-f12b7e9b7bb2.md`

## Decision

The flagged exception handler hid failures while resetting the global Prometheus
collector. The same fixture also swallowed failures while clearing completed
OpenTelemetry traces and during post-test metrics cleanup. Because MCP unit tests
import these observability modules directly, these are required test dependencies,
not optional integrations. Continuing after an import or reset failure defeats the
fixture's isolation guarantee and can make later tests depend on leaked state.

The fixture now performs one explicit reset operation before and after each test.
Import, singleton lookup, metrics reset, and trace cleanup errors propagate to
pytest as setup or teardown failures. The teardown runs from a `finally` block so
cleanup is attempted even when a test fails or the fixture generator is closed.

## Focused Validation

`tests/test_ref_237_mcp_conftest.py` verifies that metrics and completed traces are
both cleared, collector reset failures are not swallowed, and the fixture invokes
the reset during both setup and teardown.

Validation results:

- PASS — `python3 -m py_compile tests/mcp/unit/conftest.py tests/test_ref_237_mcp_conftest.py`
- PASS — `python3 -m pytest tests/test_ref_237_mcp_conftest.py -q` (3 passed)
- PASS — `python3 -m pytest tests/mcp/unit/test_mcplusplus_v39_session84_observability.py -q` (48 passed)

The pytest runs emitted the repository's existing `pytest-asyncio` configuration
deprecation warning; no test warnings were introduced by this change.
