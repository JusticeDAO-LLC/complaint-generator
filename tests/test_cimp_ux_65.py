"""New UX campaign ingestion and startup stay short of owned execution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from copy import deepcopy
from types import SimpleNamespace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from integrations.ipfs_accelerate import improvement_plan as compiler
from integrations.ipfs_accelerate import improvement_runner as runner


ROOT = Path(__file__).resolve().parents[1]
SPEC = "docs/task_boards/complaint_gui_ux_overhaul_spec.json"
HISTORICAL = (
    "docs/task_boards/complaint_intake_task_board.md",
    "docs/task_boards/complaint_mediator_grounding_task_board.md",
    "docs/task_boards/complaint_gui_collaboration_task_board.md",
)
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture(autouse=True)
def _ready_doctor_without_provider(monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(runner, "_branch", lambda path: "codex/gui-ux-overhaul-20261026")
    monkeypatch.setattr(runner, "_private_runtime_checks", lambda *args: {"ready": True, "reason": "ready"})
    monkeypatch.setattr(runner, "_auth_material_present", lambda env: True)
    monkeypatch.setattr(runner.shutil, "which", lambda *args, **kwargs: "/usr/bin/false")


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    root = tmp_path_factory.mktemp("ux-campaign-repo")
    historical = {}
    for relative in HISTORICAL:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        target.write_bytes(raw)
        historical[relative] = raw
    spec_path = root / SPEC
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_bytes((ROOT / SPEC).read_bytes())
    runner._native_modules(ROOT)
    generated = compiler.generate(spec_path, root)
    spec = compiler.load_spec(spec_path)
    binding = compiler.campaign_observation_binding(spec)
    state = tmp_path_factory.mktemp("ux-campaign-state")
    worktree = tmp_path_factory.mktemp("ux-campaign-worktree")
    os.chmod(worktree, 0o700)
    runner._validate_worktree_root(root, state, worktree, claim=True)
    budget = {"spent": 7, "holds": ["historical-intake"], "refunded": False}
    (state / "budget.json").write_text(json.dumps(budget), encoding="utf-8")
    (state / "receipts.jsonl").write_text('{"task_id":"CIMP-INTAKE-01","status":"completed"}\n', encoding="utf-8")
    (state / "accounting.json").write_text('{"paid_calls":4}\n', encoding="utf-8")
    return {
        "root": root, "spec_path": spec_path, "spec": spec, "generated": generated,
        "binding": binding, "state": state, "worktree": worktree, "historical": historical,
        "budget": (state / "budget.json").read_bytes(),
        "receipts": (state / "receipts.jsonl").read_bytes(),
        "accounting": (state / "accounting.json").read_bytes(),
        "board": Path(generated["board_path"]).read_bytes(),
    }


def _preserved(campaign) -> None:
    state = campaign["state"]
    assert (state / "budget.json").read_bytes() == campaign["budget"]
    assert (state / "receipts.jsonl").read_bytes() == campaign["receipts"]
    assert (state / "accounting.json").read_bytes() == campaign["accounting"]
    assert Path(campaign["generated"]["board_path"]).read_bytes() == campaign["board"]
    for relative, raw in campaign["historical"].items():
        assert (campaign["root"] / relative).read_bytes() == raw
        assert (ROOT / relative).read_bytes() == raw


def _observe(campaign, **kwargs):
    observed = runner.qualify_new_campaign_startup(
        campaign["root"], campaign["spec_path"], kwargs.get("state", campaign["state"]),
        worktree_root=kwargs.get("worktree", campaign["worktree"]))
    _preserved(campaign)
    return observed


def _phase(campaign, *, attempt=1, phase="validating", started=None, task_id="CIMP-UX-01", cid=None):
    tasks = runner._native_modules(ROOT)[1].parse_task_file(
        Path(campaign["generated"]["board_path"]), task_header_prefix=runner.TASK_PREFIX)
    identity = next(task for task in tasks if task.task_id == task_id)
    when = started if started is not None else datetime.now(timezone.utc)
    payload = {
        "implementation_in_progress": True,
        "active_task_id": task_id,
        "active_task_cid": identity.canonical_task_cid if cid is None else cid,
        "active_attempt": attempt,
        "active_phase": phase,
        "active_phase_started_at": when.isoformat(),
    }
    path = campaign["state"] / f"{runner.STATE_PREFIX}_task_state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return identity


class _Owned:
    def __init__(self, campaign):
        token = "synthetic-ux-owner"
        code = (
            "import subprocess,sys,time\n"
            "state=sys.argv[sys.argv.index('--state-dir')+1]\n"
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(180)',"
            "'implementation_daemon','--state-dir',state])\n"
            "time.sleep(180)\n"
        )
        argv = [sys.executable, "-c", code, "_run", "--owner-token", token,
                "--state-dir", str(campaign["state"]), "--worktree-root", str(campaign["worktree"])]
        self.proc = subprocess.Popen(argv, start_new_session=True)
        self.argv = argv
        self.token = token
        self.campaign = campaign
        deadline = time.time() + 5
        child = None
        while time.time() < deadline and child is None:
            for entry in Path("/proc").iterdir():
                if not entry.name.isdigit():
                    continue
                identity = runner.process_identity(int(entry.name))
                if not identity or identity.get("ppid") != self.proc.pid:
                    continue
                if "implementation_daemon" in identity.get("argv", []):
                    child = identity
                    break
            time.sleep(0.05)
        if child is None:
            self.close()
            raise AssertionError("daemon_not_born")
        self.child = child
        launcher = runner.process_identity(self.proc.pid)
        binding = campaign["binding"]
        record = {
            "schema_version": "complaint-improvement-launcher@1",
            "identity": launcher, "argv": argv, "owner_token": token,
            "started_at": time.time(), "status": "starting",
            "repo_root": str(campaign["root"]), "spec_path": str(campaign["spec_path"]),
            "state_dir": str(campaign["state"]), "merge_target": "codex/gui-ux-overhaul-20261026",
            "board_path": campaign["generated"]["board_path"],
            "plan_id": binding["plan_id"], "source_generation": binding["source_generation"],
            "provider": "grok_cli", "model": "grok-4.7", "allow_fallback": False,
            "worktree_root": str(campaign["worktree"]),
            "worktree_root_binding": runner._validate_worktree_root(
                campaign["root"], campaign["state"], campaign["worktree"]),
        }
        runner._atomic_json(campaign["state"] / "launcher.json", record)
        runner._atomic_json(campaign["state"] / f"{runner.STATE_PREFIX}_supervisor_status.json", {
            "status": "running", "supervisor_pid": self.proc.pid, "daemon_pid": child["pid"],
            "daemon_pid_alive": True, "daemon_start_ticks": child["start_ticks"],
            "daemon_boot_id": child["boot_id"],
        })

    def close(self):
        if self.proc.poll() is None:
            os.killpg(self.proc.pid, 15)
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, 9)
                self.proc.wait(timeout=2)


def test_publisher_bindings_are_independent_and_ingestion_does_not_execute(published):
    spec = published["spec"]
    manifest = json.loads((ROOT / "docs/ux/complaint_ux_overhaul/baseline/screenshot_manifest.json").read_text())
    assert spec["baseline_commit"] == manifest["application_base_commit"]
    assert published["generated"]["receipt"]["execution_started"] is False
    assert published["generated"]["receipt"]["tasks_completed_by_ingestion"] == 0
    observed = _observe(published)
    binding = published["binding"]
    assert observed["identities_independent"] is True
    assert observed["publisher_bound"] is True
    assert observed["publisher"]["plan_id"] == binding["plan_id"]
    assert observed["publisher"]["source_generation"] == binding["source_generation"]
    assert set(observed["task_cids"]) == {f"CIMP-UX-{number:02d}" for number in range(1, 69)}
    assert len(set(observed["task_cids"].values())) == 68
    sample = observed["task_bindings"]["CIMP-UX-65"]
    declared = next(task for task in spec["tasks"] if task["id"] == "CIMP-UX-65")
    assert sample["depends_on"] == declared["depends_on"]
    assert sample["validation"] == declared["validation_commands"]
    assert sample["status"] == "todo"
    assert observed["execution_admitted"] is False
    assert observed["ingestion_is_execution"] is False
    assert observed["tasks_completed_by_ingestion"] == 0
    assert observed["doctor_ready"] is True
    assert observed["doctor_ready_is_execution"] is False
    assert observed["launcher_birth"] is False and observed["daemon_birth"] is False
    assert observed["paid_calls"] == 0 and observed["completion_authority"] is False
    scopes = observed["identity_scopes"]
    assert len(set(scopes.values())) == 6
    assert Path(scopes["state"]) != Path(scopes["worktree"])
    assert not Path(scopes["state"]).is_relative_to(published["root"])
    assert binding["board_namespace"] == "complaint-gui-ux-overhaul"
    assert binding["distinct_from_historical_intake"] is True


def test_live_pid_and_completed_markdown_are_not_execution(published):
    board = Path(published["generated"]["board_path"])
    held = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        identity = runner.process_identity(held.pid)
        runner._atomic_json(published["state"] / "launcher.json", {
            "schema_version": "complaint-improvement-launcher@1",
            "identity": identity, "argv": identity["argv"], "owner_token": "not-a-campaign-owner",
            "repo_root": str(published["root"]), "spec_path": str(published["spec_path"]),
            "state_dir": str(published["state"]), "plan_id": published["binding"]["plan_id"],
            "source_generation": published["binding"]["source_generation"],
            "provider": "grok_cli", "model": "grok-4.7",
        })
        text = board.read_text(encoding="utf-8")
        board.write_text(text.replace("- Status: todo", "- Status: completed", 1), encoding="utf-8")
        published["board"] = board.read_bytes()
        observed = _observe(published)
        assert observed["pid_alive"] is True
        assert observed["pid_alive_is_execution"] is False
        assert observed["launcher_birth"] is False
        assert observed["markdown_completed_task_ids"]
        assert observed["markdown_status_grants_execution"] is False
        assert observed["tasks_completed_by_ingestion"] == 0
        assert observed["execution_admitted"] is False
        assert observed["doctor_ready_is_execution"] is False
    finally:
        held.kill()
        held.wait(timeout=2)
        restored = board.read_text(encoding="utf-8").replace("- Status: completed", "- Status: todo", 1)
        board.write_text(restored, encoding="utf-8")
        published["board"] = board.read_bytes()


def test_owned_births_without_bounded_work_do_not_execute(published):
    owned = _Owned(published)
    try:
        observed = _observe(published)
        assert observed["launcher_birth"] is True
        assert observed["daemon_birth"] is False
        assert observed["bounded_work"]["active"] is False
        assert observed["execution_admitted"] is False
        assert observed["doctor_ready"] is True
        assert observed["doctor_ready_is_execution"] is False
        assert observed["paid_calls"] == 0
    finally:
        owned.close()


def test_authored_phase_and_inert_owned_processes_are_not_execution(published):
    _phase(published)
    owned = _Owned(published)
    try:
        observed = _observe(published)
        assert observed["execution_admitted"] is False
        assert observed["launcher_birth"] is True and observed["daemon_birth"] is False
        assert observed["bounded_work"]["phase"] == "validating"
        assert observed["bounded_work"]["attempt"] == 1
        assert observed["bounded_work"]["timeout_seconds"] == 900
        assert observed["bounded_work"]["validation_commands"]
        assert observed["source_generation_bound"] is True and observed["plan_bound"] is True
        assert observed["publisher_bound"] is True
        assert "CIMP-UX-65" not in observed["markdown_completed_task_ids"]
        assert observed["task_bindings"]["CIMP-UX-01"]["status"] == "todo"
        assert observed["completion_authority"] is False
        assert observed["historical_and_budget_unchanged"] is True
    finally:
        owned.close()


def test_expired_attempt_and_foreign_generation_are_refused(published):
    _phase(published, attempt=4, phase="implementing",
           started=datetime.now(timezone.utc) - timedelta(seconds=1000))
    owned = _Owned(published)
    try:
        refused = _observe(published)
        assert refused["launcher_birth"] is True and refused["daemon_birth"] is False
        assert refused["bounded_work"]["active"] is False
        assert refused["execution_admitted"] is False
        record = json.loads((published["state"] / "launcher.json").read_text(encoding="utf-8"))
        record["source_generation"] = "other-generation"
        runner._atomic_json(published["state"] / "launcher.json", record)
        _phase(published, attempt=1, phase="implementing")
        mismatched = _observe(published)
        assert mismatched["source_generation_bound"] is False
        assert mismatched["launcher_birth"] is False
        assert mismatched["execution_admitted"] is False
        assert mismatched["publisher"]["source_generation"] == published["binding"]["source_generation"]
    finally:
        owned.close()


def test_collapsed_scopes_and_unpublished_plan_are_not_a_new_campaign(published):
    inside = published["root"] / "nested-state"
    inside.mkdir()
    nested_worktree = published["root"] / "nested-worktree"
    nested_worktree.mkdir()
    os.chmod(nested_worktree, 0o700)
    collapsed = runner.qualify_new_campaign_startup(
        published["root"], published["spec_path"], inside, worktree_root=nested_worktree)
    assert collapsed["identities_independent"] is False
    assert collapsed["execution_admitted"] is False
    plan = published["root"] / published["binding"]["plan_relative"]
    original = plan.read_bytes()
    plan.write_text("{", encoding="utf-8")
    try:
        broken = _observe(published)
        assert broken["publisher_bound"] is False
        assert broken["execution_admitted"] is False
        assert broken["tasks_completed_by_ingestion"] == 0
    finally:
        plan.write_bytes(original)
    _preserved(published)


def test_native_duckdb_without_json_mirror_is_observed(published, tmp_path):
    """The genuine Native row is readable; authored phase still is not work."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    from integrations.ipfs_accelerate.reconciliation_activity import catalog_path
    daemon = runner._native_modules(ROOT)[1]
    tasks = daemon.parse_task_file(Path(published["generated"]["board_path"]), task_header_prefix=runner.TASK_PREFIX)
    task = next(item for item in tasks if item.task_id == "CIMP-UX-01")
    state_dir = tmp_path / "duckdb-campaign"
    state_dir.mkdir(mode=0o700)
    state_path = state_dir / f"{runner.STATE_PREFIX}_task_state.json"
    catalog, _ = catalog_path(runner, state_dir)
    plane.bind_task_state_control_plane(state_path, str(catalog))
    state = daemon.PortalTaskState()
    state.implementation_in_progress = True
    state.active_task_id = task.task_id
    state.active_task_cid = task.canonical_task_cid
    state.active_task_key = task.canonical_task_key
    state.active_attempt = 1
    state.active_phase = "validating"
    state.active_phase_started_at = datetime.now(timezone.utc).isoformat()
    state.save(state_path)
    assert not state_path.exists()
    before = catalog.read_bytes()
    value = runner._bounded_provider_validation(published["root"], state_dir,
        {task.task_id: task.canonical_task_cid}, tasks)
    assert value["native_state_source"]["source"] == "native_control_plane"
    assert value["phase"] == "validating" and value["attempt"] == 1
    assert value["phase_metadata_bounded"] is True
    assert value["active"] is False
    assert value["completion_authority"] is False
    assert before == catalog.read_bytes() and not state_path.exists()
    # True current-row metadata remains insufficient; corrupted attempt/case
    # bindings must also fail before observing any execution producer.
    for field, altered in (("active_task_cid", "foreign-cid"), ("active_task_key", "foreign-key"),
                            ("active_attempt", 4), ("active_phase", "waiting_for_user")):
        prior = getattr(state, field)
        setattr(state, field, altered)
        state.save(state_path)
        refused = runner._bounded_provider_validation(published["root"], state_dir,
            {task.task_id: task.canonical_task_cid}, tasks)
        assert refused["phase_metadata_bounded"] is False and refused["active"] is False, field
        setattr(state, field, prior)
    state.save(state_path)


@pytest.mark.parametrize("old,new", [
    ("- Implementation provider: grok", "- Implementation provider: codex"),
    ("- Provider role: grok-only", "- Provider role: any"),
    ("- Model: grok-4.7", "- Model: another-model"),
    ("- Provider fallback: disabled", "- Provider fallback: enabled"),
])
def test_published_board_semantic_route_changes_are_refused(published, old, new):
    board = Path(published["generated"]["board_path"])
    raw = board.read_bytes()
    assert old.encode() in raw
    try:
        board.write_bytes(raw.replace(old.encode(), new.encode(), 1))
        # Preservation is measured around observation, not around this explicit
        # negative fixture mutation of its own independent generated board.
        published["board"] = board.read_bytes()
        observed = _observe(published)
        assert observed["publisher_bound"] is False
        assert observed["execution_admitted"] is False
    finally:
        board.write_bytes(raw)
        published["board"] = raw


def _native_fixture_stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()

def _native_fixture_write(path, body):
    runner._atomic_json(path, body)
    path.chmod(0o600)

def _native_fixture_wait(path, timeout=20):
    deadline = time.monotonic() + timeout
    while not path.is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError(path.name)
        time.sleep(.05)
    return json.loads(path.read_text())

def _native_fixture_worker(base):
    """Actual local executor under explicitly synthetic direct-child custody."""
    runner._native_modules(ROOT)
    from integrations.ipfs_accelerate import reconciliation_activity
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as daemon
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import build_validation_environment, validation_environment_for_runner
    campaign = base / "campaign"
    state_path = campaign / (runner.STATE_PREFIX + "_task_state.json")
    workspace = base / "worktrees" / "validator"
    _native_fixture_wait(base / "owner-ready.json")
    board = base / "fixture-board.md"
    board.write_text("## CIMP-FIXTURE-65 Local validator producer\n\n"
                     "- Status: todo\n- Completion: validation\n- Priority: high\n"
                     "- Outputs: fixture.txt\n- Validation: sleep 8\n")
    task = daemon.parse_task_file(board, task_header_prefix=runner.TASK_PREFIX)[0]
    worker = daemon.PortalImplementationDaemon(todo_path=board, state_path=state_path,
        strategy_path=campaign / "strategy.json", events_path=campaign / "events.jsonl",
        repo_root=ROOT, task_header_prefix=runner.TASK_PREFIX, implement=False,
        use_ephemeral_worktree=False, worktree_root=base / "worktrees")
    started = _native_fixture_stamp(time.time() - 1)
    claim = worker._build_implementation_task_claim_metadata(task, 1, started)
    claim_path = worker._implementation_task_claim_path(task.task_id, canonical_task_cid=task.canonical_task_cid)
    acquired = worker._try_acquire_implementation_dispatch_intent(claim_path, claim)
    assert acquired[0], acquired[1]
    claim = acquired[3]
    lease = worker._build_implementation_lock_metadata(task, 1, started)
    lease_path = campaign / "implementation.lock"
    assert worker._try_acquire_implementation_lock(lease_path, lease)[0]
    try:
        catalog, _ = reconciliation_activity.catalog_path(runner, campaign)
        plane.bind_task_state_control_plane(state_path, str(catalog))
        now = time.time()
        log = campaign / "implementation_logs" / (task.task_id.lower() + "-attempt-1-" + "e" * 32 + ".log")
        log.write_text("Private local validator fixture, no provider dispatch.\n")
        log.chmod(0o600)
        state = daemon.PortalTaskState()
        for key, value in dict(implementation_in_progress=True, active_task_id=task.task_id,
            last_implementation_task_id=task.task_id, active_task_cid=task.canonical_task_cid,
            active_task_key=task.canonical_task_key, active_attempt=1, active_phase="validating",
            active_phase_started_at=_native_fixture_stamp(now), last_implementation_started_at=started,
            last_implementation_finished_at="", active_worktree_path=str(workspace),
            active_log_path=str(log), last_implementation_log_path=str(log), heartbeat_at=_native_fixture_stamp(now),
            last_progress_at=_native_fixture_stamp(now)).items():
            setattr(state, key, value)
        state.save(state_path)
        assert not state_path.exists(), "Fixture must exercise Native DuckDB without a JSON mirror."
        context = dict(campaign_state_dir=str(campaign), target_source_root=str(ROOT),
            task_id=task.task_id, task_cid=task.canonical_task_cid, task_key=task.canonical_task_key)
        binding = runner._validation_activity_binding(workspace, {"id": task.task_id}, context, now_ts=time.time())
        assert binding is not None, "Actual Native custody failed its existing binding."
        _native_fixture_write(base / "worker-ready.json", {"task_id": task.task_id, "task_cid": task.canonical_task_cid,
            "task_key": task.canonical_task_key, "catalog": str(catalog), "claim_path": str(claim_path)})
        validation_environment = validation_environment_for_runner(build_validation_environment({
            "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
            "IPFS_ACCELERATE_AGENT_VALIDATION_PYTHON": sys.executable}),
            daemon.PortalImplementationDaemon._validation_command_runner)
        result = runner._call_validation_with_activity(
            executor=daemon.PortalImplementationDaemon._validation_command_runner,
            spec=SimpleNamespace(command="sleep 8", raw_command="sleep 8"), workspace_path=workspace,
            timeout_seconds=20, environment=validation_environment, task={"id": task.task_id}, context=context)
        assert result["returncode"] == 0, result
        _native_fixture_write(base / "worker-result.json", {"returncode": result["returncode"],
            "executor": "PortalImplementationDaemon._validation_command_runner", "provider_dispatched": False,
            "completion_authority": False})
        _native_fixture_wait(base / "owner-observed.json")
    finally:
        worker._release_implementation_lock(lease_path, lease)
        worker._release_implementation_task_claim(claim_path, claim)

def _native_fixture_owner(base):
    runner._native_modules(ROOT)
    from integrations.ipfs_accelerate import reconciliation_activity
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as daemon
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import build_validation_environment, validation_environment_for_runner
    fixture_sdk_pin = subprocess.check_output(["git", "rev-parse", "HEAD"],
        cwd=Path(native.__file__).resolve().parents[3], text=True).strip()
    campaign = base / "campaign"
    worktrees = base / "worktrees"
    for path in (campaign, worktrees, campaign / "implementation_logs"):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    root_binding = runner._validate_worktree_root(ROOT, campaign, worktrees, claim=True)
    (worktrees / "validator").mkdir(mode=0o700)
    process = subprocess.Popen([sys.executable, "-I", "-B", str(Path(sys.argv[0]).resolve()), "--worker", str(base)], cwd=base)
    record = dict(identity=runner.process_identity(os.getpid()), argv=runner.process_identity(os.getpid())["argv"],
        owner_token="private-native-validator-fixture", started_at=time.time(), repo_root=str(ROOT),
        state_dir=str(campaign), board_path=str(ROOT / runner.DEFAULT_ARTIFACTS.board_relative),
        worktree_root=str(worktrees), worktree_root_binding=root_binding)
    _native_fixture_write(campaign / "launcher.json", record)
    assert runner.owns_process(record)
    # This is declared synthetic policy custody.  The stored command remains
    # the helper's true argv, so a strict actual-runner check must reject it.
    native.write_supervised_child_identity(campaign / (runner.STATE_PREFIX + "_managed_daemon.identity.json"),
        pid=process.pid, command=[sys.executable, "-I", "-B", str(Path(sys.argv[0]).resolve()), "--worker", str(base)],
        owner_scope=dict(repo_root=str(ROOT), state_dir=str(campaign), state_prefix=runner.STATE_PREFIX,
            todo_path=str(ROOT / runner.DEFAULT_ARTIFACTS.board_relative), daemon_entrypoint=str(Path(runner.__file__).resolve())),
        require_direct_child=True)
    _native_fixture_write(campaign / (runner.STATE_PREFIX + "_supervisor_status.json"), dict(status="running",
        supervisor_pid=os.getpid(), daemon_pid=process.pid, daemon_pid_alive=True, updated_at=_native_fixture_stamp(time.time())))
    _native_fixture_write(base / "owner-ready.json", {"ready": True, "synthetic_custody": True})
    try:
        worker = _native_fixture_wait(base / "worker-ready.json")
        evidence = None
        snapshot = None
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            snapshot = reconciliation_activity.snapshot(runner, campaign)
            assert snapshot is not None
            evidence = reconciliation_activity.evidence(runner, ROOT, campaign, record, snapshot["body"], now_ts=time.time())
            if evidence is not None:
                break
            if process.poll() is not None:
                raise AssertionError("Local validator exited before evidence; see private log.")
            time.sleep(.1)
        assert evidence is not None, "No canonical executor activity was observed."
        assert evidence["source"] == "owned_canonical_executor_activity"
        strict_daemon_birth = runner._daemon_birth_owned(record, campaign)
        assert strict_daemon_birth is False, "A helper child must not qualify as the actual campaign daemon."
        before = json.dumps(snapshot, sort_keys=True)
        refused = {}
        for damage in ("cid", "attempt", "phase", "owner_birth", "expired"):
            body = deepcopy(snapshot["body"])
            observed_record = deepcopy(record)
            now = time.time()
            if damage == "cid": body["active_task_cid"] = "foreign-task-cid"
            elif damage == "attempt":
                # The reader deliberately derives its attempt from canonical
                # DuckDB, so test actual pulse replay against a changed binding.
                context = dict(campaign_state_dir=str(campaign), target_source_root=str(ROOT),
                    task_id=body["active_task_id"], task_cid=body["active_task_cid"], task_key=body["active_task_key"])
                binding = runner._validation_activity_binding(Path(body["active_worktree_path"]),
                    {"id": body["active_task_id"]}, context, now_ts=now, owner_pid=process.pid)
                pulse = runner._read_validation_activity(runner._validation_activity_path(binding))
                refused[damage] = not runner._validation_activity_record_valid(pulse, {**binding, "attempt": 2}, now_ts=now)
                continue
            elif damage == "phase": body["active_phase"] = "implementing"
            elif damage == "owner_birth": observed_record["identity"]["start_ticks"] += 1
            else: now += runner.TIMEOUT_SECONDS + 1
            refused[damage] = reconciliation_activity.evidence(runner, ROOT, campaign, observed_record, body, now_ts=now) is None
        # Readers and rejection probes never write Native state.
        after = reconciliation_activity.snapshot(runner, campaign)
        assert before == json.dumps(after, sort_keys=True)
        _native_fixture_write(base / "owner-observed.json", {"observed": True})
        process.wait(timeout=20)
        assert process.returncode == 0
        result = _native_fixture_wait(base / "worker-result.json")
        state_path = campaign / (runner.STATE_PREFIX + "_task_state.json")
        report = dict(schema="private-task65-native-validator-producer@1", synthetic_policy_custody=True,
            full_campaign_qualified=False, actual_runner_entrypoint=False, provider_dispatched=False,
            strict_daemon_birth_owned=strict_daemon_birth,
            native_state_source="native_duckdb_control_plane", json_mirror_absent=not state_path.exists(),
            native_snapshot_revision=snapshot["revision"], activity_evidence=evidence,
            refused=refused, native_state_unchanged=before == json.dumps(after, sort_keys=True),
            validator=result, completion_authority=False,
            source_root=str(ROOT), source_sha256=hashlib.sha256(Path(runner.__file__).read_bytes()).hexdigest(),
            sdk_pin=fixture_sdk_pin, task_id=worker["task_id"])
        _native_fixture_write(base / "report.json", report)
        return report
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)

@pytest.fixture(scope="module")
def actual_native_local_validator(tmp_path_factory):
    """Real Native producers/executor; explicit synthetic helper custody only."""
    runner._native_modules(ROOT)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    sdk = Path(native.__file__).resolve().parents[3]
    actual_pin = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=sdk, text=True).strip()
    declared_pin = subprocess.check_output(["git", "rev-parse", "HEAD:external/ipfs_accelerate_py"], cwd=ROOT, text=True).strip()
    assert actual_pin == declared_pin
    base = tmp_path_factory.mktemp("actual-native-local-validator")
    program = base / "fixture_entrypoint.py"
    paths = [str(ROOT), str(sdk), str(sdk.parent / "ipfs_datasets_py"), str(sdk.parent / "ipfs_kit_py")]
    program.write_text("import sys\nsys.path[:0]="+repr(paths)+"\n"+
        "from pathlib import Path\nfrom tests.test_cimp_ux_65 import _native_fixture_owner, _native_fixture_worker\n"+
        "if __name__=='__main__':\n (_native_fixture_worker if sys.argv[1]=='--worker' else _native_fixture_owner)(Path(sys.argv[2]))\n")
    argv = [sys.executable, "-I", "-B", str(program), "--owner", str(base), "_run", "--owner-token",
            "private-native-validator-fixture", "--worktree-root", str(base / "worktrees")]
    with (base / "private-producer.log").open("w") as log:
        result = subprocess.run(argv, cwd=base, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, timeout=80)
    assert result.returncode == 0, "See private-producer.log for the isolated local producer."
    return json.loads((base / "report.json").read_text())


def test_actual_native_duckdb_and_canonical_local_validator_under_synthetic_custody(actual_native_local_validator):
    report = actual_native_local_validator
    assert report["synthetic_policy_custody"] is True
    assert report["json_mirror_absent"] is True and report["native_state_unchanged"] is True
    assert type(report["native_snapshot_revision"]) is int
    assert report["native_state_source"] == "native_duckdb_control_plane"
    assert report["activity_evidence"]["source"] == "owned_canonical_executor_activity"
    assert report["activity_evidence"]["type"] == "canonical_native_validation_in_flight"
    assert report["activity_evidence"]["attempt"] == 1
    assert report["validator"]["returncode"] == 0
    assert all(report["refused"].values()), report["refused"]
    assert report["strict_daemon_birth_owned"] is False
    assert report["full_campaign_qualified"] is False and report["actual_runner_entrypoint"] is False
    assert report["provider_dispatched"] is False and report["completion_authority"] is False
