"""Same-portal finite stop cutoff and committed response delivery boundaries."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
import os

import pytest
from fastapi.testclient import TestClient

from applications.complaint_workspace import ComplaintWorkspaceService
from tests.test_cimp_gui_14 import _composed_case_world,_composed_headers,_composed_login,PASSPHRASE
from tests.test_cimp_gui_16 import NARRATIVE

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


def _start(client,world):
    csrf=_composed_login(client)
    response=client.post('/api/complaint-workspace/intake-chat',headers=_composed_headers(world.case,csrf),
        json={'message':NARRATIVE,'interview_action':'start'})
    assert response.status_code==200
    return csrf


def _stop(client,world,csrf,protocol):
    headers=_composed_headers(world.case,csrf)
    arguments={'message':'','interview_action':'pause'}
    if protocol=='http':return client.post('/api/complaint-workspace/intake-chat',headers=headers,json=arguments)
    if protocol=='mcp':return client.post('/api/complaint-workspace/mcp/call',headers=headers,
        json={'tool_name':'complaint.run_intake_chat_turn','arguments':arguments})
    return client.post('/api/complaint-workspace/mcp/rpc',headers=headers,json={
        'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'complaint.run_intake_chat_turn','arguments':arguments}})


@pytest.mark.parametrize('protocol',['http','mcp','rpc'])
def test_actual_same_portal_logout_finishes_before_finite_head_and_recovery_stays_closed(tmp_path,monkeypatch,protocol):
    from integrations import private_storage
    world=_composed_case_world(tmp_path);service=world.services[world.case.case_id]
    staged,release=Event(),Event();original=private_storage._fsync_file
    with TestClient(world.app,base_url='https://testserver') as client:
        csrf=_start(client,world);repo=service.joined_revision_repository(world.case.tenant_id,world.case.case_id)
        head=repo/'head.cgpe';before=head.read_bytes();commits=private_storage._native_commit_transactions(repo)
        def paused(descriptor,operation):
            original(descriptor,operation);path=Path(os.readlink('/proc/self/fd/'+str(descriptor)))
            if path.parent==repo and path.read_bytes().startswith(private_storage._HEAD_RECORD_MAGIC):
                staged.set();assert release.wait(20)
        monkeypatch.setattr(private_storage,'_fsync_file',paused)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(_stop,client,world,csrf,protocol)
            try:
                assert staged.wait(20)
                # Same TestClient means the same ASGI portal/event loop.
                assert client.post('/api/complaint-workspace/auth/logout',headers={'x-csrf-token':csrf}).status_code==200
            finally:release.set()
            response=pending.result(timeout=20)
        if protocol=='http':assert response.status_code==403
        else:
            assert response.status_code==200
            body=response.json();assert body.get('isError') is True or body.get('error') or (body.get('result') or {}).get('isError') is True
        assert NARRATIVE not in response.text and head.read_bytes()==before
        assert private_storage._native_commit_transactions(repo)==commits
        service.recover_joined_intake_revision(world.case.tenant_id,case_id=world.case.case_id)
        assert head.read_bytes()==before and private_storage._native_commit_transactions(repo)==commits


@pytest.mark.parametrize('boundary',['key','logout'])
def test_committed_finite_stop_rechecks_private_response_but_keeps_its_commit(tmp_path,monkeypatch,boundary):
    world=_composed_case_world(tmp_path);service=world.services[world.case.case_id]
    projected,release=Event(),Event();actual=ComplaintWorkspaceService._build_intake_chat_payload
    def paused(self,state,*args,**kwargs):
        value=actual(self,state,*args,**kwargs)
        if self is service and (state.get('interview_stop') or {}).get('control')=='pause':
            projected.set();assert release.wait(20)
        return value
    with TestClient(world.app,base_url='https://testserver') as client:
        csrf=_start(client,world);head=service.joined_revision_repository(world.case.tenant_id,world.case.case_id)/'head.cgpe'
        before=head.read_bytes();monkeypatch.setattr(ComplaintWorkspaceService,'_build_intake_chat_payload',paused)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(_stop,client,world,csrf,'http')
            try:
                assert projected.wait(20);committed=head.read_bytes();assert committed!=before
                if boundary=='key':service.lock_private_keys()
                else:assert client.post('/api/complaint-workspace/auth/logout',headers={'x-csrf-token':csrf}).status_code==200
            finally:release.set()
            response=pending.result(timeout=20)
        assert response.status_code in {401,403,409,503} and NARRATIVE not in response.text
        assert head.read_bytes()==committed
        if boundary=='key':service.unlock_private_keys(passphrase=PASSPHRASE)
        _composed_login(client)
        current=client.get('/api/complaint-workspace/session',headers=_composed_headers(world.case))
        assert current.status_code==200 and current.json()['session']['intentional_user_wait']['paused'] is True
        assert head.read_bytes()==committed
