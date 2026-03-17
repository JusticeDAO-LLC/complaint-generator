"""TIER 3 type annotation tests for OntologyGenerator metrics methods.

Tests for confidence_histogram, entity_type_distribution, entity_count_by_type,
and relationship_type_counts methods with ConfidenceHistogram, EntityTypeDistribution,
EntityCountByType, and RelationshipTypeCounts type contracts.
"""
import pytest
from dataclasses import dataclass
from typing import Dict

# OntologyGenerator and result types
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import OntologyGenerator

# Type contracts
from ipfs_datasets_py.optimizers.graphrag.query_optimizer_types import (
    ConfidenceHistogram,
    EntityTypeDistribution,
    EntityCountByType,
    RelationshipTypeCounts,
)

# Result structures from ontology_generator
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    Entity,
    Relationship,
    EntityExtractionResult,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture()
def ontology_generator():
    """Create an OntologyGenerator instance."""
    return OntologyGenerator()


@pytest.fixture()
def empty_result() -> EntityExtractionResult:
    """Create an empty EntityExtractionResult (no entities, no relationships)."""
    return EntityExtractionResult(entities=[], relationships=[], confidence=0.0)


@pytest.fixture()
def simple_result() -> EntityExtractionResult:
    """Create a simple EntityExtractionResult with 3 entities and 2 relationships."""
    entities = [
        Entity(id="e1", text="Alice", type="Person", confidence=0.9),
        Entity(id="e2", text="Google", type="Organization", confidence=0.85),
        Entity(id="e3", text="Bob", type="Person", confidence=0.7),
    ]
    relationships = [
        Relationship(
            id="r1",
            source_id="e1",
            target_id="e2",
            type="works_for",
        ),
        Relationship(
            id="r2",
            source_id="e3",
            target_id="e2",
            type="works_for",
        ),
    ]
    return EntityExtractionResult(entities=entities, relationships=relationships, confidence=0.82)


@pytest.fixture()
def multi_type_result() -> EntityExtractionResult:
    """Create an EntityExtractionResult with varied entity types and confidences."""
    entities = [
        Entity(id="e1", text="Person1", type="Person", confidence=0.95),
        Entity(id="e2", text="Person2", type="Person", confidence=0.92),
        Entity(id="e3", text="Person3", type="Person", confidence=0.88),
        Entity(id="e4", text="Org1", type="Organization", confidence=0.80),
        Entity(id="e5", text="Org2", type="Organization", confidence=0.75),
        Entity(id="e6", text="Location1", type="Location", confidence=0.70),
    ]
    relationships = [
        Relationship(
            id="r1",
            source_id="e1",
            target_id="e4",
            type="works_for",
        ),
        Relationship(
            id="r2",
            source_id="e2",
            target_id="e4",
            type="works_for",
        ),
        Relationship(
            id="r3",
            source_id="e4",
            target_id="e6",
            type="located_in",
        ),
        Relationship(
            id="r4",
            source_id="e5",
            target_id="e6",
            type="located_in",
        ),
        Relationship(
            id="r5",
            source_id="e1",
            target_id="e2",
            type="knows",
        ),
    ]
    return EntityExtractionResult(entities=entities, relationships=relationships, confidence=0.84)


# ============================================================================
# Tests: confidence_histogram
# ============================================================================


class TestConfidenceHistogram:
    """Tests for OntologyGenerator.confidence_histogram() return type."""

    def test_returns_confidence_histogram_type(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify return type is ConfidenceHistogram (Dict[str, int])."""
        result = ontology_generator.confidence_histogram(simple_result, bins=5)
        assert isinstance(result, dict)
        # All keys are strings (bucket labels)
        assert all(isinstance(k, str) for k in result.keys())
        # All values are integers (counts)
        assert all(isinstance(v, int) for v in result.values())

    def test_histogram_bins_parameter(
        self, ontology_generator: OntologyGenerator, multi_type_result: EntityExtractionResult
    ):
        """Verify histogram respects bins parameter."""
        result_5 = ontology_generator.confidence_histogram(multi_type_result, bins=5)
        result_10 = ontology_generator.confidence_histogram(multi_type_result, bins=10)
        # More bins should have different structure (likely more entries)
        assert isinstance(result_5, dict)
        assert isinstance(result_10, dict)

    def test_histogram_empty_result(
        self, ontology_generator: OntologyGenerator, empty_result: EntityExtractionResult
    ):
        """Verify histogram handles empty results."""
        result = ontology_generator.confidence_histogram(empty_result, bins=5)
        assert isinstance(result, dict)
        # Histogram creates buckets even with no data, counts should all be 0
        assert all(v == 0 for v in result.values())

    def test_histogram_bucket_labels_are_ranges(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify bucket labels are in expected format like '0.0-0.2'."""
        result = ontology_generator.confidence_histogram(simple_result, bins=5)
        # Check that bucket labels look like ranges
        for label in result.keys():
            assert isinstance(label, str)
            assert "-" in label  # Should contain a dash (e.g., "0.0-0.2")

    def test_histogram_count_totals_match_entities(
        self, ontology_generator: OntologyGenerator, multi_type_result: EntityExtractionResult
    ):
        """Verify histogram counts sum to total entity count."""
        result = ontology_generator.confidence_histogram(multi_type_result, bins=5)
        total_count = sum(result.values())
        assert total_count == len(multi_type_result.entities)


# ============================================================================
# Tests: entity_type_distribution
# ============================================================================


class TestEntityTypeDistribution:
    """Tests for OntologyGenerator.entity_type_distribution() return type."""

    def test_returns_entity_type_distribution_type(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify return type is EntityTypeDistribution (Dict[str, float])."""
        result = ontology_generator.entity_type_distribution(simple_result)
        assert isinstance(result, dict)
        # All keys are strings (type names)
        assert all(isinstance(k, str) for k in result.keys())
        # All values are floats (relative frequencies)
        assert all(isinstance(v, float) for v in result.values())

    def test_distribution_values_sum_to_one(
        self, ontology_generator: OntologyGenerator, multi_type_result: EntityExtractionResult
    ):
        """Verify distribution values sum to approximately 1.0."""
        result = ontology_generator.entity_type_distribution(multi_type_result)
        total = sum(result.values())
        assert 0.99 <= total <= 1.01  # Account for floating point rounding

    def test_distribution_values_in_valid_range(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify all distribution values are in [0.0, 1.0]."""
        result = ontology_generator.entity_type_distribution(simple_result)
        assert all(0.0 <= v <= 1.0 for v in result.values())

    def test_distribution_empty_result(
        self, ontology_generator: OntologyGenerator, empty_result: EntityExtractionResult
    ):
        """Verify distribution handles empty results."""
        result = ontology_generator.entity_type_distribution(empty_result)
        # Should return empty dict when no entities
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_distribution_type_names_match_input(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify distribution keys match entity types in result."""
        result = ontology_generator.entity_type_distribution(simple_result)
        entity_types = {e.type for e in simple_result.entities}
        assert set(result.keys()) == entity_types


# ============================================================================
# Tests: entity_count_by_type
# ============================================================================


class TestEntityCountByType:
    """Tests for OntologyGenerator.entity_count_by_type() return type."""

    def test_returns_entity_count_by_type(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify return type is EntityCountByType (Dict[str, int])."""
        result = ontology_generator.entity_count_by_type(simple_result)
        assert isinstance(result, dict)
        # All keys are strings (type names)
        assert all(isinstance(k, str) for k in result.keys())
        # All values are integers (counts)
        assert all(isinstance(v, int) for v in result.values())

    def test_count_totals_match_entity_count(
        self, ontology_generator: OntologyGenerator, multi_type_result: EntityExtractionResult
    ):
        """Verify counts sum to total entity count."""
        result = ontology_generator.entity_count_by_type(multi_type_result)
        total_count = sum(result.values())
        assert total_count == len(multi_type_result.entities)

    def test_count_values_all_positive(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify all count values are positive integers."""
        result = ontology_generator.entity_count_by_type(simple_result)
        assert all(v > 0 for v in result.values())

    def test_count_empty_result(
        self, ontology_generator: OntologyGenerator, empty_result: EntityExtractionResult
    ):
        """Verify count handles empty results."""
        result = ontology_generator.entity_count_by_type(empty_result)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_count_correct_per_type(
        self, ontology_generator: OntologyGenerator, multi_type_result: EntityExtractionResult
    ):
        """Verify counts for each type are correct."""
        result = ontology_generator.entity_count_by_type(multi_type_result)
        # Count entities by type
        expected = {}
        for entity in multi_type_result.entities:
            expected[entity.type] = expected.get(entity.type, 0) + 1
        assert result == expected


# ============================================================================
# Tests: relationship_type_counts
# ============================================================================


class TestRelationshipTypeCounts:
    """Tests for OntologyGenerator.relationship_type_counts() return type."""

    def test_returns_relationship_type_counts(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify return type is RelationshipTypeCounts (Dict[str, int])."""
        result = ontology_generator.relationship_type_counts(simple_result)
        assert isinstance(result, dict)
        # All keys are strings (relationship type names)
        assert all(isinstance(k, str) for k in result.keys())
        # All values are integers (counts)
        assert all(isinstance(v, int) for v in result.values())

    def test_count_totals_match_relationship_count(
        self, ontology_generator: OntologyGenerator, multi_type_result: EntityExtractionResult
    ):
        """Verify counts sum to total relationship count."""
        result = ontology_generator.relationship_type_counts(multi_type_result)
        total_count = sum(result.values())
        assert total_count == len(multi_type_result.relationships)

    def test_count_values_all_positive(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify all count values are positive integers."""
        result = ontology_generator.relationship_type_counts(simple_result)
        assert all(v > 0 for v in result.values())

    def test_count_empty_result(
        self, ontology_generator: OntologyGenerator, empty_result: EntityExtractionResult
    ):
        """Verify count handles empty results."""
        result = ontology_generator.relationship_type_counts(empty_result)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_count_correct_per_type(
        self, ontology_generator: OntologyGenerator, multi_type_result: EntityExtractionResult
    ):
        """Verify counts for each type are correct."""
        result = ontology_generator.relationship_type_counts(multi_type_result)
        # Count relationships by type
        expected = {}
        for rel in multi_type_result.relationships:
            expected[rel.type] = expected.get(rel.type, 0) + 1
        assert result == expected


# ============================================================================
# Integration Tests: TIER 3 Methods Together
# ============================================================================


class TestTIER3Integration:
    """Integration tests validating multiple TIER 3 methods together."""

    def test_all_metrics_return_expected_types(
        self, ontology_generator: OntologyGenerator, multi_type_result: EntityExtractionResult
    ):
        """Verify all 4 TIER 3 methods return their expected types."""
        histogram = ontology_generator.confidence_histogram(multi_type_result, bins=5)
        distribution = ontology_generator.entity_type_distribution(multi_type_result)
        counts_by_type = ontology_generator.entity_count_by_type(multi_type_result)
        rel_counts = ontology_generator.relationship_type_counts(multi_type_result)

        # Type validation
        assert isinstance(histogram, dict)
        assert isinstance(distribution, dict)
        assert isinstance(counts_by_type, dict)
        assert isinstance(rel_counts, dict)

        # Value type validation
        assert all(isinstance(v, int) for v in histogram.values())
        assert all(isinstance(v, float) for v in distribution.values())
        assert all(isinstance(v, int) for v in counts_by_type.values())
        assert all(isinstance(v, int) for v in rel_counts.values())

    def test_entity_counts_consistency_across_methods(
        self, ontology_generator: OntologyGenerator, multi_type_result: EntityExtractionResult
    ):
        """Verify entity counts are consistent between histogram and type counts."""
        histogram = ontology_generator.confidence_histogram(multi_type_result, bins=5)
        counts_by_type = ontology_generator.entity_count_by_type(multi_type_result)

        # Both should have counts summing to total entities
        histogram_total = sum(histogram.values())
        counts_total = sum(counts_by_type.values())
        assert histogram_total == counts_total == len(multi_type_result.entities)

    def test_type_distribution_consistency_with_counts(
        self, ontology_generator: OntologyGenerator, multi_type_result: EntityExtractionResult
    ):
        """Verify distribution is consistent with type counts."""
        distribution = ontology_generator.entity_type_distribution(multi_type_result)
        counts_by_type = ontology_generator.entity_count_by_type(multi_type_result)

        # Keys should match
        assert set(distribution.keys()) == set(counts_by_type.keys())

        # Values should be proportional
        total = len(multi_type_result.entities)
        for type_name, count in counts_by_type.items():
            expected_freq = count / total
            actual_freq = distribution[type_name]
            assert abs(expected_freq - actual_freq) < 0.001  # Allow small rounding error
