#!/usr/bin/env python3
"""Run the native campaign, or observe existing owned live progress safely."""

from pathlib import Path
import argparse
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import integrations.ipfs_accelerate.improvement_runner as runner


PROFILE_FLAGS = {
    "--implementation-timeout": "900", "--implementation-max-timeout": "900",
    "--implementation-log-stall-seconds": "180", "--max-task-attempts": "3",
    "--max-restarts": "5", "--validation-max-workers": "1",
    "--task-shard-count": "1", "--task-shard-index": "0",
}


def _observation(value):
    """Select closed metadata; never serialize public status's raw log tails."""
    state = value.get("native_state") or {}
    heartbeat = value.get("native_heartbeat") or {}
    evidence = value.get("provider_execution_evidence") or {}
    birth = runner.process_identity(value.get("pid")) if value.get("owned_process_alive") else None
    daemon = runner.process_identity(heartbeat.get("daemon_pid")) if birth and heartbeat.get("daemon_pid") else None
    return {
        "status": value.get("status"), "healthy": value.get("healthy") is True,
        "owned": value.get("owned_process_alive") is True,
        "owner": {key: (birth or {}).get(key) for key in ("pid", "start_ticks", "boot_id")},
        "daemon_pid": heartbeat.get("daemon_pid"),
        "daemon_birth": {key: (daemon or {}).get(key) for key in ("pid", "start_ticks", "boot_id", "ppid")},
        "heartbeat": heartbeat.get("updated_at"),
        "provider": value.get("provider"), "model": value.get("model"),
        "allow_fallback": value.get("allow_fallback"),
        "task": {key: state.get(key) for key in (
            "active_task_id", "active_task_cid", "active_attempt", "active_task_started_at",
            "active_worktree_path", "active_log_path")},
        "application_interview_state": value.get("application_interview_state"),
        "provider_progress": value.get("provider_progress_verified") is True,
        "log_bytes": evidence.get("log_bytes"),
        "usage": (evidence.get("frame_counts") or {}).get("usage", 0),
        "tools": sum((evidence.get("frame_counts") or {}).get(key, 0)
                     for key in ("tool_call", "tool_call_update")),
    }


def _active(value):
    task, owner, daemon = value["task"], value["owner"], value["daemon_birth"]
    return bool(value["status"] == "active" and value["healthy"] and value["owned"]
        and value["provider_progress"] and value["provider"] == "grok_cli"
        and value["model"] == "grok-4.7" and value["allow_fallback"] is False
        and type(owner["pid"]) is int and owner["pid"] > 1
        and type(owner["start_ticks"]) is int and owner["start_ticks"] > 0 and owner["boot_id"]
        and type(value["daemon_pid"]) is int and value["daemon_pid"] > 1
        and daemon["pid"] == value["daemon_pid"] and daemon["pid"] != owner["pid"]
        and daemon["ppid"] == owner["pid"]
        and type(daemon["start_ticks"]) is int and daemon["start_ticks"] > 0 and daemon["boot_id"]
        and task["active_task_id"] and task["active_task_cid"]
        and type(task["active_attempt"]) is int and task["active_attempt"] > 0
        and all(task[key] for key in ("active_task_started_at", "active_worktree_path", "active_log_path"))
        and type(value["log_bytes"]) is int and value["log_bytes"] > 0
        and type(value["usage"]) is int and value["usage"] > 0
        and type(value["tools"]) is int and value["tools"] > 0 and value["heartbeat"])


def observe_live_profile(repo_root, spec_path, state_dir, *, observation_seconds=45):
    """Observe an existing campaign. This never starts, faults or recovers one.

    Configured options are distinct from actual process-profile attestations.
    Native completion, stop/resume and the real process-failure fixture are
    separately measured obligations, not inferred from these observations.
    """
    result = {"schema": "complaint-improvement-live-profile@1",
        "status": "live_evidence_unavailable", "completion_authority": False,
        "live_acceptance_complete": False, "execution_started": False,
        "failure_injected": False, "state_dir": str(state_dir),
        "commands": {command: [sys.executable, str(Path(__file__).resolve()), command,
            "--repo-root", str(repo_root), "--spec", str(spec_path), "--state-dir", str(state_dir)]
            for command in ("status", "stop", "start", "recover")},
        "resume_uses_same_epoch_start": True,
        "limits": ["Current public health and owned progress only; actual process-profile, native validated-output/callback, same-epoch stop/start and separately measured zero-paid process/lease recovery evidence remain required."]}
    try:
        if not 5 <= observation_seconds <= 45:
            raise ValueError("bounded_observation_required")
        doctor = runner.doctor(repo_root, spec_path, state_dir)
        argv = doctor.get("native_argv") or []
        configured = {flag: argv[argv.index(flag) + 1] if argv.count(flag) == 1
                      and argv.index(flag) + 1 < len(argv) else None for flag in PROFILE_FLAGS}
        result["configured_profile"] = configured
        if (doctor.get("status") != "ready" or configured != PROFILE_FLAGS
                or doctor.get("provider") != "grok_cli" or doctor.get("model") != "grok-4.7"
                or doctor.get("allow_fallback") is not False):
            result["reason"] = "configured_profile_unavailable"
            return result
        first = _observation(runner.status(repo_root, spec_path, state_dir))
        result["observations"] = [first]
        if not _active(first):
            result["reason"] = "owned_active_progress_unavailable"
            return result
        started = time.monotonic()
        while time.monotonic() - started < observation_seconds:
            time.sleep(1)
            second = _observation(runner.status(repo_root, spec_path, state_dir))
            if not _active(second) or any(first[key] != second[key] for key in ("owner", "daemon_pid", "daemon_birth", "task")):
                result["reason"] = "current_owner_or_attempt_changed"
                return result
            if (time.monotonic() - started >= 5 and second["heartbeat"] != first["heartbeat"]
                    and second["log_bytes"] > first["log_bytes"]
                    and second["usage"] >= first["usage"] and second["tools"] > first["tools"]):
                result.update(status="live_progress_observed", reason="two_owned_heartbeat_cycles",
                              observations=[first, second], observation_seconds=time.monotonic() - started)
                return result
        result["reason"] = "second_owned_progress_cycle_unavailable"
    except (OSError, ValueError, RuntimeError, TypeError, KeyError, IndexError, AttributeError):
        result["reason"] = "public_observation_unavailable"
    return result


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "live-profile":
        # Preserve actual start/status/recover/stop and their ownership checks.
        # Resume is public start with the same explicit epoch, not a new verb.
        return runner.main(argv)
    parser = argparse.ArgumentParser(description="Read-only existing owned campaign progress; no lifecycle actions.")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--observation-seconds", type=int, default=45)
    args = parser.parse_args(argv[1:])
    root = args.repo_root.resolve()
    result = observe_live_profile(root, (args.spec or root / runner.SPEC_RELATIVE).resolve(),
                                  args.state_dir.resolve(), observation_seconds=args.observation_seconds)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "live_progress_observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
