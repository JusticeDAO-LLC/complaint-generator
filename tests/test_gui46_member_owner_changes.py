"""Real encrypted Member store lifecycle; no provider or key-rotation claims.

The Assignment HTTP tests separately qualify actual Cookie/key-owner effects.
Callbacks below are explicitly inert publication refusals at the real writer.
"""
from copy import deepcopy
import json
import os
import threading
from pathlib import Path

import pytest

from applications import case_membership as module
from applications.case_membership import CaseMembershipStore, CaseMembershipError
from tests.test_cimp_gui_10 import _world, _invite

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


@pytest.fixture
def world(tmp_path):
    store,key,principals,cases,owner,lawyer,admin,stranger,case,other,clock=_world(tmp_path)
    pending=_invite(store,owner,lawyer,case)
    grant=store.accept(member_principal_id=lawyer.principal_id,grant_id=pending.grant_id,
        expected_version=pending.version,idempotency_key='accept-member')
    return dict(store=store,key=key,principals=principals,cases=cases,owner=owner,lawyer=lawyer,
        admin=admin,stranger=stranger,case=case,other=other,clock=clock,grant=grant)


def _cold(w):
    return CaseMembershipStore(w['store']._root,key=w['key'],key_id='membership-key',
        principals=w['principals'],cases=w['cases'],clock=lambda:w['clock']['now'])


def _prepare(w,store=None,**changes):
    args=dict(owner_principal_id=w['owner'].principal_id,grant_id=w['grant'].grant_id,
        expected_version=w['grant'].version,idempotency_key='strict-private-owner-change')
    args.update(changes)
    return (store or w['store']).prepare_owner_change(**args)


def _finish(w,op,store=None,**changes):
    return (store or w['store']).finish_owner_change(owner_principal_id=w['owner'].principal_id,
        grant_id=w['grant'].grant_id,operation_id=op['operation']['operation_id'],**changes)


def _bytes(store):
    return {p.name:p.read_bytes() for p in (store._root/'grants').iterdir() if p.is_file()}


def test_real_encrypted_prepare_cold_replay_finish_and_current_grant_history(world):
    w=world;store=w['store'];original=store._grant_path(w['grant'].grant_id).read_bytes()
    assert not original.startswith(b'{')
    prepared=_prepare(w,actions={'case.read'},expires_at=w['clock']['now']+5000)
    assert not prepared['replayed'] and prepared['operation']['phase']=='prepared'
    raw=store._grant_path(w['grant'].grant_id).read_bytes()
    assert raw.startswith(b'{') and b'strict-private-owner-change' not in raw
    cold=_cold(w)
    replay=_prepare(w,cold,actions={'case.read'},expires_at=w['clock']['now']+5000)
    assert replay['replayed'] and replay['operation']==prepared['operation']
    assert replay['grant'].version==w['grant'].version
    completed=_finish(w,prepared,cold)
    assert completed['operation']['phase']=='complete' and not completed['replayed']
    assert completed['grant'].version==w['grant'].version+1
    assert completed['grant'].actions==('case.read',)
    audit=completed['operation']['audit']
    assert audit['confirmed'] is True and audit['revision']==completed['grant'].version
    assert audit['prior_scope']==list(w['grant'].actions)
    assert audit['effect_metadata']=={}  # No external crypto was claimed.
    after=_cold(w)
    second=_finish(w,prepared,after)
    assert second['replayed'] and second['operation']==completed['operation']
    assert after.load(w['grant'].grant_id).owner_changes==(completed['operation'],)
    with pytest.raises(CaseMembershipError,match='replay_mismatch'):
        _prepare(w,after,actions={'case.read','case.review'},expires_at=w['clock']['now']+5000)


def test_stored_revoke_cutoff_survives_cold_retry_without_becoming_request_authority(world):
    w=world;prepared=_prepare(w,revoke=True,revoke_cutoff=1)
    replay=_prepare(w,_cold(w),revoke=True,revoke_cutoff=999)
    assert replay['replayed'] and replay['operation']==prepared['operation']
    assert replay['operation']['revoke_cutoff']==1
    completed=_finish(w,prepared,effect_metadata={})
    assert completed['grant'].status=='removed'
    assert completed['operation']['effect_metadata']=={}
    assert not completed['operation']['audit']['effect_metadata'].get('data_key_rotated',False)


def test_upgraded_sole_record_does_not_depend_on_legacy_routing_sidecars(world):
    w=world;prepared=_prepare(w,actions={'case.read'});completed=_finish(w,prepared)
    directory=w['store']._root/'grants'
    for suffix in ('revision','tenant','case'):
        (directory/f"{w['grant'].grant_id}.{suffix}").unlink()
    loaded=_cold(w).load(w['grant'].grant_id)
    assert loaded.version==completed['grant'].version and loaded.owner_changes==completed['grant'].owner_changes
    assert _finish(w,prepared,_cold(w))['replayed'] is True


@pytest.mark.parametrize('field,value',[('version',99),('tenant_id','forged-tenant'),('case_id','forged-case')])
def test_untrusted_upgraded_routing_cannot_select_a_different_authenticated_binding(world,field,value):
    w=world;_prepare(w,actions={'case.read'})
    path=w['store']._grant_path(w['grant'].grant_id)
    wrapper=json.loads(path.read_bytes());wrapper[field]=value
    path.write_text(json.dumps(wrapper));path.chmod(0o600)
    with pytest.raises(CaseMembershipError):_cold(w).load(w['grant'].grant_id)


def test_actor_key_is_global_across_grants_and_changed_payload_never_rescopes(world):
    w=world;first=_prepare(w,actions={'case.read'})
    second_case=w['cases'].create_case(actor_principal_id=w['owner'].principal_id)
    second=_invite(w['store'],w['owner'],w['lawyer'],second_case,key='second-invite')
    with pytest.raises(CaseMembershipError,match='replay_mismatch'):
        _prepare(w,grant_id=second.grant_id,expected_version=second.version,actions={'case.read'})
    for actor in (w['lawyer'],w['stranger'],w['admin']):
        with pytest.raises(CaseMembershipError):
            _prepare(w,owner_principal_id=actor.principal_id,actions={'case.read'})
    assert _cold(w).load(w['grant'].grant_id).owner_changes==(first['operation'],)


def test_prepared_scope_denies_open_and_late_member_use_and_competing_edits(world):
    w=world;g=w['grant'];store=w['store']
    args=dict(actor_principal_id=w['lawyer'].principal_id,grant_id=g.grant_id,tenant_id=g.tenant_id,
        case_id=g.case_id,resource_id=g.resource_id,action='case.read',expected_version=g.version)
    ticket=store.begin_request(**args,request_id='open-before-owner-change')
    _prepare(w,actions={'case.read'})
    for call in (lambda:store.authorize(**args),lambda:store.begin_request(**args,request_id='later'),
        lambda:store.finish_request(ticket),
        lambda:store.update_scope(owner_principal_id=w['owner'].principal_id,grant_id=g.grant_id,
            expected_version=g.version,actions={'case.read'}),
        lambda:store.remove(owner_principal_id=w['owner'].principal_id,grant_id=g.grant_id,expected_version=g.version),
        lambda:_prepare(w,idempotency_key='another-change',actions={'case.read','case.review'})):
        with pytest.raises(CaseMembershipError,match='owner_change_pending'):call()


@pytest.mark.parametrize('stage',['prepare','finish'])
def test_real_crypto_and_temp_sync_precede_publication_refusal_without_record_changes(world,monkeypatch,stage):
    w=world;prepared=_prepare(w,actions={'case.read'}) if stage=='finish' else None
    before=_bytes(w['store']);sealed=[];synced=[]
    real_seal=module.seal_private_artifact;real_sync=module.os.fsync
    def seal(*args,**kwargs):
        result=real_seal(*args,**kwargs);sealed.append(True);return result
    def fsync(fd):
        path=Path(os.readlink(f'/proc/self/fd/{fd}'))
        result=real_sync(fd)
        if path.name.endswith('.tmp'):synced.append(path)
        return result
    def refuse():
        assert sealed and synced and synced[-1].is_file()
        assert _bytes(w['store'])=={**before,synced[-1].name:synced[-1].read_bytes()}
        raise CaseMembershipError('explicit_inert_publication_refusal')
    monkeypatch.setattr(module,'seal_private_artifact',seal);monkeypatch.setattr(module.os,'fsync',fsync)
    with pytest.raises(CaseMembershipError,match='explicit_inert_publication_refusal'):
        if stage=='prepare':_prepare(w,actions={'case.read'},before_publish=refuse)
        else:_finish(w,prepared,before_publish=refuse)
    assert _bytes(w['store'])==before
    assert not list((w['store']._root/'grants').glob('*.tmp'))


def test_cold_historical_replay_does_not_reset_later_scope_and_history_is_finite(world,monkeypatch):
    w=world;monkeypatch.setattr(module,'OWNER_OPERATION_LIMIT',2)
    first=_prepare(w,actions={'case.read'});one=_finish(w,first)
    second=_prepare(w,expected_version=one['grant'].version,idempotency_key='second-change',
        actions={'case.read','case.review'});two=_finish(w,second)
    replay=_prepare(w,_cold(w),actions={'case.read'})
    assert replay['replayed'] and replay['operation']==one['operation']
    assert replay['grant'].version==two['grant'].version and replay['grant'].actions==two['grant'].actions
    before=_bytes(w['store'])
    with pytest.raises(CaseMembershipError,match='owner_change_history_full'):
        _prepare(w,expected_version=two['grant'].version,idempotency_key='third-change',actions={'case.read'})
    assert _bytes(w['store'])==before


def test_coordination_lock_is_distinct_and_concurrent_exact_requests_complete_once(world):
    w=world;returned=[];errors=[];barrier=threading.Barrier(2)
    with w['store'].owner_change_scope():
        thread=threading.Thread(target=lambda:returned.append(w['store'].load(w['grant'].grant_id)))
        thread.start();thread.join(2);assert not thread.is_alive()
    assert len(returned)==1;returned.clear()
    def run():
        try:
            store=_cold(w);barrier.wait()
            with store.owner_change_scope():
                prepared=_prepare(w,store,actions={'case.read'})
                returned.append(_finish(w,prepared,store))
        except BaseException as exc:errors.append(exc)
    threads=[threading.Thread(target=run) for _ in range(2)]
    for thread in threads:thread.start()
    for thread in threads:thread.join(5);assert not thread.is_alive()
    assert not errors and len(returned)==2
    assert sorted(item['replayed'] for item in returned)==[False,True]
    loaded=_cold(w).load(w['grant'].grant_id)
    assert loaded.version==w['grant'].version+1 and len(loaded.owner_changes)==1


def test_publication_scope_joins_only_current_prepared_owner_case_and_completed_replay_rechecks_callback(world):
    w=world;prepared=_prepare(w,actions={'case.read'});op=prepared['operation']['operation_id']
    args=dict(owner_principal_id=w['owner'].principal_id,grant_id=w['grant'].grant_id,operation_id=op)
    with w['store'].owner_change_publication_scope(**args) as grant:
        assert grant.grant_id==w['grant'].grant_id and grant.version==w['grant'].version
    for changes in ({'owner_principal_id':w['lawyer'].principal_id},{'operation_id':'wrong-operation'}):
        with pytest.raises(CaseMembershipError):
            with w['store'].owner_change_publication_scope(**{**args,**changes}):pass
    _finish(w,prepared)
    with pytest.raises(CaseMembershipError,match='owner_change_not_pending'):
        with w['store'].owner_change_publication_scope(**args):pass
    before=_bytes(w['store'])
    def refuse():raise CaseMembershipError('explicit_expired_response_scope')
    with pytest.raises(CaseMembershipError,match='explicit_expired_response_scope'):
        _finish(w,prepared,_cold(w),before_publish=refuse)
    assert _bytes(w['store'])==before


@pytest.mark.parametrize('effect',[{'private_key':'forbidden'}, {'data_key_rotated':'true'}, {'cutoff':False}])
def test_effect_metadata_is_closed_and_not_a_client_payload_channel(world,effect):
    w=world;prepared=_prepare(w,revoke=True,revoke_cutoff=1);before=_bytes(w['store'])
    with pytest.raises(CaseMembershipError,match='operation_effect_metadata'):
        _finish(w,prepared,effect_metadata=effect)
    assert _bytes(w['store'])==before


@pytest.mark.parametrize('stage',['prepare','prepare_replay','finish','finish_replay','invite_replay','accept_replay'])
def test_explicit_false_trusted_hook_denies_publication_and_replay_without_changing_records(world,stage):
    w=world;prepared=None
    if stage in {'prepare_replay','finish','finish_replay'}:
        prepared=_prepare(w,actions={'case.read'})
    if stage=='finish_replay':_finish(w,prepared)
    before=_bytes(w['store']);calls=[]
    def deny():calls.append(True);return False
    with pytest.raises(CaseMembershipError,match='publication_denied'):
        if stage in {'prepare','prepare_replay'}:
            _prepare(w,actions={'case.read'},before_publish=deny)
        elif stage in {'finish','finish_replay'}:
            _finish(w,prepared,before_publish=deny)
        elif stage=='invite_replay':
            w['store'].invite(owner_principal_id=w['owner'].principal_id,
                member_principal_id=w['lawyer'].principal_id,case_id=w['case'].case_id,
                resource_id=w['case'].resource_id,tenant_id=w['case'].tenant_id,
                actions={'case.read','case.review'},expires_at=1_700_003_600,
                expected_case_revision=w['case'].revision,idempotency_key='invite-1',before_publish=deny)
        else:
            w['store'].accept(member_principal_id=w['lawyer'].principal_id,grant_id=w['grant'].grant_id,
                expected_version=w['grant'].version,idempotency_key='accept-member',before_publish=deny)
    assert calls==[True] and _bytes(w['store'])==before
    assert not list((w['store']._root/'grants').glob('*.tmp'))
