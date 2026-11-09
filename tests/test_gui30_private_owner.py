"""Definition/correspondence replay must use the current encrypted case source."""
from copy import deepcopy
from fastapi.testclient import TestClient
import pytest
from applications.complaint_workspace import ComplaintWorkspaceService
from tests.test_gui25_26_private_owner_http import _world, _login, _headers, _start_case, _choose, _body
from tests.test_cimp_gui_30 import LEGAL_SOURCE, _bundle, _populations
from applications.legal_analysis_api import definition_wire, definition_inputs_wire

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _source(client, world, csrf):
    _start_case(client, world, csrf)
    generation = _choose(client, world, csrf)
    request = _body(generation)
    request['local_rows'] = {'state_statute': [{'text': LEGAL_SOURCE,
        'citation': 'fixture://gui30-owned-source', 'uri': 'fixture://gui30-owned-source',
        'corpus_version': 'synthetic-v1', 'jurisdiction': 'OR', 'effective_date': '2024-01-01'}],
        'state_administrative_rule': []}
    got = client.post('/api/legal-research/' + world.case.case_id, headers=_headers(world, csrf), json=request)
    assert got.status_code == 200
    source = next(row for row in got.json()['source_version_receipts'] if row['kind'] == 'candidate')
    reviewed = client.post('/api/legal-research/' + world.case.case_id + '/admissions', headers=_headers(world, csrf),
        json={'decision':'admit','source_passage':source['source_passage'],'authority_identity':source['authority_identity'],
            'jurisdiction':source['jurisdiction'],'effective_date':source['effective_date'],'version':source['version'],
            'content_hash':source['content_hash'],'applicability':source['stated_applicability'],
            'treatment_state':source['treatment_state'],'exceptions':source['exceptions'],'operation_id':'synthetic30-source-review'})
    assert reviewed.status_code == 200 and reviewed.json()['source_status'] == 'source_admitted'
    return source


def _request(client, world, source):
    state = client.get('/api/legal-analysis/' + world.case.case_id + '/definition-correspondence', headers=_headers(world))
    assert state.status_code == 200
    return {'request_id':'synthetic30-definition-replay','source_content_hash':source['content_hash'],
        'expected_private_revision':state.json()['private_revision'],'expected_session_revision':state.json()['session_revision'],
        'declared_populations':_populations(), 'owner_inputs':definition_inputs_wire(_bundle())}


def test_definition_cache_cannot_bypass_real_case_key_lock(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url='https://testserver') as client:
        csrf = _login(client)
        _start_case(client, world, csrf)
        world.service.lock_private_keys()
        result = client.get('/api/legal-analysis/' + world.case.case_id + '/definition-correspondence', headers=_headers(world))
        assert result.status_code == 503
        assert result.json()['error'] == 'unlock_needed'


def test_definition_http_rejects_caller_source_or_context_as_case_authority(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url='https://testserver') as client:
        csrf = _login(client)
        _start_case(client, world, csrf)
        current = client.get('/api/legal-analysis/' + world.case.case_id + '/definition-correspondence', headers=_headers(world)).json()
        result = client.post('/api/legal-analysis/' + world.case.case_id + '/definition-correspondence',
            headers=_headers(world, csrf), json={'expected_private_revision':current['private_revision'],
                'expected_session_revision':current['session_revision'], 'request_id':'synthetic30-forged-source','source_text':LEGAL_SOURCE,
                'declared_populations':_populations()})
        assert result.status_code == 422
        assert result.json()['error'] == 'client_case_authority'


def test_current_definition_owner_replay_persists_under_actual_reviewed_source_and_cold_key(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url='https://testserver') as client:
        csrf = _login(client)
        source = _source(client, world, csrf)
        request = _request(client, world, source)
        result = client.post('/api/legal-analysis/' + world.case.case_id + '/definition-correspondence', headers=_headers(world, csrf), json=request)
        assert result.status_code == 200
        payload = result.json()
        assert payload['status'] == 'bound'
        assert payload['source_binding']['content_hash'] == source['content_hash']
        assert payload['authorizes_law'] is False and payload['authorizes_proof'] is False
        assert payload['executed_proof'] is False and payload['proof'] is False
        assert all(row['genuine_current_owner_receipt'] is True for row in payload['owners'].values())
    world.service.lock_private_keys()
    fresh = ComplaintWorkspaceService(root_dir=world.service_root)
    assert fresh.unlock_private_keys(passphrase='synthetic-password')['unlocked'] is True
    with TestClient(world.app_for(world.mediator, fresh), base_url='https://testserver') as client:
        _login(client)
        result = client.get('/api/legal-analysis/' + world.case.case_id + '/definition-correspondence', headers=_headers(world))
        assert result.status_code == 200 and result.json()['status'] == 'bound'
        assert result.json()['source_current'] is True
        assert result.json()['source_binding'] == payload['source_binding']
        assert result.json()['authorizes_law'] is False and result.json()['executed_proof'] is False
