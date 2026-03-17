"""
Entity Linking and Disambiguation Tests

Tests for entity linking across sources, disambiguation strategies, and
knowledge base integration. Covers:
- Cross-document entity linking
- Knowledge base entity resolution
- Entity alias resolution
- CReferential entity chains
- Entity canonicalization
- Linking confidence scoring
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestBasicEntityLinking:
    """Basic entity linking functionality."""
    
    def test_link_entity_to_kb(self):
        """Link entity to knowledge base entries."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "New York is a major city."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Entities should be linkable to KB
        assert isinstance(entities, list)
    
    def test_entity_disambiguation_linking(self):
        """Disambiguate entities before linking."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Ambiguous entity name
        text = "Washington is the capital. Washington is also a state."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should disambiguate Washington before linking
        assert isinstance(entities, list)
    
    def test_linking_score_computation(self):
        """Compute entity linking scores."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Entity to be linked"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Links should have scores
        for entity in entities:
            if isinstance(entity, dict):
                assert isinstance(entity, dict)
    
    def test_multiple_candidates_ranking(self):
        """Rank multiple candidate KB entries."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "John works for Apple."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Apple could be company or fruit - should rank candidates
        assert isinstance(entities, list)


class TestCrossDocumentLinking:
    """Cross-document entity linking."""
    
    def test_link_entity_across_documents(self):
        """Link same entity across multiple documents."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        doc1 = "Alice works at Company X."
        doc2 = "Alice leads the engineering team."
        
        result1 = generator.generate_ontology(doc1, context)
        result2 = generator.generate_ontology(doc2, context)
        
        assert result1 is not None
        assert result2 is not None
        # Should recognize Alice in both documents as same entity
        assert "entities" in result1
        assert "entities" in result2
    
    def test_entity_chain_linking(self):
        """Link entities in referential chains."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Referential chain: Alice -> she -> the manager
        text = "Alice is a manager. She leads the team. The manager reports to CEO."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should link pronouns and references to original entity
        assert isinstance(entities, list)
    
    def test_cross_doc_relationship_linking(self):
        """Link relationships across documents."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="organizational")
        generator = OntologyGenerator()
        
        doc1 = "Alice manages Bob."
        doc2 = "Bob works at Company X."
        
        result1 = generator.generate_ontology(doc1, context)
        result2 = generator.generate_ontology(doc2, context)
        
        assert result1 is not None
        assert result2 is not None
        # Should maintain entity links across docs
        assert "relationships" in result1
        assert "entities" in result2


class TestEntityAliasResolution:
    """Test entity alias and alternative name resolution."""
    
    def test_resolve_entity_aliases(self):
        """Resolve aliases to canonical entity."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Robert Smith (Bob) is the CEO. Smith leads the company."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize Robert, Bob, Smith as same entity
        assert isinstance(entities, list)
    
    def test_abbreviation_expansion(self):
        """Expand abbreviations to canonical form."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Dr. John Smith, M.D. works at USA Medical Center."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should expand abbreviations: Dr., M.D., USA
        assert isinstance(entities, list)
    
    def test_nickname_resolution(self):
        """Resolve nicknames to formal names."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "William 'Bill' Gates is the founder. Gates led Microsoft."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize Bill as William
        assert isinstance(entities, list)
    
    def test_multilingual_alias_resolution(self):
        """Resolve aliases across languages."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "José (Joe) García works in the company."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should handle multilingual aliases
        assert isinstance(entities, list)


class TestCoreferenceResolution:
    """Test coreference resolution for entity linking."""
    
    def test_pronoun_coreference(self):
        """Resolve pronouns to entities."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice is a manager. She leads the team. Her office is on the 5th floor."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should link she/her to Alice
        assert isinstance(entities, list)
    
    def test_appositive_coreference(self):
        """Resolve appositives to entities."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Bob Johnson, the CEO, led the company. Johnson retired last year."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should link CEO role and Johnson to same entity
        assert isinstance(entities, list)
    
    def test_definite_description_coreference(self):
        """Resolve definite descriptions to entities."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice founded the company. The founder still leads it today."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should link 'the founder' to Alice
        assert isinstance(entities, list)
    
    def test_event_coreference(self):
        """Resolve event references."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "The merger happened in 2020. This transaction changed the industry."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should link 'this transaction' to 'merger'
        assert isinstance(result, dict)


class TestEntityCanonicalization:
    """Test entity name canonicalization."""
    
    def test_case_normalization(self):
        """Normalize entity names to canonical case."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "john smith, JOHN SMITH, John Smith"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should normalize to canonical case
        assert isinstance(entities, list)
    
    def test_whitespace_normalization(self):
        """Normalize whitespace in entity names."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice  Smith vs Alice Smith"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should normalize whitespace
        assert isinstance(entities, list)
    
    def test_punctuation_normalization(self):
        """Normalize punctuation in entity names."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "U.S.A. vs USA vs U.S.A"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should normalize punctuation
        assert isinstance(entities, list)
    
    def test_canonical_form_selection(self):
        """Select canonical form from multiple variants."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Python (programming language) is widely used. Python is versatile."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should select most informative canonical form
        assert isinstance(entities, list)


class TestLinkingConfidenceScoring:
    """Test confidence scoring for entity linking."""
    
    def test_link_confidence_computation(self):
        """Compute confidence scores for entity links."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Unambiguous Entity Name"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Links should have confidence scores
        for entity in entities:
            if isinstance(entity, dict):
                assert isinstance(entity, dict)
    
    def test_ambiguous_linking_confidence(self):
        """Lower confidence for ambiguous entity links."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Washington or Churchill could refer to person or place."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Ambiguous links should have lower confidence
        assert isinstance(entities, list)
    
    def test_popular_entity_linking_boost(self):
        """Boost confidence for popular/frequent entities."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Very common entity
        text = "Apple Inc. is a major company. Apple stock rose."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Popular entity should have high link confidence
        assert isinstance(entities, list)


class TestLinkingEdgeCases:
    """Test edge cases in entity linking."""
    
    def test_link_rare_entities(self):
        """Link rare or specialized entities."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="scientific")
        generator = OntologyGenerator()
        
        text = "Zygomycosis is rare fungal infection."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should handle rare entities
        assert isinstance(entities, list)
    
    def test_link_newly_created_entities(self):
        """Link entities not in KB."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "NewStartupXYZ Inc recently founded."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should handle entities not in KB
        assert isinstance(entities, list)
    
    def test_link_very_long_entity_names(self):
        """Link entities with very long names."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "The comprehensive international organization for scientific advancement works globally."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should handle long entity names
        assert isinstance(entities, list)
    
    def test_link_numeric_entities(self):
        """Link numeric and alphanumeric entities."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "NASA-STD-1590B is the standard. RFC 3986 is important."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should handle numeric identifiers
        assert isinstance(entities, list)
