"""Tests for OntologyCritic.explain_score() method.

Comprehensive test coverage for human-readable score explanation generation,
including all dimensions, score bands, and edge cases.
"""

import sys
sys.path.insert(0, '/home/barberb/complaint-generator/ipfs_datasets_py')

import pytest
from unittest.mock import MagicMock

from ipfs_datasets_py.optimizers.graphrag import OntologyCritic, CriticScore


class TestExplainScoreBasics:
    """Tests for basic explain_score functionality."""
    
    def test_explain_score_returns_dict(self):
        """explain_score returns a dictionary."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert isinstance(result, dict)
    
    def test_explain_score_has_all_dimensions(self):
        """explain_score includes explanations for all dimensions."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        expected_keys = {
            'completeness',
            'consistency', 
            'clarity',
            'granularity',
            'relationship_coherence',
            'domain_alignment',
            'overall'
        }
        assert set(result.keys()) == expected_keys
    
    def test_explain_score_values_are_strings(self):
        """Each explanation is a non-empty string."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        for key, value in result.items():
            assert isinstance(value, str)
            assert len(value) > 0


class TestExplainScoreHighScores:
    """Tests for explanations with high scores (0.7+)."""
    
    def test_high_completeness_explanation(self):
        """High completeness (>= 0.7) indicates good coverage."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.85,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "captures most expected concepts" in result['completeness']
    
    def test_high_consistency_explanation(self):
        """High consistency (>= 0.7) indicates no significant contradictions."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.85,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "no significant contradictions" in result['consistency']
    
    def test_high_clarity_explanation(self):
        """High clarity (>= 0.7) indicates clear definitions."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.85,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "clear and unambiguous" in result['clarity']
    
    def test_high_granularity_explanation(self):
        """High granularity (>= 0.7) indicates appropriate level of detail."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.85,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "appropriate for the domain" in result['granularity']
    
    def test_high_relationship_coherence_explanation(self):
        """High relationship coherence (>= 0.7) indicates well-formed relationships."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.85,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "well-formed, semantically meaningful" in result['relationship_coherence']
    
    def test_high_domain_alignment_explanation(self):
        """High domain alignment (>= 0.7) indicates domain conventions followed."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.85,
        )
        
        result = critic.explain_score(score)
        assert "follow domain conventions" in result['domain_alignment']
    
    def test_high_overall_explanation(self):
        """High overall (>= 0.7) indicates ready for use."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "ready for use" in result['overall']


class TestExplainScoreLowScores:
    """Tests for explanations with low scores (< 0.7)."""
    
    def test_low_completeness_explanation(self):
        """Low completeness (< 0.7) indicates missing concepts."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.45,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "many expected concepts" in result['completeness']
        assert "missing" in result['completeness']
    
    def test_low_consistency_explanation(self):
        """Low consistency (< 0.7) indicates contradictions detected."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.45,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "contradictions" in result['consistency']
    
    def test_low_clarity_explanation(self):
        """Low clarity (< 0.7) indicates ambiguous labels."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.45,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "lack definitions or have ambiguous" in result['clarity']
    
    def test_low_granularity_explanation(self):
        """Low granularity (< 0.7) indicates inappropriate level of detail."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.45,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "coarse or too fine-grained" in result['granularity']
    
    def test_low_relationship_coherence_explanation(self):
        """Low relationship coherence (< 0.7) indicates poor relationship quality."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.45,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "lack semantic coherence" in result['relationship_coherence']
    
    def test_low_domain_alignment_explanation(self):
        """Low domain alignment (< 0.7) indicates deviation from conventions."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.45,
        )
        
        result = critic.explain_score(score)
        assert "deviate from expected domain conventions" in result['domain_alignment']
    
    def test_low_overall_explanation(self):
        """Low overall (< 0.7) indicates refinement recommended."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "further refinement is recommended" in result['overall']


class TestExplainScoreScoreBands:
    """Tests for score band classification."""
    
    def test_excellent_band_explanation(self):
        """Scores >= 0.85 are classified as excellent."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.90,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "excellent" in result['completeness']
    
    def test_good_band_explanation(self):
        """Scores >= 0.70 and < 0.85 are classified as good."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.78,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "good" in result['completeness']
    
    def test_acceptable_band_explanation(self):
        """Scores >= 0.50 and < 0.70 are classified as acceptable."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.60,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "acceptable" in result['completeness']
    
    def test_weak_band_explanation(self):
        """Scores >= 0.30 and < 0.50 are classified as weak."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.40,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "weak" in result['completeness']
    
    def test_poor_band_explanation(self):
        """Scores < 0.30 are classified as poor."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.20,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "poor" in result['completeness']


class TestExplainScoreEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_all_scores_zero(self):
        """All zero scores should have explanations."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.0,
            consistency=0.0,
            clarity=0.0,
            granularity=0.0,
            relationship_coherence=0.0,
            domain_alignment=0.0,
        )
        
        result = critic.explain_score(score)
        assert len(result) == 7
        for value in result.values():
            assert len(value) > 0
    
    def test_all_scores_one(self):
        """All scores of 1.0 should have explanations."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=1.0,
            consistency=1.0,
            clarity=1.0,
            granularity=1.0,
            relationship_coherence=1.0,
            domain_alignment=1.0,
        )
        
        result = critic.explain_score(score)
        assert len(result) == 7
        for value in result.values():
            assert len(value) > 0
    
    def test_boundary_score_07(self):
        """Score of exactly 0.7 should be classified as good."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.7,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        # 0.7 is the boundary for "good"
        assert "captures most expected concepts" in result['completeness']
    
    def test_boundary_score_069(self):
        """Score just below 0.7 should indicate areas for improvement."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.69,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        # Score < 0.7 shows gaps
        assert "many expected concepts" in result['completeness']
    
    def test_mixed_score_levels(self):
        """Mix of high and low scores should provide appropriate explanations."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.85,  # High
            consistency=0.45,   # Low
            clarity=0.95,       # Very high
            granularity=0.35,   # Very low
            relationship_coherence=0.70, # Boundary
            domain_alignment=0.50,       # Mid
        )
        
        result = critic.explain_score(score)
        
        # Check each dimension's explanation matches its score level
        assert "captures most expected concepts" in result['completeness']
        assert "contradictions" in result['consistency']
        assert "clear and unambiguous" in result['clarity']
        assert "coarse or too fine-grained" in result['granularity']
        assert "appropriate for the domain" in result['relationship_coherence']
        assert "further refinement is recommended" in result['overall']


class TestExplainScorePercentageFormatting:
    """Tests for percentage formatting in explanations."""
    
    def test_percentages_are_included(self):
        """Explanations should include percentage representations."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.50,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        # Should have percentages like "50%" or "50.0%"
        assert "50%" in result['completeness']
    
    def test_percentage_formatting_consistency(self):
        """All percentage values should be consistently formatted."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.666,
            consistency=0.777,
            clarity=0.888,
            granularity=0.999,
            relationship_coherence=0.111,
            domain_alignment=0.222,
        )
        
        result = critic.explain_score(score)
        for key, value in result.items():
            # Each explanation should contain percentage formatting
            assert "%" in value


class TestExplainScoreIntegration:
    """Integration tests for explain_score with different scenarios."""
    
    def test_typical_good_ontology(self):
        """Typical good ontology should have positive explanations."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.82,
            consistency=0.79,
            clarity=0.85,
            granularity=0.76,
            relationship_coherence=0.81,
            domain_alignment=0.78,
        )
        
        result = critic.explain_score(score)
        assert "ready for use" in result['overall']
    
    def test_typical_poor_ontology(self):
        """Typical poor ontology should have negative explanations."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.35,
            consistency=0.42,
            clarity=0.38,
            granularity=0.45,
            relationship_coherence=0.40,
            domain_alignment=0.36,
        )
        
        result = critic.explain_score(score)
        assert "further refinement is recommended" in result['overall']
    
    def test_unbalanced_ontology(self):
        """Unbalanced ontology (one strong, one weak dimension) should show both."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.95,  # Excellent
            consistency=0.25,   # Poor
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        
        result = critic.explain_score(score)
        assert "captures most expected concepts" in result['completeness']
        assert "contradictions" in result['consistency']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
