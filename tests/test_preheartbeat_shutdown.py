"""Stopped before first heartbeat: real inert parent, explicit synthetic history.

The public stop closes a real private Python process. Docker is the existing
inert transport fixture; no daemon, provider, container, or live campaign runs.
Historical heartbeat fields describe scope only, never current death authority.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import os
import subprocess
import sys
import time

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import improvement_shutdown as shutdown
from tests.test_improvement_container_shutdown import campaign, docker, stamp, _missing_marker_heartbeat

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
_REAL_PROCESS_IDENTITY = runner.process_identity
_REAL_INVENTORY = shutdown._complete_process_inventory


@pytest.fixture
def stopped_before_heartbeat(campaign, docker, monkeypatch, request):
    fixture = campaign
    monkeypatch.setattr(runner, 'process_identity', _REAL_PROCESS_IDENTITY)
    first_ever = getattr(request, 'param', None)
    old = None
    if first_ever is not None:
        for name in ['complaint_intake_supervisor_status.json','complaint_intake_events.jsonl',
                     'complaint_intake_supervisor_events.jsonl']:
            (fixture.state/name).unlink(missing_ok=True)
            if first_ever == 'empty' and name.endswith('.jsonl'):(fixture.state/name).write_bytes(b'')
    else:
        old = _missing_marker_heartbeat(fixture.state, fixture.record, None)
        old.update(status='stopped', supervisor_pid=1073741824, updated_at=stamp(time.time()-5),
            supervisor_pid_alive=False, daemon_pid_alive=False, active_worker_count=0, active_worker_pids=[],
            worker_descendant_count=0, managed_daemon_cleanup={'quiesced':True,'pid':1073741825,
                'pid_path':str(fixture.state/'complaint_intake_managed_daemon.pid'),
                'identity_path':str(fixture.state/'complaint_intake_managed_daemon.identity.json'), 'remaining_pid':None})
        runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json', old)
        (fixture.state/'complaint_intake_supervisor.pid').write_text('1073741824\n')
        (fixture.state/'complaint_intake_supervisor_events.jsonl').write_text(json.dumps({
            'type':'supervisor_signal_shutdown','timestamp':old['updated_at']})+'\n')
    script = fixture.repo / 'scripts/run_complaint_improvement_supervisor.py'
    script.parent.mkdir(parents=True)
    script.write_text('import time\ntime.sleep(30)\n')
    process = subprocess.Popen(fixture.record['argv'], cwd=fixture.repo, start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        identity = runner.process_identity(process.pid)
        assert identity and identity['session'] == identity['process_group'] == process.pid
        record = {**deepcopy(fixture.record), 'identity':identity, 'status':'starting', 'started_at':time.time()}
        runner._atomic_json(fixture.state / 'launcher.json', record)
        starting = (fixture.state / 'launcher.json').read_bytes()
        stopped = runner.stop(fixture.state, timeout=.2)
        process.wait(timeout=3)
        assert stopped['status']=='stopped' and stopped['signalled'] is True and stopped['remaining_pids']==[]
        assert stopped['container_shutdown']['quiesced'] is True and not docker[0].effects
        current = json.loads((fixture.state/'launcher.json').read_text())
        proof = json.loads((fixture.state/shutdown.RECEIPT_NAME).read_text())
        assert proof['launcher_sha256']==hashlib.sha256(starting).hexdigest()
        assert runner._shutdown_verified(current, proof, fixture.repo, fixture.state)
        monkeypatch.setattr(shutdown, '_native_runtime', lambda: pytest.fail('read-only closure invoked Docker'))
        yield SimpleNamespace(**{**vars(fixture), 'record':current}, heartbeat=old, starting=starting,
            context=shutdown._context(fixture.state,current), stop_result=stopped)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)


def _bytes(fixture):
    return {p.name:p.read_bytes() for p in fixture.state.iterdir() if p.is_file()}


def test_normal_public_stop_before_heartbeat_has_fresh_readonly_closure(stopped_before_heartbeat, monkeypatch):
    f=stopped_before_heartbeat; before=_bytes(f); scans=[]
    def inventory(cutoff):
        scans.append(cutoff)
        return _REAL_INVENTORY(cutoff)
    monkeypatch.setattr(shutdown,'_complete_process_inventory',inventory)
    result=shutdown._parent_closed(f.state,f.record,f.context,False)
    assert result['source']=='owned_preheartbeat_stop_and_double_complete_proc_inventory'
    assert result['observations']==2 and result['proc_census_complete'] is True
    assert result['historical_heartbeat_only'] is True
    assert result['signals_sent'] is result['attempt_refunded'] is result['completion_authority'] is False
    assert scans==[f.record['identity']['start_ticks']]*2 and _bytes(f)==before


@pytest.mark.parametrize('stopped_before_heartbeat',['absent','empty'],indirect=True)
def test_first_ever_stopped_launch_without_heartbeat_requires_fresh_closure(stopped_before_heartbeat,monkeypatch):
    f=stopped_before_heartbeat
    assert f.heartbeat is None
    before=_bytes(f);monkeypatch.setattr(shutdown,'_complete_process_inventory',_REAL_INVENTORY)
    result=shutdown._parent_closed(f.state,f.record,f.context,False)
    assert result['historical_heartbeat_only'] is False and result['observations']==2
    assert _bytes(f)==before


@pytest.mark.parametrize('damage',['wrong_receipt_owner','starting_hash','stopped_time','starting_status',
    'wrong_hb_repo','running_hb','newer_hb','current_hb_owner','active_worker','pid_marker','identity_marker',
    'current_supervisor_marker','task_event','supervisor_event','malformed_event','absent_hb_old_event','removed_old_history'])
def test_preheartbeat_closure_refuses_mixed_scope_or_postlaunch_evidence(stopped_before_heartbeat,monkeypatch,damage):
    f=stopped_before_heartbeat;record=deepcopy(f.record);hb=deepcopy(f.heartbeat)
    receipt=json.loads((f.state/shutdown.RECEIPT_NAME).read_text())
    if damage=='wrong_receipt_owner':receipt['owner_token_sha256']='a'*64
    elif damage=='starting_hash':receipt['launcher_sha256']='a'*64
    elif damage=='stopped_time':record['stopped_at']=record['started_at']-1
    elif damage=='starting_status':record['status']='starting'
    elif damage=='wrong_hb_repo':hb['repo_root']='/foreign'
    elif damage=='running_hb':hb['status']='running'
    elif damage=='newer_hb':hb['updated_at']=stamp(record['started_at']+1)
    elif damage=='current_hb_owner':hb['supervisor_pid']=record['identity']['pid']
    elif damage=='active_worker':hb['active_worker_count']=1;hb['active_worker_pids']=[1073741826]
    elif damage=='pid_marker':(f.state/'complaint_intake_managed_daemon.pid').write_text('1073741826\n')
    elif damage=='identity_marker':(f.state/'complaint_intake_managed_daemon.identity.json').write_text('{}')
    elif damage=='current_supervisor_marker':(f.state/'complaint_intake_supervisor.pid').write_text(str(record['identity']['pid'])+'\n')
    elif damage in {'task_event','supervisor_event'}:
        name='complaint_intake_events.jsonl' if damage=='task_event' else 'complaint_intake_supervisor_events.jsonl'
        with (f.state/name).open('a') as out:out.write(json.dumps({'type':'selection_or_maintenance','timestamp':stamp(record['started_at']+.1)})+'\n')
    elif damage=='malformed_event':(f.state/'complaint_intake_events.jsonl').write_text('{\n')
    elif damage=='removed_old_history':(f.state/'complaint_intake_events.jsonl').unlink()
    runner._atomic_json(f.state/'launcher.json',record)
    runner._atomic_json(f.state/shutdown.RECEIPT_NAME,receipt)
    runner._atomic_json(f.state/'complaint_intake_supervisor_status.json',hb)
    if damage=='absent_hb_old_event':
        (f.state/'complaint_intake_supervisor_status.json').unlink()
        (f.state/'complaint_intake_supervisor.pid').unlink()
    monkeypatch.setattr(shutdown,'_complete_process_inventory',lambda cutoff:[])
    before=_bytes(f)
    with pytest.raises((ValueError,OSError)):
        shutdown._parent_closed(f.state,record,shutdown._context(f.state,record),False)
    assert _bytes(f)==before


@pytest.mark.parametrize('damage',['group','session','scoped_cwd','scoped_argv','unreadable_inventory','custody_inode'])
def test_preheartbeat_closure_rechecks_complete_population_and_custody(stopped_before_heartbeat,monkeypatch,damage):
    f=stopped_before_heartbeat;calls=[]
    def inventory(cutoff):
        calls.append(cutoff)
        if damage=='unreadable_inventory':raise ValueError('explicit synthetic unavailable census')
        if damage=='custody_inode':
            if len(calls)==1:
                path=f.state/'container_shutdown.json';raw=path.read_bytes();path.unlink();path.write_bytes(raw);path.chmod(0o600)
            return []
        row={'pid':1073741826,'uid':os.getuid(),'process_group':1073741826,'session':1073741826,
            'start_ticks':cutoff+1,'argv':('/usr/bin/python3',),'cwd':str(f.repo.parent)}
        if damage=='group':row['process_group']=f.record['identity']['pid']
        elif damage=='session':row['session']=f.record['identity']['pid']
        elif damage=='scoped_cwd':row['cwd']=str(f.workspace)
        else:row['argv']=tuple(f.record['argv'])
        return [row]
    monkeypatch.setattr(shutdown,'_complete_process_inventory',inventory)
    with pytest.raises((ValueError,OSError)):
        shutdown._parent_closed(f.state,f.record,f.context,False)


def test_real_live_escaped_campaign_child_prevents_preheartbeat_closure(stopped_before_heartbeat,monkeypatch):
    f=stopped_before_heartbeat
    child=subprocess.Popen([sys.executable,'-I','-B','-c','import time;time.sleep(30)'],cwd=f.workspace,
        start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        monkeypatch.setattr(shutdown,'_complete_process_inventory',_REAL_INVENTORY)
        with pytest.raises(ValueError):shutdown._parent_closed(f.state,f.record,f.context,False)
        assert child.poll() is None
    finally:
        child.terminate();child.wait(timeout=3)
