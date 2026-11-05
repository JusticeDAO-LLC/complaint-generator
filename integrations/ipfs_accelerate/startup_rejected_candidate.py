"""Observe one retained replay-only rejection without granting task authority.

Native has already refused this immutable candidate. This negative observation
only permits its normal task scheduler to continue after startup maintenance.
It never retries, admits, merges, retires or completes the rejected candidate.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Mapping

from . import release_evidence as evidence


def _need(value, step=''):
    if not value:
        raise ValueError(step or 'startup_replay_rejection_unverified')


def _journal(path):
    from ipfs_accelerate_py.agent_supervisor.runtime import event_log
    raw=evidence._read(path,maximum=evidence.MAX_JOURNAL,source=True)
    _need(raw.endswith(b'\n'))
    stream,snapshot=event_log._event_stream_binding(path)
    previous,rows='',[]
    for sequence,line in enumerate(raw.splitlines(),1):
        _need(sequence<=evidence.MAX_EVENTS and len(line)<=evidence.MAX_METADATA)
        row=evidence._object(line)
        _need(type(row.get('sequence')) is int and row['sequence']==sequence
            and row.get('previous_event_id','')==previous and row.get('stream_id')==stream
            and row.get('snapshot_id')==snapshot and row.get('event_id')==event_log._event_identity(row))
        previous=row['event_id'];rows.append(row)
    return rows,hashlib.sha256(raw).hexdigest()


def _refusal(result):
    _need(isinstance(result,Mapping) and type(result.get('returncode')) is int
        and result['returncode']==1 and result.get('provider_dispatched') is False
        and result.get('attempt_consumed') is False)
    validation,merge=result.get('validation_result'),result.get('merge_result')
    _need(isinstance(validation,Mapping) and validation.get('attempted') is False
        and validation.get('passed') is False and type(validation.get('returncode')) is int
        and validation['returncode']==78 and validation.get('reason')=='proposal_gate_failed'
        and not validation.get('error_type') and isinstance(merge,Mapping)
        and merge.get('merged') is False and merge.get('queued') not in (True,)
        and merge.get('attempted') in (None,False) and merge.get('reason')=='not_attempted')
    gate=validation.get('proposal_gate')
    _need(isinstance(gate,Mapping) and gate.get('attempted') is True and gate.get('accepted') is False
        and gate.get('reason_codes')==['stale_proposal_replay']
        and all(re.fullmatch(r'[0-9a-f]{64}',str(gate.get(k,''))) for k in ('proposal_id','receipt_id')))
    return {k:gate.get(k) for k in ('attempted','accepted','reason_codes','proposal_id','receipt_id','repository_tree_id','changed_paths')}


def _scope(result):
    _need(isinstance(result,Mapping))
    return tuple(result.get(k) for k in ('task_id','branch','worktree_path','implementation_commit','baseline_ref','recovery_key'))


def _expired_balance_quarantine(quarantine, path, identity) -> bool:
    """True when this workspace's custody is the aged dead Grok 402 hold."""
    if not isinstance(quarantine, Mapping) or quarantine.get('reason') != 'provider_capacity_settlement_required':
        return False
    record = quarantine.get('lifecycle_record')
    fence = quarantine.get('fence_authority')
    if not isinstance(record, Mapping) or not isinstance(fence, Mapping):
        return False
    if record.get('workspace_path') != str(path) or record.get('canonical_task_cid') != identity.canonical_task_cid:
        return False
    from .settled_balance_capacity import record_is_expired_executed_balance_hold
    observed = dict(fence)
    observed['reason'] = 'provider_capacity_settlement_required'
    return record_is_expired_executed_balance_hold(observed)


def _proof(supervisor,item,daemon,allowed_scopes,allow_expired_balance_quarantine=False):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.current_incident_adjudication import _baseline_unchanged
    from .startup_terminal_candidate import _worktree_custody
    config=supervisor.config;root=Path(config.repo_root)
    _need(isinstance(item,Mapping) and item.get('merged') is False and item.get('validated_before_merge') is True)
    preflight=item.get('preflight_result')
    _need(config.worktree_reconciliation_preflight_enabled is True and isinstance(preflight,Mapping)
        and preflight.get('attempted') is True and preflight.get('mergeable') is True
        and type(preflight.get('returncode')) is int and preflight['returncode']==0)
    recovery=item.get('recovery_result');gate=_refusal(recovery)
    branch,head,key=item.get('branch'),item.get('head'),item.get('recovery_key')
    path=Path(str(item.get('path','')));baseline=recovery.get('baseline_ref')
    _need(isinstance(branch,str) and bool(branch) and all(re.fullmatch(r'[0-9a-f]{40,64}',str(v or '')) for v in (head,key,baseline))
        and item.get('target_ref')==config.merge_target_branch
        and recovery.get('branch')==branch and recovery.get('worktree_path')==str(path)
        and recovery.get('implementation_commit')==head and recovery.get('recovery_key')==key
        and gate['repository_tree_id']==baseline)
    native_rows,native_pin=_journal(Path(daemon.events_path))
    terminals=[r for r in native_rows if r.get('type')=='worktree_reconciliation_validation_finished'
        and r.get('branch')==branch and r.get('implementation_commit')==head and r.get('recovery_key')==key]
    _need(bool(terminals));terminal=terminals[-1]
    _need(_refusal(terminal)==gate)
    task_id=terminal.get('task_id');tasks=daemon._load_tasks()
    matching=[t for t in tasks if t.task_id==task_id]
    _need(len(matching)==1);task=matching[0];identity=daemon._identity_for_task(task)
    binding={'canonical_task_cid':identity.canonical_task_cid,'canonical_task_key':identity.canonical_task_key,'board_namespace':identity.board_namespace}
    _need(all(binding.values()) and native.normalize_status(task.status)=='todo'
        and all(terminal.get(k)==v for k,v in binding.items())
        and recovery.get('task_id')==task_id and recovery.get('task_cid')==identity.canonical_task_cid
        and type(terminal.get('attempt')) is int and terminal['attempt']>=0)
    scope=_scope(recovery)
    starts=[r for r in native_rows if r.get('type')=='worktree_reconciliation_validation_started'
        and _scope(r)==scope]
    _need(bool(starts));start=starts[-1]
    _need(start['sequence']<terminal['sequence'])
    accepted=[r for r in native_rows if r.get('type')=='implementation_proposal_validated'
        and r.get('sequence',0)<start['sequence'] and r.get('task_id')==task_id
        and r.get('accepted') is True and r.get('proposal_id')==gate['proposal_id']
        and r.get('repository_tree_id')==baseline and all(r.get(k)==v for k,v in binding.items())]
    _need(bool(accepted))
    _need(all(start.get(k)==v for k,v in binding.items())
        and all(start.get(k)==terminal.get(k) for k in ('branch','worktree_path','implementation_commit','baseline_ref','recovery_key','attempt'))
        and start.get('provider_dispatched') is False and start.get('attempt_consumed') is False
        and terminal.get('worktree_path')==str(path) and terminal.get('baseline_ref')==baseline)
    for row in native_rows:
        if row['sequence']<=start['sequence']:continue
        same=row.get('task_id')==task_id
        _need(not (same and row['sequence']>terminal['sequence'] and row.get('type') in {
            'implementation_started','implementation_finished','todo_status_updated'}))
        if same and row['sequence']>terminal['sequence'] and row.get('type')=='worktree_reconciliation_validation_started':
            # A later same-task reconciliation is harmless only after the
            # whole current batch independently proves that exact scope closed.
            _need(_scope(row) in allowed_scopes)
        _need(not (same and row.get('type')=='implementation_proposal_validated' and row.get('accepted') is True))
        _need(not (row.get('branch')==branch and row.get('type') in {'merge_candidate_enqueued','merge_finished'}))
    rows,supervisor_pin=_journal(Path(config.events_path))
    reports=[(row,entry) for row in rows if row.get('type')=='worktree_reconciliation'
        for entry in row.get('processed',[]) if isinstance(entry,Mapping)
        and entry.get('branch')==branch and entry.get('head')==head and entry.get('recovery_key')==key]
    _need(bool(reports));report_event,report=reports[-1]
    _need(report.get('path')==str(path) and _refusal(report.get('recovery_result'))==gate
        and report.get('recovery_result',{}).get('implementation_commit')==head)
    _need(path.is_absolute() and path.parent==config.worktree_root and path.resolve(strict=True)==path
        and config.worktree_root.resolve(strict=True)==config.worktree_root)
    records=supervisor._git_worktree_records(root)
    _need(len(records)<=256)
    matches=[r for r in records if r.get('worktree')==str(path)]
    _need(len(matches)==1 and matches[0].get('HEAD')==head
        and str(matches[0].get('branch','')).removeprefix('refs/heads/')==branch
        and _worktree_custody(supervisor,daemon,path,branch,head)
        and evidence._git(path,'rev-parse','HEAD')==head
        and not evidence._git(path,'status','--porcelain','--untracked-files=all','--ignore-submodules=none'))
    _baseline_unchanged(task,path,head,native)
    target=evidence._git(root,'rev-parse',config.merge_target_branch+'^{commit}')
    _need(supervisor._worktree_reconciliation_recovery_key(task_cid=identity.canonical_task_cid,
        baseline_ref=baseline,candidate_commit=head,target_commit=target,mode='pre_merge')==key)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.portal_task_state_control_plane import read_task_state_payload
    state=read_task_state_payload(daemon.state_path)
    _need(isinstance(state,dict))
    state_raw=json.dumps(state,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    _need(state.get('implementation_in_progress') is False and not state.get('active_attempt')
        and not state.get('active_phase') and not state.get('active_worktree_path') and not state.get('active_provider_runner')
        and not state.get('active_log_path') and not state.get('active_branch')
        and not any(state.get(k) for k in ('manual_hold','manual_cancellation','capacity_quarantine','protected_incident','protected_implementation_attempts')))
    _need(not any(os.path.lexists(Path(config.state_dir)/'watchdog'/name) for name in ('HOLD','OPERATOR_STOP')))
    _need(not os.path.lexists(Path(config.state_dir)/native.IMPLEMENTATION_PROTECTED_ACTIVE_SNAPSHOT_FILENAME))
    _need(not os.path.lexists(daemon._implementation_lock_path())
        and not os.path.lexists(daemon._implementation_task_claim_path(task_id,canonical_task_cid=identity.canonical_task_cid)))
    quarantine=daemon.worktree_lifecycle.load_quarantine(path)
    if allow_expired_balance_quarantine:
        _need(_expired_balance_quarantine(quarantine, path, identity), 'expired_balance_quarantine')
    else:
        _need(quarantine is None, 'unexpected_quarantine')
    life=daemon.worktree_lifecycle.load_workspace(path)
    if allow_expired_balance_quarantine:
        _need(life is None or (life.canonical_task_cid==identity.canonical_task_cid
            and life.workspace_path==str(path)), 'quarantine_lifecycle_identity')
    else:
        _need(life is None or (life.is_terminal and life.canonical_task_cid==identity.canonical_task_cid
            and life.workspace_path==str(path) and life.branch==branch), 'lifecycle_not_terminal')
    # Existing queue APIs may initialize schema. Only inspect its existing
    # database read-only; pending, in-flight or quarantined effects stay blocking.
    import duckdb
    from ipfs_accelerate_py.agent_supervisor.task_sources.duckdb_state import connect_duckdb_with_policy
    database=Path(daemon.merge_queue_dir)/'merge_queue.duckdb'
    evidence._readable_database(database,private_root=Path(config.state_dir))
    connection=connect_duckdb_with_policy(duckdb,database,read_only=True)
    try:
        pending=connection.execute("SELECT COUNT(*) FROM merge_requests WHERE status NOT IN ('completed','failed')").fetchone()[0]
    finally:connection.close()
    _need(pending==0)
    return (native_pin,supervisor_pin,hashlib.sha256(state_raw).hexdigest(),
        hashlib.sha256(evidence._read(Path(daemon.todo_path),source=True)).hexdigest(),target,
        terminal['event_id'],start['event_id'],gate,report_event['event_id'])


def retained_replay_rejection(supervisor,item,*,maintenance_result,allow_expired_balance_quarantine=False) -> bool:
    """Reprove the negative outcome; never infer a task from branch spelling."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
    from ipfs_accelerate_py.agent_supervisor.merge.workspace_quarantine import maintenance
    try:
        if (not isinstance(maintenance_result,Mapping) or maintenance_result.get('maintenance_blocked') is True
                or maintenance_result.get('stuck') is not False
                or getattr(supervisor,'_complaint_startup_preflight_pending',False) is not True):return False
        context=getattr(supervisor,'_complaint_startup_reconciliation_context',None)
        daemon=context.get('daemon') if isinstance(context,Mapping) else None
        if not isinstance(daemon,PortalImplementationDaemon) or daemon.implement is not False:return False
        with maintenance(Path(supervisor.config.repo_root)) as unfenced:
            if not unfenced:return False
            processed=maintenance_result.get('worktree_reconciliation',{}).get('processed')
            _need(isinstance(processed,list) and 0<len(processed)<=50 and isinstance(item,Mapping))
            task_id=item.get('recovery_result',{}).get('task_id')
            batch=[entry for entry in processed if isinstance(entry,Mapping)
                and entry.get('recovery_result',{}).get('task_id')==task_id]
            _need(bool(task_id) and item in batch)
            scopes=[_scope(entry.get('recovery_result')) for entry in batch]
            _need(len(set(scopes))==len(scopes))
            allowed_scopes=set(scopes)
            first=[_proof(supervisor,entry,daemon,allowed_scopes,allow_expired_balance_quarantine) for entry in batch]
            _need(len({proof[-1] for proof in first})==1)
            return (first==[_proof(supervisor,entry,daemon,allowed_scopes,allow_expired_balance_quarantine) for entry in batch]
                and getattr(supervisor,'_complaint_startup_reconciliation_context',None) is context
                and getattr(supervisor,'_complaint_startup_preflight_pending',False) is True)
    except Exception as exc:
        if allow_expired_balance_quarantine:
            retained_quarantined_balance_replay.last_error=f'{type(exc).__name__}: {exc}'
        return False


def retained_quarantined_balance_replay(supervisor,item,*,maintenance_result) -> bool:
    """Permit startup past one aged dead 402 quarantine. Do not retry or complete it."""
    retained_quarantined_balance_replay.last_error=''
    return retained_replay_rejection(
        supervisor, item, maintenance_result=maintenance_result,
        allow_expired_balance_quarantine=True)
