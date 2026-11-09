"""Live observation contracts plus genuine zero-paid native process recovery.

Facade controls are unit tests, not live acceptance. The process case really
crashes an owned OS child and uses native supervision/lifecycle CAS, without
claiming a paid Grok crash or the ordinary implementation-claim-file protocol.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

# Load this checkout's actual entrypoint; another installed regular `scripts`
# package must not redirect this namespace-package source import.
import importlib.util
_ENTRY_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_complaint_improvement_supervisor.py"
_ENTRY_SPEC = importlib.util.spec_from_file_location("scripts.run_complaint_improvement_supervisor", _ENTRY_PATH)
assert _ENTRY_SPEC is not None and _ENTRY_SPEC.loader is not None
_loaded_entry = importlib.util.module_from_spec(_ENTRY_SPEC)
sys.modules[_ENTRY_SPEC.name] = _loaded_entry
_ENTRY_SPEC.loader.exec_module(_loaded_entry)
import scripts.run_complaint_improvement_supervisor as entry
assert entry is _loaded_entry and Path(entry.__file__).resolve() == _ENTRY_PATH
from ipfs_accelerate_py.agent_supervisor.merge import worktree_lifecycle as lifecycle
from ipfs_accelerate_py.agent_supervisor.todo_daemon.core import ManagedDaemonSpec, pid_alive
from ipfs_accelerate_py.agent_supervisor.todo_daemon.supervisor_loop import (
    SupervisorLoop, SupervisorLoopConfig, SupervisorLoopDecision,
)
from ipfs_accelerate_py.agent_supervisor.todo_daemon.supervisor_runtime import (
    RestartPolicy, SUPERVISED_CHILD_IDENTITY_PATH_ENV, SUPERVISED_CHILD_OWNER_SCOPE_ENV,
    load_supervised_child_identity, terminate_supervised_child,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

# Installed before ANY native import in the authored child. No provider,
# socket connection, arbitrary shell command or further worker may be launched.
CHILD_GUARD = r'''
import os, pathlib, socket, subprocess, sys
root = pathlib.Path(sys.argv[1]).resolve(strict=True)
assert root == pathlib.Path.cwd().resolve(strict=True)
assert root.name == "native-owned-process" and root.stat().st_uid == os.getuid()
assert root.stat().st_mode & 0o077 == 0
keep = {key: os.environ[key] for key in (
    "PATH", "PYTHONPATH", "HOME", "TMPDIR", "LANG", "LC_ALL",
    "COMMON_CRAWL_AUTO_CLONE_SOURCE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE",
    "IPFS_ACCELERATE_META_INDEX_DUCKDB", "IPFS_ACCELERATE_META_INDEX_DUCKLAKE",
    "IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR",
) if key in os.environ}
os.environ.clear()
os.environ.update(keep)
assert pathlib.Path(os.environ["IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR"]).resolve(strict=True) == root / "state" / "control-plane"
def denied(*args, **kwargs):
    raise PermissionError("owned_fixture_external_effect_denied")
original_socket = socket.socket
class ClosedSocket(original_socket):
    def __init__(self, family=socket.AF_INET, *args, **kwargs):
        if family in (socket.AF_INET, socket.AF_INET6): return denied()
        super().__init__(family, *args, **kwargs)
    def connect(self, *args, **kwargs): return denied()
    def connect_ex(self, *args, **kwargs): return denied()
    def sendto(self, *args, **kwargs): return denied()
socket.socket = ClosedSocket
socket.create_connection = socket.getaddrinfo = denied
original_popen = subprocess.Popen
class ClosedPopen:
    @classmethod
    def __class_getitem__(cls, _): return cls
    def __new__(cls, command, *args, **kwargs):
        if not isinstance(command, (list, tuple)) or kwargs.get("shell"):
            return denied()
        parts = list(map(str, command))
        if not parts or parts[0] not in ("git", "/usr/bin/git"):
            return denied()
        tail = parts[1:]
        cwd = pathlib.Path(kwargs.get("cwd") or pathlib.Path.cwd()).resolve(strict=True)
        if tail[:1] == ["-C"]:
            if len(tail) < 3: return denied()
            cwd = pathlib.Path(tail[1]).resolve(strict=True)
            tail = tail[2:]
        if cwd != root: return denied()
        allowed = tail in (["rev-parse", "--git-common-dir"], ["rev-parse", "--show-toplevel"],
                           ["rev-parse", "HEAD"], ["rev-parse", "--is-inside-work-tree"])
        allowed = allowed or tail in (["worktree", "add", "--detach", str(root / "workspace-1"), "HEAD"],
                                     ["worktree", "add", "--detach", str(root / "workspace-2"), "HEAD"])
        if not allowed: return denied()
        return original_popen(command, *args, **kwargs)
subprocess.Popen = ClosedPopen
os.system = subprocess.call = denied
GUARD_ACTIVE = socket.socket is ClosedSocket and subprocess.Popen is ClosedPopen
'''

WORKER_SOURCE = r'''
from pathlib import Path
import sys
exec(compile(Path(__file__).with_name("process_guard.py").read_bytes(),
             str(Path(__file__).with_name("process_guard.py")), "exec"))
import json, os, time, subprocess
from ipfs_accelerate_py.agent_supervisor.merge import worktree_lifecycle as lifecycle
root = Path(sys.argv[1]).resolve(strict=True)
mode = sys.argv[2]
birth = lifecycle.current_process_birth()
assert birth.pid == os.getpid() and birth.start_time_ticks > 0 and birth.boot_id

def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True))
    os.replace(temporary, path)

common = {"birth": birth.to_dict(), "guard_active": GUARD_ACTIVE,
          "native_origin": str(Path(lifecycle.__file__).resolve())}
if mode == "sentinel":
    write(root / "sentinel-ready.json", common)
    deadline = time.monotonic() + 30
    while not (root / "sentinel-stop").exists() and time.monotonic() < deadline:
        time.sleep(.01)
    raise SystemExit(0)
assert mode == "worker"
store = lifecycle.WorktreeLifecycleStore(root, store_dir=root / "state" / "lifecycle")
first = store.load_task_attempt(canonical_task_cid="synthetic-ops06-cid", task_id="OPS06-PRIVATE", attempt=1)
attempt = 1 if first is None else 2
if first is not None:
    retired = store.reclaim_dead_owner_for_controlled_restart(
        first.workspace_path, expected_state_dir=root / "state", reason="injected_owned_process_crash")
    assert retired is not None and retired.is_terminal and retired.fence > first.fence
workspace = root / ("workspace-" + str(attempt))
record = store.begin_preparing(task_id="OPS06-PRIVATE", canonical_task_cid="synthetic-ops06-cid",
    attempt=attempt, lane_id="private-fixture", workspace_path=workspace,
    branch="private-fixture-" + str(attempt), merge_target="main", state_dir=str(root / "state"))
subprocess.run(["git", "worktree", "add", "--detach", str(workspace), "HEAD"], cwd=root,
               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
record = store.mark_active(workspace, lease_id=record.lease_id, expected_fence=record.fence)
write(root / ("ready-" + str(attempt) + ".json"), {**common, "record": record.to_dict(),
      "guard_sha256": __import__("hashlib").sha256(Path(__file__).with_name("process_guard.py").read_bytes()).hexdigest()})
deadline = time.monotonic() + 15
sequence = 0
while time.monotonic() < deadline:
    sequence += 1
    write(root / ("progress-" + str(attempt) + ".json"), {"pid": os.getpid(), "sequence": sequence})
    if attempt == 1 and (root / "inject-crash").exists():
        os._exit(37)
    time.sleep(.02)
raise SystemExit(79)
'''


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


def _wait(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    assert predicate(), "owned fixture observation timed out"


def _read(path):
    return json.loads(path.read_text())


def test_real_owned_worker_failure_recovers_once_without_duplicate_leases(tmp_path, monkeypatch):
    """Actual OS failure/restart/claim exclusion; zero model/paid transport."""
    assert os.name == "posix" and Path("/proc/self/stat").is_file()
    root = tmp_path / "native-owned-process"
    root.mkdir(mode=0o700)
    state = root / "state"
    state.mkdir(mode=0o700)
    (state / "control-plane").mkdir(mode=0o700)
    monkeypatch.setenv("IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR", str(state / "control-plane"))
    for name in ("home", "temporary"):
        (root / name).mkdir(mode=0o700)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "core.hooksPath", "/dev/null")
    _git(root, "config", "user.name", "Owned Synthetic Fixture")
    _git(root, "config", "user.email", "synthetic@example.invalid")
    (root / "README").write_text("Synthetic data only.\n")
    _git(root, "add", "README")
    _git(root, "commit", "-qm", "Synthetic baseline")
    baseline = _git(root, "rev-parse", "HEAD")
    program, guard = root / "owned_worker.py", root / "process_guard.py"
    program.write_text(WORKER_SOURCE)
    guard.write_text(CHILD_GUARD)
    program.chmod(0o600)
    guard.chmod(0o600)
    native_root = Path(lifecycle.__file__).resolve().parents[3]
    environment = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(native_root),
        "HOME": str(root / "home"), "TMPDIR": str(root / "temporary"), "LANG": "C", "LC_ALL": "C",
        "COMMON_CRAWL_AUTO_CLONE_SOURCE": "0", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "IPFS_ACCELERATE_META_INDEX_DUCKDB": "", "IPFS_ACCELERATE_META_INDEX_DUCKLAKE": "",
        "IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR": str(state / "control-plane")}
    identity = state / "worker.identity.json"
    environment[SUPERVISED_CHILD_IDENTITY_PATH_ENV] = str(identity)
    environment[SUPERVISED_CHILD_OWNER_SCOPE_ENV] = json.dumps({"repo_root": str(root), "state_dir": str(state)})
    command = (sys.executable, str(program), str(root), "worker")
    spec = ManagedDaemonSpec(name="ops06-private", schema="synthetic-owned-process@1", repo_root=root,
        daemon_dir=state, runner=command, status_path=state / "child.json",
        supervisor_status_path=state / "supervisor.json", supervisor_pid_path=state / "supervisor.pid",
        child_pid_path=state / "worker.pid", supervisor_out_path=state / "supervisor.out",
        ensure_status_path=state / "ensure.json", ensure_check_path=state / "check.json",
        supervisor_lock_path=state / "launch.lock")
    store = lifecycle.WorktreeLifecycleStore(root, store_dir=state / "lifecycle")
    sentinel = subprocess.Popen([sys.executable, str(program), str(root), "sentinel"], cwd=root,
        env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    sentinel_birth = lifecycle.read_process_birth(sentinel.pid)
    assert sentinel_birth is not None and sentinel_birth.start_time_ticks > 0
    observed = {}
    captured_child = []
    deadline = time.monotonic() + 20

    def watchdog(loop, child, _status):
        captured_child[:] = [child]
        if time.monotonic() > deadline:
            return SupervisorLoopDecision.stop("fixture_deadline", status="fixture_timeout")
        first_path = root / "ready-1.json"
        if not first_path.exists() or not (root / "progress-1.json").exists():
            return SupervisorLoopDecision.keep_running()
        first = _read(first_path)
        if "first" not in observed:
            observed["first"] = first
            observed["first_identity"] = load_supervised_child_identity(identity)
            observed["first_heartbeat"] = _read(spec.supervisor_status_path)["updated_at"]
            observed["first_progress"] = _read(root / "progress-1.json")["sequence"]
            assert lifecycle.read_process_birth(child.pid) is not None
            assert child.pid == first["birth"]["pid"]
            with pytest.raises(lifecycle.DuplicateAttemptError):
                store.begin_preparing(task_id="OPS06-PRIVATE", canonical_task_cid="synthetic-ops06-cid",
                    attempt=1, lane_id="competing-private", workspace_path=root / "duplicate-workspace",
                    branch="duplicate", merge_target="main", state_dir=str(state))
            assert store.reclaim_dead_owner_for_controlled_restart(root / "workspace-1", expected_state_dir=state) is None
            observed["duplicate_refused"] = True
            return SupervisorLoopDecision.keep_running()
        if not (root / "inject-crash").exists():
            heartbeat = _read(spec.supervisor_status_path)["updated_at"]
            progress = _read(root / "progress-1.json")["sequence"]
            if heartbeat != observed["first_heartbeat"] and progress > observed["first_progress"]:
                observed["second_heartbeat"] = heartbeat
                (root / "inject-crash").write_text("owned synthetic fault\n")
            return SupervisorLoopDecision.keep_running()
        second_path = root / "ready-2.json"
        if not second_path.exists() or not (root / "progress-2.json").exists():
            return SupervisorLoopDecision.keep_running()
        second = _read(second_path)
        progress = _read(root / "progress-2.json")
        observed.setdefault("second_initial", progress)
        if progress["sequence"] <= observed["second_initial"]["sequence"]:
            return SupervisorLoopDecision.keep_running()
        observed.update(second=second, second_progress=progress,
                        failed_exit=loop.last_exit_code,
                        second_identity=load_supervised_child_identity(identity))
        return SupervisorLoopDecision.stop("owned_successor_progress_observed")

    loop = SupervisorLoop(SupervisorLoopConfig(spec=spec, command=command, log_prefix="owned-worker",
        child_env=environment, max_restarts=2, heartbeat_seconds=.02, poll_seconds=.02,
        watchdog_startup_grace_seconds=0, watchdog_stale_after_seconds=30, stop_grace_seconds=.2,
        restart_policy=RestartPolicy(restart_backoff_seconds=.02, fast_restart_backoff_seconds=.02)),
        watchdog_hook=watchdog)
    try:
        _wait((root / "sentinel-ready.json").exists, timeout=5)
        assert _read(root / "sentinel-ready.json")["guard_active"] is True
        assert lifecycle.read_process_birth(sentinel.pid) == sentinel_birth
        result = loop.run()
        assert result.status == "stopped" and result.restart_count == 1
        assert result.last_recycle_reason == "owned_successor_progress_observed"
        assert observed["failed_exit"] == 37 and observed["duplicate_refused"]
        assert observed["first_heartbeat"] != observed["second_heartbeat"]
        first, second = observed["first"], observed["second"]
        assert first["birth"]["pid"] != second["birth"]["pid"]
        assert lifecycle.read_process_birth(first["birth"]["pid"]) is None
        assert not pid_alive(second["birth"]["pid"])
        for ready, captured in ((first, observed["first_identity"]), (second, observed["second_identity"])):
            assert captured is not None and captured.command == command
            assert captured.process_birth.pid == ready["birth"]["pid"]
            assert captured.process_birth.start_time_ticks == ready["birth"]["start_time_ticks"]
            assert ready["guard_active"] is True
            assert ready["guard_sha256"] == hashlib.sha256(CHILD_GUARD.encode()).hexdigest()
            assert ready["native_origin"] == str(Path(lifecycle.__file__).resolve())
        retired = store.load_task_attempt(canonical_task_cid="synthetic-ops06-cid", task_id="OPS06-PRIVATE", attempt=1)
        assert retired is not None and retired.is_terminal
        assert retired.fence > first["record"]["fence"]
        successor = store.load_task_attempt(canonical_task_cid="synthetic-ops06-cid", task_id="OPS06-PRIVATE", attempt=2)
        assert successor is not None and successor.owner.pid == second["birth"]["pid"]
        assert len([record for record in store.iter_records() if record.is_nonterminal]) == 1
        final = store.reclaim_dead_owner_for_controlled_restart(
            successor.workspace_path, expected_state_dir=state, reason="private_fixture_closed")
        assert final is not None and final.is_terminal
        assert not any(record.is_nonterminal for record in store.iter_records())
        assert lifecycle.read_process_birth(sentinel.pid) == sentinel_birth and sentinel.poll() is None
        assert not spec.child_pid_path.exists() and not identity.exists()
        assert _git(root, "rev-parse", "HEAD") == _git(root, "rev-parse", "main") == baseline
    finally:
        if captured_child and pid_alive(captured_child[0].pid):
            assert terminate_supervised_child(captured_child[0], grace_seconds=.2)
        (root / "sentinel-stop").touch()
        try:
            sentinel.wait(timeout=3)
        except subprocess.TimeoutExpired:
            assert lifecycle.read_process_birth(sentinel.pid) == sentinel_birth
            sentinel.terminate()
            sentinel.wait(timeout=2)


def _unit_observation():
    return {"status": "active", "healthy": True, "owned_process_alive": True, "pid": 424242,
        "provider": "grok_cli", "model": "grok-4.7", "allow_fallback": False,
        "provider_progress_verified": True, "native_state": {"active_task_id": "SYNTHETIC",
            "active_task_cid": "synthetic-cid", "active_attempt": 1, "active_task_started_at": "synthetic-time",
            "active_worktree_path": "/synthetic/work", "active_log_path": "/synthetic/log"},
        "native_heartbeat": {"updated_at": "first", "daemon_pid": 424243},
        "provider_execution_evidence": {"log_bytes": 100, "frame_counts": {"usage": 1, "tool_call": 1}},
        "events_tail": ["PRIVATE_PROMPT_SENTINEL"], "launcher_log_tail": ["OWNER_TOKEN_SENTINEL"]}


def _unit_public_api(monkeypatch):
    argv = [part for item in entry.PROFILE_FLAGS.items() for part in item]
    monkeypatch.setattr(entry.runner, "doctor", lambda *a: {"status": "ready", "native_argv": argv,
        "provider": "grok_cli", "model": "grok-4.7", "allow_fallback": False})
    monkeypatch.setattr(entry.runner, "process_identity", lambda pid: {"pid": pid, "start_ticks": 7, "boot_id": "unit", "ppid": 424242})
    for name in ("start", "stop", "recover_stalled_worker", "prepare", "run_internal"):
        monkeypatch.setattr(entry.runner, name, lambda *a, **k: pytest.fail("observation performed lifecycle action"))


def test_unit_public_observer_reports_missing_evidence_without_lifecycle_actions(tmp_path, monkeypatch):
    _unit_public_api(monkeypatch)
    monkeypatch.setattr(entry.runner, "status", lambda *a: {"status": "stopped", "healthy": False})
    result = entry.observe_live_profile(tmp_path, tmp_path / "spec", tmp_path / "state")
    assert result["status"] == "live_evidence_unavailable"
    assert result["live_acceptance_complete"] is False and result["completion_authority"] is False
    assert result["execution_started"] is False and result["failure_injected"] is False


def test_unit_observer_requires_two_distinct_current_cycles_and_redacts_tails(tmp_path, monkeypatch):
    _unit_public_api(monkeypatch)
    clock = [0]
    monkeypatch.setattr(entry.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(entry.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    def status(*_):
        value = _unit_observation()
        if clock[0] >= 5:
            value["native_heartbeat"]["updated_at"] = "second"
            value["provider_execution_evidence"].update(log_bytes=200, frame_counts={"usage": 2, "tool_call": 2})
        return value
    monkeypatch.setattr(entry.runner, "status", status)
    result = entry.observe_live_profile(tmp_path, tmp_path / "spec", tmp_path / "state", observation_seconds=10)
    assert result["status"] == "live_progress_observed" and result["observation_seconds"] >= 5
    assert len(result["observations"]) == 2 and result["live_acceptance_complete"] is False
    assert "PRIVATE_PROMPT_SENTINEL" not in json.dumps(result) and "OWNER_TOKEN_SENTINEL" not in json.dumps(result)
    assert result["completion_authority"] is False


@pytest.mark.parametrize("change", ["owner", "attempt", "stale", "post_provider"])
def test_unit_observer_refuses_changed_owner_attempt_or_stale_round(tmp_path, monkeypatch, change):
    _unit_public_api(monkeypatch)
    clock = [0]
    monkeypatch.setattr(entry.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(entry.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    def status(*_):
        value = _unit_observation()
        if clock[0]:
            if change == "owner": value["pid"] += 1
            if change == "attempt": value["native_state"]["active_attempt"] += 1
            if change == "post_provider": value["status"] = "post_provider"
        return value
    monkeypatch.setattr(entry.runner, "status", status)
    result = entry.observe_live_profile(tmp_path, tmp_path / "spec", tmp_path / "state", observation_seconds=5)
    assert result["status"] == "live_evidence_unavailable"
    assert result["completion_authority"] is False and result["live_acceptance_complete"] is False


@pytest.mark.parametrize("command", ["start", "status", "recover", "stop"])
def test_legacy_cli_commands_delegate_without_new_lifecycle_policy(monkeypatch, command):
    calls = []
    monkeypatch.setattr(entry.runner, "main", lambda argv: calls.append(argv) or 17)
    argv = [command, "--state-dir", "/synthetic/explicit-epoch"]
    assert entry.main(argv) == 17 and calls == [argv]


@pytest.mark.parametrize("state,interview", [("waiting_for_user", "awaiting_user"), ("blocked", None)])
def test_unit_observer_keeps_product_wait_separate_from_development_block(tmp_path, monkeypatch, state, interview):
    _unit_public_api(monkeypatch)
    monkeypatch.setattr(entry.runner, "status", lambda *a: {
        "status": state, "healthy": True, "application_interview_state": interview})
    result = entry.observe_live_profile(tmp_path, tmp_path / "spec", tmp_path / "state")
    assert result["status"] == "live_evidence_unavailable"
    assert result["observations"][0]["status"] == state
    assert result["observations"][0]["application_interview_state"] == interview
    assert result["resume_uses_same_epoch_start"] is True
    assert result["commands"]["start"][2] == "start" and "resume" not in result["commands"]


def test_unit_public_observation_failure_is_sanitized_and_not_live_proof(tmp_path, monkeypatch):
    _unit_public_api(monkeypatch)
    def failed(*args):
        raise OSError("PRIVATE_SOURCE_PATH_OR_SECRET_SENTINEL")
    monkeypatch.setattr(entry.runner, "status", failed)
    result = entry.observe_live_profile(tmp_path, tmp_path / "spec", tmp_path / "state")
    assert result["status"] == "live_evidence_unavailable"
    assert result["reason"] == "public_observation_unavailable"
    assert "PRIVATE_SOURCE_PATH_OR_SECRET_SENTINEL" not in json.dumps(result)
    assert result["completion_authority"] is False
