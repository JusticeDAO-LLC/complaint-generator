"""Watchdog and formal alignment plan contracts.

These tests read the repository and do not start a model, Mike, or an IPFS daemon.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "docs" / "task_boards" / "complaint_alignment_formal_work_plan.json"
BOARD_PATH = ROOT / "docs" / "task_boards" / "complaint_alignment_execution_board.json"
CLI_PATH = ROOT / "scripts" / "run_alignment_watchdog.py"
WATCHDOG_PATH = ROOT / "integrations" / "ipfs_accelerate" / "watchdog.py"
API_PATH = ROOT / "applications" / "complaint_workspace_api.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("run_alignment_watchdog", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _plan():
    from integrations.ipfs_accelerate.alignment_plan import build_alignment_work_plan

    return build_alignment_work_plan()


def test_formal_plan_round_trips_through_the_supervisor_contract(tmp_path: Path):
    from integrations.ipfs_accelerate.alignment_checks import CHECKERS
    from integrations.ipfs_accelerate.alignment_plan import alignment_task_ids, plan_document
    from integrations.ipfs_accelerate.watchdog import load_formal_plan

    plan = _plan()
    document = plan_document(plan)
    target = tmp_path / "plan.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    loaded = load_formal_plan(target)
    assert loaded.plan_id == plan.plan_id
    assert len(loaded.goals) == 5
    assert len(loaded.subgoals) == 10
    assert len(loaded.tasks) == 19
    assert {task.task_id for task in loaded.tasks} == set(CHECKERS)
    assert alignment_task_ids() == tuple(CHECKERS)
    goal_ids = {goal.goal_id for goal in loaded.goals}
    subgoal_ids = {subgoal.subgoal_id for subgoal in loaded.subgoals}
    assert not goal_ids & subgoal_ids
    for task in loaded.tasks:
        subgoal = next(item for item in loaded.subgoals if item.subgoal_id == task.subgoal_id)
        assert task.goal_id == subgoal.goal_id
        assert task.actor_ids == ("actor.watchdog",)


def test_committed_plan_and_board_match_the_builder():
    from integrations.ipfs_accelerate.watchdog import initial_execution_board, load_formal_plan

    plan = _plan()
    loaded = load_formal_plan(PLAN_PATH)
    assert loaded.plan_id == plan.plan_id
    assert json.loads(PLAN_PATH.read_text(encoding="utf-8"))["plan_id"] == plan.plan_id
    board = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    expected = initial_execution_board(plan)
    assert board["schema_version"] == expected["schema_version"]
    assert board["plan_id"] == plan.plan_id
    assert set(board["tasks"]) == set(expected["tasks"])
    for task_id, record in board["tasks"].items():
        assert record["status"] in {"ready", "blocked", "in_progress", "completed", "failed", "cancelled"}
        assert record["depends_on"] == expected["tasks"][task_id]["depends_on"]
        if record["status"] == "ready":
            assert all(board["tasks"][dependency]["status"] == "completed" for dependency in record["depends_on"])


def test_repair_requeues_a_stale_claim_and_clears_a_finished_dependency():
    from integrations.ipfs_accelerate.watchdog import initial_execution_board, repair_execution_board

    plan = _plan()
    state = initial_execution_board(plan)
    state["tasks"]["task.mike_protocol_versions"]["status"] = "in_progress"
    state["tasks"]["task.mike_protocol_versions"]["heartbeat_unix"] = 0
    state["tasks"]["task.mike_protocol_versions"]["claim_pid"] = 0
    state["supervisor"]["status"] = "blocked"
    state["supervisor"]["blocked_reason"] = "queue_stuck"
    state["supervisor"]["heartbeat_unix"] = 50
    receipts = repair_execution_board(state, plan, now=100, stall_seconds=30, max_attempts=3)
    kinds = {receipt["kind"] for receipt in receipts}
    assert "stall_requeued" in kinds
    assert "supervisor_repaired" in kinds
    assert state["tasks"]["task.mike_protocol_versions"]["status"] == "ready"
    assert state["supervisor"]["status"] == "idle"
    assert state["supervisor"]["blocked_reason"] == ""

    state["tasks"]["task.mike_protocol_versions"]["status"] = "completed"
    receipts = repair_execution_board(state, plan, now=100, stall_seconds=30, max_attempts=3)
    assert state["tasks"]["task.mike_connector_tools"]["status"] == "ready"
    assert any(receipt["kind"] == "dependency_cleared" for receipt in receipts)


def test_repair_blocks_a_claim_that_stalls_past_the_attempt_cap():
    from integrations.ipfs_accelerate.watchdog import initial_execution_board, repair_execution_board

    plan = _plan()
    state = initial_execution_board(plan)
    record = state["tasks"]["task.logic_adapter_paths"]
    record["status"] = "in_progress"
    record["heartbeat_unix"] = 0
    record["attempts"] = 2
    repair_execution_board(state, plan, now=10, stall_seconds=5, max_attempts=3)
    assert record["status"] == "blocked"
    assert record["blocker"] == "attempt_cap"
    assert record["attempts"] == 3


def test_repair_requeues_a_fresh_claim_whose_owner_pid_is_dead():
    from integrations.ipfs_accelerate.watchdog import initial_execution_board, repair_execution_board

    finished = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"],
        check=True,
        capture_output=True,
        text=True,
    )
    dead_pid = int(finished.stdout.strip())
    assert dead_pid != os.getpid()
    plan = _plan()
    state = initial_execution_board(plan)
    record = state["tasks"]["task.kit_gate_default_off"]
    record["status"] = "in_progress"
    record["heartbeat_unix"] = 1_000
    record["claim_pid"] = dead_pid
    state["supervisor"]["status"] = "running"
    state["supervisor"]["heartbeat_unix"] = 1_000
    state["supervisor"]["pid"] = dead_pid
    receipts = repair_execution_board(state, plan, now=1_001, stall_seconds=120, max_attempts=3)
    assert record["status"] == "ready"
    assert state["supervisor"]["status"] == "idle"
    assert any(receipt["kind"] == "stall_requeued" for receipt in receipts)
    assert any(receipt["kind"] == "supervisor_repaired" for receipt in receipts)


def test_live_claim_from_disk_does_not_start_another_task(tmp_path: Path):
    from integrations.ipfs_accelerate.watchdog import initial_execution_board, run_watchdog, save_state

    plan = _plan()
    state = initial_execution_board(plan)
    record = state["tasks"]["task.llm_router_facade"]
    record["status"] = "in_progress"
    record["heartbeat_unix"] = 500
    record["claim_pid"] = os.getpid()
    state["supervisor"]["status"] = "running"
    state["supervisor"]["heartbeat_unix"] = 500
    state["supervisor"]["pid"] = os.getpid()
    plan_path = PLAN_PATH
    state_path = tmp_path / "state.json"
    save_state(state_path, state)
    summary = run_watchdog(
        plan_path=plan_path,
        state_path=state_path,
        repo_root=ROOT,
        max_cycles=5,
        stall_seconds=120,
        now=lambda: 510,
    )
    assert summary["last_action"] == "held"
    assert summary["cycles"] == 1
    assert summary["completed"] is False
    held = json.loads(state_path.read_text(encoding="utf-8"))
    assert held["tasks"]["task.llm_router_facade"]["status"] == "in_progress"
    assert held["supervisor"]["status"] == "running"


def test_malformed_state_is_rebuilt_and_the_board_can_finish(tmp_path: Path):
    from integrations.ipfs_accelerate.watchdog import run_watchdog

    state_path = tmp_path / "state.json"
    state_path.write_text("{", encoding="utf-8")
    summary = run_watchdog(
        plan_path=PLAN_PATH,
        state_path=state_path,
        repo_root=ROOT,
        max_cycles=64,
        stall_seconds=120,
        now=lambda: 20,
    )
    assert summary["completed"] is True
    assert summary["off_request_path"] is True
    assert summary["task_counts"]["completed"] == 19
    assert any(receipt["kind"] == "state_rebuilt" for receipt in summary["repairs"])
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["plan_id"] == summary["plan_id"]
    assert all(record["status"] == "completed" for record in saved["tasks"].values())


def test_a_failed_check_does_not_stop_the_other_tasks(tmp_path: Path):
    from integrations.ipfs_accelerate.watchdog import run_watchdog

    summary = run_watchdog(
        plan_path=PLAN_PATH,
        state_path=tmp_path / "state.json",
        repo_root=ROOT,
        max_cycles=64,
        stall_seconds=120,
        now=lambda: 30,
        checkers={"task.logic_adapter_paths": lambda _root: (False, "injected failure")},
    )
    assert summary["completed"] is False
    assert summary["task_counts"]["failed"] == 1
    assert summary["task_counts"]["completed"] == 18
    saved = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert saved["tasks"]["task.logic_adapter_paths"]["status"] == "failed"
    assert saved["tasks"]["task.logic_adapter_paths"]["blocker"] == "check_failed"


def test_cli_completes_the_board_without_a_control_plane_request(tmp_path: Path, capsys):
    cli_text = CLI_PATH.read_text(encoding="utf-8")
    watchdog_text = WATCHDOG_PATH.read_text(encoding="utf-8")
    api_text = API_PATH.read_text(encoding="utf-8")
    for text in (cli_text, watchdog_text):
        assert "SupervisorControlService" not in text
        assert "OperationRequest" not in text
        assert "complaint_workspace_api" not in text
    assert "run_alignment_watchdog" not in api_text
    cli = _load_cli()
    code = cli.main(
        [
            "--plan",
            str(PLAN_PATH),
            "--state",
            str(tmp_path / "cli-state.json"),
            "--max-cycles",
            "64",
        ]
    )
    captured = json.loads(capsys.readouterr().out)
    assert code == 0
    assert captured["completed"] is True
    assert captured["off_request_path"] is True
    assert captured["task_counts"]["completed"] == 19
    assert captured["supervisor_status"] == "idle"


def test_monitor_waits_for_a_live_claim_then_recovers_its_stall(tmp_path: Path):
    from integrations.ipfs_accelerate.watchdog import initial_execution_board, run_watchdog, save_state

    plan = _plan()
    state = initial_execution_board(plan)
    record = state["tasks"]["task.llm_router_facade"]
    record.update(status="in_progress", heartbeat_unix=100, claim_pid=os.getpid())
    state["supervisor"].update(status="running", heartbeat_unix=100, pid=os.getpid())
    target = tmp_path / "state.json"
    save_state(target, state)
    clock = [101]
    waits = []

    def advance(seconds):
        waits.append(seconds)
        clock[0] += 10

    summary = run_watchdog(
        plan_path=PLAN_PATH, state_path=target, repo_root=ROOT,
        monitor=True, stall_seconds=5, now=lambda: clock[0], sleep=advance,
    )
    assert waits == [5]
    assert summary["completed"] is True
    assert any(item["kind"] == "stall_requeued" for item in summary["repairs"])


def test_transient_check_failure_is_retried_without_starving_dependents(tmp_path: Path):
    from integrations.ipfs_accelerate.watchdog import run_watchdog

    attempts = tmp_path / "attempts"

    def transient(_root):
        count = int(attempts.read_text()) if attempts.exists() else 0
        attempts.write_text(str(count + 1))
        return count > 0, "transient failure" if not count else "recovered"

    summary = run_watchdog(
        plan_path=PLAN_PATH, state_path=tmp_path / "state.json", repo_root=ROOT,
        checkers={"task.mike_protocol_versions": transient},
    )
    assert summary["completed"] is True
    assert attempts.read_text() == "2"
    assert any(item["kind"] == "check_retried" for item in summary["repairs"])


def test_hanging_checker_times_out_and_other_tasks_continue(tmp_path: Path):
    import time
    from integrations.ipfs_accelerate.watchdog import run_watchdog

    def hanging(_root):
        time.sleep(60)
        raise AssertionError("the child should have been terminated")

    summary = run_watchdog(
        plan_path=PLAN_PATH, state_path=tmp_path / "state.json", repo_root=ROOT,
        checker_timeout_seconds=0.05, max_attempts=2,
        checkers={"task.logic_adapter_paths": hanging},
    )
    assert summary["completed"] is False
    assert summary["task_counts"]["completed"] == 18
    pending = summary["pending_tasks"]["task.logic_adapter_paths"]
    assert "timed out" in pending["last_receipt"]["detail"]
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["tasks"]["task.logic_adapter_paths"]["attempts"] == 2


def test_duplicate_monitor_holds_without_rewriting_the_board(tmp_path: Path):
    from integrations.ipfs_accelerate.watchdog import _state_lock, initial_execution_board, run_watchdog, save_state

    target = tmp_path / "state.json"
    save_state(target, initial_execution_board(_plan()))
    original = target.read_bytes()
    with _state_lock(target) as owned:
        assert owned
        summary = run_watchdog(plan_path=PLAN_PATH, state_path=target, repo_root=ROOT)
    assert summary["last_action"] == "held"
    assert summary["cycles"] == 0
    assert target.read_bytes() == original


def test_changed_plan_does_not_keep_completed_receipts(tmp_path: Path):
    from integrations.ipfs_accelerate.watchdog import initial_execution_board, load_or_create_state, save_state

    plan = _plan()
    state = initial_execution_board(plan)
    state["plan_id"] = "different-plan"
    for record in state["tasks"].values():
        record["status"] = "completed"
    target = tmp_path / "state.json"
    save_state(target, state)
    loaded, repairs = load_or_create_state(target, plan)
    assert all(record["status"] != "completed" for record in loaded["tasks"].values())
    assert repairs == [{"kind": "state_rebuilt", "reason": "plan_changed"}]


def test_source_changes_invalidate_success_and_exhausted_failure(tmp_path: Path):
    from integrations.ipfs_accelerate.alignment_checks import CHECKERS
    from integrations.ipfs_accelerate.watchdog import run_watchdog

    source = tmp_path / "applications" / "source.py"
    source.parent.mkdir()
    source.write_text("broken")
    target = tmp_path / "state.json"
    checkers = {key: lambda _root: (True, "verified") for key in CHECKERS}
    checkers["task.mike_protocol_versions"] = lambda _root: (source.read_text() == "fixed", "behavior")
    first = run_watchdog(plan_path=PLAN_PATH, state_path=target, repo_root=tmp_path,
                         checkers=checkers, max_attempts=1)
    assert first["completed"] is False
    source.write_text("fixed")
    second = run_watchdog(plan_path=PLAN_PATH, state_path=target, repo_root=tmp_path,
                          checkers=checkers, max_attempts=1)
    assert second["completed"] is True
    source.write_text("broken again")
    third = run_watchdog(plan_path=PLAN_PATH, state_path=target, repo_root=tmp_path,
                         checkers=checkers, max_attempts=1)
    assert third["completed"] is False


def test_watchdog_preserves_an_explicit_operator_pause(tmp_path: Path):
    from integrations.ipfs_accelerate.watchdog import initial_execution_board, run_watchdog, save_state

    state = initial_execution_board(_plan())
    state["supervisor"].update(status="paused", blocked_reason="operator maintenance")
    target = tmp_path / "state.json"
    save_state(target, state)
    summary = run_watchdog(plan_path=PLAN_PATH, state_path=target, repo_root=ROOT)
    assert summary["last_action"] == "held"
    assert summary["task_counts"]["completed"] == 0
    assert summary["supervisor_status"] == "paused"


def test_monitor_reloads_an_operator_resume_during_a_wait(tmp_path: Path):
    from integrations.ipfs_accelerate.watchdog import initial_execution_board, run_watchdog, save_state

    state = initial_execution_board(_plan())
    state["supervisor"].update(status="paused", blocked_reason="maintenance")
    target = tmp_path / "state.json"
    save_state(target, state)
    waits = []

    def resume(seconds):
        waits.append(seconds)
        current = json.loads(target.read_text())
        current["supervisor"].update(status="idle", blocked_reason="")
        save_state(target, current)

    summary = run_watchdog(plan_path=PLAN_PATH, state_path=target, repo_root=ROOT,
                           monitor=True, sleep=resume)
    assert summary["completed"] is True
    assert waits == [5]


def test_input_revalidation_preserves_manual_task_blocks_and_cancellation(tmp_path: Path):
    from integrations.ipfs_accelerate.watchdog import initial_execution_board, run_watchdog, save_state

    state = initial_execution_board(_plan())
    state["tasks"]["task.logic_adapter_paths"].update(status="blocked", blocker="operator_approval")
    state["tasks"]["task.multimedia_attachment_adapter"]["status"] = "cancelled"
    target = tmp_path / "state.json"
    save_state(target, state)
    summary = run_watchdog(plan_path=PLAN_PATH, state_path=target, repo_root=ROOT)
    assert summary["completed"] is False
    assert summary["pending_tasks"]["task.logic_adapter_paths"]["blocker"] == "operator_approval"
    assert summary["pending_tasks"]["task.multimedia_attachment_adapter"]["status"] == "cancelled"


def test_stale_active_claim_cannot_complete_with_old_source_receipts(tmp_path: Path):
    from integrations.ipfs_accelerate.watchdog import initial_execution_board, run_watchdog, save_state

    state = initial_execution_board(_plan())
    state["source_fingerprint"] = "old-source"
    for record in state["tasks"].values():
        record["status"] = "completed"
    state["tasks"]["task.logic_adapter_paths"].update(status="in_progress", heartbeat_unix=0)
    target = tmp_path / "state.json"
    save_state(target, state)
    summary = run_watchdog(plan_path=PLAN_PATH, state_path=target, repo_root=ROOT, max_cycles=1)
    assert summary["completed"] is False
    assert summary["source_current"] is False
    summary = run_watchdog(plan_path=PLAN_PATH, state_path=target, repo_root=ROOT)
    assert summary["completed"] is True
    assert summary["source_current"] is True
    saved = json.loads(target.read_text())
    assert all(record["receipts"] for record in saved["tasks"].values())


def test_retry_repairs_a_null_receipt_list(tmp_path: Path):
    from integrations.ipfs_accelerate.watchdog import (
        _source_fingerprint, initial_execution_board, run_watchdog, save_state,
    )

    state = initial_execution_board(_plan())
    state["source_fingerprint"] = _source_fingerprint(ROOT)
    state["tasks"]["task.logic_adapter_paths"].update(
        status="failed", blocker="check_failed", receipts=None,
    )
    target = tmp_path / "state.json"
    save_state(target, state)
    summary = run_watchdog(plan_path=PLAN_PATH, state_path=target, repo_root=ROOT)
    assert summary["completed"] is True
