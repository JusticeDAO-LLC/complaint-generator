# Batch 264: _extract_rule_based() Performance Profile

## Overview

This report documents profiling results for `OntologyGenerator._extract_rule_based()` using a ~5k token legal-style document. The goal is to isolate rule-based extraction hot paths and confirm the dominant cost centers before deeper optimizations.

**Date**: 2026-02-23
**Batch**: 264
**Priority**: P2 PERF
**Status**: ✅ COMPLETE

## Test Configuration

```text
Input Size: 5,009 tokens
Domain: legal
Strategy: RULE_BASED
Data Type: TEXT
Profile Target: _extract_rule_based()
```

## Performance Metrics

| Metric | Value |
|--------|-------|
| **Total Execution Time** | 18.50 ms |
| **Entities Extracted** | 15 |
| **Relationships Inferred** | 105 |
| **Function Calls** | 6,153 |

## Top Hotspots (Cumulative Time)

1. **`_extract_rule_based()`** - 0.018s (100% of profile scope)
2. **`infer_relationships()`** - 0.007s
3. **`re.Pattern.search()`** - 0.007s (216 calls)
4. **`_promote_person_entities()`** - 0.007s
5. **`_extract_entities_from_patterns()`** - 0.004s

## Observations

- **Regex search dominates** the non-relationship work. Even with a small entity set (15 entities), 216 regex searches account for a large share of the total runtime.
- **Person promotion is still expensive**, mirroring Batch 262 results. It remains a candidate for batching and regex reuse.
- **Relationship inference is fast** at this scale, but it is already one of the top two cost centers, suggesting it will dominate as entity count rises.

## Optimization Recommendations

### High impact
1. **Batch regex usage in `_promote_person_entities()`**
   - Collapse multiple searches into a single compiled pattern.
   - Avoid repeated `text.lower()` inside loops.

2. **Pre-compile rule patterns and reuse compiled regex**
   - Reduce repeated `re.compile()` calls in extraction patterns.

### Medium impact
3. **Limit relationship candidate pairs**
   - Add heuristic filters (type-based, proximity-based) before full pair evaluation.

### Low impact
4. **Reduce string allocations**
   - Avoid repeated `.strip()` and `.lower()` when inputs are already normalized.

## Next Steps

- Compare the 5k-token profile with the 10k-token Batch 262 profile to confirm scaling behavior.
- Apply regex batching in `_promote_person_entities()` and re-run Batch 264 to quantify improvement.
- Consider adding a proximity window to `infer_relationships()` to avoid worst-case O(n^2) growth.
