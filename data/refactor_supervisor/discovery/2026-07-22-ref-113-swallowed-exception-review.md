# REF-113 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_multi_run_autopatch_loop.py:130`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-113-codebase-scan-53b79553b394.md`

## Decision

The child autopatch process prints its summary path only after writing the JSON
artifact. A missing, unreadable, malformed, or non-object advertised summary is
therefore corrupt runtime output rather than an expected optional-file case.
Silently converting all such failures to an unknown orchestrator id allowed the
parent loop to report success, clear its resumable active id, and potentially
commit changes without exposing the broken artifact.

The broad `Exception` handler has been removed so filesystem and JSON failures
propagate for diagnosis. The loader now validates the summary object and the
type of an included `orchestrator_id`, producing path-specific errors for
contract violations. An omitted id still returns `None`, preserving the
caller's existing timestamp fallback and `unknown` status output.

## Focused Validation

`tests/test_codex_multi_run_autopatch_loop_summary.py` covers valid and omitted
ids, rejects invalid summary shapes and id types, and verifies malformed JSON
and unexpected read failures are no longer swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_multi_run_autopatch_loop.py
```
