"""Real Native event chains and private files; process observations are seams."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import watchdog_reconciliation as module
from integrations.ipfs_accelerate.improvement_plan import source_generation
from integrations.ipfs_accelerate.improvement_runner import _event_timestamp
from ipfs_accelerate_py.agent_supervisor.prompt.prompt_workflow import prompt_workflow_cid
from ipfs_accelerate_py.agent_supervisor.runtime.event_log import append_jsonl_event


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    path.chmod(0o600)


@pytest.fixture
def historical(tmp_path):
    root = tmp_path / "source"
    state = tmp_path / "campaign"
    workroot = tmp_path / "worktrees"
    workspace = workroot / "workspace_fixture"
    archive = tmp_path / "closed-owner"
    for path in (root, state, workspace, archive):
        path.mkdir(parents=True, mode=0o700)
    spec = json.loads((Path(__file__).resolve().parents[1] /
        "docs/task_boards/complaint_gui_ux_overhaul_spec.json").read_text())
    scope = {key: prompt_workflow_cid({"fixture_scope": key}) for key in
        ("repository_root_cid", "policy_root", "run_cid")}
    key = "f" * 64
    terminal = prompt_workflow_cid({"fixture_terminal": True})
    task_cid = prompt_workflow_cid({"fixture_task": True})
    task_key = "task/v1/" + hashlib.sha256(b"fixture_task").hexdigest()
    argv = ["/usr/bin/python", str(root / "scripts/run_complaint_improvement_supervisor.py"), "_run",
        "--repo-root", str(root), "--spec", str(root / "spec.json"), "--state-dir", str(state),
        "--owner-token", "fixture_token", "--merge-target", "fixture_branch"]
    launch = {"status": "stopped", "started_at": 110.0, "stopped_at": 190.0,
        "source_generation": source_generation(spec), "argv": argv,
        "identity": {"argv": argv, "pid": 42424242, "session": 42424242, "process_group": 42424242,
            "start_ticks": 7, "boot_id": "synthetic_kernel_birth"},
        "repo_root": str(root), "state_dir": str(state), "plan_id": "fixture_plan",
        "owner_token": "fixture_token", "merge_target": "fixture_branch"}
    ledger = {"scope": scope, "incidents": {key: {"terminal_cid": terminal, "attempts": 1, "phase": "uncertain"}}}
    manifest = {"schema": "complaint-owned-closure-preservation@1", "completion_authority": False, "files": {}}
    for name, value in {"launcher.json": launch, "container_shutdown.json": {"quiesced": True},
            "watchdog/campaign-progress-watchdog.json": ledger}.items():
        _write(archive / name, value)
        raw = (archive / name).read_bytes()
        manifest["files"][name] = {"present": True, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    _write(archive / "manifest.json", manifest)
    digest = hashlib.sha256((archive / "manifest.json").read_bytes()).hexdigest()
    command = ["/usr/bin/python", "-m", "ipfs_accelerate_py.agent_supervisor.runtime.grok_cli_runner",
        "--workspace", str(workspace), "--model", "grok-4.7", "--max-turns", "64"]
    log = state / "implementation_logs" / ("cimp-ux-01-attempt-2-" + "a" * 32 + ".log")
    log.parent.mkdir(mode=0o700)
    log.write_text("\n".join(["Task: CIMP-UX-01 Synthetic fixture", "Started: " + _iso(131),
        "Workspace: " + str(workspace), "Branch: fixture_branch", "Baseline: fixture_baseline",
        "Command: " + shlex.join(command), "", '{"type":"usage","usage":{"input_tokens":1}}',
        '{"type":"tool_call","name":"synthetic_tool"}', '{"type":"end"}', ""]))
    log.chmod(0o600)
    os.utime(log, (170, 170))
    event_path = state / "complaint_intake_events.jsonl"
    append_jsonl_event(event_path, "task_selected", {"task_id": "CIMP-UX-01", "timestamp": _iso(130)})
    start = append_jsonl_event(event_path, "implementation_started", {"task_id": "CIMP-UX-01", "attempt": 2,
        "canonical_task_cid": task_cid, "canonical_task_key": task_key, "worktree_path": str(workspace), "board_namespace": "fixture_board.md",
        "timestamp": _iso(140), "branch": "fixture_branch", "baseline_ref": "fixture_baseline",
        "log_path": str(log), "execution_mode": "model-assisted", "command": command})
    append_jsonl_event(event_path, "implementation_finished", {"task_id": "CIMP-UX-01", "attempt": 2,
        "canonical_task_cid": task_cid, "canonical_task_key": task_key, "board_namespace": "fixture_board.md", "worktree_path": str(workspace), "timestamp": _iso(180)})
    runner = SimpleNamespace(_event_timestamp=_event_timestamp,
        _full_launch_record=lambda _: True, _campaign_tuple_matches=lambda *args: True,
        _shutdown_verified=lambda *args: True, _owner_liveness=lambda _: "dead",
        recorded_worktree_root=lambda *args: (workroot, None), owns_process=lambda _: True,
        _native_modules=lambda _: (None, SimpleNamespace(parse_task_file=lambda *args, **kwargs: [
            SimpleNamespace(task_id="CIMP-UX-01", canonical_task_cid=task_cid, canonical_task_key=task_key)])), TASK_PREFIX="## CIMP-")
    watcher = SimpleNamespace(root=root, state=state, spec_path=root / "spec.json", spec=spec, scope=scope,
        runner=runner, artifacts=SimpleNamespace(board_relative="fixture_board.md", board_namespace="fixture-campaign-slug"),
        _launch=lambda: ({"fixture_current_owner": True}, True, "c" * 64))
    context = {"scope": scope, "incident_key": key, "terminal_cid": terminal,
        "recovery_ordinal": 1, "action_receipt_cid": prompt_workflow_cid({"fixture_action": True}),
        "action_started_at_ms": 100000, "action_finished_at_ms": 120000}
    return SimpleNamespace(root=root, state=state, workroot=workroot, workspace=workspace, archive=archive,
        digest=digest, log=log, event_path=event_path, watcher=watcher, context=context, start=start,
        verifier=lambda: module.ClosedRestartProof(watcher, archive, expected_manifest_sha256=digest))


def test_private_closed_owner_and_hash_chained_actual_log_metadata_produce_closed_proof(historical):
    verifier = historical.verifier()
    before = {str(p): p.read_bytes() for p in historical.state.rglob("*") if p.is_file()}
    proof = verifier(historical.context)
    assert proof["effects_verified"] is True and proof["later_work_verified"] is True
    assert proof["progress_attempt"] == 2 and proof["progress_task_id"] == "CIMP-UX-01"
    assert proof["restart_started_at_ms"] == 110000 and proof["progress_observed_at_ms"] == 180000
    assert proof["current_owner_token"] == "c" * 64 and len(proof["evidence_cids"]) == 4
    assert proof == verifier(historical.context)
    assert "synthetic_tool" not in json.dumps(proof) and "Command" not in json.dumps(proof)
    assert before == {str(p): p.read_bytes() for p in historical.state.rglob("*") if p.is_file()}


@pytest.mark.parametrize("damage", ["archive", "owner_alive", "owner_unknown", "scope", "incident", "current_unowned", "event_hash", "partial_event", "log_header", "log_command", "missing_usage", "log_outside", "log_time", "event_namespace_slug", "task_key"])
def test_unowned_stale_or_tampered_historical_work_never_produces_proof(historical, damage):
    verifier = historical.verifier()
    if damage == "archive":
        (historical.archive / "launcher.json").write_text('{}')
    elif damage == "owner_alive":
        historical.watcher.runner._owner_liveness = lambda _: "alive"
    elif damage == "owner_unknown":
        historical.watcher.runner._owner_liveness = lambda _: "unknown"
    elif damage == "scope":
        verifier.ledger["scope"] = {"foreign": True}
    elif damage == "incident":
        historical.context = {**historical.context, "terminal_cid": prompt_workflow_cid({"foreign": True})}
    elif damage == "current_unowned":
        historical.watcher.runner.owns_process = lambda _: False
    elif damage == "event_hash":
        values = [json.loads(line) for line in historical.event_path.read_text().splitlines()]
        values[1]["attempt"] = 1
        historical.event_path.write_text("\n".join(json.dumps(value) for value in values) + "\n")
    elif damage == "partial_event":
        historical.event_path.write_bytes(historical.event_path.read_bytes()[:-1])
    elif damage == "log_header":
        historical.log.write_text(historical.log.read_text().replace("Task: CIMP-UX-01", "Task: CIMP-UX-99"))
    elif damage == "log_command":
        historical.log.write_text(historical.log.read_text().replace("--model grok-4.7", "--model unrelated"))
    elif damage == "missing_usage":
        historical.log.write_text(historical.log.read_text().replace('"type":"usage"', '"type":"thought"'))
    elif damage == "log_outside":
        preserved = historical.log.with_suffix(".original")
        historical.log.rename(preserved)
        historical.log.symlink_to(preserved)
    elif damage == "log_time":
        os.utime(historical.log, (201, 201))
    elif damage in {"event_namespace_slug", "task_key"}:
        from ipfs_accelerate_py.agent_supervisor.runtime.event_log import _event_identity
        values = [json.loads(line) for line in historical.event_path.read_text().splitlines()]
        previous = ""
        for value in values:
            if value["type"] in {"implementation_started", "implementation_finished"}:
                if damage == "event_namespace_slug":
                    value["board_namespace"] = "fixture-campaign-slug"
                else:
                    value["canonical_task_key"] = "task/v1/" + "0" * 64
            value["previous_event_id"] = previous
            value["event_id"] = _event_identity(value)
            previous = value["event_id"]
        historical.event_path.write_text("\n".join(json.dumps(value) for value in values) + "\n")
    with pytest.raises(ValueError):
        verifier(historical.context)


def test_private_archive_must_match_the_explicit_manifest_pin(historical):
    with pytest.raises(ValueError, match="manifest_changed"):
        module.ClosedRestartProof(historical.watcher, historical.archive, expected_manifest_sha256="0" * 64)



def test_public_reconciliation_uses_actual_native_receipt_and_preserves_its_ordinal(historical, monkeypatch):
    from integrations.ipfs_accelerate import campaign_watchdog
    from ipfs_accelerate_py.agent_supervisor.rescue.campaign_watchdog import (
        CampaignProgressWatchdog, CampaignProgressWatchdogPolicy, OBSERVATION_SCHEMA,
    )
    from ipfs_accelerate_py.agent_supervisor.rescue.supervisor_recovery import RecoveryActionObservation
    watcher = historical.watcher
    watcher.directory = historical.state / "watchdog"
    now = [69000]
    calls = []
    task_cid = historical.start["canonical_task_cid"]
    observed = {"schema": OBSERVATION_SCHEMA, "scope": watcher.scope,
        "status": "stalled", "healthy": False, "completion_verified": False, "manual_hold": False,
        "hold_reason": "", "progress_verified": False, "owner_binding_verified": True,
        "recovery_permitted": True, "pending_task_ids": ["CIMP-UX-01"], "active_task_id": "",
        "active_task_cid": "", "attempt": 0, "progress_token": "before", "owner_token": "a" * 64,
        "grace_until_ms": 0}
    def recover(context):
        calls.append(context)
        now[0] = 120000
        return RecoveryActionObservation(False, ("old_lane_fenced", "lane_restarted"), {"healthy": False}, partial=True)
    watcher.observe = lambda: deepcopy(observed)
    native = CampaignProgressWatchdog(watcher.directory, repository_root=watcher.root, scope=watcher.scope,
        observe=watcher.observe, recover=recover, policy=CampaignProgressWatchdogPolicy(deadline_ms=1_200_000),
        clock_ms=lambda: now[0])
    assert native.run_once()["status"] == "confirming"
    now[0] = 100000
    assert native.run_once()["reason"] == "application_recovery_effects_unproven"
    ledger = json.loads(native.state_path.read_text())
    assert next(iter(ledger["incidents"].values()))["phase"] == "uncertain"
    _write(historical.archive / "watchdog/campaign-progress-watchdog.json", ledger)
    manifest = json.loads((historical.archive / "manifest.json").read_text())
    raw = (historical.archive / "watchdog/campaign-progress-watchdog.json").read_bytes()
    manifest["files"]["watchdog/campaign-progress-watchdog.json"] = {
        "present": True, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    _write(historical.archive / "manifest.json", manifest)
    digest = hashlib.sha256((historical.archive / "manifest.json").read_bytes()).hexdigest()
    observed.update(status="active", healthy=True, progress_verified=True, owner_token="c" * 64,
        active_task_id="CIMP-UX-01", active_task_cid=task_cid, attempt=3, progress_token="actual_later_current_work")
    monkeypatch.setattr(campaign_watchdog, "ComplaintCampaignWatchdog", lambda *args: watcher)
    terminal_file, = (watcher.directory / "programmatic-recovery").glob("*.json")
    original_terminal = terminal_file.read_bytes()
    result = module.reconcile_closed_restart(watcher.root, watcher.spec_path, watcher.state, historical.archive,
        expected_manifest_sha256=digest)
    assert result["results"][0]["reason"] == "known_restart_effects_verified"
    assert result["provider_calls"] == 0 and result["attempt_refunded"] is False
    entry = next(iter(json.loads(native.state_path.read_text())["incidents"].values()))
    assert entry["phase"] == "finished" and entry["attempts"] == 1
    assert terminal_file.read_bytes() == original_terminal and len(calls) == 1
    again = module.reconcile_closed_restart(watcher.root, watcher.spec_path, watcher.state, historical.archive,
        expected_manifest_sha256=digest)
    assert again["results"][0]["reason"] == "known_restart_effects_already_reconciled"
    assert terminal_file.read_bytes() == original_terminal and len(calls) == 1
