"""
Comprehensive tests for ScoreAnalyzer statistical metrics.

Tests cover all analysis methods:
- Single score analysis (weakest_dimension, strongest_dimension, etc.)
- Batch analysis (mean_overall, percentile_overall, batch_dimension_stats)
- Comparative analysis (score_improvement_percent, recommend_focus_dimensions)
- Statistical metrics (entropy, variance, z-scores, MAD)

Uses hypothesis for property-based testing of numerical properties.
"""

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from dataclasses import dataclass

from ipfs_datasets_py.optimizers.graphrag.score_analyzer import (
    ScoreAnalyzer,
    STANDARD_DIMENSIONS,
    DimensionStats,
)


@dataclass
class MockCriticScore:
    """Mock CriticScore for testing."""
    overall: float = 0.5
    completeness: float = 0.5
    consistency: float = 0.5
    clarity: float = 0.5
    granularity: float = 0.5
    relationship_coherence: float = 0.5
    domain_alignment: float = 0.5


def create_score(**kwargs) -> MockCriticScore:
    """Helper to create mock score with custom values."""
    defaults = {f: 0.5 for f in STANDARD_DIMENSIONS}
    defaults.update(kwargs)
    defaults.setdefault('overall', kwargs.get('completeness', 0.5))
    return MockCriticScore(**defaults)


class TestScoreAnalyzerInitialization:
    """Test ScoreAnalyzer initialization and configuration."""
    
    def test_default_initialization(self):
        """Test analyzer initializes with standard dimensions."""
        analyzer = ScoreAnalyzer()
        assert analyzer.DIMENSIONS == STANDARD_DIMENSIONS
    
    def test_custom_dimensions(self):
        """Test analyzer accepts custom dimension set."""
        custom_dims = ("dim1", "dim2", "dim3")
        analyzer = ScoreAnalyzer(dimensions=custom_dims)
        assert analyzer.DIMENSIONS == custom_dims


class TestSingleScoreAnalysis:
    """Test methods that analyze individual CriticScore objects."""
    
    def test_weakest_dimension(self):
        """Test identifying dimension with lowest score."""
        analyzer = ScoreAnalyzer()
        score = create_score(clarity=0.2, completeness=0.8)
        assert analyzer.weakest_dimension(score) == "clarity"
    
    def test_strongest_dimension(self):
        """Test identifying dimension with highest score."""
        analyzer = ScoreAnalyzer()
        score = create_score(completeness=0.9, consistency=0.5)
        assert analyzer.strongest_dimension(score) == "completeness"
    
    def test_dimension_range_equal_scores(self):
        """Test range is zero when all dimensions equal."""
        analyzer = ScoreAnalyzer()
        score = create_score(
            completeness=0.5, consistency=0.5, clarity=0.5,
            granularity=0.5, relationship_coherence=0.5, domain_alignment=0.5
        )
        assert analyzer.dimension_range(score) == pytest.approx(0.0)
    
    def test_dimension_range_varied_scores(self):
        """Test range computation with varied scores."""
        analyzer = ScoreAnalyzer()
        score = create_score(
            completeness=0.9, consistency=0.3, clarity=0.6,
            granularity=0.4, relationship_coherence=0.5, domain_alignment=0.7
        )
        result = analyzer.dimension_range(score)
        assert result == pytest.approx(0.6)  # 0.9 - 0.3
    
    def test_dimensions_above_threshold(self):
        """Test counting dimensions above threshold."""
        analyzer = ScoreAnalyzer()
        score = create_score(
            completeness=0.8, consistency=0.75, clarity=0.6,
            granularity=0.5, relationship_coherence=0.7, domain_alignment=0.65
        )
        # Above 0.7 (strictly >): completeness=0.8, consistency=0.75 = 2 dims
        # (relationship_coherence=0.7 is equal, not above)
        assert analyzer.dimensions_above_threshold(score, 0.7) == 2
    
    def test_dimension_delta_improvement(self):
        """Test computing deltas between two scores."""
        analyzer = ScoreAnalyzer()
        before = create_score(completeness=0.5, consistency=0.6)
        after = create_score(completeness=0.7, consistency=0.5)
        
        deltas = analyzer.dimension_delta(before, after)
        assert deltas["completeness"] == pytest.approx(0.2)
        assert deltas["consistency"] == pytest.approx(-0.1)
    
    def test_score_balance_ratio_equal(self):
        """Test balance ratio is 1.0 when all dimensions equal."""
        analyzer = ScoreAnalyzer()
        score = create_score(
            completeness=0.5, consistency=0.5, clarity=0.5,
            granularity=0.5, relationship_coherence=0.5, domain_alignment=0.5
        )
        assert analyzer.score_balance_ratio(score) == pytest.approx(1.0)
    
    def test_score_balance_ratio_varied(self):
        """Test balance ratio with varied dimensions."""
        analyzer = ScoreAnalyzer()
        score = create_score(
            completeness=0.8, consistency=0.4, clarity=0.5,
            granularity=0.5, relationship_coherence=0.5, domain_alignment=0.5
        )
        # max: 0.8, min: 0.4, ratio: 0.8/0.4 = 2.0
        assert analyzer.score_balance_ratio(score) == pytest.approx(2.0)
    
    def test_score_dimension_variance_equal(self):
        """Test variance is zero when all dimensions equal."""
        analyzer = ScoreAnalyzer()
        score = create_score()
        assert analyzer.score_dimension_variance(score) == pytest.approx(0.0)
    
    def test_score_dimension_variance_varied(self):
        """Test variance computation with varied dimensions."""
        analyzer = ScoreAnalyzer()
        # Dims: [0.9, 0.3, 0.5, 0.5, 0.5, 0.7]
        # Mean: 3.4/6 ≈ 0.5667
        # Variance: ((0.9-0.5667)^2 + (0.3-0.5667)^2 + ...) / 6 ≈ 0.0356
        score = create_score(
            completeness=0.9, consistency=0.3, clarity=0.5,
            granularity=0.5, relationship_coherence=0.5, domain_alignment=0.7
        )
        variance = analyzer.score_dimension_variance(score)
        assert variance == pytest.approx(0.0356, abs=0.001)
    
    def test_score_dimension_std(self):
        """Test standard deviation computation."""
        analyzer = ScoreAnalyzer()
        score = create_score(
            completeness=0.9, consistency=0.3, clarity=0.5,
            granularity=0.5, relationship_coherence=0.5, domain_alignment=0.7
        )
        std = analyzer.score_dimension_std(score)
        variance = analyzer.score_dimension_variance(score)
        assert std == pytest.approx(variance ** 0.5)
    
    def test_score_dimension_mean_abs_deviation(self):
        """Test Mean Absolute Deviation computation."""
        analyzer = ScoreAnalyzer()
        # Dims: [0.9, 0.3, 0.5, 0.5, 0.5, 0.7]
        # Mean: 3.4/6 ≈ 0.5667
        # MAD: (|0.9-0.5667| + |0.3-0.5667| + ... ) / 6 ≈ 0.1556
        score = create_score(
            completeness=0.9, consistency=0.3, clarity=0.5,
            granularity=0.5, relationship_coherence=0.5, domain_alignment=0.7
        )
        mad = analyzer.score_dimension_mean_abs_deviation(score)
        assert mad == pytest.approx(0.1556, abs=0.001)
    
    def test_score_dimension_entropy_uniform(self):
        """Test entropy is well-defined for uniform distribution."""
        analyzer = ScoreAnalyzer()
        score = create_score()
        entropy = analyzer.score_dimension_entropy(score)
        # All equal = uniform distribution, should be valid number
        assert isinstance(entropy, float)
        assert entropy >= 0.0
    
    def test_score_dimension_max_z_equal_dims(self):
        """Test max z-score is zero when dimensions are equal."""
        analyzer = ScoreAnalyzer()
        score = create_score()
        z_max = analyzer.score_dimension_max_z(score)
        assert z_max == pytest.approx(0.0)
    
    def test_score_dimension_max_z_varied_dims(self):
        """Test max z-score with varied dimensions."""
        analyzer = ScoreAnalyzer()
        score = create_score(completeness=0.9, consistency=0.1)  # Others at 0.5
        z_max = analyzer.score_dimension_max_z(score)
        assert z_max > 0.0
    
    def test_score_dimension_min_z_equal_dims(self):
        """Test min z-score is zero when dimensions are equal."""
        analyzer = ScoreAnalyzer()
        score = create_score()
        z_min = analyzer.score_dimension_min_z(score)
        assert z_min == pytest.approx(0.0)


class TestBatchAnalysis:
    """Test methods that analyze batches of CriticScore objects."""
    
    def test_mean_overall_empty_batch(self):
        """Test mean is 0.0 for empty batch."""
        analyzer = ScoreAnalyzer()
        assert analyzer.mean_overall([]) == pytest.approx(0.0)
    
    def test_mean_overall_single_score(self):
        """Test mean for batch with single score."""
        analyzer = ScoreAnalyzer()
        score = create_score(overall=0.7)
        assert analyzer.mean_overall([score]) == pytest.approx(0.7)
    
    def test_mean_overall_multiple_scores(self):
        """Test mean computation across multiple scores."""
        analyzer = ScoreAnalyzer()
        scores = [
            create_score(overall=0.6),
            create_score(overall=0.8),
            create_score(overall=0.7),
        ]
        assert analyzer.mean_overall(scores) == pytest.approx(0.7)
    
    def test_dimension_mean(self):
        """Test computing mean for specific dimension."""
        analyzer = ScoreAnalyzer()
        scores = [
            create_score(completeness=0.6),
            create_score(completeness=0.8),
            create_score(completeness=0.7),
        ]
        assert analyzer.dimension_mean(scores, "completeness") == pytest.approx(0.7)
    
    def test_percentile_overall_empty_raises(self):
        """Test percentile raises on empty batch."""
        analyzer = ScoreAnalyzer()
        with pytest.raises(ValueError):
            analyzer.percentile_overall([], percentile=75.0)
    
    def test_percentile_overall_invalid_percentile_raises(self):
        """Test percentile raises on invalid percentile."""
        analyzer = ScoreAnalyzer()
        scores = [create_score()]
        with pytest.raises(ValueError):
            analyzer.percentile_overall(scores, percentile=150.0)
    
    def test_percentile_overall_single_score(self):
        """Test percentile with single score."""
        analyzer = ScoreAnalyzer()
        score = create_score(overall=0.75)
        assert analyzer.percentile_overall([score], 50.0) == pytest.approx(0.75)
    
    def test_percentile_overall_75th(self):
        """Test 75th percentile computation."""
        analyzer = ScoreAnalyzer()
        scores = [
            create_score(overall=float(i) / 100) for i in range(1, 101)
        ]
        p75 = analyzer.percentile_overall(scores, percentile=75.0)
        # Should be around 0.75
        assert 0.72 < p75 < 0.78
    
    def test_min_max_overall_empty(self):
        """Test min/max for empty batch."""
        analyzer = ScoreAnalyzer()
        min_val, max_val = analyzer.min_max_overall([])
        assert min_val == 0.0
        assert max_val == 0.0
    
    def test_min_max_overall_values(self):
        """Test min/max computation."""
        analyzer = ScoreAnalyzer()
        scores = [
            create_score(overall=0.3),
            create_score(overall=0.8),
            create_score(overall=0.5),
        ]
        min_val, max_val = analyzer.min_max_overall(scores)
        assert min_val == pytest.approx(0.3)
        assert max_val == pytest.approx(0.8)
    
    def test_batch_dimension_stats(self):
        """Test computing statistics across batch."""
        analyzer = ScoreAnalyzer()
        scores = [
            create_score(completeness=0.6),
            create_score(completeness=0.8),
            create_score(completeness=0.7),
        ]
        stats = analyzer.batch_dimension_stats(scores)
        
        assert "completeness" in stats
        assert stats["completeness"].count == 3
        assert stats["completeness"].overall == pytest.approx(0.7)
        assert stats["completeness"].min_value == pytest.approx(0.6)
        assert stats["completeness"].max_value == pytest.approx(0.8)
    
    def test_batch_dimension_stats_empty(self):
        """Test dimension stats for empty batch."""
        analyzer = ScoreAnalyzer()
        stats = analyzer.batch_dimension_stats([])
        assert stats == {}
    
    def test_batch_divergence_single_score(self):
        """Test divergence is zero for single score."""
        analyzer = ScoreAnalyzer()
        scores = [create_score(overall=0.7)]
        assert analyzer.batch_divergence(scores) == pytest.approx(0.0)
    
    def test_batch_divergence_identical_scores(self):
        """Test divergence is zero for identical scores."""
        analyzer = ScoreAnalyzer()
        scores = [create_score(overall=0.7) for _ in range(5)]
        assert analyzer.batch_divergence(scores) == pytest.approx(0.0)
    
    def test_batch_divergence_varied_scores(self):
        """Test divergence increases with variation."""
        analyzer = ScoreAnalyzer()
        scores = [
            create_score(overall=0.3),
            create_score(overall=0.5),
            create_score(overall=0.7),
        ]
        divergence = analyzer.batch_divergence(scores)
        # Mean is 0.5, distances are 0.2, 0.0, 0.2 = avg 0.133
        assert divergence == pytest.approx(0.133, abs=0.01)


class TestComparativeAnalysis:
    """Test methods for comparing and analyzing score changes."""
    
    def test_score_improvement_percent_increase(self):
        """Test improvement percent for score increase."""
        analyzer = ScoreAnalyzer()
        before = create_score(overall=0.5)
        after = create_score(overall=0.6)
        improvement = analyzer.score_improvement_percent(before, after)
        # (0.6 - 0.5) / 0.5 * 100 = 20%
        assert improvement == pytest.approx(20.0)
    
    def test_score_improvement_percent_decrease(self):
        """Test improvement percent for score decrease."""
        analyzer = ScoreAnalyzer()
        before = create_score(overall=0.8)
        after = create_score(overall=0.6)
        improvement = analyzer.score_improvement_percent(before, after)
        # (0.6 - 0.8) / 0.8 * 100 = -25%
        assert improvement == pytest.approx(-25.0)
    
    def test_score_improvement_percent_zero_before(self):
        """Test improvement percent when before score is zero."""
        analyzer = ScoreAnalyzer()
        before = create_score(overall=0.0)
        after = create_score(overall=0.5)
        improvement = analyzer.score_improvement_percent(before, after)
        # Division by zero handled -> return 0.0
        assert improvement == pytest.approx(0.0)
    
    def test_dimension_improvement_count_all_improve(self):
        """Test counting improved dimensions."""
        analyzer = ScoreAnalyzer()
        before = create_score(completeness=0.5, consistency=0.5, clarity=0.5)
        after = create_score(completeness=0.6, consistency=0.6, clarity=0.6)
        
        improvements = analyzer.dimension_improvement_count(
            before, after, min_improvement=0.05
        )
        # At least 3 dimensions improved
        assert improvements >= 3
    
    def test_dimension_improvement_count_none_improve(self):
        """Test when no dimensions improve."""
        analyzer = ScoreAnalyzer()
        before = create_score(completeness=0.8)
        after = create_score(completeness=0.7)
        
        improvements = analyzer.dimension_improvement_count(
            before, after, min_improvement=0.05
        )
        # Completeness decreased, not improved
        assert improvements == 0
    
    def test_recommend_focus_dimensions(self):
        """Test recommending dimensions for improvement."""
        analyzer = ScoreAnalyzer()
        scores = [
            create_score(completeness=0.8, consistency=0.3, clarity=0.7),
            create_score(completeness=0.75, consistency=0.25, clarity=0.8),
        ]
        
        recommendations = analyzer.recommend_focus_dimensions(scores, count=2)
        # Should recommend consistency and completeness (lowest avg scores)
        assert len(recommendations) == 2
        assert recommendations[0][0] in ["consistency", "completeness"]
        assert recommendations[0][1] <= recommendations[1][1]


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_all_zero_dimensions(self):
        """Test scores with all zero dimensions."""
        analyzer = ScoreAnalyzer()
        score = create_score(
            completeness=0.0, consistency=0.0, clarity=0.0,
            granularity=0.0, relationship_coherence=0.0, domain_alignment=0.0,
            overall=0.0
        )
        range_val = analyzer.dimension_range(score)
        assert range_val == pytest.approx(0.0)
    
    def test_all_max_dimensions(self):
        """Test scores with all maximum dimensions."""
        analyzer = ScoreAnalyzer()
        score = create_score(
            completeness=1.0, consistency=1.0, clarity=1.0,
            granularity=1.0, relationship_coherence=1.0, domain_alignment=1.0,
            overall=1.0
        )
        entropy = analyzer.score_dimension_entropy(score)
        # Uniform distribution should be valid
        assert isinstance(entropy, float)
        assert entropy >= 0.0
    
    def test_mixed_extreme_values(self):
        """Test with extreme value differences."""
        analyzer = ScoreAnalyzer()
        score = create_score(
            completeness=0.0, consistency=1.0, clarity=0.0,
            granularity=1.0, relationship_coherence=0.0, domain_alignment=1.0
        )
        z_max = analyzer.score_dimension_max_z(score)
        # With extreme alternation, z-scores should be significant
        assert z_max > 0.5


class TestPropertyBased:
    """Property-based tests using hypothesis."""
    
    @given(st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_weakest_le_strongest_dimension(self, dim_value: float):
        """Property: weakest dimension score ≤ strongest dimension score."""
        analyzer = ScoreAnalyzer()
        score = create_score(
            completeness=dim_value,
            consistency=dim_value + 0.1 if dim_value < 0.9 else 1.0,
        )
        weakest_score = getattr(score, analyzer.weakest_dimension(score))
        strongest_score = getattr(score, analyzer.strongest_dimension(score))
        assert weakest_score <= strongest_score
    
    @given(st.lists(
        st.floats(min_value=0.0, max_value=1.0),
        min_size=1,
        max_size=10
    ))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_mean_within_range(self, overall_values: list):
        """Property: mean overall is between min and max scores."""
        analyzer = ScoreAnalyzer()
        scores = [create_score(overall=v) for v in overall_values]
        mean = analyzer.mean_overall(scores)
        min_val, max_val = analyzer.min_max_overall(scores)
        assert min_val <= mean <= max_val
    
    @given(st.floats(min_value=0.5, max_value=1.0),
           st.floats(min_value=0.0, max_value=0.5))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_balance_ratio_gte_one(self, high: float, low: float):
        """Property: balance ratio is always ≥ 1.0."""
        analyzer = ScoreAnalyzer()
        score = create_score(
            completeness=high,
            consistency=low,
            clarity=0.5,
            granularity=0.5,
            relationship_coherence=0.5,
            domain_alignment=0.5,
        )
        if low > 0:  # Avoid zero denominator
            ratio = analyzer.score_balance_ratio(score)
            assert ratio >= 1.0
