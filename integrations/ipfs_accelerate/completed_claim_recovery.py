"""Retire an exact dead legacy claim after Native's durable completion callback.

The caller retains launcher, checkout and settled-queue guards and supplies its
existing process/container closure reproof. This grants no completion, attempt,
selection, merge or lifecycle authority. The Portal state projection is read
without saving; its pre-callback status may legitimately remain stale.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Callable, Mapping

from . import release_evidence as evidence

SCHEMA = "complaint-completed-claim-retirement@1"


def _legacy_config(config):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor import PortalSupervisorConfig
    from ipfs_accelerate_py.agent_supervisor.runtime.multi_supervisor_runner import (
        DatabaseProgramConfig, AUTHORITY_MODE_LEGACY_MARKDOWN,
        TASK_SOURCE_LEGACY_MARKDOWN, TASK_SOURCE_MARKDOWN)
    if type(config) is not PortalSupervisorConfig:
        return False
    program = config.database_program
    if program is None:
        return True
    return (type(program) is DatabaseProgramConfig
        and program.authority_mode == AUTHORITY_MODE_LEGACY_MARKDOWN
        and program.task_source_kind in {TASK_SOURCE_LEGACY_MARKDOWN, TASK_SOURCE_MARKDOWN}
        and program.explicit_legacy is True
        and not native.is_database_authority_mode(authority_mode=program.authority_mode,
                                                 task_source_kind=program.task_source_kind))


def completed_claim_daemon(config, *, merge_queue):
    """Use Native's actual reconciliation constructor and existing queue.

    In 6af the Native builder deliberately omits board_namespace. Markdown
    canonical identity therefore retains the source filename namespace.
    """
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.merge.merge_queue import MergeQueue
    _require(_legacy_config(config) and isinstance(merge_queue, MergeQueue)
        and Path(merge_queue.queue_dir) == Path(config.merge_queue_dir), "completed_claim_config_required")
    return native.PortalImplementationDaemon(
        todo_path=config.todo_path, state_path=config.state_path, strategy_path=config.strategy_path,
        events_path=Path(config.state_dir) / f"{config.state_prefix}_events.jsonl", repo_root=config.repo_root,
        task_header_prefix=config.task_prefix, implement=False,
        implementation_command=config.implementation_command, implementation_timeout=config.implementation_timeout,
        max_task_attempts=config.max_task_attempts, use_ephemeral_worktree=False,
        worktree_root=config.worktree_root, merge_target_branch=config.merge_target_branch,
        merge_queue_dir=config.merge_queue_dir, merge_queue=merge_queue,
        worktree_submodule_paths=config.worktree_submodule_paths,
        implementation_protected_paths=config.implementation_protected_paths,
        objective_path=config.objective_path, objective_bundle_dir=config.objective_bundle_dir,
        generated_status_paths=config.generated_dirty_repair_paths,
        llm_merge_resolver_command=config.llm_merge_resolver_command,
        llm_merge_resolver_timeout_seconds=config.llm_merge_resolver_timeout_seconds,
        task_shard_count=config.task_shard_count, task_shard_index=config.task_shard_index,
        strict_task_sharding=config.strict_task_sharding)


def read_only_completion_view(config):
    """Allocate the genuine Native type without constructor/catalog effects.

    Only read-only owner methods are used: _load_tasks and _identity_for_task
    parse/hash the actual Markdown source; the scope validator is static; the
    durable-callback predicate only reads the protected-path configuration.
    No instance methods, source classes, guards or queues are replaced.
    """
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import checkout_repository_id
    _require(_legacy_config(config),
             "completed_claim_legacy_config_required")
    view = object.__new__(native.PortalImplementationDaemon)
    view.repo_root, view.todo_path = Path(config.repo_root), Path(config.todo_path)
    view.state_path = Path(config.state_path)
    view.events_path = Path(config.state_dir) / f"{config.state_prefix}_events.jsonl"
    view.task_source, view.task_header_prefix, view.implement = None, config.task_prefix, False
    view.merge_target_branch = config.merge_target_branch
    view.merge_target_repository_id = checkout_repository_id(view.repo_root)
    view.merge_queue_dir = Path(config.merge_queue_dir)
    view.implementation_protected_paths = tuple(config.implementation_protected_paths)
    view._complaint_read_only_completion_view = True
    return view


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _file(path):
    # Legacy Native publishes these owned records under umask 002 (actual
    # retained claims may be 0775). This narrowly retains its no-world-write
    # compatibility; it is not source or completion authority.
    raw = evidence._read(path, maximum=64 * 1024, source=True)
    info = path.lstat()
    identity = tuple(getattr(info, key) for key in
        ("st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"))
    return evidence._object(raw), identity, hashlib.sha256(raw).hexdigest()


def _dead(metadata):
    from ipfs_accelerate_py.agent_supervisor.merge.worktree_lifecycle import (
        ProcessBirthIdentity, read_process_birth, owner_liveness, OwnerLiveness)
    birth = metadata.get("owner_process_birth")
    _require(isinstance(birth, Mapping), "completed_claim_birth_missing")
    owner = ProcessBirthIdentity.from_dict(birth)
    _require(type(metadata.get("pid")) is int and owner.pid == metadata["pid"]
        and owner.pid > 0 and owner.start_time_ticks > 0 and bool(owner.boot_id),
        "completed_claim_birth_invalid")
    # Native's DEAD includes PID reuse. This exception additionally refuses
    # a currently occupied PID, even when its birth differs from the old owner.
    _require(read_process_birth(owner.pid) is None
        and owner_liveness(owner) is OwnerLiveness.DEAD, "completed_claim_owner_not_dead")


def _journal(daemon):
    from ipfs_accelerate_py.agent_supervisor.runtime import event_log
    path = Path(daemon.events_path)
    raw = evidence._read(path, maximum=evidence.MAX_JOURNAL, source=True)
    _require(raw.endswith(b"\n"), "completed_claim_journal_incomplete")
    stream, snapshot = event_log._event_stream_binding(path)
    previous, rows = "", []
    for index, line in enumerate(raw.splitlines(), 1):
        _require(index <= evidence.MAX_EVENTS and len(line) <= evidence.MAX_METADATA,
                 "completed_claim_journal_unbounded")
        value = evidence._object(line)
        _require(value.get("sequence") == index and type(value.get("sequence")) is int
            and value.get("previous_event_id", "") == previous
            and value.get("stream_id") == stream and value.get("snapshot_id") == snapshot
            and value.get("event_id") == event_log._event_identity(value),
            "completed_claim_journal_invalid")
        previous = value["event_id"]
        rows.append(value)
    return rows, hashlib.sha256(raw).hexdigest()


def _one(rows, predicate, reason):
    found = [row for row in rows if predicate(row)]
    _require(len(found) == 1, reason)
    return found[0]


def _queue(daemon, request_id, task_id, cid):
    import duckdb
    from ipfs_accelerate_py.agent_supervisor.task_sources.duckdb_state import connect_duckdb_with_policy
    database = Path(daemon.merge_queue_dir) / "merge_queue.duckdb"
    evidence._readable_database(database, private_root=Path(daemon.state_path).parent)
    connection = connect_duckdb_with_policy(duckdb, database, read_only=True)
    try:
        rows = connection.execute("SELECT status,task_id,canonical_task_id,canonical_task_key,metadata_json "
            "FROM merge_requests WHERE request_id=?", [request_id]).fetchall()
    finally:
        connection.close()
    _require(len(rows) == 1, "completed_claim_queue_request_missing")
    status, display, canonical, key, raw = rows[0]
    _require(status == "completed" and display == task_id and canonical == cid
        and isinstance(raw, str) and len(raw) <= evidence.MAX_METADATA,
        "completed_claim_queue_not_completed")
    return evidence._object(raw.encode()), key, hashlib.sha256(raw.encode()).hexdigest()


def completed_callback_proof(daemon, *, task_id, canonical_task_cid, attempt, workspace, branch):
    """Authenticate an interrupted finish without claim, lane or status writes.

    Caller locators only select history. The current Native task source, exact
    completed queue, native member receipt and real Git ancestry supply proof.
    Other tasks may have executed since this callback.
    """
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    _require(isinstance(daemon, native.PortalImplementationDaemon) and daemon.implement is False
        and daemon.task_source is None, "completed_claim_legacy_daemon_required")
    root = Path(daemon.repo_root)
    evidence._directory(root)
    task = _one(daemon._load_tasks(), lambda row: row.task_id == task_id,
                "completed_claim_task_not_unique")
    identity = daemon._identity_for_task(task)
    cid = canonical_task_cid
    binding = {"canonical_task_cid": cid, "canonical_task_key": identity.canonical_task_key,
               "board_namespace": identity.board_namespace}
    _require(native.normalize_status(task.status) == "completed"
        and identity.canonical_task_cid == cid, "completed_claim_current_task_not_completed")
    _require(type(attempt) is int and attempt > 0 and isinstance(workspace, str)
        and Path(workspace).is_absolute() and isinstance(branch, str) and bool(branch),
        "completed_claim_history_locator_invalid")
    rows, journal_sha = _journal(daemon)
    def bound(row):
        return row.get("task_id") == task_id and all(row.get(k) == v for k, v in binding.items())
    start = _one(rows, lambda row: row.get("type") == "implementation_started" and bound(row)
        and row.get("attempt") == attempt and row.get("branch") == branch
        and row.get("worktree_path") == workspace, "completed_claim_start_missing")
    segment = [row for row in rows if row["sequence"] > start["sequence"]]
    for row in segment:
        if row.get("task_id") == task_id:
            _require(all(k not in row or row[k] in (None, "") or row[k] == v
                for k, v in {**binding, "task_cid": cid}.items()),
                "completed_claim_history_identity_conflict")
    _require(not any(row.get("type") == "implementation_started" and row.get("task_id") == task_id for row in segment),
             "completed_claim_newer_execution")
    accepted = _one(segment, lambda row: row.get("type") == "implementation_proposal_validated"
        and bound(row) and row.get("accepted") is True, "completed_claim_proposal_missing")
    handoff = _one(segment, lambda row: row.get("type") == "implementation_candidate_handoff_verified"
        and bound(row) and row.get("attempt") == attempt and row.get("allowed") is True
        and bool(row.get("implementation_commit")), "completed_claim_handoff_missing")
    candidate = handoff["implementation_commit"]
    enqueue = _one(segment, lambda row: row.get("type") == "merge_candidate_enqueued"
        and bound(row) and row.get("attempt") == attempt and row.get("branch") == branch
        and row.get("implementation_commit") == candidate, "completed_claim_enqueue_missing")
    target = daemon.merge_target_branch
    _require(isinstance(target, str) and bool(target), "completed_claim_target_missing")
    target_commit = evidence._git(root, "rev-parse", "--verify", target + "^{commit}")
    metadata, queue_key, queue_sha = _queue(daemon, enqueue.get("request_id"), task_id, cid)
    _require(queue_key == binding["canonical_task_key"]
        and metadata.get("schema") == "ipfs_accelerate_py/agent-supervisor/merge-candidate@3"
        and metadata.get("completion_task_cids") == {task_id: cid}
        and metadata.get("target_repository_id") == daemon.merge_target_repository_id
        and metadata.get("target_branch") == target and metadata.get("repo_root") == str(root)
        and metadata.get("todo_path") == str(daemon.todo_path)
        and metadata.get("state_path") == str(daemon.state_path)
        and metadata.get("events_path") == str(daemon.events_path)
        and metadata.get("implementation_commit") == candidate
        and metadata.get("baseline_ref") == start.get("baseline_ref")
        and metadata.get("task", {}).get("task_id") == task_id,
        "completed_claim_queue_binding_mismatch")
    validation = metadata.get("validation_proof")
    _require(isinstance(validation, dict) and validation.get("passed") is True
        and type(validation.get("returncode")) is int and validation["returncode"] == 0
        and validation.get("selection", {}).get("scope") == "pre_merge"
        and not daemon._scope_adjudication_merge_binding_error(validation),
        "completed_claim_validation_unverified")
    gate = validation.get("proposal_gate")
    if isinstance(gate, dict):
        _require(gate.get("accepted") is True
            and gate.get("proposal_id") == accepted.get("proposal_id")
            and gate.get("repository_tree_id") == accepted.get("repository_tree_id")
            and gate.get("repository_tree_id") == start.get("baseline_ref"),
            "completed_claim_proposal_queue_mismatch")
    merged = _one(segment, lambda row: row.get("type") == "merge_finished"
        and row.get("branch") == branch and row.get("target_branch") == target
        and row.get("merged") is True and row.get("attempted") is True
        and type(row.get("returncode")) is int and row["returncode"] == 0,
        "completed_claim_merge_missing")
    merge_commit, base = merged.get("merge_commit"), merged.get("integration_base_commit")
    _require(all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{40}", v)
        for v in (candidate, merge_commit, base)), "completed_claim_commit_invalid")
    _require(evidence._git(root, "show", "--format=%P", "--no-patch", merge_commit).split() == [base, candidate],
             "completed_claim_integration_not_two_parent")
    evidence._git(root, "merge-base", "--is-ancestor", merge_commit, target_commit)
    cleanup = _one(segment, lambda row: row.get("type") == "cleanup_finished"
        and row.get("branch") == branch and row.get("cleaned") is True
        and row.get("deleted_branch") is True, "completed_claim_cleanup_missing")
    pooled = _one(segment, lambda row: row.get("type") == "worktree_pool_lease_released"
        and row.get("branch") == branch and row.get("worktree_path") == workspace
        and row.get("released") is True and row.get("reason") == "clean_prepared_workspace",
        "completed_claim_pool_release_missing")
    todo = _one(segment, lambda row: row.get("type") == "todo_status_updated" and bound(row)
        and row.get("updated_task_ids") == [task_id] and row.get("durable") is True
        and daemon._todo_completion_is_durable(row), "completed_claim_callback_missing")
    receipt = {"schema": native.MEMBER_COMPLETION_RECEIPT_SCHEMA, "task_id": task_id,
               **binding, "status": "succeeded"}
    _require(todo.get("completion_receipts") == [receipt]
        and not todo.get("missing_task_ids") and not todo.get("missing_status_task_ids"),
        "completed_claim_member_receipt_mismatch")
    committed = todo.get("commit_result")
    _require(isinstance(committed, dict) and committed.get("committed") is True
        and native.PortalImplementationDaemon._generated_file_commit_result_trusted(committed)
        and committed.get("repo") == str(root)
        and committed.get("path") == str(Path(daemon.todo_path).relative_to(root)),
        "completed_claim_callback_commit_missing")
    callback_commit = committed.get("commit")
    _require(isinstance(callback_commit, str) and re.fullmatch(r"[0-9a-f]{40}", callback_commit),
             "completed_claim_callback_commit_invalid")
    evidence._git(root, "merge-base", "--is-ancestor", merge_commit, callback_commit)
    evidence._git(root, "merge-base", "--is-ancestor", callback_commit, target_commit)
    finishes = [row for row in segment if row.get("type") == "implementation_finished"
                and row.get("task_id") == task_id]
    for finish in finishes:
        _require(all(not finish.get(k) or finish[k] == v for k, v in binding.items())
            and (finish.get("canonical_task_cid") or finish.get("task_cid")) == cid
            and (not finish.get("task_cid") or finish["task_cid"] == cid)
            and type(finish.get("returncode")) is int and finish["returncode"] == 0
            and finish.get("implementation_commit") == candidate
            and isinstance(finish.get("validation_result"), dict)
            and finish["validation_result"].get("passed") is True
            and isinstance(finish.get("merge_result"), dict)
            and (finish["merge_result"].get("merged") is True
                 or finish["merge_result"].get("already_merged") is True)
            and finish["merge_result"].get("merge_commit") == merge_commit,
            "completed_claim_finish_conflict")
    _require(start["sequence"] < accepted["sequence"] < handoff["sequence"]
        < pooled["sequence"] < enqueue["sequence"] < merged["sequence"]
        < cleanup["sequence"] < todo["sequence"], "completed_claim_event_order")
    return {"schema": SCHEMA, "task_id": task_id, **binding, "attempt": attempt,
        "workspace": workspace, "branch": branch, "task_source": "native_markdown",
        "source_status": "completed",
        "task_source_sha256": hashlib.sha256(evidence._read(Path(daemon.todo_path), source=True)).hexdigest(),
        "journal_sha256": journal_sha, "request_id": enqueue["request_id"],
        "queue_metadata_sha256": queue_sha, "merge_commit": merge_commit,
        "callback_commit": callback_commit, "target_commit": target_commit,
        "event_ids": [row["event_id"] for row in
        (start, accepted, handoff, pooled, enqueue, merged, cleanup, todo)],
        "callback_event_id": todo["event_id"], "callback_sequence": todo["sequence"],
        "member_receipt": receipt, "finish_event_ids": [row["event_id"] for row in finishes],
        "validation_proof": validation, "repo_root": str(root),
        "baseline_ref": start.get("baseline_ref"), "implementation_commit": candidate,
        "proposal_id": accepted.get("proposal_id")}


def review_completed_claim(daemon):
    """Read-only proof; source, queue, journal, CP and exact claim are re-read."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.portal_task_state_control_plane import read_task_state_payload
    _require(isinstance(daemon, native.PortalImplementationDaemon) and daemon.implement is False
        and daemon.task_source is None, "completed_claim_legacy_daemon_required")
    root, state_dir = Path(daemon.repo_root), Path(daemon.state_path).parent
    evidence._directory(root)
    evidence._directory(state_dir, private=True)
    state = read_task_state_payload(daemon.state_path)
    _require(isinstance(state, dict), "completed_claim_native_state_unavailable")
    idle = ("active_task_id", "active_task_cid", "active_attempt", "active_worktree_path",
            "active_branch", "active_provider_runner", "protected_implementation_attempts")
    _require(state.get("implementation_in_progress") is False and not any(state.get(k) for k in idle),
             "completed_claim_lane_not_quiesced")
    task_id, cid = state.get("last_implementation_task_id"), state.get("last_implementation_task_cid")
    _require(isinstance(task_id, str) and bool(task_id) and isinstance(cid, str) and bool(cid),
             "completed_claim_task_unbound")
    task = _one(daemon._load_tasks(), lambda row: row.task_id == task_id,
                "completed_claim_task_not_unique")
    identity = daemon._identity_for_task(task)
    binding = {"canonical_task_cid": cid, "canonical_task_key": identity.canonical_task_key,
               "board_namespace": identity.board_namespace}
    _require(native.normalize_status(task.status) == "completed"
        and identity.canonical_task_cid == cid, "completed_claim_current_task_not_completed")
    projected = (state.get("task_identities") or {}).get(task_id)
    _require(isinstance(projected, dict) and all(projected.get(k) == v for k, v in binding.items()),
             "completed_claim_state_identity_mismatch")
    path = daemon._implementation_task_claim_path(task_id, canonical_task_cid=cid)
    claim, file_identity, claim_sha = _file(path)
    attempt = claim.get("attempt")
    _require(type(attempt) is int and 1 <= attempt <= daemon.max_task_attempts
        and (state.get("implementation_attempts") or {}).get(task_id) == attempt
        and (state.get("implementation_attempts_by_cid") or {}).get(cid) == attempt,
        "completed_claim_attempt_mismatch")
    expected = {**binding, "task_id": task_id, "kind": native.IMPLEMENTATION_TASK_CLAIM_LOCK_KIND,
        "state_dir": str(state_dir.resolve()), "state_path": str(Path(daemon.state_path).resolve()),
        "repository_id": daemon.merge_target_repository_id, "worktree_root": str(root.resolve()),
        "task_shard_count": daemon.task_shard_count, "task_shard_index": daemon.task_shard_index,
        "started_at": state.get("last_implementation_started_at")}
    _require(all(claim.get(k) == v for k, v in expected.items()) and bool(claim.get("lease_id")),
             "completed_claim_scope_mismatch")
    _dead(claim)
    _require(not native.implementation_task_claim_protected_fence_paths(claim),
             "completed_claim_protected_fence")
    workspace, branch = state.get("last_implementation_worktree_path"), state.get("last_implementation_branch")
    _require(isinstance(workspace, str) and Path(workspace).is_absolute() and isinstance(branch, str)
        and bool(branch), "completed_claim_workspace_unbound")
    lifecycle = daemon.worktree_lifecycle
    index_attempt = daemon._worktree_lifecycle_attempt_for_identity(task_id=task_id,
        canonical_task_cid=cid, portal_attempt=attempt)
    life_paths = [lifecycle.workspace_path_for(Path(workspace)),
                  lifecycle.task_index_path_for(canonical_task_cid=cid, task_id=task_id, attempt=index_attempt)]
    _require(not any(os.path.lexists(p) for p in life_paths), "completed_claim_lifecycle_not_absent")
    history = completed_callback_proof(daemon, task_id=task_id,
        canonical_task_cid=cid, attempt=attempt, workspace=workspace, branch=branch)
    lock_path = daemon._implementation_lock_path()
    lease = None
    if os.path.lexists(lock_path):
        value, inode, sha = _file(lock_path)
        # Actual 6af implementation leases predate birth/repository fields.
        # Join that exact producer schema to the fully proved task claim;
        # never invent a birth field or accept a current merge/foreign lease.
        legacy_fields = {"kind", "lease_id", "pid", "owner_script", "repo_root", "state_dir",
            "task_id", "canonical_task_key", "canonical_task_cid", "board_namespace", "attempt", "started_at"}
        _require(set(value) == legacy_fields and value.get("kind") == "implementation"
            and type(value.get("pid")) is int and type(value.get("attempt")) is int
            and isinstance(value.get("lease_id"), str) and 0 < len(value["lease_id"]) <= 256
            and value.get("repo_root") == str(root.resolve())
            and all(value.get(k) == claim.get(k) for k in
                ("task_id", "canonical_task_cid", "canonical_task_key", "board_namespace",
                 "attempt", "pid", "owner_script", "state_dir", "started_at")),
            "completed_claim_implementation_lease_mismatch")
        _dead(claim)
        lease = {"path": str(lock_path), "metadata": value, "identity": inode, "sha256": sha}
    return {**history, "portal_projection_status": (state.get("task_statuses") or {}).get(task_id),
        "native_payload": state, "native_sha256": _digest(state),
        "claim_path": str(path), "claim": claim, "claim_identity": file_identity,
        "claim_sha256": claim_sha, "implementation_lease": lease}


def observe_interrupted_completion(daemon, *, task_id, canonical_task_cid, journal_pin, integration_head=None):
    """Read historical completion after a real callback interrupted its finish.

    There must be no finish event at all for this execution. A newer start,
    failed finish or explicit conflicting identity cannot be hidden by it.
    """
    rows, journal_sha = _journal(daemon)
    _require(journal_sha == journal_pin.get("prefix_sha256")
        and journal_pin.get("chain_verified") is True, "completed_claim_journal_snapshot_changed")
    starts = [row for row in rows if row.get("type") == "implementation_started"
              and row.get("task_id") == task_id]
    _require(bool(starts), "completed_claim_start_missing")
    start = starts[-1]
    proof = completed_callback_proof(daemon, task_id=task_id, canonical_task_cid=canonical_task_cid,
        attempt=start.get("attempt"), workspace=start.get("worktree_path"), branch=start.get("branch"))
    _require(not proof["finish_event_ids"], "completed_claim_finish_present")
    _require(integration_head is None or proof["target_commit"] == integration_head,
             "completed_claim_integration_snapshot_changed")
    _require(proof["journal_sha256"] == journal_sha, "completed_claim_journal_snapshot_changed")
    task = _one(daemon._load_tasks(), lambda row: row.task_id == task_id,
                "completed_claim_task_not_unique")
    history = evidence.historical_queue_validation(Path(daemon.state_path).parent,
        proof["validation_proof"], task, journal_pin,
        callback_sequence=proof["callback_sequence"], callback_event_id=proof["callback_event_id"],
        callback_binding=proof)
    return {"task_cid": canonical_task_cid, "event_id": proof["callback_event_id"],
        "event_kind": "todo_status_updated", "callback_commit": proof["callback_commit"],
        "member_receipt_digest": _digest(proof["member_receipt"]),
        "historical_evidence_digest": _digest(history),
        "observation_provenance": "interrupted_finish_completed_queue_and_durable_callback",
        "native_finish_event_synthesized": False, "request_id": proof["request_id"],
        "merge_commit": proof["merge_commit"], "history_proof_digest": _digest(proof)}


def reconcile_completed_claim(daemon, *, reprove_closure: Callable[[], None]):
    """Use Native's exact-file CAS primitive; caller retains all outer guards."""
    from .improvement_runner import _atomic_json
    from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import (
        CheckoutMutationLease, release_checkout_mutation_lease)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.portal_task_state_control_plane import read_task_state_payload
    _require(not getattr(daemon, "_complaint_read_only_completion_view", False),
             "completed_claim_read_only_view_cannot_release")
    reprove_closure()
    first = review_completed_claim(daemon)
    reprove_closure()
    current = review_completed_claim(daemon)
    _require(first == current, "completed_claim_proof_changed")
    directory = Path(daemon.state_path).parent / "completed-claim-retirement"
    directory.mkdir(mode=0o700, exist_ok=True)
    evidence._directory(directory, private=True)
    operation = _digest(current)
    path = directory / (operation + ".json")
    body = {"schema": SCHEMA, "operation_id": operation, "task_id": current["task_id"],
        "canonical_task_cid": current["canonical_task_cid"], "attempt": current["attempt"],
        "native_sha256": current["native_sha256"], "claim_sha256": current["claim_sha256"],
        "journal_sha256": current["journal_sha256"], "request_id": current["request_id"],
        "merge_commit": current["merge_commit"], "callback_commit": current["callback_commit"],
        "completion_authority": False, "attempt_refunded": False}
    if os.path.lexists(path):
        prior = evidence._object(evidence._read(path))
        _require(prior == {**body, "phase": "prepared"}, "completed_claim_receipt_conflict")
    else:
        _atomic_json(path, {**body, "phase": "prepared"})
    # Reprove after preparing the private receipt, immediately before Native CAS.
    reprove_closure()
    _require(review_completed_claim(daemon) == current, "completed_claim_proof_changed")
    for item in [current["implementation_lease"], {"path": current["claim_path"],
            "metadata": current["claim"], "identity": current["claim_identity"]}]:
        if item is None:
            continue
        lease = CheckoutMutationLease(Path(item["path"]), item["metadata"],
                                      item["identity"][0], item["identity"][1])
        _require(release_checkout_mutation_lease(lease, require_exact_metadata=True),
                 "completed_claim_exact_release_refused")
        _require(not os.path.lexists(lease.lock_path), "completed_claim_release_not_absent")
    _require(read_task_state_payload(daemon.state_path) == current["native_payload"],
             "completed_claim_native_state_changed")
    _atomic_json(path, {**body, "phase": "released"})
    return {"reconciled": True, "blocked": False, "reason": "completed_claim_retired",
        "task_id": current["task_id"], "canonical_task_cid": current["canonical_task_cid"],
        "attempt": current["attempt"], "receipt_path": str(path),
        "completion_authority": False, "paid_dispatch": False, "attempt_refunded": False,
        "native_payload_preserved": True, "task_source": "native_markdown"}

