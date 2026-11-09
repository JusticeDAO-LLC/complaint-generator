"""Synthetic terminal routing contracts. Typed fakes are never live-canary evidence."""
import ctypes.util
import importlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import uuid

import pytest
from tests.private_session_assertions import assert_private_session_frame, private_session_path

import backends.llm_router_backend as module
from backends.llm_router_backend import (
    LLMRouterBackend, ProviderRouteError, PINNED_GROK_MODEL, PINNED_GROK_PROVIDER,
    SUPPORTED_GROK_47_IDENTITIES, router_session_diagnostics_payload,
    router_task_receipt_payload,
)
from integrations.ipfs_accelerate.routers import INFERENCE_OWNER, PINNED_GROK_CANARY_PROMPT

ROOT = Path(__file__).resolve().parents[1]
COMPLAINT_MARKER = "COMPLAINT_PRIVATE_FACT_SHOULD_NOT_LEAK"


def _backend(**overrides):
    progress = []
    options = dict(timeout_seconds=2, retry_max_attempts=2, retry_backoff_base_s=0,
                   retry_backoff_max_s=0, retry_jitter_s=0, progress_callback=progress.append)
    options.update(overrides)
    return LLMRouterBackend('terminal-test', provider=PINNED_GROK_PROVIDER,
                            model=PINNED_GROK_MODEL, **options), progress


def _native_types():
    from ipfs_accelerate_py.cli_runtime.grok_invocation_observation import ObservedTextGeneration, GrokInvocationObservation
    return ObservedTextGeneration, GrokInvocationObservation


def _result(kwargs, text='synthetic-ok', **changes):
    result_type, observation_type = _native_types()
    values = dict(invocation_id=uuid.uuid4().hex, request_id=kwargs['observation_request_id'],
                  native_dispatch_count=1, selected_provider_name=PINNED_GROK_PROVIDER,
                  selected_model_name=PINNED_GROK_MODEL, provider_reported_model=PINNED_GROK_MODEL,
                  process_returncode=0, stream_complete=True, wire_model_observed=True,
                  evidence_class='native_final_end_model_usage')
    values.update(changes)
    return result_type(text, observation_type(**values))


def _observed(monkeypatch, function):
    result_type, observation_type = _native_types()
    monkeypatch.setattr(module, 'load_observed_llm_symbols', lambda: (function, result_type, observation_type))


def test_offline_fake_router_traverses_llm_router(monkeypatch):
    calls = []
    def fake(**kwargs):
        calls.append(kwargs)
        assert kwargs['provider'] == PINNED_GROK_PROVIDER
        assert kwargs['model_name'] == PINNED_GROK_MODEL
        assert kwargs['allow_local_fallback'] is kwargs['allow_cross_provider_fallback'] is False
        assert kwargs['grok_stream_progress'] is True
        return _result(kwargs)
    _observed(monkeypatch, fake)
    backend, progress = _backend()
    assert backend('synthetic-router-probe') == 'synthetic-ok'
    assert len(calls) == 1
    diagnostic = backend.sanitized_session_diagnostics()
    receipt = backend.task_receipts[-1]
    assert diagnostic['requested_router'] == diagnostic['selected_router'] == INFERENCE_OWNER
    assert diagnostic['requested_provider'] == diagnostic['selected_provider'] == PINNED_GROK_PROVIDER
    assert diagnostic['requested_model'] == diagnostic['selected_model'] == PINNED_GROK_MODEL
    assert diagnostic['provider_supported_identity'] is True
    assert diagnostic['route_observation'] == 'verified'
    assert diagnostic['session_id'] == backend.session_id
    assert diagnostic['session_retained'] is True
    assert receipt['request_id'] == calls[0]['observation_request_id']
    assert len(receipt['native_invocation_id']) == 32
    assert receipt['live_canary'] is False
    assert 'synthetic-router-probe' not in json.dumps([diagnostic, receipt, progress])
    assert progress[0]['phase'] == 'provider_wait'


def test_unavailable_grok_does_not_substitute_codex(monkeypatch):
    def unavailable(**kwargs):
        raise OSError(COMPLAINT_MARKER)
    _observed(monkeypatch, unavailable)
    backend, _ = _backend(retry_max_attempts=1)
    with pytest.raises(ProviderRouteError) as caught:
        backend(COMPLAINT_MARKER)
    assert caught.value.payload['error_code'] == 'provider_unavailable'
    assert caught.value.payload['session_id'] == backend.session_id
    assert caught.value.payload['session_retained'] is True
    assert caught.value.payload['selected_provider'] == caught.value.payload['selected_model'] == ''
    assert COMPLAINT_MARKER not in str(caught.value)


def test_observed_codex_selection_is_refused(monkeypatch):
    _observed(monkeypatch, lambda **kw: _result(kw, selected_provider_name='codex_cli', provider_reported_model='gpt-5.3-codex'))
    backend, _ = _backend()
    with pytest.raises(ProviderRouteError) as caught:
        backend('synthetic')
    assert caught.value.payload['error_code'] == 'substitution_refused'
    assert caught.value.payload['selected_provider'] == caught.value.payload['selected_model'] == ''
    assert backend.session_retained is True


def test_timeout_retry_and_cancel(monkeypatch):
    calls = []
    def flaky(**kw):
        calls.append(kw)
        if len(calls) == 1:
            raise RuntimeError('temporarily unavailable')
        return _result(kw, 'second')
    _observed(monkeypatch, flaky)
    backend, progress = _backend()
    assert backend('synthetic') == 'second'
    assert len(calls) == 2
    assert any(item['phase'] == 'retry_backoff' for item in progress)
    def timeout(**kw):
        assert 0 < kw['timeout'] <= .2
        raise TimeoutError(COMPLAINT_MARKER)
    _observed(monkeypatch, timeout)
    timed, _ = _backend(timeout_seconds=.2)
    with pytest.raises(ProviderRouteError) as caught:
        timed('synthetic')
    assert caught.value.payload['error_code'] == 'timeout'
    assert COMPLAINT_MARKER not in str(caught.value)
    cancelled, _ = _backend()
    cancelled.cancel()
    with pytest.raises(ProviderRouteError) as caught:
        cancelled('synthetic')
    assert caught.value.payload['error_code'] == 'cancelled'


def test_structured_output_validation(monkeypatch):
    _observed(monkeypatch, lambda **kw: _result(kw, 'not-json'))
    backend, _ = _backend(structured_output=True, response_schema={'required': ['answer']})
    with pytest.raises(ProviderRouteError) as caught:
        backend('synthetic')
    assert caught.value.payload['error_code'] == 'malformed_output'
    assert backend.session_retained is True


def test_build_label_is_provider_supported_identity(monkeypatch):
    _observed(monkeypatch, lambda **kw: _result(kw, 'ok', provider_reported_model='grok-4.7-build'))
    backend, _ = _backend()
    assert backend('synthetic') == 'ok'
    assert backend.task_receipts[-1]['selected_model'] == 'grok-4.7-build'
    assert backend.task_receipts[-1]['requested_model'] == PINNED_GROK_MODEL
    assert backend.task_receipts[-1]['provider_supported_identity'] is True


def test_config_and_launcher_select_grok47_router():
    config = json.loads((ROOT / 'config.llm_router.json').read_text())
    selected = next(item for item in config['BACKENDS'] if item['id'] == 'llm-router-grok-4.7')
    assert selected['provider'] == PINNED_GROK_PROVIDER and selected['model'] == PINNED_GROK_MODEL
    assert selected['allow_local_fallback'] is selected['allow_cross_provider_fallback'] is False
    script = (ROOT / 'scripts/run_cli_mediator.sh').read_text()
    assert 'COMPLAINT_GENERATOR_MEDIATOR_BACKENDS="llm-router-grok-4.7"' in script


def test_cli_diagnostics_and_receipts_are_sanitized():
    diagnostics = router_session_diagnostics_payload(str(ROOT / 'config.llm_router.json'))
    receipts = router_task_receipt_payload(str(ROOT / 'config.llm_router.json'))
    assert diagnostics['requested_router'] == INFERENCE_OWNER
    assert diagnostics['requested_provider'] == PINNED_GROK_PROVIDER
    assert diagnostics['requested_model'] == PINNED_GROK_MODEL
    assert diagnostics['selected_provider'] == diagnostics['selected_model'] == ''
    assert diagnostics['prompt_logged'] is False
    assert diagnostics['remote_inference']['sends_complaint_text_remotely'] is True
    assert diagnostics['remote_inference']['encryption_at_rest_implies_private_remote_inference'] is False
    assert receipts['receipts'][0]['status'] == 'configured'


def test_synthetic_live_canary_records_model_without_complaint_data(monkeypatch):
    # Exercise the existing real first-party capability interpreter, with only
    # a synthetic transport. A mapping is not current-call wire-model evidence.
    monkeypatch.setattr('integrations.ipfs_datasets.llm.grok_cli_binary_present', lambda: True)
    monkeypatch.setattr('integrations.ipfs_datasets.llm.grok_cli_auth_present', lambda: True)
    calls = []
    def transport(**kw):
        calls.append(kw)
        assert kw['prompt'] == PINNED_GROK_CANARY_PROMPT
        return {'text': PINNED_GROK_CANARY_PROMPT, 'selected_provider_name': PINNED_GROK_PROVIDER,
                'selected_model_name': 'grok-4.7-build'}
    backend, _ = _backend()
    receipt = backend.run_synthetic_live_canary(transport=transport)
    assert len(calls) == 1
    assert receipt['selected_provider'] == receipt['selected_model'] == ''
    assert receipt['provider_supported_identity'] is receipt['live_canary'] is False
    assert receipt['complaint_data_included'] is False
    assert receipt['evidence_class'] == 'synthetic_canary'
    assert PINNED_GROK_CANARY_PROMPT not in json.dumps(receipt)
    assert backend.run_synthetic_live_canary()['status'] == 'not_requested'


def test_pinned_route_cannot_disable_substitution_checks():
    backend, _ = _backend(forbid_model_substitution=False)
    assert backend._strict_route() is True


def test_injected_canary_identity_stays_unverified_and_calls_once(monkeypatch):
    monkeypatch.setattr('integrations.ipfs_datasets.llm.grok_cli_binary_present', lambda: True)
    monkeypatch.setattr('integrations.ipfs_datasets.llm.grok_cli_auth_present', lambda: True)
    calls = []
    def injected(**kw):
        calls.append(kw)
        return {'text': PINNED_GROK_CANARY_PROMPT, 'selected_provider_name': PINNED_GROK_PROVIDER,
                'selected_model_name': 'grok-4.7-build', 'live_canary': True}
    backend, _ = _backend()
    receipt = backend.run_synthetic_live_canary(transport=injected)
    assert len(calls) == 1
    assert receipt['live_canary'] is receipt['provider_supported_identity'] is False
    assert receipt['route_observation'] != 'verified'
    assert receipt['selected_provider'] == receipt['selected_model'] == ''


def test_explicit_live_canary_delegates_to_existing_bound_firstparty_api(monkeypatch):
    calls = []
    def capability(**kw):
        calls.append(kw)
        return {'status': 'unavailable', 'live_canary': False}
    monkeypatch.setattr(module, 'grok47_route_capability', capability)
    backend, _ = _backend()
    assert backend.run_synthetic_live_canary(confirm_live=True)['live_canary'] is False
    assert calls == [{'include_canary': True}]


def test_cancel_during_generation_cannot_return_a_late_answer(monkeypatch):
    backend, _ = _backend()
    def generation(**kw):
        backend.cancel()
        return _result(kw, 'late private output')
    _observed(monkeypatch, generation)
    with pytest.raises(ProviderRouteError) as caught:
        backend('synthetic')
    assert caught.value.payload['error_code'] == 'cancelled'
    assert 'late private output' not in str(caught.value)


def test_provider_identity_fields_cannot_echo_private_values(monkeypatch):
    _observed(monkeypatch, lambda **kw: _result(kw, selected_provider_name=COMPLAINT_MARKER,
                                               provider_reported_model=COMPLAINT_MARKER,
                                               request_id=COMPLAINT_MARKER))
    backend, _ = _backend()
    with pytest.raises(ProviderRouteError) as caught:
        backend(COMPLAINT_MARKER)
    assert COMPLAINT_MARKER not in str(caught.value)
    assert COMPLAINT_MARKER not in json.dumps(backend.task_receipts)


@pytest.mark.parametrize('changes', [dict(native_dispatch_count=2), dict(wire_model_observed=False),
    dict(stream_complete=False), dict(process_returncode=1), dict(evidence_class='usage_text'),
    dict(invocation_scope='previous_call'), dict(raw_provider_data_exported=True),
    dict(request_id='0'*32)])
def test_unbound_or_incomplete_observation_cannot_verify_identity(monkeypatch, changes):
    _observed(monkeypatch, lambda **kw: _result(kw, **changes))
    backend, _ = _backend()
    with pytest.raises(ProviderRouteError) as caught:
        backend('synthetic')
    assert caught.value.payload['error_code'] == 'route_unverified'


def test_global_or_mapping_trace_never_verifies_identity(monkeypatch):
    _observed(monkeypatch, lambda **kw: {'text': 'fake', 'observed_provider_name': PINNED_GROK_PROVIDER,
                                       'observed_model_name': PINNED_GROK_MODEL})
    backend, _ = _backend()
    with pytest.raises(ProviderRouteError) as caught:
        backend('synthetic')
    assert caught.value.payload['error_code'] == 'route_unverified'


def test_private_policy_is_decided_before_loading_provider(monkeypatch):
    from integrations.ipfs_datasets.llm import build_complaint_privacy_context, privacy_policy_for_mode
    def forbidden():
        raise AssertionError('provider loaded before consent')
    monkeypatch.setattr(module, 'load_observed_llm_symbols', forbidden)
    backend, _ = _backend()
    context = build_complaint_privacy_context(privacy_policy_for_mode('synthetic', 'synthetic', 'local'),
                                            user_id='synthetic', case_id='synthetic', data_class='raw_intake')
    with pytest.raises(ProviderRouteError) as caught:
        backend(COMPLAINT_MARKER, complaint_privacy_context=context)
    assert caught.value.payload['error_code'] == 'privacy_denied'
    assert COMPLAINT_MARKER not in str(caught.value)


def test_native_capture_cancellation_reaps_its_owned_child_before_return(monkeypatch):
    from ipfs_accelerate_py.cli_runtime import grok_stream_capture as capture
    backend, _ = _backend()
    class Child:
        def poll(self): return self.returncode
        def kill(self): self.killed = True; self.returncode = -9
        def wait(self, timeout): self.waited = True; return self.returncode
    # Keep both writers owned by this test and close them deterministically.
    readers, writers = [], []
    child = Child.__new__(Child)
    for name in ('stdout', 'stderr'):
        r, w = os.pipe(); readers.append(r); writers.append(w)
        setattr(child, name, os.fdopen(r, 'rb'))
    child.returncode = None; child.killed = child.waited = False
    def launch(command, **kw):
        assert command == ['synthetic-owned-grok']
        backend.cancel()
        return child
    monkeypatch.setattr(capture.subprocess, 'Popen', launch)
    def generation(**kw):
        capture.capture_grok_stream(['synthetic-owned-grok'], env={}, timeout=kw['timeout'],
                                    progress_callback=kw['grok_progress_callback'])
        raise AssertionError('cancelled capture returned')
    _observed(monkeypatch, generation)
    try:
        with pytest.raises(ProviderRouteError) as caught:
            backend('synthetic')
        assert caught.value.payload['error_code'] == 'cancelled'
        assert child.killed and child.waited
        assert child.stdout.closed and child.stderr.closed
    finally:
        for fd in writers: os.close(fd)


@pytest.fixture
def terminal_service(tmp_path, monkeypatch):
    # Real native dependencies may discover libmagic by starting ldconfig. Bind
    # only this actual root-owned library while keeping the global egress deny.
    library = Path('/usr/lib/x86_64-linux-gnu/libmagic.so.1.0.0')
    st = library.stat()
    assert st.st_uid == 0 and not stat.S_IMODE(st.st_mode) & 0o022
    original_find = ctypes.util.find_library
    monkeypatch.setattr(ctypes.util, 'find_library', lambda name: str(library) if name == 'magic' else original_find(name))
    guarded_popen = subprocess.Popen
    class GuardedPopen:
        def __new__(cls, *args, **kw): return guarded_popen(*args, **kw)
        @classmethod
        def __class_getitem__(cls, item): return cls
    monkeypatch.setattr(subprocess, 'Popen', GuardedPopen)
    workspace = importlib.import_module('applications.complaint_workspace')
    monkeypatch.setattr(workspace, '_SESSION_DIR', tmp_path / 'global-import')
    prior = sys.modules.pop('applications.complaint_cli', None)
    package = importlib.import_module('applications')
    previous_attribute = getattr(package, 'complaint_cli', None)
    import applications.complaint_cli as cli
    service = cli.TerminalComplaintWorkspaceService(root_dir=tmp_path / 'sessions')
    service.initialize_private_keys(protection='passphrase', passphrase='synthetic-test-passphrase')
    service.ensure_private_case_key('synthetic-user', 'synthetic-user')
    monkeypatch.setattr(cli, 'service', service)
    try:
        yield cli, service
    finally:
        sys.modules.pop('applications.complaint_cli', None)
        if prior is not None: sys.modules['applications.complaint_cli'] = prior
        if previous_attribute is not None: setattr(package, 'complaint_cli', previous_attribute)
        elif hasattr(package, 'complaint_cli'): delattr(package, 'complaint_cli')


def test_actual_shared_cli_saves_invocation_with_encrypted_cold_resume(terminal_service, monkeypatch, capsys):
    cli, service = terminal_service
    service.set_privacy_policy('synthetic-user', 'grok')
    calls = []
    def generate(**kw):
        control = json.loads(kw['prompt'])
        assert control['operation'] in {'extract_facts', 'propose_questions'}
        assert control['request_id'] == kw['observation_request_id']
        calls.append(kw)
        body = {key: control[key] for key in ('schema_version', 'operation', 'request_id')}
        body.update(facts=[], questions=[])
        return _result(kw, json.dumps(body))
    _observed(monkeypatch, generate)
    from integrations.ipfs_datasets import llm
    result_type, observation_type = _native_types()
    monkeypatch.setattr(llm, 'load_observed_llm_symbols', lambda: (generate, result_type, observation_type))
    narrative = 'SYNTHETIC_NARRATIVE_FOR_ROUTER_TEST'
    monkeypatch.setattr(sys, 'stdin', io.StringIO(narrative + '\n.\nSynthetic Person\n'))
    with pytest.raises(SystemExit) as paused:
        cli.chat(user_id='synthetic-user', max_turns=2)
    assert paused.value.code == 0
    assert calls, 'default canonical chat never reached the observed router backend'
    assert {json.loads(call['prompt'])['operation'] for call in calls} == {'extract_facts', 'propose_questions'}
    assert len({call['observation_request_id'] for call in calls}) == len(calls)
    session = service.get_session('synthetic-user')['session']
    projection = session['shared_interview']
    assert projection['knowledge_graph'] is not None
    history = projection['denoiser_history']
    assert sum(entry.get('answer') == 'Synthetic Person' for entry in history) == 1
    receipts = session['router_trace']['receipts']
    assert receipts and all(entry['interview_session_id'] == projection['session_id'] for entry in receipts)
    assert all(entry['router_receipt']['request_id'] for entry in receipts)
    assert all(entry['router_receipt']['native_invocation_id'] for entry in receipts)
    assert all(entry['router_receipt']['live_canary'] is False for entry in receipts)
    assert narrative not in json.dumps(session['router_trace'])
    from applications.complaint_workspace import namespace_filename
    encrypted = private_session_path(service._session_dir, 'synthetic-user')
    assert_private_session_frame(encrypted.read_bytes(), narrative)
    restarted = cli.TerminalComplaintWorkspaceService(root_dir=service._session_dir)
    restarted.unlock_private_keys(passphrase='synthetic-test-passphrase')
    resumed = restarted.run_intake_chat_turn('synthetic-user')
    assert resumed['session']['shared_interview']['denoiser_history'] == history
    assert resumed['session']['router_trace'] == session['router_trace']
    monkeypatch.setattr(cli, 'service', restarted)
    capsys.readouterr()
    cli.router_task_receipt(user_id='synthetic-user')
    assert json.loads(capsys.readouterr().out)['receipts'] == receipts


def test_actual_shared_cli_local_policy_never_loads_remote_provider(terminal_service, monkeypatch):
    cli, service = terminal_service
    def forbidden(): raise AssertionError('local-private loaded remote provider')
    monkeypatch.setattr(module, 'load_observed_llm_symbols', forbidden)
    payload = service.run_intake_chat_turn('synthetic-user', message='SYNTHETIC_LOCAL_NARRATIVE')
    assert payload['session']['privacy_policy']['cloud_processing_enabled'] is False
    assert not (payload['session'].get('router_trace') or {}).get('receipts')


@pytest.mark.parametrize('value', [None, 1, 'yes'])
def test_canary_needs_boolean_confirmation_before_discovery(monkeypatch, value):
    monkeypatch.setattr(module, 'grok47_route_capability', lambda **kw: pytest.fail('unexpected canary discovery'))
    backend, _ = _backend()
    with pytest.raises(ValueError):
        backend.run_synthetic_live_canary(confirm_live=value)


def test_progress_display_failure_does_not_repeat_provider_dispatch(monkeypatch):
    calls = []
    def generate(**kw):
        calls.append(kw)
        kw['grok_progress_callback']({})
        return _result(kw)
    _observed(monkeypatch, generate)
    def broken_display(event):
        raise RuntimeError(COMPLAINT_MARKER)
    backend, _ = _backend(progress_callback=broken_display)
    assert backend('synthetic') == 'synthetic-ok'
    assert len(calls) == 1
    assert COMPLAINT_MARKER not in json.dumps(backend.task_receipts)


def test_shell_launcher_enters_private_canonical_chat_without_legacy_config():
    script = (ROOT / 'scripts/run_cli_mediator.sh').read_text()
    assert 'exec "${PYTHON}" -m applications.complaint_cli chat "$@"' in script
    assert 'run.py' not in script and '--config' not in script
    assert 'COMMON_CRAWL_AUTO_CLONE_SOURCE=0' in script
    assert 'umask 077' in script


def test_real_native_generation_overrides_ambient_command_and_denies_all_tools(monkeypatch):
    """Actual native builder/observation, authored stream only; never a live call."""
    from contextlib import contextmanager
    from types import SimpleNamespace
    from ipfs_accelerate_py import llm_router as router
    from ipfs_accelerate_py.cli_runtime import grok_stream_capture as stream
    from integrations.ipfs_datasets.llm import build_complaint_privacy_context, privacy_policy_for_mode
    monkeypatch.setenv('IPFS_ACCELERATE_PY_GROK_CLI_CMD', 'grok --tools write_file --resume synthetic-foreign')
    monkeypatch.setenv('IPFS_ACCELERATE_PY_GROK_CLI_TOOLS', 'write_file,run_terminal_cmd')
    monkeypatch.setenv('IPFS_ACCELERATE_PY_GROK_CLI_PERMISSION_MODE', 'bypassPermissions')
    monkeypatch.setenv('IPFS_ACCELERATE_PY_GROK_CLI_MAX_TURNS', '64')
    monkeypatch.setattr(router, '_cli_available', lambda command: True)
    provider = router._get_grok_cli_provider()
    monkeypatch.setattr(router, 'get_default_router_deps', lambda: SimpleNamespace())
    monkeypatch.setattr(router, 'get_llm_provider', lambda name, **kw: provider)
    monkeypatch.setattr(router, '_response_cache_enabled', lambda: False)
    @contextmanager
    def sampling(environment, **kw): yield environment
    monkeypatch.setattr(router, '_grok_zero_temperature_environment', sampling)
    calls = []
    def capture(argv, **kw):
        calls.append(argv)
        assert argv[0] == 'grok' and '--resume' not in argv
        assert argv[argv.index('--tools') + 1] == 'read_file'
        assert set(argv[argv.index('--disallowed-tools') + 1].split(',')) == {'read_file','search_tool','use_tool'}
        assert argv[argv.index('--max-turns') + 1] == '1'
        assert argv[argv.index('--permission-mode') + 1] == 'dontAsk'
        assert argv[argv.index('--model') + 1] == PINNED_GROK_MODEL
        assert '--no-subagents' in argv and '--disable-web-search' in argv
        assert 0 < kw['timeout'] <= 2
        assert Path(argv[argv.index('--prompt-file') + 1]).read_text() == COMPLAINT_MARKER
        end = {'type':'end','stopReason':'end_turn','modelUsage':{PINNED_GROK_MODEL:{'outputTokens':1}}}
        parser = stream.GrokStreamParser()
        parser.feed(b''.join(json.dumps(frame).encode()+b'\n' for frame in [{'type':'text','data':'synthetic-ok'},end]), elapsed_seconds=.1)
        parser.eof('stdout',elapsed_seconds=.2); parser.eof('stderr',elapsed_seconds=.2)
        parser.process_exit(0,elapsed_seconds=.2)
        return SimpleNamespace(returncode=0,timed_out=False,progress=parser.snapshot(elapsed_seconds=.2),
            final_payload=parser.final_payload,stdout=json.dumps({**end,'text':parser.response_text}),stderr='',response_text=parser.response_text)
    monkeypatch.setattr(stream, 'capture_grok_stream', capture)
    result_type, observation_type = _native_types()
    monkeypatch.setattr(module, 'load_observed_llm_symbols', lambda: (router.generate_text_with_observation,result_type,observation_type))
    policy = privacy_policy_for_mode('synthetic','synthetic','grok')
    context = build_complaint_privacy_context(policy,user_id='synthetic',case_id='synthetic',data_class='raw_intake')
    backend, _ = _backend()
    assert backend(COMPLAINT_MARKER,complaint_privacy_context=context) == 'synthetic-ok'
    assert len(calls) == 1 and backend.task_receipts[-1]['provider_supported_identity'] is True
    assert backend.task_receipts[-1]['live_canary'] is False
    assert COMPLAINT_MARKER not in json.dumps(backend.task_receipts)
