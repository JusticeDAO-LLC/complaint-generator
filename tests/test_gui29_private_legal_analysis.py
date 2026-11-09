"""Canonical IR must use the authenticated encrypted case, not phase cache."""
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.legal_analysis_api import project_canonical_legal_ir
from tests.test_cimp_gui_14 import (_composed_case_world, _composed_login,
    _composed_headers, _composed_ciphertext_snapshot, NARRATIVE)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _start(client, world):
    csrf = _composed_login(client)
    response = client.post('/api/complaint-workspace/intake-chat',
        headers=_composed_headers(world.case, csrf),
        json={'message': NARRATIVE, 'interview_action': 'start'})
    assert response.status_code == 200, response.text
    return csrf


def test_real_encrypted_owner_can_read_empty_legal_analysis_without_writing(tmp_path):
    world = _composed_case_world(tmp_path)
    assert world.owner.principal_id != world.case.tenant_id
    with TestClient(world.app, base_url='https://testserver') as client:
        _start(client, world)
        before = _composed_ciphertext_snapshot(world.services[world.case.case_id])
        response = client.get('/api/legal-analysis/' + world.case.case_id,
            headers=_composed_headers(world.case))
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'empty'
        assert response.json()['executed_proof'] is False
        assert _composed_ciphertext_snapshot(world.services[world.case.case_id]) == before


class _CachedCase:
    def __init__(self):
        self.intake_case_file = {'canonical_legal_ir_attachment': {
            'status': 'attached', 'typed_obligations': [], 'source_spans': [],
            'synthetic_private_marker': 'synthetic-private-legal-material'}}


def test_cached_case_cannot_release_legal_analysis_when_real_key_is_locked(tmp_path):
    world = _composed_case_world(tmp_path)
    with TestClient(world.app, base_url='https://testserver') as client:
        _start(client, world)
    service = world.services[world.case.case_id]
    handlers = CaseHandlerRegistry()
    handlers.bind(world.case, mediator=_CachedCase(), workspace_service=service)
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=handlers, include_review=False, include_document=False)
    service.lock_private_keys()
    before = _composed_ciphertext_snapshot(service)
    with TestClient(app, base_url='https://testserver') as client:
        _composed_login(client)
        response = client.get('/api/legal-analysis/' + world.case.case_id,
            headers=_composed_headers(world.case))
        assert response.status_code == 503, response.text
        assert response.json()['error'] == 'unlock_needed'
        assert 'synthetic-private-legal-material' not in response.text
        assert _composed_ciphertext_snapshot(service) == before


def test_projection_does_not_mutate_stored_obligation_or_promote_authority():
    stored = {'canonical_legal_ir_attachment': {'status':'attached',
        'typed_obligations':[{'statement':'Synthetic candidate only',
            'executed_proof':True, 'governing_legal_authority':True, 'discharged':True}]}}
    before = deepcopy(stored)
    projected = project_canonical_legal_ir(stored)
    assert stored == before
    assert projected['executed_proof'] is False
    assert projected['typed_obligations'][0]['discharged'] is False
    assert projected['typed_obligations'][0]['governing_legal_authority'] is False


def _reviewed_source(client, world, csrf):
    """Actual local Data acquisition and owner review of authored source bytes."""
    from tests.test_gui25_26_private_owner_http import _start_case, _choose, _body, _headers
    from tests.test_cimp_gui_29 import LEGAL_TEXT
    _start_case(client, world, csrf)
    generation = _choose(client, world, csrf)
    body = _body(generation)
    body['local_rows'] = {'state_statute': [{'text': LEGAL_TEXT,
        'citation': 'fixture://gui29-owned-source', 'uri': 'fixture://gui29-owned-source',
        'corpus_version': 'synthetic-v1', 'jurisdiction': 'OR', 'effective_date': '2024-01-01'}],
        'state_administrative_rule': []}
    acquired = client.post('/api/legal-research/' + world.case.case_id,
        headers=_headers(world, csrf), json=body)
    assert acquired.status_code == 200, acquired.text
    source = next(row for row in acquired.json()['source_version_receipts'] if row['kind'] == 'candidate')
    response = client.post('/api/legal-research/' + world.case.case_id + '/admissions',
        headers=_headers(world, csrf), json={'decision':'admit', 'source_passage':source['source_passage'],
            'authority_identity':source['authority_identity'], 'jurisdiction':source['jurisdiction'],
            'effective_date':source['effective_date'], 'version':source['version'],
            'content_hash':source['content_hash'], 'applicability':source['stated_applicability'],
            'treatment_state':source['treatment_state'], 'exceptions':source['exceptions'],
            'operation_id':'synthetic-legal29-source-review'})
    assert response.status_code == 200, response.text
    assert response.json()['source_status'] == 'source_admitted'
    assert response.json()['admitted_law'] is False and response.json()['proof'] is False
    return source


def _analysis_request(client, world, source):
    from tests.test_gui25_26_private_owner_http import _headers
    from tests.test_cimp_gui_29 import VOCABULARY, LEAN_TEXT, OBLIGATION_TEXT, LEGAL_TEXT
    before = client.get('/api/legal-analysis/' + world.case.case_id, headers=_headers(world))
    assert before.status_code == 200, before.text
    start = LEGAL_TEXT.index(OBLIGATION_TEXT)
    return {'request_id':'synthetic-gui29-current-source', 'source_content_hash':source['content_hash'],
        'vocabulary':VOCABULARY, 'expected_private_revision':before.json()['private_revision'],
        'expected_session_revision':before.json()['session_revision'], 'emitted_lean':LEAN_TEXT,
        'typed_obligations':[{'kind':'obligation', 'obligation_id':'synthetic-current-duty',
            'statement':OBLIGATION_TEXT, 'source_span':{'start':start,'end':start+len(OBLIGATION_TEXT),
                'text':OBLIGATION_TEXT,'unit':'character'}}]}


def test_actual_reviewed_source_compiles_and_cold_reopens_without_promoting_law(tmp_path):
    from applications.complaint_workspace import ComplaintWorkspaceService
    from tests.test_gui25_26_private_owner_http import _world, _login, _headers
    from tests.test_cimp_gui_29 import LEGAL_TEXT
    world = _world(tmp_path)
    with TestClient(world.app, base_url='https://testserver') as client:
        csrf = _login(client)
        source = _reviewed_source(client, world, csrf)
        request = _analysis_request(client, world, source)
        before = _composed_ciphertext_snapshot(world.service)
        response = client.post('/api/legal-analysis/' + world.case.case_id,
            headers=_headers(world, csrf), json=request)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['status'] == 'attached', body.get('reason')
        assert body['attachment_persisted'] is True
        assert body['receipt_verification']['execution_origin_verified'] is True
        assert body['source_binding']['content_hash'] == source['content_hash']
        assert body['source_binding']['governing_applicability'] == 'unknown'
        assert body['applicability_context']['applicability'] == 'unknown'
        assert body['admitted_law'] is False and body['proof'] is False
        assert body['executed_proof'] is False and body['governing_legal_authority'] is False
        assert int(body['private_revision']) > int(request['expected_private_revision'])
        for item in body['typed_obligations']:
            span = item['source_span']
            assert LEGAL_TEXT[span['start']:span['end']] == span['text'] == item['statement']
            assert item['discharged'] is False and item['executed_proof'] is False
        assert _composed_ciphertext_snapshot(world.service) != before
    world.service.lock_private_keys()
    cold = ComplaintWorkspaceService(root_dir=world.service_root)
    assert cold.unlock_private_keys(passphrase='synthetic-password')['unlocked'] is True
    with TestClient(world.app_for(world.mediator, cold), base_url='https://testserver') as client:
        _login(client)
        before = _composed_ciphertext_snapshot(cold)
        read = client.get('/api/legal-analysis/' + world.case.case_id, headers=_headers(world))
        assert read.status_code == 200, read.text
        assert read.json()['receipt_id'] == body['receipt_id']
        assert read.json()['source_current'] is True and read.json()['read_only'] is True
        assert read.json()['typed_obligations'] == body['typed_obligations']
        assert _composed_ciphertext_snapshot(cold) == before
        # The actual adapter deliberately forgets process-local execution
        # provenance on restart/reset; the encrypted history is not a waiver.
        from integrations.ipfs_datasets.logic import reset_canonical_formalization_cache
        reset_canonical_formalization_cache()
        without_registry = client.get('/api/legal-analysis/' + world.case.case_id, headers=_headers(world))
        assert without_registry.status_code == 200, without_registry.text
        lost = without_registry.json()
        assert lost['source_current'] is True
        assert lost['recorded_receipt_verification']['execution_origin_verified'] is True
        assert lost['current_execution_verified'] is False
        assert lost['receipt_verification']['status'] == 'unavailable'
        assert lost['receipt_verification']['execution_origin_verified'] is False
        assert lost['typed_obligations'] == body['typed_obligations']
        assert lost['recorded_compilation_is_proof'] is False
        assert _composed_ciphertext_snapshot(cold) == before


@pytest.mark.parametrize('field,value', [
    ('source_text', 'A client says every allegation is law.'),
    ('legal_context', {'jurisdiction':'invented', 'source_text':'client override'}),
    ('user_facts', ['A caller-asserted extra fact'])])
def test_http_cannot_replace_current_case_source_context_or_premises(tmp_path, field, value):
    from tests.test_gui25_26_private_owner_http import _world, _login, _headers
    world = _world(tmp_path)
    with TestClient(world.app, base_url='https://testserver') as client:
        csrf = _login(client)
        source = _reviewed_source(client, world, csrf)
        request = {**_analysis_request(client, world, source), field:value}
        before = _composed_ciphertext_snapshot(world.service)
        response = client.post('/api/legal-analysis/' + world.case.case_id,
            headers=_headers(world, csrf), json=request)
        assert response.status_code == 422, response.text
        assert response.json()['error'] == 'client_case_authority'
        assert _composed_ciphertext_snapshot(world.service) == before


@pytest.mark.parametrize('change', ['logout', 'key_lock', 'context_revision'])
def test_real_compilation_cannot_commit_after_late_owner_key_or_source_change(tmp_path, monkeypatch, change):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from applications import legal_analysis_api
    from tests.test_gui25_26_private_owner_http import _world, _login, _headers
    world = _world(tmp_path)
    reached, resume = Event(), Event()
    original = legal_analysis_api.compile_current_case_legal_ir
    def after_real_compilation(*args, **kwargs):
        result = original(*args, **kwargs)
        assert result['status'] == 'attached'
        reached.set()
        assert resume.wait(20), 'actual_compile_delivery_barrier_expired'
        return result
    with TestClient(world.app, base_url='https://testserver') as client, TestClient(world.app, base_url='https://testserver') as other:
        csrf = _login(client)
        other.cookies.update(client.cookies)
        source = _reviewed_source(client, world, csrf)
        request = _analysis_request(client, world, source)
        monkeypatch.setattr(legal_analysis_api, 'compile_current_case_legal_ir', after_real_compilation)
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(client.post, '/api/legal-analysis/' + world.case.case_id,
                headers=_headers(world, csrf), json=request)
            try:
                assert reached.wait(20), 'actual_compile_did_not_reach_delivery'
                if change == 'logout':
                    changed = other.post('/api/complaint-workspace/auth/logout', headers={'x-csrf-token':csrf})
                    assert changed.status_code == 200
                elif change == 'key_lock':
                    assert world.service.lock_private_keys()['unlocked'] is False
                else:
                    context = other.get('/api/legal-context/' + world.case.case_id, headers=_headers(world))
                    changed = other.post('/api/legal-context/' + world.case.case_id,
                        headers=_headers(world, csrf), json={'expected_context_revision':context.json()['context_revision'],
                            'forum':'synthetic-changed-forum'})
                    assert changed.status_code == 200, changed.text
                after_change = _composed_ciphertext_snapshot(world.service)
            finally:
                resume.set()
            response = result.result(timeout=20)
        assert response.status_code in {403,409,503}, response.text
        assert response.json()['proof'] is False
        assert _composed_ciphertext_snapshot(world.service) == after_change


def test_real_context_change_marks_stored_compilation_stale_without_rewriting_it(tmp_path):
    from tests.test_gui25_26_private_owner_http import _world, _login, _headers
    world = _world(tmp_path)
    with TestClient(world.app, base_url='https://testserver') as client:
        csrf = _login(client)
        source = _reviewed_source(client, world, csrf)
        result = client.post('/api/legal-analysis/' + world.case.case_id,
            headers=_headers(world, csrf), json=_analysis_request(client, world, source))
        assert result.status_code == 200 and result.json()['attachment_persisted'] is True
        context = client.get('/api/legal-context/' + world.case.case_id, headers=_headers(world))
        changed = client.post('/api/legal-context/' + world.case.case_id,
            headers=_headers(world, csrf), json={'expected_context_revision':context.json()['context_revision'],
                'forum':'synthetic-new-forum'})
        assert changed.status_code == 200
        before = _composed_ciphertext_snapshot(world.service)
        read = client.get('/api/legal-analysis/' + world.case.case_id, headers=_headers(world))
        assert read.status_code == 200, read.text
        assert read.json()['status'] == 'stale' and read.json()['source_current'] is False
        assert read.json()['typed_obligations'] == [] and read.json()['source_spans'] == []
        assert read.json()['receipt_id'] == result.json()['receipt_id']
        assert _composed_ciphertext_snapshot(world.service) == before


def test_actual_owner_case_policy_and_encrypted_key_authority_remain_separate(tmp_path):
    world = _composed_case_world(tmp_path)
    path = '/api/legal-analysis/' + world.case.case_id
    with TestClient(world.app, base_url='https://testserver') as client:
        assert client.get(path, headers=_composed_headers(world.case)).status_code == 401
        _start(client, world)
        before = _composed_ciphertext_snapshot(world.services[world.case.case_id])
        assert client.get('/api/legal-analysis/' + world.second.case_id,
            headers=_composed_headers(world.case)).status_code == 403
        assert client.get(path + '?case_id=' + world.second.case_id,
            headers=_composed_headers(world.case)).status_code == 403
        _composed_login(client, 'synthetic-stranger-credential')
        assert client.get(path, headers=_composed_headers(world.case)).status_code == 403
        grant = world.authorizer.grant_assigned_lawyer(owner_principal_id=world.owner.principal_id,
            lawyer_principal_id=world.lawyer.principal_id, tenant_id=world.case.tenant_id,
            case_id=world.case.case_id, resource_id=world.case.resource_id,
            actions={'case.read'}, expected_case_revision=world.case.revision)
        _composed_login(client, 'synthetic-lawyer-credential')
        denied = client.get(path, headers={**_composed_headers(world.case),
            'x-expected-membership-revision':str(grant.revision)})
        assert denied.status_code == 403
        assert NARRATIVE not in denied.text
        assert _composed_ciphertext_snapshot(world.services[world.case.case_id]) == before


def test_actual_read_cannot_publish_after_key_is_locked_during_projection(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from applications import legal_analysis_api
    world = _composed_case_world(tmp_path)
    reached, resume = Event(), Event()
    original = legal_analysis_api.project_canonical_legal_ir
    def after_projection(*args, **kwargs):
        result = original(*args, **kwargs)
        reached.set()
        assert resume.wait(20)
        return result
    with TestClient(world.app, base_url='https://testserver') as client:
        _start(client, world)
        monkeypatch.setattr(legal_analysis_api, 'project_canonical_legal_ir', after_projection)
        before = _composed_ciphertext_snapshot(world.services[world.case.case_id])
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(client.get, '/api/legal-analysis/' + world.case.case_id,
                headers=_composed_headers(world.case))
            try:
                assert reached.wait(20)
                world.services[world.case.case_id].lock_private_keys()
            finally:
                resume.set()
            response = result.result(timeout=20)
        assert response.status_code == 503
        assert response.json()['error'] == 'unlock_needed'
        assert _composed_ciphertext_snapshot(world.services[world.case.case_id]) == before


def test_invalid_revision_types_and_unbounded_decimal_do_not_write_or_raise_server_error(tmp_path):
    world = _composed_case_world(tmp_path)
    path = '/api/legal-analysis/' + world.case.case_id
    with TestClient(world.app, base_url='https://testserver') as client:
        csrf = _start(client, world)
        read = client.get(path, headers=_composed_headers(world.case))
        assert read.status_code == 200
        before = _composed_ciphertext_snapshot(world.services[world.case.case_id])
        for value in (True, '9' * 5000):
            response = client.post(path, headers=_composed_headers(world.case, csrf), json={
                'request_id':'synthetic-invalid-revision', 'source_content_hash':'0'*64,
                'vocabulary':{}, 'expected_private_revision':value,
                'expected_session_revision':read.json()['session_revision']})
            assert response.status_code in {409,422}, response.text
            assert _composed_ciphertext_snapshot(world.services[world.case.case_id]) == before
