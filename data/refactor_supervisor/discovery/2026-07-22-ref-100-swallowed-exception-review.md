# REF-100 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:148`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-100-codebase-scan-68fe19c78b01.md`

## Decision

The reset timestamp reaches the remaining-delay calculation only after one of
the timestamp parsers has returned a timezone-aware `datetime`. Subtracting the
current UTC time and converting the resulting duration to seconds therefore has
no expected per-message failure mode.

The broad `Exception` handler hid unexpected clock and datetime failures and
silently left the caller without a usable reset delay. The handler has been
removed so implementation and runtime defects propagate for diagnosis. Past
reset timestamps remain supported: their non-positive delay is intentionally
ignored without raising an exception.

## Focused Validation

`tests/test_codex_rate_limit_parsing.py` verifies that a failure while obtaining
the current time is no longer swallowed by the reset-delay calculation. Existing
tests continue to cover valid future timestamps and malformed provider input.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
