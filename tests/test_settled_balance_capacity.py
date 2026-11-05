"""An aged, dead Grok 402 must not freeze every later task."""
import hashlib
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate.docker_isolation_capacity import capacity_isolating_daemon
from integrations.ipfs_accelerate.settled_balance_capacity import (
    MESSAGE,
    record_is_expired_executed_balance_hold,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

WORKTREE = "/home/barberb/agent-worktrees/complaint-ux/workspace_0123456789abcdef"


def _log(path, body: bytes):
    path.write_bytes(body)
    os.chmod(path, 0o600)
    return path


def _record(log, *, started_at, **overrides):
    raw = log.read_bytes()
    body = {
        "reason": "provider_capacity_settlement_required",
        "returncode": 1,
        "attempt_consumed": True,
        "provider_dispatched": "unknown",
        "providers": ["grok"],
        "callback_outcome": "unknown",
        "retry_authorized": False,
        "settlement_authority": False,
        "completion_authority": False,
        "cleanup_allowed": False,
        "task_id": "CIMP-UX-64",
        "started_at": started_at,
        "worktree_path": WORKTREE,
        "execution_observation": {
            "task_execution_observed": True,
            "terminal_callback_custody": "unknown",
            "tool_event_count": 2,
            "model_calls": 2,
            "turns": 2,
        },
        "log_path": str(log),
        "log_identity": {
            "complete_digest": True,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
        },
    }
    body.update(overrides)
    return body


def _old(now):
    return (now - timedelta(hours=2)).isoformat()


def test_aged_dead_402_does_not_stop_the_scheduler(tmp_path):
    now = datetime.now(timezone.utc)
    log = _log(tmp_path / "attempt.log", f"tool output\n{MESSAGE}\n".encode())
    record = _record(log, started_at=_old(now))
    assert record_is_expired_executed_balance_hold(
        record, now=now, proc_root=tmp_path / "proc",
    )

    class Native:
        _runtime_wake_coordinator = None

        def _retained_provider_capacity_deferral(self):
            return record

        def _run_once(self):
            return {"selected": "CIMP-UX-65"}

        def run_once(self):
            retained = self._retained_provider_capacity_deferral()
            if retained is not None:
                return {"implementation_result": retained}
            return self._run_once()

    daemon = capacity_isolating_daemon(Native)()
    assert daemon._retained_provider_capacity_deferral() is None
    assert daemon.run_once() == {"selected": "CIMP-UX-65"}


def test_fresh_402_still_stops_the_board(tmp_path):
    now = datetime.now(timezone.utc)
    log = _log(tmp_path / "attempt.log", MESSAGE.encode())
    record = _record(log, started_at=(now - timedelta(minutes=5)).isoformat())
    assert record_is_expired_executed_balance_hold(
        record, now=now, proc_root=tmp_path / "proc",
    ) is False

    class Native:
        def _retained_provider_capacity_deferral(self):
            return record

        def run_once(self):
            retained = self._retained_provider_capacity_deferral()
            if retained is not None:
                return {"implementation_result": retained}
            raise AssertionError("fresh 402 reached the scheduler")

    daemon = capacity_isolating_daemon(Native)()
    assert daemon.run_once()["implementation_result"] is record


def test_live_worktree_process_keeps_the_hold(tmp_path):
    now = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
    log = _log(tmp_path / "attempt.log", MESSAGE.encode())
    record = _record(log, started_at=_old(now))
    proc = tmp_path / "proc" / "42"
    proc.mkdir(parents=True)
    (proc / "cmdline").write_bytes(WORKTREE.encode() + b"\0")
    assert record_is_expired_executed_balance_hold(
        record, now=now, proc_root=tmp_path / "proc",
    ) is False


def test_unsealed_log_keeps_the_hold(tmp_path):
    now = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
    log = _log(tmp_path / "attempt.log", MESSAGE.encode())
    record = _record(log, started_at=_old(now))
    record["log_identity"]["sha256"] = "0" * 64
    assert record_is_expired_executed_balance_hold(
        record, now=now, proc_root=tmp_path / "proc",
    ) is False
