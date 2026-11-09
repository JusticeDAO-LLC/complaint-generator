# REF-081 Swallowed Exception Review

Date: 2026-07-22
Source finding: `adversarial_harness/session.py:4423`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-081-codebase-scan-34e672b9ad65.md`

## Decision

The formalization transition is a best-effort precursor to document generation. A
transition failure should not abort the document builder because the session has a
direct graph handoff and a fallback document packet. It must not be silent,
however: without an observable failure, operators cannot distinguish an ordinary
fallback from a broken mediator phase transition.

The broad exception boundary is therefore retained at this optional integration
point, but it now logs a warning with the session identifier and traceback before
continuing to document generation.

## Focused Validation

`test_document_generation_logs_formalization_transition_failure_and_continues`
injects a failing formalization transition and verifies that the warning includes
the session and exception while the document builder still completes.

Required syntax validation:

```text
python3 -m py_compile adversarial_harness/session.py
```
