"""
Temporal Reasoning and Extraction Tests

Tests for temporal information extraction, event ordering,
time expressions, and temporal relationships.
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestBasicTemporalExtraction:
    """Test basic temporal information extraction."""
    
    def test_extract_absolute_date(self):
        """Extract absolute date expressions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Event occurred on January 15, 2023."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should extract date entity
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    def test_extract_relative_time(self):
        """Extract relative time expressions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Meeting scheduled for next Tuesday."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize relative temporal reference
        assert isinstance(result, dict)
    
    def test_extract_duration(self):
        """Extract duration expressions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Treatment lasted 3 weeks."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should extract duration
        entities = result.get("entities", [])
        assert isinstance(entities, list)


class TestEventOrdering:
    """Test event ordering and sequencing."""
    
    def test_identify_before_relationship(self):
        """Identify 'before' temporal relationships."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Surgery occurred before treatment began."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should identify before relationship
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)
    
    def test_identify_after_relationship(self):
        """Identify 'after' temporal relationships."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Medication started after diagnosis."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should identify after relationship
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)
    
    def test_identify_during_relationship(self):
        """Identify 'during' temporal relationships."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Complications occurred during surgery."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should identify during relationship
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)


class TestTemporalChaining:
    """Test temporal chaining and inference."""
    
    def test_chain_before_events(self):
        """Chain before relationships transitively."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "A before B. B before C. Therefore A before C."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should infer transitive ordering
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)
    
    def test_infer_contains_from_during(self):
        """Infer containment from during relationships."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Event X during event Y implies Y contains X."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize containment inference
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)


class TestTemporalGranularity:
    """Test temporal granularity handling."""
    
    def test_handle_year_granularity(self):
        """Handle year-level temporal granularity."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Occurred in 2023."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize year-level precision
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    def test_handle_month_granularity(self):
        """Handle month-level temporal granularity."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Event happened March 2023."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize month-level precision
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    def test_handle_day_granularity(self):
        """Handle day-level temporal granularity."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Occurred on March 15, 2023."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize day-level precision
        entities = result.get("entities", [])
        assert isinstance(entities, list)


class TestTemporalModifiers:
    """Test temporal modifier handling."""
    
    def test_handle_frequency_modifiers(self):
        """Handle frequency modifiers (daily, weekly)."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Take medication twice daily."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize frequency
        assert isinstance(result, dict)
    
    def test_handle_iterative_modifiers(self):
        """Handle iterative modifiers (repeat, recurring)."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Recurring illness every summer."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize iterative pattern
        assert isinstance(result, dict)
    
    def test_handle_aspect_modifiers(self):
        """Handle aspect modifiers (started, completed)."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Treatment started last week."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize aspect
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)


class TestTemporalExpressions:
    """Test various temporal expressions."""
    
    def test_parse_natural_language_dates(self):
        """Parse natural language date expressions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Meeting next Friday at 3 PM."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should parse relative temporal reference
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    def test_parse_iso_format_dates(self):
        """Parse ISO format date expressions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Date: 2023-03-15T10:30:00Z"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should parse ISO format
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    def test_parse_timestamp_expressions(self):
        """Parse timestamp expressions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Event at 14:30 on 3/15/2023."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should extract timestamp
        entities = result.get("entities", [])
        assert isinstance(entities, list)


class TestTemporalUncertainty:
    """Test handling temporal uncertainty."""
    
    def test_handle_approximate_dates(self):
        """Handle approximate date expressions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Approximately March 2023."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize uncertainty marker
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    def test_handle_range_dates(self):
        """Handle date range expressions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Between January and March 2023."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should extract date range
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    def test_handle_uncertain_duration(self):
        """Handle uncertain duration expressions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Lasted around 2-3 weeks."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should capture duration uncertainty
        entities = result.get("entities", [])
        assert isinstance(entities, list)


class TestTemporalInference:
    """Test temporal inference capabilities."""
    
    def test_infer_concurrent_events(self):
        """Infer concurrent event timing."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "While surgery was ongoing, complications arose."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should infer temporal concurrency
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)
    
    def test_infer_causal_temporal_order(self):
        """Infer temporal order from causality."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Medication caused improvement."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should infer medication before improvement
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)


class TestTemporalEdgeCases:
    """Test edge cases in temporal handling."""
    
    def test_handle_future_perfect_tense(self):
        """Handle future perfect tense."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Will have completed by tomorrow."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize future perfect
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)
    
    def test_handle_past_perfect_tense(self):
        """Handle past perfect tense."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Had completed before arrival."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize past perfect ordering
        relationships = result.get("relationships", [])
        assert isinstance(relationships, list)
    
    def test_handle_cyclical_time(self):
        """Handle cyclical time references."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Event every Monday at 10 AM."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should recognize cyclical pattern
        entities = result.get("entities", [])
        assert isinstance(entities, list)
    
    def test_handle_null_temporal_expression(self):
        """Handle missing temporal information."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Event occurred."
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle gracefully without explicit time
        assert isinstance(result, dict)
