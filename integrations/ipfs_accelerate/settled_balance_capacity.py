"""Let a finished Grok balance failure stop blocking the rest of the board.

A grok run that already did task work and then exited with HTTP 402 is stored
as retained provider capacity. That record denies every later callback, and
nothing in the record grants settlement. This predicate recognizes only a
sealed, aged, dead-runner observation of that exact error. The caller may
then schedule the next attempt. It does not delete the record, refund the
consumed attempt, clean the quarantine, or grant completion. A fresh 402
still stops the board so the remaining attempts are not burned in a loop.
"""
from __future__ import annotations

import hashlib
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

MESSAGE = (
    "API error (status 402 Payment Required): Grok Build usage balance exhausted"
)
MIN_AGE_SECONDS = 30 * 60
_TAIL_BYTES = 8192
_DENY = (
    "retry_authorized",
    "settlement_authority",
    "completion_authority",
    "cleanup_allowed",
)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def worktree_has_live_process(worktree: str, proc_root: Path) -> bool:
    """True when a process command still names this worktree, or /proc cannot be read."""
    if not worktree.startswith("/") or len(worktree) < 40 or "workspace_" not in worktree:
        return True
    needle = worktree.encode()
    try:
        entries = list(proc_root.iterdir())
    except FileNotFoundError:
        return False
    except OSError:
        return True
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if needle in raw:
            return True
    return False


def _sealed_log_ends_with_balance_error(path: Path, identity: Mapping[str, Any]) -> bool:
    if identity.get("complete_digest") is not True:
        return False
    expected = identity.get("sha256")
    size = identity.get("size")
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    if type(size) is not int or size <= 0 or size > 256 * 1024 * 1024:
        return False
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or info.st_mode & 0o022
            or info.st_size != size
        ):
            return False
        digest = hashlib.sha256()
        remaining = info.st_size
        tail = b""
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                return False
            digest.update(chunk)
            tail = (tail + chunk)[-_TAIL_BYTES:]
            remaining -= len(chunk)
        if digest.hexdigest() != expected:
            return False
    finally:
        os.close(descriptor)
    return MESSAGE.encode() in tail


def record_is_expired_executed_balance_hold(
    record: Mapping[str, Any],
    *,
    now: datetime | None = None,
    proc_root: Path = Path("/proc"),
    min_age_seconds: int = MIN_AGE_SECONDS,
) -> bool:
    """True only for an aged, dead, sealed 402 observation."""
    if not isinstance(record, Mapping) or record.get("custody_error"):
        return False
    if record.get("reason") != "provider_capacity_settlement_required":
        return False
    if type(record.get("returncode")) is not int or record.get("returncode") != 1:
        return False
    if record.get("attempt_consumed") is not True or record.get("provider_dispatched") != "unknown":
        return False
    if record.get("providers") != ["grok"]:
        return False
    if record.get("callback_outcome") != "unknown":
        return False
    if any(record.get(key) is not False for key in _DENY):
        return False
    observation = record.get("execution_observation")
    if not isinstance(observation, Mapping):
        return False
    if observation.get("task_execution_observed") is not True:
        return False
    if observation.get("terminal_callback_custody") != "unknown":
        return False
    for key in ("tool_event_count", "model_calls", "turns"):
        count = observation.get(key)
        if type(count) is not int or count < 1:
            return False
    started = record.get("started_at")
    if not isinstance(started, str):
        return False
    try:
        started_at = _aware(datetime.fromisoformat(started))
    except ValueError:
        return False
    current = _aware(now or datetime.now(timezone.utc))
    if (current - started_at).total_seconds() < min_age_seconds:
        return False
    worktree = record.get("worktree_path")
    log_path = record.get("log_path")
    identity = record.get("log_identity")
    if not isinstance(worktree, str) or not isinstance(log_path, str):
        return False
    if not log_path.startswith("/") or not isinstance(identity, Mapping):
        return False
    if worktree_has_live_process(worktree, proc_root):
        return False
    return _sealed_log_ends_with_balance_error(Path(log_path), identity)
