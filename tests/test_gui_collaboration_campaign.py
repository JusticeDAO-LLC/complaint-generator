"""The reviewed GUI program is a separate, unexecuted Native campaign."""

from graphlib import TopologicalSorter
import inspect
import json
from pathlib import Path

import pytest

from integrations.ipfs_accelerate import improvement_plan as compiler
from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate.campaign import campaign_artifacts


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = {
    "spec_relative": "docs/task_boards/complaint_gui_collaboration_spec.json",
    "plan_relative": "docs/task_boards/complaint_gui_collaboration_formal_work_plan.json",
    "board_relative": "docs/task_boards/complaint_gui_collaboration_task_board.md",
    "board_namespace": "complaint-gui-collaboration",
}
PREVIOUS_ARTIFACTS = (
    compiler.SPEC_RELATIVE,
    compiler.PLAN_RELATIVE,
    compiler.BOARD_RELATIVE,
    "docs/task_boards/complaint_mediator_grounding_spec.json",
    "docs/task_boards/complaint_mediator_grounding_formal_work_plan.json",
    "docs/task_boards/complaint_mediator_grounding_task_board.md",
)
EXPECTED_TASK_IDS = {f"CIMP-GUI-{number:02d}" for number in range(1, 61)}


@pytest.fixture
def gui_spec():
    return compiler.load_spec(ROOT / CAMPAIGN["spec_relative"])


@pytest.fixture
def generated_campaign(tmp_path, gui_spec):
    """Compile only synthetic copies, retaining both completed programs verbatim."""
    previous = {relative: (ROOT / relative).read_bytes() for relative in PREVIOUS_ARTIFACTS}
    for relative, raw in previous.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    source = tmp_path / CAMPAIGN["spec_relative"]
    source.write_bytes((ROOT / CAMPAIGN["spec_relative"]).read_bytes())
    generated = compiler.generate(source, tmp_path)
    yield tmp_path, source, generated
    for relative, raw in previous.items():
        assert (tmp_path / relative).read_bytes() == raw
        assert (ROOT / relative).read_bytes() == raw


def _native_tasks(board):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import parse_task_file

    return parse_task_file(board, task_header_prefix=runner.TASK_PREFIX)


def _ancestors(tasks, task_id):
    pending = list(tasks[task_id]["depends_on"])
    found = set()
    while pending:
        dependency = pending.pop()
        if dependency not in found:
            found.add(dependency)
            pending.extend(tasks[dependency]["depends_on"])
    return found


def test_gui_plan_roundtrips_real_native_contracts_without_completion_events(gui_spec, generated_campaign):
    root, _, generated = generated_campaign
    plan = compiler.build_improvement_work_plan(gui_spec)
    from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import FormalWorkPlan

    assert Path(inspect.getfile(FormalWorkPlan)).resolve() == (
        ROOT / "external/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/planning/formal_planning_contracts.py"
    ).resolve()
    restored = FormalWorkPlan.from_dict(json.loads(Path(generated["plan_path"]).read_bytes()))
    assert isinstance(plan, FormalWorkPlan)
    assert restored.to_dict() == plan.to_dict()
    assert restored.plan_id == plan.plan_id
    assert (len(plan.tasks), len(plan.goals), len(plan.subgoals)) == (60, 14, 31)
    assert plan.source_ids == ("complaint-generator", CAMPAIGN["spec_relative"])
    assert all(goal.source_ids == (CAMPAIGN["spec_relative"],) for goal in plan.goals)
    assert {task.task_id for task in plan.tasks} == EXPECTED_TASK_IDS
    assert {requirement.requirement_id for requirement in plan.evidence_requirements} == {
        "test." + task_id for task_id in EXPECTED_TASK_IDS
    }
    assert {requirement_id for goal in plan.goals for requirement_id in goal.evidence_requirement_ids} == {
        requirement.requirement_id for requirement in plan.evidence_requirements
    }
    assert {requirement_id for subgoal in plan.subgoals for requirement_id in subgoal.evidence_requirement_ids} == {
        requirement.requirement_id for requirement in plan.evidence_requirements
    }
    assert plan.events == () and restored.events == ()
    receipt = generated["receipt"]
    assert receipt["native_roundtrip"] is True
    assert receipt["native_contract_ingested"] is True
    assert receipt["execution_started"] is False
    assert receipt["tasks_completed_by_ingestion"] == 0
    assert receipt["validations_executed"] == []
    assert generated["plan_path"] == str(root / CAMPAIGN["plan_relative"])
    assert generated["board_path"] == str(root / CAMPAIGN["board_relative"])


def test_native_projection_ingests_all_gui_tasks_and_only_baseline_is_ready(gui_spec, generated_campaign):
    root, _, generated = generated_campaign
    tasks = _native_tasks(Path(generated["board_path"]))
    expected = {task["id"]: task for task in gui_spec["tasks"]}
    assert len(tasks) == 60
    assert {task.task_id for task in tasks} == EXPECTED_TASK_IDS
    assert len({task.canonical_task_cid for task in tasks}) == 60
    assert len({task.canonical_task_key for task in tasks}) == 60
    assert all(task.canonical_task_cid and task.canonical_task_key for task in tasks)
    for task in tasks:
        declared = expected[task.task_id]
        assert task.status == "todo" and task.completion == "validation"
        assert task.depends_on == declared["depends_on"]
        assert task.outputs == declared["targets"]
        assert task.validation == declared["validation_commands"]
        assert task.metadata["provider role"] == "grok-only"
        assert task.metadata["model"] == "grok-4.7"
        assert task.metadata["provider fallback"] == "disabled"
        assert not set(task.outputs) & set(PREVIOUS_ARTIFACTS)
    summary = runner._board_summary(tasks)
    assert summary["count"] == 60 and summary["completed"] == 0
    assert summary["ready_task_ids"] == ["CIMP-GUI-01"]
    assert summary["manual_hold_task_ids"] == []
    previous_ids = {
        task.task_id for relative in (compiler.BOARD_RELATIVE, PREVIOUS_ARTIFACTS[-1])
        for task in _native_tasks(root / relative)
    }
    assert len(previous_ids) == 102
    assert not previous_ids & EXPECTED_TASK_IDS


def test_gui_dag_has_no_cycle_or_activation_before_baseline(gui_spec):
    tasks = {task["id"]: task for task in gui_spec["tasks"]}
    graph = {task_id: set(task["depends_on"]) for task_id, task in tasks.items()}
    ordered = tuple(TopologicalSorter(graph).static_order())
    assert len(ordered) == 60 and set(ordered) == EXPECTED_TASK_IDS
    assert {task_id for task_id, dependencies in graph.items() if not dependencies} == {"CIMP-GUI-01"}
    assert all("CIMP-GUI-01" in _ancestors(tasks, task_id)
               for task_id in EXPECTED_TASK_IDS - {"CIMP-GUI-01"})
    assert set(tasks["CIMP-GUI-60"]["depends_on"]) == EXPECTED_TASK_IDS - {"CIMP-GUI-60"}


@pytest.mark.parametrize("task_id,required", [
    ("CIMP-GUI-06", {"CIMP-GUI-05", "CIMP-GUI-07", "CIMP-GUI-09"}),
    ("CIMP-GUI-11", {"CIMP-GUI-10"}),
    ("CIMP-GUI-12", {"CIMP-GUI-11"}),
    ("CIMP-GUI-34", {"CIMP-GUI-06", "CIMP-GUI-09", "CIMP-GUI-11", "CIMP-GUI-13", "CIMP-GUI-33"}),
    ("CIMP-GUI-41", {"CIMP-GUI-02", "CIMP-GUI-09", "CIMP-GUI-10", "CIMP-GUI-11", "CIMP-GUI-12", "CIMP-GUI-13"}),
    ("CIMP-GUI-42", {"CIMP-GUI-11", "CIMP-GUI-12", "CIMP-GUI-13", "CIMP-GUI-36", "CIMP-GUI-41"}),
    ("CIMP-GUI-50", {"CIMP-GUI-02", "CIMP-GUI-05", "CIMP-GUI-06", "CIMP-GUI-09", "CIMP-GUI-13"}),
    ("CIMP-GUI-55", {"CIMP-GUI-06", "CIMP-GUI-12", "CIMP-GUI-46", "CIMP-GUI-52", "CIMP-GUI-54"}),
    ("CIMP-GUI-56", {"CIMP-GUI-02", "CIMP-GUI-11", "CIMP-GUI-12", "CIMP-GUI-20", "CIMP-GUI-33", "CIMP-GUI-34", "CIMP-GUI-44", "CIMP-GUI-55"}),
    ("CIMP-GUI-58", {"CIMP-GUI-02", "CIMP-GUI-55", "CIMP-GUI-57"}),
    ("CIMP-GUI-59", {"CIMP-GUI-56", "CIMP-GUI-57", "CIMP-GUI-58"}),
])
def test_critical_effects_wait_for_browser_auth_consent_and_key_grants(gui_spec, task_id, required):
    tasks = {task["id"]: task for task in gui_spec["tasks"]}
    assert required <= _ancestors(tasks, task_id)


@pytest.mark.parametrize("task_id,prerequisite", [
    ("CIMP-GUI-08", "CIMP-GUI-06"),
    ("CIMP-GUI-13", "CIMP-GUI-12"),
    ("CIMP-GUI-32", "CIMP-GUI-41"),
])
def test_reviewed_activation_edges_are_explicit(gui_spec, task_id, prerequisite):
    tasks = {task["id"]: task for task in gui_spec["tasks"]}
    assert prerequisite in tasks[task_id]["depends_on"]


def test_route_implementation_tasks_can_wire_the_actual_shared_composition_owner(gui_spec):
    tasks = {task["id"]: task for task in gui_spec["tasks"]}
    route_tasks = (6, 8, 14, 21, 22, 24, 25, 26, 27, 29, 30, 31, 32, 33,
                   37, 38, 39, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52)
    assert "applications/server.py" in tasks["CIMP-GUI-06"]["targets"]
    for number in route_tasks:
        task_id = f"CIMP-GUI-{number:02d}"
        assert "applications/case_routes.py" in tasks[task_id]["targets"], task_id


def test_every_browser_surface_waits_for_real_native_browser_capability(gui_spec):
    tasks = {task["id"]: task for task in gui_spec["tasks"]}
    surfaces = [task for task in tasks.values()
                if any(path.startswith(("templates/", "static/")) for path in task["targets"])]
    assert surfaces
    for task in surfaces:
        assert "CIMP-GUI-02" in _ancestors(tasks, task["id"]), task["id"]


def test_recompilation_preserves_gui_runtime_holds_and_all_six_previous_artifacts(generated_campaign):
    root, source, generated = generated_campaign
    board = Path(generated["board_path"])
    text = board.read_text(encoding="utf-8")
    held = text.replace("- Status: todo", "- Status: waiting_user\n- Manual hold: true\n- Runtime note: synthetic user decision pending", 1)
    assert held != text
    board.write_text(held, encoding="utf-8")
    held_bytes = board.read_bytes()
    identities_before = {task.task_id: task.canonical_task_cid for task in _native_tasks(board)}
    repeated = compiler.generate(source, root)
    assert repeated["receipt"]["board_preserved"] is True
    assert repeated["receipt"]["tasks_completed_by_ingestion"] == 0
    assert board.read_bytes() == held_bytes
    tasks = _native_tasks(board)
    assert {task.task_id: task.canonical_task_cid for task in tasks} == identities_before
    summary = runner._board_summary(tasks)
    assert summary["manual_hold_task_ids"] == ["CIMP-GUI-01"]
    assert summary["ready_task_ids"] == [] and summary["completed"] == 0


def test_gui_selection_and_recovery_use_only_its_bound_spec_and_namespace(gui_spec, generated_campaign, monkeypatch):
    root, source, _ = generated_campaign
    monkeypatch.chdir(root)
    artifacts = campaign_artifacts(gui_spec)
    assert artifacts.__dict__ == CAMPAIGN
    state = root / "fresh-gui-state"
    state.mkdir(mode=0o700)
    board = root / CAMPAIGN["board_relative"]
    # This is a path/configuration fixture, never a process or completion receipt.
    record = {"schema_version": "complaint-improvement-launcher@1", "repo_root": str(root),
              "state_dir": str(state), "spec_path": str(source), "board_path": str(board),
              "plan_id": compiler.build_improvement_work_plan(gui_spec).plan_id,
              "provider": "grok_cli", "model": "grok-4.7", "allow_fallback": False,
              "merge_target": "gui-campaign-test"}
    launcher = state / "launcher.json"
    launcher.write_text(json.dumps(record), encoding="utf-8")
    assert runner._native_campaign_spec(root, state, todo_path=board,
                                        board_namespace=CAMPAIGN["board_namespace"]) == gui_spec
    config = runner._recovery_config(root, state, record)
    assert config.todo_path == board
    assert config.board_namespace == CAMPAIGN["board_namespace"]
    assert set(config.implementation_protected_paths) == {
        CAMPAIGN[field] for field in ("spec_relative", "plan_relative", "board_relative")
    }
    assert config.implementation_timeout == 900 and config.max_task_attempts == 3
    with pytest.raises(ValueError, match="task board"):
        runner._native_campaign_spec(root, state, todo_path=root / PREVIOUS_ARTIFACTS[-1])
    with pytest.raises(ValueError, match="namespace"):
        runner._native_campaign_spec(root, state, todo_path=board, board_namespace="complaint-mediator-grounding")
    record["spec_path"] = str(root / PREVIOUS_ARTIFACTS[3])
    launcher.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="not bound"):
        runner._native_campaign_spec(root, state, todo_path=board,
                                     board_namespace=CAMPAIGN["board_namespace"])
