"""Explicit synthetic boundary fixtures; these never prove real completion."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import release_evidence as bridge


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _synthetic_pin(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_current_qualification_absence_does_no_spec_or_native_work(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("absent qualification must not consult this boundary")
    monkeypatch.setattr(bridge, "_directory", forbidden)
    monkeypatch.setattr(bridge.compiler, "load_spec", forbidden)
    monkeypatch.setattr(bridge, "_verify_current_release_qualification", forbidden)
    # An arbitrary author JSON elsewhere has no effect on the fixed slot.
    _write(tmp_path / "author-evidence.json", {"accepted": True, "completion_authority": True})
    assert bridge.read_current_release_qualification(tmp_path / "missing-source", tmp_path / "missing-spec",
        tmp_path / "missing-campaign", phase="pre-admission") is None


def test_current_qualification_rejects_flags_in_fixed_slot_before_native_work(tmp_path, monkeypatch):
    root, state = tmp_path / "source", tmp_path / "campaign"
    root.mkdir(mode=0o700)
    state.mkdir(mode=0o700)
    (state / "host-acceptance").mkdir(mode=0o700)
    _write(state / "host-acceptance" / bridge._CURRENT_BINDING_NAME,
        {"schema": "author-claims-current", "accepted": True, "completion_authority": True})
    monkeypatch.setattr(bridge.compiler, "load_spec", lambda *_: pytest.fail("malformed slot must fail before spec work"))
    with pytest.raises(bridge.ReleaseEvidenceError, match="host_binding_contract"):
        bridge.read_current_release_qualification(root, root / bridge.compiler.SPEC_RELATIVE, state, phase="pre-admission")


@pytest.mark.parametrize("damage", ["symlink", "hardlink", "public_file", "public_directory"])
def test_current_fixed_binding_requires_owned_private_nonalias_slot(tmp_path, damage):
    root, state = tmp_path / "source", tmp_path / "campaign"
    root.mkdir(mode=0o700)
    state.mkdir(mode=0o700)
    directory = state / "host-acceptance"
    directory.mkdir(mode=0o700)
    path = directory / bridge._CURRENT_BINDING_NAME
    _write(path, {"schema": "explicit-invalid-unit-binding"})
    if damage == "symlink":
        path.rename(directory / "other.json")
        path.symlink_to(directory / "other.json")
    elif damage == "hardlink":
        import os
        os.link(path, directory / "other.json")
    elif damage == "public_file":
        path.chmod(0o644)
    else:
        directory.chmod(0o755)
    with pytest.raises(bridge.ReleaseEvidenceError):
        bridge.read_current_release_qualification(root, root / bridge.compiler.SPEC_RELATIVE, state, phase="pre-admission")


def test_current_plan_is_finite_serial_exact_whole_module_partition(tmp_path):
    manifest = {name: [f"tests/test_explicit_fake_{name}_{index:02d}.py" for index in range(count)]
        for name, count in (("application", 65), ("lifecycle", 16), ("replica", 2))}
    plan = bridge._current_shard_plan(manifest, tmp_path)
    assert plan == bridge._current_shard_plan(deepcopy(manifest), tmp_path)
    shards = plan["shards"]
    assert len(shards) == 22 and plan["serial"] is True and plan["retries"] == 0
    assert plan["per_shard_budget_seconds"] == 900
    assert all(1 <= len(row["modules"]) <= 4 and row["budget_seconds"] == 900 for row in shards)
    assert [module for row in shards for module in row["modules"]] == [module for group in manifest.values() for module in group]
    assert all(" -k " not in row["command"] and "::" not in row["command"] for row in shards)
    manifest["replica"][0] = manifest["application"][0]
    with pytest.raises(bridge.ReleaseEvidenceError, match="module_identity"):
        bridge._current_shard_plan(manifest, tmp_path)


def test_current_source_empty_file_valid_but_empty_evidence_invalid(tmp_path):
    path = tmp_path / "__init__.py"
    path.touch(mode=0o600)
    assert bridge._current_file(path, source=True) == b""
    with pytest.raises(bridge.ReleaseEvidenceError):
        bridge._current_file(path)


def test_current_measurement_scope_cannot_omit_explicit_report_or_dependency():
    expected = {"snapshot": {"files": {"product.py": {"sha256": "a" * 64},
        "docs/report.json": {"sha256": "b" * 64}},
        "dependencies": {"external/explicit-fake": {"gitlink": "c" * 40, "scope": "opaque_gitlink_identity_only"}}}}
    measured = {"files": deepcopy(expected["snapshot"]["files"]),
        "dependencies": {"external/explicit-fake": {"gitlink": "c" * 40, "head": "unavailable"}}}
    bridge._current_measurement_snapshot(measured, expected)
    without_report = deepcopy(measured)
    del without_report["files"]["docs/report.json"]
    with pytest.raises(bridge.ReleaseEvidenceError, match="source_changed"):
        bridge._current_measurement_snapshot(without_report, expected)
    without_dependency = deepcopy(measured)
    without_dependency["dependencies"] = {}
    with pytest.raises(bridge.ReleaseEvidenceError, match="dependency_population"):
        bridge._current_measurement_snapshot(without_dependency, expected)


@pytest.fixture
def explicit_staged_native_catalog(tmp_path):
    """Real Native catalog mechanics over explicit temporary fake test source."""
    from integrations.ipfs_datasets.loader import ensure_import_paths
    ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
    from ipfs_accelerate_py.testing import pytest_ast_seal as native
    root = tmp_path / "synthetic-source"
    root.mkdir(mode=0o700)
    (root / "tests").mkdir(mode=0o700)
    (root / ".git").mkdir(mode=0o700)
    (root / "conftest.py").touch(mode=0o600)
    (root / "product.py").write_text("VALUE = 1\n")
    relative = "tests/test_explicit_fake_staged.py"
    (root / relative).write_text("import product\ndef test_synthetic():\n    assert product.VALUE == 1\n")
    required = [relative + "::test_synthetic"]
    closure = native.ast_closure(root, root / relative)
    assert closure
    catalogs = {}
    for mode in ("collect", "run"):
        path = tmp_path / (mode + ".duckdb")
        oracle = native.DuckDbQuackSealOracle(path)
        seal = native.seal_files(closure, oracle)
        if mode == "run":
            oracle.remember(required[0], seal.digest, file_count=len(seal.files))
        oracle.close()
        path.chmod(0o600)
        catalogs[mode] = path
    return SimpleNamespace(root=root, native=native, required=required, closures={relative: closure}, catalogs=catalogs)


def _reprove_fake_catalog(context, mode="run"):
    return bridge._current_catalog(context.catalogs[mode], collection_only=mode == "collect",
        required=context.required, current_root=context.root, execution_root=context.root,
        native=context.native, closures=context.closures, hashes={})


def test_current_catalog_rederives_actual_native_hash_and_empty_source(explicit_staged_native_catalog):
    context = explicit_staged_native_catalog
    _reprove_fake_catalog(context, "collect")
    _reprove_fake_catalog(context)
    (context.root / "product.py").write_text("VALUE = 2\n")
    with pytest.raises(bridge.ReleaseEvidenceError, match="catalog_source_changed"):
        _reprove_fake_catalog(context)


@pytest.mark.parametrize("damage", ["seal", "authority", "missing_pass", "extra_pass", "collect_pass"])
def test_current_catalog_rejects_forged_incomplete_or_reused_passes(explicit_staged_native_catalog, damage):
    import duckdb
    context = explicit_staged_native_catalog
    mode = "collect" if damage == "collect_pass" else "run"
    database = duckdb.connect(str(context.catalogs[mode]), config={"threads": 1})
    try:
        if damage == "seal":
            database.execute("UPDATE pytest_ast_seal SET seal=?", ["0" * 64])
        elif damage == "authority":
            database.execute("UPDATE pytest_ast_seal SET completion_authority=TRUE")
        elif damage == "missing_pass":
            database.execute("DELETE FROM pytest_ast_seal")
        else:
            database.execute("INSERT INTO pytest_ast_seal VALUES (?, ?, 1, 'explicit-synthetic-time', FALSE)",
                ["tests/test_explicit_fake_staged.py::never_executed", "0" * 64])
    finally:
        database.close()
    with pytest.raises(bridge.ReleaseEvidenceError):
        _reprove_fake_catalog(context, mode)


@pytest.fixture
def explicit_staged_shard(explicit_staged_native_catalog, tmp_path):
    """Synthetic process reports plus real temporary Native catalog rows.

    These values deliberately do not establish actual process execution or
    Native campaign completion. They exercise the pure consumer's boundaries.
    """
    import shutil
    import sys
    from integrations.ipfs_accelerate.release_guard import checker
    from ipfs_accelerate_py.agent_supervisor.validation import validation_runtime as runtime
    context = explicit_staged_native_catalog
    evidence = tmp_path / "explicit-fake-producer"
    run = evidence / "shard-000" / "measurements" / "measured-explicit-fake"
    for directory in (evidence, evidence / "shard-000", evidence / "shard-000" / "measurements", run):
        directory.mkdir(mode=0o700)
    interpreter_sha, interpreter_stat = runtime._validation_python_interpreter_identity(sys.executable)
    mode = runtime._validation_python_launcher_mode(sealed=True)
    policy = runtime._validation_python_launcher_policy_sha256(mode)
    runtime_identity = {"interpreter_sha256": interpreter_sha, "interpreter_stat": interpreter_stat,
                        "launcher_mode": mode, "launcher_policy_sha256": policy}
    launcher = {"sealed": True, "mode": mode, "content_sha256": "a" * 64,
                "interpreter_sha256": interpreter_sha, "interpreter_stat": interpreter_stat, "policy_sha256": policy}
    imported = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in context.closures[context.required[0].split("::")[0]]}
    source = {"files": {str(path.relative_to(context.root)): {"sha256": digest} for path, digest in
        ((Path(name), value) for name, value in imported.items())}, "dependencies": {}}
    current = {"snapshot": deepcopy(source), "runtime_identity": runtime_identity}
    for phase in ("collect", "run"):
        shutil.copyfile(context.catalogs[phase], run / (phase + ".duckdb"))
        (run / (phase + ".duckdb")).chmod(0o600)
        _write(run / (phase + ".json"), {"schema": "complaint-pytest-observation@1", "exitstatus": 0,
            "nodeids": context.required, "reports": [] if phase == "collect" else [
                {"nodeid": context.required[0], "when": when, "outcome": "passed"} for when in ("setup", "call", "teardown")],
            "completion_authority": False})
        _write(run / (phase + "-native-result.json"), {"returncode": 0, "validation_python_launcher": launcher,
            "owned_process_cleanup": {"quiescent": True, "canonical_native_delegate": True}})
        _write(run / (phase + ".guard.json"), {"schema": "complaint-release-effect-guard@1", "exitstatus": 0,
            "network_process_dispatch_permitted": False, "kernel_network_deny": True, "provider_process_deny": True,
            "guard_load_order": "explicit_first_plugin_before_product_imports", "private_namespace": str(evidence / "shard-000"),
            "imported_source_hashes": imported})
    import xml.etree.ElementTree as ET
    xml = ET.Element("testsuites")
    properties = ET.SubElement(ET.SubElement(xml, "testcase"), "properties")
    ET.SubElement(properties, "property", name="complaint_nodeid", value=context.required[0])
    (run / "junit.xml").write_bytes(ET.tostring(xml))
    (run / "junit.xml").chmod(0o600)
    shard = {"id": "shard-000", "modules": [context.required[0].split("::")[0]], "command": "explicit synthetic command"}
    cases = [{"nodeid": context.required[0], "outcome": "passed"}]
    measured = {"schema": "complaint-owned-behavioral-measurement@1", "reason": "", "source_unchanged": True,
        "source_before": deepcopy(source), "source_after": deepcopy(source), "completion_authority": False,
        "workspace_path": str(context.root), "run_path": str(run), "required_nodeids": context.required, "cases": cases,
        "observation_binding": {"required_nodeids": context.required, "command": shard["command"], "collected_count": 1,
            "exit_status": 0, "timed_out": False, "cases": cases},
        "trusted_executor": {"qualname": "_owned_native_runner", "canonical_native_identity": False},
        "results": [{"mode": phase, "returncode": 0, "timed_out": False, "validation_python_launcher": launcher}
                    for phase in ("collect", "run")]}
    def refresh():
        measured["artifacts"] = [_synthetic_pin(run / name) for name in ("collect.json", "collect.duckdb", "collect-native-result.json",
            "collect.guard.json", "run.json", "run.duckdb", "run-native-result.json", "run.guard.json", "junit.xml")]
        _write(run / "measurement.json", measured)
        return _synthetic_pin(run / "measurement.json")
    def reprove():
        return bridge._current_reprove_shard(context.root, context.root, evidence, refresh(), shard, current,
            checker, context.native, context.closures, {})
    return SimpleNamespace(context=context, run=run, reprove=reprove, measured=measured, refresh=refresh)


def test_current_shard_pure_reproof_keeps_fake_process_claims_non_authoritative(explicit_staged_shard):
    fixture = explicit_staged_shard
    result = fixture.reprove()
    assert result["required_nodeids"] == fixture.context.required
    assert result["completion_authority"] is False
    assert "native_completion_satisfied" not in result


@pytest.mark.parametrize("damage", ["skip", "missing_teardown", "junit_skip", "kernel_guard", "cleanup", "runtime_policy", "imported_hash"])
def test_current_shard_rejects_reauthored_bad_phase_artifacts(explicit_staged_shard, damage):
    fixture = explicit_staged_shard
    if damage in {"skip", "missing_teardown"}:
        path = fixture.run / "run.json"
        value = json.loads(path.read_bytes())
        if damage == "skip":
            value["reports"][1]["outcome"] = "skipped"
        else:
            value["reports"].pop()
        _write(path, value)
    elif damage == "junit_skip":
        import xml.etree.ElementTree as ET
        path = fixture.run / "junit.xml"
        tree = ET.fromstring(path.read_bytes())
        ET.SubElement(next(tree.iter("testcase")), "skipped")
        path.write_bytes(ET.tostring(tree))
    elif damage in {"kernel_guard", "imported_hash"}:
        path = fixture.run / "run.guard.json"
        value = json.loads(path.read_bytes())
        if damage == "kernel_guard":
            value["kernel_network_deny"] = False
        else:
            value["imported_source_hashes"][str(fixture.context.root / "product.py")] = "0" * 64
        _write(path, value)
    else:
        path = fixture.run / "run-native-result.json"
        value = json.loads(path.read_bytes())
        if damage == "cleanup":
            value["owned_process_cleanup"]["quiescent"] = False
        else:
            value["validation_python_launcher"]["policy_sha256"] = "0" * 64
        _write(path, value)
    # Even re-pinning every edited synthetic artifact cannot make the reader
    # accept failed/skipped/missing phases, stale imports or invalid boundaries.
    with pytest.raises(bridge.ReleaseEvidenceError):
        fixture.reprove()


def test_current_runtime_preserves_actual_native_active_venv_approval(tmp_path):
    """Use the actual approved Native roots, including Data's VENV when active.

    User-owned installed package roots are commonly owner-writable. This does
    not modify their permissions or rediscover an installation by pathname.
    """
    import os
    import stat
    from integrations.ipfs_accelerate.release_guard import checker
    root = Path(bridge.__file__).resolve().parents[2]
    environment = checker._validation_environment(root, tmp_path)
    selected = sorted({entry for entry in environment["PYTHONPATH"].split(os.pathsep)
        if Path(entry).name in {"site-packages", "dist-packages"}})
    assert selected
    before = {entry: (Path(entry).stat().st_uid, stat.S_IMODE(Path(entry).stat().st_mode)) for entry in selected}
    # The exact trusted Host handoff and independently Native-approved current
    # context must rederive the same runtime; no extra owner-write ban applies.
    handed_off = bridge._current_runtime_identity(root, checker, validation_environment=environment)
    current = bridge._current_runtime_identity(root, checker)
    assert handed_off == current
    assert current["approved_package_roots"] == selected
    assert current["launcher_mode"] == environment["IPFS_ACCELERATE_VALIDATION_PYTHON_LAUNCHER_MODE"]
    assert before == {entry: (Path(entry).stat().st_uid, stat.S_IMODE(Path(entry).stat().st_mode)) for entry in selected}


def test_current_runtime_rejects_unapproved_same_basename_before_metadata_reads(tmp_path, monkeypatch):
    import os
    import importlib.metadata
    from integrations.ipfs_accelerate.release_guard import checker
    root = Path(bridge.__file__).resolve().parents[2]
    environment = checker._validation_environment(root, tmp_path)
    fake = tmp_path / "unapproved-explicit-fake" / "site-packages"
    fake.mkdir(parents=True, mode=0o700)
    environment["PYTHONPATH"] += os.pathsep + str(fake)
    facade = SimpleNamespace(_validation_environment=lambda *_args: environment,
        native_memfd_approved_paths=checker.native_memfd_approved_paths)
    def forbidden_metadata(*_args, **_kwargs):
        pytest.fail("unapproved runtime root reached distribution metadata reader")
    monkeypatch.setattr(importlib.metadata, "distributions", forbidden_metadata)
    with pytest.raises(bridge.ReleaseEvidenceError, match="runtime_package_root_unapproved"):
        bridge._current_runtime_identity(root, facade)


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path.read_bytes()


def _fake_identity(value):
    body = {key: item for key, item in value.items() if key != "event_id"}
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _fake_native():
    return SimpleNamespace(PortalImplementationDaemon=SimpleNamespace(
        _generated_file_commit_result_trusted=lambda value: value.get("committed") is True),
        content_identity=lambda value: _fake_identity(value))


def _fake_task(task_id="CIMP-FAKE-00"):
    return SimpleNamespace(task_id=task_id, canonical_task_cid="fake-cid-" + task_id,
                           canonical_task_key="fake-key-" + task_id, status="completed")


def _fake_finish(task):
    return {"task_id": task.task_id, "canonical_task_cid": task.canonical_task_cid,
        "canonical_task_key": task.canonical_task_key, "returncode": 0, "validation_passed": True,
        "merged": True, "sequence": 1, "event_id": "fake-event", "behavioral_evidence": [],
        "implementation_commit": "1" * 40, "merge_commit": "2" * 40,
        "todo": {"updated": True, "updated_task_ids": [task.task_id],
            "completion_receipts": [{"schema": "ipfs_accelerate_py.agent_supervisor.member_completion_receipt@1",
                "task_id": task.task_id, "canonical_task_cid": task.canonical_task_cid,
                "canonical_task_key": task.canonical_task_key, "status": "succeeded"}],
            "commit_result": {"committed": True, "commit": "3" * 40}}}


@pytest.mark.parametrize("damage", ["cid", "member_status", "member_duplicate", "board_commit", "missing_member"])
def test_synthetic_callback_rejects_missing_or_wrong_revision_proof(damage):
    task = _fake_task()
    row = _fake_finish(task)
    if damage == "cid":
        row["canonical_task_cid"] = "other-fake-revision"
    elif damage == "member_status":
        row["todo"]["completion_receipts"][0]["status"] = "pending"
    elif damage == "member_duplicate":
        row["todo"]["completion_receipts"] *= 2
    elif damage == "board_commit":
        row["todo"]["commit_result"]["committed"] = False
    else:
        row["todo"]["missing_task_ids"] = ["CIMP-FAKE-OTHER"]
    with pytest.raises(bridge.ReleaseEvidenceError):
        bridge._callback(row, task, _fake_native())


def test_synthetic_historical_measurement_stays_historical_and_is_hash_pinned(tmp_path):
    path = tmp_path / "evidence-runs" / "explicit-fake-run" / "measurement.json"
    source = {"digest": "a" * 64}
    raw = _write(path, {"schema": "complaint-owned-behavioral-measurement@1", "reason": "",
                        "source_unchanged": True, "source_before": source, "source_after": source})
    observation = [{"admitted": True, "measurement_record": {
        "path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}}]
    result = bridge._historical_measurements(tmp_path, observation)
    assert result["status"] == "HISTORICAL"
    assert result["current_source_equivalence"] is False
    assert result["source_after_digests"] == ["a" * 64]
    assert result["artifacts"][0]["sha256"] == hashlib.sha256(raw).hexdigest()
    _write(path, {"schema": "author-edited-fake"})
    with pytest.raises(bridge.ReleaseEvidenceError, match="digest_mismatch"):
        bridge._historical_measurements(tmp_path, observation)


def test_synthetic_receipt_flags_without_owned_measurement_never_suffice(tmp_path):
    with pytest.raises(bridge.ReleaseEvidenceError, match="pin_missing"):
        bridge._historical_measurements(tmp_path, [{"accepted": True, "admitted": True,
            "completion_authority": True, "current_source": True}])


def test_synthetic_journal_projects_only_completion_metadata_and_pins_prefix(tmp_path):
    task = _fake_task()
    finish = _fake_finish(task)
    event = {"sequence": 1, "previous_event_id": "", "stream_id": "fake-stream", "snapshot_id": "fake-snapshot",
        "type": "implementation_finished",
        "task_id": task.task_id, "canonical_task_cid": task.canonical_task_cid,
        "canonical_task_key": task.canonical_task_key, "returncode": 0,
        "implementation_commit": "1" * 40,
        "validation_result": {"passed": True, "behavioral_evidence": [{"admitted": True,
            "measurement_record": {"path": "fake-path", "sha256": "a" * 64},
            "provider_thoughts": "SYNTHETIC-SECRET-SENTINEL"}]},
        "merge_result": {"merged": True, "merge_commit": "2" * 40, "todo_update_result": finish["todo"]},
        "argv": ["SYNTHETIC-SECRET-SENTINEL"], "environment": {"PRIVATE": "SYNTHETIC-SECRET-SENTINEL"}}
    event["event_id"] = _fake_identity(event)
    path = tmp_path / "complaint_intake_events.jsonl"
    raw = (json.dumps(event) + "\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    before = path.read_bytes()
    fake_log = SimpleNamespace(_event_identity=_fake_identity, _event_stream_binding=lambda _path: ("fake-stream", "fake-snapshot"))
    rows, pin = bridge._journal(tmp_path, fake_log)
    assert path.read_bytes() == before
    assert pin["chain_verified"] is True
    assert pin["prefix_bytes"] == len(raw)
    assert pin["prefix_sha256"] == hashlib.sha256(raw).hexdigest()
    assert "SYNTHETIC-SECRET-SENTINEL" not in json.dumps(rows)
    event["returncode"] = 1
    path.write_text(json.dumps(event) + "\n")
    with pytest.raises(bridge.ReleaseEvidenceError, match="chain_invalid"):
        bridge._journal(tmp_path, fake_log)


def test_synthetic_author_receipt_flags_do_not_create_campaign_authority(tmp_path):
    _write(tmp_path / "launcher.json", {"repo_root": str(tmp_path), "state_dir": str(tmp_path),
        "plan_id": "fake-plan", "accepted": True, "completion_authority": True,
        "schema_version": "author-claims-to-be-native"})
    with pytest.raises(bridge.ReleaseEvidenceError, match="binding_mismatch"):
        bridge._campaign_context(tmp_path, tmp_path, "fake-plan")


@pytest.fixture
def synthetic_boundary(tmp_path, monkeypatch):
    """Mock every Native store; successful joins remain explicit unit fakes."""
    root, state = tmp_path / "source", tmp_path / "fake-campaign"
    root.mkdir()
    state.mkdir()
    identifiers = [f"CIMP-FAKE-{index:02d}" for index in range(57)] + [bridge.SELF_TASK]
    spec_tasks, native_tasks = [], []
    for identifier in identifiers:
        item = {"id": identifier, "title": "Explicit fake " + identifier, "acceptance": ["synthetic assertion"],
            "targets": ["fake.py"], "validation_commands": ["python -m pytest fake_test.py"],
            "depends_on": [], "goal_id": "fake.goal", "subgoal_id": "fake.subgoal"}
        task = _fake_task(identifier)
        task.__dict__.update(title=item["title"], acceptance="synthetic assertion", outputs=item["targets"],
            validation=item["validation_commands"], depends_on=[],
            metadata={"goal": item["goal_id"], "subgoal": item["subgoal_id"], "provider role": "grok-only", "model": "grok-4.7"})
        native_tasks.append(task)
        spec_tasks.append(item)
    goals = [SimpleNamespace(goal_id=f"fake.goal.{index}",
        evidence_requirement_ids=tuple("test." + task_id for task_id in identifiers[index::10])) for index in range(10)]
    subgoals = [SimpleNamespace(subgoal_id=f"fake.subgoal.{index}", goal_id=f"fake.goal.{index % 10}",
        evidence_requirement_ids=tuple("test." + task_id for task_id in identifiers[index::29])) for index in range(29)]
    plan = SimpleNamespace(plan_id="explicit-fake-plan", tasks=native_tasks, goals=goals, subgoals=subgoals,
                           evidence_requirements=list(range(58)), to_dict=lambda: {"schema": "explicit-fake-formal-plan"})
    _write(root / bridge.compiler.SPEC_RELATIVE, {"tasks": spec_tasks})
    _write(root / bridge.compiler.PLAN_RELATIVE, {**plan.to_dict(), "plan_id": plan.plan_id})
    board = root / bridge.compiler.BOARD_RELATIVE
    board.write_text("<!-- plan_id: explicit-fake-plan -->\nExplicit synthetic board; parsed only by the fake Native boundary.\n")
    board.chmod(0o600)
    native = _fake_native()
    native.parse_task_text = lambda *_args, **_kwargs: native_tasks
    projection = {"completed_task_ids": identifiers.copy(), "assumed_completed_task_ids": [],
        "task_statuses": {task_id: "completed" for task_id in identifiers},
        "task_identities": {task.task_id: {"canonical_task_cid": task.canonical_task_cid} for task in native_tasks}}
    bindings = {task.task_id: {task.canonical_task_cid} for task in native_tasks}
    finishes = [_fake_finish(task) for task in native_tasks]
    monkeypatch.setattr(bridge, "_directory", lambda path, **_kwargs: path)
    monkeypatch.setattr(bridge.compiler, "validate_spec", lambda value: value)
    monkeypatch.setattr(bridge.compiler, "build_improvement_work_plan", lambda _spec: plan)
    monkeypatch.setattr(bridge, "_native", lambda: (native, None))
    monkeypatch.setattr(bridge, "_campaign_context", lambda *_args: (root, {"merge_target": "explicit-fake-target"}))
    monkeypatch.setattr(bridge, "_read_state", lambda *_args: projection)
    monkeypatch.setattr(bridge, "_queue_bindings", lambda *_args: bindings)
    monkeypatch.setattr(bridge, "_journal", lambda *_args: (finishes, {"chain_verified": True, "fixture": "explicit-fake"}))
    monkeypatch.setattr(bridge, "_historical_measurements", lambda *_args: {
        "status": "HISTORICAL", "artifacts": [{"path": "explicit-fake", "sha256": "a" * 64}],
        "current_source_equivalence": False})
    monkeypatch.setattr(bridge, "_git", lambda *_args: "1" * 40)
    return SimpleNamespace(root=root, state=state, projection=projection, bindings=bindings, tasks=native_tasks,
                           finishes=finishes, identifiers=identifiers)


def _collect(context, phase="post-completion"):
    return bridge.collect_native_release_evidence(context.root, context.root / bridge.compiler.SPEC_RELATIVE,
                                                  context.state, phase=phase)


def test_synthetic_all58_join_never_upgrades_current_source_or_goal_lifecycles(synthetic_boundary):
    result = _collect(synthetic_boundary)
    assert result["native_completion_satisfied"] is True
    assert len(result["tasks"]) == 58 and len(result["goals"]) == 10 and len(result["subgoals"]) == 29
    assert result["completion_authority"] is False
    assert result["current_source_semantic_coverage"]["status"] == "UNVERIFIED"
    assert all(not row["native_goal_lifecycle_claimed"] for row in result["goals"].values())
    assert all(row["current_source_semantic_coverage"]["status"] == "UNVERIFIED" for row in result["tasks"].values())


@pytest.mark.parametrize("damage,kind", [("queue", "missing"), ("identity", "missing"), ("callback", "unavailable"), ("held", "held")])
def test_synthetic_missing_join_member_fails_closed(synthetic_boundary, damage, kind):
    context = synthetic_boundary
    identifier = context.identifiers[0]
    if damage == "queue":
        context.bindings[identifier] = {"different-fake-revision"}
    elif damage == "identity":
        context.projection["task_identities"][identifier]["canonical_task_cid"] = "different-fake-revision"
    elif damage == "callback":
        context.finishes[0]["todo"]["completion_receipts"][0]["status"] = "pending"
    else:
        context.projection["task_statuses"][identifier] = "manual_hold"
    result = _collect(context)
    assert result["native_completion_satisfied"] is False
    assert any(issue["task_id"] == identifier and issue["kind"] == kind for issue in result["issues"])


def test_synthetic_pre_admission_allows_only_self_pending(synthetic_boundary):
    context = synthetic_boundary
    context.projection["completed_task_ids"].remove(bridge.SELF_TASK)
    context.projection["task_statuses"][bridge.SELF_TASK] = "in_progress"
    context.projection.update(implementation_in_progress=True, active_task_id=bridge.SELF_TASK)
    context.bindings.pop(bridge.SELF_TASK)
    context.tasks[-1].status = "in-progress"
    before = deepcopy(context.projection)
    pre, post = _collect(context, "pre-admission"), _collect(context)
    assert pre["native_completion_satisfied"] is True
    assert pre["tasks"][bridge.SELF_TASK]["native_completed"] is False
    assert post["native_completion_satisfied"] is False
    assert context.projection == before


def test_unknown_phase_is_typed_failure_without_reading_any_store():
    result = bridge.collect_native_release_evidence("/nonexistent", "/nonexistent/spec", "/nonexistent/state", phase="author-approved")
    assert result["native_completion_satisfied"] is False
    assert result["issues"] == [{"code": "unknown_release_phase", "kind": "unknown"}]


def test_native_group_catalog_requires_private_canonical_campaign_boundary(tmp_path):
    from integrations.ipfs_accelerate.release_evidence import _readable_database, ReleaseEvidenceError
    state = tmp_path / "campaign"
    state.mkdir(mode=0o700)
    lanes = state / "control-plane" / "lanes"
    lanes.mkdir(parents=True)
    database = lanes / "state.duckdb"
    database.write_bytes(b"unit fixture catalog; no database opened")
    database.chmod(0o664)
    _readable_database(database, private_root=state)
    state.chmod(0o770)
    with pytest.raises(ReleaseEvidenceError):
        _readable_database(database, private_root=state)
    state.chmod(0o700)
    database.chmod(0o666)
    with pytest.raises(ReleaseEvidenceError):
        _readable_database(database, private_root=state)


def _synthetic_legacy_validation():
    """Construct only pure Native receipt values, never an executor or daemon."""
    from integrations.ipfs_datasets.loader import ensure_import_paths
    ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
    from ipfs_accelerate_py.agent_supervisor.validation import validation_scheduler as scheduler

    command = "python -m pytest -q tests/test_explicit_legacy_fixture.py"
    delivered = "export PYTHONPATH=/synthetic/SYNTHETIC-SECRET-SENTINEL && " + command
    validation_id, node_id, tree = "explicit-unit-validation", "explicit-unit-node", "explicit-unit-tree"
    graph = scheduler.ImpactDependencyGraph(repository_tree_id=tree,
        dependencies={"tests/test_explicit_legacy_fixture.py": ("unit_source.py",)},
        validation_targets={validation_id: ("tests/test_explicit_legacy_fixture.py",)})
    node = scheduler.ValidationDAGNodeRecord(node_id=node_id, command=delivered,
        stage=scheduler.ValidationStage.TARGETED.label,
        disposition=scheduler.ValidationNodeDisposition.SUCCEEDED, reason="explicit unit metadata",
        impact_paths=graph.affected_paths(("unit_source.py",)), returncode=0,
        result_digest="a" * 64, validation_id=validation_id, selected=True, mandatory=True,
        selection_reason="explicit unit graph declaration")
    dag = scheduler.ValidationDAGReceipt(repository_tree_id=tree,
        objective_id="explicit-unit-objective", policy_id="explicit-unit-validation-policy",
        proposal_receipt_id="explicit-unit-proposal-receipt", graph_id=graph.graph_id,
        changed_paths=("unit_source.py",), affected_paths=graph.affected_paths(("unit_source.py",)),
        nodes=(node,), passed=True, impact_graph=graph, required_validation_ids=(validation_id,),
        selected_node_ids=(node_id,), coverage_complete=True, uncovered_impact=False,
        authority_gates=tuple(scheduler.ValidationAuthorityGateRecord(
            gate=gate, disposition=scheduler.ValidationAuthorityDisposition.PENDING,
            reason="unit validation does not grant downstream authority", depends_on=(node_id,))
            for gate in scheduler.REQUIRED_AUTHORITY_GATES)).to_dict()
    launcher = {"mode": "linux:sealed-memfd", "sealed": True,
        "content_sha256": "b" * 64, "interpreter_sha256": "c" * 64, "policy_sha256": "d" * 64,
        "interpreter_stat": json.dumps({"device": 1, "inode": 2, "mode": 0o100755,
            "mtime_ns": 3, "size": 4, "path": "/synthetic/SYNTHETIC-SECRET-SENTINEL"})}
    validation = {"attempted": True, "passed": True, "returncode": 0, "coverage_errors": [],
        "target_commit": tree,
        "results": [{"command": delivered, "raw_command": delivered, "ordinal": 0,
            "validation_id": validation_id, "returncode": 0, "timed_out": False,
            "cache_hit": False, "attempt_number": 1, "validation_result_digest": "a" * 64,
            "cache_key": "e" * 64, "validation_python_launcher": launcher}],
        "validation_dag_receipt": dag,
        "validation_plan_binding": {"command_count": 1, "graph_id": graph.graph_id,
            "validation_ids": [validation_id]},
        "candidate_binding": {"verified": True, "expected_fingerprint": "sha256:" + "f" * 64,
            "current_fingerprint": "sha256:" + "f" * 64,
            "proposal_id": "explicit-unit-proposal", "validated_workspace": {"verified": True}},
        "proposal_gate": {"attempted": True, "accepted": True, "reason_codes": [],
            "proposal_id": "explicit-unit-proposal", "receipt_id": "explicit-unit-proposal-receipt",
            "repository_tree_id": tree, "policy_id": "explicit-unit-proposal-policy"},
        "provider_text": "SYNTHETIC-SECRET-SENTINEL"}
    return validation, command


def _synthetic_legacy_journal(tmp_path, validation):
    task = _fake_task()
    finish = _fake_finish(task)
    event = {"sequence": 1, "previous_event_id": "", "stream_id": "fake-stream",
        "snapshot_id": "fake-snapshot", "type": "implementation_finished",
        "task_id": task.task_id, "canonical_task_cid": task.canonical_task_cid,
        "canonical_task_key": task.canonical_task_key, "returncode": 0,
        "implementation_commit": "1" * 40, "validation_result": validation,
        "merge_result": {"merged": True, "merge_commit": "2" * 40, "todo_update_result": finish["todo"]}}
    event["event_id"] = _fake_identity(event)
    path = tmp_path / "complaint_intake_events.jsonl"
    raw = (json.dumps(event) + "\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    fake_log = SimpleNamespace(_event_identity=_fake_identity,
        _event_stream_binding=lambda _path: ("fake-stream", "fake-snapshot"))
    rows, pin = bridge._journal(tmp_path, fake_log)
    assert path.read_bytes() == raw
    return rows[0], pin, raw


def test_synthetic_legacy_executor_stays_historical_without_invented_host_measurement(tmp_path):
    validation, command = _synthetic_legacy_validation()
    row, pin, raw = _synthetic_legacy_journal(tmp_path, validation)
    task = _fake_task()
    task.validation = [command]
    result = bridge._historical_execution(tmp_path, row, task, pin)
    assert row["behavioral_evidence_present"] is False
    assert row["behavioral_evidence"] is None
    assert result["status"] == "HISTORICAL"
    assert result["evidence_kind"] == "legacy_native_executor"
    assert result["current_source_equivalence"] is False
    assert result["artifacts"] == [] and result["source_after_digests"] == []
    assert result["journal_prefix"]["prefix_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["native_event"]["event_id"] == row["event_id"]
    assert result["validation_metadata"]["dag_receipt_id"] == validation["validation_dag_receipt"]["receipt_id"]
    assert "SYNTHETIC-SECRET-SENTINEL" not in json.dumps(row)
    assert "command" not in result["validation_metadata"]["results"][0]
    assert not any(key in result for key in ("cases", "skipped", "ast_seals", "measurement_record"))
    assert result["limitations"]


@pytest.mark.parametrize("damage", ["dag_identity", "coverage", "result_digest", "unsealed",
    "timeout", "cache_hit", "candidate_fingerprint", "proposal_gate", "command_prefix", "plan_binding"])
def test_synthetic_legacy_metadata_rejects_detached_or_incomplete_execution(damage):
    validation, _command = _synthetic_legacy_validation()
    if damage == "dag_identity":
        validation["validation_dag_receipt"]["receipt_id"] = "0" * 64
    elif damage == "coverage":
        validation["validation_dag_receipt"]["coverage_complete"] = False
    elif damage == "result_digest":
        validation["results"][0]["validation_result_digest"] = "0" * 64
    elif damage == "unsealed":
        validation["results"][0]["validation_python_launcher"]["sealed"] = False
    elif damage == "timeout":
        validation["results"][0]["timed_out"] = True
    elif damage == "cache_hit":
        validation["results"][0]["cache_hit"] = True
    elif damage == "candidate_fingerprint":
        validation["candidate_binding"]["current_fingerprint"] = "sha256:" + "0" * 64
    elif damage == "proposal_gate":
        validation["proposal_gate"]["accepted"] = False
    elif damage == "command_prefix":
        validation["results"][0]["command"] = "export OTHER=unit && " + _command
    else:
        validation["validation_plan_binding"]["validation_ids"] = []
    with pytest.raises(bridge.ReleaseEvidenceError, match="legacy_native_"):
        bridge._legacy_native_validation(validation)


@pytest.mark.parametrize("modern", [None, [], {}, [None], [{"admitted": True}]])
def test_malformed_modern_evidence_never_falls_back_to_valid_legacy_metadata(tmp_path, modern):
    validation, command = _synthetic_legacy_validation()
    validation["behavioral_evidence"] = modern
    row, pin, _raw = _synthetic_legacy_journal(tmp_path, validation)
    task = _fake_task()
    task.validation = [command]
    assert row["behavioral_evidence_present"] is True
    assert row["legacy_native_validation"] is None
    with pytest.raises(bridge.ReleaseEvidenceError, match="historical_"):
        bridge._historical_execution(tmp_path, row, task, pin)


@pytest.mark.parametrize("damage", ["journal_pin", "command_contract"])
def test_synthetic_legacy_history_requires_authenticated_prefix_and_actual_task_contract(tmp_path, damage):
    validation, command = _synthetic_legacy_validation()
    row, pin, _raw = _synthetic_legacy_journal(tmp_path, validation)
    task = _fake_task()
    task.validation = [command]
    if damage == "journal_pin":
        pin["chain_verified"] = False
    else:
        task.validation = ["python -m pytest -q tests/a_different_unit_contract.py"]
    with pytest.raises(bridge.ReleaseEvidenceError, match="legacy_native_"):
        bridge._historical_execution(tmp_path, row, task, pin)
