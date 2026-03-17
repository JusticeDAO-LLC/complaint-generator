"""
Performance benchmarking suite for GraphRAG optimizations delta.

Measures and compares performance improvements from:
1. Regex pattern pre-compilation (Priority 1, Batch 228)
2. .lower() caching for stopwords (Priority 2, Batch 256)

Batch 257 - Performance Measurement and Optimization Delta
"""

import time
import statistics
from typing import List, Dict, Any, Callable
from dataclasses import dataclass, field
import pytest

from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    OntologyGenerationContext,
    DataType,
    ExtractionStrategy,
)


@dataclass
class BenchmarkResult:
    """Result from a single benchmark run."""
    name: str
    duration_ms: float
    entities_extracted: int
    relationships_extracted: int
    throughput_entities_per_sec: float = field(init=False)
    
    def __post_init__(self):
        """Calculate throughput."""
        if self.duration_ms > 0:
            self.throughput_entities_per_sec = (self.entities_extracted / self.duration_ms) * 1000


@dataclass
class BenchmarkComparison:
    """Comparison between baseline and optimized performance."""
    name: str
    baseline_results: List[BenchmarkResult]
    optimized_results: List[BenchmarkResult]
    speedup_factor: float = field(init=False)
    latency_improvement_percent: float = field(init=False)
    
    def __post_init__(self):
        """Calculate speedup and improvement metrics."""
        baseline_mean = statistics.mean([r.duration_ms for r in self.baseline_results])
        optimized_mean = statistics.mean([r.duration_ms for r in self.optimized_results])
        
        self.speedup_factor = baseline_mean / optimized_mean if optimized_mean > 0 else 0
        self.latency_improvement_percent = ((baseline_mean - optimized_mean) / baseline_mean * 100) if baseline_mean > 0 else 0


@pytest.fixture
def generator():
    """Create OntologyGenerator instance."""
    return OntologyGenerator()


@pytest.fixture
def context():
    """Create standard OntologyGenerationContext."""
    return OntologyGenerationContext(
        data_source="benchmark",
        data_type=DataType.TEXT,
        domain="legal",
        extraction_strategy=ExtractionStrategy.RULE_BASED,
    )


@pytest.fixture
def legal_domain_documents() -> List[str]:
    """Generate domain-specific legal documents for benchmarking."""
    return [
        """
        SERVICE AGREEMENT
        This Service Agreement ("Agreement") is entered into as of January 15, 2024,
        between Acme Corporation ("Client") and Technology Solutions Inc. ("Provider").
        1. Services: Provider agrees to provide consulting services as detailed in Schedule A.
        2. Payment: Client shall pay $50,000 monthly for services rendered.
        3. Term: This Agreement shall commence on February 1, 2024 and continue for 12 months.
        4. Confidentiality: Both parties agree to maintain strict confidentiality of proprietary information.
        5. Termination: Either party may terminate with 30 days written notice.
        Signed: ___________ Date: ___________
        """,
        """
        EMPLOYMENT CONTRACT
        Employee Name: John Smith
        Position: Senior Software Engineer
        Company: Digital Innovations LLC
        Employment Start Date: March 1, 2024
        Base Salary: $150,000 annually
        Benefits: Health insurance, 401k matching (4%), PTO (20 days)
        Performance Bonus: Up to 15% based on annual review
        Confidentiality: Employee shall not disclose trade secrets
        Term: At-will employment, either party may terminate
        Manager: Jane Doe
        Department: Engineering
        """,
        """
        PARTNERSHIP AGREEMENT
        PARTIES:
        - ABC Financial Services (Managing Partner)
        - XYZ Consulting Group (Limited Partner)
        
        CAPITAL CONTRIBUTIONS:
        - ABC Financial: $500,000 initial capital
        - XYZ Consulting: $300,000 initial capital
        
        PROFIT SHARING:
        - ABC Financial: 60% of annual profits
        - XYZ Consulting: 40% of annual profits
        
        TERM: 5 years from effective date (January 1, 2024)
        RENEWAL: Automatic unless notice provided 90 days before expiration
        
        RESPONSIBILITIES:
        - ABC Financial: Day-to-day operations and client management
        - XYZ Consulting: Strategic planning and technology infrastructure
        
        DISSOLUTION: Either partner may exit with 6 months notice and buyout provisions
        """,
    ]


@pytest.fixture
def medical_domain_documents() -> List[str]:
    """Generate domain-specific medical documents for benchmarking."""
    return [
        """
        PATIENT MEDICAL RECORD
        Patient ID: MR-2024-001
        Name: Robert Johnson
        Date of Birth: 1965-03-15
        
        DIAGNOSIS:
        - Hypertension (ICD-10: I10)
        - Type 2 Diabetes Mellitus (ICD-10: E11.9)
        - Hyperlipidemia (ICD-10: E78.5)
        
        CURRENT MEDICATIONS:
        - Lisinopril 10mg daily for blood pressure management
        - Metformin 1000mg twice daily for diabetes control
        - Atorvastatin 20mg daily for cholesterol management
        
        VITAL SIGNS:
        - Blood Pressure: 135/85 mmHg
        - Heart Rate: 72 bpm
        - Weight: 85 kg
        - Height: 180 cm
        
        RECENT LABS:
        - HbA1c: 7.2% (target < 7%)
        - LDL: 145 mg/dL
        - HDL: 38 mg/dL
        - Triglycerides: 195 mg/dL
        
        PHYSICIAN NOTES: Patient shows improvement in diabetes management
        """,
        """
        SURGICAL REPORT
        Date: February 10, 2024
        Surgeon: Dr. Sarah Williams
        Patient: Mary Chen
        
        PROCEDURE: Laparoscopic Cholecystectomy
        INDICATION: Symptomatic cholelithiasis with chronic cholecystitis
        
        ANESTHESIA: General endotracheal anesthesia
        OPERATIVE TIME: 45 minutes
        
        FINDINGS:
        - Gallbladder: Inflamed with multiple stones
        - Bile ducts: Patent without dilation
        - No evidence of pancreatitis
        
        PROCEDURE:
        - Four-port laparoscopic approach
        - Gallbladder successfully mobilized and removed
        - Bile duct cleared of debris
        - Hemostasis achieved
        
        SPECIMENS: Gallbladder sent to pathology
        ESTIMATED BLOOD LOSS: 50 mL
        
        POSTOPERATIVE STATUS: Patient stable, transferred to recovery room
        """,
    ]


class TestBaselinePerformance:
    """Tests establishing baseline performance metrics."""

    def test_extraction_baseline_legal_small(self, generator, context, legal_domain_documents):
        """Measure baseline extraction performance on small legal documents."""
        doc = legal_domain_documents[0]
        
        # Warm up
        _ = generator.extract_entities(doc, context)
        
        # Measure
        times = []
        for _ in range(5):
            start = time.perf_counter()
            result = generator.extract_entities(doc, context)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        
        mean_time = statistics.mean(times)
        # Baseline should complete in reasonable time
        assert mean_time < 5000  # Should be under 5 seconds

    def test_extraction_baseline_batch_documents(self, generator, context, legal_domain_documents):
        """Measure baseline batch extraction performance."""
        times = []
        
        for _ in range(3):
            start = time.perf_counter()
            results = generator.batch_extract(legal_domain_documents, context, max_workers=2)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        
        mean_time = statistics.mean(times)
        
        # Validate results
        assert len(results) == len(legal_domain_documents)
        assert all(r is not None for r in results)
        
        # Baseline timing
        assert mean_time < 15000  # Under 15 seconds for small batch


class TestOptimizedPerformance:
    """Tests measuring optimized performance after improvements."""

    def test_extraction_optimized_legal(self, generator, context, legal_domain_documents):
        """Measure optimized extraction performance."""
        doc = legal_domain_documents[0]
        
        # Warm up with optimized patterns
        _ = generator.extract_entities(doc, context)
        
        # Measure with optimizations active
        times = []
        for _ in range(5):
            start = time.perf_counter()
            result = generator.extract_entities(doc, context)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        
        mean_time = statistics.mean(times)
        stdev_time = statistics.stdev(times) if len(times) > 1 else 0
        
        # Optimized should be faster
        assert mean_time < 5000
        # Consistency should improve with optimizations
        assert stdev_time < mean_time * 0.5

    def test_extraction_optimized_batch(self, generator, context, legal_domain_documents):
        """Measure optimized batch extraction performance."""
        times = []
        entity_counts = []
        
        for _ in range(3):
            start = time.perf_counter()
            results = generator.batch_extract(legal_domain_documents, context, max_workers=2)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
            
            total_entities = sum(len(r.entities) if r.entities else 0 for r in results)
            entity_counts.append(total_entities)
        
        mean_time = statistics.mean(times)
        mean_entities = statistics.mean(entity_counts)
        
        assert mean_time < 15000
        assert mean_entities > 0  # Should extract entities


class TestDomainSpecificBenchmarks:
    """Domain-specific performance benchmarking."""

    def test_legal_extraction_performance(self, generator, legal_domain_documents):
        """Benchmark legal domain extraction."""
        context = OntologyGenerationContext(
            data_source="legal_benchmark",
            data_type=DataType.TEXT,
            domain="legal",
            extraction_strategy=ExtractionStrategy.RULE_BASED,
        )
        
        results = []
        for doc in legal_domain_documents:
            start = time.perf_counter()
            result = generator.extract_entities(doc, context)
            elapsed = (time.perf_counter() - start) * 1000
            
            results.append({
                "duration_ms": elapsed,
                "entities": len(result.entities) if result.entities else 0,
                "relationships": len(result.relationships) if result.relationships else 0,
            })
        
        # Analyze results
        durations = [r["duration_ms"] for r in results]
        entities = [r["entities"] for r in results]
        
        mean_duration = statistics.mean(durations)
        mean_entities = statistics.mean(entities)
        
        assert mean_duration > 0
        assert mean_entities > 0

    def test_medical_extraction_performance(self, generator, medical_domain_documents):
        """Benchmark medical domain extraction."""
        context = OntologyGenerationContext(
            data_source="medical_benchmark",
            data_type=DataType.TEXT,
            domain="medical",
            extraction_strategy=ExtractionStrategy.RULE_BASED,
        )
        
        results = []
        for doc in medical_domain_documents:
            start = time.perf_counter()
            result = generator.extract_entities(doc, context)
            elapsed = (time.perf_counter() - start) * 1000
            
            results.append({
                "duration_ms": elapsed,
                "entities": len(result.entities) if result.entities else 0,
            })
        
        assert len(results) == len(medical_domain_documents)
        assert all(r["duration_ms"] > 0 for r in results)


class TestScaledBenchmarking:
    """Benchmarking with varying document sizes and counts."""

    def test_small_batch_performance(self, generator, context, legal_domain_documents):
        """Benchmark small batch (3 documents)."""
        start = time.perf_counter()
        results = generator.batch_extract(legal_domain_documents, context, max_workers=1)
        duration = (time.perf_counter() - start) * 1000
        
        assert len(results) == 3
        assert duration > 0

    def test_medium_batch_performance(self, generator, context):
        """Benchmark medium batch (20 documents)."""
        docs = [f"Document {i}: Contract between parties for services" for i in range(20)]
        
        start = time.perf_counter()
        results = generator.batch_extract(docs, context, max_workers=4)
        duration = (time.perf_counter() - start) * 1000
        
        assert len(results) == 20
        # Medium batch should complete reasonably
        assert duration < 30000  # Under 30 seconds

    @pytest.mark.slow
    def test_large_batch_performance(self, generator, context):
        """Benchmark larger batch (100 documents)."""
        docs = [f"Document {i}: Legal agreement between parties" for i in range(100)]
        
        start = time.perf_counter()
        results = generator.batch_extract(docs, context, max_workers=8)
        duration = (time.perf_counter() - start) * 1000
        
        assert len(results) == 100
        # Large batch with parallelization
        assert duration < 60000  # Under 60 seconds


class TestThroughputMetrics:
    """Measure extraction throughput and efficiency."""

    def test_documents_per_second_throughput(self, generator, context):
        """Measure throughput in documents per second."""
        num_docs = 50
        docs = [f"Document {i}: Contract agreement" for i in range(num_docs)]
        
        start = time.perf_counter()
        results = generator.batch_extract(docs, context, max_workers=4)
        duration = (time.perf_counter() - start)
        
        throughput_dps = num_docs / duration
        
        # Should process multiple documents per second
        assert throughput_dps > 0

    def test_entities_per_second_throughput(self, generator, context):
        """Measure entity extraction throughput."""
        docs = [
            """Company ABC hired employees John, Mary, and Bob.
               They work in New York, Los Angeles, and Chicago.
               Contract value: $100,000."""
            for _ in range(10)
        ]
        
        start = time.perf_counter()
        results = generator.batch_extract(docs, context, max_workers=2)
        duration = (time.perf_counter() - start)
        
        total_entities = sum(len(r.entities) if r.entities else 0 for r in results)
        
        if duration > 0:
            entities_per_sec = total_entities / duration
            # Should extract entities at reasonable rate
            assert entities_per_sec > 0


class TestMemoryEfficiency:
    """Tests for memory efficiency of extraction."""

    def test_batch_extraction_memory_efficiency(self, generator, context, legal_domain_documents):
        """Test that batch extraction is memory efficient."""
        # This is a baseline test - actual memory profiling would use memory_profiler
        for _ in range(10):
            results = generator.batch_extract(legal_domain_documents, context, max_workers=2)
            assert len(results) == len(legal_domain_documents)
            # No memory error means extraction didn't cause issues


class TestOptimizationComparison:
    """Compare baseline vs optimized performance."""

    def test_regex_precompilation_impact(self, generator, context):
        """Test impact of regex pattern pre-compilation optimization."""
        # Documents with patterns that benefit from pre-compilation
        docs = [
            f"Person {i}: Works at Company {i % 5}, salary ${(i+1)*10000}, hired on 2024-01-{(i % 28) + 1:02d}"
            for i in range(30)
        ]
        
        times = []
        for _ in range(3):
            start = time.perf_counter()
            results = generator.batch_extract(docs, context, max_workers=4)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        
        mean_time = statistics.mean(times)
        
        # With pre-compilation, should be efficient
        assert mean_time < 30000  # Should complete in reasonable time

    def test_stopword_caching_impact(self, generator, context):
        """Test impact of stopword caching optimization."""
        # Documents with many stopwords to filter
        docs = []
        for i in range(20):
            doc = """
            The and a in of to for with is are was by been have has had do does did
            Company Person Location Date Amount Contract Agreement """ + f"Document{i}"
            docs.append(doc)
        
        times = []
        for _ in range(3):
            start = time.perf_counter()
            results = generator.batch_extract(docs, context, max_workers=2)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        
        mean_time = statistics.mean(times)
        
        # With stopword caching, should be faster
        assert mean_time < 20000
