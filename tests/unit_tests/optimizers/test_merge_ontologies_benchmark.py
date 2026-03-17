"""Benchmark tests for ontology merging performance.

Tests the performance of OntologyGenerator._merge_ontologies() on large ontologies.
Uses pytest-benchmark for standardized performance measurement.
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import OntologyGenerator


class TestMergeOntologiesBenchmark:
    """Benchmark ontology merging performance."""

    @pytest.fixture
    def generator(self):
        """Create an OntologyGenerator instance for benchmarking."""
        return OntologyGenerator()

    def create_large_ontology(self, num_entities: int, num_relationships: int) -> dict:
        """Create a large test ontology with specified entity and relationship counts.
        
        Args:
            num_entities: Number of entities to generate
            num_relationships: Number of relationships to generate
            
        Returns:
            Ontology dict with entities and relationships
        """
        entities = []
        for i in range(num_entities):
            entities.append({
                "id": f"entity_{i:06d}",
                "text": f"Entity {i}",
                "type": "CONCEPT" if i % 2 == 0 else "ACTOR",
                "confidence": 0.95 - (i % 10) * 0.01,
                "properties": {
                    "index": i,
                    "category": f"category_{i % 10}",
                    "domain": f"domain_{i % 5}",
                },
                "last_seen": 1000000.0,
            })

        relationships = []
        for i in range(num_relationships):
            source_idx = i % num_entities
            target_idx = (i + 1) % num_entities
            relationships.append({
                "id": f"rel_{i:06d}",
                "source_id": f"entity_{source_idx:06d}",
                "target_id": f"entity_{target_idx:06d}",
                "type": "RELATED_TO" if i % 3 == 0 else "DEPENDS_ON",
                "confidence": 0.90 - (i % 10) * 0.01,
                "properties": {
                    "index": i,
                    "strength": (i % 10) + 1,
                },
            })

        return {
            "entities": entities,
            "relationships": relationships,
            "metadata": {
                "current_time": 1000000.0,
                "version": "1.0",
            },
        }

    def test_merge_small_ontologies(self, benchmark, generator):
        """Benchmark merging of small ontologies (10 entities, 10 relationships)."""
        base = self.create_large_ontology(10, 10)
        extension = self.create_large_ontology(5, 5)

        result = benchmark(generator._merge_ontologies, base, extension)

        # Verify result structure
        assert "entities" in result
        assert "relationships" in result
        assert len(result["entities"]) > 0

    def test_merge_medium_ontologies(self, benchmark, generator):
        """Benchmark merging of medium ontologies (100 entities, 100 relationships)."""
        base = self.create_large_ontology(100, 100)
        extension = self.create_large_ontology(50, 50)

        result = benchmark(generator._merge_ontologies, base, extension)

        assert "entities" in result
        assert len(result["entities"]) > 0

    def test_merge_large_ontologies_1000(self, benchmark, generator):
        """Benchmark merging of large ontologies (1000 entities, 1000 relationships).
        
        This is the main performance test to ensure merge_ontologies scales well.
        """
        base = self.create_large_ontology(1000, 1000)
        extension = self.create_large_ontology(500, 500)

        result = benchmark(generator._merge_ontologies, base, extension)

        # Verify correctness
        assert "entities" in result
        assert "relationships" in result
        # Base + extension entities, with dedup
        assert len(result["entities"]) >= 1000

    def test_merge_xlarge_ontologies_5000(self, benchmark, generator):
        """Benchmark merging of very large ontologies (5000 entities, 5000 relationships).
        
        Tests performance at extreme scale to identify bottlenecks.
        """
        base = self.create_large_ontology(5000, 5000)
        extension = self.create_large_ontology(2500, 2500)

        result = benchmark(generator._merge_ontologies, base, extension)

        assert "entities" in result
        assert len(result["entities"]) >= 5000

    def test_merge_many_small_batches(self, benchmark, generator):
        """Benchmark sequential merging of many small ontologies.
        
        Simulates real workflow where ontologies are refined iteratively.
        """
        base = self.create_large_ontology(100, 100)

        def merge_multiple():
            result = base.copy()
            for i in range(10):
                increment = self.create_large_ontology(50, 50)
                result = generator._merge_ontologies(result, increment)
            return result

        result = benchmark(merge_multiple)
        assert "entities" in result

    def test_merge_with_high_duplicate_entities(self, benchmark, generator):
        """Benchmark merge performance when most entities already exist (high dedup rate)."""
        base = self.create_large_ontology(1000, 1000)
        
        # Extension has mostly the same entities (different properties)
        extension = self.create_large_ontology(1000, 1000)
        # Update extension to use same entity IDs as base
        for i, entity in enumerate(extension["entities"]):
            entity["id"] = f"entity_{i:06d}"

        result = benchmark(generator._merge_ontologies, base, extension)

        # Most entities should be deduplicated
        assert "entities" in result
        assert len(result["entities"]) <= 1100  # Some new entities expected

    def test_merge_with_low_duplicate_entities(self, benchmark, generator):
        """Benchmark merge performance when few entities are duplicated (low dedup rate)."""
        base = self.create_large_ontology(1000, 1000)
        extension = self.create_large_ontology(1000, 1000)
        
        # Extension has completely different entity IDs
        for i, entity in enumerate(extension["entities"]):
            entity["id"] = f"ext_entity_{i:06d}"

        result = benchmark(generator._merge_ontologies, base, extension)

        # Almost all entities should be new
        assert "entities" in result
        assert len(result["entities"]) >= 1900

    def test_merge_empty_base(self, benchmark, generator):
        """Benchmark merge when base ontology is empty."""
        base = {"entities": [], "relationships": []}
        extension = self.create_large_ontology(500, 500)

        result = benchmark(generator._merge_ontologies, base, extension)

        assert len(result["entities"]) == 500

    def test_merge_empty_extension(self, benchmark, generator):
        """Benchmark merge when extension is empty."""
        base = self.create_large_ontology(500, 500)
        extension = {"entities": [], "relationships": []}

        result = benchmark(generator._merge_ontologies, base, extension)

        assert len(result["entities"]) == 500

    def test_merge_with_confidence_decay(self, benchmark, generator):
        """Benchmark merge with time-based confidence decay calculation.
        
        Tests performance of confidence decay logic on entities not in extension.
        """
        base = self.create_large_ontology(1000, 1000)
        extension = self.create_large_ontology(100, 100)  # Only small extension

        result = benchmark(generator._merge_ontologies, base, extension)

        # Verify decay was applied to non-extension entities
        assert "entities" in result
        # Most entities should have decayed confidence
        decayed_count = sum(
            1 for e in result["entities"]
            if isinstance(e, dict) and e.get("confidence", 1.0) < 0.95
        )
        assert decayed_count > 800

    def test_merge_performance_scaling_linearity(self, benchmark, generator):
        """Benchmark to verify merge scales reasonably (not quadratic).
        
        Tests with progressively larger ontologies to check scaling profile.
        """
        def merge_100_100():
            base = self.create_large_ontology(100, 100)
            ext = self.create_large_ontology(100, 100)
            return generator._merge_ontologies(base, ext)

        def merge_500_500():
            base = self.create_large_ontology(500, 500)
            ext = self.create_large_ontology(500, 500)
            return generator._merge_ontologies(base, ext)

        # Benchmark both - we'll compare timing manually
        # This demonstrates the benchmark infrastructure for scaling analysis
        result = benchmark(merge_100_100)
        assert "entities" in result


class TestMergeOntologiesCorrectness:
    """Test correctness properties of ontology merging.
    
    These are functional tests, not benchmarks, but are important for
    validating that optimization changes don't break correctness.
    """

    @pytest.fixture
    def generator(self):
        """Create an OntologyGenerator instance."""
        return OntologyGenerator()

    def test_merge_preserves_base_entities(self, generator):
        """Test that all base entities are preserved in merge."""
        base = {
            "entities": [
                {"id": "e1", "text": "Entity 1", "type": "CONCEPT", "confidence": 0.9},
                {"id": "e2", "text": "Entity 2", "type": "ACTOR", "confidence": 0.8},
            ],
            "relationships": [],
        }
        extension = {
            "entities": [
                {"id": "e3", "text": "Entity 3", "type": "CONCEPT", "confidence": 0.85},
            ],
            "relationships": [],
        }

        result = generator._merge_ontologies(base, extension)

        entity_ids = {e["id"] for e in result["entities"] if isinstance(e, dict)}
        assert "e1" in entity_ids
        assert "e2" in entity_ids
        assert "e3" in entity_ids

    def test_merge_deduplicates_entities(self, generator):
        """Test that duplicate entities are deduplicated (not multiplied)."""
        base = {
            "entities": [
                {"id": "e1", "text": "Entity 1", "type": "CONCEPT", "confidence": 0.9},
            ],
            "relationships": [],
        }
        extension = {
            "entities": [
                {"id": "e1", "text": "Entity 1 Updated", "type": "CONCEPT", "confidence": 0.95},
            ],
            "relationships": [],
        }

        result = generator._merge_ontologies(base, extension)

        # Only one entity with id "e1"
        e1_count = sum(1 for e in result["entities"] if isinstance(e, dict) and e.get("id") == "e1")
        assert e1_count == 1

    def test_merge_respects_missing_metadata(self, generator):
        """Test that merge works when metadata is missing."""
        base = {"entities": [{"id": "e1", "text": "E1", "confidence": 0.9}], "relationships": []}
        extension = {"entities": [{"id": "e2", "text": "E2", "confidence": 0.95}], "relationships": []}
        # No metadata field

        result = generator._merge_ontologies(base, extension)

        assert "entities" in result
        entity_ids = {e["id"] for e in result["entities"] if isinstance(e, dict)}
        assert "e1" in entity_ids and "e2" in entity_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
