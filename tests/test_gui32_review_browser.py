"""Actual owner share and recipient browser writes; no canned API/DOM."""
from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from tests import test_cimp_gui_15 as browser_owner
from tests import gui_native_browser as browser
from tests.test_gui32_private_review_http import _world,MARKER

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


@contextmanager
def _page(tmp_path,monkeypatch,*,share=True):
    world=_world(tmp_path,share=share)
    view=SimpleNamespace(application=world.review_app,case=world.case,principal=world.lawyer,
        service=world.service,actual=world)
    monkeypatch.setattr(browser_owner,'_typed_world',lambda _path:view)
    with browser_owner._page(tmp_path,monkeypatch,'typed_owner') as (_,page):
        yield world,page


def _url(world,owner=False):
    return browser.SAME_ORIGIN+'/api/legal-analysis/'+world.case.case_id+'/lawyer-workspace?'+urlencode({
        'tenant_id':world.case.tenant_id,'case_id':world.case.case_id,'resource_id':world.case.resource_id,
        'expected_revision':world.case.revision,'expected_membership_revision':0 if owner else world.policy.revision})


def _cookie_login(page,credential):
    result=page.evaluate("""async credential => { const response=await fetch('/api/complaint-workspace/auth/login',{
        method:'POST',credentials:'same-origin',headers:{'content-type':'application/json'},
        body:JSON.stringify({credential})});return {status:response.status,issued:await response.json()};}""",credential)
    assert result['status']==200
    return result['issued']


def _authorize(page,credential):
    page.fill('#review-credential',credential)
    with page.expect_response(lambda r:r.url.endswith('/auth/login') and r.request.method=='POST') as seen:
        page.click('#review-login button')
    assert seen.value.status==200
    page.wait_for_function("document.querySelectorAll('#revision-list [data-revision-key]').length===4")
    assert page.locator('#review-credential').input_value()==''


def _propose(page):
    page.fill('[name=request_id]','synthetic-browser-review')
    page.fill('[name=interpretation]',MARKER)
    page.fill('[name=source_citation]','Authored review candidate; governing applicability unknown.')
    with page.expect_response(lambda r:r.url.endswith('/lawyer-reviews') and r.request.method=='POST') as seen:
        page.click('#lawyer-review-form button')
    assert seen.value.status==200
    page.wait_for_function("document.querySelectorAll('#human-review-rows tr').length===1")
    assert MARKER in page.locator('#human-review-rows').inner_text()


def test_real_owner_shares_in_gui_then_locked_owner_recipient_submits_and_logs_out(tmp_path,monkeypatch):
    with _page(tmp_path,monkeypatch,share=False) as (world,page):
        issued=_cookie_login(page,'synthetic-owner-credential')
        page.evaluate("""data=>{window.workspaceClient.setBrowserSession(data.issued);
            window.workspaceClient.setCaseContext(data.case);}""",{'issued':issued,'case':{
                'tenant_id':world.case.tenant_id,'case_id':world.case.case_id,
                'resource_id':world.case.resource_id,'revision':world.case.revision}})
        with page.expect_navigation(wait_until='domcontentloaded') as opened:
            page.click('#open-owner-review-sharing')
        assert opened.value.status==200 and 'expected_revision=1' in page.url
        _authorize(page,'synthetic-owner-credential')
        assert page.locator('#review-owner-sharing').is_visible()
        page.fill('#review-membership',world.membership.grant_id)
        page.fill('#review-membership-version',str(world.membership.version))
        with page.expect_response(lambda r:r.url.endswith('/lawyer-reviews/share') and r.request.method=='POST') as seen:
            page.click('#review-share-form button')
        assert seen.value.status==200
        page.wait_for_selector('#review-share-result a')
        link=page.locator('#review-share-result a').get_attribute('href')
        assert link.startswith('/api/legal-analysis/') and 'expected_membership_revision=' in link
        world.owner_keys.lock();world.service.lock_private_keys()
        # The actual page login boundary clears its private state on account
        # change. Reopen the server-issued case link under the new real cookie.
        page.fill('#review-credential','synthetic-lawyer-credential')
        page.click('#review-login button')
        page.wait_for_function("document.getElementById('lawyer-review-result').textContent.includes('does not match the current account')")
        assert page.locator('#revision-list').inner_text()==''
        assert page.goto(browser.SAME_ORIGIN+link).status==200
        _authorize(page,'synthetic-lawyer-credential')
        assert page.locator('#review-owner-sharing').is_hidden()
        _propose(page)
        assert world.owner_keys.unlocked is False
        page.click('#review-logout')
        page.wait_for_function("document.getElementById('lawyer-review-result').textContent.includes('logged out')")
        assert page.locator('#human-review-rows').inner_text()==''
        assert MARKER not in page.locator('body').inner_text()
        assert page.evaluate("async () => (await fetch('/api/complaint-workspace/auth/session',{credentials:'same-origin'})).status")==401


def test_real_delivered_review_response_cannot_repaint_after_actual_clear(tmp_path,monkeypatch):
    """Deterministic client-delivery race; no concurrent network claim."""
    with _page(tmp_path,monkeypatch) as (world,page):
        _cookie_login(page,'synthetic-lawyer-credential')
        page.add_init_script("""(() => {
            const add=EventTarget.prototype.addEventListener;
            EventTarget.prototype.addEventListener=function(kind,handler,...options){
                if(this.id==='review-refresh' && kind==='click')return add.call(this,kind,async function(event){
                    try{return await handler.call(this,event);}finally{window.actualReviewRefreshSettled=true;}},...options);
                return add.call(this,kind,handler,...options);
            };
        })();""")
        page.goto(_url(world));_authorize(page,'synthetic-lawyer-credential');_propose(page)
        page.evaluate("""() => {
            const actual=fetch;window.actualReviewRefreshSettled=false;window.reviewPayloadReady=false;
            window.fetch=async (...args)=>{const response=await actual(...args);
                if(String(args[0]).endsWith('/lawyer-reviews') && args[1].method==='GET'){
                    const read=response.json.bind(response);response.json=async()=>{const data=await read();
                        window.reviewPayloadReady=true;await new Promise(resolve=>window.releaseActualReviewPayload=resolve);return data;};}
                return response;};
        }""")
        page.click('#review-refresh')
        page.wait_for_function('window.reviewPayloadReady===true')
        page.click('#review-clear')
        page.evaluate('window.releaseActualReviewPayload()')
        page.wait_for_function('window.actualReviewRefreshSettled===true')
        assert page.locator('#human-review-rows').inner_text()==''
        assert MARKER not in page.locator('body').inner_text()
        assert page.locator('[name=interpretation]').input_value()==''
