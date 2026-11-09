"""Read-only, bounded liveness for Native's same-attempt provider repair.

Activity is not completion, semantic work progress, or a renewed execution
lease. The provider remains subject to Native's original absolute deadline.
"""
from __future__ import annotations

from collections import Counter
import json
import math
import os
from pathlib import Path
import stat
import time


_MARKER = b"[auto-rescue] inline_provider_rescue start"
_CLOSE = (b"[auto-rescue] inline_provider_rescue returncode=",
          b"[auto-rescue] inline_provider_rescue error:")
_WORK = frozenset({"usage", "tool_call", "tool_call_update"})
_ACTIVITY = _WORK | {"thought", "text"}
_REASONS = frozenset({"not_active_rescue", "rescue_held", "native_owner_unavailable",
    "native_binding_unavailable", "native_owner_command_changed", "provider_deadline_unavailable",
    "provider_deadline_expired", "primary_start_unavailable", "primary_start_unbound", "attempt_finished",
    "rescue_start_unavailable", "rescue_start_unbound", "rescue_time_unbound", "rescue_closed",
    "provider_pid_invalid", "provider_birth_unbound", "provider_uid_unbound", "provider_workspace_unbound",
    "provider_session_unbound", "provider_stdout_unbound", "provider_event_birth_unbound", "provider_birth_changed",
    "log_custody_invalid", "log_prefix_truncated", "log_prefix_changed", "log_custody_changed",
    "rescue_log_stale", "log_header_ambiguous", "log_header_unbound", "rescue_frame_incomplete",
    "rescue_marker_unbound", "rescue_terminal", "rescue_activity_unavailable", "native_binding_changed",
    "bounded_native_rescue_activity", "rescue_observation_unavailable", "native_state_unbound", "native_state_changed"})


def summary(value):
    """Closed private/journal metadata; no paths, argv, lease or text fields."""
    if value is None:
        value = {"reason":"not_active_rescue"}
    value = value if type(value) is dict else {}
    reason = value.get("reason")
    result = {"activity_verified": value.get("activity_verified") is True,
        "work_progress_verified": value.get("work_progress_verified") is True,
        "reason": reason if type(reason) is str and reason in _REASONS else "rescue_observation_unavailable"}
    for key in ("deadline_at", "rescue_started_at"):
        item = value.get(key)
        if type(item) in (int,float) and math.isfinite(item) and 0 <= item < 2**53:
            result[key] = item
    for key in ("attempt", "log_device", "log_inode", "log_bytes", "log_mtime_ns"):
        item = value.get(key)
        if type(item) is int and 0 <= item < 2**63:
            result[key] = item
    for key in ("owner_birth", "provider_birth"):
        item = value.get(key)
        if type(item) is dict:
            safe = {name:item[name] for name in ("pid","start_time_ticks","parent_pid")
                if type(item.get(name)) is int and 0 <= item[name] < 2**63}
            if safe:result[key] = safe
    counts = value.get("frame_counts")
    if type(counts) is dict:
        result["frame_counts"] = {key:counts[key] for key in sorted(_ACTIVITY)
            if type(counts.get(key)) is int and 0 <= counts[key] < 1_000_000_000}
    if type(value.get("last_frame_kind")) is str and value["last_frame_kind"] in _ACTIVITY:
        result["last_frame_kind"] = value["last_frame_kind"]
    return result


class _Unavailable(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise _Unavailable(code)


def _append_prefix(path, *, maximum=32 * 1024 * 1024):
    """Read one owned complete prefix while allowing verified append growth.

    This is only for the live Native stdout log. Immutable authority readers
    remain strict. Re-read the captured prefix to reject in-place mutation;
    replacement, truncation, aliases and changed custody are never append.
    """
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_uid", "st_mode", "st_nlink")
        _require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                 and before.st_nlink == 1 and not before.st_mode & 0o022
                 and 0 < before.st_size <= maximum, "log_custody_invalid")
        def read():
            pieces, offset = [], 0
            while offset < before.st_size:
                data = os.pread(descriptor, min(1_048_576, before.st_size-offset), offset)
                _require(bool(data), "log_prefix_truncated")
                pieces.append(data); offset += len(data)
            return b"".join(pieces)
        raw = read()
        _require(read() == raw, "log_prefix_changed")
        after, current = os.fstat(descriptor), path.lstat()
        _require(all(getattr(item, key) == getattr(before, key)
                     for item in (after, current) for key in fields)
                 and after.st_size >= before.st_size and current.st_size >= before.st_size
                 and after.st_mtime_ns >= before.st_mtime_ns
                 and current.st_mtime_ns >= before.st_mtime_ns,
                 "log_custody_changed")
        return raw, before
    finally:
        os.close(descriptor)


def _provider_birth(native, pid, owner, workspace, log_identity, event_time):
    _require(type(pid) is int and pid > 1 and pid != owner.pid, "provider_pid_invalid")
    birth = native.read_process_birth(pid)
    _require(birth is not None and birth.start_time_ticks > 0
             and birth.boot_id == owner.boot_id and birth.parent_pid == owner.pid,
             "provider_birth_unbound")
    process = Path("/proc") / str(pid)
    _require(process.stat().st_uid == os.getuid(), "provider_uid_unbound")
    _require(Path(os.readlink(process / "cwd")) == workspace, "provider_workspace_unbound")
    _require(os.getsid(pid) == pid and os.getpgid(pid) == pid, "provider_session_unbound")
    for number in (1, 2):
        info = (process / "fd" / str(number)).stat()
        _require((info.st_dev, info.st_ino) == tuple(log_identity), "provider_stdout_unbound")
    # Native's callback records a PID, not its birth. Join the observed kernel
    # birth to that actual start callback, rather than inventing a saved birth.
    boot = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                if line.startswith("btime "))
    born_at = boot + birth.start_time_ticks / os.sysconf("SC_CLK_TCK")
    _require(event_time - 2 <= born_at <= event_time + 0.1, "provider_event_birth_unbound")
    _require(native.read_process_birth(owner.pid) == owner
             and native.read_process_birth(pid) == birth, "provider_birth_changed")
    return birth


def observe(runner, repo_root, campaign, state, *, now_ts):
    """Return only closed diagnostic metadata; never argv or provider content."""
    report = {"source": "owned_native_auto_rescue", "activity_verified": False,
              "work_progress_verified": False, "reason": "not_active_rescue",
              "completion_authority": False}
    try:
        _require(state.get("active_phase") == "validating"
                 and state.get("implementation_in_progress") is True, "not_active_rescue")
        _require(not any(state.get(key) for key in
            ("manual_hold", "manual_cancellation", "capacity_quarantine", "protected_incident")),
            "rescue_held")
        context = {"campaign_state_dir": str(campaign), "target_source_root": str(repo_root),
            "task_id": state.get("active_task_id"), "task_cid": state.get("active_task_cid"),
            "task_key": state.get("active_task_key")}
        daemon, native, _ = runner._validation_activity_modules()
        identity = native.load_supervised_child_identity(campaign / (runner.STATE_PREFIX + "_managed_daemon.identity.json"))
        _require(identity is not None, "native_owner_unavailable")
        owner = identity.process_birth
        binding = runner._validation_activity_binding(Path(state.get("active_worktree_path") or ""),
            {"id": context["task_id"]}, context, now_ts=now_ts, owner_pid=owner.pid)
        _require(binding is not None, "native_binding_unavailable")
        snapshot = runner._validation_activity_snapshot(campaign)
        current = snapshot.get("body") if isinstance(snapshot,dict) else None
        state_keys = ("active_task_id","active_task_cid","active_task_key","active_attempt",
            "active_task_started_at","active_phase","active_phase_started_at","active_log_path","active_worktree_path",
            "last_implementation_task_id","last_implementation_task_cid","last_implementation_task_key",
            "last_implementation_started_at","last_implementation_log_path","last_implementation_worktree_path",
            "implementation_in_progress","manual_hold","manual_cancellation","capacity_quarantine","protected_incident")
        _require(isinstance(current,dict) and all(state.get(key)==current.get(key) for key in state_keys),
                 "native_state_unbound")
        _require(type(state.get("active_attempt")) is int and state["active_attempt"] == binding["attempt"]
                 and state.get("active_phase_started_at") == binding["phase_started_at"]
                 and state.get("active_log_path") == state.get("last_implementation_log_path") == binding["log_path"],
                 "native_state_unbound")
        _require(native.read_process_command_argv(owner.pid) == identity.command
                 and native.supervised_child_identity_liveness(identity) is native.OwnerLiveness.ALIVE,
                 "native_owner_command_changed")
        report.update(task_id=binding["task_id"], task_cid=binding["canonical_task_cid"],
            attempt=binding["attempt"], owner_birth=owner.to_dict())
        start_times = [runner._event_timestamp({"timestamp": state.get(key)})
            for key in ("active_task_started_at", "last_implementation_started_at")]
        _require(all(value is not None for value in start_times), "provider_deadline_unavailable")
        from .improvement_recovery import _owned_bytes
        from ipfs_accelerate_py.agent_supervisor.todo_daemon.current_incident_adjudication import _event_rows
        event_path = campaign / (runner.STATE_PREFIX + "_events.jsonl")
        rows = _event_rows(_owned_bytes(event_path, runner.MAX_EVENT_HISTORY_BYTES, legacy_group_write=True))
        starts = [i for i, row in enumerate(rows) if row.get("type") == "implementation_started"]
        _require(bool(starts), "primary_start_unavailable")
        index, primary = starts[-1], rows[starts[-1]]
        same = {"task_id": binding["task_id"], "canonical_task_cid": binding["canonical_task_cid"],
                "canonical_task_key": binding["canonical_task_key"], "attempt": binding["attempt"]}
        def joined(row):
            return all(row.get(key) == value for key, value in same.items())
        primary_time = runner._event_timestamp(primary)
        exact_starts = [row for row in rows if row.get("type") == "implementation_started"
                        and joined(row) and row.get("worktree_path") == binding["workspace"]
                        and row.get("log_path") == binding["log_path"]]
        _require(joined(primary) and primary.get("execution_mode") == "model-assisted"
                 and primary.get("worktree_path") == binding["workspace"]
                 and primary.get("log_path") == binding["log_path"]
                 and len(exact_starts) == 1 and primary_time is not None
                 and start_times[0] <= start_times[1] <= primary_time <= now_ts + 2, "primary_start_unbound")
        # Native creates its fixed provider deadline after checkout and this
        # execution-start event. Selection/log-header times precede setup.
        # The phase cap and existing 900-second ceiling remain unchanged;
        # duplicate starts cannot renew this conservative observation window.
        deadline = min(binding["phase_deadline"], primary_time + runner.TIMEOUT_SECONDS)
        report["deadline_at"] = deadline
        report["deadline_basis"] = "canonical_native_execution_event_and_phase_cap"
        _require(now_ts < deadline, "provider_deadline_expired")
        subsequent = rows[index+1:]
        _require(not any(row.get("type") == "implementation_finished" and joined(row) for row in subsequent),
                 "attempt_finished")
        prepared = [row for row in subsequent if row.get("type") == "implementation_auto_rescue_provider_prepared"]
        started = [row for row in subsequent if row.get("type") == "implementation_auto_rescue_provider_started"]
        _require(len(prepared) == len(started) == 1, "rescue_start_unavailable")
        ready, born = prepared[0], started[0]
        _require(joined(ready) and joined(born) and ready.get("strategy_changed") is True
                 and born.get("strategy_changed") is True
                 and ready.get("board_namespace") == primary.get("board_namespace") == born.get("board_namespace")
                 and isinstance(ready.get("plan"), dict)
                 and ready["plan"].get("action") in {"inline_provider_rescue", "remediate_scoped_test_secret"}
                 and all(born.get(key) == ready.get(key) for key in
                         ("base_prompt_id", "rescue_prompt_id", "plan"))
                 and bool(ready.get("base_prompt_id")) and bool(ready.get("rescue_prompt_id"))
                 and ready["base_prompt_id"] != ready["rescue_prompt_id"], "rescue_start_unbound")
        event_time, prepared_time = runner._event_timestamp(born), runner._event_timestamp(ready)
        _require(event_time is not None and prepared_time is not None
                 and primary_time <= prepared_time <= event_time <= now_ts + 2,
                 "rescue_time_unbound")
        _require(not any(row.get("type") in {"implementation_auto_rescue_provider_failed",
                "implementation_auto_rescue_provider_blocked"}
                and joined(row) and runner._event_timestamp(row) >= event_time for row in subsequent),
                "rescue_closed")
        workspace, log = Path(binding["workspace"]), Path(binding["log_path"])
        provider = _provider_birth(native, born.get("provider_pid"), owner, workspace,
                                   binding["log_identity"], event_time)
        raw, info = _append_prefix(log)
        _require((info.st_dev, info.st_ino) == tuple(binding["log_identity"]), "log_custody_changed")
        report.update(provider_birth=provider.to_dict(), rescue_started_at=event_time,
            log_device=info.st_dev, log_inode=info.st_ino, log_bytes=len(raw), log_mtime_ns=info.st_mtime_ns)
        observed_now = max(now_ts, time.time())
        _require(observed_now < deadline, "provider_deadline_expired")
        _require(0 <= observed_now - info.st_mtime <= runner.STALL_SECONDS, "rescue_log_stale")
        headers = {}
        for line in raw.splitlines()[:8]:
            key, sep, value = line.partition(b": ")
            if sep and key in {b"Task", b"Started", b"Workspace"}:
                _require(key not in headers, "log_header_ambiguous")
                headers[key] = value.decode("utf8")
        _require(headers.get(b"Task", "").split(" ", 1)[0] == binding["task_id"]
                 and headers.get(b"Started") == state["last_implementation_started_at"]
                 and headers.get(b"Workspace") == binding["workspace"], "log_header_unbound")
        _require(raw.endswith(b"\n"), "rescue_frame_incomplete")
        lines = raw.splitlines()
        markers = [i for i, line in enumerate(lines) if line == _MARKER]
        _require(len(markers) == 1, "rescue_marker_unbound")
        segment = lines[markers[0]+1:]
        _require(not any(line.startswith(_CLOSE) for line in segment), "rescue_closed")
        counts, last = Counter(), None
        for line in segment:
            try:
                frame = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                last = None; continue
            kind = frame.get("type") if isinstance(frame, dict) else None
            if kind in {"end", "error", "max_turns_reached"}:
                raise _Unavailable("rescue_terminal")
            if kind in _ACTIVITY and (kind != "usage" or isinstance(frame.get("usage"), dict)):
                counts[kind] += 1; last = kind
            else:
                last = None
        _require(last in _ACTIVITY, "rescue_activity_unavailable")
        _require(_provider_birth(native, born["provider_pid"], owner, workspace,
                binding["log_identity"], event_time) == provider, "provider_birth_changed")
        fresh = runner._validation_activity_binding(workspace, {"id": context["task_id"]}, context,
                                                   now_ts=max(now_ts,time.time()), owner_pid=owner.pid)
        _require(fresh == binding, "native_binding_changed")
        final_snapshot = runner._validation_activity_snapshot(campaign)
        final_state = final_snapshot.get("body") if isinstance(final_snapshot,dict) else None
        _require(isinstance(final_state,dict) and all(final_state.get(key)==current.get(key) for key in state_keys),
                 "native_state_changed")
        _require(max(now_ts,time.time()) < deadline, "provider_deadline_expired")
        report.update(activity_verified=True, work_progress_verified=last in _WORK,
            frame_counts=dict(counts), last_frame_kind=last, reason="bounded_native_rescue_activity")
    except _Unavailable as exc:
        report["reason"] = str(exc)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, StopIteration, RuntimeError):
        report["reason"] = "rescue_observation_unavailable"
    return report
