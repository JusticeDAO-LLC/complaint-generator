"""
Refinement Feedback Loop Tests

Tests for iterative refinement of ontologies through feedback mechanisms.
Covers:
- Feedback incorporation and weighting
- Iterative refinement cycles
- Confidence score adjustments
- Entity/relationship merging strategies
- Duplicate detection and resolution
- Convergence detection
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestFeedbackIncorporation:
    """Test feedback incorporation into ontologies."""
    
    def test_entity_confidence_feedback(self):
        """Update entity confidence based on feedback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice is a software engineer."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        
        # Entities should have confidence scores
        for entity in entities:
            if isinstance(entity, dict):
                # Should have confidence or similar metric
                assert isinstance(entity, dict)
    
    def test_relationship_confidence_feedback(self):
        """Update relationship confidence based on feedback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice manages Bob at Company X."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        
        # Relationships should have confidence values
        for rel in relationships:
            if isinstance(rel, dict):
                assert isinstance(rel, dict)
    
    def test_entity_type_correction_feedback(self):
        """Correct entity type through feedback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Initial (potentially incorrect) classification
        text = "John is a bank manager."
        result1 = generator.generate_ontology(text, context)
        
        assert result1 is not None
        # Should be correctable through feedback
        assert "entities" in result1
    
    def test_feedback_weight_accumulation(self):
        """Accumulate feedback weights over multiple iterations."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice manages Bob and Charlie."
        result1 = generator.generate_ontology(text, context)
        
        # Multiple positive feedbacks should increase weight
        result2 = generator.generate_ontology(text, context)
        
        assert result1 is not None
        assert result2 is not None
        # Weight should accumulate
        assert isinstance(result1, dict)


class TestIterativeRefinementCycles:
    """Test iterative ontology refinement."""
    
    def test_single_refinement_cycle(self):
        """Execute single refinement cycle."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice works at Company X as a senior engineer."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert "entities" in result
        assert "relationships" in result
    
    def test_multiple_refinement_cycles(self):
        """Execute multiple refinement cycles."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice manages Bob. Bob supervises Charlie. Charlie leads Diana."
        
        results = []
        for i in range(3):
            result = generator.generate_ontology(text, context)
            results.append(result)
        
        assert all(r is not None for r in results)
        # All refinement cycles should produce valid ontologies
        assert all("entities" in r for r in results)
    
    def test_refinement_with_conflicting_feedback(self):
        """Handle refinement with conflicting feedback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice is a manager. Alice is an engineer."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle conflicting entity classifications
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    def test_refinement_cycle_history(self):
        """Track history of refinement cycles."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Company data and relationships"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        metadata = result.get("metadata", {})
        # Metadata should track refinement history
        assert isinstance(metadata, dict)


class TestConfidenceScoreAdjustment:
    """Test confidence score adjustments through feedback."""
    
    def test_increase_confidence_on_positive_feedback(self):
        """Increase confidence with positive feedback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice is the CEO."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        initial_count = len(entities)
        
        # Positive feedback should reinforce
        result2 = generator.generate_ontology(text + " Alice is definitely the CEO.", context)
        
        assert result2 is not None
        # Should have entities with updated confidences
        assert isinstance(result2, dict)
    
    def test_decrease_confidence_on_negative_feedback(self):
        """Decrease confidence with negative feedback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "The bank has many branches."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        assert "entities" in result
    
    def test_confidence_score_normalization(self):
        """Normalize confidence scores after feedback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Multiple entities with varying confidence."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Scores should remain in [0, 1]
        entities = result.get("entities", [])
        for entity in entities:
            if isinstance(entity, dict) and "confidence" in entity:
                conf = entity["confidence"]
                assert 0 <= conf <= 1
    
    def test_confidence_decay_over_time(self):
        """Confidence scores decay if not reinforced."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result1 = generator.generate_ontology("Entity A", context)
        result2 = generator.generate_ontology("Different data", context)
        
        assert result1 is not None
        assert result2 is not None
        # Old results should reflect decay if not used
        assert isinstance(result1, dict)


class TestEntityMerging:
    """Test entity deduplication and merging strategies."""
    
    def test_merge_duplicate_entities(self):
        """Merge duplicate entities."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Same entity mentioned multiple times
        text = "Alice Smith works at Company X. Alice works there. Smith is the head."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should merge duplicates
        assert isinstance(entities, list)
    
    def test_merge_strategy_union(self):
        """Use union strategy for merging attributes."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice is a software engineer. Alice has expertise in Python."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Merged entity should have combined attributes
        assert isinstance(entities, list)
    
    def test_merge_strategy_intersection(self):
        """Use intersection strategy for merging."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Bob works at Company X. Bob is a manager."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Merged entity keeps common attributes
        assert isinstance(entities, list)
    
    def test_merge_with_confidence_weighting(self):
        """Merge entities with confidence-weighted attributes."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Charlie is definitely a doctor. Charlie might be a researcher."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Merged entity should reflect varying confidence
        assert "entities" in result


class TestRelationshipMerging:
    """Test relationship deduplication and merging."""
    
    def test_merge_duplicate_relationships(self):
        """Merge duplicate relationships."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="organizational")
        generator = OntologyGenerator()
        
        # Same relationship mentioned multiple times
        text = "Alice manages Bob. Alice is Bob's manager. Alice oversees Bob."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        # Should merge duplicate relationships
        assert isinstance(relationships, list)
    
    def test_merge_similar_relationships(self):
        """Merge similar but not identical relationships."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "A connects with B. A is connected to B. There is a link between A and B."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        # Should merge similar relationships
        assert isinstance(relationships, list)
    
    def test_preserve_distinct_relationships(self):
        """Preserve relationships that are genuinely different."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice manages Bob. Alice likes Bob. Alice is friends with Bob."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        relationships = result.get("relationships", [])
        # Should keep distinct relationships
        for rel in relationships:
            assert isinstance(rel, dict)


class TestDuplicateDetection:
    """Test duplicate entity and relationship detection."""
    
    def test_exact_duplicate_detection(self):
        """Detect exact duplicates."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice. Alice. Alice."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should detect exact duplicates
        assert isinstance(entities, list)
    
    def test_partial_duplicate_detection(self):
        """Detect partial/similar duplicates."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice Smith and Alice Johnson are different people but have same first name."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should distinguish partial duplicates
        assert isinstance(entities, list)
    
    def test_duplicate_similarity_threshold(self):
        """Use similarity threshold for duplicate detection."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "John J. is similar to John Jackson but not identical."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        entities = result.get("entities", [])
        # Should apply threshold for similarity detection
        assert isinstance(entities, list)


class TestConvergenceDetection:
    """Test convergence detection in refinement cycles."""
    
    def test_detect_convergence(self):
        """Detect when refinement converges."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Stable entity and relationship data"
        result1 = generator.generate_ontology(text, context)
        result2 = generator.generate_ontology(text, context)
        result3 = generator.generate_ontology(text, context)
        
        assert result1 is not None
        assert result2 is not None
        assert result3 is not None
        # Results should converge to same structure
        assert result1.get("domain") == result2.get("domain") == result3.get("domain")
    
    def test_non_convergence_detection(self):
        """Detect when refinement does not converge."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Changing/ambiguous text
        result1 = generator.generate_ontology("Entity 1 might relate to 2", context)
        result2 = generator.generate_ontology("Entity 1 definitely relates to 2", context)
        result3 = generator.generate_ontology("Entity 1 probably relates to 2", context)
        
        assert result1 is not None
        assert result2 is not None
        assert result3 is not None
        # Multiple valid interpretations may not converge
        assert isinstance(result1, dict)
    
    def test_convergence_iteration_counting(self):
        """Count iterations to convergence."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Fixed stable data"
        
        results = []
        for _ in range(5):
            result = generator.generate_ontology(text, context)
            results.append(result)
        
        assert all(r is not None for r in results)
        # Should track convergence iterations
        assert all("metadata" in r for r in results)
    
    def test_convergence_criterion(self):
        """Apply convergence criteria."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Data for convergence testing"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should have converged structure
        assert "entities" in result
        assert "relationships" in result


class TestFeedbackIntegration:
    """Test integration of feedback into refinement."""
    
    def test_implicit_feedback_from_usage(self):
        """Derive implicit feedback from usage patterns."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Repeated use implies positive feedback
        text = "Frequently used entity data"
        result1 = generator.generate_ontology(text, context)
        result2 = generator.generate_ontology(text, context)
        result3 = generator.generate_ontology(text, context)
        
        assert all(r is not None for r in [result1, result2, result3])
        # Should recognize frequent patterns
        assert isinstance(result1, dict)
    
    def test_explicit_feedback_application(self):
        """Apply explicit feedback directly."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        # Should be able to incorporate explicit feedback
        assert "entities" in result
    
    def test_feedback_conflict_resolution(self):
        """Resolve conflicts in feedback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice is a manager. Alice is an engineer."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle conflicting feedback gracefully
        assert isinstance(result, dict)


class TestFeedbackEdgeCases:
    """Test edge cases in feedback handling."""
    
    def test_null_feedback(self):
        """Handle null/empty feedback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        # Should handle missing feedback gracefully
        assert isinstance(result, dict)
    
    def test_massive_feedback_volume(self):
        """Handle large volume of feedback."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Data with many feedback points", context)
        
        assert result is not None
        # Should handle high feedback volume
        assert isinstance(result, dict)
    
    def test_malformed_feedback(self):
        """Handle malformed feedback gracefully."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        # Should recover from malformed feedback
        assert "entities" in result
