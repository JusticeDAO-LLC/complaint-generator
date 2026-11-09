"""Public start reconciles only an owned stopped Native crash fence."""
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

import integrations.ipfs_accelerate.improvement_runner as runner
from tests.test_improvement_recovery import _identity, _spec_text, _stamp

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    """Real Native snapshot/lifecycle/accounting; no provider or callback exists.

    This models interrupted fence cleanup with no repo-wide task claim. A
    separate test retains a genuine nonterminal claim and proves refusal.
    Only process/container transports and the final compiler/doctor are inert.
    """
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.merge.worktree_lifecycle import ProcessBirthIdentity
    from test.api.test_agent_supervisor_implementation_protected_paths import (
        POLICY_PATH, _protected_git_worktree_daemon, _seed_active_lifecycle, _persist_active_attempt_state,
    )
    from integrations.ipfs_accelerate.improvement_shutdown import _context
    fixture, root, old, protected = _protected_git_worktree_daemon(tmp_path)
    state = fixture.state_path.parent
    state.mkdir(parents=True, exist_ok=True, mode=0o700); state.chmod(0o700)
    worktrees = state / "worktrees"; worktrees.mkdir(mode=0o700)
    workspace = worktrees / "lane"
    runner.subprocess.run(["git", "worktree", "move", str(old), str(workspace)], cwd=root, check=True, capture_output=True)
    spec = root / runner.SPEC_RELATIVE; spec.parent.mkdir(parents=True, exist_ok=True); spec.write_text(_spec_text())
    board = root / "docs/task_boards/complaint_intake_task_board.md"
    board.write_text("# Tasks\n\n## CIMP-OPS-03 Recovery\n\n- Status: ready\n- Completion: manual\n- Outputs: src/example.py\n")
    environment = runner.campaign_environment(root, state_dir=state)
    for key, value in environment.items():
        if key.startswith(("IPFS_ACCELERATE_", "TODO_DAEMON_")) or key == "COMMON_CRAWL_AUTO_CLONE_SOURCE":
            monkeypatch.setenv(key, value)
    build_argv = runner.native_argv
    monkeypatch.setattr(runner, "native_argv", lambda *a, **k: build_argv(*a, **k) + ["--implementation-protected-path", POLICY_PATH])
    identity = {**_identity(2**30 - 7), "start_ticks": 1, "boot_id": "dead-owner"}
    argv = [sys.executable, str(root / "scripts/run_complaint_improvement_supervisor.py"), "_run",
        "--repo-root", str(root), "--spec", str(spec), "--state-dir", str(state), "--owner-token", "fixture-owner", "--merge-target", "master"]
    record = {"schema_version": "complaint-improvement-launcher@1", "identity": dict(identity, argv=argv),
        "argv": argv, "owner_token": "fixture-owner", "started_at": runner.time.time()-50, "status": "stopped",
        "repo_root": str(root), "spec_path": str(spec), "state_dir": str(state), "merge_target": "master",
        "board_path": str(board), "plan_id": runner._requested_plan_id(spec), "provider": "grok_cli", "model": runner.MODEL, "allow_fallback": False}
    runner._atomic_json(state / "launcher.json", record)
    monkeypatch.setattr(runner, "process_identity", lambda _pid: None)
    daemon = runner._open_recovery_daemon(root, state, record)
    tasks = daemon._load_tasks(); daemon._register_task_identities(tasks); task = tasks[0]
    task_identity = daemon._identity_for_task(task)
    _seed_active_lifecycle(daemon, task, workspace, ProcessBirthIdentity(pid=identity["pid"], start_time_ticks=1, boot_id="dead-owner"), attempt=3)
    daemon._require_implementation_protected_snapshot(task=task, attempt=3, workspace_path=workspace)
    payload = _persist_active_attempt_state(daemon, task=task, workspace=workspace, attempt=3)
    payload.implementation_attempts = {task.task_id: 3}; payload.implementation_attempts_by_cid = {task_identity.canonical_task_cid: 3}
    payload.save(daemon.state_path)
    daemon._record_event("fixture_prior_event", {"provider_dispatched": False})
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_strategy.json", {})
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_supervisor_status.json", {"status": "stopped", "repo_root": str(root),
        "supervisor_pid": identity["pid"], "updated_at": _stamp(), "managed_daemon_cleanup": {"quiesced": True}})
    runner._atomic_json(state / "container_shutdown.json", {**_context(state, record), "schema": "complaint-improvement-container-shutdown@1",
        "status": "stopped", "quiesced": True, "completion_authority": False, "provider_callback_settled": False, "attempt_refunded": False, "containers": []})
    monkeypatch.setattr(runner, "_observe_campaign_containers", lambda *a: True)
    monkeypatch.setattr(runner, "_resource_capacity", lambda *a: {"ready": True})
    monkeypatch.setattr(runner, "_validate_board", lambda *a: {"count": 1, "completed": 0, "ready_task_ids": [task.task_id], "manual_hold_task_ids": []})
    prepared = []
    def prepare(*_args):
        assert not daemon._implementation_protected_active_snapshot_path().exists()
        prepared.append(True)
        return {"board_path": str(board)}
    monkeypatch.setattr(runner, "prepare", prepare)
    monkeypatch.setattr(runner, "doctor", lambda *a, **k: {"status": "not_ready", "fixture_gate": True})
    monkeypatch.setattr(runner, "_signal_birth", lambda *a, **k: pytest.fail("pre-start signalled a process"))
    popen = runner.subprocess.Popen
    def forbid_worker(argv, **kwargs):
        assert "--owner-token" not in argv, "pre-start dispatched a new campaign worker"
        return popen(argv, **kwargs)
    monkeypatch.setattr(runner.subprocess, "Popen", forbid_worker)
    reconciler = native.CrashFenceReconciler
    monkeypatch.setattr(native, "CrashFenceReconciler", lambda daemon: reconciler(daemon, max_hold_seconds=10))
    monkeypatch.chdir(ROOT)
    return dict(root=root, spec=spec, state=state, record=record, daemon=daemon, native=native, prepared=prepared, protected=protected)


@pytest.mark.parametrize("explicit_cas", [False, True])
def test_public_start_reconciles_real_fence_before_prepare_without_nested_lock(campaign, monkeypatch, explicit_cas):
    w = campaign; d = w["daemon"]; native = w["native"]
    before = native.PortalTaskState.load(d.state_path)
    original = runner._lock; held = []; seen = []
    @contextmanager
    def lock(path, name="launcher.lock", **kwargs):
        if name == "recovery.lock":
            assert held == [], "start retained its launcher lock while calling recovery"
        with original(path, name, **kwargs):
            held.append(name); seen.append(name)
            try: yield
            finally: held.pop()
    monkeypatch.setattr(runner, "_lock", lock)
    result = runner.start(w["root"], w["spec"], w["state"], expected_launcher_sha256=digest(w["record"]) if explicit_cas else None)
    assert result.get("doctor", {}).get("fixture_gate") and w["prepared"] == [True], result
    assert seen[:3] == ["recovery.lock", "launcher.lock", "runner.lock"] and seen[-1] == "launcher.lock"
    after = native.PortalTaskState.load(d.state_path)
    assert after.implementation_attempts == before.implementation_attempts == {"CIMP-OPS-03": 3}
    assert after.implementation_attempts_by_cid == before.implementation_attempts_by_cid
    assert after.completed_task_ids == before.completed_task_ids == []
    assert after.last_implementation_returncode is before.last_implementation_returncode is None
    assert after.last_implementation_finished_at == before.last_implementation_finished_at == ""
    assert not any(event["type"] == "implementation_finished" for event in d._iter_events())
    assert not after.implementation_in_progress and not d._implementation_protected_active_snapshot_path().exists()
    assert runner._read_json(w["state"] / "launcher.json") == w["record"]


@pytest.mark.parametrize("damage", ["hold", "operator_stop", "cas", "foreign", "live_reuse", "pid_reuse", "latched", "incident_only", "source", "container", "closure", "marker_unreadable", "empty_snapshot"])
def test_prestart_refuses_unsafe_admission_without_calling_recovery(campaign, monkeypatch, damage):
    w = campaign; state = w["state"]; record = w["record"]; d = w["daemon"]
    expected = digest(record)
    if damage in {"hold", "operator_stop"}:
        (state / "watchdog").mkdir(); (state / "watchdog" / ("HOLD" if damage == "hold" else "OPERATOR_STOP")).touch()
    elif damage == "cas": expected = "0" * 64
    elif damage == "foreign":
        runner._atomic_json(state / "launcher.json", dict(record, repo_root=str(w["root"].parent)))
    elif damage in {"live_reuse", "pid_reuse"}:
        live = record["identity"] if damage == "live_reuse" else dict(record["identity"], start_ticks=2)
        monkeypatch.setattr(runner, "process_identity", lambda pid: live if pid == live["pid"] else None)
    elif damage in {"latched", "incident_only"}:
        runner._atomic_json(state / "implementation-protected-path-incident.json", {"incident": True})
        if damage == "incident_only": d._implementation_protected_active_snapshot_path().unlink()
    elif damage == "source": monkeypatch.setattr(runner, "_read_native_state", lambda *a: ({}, {"source": "unavailable"}))
    elif damage == "container": monkeypatch.setattr(runner, "_observe_campaign_containers", lambda *a: False)
    elif damage == "marker_unreadable":
        lstat = Path.lstat
        def unavailable(path):
            if path == d._implementation_protected_active_snapshot_path(): raise PermissionError("fixture unreadable marker")
            return lstat(path)
        monkeypatch.setattr(Path, "lstat", unavailable)
    elif damage == "empty_snapshot": runner._atomic_json(d._implementation_protected_active_snapshot_path(), {})
    else: runner._atomic_json(state / "container_shutdown.json", {})
    monkeypatch.setattr(runner, "recover_stalled_worker", lambda *a, **k: pytest.fail("unsafe automatic recovery"))
    snapshot = {p: p.read_bytes() for p in (d.state_path, state / "launcher.json") if p.exists()}
    native_before = asdict(w["native"].PortalTaskState.load(d.state_path))
    result = runner.start(w["root"], w["spec"], state, expected_launcher_sha256=expected)
    assert result["status"] == ("already_running" if damage == "live_reuse" else "not_ready")
    assert w["prepared"] == [] and all(p.read_bytes() == raw for p, raw in snapshot.items())
    assert asdict(w["native"].PortalTaskState.load(d.state_path)) == native_before


@pytest.mark.parametrize("change", ["launcher", "hold"])
def test_public_recovery_rechecks_prestart_cas_under_its_own_locks(campaign, monkeypatch, change):
    w = campaign; original = runner._lock
    @contextmanager
    def lock(path, name="launcher.lock", **kwargs):
        if name == "runner.lock":
            if change == "launcher": runner._atomic_json(w["state"] / "launcher.json", dict(w["record"], owner_token="replacement"))
            else:
                (w["state"] / "watchdog").mkdir(); (w["state"] / "watchdog/HOLD").touch()
        with original(path, name, **kwargs): yield
    monkeypatch.setattr(runner, "_lock", lock)
    monkeypatch.setattr(runner, "_open_recovery_daemon", lambda *a, **k: pytest.fail("stale admission opened Native mutation"))
    result = runner.start(w["root"], w["spec"], w["state"], expected_launcher_sha256=digest(w["record"]))
    assert result["reason"] == "prestart_quiesced_recovery_refused" and not w["prepared"]
    assert result["prestart_recovery"]["reason"] == ("launcher_changed_before_recovery" if change == "launcher" else "watchdog_manual_hold")
    assert w["daemon"]._implementation_protected_active_snapshot_path().exists()


@pytest.mark.parametrize("change", ["launcher", "hold"])
def test_normal_start_rechecks_custody_after_successful_recovery(campaign, monkeypatch, change):
    w = campaign; original = runner._lock
    @contextmanager
    def lock(path, name="launcher.lock", **kwargs):
        if name == "launcher.lock" and kwargs.get("blocking", True):
            if change == "launcher": runner._atomic_json(w["state"] / "launcher.json", dict(w["record"], owner_token="replacement"))
            else:
                (w["state"] / "watchdog").mkdir(); (w["state"] / "watchdog/HOLD").touch()
        with original(path, name, **kwargs): yield
    monkeypatch.setattr(runner, "_lock", lock)
    # No caller CAS: automatic recovery must carry its own original capture
    # through the normal locked start admission after recovery releases locks.
    result = runner.start(w["root"], w["spec"], w["state"])
    assert result["reason"] == ("launcher_changed_before_start" if change == "launcher" else "watchdog_manual_hold")
    assert not w["prepared"] and not w["daemon"]._implementation_protected_active_snapshot_path().exists()


def test_real_nonterminal_claim_partial_recovery_never_reaches_prepare(tmp_path, monkeypatch):
    from tests.test_improvement_recovery import _native_recovery_campaign
    from integrations.ipfs_accelerate import pending_claim_runtime as pending
    d, root, _, _, _, claim, spec, record, _ = _native_recovery_campaign(tmp_path, monkeypatch)
    native = runner._native_modules(root)[1]
    before = native.PortalTaskState.load(d.state_path)
    claim_before, board_before = claim.read_bytes(), d.todo_path.read_bytes()
    real_pending, real_state = pending.reconcile_pending_claim, runner._read_native_state
    proof_refused, after_refusal = [], []
    def review(*args, **kwargs):
        try: return real_pending(*args, **kwargs)
        except ValueError as error:
            assert str(error) == "latest_exact_start_required"
            proof_refused.append(True)
            raise
    def observed_state(*args, **kwargs):
        value = real_state(*args, **kwargs)
        if proof_refused: after_refusal.append(value[0])
        return value
    monkeypatch.setattr(pending, "reconcile_pending_claim", review)
    monkeypatch.setattr(runner, "_read_native_state", observed_state)
    monkeypatch.setattr(runner, "_resource_capacity", lambda *a: {"ready": True})
    monkeypatch.setattr(runner, "prepare", lambda *a: pytest.fail("partial recovery reached prepare"))
    result = runner.start(root, spec, d.state_path.parent, expected_launcher_sha256=digest(record))
    assert result["reason"] == "prestart_quiesced_recovery_refused"
    recovery = result["prestart_recovery"]
    assert recovery["recovery"] == "blocked" and recovery["reason"] == "task_claim_reconciliation_blocked"
    assert not recovery["reconciled"] and claim.exists()
    refusal = recovery["pending_claim_reconciliation"]
    assert refusal["reason"] == "latest_exact_start_required" and refusal["blocked"] and not refusal["reconciled"]
    assert all(refusal[key] is False for key in ("completion_authority", "attempt_refunded", "provider_callback_settled", "new_attempt_authority"))
    # Observe the real post-refusal Native payload: classification must not
    # return early before the common accounting/completion invariant checks.
    assert proof_refused and after_refusal
    assert all(value["implementation_attempts"] == before.implementation_attempts
        and value["implementation_attempts_by_cid"] == before.implementation_attempts_by_cid
        and value.get("completed_task_ids", []) == before.completed_task_ids for value in after_refusal)
    assert not (d.state_path.parent / runner._COOLDOWN_NAME).exists()
    after = native.PortalTaskState.load(d.state_path)
    assert after.implementation_attempts == before.implementation_attempts and after.implementation_attempts_by_cid == before.implementation_attempts_by_cid
    assert after.completed_task_ids == before.completed_task_ids == []
    assert after.last_implementation_returncode is before.last_implementation_returncode is None
    assert after.last_implementation_finished_at == before.last_implementation_finished_at == ""
    assert claim.read_bytes() == claim_before and d.todo_path.read_bytes() == board_before
    assert not any(event["type"] == "implementation_finished" for event in d._iter_events())


@pytest.mark.parametrize("other_reason", ["other_fixture_error", "latest_exact_start_required "])
def test_other_pending_value_errors_keep_the_existing_cooldown(tmp_path, monkeypatch, other_reason):
    from tests.test_improvement_recovery import _native_recovery_campaign
    from integrations.ipfs_accelerate import pending_claim_runtime as pending
    d, root, _, _, _, claim, spec, _, _ = _native_recovery_campaign(tmp_path, monkeypatch)
    native = runner._native_modules(root)[1]; before = native.PortalTaskState.load(d.state_path)
    def unavailable(*_args, **_kwargs): raise ValueError(other_reason)
    monkeypatch.setattr(pending, "reconcile_pending_claim", unavailable)
    result = runner.recover_stalled_worker(root, spec, d.state_path.parent)
    assert result["recovery"] == "cooldown" and result["reason"] == "dependency_unavailable"
    assert result["reconciled"] is False and result["paid_dispatch"] is False
    assert result["attempt_refunded"] is False and result["completion_authority"] is False
    after = native.PortalTaskState.load(d.state_path)
    assert after.implementation_attempts == before.implementation_attempts
    assert after.implementation_attempts_by_cid == before.implementation_attempts_by_cid
    assert after.completed_task_ids == before.completed_task_ids == [] and claim.exists()


def test_absent_fences_keep_ordinary_start_without_native_recovery(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_resource_capacity", lambda *a: {"ready": True})
    monkeypatch.setattr(runner, "recover_stalled_worker", lambda *a, **k: pytest.fail("ordinary start invoked recovery"))
    monkeypatch.setattr(runner, "_read_native_state", lambda *a: pytest.fail("ordinary start read Native recovery state"))
    monkeypatch.setattr(runner, "_observe_campaign_containers", lambda *a: True)
    monkeypatch.setattr(runner, "prepare", lambda *a: {"board_path": "/fixture/board"})
    monkeypatch.setattr(runner, "doctor", lambda *a, **k: {"status": "not_ready", "ordinary": True})
    assert runner.start(ROOT, ROOT / runner.SPEC_RELATIVE, tmp_path)["doctor"]["ordinary"]
