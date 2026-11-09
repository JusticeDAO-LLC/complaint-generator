#!/usr/bin/env python3
"""
Batch 231: Profile LLM Fallback Latency

Measures latency impact of LLM fallback in _extract_with_llm_fallback().
Since LLM extraction currently falls back to rule-based extraction when
accelerate is unavailable, this script measures the overhead of invoking
that fallback path (double rule-based pass + fallback checks).
"""

import sys
import time
import statistics
from pathlib import Path

sys.path.insert(0, '/home/barberb/complaint-generator')
sys.path.insert(0, '/home/barberb/complaint-generator/ipfs_datasets_py')

from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
    ExtractionConfig,
    DataType,
    ExtractionStrategy,
)


TEST_TEXT = (
    "This Agreement includes a warranty and indemnification obligation. "
    "The parties agree to arbitration and waiver of jury trial. "
    "Confidential Information must be protected and returned upon termination. "
) * 200  # ~24 KB


def run_timed(generator, context, runs=5, warmup=2):
    for _ in range(warmup):
        generator.extract_entities(TEST_TEXT, context)
    
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        generator.extract_entities(TEST_TEXT, context)
        times.append((time.perf_counter() - start) * 1000)
    
    return {
        "mean_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "min_ms": min(times),
        "max_ms": max(times),
        "stdev_ms": statistics.stdev(times) if len(times) > 1 else 0.0,
        "times_ms": times,
    }


def main():
    print("Batch 231: LLM fallback latency profiling")
    print("=" * 70)
    print(f"Text size: {len(TEST_TEXT.encode('utf-8')) / 1024:.1f} KB")
    
    generator = OntologyGenerator(use_ipfs_accelerate=False)
    
    # Baseline: rule-based only (no fallback)
    base_config = ExtractionConfig(
        llm_fallback_threshold=0.0,
        min_entity_length=2,
    )
    base_context = OntologyGenerationContext(
        data_source='llm_fallback_base.txt',
        data_type=DataType.TEXT,
        domain='legal',
        extraction_strategy=ExtractionStrategy.RULE_BASED,
        config=base_config,
    )
    
    base_stats = run_timed(generator, base_context)
    
    # Fallback path: force fallback by setting a high threshold and llm_backend
    fallback_config = ExtractionConfig(
        llm_fallback_threshold=0.99,
        min_entity_length=2,
    )
    fallback_context = OntologyGenerationContext(
        data_source='llm_fallback_forced.txt',
        data_type=DataType.TEXT,
        domain='legal',
        extraction_strategy=ExtractionStrategy.RULE_BASED,
        config=fallback_config,
    )
    
    # Enable llm_backend to trigger fallback logic
    generator.llm_backend = object()
    fallback_stats = run_timed(generator, fallback_context)
    
    # Report
    print("\nBaseline (rule-based only)")
    print(f"  Mean:   {base_stats['mean_ms']:.2f}ms")
    print(f"  Median: {base_stats['median_ms']:.2f}ms")
    print(f"  Min:    {base_stats['min_ms']:.2f}ms")
    print(f"  Max:    {base_stats['max_ms']:.2f}ms")
    
    print("\nFallback path (forced)")
    print(f"  Mean:   {fallback_stats['mean_ms']:.2f}ms")
    print(f"  Median: {fallback_stats['median_ms']:.2f}ms")
    print(f"  Min:    {fallback_stats['min_ms']:.2f}ms")
    print(f"  Max:    {fallback_stats['max_ms']:.2f}ms")
    
    overhead_ms = fallback_stats['mean_ms'] - base_stats['mean_ms']
    overhead_pct = (overhead_ms / base_stats['mean_ms']) * 100 if base_stats['mean_ms'] else 0.0
    
    print("\nOverhead Summary")
    print(f"  Mean overhead: {overhead_ms:.2f}ms")
    print(f"  Overhead pct:  {overhead_pct:.2f}%")
    print("\nBatch 231: Profiling Complete ✅")


if __name__ == '__main__':
    main()
