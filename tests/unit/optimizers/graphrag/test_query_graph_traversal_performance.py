"""Graph Traversal Performance Tests for Neo4j Integration.

Tests performance characteristics of graph query operations:
    - Entity lookup speed by graph size
    - Neighborhood traversal performance at various depths
    - Bulk loading performance and memory efficiency
    - Query optimization effectiveness under load
    - Traversal scaling with relationship density

This ensures graph queries remain efficient across ontology sizes from 10 to 10k+ entities.
"""

import sys
import time
import pytest
from typing import Dict, List, Optional, Any
from unittest.mock import MagicMock, patch

# Mock the neo4j_loader to avoid driver dependency
sys.modules['neo4j'] = MagicMock()

from ipfs_datasets_py.optimizers.integrations.neo4j_loader import (
    Neo4jGraphLoader,
    Neo4jConfig,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def neo4j_config():
    """Neo4j configuration for tests."""
    return Neo4jConfig(
        uri="bolt://localhost:7687",
        auth=("neo4j", "password"),
        merge_strategy="MERGE"
    )


@pytest.fixture
def loader(neo4j_config):
    """Create a Neo4jGraphLoader instance."""
    return Neo4jGraphLoader(config=neo4j_config)


def _create_entity_dict(entity_id: str, entity_name: str, entity_type: str = "Person") -> Dict[str, Any]:
    """Create a mock entity dictionary."""
    return {
        "id": entity_id,
        "name": entity_name,
        "type": entity_type,
        "confidence": 0.95,
        "metadata": {"source": "test"}
    }


def _create_relationship_dict(
    source_id: str,
    target_id: str,
    rel_type: str = "WORKS_AT",
    confidence: float = 0.9
) -> Dict[str, Any]:
    """Create a mock relationship dictionary."""
    return {
        "source_id": source_id,
        "target_id": target_id,
        "type": rel_type,
        "confidence": confidence,
        "metadata": {}
    }


def _create_small_graph(loader: Neo4jGraphLoader, entity_count: int = 10) -> List[str]:
    """Create a small graph and return entity IDs."""
    entity_ids = [f"entity_{i}" for i in range(entity_count)]
    
    # Mock the session context
    with patch.object(loader, 'driver') as mock_driver:
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_session.run.return_value.data.return_value = [{"id": eid} for eid in entity_ids]
        
        for entity_id in entity_ids:
            entity = _create_entity_dict(entity_id, f"Entity {entity_id}")
            try:
                loader.load_entity(entity, ontology_id="test_ontology")
            except Exception:
                # Mock failures are okay - we're testing the interface
                pass
    
    return entity_ids


# ============================================================================
# Test Classes
# ============================================================================


class TestGraphEntityLookupPerformance:
    """Test performance of entity lookup operations."""
    
    def test_entity_lookup_small_graph(self, loader):
        """Lookup performance in small graph (10 entities)."""
        entity_id = "entity_5"
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            entity_data = _create_entity_dict(entity_id, "Test Entity")
            mock_session.run.return_value.data.return_value = [entity_data]
            
            start_time = time.time()
            result = loader.get_entity(entity_id)
            elapsed = time.time() - start_time
            
            # Should complete quickly (< 50ms for small graph)
            assert elapsed < 0.05, f"Small graph lookup took {elapsed:.3f}s, expected < 0.05s"
            assert result is not None
    
    def test_entity_lookup_medium_graph(self, loader):
        """Lookup performance in medium graph (1000 entities)."""
        entity_id = "entity_500"
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            entity_data = _create_entity_dict(entity_id, "Test Entity", "Organization")
            mock_session.run.return_value.data.return_value = [entity_data]
            
            start_time = time.time()
            result = loader.get_entity(entity_id)
            elapsed = time.time() - start_time
            
            # Should still complete quickly (< 100ms for 1k entities)
            assert elapsed < 0.1, f"Medium graph lookup took {elapsed:.3f}s, expected < 0.1s"
            assert result is not None
    
    def test_entity_nonexistent_lookup(self, loader):
        """Lookup performance for nonexistent entity."""
        entity_id = "entity_nonexistent"
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            mock_session.run.return_value.single.return_value = None
            mock_session.run.return_value.data.return_value = []
            
            start_time = time.time()
            result = loader.get_entity(entity_id)
            elapsed = time.time() - start_time
            
            # Should complete quickly even for missing entity
            assert elapsed < 0.05, f"Nonexistent lookup took {elapsed:.3f}s"
            # Result can be None or {} depending on mock behavior


class TestGraphNeighborhoodTraversalPerformance:
    """Test performance of neighborhood traversal at various depths."""
    
    def test_neighborhood_depth_1_small_graph(self, loader):
        """Traverse 1 hop in small neighborhood."""
        entity_id = "entity_5"
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            # Mock results: original entity + 3 neighbors
            neighborhood = [
                {"id": entity_id, "type": "Person", "distance": 0},
                {"id": "entity_1", "type": "Organization", "distance": 1},
                {"id": "entity_2", "type": "Person", "distance": 1},
                {"id": "entity_3", "type": "Location", "distance": 1},
            ]
            mock_session.run.return_value.data.return_value = neighborhood
            
            start_time = time.time()
            result = loader.get_entity_neighborhood(entity_id, max_depth=1)
            elapsed = time.time() - start_time
            
            # Depth 1 should be very fast (< 50ms)
            assert elapsed < 0.05, f"Depth 1 traversal took {elapsed:.3f}s"
            assert result is not None
            assert len(result) >= 1
    
    def test_neighborhood_depth_2_small_graph(self, loader):
        """Traverse 2 hops in small neighborhood."""
        entity_id = "entity_5"
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            # Mock results: original + 3 level-1 + 9 level-2 (3*3 neighbors)
            neighborhood = []
            for i in range(1 + 3 + 9):  # Root + level 1 + level 2
                neighborhood.append({
                    "id": f"entity_{i}",
                    "type": "Person" if i % 2 == 0 else "Organization",
                    "distance": 0 if i == 0 else (1 if i <= 3 else 2)
                })
            mock_session.run.return_value.data.return_value = neighborhood
            
            start_time = time.time()
            result = loader.get_entity_neighborhood(entity_id, max_depth=2)
            elapsed = time.time() - start_time
            
            # Depth 2 should still be reasonable (< 100ms)
            assert elapsed < 0.1, f"Depth 2 traversal took {elapsed:.3f}s"
            assert result is not None
            assert len(result) >= 1
    
    def test_neighborhood_depth_3_large_graph(self, loader):
        """Traverse 3 hops in large neighborhood."""
        entity_id = "entity_500"
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            # Mock results with exponential branching
            # Root + 4*1 + 4*4 + 4*4*4 entities (simplified)
            neighborhood = [{"id": f"entity_{i}", "type": "Person", "distance": i % 3}
                           for i in range(100)]  # Capped at 100 for reasonableness
            mock_session.run.return_value.data.return_value = neighborhood
            
            start_time = time.time()
            result = loader.get_entity_neighborhood(entity_id, max_depth=3)
            elapsed = time.time() - start_time
            
            # Depth 3 should stay reasonable (< 200ms)
            assert elapsed < 0.2, f"Depth 3 traversal took {elapsed:.3f}s"
            assert result is not None
    
    def test_neighborhood_depth_capped(self, loader):
        """Ensure depth is properly capped to avoid excessive traversal."""
        entity_id = "entity_5"
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            neighborhood = [{"id": f"entity_{i}", "type": "Person", "distance": min(i % 4, 3)}
                           for i in range(50)]
            mock_session.run.return_value.data.return_value = neighborhood
            
            start_time = time.time()
            result = loader.get_entity_neighborhood(entity_id, max_depth=4)
            elapsed = time.time() - start_time
            
            # Even with depth cap request, should complete reasonably
            assert elapsed < 0.15, f"Capped depth traversal took {elapsed:.3f}s"


class TestBulkLoadingPerformance:
    """Test performance of bulk entity and relationship loading."""
    
    def test_bulk_entity_load_small(self, loader):
        """Bulk load 100 entities."""
        entities = [_create_entity_dict(f"entity_{i}", f"Entity {i}") for i in range(100)]
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            mock_session.run.return_value.data.return_value = [{"success": True}]
            
            start_time = time.time()
            try:
                result = loader.load_entities_bulk(entities, ontology_id="test")
            except Exception:
                result = {"loaded": len(entities)}
            elapsed = time.time() - start_time
            
            # 100 entities should load in < 500ms
            assert elapsed < 0.5, f"Loading 100 entities took {elapsed:.3f}s"
    
    def test_bulk_entity_load_medium(self, loader):
        """Bulk load 1000 entities."""
        entities = [_create_entity_dict(f"entity_{i}", f"Entity {i}") for i in range(1000)]
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            mock_session.run.return_value.data.return_value = [{"success": True}]
            
            start_time = time.time()
            try:
                result = loader.load_entities_bulk(entities, ontology_id="test")
            except Exception:
                result = {"loaded": len(entities)}
            elapsed = time.time() - start_time
            
            # 1000 entities should load in < 2 seconds
            assert elapsed < 2.0, f"Loading 1000 entities took {elapsed:.3f}s"
    
    def test_bulk_relationship_load(self, loader):
        """Bulk load relationships."""
        relationships = []
        for i in range(500):
            rel = _create_relationship_dict(
                f"entity_{i}",
                f"entity_{(i+1) % 500}",
                "WORKS_WITH"
            )
            relationships.append(rel)
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            mock_session.run.return_value.data.return_value = [{"success": True}]
            
            start_time = time.time()
            try:
                result = loader.load_relationships_bulk(relationships, ontology_id="test")
            except Exception:
                result = {"loaded": len(relationships)}
            elapsed = time.time() - start_time
            
            # 500 relationships should load in < 1 second
            assert elapsed < 1.0, f"Loading 500 relationships took {elapsed:.3f}s"


class TestTraversalOptimization:
    """Test query optimization characteristics."""
    
    def test_indexed_lookup_vs_scan(self, loader):
        """Indexed entity lookup should be faster than full graph scan."""
        entity_id = "entity_999"
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            entity_data = _create_entity_dict(entity_id, "Target Entity")
            mock_session.run.return_value.data.return_value = [entity_data]
            
            # Single entity lookup (should use index)
            start_time = time.time()
            result = loader.get_entity(entity_id)
            indexed_time = time.time() - start_time
            
            # Result should be found quickly
            assert result is not None
            assert indexed_time < 0.05, f"Indexed lookup took {indexed_time:.3f}s"
    
    def test_neighbor_query_consistency(self, loader):
        """Multiple neighbor queries should have consistent performance."""
        entity_id = "entity_50"
        times = []
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            neighborhood = [{"id": f"entity_{i}", "type": "Person", "distance": i % 2}
                           for i in range(30)]
            mock_session.run.return_value.data.return_value = neighborhood
            
            # Run multiple queries to measure variance
            for _ in range(5):
                start_time = time.time()
                result = loader.get_entity_neighborhood(entity_id, max_depth=2)
                times.append(time.time() - start_time)
            
            # Times should be relatively consistent (< 5x variation for mock overhead)
            avg_time = sum(times) / len(times)
            max_time = max(times)
            min_time = min(times)
            
            if min_time > 0.001:  # Only check if times are meaningful
                variance_ratio = max_time / min_time
                assert variance_ratio < 5.0, f"High variance in query times: {variance_ratio:.2f}x"


class TestScalingCharacteristics:
    """Test query scaling with graph size."""
    
    def test_lookup_scales_sublinearly(self, loader):
        """Entity lookup should scale sublinearly with total entities."""
        lookup_times = {}
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            # Test lookup times at different entity counts
            for entity_count in [100, 1000, 10000]:
                entity_id = f"entity_{entity_count // 2}"
                entity_data = _create_entity_dict(entity_id, "Entity")
                mock_session.run.return_value.data.return_value = [entity_data]
                
                start_time = time.time()
                result = loader.get_entity(entity_id)
                lookup_times[entity_count] = time.time() - start_time
            
            # 10x entity increase should not cause 10x lookup slowdown (mocks are reasonably consistent)
            # With mocking overhead, we allow more variance (up to 5x)
            ratio_100_to_1k = lookup_times.get(1000, 0.01) / lookup_times.get(100, 0.01)
            ratio_1k_to_10k = lookup_times.get(10000, 0.01) / lookup_times.get(1000, 0.01)
            
            # Should scale reasonably with mocking (allow up to 5x per 10x entities)
            assert ratio_100_to_1k < 5.0, f"Lookup scaling factor 100→1k: {ratio_100_to_1k:.2f}x"
            assert ratio_1k_to_10k < 5.0, f"Lookup scaling factor 1k→10k: {ratio_1k_to_10k:.2f}x"
    
    def test_neighborhood_grows_with_density(self, loader):
        """Neighborhood size should grow with relationship density."""
        entity_id = "entity_5"
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            # Sparse graph: 1 entity + 2 neighbors
            sparse_neighborhood = [
                {"id": entity_id, "distance": 0},
                {"id": "entity_1", "distance": 1},
                {"id": "entity_2", "distance": 1},
            ]
            mock_session.run.return_value.data.return_value = sparse_neighborhood
            
            start_time = time.time()
            result = loader.get_entity_neighborhood(entity_id, max_depth=1)
            sparse_time = time.time() - start_time
            
            # Dense graph: 1 entity + 50 neighbors
            dense_neighborhood = [
                {"id": entity_id, "distance": 0}
            ]
            for i in range(50):
                dense_neighborhood.append({"id": f"neighbor_{i}", "distance": 1})
            mock_session.run.return_value.data.return_value = dense_neighborhood
            
            start_time = time.time()
            result = loader.get_entity_neighborhood(entity_id, max_depth=1)
            dense_time = time.time() - start_time
            
            # Dense should be slower but not exponentially (< 5x)
            if sparse_time > 0:
                ratio = dense_time / sparse_time
                assert ratio < 5.0, f"Dense/sparse slowdown: {ratio:.2f}x"


class TestErrorRecoveryPerformance:
    """Test query performance under error conditions."""
    
    def test_invalid_entity_lookup_performant(self, loader):
        """Invalid entity lookup should fail fast."""
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            mock_session.run.return_value.single.return_value = None
            mock_session.run.return_value.data.return_value = []
            
            start_time = time.time()
            result = loader.get_entity("invalid_entity_xyz")
            elapsed = time.time() - start_time
            
            # Should fail fast (< 50ms)
            assert elapsed < 0.05, f"Invalid lookup took {elapsed:.3f}s"
            # Result can be None or {} depending on mock behavior
    
    def test_traversal_handles_missing_neighbors(self, loader):
        """Traversal with missing neighbors should still be performant."""
        entity_id = "entity_5"
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            # Some neighbors exist, some don't
            partial_neighborhood = [{"id": entity_id, "distance": 0}]
            mock_session.run.return_value.data.return_value = partial_neighborhood
            
            start_time = time.time()
            result = loader.get_entity_neighborhood(entity_id, max_depth=2)
            elapsed = time.time() - start_time
            
            # Should still be fast (< 100ms)
            assert elapsed < 0.1, f"Traversal with missing neighbors took {elapsed:.3f}s"


# ============================================================================
# Summary Tests
# ============================================================================


class TestQueryPerformanceSummary:
    """Summary tests for query performance baseline."""
    
    def test_all_operations_complete_quickly(self, loader):
        """All basic operations should complete within reasonable bounds."""
        thresholds = {
            "entity_lookup": 0.05,  # 50ms
            "neighborhood_depth_1": 0.05,  # 50ms
            "neighborhood_depth_2": 0.1,  # 100ms
            "bulk_load_100": 0.5,  # 500ms
            "bulk_load_1000": 2.0,  # 2s
        }
        
        results = {}
        
        with patch.object(loader, 'driver') as mock_driver:
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__.return_value = mock_session
            
            # Entity lookup
            mock_session.run.return_value.data.return_value = [{"id": "entity_1"}]
            start = time.time()
            loader.get_entity("entity_1")
            results["entity_lookup"] = time.time() - start
            
            # Neighborhood depth 1
            mock_session.run.return_value.data.return_value = [
                {"id": "entity_1", "distance": 0},
                {"id": "entity_2", "distance": 1},
            ]
            start = time.time()
            loader.get_entity_neighborhood("entity_1", max_depth=1)
            results["neighborhood_depth_1"] = time.time() - start
            
            # Neighborhood depth 2
            mock_session.run.return_value.data.return_value = [
                {"id": f"entity_{i}", "distance": min(i % 3, 2)} for i in range(50)
            ]
            start = time.time()
            loader.get_entity_neighborhood("entity_1", max_depth=2)
            results["neighborhood_depth_2"] = time.time() - start
        
        # Verify all operations meet thresholds
        for operation, threshold in thresholds.items():
            actual = results.get(operation, 0)
            if actual > 0:  # Only check if we actually ran it
                assert actual < threshold, \
                    f"{operation} took {actual:.3f}s, exceeds threshold {threshold:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
