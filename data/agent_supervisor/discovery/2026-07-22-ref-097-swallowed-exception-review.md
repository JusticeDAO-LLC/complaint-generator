# REF-097 Swallowed Exception Review

Date: 2026-07-22
Source finding: `document_optimization.py:4683`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-097-codebase-scan-1d2347878027.md`

## Decision

Mediator lookups provide optional support and evidence context to document
optimization. A failed lookup should not abort the entire optimization because
the existing callers deliberately fall back to empty summaries or collections.

The recovery boundary is therefore retained, but mediator exceptions are no
longer silent. The wrapper now logs a warning with traceback information before
returning its existing `None` fallback. The warning identifies only the invoked
method and intentionally omits keyword argument values because those values can
include user or complaint identifiers.

## Focused Validation

`test_mediator_failure_is_logged_and_returns_optional_context_fallback` injects
a failing mediator method and verifies the fallback result, warning, traceback,
and omission of the supplied user identifier from the log message.

Required syntax validation:

```text
python3 -m py_compile document_optimization.py
```
