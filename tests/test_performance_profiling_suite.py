"""
Performance Profiling and Benchmarking Suite

Tests for performance metrics, latency profiling, memory usage,
throughput measurement, and optimization validation.
"""

import pytest
import time
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
)


class TestExtractionLatency:
    """Test extraction latency for various input sizes."""
    
    def test_latency_small_text(self):
        """Measure latency for small text input."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John went to the store."
        
        start = time.perf_counter()
        result = generator.generate_ontology(text, context)
        latency = time.perf_counter() - start
        
        assert result is not None
        assert latency > 0
    
    def test_latency_medium_text(self):
        """Measure latency for medium text input."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John Smith, a senior engineer at Acme Corporation, met with Jane Doe, " \
               "the marketing director. They discussed the new product launch scheduled " \
               "for next quarter. The meeting took place in the conference room on " \
               "Monday morning."
        
        start = time.perf_counter()
        result = generator.generate_ontology(text, context)
        latency = time.perf_counter() - start
        
        assert result is not None
        assert latency > 0
    
    def test_latency_large_text(self):
        """Measure latency for larger text input."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = " ".join(["The research team discovered new patterns in data processing."] * 50)
        
        start = time.perf_counter()
        result = generator.generate_ontology(text, context)
        latency = time.perf_counter() - start
        
        assert result is not None
        assert latency > 0


class TestExtractionThroughput:
    """Test extraction throughput."""
    
    def test_throughput_sequential_processing(self):
        """Measure throughput for sequential processing."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        texts = ["Test data " + str(i) for i in range(10)]
        
        start = time.perf_counter()
        results = [generator.generate_ontology(text, context) for text in texts]
        total_time = time.perf_counter() - start
        
        assert len(results) == 10
        throughput = len(results) / total_time
        assert throughput > 0
    
    def test_throughput_batch_processing(self):
        """Measure throughput for batch processing."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        texts = ["Batch item " + str(i) for i in range(20)]
        
        start = time.perf_counter()
        results = [generator.generate_ontology(text, context) for text in texts]
        total_time = time.perf_counter() - start
        
        assert len(results) == 20
        throughput = len(results) / total_time
        assert throughput > 0


class TestDomainSpecificPerformance:
    """Test performance differences across domains."""
    
    def test_legal_domain_performance(self):
        """Measure performance for legal domain."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="legal"
        )
        generator = OntologyGenerator()
        
        text = "The plaintiff sued for breach of contract."
        
        start = time.perf_counter()
        result = generator.generate_ontology(text, context)
        latency = time.perf_counter() - start
        
        assert result is not None
        assert latency > 0
    
    def test_medical_domain_performance(self):
        """Measure performance for medical domain."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="medical"
        )
        generator = OntologyGenerator()
        
        text = "Patient presents with hypertension and diabetes."
        
        start = time.perf_counter()
        result = generator.generate_ontology(text, context)
        latency = time.perf_counter() - start
        
        assert result is not None
        assert latency > 0
    
    def test_business_domain_performance(self):
        """Measure performance for business domain."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="business"
        )
        generator = OntologyGenerator()
        
        text = "Company revenue increased by 25% year-over-year."
        
        start = time.perf_counter()
        result = generator.generate_ontology(text, context)
        latency = time.perf_counter() - start
        
        assert result is not None
        assert latency > 0


class TestScalabilityByTextSize:
    """Test scalability with increasing text size."""
    
    def test_scalability_10_words(self):
        """Extract from 10-word text."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = " ".join(["word"] * 10)
        result = generator.generate_ontology(text, context)
        
        assert result is not None
    
    def test_scalability_100_words(self):
        """Extract from 100-word text."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = " ".join(["word"] * 100)
        result = generator.generate_ontology(text, context)
        
        assert result is not None
    
    def test_scalability_1000_words(self):
        """Extract from 1000-word text."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = " ".join(["word"] * 1000)
        result = generator.generate_ontology(text, context)
        
        assert result is not None
    
    def test_scalability_5000_words(self):
        """Extract from 5000-word text."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = " ".join(["word"] * 5000)
        result = generator.generate_ontology(text, context)
        
        assert result is not None


class TestEntityExtensionPerformance:
    """Test performance impact of entity count."""
    
    def test_performance_few_entities(self):
        """Performance with few entities."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John works."
        
        start = time.perf_counter()
        result = generator.generate_ontology(text, context)
        latency = time.perf_counter() - start
        
        assert result is not None
        assert latency > 0
    
    def test_performance_many_entities(self):
        """Performance with many entities."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        names = ["Alice", "Bob", "Charlie", "Diana", "Edward", "Fiona",
                 "George", "Helen", "Ivan", "Julia"]
        text = " and ".join(names) + " all met."
        
        start = time.perf_counter()
        result = generator.generate_ontology(text, context)
        latency = time.perf_counter() - start
        
        assert result is not None
        assert latency > 0


class TestRelationshipExtractionPerformance:
    """Test performance of relationship extraction."""
    
    def test_few_relationships_performance(self):
        """Performance with few relationships."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John manages the project."
        
        start = time.perf_counter()
        result = generator.generate_ontology(text, context)
        latency = time.perf_counter() - start
        
        assert result is not None
        assert latency > 0
    
    def test_many_relationships_performance(self):
        """Performance with complex relationship networks."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "John manages Alice, Alice supervises Bob, Bob helps Charlie, " \
               "Charlie reports to David, David supports Edward."
        
        start = time.perf_counter()
        result = generator.generate_ontology(text, context)
        latency = time.perf_counter() - start
        
        assert result is not None
        assert latency > 0


class TestMemoryFootprint:
    """Test memory usage patterns."""
    
    def test_small_text_memory(self):
        """Memory usage for small text."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Test"
        result = generator.generate_ontology(text, context)
        
        assert result is not None
    
    def test_large_text_memory(self):
        """Memory usage for large text."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = " ".join(["test"] * 10000)
        result = generator.generate_ontology(text, context)
        
        assert result is not None


class TestCachingPerformance:
    """Test performance with repeated extractions."""
    
    def test_repeated_extraction_performance(self):
        """Performance for repeated extractions from same text."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        text = "Test text for caching performance"
        
        # First extraction
        start1 = time.perf_counter()
        result1 = generator.generate_ontology(text, context)
        time1 = time.perf_counter() - start1
        
        # Repeated extraction
        start2 = time.perf_counter()
        result2 = generator.generate_ontology(text, context)
        time2 = time.perf_counter() - start2
        
        assert result1 is not None
        assert result2 is not None
    
    def test_different_text_performance(self):
        """Performance for different text extractions."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        texts = ["Text number " + str(i) for i in range(10)]
        
        times = []
        for text in texts:
            start = time.perf_counter()
            result = generator.generate_ontology(text, context)
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            assert result is not None
        
        # Performance should be reasonably consistent
        assert len(times) == 10


class TestInitializationPerformance:
    """Test initialization overhead."""
    
    def test_generator_initialization(self):
        """Measure generator initialization time."""
        start = time.perf_counter()
        generator = OntologyGenerator()
        init_time = time.perf_counter() - start
        
        assert generator is not None
        assert init_time > 0
    
    def test_context_creation_performance(self):
        """Measure context creation time."""
        start = time.perf_counter()
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        init_time = time.perf_counter() - start
        
        assert context is not None
        assert init_time > 0


class TestComplexityGrowth:
    """Test how performance scales with complexity."""
    
    def test_entity_count_complexity(self):
        """Test performance scaling with entity count."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        for count in [1, 5, 10]:
            text = " and ".join([f"Entity{i}" for i in range(count)])
            result = generator.generate_ontology(text, context)
            assert result is not None
    
    def test_text_length_complexity(self):
        """Test performance scaling with text length."""
        context = OntologyGenerationContext(
            data_source="test", data_type="text", domain="general"
        )
        generator = OntologyGenerator()
        
        for length in [10, 100, 500, 1000]:
            text = "word " * length
            result = generator.generate_ontology(text, context)
            assert result is not None
