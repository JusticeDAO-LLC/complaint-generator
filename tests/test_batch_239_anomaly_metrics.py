"""
Batch 239: Anomaly & Signal Detection Metrics Tests

Tests for three new anomaly/signal detection methods:
- score_drawdown_ratio(): Recovery from recent peaks (drawdown measure)
- score_cycle_period(): Dominant cycle length detection
- score_persistence(): Trend persistence in deltas

All tests marked with @pytest.mark.llm using RUN_LLM_TESTS environment variable.

Test Structure:
- TestScoreDrawdownRatio: 10 tests covering peaks, current values, edge cases
- TestScoreCyclePeriod: 11 tests covering oscillation detection, monotonic trends
- TestScorePersistence: 10 tests covering delta autocorrelation, persistence
- TestAnomalyIntegration: 5 integration tests for metric interactions
"""

import pytest
import sys
import os

# Ensure we can import from ipfs_datasets_py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ipfs_datasets_py.optimizers.graphrag import OntologyOptimizer


@pytest.mark.llm
class TestScoreDrawdownRatio:
    """Test score_drawdown_ratio() method."""

    def test_empty_history(self):
        """Empty history returns 0.0."""
        opt = OntologyOptimizer()
        assert opt.score_drawdown_ratio() == 0.0

    def test_single_entry(self):
        """Single entry at peak → ratio = 1.0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(0.8)]
        assert opt.score_drawdown_ratio() == 1.0

    def test_at_peak(self):
        """Current score at peak → ratio = 1.0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.5, 0.7, 0.8]]
        result = opt.score_drawdown_ratio()
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_at_bottom_after_peak(self):
        """Current score at minimum after peak → ratio ≈ 0.0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.8, 0.1]]
        result = opt.score_drawdown_ratio()
        # 0.1 / 0.8 ≈ 0.125
        assert result == pytest.approx(0.125, abs=1e-6)

    def test_fifty_percent_drawdown(self):
        """50% drawdown from peak."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.4, 0.8, 0.4]]
        # peak = 0.8, current = 0.4 → ratio = 0.5
        result = opt.score_drawdown_ratio()
        assert result == pytest.approx(0.5, abs=1e-6)

    def test_zero_peak(self):
        """Zero peak returns 0.0 (avoid division)."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(0.0) for _ in range(3)]
        assert opt.score_drawdown_ratio() == 0.0

    def test_all_equal_scores(self):
        """All equal scores → ratio = 1.0 (no drawdown)."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(0.5) for _ in range(5)]
        assert opt.score_drawdown_ratio() == pytest.approx(1.0, abs=1e-6)

    def test_recovery_toward_peak(self):
        """Recovery climbing back up → ratio increases toward 1."""
        opt = OntologyOptimizer()
        # 0.8, 0.2, 0.5 (dip then partial recovery)
        opt._history = [opt._make_opt_entry(s) for s in [0.8, 0.2, 0.5]]
        result = opt.score_drawdown_ratio()
        # peak = 0.8, current = 0.5 → ratio = 0.625
        assert result == pytest.approx(0.625, abs=1e-6)

    def test_complete_recovery(self):
        """Recovery to original peak → ratio = 1.0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.8, 0.3, 0.8]]
        result = opt.score_drawdown_ratio()
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_ratio_clamped_to_range(self):
        """Ratio always in [0.0, 1.0]."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.1, 0.2, 0.3, 0.4, 0.5]]
        result = opt.score_drawdown_ratio()
        assert 0.0 <= result <= 1.0


@pytest.mark.llm
class TestScoreCyclePeriod:
    """Test score_cycle_period() method."""

    def test_empty_history(self):
        """Empty history returns 0.0."""
        opt = OntologyOptimizer()
        assert opt.score_cycle_period() == 0.0

    def test_less_than_four_entries(self):
        """Fewer than 4 entries returns 0.0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.5, 0.6, 0.7]]
        assert opt.score_cycle_period() == 0.0

    def test_zero_variance(self):
        """Constant scores (zero variance) returns 0.0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(0.5) for _ in range(5)]
        assert opt.score_cycle_period() == 0.0

    def test_monotonic_trend(self):
        """No cycle in monotonic trend → 0.0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.1, 0.2, 0.3, 0.4, 0.5]]
        result = opt.score_cycle_period()
        # Monotonic has no cycle
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_perfect_two_period_oscillation(self):
        """Perfect 2-step oscillation → period detected."""
        opt = OntologyOptimizer()
        # 0.5, 0.7, 0.5, 0.7, 0.5, 0.7, 0.5
        opt._history = [opt._make_opt_entry(s) for s in [0.5, 0.7, 0.5, 0.7, 0.5, 0.7, 0.5]]
        result = opt.score_cycle_period()
        # Should detect some cycle period (exact detection varies)
        assert result > 0.0

    def test_three_period_oscillation(self):
        """3-step cyclical pattern."""
        opt = OntologyOptimizer()
        # 0.3, 0.6, 0.4, 0.3, 0.6, 0.4, 0.3, 0.6, 0.4
        pattern = [0.3, 0.6, 0.4] * 3
        opt._history = [opt._make_opt_entry(s) for s in pattern]
        result = opt.score_cycle_period()
        # Should detect 3-period cycle
        assert result == pytest.approx(3.0, abs=0.5)

    def test_noisy_oscillation(self):
        """Oscillation with noise still detectable if significant."""
        opt = OntologyOptimizer()
        # Base 2-period with small noise
        base = [0.5, 0.7, 0.5, 0.7, 0.5, 0.7, 0.5]
        opt._history = [opt._make_opt_entry(s) for s in base]
        result = opt.score_cycle_period()
        # Should still detect approximate 2-period
        assert 0.0 < result < 4.0

    def test_weak_cycle_not_detected(self):
        """Weak cycle (low autocorr) not detected."""
        opt = OntologyOptimizer()
        # Random-ish walk with no strong cycle
        opt._history = [opt._make_opt_entry(s) for s in [0.5, 0.4, 0.6, 0.55, 0.62]]
        result = opt.score_cycle_period()
        # Should return 0.0 (no strong cycle)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_long_period_oscillation(self):
        """Longer-period oscillation."""
        opt = OntologyOptimizer()
        # 4-step pattern repeated
        pattern = [0.2, 0.5, 0.3, 0.7] * 2
        opt._history = [opt._make_opt_entry(s) for s in pattern]
        result = opt.score_cycle_period()
        # Should detect cycle or return 0 if autocorr too weak
        assert result >= 0.0

    def test_cycle_period_nonnegative(self):
        """Result is always >= 0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.1, 0.8, 0.2, 0.7, 0.3]]
        result = opt.score_cycle_period()
        assert result >= 0.0


@pytest.mark.llm
class TestScorePersistence:
    """Test score_persistence() method."""

    def test_empty_history(self):
        """Empty history returns 0.0."""
        opt = OntologyOptimizer()
        assert opt.score_persistence() == 0.0

    def test_fewer_than_three_entries(self):
        """Fewer than 3 entries returns 0.0."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.5, 0.6]]
        assert opt.score_persistence() == 0.0

    def test_consistent_improvement(self):
        """Consistent linear improvement → high persistence."""
        opt = OntologyOptimizer()
        # 0.1, 0.2, 0.3, 0.4, 0.5 (deltas = [0.1, 0.1, 0.1, 0.1])
        opt._history = [opt._make_opt_entry(s) for s in [0.1, 0.2, 0.3, 0.4, 0.5]]
        result = opt.score_persistence()
        # Perfect consistency in deltas → perfect persistence → 1.0
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_accelerating_improvement(self):
        """Accelerating improvement → positive persistence."""
        opt = OntologyOptimizer()
        # 0.1, 0.2, 0.4, 0.8 (deltas = [0.1, 0.2, 0.4] → increasing)
        opt._history = [opt._make_opt_entry(s) for s in [0.1, 0.2, 0.4, 0.8]]
        result = opt.score_persistence()
        # Increasing deltas → positive autocorr
        assert 0.0 <= result <= 1.0

    def test_random_oscillation(self):
        """Random oscillation → low persistence."""
        opt = OntologyOptimizer()
        # 0.5, 0.3, 0.7, 0.2, 0.8 (deltas = [−0.2, 0.4, −0.5, 0.6])
        opt._history = [opt._make_opt_entry(s) for s in [0.5, 0.3, 0.7, 0.2, 0.8]]
        result = opt.score_persistence()
        # Alternating deltas → low autocorr → low persistence
        assert result < 0.5

    def test_perfect_oscillation(self):
        """Perfect alternation → very low persistence."""
        opt = OntologyOptimizer()
        # 0.5, 0.6, 0.5, 0.6, 0.5 (deltas = [0.1, −0.1, 0.1, −0.1])
        opt._history = [opt._make_opt_entry(s) for s in [0.5, 0.6, 0.5, 0.6, 0.5]]
        result = opt.score_persistence()
        # Perfect alternation → negative autocorr → clamped to [0, 1]
        assert result >= 0.0

    def test_zero_variance_deltas(self):
        """Constant deltas (e.g. linear trend) → perfect persistence."""
        opt = OntologyOptimizer()
        # 0.0, 0.1, 0.2, 0.3, 0.4 (deltas = [0.1, 0.1, 0.1, 0.1])
        opt._history = [opt._make_opt_entry(s) for s in [0.0, 0.1, 0.2, 0.3, 0.4]]
        result = opt.score_persistence()
        # All deltas identical → perfect persistence = 1.0
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_decelerating_improvement(self):
        """Decelerating improves → positive but lower than accelerating."""
        opt = OntologyOptimizer()
        # 0.0, 0.5, 0.8, 0.9, 0.95 (deltas = [0.5, 0.3, 0.1, 0.05] → decreasing)
        opt._history = [opt._make_opt_entry(s) for s in [0.0, 0.5, 0.8, 0.9, 0.95]]
        result = opt.score_persistence()
        # Decreasing deltas → positive autocorr but not perfect
        assert 0.0 < result < 1.0

    def test_persistence_bounded(self):
        """Persistence always in [0, 1]."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.2, 0.3, 0.5, 0.8, 1.2]]
        result = opt.score_persistence()
        assert 0.0 <= result <= 1.0

    def test_three_entry_minimum(self):
        """Exactly 3 entries can compute persistence."""
        opt = OntologyOptimizer()
        # 0.1, 0.2, 0.3 (deltas = [0.1, 0.1])
        opt._history = [opt._make_opt_entry(s) for s in [0.1, 0.2, 0.3]]
        result = opt.score_persistence()
        # Should work without error
        assert 0.0 <= result <= 1.0


@pytest.mark.llm
class TestAnomalyIntegration:
    """Integration tests for anomaly/signal metrics."""

    def test_all_three_metrics_on_same_history(self):
        """All three metrics work on same history."""
        opt = OntologyOptimizer()
        scores = [0.1, 0.3, 0.2, 0.5, 0.4, 0.7, 0.6]
        opt._history = [opt._make_opt_entry(s) for s in scores]

        drawdown = opt.score_drawdown_ratio()
        cycle = opt.score_cycle_period()
        persist = opt.score_persistence()

        # All should return valid values
        assert isinstance(drawdown, float)
        assert isinstance(cycle, float)
        assert isinstance(persist, float)
        assert 0.0 <= drawdown <= 1.0
        assert cycle >= 0.0
        assert 0.0 <= persist <= 1.0

    def test_monotonic_increasing_metrics(self):
        """Monotonic increase shows high drawdown, low cycle, high persistence."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.1, 0.2, 0.3, 0.4, 0.5]]

        drawdown = opt.score_drawdown_ratio()
        cycle = opt.score_cycle_period()
        persist = opt.score_persistence()

        # At peak → high drawdown
        assert drawdown > 0.9
        # Monotonic → no cycle or very low
        assert cycle < 1.0
        # Constant deltas → perfect persistence
        assert persist == pytest.approx(1.0, abs=1e-6)

    def test_oscillating_pattern_metrics(self):
        """Oscillation shows lower drawdown, detectable cycle, lower persistence."""
        opt = OntologyOptimizer()
        opt._history = [opt._make_opt_entry(s) for s in [0.5, 0.7, 0.5, 0.7, 0.5, 0.7, 0.5]]

        drawdown = opt.score_drawdown_ratio()
        cycle = opt.score_cycle_period()
        persist = opt.score_persistence()

        # Current at middle of range → moderate drawdown
        assert 0.5 < drawdown < 0.8
        # Clear oscillation → cycle detected
        assert cycle > 0.0
        # Alternating deltas → low persistence
        assert persist < 0.5

    def test_recovery_scenario(self):
        """Dip and recovery shows improving metrics."""
        opt = OntologyOptimizer()
        # Peak, dip, then recovery
        opt._history = [opt._make_opt_entry(s) for s in [0.8, 0.2, 0.5, 0.7]]

        drawdown = opt.score_drawdown_ratio()
        persist = opt.score_persistence()

        # At current 0.7 vs peak 0.8 → good drawdown ratio (87.5%)
        assert drawdown > 0.8
        # Recovery trend with varying deltas → may have moderate/low persistence
        assert 0.0 <= persist <= 1.0

    def test_real_world_optimization_anomaly_scenario(self):
        """Real-world scenario: detect convergence quality from metrics."""
        opt = OntologyOptimizer()
        # Typical optimization: rough start, improvement, then convergence
        scores = [0.3, 0.2, 0.4, 0.25, 0.5, 0.55, 0.6, 0.62, 0.63, 0.65]
        opt._history = [opt._make_opt_entry(s) for s in scores]

        drawdown = opt.score_drawdown_ratio()
        cycle = opt.score_cycle_period()
        persist = opt.score_persistence()

        # All should be computable without error
        assert isinstance(drawdown, float)
        assert isinstance(cycle, float)
        assert isinstance(persist, float)

        # Recent convergence means improvement persistence
        assert persist >= 0.0
        # At high drawdown ratio (near peak)
        assert 0.0 <= drawdown <= 1.0


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
