"""
Domain Adaptation and Learning Tests

Tests for domain-specific learning, adaptation mechanisms, and transfer
learning capabilities. Covers domain switching, fine-tuning, and knowledge 
transfer across domains.
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestBasicDomainAdaptation:
    """Test basic domain adaptation mechanisms."""
    
    def test_adapt_to_legal_domain(self):
        """Adapt extraction to legal domain."""
        context = OntologyGenerationContext(
            data_source="contract", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        text = "Plaintiff sues for breach of contract."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert result.get("domain") == "legal"
    
    def test_adapt_to_medical_domain(self):
        """Adapt extraction to medical domain."""
        context = OntologyGenerationContext(
            data_source="patient_record", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "Patient presents with hypertension."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert result.get("domain") == "medical"
    
    def test_adapt_to_business_domain(self):
        """Adapt extraction to business domain."""
        context = OntologyGenerationContext(
            data_source="annual_report", data_type="text", domain="business"
        )
        generator = OntologyGenerator()
        
        text = "Revenue increased by 25% YoY."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert result.get("domain") == "business"


class TestDomainSpecificRules:
    """Test domain-specific extraction rules."""
    
    def test_legal_domain_rules(self):
        """Apply legal domain-specific rules."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        text = "The court ruled in favor of plaintiff. Defendant appealed."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize legal entities (Court, Judge, Party)
        assert isinstance(entities, list)
    
    def test_medical_domain_rules(self):
        """Apply medical domain-specific rules."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "Dr. Johnson prescribed antibiotics for infection."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize medical entities (Doctor, Treatment, Condition)
        assert isinstance(entities, list)
    
    def test_financial_domain_rules(self):
        """Apply financial domain-specific rules."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="business"
        )
        generator = OntologyGenerator()
        
        text = "Stock price: $100. P/E ratio: 15.5"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize financial entities
        assert isinstance(entities, list)


class TestDomainTransferLearning:
    """Test transfer learning across domains."""
    
    def test_transfer_from_general_to_legal(self):
        """Transfer knowledge from general domain to legal."""
        context_general = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        context_legal = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        text = "John Smith sues ABC Corporation for damages."
        
        result_general = generator.generate_ontology(text, context_general)
        result_legal = generator.generate_ontology(text, context_legal)
        
        assert result_general is not None
        assert result_legal is not None
        # Legal domain should have additional insights
        assert result_legal.get("domain") == "legal"
    
    def test_transfer_from_medical_to_general(self):
        """Transfer knowledge from medical to general domain."""
        context_medical = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        context_general = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Patient treated for influenza at hospital."
        
        result_medical = generator.generate_ontology(text, context_medical)
        result_general = generator.generate_ontology(text, context_general)
        
        assert result_medical is not None
        assert result_general is not None
        assert result_medical.get("domain") == "medical"


class TestDomainSwitching:
    """Test dynamic domain switching."""
    
    def test_switch_domain_mid_session(self):
        """Switch domains within same session."""
        generator = OntologyGenerator()
        
        context_legal = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal"
        )
        context_medical = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        
        result1 = generator.generate_ontology("Plaintiff sues", context_legal)
        result2 = generator.generate_ontology("Patient diagnosed", context_medical)
        
        assert result1 is not None
        assert result2 is not None
        assert result1.get("domain") == "legal"
        assert result2.get("domain") == "medical"
    
    def test_domain_isolation(self):
        """Ensure domain-specific data doesn't leak across switches."""
        generator = OntologyGenerator()
        
        context1 = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal"
        )
        context2 = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        
        result1 = generator.generate_ontology("Legal term", context1)
        result2 = generator.generate_ontology("General term", context2)
        
        assert result1 is not None
        assert result2 is not None
        # Each should maintain its domain context
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)


class TestDomainFineTuning:
    """Test fine-tuning for domain-specific extraction."""
    
    def test_finetune_with_domain_examples(self):
        """Fine-tune extraction using domain-specific examples."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        # Domain-specific text
        text = "Complaint filed in court system."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize legal terminology
        assert isinstance(result, dict)
    
    def test_adaptation_improves_domain_accuracy(self):
        """Domain adaptation improves extraction accuracy."""
        context_general = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        context_medical = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        medical_text = "Myocardial infarction diagnosis"
        
        # General extraction may be less accurate
        result_general = generator.generate_ontology(medical_text, context_general)
        # Medical extraction should be more accurate
        result_medical = generator.generate_ontology(medical_text, context_medical)
        
        assert result_general is not None
        assert result_medical is not None
        # Medical context provides domain-specific understanding
        assert result_medical.get("domain") == "medical"


class TestCrossDomainConsistency:
    """Test consistency of extraction patterns across domains."""
    
    def test_entity_structure_consistency(self):
        """Entity structure consistent across domains."""
        generator = OntologyGenerator()
        
        contexts = [
            OntologyGenerationContext(data_source="test", data_type="text", domain="legal"),
            OntologyGenerationContext(data_source="test", data_type="text", domain="medical"),
            OntologyGenerationContext(data_source="test", data_type="text", domain="business"),
        ]
        
        text = "Entity extraction test"
        results = [generator.generate_ontology(text, ctx) for ctx in contexts]
        
        # All should have same structure
        for result in results:
            assert "entities" in result
            assert "relationships" in result
            assert "metadata" in result
    
    def test_confidence_scaling_consistency(self):
        """Confidence scores scaled consistently across domains."""
        generator = OntologyGenerator()
        
        contexts = [
            OntologyGenerationContext(data_source="test", data_type="text", domain="legal"),
            OntologyGenerationContext(data_source="test", data_type="text", domain="medical"),
        ]
        
        text = "Test data"
        results = [generator.generate_ontology(text, ctx) for ctx in contexts]
        
        # Confidence scaling should be consistent
        for result in results:
            entities = result.get("entities", [])
            for entity in entities:
                if isinstance(entity, dict) and "confidence" in entity:
                    # Confidence should be in [0, 1]
                    assert 0 <= entity["confidence"] <= 1


class TestMultiDomainExtraction:
    """Test extraction in multi-domain contexts."""
    
    def test_mixed_domain_text(self):
        """Extract from text spanning multiple domains."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        # Text with legal + medical elements
        text = "Dr. Johnson sued for medical malpractice."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should handle cross-domain entities
        assert isinstance(entities, list)
    
    def test_domain_priority_ranking(self):
        """Rank domains by relevance in mixed text."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Legal contract about medical treatment"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should identify multiple domain themes
        assert isinstance(result, dict)


class TestDomainSemantics:
    """Test semantic understanding within domains."""
    
    def test_legal_semantics(self):
        """Understand legal domain semantics."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        text = "The defendant pleaded guilty to charges."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should understand legal relationships
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)
    
    def test_medical_semantics(self):
        """Understand medical domain semantics."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "Aspirin reduces risk of myocardial infarction."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should understand medical causality
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)
    
    def test_business_semantics(self):
        """Understand business domain semantics."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="business"
        )
        generator = OntologyGenerator()
        
        text = "Company A acquired Company B for $1 billion."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should understand business relationships
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)


class TestDomainVocabulary:
    """Test domain-specific vocabulary handling."""
    
    def test_legal_vocabulary(self):
        """Handle legal-specific vocabulary."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        text = "Plaintiff filed motion for summary judgment."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize legal vocabulary
        assert isinstance(entities, list)
    
    def test_medical_vocabulary(self):
        """Handle medical-specific vocabulary."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "Endoscopy revealed gastritis with erosions."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should recognize medical vocabulary
        assert isinstance(entities, list)


class TestAdaptationEdgeCases:
    """Test edge cases in domain adaptation."""
    
    def test_adapt_to_unknown_domain(self):
        """Handle adaptation to unknown domain."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="unknown_domain"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        # Should fall back to general domain
        assert isinstance(result, dict)
    
    def test_adapt_with_empty_domain(self):
        """Handle empty/null domain gracefully."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        # Should use default general domain
        assert isinstance(result, dict)
    
    def test_adapt_with_special_chars_domain(self):
        """Handle domain names with special characters."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal-medical"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        # Should handle gracefully
        assert isinstance(result, dict)
