"""Late owner reproof happens at the actual encrypted head publication."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
import os
import pytest
from fastapi.testclient import TestClient
from integrations import private_storage
from tests.test_gui25_26_private_owner_http import _world, _login, _headers
from tests.test_gui30_private_owner import _source, _request

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_definition_replay_cannot_publish_after_actual_head_fsync_then_key_lock(tmp_path, monkeypatch):
    world = _world(tmp_path)
    entered, release = Event(), Event()
    original = private_storage._fsync_file
    with TestClient(world.app, base_url='https://testserver') as client:
        csrf = _login(client)
        source = _source(client, world, csrf)
        body = _request(client, world, source)
        repository = world.service.joined_revision_repository(world.case.tenant_id, world.case.case_id)
        before = (repository / 'head.cgpe').read_bytes()
        def actual_head_then_pause(fd, operation):
            original(fd, operation)
            staged = Path(os.readlink(f'/proc/self/fd/{fd}'))
            if staged.parent == repository and staged.read_bytes().startswith(private_storage._HEAD_RECORD_MAGIC):
                entered.set()
                assert release.wait(20)
        monkeypatch.setattr(private_storage, '_fsync_file', actual_head_then_pause)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(client.post,
                '/api/legal-analysis/' + world.case.case_id + '/definition-correspondence',
                headers=_headers(world, csrf), json=body)
            try:
                assert entered.wait(500), 'genuine_owner_replay_did_not_reach_encrypted_head'
                assert (repository / 'head.cgpe').read_bytes() == before
                world.service.lock_private_keys()
            finally:
                release.set()
            result = pending.result(timeout=25)
        assert result.status_code in {403,409,503}
        assert (repository / 'head.cgpe').read_bytes() == before
        assert not list(repository.glob('.*.tmp'))
        world.service.unlock_private_keys(passphrase='synthetic-password')
        world.service.recover_joined_intake_revision(world.case.tenant_id, case_id=world.case.case_id)
        assert (repository / 'head.cgpe').read_bytes() == before
