"""Read-only recognition of a retained failed attempt of a completed task.

This does not merge, retire, clean, complete, or retry a candidate. It only
prevents an authenticated obsolete candidate from blocking the startup pass.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Mapping


def _events(path: Path, maximum: int):
    from .improvement_recovery import _owned_bytes
    raw = _owned_bytes(path, maximum, legacy_group_write=True)
    if not raw.endswith(b"\n"):
        raise ValueError("startup event stream is incomplete")
    rows, previous = [], ""
    for sequence, line in enumerate(raw.splitlines(), 1):
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("startup event is not an object")
        body = {key: value for key, value in event.items() if key != "event_id"}
        expected = "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True,
            ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        if (event.get("sequence") != sequence or event.get("previous_event_id", "") != previous
                or event.get("event_id") != expected):
            raise ValueError("startup event chain differs")
        previous = expected
        rows.append(event)
    return rows


def _worktree_custody(supervisor, daemon, path: Path, branch: str, commit: str) -> bool:
    from .improvement_recovery import _owned_bytes
    common = supervisor._verified_git_worktree_common_dir(path)
    if common is None or common != supervisor._verified_git_worktree_common_dir(supervisor.config.repo_root):
        return False
    result = daemon._run_git(["rev-parse", "--absolute-git-dir"], cwd=path)
    if result.returncode != 0:
        return False
    admin = Path(result.stdout.strip())
    if not admin.is_absolute() or admin.resolve(strict=True) != admin:
        return False
    actual_head = daemon._run_git(["rev-parse", "--verify", "HEAD^{commit}"], cwd=path)
    actual_branch = daemon._run_git(["symbolic-ref", "--quiet", "HEAD"], cwd=path)
    if (actual_head.returncode != 0 or actual_head.stdout.strip() != commit
            or actual_branch.returncode != 0 or actual_branch.stdout.strip() != "refs/heads/" + branch):
        return False
    pointer, backlink = _owned_bytes(path / ".git", 4096, legacy_group_write=True), _owned_bytes(admin / "gitdir", 4096, legacy_group_write=True)
    if len(pointer) > 4096 or len(backlink) > 4096 or not pointer.startswith(b"gitdir: "):
        return False
    target = Path(pointer.decode().strip().removeprefix("gitdir: "))
    target = target if target.is_absolute() else path / target
    return target.resolve(strict=True) == admin and Path(backlink.decode().strip()).resolve(strict=True) == path / ".git"


def _rescue_original(supervisor, daemon, candidate, records, events):
    branch, commit = str(candidate.get("branch") or ""), str(candidate.get("head") or "")
    path = Path(str(candidate.get("path") or ""))
    root = supervisor.config.worktree_root
    if (not branch.startswith("rescue/worktree/") or re.fullmatch(r"[0-9a-f]{40}", commit) is None
            or not path.is_absolute() or path.parent != root or path.resolve(strict=True) != path
            or root.resolve(strict=True) != root or supervisor._git_status_short(path)):
        return None
    matches = [row for row in records if row.get("worktree") == str(path)]
    if (len(matches) != 1 or str(matches[0].get("branch") or "").removeprefix("refs/heads/") != branch
            or matches[0].get("HEAD") != commit or not _worktree_custody(supervisor, daemon, path, branch, commit)):
        return None
    raw = daemon._run_git(["cat-file", "commit", commit], cwd=path)
    if raw.returncode != 0 or len(raw.stdout.encode()) > 65536:
        return None
    header, separator, body = raw.stdout.partition("\n\n")
    parents = [line[7:] for line in header.splitlines() if line.startswith("parent ")]
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if (not separator or len(parents) != 1 or len(lines) != 4
            or not all(any(line.startswith(kind + " ") and " <implementation-supervisor@example.invalid> " in line
                for line in header.splitlines()) for kind in ("author", "committer"))
            or not lines[1].startswith("Original branch: ")
            or lines[2] != "Original HEAD: " + parents[0]
            or lines[3] not in {"Cleanup reason: stale_active_execution_auto_rescue",
                "Cleanup reason: reconciliation_uncommitted_integrated_base"}):
        return None
    original = lines[1].removeprefix("Original branch: ")
    if not original.startswith("implementation/") or lines[0] != "Rescue dirty worktree " + original:
        return None
    proof = [event for event in events if event.get("type") == "dirty_worktree_rescued"
        and event.get("preserved") is True and type(event.get("returncode")) is int
        and event["returncode"] == 0 and event.get("path") == str(path)
        and event.get("target_ref") == supervisor.config.merge_target_branch
        and event.get("branch") == original and event.get("head") == parents[0]
        and event.get("rescue_branch") == branch and event.get("rescue_commit") == commit]
    return (original, parents[0]) if len(proof) == 1 else None


def _integrated_winner(supervisor, event, task_id, binding):
    merge = event.get("merge_result")
    validation = event.get("validation_result")
    if (not isinstance(merge, Mapping) or not isinstance(validation, Mapping)
            or validation.get("passed") is not True or type(validation.get("returncode")) is not int
            or validation["returncode"] != 0 or merge.get("merged") is not True
            or merge.get("attempted") is not True or type(merge.get("returncode")) is not int
            or merge["returncode"] != 0 or merge.get("target_branch") != supervisor.config.merge_target_branch
            or merge.get("completion_task_cids") != {task_id: binding["canonical_task_cid"]}
            or any(merge.get(key) != value for key, value in binding.items() if key != "board_namespace")):
        return False
    proof = merge.get("integration_commit_proof")
    if not isinstance(proof, Mapping) or proof.get("passed") is not True or proof.get("exact_two_parent_merge") is not True:
        return False
    winner, integrated, base = event.get("implementation_commit"), merge.get("merge_commit"), merge.get("integration_base_commit")
    if (any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None for value in (winner, integrated, base))
            or merge.get("implementation_commit") != winner or proof.get("implementation_commit") != winner
            or proof.get("integration_commit") != integrated or proof.get("integration_ref") != integrated
            or proof.get("integration_base_commit") != base
            or proof.get("target_branch") != supervisor.config.merge_target_branch
            or supervisor._git_commit_parents(supervisor.config.repo_root, integrated) != [base, winner]
            or not supervisor._git_ref_is_ancestor(supervisor.config.repo_root, integrated, "HEAD")):
        return False
    return True


def completed_preflight_conflict(supervisor, candidate) -> bool:
    """Reprove current Native completion; never use a branch-name task parser."""
    if str(candidate.get("branch") or "").startswith("implementation/"):
        from .startup_completed_replay_candidate import completed_replay_conflict
        return completed_replay_conflict(supervisor, candidate)
    from . import improvement_runner as runner
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
    try:
        config = supervisor.config
        merge, preflight = candidate.get("merge_result"), candidate.get("preflight_result")
        branch = str(candidate.get("branch") or "").removeprefix("refs/heads/")
        if (not isinstance(merge, Mapping) or not isinstance(preflight, Mapping)
                or candidate.get("merged") is not False or merge.get("attempted") is not False
                or merge.get("merged") is not False or merge.get("reason") != "preflight_merge_conflict"
                or preflight.get("reason") != "preflight_merge_conflict"
                or preflight.get("attempted") is not True or preflight.get("mergeable") is not False
                or type(preflight.get("returncode")) is not int or preflight["returncode"] != 1
                or any(row.get("branch") != branch or row.get("target_ref") != config.merge_target_branch
                    for row in (candidate, merge, preflight))):
            return False
        # Native's normal constructor is implementation-disabled. Do not call
        # _reconciliation_task_context: it registers/saves the CID queue.
        context = getattr(supervisor, "_complaint_startup_reconciliation_context", None)
        daemon = context.get("daemon") if isinstance(context, Mapping) else None
        if daemon is None:
            from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor import PortalImplementationSupervisor
            # A read-only status check needs Native's canonical disabled
            # constructor, not the Host's measured validation adapter.
            daemon = PortalImplementationSupervisor._build_worktree_reconciliation_daemon(supervisor)
        if not isinstance(daemon, PortalImplementationDaemon) or daemon.implement is not False:
            return False
        native_events = _events(config.state_dir / f"{config.state_prefix}_events.jsonl", runner.MAX_EVENT_HISTORY_BYTES)
        rescue_events = _events(config.events_path, runner.MAX_EVENT_HISTORY_BYTES)
        records = supervisor._git_worktree_records(config.repo_root)
        if len(records) > 256:
            return False
        attested = _rescue_original(supervisor, daemon, candidate, records, rescue_events)
        if attested is None:
            return False
        original, baseline = attested
        starts = [event for event in native_events if event.get("type") == "implementation_started"
            and event.get("branch") == original and event.get("baseline_ref") == baseline]
        if len(starts) != 1:
            return False
        started = starts[0]
        task_id = started.get("task_id")
        tasks = [task for task in daemon._load_tasks() if task.task_id == task_id]
        if len(tasks) != 1:
            return False
        task = tasks[0]
        identity = daemon._identity_for_task(task)
        binding = {"canonical_task_cid": identity.canonical_task_cid,
            "canonical_task_key": identity.canonical_task_key, "board_namespace": identity.board_namespace}
        if (not all(binding.values()) or any(started.get(key) != value for key, value in binding.items())
                or type(started.get("attempt")) is not int or started["attempt"] < 1):
            return False
        completed = [event for event in native_events if event.get("type") == "implementation_finished"
            and event.get("task_id") == task_id and all(event.get(key) == value for key, value in binding.items())
            and event["sequence"] > started["sequence"]
            and type(event.get("attempt")) is int and event["attempt"] > started["attempt"]
            and type(event.get("returncode")) is int and event["returncode"] == 0
            and _integrated_winner(supervisor, event, task_id, binding)]
        if not completed or PortalImplementationDaemon._completed_task_binding_error(daemon,
                {"task": {"task_id": task_id}, "completion_task_cids": {task_id: identity.canonical_task_cid}}):
            return False
        # Re-read the custody chain and current board immediately before the
        # nonblocking classification; no result, ref, cache, or state is edited.
        return (_rescue_original(supervisor, daemon, candidate,
                    supervisor._git_worktree_records(config.repo_root),
                    _events(config.events_path, runner.MAX_EVENT_HISTORY_BYTES)) == attested
            and not PortalImplementationDaemon._completed_task_binding_error(daemon,
                {"task": {"task_id": task_id}, "completion_task_cids": {task_id: identity.canonical_task_cid}}))
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return False
