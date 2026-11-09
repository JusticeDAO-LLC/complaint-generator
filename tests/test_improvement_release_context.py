"""Unit checks for trusted release-command locator handoff.

Synthetic launcher metadata and recording callbacks exercise only the parent
handoff. No child command or Native daemon runs, and no fixture establishes
task completion, source qualification, or release qualification.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_plan as plan
from integrations.ipfs_accelerate import improvement_runner as runner
from tests.test_improvement_runner import _full_owner, _spec

ROOT = Path(__file__).resolve().parents[1]
DECLARED = "python scripts/validate_complaint_intake.py --phase pre-admission"
COMPANION = "python -m pytest -q --run-llm --run-network --run-heavy tests/test_intake_release_gate.py"
STATE_ENV = "COMPLAINT_INTAKE_RELEASE_CAMPAIGN_STATE_DIR"
TARGET_ENV = "COMPLAINT_INTAKE_RELEASE_TARGET_SOURCE_ROOT"
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture
def release_context_case(tmp_path, monkeypatch):
    from integrations.ipfs_datasets.loader import ensure_import_paths

    ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon

    def no_daemon(*_args, **_kwargs):
        pytest.fail("a handoff unit fixture must not construct a Native daemon")

    monkeypatch.setattr(PortalImplementationDaemon, "__init__", no_daemon)
    target = tmp_path / "trusted-parent-source"
    target.mkdir(mode=0o700)
    spec = target / runner.SPEC_RELATIVE
    spec.parent.mkdir(parents=True)
    spec.write_text(json.dumps(_spec()))
    plan_id = runner._requested_plan_id(spec)
    assert plan_id
    campaign = tmp_path / "owned-campaign"
    campaign.mkdir(mode=0o700)
    launch = _full_owner(target, spec, campaign, plan_id)
    (campaign / "launcher.json").write_text(json.dumps(launch))

    candidate = tmp_path / "candidate-source"
    (candidate / "tests").mkdir(parents=True)
    (candidate / "scripts").mkdir()
    # A locator unit has no dependency on the pending release implementation.
    # Its inert output belongs to a synthetic parent with no installed gate.
    monkeypatch.setattr(runner, "__file__", str(target / "integrations/ipfs_accelerate/improvement_runner.py"))
    bootstrap = target / "integrations/ipfs_accelerate/improvement_plan.py"
    bootstrap.parent.mkdir(parents=True)
    bootstrap.write_bytes((ROOT / "integrations/ipfs_accelerate/improvement_plan.py").read_bytes())
    (candidate / "tests/test_intake_release_gate.py").write_text(
        "def test_inert_locator_fixture():\n    assert True\n")
    (candidate / "scripts/validate_complaint_intake.py").write_text(
        "# Inert handoff unit source; never executed.\n")
    task = {
        "id": "CIMP-REL-03",
        "targets": ["scripts/validate_complaint_intake.py", "tests/test_intake_release_gate.py"],
        "validation_commands": [COMPANION, DECLARED],
        "depends_on": [],
    }
    # Full Git/dependency inventory is outside this unit's scope. Keep real
    # output hashing and all launcher/plan/path checks; never mint a passing run.
    monkeypatch.setattr(runner, "_source_freeze", lambda root, extra=(): {
        "unit_scope": "declared output hashing only", "outputs": plan.bind_sources(root, extra),
    })
    environment = {
        "PATH": "/synthetic-unit-bin", "UNIT_KEEP": "owned fixture",
        STATE_ENV: "untrusted ambient state", TARGET_ENV: "untrusted ambient target",
    }
    context = {"campaign_state_dir": str(campaign), "target_source_root": str(target)}
    command = "PYTHONPATH=/synthetic-unit-source " + DECLARED

    def measure(callback, *, supplied_context=None, supplied_environment=None):
        return runner.measure_behavioral_command(
            candidate, tmp_path / "unit-measurements", task, command,
            runner=callback,
            environment=environment if supplied_environment is None else supplied_environment,
            context=context if supplied_context is None else supplied_context,
            declared_command=DECLARED,
            timeout_seconds=30,
        )

    return SimpleNamespace(target=target, spec=spec, campaign=campaign, launch=launch,
        candidate=candidate, environment=environment, context=context, command=command, measure=measure)


def _recording_callback(calls, *, claimed_sealed=False, output="unit callback; no child executed"):
    def callback(**kwargs):
        calls.append(kwargs)
        return {"command": kwargs["spec"].command, "returncode": 0, "output": output,
                "validation_python_launcher": {"sealed": claimed_sealed}}
    return callback


def _assert_no_completion(observed, reason):
    measurement = observed["host_measurement"]
    assert measurement["reason"] == reason
    assert measurement["completion_authority"] is False
    assert measurement["trusted_executor"]["canonical_native_identity"] is False
    assert observed["exit_status"] == 1
    assert observed["collected_count"] == 0
    assert observed["required_nodeids"] == []


def test_release_handoff_preserves_canonical_command_and_copies_environment(release_context_case):
    case = release_context_case
    calls = []
    original_environment, original_context = dict(case.environment), deepcopy(case.context)
    observed = case.measure(_recording_callback(calls))
    assert len(calls) == 1
    call = calls[0]
    assert call["spec"].command == call["spec"].raw_command == case.command
    assert observed["command"] == DECLARED
    assert call["workspace_path"] == case.candidate
    assert case.target != case.candidate
    assert call["environment"] is not case.environment
    copied_environment = dict(call["environment"])
    runtime = Path(copied_environment.pop("COMPLAINT_INTAKE_RELEASE_RUNTIME_DIR"))
    assert runtime.parent.parent == case.candidate.parent / "unit-measurements"
    assert runtime.name == "release-runtime" and runtime.stat().st_mode & 0o777 == 0o700
    assert copied_environment == {
        **original_environment, STATE_ENV: str(case.campaign), TARGET_ENV: str(case.target),
    }
    assert case.environment == original_environment
    assert case.context == original_context
    assert observed["host_measurement"]["results"][0]["original_command"] == case.command
    _assert_no_completion(observed, "sealed_execution_unavailable")


@pytest.mark.parametrize("damage", [
    "target_alias", "state_alias", "target_mismatch", "state_mismatch",
    "state_permissions", "state_owner", "missing_launcher", "process_only_launcher",
    "plan_mismatch", "spec_mismatch", "provider_mismatch", "fallback_enabled",
])
def test_release_handoff_rejects_unbound_or_aliased_campaign(release_context_case, monkeypatch, damage):
    case = release_context_case
    context = dict(case.context)
    launch = dict(case.launch)
    if damage in {"target_alias", "state_alias"}:
        destination = case.target if damage == "target_alias" else case.campaign
        alias = destination.with_name(destination.name + "-alias")
        alias.symlink_to(destination, target_is_directory=True)
        context["target_source_root" if damage == "target_alias" else "campaign_state_dir"] = str(alias)
    elif damage == "target_mismatch":
        other = case.target.with_name("other-trusted-source")
        other.mkdir(mode=0o700)
        context["target_source_root"] = str(other)
    elif damage == "state_mismatch":
        other = case.campaign.with_name("other-owned-campaign")
        other.mkdir(mode=0o700)
        (other / "launcher.json").write_text(json.dumps(launch))
        context["campaign_state_dir"] = str(other)
    elif damage == "state_permissions":
        case.campaign.chmod(0o755)
    elif damage == "state_owner":
        monkeypatch.setattr(runner.os, "getuid", lambda: -1)
    elif damage == "missing_launcher":
        (case.campaign / "launcher.json").unlink()
    elif damage == "process_only_launcher":
        launch = {"identity": {"pid": 1}, "status": "unit metadata only"}
    elif damage == "plan_mismatch":
        launch["plan_id"] = "unit-other-plan"
    elif damage == "spec_mismatch":
        launch["spec_path"] = str(case.target / "other-spec.json")
    elif damage == "provider_mismatch":
        launch["provider"] = "unit-other-provider"
    elif damage == "fallback_enabled":
        launch["allow_fallback"] = True
    if damage in {"process_only_launcher", "plan_mismatch", "spec_mismatch", "provider_mismatch", "fallback_enabled"}:
        (case.campaign / "launcher.json").write_text(json.dumps(launch))
    calls = []
    original_environment, original_context = dict(case.environment), deepcopy(context)
    observed = case.measure(_recording_callback(calls), supplied_context=context)
    assert calls == []
    assert case.environment == original_environment
    assert context == original_context
    _assert_no_completion(observed, "release_context_unavailable")


def test_caller_success_json_and_claimed_seal_are_not_release_completion(release_context_case):
    case = release_context_case
    caller_claim = {"release_qualified": True, "admitted": True, "completion_authority": True}
    context = {**case.context, "completion_report": deepcopy(caller_claim), "observed": deepcopy(caller_claim)}
    calls = []
    observed = case.measure(
        _recording_callback(calls, claimed_sealed=True, output=json.dumps(caller_claim)),
        supplied_context=context,
    )
    # A claimed script exit/seal is followed by independent collection. This
    # callback creates no phase manifest, catalog, JUnit, or AST evidence.
    assert len(calls) == 2
    assert calls[0]["spec"].command == case.command
    assert "--collect-only" in calls[1]["spec"].command
    actual_environment = dict(calls[0]["environment"])
    runtime = Path(actual_environment.pop("COMPLAINT_INTAKE_RELEASE_RUNTIME_DIR"))
    assert runtime.is_dir() and runtime.stat().st_mode & 0o777 == 0o700
    assert actual_environment == {
        **case.environment, STATE_ENV: str(case.campaign), TARGET_ENV: str(case.target),
    }
    assert "completion_report" not in calls[0]["environment"]
    assert "observed" not in calls[0]["environment"]
    assert json.dumps(caller_claim) not in calls[0]["spec"].command
    _assert_no_completion(observed, "missing_phase_manifest")


def test_host_rechecks_fixed_qualification_around_actual_script_callback(release_context_case, monkeypatch):
    """An explicit unit callback cannot conceal changed host qualification."""
    from integrations.ipfs_accelerate import release_evidence as bridge
    case = release_context_case
    first = {"host_binding": {"path": "unit-only-fixed-slot", "sha256": "a" * 64},
             "qualification": {"path": "unit-only-proof", "sha256": "b" * 64},
             "producer": {"path": "unit-only-producer", "sha256": "c" * 64},
             "source_identity": {"unit": "before"}, "required_case_count": 1}
    second = {**first, "source_identity": {"unit": "changed"}}
    reads = []
    def read(root, spec, state, *, phase, validation_environment):
        assert validation_environment is case.environment
        reads.append((root, spec, state, phase))
        return first if len(reads) == 1 else second
    monkeypatch.setattr(bridge, "read_current_release_qualification", read)
    calls = []
    observed = case.measure(_recording_callback(calls, claimed_sealed=True))
    assert len(reads) == 2 and len(calls) == 1
    assert all(row == (case.candidate, case.candidate / runner.SPEC_RELATIVE, case.campaign, "pre-admission") for row in reads)
    _assert_no_completion(observed, "release_current_qualification_changed")
    measured = observed["host_measurement"]["current_release_qualification"]
    assert measured["host_binding"] == first["host_binding"]
    assert measured["before_after_equal"] is False and measured["completion_authority"] is False
