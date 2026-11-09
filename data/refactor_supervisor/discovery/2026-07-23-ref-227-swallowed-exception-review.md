# REF-227 Swallowed Exception Review

Date: 2026-07-23
Source finding: `scripts/refactor_agent_supervisor.py:3241`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-227-codebase-scan-968d22551409.md`

## Decision

The daemon intentionally treats PID-file removal as best-effort during shutdown
so a filesystem cleanup problem does not prevent the final status handoff. The
flagged handler was nevertheless defective because it silently discarded every
exception. This concealed a stale PID file from operators and also suppressed
non-filesystem programming errors.

Owned PID-file cleanup now catches only `OSError` and returns an actionable
message containing the path, exception type, and exception message. The daemon
persists that message in both `pid_cleanup_error` and the common `last_error`
status field before exiting. Successful cleanup writes both fields as `null`,
which clears a failure retained in a previous merged status snapshot.
Non-filesystem exceptions propagate normally.

Cleanup still verifies that the PID file belongs to the current process before
removing it, so a replacement daemon's ownership marker cannot be deleted.

## Focused Validation

`tests/test_ref_227_supervisor_pid_cleanup.py` verifies that a PID unlink
permission failure remains non-fatal, preserves the owned PID file, and is
visible in the final status snapshot. It also verifies that a later successful
cleanup clears the prior failure and that a non-filesystem cleanup defect is
not swallowed.

Required syntax validation:

```text
python3 -m py_compile scripts/refactor_agent_supervisor.py
```

Validation results:

- PASS — `python3 -m py_compile scripts/refactor_agent_supervisor.py`
- PASS — `python3 -m pytest tests/test_ref_227_supervisor_pid_cleanup.py -q`
  (3 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
- PASS — `python3 -m pytest tests/test_refactor_agent_supervisor.py -q`
  (38 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
