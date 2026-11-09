# REF-225 Swallowed Exception Review

Date: 2026-07-22
Source finding: `mediator/legal_authority_hooks.py:2612`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-225-codebase-scan-1cc8e01bb3ed.md`

## Decision

`get_authority_by_id` uses `None` to represent a successful lookup in which no
authority has the requested ID. The flagged handler was defective because it
also returned `None` for every DuckDB query, row-decoding, and treatment
hydration failure. Callers therefore could not distinguish missing data from a
broken lookup, even though the error was logged. Failures after connecting
could also bypass `close()` and leak the database connection.

The lookup now retains `None` only for a successful not-found result. Unexpected
failures emit the established `legal_authority_query_error` event with the
authority ID, exception type, and exception message, then propagate the original
exception. The connection is managed with deterministic cleanup on success,
not-found, decoding failure, and query failure.

## Focused Validation

`tests/test_ref_225_legal_authority_lookup_failure.py` verifies that a query
failure is logged, propagated unchanged, and closes the DuckDB connection. It
also verifies that a successful not-found query still returns `None`, closes the
connection, and does not emit an error event.

Required syntax validation:

```text
python3 -m py_compile mediator/legal_authority_hooks.py
```

Validation results:

- PASS — `python3 -m py_compile mediator/legal_authority_hooks.py`
- PASS — `python3 -m pytest tests/test_ref_225_legal_authority_lookup_failure.py -q`
  (2 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
- PASS — `python3 -m pytest tests/test_legal_authority_hooks.py -q`
  (30 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
