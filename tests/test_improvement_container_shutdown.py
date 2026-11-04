"""Owned shutdown contracts; one inert native child, never a provider or Docker."""

from copy import deepcopy
from datetime import datetime, timezone
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


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
IMAGE = 'sha256:' + 'a' * 64
CONTAINER = 'b' * 64
OTHER_CONTAINER = 'c' * 64
_REAL_PROCESS_IDENTITY = runner.process_identity
_REAL_HISTORICAL_PROCESS_INVENTORY = shutdown._complete_process_inventory

# The one real-process control launches only this private inert wrapper and its
# one fixed worker. The wrapper uses the actual public native identity writer
# and launcher; all networking and every other subprocess are denied first.
SEALED_ORPHAN_WORKER = 'import time\ntime.sleep(45)\n'
SEALED_ORPHAN_WRAPPER = r'''
import json, os, pathlib, socket, sys, time
config = pathlib.Path(os.environ.pop('COMPLAINT_SHUTDOWN_FIXTURE_CONFIG'))
data = json.loads(config.read_text())
repo = pathlib.Path(data['repo'])
assert repo == pathlib.Path.cwd() and config.parent == repo.parent
command = data['command']
def audit(event, args):
    if event == 'socket.__new__' and args[1] in (socket.AF_INET, socket.AF_INET6):
        raise PermissionError('synthetic_shutdown_network_denied')
    if event in ('socket.connect','socket.sendto','socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr','socket.getnameinfo'):
        raise PermissionError('synthetic_shutdown_network_denied')
    if event == 'subprocess.Popen' and (list(args[1]) != command or args[2] != str(repo)):
        raise PermissionError('synthetic_shutdown_process_denied')
sys.addaudithook(audit)
sys.path[:0] = data['roots']
from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as native
record = data['record']
birth = native.read_process_birth(os.getpid())
assert birth and os.getsid(0) == os.getpid() == os.getpgrp()
record['identity'] = {'pid':birth.pid,'start_ticks':birth.start_time_ticks,
    'boot_id':birth.boot_id,'session':os.getsid(0),'process_group':os.getpgrp(),
    'argv':[sys.executable,*sys.argv]}
assert record['argv'] == record['identity']['argv']
record['started_at'] = time.time()
record['status'] = 'starting'
state = pathlib.Path(record['state_dir'])
def write(name, value):
    path = state / name
    path.write_text(json.dumps(value,sort_keys=True))
    path.chmod(0o600)
write('launcher.json',record)
# A separate kernel clock tick makes the child-after-parent rule deterministic.
time.sleep(.04)
scope = {'repo_root':str(repo),'state_dir':str(state),'state_prefix':'complaint_intake',
    'todo_path':record['board_path'],'daemon_entrypoint':command[1]}
pid_path = state / 'complaint_intake_managed_daemon.pid'
identity_path = native.supervised_child_identity_path(pid_path)
env = dict(os.environ)
env.update({native.SUPERVISED_CHILD_IDENTITY_PATH_ENV:str(identity_path),
    native.SUPERVISED_CHILD_OWNER_SCOPE_ENV:json.dumps(scope,sort_keys=True)})
child = native.launch_supervised_child(native.SupervisedChildSpec(repo_root=repo,
    command=tuple(command),log_path=state/'inert-daemon.log',child_pid_path=pid_path,
    env=env,start_new_session=True))
identity = native.load_supervised_child_identity(identity_path)
assert identity and identity.process_birth.parent_pid == os.getpid()
write('complaint_intake_supervisor_status.json',{'status':'termination_blocked',
    'repo_root':str(repo),'supervisor_pid':os.getpid(),
    'updated_at':identity.created_at,'daemon_pid':child.pid,
    'last_recycle_reason':'workspace_container_present','restart_count':0})
write('inert-ready.json',{'pid':child.pid,'identity_record_id':identity.record_id,
    'birth':identity.process_birth.to_dict(),
    'native_origin':str(pathlib.Path(native.__file__).resolve()),'guard_active':True})
'''


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    from integrations.ipfs_accelerate.improvement_plan import build_improvement_work_plan, load_spec
    repo = tmp_path / 'repository'
    spec = repo / runner.SPEC_RELATIVE
    spec.parent.mkdir(parents=True)
    spec.write_text(json.dumps({
        'schema_version': 'complaint-intake-improvement@1', 'title': 'Synthetic shutdown',
        'provider': {'router': 'ipfs_accelerate_py.llm_router', 'provider': 'grok_cli', 'model': 'grok-4.7', 'allow_fallback': False},
        'execution_policy': {'synthetic_only': True}, 'goals': [{'id': 'goal.tui', 'title': 'TUI', 'subgoals': [{'id': 'sub.tui', 'title': 'PTY'}]}],
        'tasks': [{'id': 'CIMP-TUI-01', 'title': 'Synthetic PTY', 'goal_id': 'goal.tui', 'subgoal_id': 'sub.tui',
                  'priority': 'P0', 'targets': ['tests/test_synthetic.py'], 'depends_on': [],
                  'acceptance': ['Synthetic PTY passes'], 'validation_commands': ['python -m pytest tests/test_synthetic.py'],
                  'implementation_prompt': 'Use only synthetic fixtures.'}],
    }))
    plan = build_improvement_work_plan(load_spec(spec)).plan_id
    state = tmp_path / 'epoch'
    state.mkdir(mode=0o700)
    workspace = state / 'worktrees/workspace_synthetic_01'
    workspace.mkdir(parents=True)
    started = time.time() - 60
    argv = [sys.executable, str(repo / 'scripts/run_complaint_improvement_supervisor.py'), '_run',
            '--repo-root', str(repo), '--spec', str(spec), '--state-dir', str(state),
            '--owner-token', 'synthetic-owner', '--merge-target', 'synthetic-campaign']
    identity = {'pid': 991115, 'start_ticks': 123456, 'boot_id': 'synthetic-boot',
                'session': 991115, 'process_group': 991115, 'argv': argv}
    record = {'schema_version': 'complaint-improvement-launcher@1', 'identity': identity, 'argv': argv,
              'owner_token': 'synthetic-owner', 'started_at': started, 'status': 'stopped',
              'repo_root': str(repo), 'spec_path': str(spec), 'state_dir': str(state),
              'board_path': str(repo / 'docs/task_boards/complaint_intake_task_board.md'),
              'plan_id': plan, 'provider': 'grok_cli', 'model': 'grok-4.7', 'allow_fallback': False,
              'merge_target': 'synthetic-campaign'}
    runner._atomic_json(state / 'launcher.json', record)
    event = {'type': 'implementation_started', 'event_id': 'sha256:' + 'd' * 64,
             'timestamp': stamp(started + 5), 'task_id': 'CIMP-TUI-01', 'canonical_task_cid': 'b' + 'a' * 58,
             'attempt': 1, 'worktree_path': str(workspace)}
    (state / 'complaint_intake_events.jsonl').write_text(json.dumps(event) + '\n')
    (state / 'complaint_intake_events.jsonl').chmod(0o664)
    runner._atomic_json(state / 'complaint_intake_supervisor_status.json', {
        'status': 'stopped', 'repo_root': str(repo), 'supervisor_pid': identity['pid'],
        'updated_at': stamp(started + 20), 'managed_daemon_cleanup': {'quiesced': True}})
    monkeypatch.setattr(runner, 'process_identity', lambda _pid: None)
    return SimpleNamespace(repo=repo, spec=spec, state=state, workspace=workspace,
                           record=record, event=event, started=started)


def container(campaign, identifier=CONTAINER, *, workspace=None):
    workspace = workspace or campaign.workspace
    return {'Id': identifier, 'Image': IMAGE, 'Created': stamp(campaign.started + 10),
            'Name': '/ipfs-accelerate-grok-991116-' + 'e' * 32,
            'WorkingDir': str(workspace), 'Label': 'true',
            'State': {'Status': 'running', 'Running': True, 'Restarting': False,
                      'Paused': False, 'Pid': 991116, 'StartedAt': stamp(campaign.started + 11)},
            'Mounts': [{'Type': 'bind', 'Source': str(workspace), 'Destination': str(workspace), 'RW': True}]}


class FakeDocker:
    def __init__(self, values=()):
        self.containers = {value['Id']: deepcopy(value) for value in values}
        self.effects = []
        self.calls = []
        self.ps_count = 0
        self.inspect_count = 0
        self.before_inspect = None
        self.before_ps = None
        self.failed_stop = False
        self.failed_remove = False
        self.inspect_unavailable = False
        self.timed_out = False

    def __call__(self, argv, **kwargs):
        assert argv[:2] == ['/trusted/native/docker', '--host=unix:///var/run/docker.sock']
        assert '--config' in argv
        assert kwargs['env'] == {'PATH': '/usr/bin'}
        assert 0 < kwargs['timeout'] <= 5
        op = argv[4]
        args = argv[5:]
        self.calls.append((op, args))
        if op == 'ps':
            if self.timed_out:
                raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
            self.ps_count += 1
            if self.before_ps:
                self.before_ps(self)
            return SimpleNamespace(returncode=0, stdout=''.join(value + '\n' for value in self.containers), stderr='')
        identifier = args[-1]
        if op == 'inspect':
            self.inspect_count += 1
            assert '.Config.Env' not in args[1] and '.Logs' not in args[1]
            if self.before_inspect:
                self.before_inspect(self, identifier)
            value = self.containers.get(identifier)
            if value is None or self.inspect_unavailable:
                return SimpleNamespace(returncode=1, stdout='', stderr='inspection unavailable')
            return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr='')
        self.effects.append((op, identifier))
        if op == 'stop':
            assert args == ['--time=3', identifier]
            if not self.failed_stop:
                self.containers[identifier]['State'].update(Status='exited', Running=False, Pid=0)
        elif op == 'rm':
            assert args == [identifier]  # Never --force or a mutable name.
            if not self.failed_remove:
                self.containers.pop(identifier)
        else:
            pytest.fail('unexpected Docker operation')
        return SimpleNamespace(returncode=0, stdout=identifier + '\n', stderr='')


@pytest.fixture
def docker(monkeypatch):
    fake = FakeDocker()
    native = SimpleNamespace(_docker_isolation_binary=lambda: '/trusted/native/docker',
        _docker_ordinary_task_toolchain_image_id=lambda *_args, **_kwargs: IMAGE,
        _docker_control_env=lambda: {'PATH': '/usr/bin'})
    monkeypatch.setattr(shutdown, '_native_runtime', lambda: native)
    monkeypatch.setattr(shutdown.subprocess, 'run', fake)
    return fake, native


def close(campaign, **kwargs):
    return shutdown.close_campaign_containers(campaign.state, campaign.record, **kwargs)


def test_historical_stopped_parent_closes_only_exact_owned_container(campaign, docker):
    fake, _ = docker
    fake.containers = {CONTAINER: container(campaign),
                       OTHER_CONTAINER: container(campaign, OTHER_CONTAINER, workspace=campaign.repo / 'other-workspace')}
    original_events = (campaign.state / 'complaint_intake_events.jsonl').read_bytes()
    result = close(campaign)
    assert result['status'] == 'stopped' and result['quiesced'] is True
    assert fake.effects == [('stop', CONTAINER), ('rm', CONTAINER)]
    assert list(fake.containers) == [OTHER_CONTAINER]
    assert (campaign.state / 'complaint_intake_events.jsonl').read_bytes() == original_events
    receipt = json.loads((campaign.state / shutdown.RECEIPT_NAME).read_text())
    assert receipt['plan_id'] == campaign.record['plan_id']
    assert receipt['owner_token_sha256'] == hashlib.sha256(campaign.record['owner_token'].encode()).hexdigest()
    assert receipt['containers'][0]['event_id'] == campaign.event['event_id']
    assert receipt['containers'][0]['created'] == stamp(campaign.started + 10)
    assert receipt['completion_authority'] is False and receipt['provider_callback_settled'] is False
    assert receipt['attempt_refunded'] is False and receipt['manual_holds_preserved'] is True


def test_legacy_process_only_record_never_acquires_docker_authority(tmp_path, monkeypatch):
    monkeypatch.setattr(shutdown, '_native_runtime', lambda: pytest.fail('legacy Docker call'))
    result = shutdown.close_campaign_containers(tmp_path, {'identity': {'pid': 1234}, 'started_at': time.time()})
    assert result['applicable'] is False and not result['quiesced']


@pytest.mark.parametrize('field,value', [('plan_id', 'other-plan'), ('state_dir', '/another/epoch'),
    ('repo_root', '/another/repository'), ('allow_fallback', True)])
def test_changed_launcher_binding_has_no_docker_effect(campaign, docker, field, value):
    campaign.record[field] = value
    runner._atomic_json(campaign.state / 'launcher.json', campaign.record)
    result = close(campaign)
    assert result['status'] == 'stop_incomplete' and not docker[0].calls


def test_launcher_file_changed_or_symlinked_has_no_authority(campaign, docker):
    owner = campaign.state / 'launcher.json'
    moved = campaign.state / 'owner-copy.json'
    owner.rename(moved)
    owner.symlink_to(moved)
    assert close(campaign)['status'] == 'stop_incomplete'
    assert not docker[0].calls


@pytest.mark.parametrize('mutation', ['old_event', 'escaping_workspace', 'symlink_workspace', 'wrong_image', 'missing_label', 'before_launch', 'future_created', 'missing_mount'])
def test_unbound_campaign_container_never_receives_effect(campaign, docker, mutation):
    fake, _ = docker
    value = container(campaign)
    if mutation == 'old_event':
        campaign.event['timestamp'] = stamp(campaign.started - 10)
        (campaign.state / 'complaint_intake_events.jsonl').write_text(json.dumps(campaign.event) + '\n')
    elif mutation == 'escaping_workspace':
        campaign.event['worktree_path'] = str(campaign.repo / 'elsewhere')
        (campaign.state / 'complaint_intake_events.jsonl').write_text(json.dumps(campaign.event) + '\n')
    elif mutation == 'symlink_workspace':
        campaign.workspace.rmdir()
        campaign.workspace.symlink_to(campaign.repo, target_is_directory=True)
    elif mutation == 'wrong_image':
        value['Image'] = 'sha256:' + 'f' * 64
    elif mutation == 'missing_label':
        value['Label'] = None
    elif mutation == 'before_launch':
        value['Created'] = stamp(campaign.started - 1)
    elif mutation == 'future_created':
        value['Created'] = stamp(time.time() + 60)
    elif mutation == 'missing_mount':
        value['Mounts'] = []
    fake.containers[CONTAINER] = value
    assert close(campaign)['status'] == 'stop_incomplete'
    assert not fake.effects


def test_container_immutable_identity_is_rechecked_before_stop(campaign, docker):
    fake, _ = docker
    fake.containers[CONTAINER] = container(campaign)
    def replace_identity(fake, identifier):
        if fake.inspect_count == 2:
            fake.containers[identifier]['Created'] = stamp(campaign.started + 12)
    fake.before_inspect = replace_identity
    assert close(campaign)['status'] == 'stop_incomplete'
    assert not fake.effects


@pytest.mark.parametrize('failure', ['inspection', 'stop', 'remove', 'image', 'docker', 'timeout'])
def test_unknown_docker_closure_cannot_claim_stopped(campaign, docker, failure):
    fake, native = docker
    fake.containers[CONTAINER] = container(campaign)
    if failure == 'inspection': fake.inspect_unavailable = True
    elif failure == 'stop': fake.failed_stop = True
    elif failure == 'remove': fake.failed_remove = True
    elif failure == 'image': native._docker_ordinary_task_toolchain_image_id = lambda *_args, **_kwargs: ''
    elif failure == 'docker': native._docker_isolation_binary = lambda: ''
    elif failure == 'timeout': fake.timed_out = True
    result = close(campaign)
    assert result['status'] == 'stop_incomplete' and result['quiesced'] is False


def test_inventory_is_bounded(campaign, docker):
    fake, _ = docker
    fake.containers = {f'{number:064x}': {} for number in range(shutdown.MAX_CONTAINERS + 1)}
    assert close(campaign)['status'] == 'stop_incomplete'
    assert not fake.effects


@pytest.mark.parametrize('empty_stream', [False, True])
def test_startup_without_task_events_still_observes_empty_docker_inventory(campaign, docker, empty_stream):
    events = campaign.state / 'complaint_intake_events.jsonl'
    if empty_stream:
        events.write_text('')
    else:
        events.unlink()
    result = close(campaign)
    assert result['quiesced'] is True
    assert docker[0].ps_count == 2 and not docker[0].effects


def test_dead_parent_without_owned_shutdown_evidence_is_incomplete(campaign, docker):
    (campaign.state / 'complaint_intake_supervisor_status.json').unlink()
    assert close(campaign)['status'] == 'stop_incomplete'
    assert not docker[0].calls


def test_second_inventory_closes_container_created_during_parent_stop(campaign, docker):
    fake, _ = docker
    def late_create(fake):
        if fake.ps_count == 2:
            fake.containers[CONTAINER] = container(campaign)
    fake.before_ps = late_create
    result = close(campaign, parent_quiesced=True)
    assert result['quiesced'] is True
    assert fake.effects == [('stop', CONTAINER), ('rm', CONTAINER)]


def test_optional_retention_requires_observed_nonrunning_state(campaign, docker):
    fake, _ = docker
    fake.containers[CONTAINER] = container(campaign)
    result = close(campaign, remove_stopped=False)
    assert result['quiesced'] is True
    assert fake.effects == [('stop', CONTAINER)]
    assert fake.containers[CONTAINER]['State']['Running'] is False
    assert all(not item['removed'] for item in result['containers'])


def test_stop_checks_docker_even_when_original_launcher_is_dead(campaign, docker):
    fake, _ = docker
    fake.containers[CONTAINER] = container(campaign)
    result = runner.stop(campaign.state, timeout=0)
    assert result['status'] == 'stopped' and result['signalled'] is False
    assert fake.effects == [('stop', CONTAINER), ('rm', CONTAINER)]


def test_stop_never_returns_stopped_when_container_fence_is_unknown(campaign, docker):
    fake, _ = docker
    fake.containers[CONTAINER] = container(campaign)
    fake.failed_stop = True
    assert runner.stop(campaign.state, timeout=0)['status'] == 'stop_incomplete'


def test_live_process_stop_checks_containers_after_birth_bound_signals(campaign, docker, monkeypatch):
    fake, _ = docker
    current = {campaign.record['identity']['pid']: campaign.record['identity']}
    monkeypatch.setattr(runner, 'process_identity', lambda pid: current.get(pid))
    monkeypatch.setattr(runner, '_descendants', lambda _identity: [])
    def signal_birth(identity, _signal):
        current.pop(identity['pid'], None)
        fake.containers[CONTAINER] = container(campaign)
        return True
    monkeypatch.setattr(runner, '_signal_birth', signal_birth)
    result = runner.stop(campaign.state, timeout=0)
    assert result['status'] == 'stopped' and result['signalled'] is True
    assert fake.effects == [('stop', CONTAINER), ('rm', CONTAINER)]


def configure_external(campaign):
    target = campaign.state.parent / 'private-worktree-root'
    target.mkdir(mode=0o700)
    binding = runner._validate_worktree_root(campaign.repo, campaign.state, target, claim=True)
    campaign.record.update(worktree_root=str(target), worktree_root_binding=binding)
    campaign.record['argv'].extend(['--worktree-root', str(target)])
    campaign.record['identity']['argv'] = campaign.record['argv'][:]
    runner._atomic_json(campaign.state / 'launcher.json', campaign.record)
    campaign.workspace = target / 'workspace_synthetic_01'
    campaign.workspace.mkdir()
    campaign.event['worktree_path'] = str(campaign.workspace)
    (campaign.state / 'complaint_intake_events.jsonl').write_text(json.dumps(campaign.event) + '\n')
    return target


def test_configured_root_closes_only_current_bound_workers_and_preserves_legacy_root(campaign, docker):
    old_workspace = campaign.workspace
    target = configure_external(campaign)
    fake, _ = docker
    fake.containers = {CONTAINER: container(campaign),
                       OTHER_CONTAINER: container(campaign, OTHER_CONTAINER, workspace=old_workspace)}
    original_events = (campaign.state / 'complaint_intake_events.jsonl').read_bytes()
    result = close(campaign)
    assert result['status'] == 'stopped' and result['quiesced'] is True
    assert result['worktree_root'] == str(target)
    assert result['worktree_root_binding'] == campaign.record['worktree_root_binding']
    assert fake.effects == [('stop', CONTAINER), ('rm', CONTAINER)]
    assert OTHER_CONTAINER in fake.containers and old_workspace.is_dir()
    assert (campaign.state / 'complaint_intake_events.jsonl').read_bytes() == original_events


@pytest.mark.parametrize('mutation', ['record_missing', 'flag_missing', 'flag_duplicate', 'marker_corrupt', 'directory_replaced'])
def test_configured_root_unknown_custody_refuses_all_docker_effects(campaign, docker, mutation):
    target = configure_external(campaign)
    if mutation == 'record_missing':
        campaign.record.pop('worktree_root_binding')
    elif mutation == 'flag_missing':
        campaign.record['argv'] = campaign.record['argv'][:-2]
    elif mutation == 'flag_duplicate':
        campaign.record['argv'] += ['--worktree-root', str(target)]
    elif mutation == 'marker_corrupt':
        (target / runner.WORKTREE_MARKER).write_text('{}')
    else:
        target.rename(target.with_name('preserved-original-root'))
        target.mkdir(mode=0o700)
    runner._atomic_json(campaign.state / 'launcher.json', campaign.record)
    assert close(campaign)['status'] == 'stop_incomplete'
    assert not docker[0].calls and not docker[0].effects


def test_directory_swap_during_container_observation_cannot_grant_stop_authority(campaign, docker):
    target = configure_external(campaign)
    fake, _ = docker
    fake.containers = {CONTAINER: container(campaign)}
    def swap(*unused):
        fake.before_inspect = None
        target.rename(target.with_name('preserved-before-swap'))
        target.mkdir(mode=0o700)
    fake.before_inspect = swap
    result = close(campaign)
    assert result['status'] == 'stop_incomplete' and not fake.effects


def test_legacy_root_is_not_reinterpreted_from_current_ambient_configuration(campaign, docker, monkeypatch):
    monkeypatch.setenv('IPFS_ACCELERATE_AGENT_WORKTREE_ROOT', '/foreign/root')
    fake, _ = docker
    fake.containers = {CONTAINER: container(campaign)}
    result = close(campaign)
    assert result['status'] == 'stopped'
    assert result['worktree_root'] == str(campaign.state / 'worktrees')
    assert result['worktree_root_binding'] is None
    assert fake.effects == [('stop', CONTAINER), ('rm', CONTAINER)]


@pytest.mark.parametrize('proof', ['missing', 'wrong_owner', 'not_quiesced', 'live_parent'])
def test_switching_legacy_root_requires_old_launch_closure_and_dead_owner(campaign, docker, monkeypatch, proof):
    target = campaign.state.parent / 'new-root'
    target.mkdir(mode=0o700)
    if proof != 'missing':
        assert close(campaign)['quiesced'] is True
        receipt = campaign.state / shutdown.RECEIPT_NAME
        body = json.loads(receipt.read_text())
        if proof == 'wrong_owner':
            body['owner_token_sha256'] = 'f' * 64
        elif proof == 'not_quiesced':
            body['quiesced'] = False
        runner._atomic_json(receipt, body)
    if proof == 'live_parent':
        monkeypatch.setattr(runner, 'process_identity', lambda _pid: campaign.record['identity'])
    before = (campaign.state / 'launcher.json').read_bytes()
    with pytest.raises(ValueError, match='closure-verified'):
        runner._select_worktree_root(campaign.repo, campaign.state, campaign.record, target)
    assert (campaign.state / 'launcher.json').read_bytes() == before
    assert not (target / runner.WORKTREE_MARKER).exists()


def test_stopped_legacy_launch_can_choose_new_root_without_changing_old_epoch_history(campaign, docker):
    target = campaign.state.parent / 'new-root'
    target.mkdir(mode=0o700)
    assert close(campaign)['quiesced'] is True
    original = {name: (campaign.state / name).read_bytes() for name in
                ['launcher.json', 'complaint_intake_events.jsonl', 'complaint_intake_supervisor_status.json']}
    root, binding = runner._select_worktree_root(campaign.repo, campaign.state, campaign.record, target)
    assert root == target and binding['state_dir'] == str(campaign.state)
    assert not (target / runner.WORKTREE_MARKER).exists()  # Doctor is read-only.
    assert original == {name: (campaign.state / name).read_bytes() for name in original}
    assert campaign.workspace.is_dir()


@pytest.mark.parametrize("independent_campaign", [False, True])
def test_native_fenced_orphan_session_allows_public_stop_without_rewriting_heartbeat(campaign, monkeypatch, independent_campaign):
    """One real sealed daemon/fence; reused or unknown custody stays refused."""
    import ctypes
    from dataclasses import replace
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import core
    from integrations.ipfs_accelerate import improvement_recovery as recovery

    monkeypatch.setattr(runner, 'process_identity', _REAL_PROCESS_IDENTITY)
    root, state, repo = campaign.state.parent, campaign.state, campaign.repo
    if independent_campaign:
        from integrations.ipfs_accelerate.improvement_plan import build_improvement_work_plan, load_spec
        relative = 'docs/task_boards/synthetic_shutdown_campaign.json'
        material = json.loads(campaign.spec.read_text())
        material['campaign'] = {'spec_relative': relative,
            'plan_relative': 'docs/task_boards/synthetic_shutdown_plan.json',
            'board_relative': 'docs/task_boards/synthetic_shutdown_board.md',
            'board_namespace': 'synthetic-independent-shutdown'}
        campaign.spec = repo / relative
        campaign.spec.write_text(json.dumps(material))
        campaign.record['spec_path'] = str(campaign.spec)
        campaign.record['board_path'] = str(repo / material['campaign']['board_relative'])
        campaign.record['plan_id'] = build_improvement_work_plan(load_spec(campaign.spec)).plan_id
        index = campaign.record['argv'].index('--spec')
        campaign.record['argv'][index + 1] = str(campaign.spec)
        campaign.record['identity']['argv'] = campaign.record['argv'][:]
        runner._atomic_json(state / 'launcher.json', campaign.record)
    for name in ('scripts', 'integrations/ipfs_accelerate'):
        (repo / name).mkdir(parents=True, exist_ok=True)
    repo.chmod(0o700)
    worker = repo / 'integrations/ipfs_accelerate/improvement_runner.py'
    wrapper = repo / 'scripts/run_complaint_improvement_supervisor.py'
    worker.write_text(SEALED_ORPHAN_WORKER); worker.chmod(0o600)
    wrapper.write_text(SEALED_ORPHAN_WRAPPER); wrapper.chmod(0o600)
    # Compare with the real Native producer, not a hand-written command or
    # a permissive fake identity/guard. No run/start/provider API is invoked.
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as producer
    from integrations.ipfs_accelerate.campaign import campaign_artifacts
    from integrations.ipfs_accelerate.improvement_plan import load_spec
    artifacts = campaign_artifacts(load_spec(campaign.spec))
    monkeypatch.setenv('IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR', str(state / 'control-plane'))
    native_config = producer.supervisor_config_from_args(producer.parse_args(
        runner.native_argv(Path(campaign.record['board_path']), state, campaign.record['merge_target'],
            board_namespace=artifacts.board_namespace, protected_paths=artifacts.protected_paths)),
        repo_root=repo, daemon_script_path=worker)
    owner = producer.PortalImplementationSupervisor(native_config)
    command = owner._build_daemon_command()
    del owner
    assert tuple(command) == shutdown._managed_native_command(campaign.record,
        shutdown._context(state, campaign.record))
    config = root / 'sealed-orphan-config.json'
    config.write_text(json.dumps({'repo': str(repo), 'record': campaign.record,
        'command': command, 'roots': [str(Path(__file__).resolve().parents[1]),
                                    str(Path(native.__file__).resolve().parents[3])]}))
    config.chmod(0o600)
    home, temporary = root / 'private-home', root / 'private-temporary'
    home.mkdir(mode=0o700); temporary.mkdir(mode=0o700)
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL') if key in os.environ}
    env.update({'HOME': str(home), 'TMPDIR': str(temporary),
        'COMPLAINT_SHUTDOWN_FIXTURE_CONFIG': str(config),
        'COMMON_CRAWL_AUTO_CLONE_SOURCE': '0', 'IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD': '0',
        'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
        'IPFS_DATASETS_PY_MINIMAL_IMPORTS': '1', 'PYTHONDONTWRITEBYTECODE': '1',
        'IPFS_ACCELERATE_META_INDEX_DUCKDB': '', 'IPFS_ACCELERATE_META_INDEX_DUCKLAKE': '',
        'IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR': str(state / 'control-plane')})
    # Adopt only this fixture's orphan so the real public native fence can
    # reap it deterministically, independently of PID1's reaping policy.
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    parent = child = None
    pid_path = state / 'complaint_intake_managed_daemon.pid'
    sidecar = native.supervised_child_identity_path(pid_path)
    try:
        error_fd = os.open(root / 'inert-wrapper.stderr', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(error_fd, 'wb') as errors:
            parent = subprocess.Popen(campaign.record['argv'], cwd=repo, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors,
                start_new_session=True)
            assert parent.wait(timeout=15) == 0
        record = json.loads((state / 'launcher.json').read_text())
        identity = native.load_supervised_child_identity(sidecar)
        assert identity is not None and identity.process_birth.parent_pid == parent.pid
        assert identity.command == tuple(command)
        assert record['identity']['pid'] == parent.pid and not (Path('/proc') / str(parent.pid)).exists()
        assert record['status'] == 'starting'
        ready = json.loads((state / 'inert-ready.json').read_text())
        assert ready['guard_active'] is True and ready['identity_record_id'] == identity.record_id
        assert ready['birth'] == identity.process_birth.to_dict()
        assert ready['native_origin'] == str(Path(native.__file__).resolve())
        child = native.SupervisedChild(pid=identity.process_birth.pid, command=identity.command,
            log_path=state / 'inert-daemon.log', child_pid_path=pid_path, identity_path=sidecar,
            identity_record_id=identity.record_id, identity_process_birth=identity.process_birth,
            owned_process_group_id=identity.process_birth.pid)
        context = shutdown._context(state, record)
        assert context is not None
        heartbeat = state / 'complaint_intake_supervisor_status.json'
        original = {path: path.read_bytes() for path in (sidecar, pid_path, heartbeat)}
        original_modes = {path: path.stat().st_mode & 0o777 for path in original}
        with pytest.raises(ValueError, match='not proven absent'):
            shutdown._parent_closed(state, record, context, False)
        assert native.supervised_child_identity_liveness(identity) is native.OwnerLiveness.ALIVE
        orphan_fence = shutdown.fence_owned_orphan_native_child(state, record)
        assert orphan_fence['status'] == 'fenced' and orphan_fence['fenced'] is True
        assert orphan_fence['markers_preserved'] is True
        try:
            os.waitpid(child.pid, 0)
        except ChildProcessError:
            pass
        assert not (Path('/proc') / str(child.pid)).exists()
        assert original == {path: path.read_bytes() for path in original}

        def save_identity(value):
            if value == identity:
                sidecar.write_bytes(original[sidecar]); pid_path.write_bytes(original[pid_path])
                sidecar.chmod(original_modes[sidecar]); pid_path.chmod(original_modes[pid_path])
                return
            sidecar.write_text(json.dumps(value.to_dict())); sidecar.chmod(0o600)
            pid_path.write_text(f'{value.process_birth.pid}\n'); pid_path.chmod(0o600)

        kit_index = identity.command.index('external/ipfs_kit_py')
        namespace_index = identity.command.index('--board-namespace') + 1
        protected_mutations = []
        if independent_campaign:
            protected_index = identity.command.index('--implementation-protected-path')
            protected_mutations = [
                replace(identity, command=identity.command[:protected_index]
                    + identity.command[protected_index + 2:], record_id=''),
                replace(identity, command=identity.command[:protected_index + 1]
                    + ('docs/task_boards/unrelated.json',)
                    + identity.command[protected_index + 2:], record_id=''),
                replace(identity, command=(*identity.command, '--implementation-protected-path',
                    'docs/task_boards/unrelated.json'), record_id=''),
            ]
        mutations = [*protected_mutations,
            replace(identity, command=identity.command[:namespace_index] + ('unrelated-namespace',)
                + identity.command[namespace_index + 1:], record_id=''),
            replace(identity, command=identity.command[:kit_index - 1] + identity.command[kit_index + 1:], record_id=''),
            replace(identity, command=(*identity.command, '--worktree-submodule-path', 'external/unrelated'), record_id=''),
            replace(identity, owner_scope={**identity.owner_scope, 'state_dir': str(root / 'foreign')}, record_id=''),
            replace(identity, command=(*identity.command, '--foreign-option'), record_id=''),
            replace(identity, created_at=stamp(record['started_at'] - 1), record_id=''),
            replace(identity, process_birth=replace(identity.process_birth, parent_pid=os.getpid()), record_id=''),
            replace(identity, process_birth=replace(identity.process_birth, boot_id='foreign-boot'), record_id=''),
            replace(identity, process_birth=replace(identity.process_birth,
                start_time_ticks=record['identity']['start_ticks']), record_id=''),
        ]
        for value in mutations:
            save_identity(value)
            with pytest.raises(ValueError): shutdown._parent_closed(state, record, context, False)
        # A real unrelated live process is the sentinel for a reused numeric
        # child PID. Native DEAD-by-birth alone must never authorize closure.
        sentinel = native.read_process_birth(os.getpid())
        reused = replace(identity, process_birth=replace(identity.process_birth,
            pid=os.getpid(), start_time_ticks=identity.process_birth.start_time_ticks), record_id='')
        save_identity(reused)
        assert native.supervised_child_identity_liveness(reused) is native.OwnerLiveness.DEAD
        with pytest.raises(ValueError, match='not proven absent'):
            shutdown._parent_closed(state, record, context, False)
        assert native.read_process_birth(os.getpid()) == sentinel
        save_identity(identity)
        # A reused launcher PID also remains unavailable, even though its old
        # recorded birth differs from the live unrelated sentinel.
        launcher_path = state / 'launcher.json'
        original_launcher = launcher_path.read_bytes()
        reused_parent = deepcopy(record)
        reused_parent['identity'].update(pid=os.getpid(), start_ticks=sentinel.start_time_ticks + 1,
            session=os.getpid(), process_group=os.getpid())
        launcher_path.write_text(json.dumps(reused_parent))
        reused_heartbeat = json.loads(original[heartbeat])
        reused_heartbeat['supervisor_pid'] = os.getpid()
        heartbeat.write_text(json.dumps(reused_heartbeat))
        save_identity(replace(identity, process_birth=replace(identity.process_birth,
            parent_pid=os.getpid()), record_id=''))
        with pytest.raises(ValueError, match='not proven absent'):
            shutdown._parent_closed(state, reused_parent, shutdown._context(state, reused_parent), False)
        launcher_path.write_bytes(original_launcher)
        heartbeat.write_bytes(original[heartbeat])
        save_identity(identity)
        with monkeypatch.context() as denied:
            denied.setattr(core, '_process_identity_snapshot', lambda: SimpleNamespace(available=False, processes={}))
            with pytest.raises(ValueError, match='not proven absent'):
                shutdown._parent_closed(state, record, context, False)
        with monkeypatch.context() as denied:
            denied.setattr(core, '_process_identity_snapshot', lambda: SimpleNamespace(available=True,
                processes={os.getpid(): ('S', 1, child.pid, child.pid, str(sentinel.start_time_ticks))}))
            with pytest.raises(ValueError, match='not proven absent'):
                shutdown._parent_closed(state, record, context, False)
        actual_session_check = native._supervised_child_identity_session_quiesced
        with monkeypatch.context() as racing:
            def changed_marker(value):
                pid_path.write_text('1\n')
                return actual_session_check(value)
            racing.setattr(native, '_supervised_child_identity_session_quiesced', changed_marker)
            with pytest.raises(ValueError, match='custody changed'):
                shutdown._parent_closed(state, record, context, False)
        save_identity(identity)
        sidecar.write_text('{}')
        with pytest.raises(ValueError, match='identity is invalid'):
            shutdown._parent_closed(state, record, context, False)
        save_identity(identity)
        retained = sidecar.with_suffix('.retained')
        sidecar.rename(retained)
        with pytest.raises(OSError): shutdown._parent_closed(state, record, context, False)
        sidecar.symlink_to(retained)
        with pytest.raises((OSError, ValueError)): shutdown._parent_closed(state, record, context, False)
        sidecar.unlink(); retained.rename(sidecar)
        shutdown._parent_closed(state, record, context, False)
        assert heartbeat.read_bytes() == original[heartbeat]
        # Use the ordinary public stop path after the independent native fence.
        # Docker is fake/empty; it must generate its own fresh closure receipt.
        fake = FakeDocker()
        docker_runtime = SimpleNamespace(_docker_isolation_binary=lambda: '/trusted/native/docker',
            _docker_ordinary_task_toolchain_image_id=lambda *_a, **_k: IMAGE,
            _docker_control_env=lambda: {'PATH': '/usr/bin'})
        monkeypatch.setattr(shutdown, '_native_runtime', lambda: docker_runtime)
        monkeypatch.setattr(shutdown.subprocess, 'run', fake)
        result = runner.stop(state, timeout=0)
        assert result['status'] == 'stopped' and result['signalled'] is False
        stopped_record = json.loads((state / 'launcher.json').read_text())
        assert stopped_record['status'] == 'stopped'
        assert heartbeat.read_bytes() == original[heartbeat]
        assert json.loads((state / shutdown.RECEIPT_NAME).read_text())['quiesced'] is True
        assert fake.effects == [] and fake.ps_count == 2
        assert recovery._campaign_process_argv(command, repo_root=repo, state_dir=state)
        for unrelated in ([sys.executable, str(root / 'foreign/improvement_runner.py'), *command[2:]],
                          ['bash', '-lc', ' '.join(command)],
                          [*command, '--state-dir', str(state)],
                          [part if part != str(state) else str(root / 'foreign-state') for part in command]):
            assert not recovery._campaign_process_argv(unrelated, repo_root=repo, state_dir=state)
        # A complete process inventory must also catch another actual custom
        # daemon command outside the retained leader's now-absent session.
        # No third actor is launched: this negative supplies only a closed,
        # synthetic read-only /proc observation to the existing scan.
        real_path = Path
        def inventory(argv):
            class Entry:
                name = '991125'
                def stat(self):
                    return SimpleNamespace(st_uid=os.getuid())
                def __truediv__(self, key):
                    assert key == 'cmdline'
                    return SimpleNamespace(read_bytes=lambda: ('\0'.join(argv) + '\0').encode())
            return SimpleNamespace(iterdir=lambda: iter([Entry()]))
        with monkeypatch.context() as extra:
            extra.setattr(recovery, 'Path', lambda value: inventory(command) if str(value) == '/proc' else real_path(value))
            with pytest.raises(ValueError, match='old campaign daemon/provider processes remain'):
                recovery._assert_processes_absent(state, state / 'worktrees', stopped_record, {}, json.loads(original[heartbeat]))
        with monkeypatch.context() as unrelated:
            unrelated.setattr(recovery, 'Path', lambda value: inventory(['bash', '-lc', ' '.join(command)])
                if str(value) == '/proc' else real_path(value))
            assert recovery._assert_processes_absent(state, state / 'worktrees', stopped_record, {},
                json.loads(original[heartbeat]))['matching_processes'] == 0
        projection = recovery._assert_processes_absent(state, state / 'worktrees', stopped_record, {},
            json.loads(original[heartbeat]))
        assert projection == {'old_births_alive': False, 'matching_processes': 0, 'native_shutdown_quiesced': True}
        assert original == {path: path.read_bytes() for path in original}
        # A crash may remove both canonical markers after the actual public
        # native fence. Historical running status remains historical; the new
        # verifier must establish closure without reconstructing either file.
        missing_record = deepcopy(record)
        runner._atomic_json(state / 'launcher.json', missing_record)
        running = _missing_marker_heartbeat(state, missing_record, child.pid)
        runner._atomic_json(heartbeat, running)
        # Preserve the actual sealed identity, then use the public Native
        # cleanup API. The archive remains observation input, never a marker.
        archive = root / 'retained-native-identity.json'
        archive.write_bytes(original[sidecar]); archive.chmod(0o600)
        cleared = native.clear_child_pid_file(child)
        assert cleared is True and not pid_path.exists() and not sidecar.exists()
        public_clear = root / 'public-native-clear-result.json'
        public_clear.write_text(json.dumps({'native_api': 'clear_child_pid_file',
            'returned': cleared, 'canonical_pid_absent': not pid_path.exists(),
            'canonical_identity_absent': not sidecar.exists(),
            'signals_performed': False, 'completion_authority': False}))
        public_clear.chmod(0o600)
        def reference(path):
            return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        effect = {'schema': 'complaint-public-native-marker-clear-observation@1',
            'api': 'supervisor_runtime.clear_child_pid_file', 'identity_record_id': identity.record_id,
            'identity_sha256': reference(archive)['sha256'],
            'launch_binding_sha256': shutdown._retained_launch_binding(missing_record,
                shutdown._context(state, missing_record)),
            'native_source': reference(Path(native.__file__).resolve()),
            'canonical_pid_path': str(pid_path), 'canonical_identity_path': str(sidecar),
            'result': reference(public_clear)}
        effect_path = root / 'public-native-clear-observation.json'
        effect_path.write_text(json.dumps(effect)); effect_path.chmod(0o600)
        retained_proof = {'schema': 'complaint-retained-native-child-observation@1',
            'identity': reference(archive), 'effect': reference(effect_path),
            'worktree_submodule_paths': ['external/ipfs_datasets_py', 'external/ipfs_kit_py']}
        running_bytes = heartbeat.read_bytes()
        missing_context = shutdown._context(state, missing_record)
        observed = shutdown._parent_closed(state, missing_record, missing_context, False)
        assert observed['proc_census_complete'] is True and observed['observations'] == 2
        assert observed['minimum_owned_start_ticks'] == record['identity']['start_ticks']
        assert observed['all_births_group_and_session_checked'] is True
        assert len(observed['prelaunch_scope_exclusions']) == 2
        assert all(type(count) is int and count >= 0 for count in observed['prelaunch_scope_exclusions'])
        assert observed['sealed_native_identity_used'] is False
        assert observed['daemon_birth_ticks_claimed'] is False and observed['signals_sent'] is False
        fake.calls.clear(); fake.ps_count = 0
        stopped = runner.stop(state, timeout=0)
        assert stopped['status'] == 'stopped' and stopped['signalled'] is False
        missing_stopped = json.loads((state / 'launcher.json').read_text())
        assert missing_stopped['status'] == 'stopped'
        receipt = json.loads((state / shutdown.RECEIPT_NAME).read_text())
        assert receipt['quiesced'] is True and receipt['process_closure']['observations'] == 2
        assert fake.effects == [] and fake.ps_count == 2
        assert heartbeat.read_bytes() == running_bytes
        assert not pid_path.exists() and not sidecar.exists()
        assert recovery._assert_processes_absent(state, state / 'worktrees', missing_stopped, {},
            running) == {'old_births_alive': False, 'matching_processes': 0, 'native_shutdown_quiesced': True}
        assert heartbeat.read_bytes() == running_bytes
        assert not pid_path.exists() and not sidecar.exists()
        # The real Native final heartbeat can lose daemon_pid after a blocked
        # exit. Null remains refused without explicit retained observation.
        null_heartbeat = {**running, 'status': 'termination_blocked', 'daemon_pid': None}
        runner._atomic_json(heartbeat, null_heartbeat)
        null_bytes = heartbeat.read_bytes()
        current_record = json.loads((state / 'launcher.json').read_text())
        current_context = shutdown._context(state, current_record)
        with pytest.raises(ValueError, match='full launch scope'):
            shutdown._parent_closed(state, current_record, current_context, False)
        observed = shutdown._parent_closed(state, current_record, current_context, False, retained_proof)
        assert observed['observations'] == 2 and observed['proc_census_complete'] is True
        assert observed['sealed_native_identity_used'] is True and observed['daemon_birth_ticks_claimed'] is True
        assert observed['retained_native_observation']['daemon_pid'] == child.pid
        assert observed['retained_native_observation']['positive_execution_or_fencing_authority'] is False
        assert observed['minimum_owned_start_ticks'] == record['identity']['start_ticks']
        assert heartbeat.read_bytes() == null_bytes and not pid_path.exists() and not sidecar.exists()
        for index, change in enumerate((
                {'api': 'foreign'}, {'identity_record_id': 'foreign'},
                {'identity_sha256': 'f' * 64}, {'launch_binding_sha256': 'f' * 64},
                {'canonical_pid_path': str(root / 'foreign.pid')},
                {'native_source': {**effect['native_source'], 'sha256': 'f' * 64}})):
            invalid = root / f'invalid-retained-effect-{index}.json'
            invalid.write_text(json.dumps({**effect, **change})); invalid.chmod(0o600)
            with pytest.raises(ValueError):
                shutdown._parent_closed(state, current_record, current_context, False,
                    {**retained_proof, 'effect': reference(invalid)})
        invalid_result = root / 'refused-public-clear-result.json'
        invalid_result.write_text(json.dumps({**json.loads(public_clear.read_text()), 'returned': False}))
        invalid_result.chmod(0o600)
        invalid_effect = root / 'refused-public-clear-effect.json'
        invalid_effect.write_text(json.dumps({**effect, 'result': reference(invalid_result)}))
        invalid_effect.chmod(0o600)
        with pytest.raises(ValueError, match='absence observation'):
            shutdown._parent_closed(state, current_record, current_context, False,
                {**retained_proof, 'effect': reference(invalid_effect)})
        # A self-consistent typed record for another parent still has no scope.
        foreign = replace(identity, process_birth=replace(identity.process_birth,
            parent_pid=os.getpid()), record_id='')
        foreign_path = root / 'foreign-retained-identity.json'
        foreign_path.write_text(json.dumps(foreign.to_dict())); foreign_path.chmod(0o600)
        foreign_effect = root / 'foreign-retained-effect.json'
        foreign_effect.write_text(json.dumps({**effect, 'identity_record_id': foreign.to_dict()['record_id'],
            'identity_sha256': reference(foreign_path)['sha256']})); foreign_effect.chmod(0o600)
        with pytest.raises(ValueError, match='birth/command/session'):
            shutdown._parent_closed(state, current_record, current_context, False,
                {**retained_proof, 'identity': reference(foreign_path), 'effect': reference(foreign_effect)})
        with monkeypatch.context() as unknown:
            unknown.setattr(native, 'supervised_child_identity_liveness', lambda _identity: native.OwnerLiveness.UNKNOWN)
            with pytest.raises(ValueError, match='birth/command/session'):
                shutdown._parent_closed(state, current_record, current_context, False, retained_proof)
        with monkeypatch.context() as group:
            group.setattr(shutdown, '_complete_process_inventory', lambda *_a: [
                {'pid': 1073741826, 'uid': os.getuid() + 1, 'process_group': child.pid,
                 'session': child.pid, 'argv': (), 'cwd': None}])
            with pytest.raises(ValueError, match='group or session'):
                shutdown._parent_closed(state, current_record, current_context, False, retained_proof)
        actual_inventory = shutdown._complete_process_inventory
        with monkeypatch.context() as changed:
            def changed_archive(*args):
                rows = actual_inventory(*args)
                archive.write_bytes(original[sidecar] + b' ')
                return rows
            changed.setattr(shutdown, '_complete_process_inventory', changed_archive)
            with pytest.raises(ValueError, match='hash changed'):
                shutdown._parent_closed(state, current_record, current_context, False, retained_proof)
        archive.write_bytes(original[sidecar]); archive.chmod(0o600)
        fake.calls.clear(); fake.ps_count = 0
        retained_stop = runner.stop(state, timeout=0, retained_native_child_proof=retained_proof)
        assert retained_stop['status'] == 'stopped' and retained_stop['signalled'] is False
        stored = json.loads((state / shutdown.RECEIPT_NAME).read_text())
        assert stored['quiesced'] is True and stored['retained_native_child_proof'] == retained_proof
        assert stored['process_closure']['observations'] == 2 and fake.effects == []
        assert heartbeat.read_bytes() == null_bytes and not pid_path.exists() and not sidecar.exists()
        # The ordinary subsequent start-side observer rederives stored evidence,
        # never treating the previous closure as cached positive authority.
        final_record = json.loads((state / 'launcher.json').read_text())
        again = shutdown._parent_closed(state, final_record, shutdown._context(state, final_record), False)
        assert again['observations'] == 2 and again['retained_native_observation']['daemon_pid'] == child.pid
        assert heartbeat.read_bytes() == null_bytes and archive.read_bytes() == original[sidecar]
    finally:
        if parent is not None and parent.poll() is None:
            parent.kill(); parent.wait(timeout=3)
        if child is not None and native.supervised_child_identity_liveness(identity) is native.OwnerLiveness.ALIVE:
            if 'original' in locals():
                sidecar.write_bytes(original[sidecar]); pid_path.write_bytes(original[pid_path])
            native.terminate_supervised_child(child, grace_seconds=.1, clear_pid_file=False)
        if child is not None:
            try: os.waitpid(child.pid, os.WNOHANG)
            except ChildProcessError: pass
        assert libc.prctl(36, previous.value, 0, 0, 0) == 0


def _missing_marker_heartbeat(state, record, daemon_pid):
    """Synthetic producer-shaped scope; never manufactures a death receipt."""
    started = record['started_at']
    run_id = datetime.fromtimestamp(started, timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    native_state = str(state / f'{runner.STATE_PREFIX}_task_state.json')
    return {'schema': 'ipfs_accelerate_py.agent_supervisor.todo_implementation_supervisor.supervisor',
        'status': 'running', 'repo_root': record['repo_root'],
        'supervisor_pid': record['identity']['pid'], 'daemon_pid': daemon_pid,
        'updated_at': stamp(time.time()), 'todo_path': record['board_path'],
        'state_path': native_state, 'current_status_path': native_state, 'progress_path': native_state,
        'child_pid_path': str(state / f'{runner.STATE_PREFIX}_managed_daemon.pid'),
        'supervisor_lock_path': str(state / f'{runner.STATE_PREFIX}_supervisor.lock'),
        'state_prefix': runner.STATE_PREFIX, 'task_prefix': runner.TASK_PREFIX, 'max_task_attempts': 3,
        'control_plane_source_schema': 'ipfs_accelerate_py.agent_supervisor.control_plane_source@1',
        'control_plane_source_revision': 'a' * 40, 'control_plane_current_source_revision': 'a' * 40,
        'control_plane_source_id': 'b' + 'a' * 58, 'control_plane_current_source_id': 'b' + 'a' * 58,
        'run_id': run_id, 'log_path': str(state / f'{runner.STATE_PREFIX}_managed_daemon_{run_id}.log')}


@pytest.fixture
def missing_marker_campaign(campaign, monkeypatch):
    # Isolated read-only census controls complement the real public-native
    # fence above; no additional process is launched by these negative cases.
    record = deepcopy(campaign.record)
    record['identity'].update(pid=1073741824, session=1073741824, process_group=1073741824,
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    record['status'] = 'starting'
    runner._atomic_json(campaign.state / 'launcher.json', record)
    heartbeat = _missing_marker_heartbeat(campaign.state, record, 1073741825)
    runner._atomic_json(campaign.state / 'complaint_intake_supervisor_status.json', heartbeat)
    monkeypatch.setattr(shutdown, '_complete_process_inventory', lambda *_a: [])
    return SimpleNamespace(**vars(campaign), current_record=record, heartbeat=heartbeat,
        context=shutdown._context(campaign.state, record))


@pytest.mark.parametrize('mutation', [
    {'repo_root': '/foreign'}, {'todo_path': '/foreign'}, {'state_path': '/foreign'},
    {'current_status_path': '/foreign'}, {'progress_path': '/foreign'},
    {'child_pid_path': '/foreign'}, {'supervisor_lock_path': '/foreign'},
    {'state_prefix': 'foreign'}, {'task_prefix': 'foreign'}, {'supervisor_pid': 3},
    {'daemon_pid': None}, {'max_task_attempts': 2}, {'schema': 'foreign'},
    {'control_plane_current_source_revision': 'f' * 40},
    {'control_plane_current_source_id': 'b' + 'f' * 58}, {'updated_at': '2000-01-01T00:00:00Z'},
    {'run_id': '20000101T000000Z'}, {'log_path': '/foreign'},
])
def test_missing_marker_heartbeat_scope_never_grants_closure(missing_marker_campaign, mutation):
    fixture = missing_marker_campaign
    runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json',
        {**fixture.heartbeat, **mutation})
    with pytest.raises(ValueError):
        shutdown._parent_closed(fixture.state, fixture.current_record, fixture.context, False)


@pytest.mark.parametrize('marker', ['pid', 'identity', 'dangling_identity'])
def test_missing_marker_partial_or_symlink_evidence_refuses(missing_marker_campaign, marker):
    fixture = missing_marker_campaign
    pid = fixture.state / 'complaint_intake_managed_daemon.pid'
    sidecar = pid.with_suffix('.identity.json')
    if marker == 'pid':
        pid.write_text('1073741825\n')
    elif marker == 'identity':
        sidecar.write_text('{}')
    else:
        sidecar.symlink_to(fixture.state / 'missing-target')
    with pytest.raises((ValueError, OSError)):
        shutdown._parent_closed(fixture.state, fixture.current_record, fixture.context, False)


@pytest.mark.parametrize('leader', ['parent', 'daemon'])
def test_missing_marker_numeric_pid_reuse_refuses(missing_marker_campaign, leader):
    fixture = missing_marker_campaign
    record, heartbeat = deepcopy(fixture.current_record), deepcopy(fixture.heartbeat)
    if leader == 'parent':
        record['identity'].update(pid=os.getpid(), session=os.getpid(), process_group=os.getpid())
        heartbeat['supervisor_pid'] = os.getpid()
    else:
        heartbeat['daemon_pid'] = os.getpid()
    runner._atomic_json(fixture.state / 'launcher.json', record)
    runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json', heartbeat)
    with pytest.raises(ValueError, match='numeric PID is still present'):
        shutdown._parent_closed(fixture.state, record, shutdown._context(fixture.state, record), False)


@pytest.mark.parametrize('kind', ['group', 'session', 'workspace_cwd', 'workspace_argv', 'daemon_argv'])
def test_missing_marker_escaped_process_or_session_refuses(missing_marker_campaign, monkeypatch, kind):
    fixture = missing_marker_campaign
    row = {'pid': 1073741826, 'uid': os.getuid(), 'process_group': 1073741826,
        'session': 1073741826, 'argv': ('unrelated',), 'cwd': str(fixture.repo)}
    if kind in {'group', 'session'}:
        row['process_group' if kind == 'group' else 'session'] = fixture.heartbeat['daemon_pid']
        row['uid'] = os.getuid() + 1
    elif kind == 'workspace_cwd':
        row['cwd'] = str(fixture.workspace)
    elif kind == 'workspace_argv':
        row['argv'] = (sys.executable, str(fixture.workspace / 'worker.py'))
    else:
        row['argv'] = (sys.executable, str(fixture.repo / 'integrations/ipfs_accelerate/improvement_runner.py'),
            '--todo-path', fixture.current_record['board_path'], '--state-dir', str(fixture.state))
    monkeypatch.setattr(shutdown, '_complete_process_inventory', lambda *_a: [row])
    with pytest.raises(ValueError, match='still present|remains outside'):
        shutdown._parent_closed(fixture.state, fixture.current_record, fixture.context, False)


@pytest.mark.parametrize('change', ['unavailable', 'heartbeat', 'launcher', 'marker', 'boot'])
def test_missing_marker_unknown_or_changed_custody_refuses(missing_marker_campaign, monkeypatch, change):
    fixture = missing_marker_campaign
    calls = []
    def inventory(_minimum_owned_start_ticks):
        calls.append(1)
        if change == 'unavailable':
            raise ValueError('complete process inventory is unavailable')
        if len(calls) == 1:
            if change == 'heartbeat':
                runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json',
                    {**fixture.heartbeat, 'restart_count': 1})
            elif change == 'launcher':
                runner._atomic_json(fixture.state / 'launcher.json', {**fixture.current_record, 'status': 'stopped'})
            elif change == 'marker':
                (fixture.state / 'complaint_intake_managed_daemon.pid').write_text('1073741825\n')
        return []
    monkeypatch.setattr(shutdown, '_complete_process_inventory', inventory)
    record = fixture.current_record
    if change == 'boot':
        record = deepcopy(record)
        record['identity']['boot_id'] = 'foreign-boot'
        runner._atomic_json(fixture.state / 'launcher.json', record)
    with pytest.raises(ValueError):
        shutdown._parent_closed(fixture.state, record, shutdown._context(fixture.state, record), False)


def test_missing_marker_observation_is_pure_and_ignores_unrelated_shell_text(missing_marker_campaign, monkeypatch):
    fixture = missing_marker_campaign
    paths = [fixture.state / 'launcher.json', fixture.state / 'complaint_intake_supervisor_status.json']
    before = {path: path.read_bytes() for path in paths}
    shell_text = f'python {fixture.workspace}/worker.py --state-dir {fixture.state}'
    calls = []
    def inventory(_minimum_owned_start_ticks):
        calls.append(1)
        return [{'pid': 1073741826, 'uid': os.getuid(), 'process_group': 1073741826,
            'session': 1073741826, 'argv': ('bash', '-lc', shell_text), 'cwd': str(fixture.repo)}]
    monkeypatch.setattr(shutdown, '_complete_process_inventory', inventory)
    result = shutdown._parent_closed(fixture.state, fixture.current_record, fixture.context, False)
    assert len(calls) == 2 and result['proc_census_complete'] is True
    assert result['signals_sent'] is False and result['completion_authority'] is False
    assert result['heartbeat_status_preserved'] == 'running'
    assert before == {path: path.read_bytes() for path in paths}
    assert not (fixture.state / 'complaint_intake_managed_daemon.pid').exists()
    assert not (fixture.state / 'complaint_intake_managed_daemon.identity.json').exists()


@pytest.mark.parametrize('failure', ['malformed', 'missing_live_metadata', 'birth_changed'])
def test_complete_process_inventory_never_converts_unknown_to_absence(tmp_path, monkeypatch, failure):
    proc = tmp_path / 'synthetic-proc'
    proc.mkdir()
    entry = proc / '1073741826'
    entry.mkdir()
    fields = ['S', '1', '1073741826', '1073741826', *(['0'] * 15), '42']
    raw = '1073741826 (synthetic fixture) ' + ' '.join(fields)
    (entry / 'stat').write_text('malformed' if failure == 'malformed' else raw)
    (entry / 'cmdline').write_bytes(b'unrelated\0')
    if failure != 'missing_live_metadata':
        (entry / 'cwd').symlink_to(tmp_path, target_is_directory=True)
    actual_path, actual_read = Path, Path.read_text
    monkeypatch.setattr(shutdown, 'Path', lambda value: proc if str(value) == '/proc' else actual_path(value))
    reads = []
    def read(path, *args, **kwargs):
        result = actual_read(path, *args, **kwargs)
        if failure == 'birth_changed' and path == entry / 'stat':
            reads.append(1)
            if len(reads) == 2:
                return result.rsplit(' ', 1)[0] + ' 43'
        return result
    monkeypatch.setattr(actual_path, 'read_text', read)
    with pytest.raises(ValueError, match='complete process inventory is unavailable'):
        shutdown._complete_process_inventory(42)


@pytest.mark.parametrize('cutoff', [None, True, False, 0, -1, 1.5, '42', 10**30])
def test_complete_process_inventory_refuses_invalid_launcher_birth_bound(cutoff):
    with pytest.raises(ValueError, match='birth bound'):
        shutdown._complete_process_inventory(cutoff)


@pytest.mark.parametrize('cutoff,permitted', [(43, True), (42, False), (41, False)])
def test_nondumpable_scope_is_excluded_only_for_proven_prelaunch_birth(tmp_path, monkeypatch, cutoff, permitted):
    proc = tmp_path / 'synthetic-proc'; proc.mkdir()
    entry = proc / '1073741826'; entry.mkdir()
    fields = ['S', '1', '1073741826', '1073741826', *(['0'] * 15), '42']
    (entry / 'stat').write_text('1073741826 (preexisting nondumpable fixture) ' + ' '.join(fields))
    (entry / 'cmdline').write_bytes(b'unrelated\0')
    actual_path = Path
    monkeypatch.setattr(shutdown, 'Path', lambda value: proc if str(value) == '/proc' else actual_path(value))
    def unavailable_cwd(path):
        assert path == entry / 'cwd'
        raise PermissionError('synthetic nondumpable cwd')
    monkeypatch.setattr(shutdown.os, 'readlink', unavailable_cwd)
    if not permitted:
        with pytest.raises(ValueError, match='complete process inventory is unavailable'):
            shutdown._complete_process_inventory(cutoff)
        return
    rows = shutdown._complete_process_inventory(cutoff)
    assert len(rows) == 1  # Excluded scope inspection is never process absence.
    assert rows[0]['start_ticks'] == 42 and rows[0]['pid'] == 1073741826
    assert rows[0]['process_group'] == rows[0]['session'] == 1073741826
    assert rows[0]['scope_metadata_required'] is False and rows[0]['prelaunch_scope_excluded'] is True
    assert rows[0]['argv'] == () and rows[0]['cwd'] is None


@pytest.mark.parametrize('identity', ['group', 'session'])
def test_prelaunch_exclusion_never_hides_historical_group_or_session(missing_marker_campaign, monkeypatch, identity):
    fixture = missing_marker_campaign
    row = {'pid': 1073741826, 'uid': os.getuid(), 'start_ticks': 1,
        'process_group': 1073741826, 'session': 1073741826, 'argv': (), 'cwd': None,
        'prelaunch_scope_excluded': True, 'scope_metadata_required': False}
    row['process_group' if identity == 'group' else 'session'] = fixture.heartbeat['daemon_pid']
    monkeypatch.setattr(shutdown, '_complete_process_inventory', lambda *_a: [row])
    with pytest.raises(ValueError, match='historical group or session is still present'):
        shutdown._parent_closed(fixture.state, fixture.current_record, fixture.context, False)


_REAL_COMPLETE_PROCESS_INVENTORY = shutdown._complete_process_inventory


@pytest.fixture
def foreign_login_kernel(tmp_path, monkeypatch):
    """Synthetic kernel/root-logind filesystem, no process or session launch.

    Only virtual root ownership is projected. The real metadata parsers, file
    readers, session/cgroup checks and complete census execute unchanged.
    """
    import stat as stat_module
    base = tmp_path / 'foreign-login-kernel'
    proc, run, cgroup = base / 'proc', base / 'run/systemd/sessions', base / 'sys/fs/cgroup'
    proc.mkdir(parents=True); run.mkdir(parents=True); cgroup.mkdir(parents=True)
    target, leader, broker, audit = 1073741800, 1073741801, 1073741802, 77
    cutoff = 100
    actual_path, actual_stat, actual_fstat, actual_readlink = Path, Path.stat, os.fstat, os.readlink
    root_roles = {proc / str(leader), proc / str(broker)}
    trusted_ancestors = set(base.parents) | {base}
    bad_owner = set()
    def path(value):
        text = str(value)
        reader = '/proc/' + str(os.getpid())
        if text.startswith(reader + '/'):
            return proc / 'self' / text[len(reader):].lstrip('/')
        if text == '/proc/1/timens_offsets':
            return proc / 'initial-timens-offsets'
        for prefix, replacement in [('/proc', proc), ('/run/systemd/sessions', run), ('/sys/fs/cgroup', cgroup)]:
            if text == prefix or text.startswith(prefix + '/'):
                return replacement / text[len(prefix):].lstrip('/')
        return actual_path(value)
    def root_owned(p):
        return (p in trusted_ancestors or p == run or p.is_relative_to(run)
            or p == cgroup or p.is_relative_to(cgroup)
            or any(p == root or p.is_relative_to(root) for root in root_roles)
            or p in set(run.parents) | set(cgroup.parents))
    def projected(p, info):
        values = list(info)
        if root_owned(p):
            values[4] = 0
        if p in bad_owner:
            values[4] = os.getuid()
        if p in trusted_ancestors:
            values[0] = stat_module.S_IFDIR | 0o755
        return os.stat_result(values)
    def observed_stat(p, *args, **kwargs):
        return projected(p, actual_stat(p, *args, **kwargs))
    def observed_fstat(fd):
        info = actual_fstat(fd)
        try:
            p = actual_path(actual_readlink('/proc/self/fd/' + str(fd)))
        except OSError:
            return info
        return projected(p, info)
    def observed_readlink(p):
        if str(p) == '/proc/' + str(os.getpid()) + '/ns/time':
            return 'time:[4026531834]'
        if actual_path(p) == proc / str(target) / 'cwd':
            raise PermissionError('synthetic foreign root-broker cwd')
        return actual_readlink(p)
    def write(p, body):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body if isinstance(body, bytes) else body.encode())
        p.chmod(0o644)
    scope = f'/user.slice/user-{os.getuid()}.slice/session-{audit}.scope'
    def process(pid, uid, parent, birth, sid, loginuid, group=None, session=None):
        directory = proc / str(pid); directory.mkdir(exist_ok=True)
        fields = ['S', str(parent), str(group or pid), str(session or pid), *(['0'] * 15), str(birth)]
        write(directory / 'stat', str(pid) + ' (synthetic root-broker fixture) ' + ' '.join(fields))
        write(directory / 'status', f'Pid:\t{pid}\nNSpid:\t{pid}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\nCapEff:\t0000000000000000\nCapPrm:\t0000000000000000\nCapAmb:\t0000000000000000\n')
        write(directory / 'sessionid', str(sid) + '\n'); write(directory / 'loginuid', str(loginuid) + '\n')
        write(directory / 'cgroup', '0::' + scope + '\n')
    process(target, os.getuid(), leader, 300, audit, os.getuid())
    process(leader, 0, broker, 200, audit, os.getuid())
    process(broker, 0, 1, 50, 2**32 - 1, 2**32 - 1)
    write(proc / str(target) / 'cmdline', b'unrelated-session-server\0')
    write(proc / 'sys/kernel/random/boot_id', 'synthetic-current-boot\n')
    write(proc / 'self/timens_offsets', 'monotonic 0 0\nboottime 0 0\n')
    write(proc / 'initial-timens-offsets', 'monotonic 0 0\nboottime 0 0\n')
    write(proc / 'self/uid_map', '0 0 4294967295\n')
    write(proc / 'self/mountinfo', '1 0 0:1 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n')
    record = run / str(audit)
    record_body = f'UID={os.getuid()}\nAUDIT={audit}\nLEADER={leader}\nSERVICE=sshd\nREMOTE=1\nSCOPE=session-{audit}.scope\nMONOTONIC=2500000\n'
    write(record, record_body)
    current = cgroup
    for component in [None, *scope.lstrip('/').split('/')]:
        if component is not None:
            current = current / component
        current.mkdir(exist_ok=True); current.chmod(0o755)
        write(current / 'cgroup.procs', ''); write(current / 'cgroup.threads', '')
    write(current / 'cgroup.type', 'domain\n')
    # mkdir(parents=True) obeys the real user's umask. Model the declared
    # trusted root hierarchy physically, before projecting only its UID.
    trusted_directories = {run, cgroup, *run.parents, *cgroup.parents}
    for directory in trusted_directories:
        if directory.is_relative_to(base):
            directory.chmod(0o755)
    assert all(not directory.stat().st_mode & 0o022 for directory in trusted_directories
        if directory.is_relative_to(base))
    monkeypatch.setattr(shutdown, 'Path', path)
    monkeypatch.setattr(actual_path, 'stat', observed_stat)
    monkeypatch.setattr(shutdown.os, 'fstat', observed_fstat)
    monkeypatch.setattr(shutdown.os, 'readlink', observed_readlink)
    return SimpleNamespace(proc=proc, run=run, cgroup=cgroup, leaf=current, record=record,
        target=target, leader=leader, broker=broker, audit=audit, cutoff=cutoff, write=write,
        process=process, record_body=record_body, bad_owner=bad_owner, actual_readlink=actual_readlink,
        observed_readlink=observed_readlink, actual_path=actual_path)


def test_foreign_login_cwd_exception_retains_real_census_and_explicit_proof(foreign_login_kernel):
    fixture = foreign_login_kernel
    rows = shutdown._complete_process_inventory(fixture.cutoff)
    target = next(row for row in rows if row['pid'] == fixture.target)
    assert len(rows) == 3 and target['cwd'] is None and target['argv'] == ('unrelated-session-server',)
    assert target['scope_metadata_required'] is True and target['prelaunch_scope_excluded'] is False
    proof = target['foreign_cwd_proof']
    assert proof['cwd_known'] is False and proof['cwd_permission_denied'] is True
    assert proof['audit_session'] == fixture.audit and proof['leader_pid'] == fixture.leader
    assert proof['broker_pid'] == fixture.broker and proof['trusted_privileged_host_boundary'] is True
    assert proof['historical_privileged_migration_impossible_claim'] is False
    assert all(len(proof[key]) == 64 for key in ['record_sha256', 'kernel_identity_sha256', 'cgroup_metadata_sha256', 'boot_sha256'])


@pytest.mark.parametrize('failure', [
    'record_uid', 'record_audit', 'record_duplicate', 'record_symlink', 'record_owner',
    'record_old', 'record_equal', 'record_future', 'leader_uid', 'leader_old', 'target_parent',
    'target_audit', 'target_loginuid', 'broker_uid', 'broker_audit', 'broker_loginuid',
    'cap_effective', 'cap_permitted', 'cap_ambient', 'writable_scope', 'writable_ancestor',
    'foreign_cgroup', 'threaded_scope', 'wrong_mount', 'time_offset', 'user_namespace', 'nested_pid_namespace', 'unknown_argv',
])
def test_foreign_login_cwd_exception_refuses_incomplete_or_forged_proof(foreign_login_kernel, failure):
    f = foreign_login_kernel
    def replace(p, old, new):
        f.write(p, p.read_text().replace(old, new))
    if failure == 'record_uid': replace(f.record, f'UID={os.getuid()}', 'UID=0')
    elif failure == 'record_audit': replace(f.record, f'AUDIT={f.audit}', 'AUDIT=78')
    elif failure == 'record_duplicate': f.write(f.record, f.record_body + 'UID=0\n')
    elif failure == 'record_symlink':
        original = f.record.with_name('original-record'); f.record.rename(original); f.record.symlink_to(original)
    elif failure == 'record_owner': f.bad_owner.add(f.record)
    elif failure in {'record_old', 'record_equal', 'record_future'}:
        value = {'record_old': '1', 'record_equal': '1010000', 'record_future': str(2**64 - 1)}[failure]
        replace(f.record, 'MONOTONIC=2500000', 'MONOTONIC=' + value)
    elif failure == 'leader_uid': replace(f.proc / str(f.leader) / 'status', 'Uid:\t0\t0\t0\t0', f'Uid:\t{os.getuid()}\t{os.getuid()}\t{os.getuid()}\t{os.getuid()}')
    elif failure == 'leader_old': f.process(f.leader, 0, f.broker, 99, f.audit, os.getuid())
    elif failure == 'target_parent': f.process(f.target, os.getuid(), f.broker, 300, f.audit, os.getuid())
    elif failure == 'target_audit': f.write(f.proc / str(f.target) / 'sessionid', '78\n')
    elif failure == 'target_loginuid': f.write(f.proc / str(f.target) / 'loginuid', '0\n')
    elif failure == 'broker_uid': f.process(f.broker, os.getuid(), 1, 50, 2**32 - 1, 2**32 - 1)
    elif failure == 'broker_audit': f.write(f.proc / str(f.broker) / 'sessionid', str(f.audit))
    elif failure == 'broker_loginuid': f.write(f.proc / str(f.broker) / 'loginuid', str(os.getuid()))
    elif failure.startswith('cap_'):
        key = {'cap_effective': 'CapEff', 'cap_permitted': 'CapPrm', 'cap_ambient': 'CapAmb'}[failure]
        replace(f.proc / str(f.target) / 'status', key + ':\t0000000000000000', key + ':\t0000000020000000')
    elif failure == 'writable_scope': (f.leaf / 'cgroup.procs').chmod(0o666)
    elif failure == 'writable_ancestor': (f.cgroup / 'cgroup.procs').chmod(0o666)
    elif failure == 'foreign_cgroup': f.write(f.proc / str(f.target) / 'cgroup', '0::/foreign.scope\n')
    elif failure == 'threaded_scope': f.write(f.leaf / 'cgroup.type', 'threaded\n')
    elif failure == 'wrong_mount': f.write(f.proc / 'self/mountinfo', '1 0 0:1 / /sys/fs/cgroup rw - tmpfs tmpfs rw\n')
    elif failure == 'time_offset': f.write(f.proc / 'self/timens_offsets', 'monotonic 1 0\nboottime 0 0\n')
    elif failure == 'user_namespace': f.write(f.proc / 'self/uid_map', '0 1003 1\n')
    elif failure == 'nested_pid_namespace': replace(f.proc / str(f.target) / 'status', f'NSpid:\t{f.target}', f'NSpid:\t{f.target}\t1')
    else: (f.proc / str(f.target) / 'cmdline').unlink()
    with pytest.raises(ValueError, match='complete process inventory is unavailable'):
        shutdown._complete_process_inventory(f.cutoff)


@pytest.mark.parametrize('change', ['record', 'birth', 'audit', 'namespace', 'cgroup_type'])
def test_foreign_login_cwd_proof_refuses_observation_races(foreign_login_kernel, monkeypatch, change):
    f = foreign_login_kernel
    # Race actual filesystem metadata between the first and final kernel
    # reads, without mocking the product's proof predicate or its decision.
    original_fstat = shutdown.os.fstat
    calls = []
    def fstat(fd):
        result = original_fstat(fd)
        path = f.actual_path(f.actual_readlink('/proc/self/fd/' + str(fd)))
        if path == f.record:
            calls.append(1)
            if len(calls) == 1:
                if change == 'record': f.write(f.record, f.record_body.replace('REMOTE=1', 'REMOTE=0'))
                elif change == 'birth': f.process(f.target, os.getuid(), f.leader, 301, f.audit, os.getuid())
                elif change == 'audit': f.write(f.proc / str(f.target) / 'sessionid', '78\n')
        return result
    if change in {'namespace', 'cgroup_type'}:
        names = []
        def readlink(path):
            if str(path) == '/proc/' + str(os.getpid()) + '/ns/time':
                names.append(1)
                if change == 'cgroup_type':
                    if len(names) == 2:
                        f.write(f.leaf / 'cgroup.type', 'threaded\n')
                    return 'time:[4026531834]'
                return 'time:[1]' if len(names) == 1 else 'time:[2]'
            return f.observed_readlink(path)
        monkeypatch.setattr(shutdown.os, 'readlink', readlink)
    else:
        monkeypatch.setattr(shutdown.os, 'fstat', fstat)
    with pytest.raises(ValueError, match='complete process inventory is unavailable'):
        shutdown._complete_process_inventory(f.cutoff)


@pytest.mark.parametrize('matching', ['none', 'group', 'argv'])
def test_missing_marker_public_closure_keeps_foreign_process_and_rejects_owned_matches(
        missing_marker_campaign, foreign_login_kernel, monkeypatch, matching):
    f, campaign = foreign_login_kernel, missing_marker_campaign
    record = deepcopy(campaign.current_record)
    record['identity'].update(start_ticks=f.cutoff, boot_id='synthetic-current-boot')
    runner._atomic_json(campaign.state / 'launcher.json', record)
    context = shutdown._context(campaign.state, record)
    if matching == 'group':
        f.process(f.target, os.getuid(), f.leader, 300, f.audit, os.getuid(), group=campaign.heartbeat['daemon_pid'])
    elif matching == 'argv':
        f.write(f.proc / str(f.target) / 'cmdline', (str(campaign.workspace / 'escaped.py') + '\0').encode())
    monkeypatch.setattr(shutdown, '_complete_process_inventory', _REAL_COMPLETE_PROCESS_INVENTORY)
    before = (campaign.state / 'complaint_intake_supervisor_status.json').read_bytes()
    if matching != 'none':
        with pytest.raises(ValueError, match='historical group or session is still present|matching campaign process'):
            shutdown._parent_closed(campaign.state, record, context, False)
        return
    observed = shutdown._parent_closed(campaign.state, record, context, False)
    assert observed['proc_census_complete'] is True and observed['observations'] == 2
    assert len(observed['foreign_cwd_observations']) == 2
    assert all(len(proofs) == 1 and proofs[0]['cwd_known'] is False for proofs in observed['foreign_cwd_observations'])
    assert observed['signals_sent'] is False and observed['heartbeat_status_preserved'] == 'running'
    assert (campaign.state / 'complaint_intake_supervisor_status.json').read_bytes() == before



@pytest.mark.parametrize('uid,euid', [(0, 0), (1000, 1001)])
def test_foreign_login_cwd_proof_refuses_privileged_observer_before_io(monkeypatch, uid, euid):
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(1)
        raise AssertionError('foreign proof must reject this observer before opening metadata')
    with monkeypatch.context() as observer:
        observer.setattr(shutdown.os, 'getuid', lambda: uid)
        observer.setattr(shutdown.os, 'geteuid', lambda: euid)
        observer.setattr(shutdown.os, 'open', unavailable)
        with pytest.raises(ValueError, match='ordinary unprivileged observer'):
            shutdown._foreign_login_cwd_proof(1073741800, 100)
    assert calls == []


def test_retained_native_observation_never_authorizes_live_parent_signals(campaign, monkeypatch):
    monkeypatch.setattr(runner, 'owns_process', lambda _record: True)
    monkeypatch.setattr(runner, '_signal_birth', lambda *_a: pytest.fail('retained observation must not signal'))
    result = runner.stop(campaign.state, timeout=0, retained_native_child_proof={})
    assert result['status'] == 'stop_incomplete' and result['signalled'] is False
    assert 'live fencing' in result['reason']



def test_owned_event_history_above_old_limit_preserves_native_chain_and_closure(campaign, docker, monkeypatch):
    # The shared fixture helper writes a genuine Native sequence/hash chain;
    # routine synthetic records stay below its per-event bound, no provider runs.
    from tests.test_improvement_runner import _owned_growing_native_event_history
    events = campaign.state / 'complaint_intake_events.jsonl'
    monkeypatch.setenv('IPFS_ACCELERATE_AGENT_EVENT_LOG_MAX_BYTES', str(50 * 1024 * 1024))
    event, original = _owned_growing_native_event_history(events, campaign.event, padding_records=33)
    campaign.event = event
    assert 16_000_000 < len(original) < shutdown.MAX_EVENTS_BYTES
    expected_sha = hashlib.sha256(original).hexdigest()
    starts, observed_sha = shutdown._events(campaign.state, campaign.started)
    assert observed_sha == expected_sha
    assert starts == {campaign.workspace: [{
        'event_id': event['event_id'], 'started_at': datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00')).timestamp(),
        'task_id': event['task_id'], 'canonical_task_cid': event['canonical_task_cid'], 'attempt': 1,
    }]}
    fake, _ = docker
    fake.containers = {CONTAINER: container(campaign)}
    result = close(campaign)
    assert result['status'] == 'stopped' and result['quiesced'] is True
    assert result['event_log_sha256'] == expected_sha
    assert result['containers'][0]['event_id'] == event['event_id']
    assert fake.effects == [('stop', CONTAINER), ('rm', CONTAINER)]
    assert events.read_bytes() == original
    receipt = json.loads((campaign.state / shutdown.RECEIPT_NAME).read_text())
    assert receipt['event_log_sha256'] == expected_sha
    assert receipt['completion_authority'] is False and receipt['attempt_refunded'] is False


def test_event_history_above_finite_limit_refuses_before_container_effects(campaign, docker):
    events = campaign.state / 'complaint_intake_events.jsonl'
    # A sparse private fixture crosses the finite bound without allocating a
    # giant payload. The real owned-byte gate must refuse before reading it.
    with events.open('wb') as output:
        output.truncate(shutdown.MAX_EVENTS_BYTES + 1)
    result = close(campaign)
    assert result['status'] == 'stop_incomplete' and result['quiesced'] is False
    assert result['reason'] == 'recovery evidence must be a bounded owned regular file'
    assert not docker[0].calls and not docker[0].effects
    assert events.stat().st_size == shutdown.MAX_EVENTS_BYTES + 1


@pytest.fixture
def failed_preflight_campaign(missing_marker_campaign):
    fixture = missing_marker_campaign
    heartbeat = deepcopy(fixture.heartbeat)
    heartbeat.update(status='agentic_maintenance_failed', daemon_pid=None, daemon_process_birth=None,
        active_agentic_maintenance_has_daemon=False, active_worker_count=0, active_worker_pids=[],
        worker_descendant_count=0, last_agentic_maintenance_status='failed',
        last_agentic_maintenance_phase='worktree_reconciliation', run_id='',
        supervisor_process_birth={'pid':fixture.current_record['identity']['pid'],
            'start_time_ticks':fixture.current_record['identity']['start_ticks'],
            'boot_id':fixture.current_record['identity']['boot_id'], 'parent_pid':1},
        supervisor_maintenance={'schema':'ipfs_accelerate_py/agent-supervisor/supervisor-maintenance@1',
            'phase':'failed','started_at':stamp(fixture.started+1),'finished_at':stamp(fixture.started+2)})
    runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json', heartbeat)
    (fixture.state / 'complaint_intake_events.jsonl').write_text('')
    return SimpleNamespace(**vars(fixture), preflight_heartbeat=heartbeat)


def _budget_terminal_heartbeat(heartbeat):
    return {**heartbeat, 'status': 'task_attempt_budget_exhausted', 'daemon_pid': None,
        'active_worker_count': 0, 'active_worker_pids': [], 'worker_descendant_count': 0,
        'last_recycle_reason': 'task_attempt_budget_exhausted', 'attempt_budget_terminal_pending': False,
        'attempt_budget_terminal_guard': {'safe': True, 'generation_restart_authorized': False,
            'operator_successor_required': True, 'task_completion_authority': False,
            'local_implementation_in_progress': False, 'local_active_task_id': '',
            'attempt_budget_consumed': False, 'provider_invocation_consumed': False},
        'selection_blocker': {'reason': 'task_attempt_budget_exhausted', 'completion_authority': False,
            'max_task_attempts': 3, 'operator_successor_required': True,
            'limited_tasks': [{'task_id': 'CIMP-UX-11', 'attempt_count': 3},
                {'task_id': 'CIMP-UX-24', 'attempt_count': 3}]}}


def test_budget_exhausted_terminal_stop_closes_without_rearming_or_completing(missing_marker_campaign, docker):
    fixture = missing_marker_campaign
    heartbeat = _budget_terminal_heartbeat(fixture.heartbeat)
    runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json', heartbeat)
    before = (fixture.state / 'complaint_intake_supervisor_status.json').read_bytes()
    result = runner.stop(fixture.state)
    proof = result['container_shutdown']['process_closure']
    assert result['status'] == 'stopped' and result['signalled'] is False
    assert proof['source'] == 'owned_attempt_budget_terminal_and_double_complete_proc_inventory'
    assert proof['attempt_refunded'] is False and proof['completion_authority'] is False
    assert result['container_shutdown']['attempt_refunded'] is False
    assert result['container_shutdown']['completion_authority'] is False
    assert not docker[0].effects
    assert (fixture.state / 'complaint_intake_supervisor_status.json').read_bytes() == before


def _control_plane_reload_heartbeat(heartbeat):
    current = '0123456789abcdef0123456789abcdef01234567'
    assert current != heartbeat['control_plane_source_revision']
    return {**heartbeat, 'status': 'control_plane_reload_required', 'daemon_pid': None,
        'daemon_pid_alive': False, 'active_worker_count': 0, 'active_worker_pids': [],
        'last_recycle_reason': 'control_plane_source_changed', 'last_exit_code': 137,
        'control_plane_update_pending': True, 'control_plane_reload_deferred': False,
        'control_plane_reload_attempt_budget_consumed': False,
        'control_plane_reload_provider_invocation_consumed': False,
        'control_plane_current_source_revision': current,
        'control_plane_current_source_id': 'baguqeerareloadcurrentsourceidmustdifferfromloadedrevision'}


def test_control_plane_reload_exit_closes_without_rearming_or_completing(missing_marker_campaign, docker):
    fixture = missing_marker_campaign
    heartbeat = _control_plane_reload_heartbeat(fixture.heartbeat)
    runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json', heartbeat)
    before = (fixture.state / 'complaint_intake_supervisor_status.json').read_bytes()
    result = runner.stop(fixture.state)
    proof = result['container_shutdown']['process_closure']
    assert result['status'] == 'stopped' and result['signalled'] is False
    assert proof['source'] == 'owned_control_plane_reload_and_double_complete_proc_inventory'
    assert proof['attempt_refunded'] is False and proof['completion_authority'] is False
    assert result['container_shutdown']['attempt_refunded'] is False
    assert result['container_shutdown']['completion_authority'] is False
    assert not docker[0].effects
    assert (fixture.state / 'complaint_intake_supervisor_status.json').read_bytes() == before


def test_control_plane_reload_without_a_source_change_stays_open(missing_marker_campaign, docker):
    fixture = missing_marker_campaign
    heartbeat = _control_plane_reload_heartbeat(fixture.heartbeat)
    heartbeat['control_plane_current_source_revision'] = heartbeat['control_plane_source_revision']
    heartbeat['control_plane_current_source_id'] = heartbeat['control_plane_source_id']
    runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json', heartbeat)
    result = runner.stop(fixture.state)
    assert result['status'] == 'stop_incomplete' and result['signalled'] is False
    assert not docker[0].calls and not docker[0].effects


def test_budget_exhausted_restart_authority_remains_unclosed(missing_marker_campaign, docker):
    fixture = missing_marker_campaign
    heartbeat = _budget_terminal_heartbeat(fixture.heartbeat)
    heartbeat['attempt_budget_terminal_guard']['generation_restart_authorized'] = True
    runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json', heartbeat)
    result = runner.stop(fixture.state)
    assert result['status'] == 'stop_incomplete' and result['signalled'] is False
    assert not docker[0].calls and not docker[0].effects


def test_failed_preflight_public_stop_proves_closure_without_fabricating_a_child(failed_preflight_campaign, docker, monkeypatch):
    fixture = failed_preflight_campaign
    observations = []
    def census(cutoff):
        observations.append(cutoff)
        return []
    monkeypatch.setattr(shutdown, '_complete_process_inventory', census)
    before = (fixture.state / 'complaint_intake_supervisor_status.json').read_bytes()
    result = runner.stop(fixture.state)
    assert result['status'] == 'stopped' and result['signalled'] is False
    proof = result['container_shutdown']['process_closure']
    assert proof['preflight_without_managed_daemon'] is True
    assert proof['proc_census_complete'] is True and proof['observations'] == 2
    assert proof['daemon_birth_ticks_claimed'] is False and proof['signals_sent'] is False
    assert observations == [fixture.current_record['identity']['start_ticks']] * 2
    assert not docker[0].effects
    assert (fixture.state / 'complaint_intake_supervisor_status.json').read_bytes() == before


@pytest.mark.parametrize('damage', ['birth_pid','birth_ticks','birth_boot','daemon','daemon_birth','has_daemon','workers','worker_pids','descendants','phase','status','maintenance_phase','maintenance_time','current_run','paid_start'])
def test_failed_preflight_cannot_claim_closure_for_unknown_or_launched_work(failed_preflight_campaign, docker, damage):
    fixture = failed_preflight_campaign
    hb = deepcopy(fixture.preflight_heartbeat)
    if damage == 'birth_pid': hb['supervisor_process_birth']['pid'] += 1
    elif damage == 'birth_ticks': hb['supervisor_process_birth']['start_time_ticks'] += 1
    elif damage == 'birth_boot': hb['supervisor_process_birth']['boot_id'] = 'foreign'
    elif damage == 'daemon': hb['daemon_pid'] = 1073741825
    elif damage == 'daemon_birth': hb['daemon_process_birth'] = {'pid':1073741825}
    elif damage == 'has_daemon': hb['active_agentic_maintenance_has_daemon'] = True
    elif damage == 'workers': hb['active_worker_count'] = 1
    elif damage == 'worker_pids': hb['active_worker_pids'] = [1073741825]
    elif damage == 'descendants': hb['worker_descendant_count'] = 1
    elif damage == 'phase': hb['last_agentic_maintenance_phase'] = 'unknown'
    elif damage == 'status': hb['last_agentic_maintenance_status'] = 'running'
    elif damage == 'maintenance_phase': hb['supervisor_maintenance']['phase'] = 'running'
    elif damage == 'maintenance_time': hb['supervisor_maintenance']['started_at'] = stamp(fixture.started-1)
    elif damage == 'current_run': hb['run_id'] = datetime.fromtimestamp(fixture.started, timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    else: (fixture.state / 'complaint_intake_events.jsonl').write_text(json.dumps(fixture.event)+'\n')
    runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json', hb)
    result = runner.stop(fixture.state)
    assert result['status'] == 'stop_incomplete' and result['signalled'] is False
    assert not docker[0].calls and not docker[0].effects


@pytest.mark.parametrize('scope', ['group','workspace'])
def test_failed_preflight_still_requires_complete_empty_fresh_process_censuses(failed_preflight_campaign, docker, monkeypatch, scope):
    fixture = failed_preflight_campaign
    process = {'pid':1073741826,'uid':os.getuid(),'process_group':0,'session':0,
        'argv':['/usr/bin/python3'],'cwd':str(fixture.repo.parent),'start_ticks':123457}
    if scope == 'group': process['session'] = fixture.current_record['identity']['pid']
    else: process['cwd'] = str(fixture.workspace)
    monkeypatch.setattr(shutdown, '_complete_process_inventory', lambda *_args: [process])
    result = runner.stop(fixture.state)
    assert result['status'] == 'stop_incomplete' and not docker[0].calls


def test_monitor_closes_only_its_dead_launch_through_public_stop(campaign, docker):
    from integrations.ipfs_accelerate.improvement_monitor import watch_owned_launch
    fake, _ = docker
    original = (campaign.state / "complaint_intake_events.jsonl").read_bytes()
    result = watch_owned_launch(campaign.repo, campaign.spec, campaign.state, maximum_seconds=1)
    assert result["status"] == "stopped_after_launcher_exit"
    assert result["stop_result"]["container_shutdown"]["quiesced"] is True
    assert result["provider_dispatched"] is result["attempt_refunded"] is False
    assert (campaign.state / "complaint_intake_events.jsonl").read_bytes() == original
    assert fake.effects == []


def test_monitor_refuses_replacement_owner_without_stopping_it(campaign, monkeypatch):
    from integrations.ipfs_accelerate import improvement_monitor as monitor
    monkeypatch.setattr(runner, "owns_process", lambda record: True)
    monkeypatch.setattr(runner, "stop", lambda *_a, **_k: pytest.fail("replacement owner must not be stopped"))
    def replace_owner(_delay):
        record = deepcopy(campaign.record)
        record["owner_token"] = "replacement-owner"
        runner._atomic_json(campaign.state / "launcher.json", record)
    monkeypatch.setattr(monitor.time, "sleep", replace_owner)
    result = monitor.watch_owned_launch(campaign.repo, campaign.spec, campaign.state, maximum_seconds=1)
    assert result["status"] == "monitor_owner_changed"


def test_monitor_never_fences_a_reused_numeric_launcher_pid(campaign, monkeypatch):
    from integrations.ipfs_accelerate.improvement_monitor import watch_owned_launch
    record = deepcopy(campaign.record)
    record["identity"].update(pid=os.getpid(), session=os.getpid(), process_group=os.getpid())
    runner._atomic_json(campaign.state / "launcher.json", record)
    monkeypatch.setattr(runner, "stop", lambda *_a, **_k: pytest.fail("reused PID must not be stopped"))
    result = watch_owned_launch(campaign.repo, campaign.spec, campaign.state, maximum_seconds=1)
    assert result["status"] == "monitor_owner_unknown"


def test_monitor_expiry_consumes_one_permanent_owner_window(campaign, monkeypatch):
    from integrations.ipfs_accelerate import improvement_monitor as monitor
    monkeypatch.setattr(runner, "owns_process", lambda record: True)
    monkeypatch.setattr(runner, "stop", lambda *_a, **_k: pytest.fail("live owner must not be stopped"))
    first = monitor.watch_owned_launch(campaign.repo, campaign.spec, campaign.state, maximum_seconds=.005)
    second = monitor.watch_owned_launch(campaign.repo, campaign.spec, campaign.state, maximum_seconds=.005)
    assert first["status"] == "monitor_expired"
    assert second["status"] == "monitor_window_consumed"
    windows = list((campaign.state / "monitor-owner-windows").iterdir())
    assert len(windows) == 1 and windows[0].stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("duration", [0, -1, 21601, float("nan"), float("inf"), True])
def test_monitor_rejects_unbounded_or_invalid_windows_before_effects(tmp_path, duration):
    from integrations.ipfs_accelerate.improvement_monitor import watch_owned_launch
    before = list(tmp_path.iterdir())
    with pytest.raises(ValueError, match="monitor duration"):
        watch_owned_launch(tmp_path, tmp_path / "missing", tmp_path / "absent", maximum_seconds=duration)
    assert list(tmp_path.iterdir()) == before


def test_monitor_refuses_changed_source_before_stop(campaign, monkeypatch):
    from integrations.ipfs_accelerate import improvement_monitor as monitor
    fingerprints = iter(({"source": "original"}, {"source": "changed"}))
    monkeypatch.setattr(monitor, "_source_snapshot", lambda: next(fingerprints))
    monkeypatch.setattr(runner, "stop", lambda *_a, **_k: pytest.fail("changed source must not authorize stop"))
    result = monitor.watch_owned_launch(campaign.repo, campaign.spec, campaign.state, maximum_seconds=1)
    assert result["status"] == "monitor_source_changed"


@pytest.fixture
def completed_preflight_campaign(failed_preflight_campaign, monkeypatch):
    """Author the terminal receipt through Native's actual receipt producer."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    fixture = failed_preflight_campaign
    heartbeat = deepcopy(fixture.preflight_heartbeat)
    heartbeat.update(status='agentic_maintenance_completed', last_agentic_maintenance_status='completed',
        last_agentic_maintenance_phase='supervisor_check_event', updated_at=stamp(fixture.started + 2))
    heartbeat['supervisor_maintenance'].update(phase='completed', timeout_seconds=900.0,
        deadline_at=stamp(fixture.started + 901))
    runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json', heartbeat)
    owner = native.ProcessBirthIdentity.from_dict(heartbeat['supervisor_process_birth'])
    assert owner is not None
    supervisor = object.__new__(native.PortalImplementationSupervisor)
    supervisor.config = SimpleNamespace(repo_root=fixture.repo, state_dir=fixture.state,
        state_path=fixture.state / 'complaint_intake_task_state.json', state_prefix='complaint_intake')
    with monkeypatch.context() as scope:
        scope.setattr(native, 'os', SimpleNamespace(getpid=lambda: owner.pid))
        scope.setattr(native, 'read_process_birth', lambda pid: owner if pid == owner.pid else None)
        native.PortalImplementationSupervisor._write_supervisor_maintenance_receipt(supervisor,
            'supervisor_check_event', status='completed', started_at=stamp(fixture.started + 1),
            updated_at=stamp(fixture.started + 2))
    return SimpleNamespace(**{**vars(fixture), 'preflight_heartbeat': heartbeat},
        maintenance_receipt=fixture.state / 'complaint_intake_supervisor_maintenance_receipt.json')


def test_completed_preflight_public_stop_uses_real_native_receipt_and_preserves_history(
        completed_preflight_campaign, docker, monkeypatch):
    fixture = completed_preflight_campaign
    observations = []
    def census(cutoff):
        observations.append(cutoff)
        return []
    monkeypatch.setattr(shutdown, '_complete_process_inventory', census)
    heartbeat = (fixture.state / 'complaint_intake_supervisor_status.json').read_bytes()
    receipt = fixture.maintenance_receipt.read_bytes()
    result = runner.stop(fixture.state)
    assert result['status'] == 'stopped' and result['signalled'] is False
    proof = result['container_shutdown']['process_closure']
    assert proof['source'] == 'owned_completed_preflight_native_receipt_and_double_complete_proc_inventory'
    assert proof['maintenance_receipt_sha256'] == hashlib.sha256(receipt).hexdigest()
    assert proof['preflight_without_managed_daemon'] is True
    assert proof['proc_census_complete'] is True and proof['observations'] == 2
    assert proof['daemon_birth_ticks_claimed'] is False and proof['signals_sent'] is False
    assert observations == [fixture.current_record['identity']['start_ticks']] * 2
    assert (fixture.state / 'complaint_intake_supervisor_status.json').read_bytes() == heartbeat
    assert fixture.maintenance_receipt.read_bytes() == receipt
    assert not docker[0].effects


@pytest.mark.parametrize('damage', ['missing', 'symlink', 'schema', 'repo', 'state_dir', 'state_path',
    'state_prefix', 'pid', 'birth_pid', 'birth_ticks', 'birth_boot', 'phase', 'status', 'started',
    'updated', 'completed', 'extra_field', 'deadline', 'timeout', 'managed_daemon', 'current_run', 'paid_start'])
def test_completed_preflight_refuses_unbound_native_receipt_or_launched_work(
        completed_preflight_campaign, docker, damage):
    fixture = completed_preflight_campaign
    path = fixture.maintenance_receipt
    receipt = json.loads(path.read_text())
    heartbeat = deepcopy(fixture.preflight_heartbeat)
    if damage == 'missing':
        path.unlink()
    elif damage == 'symlink':
        saved = path.with_suffix('.saved.json')
        path.rename(saved)
        path.symlink_to(saved)
    elif damage == 'schema': receipt['schema'] = 'unrelated'
    elif damage == 'repo': receipt['repo_root'] = str(fixture.repo.parent)
    elif damage == 'state_dir': receipt['state_dir'] = str(fixture.state.parent)
    elif damage == 'state_path': receipt['state_path'] = str(fixture.state / 'foreign.json')
    elif damage == 'state_prefix': receipt['state_prefix'] = 'foreign'
    elif damage == 'pid': receipt['supervisor_pid'] += 1
    elif damage == 'birth_pid': receipt['process_birth']['pid'] += 1
    elif damage == 'birth_ticks': receipt['process_birth']['start_time_ticks'] += 1
    elif damage == 'birth_boot': receipt['process_birth']['boot_id'] = 'foreign'
    elif damage == 'phase': receipt['phase'] = 'worktree_reconciliation'
    elif damage == 'status': receipt['status'] = 'running'
    elif damage == 'started': receipt['maintenance_started_at'] = stamp(fixture.started - 1)
    elif damage == 'updated': receipt['updated_at'] = stamp(fixture.started + 3)
    elif damage == 'completed': receipt['completed_at'] = stamp(fixture.started + 3)
    elif damage == 'extra_field': receipt['positive_execution_authority'] = True
    elif damage == 'deadline': heartbeat['supervisor_maintenance']['deadline_at'] = stamp(fixture.started + 902)
    elif damage == 'timeout': heartbeat['supervisor_maintenance']['timeout_seconds'] = 901
    elif damage == 'managed_daemon': heartbeat['daemon_pid'] = 1073741825
    elif damage == 'current_run':
        heartbeat['run_id'] = datetime.fromtimestamp(fixture.started, timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    else: (fixture.state / 'complaint_intake_events.jsonl').write_text(json.dumps(fixture.event) + '\n')
    if damage not in {'missing', 'symlink'}:
        runner._atomic_json(path, receipt)
    runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json', heartbeat)
    result = runner.stop(fixture.state)
    assert result['status'] == 'stop_incomplete' and result['signalled'] is False
    assert not docker[0].calls and not docker[0].effects


@pytest.mark.parametrize('damage', ['receipt_race', 'second_census_session'])
def test_completed_preflight_requires_stable_receipt_and_two_empty_fresh_censuses(
        completed_preflight_campaign, docker, monkeypatch, damage):
    fixture = completed_preflight_campaign
    calls = []
    def census(cutoff):
        calls.append(cutoff)
        if damage == 'receipt_race' and len(calls) == 1:
            receipt = json.loads(fixture.maintenance_receipt.read_text())
            receipt['process_birth']['start_time_ticks'] += 1
            runner._atomic_json(fixture.maintenance_receipt, receipt)
        if damage == 'second_census_session' and len(calls) == 2:
            return [{'pid':1073741826, 'uid':os.getuid(), 'process_group':0,
                'session':fixture.current_record['identity']['pid'], 'argv':['/usr/bin/python3'],
                'cwd':str(fixture.repo.parent), 'start_ticks':123457}]
        return []
    monkeypatch.setattr(shutdown, '_complete_process_inventory', census)
    result = runner.stop(fixture.state)
    assert result['status'] == 'stop_incomplete' and result['signalled'] is False
    assert not docker[0].calls and not docker[0].effects


@pytest.fixture
def historical_identity_preflight(completed_preflight_campaign, monkeypatch):
    """Actual Native stale-PID repair preserves the previous sealed identity."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as producer
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as native
    fixture = completed_preflight_campaign
    observer = native.read_process_birth(os.getpid())
    assert observer is not None and observer.start_time_ticks > 20
    record = deepcopy(fixture.current_record)
    record['identity']['start_ticks'] = observer.start_time_ticks - 5
    heartbeat = deepcopy(fixture.preflight_heartbeat)
    heartbeat['supervisor_process_birth']['start_time_ticks'] = record['identity']['start_ticks']
    runner._atomic_json(fixture.state / 'launcher.json', record)
    runner._atomic_json(fixture.state / 'complaint_intake_supervisor_status.json', heartbeat)
    owner = native.ProcessBirthIdentity.from_dict(heartbeat['supervisor_process_birth'])
    supervisor = object.__new__(producer.PortalImplementationSupervisor)
    supervisor.config = producer.PortalSupervisorConfig(repo_root=fixture.repo, state_dir=fixture.state,
        todo_path=Path(record['board_path']), state_path=fixture.state / 'complaint_intake_task_state.json',
        strategy_path=fixture.state / 'complaint_intake_strategy.json', state_prefix='complaint_intake',
        events_path=fixture.state / 'complaint_intake_supervisor_events.jsonl',
        daemon_script_path=fixture.repo / 'integrations/ipfs_accelerate/improvement_runner.py',
        worktree_root=Path(fixture.context['worktree_root']))
    with monkeypatch.context() as scope:
        scope.setattr(producer, 'os', SimpleNamespace(getpid=lambda: owner.pid))
        scope.setattr(producer, 'read_process_birth', lambda pid: owner if pid == owner.pid else None)
        producer.PortalImplementationSupervisor._write_supervisor_maintenance_receipt(supervisor,
            'supervisor_check_event', status='completed', started_at=stamp(fixture.started + 1),
            updated_at=stamp(fixture.started + 2))
    context = shutdown._context(fixture.state, record)
    old_birth = native.ProcessBirthIdentity(pid=1073741825, start_time_ticks=observer.start_time_ticks - 10,
        boot_id=observer.boot_id, parent_pid=1073741823)
    identity = native.SupervisedChildIdentity(process_birth=old_birth,
        command=shutdown._managed_native_command(record, context),
        owner_scope={'repo_root':str(fixture.repo), 'state_dir':str(fixture.state),
            'state_prefix':runner.STATE_PREFIX, 'todo_path':record['board_path'],
            'daemon_entrypoint':str(fixture.repo / 'integrations/ipfs_accelerate/improvement_runner.py')},
        created_at=stamp(fixture.started - 1))
    identity = native.SupervisedChildIdentity.from_dict(identity.to_dict())
    pid_path = fixture.state / 'complaint_intake_managed_daemon.pid'
    identity_path = pid_path.with_suffix('.identity.json')
    pid_path.write_text(f'{old_birth.pid}\n');pid_path.chmod(0o600)
    identity_path.write_text(json.dumps(identity.to_dict()));identity_path.chmod(0o600)
    before = identity_path.read_bytes()
    repaired = producer.PortalImplementationSupervisor.ensure_managed_daemon_pid_file(supervisor)
    assert repaired['repaired'] is True and repaired['reason'] == 'stale_managed_pid'
    assert not pid_path.exists() and identity_path.read_bytes() == before
    monkeypatch.setattr(native, 'terminate_supervised_child', lambda *_a, **_k: pytest.fail('historical identity never grants signal authority'))
    return SimpleNamespace(**{**vars(fixture), 'current_record':record, 'context':context,
        'preflight_heartbeat':heartbeat}, identity=identity, identity_path=identity_path,
        pid_path=pid_path, identity_bytes=before, native=native)


def test_actual_native_pid_repair_historical_identity_allows_current_preflight_closure(
        historical_identity_preflight, docker, monkeypatch):
    fixture = historical_identity_preflight
    # Invoke the actual complete inventory; other negative cases control only
    # the observation boundary to inject concrete forbidden processes/races.
    actual = _REAL_HISTORICAL_PROCESS_INVENTORY
    observations = []
    def inventory(cutoff):
        observations.append(cutoff)
        return actual(cutoff)
    monkeypatch.setattr(shutdown, '_complete_process_inventory', inventory)
    heartbeat = (fixture.state / 'complaint_intake_supervisor_status.json').read_bytes()
    before_receipt = fixture.maintenance_receipt.read_bytes()
    fenced = shutdown.fence_owned_orphan_native_child(fixture.state, fixture.current_record)
    assert fenced['status'] == 'historical_identity_already_closed' and fenced['fenced'] is False
    assert fenced['current_launch_child_authority'] is False
    result = runner.stop(fixture.state)
    assert result['status'] == 'stopped' and result['signalled'] is False
    proof = result['container_shutdown']['process_closure']
    assert proof['observations'] == 2 and proof['proc_census_complete'] is True
    assert proof['canonical_markers_absent'] is False and proof['canonical_pid_marker_absent'] is True
    assert proof['canonical_identity_marker_absent'] is False and proof['historical_identity_preserved'] is True
    assert proof['historical_native_identity']['current_launch_child_authority'] is False
    assert proof['minimum_owned_start_ticks'] == fixture.identity.process_birth.start_time_ticks
    assert len(observations) >= 2 and set(observations) == {fixture.identity.process_birth.start_time_ticks}
    assert fixture.identity_path.read_bytes() == fixture.identity_bytes and not fixture.pid_path.exists()
    assert (fixture.state / 'complaint_intake_supervisor_status.json').read_bytes() == heartbeat
    assert fixture.maintenance_receipt.read_bytes() == before_receipt and not docker[0].effects


@pytest.mark.parametrize('damage', ['scope', 'command', 'boot', 'current_birth', 'current_time',
    'live_pid', 'reused_pid', 'unknown_liveness', 'changed_identity', 'escaped_old_group'])
def test_historical_identity_never_bypasses_current_or_unknown_custody(
        historical_identity_preflight, docker, monkeypatch, damage):
    from dataclasses import replace
    fixture = historical_identity_preflight
    native, identity = fixture.native, fixture.identity
    if damage == 'scope':identity=replace(identity,owner_scope={**identity.owner_scope,'todo_path':'/foreign'},record_id='')
    elif damage == 'command':identity=replace(identity,command=(*identity.command,'--foreign-option'),record_id='')
    elif damage == 'boot':identity=replace(identity,process_birth=replace(identity.process_birth,boot_id='foreign'),record_id='')
    elif damage == 'current_birth':identity=replace(identity,process_birth=replace(identity.process_birth,start_time_ticks=fixture.current_record['identity']['start_ticks']+1),record_id='')
    elif damage == 'current_time':identity=replace(identity,created_at=stamp(fixture.started+1),record_id='')
    elif damage in {'live_pid','reused_pid'}:
        now=native.read_process_birth(os.getpid())
        birth=now if damage=='live_pid' else replace(identity.process_birth,pid=os.getpid())
        identity=replace(identity,process_birth=birth,record_id='')
    elif damage == 'unknown_liveness':
        monkeypatch.setattr(native,'supervised_child_identity_liveness',lambda _identity:native.OwnerLiveness.UNKNOWN)
    elif damage == 'changed_identity':
        def changed(_cutoff):
            fixture.identity_path.write_text(json.dumps(replace(identity,created_at=stamp(fixture.started-2),record_id='').to_dict()))
            return []
        monkeypatch.setattr(shutdown,'_complete_process_inventory',changed)
    elif damage == 'escaped_old_group':
        monkeypatch.setattr(shutdown,'_complete_process_inventory',lambda _cutoff:[{
            'pid':1073741826,'uid':os.getuid()+1,'process_group':identity.process_birth.parent_pid,
            'session':1073741826,'argv':(),'cwd':'/','prelaunch_scope_excluded':True}])
    fixture.identity_path.write_text(json.dumps(identity.to_dict()));fixture.identity_path.chmod(0o600)
    result = runner.stop(fixture.state)
    assert result['status'] == 'stop_incomplete' and result['signalled'] is False
    assert fixture.identity_path.exists() and not fixture.pid_path.exists() and not docker[0].effects
