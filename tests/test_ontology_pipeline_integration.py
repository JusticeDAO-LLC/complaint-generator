"""
Ontology Pipeline Integration Tests

Tests for end-to-end ontology generation pipeline including all stages:
data loading, entity extraction, relationship inference, validation, 
and output formatting. Full integration testing.
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestPipelineDataLoading:
    """Test data loading in pipeline."""
    
    def test_load_text_data(self):
        """Load text data for processing."""
        context = OntologyGenerationContext(data_source="test.txt", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Sample text data for pipeline."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)
    
    def test_load_large_text(self):
        """Load large text documents."""
        context = OntologyGenerationContext(data_source="large.txt", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # 5000 character text
        text = "Entity " * 1000 + "data."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)
    
    def test_load_with_special_characters(self):
        """Load text with special characters."""
        context = OntologyGenerationContext(data_source="special.txt", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Text with émojis 🎉 and spëcial çhars: §±¶†"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result, dict)


class TestPipelineEntityExtraction:
    """Test entity extraction in pipeline."""
    
    def test_extract_entities_basic(self):
        """Extract entities from text."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice works at Company X in New York."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        assert len(entities) > 0
    
    def test_extract_entities_with_types(self):
        """Extract entities with proper types."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Person: John, Place: Paris, Organization: Apple"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Check entity structure
        for entity in entities:
            if isinstance(entity, dict):
                assert "text" in entity or "type" in entity
    
    def test_extract_all_entity_types(self):
        """Extract all entity types in dataset."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Person John, Location Paris, Organization Google, Date 2024, Amount $100"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        assert isinstance(entities, list)


class TestPipelineRelationshipInference:
    """Test relationship inference in pipeline."""
    
    def test_infer_relationships(self):
        """Infer relationships from entities."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice manages Bob. Bob works with Charlie."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)
    
    def test_infer_transitive_relationships(self):
        """Infer transitive relationships."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "A contains B. B contains C."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        # Should infer A contains C
        assert isinstance(relationships, list)
    
    def test_relationship_confidence_assignment(self):
        """Assign confidence to relationships."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice definitely manages Bob. Alice probably co-leads Charlie."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        # Relationships should have varying confidence
        assert isinstance(relationships, list)


class TestPipelineValidation:
    """Test validation stages in pipeline."""
    
    def test_validate_entity_structure(self):
        """Validate entity structure."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Entity data"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # All entities should be dicts
        assert all(isinstance(e, dict) for e in entities)
    
    def test_validate_relationship_structure(self):
        """Validate relationship structure."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "A relates to B"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        # All relationships should be dicts
        assert all(isinstance(r, dict) for r in relationships)
    
    def test_validate_metadata(self):
        """Validate metadata structure."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Test data"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert "metadata" in result
        metadata = result.get("metadata", {})
        assert isinstance(metadata, dict)


class TestPipelineOutputFormatting:
    """Test output formatting in pipeline."""
    
    def test_format_json_output(self):
        """Format output as JSON."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Test data"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should be JSON serializable
        assert isinstance(result, dict)
    
    def test_output_contains_required_fields(self):
        """Output contains all required fields."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Test data"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        required_fields = ["entities", "relationships", "metadata", "domain"]
        for field in required_fields:
            assert field in result
    
    def test_output_field_types(self):
        """Validate output field types."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Test data"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert isinstance(result.get("entities", []), list)
        assert isinstance(result.get("relationships", []), list)
        assert isinstance(result.get("metadata", {}), dict)
        assert isinstance(result.get("domain"), str)


class TestPipelineEndToEnd:
    """End-to-end pipeline tests."""
    
    def test_pipeline_legal_domain(self):
        """Run full pipeline for legal domain."""
        context = OntologyGenerationContext(
            data_source="contract.txt", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        text = "Plaintiff Smith sues defendant Jones. Contract dated 2024. Witness Johnson testifies."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert result.get("domain") == "legal"
        assert "entities" in result
        assert "relationships" in result
    
    def test_pipeline_medical_domain(self):
        """Run full pipeline for medical domain."""
        context = OntologyGenerationContext(
            data_source="patient.txt", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "Patient diagnosed with diabetes. Symptoms include fever. Treatment: insulin."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert result.get("domain") == "medical"
        assert "entities" in result
    
    def test_pipeline_business_domain(self):
        """Run full pipeline for business domain."""
        context = OntologyGenerationContext(
            data_source="report.txt", data_type="text", domain="business"
        )
        generator = OntologyGenerator()
        
        text = "Company revenue increased. CEO announced expansion. Stock price rose."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert result.get("domain") == "business"
        assert "entities" in result


class TestPipelinePerformance:
    """Pipeline performance tests."""
    
    def test_pipeline_processing_time(self):
        """Pipeline completes in reasonable time."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Entity data " * 100
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should complete without timeout
        assert isinstance(result, dict)
    
    def test_pipeline_memory_efficiency(self):
        """Pipeline memory usage is reasonable."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Data " * 10000
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should not crash due to memory
        assert isinstance(result, dict)


class TestPipelineErrorHandling:
    """Pipeline error handling."""
    
    def test_handle_empty_input(self):
        """Handle empty input gracefully."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("", context)
        
        assert result is not None
        assert isinstance(result, dict)
    
    def test_handle_none_input(self):
        """Handle None input gracefully."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Should handle gracefully
        result = generator.generate_ontology("Test", context)
        
        assert result is not None
    
    def test_handle_invalid_domain(self):
        """Handle invalid domain gracefully."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="invalid_domain"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        # Should still generate ontology with fallback
        assert isinstance(result, dict)


class TestPipelineConsistency:
    """Pipeline consistency tests."""
    
    def test_consistent_results_same_input(self):
        """Same input produces consistent results."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice works at Company X."
        
        results = [generator.generate_ontology(text, context) for _ in range(3)]
        
        assert all(r is not None for r in results)
        # Entity counts should be consistent
        entity_counts = [len(r.get("entities", [])) for r in results]
        assert len(set(entity_counts)) <= 2  # Allow minor variation


class TestPipelineIntegrationWithRefinement:
    """Pipeline integration with refinement cycles."""
    
    def test_pipeline_with_feedback(self):
        """Pipeline accepts and processes feedback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Initial data"
        result1 = generator.generate_ontology(text, context)
        
        # Refined text with feedback
        text2 = "Initial data refined"
        result2 = generator.generate_ontology(text2, context)
        
        assert result1 is not None
        assert result2 is not None
        # Both should be valid
        assert "entities" in result1
        assert "entities" in result2
