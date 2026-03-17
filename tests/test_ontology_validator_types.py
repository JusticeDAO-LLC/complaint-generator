"""Tests for OntologyValidator type contracts and merge suggestion functionality.

Tests the MergeEvidenceDict TypedDict contract and validates OntologyValidator
methods for correct struct structure, evidence field types, and merge logic.
"""
import pytest
from typing import Dict, Any

# OntologyValidator and types
from ipfs_datasets_py.optimizers.graphrag.ontology_validator import (
    OntologyValidator,
    MergeSuggestion,
)

# Type contracts
from ipfs_datasets_py.optimizers.graphrag.query_optimizer_types import MergeEvidenceDict


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture()
def validator() -> OntologyValidator:
    """Create an OntologyValidator instance with default settings."""
    return OntologyValidator(min_name_similarity=0.75)


@pytest.fixture()
def simple_ontology() -> Dict[str, Any]:
    """Create a simple ontology with potential duplicates."""
    return {
        "entities": [
            {"id": "e1", "text": "Alice Smith", "type": "Person", "confidence": 0.9},
            {"id": "e2", "text": "Alice Smyth", "type": "Person", "confidence": 0.85},
            {"id": "e3", "text": "Bob Johnson", "type": "Person", "confidence": 0.92},
        ],
        "relationships": []
    }


@pytest.fixture()
def complex_ontology() -> Dict[str, Any]:
    """Create a complex ontology with multiple entity types."""
    return {
        "entities": [
            {"id": "e1", "text": "ACME Corp", "type": "Organization", "confidence": 0.92},
            {"id": "e2", "text": "ACME Corporation", "type": "Organization", "confidence": 0.90},
            {"id": "e3", "text": "Alice Smith", "type": "Person", "confidence": 0.88},
            {"id": "e4", "text": "Alice Smith", "type": "Person", "confidence": 0.87},  # Exact duplicate
            {"id": "e5", "text": "New York", "type": "Location", "confidence": 0.89},
            {"id": "e6", "text": "NYC", "type": "Location", "confidence": 0.75},
        ],
        "relationships": [
            {"id": "r1", "source_id": "e3", "target_id": "e1", "type": "works_for"},
            {"id": "r2", "source_id": "e4", "target_id": "e2", "type": "works_for"},
        ]
    }


@pytest.fixture()
def empty_ontology() -> Dict[str, Any]:
    """Create an empty ontology."""
    return {"entities": [], "relationships": []}


# ============================================================================
# Tests: MergeSuggestion Type Contract
# ============================================================================


class TestMergeSuggestionType:
    """Tests for MergeSuggestion dataclass and MergeEvidenceDict type."""

    def test_merge_suggestion_has_correct_fields(self, validator: OntologyValidator, simple_ontology: Dict[str, Any]):
        """Verify MergeSuggestion has all required fields."""
        suggestions = validator.suggest_entity_merges(simple_ontology, threshold=0.7)
        
        assert len(suggestions) > 0, "Should have at least one merge suggestion"
        
        suggestion = suggestions[0]
        assert isinstance(suggestion, MergeSuggestion)
        assert hasattr(suggestion, "entity1_id")
        assert hasattr(suggestion, "entity2_id")
        assert hasattr(suggestion, "similarity_score")
        assert hasattr(suggestion, "reason")
        assert hasattr(suggestion, "evidence")

    def test_evidence_dict_has_required_fields(self, validator: OntologyValidator, simple_ontology: Dict[str, Any]):
        """Verify evidence dict has MergeEvidenceDict structure."""
        suggestions = validator.suggest_entity_merges(simple_ontology, threshold=0.7)
        
        assert len(suggestions) > 0
        evidence = suggestions[0].evidence
        
        # Check all required MergeEvidenceDict fields are present
        assert "name_similarity" in evidence
        assert "type_match" in evidence
        assert "type1" in evidence
        assert "type2" in evidence
        assert "confidence1" in evidence
        assert "confidence2" in evidence
        assert "confidence_difference" in evidence

    def test_evidence_field_types(self, validator: OntologyValidator, simple_ontology: Dict[str, Any]):
        """Verify evidence field value types match MergeEvidenceDict."""
        suggestions = validator.suggest_entity_merges(simple_ontology, threshold=0.7)
        
        assert len(suggestions) > 0
        evidence = suggestions[0].evidence
        
        # Type validation
        assert isinstance(evidence["name_similarity"], float)
        assert isinstance(evidence["type_match"], bool)
        assert isinstance(evidence["type1"], str)
        assert isinstance(evidence["type2"], str)
        assert isinstance(evidence["confidence1"], float)
        assert isinstance(evidence["confidence2"], float)
        assert isinstance(evidence["confidence_difference"], float)

    def test_similarity_score_in_valid_range(self, validator: OntologyValidator, simple_ontology: Dict[str, Any]):
        """Verify similarity_score is in [0.0, 1.0]."""
        suggestions = validator.suggest_entity_merges(simple_ontology, threshold=0.0)
        
        for suggestion in suggestions:
            assert 0.0 <= suggestion.similarity_score <= 1.0

    def test_repr_method(self, validator: OntologyValidator, simple_ontology: Dict[str, Any]):
        """Verify __repr__ method works correctly."""
        suggestions = validator.suggest_entity_merges(simple_ontology, threshold=0.7)
        
        assert len(suggestions) > 0
        repr_str = repr(suggestions[0])
        
        assert "MergeSuggestion(" in repr_str
        assert "score=" in repr_str
        assert "reason=" in repr_str


# ============================================================================
# Tests: suggest_entity_merges Method
# ============================================================================


class TestSuggestEntityMerges:
    """Tests for OntologyValidator.suggest_entity_merges() method."""

    def test_returns_list_of_merge_suggestions(self, validator: OntologyValidator, simple_ontology: Dict[str, Any]):
        """Verify method returns list of MergeSuggestion objects."""
        result = validator.suggest_entity_merges(simple_ontology, threshold=0.7)
        
        assert isinstance(result, list)
        assert all(isinstance(s, MergeSuggestion) for s in result)

    def test_threshold_filters_suggestions(self, validator: OntologyValidator, simple_ontology: Dict[str, Any]):
        """Verify threshold parameter filters suggestions correctly."""
        low_threshold = validator.suggest_entity_merges(simple_ontology, threshold=0.5)
        high_threshold = validator.suggest_entity_merges(simple_ontology, threshold=0.9)
        
        # Lower threshold should have more or equal suggestions
        assert len(low_threshold) >= len(high_threshold)
        
        # All high threshold suggestions should have score >= 0.9
        for suggestion in high_threshold:
            assert suggestion.similarity_score >= 0.9

    def test_max_suggestions_limit(self, validator: OntologyValidator, complex_ontology: Dict[str, Any]):
        """Verify max_suggestions parameter limits output."""
        all_suggestions = validator.suggest_entity_merges(complex_ontology, threshold=0.5, max_suggestions=None)
        limited_suggestions = validator.suggest_entity_merges(complex_ontology, threshold=0.5, max_suggestions=2)
        
        assert len(limited_suggestions) <= 2
        assert len(limited_suggestions) <= len(all_suggestions)

    def test_sorted_by_similarity_descending(self, validator: OntologyValidator, complex_ontology: Dict[str, Any]):
        """Verify suggestions are sorted by similarity score (descending)."""
        suggestions = validator.suggest_entity_merges(complex_ontology, threshold=0.5)
        
        if len(suggestions) > 1:
            scores = [s.similarity_score for s in suggestions]
            assert scores == sorted(scores, reverse=True)

    def test_empty_ontology_returns_empty_list(self, validator: OntologyValidator, empty_ontology: Dict[str, Any]):
        """Verify empty ontology returns empty suggestions list."""
        suggestions = validator.suggest_entity_merges(empty_ontology, threshold=0.5)
        
        assert isinstance(suggestions, list)
        assert len(suggestions) == 0

    def test_exact_duplicate_names_high_score(self, validator: OntologyValidator):
        """Verify exact duplicate entity names get high similarity scores."""
        ontology = {
            "entities": [
                {"id": "e1", "text": "Alice Smith", "type": "Person", "confidence": 0.9},
                {"id": "e2", "text": "Alice Smith", "type": "Person", "confidence": 0.88},
            ],
            "relationships": []
        }
        
        suggestions = validator.suggest_entity_merges(ontology, threshold=0.5)
        
        assert len(suggestions) > 0
        # Exact match should have very high score (close to 1.0)
        assert suggestions[0].similarity_score >= 0.9

    def test_different_types_lower_score(self, validator: OntologyValidator):
        """Verify entities with different types get lower similarity scores."""
        ontology = {
            "entities": [
                {"id": "e1", "text": "New York", "type": "Location", "confidence": 0.9},
                {"id": "e2", "text": "New York", "type": "Organization", "confidence": 0.9},
            ],
            "relationships": []
        }
        
        suggestions = validator.suggest_entity_merges(ontology, threshold=0.5)
        
        if len(suggestions) > 0:
            # Type mismatch should reduce score (type contributes 30%)
            evidence = suggestions[0].evidence
            assert evidence["type_match"] is False
            # Even with exact name match, different types reduce overall score
            assert suggestions[0].similarity_score < 1.0


# ============================================================================
# Tests: Evidence Structure Validation
# ============================================================================


class TestEvidenceStructure:
    """Tests for evidence dict structure in merge suggestions."""

    def test_name_similarity_calculation(self):
        """Verify name_similarity field is correctly calculated."""
        # Use lower min_name_similarity to test calculation
        validator = OntologyValidator(min_name_similarity=0.5)
        ontology = {
            "entities": [
                {"id": "e1", "text": "ACME Corp", "type": "Organization", "confidence": 0.9},
                {"id": "e2", "text": "ACME Corporation", "type": "Organization", "confidence": 0.9},
            ],
            "relationships": []
        }
        
        suggestions = validator.suggest_entity_merges(ontology, threshold=0.5)
        
        assert len(suggestions) > 0
        evidence = suggestions[0].evidence
        
        # Should be > 0.5 for similar names
        assert evidence["name_similarity"] > 0.5
        # Should be < 1.0 since not exact match
        assert evidence["name_similarity"] < 1.0

    def test_type_match_boolean(self, validator: OntologyValidator, simple_ontology: Dict[str, Any]):
        """Verify type_match is a boolean."""
        suggestions = validator.suggest_entity_merges(simple_ontology, threshold=0.5)
        
        for suggestion in suggestions:
            assert isinstance(suggestion.evidence["type_match"], bool)

    def test_confidence_difference_calculation(self, validator: OntologyValidator):
        """Verify confidence_difference is abs(conf1 - conf2)."""
        ontology = {
            "entities": [
                {"id": "e1", "text": "Alice", "type": "Person", "confidence": 0.9},
                {"id": "e2", "text": "Alice", "type": "Person", "confidence": 0.7},
            ],
            "relationships": []
        }
        
        suggestions = validator.suggest_entity_merges(ontology, threshold=0.5)
        
        assert len(suggestions) > 0
        evidence = suggestions[0].evidence
        
        # abs(0.9 - 0.7) = 0.2
        assert abs(evidence["confidence_difference"] - 0.2) < 0.01

    def test_type_fields_populated(self, validator: OntologyValidator, complex_ontology: Dict[str, Any]):
        """Verify type1 and type2 fields contain entity type strings."""
        suggestions = validator.suggest_entity_merges(complex_ontology, threshold=0.5)
        
        for suggestion in suggestions:
            evidence = suggestion.evidence
            assert isinstance(evidence["type1"], str)
            assert isinstance(evidence["type2"], str)
            assert len(evidence["type1"]) > 0
            assert len(evidence["type2"]) > 0


# ============================================================================
# Tests: Validator Error Handling
# ============================================================================


class TestValidatorErrorHandling:
    """Tests for OntologyValidator error handling."""

    def test_invalid_ontology_type_raises_error(self, validator: OntologyValidator):
        """Verify non-dict ontology raises ValueError."""
        with pytest.raises(ValueError, match="ontology must be a dictionary"):
            validator.suggest_entity_merges("not a dict", threshold=0.5)

    def test_invalid_threshold_raises_error(self, validator: OntologyValidator, simple_ontology: Dict[str, Any]):
        """Verify invalid threshold raises ValueError."""
        with pytest.raises(ValueError, match="threshold must be between 0.0 and 1.0"):
            validator.suggest_entity_merges(simple_ontology, threshold=1.5)
        
        with pytest.raises(ValueError, match="threshold must be between 0.0 and 1.0"):
            validator.suggest_entity_merges(simple_ontology, threshold=-0.1)

    def test_missing_entities_key_handled_gracefully(self, validator: OntologyValidator):
        """Verify missing 'entities' key is handled gracefully with empty list."""
        ontology = {"relationships": []}
        
        # Should return empty list, not raise error (implementation uses .get("entities", []))
        suggestions = validator.suggest_entity_merges(ontology, threshold=0.5)
        assert suggestions == []

    def test_non_list_entities_raises_error(self, validator: OntologyValidator):
        """Verify non-list entities value raises ValueError."""
        ontology = {"entities": "not a list", "relationships": []}
        
        with pytest.raises(ValueError, match="must be a list"):
            validator.suggest_entity_merges(ontology, threshold=0.5)


# ============================================================================
# Tests: Validator Configuration
# ============================================================================


class TestValidatorConfiguration:
    """Tests for OntologyValidator initialization and configuration."""

    def test_default_min_name_similarity(self):
        """Verify default min_name_similarity is set correctly."""
        validator = OntologyValidator()
        assert validator.min_name_similarity == 0.75

    def test_custom_min_name_similarity(self):
        """Verify custom min_name_similarity can be set."""
        validator = OntologyValidator(min_name_similarity=0.9)
        assert validator.min_name_similarity == 0.9

    def test_min_name_similarity_filters_suggestions(self):
        """Verify min_name_similarity parameter filters low-similarity pairs."""
        ontology = {
            "entities": [
                {"id": "e1", "text": "ACME Corp", "type": "Organization", "confidence": 0.9},
                {"id": "e2", "text": "ACME Corporation", "type": "Organization", "confidence": 0.9},
                {"id": "e3", "text": "XYZ Inc", "type": "Organization", "confidence": 0.9},
            ],
            "relationships": []
        }
        
        strict_validator = OntologyValidator(min_name_similarity=0.9)
        lenient_validator = OntologyValidator(min_name_similarity=0.5)
        
        strict_suggestions = strict_validator.suggest_entity_merges(ontology, threshold=0.5)
        lenient_suggestions = lenient_validator.suggest_entity_merges(ontology, threshold=0.5)
        
        # Lenient validator should have more or equal suggestions
        assert len(lenient_suggestions) >= len(strict_suggestions)


# ============================================================================
# Integration Tests
# ============================================================================


class TestValidatorIntegration:
    """Integration tests for OntologyValidator with realistic scenarios."""

    def test_realistic_merge_workflow(self, validator: OntologyValidator):
        """Test a realistic workflow of finding and processing merge suggestions."""
        ontology = {
            "entities": [
                {"id": "e1", "text": "Apple Inc.", "type": "Organization", "confidence": 0.95},
                {"id": "e2", "text": "Apple Inc", "type": "Organization", "confidence": 0.92},
                {"id": "e3", "text": "Steve Jobs", "type": "Person", "confidence": 0.90},
                {"id": "e4", "text": "Steve P. Jobs", "type": "Person", "confidence": 0.88},
                {"id": "e5", "text": "Cupertino", "type": "Location", "confidence": 0.85},
            ],
            "relationships": [
                {"id": "r1", "source_id": "e3", "target_id": "e1", "type": "founded"},
                {"id": "r2", "source_id": "e1", "target_id": "e5", "type": "located_in"},
            ]
        }
        
        # Get top 3 merge suggestions
        suggestions = validator.suggest_entity_merges(ontology, threshold=0.7, max_suggestions=3)
        
        # Should have suggestions
        assert len(suggestions) > 0
        
        # All should be valid MergeSuggestion objects
        for suggestion in suggestions:
            assert isinstance(suggestion, MergeSuggestion)
            assert isinstance(suggestion.evidence, dict)
            assert 0.7 <= suggestion.similarity_score <= 1.0
            assert len(suggestion.reason) > 0

    def test_no_false_positives_different_entities(self, validator: OntologyValidator):
        """Verify validator doesn't suggest merging clearly different entities."""
        ontology = {
            "entities": [
                {"id": "e1", "text": "Apple Inc", "type": "Organization", "confidence": 0.95},
                {"id": "e2", "text": "Orange Juice", "type": "Product", "confidence": 0.90},
                {"id": "e3", "text": "Microsoft", "type": "Organization", "confidence": 0.92},
            ],
            "relationships": []
        }
        
        suggestions = validator.suggest_entity_merges(ontology, threshold=0.8)
        
        # Should have no high-confidence suggestions for completely different entities
        for suggestion in suggestions:
            # If there are any suggestions, they should have different types or low name similarity
            evidence = suggestion.evidence
            if evidence["type_match"]:
                # Same type entities should have very low name similarity
                assert evidence["name_similarity"] < 0.9
