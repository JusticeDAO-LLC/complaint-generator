# REF-109 Swallowed Exception Review

Date: 2026-07-22
Source finding: `examples/codex_autopatch_from_run.py:2596`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-109-codebase-scan-32a191a317c3.md`

## Decision

The flagged path persists rate-limit metadata that the script subsequently
reports as saved and that parent orchestration uses to diagnose rate-limit
exits. A failed write therefore cannot be treated as an optional, best-effort
diagnostic: swallowing it leaves no resumable metadata while misleading callers
with a path to an artifact that does not exist or is incomplete.

Artifact persistence now runs through a focused module-level helper without a
catch-all handler. Filesystem, serialization, and unexpected runtime failures
propagate to the caller instead of allowing the script to announce a nonexistent
artifact or continue into a retry whose state was not recorded. The separate
best-effort transcript append remains outside this finding and is tracked by
REF-110.

## Focused Validation

`tests/test_codex_rate_limit_parsing.py` verifies successful metadata persistence
and confirms that an artifact write failure propagates instead of being silently
swallowed.

Required syntax validation:

```text
python3 -m py_compile examples/codex_autopatch_from_run.py
```
