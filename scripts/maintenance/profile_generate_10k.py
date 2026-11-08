#!/usr/bin/env python3
"""Profile OntologyGenerator.generate_ontology() on ~10k tokens."""

import sys
sys.path.insert(0, 'ipfs_datasets_py')

import cProfile
import io
import logging
import pstats

from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    DataType,
    ExtractionConfig,
    ExtractionStrategy,
    OntologyGenerationContext,
    OntologyGenerator,
)


def main():
    # Build ~10k token input (250 repeats × ~40 tokens each)
    sentence = (
        "Dr. Alice Smith met Bob Johnson at Acme Corp on January 1, 2024 in New York City. "
        "USD 1,000.00 was paid to Acme Corp. "
        "The obligation of Alice is to file the report. "
    )
    text = sentence * 250
    word_count = len(text.split())
    print(f"Input text: {len(text)} chars, ~{word_count} words, ~{word_count * 1.3:.0f} tokens")
    
    # Setup generator
    log = logging.getLogger("profile.ontology_generator")
    log.disabled = True
    
    generator = OntologyGenerator(use_ipfs_accelerate=False, logger=log)
    context = OntologyGenerationContext(
        data_source="profile",
        data_type=DataType.TEXT,
        domain="general",
        extraction_strategy=ExtractionStrategy.RULE_BASED,
        config=ExtractionConfig(),
    )
    
    def run_once():
        return generator.generate_ontology(text, context)
    
    # Warm caches
    print("Warming caches...")
    run_once()
    
    # Profile
    print("\nProfiling generate_ontology()...")
    profiler = cProfile.Profile()
    profiler.runcall(run_once)
    
    buf = io.StringIO()
    stats = pstats.Stats(profiler, stream=buf).strip_dirs().sort_stats('cumulative')
    stats.print_stats(30)
    output = buf.getvalue()
    print(output)
    
    # Show results
    ontology = run_once()
    meta = ontology.get("metadata", {}) if isinstance(ontology, dict) else {}
    print("\nResults:", {
        "entities": len(ontology.get("entities", [])),
        "relationships": len(ontology.get("relationships", [])),
        "strategy": meta.get("extraction_strategy"),
        "domain": meta.get("domain"),
    })


if __name__ == "__main__":
    main()
