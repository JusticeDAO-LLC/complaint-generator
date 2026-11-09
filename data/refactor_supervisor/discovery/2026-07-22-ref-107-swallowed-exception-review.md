# REF-107 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:425`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-107-codebase-scan-49486516bc95.md`

## Decision

Prompt construction reads several session counters from a persisted optimizer
report. Missing or malformed counter values are expected input problems and
should continue to behave as zero. Integer conversion reports those problems
with `TypeError`, `ValueError`, or `OverflowError`.

The broad handler wrapped both conversion and all focus-generation logic. It
silently concealed unexpected conversion failures and unrelated implementation
defects, while its no-op assignment provided no observability. Count parsing now
has a narrow helper that defaults only expected conversion failures to zero, and
the focus logic runs without a catch-all handler so unexpected failures remain
visible for diagnosis.

## Focused Validation

`tests/test_codex_autopatch_prompt.py` verifies that malformed persisted counts
remain non-fatal and do not create misleading focus recommendations. It also
verifies that an unexpected count conversion failure is no longer swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
