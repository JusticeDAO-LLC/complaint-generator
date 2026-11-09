"""Independent negatives for stopped-before-heartbeat closure, all private.

Public stops and live-parent tests use real inert Python processes. Census
faults are explicit negative seams; they never manufacture successful history.
"""
from copy import deepcopy
import json
import os
import subprocess
import time

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import improvement_shutdown as shutdown
from tests.test_improvement_container_shutdown import campaign, docker, stamp
from tests.test_preheartbeat_shutdown import stopped_before_heartbeat, _REAL_INVENTORY, _bytes

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.mark.parametrize('stop_count', [2, 3])
def test_repeated_genuine_public_stop_retains_readonly_restart_eligibility(
        stopped_before_heartbeat, docker, monkeypatch, stop_count):
    """Repeated public stops must retain the original launch's provenance."""
    f = stopped_before_heartbeat
    before = _bytes(f)
    monkeypatch.setattr(shutdown, '_native_runtime', lambda: docker[1])
    for _ in range(stop_count - 1):
        stopped = runner.stop(f.state, timeout=.2)
        assert stopped['status'] == 'stopped' and stopped['signalled'] is False
        assert stopped['container_shutdown']['quiesced'] is True and not docker[0].effects
        record = json.loads((f.state / 'launcher.json').read_bytes())
        proof = json.loads((f.state / shutdown.RECEIPT_NAME).read_bytes())
        assert runner._shutdown_verified(record, proof, f.repo, f.state)
        assert record['identity'] == f.record['identity'] and record['started_at'] == f.record['started_at']
    # Only ordinary stop's two existing receipts may change. In particular,
    # old heartbeat, Native events, task state and counters are preserved.
    after_stop = _bytes(f)
    for name in set(before) | set(after_stop):
        if name not in {'launcher.json', shutdown.RECEIPT_NAME}:
            assert before.get(name) == after_stop.get(name), name
    monkeypatch.setattr(shutdown, '_native_runtime', lambda: pytest.fail('readonly reproof invoked Docker'))
    calls = []
    def inventory(cutoff):
        calls.append(cutoff)
        return _REAL_INVENTORY(cutoff)
    monkeypatch.setattr(shutdown, '_complete_process_inventory', inventory)
    result = shutdown._parent_closed(f.state, record, shutdown._context(f.state, record), False)
    assert result['source'] == 'owned_preheartbeat_stop_and_double_complete_proc_inventory'
    assert result['observations'] == 2 and len(calls) == 2
    assert result['signals_sent'] is result['attempt_refunded'] is result['completion_authority'] is False
    assert _bytes(f) == after_stop


def test_actual_live_launcher_birth_refuses_cached_stopped_receipt(
        stopped_before_heartbeat, monkeypatch):
    f = stopped_before_heartbeat
    child = subprocess.Popen(f.record['argv'], cwd=f.repo, start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        identity = None
        for _ in range(40):
            identity = runner.process_identity(child.pid)
            if identity and identity.get('argv') == f.record['argv']:
                break
            time.sleep(.025)
        assert identity and identity['argv'] == f.record['argv']
        record = {**deepcopy(f.record), 'identity': identity}
        runner._atomic_json(f.state / 'launcher.json', record)
        before = _bytes(f)
        with pytest.raises(ValueError, match='recorded campaign parent is still alive'):
            shutdown._parent_closed(f.state, record, shutdown._context(f.state, record), False)
        assert child.poll() is None and _bytes(f) == before
    finally:
        child.terminate()
        child.wait(timeout=3)


def test_fresh_census_recycled_numeric_parent_is_not_absence(
        stopped_before_heartbeat, monkeypatch):
    """A synthetic reused-PID census is rejection evidence, never authority."""
    f = stopped_before_heartbeat
    birth = f.record['identity']
    row = {'pid': birth['pid'], 'uid': os.getuid(), 'ppid': 1,
           'process_group': birth['pid'] + 1, 'session': birth['pid'] + 1,
           'start_ticks': birth['start_ticks'] + 1, 'argv': ('/usr/bin/python3',),
           'cwd': str(f.repo.parent), 'scope_metadata_required': True,
           'prelaunch_scope_excluded': False, 'foreign_cwd_proof': None}
    monkeypatch.setattr(shutdown, '_complete_process_inventory', lambda cutoff: [row])
    before = _bytes(f)
    with pytest.raises(ValueError):
        shutdown._parent_closed(f.state, f.record, f.context, False)
    assert _bytes(f) == before


def test_preheartbeat_does_not_borrow_retained_native_child_authority(
        stopped_before_heartbeat, monkeypatch):
    f = stopped_before_heartbeat
    monkeypatch.setattr(shutdown, '_complete_process_inventory', lambda cutoff: [])
    before = _bytes(f)
    with pytest.raises(ValueError):
        shutdown._parent_closed(f.state, f.record, f.context, False,
            retained_native_child_proof={'synthetic_forbidden_proof': True})
    assert _bytes(f) == before


@pytest.mark.parametrize('race', ['task_event', 'supervisor_event', 'pid_marker', 'identity_marker'])
def test_second_census_evidence_race_never_becomes_closure(
        stopped_before_heartbeat, monkeypatch, race):
    f = stopped_before_heartbeat
    calls = []
    def inventory(cutoff):
        calls.append(cutoff)
        if len(calls) == 2:
            if race in {'task_event', 'supervisor_event'}:
                name = ('complaint_intake_events.jsonl' if race == 'task_event'
                        else 'complaint_intake_supervisor_events.jsonl')
                with (f.state / name).open('a') as stream:
                    stream.write(json.dumps({'type': 'synthetic_late_native_event',
                        'timestamp': stamp(f.record['started_at'] + .1)}) + '\n')
            else:
                name = ('complaint_intake_managed_daemon.pid' if race == 'pid_marker'
                        else 'complaint_intake_managed_daemon.identity.json')
                (f.state / name).write_text('1073741826\n' if race == 'pid_marker' else '{}')
        return []
    monkeypatch.setattr(shutdown, '_complete_process_inventory', inventory)
    with pytest.raises((ValueError, OSError)):
        shutdown._parent_closed(f.state, f.record, f.context, False)
    assert len(calls) == 2
