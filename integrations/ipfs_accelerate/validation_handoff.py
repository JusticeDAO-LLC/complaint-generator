"""A fixed, owner-bound interval for Native to journal a returned validation.

This observation grants no provider, validation, attempt or completion
authority. Its only purpose is to avoid fencing the exact Native controller
between its executor returning and its terminal receipt becoming durable.
"""
from __future__ import annotations

import math
import os
import re

GRACE_SECONDS = 30.0
SCHEMA = "complaint-owned-validation-handoff@1"


def _path(runner, binding, *, create=False):
    active = runner._validation_activity_path(binding, create=create)
    return active.with_name(active.stem + ".handoff.json")


def valid(runner, value, binding, *, now_ts):
    from .improvement_plan import _digest

    if (not isinstance(value, dict) or value.get("schema") != SCHEMA
            or value.get("state") != "settled" or value.get("completion_authority") is not False
            or re.fullmatch(r"[0-9a-f]{32}", str(value.get("activity_id", ""))) is None
            or value.get("binding_sha256") != _digest(binding)
            or _digest(value.get("binding")) != _digest(binding)):
        return False
    numbers = [value.get(key) for key in ("started_at", "settled_at", "deadline_at")]
    if any(isinstance(number, bool) or not isinstance(number, (int, float))
           or not math.isfinite(number) for number in [now_ts, *numbers]):
        return False
    started, settled, deadline = numbers
    phase_deadline = binding.get("phase_deadline")
    if (isinstance(phase_deadline, bool) or not isinstance(phase_deadline, (int, float))
            or not math.isfinite(phase_deadline)):
        return False
    return bool(phase_deadline - runner.TIMEOUT_SECONDS <= started <= settled <= now_ts < deadline
                and deadline <= min(phase_deadline, started + runner.TIMEOUT_SECONDS, settled + GRACE_SECONDS))


def publish(runner, binding, *, activity_id, started_at, settled_at, deadline_at):
    """Called once by the canonical executor's finally block, under its inode guard."""
    from .improvement_plan import _digest

    # A descendant/tool cannot publish on the Native controller's behalf.
    _daemon, native, _plane = runner._validation_activity_modules()
    birth = native.ProcessBirthIdentity.from_dict(binding.get("owner_birth"))
    if birth.pid != os.getpid() or native.read_process_birth(os.getpid()) != birth:
        return False

    value = {"schema": SCHEMA, "state": "settled", "activity_id": activity_id,
             "binding": binding, "binding_sha256": _digest(binding),
             "started_at": started_at, "settled_at": settled_at,
             "deadline_at": min(deadline_at, binding["phase_deadline"], settled_at + GRACE_SECONDS),
             "completion_authority": False}
    if not valid(runner, value, binding, now_ts=settled_at):
        return False
    path = _path(runner, binding, create=True)
    if path.exists() or path.is_symlink():
        previous = runner._read_validation_activity(path)
        # Re-observing a returned command can never renew its handoff. A
        # subsequent genuine command must have started after the old return.
        if (previous.get("activity_id") == activity_id
                or not valid(runner, previous, binding, now_ts=previous.get("settled_at"))
                or started_at < previous["settled_at"]):
            return False
    runner._atomic_json(path, value)
    return True


def read(runner, binding, *, now_ts):
    try:
        value = runner._read_validation_activity(_path(runner, binding))
        return value if valid(runner, value, binding, now_ts=now_ts) else None
    except (OSError, ValueError, TypeError, KeyError):
        return None


def owned(runner, supervisor, state, *, now_ts, owner_pid):
    """Reprove the ordinary canonical owner; the receipt alone is insufficient."""
    from pathlib import Path

    try:
        if any(getattr(state, key, False) for key in
               ("manual_hold", "manual_cancellation", "capacity_quarantine", "protected_incident")):
            return False
        context = {"campaign_state_dir": str(supervisor.config.state_dir),
                   "target_source_root": str(supervisor.config.repo_root),
                   "task_id": state.active_task_id, "task_cid": state.active_task_cid,
                   "task_key": state.active_task_key}
        binding = runner._validation_activity_binding(Path(state.active_worktree_path),
            {"id": state.active_task_id}, context, now_ts=now_ts, owner_pid=owner_pid)
        return binding is not None and read(runner, binding, now_ts=now_ts) is not None
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return False
