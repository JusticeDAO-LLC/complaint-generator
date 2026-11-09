# REF-080 Swallowed Exception Review

Date: 2026-07-22
Source finding: `adversarial_harness/session.py:4416`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-080-codebase-scan-8af245b6aa1f.md`

## Decision

The evidence-phase transition is a best-effort precursor to document generation.
A transition failure should not abort the document builder because the session
continues through formalization and retains a fallback document packet. It must
not be silent, however: without an observable failure, operators cannot
distinguish a successful phase transition from a broken mediator integration.

The broad exception boundary is therefore retained at this optional integration
point, but it now logs a warning with the session identifier and traceback before
continuing to the direct document-generation handoff.

## Focused Validation

`test_document_generation_logs_evidence_transition_failure_and_continues`
injects a failing evidence-phase transition and verifies that the warning includes
the session and exception while the document builder still completes.

Required syntax validation:

```text
python3 -m py_compile adversarial_harness/session.py
```
