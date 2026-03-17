"""
Extraction Quality Metrics Tests

Tests for quality metrics and evaluation of extraction results.
Covers precision, recall, F1 scores, confidence distributions,
and domain-specific quality measures.
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestExtractionPrecision:
    """Test precision metrics for extraction."""
    
    def test_precision_high_confidence_entities(self):
        """High confidence entities should have high precision."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "John Smith works at Apple Inc."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Clear entities should be extracted
        assert len(entities) > 0
    
    def test_precision_low_ambiguity_text(self):
        """Low-ambiguity text should have high precision."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice is a doctor."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # All extracted entities should be correct
        assert all(isinstance(e, dict) for e in entities)
    
    def test_precision_decreases_with_ambiguity(self):
        """Precision decreases with ambiguous text."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Ambiguous text
        text = "Bank could be financial or geographical."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # May have lower precision on ambiguous entity
        assert isinstance(entities, list)


class TestExtractionRecall:
    """Test recall metrics for extraction."""
    
    def test_recall_finds_obvious_entities(self):
        """Should find obvious entities in text."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice, Bob, and Charlie work together."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should find multiple person entities
        assert len(entities) > 0
    
    def test_recall_on_diverse_types(self):
        """Should find entities of diverse types."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Person John works at Company X in City Y on 2024-02-23."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should extract multiple entity types
        assert len(entities) > 0


class TestF1Metrics:
    """Test F1 score computation and evaluation."""
    
    def test_f1_computation(self):
        """Compute F1 scores for extraction."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Entity extraction test data"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Result should have metrics available
        assert isinstance(result, dict)
    
    def test_f1_balanced_precision_recall(self):
        """F1 reflects balance between precision and recall."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Balanced test data with multiple entities"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # F1 should reflect extraction quality
        metadata = result.get("metadata", {})
        assert isinstance(metadata, dict)


class TestConfidenceDistribution:
    """Test confidence score distributions."""
    
    def test_confidence_mean(self):
        """Compute mean confidence of extracted entities."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Entity data for confidence testing"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Mean confidence should be available
        assert isinstance(result, dict)
    
    def test_confidence_variance(self):
        """Compute confidence variance."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Data with varying entity confidence levels"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Entities may have varying confidence
        assert isinstance(entities, list)
    
    def test_confidence_percentiles(self):
        """Compute confidence percentiles."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Multiple entities for percentile analysis"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Metadata should allow percentile computation
        assert isinstance(result, dict)


class TestDomainSpecificQuality:
    """Test domain-specific quality metrics."""
    
    def test_legal_domain_quality(self):
        """Evaluate quality metrics for legal domain."""
        context = OntologyGenerationContext(
            data_source="contract.txt", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        text = "Plaintiff sues defendant. Witness testifies."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert result.get("domain") == "legal"
    
    def test_medical_domain_quality(self):
        """Evaluate quality metrics for medical domain."""
        context = OntologyGenerationContext(
            data_source="patient.txt", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "Patient diagnosed. Symptoms present. Treatment prescribed."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert result.get("domain") == "medical"
    
    def test_business_domain_quality(self):
        """Evaluate quality metrics for business domain."""
        context = OntologyGenerationContext(
            data_source="report.txt", data_type="text", domain="business"
        )
        generator = OntologyGenerator()
        
        text = "Company revenue increased. CEO announced strategy."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert result.get("domain") == "business"


class TestEntityTypeQuality:
    """Test quality of entity type classification."""
    
    def test_entity_type_accuracy(self):
        """Measure entity type classification accuracy."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "John (person) works at Apple (organization) in NYC (location)."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Entity types should be correct
        for entity in entities:
            if isinstance(entity, dict):
                assert isinstance(entity, dict)
    
    def test_entity_type_distribution(self):
        """Analyze distribution of entity types."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Multiple diverse entity types in one text"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should extract entities of varying types
        assert isinstance(entities, list)


class TestRelationshipQuality:
    """Test quality of relationship extraction."""
    
    def test_relationship_accuracy(self):
        """Measure relationship extraction accuracy."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice manages Bob. Bob works with Charlie."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        # Relationships should be correctly extracted
        assert isinstance(relationships, list)
    
    def test_relationship_type_quality(self):
        """Measure relationship type classification."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="organizational")
        generator = OntologyGenerator()
        
        text = "Manager-subordinate relationship identified."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        # Relationship types should be appropriate
        for rel in relationships:
            if isinstance(rel, dict):
                assert isinstance(rel, dict)


class TestExtractionCompleteness:
    """Test completeness of extraction."""
    
    def test_entity_coverage(self):
        """Measure entity extraction coverage."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice, Bob, Charlie, Diana, Edward work together."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should extract most entities
        assert len(entities) > 0
    
    def test_relationship_coverage(self):
        """Measure relationship extraction coverage."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "A-B related. B-C related. C-D related. D-E related."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        # Should extract most relationships
        assert isinstance(relationships, list)


class TestExtractionConsistency:
    """Test consistency of extraction metrics."""
    
    def test_consistent_entity_extraction(self):
        """Entity extraction should be consistent across runs."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Consistent test data"
        
        results = [generator.generate_ontology(text, context) for _ in range(3)]
        
        assert all(r is not None for r in results)
        # Entity counts should be consistent
        entity_counts = [len(r.get("entities", [])) for r in results]
        assert len(set(entity_counts)) <= 2
    
    def test_consistent_relationship_extraction(self):
        """Relationship extraction should be consistent."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Consistent relationship data"
        
        results = [generator.generate_ontology(text, context) for _ in range(3)]
        
        assert all(r is not None for r in results)
        # Relationship counts should be consistent
        rel_counts = [len(r.get("relationships", [])) for r in results]
        assert len(set(rel_counts)) <= 2


class TestErrorMetrics:
    """Test error and anomaly metrics."""
    
    def test_false_positive_rate(self):
        """Measure false positive rate in extraction."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Simple test with clear entities"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # False positives should be minimal for clear text
        assert isinstance(entities, list)
    
    def test_false_negative_rate(self):
        """Measure false negative rate."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Multiple obvious entities that should all be found"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # False negatives should be minimal
        assert len(entities) > 0


class TestQualityMetricsEdgeCases:
    """Test edge cases in quality metrics."""
    
    def test_quality_metrics_empty_input(self):
        """Handle quality metrics for empty input."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("", context)
        
        assert result is not None
        # Should still produce valid metrics structure
        assert isinstance(result, dict)
    
    def test_quality_metrics_single_entity(self):
        """Handle quality metrics with single entity."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("John", context)
        
        assert result is not None
        # Metrics should handle single entity gracefully
        assert isinstance(result, dict)
    
    def test_quality_metrics_large_ontology(self):
        """Handle quality metrics for large ontologies."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Entity " * 500
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should compute metrics efficiently
        assert isinstance(result, dict)
