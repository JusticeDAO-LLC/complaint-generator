"""Progress checks and verified recovery for one complaint supervisor campaign.

Native remains the authority for process fencing, task attempts, validation,
merge and completion. This adapter never edits those records or calls a model.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import time


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# These are the existing Native and watchdog ceilings. Qualification reads them;
# it does not raise, extend, or refund them.
_PRESERVED_BUDGETS = {
    "startup_seconds": 90,
    "stall_seconds": 180,
    "implementation_timeout_seconds": 900,
    "watchdog_action_deadline_ms": 1_200_000,
    "max_recoveries_per_incident": 2,
}


def preserved_native_watchdog_budgets(runner):
    """Return the finite Native/watchdog ceilings already used by this campaign.

    A test double may supply the same startup and stall values. Missing timeout
    evidence is read from the production runner module. Any other number is a
    contract change, not a new budget.
    """
    from .improvement_runner import STARTUP_SECONDS, STALL_SECONDS, TIMEOUT_SECONDS
    startup = getattr(runner, "STARTUP_SECONDS", STARTUP_SECONDS)
    stall = getattr(runner, "STALL_SECONDS", STALL_SECONDS)
    timeout = getattr(runner, "TIMEOUT_SECONDS", TIMEOUT_SECONDS)
    budgets = {
        "startup_seconds": startup,
        "stall_seconds": stall,
        "implementation_timeout_seconds": timeout,
        "watchdog_action_deadline_ms": 1_200_000,
        "max_recoveries_per_incident": 2,
    }
    if budgets != _PRESERVED_BUDGETS:
        raise ValueError("watchdog_budget_changed")
    if any(type(value) is not int or value <= 0 for value in budgets.values()):
        raise ValueError("watchdog_budget_unbounded")
    return dict(budgets)


def _finite_deadline(value):
    if isinstance(value, bool) or type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def _activity_deadline(evidence):
    if not isinstance(evidence, dict):
        return None
    return _finite_deadline(evidence.get("deadline_at"))


def _monitor_class(*, hold, state, recovery_permitted, source_stale, completed, idle_ready):
    if completed:
        return "complete"
    if state == "complete":
        return "completion_unverified"
    if source_stale:
        return "stale_source"
    if hold == "cancelled":
        return "cancelled_validation"
    if hold in {"awaiting_user", "manual_hold", "paused"}:
        return "intentional_user_wait"
    if hold:
        return "held"
    if idle_ready and recovery_permitted:
        return "idle_ready"
    if state in {"stalled", "no_progress", "daemon_failed"} and recovery_permitted:
        return "development_worker_stall"
    return "in_progress"


def _watchdog_executable_path(interpreter, environment=None):
    """Bind public executable locations without inheriting shell/cwd authority.

    A user service does not inherit the interactive shell's PATH. Keep the
    selected command's directory (including a Grok symlink's directory), not
    the resolved script's directory. This does not change validation's
    separately sealed executable search path or copy any credentials.
    """
    source = os.environ if environment is None else environment
    executable = Path(interpreter)
    if not executable.is_absolute():
        raise ValueError("watchdog_interpreter_not_absolute")
    provider = shutil.which(source.get("IPFS_ACCELERATE_AGENT_GROK_BIN") or "grok",
                          path=source.get("PATH", os.defpath))
    if not provider:
        raise ValueError("watchdog_grok_executable_unavailable")
    selected = [executable, Path(provider)]
    for command in ("node", "docker", "git"):
        found = shutil.which(command, path=source.get("PATH", os.defpath))
        if found:
            selected.append(Path(found))
    if any(not item.is_absolute() for item in selected):
        raise ValueError("watchdog_executable_path_invalid")
    directories = []
    for path in [*(item.absolute().parent for item in selected),
                 *(Path(part) for part in os.defpath.split(os.pathsep) if part)]:
        if not path.is_absolute() or any(c in str(path) for c in "\n\r\0"):
            raise ValueError("watchdog_executable_path_invalid")
        directory = str(path.resolve(strict=True))
        if not path.is_dir() or os.pathsep in directory:
            raise ValueError("watchdog_executable_path_invalid")
        if directory not in directories:
            directories.append(directory)
    return os.pathsep.join(directories)


def _preflight_summary(check):
    """Return closed diagnostic metadata; never serialize auth/config bodies."""
    if not isinstance(check, dict):
        check = {}
    def observed_boolean(value):
        return value if type(value) is bool else None
    def nested(key, member):
        value = check.get(key)
        return observed_boolean(value.get(member)) if isinstance(value, dict) else None
    flags = {
        "grok_binary_present": observed_boolean(check.get("grok_binary_present")),
        "auth_material_present": observed_boolean(check.get("auth_material_present")),
        "private_runtime_ready": nested("privacy", "ready"),
        "worktree_capacity_sufficient": nested("worktree_capacity", "sufficient"),
        "resource_capacity_ready": nested("resource_capacity", "ready"),
    }
    codes = {
        "grok_binary_present": "grok_executable_missing",
        "auth_material_present": "provider_auth_material_missing",
        "private_runtime_ready": "private_runtime_unavailable",
        "worktree_capacity_sufficient": "worktree_capacity_insufficient",
        "resource_capacity_ready": "resource_capacity_unavailable",
    }
    raw_status = check.get("status")
    status = raw_status if type(raw_status) is str and raw_status in {"ready", "not_ready"} else "unknown"
    reasons = [codes[key] for key, value in flags.items() if value is False]
    if status != "ready" and not reasons:
        reasons = ["preflight_not_ready" if status == "not_ready" else "preflight_status_unknown"]
    return {"status": status, "reasons": reasons, **flags}


class ComplaintCampaignWatchdog:
    def __init__(self, repo_root, spec_path, state_dir, *, expected_spec_sha256=None,
                 expected_plan_id=None, clock=None):
        from . import improvement_runner as runner
        self.runner = runner
        self.root, self.spec_path, self.state = (Path(p).resolve(strict=True)
            for p in (repo_root, spec_path, state_dir))
        self.spec, self.artifacts = runner._campaign_spec(self.root, self.spec_path)
        self.spec_sha = hashlib.sha256(self.spec_path.read_bytes()).hexdigest()
        runner._native_modules(self.root)
        from .improvement_plan import build_improvement_work_plan
        self.plan_id = build_improvement_work_plan(self.spec).plan_id
        if ((expected_spec_sha256 and expected_spec_sha256 != self.spec_sha)
                or (expected_plan_id and expected_plan_id != self.plan_id)):
            raise ValueError("watchdog_campaign_contract_changed")
        self.clock = clock or time.time
        from ipfs_accelerate_py.agent_supervisor.prompt.prompt_workflow import prompt_workflow_cid
        self.scope = {
            "repository_root_cid": prompt_workflow_cid({"repo_root": str(self.root)}),
            "policy_root": prompt_workflow_cid({"schema": "complaint-campaign-watchdog-policy@1",
                "plan_id": self.plan_id, "spec_sha256": self.spec_sha,
                "implementation_attempts_unchanged": True, "confirmations": 2,
                "max_recoveries_per_incident": 2}),
            "run_cid": prompt_workflow_cid({"state_dir": str(self.state), "plan_id": self.plan_id}),
        }
        self.directory = self.state / "watchdog"
        self.latest_status = {}
        self.latest_completion = {}
        self.latest_observation = {}
        self.last_action = {}
        self.latest_preflight = {}

    def _contract_current(self):
        if hashlib.sha256(self.spec_path.read_bytes()).hexdigest() != self.spec_sha:
            raise ValueError("watchdog_campaign_contract_changed")

    def _launch(self):
        from .improvement_shutdown import _context
        value = self.runner._read_json(self.state / "launcher.json")
        bound = bool(not value.get("read_error") and self.runner._full_launch_record(value)
            and self.runner._campaign_tuple_matches(value, self.root, self.spec_path, self.state)
            and _context(self.state, value) is not None)
        token = _digest({key: value.get(key) for key in
            ("identity", "started_at", "repo_root", "state_dir", "plan_id", "worktree_root_binding")})
        return value, bound, token

    def _automatic_stop_matches(self, launch, token):
        from .improvement_recovery import _owned_bytes
        try:
            value = json.loads(_owned_bytes(self.directory / "automatic-stop.json", 8192))
            shutdown = self.runner._read_json(self.state / "container_shutdown.json")
            return bool(value == {"schema": "complaint-watchdog-owned-stop@1", "scope": self.scope,
                    "owner_token": token, "launcher_sha256": _digest(launch)}
                and self.runner._shutdown_verified(launch, shutdown, self.root, self.state))
        except (OSError, ValueError, TypeError, KeyError):
            return False

    def _mark_automatic_stop(self, token):
        launch, bound, current = self._launch()
        shutdown = self.runner._read_json(self.state / "container_shutdown.json")
        if (not bound or current != token or launch.get("status") != "stopped"
                or not self.runner._shutdown_verified(launch, shutdown, self.root, self.state)):
            raise RuntimeError("watchdog_automatic_stop_unverified")
        self.runner._atomic_json(self.directory / "automatic-stop.json", {
            "schema": "complaint-watchdog-owned-stop@1", "scope": self.scope,
            "owner_token": token, "launcher_sha256": _digest(launch)})

    def observe(self):
        self._contract_current()
        self.latest_preflight = {}
        status = self.runner.status(self.root, self.spec_path, self.state)
        self.latest_status = status
        launch, bound, owner = self._launch()
        self.latest_launcher = launch
        native = status.get("native_state") or {}
        tasks = self.runner._native_modules(self.root)[1].parse_task_file(
            self.root / self.artifacts.board_relative, task_header_prefix=self.runner.TASK_PREFIX)
        pending = sorted(t.task_id for t in tasks if t.status != "completed")
        completed = False
        self.latest_completion = {}
        if not pending:
            from .campaign_completion import verify_campaign_completion
            self.latest_completion = verify_campaign_completion(self.root, self.spec_path, self.state)
            completed = self.latest_completion.get("verified") is True
        phase = str(native.get("active_phase") or "").lower()
        waiting = status.get("application_interview_state")
        automatic_stop = bool(launch.get("status") == "stopped"
            and self._automatic_stop_matches(launch, owner))
        hold = ""
        if os.path.lexists(self.directory / "HOLD") or os.path.lexists(self.directory / "OPERATOR_STOP"):
            hold = "manual_hold"
        elif native.get("manual_hold") or status.get("board", {}).get("manual_hold_task_ids"):
            hold = "manual_hold"
        elif native.get("manual_cancellation") or waiting == "cancelled":
            hold = "cancelled"
        elif waiting in {"awaiting_user", "waiting_for_user", "paused", "manual_hold"}:
            hold = "awaiting_user" if waiting in {"awaiting_user", "waiting_for_user"} else "manual_hold"
        elif native.get("capacity_quarantine") or phase == "capacity_quarantine":
            hold = "capacity_quarantine"
        elif native.get("protected_incident") or phase == "protected_incident":
            hold = "protected_incident"
        elif str(native.get("dependency_status") or "").lower() in {"unavailable", "temporary_unavailable", "degraded"}:
            hold = "dependency_unavailable"
        elif launch.get("status") == "stopped" and pending and not automatic_stop:
            # An operator's deliberate stop is not an unexpected owner death.
            hold = "manual_hold"
        elif automatic_stop and pending:
            check = self.runner.doctor(self.root, self.spec_path, self.state)
            self.latest_preflight = _preflight_summary(check)
            if check.get("status") != "ready":
                hold = "dependency_unavailable"
        active = str(native.get("active_task_id") or "")
        cid = str(native.get("active_task_cid") or "")
        if not active or not cid:
            active = cid = ""
        provider = status.get("provider_execution_evidence") or {}
        validation = status.get("validation_activity_evidence") or {}
        if not isinstance(validation, dict):
            validation = {}
        progress = _digest({"pending": pending, "task": active, "cid": cid,
            "attempt": native.get("active_attempt", 0), "phase": phase,
            "provider": {k: provider.get(k) for k in ("frame_counts", "log_bytes", "provider_terminal_observed")},
            "validation": {k: validation.get(k) for k in ("activity_id", "binding_sha256", "type")}})
        state = str(status.get("status") or "unknown")
        retry = status.get("retry_cooldown_evidence") or {}
        retry_cooldown = (bound and not hold and not self.runner._claim_proof_conflict(native)
            and not status.get("native_read_errors") and status.get("healthy") is True
            and state == "retry_cooldown" and status.get("retry_cooldown_verified") is True
            and retry.get("verified") is True and _finite_deadline(retry.get("retry_at")) is not None
            and self.clock() < retry["retry_at"] and not active
            and not native.get("implementation_in_progress"))
        if retry_cooldown:
            # Native's frozen observation schema has no scheduler-only status.
            # The Host reports it below without claiming semantic work progress.
            state = "running"
        if state not in {"waiting_for_user", "manual_hold", "paused", "cancelled", "capacity_quarantine",
                "protected_incident", "budget_exhausted", "blocked", "active", "post_provider", "running",
                "maintenance", "selected", "starting", "stalled", "no_progress", "daemon_failed", "stopped",
                "complete", "identity_mismatch", "state_error", "board_error", "stop_incomplete", "unknown"}:
            state = "unknown"
        # A detached owner can exit during startup before it publishes a new
        # shutdown proof. Public status correctly calls that stop_incomplete;
        # it still needs the ordinary verified stop, rather than being left
        # outside the watchdog's actionable failure set forever. Only a bound
        # launch that was expected to run and whose recorded owner is proved
        # dead qualifies. Operator stops and uncertain/reused/live PIDs retain
        # their existing refusal semantics. Public stop still proves closure.
        if (state == "stop_incomplete" and bound
                and launch.get("status") in {"starting", "running"}
                and status.get("owned_process_alive") is False
                and status.get("worker_liveness") in {"dead", "absent"}
                and self.runner._owner_liveness(launch.get("identity")) == "dead"):
            state = "daemon_failed"
        permitted = bool(bound and pending and not hold and not status.get("native_read_errors")
            and not self.runner._claim_proof_conflict(native)
            and status.get("worker_liveness") not in {"unknown", "pid_reuse"}
            and (state in {"stalled", "no_progress", "daemon_failed"}
                 or (state == "stopped" and automatic_stop)))
        selected_at = self.runner._event_timestamp({"timestamp": native.get("active_task_started_at")}) or 0
        grace_started = max(float(launch.get("started_at") or 0), selected_at)
        # A live heartbeat can coexist with an orphaned claim or an idle
        # selector. Logical ready work distinguishes that mechanical block
        # from a task genuinely waiting for dependencies or user input.
        idle_ready = False
        if (state in {"blocked", "running"} and not retry_cooldown and not hold and pending
                and status.get("board", {}).get("ready_task_ids")
                and not active and not native.get("implementation_in_progress")
                and not status.get("provider_progress_verified")
                and not status.get("validation_activity_verified")
                and self.clock() >= grace_started + self.runner.STALL_SECONDS):
            state = "no_progress"
            idle_ready = True
            permitted = bool(bound and not status.get("native_read_errors")
                and not self.runner._claim_proof_conflict(native)
                and status.get("worker_liveness") not in {"unknown", "pid_reuse"})
        source_stale = bool(self.runner._claim_proof_conflict(native))
        attempt = 0 if completed else int(native.get("active_attempt") or 0)
        task_id = "" if completed else active
        task_cid = "" if completed else cid
        budgets = preserved_native_watchdog_budgets(self.runner)
        result = {"schema": "campaign-progress-observation@1", "scope": dict(self.scope),
            "status": "complete" if completed else state, "healthy": completed or status.get("healthy") is True,
            "completion_verified": completed, "manual_hold": bool(hold), "hold_reason": hold,
            "progress_verified": False if completed else bool(status.get("provider_progress_verified")
                or status.get("validation_activity_verified")),
            "owner_binding_verified": bound, "recovery_permitted": permitted,
            "pending_task_ids": pending, "active_task_id": task_id,
            "active_task_cid": task_cid,
            "attempt": attempt,
            "progress_token": progress, "owner_token": owner,
            "grace_until_ms": int((grace_started + self.runner.STARTUP_SECONDS) * 1000)}
        # Frozen Native observes an exact schema. These closed diagnostics are
        # Host report metadata and confer no process, budget or task authority.
        # The current runner has no browser-deadline producer; do not invent one.
        self.latest_monitoring = {
            "schema": "complaint-gui-monitoring@1",
            "task_identity": {"task_id": task_id, "cid": task_cid, "attempt": attempt},
            "browser_deadline_at": None,
            "validator_deadline_at": (_activity_deadline(validation)
                if status.get("validation_activity_verified") is True else None),
            "monitor_class": _monitor_class(hold=hold, state=result["status"],
                recovery_permitted=permitted, source_stale=source_stale,
                completed=completed, idle_ready=idle_ready),
            "retry_cooldown": retry if retry_cooldown else None,
            "source_stale": source_stale, "idle_ready": idle_ready and not completed,
            "budgets": budgets, "paid_attempt_rearmed": False, "hold_bypassed": False,
            "completion_authority": False,
        }
        if retry_cooldown and not hold and not source_stale:
            self.latest_monitoring["monitor_class"] = "bounded_native_retry_cooldown"
        self.latest_observation = result
        return result

    def _accounting(self):
        value, _ = self.runner._read_native_state(self.root,
            self.state / f"{self.runner.STATE_PREFIX}_task_state.json")
        if value.get("read_error"):
            raise RuntimeError("watchdog_native_accounting_unavailable")
        keys = ("implementation_attempts", "implementation_attempts_by_cid", "protected_implementation_attempts",
            "retry_budget_repair_receipts", "retry_budget_repair_rearm_receipts",
            "stale_proposal_replay_rearm_receipts", "validation_obsolescence_rearm_receipts")
        return {k: value.get(k, {}) for k in keys}

    def recover(self, context):
        from ipfs_accelerate_py.agent_supervisor.rescue.supervisor_recovery import RecoveryActionObservation
        effects = []
        action = self.last_action = {"stage": "before_stop", "provider_dispatched_by_watchdog": False}
        expected = self.latest_observation
        current = self.observe()
        if current != expected or not current["recovery_permitted"]:
            return RecoveryActionObservation(False, reason="campaign_changed_before_stop")
        before = self._accounting()
        deadline = context.deadline_at_ms / 1000
        def remaining():
            if self.clock() >= deadline:
                raise TimeoutError("watchdog_action_deadline")
        remaining()
        if self.observe() != expected:
            return RecoveryActionObservation(False, reason="campaign_changed_during_accounting")
        stopped = self.runner.stop(self.state, expected_launcher_sha256=_digest(self.latest_launcher))
        action.update(stage="stopped", stop_status=stopped.get("status"))
        if stopped.get("status") != "stopped":
            return RecoveryActionObservation(False, reason="owned_stop_incomplete")
        effects.append("old_lane_fenced")
        self._mark_automatic_stop(expected["owner_token"])
        remaining()
        action["stage"] = "reconcile"
        recovered = self.runner.recover_stalled_worker(self.root, self.spec_path, self.state)
        action.update(recovery_status=recovered.get("recovery"), recovery_reason=recovered.get("reason"))
        if self._accounting() != before:
            raise RuntimeError("watchdog_native_accounting_changed_before_restart")
        remaining()
        after = self.observe()
        if after["completion_verified"]:
            action["stage"] = "completed_during_reconciliation"
            return RecoveryActionObservation(True, tuple(effects), {"healthy": True}, reason="verified_completion")
        if after["manual_hold"]:
            return RecoveryActionObservation(False, tuple(effects), reason="hold_introduced_during_recovery")
        # Only verified reconciliation or an ordinary closed empty execution
        # may resume. All refusal reasons retain their holds and evidence.
        if recovered.get("recovery") != "reconciled":
            return RecoveryActionObservation(False, tuple(effects), reason="native_reconciliation_refused")
        action["stage"] = "doctor"
        check = self.runner.doctor(self.root, self.spec_path, self.state)
        self.latest_preflight = _preflight_summary(check)
        action["preflight"] = self.latest_preflight
        if check.get("status") != "ready":
            return RecoveryActionObservation(False, tuple(effects), reason="native_preflight_not_ready")
        remaining()
        restart_view = self.observe()
        if restart_view["completion_verified"]:
            return RecoveryActionObservation(True, tuple(effects), {"healthy": True}, reason="verified_completion")
        if (restart_view["owner_token"] != expected["owner_token"] or restart_view["manual_hold"]
                or not restart_view["owner_binding_verified"] or not restart_view["recovery_permitted"]):
            return RecoveryActionObservation(False, tuple(effects), reason="campaign_changed_before_restart")
        if self._accounting() != before:
            raise RuntimeError("watchdog_native_accounting_changed_before_restart")
        remaining()
        action["stage"] = "start"
        started = self.runner.start(self.root, self.spec_path, self.state,
            expected_launcher_sha256=_digest(self.latest_launcher))
        action["start_status"] = started.get("status")
        if started.get("status") not in {"starting", "already_running"}:
            return RecoveryActionObservation(False, tuple(effects), reason="native_restart_refused")
        effects.append("lane_restarted")
        # A PID is not recovery. Observe genuine work, or a bounded start that
        # remains visible to subsequent timer checks without spending a retry.
        action["stage"] = "observe_restart"
        until = min(deadline, self.clock() + self.runner.STARTUP_SECONDS)
        while self.clock() < until:
            view = self.observe()
            if view["completion_verified"] or (view["healthy"] and view["progress_verified"]):
                action["stage"] = "verified_progress"
                return RecoveryActionObservation(True, tuple(effects), {"healthy": True})
            if view["manual_hold"] or view["status"] in {"daemon_failed", "state_error", "identity_mismatch", "stop_incomplete"}:
                break
            time.sleep(min(2, max(0, until - self.clock())))
        # Stop/reconciliation/start have already proved both local effects.
        # A slow semantic-health observation is not an uncertain side effect;
        # Native still records the failed health check and spends this ordinal.
        # Marking it partial would permanently quarantine this incident even
        # when the same restarted lane later produces verified work.
        return RecoveryActionObservation(False, tuple(effects), reason="restart_waiting_for_verified_progress")

    def run_once(self, *, stop_completed=False):
        from ipfs_accelerate_py.agent_supervisor.rescue.campaign_watchdog import (
            CampaignProgressWatchdog, CampaignProgressWatchdogPolicy)
        budgets = preserved_native_watchdog_budgets(self.runner)
        policy = CampaignProgressWatchdogPolicy(deadline_ms=budgets["watchdog_action_deadline_ms"])
        # Frozen SDK profiles have no activity-only observation field. Keep a
        # strictly owned, deadline-bound repair passive without calling its
        # recovery policy or changing its durable incident/work-progress state.
        initial_error = None
        try:
            first = self.observe()
        except Exception as exc:
            # Let the unchanged SDK map observation failures to its existing
            # typed error result, without retrying or authorizing an effect.
            first, initial_error = {}, exc
        from .watchdog_failure_evidence import capture as capture_first_failure
        failure_capture = capture_first_failure(self.directory, scope=self.scope, observation=first,
            status=self.latest_status, preflight=getattr(self,"latest_preflight",{}), observed_at=self.clock())
        rescue = self.latest_status.get("auto_rescue_activity_evidence")
        rescue = rescue if type(rescue) is dict else {}
        retry = self.latest_status.get("retry_cooldown_evidence")
        retry = retry if type(retry) is dict else {}
        passive_retry = (first.get("owner_binding_verified") is True
            and first.get("healthy") is True and first.get("status") == "running"
            and first.get("manual_hold") is False and not first.get("hold_reason")
            and first.get("completion_verified") is False and first.get("pending_task_ids")
            and not first.get("active_task_id") and not first.get("active_task_cid")
            and not first.get("attempt") and first.get("recovery_permitted") is False
            and self.latest_status.get("status") == "retry_cooldown"
            and self.latest_status.get("retry_cooldown_verified") is True
            and self.latest_status.get("owned_process_alive") is True
            and self.latest_status.get("worker_liveness") == "alive"
            and not self.latest_status.get("native_read_errors")
            and self.latest_monitoring.get("source_stale") is False
            and first.get("progress_verified") is False
            and retry.get("verified") is True and retry.get("progress_verified") is False
            and type(retry.get("task_ids")) is list and retry["task_ids"]
            and set(retry["task_ids"]) <= set(first["pending_task_ids"])
            and _finite_deadline(retry.get("retry_at")) is not None
            and self.clock() < retry["retry_at"])
        passive_rescue = (first.get("owner_binding_verified") is True
            and first.get("healthy") is True and first.get("status") == "active"
            and first.get("manual_hold") is False and not first.get("hold_reason")
            and first.get("completion_verified") is False and first.get("pending_task_ids")
            and first.get("active_task_id") in first["pending_task_ids"]
            and first.get("active_task_id") == rescue.get("task_id")
            and first.get("active_task_cid") == rescue.get("task_cid")
            and self.latest_status.get("owned_process_alive") is True
            and self.latest_status.get("worker_liveness") == "alive"
            and first.get("progress_verified") is False
            and self.latest_status.get("auto_rescue_activity_verified") is True
            and rescue.get("activity_verified") is True and rescue.get("work_progress_verified") is False
            and rescue.get("reason") == "bounded_native_rescue_activity"
            and type(rescue.get("deadline_at")) in (int,float) and math.isfinite(rescue["deadline_at"])
            and self.clock() < rescue["deadline_at"])
        if passive_retry:
            # A fixed Native selection deadline is not a new grace lease. Do
            # not enter recovery policy or rewrite its incident ledger here.
            result = {"schema":"campaign-progress-watchdog-result@1", "scope":dict(self.scope),
                "status":"cooldown", "reason":"bounded_native_retry_cooldown", "retry_at":retry["retry_at"],
                "progress_verified":False, "completion_authority":False,
                "provider_calls_by_watchdog":0, "attempt_refunded":False}
        elif passive_rescue:
            result = {"schema":"campaign-progress-watchdog-result@1", "scope":dict(self.scope),
                "status":"healthy", "reason":"bounded_native_rescue_activity", "progress_verified":False,
                "completion_authority":False,"provider_calls_by_watchdog":0,"attempt_refunded":False}
        else:
            # Preserve the SDK's original observation count/order and every
            # pre-effect re-observation, rather than observing twice initially.
            pending = [first]
            def observe():
                if pending:
                    value = pending.pop()
                    if initial_error is not None:
                        raise initial_error
                    return value
                return self.observe()
            result = CampaignProgressWatchdog(self.directory, repository_root=self.root, scope=self.scope, observe=observe,
                recover=self.recover, policy=policy).run_once()
        if result.get("status") == "complete" and stop_completed and not self.latest_observation.get("manual_hold"):
            expected = self.latest_observation
            if self.observe() != expected or not self.latest_observation["completion_verified"]:
                result = {**result, "status": "refused", "reason": "completion_changed_before_cleanup"}
            else:
                launch = self.latest_launcher
                bound = self.latest_observation["owner_binding_verified"]
                if bound and self.runner.owns_process(launch):
                    stopped = self.runner.stop(self.state, expected_launcher_sha256=_digest(launch))
                    result = {**result, "completion_cleanup": {"status": stopped.get("status"),
                        "quiesced": (stopped.get("container_shutdown") or {}).get("quiesced")}}
                    if stopped.get("status") != "stopped":
                        result.update(status="refused", reason="completed_supervisor_cleanup_incomplete")
        from .auto_rescue_activity import summary as rescue_summary
        provider = self.latest_status.get("provider_execution_evidence")
        provider = provider if type(provider) is dict else {}
        provider_counts = provider.get("frame_counts")
        provider_counts = provider_counts if type(provider_counts) is dict else {}
        failure_evidence = {"auto_rescue":rescue_summary(self.latest_status.get("auto_rescue_activity_evidence")),
            "provider_progress_verified":self.latest_status.get("provider_progress_verified") is True,
            "validation_activity_verified":self.latest_status.get("validation_activity_verified") is True,
            "claim_progress_verified":self.latest_status.get("claim_progress_verified") is True,
            "provider_terminal_observed":provider.get("provider_terminal_observed") is True,
            "provider_frame_counts":{key:provider_counts[key] for key in ("usage","tool_call","tool_call_update")
                if type(provider_counts.get(key)) is int and 0 <= provider_counts[key] < 1_000_000_000}}
        report = {**result, "checked_at": self.clock(), "plan_id": self.plan_id,
            "repo_root": str(self.root), "state_dir": str(self.state),
            "completed": (self.latest_status.get("board") or {}).get("completed"),
            "task_count": (self.latest_status.get("board") or {}).get("count"),
            "active_task_id": self.latest_observation.get("active_task_id"),
            "last_action": self.last_action, "completion": self.latest_completion,
            "preflight": getattr(self, "latest_preflight", {}),
            "native_status": self.latest_status.get("status"), "activity_evidence":failure_evidence,
            "initial_failure_capture":failure_capture,
            "monitoring": getattr(self, "latest_monitoring", {})}
        import stat
        self.directory.mkdir(mode=0o700, exist_ok=True)
        info = self.directory.lstat()
        if (self.directory.resolve(strict=True) != self.directory or info.st_uid != os.getuid()
                or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError("watchdog_directory_custody_invalid")
        self.runner._atomic_json(self.directory / "latest.json", report)
        return report


_RECOVERY_KINDS = frozenset({
    "idle_ready", "development_worker_stall", "validation_activity", "owner_death",
})
_ATTEMPT_CAP = 3
_TURN_CAP = 64
_PRESERVED_HOLDS = frozenset({
    "awaiting_user", "manual_hold", "paused", "cancelled", "capacity_quarantine",
    "protected_incident", "dependency_unavailable",
})


def _argv_foreign(identity, scope_token):
    argv = identity.get("argv") or []
    if "foreign-validator" in argv:
        return True
    if "--watchdog-scope" not in argv:
        return False
    index = argv.index("--watchdog-scope")
    token = argv[index + 1] if index + 1 < len(argv) else ""
    return token != scope_token


def _matching_birth(identity):
    from .improvement_runner import process_identity
    if not isinstance(identity, dict):
        return None
    current = process_identity(identity.get("pid"))
    if not current:
        return None
    if any(current.get(key) != identity.get(key) for key in ("pid", "start_ticks", "boot_id")):
        return None
    return current


def _foreign_closure(nodes, scope_token):
    by_pid = {node["pid"]: node for node in nodes}
    memo = {}

    def foreign(pid):
        if pid in memo:
            return memo[pid]
        node = by_pid.get(pid)
        if node is None:
            memo[pid] = False
            return False
        parent = node.get("ppid")
        memo[pid] = _argv_foreign(node, scope_token) or (parent in by_pid and foreign(parent))
        return memo[pid]

    return {pid for pid in by_pid if foreign(pid)}


def _signal_matching_birth(identity, signum):
    import signal
    current = _matching_birth(identity)
    if current is None or current["pid"] <= 1:
        return False
    try:
        if hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"):
            descriptor = os.pidfd_open(current["pid"])
            try:
                again = _matching_birth(identity)
                if again is None:
                    return False
                signal.pidfd_send_signal(descriptor, signum)
            finally:
                os.close(descriptor)
        else:
            os.kill(current["pid"], signum)
    except ProcessLookupError:
        return False
    except OSError:
        return False
    return True


def _reap_owned_births(owned):
    """Signal only captured births. A foreign validator is never in this set."""
    import signal
    for signum in (signal.SIGTERM, signal.SIGKILL):
        for identity in owned:
            _signal_matching_birth(identity, signum)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if all(_matching_birth(identity) is None for identity in owned):
                return True
            time.sleep(0.05)
    return all(_matching_birth(identity) is None for identity in owned)


def qualify_scoped_owned_recovery(*, kind, owner_identity, scope_token, phase_started_at, now,
                                  descendant_identities=(), hold="", ledger_uncertain=False,
                                  awaiting_user=False, attempt=0, turns=0, recovery_actions=0,
                                  validation_scope=None, active_scope=None, claimed_deadline=None,
                                  ledger=None):
    """Recover one scoped incident without extending Native budgets or ledgers.

    Idle, stall, and validation recovery wait out the existing grace and stall
    windows and stop at the current phase deadline. Owner death may recover
    earlier, still inside that same deadline. Holds, uncertain ledgers, and a
    product awaiting a user are left untouched. Nested owned children are
    reaped by birth. A foreign validator, including one nested under the owner,
    is not signalled and cannot supply the deadline.
    """
    from . import improvement_runner as runner
    budgets = preserved_native_watchdog_budgets(runner)
    if not isinstance(scope_token, str) or not scope_token or any(c in scope_token for c in "\n\r\0"):
        raise ValueError("watchdog_scope_invalid")
    if isinstance(phase_started_at, bool) or type(phase_started_at) not in (int, float) or not math.isfinite(phase_started_at):
        raise ValueError("watchdog_phase_start_invalid")
    if isinstance(now, bool) or type(now) not in (int, float) or not math.isfinite(now) or now < phase_started_at:
        raise ValueError("watchdog_observation_clock_invalid")
    if type(attempt) is not int or type(turns) is not int or type(recovery_actions) is not int:
        raise ValueError("watchdog_recovery_counters_invalid")
    if attempt < 0 or turns < 0 or recovery_actions < 0:
        raise ValueError("watchdog_recovery_counters_invalid")
    deadline = float(phase_started_at) + budgets["implementation_timeout_seconds"]
    grace_until = float(phase_started_at) + budgets["startup_seconds"]
    stall_until = float(phase_started_at) + budgets["stall_seconds"]
    report = {
        "schema": "complaint-scoped-owned-recovery@1",
        "kind": kind,
        "status": "refused",
        "reason": "recovery_not_permitted",
        "reaped_pids": [],
        "spared_pids": [],
        "phase_deadline": deadline,
        "grace_until": grace_until,
        "stall_until": stall_until,
        "budgets": budgets,
        "attempt": attempt,
        "turns": turns,
        "attempt_cap": _ATTEMPT_CAP,
        "turn_cap": _TURN_CAP,
        "recovery_actions": recovery_actions,
        "max_recoveries_per_incident": budgets["max_recoveries_per_incident"],
        "attempt_refunded": False,
        "ledger_mutated": False,
        "completion_authority": False,
        "foreign_validator_adopted": False,
    }
    if ledger is not None and not isinstance(ledger, dict):
        raise ValueError("watchdog_ledger_invalid")
    preserved = None if ledger is None else dict(ledger)
    nodes = []
    for identity in descendant_identities:
        current = _matching_birth(identity)
        if current is not None:
            nodes.append(current)
    owner_live = _matching_birth(owner_identity)
    if owner_live is not None:
        nodes.extend(runner._descendants(owner_live))
        nodes.append(owner_live)
    unique = {}
    for node in nodes:
        unique.setdefault(node["pid"], node)
    nodes = list(unique.values())
    owner_pid = owner_identity.get("pid") if isinstance(owner_identity, dict) else None
    session_nodes = [node for node in nodes if node.get("session") == owner_pid or node.get("pid") == owner_pid]
    foreign = _foreign_closure(session_nodes, scope_token)
    owned = [node for node in session_nodes if node["pid"] not in foreign and not _argv_foreign(node, scope_token)]
    report["spared_pids"] = sorted(foreign)

    def finish(status, reason, *, reaped=()):
        report["status"] = status
        report["reason"] = reason
        report["reaped_pids"] = sorted(reaped)
        if ledger is not None and ledger != preserved:
            raise RuntimeError("watchdog_ledger_mutated")
        return report

    if awaiting_user or hold in _PRESERVED_HOLDS or hold == "awaiting_user":
        return finish("preserved", "awaiting_user" if awaiting_user or hold == "awaiting_user" else "hold_preserved")
    if ledger_uncertain:
        return finish("preserved", "uncertain_ledger")
    if kind not in _RECOVERY_KINDS:
        return finish("refused", "recovery_kind_unknown")
    if recovery_actions >= budgets["max_recoveries_per_incident"]:
        return finish("refused", "recovery_actions_exhausted")
    if turns > _TURN_CAP or (kind != "idle_ready" and not 1 <= attempt <= _ATTEMPT_CAP):
        return finish("refused", "attempt_or_turn_cap")
    if kind == "idle_ready" and attempt > _ATTEMPT_CAP:
        return finish("refused", "attempt_or_turn_cap")
    if now >= deadline:
        return finish("refused", "phase_deadline_expired")
    if kind == "validation_activity":
        if validation_scope != active_scope or not active_scope:
            return finish("refused", "foreign_validator_contamination")
        if claimed_deadline != deadline:
            return finish("refused", "stale_phase_deadline")
    elif kind in {"idle_ready", "development_worker_stall"} and now < stall_until:
        return finish("refused", "within_grace_or_stall")
    if kind == "owner_death":
        if owner_live is not None:
            return finish("refused", "owner_still_alive")
    elif owner_live is None:
        return finish("refused", "owner_birth_uncertain")
    if not owned:
        return finish("refused", "owned_tree_absent")
    # Deepest owned births first. Foreign births stay in the spared set.
    owned.sort(key=lambda node: node.get("ppid") == owner_pid)
    if not _reap_owned_births(owned):
        return finish("refused", "owned_reap_incomplete", reaped=[
            node["pid"] for node in owned if _matching_birth(node) is None])
    report["recovery_actions"] = recovery_actions + 1
    return finish("recovered", kind, reaped=[node["pid"] for node in owned])


def watch_campaign(repo_root, spec_path, state_dir, *, once=False, interval_seconds=60,
                   stop_completed=False, expected_spec_sha256=None, expected_plan_id=None):
    if type(interval_seconds) not in (int, float) or not 5 <= interval_seconds <= 3600:
        raise ValueError("watchdog_interval_invalid")
    watcher = ComplaintCampaignWatchdog(repo_root, spec_path, state_dir,
        expected_spec_sha256=expected_spec_sha256, expected_plan_id=expected_plan_id)
    while True:
        result = watcher.run_once(stop_completed=stop_completed)
        if once or result.get("status") == "complete":
            return result
        time.sleep(interval_seconds)


def systemd_units(repo_root, spec_path, state_dir, *, interpreter, plan_id, spec_sha256,
                  executable_path=None):
    """Render dedicated user units; installation and enabling are explicit."""
    root, spec, state = (Path(p).resolve(strict=True) for p in (repo_root, spec_path, state_dir))
    name = "complaint-agent-watchdog-" + _digest(str(state))[:12]
    def quoted(value):
        value = str(value)
        if any(c in value for c in "\n\r\0"):
            raise ValueError("watchdog_unit_argument_invalid")
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'
    command = [interpreter, "-I", "-B", root / "scripts/run_complaint_improvement_supervisor.py",
        "watchdog", "--once", "--stop-completed", "--repo-root", root, "--spec", spec,
        "--state-dir", state, "--expected-plan-id", plan_id, "--expected-spec-sha256", spec_sha256]
    working_directory = str(root).replace("%", "%%")
    if any(c in working_directory for c in "\n\r\0"):
        raise ValueError("watchdog_unit_argument_invalid")
    runtime_path = executable_path if executable_path is not None else os.defpath
    if (not isinstance(runtime_path, str) or not runtime_path
            or any(c in runtime_path for c in "\n\r\0")
            or any(not Path(part).is_absolute() for part in runtime_path.split(os.pathsep))):
        raise ValueError("watchdog_executable_path_invalid")
    # Environment= expands unit specifiers but does not expand '$'. ExecStart
    # has a different expansion contract, so do not reuse its dollar escaping.
    path_assignment = '"PATH=' + runtime_path.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'
    service = "\n".join(["[Unit]", "Description=Verify and recover the complaint agent campaign", "",
        "[Service]", "Type=oneshot", "WorkingDirectory=" + working_directory,
        "ExecStart=" + " ".join(quoted(v) for v in command), "TimeoutStartSec=1800",
        # Public start detaches a Native owner. Session detachment does not
        # escape this cgroup; only Native's public stop may reap its children.
        "KillMode=process", "UMask=0077", "Environment=HF_HUB_OFFLINE=1",
        "Environment=HF_DATASETS_OFFLINE=1", "Environment=TRANSFORMERS_OFFLINE=1",
        "Environment=IPFS_DATASETS_PY_MINIMAL_IMPORTS=1", "Environment=IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD=0",
        "Environment=" + path_assignment,
        "SyslogIdentifier=" + name, ""])
    timer = "\n".join(["[Unit]", "Description=Check complaint agent campaign progress every minute", "",
        "[Timer]", "OnCalendar=*-*-* *:*:00", "OnUnitInactiveSec=60s", "Persistent=true", "AccuracySec=1s",
        "Unit=" + name + ".service", "", "[Install]", "WantedBy=timers.target", ""])
    return {"name": name, "service": service, "timer": timer}


def install_user_timer(repo_root, spec_path, state_dir, *, interpreter=None, unit_directory=None, command_runner=None):
    """Install this campaign's dedicated user timer without replacing other units."""
    import stat
    import subprocess
    import sys
    import tempfile
    watcher = ComplaintCampaignWatchdog(repo_root, spec_path, state_dir)
    units = systemd_units(watcher.root, watcher.spec_path, watcher.state,
        interpreter=interpreter or sys.executable, plan_id=watcher.plan_id, spec_sha256=watcher.spec_sha,
        executable_path=_watchdog_executable_path(interpreter or sys.executable))
    folder = (Path(unit_directory) if unit_directory else
        Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "systemd/user")
    folder.mkdir(parents=True, exist_ok=True)
    if folder.resolve(strict=True) != folder.absolute() or folder.stat().st_uid != os.getuid():
        raise ValueError("watchdog_unit_directory_unowned")
    files = {folder / (units["name"] + "." + kind): units[kind] for kind in ("service", "timer")}
    # The previous renderer omitted PATH. Upgrade only its exact, same-campaign
    # managed bytes; any operator customization or foreign binding still fails.
    legacy_service = "\n".join(line for line in units["service"].splitlines()
                               if not line.startswith('Environment="PATH=')) + "\n"
    legacy_timer = "\n".join(line for line in units["timer"].splitlines()
                             if line != "OnUnitInactiveSec=60s") + "\n"
    legacy_units = {folder / (units["name"] + ".service"): legacy_service,
                    folder / (units["name"] + ".timer"): legacy_timer}
    upgrades = {}
    for path, content in files.items():
        if os.path.lexists(path):
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise ValueError("watchdog_existing_unit_conflict")
            existing = path.read_text()
            if existing == content:
                continue
            if existing != legacy_units.get(path):
                raise ValueError("watchdog_existing_unit_conflict")
            upgrades[path] = (existing, info)
    for path, content in files.items():
        if not path.exists() or path in upgrades:
            descriptor, temporary = tempfile.mkstemp(prefix=".watchdog-unit-", dir=folder)
            try:
                with os.fdopen(descriptor, "w") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                if path in upgrades:
                    expected, previous = upgrades[path]
                    current = path.lstat()
                    if (any(getattr(current, key) != getattr(previous, key) for key in
                            ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"))
                            or path.read_text() != expected):
                        raise ValueError("watchdog_existing_unit_conflict")
                    os.replace(temporary, path)
                else:
                    # Do not replace a different unit created after preflight.
                    os.link(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    run = command_runner or subprocess.run
    commands = [["systemd-analyze", "--user", "verify", *(str(p) for p in files)],
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", units["name"] + ".timer"],
        ["systemctl", "--user", "start", units["name"] + ".service"]]
    for command in commands:
        run(command, check=True, capture_output=True, text=True, timeout=1800)
    return {"status": "installed", "unit": units["name"], "timer_enabled": True,
        "state_dir": str(watcher.state), "report_path": str(watcher.directory / "latest.json"),
        "updated_units": [path.name for path in upgrades]}
