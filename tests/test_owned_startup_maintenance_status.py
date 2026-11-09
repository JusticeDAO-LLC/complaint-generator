"""Private inert owner, actual Native maintenance writer and real status reader.

The timestamps describe an authored long startup; no provider, recovery,
completion, public campaign or lifecycle operation is invoked.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from copy import deepcopy

import pytest
from integrations.ipfs_accelerate import improvement_runner as runner

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _owned_main(base):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as daemon
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.supervisor_activity import SupervisorMaintenanceWindow
    from integrations.ipfs_accelerate.reconciliation_activity import catalog_path
    root = Path(runner.__file__).resolve().parents[2]
    sdk = Path(native.__file__).resolve().parents[3]
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=sdk,text=True).strip() == subprocess.check_output(
        ['git','rev-parse','HEAD:external/ipfs_accelerate_py'],cwd=root,text=True).strip()
    assert Path(native.PortalImplementationSupervisor._write_supervisor_maintenance_status.__code__.co_filename).resolve() == Path(native.__file__).resolve()
    campaign = base/'campaign'; campaign.mkdir(mode=0o700)
    spec = root/'docs/task_boards/complaint_gui_collaboration_spec.json'
    _, artifacts = runner._campaign_spec(root,spec)
    config = native.PortalSupervisorConfig(todo_path=root/artifacts.board_relative,
        state_path=campaign/(runner.STATE_PREFIX+'_task_state.json'),
        strategy_path=campaign/(runner.STATE_PREFIX+'_strategy.json'),
        events_path=campaign/(runner.STATE_PREFIX+'_supervisor_events.jsonl'),
        state_dir=campaign,repo_root=root,state_prefix=runner.STATE_PREFIX,
        task_prefix=runner.TASK_PREFIX,board_namespace=artifacts.board_namespace,
        implementation_timeout=900,stale_seconds=180,check_interval=1,implement=False)
    supervisor = native.PortalImplementationSupervisor(config)
    target,_ = catalog_path(runner,campaign)
    plane.bind_task_state_control_plane(config.state_path,str(target))
    state = daemon.PortalTaskState()
    stamp = lambda seconds: datetime.fromtimestamp(seconds,timezone.utc).isoformat()
    now = time.time(); state.heartbeat_at=state.last_progress_at=stamp(now)
    state.save(config.state_path)
    identity = runner.process_identity(os.getpid())
    assert identity and identity['pid']==identity['session']==identity['process_group']
    launcher = dict(schema_version='complaint-improvement-launcher@1',repo_root=str(root),state_dir=str(campaign),
        spec_path=str(spec),board_path=str(config.todo_path),plan_id=runner._requested_plan_id(spec),
        provider='grok_cli',model=runner.MODEL,allow_fallback=False,identity=identity,argv=identity['argv'],
        status='starting',owner_token='private-startup-fixture',started_at=now-140)
    runner._atomic_json(campaign/'launcher.json',launcher)
    started = stamp(now-120)
    window = SupervisorMaintenanceWindow.begin(started_at=started,timeout_seconds=900)
    observations = {}
    for phase in ('running','completed'):
        supervisor._write_supervisor_maintenance_status('run_once',status=phase,started_at=started,maintenance_window=window)
        before={str(p.name):p.read_bytes() for p in campaign.glob('*.json')}
        value=runner.status(root,spec,campaign)
        observations[phase]={key:value.get(key) for key in ('status','healthy','owned_process_alive','native_read_errors',
            'progress_verified','provider_progress_verified','validation_activity_verified','startup_activity_verified','startup_activity_evidence')}
        assert before=={str(p.name):p.read_bytes() for p in campaign.glob('*.json')}, 'Status must remain read-only.'
    from integrations.ipfs_accelerate.startup_maintenance_activity import observe
    heartbeat_path=campaign/(runner.STATE_PREFIX+'_supervisor_status.json')
    receipt_path=campaign/(runner.STATE_PREFIX+'_supervisor_maintenance_receipt.json')
    heartbeat=runner._read_json(heartbeat_path); receipt=runner._read_json(receipt_path)
    def check(launch=launcher,beat=heartbeat,body=None,now_ts=None,caller_spec=spec):
        return observe(runner,root,caller_spec,campaign,launch,beat,vars(state) if body is None else body,
            now_ts=time.time() if now_ts is None else now_ts)
    good=check(); assert good is not None
    observations['fixed_bound']=good
    # The caller's observation begins before Native publishes its next real
    # heartbeat/receipt. Later reads must use their actual post-read clock.
    captured=time.time()
    supervisor._write_supervisor_maintenance_status('run_once',status='running',started_at=started,
        maintenance_window=window)
    later_heartbeat=runner._read_json(heartbeat_path);later_receipt=runner._read_json(receipt_path)
    published=native.parse_timestamp(later_heartbeat['updated_at']).timestamp()
    assert captured < published <= time.time()
    observations['heartbeat_read_race']={'captured':captured,'published':published,
        'result':check(beat=later_heartbeat,now_ts=captured),
        'original_deadline':native.parse_timestamp(window.deadline_at).timestamp()}
    future=stamp(time.time()+60)
    runner._atomic_json(heartbeat_path,{**later_heartbeat,'updated_at':future})
    runner._atomic_json(receipt_path,{**later_receipt,'updated_at':future})
    observations['future_heartbeat_refused']=check(beat=runner._read_json(heartbeat_path)) is None
    runner._atomic_json(heartbeat_path,later_heartbeat);runner._atomic_json(receipt_path,later_receipt)
    observations['race_deadline_refused']=check(beat=later_heartbeat,
        now_ts=native.parse_timestamp(window.deadline_at).timestamp()) is None
    observations['race_stale_heartbeat_refused']=check(beat=later_heartbeat,now_ts=published+121) is None
    runner._atomic_json(heartbeat_path,heartbeat);runner._atomic_json(receipt_path,receipt)
    refused={}
    for damage in ('birth','receipt_scope','receipt_start','missing_receipt','phase','error','window_timeout',
                   'window_deadline','old_launch','heartbeat_stale','completed_deadline','live_daemon_marker',
                   'live_daemon_identity','manual_hold','operator_hold','native_hold','active_provider',
                   'provider_receipt','provider_dispatched','active_attempt','executing_phase','active_workspace',
                   'timeout_bool','timeout_nonfinite','caller_spec'):
        launch,beat,rec=deepcopy(launcher),deepcopy(heartbeat),deepcopy(receipt)
        body=deepcopy(vars(state));now_ts=time.time()
        try:
            if damage=='birth': rec['process_birth']['start_time_ticks']+=1
            elif damage=='receipt_scope': rec['repo_root']=str(base)
            elif damage=='receipt_start': rec['maintenance_started_at']=stamp(now-121)
            elif damage=='phase': rec['status']='failed'
            elif damage=='error': beat['last_agentic_maintenance_error']='synthetic_failure'
            elif damage=='window_timeout': beat['supervisor_maintenance']['timeout_seconds']=901
            elif damage=='window_deadline': beat['supervisor_maintenance']['deadline_at']=stamp(now+901)
            elif damage=='old_launch': launch['started_at']=now-10
            elif damage=='heartbeat_stale': now_ts=native.parse_timestamp(beat['updated_at']).timestamp()+121
            elif damage=='completed_deadline': now_ts=good['deadline_at']+.01
            elif damage=='live_daemon_marker': (campaign/(runner.STATE_PREFIX+'_managed_daemon.pid')).write_text(str(os.getpid()))
            elif damage=='live_daemon_identity': (campaign/(runner.STATE_PREFIX+'_managed_daemon.identity.json')).write_text('{}')
            elif damage in ('manual_hold','operator_hold'):
                (campaign/'watchdog').mkdir(exist_ok=True)
                (campaign/'watchdog'/('HOLD' if damage=='manual_hold' else 'OPERATOR_STOP')).write_text('Synthetic hold\n')
            elif damage=='native_hold': body['manual_hold']=True
            elif damage=='active_provider': body['implementation_in_progress']=True
            elif damage=='provider_receipt': body['active_provider_runner']={'pid':os.getpid()}
            elif damage=='provider_dispatched': body['provider_dispatched']=True
            elif damage=='active_attempt': body['active_attempt']=1
            elif damage=='executing_phase': body['active_phase']='validating'
            elif damage=='active_workspace': body['active_worktree_path']=str(base)
            elif damage=='timeout_bool': beat['supervisor_maintenance']['timeout_seconds']=True
            elif damage=='timeout_nonfinite': beat['supervisor_maintenance']['timeout_seconds']=float('nan')
            runner._atomic_json(campaign/'launcher.json',launch)
            runner._atomic_json(heartbeat_path,beat);runner._atomic_json(receipt_path,rec)
            if damage=='missing_receipt': receipt_path.unlink()
            caller_spec=root/runner.SPEC_RELATIVE if damage=='caller_spec' else spec
            if damage=='caller_spec': runner._campaign_spec(root,caller_spec)
            refused[damage]=check(launch,beat,body,now_ts,caller_spec) is None
        finally:
            runner._atomic_json(campaign/'launcher.json',launcher)
            runner._atomic_json(heartbeat_path,heartbeat);runner._atomic_json(receipt_path,receipt)
            for path in (campaign/(runner.STATE_PREFIX+'_managed_daemon.pid'),
                    campaign/(runner.STATE_PREFIX+'_managed_daemon.identity.json'),campaign/'watchdog/HOLD',campaign/'watchdog/OPERATOR_STOP'):
                if path.exists():path.unlink()
    # A fresh heartbeat cannot renew the immutable original maintenance cap.
    expired_start=stamp(time.time()-901)
    supervisor._write_supervisor_maintenance_status('run_once',status='running',started_at=expired_start,
        maintenance_window=SupervisorMaintenanceWindow.begin(started_at=expired_start,timeout_seconds=900))
    runner._atomic_json(campaign/'launcher.json',{**launcher,'started_at':time.time()-1000})
    refused['running_deadline']=observe(runner,root,spec,campaign,runner._read_json(campaign/'launcher.json'),
        runner._read_json(heartbeat_path),vars(state),now_ts=time.time()) is None
    runner._atomic_json(campaign/'launcher.json',launcher)
    # Actual Native spawn publishes the child PID immediately, before its
    # independent bootstrap. The no-daemon handoff must stop qualifying.
    child_script=base/'inert_daemon.py';child_script.write_text('import time\ntime.sleep(20)\n')
    config.daemon_script_path=child_script
    child=supervisor._start_daemon()
    try:
        child_birth=native.read_process_birth(child.pid);assert child_birth is not None
        supervisor._write_supervisor_maintenance_status('run_once',status='completed',started_at=started,
            maintenance_window=window,daemon_pid=child.pid,daemon_process_birth=child_birth)
        value=runner.status(root,spec,campaign)
        observations['spawned']={key:value.get(key) for key in ('status','owned_process_alive',
            'startup_activity_verified','progress_verified','native_read_errors')}
        observations['spawned']['board_complete']=bool(value['board']['count']
            and value['board']['count']==value['board']['completed'])
    finally:
        child.terminate();child.wait(timeout=10)
        supervisor._managed_daemon_pid_path().unlink()
    observations['refused']=refused
    return observations


@pytest.fixture(scope='module')
def owned_observations(tmp_path_factory):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as runtime
    base=tmp_path_factory.mktemp('owned-startup-status')
    sdk=Path(native.__file__).resolve().parents[3]
    paths=[str(Path(runner.__file__).resolve().parents[2]),str(sdk),str(sdk.parent/'ipfs_datasets_py'),str(sdk.parent/'ipfs_kit_py')]
    program=base/'parent.py'; output=base/'closed-status.json'
    program.write_text('import sys\nsys.path[:0]='+repr(paths)+'\n'+
        'from pathlib import Path\nimport json\nfrom tests.test_owned_startup_maintenance_status import _owned_main\n'+
        "if __name__=='__main__': Path(sys.argv[5]).write_text(json.dumps(_owned_main(Path(sys.argv[4]))))\n")
    with (base/'private-child.log').open('w') as log:
        result=runtime.run_process_group_stream([sys.executable,'-I','-B',str(program),'_run','--owner-token',
            'private-startup-fixture',str(base),str(output)],cwd=base,stdout=log,env=dict(os.environ),
            inherit_environment=False,timeout_seconds=60)
    assert result.returncode==0, 'See private-child.log for this inert fixture.'
    return json.loads(output.read_text())


@pytest.mark.parametrize('phase',['running','completed'])
def test_actual_native_maintenance_after_ninety_seconds_is_bounded_liveness(owned_observations,phase):
    value=owned_observations[phase]
    assert value['native_read_errors']=={} and value['owned_process_alive'] is True,value
    assert value['status']=='maintenance',value
    assert value['healthy'] is True and value['startup_activity_verified'] is True,value
    assert value['progress_verified'] is False and value['provider_progress_verified'] is False
    assert value['validation_activity_verified'] is False


@pytest.mark.parametrize('damage',['birth','receipt_scope','receipt_start','missing_receipt','phase','error',
    'window_timeout','window_deadline','old_launch','heartbeat_stale','completed_deadline','live_daemon_marker',
    'live_daemon_identity','manual_hold','operator_hold','native_hold','active_provider','running_deadline',
    'provider_receipt','provider_dispatched','active_attempt','executing_phase','active_workspace',
    'timeout_bool','timeout_nonfinite','caller_spec'])
def test_actual_owned_receipt_refuses_changed_scope_or_fixed_deadline(owned_observations,damage):
    assert owned_observations['refused'][damage] is True


def test_actual_native_spawn_hands_status_to_existing_managed_child_guard(owned_observations):
    value=owned_observations['spawned']
    assert value['native_read_errors']=={} and value['owned_process_alive'] is True,value
    expected='complete' if value['board_complete'] else 'maintenance'
    assert value['status']==expected and value['startup_activity_verified'] is False,value
    assert value['progress_verified'] is False


def test_completed_observation_uses_only_original_fixed_handoff(owned_observations):
    value=owned_observations['fixed_bound']
    assert value['reason']=='bounded_native_startup_handoff'
    assert value['work_progress_verified'] is False and value['completion_authority'] is False


def test_real_native_heartbeat_published_after_caller_clock_is_current_liveness(owned_observations):
    race=owned_observations['heartbeat_read_race']
    assert race['captured'] < race['published']
    assert race['result'] is not None
    assert race['result']['reason']=='bounded_native_startup_maintenance'
    assert race['result']['deadline_at']==race['original_deadline']
    assert race['result']['work_progress_verified'] is False


def test_fresh_read_clock_cannot_admit_future_or_expired_native_heartbeat(owned_observations):
    assert owned_observations['future_heartbeat_refused'] is True
    assert owned_observations['race_deadline_refused'] is True
    assert owned_observations['race_stale_heartbeat_refused'] is True
