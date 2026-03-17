# Batch 262: OntologyGenerator.generate() Performance Profile on 10k Tokens

## Overview

This report documents the performance profiling of `OntologyGenerator.generate_ontology()` on a large 10k-token legal document to identify bottlenecks and hot paths in the rule-based extraction pipeline.

**Date**: 2024  
**Batch**: 262  
**Priority**: P2 PERF  
**Status**: ✅ COMPLETE

## Test Configuration

```python
Input Size: 10,171 tokens (75.5 KB)
Domain: legal
Strategy: RULE_BASED
Data Type: TEXT
Document: Synthetic Master Services Agreement with 50+ sections
```

## Performance Metrics

### Execution Results

| Metric | Value |
|--------|-------|
| **Total Execution Time** | 164.95 ms |
| **Entities Extracted** | 66 entities |
| **Relationships Inferred** | 52 relationships |
| **Throughput (tokens)** | 61,662 tokens/sec |
| **Throughput (entities)** | 400.1 entities/sec |
| **Function Calls** | 129,393 total calls |

### Comparison with Batch 227 Baseline

Batch 227 profiled a smaller document (48.6 KB ≈ 6,600 tokens):

| Metric | Batch 227 (6.6K tokens) | Batch 262 (10.1K tokens) | Scaling |
|--------|------------------------|-------------------------|---------|
| **Execution Time** | 39 ms | 164.95 ms | **4.2x** |
| **Throughput** | ~169K tokens/sec | 61,662 tokens/sec | **0.37x** |
| **Tokens/ms** | 169 tokens/ms | 61.6 tokens/ms | **0.36x** |

**Observation**: Performance scales **sub-linearly** (not O(n)). A 1.54x increase in input size (6.6K → 10.1K tokens) resulted in a 4.2x increase in execution time. This suggests O(n²) or O(n log n) behavior likely due to relationship inference or regex pattern matching over entities.

## Bottleneck Analysis

### Top 5 Hotspots (by cumulative time)

1. **`_promote_person_entities()`** - **0.115s (70% of execution time)**
   - Calls: 1
   - Total searches: 122 regex searches
   - Average per search: 0.94 ms
   - **Issue**: Performs multiple regex searches per entity to identify person names
   - **Optimization**: Batch regex patterns, pre-compile patterns, use single-pass matching

2. **`re.Pattern.search()`** - **0.089s (54% of execution time)**
   - Calls: 492 searches
   - Average: 0.18 ms per search
   - **Issue**: High overhead from repeated regex searches
   - **Optimization**: Reduce regex operations, cache results, use compiled patterns

3. **Regex compilation (`re._compile()`)** - **0.026s (16% of execution time)**
   - Calls: 499 compilations
   - Average: 0.05 ms per compile
   - **Issue**: Patterns are being recompiled instead of reused
   - **Optimization**: Pre-compile all patterns at module level, use pattern cache

4. **`infer_relationships()`** - **0.015s (9% of execution time)**
   - Calls: 1
   - Relationships inferred: 52
   - **Performance**: Relatively efficient at 0.29 ms per relationship
   - **Observation**: Despite O(n²) potential (66 entities → 2,145 pairs), only 0.015s spent

5. **`_extract_entities_from_patterns()`** - **0.011s (7% of execution time)**
   - Calls: 1
   - Entities extracted: 66
   - **Performance**: Very efficient at 0.17 ms per entity
   - **Observation**: Core entity extraction is fast; most time spent in post-processing

### Function Call Distribution

| Category | Calls | % of Total |
|----------|-------|------------|
| **List operations** | 26,413 appends | 20.4% |
| **Type checking** | 16,277 isinstance() | 12.6% |
| **Regex internals** | 13,841 parser ops | 10.7% |
| **String operations** | 10,057 (find, lower, strip) | 7.8% |
| **Regex searches** | 492 searches | 0.4% (but 54% of time!) |

## Root Cause Analysis

### 1. Regex Pattern Recompilation (26 ms overhead)

**Problem**: 499 regex compilations suggest patterns are not being cached effectively.

**Evidence**:
```
499 calls to __init__.py:280(_compile)  - 0.026s cumulative
94 calls to _compiler.py:745(compile)   - 0.025s cumulative
```

**Solution**: Pre-compile all regex patterns at module level using `re.compile()` and store in class-level constants.

### 2. _promote_person_entities() Inefficiency (115 ms)

**Problem**: 70% of execution time spent identifying person entities through repeated regex searches.

**Evidence**:
```
1 call to ontology_generator.py:4519(_promote_person_entities) - 0.115s cumulative
122 calls to re.search() within this function
```

**Solution**:
- Batch all person-name patterns into a single compiled regex: `(pattern1|pattern2|pattern3)`
- Single-pass matching instead of 122+ separate searches
- Cache person entity determinations

### 3. Relationship Inference Scaling

**Problem**: While currently efficient (0.015s), this is likely O(n²) and will become a bottleneck at 1000+ entities.

**Current Performance**: 66 entities × 66 entities = 4,356 potential pairs, but only 52 relationships inferred suggests good filtering.

**Projection**: For 1,000 entities → 1,000,000 pairs → estimated ~227 seconds (3.8 minutes) if O(n²).

**Solution**: 
- Implement spatial indexing (entities nearby in text more likely to relate)
- Skip impossible type pairs early
- Use entity co-occurrence windows (e.g., ±50 tokens)

## Scaling Analysis

### Empirical Scaling

| Input Size | Execution Time | Tokens/sec | Scaling Factor |
|------------|---------------|------------|----------------|
| 6.6K tokens | 39 ms | 169,231 t/s | 1.0x |
| 10.1K tokens | 164.95 ms | 61,662 t/s | 4.2x time |

**Time Complexity**: Appears to be **O(n^1.5) to O(n^2)** rather than linear O(n).

**Extrapolations**:
- **20K tokens**: ~663 ms (projected)
- **50K tokens**: ~4.1 seconds (projected)
- **100K tokens**: ~16.5 seconds (projected)

These projections assume continued sub-linear scaling. Actual results may vary due to relationship inference becoming dominant at higher entity counts.

## Optimization Recommendations

### High Impact (should implement immediately)

1. **Pre-compile regex patterns** (estimated 26 ms savings)
   - Move all regex patterns to module-level compiled constants
   - Eliminate 499 re-compilation calls
   - **Expected gain**: 15-20% speed improvement

2. **Optimize _promote_person_entities()** (estimated 80-100 ms savings)
   - Combine 122 regex searches into single batched pattern
   - Use `re.finditer()` for single-pass matching
   - **Expected gain**: 50-60% speed improvement

3. **Cache regex results** (estimated 10-15 ms savings)
   - Add LRU cache for repeated pattern searches
   - Cache person entity determinations
   - **Expected gain**: 5-10% speed improvement

### Medium Impact (worth investigating)

4. **Relationship inference spatial indexing**
   - Current: O(n²) entity pair iteration
   - Proposed: O(n log n) with spatial indexing
   - **Expected gain**: Prevents future bottleneck at 1000+ entities

5. **Reduce string operations**
   - 2,210 `str.find()` calls, 5,647 `str.lower()` calls
   - Pre-normalize text once instead of per-pattern
   - **Expected gain**: 5-10 ms savings

### Low Impact (defer until proven bottleneck)

6. **Vectorize entity confidence calculations**
   - Current: Per-entity calculation
   - Proposed: Batch numpy operations
   - **Expected gain**: <5 ms savings

## Comparison: Rule-Based vs LLM-Fallback

This profile used `RULE_BASED` strategy. For comparison:

| Strategy | Est. Time (10K tokens) | Throughput | Trade-off |
|----------|----------------------|------------|-----------|
| **RULE_BASED** | 165 ms | 61,662 t/s | Fast, lower accuracy |
| **LLM_FALLBACK** | ~2-5 seconds | ~2,000-5,000 t/s | Slower, higher accuracy |
| **PURE_LLM** | ~10-30 seconds | ~300-1,000 t/s | Slowest, highest accuracy |

**Recommendation**: For large documents (>10K tokens), use `RULE_BASED` for initial extraction, then selectively apply `LLM_FALLBACK` to high-value or ambiguous entities.

## Test Coverage

- ✅ Profile script created: `profile_batch_262_generate_10k.py`
- ✅ 10k-token legal text generator implemented
- ✅ Profiling data captured: `.prof` binary + `.txt` report
- ✅ Top hotspots identified and analyzed
- ✅ Scaling analysis completed
- ✅ Optimization recommendations documented

## Conclusion

The profiling reveals that **regex pattern matching dominates execution time** (54% in `re.Pattern.search()`, 70% cumulative in `_promote_person_entities()`). The three high-impact optimizations (pre-compile patterns, optimize person promotion, cache results) could reduce execution time by **70-80%** (from 165 ms to ~30-50 ms).

**Current performance (165 ms for 10K tokens) is acceptable for most use cases**, but the sub-linear scaling suggests that documents >50K tokens will require optimization.

**Next Steps**:
1. Implement pre-compiled regex patterns in `ontology_generator.py`
2. Refactor `_promote_person_entities()` to use batched patterns
3. Add spatial indexing for relationship inference
4. Re-profile after optimizations to validate improvements

---

**Files Generated**:
- `profile_batch_262_generate_10k.py` - Profiling script (390 LOC)
- `profile_batch_262_generate_10k.prof` - Binary profile data
- `profile_batch_262_generate_10k.txt` - Detailed profiling report
- `PROFILING_BATCH_262_ANALYSIS.md` - This analysis document
