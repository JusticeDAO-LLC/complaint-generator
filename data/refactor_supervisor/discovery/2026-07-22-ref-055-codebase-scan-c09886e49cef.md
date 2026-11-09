# REF-055 Codebase Scan Finding

Date: 2026-07-22
Fingerprint: c09886e49ceff0bb016d4a0033dc17178969291d
Kind: swallowed_exception
Source: adversarial_harness/harness.py:879
Priority: P1
Track: runtime

## Evidence

```text
except Exception:
```

## Suggested Handling

Review the finding in context, decide whether it represents a bug, missing test,
maintenance risk, or false positive, and land a small fix with validation. If the
finding is a false positive, document why in the changed code or discovery notes
so the supervisor does not keep re-adding the same work.

## Resolution

The finding identified a real session-initialization bug. The harness proactively
creates three session-scoped DuckDB containers before constructing mediator
hooks, but the blanket handler silently discarded every import, connection, and
filesystem failure. The session then continued with missing or partially created
databases even though persistence reports those files as expected artifacts.

Database creation now runs in a focused helper without an exception fallback.
DuckDB is a declared runtime dependency, and a configured database that cannot be
opened is not optional, so the existing `_run_single_session` error boundary now
turns such a failure into an explicit failed `SessionResult`, logs its traceback,
and writes failed session progress. Sessions without a state directory skip
database initialization and do not import DuckDB.

## Focused Validation

`tests/test_ref_055_harness_duckdb_initialization.py` verifies that all configured
database connections are created and closed, unconfigured paths do no work,
connection failures propagate from the helper, and the session runner records a
DuckDB initialization error without constructing a mediator.

Required syntax validation:

```text
python3 -m py_compile adversarial_harness/harness.py
```
