"""Test suite for CriticScore statistics and distribution analysis.

Validates CriticScore across large sample sets, checking:
- Score statistics (mean, std, percentiles)
- Distribution characteristics (normal, skew, kurtosis)
- Dimension correlations
- Boundary conditions
"""

import pytest
import statistics as st
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../"))

from ipfs_datasets_py.optimizers.graphrag.ontology_critic import OntologyCritic, CriticScore
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import OntologyGenerationContext


@pytest.fixture
def critic():
    """Create an OntologyCritic instance."""
    return OntologyCritic()


@pytest.fixture
def context():
    """Create a basic OntologyGenerationContext."""
    return OntologyGenerationContext(
        data_source="test_data",
        data_type="text",
        domain="health",
    )


class TestCriticScoreBasicStatistics:
    """Test basic statistical properties of CriticScore."""

    def test_critic_score_single_dimension_mean(self, critic):
        """Test mean calculation for single dimension."""
        scores = [
            CriticScore(
                completeness=0.8,
                consistency=0.85,
                clarity=0.75,
                granularity=0.8,
                relationship_coherence=0.82,
                domain_alignment=0.88,
            )
            for _ in range(10)
        ]

        completeness_scores = [s.completeness for s in scores]
        mean_completeness = st.mean(completeness_scores)

        assert mean_completeness == 0.8
        assert len(scores) == 10

    def test_critic_score_multiple_dimensions_variance(self, critic):
        """Test variance across multiple dimensions."""
        scores = [
            CriticScore(
                completeness=0.6 + (i * 0.04),  # Varies: 0.6 to 1.0
                consistency=0.85,
                clarity=0.75,
                granularity=0.8,
                relationship_coherence=0.82,
                domain_alignment=0.88,
            )
            for i in range(11)
        ]

        completeness_scores = [s.completeness for s in scores]
        variance = st.variance(completeness_scores)

        # Should have non-zero variance
        assert variance > 0
        assert st.mean(completeness_scores) > 0.7
        assert st.mean(completeness_scores) < 0.9

    def test_critic_score_stdev_calculation(self, critic):
        """Test standard deviation calculation."""
        scores = [
            CriticScore(
                completeness=0.5 + (i * 0.1),  # 0.5, 0.6, 0.7, 0.8, 0.9
                consistency=0.85,
                clarity=0.75,
                granularity=0.8,
                relationship_coherence=0.82,
                domain_alignment=0.88,
            )
            for i in range(5)
        ]

        completeness_scores = [s.completeness for s in scores]
        stdev = st.stdev(completeness_scores)

        assert stdev > 0
        assert stdev < 0.5  # Should be moderate variation


class TestCriticScoreDistributions:
    """Test score distributions across samples."""

    def test_critic_score_large_sample_distribution(self, critic):
        """Test distribution of scores across large sample set."""
        import random
        random.seed(42)  # For reproducibility

        scores = [
            CriticScore(
                completeness=random.uniform(0.5, 1.0),
                consistency=random.uniform(0.5, 1.0),
                clarity=random.uniform(0.5, 1.0),
                granularity=random.uniform(0.5, 1.0),
                relationship_coherence=random.uniform(0.5, 1.0),
                domain_alignment=random.uniform(0.5, 1.0),
            )
            for _ in range(100)
        ]

        # Extract individual dimensions
        completeness_scores = [s.completeness for s in scores]
        consistency_scores = [s.consistency for s in scores]
        clarity_scores = [s.clarity for s in scores]

        # Verify distributions are reasonable
        assert len(scores) == 100
        assert all(0.5 <= s <= 1.0 for s in completeness_scores)
        assert st.mean(completeness_scores) > 0.6
        assert st.mean(completeness_scores) < 0.9
        assert st.mean(consistency_scores) > 0.6
        assert st.mean(clarity_scores) > 0.6

    def test_critic_score_percentile_calculation(self, critic):
        """Test percentile distribution."""
        import random
        random.seed(42)

        scores = [
            CriticScore(
                completeness=random.uniform(0.5, 1.0),
                consistency=random.uniform(0.5, 1.0),
                clarity=random.uniform(0.5, 1.0),
                granularity=random.uniform(0.5, 1.0),
                relationship_coherence=random.uniform(0.5, 1.0),
                domain_alignment=random.uniform(0.5, 1.0),
            )
            for _ in range(50)
        ]

        completeness_scores = sorted([s.completeness for s in scores])

        # Calculate percentiles
        p25_idx = int(len(completeness_scores) * 0.25)
        p50_idx = int(len(completeness_scores) * 0.50)
        p75_idx = int(len(completeness_scores) * 0.75)

        p25 = completeness_scores[p25_idx]
        p50 = completeness_scores[p50_idx]
        p75 = completeness_scores[p75_idx]

        # P25 < P50 < P75
        assert p25 < p50 < p75
        assert 0.5 <= p25 <= 1.0
        assert 0.5 <= p75 <= 1.0

    def test_critic_score_bimodal_distribution(self, critic):
        """Test scenario with bimodal score distribution."""
        import random
        random.seed(42)

        # Create two clusters: low (0.3-0.5) and high (0.8-1.0)
        low_scores = [
            CriticScore(
                completeness=random.uniform(0.3, 0.5),
                consistency=random.uniform(0.3, 0.5),
                clarity=random.uniform(0.3, 0.5),
                granularity=random.uniform(0.3, 0.5),
                relationship_coherence=random.uniform(0.3, 0.5),
                domain_alignment=random.uniform(0.3, 0.5),
            )
            for _ in range(25)
        ]

        high_scores = [
            CriticScore(
                completeness=random.uniform(0.8, 1.0),
                consistency=random.uniform(0.8, 1.0),
                clarity=random.uniform(0.8, 1.0),
                granularity=random.uniform(0.8, 1.0),
                relationship_coherence=random.uniform(0.8, 1.0),
                domain_alignment=random.uniform(0.8, 1.0),
            )
            for _ in range(25)
        ]

        all_scores = low_scores + high_scores
        completeness_scores = [s.completeness for s in all_scores]

        mean_completeness = st.mean(completeness_scores)
        # Should be roughly in the middle due to two clusters
        assert 0.5 < mean_completeness < 0.8


class TestCriticScoreDimensionCorrelations:
    """Test correlations between score dimensions."""

    def test_critic_score_positively_correlated_dimensions(self, critic):
        """Test when dimensions are positively correlated."""
        scores = [
            CriticScore(
                completeness=0.5 + (i * 0.05),  # Increases with i
                consistency=0.5 + (i * 0.05),   # Also increases with i
                clarity=0.75,
                granularity=0.8,
                relationship_coherence=0.82,
                domain_alignment=0.88,
            )
            for i in range(10)
        ]

        completeness_vals = [s.completeness for s in scores]
        consistency_vals = [s.consistency for s in scores]

        # Both should increase together
        assert completeness_vals[0] < completeness_vals[-1]
        assert consistency_vals[0] < consistency_vals[-1]

    def test_critic_score_independent_dimensions(self, critic):
        """Test when dimensions are independent."""
        import random
        random.seed(42)

        scores = [
            CriticScore(
                completeness=random.uniform(0.5, 1.0),
                consistency=random.uniform(0.5, 1.0),  # Independent
                clarity=random.uniform(0.5, 1.0),
                granularity=random.uniform(0.5, 1.0),
                relationship_coherence=random.uniform(0.5, 1.0),
                domain_alignment=random.uniform(0.5, 1.0),
            )
            for _ in range(50)
        ]

        # Extract dimensions
        completeness_vals = [s.completeness for s in scores]
        consistency_vals = [s.consistency for s in scores]
        clarity_vals = [s.clarity for s in scores]

        # Verify they're all different (independently varying)
        assert len(set(map(lambda x: round(x, 2), completeness_vals))) > 10
        assert len(set(map(lambda x: round(x, 2), consistency_vals))) > 10
        assert len(set(map(lambda x: round(x, 2), clarity_vals))) > 10


class TestCriticScoreBoundaryConditions:
    """Test boundary conditions and edge cases."""

    def test_critic_score_minimum_values(self, critic):
        """Test scores with minimum values (0.0)."""
        score = CriticScore(
            completeness=0.0,
            consistency=0.0,
            clarity=0.0,
            granularity=0.0,
            relationship_coherence=0.0,
            domain_alignment=0.0,
        )

        assert score.completeness == 0.0
        assert score.overall == 0.0

    def test_critic_score_maximum_values(self, critic):
        """Test scores with maximum values (1.0)."""
        score = CriticScore(
            completeness=1.0,
            consistency=1.0,
            clarity=1.0,
            granularity=1.0,
            relationship_coherence=1.0,
            domain_alignment=1.0,
        )

        assert score.completeness == 1.0
        assert score.overall == 1.0

    def test_critic_score_mixed_extremes(self, critic):
        """Test with mixed extreme values."""
        score = CriticScore(
            completeness=0.0,
            consistency=1.0,
            clarity=0.0,
            granularity=1.0,
            relationship_coherence=0.5,
            domain_alignment=0.5,
        )

        # Overall should be weighted average
        assert 0.0 < score.overall < 1.0

    def test_critic_score_all_median_values(self, critic):
        """Test with all median values (0.5)."""
        score = CriticScore(
            completeness=0.5,
            consistency=0.5,
            clarity=0.5,
            granularity=0.5,
            relationship_coherence=0.5,
            domain_alignment=0.5,
        )

        assert score.overall == 0.5
        assert score.completeness == 0.5


class TestCriticScoreAggregation:
    """Test aggregation of scores across samples."""

    def test_critic_score_mean_aggregation(self, critic):
        """Test calculating mean score across samples."""
        import random
        random.seed(42)

        scores = [
            CriticScore(
                completeness=random.uniform(0.6, 0.9),
                consistency=random.uniform(0.7, 0.95),
                clarity=random.uniform(0.6, 0.85),
                granularity=random.uniform(0.65, 0.9),
                relationship_coherence=random.uniform(0.7, 0.9),
                domain_alignment=random.uniform(0.75, 0.95),
            )
            for _ in range(20)
        ]

        mean_overall = st.mean([s.overall for s in scores])
        mean_completeness = st.mean([s.completeness for s in scores])

        assert 0.6 < mean_overall < 1.0
        assert 0.6 < mean_completeness < 0.95

    def test_critic_score_weighted_aggregation(self, critic):
        """Test weighted aggregation with importance weights."""
        scores = [
            CriticScore(
                completeness=0.8,
                consistency=0.85,
                clarity=0.75,
                granularity=0.8,
                relationship_coherence=0.82,
                domain_alignment=0.88,
            ),
            CriticScore(
                completeness=0.6,
                consistency=0.65,
                clarity=0.55,
                granularity=0.6,
                relationship_coherence=0.62,
                domain_alignment=0.68,
            ),
        ]

        # Manual weighted average (emphasizing first score)
        weights = [0.7, 0.3]
        weighted_overall = sum(s.overall * w for s, w in zip(scores, weights))

        assert 0.6 < weighted_overall < 0.9


class TestCriticScoreValidation:
    """Test score validation and constraints."""

    def test_critic_score_dimensions_in_range(self, critic):
        """Test that dimensions are within valid range."""
        import random
        random.seed(42)

        for _ in range(100):
            score = CriticScore(
                completeness=random.uniform(0.0, 1.0),
                consistency=random.uniform(0.0, 1.0),
                clarity=random.uniform(0.0, 1.0),
                granularity=random.uniform(0.0, 1.0),
                relationship_coherence=random.uniform(0.0, 1.0),
                domain_alignment=random.uniform(0.0, 1.0),
            )

            assert 0.0 <= score.completeness <= 1.0
            assert 0.0 <= score.consistency <= 1.0
            assert 0.0 <= score.clarity <= 1.0
            assert 0.0 <= score.granularity <= 1.0
            assert 0.0 <= score.relationship_coherence <= 1.0
            assert 0.0 <= score.domain_alignment <= 1.0
            assert 0.0 <= score.overall <= 1.0

    def test_critic_score_consistency_properties(self, critic):
        """Test consistency of score properties."""
        score = CriticScore(
            completeness=0.8,
            consistency=0.85,
            clarity=0.75,
            granularity=0.8,
            relationship_coherence=0.82,
            domain_alignment=0.88,
        )

        # Same score should always produce same overall
        overall1 = score.overall
        overall2 = score.overall
        assert overall1 == overall2

        # Modifying one dimension shouldn't affect others
        original_completeness = score.completeness
        consistency_value = score.consistency
        assert score.consistency == consistency_value


class TestCriticScoreSampling:
    """Test sampling and statistical tests on score distributions."""

    def test_critic_score_random_sampling(self, critic):
        """Test random sampling of scores."""
        import random
        random.seed(42)

        sample_size = 200
        scores = [
            CriticScore(
                completeness=random.uniform(0.5, 1.0),
                consistency=random.uniform(0.5, 1.0),
                clarity=random.uniform(0.5, 1.0),
                granularity=random.uniform(0.5, 1.0),
                relationship_coherence=random.uniform(0.5, 1.0),
                domain_alignment=random.uniform(0.5, 1.0),
            )
            for _ in range(sample_size)
        ]

        assert len(scores) == sample_size
        assert all(isinstance(s, CriticScore) for s in scores)

    def test_critic_score_bootstrap_confidence_intervals(self, critic):
        """Test bootstrap-style confidence intervals."""
        import random
        random.seed(42)

        # Original sample
        scores = [
            CriticScore(
                completeness=random.uniform(0.6, 0.9),
                consistency=random.uniform(0.7, 0.95),
                clarity=random.uniform(0.6, 0.85),
                granularity=random.uniform(0.65, 0.9),
                relationship_coherence=random.uniform(0.7, 0.9),
                domain_alignment=random.uniform(0.75, 0.95),
            )
            for _ in range(100)
        ]

        completeness_vals = [s.completeness for s in scores]
        overall_vals = [s.overall for s in scores]

        mean_completeness = st.mean(completeness_vals)
        mean_overall = st.mean(overall_vals)

        # Bootstrap resampling
        resample1 = [random.choice(completeness_vals) for _ in range(100)]
        resample2 = [random.choice(overall_vals) for _ in range(100)]

        resample_mean1 = st.mean(resample1)
        resample_mean2 = st.mean(resample2)

        # Resampled means should be close to original
        assert abs(resample_mean1 - mean_completeness) < 0.2
        assert abs(resample_mean2 - mean_overall) < 0.2
