# REF-101 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:176`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-101-codebase-scan-e828b7e6adff.md`

## Decision

Rate-limit reset timestamps reach the flagged calculation only after one of the
two local parsers has returned a timezone-aware `datetime`. Malformed provider
timestamps are handled at those parsing boundaries by returning `None`, so the
remaining-seconds calculation has no expected input failure to suppress.

The broad `Exception` handler silently hid unexpected failures in clock access,
datetime arithmetic, and conversion, potentially discarding a valid reset time
and causing the caller to choose an inaccurate fallback delay. The handler has
been removed so those implementation and runtime failures remain observable.
Past reset timestamps retain the existing behavior of leaving the derived reset
seconds unset.

## Focused Validation

`tests/test_codex_rate_limit_parsing.py` verifies that an unexpected system-clock
failure during the remaining-seconds calculation propagates instead of being
silently swallowed. Existing tests continue to cover valid ISO and human reset
timestamps and malformed provider input at the parsing boundary.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
