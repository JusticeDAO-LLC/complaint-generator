"""Fresh negative closure for an actual parent that exits before its heartbeat.

Only private inert Python processes run. The existing inert Docker transport
performs no real container or provider work. History is explicit synthetic scope;
actual process absence and full inventories remain freshly observed.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import improvement_shutdown as shutdown
from tests.test_improvement_container_shutdown import campaign, docker, stamp, _missing_marker_heartbeat

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
_REAL_IDENTITY = runner.process_identity
_REAL_INVENTORY = shutdown._complete_process_inventory


@pytest.fixture
def dead_before_heartbeat(campaign, docker, monkeypatch):
    f = campaign
    monkeypatch.setattr(runner, 'process_identity', _REAL_IDENTITY)
    old = _missing_marker_heartbeat(f.state, f.record, None)
    old.update(status='stopped', supervisor_pid=1073741824, updated_at=stamp(time.time()-5),
        supervisor_pid_alive=False, daemon_pid_alive=False, active_worker_count=0, active_worker_pids=[],
        worker_descendant_count=0, managed_daemon_cleanup={'quiesced': True, 'pid': 1073741825,
            'pid_path': str(f.state/'complaint_intake_managed_daemon.pid'),
            'identity_path': str(f.state/'complaint_intake_managed_daemon.identity.json'), 'remaining_pid': None})
    runner._atomic_json(f.state/'complaint_intake_supervisor_status.json', old)
    (f.state/'complaint_intake_supervisor.pid').write_text('1073741824\n')
    (f.state/'complaint_intake_supervisor_events.jsonl').write_text(json.dumps({
        'type': 'supervisor_signal_shutdown', 'timestamp': old['updated_at']})+'\n')
    script = f.repo/'scripts/run_complaint_improvement_supervisor.py'
    script.parent.mkdir(parents=True)
    script.write_text('import time\ntime.sleep(30)\n')
    child = subprocess.Popen(f.record['argv'], cwd=f.repo, start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # /proc cmdline can be briefly empty while exec publishes the child's
        # address space. Capture the actual registered argv before retaining
        # this real birth as historical shutdown evidence.
        deadline = time.monotonic() + 2
        while True:
            identity = _REAL_IDENTITY(child.pid)
            if (identity and identity.get('argv') == f.record['argv']
                    and identity['session'] == identity['process_group'] == child.pid):
                break
            assert child.poll() is None, 'inert parent exited before publishing its argv'
            assert time.monotonic() < deadline, 'inert parent did not publish its exact argv'
            time.sleep(.01)
        record = {**deepcopy(f.record), 'identity': identity, 'status': 'starting', 'started_at': time.time()}
        runner._atomic_json(f.state/'launcher.json', record)
        child.terminate(); child.wait(timeout=3)
        assert not (Path('/proc')/str(child.pid)).exists()
        monkeypatch.setattr(shutdown, '_complete_process_inventory', _REAL_INVENTORY)
        yield SimpleNamespace(**{**vars(f), 'record': record}, heartbeat=old,
            context=shutdown._context(f.state, record))
    finally:
        if child.poll() is None: child.kill()
        child.wait(timeout=3)


def _bytes(f):
    return {p.name: p.read_bytes() for p in f.state.iterdir() if p.is_file()}


@pytest.mark.parametrize('receipt', ['absent', 'failed', 'malformed'])
def test_actual_dead_start_has_fresh_readonly_closure_without_stop_receipt(dead_before_heartbeat, monkeypatch, receipt):
    f = dead_before_heartbeat
    if receipt != 'absent':
        path = f.state/shutdown.RECEIPT_NAME
        path.write_text('{invalid' if receipt == 'malformed' else json.dumps({
            'status': 'stop_incomplete', 'quiesced': False, 'reason': 'invalid shutdown timestamp'}))
        path.chmod(0o600)
    scans = []
    def inventory(cutoff, **options):
        scans.append(cutoff)
        return _REAL_INVENTORY(cutoff, **options)
    monkeypatch.setattr(shutdown, '_complete_process_inventory', inventory)
    before = _bytes(f)
    result = shutdown._parent_closed(f.state, f.record, f.context, False)
    assert result['source'] == 'owned_dead_preheartbeat_start_and_double_complete_proc_inventory'
    assert result['observations'] == 2 and result['proc_census_complete'] is True
    assert result['historical_heartbeat_only'] is True and 'observed_stopped_at' not in result
    assert result['signals_sent'] is result['attempt_refunded'] is result['completion_authority'] is False
    assert scans == [f.record['identity']['start_ticks']]*2 and _bytes(f) == before


def test_actual_public_stop_of_dead_start_establishes_normal_repeatable_provenance(dead_before_heartbeat, docker):
    f = dead_before_heartbeat
    starting = (f.state/'launcher.json').read_bytes()
    outcome = runner.stop(f.state, timeout=.1)
    assert outcome['status'] == 'stopped' and outcome['signalled'] is False
    assert outcome['container_shutdown']['process_closure']['source'] == (
        'owned_dead_preheartbeat_start_and_double_complete_proc_inventory')
    assert not docker[0].effects
    record = json.loads((f.state/'launcher.json').read_text())
    proof = json.loads((f.state/shutdown.RECEIPT_NAME).read_text())
    assert proof['launcher_sha256'] == hashlib.sha256(starting).hexdigest()
    assert record['started_at'] <= record['stopped_at'] <= time.time()
    assert runner._shutdown_verified(record, proof, f.repo, f.state)
    repeated = shutdown._parent_closed(f.state, record, shutdown._context(f.state, record), False)
    assert repeated['source'] == 'owned_preheartbeat_stop_and_double_complete_proc_inventory'


@pytest.mark.parametrize('history', ['absent', 'empty'])
def test_actual_first_launch_without_history_can_close(dead_before_heartbeat, history):
    f = dead_before_heartbeat
    for name in ['complaint_intake_supervisor_status.json', 'complaint_intake_supervisor.pid',
                 'complaint_intake_events.jsonl', 'complaint_intake_supervisor_events.jsonl']:
        (f.state/name).unlink()
        if history == 'empty' and name.endswith('.jsonl'): (f.state/name).write_bytes(b'')
    before = _bytes(f)
    result = shutdown._parent_closed(f.state, f.record, f.context, False)
    assert result['historical_heartbeat_only'] is False and result['observations'] == 2
    assert _bytes(f) == before


@pytest.mark.parametrize('damage', ['stopped_at', 'running', 'wrong_hb_repo', 'running_hb', 'newer_hb',
    'current_hb_owner', 'active_worker', 'pid_marker', 'identity_marker', 'current_supervisor_marker',
    'task_event', 'supervisor_event', 'malformed_event', 'missing_timestamp', 'absent_hb_old_event',
    'receipt_symlink', 'receipt_hardlink', 'receipt_writable'])
def test_dead_start_rejects_mixed_or_unavailable_history(dead_before_heartbeat, monkeypatch, damage):
    f = dead_before_heartbeat; record = deepcopy(f.record); hb = deepcopy(f.heartbeat)
    if damage == 'stopped_at': record['stopped_at'] = time.time()
    elif damage == 'running': record['status'] = 'running'
    elif damage == 'wrong_hb_repo': hb['repo_root'] = '/foreign'
    elif damage == 'running_hb': hb['status'] = 'running'
    elif damage == 'newer_hb': hb['updated_at'] = stamp(record['started_at']+1)
    elif damage == 'current_hb_owner': hb['supervisor_pid'] = record['identity']['pid']
    elif damage == 'active_worker': hb['active_worker_count'] = 1; hb['active_worker_pids'] = [1073741826]
    elif damage == 'pid_marker': (f.state/'complaint_intake_managed_daemon.pid').write_text('1073741826\n')
    elif damage == 'identity_marker': (f.state/'complaint_intake_managed_daemon.identity.json').write_text('{}')
    elif damage == 'current_supervisor_marker': (f.state/'complaint_intake_supervisor.pid').write_text(str(record['identity']['pid'])+'\n')
    elif damage in {'task_event', 'supervisor_event', 'missing_timestamp'}:
        name = 'complaint_intake_supervisor_events.jsonl' if damage == 'supervisor_event' else 'complaint_intake_events.jsonl'
        event = {'type': 'selection_or_maintenance'}
        if damage != 'missing_timestamp': event['timestamp'] = stamp(record['started_at']+.1)
        with (f.state/name).open('a') as out: out.write(json.dumps(event)+'\n')
    elif damage == 'malformed_event': (f.state/'complaint_intake_events.jsonl').write_text('{\n')
    elif damage.startswith('receipt_'):
        path = f.state/shutdown.RECEIPT_NAME
        target = f.state/'private-receipt'; target.write_text('{}'); target.chmod(0o600)
        if damage == 'receipt_symlink': path.symlink_to(target)
        elif damage == 'receipt_hardlink': os.link(target, path)
        else: path.write_text('{}'); path.chmod(0o666)
    runner._atomic_json(f.state/'launcher.json', record)
    runner._atomic_json(f.state/'complaint_intake_supervisor_status.json', hb)
    if damage == 'absent_hb_old_event':
        (f.state/'complaint_intake_supervisor_status.json').unlink()
        (f.state/'complaint_intake_supervisor.pid').unlink()
    monkeypatch.setattr(shutdown, '_complete_process_inventory', lambda cutoff, **options: [])
    before = _bytes(f)
    with pytest.raises((ValueError, OSError)):
        shutdown._parent_closed(f.state, record, shutdown._context(f.state, record), False)
    assert _bytes(f) == before


@pytest.mark.parametrize('damage', ['group', 'session', 'scoped_cwd', 'scoped_argv', 'unavailable',
    'launcher_inode', 'event_after_first_scan', 'marker_after_first_scan', 'receipt_after_first_scan'])
def test_dead_start_rechecks_census_and_evidence_at_each_scan(dead_before_heartbeat, monkeypatch, damage):
    f = dead_before_heartbeat; calls = []
    def inventory(cutoff, **options):
        calls.append(cutoff)
        if damage == 'unavailable': raise ValueError('explicit synthetic unavailable inventory')
        if damage.endswith('first_scan') or damage == 'launcher_inode':
            if len(calls) == 1:
                if damage == 'launcher_inode':
                    path = f.state/'launcher.json'; raw = path.read_bytes(); path.unlink(); path.write_bytes(raw); path.chmod(0o600)
                elif damage == 'event_after_first_scan':
                    with (f.state/'complaint_intake_events.jsonl').open('a') as out:
                        out.write(json.dumps({'timestamp': stamp(time.time()), 'type': 'selected'})+'\n')
                elif damage == 'marker_after_first_scan': (f.state/'complaint_intake_managed_daemon.pid').write_text('1073741826\n')
                else: runner._atomic_json(f.state/shutdown.RECEIPT_NAME, {'status': 'unverified'})
            return []
        row = {'pid': 1073741826, 'uid': os.getuid(), 'process_group': 1073741826,
            'session': 1073741826, 'start_ticks': cutoff+1, 'argv': ('/usr/bin/python3',), 'cwd': str(f.repo.parent)}
        if damage == 'group': row['process_group'] = f.record['identity']['pid']
        elif damage == 'session': row['session'] = f.record['identity']['pid']
        elif damage == 'scoped_cwd': row['cwd'] = str(f.workspace)
        else: row['argv'] = tuple(f.record['argv'])
        return [row]
    monkeypatch.setattr(shutdown, '_complete_process_inventory', inventory)
    with pytest.raises((ValueError, OSError)):
        shutdown._parent_closed(f.state, f.record, f.context, False)


def test_real_escaped_live_campaign_process_blocks_dead_start_closure(dead_before_heartbeat):
    f = dead_before_heartbeat
    child = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(30)'],
        cwd=f.workspace, start_new_session=True, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with pytest.raises(ValueError): shutdown._parent_closed(f.state, f.record, f.context, False)
        assert child.poll() is None
    finally:
        child.terminate(); child.wait(timeout=3)
