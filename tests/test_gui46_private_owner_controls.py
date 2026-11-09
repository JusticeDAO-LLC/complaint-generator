"""Authored real encrypted owner/recipient cases; current Task46 contract audit."""
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from applications.case_assignment_api import CaseAssignmentService
from integrations.private_storage import (PrivateArtifactBinding, PrivateArtifactIntegrityError,
    open_private_artifact, parse_private_envelope, seal_private_artifact)
from tests.test_cimp_gui_14 import _composed_login, PASSPHRASE
from tests.test_gui32_private_review_http import _world as _review_world, _headers as _review_headers

pytestmark = [pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


def _service(world):
    return CaseAssignmentService(principals=world.principals,cases=world.cases,
        memberships=world.memberships,key_grants=world.grants,
        sessions={world.owner.principal_id:world.owner_keys,world.lawyer.principal_id:world.recipient},
        clock=lambda:int(time.time()))


def _world(tmp_path):
    world=_review_world(tmp_path,actual_workspace_as_mediator=True)
    assert world.owner.principal_id != world.case.tenant_id
    world.review_app.state.case_assignments=_service(world)
    return world


def _headers(csrf):
    return {'x-csrf-token':csrf}


def _change(world,client,csrf,*,key='real-owner-change',**updates):
    body={'confirm_grant_change':True,'expected_version':world.membership.version,
        'idempotency_key':key,**updates}
    return client.post('/api/cases/assignments/'+world.membership.grant_id+'/change',headers=_headers(csrf),json=body),body


def _retained_key(world,grant):
    return world.recipient.unwrap_granted_resource_key(
        {'nonce':grant.wrapped_nonce,'ciphertext':grant.wrapped_ciphertext},
        tenant_id=grant.tenant_id,case_id=grant.case_id,canonical_principal_id=grant.canonical_owner_principal_id,
        revision=grant.artifact_revision,recipient_principal_id=grant.recipient_principal_id,
        artifact_kind=grant.artifact_kind,resource_id=grant.resource_id,
        membership_grant_id=grant.membership_grant_id,membership_version=grant.membership_version,
        data_key_id=grant.data_key_id,recipient_wrap_key_id=grant.recipient_wrap_key_id)


def test_actual_owner_revocation_denies_retained_key_on_future_owner_ciphertext(tmp_path):
    world=_world(tmp_path)
    world.owner_keys.unlock_passphrase(PASSPHRASE)
    world.service.unlock_private_keys(passphrase=PASSPHRASE)
    binding=PrivateArtifactBinding(tenant_id=world.case.tenant_id,case_id=world.case.case_id,
        principal_id=world.case.tenant_id,artifact_kind='session',revision='session-v1')
    with TestClient(world.review_app,base_url='https://testserver') as owner, TestClient(world.review_app,base_url='https://testserver') as lawyer:
        csrf=_composed_login(owner)
        _composed_login(lawyer,'synthetic-lawyer-credential')
        assert lawyer.get('/api/legal-analysis/'+world.case.case_id+'/lawyer-reviews',headers=_review_headers(world)).status_code==200
        issued=owner.post('/api/cases/assignments/'+world.membership.grant_id+'/key-grant',headers=_headers(csrf),json={
            'artifact_kind':'session','artifact_revision':'session-v1','idempotency_key':'real-retained-owner-key'})
        assert issued.status_code==201,issued.text
        grant=world.grants.load(issued.json()['key_grant_id'])
        retained=_retained_key(world,grant)
        old_id,_old=world.owner_keys.provider().resolve(binding)
        revoked,_=_change(world,owner,csrf,revoke=True,key='real-owner-revocation')
        assert revoked.status_code==200 and revoked.json()['revoked'] is True,revoked.text
        assert lawyer.get('/api/legal-analysis/'+world.case.case_id+'/lawyer-reviews',headers=_review_headers(world)).status_code==403
        key_id,key=world.owner_keys.provider().resolve(binding)
        future=seal_private_artifact(b'Authored future owner record after public revocation.',binding=binding,key=key,key_id=key_id)
        # Use the actual new header ID deliberately: the test must fail AES
        # authentication, not merely a string comparison with an old ID.
        assert open_private_artifact(future,binding=binding,key=key,expected_key_id=key_id).startswith(b'Authored future')
        with pytest.raises(PrivateArtifactIntegrityError,match='authentication_failed'):
            open_private_artifact(future,binding=binding,key=retained,expected_key_id=parse_private_envelope(future)['key_id'])
        assert key_id != old_id


def test_actual_owner_change_keeps_idempotent_audit_after_service_reopen(tmp_path):
    world=_world(tmp_path)
    with TestClient(world.review_app,base_url='https://testserver') as owner:
        csrf=_composed_login(owner)
        changed,body=_change(world,owner,csrf,scope=['case.read'],key='real-owner-cold-replay')
        assert changed.status_code==200 and len(changed.json()['audit'])==1,changed.text
        version=world.memberships.load(world.membership.grant_id).version
        world.review_app.state.case_assignments=_service(world)
        inspected=owner.get('/api/cases/assignments/'+world.membership.grant_id)
        replay=owner.post('/api/cases/assignments/'+world.membership.grant_id+'/change',headers=_headers(csrf),json=body)
        assert world.memberships.load(world.membership.grant_id).version==version
        actual=(len(inspected.json()['audit']),replay.status_code,replay.json().get('idempotent_replay'))
        assert actual==(1,200,True),actual


def test_actual_session_expiry_during_membership_encryption_refuses_publication(tmp_path,monkeypatch):
    from applications import case_membership
    world=_world(tmp_path)
    before=world.memberships.load(world.membership.grant_id)
    original=case_membership.seal_private_artifact
    reached=[]
    def expire_after_real_encryption(*args,**kwargs):
        envelope=original(*args,**kwargs)
        if kwargs['binding'].case_id==world.case.case_id and kwargs['binding'].revision==str(before.version+1):
            reached.append(True)
            world.clock['now']+=301
        return envelope
    with TestClient(world.review_app,base_url='https://testserver') as owner:
        csrf=_composed_login(owner)
        monkeypatch.setattr(case_membership,'seal_private_artifact',expire_after_real_encryption)
        response,_=_change(world,owner,csrf,scope=['case.read','case.review','case.download'],key='real-expired-grant-change')
        assert reached
        assert owner.get('/api/complaint-workspace/auth/session').status_code==401
        current=world.memberships.load(world.membership.grant_id)
        assert (response.status_code,current.version,current.actions)==(401,before.version,before.actions),(
            response.status_code,current.version,current.actions)


def test_real_owner_grant_response_cannot_repaint_after_actual_clear(tmp_path):
    from tests.test_cimp_gui_46 import _browser
    from tests import gui_native_browser as browser
    world=_world(tmp_path)
    private_browser=tmp_path/'browser';private_browser.mkdir()
    with _browser(private_browser,world.review_app) as page:
        page.goto(browser.SAME_ORIGIN+'/case-grants',wait_until='domcontentloaded')
        page.wait_for_function("['ready','partial','denied','error'].includes(document.body.dataset.workspaceHydrated)")
        issued=page.evaluate('''async () => {
            const response=await fetch('/api/complaint-workspace/auth/login',{method:'POST',credentials:'same-origin',
                headers:{'content-type':'application/json'},body:JSON.stringify({credential:'synthetic-owner-credential'})});
            if(response.status!==200)throw new Error('actual login failed');return await response.json();
        }''')
        assert issued['principal_id']==world.owner.principal_id != world.case.tenant_id
        page.fill('#grant-csrf',issued['csrf_token'])
        page.fill('#grant-id',world.membership.grant_id)
        # Delay delivery of the unchanged real ASGI Response, never fabricate
        # fetch data. A zero-delay completion task observes the real JSON await.
        page.evaluate('''target => {
            const original=window.fetch.bind(window);
            window.fetch=async (...args) => {
                const response=await original(...args);
                if(String(args[0])===target){
                    window.actualGrantStatus=response.status;
                    window.actualGrantWaiting=true;
                    await new Promise(resolve => {window.releaseActualGrant=resolve;});
                    const json=response.json.bind(response);
                    response.json=async () => {
                        const payload=await json();
                        setTimeout(() => {window.actualGrantDeliverySettled=true;},0);
                        return payload;
                    };
                }
                return response;
            };
        }''','/api/cases/assignments/'+world.membership.grant_id)
        page.click('#grant-inspect')
        page.wait_for_function('window.actualGrantWaiting===true')
        assert page.evaluate('window.actualGrantStatus')==200
        page.click('#workspace-clear-private-state')
        page.wait_for_function("document.body.dataset.workspaceHydrated==='cleared'")
        assert page.input_value('#grant-id')=='' and page.input_value('#grant-csrf')==''
        page.evaluate('window.releaseActualGrant()')
        page.wait_for_function('window.actualGrantDeliverySettled===true')
        visible=page.evaluate("['grant-status','grant-effective-scope','grant-effective-revision','grant-effective-flag'].map(id=>document.getElementById(id).textContent)")
        assert visible==['','','',''],visible


def test_real_case_rotation_preserves_cold_owner_joined_read_and_future_write(tmp_path):
    from tests.test_cimp_gui_14 import _composed_headers
    world=_world(tmp_path)
    world.owner_keys.unlock_passphrase(PASSPHRASE)
    world.service.unlock_private_keys(passphrase=PASSPHRASE)
    with TestClient(world.review_app,base_url='https://testserver') as owner:
        csrf=_composed_login(owner)
        before=owner.get('/api/complaint-workspace/session',headers=_composed_headers(world.case))
        assert before.status_code==200,before.text
        receipt=world.grants.revoke_and_rotate(actor_principal_id=world.owner.principal_id,
            recipient_principal_id=world.lawyer.principal_id,case_id=world.case.case_id,
            tenant_id=world.case.tenant_id,resource_id=world.case.resource_id,cutoff=1,
            owner_session=world.owner_keys,idempotency_key='actual-owner-joined-rotation')
        assert receipt['data_key_rotated'] is True
        world.service.lock_private_keys()
        world.service.unlock_private_keys(passphrase=PASSPHRASE)
        after=owner.get('/api/complaint-workspace/session',headers=_composed_headers(world.case))
        assert after.status_code==200,after.text
        assert after.json()['session']['private_revision']==before.json()['session']['private_revision']
        shared=after.json()['session']['shared_interview']
        inquiry=shared['pending_inquiry']
        advanced=owner.post('/api/complaint-workspace/intake-chat',headers=_composed_headers(world.case,csrf),json={
            'interview_action':'answer','question_id':inquiry['inquiry_id'],
            'expected_question_revision':inquiry['revision'],
            'message':'Authored post-revocation owner answer about the selected event.'})
        assert advanced.status_code==200,advanced.text
        assert advanced.json()['interview']['session_revision']==shared['session_revision']+1
        world.service.lock_private_keys()
        world.service.unlock_private_keys(passphrase=PASSPHRASE)
        reopened=owner.get('/api/complaint-workspace/session',headers=_composed_headers(world.case))
        assert reopened.status_code==200,reopened.text
        assert int(reopened.json()['session']['private_revision'])>int(after.json()['session']['private_revision'])



def test_joined_rotation_authenticates_each_historical_epoch_and_new_writes(tmp_path):
    from integrations.private_storage import (UserOwnedKeySession, commit_private_revision,
        read_private_revision, PrivateRevisionError, PrivateKeyLockedError)
    session=UserOwnedKeySession(tmp_path/'keys')
    session.create(protection='passphrase',passphrase=PASSPHRASE)
    session.ensure_data_key('authored-tenant','authored-case')
    old_id,old_key=session.provider().resolve(PrivateArtifactBinding(tenant_id='authored-tenant',case_id='authored-case',principal_id='authored-tenant',artifact_kind='session',revision='session-v1'))
    root=tmp_path/'joined'
    fields=dict(tenant_id='authored-tenant',case_id='authored-case',principal_id='authored-tenant')
    first=commit_private_revision(root,**fields,key=old_key,key_id=old_id,expected_revision='0',
        session=b'authored old session',fact_graph=b'authored old facts',proof=b'authored old proof')
    assert first.committed
    rotation=session.rotate_case_grant_data_key('authored-tenant','authored-case',
        resource_id='authored-resource',expected_data_key_id=old_id,operation_id='authored-rotation')
    new_id,new_key=session.provider().resolve(PrivateArtifactBinding(**fields,artifact_kind='session',revision='session-v1'))
    assert rotation['new_data_key_id']==new_id != old_id
    lookup=lambda identity:session.lookup_data_key('authored-tenant','authored-case',identity)
    assert read_private_revision(root,**fields,key=new_key,key_id=new_id,key_resolver=lookup)['session']==b'authored old session'
    second=commit_private_revision(root,**fields,key=new_key,key_id=new_id,expected_revision='1',
        session=b'authored new session',fact_graph=b'authored new facts',proof=b'authored new proof',key_resolver=lookup)
    assert second.committed
    assert read_private_revision(root,**fields,key=new_key,key_id=new_id,key_resolver=lookup)['session']==b'authored new session'
    with pytest.raises(PrivateRevisionError):
        read_private_revision(root,**fields,key=new_key,key_id=new_id,
            key_resolver=lambda identity:session.lookup_data_key('authored-tenant','other-case',identity))
    with pytest.raises(PrivateRevisionError):
        read_private_revision(root,**fields,key=old_key,key_id=old_id)
    session.lock()
    with pytest.raises(PrivateRevisionError,match="did not authenticate"):
        read_private_revision(root,**fields,key=new_key,key_id=new_id,key_resolver=lookup)


def test_revocation_partial_key_commit_is_fenced_and_cold_retry_reuses_epoch(tmp_path,monkeypatch):
    from integrations.private_collaboration import CaseResourceKeyGrantStore
    world=_world(tmp_path)
    world.owner_keys.unlock_passphrase(PASSPHRASE)
    world.service.unlock_private_keys(passphrase=PASSPHRASE)
    binding=PrivateArtifactBinding(tenant_id=world.case.tenant_id,case_id=world.case.case_id,
        principal_id=world.case.tenant_id,artifact_kind='session',revision='session-v1')
    old_id,_=world.owner_keys.provider().resolve(binding)
    original=CaseResourceKeyGrantStore._seal
    reached=[]
    def fail_after_key_commit(store,grant,**kwargs):
        if store is world.grants and grant.status=='revoked' and not reached:
            reached.append(True)
            raise OSError('authored post-key/pre-grant publication fault')
        return original(store,grant,**kwargs)
    with TestClient(world.review_app,base_url='https://testserver') as owner:
        csrf=_composed_login(owner)
        monkeypatch.setattr(CaseResourceKeyGrantStore,'_seal',fail_after_key_commit)
        first,body=_change(world,owner,csrf,revoke=True,key='authored-partial-revocation')
        assert reached and first.status_code==409,first.text
        assert first.json()=={'error':'case_key_rotation_incomplete'}
        pending=world.memberships.load(world.membership.grant_id)
        assert pending.version==world.membership.version
        assert pending.owner_changes[-1]['phase']=='prepared'
        new_id,_=world.owner_keys.provider().resolve(binding)
        assert new_id!=old_id
        with pytest.raises(Exception) as refused:
            world.memberships.authorize(actor_principal_id=world.lawyer.principal_id,
                grant_id=pending.grant_id,tenant_id=pending.tenant_id,case_id=pending.case_id,
                resource_id=pending.resource_id,action='case.read',expected_version=pending.version)
        assert getattr(refused.value,'code',None)=='owner_change_pending'
        world.review_app.state.case_assignments=_service(world)
        completed=owner.post('/api/cases/assignments/'+pending.grant_id+'/change',headers=_headers(csrf),json=body)
        assert completed.status_code==200,completed.text
        assert completed.json()['revoked'] is True and len(completed.json()['audit'])==1
        assert world.owner_keys.provider().resolve(binding)[0]==new_id
        replay=owner.post('/api/cases/assignments/'+pending.grant_id+'/change',headers=_headers(csrf),json=body)
        assert replay.status_code==200 and replay.json()['idempotent_replay'] is True,replay.text
        assert len(replay.json()['audit'])==1 and world.owner_keys.provider().resolve(binding)[0]==new_id


def test_actual_same_portal_logout_during_member_crypto_aborts_and_fresh_login_resumes(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from applications import case_membership
    from applications.browser_sessions import SESSION_COOKIE
    world=_world(tmp_path)
    entered,release=Event(),Event()
    original=case_membership.seal_private_artifact
    def hold_after_crypto(*args,**kwargs):
        value=original(*args,**kwargs)
        if kwargs['binding'].case_id==world.case.case_id and not entered.is_set():
            entered.set()
            assert release.wait(10)
        return value
    with TestClient(world.review_app,base_url='https://testserver') as owner:
        csrf=_composed_login(owner)
        monkeypatch.setattr(case_membership,'seal_private_artifact',hold_after_crypto)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(_change,world,owner,csrf,scope=['case.read'],key='actual-logout-pending-change')
            assert entered.wait(10)
            logout=owner.post('/api/complaint-workspace/auth/logout',headers=_headers(csrf),json={})
            assert logout.status_code==200,logout.text
            release.set()
            denied,body=future.result(timeout=10)
        assert denied.status_code==401,denied.text
        current=world.memberships.load(world.membership.grant_id)
        assert current.version==world.membership.version and current.owner_changes==()
        fresh=_composed_login(owner)
        resumed=owner.post('/api/cases/assignments/'+current.grant_id+'/change',headers=_headers(fresh),json=body)
        assert resumed.status_code==200 and len(resumed.json()['audit'])==1,resumed.text


def test_concurrent_identical_owner_changes_publish_one_audit_and_changed_replay_refuses(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    world=_world(tmp_path)
    with TestClient(world.review_app,base_url='https://testserver') as owner:
        csrf=_composed_login(owner)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(_change,world,owner,csrf,scope=['case.read'],key='actual-concurrent-owner') for _ in range(2)]
            results=[f.result(timeout=20)[0] for f in futures]
        assert [r.status_code for r in results]==[200,200],[r.text for r in results]
        assert sorted(r.json()['idempotent_replay'] for r in results)==[False,True]
        current=world.memberships.load(world.membership.grant_id)
        assert current.version==world.membership.version+1 and len(current.owner_changes)==1
        changed,_=_change(world,owner,csrf,scope=['case.read','case.review'],key='actual-concurrent-owner')
        assert changed.status_code==409 and changed.json()['error']=='replay_mismatch',changed.text
        assert world.memberships.load(current.grant_id)==current


def test_configured_owner_wallet_lock_during_member_crypto_denies_change(tmp_path,monkeypatch):
    from applications import case_membership
    world=_world(tmp_path)
    world.owner_keys.unlock_passphrase(PASSPHRASE)
    original=case_membership.seal_private_artifact
    reached=[]
    def lock_after_crypto(*args,**kwargs):
        value=original(*args,**kwargs)
        if kwargs['binding'].case_id==world.case.case_id and not reached:
            reached.append(True);world.owner_keys.lock()
        return value
    with TestClient(world.review_app,base_url='https://testserver') as owner:
        csrf=_composed_login(owner)
        monkeypatch.setattr(case_membership,'seal_private_artifact',lock_after_crypto)
        denied,body=_change(world,owner,csrf,scope=['case.read'],key='actual-wallet-cutoff')
        assert reached and denied.status_code==503 and denied.json()['error']=='key_owner_required',denied.text
        current=world.memberships.load(world.membership.grant_id)
        assert current.version==world.membership.version and current.owner_changes==()
        world.owner_keys.unlock_passphrase(PASSPHRASE)
        resumed=owner.post('/api/cases/assignments/'+current.grant_id+'/change',headers=_headers(csrf),json=body)
        assert resumed.status_code==200 and len(resumed.json()['audit'])==1,resumed.text


def test_actual_owner_wallet_lock_at_keystore_fsync_fences_until_exact_retry(tmp_path,monkeypatch):
    from integrations import private_storage
    world=_world(tmp_path)
    world.owner_keys.unlock_passphrase(PASSPHRASE)
    world.service.unlock_private_keys(passphrase=PASSPHRASE)
    binding=PrivateArtifactBinding(tenant_id=world.case.tenant_id,case_id=world.case.case_id,
        principal_id=world.case.tenant_id,artifact_kind='session',revision='session-v1')
    old_id,_=world.owner_keys.provider().resolve(binding)
    original=private_storage._write_private_bytes
    reached=[]
    def lock_after_real_fsync(path,*args,**kwargs):
        result=original(path,*args,**kwargs)
        if Path(path)==world.owner_keys.directory/('.'+private_storage.KEY_STORE_FILENAME+'.tmp') and not reached:
            reached.append(True);world.owner_keys.lock()
        return result
    with TestClient(world.review_app,base_url='https://testserver') as owner:
        csrf=_composed_login(owner)
        monkeypatch.setattr(private_storage,'_write_private_bytes',lock_after_real_fsync)
        denied,body=_change(world,owner,csrf,revoke=True,key='actual-keystore-fsync-cutoff')
        assert reached and denied.status_code==503,denied.text
        pending=world.memberships.load(world.membership.grant_id)
        assert pending.version==world.membership.version and pending.owner_changes[-1]['phase']=='prepared'
        world.owner_keys.unlock_passphrase(PASSPHRASE)
        assert world.owner_keys.provider().resolve(binding)[0]==old_id
        resumed=owner.post('/api/cases/assignments/'+pending.grant_id+'/change',headers=_headers(csrf),json=body)
        assert resumed.status_code==200 and resumed.json()['revoked'] is True,resumed.text
        assert world.owner_keys.provider().resolve(binding)[0]!=old_id
        assert len(resumed.json()['audit'])==1


def test_other_pending_crypto_operation_cannot_prepare_a_new_member_change(tmp_path,monkeypatch):
    from integrations.private_collaboration import CaseResourceKeyGrantStore
    world=_world(tmp_path)
    world.owner_keys.unlock_passphrase(PASSPHRASE)
    original=CaseResourceKeyGrantStore._seal
    def interrupt(store,grant,**kwargs):
        if store is world.grants and grant.status=='revoked':
            raise OSError('authored independent trusted rotation interruption')
        return original(store,grant,**kwargs)
    monkeypatch.setattr(CaseResourceKeyGrantStore,'_seal',interrupt)
    with pytest.raises(OSError):
        world.grants.revoke_and_rotate(actor_principal_id=world.owner.principal_id,
            recipient_principal_id=world.lawyer.principal_id,case_id=world.case.case_id,
            tenant_id=world.case.tenant_id,resource_id=world.case.resource_id,cutoff=1,
            owner_session=world.owner_keys,idempotency_key='independent-trusted-rotation')
    before=world.memberships.load(world.membership.grant_id)
    assert before.owner_changes==()
    with TestClient(world.review_app,base_url='https://testserver') as owner:
        csrf=_composed_login(owner)
        denied,_=_change(world,owner,csrf,revoke=True,key='fresh-change-during-independent-rotation')
        assert denied.status_code==409,denied.text
        assert world.memberships.load(before.grant_id)==before
