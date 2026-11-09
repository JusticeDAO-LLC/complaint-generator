# REF-224 Swallowed Exception Review

Date: 2026-07-22
Source finding: `mediator/legal_authority_hooks.py:1318`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-224-codebase-scan-64f50cf3d4f3.md`

## Decision

DuckDB path preparation is intentionally best-effort: schema initialization
owns the database connection error path and will report an unusable path. The
flagged handler was defective because it silently discarded every exception,
including filesystem errors that explain why the empty-file cleanup or parent
directory creation failed and programming/configuration errors that should not
be suppressed.

The handler now catches only `OSError` and emits the structured
`legal_authority_db_path_prepare_error` event with the database path, exception
type, and exception message. Non-filesystem exceptions propagate so invalid
configuration and code defects remain immediately visible. This matches the
path-preparation contract used by the repository's other DuckDB-backed hooks.

## Focused Validation

`tests/test_ref_224_legal_authority_path.py` verifies that a filesystem failure
records actionable diagnostics without preempting the schema initializer's
connection handling, and that an invalid path value is no longer swallowed.

Required syntax validation:

```text
python3 -m py_compile mediator/legal_authority_hooks.py
```

Validation results:

- PASS — `python3 -m py_compile mediator/legal_authority_hooks.py`
- PASS — `python3 -m pytest tests/test_ref_224_legal_authority_path.py -q`
  (2 passed)
- PASS — `python3 -m pytest tests/test_legal_authority_hooks.py -q`
  (30 passed)
