"""Close a protected-guard preflight using its real Native terminal receipt.

History is an explicit private fixture; the recorded parent really starts,
exits and is reaped, and the positive observes two real process inventories.
The existing Docker transport is inert and dispatches no provider/container.
"""
from copy import deepcopy
import hashlib
import json
import time
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import improvement_shutdown as shutdown
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
from tests.test_dead_preheartbeat_shutdown import dead_before_heartbeat
from tests.test_improvement_container_shutdown import campaign, docker, stamp

REAL_INVENTORY = shutdown._complete_process_inventory
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture
def blocked_guard(dead_before_heartbeat, monkeypatch):
    f = dead_before_heartbeat
    hb = deepcopy(f.heartbeat)
    parent = f.record['identity']
    # Keep the completed receipt inside the real launch interval without
    # comparing a rounded ISO microsecond to the launch's fractional float.
    begun = time.time()
    finished = time.time()
    birth = {'pid': parent['pid'], 'start_time_ticks': parent['start_ticks'],
        'boot_id': parent['boot_id'], 'parent_pid': parent['ppid']}
    hb.update(status='agentic_maintenance_completed', supervisor_pid=parent['pid'],
        supervisor_process_birth=birth, daemon_pid=None, daemon_process_birth=None,
        active_agentic_maintenance_has_daemon=False, active_worker_count=0, active_worker_pids=[],
        worker_descendant_count=0, last_agentic_maintenance_status='completed',
        last_agentic_maintenance_phase='implementation_protected_path_guard', run_id='',
        updated_at=stamp(finished), supervisor_maintenance={
            'schema': 'ipfs_accelerate_py/agent-supervisor/supervisor-maintenance@1',
            'phase': 'completed', 'started_at': stamp(begun), 'finished_at': stamp(finished),
            'timeout_seconds': 900, 'deadline_at': stamp(begun+900)})
    runner._atomic_json(f.state/'complaint_intake_supervisor_status.json', hb)
    owner = native.ProcessBirthIdentity.from_dict(birth)
    producer = object.__new__(native.PortalImplementationSupervisor)
    producer.config = SimpleNamespace(repo_root=f.repo, state_dir=f.state,
        state_path=f.state/'complaint_intake_task_state.json', state_prefix='complaint_intake')
    with monkeypatch.context() as scope:
        scope.setattr(native, 'os', SimpleNamespace(getpid=lambda: parent['pid']))
        scope.setattr(native, 'read_process_birth', lambda pid: owner if pid == owner.pid else None)
        native.PortalImplementationSupervisor._write_supervisor_maintenance_receipt(producer,
            'implementation_protected_path_guard', status='completed', started_at=stamp(begun), updated_at=stamp(finished))
    return SimpleNamespace(**vars(f), guard_heartbeat=hb,
        receipt=f.state/'complaint_intake_supervisor_maintenance_receipt.json')


def test_actual_dead_parent_guard_receipt_allows_public_stop_without_signals(blocked_guard, docker, monkeypatch):
    f = blocked_guard
    calls = []
    def inventory(cutoff):
        calls.append(cutoff)
        return REAL_INVENTORY(cutoff)
    monkeypatch.setattr(shutdown, '_complete_process_inventory', inventory)
    hb = (f.state/'complaint_intake_supervisor_status.json').read_bytes()
    receipt = f.receipt.read_bytes()
    result = runner.stop(f.state)
    assert result['status'] == 'stopped' and result['signalled'] is False
    proof = result['container_shutdown']['process_closure']
    assert proof['source'] == 'owned_completed_preflight_native_receipt_and_double_complete_proc_inventory'
    assert proof['observations'] == 2 and calls == [f.record['identity']['start_ticks']]*2
    assert proof['preflight_without_managed_daemon'] is True and proof['daemon_birth_ticks_claimed'] is False
    assert proof['maintenance_receipt_sha256'] == hashlib.sha256(receipt).hexdigest()
    assert proof['signals_sent'] is proof['completion_authority'] is proof['attempt_refunded'] is False
    assert f.receipt.read_bytes() == receipt and (f.state/'complaint_intake_supervisor_status.json').read_bytes() == hb
    assert not docker[0].effects


@pytest.mark.parametrize('damage', ['unknown_phase', 'different_receipt_phase', 'receipt_owner',
    'receipt_deadline', 'new_run', 'paid_start', 'daemon', 'worker', 'unavailable_census', 'receipt_race'])
def test_guard_preflight_still_refuses_unbound_or_active_scope(blocked_guard, docker, monkeypatch, damage):
    f = blocked_guard; hb = deepcopy(f.guard_heartbeat); receipt = json.loads(f.receipt.read_text())
    if damage == 'unknown_phase': hb['last_agentic_maintenance_phase'] = receipt['phase'] = 'unrecognized_boundary'
    elif damage == 'different_receipt_phase': receipt['phase'] = 'supervisor_check_event'
    elif damage == 'receipt_owner': receipt['process_birth']['start_time_ticks'] += 1
    elif damage == 'receipt_deadline': hb['supervisor_maintenance']['deadline_at'] = stamp(time.time()+1000)
    elif damage == 'new_run': hb['run_id'] = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(f.record['started_at']))
    elif damage == 'paid_start':
        event = deepcopy(f.event); event['timestamp'] = stamp(time.time())
        (f.state/'complaint_intake_events.jsonl').write_text(json.dumps(event)+'\n')
    elif damage == 'daemon': hb['daemon_pid'] = 1073741826
    elif damage == 'worker': hb['active_worker_count'] = 1; hb['active_worker_pids'] = [1073741826]
    runner._atomic_json(f.state/'complaint_intake_supervisor_status.json', hb)
    runner._atomic_json(f.receipt, receipt)
    scans = []
    def inventory(cutoff):
        scans.append(cutoff)
        if damage == 'unavailable_census': raise ValueError('explicit unavailable observation')
        if damage == 'receipt_race' and len(scans) == 1:
            changed = dict(receipt, status='running'); runner._atomic_json(f.receipt, changed)
        return []
    monkeypatch.setattr(shutdown, '_complete_process_inventory', inventory)
    result = runner.stop(f.state)
    assert result['status'] == 'stop_incomplete' and result['signalled'] is False
    assert not docker[0].effects
