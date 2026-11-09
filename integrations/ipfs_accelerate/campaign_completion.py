"""Read-only Native campaign completion, separate from current-source qualification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import improvement_plan as compiler
from . import release_evidence as evidence
from .campaign import campaign_artifacts

SCHEMA = "complaint-campaign-completion-observation@1"
_STATE_FIELDS = ("ready_task_ids", "waiting_task_ids", "active_provider_runner",
                 "implementation_attempts", "implementation_attempts_by_cid",
                 "protected_implementation_attempts")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _state(root: Path, state: Path) -> dict[str, Any]:
    """Use the existing bounded Native read adapter, including board catalogs."""
    import os
    from .improvement_runner import _read_native_state
    previous = Path.cwd()
    try:
        body, locator = _read_native_state(root, state / "complaint_intake_task_state.json", timeout_seconds=10)
    finally:
        os.chdir(previous)
    if body.get("read_error") or locator.get("source") != "native_control_plane":
        raise evidence.ReleaseEvidenceError("native_state_projection_unavailable")
    authority = Path(str(locator.get("authority_path") or ""))
    evidence._readable_database(authority, private_root=state)
    fields = ("completed_task_ids", "assumed_completed_task_ids", "task_identities", "task_statuses",
              "blocked_task_ids", "implementation_in_progress", "active_task_id", *_STATE_FIELDS)
    return {key: body.get(key) for key in fields}


def _queue(root: Path, state: Path, branch: str) -> dict[str, Any]:
    """Use Native completion rules and inspect the same existing store read-only."""
    import duckdb
    from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import checkout_repository_id
    from ipfs_accelerate_py.agent_supervisor.task_sources.duckdb_state import connect_duckdb_with_policy
    bindings = evidence._queue_bindings(root, state, branch)
    path = state / "merge-queue" / "merge_queue.duckdb"
    evidence._readable_database(path, private_root=state)
    connection = connect_duckdb_with_policy(duckdb, path, read_only=True)
    try:
        rows = connection.execute("SELECT request_id,status,metadata_json,claim_generation,updated_at "
                                  "FROM merge_requests ORDER BY request_id").fetchall()
    finally:
        connection.close()
    if len(rows) > 256:
        raise evidence.ReleaseEvidenceError("native_merge_queue_unbounded")
    repository_id = checkout_repository_id(root)
    scoped = []
    for request, status, raw_metadata, generation, updated in rows:
        if len(str(raw_metadata)) > evidence.MAX_METADATA:
            raise evidence.ReleaseEvidenceError("native_merge_metadata_unbounded")
        metadata = evidence._object(str(raw_metadata).encode())
        if (metadata.get("target_repository_id") == repository_id
                and metadata.get("target_branch") == branch):
            scoped.append([request, status, hashlib.sha256(str(raw_metadata).encode()).hexdigest(),
                           generation, updated])
        elif status in {"pending", "processing"} and not metadata.get("target_repository_id"):
            raise evidence.ReleaseEvidenceError("unbound_open_merge_request")
    active = [row[0] for row in scoped if row[1] in {"pending", "processing"}]
    return {"bindings": {key: sorted(value) for key, value in bindings.items()},
            "open_request_ids": active, "snapshot_digest": _digest(scoped),
            "completed_requests": sum(row[1] == "completed" for row in scoped)}


def _latest_terminals(state: Path, pin: dict[str, Any], tasks: dict[str, Any]) -> dict[str, int]:
    """A newer failed finish cannot be hidden by the bridge's success projection."""
    raw = evidence._read(state / "complaint_intake_events.jsonl", maximum=evidence.MAX_JOURNAL, source=True)
    if hashlib.sha256(raw).hexdigest() != pin["prefix_sha256"]:
        raise evidence.ReleaseEvidenceError("completion_snapshot_changed")
    latest = {}
    for line in raw.splitlines():
        row = evidence._object(line)
        task = tasks.get(row.get("task_id"))
        if task is None or row.get("type") != "implementation_finished":
            continue
        primary, alias = row.get("canonical_task_cid"), row.get("task_cid")
        if primary and alias and primary != alias:
            raise evidence.ReleaseEvidenceError("native_finish_identity_conflict")
        if (primary or alias) != task.canonical_task_cid:
            continue
        if type(row.get("returncode")) is not int or row["returncode"] != 0:
            latest[task.task_id] = -int(row["sequence"])
        else:
            latest[task.task_id] = int(row["sequence"])
    return latest


def _source_snapshot(root: Path, spec_file: Path, artifacts) -> dict[str, Any]:
    paths = (spec_file, root / artifacts.plan_relative, root / artifacts.board_relative)
    return {"head": evidence._git(root, "rev-parse", "HEAD"),
            "files": {str(path.relative_to(root)): hashlib.sha256(evidence._read(path, source=True)).hexdigest()
                      for path in paths}}


def _task_completion_observation(root: Path, state: Path, task, native, rows, journal_pin,
                                 latest, *, interrupted_view=None, integration_head=None) -> dict[str, Any]:
    """Keep ordinary finish rules; separately observe a proven interrupted callback."""
    candidates = [row for row in rows if row.get("task_id") == task.task_id
                  and row.get("canonical_task_cid") == task.canonical_task_cid]
    head = integration_head or evidence._git(root, "rev-parse", "HEAD")
    if not candidates:
        if latest.get(task.task_id) is not None or interrupted_view is None:
            raise evidence.ReleaseEvidenceError("native_callback_history_missing")
        from .completed_claim_recovery import observe_interrupted_completion
        try:
            return observe_interrupted_completion(interrupted_view, task_id=task.task_id,
                canonical_task_cid=task.canonical_task_cid, journal_pin=journal_pin, integration_head=head)
        except (ValueError, OSError, RuntimeError) as error:
            raise evidence.ReleaseEvidenceError("interrupted_callback_" + str(error)) from None
    row = candidates[-1]
    if latest.get(task.task_id) != row["sequence"]:
        raise evidence.ReleaseEvidenceError("latest_native_finish_not_successful")
    if row.get("behavioral_evidence_present") and not isinstance(row.get("todo", {}).get("completion_callback_evidence"), dict):
        raise evidence.ReleaseEvidenceError("native_callback_evidence_missing")
    receipt, callback_commit = evidence._callback(row, task, native)
    history = evidence._historical_execution(state, row, task, journal_pin)
    commits = (row.get("implementation_commit"), row.get("merge_commit"), callback_commit)
    if any(evidence._COMMIT.fullmatch(str(commit or "")) is None for commit in commits):
        raise evidence.ReleaseEvidenceError("native_integration_commit_missing")
    for commit in set(commits):
        evidence._git(root, "merge-base", "--is-ancestor", commit, head)
    return {"task_cid": task.canonical_task_cid, "event_id": row["event_id"],
        "event_kind": "implementation_finished", "callback_commit": callback_commit,
        "member_receipt_digest": _digest(receipt), "historical_evidence_digest": _digest(history)}


def verify_campaign_completion(repo_root: Path | str, spec_path: Path | str,
                               state_dir: Path | str) -> dict[str, Any]:
    """Verify existing Native completion without provider, task or recovery effects.

    A successful result establishes historical validation, integration and
    canonical completion callbacks. It does not qualify the checkout's current
    product behavior, optional providers, legal conclusions or replica services.
    """
    result = {"schema": SCHEMA, "verified": False, "reason": "completion_unavailable",
              "completed": 0, "task_count": 0, "completion_authority": False,
              "historical_execution_only": True, "current_source_qualification": False,
              "evidence_digests": {}, "tasks": {}}
    try:
        root = evidence._directory(Path(repo_root))
        state = evidence._directory(Path(state_dir), private=True)
        spec_file = Path(spec_path)
        spec = compiler.validate_spec(evidence._object(evidence._read(spec_file, source=True)))
        artifacts = campaign_artifacts(spec)
        artifacts.validate_source(root, spec_file)
        if spec_file != root / artifacts.spec_relative:
            raise evidence.ReleaseEvidenceError("noncanonical_specification_path")
        native, event_log = evidence._native()
        plan = compiler.build_improvement_work_plan(spec)
        expected_ids = {task["id"] for task in spec["tasks"]}
        result["task_count"] = len(expected_ids)
        if not 0 < len(expected_ids) <= 256:
            raise evidence.ReleaseEvidenceError("campaign_task_population_unbounded")
        stored = evidence._object(evidence._read(root / artifacts.plan_relative, source=True))
        if stored != {**plan.to_dict(), "plan_id": plan.plan_id}:
            raise evidence.ReleaseEvidenceError("formal_plan_contract_mismatch")
        launcher_path = state / "launcher.json"
        launcher_raw = evidence._read(launcher_path)
        launcher = evidence._object(launcher_raw)
        branch = launcher.get("merge_target")
        if (launcher.get("schema_version") != "complaint-improvement-launcher@1"
                or launcher.get("repo_root") != str(root) or launcher.get("state_dir") != str(state)
                or launcher.get("spec_path") != str(spec_file) or launcher.get("plan_id") != plan.plan_id
                or launcher.get("board_path") != str(root / artifacts.board_relative)
                or launcher.get("provider") != "grok_cli" or launcher.get("model") != "grok-4.7"
                or launcher.get("allow_fallback") is not False or not isinstance(branch, str)
                or not branch or evidence._git(root, "symbolic-ref", "--short", "HEAD") != branch.removeprefix("refs/heads/")):
            raise evidence.ReleaseEvidenceError("campaign_launcher_binding_mismatch")
        before = _source_snapshot(root, spec_file, artifacts)
        board_raw = evidence._read(root / artifacts.board_relative, source=True)
        compiler._require_matching_projection(board_raw.decode(), spec, plan.plan_id, root)
        if board_raw.decode().count(f"<!-- plan_id: {plan.plan_id} -->") != 1:
            raise evidence.ReleaseEvidenceError("native_board_plan_binding_mismatch")
        parsed = native.parse_task_text(board_raw.decode(), path=root / artifacts.board_relative,
                                        task_header_prefix="## CIMP-")
        tasks = {task.task_id: task for task in parsed}
        if len(parsed) != len(expected_ids) or set(tasks) != expected_ids:
            raise evidence.ReleaseEvidenceError("native_board_task_set_mismatch")
        projection = _state(root, state)
        result["completed"] = len(projection.get("completed_task_ids") or [])
        if (projection.get("implementation_in_progress") is not False
                or projection.get("active_task_id") or projection.get("active_provider_runner")):
            raise evidence.ReleaseEvidenceError("native_execution_active")
        idle_lists = ("assumed_completed_task_ids", "blocked_task_ids", "ready_task_ids", "waiting_task_ids")
        if any(not isinstance(projection.get(key), list) or projection[key] for key in idle_lists):
            raise evidence.ReleaseEvidenceError("native_campaign_not_terminal")
        completed = projection.get("completed_task_ids")
        identities, statuses = projection.get("task_identities"), projection.get("task_statuses")
        if (not isinstance(completed, list) or len(completed) != len(expected_ids)
                or set(completed) != expected_ids or not isinstance(identities, dict)
                or not isinstance(statuses, dict)):
            raise evidence.ReleaseEvidenceError("native_completed_task_population_mismatch")
        queue = _queue(root, state, branch)
        if queue["open_request_ids"]:
            raise evidence.ReleaseEvidenceError("native_merge_queue_open")
        rows, journal_pin = evidence._journal(state, event_log)
        latest = _latest_terminals(state, journal_pin, tasks)
        interrupted_view = None
        for task_id, task in tasks.items():
            if (task.status != "completed" or statuses.get(task_id) != "completed"
                    or identities.get(task_id, {}).get("canonical_task_cid") != task.canonical_task_cid
                    or task.canonical_task_cid not in queue["bindings"].get(task_id, [])):
                raise evidence.ReleaseEvidenceError("actual_native_revision_completion_missing")
            if (interrupted_view is None and latest.get(task_id) is None
                    and not any(row.get("task_id") == task_id
                        and row.get("canonical_task_cid") == task.canonical_task_cid for row in rows)):
                from .improvement_runner import _recovery_config
                from .completed_claim_recovery import read_only_completion_view
                interrupted_view = read_only_completion_view(_recovery_config(root, state, launcher))
            result["tasks"][task_id] = _task_completion_observation(root, state, task, native,
                rows, journal_pin, latest, interrupted_view=interrupted_view, integration_head=before["head"])
        after = _source_snapshot(root, spec_file, artifacts)
        if (after != before or evidence._read(launcher_path) != launcher_raw
                or _state(root, state) != projection or _queue(root, state, branch) != queue
                or hashlib.sha256(evidence._read(state / "complaint_intake_events.jsonl",
                    maximum=evidence.MAX_JOURNAL, source=True)).hexdigest() != journal_pin["prefix_sha256"]):
            raise evidence.ReleaseEvidenceError("completion_snapshot_changed")
        result.update(verified=True, reason="native_campaign_completion_verified", completed=len(tasks),
            plan_id=plan.plan_id, head=before["head"], evidence_digests={
                "source_contract": _digest(before), "launcher": hashlib.sha256(launcher_raw).hexdigest(),
                "projection": _digest(projection), "queue": queue["snapshot_digest"],
                "journal": journal_pin["prefix_sha256"], "callbacks": _digest(result["tasks"])})
        result["snapshot_digest"] = _digest(result["evidence_digests"])
    except evidence.ReleaseEvidenceError as error:
        result["reason"] = str(error)
    except Exception as error:
        result["reason"] = "completion_evidence_unavailable"
        result["error_type"] = type(error).__name__
    return result
