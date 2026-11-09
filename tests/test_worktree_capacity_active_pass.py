"""Cold capacity is checked between blocking passes, never inside active work."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import threading
import time

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon_runner as native_loop
from tests.test_worktree_capacity_admission import _world, _observed_roles_ready


def test_public_native_loop_does_not_recheck_cold_capacity_inside_a_blocking_pass(tmp_path, monkeypatch):
    repo = _world(tmp_path)
    _observed_roles_ready(monkeypatch, tmp_path)
    free = [1_000_000]
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _: SimpleNamespace(free=free[0]))
    samples, entered, closed, failures = [], threading.Event(), [], []
    actual_capacity = runner._worktree_capacity

    def sample(*args):
        value = actual_capacity(*args)
        samples.append(value)
        return value

    monkeypatch.setattr(runner, "_worktree_capacity", sample)

    class BlockingPass:
        calls = 0
        child = None
        completed = False

        def run_once(self):
            self.calls += 1
            # A real inert owned process, with no provider or Native task state.
            self.child = subprocess.Popen([sys.executable, "-I", "-B", "-c",
                "import sys; print('ready', flush=True); raise SystemExit(0 if sys.stdin.read(1)=='x' else 3)"],
                cwd=tmp_path, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            assert self.child.stdout.readline().strip() == "ready"
            entered.set()
            assert self.child.wait(timeout=10) == 0
            self.completed = True
            return {"unchanged": True, "write_count": 0}

        def wait_for_wake(self, *, timeout):
            assert self.completed

        def close_event_runtime(self):
            assert self.child is None or self.child.poll() is not None
            closed.append(True)

    daemon = BlockingPass()

    def reduce_free_during_actual_work():
        try:
            assert entered.wait(10)
            assert daemon.child.poll() is None
            free[0] = 1
            time.sleep(.05)
            assert daemon.child.poll() is None
            assert len(samples) == 1 and samples[0]["sufficient"] is True
            assert daemon.completed is False and closed == []
        except BaseException as exc:
            failures.append(exc)
        finally:
            if daemon.child is not None and daemon.child.poll() is None:
                daemon.child.stdin.write("x")
                daemon.child.stdin.flush()

    observer = threading.Thread(target=reduce_free_during_actual_work, name="private-capacity-control")
    context = native_loop.ImplementationDaemonRunContext(
        parsed=SimpleNamespace(once=False, daemon_hook_timeout_seconds=3, interval=0),
        state_path=tmp_path / "native-state.json", strategy_path=tmp_path / "strategy.json",
        events_path=tmp_path / "events.jsonl")
    observer.start()
    try:
        with pytest.raises(runner.CampaignResourceHold) as refused:
            native_loop.run_portal_implementation_daemon_loop(daemon, context, logger=runner._LOGGER,
                hooks=(runner._resource_admission_hook(repo, tmp_path / "campaign", tmp_path / "worktrees",
                    {"HOME": str(tmp_path / "home"), "TMPDIR": str(tmp_path / "temporary")}),))
        assert refused.value.observation["reason"] == "cold_checkout_capacity_insufficient"
        assert daemon.completed is True and daemon.calls == 1
        assert len(samples) == 2 and samples[1]["sufficient"] is False
        assert closed == [True]
        assert not context.state_path.exists() and not context.events_path.exists()
    finally:
        if daemon.child is not None and daemon.child.poll() is None:
            daemon.child.kill()
            daemon.child.wait(timeout=5)
        observer.join(timeout=5)
    assert not observer.is_alive() and failures == []


def test_actual_legacy_supervisor_child_command_is_not_an_once_poll(tmp_path):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    repo = _world(tmp_path)
    board = repo / "board.md"
    board.write_text("# Synthetic board\n")
    args = native.parse_args(runner.native_argv(board, tmp_path / "campaign", "main",
        worktree_root=tmp_path / "worktrees"))
    config = native.supervisor_config_from_args(args, repo_root=repo, daemon_script_path=Path(runner.__file__))
    supervisor = native.PortalImplementationSupervisor(config)
    command = supervisor._build_daemon_command()
    assert config.plan_bound_dispatch is False
    assert "--once" not in command
    assert command[1] == str(Path(runner.__file__))
    assert command[command.index("--todo-path") + 1] == str(board)
