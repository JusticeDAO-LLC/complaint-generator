"""Actual cookie/member/recipient-key review boundaries, authored cases only."""
from copy import deepcopy
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import json
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.case_membership import CaseMembershipStore
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.case_review import live_revisions
from applications.review_ui import attach_static_asset_routes
from applications.site_ui import attach_core_site_ui_routes
from integrations.private_collaboration import CaseResourceKeyGrantStore
from integrations.private_storage import UserOwnedKeySession, PrivateArtifactBinding, seal_private_artifact
from tests.test_cimp_gui_14 import (_composed_case_world, _composed_login, _composed_headers,
    _composed_ciphertext_snapshot, NARRATIVE, PASSPHRASE)
from tests.test_authority_dependency_public_pipeline import _workflow

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
MARKER = "Synthetic private lawyer interpretation about the authored intake."


def _world(tmp_path, *, actual_workspace_as_mediator=False, legal=False, actions=None, share=True):
    from applications.case_review_store import CaseReviewService
    world = _composed_case_world(tmp_path)
    case, service = world.case, world.services[world.case.case_id]
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        started = client.post('/api/complaint-workspace/intake-chat', headers=_composed_headers(case, csrf),
            json={'message': NARRATIVE, 'interview_action': 'start'})
        assert started.status_code == 200
        if legal:
            from applications.case_consent_api import CaseConsentService
            from tests.test_gui29_private_legal_analysis import _reviewed_source, _analysis_request
            from tests.test_gui25_26_private_owner_http import _headers as legal_headers
            world.app.state.case_consent=CaseConsentService(tmp_path/'consent',cases=world.cases,key=os.urandom(32),key_id='consent',clock=lambda:int(time.time()))
            world.service=service
            source=_reviewed_source(client,world,csrf)
            compiled=client.post('/api/legal-analysis/'+case.case_id,headers=legal_headers(world,csrf),
                json=_analysis_request(client,world,source))
            assert compiled.status_code==200,compiled.text
        shared = client.get('/api/complaint-workspace/session', headers=_composed_headers(case)).json()['session']['shared_interview']
    mediator = _workflow(tmp_path / 'real-mediator')
    assert not mediator.workflow_actions.restore_session_projection(deepcopy(shared)).get('error')
    memberships = CaseMembershipStore(tmp_path/'memberships', key=os.urandom(32), key_id='membership',
        principals=world.principals, cases=world.cases)
    invitation = memberships.invite(owner_principal_id=world.owner.principal_id,
        member_principal_id=world.lawyer.principal_id, case_id=case.case_id,
        resource_id=case.resource_id, tenant_id=case.tenant_id, actions=set(actions or {'case.read','case.review'}),
        expected_case_revision=case.revision, expires_at=int(time.time())+3600, idempotency_key='synthetic-review-invite')
    membership = memberships.accept(member_principal_id=world.lawyer.principal_id,
        grant_id=invitation.grant_id, expected_version=invitation.version, idempotency_key='synthetic-review-accept')
    grants = CaseResourceKeyGrantStore(tmp_path/'key-grants', key=os.urandom(32), key_id='key-grant',
        principals=world.principals, cases=world.cases, memberships=memberships)
    owner_keys = UserOwnedKeySession(tmp_path/'workspaces'/case.case_id/'private-keys')
    owner_keys.unlock_passphrase(PASSPHRASE)
    recipient = UserOwnedKeySession(tmp_path/'recipient-keys')
    recipient.create(protection='passphrase', passphrase='synthetic-password')
    reviews = CaseReviewService(tmp_path/'reviews',cases=world.cases,authorizer=world.authorizer,
        memberships=memberships,grants=grants,sessions={world.owner.principal_id:owner_keys,world.lawyer.principal_id:recipient})
    reviews.bind_case(case,service)
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=service if actual_workspace_as_mediator else mediator,
        workspace_service=service, authorize_delegated=reviews.authorize_bound)
    app = FastAPI()
    compose_case_routes(app,authorizer=world.authorizer,browser_sessions=world.sessions,
        case_handlers=handlers,case_reviews=reviews,include_review=False,include_document=False)
    attach_static_asset_routes(app);attach_core_site_ui_routes(app)
    if share:
      with TestClient(app,base_url='https://testserver') as client:
          csrf=_composed_login(client)
          status=client.get('/api/legal-analysis/'+case.case_id+'/lawyer-reviews/sharing',headers=_composed_headers(case))
          assert status.status_code==200,status.text
          shared_response=client.post('/api/legal-analysis/'+case.case_id+'/lawyer-reviews/share',headers=_composed_headers(case,csrf),
              json={'membership_id':membership.grant_id,'expected_membership_version':membership.version,
                  'expected_private_revision':status.json()['private_revision']})
          assert shared_response.status_code==200,shared_response.text
    if share: owner_keys.lock();service.lock_private_keys()
    policy=world.authorizer.grant_assigned_lawyer(owner_principal_id=world.owner.principal_id,
        lawyer_principal_id=world.lawyer.principal_id,case_id=case.case_id,tenant_id=case.tenant_id,
        resource_id=case.resource_id,actions=set(actions or {'case.read','case.review'}),expected_case_revision=case.revision)
    fields={**vars(world),"service":service}
    return SimpleNamespace(**fields, review_app=app, mediator=mediator,
        recipient=recipient, policy=policy, reviews=reviews,memberships=memberships,membership=membership,
        owner_keys=owner_keys,grants=grants)


def _headers(world, csrf=None):
    return {**_composed_headers(world.case, csrf), 'x-expected-membership-revision':str(world.policy.revision)}


def _propose(client, world, csrf):
    view = client.get('/api/legal-analysis/'+world.case.case_id+'/lawyer-reviews',headers=_headers(world)).json()
    live = {**view['live_revisions'],'review_revision':view['review_revision']}
    response = client.post('/api/legal-analysis/'+world.case.case_id+'/lawyer-reviews', headers=_headers(world,csrf),
        json={'operation':'propose','request_id':'synthetic-review-proposal','interpretation':MARKER,
            'governing_legal_authority':True,'admitted_law':True,
            'source_citation':'Authored review candidate; governing applicability unknown.', 'expected_review_revision':live['review_revision'],
            **{'expected_'+name:live[name] for name in ('case_revision','source_revision','fact_revision','proof_revision')}})
    assert response.status_code == 200,response.text
    return response.json()


def test_actual_workspace_composition_reads_review_after_real_recipient_key_grant(tmp_path):
    world = _world(tmp_path,actual_workspace_as_mediator=True)
    with TestClient(world.review_app,base_url='https://testserver') as client:
        _composed_login(client,'synthetic-lawyer-credential')
        response = client.get('/api/legal-analysis/'+world.case.case_id+'/lawyer-reviews',headers=_headers(world))
        assert response.status_code == 200,response.text
        assert response.json()['human_legal_reviews'] == []


def test_review_post_commits_actual_encrypted_owner_revision(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.review_app,base_url='https://testserver') as client:
        csrf = _composed_login(client,'synthetic-lawyer-credential')
        before = (next((tmp_path/'reviews').glob('*/head'))).read_bytes()
        response = _propose(client,world,csrf)
        assert response['record']['interpretation'] == MARKER
        assert (next((tmp_path/'reviews').glob('*/head'))).read_bytes() != before, 'accepted_review_only_mutated_cached_mediator'


def test_actual_recipient_key_lock_during_projection_cannot_publish_cached_review(tmp_path,monkeypatch):
    import applications.case_review as api
    world = _world(tmp_path)
    reached,release = Event(),Event()
    actual = api.project_lawyer_reviews
    with TestClient(world.review_app,base_url='https://testserver') as client:
        csrf = _composed_login(client,'synthetic-lawyer-credential')
        _propose(client,world,csrf)
        def paused(*args,**kwargs):
            result=actual(*args,**kwargs);reached.set()
            assert release.wait(20),'synthetic_projection_barrier_expired'
            return result
        monkeypatch.setattr(api,'project_lawyer_reviews',paused)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(client.get,'/api/legal-analysis/'+world.case.case_id+'/lawyer-reviews',headers=_headers(world))
            try:
                assert reached.wait(20)
                world.recipient.lock()
            finally:release.set()
            response=pending.result(timeout=20)
        assert response.status_code in {401,403,409,503}, 'late_locked_recipient_received_cached_review'
        assert MARKER not in response.text


def test_actual_lawyer_page_embeds_parseable_current_projection(tmp_path,monkeypatch):
    from tests import test_cimp_gui_15 as owner_browser
    from tests import gui_native_browser as browser
    world = _world(tmp_path)
    view = SimpleNamespace(application=world.review_app,case=world.case,principal=world.lawyer,
        service=world.service,actual=world)
    monkeypatch.setattr(owner_browser,'_typed_world',lambda _path:view)
    with owner_browser._page(tmp_path,monkeypatch,'typed_owner') as (_,page):
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error).splitlines()[0][:120]))
        page.evaluate("""async () => {
            const response=await fetch('/api/complaint-workspace/auth/login',{method:'POST',credentials:'same-origin',
                headers:{'content-type':'application/json'},body:JSON.stringify({credential:'synthetic-lawyer-credential'})});
            if(!response.ok)throw new Error('synthetic_lawyer_login_failed');
        }""")
        from urllib.parse import urlencode
        selector={name:value for name,value in (
            ('tenant_id',world.case.tenant_id),('case_id',world.case.case_id),('resource_id',world.case.resource_id),
            ('expected_revision',world.case.revision),('expected_membership_revision',world.policy.revision))}
        response=page.goto(browser.SAME_ORIGIN+'/api/legal-analysis/'+world.case.case_id+'/lawyer-workspace?'+urlencode(selector),wait_until='domcontentloaded')
        assert response.status == 200
        try:
            page.wait_for_function("document.querySelectorAll('#revision-list [data-revision-key]').length===4")
        except Exception:
            raise AssertionError({'javascript_errors':errors,'public_status':page.locator('#lawyer-review-result').inner_text(),
                'reason_codes':page.evaluate('window.reviewErrorCodes'),'auth_observations':page.evaluate('window.reviewAuthObservations')}) from None
        assert page.locator('#lawyer-review-state').text_content()==''
        assert page.locator('#revision-list [data-revision-key]').count() == 4


def test_genuine_reviewed_case_source_can_be_human_approved_without_claiming_proof(tmp_path):
    world=_world(tmp_path,legal=True)
    with TestClient(world.review_app,base_url='https://testserver') as client:
        csrf=_composed_login(client,'synthetic-lawyer-credential')
        proposed=_propose(client,world,csrf)
        path='/api/legal-analysis/'+world.case.case_id+'/lawyer-reviews'
        view=client.get(path,headers=_headers(world)).json()
        assert view['live_revisions']['source_bound'] is True
        live=view['live_revisions']
        response=client.post(path,headers=_headers(world,csrf),json={'operation':'review','request_id':'synthetic-review-approval',
            'proposal_id':proposed['record']['record_id'],'decision':'approved','expected_review_revision':view['review_revision'],
            **{'expected_'+k:live[k] for k in ('case_revision','source_revision','fact_revision','proof_revision')}})
        assert response.status_code==200,response.text
        row=response.json()['record']
        assert row['decision']=='approved' and row['accepted_for_bound_revision'] is True
        assert response.json()['legal_sufficiency'] is False and response.json()['governing_legal_authority'] is False
        assert response.json()['live_revisions']['checked_proof_producer_available'] is False


def test_review_cold_reopen_and_same_request_different_body_are_not_lost_or_replayed(tmp_path):
    from applications.case_review_store import CaseReviewService
    world=_world(tmp_path)
    with TestClient(world.review_app,base_url='https://testserver') as client:
        csrf=_composed_login(client,'synthetic-lawyer-credential')
        proposed=_propose(client,world,csrf)
        recipient=UserOwnedKeySession(tmp_path/'recipient-keys')
        recipient.unlock_passphrase('synthetic-password')
        cold=CaseReviewService(tmp_path/'reviews',cases=world.cases,authorizer=world.authorizer,
            memberships=world.memberships,grants=world.grants,
            sessions={world.owner.principal_id:world.owner_keys,world.lawyer.principal_id:recipient})
        cold.bind_case(world.case,world.service)
        world.review_app.state.case_reviews=cold
        path='/api/legal-analysis/'+world.case.case_id+'/lawyer-reviews'
        read=client.get(path,headers=_headers(world))
        assert read.status_code==200,read.text
        assert read.json()['human_legal_reviews'][0]['interpretation']==MARKER
        view=read.json();live=view['live_revisions']
        response=client.post(path,headers=_headers(world,csrf),json={'operation':'propose','request_id':'synthetic-review-proposal',
            'interpretation':'Different bounded body','source_citation':'Other citation',
            'expected_review_revision':view['review_revision'],
            **{'expected_'+k:live[k] for k in ('case_revision','source_revision','fact_revision','proof_revision')}})
        assert response.status_code==409 and response.json()['error']=='replay_mismatch'
        assert not world.owner_keys.unlocked
        assert all(MARKER.encode() not in path.read_bytes() for path in (tmp_path/'reviews').rglob('*') if path.is_file())
