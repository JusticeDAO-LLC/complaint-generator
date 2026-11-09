"""A pending scope amendment preserves actual native accounting and history."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess

import pytest

from integrations.ipfs_accelerate import improvement_amendment as amendment
from integrations.ipfs_accelerate import improvement_plan as compiler
from integrations.ipfs_accelerate import improvement_recovery as recovery
from integrations.ipfs_accelerate import improvement_runner as runner


ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True, timeout=20).stdout.strip()


def _unamended_synthetic_spec(source):
    """Undo only the two reviewed recipes in a copy of the test input.

    Production plan progress and Git history must not determine a synthetic
    fixture's starting contract. Partial or unfamiliar amendments are errors.
    """
    spec = deepcopy(compiler.validate_spec(source))
    task = next(item for item in spec["tasks"] if item["id"] == amendment.TASK)
    suffix = " " + amendment.BASELINE_TEST
    guidance = "\n\n" + amendment.GUIDANCE
    has_target = amendment.BASELINE_TEST in task["targets"]
    has_validation = any(amendment.BASELINE_TEST in value for value in task["validation_commands"])
    has_guidance = amendment.GUIDANCE in task["implementation_prompt"]
    if has_target or has_validation or has_guidance:
        if (task["targets"].count(amendment.BASELINE_TEST) != 1
                or task["targets"][-1] != amendment.BASELINE_TEST
                or len(task["validation_commands"]) != 1
                or not task["validation_commands"][0].endswith(suffix)
                or task["implementation_prompt"].count(amendment.GUIDANCE) != 1
                or not task["implementation_prompt"].endswith(guidance)):
            raise ValueError("synthetic source has an incomplete or unfamiliar TUI-02 amendment")
        task["targets"].pop()
        task["validation_commands"][0] = task["validation_commands"][0][:-len(suffix)]
        task["implementation_prompt"] = task["implementation_prompt"][:-len(guidance)]
    release = next(item for item in spec["tasks"] if item["id"] == "CIMP-REL-03")
    original_dependencies = ["CIMP-REL-01", "CIMP-REL-02", "CIMP-OPS-06"]
    from integrations.ipfs_accelerate import improvement_release_amendment as release_amendment
    has_phase = release_amendment.PRE_ADMISSION_COMMAND in release["validation_commands"]
    has_release_guidance = release_amendment.GUIDANCE in release["implementation_prompt"]
    if has_phase or has_release_guidance:
        suffix = "\n\n" + release_amendment.GUIDANCE
        if (release["depends_on"] != original_dependencies + ["CIMP-TUI-12"]
                or len(release["validation_commands"]) != 2
                or release["validation_commands"][1] != release_amendment.PRE_ADMISSION_COMMAND
                or release["implementation_prompt"].count(release_amendment.GUIDANCE) != 1
                or not release["implementation_prompt"].endswith(suffix)):
            raise ValueError("synthetic source has an incomplete release phase amendment")
        release["validation_commands"][1] = release_amendment.SCRIPT_COMMAND
        release["implementation_prompt"] = release["implementation_prompt"][:-len(suffix)]
    if release["depends_on"] == original_dependencies + ["CIMP-TUI-12"]:
        release["depends_on"] = original_dependencies
    elif release["depends_on"] != original_dependencies:
        raise ValueError("synthetic source has an unfamiliar release dependency amendment")
    return compiler.validate_spec(spec)


@pytest.fixture
def stopped(tmp_path, monkeypatch):
    _, native = runner._native_modules(ROOT)
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "--quiet")
    _git(root, "-c", "user.name=Synthetic", "-c", "user.email=test@example.invalid",
         "commit", "--allow-empty", "-m", "Synthetic source revision")
    spec = root / compiler.SPEC_RELATIVE
    spec.parent.mkdir(parents=True)
    spec.write_text(json.dumps(_unamended_synthetic_spec(compiler.load_spec(ROOT / compiler.SPEC_RELATIVE))))
    generated = compiler.generate(spec, root)
    board = root / compiler.BOARD_RELATIVE
    board.write_text(board.read_text().replace("- Status: todo", "- Status: completed", 1))
    raw = board.read_bytes()
    blocks = amendment._blocks(raw)
    extra = b"- Operator opaque field: keep  two spaces; \xe2\x98\x83\n"
    board.write_bytes(raw.replace(blocks[amendment.TASK], blocks[amendment.TASK].replace(
        b"- Status: todo\n", b"- Status: todo\n" + extra, 1), 1))
    baseline = root / amendment.BASELINE_RECEIPT
    baseline.write_text('{"historical_only":true,"never_rewrite":"receipt"}\n')
    base = tmp_path / "campaign"
    state = base / "epochs/fixed-capacity"
    state.mkdir(parents=True, mode=0o700)
    base.chmod(0o700)
    for key in ("IPFS_ACCELERATE_AGENT_CONTROL_DUCKDB", "IPFS_ACCELERATE_AGENT_CONTROL_DUCKLAKE",
                "IPFS_ACCELERATE_AGENT_QUACK_ENDPOINT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(runner.ORCHESTRATION_DIR_ENV, str(state / "control-plane"))
    quarantine = tmp_path / "immutable-old-quarantine.json"
    quarantine.write_text('{"old_quarantine":"retained"}\n')
    quarantine.chmod(0o600)
    plan_id = generated["receipt"]["plan_id"]
    origin = {"schema": recovery.SCHEMA, "repo_root": str(root), "plan_id": plan_id,
        "new_state_dir": str(state), "quarantine_path": str(quarantine),
        "quarantine_sha256": recovery._digest(quarantine.read_bytes()),
        "old_quarantine_released": False, "completion_authority": False,
        "attempt_refunded": False, "candidate_adoption_authority": False,
        "evidence_reuse_authority": False}
    runner._atomic_json(state / recovery.RECEIPT_NAME, origin)
    runner._atomic_json(base / "active_epoch.json", {"schema": recovery.POINTER_SCHEMA,
        "repo_root": str(root), "plan_id": plan_id, "epoch": "epochs/fixed-capacity",
        "recovery_receipt_sha256": recovery._digest((state / recovery.RECEIPT_NAME).read_bytes())})
    runner._atomic_json(state / "launcher.json", {"repo_root": str(root), "plan_id": plan_id,
        "status": "stopped", "identity": {}, "merge_target": "synthetic-main"})
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_supervisor_status.json",
        {"status": "stopped", "managed_daemon_cleanup": {"quiesced": True}})
    tasks = {task.task_id: task for task in native.parse_task_file(board, runner.TASK_PREFIX)}
    assert tasks[amendment.BASELINE_TASK].canonical_task_cid == amendment.BASELINE_CID
    from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import checkout_repository_id
    from ipfs_accelerate_py.agent_supervisor.merge.merge_queue import MergeQueue
    queue = MergeQueue(state / "merge-queue", target_repository_id=checkout_repository_id(root),
                       target_branch="synthetic-main", require_target_binding=True)
    queue.enqueue(branch_name="historical-completed-candidate", task_id=amendment.BASELINE_TASK,
                  canonical_task_cid=amendment.BASELINE_CID,
                  metadata={"schema": "ipfs_accelerate_py/agent-supervisor/merge-candidate@3",
                            "completion_task_cids": {amendment.BASELINE_TASK: amendment.BASELINE_CID}})
    claimed = queue.dequeue(consumer_id="synthetic-completion")
    assert claimed is not None
    queue.complete(claimed, metadata={"historical_only": True})
    with recovery._native_environment(state):
        native.PortalTaskState(implementation_attempts={amendment.BASELINE_TASK: 4},
            implementation_attempts_by_cid={amendment.BASELINE_CID: 4},
            completed_task_ids=[amendment.BASELINE_TASK],
            task_statuses={amendment.BASELINE_TASK: "completed", amendment.TASK: "todo"},
            task_identities={key: {"canonical_task_cid": value.canonical_task_cid} for key, value in tasks.items()},
            retry_budget_repair_receipts={amendment.BASELINE_TASK: "historic-unmodified"}).save(
                state / f"{runner.STATE_PREFIX}_task_state.json")

    def native_read(_root, path, **_kwargs):
        # Real native authoritative read; no .load(create=True), mock payload,
        # state serialization or count repair is used by the amendment.
        from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
        with recovery._native_environment(path.parent):
            payload = plane.read_task_state_payload(path)
        return payload, {"source": "native_control_plane"}

    monkeypatch.setattr(runner, "_read_native_state", native_read)
    monkeypatch.setattr(amendment, "_assert_containers_quiescent", lambda _state:
        {"running_matching_containers": 0, "stopped_container_ids": []})
    return {"root": root, "spec": spec, "board": board, "base": base, "state": state,
            "baseline": baseline, "quarantine": quarantine, "native": native,
            "tasks": tasks, "read": native_read, "queue": queue}


def _review(context):
    return amendment.review_tui_baseline_amendment(context["root"], context["spec"], context["base"],
        baseline_receipt_sha256=recovery._digest(context["baseline"].read_bytes()))


def _apply(context, expected=None):
    return amendment.apply_tui_baseline_amendment(context["root"], context["spec"], context["base"],
        expected=expected or _review(context))


def _state(context):
    return context["read"](context["root"], context["state"] / f"{runner.STATE_PREFIX}_task_state.json")[0]


def _change_native(context, **changes):
    path = context["state"] / f"{runner.STATE_PREFIX}_task_state.json"
    with recovery._native_environment(context["state"]):
        state = context["native"].PortalTaskState.load(path)
        for key, value in changes.items():
            setattr(state, key, value)
        state.save(path)


def test_snapshot_parser_uses_actual_production_namespace_and_first_cid():
    _, native = runner._native_modules(ROOT)
    board = ROOT / compiler.BOARD_RELATIVE
    actual = {task.task_id: task for task in native.parse_task_file(board, runner.TASK_PREFIX)}
    snapshot = amendment._tasks(native, ROOT, board.read_bytes())
    assert snapshot[amendment.BASELINE_TASK].canonical_task_cid == amendment.BASELINE_CID
    for key, task in actual.items():
        assert snapshot[key].canonical_task_cid == task.canonical_task_cid
        assert snapshot[key].canonical_task_key == task.canonical_task_key
        assert snapshot[key].board_namespace == task.board_namespace


def test_real_native_amendment_changes_one_pending_cid_and_preserves_all_history(stopped):
    old_board = stopped["board"].read_bytes()
    old_native = _state(stopped)
    queue_bytes = {path: path.read_bytes() for path in (stopped["state"] / "merge-queue").rglob("*") if path.is_file()}
    immutable = [stopped["baseline"], stopped["quarantine"], stopped["state"] / recovery.RECEIPT_NAME]
    old_bytes = {path: path.read_bytes() for path in immutable}
    old_blocks = amendment._blocks(old_board)
    expected = _review(stopped)
    assert stopped["board"].read_bytes() == old_board
    assert _state(stopped) == old_native
    assert {path: path.read_bytes() for path in queue_bytes} == queue_bytes
    receipt = _apply(stopped, expected)
    assert _state(stopped) == old_native
    assert {path: path.read_bytes() for path in immutable} == old_bytes
    assert receipt["preserved_attempts"]["implementation_attempts"] == {amendment.BASELINE_TASK: 4}
    assert receipt["preserved_completed_task_ids"] == [amendment.BASELINE_TASK]
    assert receipt["merge_queue_settlement"]["status_counts"]["completed"] == 1
    assert all(receipt[key] is False for key in amendment._NO_AUTHORITY)
    assert recovery.resolve_active_epoch(stopped["root"], stopped["spec"], stopped["base"]) == stopped["state"]
    new_blocks = amendment._blocks(stopped["board"].read_bytes())
    assert all(new_blocks[key] == value for key, value in old_blocks.items() if key != amendment.TASK)
    assert b"- Operator opaque field: keep  two spaces; \xe2\x98\x83\n" in new_blocks[amendment.TASK]
    assert "Migrate the live TUI baseline" in new_blocks[amendment.TASK].decode()
    _, native = runner._native_modules(stopped["root"])
    after = {task.task_id: task for task in native.parse_task_file(stopped["board"], runner.TASK_PREFIX)}
    assert [key for key in after if after[key].canonical_task_cid != stopped["tasks"][key].canonical_task_cid] == [amendment.TASK]
    assert {key: task.status for key, task in after.items()} == {key: task.status for key, task in stopped["tasks"].items()}
    assert after[amendment.BASELINE_TASK].canonical_task_cid == amendment.BASELINE_CID
    assert after[amendment.TASK].validation[0].endswith("tests/test_tui_narrative_capture.py " + amendment.BASELINE_TEST)
    # Ordinary compilation now accepts the amended identity and preserves the
    # completed status and every unknown runtime field byte-for-byte.
    before_generate = stopped["board"].read_bytes()
    result = compiler.generate(stopped["spec"], stopped["root"])
    assert result["receipt"]["plan_id"] == receipt["new_plan_id"]
    assert result["receipt"]["tasks_completed_by_ingestion"] == 0
    assert stopped["board"].read_bytes() == before_generate
    assert _state(stopped) == old_native


@pytest.mark.parametrize("changes", [
    {"implementation_attempts": {amendment.TASK: 1, amendment.BASELINE_TASK: 4}},
    {"implementation_in_progress": True, "active_task_id": amendment.TASK},
    {"blocked_task_ids": [amendment.TASK]},
    {"completed_task_ids": [amendment.BASELINE_TASK, amendment.TASK]},
    {"protected_implementation_attempts": {amendment.TASK: {"attempt": 1}}},
])
def test_attempted_active_held_or_completed_native_task_cannot_be_amended(stopped, changes):
    expected = _review(stopped)
    _change_native(stopped, **changes)
    original = stopped["spec"].read_bytes()
    with pytest.raises(ValueError, match="active|completed|held|consumed"):
        _apply(stopped, expected)
    assert stopped["spec"].read_bytes() == original


@pytest.mark.parametrize("key", ["spec", "plan", "board", "pointer", "source_head"])
def test_exact_reviewed_sources_and_pointer_use_compare_and_swap(stopped, key):
    expected = _review(stopped)
    if key == "source_head":
        _git(stopped["root"], "-c", "user.name=Synthetic", "-c", "user.email=test@example.invalid",
             "commit", "--allow-empty", "-m", "A later source revision")
    else:
        path = {"spec": stopped["spec"], "plan": stopped["root"] / compiler.PLAN_RELATIVE,
                "board": stopped["board"], "pointer": stopped["base"] / "active_epoch.json"}[key]
        path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="CAS inputs"):
        _apply(stopped, expected)
    assert json.loads((stopped["base"] / "active_epoch.json").read_text())["schema"] == recovery.POINTER_SCHEMA


def test_native_claim_and_native_maintenance_owner_are_not_removed(stopped):
    expected = _review(stopped)
    _, native = runner._native_modules(stopped["root"])
    facade = object.__new__(native.PortalImplementationDaemon)
    facade.repo_root = stopped["root"]
    claim = facade._implementation_task_claim_path(amendment.TASK, canonical_task_cid=expected["old_task_cid"])
    claim.parent.mkdir(parents=True, exist_ok=True)
    claim.write_text('{"pid":1,"protected":"must remain even if stale"}')
    with pytest.raises(ValueError, match="existing native claim"):
        _apply(stopped, expected)
    assert claim.read_text() == '{"pid":1,"protected":"must remain even if stale"}'
    claim.unlink()  # Only the test removes its synthetic fixture claim.
    from ipfs_accelerate_py.agent_supervisor.merge import checkout_lock as locks
    maintenance = locks.board_scoped_protected_path_maintenance_lock_path(stopped["root"], "complaint-intake-improvement")
    maintenance.write_text('{"pid":1,"lease_id":"synthetic-retained"}')
    with pytest.raises(ValueError, match="maintenance or merge owner"):
        _apply(stopped, expected)
    assert maintenance.read_text() == '{"pid":1,"lease_id":"synthetic-retained"}'


def test_native_daemon_recognizes_amendment_leases_as_current_owners(stopped):
    from ipfs_accelerate_py.agent_supervisor.merge import checkout_lock as locks
    native = stopped["native"]
    facade = object.__new__(native.PortalImplementationDaemon)
    facade.repo_root = stopped["root"]
    maintenance = locks.board_scoped_protected_path_maintenance_lock_path(stopped["root"], "complaint-intake-improvement")
    merge = locks.board_scoped_checkout_mutation_lock_path(stopped["root"], "complaint-intake-improvement")
    with amendment._native_maintenance(stopped["root"]):
        assert facade._lock_owner_is_active(json.loads(maintenance.read_text()),
                                           expected_kind="implementation-protected-maintenance")
        assert facade._merge_lock_owner_is_active(json.loads(merge.read_text()))
    assert not maintenance.exists() and not merge.exists()


def test_pending_native_queue_is_refused_and_completed_history_is_retained(stopped):
    queue = stopped["queue"]
    queue.enqueue(branch_name="unsettled", task_id=amendment.TASK,
                  canonical_task_cid=stopped["tasks"][amendment.TASK].canonical_task_cid)
    before = (stopped["state"] / "merge-queue/merge_queue.duckdb").read_bytes()
    with pytest.raises(ValueError, match="pending or processing"):
        _apply(stopped)
    assert (stopped["state"] / "merge-queue/merge_queue.duckdb").read_bytes() == before
    assert queue.pending_count() == 1


def test_snapshot_parent_symlink_cannot_write_outside_campaign(stopped, tmp_path):
    outside = tmp_path / "outside-amendments"
    outside.mkdir(mode=0o700)
    (stopped["base"] / "amendments").symlink_to(outside, target_is_directory=True)
    before = stopped["spec"].read_bytes()
    with pytest.raises(ValueError, match="cannot traverse symlinks"):
        _apply(stopped)
    assert list(outside.iterdir()) == []
    assert stopped["spec"].read_bytes() == before


def test_actual_live_recorded_owner_and_unavailable_container_inventory_refuse(stopped, monkeypatch):
    path = stopped["state"] / "launcher.json"
    record = json.loads(path.read_text())
    record["identity"] = runner.process_identity(os.getpid())
    runner._atomic_json(path, record)
    with pytest.raises(ValueError, match="still alive"):
        _apply(stopped)
    record["identity"] = {}
    runner._atomic_json(path, record)
    def unavailable(_state):
        raise ValueError("Docker state unavailable")
    monkeypatch.setattr(amendment, "_assert_containers_quiescent", unavailable)
    with pytest.raises(ValueError, match="Docker state unavailable"):
        _apply(stopped)


@pytest.mark.parametrize("which", ["origin", "snapshot", "receipt", "baseline", "traversal", "current_plan", "current_board"])
def test_published_chain_fails_closed_on_changed_evidence(stopped, which):
    _apply(stopped)
    pointer_path = stopped["base"] / "active_epoch.json"
    pointer = json.loads(pointer_path.read_text())
    directory = (stopped["base"] / pointer["amendment"]).parent
    if which == "traversal":
        pointer["amendment"] = "amendments/../receipt.json"
        runner._atomic_json(pointer_path, pointer)
    elif which == "current_board":
        stopped["board"].write_bytes(stopped["board"].read_bytes().replace(
            b"- Outputs: ", b"- Outputs: unauthorized.py, ", 1))
    elif which == "current_plan":
        plan_path = stopped["root"] / compiler.PLAN_RELATIVE
        value = json.loads(plan_path.read_text())
        value["metadata"]["title"] = "A different formal contract"
        plan_path.write_text(json.dumps(value))
    else:
        target = {"origin": stopped["state"] / recovery.RECEIPT_NAME,
                  "snapshot": directory / "old_board.snapshot", "receipt": directory / "receipt.json",
                  "baseline": stopped["baseline"]}[which]
        target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="amendment|amended|original recovery"):
        recovery.resolve_active_epoch(stopped["root"], stopped["spec"], stopped["base"])


def test_pointer_allows_later_status_and_unknown_note_changes(stopped):
    _apply(stopped)
    raw = stopped["board"].read_bytes()
    blocks = amendment._blocks(raw)
    updated = blocks[amendment.TASK].replace(b"- Status: todo\n",
        b"- Status: completed\n- New runtime note: retained later state\n", 1)
    stopped["board"].write_bytes(raw.replace(blocks[amendment.TASK], updated, 1))
    assert recovery.resolve_active_epoch(stopped["root"], stopped["spec"], stopped["base"]) == stopped["state"]


def test_manual_hold_board_field_and_changed_completed_contract_are_rejected(stopped):
    original = stopped["board"].read_bytes()
    blocks = amendment._blocks(original)
    stopped["board"].write_bytes(original.replace(blocks[amendment.TASK],
        blocks[amendment.TASK].replace(b"- Status: todo\n", b"- Status: todo\n- Manual hold: true\n"), 1))
    with pytest.raises(ValueError, match="completed baseline identity"):
        _review(stopped)
    stopped["board"].write_bytes(original.replace(b"## CIMP-TUI-01 ", b"## CIMP-TUI-01 Altered ", 1))
    with pytest.raises(ValueError, match="old native board contract"):
        _review(stopped)


def test_native_event_history_and_completed_source_identity_are_required(stopped):
    events = stopped["state"] / f"{runner.STATE_PREFIX}_events.jsonl"
    events.write_text(json.dumps({"type": "implementation_provider_started", "task_id": amendment.TASK}) + "\n")
    events.chmod(0o600)
    with pytest.raises(ValueError, match="execution history"):
        _apply(stopped)
    events.unlink()
    identities = _state(stopped)["task_identities"]
    identities[amendment.BASELINE_TASK]["canonical_task_cid"] = "different-completed-revision"
    _change_native(stopped, task_identities=identities)
    with pytest.raises(ValueError, match="completed baseline source identity"):
        _apply(stopped)


def test_stale_dependency_projection_preserved_with_canonical_queue_completion(stopped):
    _change_native(stopped, completed_task_ids=[], task_statuses={amendment.BASELINE_TASK: "ready", amendment.TASK: "waiting"})
    before = _state(stopped)
    receipt = _apply(stopped)
    assert _state(stopped) == before
    assert receipt["preserved_completed_task_ids"] == []


def test_unversioned_queue_completion_cannot_authorize_amendment(stopped):
    # Replace only the synthetic fixture store: no production helper does this.
    from ipfs_accelerate_py.agent_supervisor.task_sources.duckdb_state import open_duckdb_connection
    with open_duckdb_connection(stopped["state"] / "merge-queue/merge_queue.duckdb") as connection:
        connection.execute("UPDATE merge_requests SET metadata_json=json_merge_patch(metadata_json, ?) WHERE status='completed'",
                           ('{"schema":"unversioned"}',))
    with pytest.raises(ValueError, match="versioned native queue completion"):
        _apply(stopped)


@pytest.mark.parametrize("line", ["not-json\n", "[]\n"])
def test_unknown_native_event_history_is_not_absence(stopped, line):
    events = stopped["state"] / f"{runner.STATE_PREFIX}_events.jsonl"
    events.write_text(line)
    events.chmod(0o600)
    with pytest.raises(ValueError, match="history is malformed"):
        _apply(stopped)


def test_interrupted_publication_keeps_native_evidence_and_refuses_startup(stopped, monkeypatch):
    native_before = _state(stopped)
    preserved = [stopped["baseline"], stopped["quarantine"], stopped["state"] / recovery.RECEIPT_NAME]
    bytes_before = {path: path.read_bytes() for path in preserved}
    writer = amendment._write
    def fail_before_plan(path, raw, **kwargs):
        if path == stopped["root"] / compiler.PLAN_RELATIVE:
            raise OSError("synthetic publication interruption")
        return writer(path, raw, **kwargs)
    monkeypatch.setattr(amendment, "_write", fail_before_plan)
    with pytest.raises(OSError, match="publication interruption"):
        _apply(stopped)
    with pytest.raises(ValueError, match="plan binding"):
        recovery.resolve_active_epoch(stopped["root"], stopped["spec"], stopped["base"])
    assert _state(stopped) == native_before
    assert {path: path.read_bytes() for path in preserved} == bytes_before
    assert len(list((stopped["base"] / "amendments").glob("*/receipt.json"))) == 1


@pytest.mark.parametrize("running", [True, None])
def test_read_only_docker_probe_rejects_live_or_unknown_matching_container(tmp_path, monkeypatch, running):
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner as runtime
    identifier = "a" * 64
    state = tmp_path / "campaign"
    calls = []
    monkeypatch.setattr(runtime, "_docker_isolation_binary", lambda: "/usr/bin/docker")
    def observe(argv, **kwargs):
        calls.append(argv)
        if "ps" in argv:
            value = identifier + "\n"
        else:
            value = json.dumps({"Id": identifier, "Running": running,
                "Mounts": [{"Type": "bind", "Source": str(state / "worktrees/workspace_owned")}]})
        return subprocess.CompletedProcess(argv, 0, value, "")
    monkeypatch.setattr(amendment.subprocess, "run", observe)
    with pytest.raises(ValueError, match="running or unknown"):
        amendment._assert_containers_quiescent(state)
    assert all("stop" not in call and "rm" not in call for call in calls)
