import pytest

from integrations.ipfs_datasets.logic import check_contradictions, prove_claim_elements


pytestmark = pytest.mark.no_auto_network


def test_logic_stubbed_adapters_summarize_temporal_predicate_shapes():
    predicates = [
        {'predicate_type': 'claim_element', 'claim_type': 'retaliation', 'predicate_id': 'retaliation:1'},
        {'predicate_type': 'support_trace', 'claim_type': 'retaliation', 'predicate_id': 'fact:support'},
        {'predicate_type': 'temporal_fact', 'claim_type': 'retaliation', 'predicate_id': 'temporal_fact:fact_1'},
        {'predicate_type': 'temporal_proof_lead', 'claim_type': 'retaliation', 'predicate_id': 'temporal_proof_lead:lead_1'},
        {'predicate_type': 'temporal_relation', 'claim_type': 'retaliation', 'predicate_id': 'timeline_relation_001'},
        {'predicate_type': 'temporal_issue', 'claim_type': 'retaliation', 'predicate_id': 'temporal_reverse_before_001'},
        {'predicate_type': 'contradiction_candidate', 'claim_type': 'retaliation', 'predicate_id': 'contradiction:retaliation:1:0'},
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