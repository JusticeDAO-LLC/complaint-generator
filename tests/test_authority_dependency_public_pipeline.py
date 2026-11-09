"""Current local source admission through genuine intake and formalization paths."""
from copy import deepcopy

import pytest

from complaint_phases.dependency_graph import DependencyGraphBuilder, NodeType
from complaint_phases.phase_manager import ComplaintPhase
from integrations.ipfs_datasets.logic import sha256_utf8
from mediator.mediator import Mediator

from tests.test_authority_dependency_pipeline import (
    _MockBackend, _source_record, _verified_requirement, _local_sources,
    _sourced_nodes, _gap_nodes, _CONTEXT,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _workflow(tmp_path):
    mediator = Mediator([_MockBackend()], evidence_db_path=str(tmp_path / 'evidence.duckdb'),
                        legal_authority_db_path=str(tmp_path / 'authority.duckdb'),
                        claim_support_db_path=str(tmp_path / 'support.duckdb'))
    mediator.state.username = 'source-fixture-owner'
    return mediator


def _start(monkeypatch, tmp_path, records, *, context=_CONTEXT):
    mediator = _workflow(tmp_path)
    _local_sources(monkeypatch, mediator, records)
    mediator.start_three_phase_process('My employer discriminated against me.' + context)
    return mediator, mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')


def test_local_stored_authority_roundtrip_drives_real_source_promotion(tmp_path):
    mediator = _workflow(tmp_path)
    source = _source_record('ors:fixture', 'notice')
    stored = mediator.legal_authority_storage.add_authority({
        'type': 'statute', 'source': 'owned-local-corpus', 'title': 'Notice rule',
        'citation': source['citation'], 'content': source['source_text'], 'jurisdiction': 'OR',
        'metadata': {key: value for key, value in source.items()
                     if key not in {'id', 'content', 'claim_type'}},
    }, 'source-fixture-owner', claim_type='employment_discrimination')
    assert stored > 0
    records = mediator.get_legal_authorities(claim_type='employment_discrimination')
    assert len(records) == 1 and records[0]['content'] == source['source_text']
    mediator.start_three_phase_process('My employer discriminated against me.' + _CONTEXT)
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
    nodes = _sourced_nodes(graph)
    assert nodes and not _gap_nodes(graph)
    proof = nodes[0].attributes
    span = proof['source_span']
    text = proof['source_record']['source_text']
    assert text.encode('utf-8')[span['start']:span['end']].decode('utf-8') == proof['rule_text']
    assert proof['source_hash'] == sha256_utf8(text)
    assert proof['authority_version'] == '2024-edition'
    assert proof['temporal_applicability']['applicable'] is True
    assert proof['provenance'] and proof['about_complainant'] is False
    assert proof['source_record']['metadata']['provenance'] == source['provenance']
    # Change the real owned storage fixture, then exercise its public read and
    # refresh paths. Empty materialized lists cannot erase adverse corpus data.
    import json
    from mediator.legal_authority_hooks import duckdb
    # The actual stored body owns the source span/hash even if old metadata
    # still supplies a self-consistent earlier body and hash.
    nodes[0].satisfied = True
    changed_body = 'An employer shall provide a hearing to an employee.'
    with duckdb.connect(mediator.legal_authority_storage.db_path) as conn:
        conn.execute('UPDATE legal_authorities SET content = ? WHERE id = ?', [changed_body, stored])
    changed = mediator.get_legal_authorities(claim_type='employment_discrimination')
    assert changed[0]['content'] == changed_body and 'source_text' not in changed[0]
    assert changed[0]['metadata']['source_text'] == source['source_text']
    report = mediator.refresh_verified_legal_dependencies({'source_changed': True})
    assert nodes[0].id in report['affected_node_ids']
    assert nodes[0].satisfied is False and nodes[0].attributes['source_available'] is False
    assert _gap_nodes(graph)
    with duckdb.connect(mediator.legal_authority_storage.db_path) as conn:
        conn.execute('UPDATE legal_authorities SET content = ? WHERE id = ?', [source['source_text'], stored])
    mediator.refresh_verified_legal_dependencies({'source_changed': True})
    nodes = [node for node in _sourced_nodes(graph) if node.attributes.get('source_available')]
    assert nodes and not _gap_nodes(graph)
    assert nodes[0].attributes['source_hash'] == sha256_utf8(source['source_text'])
    assert nodes[0].attributes['source_record']['source_text'] == source['source_text']
    changed_metadata = deepcopy(records[0]['metadata'])
    changed_metadata['authority_treatment_edges'] = [
        {'relation_type': 'adverse', 'target_authority_id': source['authority_id']}
    ]
    with duckdb.connect(mediator.legal_authority_storage.db_path) as conn:
        conn.execute('UPDATE legal_authorities SET metadata = ? WHERE id = ?',
                     [json.dumps(changed_metadata), stored])
    reread = mediator.get_legal_authorities(claim_type='employment_discrimination')
    assert reread[0]['authority_treatment_edges'] == []
    assert reread[0]['metadata']['authority_treatment_edges'] == changed_metadata['authority_treatment_edges']
    nodes[0].satisfied = True
    report = mediator.refresh_verified_legal_dependencies({'source_changed': True})
    assert nodes[0].id in report['affected_node_ids']
    assert nodes[0].satisfied is False and nodes[0].attributes['source_available'] is False
    assert _gap_nodes(graph)
    assert mediator.advance_to_formalization_phase()['code'] == 'legal_context_source_gap'


@pytest.mark.parametrize('forged', [
    {'promoted': True, 'source_bound': True, 'verification_status': 'verified', 'authority_id': 'x',
     'applicable': True, 'support_eligible': True},
    {'promoted': True, 'source_record': {'source_text': 'A model says this is required.'},
     'applicable': True, 'support_eligible': True},
])
def test_forged_verification_labels_never_admit_a_dependency(forged):
    builder = DependencyGraphBuilder()
    graph = builder.build_from_claims([{'type': 'employment_discrimination', 'name': 'Claim'}],
                                     {'employment_discrimination': [forged]},
                                     require_verified_legal_sources=True)
    assert not _sourced_nodes(graph)
    assert _gap_nodes(graph)
    assert graph.metadata['heuristic_law_derived_invoked'] is False


@pytest.mark.parametrize('context', ['', ' Under Oregon law.', ' Applicable law date: 2024-06-01.'])
def test_missing_current_legal_context_blocks_real_formalization(monkeypatch, tmp_path, context):
    mediator, graph = _start(monkeypatch, tmp_path, [_source_record('rule-a', 'notice')], context=context)
    # Caller pre-populated flags and a law's date cannot fill in the user's context.
    mediator.state.verified_legal_requirements = {'employment_discrimination': [_verified_requirement('fake', 'notice')]}
    intake = mediator.phase_manager.phase_data[ComplaintPhase.INTAKE]
    intake.update(remaining_gaps=0, denoising_converged=True, intake_gap_types=[])
    assert _gap_nodes(graph)
    assert 'legal_context_source_gap' in mediator.phase_manager.get_intake_readiness()['blockers']
    phase = mediator.phase_manager.get_current_phase()
    result = mediator.advance_to_formalization_phase()
    assert result['code'] == 'legal_context_source_gap'
    assert result['matching_complete'] is False and result['applicability'] == 'unknown'
    assert mediator.phase_manager.get_current_phase() == phase
    assert not mediator.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'matching_complete')
    mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
    mediator.phase_manager.phase_data[ComplaintPhase.EVIDENCE].update(
        evidence_count=1, knowledge_graph_enhanced=True, evidence_gap_ratio=0)
    assert mediator.phase_manager.advance_to_phase(ComplaintPhase.FORMALIZATION) is False
    from complaint_phases.legal_graph import LegalGraph
    mediator.phase_manager.phase_data[ComplaintPhase.FORMALIZATION].update(
        legal_graph=LegalGraph(), matching_complete=True, formal_complaint={'text': 'not proof'})
    assert mediator.phase_manager.is_phase_complete(ComplaintPhase.FORMALIZATION) is False


@pytest.mark.parametrize('change', ['remove', 'backend_error', 'hash_change', 'expired', 'adverse'])
def test_current_source_loss_retires_support_and_reopens_gap(monkeypatch, tmp_path, change):
    records = [_source_record('rule-a', 'notice')]
    mediator, graph = _start(monkeypatch, tmp_path, records)
    node = next(item for item in _sourced_nodes(graph) if item.attributes.get('source_available'))
    node.satisfied = True
    node.attributes['satisfaction_state'] = 'satisfied'
    if change == 'remove':
        records.clear()
    elif change == 'backend_error':
        def unavailable(*args):
            raise RuntimeError('PRIVATE_BACKEND_ERROR_DO_NOT_REPORT')
        monkeypatch.setattr(mediator.legal_authority_storage, 'get_authorities_by_claim', unavailable)
    elif change == 'hash_change':
        records[0]['source_hash'] = sha256_utf8('different source')
    elif change == 'expired':
        records[0]['expiration_date'] = '2024-03-01'
    else:
        records[0]['authority_treatment_edges'] = [{'relation_type': 'adverse', 'target_authority_id': 'rule-a'}]
    report = mediator.refresh_verified_legal_dependencies({'source_changed': True})
    assert node.id in report['affected_node_ids']
    assert node.satisfied is False and node.attributes['source_available'] is False
    assert _gap_nodes(graph)
    assert 'PRIVATE_BACKEND_ERROR_DO_NOT_REPORT' not in repr(report)
    result = mediator.advance_to_formalization_phase()
    assert result['code'] == 'legal_context_source_gap'
    assert not mediator.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'matching_complete')


def test_same_source_refresh_preserves_satisfaction_but_new_rule_replaces_it(monkeypatch, tmp_path):
    records = [_source_record('rule-a', 'notice')]
    mediator, graph = _start(monkeypatch, tmp_path, records)
    node = next(item for item in _sourced_nodes(graph) if item.attributes.get('source_available'))
    node.satisfied = True
    node.attributes['satisfaction_state'] = 'satisfied'
    edge_ids = {key for key, edge in graph.dependencies.items() if edge.source_id == node.id}
    report = mediator.refresh_verified_legal_dependencies({'source_changed': True})
    assert node.id in report['preserved_node_ids'] and node.satisfied is True
    assert edge_ids.issubset(graph.dependencies)
    records[0] = _source_record('rule-a', 'written notice')
    report = mediator.refresh_verified_legal_dependencies({'rule_ids': [node.attributes['rule_id']]})
    active = [item for item in _sourced_nodes(graph) if item.attributes.get('source_available')]
    assert active and active[0].id != node.id and active[0].satisfied is False
    assert node.attributes['source_available'] is False and node.satisfied is False
    assert not _gap_nodes(graph)
    assert not any(edge.source_id == node.id for edge in graph.dependencies.values())
    assert node.attributes['retired_dependency_edges']


def test_new_date_rechecks_current_version_without_guessing_query_date(monkeypatch, tmp_path):
    records = [_source_record('rule-a', 'notice')]
    records[0]['expiration_date'] = '2024-12-31'
    mediator, graph = _start(monkeypatch, tmp_path, records)
    node = next(item for item in _sourced_nodes(graph) if item.attributes.get('source_available'))
    node.satisfied = True
    case = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')
    mediator.apply_explicit_legal_context(case, applicable_law_date='2025-02-01')
    assert node.satisfied is False and node.attributes['source_available'] is False
    assert _gap_nodes(graph)
    assert mediator.advance_to_formalization_phase()['code'] == 'legal_context_source_gap'


def test_fact03_revision_uses_actual_stable_identity_and_preserves_other_support(monkeypatch, tmp_path):
    records = [_source_record('rule-a', 'notice')]
    mediator, graph = _start(monkeypatch, tmp_path, records)
    text = 'My supervisor sent the notice.'
    context = {'source_text': text, 'source_kind': 'user_statement', 'source_id': 'message-1',
               'message_id': 'message-1', 'assertion_status': 'asserted',
               'extractor_version': 'user_assertion@1', 'source_hash': sha256_utf8(text),
               'subject_key': 'notice'}
    first = mediator.process_denoising_answer({'type': 'fact', 'question': 'What happened?'}, text,
                                              factual_action='assert', source_context=context,
                                              answer_event_id='fact-assert-1')
    kg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
    prior = next(entity for entity in kg.entities.values()
                 if entity.attributes.get('factual_action') == 'assert')
    stable = prior.provenance['user_assertion']['stable_id']
    # Attach satisfaction through the canonical support-id fields FACT03 reads.
    legal = next(item for item in _sourced_nodes(graph) if item.attributes.get('source_available'))
    legal.attributes['source_fact_ids'] = [stable]
    legal.attributes['dependency_scope']['fact_ids'] = [stable]
    legal.satisfied = True
    legal.attributes['satisfaction_state'] = 'satisfied'
    other = next(node for node in graph.nodes.values() if node.node_type == NodeType.FACT
                 and node.attributes.get('dependency_class') == 'factual_clarification')
    other.satisfied = True
    corrected = 'My supervisor did not send the notice.'
    correction_context = dict(context, source_text=corrected, source_id='message-2', message_id='message-2',
                              source_hash=sha256_utf8(corrected))
    mediator.process_denoising_answer({'type': 'fact', 'question': 'Correct the prior statement.'}, corrected,
                                     factual_action='correct', source_context=correction_context,
                                     supersedes_stable_id=stable, answer_event_id='fact-correct-2')
    report = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'verified_dependency_refresh')
    assert legal.satisfied is False and legal.attributes['stale_satisfaction'] is True
    assert legal.id in report['affected_node_ids']
    assert other.satisfied is True
    assert kg.factual_ledger()['revisions']


def test_source_record_bound_is_checked_before_promotion(monkeypatch, tmp_path):
    source = _source_record('rule-a', 'notice')
    source['metadata'] = {'oversized': 'x' * 262145}
    mediator, graph = _start(monkeypatch, tmp_path, [source])
    assert not _sourced_nodes(graph) and _gap_nodes(graph)
    assert mediator.advance_to_formalization_phase()['code'] == 'legal_context_source_gap'


def test_actual_formalization_uses_current_promoted_graph_with_empty_legacy_statutes(monkeypatch, tmp_path):
    mediator, graph = _start(monkeypatch, tmp_path, [_source_record('rule-a', 'notice')])
    mediator.state.applicable_statutes = []
    mediator.phase_manager.current_phase = ComplaintPhase.EVIDENCE
    evidence = mediator.phase_manager.phase_data[ComplaintPhase.EVIDENCE]
    evidence.update(evidence_count=1, knowledge_graph_enhanced=True, evidence_gap_ratio=0)
    result = mediator.advance_to_formalization_phase()
    assert result['phase'] == ComplaintPhase.FORMALIZATION.value
    legal = mediator.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph')
    assert legal is mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'verified_legal_graph')
    assert legal.get_elements_by_type('legal_requirement')
    matches = result['matching_results']['claims']
    assert matches and all(claim['legal_requirements'] > 0 for claim in matches)
    assert all(claim.get('confidence') != 1.0 or claim.get('satisfied_requirements') > 0 for claim in matches)


def test_structured_case_readiness_reopens_and_clears_only_current_source_gap(monkeypatch, tmp_path):
    records = []
    mediator, graph = _start(monkeypatch, tmp_path, records)
    case = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')
    assert case['intake_sections']
    missing = mediator.phase_manager.get_intake_readiness()
    assert missing['criteria']['legal_sources_available'] is False
    assert 'legal_context_source_gap' in missing['blockers']
    records.append(_source_record('rule-restored', 'notice'))
    mediator.refresh_verified_legal_dependencies({'source_changed': True})
    restored = mediator.phase_manager.get_intake_readiness()
    assert restored['criteria']['legal_sources_available'] is True
    assert 'legal_context_source_gap' not in restored['blockers']
    assert not _gap_nodes(graph)
    assert _sourced_nodes(graph)


def test_same_authority_versions_keep_their_own_hash_span_and_query_proof(monkeypatch, tmp_path):
    first = _source_record('shared-authority', 'written notice')
    second = _source_record('shared-authority', 'hearing notice')
    second['authority_version'] = '2024-revision'
    records = [first, second]
    mediator, graph = _start(monkeypatch, tmp_path, records)
    active = [node for node in _sourced_nodes(graph) if node.attributes.get('source_available')]
    assert {node.attributes['authority_version'] for node in active} == {'2024-edition', '2024-revision'}
    assert len(active) == 2
    for node in active:
        proof = node.attributes
        source = proof['source_record']
        assert proof['authority_version'] == source['authority_version']
        assert proof['source_hash'] == sha256_utf8(source['source_text'])
        assert source['source_text'] == proof['description']
        legal = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'verified_legal_graph')
        element = legal.elements[proof['rule_id']]
        assert element.attributes['authority_version'] == proof['authority_version']
        assert element.attributes['source_hash'] == proof['source_hash']


def test_same_type_claims_keep_separate_obligation_satisfaction_and_successor_edges():
    builder = DependencyGraphBuilder()
    shared = _verified_requirement('shared-rule', 'notice')
    graph = builder.build_from_claims([
        {'name': 'First employer claim', 'type': 'employment_discrimination', 'description': 'First distinct action'},
        {'name': 'Second employer claim', 'type': 'employment_discrimination', 'description': 'Second distinct action'},
    ], {'employment_discrimination': [shared]}, require_verified_legal_sources=True)
    claims = graph.get_nodes_by_type(NodeType.CLAIM)
    assert len(claims) == 2
    active = _sourced_nodes(graph)
    assert len(active) == 2 and active[0].id != active[1].id
    obligations = {edge.target_id: graph.nodes[edge.source_id] for edge in graph.dependencies.values()
                   if edge.source_id in {node.id for node in active}}
    assert set(obligations) == {claim.id for claim in claims}
    obligations[claims[0].id].satisfied = True
    assert obligations[claims[1].id].satisfied is False
    assert not any(edge.source_id == obligations[claims[0].id].id and edge.target_id == claims[1].id
                   for edge in graph.dependencies.values())
    unrelated = next(node for node in graph.nodes.values() if node.node_type == NodeType.FACT)
    unrelated.satisfied = True
    unrelated_edges = {key for key, edge in graph.dependencies.items() if edge.source_id == unrelated.id}
    revised = _verified_requirement('shared-rule', 'written notice')
    report = builder.reconcile_verified_requirements(graph, {'employment_discrimination': [revised]})
    successors = [node for node in _sourced_nodes(graph) if node.attributes.get('source_available')]
    assert len(successors) == 2 and successors[0].id != successors[1].id
    assert all(not node.satisfied for node in successors)
    assert {edge.target_id for edge in graph.dependencies.values()
            if edge.source_id in {node.id for node in successors}} == {claim.id for claim in claims}
    assert all(node.attributes['source_available'] is False for node in active)
    assert all(not node.satisfied for node in active)
    assert not any(edge.source_id in {node.id for node in active} for edge in graph.dependencies.values())
    assert not _gap_nodes(graph)
    assert unrelated.satisfied is True and unrelated.id in report['preserved_node_ids']
    assert unrelated_edges.issubset(graph.dependencies)

    final_rule = _verified_requirement('shared-rule', 'timely written notice')
    builder.refresh_affected_dependencies(graph, {
        'rule_ids': ['shared-rule'],
        'updated_requirements': {'employment_discrimination': [final_rule]},
    })
    current = [node for node in _sourced_nodes(graph) if node.attributes.get('source_available')]
    assert len(current) == 2
    assert {edge.target_id for edge in graph.dependencies.values()
            if edge.source_id in {node.id for node in current}} == {claim.id for claim in claims}
    assert all(node.description == final_rule['description'] for node in current)
    assert unrelated.satisfied is True


def test_source_obligation_question_targets_preserve_same_type_claim_identity(monkeypatch, tmp_path):
    from complaint_phases.knowledge_graph import KnowledgeGraph, Entity

    mediator = _workflow(tmp_path)
    _local_sources(monkeypatch, mediator, [_source_record('shared-source', 'notice')])
    claims = [
        {'type': 'employment_discrimination', 'name': 'First employer claim', 'description': 'First action'},
        {'type': 'employment_discrimination', 'name': 'Second employer claim', 'description': 'Second action'},
    ]
    case = {'source_complaint_text': _CONTEXT}
    requirements = mediator._collect_verified_legal_requirements(claims, case)
    graph = mediator.dg_builder.build_from_claims(claims, requirements, require_verified_legal_sources=True)
    kg = KnowledgeGraph()
    for index, claim in enumerate(claims):
        kg.add_entity(Entity(f'claim-{index}', 'claim', claim['name'], attributes={'claim_type': claim['type']}))
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', graph)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', case)
    pressure = mediator._build_intake_matching_pressure_map(kg, graph, case)
    current_claims = graph.get_nodes_by_type(NodeType.CLAIM)
    obligations = {
        claim.id: {edge.source_id for edge in graph.get_dependencies_for_node(claim.id, direction='incoming')
                   if graph.nodes[edge.source_id].attributes.get('dependency_class') == 'legally_sourced_requirement'}
        for claim in current_claims
    }
    assert all(len(ids) == 1 for ids in obligations.values())
    assert len(set.union(*obligations.values())) == 2
    group = pressure['employment_discrimination']
    assert set(group['claim_obligations']) == set(obligations)
    for claim_id, ids in obligations.items():
        assert set(group['claim_obligations'][claim_id]['missing_requirement_element_ids']) == ids
    candidates = mediator.denoiser.collect_question_candidates(kg, graph, max_questions=100, intake_case_file=case)
    questions = [item for item in candidates if item.get('context', {}).get('requirement_id')
                 in set.union(*obligations.values())]
    assert {item['context']['claim_id'] for item in questions} == set(obligations)
    raw_summary = mediator._summarize_intake_legal_targeting(pressure, questions)
    assert {item['target_element_id'] for item in raw_summary['claims']['employment_discrimination']['mapped_candidates']} == set.union(*obligations.values())
    assert all(item['direct_legal_target_match'] for item in raw_summary['claims']['employment_discrimination']['mapped_candidates'])
    for question in questions:
        claim_id = question['context']['claim_id']
        annotated = mediator._annotate_intake_question_candidate(question, {}, pressure)
        assert annotated['target_claim_type'] == 'employment_discrimination'
        assert annotated['selector_signals']['direct_legal_target_match'] is True
        assert set(annotated['selector_signals']['matcher_missing_requirement_element_ids']) == obligations[claim_id]
    first_question = questions[0]
    missing = deepcopy(first_question)
    missing['context'].pop('claim_id')
    missing['target_claim_type'] = 'employment_discrimination'
    missing['ranking_explanation']['target_claim_type'] = 'employment_discrimination'
    denied = mediator._annotate_intake_question_candidate(missing, {}, pressure)
    assert denied['target_claim_type'] == '' and not denied['selector_signals']['direct_legal_target_match']
    assert not mediator._summarize_intake_legal_targeting(pressure, [missing])['claims']['employment_discrimination']['mapped_candidates']
    crossed = deepcopy(first_question)
    crossed['context']['claim_id'] = next(key for key in obligations if key != first_question['context']['claim_id'])
    denied = mediator._annotate_intake_question_candidate(crossed, {}, pressure)
    assert not denied['selector_signals']['direct_legal_target_match']
    assert not mediator._summarize_intake_legal_targeting(pressure, [crossed])['claims']['employment_discrimination']['mapped_candidates']
    foreign = deepcopy(first_question)
    foreign['context']['claim_id'] = 'unknown-claim'
    denied = mediator._annotate_intake_question_candidate(foreign, {}, pressure)
    assert denied['target_claim_type'] == '' and not denied['selector_signals']['direct_legal_target_match']
    assert not mediator._summarize_intake_legal_targeting(pressure, [foreign])['claims']['employment_discrimination']['mapped_candidates']
    retired = graph.nodes[first_question['context']['requirement_id']]
    retired.attributes['source_available'] = False
    refreshed = mediator._build_intake_matching_pressure_map(kg, graph, case)
    denied = mediator._annotate_intake_question_candidate(first_question, {}, refreshed)
    assert not denied['selector_signals']['direct_legal_target_match']
    assert retired.id not in refreshed['employment_discrimination']['missing_requirement_element_ids']
    assert not mediator._summarize_intake_legal_targeting(refreshed, [first_question])['claims']['employment_discrimination']['mapped_candidates']


@pytest.mark.parametrize('label', ['Applicable law date', 'Law in effect on', 'Law applicable on'])
def test_explicit_law_query_date_cannot_close_a_factual_timeline_gap(label):
    builder = DependencyGraphBuilder()
    legal_context = f' Under Oregon law. {label}: 2024-06-01.'
    undated = 'My employer discriminated against me.' + legal_context
    graph = builder.build_from_claims([
        {'type': 'employment_discrimination', 'name': 'Claim', 'description': undated},
    ], {}, require_verified_legal_sources=True)
    timeline = [node for node in graph.get_nodes_by_type(NodeType.FACT) if node.name == 'Timeline of events']
    assert timeline and all(node.satisfied is False for node in timeline)
    assert graph.get_nodes_by_type(NodeType.CLAIM)[0].description == undated
    assert _gap_nodes(graph)
    dated = 'My employer fired me on January 20, 2026.' + legal_context
    event_graph = builder.build_from_claims([
        {'type': 'employment_discrimination', 'name': 'Claim', 'description': dated},
    ], {}, require_verified_legal_sources=True)
    assert not [node for node in event_graph.get_nodes_by_type(NodeType.FACT) if node.name == 'Timeline of events']
    assert event_graph.get_nodes_by_type(NodeType.CLAIM)[0].description == dated
    assert _gap_nodes(event_graph)
    same_sentence = f'Under Oregon law. {label}: 2024-06-01, my employer fired me on January 20, 2026.'
    after_graph = builder.build_from_claims([
        {'type': 'employment_discrimination', 'name': 'Claim', 'description': same_sentence},
    ], {}, require_verified_legal_sources=True)
    assert not [node for node in after_graph.get_nodes_by_type(NodeType.FACT) if node.name == 'Timeline of events']
    assert after_graph.get_nodes_by_type(NodeType.CLAIM)[0].description == same_sentence
    assert _gap_nodes(after_graph)
