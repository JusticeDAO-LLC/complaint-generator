"""Current-source behavioral evidence is the only task-completion authority.

Unit fakes, optional provider smoke, empty collection, skips, stale hashes,
missing outputs, failed assertions and subprocess timeouts stay repairable
rejections. Dependent readiness is recomputed from the stored receipts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.ipfs_accelerate.improvement_plan import (
    SEALED_ENVIRONMENT_POLICY,
    assess_behavioral_evidence,
    bind_sources,
    canonical_model_policy,
)
from integrations.ipfs_accelerate.improvement_runner import (
    gate_task_completion,
    recompute_dependent_readiness,
)


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

COMMAND = "python -m pytest -q --run-llm --run-network --run-heavy tests/test_improvement_evidence_gate.py"
NODE_A = "tests/test_improvement_evidence_gate.py::test_local_node_evidence_completes_and_readies_dependent"
NODE_B = "tests/test_improvement_evidence_gate.py::test_recompute_invalidates_dependents"


@pytest.fixture(autouse=True)
def _explicit_new_rel03_parent_baseline(tmp_path, monkeypatch, request):
    """Retain the original new-output scenario for five synthetic REL03 cases.

    The real release gate did not exist in their installed parent source.
    Production test preservation stays enabled; only this explicit unit parent
    supplies that original absence while copying the real phase bootstrap.
    """
    names = {
        "test_exact_rel03_script_and_trusted_behavioral_companion_are_both_required",
        "test_real_rel03_two_command_contract_preserves_each_command_identity",
        "test_rel03_unknown_extra_command_does_not_gain_script_companion_dispatch",
    }
    if getattr(request.node, "originalname", None) not in names:
        return
    from integrations.ipfs_accelerate import improvement_runner as runner
    actual = Path(runner.__file__).resolve().parents[2]
    parent = tmp_path.parent / ("trusted-rel03-parent-" + tmp_path.name)
    parent.mkdir(mode=0o700)
    bootstrap = parent / "integrations/ipfs_accelerate/improvement_plan.py"
    bootstrap.parent.mkdir(parents=True)
    bootstrap.write_bytes((actual / "integrations/ipfs_accelerate/improvement_plan.py").read_bytes())
    assert not (parent / "tests/test_intake_release_gate.py").exists()
    monkeypatch.setattr(runner, "__file__", str(bootstrap.with_name("improvement_runner.py")))


def _task(task_id: str = "CIMP-OPS-04", *, depends=None, command: str = COMMAND) -> dict:
    return {
        "id": task_id,
        "targets": [f"out/{task_id}.py"],
        "validation_commands": [command],
        "depends_on": list(depends or []),
    }


def _environment() -> dict:
    return {**SEALED_ENVIRONMENT_POLICY, "HOME": "/tmp/ipfs-accelerate-validation-home-evidence"}


def _write_output(root: Path, task_id: str, body: str = "def ready():\n    return True\n") -> str:
    path = root / "out" / f"{task_id}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    artifact = root / "artifacts" / f"{task_id}.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps({"task_id": task_id, "body": body}), encoding="utf-8")
    return str(path.relative_to(root))


def _observation(root: Path, task_id: str = "CIMP-OPS-04", **overrides) -> dict:
    binding = bind_sources(root, [f"out/{task_id}.py"])
    artifact = root / "artifacts" / f"{task_id}.json"
    value = {
        "lane": "local_node_integration",
        "command": COMMAND,
        "exit_status": 0,
        "timed_out": False,
        "collected_count": 2,
        "cases": [
            {"nodeid": NODE_A, "outcome": "passed"},
            {"nodeid": NODE_B, "outcome": "passed"},
        ],
        "required_nodeids": [NODE_A, NODE_B],
        "environment": _environment(),
        "source_binding": binding,
        "artifacts": [{"relative_path": artifact.relative_to(root).as_posix()}],
    }
    value.update(overrides)
    return value


def _spec(*tasks: dict) -> dict:
    return {"tasks": list(tasks)}


def _gate(tmp_path: Path, task: dict, observation: dict, **kwargs) -> dict:
    # Migrate the positive prerequisite to an actual owned sealed pytest run.
    # Old defect assertions still alter claimed metadata, while the host also
    # independently verifies collection/JUnit/phases/current AST and source.
    from integrations.ipfs_accelerate.improvement_runner import measure_behavioral_command
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import build_validation_environment, validation_environment_for_runner
    import os
    import subprocess
    measurement_fault = kwargs.pop("_measurement_fault", None)
    measurement_context = kwargs.pop("_measurement_context", {})
    if observation.get("lane") == "local_node_integration" and all((tmp_path / p).is_file() for p in task["targets"]):
        tests = tmp_path / "tests"
        tests.mkdir(exist_ok=True)
        (tmp_path / "conftest.py").write_text("def pytest_addoption(parser):\n for flag in ('--run-llm','--run-network','--run-heavy'): parser.addoption(flag, action='store_true')\n")
        (tmp_path / "complaint_fixture_guard.py").write_text("""import json, socket, sys
import os, stat, tempfile
from pathlib import Path
from collections import Counter
_fixture = Path(__file__).resolve().parent
_control = _fixture / 'nested-fixture-control-plane'
_temporary = _fixture / 'nested-fixture-tmp'
for _path in (_control, _temporary):
 _path.mkdir(mode=0o700, exist_ok=True)
 _info = _path.lstat()
 if _path.resolve(strict=True) != _path or not stat.S_ISDIR(_info.st_mode) or _info.st_uid != os.getuid() or stat.S_IMODE(_info.st_mode) != 0o700:
  raise AssertionError('nested_fixture_namespace_not_owned')
os.environ['IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR'] = str(_control)
os.environ['IPFS_ACCELERATE_META_INDEX_DUCKDB'] = ''
os.environ['IPFS_ACCELERATE_META_INDEX_DUCKLAKE'] = ''
os.environ['IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD'] = '0'
os.environ['TMPDIR'] = str(_temporary)
tempfile.tempdir = str(_temporary)
_counts = Counter()
def _audit(event, args):
 if event in {'subprocess.Popen', 'os.system', 'os.exec', 'os.fork', 'os.forkpty', 'os.posix_spawn', 'os.spawn'}:
  _counts['denied_process'] += 1
  raise AssertionError('nested_fixture_process_denied')
 network = event in {'socket.getaddrinfo', 'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.getnameinfo'}
 network = network or event == 'socket.__new__' and args[1] in (socket.AF_INET, socket.AF_INET6)
 network = network or event in {'socket.connect', 'socket.sendto'} and args[0].family in (socket.AF_INET, socket.AF_INET6)
 if network:
  _counts['denied_network'] += 1
  raise AssertionError('nested_fixture_network_denied')
sys.addaudithook(_audit)
def pytest_sessionfinish(session, exitstatus):
 path=Path(session.config.getoption('--complaint-evidence-path')).with_suffix('.guard.json')
 path.write_text(json.dumps({'schema':'complaint-nested-fixture-egress@1','exitstatus':int(exitstatus),'denied_attempts':dict(_counts),'network_process_dispatch_permitted':False,'guard_load_order':'explicit first -p before AST and phase plugins; pytest bootstrap precedes guard','private_namespaces':{'orchestration_dir':str(_control),'tmpdir':str(_temporary),'meta_index_duckdb_disabled':os.environ.get('IPFS_ACCELERATE_META_INDEX_DUCKDB')=='','meta_index_ducklake_disabled':os.environ.get('IPFS_ACCELERATE_META_INDEX_DUCKLAKE')=='','nltk_auto_download':os.environ.get('IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD')}}))
 path.chmod(0o600)
""")
        adapter = tmp_path / "adapter.py"
        if not adapter.exists(): adapter.write_text("VERSION=1\n")
        names = [node.rsplit("::", 1)[1] for node in (NODE_A, NODE_B)]
        claims = observation.get("cases")
        outcomes = [row.get("outcome") for row in claims] if isinstance(claims, list) and all(isinstance(row, dict) for row in claims) else []
        bodies = []
        for index, name in enumerate(names):
            outcome = outcomes[index] if index < len(outcomes) else "passed"
            body = "pytest.skip('synthetic required skip')" if outcome == "skipped" else "assert False, 'synthetic required failure'" if outcome == "failed" else "assert adapter.VERSION > 0"
            bodies.append("def " + name + "(): " + body)
        (tests / "test_improvement_evidence_gate.py").write_text("import adapter, pytest\n" + "\n".join(bodies))
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "add", "out", "tests", "conftest.py", "adapter.py", "complaint_fixture_guard.py"], check=True)
        native = PortalImplementationDaemon._validation_command_runner
        import shlex
        from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native_source
        # The parent may already have imported these modules while its runtime
        # sys.path was changed by another synthetic campaign. Bind the child to
        # these exact first-party/native source origins plus approved packages.
        source_env = dict(os.environ)
        source_env.pop("IPFS_ACCELERATE_AGENT_VALIDATION_PYTHON", None)
        env = build_validation_environment(source_env)
        roots = [tmp_path.resolve(), Path(__file__).resolve().parents[1],
                 Path(native_source.__file__).resolve().parents[3],
                 Path(pytest.__file__).resolve().parents[1]]
        roots += [Path(p).resolve() for p in env.get("PYTHONPATH", "").split(os.pathsep)
                  if p and Path(p).is_absolute() and Path(p).is_dir()]
        env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(map(str, roots)))
        env = validation_environment_for_runner(env, native)
        # Native scheduler environment rebuilding intentionally strips ambient
        # source roots. The actual fixture command must carry its owned roots.
        source_command = "PYTHONPATH=" + shlex.quote(env["PYTHONPATH"]) + " " + COMMAND
        def delegate(**call):
            result = native(**call)
            command = call["spec"].command
            if measurement_fault and "--collect-only" not in command and result.get("returncode") == 0:
                import shlex
                tokens = shlex.split(command)
                manifest = Path(next(t.split("=", 1)[1] for t in tokens if t.startswith("--complaint-evidence-path=")))
                if measurement_fault == "junit": (manifest.parent / "junit.xml").unlink()
                elif measurement_fault == "phases": manifest.unlink()
                elif measurement_fault == "catalog": manifest.with_suffix(".duckdb").unlink()
                elif measurement_fault == "population":
                    value = json.loads(manifest.read_text()); value["nodeids"].pop(); manifest.write_text(json.dumps(value))
                elif measurement_fault == "source": adapter.write_text("VERSION=99\n")
            return result
        measured = measure_behavioral_command(tmp_path, tmp_path / "state" / "runs", task, source_command,
                                               runner=delegate, environment=env, timeout_seconds=45, declared_command=COMMAND,
                                               context={"require_child_guard": True, "pytest_guard_plugin": "complaint_fixture_guard", **measurement_context})
        from integrations.ipfs_accelerate.improvement_runner import _observed_artifacts
        observation["artifacts"] = _observed_artifacts(tmp_path, observation)
        if all(a["present"] for a in observation["artifacts"]):
            observation.pop("artifacts")  # host-measured artifacts, not authored claims
        observation.pop("environment", None)
        measured.update(observation)
        observation = measured
        if kwargs.pop("_return_measurement", False):
            return observation, native, env
    return gate_task_completion(
        tmp_path, tmp_path / "state", task, observation,
        facts=kwargs.pop("facts", {"narrative": "synthetic"}),
        model_policy=kwargs.pop("model_policy", canonical_model_policy()),
        legal_data_version=kwargs.pop("legal_data_version", "legal-2026-10-21"),
        spec=kwargs.pop("spec", None), **kwargs,
    )


def test_local_node_evidence_completes_and_readies_dependent(tmp_path: Path) -> None:
    _write_output(tmp_path, "CIMP-OPS-01")
    _write_output(tmp_path, "CIMP-OPS-04")
    upstream = _task("CIMP-OPS-01")
    downstream = _task("CIMP-OPS-04", depends=["CIMP-OPS-01"])
    spec = _spec(upstream, downstream)
    first = _gate(tmp_path, upstream, _observation(tmp_path, "CIMP-OPS-01"), spec=spec)
    assert first["completion"] is True
    assert first["reason"] == "current_source_behavioral_evidence"
    assert first["repairable"] is False
    assert first["readiness"]["tasks"]["CIMP-OPS-01"]["complete"] is True
    assert first["readiness"]["tasks"]["CIMP-OPS-04"]["ready"] is True
    assert first["readiness"]["tasks"]["CIMP-OPS-04"]["complete"] is False
    assert first["readiness"]["tasks"]["CIMP-OPS-04"]["reason"] == "missing_behavioral_evidence"
    second = _gate(tmp_path, downstream, _observation(tmp_path, "CIMP-OPS-04"), spec=spec)
    assert second["completion"] is True
    assert second["exit_status"] == 0
    assert second["command"] == COMMAND
    assert second["environment_policy"]["required"]["PATH"] == SEALED_ENVIRONMENT_POLICY["PATH"]
    assert second["environment_policy"]["required"]["python"] == "/usr/bin/python3.12"
    assert second["source_binding"]["digest"]
    assert second["required_cases"][0]["nodeid"] == NODE_A
    assert second["artifacts"][0]["present"] is True
    assert second["artifacts"][0]["sha256"]
    assert second["native_validation"]["verdict_kind"] == "test"
    stored = json.loads((tmp_path / "state/evidence/CIMP-OPS-04/completion.json").read_text(encoding="utf-8"))
    lane = json.loads((tmp_path / "state/evidence/CIMP-OPS-04/local_node_integration.json").read_text(encoding="utf-8"))
    assert stored == lane
    assert stored["facts_digest"] and stored["legal_data_version"] == "legal-2026-10-21"
    assert second["readiness"]["tasks"]["CIMP-OPS-04"]["ready"] is True
    assert second["readiness"]["tasks"]["CIMP-OPS-04"]["complete"] is True


@pytest.mark.parametrize("overrides,reason", [
    ({"collected_count": 0, "cases": [], "required_nodeids": []}, "zero_test_collection"),
    ({"cases": [
        {"nodeid": NODE_A, "outcome": "skipped"},
        {"nodeid": NODE_B, "outcome": "passed"},
    ]}, "skipped_required_case"),
    ({"cases": [
        {"nodeid": NODE_A, "outcome": "failed"},
        {"nodeid": NODE_B, "outcome": "passed"},
    ], "exit_status": 1}, "failed_assertion"),
    ({"timed_out": True, "exit_status": None}, "subprocess_timeout"),
    ({"source_binding": {"files": {"out/CIMP-OPS-04.py": {"sha256": "0" * 64}}}}, "stale_source_hash"),
    ({"artifacts": [{"relative_path": "artifacts/missing.json"}]}, "missing_output"),
])
def test_defective_local_evidence_cannot_complete(tmp_path: Path, overrides: dict, reason: str) -> None:
    _write_output(tmp_path, "CIMP-OPS-04")
    receipt = _gate(tmp_path, _task(), _observation(tmp_path, **overrides))
    assert receipt["completion"] is False
    assert receipt["admitted"] is False
    assert receipt["repairable"] is True
    assert receipt["reason"] == reason
    assert "command" in receipt and "exit_status" in receipt
    assert receipt["required_cases"] is not None
    stored = json.loads((tmp_path / "state/evidence/CIMP-OPS-04/completion.json").read_text(encoding="utf-8"))
    assert stored["reason"] == reason and stored["completion"] is False


def test_missing_declared_output_rejects_before_completion(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "CIMP-OPS-04.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")
    observation = _observation(tmp_path)
    observation["source_binding"] = None
    receipt = _gate(tmp_path, _task(), observation)
    assert receipt["reason"] == "missing_output"
    assert receipt["completion"] is False
    assert receipt["repairable"] is True


def test_unit_fake_and_provider_smoke_are_distinct_and_cannot_complete(tmp_path: Path) -> None:
    _write_output(tmp_path, "CIMP-OPS-04")
    task = _task()
    fake = _gate(tmp_path, task, _observation(tmp_path, lane="unit_fake", environment={"PATH": "/tmp/fake"}))
    smoke = _gate(tmp_path, task, _observation(tmp_path, lane="optional_real_provider_smoke"))
    assert fake["reason"] == "unit_fake_is_not_current_source_completion"
    assert smoke["reason"] == "optional_real_provider_smoke_is_not_completion"
    assert fake["completion"] is smoke["completion"] is False
    assert fake["repairable"] is smoke["repairable"] is True
    assert (tmp_path / "state/evidence/CIMP-OPS-04/unit_fake.json").is_file()
    assert (tmp_path / "state/evidence/CIMP-OPS-04/optional_real_provider_smoke.json").is_file()
    assert not (tmp_path / "state/evidence/CIMP-OPS-04/completion.json").exists()


def test_failed_smoke_does_not_erase_admitted_local_evidence(tmp_path: Path) -> None:
    _write_output(tmp_path, "CIMP-OPS-04")
    task = _task()
    admitted = _gate(tmp_path, task, _observation(tmp_path))
    failed = _observation(tmp_path, lane="optional_real_provider_smoke", exit_status=1,
                          cases=[{"nodeid": NODE_A, "outcome": "failed"}, {"nodeid": NODE_B, "outcome": "passed"}])
    smoke = _gate(tmp_path, task, failed)
    stored = json.loads((tmp_path / "state/evidence/CIMP-OPS-04/completion.json").read_text(encoding="utf-8"))
    assert admitted["completion"] is True
    assert smoke["reason"] == "failed_assertion"
    assert smoke["lane"] == "optional_real_provider_smoke"
    assert stored["completion"] is True
    assert stored["lane"] == "local_node_integration"


def test_recompute_invalidates_dependents(tmp_path: Path) -> None:
    _write_output(tmp_path, "CIMP-OPS-01", "def upstream():\n    return 1\n")
    _write_output(tmp_path, "CIMP-OPS-04")
    upstream = _task("CIMP-OPS-01")
    downstream = _task("CIMP-OPS-04", depends=["CIMP-OPS-01"])
    spec = _spec(upstream, downstream)
    facts = {"narrative": "synthetic"}
    _gate(tmp_path, upstream, _observation(tmp_path, "CIMP-OPS-01"), facts=facts, spec=spec)
    _gate(tmp_path, downstream, _observation(tmp_path, "CIMP-OPS-04"), facts=facts, spec=spec)
    _write_output(tmp_path, "CIMP-OPS-01", "def upstream():\n    return 2\n")
    stale = recompute_dependent_readiness(
        tmp_path, tmp_path / "state", spec, facts=facts,
        model_policy=canonical_model_policy(), legal_data_version="legal-2026-10-21",
    )
    assert stale["tasks"]["CIMP-OPS-01"]["complete"] is False
    assert stale["tasks"]["CIMP-OPS-01"]["reason"] == "stale_source_hash"
    assert stale["tasks"]["CIMP-OPS-01"]["repairable"] is True
    assert stale["tasks"]["CIMP-OPS-04"]["complete"] is False
    assert stale["tasks"]["CIMP-OPS-04"]["ready"] is False
    assert stale["tasks"]["CIMP-OPS-04"]["reason"] == "upstream_evidence_not_current"
    restored = bind_sources(tmp_path, ["out/CIMP-OPS-01.py"])
    _gate(tmp_path, upstream, _observation(tmp_path, "CIMP-OPS-01", source_binding=restored), facts=facts, spec=spec)
    _gate(tmp_path, downstream, _observation(tmp_path, "CIMP-OPS-04"), facts=facts, spec=spec)
    changed_policy = recompute_dependent_readiness(
        tmp_path, tmp_path / "state", spec, facts=facts,
        model_policy={**canonical_model_policy(), "allow_fallback": True},
        legal_data_version="legal-2026-10-21",
    )
    assert changed_policy["tasks"]["CIMP-OPS-01"]["reason"] == "model_policy_changed"
    assert changed_policy["tasks"]["CIMP-OPS-04"]["ready"] is False
    _gate(tmp_path, upstream, _observation(tmp_path, "CIMP-OPS-01", source_binding=restored), facts=facts, spec=spec)
    _gate(tmp_path, downstream, _observation(tmp_path, "CIMP-OPS-04"), facts=facts, spec=spec)
    changed_legal = recompute_dependent_readiness(
        tmp_path, tmp_path / "state", spec, facts=facts,
        model_policy=canonical_model_policy(), legal_data_version="legal-2026-11-01",
    )
    assert changed_legal["tasks"]["CIMP-OPS-01"]["reason"] == "legal_data_version_changed"
    assert changed_legal["tasks"]["CIMP-OPS-04"]["blocked_by"] == ["CIMP-OPS-01"]
    _gate(tmp_path, upstream, _observation(tmp_path, "CIMP-OPS-01", source_binding=restored), facts=facts, spec=spec)
    _gate(tmp_path, downstream, _observation(tmp_path, "CIMP-OPS-04"), facts=facts, spec=spec)
    corrected = recompute_dependent_readiness(
        tmp_path, tmp_path / "state", spec, facts={"narrative": "corrected"},
        model_policy=canonical_model_policy(), legal_data_version="legal-2026-10-21",
    )
    assert corrected["tasks"]["CIMP-OPS-01"]["reason"] == "corrected_facts"
    assert corrected["tasks"]["CIMP-OPS-04"]["repairable"] is True
    persisted = json.loads((tmp_path / "state/evidence/CIMP-OPS-01/completion.json").read_text(encoding="utf-8"))
    assert persisted["reason"] == "corrected_facts" and persisted["completion"] is False


def test_assess_rejects_non_test_command_and_wrong_model_policy(tmp_path: Path) -> None:
    _write_output(tmp_path, "CIMP-OPS-04")
    binding = bind_sources(tmp_path, ["out/CIMP-OPS-04.py"])
    command = "python -m py_compile out/CIMP-OPS-04.py"
    task = _task(command=command)
    observation = _observation(tmp_path, command=command)
    receipt = assess_behavioral_evidence(task, observation, source_binding=binding)
    assert receipt["reason"] == "command_not_behavioral_test"
    assert receipt["completion"] is False
    rejected = assess_behavioral_evidence(
        _task(), _observation(tmp_path), source_binding=binding,
        model_policy={**canonical_model_policy(), "model": "other"},
    )
    assert rejected["reason"] == "model_policy_rejected"
    assert rejected["repairable"] is True


def test_caller_report_without_host_measurement_is_not_admitted(tmp_path):
    _write_output(tmp_path, "CIMP-OPS-04")
    receipt = gate_task_completion(tmp_path, tmp_path / "state", _task(), _observation(tmp_path))
    assert receipt["completion"] is False
    assert receipt["completion_authority"] is False
    assert receipt["reason"] == "host_measurement_required"


def test_missing_execution_time_binding_is_not_admitted(tmp_path):
    _write_output(tmp_path, "CIMP-OPS-04")
    receipt = gate_task_completion(tmp_path, tmp_path / "state", _task(), _observation(tmp_path, source_binding=None))
    assert receipt["completion"] is False
    assert receipt["repairable"] is True


def test_malformed_required_nodeid_is_typed_rejection(tmp_path):
    _write_output(tmp_path, "CIMP-OPS-04")
    receipt = _gate(tmp_path, _task(), _observation(tmp_path, required_nodeids=[[NODE_A]]))
    assert receipt["completion"] is False
    assert receipt["repairable"] is True


def test_imported_adapter_change_invalidates_prior_measurement(tmp_path):
    _write_output(tmp_path, "CIMP-OPS-04")
    adapter = tmp_path / "adapter.py"
    adapter.write_text("VERSION=1\n")
    observed = _observation(tmp_path)
    observed["execution_sources"] = bind_sources(tmp_path, ["adapter.py"])
    _gate(tmp_path, _task(), observed)
    adapter.write_text("VERSION=2\n")
    readiness = recompute_dependent_readiness(tmp_path, tmp_path / "state", _spec(_task()))
    assert readiness["tasks"]["CIMP-OPS-04"]["complete"] is False


@pytest.mark.parametrize("fault,reason", [("junit", "missing_output"), ("phases", "missing_phase_manifest"),
    ("catalog", "missing_output"), ("population", "collection_identity_mismatch"), ("source", "stale_source_hash")])
def test_actual_measured_artifacts_and_source_are_required(tmp_path, fault, reason):
    _write_output(tmp_path, "CIMP-OPS-04")
    receipt = _gate(tmp_path, _task(), _observation(tmp_path), _measurement_fault=fault)
    assert receipt["completion"] is False and receipt["admitted"] is False
    assert receipt["reason"] == reason and receipt["repairable"] is True
    assert receipt["completion_authority"] is False


def test_serialized_measured_receipt_cannot_recreate_host_capability(tmp_path):
    _write_output(tmp_path, "CIMP-OPS-04")
    original = _gate(tmp_path, _task(), _observation(tmp_path))
    receipt = gate_task_completion(tmp_path, tmp_path / "other-state", _task(), json.loads(json.dumps(original)), legal_data_version="synthetic")
    assert receipt["admitted"] is False and receipt["completion_authority"] is False


def test_supported_runner_entrypoint_is_consumed_by_actual_supervisor(tmp_path, monkeypatch):
    import integrations.ipfs_accelerate.improvement_runner as runner
    import inspect
    assert "daemon_script_path=Path(__file__).resolve()" in inspect.getsource(runner.run_internal)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor import PortalImplementationSupervisor
    # The real command builder must launch this script with the original native
    # task/owner/profile arguments. No authored replacement daemon command.
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor import parse_args, supervisor_config_from_args
    from integrations.ipfs_accelerate.improvement_plan import BOARD_RELATIVE
    root = Path(runner.__file__).resolve().parents[2]
    args = parse_args(runner.native_argv(root / BOARD_RELATIVE, tmp_path, "main"))
    config = supervisor_config_from_args(args, repo_root=root)
    from dataclasses import replace
    supervisor = PortalImplementationSupervisor(replace(config, daemon_script_path=Path(runner.__file__)))
    command = supervisor._build_daemon_command()
    assert str(Path(runner.__file__)) in command
    assert command[command.index("--todo-path") + 1] == str(root / BOARD_RELATIVE)
    assert command[command.index("--board-namespace") + 1] == "complaint-intake-improvement"
    assert command[command.index("--max-task-attempts") + 1] == "3"


def test_advisory_readiness_never_claims_native_scheduling_authority(tmp_path):
    _write_output(tmp_path, "CIMP-OPS-04")
    receipt = recompute_dependent_readiness(tmp_path, tmp_path / "state", _spec(_task()))
    assert receipt["completion_authority"] is False
    assert receipt["native_scheduling_enforced"] is False


@pytest.mark.parametrize("skip", [False, True])
def test_native_proposal_scheduler_actually_consumes_gate_before_acceptance(tmp_path, skip):
    from integrations.ipfs_accelerate.improvement_runner import EvidenceValidationScheduler
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalTask
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import ValidationScheduler, build_declared_validation_plan_graph
    from ipfs_accelerate_py.agent_supervisor.validation.proposal_validation import ImplementationProposal, CandidateDiffEntry, DiffChangeKind, ProposalValidationPolicy, validate_implementation_proposal
    _write_output(tmp_path, "CIMP-OPS-04")
    task = _task()
    _, executor, env = _gate(tmp_path, task, _observation(tmp_path), _return_measurement=True)
    if skip:
        test = tmp_path / "tests/test_improvement_evidence_gate.py"
        test.write_text("import pytest\ndef test_required_case(): pytest.skip('synthetic required skip')\n")
    # Use the real Native producer and exact Git baseline, not serialized
    # synthetic repository/tree labels or sources unrelated to the worktree.
    import hashlib
    import subprocess
    from ipfs_accelerate_py.agent_supervisor.proof.code_proof_obligations import collect_git_candidate_diff
    output = tmp_path / task["targets"][0]
    candidate = output.read_bytes()
    output.write_text("def ready():\n    return False\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "out", "tests"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
                    "commit", "-qm", "Synthetic baseline"], check=True)
    baseline = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()
    common = Path(subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "--path-format=absolute", "--git-common-dir"], text=True).strip()).resolve()
    output.write_bytes(candidate)
    repository = "repository:sha256:" + hashlib.sha256(str(common).encode()).hexdigest()
    proposal = ImplementationProposal(task_id=task["id"], accepted_plan_id="plan:synthetic", repository_id=repository,
        repository_tree_id=baseline, objective_id="objective:synthetic", baseline_id=baseline,
        context_id="context:owned-synthetic-attempt", replay_nonce="synthetic-attempt-1",
        declared_paths=tuple(task["targets"]), candidate_diff=tuple(entry for entry in
            collect_git_candidate_diff(tmp_path, base_revision=baseline) if entry.new_path in task["targets"]))
    accepted = validate_implementation_proposal(proposal, policy=ProposalValidationPolicy(allowed_paths=tuple(task["targets"])))
    assert accepted.accepted
    import shlex
    # Match the real daemon's explicit worktree PYTHONPATH wrapper. Rebuilding
    # a native validation environment intentionally strips ambient package roots.
    source_command = "PYTHONPATH=" + shlex.quote(env["PYTHONPATH"]) + " " + COMMAND
    commands, graph = build_declared_validation_plan_graph([source_command], repository_tree_id=proposal.repository_tree_id, changed_paths=task["targets"])
    scheduler = EvidenceValidationScheduler(ValidationScheduler(max_workers=1), state_dir=tmp_path / "native-evidence", spec=_spec(task))
    native_task = PortalTask(task["id"], "Synthetic owned task", "todo", "", "P0", "synthetic", outputs=task["targets"], validation=[COMMAND], canonical_task_cid="synthetic-task-cid")
    assert scheduler.bind_task(native_task, tmp_path) == {}
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import sealed_validation_python_runner
    from types import SimpleNamespace
    @sealed_validation_python_runner
    def guarded_executor(**call):
        spec = call["spec"]
        instrumented = spec.command.replace(" -m pytest ", " -m pytest -p complaint_fixture_guard ", 1)
        assert instrumented != spec.command
        call["spec"] = SimpleNamespace(command=instrumented, raw_command=spec.raw_command)
        return executor(**call)
    report = scheduler.run_validated(accepted, commands, workspace_path=tmp_path, runner=guarded_executor, environment=env,
        impact_graph=graph, require_impact_graph=True, require_full_validation=True, scope="pre_merge")
    assert report["passed"] is (not skip)
    assert report["returncode"] == (78 if skip else 0)
    assert report["firstparty_completion_authority"] is False
    assert report["proposal_validation"]["accepted"] is True
    assert report["cache_hits"] == 0
    assert report["behavioral_evidence"]
    if skip:
        assert report["behavioral_evidence"][0]["reason"] == "skipped_required_case"
    else:
        receipt = report["behavioral_evidence"][0]
        assert receipt["admitted"] is True and receipt["completion_authority"] is False
        assert receipt["host_measurement"]["lane_basis"] == "native_host_validation"
        assert receipt["host_measurement"]["live_node_verified"] is False
        assert len([a for a in receipt["host_measurement"]["artifacts"] if a["path"].endswith(".guard.json")]) == 2


def test_ordinary_adapter_preserves_native_constructor_scope_and_sole_loop(tmp_path, monkeypatch):
    import integrations.ipfs_accelerate.improvement_runner as runner
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon_runner as loop
    from ipfs_accelerate_py.agent_supervisor.runtime import process_security
    captured = {}
    monkeypatch.setattr(process_security, "harden_state_authority_process", lambda: captured.setdefault("hardened", True))
    real_constructor = native.PortalImplementationDaemon
    def construct(**kwargs):
        captured["kwargs"] = kwargs
        return real_constructor(**kwargs)
    monkeypatch.setattr(native, "PortalImplementationDaemon", construct)
    def sole_loop(daemon, context, **kwargs):
        captured["daemon"] = daemon
        captured["context"] = context
        assert daemon.validation_scheduler is scheduler
        assert daemon.board_namespace == "complaint-intake-improvement"
        daemon.close_event_runtime()
    monkeypatch.setattr(loop, "run_portal_implementation_daemon_loop", sole_loop)
    board = tmp_path / "board.md"; board.write_text("# Synthetic\n")
    scheduler = object()
    runner._run_evidence_daemon_adapter(["--todo-path", str(board), "--state-dir", str(tmp_path / "state"),
        "--state-prefix", "synthetic", "--task-source-kind", "legacy-markdown", "--authority-mode", "legacy_markdown",
        "--explicit-legacy-task-source", "--board-namespace", "complaint-intake-improvement", "--once",
        "--validation-max-workers", "1", "--validation-resource-budget", "1"], repo_root=tmp_path, validation_scheduler=scheduler)
    values = captured["kwargs"]
    assert captured["hardened"] and len(values) == 51
    assert values["implement"] is False
    assert values["validation_max_workers"] == values["validation_resource_budget"] == 1
    assert values["generated_status_paths"] == [] and values["external_reservation_manifest_paths"] == []
    assert values["expected_task_source_root_id"] == ""
    assert captured["context"].state_path == tmp_path / "state/synthetic_task_state.json"


@pytest.mark.parametrize("flag,value", [("--authority-mode", "duckdb"), ("--task-source-kind", "duckdb"), ("--manual-completion-authority-task-id", "CIMP-OPS-04")])
def test_unsupported_authority_modes_never_construct_adapter(tmp_path, monkeypatch, flag, value):
    import integrations.ipfs_accelerate.improvement_runner as runner
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.runtime import process_security
    monkeypatch.setattr(process_security, "harden_state_authority_process", lambda: None)
    monkeypatch.setattr(native, "PortalImplementationDaemon", lambda **kwargs: pytest.fail("unsupported mode constructed"))
    with pytest.raises((ValueError, SystemExit)):
        runner._run_evidence_daemon_adapter(["--todo-path", str(tmp_path / "board.md"), flag, value], repo_root=tmp_path, validation_scheduler=object())


@pytest.mark.parametrize("script_status", [0, 1])
def test_exact_rel03_script_and_trusted_behavioral_companion_are_both_required(tmp_path, script_status):
    from integrations.ipfs_accelerate.improvement_runner import measure_behavioral_command
    _write_output(tmp_path, "CIMP-OPS-04")
    _, executor, env = _gate(tmp_path, _task(), _observation(tmp_path), _return_measurement=True)
    script = tmp_path / "scripts/validate_complaint_intake.py"; script.parent.mkdir()
    # Explicit first import installs the same child denies before this exact
    # synthetic script body. It does not claim a real release validation.
    script.write_text("import complaint_fixture_guard\nimport json\nprint(json.dumps({'phase':'pre-admission','release_eligible':False,'self_pending':True,'other_completed':57}))\nraise SystemExit(" + str(script_status) + ")\n")
    companion = tmp_path / "tests/test_intake_release_gate.py"
    companion.write_text("def test_release_self_pending_is_not_eligible():\n assert 57 < 58\n")
    task = {"id":"CIMP-REL-03","targets":["scripts/validate_complaint_intake.py","tests/test_intake_release_gate.py"],
        "validation_commands":["python scripts/validate_complaint_intake.py --phase pre-admission"],"depends_on":[]}
    observed = measure_behavioral_command(tmp_path, tmp_path / "rel-runs", task, task["validation_commands"][0],
        runner=executor, environment=env, timeout_seconds=45,
        context={"require_child_guard":True,"pytest_guard_plugin":"complaint_fixture_guard"})
    receipt = gate_task_completion(tmp_path, tmp_path / "rel-state", task, observed, legal_data_version="synthetic-source-version")
    assert receipt["admitted"] is (script_status == 0)
    assert receipt["completion_authority"] is False
    if script_status == 0:
        measurement = receipt["host_measurement"]
        assert measurement["behavioral_companion"] == "tests/test_intake_release_gate.py"
        assert [r["mode"] for r in measurement["results"]] == ["declared_script","collect","run"]
        original = json.loads(Path(measurement["artifacts"][0]["path"]).read_text())
        assert '"release_eligible": false' in original["output"]
    else:
        assert receipt["reason"] == "declared_command_failed"


def _current_rel03_measurement_fixture(tmp_path):
    """Use the real two-command contract with inert source-bound child bodies."""
    from integrations.ipfs_accelerate import improvement_plan as compiler
    _write_output(tmp_path, "CIMP-OPS-04")
    _, executor, environment = _gate(
        tmp_path, _task(), _observation(tmp_path), _return_measurement=True)
    spec = compiler.load_spec(Path(__file__).resolve().parents[1] / compiler.SPEC_RELATIVE)
    task = next(item for item in spec["tasks"] if item["id"] == "CIMP-REL-03")
    assert task["validation_commands"] == [
        "python -m pytest -q --run-llm --run-network --run-heavy tests/test_intake_release_gate.py",
        "python scripts/validate_complaint_intake.py --phase pre-admission",
    ]
    script = tmp_path / "scripts/validate_complaint_intake.py"
    script.parent.mkdir(exist_ok=True)
    script.write_text(
        "import complaint_fixture_guard\nfrom pathlib import Path\n"
        "Path('declared-release-script-ran').write_text('synthetic invocation')\n"
        "print('synthetic pre-admission checker; no real task completion claimed')\n")
    report = tmp_path / "docs/task_boards/complaint_intake_completion.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"phase":"pre-admission", "release_qualified":False,
                                 "self_completion_pending":True, "pending_task_ids":["CIMP-REL-03"]}))
    (tmp_path / "tests/test_intake_release_gate.py").write_text(
        "import json\nfrom pathlib import Path\n"
        "def test_current_release_remains_self_pending():\n"
        " value=json.loads(Path('docs/task_boards/complaint_intake_completion.json').read_text())\n"
        " assert value['release_qualified'] is False\n"
        " assert value['self_completion_pending'] is True\n"
        " assert value['pending_task_ids'] == ['CIMP-REL-03']\n")
    assert all((tmp_path / path).is_file() for path in task["targets"])
    return task, executor, environment


@pytest.mark.parametrize("command_index", [0, 1])
def test_real_rel03_two_command_contract_preserves_each_command_identity(tmp_path, command_index):
    import shlex
    from integrations.ipfs_accelerate.improvement_runner import measure_behavioral_command
    task, executor, environment = _current_rel03_measurement_fixture(tmp_path)
    declared = task["validation_commands"][command_index]
    command = "PYTHONPATH=" + shlex.quote(environment["PYTHONPATH"]) + " " + declared
    observed = measure_behavioral_command(
        tmp_path, tmp_path / "real-rel-runs", task, command,
        runner=executor, environment=environment, timeout_seconds=45,
        declared_command=declared,
        context={"require_child_guard":True, "pytest_guard_plugin":"complaint_fixture_guard"})
    receipt = gate_task_completion(tmp_path, tmp_path / "real-rel-state", task, observed,
                                   legal_data_version="synthetic-source-version")
    assert receipt["admitted"] is True
    assert receipt["completion_authority"] is False
    assert observed["command"] == declared
    assert observed["host_task_contract"]["task"]["validation_commands"] == task["validation_commands"]
    assert observed["host_measurement"]["reason"] == ""
    assert observed["required_nodeids"] == [
        "tests/test_intake_release_gate.py::test_current_release_remains_self_pending"]
    expected_modes = ["declared_script", "collect", "run"] if command_index == 1 else ["collect", "run"]
    assert [result["mode"] for result in observed["host_measurement"]["results"]] == expected_modes
    assert (tmp_path / "declared-release-script-ran").exists() is (command_index == 1)
    assert observed["host_measurement"]["behavioral_companion"] == (
        "tests/test_intake_release_gate.py" if command_index == 1 else None)


def test_rel03_unknown_extra_command_does_not_gain_script_companion_dispatch(tmp_path):
    import shlex
    from integrations.ipfs_accelerate.improvement_runner import measure_behavioral_command
    task, _executor, environment = _current_rel03_measurement_fixture(tmp_path)
    task["validation_commands"] = task["validation_commands"] + ["python unreviewed.py"]
    declared = task["validation_commands"][1]
    calls = []
    def forbidden(**kwargs):
        calls.append(kwargs)
        raise AssertionError("an unfamiliar release contract must refuse before execution")
    observed = measure_behavioral_command(
        tmp_path, tmp_path / "refused-rel-runs", task,
        "PYTHONPATH=" + shlex.quote(environment["PYTHONPATH"]) + " " + declared,
        runner=forbidden, environment=environment, timeout_seconds=45,
        declared_command=declared,
        context={"require_child_guard":True, "pytest_guard_plugin":"complaint_fixture_guard"})
    assert calls == []
    assert observed["host_measurement"]["reason"] == "unsupported_behavioral_command"
    assert observed["host_measurement"]["behavioral_companion"] is None
    assert not (tmp_path / "declared-release-script-ran").exists()
    assert observed["host_measurement"]["completion_authority"] is False


def test_actual_private_storage_change_measures_all_finite_impacted_companions(tmp_path, monkeypatch):
    """Bind the production impact policy; execute its finite selector in an isolated unit fixture.

    The real replica companion keeps its separate process/crypto acceptance.
    This fixture deliberately retains its absolute process/network denial.
    """
    import shlex
    import integrations.ipfs_accelerate.improvement_runner as runtime
    _write_output(tmp_path, "CIMP-OPS-04")
    _, executor, environment = _gate(tmp_path, _task(), _observation(tmp_path), _return_measurement=True)
    product = tmp_path / "integrations/private_storage.py"
    product.parent.mkdir()
    product.write_text("SOURCE_KIND = 'synthetic private storage impact fixture'\n")
    companions = {
        "tests/test_private_workspace_crypto.py": "test_crypto_companion_selected",
        "tests/test_private_workspace_keys.py": "test_key_companion_selected",
        "tests/test_private_storage_adapter.py": "test_adapter_companion_selected",
    }
    for relative, function in companions.items():
        (tmp_path / relative).write_text("def " + function + "():\n assert 2 + 2 == 4\n")
    trusted = "tests/test_private_replica_acceptance.py"
    with pytest.raises(ValueError, match="impacted_check_missing"):
        runtime._impacted_behavioral_checks(tmp_path, ["integrations/private_storage.py"])
    trusted_bytes = (Path(__file__).resolve().parent / "test_private_replica_acceptance.py").read_bytes()
    (tmp_path / trusted).write_bytes(trusted_bytes)
    assert runtime._impacted_behavioral_checks(tmp_path, ["integrations/private_storage.py"]) == sorted([*companions, trusted])
    binding = runtime._private_replica_acceptance_binding(tmp_path, _task(), [trusted])
    assert binding["sha256"]
    (tmp_path / trusted).write_bytes(trusted_bytes + b"\n# synthetic fixture tampering\n")
    with pytest.raises(ValueError, match="trusted_replica_acceptance_changed"):
        runtime._private_replica_acceptance_binding(tmp_path, _task(), [trusted])
    (tmp_path / trusted).write_bytes(trusted_bytes)
    # A named unit-only policy key exercises actual collection/instrumentation
    # without relabeling the real crypto/probe suite as a stub or disabling its guard.
    fixture_key = "unit-fixture/private-storage-impact"
    monkeypatch.setitem(runtime._IMPACTED_BEHAVIORAL_CHECKS, fixture_key, tuple(companions))
    reviewed = tmp_path / "reviewed-fixture-baseline"
    for relative in companions:
        target = reviewed / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((tmp_path / relative).read_bytes())
    real_preserve = runtime._preserve_existing_behavioral_definitions
    monkeypatch.setattr(runtime, "_preserve_existing_behavioral_definitions",
        lambda root, paths: real_preserve(root, paths, trusted_root=reviewed))
    task = _task()
    observed = runtime.measure_behavioral_command(tmp_path, tmp_path / "private-impact-runs", task,
        "PYTHONPATH=" + shlex.quote(environment["PYTHONPATH"]) + " " + COMMAND,
        runner=executor, environment=environment, timeout_seconds=45, declared_command=COMMAND,
        context={"changed_paths": [fixture_key], "require_child_guard": True,
                 "pytest_guard_plugin": "complaint_fixture_guard"})
    assert observed["host_measurement"]["reason"] == ""
    assert observed["host_measurement"]["impacted_checks"] == sorted(companions)
    expected = {NODE_A, NODE_B} | {path + "::" + function for path, function in companions.items()}
    assert set(observed["required_nodeids"]) == expected
    assert observed["collected_count"] == 5
    assert all(row["outcome"] == "passed" for row in observed["cases"])
    assert observed["host_measurement"]["completion_authority"] is False


@pytest.mark.parametrize("mutation", ["cases", "required", "count", "record", "unimported_source", "contract"])
def test_measured_capability_rejects_postrun_mutants(tmp_path, mutation):
    import subprocess
    _write_output(tmp_path, "CIMP-OPS-04")
    unimported = tmp_path / "unused_shared_adapter.py"; unimported.write_text("VERSION=1\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", unimported.name], check=True)
    observed, _, _ = _gate(tmp_path, _task(), _observation(tmp_path), _return_measurement=True)
    altered = observed.copy()
    if mutation == "cases": altered["cases"] = [{"nodeid":"foreign.py::test_foreign", "outcome":"passed"}]
    elif mutation == "required": altered["required_nodeids"] = [NODE_A]
    elif mutation == "count": altered["collected_count"] = 1
    elif mutation == "record": Path(altered.measurement_record["path"]).unlink()
    elif mutation == "contract": altered["host_task_contract"] = {"task":{},"context":{},"command":COMMAND}
    else: unimported.write_text("VERSION=2\n")
    receipt = gate_task_completion(tmp_path, tmp_path / "mutant-state", _task(), altered, legal_data_version="synthetic")
    assert receipt["admitted"] is False and receipt["completion"] is False
    assert receipt["repairable"] is True and receipt["completion_authority"] is False


def test_native_catalog_rejects_empty_seal_and_file_count(tmp_path):
    import duckdb
    from integrations.ipfs_accelerate.improvement_runner import _read_catalog
    _write_output(tmp_path, "CIMP-OPS-04")
    observed, _, _ = _gate(tmp_path, _task(), _observation(tmp_path), _return_measurement=True)
    catalog = next(Path(a["path"]) for a in observed["host_measurement"]["artifacts"] if a["path"].endswith("run.duckdb"))
    with duckdb.connect(str(catalog)) as database:
        database.execute("UPDATE pytest_ast_seal SET seal='', file_count=0")
    with pytest.raises(ValueError, match="catalog_seal_invalid"):
        _read_catalog(catalog)


def test_tracked_private_bodies_are_never_hashed_or_exposed_by_source_binding(tmp_path, monkeypatch):
    import subprocess
    import integrations.ipfs_accelerate.improvement_plan as plan
    from integrations.ipfs_accelerate.improvement_runner import _source_freeze
    source = tmp_path / "source.py"; source.write_text("VALUE=1\n")
    private = ["secrets/body.json", "evidence/body.py", "uploads/body.json", "attachments/body.py", "data/body.json", ".env.local", "owner.key", "owner.pem"]
    for name in private:
        path = tmp_path / name; path.parent.mkdir(exist_ok=True); path.write_text("synthetic-private-canary")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", "."], check=True)
    real_hash = plan._hash_file
    seen = []
    def hash_file(path):
        relative = path.relative_to(tmp_path).as_posix()
        assert relative not in private, "private body opened"
        seen.append(relative)
        return real_hash(path)
    monkeypatch.setattr(plan, "_hash_file", hash_file)
    frozen = _source_freeze(tmp_path, ["source.py"])
    assert set(frozen["files"]) == {"source.py"} and seen
    assert all(name not in json.dumps(frozen) for name in private)
    assert all(plan._safe_relative(tmp_path, name) is None for name in private)
    with pytest.raises(ValueError, match="private_source_binding_forbidden"):
        _source_freeze(tmp_path, [private[0]])


def test_borrowed_measured_object_cannot_replace_original_host_record_pin(tmp_path):
    import hashlib
    _write_output(tmp_path, "CIMP-OPS-04")
    original, _, _ = _gate(tmp_path, _task(), _observation(tmp_path), _return_measurement=True)
    altered = original.copy()
    forged = json.loads(json.dumps(altered["host_measurement"]))
    forged["cases"] = [{"nodeid":"foreign.py::test_foreign", "outcome":"passed"}]
    forged["required_nodeids"] = ["foreign.py::test_foreign"]
    forged["observation_binding"].update(cases=forged["cases"], required_nodeids=forged["required_nodeids"], collected_count=1)
    replacement = tmp_path / "replacement.json"; replacement.write_text(json.dumps(forged))
    replacement_record = {"path":str(replacement),"sha256":hashlib.sha256(replacement.read_bytes()).hexdigest()}
    with pytest.raises(AttributeError):
        altered.measurement_record = replacement_record
    # Mutating the returned descriptive dict also cannot change the registry.
    altered.measurement_record.update(replacement_record)
    altered["host_measurement"] = forged
    altered.update(cases=forged["cases"], required_nodeids=forged["required_nodeids"], collected_count=1)
    receipt = gate_task_completion(tmp_path, tmp_path / "replacement-state", _task(), altered, legal_data_version="synthetic")
    assert receipt["admitted"] is False and receipt["reason"] == "measurement_record_mismatch"
    assert receipt["completion_authority"] is False


def test_private_aliases_and_symlinked_source_parents_are_refused_before_body_read(tmp_path, monkeypatch):
    import subprocess
    import integrations.ipfs_accelerate.improvement_plan as plan
    from integrations.ipfs_accelerate.improvement_runner import _source_freeze
    secret = tmp_path / "secrets/body.json"; secret.parent.mkdir(); secret.write_text("synthetic-private-body")
    alias = tmp_path / "alias.py"; alias.symlink_to(secret)
    package = tmp_path / "pkg"; package.mkdir(); (package / "source.py").write_text("VALUE=1\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "pkg/source.py"], check=True)
    (package / "source.py").unlink(); package.rmdir(); package.symlink_to(secret.parent, target_is_directory=True)
    called = []
    monkeypatch.setattr(plan, "_hash_file", lambda path: called.append(path) or pytest.fail("aliased body read"))
    assert plan.bind_sources(tmp_path, ["alias.py"])["missing"] == ["alias.py"]
    assert plan.bind_sources(tmp_path, ["pkg"])["missing"] == ["pkg"]
    with pytest.raises(ValueError, match="source_alias_forbidden"):
        _source_freeze(tmp_path)
    assert called == []


def test_impacted_checks_use_actual_reused_adapter_paths():
    from integrations.ipfs_accelerate.improvement_runner import _impacted_behavioral_checks
    root = Path(__file__).resolve().parents[1]
    assert {"tests/test_explicit_legal_context.py", "tests/test_ipfs_adapter_layer.py"} <= set(_impacted_behavioral_checks(root, ["integrations/ipfs_datasets/legal.py"]))
    assert "tests/test_proof_report_and_pinning.py" in _impacted_behavioral_checks(root, ["integrations/ipfs_datasets/storage.py"])
    assert "tests/test_private_workspace_keys.py" in _impacted_behavioral_checks(root, ["integrations/private_storage.py"])
    assert _impacted_behavioral_checks(root, ["unrelated.py"]) == []


@pytest.mark.parametrize("advisory_failure", [None, "timeout", "failed_git", "malformed_receipt"])
def test_consumed_scheduler_recomputes_advisory_after_real_dependency_revision(tmp_path, monkeypatch, advisory_failure):
    import os, shlex, subprocess
    from types import SimpleNamespace
    from integrations.ipfs_accelerate.improvement_runner import EvidenceValidationScheduler
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalTask
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import ValidationScheduler
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import sealed_validation_python_runner
    first, second = _task("CIMP-OPS-01"), _task("CIMP-OPS-04")
    for task in (first, second): _write_output(tmp_path, task["id"])
    dependency = tmp_path / "external/ipfs_datasets_py"; dependency.mkdir(parents=True)
    def git(where, *args):
        return subprocess.check_output(["git", "-C", str(where), *args], text=True).strip()
    git(tmp_path, "init", "-q"); git(dependency, "init", "-q")
    def revision(value):
        (dependency / "rules.py").write_text("VERSION=" + str(value) + "\n")
        git(dependency, "add", "rules.py")
        git(dependency, "-c", "user.name=Synthetic Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Synthetic revision")
        return git(dependency, "rev-parse", "HEAD")
    old_revision = revision(1)
    git(tmp_path, "update-index", "--add", "--cacheinfo", "160000," + old_revision + ",external/ipfs_datasets_py")
    _, executor, env = _gate(tmp_path, first, _observation(tmp_path, first["id"]), _return_measurement=True)
    @sealed_validation_python_runner
    def guarded_executor(**call):
        spec = call["spec"]
        command = spec.command.replace(" -m pytest ", " -m pytest -p complaint_fixture_guard ", 1)
        assert command != spec.command
        call["spec"] = SimpleNamespace(command=command, raw_command=spec.raw_command)
        return executor(**call)
    state = tmp_path / "advisory-state"
    scheduler = EvidenceValidationScheduler(ValidationScheduler(max_workers=1), state_dir=state, spec=_spec(first, second))
    def run(task):
        native = PortalTask(task["id"], "Synthetic", "todo", "", "P0", "synthetic", outputs=task["targets"], validation=[COMMAND])
        scheduler.bind_task(native, tmp_path)
        return scheduler.run(["PYTHONPATH=" + shlex.quote(env["PYTHONPATH"]) + " " + COMMAND],
            workspace_path=tmp_path, runner=guarded_executor, environment=env, require_full_validation=True, scope="pre_merge")
    before = run(first)
    assert before["passed"] is True
    assert before["dependent_readiness"]["tasks"][first["id"]]["complete"] is True
    assert before["dependent_readiness"]["legal_data_version"] == old_revision
    new_revision = revision(2)
    if advisory_failure is not None:
        import integrations.ipfs_accelerate.improvement_runner as runner
        def unavailable(*args, **kwargs):
            if advisory_failure == "timeout":
                raise subprocess.TimeoutExpired(["git", "ls-files"], timeout=20)
            if advisory_failure == "failed_git":
                raise subprocess.CalledProcessError(128, ["git", "ls-files"])
            raise AttributeError("synthetic malformed advisory record")
        monkeypatch.setattr(runner, "recompute_dependent_readiness", unavailable)
    after = run(second)
    assert after["passed"] is True  # advisory history never becomes another scheduler
    advisory = after["dependent_readiness"]
    if advisory_failure is not None:
        assert advisory == {"available":False,"reason":"advisory_observation_unavailable",
            "native_scheduling_enforced":False,"completion_authority":False}
        assert json.loads((state / "evidence/readiness.json").read_text())["legal_data_version"] == old_revision
        return
    assert advisory["legal_data_version"] == new_revision != old_revision
    assert advisory["tasks"][first["id"]]["complete"] is False
    assert advisory["tasks"][first["id"]]["reason"] in {"stale_source_hash", "legal_data_version_changed"}
    assert advisory["native_scheduling_enforced"] is False and advisory["completion_authority"] is False
    assert json.loads((state / "evidence/readiness.json").read_text()) == advisory


def test_real_sealed_pytest_bootstrap_survives_declared_pythonpath_export(tmp_path):
    import hashlib
    import os
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native_source
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import validation_environment_for_runner
    from integrations.ipfs_accelerate.improvement_runner import measure_behavioral_command

    _write_output(tmp_path, "CIMP-OPS-04")
    _, executor, env = _gate(tmp_path, _task(), _observation(tmp_path), _return_measurement=True)
    # Real phase-plugin source, copied intact into the synthetic checkout. This
    # matches native validation's current worktree package, not a plugin fake.
    package = tmp_path / "integrations/ipfs_accelerate"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    phase_source = Path(__file__).resolve().parents[1] / "integrations/ipfs_accelerate/improvement_plan.py"
    phase = package / "improvement_plan.py"
    phase.write_bytes(phase_source.read_bytes())
    campaign_source = phase_source.with_name("campaign.py")
    campaign = package / "campaign.py"
    campaign.write_bytes(campaign_source.read_bytes())
    declared = tmp_path / "external/ipfs_datasets_py"
    decoy = declared / "ipfs_accelerate_py"
    decoy.mkdir(parents=True)
    (decoy / "__init__.py").write_text("raise RuntimeError('untrusted_native_bootstrap')\n")
    (tmp_path / "complaint_owned_network_guard.py").write_text(
        "raise RuntimeError('candidate_shadowed_owned_network_guard')\n")
    native_root = Path(native_source.__file__).resolve().parents[3]
    seal = native_root / "ipfs_accelerate_py/testing/pytest_ast_seal.py"
    test = tmp_path / "tests/test_improvement_evidence_gate.py"
    test.write_text("from pathlib import Path\n"
        "import ctypes, errno, socket\n"
        "import integrations.ipfs_accelerate.improvement_plan as phase\n"
        "import integrations.ipfs_accelerate.campaign as campaign\n"
        "import ipfs_accelerate_py.testing.pytest_ast_seal as seal\n"
        "def test_actual_plugin_origins():\n"
        f" assert Path(phase.__file__).resolve() == Path({str(phase)!r})\n"
        f" assert Path(campaign.__file__).resolve() == Path({str(campaign)!r})\n"
        f" assert Path(seal.__file__).resolve() == Path({str(seal)!r})\n"
        " libc = ctypes.CDLL(None, use_errno=True)\n"
        " for family in (socket.AF_INET, socket.AF_INET6):\n"
        "  ctypes.set_errno(0)\n"
        "  descriptor = libc.socket(family, socket.SOCK_STREAM, 0)\n"
        "  if descriptor >= 0: libc.close(descriptor)\n"
        "  assert descriptor == -1 and ctypes.get_errno() == errno.EPERM\n"
        " left, right = socket.socketpair()\n"
        " try:\n"
        "  assert left.send(b'network-guard') == 13\n"
        "  assert right.recv(13) == b'network-guard'\n"
        " finally:\n"
        "  left.close(); right.close()\n")
    # Reproduce the actual native scheduler's approved package-only environment
    # and the normalized task command's overwriting relative export.
    env["PYTHONPATH"] = str(Path(pytest.__file__).resolve().parents[1])
    env = validation_environment_for_runner(env, executor)
    command = "export PYTHONPATH=external/ipfs_datasets_py && " + COMMAND
    observed = measure_behavioral_command(tmp_path, tmp_path / "bootstrap-runs", _task(), command,
        runner=executor, environment=env, timeout_seconds=45, declared_command=COMMAND,
        context={"require_child_guard": True, "pytest_guard_plugin": "complaint_fixture_guard"})
    measured = observed["host_measurement"]
    assert measured["reason"] == ""
    assert measured["required_nodeids"] == ["tests/test_improvement_evidence_gate.py::test_actual_plugin_origins"]
    assert measured["cases"] == [{"nodeid": measured["required_nodeids"][0], "outcome": "passed"}]
    assert measured["source_unchanged"] is True
    assert all(result["validation_python_launcher"]["sealed"] is True for result in measured["results"])
    assert measured["imported_sources"][str(seal)] == hashlib.sha256(seal.read_bytes()).hexdigest()
    assert measured["imported_sources"][str(phase)] == hashlib.sha256(phase_source.read_bytes()).hexdigest()
    assert measured["imported_sources"][str(campaign)] == hashlib.sha256(campaign_source.read_bytes()).hexdigest()
    assert all(result["original_command"] == command for result in measured["results"])
    assert all("-p complaint_fixture_guard" in result["executed_command"] for result in measured["results"])
    assert all(" -P -m pytest " in result["executed_command"] for result in measured["results"])
    network = measured["kernel_network_guard"]
    assert network["validation_children_only"] is True
    assert [row["mode"] for row in network["proofs"]] == ["collect", "run"]
    assert all(Path(row["path"]).is_file() and row["sha256"] for row in network["proofs"])
    assert observed["completion_authority"] is False if "completion_authority" in observed else measured["completion_authority"] is False


@pytest.mark.parametrize("changed", ["applications/complaint_workspace.py", "static/complaint_conversation.js", "static/complaint_mcp_sdk.js"])
def test_correction_product_changes_require_the_bounded_accepted_companion(tmp_path, changed):
    from integrations.ipfs_accelerate import improvement_runner as runtime
    selector = ("tests/test_cimp_ux_10.py::"
                "test_answer_and_correction_update_graphs_once_and_stale_replies_do_not")
    expected = runtime._IMPACTED_BEHAVIORAL_CHECKS[changed]
    late_selector = "tests/test_cimp_ux_10.py::test_delayed_answer_cannot_repaint_a_new_selected_case"
    assert {selector, late_selector} <= set(expected)
    for relative in expected:
        path = tmp_path / relative.partition("::")[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    assert runtime._impacted_behavioral_checks(tmp_path, [changed]) == sorted(expected)
    (tmp_path / "tests/test_cimp_ux_10.py").unlink()
    with pytest.raises(ValueError, match="impacted_check_missing"):
        runtime._impacted_behavioral_checks(tmp_path, [changed])


@pytest.mark.parametrize("mode", ["passes", "strong_fails", "weakens", "omits", "full_file",
                                  "filtered_node", "filtered_file", "parameters", "late_fails", "one_node_only", "partial_file"])
def test_measured_correction_selector_enforces_success_without_running_unrelated_cases(tmp_path, monkeypatch, mode):
    """Synthetic selector fixture, separate from the genuine browser acceptance.

    A declared positive-VERSION test permits VERSION1. The trusted companion
    requires VERSION2; unrelated failing cases prove the selector stays bounded.
    The fixture retains the real sealed executor, AST and child/network guards.
    """
    import shlex
    from integrations.ipfs_accelerate import improvement_runner as runtime
    _write_output(tmp_path, "CIMP-OPS-04")
    _, executor, environment = _gate(tmp_path, _task(), _observation(tmp_path), _return_measurement=True)
    relative, _, function = runtime._FACTUAL_CORRECTION_ACCEPTANCE.partition("::")
    late_function = runtime._CASE_SWITCH_ACCEPTANCE.partition("::")[2]
    companion = tmp_path / relative
    declaration = ("@pytest.mark.parametrize('expected', [2, 2], ids=['first', 'second'])\n"
                   "def " + function + "(expected):\n    assert adapter.VERSION == expected\n"
                   if mode == "parameters" else "def " + function + "():\n    assert adapter.VERSION == 2\n")
    companion.write_text("import adapter, pytest\n\n" + declaration
                         + "\ndef " + late_function + "():\n    assert adapter.CASE_ID == 'new-case'\n"
                         + "\ndef test_unrelated_case_stays_out_of_bounded_selector():\n    assert "
                         + ("True" if mode == "full_file" else "False") + "\n"
                         + ("\ndef test_weak_declared_only():\n    assert adapter.VERSION > 0\n"
                            if mode == "filtered_node" else ""))
    reviewed = tmp_path / "reviewed-companion-baseline"
    baseline = reviewed / relative
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes(companion.read_bytes())
    real_preserve = runtime._preserve_existing_behavioral_definitions
    monkeypatch.setattr(runtime, "_preserve_existing_behavioral_definitions",
        lambda root, paths: real_preserve(root, paths, trusted_root=reviewed))
    key = "static/complaint_conversation.js"
    product = tmp_path / key
    product.parent.mkdir()
    product.write_text("// Explicit synthetic impact input; real browser acceptance is qualified separately.\n")
    impacted = sorted(runtime._IMPACTED_BEHAVIORAL_CHECKS[key])
    if mode in {"filtered_file", "partial_file"}:
        # Separate generic whole-file policy control, retaining real collection.
        impacted = [relative]
        monkeypatch.setitem(runtime._IMPACTED_BEHAVIORAL_CHECKS, key, tuple(impacted))
    version = "2" if mode in {"passes", "full_file", "parameters", "late_fails", "one_node_only", "partial_file"} else "1"
    case = "old-case" if mode == "late_fails" else "new-case"
    (tmp_path / "adapter.py").write_text("VERSION=" + version + "\nCASE_ID=" + repr(case) + "\n")
    if mode == "weakens":
        companion.write_text(companion.read_text().replace("adapter.VERSION == 2", "adapter.VERSION > 0"))
    elif mode == "omits":
        companion.write_text(companion.read_text().replace("def " + function + "(", "def omitted_accepted_companion("))
    command = COMMAND + (" " + relative if mode in {"full_file", "filtered_node", "one_node_only", "partial_file"} else "")
    if mode == "filtered_node":
        command += " -k weak"
    elif mode == "filtered_file":
        command += " -k local_node_evidence"
    elif mode in {"one_node_only", "partial_file"}:
        command += " -k answer_and_correction_update_graphs_once"
    observed = runtime.measure_behavioral_command(tmp_path, tmp_path / "selector-runs", _task(command=command),
        "PYTHONPATH=" + shlex.quote(environment["PYTHONPATH"]) + " " + command,
        runner=executor, environment=environment, timeout_seconds=45, declared_command=command,
        context={"changed_paths": [key], "require_child_guard": True, "pytest_guard_plugin": "complaint_fixture_guard"})
    measured = observed["host_measurement"]
    assert measured["impacted_checks"] == impacted
    assert measured["completion_authority"] is False
    if mode in {"filtered_node", "filtered_file", "one_node_only", "partial_file"}:
        assert measured["reason"] == "impacted_required_case_missing"
        missing = [runtime._CASE_SWITCH_ACCEPTANCE] if mode == "one_node_only" else impacted
        assert measured["missing_impacted_checks"] == missing
        assert [row["mode"] for row in measured["results"]] == ["collect"]
        assert measured["results"][0]["returncode"] == 0
        expected = (runtime._FACTUAL_CORRECTION_ACCEPTANCE if mode in {"one_node_only", "partial_file"} else
                    relative + "::test_weak_declared_only" if mode == "filtered_node" else NODE_A)
        assert observed["required_nodeids"] == [expected]
        assert not (Path(measured["run_path"]) / "run.json").exists()
    elif mode in {"weakens", "omits"}:
        assert measured["reason"] == "existing_behavioral_definition_changed"
        assert measured["behavioral_definition_diagnostic"]["candidate_executed"] is False
        assert not measured["results"]
    else:
        assert measured["reason"] == ("failed_assertion" if mode in {"strong_fails", "late_fails"} else "")
        companion_nodes = ({runtime._FACTUAL_CORRECTION_ACCEPTANCE + "[first]",
                            runtime._FACTUAL_CORRECTION_ACCEPTANCE + "[second]"}
                           if mode == "parameters" else {runtime._FACTUAL_CORRECTION_ACCEPTANCE})
        expected = {NODE_A, NODE_B, *companion_nodes, runtime._CASE_SWITCH_ACCEPTANCE}
        if mode == "full_file":
            expected.add(relative + "::test_unrelated_case_stays_out_of_bounded_selector")
        assert set(observed["required_nodeids"]) == expected
        assert observed["collected_count"] == len(expected)
        # Host deliberately stops projecting cases at the first failure.
        # The genuine phase manifest still records every executed test.
        phases = json.loads((Path(measured["run_path"]) / "run.json").read_text())
        cases = {row["nodeid"]: row["outcome"] for row in phases["reports"] if row["when"] == "call"}
        assert cases[NODE_A] == cases[NODE_B] == "passed"
        assert all(cases[node] == ("failed" if mode == "strong_fails" else "passed") for node in companion_nodes)
        assert cases[runtime._CASE_SWITCH_ACCEPTANCE] == ("failed" if mode == "late_fails" else "passed")
        assert any(row["path"] == relative for row in measured["preserved_behavioral_definitions"])
