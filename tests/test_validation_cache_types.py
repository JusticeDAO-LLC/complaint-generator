"""Tests for validation_cache type contracts.

This module tests the CacheStatsDict and MultiLayerCacheStatsDict TypedDict
contracts to ensure proper type safety for cache statistics.
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.validation_cache import (
    CacheStats,
    CacheStatsDict,
    MultiLayerCacheStatsDict,
    LRUCache,
    ValidationCache,
)


class TestCacheStatsDictType:
    """Tests for CacheStatsDict TypedDict structure."""
    
    def test_cache_stats_dict_has_correct_fields(self):
        """Verify CacheStatsDict has expected field names."""
        stats: CacheStatsDict = {
            "hits": 100,
            "misses": 20,
            "evictions": 5,
            "writes": 150,
            "hit_rate": 0.8333,
            "total_requests": 120,
            "total_size_mb": 15.5,
        }
        
        assert "hits" in stats
        assert "misses" in stats
        assert "evictions" in stats
        assert "writes" in stats
        assert "hit_rate" in stats
        assert "total_requests" in stats
        assert "total_size_mb" in stats
    
    def test_cache_stats_dict_field_types(self):
        """Verify field types in CacheStatsDict."""
        stats: CacheStatsDict = {
            "hits": 50,
            "misses": 10,
            "evictions": 2,
            "writes": 75,
            "hit_rate": 0.8333,
            "total_requests": 60,
            "total_size_mb": 10.25,
        }
        
        assert isinstance(stats["hits"], int)
        assert isinstance(stats["misses"], int)
        assert isinstance(stats["evictions"], int)
        assert isinstance(stats["writes"], int)
        assert isinstance(stats["hit_rate"], float)
        assert isinstance(stats["total_requests"], int)
        assert isinstance(stats["total_size_mb"], float)
    
    def test_cache_stats_dict_optional_fields(self):
        """Verify fields are optional in CacheStatsDict (total=False)."""
        partial_stats: CacheStatsDict = {
            "hits": 10,
            "misses": 2,
        }
        
        assert "hits" in partial_stats
        assert "misses" in partial_stats
        assert "evictions" not in partial_stats
    
    def test_cache_stats_dict_empty_is_valid(self):
        """Verify empty CacheStatsDict is valid (total=False)."""
        empty_stats: CacheStatsDict = {}
        
        assert isinstance(empty_stats, dict)
        assert len(empty_stats) == 0


class TestMultiLayerCacheStatsDictType:
    """Tests for MultiLayerCacheStatsDict TypedDict structure."""
    
    def test_multi_layer_cache_stats_dict_has_correct_fields(self):
        """Verify MultiLayerCacheStatsDict has expected field names."""
        stats: MultiLayerCacheStatsDict = {
            "tdfol_cache": {"hits": 10, "misses": 2, "hit_rate": 0.8333},
            "consistency_cache": {"hits": 20, "misses": 5, "hit_rate": 0.8},
            "incremental_cache": {"hits": 30, "misses": 10, "hit_rate": 0.75},
            "total_hit_rate": 0.7857,
        }
        
        assert "tdfol_cache" in stats
        assert "consistency_cache" in stats
        assert "incremental_cache" in stats
        assert "total_hit_rate" in stats
    
    def test_multi_layer_cache_stats_nested_types(self):
        """Verify nested CacheStatsDict in MultiLayerCacheStatsDict."""
        stats: MultiLayerCacheStatsDict = {
            "tdfol_cache": {"hits": 5, "misses": 1, "hit_rate": 0.8333},
            "consistency_cache": {"hits": 10, "misses": 2, "hit_rate": 0.8333},
            "incremental_cache": {"hits": 15, "misses": 3, "hit_rate": 0.8333},
            "total_hit_rate": 0.8333,
        }
        
        # Verify each layer is a CacheStatsDict-like structure
        for key in ["tdfol_cache", "consistency_cache", "incremental_cache"]:
            assert isinstance(stats[key], dict)
            assert "hits" in stats[key]
            assert "misses" in stats[key]
            assert "hit_rate" in stats[key]
        
        assert isinstance(stats["total_hit_rate"], float)
    
    def test_multi_layer_cache_stats_optional_fields(self):
        """Verify fields are optional in MultiLayerCacheStatsDict."""
        partial_stats: MultiLayerCacheStatsDict = {
            "total_hit_rate": 0.75,
        }
        
        assert "total_hit_rate" in partial_stats
        assert "tdfol_cache" not in partial_stats


class TestCacheStatsIntegration:
    """Integration tests for CacheStats.to_dict()."""
    
    def test_cache_stats_to_dict_returns_typed_dict(self):
        """Verify CacheStats.to_dict() returns CacheStatsDict structure."""
        cache_stats = CacheStats(
            hits=100,
            misses=25,
            evictions=10,
            writes=150,
            total_size_bytes=16 * 1024 * 1024,  # 16 MB
        )
        
        result = cache_stats.to_dict()
        
        # Verify all expected fields present
        assert "hits" in result
        assert "misses" in result
        assert "evictions" in result
        assert "writes" in result
        assert "hit_rate" in result
        assert "total_requests" in result
        assert "total_size_mb" in result
        
        # Verify values
        assert result["hits"] == 100
        assert result["misses"] == 25
        assert result["evictions"] == 10
        assert result["writes"] == 150
        assert result["hit_rate"] == 0.8  # 100 / 125
        assert result["total_requests"] == 125
        assert result["total_size_mb"] == 16.0
    
    def test_cache_stats_to_dict_rounds_correctly(self):
        """Verify to_dict() rounds values correctly."""
        cache_stats = CacheStats(
            hits=85,
            misses=15,
            evictions=3,
            writes=100,
            total_size_bytes=10_500_000,  # ~10.01 MB
        )
        
        result = cache_stats.to_dict()
        
        # hit_rate should be rounded to 4 decimals
        assert result["hit_rate"] == 0.85  # 85/100
        
        # total_size_mb should be rounded to 2 decimals
        expected_mb = round(10_500_000 / (1024 * 1024), 2)
        assert result["total_size_mb"] == expected_mb
    
    def test_cache_stats_to_dict_zero_requests(self):
        """Verify to_dict() handles zero requests correctly."""
        cache_stats = CacheStats(
            hits=0,
            misses=0,
            evictions=0,
            writes=0,
            total_size_bytes=0,
        )
        
        result = cache_stats.to_dict()
        
        # With zero requests, hit_rate should be 0.0
        assert result["hit_rate"] == 0.0
        assert result["total_requests"] == 0


class TestLRUCacheIntegration:
    """Integration tests with LRUCache."""
    
    def test_lru_cache_stats_returns_cache_stats_dict(self):
        """Verify LRUCache.stats.to_dict() returns CacheStatsDict."""
        cache = LRUCache(max_size=10, max_memory_mb=1.0)
        
        # Perform some cache operations
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss
        
        result = cache.stats.to_dict()
        
        # Verify structure
        assert "hits" in result
        assert "misses" in result
        assert result["hits"] == 1
        assert result["misses"] == 1
        assert result["writes"] == 1
    
    def test_lru_cache_eviction_updates_stats(self):
        """Verify cache evictions are tracked in stats."""
        cache = LRUCache(max_size=2, max_memory_mb=0.01)
        
        # Fill cache beyond capacity
        cache.set("key1", "a" * 100)
        cache.set("key2", "b" * 100)
        cache.set("key3", "c" * 100)  # Should trigger eviction
        
        result = cache.stats.to_dict()
        
        # Eviction should have occurred
        assert result["evictions"] >= 1


class TestValidationCacheIntegration:
    """Integration tests for ValidationCache.get_stats()."""
    
    def test_multi_layer_cache_get_stats_returns_typed_dict(self):
        """Verify ValidationCache.get_stats() returns MultiLayerCacheStatsDict."""
        cache = ValidationCache(max_size=100)
        
        result = cache.get_stats()
        
        # Verify top-level structure
        assert "tdfol_cache" in result
        assert "consistency_cache" in result
        assert "incremental_cache" in result
        assert "total_hit_rate" in result
        
        # Verify each nested layer is a CacheStatsDict
        assert isinstance(result["tdfol_cache"], dict)
        assert isinstance(result["consistency_cache"], dict)
        assert isinstance(result["incremental_cache"], dict)
        
        # Verify nested fields present
        assert "hits" in result["tdfol_cache"]
        assert "misses" in result["tdfol_cache"]
        assert "hit_rate" in result["tdfol_cache"]
    
    def test_multi_layer_cache_total_hit_rate_calculation(self):
        """Verify total_hit_rate is calculated correctly across layers."""
        cache = ValidationCache(max_size=100)
        
        # Perform operations on different layers
        cache.set_tdfol("key1", ["formula1"])
        cache.get_tdfol("key1")  # Hit
        
        cache.set_consistency("key2", {"result": "ok"})
        cache.get_consistency("key2")  # Hit
        
        # Get and miss on incremental
        cache.get_incremental(["e1", "e2"])  # Miss
        
        result = cache.get_stats()
        
        # Total: 2 hits, 1 miss = 2/3 ≈ 0.6667
        expected_rate = round(2 / 3, 4)
        assert result["total_hit_rate"] == expected_rate
    
    def test_multi_layer_cache_empty_stats(self):
        """Verify get_stats() works with empty caches."""
        cache = ValidationCache(max_size=100)
        
        result = cache.get_stats()
        
        # With no operations, total_hit_rate should be 0.0
        assert result["total_hit_rate"] == 0.0
        
        # All layers should have zero stats
        for layer in ["tdfol_cache", "consistency_cache", "incremental_cache"]:
            assert result[layer]["hits"] == 0
            assert result[layer]["misses"] == 0


class TestCacheStatsDictRealWorldScenarios:
    """Real-world scenario tests for cache statistics."""
    
    def test_high_hit_rate_scenario(self):
        """Simulate high cache hit rate scenario."""
        cache = LRUCache(max_size=100, max_memory_mb=10.0)
        
        # Add items
        for i in range(10):
            cache.set(f"key{i}", f"value{i}")
        
        # High hit rate - access same items repeatedly
        for _ in range(50):
            for i in range(10):
                cache.get(f"key{i}")
        
        result = cache.stats.to_dict()
        
        # Should have very high hit rate
        assert result["hits"] == 500
        assert result["misses"] == 0
        assert result["hit_rate"] == 1.0
        assert result["writes"] == 10
    
    def test_cache_eviction_tracking(self):
        """Simulate cache with many evictions."""
        cache = LRUCache(max_size=3, max_memory_mb=0.01)
        
        # Add many items to trigger evictions
        for i in range(20):
            cache.set(f"key{i}", f"value{i}")
        
        result = cache.stats.to_dict()
        
        # Should have many evictions
        assert result["evictions"] > 0
        assert result["writes"] == 20
    
    def test_mixed_cache_operations(self):
        """Simulate realistic mix of cache operations."""
        cache = LRUCache(max_size=50, max_memory_mb=5.0)
        
        # Mix of sets and gets
        for i in range(10):
            cache.set(f"key{i}", f"value{i}")
        
        # Some hits
        for i in range(5):
            cache.get(f"key{i}")
        
        # Some misses
        for i in range(10, 15):
            cache.get(f"key{i}")
        
        result = cache.stats.to_dict()
        
        assert result["hits"] == 5
        assert result["misses"] == 5
        assert result["hit_rate"] == 0.5
        assert result["writes"] == 10
        assert result["total_requests"] == 10


class TestCacheStatsDictStructure:
    """Tests verifying CacheStatsDict structure compliance."""
    
    def test_cache_stats_dict_from_to_dict_matches_type(self):
        """Verify dict from to_dict() matches CacheStatsDict structure."""
        cache_stats = CacheStats(hits=50, misses=10, evictions=2, writes=60, total_size_bytes=5_000_000)
        result = cache_stats.to_dict()
        
        # Verify exact field set
        expected_fields = {"hits", "misses", "evictions", "writes", "hit_rate", "total_requests", "total_size_mb"}
        assert set(result.keys()) == expected_fields
    
    def test_multi_layer_stats_nested_structure(self):
        """Verify MultiLayerCacheStatsDict nested structure correctness."""
        cache = ValidationCache(max_size=100)
        
        result = cache.get_stats()
        # Verify top-level keys
        expected_top_level = {"tdfol_cache", "consistency_cache", "incremental_cache", "total_hit_rate"}
        assert set(result.keys()) == expected_top_level
        
        # Verify each nested dict has CacheStatsDict fields
        for layer_key in ["tdfol_cache", "consistency_cache", "incremental_cache"]:
            layer_stats = result[layer_key]
            assert "hits" in layer_stats
            assert "misses" in layer_stats
            assert "hit_rate" in layer_stats
            assert "total_requests" in layer_stats
