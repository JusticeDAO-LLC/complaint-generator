"""Observe Native's durable selector backoff without changing its deadline.

A scheduled retry is neither work progress nor a renewed attempt. This observer
reads existing queue/journal metadata only; Native's selector helpers can release
cooldowns and must never be called by status or the watchdog.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import time

from .auto_rescue_activity import _append_prefix


class _Unavailable(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise _Unavailable(reason)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value < 2**53


def _ids(value):
    return (type(value) is list and 0 < len(value) <= 256
            and all(type(item) is str and 0 < len(item) <= 256 for item in value)
            and len(set(value)) == len(value))


def _read(path, maximum):
    raw, _ = _append_prefix(path, maximum=maximum)
    return raw


def summary(value):
    """Closed metadata only; never export journal content, notes, paths or argv."""
    value = value if type(value) is dict else {}
    result = {"schema": "complaint-native-retry-cooldown@1",
        "verified": value.get("verified") is True, "progress_verified": False,
        "completion_authority": False}
    if result["verified"]:
        result.update(reason="bounded_native_retry_cooldown", retry_at=value["retry_at"],
            task_ids=list(value["task_ids"]), tasks=[dict(item) for item in value["tasks"]],
            queue_sha256=value["queue_sha256"])
    else:
        result["reason"] = "retry_cooldown_unavailable"
    return result


def observe(runner, repo_root, state_dir, record, native, heartbeat, board, *,
            spec, artifacts, current_state, now_ts=None):
    """Prove all selectable ready work is within its original failure backoff.

    Ordinary failed-attempt cooldowns have an existing finished-event producer.
    No-change/authority-renewal/deferred schedules without a bound outcome
    receipt are deliberately unavailable, rather than guessed from file age.
    """
    now = time.time() if now_ts is None else now_ts
    result = {"verified": False, "progress_verified": False, "completion_authority": False}
    try:
        _require(_number(now) and current_state and not board.get("read_error"), "state_unavailable")
        _require(not any(native.get(key) for key in (
            "implementation_in_progress", "active_task_id", "active_task_cid", "active_task_key",
            "active_attempt", "active_phase", "active_task_started_at", "active_log_path",
            "active_worktree_path", "active_branch", "active_provider_runner", "manual_hold",
            "manual_cancellation", "capacity_quarantine", "protected_incident")), "active_or_held")
        _require(not board.get("manual_hold_task_ids") and not runner._claim_proof_conflict(native)
            and str(native.get("dependency_status") or "").lower() not in {
                "unavailable", "temporary_unavailable", "degraded"}, "held_or_source_conflict")
        state_dir, repo_root = Path(state_dir), Path(repo_root)
        _require(not any(os.path.lexists(state_dir / "watchdog" / name)
            for name in ("HOLD", "OPERATOR_STOP")), "operator_hold")
        _require(record.get("status") in {"starting", "running"}
            and runner.owns_process(record), "owner_unavailable")
        from .improvement_plan import source_generation
        _require(record.get("source_generation") == source_generation(spec)
            and record.get("plan_id") == runner._requested_plan_id(Path(record["spec_path"]))
            and record.get("repo_root") == str(repo_root)
            and record.get("state_dir") == str(state_dir)
            and record.get("board_path") == str(repo_root / artifacts.board_relative), "source_unbound")
        owner = record["identity"]
        daemon = runner.process_identity(heartbeat.get("daemon_pid"))
        _require(daemon and daemon.get("ppid") == owner["pid"]
            and heartbeat.get("supervisor_pid") == owner["pid"]
            and heartbeat.get("status") == "running" and heartbeat.get("daemon_pid_alive") is True
            and heartbeat.get("active_worker_count") == 0
            and heartbeat.get("active_worker_pids") == [], "daemon_unavailable")
        _require(all((Path("/proc") / str(pid)).stat().st_uid == os.getuid()
            for pid in (owner["pid"], daemon["pid"])), "process_custody_invalid")
        child_record = json.loads(_read(state_dir / (runner.STATE_PREFIX + "_managed_daemon.identity.json"), 32768))
        scope = child_record.get("owner_scope") or {}
        _require(child_record.get("schema") == "ipfs_accelerate_py.agent_supervisor.supervised-child-identity@1"
            and child_record.get("command") == daemon.get("argv")
            and scope.get("repo_root") == str(repo_root) and scope.get("state_dir") == str(state_dir)
            and scope.get("todo_path") == str(repo_root / artifacts.board_relative), "daemon_command_unbound")
        heartbeat_path = state_dir / (runner.STATE_PREFIX + "_supervisor_status.json")
        heartbeat_stamp = runner._event_timestamp({"timestamp": heartbeat.get("updated_at")})
        _require(heartbeat_stamp is not None and 0 <= now - heartbeat_stamp <= 120
            and 0 <= now - heartbeat_path.stat().st_mtime <= 120, "heartbeat_stale")
        # Settled PortalTaskState has no owner_process_birth field. Native's
        # separately published supervised-child receipt owns that binding.
        birth = child_record.get("process_birth") or {}
        _require(all(birth.get(k) == daemon.get(v) for k, v in (
            ("pid", "pid"), ("parent_pid", "ppid"), ("start_time_ticks", "start_ticks"),
            ("boot_id", "boot_id"))), "daemon_birth_unbound")
        children = Path("/proc") / str(daemon["pid"]) / "task" / str(daemon["pid"]) / "children"
        _require(not children.read_text().strip(), "worker_present")
        selectable = native.get("selectable_ready_task_ids")
        _require(_ids(selectable) and _ids(board.get("ready_task_ids"))
            and set(selectable) == set(board["ready_task_ids"])
            and set(selectable) <= set(native.get("ready_task_ids") or [])
            and set(selectable) <= set(native.get("eligible_ready_task_ids") or []), "ready_work_unbound")
        maximum = heartbeat.get("max_task_attempts")
        _require(type(maximum) is int and maximum == 3, "attempt_policy_unbound")
        _, daemon_module = runner._native_modules(repo_root)
        parsed = list(daemon_module.parse_task_file(repo_root / artifacts.board_relative,
            task_header_prefix=runner.TASK_PREFIX))
        board_tasks = {task.task_id: task for task in parsed}
        _require(0 < len(parsed) <= 256 and len(board_tasks) == len(parsed), "board_identity_unavailable")
        queue_path = state_dir / "task_queue.json"
        queue_raw = _read(queue_path, 2_000_000)
        queue = json.loads(queue_raw)
        _require(type(queue) is dict and queue.get("schema") == "persistent_task_queue_v3"
            and type(queue.get("entries")) is dict and len(queue["entries"]) <= 4096
            and type(queue.get("aliases")) is dict, "queue_unavailable")
        events_path = state_dir / (runner.STATE_PREFIX + "_events.jsonl")
        journal = _read(events_path, 32 * 1024 * 1024)
        _require(journal.endswith(b"\n"), "journal_incomplete")
        events = [json.loads(line) for line in journal.splitlines() if line]
        _require(all(type(event) is dict for event in events), "journal_invalid")
        identities = native.get("task_identities") or {}
        tasks = []
        for task_id in sorted(selectable):
            identity = identities.get(task_id) or {}
            cid, key = identity.get("canonical_task_cid"), identity.get("canonical_task_key")
            namespace = identity.get("board_namespace")
            board_task = board_tasks.get(task_id)
            _require(type(cid) is str and cid.startswith("b") and type(key) is str
                and key.startswith("task/v1/") and queue["aliases"].get(task_id) == cid
                and namespace == Path(artifacts.board_relative).name
                and board_task is not None and board_task.canonical_task_cid == cid
                and board_task.canonical_task_key == key, "identity_unbound")
            entry = queue["entries"].get(cid) or {}
            _require(entry.get("task_id") == task_id and entry.get("canonical_task_cid") == cid
                and entry.get("canonical_task_key") == key
                and any(type(item) is dict and item.get("display_task_id") == task_id
                    and item.get("source_path") == str(repo_root / artifacts.board_relative)
                    and item.get("board_namespace") == namespace
                    for item in entry.get("provenance", [])), "queue_identity_unbound")
            attempt = entry.get("attempt_count")
            by_id = native.get("implementation_attempts", {}).get(task_id)
            by_cid = native.get("implementation_attempts_by_cid", {}).get(cid)
            _require(type(attempt) is int and 0 < attempt < maximum
                and type(by_id) is int and type(by_cid) is int and by_id == by_cid == attempt,
                "attempt_unbound_or_exhausted")
            failures = entry.get("consecutive_failures")
            _require(type(failures) is int and 0 < failures <= attempt
                and entry.get("consecutive_no_change") == 0
                and not entry.get("authority_renewal_key")
                and not entry.get("authority_renewal_quarantined"), "outcome_unavailable")
            terminal = next((event for event in reversed(events)
                if event.get("task_id") == task_id and event.get("type") in {
                    "implementation_started", "task_selected", "implementation_finished"}), None)
            _require(terminal and terminal.get("type") == "implementation_finished"
                and terminal.get("canonical_task_cid") == cid
                and terminal.get("canonical_task_key") == key
                and terminal.get("board_namespace") == namespace
                and type(terminal.get("attempt")) is int and terminal["attempt"] == attempt
                and terminal.get("attempt_consumed") is True
                and type(terminal.get("returncode")) is int and terminal["returncode"] != 0,
                "outcome_unbound")
            finished = runner._event_timestamp(terminal)
            deadline = entry.get("cooldown_until")
            duration = min(300 * 2 ** (failures - 1), 14400)
            _require(_number(finished) and _number(deadline)
                and record["started_at"] <= finished <= now < deadline
                and abs(deadline - finished - duration) <= 2, "deadline_unbound_or_expired")
            tasks.append({"task_id": task_id, "task_cid": cid, "attempt": attempt,
                "attempts_remaining": maximum - attempt, "retry_at": deadline})
        _require(_read(queue_path, 2_000_000) == queue_raw
            and runner.process_identity(daemon["pid"]) == daemon
            and runner.owns_process(record) and not children.read_text().strip(), "observation_changed")
        result.update(verified=True, reason="bounded_native_retry_cooldown",
            retry_at=min(task["retry_at"] for task in tasks), task_ids=sorted(selectable), tasks=tasks,
            queue_sha256=hashlib.sha256(queue_raw).hexdigest())
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        pass
    return summary(result)
