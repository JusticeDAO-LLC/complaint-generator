"""Fresh-process private terminal unlock; all data and credentials are synthetic."""
from __future__ import annotations
import importlib,json,os,pty,select,subprocess,sys,time
from pathlib import Path
import pytest
from applications.complaint_workspace import ComplaintWorkspaceService,WorkspaceAccess,WorkspacePersistenceError,WorkspaceAuthorizationDenied,workspace_access_scope
from tests.test_tui_interview_acceptance import _block_network_and_provider_subprocesses
pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]
PHRASE='synthetic-cold-terminal-unlock-test-passphrase'
USER='synthetic-cold-terminal'
NARRATIVE='On March 4, 2024 supervisor Alex Rivera fired me after I reported safety concerns.'

def _files(root):return {str(p.relative_to(root)):p.read_bytes()for p in root.rglob('*')if p.is_file()}

@pytest.fixture
def terminal(tmp_path,monkeypatch):
    service=ComplaintWorkspaceService(root_dir=tmp_path/'session')
    service.initialize_private_keys(protection='passphrase',passphrase=PHRASE)
    cli=importlib.import_module('applications.complaint_cli')
    monkeypatch.setattr(cli,'service',service)
    return cli,service

def _prompt(monkeypatch,value=PHRASE,tty=True):
    from integrations import private_storage
    class Input:
        def isatty(self):return tty
    monkeypatch.setattr(sys,'stdin',Input())
    monkeypatch.setattr(private_storage,'read_unlock_passphrase',lambda _label:value)

def test_existing_case_unlock_stays_in_the_chat_process(terminal,monkeypatch):
    cli,service=terminal
    original=service.ensure_private_case_key(USER,USER)['data_key_id']
    service.lock_private_keys();before=_files(service._session_dir)
    _prompt(monkeypatch);cli._unlock_private_chat_case(USER)
    assert service.private_key_status()['unlocked'] is True
    assert service.ensure_private_case_key(USER,USER)['data_key_id']==original
    assert _files(service._session_dir)==before
    assert service.get_privacy_policy(USER)['policy']['cloud_processing_enabled'] is False

def test_new_case_gets_a_wrapped_key_after_unlock(terminal,monkeypatch):
    cli,service=terminal;service.lock_private_keys();_prompt(monkeypatch)
    cli._unlock_private_chat_case(USER)
    assert service.ensure_private_case_key(USER,USER)['data_key_id']
    assert service.private_key_status()['unlocked'] is True
    assert all(PHRASE.encode()not in blob for blob in _files(service._session_dir).values())

@pytest.mark.parametrize('kind',['primary','legacy','joined','snapshot','unindexed'])
def test_missing_case_key_cannot_replace_existing_private_state(terminal,monkeypatch,kind):
    cli,service=terminal
    if kind=='primary':path=service._session_dir/(service._namespace_filename(USER)+'.cgpe')
    elif kind=='legacy':path=service._legacy_session_path(USER)
    elif kind=='joined':path=service.joined_revision_repository(USER,USER)/'head.cgpe'
    elif kind=='snapshot':path=service.interview_snapshot_directory(USER,USER)/'head.json'
    else:path=service._session_dir/'private-artifacts'/'opaque-existing'
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);path.write_bytes(b'opaque-synthetic-existing-private-bytes')
    before=_files(service._session_dir);service.lock_private_keys();_prompt(monkeypatch)
    with pytest.raises(WorkspacePersistenceError)as error:cli._unlock_private_chat_case(USER)
    assert error.value.code=='key_unavailable'
    assert _files(service._session_dir)==before

def test_wrong_passphrase_preserves_bytes(terminal,monkeypatch):
    cli,service=terminal;service.ensure_private_case_key(USER,USER);service.lock_private_keys();before=_files(service._session_dir)
    _prompt(monkeypatch,'wrong-synthetic-passphrase')
    with pytest.raises(WorkspacePersistenceError)as error:cli._unlock_private_chat_case(USER)
    assert error.value.code=='authentication_failed'and _files(service._session_dir)==before

def test_nonterminal_never_reads_a_passphrase(terminal,monkeypatch):
    cli,service=terminal;service.lock_private_keys();before=_files(service._session_dir)
    _prompt(monkeypatch,tty=False)
    from integrations import private_storage
    monkeypatch.setattr(private_storage,'read_unlock_passphrase',lambda *_a:pytest.fail('nonterminal passphrase read'))
    with pytest.raises(WorkspacePersistenceError)as error:cli._unlock_private_chat_case(USER)
    assert error.value.code=='unlock_needed'and _files(service._session_dir)==before

def test_absent_store_is_not_replaced_automatically(tmp_path,monkeypatch):
    cli=importlib.import_module('applications.complaint_cli');service=ComplaintWorkspaceService(root_dir=tmp_path/'absent');monkeypatch.setattr(cli,'service',service)
    before=_files(service._session_dir);_prompt(monkeypatch)
    with pytest.raises(WorkspacePersistenceError)as error:cli._unlock_private_chat_case(USER)
    assert error.value.code=='unlock_needed'and _files(service._session_dir)==before

def test_authorization_precedes_any_key_lookup(terminal,monkeypatch):
    cli,service=terminal;before=_files(service._session_dir)
    monkeypatch.setattr(service,'_private_key_session',lambda:pytest.fail('key lookup before local-operator authorization'))
    with workspace_access_scope(WorkspaceAccess.authenticated('other-user',case_id='other-case')):
        with pytest.raises(WorkspaceAuthorizationDenied):cli._unlock_private_chat_case(USER)
    assert _files(service._session_dir)==before

def test_chat_rejects_passphrase_process_arguments(monkeypatch,capsys):
    cli=importlib.import_module('complaint_generator.cli')
    secret='synthetic-never-echo-this-argument'
    monkeypatch.setattr(sys,'argv',['complaint-generator','chat','--passphrase',secret])
    with pytest.raises(SystemExit)as error:cli.main()
    captured=capsys.readouterr();assert secret not in str(error.value)+captured.out+captured.err

def _real_cli(tmp_path,session_dir,phrase,*,narrative=None):
    root=Path(__file__).resolve().parents[1]
    script=tmp_path/'real-package-chat.py'
    # Only storage location is isolated. main constructs its normal, locked
    # TerminalComplaintWorkspaceService; no unlocked service is injected.
    script.write_text("import sys\nfrom pathlib import Path\nsys.path[:0]="+repr(list(sys.path))+"\nfrom applications import complaint_workspace as workspace\nworkspace._SESSION_DIR=Path("+repr(str(session_dir))+")\nfrom complaint_generator.cli import main\nsys.argv=['complaint-generator','chat','--user-id',"+repr(USER)+",'--max-turns','1']\nmain()\n")
    script.chmod(0o600)
    master,slave=pty.openpty();os.set_blocking(master,False)
    env={**os.environ,'NO_COLOR':'1','TERM':'dumb','COMPLAINT_CLI_ASCII':'1'}
    process=subprocess.Popen([sys.executable,'-I','-B',str(script)],cwd=root,env=env,stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
    os.close(slave);parts=[];sent_phrase=False;sent_narrative=False;deadline=time.monotonic()+150
    try:
        while time.monotonic()<deadline:
            ready,_,_=select.select([master],[],[],.1)
            if ready:
                try:chunk=os.read(master,65536)
                except OSError:break
                if not chunk:break
                parts.append(chunk);assert sum(map(len,parts))<=262144
            raw=b''.join(parts)
            if not sent_phrase and b'Private workspace passphrase' in raw:
                os.write(master,(phrase+'\n').encode());sent_phrase=True
            if sent_phrase and narrative is not None and not sent_narrative and (b'Describe your complaint' in raw or b'plain language' in raw):
                os.write(master,(narrative+'\n').encode());sent_narrative=True
            if process.poll()is not None:break
        if process.poll()is None:process.terminate()
        code=process.wait(timeout=10)
    finally:
        os.close(master)
    output=b''.join(parts)
    assert sent_phrase and phrase.encode()not in output
    return code,output,sent_narrative

def test_fresh_package_chat_unlocks_without_an_injected_service(terminal,tmp_path):
    _,service=terminal;service.lock_private_keys()
    code,output,sent=_real_cli(tmp_path,service._session_dir,PHRASE,narrative=NARRATIVE)
    assert code==0 and sent
    assert b'Traceback'not in output and b'Chat paused' in output
    fresh=ComplaintWorkspaceService(root_dir=service._session_dir);fresh.unlock_private_keys(passphrase=PHRASE)
    status=fresh.run_intake_chat_turn(USER,interview_action='status')
    assert status['original_complaint']['text']==NARRATIVE
    assert status['interview']['inquiry']['inquiry_id'].startswith('inq-')
    assert status['stopping_policy']['legal_sufficiency'] is False

def test_fresh_package_wrong_passphrase_is_private_and_preserves_store(terminal,tmp_path):
    _,service=terminal;service.ensure_private_case_key(USER,USER);service.lock_private_keys();before=_files(service._session_dir)
    code,output,sent=_real_cli(tmp_path,service._session_dir,'synthetic-wrong-password')
    assert code==2 and not sent and b'Traceback'not in output and b'authentication_failed'in output
    assert _files(service._session_dir)==before


def test_unlock_cancellation_has_a_bounded_private_exit(terminal,monkeypatch,capsys):
    cli,service=terminal;service.lock_private_keys();before=_files(service._session_dir);_prompt(monkeypatch)
    from integrations import private_storage
    def interrupted(*_args):raise KeyboardInterrupt()
    monkeypatch.setattr(private_storage,'read_unlock_passphrase',interrupted)
    with pytest.raises(SystemExit)as error:cli.chat(user_id=USER,max_turns=1)
    output=capsys.readouterr();assert error.value.code==130
    assert 'Traceback'not in output.out+output.err and PHRASE not in output.out+output.err
    assert _files(service._session_dir)==before
