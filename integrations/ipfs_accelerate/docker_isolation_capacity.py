"""Keep one pre-dispatch Docker image miss from freezing the whole board.

The runner sentence "Default Grok quota route requires the pinned local
Docker isolation image" names the local isolation route. The capacity
classifier also matches the words "Grok quota", so a failed image inspect is
stored as retained provider capacity. That record denies every later
callback. This wrapper lets the ordinary scheduler continue for that exact
log and no other capacity record. It does not delete the record, refund the
consumed attempt, clean the quarantined worktree, or grant completion.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Mapping

from .settled_balance_capacity import record_is_expired_executed_balance_hold

MESSAGE = (
    "Default Grok quota route requires the pinned local Docker isolation image"
)
_HEADER_PREFIXES = (
    "Task:",
    "Started:",
    "Workspace:",
    "Branch:",
    "Baseline:",
    "Command:",
)
_MAX_LOG_BYTES = 16 * 1024
_DENY = (
    "retry_authorized",
    "settlement_authority",
    "completion_authority",
    "cleanup_allowed",
)


def log_is_docker_isolation_miss(path: Path) -> bool:
    """True only when the owned log's sole diagnostic is the image miss."""
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
            or not 0 < info.st_size <= _MAX_LOG_BYTES
        ):
            return False
        raw = os.read(descriptor, _MAX_LOG_BYTES + 1)
        if len(raw) != info.st_size:
            return False
    finally:
        os.close(descriptor)
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return False
    lowered = text.lower()
    if any(token in lowered for token in (
            "rate limit", "rate_limit", "usage limit", "usage balance",
            "balance exhausted", "payment required", "resource exhausted",
            "too many requests", "429", "402")):
        return False
    diagnostics = [
        line.strip() for line in text.splitlines()
        if line.strip() and not line.strip().startswith(_HEADER_PREFIXES)
    ]
    return diagnostics == [MESSAGE]


def record_is_docker_isolation_miss(record: Mapping[str, Any]) -> bool:
    """True only for the retained observation of that same image miss."""
    if not isinstance(record, Mapping) or record.get("custody_error"):
        return False
    if record.get("reason") != "provider_capacity_settlement_required":
        return False
    if type(record.get("returncode")) is not int or record.get("returncode") != 2:
        return False
    if record.get("attempt_consumed") is not True or record.get("provider_dispatched") != "unknown":
        return False
    if record.get("providers") != ["grok"]:
        return False
    if any(record.get(key) is not False for key in _DENY):
        return False
    observation = record.get("execution_observation")
    if (not isinstance(observation, Mapping)
            or observation.get("task_execution_observed") is not False
            or any(observation.get(key) not in (0, None) for key in ("tool_event_count", "model_calls", "turns"))
            or any(type(observation.get(key)) is not int or observation.get(key) != 0
                   for key in ("tool_event_count", "model_calls", "turns") if key in observation)):
        return False
    if any(key not in observation for key in ("tool_event_count", "model_calls", "turns")):
        return False
    log_path = record.get("log_path")
    if not isinstance(log_path, str) or not Path(log_path).is_absolute():
        return False
    return log_is_docker_isolation_miss(Path(log_path))


def capacity_isolating_daemon(native_class):
    """Return a daemon that does not let this one miss deny the board."""

    class CapacityIsolatingDaemon(native_class):
        def _retained_provider_capacity_deferral(self):
            record = super()._retained_provider_capacity_deferral()
            if (getattr(self, "_docker_isolation_miss_attempt_open", False)
                    and record is not None
                    and record_is_docker_isolation_miss(record)):
                return None
            if record is not None and record_is_expired_executed_balance_hold(record):
                return None
            return record

        def _provider_capacity_failure_from_log(self, log_path, *, command=(), returncode=None):
            if log_is_docker_isolation_miss(Path(log_path)):
                return {
                    "exhausted": False,
                    "providers": [],
                    "reason": "",
                    "pre_dispatch_refusal_verified": False,
                    "retained_callback_required": False,
                }
            return super()._provider_capacity_failure_from_log(
                log_path, command=command, returncode=returncode)

        def _run_implementation(self, task, state):
            record = native_class._retained_provider_capacity_deferral(self)
            # The same miss also blocks every later ready task. Native returns
            # the retained record before dispatch unless it is hidden for this
            # call only. The record, quarantine, and attempt stay in place.
            if record is not None and record_is_docker_isolation_miss(record):
                self._docker_isolation_miss_attempt_open = True
                try:
                    return super()._run_implementation(task, state)
                finally:
                    self._docker_isolation_miss_attempt_open = False
            return super()._run_implementation(task, state)

        def run_once(self, *args, **kwargs):
            record = native_class._retained_provider_capacity_deferral(self)
            if record is not None and record_is_docker_isolation_miss(record):
                result = self._run_once()
                coordinator = self._runtime_wake_coordinator
                if coordinator is not None:
                    synchronize = getattr(coordinator, "synchronize_file_cursors", None)
                    if callable(synchronize):
                        synchronize()
                return result
            return super().run_once(*args, **kwargs)

    return CapacityIsolatingDaemon
