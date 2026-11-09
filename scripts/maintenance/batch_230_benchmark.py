#!/usr/bin/env python3
"""
Batch 230: Benchmark Optimization Deltas

Measures actual performance improvements from:
- Batch 228: Regex pattern pre-compilation (expected 5-10% speedup)
- Batch 229: Config caching with weakref (expected 3-5% speedup)

Uses the same 48.6KB legal text input from Batch 227 profiling analysis.
Compares extract_entities() performance under various scenarios.
"""

import sys
import time
import json
import statistics
from pathlib import Path

sys.path.insert(0, '/home/barberb/complaint-generator')
sys.path.insert(0, '/home/barberb/complaint-generator/ipfs_datasets_py')

from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator,
    OntologyGenerationContext,
    ExtractionConfig,
    DataType,
)


# Load the test data (same 48.6KB legal text from Batch 227)
TEST_DATA_DIR = Path('/home/barberb/complaint-generator/tests/fixtures/data')
TEST_DATA_FILE = TEST_DATA_DIR / 'legal_document_48kb.txt'

# Fallback test data in case file doesn't exist
SAMPLE_LEGAL_TEXT = """
ARTICLE 1: DEFINITIONS AND INTERPRETATION

1.1 In this Agreement, unless the context otherwise requires:

"Agreement" means this agreement including all schedules and appendices;
"Confidential Information" includes all information disclosed by one party to another;
"Force Majeure Event" includes events beyond reasonable control of either party;
"Intellectual Property Rights" means all patents, trademarks, and copyrights;
"Indemnification Obligation" refers to indemnifying and holding harmless;
"Liability Cap" shall not exceed the fees paid in the preceding 12 months;
"Material Breach" means a failure that substantially affects performance;
"Warranty" includes all express and implied guarantees of fitness;
"Arbitration Clause" provides for binding arbitration of disputes;
"Waiver" of any right requires written consent and must be explicit.

ARTICLE 2: REPRESENTATIONS AND WARRANTIES

2.1 Each party represents and warrants that:
(a) It has the legal authority to enter into this Agreement;
(b) This Agreement constitutes a valid and binding obligation;
(c) Execution does not violate any law or regulation;
(d) All information provided is accurate and complete;
(e) There are no undisclosed liabilities or claims pending.

2.2 DISCLAIMER OF WARRANTIES: EXCEPT AS EXPRESSLY PROVIDED, ALL WARRANTIES,
EXPRESS OR IMPLIED, INCLUDING MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE, ARE DISCLAIMED.

ARTICLE 3: CONFIDENTIALITY

3.1 Definition of Confidential Information:
Confidential Information means all technical, business, and financial information
disclosed by one party to the other, including but not limited to:
- Trade secrets and know-how
- Customer lists and contact information
- Financial records and pricing information
- Technical specifications and source code
- Strategic plans and business strategies
- Legal opinions and privileged communications

3.2 Obligations:
The receiving party shall:
(a) Maintain strict confidentiality of all Confidential Information;
(b) Limit disclosure to employees with a legitimate need to know;
(c) Implement reasonable security measures to prevent unauthorized access;
(d) Return or destroy all Confidential Information upon termination;
(e) Acknowledge and respect any third-party intellectual property rights.

ARTICLE 4: LIABILITY AND INDEMNIFICATION

4.1 Limitation of Liability:
IN NO EVENT SHALL EITHER PARTY BE LIABLE FOR:
(a) Any indirect, incidental, consequential, or punitive damages;
(b) Loss of revenue, use, or business opportunity;
(c) Loss of data or information;
(d) Damages exceeding the total fees paid in the 12-month period.

4.2 Indemnification:
Each party shall indemnify and hold harmless the other party from any
third-party claims arising out of:
(a) Breach of representations or warranties;
(b) Infringement of intellectual property rights;
(c) Violation of applicable laws;
(d) Negligence or willful misconduct.

ARTICLE 5: TERM AND TERMINATION

5.1 The Agreement shall continue for an initial term of three (3) years,
renewable by mutual written consent for successive one-year periods.

5.2 Either party may terminate for:
(a) Material breach by the other party, after 30 days written notice;
(b) Convenience with 60 days written notice;
(c) Insolvency or bankruptcy of the other party.

5.3 Upon termination:
(a) All rights and obligations cease;
(b) Confidential Information must be returned or destroyed;
(c) Payment obligations for accrued services remain due;
(d) Survival clauses continue to apply.

ARTICLE 6: ARBITRATION AND DISPUTE RESOLUTION

6.1 Dispute Resolution:
Any dispute arising under this Agreement shall be settled by:
(a) First attempt: good faith negotiation (30 days);
(b) Second attempt: mediation by a neutral third party (60 days);
(c) Final: binding arbitration under applicable arbitration rules.

6.2 Each party waives:
(a) The right to trial by jury;
(b) The right to sue in court;
(c) Appeals except on arbitrator bias or misconduct;
(d) Class action participation.

6.3 The arbitrator shall:
(a) Apply the law of the jurisdiction specified herein;
(b) Issue a written decision with findings of fact and law;
(c) Award reasonable attorneys' fees to the prevailing party;
(d) Issue the decision within six (6) months of arbitration commencement.

ARTICLE 7: GENERAL PROVISIONS

7.1 Governing Law:
This Agreement shall be governed by the laws of [Jurisdiction], without
regard to conflicts of law principles.

7.2 Entire Agreement:
This Agreement constitutes the entire agreement between the parties and
supersedes all prior negotiations, understandings, and agreements.

7.3 Amendments:
No amendment or modification is valid unless in writing and signed by
authorized representatives of both parties.

7.4 Severability:
If any provision is found invalid or unenforceable, the remaining
provisions shall continue in full force and effect.

7.5 Waiver:
No waiver of any provision or right under this Agreement shall be effective
unless in writing signed by the required party.

7.6 Assignment:
Neither party may assign this Agreement without the prior written consent
of the other party, except in connection with a merger or acquisition.

7.7 Force Majeure:
Neither party shall be liable for failure to perform due to Force Majeure
Events beyond their reasonable control, including:
- Acts of God (earthquakes, floods, hurricanes)
- War, terrorism, insurrection
- Pandemics and epidemics
- Government actions and regulatory changes
- Internet or utility failures

7.8 Notices:
All notices must be in writing and delivered personally, by email, or by
certified mail to the addresses specified by each party.

7.9 Relationship:
Nothing in this Agreement creates a partnership, joint venture, or agency
relationship between the parties.

IN WITNESS WHEREOF, the parties have executed this Agreement as of the
Effective Date first written above.
""" * 3  # Repeat to reach ~48KB


def run_benchmark(
    generator: OntologyGenerator,
    test_text: str,
    context: OntologyGenerationContext,
    num_runs: int = 5,
    warmup_runs: int = 2,
    scenario_name: str = "Default",
) -> dict:
    """
    Run benchmark for extract_entities with timing statistics.
    
    Args:
        generator: OntologyGenerator instance
        test_text: Text to extract entities from
        context: Extraction context
        num_runs: Number of benchmark runs
        warmup_runs: Number of warmup runs (not included in stats)
        scenario_name: Name of benchmark scenario
        
    Returns:
        Dict with timing statistics
    """
    print(f"\n{'='*70}")
    print(f"Scenario: {scenario_name}")
    print(f"{'='*70}")
    print(f"Warmup runs: {warmup_runs}, Benchmark runs: {num_runs}")
    
    # Warmup runs
    for i in range(warmup_runs):
        _ = generator.extract_entities(test_text, context)
    
    # Timed benchmark runs
    times = []
    for i in range(num_runs):
        start = time.perf_counter()
        result = generator.extract_entities(test_text, context)
        elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
        times.append(elapsed)
        print(f"  Run {i+1}: {elapsed:.2f}ms ({len(result.entities)} entities)")
    
    # Calculate statistics
    stats = {
        "scenario": scenario_name,
        "num_runs": num_runs,
        "times_ms": times,
        "mean_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "stdev_ms": statistics.stdev(times) if len(times) > 1 else 0.0,
        "min_ms": min(times),
        "max_ms": max(times),
        "total_entities": len(result.entities),
    }
    
    print(f"\nStatistics:")
    print(f"  Mean:   {stats['mean_ms']:.2f}ms")
    print(f"  Median: {stats['median_ms']:.2f}ms")
    print(f"  StdDev: {stats['stdev_ms']:.2f}ms")
    print(f"  Min:    {stats['min_ms']:.2f}ms")
    print(f"  Max:    {stats['max_ms']:.2f}ms")
    
    return stats


def calculate_speedup(baseline_ms: float, optimized_ms: float) -> float:
    """Calculate speedup percentage."""
    return ((baseline_ms - optimized_ms) / baseline_ms) * 100


def main():
    """Main benchmarking entry point."""
    print("Batch 230: Optimization Delta Benchmarking")
    print("=" * 70)
    
    # Load test data
    if TEST_DATA_FILE.exists():
        with open(TEST_DATA_FILE, 'r') as f:
            test_text = f.read()
        print(f"Loaded test data from {TEST_DATA_FILE}")
    else:
        test_text = SAMPLE_LEGAL_TEXT
        print(f"Using generated test data (file not found at {TEST_DATA_FILE})")
    
    text_size_kb = len(test_text.encode('utf-8')) / 1024
    print(f"Test data size: {text_size_kb:.1f} KB")
    
    # Initialize generator
    generator = OntologyGenerator(use_ipfs_accelerate=False)
    print("\nOntologyGenerator initialized (rule-based extraction)")
    
    all_results = []
    
    # Benchmark Scenario 1: Single config (tests Batch 229 cache)
    print("\n" + "="*70)
    print("SCENARIO 1: Single Config (Tests Batch 229 Config Caching)")
    print("="*70)
    
    config1 = ExtractionConfig(
        min_entity_length=3,
        stopwords=['the', 'a', 'and', 'or', 'is', 'are', 'in', 'of', 'to'],
        allowed_entity_types=['LegalConcept', 'Obligation'],
    )
    
    context1 = OntologyGenerationContext(
        data_source='legal_document.txt',
        data_type=DataType.TEXT,
        domain='legal',
        config=config1,
    )
    
    # Run 3 times with same config - should benefit from Batch 229 caching
    for i in range(3):
        stats = run_benchmark(
            generator,
            test_text,
            context1,
            num_runs=3,
            warmup_runs=1,
            scenario_name=f"Config 1 - Call {i+1}",
        )
        all_results.append(stats)
    
    # Benchmark Scenario 2: Multiple configs (no cache hits)
    print("\n" + "="*70)
    print("SCENARIO 2: Multiple Configs (Tests Batch 228 Pattern Caching)")
    print("="*70)
    
    for cfg_idx in range(3):
        config = ExtractionConfig(
            min_entity_length=2 + cfg_idx,
            stopwords=['the', 'a', 'and'] if cfg_idx % 2 == 0 else ['or', 'is', 'in'],
        )
        
        context = OntologyGenerationContext(
            data_source=f'legal_document_{cfg_idx}.txt',
            data_type=DataType.TEXT,
            domain='legal',
            config=config,
        )
        
        stats = run_benchmark(
            generator,
            test_text,
            context,
            num_runs=3,
            warmup_runs=1,
            scenario_name=f"Config {cfg_idx+1} (Multiple) - Call 1",
        )
        all_results.append(stats)
    
    # Benchmark Scenario 3: Default/None config
    print("\n" + "="*70)
    print("SCENARIO 3: Default Config")
    print("="*70)
    
    context_default = OntologyGenerationContext(
        data_source='legal_document_default.txt',
        data_type=DataType.TEXT,
        domain='legal',
        config={},  # Use defaults
    )
    
    stats = run_benchmark(
        generator,
        test_text,
        context_default,
        num_runs=3,
        warmup_runs=1,
        scenario_name="Default Config",
    )
    all_results.append(stats)
    
    # Analysis and summary
    print("\n" + "="*70)
    print("PERFORMANCE ANALYSIS")
    print("="*70)
    
    # Extract timing data for analysis
    config1_times = [all_results[i]['mean_ms'] for i in range(3)]
    
    # Calculate cache efficiency
    if len(config1_times) >= 2:
        cache_speedup = calculate_speedup(config1_times[0], config1_times[1])
        print(f"\nBatch 229 Config Caching Efficiency:")
        print(f"  First call (no cache):  {config1_times[0]:.2f}ms")
        print(f"  Second call (w/cache):  {config1_times[1]:.2f}ms")
        print(f"  Speedup:                {cache_speedup:.2f}%")
    
    # Save results to JSON
    results_file = Path('/home/barberb/complaint-generator/batch_230_benchmarks.json')
    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\nDetailed results saved to: {results_file}")
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Text size: {text_size_kb:.1f} KB")
    print(f"Total benchmark scenarios: {len(all_results)}")
    print(f"Overall mean time: {statistics.mean([r['mean_ms'] for r in all_results]):.2f}ms")
    print(f"Best time: {min([r['mean_ms'] for r in all_results]):.2f}ms")
    print(f"Worst time: {max([r['mean_ms'] for r in all_results]):.2f}ms")
    
    print("\n" + "="*70)
    print("Batch 230: Benchmarking Complete ✅")
    print("="*70)


if __name__ == '__main__':
    main()
