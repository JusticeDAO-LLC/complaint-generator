"""Operator holds fence the real Native loop between passes, without task authority."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon_runner as native_loop


@pytest.mark.parametrize('marker', ['HOLD', 'OPERATOR_STOP'])
@pytest.mark.parametrize('kind', ['regular', 'directory', 'dangling_symlink'])
def test_marker_fences_native_pass_before_sizing_or_dispatch(tmp_path, monkeypatch, marker, kind):
    state = tmp_path/'campaign'; directory = state/'watchdog'; directory.mkdir(parents=True)
    path = directory/marker
    if kind == 'regular': path.write_text('opaque operator-owned hold\n')
    elif kind == 'directory': path.mkdir()
    else: path.symlink_to(directory/'missing-target')
    identity = path.lstat()
    calls, closed = [], []
    class Dispatch:
        def run_once(self): calls.append('dispatch'); raise AssertionError('dispatch under hold')
        def close_event_runtime(self): closed.append(True)
    def sizing(*args, **kwargs):
        calls.append('sizing'); raise AssertionError('sizing under hold')
    monkeypatch.setattr(runner, '_require_resource_capacity', sizing)
    context = native_loop.ImplementationDaemonRunContext(
        parsed=SimpleNamespace(once=True, daemon_hook_timeout_seconds=3, interval=1),
        state_path=state/'native.json', strategy_path=state/'strategy.json', events_path=state/'events.jsonl')
    before = b'{"implementation_attempts":{"synthetic-task":2}}'
    context.state_path.write_bytes(before)
    with pytest.raises(runner.CampaignOperatorHold) as refused:
        native_loop.run_portal_implementation_daemon_loop(Dispatch(), context, logger=runner._LOGGER,
            hooks=(runner._resource_admission_hook(tmp_path, state, tmp_path/'worktrees', {}),))
    assert refused.value.observation['marker'] == marker
    assert refused.value.observation['paid_dispatch'] is False
    assert refused.value.observation['accounting_changed'] is False
    assert refused.value.observation['attempt_refunded'] is False
    assert calls == [] and closed == [True]
    assert context.state_path.read_bytes() == before and not context.events_path.exists()
    assert path.lstat() == identity


def test_hold_arriving_during_sizing_fences_same_pass(tmp_path, monkeypatch):
    state = tmp_path/'campaign'; directory = state/'watchdog'; directory.mkdir(parents=True)
    def sizing(*args, **kwargs): (directory/'HOLD').write_text('created during admission')
    monkeypatch.setattr(runner, '_require_resource_capacity', sizing)
    monkeypatch.setattr(runner, '_worktree_capacity', lambda *args: {'sufficient': True})
    hook = runner._resource_admission_hook(tmp_path, state, tmp_path/'worktrees', {})
    with pytest.raises(runner.CampaignOperatorHold): hook.callback(None)
    assert (directory/'HOLD').read_text() == 'created during admission'


def test_hold_during_actual_child_pass_allows_finish_and_refuses_next_pass(tmp_path):
    """Real child + pinned Native loop; dispatch itself is an explicit inert sentinel."""
    root = Path(runner.__file__).resolve().parents[2]
    script = tmp_path/'child.py'
    script.write_text('''
import json, pathlib, sys, time
from types import SimpleNamespace
sys.path[:0] = ROOT_PATHS
from integrations.ipfs_accelerate import improvement_runner as runner
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon_runner as loop
p = pathlib.Path(sys.argv[1]); state=p/'campaign'; (state/'watchdog').mkdir(parents=True)
runner._require_resource_capacity=lambda *args, **kwargs: None
runner._worktree_capacity=lambda *args, **kwargs: {'sufficient': True}
class InertPass:
    def run_once(self):
        with (p/'passes').open('a') as out: out.write('entered\\n')
        (p/'entered').write_text('actual child pass is active')
        deadline=time.monotonic()+20
        while not (p/'release').exists():
            if time.monotonic()>deadline: raise RuntimeError('owned test timed out')
            time.sleep(.01)
        (p/'finished').write_text('current pass completed')
        return {'unchanged': True, 'write_count': 0}
    def close_event_runtime(self): (p/'closed').write_text('closed')
ctx=loop.ImplementationDaemonRunContext(parsed=SimpleNamespace(once=False,daemon_hook_timeout_seconds=3,interval=.01),
    state_path=state/'native.json',strategy_path=state/'strategy.json',events_path=state/'events.jsonl')
ctx.state_path.write_text('{"implementation_attempts":{"synthetic-task":2}}')
try:
    loop.run_portal_implementation_daemon_loop(InertPass(),ctx,logger=runner._LOGGER,
        hooks=(runner._resource_admission_hook(p,state,p/'worktrees',{}),))
except runner.CampaignOperatorHold as error:
    (p/'refused').write_text(json.dumps(error.observation))
else: raise RuntimeError('hold did not fence next pass')
'''.replace('ROOT_PATHS', repr([str(root), str(root/'external/ipfs_accelerate_py'),
    str(root/'external/ipfs_datasets_py'), str(root/'external/ipfs_kit_py')])))
    with (tmp_path/'child.log').open('w') as log:
        child = subprocess.Popen([sys.executable, '-I', '-B', str(script), str(tmp_path)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic()+20
            while not (tmp_path/'entered').exists():
                assert child.poll() is None, (tmp_path/'child.log').read_text()
                assert time.monotonic() < deadline
                time.sleep(.01)
            hold = tmp_path/'campaign/watchdog/HOLD'
            hold.write_text('opaque hold during active work')
            assert child.poll() is None and not (tmp_path/'closed').exists()
            (tmp_path/'release').write_text('finish the owned current pass')
            assert child.wait(timeout=10) == 0, (tmp_path/'child.log').read_text()
        finally:
            if child.poll() is None: child.terminate()
            child.wait(timeout=3)
    assert (tmp_path/'passes').read_text() == 'entered\n'
    assert (tmp_path/'finished').exists() and (tmp_path/'closed').exists()
    assert json.loads((tmp_path/'refused').read_text())['paid_dispatch'] is False
    assert (tmp_path/'campaign/native.json').read_text() == '{"implementation_attempts":{"synthetic-task":2}}'
    assert hold.read_text() == 'opaque hold during active work'
    assert not (tmp_path/'campaign/events.jsonl').exists()
