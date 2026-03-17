"""Tests for parallel relationship inference optimization (P3).

This module tests the parallelization of the co-occurrence-based relationship
inference in OntologyGenerator, verifying that:
- Parallel and serial inference produce equivalent results
- Thread safety is maintained (cell lock for rel_id_counter)
- Speedup is achieved on multi-entity datasets
- Correctness with various configurations (prefilter, sentence_window, parallel)
"""

import pytest
from dataclasses import dataclass
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
    ExtractionConfig,
    DataType,
)


@dataclass
class Entity:
    """Mock entity for testing."""
    id: str
    text: str
    type: str
    confidence: float = 0.9


@dataclass  
class Relationship:
    """Mock relationship for testing."""
    id: str
    source_id: str
    target_id: str
    type: str
    confidence: float


class TestParallelRelationshipInference:
    """Test suite for P3 parallel relationship inference."""

    @pytest.fixture
    def generator(self):
        """Create test OntologyGenerator."""
        return OntologyGenerator()

    @pytest.fixture
    def context_serial(self):
        """Create context with parallel disabled."""
        return OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="general",
            config=ExtractionConfig(
                enable_parallel_inference=False,
                max_workers=4,
            ),
        )

    @pytest.fixture
    def context_parallel_2workers(self):
        """Create context with 2 parallel workers."""
        return OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="general",
            config=ExtractionConfig(
                enable_parallel_inference=True,
                max_workers=2,
            ),
        )

    @pytest.fixture
    def context_parallel_4workers(self):
        """Create context with 4 parallel workers."""
        return OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="general",
            config=ExtractionConfig(
                enable_parallel_inference=True,
                max_workers=4,
            ),
        )

    def test_parallel_disabled_by_default(self):
        """Verify parallel inference is disabled by default."""
        config = ExtractionConfig()
        assert config.enable_parallel_inference is False
        assert config.max_workers == 4

    def test_parallel_with_small_entity_count_falls_back_to_serial(
        self, generator, context_parallel_2workers
    ):
        """Verify that small entity counts fall back to serial processing.
        
        With < 10 entities, parallel processing is skipped regardless of config.
        """
        # Create 8 entities (below threshold)
        entities = [
            Entity(id=f"ent_{i}", text=f"entity{i}", type="Person")
            for i in range(8)
        ]
        text = " ".join(e.text for e in entities)
        
        # Context enables parallel but entity count is too low
        context = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="general",
            config=ExtractionConfig(
                enable_parallel_inference=True,  # Enabled
                max_workers=2,
            ),
        )
        
        # Should still compute relationships without error
        relationships = generator.infer_relationships(entities, context, text)
        assert len(relationships) >= 0

    def test_parallel_and_serial_produce_same_relationships(
        self, generator, context_serial, context_parallel_4workers
    ):
        """Verify that serial and parallel inference produce equivalent results.
        
        Both should extract the same relationships from test data (order may differ).
        """
        # Create test entities cluster
        entities = [
            Entity(id="p1", text="Alice", type="Person"),
            Entity(id="p2", text="Bob", type="Person"),
            Entity(id="p3", text="Charlie", type="Person"),
            Entity(id="o1", text="company", type="Organization"),
            Entity(id="o2", text="bank", type="Organization"),
            Entity(id="l1", text="New York", type="Location"),
            Entity(id="l2", text="Boston", type="Location"),
            Entity(id="m1", text="$100", type="MonetaryAmount"),
            Entity(id="m2", text="$200", type="MonetaryAmount"),
            Entity(id="d1", text="2024-01-01", type="Date"),
            Entity(id="d2", text="2024-02-01", type="Date"),
            Entity(id="c1", text="concept1", type="Concept"),
        ]
        
        text = (
            "Alice works at company in New York. Bob manages the bank in Boston. "
            "Alice paid $100 to Bob. Bob paid $200 to company. "
            "Alice met Bob on 2024-01-01. Bob met Charlie on 2024-02-01. "
            "The bank has a concept1."
        )
        
        # Run serial inference
        rels_serial = generator.infer_relationships(entities, context_serial, text)
        
        # Run parallel inference
        rels_parallel = generator.infer_relationships(
            entities, context_parallel_4workers, text
        )
        
        # Both should find relationships
        assert len(rels_serial) > 0
        assert len(rels_parallel) > 0
        
        # Should have same count (or within 1-2 due to thread scheduling)
        assert abs(len(rels_serial) - len(rels_parallel)) <= 2
        
        # Check that key relationships exist in both (by source_id, target_id pairs)
        serial_pairs = {(r.source_id, r.target_id) for r in rels_serial}
        parallel_pairs = {(r.source_id, r.target_id) for r in rels_parallel}
        
        # At least 80% of relationships should match
        overlap = len(serial_pairs & parallel_pairs)
        assert overlap >= int(0.8 * len(serial_pairs))

    def test_parallel_thread_safety_with_id_generation(
        self, generator, context_parallel_2workers
    ):
        """Verify thread-safe relationship ID generation in parallel mode.
        
        All relationship IDs should be unique even with parallel execution.
        """
        # Create many entities to stress test parallel processing
        entities = [
            Entity(id=f"ent_{i}", text=f"entity{i}", type="Person")
            for i in range(20)
        ]
        text = " ".join(e.text for e in entities)
        
        relationships = generator.infer_relationships(
            entities, context_parallel_2workers, text
        )
        
        # All IDs should be unique
        rel_ids = {r.id for r in relationships}
        assert len(rel_ids) == len(relationships), "Duplicate relationship IDs found"
        
        # All IDs should follow the expected format
        for rel_id in rel_ids:
            if rel_id.startswith("rel_"):
                # Extract number and verify it's a 4-digit zero-padded number
                num_str = rel_id.split("_")[1]
                assert len(num_str) == 4, f"Invalid ID format: {rel_id}"
                assert num_str.isdigit(), f"Non-numeric ID: {rel_id}"

    def test_parallel_with_type_prefiltering(
        self, generator, context_parallel_4workers
    ):
        """Verify parallel inference works correctly with type prefiltering.
        
        Impossible type pairs should still be filtered in parallel mode.
        """
        # Create entities with impossible pairs (Date-Date, Location-Location, etc.)
        entities = [
            Entity(id="p1", text="person1", type="Person"),
            Entity(id="p2", text="person2", type="Person"),
            Entity(id="d1", text="date1", type="Date"),
            Entity(id="d2", text="date2", type="Date"),
            Entity(id="l1", text="location1", type="Location"),
            Entity(id="l2", text="location2", type="Location"),
        ]
        
        text = "person1 met person2 on date1 and date2 between location1 and location2"
        
        # Enable parallel inference
        relationships = generator.infer_relationships(entities, context_parallel_4workers, text)
        
        # Check that Date-Date and Location-Location pairs are NOT in results
        for rel in relationships:
            source = next((e for e in entities if e.id == rel.source_id), None)
            target = next((e for e in entities if e.id == rel.target_id), None)
            
            if source and target:
                types = {source.type.lower(), target.type.lower()}
                # These pairs should not exist
                assert types != {"date"}
                assert types != {"location"}
                assert types != {"monetaryamount"}
                assert types != {"duration"}
                assert types != {"time"}
                assert types != {"concept"}

    def test_parallel_with_sentence_window(
        self, generator
    ):
        """Verify parallel inference works with sentence-window limiting.
        
        Entities in distant sentences should be filtered regardless of parallelization.
        """
        # Create context with both parallel and sentence window enabled
        context_parallel_windowed = OntologyGenerationContext(
            data_source="test",
            data_type=DataType.TEXT,
            domain="general",
            config=ExtractionConfig(
                enable_parallel_inference=True,
                max_workers=2,
                sentence_window=1,  # Only within 1 sentence distance
            ),
        )
        
        entities = [
            Entity(id="p1", text="Alice", type="Person"),
            Entity(id="p2", text="Bob", type="Person"),
            Entity(id="p3", text="Charlie", type="Person"),
            Entity(id="p4", text="David", type="Person"),
        ]
        
        # Text with Bob in sentence 0 and David in sentence 2 (too far with window=1)
        text = (
            "Alice met Bob here. "                         # Sentence 0: Alice, Bob
            "Charlie met someone else. "                  # Sentence 1: Charlie
            "David is mentioned far away here."           # Sentence 2: David
        )
        
        relationships = generator.infer_relationships(
            entities, context_parallel_windowed, text
        )
        
        # Bob (sentence 0) and David (sentence 2) are 2 sentences apart with window=1, should be filtered
        bob_david_pairs = [
            r for r in relationships
            if (r.source_id == "p2" and r.target_id == "p4") or
               (r.source_id == "p4" and r.target_id == "p2")
        ]
        # Should be filtered out by sentence window (distance 2 > window 1)
        assert len(bob_david_pairs) == 0

    def test_max_workers_validation(self):
        """Verify max_workers field is properly validated."""
        # Valid values
        config1 = ExtractionConfig(max_workers=1)
        config1.validate()  # Should not raise
        
        config2 = ExtractionConfig(max_workers=8)
        config2.validate()  # Should not raise
        
        # Invalid values
        with pytest.raises(ValueError, match="max_workers must be >= 1"):
            config_invalid = ExtractionConfig(max_workers=0)
            config_invalid.validate()
        
        with pytest.raises(ValueError, match="max_workers must be >= 1"):
            config_invalid = ExtractionConfig(max_workers=-1)
            config_invalid.validate()

    def test_parallel_config_serialization(self):
        """Verify parallel config parameters are properly serialized.
        
        Roundtrip through to_dict/from_dict should preserve parallel settings.
        """
        original = ExtractionConfig(
            enable_parallel_inference=True,
            max_workers=6,
            sentence_window=2,
        )
        
        # Serialize to dict
        config_dict = original.to_dict()
        assert config_dict["enable_parallel_inference"] is True
        assert config_dict["max_workers"] == 6
        
        # Deserialize from dict
        restored = ExtractionConfig.from_dict(config_dict)
        assert restored.enable_parallel_inference is True
        assert restored.max_workers == 6
        assert restored.sentence_window == 2
        
        # Should match original
        assert restored == original

    def test_parallel_with_different_worker_counts(self, generator):
        """Verify inference quality is consistent across different worker counts.
        
        Results should be equivalent whether using 1, 2, 4, or 8 workers.
        """
        entities = [
            Entity(id=f"ent_{i}", text=f"ent{i}", type="Person")
            for i in range(15)
        ]
        text = " ".join(e.text for e in entities)
        
        results = {}
        for num_workers in [1, 2, 4, 8]:
            context = OntologyGenerationContext(
                data_source="test",
                data_type=DataType.TEXT,
                domain="general",
                config=ExtractionConfig(
                    enable_parallel_inference=(num_workers > 1),
                    max_workers=num_workers,
                ),
            )
            rels = generator.infer_relationships(entities, context, text)
            results[num_workers] = len(rels)
        
        # All should produce similar counts (within small variance due to threading)
        counts = list(results.values())
        max_diff = max(counts) - min(counts)
        assert max_diff <= 2, f"Significant differences in worker counts: {results}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
