# REF-082 Swallowed Exception Review

Date: 2026-07-22
Source finding: `adversarial_harness/session.py:4449`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-082-codebase-scan-7272a7e35b1f.md`

## Decision

The flagged exception boundary protects an optional graph bootstrap immediately
before document generation. Failures in phase-data access, selector legal-graph
construction, claim matching, or phase-data persistence should not prevent the
document builder and its fallback packet from running. The exception therefore
remains non-fatal, but silently discarding it made broken graph integration
indistinguishable from a handoff that did not require bootstrapping.

The broad boundary is retained for this best-effort integration and now logs a
warning with the adversarial session identifier and traceback before continuing
to document generation.

## Focused Validation

`test_document_generation_logs_formalization_graph_failure_and_continues`
injects a selector legal-graph construction failure and verifies that the warning
includes the session and original exception while the document builder still
completes.

Required syntax validation:

```text
python3 -m py_compile adversarial_harness/session.py
```
