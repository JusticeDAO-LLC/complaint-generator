import pytest

from integrations.ipfs_datasets.logic import check_contradictions, prove_claim_elements, run_hybrid_reasoning


pytestmark = pytest.mark.no_auto_network


def test_logic_stubbed_adapters_summarize_temporal_predicate_shapes():
    predicates = [
        {
            'predicate_type': 'claim_element',
            'claim_type': 'retaliation',
            'predicate_id': 'retaliation:1',
            'claim_element_id': 'retaliation:1',
            'claim_element_text': 'Protected activity',
        },
        {
            'predicate_type': 'support_trace',
            'claim_type': 'retaliation',
            'predicate_id': 'fact:support',
            'support_ref': 'QmEvidenceTemporal',
            'support_kind': 'evidence',
            'text': 'HR complaint email confirms the report.',
            'claim_element_id': 'retaliation:1',
        },
        {
            'predicate_type': 'temporal_fact',
            'claim_type': 'retaliation',
            'predicate_id': 'temporal_fact:fact_1',
            'fact_id': 'fact_1',
            'text': 'Employee complained to HR.',
            'start_date': '2025-03-01',
            'end_date': '2025-03-01',
            'granularity': 'day',
            'is_approximate': False,
            'is_range': False,
            'relative_markers': [],
        },
        {
            'predicate_type': 'temporal_proof_lead',
            'claim_type': 'retaliation',
            'predicate_id': 'temporal_proof_lead:lead_1',
            'lead_id': 'lead_1',
            'description': 'HR complaint email',
            'related_fact_ids': ['fact_1'],
            'start_date': '2025-03-01',
            'end_date': '2025-03-31',
            'granularity': 'month',
            'is_approximate': False,
            'is_range': True,
        },
        {
            'predicate_type': 'temporal_relation',
            'claim_type': 'retaliation',
            'predicate_id': 'timeline_relation_001',
            'relation_type': 'before',
            'source_fact_id': 'fact_1',
            'target_fact_id': 'fact_2',
        },
        {
            'predicate_type': 'temporal_issue',
            'claim_type': 'retaliation',
            'predicate_id': 'temporal_reverse_before_001',
            'summary': 'Complaint and termination are ordered inconsistently.',
            'left_node_name': 'Employee complained to HR.',
            'right_node_name': 'Employee was terminated.',
            'severity': 'blocking',
        },
        {
            'predicate_type': 'contradiction_candidate',
            'claim_type': 'retaliation',
            'predicate_id': 'contradiction:retaliation:1:0',
        },
    ]

    proof_result = prove_claim_elements(predicates)
    contradiction_result = check_contradictions(predicates)

    for result in (proof_result, contradiction_result):
        assert result['predicate_count'] == 7
        assert result['predicate_type_counts'] == {
            'claim_element': 1,
            'contradiction_candidate': 1,
            'support_trace': 1,
            'temporal_fact': 1,
            'temporal_issue': 1,
            'temporal_proof_lead': 1,
            'temporal_relation': 1,
        }
        assert result['claim_type_counts'] == {'retaliation': 7}
        assert result['temporal_predicate_count'] == 4
        assert result['temporal_relation_count'] == 1
        assert result['contradiction_signal_count'] == 2
        assert result['metadata']['predicate_type_counts'] == result['predicate_type_counts']
        assert result['metadata']['details']['predicate_type_counts'] == result['predicate_type_counts']
        assert result['metadata']['details']['temporal_predicate_count'] == 4
        assert result['metadata']['details']['contradiction_signal_count'] == 2
        reasoning_payload = result['temporal_reasoning_payload']
        assert reasoning_payload['formalism'] == 'tdfol_dcec_bridge_v1'
        assert reasoning_payload['claim_types'] == ['retaliation']
        assert len(reasoning_payload['timeline_events']) == 1
        assert len(reasoning_payload['temporal_proof_leads']) == 1
        assert len(reasoning_payload['temporal_relations']) == 1
        assert len(reasoning_payload['contradiction_signals']) == 2
        assert any('forall t (AtTime(t,t_2025_03_01) -> Fact(fact_1,t))' in formula for formula in reasoning_payload['tdfol_formulas'])
        assert any('forall t (During(t,t_2025_03_01,t_2025_03_31) -> EvidenceLead(lead_1,t))' in formula for formula in reasoning_payload['tdfol_formulas'])
        assert 'Before(fact_1,fact_2)' in reasoning_payload['tdfol_formulas']
        assert 'Happens(fact_1,t_2025_03_01)' in reasoning_payload['dcec_formulas']
        assert 'AvailableDuring(lead_1,t_2025_03_01,t_2025_03_31)' in reasoning_payload['dcec_formulas']
        assert 'Conflicts(employee_complained_to_hr,employee_was_terminated)' in reasoning_payload['dcec_formulas']
        assert result['metadata']['details']['temporal_reasoning_payload'] == reasoning_payload


def test_run_hybrid_reasoning_returns_temporal_bridge_bundle():
    predicates = [
        {
            'predicate_type': 'claim_element',
            'claim_type': 'retaliation',
            'predicate_id': 'retaliation:1',
            'claim_element_id': 'retaliation:1',
            'claim_element_text': 'Protected activity',
        },
        {
            'predicate_type': 'temporal_fact',
            'claim_type': 'retaliation',
            'predicate_id': 'temporal_fact:fact_1',
            'fact_id': 'fact_1',
            'text': 'Employee complained to HR.',
            'start_date': '2025-03-01',
            'end_date': '2025-03-01',
            'granularity': 'day',
            'is_approximate': False,
            'is_range': False,
            'relative_markers': [],
        },
        {
            'predicate_type': 'temporal_relation',
            'claim_type': 'retaliation',
            'predicate_id': 'timeline_relation_001',
            'relation_type': 'before',
            'source_fact_id': 'fact_1',
            'target_fact_id': 'fact_2',
        },
    ]

    result = run_hybrid_reasoning({'predicates': predicates})

    assert result['status'] == 'success'
    assert result['metadata']['operation'] == 'run_hybrid_reasoning'
    assert result['metadata']['implementation_status'] == 'implemented'
    assert result['metadata']['details']['reasoning_mode'] == 'temporal_bridge'
    assert result['predicate_count'] == 3
    assert result['result']['formalism'] == 'tdfol_dcec_bridge_v1'
    assert result['result']['reasoning_mode'] == 'temporal_bridge'
    assert result['result']['timeline_event_count'] == 1
    assert result['result']['temporal_relation_count'] == 1
    assert result['result']['contradiction_signal_count'] == 0
    assert 'forall t (AtTime(t,t_2025_03_01) -> Fact(fact_1,t))' in result['result']['tdfol_formulas']
    assert 'Before(fact_1,fact_2)' in result['result']['tdfol_formulas']
    assert 'Happens(fact_1,t_2025_03_01)' in result['result']['dcec_formulas']
    assert result['temporal_reasoning_payload']['tdfol_formulas'] == result['result']['tdfol_formulas']


def test_logic_entrypoints_preserve_claim_support_temporal_handoff():
    predicates = [
        {
            'predicate_type': 'claim_element',
            'claim_type': 'retaliation',
            'predicate_id': 'retaliation:1',
            'claim_element_id': 'retaliation:1',
            'claim_element_text': 'Protected activity',
        },
        {
            'predicate_type': 'temporal_fact',
            'claim_type': 'retaliation',
            'predicate_id': 'temporal_fact:fact_1',
            'fact_id': 'fact_1',
            'text': 'Employee complained to HR.',
            'start_date': '2025-03-01',
            'end_date': '2025-03-01',
            'granularity': 'day',
            'is_approximate': False,
            'is_range': False,
            'relative_markers': [],
        },
    ]
    payload = {
        'predicates': predicates,
        'claim_support_temporal_handoff': {
            'claim_type': 'retaliation',
            'claim_element_id': 'retaliation:1',
            'unresolved_temporal_issue_count': 1,
            'unresolved_temporal_issue_ids': ['timeline-gap-001'],
            'chronology_task_count': 1,
            'event_ids': ['fact_1'],
            'temporal_fact_ids': ['fact_1'],
            'temporal_relation_ids': ['timeline_relation_001'],
            'timeline_issue_ids': ['timeline-gap-001'],
            'temporal_issue_ids': ['timeline-gap-001'],
            'temporal_proof_bundle_ids': ['retaliation:1:bundle_001'],
            'temporal_proof_objectives': ['resolve_temporal_rule_profile'],
        },
    }

    proof_result = prove_claim_elements(payload)
    contradiction_result = check_contradictions(payload)
    hybrid_result = run_hybrid_reasoning(payload)

    for result in (proof_result, contradiction_result, hybrid_result):
        handoff = result['temporal_reasoning_payload']['claim_support_temporal_handoff']
        assert handoff == payload['claim_support_temporal_handoff']
        assert handoff['unresolved_temporal_issue_count'] == 1
        assert handoff['event_ids'] == ['fact_1']
        assert handoff['temporal_proof_bundle_ids'] == ['retaliation:1:bundle_001']
        theorem_export_metadata = result['temporal_reasoning_payload']['theorem_export_metadata']
        assert theorem_export_metadata['contract_version'] == 'claim_support_temporal_handoff_v1'
        assert theorem_export_metadata['chronology_blocked'] is True
        assert theorem_export_metadata['chronology_task_count'] == 1
        assert theorem_export_metadata['temporal_issue_ids'] == ['timeline-gap-001']

    assert hybrid_result['result']['theorem_export_metadata'] == hybrid_result['temporal_reasoning_payload']['theorem_export_metadata']