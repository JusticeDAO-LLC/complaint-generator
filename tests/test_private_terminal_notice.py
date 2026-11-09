"""The public terminal must describe consent and encryption without false states."""
from pathlib import Path
import pytest
from applications.complaint_workspace import ComplaintWorkspaceService
from tests.test_intake_documented_commands import _operator_env, _pty_run, _python_argv, PRIMARY, REPO_ROOT
from tests.private_session_assertions import assert_private_session_frame, private_session_path
from tests.test_tui_interview_acceptance import _block_network_and_provider_subprocesses

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
PHRASE = 'synthetic-private-notice-passphrase'
USER = 'synthetic-private-notice'


def _service(directory: Path):
    service = ComplaintWorkspaceService(root_dir=directory)
    service.initialize_private_keys(protection='passphrase', passphrase=PHRASE)
    service.ensure_private_case_key(USER, USER)
    return service


@pytest.mark.parametrize('mode', ['local', 'grok'])
def test_shared_opening_does_not_claim_plaintext_or_wrong_processing_mode(tmp_path: Path, mode: str):
    service = _service(tmp_path / 'sessions')
    service.set_privacy_policy(USER, mode)
    opened = service.run_intake_chat_turn(USER)
    message = opened['message']
    assert 'plaintext/pending' not in message
    assert not (mode == 'grok' and 'Privacy mode is local private processing' in message)
    assert '/privacy local' in message and '/privacy grok' in message
    assert opened['session']['privacy_policy']['cloud_processing_enabled'] is (mode == 'grok')
    assert opened.get('accepted_answer') is None
    assert opened['inquiry']['question_id'] == 'original_complaint'
    assert_private_session_frame(private_session_path(service._session_dir, USER).read_bytes(), PHRASE)
    assert service.get_session(USER)['session']['at_rest_protection'] == 'private_envelope'


@pytest.mark.parametrize('mode', ['local', 'grok'])
def test_fresh_terminal_notice_matches_saved_choice_and_encrypted_case(tmp_path: Path, mode: str):
    sessions, home = tmp_path / 'sessions', tmp_path / 'home'
    home.mkdir()
    service = _service(sessions)
    service.lock_private_keys()
    argv = _python_argv(PRIMARY, {'USER_ID': USER}) + ['--privacy-mode', mode]
    code, transcript = _pty_run(argv, cwd=REPO_ROOT,
        env=_operator_env(home, {'COMPLAINT_WORKSPACE_SESSION_DIR': str(sessions)}),
        steps=[('passphrase', PHRASE + '\n'), ('>', '/quit\n')])
    assert code == 0, transcript[-1500:]
    assert PHRASE not in transcript and 'plaintext/pending' not in transcript
    if mode == 'grok':
        assert 'Remote Grok processing authorized' in transcript
        assert 'Privacy mode is local private processing' not in transcript
    else:
        assert 'future remote calls are disabled' in transcript
    cold = ComplaintWorkspaceService(root_dir=sessions)
    cold.unlock_private_keys(passphrase=PHRASE)
    assert cold.get_privacy_policy(USER)['policy']['cloud_processing_enabled'] is (mode == 'grok')
    state = cold.get_session(USER)['session']
    assert state['at_rest_protection'] == 'private_envelope' and state['intake_history'] == []
    assert_private_session_frame(private_session_path(sessions, USER).read_bytes(), PHRASE)
