# REF-086 Swallowed Exception Review

Date: 2026-07-22
Source finding: `complaint_analysis/research_bootstrap_workflow.py:438`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-086-codebase-scan-20594a03322b.md`

## Decision

Candidate URLs are extracted from untrusted HTML, so malformed URL syntax is an
expected per-link failure and should continue to produce `None`. `urlparse`
reports malformed bracketed hosts and invalid Unicode in the authority component
with `ValueError`.

The broad `Exception` handler also hid unexpected failures in candidate scoring,
making implementation defects look like malformed source data. The handler is
now limited to `ValueError`. Expected invalid URLs remain non-fatal while
unexpected exceptions propagate for diagnosis and workflow-level handling.

## Focused Validation

`tests/test_research_bootstrap_workflow.py` verifies that malformed URL syntax is
still rejected and that an unexpected URL parser failure is no longer swallowed.

Required syntax validation:

```text
python3 -m py_compile complaint_analysis/research_bootstrap_workflow.py
```
