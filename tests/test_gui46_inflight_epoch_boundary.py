"""Authored real owner HTTP write vs. public cryptographic revocation ordering."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient

from integrations import private_storage
from integrations.private_storage import PrivateArtifactBinding, parse_private_envelope
from tests.test_cimp_gui_14 import _composed_login, _composed_headers, PASSPHRASE
from tests.test_gui46_private_owner_controls import _world, _headers, _change, _retained_key

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


def test_actual_inflight_owner_answer_cannot_publish_old_dek_after_revocation(tmp_path,monkeypatch):
    world=_world(tmp_path)
    world.owner_keys.unlock_passphrase(PASSPHRASE)
    world.service.unlock_private_keys(passphrase=PASSPHRASE)
    binding=PrivateArtifactBinding(tenant_id=world.case.tenant_id,case_id=world.case.case_id,
        principal_id=world.case.tenant_id,artifact_kind='session',revision='session-v1')
    repository=world.service.joined_revision_repository(world.case.tenant_id,world.case.case_id)
    old_id,_=world.owner_keys.provider().resolve(binding)
    entered,release=Event(),Event()
    actual=private_storage._atomic_write
    def pause_after_real_head_staging(directory,name,payload,**kwargs):
        if directory==repository and name==private_storage._HEAD_NAME and not entered.is_set():
            original_check=kwargs.get('before_replace')
            def publication_boundary():
                entered.set()
                assert release.wait(20),'authored publication barrier timed out'
                return original_check() if original_check is not None else None
            kwargs['before_replace']=publication_boundary
        return actual(directory,name,payload,**kwargs)
    # Two real ASGI portals model concurrent workers. The request bodies,
    # cookie authorization, crypto and WAL path are unchanged; only delivery
    # at the actual already-fsynced head replacement is paused.
    with TestClient(world.review_app,base_url='https://testserver') as owner, TestClient(world.review_app,base_url='https://testserver') as writer:
        csrf=_composed_login(owner)
        writer.cookies.update(owner.cookies)
        issued=owner.post('/api/cases/assignments/'+world.membership.grant_id+'/key-grant',headers=_headers(csrf),json={
            'artifact_kind':'session','artifact_revision':'session-v1','idempotency_key':'authored-inflight-retained-key'})
        assert issued.status_code==201,issued.text
        retained=_retained_key(world,world.grants.load(issued.json()['key_grant_id']))
        view=owner.get('/api/complaint-workspace/session',headers=_composed_headers(world.case))
        assert view.status_code==200,view.text
        shared=view.json()['session']['shared_interview'];pending=shared['pending_inquiry']
        head_before=(repository/private_storage._HEAD_NAME).read_bytes()
        monkeypatch.setattr(private_storage,'_atomic_write',pause_after_real_head_staging)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(writer.post,'/api/complaint-workspace/intake-chat',headers=_composed_headers(world.case,csrf),json={
                'interview_action':'answer','question_id':pending['inquiry_id'],
                'expected_question_revision':pending['revision'],
                'message':'Authored owner answer paused before the public key cutoff.'})
            assert entered.wait(20),'actual owner write did not reach the head publication boundary'
            try:
                revoked,_=_change(world,owner,csrf,revoke=True,key='authored-inflight-cutoff')
                assert revoked.status_code==200 and revoked.json()['revoked'] is True,revoked.text
                assert world.owner_keys.provider().resolve(binding)[0]!=old_id
            finally:
                release.set()
            response=future.result(timeout=20)
        head_after=(repository/private_storage._HEAD_NAME).read_bytes()
        envelope,revision=private_storage._head_record(repository)
        published_old_epoch=head_after!=head_before and parse_private_envelope(envelope)['key_id']==old_id
        assert not published_old_epoch,{'response_status':response.status_code,'old_epoch_published_after_completed_revoke':True}
        assert response.status_code in {403,409,503},response.text
        assert head_after==head_before
        current=owner.get('/api/complaint-workspace/session',headers=_composed_headers(world.case))
        assert current.status_code==200,current.text
        assert current.json()['session']['shared_interview']['pending_inquiry']==pending
        fresh=owner.post('/api/complaint-workspace/intake-chat',headers=_composed_headers(world.case,csrf),json={
            'interview_action':'answer','question_id':pending['inquiry_id'],
            'expected_question_revision':pending['revision'],
            'message':'Authored owner answer paused before the public key cutoff.'})
        assert fresh.status_code==200,fresh.text
        fresh_envelope,_=private_storage._head_record(repository)
        assert parse_private_envelope(fresh_envelope)['key_id']==world.owner_keys.provider().resolve(binding)[0]!=old_id

