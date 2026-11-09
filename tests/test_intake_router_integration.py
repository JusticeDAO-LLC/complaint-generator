"""Real canonical intake surfaces with genuine encryption and authored native responses."""
import asyncio
from copy import deepcopy
import importlib
import json
import sys

import pytest

from tests.test_tui_router_trace import terminal_service, _native_types, _result

NARRATIVE = 'José paid Acme on May 4, 2024.'
ANSWER = 'Synthetic Person is the complainant.'


def _native_transport(monkeypatch, *, malformed=False, quota=False):
    import integrations.ipfs_datasets.llm as llm
    import backends.llm_router_backend as backend
    calls=[]
    result_type,observation_type=_native_types()
    def generate(**kw):
        control=json.loads(kw['prompt'] if kw['prompt'].startswith('{') else kw['prompt'].split('\n',1)[1])
        if 'allowed_targets' not in control:
            control=json.loads(control['prompt'].split('\n',1)[1])
        calls.append({'request_id':control['request_id'],'operation':control['operation'],
                      'targets':deepcopy(control['allowed_targets']), 'native_request_id':kw['observation_request_id']})
        assert kw['observation_request_id']==control['request_id']
        assert kw['allow_local_fallback'] is kw['allow_cross_provider_fallback'] is False
        assert kw['grok_cli_cmd']==['grok']
        facts=[];questions=[]
        if control['operation']=='extract_facts':
            if quota:raise RuntimeError('quota exceeded PRIVATE_ERROR_MUST_NOT_LEAK')
            text=control['source_text'];value='paid'
            if value in text:
                ref=next(key for key,meta in control['allowed_targets'].items() if meta['field']=='act')
                start=text.encode().index(value.encode())
                facts=[{'field':'act','value':value,'source_start':start,
                        'source_end':start+(1 if malformed else len(value.encode())),'target_ref':ref}]
        else:
            if control['allowed_targets']:
                ref=next(iter(control['allowed_targets']));meta=control['allowed_targets'][ref]
                questions=[{'question_id':meta['question_id'],'prompt':meta['prompt'],'target_ref':ref}]
        body={'schema_version':'intake_request_v1','operation':control['operation'],
              'request_id':control['request_id'],'questions':questions,'facts':facts}
        return _result(kw,json.dumps(body))
    monkeypatch.setattr(llm,'load_observed_llm_symbols',lambda:(generate,result_type,observation_type))
    monkeypatch.setattr(backend,'load_observed_llm_symbols',lambda:(generate,result_type,observation_type))
    return calls


def _base_service(cli, service, tmp_path):
    workspace=importlib.import_module('applications.complaint_workspace')
    result=workspace.ComplaintWorkspaceService(root_dir=tmp_path/'base-sessions')
    result.initialize_private_keys(protection='passphrase',passphrase='synthetic-base-passphrase')
    result.ensure_private_case_key('synthetic-user','synthetic-user')
    result.set_privacy_policy('synthetic-user','grok')
    return result


@pytest.mark.parametrize('channel',['terminal','package','http','mcp'])
def test_real_shared_surfaces_use_both_typed_roles_and_canonical_graph(terminal_service,tmp_path,monkeypatch,capsys,channel):
    cli,terminal=terminal_service
    service=terminal if channel=='terminal' else _base_service(cli,terminal,tmp_path)
    service.set_privacy_policy('synthetic-user','grok')
    calls=_native_transport(monkeypatch)
    from applications.complaint_workspace import WorkspaceAccess,workspace_access_scope,namespace_filename
    args={'user_id':'synthetic-user','message':NARRATIVE}
    with workspace_access_scope(WorkspaceAccess.authenticated('synthetic-user',case_id='synthetic-user')):
        if channel=='terminal':
            cli.chat_turn(**args);payload=json.loads(capsys.readouterr().out)
        elif channel=='package':
            from complaint_generator.workspace import run_intake_chat_turn
            payload=run_intake_chat_turn(**args,service=service)
        elif channel=='mcp':
            payload=service.call_mcp_tool('complaint.run_intake_chat_turn',args)
        else:
            from applications.complaint_workspace_api import create_complaint_workspace_router,IntakeChatTurnRequest
            router=create_complaint_workspace_router(service)
            endpoint=next(route.endpoint for route in router.routes if route.path=='/api/complaint-workspace/intake-chat')
            payload=asyncio.run(endpoint(IntakeChatTurnRequest(**args)))
    assert {call['operation'] for call in calls}=={'extract_facts','propose_questions'}
    assert len({call['request_id'] for call in calls})==len(calls)
    assert all(call['native_request_id']==call['request_id'] for call in calls)
    session=payload['session'];projection=session['shared_interview']
    assert projection['knowledge_graph']['entities']
    mediator=service._interview_mediators[('synthetic-user','synthetic-user')]
    from complaint_phases import ComplaintPhase
    graph=mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE,'knowledge_graph')
    proposed=[entity for entity in graph.entities.values() if entity.attributes.get('model_field')=='act']
    from complaint_phases.knowledge_graph import assertion_from_provenance
    assert proposed and all(assertion_from_provenance(entity.provenance).is_asserted_user_fact is False
                            and assertion_from_provenance(entity.provenance).record_type == 'model_suggestion' for entity in proposed)
    assert all(item['status']=='available' for item in session['intake_router']['receipts'])
    assert not session['intake_router']['errors']
    assert all(item['intake_complete'] is False for item in session['intake_router']['receipts'])
    assert 'model_relationship_proposals_unsupported' in session['intake_router']['limitations']
    if channel=='terminal':
        traces=session['router_trace']['receipts']
        assert len(traces)==len(calls)
        assert len({item['router_receipt']['native_invocation_id'] for item in traces})==len(calls)
    serialized=json.dumps(session['intake_router'])
    assert NARRATIVE not in serialized and 'José' not in serialized
    encrypted=service._session_dir/namespace_filename('synthetic-user')
    assert encrypted.read_bytes().startswith(b'CGPE') and NARRATIVE.encode() not in encrypted.read_bytes()


def test_failed_extraction_keeps_user_answer_and_unavailable_status_on_cold_resume(terminal_service,tmp_path,monkeypatch):
    cli,terminal=terminal_service
    service=_base_service(cli,terminal,tmp_path)
    calls=_native_transport(monkeypatch,quota=True)
    payload=service.run_intake_chat_turn('synthetic-user',message=NARRATIVE)
    assert payload['session']['intake_router']['errors']['extract_facts']=='quota'
    current=payload['interview']
    assert current['status']!='complete' and current['error']['resumable'] is True
    assert current['inquiry']
    answered=service.run_intake_chat_turn('synthetic-user',message=ANSWER,
        question_id=current['inquiry']['inquiry_id'],expected_question_revision=current['expected_question_revision'])
    history=answered['session']['shared_interview']['denoiser_history']
    assert sum(entry.get('answer')==ANSWER for entry in history)==1
    assert answered['session']['intake_router']['errors']['extract_facts']=='quota'
    before=len(calls)
    workspace=importlib.import_module('applications.complaint_workspace')
    fresh=workspace.ComplaintWorkspaceService(root_dir=service._session_dir)
    fresh.unlock_private_keys(passphrase='synthetic-base-passphrase')
    resumed=fresh.run_intake_chat_turn('synthetic-user',interview_action='resume')
    assert len(calls)==before
    assert resumed['session']['shared_interview']['denoiser_history']==history
    assert resumed['interview']['status']!='complete'
    assert resumed['interview']['error']['router_failures']['extract_facts']=='quota'
    assert 'PRIVATE_ERROR_MUST_NOT_LEAK' not in json.dumps(resumed)


def test_malformed_extraction_adds_no_provider_entity_or_false_completion(terminal_service,tmp_path,monkeypatch):
    cli,terminal=terminal_service
    service=_base_service(cli,terminal,tmp_path)
    _native_transport(monkeypatch,malformed=True)
    payload=service.run_intake_chat_turn('synthetic-user',message=NARRATIVE)
    mediator=service._interview_mediators[('synthetic-user','synthetic-user')]
    from complaint_phases import ComplaintPhase
    graph=mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE,'knowledge_graph')
    assert not [entity for entity in graph.entities.values() if entity.attributes.get('model_field')=='act']
    assert payload['session']['intake_router']['errors']['extract_facts']=='malformed_output'
    assert payload['interview']['status']!='complete'
    assert payload['interview']['readiness']['ready_to_advance'] is False
