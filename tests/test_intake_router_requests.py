"""Bounded typed intake exchanges; authored transports are never live evidence."""
import json
import time
import uuid

import pytest

import integrations.ipfs_datasets.llm as llm
import backends.llm_router_backend as backend_module
from backends.llm_router_backend import LLMRouterBackend, ProviderRouteError
from integrations.ipfs_accelerate.routers import PINNED_GROK_MODEL, PINNED_GROK_PROVIDER
from mediator.mediator import Mediator
from complaint_phases import ComplaintPhase, KnowledgeGraph
from tests.test_tui_router_trace import _native_types, _result

SECRET = 'PRIVATE_NARRATIVE_SHOULD_NOT_LEAK'
SOURCE = 'José paid'
TARGETS = ('party.complainant',)


def _context():
    return llm.build_complaint_privacy_context(llm.privacy_policy_for_mode('synthetic','synthetic','grok'),
        user_id='synthetic',case_id='synthetic',data_class='raw_intake')


def _body(request_id, operation='extract_facts', questions=None, facts=None):
    return json.dumps({'schema_version':'intake_request_v1','operation':operation,'request_id':request_id,
                       'questions':questions or [],'facts':facts or []},separators=(',',':'))


def _fact(target='party.complainant'):
    return {'field':'party','value':'José','source_start':0,'source_end':len('José'.encode()),'target_ref':target}


def _backend(**overrides):
    options = dict(retry_max_attempts=3,retry_backoff_base_s=5,retry_backoff_max_s=5,
                   retry_jitter_s=0,timeout_seconds=.25,intake_operation='extract_facts')
    options.update(overrides)
    return LLMRouterBackend('intake-router',provider=PINNED_GROK_PROVIDER,model=PINNED_GROK_MODEL,**options)


def _patch_native(monkeypatch, fn):
    result_type, observation_type = _native_types()
    monkeypatch.setattr(llm,'load_observed_llm_symbols',lambda: (fn,result_type,observation_type))
    monkeypatch.setattr(backend_module,'load_observed_llm_symbols',lambda: (fn,result_type,observation_type))


def _call(backend, text=SECRET, **kwargs):
    return backend(text,intake_source_text=SOURCE,intake_target_refs=TARGETS,
                   complaint_privacy_context=_context(),**kwargs)


def _assert_pinned(call):
    assert call['provider']==PINNED_GROK_PROVIDER and call['model_name']==PINNED_GROK_MODEL
    assert call['allow_local_fallback'] is call['allow_cross_provider_fallback'] is False
    assert call['grok_cli_cmd']==['grok'] and call['grok_tools']=='read_file'
    assert set(call['grok_disallowed_tools'].split(','))=={'read_file','search_tool','use_tool'}


def _mediator(tmp_path, backend):
    mediator = Mediator([backend],evidence_db_path=str(tmp_path/'e.db'),
        legal_authority_db_path=str(tmp_path/'l.db'),claim_support_db_path=str(tmp_path/'c.db'))
    mediator.workflow_actions.bind_interview_privacy(llm.privacy_policy_for_mode('synthetic','synthetic','grok'),
        user_id='synthetic',case_id='synthetic')
    mediator.begin_intake_router_action(owner_id='synthetic',case_id='synthetic',session_id=uuid.uuid4().hex,revision=0)
    return mediator


def test_response_format_matches_native_strict_shape():
    fmt=llm.intake_request_response_format()
    assert set(fmt)=={'type','json_schema'}
    assert set(fmt['json_schema'])=={'name','strict','schema'} and fmt['json_schema']['strict'] is True


def test_quota_failure_dispatches_pinned_model_once(monkeypatch):
    calls=[]
    def native(**kw):
        calls.append(kw);raise RuntimeError('quota exceeded '+SECRET)
    _patch_native(monkeypatch,native)
    backend=_backend()
    with pytest.raises(ProviderRouteError) as caught:_call(backend)
    assert caught.value.payload['error_code']=='quota' and caught.value.payload['status']=='quota'
    assert caught.value.payload['intake_complete'] is False and len(calls)==1
    _assert_pinned(calls[0])
    assert SECRET not in json.dumps(caught.value.payload)


def test_total_retry_budget_does_not_open_another_model(monkeypatch):
    calls=[]
    def native(**kw):
        calls.append(kw);raise RuntimeError('temporarily unavailable')
    _patch_native(monkeypatch,native)
    started=time.monotonic()
    with pytest.raises(ProviderRouteError) as caught:_call(_backend())
    assert caught.value.payload['error_code'] in {'provider_unavailable','timeout'}
    assert len(calls)==1 and time.monotonic()-started<1
    _assert_pinned(calls[0])


def test_cancel_unwinds_provider_cleanup_without_background_worker(monkeypatch):
    backend=_backend(timeout_seconds=1)
    cleanup=[]
    monkeypatch.setattr(backend_module.threading,'Thread',lambda *a,**k:pytest.fail('background provider thread'))
    def native(**kw):
        try:
            backend.cancel()
            kw['grok_progress_callback']({})
            pytest.fail('cancel callback returned')
        finally:cleanup.append('owned transport closed')
    _patch_native(monkeypatch,native)
    with pytest.raises(ProviderRouteError) as caught:_call(backend)
    assert caught.value.payload['error_code']=='cancelled'
    assert cleanup==['owned transport closed']
    assert SECRET not in json.dumps(caught.value.payload)


def test_schema_and_span_rejection_leaves_canonical_graph_unchanged(tmp_path,monkeypatch):
    raw=['not json']
    def native(**kw):return _result(kw,raw[0])
    _patch_native(monkeypatch,native)
    mediator=_mediator(tmp_path,_backend(timeout_seconds=2))
    graph=KnowledgeGraph()
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE,'knowledge_graph',graph)
    before=graph.to_dict()
    for value in ['not json','```json\n{}\n```','{"schema_version":"intake_request_v1","schema_version":"intake_request_v1"}']:
        raw[0]=value
        assert mediator.request_intake_candidates('extract_facts',source_text=SOURCE,
            targets={'party.complainant':{'field':'party'}}) is None
        assert graph.to_dict()==before
    with pytest.raises(llm.IntakeContractError):
        llm.parse_intake_request(_body(uuid.uuid4().hex,facts=[{**_fact(),'source_end':1}]),
            request_id=uuid.uuid4().hex,operation='extract_facts',source_text=SOURCE,allowed_target_refs=TARGETS)


def test_valid_span_is_model_candidate_and_empty_is_not_completion(tmp_path,monkeypatch):
    def native(**kw):return _result(kw,_body(kw['observation_request_id'],facts=[_fact('candidate:0')]))
    _patch_native(monkeypatch,native)
    mediator=_mediator(tmp_path,_backend(timeout_seconds=2))
    graph=mediator.kg_builder.build_from_text(SOURCE)
    candidates=[entity for entity in graph.entities.values() if entity.name=='José']
    from complaint_phases.knowledge_graph import assertion_from_provenance
    assert candidates and all(assertion_from_provenance(entity.provenance).is_asserted_user_fact is False
                              and assertion_from_provenance(entity.provenance).record_type == 'model_suggestion' for entity in candidates)
    assert mediator.intake_router_snapshot()['receipts'][-1]['intake_complete'] is False
    assert not hasattr(mediator,'intake_model_suggestions')


def test_redacted_trace_and_fresh_request_ids_propagate(tmp_path,monkeypatch):
    calls=[]
    def native(**kw):
        calls.append(kw)
        prompt=json.loads(kw['prompt'] if kw['prompt'].startswith('{') else kw['prompt'].split('\n',1)[1])
        if 'allowed_targets' not in prompt:
            prompt=json.loads(prompt['prompt'].split('\n',1)[1])
        return _result(kw,_body(prompt['request_id'],operation=prompt['operation']))
    _patch_native(monkeypatch,native)
    backend=_backend(timeout_seconds=2)
    mediator=_mediator(tmp_path,backend)
    for _ in range(2):
        assert mediator.request_intake_candidates('extract_facts',source_text=SOURCE,
            targets={'party.complainant':{'field':'party'}})['facts']==[]
    assert len(calls)==2
    assert len({call['observation_request_id'] for call in calls})==2
    assert len({item['request_id'] for item in backend.task_receipts})==2
    assert all(item['native_invocation_id'] for item in backend.task_receipts)
    assert SECRET not in json.dumps(mediator.state.log+backend.task_receipts)
    assert 'router-test-1' not in json.dumps(backend.last_result_metadata)


def test_unbound_legacy_application_cannot_claim_canonical_effects(tmp_path):
    mediator=_mediator(tmp_path,lambda *a,**k:'unused')
    graph=KnowledgeGraph();mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE,'knowledge_graph',graph)
    before=graph.to_dict()
    outcome=mediator.apply_intake_router_output(_body(uuid.uuid4().hex,facts=[_fact()]),
        operation='extract_facts',source_text=SOURCE,request_id=uuid.uuid4().hex)
    assert outcome['applied'] is outcome['graph_changed'] is outcome['intake_complete'] is False
    assert outcome['error_code']=='binding_missing' and graph.to_dict()==before
    assert not hasattr(mediator,'intake_model_suggestions')


def test_exchange_failure_does_not_change_canonical_graph(tmp_path,monkeypatch):
    def native(**kw):raise RuntimeError('unavailable '+SECRET)
    _patch_native(monkeypatch,native)
    mediator=_mediator(tmp_path,_backend(retry_max_attempts=1,timeout_seconds=1))
    graph=KnowledgeGraph();mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE,'knowledge_graph',graph)
    before=graph.to_dict()
    assert mediator.request_intake_candidates('extract_facts',source_text=SOURCE,
        targets={'party.complainant':{'field':'party'}}) is None
    assert graph.to_dict()==before
    assert mediator.intake_router_snapshot()['errors']['extract_facts']=='provider_unavailable'
    assert SECRET not in json.dumps(mediator.state.log)


@pytest.mark.parametrize('message,expected',[('quota exceeded','quota'),('structured output invalid','malformed_output')])
def test_distinct_failure_kinds(monkeypatch,message,expected):
    def native(**kw):raise RuntimeError(message)
    _patch_native(monkeypatch,native)
    with pytest.raises(ProviderRouteError) as caught:_call(_backend(timeout_seconds=1,retry_max_attempts=1))
    assert caught.value.payload['error_code']==expected
