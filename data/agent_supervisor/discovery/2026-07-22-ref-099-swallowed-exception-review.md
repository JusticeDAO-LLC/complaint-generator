# REF-099 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:83`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-099-codebase-scan-24ed648c404c.md`

## Decision

Human-readable rate-limit reset timestamps originate in provider error messages
and are therefore untrusted. A message that does not match either supported
timestamp format is an expected per-message failure, and `datetime.strptime`
reports that condition with `ValueError`; the helper should continue trying its
supported formats and ultimately return `None` in that case.

The broad `Exception` handler also concealed unexpected failures in the datetime
parser. The handler is now limited to `ValueError`, preserving tolerant handling
of malformed provider timestamps while allowing implementation and runtime
defects to propagate for diagnosis.

## Focused Validation

`tests/test_codex_rate_limit_parsing.py` verifies that a malformed human reset
timestamp remains non-fatal and that an unexpected datetime parser failure is no
longer swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
