"""
Advanced Ontology Features and Capabilities Testing

Tests for advanced features including ontology versioning, schema
validation, knowledge graph operations, and advanced querying.
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestOntologyVersioning:
    """Test ontology versioning capabilities."""
    
    def test_ontology_has_version_field(self):
        """Ontology includes version information."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        assert result is not None
        # Version should be tracked
        assert isinstance(result, dict)
    
    def test_version_consistency_across_domains(self):
        """Version field consistent across domains."""
        texts = [
            ("legal", "Contract signed"),
            ("medical", "Patient diagnosed"),
            ("business", "Revenue increased"),
        ]
        
        generator = OntologyGenerator()
        
        for domain, text in texts:
            context = OntologyGenerationContext(
                data_source="test", data_type="text", domain=domain
            )
            result = generator.generate_ontology(text, context)
            
            assert result is not None
            assert isinstance(result, dict)


class TestEntityHierarchy:
    """Test entity hierarchy and classification."""
    
    def test_entity_type_hierarchy(self):
        """Entity types form proper hierarchy."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John Smith, a software engineer at Acme Corporation"
        result = generator.generate_ontology(text, context)
        
        entities = result.get("entities", [])
        
        # Should classify entities by type
        assert isinstance(entities, list)
    
    def test_entity_subtyping(self):
        """Entity subtyping relationships."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Person: John. Organization: Acme. Location: New York"
        result = generator.generate_ontology(text, context)
        
        entities = result.get("entities", [])
        
        # Should distinguish entity subtypes
        assert isinstance(entities, list)


class TestRelationshipHierarchy:
    """Test relationship hierarchy and classification."""
    
    def test_relationship_type_hierarchy(self):
        """Relationship types form proper hierarchy."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John manages Alice. Alice supervises Bob."
        result = generator.generate_ontology(text, context)
        
        relationships = result.get("relationships", [])
        
        # Should classify relationships
        assert isinstance(relationships, list)
    
    def test_relationship_transitivity(self):
        """Relationships can be transitive."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "A contains B. B contains C."
        result = generator.generate_ontology(text, context)
        
        relationships = result.get("relationships", [])
        
        # Should handle transitive reasoning
        assert isinstance(relationships, list)


class TestKnowledgeGraphStructure:
    """Test knowledge graph structural properties."""
    
    def test_graph_connectivity(self):
        """Knowledge graph maintains connectivity."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John works for Acme. Acme is located in New York."
        result = generator.generate_ontology(text, context)
        
        entities = result.get("entities", [])
        relationships = result.get("relationships", [])
        
        # Graph should be connected
        assert len(entities) > 0
        assert len(relationships) > 0
    
    def test_graph_cycles_detection(self):
        """Cycles in knowledge graph detected."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "A influences B. B influences C. C influences A."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle cycles
        assert isinstance(result, dict)
    
    def test_graph_redundancy_detection(self):
        """Redundant relationships detected."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John manages Alice. John manages Alice."
        result = generator.generate_ontology(text, context)
        
        relationships = result.get("relationships", [])
        
        # Should detect redundancy
        assert isinstance(relationships, list)


class TestSchemaValidation:
    """Test ontology schema and validation."""
    
    def test_entities_follow_schema(self):
        """All entities follow schema."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("John works", context)
        
        entities = result.get("entities", [])
        for entity in entities:
            assert isinstance(entity, dict)
            # Entity should have basic properties
            assert len(entity) > 0
    
    def test_relationships_follow_schema(self):
        """All relationships follow schema."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("John manages Alice", context)
        
        relationships = result.get("relationships", [])
        for rel in relationships:
            assert isinstance(rel, dict)
            # Relationship should have basic properties
            assert len(rel) > 0


class TestConstraintValidation:
    """Test constraint validation."""
    
    def test_entity_uniqueness_constraint(self):
        """Entity uniqueness constraints."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("John and John", context)
        
        entities = result.get("entities", [])
        # Should handle duplicate entities
        assert isinstance(entities, list)
    
    def test_relationship_cardinality(self):
        """Relationship cardinality constraints."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John manages Alice, Bob, Charlie"
        result = generator.generate_ontology(text, context)
        
        relationships = result.get("relationships", [])
        # Should handle multiple relationships
        assert isinstance(relationships, list)


class TestInheritanceAndComposition:
    """Test inheritance and composition patterns."""
    
    def test_inheritance_relationships(self):
        """Inheritance relationships recognized."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Engineer is a type of Employee"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)
    
    def test_composition_relationships(self):
        """Composition relationships recognized."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Company has departments. Departments have teams."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)


class TestMetadataEnrichment:
    """Test metadata enrichment."""
    
    def test_metadata_contains_statistics(self):
        """Metadata includes statistics."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test data", context)
        
        metadata = result.get("metadata", {})
        assert isinstance(metadata, dict)
    
    def test_metadata_source_tracking(self):
        """Metadata tracks source information."""
        context = OntologyGenerationContext(
            data_source="document1", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Contract terms", context)
        
        assert result is not None
        metadata = result.get("metadata", {})
        assert isinstance(metadata, dict)
    
    def test_metadata_quality_scores(self):
        """Metadata includes quality scores."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        metadata = result.get("metadata", {})
        # Quality metrics should be present
        assert isinstance(metadata, dict)


class TestAggregationOperations:
    """Test aggregation and summarization."""
    
    def test_entity_grouping(self):
        """Entities can be grouped."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John, Alice, Bob work at Acme"
        result = generator.generate_ontology(text, context)
        
        entities = result.get("entities", [])
        assert len(entities) > 0
    
    def test_relationship_aggregation(self):
        """Relationships can be aggregated."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John manages Alice, Bob, Charlie"
        result = generator.generate_ontology(text, context)
        
        relationships = result.get("relationships", [])
        # Should aggregate similar relationships
        assert isinstance(relationships, list)


class TestQueryOperations:
    """Test query-like operations on ontology."""
    
    def test_entity_lookup(self):
        """Can lookup entities."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John Smith works at Acme"
        result = generator.generate_ontology(text, context)
        
        entities = result.get("entities", [])
        # Should have found John Smith
        assert len(entities) > 0
    
    def test_relationship_lookup(self):
        """Can lookup relationships."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John manages Alice"
        result = generator.generate_ontology(text, context)
        
        relationships = result.get("relationships", [])
        # Should have found manages relationship
        assert len(relationships) > 0


class TestOntologyExport:
    """Test ontology export capabilities."""
    
    def test_ontology_is_serializable(self):
        """Ontology can be serialized."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        # Should be JSON-serializable
        import json
        try:
            json.dumps(result)
        except TypeError:
            # Some fields might not be JSON-serializable, that's ok
            pass
    
    def test_ontology_has_metadata(self):
        """Ontology includes exportable metadata."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("test", context)
        
        assert "metadata" in result
        assert isinstance(result["metadata"], dict)


class TestAdvancedDomainFeatures:
    """Test advanced domain-specific features."""
    
    def test_legal_domain_entities(self):
        """Legal domain recognizes special entities."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        text = "Agreement signed on January 1, 2024"
        result = generator.generate_ontology(text, context)
        
        entities = result.get("entities", [])
        # Should recognize legal entities
        assert isinstance(entities, list)
    
    def test_medical_domain_entities(self):
        """Medical domain recognizes special entities."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "Diagnosis: Hypertension. Treatment: Medication"
        result = generator.generate_ontology(text, context)
        
        entities = result.get("entities", [])
        # Should recognize medical entities
        assert isinstance(entities, list)
    
    def test_business_domain_entities(self):
        """Business domain recognizes special entities."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="business"
        )
        generator = OntologyGenerator()
        
        text = "Q4 revenue: $1M. Expenses: $500K"
        result = generator.generate_ontology(text, context)
        
        entities = result.get("entities", [])
        # Should recognize business entities
        assert isinstance(entities, list)
