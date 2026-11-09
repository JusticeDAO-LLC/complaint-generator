"""Actual encrypted proposal to canonical private factual correction."""
from copy import deepcopy
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import json
import os

import pytest
from fastapi.testclient import TestClient

from complaint_phases.knowledge_graph import KnowledgeGraph
from tests.test_cimp_gui_14 import _composed_login, _composed_headers, PASSPHRASE
from tests.test_gui18_private_publication import _prepare, CORRECTION, ANSWER
from tests.test_gui32_private_review_http import _world as _review_world, _headers as _lawyer_headers

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _world(tmp_path, *, with_support=False):
    world = _review_world(tmp_path, actual_workspace_as_mediator=True)
    world.owner_keys.unlock_passphrase(PASSPHRASE)
    world.service.unlock_private_keys(passphrase=PASSPHRASE)
    with TestClient(world.review_app, base_url='https://testserver') as owner:
        csrf = _composed_login(owner)
        current = owner.get('/api/complaint-workspace/session', headers=_composed_headers(world.case))
        assert current.status_code == 200, current.text
        pending = current.json()['session']['shared_interview']['pending_inquiry']
        answered = owner.post('/api/complaint-workspace/intake-chat', headers=_composed_headers(world.case, csrf),
            json={'message':ANSWER,'question_id':pending['inquiry_id'],
                  'expected_question_revision':pending['revision'],'interview_action':'answer'})
        assert answered.status_code == 200, answered.text
        offer = answered.json()['adaptive_inquiry']['factual_correction']
        assert offer['actor_principal_id'] == world.owner.principal_id
        if with_support:
            # Authored operator fixture: an unverified cached support edge is
            # deliberately retained so the actual correction must invalidate
            # it. Its flags grant no case, source, proof or law authority.
            from complaint_phases.knowledge_graph import Entity, Relationship
            state = owner.get('/api/complaint-workspace/session', headers=_composed_headers(world.case)).json()['session']
            graph = KnowledgeGraph.from_dict(state['shared_interview']['knowledge_graph'])
            fact_id = graph.factual_ledger()['assertion_states'][offer['target_stable_id']]['entity_id']
            claim_id = 'synthetic-review-cache-claim'
            graph.add_entity(Entity(id=claim_id, type='claim', name='Authored cache invalidation control'))
            graph.add_relationship(Relationship(id='synthetic-review-cache-support', source_id=fact_id,
                target_id=claim_id, relation_type='supports', attributes={
                    'proof_cache':{'reusable':True,'satisfied':True,'fact_id':fact_id},
                    'proof_cache_entity_id':fact_id}))
            state['shared_interview']['knowledge_graph'] = graph.to_dict()
            world.service._save_state(state)
        path = '/api/legal-analysis/' + world.case.case_id
        status = owner.get(path + '/lawyer-reviews/sharing', headers=_composed_headers(world.case))
        assert status.status_code == 200, status.text
        shared = owner.post(path + '/lawyer-reviews/share', headers=_composed_headers(world.case, csrf),
            json={'membership_id':world.membership.grant_id, 'expected_membership_version':world.membership.version,
                  'expected_private_revision':status.json()['private_revision']})
        assert shared.status_code == 200, shared.text
    with TestClient(world.review_app, base_url='https://testserver') as lawyer:
        csrf = _composed_login(lawyer, 'synthetic-lawyer-credential')
        view = lawyer.get(path + '/review-items', headers=_lawyer_headers(world))
        assert view.status_code == 200, view.text
        live = view.json()['live_revisions']
        proposed = lawyer.post(path + '/review-items', headers=_lawyer_headers(world, csrf), json={
            'operation':'create_proposal', 'request_id':'synthetic-factual-proposal',
            'body':'Please correct the accepted factual answer.', 'target_kind':'fact',
            'target_id':offer['target_stable_id'], 'proposed_text':CORRECTION,
            'expected_review_revision':view.json()['review_revision'],
            **{'expected_'+name:live[name] for name in ('case_revision','source_revision','fact_revision','proof_revision')}})
        assert proposed.status_code == 200, proposed.text
    with TestClient(world.review_app, base_url='https://testserver') as owner:
        _composed_login(owner)
        response = owner.get('/api/complaint-workspace/session', headers=_composed_headers(world.case))
        assert response.status_code == 200, response.text
        state = response.json()['session']
    request = {'proposal_id':proposed.json()['record']['item_id'], 'request_id':'synthetic-owner-accept',
        'expected_review_revision':proposed.json()['review_revision'],
        'expected_private_revision':state['private_revision'],
        'expected_session_revision':state['shared_interview']['session_revision']}
    return world, offer, request


def _accept(client, world, csrf, request):
    return client.post('/api/legal-analysis/' + world.case.case_id + '/review-transitions',
        headers=_composed_headers(world.case, csrf), json=request)


def _state(client, world):
    response = client.get('/api/complaint-workspace/session', headers=_composed_headers(world.case))
    assert response.status_code == 200, response.text
    return response.json()['session']


def _head(world):
    return world.service.joined_revision_repository(world.case.tenant_id, world.case.case_id) / 'head.cgpe'


def test_public_review_acceptance_supersedes_private_fact_and_replays_without_another_commit(tmp_path):
    world, offer, request = _world(tmp_path, with_support=True)
    with TestClient(world.review_app, base_url='https://testserver') as client:
        csrf = _composed_login(client)
        before = _head(world).read_bytes()
        prior_graph = KnowledgeGraph.from_dict(_state(client, world)['shared_interview']['knowledge_graph'])
        prior_envelope = deepcopy(prior_graph.assertion_state(offer['target_stable_id'])['envelope'])
        accepted = _accept(client, world, csrf, request)
        assert accepted.status_code == 200, accepted.text
        receipt = accepted.json()
        assert receipt['applied'] is True and receipt['status'] == 'accepted', receipt
        assert receipt['accepting_owner_actor'] == world.owner.principal_id != world.case.tenant_id
        assert receipt['review_status_repository_updated'] is False
        state = _state(client, world)
        graph = KnowledgeGraph.from_dict(state['shared_interview']['knowledge_graph'])
        assert graph.assertion_state(offer['target_stable_id'])['status'] == 'superseded'
        assert graph.assertion_state(offer['target_stable_id'])['envelope'] == prior_envelope
        assert graph.assertion_state(receipt['replacement_stable_id'])['status'] == 'active'
        support = graph.relationships['synthetic-review-cache-support']
        assert support.attributes['proof_cache']['reusable'] is False
        assert support.attributes['proof_cache']['satisfied'] is False
        assert receipt['invalidated_support_targets']
        assert state['canonical_review_acceptances'][request['request_id']]['receipt_sha256'] == receipt['receipt_sha256']
        assert state['private_revision'] == receipt['result_private_revision']
        assert int(state['private_revision']) == int(request['expected_private_revision']) + 1
        committed = _head(world).read_bytes()
        assert committed != before
        replay = _accept(client, world, csrf, request)
        assert replay.status_code == 200, replay.text
        assert replay.json()['applied'] is False and replay.json()['replayed'] is True
        assert replay.json()['historically_applied'] is True and replay.json()['current_result'] is True
        assert _head(world).read_bytes() == committed
        changed = _accept(client, world, csrf, {**request, 'expected_session_revision':request['expected_session_revision']+1})
        assert changed.status_code == 409, changed.text
        assert _head(world).read_bytes() == committed


@pytest.mark.parametrize('key_owner', ['workspace', 'review_owner'])
def test_locked_real_owner_key_cannot_accept_or_publish_a_receipt(tmp_path, key_owner):
    world, _offer, request = _world(tmp_path)
    before = _head(world).read_bytes()
    if key_owner == 'workspace':
        world.service.lock_private_keys()
    else:
        world.owner_keys.lock()
    with TestClient(world.review_app, base_url='https://testserver') as client:
        csrf = _composed_login(client)
        response = _accept(client, world, csrf, request)
        assert response.status_code in {401, 403, 409, 503}, response.text
        assert response.json().get('applied') is not True
    assert _head(world).read_bytes() == before


def test_assigned_lawyer_cannot_adopt_with_unlocked_owner_keys(tmp_path):
    world, _offer, request = _world(tmp_path)
    before = _head(world).read_bytes()
    assert world.owner_keys.unlocked and world.service.private_key_status()['unlocked']
    with TestClient(world.review_app, base_url='https://testserver') as lawyer:
        csrf = _composed_login(lawyer, 'synthetic-lawyer-credential')
        response = _accept(lawyer, world, csrf, request)
        assert response.status_code == 403, response.text
        assert CORRECTION not in response.text
    assert _head(world).read_bytes() == before


def test_actual_new_owner_answer_makes_old_proposal_preconditions_stale(tmp_path):
    world, offer, request = _world(tmp_path)
    with TestClient(world.review_app, base_url='https://testserver') as client:
        csrf = _composed_login(client)
        current = _state(client, world)
        pending = current['shared_interview']['pending_inquiry']
        assert pending is not None
        changed = client.post('/api/complaint-workspace/intake-chat', headers=_composed_headers(world.case, csrf),
            json={'message':'I submitted the report to the safety office.','question_id':pending['inquiry_id'],
                'expected_question_revision':pending['revision'],'interview_action':'answer'})
        assert changed.status_code == 200, changed.text
        before = _head(world).read_bytes()
        refused = _accept(client, world, csrf, request)
        assert refused.status_code == 409, refused.text
        assert _head(world).read_bytes() == before
        state = _state(client, world)
        assert request['request_id'] not in state.get('canonical_review_acceptances', {})
        assert KnowledgeGraph.from_dict(state['shared_interview']['knowledge_graph']).assertion_state(offer['target_stable_id'])['status'] == 'active'


def test_concurrent_acceptance_has_one_actual_factual_commit(tmp_path, monkeypatch):
    from mediator.mediator import Mediator
    world, offer, request = _world(tmp_path)
    barrier = Barrier(2)
    original = Mediator.apply_factual_correction
    def concurrent(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        assert result.get('status') == 'applied'
        barrier.wait(timeout=20)
        return result
    monkeypatch.setattr(Mediator, 'apply_factual_correction', concurrent)
    with TestClient(world.review_app, base_url='https://testserver') as client:
        csrf = _composed_login(client)
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: _accept(client, world, csrf, request), range(2)))
        assert sum(r.status_code == 200 and r.json().get('applied') is True for r in replies) == 1
        assert all(r.status_code in {200, 409} for r in replies), [r.text for r in replies]
        state = _state(client, world)
        assert int(state['private_revision']) == int(request['expected_private_revision']) + 1
        assert len(state['canonical_review_acceptances']) == 1
        assert KnowledgeGraph.from_dict(state['shared_interview']['knowledge_graph']).assertion_state(offer['target_stable_id'])['status'] == 'superseded'


def test_real_review_cas_change_during_correction_prevents_canonical_publication(tmp_path, monkeypatch):
    from mediator.mediator import Mediator
    from integrations import private_storage
    world, _offer, request = _world(tmp_path)
    reached, release = Event(), Event()
    original = Mediator.apply_factual_correction
    def paused(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        reached.set()
        assert release.wait(20)
        return result
    monkeypatch.setattr(Mediator, 'apply_factual_correction', paused)
    before = _head(world).read_bytes()
    repository = _head(world).parent
    commits = private_storage._native_commit_transactions(repository)
    with TestClient(world.review_app, base_url='https://testserver') as owner, TestClient(world.review_app, base_url='https://testserver') as lawyer:
        csrf = _composed_login(owner)
        lawyer_csrf = _composed_login(lawyer, 'synthetic-lawyer-credential')
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(_accept, owner, world, csrf, request)
            try:
                assert reached.wait(20)
                path = '/api/legal-analysis/' + world.case.case_id + '/review-items'
                view = lawyer.get(path, headers=_lawyer_headers(world))
                assert view.status_code == 200, view.text
                live = view.json()['live_revisions']
                dissent = lawyer.post(path, headers=_lawyer_headers(world, lawyer_csrf), json={
                    'operation':'dissent','request_id':'synthetic-late-dissent','proposal_id':request['proposal_id'],
                    'body':'Keep the original date pending another record.',
                    'expected_review_revision':view.json()['review_revision'],
                    **{'expected_'+name:live[name] for name in ('case_revision','source_revision','fact_revision','proof_revision')}})
                assert dissent.status_code == 200, dissent.text
            finally:
                release.set()
            response = pending.result(timeout=20)
        assert response.status_code == 409, response.text
        assert _head(world).read_bytes() == before
        assert private_storage._native_commit_transactions(repository) == commits
        state = _state(owner, world)
        assert request['request_id'] not in state.get('canonical_review_acceptances', {})


@pytest.mark.parametrize('boundary', ['logout', 'workspace_key', 'review_owner_key'])
def test_actual_head_temp_publication_rechecks_owner_and_review_key(tmp_path, monkeypatch, boundary):
    from integrations import private_storage
    world, _offer, request = _world(tmp_path)
    reached, release = Event(), Event()
    original = private_storage._fsync_file
    repository = _head(world).parent
    before = _head(world).read_bytes()
    commits = private_storage._native_commit_transactions(repository)
    def paused(descriptor, operation):
        original(descriptor, operation)
        path = Path(os.readlink(f'/proc/self/fd/{descriptor}'))
        if path.parent == repository and path.read_bytes().startswith(private_storage._HEAD_RECORD_MAGIC):
            reached.set()
            assert release.wait(20)
    monkeypatch.setattr(private_storage, '_fsync_file', paused)
    with TestClient(world.review_app, base_url='https://testserver') as owner:
        csrf = _composed_login(owner)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(_accept, owner, world, csrf, request)
            try:
                assert reached.wait(20), 'Actual canonical head boundary was not reached.'
                if boundary == 'logout':
                    assert owner.post('/api/complaint-workspace/auth/logout', headers={'x-csrf-token':csrf}).status_code == 200
                elif boundary == 'workspace_key':
                    world.service.lock_private_keys()
                else:
                    world.owner_keys.lock()
            finally:
                release.set()
            response = pending.result(timeout=20)
        assert response.status_code in {401, 403, 409, 503}, response.text
        assert CORRECTION not in response.text
        assert _head(world).read_bytes() == before
        assert private_storage._native_commit_transactions(repository) == commits
    world.service.unlock_private_keys(passphrase=PASSPHRASE)
    world.service.recover_joined_intake_revision(world.case.tenant_id, case_id=world.case.case_id)
    assert _head(world).read_bytes() == before


def test_interrupted_actual_head_write_recovers_without_receipt_then_identical_retry_commits(tmp_path, monkeypatch):
    from integrations import private_storage
    world, offer, request = _world(tmp_path)
    original = private_storage._fsync_file
    repository = _head(world).parent
    before = _head(world).read_bytes()
    commits = private_storage._native_commit_transactions(repository)
    fired = False
    def interrupted(descriptor, operation):
        nonlocal fired
        original(descriptor, operation)
        path = Path(os.readlink(f'/proc/self/fd/{descriptor}'))
        if not fired and path.parent == repository and path.read_bytes().startswith(private_storage._HEAD_RECORD_MAGIC):
            fired = True
            raise private_storage.PrivateRevisionInterrupted('synthetic-head-temp', 'synthetic-transaction')
    monkeypatch.setattr(private_storage, '_fsync_file', interrupted)
    with TestClient(world.review_app, base_url='https://testserver') as owner:
        csrf = _composed_login(owner)
        response = _accept(owner, world, csrf, request)
        assert fired and response.status_code >= 400, response.text
        assert _head(world).read_bytes() == before
        assert private_storage._native_commit_transactions(repository) == commits
        monkeypatch.setattr(private_storage, '_fsync_file', original)
        world.service.recover_joined_intake_revision(world.case.tenant_id, case_id=world.case.case_id)
        world.service.recover_joined_intake_revision(world.case.tenant_id, case_id=world.case.case_id)
        assert _head(world).read_bytes() == before
        assert request['request_id'] not in _state(owner, world).get('canonical_review_acceptances', {})
        retried = _accept(owner, world, csrf, request)
        assert retried.status_code == 200 and retried.json()['applied'] is True, retried.text
        state = _state(owner, world)
        assert int(state['private_revision']) == int(request['expected_private_revision']) + 1
        assert KnowledgeGraph.from_dict(state['shared_interview']['knowledge_graph']).assertion_state(offer['target_stable_id'])['status'] == 'superseded'


@pytest.mark.parametrize('kind', ['legal_admission', 'draft_revision'])
def test_unimplemented_target_owners_refuse_instead_of_adopting_shadow_state(tmp_path, kind):
    world, _offer, request = _world(tmp_path)
    path = '/api/legal-analysis/' + world.case.case_id
    with TestClient(world.review_app, base_url='https://testserver') as lawyer:
        csrf = _composed_login(lawyer, 'synthetic-lawyer-credential')
        view = lawyer.get(path + '/review-items', headers=_lawyer_headers(world)).json()
        live = view['live_revisions']
        proposal = lawyer.post(path + '/review-items', headers=_lawyer_headers(world, csrf), json={
            'operation':'create_proposal','request_id':'synthetic-unsupported-proposal','body':'Capability refusal control.',
            'target_kind':kind,'target_id':'synthetic-unimplemented-target','proposed_text':'Authored proposed text.',
            'expected_review_revision':view['review_revision'],
            **{'expected_'+name:live[name] for name in ('case_revision','source_revision','fact_revision','proof_revision')}})
        assert proposal.status_code == 200, proposal.text
    with TestClient(world.review_app, base_url='https://testserver') as owner:
        csrf = _composed_login(owner)
        before = _head(world).read_bytes()
        refused = _accept(owner, world, csrf, {**request, 'request_id':'synthetic-unsupported-accept',
            'proposal_id':proposal.json()['record']['item_id'],'expected_review_revision':proposal.json()['review_revision']})
        assert refused.status_code == 503, refused.text
        assert refused.json()['error'] == 'review_target_capability_unavailable'
        assert refused.json().get('applied') is not True
        assert _head(world).read_bytes() == before


def test_typed_preconditions_and_json_cannot_supply_a_review_or_authority_object(tmp_path):
    world, _offer, request = _world(tmp_path)
    with TestClient(world.review_app, base_url='https://testserver') as owner:
        csrf = _composed_login(owner)
        before = _head(world).read_bytes()
        for changes in [
            {'expected_review_revision':True}, {'expected_session_revision':False},
            {'expected_private_revision':int(request['expected_private_revision'])},
            {'proposal_id':{'target_id':'synthetic-forged','proposed_text':'Forged body object.'}},
            {'review_service':{'trusted_local':True}}, {'_review_acceptance':{'authorized':True}},
        ]:
            refused = _accept(owner, world, csrf, {**request, **changes})
            assert refused.status_code in {403,422}, refused.text
            assert refused.json().get('applied') is not True
            assert _head(world).read_bytes() == before


def test_identical_receipt_replay_after_later_facts_is_historical_and_does_not_write(tmp_path):
    world, _offer, request = _world(tmp_path)
    with TestClient(world.review_app, base_url='https://testserver') as owner:
        csrf = _composed_login(owner)
        accepted = _accept(owner, world, csrf, request)
        assert accepted.status_code == 200 and accepted.json()['applied'] is True, accepted.text
        state = _state(owner, world)
        pending = state['shared_interview']['pending_inquiry']
        assert pending is not None
        changed = owner.post('/api/complaint-workspace/intake-chat', headers=_composed_headers(world.case, csrf),
            json={'message':'I sent the signed report to the safety office.','question_id':pending['inquiry_id'],
                  'expected_question_revision':pending['revision'],'interview_action':'answer'})
        assert changed.status_code == 200, changed.text
        before = _head(world).read_bytes()
        replay = _accept(owner, world, csrf, request)
        assert replay.status_code == 200, replay.text
        assert replay.json()['applied'] is False and replay.json()['historically_applied'] is True
        assert replay.json()['current_result'] is False
        assert replay.json()['result_private_revision'] == accepted.json()['result_private_revision']
        assert int(replay.json()['current_private_revision']) > int(replay.json()['result_private_revision'])
        assert _head(world).read_bytes() == before
