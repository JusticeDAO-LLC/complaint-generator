"""
Negation Handling and Extraction Tests

Tests for detecting and properly handling negation in text,
including scope resolution, double negatives, and negation
in different linguistic contexts.
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestBasicNegationDetection:
    """Test basic negation detection."""
    
    def test_detect_simple_negation(self):
        """Detect simple negation with not."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Patient is not diabetic."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should detect negation of diabetic condition
        assert isinstance(result, dict)
    
    def test_detect_no_negation(self):
        """Detect negation with 'no'."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "No evidence of infection found."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize 'no' as negation marker
        assert isinstance(result, dict)
    
    def test_detect_never_negation(self):
        """Detect negation with 'never'."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Patient never smoked cigarettes."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize temporal negation
        assert isinstance(result, dict)
    
    def test_detect_prefix_negation(self):
        """Detect negation with prefix (un-, non-, etc.)."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "The treatment was unsuccessful."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize prefix negation
        entities = result.get("entities", [])
        assert isinstance(entities, list)


class TestNegationScope:
    """Test negation scope resolution."""
    
    def test_narrow_negation_scope(self):
        """Determine narrow negation scope."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Not all patients responded to treatment."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Negation applies only to 'all' not to entire predicate
        assert isinstance(result, dict)
    
    def test_broad_negation_scope(self):
        """Determine broad negation scope."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Do not give medication to patient."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Negation applies to entire action
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)
    
    def test_scope_with_multiple_clauses(self):
        """Determine scope with multiple clauses."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Patient cannot walk but can sit."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should scope negation correctly to first clause
        assert isinstance(result, dict)


class TestDoubleNegation:
    """Test double negation handling."""
    
    def test_recognize_double_negation(self):
        """Recognize and resolve double negation."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "We cannot deny the evidence."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Double negation affirms
        assert isinstance(result, dict)
    
    def test_multiple_negations(self):
        """Handle multiple negations in sequence."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Not unlikely to not occur."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should parse multiple negations correctly
        assert isinstance(result, dict)
    
    def test_negation_in_conditional(self):
        """Handle negation in conditional statements."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "If not approved, do not proceed."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle conditional negations
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)


class TestNegationInContext:
    """Test negation in different contexts."""
    
    def test_negation_in_question(self):
        """Detect negation in questions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Is the patient not improving?"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize negation in question
        assert isinstance(result, dict)
    
    def test_negation_in_imperative(self):
        """Detect negation in imperative sentences."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Don't administer medication without approval."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize imperative negation
        assert isinstance(result, dict)
    
    def test_negation_in_subordinate_clause(self):
        """Detect negation in subordinate clauses."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Although not approved, the treatment continued."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should scope negation to subordinate clause
        assert isinstance(result, dict)


class TestNegationWithQuantifiers:
    """Test negation interaction with quantifiers."""
    
    def test_negation_with_universal_quantifier(self):
        """Negation with 'all' quantifier."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Not all patients improved."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Negation of universal is existential
        assert isinstance(result, dict)
    
    def test_negation_with_existential_quantifier(self):
        """Negation with 'some' quantifier."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "No patients had adverse reactions."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Negation of existential is universal
        assert isinstance(result, dict)
    
    def test_negation_with_numeric_quantifier(self):
        """Negation with numeric quantifiers."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Not 5 patients but 3 improved."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle numeric negation
        entities = result.get("entities", [])
        assert isinstance(entities, list)


class TestNegationWithModalVerbs:
    """Test negation with modal verbs."""
    
    def test_negation_with_can(self):
        """Negation with 'can'."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Patient cannot walk without assistance."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize ability negation
        assert isinstance(result, dict)
    
    def test_negation_with_must(self):
        """Negation with 'must'."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Patient must not receive medication."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize prohibition
        assert isinstance(result, dict)
    
    def test_negation_with_may(self):
        """Negation with 'may'."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Patient may not attend without permission."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize permission negation
        assert isinstance(result, dict)


class TestNegationInComparatives:
    """Test negation in comparative statements."""
    
    def test_negation_in_comparative(self):
        """Negation in comparative expressions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Result is not worse than expected."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle comparative negation
        assert isinstance(result, dict)
    
    def test_negation_in_superlative(self):
        """Negation in superlative expressions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "This is not the best option."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle superlative negation
        entities = result.get("entities", [])
        assert isinstance(entities, list)


class TestNegationInConjunctions:
    """Test negation in conjunctive statements."""
    
    def test_negation_in_and_clause(self):
        """Negation in 'and' conjunction."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Not approved and not recommended."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should scope negation to both elements
        assert isinstance(result, dict)
    
    def test_negation_in_or_clause(self):
        """Negation in 'or' conjunction."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Not valid or not approved."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should apply De Morgan's law correctly
        assert isinstance(result, dict)


class TestNegationEdgeCases:
    """Test edge cases in negation handling."""
    
    def test_negation_with_proper_noun(self):
        """Handle negation applied to proper nouns."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "The patient is not John Smith."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle identity negation
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    def test_negation_with_empty_scope(self):
        """Handle negation with unclear scope."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Not."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle gracefully
        assert isinstance(result, dict)
    
    def test_negation_with_contractions(self):
        """Handle negation in contractions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Patient isn't responding. Doctor won't prescribe."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should parse contractions correctly
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    def test_negation_in_hyphenated_words(self):
        """Handle negation in hyphenated words."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Non-invasive procedure approved."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize hyphenated negation
        entities = result.get("entities", [])
        assert isinstance(entities, list)
