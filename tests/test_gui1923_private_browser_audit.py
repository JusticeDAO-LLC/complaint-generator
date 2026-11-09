"""Real owner HTTP/Chromium baseline; delayed genuine body delivery only."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
import os

import pytest
from fastapi.testclient import TestClient

from tests.test_cimp_gui_15 import _page
from tests.test_gui16_current_privacy import _bind_actual_owner,_enter
from tests.test_cimp_gui_16 import NARRATIVE
from tests.test_cimp_gui_14 import _composed_case_world,_composed_headers,_composed_login

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


def test_real_graph_get_uses_current_encrypted_owner_and_key_lock_clears_previous_dom(tmp_path,monkeypatch):
    with _page(tmp_path,monkeypatch,'typed_owner') as (world,page):
        _bind_actual_owner(page,world);_enter(page)
        page.evaluate('async()=>{await refreshFactualGraphInspector();}')
        assert NARRATIVE in page.locator('#factual-graph-mount').text_content()
        assert page.get_attribute('#factual-graph-inspector','data-authorized')=='true'
        world.service.lock_private_keys()
        page.evaluate('async()=>{await refreshFactualGraphInspector();}')
        assert NARRATIVE not in page.locator('#factual-graph-mount').text_content()
        assert page.get_attribute('#factual-graph-inspector','data-authorized')=='false'


@pytest.mark.parametrize('boundary',['clear','case','actor'])
def test_actual_graph_response_cannot_repaint_after_real_private_boundary(tmp_path,monkeypatch,boundary):
    """Deterministic client delivery, without concurrent HTTP/WS/SSE claims."""
    with _page(tmp_path,monkeypatch,'typed_owner') as (world,page):
        _bind_actual_owner(page,world);_enter(page)
        page.evaluate("""()=>{
            const original=window.fetch;window.actualGraphReady=false;window.actualGraphSettled=false;
            window.fetch=async(...args)=>{const response=await original(...args);
                if(new URL(String(args[0]),location.href).pathname.endsWith('/factual')){
                    const read=response.json.bind(response);response.json=async()=>{
                        const value=await read();window.actualGraphCase=value.case_id;
                        window.actualGraphReady=true;await new Promise(resolve=>window.releaseActualGraph=resolve);return value;};}
                return response;};
            window.actualGraphRequest=refreshFactualGraphInspector().finally(()=>window.actualGraphSettled=true);
        }""")
        page.wait_for_function('window.actualGraphReady===true')
        assert page.evaluate('window.actualGraphCase')==world.case.case_id
        if boundary=='clear':
            page.click('#workspace-clear-private-state')
            page.wait_for_function("document.body.dataset.workspaceHydrated==='cleared'")
        elif boundary=='case':
            second=world.actual.second
            page.fill('#workspace-switch-user-id',second.tenant_id);page.click('#workspace-switch-user')
            page.wait_for_function("document.body.dataset.workspaceHydrated==='switched'")
            page.evaluate('caseContext=>window.workspaceClient.setCaseContext(caseContext)',{
                'tenant_id':second.tenant_id,'case_id':second.case_id,'resource_id':second.resource_id,'revision':second.revision})
        else:
            page.click('#workspace-logout')
            page.wait_for_function("document.body.dataset.workspaceHydrated==='logged-out'")
            assert page.evaluate("async()=> (await fetch('/api/complaint-workspace/auth/session',{credentials:'same-origin'})).status")==401
            issued=page.evaluate("""async()=>{const r=await fetch('/api/complaint-workspace/auth/login',{
                method:'POST',credentials:'same-origin',headers:{'content-type':'application/json'},
                body:JSON.stringify({credential:'synthetic-stranger-credential'})});
                if(!r.ok)throw new Error('actual_actor_login_failed');return await r.json();}""")
            assert issued['principal_id']==world.actual.stranger.principal_id!=world.principal.principal_id
            foreign=world.actual.foreign
            page.evaluate('data=>{workspaceClient.setBrowserSession(data.issued);workspaceClient.setCaseContext(data.case);}',{
                'issued':issued,'case':{'tenant_id':foreign.tenant_id,'case_id':foreign.case_id,
                    'resource_id':foreign.resource_id,'revision':foreign.revision}})
        page.evaluate('window.releaseActualGraph()');page.wait_for_function('window.actualGraphSettled===true')
        assert NARRATIVE not in page.locator('#factual-graph-mount').text_content(),'old authorized graph repainted after the boundary'
        assert page.get_attribute('#factual-graph-inspector','data-authorized')!='true'


def test_actual_finite_buttons_keep_unresolved_nonproof_outcomes_visible(tmp_path,monkeypatch):
    with _page(tmp_path,monkeypatch,'typed_owner') as (world,page):
        _bind_actual_owner(page,world);_enter(page)
        for button,stop in (('finite-interview-pause','paused'),('finite-interview-cancel','cancelled')):
            page.click('#'+button)
            page.wait_for_function('stop=>document.getElementById("finite-interview-outcome").dataset.stop===stop',arg=stop)
            assert page.get_attribute('#finite-interview-outcome','data-legal-sufficiency')=='false'
            assert page.get_attribute('#finite-interview-outcome','data-worker-stalled')=='false'
            assert page.locator('#finite-interview-reasons li').count()>0
            assert 'not legal sufficiency' in page.locator('#finite-interview-sufficiency').text_content()


def test_actual_sdk_finite_completion_cannot_repaint_after_clear(tmp_path,monkeypatch):
    with _page(tmp_path,monkeypatch,'typed_owner') as (world,page):
        _bind_actual_owner(page,world);_enter(page)
        page.evaluate("""()=>{window.actualFiniteCleared=false;
            window.addEventListener('complaint-mcp-sdk-call',event=>{
                if(!window.actualFiniteCleared && event.detail.tool_name==='complaint.run_intake_chat_turn' && event.detail.status==='success'){
                    window.actualFiniteCleared=true;document.getElementById('workspace-clear-private-state').click();}});
            window.actualFiniteDone=false;window.actualFiniteRequest=controlFiniteInterview('pause').finally(()=>window.actualFiniteDone=true);}""")
        page.wait_for_function('window.actualFiniteDone===true')
        assert page.evaluate('window.actualFiniteCleared') is True
        assert page.get_attribute('body','data-workspace-hydrated')=='cleared'
        assert page.get_attribute('#finite-interview-outcome','data-stop')!='paused'
        assert page.locator('#adaptive-narrative').input_value()==''


def test_finite_stop_cannot_publish_head_after_actual_owner_key_locks(tmp_path,monkeypatch):
    from integrations import private_storage
    world=_composed_case_world(tmp_path);case=world.case;service=world.services[case.case_id]
    with TestClient(world.app,base_url='https://testserver') as owner:
        csrf=_composed_login(owner)
        started=owner.post('/api/complaint-workspace/intake-chat',headers=_composed_headers(case,csrf),
            json={'message':NARRATIVE,'interview_action':'start'})
        assert started.status_code==200
        repository=service.joined_revision_repository(case.tenant_id,case.case_id);head=repository/'head.cgpe';before=head.read_bytes()
        staged,release=Event(),Event();actual=private_storage._fsync_file
        def paused(descriptor,operation):
            actual(descriptor,operation);path=Path(os.readlink('/proc/self/fd/'+str(descriptor)))
            if path.parent==repository and path.read_bytes().startswith(private_storage._HEAD_RECORD_MAGIC):
                staged.set();assert release.wait(20)
        monkeypatch.setattr(private_storage,'_fsync_file',paused)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(owner.post,'/api/complaint-workspace/intake-chat',headers=_composed_headers(case,csrf),
                json={'message':'','interview_action':'pause'})
            try:
                assert staged.wait(20),'actual finite-stop head staging was not reached'
                service.lock_private_keys()
            finally:release.set()
            response=pending.result(timeout=20)
        assert response.status_code in {401,403,409,500,503},{'status':response.status_code}
        assert head.read_bytes()==before,'finite stop published after the key cutoff'


def test_actual_finite_response_cancellation_does_not_claim_the_committed_stop_failed(tmp_path,monkeypatch):
    with _page(tmp_path,monkeypatch,'typed_owner') as (world,page):
        _bind_actual_owner(page,world);_enter(page)
        page.evaluate("""()=>{
            const actual=workspaceClient.fetchImpl;window.actualFiniteServerPaused=false;let cancel=true;
            workspaceClient.fetchImpl=async(...args)=>{const response=await actual(...args);
                if(cancel && new URL(String(args[0]),location.href).pathname.endsWith('/mcp/rpc')){
                    cancel=false;const data=await response.clone().json();
                    window.actualFiniteServerPaused=JSON.stringify(data).includes('"stop":"paused"');
                    await response.body.cancel();}
                return response;};
            window.actualFiniteDone=false;window.actualFiniteRequest=controlFiniteInterview('pause').finally(()=>window.actualFiniteDone=true);
        }""")
        page.wait_for_function('window.actualFiniteDone===true')
        assert page.evaluate('window.actualFiniteServerPaused') is True
        paused=page.evaluate("""async caseId=>{const current=await workspaceClient.getSession(caseId);
            return current.session.intentional_user_wait.paused;}""",world.case.tenant_id)
        assert paused is True
        assert 'interview did not stop' not in page.locator('#workspace-status').text_content().lower()
