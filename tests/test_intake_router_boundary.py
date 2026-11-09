"""Synthetic typed-intake provider boundary; no daemon, network or live provider."""
import json
import subprocess
import uuid
from types import SimpleNamespace

import pytest

import backends.llm_router_backend as backend_module
import integrations.ipfs_datasets.llm as llm
from backends.llm_router_backend import LLMRouterBackend
from integrations.ipfs_datasets.llm import build_complaint_privacy_context, privacy_policy_for_mode
from ipfs_accelerate_py.cli_runtime.grok_invocation_observation import ObservedTextGeneration, GrokInvocationObservation

SECRET = 'SYNTHETIC_PRIVATE_TOKEN_NO_ECHO'
SOURCE = 'José paid'
TARGETS = ('party.complainant',)


def _context(mode='grok'):
    return build_complaint_privacy_context(privacy_policy_for_mode('synthetic', 'synthetic', mode),
        user_id='synthetic', case_id='synthetic', data_class='raw_intake')


def _body(request_id):
    return json.dumps({'schema_version': 'intake_request_v1', 'operation': 'extract_facts',
        'request_id': request_id, 'questions': [], 'facts': [{'field': 'party', 'value': 'José',
        'source_start': 0, 'source_end': 5, 'target_ref': 'party.complainant'}]})


def _fake_boundary(monkeypatch, request_id):
    ordinary, observed = [], []
    def plain(**kwargs):
        ordinary.append(kwargs)
        return _body(request_id)
    def generate(**kwargs):
        observed.append(kwargs)
        obs = GrokInvocationObservation(invocation_id=uuid.uuid4().hex,
            request_id=kwargs['observation_request_id'], native_dispatch_count=1,
            selected_provider_name='grok_cli', selected_model_name='grok-4.7',
            provider_reported_model='grok-4.7', wire_model_observed=True, process_returncode=0,
            stream_complete=True, evidence_class='native_final_end_model_usage')
        return ObservedTextGeneration(text=_body(kwargs['observation_request_id']), observation=obs)
    monkeypatch.setattr(llm, 'generate_text', plain)
    monkeypatch.setattr(llm, 'get_last_generation_trace', lambda: {
        'effective_provider_name': 'grok_cli', 'effective_model_name': 'grok-4.7', 'router_version': SECRET})
    monkeypatch.setattr(llm, '_provider_preflight_error', lambda **kwargs: None)
    monkeypatch.setattr(llm, 'load_observed_llm_symbols',
        lambda: (generate, ObservedTextGeneration, GrokInvocationObservation), raising=False)
    return ordinary, observed


def test_backend_typed_intake_uses_observed_fixed_tool_boundary(monkeypatch):
    request_id = uuid.uuid4().hex
    ordinary, observed = _fake_boundary(monkeypatch, request_id)
    backend = LLMRouterBackend('synthetic', provider='grok_cli', model='grok-4.7',
        intake_operation='extract_facts', timeout_seconds=10)
    text = backend(SECRET, intake_request_id=request_id, intake_source_text=SOURCE,
        intake_target_refs=TARGETS, complaint_privacy_context=_context())
    assert json.loads(text)['request_id'] == request_id
    assert not ordinary and len(observed) == 1
    call = observed[0]
    prompt = json.loads(call['prompt'])
    assert prompt['request_id'] == request_id and prompt['operation'] == 'extract_facts'
    assert prompt['source_text'] == SOURCE and prompt['allowed_target_refs'] == list(TARGETS)
    assert prompt['prompt'] == SECRET and prompt['schema']['additionalProperties'] is False
    assert call['grok_cli_cmd'] == ['grok']
    assert call['grok_tools'] == 'read_file'
    assert call['grok_disallowed_tools'] == 'read_file,search_tool,use_tool'
    assert call['grok_max_turns'] == 1 and call['grok_permission_mode'] == 'dontAsk'
    assert call['grok_stream_progress'] is True and 'response_format' not in call
    assert backend.task_receipts[-1]['provider_supported_identity'] is True
    assert SECRET not in json.dumps(backend.task_receipts)


@pytest.mark.parametrize('entrypoint', ['generate_text_with_metadata', 'generate_text_via_router'])
def test_public_typed_entrypoints_share_observed_boundary(monkeypatch, entrypoint):
    request_id = uuid.uuid4().hex
    ordinary, observed = _fake_boundary(monkeypatch, request_id)
    result = getattr(llm, entrypoint)(SECRET, provider='grok_cli', model_name='grok-4.7',
        request_id=request_id, intake_operation='extract_facts', intake_source_text=SOURCE,
        intake_target_refs=TARGETS, complaint_privacy_context=_context(), timeout=1)
    if entrypoint.endswith('metadata'):
        assert result['status'] == 'available' and result['invocation_bound'] is True
        assert result['request_id'] == request_id
    else:
        assert json.loads(result)['request_id'] == request_id
    assert not ordinary and len(observed) == 1


def test_arbitrary_global_version_token_never_enters_trace():
    receipt = llm._redacted_router_trace({'router_version': SECRET}, request_id=uuid.uuid4().hex,
        requested_provider='grok_cli', requested_model='grok-4.7')
    assert SECRET not in json.dumps(receipt)


@pytest.mark.parametrize('privacy', [None, 'local', 'malformed'])
def test_typed_private_generation_refuses_before_loading_provider(monkeypatch, privacy):
    monkeypatch.setattr(llm, 'load_observed_llm_symbols', lambda: pytest.fail('provider loaded'))
    context = _context('local') if privacy == 'local' else {'version': SECRET} if privacy == 'malformed' else None
    result = llm.generate_text_with_metadata(SECRET, provider='grok_cli', model_name='grok-4.7',
        request_id=uuid.uuid4().hex, intake_operation='extract_facts', intake_source_text=SOURCE,
        intake_target_refs=TARGETS, complaint_privacy_context=context)
    assert result['failure_kind'] == 'privacy_denied' and result['dispatch'] == 'none'
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize('targets', [None, ['party.complainant', 'party.complainant'], SECRET, [True]])
def test_host_target_authority_is_required_before_provider(monkeypatch, targets):
    monkeypatch.setattr(llm, 'load_observed_llm_symbols', lambda: pytest.fail('provider loaded'))
    result = llm.generate_text_with_metadata(SECRET, provider='grok_cli', model_name='grok-4.7',
        request_id=uuid.uuid4().hex, intake_operation='extract_facts', intake_source_text=SOURCE,
        intake_target_refs=targets, complaint_privacy_context=_context())
    assert result['failure_kind'] == 'malformed' and result['dispatch'] == 'none'
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize('change,code', [({'request_id': '0' * 32}, 'route_unverified'),
    ({'native_dispatch_count': 2}, 'route_unverified'), ({'stream_complete': False}, 'route_unverified'),
    ({'provider_reported_model': SECRET}, 'substitution_refused')])
def test_current_typed_native_identity_is_required(monkeypatch, change, code):
    def generate(**kw):
        obs = dict(invocation_id=uuid.uuid4().hex, request_id=kw['observation_request_id'],
            native_dispatch_count=1, selected_provider_name='grok_cli', selected_model_name='grok-4.7',
            provider_reported_model='grok-4.7', wire_model_observed=True, process_returncode=0,
            stream_complete=True, evidence_class='native_final_end_model_usage')
        obs.update(change)
        return ObservedTextGeneration(text=_body(kw['observation_request_id']), observation=GrokInvocationObservation(**obs))
    monkeypatch.setattr(llm, 'load_observed_llm_symbols', lambda: (generate, ObservedTextGeneration, GrokInvocationObservation))
    backend = LLMRouterBackend('synthetic', provider='grok_cli', model='grok-4.7', intake_operation='extract_facts')
    with pytest.raises(backend_module.ProviderRouteError) as caught:
        backend(SECRET, intake_source_text=SOURCE, intake_target_refs=TARGETS, complaint_privacy_context=_context())
    assert caught.value.payload['error_code'] == code
    assert SECRET not in json.dumps(caught.value.payload)


@pytest.mark.parametrize('kind', ['quota', 'timeout', 'unavailable'])
def test_typed_failures_are_distinct_closed_and_dispatch_once(monkeypatch, kind):
    calls = []
    def generate(**kw):
        calls.append(kw)
        if kind == 'timeout':
            raise subprocess.TimeoutExpired([SECRET], 1)
        raise RuntimeError(('quota exceeded ' if kind == 'quota' else '') + SECRET)
    monkeypatch.setattr(llm, 'load_observed_llm_symbols', lambda: (generate, ObservedTextGeneration, GrokInvocationObservation))
    backend = LLMRouterBackend('synthetic', provider='grok_cli', model='grok-4.7',
        intake_operation='extract_facts', retry_max_attempts=3, retryable_error_substrings=['unavailable'])
    with pytest.raises(backend_module.ProviderRouteError) as caught:
        backend(SECRET, intake_source_text=SOURCE, intake_target_refs=TARGETS, complaint_privacy_context=_context())
    assert caught.value.payload['error_code'] == {'unavailable': 'provider_unavailable'}.get(kind, kind)
    assert len(calls) == 1 and SECRET not in json.dumps(caught.value.payload)


@pytest.mark.parametrize('text,limit', [('not-json', 262144), ('oversized', 10)])
def test_malformed_and_output_budget_never_become_success(monkeypatch, text, limit):
    request_id = uuid.uuid4().hex
    _fake_boundary(monkeypatch, request_id)
    original = llm.load_observed_llm_symbols()[0]
    def generate(**kw):
        result = original(**kw)
        return ObservedTextGeneration(text=text if text == 'not-json' else _body(kw['observation_request_id']),
            observation=result.observation)
    monkeypatch.setattr(llm, 'load_observed_llm_symbols', lambda: (generate, ObservedTextGeneration, GrokInvocationObservation))
    result = llm.generate_text_with_metadata(SECRET, provider='grok_cli', model_name='grok-4.7',
        request_id=request_id, intake_operation='extract_facts', intake_source_text=SOURCE,
        intake_target_refs=TARGETS, complaint_privacy_context=_context(), max_output_bytes=limit)
    assert result['status'] == result['failure_kind'] == 'malformed'
    assert result['text'] == '' and result['intake_complete'] is False


@pytest.fixture
def owned_native_capture(monkeypatch):
    import os
    from ipfs_accelerate_py.cli_runtime import grok_stream_capture as capture
    class Child:
        returncode = None
        killed = waited = False
        def poll(self): return self.returncode
        def kill(self): self.killed = True; self.returncode = -9
        def wait(self, timeout): self.waited = True; return self.returncode
    child = Child()
    writers = []
    for name in ('stdout', 'stderr'):
        read, write = os.pipe(); writers.append(write)
        setattr(child, name, os.fdopen(read, 'rb'))
    child.on_launch = lambda: None
    def launch(*args, **kwargs):
        child.on_launch()
        return child
    monkeypatch.setattr(capture.subprocess, 'Popen', launch)
    for name in ('kill', 'killpg'):
        monkeypatch.setattr(backend_module.os, name, lambda *a, **k: pytest.fail('raw PID signal'))
    def generate(**kw):
        result = capture.capture_grok_stream(['synthetic-owned-grok'], env={},
            timeout=kw['timeout'], progress_callback=kw['grok_progress_callback'])
        if result.timed_out:
            import subprocess
            raise subprocess.TimeoutExpired(['synthetic-owned-grok'], kw['timeout'])
        raise AssertionError('owned capture returned unexpectedly')
    monkeypatch.setattr(llm, 'load_observed_llm_symbols', lambda: (generate, ObservedTextGeneration, GrokInvocationObservation))
    try:
        yield child
    finally:
        for fd in writers: os.close(fd)
        for name in ('stdout', 'stderr'):
            pipe = getattr(child, name)
            if not pipe.closed: pipe.close()


def test_inflight_cancel_reaps_native_owned_child_before_return(owned_native_capture):
    import threading
    child = owned_native_capture
    backend = LLMRouterBackend('synthetic', provider='grok_cli', model='grok-4.7',
        intake_operation='extract_facts', timeout_seconds=.2)
    timer = threading.Timer(.02, backend.cancel)
    child.on_launch = timer.start
    try:
        with pytest.raises(backend_module.ProviderRouteError) as caught:
            backend(SECRET, intake_source_text=SOURCE, intake_target_refs=TARGETS, complaint_privacy_context=_context())
        assert caught.value.payload['error_code'] == 'cancelled'
        assert child.killed and child.waited and child.stdout.closed and child.stderr.closed
    finally:
        if timer.ident is not None: timer.join(1)


def test_timeout_reaps_native_owned_child_before_return(owned_native_capture):
    child = owned_native_capture
    backend = LLMRouterBackend('synthetic', provider='grok_cli', model='grok-4.7',
        intake_operation='extract_facts', timeout_seconds=.02)
    with pytest.raises(backend_module.ProviderRouteError) as caught:
        backend(SECRET, intake_source_text=SOURCE, intake_target_refs=TARGETS, complaint_privacy_context=_context())
    assert caught.value.payload['error_code'] == 'timeout'
    assert child.killed and child.waited and child.stdout.closed and child.stderr.closed


@pytest.mark.parametrize('field', ['question_id', 'prompt'])
def test_escaped_lone_surrogate_question_is_rejected(field):
    request_id = uuid.uuid4().hex
    question = {'question_id': 'question-original', 'prompt': 'What happened?', 'target_ref': 'question.original'}
    question[field] = chr(0xd800)
    body = json.dumps({'schema_version': 'intake_request_v1', 'operation': 'propose_questions',
        'request_id': request_id, 'questions': [question], 'facts': []})
    with pytest.raises(llm.IntakeContractError) as caught:
        llm.parse_intake_request(body, request_id=request_id, operation='propose_questions',
            source_text=SOURCE, allowed_target_refs=('question.original',))
    assert str(caught.value) == 'malformed'


@pytest.mark.parametrize('empty', [False, True])
def test_observed_questions_preserve_unicode_and_explicit_empty_authority(monkeypatch, empty):
    question = {'question_id': 'question-original', 'prompt': 'Où était José ?', 'target_ref': 'question.original'}
    def generate(**kw):
        request_id = kw['observation_request_id']
        observation = GrokInvocationObservation(invocation_id=uuid.uuid4().hex, request_id=request_id,
            native_dispatch_count=1, selected_provider_name='grok_cli', selected_model_name='grok-4.7',
            provider_reported_model='grok-4.7', wire_model_observed=True, process_returncode=0,
            stream_complete=True, evidence_class='native_final_end_model_usage')
        body = {'schema_version': 'intake_request_v1', 'operation': 'propose_questions',
            'request_id': request_id, 'questions': [] if empty else [question], 'facts': []}
        return ObservedTextGeneration(json.dumps(body), observation)
    monkeypatch.setattr(llm, 'load_observed_llm_symbols', lambda: (generate, ObservedTextGeneration, GrokInvocationObservation))
    result = llm.generate_text_with_metadata(SECRET, provider='grok_cli', model_name='grok-4.7',
        request_id=uuid.uuid4().hex, intake_operation='propose_questions', intake_source_text=SOURCE,
        intake_target_refs=() if empty else ('question.original',), complaint_privacy_context=_context())
    assert result['status'] == 'available' and result['successful_empty'] is empty
    assert json.loads(result['text'])['questions'] == ([] if empty else [question])
    assert result['schema_enforcement'] == 'host_fixed_intake_schema'
    assert result['native_response_format_supported'] is False


def test_host_parse_work_cannot_outlive_total_deadline(monkeypatch):
    request_id = uuid.uuid4().hex
    _, observed = _fake_boundary(monkeypatch, request_id)
    clock = [100.0]
    monkeypatch.setattr(llm.time, 'monotonic', lambda: clock[0])
    actual_parse = llm.parse_intake_request
    def delayed_parse(*args, **kwargs):
        parsed = actual_parse(*args, **kwargs)
        clock[0] += 2.0
        return parsed
    monkeypatch.setattr(llm, 'parse_intake_request', delayed_parse)
    result = llm.generate_text_with_metadata(SECRET, provider='grok_cli', model_name='grok-4.7',
        request_id=request_id, intake_operation='extract_facts', intake_source_text=SOURCE,
        intake_target_refs=TARGETS, complaint_privacy_context=_context(), timeout=1)
    assert result['failure_kind'] == 'timeout' and result['text'] == '' and len(observed) == 1
