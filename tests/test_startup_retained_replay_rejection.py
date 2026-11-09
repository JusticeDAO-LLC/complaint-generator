"""Synthetic private tasks, genuine Native admission/reconcile/Git producers.

No model/provider is invoked and no implementation task is completed here.
"""
from dataclasses import asdict
from pathlib import Path
import json
import os
import subprocess

import pytest
from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import improvement_plan as compiler
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as daemon_native

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _git(root, *args):
    return subprocess.run(['git', '--no-replace-objects', *args], cwd=root,
        capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture(scope='module')
def native_replay_world(tmp_path_factory):
    base=tmp_path_factory.mktemp('genuine-retained-replay')
    root,state,trees=(base/name for name in ('repo','state','worktrees'))
    for p in (root,state,trees): p.mkdir(mode=0o700)
    _git(root,'init','-q','-b','main');_git(root,'config','user.name','Synthetic Native replay fixture');_git(root,'config','user.email','synthetic@example.invalid')
    tasks=[]
    for n in (1,2):
        tasks.append({'id':f'CIMP-SYN-{n:02}', 'goal_id':'goal.synthetic','subgoal_id':'sub.synthetic',
            'title':'Retained failure' if n==1 else 'Independent ready task','priority':'P1' if n==1 else 'P0',
            'targets':[f'out/task{n}.py', 'tests/test_retained.py' if n==1 else 'tests/test_independent.py'],'depends_on':[],'acceptance':['Synthetic local boundary only.'],
            'validation_commands':['python -m pytest -q tests/test_retained.py' if n==1 else 'python -m pytest -q tests/test_independent.py'],
            'implementation_prompt':'Synthetic fixture only; no model call.'})
    spec={'schema_version':'complaint-generator/improvement-spec@1','title':'Synthetic startup boundary',
        'provider':{'router':'ipfs_accelerate_py.llm_router','provider':'grok_cli','model':'grok-4.7','allow_fallback':False},
        'goals':[{'id':'goal.synthetic','title':'Synthetic','subgoals':[{'id':'sub.synthetic','title':'Synthetic'}]}],
        'tasks':tasks,'execution_policy':{'synthetic_only':True},'findings':[]}
    specfile=root/runner.SPEC_RELATIVE;specfile.parent.mkdir(parents=True);specfile.write_text(json.dumps(spec))
    compiler.generate(specfile,root)
    _git(root,'add','.');_git(root,'commit','-qm','Synthetic task source')
    baseline=_git(root,'rev-parse','HEAD')
    board=root/compiler.BOARD_RELATIVE
    config=native.PortalSupervisorConfig(todo_path=board,state_path=state/'state.json',strategy_path=state/'strategy.json',
        events_path=state/'supervisor_events.jsonl',state_dir=state,repo_root=root,state_prefix='synthetic',task_prefix='## CIMP-',
        worktree_root=trees,merge_target_branch='main',merge_queue_dir=state/'merge-queue',
        implementation_protected_paths=(compiler.BOARD_RELATIVE,),
        worktree_scan_cache_enabled=False,worktree_reconciliation_max_merges=1,
        implementation_timeout=30,max_task_attempts=3,llm_merge_resolver_command='')
    supervisor=runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor)(config)
    # Genuine Native constructor and source identities, with no method/class
    # replacements. Initial validation is administrative and provider-free.
    daemon=native.PortalImplementationSupervisor._build_worktree_reconciliation_daemon(supervisor)
    daemon_native.PortalTaskState().save(config.state_path)
    current=daemon._load_tasks();daemon._register_task_identities(current);task=current[0]
    identity=daemon._identity_for_task(task)
    branch='implementation/private-retained-attempt-1';leaf=trees/'workspace_retained'
    _git(root,'worktree','add','-q','-b',branch,str(leaf),baseline)
    (leaf/'out').mkdir();(leaf/'out/task1.py').write_text('VALUE = "synthetic failed candidate"\n')
    (leaf/'tests').mkdir();(leaf/'tests/test_retained.py').write_text('def test_retained_failure():\n assert False\n')
    _git(leaf,'add','out/task1.py','tests/test_retained.py')
    admitted=daemon._validate_implementation_patch(leaf,task,baseline_ref=baseline,allow_scope_adjudication=False)
    assert admitted.accepted, daemon._compact_proposal_validation(admitted)
    _git(leaf,'commit','-qm','Synthetic retained candidate')
    head=_git(leaf,'rev-parse','HEAD')
    key=supervisor._worktree_reconciliation_recovery_key(task_cid=identity.canonical_task_cid,baseline_ref=baseline,
        candidate_commit=head,target_commit=baseline,mode='pre_merge')
    result=daemon.reconcile_validated_worktree_candidate(worktree_path=leaf,branch_name=branch,task=task,
        baseline_ref=baseline,candidate_commit=head,recovery_key=key)
    assert result['provider_dispatched'] is False and result['attempt_consumed'] is False
    assert result['validation_result']['passed'] is False
    assert result['validation_result']['proposal_gate']['reason_codes']==['stale_proposal_replay']
    return dict(root=root,state=state,trees=trees,leaf=leaf,branch=branch,head=head,baseline=baseline,key=key,
        config=config,supervisor=supervisor,daemon=daemon,task=task,identity=identity,result=result)


def test_actual_terminal_replay_does_not_block_independent_native_selection(native_replay_world):
    w=native_replay_world;s=w['supervisor']
    before=asdict(daemon_native.PortalTaskState.load(s.config.state_path))
    source=s.config.todo_path.read_bytes();ref=_git(w['root'],'rev-parse',w['branch'])
    s._complaint_startup_preflight_pending=True
    s._complaint_startup_reconciliation_context=None
    # This is the actual maintenance loop, including its real custody/lease/
    # source/protected guards. The baseline Host currently raises here.
    result=s.run_once(include_refill=False)
    w['maintenance_result']=result
    assert result.get('maintenance_blocked') is not True
    assert s._complaint_startup_preflight_pending is False
    item=result['worktree_reconciliation']['processed'][0]
    assert item['recovery_result']['validation_result']['proposal_gate']['reason_codes']==['stale_proposal_replay']
    assert item['merged'] is False and item['recovery_result']['attempt_consumed'] is False
    assert w['leaf'].is_dir() and _git(w['root'],'rev-parse',w['branch'])==ref
    assert s.config.todo_path.read_bytes()==source
    after=asdict(daemon_native.PortalTaskState.load(s.config.state_path))
    for name in ['implementation_attempts','implementation_attempts_by_cid']+[n for n in before if n.startswith('completed')]:
        assert after[name]==before[name]
    w['daemon'].run_once()
    selected=daemon_native.PortalTaskState.load(s.config.state_path)
    assert selected.active_task_id=='CIMP-SYN-02' and selected.implementation_in_progress is False
    assert after['implementation_attempts'].get('CIMP-SYN-02',0)==0


@pytest.mark.parametrize('damage',['new_head','new_start','scope','additional_reason','dirty','foreign_worktree','missing_terminal','private_hold','live_claim','live_lease','changed_definition','missing_report','preflight_conflict'])
def test_uncertain_or_changed_candidate_still_blocks(native_replay_world,damage):
    from copy import deepcopy
    import shutil
    from integrations.ipfs_accelerate.startup_rejected_candidate import retained_replay_rejection,_journal
    w=native_replay_world;s=w['supervisor'];d=w['daemon']
    s._complaint_startup_preflight_pending=True
    s._reconciliation_task_context(d)
    reports,_=_journal(s.config.events_path)
    item=deepcopy(w['maintenance_result']['worktree_reconciliation']['processed'][0])
    assert retained_replay_rejection(s,item,maintenance_result=w['maintenance_result']) is True
    native_raw=d.events_path.read_bytes();super_raw=s.config.events_path.read_bytes();board=s.config.todo_path.read_bytes()
    old=(w['leaf']/'out/task1.py').read_bytes();hold=w['state']/'watchdog/HOLD';foreign=None;pending=None;claim_path=None;lease_metadata=None
    try:
        if damage=='new_head':
            (w['leaf']/'out/task1.py').write_bytes(old+b'# synthetic changed candidate\n')
            _git(w['leaf'],'add','out/task1.py');_git(w['leaf'],'commit','-qm','Synthetic changed HEAD')
        elif damage=='dirty':(w['leaf']/'out/task1.py').write_bytes(old+b'# dirty\n')
        elif damage=='new_start':
            d._record_event('worktree_reconciliation_validation_started',{'task_id':w['task'].task_id,'task_cid':w['identity'].canonical_task_cid,'attempt':1,'branch':w['branch'],'worktree_path':str(w['leaf']),'baseline_ref':w['baseline'],'implementation_commit':w['head'],'recovery_key':w['key'],'provider_dispatched':False,'attempt_consumed':False})
        elif damage=='scope':item['recovery_result']['task_cid']='wrong-canonical-task'
        elif damage=='additional_reason':item['recovery_result']['validation_result']['proposal_gate']['reason_codes'].append('path_outside_scope')
        elif damage=='preflight_conflict':item['preflight_result']['mergeable']=False
        elif damage=='private_hold':hold.parent.mkdir(exist_ok=True);hold.write_text('Synthetic explicit operator hold\n')
        elif damage=='changed_definition':s.config.todo_path.write_bytes(board.replace(b'Synthetic local boundary only.',b'Changed synthetic boundary.'))
        elif damage=='missing_terminal':
            lines=native_raw.splitlines(keepends=True)
            seq=max(i for i,line in enumerate(lines) if json.loads(line).get('type')=='worktree_reconciliation_validation_finished')
            d.events_path.write_bytes(b''.join(lines[:seq]))
        elif damage=='missing_report':
            lines=super_raw.splitlines(keepends=True)
            seq=max(i for i,line in enumerate(lines) if json.loads(line).get('type')=='worktree_reconciliation')
            s.config.events_path.write_bytes(b''.join(lines[:seq]))
        elif damage=='foreign_worktree':
            foreign=w['leaf'].with_name('retained-original');w['leaf'].rename(foreign)
            subprocess.run(['git','clone','--quiet','--shared',str(w['root']),str(w['leaf'])],check=True)
            _git(w['leaf'],'checkout','-q','-b',w['branch'],w['head'])
        elif damage=='live_claim':
            metadata=d._build_implementation_task_claim_metadata(w['task'],1,daemon_native.utc_now())
            claim_path=d._implementation_task_claim_path(w['task'].task_id,canonical_task_cid=w['identity'].canonical_task_cid)
            ok,reason,_=d._try_acquire_implementation_task_claim(claim_path,metadata);assert ok,reason
        else:
            lease_metadata=d._build_implementation_lock_metadata(w['task'],1,daemon_native.utc_now())
            fd,reason,_=d._try_acquire_lock(d._implementation_lock_path(),lock_kind='implementation',owner_active=d._implementation_lock_owner_is_active)
            assert fd is not None,reason;d._write_lock_metadata(fd,lease_metadata)
        assert retained_replay_rejection(s,item,maintenance_result=w['maintenance_result']) is False
        assert item.get('merged') is False
    finally:
        if foreign is not None:
            shutil.rmtree(w['leaf']);foreign.rename(w['leaf'])
        if damage=='new_head':_git(w['leaf'],'reset','--hard',w['head'])
        (w['leaf']/'out/task1.py').write_bytes(old)
        d.events_path.write_bytes(native_raw);s.config.events_path.write_bytes(super_raw);s.config.todo_path.write_bytes(board)
        hold.unlink(missing_ok=True)
        if claim_path is not None:
            d._release_implementation_task_claim(claim_path,metadata)
        if lease_metadata is not None:d._release_implementation_lock(d._implementation_lock_path(),lease_metadata)



@pytest.fixture(scope='module')
def two_candidate_world(native_replay_world):
    """Two actual Native rejected orphans for one current pending task."""
    from dataclasses import replace
    w=native_replay_world;d=w['daemon'];root=w['root']
    branch='implementation/private-second-attempt-1';leaf=w['trees']/'workspace_second'
    _git(root,'worktree','add','-q','-b',branch,str(leaf),w['baseline'])
    (leaf/'out').mkdir();(leaf/'out/task1.py').write_text('VALUE = "second synthetic failed candidate"\n')
    (leaf/'tests').mkdir();(leaf/'tests/test_retained.py').write_text('def test_retained_failure():\n assert False\n')
    _git(leaf,'add','out/task1.py','tests/test_retained.py')
    admitted=d._validate_implementation_patch(leaf,w['task'],baseline_ref=w['baseline'],allow_scope_adjudication=False)
    assert admitted.accepted,d._compact_proposal_validation(admitted)
    _git(leaf,'commit','-qm','Second synthetic retained candidate');head=_git(leaf,'rev-parse','HEAD')
    config=replace(w['config'],worktree_reconciliation_max_merges=2)
    supervisor=runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor)(config)
    key=supervisor._worktree_reconciliation_recovery_key(task_cid=w['identity'].canonical_task_cid,
        baseline_ref=w['baseline'],candidate_commit=head,target_commit=w['baseline'],mode='pre_merge')
    failed=d.reconcile_validated_worktree_candidate(worktree_path=leaf,branch_name=branch,task=w['task'],
        baseline_ref=w['baseline'],candidate_commit=head,recovery_key=key)
    assert failed['validation_result']['proposal_gate']['reason_codes']==['stale_proposal_replay']
    return {**w,'supervisor':supervisor,'second':{'branch':branch,'path':leaf,'head':head,'key':key}}


def test_two_closed_replay_orphans_of_same_task_allow_native_independent_selection(two_candidate_world):
    w=two_candidate_world;s=w['supervisor'];s._complaint_startup_preflight_pending=True
    s._complaint_startup_reconciliation_context=None
    before=asdict(daemon_native.PortalTaskState.load(s.config.state_path))
    refs=[_git(w['root'],'rev-parse',branch) for branch in (w['branch'],w['second']['branch'])]
    result=s.run_once(include_refill=False)
    items=result['worktree_reconciliation']['processed']
    assert len(items)==2 and all(item['merged'] is False for item in items)
    assert all(item['recovery_result']['validation_result']['proposal_gate']['reason_codes']==['stale_proposal_replay'] for item in items)
    assert [_git(w['root'],'rev-parse',branch) for branch in (w['branch'],w['second']['branch'])]==refs
    after=asdict(daemon_native.PortalTaskState.load(s.config.state_path))
    assert all(after[k]==before[k] for k in ('implementation_attempts','implementation_attempts_by_cid','completed_task_ids'))
    w['daemon'].run_once();selected=daemon_native.PortalTaskState.load(s.config.state_path)
    assert selected.active_task_id=='CIMP-SYN-02' and selected.implementation_in_progress is False
    w['batch_result']=result


@pytest.mark.parametrize('damage',['unclosed_known','unclosed_unknown','paid_start','accepted_proposal','missing_second_terminal','unknown_second_item'])
def test_batch_permission_requires_every_exact_scope_closed(two_candidate_world,damage):
    from copy import deepcopy
    from integrations.ipfs_accelerate.startup_rejected_candidate import retained_replay_rejection,_journal
    w=two_candidate_world;s=w['supervisor'];d=w['daemon']
    if 'batch_result' not in w:
        s._complaint_startup_preflight_pending=True;s._complaint_startup_reconciliation_context=None
        w['batch_result']=s.run_once(include_refill=False)
    s._complaint_startup_preflight_pending=True;s._reconciliation_task_context(d)
    maintenance=deepcopy(w['batch_result']);item=maintenance['worktree_reconciliation']['processed'][0]
    if not retained_replay_rejection(s,item,maintenance_result=maintenance):
        from integrations.ipfs_accelerate.startup_rejected_candidate import _proof,_scope
        entries=maintenance['worktree_reconciliation']['processed'];scopes={_scope(entry['recovery_result']) for entry in entries}
        for entry in entries:_proof(s,entry,d,scopes)
        raise AssertionError('batch outer predicate failed')
    raw=d.events_path.read_bytes();third=None
    try:
        rows,_=_journal(d.events_path)
        if damage in {'unclosed_known','unclosed_unknown'}:
            start=next(r for r in reversed(rows) if r.get('type')=='worktree_reconciliation_validation_started')
            payload={k:v for k,v in start.items() if k not in {'type','sequence','event_id','previous_event_id','stream_id','snapshot_id','timestamp'}}
            if damage=='unclosed_unknown':
                payload.update(branch='implementation/private-unclosed',recovery_key='e'*40)
            d._record_event('worktree_reconciliation_validation_started',payload)
        elif damage=='paid_start':
            d._record_event('implementation_started',{'task_id':w['task'].task_id,'attempt':2,
                'branch':'implementation/new-private-paid-context','worktree_path':str(w['leaf']),
                'baseline_ref':w['baseline']})
        elif damage=='accepted_proposal':
            third=w['trees']/'workspace_new_proposal';branch='implementation/private-new-accepted'
            _git(w['root'],'worktree','add','-q','-b',branch,str(third),w['baseline'])
            (third/'out').mkdir();(third/'out/task1.py').write_text('VALUE = "new accepted candidate"\n')
            (third/'tests').mkdir();(third/'tests/test_retained.py').write_text('def test_retained_failure():\n assert False\n')
            _git(third,'add','out/task1.py','tests/test_retained.py')
            accepted=d._validate_implementation_patch(third,w['task'],baseline_ref=w['baseline'],allow_scope_adjudication=False)
            assert accepted.accepted
        elif damage=='missing_second_terminal':
            lines=raw.splitlines(keepends=True)
            seq=max(i for i,line in enumerate(lines) if json.loads(line).get('type')=='worktree_reconciliation_validation_finished')
            d.events_path.write_bytes(b''.join(lines[:seq]))
        else:
            maintenance['worktree_reconciliation']['processed'][1]['recovery_result']['validation_result']['proposal_gate']['reason_codes'].append('path_outside_scope')
        assert retained_replay_rejection(s,item,maintenance_result=maintenance) is False
    finally:
        d.events_path.write_bytes(raw)
        if third is not None:
            _git(w['root'],'worktree','remove','--force',str(third));_git(w['root'],'branch','-D','implementation/private-new-accepted')


def test_actual_unknown_third_orphan_remains_globally_blocking(two_candidate_world):
    from dataclasses import replace
    w=two_candidate_world;root=w['root'];leaf=w['trees']/'workspace_unknown'
    branch='implementation/private-unknown-task'
    _git(root,'worktree','add','-q','-b',branch,str(leaf),w['baseline'])
    (leaf/'unknown.txt').write_text('Synthetic unresolved task provenance.\n')
    _git(leaf,'add','unknown.txt');_git(leaf,'commit','-qm','Synthetic unknown orphan')
    config=replace(w['config'],worktree_reconciliation_max_merges=3)
    s=runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor)(config)
    s._complaint_startup_preflight_pending=True;s._complaint_startup_reconciliation_context=None
    try:
        with pytest.raises(RuntimeError,match='startup candidate recovery remains unresolved'):
            s.run_once(include_refill=False)
        assert leaf.is_dir() and _git(root,'rev-parse',branch)
    finally:
        _git(root,'worktree','remove','--force',str(leaf));_git(root,'branch','-D',branch)


def test_genuine_pending_effect_keeps_completed_batch_blocked(two_candidate_world):
    from integrations.ipfs_accelerate.startup_rejected_candidate import retained_replay_rejection
    w=two_candidate_world;s=w['supervisor'];d=w['daemon']
    s._complaint_startup_preflight_pending=True;s._complaint_startup_reconciliation_context=None
    result=s.run_once(include_refill=False)
    s._complaint_startup_preflight_pending=True;s._reconciliation_task_context(d)
    item=result['worktree_reconciliation']['processed'][0]
    assert retained_replay_rejection(s,item,maintenance_result=result) is True
    pending=d.merge_queue.enqueue(branch_name=w['branch'],task_id=w['task'].task_id,
        canonical_task_id=w['identity'].canonical_task_cid,canonical_task_key=w['identity'].canonical_task_key,
        commit_sha=w['head'],metadata={'synthetic_pending_effect':True},
        target_repository_id=d.merge_target_repository_id,target_branch='main')
    try:
        assert retained_replay_rejection(s,item,maintenance_result=result) is False
    finally:
        # End of this disposable fixture: cancel does not create task-completion
        # authority, unlike completing a synthetic pending merge for cleanup.
        assert d.merge_queue.cancel(pending,reason='Synthetic refusal fixture cleanup') is not None
