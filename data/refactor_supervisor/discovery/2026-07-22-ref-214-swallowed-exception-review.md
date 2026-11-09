# REF-214 Swallowed Exception Review

Date: 2026-07-22
Source finding: `mediator/claim_support_hooks.py:114`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-214-codebase-scan-53b80264b7e5.md`

## Decision

Claim-support persistence prepares its DuckDB path before schema
initialization. This preparation creates a missing parent directory and removes
an empty placeholder file so DuckDB can create a valid database. The operation
is intentionally best-effort because schema initialization already owns the
connection failure path, but silently discarding every exception removed the
filesystem error that explains a later schema failure. Catching `Exception`
also hid non-filesystem programming and configuration errors.

The hook now catches only `OSError`, records a
`claim_support_db_path_prepare_error` event with the database path, exception
type, and message, and continues to schema initialization. Non-filesystem
errors remain visible to the caller. This matches the persistence diagnostics
used by the neighboring evidence hook while preserving claim-support startup
behavior for expected filesystem failures.

## Focused Validation

`tests/test_ref_214_claim_support_path.py` verifies that a filesystem failure is
reported through the mediator with actionable context and that an invalid path
configuration is no longer swallowed.

Required syntax validation:

```text
python3 -m py_compile mediator/claim_support_hooks.py
```

Validation results:

- PASS — `python3 -m py_compile mediator/claim_support_hooks.py`
- PASS — `python3 -m pytest tests/test_ref_214_claim_support_path.py -q`
  (2 passed)
- PASS — `python3 -m pytest tests/test_claim_support_hooks.py -q`
  (47 passed)
