"""Actual guarded review correction and crypto cutoff share one key epoch order."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
import os

import pytest
from fastapi.testclient import TestClient

from integrations.private_storage import UserOwnedKeySession, PrivateArtifactBinding, PrivateStorageError
from tests.test_cimp_gui_14 import _composed_login, PASSPHRASE
from tests.test_gui47_private_acceptance import _world, _accept, _head
from tests.test_gui46_private_owner_controls import _service, _change

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


def test_actual_guarded_review_callback_and_revocation_finish_without_lock_inversion(tmp_path,monkeypatch):
    world,_offer,request=_world(tmp_path)
    world.review_app.state.case_assignments=_service(world)
    assert world.owner_keys.directory==world.service._private_key_session().directory
    entered,release,revoker_entered=Event(),Event(),Event()
    actual_factory=world.service._joined_publication_scope
    actual_epoch=UserOwnedKeySession.case_key_epoch_scope
    before=_head(world).read_bytes();at_epoch_exit=[]
    def factory(*args,**kwargs):
        underlying=actual_factory(*args,**kwargs)
        @contextmanager
        def hold():
            with underlying():
                entered.set()
                assert release.wait(15),'authored guarded correction barrier timed out'
                try:
                    yield
                finally:
                    # The real Kit execute has committed or aborted before
                    # ExitStack drops this actual epoch. No key lock is held.
                    at_epoch_exit.append(_head(world).read_bytes())
        return hold
    def observe_epoch(session,*args,**kwargs):
        if session is world.owner_keys:
            revoker_entered.set()
        return actual_epoch(session,*args,**kwargs)
    monkeypatch.setattr(world.service,'_joined_publication_scope',factory)
    monkeypatch.setattr(UserOwnedKeySession,'case_key_epoch_scope',observe_epoch)
    with TestClient(world.review_app,base_url='https://testserver') as accepter, TestClient(world.review_app,base_url='https://testserver') as revoker:
        csrf=_composed_login(accepter);revoker.cookies.update(accepter.cookies)
        with ThreadPoolExecutor(max_workers=2) as pool:
            accepting=pool.submit(_accept,accepter,world,csrf,request)
            assert entered.wait(15),'actual correction did not enter its publication epoch'
            revoking=pool.submit(_change,world,revoker,csrf,revoke=True,key='actual-review-callback-cutoff')
            try:
                assert revoker_entered.wait(15),'actual public revoke did not reach the epoch boundary'
                assert not revoking.done(),'revocation escaped the already-held write epoch'
            finally:
                release.set()
            accepted=accepting.result(timeout=20)
            revoked,_=revoking.result(timeout=20)
        assert accepted.status_code in {200,403,409,503},{'status':accepted.status_code}
        assert revoked.status_code==200 and revoked.json()['revoked'] is True,revoked.json().get('error')
        assert len(at_epoch_exit)==1 and _head(world).read_bytes()==at_epoch_exit[0]
        if _head(world).read_bytes()!=before:
            assert accepted.status_code==200 or accepted.json().get('applied') is not True


def test_epoch_serializes_independent_sessions_without_holding_keys(tmp_path):
    first=UserOwnedKeySession(tmp_path/'keys');first.create(protection='passphrase',passphrase=PASSPHRASE)
    first.ensure_data_key('authored-tenant','authored-case')
    second=UserOwnedKeySession(first.directory);second.unlock_passphrase(PASSPHRASE)
    binding=PrivateArtifactBinding(tenant_id='authored-tenant',case_id='authored-case',
        principal_id='authored-tenant',artifact_kind='session',revision='session-v1')
    attempted,entered=Event(),Event()
    def competing():
        attempted.set()
        with second.case_key_epoch_scope('authored-tenant','authored-case'):
            entered.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        with first.case_key_epoch_scope('authored-tenant','authored-case'):
            with first.case_key_epoch_scope('authored-tenant','authored-case'):
                material=pool.submit(second.provider().resolve,binding)
                assert material.result(timeout=5)[0]==first.provider().resolve(binding)[0]
            blocked=pool.submit(competing)
            assert attempted.wait(5)
            assert not entered.wait(.1)
        blocked.result(timeout=5)
        assert entered.is_set()


@pytest.mark.parametrize('damage',['mode','symlink'])
def test_epoch_refuses_unsafe_existing_lock_without_repair(tmp_path,damage):
    session=UserOwnedKeySession(tmp_path/'keys');session.create(protection='passphrase',passphrase=PASSPHRASE)
    with session.case_key_epoch_scope('authored-tenant','authored-case'):
        pass
    locks=list(session.directory.glob('.case-epoch-*.lock'));assert len(locks)==1
    path=locks[0]
    if damage=='mode':
        path.chmod(0o660)
    else:
        path.unlink();target=tmp_path/'sentinel';target.write_bytes(b'authored untouched sentinel');path.symlink_to(target)
    before=(path.lstat().st_mode,path.lstat().st_ino)
    with pytest.raises((PrivateStorageError,OSError)):
        with session.case_key_epoch_scope('authored-tenant','authored-case'):
            pytest.fail('unsafe epoch lock admitted')
    assert (path.lstat().st_mode,path.lstat().st_ino)==before
    if damage=='symlink':assert target.read_bytes()==b'authored untouched sentinel'
