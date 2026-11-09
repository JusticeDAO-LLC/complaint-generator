"""Real inert launch publication; availability stubs never qualify a provider.

The kernel supplies the spawned launcher's identity. No Native implementation,
provider, Docker effect, claim, task-state or completion is exercised here.
"""
from pathlib import Path
import json
import subprocess
import sys

import pytest

from integrations.ipfs_accelerate import improvement_plan as compiler
from integrations.ipfs_accelerate import improvement_runner as runner


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
ROOT = Path(__file__).resolve().parents[1]


def _spec():
    return {
        "schema_version": "complaint-generator.synthetic-publication@1",
        "title": "Synthetic generation publication",
        "campaign": {
            "spec_relative": "docs/task_boards/synthetic_generation_spec.json",
            "plan_relative": "docs/task_boards/synthetic_generation_plan.json",
            "board_relative": "docs/task_boards/synthetic_generation_board.md",
            "board_namespace": "synthetic-generation-publication",
        },
        "provider": compiler.canonical_model_policy(),
        "execution_policy": {"one_lane": True},
        "goals": [{"id": "goal.publication", "title": "Publication", "subgoals": [
            {"id": "subgoal.publication", "title": "Bind generation"}]}],
        "tasks": [{"id": "CIMP-UX-SYN-01", "title": "Synthetic source generation",
            "goal_id": "goal.publication", "subgoal_id": "subgoal.publication",
            "priority": "P0", "targets": ["tests/synthetic_publication.py"],
            "acceptance": ["Normal launch binds its actual source generation"],
            "validation_commands": ["python -m pytest -q tests/synthetic_publication.py"],
            "depends_on": [], "implementation_prompt": "Synthetic inert fixture only."}],
    }


@pytest.mark.parametrize("indent", [None, 2])
def test_actual_start_publishes_compiled_generation_and_duplicate_keeps_receipt(tmp_path, monkeypatch, indent):
    monkeypatch.chdir(ROOT)
    runner._native_modules(ROOT)
    root = tmp_path / "synthetic-source"
    root.mkdir(mode=0o700)
    state = tmp_path / "private-state"
    state.mkdir(mode=0o700)
    spec = _spec()
    spec_path = root / spec["campaign"]["spec_relative"]
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(json.dumps(spec, indent=indent))
    generated = compiler.generate(spec_path, root)
    plan = compiler.build_improvement_work_plan(spec)
    launcher = root / "scripts/run_complaint_improvement_supervisor.py"
    launcher.parent.mkdir()
    launcher.write_text("import time\ntime.sleep(30)\n")
    # These are explicit unit availability seams, not Docker/provider proof.
    monkeypatch.setattr(runner, "doctor", lambda *_a, **_k: {
        "status": "ready", "merge_target": "synthetic-publication",
        "native_plan_id": generated["receipt"]["plan_id"]})
    monkeypatch.setattr(runner, "_observe_campaign_containers", lambda *_a, **_k: True)
    actual_popen = runner.subprocess.Popen
    children = []

    def capture(argv, **kwargs):
        child = actual_popen(argv, **kwargs)
        if "_run" in argv and "--owner-token" in argv:
            children.append(child)
        return child

    monkeypatch.setattr(runner.subprocess, "Popen", capture)
    try:
        launched = runner.start(root, spec_path, state)
        assert launched["status"] == "starting" and launched["progress_verified"] is False
        assert len(children) == 1 and children[0].poll() is None
        record = runner._read_json(state / "launcher.json")
        assert runner.owns_process(record)
        assert record["plan_id"] == plan.plan_id
        assert record.get("source_generation") == plan.metadata["spec_sha256"]
        assert record["source_generation"] == compiler.source_generation(compiler.load_spec(spec_path))
        assert record["provider"] == "grok_cli" and record["model"] == "grok-4.7"
        assert record["allow_fallback"] is False
        original = (state / "launcher.json").read_bytes()
        assert runner.start(root, spec_path, state)["status"] == "already_running"
        assert len(children) == 1 and (state / "launcher.json").read_bytes() == original
        # Exercise the real separate-campaign binding consumer. Health itself
        # is deliberately unavailable: this child is no Native daemon.
        monkeypatch.setattr(runner, "status", lambda *_a, **_k: {
            "status": "starting", "healthy": False, "native_state": {}})
        observed = runner.observe_separate_campaign(root, spec_path, state)
        assert observed["plan_bound"] is True and observed["source_generation_bound"] is True
        assert observed["healthy"] is False and observed["native_closed_task_ids"] == []
        assert observed["completion_authority"] is False and observed["provider_started"] is False
        assert (state / "launcher.json").read_bytes() == original
        assert not list(state.glob("*task_state*")) and not (state / "control-plane").exists()
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
