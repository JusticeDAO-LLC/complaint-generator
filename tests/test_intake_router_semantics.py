"""Real graph/source admission controls; authored backend output is never live evidence."""
import copy
import json
import uuid

import pytest

import integrations.ipfs_datasets.llm as llm
from complaint_phases.knowledge_graph import Entity, KnowledgeGraph, KnowledgeGraphBuilder
from complaint_phases.dependency_graph import DependencyGraph
from complaint_phases.phase_manager import ComplaintPhase
from integrations.ipfs_datasets.types import build_user_assertion_envelope, source_byte_hash, user_assertion_from_mapping
from mediator.mediator import Mediator

SOURCE = 'José paid café rent. José kept the receipt.'
USER = 'synthetic-route02-alice'
CASE = 'synthetic-route02-case-a'


class AuthoredBackend:
    id = 'authored-semantic-fixture'

    def __init__(self, text='not-json'):
        self.text = text
        self.calls = []

    def __call__(self, prompt, **kwargs):
        self.calls.append(kwargs)
        return self.text


def _fact(target='fact_original', *, start=0, value='José'):
    return {'field': 'party', 'value': value, 'source_start': start,
            'source_end': start + len(value.encode('utf-8')), 'target_ref': target}


def _body(request_id, *, facts=None, questions=None, operation='extract_facts'):
    return json.dumps({'schema_version': llm.INTAKE_REQUEST_SCHEMA_VERSION,
                      'operation': operation, 'request_id': request_id,
                      'facts': [] if facts is None else facts,
                      'questions': [] if questions is None else questions}, ensure_ascii=False)


def _user_context(text, identity='synthetic-message-a'):
    return {'source_text': text, 'source_kind': 'user_statement', 'source_id': identity,
            'message_id': identity, 'assertion_status': 'asserted',
            'extractor_version': 'route02-semantic-fixture',
            'source_hash': source_byte_hash(text),
            'source_span': {'start': 0, 'end': len(text.encode('utf-8')), 'text': text},
            'subject_key': 'synthetic-payment'}


@pytest.fixture
def canonical(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    backend = AuthoredBackend()
    mediator = Mediator([backend], evidence_db_path=tmp_path/'evidence.db',
                        legal_authority_db_path=tmp_path/'authority.db',
                        claim_support_db_path=tmp_path/'support.db')
    graph = KnowledgeGraph()
    envelope = build_user_assertion_envelope(**_user_context(SOURCE))
    assert envelope.is_asserted_user_fact
    fact = Entity(id='fact_original', type='fact', name=SOURCE,
                  attributes={'description': SOURCE}, confidence=1.0, source='complaint',
                  provenance={'user_assertion': envelope.as_dict()})
    graph.add_entity(fact)
    graph.register_assertion(fact, envelope, status='active')
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', graph)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', DependencyGraph())
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file',
                                             {'canonical_facts': [], 'candidate_claims': []})
    request_id = uuid.uuid4().hex
    mediator._router_request_id = request_id
    return mediator, graph, envelope, request_id


def _graph_state(mediator):
    kg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
    dg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
    return copy.deepcopy({'kg': kg.to_dict(), 'dg': dg.to_dict()})


def test_exact_utf8_span_keeps_repeated_source_occurrence_explicit():
    request_id = uuid.uuid4().hex
    second = SOURCE.encode('utf-8').rfind('José'.encode('utf-8'))
    parsed = llm.parse_intake_request(_body(request_id, facts=[_fact(start=second)]),
                                      request_id=request_id, operation='extract_facts', source_text=SOURCE, allowed_target_refs=('fact_original',))
    assert parsed['facts'][0]['source_start'] == second
    assert parsed['facts'][0]['value'] == 'José'


@pytest.mark.parametrize('fact', [
    _fact(start=1),
    {**_fact(), 'source_end': 4},
    {**_fact(), 'source_start': True},
    {**_fact(), 'source_start': -1},
    {**_fact(), 'source_end': len(SOURCE.encode('utf-8')) + 1},
    {**_fact(), 'assertion_verified': True},
])
def test_invalid_utf8_or_forged_assertion_fields_are_rejected(fact):
    request_id = uuid.uuid4().hex
    with pytest.raises(llm.IntakeContractError):
        llm.parse_intake_request(_body(request_id, facts=[fact]), request_id=request_id,
                                 operation='extract_facts', source_text=SOURCE, allowed_target_refs=('fact_original',))


@pytest.mark.parametrize('mutation', ['duplicate', 'nonfinite', 'oversize', 'unknown_field', 'nested_fact_type', 'nested_operation_type'])
def test_malformed_json_stays_typed_and_never_weakens_the_grammar(mutation):
    request_id = uuid.uuid4().hex
    body = _body(request_id, facts=[_fact()])
    if mutation == 'duplicate': body = body.replace('"facts":', '"facts": [], "facts":', 1)
    elif mutation == 'nonfinite': body = body.replace('"source_start": 0', '"source_start": NaN')
    elif mutation == 'oversize': body = '{"padding":"' + 'x' * llm.INTAKE_MAX_OUTPUT_BYTES + '"}'
    elif mutation == 'unknown_field': body = body[:-1] + ',"asserted":true}'
    elif mutation == 'nested_fact_type': body = _body(request_id, facts=[{**_fact(), 'field': []}])
    else: body = _body(request_id, operation=[])
    with pytest.raises(llm.IntakeContractError):
        llm.parse_intake_request(body, request_id=request_id, operation='extract_facts', source_text=SOURCE, allowed_target_refs=('fact_original',))


@pytest.mark.parametrize('field,value', [('operation', []), ('operation', {}), ('fact_field', []), ('fact_field', {})])
def test_host_fallback_rejects_unhashable_types_with_the_same_typed_error(field, value):
    request_id = uuid.uuid4().hex
    body = json.loads(_body(request_id, facts=[_fact()]))
    if field == 'operation': body['operation'] = value
    else: body['facts'][0]['field'] = value
    with pytest.raises(llm.IntakeContractError):
        llm._host_validate_intake_tree(body, request_id=request_id, operation='extract_facts', source_text=SOURCE, allowed_target_refs=('fact_original',))


@pytest.mark.parametrize('target', ['unknown-canonical-target', 'authority_source:foreign-law', 'fact_foreign_case'])
def test_unknown_foreign_or_legal_target_cannot_be_reported_applied(canonical, target):
    mediator, graph, envelope, request_id = canonical
    before = _graph_state(mediator)
    outcome = mediator.apply_intake_router_output(_body(request_id, facts=[_fact(target)]),
                operation='extract_facts', source_text=SOURCE, request_id=request_id)
    assert outcome['applied'] is False
    assert outcome['graph_changed'] is False
    assert _graph_state(mediator) == before
    assert graph.assertion_state(envelope.stable_id)['status'] == 'active'


def test_previous_request_identity_cannot_be_replayed_as_current_application(canonical):
    mediator, graph, envelope, old_request = canonical
    mediator._router_request_id = uuid.uuid4().hex
    before = _graph_state(mediator)
    outcome = mediator.apply_intake_router_output(_body(old_request, facts=[_fact()]),
                operation='extract_facts', source_text=SOURCE, request_id=old_request)
    assert outcome['applied'] is False
    assert outcome['graph_changed'] is False
    assert _graph_state(mediator) == before


def test_graph_change_receipt_reflects_canonical_graphs_not_an_ad_hoc_side_list(canonical):
    mediator, graph, envelope, request_id = canonical
    before = _graph_state(mediator)
    outcome = mediator.apply_intake_router_output(_body(request_id, facts=[_fact()]),
                operation='extract_facts', source_text=SOURCE, request_id=request_id)
    actual_change = _graph_state(mediator) != before
    assert outcome['graph_changed'] is actual_change
    # Model text cannot replace or manufacture this genuine user proof.
    assert graph.entities['fact_original'].provenance['user_assertion'] == envelope.as_dict()
    assert graph.assertion_state(envelope.stable_id)['status'] == 'active'


def test_rejected_repair_does_not_change_actual_graph_or_ledger(canonical):
    mediator, graph, envelope, request_id = canonical
    before = _graph_state(mediator)
    bad = '```json\n' + _body(request_id, facts=[_fact()]) + '\n```'
    outcome = mediator.apply_intake_router_output(bad, operation='extract_facts',
                                                source_text=SOURCE, request_id=request_id)
    assert outcome['applied'] is False
    assert outcome['intake_complete'] is False
    assert _graph_state(mediator) == before
    assert graph.assertion_state(envelope.stable_id)['status'] == 'active'


@pytest.mark.parametrize('targets', [None, 'fact_original', ['fact_original', 'fact_original'], [3], ['bad target']])
def test_missing_or_malformed_host_authority_is_not_inferred(targets):
    request_id = uuid.uuid4().hex
    with pytest.raises(llm.IntakeContractError) as caught:
        llm.parse_intake_request(_body(request_id), request_id=request_id,
            operation='extract_facts', source_text=SOURCE, allowed_target_refs=targets)
    assert caught.value.code == 'identity'


def test_empty_host_authority_only_allows_successful_empty_output():
    request_id = uuid.uuid4().hex
    result = llm.parse_intake_request(_body(request_id), request_id=request_id,
        operation='extract_facts', source_text=SOURCE, allowed_target_refs=())
    assert result['facts'] == result['questions'] == []
    with pytest.raises(llm.IntakeContractError):
        llm.parse_intake_request(_body(request_id, facts=[_fact()]), request_id=request_id,
            operation='extract_facts', source_text=SOURCE, allowed_target_refs=())


@pytest.mark.parametrize('text', ['"\\ud800"', '[' * 1200 + ']' * 1200])
def test_invalid_encoding_or_excessive_depth_remains_typed(text):
    with pytest.raises(llm.IntakeContractError):
        llm.parse_intake_request(text, request_id=uuid.uuid4().hex,
            operation='extract_facts', source_text=SOURCE, allowed_target_refs=('fact_original',))


@pytest.fixture
def bound(canonical):
    mediator, graph, envelope, _ = canonical
    policy = llm.privacy_policy_for_mode(USER, CASE, 'grok')
    mediator.workflow_actions.bind_interview_privacy(policy, user_id=USER, case_id=CASE)
    mediator.begin_intake_router_action(owner_id=USER, case_id=CASE,
        session_id=uuid.uuid4().hex, revision=0)
    return mediator, graph, envelope, mediator.backends[0]


def _respond(backend, fn):
    def authored(prompt, **kwargs):
        backend.calls.append(copy.deepcopy(kwargs))
        return fn(kwargs)
    # An instance __call__ override is ignored by Python; replace the backend
    # in its owning mediator explicitly in each fixture below instead.
    return authored


def _install_response(mediator, backend, fn):
    mediator.backends[0] = _respond(backend, fn)


def test_host_exchange_uses_fresh_call_ids_and_opaque_safe_receipts(bound):
    mediator, graph, envelope, backend = bound
    _install_response(mediator, backend,
        lambda kw: _body(kw['intake_request_id'], facts=[_fact('opaque-slot')]))
    before = _graph_state(mediator)
    targets = {'opaque-slot': {'field': 'party'}}
    one = mediator.request_intake_candidates('extract_facts', source_text=SOURCE, targets=targets)
    two = mediator.request_intake_candidates('extract_facts', source_text=SOURCE, targets=targets)
    assert one is not None and two is not None and one['request_id'] != two['request_id']
    assert len(backend.calls) == 2
    assert _graph_state(mediator) == before  # Validation is not graph admission.
    snapshot = mediator.intake_router_snapshot()
    assert snapshot['intake_complete'] is False
    assert len(snapshot['receipts']) == 2 and all(r['status'] == 'available' for r in snapshot['receipts'])
    assert {r['request_id'] for r in snapshot['receipts']} == {one['request_id'], two['request_id']}
    public = json.dumps(snapshot)
    assert SOURCE not in public and USER not in public and CASE not in public
    assert source_byte_hash(SOURCE) not in public
    assert all(len(r['binding_id']) == 32 for r in snapshot['receipts'])


@pytest.mark.parametrize('mutation', ['revision', 'action', 'owner', 'case', 'consent', 'stale_reply', 'foreign_ref', 'field_swap'])
def test_changed_host_authority_or_stale_reply_has_no_canonical_effect(bound, mutation):
    mediator, graph, envelope, backend = bound
    before = _graph_state(mediator)
    targets = {'opaque-slot': {'field': 'party'}}
    def reply(kw):
        request = kw['intake_request_id']
        fact = _fact('opaque-slot')
        if mutation == 'revision': mediator.workflow_actions._interview_meta = {'session_revision': 1}
        elif mutation == 'action':
            mediator.begin_intake_router_action(owner_id=USER, case_id=CASE,
                session_id=uuid.uuid4().hex, revision=0)
        elif mutation == 'owner': mediator._interview_privacy_context['user_id'] = 'synthetic-bob'
        elif mutation == 'case': mediator._interview_privacy_context['case_id'] = 'synthetic-case-b'
        elif mutation == 'consent':
            mediator._interview_privacy_context = llm.build_complaint_privacy_context(
                llm.privacy_policy_for_mode(USER, CASE, 'local'), user_id=USER,
                case_id=CASE, data_class='raw_intake')
        elif mutation == 'stale_reply': request = uuid.uuid4().hex
        elif mutation == 'foreign_ref': fact['target_ref'] = 'authority_source:foreign-law'
        elif mutation == 'field_swap': fact['field'] = 'date'
        return _body(request, facts=[fact])
    _install_response(mediator, backend, reply)
    if mutation in {'revision', 'action'}:
        with pytest.raises(ValueError, match='stale_intake_request'):
            mediator.request_intake_candidates('extract_facts', source_text=SOURCE, targets=targets)
    else:
        assert mediator.request_intake_candidates('extract_facts', source_text=SOURCE, targets=targets) is None
        assert mediator.intake_router_snapshot()['errors']
        assert mediator.intake_router_snapshot()['receipts'][-1]['status'] != 'available'
    assert len(backend.calls) == 1 and _graph_state(mediator) == before
    assert graph.entities['fact_original'].provenance['user_assertion'] == envelope.as_dict()


def test_callers_cannot_mutate_host_target_authority_while_response_is_pending(bound):
    mediator, graph, envelope, backend = bound
    targets = {'opaque-slot': {'field': 'party'}}
    def reply(kw):
        targets['opaque-slot']['field'] = 'date'
        targets['foreign-slot'] = {'field': 'party'}
        return _body(kw['intake_request_id'], facts=[_fact('opaque-slot')])
    _install_response(mediator, backend, reply)
    result = mediator.request_intake_candidates('extract_facts', source_text=SOURCE, targets=targets)
    assert result is not None and result['facts'][0]['field'] == 'party'
    assert backend.calls[0]['intake_target_refs'] == ('opaque-slot',)


@pytest.mark.parametrize('kind', ['foreign_target', 'swapped_question_id', 'whitespace', 'duplicate'])
def test_question_proposals_cannot_change_host_question_identity(bound, kind):
    mediator, graph, envelope, backend = bound
    original = [{'question': 'When did the payment happen?', 'type': 'date',
        'question_id': 'canonical-inquiry', 'target_id': 'fact_original',
        'priority': 4, 'context': {'unknown_recorded': True}}]
    def reply(kw):
        question = {'question_id': 'q0', 'prompt': 'What date was the payment?', 'target_ref': 'question:0'}
        if kind == 'foreign_target': question['target_ref'] = 'question:other'
        elif kind == 'swapped_question_id': question['question_id'] = 'different'
        elif kind == 'whitespace': question['prompt'] = '   '
        return _body(kw['intake_request_id'], operation='propose_questions',
            questions=[question, copy.deepcopy(question)] if kind == 'duplicate' else [question])
    _install_response(mediator, backend, reply)
    before = _graph_state(mediator)
    assert mediator._intake_question_proposals(original, source_text=SOURCE) == original
    assert _graph_state(mediator) == before and original[0]['context']['unknown_recorded'] is True
    assert mediator.intake_router_snapshot()['errors']['propose_questions'] == 'malformed_output'


def test_question_wording_preserves_canonical_unknown_and_target_metadata(bound):
    mediator, graph, envelope, backend = bound
    original = [{'question': 'When did the payment happen?', 'type': 'date',
        'question_id': 'canonical-inquiry', 'target_id': 'fact_original', 'priority': 4,
        'context': {'unknown_recorded': True}}]
    _install_response(mediator, backend, lambda kw: _body(kw['intake_request_id'], operation='propose_questions',
        questions=[{'question_id': 'q0', 'prompt': 'What date was the payment?', 'target_ref': 'question:0'}]))
    updated = mediator._intake_question_proposals(original, source_text=SOURCE)
    assert updated[0]['question'] == original[0]['question']
    assert updated[0]['model_proposal']['wording'] == 'What date was the payment?'
    assert {k:v for k,v in updated[0].items() if k not in {'question','model_proposal'}} == {
        k:v for k,v in original[0].items() if k != 'question'}
    assert original[0]['question'] == 'When did the payment happen?'
    assert updated[0]['model_proposal']['legal_sufficiency'] is False


def test_real_graph_admission_retains_exact_model_span_without_user_or_legal_assertion(bound, monkeypatch):
    mediator, graph, envelope, backend = bound
    second = SOURCE.encode('utf-8').rfind('José'.encode('utf-8'))
    _install_response(mediator, backend,
        lambda kw: _body(kw['intake_request_id'], facts=[_fact('candidate:0', start=second)]))
    builder = KnowledgeGraphBuilder(mediator)
    # Keep the actual typed role + actual graph admission, while isolating this
    # model record from unrelated heuristic extraction/relationship generation.
    monkeypatch.setattr(builder, '_extract_entities', lambda text: builder._llm_extract_entities(text))
    monkeypatch.setattr(builder, '_extract_relationships', lambda text, kg: [])
    result = builder.build_from_text(SOURCE, source_context=_user_context(SOURCE))
    assert len(result.entities) == 1
    entity = next(iter(result.entities.values()))
    proof = user_assertion_from_mapping(entity.provenance['user_assertion'])
    assert proof.source_span_start == second and proof.source_span_end == second + len('José'.encode())
    assert proof.source_span_text == 'José'
    assert proof.record_type == 'model_suggestion' and not proof.is_asserted_user_fact
    assert entity.name == 'José' and entity.type == 'person'
    assert entity.provenance['extractor']['intake_router']['request_id'] == backend.calls[0]['intake_request_id']
    assert all(not user_assertion_from_mapping(e.provenance['user_assertion']).is_asserted_user_fact
               for e in result.entities.values())
    assert mediator.query_intake_candidates(collection_key='relationships', source_text=SOURCE) == []
    assert len(backend.calls) == 1  # Unsupported relationships never open a call.
