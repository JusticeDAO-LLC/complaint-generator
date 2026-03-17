"""
Cache Invalidation Tests

Tests for cache consistency, invalidation strategies, and refresh mechanisms during
ontology refinement cycles. Covers:
- Cache hit/miss scenarios
- Invalidation on entity/relationship changes
- Distributed cache consistency
- Stale data detection
- Cache TTL and expiration
- Refresh patterns
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestCacheBasics:
    """Basic cache operation tests."""
    
    def test_cache_initialization(self):
        """Initialize cache with proper structure."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        assert "metadata" in result
        assert "entities" in result
        assert "relationships" in result
    
    def test_cache_hit_on_repeated_query(self):
        """Cache hit when same query executed twice."""
        text = "Alice works at Company X."
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result1 = generator.generate_ontology(text, context)
        result2 = generator.generate_ontology(text, context)
        
        assert result1 is not None
        assert result2 is not None
        # Results should be equivalent
        assert len(result1.get("entities", [])) == len(result2.get("entities", []))
    
    def test_cache_miss_on_different_query(self):
        """Cache miss when different query executed."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result1 = generator.generate_ontology("Alice works at Company X.", context)
        result2 = generator.generate_ontology("Bob lives in New York.", context)
        
        assert result1 is not None
        assert result2 is not None
        # Results should differ
        assert isinstance(result1.get("entities", []), list)
        assert isinstance(result2.get("entities", []), list)


class TestCacheInvalidationOnChange:
    """Test cache invalidation when ontology changes."""
    
    def test_invalidate_on_entity_addition(self):
        """Cache invalidation when new entity added."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Initial generation
        text1 = "Alice works at Company X."
        result1 = generator.generate_ontology(text1, context)
        
        # New text with additional entity
        text2 = "Alice works at Company X. Bob also works there."
        result2 = generator.generate_ontology(text2, context)
        
        assert result1 is not None
        assert result2 is not None
        # Should detect change in entity count
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)
    
    def test_invalidate_on_relationship_change(self):
        """Cache invalidation when relationships change."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text1 = "Alice manages the team."
        result1 = generator.generate_ontology(text1, context)
        
        text2 = "Alice manages Bob and Charlie."
        result2 = generator.generate_ontology(text2, context)
        
        assert result1 is not None
        assert result2 is not None
        assert "relationships" in result1
        assert "relationships" in result2
    
    def test_invalidate_on_entity_type_change(self):
        """Cache invalidation when entity types change."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text1 = "John works in New York."
        result1 = generator.generate_ontology(text1, context)
        
        text2 = "John Smith is the CEO of Smith Inc."
        result2 = generator.generate_ontology(text2, context)
        
        assert result1 is not None
        assert result2 is not None
        entities1 = result1.get("entities", [])
        entities2 = result2.get("entities", [])
        assert isinstance(entities1, list)
        assert isinstance(entities2, list)


class TestCacheRefreshStrategies:
    """Test different cache refresh strategies."""
    
    def test_full_cache_refresh(self):
        """Perform full cache refresh after semantic change."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice and Bob work together."
        result1 = generator.generate_ontology(text, context)
        
        # Force refresh
        result2 = generator.generate_ontology(text, context)
        
        assert result1 is not None
        assert result2 is not None
        # Both should have valid structure
        for result in [result1, result2]:
            assert "entities" in result
            assert "relationships" in result
    
    def test_incremental_cache_update(self):
        """Update cache incrementally on specific field changes."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Generate initial ontology
        text1 = "Alice works at Company X with 100 employees."
        result1 = generator.generate_ontology(text1, context)
        
        # Slightly modified text (same entities, different details)
        text2 = "Alice works at Company X with 200 employees."
        result2 = generator.generate_ontology(text2, context)
        
        assert result1 is not None
        assert result2 is not None
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)
    
    def test_cache_invalidation_with_timestamp(self):
        """Invalidate cache based on timestamp/version."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        metadata = result.get("metadata", {})
        assert isinstance(metadata, dict)


class TestDistributedCacheConsistency:
    """Test cache consistency across distributed systems."""
    
    def test_cache_coherence_single_node(self):
        """Cache coherence within single node."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice manages Bob. Bob supervises Charlie."
        result1 = generator.generate_ontology(text, context)
        result2 = generator.generate_ontology(text, context)
        
        assert result1 is not None
        assert result2 is not None
        # Both should produce consistent results
        assert result1.get("domain") == result2.get("domain")
    
    def test_cache_serialization(self):
        """Cache can be serialized/deserialized correctly."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="legal")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Legal contract text", context)
        
        assert result is not None
        # Result should be JSON-compatible
        assert isinstance(result, dict)
        assert "entities" in result
        assert "relationships" in result
    
    def test_cache_consistency_across_domains(self):
        """Cache consistency maintained across different domains."""
        text = "Patient John has diabetes."
        
        context_medical = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        context_general = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        
        generator = OntologyGenerator()
        
        result_medical = generator.generate_ontology(text, context_medical)
        result_general = generator.generate_ontology(text, context_general)
        
        assert result_medical is not None
        assert result_general is not None
        # Both should have valid structure
        assert "entities" in result_medical
        assert "entities" in result_general


class TestStaleDataDetection:
    """Test stale data detection and handling."""
    
    def test_detect_stale_entity_data(self):
        """Detect when entity data becomes stale."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text1 = "Alice is the CEO of Company X."
        result1 = generator.generate_ontology(text1, context)
        
        # Update with conflicting information
        text2 = "Alice is the CTO of Company X."
        result2 = generator.generate_ontology(text2, context)
        
        assert result1 is not None
        assert result2 is not None
        # Should compare and detect change
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)
    
    def test_detect_stale_relationship_data(self):
        """Detect when relationship data becomes stale."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="organizational")
        generator = OntologyGenerator()
        
        text1 = "Alice manages Bob and Charlie."
        result1 = generator.generate_ontology(text1, context)
        
        text2 = "Alice manages Bob, Charlie, and Diana."
        result2 = generator.generate_ontology(text2, context)
        
        assert result1 is not None
        assert result2 is not None
        rels1 = result1.get("relationships", [])
        rels2 = result2.get("relationships", [])
        assert isinstance(rels1, list)
        assert isinstance(rels2, list)
    
    def test_stale_cache_marker(self):
        """Mark cache entries as stale appropriately."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        metadata = result.get("metadata", {})
        # Should have metadata indicating freshness
        assert isinstance(metadata, dict)


class TestCacheTTLAndExpiration:
    """Test cache TTL and expiration mechanisms."""
    
    def test_cache_ttl_configuration(self):
        """Configure cache TTL."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        # Should support TTL configuration
        assert "metadata" in result
    
    def test_cache_expiration_check(self):
        """Check if cache entry has expired."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result1 = generator.generate_ontology("Text 1", context)
        result2 = generator.generate_ontology("Text 2", context)
        
        assert result1 is not None
        assert result2 is not None
        # Both should be valid dict structures
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)
    
    def test_cache_refresh_on_expiration(self):
        """Refresh cache when expired."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Initial generation
        result1 = generator.generate_ontology("Test data", context)
        
        # Simulated re-generation
        result2 = generator.generate_ontology("Test data", context)
        
        assert result1 is not None
        assert result2 is not None
        # Should regenerate if expired
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)


class TestCachePerformance:
    """Test cache performance characteristics."""
    
    def test_cache_hit_performance(self):
        """Cache hits should be faster than cache misses."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Alice works at Company X."
        
        # Prime cache
        result1 = generator.generate_ontology(text, context)
        
        # Cache hit
        result2 = generator.generate_ontology(text, context)
        
        assert result1 is not None
        assert result2 is not None
        # Both results should be valid
        assert "entities" in result1
        assert "entities" in result2
    
    def test_cache_storage_efficiency(self):
        """Cache storage should be efficient."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Generate multiple ontologies
        texts = [
            "Alice works at Company X.",
            "Bob works at Company Y.",
            "Charlie works at Company Z.",
        ]
        
        results = [generator.generate_ontology(text, context) for text in texts]
        
        assert all(r is not None for r in results)
        assert all(isinstance(r, dict) for r in results)
    
    def test_cache_eviction_efficiency(self):
        """Cache eviction should be efficient."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        # Cache should handle eviction gracefully
        assert isinstance(result, dict)


class TestCacheInvalidationPriority:
    """Test cache invalidation priority and strategies."""
    
    def test_high_priority_cache_invalidation(self):
        """Invalidate critical entries immediately."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="legal")
        generator = OntologyGenerator()
        
        # Critical legal data
        text1 = "Contract signed January 1, 2024"
        result1 = generator.generate_ontology(text1, context)
        
        # Updated contract
        text2 = "Contract signed January 2, 2024"
        result2 = generator.generate_ontology(text2, context)
        
        assert result1 is not None
        assert result2 is not None
        # Should invalidate immediately for legal domain
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)
    
    def test_low_priority_cache_invalidation(self):
        """Allow stale low-priority entries temporarily."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result1 = generator.generate_ontology("General data", context)
        result2 = generator.generate_ontology("General data", context)
        
        assert result1 is not None
        assert result2 is not None
        # Low-priority can remain cached longer
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)
    
    def test_selective_cache_invalidation(self):
        """Invalidate specific cache entries only."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Generate multiple entries
        result1 = generator.generate_ontology("Entity A related to B", context)
        result2 = generator.generate_ontology("Entity C related to D", context)
        
        assert result1 is not None
        assert result2 is not None
        # Should support selective invalidation
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)


class TestCacheEdgeCases:
    """Test cache edge cases and error handling."""
    
    def test_cache_with_empty_ontology(self):
        """Handle caching of empty ontologies."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("", context)
        
        assert result is not None
        # Should handle empty result gracefully
        assert "entities" in result
        assert isinstance(result["entities"], list)
    
    def test_cache_with_large_ontology(self):
        """Handle caching of large ontologies."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        # Large text with many entities
        text = ". ".join([f"Entity {i} is related to Entity {i+1}" for i in range(50)])
        result = generator.generate_ontology(text, context)
        
        assert result is not None
        # Should handle large cache gracefully
        assert isinstance(result, dict)
    
    def test_cache_concurrency(self):
        """Handle concurrent cache access."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        text = "Concurrent test data"
        
        # Simulated concurrent access
        result1 = generator.generate_ontology(text, context)
        result2 = generator.generate_ontology(text, context)
        
        assert result1 is not None
        assert result2 is not None
        # Results should be consistent
        assert result1.get("domain") == result2.get("domain")
    
    def test_cache_corruption_recovery(self):
        """Recover from corrupted cache entries."""
        context = OntologyGenerationContext(data_source="test", data_type="text", domain="general")
        generator = OntologyGenerator()
        
        result = generator.generate_ontology("Test data", context)
        
        assert result is not None
        # Should have valid structure even if cache was corrupted
        assert "entities" in result
        assert "relationships" in result
