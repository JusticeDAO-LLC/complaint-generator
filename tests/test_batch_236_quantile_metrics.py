"""Batch 236 Quantile Metrics Tests: score_median, score_percentile, score_iqr."""

import pytest
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
# Tests for score_median
# ============================================================================

class TestScoreMedian:
    """Test OntologyOptimizer.score_median()."""

    def test_empty_history(self):
        """Empty history should return 0.0."""
        opt = _make_opt(scores=[])
        assert opt.score_median() == 0.0

    def test_single_entry(self):
        """Single entry should return that value."""
        opt = _make_opt(scores=[0.7])
        assert opt.score_median() == 0.7

    def test_two_entries(self):
        """Two entries should return average."""
        opt = _make_opt(scores=[0.2, 0.8])
        assert opt.score_median() == pytest.approx(0.5)

    def test_odd_length(self):
        """Odd-length list should return middle element."""
        opt = _make_opt(scores=[0.1, 0.3, 0.5, 0.7, 0.9])
        assert opt.score_median() == 0.5

    def test_even_length(self):
        """Even-length list should return average of two middle elements."""
        opt = _make_opt(scores=[0.1, 0.2, 0.3, 0.4])
        # Sorted: [0.1, 0.2, 0.3, 0.4], median = (0.2 + 0.3) / 2 = 0.25
        assert opt.score_median() == pytest.approx(0.25)

    def test_unsorted_input(self):
        """Should handle unsorted input correctly."""
        opt = _make_opt(scores=[0.9, 0.1, 0.5])
        # Sorted: [0.1, 0.5, 0.9], median = 0.5
        assert opt.score_median() == 0.5

    def test_duplicate_values(self):
        """Should handle duplicate values."""
        opt = _make_opt(scores=[0.5, 0.5, 0.5, 0.1, 0.9])
        # Sorted: [0.1, 0.5, 0.5, 0.5, 0.9], median = 0.5
        assert opt.score_median() == 0.5

    def test_return_type(self):
        """Return type should be float."""
        opt = _make_opt(scores=[0.1, 0.5, 0.9])
        result = opt.score_median()
        assert isinstance(result, float)


# ============================================================================
# Tests for score_percentile
# ============================================================================

class TestScorePercentile:
    """Test OntologyOptimizer.score_percentile(p)."""

    def test_empty_history(self):
        """Empty history should raise ValueError."""
        opt = _make_opt(scores=[])
        with pytest.raises(ValueError, match="requires at least one history entry"):
            opt.score_percentile(50.0)

    def test_single_entry(self):
        """Single entry should return that value for any p in (0, 100]."""
        opt = _make_opt(scores=[0.5])
        assert opt.score_percentile(50.0) == 0.5
        assert opt.score_percentile(100.0) == 0.5

    def test_percentile_100(self):
        """100th percentile should return maximum."""
        opt = _make_opt(scores=[0.1, 0.2, 0.3, 0.4, 0.5])
        assert opt.score_percentile(100.0) == pytest.approx(0.5)

    def test_percentile_50(self):
        """50th percentile should return median."""
        opt = _make_opt(scores=[0.1, 0.2, 0.3, 0.4, 0.5])
        assert opt.score_percentile(50.0) == pytest.approx(0.3)

    def test_percentile_25(self):
        """25th percentile (Q1)."""
        opt = _make_opt(scores=[0.0, 0.25, 0.5, 0.75, 1.0])
        # Linear interpolation at 25th percentile
        result = opt.score_percentile(25.0)
        assert result == pytest.approx(0.25)

    def test_percentile_75(self):
        """75th percentile (Q3)."""
        opt = _make_opt(scores=[0.0, 0.25, 0.5, 0.75, 1.0])
        result = opt.score_percentile(75.0)
        assert result == pytest.approx(0.75)

    def test_percentile_zero_invalid(self):
        """0th percentile (p=0) should raise ValueError (p must be in (0, 100])."""
        opt = _make_opt(scores=[0.1, 0.5, 0.9])
        with pytest.raises(ValueError, match="p must be in \\(0, 100\\]"):
            opt.score_percentile(0.0)

    def test_percentile_negative_invalid(self):
        """Negative percentile should raise ValueError."""
        opt = _make_opt(scores=[0.1, 0.5, 0.9])
        with pytest.raises(ValueError, match="p must be in \\(0, 100\\]"):
            opt.score_percentile(-10.0)

    def test_percentile_over_100_invalid(self):
        """Percentile > 100 should raise ValueError."""
        opt = _make_opt(scores=[0.1, 0.5, 0.9])
        with pytest.raises(ValueError, match="p must be in \\(0, 100\\]"):
            opt.score_percentile(150.0)

    def test_percentile_interpolation(self):
        """Test linear interpolation between points."""
        opt = _make_opt(scores=[0.0, 1.0])
        # 50th percentile between 0.0 and 1.0 should be 0.5
        assert opt.score_percentile(50.0) == pytest.approx(0.5)

    def test_return_type(self):
        """Return type should be float."""
        opt = _make_opt(scores=[0.1, 0.5, 0.9])
        result = opt.score_percentile(50.0)
        assert isinstance(result, float)


# ============================================================================
# Tests for score_iqr
# ============================================================================

class TestScoreIQR:
    """Test OntologyOptimizer.score_iqr()."""

    def test_empty_history(self):
        """Empty history should return 0.0."""
        opt = _make_opt(scores=[])
        assert opt.score_iqr() == 0.0

    def test_single_entry(self):
        """Single entry should return 0.0."""
        opt = _make_opt(scores=[0.5])
        assert opt.score_iqr() == 0.0

    def test_two_entries(self):
        """Two entries should return 0.0 (fewer than 4)."""
        opt = _make_opt(scores=[0.2, 0.8])
        assert opt.score_iqr() == 0.0

    def test_three_entries(self):
        """Three entries should return 0.0 (fewer than 4)."""
        opt = _make_opt(scores=[0.1, 0.5, 0.9])
        assert opt.score_iqr() == 0.0

    def test_four_entries_uniform(self):
        """Four uniform entries should have 0 IQR."""
        opt = _make_opt(scores=[0.5, 0.5, 0.5, 0.5])
        assert opt.score_iqr() == pytest.approx(0.0)

    def test_eight_entries(self):
        """Eight entries uniformly distributed."""
        opt = _make_opt(scores=[0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875])
        # Q1 ≈ 0.25/2, Q3 ≈ 0.75 - 0.25/2 = 0.625
        # IQR ≈ 0.375 approximately
        result = opt.score_iqr()
        assert result > 0.0
        assert result < 1.0

    def test_ten_entries_range(self):
        """Ten entries: 0.0 to 0.9."""
        opt = _make_opt(scores=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
        # Sorted same. Q1 at 25% ≈ 0.225, Q3 at 75% ≈ 0.675
        # IQR ≈ 0.45
        result = opt.score_iqr()
        assert result > 0.3 and result < 0.55

    def test_return_type(self):
        """Return type should be float."""
        opt = _make_opt(scores=[0.1, 0.2, 0.3, 0.4, 0.5])
        result = opt.score_iqr()
        assert isinstance(result, float)

    def test_non_negative(self):
        """IQR should always be non-negative."""
        opt = _make_opt(scores=[0.9, 0.2, 0.7, 0.4, 0.5])
        assert opt.score_iqr() >= 0.0

    def test_iqr_property(self):
        """IQR should be symmetric for symmetric distributions."""
        opt = _make_opt(scores=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
        iqr = opt.score_iqr()
        q1 = opt.score_percentile(25.0)
        q3 = opt.score_percentile(75.0)
        assert iqr == pytest.approx(q3 - q1, abs=1e-4)


# ============================================================================
# Integration Tests
# ============================================================================

class TestQuantileIntegration:
    """Test relationships and consistency between quantile metrics."""

    def test_median_equals_p50(self):
        """Median should equal 50th percentile."""
        opt = _make_opt(scores=[0.1, 0.3, 0.5, 0.7, 0.9])
        median = opt.score_median()
        p50 = opt.score_percentile(50.0)
        assert median == pytest.approx(p50)

    def test_percentile_ordering(self):
        """Lower percentiles should be less than or equal to higher ones."""
        opt = _make_opt(scores=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
        p25 = opt.score_percentile(25.0)
        p50 = opt.score_percentile(50.0)
        p75 = opt.score_percentile(75.0)
        assert p25 <= p50 <= p75

    def test_iqr_uses_q1_q3(self):
        """IQR calculation should use Q1 and Q3."""
        opt = _make_opt(scores=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
        iqr = opt.score_iqr()
        q1 = opt.score_percentile(25.0)
        q3 = opt.score_percentile(75.0)
        expected_iqr = q3 - q1
        assert iqr == pytest.approx(expected_iqr, abs=1e-4)

    def test_all_metrics_on_real_pattern(self):
        """Test all three metrics on a realistic improving score pattern."""
        # Simulating improving scores over time (fitness optimization)
        scores = [0.2, 0.25, 0.28, 0.3, 0.35, 0.38, 0.4, 0.42, 0.45, 0.5]
        opt = _make_opt(scores=scores)
        
        median = opt.score_median()
        iqr = opt.score_iqr()
        p95 = opt.score_percentile(95.0)
        
        # Median should be in the middle of the range
        assert 0.2 < median < 0.5
        # IQR should be positive but less than full range
        assert 0.0 < iqr < 0.3
        # 95th percentile should be near the top
        assert p95 > median
        assert p95 <= 0.5
