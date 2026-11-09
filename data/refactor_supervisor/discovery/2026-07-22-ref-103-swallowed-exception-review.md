# REF-103 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:391`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-103-codebase-scan-f0d337002b0e.md`

## Decision

The average knowledge-graph entity-growth metric comes from a persisted optimizer
report and may be missing or non-numeric. `float` reports those expected input
problems with `TypeError` or `ValueError`, and prompt construction should omit the
related focus recommendation when either occurs.

The broad `Exception` handler concealed unexpected failures while converting the
metric. Conversion now occurs before the surrounding best-effort focus logic and
catches only `TypeError` and `ValueError`. This preserves tolerant handling of
malformed report data while allowing implementation and runtime defects to
propagate for diagnosis.

## Focused Validation

`tests/test_codex_autopatch_prompt.py` verifies that a non-numeric entity-growth
metric remains non-fatal, that a valid low value produces the intended focus, and
that an unexpected conversion failure is no longer swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
