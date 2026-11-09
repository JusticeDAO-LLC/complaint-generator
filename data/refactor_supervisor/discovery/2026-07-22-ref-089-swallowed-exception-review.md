# REF-089 Swallowed Exception Review

Date: 2026-07-22
Source finding: `adversarial_harness/session.py:4409`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-089-codebase-scan-8a0485e56dc3.md`

## Decision

The flagged boundary confirms the intake summary before the adversarial session
hands off to evidence, formalization, and document generation. Confirmation is a
best-effort compatibility hook: mediators without the hook are supported, and a
confirmation failure must not prevent the document builder from producing a
useful result. Silently swallowing a failure here hid state-transition problems
and made a document package appear to follow a clean handoff when it did not.

The handoff now logs a warning with the adversarial session identifier and full
exception context, then preserves the existing direct document-generation
fallback. This matches the observability and recovery behavior of the adjacent
evidence and formalization transition boundaries.

## Focused Validation

`test_document_generation_logs_intake_confirmation_failure_and_continues`
injects a confirmation failure and verifies that the document package is still
built while the warning records the session and original exception.

Required syntax validation:

```text
python3 -m py_compile adversarial_harness/session.py
```
