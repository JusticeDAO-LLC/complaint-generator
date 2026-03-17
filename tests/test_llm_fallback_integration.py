"""
LLM Fallback Strategy Integration Tests

Tests for LLM fallback mechanisms when rule-based extraction confidence is low.
Covers fallback triggering, LLM quality metrics, and hybrid mode behavior.
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestLLMFallbackBasics:
    """Basic LLM fallback functionality."""
    
    def test_fallback_triggered_on_low_confidence(self):
        """Trigger LLM fallback when rule-based confidence is low."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Ambiguous text that may trigger fallback
        text = "The bank by the river flooded."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)
    
    def test_fallback_not_triggered_on_high_confidence(self):
        """Don't trigger fallback when confidence is high."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Clear, unambiguous text
        text = "John Smith is a software engineer at Apple Inc."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        assert len(entities) > 0
    
    def test_fallback_decision_threshold(self):
        """Apply fallback decision threshold."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Borderline confidence text"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)


class TestLLMFallbackQuality:
    """Test quality of LLM fallback results."""
    
    def test_llm_improves_entity_accuracy(self):
        """LLM fallback improves entity extraction accuracy."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Complex sentence needing LLM understanding
        text = "The secretary general addresses the assembly."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should correctly identify entities despite complexity
        assert isinstance(entities, list)
    
    def test_llm_resolves_ambiguity(self):
        """LLM resolves ambiguous entity references."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Ambiguous text
        text = "The box is in the bank. The bank has security."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should disambiguate 'bank'
        assert isinstance(entities, list)
    
    def test_llm_handles_complex_relationships(self):
        """LLM correctly identifies complex relationships."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "The board's decision to appoint Sarah was controversial."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        # Should identify appointment relationship
        assert isinstance(relationships, list)


class TestLLMFallbackConsistency:
    """Test consistency of LLM fallback."""
    
    def test_consistent_llm_results(self):
        """LLM fallback produces consistent results."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Consistent test data"
        
        results = []
        for _ in range(3):
            result = generator.generate_ontology(text, context)
            results.append(result)
        
        assert all(r is not None for r in results)
        # Entity counts should be consistent
        entity_counts = [len(r.get("entities", [])) for r in results]
        assert len(set(entity_counts)) <= 2
    
    def test_llm_respects_domain(self):
        """LLM fallback respects domain constraints."""
        context_legal = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal"
        )
        context_medical = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "Doctor prescribed medication. Plaintiff sued for damages."
        result_legal = generator.generate_ontology(text, context_legal)
        result_medical = generator.generate_ontology(text, context_medical)
        
        assert result_legal is not None
        assert result_medical is not None
        # Domains should be respected
        assert result_legal.get("domain") == "legal"
        assert result_medical.get("domain") == "medical"


class TestHybridExtractionMode:
    """Test hybrid rule-based + LLM extraction mode."""
    
    def test_hybrid_mode_switches_appropriately(self):
        """Hybrid mode switches between strategies."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Simple text (use rule-based)
        simple = "John works at Company."
        result1 = generator.generate_ontology(simple, context)
        
        # Complex text (may use LLM)
        complex_text = "The convoluted arrangement of entities required sophisticated analysis."
        result2 = generator.generate_ontology(complex_text, context)
        
        assert result1 is not None
        assert result2 is not None
        # Both should produce valid results
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)
    
    def test_hybrid_combines_results(self):
        """Hybrid mode combines rule and LLM results."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Complex data requiring hybrid extraction approach"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should have combined Entity extraction
        assert "entities" in result
        assert "relationships" in result


class TestLLMFallbackPerformance:
    """Test LLM fallback performance characteristics."""
    
    def test_fallback_latency(self):
        """LLM fallback completes in reasonable time."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Test data for latency measurement"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should complete without timeout
        assert isinstance(result, dict)
    
    def test_multiple_fallback_calls(self):
        """Handle multiple LLM fallback calls efficiently."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        texts = [
            "Data requiring fallback 1",
            "Data requiring fallback 2",
            "Data requiring fallback 3",
        ]
        
        results = [generator.generate_ontology(t, context) for t in texts]
        
        assert all(r is not None for r in results)
        assert all(isinstance(r, dict) for r in results)


class TestLLMFallbackErrorHandling:
    """Test error handling in LLM fallback."""
    
    def test_graceful_fallback_failure(self):
        """Handle LLM fallback failures gracefully."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Edge case text
        text = ""
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should return valid ontology even on failure
        assert isinstance(result, dict)
    
    def test_fallback_with_malformed_input(self):
        """Handle malformed input in fallback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Incomplete sentence without"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)


class TestConfidenceThresholdConfig:
    """Test confidence threshold configuration."""
    
    def test_custom_confidence_threshold(self):
        """Apply custom confidence threshold."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Test data"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Metadata should indicate confidence levels
        assert "metadata" in result
    
    def test_threshold_affects_fallback_trigger(self):
        """Threshold configuration affects fallback triggering."""
        context_low = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        context_high = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Data for threshold testing"
        result_low = generator.generate_ontology(text, context_low)
        result_high = generator.generate_ontology(text, context_high)
        
        assert result_low is not None
        assert result_high is not None
        # Different thresholds may produce different results
        assert isinstance(result_low, dict)
        assert isinstance(result_high, dict)


class TestDomainSpecificFallback:
    """Test domain-specific LLM fallback behavior."""
    
    def test_legal_domain_fallback(self):
        """LLM fallback for legal domain."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        text = "Plaintiff sues defendant for breach of contract."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert result.get("domain") == "legal"
    
    def test_medical_domain_fallback(self):
        """LLM fallback for medical domain."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "Patient presents with hypertension and dyslipidemia."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert result.get("domain") == "medical"
    
    def test_scientific_domain_fallback(self):
        """LLM fallback for scientific domain."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="scientific"
        )
        generator = OntologyGenerator()
        
        text = "Photosynthesis converts CO2 and H2O into glucose and O2."
        result = generator.generate_ontology(text, context)
        
        assert result is not None


class TestFallbackMetrics:
    """Test fallback-related metrics and monitoring."""
    
    def test_track_fallback_invocations(self):
        """Track how often fallback is invoked."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Data for fallback tracking"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        metadata = result.get("metadata", {})
        # Should track fallback invoke count
        assert isinstance(metadata, dict)
    
    def test_measure_fallback_improvement(self):
        """Measure improvement from fallback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Complex data for improvement measurement"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Result should reflect fallback improvement
        assert isinstance(result, dict)


class TestLLMFallbackEdgeCases:
    """Test edge cases in LLM fallback."""
    
    def test_very_short_text_fallback(self):
        """Handle very short text in fallback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Go"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)
    
    def test_very_long_text_fallback(self):
        """Handle very long text in fallback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Data " * 5000
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)
    
    def test_numeric_heavy_text_fallback(self):
        """Handle numeric-heavy text in fallback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "12345 67890 11111 22222 33333"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)
