"""Committed canonical acceptance remains durable; response access is current."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from fastapi.testclient import TestClient

from applications.complaint_workspace import ComplaintWorkspaceRequestHandlers,ComplaintWorkspaceService
from complaint_phases.knowledge_graph import KnowledgeGraph
from tests.test_gui47_private_acceptance import _world,_accept,_head,_state
from tests.test_cimp_gui_14 import _composed_login,_composed_headers,PASSPHRASE
from tests.test_gui32_private_review_http import _headers as _lawyer_headers

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


@pytest.mark.parametrize('boundary',['workspace_key','review_owner_key','logout'])
def test_legitimate_committed_owner_acceptance_refuses_late_private_response_and_replays(tmp_path,monkeypatch,boundary):
    world,offer,request=_world(tmp_path)
    before=_head(world).read_bytes();completed,release=Event(),Event()
    actual=ComplaintWorkspaceRequestHandlers.apply_terminal_graph_edit
    def paused(self,*args,**kwargs):
        result=actual(self,*args,**kwargs)
        if self.workspace is world.service and result.get('review_acceptance'):
            assert result['status']=='applied' and _head(world).read_bytes()!=before
            completed.set();assert release.wait(20)
        return result
    monkeypatch.setattr(ComplaintWorkspaceRequestHandlers,'apply_terminal_graph_edit',paused)
    with TestClient(world.review_app,base_url='https://testserver') as owner,TestClient(world.review_app,base_url='https://testserver') as other:
        csrf=_composed_login(owner);other.cookies.update(owner.cookies)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(_accept,owner,world,csrf,request)
            try:
                assert completed.wait(20),'real canonical acceptance did not commit'
                committed=_head(world).read_bytes();assert committed!=before
                if boundary=='workspace_key':world.service.lock_private_keys()
                elif boundary=='review_owner_key':world.owner_keys.lock()
                else:assert other.post('/api/complaint-workspace/auth/logout',headers={'x-csrf-token':csrf}).status_code==200
            finally:release.set()
            response=pending.result(timeout=20)
        assert response.status_code in {401,403,409,503},{'status':response.status_code}
        assert 'actual_factual_correction' not in response.json()
        assert request['proposal_id'] not in response.text
        assert _head(world).read_bytes()==committed,'a valid pre-cutoff commit must remain committed'
        if boundary=='workspace_key':world.service.unlock_private_keys(passphrase=PASSPHRASE)
        if boundary=='review_owner_key':world.owner_keys.unlock_passphrase(PASSPHRASE)
        csrf=_composed_login(owner)
        state=_state(owner,world)
        stored=state['canonical_review_acceptances'][request['request_id']]
        graph=KnowledgeGraph.from_dict(state['shared_interview']['knowledge_graph'])
        assert graph.assertion_state(offer['target_stable_id'])['status']=='superseded'
        assert graph.assertion_state(stored['replacement_stable_id'])['status']=='active'
        assert state['private_revision']==stored['result_private_revision']
        replay=_accept(owner,world,csrf,request)
        assert replay.status_code==200,replay.text
        assert replay.json()['applied'] is False and replay.json()['historically_applied'] is True
        assert replay.json()['replayed'] is True and replay.json()['receipt_sha256']==stored['receipt_sha256']
        assert _head(world).read_bytes()==committed


@pytest.mark.parametrize('boundary',['workspace_key','review_owner_key'])
def test_acceptance_delivery_rechecks_keys_after_actual_current_material_decryption(tmp_path,monkeypatch,boundary):
    world,_offer,request=_world(tmp_path);before=_head(world).read_bytes()
    decrypted,release=Event(),Event();actual=ComplaintWorkspaceService._load_state
    def paused(self,*args,**kwargs):
        value=actual(self,*args,**kwargs)
        if self is world.service and request['request_id'] in (value.get('canonical_review_acceptances') or {}):
            decrypted.set();assert release.wait(20)
        return value
    monkeypatch.setattr(ComplaintWorkspaceService,'_load_state',paused)
    with TestClient(world.review_app,base_url='https://testserver') as owner:
        csrf=_composed_login(owner)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(_accept,owner,world,csrf,request)
            try:
                assert decrypted.wait(20),'actual committed material was not reopened'
                committed=_head(world).read_bytes();assert committed!=before
                if boundary=='workspace_key':world.service.lock_private_keys()
                else:world.owner_keys.lock()
            finally:release.set()
            response=pending.result(timeout=20)
        assert response.status_code in {401,403,409,503},{'status':response.status_code}
        assert 'actual_factual_correction' not in response.json()
        assert _head(world).read_bytes()==committed


def test_review_cas_advance_after_canonical_commit_refuses_delivery_without_rolling_back(tmp_path,monkeypatch):
    world,_offer,request=_world(tmp_path);before=_head(world).read_bytes()
    completed,release=Event(),Event();actual=ComplaintWorkspaceRequestHandlers.apply_terminal_graph_edit
    def paused(self,*args,**kwargs):
        result=actual(self,*args,**kwargs)
        if self.workspace is world.service and result.get('review_acceptance'):
            completed.set();assert release.wait(20)
        return result
    monkeypatch.setattr(ComplaintWorkspaceRequestHandlers,'apply_terminal_graph_edit',paused)
    prefix='/api/legal-analysis/'+world.case.case_id
    with TestClient(world.review_app,base_url='https://testserver') as owner,TestClient(world.review_app,base_url='https://testserver') as sharer,TestClient(world.review_app,base_url='https://testserver') as lawyer:
        csrf=_composed_login(owner);sharer.cookies.update(owner.cookies)
        lawyer_csrf=_composed_login(lawyer,'synthetic-lawyer-credential')
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(_accept,owner,world,csrf,request)
            try:
                assert completed.wait(20)
                committed=_head(world).read_bytes();assert committed!=before
                current=sharer.get(prefix+'/lawyer-reviews/sharing',headers=_composed_headers(world.case))
                assert current.status_code==200
                shared=sharer.post(prefix+'/lawyer-reviews/share',headers=_composed_headers(world.case,csrf),json={
                    'membership_id':world.membership.grant_id,'expected_membership_version':world.membership.version,
                    'expected_private_revision':current.json()['private_revision']})
                assert shared.status_code==200,{'status':shared.status_code}
                view=lawyer.get(prefix+'/review-items',headers=_lawyer_headers(world)).json();live=view['live_revisions']
                dissent=lawyer.post(prefix+'/review-items',headers=_lawyer_headers(world,lawyer_csrf),json={
                    'operation':'dissent','request_id':'synthetic-after-commit-dissent','body':'Preserve this later attributed disagreement.',
                    'proposal_id':request['proposal_id'],'expected_review_revision':view['review_revision'],
                    **{'expected_'+name:live[name] for name in ('case_revision','source_revision','fact_revision','proof_revision')}})
                assert dissent.status_code==200,{'status':dissent.status_code}
                assert dissent.json()['review_revision']==request['expected_review_revision']+1
            finally:release.set()
            response=pending.result(timeout=20)
        assert response.status_code==409 and response.json()['error']=='stale_revision'
        assert 'actual_factual_correction' not in response.json() and _head(world).read_bytes()==committed
