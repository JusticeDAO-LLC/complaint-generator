"""Real revocation, browser-session, owner sharing and encrypted review CAS."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path
import os
import time

import pytest
from fastapi.testclient import TestClient

from tests.test_gui32_private_review_http import _world,_headers,_propose,MARKER
from tests.test_cimp_gui_14 import _composed_login,_composed_headers,PASSPHRASE

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


def _path(world):return '/api/legal-analysis/'+world.case.case_id+'/lawyer-reviews'


def _body(view,request_id,**fields):
    live=view['live_revisions']
    return {'request_id':request_id,'expected_review_revision':view['review_revision'],
        **{'expected_'+k:live[k] for k in ('case_revision','source_revision','fact_revision','proof_revision')},**fields}


@pytest.mark.parametrize('boundary',['logout','rotate','membership'])
def test_current_recipient_read_drops_after_real_late_access_boundary(tmp_path,monkeypatch,boundary):
    import applications.case_review as api
    world=_world(tmp_path)
    reached,release=Event(),Event()
    actual=api.project_lawyer_reviews
    with TestClient(world.review_app,base_url='https://testserver') as client, TestClient(world.review_app,base_url='https://testserver') as other:
        csrf=_composed_login(client,'synthetic-lawyer-credential');_propose(client,world,csrf)
        other.cookies.update(client.cookies)
        def paused(*args,**kwargs):
            value=actual(*args,**kwargs);reached.set();assert release.wait(20);return value
        monkeypatch.setattr(api,'project_lawyer_reviews',paused)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(client.get,_path(world),headers=_headers(world))
            try:
                assert reached.wait(20)
                if boundary=='membership':
                    world.memberships.remove(owner_principal_id=world.owner.principal_id,
                        grant_id=world.membership.grant_id,expected_version=world.membership.version)
                else:
                    response=other.post('/api/complaint-workspace/auth/'+boundary,headers={'x-csrf-token':csrf})
                    assert response.status_code==200
            finally:release.set()
            response=pending.result(timeout=20)
        assert response.status_code in {401,403,409,503} and MARKER not in response.text


@pytest.mark.parametrize('stage',['source_crypto','grant_crypto'])
def test_owner_logout_during_real_share_crypto_cannot_issue_after_cutoff(tmp_path,monkeypatch,stage):
    import applications.case_review_store as owner
    import integrations.private_collaboration as grants
    world=_world(tmp_path,share=False)
    target=owner if stage=='source_crypto' else grants
    actual=target.seal_private_artifact
    reached,release=Event(),Event()
    kind='case-review-source' if stage=='source_crypto' else 'case-resource-key-grant'
    def paused(*args,**kwargs):
        value=actual(*args,**kwargs)
        if kwargs['binding'].artifact_kind==kind:
            reached.set();assert release.wait(20)
        return value
    monkeypatch.setattr(target,'seal_private_artifact',paused)
    with TestClient(world.review_app,base_url='https://testserver') as client,TestClient(world.review_app,base_url='https://testserver') as other:
        csrf=_composed_login(client);other.cookies.update(client.cookies)
        view=client.get(_path(world)+'/sharing',headers=_composed_headers(world.case)).json()
        body={'membership_id':world.membership.grant_id,'expected_membership_version':world.membership.version,
            'expected_private_revision':view['private_revision']}
        before={str(p.relative_to(tmp_path/'reviews')):p.read_bytes() for p in (tmp_path/'reviews').rglob('*') if p.is_file()}
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(client.post,_path(world)+'/share',headers=_composed_headers(world.case,csrf),json=body)
            try:
                assert reached.wait(20)
                assert other.post('/api/complaint-workspace/auth/logout',headers={'x-csrf-token':csrf}).status_code==200
            finally:release.set()
            response=pending.result(timeout=20)
        assert response.status_code in {401,403,503}
        after={str(p.relative_to(tmp_path/'reviews')):p.read_bytes() for p in (tmp_path/'reviews').rglob('*') if p.is_file()}
        assert after==before
        assert list((tmp_path/'key-grants/grants').glob('*.envelope'))==[]


def test_actual_shared_source_drift_requires_owner_reshare_and_old_approval_stays_stale(tmp_path):
    world=_world(tmp_path,legal=True)
    with TestClient(world.review_app,base_url='https://testserver') as recipient,TestClient(world.review_app,base_url='https://testserver') as owner:
        csrf=_composed_login(recipient,'synthetic-lawyer-credential')
        proposed=_propose(recipient,world,csrf)
        view=recipient.get(_path(world),headers=_headers(world)).json()
        approved=recipient.post(_path(world),headers=_headers(world,csrf),json=_body(view,'synthetic-approval',
            operation='review',proposal_id=proposed['record']['record_id'],decision='approved'))
        assert approved.status_code==200
        old_approval=approved.json()['record']['record_id']
        world.service.unlock_private_keys(passphrase=PASSPHRASE)
        world.owner_keys.unlock_passphrase(PASSPHRASE)
        owner_csrf=_composed_login(owner)
        context=owner.get('/api/legal-context/'+world.case.case_id,headers=_composed_headers(world.case)).json()
        changed=owner.post('/api/legal-context/'+world.case.case_id,headers=_composed_headers(world.case,owner_csrf),
            json={'expected_context_revision':context['context_revision'],'forum':'New authored review forum'})
        assert changed.status_code==200
        stale=recipient.get(_path(world),headers=_headers(world))
        assert stale.status_code==409 and stale.json()['error']=='review_source_changed'
        current=owner.get(_path(world)+'/sharing',headers=_composed_headers(world.case)).json()
        shared=owner.post(_path(world)+'/share',headers=_composed_headers(world.case,owner_csrf),json={
            'membership_id':world.membership.grant_id,'expected_membership_version':world.membership.version,
            'expected_private_revision':current['private_revision']})
        assert shared.status_code==200,shared.text
        world.owner_keys.lock();world.service.lock_private_keys()
        view=recipient.get(_path(world),headers=_headers(world)).json()
        assert all(row['stale'] for row in view['human_legal_reviews'])
        head=next((tmp_path/'reviews').glob('*/head'));before=head.read_bytes()
        refused=recipient.post(_path(world),headers=_headers(world,csrf),json=_body(view,'synthetic-stale-promote',
            operation='promote',approval_id=old_approval))
        assert refused.status_code in {409,503} and head.read_bytes()==before
        assert view['current_promotion'] is None


def test_actual_concurrent_review_cas_keeps_exactly_one_append(tmp_path):
    world=_world(tmp_path)
    with TestClient(world.review_app,base_url='https://testserver') as client:
        csrf=_composed_login(client,'synthetic-lawyer-credential')
        view=client.get(_path(world),headers=_headers(world)).json()
        def post(index):
            return client.post(_path(world),headers=_headers(world,csrf),json=_body(view,'synthetic-cas-'+str(index),
                operation='propose',interpretation='Authored concurrent proposal '+str(index),source_citation='Candidate only'))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(post,[0,1]))
        assert sorted(r.status_code for r in results)==[200,409]
        current=client.get(_path(world),headers=_headers(world)).json()
        assert current['review_revision']==1 and len(current['human_legal_reviews'])==1


def test_readonly_recipient_and_wrong_actor_cannot_write_or_cross_case(tmp_path):
    world=_world(tmp_path,actions={'case.read'})
    with TestClient(world.review_app,base_url='https://testserver') as client:
        csrf=_composed_login(client,'synthetic-lawyer-credential')
        view=client.get(_path(world),headers=_headers(world))
        assert view.status_code==200
        response=client.post(_path(world),headers=_headers(world,csrf),json=_body(view.json(),'synthetic-readonly',
            operation='propose',interpretation='Not permitted',source_citation='Candidate only'))
        assert response.status_code==403
        assert client.get('/api/legal-analysis/'+world.second.case_id+'/lawyer-reviews',headers=_headers(world)).status_code==403
        _composed_login(client,'synthetic-stranger-credential')
        assert client.get(_path(world),headers=_headers(world)).status_code==403


def test_real_fifo_source_refuses_without_blocking_or_plaintext(tmp_path):
    world=_world(tmp_path)
    source=next((tmp_path/'reviews').glob('*/source'));source.unlink();os.mkfifo(source,0o600)
    with TestClient(world.review_app,base_url='https://testserver') as client:
        _composed_login(client,'synthetic-lawyer-credential')
        start=time.monotonic();response=client.get(_path(world),headers=_headers(world))
        assert time.monotonic()-start<3
        assert response.status_code in {403,503} and not response.json().get('human_legal_reviews')


def test_actual_canonical_writer_waits_for_review_source_hold_then_invalidates_share(tmp_path,monkeypatch):
    import applications.case_review_store as review
    import integrations.private_storage as storage
    world=_world(tmp_path)
    world.owner_keys.unlock_passphrase(PASSPHRASE);world.service.unlock_private_keys(passphrase=PASSPHRASE)
    staged,release,writer_waiting=Event(),Event(),Event()
    actual_atomic,actual_lock=review._atomic,storage._process_lock
    def paused(path,*args,**kwargs):
        if path.name=='head':staged.set();assert release.wait(20)
        return actual_atomic(path,*args,**kwargs)
    class ObservedLock:
        def __init__(self,lock):self.lock=lock
        def acquire(self,*args,**kwargs):
            if staged.is_set() and not release.is_set():writer_waiting.set()
            return self.lock.acquire(*args,**kwargs)
        def release(self):return self.lock.release()
    monkeypatch.setattr(review,'_atomic',paused)
    monkeypatch.setattr(storage,'_process_lock',lambda root:ObservedLock(actual_lock(root)))
    with TestClient(world.review_app,base_url='https://testserver') as client,TestClient(world.review_app,base_url='https://testserver') as owner:
        csrf=_composed_login(client,'synthetic-lawyer-credential');owner_csrf=_composed_login(owner)
        view=client.get(_path(world),headers=_headers(world)).json()
        context=owner.get('/api/legal-context/'+world.case.case_id,headers=_composed_headers(world.case)).json()
        def update():
            return owner.post('/api/legal-context/'+world.case.case_id,headers=_composed_headers(world.case,owner_csrf),
                json={'expected_context_revision':context['context_revision'],'forum':'Concurrent canonical forum'})
        with ThreadPoolExecutor(max_workers=2) as pool:
            review_result=pool.submit(client.post,_path(world),headers=_headers(world,csrf),json=_body(view,'synthetic-serialized-review',
                operation='propose',interpretation=MARKER,source_citation='Authored candidate only'))
            try:
                assert staged.wait(20)
                changed=pool.submit(update)
                assert writer_waiting.wait(20) and not changed.done()
            finally:release.set()
            assert review_result.result(timeout=20).status_code==200
            response=changed.result(timeout=20)
            assert response.status_code==200,response.text
        world.owner_keys.lock();world.service.lock_private_keys()
        stale=client.get(_path(world),headers=_headers(world))
        assert stale.status_code==409 and stale.json()['error']=='review_source_changed'


@pytest.mark.parametrize('boundary',['logout','key','membership','grant_cutoff'])
def test_real_review_head_publication_rechecks_late_recipient_boundary(tmp_path,monkeypatch,boundary):
    import applications.case_review_store as review
    world=_world(tmp_path);staged,release=Event(),Event();actual_atomic=review._atomic
    head=next((tmp_path/'reviews').glob('*/head'));before=head.read_bytes()
    def paused(path,data,late):
        def immediately_before_replace():
            staged.set();assert release.wait(20);return late()
        return actual_atomic(path,data,immediately_before_replace if path==head else late)
    monkeypatch.setattr(review,'_atomic',paused)
    with TestClient(world.review_app,base_url='https://testserver') as client,TestClient(world.review_app,base_url='https://testserver') as other:
        csrf=_composed_login(client,'synthetic-lawyer-credential');other.cookies.update(client.cookies)
        view=client.get(_path(world),headers=_headers(world)).json()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(client.post,_path(world),headers=_headers(world,csrf),json=_body(view,'synthetic-late-refused',
                operation='propose',interpretation=MARKER,source_citation='Authored review only'))
            try:
                assert staged.wait(20)
                if boundary=='logout':assert other.post('/api/complaint-workspace/auth/logout',headers={'x-csrf-token':csrf}).status_code==200
                elif boundary=='key':world.recipient.lock()
                elif boundary=='membership':world.memberships.remove(owner_principal_id=world.owner.principal_id,
                    grant_id=world.membership.grant_id,expected_version=world.membership.version)
                else:
                    # This independent owner revocation uses its own unlocked
                    # handle; the pending lawyer request still uses only its
                    # recipient handle and cannot borrow it.
                    world.owner_keys.unlock_passphrase(PASSPHRASE)
                    result=world.grants.revoke_and_rotate(actor_principal_id=world.owner.principal_id,
                        recipient_principal_id=world.lawyer.principal_id,case_id=world.case.case_id,
                        tenant_id=world.case.tenant_id,resource_id=world.case.resource_id,cutoff=1,
                        owner_session=world.owner_keys,recipient_sessions={},idempotency_key='synthetic-review-cutoff')
                    assert result['future_access_revoked'] is True
                    world.owner_keys.lock()
            finally:release.set()
            response=pending.result(timeout=20)
        assert response.status_code in {401,403,409,503},response.text
        assert head.read_bytes()==before and MARKER not in response.text
        assert list(head.parent.glob('.*.tmp'))==[]


@pytest.mark.parametrize('boundary',['logout','key'])
def test_committed_review_response_drops_private_plaintext_after_late_projection_boundary(tmp_path,monkeypatch,boundary):
    import applications.case_review as review
    world=_world(tmp_path);head=next((tmp_path/'reviews').glob('*/head'));before=head.read_bytes()
    projected,release=Event(),Event();actual=review.project_lawyer_reviews
    def paused(*args,**kwargs):
        result=actual(*args,**kwargs)
        if head.read_bytes()!=before:
            projected.set();assert release.wait(20)
        return result
    monkeypatch.setattr(review,'project_lawyer_reviews',paused)
    with TestClient(world.review_app,base_url='https://testserver') as client,TestClient(world.review_app,base_url='https://testserver') as other:
        csrf=_composed_login(client,'synthetic-lawyer-credential');other.cookies.update(client.cookies)
        view=client.get(_path(world),headers=_headers(world)).json()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(client.post,_path(world),headers=_headers(world,csrf),json=_body(view,'synthetic-committed-before-cutoff',
                operation='propose',interpretation=MARKER,source_citation='Authored candidate'))
            try:
                assert projected.wait(20)
                committed=head.read_bytes();assert committed!=before
                if boundary=='logout':assert other.post('/api/complaint-workspace/auth/logout',headers={'x-csrf-token':csrf}).status_code==200
                else:world.recipient.lock()
            finally:release.set()
            response=pending.result(timeout=20)
        assert response.status_code in {401,403,409,503} and MARKER not in response.text
        assert head.read_bytes()==committed,'a valid earlier commit must not be falsely rolled back'


def test_fresh_authenticated_exact_lost_response_replay_is_readonly_and_does_not_append(tmp_path):
    world=_world(tmp_path);head=next((tmp_path/'reviews').glob('*/head'))
    with TestClient(world.review_app,base_url='https://testserver') as client:
        csrf=_composed_login(client,'synthetic-lawyer-credential')
        view=client.get(_path(world),headers=_headers(world)).json()
        body=_body(view,'synthetic-exact-lost-reply',operation='propose',interpretation=MARKER,source_citation='Authored candidate')
        first=client.post(_path(world),headers=_headers(world,csrf),json=body)
        assert first.status_code==200,first.text
        before=head.read_bytes()
        assert client.post('/api/complaint-workspace/auth/logout',headers={'x-csrf-token':csrf}).status_code==200
        csrf=_composed_login(client,'synthetic-lawyer-credential')
        replay=client.post(_path(world),headers=_headers(world,csrf),json=body)
        assert replay.status_code==200,replay.text
        assert replay.json()['replayed'] is True and replay.json()['read_only'] is True
        assert replay.json()['record']['record_id']==first.json()['record']['record_id']
        assert head.read_bytes()==before
