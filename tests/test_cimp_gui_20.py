"""A new process resumes the interview from the encrypted snapshot.

The pending inquiry, case, consent, factual and legal graph revisions,
deferred gaps, and corrections come from that snapshot. Hook receipts and
saved messages are not dispatched again. A browser cache is not a case
record. Denied, revoked, and missing-key resumes stay explicit.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import create_complaint_workspace_router

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

USER_ID = "synthetic-gui-20"
PASSPHRASE = "synthetic-gui-20-passphrase"
OTHER_PASSPHRASE = "synthetic-gui-20-other-passphrase"
QUESTION = "Who scheduled the warehouse shift?"
CACHE_QUESTION = "Browser cache question that must not be restored."
FACT_REVISION = "fact-rev-4"
LAW_REVISION = "law-rev-9"
GAP_ID = "inq-deferred-gap"
CORRECTION_ID = "cor-gui-20"
HOOK_REQUEST = "a" * 32


def _service(tmp_path: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(USER_ID, USER_ID)
    return service


def _seed(service: ComplaintWorkspaceService) -> None:
    state = service._load_state(USER_ID)
    state["case_id"] = USER_ID
    state["operation_consent"] = {
        "contract": "operation-consent-v1",
        "case_id": USER_ID,
        "generation": 3,
        "revoked": False,
        "purpose": "extract_facts",
    }
    state["intake_history"] = [{"question_id": "inq-prior", "answer": "I reported the hazard.", "effect_id": "effect-prior"}]
    state["intake_router"] = {"receipts": [{"operation": "extract_facts", "request_id": HOOK_REQUEST, "status": "available", "provider_replayed": False}]}
    state["deferred_gaps"] = [{
        "inquiry_id": GAP_ID,
        "disposition": "deferred",
        "preserved": True,
        "creates_fact": False,
        "target_id": "gap-target",
    }]
    state["factual_corrections"] = [{
        "correction_id": CORRECTION_ID,
        "previous": "January 1",
        "replacement": "January 2",
        "actor_principal_id": USER_ID,
        "prior_retained": True,
    }]
    state["shared_interview"] = {
        "schema_version": "shared-interview-session-v1",
        "session_id": "interview-gui-20",
        "session_revision": 5,
        "pending_inquiry": {
            "inquiry_id": "inq-pending-20",
            "revision": 6,
            "question": QUESTION,
            "objective_id": "witnesses",
            "target_id": "witness-gap",
            "target_revision": "2",
        },
        "knowledge_graph": {"graph_id": "fact-graph-20", "graph_revision": FACT_REVISION, "entities": [{"id": "fact-1", "name": "shift"}]},
        "dependency_graph": {"graph_id": "law-graph-20", "graph_revision": LAW_REVISION, "nodes": [{"id": "req-1", "label": "causation"}]},
        "legal_sufficiency": False,
    }
    service._save_state(state)


def _assert_exact(body: dict) -> None:
    resume = body["encrypted_resume"]
    assert resume["restored"] is True
    assert resume["status"] == "resumed"
    assert resume["hooks_replayed"] is False
    assert resume["messages_replayed"] is False
    assert resume["browser_cache_used"] is False
    assert resume["source"] == "encrypted_interview_snapshot"
    session = body["session"]
    pending = session["shared_interview"]["pending_inquiry"]
    assert pending["inquiry_id"] == "inq-pending-20"
    assert pending["revision"] == 6
    assert pending["question"] == QUESTION
    assert pending["target_id"] == "witness-gap"
    assert session["case_id"] == USER_ID
    assert session["operation_consent"]["generation"] == 3
    assert session["operation_consent"]["revoked"] is False
    assert session["operation_consent"]["purpose"] == "extract_facts"
    assert session["factual_graph_binding"]["revision"] == FACT_REVISION
    assert session["legal_graph_binding"]["revision"] == LAW_REVISION
    assert session["shared_interview"]["knowledge_graph"]["graph_revision"] == FACT_REVISION
    assert session["shared_interview"]["dependency_graph"]["graph_revision"] == LAW_REVISION
    assert session["deferred_gaps"][0]["inquiry_id"] == GAP_ID
    assert session["deferred_gaps"][0]["disposition"] == "deferred"
    assert session["factual_corrections"][0]["correction_id"] == CORRECTION_ID
    assert session["factual_corrections"][0]["replacement"] == "January 2"
    assert session["factual_corrections"][0]["prior_retained"] is True
    assert [item["effect_id"] for item in session["intake_history"]] == ["effect-prior"]
    assert session["intake_router"]["receipts"][0]["request_id"] == HOOK_REQUEST
    assert session["intake_router"]["hooks_replayed"] is False
    assert body["hooks_replayed"] is False
    assert body["messages_replayed"] is False
    assert body["browser_cache_used"] is False
    assert body["legal_sufficiency"] is False
    assert body["stored_as_answer"] is False
    encoded = json.dumps(body)
    assert CACHE_QUESTION not in encoded


def test_new_process_resumes_exact_encrypted_interview_without_replay(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "integrations.ipfs_datasets.llm.generate_text",
        lambda **_kwargs: calls.append("generate") or (_ for _ in ()).throw(AssertionError("provider replay")),
    )
    service = _service(tmp_path)
    _seed(service)
    sealed = service.seal_encrypted_browser_interview(USER_ID)
    assert sealed["hooks_replayed"] is False
    assert sealed["messages_replayed"] is False
    state = service._load_state(USER_ID)
    state["shared_interview"]["pending_inquiry"]["question"] = "session cache question"
    state["operation_consent"]["generation"] = 99
    state["factual_graph_binding"] = {"revision": "fact-rev-stale", "status": "bound"}
    state["legal_graph_binding"] = {"revision": "law-rev-stale", "status": "bound"}
    state["deferred_gaps"] = [{"inquiry_id": "inq-session-cache", "disposition": "deferred"}]
    state["factual_corrections"] = [{"correction_id": "cor-session-cache", "replacement": "session"}]
    state["intake_history"] = [{"question_id": "extra", "answer": "replay me", "effect_id": "effect-replay"}]
    state["intake_router"] = {"receipts": [{"operation": "extract_facts", "request_id": "b" * 32, "status": "available"}]}
    service._save_state(state)
    fresh = ComplaintWorkspaceService(root_dir=service._session_dir)
    fresh.unlock_private_keys(passphrase=PASSPHRASE)
    resumed = fresh.resume_encrypted_browser_interview(USER_ID, browser_cache={"question": CACHE_QUESTION, "case_text": CACHE_QUESTION})
    _assert_exact(resumed)
    assert calls == []
    assert fresh._interview_mediators == {}
    again = fresh.run_intake_chat_turn(USER_ID, message=json.dumps({"question": CACHE_QUESTION}), interview_action="encrypted_resume")
    _assert_exact(again)
    assert calls == []


def test_http_resume_uses_encrypted_snapshot_not_request_body(tmp_path):
    service = _service(tmp_path)
    _seed(service)
    service.seal_encrypted_browser_interview(USER_ID)
    app = FastAPI()
    app.include_router(create_complaint_workspace_router(service, trusted_local=True))
    client = TestClient(app)
    response = client.post(
        "/api/complaint-workspace/intake-chat",
        json={"user_id": USER_ID, "message": CACHE_QUESTION, "interview_action": "encrypted_resume"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    _assert_exact(body)
    assert body["adaptive_inquiry"]["prompt"] == QUESTION
    assert body["adaptive_inquiry"]["inquiry_id"] == "inq-pending-20"


def test_denied_revoked_and_missing_key_resume_are_explicit(tmp_path):
    service = _service(tmp_path)
    _seed(service)
    service.seal_encrypted_browser_interview(USER_ID)
    service._authorizer = lambda _requirement, _context: False
    denied = service.resume_encrypted_browser_interview(USER_ID, browser_cache=CACHE_QUESTION)
    assert denied["status"] == "denied"
    assert denied["encrypted_resume"]["code"] == "authorization_denied"
    assert denied["encrypted_resume"]["restored"] is False
    assert denied["encrypted_resume"]["explicit"] is True
    assert denied["browser_cache_used"] is False
    assert CACHE_QUESTION not in json.dumps(denied)
    assert "shared_interview" not in denied["session"]

    locked = _service(tmp_path / "locked")
    _seed(locked)
    locked.seal_encrypted_browser_interview(USER_ID)
    locked.lock_private_keys()
    locked_result = locked.resume_encrypted_browser_interview(USER_ID, browser_cache=CACHE_QUESTION)
    assert locked_result["status"] == "denied"
    assert locked_result["encrypted_resume"]["code"] == "unlock_needed"
    assert locked_result["encrypted_resume"]["restored"] is False
    assert CACHE_QUESTION not in json.dumps(locked_result)

    missing = ComplaintWorkspaceService(root_dir=tmp_path / "no-keys")
    missing_result = missing.resume_encrypted_browser_interview(USER_ID, browser_cache=CACHE_QUESTION)
    assert missing_result["status"] == "missing_key"
    assert missing_result["encrypted_resume"]["code"] == "missing_key"
    assert missing_result["encrypted_resume"]["restored"] is False
    assert CACHE_QUESTION not in json.dumps(missing_result)

    source = _service(tmp_path / "source")
    _seed(source)
    source.seal_encrypted_browser_interview(USER_ID)
    other = ComplaintWorkspaceService(root_dir=tmp_path / "revoked")
    other.initialize_private_keys(protection="passphrase", passphrase=OTHER_PASSPHRASE)
    other.ensure_private_case_key(USER_ID, USER_ID)
    src_dir = source.interview_snapshot_directory(USER_ID)
    dest_dir = other.interview_snapshot_directory(USER_ID)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_dir, dest_dir)
    revoked = other.resume_encrypted_browser_interview(USER_ID, browser_cache=CACHE_QUESTION)
    assert revoked["status"] == "revoked"
    assert revoked["encrypted_resume"]["code"] == "key_revoked"
    assert revoked["encrypted_resume"]["restored"] is False
    assert revoked["hooks_replayed"] is False
    assert QUESTION not in json.dumps(revoked)
    assert CACHE_QUESTION not in json.dumps(revoked)
    opened = other._load_state(USER_ID)
    assert QUESTION not in json.dumps(opened.get("shared_interview") or {})


def test_browser_resume_ignores_page_cache(tmp_path, monkeypatch):
    from tests.test_gui16_current_privacy import _bind_actual_owner, _enter
    from applications.complaint_workspace import WorkspaceAccess, workspace_access_scope
    from tests.test_cimp_gui_15 import _page

    with _page(tmp_path, monkeypatch, "typed_owner") as (world, page):
        BROWSER_USER = world.case.tenant_id
        service = world.service
        _bind_actual_owner(page, world)
        _enter(page)
        state = service._load_state(BROWSER_USER, case_id=world.case.case_id)
        state["case_id"] = world.case.case_id
        state["operation_consent"] = {"contract": "operation-consent-v1", "case_id": world.case.case_id, "generation": 4, "revoked": False, "purpose": "extract_facts"}
        state["deferred_gaps"] = [{"inquiry_id": GAP_ID, "disposition": "deferred", "preserved": True, "creates_fact": False, "target_id": "gap-target"}]
        state["factual_corrections"] = [{"correction_id": CORRECTION_ID, "previous": "January 1", "replacement": "January 2", "prior_retained": True}]
        state["intake_history"] = [{"question_id": "inq-prior", "answer": "I reported the hazard.", "effect_id": "effect-prior"}]
        state["shared_interview"] = {
            "schema_version": "shared-interview-session-v1",
            "session_id": "interview-gui-20-browser",
            "session_revision": 5,
            "pending_inquiry": {
                "inquiry_id": "inq-pending-20",
                "revision": 6,
                "question": QUESTION,
                "objective_id": "witnesses",
                "target_id": "witness-gap",
                "target_revision": "2",
            },
            "knowledge_graph": {"graph_id": "fact-graph-20", "graph_revision": FACT_REVISION, "entities": [{"id": "fact-1"}]},
            "dependency_graph": {"graph_id": "law-graph-20", "graph_revision": LAW_REVISION, "nodes": [{"id": "req-1"}]},
            "legal_sufficiency": False,
        }
        with workspace_access_scope(WorkspaceAccess.trusted_local(BROWSER_USER, world.case.case_id)):
            service._save_state(state)
        # The authenticated encrypted head is the current case, not a cache.
        # A browser resume must not rewind a newer legitimate head to an older
        # optional sealed version. Only browser storage is polluted here.
        _bind_actual_owner(page, world)
        page.evaluate(
            """marker => {
                localStorage.setItem('complaint-workspace-case', marker);
                sessionStorage.setItem('complaint-workspace-inquiry', marker);
            }""",
            CACHE_QUESTION,
        )
        _bind_actual_owner(page, world)
        assert page.locator("#encrypted-interview-resume").get_attribute("data-task") == "CIMP-GUI-20"
        assert CACHE_QUESTION not in page.text_content("#adaptive-pending-prompt")
        page.click("#encrypted-interview-resume-button")
        page.wait_for_function("document.getElementById('encrypted-interview-resume').dataset.restored === 'true'")
        assert page.get_attribute("#encrypted-interview-resume", "data-browser-cache-used") == "false"
        assert page.get_attribute("#encrypted-interview-resume", "data-hooks-replayed") == "false"
        assert page.get_attribute("#encrypted-interview-resume", "data-messages-replayed") == "false"
        assert page.text_content("#encrypted-interview-resume-inquiry") == QUESTION
        assert "factual fact-rev-4 legal law-rev-9" in page.text_content("#encrypted-interview-resume-graphs")
        assert GAP_ID in page.text_content("#encrypted-interview-resume-gaps")
        assert CORRECTION_ID in page.text_content("#encrypted-interview-resume-corrections")
        assert "consent generation 4" in page.text_content("#encrypted-interview-resume-consent")
        assert page.text_content("#adaptive-pending-prompt") == QUESTION
        stored = page.evaluate("JSON.stringify({...localStorage, ...sessionStorage})")
        assert CACHE_QUESTION not in stored
        assert page.text_content("#encrypted-interview-resume-inquiry") != CACHE_QUESTION


CACHE_TOKEN = "browser-cache-plaintext-gui-20-must-not-return"
def _actual_owner_resume_world(tmp_path):
    """Public operator composition, real issued cookie and encrypted case."""
    from fastapi import FastAPI
    from applications.case_routes import CaseHandlerRegistry, compose_case_routes
    from tests.test_cimp_gui_14 import (_composed_case_world, _composed_login,
        _composed_headers, PASSPHRASE as OWNER_PASSPHRASE)
    from tests.test_cimp_gui_16 import NARRATIVE
    world = _composed_case_world(tmp_path)
    with TestClient(world.app, base_url='https://testserver') as client:
        csrf = _composed_login(client)
        started = client.post('/api/complaint-workspace/intake-chat',
            headers=_composed_headers(world.case, csrf), json={'message': NARRATIVE, 'interview_action': 'start'})
        assert started.status_code == 200, started.text
        shared = started.json()['session']['shared_interview']
        assert shared['pending_inquiry']['question']
    # A separate actual service has no mediator cache, but opens the same
    # authenticated encrypted owner storage. Actor and canonical tenant differ.
    cold = ComplaintWorkspaceService(root_dir=tmp_path / 'workspaces' / world.case.case_id)
    assert cold.unlock_private_keys(passphrase=OWNER_PASSPHRASE)['unlocked'] is True
    handlers = CaseHandlerRegistry()
    handlers.bind(world.case, mediator=cold, workspace_service=cold)
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=handlers, include_review=False, include_document=False)
    assert world.owner.principal_id != world.case.tenant_id
    return world, cold, app, shared


def test_actual_owner_cookie_cold_resume_keeps_current_case_and_pending_inquiry(tmp_path, monkeypatch):
    from tests.test_cimp_gui_14 import _composed_login, _composed_headers
    world, cold, app, shared = _actual_owner_resume_world(tmp_path)
    head = cold.joined_revision_repository(world.case.tenant_id, world.case.case_id) / 'head.cgpe'
    before = head.read_bytes()
    monkeypatch.setattr(cold, '_mediator_for_shared_interview', lambda *a, **k:
        (_ for _ in ()).throw(AssertionError('actual cold resume replayed mediator hooks')))
    with TestClient(app, base_url='https://testserver') as client:
        csrf = _composed_login(client)
        result = client.post('/api/complaint-workspace/intake-chat',
            headers=_composed_headers(world.case, csrf), json={'message': CACHE_TOKEN, 'interview_action': 'encrypted_resume'})
        assert result.status_code == 200, result.text
        payload = result.json()
        assert payload['resumed'] is True
        assert payload['encrypted_resume']['case']['case_id'] == world.case.case_id
        assert payload['encrypted_resume']['pending_inquiry'] == shared['pending_inquiry']
        assert payload['encrypted_resume']['hooks_replayed'] is False
        assert payload['encrypted_resume']['messages_replayed'] is False
        assert CACHE_TOKEN not in result.text
    assert head.read_bytes() == before


@pytest.mark.parametrize('boundary', ['key_lock', 'logout'])
def test_actual_owner_resume_denies_plaintext_after_projection_cutoff(tmp_path, monkeypatch, boundary):
    from threading import Event, Thread
    from applications.browser_sessions import SESSION_COOKIE
    from applications.complaint_workspace import ComplaintWorkspaceRequestHandlers
    from tests.test_cimp_gui_14 import _composed_login, _composed_headers
    world, cold, app, shared = _actual_owner_resume_world(tmp_path)
    head = cold.joined_revision_repository(world.case.tenant_id, world.case.case_id) / 'head.cgpe'
    before = head.read_bytes()
    actual = ComplaintWorkspaceRequestHandlers._build_session_payload
    completed = []
    entered, release = Event(), Event()
    with TestClient(app, base_url='https://testserver') as client:
        csrf = _composed_login(client)
        token = client.cookies.get(SESSION_COOKIE)
        def project_then_cutoff(handler, state):
            payload = actual(handler, state)
            if handler.workspace is cold and not completed:
                entered.set()
                assert release.wait(15), 'bounded actual resume projection barrier expired'
            return payload
        monkeypatch.setattr(ComplaintWorkspaceRequestHandlers, '_build_session_payload', project_then_cutoff)
        responses, errors = [], []
        def request():
            try:
                responses.append(client.post('/api/complaint-workspace/intake-chat',
                    headers=_composed_headers(world.case, csrf), json={'interview_action': 'encrypted_resume'}))
            except BaseException as error:
                errors.append(error)
        worker = Thread(target=request, daemon=True)
        worker.start()
        try:
            assert entered.wait(15), 'actual decrypted resume did not reach projection'
            if boundary == 'key_lock':
                cold.lock_private_keys()
            else:
                world.sessions.logout(token, csrf_token=csrf)
            completed.append(True)
        finally:
            release.set()
            worker.join(20)
        assert not worker.is_alive() and not errors
        assert len(responses) == 1
        result = responses[0]
        assert completed == [True]
        leaked = shared['pending_inquiry']['question'] in result.text
        assert not leaked, 'current resume plaintext survived actual access cutoff'
        assert result.json().get('resumed') is not True
    assert head.read_bytes() == before


def test_actual_owner_chromium_resumes_encrypted_inquiry_and_case(tmp_path, monkeypatch):
    from tests.test_cimp_gui_15 import _page
    from tests.test_gui16_current_privacy import _bind_actual_owner, _enter
    with _page(tmp_path, monkeypatch, 'typed_owner') as (world, page):
        _bind_actual_owner(page, world)
        _enter(page)
        inquiry = page.get_attribute('#adaptive-pending', 'data-inquiry-id')
        question = page.locator('#adaptive-pending-prompt').text_content()
        page.click('#encrypted-interview-resume-button')
        page.wait_for_function("document.getElementById('encrypted-interview-resume').dataset.resumed === 'true'")
        assert page.get_attribute('#encrypted-interview-resume', 'data-case-id') == world.case.case_id
        assert page.get_attribute('#encrypted-interview-resume-inquiry', 'data-inquiry-id') == inquiry
        assert page.locator('#encrypted-interview-resume-inquiry').text_content() == question
        assert world.principal.principal_id != world.case.tenant_id


def test_actual_resume_response_cannot_paint_after_real_cookie_logout(tmp_path, monkeypatch):
    from tests.test_cimp_gui_15 import _page
    from tests.test_gui16_current_privacy import _bind_actual_owner, _enter
    with _page(tmp_path, monkeypatch, 'typed_owner') as (world, page):
        _bind_actual_owner(page, world)
        _enter(page)
        page.evaluate("""() => {
            const actual = workspaceClient.fetchImpl;
            window.actualResumeReady = false; window.actualResumeSettled = false;
            workspaceClient.fetchImpl = async (...args) => {
                const response = await actual(...args);
                const packet = args[1] && args[1].body ? JSON.parse(args[1].body) : {};
                if (new URL(String(args[0]), location.href).pathname.endsWith('/mcp/rpc')
                        && packet.params && packet.params.name === 'complaint.run_intake_chat_turn'
                        && packet.params.arguments.interview_action === 'encrypted_resume') {
                    const read = response.json.bind(response);
                    response.json = async () => {
                        const value = await read(); window.actualResumeReady = true;
                        await new Promise(resolve => window.releaseActualResume = resolve); return value;
                    };
                }
                return response;
            };
            window.actualResumeRequest = resumeEncryptedInterview().finally(() => window.actualResumeSettled = true);
        }""")
        page.wait_for_function('window.actualResumeReady === true')
        status = page.evaluate("""async () => {
            const result = await fetch('/api/complaint-workspace/auth/logout', {method:'POST',
                credentials:'same-origin', headers:{'content-type':'application/json',
                    'x-csrf-token':workspaceClient.csrfToken}, body:'{}'});
            return result.status;
        }""")
        assert status == 200
        assert page.evaluate("async () => (await fetch('/api/complaint-workspace/auth/session', {credentials:'same-origin'})).status") == 401
        page.evaluate('window.releaseActualResume()')
        page.wait_for_function('window.actualResumeSettled === true')
        assert page.get_attribute('#encrypted-interview-resume', 'data-resumed') != 'true', 'old resume repainted after the real cookie was revoked'
        assert page.locator('#encrypted-interview-resume-inquiry').text_content() == ''


@pytest.mark.parametrize('frontdoor', ['http', 'mcp', 'rpc'])
def test_actual_same_portal_logout_completes_before_pending_resume_delivery(tmp_path, monkeypatch, frontdoor):
    import asyncio
    from threading import Event
    import httpx
    from applications.complaint_workspace import ComplaintWorkspaceRequestHandlers
    from tests.test_cimp_gui_14 import _composed_headers
    world, cold, app, shared = _actual_owner_resume_world(tmp_path)
    entered, release = Event(), Event()
    actual = ComplaintWorkspaceRequestHandlers._build_session_payload
    expired = []
    def projected(handler, state):
        payload = actual(handler, state)
        if handler.workspace is cold:
            entered.set()
            expired.append(not release.wait(3))
        return payload
    monkeypatch.setattr(ComplaintWorkspaceRequestHandlers, '_build_session_payload', projected)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://testserver') as client:
            login = await client.post('/api/complaint-workspace/auth/login',
                                      json={'credential': 'synthetic-owner-credential'})
            assert login.status_code == 200
            csrf = login.json()['csrf_token']
            args = {'interview_action': 'encrypted_resume'}
            path, body = '/api/complaint-workspace/intake-chat', args
            if frontdoor == 'mcp':
                path, body = '/api/complaint-workspace/mcp/call', {
                    'tool_name': 'complaint.run_intake_chat_turn', 'arguments': args}
            if frontdoor == 'rpc':
                path, body = '/api/complaint-workspace/mcp/rpc', {'jsonrpc': '2.0', 'id': 'synthetic-resume',
                    'method': 'tools/call', 'params': {'name': 'complaint.run_intake_chat_turn', 'arguments': args}}
            pending = asyncio.create_task(client.post(path, headers=_composed_headers(world.case, csrf), json=body))
            try:
                assert await asyncio.to_thread(entered.wait, 5), 'actual encrypted resume did not reach projection'
                logout = await asyncio.wait_for(client.post('/api/complaint-workspace/auth/logout',
                    headers={'x-csrf-token': csrf}, json={}), 2)
                assert logout.status_code == 200
            finally:
                release.set()
            response = await asyncio.wait_for(pending, 10)
            assert expired == [False], 'same-portal logout was blocked until synchronous resume released'
            leaked = shared['pending_inquiry']['question'] in response.text
            assert not leaked, 'pending resume delivered private text after the completed same-portal logout'
    asyncio.run(scenario())


@pytest.mark.parametrize('boundary', ['clear', 'case', 'actor'])
def test_delayed_actual_resume_cannot_repaint_after_page_case_or_actor_boundary(tmp_path, monkeypatch, boundary):
    from tests.test_cimp_gui_15 import _page
    from tests.test_gui16_current_privacy import _bind_actual_owner, _enter
    with _page(tmp_path, monkeypatch, 'typed_owner') as (world, page):
        _bind_actual_owner(page, world)
        _enter(page)
        page.evaluate("""() => {
            const actual = workspaceClient.fetchImpl;
            window.actualResumeReady = false; window.actualResumeSettled = false;
            workspaceClient.fetchImpl = async (...args) => {
                const response = await actual(...args);
                const packet = args[1] && args[1].body ? JSON.parse(args[1].body) : {};
                if (packet.params && packet.params.name === 'complaint.run_intake_chat_turn'
                        && packet.params.arguments.interview_action === 'encrypted_resume') {
                    const read = response.json.bind(response);
                    response.json = async () => {
                        const value = await read(); window.actualResumeReady = true;
                        await new Promise(resolve => window.releaseActualResume = resolve); return value;
                    };
                }
                return response;
            };
            window.actualResumeRequest = resumeEncryptedInterview().finally(() => window.actualResumeSettled = true);
        }""")
        page.wait_for_function('window.actualResumeReady === true')
        if boundary == 'clear':
            page.click('#workspace-clear-private-state')
            page.wait_for_function("document.body.dataset.workspaceHydrated === 'cleared'")
        elif boundary == 'case':
            case = world.actual.second
            page.fill('#workspace-switch-user-id', case.tenant_id)
            page.click('#workspace-switch-user')
            page.wait_for_function("document.body.dataset.workspaceHydrated === 'switched'")
            page.evaluate('value => workspaceClient.setCaseContext(value)', {
                'tenant_id': case.tenant_id, 'case_id': case.case_id,
                'resource_id': case.resource_id, 'revision': case.revision})
        else:
            page.click('#workspace-logout')
            page.wait_for_function("document.body.dataset.workspaceHydrated === 'logged-out'")
            issued = page.evaluate("""async () => {
                const response = await fetch('/api/complaint-workspace/auth/login', {method:'POST',
                    credentials:'same-origin', headers:{'content-type':'application/json'},
                    body:JSON.stringify({credential:'synthetic-stranger-credential'})});
                if (!response.ok) throw new Error('actual_actor_login_failed'); return await response.json();
            }""")
            assert issued['principal_id'] == world.actual.stranger.principal_id
            case = world.actual.foreign
            page.evaluate('data => {workspaceClient.setBrowserSession(data.issued); workspaceClient.setCaseContext(data.case);}',
                {'issued': issued, 'case': {'tenant_id': case.tenant_id, 'case_id': case.case_id,
                    'resource_id': case.resource_id, 'revision': case.revision}})
        page.evaluate('window.releaseActualResume()')
        page.wait_for_function('window.actualResumeSettled === true')
        assert page.get_attribute('#encrypted-interview-resume', 'data-resumed') != 'true'
        assert page.locator('#encrypted-interview-resume-inquiry').text_content() == ''
        assert page.get_attribute('#encrypted-interview-resume', 'data-case-id') in {None, ''}


def test_actual_case_revision_advance_during_resume_keeps_new_head_and_refuses_old_view(tmp_path, monkeypatch):
    import asyncio
    from threading import Event
    import httpx
    from applications.complaint_workspace import ComplaintWorkspaceRequestHandlers
    from tests.test_cimp_gui_14 import _composed_headers
    world, cold, app, shared = _actual_owner_resume_world(tmp_path)
    head = cold.joined_revision_repository(world.case.tenant_id, world.case.case_id) / 'head.cgpe'
    before = head.read_bytes()
    entered, release = Event(), Event()
    actual = ComplaintWorkspaceRequestHandlers._build_session_payload
    def projected(handler, state):
        payload = actual(handler, state)
        if handler.workspace is cold and not entered.is_set():
            entered.set()
            assert release.wait(10), 'actual saved-revision barrier expired'
        return payload
    monkeypatch.setattr(ComplaintWorkspaceRequestHandlers, '_build_session_payload', projected)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://testserver') as client:
            login = await client.post('/api/complaint-workspace/auth/login',
                                      json={'credential':'synthetic-owner-credential'})
            assert login.status_code == 200
            headers = _composed_headers(world.case, login.json()['csrf_token'])
            pending = asyncio.create_task(client.post('/api/complaint-workspace/intake-chat', headers=headers,
                                                     json={'interview_action':'encrypted_resume'}))
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                inquiry = shared['pending_inquiry']
                updated = await asyncio.wait_for(client.post('/api/complaint-workspace/intake-chat', headers=headers,
                    json={'interview_action':'answer', 'message':'2024-03-04', 'question_id':inquiry['inquiry_id'],
                          'expected_question_revision':inquiry['revision']}), 8)
                assert updated.status_code == 200
                saved = head.read_bytes()
                assert saved != before
            finally:
                release.set()
            result = await asyncio.wait_for(pending, 8)
            assert result.status_code == 200
            assert result.json()['encrypted_resume']['code'] == 'revision_conflict'
            assert result.json()['resumed'] is False
            assert head.read_bytes() == saved
    asyncio.run(scenario())


def test_actual_cold_owner_resume_reads_retained_head_after_public_key_rotation(tmp_path):
    from fastapi import FastAPI
    from applications.case_routes import CaseHandlerRegistry, compose_case_routes
    from integrations.private_storage import PrivateArtifactBinding
    from tests.test_cimp_gui_14 import _composed_login, _composed_headers, PASSPHRASE as OWNER_PASSPHRASE
    from tests.test_gui46_private_owner_controls import _world as grant_world, _change
    world = grant_world(tmp_path)
    world.owner_keys.unlock_passphrase(OWNER_PASSPHRASE)
    world.service.unlock_private_keys(passphrase=OWNER_PASSPHRASE)
    binding = PrivateArtifactBinding(tenant_id=world.case.tenant_id, case_id=world.case.case_id,
        principal_id=world.case.tenant_id, artifact_kind='session', revision='session-v1')
    old_id, _ = world.owner_keys.provider().resolve(binding)
    head = world.service.joined_revision_repository(world.case.tenant_id, world.case.case_id) / 'head.cgpe'
    before = head.read_bytes()
    with TestClient(world.review_app, base_url='https://testserver') as client:
        csrf = _composed_login(client)
        current = client.get('/api/complaint-workspace/session', headers=_composed_headers(world.case))
        assert current.status_code == 200
        inquiry = current.json()['session']['shared_interview']['pending_inquiry']
        revoked, _ = _change(world, client, csrf, revoke=True, key='synthetic-resume-owner-cutoff')
        assert revoked.status_code == 200 and revoked.json()['revoked'] is True
    assert world.owner_keys.provider().resolve(binding)[0] != old_id
    assert head.read_bytes() == before  # The saved case still needs its retained historical key.
    cold = ComplaintWorkspaceService(root_dir=tmp_path / 'workspaces' / world.case.case_id)
    assert cold.unlock_private_keys(passphrase=OWNER_PASSPHRASE)['unlocked'] is True
    handlers = CaseHandlerRegistry()
    handlers.bind(world.case, mediator=cold, workspace_service=cold)
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=handlers, include_review=False, include_document=False)
    with TestClient(app, base_url='https://testserver') as client:
        csrf = _composed_login(client)
        response = client.post('/api/complaint-workspace/intake-chat',
            headers=_composed_headers(world.case, csrf), json={'interview_action':'encrypted_resume'})
        assert response.status_code == 200
        assert response.json()['resumed'] is True
        assert response.json()['encrypted_resume']['case']['case_id'] == world.case.case_id
        assert response.json()['encrypted_resume']['pending_inquiry'] == inquiry
    assert world.owner.principal_id != world.case.tenant_id
    assert head.read_bytes() == before
