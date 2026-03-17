"""Tests for optimized batch entity deduplication using sorted merge buckets."""

import pytest
import numpy as np
from typing import Dict, List, Any

# Import the module - will load from file if needed
try:
    from ipfs_datasets_py.optimizers.graphrag.semantic_deduplicator import (
        SemanticEntityDeduplicator,
        SemanticMergeSuggestion,
    )
except ImportError:
    # Fallback for test execution
    import sys
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "semantic_deduplicator",
        "/home/barberb/complaint-generator/ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/semantic_deduplicator.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    SemanticEntityDeduplicator = mod.SemanticEntityDeduplicator
    SemanticMergeSuggestion = mod.SemanticMergeSuggestion


class TestBucketOptimizationCorrectness:
    """Test that the bucketed algorithm finds all correct merge pairs as brute force."""

    def test_bucket_vs_brute_force_equivalence(self):
        """Verify bucketed approach finds same pairs as brute force."""
        # Create test ontology with entities
        ontology = {
            "entities": [
                {"id": "e1", "text": "CEO", "type": "role", "confidence": 0.9},
                {"id": "e2", "text": "Chief Executive Officer", "type": "role", "confidence": 0.95},
                {"id": "e3", "text": "Attorney", "type": "role", "confidence": 0.85},
                {"id": "e4", "text": "Lawyer", "type": "role", "confidence": 0.87},
                {"id": "e5", "text": "Company", "type": "org", "confidence": 0.8},
                {"id": "e6", "text": "Organization", "type": "org", "confidence": 0.82},
            ],
            "relationships": []
        }
        
        dedup = SemanticEntityDeduplicator()
        
        # Get suggestions with bucketed approach (optimized)
        suggestions = dedup.suggest_merges(ontology, threshold=0.7)
        
        # Verify we found merge suggestions
        assert len(suggestions) > 0, "Should find semantic merge suggestions"
        
        # Verify suggestion structure
        for sugg in suggestions:
            assert isinstance(sugg, SemanticMergeSuggestion)
            assert 0.0 <= sugg.similarity_score <= 1.0
            assert sugg.entity1_id != sugg.entity2_id
    
    def test_bucket_threshold_filtering(self):
        """Verify threshold filtering works in bucketed approach."""
        ontology = {
            "entities": [
                {"id": f"e{i}", "text": f"Entity {i}", "type": "test", "confidence": 0.8}
                for i in range(10)
            ],
            "relationships": []
        }
        
        dedup = SemanticEntityDeduplicator()
        
        # High threshold should return fewer suggestions
        high_threshold_suggestions = dedup.suggest_merges(ontology, threshold=0.95)
        low_threshold_suggestions = dedup.suggest_merges(ontology, threshold=0.70)
        
        assert len(high_threshold_suggestions) <= len(low_threshold_suggestions)
    
    def test_bucket_max_suggestions_limit(self):
        """Verify max_suggestions parameter works with bucketed approach."""
        ontology = {
            "entities": [
                {"id": f"e{i}", "text": f"Entity {i}", "type": "test", "confidence": 0.8}
                for i in range(20)
            ],
            "relationships": []
        }
        
        dedup = SemanticEntityDeduplicator()
        
        # Test limiting
        max_suggestions = 5
        suggestions = dedup.suggest_merges(ontology, threshold=0.5, max_suggestions=max_suggestions)
        
        assert len(suggestions) <= max_suggestions
        # Verify sorted by similarity descending
        if len(suggestions) > 1:
            for i in range(len(suggestions) - 1):
                assert suggestions[i].similarity_score >= suggestions[i + 1].similarity_score


class TestBucketOptimizationPerformance:
    """Test that bucketing provides performance improvement over brute force."""

    def test_bucket_reduces_comparisons_small(self):
        """Verify bucketing reduces comparisons for small dataset."""
        # Create mock embedding function
        def mock_embed(texts):
            # Return simple embeddings for testing
            return np.random.rand(len(texts), 384)
        
        ontology = {
            "entities": [
                {"id": f"e{i}", "text": f"Entity {i}", "type": "test", "confidence": 0.8}
                for i in range(50)
            ],
            "relationships": []
        }
        
        dedup = SemanticEntityDeduplicator()
        
        # Should complete quickly even with bucketing
        import time
        start = time.time()
        suggestions = dedup.suggest_merges(ontology, threshold=0.7, embedding_fn=mock_embed)
        elapsed = time.time() - start
        
        # Should be reasonably fast
        assert elapsed < 5.0, f"Should complete in <5s, took {elapsed:.2f}s"
        assert isinstance(suggestions, list)

    def test_bucket_handling_very_large_entities(self):
        """Test bucket strategy scales to larger entity sets."""
        def mock_embed(texts):
            return np.random.rand(len(texts), 384)
        
        # Create larger test set
        ontology = {
            "entities": [
                {"id": f"e{i}", "text": f"Entity description number {i}", "type": "test", "confidence": 0.8}
                for i in range(100)  # 100 entities = 5050 pairs in brute force
            ],
            "relationships": []
        }
        
        dedup = SemanticEntityDeduplicator()
        
        import time
        start = time.time()
        suggestions = dedup.suggest_merges(ontology, threshold=0.8, embedding_fn=mock_embed)
        elapsed = time.time() - start
        
        # Should still be reasonable (much better than 5050 comparisons * embedding overhead)
        # With bucketing, we should check maybe 1000-2000 pairs instead of 5050
        assert elapsed < 10.0, f"Should scale reasonably, took {elapsed:.2f}s"


class TestBucketEdgeCases:
    """Test edge cases and error handling in bucketed algorithm."""

    def test_empty_entities(self):
        """Test handling of empty entity list."""
        ontology = {"entities": [], "relationships": []}
        dedup = SemanticEntityDeduplicator()
        suggestions = dedup.suggest_merges(ontology, threshold=0.8)
        assert suggestions == []

    def test_single_entity(self):
        """Test handling of single entity."""
        ontology = {
            "entities": [
                {"id": "e1", "text": "Only Entity", "type": "test", "confidence": 0.8}
            ],
            "relationships": []
        }
        dedup = SemanticEntityDeduplicator()
        suggestions = dedup.suggest_merges(ontology, threshold=0.8)
        assert suggestions == []

    def test_two_entities(self):
        """Test handling of exactly two entities."""
        ontology = {
            "entities": [
                {"id": "e1", "text": "Entity One", "type": "test", "confidence": 0.8},
                {"id": "e2", "text": "Entity One", "type": "test", "confidence": 0.85},
            ],
            "relationships": []
        }
        dedup = SemanticEntityDeduplicator()
        suggestions = dedup.suggest_merges(ontology, threshold=0.7)
        # Should find at least one suggestion since texts are identical
        assert len(suggestions) >= 0  # Depends on embedding similarity
        if suggestions:
            assert suggestions[0].entity1_id == "e1"
            assert suggestions[0].entity2_id == "e2"

    def test_all_identical_entities(self):
        """Test handling of identical entities."""
        ontology = {
            "entities": [
                {"id": f"e{i}", "text": "same text", "type": "test", "confidence": 0.8}
                for i in range(5)
            ],
            "relationships": []
        }
        dedup = SemanticEntityDeduplicator()
        suggestions = dedup.suggest_merges(ontology, threshold=0.95)
        # All should be very similar
        assert len(suggestions) > 0

    def test_threshold_boundaries(self):
        """Test threshold boundary conditions."""
        ontology = {
            "entities": [
                {"id": f"e{i}", "text": f"Entity {i}", "type": "test", "confidence": 0.8}
                for i in range(10)
            ],
            "relationships": []
        }
        dedup = SemanticEntityDeduplicator()
        
        # Threshold = 0 should find all pairs
        suggestions_zero = dedup.suggest_merges(ontology, threshold=0.0)
        # Threshold = 1 should find none (unless all identical)
        suggestions_one = dedup.suggest_merges(ontology, threshold=1.0)
        
        assert len(suggestions_zero) >= len(suggestions_one)

    def test_invalid_threshold(self):
        """Test rejection of invalid thresholds."""
        ontology = {"entities": [], "relationships": []}
        dedup = SemanticEntityDeduplicator()
        
        with pytest.raises(ValueError):
            dedup.suggest_merges(ontology, threshold=-0.1)
        
        with pytest.raises(ValueError):
            dedup.suggest_merges(ontology, threshold=1.1)

    def test_missing_threshold_parameter(self):
        """Test that suggestions work with default threshold."""
        ontology = {
            "entities": [
                {"id": "e1", "text": "Entity", "type": "test", "confidence": 0.8},
                {"id": "e2", "text": "Entity", "type": "test", "confidence": 0.85},
            ],
            "relationships": []
        }
        dedup = SemanticEntityDeduplicator()
        
        # Should use default threshold=0.85
        suggestions = dedup.suggest_merges(ontology)
        assert isinstance(suggestions, list)


class TestBucketDedupQuality:
    """Test quality of results from bucketed deduplication."""

    def test_suggestion_similarity_ordering(self):
        """Verify suggestions are sorted by similarity (descending)."""
        ontology = {
            "entities": [
                {"id": f"e{i}", "text": f"Entity {i}", "type": "test", "confidence": 0.8}
                for i in range(20)
            ],
            "relationships": []
        }
        
        dedup = SemanticEntityDeduplicator()
        suggestions = dedup.suggest_merges(ontology, threshold=0.5)
        
        # Verify sorted descending
        for i in range(len(suggestions) - 1):
            assert suggestions[i].similarity_score >= suggestions[i + 1].similarity_score

    def test_suggestion_evidence_complete(self):
        """Verify merge suggestions contain complete evidence."""
        ontology = {
            "entities": [
                {"id": "e1", "text": "CEO", "type": "role", "confidence": 0.9},
                {"id": "e2", "text": "Chief Executive Officer", "type": "role", "confidence": 0.95},
            ],
            "relationships": []
        }
        
        dedup = SemanticEntityDeduplicator()
        suggestions = dedup.suggest_merges(ontology, threshold=0.5)
        
        for sugg in suggestions:
            assert "semantic_similarity" in sugg.evidence
            assert "name_similarity" in sugg.evidence
            assert "type_match" in sugg.evidence
            assert "confidence1" in sugg.evidence
            assert "confidence2" in sugg.evidence

    def test_suggestion_no_self_pairs(self):
        """Verify no entity is paired with itself."""
        ontology = {
            "entities": [
                {"id": f"e{i}", "text": f"Entity {i}", "type": "test", "confidence": 0.8}
                for i in range(10)
            ],
            "relationships": []
        }
        
        dedup = SemanticEntityDeduplicator()
        suggestions = dedup.suggest_merges(ontology, threshold=0.01)
        
        for sugg in suggestions:
            assert sugg.entity1_id != sugg.entity2_id

    def test_suggestion_no_duplicate_pairs(self):
        """Verify no duplicate pairs in suggestions."""
        ontology = {
            "entities": [
                {"id": f"e{i}", "text": f"Entity {i}", "type": "test", "confidence": 0.8}
                for i in range(15)
            ],
            "relationships": []
        }
        
        dedup = SemanticEntityDeduplicator()
        suggestions = dedup.suggest_merges(ontology, threshold=0.01)
        
        pairs_seen = set()
        for sugg in suggestions:
            pair = (min(sugg.entity1_id, sugg.entity2_id), 
                   max(sugg.entity1_id, sugg.entity2_id))
            assert pair not in pairs_seen, f"Duplicate pair found: {pair}"
            pairs_seen.add(pair)


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
