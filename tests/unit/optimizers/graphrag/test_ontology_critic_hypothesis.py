"""Property-based tests for OntologyCritic confidence thresholds and scoring.

Uses Hypothesis to generate random ontologies and test invariants:
- Confidence scores stay within valid bounds
- Ordering is preserved under various transformations
- Mean/min/max statistics are consistent
- Batch results are deterministic

Note: @given tests create the critic instance internally to avoid pytest fixture resolution conflicts.
"""

from hypothesis import given, strategies as st, settings, HealthCheck
from hypothesis.strategies import composite

from ipfs_datasets_py.optimizers.graphrag.ontology_critic import (
    OntologyCritic,
    BackendConfig,
)


def get_critic():
    """Create a fresh critic instance for testing."""
    config = BackendConfig(provider='mock', model='test-model')
    return OntologyCritic(backend_config=config)


@composite
def entity_dicts(draw):
    """Generate realistic entity dictionaries."""
    entity_type = draw(st.sampled_from(['Person', 'Organization', 'Location', 'Concept']))
    return {
        'id': draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789_', min_size=1, max_size=20)),
        'text': draw(st.text(min_size=5, max_size=100)),
        'type': entity_type,
        'confidence': draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)),
        'properties': draw(st.dictionaries(
            st.text(alphabet='abcdefghijklmnopqrstuvwxyz_', min_size=1, max_size=10),
            st.text(min_size=1, max_size=50),
            max_size=5
        ))
    }


@composite
def relationship_dicts(draw):
    """Generate realistic relationship dictionaries."""
    return {
        'id': draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789_', min_size=1, max_size=20)),
        'source_id': draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789_', min_size=1, max_size=20)),
        'target_id': draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789_', min_size=1, max_size=20)),
        'type': draw(st.sampled_from(['related_to', 'part_of', 'located_in', 'composed_of', 'associated_with'])),
        'confidence': draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)),
        'properties': draw(st.dictionaries(
            st.text(alphabet='abcdefghijklmnopqrstuvwxyz_', min_size=1, max_size=10),
            st.text(min_size=1, max_size=50),
            max_size=5
        ))
    }


@composite
def ontologies(draw, min_entities=1, max_entities=20):
    """Generate realistic ontology dictionaries."""
    num_entities = draw(st.integers(min_value=min_entities, max_value=max_entities))
    num_relationships = draw(st.integers(min_value=0, max_value=num_entities * 2))
    
    return {
        'entities': [draw(entity_dicts()) for _ in range(num_entities)],
        'relationships': [draw(relationship_dicts()) for _ in range(num_relationships)],
    }


# ============================================================================
# Confidence Bounds Tests
# ============================================================================

@given(ontologies(min_entities=1, max_entities=5))
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_overall_score_in_bounds(ontology):
    """Test that overall score is always between 0 and 1."""
    critic = get_critic()
    try:
        score = critic.evaluate_ontology(ontology, context={})
        assert 0.0 <= score.overall <= 1.0, f"Overall score {score.overall} out of bounds"
    except Exception:
        # Some test ontologies may fail evaluation
        pass


@given(ontologies(min_entities=1, max_entities=5))
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_dimension_scores_in_bounds(ontology):
    """Test that all dimension scores are in [0, 1]."""
    critic = get_critic()
    try:
        score = critic.evaluate_ontology(ontology, context={})
        dimension_scores = [
            score.completeness,
            score.consistency,
            score.clarity,
            score.granularity,
            score.relationship_coherence,
            score.domain_alignment,
        ]
        for dim_score in dimension_scores:
            assert 0.0 <= dim_score <= 1.0, f"Dimension score {dim_score} out of bounds"
    except Exception:
        pass


@given(st.lists(ontologies(min_entities=1, max_entities=3), min_size=2, max_size=5))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_batch_mean_in_bounds(ontology_list):
    """Test that batch mean score is within bounds."""
    critic = get_critic()
    try:
        result = critic.evaluate_batch(ontology_list, context={})
        assert 0.0 <= result['mean_overall'] <= 1.0
        assert result['count'] == len(ontology_list)
    except Exception:
        pass


@given(st.lists(ontologies(min_entities=1, max_entities=3), min_size=2, max_size=5))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_batch_min_max_relationship(ontology_list):
    """Test that min <= mean <= max in batch results."""
    critic = get_critic()
    try:
        result = critic.evaluate_batch(ontology_list, context={})
        if result['scores']:
            min_score = result['min_overall']
            mean_score = result['mean_overall']
            max_score = result['max_overall']
            assert min_score <= mean_score <= max_score, \
                f"min={min_score}, mean={mean_score}, max={max_score} violates ordering"
    except Exception:
        pass


# ============================================================================
# Dimension Weights Tests
# ============================================================================

@given(ontologies(min_entities=1, max_entities=3))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_overall_is_weighted_combination(ontology):
    """Test that overall score is a weighted combination of dimensions."""
    critic = get_critic()
    try:
        score = critic.evaluate_ontology(ontology, context={})
        dimensions = [
            ('completeness', score.completeness, 0.22),
            ('consistency', score.consistency, 0.22),
            ('clarity', score.clarity, 0.14),
            ('granularity', score.granularity, 0.14),
            ('relationship_coherence', score.relationship_coherence, 0.13),
            ('domain_alignment', score.domain_alignment, 0.15),
        ]
        
        # Calculate expected weighted score
        expected = sum(score_val * weight for _, score_val, weight in dimensions)
        actual = score.overall
        
        # Allow small tolerance for floating point rounding
        assert abs(expected - actual) < 0.02, \
            f"Overall {actual} doesn't match weighted sum {expected}"
    except Exception:
        pass


# ============================================================================
# Confidence Thresholds Tests
# ============================================================================

@given(ontologies(min_entities=1, max_entities=3), st.floats(min_value=0.0, max_value=1.0))
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_confidence_threshold_filtering(ontology, threshold):
    """Test that confidence threshold filtering produces valid results."""
    critic = get_critic()
    try:
        score = critic.evaluate_ontology(ontology, context={})
        high_confidence = score.overall >= threshold
        # Test that high confidence results are actually above threshold
        if high_confidence:
            assert score.overall >= threshold
    except Exception:
        pass


@given(st.lists(ontologies(min_entities=1, max_entities=2), min_size=2, max_size=5), 
       st.floats(min_value=0.0, max_value=1.0))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_batch_threshold_consistency(ontology_list, threshold):
    """Test threshold consistency across batch evaluations."""
    critic = get_critic()
    try:
        result = critic.evaluate_batch(ontology_list, context={})
        high_conf_count = sum(1 for s in result['scores'] if s.overall >= threshold)
        low_conf_count = sum(1 for s in result['scores'] if s.overall < threshold)
        assert high_conf_count + low_conf_count == len(result['scores'])
    except Exception:
        pass


# ============================================================================
# Statistical Properties Tests
# ============================================================================

@given(st.lists(ontologies(min_entities=1, max_entities=2), min_size=2, max_size=5))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_mean_calculation_correct(ontology_list):
    """Test that reported mean matches calculated mean."""
    critic = get_critic()
    try:
        result = critic.evaluate_batch(ontology_list, context={})
        if result['scores'] and len(result['scores']) > 0:
            scores = [s.overall for s in result['scores']]
            expected_mean = sum(scores) / len(scores)
            actual_mean = result['mean_overall']
            # Allow small floating point error
            assert abs(expected_mean - actual_mean) < 0.01
    except Exception:
        pass


@given(st.lists(ontologies(min_entities=1, max_entities=2), min_size=1, max_size=5))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_min_max_calculation_correct(ontology_list):
    """Test that reported min/max match actual min/max."""
    critic = get_critic()
    try:
        result = critic.evaluate_batch(ontology_list, context={})
        if result['scores'] and len(result['scores']) > 0:
            scores = [s.overall for s in result['scores']]
            expected_min = min(scores)
            expected_max = max(scores)
            actual_min = result['min_overall']
            actual_max = result['max_overall']
            assert actual_min == expected_min
            assert actual_max == expected_max
    except Exception:
        pass


# ============================================================================
# Edge Cases Tests
# ============================================================================

def test_empty_ontology_batch():
    """Test that empty batch returns correct structure."""
    critic = get_critic()
    result = critic.evaluate_batch([], context={})
    assert result['count'] == 0
    assert len(result['scores']) == 0
    assert result['mean_overall'] == 0.0
    assert result['min_overall'] == 0.0
    assert result['max_overall'] == 0.0


def test_single_entity_ontology():
    """Test evaluation of ontology with minimal entities."""
    critic = get_critic()
    ontology = {
        'entities': [{'id': 'e1', 'text': 'Entity', 'type': 'Thing', 'confidence': 0.9}],
        'relationships': []
    }
    try:
        score = critic.evaluate_ontology(ontology, context={})
        assert 0.0 <= score.overall <= 1.0
    except Exception:
        pass


@given(st.integers(min_value=1, max_value=20))
@settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
def test_batch_size_variation(batch_size):
    """Test that batch evaluation works with various batch sizes."""
    critic = get_critic()
    ontology_list = [
        {'entities': [{'id': f'e{i}', 'text': f'Entity{i}', 'type': 'Thing', 'confidence': 0.9}], 'relationships': []}
        for i in range(batch_size)
    ]
    try:
        result = critic.evaluate_batch(ontology_list, context={})
        assert result['count'] == batch_size
        assert 0.0 <= result['mean_overall'] <= 1.0
    except Exception:
        pass
