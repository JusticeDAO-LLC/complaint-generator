# REF-238 Swallowed Exception Review

Date: 2026-07-23
Source finding: `tests/mcp/unit/test_mcplusplus_v39_session84_concurrency.py:413`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-238-codebase-scan-12d48b71aec6.md`

## Decision

The handler around `future.result()` silently discarded any exception escaping a
logging-context worker. This could let the concurrency test continue without
reporting the original worker failure or traceback. The worker already records
expected logging and context failures in `context_errors` for the existing
aggregate assertions, so an exception that escapes it is unexpected.

The redundant handler has been removed. Executor failures now propagate directly
to pytest with their original traceback, while expected operation failures remain
collected and checked by the test.

## Focused Validation

Required syntax validation:

```text
python3 -m py_compile tests/mcp/unit/test_mcplusplus_v39_session84_concurrency.py
```

Focused behavioral validation:

```text
python3 -m pytest tests/mcp/unit/test_mcplusplus_v39_session84_concurrency.py::TestLoggingConcurrentStress::test_logging_with_context_500_threads -q
```

Validation results:

- PASS — `python3 -m py_compile tests/mcp/unit/test_mcplusplus_v39_session84_concurrency.py`
- PASS — focused logging-context concurrency test (1 passed)
- PASS — full concurrency module (10 passed)

The pytest runs emitted the repository's existing `pytest-asyncio` configuration
deprecation warning; no test warnings were introduced by this change.
