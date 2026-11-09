"""Read actual closed-owner and Grok history for Native effect reconciliation.

The source archive must be an exact private copy of a normal public stop's
metadata. It grants no completion, restart, retry, refund or content access.
Native independently checks the terminal, ordinal, exact action receipt,
current owned work and stable verifier output before appending a resolution.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import stat
import shlex
import os

from .improvement_recovery import _owned_bytes
from .campaign_watchdog import _digest, preserved_native_watchdog_budgets


def _read(path, maximum=2_000_000, *, legacy=False):
    path = Path(path)
    if path.resolve(strict=True) != path.absolute():
        raise ValueError("reconciliation_file_alias")
    return _owned_bytes(path, maximum, legacy_group_write=legacy)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _events(raw):
    from ipfs_accelerate_py.agent_supervisor.runtime.event_log import (
        _event_identity, strict_event_envelope_fields,
    )
    if not raw.endswith(b"\n"):
        raise ValueError("reconciliation_event_stream_partial")
    values = [json.loads(line) for line in raw.splitlines()]
    if not 1 <= len(values) <= 50_000:
        raise ValueError("reconciliation_event_bound")
    previous = ""
    for sequence, event in enumerate(values, 1):
        strict_event_envelope_fields(event)
        if (event.get("event_id") != _event_identity(event) or event.get("sequence") != sequence
                or event.get("previous_event_id") != previous
                or event.get("stream_id") != values[0].get("stream_id")
                or event.get("snapshot_id") != values[0].get("snapshot_id")):
            raise ValueError("reconciliation_native_event_chain_invalid")
        previous = event["event_id"]
    return values


def _log_evidence(raw, start, selected_at, finished_at, runner):
    """Inspect only closed Native headers and frame kinds, never tool bodies."""
    if not raw.endswith(b"\n"):
        raise ValueError("reconciliation_grok_log_partial")
    headers = {}
    for line in raw.splitlines()[:8]:
        key, sep, value = line.partition(b": ")
        if sep and key in {b"Task", b"Started", b"Workspace", b"Branch", b"Baseline", b"Command"}:
            if key in headers:
                raise ValueError("reconciliation_grok_header_duplicate")
            headers[key] = value.decode("utf-8")
    stamp = runner._event_timestamp({"timestamp": headers.get(b"Started")})
    if (headers.get(b"Task", "").split(" ", 1)[0] != start["task_id"]
            or headers.get(b"Workspace") != start["worktree_path"]
            or headers.get(b"Branch") != start["branch"]
            or headers.get(b"Baseline") != start["baseline_ref"]
            or stamp is None or not selected_at <= stamp <= runner._event_timestamp(start) <= finished_at):
        raise ValueError("reconciliation_grok_log_binding_invalid")
    command = start.get("command")
    if (not isinstance(command, list) or len(command) < 8
            or command[1:3] != ["-m", "ipfs_accelerate_py.agent_supervisor.runtime.grok_cli_runner"]
            or "--model" not in command or command[command.index("--model") + 1] != "grok-4.7"
            or "--workspace" not in command or command[command.index("--workspace") + 1] != start["worktree_path"]
            or "--max-turns" not in command or command[command.index("--max-turns") + 1] != "64"
            or "allow-fallback" in " ".join(command)
            or shlex.split(headers.get(b"Command", "")) != command):
        raise ValueError("reconciliation_grok_route_invalid")
    counts = Counter()
    for line in raw.splitlines():
        if not line.startswith(b"{"):
            continue
        try:
            frame = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(frame, dict):
            continue
        kind = frame.get("type")
        if kind == "usage" and isinstance(frame.get("usage"), dict):
            counts[kind] += 1
        elif kind in {"tool_call", "tool_call_update"}:
            counts[kind] += 1
    if not counts["usage"] or not counts["tool_call"]:
        raise ValueError("reconciliation_grok_actual_work_missing")
    return dict(counts)


class ClosedRestartProof:
    """Pure verifier over preserved owner metadata and actual retained work."""

    def __init__(self, watcher, closed_owner_directory, *, expected_manifest_sha256):
        self.watcher = watcher
        self.directory = Path(closed_owner_directory).absolute()
        info = self.directory.lstat()
        if (self.directory.resolve(strict=True) != self.directory or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700
                or not re.fullmatch(r"[0-9a-f]{64}", str(expected_manifest_sha256))):
            raise ValueError("reconciliation_archive_unowned")
        self.manifest_raw = _read(self.directory / "manifest.json", 32768)
        if _sha(self.manifest_raw) != expected_manifest_sha256:
            raise ValueError("reconciliation_archive_manifest_changed")
        manifest = json.loads(self.manifest_raw)
        if (manifest.get("schema") != "complaint-owned-closure-preservation@1"
                or manifest.get("completion_authority") is not False or not isinstance(manifest.get("files"), dict)):
            raise ValueError("reconciliation_archive_schema_invalid")
        self.raw = {}
        for name in ("launcher.json", "container_shutdown.json", "watchdog/campaign-progress-watchdog.json"):
            raw = _read(self.directory / name)
            row = manifest["files"].get(name, {})
            if row != {"present": True, "sha256": _sha(raw), "bytes": len(raw)}:
                raise ValueError("reconciliation_archive_file_changed")
            self.raw[name] = raw
        self.launch = json.loads(self.raw["launcher.json"])
        self.shutdown = json.loads(self.raw["container_shutdown.json"])
        self.ledger = json.loads(self.raw["watchdog/campaign-progress-watchdog.json"])

    def _owner(self):
        watcher, record = self.watcher, self.launch
        runner = watcher.runner
        from .improvement_plan import source_generation
        if (not runner._full_launch_record(record)
                or not runner._campaign_tuple_matches(record, watcher.root, watcher.spec_path, watcher.state)
                or record.get("source_generation") != source_generation(watcher.spec)
                or record.get("status") != "stopped"
                or not runner._shutdown_verified(record, self.shutdown, watcher.root, watcher.state)
                or runner._owner_liveness(record.get("identity")) != "dead"):
            raise ValueError("reconciliation_closed_owner_unverified")
        workroot, binding = runner.recorded_worktree_root(record, watcher.state)
        argv, identity = record.get("argv"), record.get("identity")
        if not isinstance(argv, list) or not isinstance(identity, dict) or not argv:
            raise ValueError("reconciliation_closed_owner_identity_invalid")
        expected = [argv[0], str(watcher.root / "scripts/run_complaint_improvement_supervisor.py"), "_run",
            "--repo-root", str(watcher.root), "--spec", str(watcher.spec_path), "--state-dir", str(watcher.state),
            "--owner-token", record.get("owner_token"), "--merge-target", record.get("merge_target")]
        if binding is not None:
            expected.extend(["--worktree-root", str(workroot)])
        if (argv != expected or identity.get("argv") != argv or not Path(argv[0]).is_absolute()
                or type(identity.get("pid")) is not int or identity["pid"] <= 1
                or identity.get("session") != identity["pid"] or identity.get("process_group") != identity["pid"]
                or type(identity.get("start_ticks")) is not int or identity["start_ticks"] <= 0
                or not identity.get("boot_id")):
            raise ValueError("reconciliation_closed_owner_identity_invalid")
        return workroot

    def __call__(self, context):
        from ipfs_accelerate_py.agent_supervisor.prompt.prompt_workflow import prompt_workflow_cid
        watcher, runner = self.watcher, self.watcher.runner
        workroot = self._owner()
        current, bound, current_token = watcher._launch()
        if (not bound or not runner.owns_process(current) or self.ledger.get("scope") != watcher.scope
                or self.ledger.get("incidents", {}).get(context["incident_key"], {}).get("terminal_cid") != context["terminal_cid"]
                or self.ledger["incidents"][context["incident_key"]].get("attempts") != context["recovery_ordinal"]):
            raise ValueError("reconciliation_owner_or_incident_changed")
        for name, raw in self.raw.items():
            if _read(self.directory / name) != raw:
                raise ValueError("reconciliation_archive_changed")
        if _read(self.directory / "manifest.json", 32768) != self.manifest_raw:
            raise ValueError("reconciliation_archive_changed")
        started = float(self.launch["started_at"])
        stopped = float(self.launch["stopped_at"])
        if not context["action_started_at_ms"] <= int(started * 1000) <= context["action_finished_at_ms"]:
            raise ValueError("reconciliation_restart_outside_action")
        raw_events = _read(watcher.state / "complaint_intake_events.jsonl", 32 * 1024 * 1024, legacy=True)
        events = _events(raw_events)
        tasks = runner._native_modules(watcher.root)[1].parse_task_file(
            watcher.root / watcher.artifacts.board_relative, task_header_prefix=runner.TASK_PREFIX)
        task_identities = {task.task_id: (task.canonical_task_cid, task.canonical_task_key) for task in tasks}
        # Native's legacy-markdown event namespace is the board filename.
        # Host's campaign slug remains a separate plan/spec scope binding.
        native_board = Path(watcher.artifacts.board_relative).name
        candidates = []
        for index, start in enumerate(events):
            stamp = runner._event_timestamp(start)
            if (start.get("type") != "implementation_started" or stamp is None or not started <= stamp <= stopped
                    or (start.get("canonical_task_cid"), start.get("canonical_task_key")) != task_identities.get(start.get("task_id"))
                    or start.get("board_namespace") != native_board
                    or start.get("execution_mode") != "model-assisted"):
                continue
            workspace = Path(str(start.get("worktree_path") or ""))
            if workspace.parent != workroot or workspace.resolve() != workspace:
                raise ValueError("reconciliation_worktree_binding_invalid")
            finish = next((event for event in events[index + 1:] if event.get("type") == "implementation_finished"
                and event.get("task_id") == start["task_id"] and event.get("attempt") == start["attempt"]
                and event.get("canonical_task_cid") == start["canonical_task_cid"]
                and event.get("canonical_task_key") == start["canonical_task_key"]
                and event.get("board_namespace") == native_board
                and event.get("worktree_path") == start["worktree_path"]), None)
            if finish is None:
                continue
            finished = runner._event_timestamp(finish)
            if finished is None or not max(started, context["action_finished_at_ms"] / 1000) < finished <= stopped:
                continue
            selection = next((event for event in reversed(events[:index]) if event.get("type") == "task_selected"
                and event.get("task_id") == start["task_id"]), None)
            selected = runner._event_timestamp(selection or {})
            log = Path(str(start.get("log_path") or ""))
            if (selected is None or selected < started or log.parent != watcher.state / "implementation_logs"
                    or not re.fullmatch(re.escape(start["task_id"].lower()) + "-attempt-" + str(start["attempt"]) + r"-[0-9a-f]{32}\.log", log.name)):
                raise ValueError("reconciliation_attempt_binding_invalid")
            raw_log = _read(log, 32 * 1024 * 1024)
            counts = _log_evidence(raw_log, start, selected, finished, runner)
            if not started <= log.stat().st_mtime <= stopped:
                raise ValueError("reconciliation_log_time_invalid")
            candidates.append((start, finish, finished, _sha(raw_log), counts))
        if len(candidates) != 1:
            raise ValueError("reconciliation_later_work_missing_or_ambiguous")
        start, finish, finished, log_sha, counts = candidates[0]
        evidence = [{"archive_manifest_sha256": _sha(self.manifest_raw)},
            {"launcher_sha256": _sha(self.raw["launcher.json"]), "shutdown_sha256": _sha(self.raw["container_shutdown.json"])},
            {"event_stream_sha256": _sha(raw_events), "start_event_id": start["event_id"], "finish_event_id": finish["event_id"]},
            {"owned_log_sha256": log_sha, "frame_counts": counts}]
        return {"schema": "campaign-known-restart-effects-proof@1",
            **{key: context[key] for key in ("scope", "incident_key", "terminal_cid", "recovery_ordinal", "action_receipt_cid")},
            "restart_owner_token": _digest({key: self.launch.get(key) for key in
                ("identity", "started_at", "repo_root", "state_dir", "plan_id", "worktree_root_binding")}),
            "restart_started_at_ms": int(started * 1000), "progress_observed_at_ms": int(finished * 1000),
            "progress_task_id": start["task_id"], "progress_task_cid": start["canonical_task_cid"],
            "progress_attempt": start["attempt"], "current_owner_token": current_token,
            "evidence_cids": [prompt_workflow_cid(value) for value in evidence],
            "effects_verified": True, "later_work_verified": True}


def reconcile_closed_restart(repo_root, spec_path, state_dir, closed_owner_directory, *, expected_manifest_sha256):
    """Explicit public receipt reconciliation; no process or task effects."""
    from .campaign_watchdog import ComplaintCampaignWatchdog
    watcher = ComplaintCampaignWatchdog(repo_root, spec_path, state_dir)
    from ipfs_accelerate_py.agent_supervisor.rescue.campaign_watchdog import CampaignProgressWatchdog, CampaignProgressWatchdogPolicy
    verifier = ClosedRestartProof(watcher, closed_owner_directory, expected_manifest_sha256=expected_manifest_sha256)
    policy = CampaignProgressWatchdogPolicy(deadline_ms=preserved_native_watchdog_budgets(watcher.runner)["watchdog_action_deadline_ms"])
    def forbidden(_):
        raise RuntimeError("reconciliation_never_dispatches_recovery")
    native = CampaignProgressWatchdog(watcher.directory, repository_root=watcher.root, scope=watcher.scope,
        observe=watcher.observe, recover=forbidden, policy=policy)
    results = []
    for key, entry in verifier.ledger.get("incidents", {}).items():
        if entry.get("phase") != "uncertain" or not entry.get("terminal_cid"):
            continue
        if len(results) >= 2:
            raise ValueError("reconciliation_incident_bound")
        paths = list((watcher.directory / "programmatic-recovery").glob("*.json"))
        if len(paths) > policy.max_incidents * policy.max_recovery_attempts:
            raise ValueError("reconciliation_terminal_bound")
        documents = [json.loads(_read(path)) for path in paths]
        matching = [value for value in documents if value.get("terminal", {}).get("content_id") == entry["terminal_cid"]]
        if len(matching) != 1:
            raise ValueError("reconciliation_terminal_ambiguous")
        terminal = matching[0]["terminal"]
        payload = {"schema": "programmatic-recovery-action-observation@1", "incident_cid": terminal["incident_cid"],
            "operation": "restart_lane", "target_id": watcher.scope["run_cid"], "attempt": 1, "outcome": "failed",
            "observation": {"succeeded": False, "observed_effects": ["old_lane_fenced", "lane_restarted"],
                "post_action_health": {"healthy": False}, "reason": "application_recovery_observed", "partial": True}}
        results.append(native.reconcile_health_pending_restart(incident_key=key,
            expected_terminal_cid=entry["terminal_cid"], action_observation=payload, verify_effects=verifier))
    return {"schema": "complaint-restart-effect-reconciliation@1", "results": results,
        "completion_authority": False, "attempt_refunded": False, "provider_calls": 0}
