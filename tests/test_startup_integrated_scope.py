"""An already merged out-of-scope candidate is retained and does not stop startup."""
from dataclasses import asdict
from copy import deepcopy
import json
import os

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import improvement_plan as compiler
from integrations.ipfs_accelerate.startup_integrated_scope import (
    retained_empty_integrated_baseline, retained_integrated_scope_refusal)
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as impl
from tests.test_startup_retained_replay_rejection import _git

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture(scope="module")
def scope_world(tmp_path_factory):
    base = tmp_path_factory.mktemp("integrated-scope-refusal")
    root, state, trees = (base / name for name in ("repo", "state", "worktrees"))
    for path in (root, state, trees):
        path.mkdir(mode=0o700)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "Synthetic scope fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    tasks = [{"id": f"CIMP-SYN-{n:02}", "goal_id": "goal.synthetic", "subgoal_id": "sub.synthetic",
        "title": "Out of scope retained candidate" if n == 1 else "Independent task",
        "priority": "P1" if n == 1 else "P0",
        "targets": [f"out/task{n}.py", f"tests/test_task{n}.py"], "depends_on": [],
        "acceptance": ["Synthetic local boundary only."],
        "validation_commands": [f"python -m pytest -q tests/test_task{n}.py"],
        "implementation_prompt": "Synthetic fixture; no model call."} for n in (1, 2)]
    spec = {"schema_version": "complaint-generator/improvement-spec@1", "title": "Synthetic startup boundary",
        "provider": {"router": "ipfs_accelerate_py.llm_router", "provider": "grok_cli", "model": "grok-4.7",
                     "allow_fallback": False},
        "goals": [{"id": "goal.synthetic", "title": "Synthetic",
                   "subgoals": [{"id": "sub.synthetic", "title": "Synthetic"}]}],
        "tasks": tasks, "execution_policy": {"synthetic_only": True}, "findings": []}
    source = root / runner.SPEC_RELATIVE
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(spec))
    compiler.generate(source, root)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "Synthetic task source")
    baseline = _git(root, "rev-parse", "HEAD")
    config = native.PortalSupervisorConfig(
        todo_path=root / compiler.BOARD_RELATIVE, state_path=state / "state.json",
        strategy_path=state / "strategy.json", events_path=state / "supervisor.jsonl",
        state_dir=state, repo_root=root, state_prefix="synthetic", task_prefix="## CIMP-",
        worktree_root=trees, merge_target_branch="main", merge_queue_dir=state / "merge-queue",
        implementation_protected_paths=(compiler.BOARD_RELATIVE,), worktree_scan_cache_enabled=False,
        worktree_reconciliation_max_merges=1, implementation_timeout=30, max_task_attempts=3,
        llm_merge_resolver_command="")
    supervisor = runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor)(config)
    impl.PortalTaskState().save(config.state_path)
    branch, leaf = "implementation/cimp-syn-01-scope-attempt-1", trees / "workspace_scope"
    _git(root, "worktree", "add", "-q", "-b", branch, str(leaf), baseline)
    board = leaf / compiler.BOARD_RELATIVE
    board.write_text(board.read_text() + "\n<!-- synthetic scope marker -->\n")
    _git(leaf, "add", compiler.BOARD_RELATIVE)
    _git(leaf, "commit", "-qm", "Synthetic board-only candidate")
    _git(root, "merge", "--ff-only", branch)
    supervisor._complaint_startup_preflight_pending = True
    supervisor._complaint_startup_reconciliation_context = None
    result = native.PortalImplementationSupervisor.run_once(supervisor, include_refill=False)
    item = result["worktree_reconciliation"]["processed"][0]
    assert item["merge_result"]["reason"] == "integrated_candidate_delta_outside_task_scope"
    assert item["merge_result"]["attempt_consumed"] is False
    assert _git(root, "merge-base", "--is-ancestor", item["head"], "main") == ""
    return dict(root=root, state=state, trees=trees, leaf=leaf, branch=branch, baseline=baseline,
                supervisor=supervisor, result=result, item=item)


def test_retained_scope_refusal_allows_startup_without_budget_or_completion_changes(scope_world):
    world = scope_world
    supervisor = world["supervisor"]
    before = asdict(impl.PortalTaskState.load(supervisor.config.state_path))
    refs = _git(world["root"], "show-ref")
    assert retained_integrated_scope_refusal(
        supervisor, world["item"], maintenance_result=world["result"])
    supervisor._complaint_startup_preflight_pending = True
    observed = supervisor.run_once(include_refill=False)
    assert supervisor._complaint_startup_preflight_pending is False
    assert observed["worktree_reconciliation"]["processed"][0]["merge_result"]["reason"] == (
        "integrated_candidate_delta_outside_task_scope")
    assert observed["worktree_reconciliation"]["processed"][0]["merge_result"]["attempt_consumed"] is False
    assert refs == _git(world["root"], "show-ref")
    assert world["leaf"].is_dir()
    assert asdict(impl.PortalTaskState.load(supervisor.config.state_path)) == before


@pytest.mark.parametrize("damage", ["reason", "consumed", "blocked", "ancestor", "dirty", "hold"])
def test_unproved_scope_refusal_remains_blocking(scope_world, damage):
    world = scope_world
    supervisor = world["supervisor"]
    item, result = deepcopy(world["item"]), deepcopy(world["result"])
    cleanup = []
    try:
        if damage == "reason":
            item["merge_result"]["reason"] = "validation_failed"
        elif damage == "consumed":
            item["merge_result"]["attempt_consumed"] = True
        elif damage == "blocked":
            result["maintenance_blocked"] = True
        elif damage == "ancestor":
            supervisor.config.merge_target_branch = world["baseline"]
            cleanup.append(lambda: setattr(supervisor.config, "merge_target_branch", "main"))
        elif damage == "dirty":
            extra = world["leaf"] / "out" / "unreviewed.py"
            extra.parent.mkdir(exist_ok=True)
            extra.write_text("VALUE = 'unreviewed'\n")
            cleanup.append(extra.unlink)
        else:
            hold = world["state"] / "watchdog" / "HOLD"
            hold.parent.mkdir(mode=0o700, exist_ok=True)
            hold.write_text("{}\n")
            cleanup.append(hold.unlink)
        assert retained_integrated_scope_refusal(supervisor, item, maintenance_result=result) is False
    finally:
        for action in cleanup:
            action()
        os.chmod(world["state"], 0o700)


def test_empty_integrated_baseline_allows_startup_without_budget_or_completion_changes(tmp_path):
    root, state, trees = (tmp_path / name for name in ("repo", "state", "worktrees"))
    for path in (root, state, trees):
        path.mkdir(mode=0o700)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "Synthetic empty baseline")
    _git(root, "config", "user.email", "fixture@example.invalid")
    tasks = [{"id": f"CIMP-SYN-{n:02}", "goal_id": "goal.synthetic", "subgoal_id": "sub.synthetic",
        "title": "Empty baseline candidate" if n == 1 else "Independent task",
        "priority": "P1" if n == 1 else "P0",
        "targets": [f"out/task{n}.py", f"tests/test_task{n}.py"], "depends_on": [],
        "acceptance": ["Synthetic local boundary only."],
        "validation_commands": [f"python -m pytest -q tests/test_task{n}.py"],
        "implementation_prompt": "Synthetic fixture; no model call."} for n in (1, 2)]
    spec = {"schema_version": "complaint-generator/improvement-spec@1", "title": "Synthetic startup boundary",
        "provider": {"router": "ipfs_accelerate_py.llm_router", "provider": "grok_cli", "model": "grok-4.7",
                     "allow_fallback": False},
        "goals": [{"id": "goal.synthetic", "title": "Synthetic",
                   "subgoals": [{"id": "sub.synthetic", "title": "Synthetic"}]}],
        "tasks": tasks, "execution_policy": {"synthetic_only": True}, "findings": []}
    source = root / runner.SPEC_RELATIVE
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(spec))
    compiler.generate(source, root)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "Synthetic task source")
    baseline = _git(root, "rev-parse", "HEAD")
    config = native.PortalSupervisorConfig(
        todo_path=root / compiler.BOARD_RELATIVE, state_path=state / "state.json",
        strategy_path=state / "strategy.json", events_path=state / "supervisor.jsonl",
        state_dir=state, repo_root=root, state_prefix="synthetic", task_prefix="## CIMP-",
        worktree_root=trees, merge_target_branch="main", merge_queue_dir=state / "merge-queue",
        implementation_protected_paths=(compiler.BOARD_RELATIVE,), worktree_scan_cache_enabled=False,
        worktree_reconciliation_max_merges=1, implementation_timeout=30, max_task_attempts=3,
        llm_merge_resolver_command="")
    supervisor = runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor)(config)
    impl.PortalTaskState().save(config.state_path)
    daemon = native.PortalImplementationSupervisor._build_worktree_reconciliation_daemon(supervisor)
    current = daemon._load_tasks()
    daemon._register_task_identities(current)
    branch, leaf = "implementation/cimp-syn-01-empty-attempt-1", trees / "workspace_empty"
    _git(root, "worktree", "add", "-q", "-b", branch, str(leaf), baseline)
    leaf = leaf.resolve()
    daemon._record_event("implementation_started", {
        "task_id": "CIMP-SYN-01", "attempt": 1, "branch": branch,
        "worktree_path": str(leaf), "baseline_ref": baseline,
    })
    supervisor._complaint_startup_preflight_pending = True
    supervisor._complaint_startup_reconciliation_context = None
    probed = native.PortalImplementationSupervisor.run_once(supervisor, include_refill=False)
    item = next(row for row in probed["worktree_reconciliation"]["processed"] if row["branch"] == branch)
    assert item["merge_result"]["reason"] == "integrated_candidate_baseline_unproved"
    assert item["merge_result"]["attempt_consumed"] is False
    assert item["head"] == baseline
    assert retained_empty_integrated_baseline(supervisor, item, maintenance_result=probed)
    damaged = deepcopy(item)
    damaged["head"] = "a" * 40
    assert retained_empty_integrated_baseline(supervisor, damaged, maintenance_result=probed) is False
    before = asdict(impl.PortalTaskState.load(supervisor.config.state_path))
    refs = _git(root, "show-ref")
    supervisor._complaint_startup_preflight_pending = True
    observed = supervisor.run_once(include_refill=False)
    assert supervisor._complaint_startup_preflight_pending is False
    assert observed["worktree_reconciliation"]["processed"][0]["merge_result"]["reason"] == (
        "integrated_candidate_baseline_unproved")
    assert observed["worktree_reconciliation"]["processed"][0]["merge_result"]["attempt_consumed"] is False
    assert refs == _git(root, "show-ref")
    assert leaf.is_dir()
    assert asdict(impl.PortalTaskState.load(supervisor.config.state_path)) == before
