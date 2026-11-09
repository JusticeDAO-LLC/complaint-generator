"""A fresh epoch preserves native quarantines and consumed retry accounting."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path

import pytest

from integrations.ipfs_accelerate import improvement_recovery as recovery
from integrations.ipfs_accelerate import improvement_runner as runner


ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture
def held(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    _supervisor, native = runner._native_modules(ROOT)
    from integrations.ipfs_accelerate.improvement_plan import BOARD_RELATIVE, generate
    from ipfs_accelerate_py.agent_supervisor.merge import worktree_lifecycle as lifecycle
    from ipfs_accelerate_py.agent_supervisor.runtime import provider_capacity_custody as capacity
    from ipfs_accelerate_py.agent_supervisor.proof.formal_verification_contracts import content_identity

    root = tmp_path / "repository"
    root.mkdir()
    spec = root / runner.SPEC_RELATIVE
    spec.parent.mkdir(parents=True)
    spec.write_text(json.dumps({
        "schema_version": "complaint-intake-improvement@1", "title": "Synthetic recovery",
        "provider": {"router": "ipfs_accelerate_py.llm_router", "provider": "grok_cli", "model": "grok-4.7", "allow_fallback": False},
        "execution_policy": {"synthetic_only": True},
        "goals": [{"id": "goal.tui", "title": "TUI", "subgoals": [{"id": "sub.tui", "title": "Interview"}]}],
        "tasks": [{"id": "CIMP-TUI-01", "title": "Characterize terminal", "goal_id": "goal.tui", "subgoal_id": "sub.tui",
                   "priority": "P0", "targets": ["tests/test_terminal.py"], "depends_on": [],
                   "acceptance": ["Synthetic PTY works"], "validation_commands": ["python -m pytest tests/test_terminal.py"],
                   "implementation_prompt": "Use a bounded synthetic terminal scenario."}],
    }))
    generate(spec, root)
    task = native.parse_task_file(root / BOARD_RELATIVE, runner.TASK_PREFIX)[0]
    base = tmp_path / "campaign"
    base.mkdir(mode=0o700)
    workspace = base / "worktrees/old-candidate"
    workspace.mkdir(parents=True)
    (workspace / "candidate.txt").write_text("retained, never reused")
    log = base / "attempt.log"
    log.write_text("\n".join([
        json.dumps({"type": "usage", "opaque": "XAI402"}),
        json.dumps({"type": "max_turns_reached"}),
        json.dumps({"type": "end", "stopReason": "max_turn_requests", "num_turns": 32}),
        "Error: max turns reached", "",
    ]))
    log.chmod(0o600)
    state_path = base / f"{runner.STATE_PREFIX}_task_state.json"
    with recovery._native_environment(base):
        native.PortalTaskState(implementation_attempts={task.task_id: 2},
            implementation_attempts_by_cid={task.canonical_task_cid: 2}).save(state_path)
    plan_id = recovery._plan_id(root, spec)
    runner._atomic_json(base / "launcher.json", {"repo_root": str(root), "plan_id": plan_id,
                        "status": "stopped", "identity": {}})
    runner._atomic_json(base / f"{runner.STATE_PREFIX}_supervisor_status.json",
                        {"status": "stopped", "managed_daemon_cleanup": {"quiesced": True}})
    (base / f"{runner.STATE_PREFIX}_supervisor_status.json").chmod(0o664)
    registry = tmp_path / "registry"
    monkeypatch.setattr(lifecycle, "lifecycle_store_dir", lambda _root: registry)
    store = lifecycle.WorktreeLifecycleStore(repo_root=root)
    captured = store.begin_preparing(task_id=task.task_id, canonical_task_cid=task.canonical_task_cid,
        attempt=2, lane_id="synthetic", workspace_path=workspace, branch="synthetic-attempt-2",
        merge_target="synthetic-main", state_dir=str(base))
    body = {"schema": capacity.SCHEMA, "state_path": str(state_path), "task_id": task.task_id,
            "canonical_task_cid": task.canonical_task_cid, "attempt": 2,
            "attempt_consumed": True, "returncode": 1, "worktree_path": str(workspace),
            "log_path": str(log), "log_identity": capacity.log_identity(log),
            "retry_authorized": False, "settlement_authority": False, "completion_authority": False,
            "cleanup_allowed": False, "callback_outcome": "unknown"}
    hold = {**body, "receipt_id": content_identity(body)}
    store.quarantine_current_owner(captured, fence_authority=hold, reason=capacity.REASON)
    quarantine = store.quarantine_path_for(workspace)

    def actual_native_read(_root, path, **_kwargs):
        with recovery._native_environment(path.parent):
            return asdict(native.PortalTaskState.load(path)), {"source": "native_control_plane"}

    monkeypatch.setattr(runner, "_read_native_state", actual_native_read)
    monkeypatch.setattr(recovery, "_assert_processes_absent", lambda *_args: {"matching_processes": 0})
    monkeypatch.setattr(recovery, "_assert_containers_absent", lambda *_args: {"matching_workspace_containers": 0})
    return {"root": root, "spec": spec, "base": base, "workspace": workspace, "log": log,
            "quarantine": quarantine, "native": native, "task": task, "store": store}


def _prepare(held):
    return recovery.prepare_false_capacity_epoch(held["root"], held["spec"], held["quarantine"],
                                                  "capacity-fix", base_state_dir=held["base"])


def test_real_native_state_seed_preserves_spent_count_and_old_evidence(held):
    paths = [held["quarantine"], held["log"], held["workspace"] / "candidate.txt"]
    before = {p: p.read_bytes() for p in paths}
    receipt = _prepare(held)
    target = held["base"] / "epochs/capacity-fix"
    assert recovery.resolve_active_epoch(held["root"], held["spec"], held["base"]) == target
    assert receipt["spent_attempts"] == 2 and receipt["next_attempt"] == 3
    assert not receipt["completion_authority"] and not receipt["old_quarantine_released"]
    assert not receipt["attempt_refunded"] and not receipt["evidence_reuse_authority"]
    assert receipt["old_callback_outcome"] == "unknown"
    assert {p: p.read_bytes() for p in paths} == before
    assert not (target / "worktrees").exists()
    with recovery._native_environment(target):
        seeded = held["native"].PortalTaskState.load(target / f"{runner.STATE_PREFIX}_task_state.json")
    assert seeded.implementation_attempts == {held["task"].task_id: 2}
    assert seeded.implementation_attempts_by_cid == {held["task"].canonical_task_cid: 2}
    assert seeded.completed_task_ids == [] and seeded.active_task_id == ""
    scheduler = object.__new__(held["native"].PortalImplementationDaemon)
    scheduler._canonical_ref = lambda _task: held["task"].canonical_task_cid
    scheduler._durable_protected_recovery_attempt = lambda *_args: None
    scheduler._scoped_recovery_attempts = {}
    assert scheduler._task_attempt_count(seeded, held["task"]) == 2
    assert scheduler._task_attempt(seeded, held["task"]) == 3
    with pytest.raises(ValueError, match="already exists"):
        _prepare(held)


def test_changed_log_cannot_publish_recovery(held):
    held["log"].write_text(held["log"].read_text() + "changed\n")
    with pytest.raises(ValueError, match="log identity"):
        _prepare(held)
    assert not (held["base"] / "active_epoch.json").exists()


@pytest.mark.parametrize("terminal", [
    '{"type":"error","message":"grok quota exceeded"}\n',
    '{"type":"max_turns_reached"}\n',
    '{"type":"end","stopReason":"completed","num_turns":32}\n',
])
def test_nonquota_terminal_guard_rejects_quota_or_incomplete_evidence(held, terminal):
    with pytest.raises(ValueError):
        recovery._nonquota_terminal(held["native"], terminal.encode())


@pytest.mark.parametrize("guard", ["_assert_processes_absent", "_assert_containers_absent"])
def test_live_or_unavailable_execution_cannot_publish_epoch(held, monkeypatch, guard):
    def reject(*_args):
        raise ValueError("execution not absent")
    monkeypatch.setattr(recovery, guard, reject)
    with pytest.raises(ValueError, match="execution not absent"):
        _prepare(held)
    assert not (held["base"] / "active_epoch.json").exists()


@pytest.mark.parametrize("epoch", ["../escape", "/absolute", "epochs/other", "", "a.b", "a" * 65])
def test_unbounded_epoch_paths_are_rejected(held, epoch):
    with pytest.raises(ValueError):
        recovery.prepare_false_capacity_epoch(held["root"], held["spec"], held["quarantine"],
                                               epoch, base_state_dir=held["base"])


def test_active_pointer_plan_and_receipt_changes_fail_closed(held):
    _prepare(held)
    pointer = held["base"] / "active_epoch.json"
    payload = json.loads(pointer.read_text())
    payload["plan_id"] = "another-plan"
    runner._atomic_json(pointer, payload)
    with pytest.raises(ValueError, match="plan binding"):
        recovery.resolve_active_epoch(held["root"], held["spec"], held["base"])


def test_actual_live_owner_is_not_absence(monkeypatch, tmp_path):
    identity = runner.process_identity(os.getpid())
    # Restore the actual check rather than the synthetic proof boundary above.
    with pytest.raises(ValueError, match="still alive"):
        recovery._assert_processes_absent(tmp_path, tmp_path / "workspace",
            {"identity": identity}, {}, {"status": "stopped"})


def test_parent_shell_source_text_is_not_a_campaign_process():
    assert not recovery._campaign_process_argv(["bash", "-lc",
        "from integrations.ipfs_accelerate import improvement_runner; old='/old/state'"])
    assert recovery._campaign_process_argv(["python", "-m",
        "ipfs_accelerate_py.agent_supervisor.runtime.grok_cli_runner", "--workspace", "/old/workspace"])
