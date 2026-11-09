# REF-104 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:397`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-104-codebase-scan-91567567a40f.md`

## Decision

The average knowledge-graph relationship-growth metric comes from a persisted
optimizer report and may be missing or non-numeric. `float` reports those
expected input problems with `TypeError` or `ValueError`, and prompt construction
should omit the related focus recommendation when either occurs.

The broad `Exception` handler concealed unexpected failures while converting the
metric. Conversion now occurs before the surrounding best-effort focus logic and
catches only `TypeError` and `ValueError`. This preserves tolerant handling of
malformed report data while allowing implementation and runtime defects to
propagate for diagnosis.

## Focused Validation

`tests/test_codex_autopatch_prompt.py` verifies that non-numeric relationship
growth is ignored, numeric low growth produces the expected diagnostic, and an
unexpected conversion failure is no longer swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
