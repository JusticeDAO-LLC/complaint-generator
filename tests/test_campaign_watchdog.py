"""Observe real watchdog policy while keeping campaign effects in a fixture."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import os
import shlex

import pytest

from integrations.ipfs_accelerate import campaign_watchdog as module


def _adapter(tmp_path, monkeypatch, *, state="stalled", hold=False, completed=False):
    from ipfs_accelerate_py.agent_supervisor.prompt.prompt_workflow import prompt_workflow_cid
    watcher = object.__new__(module.ComplaintCampaignWatchdog)
    watcher.root = tmp_path
    watcher.state = tmp_path
    watcher.directory = tmp_path / "watchdog"
    watcher.spec_path = tmp_path / "spec.json"
    watcher.spec_path.write_text('{}')
    watcher.spec_sha = module.hashlib.sha256(b'{}').hexdigest()
    watcher.plan_id = "test-plan"
    watcher.artifacts = SimpleNamespace(board_relative="board.md")
    watcher.scope = {k: prompt_workflow_cid({"kind": k}) for k in
        ("repository_root_cid", "policy_root", "run_cid")}
    watcher.clock = lambda: 1000.0
    watcher.latest_status = watcher.latest_observation = watcher.latest_completion = {}
    watcher.last_action = {}
    monkeypatch.setattr(watcher, "_mark_automatic_stop", lambda _: None)
    task = SimpleNamespace(task_id="TASK-1", status="completed" if completed else "todo")
    view = {"status": "complete" if completed else state, "healthy": completed,
        "worker_liveness": "dead", "native_read_errors": {}, "board": {"completed": int(completed), "count": 1},
        "native_state": {"active_task_id": "", "active_task_cid": "", "active_attempt": 0,
            "manual_hold": hold, "implementation_in_progress": False}}
    runner = SimpleNamespace(status=lambda *_: deepcopy(view),
        _native_modules=lambda *_: (None, SimpleNamespace(parse_task_file=lambda *a, **k: [task])),
        TASK_PREFIX="## TASK-", STARTUP_SECONDS=90, STALL_SECONDS=180,
        _event_timestamp=lambda _: None,
        _claim_proof_conflict=lambda _: None,
        _atomic_json=lambda p, x: p.write_text(json.dumps(x)), owns_process=lambda _: True)
    watcher.runner = runner
    monkeypatch.setattr(watcher, "_launch", lambda: ({"started_at": 0, "status": "running"}, True, "owner-1"))
    return watcher, runner, view


def test_native_board_complete_needs_authenticated_completion(tmp_path, monkeypatch):
    from integrations.ipfs_accelerate import campaign_completion
    watcher, runner, view = _adapter(tmp_path, monkeypatch, completed=True)
    monkeypatch.setattr(campaign_completion, "verify_campaign_completion", lambda *a: {"verified": False})
    observed = watcher.observe()
    assert not observed["completion_verified"]
    assert not observed["recovery_permitted"]
    result = watcher.run_once()
    assert result["status"] == "refused"
    assert result["reason"] == "campaign_completion_unverified"


def test_complete_tick_uses_proof_and_owned_cleanup_without_recovery(tmp_path, monkeypatch):
    from integrations.ipfs_accelerate import campaign_completion
    watcher, runner, _ = _adapter(tmp_path, monkeypatch, completed=True)
    monkeypatch.setattr(campaign_completion, "verify_campaign_completion", lambda *a: {"verified": True})
    calls = []
    runner.stop = lambda state, **kw: calls.append(state) or {"status": "stopped", "container_shutdown": {"quiesced": True}}
    monkeypatch.setattr(watcher, "recover", lambda *_: pytest.fail("completed campaign dispatched recovery"))
    result = watcher.run_once(stop_completed=True)
    assert result["status"] == "complete" and result["completion_cleanup"]["quiesced"] is True
    assert calls == [tmp_path]
    assert not (watcher.directory / "campaign-progress-watchdog.json").exists()


@pytest.mark.parametrize("reason", ["manual_hold", "capacity_quarantine", "protected_incident", "awaiting_user"])
def test_intentional_wait_never_stops_or_restarts(tmp_path, monkeypatch, reason):
    watcher, runner, view = _adapter(tmp_path, monkeypatch)
    if reason == "awaiting_user":
        view["application_interview_state"] = "awaiting_user"
    else:
        view["native_state"][reason] = True
    monkeypatch.setattr(watcher, "recover", lambda *_: pytest.fail("hold dispatched recovery"))
    result = watcher.run_once()
    assert result["status"] == "held" and result["reason"] == reason



def test_native_attempt_budget_block_never_restarts_or_rearms_ready_work(tmp_path, monkeypatch):
    watcher, _, view = _adapter(tmp_path, monkeypatch, state="budget_exhausted")
    view["board"]["ready_task_ids"] = ["TASK-1"]
    view["attempt_budget"] = {"reason": "all_selectable_ready_tasks_reached_max_task_attempts",
                              "task_ids": ["TASK-1"], "attempts": {"TASK-1": 3}}
    monkeypatch.setattr(watcher, "recover", lambda *_: pytest.fail("budget block dispatched recovery"))
    before = deepcopy(view)
    result = watcher.run_once()
    assert result["status"] == "held"
    assert watcher.latest_observation["status"] == "budget_exhausted"
    assert not watcher.latest_observation["recovery_permitted"]
    assert not watcher.latest_observation["progress_verified"]
    assert view == before
    assert not (watcher.directory / "campaign-progress-watchdog.json").exists()


def test_observation_token_excludes_polling_heartbeat_and_age(tmp_path, monkeypatch):
    watcher, _, view = _adapter(tmp_path, monkeypatch)
    first = watcher.observe()
    view.update(native_heartbeat_age_seconds=0.002, observed_activity_age_seconds=1000)
    view["native_state"].update(heartbeat_at="new-poll", last_progress_at="new-poll")
    assert watcher.observe() == first
    view["provider_execution_evidence"] = {"frame_counts": {"usage": 1}, "log_bytes": 80}
    assert watcher.observe()["progress_token"] != first["progress_token"]


@pytest.mark.parametrize("native_status", ["blocked", "running"])
def test_ready_work_without_selected_worker_is_recoverable_despite_heartbeat(tmp_path, monkeypatch, native_status):
    watcher, _, view = _adapter(tmp_path, monkeypatch, state=native_status)
    view.update(healthy=True, native_heartbeat_age_seconds=0.001)
    view["board"]["ready_task_ids"] = ["TASK-1"]
    result = watcher.observe()
    assert result["status"] == "no_progress" and result["recovery_permitted"]


def test_recent_implementation_finish_is_not_an_idle_selector(tmp_path, monkeypatch):
    from integrations.ipfs_accelerate.improvement_runner import _event_timestamp
    watcher, runner, view = _adapter(tmp_path, monkeypatch, state="running")
    view.update(healthy=True, worker_liveness="alive", owned_process_alive=True)
    view["board"]["ready_task_ids"] = ["TASK-1"]
    view["native_state"]["last_implementation_finished_at"] = "1970-01-01T00:15:00+00:00"
    runner._event_timestamp = _event_timestamp
    recent = watcher.observe()
    assert recent["status"] == "running" and not recent["recovery_permitted"]
    assert watcher.latest_monitoring["idle_ready"] is False
    view["native_state"]["last_implementation_finished_at"] = "1970-01-01T00:01:40+00:00"
    stalled = watcher.observe()
    assert stalled["status"] == "no_progress" and stalled["recovery_permitted"]
    assert watcher.latest_monitoring["idle_ready"] is True


@pytest.mark.parametrize("legitimate_wait", ["dependencies", "active_worker", "manual_hold", "startup"])
def test_ready_work_detection_preserves_legitimate_waits(tmp_path, monkeypatch, legitimate_wait):
    watcher, _, view = _adapter(tmp_path, monkeypatch, state="blocked")
    view["board"]["ready_task_ids"] = ["TASK-1"]
    if legitimate_wait == "dependencies":
        view["board"]["ready_task_ids"] = []
    elif legitimate_wait == "active_worker":
        view["native_state"].update(active_task_id="TASK-1", active_task_cid="current-cid", implementation_in_progress=True)
    elif legitimate_wait == "manual_hold":
        view["native_state"]["manual_hold"] = True
    else:
        watcher.clock = lambda: 10
    result = watcher.observe()
    assert result["status"] == "blocked" and not result["recovery_permitted"]


@pytest.mark.parametrize("damage", ["owner", "hold", "progress"])
def test_changed_observation_refuses_effects(tmp_path, monkeypatch, damage):
    watcher, runner, view = _adapter(tmp_path, monkeypatch)
    watcher.observe()
    runner.stop = lambda *_: pytest.fail("changed observation signalled owner")
    if damage == "owner":
        monkeypatch.setattr(watcher, "_launch", lambda: ({"started_at": 0}, True, "replacement"))
    elif damage == "hold":
        view["native_state"]["manual_hold"] = True
    else:
        view["provider_execution_evidence"] = {"frame_counts": {"usage": 1}}
    result = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert not result.succeeded and result.reason == "campaign_changed_before_stop"


@pytest.mark.parametrize("blocked_stage", ["stop", "recover", "doctor"])
def test_recovery_stages_require_native_acceptance_and_preserve_accounting(tmp_path, monkeypatch, blocked_stage):
    watcher, runner, _ = _adapter(tmp_path, monkeypatch)
    watcher.spec = {}
    watcher.observe()
    calls = []
    monkeypatch.setattr(watcher, "_accounting", lambda: {"implementation_attempts": {"TASK-1": 2}})
    runner.stop = lambda *_, **kw: calls.append("stop") or {"status": "stop_incomplete" if blocked_stage == "stop" else "stopped"}
    runner.recover_stalled_worker = lambda *_: calls.append("recover") or {"recovery": "blocked" if blocked_stage == "recover" else "reconciled"}
    runner.doctor = lambda *_: calls.append("doctor") or {"status": "not_ready" if blocked_stage == "doctor" else "ready"}
    runner.start = lambda *_: pytest.fail("Native refusal authorized restart")
    result = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert not result.succeeded
    assert calls == ["stop", "recover", "doctor"][:{"stop": 1, "recover": 2, "doctor": 3}[blocked_stage]]


def test_accounting_change_never_restarts(tmp_path, monkeypatch):
    watcher, runner, _ = _adapter(tmp_path, monkeypatch)
    watcher.observe()
    values = iter([{"paid": 2}, {"paid": 0}])
    monkeypatch.setattr(watcher, "_accounting", lambda: next(values))
    runner.stop = lambda *_, **kw: {"status": "stopped"}
    runner.recover_stalled_worker = lambda *_: {"recovery": "reconciled"}
    runner.start = lambda *_: pytest.fail("changed accounting authorized restart")
    with pytest.raises(RuntimeError, match="accounting_changed"):
        watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))


def test_restart_requires_native_reconciliation_and_real_followup_progress(tmp_path, monkeypatch):
    watcher, runner, view = _adapter(tmp_path, monkeypatch)
    watcher.observe()
    calls = []
    monkeypatch.setattr(watcher, "_accounting", lambda: {"attempts": 2})
    runner.stop = lambda *_, **kw: calls.append("stop") or {"status": "stopped"}
    runner.recover_stalled_worker = lambda *_: calls.append("recover") or {"recovery": "reconciled"}
    runner.doctor = lambda *_: calls.append("doctor") or {"status": "ready"}
    def start(*_, **kw):
        calls.append("start")
        view.update(status="active", healthy=True, provider_progress_verified=True)
        view["native_state"].update(active_task_id="TASK-1", active_task_cid="current-task-cid", active_attempt=2)
        return {"status": "starting"}
    runner.start = start
    result = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert result.succeeded and result.healthy
    assert result.observed_effects == ("old_lane_fenced", "lane_restarted")
    assert calls == ["stop", "recover", "doctor", "start"]


def test_recovery_deadline_prevents_even_owned_stop(tmp_path, monkeypatch):
    watcher, runner, _ = _adapter(tmp_path, monkeypatch)
    watcher.observe()
    monkeypatch.setattr(watcher, "_accounting", lambda: {})
    runner.stop = lambda *_: pytest.fail("expired action signalled owner")
    with pytest.raises(TimeoutError):
        watcher.recover(SimpleNamespace(deadline_at_ms=999_999))


def test_manual_stop_is_held_but_verified_automatic_stop_can_resume(tmp_path, monkeypatch):
    watcher, runner, view = _adapter(tmp_path, monkeypatch, state="stopped")
    monkeypatch.setattr(watcher, "_launch", lambda: ({"started_at": 0, "status": "stopped"}, True, "owner-1"))
    monkeypatch.setattr(watcher, "_automatic_stop_matches", lambda *_: False)
    assert watcher.observe()["hold_reason"] == "manual_hold"
    monkeypatch.setattr(watcher, "_automatic_stop_matches", lambda *_: True)
    runner.doctor = lambda *_: {"status": "ready"}
    result = watcher.observe()
    assert result["recovery_permitted"] and not result["manual_hold"]
    runner.doctor = lambda *_: {"status": "not_ready"}
    assert watcher.observe()["hold_reason"] == "dependency_unavailable"


@pytest.mark.parametrize("change", ["hold", "owner"])
def test_doctor_cannot_override_new_hold_or_replacement_owner(tmp_path, monkeypatch, change):
    watcher, runner, view = _adapter(tmp_path, monkeypatch)
    watcher.observe()
    monkeypatch.setattr(watcher, "_accounting", lambda: {"attempts": 2})
    runner.stop = lambda *a, **kw: {"status": "stopped"}
    runner.recover_stalled_worker = lambda *_: {"recovery": "reconciled"}
    def doctor(*_):
        if change == "hold":
            view["native_state"]["manual_hold"] = True
        else:
            monkeypatch.setattr(watcher, "_launch", lambda: ({"started_at": 0}, True, "new-owner"))
        return {"status": "ready"}
    runner.doctor = doctor
    runner.start = lambda *a, **kw: pytest.fail("doctor overrode current campaign control")
    result = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert not result.succeeded and result.reason == "campaign_changed_before_restart"


@pytest.mark.parametrize("operation", ["start", "stop"])
def test_native_effect_cas_runs_under_launcher_lock(tmp_path, monkeypatch, operation):
    from contextlib import contextmanager
    from integrations.ipfs_accelerate import improvement_runner as runner
    state = tmp_path / "campaign"
    state.mkdir()
    original = {"owner": "first"}
    (state / "launcher.json").write_text(json.dumps(original))
    @contextmanager
    def raced_lock(*a, **kw):
        (state / "launcher.json").write_text(json.dumps({"owner": "replacement"}))
        yield
    monkeypatch.setattr(runner, "_lock", raced_lock)
    monkeypatch.setattr(runner, "_signal_birth", lambda *a: pytest.fail("replacement owner signalled"))
    if operation == "start":
        monkeypatch.setattr(runner, "_select_worktree_root", lambda *a: (tmp_path, None))
        monkeypatch.setattr(runner, "_resource_capacity", lambda *a: {"ready": True})
        result = runner.start(tmp_path, tmp_path / "spec", state,
            expected_launcher_sha256=module._digest(original))
    else:
        result = runner.stop(state, expected_launcher_sha256=module._digest(original))
    assert result["status"] == "stop_incomplete"
    assert result["reason"] == "launcher_changed_before_" + operation


def test_hold_created_during_native_preflight_prevents_spawn(tmp_path, monkeypatch):
    from integrations.ipfs_accelerate import improvement_runner as runner, improvement_plan
    state = tmp_path / "campaign"
    state.mkdir()
    (state / "launcher.json").write_text('{}')
    monkeypatch.setattr(runner, "_select_worktree_root", lambda *a: (tmp_path, None))
    monkeypatch.setattr(runner, "_resource_capacity", lambda *a: {"ready": True})
    monkeypatch.setattr(runner, "owns_process", lambda *_: False)
    monkeypatch.setattr(runner, "_observe_campaign_containers", lambda *a: True)
    monkeypatch.setattr(runner, "process_identity", lambda *_: None)
    monkeypatch.setattr(runner, "prepare", lambda *a: {"board_path": str(tmp_path / "board")})
    def doctor(*a, **kw):
        (state / "watchdog").mkdir()
        (state / "watchdog/HOLD").write_text('operator hold')
        return {"status": "ready", "merge_target": "test", "native_plan_id": "plan"}
    monkeypatch.setattr(runner, "doctor", doctor)
    monkeypatch.setattr(improvement_plan, "load_spec", lambda *_: {"execution_policy": {}})
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("held campaign spawned"))
    result = runner.start(tmp_path, tmp_path / "spec", state, expected_launcher_sha256=module._digest({}))
    assert result["status"] == "not_ready" and result["reason"] == "watchdog_manual_hold"
    assert result["execution_started"] is False


def test_units_bind_campaign_and_do_not_kill_detached_native_owner(tmp_path):
    root = tmp_path / "repo with spaces"
    root.mkdir()
    spec = root / "spec.json"
    spec.write_text('{}')
    state = tmp_path / "campaign"
    state.mkdir()
    units = module.systemd_units(root, spec, state, interpreter="/usr/bin/python3", plan_id="plan", spec_sha256="ab" * 32)
    assert "KillMode=process\n" in units["service"]
    assert '"watchdog" "--once" "--stop-completed"' in units["service"]
    assert '"--expected-plan-id" "plan"' in units["service"]
    assert '"--expected-spec-sha256"' in units["service"]
    assert "TimeoutStartSec=1800" in units["service"]
    assert "WorkingDirectory=" + str(root) + "\n" in units["service"]
    assert "Persistent=true" in units["timer"] and "OnCalendar=*-*-* *:*:00" in units["timer"]


def _install_fixture(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    spec = root / "spec.json"
    spec.write_text('{}')
    state = tmp_path / "campaign"
    state.mkdir()
    watcher = SimpleNamespace(root=root, spec_path=spec, state=state, directory=state / "watchdog",
        plan_id="plan", spec_sha="ab" * 32)
    monkeypatch.setattr(module, "ComplaintCampaignWatchdog", lambda *a, **kw: watcher)
    monkeypatch.setattr(module, "_watchdog_executable_path", lambda *a, **kw: os.defpath)
    return watcher, tmp_path / "units"


def test_installer_verifies_enables_and_runs_only_its_dedicated_unit(tmp_path, monkeypatch):
    watcher, folder = _install_fixture(tmp_path, monkeypatch)
    commands = []
    result = module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", unit_directory=folder,
        command_runner=lambda args, **kw: commands.append(args))
    name = result["unit"]
    assert [c[:3] for c in commands] == [["systemd-analyze", "--user", "verify"],
        ["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable"],
        ["systemctl", "--user", "start"]]
    assert commands[2][-1] == name + ".timer" and commands[3][-1] == name + ".service"
    assert set(p.name for p in folder.iterdir()) == {name + ".service", name + ".timer"}
    commands.clear()
    assert module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", unit_directory=folder,
        command_runner=lambda args, **kw: commands.append(args))["unit"] == name


def test_installer_preserves_conflicting_existing_units(tmp_path, monkeypatch):
    watcher, folder = _install_fixture(tmp_path, monkeypatch)
    units = module.systemd_units(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", plan_id="plan", spec_sha256="ab" * 32)
    folder.mkdir()
    timer = folder / (units["name"] + ".timer")
    timer.write_text('an existing user unit')
    with pytest.raises(ValueError, match="existing_unit_conflict"):
        module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
            interpreter="/usr/bin/python3", unit_directory=folder,
            command_runner=lambda *a, **kw: pytest.fail("conflicting unit enabled"))
    assert timer.read_text() == 'an existing user unit'
    assert not (folder / (units["name"] + ".service")).exists()


def test_rendered_units_pass_installed_systemd_parser_with_spaced_paths(tmp_path):
    import shutil
    import subprocess
    assert shutil.which("systemd-analyze"), "systemd parser required for installer validation"
    root = tmp_path / "repo with spaces"
    root.mkdir()
    spec = root / "spec.json"
    spec.write_text('{}')
    state = tmp_path / "campaign with spaces"
    state.mkdir()
    units = module.systemd_units(root, spec, state, interpreter="/usr/bin/python3", plan_id="plan", spec_sha256="ab" * 32)
    paths = []
    for kind in ("service", "timer"):
        path = tmp_path / (units["name"] + "." + kind)
        path.write_text(units[kind])
        paths.append(str(path))
    result = subprocess.run(["systemd-analyze", "--user", "verify", *paths], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def _executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 98\n")
    path.chmod(0o700)
    return path


def _environment_path(service):
    assignments = [shlex.split(line.partition("=")[2]) for line in service.splitlines()
                   if line.startswith('Environment="PATH=')]
    assert len(assignments) == 1 and len(assignments[0]) == 1
    # Environment= expands percent specifiers, but dollars are literal.
    return assignments[0][0].removeprefix("PATH=").replace("%%", "%")


def _ready_preflight():
    return {"status": "ready", "grok_binary_present": True, "auth_material_present": True,
            "privacy": {"ready": True}, "worktree_capacity": {"sufficient": True},
            "resource_capacity": {"ready": True}}


def test_executable_path_retains_symlink_entrypoints_and_local_node_without_running_them(tmp_path, monkeypatch):
    import subprocess
    interpreter_target = _executable(tmp_path / "system/bin/python-real")
    interpreter = tmp_path / "venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(interpreter_target)
    provider_target = _executable(tmp_path / "downloads/provider-release")
    provider = tmp_path / "local tools/bin/grok"
    provider.parent.mkdir(parents=True)
    provider.symlink_to(provider_target)
    tools = [_executable(tmp_path / name / "bin" / name) for name in ("node", "docker", "git")]
    unused = tmp_path / "unused-secret-directory"
    unused.mkdir()
    environment = {"PATH": os.pathsep.join([str(provider.parent), *(str(p.parent) for p in tools),
                    ".", "relative", "", str(unused)]), "XAI_API_KEY": "synthetic-secret-must-not-copy"}
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("PATH discovery executed a tool"))
    result = module._watchdog_executable_path(interpreter, environment)
    directories = result.split(os.pathsep)
    assert directories[0] == str(interpreter.parent.resolve())
    assert str(provider.parent.resolve()) in directories
    assert str(provider_target.parent.resolve()) not in directories
    assert all(str(tool.parent.resolve()) in directories for tool in tools)
    assert all(Path(value).is_absolute() and Path(value).is_dir() for value in directories)
    assert len(directories) == len(set(directories))
    assert not {"", ".", "relative", str(unused)} & set(directories)
    assert "synthetic-secret-must-not-copy" not in result
    for tool in ("grok", "node", "docker", "git"):
        assert module.shutil.which(tool, path=result), tool


def test_executable_path_rejects_missing_provider_without_activation(tmp_path, monkeypatch):
    import subprocess
    interpreter = _executable(tmp_path / "venv/bin/python")
    monkeypatch.setattr(module.shutil, "which", lambda *a, **kw: None)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("missing provider was executed"))
    with pytest.raises(ValueError, match="watchdog_grok_executable_unavailable"):
        module._watchdog_executable_path(interpreter, {"PATH": str(tmp_path)})


@pytest.mark.parametrize("relative", [".", "relative-bin"])
def test_executable_path_does_not_turn_cwd_commands_into_service_authority(tmp_path, monkeypatch, relative):
    interpreter = _executable(tmp_path / "venv/bin/python")
    _executable(tmp_path / relative / "grok")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="watchdog_executable_path_invalid"):
        module._watchdog_executable_path(interpreter, {"PATH": relative})


def test_service_path_defaults_are_absolute_and_explicit_path_preserves_literal_dollars(tmp_path):
    root, state = tmp_path / "repo", tmp_path / "campaign"
    root.mkdir()
    state.mkdir()
    spec = root / "spec.json"
    spec.write_text('{}')
    arguments = dict(interpreter="/usr/bin/python3", plan_id="plan", spec_sha256="ab" * 32)
    default = module.systemd_units(root, spec, state, **arguments)
    assert _environment_path(default["service"]) == os.defpath
    assert all(Path(part).is_absolute() for part in _environment_path(default["service"]).split(os.pathsep))
    directory = tmp_path / 'tools with $literal %percent "quote"'
    directory.mkdir()
    executable_path = str(directory) + os.pathsep + os.defpath
    explicit = module.systemd_units(root, spec, state, executable_path=executable_path, **arguments)
    assert _environment_path(explicit["service"]) == executable_path
    assert "$literal" in explicit["service"] and "$$literal" not in explicit["service"]
    assert "%%percent" in explicit["service"]


@pytest.mark.parametrize("executable_path", ["", ".:/usr/bin", "/usr/bin:", "relative", "/usr/bin\nXAI_API_KEY=secret"])
def test_service_path_rejects_empty_relative_and_environment_injection(tmp_path, executable_path):
    spec = tmp_path / "spec.json"
    spec.write_text('{}')
    with pytest.raises(ValueError, match="watchdog_executable_path_invalid"):
        module.systemd_units(tmp_path, spec, tmp_path, interpreter="/usr/bin/python3", plan_id="plan",
                             spec_sha256="ab" * 32, executable_path=executable_path)


def test_installer_captures_discovered_executables_and_only_that_public_environment(tmp_path, monkeypatch):
    watcher, folder = _install_fixture(tmp_path, monkeypatch)
    tools = tmp_path / "public tools"
    tools.mkdir()
    executable_path = str(tools) + os.pathsep + os.defpath
    calls = []
    monkeypatch.setattr(module, "_watchdog_executable_path",
        lambda interpreter: calls.append(interpreter) or executable_path)
    monkeypatch.setenv("XAI_API_KEY", "synthetic-secret-must-not-copy")
    result = module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", unit_directory=folder, command_runner=lambda *a, **kw: None)
    service = (folder / (result["unit"] + ".service")).read_text()
    assert calls == ["/usr/bin/python3"]
    assert _environment_path(service) == executable_path
    assert "synthetic-secret-must-not-copy" not in service and "XAI_API_KEY" not in service


def test_installer_missing_provider_cannot_enable_units(tmp_path, monkeypatch):
    watcher, folder = _install_fixture(tmp_path, monkeypatch)
    def unavailable(*a, **kw):
        raise ValueError("watchdog_grok_executable_unavailable")
    monkeypatch.setattr(module, "_watchdog_executable_path", unavailable)
    with pytest.raises(ValueError, match="watchdog_grok_executable_unavailable"):
        module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
            interpreter="/usr/bin/python3", unit_directory=folder,
            command_runner=lambda *a, **kw: pytest.fail("unavailable provider enabled a unit"))
    assert not folder.exists() or not list(folder.iterdir())


def _legacy_units(watcher, folder):
    units = module.systemd_units(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", plan_id=watcher.plan_id, spec_sha256=watcher.spec_sha)
    folder.mkdir()
    service = folder / (units["name"] + ".service")
    timer = folder / (units["name"] + ".timer")
    legacy = "\n".join(line for line in units["service"].splitlines()
                       if not line.startswith('Environment="PATH=')) + "\n"
    service.write_text(legacy)
    timer.write_text(units["timer"])
    return units, service, timer


def test_installer_upgrades_only_exact_previous_managed_service_and_is_idempotent(tmp_path, monkeypatch):
    watcher, folder = _install_fixture(tmp_path, monkeypatch)
    units, service, timer = _legacy_units(watcher, folder)
    timer_before = (timer.read_bytes(), timer.stat().st_ino)
    dropin = folder / (units["name"] + ".service.d")
    dropin.mkdir()
    custom = dropin / "operator.conf"
    custom.write_text('[Service]\nNice=5\n')
    calls = []
    first = module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", unit_directory=folder, command_runner=lambda *a, **kw: calls.append(a))
    assert first["updated_units"] == [service.name]
    assert service.read_text() == units["service"]
    assert (timer.read_bytes(), timer.stat().st_ino) == timer_before
    assert custom.read_text() == '[Service]\nNice=5\n'
    inode = service.stat().st_ino
    second = module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", unit_directory=folder, command_runner=lambda *a, **kw: calls.append(a))
    assert second["updated_units"] == [] and service.stat().st_ino == inode
    assert len(calls) == 8


@pytest.mark.parametrize("damage", ["customized", "foreign_plan", "hardlink"])
def test_managed_upgrade_preserves_custom_foreign_or_aliased_service(tmp_path, monkeypatch, damage):
    watcher, folder = _install_fixture(tmp_path, monkeypatch)
    _, service, _ = _legacy_units(watcher, folder)
    if damage == "customized":
        service.write_text(service.read_text() + '# operator customization\n')
    elif damage == "foreign_plan":
        service.write_text(service.read_text().replace('"plan"', '"foreign-plan"'))
    else:
        os.link(service, tmp_path / "alias.service")
    before = service.read_bytes()
    with pytest.raises(ValueError, match="watchdog_existing_unit_conflict"):
        module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
            interpreter="/usr/bin/python3", unit_directory=folder,
            command_runner=lambda *a, **kw: pytest.fail("conflicting managed service enabled"))
    assert service.read_bytes() == before


def test_managed_upgrade_rechecks_service_before_atomic_replacement(tmp_path, monkeypatch):
    import tempfile
    watcher, folder = _install_fixture(tmp_path, monkeypatch)
    _, service, _ = _legacy_units(watcher, folder)
    mkstemp = tempfile.mkstemp
    replacement = '# operator replaced the service during preflight\n'
    def race(*a, **kw):
        result = mkstemp(*a, **kw)
        service.write_text(replacement)
        return result
    monkeypatch.setattr(tempfile, "mkstemp", race)
    with pytest.raises(ValueError, match="watchdog_existing_unit_conflict"):
        module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
            interpreter="/usr/bin/python3", unit_directory=folder,
            command_runner=lambda *a, **kw: pytest.fail("raced managed service enabled"))
    assert service.read_text() == replacement


@pytest.mark.parametrize("field,member,reason", [
    ("grok_binary_present", None, "grok_executable_missing"),
    ("auth_material_present", None, "provider_auth_material_missing"),
    ("privacy", "ready", "private_runtime_unavailable"),
    ("worktree_capacity", "sufficient", "worktree_capacity_insufficient"),
    ("resource_capacity", "ready", "resource_capacity_unavailable"),
])
def test_preflight_reports_the_specific_missing_dependency_without_sensitive_bodies(field, member, reason):
    check = _ready_preflight()
    check["status"] = "not_ready"
    if member is None:
        check[field] = False
    else:
        check[field][member] = False
    check.update(reason="secret diagnostic body", auth={"token": "synthetic-private-token"})
    summary = module._preflight_summary(check)
    assert summary["status"] == "not_ready" and summary["reasons"] == [reason]
    assert "secret diagnostic body" not in json.dumps(summary)
    assert "synthetic-private-token" not in json.dumps(summary)


@pytest.mark.parametrize("check", [None, [], {}, {"status": []}, {"status": {"private": "value"}}])
def test_preflight_missing_or_malformed_status_is_unknown_not_healthy(check):
    summary = module._preflight_summary(check)
    assert summary["status"] == "unknown" and summary["reasons"] == ["preflight_status_unknown"]
    assert all(summary[key] is None for key in ("grok_binary_present", "auth_material_present",
        "private_runtime_ready", "worktree_capacity_sufficient", "resource_capacity_ready"))


def test_preflight_does_not_promote_truthy_strings_or_integers_to_observed_booleans():
    summary = module._preflight_summary({"status": "not_ready", "grok_binary_present": "False",
        "auth_material_present": 1, "privacy": {"ready": "yes"},
        "worktree_capacity": {"sufficient": []}, "resource_capacity": {"ready": 0}})
    assert summary == {"status": "not_ready", "reasons": ["preflight_not_ready"],
        "grok_binary_present": None, "auth_material_present": None, "private_runtime_ready": None,
        "worktree_capacity_sufficient": None, "resource_capacity_ready": None}
    ready = module._preflight_summary(_ready_preflight())
    assert ready["status"] == "ready" and ready["reasons"] == []


def test_missing_grok_hold_clears_without_resetting_persistent_recovery_budget_or_paid_counts(tmp_path, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.rescue import campaign_watchdog as native
    watcher, runner, view = _adapter(tmp_path, monkeypatch, state="stopped")
    watcher.spec = {}
    now = [1000.0]
    watcher.clock = lambda: now[0]
    actual_watchdog = native.CampaignProgressWatchdog
    def deterministic_watchdog(*a, **kw):
        return actual_watchdog(*a, **kw, clock_ms=lambda: int(now[0] * 1000))
    monkeypatch.setattr(native, "CampaignProgressWatchdog", deterministic_watchdog)
    monkeypatch.setattr(watcher, "_launch", lambda: ({"started_at": 0, "status": "stopped"}, True, "owner-1"))
    monkeypatch.setattr(watcher, "_automatic_stop_matches", lambda *_: True)
    check = _ready_preflight()
    check.update(status="not_ready", grok_binary_present=False)
    runner.doctor = lambda *_: deepcopy(check)
    paid = {"implementation_attempts": {"TASK-1": 2}, "protected_implementation_attempts": {"TASK-1": 2}}
    paid_before = deepcopy(paid)
    monkeypatch.setattr(watcher, "_accounting", lambda: deepcopy(paid))
    effects = []
    runner.stop = lambda *a, **kw: effects.append("stop") or {"status": "stopped"}
    runner.recover_stalled_worker = lambda *_: effects.append("recover") or {"recovery": "reconciled"}
    def start(*a, **kw):
        effects.append("start")
        view.update(status="active", healthy=True, provider_progress_verified=True)
        view["native_state"].update(active_task_id="TASK-1", active_task_cid="current-cid", active_attempt=2)
        return {"status": "starting"}
    runner.start = start
    ledger = watcher.directory / "campaign-progress-watchdog.json"
    held = watcher.run_once()
    assert held["status"] == "held" and held["reason"] == "dependency_unavailable"
    assert held["preflight"]["reasons"] == ["grok_executable_missing"]
    assert not ledger.exists() and effects == []
    check.update(status="ready", grok_binary_present=True)
    for ordinal in (1, 2):
        first = watcher.run_once()
        assert first["status"] == "confirming"
        assert watcher.run_once()["status"] == "confirming"  # Same clock is not another confirmation.
        assert len(effects) == (ordinal - 1) * 3
        now[0] += 31
        recovered = watcher.run_once()
        assert recovered["status"] == "recovered"
        state = json.loads(ledger.read_text())
        assert len(state["incidents"]) == 1
        assert next(iter(state["incidents"].values()))["attempts"] == ordinal
        assert next(iter(state["incidents"].values()))["phase"] == "finished"
        assert paid == paid_before
        # A later unavailable service context must preserve this ledger exactly.
        view.update(status="stopped", healthy=False, provider_progress_verified=False)
        view["native_state"].update(active_task_id="", active_task_cid="", active_attempt=0)
        check.update(status="not_ready", grok_binary_present=False)
        before = ledger.read_bytes()
        assert watcher.run_once()["status"] == "held"
        assert ledger.read_bytes() == before
        check.update(status="ready", grok_binary_present=True)
        now[0] += 61
    exhausted = watcher.run_once()
    assert exhausted["status"] == "exhausted" and exhausted["reason"] == "incident_recovery_budget_exhausted"
    assert effects == ["stop", "recover", "start"] * 2 and paid == paid_before


def test_timer_keeps_calendar_and_persistence_with_parsed_monotonic_fallback(tmp_path):
    import shutil
    import subprocess
    assert shutil.which("systemd-analyze"), "systemd parser required for timer validation"
    spec = tmp_path / "spec.json"
    spec.write_text('{}')
    units = module.systemd_units(tmp_path, spec, tmp_path, interpreter="/usr/bin/python3",
        plan_id="plan", spec_sha256="ab" * 32)
    timer = units["timer"]
    assert timer.count("OnUnitInactiveSec=60s\n") == 1
    assert "OnCalendar=*-*-* *:*:00\n" in timer
    assert "Persistent=true\n" in timer and "AccuracySec=1s\n" in timer
    paths = []
    for kind in ("service", "timer"):
        path = tmp_path / (units["name"] + "." + kind)
        path.write_text(units[kind])
        paths.append(str(path))
    result = subprocess.run(["systemd-analyze", "--user", "verify", *paths],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def _legacy_timer_with_current_service(watcher, folder):
    units = module.systemd_units(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", plan_id=watcher.plan_id, spec_sha256=watcher.spec_sha)
    folder.mkdir()
    service = folder / (units["name"] + ".service")
    timer = folder / (units["name"] + ".timer")
    service.write_text(units["service"])
    timer.write_text("\n".join(line for line in units["timer"].splitlines()
                               if line != "OnUnitInactiveSec=60s") + "\n")
    return units, service, timer


def test_installer_upgrades_exact_old_timer_without_touching_service_dropins_or_holds(tmp_path, monkeypatch):
    watcher, folder = _install_fixture(tmp_path, monkeypatch)
    units, service, timer = _legacy_timer_with_current_service(watcher, folder)
    preserved = [service]
    for kind in ("service", "timer"):
        directory = folder / (units["name"] + "." + kind + ".d")
        directory.mkdir()
        path = directory / "operator.conf"
        path.write_text('# existing operator settings\n')
        preserved.append(path)
    watcher.directory.mkdir()
    hold = watcher.directory / "HOLD"
    hold.write_text('operator maintenance remains held')
    preserved.append(hold)
    before = {path: (path.read_bytes(), path.stat().st_ino) for path in preserved}
    calls = []
    result = module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", unit_directory=folder,
        command_runner=lambda *a, **kw: calls.append(a))
    assert result["updated_units"] == [timer.name]
    assert timer.read_text() == units["timer"]
    assert {path: (path.read_bytes(), path.stat().st_ino) for path in preserved} == before
    timer_inode = timer.stat().st_ino
    repeated = module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", unit_directory=folder,
        command_runner=lambda *a, **kw: calls.append(a))
    assert repeated["updated_units"] == [] and timer.stat().st_ino == timer_inode
    assert {path: (path.read_bytes(), path.stat().st_ino) for path in preserved} == before
    assert len(calls) == 8


@pytest.mark.parametrize("damage", ["customized", "foreign_service", "hardlink"])
def test_timer_upgrade_refuses_custom_foreign_or_aliased_timer(tmp_path, monkeypatch, damage):
    watcher, folder = _install_fixture(tmp_path, monkeypatch)
    units, service, timer = _legacy_timer_with_current_service(watcher, folder)
    if damage == "customized":
        timer.write_text(timer.read_text() + '# operator customization\n')
    elif damage == "foreign_service":
        timer.write_text(timer.read_text().replace("Unit=" + units["name"] + ".service", "Unit=foreign.service"))
    else:
        os.link(timer, tmp_path / "alias.timer")
    before = {path: path.read_bytes() for path in (service, timer)}
    with pytest.raises(ValueError, match="watchdog_existing_unit_conflict"):
        module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
            interpreter="/usr/bin/python3", unit_directory=folder,
            command_runner=lambda *a, **kw: pytest.fail("conflicting timer enabled"))
    assert {path: path.read_bytes() for path in (service, timer)} == before


def test_timer_upgrade_rechecks_bytes_before_atomic_replacement(tmp_path, monkeypatch):
    import tempfile
    watcher, folder = _install_fixture(tmp_path, monkeypatch)
    _, service, timer = _legacy_timer_with_current_service(watcher, folder)
    service_before = (service.read_bytes(), service.stat().st_ino)
    mkstemp = tempfile.mkstemp
    replacement = '# operator replaced the timer during preflight\n'
    def race(*a, **kw):
        result = mkstemp(*a, **kw)
        timer.write_text(replacement)
        return result
    monkeypatch.setattr(tempfile, "mkstemp", race)
    with pytest.raises(ValueError, match="watchdog_existing_unit_conflict"):
        module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
            interpreter="/usr/bin/python3", unit_directory=folder,
            command_runner=lambda *a, **kw: pytest.fail("raced timer enabled"))
    assert timer.read_text() == replacement
    assert (service.read_bytes(), service.stat().st_ino) == service_before


def _dead_startup_adapter(tmp_path, monkeypatch, *, launch_status="starting"):
    watcher, runner, view = _adapter(tmp_path, monkeypatch, state="stop_incomplete")
    view.update(owned_process_alive=False, worker_liveness="dead")
    launch = {"schema_version": "complaint-improvement-launcher@1", "started_at": 0,
              "status": launch_status, "identity": {"pid": 99999999, "start_ticks": 1, "boot_id": "fixture-boot"}}
    expected_birth = deepcopy(launch["identity"])
    runner._owner_liveness = lambda birth: "dead" if birth == expected_birth else "missing"
    monkeypatch.setattr(watcher, "_launch", lambda: (deepcopy(launch), True, "owner-1"))
    return watcher, runner, view, launch


@pytest.mark.parametrize("launch_status", ["starting", "running"])
@pytest.mark.parametrize("worker_liveness", ["dead", "absent"])
def test_bound_unexpected_dead_owner_gets_normal_recovery_without_claiming_closure(tmp_path, monkeypatch, launch_status, worker_liveness):
    watcher, runner, view, _ = _dead_startup_adapter(tmp_path, monkeypatch, launch_status=launch_status)
    view["worker_liveness"] = worker_liveness
    runner.stop = lambda *a, **kw: pytest.fail("observation performed cleanup")
    observed = watcher.observe()
    assert observed["status"] == "daemon_failed" and observed["recovery_permitted"] is True
    assert observed["completion_verified"] is False and observed["healthy"] is False
    assert observed["manual_hold"] is False and observed["progress_verified"] is False
    assert watcher.latest_status["status"] == view["status"] == "stop_incomplete"
    assert "container_shutdown_verified" not in observed


@pytest.mark.parametrize("exclusion", [
    "manual_stopped", "manual_stop_incomplete", "unknown", "pid_reuse", "live", "owned_alive",
    "owned_unknown", "foreign_scope", "read_error", "claim_conflict", "manual_hold", "cancelled",
    "capacity_quarantine", "protected_incident", "awaiting_user", "launch_alive", "launch_unknown",
    "launch_pid_reuse", "launch_birth_missing",
])
def test_dead_startup_recovery_does_not_override_manual_or_uncertain_ownership(tmp_path, monkeypatch, exclusion):
    watcher, runner, view, launch = _dead_startup_adapter(tmp_path, monkeypatch)
    if exclusion in {"manual_stopped", "manual_stop_incomplete"}:
        launch["status"] = "stopped" if exclusion == "manual_stopped" else "stop_incomplete"
    elif exclusion in {"unknown", "pid_reuse", "live"}:
        view["worker_liveness"] = "alive" if exclusion == "live" else exclusion
    elif exclusion == "owned_alive":
        view["owned_process_alive"] = True
    elif exclusion == "owned_unknown":
        view.pop("owned_process_alive")
    elif exclusion == "foreign_scope":
        monkeypatch.setattr(watcher, "_launch", lambda: (deepcopy(launch), False, "foreign-owner"))
    elif exclusion in {"launch_alive", "launch_unknown", "launch_pid_reuse"}:
        runner._owner_liveness = lambda _: exclusion.removeprefix("launch_")
    elif exclusion == "launch_birth_missing":
        launch.pop("identity")
    elif exclusion == "read_error":
        view["native_read_errors"] = {"state": "fixture_unavailable"}
    elif exclusion == "claim_conflict":
        runner._claim_proof_conflict = lambda _: "fixture_claim_mismatch"
    elif exclusion == "cancelled":
        view["native_state"]["manual_cancellation"] = True
    elif exclusion == "awaiting_user":
        view["application_interview_state"] = "awaiting_user"
    else:
        view["native_state"][exclusion] = True
    monkeypatch.setattr(watcher, "recover", lambda *_: pytest.fail("excluded owner dispatched recovery"))
    observed = watcher.observe()
    assert observed["recovery_permitted"] is False
    result = watcher.run_once()
    assert result["status"] in {"held", "refused"}
    assert result["native_status"] == "stop_incomplete"


@pytest.mark.parametrize("saved_owner_liveness", ["alive", "unknown", "pid_reuse", "missing", None])
def test_absent_native_worker_never_substitutes_for_proved_dead_saved_launcher(tmp_path, monkeypatch, saved_owner_liveness):
    watcher, runner, view, _ = _dead_startup_adapter(tmp_path, monkeypatch)
    view["worker_liveness"] = "absent"
    runner._owner_liveness = lambda _: saved_owner_liveness
    monkeypatch.setattr(watcher, "recover", lambda *_: pytest.fail("unproved saved launcher dispatched recovery"))
    assert watcher.observe()["recovery_permitted"] is False
    assert watcher.run_once()["status"] == "refused"


@pytest.mark.parametrize("stop_status", ["stop_incomplete", "stopped"])
def test_dead_startup_uses_spaced_sdk_confirmation_and_public_stop_cas_before_restart(tmp_path, monkeypatch, stop_status):
    from ipfs_accelerate_py.agent_supervisor.rescue import campaign_watchdog as native
    watcher, runner, view, launch = _dead_startup_adapter(tmp_path, monkeypatch)
    view["worker_liveness"] = "absent"  # Real post-reconciliation startup failure shape.
    watcher.spec = {}
    now = [1000.0]
    watcher.clock = lambda: now[0]
    actual_watchdog = native.CampaignProgressWatchdog
    def deterministic_watchdog(*a, **kw):
        return actual_watchdog(*a, **kw, clock_ms=lambda: int(now[0] * 1000))
    monkeypatch.setattr(native, "CampaignProgressWatchdog", deterministic_watchdog)
    monkeypatch.setattr(watcher, "_automatic_stop_matches", lambda *_: True)
    paid = {"implementation_attempts": {"TASK-1": 3}, "protected_implementation_attempts": {"TASK-1": 3}}
    before = deepcopy(paid)
    monkeypatch.setattr(watcher, "_accounting", lambda: deepcopy(paid))
    calls, stop_digests = [], []
    expected_digest = module._digest(launch)
    def stop(*a, **kw):
        calls.append("stop")
        stop_digests.append(kw.get("expected_launcher_sha256"))
        if stop_status == "stopped":
            launch["status"] = "stopped"
            view["status"] = "stopped"
        return {"status": stop_status}
    runner.stop = stop
    runner.recover_stalled_worker = lambda *_: calls.append("recover") or {"recovery": "reconciled"}
    runner.doctor = lambda *_: _ready_preflight()
    def start(*a, **kw):
        calls.append("start")
        launch["status"] = "starting"
        view.update(status="active", healthy=True, provider_progress_verified=True,
                    worker_liveness="alive", owned_process_alive=True)
        view["native_state"].update(active_task_id="TASK-1", active_task_cid="current-cid", active_attempt=3)
        return {"status": "starting"}
    runner.start = start
    assert watcher.run_once()["status"] == "confirming"
    assert watcher.run_once()["status"] == "confirming" and calls == []
    now[0] += 31
    result = watcher.run_once()
    assert stop_digests == [expected_digest]
    if stop_status == "stop_incomplete":
        assert result["status"] == "cooldown" and calls == ["stop"]
        assert result["native_status"] == "stop_incomplete"
        assert result["last_action"]["stop_status"] == "stop_incomplete"
    else:
        assert result["status"] == "recovered" and calls == ["stop", "recover", "start"]
        assert result["last_action"]["stage"] == "verified_progress"
    ledger = json.loads((watcher.directory / "campaign-progress-watchdog.json").read_text())
    assert len(ledger["incidents"]) == 1
    assert next(iter(ledger["incidents"].values()))["attempts"] == 1
    assert paid == before


@pytest.mark.parametrize("after_restart", ["starting", "manual_hold", "daemon_failed"])
def test_proved_restart_effects_are_not_uncertain_when_health_is_pending(tmp_path, monkeypatch, after_restart):
    """A finite health observation never changes already proved effect custody."""
    watcher, runner, view = _adapter(tmp_path, monkeypatch)
    now = [1000.0]
    watcher.clock = lambda: now[0]
    monkeypatch.setattr(module.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    watcher.observe()
    calls = []
    accounting = {"implementation_attempts": {"TASK-1": 2}}
    monkeypatch.setattr(watcher, "_accounting", lambda: deepcopy(accounting))
    runner.stop = lambda *_, **kw: calls.append("stop") or {"status": "stopped"}
    runner.recover_stalled_worker = lambda *_: calls.append("recover") or {"recovery": "reconciled"}
    runner.doctor = lambda *_: calls.append("doctor") or {"status": "ready"}
    def start(*_, **kw):
        calls.append("start")
        view.update(status="starting" if after_restart == "manual_hold" else after_restart,
            healthy=False, provider_progress_verified=False)
        if after_restart == "manual_hold":
            view["native_state"]["manual_hold"] = True
        return {"status": "starting"}
    runner.start = start
    result = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert not result.succeeded and not result.healthy
    assert result.reason == "restart_waiting_for_verified_progress"
    assert result.observed_effects == ("old_lane_fenced", "lane_restarted")
    assert result.partial is False
    assert calls == ["stop", "recover", "doctor", "start"]
    assert now[0] <= 1090.0
    assert accounting == {"implementation_attempts": {"TASK-1": 2}}
    if after_restart == "manual_hold":
        assert watcher.observe()["manual_hold"] is True


def test_health_pending_restart_retains_native_ordinal_without_uncertainty(tmp_path, monkeypatch):
    """Use Native's real durable finite controller across a slow semantic start."""
    from ipfs_accelerate_py.agent_supervisor.rescue.campaign_watchdog import (
        CampaignProgressWatchdog, CampaignProgressWatchdogPolicy,
    )
    watcher, runner, view = _adapter(tmp_path, monkeypatch)
    now = [1000.0]
    watcher.clock = lambda: now[0]
    monkeypatch.setattr(module.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    accounting = {"implementation_attempts": {"TASK-1": 2}}
    monkeypatch.setattr(watcher, "_accounting", lambda: deepcopy(accounting))
    calls = []
    runner.stop = lambda *_, **kw: calls.append("stop") or {"status": "stopped"}
    runner.recover_stalled_worker = lambda *_: calls.append("recover") or {"recovery": "reconciled"}
    runner.doctor = lambda *_: calls.append("doctor") or {"status": "ready"}
    def start(*_, **kw):
        calls.append("start")
        view.update(status="starting", healthy=False, provider_progress_verified=False)
        return {"status": "starting"}
    runner.start = start
    def native():
        return CampaignProgressWatchdog(watcher.directory, repository_root=watcher.root,
            scope=watcher.scope, observe=watcher.observe, recover=watcher.recover,
            policy=CampaignProgressWatchdogPolicy(deadline_ms=1_200_000),
            clock_ms=lambda: int(now[0] * 1000))
    assert native().run_once()["status"] == "confirming"
    now[0] += 31
    result = native().run_once()
    assert result["status"] == "cooldown" and result["reason"] == "recovery_not_yet_healthy"
    ledger = json.loads(native().state_path.read_text())
    entry = next(iter(ledger["incidents"].values()))
    assert entry["phase"] == "finished" and entry["attempts"] == 1
    assert entry["terminal_cid"] == result["terminal_cid"]
    assert accounting == {"implementation_attempts": {"TASK-1": 2}}
    assert calls == ["stop", "recover", "doctor", "start"]
    view.update(status="stalled")
    now[0] += 61
    retry = native().run_once()
    assert retry["status"] == "confirming"
    assert retry["reason"] == "failure_confirmation_pending"
    unchanged = json.loads(native().state_path.read_text())
    assert next(iter(unchanged["incidents"].values()))["attempts"] == 1
    assert calls == ["stop", "recover", "doctor", "start"]
