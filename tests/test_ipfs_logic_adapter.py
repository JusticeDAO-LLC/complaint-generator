import pytest

from integrations.ipfs_datasets.logic import check_contradictions, prove_claim_elements


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