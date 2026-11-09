# REF-098 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:60`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-098-codebase-scan-e398f8e3d3b4.md`

## Decision

Rate-limit reset timestamps originate in provider error messages and are therefore
untrusted. A malformed ISO timestamp is an expected per-message failure, and
`datetime.fromisoformat` reports that condition with `ValueError`; the helper
should continue to return `None` for that case.

The broad `Exception` handler also hid unexpected failures in the timestamp
parser, making implementation defects indistinguishable from malformed provider
data. The handler is now limited to `ValueError`. Invalid provider timestamps
remain non-fatal while unexpected exceptions propagate for diagnosis.

## Focused Validation

`tests/test_codex_rate_limit_parsing.py` verifies that a malformed timestamp is
still rejected and that an unexpected datetime parser failure is no longer
swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
