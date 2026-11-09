"""Real cookie actor changes are checked independently of local SDK state."""
import pytest
from tests.test_cimp_gui_15 import _page
from tests.test_gui16_current_privacy import _bind_actual_owner,_enter
from tests.test_cimp_gui_16 import NARRATIVE

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


def test_actual_other_account_cookie_cannot_admit_old_actor_graph(tmp_path,monkeypatch):
    with _page(tmp_path,monkeypatch,'typed_owner') as (world,page):
        _bind_actual_owner(page,world);_enter(page)
        page.evaluate("""()=>{
            const original=fetch;window.cookieGraphReady=false;window.cookieGraphDone=false;
            window.fetch=async(...args)=>{const response=await original(...args);
                if(new URL(String(args[0]),location.href).pathname.endsWith('/factual')){
                    const read=response.json.bind(response);response.json=async()=>{const value=await read();
                        window.cookieGraphReady=true;await new Promise(resolve=>window.releaseCookieGraph=resolve);return value;};}
                return response;};
            window.cookieGraphRequest=refreshFactualGraphInspector().finally(()=>window.cookieGraphDone=true);
        }""")
        page.wait_for_function('window.cookieGraphReady===true')
        actor=page.evaluate("""async()=>{
            const response=await fetch('/api/complaint-workspace/auth/login',{method:'POST',credentials:'same-origin',
                headers:{'content-type':'application/json'},body:JSON.stringify({credential:'synthetic-stranger-credential'})});
            if(!response.ok)throw new Error('actual_account_change_failed');
            return (await response.json()).principal_id;
        }""")
        assert actor==world.actual.stranger.principal_id!=world.principal.principal_id
        assert page.evaluate('workspaceClient.activePrincipalId')==world.principal.principal_id
        page.evaluate('window.releaseCookieGraph()');page.wait_for_function('window.cookieGraphDone===true')
        assert NARRATIVE not in page.locator('#factual-graph-mount').text_content()
        assert page.get_attribute('#factual-graph-inspector','data-authorized')!='true'
