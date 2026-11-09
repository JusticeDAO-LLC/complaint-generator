"""Finite review actions and trusted publication refusal use real crypto."""
import os
import pytest

from integrations.private_collaboration import CaseResourceKeyGrantError
from integrations.private_storage import private_revision_source_scope,PrivateRevisionError
from tests.test_cimp_gui_11 import _world,_accept,_issue,ARTIFACT_KIND,REVISION

pytestmark=[pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


def test_real_grant_issue_and_idempotent_replay_both_honor_trusted_refusal(tmp_path):
    world=_world(tmp_path);member=_accept(world);case=world['case'];grants=world['grants']
    kwargs=dict(actor_principal_id=world['owner'].principal_id,recipient_principal_id=world['lawyer'].principal_id,
        membership_grant_id=member.grant_id,membership_version=member.version,case_id=case.case_id,
        resource_id=case.resource_id,tenant_id=case.tenant_id,artifact_kind=ARTIFACT_KIND,artifact_revision=REVISION,
        owner_session=world['owner_session'],recipient_session=world['recipient_session'],idempotency_key='synthetic-guarded-issue')
    with pytest.raises(CaseResourceKeyGrantError) as refused:
        grants.issue(**kwargs,before_publish=lambda:False)
    assert refused.value.code=='publication_denied'
    assert list((tmp_path/'key-grants/grants').glob('*.envelope'))==[]
    issued=grants.issue(**kwargs)
    path=tmp_path/'key-grants/grants'/str(issued.key_grant_id+'.envelope');before=path.read_bytes()
    with pytest.raises(CaseResourceKeyGrantError) as refused:
        grants.issue(**kwargs,before_publish=lambda:False)
    assert refused.value.code=='publication_denied' and path.read_bytes()==before
    assert grants.issue(**kwargs).key_grant_id==issued.key_grant_id


def test_review_action_does_not_broaden_default_message_write_or_arbitrary_actions(tmp_path):
    world=_world(tmp_path);member=_accept(world,actions={'case.read','case.review'});grant=_issue(world,member)
    case=world['case'];kwargs=dict(actor_principal_id=world['lawyer'].principal_id,
        membership_grant_id=member.grant_id,membership_version=member.version,key_grant_id=grant.key_grant_id,
        case_id=case.case_id,tenant_id=case.tenant_id,resource_id=case.resource_id,
        artifact_kind=ARTIFACT_KIND,artifact_revision=REVISION,recipient_session=world['recipient_session'])
    for action in (None,'case.update'):
        with pytest.raises(CaseResourceKeyGrantError):
            world['grants'].write_delegated(**kwargs,plaintext=b'Cannot broaden authority',**({} if action is None else {'action':action}))
    written=world['grants'].write_delegated(**kwargs,plaintext=b'Finite human review',action='case.review')
    opened=world['grants'].read_delegated(**kwargs,envelope=written['envelope'])
    assert opened['data']==b'Finite human review'
    admitted=world['grants'].admit_late_result(**kwargs,envelope=written['envelope'],prepared_generation=written['generation'],action='case.review')
    assert admitted['data']==b'Finite human review'


@pytest.mark.parametrize('changed',['root','lock'])
def test_opaque_source_hold_reproves_private_custody_without_claiming_authority(tmp_path,changed):
    from tests.test_gui32_private_review_http import _world as review_world
    world=review_world(tmp_path)
    root=world.service.joined_revision_repository(world.case.tenant_id,world.case.case_id)
    target=root if changed=='root' else root/'.owner.lock'
    old=target.stat().st_mode&0o777
    try:
        with pytest.raises(PrivateRevisionError) as refused:
            with private_revision_source_scope(root) as identity:
                assert identity['authority'] is False and identity['opaque_ciphertext_only'] is True
                os.chmod(target,0o770 if changed=='root' else 0o660)
        assert refused.value.code=='revision_conflict'
    finally:os.chmod(target,old)
