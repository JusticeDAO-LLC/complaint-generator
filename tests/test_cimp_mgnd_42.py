"""Campaign health scopes stay distinct from legitimate interview waits.

Synthetic private fixtures only. Recovery observation must not edit a claim,
refund an attempt, complete a task, dispatch a provider, or leave a child.
"""

from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time

import pytest

import integrations.ipfs_accelerate.improvement_runner as runner


ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
_SCOPES = ("claim", "worker", "provider", "validation", "merge")


@pytest.fixture(autouse=True)
def restore_cwd(monkeypatch):
    monkeypatch.chdir(ROOT)


def _stamp(seconds_ago=0):
    return datetime.fromtimestamp(runner.time.time() - seconds_ago, timezone.utc).isoformat()


def _identity(pid=991119):
    return {"pid": pid, "start_ticks": 123456, "boot_id": "synthetic-boot", "ppid": 1,
            "session": pid, "process_group": pid, "argv": [sys.executable, "_run"]}


def _forbid_dispatch(monkeypatch):
    original = runner.subprocess.Popen

    def guarded(*args, **kwargs):
        command = args[0] if args else kwargs.get("args")
        rendered = " ".join(map(str, command)) if isinstance(command, (list, tuple)) else str(command)
        name = Path(str(command[0] if isinstance(command, (list, tuple)) and command else rendered)).name
        if name in {"grok", "grok-cli"} or "provider" in name or "--owner-token" in rendered:
            pytest.fail(f"duplicate dispatch: {rendered}")
        if kwargs.get("stdin") not in (None, runner.subprocess.DEVNULL):
            pytest.fail("worker stdin is readable")
        return original(*args, **kwargs)

    monkeypatch.setattr(runner.subprocess, "Popen", guarded)
    monkeypatch.setattr(runner, "start", lambda *a, **k: pytest.fail("task selection"))


def _campaign(tmp_path, monkeypatch, native_state, *, started_ago=30):
    state = tmp_path / "state"
    state.mkdir(parents=True)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "schema_version": "complaint-intake-improvement@1", "title": "Synthetic health campaign",
        "provider": {"router": "ipfs_accelerate_py.llm_router", "provider": "grok_cli",
                     "model": "grok-4.7", "allow_fallback": False},
        "execution_policy": {"one_lane": True},
        "goals": [{"id": "goal.ops", "title": "Ops", "subgoals": [{"id": "sub.ops", "title": "Health"}]}],
        "tasks": [{"id": "CIMP-MGND-42", "title": "Health", "goal_id": "goal.ops", "subgoal_id": "sub.ops",
                   "priority": "P0", "targets": ["integrations/ipfs_accelerate/improvement_runner.py"],
                   "depends_on": [], "acceptance": ["Separate liveness from interview waits."],
                   "validation_commands": ["python -m pytest -q tests/test_cimp_mgnd_42.py"],
                   "implementation_prompt": "Project health without refunding an attempt."}],
    }))
    (tmp_path / "board.md").write_text("# Tasks\n\n## CIMP-MGND-42 Health\n\n- Status: ready\n")
    argv = [sys.executable, "_run", "--state-dir", str(state), "--owner-token", "synthetic-owner"]
    launcher = _identity()
    daemon = {**_identity(991120), "ppid": launcher["pid"]}
    record = {"identity": {**launcher, "argv": argv}, "argv": argv, "owner_token": "synthetic-owner",
              "started_at": runner.time.time() - started_ago, "status": "starting",
              "repo_root": str(tmp_path), "spec_path": str(spec), "state_dir": str(state),
              "board_path": str(tmp_path / "board.md"), "merge_target": "campaign-test"}
    runner._atomic_json(state / "launcher.json", record)
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_task_state.json", native_state)
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_supervisor_status.json", {
        "status": "running", "supervisor_pid": launcher["pid"], "daemon_pid": daemon["pid"],
        "daemon_pid_alive": True, "updated_at": _stamp(1),
    })
    identities = {launcher["pid"]: record["identity"], daemon["pid"]: daemon}

    def identify(pid):
        return identities.get(int(pid))

    monkeypatch.setattr(runner, "process_identity", identify)
    monkeypatch.setattr(runner, "_validate_board", lambda *a: {
        "count": 1, "completed": 0, "ready_task_ids": ["CIMP-MGND-42"], "manual_hold_task_ids": [],
    })
    return tmp_path, spec, state, record, daemon


def _attempt(state, daemon, *, phase, started_ago, log_ago=None, **extra):
    log = state / "attempt.log"
    log.write_text("synthetic-provider-log\n", encoding="utf-8")
    if log_ago is not None:
        moment = time.time() - log_ago
        os.utime(log, (moment, moment))
    payload = {"active_task_id": "CIMP-MGND-42", "active_task_cid": "bafyhealthcid", "active_attempt": 2,
               "implementation_in_progress": True, "active_phase": phase,
               "active_task_started_at": _stamp(started_ago), "active_phase_started_at": _stamp(started_ago),
               "owner_process_birth": {key: daemon[key] for key in ("pid", "start_ticks", "boot_id")},
               "implementation_attempts": {"CIMP-MGND-42": 2},
               "implementation_attempts_by_cid": {"bafyhealthcid": 2},
               "active_worktree_path": str(state / "work"), "active_log_path": str(log)}
    payload.update(extra)
    return payload


def _children():
    return [child.pid for child in multiprocessing.active_children() if child.is_alive()]


def _assert_scopes(result):
    scopes = result["scope_liveness"]
    assert list(scopes) == list(_SCOPES)
    assert result["application_interview_state"] not in scopes.values()
    assert result["scope_monitors"]["completion_authority"] is False
    for report in result["scope_monitors"]["progress"].values():
        assert report["completion_authority"] is False and report["work_complete"] is False
    assert set(result["scope_monitors"]["progress"]) == {"provider", "validation", "merge"}


def test_worker_stdin_cannot_carry_the_complaint():
    source = inspect.getsource(runner.start)
    assert "stdin=campaign_worker_stdin()" in source
    assert runner.campaign_worker_stdin() is runner.subprocess.DEVNULL
    assert runner.STALL_SECONDS < runner.TIMEOUT_SECONDS < 3600


def test_provider_validation_and_merge_liveness_are_separate(tmp_path, monkeypatch):
    _forbid_dispatch(monkeypatch)
    root, spec, state, _, daemon = _campaign(tmp_path, monkeypatch, {})
    work = str(state / "work")
    log = str(state / "attempt.log")
    cases = []

    def observe(phase, started_ago, event=None, log_ago=1):
        payload = _attempt(state, daemon, phase=phase, started_ago=started_ago, log_ago=log_ago)
        runner._atomic_json(state / f"{runner.STATE_PREFIX}_task_state.json", payload)
        events = state / f"{runner.STATE_PREFIX}_events.jsonl"
        events.write_text("" if event is None else json.dumps(event) + "\n", encoding="utf-8")
        before = (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes()
        started = time.monotonic()
        live = _children()
        result = runner.status(root, spec, state)
        assert time.monotonic() - started < 8
        assert _children() == live
        assert (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes() == before
        _assert_scopes(result)
        cases.append(result["scope_liveness"])
        return result

    fresh = {"type": "grok_usage", "provider": "grok_cli", "model": "grok-4.7", "usage": {"input_tokens": 3},
             "task_id": "CIMP-MGND-42", "task_cid": "bafyhealthcid", "attempt": 2,
             "timestamp": _stamp(1), "worktree_path": work, "log_path": log}
    provider = observe("implementing", 5, fresh)
    assert provider["scope_liveness"] == {"claim": "held", "worker": "alive", "provider": "fresh",
                                          "validation": "idle", "merge": "idle"}
    assert provider["application_interview_state"] is None
    assert provider["status"] == "active"

    validation = {"type": "validation_started", "task_id": "CIMP-MGND-42", "task_cid": "bafyhealthcid",
                  "attempt": 2, "timestamp": _stamp(1), "worktree_path": work, "log_path": log}
    checked = observe("validating", 5, validation)
    assert checked["scope_liveness"]["validation"] == "fresh"
    assert checked["scope_liveness"]["provider"] == "idle"
    assert checked["validation_activity_verified"] is True
    assert checked["provider_progress_verified"] is False

    merging = observe("merge_reconciliation", 5)
    assert merging["scope_liveness"]["merge"] == "quiet"
    assert merging["scope_liveness"]["provider"] == "idle"
    assert merging["scope_liveness"]["validation"] == "idle"
    assert merging["scope_monitors"]["progress"]["merge"]["progress_stalled"] is False

    stalled = observe("implementing", runner.STALL_SECONDS + 30, log_ago=runner.STALL_SECONDS + 30)
    assert stalled["scope_liveness"]["provider"] == "stalled"
    assert stalled["scope_liveness"]["validation"] == "idle"
    assert stalled["scope_liveness"]["merge"] == "idle"
    assert stalled["application_interview_state"] is None
    assert stalled["scope_monitors"]["progress"]["provider"]["progress_stalled"] is True
    assert stalled["status"] == "stalled"
    assert len(cases) == 4


def test_interview_waits_are_not_scope_stalls(tmp_path, monkeypatch):
    _forbid_dispatch(monkeypatch)
    root, spec, state, _, daemon = _campaign(tmp_path, monkeypatch, {}, started_ago=runner.TIMEOUT_SECONDS + 30)
    waiting = _attempt(state, daemon, phase="awaiting_user", started_ago=runner.TIMEOUT_SECONDS + 5,
                       log_ago=runner.TIMEOUT_SECONDS + 5)
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_task_state.json", waiting)
    before = (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes()
    result = runner.status(root, spec, state)
    assert result["status"] == "stalled"
    assert result["application_interview_state"] == "awaiting_user"
    assert result["scope_liveness"]["claim"] == "expired"
    assert result["scope_liveness"]["worker"] == "alive"
    assert result["scope_liveness"]["provider"] == "excluded_interview"
    assert result["scope_liveness"]["validation"] == "excluded_interview"
    assert result["scope_liveness"]["merge"] == "excluded_interview"
    assert result["scope_monitors"]["progress"]["provider"]["progress_stalled"] is False
    assert (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes() == before

    paused = _attempt(state, daemon, phase="paused", started_ago=20, log_ago=20)
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_task_state.json", paused)
    held = runner.status(root, spec, state)
    assert held["status"] == "waiting_for_user"
    assert held["application_interview_state"] == "paused"
    assert held["scope_liveness"]["claim"] == "held"
    assert held["scope_liveness"]["provider"] == "excluded_interview"
    assert "paused" not in held["scope_liveness"].values()
    assert "awaiting_user" not in held["scope_liveness"].values()


def test_synthetic_recovery_is_bounded_and_preserves_ownership(tmp_path, monkeypatch):
    _forbid_dispatch(monkeypatch)
    monkeypatch.setattr(runner, "_open_recovery_daemon", lambda *a, **k: pytest.fail("duplicate recovery owner"))
    root, spec, state, record, daemon = _campaign(tmp_path, monkeypatch, {})
    dead = _attempt(state, daemon, phase="implementing", started_ago=runner.STALL_SECONDS + 40,
                    log_ago=runner.STALL_SECONDS + 40,
                    owner_process_birth={"pid": 424242, "start_ticks": 9, "boot_id": "dead-owner"})
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_task_state.json", dead)
    state_bytes = (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes()
    launcher_bytes = (state / "launcher.json").read_bytes()
    live = _children()
    started = time.monotonic()
    result = runner.recover_stalled_worker(root, spec, state)
    assert time.monotonic() - started < 12
    assert _children() == live
    assert result["reconciled"] is False
    assert result["paid_dispatch"] is False
    assert result["attempt_refunded"] is False
    assert result["selection_performed"] is False
    assert result["completion_authority"] is False
    assert result["counters_preserved"] is True
    assert result["observed_attempts"]["CIMP-MGND-42"] == 2
    assert (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes() == state_bytes
    assert (state / "launcher.json").read_bytes() == launcher_bytes
    assert record["owner_token"] == "synthetic-owner"

    waiting = _attempt(state, daemon, phase="awaiting_user", started_ago=10, log_ago=10,
                       owner_process_birth={"pid": 424242, "start_ticks": 9, "boot_id": "dead-owner"})
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_task_state.json", waiting)
    held = (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes()
    refused = runner.recover_stalled_worker(root, spec, state)
    assert refused["recovery"] == "blocked"
    assert refused["application_interview_state"] == "awaiting_user"
    assert refused["reason"] == "interview_or_manual_awaiting_user"
    assert refused["paid_dispatch"] is False and refused["attempt_refunded"] is False
    assert (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes() == held
    assert _children() == live
