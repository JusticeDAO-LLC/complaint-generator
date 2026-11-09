"""Containerd metadata is a separate physical role before task admission.

Only metadata-path discovery and selected filesystem samples are controlled.
The directories, canonical-path checks, public doctor/start boundary and Native
before-pass loop are real; the dispatch sentinel cannot select a task or spend.
"""
from pathlib import Path
from types import SimpleNamespace
import os
import pytest
from integrations.ipfs_accelerate import improvement_runner as runner


@pytest.fixture
def storage(tmp_path, monkeypatch):
    paths = {name: tmp_path / name for name in
             ("repository", "worktrees", "home", "temporary", "containerd_metadata")}
    for path in paths.values():
        path.mkdir(mode=0o700)
    paths["state"] = tmp_path / "state"
    monkeypatch.setattr(runner, "_containerd_metadata_directory", lambda: paths["containerd_metadata"])
    monkeypatch.setenv("HOME", str(paths["home"]))
    monkeypatch.setenv("TMPDIR", str(paths["temporary"]))
    return paths


def _observe(paths):
    return runner._resource_capacity(paths["repository"], paths["state"], paths["worktrees"], os.environ)


def _metadata_sample(monkeypatch, paths, *, free_bytes=None, free_inodes=None, readonly=False, error=None):
    original = os.statvfs
    def sample(path):
        if Path(path) != paths["containerd_metadata"]:
            return original(path)
        if error is not None:
            raise error
        actual = original(path)
        return SimpleNamespace(f_bavail=actual.f_bavail if free_bytes is None else free_bytes,
            f_frsize=actual.f_frsize if free_bytes is None else 1,
            f_favail=actual.f_favail if free_inodes is None else free_inodes,
            f_files=actual.f_files, f_flag=os.ST_RDONLY if readonly else actual.f_flag)
    monkeypatch.setattr(runner.os, "statvfs", sample)


def test_real_private_metadata_directory_is_observed_without_operator_access(storage, monkeypatch):
    original = os.access
    monkeypatch.setattr(runner.os, "access", lambda path, *a, **k:
        False if Path(path) == storage["containerd_metadata"] else original(path, *a, **k))
    observed = _observe(storage)
    actual = os.statvfs(storage["containerd_metadata"])
    assert observed["ready"] is True
    row = observed["roles"]["containerd_metadata"]
    assert row["free_bytes"] == actual.f_bavail * actual.f_frsize
    assert row["free_inodes"] == actual.f_favail
    assert row["path_source"] == "standard_rootful_containerd"
    assert row["write_access_scope"] == "filesystem_flag_for_rootful_daemon"
    assert not storage["state"].exists()
    assert observed["capacity_reserved"] is False


def test_metadata_capacity_at_existing_policy_floors_is_admissible(storage, monkeypatch):
    _metadata_sample(monkeypatch, storage, free_bytes=runner.RESOURCE_MIN_FREE_BYTES,
                     free_inodes=runner.RESOURCE_MIN_FREE_INODES)
    assert _observe(storage)["ready"] is True


@pytest.mark.parametrize("failure", ["zero_bytes", "below_bytes", "zero_inodes", "below_inodes",
                                    "readonly", "unavailable", "malformed"])
def test_metadata_failure_holds_while_all_other_storage_roles_are_ready(storage, monkeypatch, failure):
    _metadata_sample(monkeypatch, storage,
        free_bytes=0 if failure == "zero_bytes" else runner.RESOURCE_MIN_FREE_BYTES - 1
            if failure == "below_bytes" else "unknown" if failure == "malformed" else None,
        free_inodes=0 if failure == "zero_inodes" else runner.RESOURCE_MIN_FREE_INODES - 1
            if failure == "below_inodes" else None,
        readonly=failure == "readonly", error=PermissionError("fixture statvfs denied")
            if failure == "unavailable" else None)
    observed = _observe(storage)
    assert observed["ready"] is False
    assert observed["roles"]["containerd_metadata"]["ready"] is False
    assert all(row["ready"] for name, row in observed["roles"].items() if name != "containerd_metadata")
    assert observed["minimum_free_bytes_per_filesystem"] == 1_073_741_824
    assert observed["minimum_free_inodes_per_filesystem"] == 1024
    assert not storage["state"].exists()
    assert observed["paid_dispatch"] is False and observed["accounting_changed"] is False
    assert observed["attempt_refunded"] is False and observed["live_wait_or_lease_claimed"] is False


@pytest.mark.parametrize("kind", ["missing", "regular_file", "symlink", "relative", "parent_alias"])
def test_metadata_location_must_be_an_existing_canonical_directory(storage, monkeypatch, kind):
    directory = storage["containerd_metadata"]
    if kind == "missing":
        candidate = directory / "missing"
    elif kind == "regular_file":
        candidate = directory / "file"; candidate.write_text("fixture")
    elif kind == "symlink":
        candidate = directory.parent / "alias"; candidate.symlink_to(directory, target_is_directory=True)
    elif kind == "relative":
        candidate = Path("relative-containerd")
    else:
        candidate = directory / ".." / directory.name
    calls = []
    actual = os.statvfs
    monkeypatch.setattr(runner, "_containerd_metadata_directory", lambda: candidate)
    monkeypatch.setattr(runner.os, "statvfs", lambda path: calls.append(Path(path)) or actual(path))
    observed = _observe(storage)
    row = observed["roles"]["containerd_metadata"]
    assert observed["ready"] is False and row["reason"] == "local_capacity_unavailable"
    assert "filesystem_path" not in row
    assert candidate not in calls and directory not in calls
    assert all(row["ready"] for name, row in observed["roles"].items() if name != "containerd_metadata")
    assert not storage["state"].exists()
    if kind == "missing":
        assert not candidate.exists()  # no healthy ancestor fallback or creation


@pytest.mark.parametrize("operation", ["doctor", "start", "internal"])
def test_full_metadata_refuses_public_admission_before_native_or_state(storage, monkeypatch, operation):
    _metadata_sample(monkeypatch, storage, free_bytes=0, free_inodes=0)
    monkeypatch.setattr(runner, "_native_modules", lambda *a: pytest.fail("metadata hold imported Native"))
    monkeypatch.setattr(runner, "_lock", lambda *a, **k: pytest.fail("metadata hold created a lock"))
    monkeypatch.setattr(runner, "prepare", lambda *a: pytest.fail("metadata hold rewrote task board"))
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: pytest.fail("metadata hold spawned an actor"))
    spec = storage["repository"] / "unread-spec.json"
    if operation == "internal":
        with pytest.raises(runner.CampaignResourceHold) as refused:
            runner.run_internal(storage["repository"], spec, storage["state"], "fixture-owner", "campaign")
        observed = refused.value.observation
        assert observed["stage"] == "before_owned_startup_lock"
    else:
        call = runner.doctor if operation == "doctor" else runner.start
        result = call(storage["repository"], spec, storage["state"], worktree_root=storage["worktrees"])
        assert result["status"] == "not_ready" and result["reason"] == "campaign_resource_hold"
        assert result["paid_calls"] == 0 and result["execution_started"] is False
        observed = result["resource_capacity"]
    assert observed["roles"]["containerd_metadata"]["ready"] is False
    assert not storage["state"].exists() and not spec.exists()
    assert list(storage["worktrees"].iterdir()) == []


def test_actual_native_before_pass_preserves_attempts_when_metadata_is_full(storage, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon_runner as native
    _metadata_sample(monkeypatch, storage, free_bytes=0, free_inodes=0)
    calls, closed = [], []
    class DispatchSentinel:
        def run_once(self):
            calls.append(True)
            pytest.fail("metadata hold reached task selection")
        def close_event_runtime(self):
            closed.append(True)
    context = native.ImplementationDaemonRunContext(
        parsed=SimpleNamespace(once=True, daemon_hook_timeout_seconds=3, interval=1),
        state_path=storage["home"] / "native-state.json", strategy_path=storage["home"] / "strategy.json",
        events_path=storage["home"] / "events.jsonl")
    context.state_path.write_text('{"implementation_attempts":{"fixture-task":2}}')
    before = context.state_path.read_bytes()
    with pytest.raises(runner.CampaignResourceHold) as refused:
        native.run_portal_implementation_daemon_loop(DispatchSentinel(), context,
            logger=runner._LOGGER, hooks=(runner._resource_admission_hook(storage["repository"],
                storage["state"], storage["worktrees"], os.environ),))
    assert refused.value.observation["roles"]["containerd_metadata"]["free_bytes"] == 0
    assert refused.value.observation["stage"] == "before_native_pass"
    assert refused.value.observation["accounting_changed"] is False
    assert calls == [] and closed == [True]
    assert context.state_path.read_bytes() == before and not context.events_path.exists()
    assert not storage["state"].exists()
