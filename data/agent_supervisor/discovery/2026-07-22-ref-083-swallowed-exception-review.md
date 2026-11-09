# REF-083 Swallowed Exception Review

Date: 2026-07-22
Source finding: `applications/cli.py:112`
Evidence: `data/refactor_supervisor/discovery/2026-07-22-ref-083-codebase-scan-8418d6dba6f1.md`

## Decision

The current-inquiry payload is an optional source for the interactive prompt. If
the mediator cannot produce that metadata, the CLI should remain usable and fall
back to its generic `Response` prompt. Propagating the exception would terminate
or disrupt an otherwise recoverable interactive session.

The broad exception boundary is therefore retained at this mediator integration
point, but the failure is no longer silent. It now logs a warning with traceback
information before returning the fallback prompt, allowing operators to diagnose
payload regressions without exposing an internal error to the CLI user.

## Focused Validation

`test_resolve_prompt_logs_payload_failure_and_uses_fallback` injects a failing
inquiry-payload provider and verifies both the generic prompt fallback and a
warning containing the original exception.

Required syntax validation:

```text
python3 -m py_compile applications/cli.py
```
