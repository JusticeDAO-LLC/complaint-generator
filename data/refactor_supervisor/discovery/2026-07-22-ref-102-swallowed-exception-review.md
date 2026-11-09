# REF-102 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:381`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-102-codebase-scan-a3dc11bd394a.md`

## Decision

The average knowledge-graph entity count comes from a persisted optimizer report
and may be missing or non-numeric. `float` reports those expected input problems
with `TypeError` or `ValueError`, and prompt construction should omit the related
focus recommendation when either occurs.

The broad `Exception` handler also concealed unexpected failures while converting
the metric. The conversion now occurs before the surrounding best-effort focus
logic and catches only `TypeError` and `ValueError`. This preserves tolerant
handling of malformed report data while allowing implementation and runtime
defects to propagate for diagnosis.

## Focused Validation

`tests/test_codex_autopatch_prompt.py` verifies that a non-numeric average entity
metric remains non-fatal and does not produce a misleading focus recommendation.
It also verifies that an unexpected metric conversion failure is no longer
swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
