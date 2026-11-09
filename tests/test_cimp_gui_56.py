"""Owner and lawyer DOM journey through the real application handlers.

Narrative, question, why, correction, graph research, invitation, message,
review, and cold resume run in Chromium. Same-origin HTTP is piped into the
composed ASGI app. Persistence is the encrypted workspace. Source rows are
synthetic. A canned mockApi packet is not the backend.

Known limits: WebSocket and SSE stay unsupported. Interview pause is an
unresolved stop, not legal sufficiency. A missing proof engine stays
conditional. Source custody is not governing-law eligibility. Unknown Data candidates stay
non-governing; an applicable raw source rule must pass the genuine SourceOwner.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from complaint_phases.knowledge_graph import KnowledgeGraph
from urllib.parse import quote

import pytest

from applications.case_routes import MESSAGE_INBOX_PATH
from applications.lawyer_workspace_api import LAWYER_WORKSPACE_API
from integrations.private_storage import ENVELOPE_MAGIC
from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import NARRATIVE

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ANSWER = "Alex Rivera fired me on March 4, 2024 after I reported a safety concern."
REPLACEMENT = "Alex Rivera fired me on March 5, 2024 after I reported a safety concern."
MESSAGE = "Synthetic owner note for the assigned lawyer."
QUERY = "termination statute"


@contextmanager
def _browsers(tmp_path, monkeypatch, app):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("Task 02 network fence is not active")
    bridge = browser.SameOriginAsgiBridge(app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = tmp_path / "journey-profiles"
    root.mkdir(mode=0o700)
    playwright = None
    contexts = []
    observed = set()

    def open_page(name):
        profile = root / name
        profile.mkdir(mode=0o700)
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        contexts.append(context)
        browser._assert_process_custody(node, chromium, profile)
        observed.update(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(20000)
        return page

    try:
        playwright = browser._load_sync_playwright()().start()
        yield open_page, bridge
    finally:
        for context in contexts:
            context.close()
        if playwright is not None:
            playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(root), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"


def _case_payload(world):
    case = world.journey_case
    return {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "revision": case.revision,
        "expected_revision": case.revision,
    }


def _arm(page, world, credential, *, bootstrap=True):
    page.goto(browser.SAME_ORIGIN + "/workspace?user_id=" + quote(world.journey_case.tenant_id), wait_until="domcontentloaded")
    page.wait_for_function("['ready','partial','denied','error'].includes(document.body.dataset.workspaceHydrated)")
    issued = page.evaluate(
        """async credential => {
            const response = await fetch('/api/complaint-workspace/auth/login', {
                method: 'POST', credentials: 'same-origin', headers: {'content-type': 'application/json'},
                body: JSON.stringify({credential})});
            if (!response.ok) throw new Error('login_' + response.status);
            return await response.json();
        }""", credential)
    assert issued["authenticated"] is True
    expected = {"synthetic-owner-credential":world.owner.principal_id,
        "synthetic-lawyer-credential":world.lawyer.principal_id,
        "synthetic-stranger-credential":world.stranger.principal_id}[credential]
    assert issued["principal_id"] == expected
    page.evaluate("""async data => {
        window.workspaceClient.setBrowserSession(data.issued);
        window.workspaceClient.setCaseContext(data.case);
        if (data.bootstrap) await window.workspaceClient.bootstrapWorkspace(data.case.tenant_id);
    }""", {"issued": issued, "case": _case_payload(world), "bootstrap": bootstrap})
    assert page.evaluate("() => typeof window.mockApi") == "undefined"
    return issued


def _sealed_narrative_absent(world, narrative=NARRATIVE):
    files = [path for path in world.service._session_dir.rglob("*") if path.is_file()]
    sealed = [path for path in files if path.read_bytes().startswith(ENVELOPE_MAGIC)]
    assert sealed
    assert all(narrative.encode() not in path.read_bytes() for path in sealed)
    assert all(ANSWER.encode() not in path.read_bytes() for path in sealed)


def _request(page, path, *, method='GET', body=None):
    """A real authenticated same-origin browser request, never a reply stub."""
    return page.evaluate("""async data => window.workspaceClient._request(data.path,
        {method:data.method, ...(data.body === null ? {} : {body:JSON.stringify(data.body)})})""",
        {'path':path, 'method':method, 'body':body})


def _tool_payload(response):
    """Decode the actual finite MCP/HTTP transport, exactly as the SDK does."""
    wire=response.json()
    if response.url.split('?')[0].endswith('/mcp/rpc'):
        result=wire['result']
    else:
        result=wire
    return result['structuredContent'] if 'structuredContent' in result else result


def _session(page):
    return _request(page, '/api/complaint-workspace/session')['session']


def _login_panel(page, credential, *, panel):
    page.fill('#'+panel+'-credential', credential)
    page.click('#'+panel+'-login button[type=submit]')
    page.wait_for_function("id => document.getElementById(id).textContent === 'Signed in'", arg=panel+'-auth-status')


def _stored_rule_signatures(shared):
    """Read law bytes from the current authenticated stored typed DG."""
    nodes=shared['dependency_graph']['nodes']
    result={}
    for node_id,node in nodes.items():
        a=node.get('attributes') or {}
        if a.get('dependency_class')!='legally_sourced_requirement':
            continue
        record=a['source_record']
        text=record.get('source_text') or record.get('content')
        assert type(text) is str and text
        result[node_id]={'rule_text':a['rule_text'],'source_hash':a['source_hash'],
            'source_span':a['source_span'],'authority_identity':a.get('authority_identity') or record.get('authority_id'),
            'source_body_sha256':hashlib.sha256(text.encode()).hexdigest()}
    return result


def _law_projection(page, world):
    """Actual owner API and production renderer on a test-owned DOM mount.

    The workspace has no built-in legal-DG refresh button. This is explicitly
    production-component coverage, rather than a claim of that missing flow.
    No source proof, graph, admission label or response is fabricated here.
    """
    payload = _request(page, '/api/graphs/' + world.case.case_id + '/legal-dependency')
    page.evaluate("""payload => {
        let mount=document.getElementById('test-owned-law-component');
        if(!mount){mount=document.createElement('section');mount.id='test-owned-law-component';
            mount.dataset.fixtureOwnedComponent='true';document.body.appendChild(mount);}
        window.complaintGraphView.renderLawDerivedDependencyGraph(mount,payload);
    }""", payload)
    assert page.get_attribute('#test-owned-law-component [data-role=law-derived-dependency-graph]', 'data-proof') == 'false'
    return payload


def _source_and_conditional_ir(owner, world):
    """DOM unavailable search, real browser-fetch fixture rows, DOM review.

    The current form has no corpus provisioning field. Its unavailable result
    remains a tested limitation. Authored local rows enter the actual Data311
    acquisition through a separate explicit authenticated browser request.
    """
    case = world.case.case_id
    owner.fill('#legal-context-case-id', case)
    owner.click('#legal-context-refresh')
    owner.wait_for_function("document.getElementById('legal-context-display').dataset.verification === 'verified'")
    owner.select_option('#legal-context-applicability', 'explicit')
    for name, value in [('jurisdiction','Oregon'),('forum','synthetic-state-trial-forum'),
                        ('event-date','2024-03-04'),('applicable-law-date','2024-03-15')]:
        owner.fill('#legal-context-'+name, value)
    with owner.expect_response(lambda r:r.url.endswith('/api/legal-context/'+case) and r.request.method=='POST') as saved:
        owner.click('#legal-context-save')
    assert saved.value.status == 200
    assert saved.value.json()['applicability'] == 'explicit'
    owner.fill('#consent-case-id',case)
    owner.select_option('#consent-purpose','citation_acquisition')
    with owner.expect_response(lambda r:r.url.endswith('/processing-consent') and r.request.method=='POST') as chosen:
        owner.click('#consent-choose-local')
    assert chosen.value.status==200, chosen.value.json()
    generation=chosen.value.json()['generation']
    owner.wait_for_function("generation => document.getElementById('consent-decision-display').dataset.generation === String(generation)",arg=generation)
    owner.fill('#legal-research-case-id',case)
    owner.fill('#legal-research-query',QUERY)
    owner.fill('#legal-research-consent-generation',str(generation))
    with owner.expect_response(lambda r:r.url.endswith('/api/legal-research/'+case) and r.request.method=='POST') as unavailable:
        owner.click('#legal-research-run')
    unavailable_payload = unavailable.value.json()
    assert unavailable_payload.get('candidate_count',0) == 0
    assert unavailable_payload['status'] == 'unavailable'
    assert unavailable_payload['error_code'] == 'offline_asset_missing'
    owner.wait_for_function("document.getElementById('legal-research-display').dataset.status === 'unavailable'")
    from tests.test_gui25_26_private_owner_http import _body
    from tests.test_cimp_gui_29 import LEGAL_TEXT, VOCABULARY, LEAN_TEXT, OBLIGATION_TEXT
    body = _body(generation)
    body['operation_id']='synthetic-gui56-local-source'
    body['local_rows']={'state_statute':[{'text':LEGAL_TEXT,
        'citation':'fixture://gui56-source','uri':'fixture://gui56-source',
        'corpus_version':'synthetic-v1','jurisdiction':'OR','effective_date':'2024-01-01'}],
        'state_administrative_rule':[]}
    acquired = _request(owner,'/api/legal-research/'+case,method='POST',body=body)
    assert acquired['candidate_count'] > 0
    assert acquired['admitted_law'] is False and acquired['proof'] is False
    source=next(row for row in acquired['source_version_receipts'] if row['kind']=='candidate')
    with owner.expect_response(lambda r:r.url.endswith('/api/legal-research/'+case) and r.request.method=='GET') as listed:
        owner.click('#legal-research-refresh')
    assert listed.value.status == 200
    owner.wait_for_function("document.getElementById('legal-research-receipts').textContent.includes('candidate')")
    owner.fill('#legal-admission-case-id',case)
    for field,key in [('identity','authority_identity'),('jurisdiction','jurisdiction'),
                      ('version','version'),('hash','content_hash'),('effective-date','effective_date'),
                      ('passage','source_passage')]:
        owner.fill('#legal-admission-'+field,source[key])
    owner.select_option('#legal-admission-applicability',source['stated_applicability'])
    owner.select_option('#legal-admission-treatment',source['treatment_state'])
    with owner.expect_response(lambda r:r.url.endswith('/admissions') and r.request.method=='POST') as reviewed:
        owner.click('#legal-admission-submit')
    assert reviewed.value.status == 200
    receipt=reviewed.value.json()
    assert receipt['source_status']=='source_admitted', {key:receipt.get(key) for key in ('source_status','reason','error_code')}
    assert receipt['source_admission']['record']['content']==source['source_passage']
    assert receipt['applicability']=='unknown' and receipt['treatment_state']=='unknown'
    assert receipt['admitted_law'] is False and receipt['proof'] is False and receipt['support_eligible'] is False
    assert receipt['attribution']['actor_principal_id']==world.owner.principal_id != world.case.tenant_id
    # Real canonical Data compilation, kept separate from checked proof. The
    # client's emitted syntax remains untrusted input to the actual owner.
    current=_request(owner,'/api/legal-analysis/'+case)
    start=LEGAL_TEXT.index(OBLIGATION_TEXT)
    compiled=_request(owner,'/api/legal-analysis/'+case,method='POST',body={
        'request_id':'synthetic-gui56-ir','source_content_hash':source['content_hash'],
        'vocabulary':VOCABULARY,'emitted_lean':LEAN_TEXT,
        'expected_private_revision':current['private_revision'],
        'expected_session_revision':current['session_revision'],
        'typed_obligations':[{'kind':'obligation','obligation_id':'synthetic-gui56-duty',
            'statement':OBLIGATION_TEXT,'source_span':{'start':start,'end':start+len(OBLIGATION_TEXT),
                'text':OBLIGATION_TEXT,'unit':'character'}}]})
    assert compiled['attachment_persisted'] is True and compiled['status']=='attached'
    assert compiled['admitted_law'] is False and compiled['executed_proof'] is False
    assert compiled['typed_obligations'] and all(row['discharged'] is False for row in compiled['typed_obligations'])
    owner.fill('#proof-trace-case-id',case)
    owner.click('#proof-trace-refresh')
    owner.wait_for_function("document.querySelectorAll('#proof-trace-list article').length > 0")
    assert owner.get_attribute('#proof-trace-summary','data-proof')=='false'
    assert owner.get_attribute('#proof-trace-summary','data-legal-sufficiency')=='false'
    assert not owner.locator('[data-green-checkmark="true"]').count()
    # Current typed graph may contain zero admitted requirements when the
    # canonical source owner's treatment/applicability is unknown. Empty is
    # truthful, rather than upgrading source custody into governing support.
    graph=_law_projection(owner,world)
    assert graph['requirements']==[]
    assert owner.locator('#test-owned-law-component [data-role=legal-rule]').count()==0
    return source


def test_owner_lawyer_dom_journey_uses_real_handlers(tmp_path, monkeypatch):
    from mediator.legal_authority_hooks import LegalAuthorityStorageHook
    from tests.test_authority_dependency_pipeline import _source_record
    from tests.test_cimp_gui_27 import NARRATIVE as SOURCE_NARRATIVE
    raw_source = _source_record('synthetic-gui56-source-rule', 'notice')
    actual_corpus_read = LegalAuthorityStorageHook.get_authorities_by_claim
    # ONLY the authored local corpus I/O changes. The genuine extractor,
    # current-context verifier, typed DG and encrypted workflow stay intact.
    monkeypatch.setattr(LegalAuthorityStorageHook, 'get_authorities_by_claim',
        lambda self, user_id, claim_type: [deepcopy(raw_source)] if claim_type == 'employment_discrimination' else [])
    world=owner_lawyer_journey_world(tmp_path/'world')
    assert world.owner.principal_id != world.case.tenant_id
    with _browsers(tmp_path/'browser',monkeypatch,world.app) as (open_page,bridge):
        owner=open_page('owner');_arm(owner,world,'synthetic-owner-credential')
        owner.fill('#adaptive-narrative',SOURCE_NARRATIVE);owner.click('#adaptive-enter-narrative')
        owner.wait_for_function("document.getElementById('adaptive-pending').dataset.pending === 'true'")
        inquiry=owner.get_attribute('#adaptive-pending','data-inquiry-id')
        admitted = _law_projection(owner, world)
        assert admitted['admitted_count'] >= 1 and admitted['proof'] is False and admitted['legal_sufficiency'] is False
        assert owner.locator('#test-owned-law-component [data-role=legal-rule]').count() == admitted['admitted_count']
        for row in admitted['requirements']:
            assert row['admitted_law'] is True and row['jurisdiction'] == 'OR'
            assert row['content_hash'] == hashlib.sha256(raw_source['source_text'].encode()).hexdigest()
            span = row['source_span']
            assert raw_source['source_text'].encode()[span['start']:span['end']].decode() == row['requirement']
            assert row['authority_identity'] and row['requirement_id']
        source_rules = [(row['content_hash'], row['source_span'], row['requirement'], row['authority_identity'])
                        for row in admitted['requirements']]
        before=_session(owner)
        stored_rules_before=_stored_rule_signatures(before['shared_interview'])
        assert stored_rules_before
        owner.click('#inquiry-why')
        owner.wait_for_function("document.getElementById('inquiry-explanation-status').dataset.action === 'why'")
        assert owner.get_attribute('#inquiry-explanation-status','data-stored-as-answer')=='false'
        assert _session(owner)['intake_history']==before['intake_history']
        assert owner.locator('#inquiry-explanation-factual').inner_text() != owner.locator('#inquiry-explanation-law').inner_text()
        owner.fill('#adaptive-answer',ANSWER)
        with owner.expect_response(lambda r:r.request.method=='POST' and ('/mcp/' in r.url or '/intake-chat' in r.url)) as answered:
            owner.click('#adaptive-submit-answer')
        assert answered.value.status==200
        offer=_tool_payload(answered.value)['adaptive_inquiry']['factual_correction']
        target=offer['target_stable_id']
        owner.wait_for_function("target => document.getElementById('factual-correction-target').value === target",arg=target)
        prior=KnowledgeGraph.from_dict(_session(owner)['shared_interview']['knowledge_graph']).assertion_state(target)
        assert prior['status']=='active'
        owner.fill('#factual-correction-replacement',REPLACEMENT);owner.click('#factual-correction-submit')
        owner.wait_for_function("document.getElementById('factual-correction-status').dataset.status === 'applied'")
        state=_session(owner)
        graph=KnowledgeGraph.from_dict(state['shared_interview']['knowledge_graph'])
        assert graph.assertion_state(target)['status']=='superseded'
        assert graph.assertion_state(target)['envelope']==prior['envelope']
        assert REPLACEMENT in [row.get('answer') for row in state['intake_history']]
        unchanged_law = _law_projection(owner, world)
        stored_rules_after=_stored_rule_signatures(state['shared_interview'])
        closed_diagnostic={
            'stored_rule_count_before':len(stored_rules_before),'stored_rule_count_after':len(stored_rules_after),
            'stored_source_rule_bytes_unchanged':stored_rules_before==stored_rules_after,
            'current_admitted_count':unchanged_law['admitted_count'],
            'research_gap':unchanged_law.get('research_gap'),
            'rejected_reasons':[row.get('reason') for row in unchanged_law.get('rejected_narratives',[]) if row.get('origin')=='dependency_graph'],
            'node_eligibility':[{'source_available':node['attributes'].get('source_available'),
                'support_eligible':node['attributes'].get('support_eligible'),
                'legal_support_invalidated':node['attributes'].get('legal_support_invalidated'),
                'invalidation_reason':node['attributes'].get('invalidation_reason')}
                for node in state['shared_interview']['dependency_graph']['nodes'].values()
                if (node.get('attributes') or {}).get('dependency_class')=='legally_sourced_requirement']}
        assert stored_rules_after==stored_rules_before,closed_diagnostic
        # The actual correction retires current source availability;
        # historical typed source bytes remain exact rather than becoming the
        # user's replacement sentence. Do not force old eligibility to green.
        assert unchanged_law['requirements']==[]
        assert closed_diagnostic['rejected_reasons']==['source_support_unavailable']
        assert closed_diagnostic['research_gap']=='no_admitted_authority'
        assert all(row['source_available'] is False for row in closed_diagnostic['node_eligibility'])
        assert unchanged_law['rules_rewritten_by_user_or_model'] is False
        closed_diagnostic['context_revisions']={name:(snapshot['shared_interview']['intake_case_file'].get('legal_context') or {}).get('context_revision')
            for name,snapshot in [('before',before),('after',state)]}
        closed_diagnostic['claim_types']={name:[row.get('claim_type',row.get('type')) for row in snapshot['shared_interview']['intake_case_file'].get('candidate_claims',[]) if isinstance(row,dict)]
            for name,snapshot in [('before',before),('after',state)]}
        (tmp_path/'closed-law-diagnostic.json').write_text(json.dumps(closed_diagnostic,sort_keys=True))
        assert REPLACEMENT not in owner.locator('#test-owned-law-component [data-role=legal-rules]').inner_text()
        owner.click('#factual-graph-refresh')
        owner.wait_for_function("document.getElementById('factual-graph-status').dataset.status === 'projected'")
        assert owner.locator('#factual-graph-mount').inner_text()
        # Close the initial raw-corpus fixture before genuine Data acquisition
        # writes and re-reads its own canonical stored source record.
        monkeypatch.setattr(LegalAuthorityStorageHook,'get_authorities_by_claim',actual_corpus_read)
        source=_source_and_conditional_ir(owner,world)
        _sealed_narrative_absent(world,SOURCE_NARRATIVE)
        owner.click('#finite-interview-pause')
        owner.wait_for_function("document.getElementById('finite-interview-outcome').dataset.stop !== ''")
        assert owner.get_attribute('#finite-interview-outcome','data-legal-sufficiency')=='false'
        assert owner.get_attribute('#finite-interview-outcome','data-stop') not in {'','sufficient','verified'}
        # No preaccepted membership or copied policy: both invitation sides
        # and the owner's real encrypted-source Share are actual DOM actions.
        expected_shared=_session(owner)['shared_interview']
        owner.goto(browser.SAME_ORIGIN+'/cases');_login_panel(owner,'synthetic-owner-credential',panel='case')
        owner.locator('#case-list button',has_text='owner-lawyer-journey').click()
        owner.select_option('#lawyer-select',world.lawyer.principal_id)
        owner.fill('#assignment-expires',str(world.now['t']+3600))
        for scope in ('case.read','case.review','case.message.send'):
            owner.locator("#invite-lawyer input[value='"+scope+"']").check()
        owner.click('#invite-lawyer button[type=submit]')
        owner.wait_for_selector('#assignment-list li[data-state=pending]')
        grant=owner.get_attribute('#assignment-list li[data-state=pending]','data-grant-id')
        lawyer=open_page('lawyer');lawyer.goto(browser.SAME_ORIGIN+'/cases')
        _login_panel(lawyer,'synthetic-lawyer-credential',panel='case')
        with lawyer.expect_response(lambda r:r.url.endswith('/'+grant+'/accept') and r.request.method=='POST') as accepted:
            lawyer.locator('#assignment-list [data-grant-id="'+grant+'"] button',has_text='Accept scope').click()
        assert accepted.value.status==200, accepted.value.json()
        version=str(accepted.value.json()['version'])
        # Replay the exact real DOM request; these values came from the
        # actual browser request, not a forged session or authority packet.
        accepted_request=accepted.value.request
        accept_body=accepted_request.post_data_json
        replay_material={'path':'/api/cases/assignments/'+grant+'/accept',
            'csrf':accepted_request.headers['x-csrf-token'],'body':accept_body}
        replay=lawyer.evaluate("""async data => {const r=await fetch(data.path,{method:'POST',credentials:'same-origin',
            headers:{'content-type':'application/json','x-csrf-token':data.csrf},body:JSON.stringify(data.body)});
            return {status:r.status,body:await r.json()};}""",replay_material)
        assert replay['status']==200 and str(replay['body']['version'])==version
        mismatch=lawyer.evaluate("""async data => {const r=await fetch(data.path,{method:'POST',credentials:'same-origin',
            headers:{'content-type':'application/json','x-csrf-token':data.csrf},
            body:JSON.stringify({...data.body,scope:['case.read']})});return {status:r.status,body:await r.json()};}""",replay_material)
        assert mismatch['status']==403 and mismatch['body']['error']=='scope_mismatch'
        lawyer.wait_for_selector('#assignment-list li[data-state=accepted]')
        assert int(version)>1
        # Return owner to its actual SDK, then use server-rendered share UI.
        _arm(owner,world,'synthetic-owner-credential')
        with owner.expect_navigation(wait_until='domcontentloaded'):
            owner.click('#open-owner-review-sharing')
        from tests.test_gui32_review_browser import _authorize
        _authorize(owner,'synthetic-owner-credential')
        owner.fill('#review-membership',grant);owner.fill('#review-membership-version',version)
        owner.click('#review-share-form button')
        owner.wait_for_selector('#review-share-result a')
        link=owner.locator('#review-share-result a').get_attribute('href')
        assert link.startswith('/api/legal-analysis/') and 'expected_membership_revision=' in link
        world.owner_keys.lock();world.service.lock_private_keys()
        # The recipient has its own unlocked key and never borrows OwnerMaster.
        from tests.test_gui32_review_browser import _cookie_login
        _cookie_login(lawyer,'synthetic-lawyer-credential')
        assert lawyer.goto(browser.SAME_ORIGIN+link).status==200
        _authorize(lawyer,'synthetic-lawyer-credential')
        lawyer.fill('[name=request_id]','synthetic-gui56-human-review')
        lawyer.fill('[name=interpretation]',MESSAGE)
        lawyer.fill('[name=source_citation]',source['authority_identity'])
        with lawyer.expect_response(lambda r:r.url.split('?')[0].endswith('/lawyer-reviews') and r.request.method=='POST') as proposed:
            lawyer.click('#lawyer-review-form button')
        assert proposed.value.status==200
        human=proposed.value.json()
        assert human['record']['actor_principal_id']==world.lawyer.principal_id != world.case.tenant_id
        assert human['record']['canonical_owner_principal_id']==world.case.tenant_id
        assert human['record']['governing_legal_authority'] is False
        assert human['legal_sufficiency'] is False and human['governing_legal_authority'] is False
        lawyer.wait_for_function("document.querySelectorAll('#human-review-rows tr').length === 1")
        assert MESSAGE in lawyer.locator('#human-review-rows').inner_text()
        assert world.owner_keys.unlocked is False
        # Message metadata is real durable AEAD. It is conversation, not KG
        # evidence, admitted law, or an instruction to execute a model.
        owner.goto(browser.SAME_ORIGIN+MESSAGE_INBOX_PATH)
        _login_panel(owner,'synthetic-owner-credential',panel='inbox')
        owner.fill('#case-id',world.case.case_id);owner.click('#create-thread')
        owner.wait_for_function("document.getElementById('thread-id').value.length > 0")
        thread=owner.locator('#thread-id').input_value()
        owner.fill('#message-text',MESSAGE)
        with owner.expect_response(lambda r:r.url.endswith('/'+thread+'/messages') and r.request.method=='POST') as sent:
            owner.click('#send-message button[type=submit]')
        assert sent.value.status==201
        assert sent.value.json()['disposition']=='conversation'
        assert sent.value.json().get('adoption') is None
        owner.wait_for_function("document.querySelectorAll('#message-list .message-text').length === 1")
        lawyer.goto(browser.SAME_ORIGIN+MESSAGE_INBOX_PATH)
        _login_panel(lawyer,'synthetic-lawyer-credential',panel='inbox')
        lawyer.fill('#case-id',world.case.case_id);lawyer.fill('#membership-grant-id',grant)
        lawyer.fill('#membership-version',version);lawyer.fill('#thread-id',thread);lawyer.click('#open-thread')
        lawyer.wait_for_function("document.querySelectorAll('#message-list .message-text').length === 1")
        assert MESSAGE in lawyer.locator('#message-list').inner_text()
        stranger=open_page('stranger');stranger.goto(browser.SAME_ORIGIN+MESSAGE_INBOX_PATH)
        _login_panel(stranger,'synthetic-stranger-credential',panel='inbox')
        stranger.fill('#case-id',world.case.case_id);stranger.fill('#thread-id',thread)
        with stranger.expect_response(lambda r:r.url.split('?')[0].endswith('/'+thread+'/messages')) as denied:
            stranger.click('#open-thread')
        assert denied.value.status==404 and denied.value.json()['error']=='missing_case'
        assert MESSAGE not in stranger.locator('body').inner_text()
        # A real logout clears existing recipient DOM and invalidates cookie.
        assert lawyer.goto(browser.SAME_ORIGIN+link).status==200
        _authorize(lawyer,'synthetic-lawyer-credential')
        assert MESSAGE in lawyer.locator('#human-review-rows').inner_text()
        lawyer.click('#review-logout')
        lawyer.wait_for_function("document.getElementById('lawyer-review-result').textContent.includes('logged out')")
        assert MESSAGE not in lawyer.locator('body').inner_text()
        assert lawyer.evaluate("async () => (await fetch('/api/complaint-workspace/auth/session',{credentials:'same-origin'})).status")==401
        assert any('/admissions' in path for path in bridge.same_origin_paths)
        assert any('/lawyer-reviews/share' in path for path in bridge.same_origin_paths)
        assert any('/lawyer-reviews' in path for path in bridge.same_origin_paths)
        assert not bridge.aborted_unqualified['websocket'] and not bridge.aborted_unqualified['sse']
    # Fresh workspace, registry, app, wallet objects and real encrypted stores.
    # Only operator configuration survives; no decrypted DTO/cache is copied.
    cold=owner_lawyer_journey_world(tmp_path/'world',previous=world)
    assert cold.service is not world.service and cold.recipient is not world.recipient
    head=cold.service.joined_revision_repository(cold.case.tenant_id,cold.case.case_id)/'head.cgpe'
    head_before=head.read_bytes()
    with _browsers(tmp_path/'cold-browser',monkeypatch,cold.app) as (open_page,_bridge):
        page=open_page('cold-owner');_arm(page,cold,'synthetic-owner-credential',bootstrap=False)
        with page.expect_response(lambda r:r.request.method=='POST' and ('/mcp/' in r.url or '/intake-chat' in r.url)) as resumed:
            page.click('#encrypted-interview-resume-button')
        assert resumed.value.status==200
        resume_receipt=_tool_payload(resumed.value)['encrypted_resume']
        for flag in ('hooks_replayed','messages_replayed','reconstructed_from_browser_cache'):
            assert resume_receipt[flag] is False
        assert resume_receipt['browser_cache_ignored'] is True
        page.wait_for_function("document.getElementById('encrypted-interview-resume').dataset.resumed === 'true'")
        assert page.get_attribute('#encrypted-interview-resume','data-case-id')==cold.case.case_id
        for flag in ('hooks-replayed', 'messages-replayed', 'browser-cache-used'):
            assert page.get_attribute('#encrypted-interview-resume', 'data-'+flag) == 'false'
        assert page.get_attribute('#encrypted-interview-resume-inquiry','data-inquiry-id')
        state=_session(page)
        assert state['shared_interview']['pending_inquiry']==expected_shared['pending_inquiry']
        assert state['shared_interview']['knowledge_graph']==expected_shared['knowledge_graph']
        assert REPLACEMENT in [row.get('answer') for row in state['intake_history']]
        assert source['content_hash'] in state['shared_interview']['intake_case_file']['legal_source_passage_index']
        assert head.read_bytes()==head_before
        cold.owner_keys.lock();cold.service.lock_private_keys()
        with page.expect_response(lambda r:r.request.method=='POST' and ('/mcp/' in r.url or '/intake-chat' in r.url)) as locked:
            page.click('#encrypted-interview-resume-button')
        # Resume returns a finite domain refusal even when JSON-RPC itself
        # succeeds. Its actual receipt, not transport status, denies plaintext.
        locked_payload=_tool_payload(locked.value)
        assert locked_payload['status']=='missing_key' and locked_payload['code']=='missing_key'
        assert locked_payload['resumed'] is False and locked_payload['plaintext_case_state'] is None
        assert locked_payload['case'] is None and locked_payload['pending_inquiry'] is None
        page.wait_for_function("document.getElementById('encrypted-interview-resume').dataset.resumed !== 'true'")
        assert head.read_bytes()==head_before
        assert REPLACEMENT not in page.locator('#encrypted-interview-resume').inner_text()
        recipient=open_page('cold-recipient')
        recipient.goto(browser.SAME_ORIGIN+'/cases',wait_until='domcontentloaded')
        _cookie_login(recipient,'synthetic-lawyer-credential')
        assert recipient.goto(browser.SAME_ORIGIN+link).status==200
        _authorize(recipient,'synthetic-lawyer-credential')
        assert MESSAGE in recipient.locator('#human-review-rows').inner_text()
        assert cold.owner_keys.unlocked is False
        recipient.goto(browser.SAME_ORIGIN+MESSAGE_INBOX_PATH)
        _login_panel(recipient,'synthetic-lawyer-credential',panel='inbox')
        recipient.fill('#case-id',cold.case.case_id);recipient.fill('#membership-grant-id',grant)
        recipient.fill('#membership-version',version);recipient.fill('#thread-id',thread);recipient.click('#open-thread')
        recipient.wait_for_function("document.querySelectorAll('#message-list .message-text').length === 1")
        assert MESSAGE in recipient.locator('#message-list').inner_text()
        assert head.read_bytes()==head_before
    _sealed_narrative_absent(cold,SOURCE_NARRATIVE)


def test_stale_correction_and_unresolved_unknown_do_not_count_as_support(tmp_path,monkeypatch):
    world=owner_lawyer_journey_world(tmp_path/'world')
    with _browsers(tmp_path/'browser',monkeypatch,world.app) as (open_page,bridge):
        page=open_page('owner-negative');_arm(page,world,'synthetic-owner-credential')
        page.fill('#adaptive-narrative',NARRATIVE);page.click('#adaptive-enter-narrative')
        page.wait_for_function("document.getElementById('adaptive-pending').dataset.pending === 'true'")
        page.click('#adaptive-unknown')
        page.wait_for_function("document.getElementById('adaptive-gap-status').dataset.gapPreserved === 'true'")
        assert page.get_attribute('#adaptive-pending','data-from-fixed-intake')=='false'
        page.fill('#adaptive-answer',ANSWER);page.click('#adaptive-submit-answer')
        page.wait_for_function("document.getElementById('factual-correction-graph-revision').value.startsWith('gr_')")
        head=world.service.joined_revision_repository(world.case.tenant_id,world.case.case_id)/'head.cgpe'
        before=head.read_bytes()
        page.fill('#factual-correction-graph-revision','gr_stale')
        page.fill('#factual-correction-replacement','This stale sentence must not become the fact.')
        page.click('#factual-correction-submit')
        page.wait_for_function("document.getElementById('factual-correction-status').dataset.status === 'refused'")
        assert page.get_attribute('#factual-correction-status','data-error')=='stale_target'
        assert head.read_bytes()==before
        assert 'This stale sentence must not become the fact.' not in str(_session(page)['intake_history'])
        assert page.evaluate('() => typeof window.mockApi')=='undefined'
        assert any('mcp' in path or path.endswith('/intake-chat') for path in bridge.same_origin_paths)
