"""Genuine pool writer interrupted inside a real Git checkout.

Only captured authored private processes are killed, at a Git smudge-filter
barrier before index publication. No index/lock/worktree is hand-edited.
No model, live campaign or real session data is used.
"""
from pathlib import Path
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from copy import deepcopy

import pytest
from integrations.ipfs_accelerate import improvement_runner as runner

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


def _git(root,*args):
    return subprocess.check_output(['git','--no-replace-objects',*args],cwd=root,text=True).strip()


def _bind_fixture_plane(root,campaign,config):
    from integrations.ipfs_accelerate.reconciliation_activity import catalog_path
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    os.environ[runner.ORCHESTRATION_DIR_ENV]=runner.campaign_environment(
        root,state_dir=campaign)[runner.ORCHESTRATION_DIR_ENV]
    target,_=catalog_path(runner,campaign)
    plane.bind_task_state_control_plane(config.state_path,str(target))


def _pool_writer(base):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.supervisor_loop import SupervisorLoop
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.supervisor import worktree_phase_worker_status
    root,campaign,trees=base/'repo',base/'campaign',base/'worktrees'
    spec=root/runner.SPEC_RELATIVE;_,artifacts=runner._campaign_spec(root,spec)
    identity=runner.process_identity(os.getpid());assert identity is not None
    launch={'schema_version':'complaint-improvement-launcher@1','repo_root':str(root),'state_dir':str(campaign),
        'spec_path':str(spec),'board_path':str(root/artifacts.board_relative),'plan_id':runner._requested_plan_id(spec),
        'provider':'grok_cli','model':runner.MODEL,'allow_fallback':False,'identity':identity,'argv':identity['argv'],
        'owner_token':'private-old-pool-owner','started_at':time.time(),'status':'starting',
        'worktree_root':str(trees),'worktree_root_binding':runner._validate_worktree_root(root,campaign,trees),
        'merge_target':'main'}
    runner._atomic_json(campaign/'launcher.json',launch)
    runner._atomic_json(base/'old-launcher.json',launch)
    assert runner.owns_process(launch)
    config=runner._recovery_config(root,campaign,launch)
    _bind_fixture_plane(root,campaign,config)
    supervisor=native.PortalImplementationSupervisor(config)
    # Real Native no-daemon maintenance publication supplies the historic
    # scope/source/birth facts later consumed by the stopped-process census.
    loop=SupervisorLoop(supervisor.build_supervisor_loop_config())
    observed=worktree_phase_worker_status({},os.getpid())
    assert observed['active_worker_count']==0
    loop._last_worker_status=dict(observed)
    loop._write_status('starting')
    supervisor.run_once(include_refill=False)
    daemon=native.PortalImplementationSupervisor._build_worktree_reconciliation_daemon(supervisor)
    daemon.run_once()
    task=daemon._load_tasks()[0];identity=daemon._identity_for_task(task)
    claim_path=daemon._implementation_task_claim_path(task.task_id,canonical_task_cid=identity.canonical_task_cid)
    if not claim_path.exists():
        metadata=daemon._build_implementation_task_claim_metadata(task,1,native.utc_now())
        assert daemon._try_acquire_implementation_task_claim(claim_path,metadata)[0]
    branch=f'implementation/{task.task_id.lower()}-{identity.short_id}-attempt-1-{int(time.time())}'
    provisional=trees/'requested'
    lifecycle=daemon.worktree_lifecycle.begin_preparing(task_id=task.task_id,
        canonical_task_cid=daemon._canonical_ref(task),attempt=daemon._worktree_lifecycle_attempt(task,1),
        lane_id=daemon._worktree_lifecycle_lane_id(),workspace_path=provisional,branch=branch,
        merge_target=daemon._main_branch_name(),state_dir=str(campaign))
    daemon._active_worktree_lifecycle=lifecycle
    assert lifecycle.is_nonterminal
    record={'pid':os.getpid(),'birth':native.read_process_birth(os.getpid()).to_dict(),
        'branch':branch,'task_id':task.task_id,'task_cid':identity.canonical_task_cid,
        'task_key':identity.canonical_task_key,'claim_path':str(claim_path),
        'cache_key':daemon._implementation_worktree_cache_key(),'provisional_path':str(provisional),
        'lifecycle_lease_id':lifecycle.lease_id,'issued_lifecycle':lifecycle.to_dict()}
    (base/'writer.json').write_text(json.dumps(record));(base/'writer.json').chmod(0o600)
    daemon._create_seeded_worktree(provisional,branch,task=task)
    raise AssertionError('The real checkout barrier must interrupt before setup returns.')


def _scenario(base,mode):
    import ctypes
    from integrations.ipfs_accelerate import improvement_plan as compiler
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as daemon_native
    root,campaign,trees=base/'repo',base/'campaign',base/'worktrees'
    # Adopt/reap only this authored process tree, independent of PID1 policy.
    libc=ctypes.CDLL(None,use_errno=True)
    assert libc.prctl(36,1,0,0,0)==0
    for p in (root,campaign,trees):p.mkdir(mode=0o700)
    marker=runner._validate_worktree_root(root,campaign,trees,claim=True)
    _git(root,'init','-q','-b','main');_git(root,'config','user.name','Synthetic interrupted pool')
    _git(root,'config','user.email','synthetic@example.invalid')
    task={'id':'CIMP-SYN-01','goal_id':'goal.synthetic','subgoal_id':'sub.synthetic','title':'Unused private setup',
        'priority':'P0','targets':['artifact.py'],'depends_on':[],'acceptance':['Synthetic unused setup only.'],
        'validation_commands':['true'],'implementation_prompt':'No provider is invoked by this fixture.'}
    spec={'schema_version':'complaint-generator/improvement-spec@1','title':'Synthetic interrupted pool',
        'provider':{'router':'ipfs_accelerate_py.llm_router','provider':'grok_cli','model':'grok-4.7','allow_fallback':False},
        'goals':[{'id':'goal.synthetic','title':'Synthetic','subgoals':[{'id':'sub.synthetic','title':'Synthetic'}]}],
        'tasks':[task],'execution_policy':{'synthetic_only':True},'findings':[]}
    spec_path=root/runner.SPEC_RELATIVE;spec_path.parent.mkdir(parents=True);spec_path.write_text(json.dumps(spec))
    compiler.generate(spec_path,root)
    sdk=Path(native.__file__).resolve().parents[3]
    paths=[str(Path(runner.__file__).resolve().parents[2]),str(sdk),str(sdk.parent/'ipfs_datasets_py'),str(sdk.parent/'ipfs_kit_py')]
    writer=root/'scripts/run_complaint_improvement_supervisor.py';writer.parent.mkdir()
    writer.write_text('import sys\nsys.path[:0]='+repr(paths)+'\n'+
        'from pathlib import Path\nfrom tests.test_startup_initializing_checkout import _pool_writer\n'+
        "if __name__=='__main__':_pool_writer(Path(__file__).resolve().parents[2])\n")
    (root/'.gitattributes').write_text('a_empty.fixture filter=privateempty\nz_pause.fixture filter=privatepause\n')
    (root/'a_empty.fixture').write_text('Synthetic immutable baseline for actual smudge output.\n')
    (root/'z_pause.fixture').write_text('Authored synthetic checkout bytes.\n')
    for i in range(4):(root/f'ordinary{i}.py').write_text(f'VALUE = {i}\n')
    _git(root,'add','.');_git(root,'commit','-qm','Synthetic pool baseline')
    baseline=_git(root,'rev-parse','HEAD')
    ready=base/'filter-ready';filter_script=base/'pause_filter.py'
    filter_script.write_text('import sys,time\nfrom pathlib import Path\nsys.stdin.buffer.read()\n'+
        'Path('+repr(str(ready))+').write_text("ready")\nwhile True:time.sleep(.02)\n')
    _git(root,'config','filter.privatepause.smudge',shlex.quote(sys.executable)+' -I -B '+shlex.quote(str(filter_script)))
    _git(root,'config','filter.privatepause.clean','cat')
    _git(root,'config','filter.privatepause.required','true')
    empty_filter=base/'empty_filter.py'
    empty_filter.write_text('import sys\nsys.stdin.buffer.read()\n'+
        ("sys.stdout.buffer.write(b'NONZERO_SYNTHETIC_TRANSFORM\\n')\n" if mode=='nonzero' else ''))
    _git(root,'config','filter.privateempty.smudge',shlex.quote(sys.executable)+' -I -B '+shlex.quote(str(empty_filter)))
    _git(root,'config','filter.privateempty.clean','cat')
    _git(root,'config','filter.privateempty.required','true')
    with (base/'private-writer.log').open('w') as capture:
        command=[sys.executable,str(writer),'_run','--repo-root',str(root),'--spec',str(spec_path),
            '--state-dir',str(campaign),'--owner-token','private-old-pool-owner','--merge-target','main',
            '--worktree-root',str(trees)]
        process=subprocess.Popen(command,cwd=base,
            env=dict(os.environ),stdout=capture,stderr=subprocess.STDOUT,start_new_session=True)
        until=time.monotonic()+60
        try:
            while not ready.exists() and process.poll() is None and time.monotonic()<until:time.sleep(.02)
            assert ready.exists(),'The real Git filter did not reach the checkout barrier.'
            producer=native.read_process_birth(process.pid)
            assert producer is not None and os.getpgid(process.pid)==os.getsid(process.pid)==process.pid
            assert process.pid!=os.getpgrp()
            from integrations.ipfs_accelerate import startup_initializing_cleanup as cleanup
            live_record=runner._read_json(base/'old-launcher.json')
            assert runner.owns_process(live_record)
            live_metadata=next((trees/'.pool-state').glob('*.json'))
            live_bytes=live_metadata.read_bytes()
            try:cleanup.cleanup_stopped_initializing_checkouts(runner,root,campaign,live_record)
            except ValueError:live_owner_refused=True
            else:live_owner_refused=False
            assert live_owner_refused and runner.owns_process(live_record)
            assert live_metadata.read_bytes()==live_bytes
            # Native engine.run_command intentionally gives Git a separate
            # session. Bind exact descendants by birth+cwd and pidfd instead
            # of assuming the pool owner's process group contains Git.
            members=[row['pid'] for row in native.descendant_processes(process.pid)]
            births={}
            for pid in [process.pid,*members]:
                birth=native.read_process_birth(pid)
                if birth is None:
                    assert pid!=process.pid and not os.path.lexists(Path('/proc')/str(pid))
                    continue
                births[pid]=birth
            members=[pid for pid in members if pid in births]
            descriptors={}
            try:
                for pid,birth in births.items():
                    assert birth is not None and birth.boot_id==producer.boot_id
                    assert birth.start_time_ticks>=producer.start_time_ticks
                    assert (Path('/proc')/str(pid)).stat().st_uid==os.getuid()
                    assert Path(os.readlink(Path('/proc')/str(pid)/'cwd')).is_relative_to(base)
                    descriptors[pid]=os.pidfd_open(pid)
                    assert native.read_process_birth(pid)==birth
                # Kill the waiting pool actor first so it cannot interpret
                # the subsequently killed Git child as an ordinary failure.
                for pid in [process.pid,*members]:
                    try:signal.pidfd_send_signal(descriptors[pid],signal.SIGKILL)
                    except ProcessLookupError:pass
                process.wait(timeout=10)
                for pid in members:
                    until=time.monotonic()+5
                    while time.monotonic()<until and os.path.lexists(Path('/proc')/str(pid)):
                        try:os.waitpid(pid,os.WNOHANG)
                        except ChildProcessError:pass
                        time.sleep(.01)
                    assert not os.path.lexists(Path('/proc')/str(pid)), 'Captured private descendant was not reaped.'
            finally:
                for descriptor in descriptors.values():os.close(descriptor)
            assert native.read_process_birth(producer.pid) is None
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
    states=list((trees/'.pool-state').glob('*.json'));assert len(states)==1
    state=json.loads(states[0].read_text());leaf=Path(state['path'])
    writer_record=json.loads((base/'writer.json').read_text())
    assert state['state']=='initializing' and state['lease_pid']==process.pid==writer_record['pid']
    gitdir=Path(_git(leaf,'rev-parse','--absolute-git-dir'))
    assert not (gitdir/'index').exists() and (gitdir/'index.lock').stat().st_size==0
    assert (leaf/'a_empty.fixture').read_bytes()==(b'NONZERO_SYNTHETIC_TRANSFORM\n' if mode=='nonzero' else b'')
    locked_raw=(gitdir/'locked').read_bytes();locked_info=(gitdir/'locked').lstat()
    assert locked_raw==b'initializing\n'
    assert _git(leaf,'rev-parse','HEAD')==state['base_commit']==baseline
    assert _git(leaf,'symbolic-ref','--short','HEAD')==writer_record['branch']
    assert not _git(root,'for-each-ref','--format=%(refname)','refs/heads/rescue/')
    (root/'advanced.py').write_text('INDEPENDENT_MAIN_ADVANCE = True\n')
    _git(root,'add','advanced.py');_git(root,'commit','-qm','Independent private target advance')
    assert _git(root,'rev-parse','HEAD')!=baseline
    identity=runner.process_identity(os.getpid());assert identity is not None
    launch={'schema_version':'complaint-improvement-launcher@1','repo_root':str(root),'state_dir':str(campaign),
        'spec_path':str(spec_path),'board_path':str(root/compiler.BOARD_RELATIVE),'plan_id':runner._requested_plan_id(spec_path),
        'provider':'grok_cli','model':runner.MODEL,'allow_fallback':False,'identity':identity,'argv':identity['argv'],
        'owner_token':'private-pool-parent','started_at':time.time()-120,'status':'starting',
        'worktree_root':str(trees),'worktree_root_binding':marker,'merge_target':'main'}
    runner._atomic_json(campaign/'launcher.json',launch)
    assert runner.owns_process(launch)
    config=runner._recovery_config(root,campaign,launch)
    # Match the actual Host-confined Native catalog and public binding.
    # No projection payload, selection event or observer result is seeded.
    _bind_fixture_plane(root,campaign,config)
    supervisor=runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor)(config)
    before_claim=Path(writer_record['claim_path']).read_bytes()
    before_cp=vars(daemon_native.PortalTaskState.load(config.state_path))
    assert before_cp['active_task_id']==writer_record['task_id']
    assert before_cp['active_task_cid']==writer_record['task_cid']
    before_refs=_git(root,'for-each-ref','--format=%(refname):%(objectname)')
    before_head=_git(root,'rev-parse','HEAD')
    reader=native.PortalImplementationSupervisor._build_worktree_reconciliation_daemon(supervisor)
    before_lifecycle=reader.worktree_lifecycle.load_workspace(writer_record['provisional_path'])
    # The actual Native constructor itself fences dead PREPARING owners.
    # Preserve that genuine transition instead of requiring stale authority.
    issued=writer_record['issued_lifecycle']
    assert issued['state']=='preparing' and issued['lease_id']==writer_record['lifecycle_lease_id']
    assert issued['owner']==writer_record['birth']
    assert before_lifecycle is not None and before_lifecycle.is_terminal
    assert before_lifecycle.terminal_reason=='controlled_restart_dead_owner'
    assert before_lifecycle.fence==issued['fence']+1
    assert before_lifecycle.owner.pid==os.getpid()
    assert all(before_lifecycle.to_dict()[key]==issued[key] for key in (
        'record_id','task_id','canonical_task_cid','attempt','lane_id','workspace_path','branch','repo_root','state_dir'))
    assert reader.worktree_lifecycle.load_task_attempt(canonical_task_cid=writer_record['task_cid'],
        task_id=writer_record['task_id'],attempt=issued['attempt'])==before_lifecycle
    result={'genuine_initial_shape':True,'head_before':baseline,'target_advanced':True,
        'pool_writer_dead':True,'mode':mode,'live_owner_refused':live_owner_refused}
    if mode=='nonzero':
        from integrations.ipfs_accelerate import startup_initializing_cleanup as cleanup
        try:cleanup._inventory(reader,root,leaf,baseline)
        except ValueError:result['nonzero_transform_refused']=True
        else:result['nonzero_transform_refused']=False
        result['unused_checkout_preserved']=leaf.exists() and states[0].exists() and gitdir.exists()
    elif mode=='primitive':
        daemon=native.PortalImplementationSupervisor._build_worktree_reconciliation_daemon(supervisor)
        assert daemon._implementation_worktree_cache_key()==writer_record['cache_key']
        pool=daemon.worktree_pool;assert pool is not None
        path=supervisor._repo_merge_lock_path()
        lease,reason,_=supervisor._acquire_supervisor_checkout_lease(path,
            supervisor._supervisor_checkout_lock_metadata(operation='synthetic_stale_initializing_proof'))
        assert lease is not None,reason
        try:
            def authorize(path,branch_hint,phase):
                assert path==leaf
                return daemon._authorize_pooled_worktree_reuse(path,writer_record['branch'],phase)
            lock,reason=pool._try_claim_authorized(state,authorize_reuse=authorize)
            assert lock is not None,reason
            assert pool._read_state(state['lease_token'])==state
            current=(gitdir/'locked').lstat()
            assert (current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns,current.st_ctime_ns)==(
                locked_info.st_dev,locked_info.st_ino,locked_info.st_size,locked_info.st_mtime_ns,locked_info.st_ctime_ns)
            assert (gitdir/'locked').read_bytes()==locked_raw and native.read_process_birth(process.pid) is None
            unlocked=pool._run(('git','worktree','unlock',str(leaf)),cwd=root)
            assert unlocked.ok
            pool._reject_and_discard(state,reason='stale_initializing_entry',lock_path=lock)
        finally:supervisor._release_supervisor_checkout_lease(lease,operation='synthetic_stale_initializing_proof')
        result['native_cleanup_removed']=not leaf.exists() and not states[0].exists() and not gitdir.exists()
        result['registration_absent']=str(leaf) not in _git(root,'worktree','list','--porcelain')
        result['branch_retained']=_git(root,'rev-parse',writer_record['branch'])==baseline
    elif mode in ('valid_index','started_event','quarantine'):
        from integrations.ipfs_accelerate import startup_initializing_cleanup as cleanup
        old=_stopped_fixture_record(base,campaign)
        assert cleanup._proof(runner,supervisor,reader,reader.worktree_pool,old,states[0])['path']==leaf
        if mode=='valid_index':
            alternate=base/'actual-git-index'
            subprocess.run(['git','--no-replace-objects','read-tree',baseline],cwd=leaf,
                env={**os.environ,'GIT_INDEX_FILE':str(alternate)},check=True,capture_output=True)
            # Negative-only injection of a genuinely Git-produced index.
            # It is retained; no index is deleted to manufacture a positive.
            os.replace(alternate,gitdir/'index')
            assert (gitdir/'index').stat().st_size>0
        elif mode=='started_event':
            reader._record_event('implementation_started',{'task_id':writer_record['task_id'],
                'attempt':1,'branch':writer_record['branch'],'worktree_path':str(leaf),
                'synthetic_no_model':True,'provider_dispatched':False})
        else:
            captured=reader.worktree_lifecycle.begin_preparing(task_id=writer_record['task_id'],
                canonical_task_cid=writer_record['task_cid'],attempt=2,
                lane_id=reader._worktree_lifecycle_lane_id(),workspace_path=leaf,
                branch=writer_record['branch'],merge_target='main',state_dir=str(campaign))
            receipt=reader.worktree_lifecycle.quarantine_current_owner(captured,
                fence_authority={'schema':'synthetic-quarantine-negative@1','provider_dispatched':False},
                reason='synthetic_retained_candidate_negative')
            assert receipt['cleanup_allowed'] is False
        before_damage_claim=Path(writer_record['claim_path']).read_bytes()
        before_damage_state=states[0].read_bytes()
        before_damage_body=deepcopy(runner._validation_activity_snapshot(campaign)['body'])
        try:cleanup.cleanup_stopped_initializing_checkouts(runner,root,campaign,old)
        except (OSError,ValueError,RuntimeError):result['terminal_damage_refused']=True
        else:result['terminal_damage_refused']=False
        assert result['terminal_damage_refused']
        assert Path(writer_record['claim_path']).read_bytes()==before_damage_claim
        assert states[0].read_bytes()==before_damage_state
        assert runner._validation_activity_snapshot(campaign)['body']==before_damage_body
        result['unused_checkout_preserved']=leaf.exists() and states[0].exists() and gitdir.exists()
    else:
        from integrations.ipfs_accelerate import improvement_shutdown as shutdown
        old=_stopped_fixture_record(base,campaign)
        result['genuine_process_closure']=True
        from integrations.ipfs_accelerate import startup_initializing_cleanup as cleanup
        if mode=='host':
            result['matrix']=_refusal_matrix(cleanup,supervisor,reader,old,states[0],state,
                leaf,gitdir,writer_record,root,campaign)
        # A genuine prepared intent plus exact Git unlock models an interrupted
        # owned cleanup. Public start must resume it without a new authority.
        lease,reason,_=supervisor._acquire_supervisor_checkout_lease(supervisor._repo_merge_lock_path(),
            supervisor._supervisor_checkout_lock_metadata(operation='synthetic_prepared_cleanup'))
        assert lease is not None,reason
        lock=None
        try:
            proof=cleanup._proof(runner,supervisor,reader,reader.worktree_pool,old,states[0])
            def authorize(path,branch_hint,phase):
                assert path==leaf
                return reader._authorize_pooled_worktree_reuse(path,writer_record['branch'],phase)
            lock,reason=reader.worktree_pool._try_claim_authorized(state,authorize_reuse=authorize)
            assert lock is not None,reason
            proof=cleanup._proof(runner,supervisor,reader,reader.worktree_pool,old,states[0])
            cleanup._operation(proof['operation_path'],{**proof['authority'],'phase':'prepared'})
            reader._run_git(['worktree','unlock',str(leaf)],cwd=root)
            assert not (gitdir/'locked').exists()
            cleanup._proof(runner,supervisor,reader,reader.worktree_pool,old,states[0])
            result['prepared_unlock_replay']=True
        finally:
            if lock is not None:reader.worktree_pool._remove_lock(lock)
            assert supervisor._release_supervisor_checkout_lease(lease,operation='synthetic_prepared_cleanup')
        # Actual read-only Docker inventory for this unique private scope.
        # There is no implementation start to authorize a container effect.
        closed=shutdown.close_campaign_containers(campaign,old,parent_quiesced=False,remove_stopped=False)
        assert closed['quiesced'] is True,closed.get('reason')
        assert closed['containers']==[]
        assert not runner._auth_material_present(os.environ)
        if mode=='release_cas':
            from unittest.mock import patch
            from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import (
                CheckoutMutationLease,release_checkout_mutation_lease,serialized_lock_update)
            original_release=native.PortalImplementationSupervisor._release_supervisor_checkout_lease
            adversary={}
            def replace_then_release(subject,captured,*,operation):
                if operation!='discard_interrupted_pool_initialization':
                    return original_release(subject,captured,operation=operation)
                metadata=subject._supervisor_checkout_lock_metadata(operation='synthetic_replacement_owner')
                assert metadata['lease_id']!=captured.lease_id
                with serialized_lock_update(captured.lock_path):
                    native.write_json_atomic(captured.lock_path,metadata)
                info=captured.lock_path.lstat()
                adversary['lease']=CheckoutMutationLease(captured.lock_path,metadata,info.st_dev,info.st_ino)
                adversary['raw']=captured.lock_path.read_bytes()
                adversary['actual_release']=original_release(subject,captured,operation=operation)
                assert adversary['actual_release'] is False
                assert captured.lock_path.read_bytes()==adversary['raw']
                return adversary['actual_release']
            # Negative-only custody race. The original Native release runs;
            # no guard is stubbed and no synthetic False result is returned.
            with patch.object(native.PortalImplementationSupervisor,'_release_supervisor_checkout_lease',replace_then_release):
                output=runner.start(root,spec_path,campaign,worktree_root=trees)
            assert output.get('reason')=='initializing_checkout_cleanup_unverified',output
            replacement=adversary['lease']
            result['real_release_cas_refused']=adversary['actual_release'] is False
            result['replacement_preserved']=replacement.lock_path.read_bytes()==adversary['raw']
            assert output.get('execution_started') is False
            # Retire only this authored current-owner replacement using the
            # exact Native metadata/device/inode primitive after observation.
            assert release_checkout_mutation_lease(replacement,require_exact_metadata=True)
        else:
            output=runner.start(root,spec_path,campaign,worktree_root=trees)
        result['start_status']=output['status']
        assert output['status']=='not_ready', 'Private empty auth must never dispatch a provider.'
        result['native_cleanup_removed']=not leaf.exists() and not states[0].exists() and not gitdir.exists()
        result['registration_absent']=str(leaf) not in _git(root,'worktree','list','--porcelain')
        result['no_synthetic_rescue']=not _git(root,'for-each-ref','--format=%(refname)','refs/heads/rescue/')
    current=daemon_native.PortalTaskState.load(config.state_path)
    result['paid_attempts']=current.implementation_attempts
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.current_incident_adjudication import _event_rows
    rows=_event_rows((campaign/(runner.STATE_PREFIX+'_events.jsonl')).read_bytes())
    result['no_implementation_start']=not any(row.get('type')=='implementation_started' for row in rows)
    result['claim_unchanged']=Path(writer_record['claim_path']).read_bytes()==before_claim
    result['cp_unchanged']=vars(current)==before_cp
    result['target_unchanged']=_git(root,'rev-parse','HEAD')==before_head and _git(root,'for-each-ref','--format=%(refname):%(objectname)')==before_refs
    result['source_clean']=not _git(root,'status','--porcelain','--untracked-files=normal')
    after_lifecycle=reader.worktree_lifecycle.load_workspace(writer_record['provisional_path'])
    result['native_lifecycle_retired']=after_lifecycle is not None and not after_lifecycle.is_nonterminal
    return result


def _stopped_fixture_record(base,campaign):
    from integrations.ipfs_accelerate import improvement_shutdown as shutdown
    old=runner._read_json(base/'old-launcher.json')
    assert runner.process_identity(old['identity']['pid']) is None
    # Observed private process death alone is never the closure authority.
    old={**old,'status':'stopped'};runner._atomic_json(campaign/'launcher.json',old)
    context=shutdown._context(campaign,old)
    closure=shutdown._parent_closed(campaign,old,context,False)
    assert closure['proc_census_complete'] is True and closure['observations']==2
    assert closure['recorded_pids_absent'] is True and closure['matching_processes']==0
    return old


def _refusal_matrix(cleanup,supervisor,daemon,old,metadata,state,leaf,gitdir,writer,root,campaign):
    """One actual stopped world; only negative data/custody changes are authored."""
    pool=daemon.worktree_pool
    assert cleanup._proof(runner,supervisor,daemon,pool,old,metadata)['path']==leaf
    result={}
    def snapshot():
        return (metadata.read_bytes(),Path(writer['claim_path']).read_bytes(),
            (gitdir/'index.lock').read_bytes(),(gitdir/'locked').read_bytes(),
            _git(root,'for-each-ref','--format=%(refname):%(objectname)'),
            deepcopy(runner._validation_activity_snapshot(campaign)['body']))
    for damage in ('extra_output','modified_source','nonempty_index_lock','manual_git_lock',
                   'manual_hold','foreign_scope','live_pool_lock','live_lifecycle'):
        assert cleanup._proof(runner,supervisor,daemon,pool,old,metadata)['path']==leaf
        changed=None;original=None;claimed=None;live=None
        try:
            if damage=='extra_output':
                changed=leaf/'artifact.py';changed.write_text('MANUAL_CANDIDATE_MUST_SURVIVE = True\n')
            elif damage=='modified_source':
                changed=leaf/'ordinary0.py';original=changed.read_bytes();changed.write_bytes(original+b'# retained manual correction\n')
            elif damage=='nonempty_index_lock':
                changed=gitdir/'index.lock';original=changed.read_bytes();changed.write_bytes(b'unknown lock payload')
            elif damage=='manual_git_lock':
                changed=gitdir/'locked';original=changed.read_bytes();changed.write_bytes(b'operator maintenance hold\n')
            elif damage=='manual_hold':
                changed=campaign/'watchdog/HOLD';changed.parent.mkdir(exist_ok=True);changed.write_text('Private explicit hold\n')
            elif damage=='foreign_scope':
                pool._write_state({**state,'repo_root':str(root.parent/'different_repository')})
            elif damage=='live_pool_lock':
                claimed=pool._try_claim(state);assert claimed is not None
            else:
                live=daemon.worktree_lifecycle.begin_preparing(task_id=writer['task_id'],
                    canonical_task_cid=writer['task_cid'],attempt=2,lane_id=daemon._worktree_lifecycle_lane_id(),
                    workspace_path=pool.worktree_root/'live_provisional',branch=writer['branch'],
                    merge_target='main',state_dir=str(campaign))
            before=snapshot()
            try:cleanup.cleanup_stopped_initializing_checkouts(runner,root,campaign,old)
            except (OSError,ValueError,RuntimeError):result[damage]=True
            else:result[damage]=False
            assert result[damage] and leaf.exists() and metadata.exists() and gitdir.exists(),damage
            assert snapshot()==before,damage
        finally:
            if live is not None:
                assert daemon._finalize_exact_worktree_lifecycle(live,reason='synthetic_live_fence_probe')['finalized']
            if claimed is not None:pool._remove_lock(claimed)
            if damage=='foreign_scope':pool._write_state(state)
            if changed is not None:
                if original is None:changed.unlink()
                else:changed.write_bytes(original)
    return result


def _run_scenario(base,mode):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as runtime
    sdk=Path(native.__file__).resolve().parents[3]
    paths=[str(Path(runner.__file__).resolve().parents[2]),str(sdk),str(sdk.parent/'ipfs_datasets_py'),str(sdk.parent/'ipfs_kit_py')]
    program=base/'parent.py';output=base/'closed-result.json'
    program.write_text('import sys\nsys.path[:0]='+repr(paths)+'\n'+
        'from pathlib import Path\nimport json\nfrom tests.test_startup_initializing_checkout import _scenario\n'+
        "if __name__=='__main__':Path(sys.argv[-1]).write_text(json.dumps(_scenario(Path(sys.argv[-3]),sys.argv[-2])))\n")
    with (base/'private-parent.log').open('w') as capture:
        result=runtime.run_process_group_stream([sys.executable,'-I','-B',str(program),'_run','--owner-token',
            'private-pool-parent','--worktree-root',str(base/'worktrees'),str(base),mode,str(output)],
            cwd=base,stdout=capture,env=dict(os.environ),inherit_environment=False,timeout_seconds=180)
    assert result.returncode==0,'Inspect private-parent.log for this authored fixture.'
    return json.loads(output.read_text())


def test_actual_pool_stale_initializing_primitive_removes_only_unused_checkout(tmp_path):
    result=_run_scenario(tmp_path,'primitive')
    assert result['genuine_initial_shape'] and result['pool_writer_dead']
    assert result['native_cleanup_removed'] and result['branch_retained']
    assert result['registration_absent'] and result['claim_unchanged'] and result['cp_unchanged']
    assert result['target_unchanged'] and result['source_clean']
    assert result['native_lifecycle_retired']
    assert result['paid_attempts']=={} and result['no_implementation_start']


@pytest.fixture(scope='module')
def host_result(tmp_path_factory):
    return _run_scenario(tmp_path_factory.mktemp('actual_stopped_startup'),'host')


def test_actual_startup_never_rescues_a_half_initialized_git_index(host_result):
    result=host_result
    assert result['genuine_initial_shape'] and result['pool_writer_dead']
    assert result['genuine_process_closure'] and result['start_status']=='not_ready',result
    assert result['native_cleanup_removed'] and result['registration_absent'] and result['no_synthetic_rescue'],result
    assert result['claim_unchanged'] and result['cp_unchanged'] and result['target_unchanged'] and result['source_clean']
    assert result['native_lifecycle_retired']
    assert result['paid_attempts']=={} and result['no_implementation_start']


@pytest.mark.parametrize('damage',['extra_output','modified_source','nonempty_index_lock','manual_git_lock',
    'manual_hold','foreign_scope','live_pool_lock','live_lifecycle'])
def test_actual_stopped_initializer_refuses_unsafe_scope_without_effect(host_result,damage):
    assert host_result['matrix'][damage]


def test_actual_prepared_unlock_is_resumed_by_public_start(host_result):
    assert host_result['prepared_unlock_replay'] and host_result['native_cleanup_removed']


def test_actual_live_pool_writer_cannot_be_cleaned(host_result):
    assert host_result['live_owner_refused']


def test_real_nonzero_git_smudge_output_is_retained(tmp_path):
    result=_run_scenario(tmp_path,'nonzero')
    assert result['genuine_initial_shape'] and result['nonzero_transform_refused']
    assert result['unused_checkout_preserved'] and result['claim_unchanged'] and result['cp_unchanged']
    assert result['target_unchanged'] and result['source_clean']


@pytest.mark.parametrize('damage',['valid_index','started_event','quarantine'])
def test_actual_terminal_safety_fence_retains_the_interrupted_checkout(tmp_path,damage):
    result=_run_scenario(tmp_path,damage)
    assert result['genuine_initial_shape'] and result['terminal_damage_refused']
    assert result['unused_checkout_preserved'] and result['claim_unchanged'] and result['cp_unchanged']
    assert result['target_unchanged'] and result['source_clean'] and result['paid_attempts']=={}


def test_actual_native_release_cas_refusal_blocks_public_start(tmp_path):
    result=_run_scenario(tmp_path,'release_cas')
    assert result['real_release_cas_refused'] and result['replacement_preserved']
    assert result['native_cleanup_removed'] and result['registration_absent']
    assert result['claim_unchanged'] and result['cp_unchanged'] and result['target_unchanged']
    assert result['paid_attempts']=={} and result['no_implementation_start']
