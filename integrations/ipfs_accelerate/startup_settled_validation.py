"""Observe a Native failed validation so startup can schedule independent work.

This negative observation never accepts, merges, retries, retires or completes
the retained candidate. Native keeps its task status, counters and retry policy.
"""
from pathlib import Path
from typing import Mapping
import os

from . import release_evidence as evidence
from .startup_rejected_candidate import _journal, _need, _scope
from .startup_terminal_candidate import _worktree_custody


def _proof(supervisor, daemon, item):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.current_incident_adjudication import _baseline_unchanged
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.portal_task_state_control_plane import read_task_state_payload

    config = supervisor.config
    _need(isinstance(item, Mapping) and item.get('merged') is False)
    merge, preflight = item.get('merge_result'), item.get('preflight_result')
    _need(isinstance(merge, Mapping) and merge.get('merged') is False
        and merge.get('attempted') in (None, False) and merge.get('queued') in (None, False)
        and merge.get('reason') in {'not_attempted', 'reconciliation_candidate_validation_already_settled'}
        and isinstance(preflight, Mapping) and preflight.get('attempted') is True
        and preflight.get('mergeable') is True and type(preflight.get('returncode')) is int
        and preflight['returncode'] == 0 and item.get('target_ref') == config.merge_target_branch)
    branch, head, key = (item.get(k) for k in ('branch', 'head', 'recovery_key'))
    path = Path(str(item.get('path', '')))
    _need(isinstance(branch, str) and branch.startswith('implementation/')
        and all(isinstance(v, str) and len(v) == 40 and all(c in '0123456789abcdef' for c in v) for v in (head, key))
        and path.is_absolute() and path.parent == config.worktree_root
        and path.resolve(strict=True) == path and config.worktree_root.resolve(strict=True) == config.worktree_root)
    rows, journal_digest = _journal(Path(daemon.events_path))
    ends = [r for r in rows if r.get('type') == 'worktree_reconciliation_validation_finished'
        and r.get('branch') == branch and r.get('implementation_commit') == head and r.get('recovery_key') == key]
    _need(bool(ends))
    end = ends[-1]
    _need(type(end.get('returncode')) is int and end['returncode'] == 1
        and end.get('provider_dispatched') is False and end.get('attempt_consumed') is False
        and end.get('worktree_path') == str(path))
    validation, terminal_merge = end.get('validation_result'), end.get('merge_result')
    _need(isinstance(validation, Mapping) and validation.get('attempted') is True
        and validation.get('passed') is False and validation.get('reason') == 'declared_validation_failed'
        and type(validation.get('returncode')) is int and validation['returncode'] == 78
        and validation.get('error') == 'validation_command_failed'
        and not validation.get('error_type') and isinstance(terminal_merge, Mapping)
        and terminal_merge.get('merged') is False and terminal_merge.get('queued') in (None, False)
        and terminal_merge.get('reason') == 'not_attempted')
    gate = validation.get('proposal_gate')
    _need(isinstance(gate, Mapping) and gate.get('attempted') is True and gate.get('accepted') is True
        and gate.get('reason_codes') == [] and gate.get('repository_tree_id') == end.get('baseline_ref'))
    matching = [t for t in daemon._load_tasks() if t.task_id == end.get('task_id')]
    _need(len(matching) == 1)
    task = matching[0]
    identity = daemon._identity_for_task(task)
    binding = dict(task_id=task.task_id, canonical_task_cid=identity.canonical_task_cid,
        canonical_task_key=identity.canonical_task_key, board_namespace=identity.board_namespace)
    _need(all(binding.values()) and native.normalize_status(task.status) == 'todo'
        and all(end.get(k) == v for k, v in binding.items()))
    results = validation.get('results')
    _need(isinstance(results, list) and len(results) == len(task.validation) and bool(results)
        and [r.get('command') for r in results] == list(task.validation)
        and all(type(r.get('returncode')) is int for r in results)
        and any(r['returncode'] != 0 for r in results))
    starts = [r for r in rows if r.get('type') == 'worktree_reconciliation_validation_started' and _scope(r) == _scope(end)]
    _need(bool(starts))
    start = starts[-1]
    _need(start['sequence'] < end['sequence'] and all(start.get(k) == v for k, v in binding.items())
        and start.get('provider_dispatched') is False and start.get('attempt_consumed') is False)
    _need(not any(r['sequence'] > end['sequence'] and r.get('task_id') == task.task_id
        and r.get('type') in {'implementation_started', 'implementation_finished', 'worktree_reconciliation_validation_started', 'todo_status_updated'} for r in rows))
    _need(not any(r['sequence'] > start['sequence'] and r.get('branch') == branch
        and r.get('type') in {'merge_candidate_enqueued', 'merge_finished'} for r in rows))
    reports, report_digest = _journal(Path(config.events_path))
    prior = [(r, entry) for r in reports if r.get('type') == 'worktree_reconciliation'
        for entry in r.get('processed', []) if entry.get('branch') == branch and entry.get('head') == head
        and entry.get('recovery_key') == key and _scope(entry.get('recovery_result', {})) == _scope(end)]
    _need(bool(prior))
    report, entry = prior[-1]
    failed = entry['recovery_result']
    _need(failed.get('validation_result') == validation and failed.get('returncode') == 1
        and failed.get('provider_dispatched') is False and failed.get('attempt_consumed') is False
        and entry.get('validated_before_merge') is True and entry.get('merged') is False)
    records = supervisor._git_worktree_records(config.repo_root)
    matching = [r for r in records if r.get('worktree') == str(path)]
    _need(len(records) <= 256 and len(matching) == 1 and matching[0].get('HEAD') == head
        and str(matching[0].get('branch', '')).removeprefix('refs/heads/') == branch
        and _worktree_custody(supervisor, daemon, path, branch, head)
        and not evidence._git(path, 'status', '--porcelain', '--untracked-files=all', '--ignore-submodules=none'))
    _baseline_unchanged(task, path, head, native)
    target = evidence._git(Path(config.repo_root), 'rev-parse', config.merge_target_branch + '^{commit}')
    _need(supervisor._worktree_reconciliation_recovery_key(task_cid=identity.canonical_task_cid,
        baseline_ref=end['baseline_ref'], candidate_commit=head, target_commit=target, mode='pre_merge') == key)
    state = read_task_state_payload(daemon.state_path)
    _need(isinstance(state, dict) and state.get('implementation_in_progress') is False
        and not any(state.get(k) for k in ('active_task_id', 'active_attempt', 'active_phase', 'active_provider_runner',
            'active_worktree_path', 'active_log_path', 'active_branch', 'manual_hold', 'manual_cancellation',
            'capacity_quarantine', 'protected_incident', 'protected_implementation_attempts')))
    _need(not any(os.path.lexists(Path(config.state_dir) / 'watchdog' / k) for k in ('HOLD', 'OPERATOR_STOP'))
        and not os.path.lexists(Path(config.state_dir) / native.IMPLEMENTATION_PROTECTED_ACTIVE_SNAPSHOT_FILENAME)
        and not os.path.lexists(daemon._implementation_lock_path())
        and not os.path.lexists(daemon._implementation_task_claim_path(task.task_id, canonical_task_cid=identity.canonical_task_cid)))
    life = daemon.worktree_lifecycle.load_workspace(path)
    _need(daemon.worktree_lifecycle.load_quarantine(path) is None
        and (life is None or life.is_terminal and life.canonical_task_cid == identity.canonical_task_cid
            and life.workspace_path == str(path) and life.branch == branch))
    import duckdb
    from ipfs_accelerate_py.agent_supervisor.task_sources.duckdb_state import connect_duckdb_with_policy
    database = Path(daemon.merge_queue_dir) / 'merge_queue.duckdb'
    evidence._readable_database(database, private_root=Path(config.state_dir))
    connection = connect_duckdb_with_policy(duckdb, database, read_only=True)
    try:
        _need(connection.execute("SELECT COUNT(*) FROM merge_requests WHERE status NOT IN ('completed','failed')").fetchone()[0] == 0)
    finally:
        connection.close()
    return journal_digest, report_digest, state, target, end['event_id'], report['event_id']


def settled_validation_failure(supervisor, item, *, maintenance_result):
    """Recognize only a fully closed, independently failed Native validation."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
    from ipfs_accelerate_py.agent_supervisor.merge.workspace_quarantine import maintenance

    daemon = None
    try:
        _need(isinstance(maintenance_result, Mapping) and maintenance_result.get('maintenance_blocked') is not True
            and maintenance_result.get('stuck') is False
            and getattr(supervisor, '_complaint_startup_preflight_pending', False) is True)
        context = getattr(supervisor, '_complaint_startup_reconciliation_context', None)
        daemon = context.get('daemon') if isinstance(context, Mapping) else None
        created = daemon is None
        if created:
            daemon = supervisor._build_worktree_reconciliation_daemon()
        _need(isinstance(daemon, PortalImplementationDaemon) and daemon.implement is False)
        with maintenance(Path(supervisor.config.repo_root)) as unfenced:
            _need(unfenced)
            first = _proof(supervisor, daemon, item)
            return first == _proof(supervisor, daemon, item)
    except Exception:
        return False
    finally:
        if isinstance(daemon, PortalImplementationDaemon) and locals().get('created'):
            daemon.close_event_runtime()
