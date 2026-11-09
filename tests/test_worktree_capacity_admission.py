"""Actual pinned Git sizing at Native's public before-pass admission hook.

Only observed free-space metadata is controlled. The checkout-size lower
bound comes from real Git trees, and the actual Native loop must refuse
before the inert dispatch sentinel can select a task or spend an attempt.
"""
from pathlib import Path
from types import SimpleNamespace
import subprocess
import pytest
from integrations.ipfs_accelerate import improvement_runner as runner
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon_runner as native_loop


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


def _init(repo):
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Synthetic fixture")
    _git(repo, "config", "user.email", "synthetic@example.invalid")
    (repo / "source.txt").write_bytes(b"s" * 8192)
    _git(repo, "add", "source.txt")
    _git(repo, "commit", "-m", "synthetic pinned source")


def _world(tmp_path, *, available=True):
    repo = tmp_path / "repository"; _init(repo)
    if available:
        data = repo / "external/ipfs_datasets_py"; _init(data)
        pin = _git(data, "rev-parse", "HEAD")
        _git(repo, "update-index", "--add", "--cacheinfo", "160000," + pin + ",external/ipfs_datasets_py")
        _git(repo, "commit", "-m", "synthetic actual dataset pin")
    for name in ("home", "temporary", "worktrees"):
        (tmp_path / name).mkdir()
    return repo


def _observed_roles_ready(monkeypatch, tmp_path):
    metadata = tmp_path / "containerd_metadata"
    metadata.mkdir(mode=0o700)
    monkeypatch.setattr(runner, "_containerd_metadata_directory", lambda: metadata)
    # The first role sample is healthy; a later worktree sample may differ.
    # No policy floor is lowered and filesystem ownership/access stay real.
    monkeypatch.setattr(runner.os, "statvfs", lambda _path: SimpleNamespace(
        f_bavail=runner.RESOURCE_MIN_FREE_BYTES * 2, f_frsize=1,
        f_favail=10000, f_files=20000, f_flag=0))


def _run(tmp_path, repo, *, admitted):
    calls, closed = [], []
    class DispatchSentinel:
        def run_once(self):
            calls.append(True)
            return {"unchanged": True, "write_count": 0}
        def close_event_runtime(self):
            closed.append(True)
    context = native_loop.ImplementationDaemonRunContext(
        parsed=SimpleNamespace(once=True, daemon_hook_timeout_seconds=3, interval=1),
        state_path=tmp_path / "native-state.json", strategy_path=tmp_path / "strategy.json",
        events_path=tmp_path / "events.jsonl")
    context.state_path.write_text('{"implementation_attempts":{"synthetic-task":2}}')
    before = context.state_path.read_bytes()
    def execute():
        native_loop.run_portal_implementation_daemon_loop(DispatchSentinel(), context,
            logger=runner._LOGGER, hooks=(runner._resource_admission_hook(repo,
                tmp_path / "campaign", tmp_path / "worktrees",
                {"HOME": str(tmp_path / "home"), "TMPDIR": str(tmp_path / "temporary")}),))
    if admitted:
        execute()
        assert calls == [True]
    else:
        with pytest.raises(runner.CampaignResourceHold) as refused:
            execute()
        assert refused.value.observation["stage"] == "before_native_pass"
        assert refused.value.observation["paid_dispatch"] is False
        assert refused.value.observation["accounting_changed"] is False
        assert refused.value.observation["attempt_refunded"] is False
        assert calls == []
    assert closed == [True]
    assert context.state_path.read_bytes() == before
    assert not context.events_path.exists() and not (tmp_path / "campaign").exists()


@pytest.mark.parametrize("capacity", ["insufficient", "unavailable"])
def test_actual_native_pass_refuses_cold_checkout_without_selection(tmp_path, monkeypatch, capacity):
    repo = _world(tmp_path, available=capacity != "unavailable")
    _observed_roles_ready(monkeypatch, tmp_path)
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    observed = runner._worktree_capacity(repo, tmp_path / "worktrees")
    assert observed["sufficient"] is (False if capacity == "insufficient" else None)
    _run(tmp_path, repo, admitted=False)


def test_actual_native_pass_accepts_observed_space_for_exact_pinned_trees(tmp_path, monkeypatch):
    repo = _world(tmp_path)
    _observed_roles_ready(monkeypatch, tmp_path)
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _: SimpleNamespace(free=1_000_000))
    observed = runner._worktree_capacity(repo, tmp_path / "worktrees")
    assert observed["sufficient"] is True
    assert observed["minimum_cold_checkout_bytes"] == 16384
    _run(tmp_path, repo, admitted=True)
