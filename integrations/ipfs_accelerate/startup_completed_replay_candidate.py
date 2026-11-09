"""Read-only recognition of an obsolete, closed Native replay rejection.

The rejected implementation remains rejected and retained. Only a separate
genuinely integrated winner and current canonical completion can make its
later merge conflict nonblocking during the guarded startup pass.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Mapping

from . import release_evidence as evidence
from .startup_rejected_candidate import _journal, _need, _refusal, _scope
from .startup_terminal_candidate import _worktree_custody


def _winner(supervisor, row, task_id, binding):
    """Join the actual compact Native proof to the real two-parent commit."""
    result, validation = row.get('merge_result'), row.get('validation_result')
    _need(isinstance(result, Mapping) and isinstance(validation, Mapping)
        and validation.get('passed') is True and type(validation.get('returncode')) is int
        and validation['returncode'] == 0 and result.get('attempted') is True
        and result.get('merged') is True and type(result.get('returncode')) is int
        and result['returncode'] == 0 and result.get('target_branch') == supervisor.config.merge_target_branch
        and result.get('completion_task_cids') == {task_id: binding['canonical_task_cid']}
        and all(result.get(k) == binding[k] for k in ('canonical_task_cid', 'canonical_task_key')))
    gate, proof = validation.get('proposal_gate'), result.get('integration_commit_proof')
    _need(isinstance(gate, Mapping) and gate.get('attempted') is True and gate.get('accepted') is True
        and gate.get('repository_tree_id') == row.get('baseline_ref')
        and re.fullmatch(r'[0-9a-f]{64}', str(gate.get('proposal_id', ''))) is not None
        and isinstance(proof, Mapping) and proof.get('passed') is True and proof.get('reasons') == [])
    head, integrated = row.get('implementation_commit'), result.get('merge_commit')
    _need(all(re.fullmatch(r'[0-9a-f]{40}', str(v or '')) for v in (head, integrated, row.get('baseline_ref')))
        and result.get('implementation_commit') == head and proof.get('implementation_commit') == head
        and proof.get('integration_commit') == integrated and proof.get('integration_ref') == integrated
        and proof.get('target_branch') == supervisor.config.merge_target_branch)
    parents = evidence._git(supervisor.config.repo_root, 'rev-list', '--parents', '-n', '1', integrated).split()
    _need(len(parents) == 3 and parents[0] == integrated and parents[2] == head and parents[1] != head)
    evidence._git(supervisor.config.repo_root, 'merge-base', '--is-ancestor', integrated, 'HEAD')
    evidence._git(supervisor.config.repo_root, 'merge-base', '--is-ancestor', row['baseline_ref'], head)
    return gate


def _quiet(supervisor, daemon, task_id, identity, path, branch):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.portal_task_state_control_plane import read_task_state_payload
    state = read_task_state_payload(daemon.state_path)
    _need(isinstance(state, dict) and state.get('implementation_in_progress') is False
        and not any(state.get(k) for k in ('active_attempt', 'active_phase', 'active_worktree_path',
            'active_provider_runner', 'active_log_path', 'active_branch', 'manual_hold', 'manual_cancellation',
            'capacity_quarantine', 'protected_incident', 'protected_implementation_attempts')))
    state_root = Path(supervisor.config.state_dir)
    _need(not any(os.path.lexists(state_root / 'watchdog' / name) for name in ('HOLD', 'OPERATOR_STOP'))
        and not os.path.lexists(state_root / native.IMPLEMENTATION_PROTECTED_ACTIVE_SNAPSHOT_FILENAME)
        and not os.path.lexists(daemon._implementation_lock_path())
        and not os.path.lexists(daemon._implementation_task_claim_path(task_id,
            canonical_task_cid=identity.canonical_task_cid))
        and daemon.worktree_lifecycle.load_quarantine(path) is None)
    life = daemon.worktree_lifecycle.load_workspace(path)
    _need(life is None or (life.is_terminal and life.canonical_task_cid == identity.canonical_task_cid
        and life.workspace_path == str(path) and life.branch == branch))
    import duckdb
    from ipfs_accelerate_py.agent_supervisor.task_sources.duckdb_state import connect_duckdb_with_policy
    database = Path(daemon.merge_queue_dir) / 'merge_queue.duckdb'
    evidence._readable_database(database, private_root=state_root)
    connection = connect_duckdb_with_policy(duckdb, database, read_only=True)
    try:
        _need(connection.execute("SELECT COUNT(*) FROM merge_requests WHERE status NOT IN ('completed','failed')").fetchone()[0] == 0)
        queue = connection.execute('SELECT request_id, status FROM merge_requests ORDER BY request_id LIMIT 10001').fetchall()
        _need(len(queue) <= 10000)
    finally:
        connection.close()
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(), queue


def _proof(supervisor, candidate, daemon):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.current_incident_adjudication import _baseline_unchanged
    config = supervisor.config
    branch, head = candidate.get('branch'), candidate.get('head')
    path = Path(str(candidate.get('path', '')))
    merge, preflight = candidate.get('merge_result'), candidate.get('preflight_result')
    _need(isinstance(branch, str) and branch.startswith('implementation/')
        and re.fullmatch(r'[0-9a-f]{40}', str(head)) is not None
        and config.worktree_reconciliation_preflight_enabled is True
        and isinstance(merge, Mapping) and isinstance(preflight, Mapping)
        and candidate.get('merged') is False and merge.get('attempted') is False and merge.get('merged') is False
        and merge.get('reason') == 'preflight_merge_conflict' and preflight.get('reason') == 'preflight_merge_conflict'
        and preflight.get('attempted') is True and preflight.get('mergeable') is False
        and type(preflight.get('returncode')) is int and preflight['returncode'] == 1
        and all(row.get('branch') == branch and row.get('target_ref') == config.merge_target_branch
            for row in (candidate, merge, preflight)))
    rows, native_pin = _journal(Path(daemon.events_path))
    terminals = [r for r in rows if r.get('type') == 'worktree_reconciliation_validation_finished'
        and r.get('branch') == branch and r.get('implementation_commit') == head]
    _need(bool(terminals))
    terminal = terminals[-1]
    gate = _refusal(terminal)
    task_id, baseline, key = terminal.get('task_id'), terminal.get('baseline_ref'), terminal.get('recovery_key')
    _need(all(re.fullmatch(r'[0-9a-f]{40,64}', str(v or '')) for v in (baseline, key))
        and terminal.get('worktree_path') == str(path) and gate['repository_tree_id'] == baseline
        and type(terminal.get('attempt')) is int and terminal['attempt'] >= 0)
    matching = [task for task in daemon._load_tasks() if task.task_id == task_id]
    _need(len(matching) == 1)
    task = matching[0]
    identity = daemon._identity_for_task(task)
    binding = {'canonical_task_cid': identity.canonical_task_cid,
        'canonical_task_key': identity.canonical_task_key, 'board_namespace': identity.board_namespace}
    _need(all(binding.values()) and native.normalize_status(task.status) == 'completed'
        and all(terminal.get(k) == v for k, v in binding.items())
        and terminal.get('task_cid') == identity.canonical_task_cid)
    scope = _scope(terminal)
    starts = [r for r in rows if r.get('type') == 'worktree_reconciliation_validation_started' and _scope(r) == scope]
    _need(bool(starts))
    start = starts[-1]
    _need(start['sequence'] < terminal['sequence'] and all(start.get(k) == v for k, v in binding.items())
        and start.get('provider_dispatched') is False and start.get('attempt_consumed') is False
        and start.get('attempt') == terminal.get('attempt'))
    admitted = [r for r in rows if r.get('type') == 'implementation_proposal_validated'
        and r['sequence'] < start['sequence'] and r.get('task_id') == task_id
        and r.get('accepted') is True and r.get('proposal_id') == gate['proposal_id']
        and r.get('repository_tree_id') == baseline and all(r.get(k) == v for k, v in binding.items())]
    _need(bool(admitted))
    winners = [r for r in rows if r.get('type') == 'implementation_finished'
        and r['sequence'] > terminal['sequence'] and r.get('task_id') == task_id
        and all(r.get(k) == v for k, v in binding.items()) and type(r.get('returncode')) is int
        and r['returncode'] == 0 and r.get('implementation_commit') != head and r.get('branch') != branch]
    _need(bool(winners))
    winner = winners[-1]
    winning_gate = _winner(supervisor, winner, task_id, binding)
    _need(any(r.get('type') == 'implementation_proposal_validated' and r.get('task_id') == task_id
        and terminal['sequence'] < r['sequence'] < winner['sequence'] and r.get('accepted') is True
        and r.get('proposal_id') == winning_gate['proposal_id']
        and r.get('repository_tree_id') == winner['baseline_ref']
        and all(r.get(k) == v for k, v in binding.items()) for r in rows))
    for row in rows:
        same = row.get('task_id') == task_id
        # A retained candidate may not have a later unclosed/replaced invocation.
        if row['sequence'] > terminal['sequence'] and row.get('branch') == branch:
            _need(row.get('type') not in {'implementation_started', 'implementation_finished',
                'worktree_reconciliation_validation_started', 'worktree_reconciliation_candidate_queued',
                'merge_candidate_enqueued', 'merge_finished'})
        if same and row['sequence'] > winner['sequence']:
            _need(row.get('type') not in {'implementation_started', 'implementation_finished',
                'worktree_reconciliation_validation_started', 'worktree_reconciliation_candidate_queued',
                'todo_status_updated'} and not (row.get('type') == 'implementation_proposal_validated'
                    and row.get('accepted') is True))
    reports, supervisor_pin = _journal(Path(config.events_path))
    historical = [(r, entry) for r in reports if r.get('type') == 'worktree_reconciliation'
        for entry in r.get('processed', []) if isinstance(entry, Mapping)
        and entry.get('branch') == branch and entry.get('head') == head and entry.get('recovery_key') == key]
    _need(bool(historical))
    report_event, report = historical[-1]
    recovery = report.get('recovery_result')
    _need(isinstance(recovery, Mapping) and _scope(recovery) == scope and _refusal(recovery) == gate
        and report.get('path') == str(path) and report.get('target_ref') == config.merge_target_branch)
    _need(path.is_absolute() and path.parent == config.worktree_root and path.resolve(strict=True) == path
        and config.worktree_root.resolve(strict=True) == config.worktree_root)
    records = supervisor._git_worktree_records(config.repo_root)
    _need(len(records) <= 256)
    matches = [r for r in records if r.get('worktree') == str(path)]
    _need(len(matches) == 1 and matches[0].get('HEAD') == head
        and str(matches[0].get('branch', '')).removeprefix('refs/heads/') == branch
        and _worktree_custody(supervisor, daemon, path, branch, head)
        and evidence._git(path, 'rev-parse', 'HEAD') == head
        and not evidence._git(path, 'status', '--porcelain', '--untracked-files=all', '--ignore-submodules=none'))
    _baseline_unchanged(task, path, head, native)
    _need(not native.PortalImplementationDaemon._completed_task_binding_error(daemon,
        {'task': {'task_id': task_id}, 'completion_task_cids': {task_id: identity.canonical_task_cid}}))
    return (native_pin, supervisor_pin, start['event_id'], terminal['event_id'], report_event['event_id'],
        winner['event_id'], evidence._git(config.repo_root, 'rev-parse', 'HEAD'),
        hashlib.sha256(evidence._read(Path(daemon.todo_path), source=True)).hexdigest(),
        _quiet(supervisor, daemon, task_id, identity, path, branch))


def completed_replay_conflict(supervisor, candidate) -> bool:
    """Observe a completed task's closed failure; never act on that candidate."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor import PortalImplementationSupervisor
    from ipfs_accelerate_py.agent_supervisor.merge.workspace_quarantine import maintenance
    try:
        _need(getattr(supervisor, '_complaint_startup_preflight_pending', False) is True)
        context = getattr(supervisor, '_complaint_startup_reconciliation_context', None)
        daemon = context.get('daemon') if isinstance(context, Mapping) else None
        if daemon is None:
            daemon = PortalImplementationSupervisor._build_worktree_reconciliation_daemon(supervisor)
        _need(isinstance(daemon, PortalImplementationDaemon) and daemon.implement is False)
        with maintenance(Path(supervisor.config.repo_root)) as unfenced:
            _need(unfenced)
            first = _proof(supervisor, candidate, daemon)
            return (first == _proof(supervisor, candidate, daemon)
                and getattr(supervisor, '_complaint_startup_preflight_pending', False) is True
                and getattr(supervisor, '_complaint_startup_reconciliation_context', None) is context)
    except Exception:
        return False
