# REF-112 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:443`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-112-codebase-scan-061b16537a95.md`

## Decision

Prompt construction reads the average knowledge-graph gap delta from a
persisted optimizer report. Missing, non-numeric, and out-of-range values are
expected input problems and should continue to omit this optional diagnostic.
Float conversion reports those problems with `TypeError`, `ValueError`, or
`OverflowError`.

The broad handler silently discarded every exception raised while converting
and evaluating this metric, including unexpected implementation and runtime
defects. The metric is now converted before the focus check, only expected
input failures result in a missing diagnostic, and unexpected failures remain
visible for diagnosis.

## Focused Validation

`tests/test_codex_autopatch_prompt.py` verifies that malformed and out-of-range
persisted metrics remain non-fatal, valid flat gap deltas produce the intended
focus recommendation, and an unexpected conversion failure is no longer
swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
