"""Independent campaign artifacts retain the completed intake campaign."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import time
import subprocess

import pytest

from integrations.ipfs_accelerate import improvement_plan as compiler
from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import improvement_shutdown as shutdown
from integrations.ipfs_accelerate.campaign import DEFAULT_ARTIFACTS, campaign_artifacts
from tests.test_improvement_validation_activity import ownership


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = {
    "spec_relative": "docs/task_boards/complaint_mediator_grounding_spec.json",
    "plan_relative": "docs/task_boards/complaint_mediator_grounding_formal_work_plan.json",
    "board_relative": "docs/task_boards/complaint_mediator_grounding_task_board.md",
    "board_namespace": "complaint-mediator-grounding",
}


def _spec(*, campaign=True):
    spec = compiler.load_spec(ROOT / compiler.SPEC_RELATIVE)
    goal = deepcopy(spec["goals"][0])
    subgoal = deepcopy(goal["subgoals"][0])
    goal.update(id="MGND-G1", subgoals=[subgoal])
    subgoal["id"] = "MGND-S1"
    task = deepcopy(spec["tasks"][0])
    task.update(id="CIMP-MGND-BOOTSTRAP", goal_id=goal["id"], subgoal_id=subgoal["id"], depends_on=[])
    spec.update(goals=[goal], tasks=[task])
    if campaign:
        spec["campaign"] = dict(CAMPAIGN)
    return spec


def _write(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    return path


def _launch(root, state, spec_path, spec):
    artifacts = campaign_artifacts(spec)
    argv = [sys.executable, str(root / "scripts/run_complaint_improvement_supervisor.py"), "_run",
            "--repo-root", str(root), "--spec", str(spec_path), "--state-dir", str(state),
            "--owner-token", "synthetic-owner", "--merge-target", "campaign-test"]
    record = {"schema_version": "complaint-improvement-launcher@1", "repo_root": str(root),
              "spec_path": str(spec_path), "state_dir": str(state),
              "plan_id": compiler.build_improvement_work_plan(spec).plan_id,
              "board_path": str(root / artifacts.board_relative), "provider": "grok_cli",
              "model": "grok-4.7", "allow_fallback": False, "owner_token": "synthetic-owner",
              "argv": argv, "merge_target": "campaign-test", "started_at": time.time() - 1,
              "identity": {"pid": 99999999, "session": 99999999, "process_group": 99999999,
                           "start_ticks": 1, "boot_id": "synthetic-boot", "argv": argv}}
    _write(state, "launcher.json", record)
    return record


def test_default_native_identity_and_existing_board_bytes_are_preserved(tmp_path):
    spec = compiler.load_spec(ROOT / compiler.SPEC_RELATIVE)
    expected = json.loads((ROOT / compiler.PLAN_RELATIVE).read_bytes())
    assert compiler.build_improvement_work_plan(spec).plan_id == expected["plan_id"]
    assert campaign_artifacts(spec) == DEFAULT_ARTIFACTS
    assert DEFAULT_ARTIFACTS.protected_paths == ()
    assert "--implementation-protected-path" not in runner.native_argv(
        tmp_path / compiler.BOARD_RELATIVE, tmp_path / "state", "campaign-test")
    spec_path = _write(tmp_path, compiler.SPEC_RELATIVE, spec)
    board = tmp_path / compiler.BOARD_RELATIVE
    board.write_bytes((ROOT / compiler.BOARD_RELATIVE).read_bytes())
    before = board.read_bytes()
    result = compiler.generate(spec_path, tmp_path)
    assert result["receipt"]["board_preserved"] is True
    assert board.read_bytes() == before
    assert result["plan_path"] == str(tmp_path / compiler.PLAN_RELATIVE)


def test_new_native_plan_and_board_use_their_actual_source_without_replacing_intake(tmp_path):
    protected = {}
    for relative in (compiler.SPEC_RELATIVE, compiler.PLAN_RELATIVE, compiler.BOARD_RELATIVE):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
        protected[relative] = path.read_bytes()
    spec = _spec()
    path = _write(tmp_path, CAMPAIGN["spec_relative"], spec)
    result = compiler.generate(path, tmp_path)
    assert result["plan_path"] == str(tmp_path / CAMPAIGN["plan_relative"])
    assert result["board_path"] == str(tmp_path / CAMPAIGN["board_relative"])
    plan = compiler.build_improvement_work_plan(spec)
    assert plan.source_ids == ("complaint-generator", CAMPAIGN["spec_relative"])
    assert plan.goals[0].source_ids == (CAMPAIGN["spec_relative"],)
    from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import FormalWorkPlan
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import parse_task_file
    restored = FormalWorkPlan.from_dict(json.loads(Path(result["plan_path"]).read_bytes()))
    assert restored.plan_id == plan.plan_id and restored.events == ()
    tasks = parse_task_file(Path(result["board_path"]), task_header_prefix=runner.TASK_PREFIX)
    assert [task.task_id for task in tasks] == ["CIMP-MGND-BOOTSTRAP"]
    assert tasks[0].validation == spec["tasks"][0]["validation_commands"]
    assert tasks[0].metadata["provider role"] == "grok-only"
    board = Path(result["board_path"])
    board.write_text(board.read_text().replace("- Status: todo", "- Status: blocked"))
    held = board.read_bytes()
    assert compiler.generate(path, tmp_path)["receipt"]["board_preserved"] is True
    assert board.read_bytes() == held
    assert all((tmp_path / relative).read_bytes() == raw for relative, raw in protected.items())
    assert result["receipt"]["tasks_completed_by_ingestion"] == 0


@pytest.mark.parametrize("field,value", [
    ("spec_relative", compiler.SPEC_RELATIVE),
    ("plan_relative", "../foreign.json"),
    ("board_relative", "/foreign.md"),
    ("board_relative", "docs/task_boards/../foreign.md"),
    ("board_relative", compiler.BOARD_RELATIVE),
    ("plan_relative", CAMPAIGN["spec_relative"]),
    ("board_namespace", DEFAULT_ARTIFACTS.board_namespace),
    ("board_namespace", "Foreign Namespace"),
])
def test_campaign_cannot_alias_old_artifacts_or_escape_its_scope(field, value):
    spec = _spec()
    spec["campaign"][field] = value
    with pytest.raises(ValueError):
        compiler.validate_spec(spec)


def test_actual_spec_location_and_artifact_symlinks_are_rejected_before_publication(tmp_path):
    spec = _spec()
    wrong = _write(tmp_path, "docs/task_boards/other.json", spec)
    with pytest.raises(ValueError, match="declared source"):
        compiler.generate(wrong, tmp_path)
    right = _write(tmp_path, CAMPAIGN["spec_relative"], spec)
    old = tmp_path / compiler.BOARD_RELATIVE
    old.write_text("retained completed board")
    (tmp_path / CAMPAIGN["board_relative"]).symlink_to(old)
    with pytest.raises(ValueError, match="symlink"):
        compiler.generate(right, tmp_path)
    assert old.read_text() == "retained completed board"
    assert not (tmp_path / CAMPAIGN["plan_relative"]).exists()


def test_native_daemon_and_recovery_select_the_bound_new_specification(tmp_path):
    _write(tmp_path, compiler.SPEC_RELATIVE, _spec(campaign=False))
    spec = _spec()
    path = _write(tmp_path, CAMPAIGN["spec_relative"], spec)
    state = tmp_path / "fresh-campaign"
    state.mkdir(mode=0o700)
    record = _launch(tmp_path, state, path, spec)
    board = tmp_path / CAMPAIGN["board_relative"]
    selected = runner._native_campaign_spec(tmp_path, state, todo_path=board,
                                           board_namespace=CAMPAIGN["board_namespace"])
    assert selected == spec
    config = runner._recovery_config(tmp_path, state, record)
    assert set(config.implementation_protected_paths) == set(campaign_artifacts(spec).protected_paths)
    native_scheduler = object()
    daemon = SimpleNamespace(validation_scheduler=native_scheduler)
    class NativeSupervisor:
        def _build_worktree_reconciliation_daemon(self):
            return daemon
    supervisor = runner._validation_aware_supervisor_class(NativeSupervisor)()
    supervisor.config = SimpleNamespace(repo_root=tmp_path, state_dir=state, todo_path=board,
                                        board_namespace=CAMPAIGN["board_namespace"])
    assert supervisor._build_worktree_reconciliation_daemon().validation_scheduler.spec == spec
    with pytest.raises(ValueError, match="task board"):
        runner._native_campaign_spec(tmp_path, state, todo_path=tmp_path / compiler.BOARD_RELATIVE)
    with pytest.raises(ValueError, match="namespace"):
        runner._native_campaign_spec(tmp_path, state, todo_path=board, board_namespace="foreign")
    _write(state, "launcher.json", {"unbound": True})
    with pytest.raises(ValueError, match="namespace"):
        runner._native_campaign_spec(tmp_path, state, todo_path=board,
                                     board_namespace=CAMPAIGN["board_namespace"])


def test_doctor_parses_the_new_board_and_native_namespace_without_starting(tmp_path, monkeypatch):
    native_modules = runner._native_modules(ROOT)
    monkeypatch.setattr(runner, "_native_modules", lambda root: native_modules)
    spec = _spec()
    path = _write(tmp_path, CAMPAIGN["spec_relative"], spec)
    compiler.generate(path, tmp_path)
    state = tmp_path / "fresh-campaign"
    state.mkdir(mode=0o700)
    monkeypatch.setattr(runner, "_resource_capacity", lambda *a: {"ready": True})
    monkeypatch.setattr(runner, "_worktree_capacity", lambda *a: {"sufficient": True})
    monkeypatch.setattr(runner, "_private_runtime_checks", lambda *a: {"ready": True})
    monkeypatch.setattr(runner, "_auth_material_present", lambda *a: False)
    result = runner.doctor(tmp_path, path, state, merge_target="campaign-test")
    args = native_modules[0].parse_args(result["native_argv"])
    assert args.todo_path == tmp_path / CAMPAIGN["board_relative"]
    assert args.board_namespace == CAMPAIGN["board_namespace"]
    assert args.implementation_protected_path == list(campaign_artifacts(spec).protected_paths)
    assert args.implementation_timeout == 900 and args.max_task_attempts == 3
    assert result["status"] == "not_ready" and result["paid_calls"] == 0
    assert result["board"]["ready_task_ids"] == ["CIMP-MGND-BOOTSTRAP"]


@pytest.mark.parametrize("new_campaign", [False, True])
def test_public_shutdown_context_accepts_only_the_bound_campaign_board(tmp_path, new_campaign):
    spec = _spec(campaign=new_campaign)
    artifacts = campaign_artifacts(spec)
    path = _write(tmp_path, artifacts.spec_relative, spec)
    state = tmp_path / "fresh-campaign"
    state.mkdir(mode=0o700)
    record = _launch(tmp_path, state, path, spec)
    assert shutdown._context(state, record)["plan_id"] == record["plan_id"]
    record["board_path"] = str(tmp_path / "docs/task_boards/foreign.md")
    _write(state, "launcher.json", record)
    with pytest.raises(ValueError, match="paths differ"):
        shutdown._context(state, record)


def test_native_daemon_entrypoint_bootstraps_its_package_in_isolated_python():
    result = subprocess.run([sys.executable, "-I", "-B", str(Path(runner.__file__)), "--help"],
                            text=True, capture_output=True, timeout=30, check=False)
    assert result.returncode == 0 and "prepare" in result.stdout


@pytest.mark.parametrize("damage", [None, "foreign_scope", "foreign_launcher_board", "changed_spec"])
def test_new_campaign_validation_activity_requires_its_exact_bound_board(ownership, damage):
    spec = _spec()
    spec["tasks"][0]["id"] = ownership.task["id"]
    path = _write(ownership.target, CAMPAIGN["spec_relative"], spec)
    record = _launch(ownership.target, ownership.campaign, path, spec)
    ownership.identity.owner_scope["todo_path"] = str(ownership.target / CAMPAIGN["board_relative"])
    if damage == "foreign_scope":
        ownership.identity.owner_scope["todo_path"] = str(ownership.target / compiler.BOARD_RELATIVE)
    elif damage == "foreign_launcher_board":
        record["board_path"] = str(ownership.target / compiler.BOARD_RELATIVE)
        _write(ownership.campaign, "launcher.json", record)
    elif damage == "changed_spec":
        spec["title"] += " changed"
        _write(ownership.target, CAMPAIGN["spec_relative"], spec)
    binding = runner._validation_activity_binding(ownership.workspace, ownership.task,
                                                  ownership.context, now_ts=time.time())
    if damage is None:
        assert binding is not None and binding["canonical_task_cid"] == ownership.context["task_cid"]
    else:
        assert binding is None


@pytest.mark.parametrize("new_campaign", [False, True])
def test_genuine_native_measurement_freezes_spec_as_input_and_admits_only_declared_outputs(tmp_path, new_campaign):
    from tests.test_improvement_evidence_gate import _gate, _task, _observation, _write_output
    from integrations.ipfs_accelerate.improvement_plan import _MeasuredEvidence, bind_sources, canonical_model_policy
    task = _task("CIMP-MGND-BIND")
    _write_output(tmp_path, task["id"])
    second = "out/second.py"
    (tmp_path / second).write_text("VALUE = 2\n")
    task["targets"].append(second)
    source = _write(tmp_path, CAMPAIGN["spec_relative"], {"input_revision": 1})
    context = {"campaign_spec_relative": CAMPAIGN["spec_relative"]} if new_campaign else {}
    observation, _, _ = _gate(tmp_path, task,
        _observation(tmp_path, task["id"], source_binding=bind_sources(tmp_path, task["targets"])),
        _return_measurement=True, _measurement_context=context)
    assert isinstance(observation, _MeasuredEvidence)
    host = observation["host_measurement"]
    assert host["source_before"] == host["source_after"]
    assert (CAMPAIGN["spec_relative"] in host["source_after"]["files"]) is new_campaign
    assert host["output_paths"] == task["targets"]
    assert observation["source_binding"] == bind_sources(tmp_path, task["targets"])
    receipt = runner.gate_task_completion(tmp_path, tmp_path / "state", task, observation,
        model_policy=canonical_model_policy(), legal_data_version="synthetic-current-data")
    assert receipt["admitted"] is True and receipt["completion_authority"] is False
    spec = {"tasks": [task], **({"campaign": dict(CAMPAIGN)} if new_campaign else {})}
    current = runner.recompute_dependent_readiness(tmp_path, tmp_path / "state", spec)
    assert current["tasks"][task["id"]]["complete"] is True
    source.write_text('{"input_revision": 2}')
    changed = runner.recompute_dependent_readiness(tmp_path, tmp_path / "state", spec)
    assert changed["tasks"][task["id"]]["complete"] is (not new_campaign)
    if new_campaign:
        assert changed["tasks"][task["id"]]["reason"] == "stale_source_hash"
    repeated = runner.gate_task_completion(tmp_path, tmp_path / "state", task, observation,
        model_policy=canonical_model_policy(), legal_data_version="synthetic-current-data")
    assert repeated["admitted"] is (not new_campaign)
    if new_campaign:
        assert repeated["reason"] == "stale_source_hash"
