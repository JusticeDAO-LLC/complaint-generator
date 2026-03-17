"""Tests for benchmark utilities module.

Tests cover:
- Delta metrics computation
- Formatting (inline, report, table)
- Aggregation of multiple results
- Stateful reporter functionality
- Edge cases and error handling
"""

import pytest
from ipfs_datasets_py.optimizers.benchmark_utils import (
    DeltaMetrics,
    compute_relative_delta,
    compute_benchmark_metrics,
    format_delta_report,
    format_delta_inline,
    aggregate_deltas,
    format_benchmark_table,
    BenchmarkReporter,
)


class TestComputeRelativeDelta:
    """Test delta computation core functionality."""

    def test_compute_delta_basic(self):
        """Test basic delta computation."""
        metrics = compute_relative_delta(1000, 750)
        assert metrics.baseline_value == 1000
        assert metrics.optimized_value == 750
        assert metrics.absolute_delta == 250
        assert pytest.approx(metrics.percent_improvement, 0.01) == 25.0
        assert pytest.approx(metrics.speedup_factor, 0.01) == 1.33
        assert metrics.is_improvement is True

    def test_compute_delta_no_improvement(self):
        """Test when optimized is slower."""
        metrics = compute_relative_delta(1000, 1200)
        assert metrics.absolute_delta == -200
        assert metrics.percent_improvement < 0
        assert metrics.speedup_factor < 1.0
        assert metrics.is_improvement is False

    def test_compute_delta_equal_values(self):
        """Test when values are equal."""
        metrics = compute_relative_delta(500, 500)
        assert metrics.absolute_delta == 0
        assert metrics.percent_improvement == 0
        assert metrics.speedup_factor == 1.0
        assert metrics.is_improvement is False

    def test_compute_delta_half_optimized(self):
        """Test 50% improvement (2x speedup)."""
        metrics = compute_relative_delta(1000, 500)
        assert pytest.approx(metrics.percent_improvement, 0.01) == 50.0
        assert pytest.approx(metrics.speedup_factor, 0.01) == 2.0

    def test_compute_delta_zero_baseline_raises(self):
        """Test that zero baseline raises ValueError."""
        with pytest.raises(ValueError):
            compute_relative_delta(0, 500)

    def test_compute_delta_negative_baseline_raises(self):
        """Test that negative baseline raises ValueError."""
        with pytest.raises(ValueError):
            compute_relative_delta(-100, 500)

    def test_compute_delta_negative_optimized_raises(self):
        """Test that negative optimized raises ValueError."""
        with pytest.raises(ValueError):
            compute_relative_delta(1000, -500)

    def test_compute_delta_small_values(self):
        """Test with very small values."""
        metrics = compute_relative_delta(0.1, 0.075)
        assert pytest.approx(metrics.percent_improvement, 0.01) == 25.0

    def test_compute_delta_large_values(self):
        """Test with very large values."""
        metrics = compute_relative_delta(1000000, 750000)
        assert pytest.approx(metrics.percent_improvement, 0.01) == 25.0


class TestComputeBenchmarkMetrics:
    """Test legacy dict-based metrics computation."""

    def test_compute_metrics_returns_dict(self):
        """Test that dict format is returned."""
        metrics = compute_benchmark_metrics(1000, 750)
        assert isinstance(metrics, dict)
        assert set(metrics.keys()) == {'baseline', 'optimized', 'delta', 'percent_improvement', 'speedup'}

    def test_compute_metrics_values(self):
        """Test dict values are correct."""
        metrics = compute_benchmark_metrics(1000, 750)
        assert metrics['baseline'] == 1000
        assert metrics['optimized'] == 750
        assert metrics['delta'] == 250
        assert pytest.approx(metrics['percent_improvement'], 0.01) == 25.0
        assert pytest.approx(metrics['speedup'], 0.01) == 1.33


class TestFormatDeltaReport:
    """Test multi-line report formatting."""

    def test_format_report_basic(self):
        """Test basic report format."""
        metrics = compute_relative_delta(1000, 750)
        report = format_delta_report(metrics)
        
        assert "Baseline:" in report
        assert "1000.0" in report
        assert "Optimized:" in report
        assert "750.0" in report
        assert "Improvement:" in report
        assert "250.0" in report
        assert "25.0%" in report
        assert "Speedup:" in report
        assert "1.33x" in report

    def test_format_report_no_improvement_warning(self):
        """Test warning for regression."""
        metrics = compute_relative_delta(1000, 1200)
        report = format_delta_report(metrics)
        assert "⚠️" in report or "slower" in report

    def test_format_report_custom_unit(self):
        """Test custom unit label."""
        metrics = compute_relative_delta(1000, 750)
        report = format_delta_report(metrics, unit="ms")
        assert "ms" in report

    def test_format_report_custom_precision(self):
        """Test custom decimal precision."""
        metrics = compute_relative_delta(1000, 667)
        report = format_delta_report(metrics, precision=2)
        assert "33.3%" in report or "33.30%" in report


class TestFormatDeltaInline:
    """Test single-line inline formatting."""

    def test_format_inline_improvement(self):
        """Test formatting for improvement case."""
        metrics = compute_relative_delta(1000, 750)
        inline = format_delta_inline(metrics)
        assert "-25.0%" in inline
        assert "speedup" in inline
        assert "1.33x" in inline

    def test_format_inline_regression(self):
        """Test formatting for regression case."""
        metrics = compute_relative_delta(1000, 1200)
        inline = format_delta_inline(metrics)
        assert "+" in inline  # Shows positive increase (bad)
        assert "slower" in inline

    def test_format_inline_precision(self):
        """Test custom precision in inline format."""
        metrics = compute_relative_delta(1000, 667)
        inline = format_delta_inline(metrics, precision=2)
        assert "33" in inline  # Should show value to specified precision


class TestAggregatDeltas:
    """Test aggregation of multiple results."""

    def test_aggregate_single_result(self):
        """Test aggregation of single result."""
        results = [(1000, 750)]
        agg = aggregate_deltas(results)
        
        assert agg['count'] == 1
        assert pytest.approx(agg['mean_percent_improvement'], 0.01) == 25.0

    def test_aggregate_multiple_results(self):
        """Test aggregation of multiple results."""
        results = [
            (1000, 750),  # 25% improvement
            (400, 260),   # 35% improvement
            (1400, 920),  # 34.3% improvement
        ]
        agg = aggregate_deltas(results)
        
        assert agg['count'] == 3
        assert 30 < agg['mean_percent_improvement'] < 35  # In range
        assert agg['min_improvement'] < agg['max_improvement']

    def test_aggregate_empty_raises(self):
        """Test that empty list raises ValueError."""
        with pytest.raises(ValueError):
            aggregate_deltas([])

    def test_aggregate_median_computation(self):
        """Test median is computed correctly."""
        results = [
            (100, 90),    # 10%
            (100, 75),    # 25%
            (100, 50),    # 50%
        ]
        agg = aggregate_deltas(results)
        
        assert agg['median_percent_improvement'] == 25.0


class TestFormatBenchmarkTable:
    """Test markdown table formatting."""

    def test_format_table_basic(self):
        """Test basic table formatting."""
        results = [
            {'name': 'test1', 'baseline': 1000, 'optimized': 750},
            {'name': 'test2', 'baseline': 400, 'optimized': 260},
        ]
        table = format_benchmark_table(results)
        
        assert "| Benchmark" in table
        assert "| Baseline" in table
        assert "| Optimized" in table
        assert "| Improvement" in table
        assert "| Speedup" in table
        assert "|---|---|---|---|---|" in table or "|-" in table
        assert "test1" in table
        assert "test2" in table

    def test_format_table_includes_values(self):
        """Test that values are included in table."""
        results = [
            {'name': 'test', 'baseline': 1000, 'optimized': 750},
        ]
        table = format_benchmark_table(results)
        
        assert "1000" in table
        assert "750" in table
        assert "25" in table  # 25% improvement

    def test_format_table_custom_unit(self):
        """Test custom unit in table."""
        results = [
            {'name': 'test', 'baseline': 1000, 'optimized': 750},
        ]
        table = format_benchmark_table(results, unit="ms")
        
        assert "ms" in table

    def test_format_table_custom_column_names(self):
        """Test custom column names."""
        results = [
            {'bmark': 'test', 'base': 1000, 'opt': 750},
        ]
        table = format_benchmark_table(
            results,
            name_col='bmark',
            baseline_col='base',
            optimized_col='opt',
        )
        
        assert "test" in table

    def test_format_table_skips_invalid_rows(self):
        """Test that invalid rows are skipped."""
        results = [
            {'name': 'valid', 'baseline': 1000, 'optimized': 750},
            {'name': 'invalid', 'baseline': 0, 'optimized': 750},  # Invalid baseline
        ]
        table = format_benchmark_table(results)
        
        assert "valid" in table
        assert "invalid" not in table  # Skipped due to invalid baseline


class TestBenchmarkReporter:
    """Test stateful reporter class."""

    def test_reporter_add_single_result(self):
        """Test adding a single result."""
        reporter = BenchmarkReporter()
        reporter.add_result("test", 1000, 750)
        
        assert len(reporter.results) == 1
        assert reporter.results[0]['name'] == "test"

    def test_reporter_add_multiple_results(self):
        """Test adding multiple results."""
        reporter = BenchmarkReporter()
        reporter.add_result("test1", 1000, 750)
        reporter.add_result("test2", 400, 260)
        
        assert len(reporter.results) == 2

    def test_reporter_table(self):
        """Test table generation."""
        reporter = BenchmarkReporter()
        reporter.add_result("test", 1000, 750)
        
        table = reporter.table()
        assert "| Benchmark" in table
        assert "test" in table

    def test_reporter_summary(self):
        """Test summary generation."""
        reporter = BenchmarkReporter()
        reporter.add_result("test1", 1000, 750)
        reporter.add_result("test2", 400, 260)
        
        summary = reporter.summary()
        assert "Summary" in summary
        assert "Mean improvement" in summary
        assert "Min improvement" in summary
        assert "Max improvement" in summary

    def test_reporter_detailed_report(self):
        """Test full detailed report."""
        reporter = BenchmarkReporter()
        reporter.add_result("test1", 1000, 750)
        reporter.add_result("test2", 400, 260)
        
        report = reporter.detailed_report()
        assert "Benchmark" in report
        assert "Summary" in report
        assert "test1" in report
        assert "test2" in report

    def test_reporter_empty_summary(self):
        """Test summary with no results."""
        reporter = BenchmarkReporter()
        summary = reporter.summary()
        assert "No results" in summary

    def test_reporter_custom_unit(self):
        """Test custom unit in reporter."""
        reporter = BenchmarkReporter(unit="ms")
        reporter.add_result("test", 1000, 750)
        
        table = reporter.table()
        assert "ms" in table

    def test_reporter_custom_precision(self):
        """Test custom precision in reporter."""
        reporter = BenchmarkReporter(precision=2)
        reporter.add_result("test", 1000, 667)
        
        summary = reporter.summary()
        # Summary should reflect the precision setting


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_very_small_improvement(self):
        """Test with very small improvement."""
        metrics = compute_relative_delta(1000.0, 999.9)
        assert metrics.percent_improvement > 0
        assert metrics.percent_improvement < 0.1

    def test_very_large_improvement(self):
        """Test with very large improvement."""
        metrics = compute_relative_delta(1000.0, 1.0)
        assert metrics.percent_improvement > 99

    def test_float_precision(self):
        """Test that float precision is maintained."""
        metrics = compute_relative_delta(1000.123, 750.456)
        assert metrics.baseline_value == 1000.123
        assert metrics.optimized_value == 750.456

    def test_delta_metrics_type(self):
        """Test that DeltaMetrics is correctly structured."""
        metrics = compute_relative_delta(1000, 750)
        assert isinstance(metrics, DeltaMetrics)
        assert hasattr(metrics, 'baseline_value')
        assert hasattr(metrics, 'optimized_value')
        assert hasattr(metrics, 'absolute_delta')
        assert hasattr(metrics, 'percent_improvement')
        assert hasattr(metrics, 'speedup_factor')
        assert hasattr(metrics, 'is_improvement')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
