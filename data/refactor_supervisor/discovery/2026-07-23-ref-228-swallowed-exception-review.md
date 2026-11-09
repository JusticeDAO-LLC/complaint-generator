# REF-228 Swallowed Exception Review

Date: 2026-07-23
Source finding: `scripts/refactor_agent_supervisor.py:4008`
Evidence: `/home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-228-codebase-scan-bdd4ee0fdbaf.md`

## Decision

The merge resolver watchdog owns a PID file that should be removed when the
watchdog exits. PID cleanup must remain best-effort so a filesystem permission
or race failure does not replace the watchdog's primary result. The flagged
handler was defective because it silently discarded every exception. That can
leave a stale PID file while giving operators no indication that lifecycle
state is degraded, and it also concealed non-filesystem programming defects.

The handler now catches only `OSError`. A filesystem failure is recorded as
structured `pid_cleanup_error` data in both the returned result and the durable
watchdog status, and is emitted to the watchdog log. Unexpected non-filesystem
exceptions propagate instead of being hidden.

## Focused Validation

`tests/test_ref_228_merge_watchdog_cleanup.py` verifies that a PID-file
permission failure remains non-fatal, retains the stale file for diagnosis,
and records its path, exception type, and message in the result, durable status,
and log. It also verifies that a non-filesystem cleanup defect propagates.

Required syntax validation:

```text
python3 -m py_compile scripts/refactor_agent_supervisor.py
```

Validation results:

- PASS — `python3 -m py_compile scripts/refactor_agent_supervisor.py`
- PASS — `python3 -m pytest tests/test_ref_228_merge_watchdog_cleanup.py -q`
  (2 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
- PASS — `python3 -m pytest tests/test_refactor_agent_supervisor.py tests/test_ref_228_merge_watchdog_cleanup.py -q`
  (40 passed, 1 unrelated pytest-asyncio configuration deprecation warning)
