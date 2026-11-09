# REF-106 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:173`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-106-codebase-scan-440f839ed999.md`

## Decision

The optional Codex exec JSONL artifact may be absent, unreadable, or contain
invalid UTF-8 while the rate-limit fallback is being inspected. `OSError` and
`UnicodeError` represent those expected artifact failures, and extraction should
continue to treat them as an unavailable fallback by returning `None`.

The broad `Exception` handler also concealed unexpected failures in file opening,
iteration, and extraction. The handler now catches only the expected I/O and
text-decoding failures so implementation and runtime defects propagate for
diagnosis.

## Focused Validation

`tests/test_codex_rate_limit_parsing.py` verifies that missing and invalid-UTF-8
artifacts remain non-fatal and that an unexpected artifact-reader failure is no
longer swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
