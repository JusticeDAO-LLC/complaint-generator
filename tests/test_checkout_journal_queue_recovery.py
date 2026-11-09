"""Real Native successor settlement precedes the Host's queue writer guard."""
from contextlib import contextmanager
from dataclasses import asdict
import json
import inspect
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from tests.test_improvement_recovery import _identity, _spec_text, _stamp, _forbid_dispatch
from ipfs_accelerate_py.agent_supervisor.merge import merge_queue as queues
from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import checkout_mutation_lock_path
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True, check=True).stdout.strip()


def launcher_digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _synthetic_argv(builder):
    """The temporary feature.py repository declares no dataset submodules."""
    def compile(*args, **kwargs):
        argv = builder(*args, **kwargs)
        result = []; index = 0
        while index < len(argv):
            if argv[index] == "--worktree-submodule-path":
                index += 2
            else:
                result.append(argv[index]); index += 1
        return result + ["--implementation-protected-path", "docs/task_boards/complaint_intake_task_board.md"]
    return compile


def test_actual_queue_reader_cannot_borrow_external_writer_fd(tmp_path):
    """Bound the real self-lock, rather than mocking a queue read result."""
    queue = queues.MergeQueue(tmp_path / "queue", target_repository_id="synthetic", target_branch="main")
    assert queue.completed_requests() == ()
    class BoundedSelfLock(TimeoutError):
        pass
    def expire(*_args):
        raise BoundedSelfLock("bounded actual queue writer self-lock")
    previous = signal.signal(signal.SIGALRM, expire)
    try:
        with queues.hold_merge_queue_settlement(tmp_path / "queue", target_repository_id="synthetic",
                                               target_branch="main", lock_timeout_seconds=.1):
            signal.setitimer(signal.ITIMER_REAL, .2)
            try:
                with pytest.raises(Exception, match="bounded actual queue writer self-lock"):
                    queue.completed_requests()
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
    finally:
        signal.signal(signal.SIGALRM, previous)
    assert queue.completed_requests() == ()


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    """Real bad producer, immutable queue/train, and ordinary durable retry.

    The historical identity fault and delayed old journal are explicit fixture
    faults. No accepted queue, callback, publication, or terminal claim is made
    by the test. Host process/container transports use the existing synthetic
    closed-campaign seam; all Native owner APIs and file locks remain real.
    """
    from integrations.ipfs_accelerate.improvement_plan import BOARD_RELATIVE
    from integrations.ipfs_accelerate.improvement_shutdown import _context
    root, state = tmp_path / "repo", tmp_path / "state"
    monkeypatch.setattr(runner, "native_argv", _synthetic_argv(runner.native_argv))
    queue_open = queues.open_duckdb_connection
    monkeypatch.setattr(queues.MergeQueue, "_connect", lambda self:
        queue_open(self.database_path, timeout_seconds=.15))
    root.mkdir(); state.mkdir(mode=0o700)
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Synthetic Native producer")
    git(root, "config", "user.email", "synthetic@example.invalid")
    board = root / BOARD_RELATIVE; board.parent.mkdir(parents=True)
    board.write_text("# Tasks\n\n## CIMP-OPS-03 Preserve exact completion\n\n"
        "- Status: todo\n- Completion: manual\n- Priority: P0\n- Track: ops\n"
        "- Outputs: feature.py\n- Validation: python -m py_compile feature.py\n"
        "- Acceptance: Actual local validation precedes completion.\n")
    git(root, "add", BOARD_RELATIVE); git(root, "commit", "-m", "pending synthetic task")
    baseline = git(root, "rev-parse", "HEAD")
    spec = root / runner.SPEC_RELATIVE; spec.write_text(_spec_text())
    branch = "implementation/cimp-ops-03-real-completion"
    git(root, "checkout", "-b", branch)
    (root / "feature.py").write_text("VALUE = 7\n")
    git(root, "add", "feature.py"); git(root, "commit", "-m", "meaningful implementation")
    candidate = git(root, "rev-parse", "HEAD"); git(root, "checkout", "main")
    worktrees = tmp_path / "worktrees"; worktrees.mkdir(mode=0o700)
    binding = runner._validate_worktree_root(root, state, worktrees, claim=True)
    # The shared fixture producer expects its candidate at this owned path.
    git(root, "worktree", "add", str(tmp_path / "worktrees/candidate"), branch)
    argv = [sys.executable, str(root / "scripts/run_complaint_improvement_supervisor.py"), "_run",
        "--repo-root", str(root), "--spec", str(spec), "--state-dir", str(state),
        "--owner-token", "synthetic-owner", "--merge-target", "main", "--worktree-root", str(worktrees)]
    record = {"schema_version": "complaint-improvement-launcher@1",
        "identity": {**_identity(2**30-7), "start_ticks": 1, "boot_id": "dead-owner", "argv": argv},
        "argv": argv, "owner_token": "synthetic-owner", "started_at": runner.time.time()-50,
        "status": "stopped", "repo_root": str(root), "spec_path": str(spec), "state_dir": str(state),
        "merge_target": "main", "board_path": str(board), "plan_id": runner._requested_plan_id(spec),
        "provider": "grok_cli", "model": runner.MODEL, "allow_fallback": False,
        "worktree_root": str(worktrees), "worktree_root_binding": binding}
    runner._atomic_json(state / "launcher.json", record)
    environment = runner.campaign_environment(root, state_dir=state)
    for key, value in environment.items():
        if key.startswith(("IPFS_ACCELERATE_", "TODO_DAEMON_")) or key == "COMMON_CRAWL_AUTO_CLONE_SOURCE":
            monkeypatch.setenv(key, value)
    (tmp_path / "seed.json").write_text(json.dumps(dict(baseline=baseline, branch=branch, candidate=candidate)))
    # Reuse the real Native faulty producer, with the first-party Host factory
    # and compiler paths instead of its standalone EX fixture configuration.
    driver = tmp_path / "produce.py"
    driver.write_text("import sys,json\nfrom pathlib import Path\n"
        "sys.path[:0]=" + repr(list(sys.path)) + "\n"
        "from integrations.ipfs_accelerate import improvement_runner as r\n"
        "from test.api import test_obsolete_completion_journal_settlement as f\n"
        + inspect.getsource(_synthetic_argv) +
        "r.native_argv=_synthetic_argv(r.native_argv)\n"
        "f.TASK='CIMP-OPS-03'\n"
        "def daemon_for(d):\n s=d/'state';root=d/'repo'\n"
        " record=json.loads((s/'launcher.json').read_text())\n"
        " supervisor,_=r._native_modules(root)\n"
        " return supervisor.PortalImplementationSupervisor(r._recovery_config(root,s,record))._build_worktree_reconciliation_daemon()\n"
        "f.daemon_for=daemon_for\nf._produce_bad_completion(Path(sys.argv[1]))\n")
    producer = subprocess.run([sys.executable, "-I", "-B", str(driver), str(tmp_path)],
        capture_output=True, text=True, timeout=90)
    (tmp_path / "producer-stderr.txt").write_text(producer.stderr)
    assert producer.returncode == 0, (producer.stdout[-2000:], producer.stderr[-6000:])
    supervisor, _ = runner._native_modules(root)
    daemon = supervisor.PortalImplementationSupervisor(
        runner._recovery_config(root, state, record))._build_worktree_reconciliation_daemon()
    lock = checkout_mutation_lock_path(root); old = lock.read_bytes()
    hidden = tmp_path / "retained-original-journal.json"
    lock.rename(hidden)
    try:
        progress = daemon._consume_one_merge_candidate()
    finally:
        assert not lock.exists()
        hidden.rename(lock)
    assert progress is not None
    request = daemon.merge_queue.get(progress["request_id"])
    assert request.status == "completed" and request.failure_count == 1
    assert lock.read_bytes() == old
    assert daemon._load_tasks()[0].status == "completed"
    observed = json.loads((tmp_path / "actual-producer-active-state.json").read_text())
    current = native.PortalTaskState.load(daemon.state_path)
    for field, value in observed.items():
        if field.startswith("active_") or field == "implementation_in_progress":
            setattr(current, field, value)
    current.save(daemon.state_path)
    assert not daemon.state_path.exists(), "fixture must use Native's active control-plane port"
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_strategy.json", {})
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_supervisor_status.json", {
        "status": "stopped", "repo_root": str(root), "supervisor_pid": record["identity"]["pid"],
        "updated_at": _stamp(), "managed_daemon_cleanup": {"quiesced": True}})
    runner._atomic_json(state / "container_shutdown.json", {**_context(state, record),
        "schema": "complaint-improvement-container-shutdown@1", "status": "stopped", "quiesced": True,
        "completion_authority": False, "provider_callback_settled": False, "attempt_refunded": False, "containers": []})
    monkeypatch.setattr(runner, "process_identity", lambda _pid: None)
    inventories = []
    monkeypatch.setattr(runner, "_observe_campaign_containers", lambda *a: inventories.append(True) or True)
    monkeypatch.setattr(runner, "_validate_board", lambda *a: {"count": 1, "completed": 1,
        "ready_task_ids": [], "manual_hold_task_ids": []})
    monkeypatch.chdir(ROOT)
    _forbid_dispatch(monkeypatch)
    return dict(daemon=daemon, root=root, state=state, spec=spec, record=record,
                lock=lock, journal=old, inventories=inventories)


def test_public_recovery_settles_before_real_writer_guard_then_reconciles(campaign, monkeypatch):
    w = campaign; before = asdict(native.PortalTaskState.load(w["daemon"].state_path))
    writer = queues.hold_merge_queue_settlement; held = []; phases = []
    @contextmanager
    def observe_writer(*args, **kwargs):
        with writer(*args, **kwargs) as receipt:
            held.append(True)
            try: yield receipt
            finally: held.pop()
    read = queues.MergeQueue.completed_requests
    def observe_read(self, *args, **kwargs):
        phases.append("typed_read")
        result = read(self, *args, **kwargs)
        assert not held, "typed Native read was placed under the separate Host writer FD"
        return result
    reconcile = native.PortalImplementationDaemon.reconcile_quiesced_active_attempt
    def observe_reconcile(self):
        assert held, "remaining Native recovery lost its existing queue writer snapshot"
        phases.append("guarded_reconcile")
        return reconcile(self)
    monkeypatch.setattr(queues, "hold_merge_queue_settlement", observe_writer)
    monkeypatch.setattr(queues.MergeQueue, "completed_requests", observe_read)
    monkeypatch.setattr(native.PortalImplementationDaemon, "reconcile_quiesced_active_attempt", observe_reconcile)
    result = runner.recover_stalled_worker(w["root"], w["spec"], w["state"],
        expected_launcher_sha256=launcher_digest(w["record"]))
    assert result.get("reconciled") is True, result
    assert not w["lock"].exists(), "the genuine common Native journal was left behind"
    assert phases[0] == "typed_read" and phases[-1] == "guarded_reconcile"
    assert len(w["inventories"]) >= 3
    after = asdict(native.PortalTaskState.load(w["daemon"].state_path))
    assert after["implementation_attempts"] == before["implementation_attempts"] == {"CIMP-OPS-03": 3}
    assert after["implementation_attempts_by_cid"] == before["implementation_attempts_by_cid"]
    assert after["completed_task_ids"] == before["completed_task_ids"]
    assert not after["implementation_in_progress"]
    assert not result["paid_dispatch"] and not result["selection_performed"] and not result["attempt_refunded"]
    assert result["checkout_journal_settlement"]["reason"] == "obsolete_completion_journal_settled"


@pytest.mark.parametrize("damage", ["native_payload", "board", "extra_event", "event_hash", "event_chain",
                                   "hold", "queue", "container"])
def test_settlement_cannot_refresh_unrelated_recovery_evidence(campaign, monkeypatch, damage):
    w = campaign
    settle = native.PortalImplementationDaemon.reconcile_obsolete_protected_completion_journal
    changed = []
    def change_after_genuine_settlement(self):
        result = settle(self)
        assert result.get("checkout_mutation_lease_recovered") is True, result
        changed.append(True)
        if damage == "native_payload":
            value = native.PortalTaskState.load(self.state_path)
            value.last_implementation_returncode = 81
            value.save(self.state_path)
        elif damage == "board":
            self.todo_path.write_bytes(self.todo_path.read_bytes() + b"\nUnaccepted edit.\n")
        elif damage == "extra_event":
            self._record_event("unrelated_recovery_event", {})
        elif damage in {"event_hash", "event_chain"}:
            lines = self.events_path.read_bytes().splitlines(keepends=True)
            event = json.loads(lines[-1])
            if damage == "event_hash":
                event["event_id"] = "sha256:" + "0" * 64
            else:
                from ipfs_accelerate_py.agent_supervisor.runtime.event_log import _event_identity
                event["previous_event_id"] = "sha256:" + "0" * 64
                event["event_id"] = _event_identity(event)
            self.events_path.write_bytes(b"".join(lines[:-1]) + json.dumps(event).encode() + b"\n")
        elif damage == "hold":
            (w["state"] / "watchdog").mkdir()
            (w["state"] / "watchdog/HOLD").write_text("synthetic operator hold\n")
        elif damage == "queue":
            (w["state"] / "merge-queue" / "merge_queue.duckdb").touch()
        else:
            monkeypatch.setattr(runner, "_observe_campaign_containers", lambda *a: False)
        return result
    monkeypatch.setattr(native.PortalImplementationDaemon, "reconcile_obsolete_protected_completion_journal",
                        change_after_genuine_settlement)
    monkeypatch.setattr(native.PortalImplementationDaemon, "reconcile_quiesced_active_attempt",
                        lambda self: pytest.fail("changed prephase evidence reached guarded Native mutation"))
    result = runner.recover_stalled_worker(w["root"], w["spec"], w["state"],
        expected_launcher_sha256=launcher_digest(w["record"]))
    assert changed and result.get("reconciled") is False, result
    assert not result["paid_dispatch"] and not result["attempt_refunded"] and not result["selection_performed"]


def test_queue_writer_change_at_guard_admission_refuses_before_native_mutation(campaign, monkeypatch):
    w = campaign; reads = []; changed = []
    read = queues.read_merge_queue_settlement
    guard = queues.hold_merge_queue_settlement
    def observe_read(*args, **kwargs):
        reads.append(True)
        try: return read(*args, **kwargs)
        finally: reads.pop()
    @contextmanager
    def change_before_guard(*args, **kwargs):
        # Convenience snapshots acquire this same guard. Change the actual
        # database only at the later retained guard admission boundary.
        if not reads and not changed:
            assert not w["lock"].exists(), "typed common settlement must already be complete"
            (w["state"] / "merge-queue/merge_queue.duckdb").touch()
            changed.append(True)
        with guard(*args, **kwargs) as receipt:
            yield receipt
    monkeypatch.setattr(queues, "read_merge_queue_settlement", observe_read)
    monkeypatch.setattr(queues, "hold_merge_queue_settlement", change_before_guard)
    monkeypatch.setattr(native.PortalImplementationDaemon, "reconcile_quiesced_active_attempt",
        lambda self: pytest.fail("a changed writer snapshot reached Native mutation"))
    before = asdict(native.PortalTaskState.load(w["daemon"].state_path))
    result = runner.recover_stalled_worker(w["root"], w["spec"], w["state"],
        expected_launcher_sha256=launcher_digest(w["record"]))
    assert changed and result["reason"] == "merge_queue_changed_before_reconciliation", result
    assert asdict(native.PortalTaskState.load(w["daemon"].state_path)) == before
    assert not result["paid_dispatch"] and not result["attempt_refunded"] and not result["selection_performed"]
