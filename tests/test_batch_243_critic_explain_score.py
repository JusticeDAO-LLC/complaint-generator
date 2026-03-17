"""Tests for OntologyCritic.explain_score() method - Batch 243.

Comprehensive test coverage for human-readable score explanation generation.
Tests all dimensions, score bands, and edge cases for explain_score().
"""

import sys
sys.path.insert(0, '/home/barberb/complaint-generator/ipfs_datasets_py')

import pytest

from ipfs_datasets_py.optimizers.graphrag import OntologyCritic, CriticScore


class TestExplainScoreBasics:
    """Basic functionality tests for explain_score()."""
    
    def test_returns_dict(self):
        """explain_score() returns a dictionary."""
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
    
    def test_all_dimensions_present(self):
        """Explanations include all seven dimensions."""
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
        expected = {'completeness', 'consistency', 'clarity', 'granularity',
                   'relationship_coherence', 'domain_alignment', 'overall'}
        assert set(result.keys()) == expected
    
    def test_explanations_are_strings(self):
        """Each explanation is a non-empty string."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.5,
            consistency=0.6,
            clarity=0.7,
            granularity=0.8,
            relationship_coherence=0.65,
            domain_alignment=0.75,
        )
        result = critic.explain_score(score)
        for key, value in result.items():
            assert isinstance(value, str), f"{key} is not a string"
            assert len(value) > 0, f"{key} is empty"


class TestExplainScoreHighScores:
    """Tests for high score explanations (>= 0.7)."""
    
    def test_high_completeness(self):
        """High completeness shows positive language."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.85,
            consistency=0.60,
            clarity=0.60,
            granularity=0.60,
            relationship_coherence=0.60,
            domain_alignment=0.60,
        )
        result = critic.explain_score(score)
        assert "captures most expected concepts" in result['completeness']
    
    def test_high_consistency(self):
        """High consistency shows no contradictions message."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.60,
            consistency=0.85,
            clarity=0.60,
            granularity=0.60,
            relationship_coherence=0.60,
            domain_alignment=0.60,
        )
        result = critic.explain_score(score)
        assert "no significant contradictions" in result['consistency']
    
    def test_high_clarity(self):
        """High clarity shows clear definitions message."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.60,
            consistency=0.60,
            clarity=0.85,
            granularity=0.60,
            relationship_coherence=0.60,
            domain_alignment=0.60,
        )
        result = critic.explain_score(score)
        assert "clear and unambiguous" in result['clarity']
    
    def test_high_granularity(self):
        """High granularity shows appropriate detail message."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.60,
            consistency=0.60,
            clarity=0.60,
            granularity=0.85,
            relationship_coherence=0.60,
            domain_alignment=0.60,
        )
        result = critic.explain_score(score)
        assert "appropriate for the domain" in result['granularity']
    
    def test_high_relationship_coherence(self):
        """High relationship coherence shows well-formed message."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.60,
            consistency=0.60,
            clarity=0.60,
            granularity=0.60,
            relationship_coherence=0.85,
            domain_alignment=0.60,
        )
        result = critic.explain_score(score)
        assert "well-formed, semantically meaningful" in result['relationship_coherence']
    
    def test_high_domain_alignment(self):
        """High domain alignment shows convention message."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.60,
            consistency=0.60,
            clarity=0.60,
            granularity=0.60,
            relationship_coherence=0.60,
            domain_alignment=0.85,
        )
        result = critic.explain_score(score)
        assert "follow domain conventions" in result['domain_alignment']


class TestExplainScoreLowScores:
    """Tests for low score explanations (< 0.7)."""
    
    def test_low_completeness(self):
        """Low completeness shows missing concepts message."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.35,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        result = critic.explain_score(score)
        assert "many expected concepts" in result['completeness']
        assert "missing" in result['completeness']
    
    def test_low_consistency(self):
        """Low consistency shows contradictions message."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.35,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        result = critic.explain_score(score)
        assert "contradictions" in result['consistency']
    
    def test_low_clarity(self):
        """Low clarity shows ambiguous labels message."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.35,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        result = critic.explain_score(score)
        assert "lack definitions or have ambiguous" in result['clarity']
    
    def test_low_granularity(self):
        """Low granularity shows coarse/fine-grained message."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.35,
            relationship_coherence=0.75,
            domain_alignment=0.75,
        )
        result = critic.explain_score(score)
        assert "coarse or too fine-grained" in result['granularity']
    
    def test_low_relationship_coherence(self):
        """Low relationship coherence shows poor quality message."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.35,
            domain_alignment=0.75,
        )
        result = critic.explain_score(score)
        assert "lack semantic coherence" in result['relationship_coherence']
    
    def test_low_domain_alignment(self):
        """Low domain alignment shows deviation message."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.75,
            consistency=0.75,
            clarity=0.75,
            granularity=0.75,
            relationship_coherence=0.75,
            domain_alignment=0.35,
        )
        result = critic.explain_score(score)
        assert "deviate from expected domain conventions" in result['domain_alignment']


class TestExplainScoreOverall:
    """Tests for overall score explanation."""
    
    def test_good_overall(self):
        """Overall score >= 0.7 shows ready for use."""
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
        # With all scores at 0.75, overall should be >= 0.7
        assert "ready for use" in result['overall']
    
    def test_poor_overall(self):
        """Overall score < 0.7 shows refinement recommended."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.35,
            consistency=0.40,
            clarity=0.38,
            granularity=0.45,
            relationship_coherence=0.30,
            domain_alignment=0.36,
        )
        result = critic.explain_score(score)
        # With most dimensions < 0.5, overall should be < 0.7
        assert "further refinement is recommended" in result['overall']


class TestExplainScoreBands:
    """Tests for score band classifications in explanations."""
    
    def test_excellent_band(self):
        """Scores >= 0.85 classified as excellent."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.90,
            consistency=0.50,
            clarity=0.50,
            granularity=0.50,
            relationship_coherence=0.50,
            domain_alignment=0.50,
        )
        result = critic.explain_score(score)
        assert "excellent" in result['completeness']
    
    def test_good_band(self):
        """Scores [0.70, 0.85) classified as good."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.78,
            consistency=0.50,
            clarity=0.50,
            granularity=0.50,
            relationship_coherence=0.50,
            domain_alignment=0.50,
        )
        result = critic.explain_score(score)
        assert "good" in result['completeness']
    
    def test_acceptable_band(self):
        """Scores [0.50, 0.70) classified as acceptable."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.60,
            consistency=0.50,
            clarity=0.50,
            granularity=0.50,
            relationship_coherence=0.50,
            domain_alignment=0.50,
        )
        result = critic.explain_score(score)
        assert "acceptable" in result['completeness']
    
    def test_weak_band(self):
        """Scores [0.30, 0.50) classified as weak."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.40,
            consistency=0.50,
            clarity=0.50,
            granularity=0.50,
            relationship_coherence=0.50,
            domain_alignment=0.50,
        )
        result = critic.explain_score(score)
        assert "weak" in result['completeness']
    
    def test_poor_band(self):
        """Scores < 0.30 classified as poor."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.20,
            consistency=0.50,
            clarity=0.50,
            granularity=0.50,
            relationship_coherence=0.50,
            domain_alignment=0.50,
        )
        result = critic.explain_score(score)
        assert "poor" in result['completeness']


class TestExplainScoreEdgeCases:
    """Edge cases and boundary tests."""
    
    def test_all_zeros(self):
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
        for key, value in result.items():
            assert len(value) > 0, f"{key} is empty"
    
    def test_all_ones(self):
        """All 1.0 scores should have explanations."""
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
        for key, value in result.items():
            assert len(value) > 0, f"{key} is empty"
    
    def test_mixed_scores(self):
        """Mix of high and low scores provides appropriate explanations."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.85,  # High
            consistency=0.45,   # Low
            clarity=0.95,       # Very high
            granularity=0.35,   # Very low
            relationship_coherence=0.70,  # Boundary
            domain_alignment=0.50,        # Mid
        )
        result = critic.explain_score(score)
        
        # Check each dimension shows appropriate messages
        assert "captures most expected concepts" in result['completeness']
        assert "contradictions" in result['consistency']
        assert "clear and unambiguous" in result['clarity']
        assert "coarse or too fine-grained" in result['granularity']


class TestExplainScorePercentages:
    """Tests for percentage formatting in explanations."""
    
    def test_percentages_included(self):
        """Explanations include percentage values."""
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
        # Should have "50%" in completeness
        assert "50%" in result['completeness']
    
    def test_all_have_percentages(self):
        """All explanations have percentage formatting."""
        critic = OntologyCritic()
        score = CriticScore(
            completeness=0.66,
            consistency=0.77,
            clarity=0.88,
            granularity=0.99,
            relationship_coherence=0.11,
            domain_alignment=0.22,
        )
        result = critic.explain_score(score)
        for key, value in result.items():
            assert "%" in value, f"{key} missing percentage"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
