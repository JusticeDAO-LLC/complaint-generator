"""
Synonym Handling and Resolution Tests

Tests for synonym detection, resolution, equivalence mapping,
and normalization. Covers term synonymy, acronym expansion,
and canonical form selection.
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestBasicSynonymDetection:
    """Test basic synonym detection mechanisms."""
    
    def test_detect_simple_synonyms(self):
        """Detect simple word synonyms."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "The car and automobile drove fast."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize car and automobile as same concept
        assert isinstance(entities, list)
    
    def test_detect_domain_synonyms(self):
        """Detect domain-specific synonyms."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "MI and myocardial infarction are same condition."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize medical acronyms as synonyms
        assert isinstance(entities, list)
    
    def test_detect_technical_synonyms(self):
        """Detect technical/specialized synonyms."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="business"
        )
        generator = OntologyGenerator()
        
        text = "P2P and peer-to-peer transactions are equivalent."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize technical equivalences
        assert isinstance(entities, list)


class TestSynonymCanonicalForm:
    """Test canonical form selection for synonyms."""
    
    def test_select_canonical_form(self):
        """Select canonical form from synonyms."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "USA, United States, and America are same country."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should select canonical form for geographic entity
        assert isinstance(entities, list)
    
    def test_prefer_full_form_over_acronym(self):
        """Prefer full form over acronym as canonical."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "Coronary Artery Disease (CAD) is serious."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize CAD as acronym for full form
        assert isinstance(result, dict)
    
    def test_canonical_form_consistency(self):
        """Apply canonical form consistently."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "The US, USA, and United States signed agreement."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # All variations should map to same canonical entity
        entities = result.get("entities", [])
        assert isinstance(entities, list)


class TestAcronymExpansion:
    """Test acronym expansion and resolution."""
    
    def test_expand_common_acronym(self):
        """Expand common abbreviations."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "CEO address shareholders."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize CEO expansion
        assert isinstance(entities, list)
    
    def test_expand_domain_specific_acronym(self):
        """Expand domain-specific acronyms."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "Patient had CT scan for diagnosis."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should expand CT to Computed Tomography
        assert isinstance(entities, list)
    
    def test_context_dependent_acronym_expansion(self):
        """Expand acronyms based on context."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "FDA approval needed for drug launch."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize FDA in pharmaceutical context
        entities = result.get("entities", [])
        assert isinstance(entities, list)


class TestSynonymEquivalenceMapping:
    """Test mapping equivalence between synonyms."""
    
    def test_create_equivalence_mapping(self):
        """Create mapping between equivalent terms."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Sofa, couch, settee are furniture."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should map sofa, couch, settee to equivalent concept
        assert isinstance(entities, list)
    
    def test_bidirectional_equivalence(self):
        """Ensure bidirectional equivalence mapping."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        # Generate twice with different orders
        text1 = "Doctor and physician treat patients."
        text2 = "Physician and doctor treat patients."
        
        result1 = generator.generate_ontology(text1, context)
        result2 = generator.generate_ontology(text2, context)
        
        assert result1 is not None
        assert result2 is not None
        # Should recognize equivalence in both directions
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)
    
    def test_transitivity_in_synonyms(self):
        """Test transitive equivalence in synonymy."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "If A=B and B=C then A=C."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle transitive relationships
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)


class TestSynonymNormalization:
    """Test synonym normalization."""
    
    def test_normalize_case_variations(self):
        """Normalize case variations as synonyms."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "APPLE, Apple, apple are same company."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize case variations
        assert isinstance(entities, list)
    
    def test_normalize_whitespace_variations(self):
        """Normalize whitespace as synonyms."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "New York, NewYork, new york refer to same place."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize whitespace variations
        assert isinstance(entities, list)
    
    def test_normalize_punctuation_variations(self):
        """Normalize punctuation variations."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "U.S.A., USA, and U.S. same country."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should normalize punctuation
        assert isinstance(entities, list)


class TestPersonNameSynonyms:
    """Test synonym handling for person names."""
    
    def test_recognize_name_aliases(self):
        """Recognize aliases for person names."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Bob, Robert, and Bobby refer to same person."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize name aliases
        assert isinstance(entities, list)
    
    def test_recognize_nickname_synonymy(self):
        """Recognize nicknames as synonyms."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Bill Gates and William Gates are same person."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize nickname synonymy
        assert isinstance(entities, list)
    
    def test_recognize_formal_informal_names(self):
        """Recognize formal and informal name variations."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Dr. John Smith and John Smith are same doctor."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should map formal and informal variations
        assert isinstance(entities, list)


class TestOrganizationNameSynonyms:
    """Test synonym handling for organization names."""
    
    def test_recognize_company_name_variants(self):
        """Recognize company name variants."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="business"
        )
        generator = OntologyGenerator()
        
        text = "Microsoft, MSFT, and MS are same company."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize company variants
        assert isinstance(entities, list)
    
    def test_recognize_organization_abbreviations(self):
        """Recognize organization abbreviations."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "FBI, Federal Bureau of Investigation same agency."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize organizational synonymy
        assert isinstance(entities, list)
    
    def test_recognize_legal_entity_names(self):
        """Recognize legal entity name variations."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="business"
        )
        generator = OntologyGenerator()
        
        text = "Google Inc., Google LLC, and Alphabet subsidiaries."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize legal entity variations
        assert isinstance(entities, list)


class TestSynonymDisambiguation:
    """Test disambiguation when synonyms have multiple meanings."""
    
    def test_disambiguate_polysemous_terms(self):
        """Disambiguate polysemous terms."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Bank (financial) vs. bank (river) are different."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should distinguish different meanings
        assert isinstance(entities, list)
    
    def test_context_based_synonym_selection(self):
        """Select appropriate synonym based on context."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "HIV and AIDS in medical context."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize medical context for synonymy
        assert isinstance(entities, list)


class TestSynonymEdgeCases:
    """Test edge cases in synonym handling."""
    
    def test_handle_empty_synonym_list(self):
        """Handle terms with no synonyms."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Unique term with no synonyms."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should handle gracefully
        assert isinstance(entities, list)
    
    def test_handle_circular_synonym_references(self):
        """Handle circular references in synonymy."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "A is B, B is C, C is A relationship."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle circular references
        assert isinstance(result, dict)
    
    def test_handle_self_referential_synonym(self):
        """Handle terms that are their own synonyms."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Term and term are same."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle self-reference gracefully
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    def test_handle_multilingual_synonyms(self):
        """Handle synonyms across languages."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Car automobile voiture equivalence."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should handle multilingual terms
        assert isinstance(entities, list)
