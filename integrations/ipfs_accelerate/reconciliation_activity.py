"""Bounded observations of Native's provider-free startup validator.

An accepted proposal and a live maintenance owner establish scope, never
progress by themselves. Only the existing canonical-executor activity record
can establish current validation activity; no attempt or task state is changed.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import time
from types import SimpleNamespace


PHASE = "validating_reconciled_candidate"


def _git(workspace, *args):
    result = subprocess.run(["git", "--no-replace-objects", *args], cwd=workspace,
                            capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise ValueError("reconciliation_activity_git_unavailable")
    return result.stdout.strip()


def catalog_path(runner, campaign):
    """Derive Native's campaign-confined address, without global configuration."""
    import hashlib
    state_path = campaign / f"{runner.STATE_PREFIX}_task_state.json"
    identity, board = campaign.resolve(), False
    for parent in (campaign, *campaign.parents):
        if (parent / ".git").exists():
            common = Path(_git(parent, "rev-parse", "--git-common-dir"))
            identity = (common if common.is_absolute() else parent / common).resolve()
            board = True
            break
    scope = hashlib.sha256(str(identity).encode()).hexdigest()[:20]
    base = campaign / "control-plane" / scope
    path = base / "board-control-plane/control.duckdb" if board else base / "lanes" / (state_path.stem + ".duckdb")
    return path, board


def snapshot(runner, campaign):
    """Read only the same confined catalog chosen by the campaign observer.

    The Native parent's ambient/registered target is not inherited by timer
    processes. Derive its explicit orchestration subtree without changing the
    environment, adopting a global database, or creating a missing catalog.
    """
    import json
    import stat
    from ipfs_accelerate_py.agent_supervisor.task_sources.duckdb_state import open_duckdb_connection
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    campaign = runner._validation_activity_directory(campaign, private=True)
    state_path = campaign / f"{runner.STATE_PREFIX}_task_state.json"
    path, board = catalog_path(runner, campaign)
    if not path.is_file() or path.resolve(strict=True) != path:
        return None
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or info.st_mode & 0o002):
        return None
    connection = open_duckdb_connection(str(path), prefer_quack=False, timeout_seconds=1.0)
    try:
        plane._validate_existing_relations(connection, board=board)
        if board:
            row = connection.execute("SELECT payload_json, updated_at_ms FROM artefact_generic "
                "WHERE board_namespace=? AND kind=? AND artefact_id=?",
                ["portal-task-state", "portal_task_state", state_path.stem]).fetchone()
        else:
            row = connection.execute("SELECT body_json, revision FROM portal_task_state WHERE lane_key=?",
                [state_path.stem]).fetchone()
    finally:
        connection.close()
    after = path.lstat()
    if (any(getattr(info,key) != getattr(after,key) for key in ("st_dev","st_ino","st_uid","st_mode","st_nlink"))
            or row is None or type(row[1]) is not int or len(str(row[0])) > 2_000_000):
        return None
    body = json.loads(row[0])
    return {"body": body, "revision": row[1], "authority_path": str(path)} if isinstance(body,dict) else None


def binding(runner, daemon, native, *, campaign, target, workspace, state, task, context, now_ts, owner_pid):
    """Bind the zero-paid-ordinal Native path without relaxing ordinary claims."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.current_incident_adjudication import _event_rows
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.supervisor_activity import SupervisorMaintenanceWindow
    from .improvement_recovery import _owned_bytes

    if (any(state.get(key) for key in ("manual_hold", "manual_cancellation", "capacity_quarantine", "protected_incident"))
            or state.get("active_phase") != PHASE or state.get("active_attempt") != 0
            or type(state.get("active_attempt")) is not int or state.get("implementation_in_progress") is not True
            or state.get("active_task_id") != task["id"] or context.get("task_id") != task["id"]
            or state.get("active_task_cid") != context["task_cid"]
            or state.get("active_task_key") != context["task_key"]
            or state.get("active_worktree_path") != str(workspace)):
        return None
    started = native.parse_timestamp(state.get("active_phase_started_at"))
    if (started is None or state.get("active_task_started_at") != state["active_phase_started_at"]
            or not 0 <= now_ts - started.timestamp() < runner.TIMEOUT_SECONDS):
        return None
    launcher = runner._read_validation_watchdog_authority(campaign / "launcher.json")
    heartbeat = runner._read_validation_watchdog_authority(campaign / f"{runner.STATE_PREFIX}_supervisor_status.json")
    receipt = runner._read_validation_watchdog_authority(campaign / f"{runner.STATE_PREFIX}_supervisor_maintenance_receipt.json")
    lease = runner._read_validation_watchdog_authority(campaign / "implementation.lock")
    claim_path = daemon.PortalImplementationDaemon._implementation_task_claim_path(
        SimpleNamespace(repo_root=target), task["id"], canonical_task_cid=context["task_cid"])
    claim = runner._read_validation_watchdog_authority(claim_path)
    if not all(isinstance(value, dict) for value in (launcher, heartbeat, receipt, lease, claim)):
        return None
    # A valid heartbeat/receipt may be newer than status's initial clock.
    # Their actual read time does not renew the fixed maintenance deadline.
    now_ts = max(now_ts, time.time())
    owner_pid = os.getpid() if owner_pid is None else owner_pid
    birth = native.read_process_birth(owner_pid) if type(owner_pid) is int and owner_pid > 1 else None
    launch_birth = launcher.get("identity", {})
    if (birth is None or birth.start_time_ticks <= 0 or not birth.boot_id or not runner.owns_process(launcher)
            or launch_birth.get("pid") != birth.pid or launch_birth.get("start_ticks") != birth.start_time_ticks
            or launch_birth.get("boot_id") != birth.boot_id
            or heartbeat.get("supervisor_pid") != birth.pid or heartbeat.get("daemon_pid") not in (None, 0)
            or heartbeat.get("status") != "agentic_maintenance_started"
            or heartbeat.get("last_agentic_maintenance_status") != "running"
            or heartbeat.get("last_agentic_maintenance_error")):
        return None
    spec_path = Path(str(launcher.get("spec_path") or ""))
    if not runner._campaign_tuple_matches(launcher, target, spec_path, campaign):
        return None
    window_data = heartbeat.get("supervisor_maintenance", {})
    if (window_data.get("schema") != "ipfs_accelerate_py/agent-supervisor/supervisor-maintenance@1"
            or window_data.get("phase") != "running" or window_data.get("finished_at") is not None):
        return None
    window = SupervisorMaintenanceWindow(window_data["started_at"], window_data["timeout_seconds"], window_data["deadline_at"])
    window_start = native.parse_timestamp(window.started_at)
    window_deadline = native.parse_timestamp(window.deadline_at)
    updated = native.parse_timestamp(heartbeat.get("updated_at"))
    receipt_updated = native.parse_timestamp(receipt.get("updated_at"))
    if (window.timeout_seconds > runner.TIMEOUT_SECONDS
            or heartbeat.get("active_agentic_maintenance_started_at") != window.started_at
            or heartbeat.get("active_agentic_maintenance_timeout_seconds") != window.timeout_seconds
            or updated is None or not 0 <= now_ts - updated.timestamp() <= 120
            or receipt_updated is None or not 0 <= now_ts - receipt_updated.timestamp() <= 120
            or not window_start.timestamp() <= started.timestamp() <= now_ts < window_deadline.timestamp()
            or receipt.get("schema") != native.SUPERVISOR_MAINTENANCE_RECEIPT_SCHEMA
            or receipt.get("status") != "running" or receipt.get("completed_at")
            or receipt.get("supervisor_pid") != birth.pid
            or native.ProcessBirthIdentity.from_dict(receipt.get("process_birth")) != birth
            or receipt.get("maintenance_started_at") != window.started_at
            or receipt.get("phase") != heartbeat.get("last_agentic_maintenance_phase")):
        return None
    state_path = campaign / f"{runner.STATE_PREFIX}_task_state.json"
    expected = {"task_id": task["id"], "canonical_task_cid": context["task_cid"],
                "canonical_task_key": context["task_key"], "attempt": 1}
    if (lease.get("kind") != "implementation" or lease.get("lease_role") != "supervisor_maintenance"
            or lease.get("pid") != birth.pid or not lease.get("lease_id")
            or claim.get("kind") != native.IMPLEMENTATION_TASK_CLAIM_LOCK_KIND
            or claim.get("lease_role") != native.IMPLEMENTATION_DISPATCH_INTENT_LEASE_ROLE
            or claim.get("pid") != birth.pid or not claim.get("lease_id")
            or type(claim.get("attempt")) is not int
            or native.ProcessBirthIdentity.from_dict(claim.get("owner_process_birth")) != birth
            or any(claim.get(key) != value for key, value in expected.items())
            or not native.checkout_lock_repository_matches(claim, target)
            or claim.get("dispatch_authority_cid") != daemon.PortalImplementationDaemon._implementation_dispatch_authority_cid(claim)
            or any(item.get("repo_root") != str(target) or item.get("state_dir") != str(campaign)
                   for item in (lease, launcher, receipt))
            or any(item.get("state_path") != str(state_path) for item in (lease, claim, receipt))):
        return None
    worktree_root, _ = runner.recorded_worktree_root(launcher, campaign)
    if workspace == worktree_root or not workspace.is_relative_to(worktree_root):
        return None
    rows = _event_rows(_owned_bytes(campaign / f"{runner.STATE_PREFIX}_events.jsonl",
                                  runner.MAX_EVENT_HISTORY_BYTES, legacy_group_write=True))
    starts = [(i, row) for i, row in enumerate(rows) if row.get("type") == "worktree_reconciliation_validation_started"]
    if not starts:
        return None
    index, start = starts[-1]
    event_time = runner._event_timestamp(start)
    candidate, baseline = start.get("implementation_commit"), start.get("baseline_ref")
    log_path = Path(str(state.get("active_log_path") or ""))
    if (type(start.get("attempt")) is not int
            or any(start.get(key) != value for key, value in expected.items() if key != "canonical_task_key")
            or start.get("canonical_task_key") != expected["canonical_task_key"]
            or start.get("worktree_path") != str(workspace) or start.get("branch") != state.get("active_branch")
            or start.get("log_path") != str(log_path) or start.get("attempt_consumed") is not False
            or start.get("provider_dispatched") is not False or event_time is None
            or event_time < started.timestamp() or event_time < float(launcher["started_at"])
            or re.fullmatch(r"[a-f0-9]{40}", str(candidate)) is None
            or re.fullmatch(r"[a-f0-9]{40}", str(baseline)) is None
            or log_path.parent != campaign / "implementation_logs"
            or re.fullmatch(re.escape(task["id"].lower()) + r"-reconciliation-validation-" + candidate[:12] + r"-[a-f0-9]{16}\.log", log_path.name) is None):
        return None
    admitted = None
    for row in rows[index + 1:]:
        if row.get("task_id") != task["id"]:
            continue
        if row.get("type") in {"implementation_finished", "worktree_reconciliation_validation_finished",
                              "worktree_reconciliation_candidate_queued", "implementation_proposal_rejected"}:
            return None
        if row.get("type") in {"implementation_proposal_validated", "implementation_proposal_receipt_reused"}:
            admitted = row
    if (admitted is None or admitted.get("accepted") is not True or admitted.get("attempted") is not True
            or admitted.get("canonical_task_cid") != context["task_cid"]
            or admitted.get("canonical_task_key") != context["task_key"]
            or admitted.get("repository_tree_id") != baseline or admitted.get("reason_codes")
            or any(re.fullmatch(r"[a-f0-9]{64}", str(admitted.get(key))) is None
                   for key in ("proposal_id", "receipt_id", "policy_id"))):
        return None
    if (_git(workspace, "rev-parse", "HEAD") != candidate
            or _git(workspace, "symbolic-ref", "--quiet", "--short", "HEAD") != start["branch"]
            or _git(workspace, "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=all")):
        return None
    log_identity = runner._validation_activity_log_identity(log_path)
    return {**expected, "attempt": 0, "validation_ordinal": 1, "execution_mode": PHASE,
            "workspace": str(workspace), "state_dir": str(campaign), "repo_root": str(target),
            "log_path": str(log_path), "log_identity": log_identity,
            "owner_record_id": start["event_id"], "owner_birth": birth.to_dict(),
            "lease_id": lease["lease_id"], "claim_lease_id": claim["lease_id"],
            "dispatch_authority_cid": claim["dispatch_authority_cid"],
            "phase_started_at": state["active_phase_started_at"],
            "phase_deadline": min(started.timestamp() + runner.TIMEOUT_SECONDS, window_deadline.timestamp()),
            "proposal_id": admitted["proposal_id"], "proposal_receipt_id": admitted["receipt_id"],
            "accepted_event_id": admitted["event_id"], "candidate_commit": candidate, "baseline_ref": baseline}


def evidence(runner, repo_root, state_dir, record, state, *, now_ts):
    """Accept only the live canonical executor's existing, short-lived pulse."""
    try:
        phase = state.get("active_phase")
        if (phase not in {PHASE, "validating"} or not runner.owns_process(record)
                or any(state.get(key) for key in ("manual_hold", "manual_cancellation", "capacity_quarantine", "protected_incident"))):
            return None
        owner_pid = record["identity"]["pid"]
        if phase == "validating":
            heartbeat = runner._read_validation_watchdog_authority(state_dir / f"{runner.STATE_PREFIX}_supervisor_status.json")
            if (heartbeat is None or heartbeat.get("status") != "running"
                    or heartbeat.get("supervisor_pid") != owner_pid):
                return None
            child = runner.process_identity(heartbeat.get("daemon_pid"))
            if not child or child.get("ppid") != owner_pid:
                return None
            owner_pid = child["pid"]
        context = {"campaign_state_dir": str(state_dir), "target_source_root": str(repo_root),
                   "task_id": state["active_task_id"], "task_cid": state["active_task_cid"],
                   "task_key": state["active_task_key"]}
        value = runner._validation_activity_binding(Path(state["active_worktree_path"]),
            {"id": state["active_task_id"]}, context, now_ts=now_ts, owner_pid=owner_pid)
        if value is None or (phase == PHASE and value.get("execution_mode") != PHASE):
            return None
        try:
            pulse = runner._read_validation_activity(runner._validation_activity_path(value))
        except (OSError, ValueError, TypeError):
            pulse = None
        # status() captures its clock before parsing provider logs and proving
        # this exact owner. A real executor can publish another pulse during
        # those reads. Validate against the clock after reading that pulse,
        # rather than misclassifying its new observation as a future timestamp.
        # An explicitly later caller clock remains authoritative for expiry;
        # neither this observation nor the pulse can extend a fixed deadline.
        observed_now = max(now_ts, time.time())
        finalizing = False
        if not runner._validation_activity_record_valid(pulse, value, now_ts=observed_now):
            from .validation_handoff import read
            pulse = read(runner, value, now_ts=observed_now)
            if pulse is None:
                return None
            finalizing = True
        kind = "canonical_reconciled_validation" if phase == PHASE else "canonical_native_validation"
        return {"type": kind + ("_finalizing" if finalizing else "_in_flight"),
                "source": "owned_canonical_executor_activity",
                "activity_id": pulse["activity_id"], "binding_sha256": pulse["binding_sha256"],
                "attempt": value["attempt"], **({"validation_ordinal": 1} if phase == PHASE else {}), "task_id": value["task_id"],
                "task_cid": value["canonical_task_cid"], "owner_birth": value["owner_birth"],
                "deadline_at": pulse["deadline_at"], "completion_authority": False}
    except Exception:
        return None
