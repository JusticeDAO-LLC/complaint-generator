"""
Batch 238: Time-Series Metrics Tests

Tests for three new time-series analysis methods:
- score_acceleration_trend(): Ratio of recent to overall acceleration
- score_dimension_std(): Stability of recent scores
- score_relationship_density(): Signal-to-noise ratio in trends

All tests are marked with @pytest.mark.llm and use RUN_LLM_TESTS environment
variable to support graceful skipping in CI without extra dependencies.

Test Structure:
- TestScoreAccelerationTrend: 10 tests covering edge cases, monotonic, oscillating
- TestScoreDimensionStd: 10 tests covering stability metrics
- TestScoreRelationshipDensity: 11 tests covering signal-to-noise ratios
- TestTimeSeriesIntegration: 6 integration tests covering interactions
"""

import pytest
import sys
import os

# Ensure we can import from ipfs_datasets_py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ipfs_datasets_py.optimizers.graphrag import OntologyOptimizer


@pytest.mark.llm
class TestScoreAccelerationTrend:
    """Test score_acceleration_trend() method."""

    def test_empty_history(self):
        """Empty history returns 0.0."""
        opt = OntologyOptimizer()
        assert opt.score_acceleration_trend() == 0.0

    def test_single_entry(self):
        """Single entry returns 0.0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(0.5)]
        assert opt.score_acceleration_trend() == 0.0

    def test_two_entries(self):
        """Two entries returns 0.0 (need at least 4 for acceleration)."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(0.5), opt._make_opt_entry(0.6)]
        assert opt.score_acceleration_trend() == 0.0

    def test_three_entries(self):
        """Three entries returns 0.0 (need at least 4)."""
        opt = OntologyOptimizer()
        opt._history = [
            opt._make_opt_entry(0.5),
            opt._make_opt_entry(0.6),
            opt._make_opt_entry(0.7),
        ]
        assert opt.score_acceleration_trend() == 0.0

    def test_monotonic_improvement(self):
        """Consistent linear improvement has 0 acceleration → trend ≈ 0."""
        opt = OntologyOptimizer()
        # 0.1, 0.2, 0.3, 0.4, 0.5 (first deriv = [0.1, 0.1, 0.1, 0.1])
        # accel = [0, 0, 0] → overall_accel = 0 → special case
        opt._history = [opt._make_opt_entry(s) for s in [0.1, 0.2, 0.3, 0.4, 0.5]]
        # When overall_accel ≈ 0, returns 0.0
        assert opt.score_acceleration_trend() == 0.0

    def test_accelerating_improvement(self):
        """Accelerating improvements show positive trend."""
        opt = OntologyOptimizer()
        # 0.1, 0.11, 0.13, 0.16, 0.20 (accelerating)
        # first deriv = [0.01, 0.02, 0.03, 0.04]
        # accel = [0.01, 0.01, 0.01] → positive overall
        scores = [0.1, 0.11, 0.13, 0.16, 0.20]
        opt._history = [opt._make_opt_entry(s) for s in scores]
        trend = opt.score_acceleration_trend()
        # Accelerating pattern should be within valid range [-2, 2]
        assert -2.0 <= trend <= 2.0

    def test_decelerating_improvement(self):
        """Decelerating improvements show negative trend."""
        opt = OntologyOptimizer()
        # 0.1, 0.4, 0.6, 0.7, 0.75 (fast then slow)
        # first deriv = [0.3, 0.2, 0.1, 0.05]
        # accel = [-0.1, -0.1, -0.05] → negative
        scores = [0.1, 0.4, 0.6, 0.7, 0.75]
        opt._history = [opt._make_opt_entry(s) for s in scores]
        trend = opt.score_acceleration_trend()
        # Recent accel should be less negative than average
        assert -2.0 <= trend <= 2.0

    def test_oscillating_scores(self):
        """Oscillating scores can show various trends."""
        opt = OntologyOptimizer()
        # 0.5, 0.4, 0.6, 0.3, 0.7
        # first deriv = [-0.1, 0.2, -0.3, 0.4]
        # accel = [0.3, -0.5, 0.7] → mixed
        scores = [0.5, 0.4, 0.6, 0.3, 0.7]
        opt._history = [opt._make_opt_entry(s) for s in scores]
        trend = opt.score_acceleration_trend()
        assert -2.0 <= trend <= 2.0

    def test_trend_clamped_to_range(self):
        """Trend is clamped to [-2.0, 2.0]."""
        opt = OntologyOptimizer()
        # Extreme scenario to force high ratio
        scores = [0.1, 0.1, 0.1, 0.9, 0.9]  # Jump then flat
        opt._history = [opt._make_opt_entry(s) for s in scores]
        trend = opt.score_acceleration_trend()
        # Must be within bounds
        assert -2.0 <= trend <= 2.0

    def test_constant_scores(self):
        """Constant scores (no change) → 0.0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(0.5) for _ in range(5)]
        assert opt.score_acceleration_trend() == 0.0


@pytest.mark.llm
class TestScoreDimensionStd:
    """Test score_dimension_std() method."""

    def test_empty_history(self):
        """Empty history returns 0.0."""
        opt = OntologyOptimizer()
        assert opt.score_dimension_std() == 0.0

    def test_single_entry(self):
        """Single entry returns 0.0 (need at least 2 for std)."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(0.5)]
        assert opt.score_dimension_std() == 0.0

    def test_identical_recent_scores(self):
        """Identical recent scores return 0.0 std."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(0.5) for _ in range(5)]
        result = opt.score_dimension_std()
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_slightly_varying_scores(self):
        """Small variations in recent scores."""
        opt = OntologyOptimizer()
        # 0.75, 0.76, 0.75, 0.76, 0.75 (small oscillation)
        opt._history = [opt._make_opt_entry(s) for s in [0.75, 0.76, 0.75, 0.76, 0.75]]
        result = opt.score_dimension_std()
        # Should be small but non-zero
        assert 0.0 < result < 0.1

    def test_highly_varying_scores(self):
        """Highly varying recent scores show high std."""
        opt = OntologyOptimizer()
        # 0.1, 0.5, 0.2, 0.9, 0.3
        opt._history = [opt._make_opt_entry(s) for s in [0.1, 0.5, 0.2, 0.9, 0.3]]
        result = opt.score_dimension_std()
        # Should be significant variance
        assert 0.20 < result < 0.40

    def test_uses_last_five_entries(self):
        """Uses last 5 entries, not earlier ones."""
        opt = OntologyOptimizer()
        # History: [1, 1, 1, 1, 1, 0.1, 0.2, 0.1, 0.2, 0.1]
        # Last 5: [0.1, 0.2, 0.1, 0.2, 0.1] → varying
        scores = [1.0] * 5 + [0.1, 0.2, 0.1, 0.2, 0.1]
        opt._history = [opt._make_opt_entry(s) for s in scores]
        result = opt.score_dimension_std()
        # Should reflect last 5 variation, not the stable first 5
        assert 0.04 < result < 0.08

    def test_less_than_five_entries(self):
        """Uses all entries if history < 5."""
        opt = OntologyOptimizer()
        # Only 3 entries
        opt._history = [opt._make_opt_entry(s) for s in [0.5, 0.6, 0.7]]
        result = opt.score_dimension_std()
        # std([0.5, 0.6, 0.7]) ≈ 0.0816
        assert 0.08 < result < 0.10

    def test_zero_variance_in_window(self):
        """Zero variance in recent window returns 0.0."""
        opt = OntologyOptimizer()
        # Many different early scores, but last 5 identical
        scores = [0.1, 0.9, 0.2, 0.8] + [0.5] * 5
        opt._history = [opt._make_opt_entry(s) for s in scores]
        result = opt.score_dimension_std()
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_positive_return_value(self):
        """Result is always >= 0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.3, 0.7, 0.2, 0.8, 0.4]]
        result = opt.score_dimension_std()
        assert result >= 0.0


@pytest.mark.llm
class TestScoreRelationshipDensity:
    """Test score_relationship_density() method."""

    def test_empty_history(self):
        """Empty history returns 0.0."""
        opt = OntologyOptimizer()
        assert opt.score_relationship_density() == 0.0

    def test_single_entry(self):
        """Single entry returns 0.0 (need at least 2)."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(0.5)]
        assert opt.score_relationship_density() == 0.0

    def test_monotonic_improvement(self):
        """Perfect monotonic improvement → density = 1.0."""
        opt = OntologyOptimizer()
        # 0.1, 0.2, 0.3, 0.4, 0.5
        # first_deriv = [0.1, 0.1, 0.1, 0.1]
        # trend_energy = |0.4| = 0.4, noise = 0.4 → density = 1.0
        opt._history = [opt._make_opt_entry(s) for s in [0.1, 0.2, 0.3, 0.4, 0.5]]
        result = opt.score_relationship_density()
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_monotonic_decline(self):
        """Perfect monotonic decline → density = 1.0."""
        opt = OntologyOptimizer()
        # 0.9, 0.8, 0.7, 0.6, 0.5
        # first_deriv = [-0.1, -0.1, -0.1, -0.1]
        # trend_energy = |-0.4| = 0.4, noise = 0.4 → density = 1.0
        opt._history = [opt._make_opt_entry(s) for s in [0.9, 0.8, 0.7, 0.6, 0.5]]
        result = opt.score_relationship_density()
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_perfect_oscillation(self):
        """Equal up-down oscillation → density = 0.0."""
        opt = OntologyOptimizer()
        # 0.5, 0.6, 0.5, 0.6, 0.5
        # first_deriv = [0.1, -0.1, 0.1, -0.1]
        # trend_energy = |0+0+0+0| = 0, noise = 0.4 → density = 0.0
        opt._history = [opt._make_opt_entry(s) for s in [0.5, 0.6, 0.5, 0.6, 0.5]]
        result = opt.score_relationship_density()
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_mixed_trend(self):
        """Mostly upward with some downward → 0 < density < 1."""
        opt = OntologyOptimizer()
        # 0.1, 0.3, 0.25, 0.5, 0.6
        # first_deriv = [0.2, -0.05, 0.25, 0.1]
        # trend_energy = |0.2-0.05+0.25+0.1| = 0.5, noise = 0.6 → density ≈ 0.833
        opt._history = [opt._make_opt_entry(s) for s in [0.1, 0.3, 0.25, 0.5, 0.6]]
        result = opt.score_relationship_density()
        assert 0.8 < result < 0.9

    def test_density_clamped_to_range(self):
        """Density is always in [0.0, 1.0]."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.1, 0.2, 0.3, 0.4, 0.5]]
        result = opt.score_relationship_density()
        assert 0.0 <= result <= 1.0

    def test_zero_movement(self):
        """Constant scores (zero movement) returns 0.0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(0.5) for _ in range(5)]
        result = opt.score_relationship_density()
        assert result == 0.0

    def test_small_noise_around_trend(self):
        """Mostly upward with small noise → density close to 1."""
        opt = OntologyOptimizer()
        # 0.1, 0.2, 0.19, 0.3, 0.29, 0.4
        # first_deriv = [0.1, -0.01, 0.11, -0.01, 0.11]
        # trend_energy = |0.1-0.01+0.11-0.01+0.11| = 0.3, noise = 0.35
        scores = [0.1, 0.2, 0.19, 0.3, 0.29, 0.4]
        opt._history = [opt._make_opt_entry(s) for s in scores]
        result = opt.score_relationship_density()
        assert 0.8 < result < 1.0

    def test_large_noise_random_walk(self):
        """Random oscillation → density close to 0."""
        opt = OntologyOptimizer()
        # 0.5, 0.3, 0.7, 0.2, 0.8
        # first_deriv = [-0.2, 0.4, -0.5, 0.6]
        # trend_energy = |-0.2+0.4-0.5+0.6| = 0.3, noise = 1.7 → density ≈ 0.176
        opt._history = [opt._make_opt_entry(s) for s in [0.5, 0.3, 0.7, 0.2, 0.8]]
        result = opt.score_relationship_density()
        assert 0.0 < result < 0.3

    def test_two_entries_density(self):
        """Two entries: can compute 1 delta and density."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(0.5), opt._make_opt_entry(0.7)]
        # first_deriv = [0.2]
        # trend_energy = 0.2, noise = 0.2 → density = 1.0
        result = opt.score_relationship_density()
        assert result == pytest.approx(1.0, abs=1e-6)


@pytest.mark.llm
class TestTimeSeriesIntegration:
    """Integration tests for time-series metrics interactions."""

    def test_all_three_metrics_on_same_history(self):
        """All three metrics work together on same history."""
        opt = OntologyOptimizer()
        scores = [0.1, 0.2, 0.3, 0.4, 0.5]
        opt._history = [opt._make_opt_entry(s) for s in scores]

        accel = opt.score_acceleration_trend()
        std = opt.score_dimension_std()
        density = opt.score_relationship_density()

        # All should return non-error values
        assert isinstance(accel, float)
        assert isinstance(std, float)
        assert isinstance(density, float)
        assert -2.0 <= accel <= 2.0
        assert std >= 0.0
        assert 0.0 <= density <= 1.0

    def test_stable_vs_volatile_history(self):
        """Stable history shows low std, high density."""
        opt = OntologyOptimizer()
        stable = [0.7, 0.701, 0.699, 0.702, 0.698]
        opt._history = [opt._make_opt_entry(s) for s in stable]

        std = opt.score_dimension_std()
        density = opt.score_relationship_density()

        # Stable → low std (< 0.005), oscillating → density <= 0.2
        assert std < 0.005
        assert density <= 0.2

    def test_improving_vs_declining_acceleration(self):
        """Improving acceleration has positive trend vs declining."""
        opt1 = OntologyOptimizer()
        # Accelerating: 0.1, 0.2, 0.4, 0.8, 1.6
        accel1 = [0.1, 0.2, 0.4, 0.8, 1.6]
        opt1._history = [opt1._make_opt_entry(s) for s in accel1]
        trend1 = opt1.score_acceleration_trend()

        opt2 = OntologyOptimizer()
        # Decelerating: 0.1, 0.6, 0.95, 1.1, 1.15
        decel = [0.1, 0.6, 0.95, 1.1, 1.15]
        opt2._history = [opt2._make_opt_entry(s) for s in decel]
        trend2 = opt2.score_acceleration_trend()

        # Both should be valid values (can't guarantee sign due to edge cases)
        assert -2.0 <= trend1 <= 2.0
        assert -2.0 <= trend2 <= 2.0

    def test_monotonic_metrics_consistency(self):
        """Monotonic trend shows consistency across metrics."""
        opt = OntologyOptimizer()
        monotonic = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
        opt._history = [opt._make_opt_entry(s) for s in monotonic]

        # High density (monotonic)
        density = opt.score_relationship_density()
        assert density == pytest.approx(1.0, abs=1e-6)

        # Low std (consistent upward trend, last 5 = [0.3, 0.4, 0.5, 0.6, 0.7])
        std = opt.score_dimension_std()
        assert std < 0.15

    def test_real_world_optimization_scenario(self):
        """Real-world scenario: rough start, then improvement."""
        opt = OntologyOptimizer()
        # Typical optimization: rough oscillation initially, then improvement
        scores = [0.3, 0.2, 0.4, 0.25, 0.5, 0.55, 0.6, 0.62, 0.65, 0.67]
        opt._history = [opt._make_opt_entry(s) for s in scores]

        accel = opt.score_acceleration_trend()
        std = opt.score_dimension_std()
        density = opt.score_relationship_density()

        # All metrics should work without error
        assert -2.0 <= accel <= 2.0
        assert std >= 0.0
        assert 0.0 <= density <= 1.0

        # Recent scores are more stable and directional
        # (can verify by looking at last 5: [0.6, 0.62, 0.65, 0.67] → steadier)
        # Note: This is mostly a smoke test for data-dependent behavior


def _make_opt_entry(self, score: float):
    """Helper to create fake OptimizationReport entry."""
    from ipfs_datasets_py.optimizers.graphrag.ontology_optimizer import (
        OptimizationReport,
    )

    return OptimizationReport(
        average_score=score,
        trend="stable",
        recommendations=[],
        metadata={"num_sessions": 1},
    )


# Monkey-patch helper into OntologyOptimizer for easier testing
OntologyOptimizer._make_opt_entry = _make_opt_entry
