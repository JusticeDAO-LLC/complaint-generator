"""Observe the mediator-grounding campaign without touching the intake baseline."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import time

import pytest

from integrations.ipfs_accelerate import improvement_plan as compiler
from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate.campaign import DEFAULT_ARTIFACTS, campaign_artifacts


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = {
    "spec_relative": "docs/task_boards/complaint_mediator_grounding_spec.json",
    "plan_relative": "docs/task_boards/complaint_mediator_grounding_formal_work_plan.json",
    "board_relative": "docs/task_boards/complaint_mediator_grounding_task_board.md",
    "board_namespace": "complaint-mediator-grounding",
}
HISTORICAL = (compiler.SPEC_RELATIVE, compiler.PLAN_RELATIVE, compiler.BOARD_RELATIVE)


def _fail(reason: str) -> None:
    raise AssertionError(reason)


def _spec():
    spec = compiler.load_spec(ROOT / compiler.SPEC_RELATIVE)
    goal = deepcopy(spec["goals"][0])
    subgoal = deepcopy(goal["subgoals"][0])
    goal.update(id="MGND-G1", subgoals=[subgoal])
    subgoal["id"] = "MGND-S1"
    task = deepcopy(spec["tasks"][0])
    task.update(id="CIMP-MGND-OBS", goal_id=goal["id"], subgoal_id=subgoal["id"], depends_on=[],
                acceptance=["Observe the separate campaign without closing it from characterization."])
    spec.update(title="Mediator grounding observation fixture", goals=[goal], tasks=[task], campaign=dict(CAMPAIGN))
    return spec


def _write(root: Path, relative: str, value) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if not isinstance(value, str) else value, encoding="utf-8")
    path.chmod(0o600)
    return path


def _copy_historical(root: Path) -> dict[str, bytes]:
    saved = {}
    for relative in HISTORICAL:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        target.write_bytes(raw)
        saved[relative] = raw
    return saved


def _launch(root: Path, state: Path, spec_path: Path, spec: dict) -> dict:
    binding = compiler.campaign_observation_binding(spec)
    argv = ["python", "scripts/run_complaint_improvement_supervisor.py", "_run"]
    record = {
        "schema_version": "complaint-improvement-launcher@1",
        "repo_root": str(root), "spec_path": str(spec_path), "state_dir": str(state),
        "plan_id": binding["plan_id"], "source_generation": binding["source_generation"],
        "board_path": str(root / CAMPAIGN["board_relative"]),
        "provider": "grok_cli", "model": "grok-4.7", "allow_fallback": False,
        "owner_token": "synthetic-owner", "argv": argv, "merge_target": "campaign-test",
        "started_at": time.time() - 5,
        "identity": {"pid": 99999991, "session": 99999991, "process_group": 99999991,
                     "start_ticks": 1, "boot_id": "synthetic-boot", "argv": argv},
    }
    _write(state, "launcher.json", record)
    _write(state, f"{runner.STATE_PREFIX}_supervisor_status.json", {
        "status": "running", "supervisor_pid": 99999991, "daemon_pid": 99999992, "daemon_pid_alive": False,
    })
    _write(state, f"{runner.STATE_PREFIX}_task_state.json", {
        "active_task_id": "CIMP-MGND-OBS", "implementation_in_progress": False,
        "selectable_ready_task_ids": ["CIMP-MGND-OBS"],
    })
    return record


def _close_event(kind: str, binding: dict, cid: str, **extra) -> dict:
    return {
        "type": kind, "accepted": True, "task_id": "CIMP-MGND-OBS", "canonical_task_cid": cid,
        "plan_id": binding["plan_id"], "source_generation": binding["source_generation"],
        "outcome": "passed", **extra,
    }


def _guard_provider(monkeypatch) -> None:
    original = subprocess.Popen

    def guarded(args, *a, **kwargs):
        rendered = args if isinstance(args, (list, tuple)) else [args]
        text = " ".join(str(part) for part in rendered).lower()
        if "grok" in text:
            _fail("provider_started")
        return original(args, *a, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", guarded)
    monkeypatch.setattr(runner.subprocess, "Popen", guarded)


def _prepare(tmp_path: Path):
    historical = _copy_historical(tmp_path)
    spec = _spec()
    spec_path = _write(tmp_path, CAMPAIGN["spec_relative"], spec)
    compiler.generate(spec_path, tmp_path)
    state = tmp_path / "synthetic-control-plane"
    state.mkdir(mode=0o700)
    record = _launch(tmp_path, state, spec_path, spec)
    return spec, spec_path, state, record, historical


def test_repository_namespace_matches_the_grounding_campaign_selector() -> None:
    raw = json.loads((ROOT / CAMPAIGN["spec_relative"]).read_text(encoding="utf-8"))
    selected = campaign_artifacts(raw)
    if selected.board_namespace != CAMPAIGN["board_namespace"]:
        _fail("namespace")
    if (selected.spec_relative, selected.plan_relative, selected.board_relative) != (
            CAMPAIGN["spec_relative"], CAMPAIGN["plan_relative"], CAMPAIGN["board_relative"]):
        _fail("artifact_paths")
    if selected == DEFAULT_ARTIFACTS or set(selected.protected_paths) & set(HISTORICAL):
        _fail("historical_alias")
    if compiler.canonical_model_policy() != {
            "router": "ipfs_accelerate_py.llm_router", "provider": "grok_cli",
            "model": "grok-4.7", "allow_fallback": False}:
        _fail("model_policy")


def test_observation_binds_health_and_keeps_the_58_task_baseline(tmp_path, monkeypatch) -> None:
    repo_before = {relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() for relative in HISTORICAL}
    spec, spec_path, state, record, historical = _prepare(tmp_path)
    _guard_provider(monkeypatch)
    binding = compiler.campaign_observation_binding(spec)
    observed = runner.observe_separate_campaign(tmp_path, spec_path, state)
    if observed["provider_started"] or observed["paid_calls"] or observed["completion_authority"]:
        _fail("authority")
    if not observed["plan_bound"] or not observed["source_generation_bound"]:
        _fail("binding")
    if observed["binding"]["plan_id"] != binding["plan_id"] or observed["binding"]["source_generation"] != binding["source_generation"]:
        _fail("generation")
    if observed["binding"]["source_generation"] != record["source_generation"]:
        _fail("launcher_generation")
    if set(observed["task_cids"]) != {"CIMP-MGND-OBS"} or not observed["task_cids"]["CIMP-MGND-OBS"]:
        _fail("cid")
    route = observed["route"]
    if (route["model"] != "grok-4.7" or route["allow_fallback"] is not False or route["provider"] != "grok_cli"
            or route["router"] != "llm_router" or route["pool_max_entries"] != "1"
            or route["implement"] is not True or route["fallback_disabled"] is not True
            or route["validation_max_workers"] != "1"
            or str(route["implementation_timeout_seconds"]) != "900"
            or route["argv_implementation_timeout"] != "900"
            or route["max_agent_turns"] != "64"
            or route["resource_min_free_bytes"] < 1_000_000_000
            or route["resource_min_free_inodes"] < 1000):
        _fail("route_caps")
    baseline = observed["historical_baseline"]
    if not baseline["unchanged"] or baseline["read_error"] or not baseline["immutable"]:
        _fail("baseline_mutated")
    if baseline["tasks"]["count"] != 58 or baseline["tasks"]["markdown_completed"] != 58 or baseline["tasks"]["remapped"]:
        _fail("baseline_count")
    if any((tmp_path / relative).read_bytes() != raw for relative, raw in historical.items()):
        _fail("baseline_bytes")
    if any(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest for relative, digest in repo_before.items()):
        _fail("repository_baseline")
    source = observed["native_state_source"]
    if not isinstance(source, dict) or source.get("completion_authority") is not False:
        _fail("native_seam")
    if source.get("source") not in {"native_control_plane", "legacy_json", "unavailable"}:
        _fail("native_source")
    if source.get("source") == "unavailable" and not observed["native_read_errors"]:
        _fail("unavailable_hidden")
    if observed["native_closed_task_ids"]:
        _fail("unclosed_task_reported_closed")


def test_characterization_and_manual_metadata_do_not_close_tasks(tmp_path, monkeypatch) -> None:
    spec, spec_path, state, _record, historical = _prepare(tmp_path)
    _guard_provider(monkeypatch)
    board = tmp_path / CAMPAIGN["board_relative"]
    text = board.read_text(encoding="utf-8")
    text = text.replace("- Status: todo", "- Status: completed", 1)
    text = text.replace("- Completion: validation", "- Completion: manual\n- Counts as characterization pass: true\n- Characterization: pass\n- Manual completion: true", 1)
    board.write_text(text, encoding="utf-8")
    events = state / f"{runner.STATE_PREFIX}_events.jsonl"
    events.write_text("".join(json.dumps(event) + "\n" for event in (
        {"type": "characterization", "counts_as_characterization_pass": True,
         "task_id": "CIMP-MGND-OBS", "accepted": True},
        {"type": "manual_metadata", "manual": True, "task_id": "CIMP-MGND-OBS", "accepted": True},
    )), encoding="utf-8")
    observed = runner.observe_separate_campaign(tmp_path, spec_path, state)
    if observed["native_closed_task_ids"] or observed["markdown_or_characterization_grants_completion"]:
        _fail("metadata_closed_task")
    if "CIMP-MGND-OBS" not in observed["markdown_completed_task_ids"]:
        _fail("markdown_not_visible")
    if "CIMP-MGND-OBS" not in observed["characterization_task_ids"] or "CIMP-MGND-OBS" not in observed["manual_metadata_task_ids"]:
        _fail("metadata_not_visible")
    if observed["native_closure"]["ignored_characterization"] < 1 or observed["native_closure"]["ignored_manual"] < 1:
        _fail("ignored_frames")
    if observed["completion_authority"] or not observed["historical_baseline"]["unchanged"]:
        _fail("authority_or_baseline")
    if any((tmp_path / relative).read_bytes() != raw for relative, raw in historical.items()):
        _fail("baseline_bytes")


def test_only_matching_native_validation_merge_and_callback_close(tmp_path, monkeypatch) -> None:
    spec, spec_path, state, _record, _historical = _prepare(tmp_path)
    _guard_provider(monkeypatch)
    binding = compiler.campaign_observation_binding(spec)
    first = runner.observe_separate_campaign(tmp_path, spec_path, state)
    cid = first["task_cids"]["CIMP-MGND-OBS"]
    events = state / f"{runner.STATE_PREFIX}_events.jsonl"
    partial = [_close_event("validation_accepted", binding, cid), _close_event("merge_accepted", binding, cid)]
    events.write_text("".join(json.dumps(event) + "\n" for event in partial), encoding="utf-8")
    partial_observed = runner.observe_separate_campaign(tmp_path, spec_path, state)
    if partial_observed["native_closed_task_ids"]:
        _fail("partial_closure")
    foreign = [
        _close_event("validation_accepted", binding, cid, source_generation="other-generation"),
        _close_event("merge_accepted", binding, cid, plan_id="other-plan"),
        _close_event("completion_callback_accepted", binding, "not-the-cid"),
        _close_event("validation_accepted", binding, cid, skipped=True, outcome="skipped"),
    ]
    complete = [_close_event(kind, binding, cid) for kind in ("validation_accepted", "merge_accepted", "completion_callback_accepted")]
    events.write_text("".join(json.dumps(event) + "\n" for event in [*foreign, *complete]), encoding="utf-8")
    closed = runner.observe_separate_campaign(tmp_path, spec_path, state)
    if closed["native_closed_task_ids"] != ["CIMP-MGND-OBS"] or closed["completion_authority"]:
        _fail("native_closure")
    if closed["binding"]["plan_id"] != binding["plan_id"] or closed["active_task_cid_bound"] is not True:
        _fail("bound_observation")
    launcher = json.loads((state / "launcher.json").read_text(encoding="utf-8"))
    launcher["source_generation"] = "other-generation"
    _write(state, "launcher.json", launcher)
    rejected = runner.observe_separate_campaign(tmp_path, spec_path, state)
    if rejected["native_closed_task_ids"] or rejected["source_generation_bound"] or rejected["healthy"]:
        _fail("foreign_generation_closed")
    if rejected["native_closure"].get("rejected_reason") != "plan_or_source_generation_mismatch":
        _fail("mismatch_hidden")


def test_native_read_failure_stays_truthful(tmp_path, monkeypatch) -> None:
    spec, spec_path, state, _record, historical = _prepare(tmp_path)
    _guard_provider(monkeypatch)

    def unavailable(repo_root, spec_path, state_dir):
        return {"status": "state_error", "healthy": False, "native_state": {},
                "native_state_source": {"source": "unavailable", "completion_authority": False},
                "native_read_errors": {"state": "native_state_reader_failed"}, "completion_authority": False}

    monkeypatch.setattr(runner, "status", unavailable)
    observed = runner.observe_separate_campaign(tmp_path, spec_path, state)
    if observed["native_state_source"]["source"] != "unavailable":
        _fail("source_rewritten")
    if observed["native_read_errors"].get("state") != "native_state_reader_failed":
        _fail("error_hidden")
    if observed["healthy"] or observed["provider_started"] or observed["native_closed_task_ids"]:
        _fail("failure_promoted")
    if any((tmp_path / relative).read_bytes() != raw for relative, raw in historical.items()):
        _fail("baseline_bytes")
    if not observed["task_cids"]:
        _fail("identity_lost")
