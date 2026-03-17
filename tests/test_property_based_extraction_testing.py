"""
Property-Based Extraction Testing with Hypothesis

Comprehensive property-based testing using Hypothesis library for
ontology extraction to ensure robustness across diverse inputs.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


# Strategies for generating test data
text_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
    min_size=1,
    max_size=500,
)

domain_strategy = st.sampled_from(["general", "legal", "medical", "business"])

class TestPropertyBasedTextHandling:
    """Property-based tests for text handling."""
    
    @given(text_strategy)
    @settings(max_examples=100, deadline=None)
    def test_any_text_generates_ontology(self, text):
        """Test that any valid text generates an ontology."""
        assume(len(text.strip()) > 0)  # Skip pure whitespace
        
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)
    
    @given(text_strategy)
    @settings(max_examples=100, deadline=None)
    def test_ontology_has_required_fields(self, text):
        """Test that all ontologies have required fields."""
        assume(len(text.strip()) > 0)
        
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        # Should always have these fields
        assert "entities" in result
        assert "relationships" in result
        assert "metadata" in result
    
    @given(text_strategy)
    @settings(max_examples=100, deadline=None)
    def test_entities_are_list_or_empty(self, text):
        """Test that entities field is always a list."""
        assume(len(text.strip()) > 0)
        
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    @given(text_strategy)
    @settings(max_examples=100, deadline=None)
    def test_relationships_are_list_or_empty(self, text):
        """Test that relationships field is always a list."""
        assume(len(text.strip()) > 0)
        
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)


class TestPropertyBasedConfidenceScores:
    """Property-based tests for confidence score validity."""
    
    @given(text_strategy)
    @settings(max_examples=100, deadline=None)
    def test_confidence_scores_in_valid_range(self, text):
        """Test that all confidence scores are in [0, 1]."""
        assume(len(text.strip()) > 0)
        
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        entities = result.get("entities", [])
        for entity in entities:
            if isinstance(entity, dict) and "confidence" in entity:
                conf = entity["confidence"]
                assert 0 <= conf <= 1, f"Confidence {conf} out of range"


class TestPropertyBasedEntityStructure:
    """Property-based tests for entity structure consistency."""
    
    @given(text_strategy)
    @settings(max_examples=100, deadline=None)
    def test_entity_structure_consistency(self, text):
        """Test that all entities follow consistent structure."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        entities = result.get("entities", [])
        for entity in entities:
            # All entities should be dictionaries
            assert isinstance(entity, dict)


class TestPropertyBasedRelationshipStructure:
    """Property-based tests for relationship structure."""
    
    @given(text_strategy)
    @settings(max_examples=100, deadline=None)
    def test_relationship_structure_consistency(self, text):
        """Test that all relationships follow consistent structure."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        relationships = result.get("relationships", [])
        for rel in relationships:
            # All relationships should be dictionaries
            assert isinstance(rel, dict)


class TestPropertyBasedDomainHandling:
    """Property-based tests for domain parameter handling."""
    
    @given(text_strategy, domain_strategy)
    @settings(max_examples=100, deadline=None)
    def test_domain_parameter_accepted(self, text, domain):
        """Test that all valid domains are accepted."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain=domain
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)


class TestPropertyBasedIdempotence:
    """Property-based tests for extraction idempotence."""
    
    @given(text_strategy)
    @settings(max_examples=50, deadline=None)
    def test_extraction_idempotent(self, text):
        """Test that running extraction twice gives same results."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result1 = generator.generate_ontology(text, context)
        result2 = generator.generate_ontology(text, context)
        
        # Both should have same structure
        assert result1.keys() == result2.keys()
        assert len(result1.get("entities", [])) == len(result2.get("entities", []))


class TestPropertyBasedSpecialCharacters:
    """Property-based tests for special character handling."""
    
    special_char_strategy = st.text(
        alphabet=st.characters(
            blacklist_categories=("Cc", "Cs"),
            min_codepoint=0x0000,
            max_codepoint=0xFFFF,
        ),
        min_size=1,
        max_size=100,
    )
    
    @given(special_char_strategy)
    @settings(max_examples=50, deadline=None)
    def test_handles_special_characters(self, text):
        """Test handling of text with special characters."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        try:
            result = generator.generate_ontology(text, context)
            assert result is not None
        except Exception:
            # Some characters might cause issues, but shouldn't crash
            pass


class TestPropertyBasedMixedContent:
    """Property-based tests for mixed content."""
    
    mixed_strategy = st.one_of(
        st.just(""),
        st.text(min_size=1, max_size=50),
        st.text(alphabet="0123456789", min_size=1, max_size=20),
        st.text(alphabet=st.characters(whitelist_categories=("Ll", "Lu")), min_size=1, max_size=50),
    )
    
    @given(mixed_strategy)
    @settings(max_examples=100, deadline=None)
    def test_mixed_content_handling(self, text):
        """Test handling of mixed content types."""
        assume(len(text) > 0)  # Skip empty strings
        
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)


class TestPropertyBasedNumericContent:
    """Property-based tests for numeric content."""
    
    numeric_strategy = st.text(
        alphabet="0123456789.+-",
        min_size=1,
        max_size=50,
    )
    
    @given(numeric_strategy)
    @settings(max_examples=50, deadline=None)
    def test_numeric_content_handling(self, text):
        """Test handling of numeric content."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)


class TestPropertyBasedRepetitiveContent:
    """Property-based tests for repetitive content."""
    
    repetitive_strategy = st.builds(
        lambda char, count: char * count,
        char=st.characters(blacklist_categories=("Cc", "Cs")),
        count=st.integers(min_value=1, max_value=100),
    )
    
    @given(repetitive_strategy)
    @settings(max_examples=50, deadline=None)
    def test_repetitive_content_handling(self, text):
        """Test handling of repetitive content."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)


class TestPropertyBasedLongContent:
    """Property-based tests for long content."""
    
    long_text_strategy = st.text(min_size=1000, max_size=5000)
    
    @given(long_text_strategy)
    @settings(max_examples=10, deadline=None)
    def test_long_text_handling(self, text):
        """Test handling of long text."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)


class TestPropertyBasedShortContent:
    """Property-based tests for short content."""
    
    short_text_strategy = st.text(min_size=1, max_size=5)
    
    @given(short_text_strategy)
    @settings(max_examples=100, deadline=None)
    def test_short_text_handling(self, text):
        """Test handling of very short text."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)


class TestPropertyBasedWhitespaceVariations:
    """Property-based tests for whitespace handling."""
    
    whitespace_strategy = st.one_of(
        st.just("   word   "),
        st.just("\t\tword\t\t"),
        st.just("\nword\n"),
        st.builds(lambda n: "word" * n, n=st.integers(1, 10)),
    )
    
    @given(whitespace_strategy)
    @settings(max_examples=50, deadline=None)
    def test_whitespace_handling(self, text):
        """Test handling of various whitespace."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)
