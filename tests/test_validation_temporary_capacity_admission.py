"""The actual public start boundary must cover Native's distinct short temp root."""
from pathlib import Path
from types import SimpleNamespace
import os

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner


@pytest.fixture
def storage(tmp_path, monkeypatch):
    paths = {name: tmp_path / name for name in ('repository', 'worktrees', 'home',
        'temporary', 'containerd_metadata', 'validation_temporary', 'state')}
    for path in paths.values():
        path.mkdir(mode=0o700)
    monkeypatch.setattr(runner, '_containerd_metadata_directory', lambda: paths['containerd_metadata'])
    # Existing filesystem discovery seam; no filesystem/ownership API is faked.
    monkeypatch.setattr(runner, '_native_validation_temporary_directory',
        lambda: paths['validation_temporary'], raising=False)
    monkeypatch.setenv('HOME', str(paths['home']))
    monkeypatch.setenv('TMPDIR', str(paths['temporary']))
    return paths


def sample_only_native_temporary(monkeypatch, paths, failure=None):
    actual = os.statvfs
    def observe(path):
        if Path(path) != paths['validation_temporary']:
            return actual(path)
        if failure == 'unavailable':
            raise PermissionError('synthetic Native temp filesystem unavailable')
        row = actual(path)
        return SimpleNamespace(
            f_bavail=runner.RESOURCE_MIN_FREE_BYTES - (failure == 'bytes'), f_frsize=1,
            f_favail=runner.RESOURCE_MIN_FREE_INODES - (failure == 'inodes'),
            f_files=row.f_files, f_flag=row.f_flag)
    monkeypatch.setattr(runner.os, 'statvfs', observe)


@pytest.mark.parametrize('failure', ['bytes', 'inodes', 'unavailable', 'missing'])
def test_public_start_refuses_only_native_temporary_failure_before_any_launch(storage, monkeypatch, failure):
    if failure == 'missing':
        storage['validation_temporary'].rmdir()
    sample_only_native_temporary(monkeypatch, storage, failure)
    counter = storage['state'] / 'complaint_intake_task_state.json'
    counter.write_text('{"implementation_attempts":{"CIMP-UX-15":2},"provider_outcome":"unknown"}')
    before = (counter.read_bytes(), counter.stat().st_ino, counter.stat().st_mtime_ns)
    def forbidden(*args, **kwargs):
        pytest.fail('a Native temp capacity hold reached preparation, a lock, Native, or a provider')
    monkeypatch.setattr(runner, '_lock', forbidden)
    monkeypatch.setattr(runner, 'prepare', forbidden)
    monkeypatch.setattr(runner, '_native_modules', forbidden)
    monkeypatch.setattr(runner.subprocess, 'Popen', forbidden)
    spec = storage['repository'] / 'must-remain-unread.json'
    result = runner.start(storage['repository'], spec, storage['state'], worktree_root=storage['worktrees'])
    assert result['status'] == 'not_ready' and result['reason'] == 'campaign_resource_hold'
    assert result['execution_started'] is False and result['paid_calls'] == 0
    observation = result['resource_capacity']
    assert observation['roles']['validation_temporary']['ready'] is False
    assert all(row['ready'] for name, row in observation['roles'].items() if name != 'validation_temporary')
    assert (counter.read_bytes(), counter.stat().st_ino, counter.stat().st_mtime_ns) == before
    assert list(storage['state'].iterdir()) == [counter]
    assert list(storage['worktrees'].iterdir()) == [] and not spec.exists()


def test_native_temporary_uses_existing_policy_floors_and_never_the_profile_alias(storage, monkeypatch):
    sample_only_native_temporary(monkeypatch, storage)
    result = runner._resource_capacity(storage['repository'], storage['state'], storage['worktrees'], os.environ)
    assert result['ready'] is True
    row = result['roles']['validation_temporary']
    assert Path(row['filesystem_path']) == storage['validation_temporary']
    assert row['free_bytes'] == runner.RESOURCE_MIN_FREE_BYTES
    assert row['free_inodes'] == runner.RESOURCE_MIN_FREE_INODES
    assert Path(result['roles']['temporary']['filesystem_path']) == storage['temporary']
    assert list(storage['state'].iterdir()) == [] and list(storage['validation_temporary'].iterdir()) == []
