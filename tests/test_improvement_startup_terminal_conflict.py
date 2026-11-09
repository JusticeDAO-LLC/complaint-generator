"""Real Git preflight, Native identity/status, and authenticated rescue history.

All histories are synthetic private fixtures written by the Native journal
producer. No provider, production completion, or lifecycle API is invoked.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as daemon_native
from ipfs_accelerate_py.agent_supervisor.task_sources.persistent_task_queue import PersistentTaskQueue

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _world(tmp_path, monkeypatch, damage, *, linked_target=False):
    import subprocess
    root, worktrees, state = (tmp_path / n for n in ('repo','worktrees','state'))
    for p in (root,worktrees,state):p.mkdir(mode=0o700)
    monkeypatch.setenv('IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR',str(state/'control-plane'))
    def git(*args,cwd=None):
        return subprocess.run(['git',*args],cwd=cwd or root,check=True,capture_output=True,text=True).stdout.strip()
    git('init','-q','-b','main');git('config','user.name','Synthetic startup');git('config','user.email','synthetic@example.invalid')
    board=root/'board.md'; board.write_text('# Synthetic\n\n## CIMP-GUI-30 Old failed candidate\n\n- Status: ready\n- Completion: manual\n- Priority: P1\n- Track: ops\n- Outputs: out/task.py\n- Acceptance: Synthetic check.\n')
    (root/'out').mkdir();(root/'out/task.py').write_text('value = 0\n');git('add','.');git('commit','-qm','baseline');baseline=git('rev-parse','HEAD')
    if linked_target:
        git('checkout','-q','--detach',baseline)
        linked=tmp_path/'linked-target';git('worktree','add','-q',str(linked),'main')
        root,board=linked,linked/'board.md'
    daemon=object.__new__(daemon_native.PortalImplementationDaemon)
    daemon.task_source=None;daemon.todo_path=board;daemon.task_header_prefix='CIMP-';daemon.task_queue=PersistentTaskQueue();daemon.repo_root=root;daemon.implement=False
    task=daemon._load_tasks()[0];identity=daemon._identity_for_task(task)
    binding={'canonical_task_cid':identity.canonical_task_cid,'canonical_task_key':identity.canonical_task_key,'board_namespace':identity.board_namespace}
    original='implementation/cimp-gui-30-private-old-attempt-1';leaf=worktrees/'workspace_retained'
    git('worktree','add','-q','-b',original,str(leaf),baseline)
    (leaf/'out/task.py').write_text('value = 1\n')
    config=native.PortalSupervisorConfig(todo_path=board,state_path=state/'state.json',strategy_path=state/'strategy.json',events_path=state/'supervisor_events.jsonl',state_dir=state,repo_root=root,state_prefix='synthetic',task_prefix='CIMP-',worktree_root=worktrees,merge_target_branch='main',worktree_reconciliation_enabled=True,worktree_reconciliation_preflight_enabled=True,worktree_scan_cache_enabled=False,worktree_reconciliation_max_merges=1)
    seen,dispatched=[],[]
    class Startup(native.PortalImplementationSupervisor):
        def _build_worktree_reconciliation_daemon(self):return daemon
        def run_once(self,*,include_refill=True):
            result=self.reconcile_backlogged_worktrees();seen.append(result);return {'worktree_reconciliation':result}
        def _run_forever_loop(self):self.run_once(include_refill=False);dispatched.append(True)
    supervisor=runner._validation_aware_supervisor_class(Startup)(config)
    rescue=supervisor._rescue_dirty_worktree(leaf,branch=original,head=baseline,target_ref='main',status_lines=supervisor._git_status_short(leaf),reason='stale_active_execution_auto_rescue')
    assert rescue['preserved'] is True
    branch=rescue['rescue_branch'];candidate=git('rev-parse','HEAD',cwd=leaf)
    # A different later attempt really merges through Git. Its status/history
    # fixtures are inputs to the real Native current-board reader, not a guard mock.
    git('checkout','-qb','implementation/winning-attempt-2',baseline)
    (root/'out/task.py').write_text('value = 2\n');git('add','out/task.py');git('commit','-qm','winning candidate');winner=git('rev-parse','HEAD')
    git('checkout','-q','main');base=git('rev-parse','HEAD');git('merge','--no-ff','-qm','actual integration',winner);integrated=git('rev-parse','HEAD')
    board.write_text(board.read_text().replace('Status: ready','Status: completed'));git('add','board.md');git('commit','-qm','synthetic completed board fixture')
    events=state/'synthetic_events.jsonl'
    start={'task_id':task.task_id,'branch':original,'baseline_ref':baseline,'attempt':1,**binding}
    finish={'task_id':task.task_id,'branch':'implementation/winning-attempt-2','attempt':2,**binding,'returncode':0,'implementation_commit':winner,'validation_result':{'passed':True,'returncode':0},'merge_result':{'attempted':True,'merged':True,'returncode':0,'target_branch':'main','implementation_commit':winner,'merge_commit':integrated,'integration_base_commit':base,'canonical_task_cid':identity.canonical_task_cid,'canonical_task_key':identity.canonical_task_key,'completion_task_cids':{task.task_id:identity.canonical_task_cid},'integration_commit_proof':{'passed':True,'exact_two_parent_merge':True,'implementation_commit':winner,'integration_base_commit':base,'integration_commit':integrated,'integration_ref':integrated,'target_branch':'main'}}}
    if damage=='wrong_cid':start['canonical_task_cid']='b'+'a'*58
    if damage=='wrong_key':finish['canonical_task_key']='task/v1/'+'f'*64
    if damage=='unfinished':board.write_text(board.read_text().replace('Status: completed','Status: ready'))
    if damage=='changed_definition':board.write_text(board.read_text().replace('out/task.py','out/changed.py'))
    if damage!='no_start':native.append_jsonl_event(events,'implementation_started',start)
    if damage!='no_winner':native.append_jsonl_event(events,'implementation_finished',finish)
    if damage=='nonintegrated_winner':git('checkout','-q','-b','unrelated-head',baseline)
    if damage=='tampered_rescue':
        rows=config.events_path.read_text().splitlines();record=json.loads(rows[-1]);record['rescue_commit']='f'*40;rows[-1]=json.dumps(record);config.events_path.write_text('\n'.join(rows)+'\n')
    daemon._run_git=lambda args,**kwargs:subprocess.run(['git',*args],cwd=kwargs.get('cwd',root),capture_output=True,text=True)
    return SimpleNamespace(root=root,leaf=leaf,branch=branch,candidate=candidate,board=board,state=state,supervisor=supervisor,daemon=daemon,seen=seen,dispatched=dispatched,git=git)


@pytest.mark.parametrize('damage',[None,'wrong_cid','wrong_key','unfinished','changed_definition','no_start','no_winner','nonintegrated_winner','tampered_rescue'])
def test_actual_preflight_conflict_only_completed_attested_task_is_nonblocking(tmp_path,monkeypatch,damage):
    w=_world(tmp_path,monkeypatch,damage)
    before={p.relative_to(w.state):p.read_bytes() for p in (w.state/'state.json',w.state/'strategy.json') if p.is_file()}
    queue_before=dict(w.daemon.task_queue.__dict__)
    if damage is None:
        w.supervisor._run_forever_loop()
        assert w.dispatched==[True]
    elif damage=='tampered_rescue':
        from ipfs_accelerate_py.agent_supervisor.control.control_contracts import CursorReplayError
        with pytest.raises(CursorReplayError,match='non-canonical event_id'):w.supervisor._run_forever_loop()
        assert w.dispatched==[]
        return
    else:
        with pytest.raises(RuntimeError,match='candidate recovery remains unresolved'):w.supervisor._run_forever_loop()
        assert w.dispatched==[]
    row=w.seen[0]['processed'][0]
    assert row['merge_result']['reason']=='preflight_merge_conflict'
    assert row['merge_result']['attempted'] is False and row['merged'] is False
    assert w.leaf.exists() and w.git('rev-parse',w.branch)==w.candidate
    assert (w.leaf/'out/task.py').read_text()=='value = 1\n'
    assert w.daemon.task_queue.__dict__==queue_before
    for p,raw in before.items():assert (w.state/p).read_bytes()==raw


def test_completed_conflict_recognition_keeps_linked_target_git_custody(tmp_path, monkeypatch):
    w = _world(tmp_path, monkeypatch, None, linked_target=True)
    refs = w.git('show-ref')
    w.supervisor._run_forever_loop()
    assert w.dispatched == [True]
    assert w.seen[0]['processed'][0]['merge_result']['reason'] == 'preflight_merge_conflict'
    assert w.git('show-ref') == refs and w.leaf.is_dir()


def test_foreign_repository_at_registered_rescue_path_is_not_terminal_skip_authority(tmp_path, monkeypatch):
    import subprocess
    w = _world(tmp_path, monkeypatch, None)
    retained = w.leaf.with_name('retained-original')
    w.leaf.rename(retained)
    subprocess.run(['git', 'clone', '--quiet', '--no-hardlinks', str(w.root), str(w.leaf)], check=True)
    w.git('checkout', '-q', '-b', w.branch, w.candidate, cwd=w.leaf)
    assert w.git('rev-parse', 'HEAD', cwd=w.leaf) == w.candidate
    refs, candidate = w.git('show-ref'), (w.leaf/'out/task.py').read_bytes()
    with pytest.raises(RuntimeError, match='candidate recovery remains unresolved'):
        w.supervisor._run_forever_loop()
    assert w.dispatched == [] and retained.is_dir()
    assert w.git('show-ref') == refs and (w.leaf/'out/task.py').read_bytes() == candidate
