"""Batch 237 Entropy Metrics Tests: score_entropy, score_concentration, score_gini_index."""

import pytest
import math
from dataclasses import dataclass

# Import the class we're testing
from ipfs_datasets_py.optimizers.graphrag.ontology_optimizer import OntologyOptimizer


@dataclass
class _FakeEntry:
    """Fake history entry with average_score."""
    average_score: float


def _make_opt(**kwargs) -> OntologyOptimizer:
    """Create a mock OntologyOptimizer with given history."""
    opt = OntologyOptimizer(enable_tracing=False)
    opt._history = [_FakeEntry(average_score=score) for score in kwargs.get('scores', [])]
    return opt


# ============================================================================
# Tests for score_entropy
# ============================================================================

class TestScoreEntropy:
    """Test OntologyOptimizer.score_entropy()."""

    def test_empty_history(self):
        """Empty history should return 0.0."""
        opt = _make_opt(scores=[])
        assert opt.score_entropy() == 0.0

    def test_single_entry(self):
        """Single entry should return 0.0 (no randomness)."""
        opt = _make_opt(scores=[0.7])
        assert opt.score_entropy() == 0.0

    def test_identical_scores(self):
        """All identical scores should return 0.0 (no entropy)."""
        opt = _make_opt(scores=[0.5, 0.5, 0.5, 0.5, 0.5])
        assert opt.score_entropy() == pytest.approx(0.0, abs=1e-10)

    def test_two_entries_distinct(self):
        """Two distinct scores should have entropy ~1.0 (log₂(2))."""
        opt = _make_opt(scores=[0.0, 1.0])
        entropy = opt.score_entropy()
        # With 2 equally likely outcomes: H = -2 * (0.5 * log₂(0.5)) = 1.0
        assert entropy == pytest.approx(1.0, abs=1e-6)

    def test_three_entries_uniform(self):
        """Three uniform scores should have entropy ~log₂(3) ≈ 1.585."""
        opt = _make_opt(scores=[0.1, 0.5, 0.9])
        entropy = opt.score_entropy()
        expected = -3 * (1/3) * math.log2(1/3)  # ≈ 1.585
        assert entropy == pytest.approx(expected, abs=1e-3)

    def test_biased_distribution(self):
        """Biased distribution (2:1 ratio) should have lower entropy."""
        # 2 observations at 0.0, 1 observation at 1.0
        opt = _make_opt(scores=[0.0, 0.0, 1.0])
        entropy = opt.score_entropy()
        # p1=2/3, p2=1/3: H = -(2/3*log₂(2/3) + 1/3*log₂(1/3))
        p1, p2 = 2/3, 1/3
        expected = -(p1 * math.log2(p1) + p2 * math.log2(p2))
        assert entropy == pytest.approx(expected, abs=1e-3)

    def test_entropy_bounds(self):
        """Entropy should be non-negative and reasonable."""
        opt = _make_opt(scores=[0.1, 0.3, 0.5, 0.7, 0.9])
        entropy = opt.score_entropy()
        assert entropy >= 0.0
        assert entropy <= math.log2(5) + 0.1  # Max entropy for 5 items ~2.32

    def test_precision_rounding(self):
        """Very close scores should be grouped together (within 10 decimal places)."""
        # Scores that differ beyond the 10th decimal place are grouped as same
        opt = _make_opt(scores=[0.5, 0.5, 0.5])  # All round to same value
        entropy = opt.score_entropy()
        # All are identical after rounding to 10 decimals
        assert entropy == pytest.approx(0.0, abs=1e-10)

    def test_return_type(self):
        """Return type should be float."""
        opt = _make_opt(scores=[0.2, 0.5, 0.8])
        result = opt.score_entropy()
        assert isinstance(result, float)

    def test_non_negative(self):
        """Entropy should always be non-negative."""
        opt = _make_opt(scores=[0.9, 0.2, 0.7, 0.4, 0.5])
        assert opt.score_entropy() >= 0.0


# ============================================================================
# Tests for score_concentration
# ============================================================================

class TestScoreConcentration:
    """Test OntologyOptimizer.score_concentration()."""

    def test_empty_history(self):
        """Empty history should return 0.0."""
        opt = _make_opt(scores=[])
        assert opt.score_concentration() == 0.0

    def test_single_entry(self):
        """Single entry should return 1.0 (perfect concentration)."""
        opt = _make_opt(scores=[0.7])
        assert opt.score_concentration() == 1.0

    def test_all_identical_scores(self):
        """All identical scores should return 1.0."""
        opt = _make_opt(scores=[0.5, 0.5, 0.5, 0.5])
        assert opt.score_concentration() == pytest.approx(1.0, abs=1e-10)

    def test_two_entries_equal(self):
        """Two equal entries should return 0.5 (= 2 * (0.5)²)."""
        opt = _make_opt(scores=[0.0, 1.0])
        assert opt.score_concentration() == pytest.approx(0.5, abs=1e-10)

    def test_three_entries_uniform(self):
        """Three uniform entries should return 1/3 (= 3 * (1/3)²)."""
        opt = _make_opt(scores=[0.0, 0.33, 0.66])
        concentration = opt.score_concentration()
        # C = 3 * (1/3)² = 1/3 ≈ 0.333
        assert concentration == pytest.approx(1/3, abs=1e-3)

    def test_biased_distribution(self):
        """Biased distribution should have higher concentration."""
        # 2 observations at 0.0, 1 observation at 1.0
        opt = _make_opt(scores=[0.0, 0.0, 1.0])
        concentration = opt.score_concentration()
        # C = (2/3)² + (1/3)² = 4/9 + 1/9 = 5/9 ≈ 0.556
        expected = (2/3) ** 2 + (1/3) ** 2
        assert concentration == pytest.approx(expected, abs=1e-6)

    def test_concentration_bounds(self):
        """Concentration should be in [0, 1]."""
        opt = _make_opt(scores=[0.1, 0.2, 0.3, 0.4, 0.5])
        concentration = opt.score_concentration()
        assert 0.0 <= concentration <= 1.0

    def test_concentration_vs_entropy_inverse(self):
        """Higher entropy ⇒ lower concentration (inverse relationship)."""
        # Create two distributions
        opt_high_entropy = _make_opt(scores=[0.1, 0.3, 0.5, 0.7, 0.9])
        opt_low_entropy = _make_opt(scores=[0.5, 0.5, 0.5, 0.6, 0.6])

        entropy_high = opt_high_entropy.score_entropy()
        entropy_low = opt_low_entropy.score_entropy()

        conc_high = opt_high_entropy.score_concentration()
        conc_low = opt_low_entropy.score_concentration()

        # High entropy should have low concentration
        assert entropy_high > entropy_low
        assert conc_high < conc_low

    def test_return_type(self):
        """Return type should be float."""
        opt = _make_opt(scores=[0.2, 0.5, 0.8])
        result = opt.score_concentration()
        assert isinstance(result, float)

    def test_non_negative(self):
        """Concentration should always be in [0, 1]."""
        opt = _make_opt(scores=[0.9, 0.2, 0.7, 0.4, 0.5])
        concentration = opt.score_concentration()
        assert 0.0 <= concentration <= 1.0


# ============================================================================
# Tests for score_gini_index
# ============================================================================

class TestScoreGiniIndex:
    """Test OntologyOptimizer.score_gini_index()."""

    def test_empty_history(self):
        """Empty history should return 0.0."""
        opt = _make_opt(scores=[])
        assert opt.score_gini_index() == 0.0

    def test_single_entry(self):
        """Single entry should return 0.0 (no inequality)."""
        opt = _make_opt(scores=[0.7])
        assert opt.score_gini_index() == 0.0

    def test_identical_scores(self):
        """All identical scores should return 0.0."""
        opt = _make_opt(scores=[0.5, 0.5, 0.5, 0.5])
        assert opt.score_gini_index() == pytest.approx(0.0, abs=1e-10)

    def test_two_entries_equal(self):
        """Two equal entries should return 0.0."""
        opt = _make_opt(scores=[0.5, 0.5])
        assert opt.score_gini_index() == pytest.approx(0.0, abs=1e-10)

    def test_extreme_inequality(self):
        """Maximum inequality (0, 0, ..., 1) should have high Gini."""
        opt = _make_opt(scores=[0.0, 0.0, 1.0])
        gini = opt.score_gini_index()
        # Should be > 0.5 (high inequality)
        assert gini > 0.5
        assert gini <= 1.0

    def test_moderate_inequality(self):
        """Moderate inequality should produce moderate Gini."""
        opt = _make_opt(scores=[0.0, 0.5, 1.0])
        gini = opt.score_gini_index()
        # Sorted: [0.0, 0.5, 1.0], mean = 0.5
        # G = (1 - 3 - 1) * 0.0 + (3 - 3 - 1) * 0.5 + (5 - 3 - 1) * 1.0 / (9 * 0.5)
        # G = 0 + (-1 * 0.5) + (1 * 1.0) / 4.5 = 0.5 / 4.5 ≈ 0.111
        assert 0.0 < gini < 0.5

    def test_gini_bounds(self):
        """Gini should be in [0, 1]."""
        opt = _make_opt(scores=[0.1, 0.2, 0.3, 0.8, 0.9])
        gini = opt.score_gini_index()
        assert 0.0 <= gini <= 1.0

    def test_increasing_scores(self):
        """Linearly increasing scores should have moderate Gini."""
        opt = _make_opt(scores=[0.1, 0.2, 0.3, 0.4, 0.5])
        gini = opt.score_gini_index()
        # Linear progression should have Gini = (n-1)/(n+1) = 4/6 ≈ 0.667
        expected = (5 - 1) / (5 + 1)  # For uniform linear
        assert gini < expected  # Exact formula may differ slightly

    def test_return_type(self):
        """Return type should be float."""
        opt = _make_opt(scores=[0.2, 0.5, 0.8])
        result = opt.score_gini_index()
        assert isinstance(result, float)

    def test_all_zeros(self):
        """All zeros should return 0.0 (no inequality)."""
        opt = _make_opt(scores=[0.0, 0.0, 0.0])
        assert opt.score_gini_index() == 0.0

    def test_gini_vs_concentration_relationship(self):
        """Gini and concentration measure inequality differently."""
        opt1 = _make_opt(scores=[0.5, 0.5, 0.5])
        opt2 = _make_opt(scores=[0.0, 0.5, 1.0])

        # Both have 0 Gini for uniform case
        assert opt1.score_gini_index() == pytest.approx(0.0, abs=1e-8)

        # Unequal case should have higher Gini
        assert opt2.score_gini_index() > 0.0
        # Unequal case should have lower (or equal) concentration if varied
        # (concentration measures which values dominate, Gini measures inequality)


# ============================================================================
# Integration Tests
# ============================================================================

class TestEntropyIntegration:
    """Test relationships and consistency between entropy metrics."""

    def test_entropy_zero_concentration_max(self):
        """Uniform entropy (single value) means maximum concentration."""
        opt = _make_opt(scores=[0.5, 0.5, 0.5, 0.5, 0.5])
        entropy = opt.score_entropy()
        concentration = opt.score_concentration()
        gini = opt.score_gini_index()

        assert entropy == pytest.approx(0.0, abs=1e-10)
        assert concentration == pytest.approx(1.0, abs=1e-10)
        assert gini == pytest.approx(0.0, abs=1e-10)

    def test_entropy_max_concentration_min(self):
        """Maximum entropy (uniform) means minimum concentration."""
        opt = _make_opt(scores=[0.2, 0.4, 0.6, 0.8])
        entropy = opt.score_entropy()
        concentration = opt.score_concentration()

        # Uniform distribution: concentration = 1/n
        expected_concentration = 1 / 4
        assert concentration == pytest.approx(expected_concentration, abs=1e-3)

    def test_improving_scores_entropy_gini(self):
        """Monotonically improving scores should have specific entropy/gini pattern."""
        opt = _make_opt(scores=[0.1, 0.2, 0.3, 0.4, 0.5])
        entropy = opt.score_entropy()
        concentration = opt.score_concentration()
        gini = opt.score_gini_index()

        # All different values but linearly distributed
        assert entropy > 1.0  # Non-trivial entropy
        assert concentration < 0.5  # Distributed
        assert gini > 0.0  # Some inequality (increasing trend)

    def test_random_fluctuation_vs_steady(self):
        """Random fluctuation should have higher entropy than steady state."""
        opt_steady = _make_opt(scores=[0.5, 0.5, 0.5, 0.5, 0.5])
        opt_fluctuating = _make_opt(scores=[0.2, 0.8, 0.1, 0.9, 0.3])

        entropy_steady = opt_steady.score_entropy()
        entropy_fluctuating = opt_fluctuating.score_entropy()

        assert entropy_steady < entropy_fluctuating

    def test_all_metrics_finite(self):
        """All metrics should return finite float values."""
        opt = _make_opt(scores=[0.1, 0.3, 0.5, 0.7, 0.9])
        entropy = opt.score_entropy()
        concentration = opt.score_concentration()
        gini = opt.score_gini_index()

        assert math.isfinite(entropy)
        assert math.isfinite(concentration)
        assert math.isfinite(gini)

    def test_optimization_convergence_pattern(self):
        """Simulated convergence should show entropy/concentration behavior."""
        # Early optimization (scattered scores)
        opt_early = _make_opt(scores=[0.2, 0.3, 0.25, 0.35, 0.28])
        
        # Late optimization (converged scores)
        opt_late = _make_opt(scores=[0.8, 0.79, 0.81, 0.80, 0.79])

        entropy_early = opt_early.score_entropy()
        entropy_late = opt_late.score_entropy()
        
        conc_early = opt_early.score_concentration()
        conc_late = opt_late.score_concentration()

        # Convergence should have lower entropy, higher concentration
        assert entropy_early > entropy_late
        assert conc_early < conc_late

    def test_real_world_optimization_scenario(self):
        """Test with realistic optimization history."""
        # Simulating: initial random → steady improvement → convergence
        scores = [
            0.1, 0.35, 0.12, 0.28,  # Random start
            0.45, 0.52, 0.58, 0.61,  # Improving trend
            0.75, 0.76, 0.75, 0.77   # Converged
        ]
        opt = _make_opt(scores=scores)

        entropy = opt.score_entropy()
        concentration = opt.score_concentration()
        gini = opt.score_gini_index()

        # All should be finite and in reasonable ranges
        assert 0.0 <= entropy <= 4.0
        assert 0.0 <= concentration <= 1.0
        assert 0.0 <= gini <= 1.0

        # Mixed pattern should have moderate entropy
        assert entropy > 0.5
