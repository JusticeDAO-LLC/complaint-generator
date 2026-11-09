"""Checker failures and phase contracts; synthetic inventories have no authority."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

import hashlib
import importlib.util
import sys

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
ROOT = Path(__file__).resolve().parents[1]
_SOURCE = ROOT / "scripts/validate_complaint_intake.py"
_NAME = "_complaint_intake_release_checker_" + hashlib.sha256(str(_SOURCE).encode()).hexdigest()[:16]
gate = sys.modules.get(_NAME)
if gate is None:
    _specification = importlib.util.spec_from_file_location(_NAME, _SOURCE)
    assert _specification is not None and _specification.loader is not None
    gate = importlib.util.module_from_spec(_specification)
    sys.modules[_NAME] = gate
    _specification.loader.exec_module(gate)
assert Path(gate.__file__).resolve() == _SOURCE.resolve()


def _unit_inventory(phase="pre-admission"):
    """Pure evaluator input only; never supplied through a production file API."""
    spec = json.loads((ROOT / gate.SPEC_RELATIVE).read_text())
    rows = {}
    for task in spec["tasks"]:
        complete = phase == "post-completion" or task["id"] != gate.SELF_TASK
        rows[task["id"]] = {"canonical_task_cid": "unit-only:" + task["id"],
            "native_completed": complete, "callback_verified": complete, "integration_verified": complete,
            "historical_evidence": {"status": "HISTORICAL" if complete else "MISSING",
                                    "current_source_equivalence": False}}
    def requirements(kind):
        groups = spec["goals"] if kind == "goals" else [s for g in spec["goals"] for s in g["subgoals"]]
        field = "goal_id" if kind == "goals" else "subgoal_id"
        output = {}
        for group in groups:
            members = [t["id"] for t in spec["tasks"] if t[field] == group["id"]]
            output[group["id"]] = {"task_ids": members, "evidence_requirement_ids": ["test." + t for t in members],
                                   "native_completion_satisfied": all(rows[t]["native_completed"] for t in members)}
        return output
    return {"schema": "complaint-native-release-evidence@1", "phase": phase,
            "completion_authority": False, "native_completion_satisfied": True, "issues": [],
            "tasks": rows, "goals": requirements("goals"), "subgoals": requirements("subgoals"),
            "integration_proof": {"verified": True}}


def _evaluate(native=None, *, phase="pre-admission", coverage=None):
    return gate.evaluate_release(native or _unit_inventory(phase),
        coverage or {"status": "VERIFIED", "completion_authority": False}, phase=phase,
        report_sha256="unit-report-hash", source={"unit": "source-contract"})


def test_current_release_remains_self_pending():
    report = json.loads((ROOT / gate.REPORT_RELATIVE).read_text())
    assert report["release_qualified"] is False
    assert report["self_completion_pending"] is True
    assert report["pending_task_ids"] == [gate.SELF_TASK]
    assert report["completion_authority"] is False


@pytest.mark.parametrize("argv,phase", [([], "post-completion"),
    (["--phase", "pre-admission"], "pre-admission"),
    (["--phase=pre-admission"], "pre-admission"),
    (["--phase", "post-completion"], "post-completion")])
def test_explicit_phase_and_strict_default(argv, phase):
    assert gate.parse_phase(argv) == phase


@pytest.mark.parametrize("argv", [["--phase"], ["--phase=guess"],
    ["--phase", "pre-admission", "--phase=post-completion"]])
def test_invalid_or_duplicate_phase_refuses(argv):
    with pytest.raises(ValueError):
        gate.parse_phase(argv)


def test_pre_admission_unit_assessment_preserves_only_self_pending():
    result = _evaluate()
    assert result["passed"] is True
    assert result["release_qualified"] is False
    assert result["pending_task_ids"] == [gate.SELF_TASK]
    assert result["self_completion_pending"] is True
    assessments = result["requirement_assessments"]
    assert len(assessments["goals"]) == 10 and len(assessments["subgoals"]) == 29
    assert assessments["goals"]["goal.release"]["status"] == "SELF_PENDING"
    assert assessments["subgoals"]["subgoal.release.acceptance-documentation"]["status"] == "SELF_PENDING"
    assert all(row["formal_lifecycle_completion_claimed"] is False and row["completion_authority"] is False
               for group in assessments.values() for row in group.values())
    assert all(row["status"] == "not_run" and row["executed"] is False for row in result["optional_live"])


@pytest.mark.parametrize("field", ["native_completed", "callback_verified", "integration_verified"])
def test_missing_tui12_native_member_or_callback_fails(field):
    native = _unit_inventory()
    native["tasks"]["CIMP-TUI-12"][field] = False
    result = _evaluate(native)
    assert result["passed"] is False and result["release_qualified"] is False
    assert any(row.get("task_id") == "CIMP-TUI-12" for row in result["issues"])


@pytest.mark.parametrize("issue", ["held", "unknown", "unavailable", "missing"])
def test_native_bridge_issues_are_never_overridden_by_current_passes(issue):
    native = _unit_inventory()
    native["issues"] = [{"code": "synthetic-" + issue, "kind": issue, "task_id": "CIMP-REL-01"}]
    result = _evaluate(native)
    assert result["passed"] is False
    assert result["historical_native_evidence"]["issues"] == native["issues"]


def test_historical_source_equivalence_is_never_relabelled_current():
    native = _unit_inventory()
    before = deepcopy(native)
    result = _evaluate(native)
    assert native == before
    assert all(row["historical_evidence"]["current_source_equivalence"] is False
               for row in result["historical_native_evidence"]["tasks"].values())


def test_missing_historical_measurement_and_current_skips_fail_closed():
    native = _unit_inventory()
    native["tasks"]["CIMP-REL-01"]["historical_evidence"]["status"] = "MISSING"
    assert _evaluate(native)["passed"] is False
    result = _evaluate(coverage={"status": "UNVERIFIED", "issues": ["skipped_required_case"]})
    assert result["passed"] is False and result["release_qualified"] is False


def test_post_completion_requires_real_reader_proof_and_all_members():
    early = _evaluate(_unit_inventory(), phase="post-completion")
    assert early["passed"] is False and early["release_qualified"] is False
    inventory = _unit_inventory("post-completion")
    inventory["integration_proof"]["verified"] = False
    assert _evaluate(inventory, phase="post-completion")["release_qualified"] is False
    # A pure policy unit input can exercise the positive branch. The CLI has
    # no serialized-evidence bypass and always invokes the genuine bridge.
    ready = _evaluate(_unit_inventory("post-completion"), phase="post-completion")
    assert ready["release_qualified"] is True and ready["completion_authority"] is False
    assert ready["pending_task_ids"] == []


def test_pre_admission_after_self_callback_requires_strict_post_phase():
    assert _evaluate(_unit_inventory("post-completion"))["passed"] is False


def test_serialized_measurement_is_not_the_existing_native_capability():
    from integrations.ipfs_accelerate.improvement_plan import _host_evidence_reason
    assert _host_evidence_reason({"host_measurement": {"reason": "", "source_unchanged": True}}, {}) == "host_measurement_required"


def test_arbitrary_evidence_and_integration_proof_file_flags_are_not_authority(tmp_path):
    for flag in ("--evidence", "--integration-proof"):
        with pytest.raises(SystemExit) as stopped:
            gate.main([flag, str(tmp_path / "author-claimed.json")])
        assert stopped.value.code == 2


def test_missing_authoritative_context_fails_without_creating_a_campaign(tmp_path, monkeypatch):
    monkeypatch.delenv(gate.STATE_ENV, raising=False)
    monkeypatch.delenv(gate.TARGET_ENV, raising=False)
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match="owned_campaign_context_missing"):
        gate._context(tmp_path, None, None)
    assert set(tmp_path.iterdir()) == before


def test_launcher_target_mismatch_fails(tmp_path):
    state = tmp_path / "state"; state.mkdir(mode=0o700)
    (state / "launcher.json").write_text(json.dumps({"repo_root": str(tmp_path / "target-a")}))
    with pytest.raises(ValueError, match="campaign_target_launcher_mismatch"):
        gate._context(tmp_path, state, tmp_path / "target-b")


def test_report_rederivation_is_stable_and_detects_source_change(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "source_bindings", lambda root: {"source": "version-one"})
    monkeypatch.setattr(gate, "mandatory_manifest", lambda root: {"unit": ["tests/unit-only.py"]})
    path = tmp_path / gate.REPORT_RELATIVE; path.parent.mkdir(parents=True)
    expected = gate.committed_report_payload(tmp_path)
    path.write_text(json.dumps(expected, indent=2, sort_keys=True))
    before = path.read_bytes()
    first = gate.committed_report_contract(tmp_path)
    assert first == gate.committed_report_contract(tmp_path) and first[0] == ""
    assert path.read_bytes() == before
    monkeypatch.setattr(gate, "source_bindings", lambda root: {"source": "version-two"})
    assert gate.committed_report_contract(tmp_path)[0] == "committed_pre_admission_contract_changed"
    assert path.read_bytes() == before


def test_full_manifest_excludes_self_and_isolates_lifecycle_and_replica():
    manifest = gate.mandatory_manifest(ROOT)
    combined = [p for group in manifest.values() for p in group]
    assert len(combined) == len(set(combined))
    assert gate.GATE_RELATIVE not in combined and gate.SCRIPT_RELATIVE not in combined
    assert gate.PUBLIC_RELATIVE in manifest["application"]
    assert "tests/test_intake_router_boundary.py" in manifest["application"]
    assert "tests/test_improvement_runner.py" in manifest["lifecycle"]
    assert "tests/test_improvement_validation_activity.py" in manifest["lifecycle"]
    assert "tests/test_improvement_release_context.py" in manifest["lifecycle"]
    assert "tests/test_private_replica_acceptance.py" in manifest["replica"]


def test_other_passing_module_cannot_hide_empty_required_module():
    selected = ["tests/test_required_graph.py", "tests/test_required_law.py"]
    population, reason = gate.module_case_population(selected,
        ["tests/test_required_graph.py::test_nonempty_graph"])
    assert population["tests/test_required_graph.py"] == ["tests/test_required_graph.py::test_nonempty_graph"]
    assert population["tests/test_required_law.py"] == []
    assert reason == "selected_module_zero_cases:tests/test_required_law.py"


def test_exact_nonempty_module_populations_and_unknown_cases_are_distinct():
    selected = ["tests/test_required_graph.py", "tests/test_required_law.py"]
    nodes = ["tests/test_required_graph.py::test_graph[a]", "tests/test_required_graph.py::test_graph[b]",
             "tests/test_required_law.py::TestAuthority::test_applicability"]
    population, reason = gate.module_case_population(selected, nodes)
    assert reason == "" and [len(population[path]) for path in selected] == [2, 1]
    assert gate.module_case_population(selected, nodes + [nodes[0]])[1] == "module_case_identity_malformed"
    assert gate.module_case_population(selected, nodes + ["tests/test_unreviewed.py::test_other"])[1] == "unselected_module_case:tests/test_unreviewed.py"


@pytest.mark.parametrize("budget", [-1, 0, 901, float("nan"), float("inf")])
def test_budget_cannot_exceed_existing_runtime_cap(tmp_path, budget):
    with pytest.raises(ValueError, match="mandatory_budget_out_of_range"):
        gate.measure_current_closure(tmp_path, tmp_path, timeout_seconds=budget)


def test_provider_or_unknown_process_is_denied_and_local_python_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setitem(gate._GUARD, "python", sys_executable := os.path.realpath(os.sys.executable))
    monkeypatch.setitem(gate._GUARD, "directory", str(tmp_path))
    assert gate._safe_local_argv([sys_executable, "-c", "pass"])
    assert not gate._safe_local_argv(["grok", "--version"])
    assert not gate._safe_local_argv(["curl", "https://example.test"])
    assert not gate._safe_local_argv(["bash", "-c", "PATH=/foreign python -m pytest"])
    assert not gate._safe_local_argv(["bash", "-c", "python -m pytest; grok --version"])


def test_actual_executable_cannot_masquerade_as_reviewed_python_or_git(monkeypatch, tmp_path):
    python = Path(sys.executable).resolve()
    monkeypatch.setitem(gate._GUARD, "python", str(python))
    monkeypatch.setitem(gate._GUARD, "directory", str(tmp_path))
    monkeypatch.setitem(gate._GUARD, "executables", {str(python): gate._hash(python)})
    foreign = tmp_path / "foreign-provider"; foreign.write_text("unit executable bytes"); foreign.chmod(0o700)
    assert gate.reviewed_process_dispatch(str(python), [str(python), "-c", "pass"], str(tmp_path), {})
    assert not gate.reviewed_process_dispatch(str(foreign), [str(python), "-c", "pass"], str(tmp_path), {})
    fake_git = tmp_path / "git"; fake_git.write_text("unit foreign git"); fake_git.chmod(0o700)
    assert not gate.reviewed_process_dispatch(str(fake_git), [str(fake_git), "status"], str(tmp_path), {})
    assert not gate.reviewed_process_dispatch(str(python), [str(fake_git), "status"], str(tmp_path), {})


def test_git_readonly_fixture_commands_require_pinned_actual_git(monkeypatch, tmp_path):
    import shutil
    executable = Path(shutil.which("git", path=os.defpath)).resolve()
    monkeypatch.setitem(gate._GUARD, "directory", str(tmp_path))
    monkeypatch.setitem(gate._GUARD, "executables", {str(executable): gate._hash(executable)})
    for operation in (["ls-tree", "-r", "-l", "-z", "HEAD"], ["symbolic-ref", "--quiet", "--short", "HEAD"]):
        argv = [str(executable), *operation]
        assert gate.reviewed_process_dispatch(str(executable), argv, str(tmp_path), {})
    foreign = tmp_path / "git"; foreign.write_text("unit executable"); foreign.chmod(0o700)
    assert not gate.reviewed_process_dispatch("git", ["git", "ls-tree", "HEAD"], str(tmp_path), {"PATH": str(tmp_path)})


def test_inherited_native_launcher_proves_roots_without_global_guard_mutation(tmp_path):
    import fcntl
    from ipfs_accelerate_py.agent_supervisor.validation import validation_runtime as runtime
    python = str(Path(sys.executable).resolve())
    environment = {"PYTHONPATH": str(tmp_path), "IPFS_ACCELERATE_VALIDATION_PYTHON_EXECUTABLE": python}
    payload = runtime._validation_python_launcher_source(executable=python,
        approved_pythonpath=str(tmp_path), ruff_sha256="", no_site=False)
    descriptor = os.memfd_create("validation Python launcher", os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
    before = dict(gate._GUARD)
    try:
        os.write(descriptor, payload)
        path = "/proc/self/fd/" + str(descriptor)
        assert not gate.native_memfd_matches(path, environment, runtime=runtime, python=python)
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, 15)
        assert gate.native_memfd_matches(path, environment, runtime=runtime, python=python)
        current_pid_path = "/proc/" + str(os.getpid()) + "/fd/" + str(descriptor)
        duplicates = {**environment, "PYTHONPATH": str(tmp_path) + os.pathsep + str(tmp_path)}
        assert gate.native_memfd_approved_paths(current_pid_path, duplicates, runtime=runtime, python=python) == (tmp_path,)
        assert gate.native_memfd_approved_paths("/proc/1/fd/" + str(descriptor), environment, runtime=runtime, python=python) is None
        assert not gate.native_memfd_matches(path, {**environment, "PYTHONPATH": str(tmp_path / "foreign")}, runtime=runtime, python=python)
        assert not gate.native_memfd_matches(path, environment, runtime=runtime, python=python,
                                            approved_roots=[tmp_path / "different-approved-root"])
        assert dict(gate._GUARD) == before
    finally:
        os.close(descriptor)


def test_claimed_native_environment_without_native_launcher_bytes_is_rejected(tmp_path):
    import fcntl
    from ipfs_accelerate_py.agent_supervisor.validation import validation_runtime as runtime
    descriptor = os.memfd_create("validation Python launcher", os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
    try:
        os.write(descriptor, b"#!/bin/bash\n# arbitrary author-created payload\n")
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, 15)
        assert not gate.native_memfd_matches("/proc/self/fd/" + str(descriptor),
            {"PYTHONPATH": str(tmp_path), "IPFS_ACCELERATE_VALIDATION_PYTHON_LAUNCHER_SHA256": "author-claimed"},
            runtime=runtime, python=str(Path(sys.executable).resolve()))
    finally:
        os.close(descriptor)


def test_post_runtime_report_cannot_overwrite_source_or_symlink(tmp_path):
    source = tmp_path / "source"; source.mkdir(mode=0o700)
    committed = source / "committed.json"; committed.write_text("unit immutable source")
    with pytest.raises(ValueError, match="runtime_report_inside_source"):
        gate.write_runtime_report(committed, {}, source_roots=(source,))
    alias = tmp_path / "alias.json"; alias.symlink_to(committed)
    with pytest.raises(ValueError, match="path_alias_forbidden"):
        gate.write_runtime_report(alias, {}, source_roots=(source,))
    assert committed.read_text() == "unit immutable source"


def test_hardlink_and_foreign_runtime_artifact_are_not_overwritten(tmp_path):
    source = tmp_path / "source"; source.mkdir(mode=0o700)
    original = source / "committed.json"; original.write_text("unit immutable source")
    hardlink = tmp_path / "hardlink.json"; os.link(original, hardlink)
    with pytest.raises(ValueError, match="runtime_report_not_owned"):
        gate.write_runtime_report(hardlink, {}, source_roots=(source,))
    foreign = tmp_path / "foreign.json"; foreign.write_text('{"schema":"other-owned-artifact"}')
    foreign.chmod(0o600)
    with pytest.raises(ValueError, match="runtime_report_foreign_artifact"):
        gate.write_runtime_report(foreign, {}, source_roots=(source,))
    assert original.read_text() == "unit immutable source"


def test_separate_runtime_artifact_keeps_pre_report_bytes_and_private_permissions(tmp_path):
    source = tmp_path / "source"; source.mkdir(mode=0o700)
    report = source / "committed.json"; report.write_bytes(b"unit pre-admission bytes\n")
    destination = tmp_path / "runtime" / "post.json"
    gate.write_runtime_report(destination, {"schema": gate.SCHEMA, "release_qualified": True,
        "committed_report_sha256": gate._hash(report), "completion_authority": False}, source_roots=(source,))
    assert report.read_bytes() == b"unit pre-admission bytes\n"
    written = json.loads(destination.read_text())
    assert written["schema"] == gate.RUNTIME_SCHEMA and written["completion_authority"] is False
    assert destination.stat().st_mode & 0o777 == 0o600
    assert destination.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("arguments", [
    ["diff", "--ext-diff"], ["show", "--textconv", "HEAD"],
    ["--exec-path=/synthetic/provider", "status"],
    ["--exec-path", "/synthetic/provider", "status"],
    ["-c", "core.fsmonitor=/synthetic/provider", "status"],
    ["-ccore.fsmonitor=/synthetic/provider", "status"],
    ["-c", "core.FsMonitor=true", "status"],
    ["-c", "diff.external=/synthetic/provider", "diff"],
    ["-c", "diff.unit.textconv=/synthetic/provider", "show"],
    ["-c", "diff.unit.command=/synthetic/provider", "diff"],
    ["-c", "core.sshCommand=/synthetic/provider", "status"],
    ["-c", "core.hooksPath=/synthetic/hooks", "status"],
    ["-c", "credential.helper=/synthetic/provider", "status"],
    ["--config-env=core.fsmonitor=UNIT_ONLY", "status"],
    ["config", "core.fsmonitor", "/synthetic/provider"],
    ["config", "core.hooksPath", "/synthetic/hooks"],
    ["config", "diff.external", "/synthetic/provider"],
])
def test_pinned_git_cannot_request_external_execution(monkeypatch, tmp_path, arguments):
    """Inspect arguments only; no Git, hook, credential helper, or provider runs."""
    import shutil
    executable = Path(shutil.which("git", path=os.defpath)).resolve()
    monkeypatch.setitem(gate._GUARD, "directory", str(tmp_path))
    monkeypatch.setitem(gate._GUARD, "executables", {str(executable): gate._hash(executable)})
    assert not gate.reviewed_process_dispatch(str(executable),
        [str(executable), *arguments], str(tmp_path), {})


@pytest.mark.parametrize("arguments", [
    ["init", "-b", "main"], ["config", "user.name", "Synthetic Unit Fixture"],
    ["config", "user.email", "unit@example.invalid"], ["config", "core.hooksPath", "/dev/null"],
    ["add", "unit.py"],
    ["-c", "user.name=Synthetic Unit Fixture", "-c", "user.email=unit@example.invalid", "commit", "-qm", "unit fixture"],
    ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "status"],
    ["diff", "--no-ext-diff", "--no-textconv"],
])
def test_git_fixture_operations_keep_the_reviewed_local_scope(monkeypatch, tmp_path, arguments):
    import shutil
    executable = Path(shutil.which("git", path=os.defpath)).resolve()
    monkeypatch.setitem(gate._GUARD, "directory", str(tmp_path))
    monkeypatch.setitem(gate._GUARD, "executables", {str(executable): gate._hash(executable)})
    assert gate.reviewed_process_dispatch(str(executable),
        [str(executable), *arguments], str(tmp_path), {})


def test_scope_keeps_opaque_gitlink_identity_without_claiming_physical_head(monkeypatch):
    from integrations.ipfs_accelerate import improvement_runner as runner
    declared = {"external/" + name: {"gitlink": "a" * 40, "head": "a" * 40}
                for name in ("ipfs_accelerate_py", "ipfs_datasets_py", "ipfs_kit_py")}
    frozen = {"files": {"synthetic-source": {"sha256": "b" * 64}},
              "dependencies": {**declared, "external/mike": {"gitlink": "c" * 40, "head": "unavailable"}}}
    monkeypatch.setattr(runner, "_source_freeze", lambda *_args: frozen)
    first = gate.source_bindings(ROOT)
    frozen["dependencies"]["external/mike"]["head"] = "d" * 40
    assert gate.source_bindings(ROOT) == first
    frozen["dependencies"]["external/mike"]["gitlink"] = "e" * 40
    assert gate.source_bindings(ROOT) != first
    frozen["dependencies"]["external/ipfs_datasets_py"]["head"] = "unavailable"
    with pytest.raises(ValueError, match="deployed_dependency_head_changed"):
        gate.source_bindings(ROOT)


def test_data_worker_core_zero_wrapper_requires_both_pinned_executables(monkeypatch, tmp_path):
    python = Path(sys.executable).resolve()
    prlimit = Path("/usr/bin/prlimit").resolve()
    monkeypatch.setitem(gate._GUARD, "python", str(python))
    monkeypatch.setitem(gate._GUARD, "executables",
                        {str(path): gate._hash(path) for path in (python, prlimit)})
    argv = [str(prlimit), "--core=0:0", "--", str(python), "-I", "-S", "-B", "-c", "pass"]
    assert gate.reviewed_process_dispatch(str(prlimit), argv, str(tmp_path), {})
    foreign = tmp_path / "python"; foreign.write_text("synthetic untrusted interpreter"); foreign.chmod(0o700)
    assert not gate.reviewed_process_dispatch(str(prlimit), [*argv[:3], str(foreign), *argv[4:]], str(tmp_path), {})
    assert not gate.reviewed_process_dispatch(str(foreign), argv, str(tmp_path), {})
    monkeypatch.setitem(gate._GUARD, "executables", {str(prlimit): gate._hash(prlimit)})
    assert not gate.reviewed_process_dispatch(str(prlimit), argv, str(tmp_path), {})


@pytest.mark.parametrize("options", [
    ["--core=unlimited", "--"], ["--pid", "1", "--core=0:0", "--"],
    ["--core=0:0", "--cpu=unlimited", "--"], ["--core=0:0"],
    ["--core=0:0", "--", "--"],
])
def test_prlimit_cannot_expand_the_reviewed_worker_wrapper(monkeypatch, tmp_path, options):
    python = Path(sys.executable).resolve()
    prlimit = Path("/usr/bin/prlimit").resolve()
    monkeypatch.setitem(gate._GUARD, "python", str(python))
    monkeypatch.setitem(gate._GUARD, "executables",
                        {str(path): gate._hash(path) for path in (python, prlimit)})
    assert not gate.reviewed_process_dispatch(str(prlimit),
        [str(prlimit), *options, str(python), "-c", "pass"], str(tmp_path), {})


def _launcher_guard_fixture(monkeypatch, tmp_path):
    source = ROOT / "scripts/run_cli_mediator.sh"
    bash = Path("/bin/bash").resolve()
    monkeypatch.setitem(gate._GUARD, "source_root", str(ROOT))
    monkeypatch.setitem(gate._GUARD, "directory", str(tmp_path))
    monkeypatch.setitem(gate._GUARD, "python", str(Path(sys.executable).resolve()))
    monkeypatch.setitem(gate._GUARD, "executables", {str(bash): gate._hash(bash)})
    monkeypatch.setitem(gate._GUARD, "launcher_script_sha256", gate._hash(source))
    monkeypatch.setitem(gate._GUARD, "launcher_probe_executables", {str(path): gate._hash(path) for path in
        (Path("/usr/bin/false").resolve(), Path("/usr/bin/python3.12").resolve())})
    environment = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
        "COMPLAINT_GENERATOR_PYTHON": "/usr/bin/false",
        "COMPLAINT_GENERATOR_MEDIATOR_BACKENDS": "configured-backend",
        "COMPLAINT_GENERATOR_LAUNCHER_DRY_RUN": "1"}
    return bash, [str(bash), str(source), "--user-id", "synthetic"], environment


def test_canonical_launcher_dry_run_preserves_broken_python_fallback(monkeypatch, tmp_path):
    bash, argv, environment = _launcher_guard_fixture(monkeypatch, tmp_path)
    # This is dispatch inspection only: the real PTY suite still executes the
    # unchanged launcher and asserts that /usr/bin/false falls back to Python.
    assert environment["COMPLAINT_GENERATOR_PYTHON"] == "/usr/bin/false"
    assert gate.reviewed_process_dispatch(str(bash), argv, str(tmp_path), environment)
    monkeypatch.setitem(gate._GUARD, "launcher_script_sha256", "0" * 64)
    assert not gate.reviewed_process_dispatch(str(bash), argv, str(tmp_path), environment)


@pytest.mark.parametrize("key,value", [
    ("BASH_ENV", "/synthetic/untrusted-startup"), ("LD_PRELOAD", "/synthetic/untrusted.so"),
    ("PATH", "/synthetic/foreign:/usr/bin:/bin"),
    ("COMPLAINT_GENERATOR_PYTHON", "/synthetic/provider"),
    ("COMPLAINT_GENERATOR_LAUNCHER_DRY_RUN", "0"),
])
def test_pinned_launcher_does_not_admit_startup_or_interpreter_injection(monkeypatch, tmp_path, key, value):
    bash, argv, environment = _launcher_guard_fixture(monkeypatch, tmp_path)
    assert not gate.reviewed_process_dispatch(str(bash), argv, str(tmp_path), {**environment, key: value})


def _exercise_private_descriptor_guard(connection, root, fixture):
    """Real audit hooks stay confined to an owned, joined fork child."""
    import errno
    private_fd = os.open(root / "evidence", os.O_RDONLY | os.O_DIRECTORY)
    fixture_fd = os.open(fixture, os.O_RDONLY | os.O_DIRECTORY)
    gate._GUARD.clear()
    gate._GUARD["denied_private"] = 0
    gate._configure_private_prefixes(root)
    gate._kernel_network_deny()
    os.open = gate._reviewed_os_open
    sys.addaudithook(gate._audit_private_access)
    os.chdir(root)
    results = {}
    try:
        for label, path, descriptor in (
                ("current_private", "evidence/note", None),
                ("fixture_descriptor", "evidence/note", fixture_fd),
                ("private_descriptor", "note", private_fd),
                ("fixture_symlink", "alias/note", fixture_fd)):
            try:
                fd = os.open(path, os.O_RDONLY, dir_fd=descriptor)
                try:
                    results[label] = os.read(fd, 64).decode()
                finally:
                    os.close(fd)
            except PermissionError as exc:
                results[label] = str(exc)
        try:
            os.open("note", os.O_RDONLY, dir_fd=-1)
        except OSError as exc:
            results["invalid_descriptor"] = exc.errno == errno.EBADF
        results["context_restored"] = getattr(gate._OPEN_CONTEXT, "active", None) is None
        connection.send(results)
    finally:
        os.close(private_fd)
        os.close(fixture_fd)
        connection.close()


def test_private_guard_resolves_actual_dir_fd_without_exempting_private_paths(tmp_path):
    import multiprocessing
    root, fixture = tmp_path / "source", tmp_path / "owned-fixture"
    (root / "evidence").mkdir(parents=True)
    (fixture / "evidence").mkdir(parents=True)
    (root / "evidence/note").write_text("synthetic private content")
    (fixture / "evidence/note").write_text("synthetic temporary content")
    (fixture / "alias").symlink_to(root / "evidence", target_is_directory=True)
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe(duplex=False)
    worker = context.Process(target=_exercise_private_descriptor_guard, args=(child, root, fixture))
    worker.start()
    child.close()
    try:
        worker.join(timeout=8)
        assert not worker.is_alive(), "private descriptor guard worker exceeded its bounded deadline"
        assert worker.exitcode == 0 and parent.poll(1)
        results = parent.recv()
        assert results == {
            "current_private": "release_existing_private_data_denied",
            "fixture_descriptor": "synthetic temporary content",
            "private_descriptor": "release_existing_private_data_denied",
            "fixture_symlink": "release_existing_private_data_denied",
            "invalid_descriptor": True, "context_restored": True,
        }
    finally:
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=2)
        parent.close()
        worker.close()


def test_fixed_current_qualification_uses_reverification_without_claiming_reexecution(monkeypatch, tmp_path):
    from integrations.ipfs_accelerate import release_evidence as bridge
    calls = []
    bound = {"schema": "complaint-release-current-semantic-coverage@1", "status": "VERIFIED",
        "execution_mode": "fixed_host_qualification_reverification",
        "producer_executions": {"actual_current_source_case_count": 2000},
        "verification_this_invocation": {"mandatory_case_execution_count": 0}, "completion_authority": False}
    def read(root, spec, state, *, phase):
        calls.append((root, spec, state, phase))
        return bound
    monkeypatch.setattr(bridge, "read_current_release_qualification", read)
    monkeypatch.setattr(gate, "measure_current_closure", lambda *args, **kwargs: pytest.fail("bound proof must be reverified, not executed again"))
    result = gate.current_release_coverage(ROOT, tmp_path, phase="pre-admission",
        campaign_state_dir=tmp_path / "owned-campaign", timeout_seconds=900)
    assert result is bound
    assert calls == [(ROOT, ROOT / gate.SPEC_RELATIVE, tmp_path / "owned-campaign", "pre-admission")]
    assert result["verification_this_invocation"]["mandatory_case_execution_count"] == 0
    assert result["producer_executions"]["actual_current_source_case_count"] == 2000


def test_only_absent_fixed_qualification_falls_back_to_direct_closure(monkeypatch, tmp_path):
    from integrations.ipfs_accelerate import release_evidence as bridge
    calls = []
    monkeypatch.setattr(bridge, "read_current_release_qualification", lambda *args, **kwargs: None)
    def direct(root, runtime, *, timeout_seconds):
        calls.append((root, runtime, timeout_seconds))
        return {"status": "UNVERIFIED", "issues": ["unit_execution_not_performed"]}
    monkeypatch.setattr(gate, "measure_current_closure", direct)
    result = gate.current_release_coverage(ROOT, tmp_path, phase="pre-admission",
        campaign_state_dir=tmp_path / "owned-campaign", timeout_seconds=899)
    assert result["status"] == "UNVERIFIED" and calls == [(ROOT, tmp_path, 899)]


def test_changed_fixed_qualification_cannot_fall_back_to_unrelated_direct_pass(monkeypatch, tmp_path):
    from integrations.ipfs_accelerate import release_evidence as bridge
    def changed(*args, **kwargs):
        raise bridge.ReleaseEvidenceError("current_qualification_artifact_digest_mismatch")
    monkeypatch.setattr(bridge, "read_current_release_qualification", changed)
    monkeypatch.setattr(gate, "measure_current_closure", lambda *args, **kwargs: pytest.fail("invalid fixed binding must fail closed"))
    with pytest.raises(bridge.ReleaseEvidenceError, match="artifact_digest_mismatch"):
        gate.current_release_coverage(ROOT, tmp_path, phase="post-completion",
            campaign_state_dir=tmp_path / "owned-campaign", timeout_seconds=900)


def test_producer_plan_preserves_all_full_modules_and_existing_command_caps(tmp_path):
    import shlex
    from integrations.ipfs_accelerate.release_evidence import _current_shard_plan
    manifest = gate.mandatory_manifest(ROOT)
    plan = _current_shard_plan(manifest, tmp_path)
    assert plan["serial"] is True and plan["retries"] == 0
    assert plan["max_modules_per_shard"] == 4 and plan["per_shard_budget_seconds"] == 900
    combined = []
    for shard in plan["shards"]:
        assert shard["group"] in manifest and 0 < len(shard["modules"]) <= 4
        assert shard["budget_seconds"] == gate.TOTAL_BUDGET_SECONDS == 900
        tokens = shlex.split(shard["command"])
        selected = [value for value in tokens if value.startswith("tests/")]
        assert selected == shard["modules"] and all("::" not in value for value in selected)
        assert "-k" not in tokens and "--lf" not in tokens and "--ff" not in tokens
        assert all(value in manifest[shard["group"]] for value in selected)
        combined.extend(selected)
    expected = [value for paths in manifest.values() for value in paths]
    assert len(combined) == len(set(combined)) == len(expected) == 83
    assert set(combined) == set(expected)
    assert gate.GATE_RELATIVE not in combined


def test_producer_rejects_reused_runtime_before_any_execution(monkeypatch, tmp_path):
    runtime = tmp_path / "qualification"; runtime.mkdir(mode=0o700)
    (runtime / "previous-artifact.json").write_text("{}")
    monkeypatch.setattr(gate, "_owned_native_runner", lambda **kwargs: pytest.fail("a reused runtime cannot execute"))
    with pytest.raises(ValueError, match="qualification_runtime_must_be_fresh"):
        gate.produce_current_release_qualification(ROOT, runtime,
            producer_path=_SOURCE, producer_sha256=gate._hash(_SOURCE))


def test_producer_rejects_changed_source_pin_before_any_execution(monkeypatch, tmp_path):
    runtime = tmp_path / "qualification"; runtime.mkdir(mode=0o700)
    monkeypatch.setattr(gate, "_owned_native_runner", lambda **kwargs: pytest.fail("an unpinned producer cannot execute"))
    with pytest.raises(ValueError, match="qualification_producer_scope_unverified"):
        gate.produce_current_release_qualification(ROOT, runtime,
            producer_path=_SOURCE, producer_sha256="0" * 64)


def test_committed_protocol_distinguishes_production_from_checker_verification(monkeypatch):
    monkeypatch.setattr(gate, "source_bindings", lambda root: {"unit": "source"})
    monkeypatch.setattr(gate, "mandatory_manifest", lambda root: {"unit": ["tests/unit-only.py"]})
    protocol = gate.committed_report_payload(ROOT)["current_qualification_protocol"]
    assert protocol["maximum_modules_per_shard"] == 4 and protocol["maximum_seconds_per_shard"] == 900
    assert protocol["pool_size"] == 1 and protocol["retries"] == protocol["mandatory_skips"] == 0
    assert protocol["bound_producer_cases_executed_by_checker_invocation"] == 0
    assert protocol["binding_invalid"] == "fail_closed_without_direct_fallback"
    assert protocol["completion_authority"] is False


def test_imported_source_receipt_hashes_actual_tracked_and_opaque_imports_without_scanning(tmp_path):
    from types import SimpleNamespace
    root = tmp_path / "source"; root.mkdir()
    source = root / "module.py"; source.write_text("SYNTHETIC = 1\n")
    nested = root / "external/ipfs_datasets_py/external/opaque/package.py"
    nested.parent.mkdir(parents=True); nested.write_text("SYNTHETIC = 2\n")
    unimported = nested.parent / "not_imported.py"; unimported.write_text("SYNTHETIC = 3\n")
    outside = tmp_path / "site_package.py"; outside.write_text("SYNTHETIC = 4\n")
    empty = root / "empty_package.py"; empty.write_text("")
    rows = {"tracked": SimpleNamespace(__file__=str(source)), "same_source_alias": SimpleNamespace(__file__=str(source)),
            "opaque": SimpleNamespace(__file__=str(nested)), "outside": SimpleNamespace(__file__=str(outside)),
            "empty_package": SimpleNamespace(__file__=str(empty)), "namespace": SimpleNamespace()}
    assert gate._imported_source_hashes(root, modules=rows) == {
        str(source): gate._hash(source), str(nested): gate._hash(nested), str(empty): gate._hash(empty)}
    assert str(unimported) not in gate._imported_source_hashes(root, modules=rows)


def test_imported_source_receipt_refuses_private_module_before_reading_bytes(monkeypatch, tmp_path):
    from types import SimpleNamespace
    private = tmp_path / "evidence/private_module.py"
    private.parent.mkdir(); private.write_text("SYNTHETIC_PRIVATE = True\n")
    monkeypatch.setattr(gate, "_hash", lambda path: pytest.fail("private module bytes must not be read"))
    with pytest.raises(RuntimeError, match="release_imported_private_source_denied"):
        gate._imported_source_hashes(tmp_path, modules={"private": SimpleNamespace(__file__=str(private))})


def test_imported_source_receipt_refuses_source_aliases(tmp_path):
    from types import SimpleNamespace
    root = tmp_path / "source"; root.mkdir()
    outside = tmp_path / "outside.py"; outside.write_text("SYNTHETIC = True\n")
    alias = root / "alias.py"; alias.symlink_to(outside)
    with pytest.raises(ValueError, match="path_alias_forbidden"):
        gate._imported_source_hashes(root, modules={"alias": SimpleNamespace(__file__=str(alias))})


def test_relative_virtual_namespace_file_is_not_candidate_filesystem_source(monkeypatch, tmp_path):
    from types import ModuleType
    class VirtualOps(ModuleType):
        __file__ = "_ops.py"
        def __init__(self):
            super().__init__("torch.ops")
    monkeypatch.chdir(tmp_path)
    virtual = VirtualOps()
    assert virtual.__spec__ is None and not (tmp_path / "_ops.py").exists()
    monkeypatch.setattr(gate, "_hash", lambda path: pytest.fail("unlocated virtual metadata is not a file to read"))
    assert gate._imported_source_hashes(tmp_path, modules={"torch.ops": virtual}) == {}


def test_relative_filesystem_module_source_is_hashed_and_missing_source_refused(monkeypatch, tmp_path):
    from types import ModuleType
    path = tmp_path / "ordinary.py"; path.write_text("SYNTHETIC = True\n")
    module = ModuleType("ordinary")
    module.__file__ = "ordinary.py"
    module.__spec__ = importlib.util.spec_from_file_location("ordinary", path)
    monkeypatch.chdir(tmp_path)
    assert gate._imported_source_hashes(tmp_path, modules={"ordinary": module}) == {str(path): gate._hash(path)}
    path.unlink()
    with pytest.raises(FileNotFoundError):
        gate._imported_source_hashes(tmp_path, modules={"ordinary": module})


def test_missing_absolute_imported_source_is_never_treated_as_virtual(tmp_path):
    from types import SimpleNamespace
    path = tmp_path / "deleted_ordinary.py"
    with pytest.raises(FileNotFoundError):
        gate._imported_source_hashes(tmp_path, modules={"ordinary": SimpleNamespace(__file__=str(path))})


@pytest.mark.parametrize("arguments", [
    ["submodule", "update", "--init", "--recursive"],
    ["submodule", "foreach", "--recursive", "echo unexpected"],
    ["submodule", "sync", "--recursive"],
    ["submodule", "status"], ["submodule", "status", "--recursive", "--", "outside"],
    ["-C", "/synthetic/outside", "submodule", "status", "--recursive"],
])
def test_submodule_metadata_exception_cannot_mutate_or_select_other_scope(monkeypatch, tmp_path, arguments):
    import shutil
    executable = Path(shutil.which("git", path=os.defpath)).resolve()
    monkeypatch.setitem(gate._GUARD, "source_root", str(ROOT))
    monkeypatch.setitem(gate._GUARD, "directory", str(tmp_path))
    monkeypatch.setitem(gate._GUARD, "executables", {str(executable): gate._hash(executable)})
    assert not gate.reviewed_process_dispatch(str(executable), [str(executable), *arguments], str(tmp_path), {})


def test_submodule_metadata_requires_owned_nonprivate_nonaliased_cwd(monkeypatch, tmp_path):
    import shutil
    executable = Path(shutil.which("git", path=os.defpath)).resolve()
    source, private, fixture, outside = (tmp_path / name for name in ("source", "source/evidence", "owned", "outside"))
    private.mkdir(parents=True); fixture.mkdir(); outside.mkdir()
    alias = tmp_path / "alias"; alias.symlink_to(fixture, target_is_directory=True)
    monkeypatch.setitem(gate._GUARD, "source_root", str(source))
    monkeypatch.setitem(gate._GUARD, "directory", str(fixture))
    monkeypatch.setitem(gate._GUARD, "executables", {str(executable): gate._hash(executable)})
    argv = [str(executable), "submodule", "status", "--recursive"]
    for path in (source, fixture):
        assert gate.reviewed_process_dispatch(str(executable), argv, str(path), {})
    for path in (private, outside, alias):
        assert not gate.reviewed_process_dispatch(str(executable), argv, str(path), {})


def _exercise_real_native_dependency_metadata_guard(connection, fixture):
    import subprocess
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import collect_dependency_state
    gate._GUARD.clear()
    os.chdir(ROOT)
    gate._install_guard(fixture.parent)
    try:
        observed = collect_dependency_state(fixture, changed_files=["pyproject.toml"])
        denied = []
        for operation in ("update", "sync", "foreach"):
            try:
                subprocess.run(["git", "submodule", operation, "--recursive"], cwd=fixture,
                               capture_output=True, check=False)
            except PermissionError as error:
                denied.append(str(error))
        connection.send({"actual_manifest_hash": observed["manifest_hashes"]["pyproject.toml"],
            "changed_files": observed["changed_files"], "gitlinks": observed["gitlinks"],
            "allowed_local_process": gate._GUARD["allowed_local_process"], "denied": denied})
    finally:
        connection.close()


def test_real_native_dependency_collector_consumes_exact_readonly_git_under_guard(tmp_path):
    import multiprocessing
    import shutil
    import subprocess
    fixture = tmp_path / "native-workspace"; fixture.mkdir(mode=0o700)
    source = fixture / "pyproject.toml"; source.write_text('[project]\nname="synthetic-local-fixture"\n')
    executable = str(Path(shutil.which("git", path=os.defpath)).resolve())
    subprocess.run([executable, "init", "-q"], cwd=fixture, capture_output=True, timeout=5, check=True)
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe(duplex=False)
    worker = context.Process(target=_exercise_real_native_dependency_metadata_guard, args=(child, fixture))
    worker.start(); child.close()
    try:
        worker.join(timeout=15)
        assert not worker.is_alive(), "Native dependency collector guard regression exceeded its deadline"
        assert worker.exitcode == 0 and parent.poll(1)
        result = parent.recv()
        assert result["actual_manifest_hash"] == gate._hash(source)
        assert result["changed_files"] == ["pyproject.toml"] and result["gitlinks"] == []
        assert result["allowed_local_process"] == 1
        assert result["denied"] == ["release_provider_or_unknown_process_denied"] * 3
    finally:
        if worker.is_alive():
            worker.kill(); worker.join(timeout=2)
        parent.close(); worker.close()


@pytest.mark.parametrize("name,arguments", [
    ("pgrep", ["-a", "-P", "1"]), ("pgrep", ["-f", "synthetic"]),
    ("pgrep", ["-P", "1,2"]), ("pgrep", ["-P", "0"]),
    ("pgrep", ["-P", "-1"]), ("ps", ["-eo", "pid=,args="]),
    ("ps", ["-o", "args=", "-p", "1"]), ("ps", ["-o", "args=", "-p", "1,2"]),
])
def test_process_metadata_does_not_admit_global_foreign_or_expanded_queries(monkeypatch, tmp_path, name, arguments):
    import shutil
    executable = Path(shutil.which(name, path=os.defpath)).resolve()
    identity = gate._pid_metadata(os.getpid())
    monkeypatch.setitem(gate._GUARD, "process_root", (os.getpid(), identity[1], identity[2]))
    monkeypatch.setitem(gate._GUARD, "executables", {str(executable): gate._hash(executable)})
    assert not gate.reviewed_process_dispatch(str(executable), [str(executable), *arguments], str(tmp_path), {})


def test_owned_process_metadata_rejects_a_changed_guard_root_birth(monkeypatch):
    identity = gate._pid_metadata(os.getpid())
    monkeypatch.setitem(gate._GUARD, "process_root", (os.getpid(), identity[1], identity[2]))
    assert gate._owned_metadata_pid(str(os.getpid()))
    monkeypatch.setitem(gate._GUARD, "process_root", (os.getpid(), identity[1] + 1, identity[2]))
    assert not gate._owned_metadata_pid(str(os.getpid()))


@pytest.mark.parametrize("arguments", [["clean", "-ffdx"], ["clean", "-ffd", "--", "file"],
    ["clean", "-n", "-ffd"], ["-C", "/synthetic/outside", "clean", "-ffd"]])
def test_git_cleanup_exception_cannot_expand_flags_or_paths(monkeypatch, tmp_path, arguments):
    import shutil
    executable = Path(shutil.which("git", path=os.defpath)).resolve()
    monkeypatch.setitem(gate._GUARD, "source_root", str(ROOT))
    monkeypatch.setitem(gate._GUARD, "directory", str(tmp_path))
    monkeypatch.setitem(gate._GUARD, "executables", {str(executable): gate._hash(executable)})
    assert not gate.reviewed_process_dispatch(str(executable), [str(executable), *arguments], str(tmp_path), {})


def test_git_cleanup_operation_does_not_intercept_a_commit_message(monkeypatch, tmp_path):
    import shutil
    executable = Path(shutil.which("git", path=os.defpath)).resolve()
    monkeypatch.setitem(gate._GUARD, "source_root", str(ROOT))
    monkeypatch.setitem(gate._GUARD, "directory", str(tmp_path))
    monkeypatch.setitem(gate._GUARD, "executables", {str(executable): gate._hash(executable)})
    assert gate.reviewed_process_dispatch(str(executable), [str(executable), "commit", "-m", "clean"], str(tmp_path), {})
    assert not gate.reviewed_process_dispatch(str(executable),
        [str(executable), "-C", str(tmp_path), "clean", "-ffd", "status"], str(tmp_path), {})


def test_git_cleanup_rejects_source_root_foreign_and_aliased_namespaces(monkeypatch, tmp_path):
    source, fixture, outside = (tmp_path / name for name in ("source", "owned", "outside"))
    for path in (source, fixture, outside):
        path.mkdir(); (path / ".git").mkdir()
    alias = tmp_path / "alias"; alias.symlink_to(fixture, target_is_directory=True)
    monkeypatch.setitem(gate._GUARD, "source_root", str(source))
    monkeypatch.setitem(gate._GUARD, "directory", str(fixture))
    assert gate._reviewed_git_cleanup_cwd(fixture)
    assert not any(gate._reviewed_git_cleanup_cwd(path) for path in (source, outside, alias))


def _exercise_actual_owned_metadata_and_cleanup_guard(connection, fixture):
    import subprocess
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.core import child_pids, parent_pid, process_args
    gate._GUARD.clear(); os.chdir(ROOT); gate._install_guard(fixture.parent)
    child = subprocess.Popen([sys.executable, "-I", "-S", "-B", "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert child.pid in child_pids(os.getpid())
        assert parent_pid(child.pid) == os.getpid()
        assert bool(process_args(child.pid))  # Assert internally; never export argv.
        assert child_pids(2**30) == []  # Native's normal exited-PID semantics.
        denied = []
        for command in (["ps", "-eo", "pid=,args="], ["ps", "-o", "args=", "-p", str(os.getppid())],
                        ["git", "clean", "-ffdx"]):
            try:subprocess.run(command, cwd=fixture, capture_output=True, check=False)
            except PermissionError as error:denied.append(str(error))
        temporary = fixture / "untracked-synthetic-file"; temporary.write_text("synthetic fixture only")
        subprocess.run(["git", "clean", "-ffd"], cwd=fixture, capture_output=True, check=True)
        assert not temporary.exists() and (fixture / ".git").exists()
        connection.send({"native_owned_metadata_verified": True, "dead_PID_empty": True,
                         "fixture_cleanup_verified": True, "denied": denied})
    finally:
        child.terminate()
        try:child.wait(timeout=2)
        except subprocess.TimeoutExpired:child.kill(); child.wait(timeout=2)
        connection.close()


def test_actual_native_owned_pid_metadata_and_fixture_cleanup_under_guard(tmp_path):
    import multiprocessing
    import shutil
    import subprocess
    fixture = tmp_path / "owned-worktree"; fixture.mkdir(mode=0o700)
    executable = str(Path(shutil.which("git", path=os.defpath)).resolve())
    subprocess.run([executable, "init", "-q"], cwd=fixture, capture_output=True, timeout=5, check=True)
    context = multiprocessing.get_context("fork"); parent, child = context.Pipe(duplex=False)
    worker = context.Process(target=_exercise_actual_owned_metadata_and_cleanup_guard, args=(child, fixture))
    worker.start(); child.close()
    try:
        worker.join(timeout=20)
        assert not worker.is_alive(), "Owned metadata/cleanup regression exceeded its deadline"
        assert worker.exitcode == 0 and parent.poll(1)
        assert parent.recv() == {"native_owned_metadata_verified": True, "dead_PID_empty": True,
            "fixture_cleanup_verified": True, "denied": ["release_provider_or_unknown_process_denied"] * 3}
    finally:
        if worker.is_alive():worker.kill(); worker.join(timeout=2)
        parent.close(); worker.close()


def _exact_replica_resource_fixture(monkeypatch, tmp_path):
    import cryptography
    import shutil
    directory = tmp_path / "owned"; directory.mkdir(mode=0o700)
    temporary = directory / "case"; temporary.mkdir(mode=0o700)
    workspace, home = temporary / "probe-workspace", temporary / "probe-home"
    workspace.mkdir(mode=0o700); home.mkdir(mode=0o700)
    operation = "deadline_publish"
    control = temporary / (operation + "-barrier"); control.mkdir(mode=0o700)
    python = Path(sys.executable).resolve()
    executable = Path(shutil.which("prlimit", path=os.defpath)).resolve()
    packages = Path(cryptography.__file__).resolve().parents[1]
    monkeypatch.setitem(gate._GUARD, "source_root", str(ROOT))
    monkeypatch.setitem(gate._GUARD, "directory", str(directory))
    monkeypatch.setitem(gate._GUARD, "python", str(python))
    monkeypatch.setitem(gate._GUARD, "executables", {str(path): gate._hash(path) for path in (python, executable)})
    monkeypatch.setitem(gate._GUARD, "approved_roots", [packages])
    literal = gate._reviewed_replica_probe_literal()
    assert isinstance(literal, str) and literal
    argv = [str(executable), "--core=0:0", "--cpu=4:4", "--as=536870912:536870912", "--",
        str(python), "-I", "-S", "-B", "-c", literal, str(os.getpid()), str(ROOT), str(workspace), operation,
        str(packages), str(control)]
    environment = {"PATH": os.defpath, "HOME": str(home), "TMPDIR": str(temporary),
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "IPFS_DATASETS_MANAGED_PROCESS_ID": "1" * 32, "IPFS_DATASETS_PROCESS_SUPERVISOR_ID": "2" * 32}
    return executable, workspace, argv, environment


def test_exact_bounded_replica_probe_requires_real_immutable_companion_source(monkeypatch, tmp_path):
    executable, workspace, argv, environment = _exact_replica_resource_fixture(monkeypatch, tmp_path)
    assert gate._hash(ROOT / "tests/test_private_replica_acceptance.py") == gate._REPLICA_COMPANION_SHA256
    assert gate.reviewed_process_dispatch(str(executable), argv, str(workspace), environment)
    monkeypatch.setattr(gate, "_REPLICA_COMPANION_SHA256", "0" * 64)
    assert not gate.reviewed_process_dispatch(str(executable), argv, str(workspace), environment)


@pytest.mark.parametrize("damage", ["code", "cpu", "memory", "python", "owner", "source", "operation",
    "workspace", "packages", "barrier", "environment", "managed_id"])
def test_replica_exception_rejects_any_changed_resource_or_custody_envelope(monkeypatch, tmp_path, damage):
    executable, workspace, argv, environment = _exact_replica_resource_fixture(monkeypatch, tmp_path)
    if damage == "code":argv[10] += "\n# changed probe source"
    elif damage == "cpu":argv[2] = "--cpu=5:5"
    elif damage == "memory":argv[3] = "--as=1073741824:1073741824"
    elif damage == "python":
        foreign = tmp_path / "python"; foreign.write_text("synthetic untrusted interpreter"); foreign.chmod(0o700); argv[5] = str(foreign)
    elif damage == "owner":argv[11] = str(os.getpid() + 1)
    elif damage == "source":argv[12] = str(tmp_path)
    elif damage == "operation":argv[14] = "unreviewed_operation"
    elif damage == "workspace":argv[13] = str(workspace.parent)
    elif damage == "packages":argv[15] = str(workspace.parent)
    elif damage == "barrier":argv[16] = str(workspace.parent)
    elif damage == "environment":environment["LD_PRELOAD"] = "/synthetic/untrusted.so"
    elif damage == "managed_id":environment["IPFS_DATASETS_MANAGED_PROCESS_ID"] = "not-a-managed-identity"
    assert not gate.reviewed_process_dispatch(str(executable), argv, str(workspace), environment)


def _exercise_real_replica_probe_with_paused_publication(connection, fixture):
    import threading
    # The real source defines the complete custody and product probe. Loading
    # definitions does not run its pytest fixtures or substitute a probe body.
    name = "_complaint_actual_replica_atomic_publication_regression"
    specification = importlib.util.spec_from_file_location(name, ROOT / "tests/test_private_replica_acceptance.py")
    companion = importlib.util.module_from_spec(specification)
    sys.modules[name] = companion
    specification.loader.exec_module(companion)
    assert gate._hash(Path(companion.__file__)) == gate._REPLICA_COMPANION_SHA256
    gate._kernel_network_deny()
    operation = "deadline_publish"
    control = fixture / (operation + "-barrier")
    go = control / "go"
    created, observed = threading.Event(), threading.Event()
    observations, errors, publications = [], [], []
    original_open, original_link = os.open, os.link

    def observer():
        try:
            assert created.wait(3), "Real probe never reached its publication gap"
            # The producer is stopped inside os.open, before its first write.
            # Old O_CREAT('go') deterministically exposed an empty final here.
            assert not go.exists(), "Release barrier became visible before its bytes were complete"
            observations.append("final_absent_before_write")
        except BaseException as error:
            errors.append(str(error))
        finally:
            observed.set()

    def paused_open(path, flags, *args, **kwargs):
        descriptor = original_open(path, flags, *args, **kwargs)
        if isinstance(path, (str, bytes, os.PathLike)) and Path(os.fsdecode(path)).parent == control and flags & os.O_CREAT:
            try:
                created.set()
                assert observed.wait(3), "Publication observer did not finish"
                assert not errors, errors
            except BaseException:
                os.close(descriptor)
                raise
        return descriptor

    def observed_link(source, destination, *args, **kwargs):
        result = original_link(source, destination, *args, **kwargs)
        if Path(destination) == go:
            assert go.read_bytes() == b"go", "Atomic release publication exposed incomplete bytes"
            publications.append("complete_at_link")
        return result

    watcher = threading.Thread(target=observer)
    watcher.start()
    os.open, os.link = paused_open, observed_link
    try:
        value = companion._probe(fixture, operation)
        assert value["operation"] == operation and value["bounded_unavailable"] is True
        assert observations == ["final_absent_before_write"] and publications == ["complete_at_link"]
        assert not errors and go.read_bytes() == b"go"
        connection.send({"actual_probe_completed": True, "bounded_unavailable": True,
            "publication_gap_observed": True, "complete_at_publication": True})
    finally:
        os.open, os.link = original_open, original_link
        created.set(); watcher.join(timeout=3)
        assert not watcher.is_alive(), "Publication observer remained active"
        connection.close()


def test_actual_replica_probe_never_exposes_go_during_forced_prewrite_gap(tmp_path):
    import multiprocessing
    fixture = tmp_path / "atomic-probe"; fixture.mkdir(mode=0o700)
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe(duplex=False)
    worker = context.Process(target=_exercise_real_replica_probe_with_paused_publication, args=(child, fixture))
    worker.start(); child.close()
    try:
        worker.join(timeout=20)
        assert not worker.is_alive(), "Actual replica publication regression exceeded its deadline"
        assert worker.exitcode == 0 and parent.poll(1)
        assert parent.recv() == {"actual_probe_completed": True, "bounded_unavailable": True,
            "publication_gap_observed": True, "complete_at_publication": True}
    finally:
        if worker.is_alive():worker.kill(); worker.join(timeout=2)
        parent.close(); worker.close()


@pytest.mark.parametrize("now,cancelled,exception", [(9.0, True, InterruptedError),
    (10.0, True, TimeoutError), (11.0, True, TimeoutError), (10.0, False, TimeoutError)])
def test_real_proof_manager_classifies_execution_boundary_before_generic_signal(now, cancelled, exception):
    import ast
    from types import SimpleNamespace
    from integrations.ipfs_datasets import logic
    definitions = [node for node in ast.parse(logic._PROOF_ROUTER_MANAGER_SOURCE).body
                   if isinstance(node, ast.FunctionDef) and node.name == "check_execution"]
    assert len(definitions) == 1
    # Execute only the real production predicate, with an exact clock boundary.
    # No manager bootstrap, subprocess, fabricated stdout, or evidence runs here.
    namespace = {"time": SimpleNamespace(monotonic=lambda: now), "execution_deadline": 10.0,
                 "cancelled": cancelled}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), "actual-proof-manager-check", "exec"), namespace)
    with pytest.raises(exception):
        namespace["check_execution"]()


@pytest.mark.parametrize("stop", ["timeout", "cancelled"])
def test_real_owner_stop_cause_overrides_generic_manager_term_envelope(monkeypatch, tmp_path, stop):
    from types import SimpleNamespace
    from integrations.ipfs_datasets import logic
    assert logic._process_lifecycle_module is not None
    fixture_name = "_complaint_actual_proof_routing_stop_cause_fixture"
    specification = importlib.util.spec_from_file_location(fixture_name,
        ROOT / "tests/test_legal_ir_proof_routing_adapter.py")
    fixture = importlib.util.module_from_spec(specification)
    monkeypatch.setitem(sys.modules, fixture_name, fixture)
    specification.loader.exec_module(fixture)
    ready = tmp_path / "manager-awaiting-owner-signal"
    marker = " global request_verified\n check_execution()\n"
    source = logic._PROOF_ROUTER_MANAGER_SOURCE
    assert source.count(marker) == 1
    # This inert manager reaches the real DataSupervisor and waits for its real
    # SIGTERM. Raising InterruptedError reproduces the ambiguous manager envelope
    # independently of the manager's deadline-ordering repair. No result JSON,
    # owner flags or stop outcome is injected into the production parent.
    waiting = (" global request_verified\n"
        + f" with open({str(ready)!r},'wb') as stream:stream.write(b'ready')\n"
        + " while not cancelled:time.sleep(.002)\n"
        + " raise InterruptedError()\n check_execution()\n")
    monkeypatch.setattr(logic, "_PROOF_ROUTER_MANAGER_SOURCE", source.replace(marker, waiting, 1))
    if stop == "cancelled":
        # Model post-owner bookkeeping finishing beyond the original deadline,
        # while leaving DataSupervisor's real clock, cancellation and limits
        # untouched. Its explicit cancellation must remain the terminal cause.
        owner_returned = [False]
        real_time = logic.time
        real_run = logic._process_lifecycle_module.ProcessSupervisor.run
        def actual_cancel_then_late_bookkeeping(self, *args, **kwargs):
            result = real_run(self, *args, **kwargs)
            assert result.cancelled is True and result.timed_out is False
            owner_returned[0] = True
            return result
        monkeypatch.setattr(logic._process_lifecycle_module.ProcessSupervisor, "run", actual_cancel_then_late_bookkeeping)
        monkeypatch.setattr(logic, "time", SimpleNamespace(monotonic=lambda:
            real_time.monotonic() + (3.0 if owner_returned[0] else 0.0)))
    class CallerCancellation:
        def is_set(self):
            return stop == "cancelled" and ready.exists()
    owned = tmp_path / "owned"
    routed = fixture._route(managed_state_directory=str(owned), cancellation_event=CallerCancellation())
    assert ready.exists()
    assert routed["outcome"] == stop
    process = routed["process"]
    assert process["termination_reason"] == ("wall_clock_deadline" if stop == "timeout" else "cancelled")
    assert process["cancelled"] is (stop == "cancelled")
    assert process["timed_out"] is True
    assert process["process_group_reaped"] is True and process["router_tree_reaped"] is True
    assert process["actual_router_started"] is False
    assert routed["substantive_trust_satisfied"] is False and routed["entails_claim_element"] is False
    assert list(owned.iterdir()) == []


def test_current_source_binding_explicitly_includes_owned_proof_logic():
    assert gate.LOGIC_RELATIVE == "integrations/ipfs_datasets/logic.py"
    assert gate.LOGIC_RELATIVE in gate.BOUND_SOURCE_PATHS
