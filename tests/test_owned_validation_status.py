"""Actual owned Native executor activity after an authored provider deadline.

Private synthetic campaign only: real claims, births, sealed executor and
short-lived canonical activity, with no model, merge, completion or recovery.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from tests.test_owned_auto_rescue_activity import _status_in_owned_parent

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def observe_actual_executor(world, mode):
    """Run inside the real Native child of the inert owned _run parent."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import (
        build_validation_environment, validation_environment_for_runner, VALIDATION_PYTHON_ENV)
    campaign, workspace = world['campaign'], world['workspace']
    stamp = lambda seconds: datetime.fromtimestamp(seconds, timezone.utc).isoformat()
    now = time.time()
    state = native.PortalTaskState.load(world['daemon'].state_path)
    state.active_task_started_at = state.last_implementation_started_at = stamp(now-1000)
    state.heartbeat_at = state.last_progress_at = stamp(now)
    state.save(world['daemon'].state_path)
    launcher = runner._read_json(campaign/'launcher.json')
    runner._atomic_json(campaign/'launcher.json', {**launcher, 'started_at':now-1100})

    def status():
        value = runner.status(world['root'], world['spec'], campaign)
        keys = ('status','healthy','scope_liveness','validation_activity_verified',
            'validation_activity_evidence','auto_rescue_activity_verified','provider_progress_verified',
            'native_read_errors','progress_verified')
        return {key:value.get(key) for key in keys}

    if mode == 'validation_provider_expired':
        # The real still-streaming Native rescue cannot borrow the validator's
        # separate phase budget. Its original provider deadline remains fixed.
        return {'provider_expired':status()}

    (workspace/'release').touch(); world['worker'].join(10)
    assert not world['worker'].is_alive()
    context = {'campaign_state_dir':str(campaign), 'target_source_root':str(world['root']),
        'task_id':state.active_task_id, 'task_cid':state.active_task_cid, 'task_key':state.active_task_key}
    task = {'id':state.active_task_id}
    binding = runner._validation_activity_binding(workspace,task,context,now_ts=time.time())
    assert binding is not None
    before = deepcopy(vars(state))
    before_claim = world['claim_path'].read_bytes()
    before_lease = world['lease_path'].read_bytes()
    program = workspace/'inert_canonical_executor.py'
    program.write_text("from pathlib import Path\nimport time\nroot=Path(__file__).parent\n"
        "(root/'executor-ready').touch()\n"
        "while not (root/'executor-release').exists(): time.sleep(.01)\n")
    command = 'python -I -B '+shlex.quote(str(program))
    executor = native.PortalImplementationDaemon._validation_command_runner
    assert Path(executor.__code__.co_filename).resolve() == Path(native.__file__).resolve()
    environment = validation_environment_for_runner(build_validation_environment(
        {**os.environ,VALIDATION_PYTHON_ENV:sys.executable}),executor)
    results, errors = [], []
    def execute():
        try:
            results.append(runner._call_validation_with_activity(executor=executor,
                spec=SimpleNamespace(command=command,raw_command=command), workspace_path=workspace,
                timeout_seconds=25, environment=environment, task=task, context=context))
        except BaseException as exc:
            errors.append(exc)
    thread = threading.Thread(target=execute,daemon=True); thread.start()
    deadline = time.monotonic()+15
    pulse_path = runner._validation_activity_path(binding,create=True)
    try:
        while (not (workspace/'executor-ready').exists() or not pulse_path.is_file()) and thread.is_alive() and time.monotonic()<deadline:
            time.sleep(.02)
        assert (workspace/'executor-ready').exists() and pulse_path.is_file(), (results,errors)
        pulse = runner._read_validation_activity(pulse_path)
        assert runner._validation_activity_record_valid(pulse,binding,now_ts=time.time())
        if mode == 'validation_pulse_race':
            from integrations.ipfs_accelerate import reconciliation_activity
            original_evidence = reconciliation_activity.evidence
            original_read = runner._read_validation_activity
            race = {}
            def after_new_pulse(*args, now_ts):
                observer_thread = threading.get_ident()
                def read(path):
                    value = original_read(path)
                    if path == pulse_path and threading.get_ident() == observer_thread:
                        until = time.monotonic()+8
                        while value['observed_at'] <= now_ts and time.monotonic() < until:
                            time.sleep(.01)
                            value = original_read(path)
                        assert value['observed_at'] > now_ts
                        race.update(captured_at=now_ts, pulse_observed_at=value['observed_at'],
                            deadline_at=value['deadline_at'], old_clock_accepts=
                            runner._validation_activity_record_valid(value,binding,now_ts=now_ts))
                    return value
                with pytest.MonkeyPatch.context() as patch:
                    patch.setattr(runner, '_read_validation_activity', read)
                    return original_evidence(*args, now_ts=now_ts)
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(reconciliation_activity, 'evidence', after_new_pulse)
                raced = status()
            # This explicitly damaged copy tests refusal; it is never written
            # to the real executor's private activity record.
            def future_read(path):
                value = original_read(path)
                return {**value, 'observed_at':time.time()+60} if path == pulse_path else value
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(runner, '_read_validation_activity', future_read)
                future = status()
            expired = original_evidence(runner,world['root'],campaign,
                runner._read_json(campaign/'launcher.json'),runner._validation_activity_snapshot(campaign)['body'],
                now_ts=binding['phase_deadline'])
            assert 'deadline_at' in race, (raced, future)
            assert original_read(pulse_path)['deadline_at'] == pulse['deadline_at'] == race['deadline_at']
            assert world['claim_path'].read_bytes() == before_claim
            assert world['lease_path'].read_bytes() == before_lease
            assert vars(state) == before
            return {'raced_pulse':raced, 'race':race, 'future_pulse':future, 'expired':expired}
        observed = {'canonical_pulse':status()}
        # Strict current ownership and the existing single validation deadline
        # remain necessary even while a genuine executor is still running.
        claim = json.loads(before_claim)
        runner._atomic_json(world['claim_path'], {**claim,'canonical_task_cid':'explicit-foreign-cid'})
        observed['wrong_claim'] = status()
        world['claim_path'].write_bytes(before_claim)
        state.active_phase_started_at = stamp(time.time()-901)
        state.save(world['daemon'].state_path)
        observed['expired_phase'] = status()
        state.active_phase_started_at = before['active_phase_started_at']
        state.save(world['daemon'].state_path)
        heartbeat = campaign/(runner.STATE_PREFIX+'_supervisor_status.json')
        info = heartbeat.stat()
        os.utime(heartbeat,(time.time()-121,time.time()-121))
        observed['stale_heartbeat'] = status()
        os.utime(heartbeat,ns=(info.st_atime_ns,info.st_mtime_ns))
        assert runner._read_validation_activity(pulse_path)['deadline_at'] == pulse['deadline_at']
        assert world['claim_path'].read_bytes() == before_claim
        assert world['lease_path'].read_bytes() == before_lease
        assert vars(state) == before
        return observed
    finally:
        (workspace/'executor-release').touch(); thread.join(10)
        assert not thread.is_alive() and not errors,errors
        assert results and results[0]['returncode']==0,results
        assert results[0]['validation_python_launcher']['sealed'] is True


def test_actual_canonical_executor_status_uses_existing_validation_deadline(tmp_path):
    observations = _status_in_owned_parent(tmp_path,'validation_canonical')
    value = observations['canonical_pulse']
    assert value['native_read_errors']=={},value
    assert value['validation_activity_evidence']['type']=='canonical_native_validation_in_flight',value
    assert value['validation_activity_verified'] is True and not value['auto_rescue_activity_verified']
    assert value['status']=='active' and value['healthy'] is True,value
    assert value['scope_liveness']['claim']=='held' and value['scope_liveness']['validation']=='fresh',value
    for damage in ('wrong_claim','expired_phase','stale_heartbeat'):
        refused = observations[damage]
        assert refused['status']=='stalled' and refused['healthy'] is False,(damage,refused)
    for damage in ('wrong_claim','expired_phase'):
        assert observations[damage]['validation_activity_verified'] is False


def test_actual_rescue_thought_keeps_original_provider_deadline(tmp_path):
    observed = _status_in_owned_parent(tmp_path,'validation_provider_expired')['provider_expired']
    assert observed['status']=='stalled' and observed['healthy'] is False,observed
    assert observed['scope_liveness']['claim']=='expired'
    assert observed['auto_rescue_activity_verified'] is False
    assert observed['validation_activity_verified'] is False
    assert observed['progress_verified'] is False


def test_real_canonical_pulse_published_during_status_read_is_not_a_false_stall(tmp_path):
    observed = _status_in_owned_parent(tmp_path,'validation_pulse_race')
    assert observed['race']['captured_at'] < observed['race']['pulse_observed_at']
    assert observed['race']['old_clock_accepts'] is False
    live = observed['raced_pulse']
    assert live['status'] == 'active' and live['healthy'] is True,live
    assert live['validation_activity_verified'] is True,live
    assert live['validation_activity_evidence']['deadline_at'] == observed['race']['deadline_at']
    assert observed['expired'] is None
    future = observed['future_pulse']
    assert future['validation_activity_verified'] is False,future
    assert future['status'] == 'stalled' and future['healthy'] is False,future
