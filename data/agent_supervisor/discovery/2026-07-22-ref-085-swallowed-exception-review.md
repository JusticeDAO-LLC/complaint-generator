# REF-085 Swallowed Exception Review

Date: 2026-07-22
Source finding: `complaint_analysis/research_bootstrap_workflow.py:425`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-085-codebase-scan-55a0fab86af9.md`

## Decision

The external-link normalizer processes untrusted links extracted from downloaded
HTML, so malformed URL syntax is an expected per-link failure and should continue
to produce `None`. The `urllib.parse` operations in this boundary report malformed
URL syntax with `ValueError`, including invalid bracketed IPv6 hosts.

The broad `Exception` handler also hid unexpected failures in the normalization
implementation, making defects indistinguishable from malformed source data. The
handler is now limited to `ValueError`. Expected bad links remain non-fatal while
unexpected exceptions propagate for diagnosis and appropriate workflow handling.

## Focused Validation

`tests/test_research_bootstrap_workflow.py` verifies that malformed URL syntax is
still rejected and that an unexpected normalizer failure is no longer swallowed.

Required syntax validation:

```text
python3 -m py_compile complaint_analysis/research_bootstrap_workflow.py
```
