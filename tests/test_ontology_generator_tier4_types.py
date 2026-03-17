"""TIER 4 type annotation tests for OntologyGenerator advanced methods.

Tests for confidence_quartiles, relationship_density_by_type, entity_id_prefix_groups,
relationship_source_degree_distribution, and result_summary_dict methods with their
specific type contracts.
"""
import pytest
from typing import List

# OntologyGenerator and result types
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    Entity,
    Relationship,
    EntityExtractionResult,
)

# Type contracts
from ipfs_datasets_py.optimizers.graphrag.query_optimizer_types import (
    ConfidenceQuartiles,
    RelationshipDensityByType,
    EntityIDPrefixGroups,
    RelationshipSourceDegreeDistribution,
    ResultSummaryDict,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture()
def ontology_generator() -> OntologyGenerator:
    """Create an OntologyGenerator instance."""
    return OntologyGenerator()


@pytest.fixture()
def empty_result() -> EntityExtractionResult:
    """Create an empty EntityExtractionResult."""
    return EntityExtractionResult(entities=[], relationships=[], confidence=0.0)


@pytest.fixture()
def simple_result() -> EntityExtractionResult:
    """Create a simple result with 5 entities and varied confidence levels."""
    entities = [
        Entity(id="alice", text="Alice", type="Person", confidence=0.95),
        Entity(id="bob", text="Bob", type="Person", confidence=0.75),
        Entity(id="charlie", text="Charlie", type="Person", confidence=0.60),
        Entity(id="david", text="David", type="Person", confidence=0.50),
        Entity(id="eve", text="Eve", type="Person", confidence=0.40),
    ]
    relationships = [
        Relationship(id="r1", source_id="alice", target_id="bob", type="knows"),
        Relationship(id="r2", source_id="bob", target_id="charlie", type="knows"),
        Relationship(id="r3", source_id="alice", target_id="charlie", type="knows"),
        Relationship(id="r4", source_id="alice", target_id="david", type="knows"),
        Relationship(id="r5", source_id="charlie", target_id="eve", type="manages"),
    ]
    return EntityExtractionResult(entities=entities, relationships=relationships, confidence=0.64)


@pytest.fixture()
def complex_result() -> EntityExtractionResult:
    """Create a complex result with mixed entity types and various confidence."""
    entities = [
        Entity(id="acme_corp", text="ACME Corp", type="Organization", confidence=0.92),
        Entity(id="alice", text="Alice Smith", type="Person", confidence=0.88),
        Entity(id="alice_email", text="alice@acme.com", type="Email", confidence=0.95),
        Entity(id="new_york", text="New York", type="Location", confidence=0.89),
        Entity(id="sep_2024", text="September 2024", type="Date", confidence=0.75),
        Entity(id="john", text="John Doe", type="Person", confidence=0.82),
        Entity(id="project_x", text="Project X", type="Project", confidence=0.70),
    ]
    relationships = [
        Relationship(id="r1", source_id="alice", target_id="acme_corp", type="works_for"),
        Relationship(id="r2", source_id="alice", target_id="alice_email", type="has_email"),
        Relationship(id="r3", source_id="acme_corp", target_id="new_york", type="located_in"),
        Relationship(id="r4", source_id="alice", target_id="project_x", type="assigned_to"),
        Relationship(id="r5", source_id="john", target_id="project_x", type="assigned_to"),
        Relationship(id="r6", source_id="project_x", target_id="sep_2024", type="deadline"),
    ]
    return EntityExtractionResult(entities=entities, relationships=relationships, confidence=0.85)


# ============================================================================
# Tests: confidence_quartiles
# ============================================================================


class TestConfidenceQuartiles:
    """Tests for OntologyGenerator.confidence_quartiles() return type."""

    def test_returns_confidence_quartiles_type(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify return type is ConfidenceQuartiles (Dict with q1, q2, q3)."""
        result = ontology_generator.confidence_quartiles(simple_result)
        assert isinstance(result, dict)
        # Check all three quartile keys are present
        assert "q1" in result
        assert "q2" in result
        assert "q3" in result
        # All values should be floats
        assert all(isinstance(v, float) for v in result.values())

    def test_quartiles_values_in_valid_range(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify all quartile values are in [0.0, 1.0]."""
        result = ontology_generator.confidence_quartiles(simple_result)
        assert all(0.0 <= v <= 1.0 for v in result.values())

    def test_quartiles_ordering(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify q1 <= q2 <= q3 (quartile ordering)."""
        result = ontology_generator.confidence_quartiles(simple_result)
        assert result["q1"] <= result["q2"] <= result["q3"]

    def test_quartiles_empty_result(
        self, ontology_generator: OntologyGenerator, empty_result: EntityExtractionResult
    ):
        """Verify quartiles handles empty results."""
        result = ontology_generator.confidence_quartiles(empty_result)
        assert isinstance(result, dict)
        # Empty result should return all 0.0
        assert result.get("q1") == 0.0
        assert result.get("q2") == 0.0
        assert result.get("q3") == 0.0

    def test_quartiles_single_entity(
        self, ontology_generator: OntologyGenerator
    ):
        """Verify quartiles with single entity all equal."""
        single = EntityExtractionResult(
            entities=[Entity(id="e1", text="test", type="Test", confidence=0.75)],
            relationships=[],
            confidence=0.75
        )
        result = ontology_generator.confidence_quartiles(single)
        # With single value, all quartiles should equal that value
        assert result["q1"] == 0.75
        assert result["q2"] == 0.75
        assert result["q3"] == 0.75


# ============================================================================
# Tests: relationship_density_by_type
# ============================================================================


class TestRelationshipDensityByType:
    """Tests for OntologyGenerator.relationship_density_by_type() return type."""

    def test_returns_relationship_density_by_type(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify return type is RelationshipDensityByType (Dict[str, float])."""
        result = ontology_generator.relationship_density_by_type(simple_result)
        assert isinstance(result, dict)
        # All keys are strings (relationship types)
        assert all(isinstance(k, str) for k in result.keys())
        # All values are floats (densities)
        assert all(isinstance(v, float) for v in result.values())

    def test_density_values_sum_to_one(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify density values sum to approximately 1.0."""
        result = ontology_generator.relationship_density_by_type(simple_result)
        total = sum(result.values())
        assert 0.99 <= total <= 1.01  # Account for floating point rounding

    def test_density_values_in_valid_range(
        self, ontology_generator: OntologyGenerator, complex_result: EntityExtractionResult
    ):
        """Verify all density values are in [0.0, 1.0]."""
        result = ontology_generator.relationship_density_by_type(complex_result)
        assert all(0.0 <= v <= 1.0 for v in result.values())

    def test_density_empty_result(
        self, ontology_generator: OntologyGenerator, empty_result: EntityExtractionResult
    ):
        """Verify density handles empty results."""
        result = ontology_generator.relationship_density_by_type(empty_result)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_density_single_type(
        self, ontology_generator: OntologyGenerator
    ):
        """Verify all relationships of single type have density 1.0."""
        single_type = EntityExtractionResult(
            entities=[
                Entity(id="e1", text="a", type="Test", confidence=0.5),
                Entity(id="e2", text="b", type="Test", confidence=0.5),
            ],
            relationships=[
                Relationship(id="r1", source_id="e1", target_id="e2", type="only_type"),
                Relationship(id="r2", source_id="e2", target_id="e1", type="only_type"),
            ],
            confidence=0.5
        )
        result = ontology_generator.relationship_density_by_type(single_type)
        assert result["only_type"] == 1.0


# ============================================================================
# Tests: entity_id_prefix_groups
# ============================================================================


class TestEntityIDPrefixGroups:
    """Tests for OntologyGenerator.entity_id_prefix_groups() return type."""

    def test_returns_entity_id_prefix_groups_type(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify return type is EntityIDPrefixGroups (Dict[str, List[str]])."""
        result = ontology_generator.entity_id_prefix_groups(simple_result, prefix_len=1)
        assert isinstance(result, dict)
        # Keys are strings (prefixes)
        assert all(isinstance(k, str) for k in result.keys())
        # Values are lists
        assert all(isinstance(v, list) for v in result.values())
        # List items are strings (entity IDs)
        for id_list in result.values():
            assert all(isinstance(eid, str) for eid in id_list)

    def test_prefix_grouping_correct(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify entities are grouped by correct prefix."""
        result = ontology_generator.entity_id_prefix_groups(simple_result, prefix_len=1)
        # Should have grouping by first character
        expected_groups = {
            "a": ["alice"],
            "b": ["bob"],
            "c": ["charlie"],
            "d": ["david"],
            "e": ["eve"],
        }
        for prefix, ids in expected_groups.items():
            assert set(result[prefix]) == set(ids)

    def test_prefix_len_variable(
        self, ontology_generator: OntologyGenerator, complex_result: EntityExtractionResult
    ):
        """Verify prefix_len parameter affects grouping."""
        result_1 = ontology_generator.entity_id_prefix_groups(complex_result, prefix_len=1)
        result_5 = ontology_generator.entity_id_prefix_groups(complex_result, prefix_len=5)
        # Different prefix lengths should create different groupings
        assert len(result_1) <= len(result_5)

    def test_prefix_groups_empty_result(
        self, ontology_generator: OntologyGenerator, empty_result: EntityExtractionResult
    ):
        """Verify prefix groups handles empty results."""
        result = ontology_generator.entity_id_prefix_groups(empty_result, prefix_len=1)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_prefix_all_ids_present(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify all entity IDs appear in groups."""
        result = ontology_generator.entity_id_prefix_groups(simple_result, prefix_len=1)
        all_ids = []
        for id_list in result.values():
            all_ids.extend(id_list)
        expected_ids = {e.id for e in simple_result.entities}
        assert set(all_ids) == expected_ids


# ============================================================================
# Tests: relationship_source_degree_distribution
# ============================================================================


class TestRelationshipSourceDegreeDistribution:
    """Tests for OntologyGenerator.relationship_source_degree_distribution() return type."""

    def test_returns_relationship_source_degree_distribution(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify return type is RelationshipSourceDegreeDistribution (Dict[str, int])."""
        result = ontology_generator.relationship_source_degree_distribution(simple_result)
        assert isinstance(result, dict)
        # All keys are strings (source entity IDs)
        assert all(isinstance(k, str) for k in result.keys())
        # All values are integers (out-degrees)
        assert all(isinstance(v, int) for v in result.values())

    def test_degree_totals_match_relationship_count(
        self, ontology_generator: OntologyGenerator, complex_result: EntityExtractionResult
    ):
        """Verify out-degrees sum to total relationship count."""
        result = ontology_generator.relationship_source_degree_distribution(complex_result)
        total_degree = sum(result.values())
        assert total_degree == len(complex_result.relationships)

    def test_degree_values_all_positive(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify all degree values are positive integers."""
        result = ontology_generator.relationship_source_degree_distribution(simple_result)
        assert all(v > 0 for v in result.values())

    def test_degree_empty_result(
        self, ontology_generator: OntologyGenerator, empty_result: EntityExtractionResult
    ):
        """Verify degree distribution handles empty results."""
        result = ontology_generator.relationship_source_degree_distribution(empty_result)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_degree_correct_per_source(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify out-degree for each source is correct."""
        result = ontology_generator.relationship_source_degree_distribution(simple_result)
        # Count expected degrees from relationships
        expected = {}
        for rel in simple_result.relationships:
            src = rel.source_id
            expected[src] = expected.get(src, 0) + 1
        assert result == expected


# ============================================================================
# Tests: result_summary_dict
# ============================================================================


class TestResultSummaryDict:
    """Tests for OntologyGenerator.result_summary_dict() return type."""

    def test_returns_result_summary_dict_type(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify return type has all required ResultSummaryDict fields."""
        result = ontology_generator.result_summary_dict(simple_result)
        assert isinstance(result, dict)
        # Check all required keys are present
        required_keys = {
            "entity_count", "relationship_count", "unique_types",
            "mean_confidence", "min_confidence", "max_confidence",
            "has_errors", "error_count"
        }
        assert set(result.keys()) == required_keys

    def test_summary_field_types(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify field types are correct."""
        result = ontology_generator.result_summary_dict(simple_result)
        assert isinstance(result["entity_count"], int)
        assert isinstance(result["relationship_count"], int)
        assert isinstance(result["unique_types"], int)
        assert isinstance(result["mean_confidence"], float)
        assert isinstance(result["min_confidence"], float)
        assert isinstance(result["max_confidence"], float)
        assert isinstance(result["has_errors"], bool)
        assert isinstance(result["error_count"], int)

    def test_summary_counts_correctness(
        self, ontology_generator: OntologyGenerator, complex_result: EntityExtractionResult
    ):
        """Verify counts match actual result data."""
        result = ontology_generator.result_summary_dict(complex_result)
        assert result["entity_count"] == len(complex_result.entities)
        assert result["relationship_count"] == len(complex_result.relationships)
        # Verify unique types
        expected_types = {e.type for e in complex_result.entities}
        assert result["unique_types"] == len(expected_types)

    def test_summary_confidence_ranges(
        self, ontology_generator: OntologyGenerator, simple_result: EntityExtractionResult
    ):
        """Verify confidence values are in valid ranges."""
        result = ontology_generator.result_summary_dict(simple_result)
        # All should be in [0.0, 1.0]
        assert 0.0 <= result["mean_confidence"] <= 1.0
        assert 0.0 <= result["min_confidence"] <= 1.0
        assert 0.0 <= result["max_confidence"] <= 1.0
        # min <= mean <= max
        assert result["min_confidence"] <= result["mean_confidence"] <= result["max_confidence"]

    def test_summary_empty_result(
        self, ontology_generator: OntologyGenerator, empty_result: EntityExtractionResult
    ):
        """Verify summary handles empty results."""
        result = ontology_generator.result_summary_dict(empty_result)
        assert result["entity_count"] == 0
        assert result["relationship_count"] == 0
        assert result["unique_types"] == 0
        assert result["mean_confidence"] == 0.0
        assert result["min_confidence"] == 0.0
        assert result["max_confidence"] == 0.0
        assert result["has_errors"] == False
        assert result["error_count"] == 0


# ============================================================================
# Integration Tests: TIER 4 Methods Together
# ============================================================================


class TestTIER4Integration:
    """Integration tests validating multiple TIER 4 methods together."""

    def test_all_tier4_methods_run_successfully(
        self, ontology_generator: OntologyGenerator, complex_result: EntityExtractionResult
    ):
        """Verify all 5 TIER 4 methods can be called on the same result."""
        # This verifies no type/implementation conflicts
        q = ontology_generator.confidence_quartiles(complex_result)
        d = ontology_generator.relationship_density_by_type(complex_result)
        p = ontology_generator.entity_id_prefix_groups(complex_result, prefix_len=2)
        s = ontology_generator.relationship_source_degree_distribution(complex_result)
        sm = ontology_generator.result_summary_dict(complex_result)

        # All should have results
        assert isinstance(q, dict) and len(q) == 3
        assert isinstance(d, dict) and len(d) > 0
        assert isinstance(p, dict) and len(p) > 0
        assert isinstance(s, dict) and len(s) > 0
        assert isinstance(sm, dict) and len(sm) == 8

    def test_summary_and_density_consistency(
        self, ontology_generator: OntologyGenerator, complex_result: EntityExtractionResult
    ):
        """Verify summary relationship count matches density relationship total."""
        summary = ontology_generator.result_summary_dict(complex_result)
        density = ontology_generator.relationship_density_by_type(complex_result)

        # Relationship count should match
        if len(complex_result.relationships) > 0:
            assert summary["relationship_count"] == len(complex_result.relationships)
            # Density keys should match relationship types in result
            rel_types = {r.type for r in complex_result.relationships}
            assert set(density.keys()) == rel_types

    def test_quartiles_against_summary_confidence(
        self, ontology_generator: OntologyGenerator, complex_result: EntityExtractionResult
    ):
        """Verify quartiles and summary confidence values are compatible."""
        quartiles = ontology_generator.confidence_quartiles(complex_result)
        summary = ontology_generator.result_summary_dict(complex_result)

        # Median (q2) should be between min and max confidence
        if len(complex_result.entities) > 0:
            assert summary["min_confidence"] <= quartiles["q2"] <= summary["max_confidence"]
            # Q2 is median, so mean might be different but both in valid range
            assert 0.0 <= quartiles["q2"] <= 1.0
