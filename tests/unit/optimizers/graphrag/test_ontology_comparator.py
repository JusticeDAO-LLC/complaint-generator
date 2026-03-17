"""Comprehensive tests for OntologyComparator comparison and ranking methods."""

import pytest
from dataclasses import dataclass
from typing import Dict, Any, List
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from ipfs_datasets_py.optimizers.graphrag import OntologyComparator, STANDARD_DIMENSIONS


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


def create_ontology(name: str = "test") -> dict:
    """Helper to create mock ontology."""
    return {"name": name, "entities": [], "relationships": []}


class TestOntologyComparatorInitialization:
    """Test OntologyComparator initialization."""
    
    def test_default_initialization(self):
        """Test initialization with default dimensions."""
        comparator = OntologyComparator()
        assert comparator.DIMENSIONS == STANDARD_DIMENSIONS
    
    def test_custom_dimensions(self):
        """Test initialization with custom dimensions."""
        custom_dims = ("dim1", "dim2", "dim3")
        comparator = OntologyComparator(dimensions=custom_dims)
        assert comparator.DIMENSIONS == custom_dims


class TestRankingMethods:
    """Test ranking and sorting operations."""
    
    def test_rank_batch_single(self):
        """Test ranking single ontology."""
        comparator = OntologyComparator()
        ontologies = [create_ontology("ont1")]
        scores = [create_score(overall=0.75)]
        
        ranked = comparator.rank_batch(ontologies, scores)
        assert len(ranked) == 1
        assert ranked[0]['rank'] == 1
    
    def test_rank_batch_multiple(self):
        """Test ranking multiple ontologies."""
        comparator = OntologyComparator()
        ontologies = [create_ontology(f"ont{i}") for i in range(3)]
        scores = [create_score(overall=0.5), create_score(overall=0.8), create_score(overall=0.6)]
        
        ranked = comparator.rank_batch(ontologies, scores)
        assert len(ranked) == 3
        assert ranked[0]['overall'] == 0.8  # Best first
        assert ranked[1]['overall'] == 0.6
        assert ranked[2]['overall'] == 0.5
    
    def test_rank_by_dimension(self):
        """Test ranking by specific dimension."""
        comparator = OntologyComparator()
        ontologies = [create_ontology(f"ont{i}") for i in range(3)]
        scores = [
            create_score(completeness=0.5),
            create_score(completeness=0.9),
            create_score(completeness=0.7)
        ]
        
        ranked = comparator.rank_by_dimension(ontologies, scores, 'completeness')
        assert ranked[0]['completeness'] == 0.9
        assert ranked[1]['completeness'] == 0.7

    def test_rank_by_missing_dimension(self):
        """Test ranking when dimension is missing from score objects."""
        comparator = OntologyComparator()
        ontologies = [create_ontology("ont1"), create_ontology("ont2")]
        scores = [create_score(overall=0.7), create_score(overall=0.9)]

        ranked = comparator.rank_by_dimension(ontologies, scores, 'missing_dim')
        assert ranked[0]['missing_dim'] == 0
        assert ranked[1]['missing_dim'] == 0
    
    def test_get_top_n(self):
        """Test getting top N ontologies."""
        comparator = OntologyComparator()
        ontologies = [create_ontology(f"ont{i}") for i in range(5)]
        scores = [create_score(overall=0.5 + i*0.1) for i in range(5)]
        
        top = comparator.get_top_n(ontologies, scores, 2)
        assert len(top) == 2
        assert top[0]['overall'] == 0.9
        assert top[1]['overall'] == 0.8
    
    def test_get_top_n_exceeds_available(self):
        """Test top N when n exceeds available ontologies."""
        comparator = OntologyComparator()
        ontologies = [create_ontology(f"ont{i}") for i in range(2)]
        scores = [create_score(overall=0.7), create_score(overall=0.8)]
        
        top = comparator.get_top_n(ontologies, scores, 5)
        assert len(top) == 2


class TestComparisonMethods:
    """Test comparison operations."""
    
    def test_compare_pair_better_first(self):
        """Test pairwise comparison where first is better."""
        comparator = OntologyComparator()
        score1 = create_score(overall=0.8)
        score2 = create_score(overall=0.5)
        
        result = comparator.compare_pair(create_ontology("ont1"), score1, 
                                        create_ontology("ont2"), score2)
        assert result['better'] == 1
        assert abs(result['overall_delta'] - 0.3) < 0.001
    
    def test_compare_pair_dimension_analysis(self):
        """Test pairwise comparison dimension analysis."""
        comparator = OntologyComparator()
        score1 = create_score(completeness=0.8, consistency=0.6)
        score2 = create_score(completeness=0.6, consistency=0.9)
        
        result = comparator.compare_pair(create_ontology("ont1"), score1,
                                        create_ontology("ont2"), score2)
        assert 'dimension_deltas' in result

    def test_compare_pair_equal_scores(self):
        """Test pairwise comparison where scores are equal."""
        comparator = OntologyComparator()
        score1 = create_score(overall=0.6)
        score2 = create_score(overall=0.6)

        result = comparator.compare_pair(create_ontology("ont1"), score1,
                                        create_ontology("ont2"), score2)
        assert result['better'] == 0
        assert result['overall_delta'] == 0
    
    def test_compare_to_baseline(self):
        """Test comparison to baseline."""
        comparator = OntologyComparator()
        baseline_score = create_score(overall=0.6)
        target_score = create_score(overall=0.8)
        
        result = comparator.compare_to_baseline(create_ontology("target"), target_score,
                                               create_ontology("baseline"), baseline_score)
        assert result['improvement_percent'] > 0

    def test_compare_to_baseline_zero_baseline(self):
        """Test comparison when baseline overall is zero."""
        comparator = OntologyComparator()
        baseline_score = create_score(overall=0.0)
        target_score = create_score(overall=0.8)

        result = comparator.compare_to_baseline(create_ontology("target"), target_score,
                                               create_ontology("baseline"), baseline_score)
        assert result['improvement_percent'] == 0
    
    def test_filter_by_threshold(self):
        """Test filtering ontologies by threshold."""
        comparator = OntologyComparator()
        ontologies = [create_ontology(f"ont{i}") for i in range(4)]
        scores = [create_score(overall=x) for x in [0.3, 0.6, 0.8, 0.5]]
        
        filtered = comparator.filter_by_threshold(ontologies, scores, 0.6)
        assert len(filtered) == 2
        assert all(f['overall'] >= 0.6 for f in filtered)
    
    def test_filter_empty_result(self):
        """Test filtering with no results above threshold."""
        comparator = OntologyComparator()
        ontologies = [create_ontology(f"ont{i}") for i in range(2)]
        scores = [create_score(overall=0.3), create_score(overall=0.4)]
        
        filtered = comparator.filter_by_threshold(ontologies, scores, 0.8)
        assert len(filtered) == 0


class TestTrendDetection:
    """Test trend detection methods."""
    
    def test_detect_trend_improving(self):
        """Test detecting improving trend."""
        comparator = OntologyComparator()
        scores = [create_score(overall=x) for x in [0.5, 0.6, 0.7, 0.8, 0.9]]
        
        trend = comparator.detect_trend(scores)
        assert trend == "improving"
    
    def test_detect_trend_degrading(self):
        """Test detecting degrading trend."""
        comparator = OntologyComparator()
        scores = [create_score(overall=x) for x in [0.9, 0.8, 0.7, 0.6, 0.5]]
        
        trend = comparator.detect_trend(scores)
        assert trend == "degrading"
    
    def test_detect_trend_stable(self):
        """Test detecting stable trend."""
        comparator = OntologyComparator()
        scores = [create_score(overall=0.5) for _ in range(5)]
        
        trend = comparator.detect_trend(scores)
        assert trend == "stable"
    
    def test_detect_trend_insufficient_data(self):
        """Test trend detection with insufficient data."""
        comparator = OntologyComparator()
        scores = [create_score(overall=0.5)]
        
        trend = comparator.detect_trend(scores)
        assert trend in ["stable", "insufficient"]


class TestThresholdCalibration:
    """Test threshold calibration methods."""
    
    def test_calibrate_thresholds_75th_percentile(self):
        """Test threshold calibration at 75th percentile."""
        comparator = OntologyComparator()
        scores = [create_score(completeness=x/10) for x in range(1, 11)]
        
        thresholds = comparator.calibrate_thresholds(scores, percentile=75)
        assert 'completeness' in thresholds
        assert 0.6 <= thresholds['completeness'] <= 0.8
    
    def test_calibrate_thresholds_50th_percentile(self):
        """Test threshold calibration at 50th percentile (median)."""
        comparator = OntologyComparator()
        scores = [create_score(completeness=x/10) for x in range(1, 11)]
        
        thresholds = comparator.calibrate_thresholds(scores, percentile=50)
        assert 0.4 <= thresholds['completeness'] <= 0.6
    
    def test_calibrate_thresholds_empty_scores(self):
        """Test calibration with empty scores list."""
        comparator = OntologyComparator()
        thresholds = comparator.calibrate_thresholds([], percentile=75)
        # Should not crash, might return empty or zeros
        assert isinstance(thresholds, dict)
    
    def test_calibrate_thresholds_multiple_dimensions(self):
        """Test that calibration covers all dimensions."""
        comparator = OntologyComparator()
        scores = [create_score() for _ in range(10)]
        
        thresholds = comparator.calibrate_thresholds(scores, percentile=75)
        for dim in STANDARD_DIMENSIONS:
            assert dim in thresholds


class TestStatisticalSummaries:
    """Test statistical summarization methods."""
    
    def test_histogram_by_dimension(self):
        """Test histogram generation by dimension."""
        comparator = OntologyComparator()
        scores = [create_score(completeness=x/10) for x in range(1, 11)]
        
        histograms = comparator.histogram_by_dimension(scores, bins=5)
        assert 'completeness' in histograms
        assert len(histograms['completeness']) == 5

    def test_histogram_counts_total(self):
        """Test histogram bucket counts sum to total scores."""
        comparator = OntologyComparator()
        scores = [create_score(completeness=x/10) for x in range(1, 11)]

        histograms = comparator.histogram_by_dimension(scores, bins=4)
        assert sum(histograms['completeness']) == len(scores)
    
    def test_summary_statistics(self):
        """Test summary statistics generation."""
        comparator = OntologyComparator()
        scores = [create_score(completeness=0.5 + i*0.1) for i in range(5)]
        
        summary = comparator.summary_statistics(scores)
        assert 'completeness' in summary
        assert 'mean' in summary['completeness']
        assert 'min' in summary['completeness']
        assert 'max' in summary['completeness']
    
    def test_histogram_empty_scores(self):
        """Test histogram with empty scores."""
        comparator = OntologyComparator()
        histograms = comparator.histogram_by_dimension([], bins=5)
        assert isinstance(histograms, dict)
    
    def test_summary_statistics_single_score(self):
        """Test summary statistics with single score."""
        comparator = OntologyComparator()
        scores = [create_score(completeness=0.7)]
        
        summary = comparator.summary_statistics(scores)
        assert summary['completeness']['mean'] == 0.7


class TestCustomScoring:
    """Test custom scoring methods."""
    
    def test_reweight_score_equal_weights(self):
        """Test reweighting with equal weights."""
        comparator = OntologyComparator()
        score = create_score(completeness=0.6, consistency=0.8)
        weights = {"completeness": 0.5, "consistency": 0.5}
        
        weighted = comparator.reweight_score(score, weights)
        assert 0.6 <= weighted <= 0.8
    
    def test_reweight_score_custom_weights(self):
        """Test reweighting with custom weights emphasizing one dimension."""
        comparator = OntologyComparator()
        score = create_score(completeness=0.2, consistency=0.9)
        weights = {"completeness": 0.1, "consistency": 0.9}
        
        weighted = comparator.reweight_score(score, weights)
        assert weighted > 0.7  # Closer to consistency value

    def test_reweight_score_zero_weights(self):
        """Test reweighting with zero weights returns default."""
        comparator = OntologyComparator()
        score = create_score(completeness=0.9)
        weights = {"completeness": 0.0, "consistency": 0.0}

        weighted = comparator.reweight_score(score, weights)
        assert weighted == 0.5
    
    def test_evaluate_against_rubric(self):
        """Test evaluation against custom rubric."""
        comparator = OntologyComparator()
        score = create_score(completeness=0.8)
        rubric = {"completeness": 0.5, "consistency": 0.3}
        
        result = comparator.evaluate_against_rubric(score, rubric)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_evaluate_against_empty_rubric(self):
        """Test rubric evaluation with empty rubric returns default."""
        comparator = OntologyComparator()
        score = create_score(completeness=0.8)

        result = comparator.evaluate_against_rubric(score, {})
        assert result == 0.5
    
    def test_evaluate_against_rubric_perfect_match(self):
        """Test rubric evaluation with perfect match."""
        comparator = OntologyComparator()
        score = create_score(completeness=0.8)
        rubric = {"completeness": 0.8}
        
        result = comparator.evaluate_against_rubric(score, rubric)
        assert result == 1.0 or result > 0.9


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_score_list(self):
        """Test operations with empty score list."""
        comparator = OntologyComparator()
        ranked = comparator.rank_batch([], [])
        assert ranked == []
    
    def test_single_vs_multiple_scores(self):
        """Test consistency between single and batch operations."""
        comparator = OntologyComparator()
        ont1 = create_ontology("test")
        score = create_score(overall=0.75)
        
        ranked = comparator.rank_batch([ont1], [score])
        assert len(ranked) == 1
        assert ranked[0]['overall'] == 0.75
    
    def test_zero_overall_scores(self):
        """Test handling of zero overall scores."""
        comparator = OntologyComparator()
        scores = [create_score(overall=0.0) for _ in range(3)]
        
        trend = comparator.detect_trend(scores)
        assert trend == "stable"


class TestPropertyBased:
    """Property-based tests using hypothesis."""
    
    @given(st.lists(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False), min_size=1, max_size=10))
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_ranking_preserves_order(self, scores_list):
        """Property: Ranking preserves descending score order."""
        comparator = OntologyComparator()
        ontologies = [create_ontology(f"ont{i}") for i in range(len(scores_list))]
        scores = [create_score(overall=s) for s in scores_list]
        
        ranked = comparator.rank_batch(ontologies, scores)
        ranked_scores = [r['overall'] for r in ranked]
        
        # Check descending order
        for i in range(len(ranked_scores) - 1):
            assert ranked_scores[i] >= ranked_scores[i + 1]
    
    @given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
           st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    def test_comparison_delta_validity(self, score1_val, score2_val):
        """Property: Comparison delta equals difference."""
        comparator = OntologyComparator()
        score1 = create_score(overall=score1_val)
        score2 = create_score(overall=score2_val)
        
        result = comparator.compare_pair(create_ontology("a"), score1,
                                        create_ontology("b"), score2)
        expected_delta = abs(score1_val - score2_val)
        assert abs(result['overall_delta'] - expected_delta) < 0.01
    
    @given(st.lists(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False), min_size=2, max_size=20))
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_reweighting_bounds(self, dimension_scores):
        """Property: Reweighted score stays within dimension bounds."""
        comparator = OntologyComparator()
        kwargs = dict(zip(STANDARD_DIMENSIONS[:len(dimension_scores)], dimension_scores))
        score = create_score(**kwargs)
        weights = {dim: 1.0/len(STANDARD_DIMENSIONS) for dim in STANDARD_DIMENSIONS}
        
        weighted = comparator.reweight_score(score, weights)
        assert 0.0 <= weighted <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
