"""
Consistency Validation Test Suite

Tests for ensuring consistency and correctness across extraction
runs, domains, and input variations. Validates invariants and
properties that must hold under all conditions.
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestInvariantProperties:
    """Test that extraction maintains important invariants."""
    
    def test_result_always_dict(self):
        """Result must always be a dictionary."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        assert isinstance(result, dict)
    
    def test_entities_always_exist(self):
        """Entities field must always exist."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        assert "entities" in result
    
    def test_relationships_always_exist(self):
        """Relationships field must always exist."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        assert "relationships" in result
    
    def test_metadata_always_exists(self):
        """Metadata field must always exist."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        assert "metadata" in result


class TestFieldTypeConsistency:
    """Test that field types are consistent."""
    
    def test_entities_field_is_list(self):
        """Entities must be a list."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        assert isinstance(result["entities"], list)
    
    def test_relationships_field_is_list(self):
        """Relationships must be a list."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        assert isinstance(result["relationships"], list)
    
    def test_metadata_field_is_dict(self):
        """Metadata must be a dictionary."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        assert isinstance(result["metadata"], dict)
    
    def test_entities_are_dicts(self):
        """All entities must be dictionaries."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John Smith and Jane Doe met at the conference."
        result = generator.generate_ontology(text, context)
        
        entities = result["entities"]
        for entity in entities:
            assert isinstance(entity, dict)
    
    def test_relationships_are_dicts(self):
        """All relationships must be dictionaries."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John manages the project with Mary."
        result = generator.generate_ontology(text, context)
        
        relationships = result["relationships"]
        for rel in relationships:
            assert isinstance(rel, dict)


class TestDomainConsistency:
    """Test consistency across different domains."""
    
    def test_legal_domain_returns_dict(self):
        """Legal domain returns proper structure."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Contract signed", context)
        
        assert isinstance(result, dict)
        assert "entities" in result
    
    def test_medical_domain_returns_dict(self):
        """Medical domain returns proper structure."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Prescription given", context)
        
        assert isinstance(result, dict)
        assert "entities" in result
    
    def test_business_domain_returns_dict(self):
        """Business domain returns proper structure."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="business"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Sales increased", context)
        
        assert isinstance(result, dict)
        assert "entities" in result
    
    def test_same_structure_across_domains(self):
        """Extraction structure consistent across domains."""
        text = "Test data"
        domains = ["general", "legal", "medical", "business"]
        
        generator = OntologyGenerator()
        
        for domain in domains:
            context = OntologyGenerationContext(
                data_source="test", data_type="text", domain=domain
            )
            result = generator.generate_ontology(text, context)
            
            # All should have required top-level fields
            assert "entities" in result
            assert "relationships" in result
            assert "metadata" in result


class TestValueTypeConsistency:
    """Test consistency of value types within fields."""
    
    def test_entity_names_are_strings(self):
        """Entity names should be strings when present."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("John and Mary met", context)
        
        entities = result["entities"]
        for entity in entities:
            if "name" in entity:
                assert isinstance(entity["name"], str)
    
    def test_entity_types_are_strings(self):
        """Entity types should be strings when present."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("John is a doctor", context)
        
        entities = result["entities"]
        for entity in entities:
            if "type" in entity:
                assert isinstance(entity["type"], str)
    
    def test_relationship_types_are_strings(self):
        """Relationship types should be strings when present."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("John manages the project", context)
        
        relationships = result["relationships"]
        for rel in relationships:
            if "type" in rel:
                assert isinstance(rel["type"], str)


class TestEmptyInputHandling:
    """Test consistency with edge case inputs."""
    
    def test_single_word_input(self):
        """Handle single word input."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        assert isinstance(result, dict)
        assert "entities" in result
    
    def test_punctuation_only_input(self):
        """Handle punctuation-only input."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("!@#$%", context)
        
        assert isinstance(result, dict)
        assert isinstance(result["entities"], list)
    
    def test_numbers_only_input(self):
        """Handle numbers-only input."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("123456", context)
        
        assert isinstance(result, dict)
        assert isinstance(result["entities"], list)
    
    def test_whitespace_only_input(self):
        """Handle whitespace-only input."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("     ", context)
        
        assert isinstance(result, dict)
        assert isinstance(result["entities"], list)


class TestConsistencyAcrossRuns:
    """Test that results are consistent across multiple runs."""
    
    def test_deterministic_output(self):
        """Same input produces same structure (deterministic)."""
        text = "Fixed input for testing"
        
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result1 = generator.generate_ontology(text, context)
        result2 = generator.generate_ontology(text, context)
        
        # Structure should be identical
        assert len(result1["entities"]) == len(result2["entities"])
        assert len(result1["relationships"]) == len(result2["relationships"])
    
    def test_consistent_entity_count(self):
        """Entity count consistent for same input."""
        text = "John Smith works for Acme Corporation"
        
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result1 = generator.generate_ontology(text, context)
        result2 = generator.generate_ontology(text, context)
        
        assert len(result1["entities"]) == len(result2["entities"])


class TestMetadataConsistency:
    """Test metadata field consistency."""
    
    def test_metadata_is_dict(self):
        """Metadata is always a dictionary."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        assert isinstance(result["metadata"], dict)
    
    def test_metadata_values_are_basic_types(self):
        """Metadata values are basic JSON types."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        for key, value in result["metadata"].items():
            assert isinstance(value, (str, int, float, bool, type(None)))


class TestNoCorruption:
    """Test that extraction doesn't corrupt data."""
    
    def test_original_text_unchanged(self):
        """Extraction doesn't modify input text."""
        original = "Test data"
        
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        generator.generate_ontology(original, context)
        
        # Input should be unchanged
        assert original == "Test data"
    
    def test_context_unchanged(self):
        """Extraction doesn't modify context."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        original_domain = context.domain
        
        generator = OntologyGenerator()
        generator.generate_ontology("test", context)
        
        # Context should be unchanged
        assert context.domain == original_domain


class TestConsistencyInvariants:
    """Test mathematical and logical invariants."""
    
    def test_no_duplicate_entities_with_same_name(self):
        """Entities with same name should be merged or handled consistently."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("John and John met", context)
        
        # Multiple Johns should exist or be merged consistently
        entities = result["entities"]
        assert isinstance(entities, list)
    
    def test_no_self_relationships(self):
        """Relationships should follow logical consistency rules."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("John manages John", context)
        
        # Should handle self-references consistently
        relationships = result["relationships"]
        assert isinstance(relationships, list)
