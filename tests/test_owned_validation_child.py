"""Actual Native-generated owner argv/leases and an inert real pytest collector.

All state is an authored private campaign. No provider, public campaign start,
task completion, or live state is invoked. Ownership predicates are not mocked.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _config(campaign, worker):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    root = Path(runner.__file__).resolve().parents[2]
    _, artifacts = runner._campaign_spec(root, root / 'docs/task_boards/complaint_gui_collaboration_spec.json')
    return native.PortalSupervisorConfig(todo_path=root / artifacts.board_relative,
        state_path=campaign / (runner.STATE_PREFIX + '_task_state.json'),
        strategy_path=campaign / (runner.STATE_PREFIX + '_strategy.json'),
        events_path=campaign / (runner.STATE_PREFIX + '_events.jsonl'), state_dir=campaign,
        repo_root=root, daemon_script_path=worker, worktree_root=campaign / 'worktrees',
        state_prefix=runner.STATE_PREFIX, task_prefix=runner.TASK_PREFIX,
        implementation_timeout=900, stale_seconds=180, check_interval=1,
        implementation_log_stall_seconds=180, implement=False)


def _supervisor(config):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    supervisor = object.__new__(runner._validation_aware_supervisor_class(native.PortalImplementationSupervisor))
    supervisor.config = config
    supervisor.board_namespace = config.todo_path.name
    supervisor._worktree_worker_phase = ''
    supervisor._last_worktree_worker_seen_monotonic = None
    return supervisor


def _worker(campaign, worker):
    """Executed only in the exact argv produced by Native's supervisor config."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as runtime
    config = _config(campaign, worker)
    supervisor = _supervisor(config)
    daemon = native.PortalImplementationDaemon(todo_path=config.todo_path, state_path=config.state_path,
        strategy_path=config.strategy_path, events_path=config.events_path, repo_root=config.repo_root,
        task_header_prefix=runner.TASK_PREFIX,
        worktree_root=config.worktree_root, board_namespace=supervisor.board_namespace, implement=False)
    tasks = daemon._load_tasks(); daemon._register_task_identities(tasks)
    task = next(t for t in tasks if t.task_id == 'CIMP-GUI-60')
    identity = daemon._identity_for_task(task)
    workspace = config.worktree_root / 'private-collect'; workspace.mkdir(parents=True)
    now = time.time(); stamp = lambda seconds: datetime.fromtimestamp(seconds, timezone.utc).isoformat()
    started = stamp(now - 1000)
    lease = daemon._build_implementation_lock_metadata(task, 1, started)
    claim = daemon._build_implementation_task_claim_metadata(task, 1, started)
    assert daemon._try_acquire_implementation_lock(daemon._implementation_lock_path(), lease)[0]
    assert daemon._try_acquire_implementation_task_claim(daemon._implementation_task_claim_path(
        task.task_id, canonical_task_cid=identity.canonical_task_cid), claim)[0]
    state = native.PortalTaskState()
    for key, value in dict(active_task_id=task.task_id, active_task_key=identity.canonical_task_key,
        active_task_cid=identity.canonical_task_cid, active_attempt=1, implementation_in_progress=True,
        active_phase='validating', active_phase_started_at=stamp(now - 1),
        active_worktree_path=str(workspace), last_implementation_task_id=task.task_id,
        last_implementation_started_at=started, last_implementation_finished_at='',
        heartbeat_at=started, last_progress_at=started).items():
        setattr(state, key, value)
    state.implementation_attempts = {task.task_id:1}
    state.implementation_attempts_by_cid = {identity.canonical_task_cid:1}
    runner._atomic_json(campaign / 'authored-state.json', vars(state))
    runtime.write_supervised_child_identity(supervisor._managed_daemon_identity_path(), pid=os.getpid(),
        command=runtime.read_process_command_argv(os.getpid()), owner_scope=supervisor._managed_daemon_owner_scope())
    supervisor._managed_daemon_pid_path().write_text(str(os.getpid()))
    (workspace / 'test_inert.py').write_text('def test_collected(): assert True\n')
    (workspace / 'conftest.py').write_text('''from pathlib import Path
import time
def pytest_sessionstart(session):
 root=Path(__file__).parent
 (root/'collect-ready').write_text('ready')
 while not (root/'collect-release').exists(): time.sleep(.01)
''')
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    with (campaign / 'collector.log').open('wb') as output:
        collect_started = time.time()
        child = subprocess.Popen([sys.executable, '-P', '-B', '-m', 'pytest', '--collect-only', '-q',
            '-p', 'no:cacheprovider', '--basetemp', str(campaign / 'collect-tmp'), 'test_inert.py'],
            cwd=workspace, env=env, stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 15
            while not (workspace / 'collect-ready').exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            assert (workspace / 'collect-ready').exists()
            runner._atomic_json(campaign / 'ready.json', {'child_pid':child.pid, 'owner_pid':os.getpid(),
                'collect_started_at':collect_started})
            while not (campaign / 'owner-release').exists():
                time.sleep(.01)
        finally:
            (workspace / 'collect-release').touch()
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=5)
    # Deliberately retain the real Native receipts for the dead-owner negative.
    # They are confined to this test's private temporary directory.


@contextmanager
def _world(tmp_path):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    campaign = tmp_path / 'campaign'; campaign.mkdir(mode=0o700)
    worker = tmp_path / 'inert_native_owner.py'
    root = Path(runner.__file__).resolve().parents[2]
    native_root = Path(native.__file__).resolve().parents[3]
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=native_root,text=True).strip() == subprocess.check_output(
        ['git','rev-parse','HEAD:external/ipfs_accelerate_py'],cwd=root,text=True).strip()
    assert Path(native.__file__).resolve() == native_root/'ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py'
    paths = [root, native_root, *(native_root.parent / name for name in ('ipfs_datasets_py','ipfs_kit_py'))]
    worker.write_text('import sys\nfrom pathlib import Path\nsys.path[:0]=' + repr(list(map(str, paths)))
        + '\nfrom tests.test_owned_validation_child import _worker\n_worker(Path(' + repr(str(campaign))
        + '),Path(__file__).resolve())\n')
    config = _config(campaign, worker); supervisor = _supervisor(config)
    command = supervisor._build_daemon_command()
    with (campaign / 'owner.log').open('wb') as output:
        process = subprocess.Popen(command, env=dict(os.environ), stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 25
            while not (campaign / 'ready.json').exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            assert (campaign / 'ready.json').exists(), (campaign / 'owner.log').read_text()[-1800:]
            state = native.PortalTaskState(**json.loads((campaign / 'authored-state.json').read_text()))
            yield SimpleNamespace(campaign=campaign, process=process, config=config, supervisor=supervisor, state=state)
        finally:
            (campaign / 'owner-release').touch()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)


def test_actual_native_owned_collect_child_keeps_initial_pulse_gap_and_refuses_stale_scope(tmp_path):
    from copy import deepcopy
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    with _world(tmp_path) as world:
        supervisor, state = world.supervisor, world.state
        before = deepcopy(vars(state)); now = time.time()
        ready = json.loads((world.campaign / 'ready.json').read_text())
        assert 0 <= now - ready['collect_started_at'] < 5
        assert not (world.campaign / 'validation-activity').exists()
        # Reproduce the exact scalar-string mismatch in the frozen SDK.
        rows = native.descendant_processes(world.process.pid)
        assert any(isinstance(row['cmdline'],str) and 'pytest' in row['cmdline'] for row in rows)
        assert supervisor._active_validation_subprocess_exists() is False
        assert native.PortalImplementationSupervisor._implementation_attempt_is_active(supervisor,state,now_ts=now) is False
        assert runner._owned_validation_window(supervisor,state,now_ts=now) is True
        assert vars(state) == before
        state.active_task_cid = 'wrong-canonical-task'
        assert runner._owned_validation_window(supervisor,state,now_ts=time.time()) is False
        state.active_task_cid = before['active_task_cid']
        state.active_phase_started_at = datetime.fromtimestamp(now-901,timezone.utc).isoformat()
        assert runner._owned_validation_window(supervisor,state,now_ts=time.time()) is False
        state.active_phase_started_at = before['active_phase_started_at']
        # A separate real marker-bearing process cannot stand in for this
        # owner's collector once that collector has returned.
        (Path(state.active_worktree_path) / 'collect-release').touch()
        deadline = time.monotonic() + 5
        while native.read_process_command_argv(ready['child_pid']) and time.monotonic() < deadline:
            time.sleep(.01)
        sentinel = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(15)', '--pytest-inert-sentinel'])
        try:
            assert sentinel.poll() is None
            assert runner._owned_validation_window(supervisor,state,now_ts=time.time()) is False
            assert sentinel.poll() is None
        finally:
            sentinel.terminate(); sentinel.wait(timeout=5)
        (world.campaign / 'owner-release').touch(); world.process.wait(timeout=15)
        assert runner._owned_validation_window(supervisor,state,now_ts=time.time()) is False

