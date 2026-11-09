"""Read-only liveness during owned Native startup maintenance and handoff.

The existing Native window remains fixed. A completed window permits only a
short fixed interval for Host postconditions before managed-daemon startup.
Neither observation establishes work, dispatch, recovery or completion authority.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import time

HANDOFF_SECONDS = 30.0


def observe(runner, repo_root, spec_path, campaign, launcher, heartbeat, state, *, now_ts):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.supervisor_activity import (
        MAINTENANCE_SCHEMA, SupervisorMaintenanceWindow)

    try:
        if (type(now_ts) not in (int,float) or not math.isfinite(now_ts)
                or state.get('implementation_in_progress')
                or type(state.get('active_attempt')) is not int or state['active_attempt'] != 0
                or state.get('active_phase') not in ('','idle','selected','selecting')
                or any(state.get(key) for key in ('active_provider_runner','provider_dispatched',
                    'active_worktree_path','active_log_path','active_branch'))
                or any(state.get(key) for key in ('manual_hold','manual_cancellation','capacity_quarantine','protected_incident'))):
            return None
        root, campaign = Path(repo_root), Path(campaign)
        runner._validation_activity_directory(campaign,private=True)
        if any(os.path.lexists(campaign/'watchdog'/name) for name in ('HOLD','OPERATOR_STOP')):
            return None
        paths = [campaign/'launcher.json',campaign/(runner.STATE_PREFIX+'_supervisor_status.json'),
            campaign/(runner.STATE_PREFIX+'_supervisor_maintenance_receipt.json')]
        read = runner._read_validation_watchdog_authority
        actual_launch, actual_heartbeat, receipt = (read(path) for path in paths)
        if actual_launch != launcher or actual_heartbeat != heartbeat or not isinstance(receipt,dict):
            return None
        # Native may publish these records after status captured its clock.
        # Observe them against the post-read clock without moving any bound.
        now_ts = max(now_ts, time.time())
        if not runner._campaign_tuple_matches(launcher,root,Path(spec_path),campaign):
            return None
        birth = native.read_process_birth(launcher.get('identity',{}).get('pid'))
        if (birth is None or not runner.owns_process(launcher)
                or launcher.get('status') not in ('starting','running')
                or native.ProcessBirthIdentity.from_dict(heartbeat.get('supervisor_process_birth')) != birth
                or native.ProcessBirthIdentity.from_dict(receipt.get('process_birth')) != birth
                or heartbeat.get('supervisor_pid') != birth.pid or receipt.get('supervisor_pid') != birth.pid
                or heartbeat.get('supervisor_pid_alive') is not True
                or heartbeat.get('daemon_pid') not in (None,0)
                or heartbeat.get('daemon_pid_alive') is not False
                or heartbeat.get('daemon_process_birth') is not None
                or heartbeat.get('active_agentic_maintenance_has_daemon') is not False
                or heartbeat.get('last_agentic_maintenance_error')):
            return None
        # The actual Native spawn publishes these markers immediately after
        # Popen. Once present, ordinary managed-daemon guards take over.
        if any(os.path.lexists(campaign/(runner.STATE_PREFIX+suffix)) for suffix in
               ('_managed_daemon.pid','_managed_daemon.identity.json')):
            return None
        state_path = str(campaign/(runner.STATE_PREFIX+'_task_state.json'))
        if (receipt.get('schema') != native.SUPERVISOR_MAINTENANCE_RECEIPT_SCHEMA
                or any(receipt.get(key) != value for key,value in {
                    'repo_root':str(root),'state_dir':str(campaign),'state_path':state_path,
                    'state_prefix':runner.STATE_PREFIX}.items())
                or any(heartbeat.get(key) != value for key,value in {
                    'repo_root':str(root),'state_path':state_path,'state_prefix':runner.STATE_PREFIX,
                    'task_prefix':runner.TASK_PREFIX,
                    'child_pid_path':str(campaign/(runner.STATE_PREFIX+'_managed_daemon.pid'))}.items())):
            return None
        value = heartbeat.get('supervisor_maintenance')
        if (not isinstance(value,dict) or set(value) != {
                'schema','started_at','timeout_seconds','deadline_at','phase','finished_at'}
                or value.get('schema') != MAINTENANCE_SCHEMA
                or type(value.get('timeout_seconds')) not in (int,float)
                or not math.isfinite(value['timeout_seconds'])):
            return None
        window = SupervisorMaintenanceWindow(value['started_at'],value['timeout_seconds'],value['deadline_at'])
        start = native.parse_timestamp(window.started_at).timestamp()
        deadline = native.parse_timestamp(window.deadline_at).timestamp()
        launch_start = launcher.get('started_at')
        updated = native.parse_timestamp(heartbeat.get('updated_at'))
        phase = value.get('phase')
        if (type(launch_start) not in (int,float) or not math.isfinite(launch_start)
                or not launch_start <= start <= now_ts
                or not 0 < window.timeout_seconds <= runner.TIMEOUT_SECONDS
                or heartbeat.get('active_agentic_maintenance_timeout_seconds') != window.timeout_seconds
                or updated is None or not 0 <= now_ts-updated.timestamp() <= 120
                or receipt.get('updated_at') != heartbeat.get('updated_at')
                or receipt.get('maintenance_started_at') != window.started_at
                or receipt.get('phase') != heartbeat.get('last_agentic_maintenance_phase')
                or not isinstance(receipt.get('phase'),str) or not receipt['phase']
                or receipt.get('status') != phase or heartbeat.get('last_agentic_maintenance_status') != phase):
            return None
        if phase == 'running':
            if (heartbeat.get('status') != 'agentic_maintenance_started'
                    or heartbeat.get('active_agentic_maintenance_started_at') != window.started_at
                    or value.get('finished_at') is not None or receipt.get('completed_at')
                    or not now_ts < deadline):
                return None
            bound, reason = deadline, 'bounded_native_startup_maintenance'
        elif phase == 'completed':
            finished = native.parse_timestamp(value.get('finished_at'))
            if (heartbeat.get('status') != 'agentic_maintenance_completed'
                    or heartbeat.get('active_agentic_maintenance_started_at') != ''
                    or finished is None or value['finished_at'] != heartbeat.get('updated_at')
                    or receipt.get('completed_at') != value['finished_at']
                    or not start <= finished.timestamp() <= deadline):
                return None
            bound = min(deadline+HANDOFF_SECONDS,finished.timestamp()+HANDOFF_SECONDS)
            if not finished.timestamp() <= now_ts < bound:
                return None
            reason = 'bounded_native_startup_handoff'
        else:
            return None
        if ([read(path) for path in paths] != [launcher,heartbeat,receipt]
                or native.read_process_birth(birth.pid) != birth or not runner.owns_process(launcher)
                or any(os.path.lexists(campaign/(runner.STATE_PREFIX+suffix)) for suffix in
                       ('_managed_daemon.pid','_managed_daemon.identity.json'))):
            return None
        return {'reason':reason,'phase':phase,'started_at':start,'deadline_at':bound,
            'owner_pid':birth.pid,'work_progress_verified':False,'completion_authority':False}
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        return None
