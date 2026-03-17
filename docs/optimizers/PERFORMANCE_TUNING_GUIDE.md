# GraphRAG Performance Tuning Guide

This guide provides practical recommendations for optimizing the performance of the GraphRAG ontology extraction pipeline, based on comprehensive profiling of real-world workloads.

## Table of Contents

1. [Performance Overview](#performance-overview)
2. [Profiling Results](#profiling-results)
3. [Optimization Strategies](#optimization-strategies)
4. [Configuration Tuning](#configuration-tuning)
5. [Scaling Guidelines](#scaling-guidelines)
6. [Best Practices](#best-practices)

## Performance Overview

### Current Performance Characteristics

Based on profiling with real-world legal documents:

| Input Size | Execution Time | Throughput | Entities/sec |
|------------|---------------|------------|--------------|
| 1K tokens | ~20 ms | ~50,000 t/s | ~200 e/s |
| 5K tokens | ~80 ms | ~62,500 t/s | ~350 e/s |
| 10K tokens | ~165 ms | ~61,600 t/s | ~400 e/s |
| 20K tokens | ~660 ms (est.) | ~30,000 t/s (est.) | ~300 e/s (est.) |

### Time Complexity

The OntologyGenerator pipeline exhibits **O(n^1.5) to O(n^2)** scaling behavior:

- **Entity extraction**: ~O(n) - scales linearly with document size
- **Regex operations**: ~O(n*m) - scales with document size × pattern count
- **Relationship inference**: ~O(e^2) - scales quadratically with entity count
- **Overall**: Sub-linear due to filtering and early termination

**Implication**: A 2x increase in document size results in approximately 4x increase in processing time.

## Profiling Results

### Key Bottlenecks (10K Token Document)

From comprehensive profiling ([PROFILING_BATCH_262_ANALYSIS.md](../docs/PROFILING_BATCH_262_ANALYSIS.md)):

| Component | Time | % Total | Function Calls | Notes |
|-----------|------|---------|----------------|-------|
| `_promote_person_entities()` | 115 ms | 70% | 122 regex searches | **Primary bottleneck** |
| `re.Pattern.search()` | 89 ms | 54% | 492 searches | Regex matching overhead |
| Regex compilation | 26 ms | 16% | 499 compilations | **Pattern recompilation** |
| `infer_relationships()` | 15 ms | 9% | 1 call | Efficient filtering |
| `_extract_entities_from_patterns()` | 11 ms | 7% | 1 call | Very efficient |

### Function Call Distribution

- **List operations**: 26,413 appends (20.4% of calls)
- **Type checking**: 16,277 isinstance() (12.6% of calls)
- **Regex internals**: 13,841 parser operations (10.7% of calls)
- **String operations**: 10,057 find/lower/strip (7.8% of calls)

**Key Finding**: 70% of execution time is spent in `_promote_person_entities()` performing 122 separate regex searches to identify person entities.

### Consistency Scoring Scalability (Batch 270)

`OntologyCritic._evaluate_consistency()` delegates to
`ontology_critic_consistency.evaluate_consistency()`. For large hierarchy
chains, recursive DFS can hit Python recursion limits and fail.

Applied optimization:
- Replaced recursive cycle detection with iterative Kahn topological-sort cycle detection.
- Removed duplicate cycle-detection pass in `evaluate_consistency()`.
- Kept LRU caching over normalized hierarchy edge tuples.

Impact:
- Eliminates recursion-depth failures on deep ontologies (2,500+ entities).
- Reduces repeated work in cycle checks.

Validation:
- `test_batch_270_consistency_cycle_scaling.py` verifies deep acyclic and cyclic
  chains score correctly without recursion errors.
- Existing profiling script/tests in `tests/performance/profile_batch_269_consistency_cycles.py`
  and `test_batch_269_consistency_profiling.py` remain green.

## Optimization Strategies

### 1. Pre-compile Regex Patterns (Est. 15-20% speedup)

**Problem**: 499 regex pattern compilations per document (~26 ms overhead)

**Solution**: Pre-compile all patterns at module level

**Before**:
```python
# Pattern compiled every time
for text in texts:
    if re.search(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', text):
        # ... extract entity
```

**After**:
```python
# Pre-compiled at module level
PERSON_NAME_PATTERN = re.compile(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b')

for text in texts:
    if PERSON_NAME_PATTERN.search(text):
        # ... extract entity
```

**Implementation**:
```python
# In ontology_generator.py (module level)
_PRECOMPILED_PATTERNS = {
    'person_name': re.compile(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b'),
    'organization': re.compile(r'\b[A-Z][a-zA-Z\.\s&]+(?:Corp|Inc|LLC|Ltd)\b'),
    'date': re.compile(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b'),
    'money': re.compile(r'\$[\d,]+(?:\.\d{2})?'),
    # ... add all domain-specific patterns
}
```

**Expected Gain**: 26 ms savings → **15-20% improvement**

### 2. Batch Person Entity Patterns (Est. 50-60% speedup)

**Problem**: `_promote_person_entities()` performs 122 separate regex searches (115 ms)

**Solution**: Combine patterns into single regex with alternation

**Before**:
```python
def _promote_person_entities(self, entities, text):
    for entity in entities:
        if re.search(pattern1, entity.text):
            entity.type = 'PERSON'
        elif re.search(pattern2, entity.text):
            entity.type = 'PERSON'
        # ... 120 more patterns
```

**After**:
```python
# Single combined pattern with all alternatives
PERSON_INDICATORS = re.compile(
    r'(?:Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.'
    r'|\b(?:he|she|him|her|his|hers)\b'
    r'|\b(?:employee|manager|director|CEO|CFO)\b'
    r'|\b[A-Z][a-z]+ [A-Z][a-z]+\b'  # Name pattern
    # ... all other person indicators
    r')',
    re.IGNORECASE
)

def _promote_person_entities(self, entities, text):
    # Single-pass matching
    for entity in entities:
        if PERSON_INDICATORS.search(entity.text):
            entity.type = 'PERSON'
```

**Expected Gain**: 80-100 ms savings → **50-60% improvement**

### 3. Cache Regex Results (Est. 5-10% speedup)

**Problem**: Same patterns applied to repeated text fragments

**Solution**: LRU cache for pattern matching results

```python
from functools import lru_cache

@lru_cache(maxsize=1024)
def _match_pattern_cached(pattern_name: str, text: str) -> bool:
    """Cache regex match results for common text fragments."""
    pattern = _PRECOMPILED_PATTERNS[pattern_name]
    return pattern.search(text) is not None
```

**Expected Gain**: 10-15 ms savings → **5-10% improvement**

### 4. Spatial Indexing for Relationship Inference (Future-proofing)

**Problem**: O(n²) scaling for relationship inference - currently 66 entities → 4,356 potential pairs

**Current Performance**: 0.015s for 66 entities (acceptable)
**Projected at 1,000 entities**: 1,000,000 pairs → ~227 seconds (unacceptable)

**Solution**: Implement spatial indexing to reduce pair candidates

```python
def _infer_relationships_spatial(self, entities: List[Entity], text: str) -> List[Relationship]:
    """Use spatial proximity to filter relationship candidates."""
    
    # Build spatial index (entity position in text)
    entity_positions = {
        e.id: e.source_span[0] if e.source_span else 0
        for e in entities
    }
    
    relationships = []
    PROXIMITY_WINDOW = 500  # characters
    
    for e1 in entities:
        # Only consider entities within proximity window
        e1_pos = entity_positions[e1.id]
        candidates = [
            e2 for e2 in entities
            if e2.id != e1.id and
            abs(entity_positions[e2.id] - e1_pos) < PROXIMITY_WINDOW
        ]
        
        for e2 in candidates:
            # Infer relationship only for nearby entities
            rel = self._infer_single_relationship(e1, e2, text)
            if rel:
                relationships.append(rel)
    
    return relationships
```

**Expected Gain**: Prevents future bottleneck at 1,000+ entities

### Combined Optimization Impact

Applying optimizations 1-3 together:

| Optimization | Individual Gain | Cumulative Time |
|-------------|-----------------|-----------------|
| Baseline | - | 165 ms |
| Pre-compile patterns | 15-20% | ~140 ms |
| Batch person patterns | 50-60% | ~60 ms |
| Cache regex results | 5-10% | ~54 ms |
| **Total** | **~70-80%** | **~50-60 ms** |

**Result**: 10K token document processing improves from **165 ms to ~50-60 ms** (2.7-3.3x speedup)

## Configuration Tuning

### ExtractionConfig Parameters

```python
from ipfs_datasets_py.optimizers.graphrag import ExtractionConfig

# Performance-optimized configuration
config = ExtractionConfig(
    confidence_threshold=0.6,        # Higher threshold = fewer entities = faster
    max_entities=100,                 # Limit total entities
    max_relationships=200,            # Limit total relationships
    window_size=512,                  # Smaller windows = less backtracking
    enable_caching=True,              # Enable result caching
    batch_size=32,                    # Batch size for parallel processing
    llm_fallback_threshold=0.2,      # Higher threshold = less LLM usage
    use_ipfs_accelerate=False,       # Disable for local-only optimization
)
```

### Parameter Impact Analysis

| Parameter | Low Value | High Value | Performance Impact |
|-----------|-----------|------------|-------------------|
| `confidence_threshold` | 0.3 | 0.8 | Higher = faster (filters more) |
| `max_entities` | 50 | 500 | Lower = faster (fewer pairs) |
| `max_relationships` | 100 | 1000 | Lower = faster (less inference) |
| `window_size` | 256 | 2048 | <600ms Smaller = faster (less context) |
| `llm_fallback_threshold` | 0.1 | 0.5 | Higher = faster (less LLM) |

### Domain-Specific Tuning

**Legal Documents**:
```python
config = ExtractionConfig(
    domain="legal",
    confidence_threshold=0.7,    # Legal entities are well-defined
    max_entities=150,            # Legal docs have many entities
    window_size=1024,            # Legal clauses are long
)
```

**Medical Records**:
```python
config = ExtractionConfig(
    domain="medical",
    confidence_threshold=0.8,    # Medical terms are precise
    max_entities=80,             # Focused entity set
    window_size=512,             # Medical notes are concise
)
```

**Business Documents**:
```python
config = ExtractionConfig(
    domain="business",
    confidence_threshold=0.6,    # Business terms vary widely
    max_entities=120,
    window_size=768,
)
```

## Scaling Guidelines

### Document Size Recommendations

| Document Size | Processing Time | Strategy |
|---------------|----------------|----------|
| < 5K tokens | < 100 ms | Direct processing |
| 5K - 20K tokens | 100-700 ms | Use confidence thresholds |
| 20K - 50K tokens | 700 ms - 4s | Chunk + merge strategy |
| > 50K tokens | > 4s | Parallel chunking required |

### Chunking Strategy for Large Documents

```python
def process_large_document(text: str, context: OntologyGenerationContext) -> Dict:
    """Process documents > 20K tokens using chunking."""
    
    CHUNK_SIZE = 10000  # tokens
    OVERLAP = 1000      # tokens for context continuity
    
    generator = OntologyGenerator()
    chunks = _chunk_text(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
    
    all_entities = []
    all_relationships = []
    
    for chunk in chunks:
        result = generator.generate_ontology(chunk, context)
        all_entities.extend(result['entities'])
        all_relationships.extend(result['relationships'])
    
    # Deduplicate entities across chunks
    deduplicated = _deduplicate_entities(all_entities)
    
    return {
        'entities': deduplicated,
        'relationships': _merge_relationships(all_relationships, deduplicated),
        'metadata': {'chunks_processed': len(chunks)}
    }
```

### Parallel Processing

For batch document processing:

```python
from concurrent.futures import ProcessPoolExecutor

def process_document_batch(documents: List[str], context: OntologyGenerationContext):
    """Process multiple documents in parallel."""
    
    generator = OntologyGenerator()
    
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(generator.generate_ontology, doc, context)
            for doc in documents
        ]
        
        results = [f.result() for f in futures]
    
    return results
```

### Memory Management

For very large documents (>100K tokens):

```python
config = ExtractionConfig(
    max_entities=100,           # Hard limit to prevent memory explosion
    max_relationships=150,      # Limit relationship storage
    enable_streaming=True,      # Stream entities instead of buffering
    checkpoint_interval=5000,   # Checkpoint every 5K tokens
)
```

## Best Practices

### 1. Choose the Right Extraction Strategy

```python
# RULE_BASED: Fast, deterministic (recommended for production)
context = Ontology GenerationContext(
    extraction_strategy=ExtractionStrategy.RULE_BASED,
    # ... other params
)

# LLM_FALLBACK: Hybrid approach (balance of speed and accuracy)
context = OntologyGenerationContext(
    extraction_strategy=ExtractionStrategy.LLM_FALLBACK,
    llm_fallback_threshold=0.3,  # Use LLM when confidence < 0.3
)

# PURE_LLM: Highest accuracy, slowest (research/high-value docs)
context = OntologyGenerationContext(
    extraction_strategy=ExtractionStrategy.PURE_LLM,
    # 10-30 seconds for 10K tokens
)
```

### 2. Profile Your Workload

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Your extraction code here
ontology = generator.generate_ontology(text, context)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 hotspots
```

### 3. Monitor Performance Metrics

```python
import time

start = time.perf_counter()
ontology = generator.generate_ontology(text, context)
elapsed = time.perf_counter() - start

token_count = len(text.split())
throughput = token_count / elapsed

print(f"Throughput: {throughput:.0f} tokens/sec")
print(f"Entities/sec: {len(ontology['entities']) / elapsed:.1f}")
print(f"Time per entity: {elapsed / len(ontology['entities']):.4f}s")

# Alert if performance degrades
if throughput < 30000:  # Below acceptable threshold
    logger.warning(f"Low throughput: {throughput:.0f} t/s")
```

### 4. Micro-benchmark Smoke Test

Use the lightweight smoke benchmark to track regressions or verify improvements
after refactors. It prints a small timing table you can paste below.

```bash
python -m ipfs_datasets_py.optimizers.tests.performance.perf_ontology_generate_smoke
```

**Before/After Timing Table (update after changes)**

| Run | Mean (ms) | P95 (ms) | Min (ms) | Max (ms) | Notes |
| --- | --- | --- | --- | --- | --- |
| Baseline | TBD | TBD | TBD | TBD | Record before optimization |
| After | TBD | TBD | TBD | TBD | Record after optimization |

**Regex Hot Paths Table (update after regex/entity optimizations)**

Run:
```bash
python -m ipfs_datasets_py.optimizers.tests.performance.perf_ontology_regex_hotpaths
```

| Segment | Mean (ms) | P95 (ms) | Notes |
| --- | --- | --- | --- |
| Pattern build | TBD | TBD | Rule pattern construction |
| Pattern extract | TBD | TBD | Regex finditer extraction |
| Person promotion | TBD | TBD | `_promote_person_entities` |

### 5. Use Caching Effectively

```python
# Enable caching for repeated documents
generator = OntologyGenerator(use_caching=True)

# Cache is automatically updated by domain and datasource
for doc in similar_documents:
    # Subsequent calls benefit from cached patterns
    ontology = generator.generate_ontology(doc, context)
```

### 6. Batch Processing for Multiple Documents

```python
# Process efficiently
results = generator.generate_ontology_batch(
    documents=documents,
    context=context,
    parallel=True,
    max_workers=4,
)
```

### 7. Tune for Your Hardware

**CPU-Bound (2-4 cores)**:
- Use RULE_BASED strategy
- confidence_threshold >= 0.7
- max_entities <= 100

**CPU-Rich (8+ cores)**:
- Enable parallel batch processing
- Use HYBRID or LLM_FALLBACK
- Process multiple documents simultaneously

**Memory-Constrained (<8GB)**:
- max_entities = 50
- max_relationships = 100
- Use chunking for documents >10K tokens

**GPU-Enabled**:
- Use PURE_LLM strategy with GPU-accelerated LLM
- Batch size = 16-32 for optimal GPU utilization

## Troubleshooting Performance Issues

### Issue: Slow Processing (< 10,000 tokens/sec)

**Diagnosis**:
```python
# Add timing instrumentation
import time

class TimedGenerator(OntologyGenerator):
    def generate_ontology(self, text, context):
        timings = {}
        
        start = time.perf_counter()
        entities = self.extract_entities(text, context)
        timings['extraction'] = time.perf_counter() - start
        
        start = time.perf_counter()
        relationships = self.infer_relationships(entities, text)
        timings['inference'] = time.perf_counter() - start
        
        print(f"Timings: {timings}")
        return super().generate_ontology(text, context)
```

**Solutions**:
1. Check if regex patterns are being recompiled (see Optimization #1)
2. Verify LLM fallback isn't triggering excessively
3. Review `max_entities` and `confidence_threshold` settings

### Issue: Memory Usage Too High

**Diagnosis**:
```python
import tracemalloc

tracemalloc.start()

ontology = generator.generate_ontology(text, context)

current, peak = tracemalloc.get_traced_memory()
print(f"Current: {current / 1024 / 1024:.1f} MB")
print(f"Peak: {peak / 1024 / 1024:.1f} MB")

tracemalloc.stop()
```

**Solutions**:
1. Reduce `max_entities` and `max_relationships`
2. Enable streaming mode for large documents
3. Use chunking strategy (see Scaling Guidelines)

### Issue: Inconsistent Performance

**Possible Causes**:
- Garbage collection pauses
- Cache misses
- Pattern recompilation

**Solution**:
```python
import gc

# Disable GC during critical sections
gc.disable()
try:
    ontology = generator.generate_ontology(text, context)
finally:
    gc.enable()
```

## Performance Regression Testing

```python
# Add to your test suite
def test_performance_regression():
    """Ensure performance doesn't regress below baselines."""
    
    generator = OntologyGenerator()
    context = OntologyGenerationContext(
        data_source="performance_test",
        data_type=DataType.TEXT,
        domain="legal",
        extraction_strategy=ExtractionStrategy.RULE_BASED,
    )
    
    # Generate 10K token document
    text = "Sample text... " * 2500  # ~10K tokens
    
    start = time.perf_counter()
    ontology = generator.generate_ontology(text, context)
    elapsed = time.perf_counter() - start
    
    token_count = len(text.split())
    throughput = token_count / elapsed
    
    # Assert performance thresholds
    assert throughput > 50000, f"Throughput {throughput:.0f} t/s below threshold 50,000 t/s"
    assert elapsed < 0.25, f"Execution time {elapsed:.3f}s exceeds 250ms threshold"
    assert len(ontology['entities']) > 20, "Too few entities extracted"
```

## References

- **[PROFILING_BATCH_262_ANALYSIS.md](../docs/PROFILING_BATCH_262_ANALYSIS.md)** - Detailed profiling analysis
- **[CONFIGURATION_REFERENCE.md](../docs/CONFIGURATION_REFERENCE.md)** - Complete configuration guide
- **[GRAPHRAG_QUICK_START.md](../docs/optimizers/GRAPHRAG_QUICK_START.md)** - Quick start guide
- **[README.md](README.md)** - Main optimizers documentation

## Version History

- **v1.0** (2026-02-23): Initial performance tuning guide based on Batch 262 profiling results
