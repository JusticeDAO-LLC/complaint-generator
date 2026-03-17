"""Test suite for Batch 241 - Batch API Methods for OntologyMediator.

Covers:
- OntologyMediator.batch_suggest_strategies() - Batch strategy recommendation
- OntologyMediator.compare_strategies() - Compare alternative strategies
- Integration tests with multiple ontologies
"""

import pytest

from ipfs_datasets_py.optimizers.graphrag import (
    OntologyMediator,
    OntologyCritic,
    OntologyGenerator,
    OntologyGenerationContext,
)
from ipfs_datasets_py.optimizers.graphrag.ontology_critic import CriticScore


@pytest.fixture
def critic():
    """Create a critic instance."""
    return OntologyCritic()


@pytest.fixture
def generator():
    """Create a generator instance."""
    return OntologyGenerator()


@pytest.fixture
def context():
    """Create a generation context."""
    return OntologyGenerationContext(
        data_source="test",
        data_type="text",
        domain="legal"
    )


@pytest.fixture
def mediator(generator, critic):
    """Create a mediator instance."""
    return OntologyMediator(
        generator=generator,
        critic=critic,
        max_rounds=5,
        convergence_threshold=0.85
    )


def create_test_score(
    completeness: float = 0.7,
    consistency: float = 0.75,
    clarity: float = 0.65,
    granularity: float = 0.7,
    relationship_coherence: float = 0.72,
    domain_alignment: float = 0.78
) -> CriticScore:
    """Create a test critic score."""
    return CriticScore(
        completeness=completeness,
        consistency=consistency,
        clarity=clarity,
        granularity=granularity,
        relationship_coherence=relationship_coherence,
        domain_alignment=domain_alignment,
        strengths=["Good domain coverage"],
        weaknesses=["Some clarity issues"],
        recommendations=["Add more properties", "Clarify relationships"]
    )


class TestBatchSuggestStrategies:
    """Test the batch_suggest_strategies() method."""

    def test_batch_suggest_strategies_returns_list(self, mediator, context, create_test_ontology):
        """Test that batch_suggest_strategies returns a list of strategies."""
        ontologies = [
            create_test_ontology(5, 3),
            create_test_ontology(8, 5),
            create_test_ontology(3, 2)
        ]
        scores = [
            create_test_score(0.7, 0.75, 0.65, 0.7, 0.72, 0.78),
            create_test_score(0.6, 0.65, 0.55, 0.6, 0.62, 0.68),
            create_test_score(0.8, 0.82, 0.75, 0.78, 0.80, 0.85)
        ]

        strategies = mediator.batch_suggest_strategies(ontologies, scores, context)

        assert isinstance(strategies, list)
        assert len(strategies) == 3
        assert all(isinstance(s, dict) for s in strategies)

    def test_batch_suggest_strategies_each_has_required_fields(self, mediator, context, create_test_ontology):
        """Test that each strategy has required fields."""
        ontologies = [
            create_test_ontology(5, 3),
            create_test_ontology(8, 5)
        ]
        scores = [
            create_test_score(0.7, 0.75, 0.65),
            create_test_score(0.6, 0.65, 0.55)
        ]

        strategies = mediator.batch_suggest_strategies(ontologies, scores, context)

        required_fields = {"action", "priority", "rationale", "estimated_impact", "affected_entity_count"}
        for strategy in strategies:
            assert required_fields.issubset(strategy.keys())
            assert isinstance(strategy["action"], str)
            assert strategy["priority"] in ["critical", "high", "medium", "low"]
            assert 0.0 <= strategy["estimated_impact"] <= 1.0
            assert isinstance(strategy["affected_entity_count"], int)

    def test_batch_suggest_strategies_empty_list(self, mediator, context):
        """Test batch_suggest_strategies with empty lists."""
        strategies = mediator.batch_suggest_strategies([], [], context)
        assert strategies == []

    def test_batch_suggest_strategies_single_item(self, mediator, context, create_test_ontology):
        """Test batch_suggest_strategies with single item."""
        ontologies = [create_test_ontology(5, 3)]
        scores = [create_test_score(0.7, 0.75, 0.65)]

        strategies = mediator.batch_suggest_strategies(ontologies, scores, context)

        assert len(strategies) == 1
        assert isinstance(strategies[0], dict)
        assert "action" in strategies[0]

    def test_batch_suggest_strategies_respects_score_differences(self, mediator, context, create_test_ontology):
        """Test that different scores produce different strategies."""
        ontology = create_test_ontology(5, 3)
        ont_list = [ontology] * 3

        # Three different scores representing different quality levels
        scores = [
            create_test_score(0.8, 0.82, 0.75),  # Good
            create_test_score(0.5, 0.52, 0.45),  # Poor
            create_test_score(0.88, 0.90, 0.85)  # Excellent
        ]

        strategies = mediator.batch_suggest_strategies(ont_list, scores, context)

        # Excellent score should have low priority or no_action
        excellent_strategy = strategies[2]
        if excellent_strategy["action"] != "converged":
            assert excellent_strategy["priority"] in ["low", "medium"]

    def test_batch_suggest_strategies_large_batch(self, mediator, context, create_test_ontology):
        """Test batch_suggest_strategies with larger batch."""
        import random
        random.seed(42)

        batch_size = 50
        ontologies = [create_test_ontology(random.randint(3, 20), random.randint(2, 15)) for _ in range(batch_size)]
        scores = [
            create_test_score(
                random.uniform(0.5, 0.95),
                random.uniform(0.5, 0.95),
                random.uniform(0.5, 0.95),
                random.uniform(0.5, 0.95),
                random.uniform(0.5, 0.95),
                random.uniform(0.5, 0.95)
            )
            for _ in range(batch_size)
        ]

        strategies = mediator.batch_suggest_strategies(ontologies, scores, context)

        assert len(strategies) == batch_size
        assert all(isinstance(s, dict) for s in strategies)
        assert all("action" in s for s in strategies)


class TestCompareStrategies:
    """Test the compare_strategies() method."""

    def test_compare_strategies_returns_ranking(self, mediator, context, create_test_ontology):
        """Test that compare_strategies returns ranked alternatives."""
        ontologies = [
            create_test_ontology(5, 3),
            create_test_ontology(8, 5),
            create_test_ontology(3, 2)
        ]
        scores = [
            create_test_score(0.7, 0.75, 0.65),
            create_test_score(0.6, 0.65, 0.55),
            create_test_score(0.8, 0.82, 0.75)
        ]

        comparison = mediator.compare_strategies(ontologies, scores, context)

        assert isinstance(comparison, list)
        assert len(comparison) == 3

    def test_compare_strategies_has_ranking_info(self, mediator, context, create_test_ontology):
        """Test that comparison includes ranking information."""
        ontologies = [
            create_test_ontology(5, 3),
            create_test_ontology(8, 5)
        ]
        scores = [
            create_test_score(0.7, 0.75, 0.65),
            create_test_score(0.6, 0.65, 0.55)
        ]

        comparison = mediator.compare_strategies(ontologies, scores, context)

        for idx, item in enumerate(comparison):
            assert isinstance(item, dict)
            assert "index" in item
            assert "rank" in item
            assert "strategy" in item
            assert "priority_score" in item
            assert isinstance(item["rank"], int)
            assert item["rank"] >= 1

    def test_compare_strategies_ordering(self, mediator, context, create_test_ontology):
        """Test that strategies are ordered by effectiveness."""
        ontology = create_test_ontology(10, 5)
        ontologies = [ontology] * 3

        # Deliberately create scores in non-sorted order
        scores = [
            create_test_score(0.5, 0.5, 0.45),  # Poor (should be ranked lower/last)
            create_test_score(0.88, 0.90, 0.85),  # Excellent (should be ranked high)
            create_test_score(0.7, 0.75, 0.65)   # Medium (should be ranked middle)
        ]

        comparison = mediator.compare_strategies(ontologies, scores, context)

        # Verify ranking is properly ordered
        ranks = [item["rank"] for item in comparison]
        assert ranks == sorted(ranks)

        # Verify the mapping of indices to ranks makes sense
        indices_by_rank = sorted([(item["rank"], item["index"]) for item in comparison])
        # Best strategy should have lowest score issues
        assert comparison[0]["strategy"]["priority"] in ["low", "medium"]

    def test_compare_strategies_empty_list(self, mediator, context):
        """Test compare_strategies with empty input."""
        comparison = mediator.compare_strategies([], [], context)
        assert comparison == []

    def test_compare_strategies_single_item(self, mediator, context, create_test_ontology):
        """Test compare_strategies with single ontology."""
        ontologies = [create_test_ontology(5, 3)]
        scores = [create_test_score(0.7, 0.75, 0.65)]

        comparison = mediator.compare_strategies(ontologies, scores, context)

        assert len(comparison) == 1
        assert comparison[0]["rank"] == 1

    def test_compare_strategies_includes_priority_score(self, mediator, context, create_test_ontology):
        """Test that priority scores are reasonable."""
        ontologies = [
            create_test_ontology(5, 3),
            create_test_ontology(8, 5)
        ]
        scores = [
            create_test_score(0.7, 0.75, 0.65),
            create_test_score(0.6, 0.65, 0.55)
        ]

        comparison = mediator.compare_strategies(ontologies, scores, context)

        for item in comparison:
            priority_score = item["priority_score"]
            assert isinstance(priority_score, (float, int))
            assert 0.0 <= priority_score <= 1.0


class TestBatchMethodsIntegration:
    """Integration tests for batch methods."""

    def test_batch_and_compare_consistency(self, mediator, context, create_test_ontology):
        """Test that batch and compare methods are consistent."""
        ontologies = [
            create_test_ontology(5, 3),
            create_test_ontology(8, 5),
            create_test_ontology(3, 2),
            create_test_ontology(10, 6)
        ]
        scores = [
            create_test_score(0.7, 0.75, 0.65),
            create_test_score(0.6, 0.65, 0.55),
            create_test_score(0.8, 0.82, 0.75),
            create_test_score(0.55, 0.58, 0.50)
        ]

        batch_strategies = mediator.batch_suggest_strategies(ontologies, scores, context)
        comparison = mediator.compare_strategies(ontologies, scores, context)

        # Same number of results
        assert len(batch_strategies) == len(comparison)

        # Verify all strategies have actions
        for batch_strat in batch_strategies:
            assert "action" in batch_strat
        for comp_item in comparison:
            assert "strategy" in comp_item
            assert "action" in comp_item["strategy"]

    def test_prioritization_reflects_scores(self, mediator, context, create_test_ontology):
        """Test that worse scores get higher priority."""
        ontology = create_test_ontology(5, 3)
        ont_list = [ontology] * 2

        scores = [
            create_test_score(0.5, 0.5, 0.45),  # Bad
            create_test_score(0.85, 0.87, 0.80)  # Good
        ]

        comparison = mediator.compare_strategies(ont_list, scores, context)

        # Bad score should have higher priority (lower rank or higher priority_score)
        bad_item = comparison[0] if comparison[0]["index"] == 0 else comparison[1]
        good_item = comparison[1] if comparison[0]["index"] == 0 else comparison[0]

        # The bad ontology should have higher priority score or earlier in comparison
        assert bad_item["priority_score"] >= good_item["priority_score"]


class TestBatchMethodsEdgeCases:
    """Test edge cases for batch methods."""

    def test_batch_suggest_with_extreme_scores(self, mediator, context, create_test_ontology):
        """Test batch methods with extreme score values."""
        ontologies = [
            create_test_ontology(5, 3),
            create_test_ontology(8, 5)
        ]
        scores = [
            create_test_score(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),  # All zeros
            create_test_score(1.0, 1.0, 1.0, 1.0, 1.0, 1.0)   # All ones
        ]

        strategies = mediator.batch_suggest_strategies(ontologies, scores, context)
        assert len(strategies) == 2
        assert all("action" in s for s in strategies)

    def test_batch_suggest_with_many_recommendations(self, mediator, context, create_test_ontology):
        """Test batch methods when scores have many recommendations."""
        ontologies = [create_test_ontology(5, 3)]
        
        # Create score with many recommendations
        score = CriticScore(
            completeness=0.5,
            consistency=0.5,
            clarity=0.45,
            granularity=0.5,
            relationship_coherence=0.52,
            domain_alignment=0.58,
            strengths=["Some coverage"],
            weaknesses=["Many issues"],
            recommendations=[
                "Add more properties",
                "Clarify relationships",
                "Fix naming conventions",
                "Merge duplicates",
                "Prune orphans",
                "Split entities",
                "Improve domain alignment"
            ]
        )
        
        strategies = mediator.batch_suggest_strategies(ontologies, [score], context)
        assert len(strategies) == 1
        assert "action" in strategies[0]

    def test_compare_strategies_with_tied_scores(self, mediator, context, create_test_ontology):
        """Test comparison when multiple ontologies have identical scores."""
        ontologies = [create_test_ontology(5, 3)] * 3  # Three identical ontologies
        scores = [create_test_score(0.7, 0.75, 0.65)] * 3  # Same scores

        comparison = mediator.compare_strategies(ontologies, scores, context)

        # All should be ranked (even if tied)
        ranks = [item["rank"] for item in comparison]
        assert all(r >= 1 for r in ranks)
        assert len(comparison) == 3
