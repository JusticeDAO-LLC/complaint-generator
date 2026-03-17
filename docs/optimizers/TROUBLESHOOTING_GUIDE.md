# GraphRAG Optimizer Troubleshooting Guide

This guide provides solutions to common issues encountered when using the GraphRAG ontology extraction and optimization pipeline.

## Table of Contents

1. [Installation & Setup Issues](#installation--setup-issues)
2. [Entity Extraction Problems](#entity-extraction-problems)
3. [Relationship Inference Issues](#relationship-inference-issues)
4. [Performance Problems](#performance-problems)
5. [Configuration Errors](#configuration-errors)
6. [LLM Integration Issues](#llm-integration-issues)
7. [Memory & Resource Constraints](#memory--resource-constraints)
8. [Validation & Quality Problems](#validation--quality-problems)
9. [Backend Resilience Exceptions](#backend-resilience-exceptions)

## Installation & Setup Issues

### Issue: Import Error - Module Not Found

**Symptom**:
```
ModuleNotFoundError: No module named 'ipfs_datasets_py.optimizers.graphrag'
```

**Cause**: Package not installed or incorrect import path

**Solution**:
```bash
# Ensure package is installed
cd ipfs_datasets_py
pip install -e .

# Verify installation
python -c "from ipfs_datasets_py.optimizers.graphrag import OntologyGenerator; print('OK')"
```

**Alternative**: Add to PYTHONPATH
```bash
export PYTHONPATH="/path/to/complaint-generator/ipfs_datasets_py:$PYTHONPATH"
```

### Issue: Missing Dependencies

**Symptom**:
```
ImportError: No module named 'matplotlib'
ModuleNotFoundError: No module named 'plotly'
```

**Cause**: Optional visualization dependencies not installed

**Solution**:
```bash
# Install with visualization support
pip install matplotlib plotly seaborn

# Or suppress warnings
import warnings
warnings.filterwarnings('ignore', message='Matplotlib/Seaborn not available')
```

**Note**: Visualization is optional - core functionality works without it.

### Issue: Type Checking Errors with mypy

**Symptom**:
```
error: Incompatible types in assignment (expression has type "Dict[str, Any]", variable has type "Ontology")
```

**Cause**: TypedDict vs dict type conflicts

**Solution**:
```python
from typing import Dict, Any, cast
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import Ontology

# Use cast to satisfy type checker
ontology: Ontology = cast(Ontology, generator.generate_ontology(text, context))

# Or use Dict[str, Any] for flexibility
ontology: Dict[str, Any] = generator.generate_ontology(text, context)
```

## Entity Extraction Problems

### Issue: No Entities Extracted

**Symptom**:
```python
ontology = generator.generate_ontology(text, context)
print(len(ontology['entities']))  # Output: 0
```

**Diagnosis**:
```python
# Check confidence threshold
config = generator.config
print(f"Confidence threshold: {config.confidence_threshold}")

# Check text content
print(f"Text length: {len(text)} chars, {len(text.split())} tokens")
print(f"Sample: {text[:200]}")
```

**Common Causes & Solutions**:

1. **Confidence threshold too high**:
```python
config = ExtractionConfig(confidence_threshold=0.3)  # Lower threshold
generator = OntologyGenerator(config=config)
```

2. **Empty or malformed text**:
```python
# Validate input
if not text or not text.strip():
    raise ValueError("Input text is empty")

# Remove control characters
import re
text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
```

3. **Unsupported domain**:
```python
# Use generic domain if domain-specific patterns fail
context = OntologyGenerationContext(
    data_source="test",
    data_type=DataType.TEXT,
    domain="general",  # Try "general" instead of specific domain
    extraction_strategy=ExtractionStrategy.RULE_BASED,
)
```

### Issue: Too Many Low-Quality Entities

**Symptom**:
```python
ontology = generator.generate_ontology(text, context)
# Output: 500+ entities, many with confidence < 0.4
```

**Solution**:
```python
# Increase confidence threshold
config = ExtractionConfig(
    confidence_threshold=0.7,  # Higher threshold
    max_entities=100,          # Limit total entities
)

# Post-filter by confidence
high_quality_entities = [
    e for e in ontology['entities']
    if e.get('confidence', 0) >= 0.7
]
```

### Issue: Important Entities Missing

**Symptom**: Known entities in text are not extracted

**Diagnosis**:
```python
# Check if entity appears in text
entity_text = "Acme Corporation"
if entity_text in text:
    print(f"'{entity_text}' found at position {text.index(entity_text)}")
    # Check extraction config
    print(f"Max entities: {config.max_entities}")
    print(f"Confidence threshold: {config.confidence_threshold}")
```

**Solutions**:

1. **Add custom entity patterns**:
```python
# Add domain-specific patterns
config = ExtractionConfig(
    custom_entity_patterns={
        'ORGANIZATION': [
            r'\b[A-Z][a-zA-Z\.\s&]+(Corp|Inc|LLC|Ltd|Company)\b',
            r'\b(Acme|GlobalTech|InnovateCo)\b',  # Known entities
        ]
    }
)
```

2. **Use LLM fallback**:
```python
context = OntologyGenerationContext(
    extraction_strategy=ExtractionStrategy.LLM_FALLBACK,
    llm_fallback_threshold=0.5,  # Use LLM for uncertain extractions
)
```

3. **Lower confidence threshold temporarily**:
```python
config = ExtractionConfig(confidence_threshold=0.3)
# Then filter results manually
```

### Issue: Duplicate Entities

**Symptom**: Same entity extracted multiple times with slight variations

**Example**:
```
{'id': 'e_001', 'text': 'John Smith', 'type': 'PERSON'}
{'id': 'e_002', 'text': 'John Smith ', 'type': 'PERSON'}  # Extra space
{'id': 'e_003', 'text': 'john smith', 'type': 'PERSON'}   # Lowercase
```

**Solution**:
```python
def deduplicate_entities(entities: List[Dict]) -> List[Dict]:
    """Remove duplicate entities based on normalized text."""
    seen = {}
    deduplicated = []
    
    for entity in entities:
        # Normalize text: lowercased, stripped, deduplicated  whitespace
        normalized = ' '.join(entity['text'].lower().split())
        
        if normalized not in seen:
            seen[normalized] = entity
            deduplicated.append(entity)
        else:
            # Keep entity with higher confidence
            if entity.get('confidence', 0) > seen[normalized].get('confidence', 0):
                deduplicated.remove(seen[normalized])
                deduplicated.append(entity)
                seen[normalized] = entity
    
    return deduplicated

# Use after extraction
ontology['entities'] = deduplicate_entities(ontology['entities'])
```

## Relationship Inference Issues

### Issue: No Relationships Inferred

**Symptom**:
```python
print(len(ontology['relationships']))  # Output: 0
```

**Diagnosis**:
```python
# Check if entities exist
print(f"Entities: {len(ontology['entities'])}")

# Check relationship config
print(f"Max relationships: {config.max_relationships}")

# Check inference strategy
print(f"Strategy: {context.extraction_strategy}")
```

**Solutions**:

1. **Ensure sufficient entities**:
```python
# Need at least 2 entities for relationships
if len(ontology['entities']) < 2:
    # Lower confidence threshold to get more entities
    config.confidence_threshold = 0.4
```

2. **Enable relationship inference explicitly**:
```python
config = ExtractionConfig(
    enable_relationship_inference=True,
    max_relationships=500,  # Increase limit
    relationship_confidence_threshold=0.3,  # Lower threshold
)
```

## Backend Resilience Exceptions

These exceptions come from shared resilience wrappers in optimizer backend paths.

### `OptimizerTimeoutError`

**Meaning**: a backend call exceeded configured timeout.

**Immediate actions**:
- Reduce per-request payload size (shorter prompt/text batch).
- Lower concurrency (`max_workers`) for the affected pipeline.
- Retry with a larger timeout only if backend latency is known to be high.

### `RetryableBackendError`

**Meaning**: a retryable backend failure occurred after retry policy was applied.

**Immediate actions**:
- Inspect root cause in `details.last_error` (if present in logs/telemetry).
- Verify backend credentials, rate limits, and service health.
- Keep retries bounded; prefer fixing upstream availability/config issues.

### `CircuitBreakerOpenError`

**Meaning**: circuit breaker is open due to repeated failures; calls are being short-circuited.

**Immediate actions**:
- Stop high-rate retries from callers and allow recovery timeout window.
- Check recent failure burst in logs around the same backend service name.
- Trigger fallback mode (rule-based extraction or deferred processing) until half-open recovery succeeds.

### Operational note

Use these exceptions as control signals, not generic failures:
- timeout => tune workload/timeout
- retryable backend error => inspect dependency health/config
- circuit open => reduce pressure and wait for recovery window

3. **Check entity proximity**:
```python
# Entities must be within proximity window
config = ExtractionConfig(
    relationship_proximity_window=1000,  # Increase window (characters)
)
```

### Issue: Too Many Spurious Relationships

**Symptom**: Many low-confidence or incorrect relationships

**Solution**:
```python
# Increase relationship confidence threshold
config = ExtractionConfig(
    relationship_confidence_threshold=0.6,  # Higher threshold
    max_relationships=100,                  # Limit total
)

# Filter relationships post-extraction
high_quality_rels = [
    r for r in ontology['relationships']
    if r.get('confidence', 0) >= 0.6
]
```

### Issue: Relationship Types Too Generic

**Symptom**: All relationships labeled as "RELATED_TO" or "ASSOCIATED_WITH"

**Cause**: Generic fallback patterns being used

**Solution**:
```python
# Add domain-specific relationship patterns
config = ExtractionConfig(
    custom_relationship_patterns={
        'legal': {
            'EMPLOYS': r'\b(?:employs|employee of|works for)\b',
            'OWNS': r'\b(?:owns|owner of|owned by)\b',
            'CONTRACTS_WITH': r'\b(?:contracts with|agreement with)\b',
        }
    }
)
```

## Performance Problems

**See [PERFORMANCE_TUNING_GUIDE.md](PERFORMANCE_TUNING_GUIDE.md) for comprehensive performance optimization.**

### Issue: Slow Processing (< 10,000 tokens/sec)

**Quick Fixes**:

1. **Use RULE_BASED strategy**:
```python
context = OntologyGenerationContext(
    extraction_strategy=ExtractionStrategy.RULE_BASED,  # Fastest
)
```

2. **Increase confidence threshold**:
```python
config = ExtractionConfig(confidence_threshold=0.7)  # Filter more aggressively
```

3. **Limit entities and relationships**:
```python
config = ExtractionConfig(
    max_entities=100,
    max_relationships=150,
)
```

### Issue: Memory Usage Too High

**Symptom**: Process killed or OOM errors on large documents

**Solution**:
```python
# Use chunking for large documents
def process_large_document_safe(text: str, context: OntologyGenerationContext):
    """Process with memory limits."""
    
    CHUNK_SIZE = 5000  # tokens
    chunks = _chunk_text(text, chunk_size=CHUNK_SIZE)
    
    results = []
    for i, chunk in enumerate(chunks):
        ontology = generator.generate_ontology(chunk, context)
        results.append(ontology)
        
        # Force garbage collection between chunks
        import gc
        gc.collect()
    
    return _merge_ontologies(results)
```

### Issue: Hanging/Infinite Loop

**Symptom**: Process never completes

**Diagnosis**:
```python
import signal

def timeout_handler(signum, frame):
    raise TimeoutError("Extraction timed out")

# Set timeout
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(30)  # 30 second timeout

try:
    ontology = generator.generate_ontology(text, context)
finally:
    signal.alarm(0)  # Cancel timeout
```

**Cause**: Usually infinite loop in regex or relationship inference

**Solution**:
```python
# Add explicit timeouts
config = ExtractionConfig(
    max_extraction_time=30,  # seconds
    max_inference_time=10,   # seconds
)
```

## Configuration Errors

### Issue: Invalid Configuration Parameters

**Symptom**:
```
ValueError: confidence_threshold must be between 0 and 1, got 1.5
```

**Solution**: Validate configuration before use
```python
from ipfs_datasets_py.optimizers.graphrag import ExtractionConfig

def validate_config(config: ExtractionConfig):
    """Validate configuration parameters."""
    
    if not 0 <= config.confidence_threshold <= 1:
        raise ValueError(f"confidence_threshold must be in [0, 1], got {config.confidence_threshold}")
    
    if config.max_entities <= 0:
        raise ValueError(f"max_entities must be positive, got {config.max_entities}")
    
    if config.max_relationships < 0:
        raise ValueError(f"max_relationships cannot be negative, got {config.max_relationships}")
    
    return True

# Use validation
config = ExtractionConfig(confidence_threshold=0.7)
validate_config(config)
```

### Issue: Configuration Not Applied

**Symptom**: Configuration changes have no effect

**Cause**: Generator created before configuration change

**Solution**:
```python
# WRONG: Config change after generator creation
generator = OntologyGenerator()
config = ExtractionConfig(confidence_threshold=0.8)
# generator still uses default config!

# CORRECT: Pass config during initialization
config = ExtractionConfig(confidence_threshold=0.8)
generator = OntologyGenerator(config=config)

# OR: Update generator config explicitly
generator = OntologyGenerator()
generator.config = ExtractionConfig(confidence_threshold=0.8)
```

### Issue: Context Parameters Ignored

**Symptom**: `domain` or `extraction_strategy` has no effect

**Diagnosis**:
```python
# Verify context is being passed
print(f"Context: {context}")
print(f"Domain: {context.domain}")
print(f"Strategy: {context.extraction_strategy}")

# Check generator receives context
ontology = generator.generate_ontology(text, context)  # Context parameter present?
```

**Solution**:
```python
# Ensure context is passed to all methods
ontology = generator.generate_ontology(text, context)  # ✓ Correct
score = critic.evaluate_ontology(ontology, context, text)  # ✓ Context passed
```

## LLM Integration Issues

### Issue: LLM Fallback Not Triggering

**Symptom**: Using `LLM_FALLBACK` strategy but no LLM calls observed

**Diagnosis**:
```python
# Check if confidence is always above threshold
print(f"Fallback threshold: {context.llm_fallback_threshold}")

# Add logging to see when fallback triggers
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Solution**:
```python
# Lower fallback threshold to trigger more often
context = OntologyGenerationContext(
    extraction_strategy=ExtractionStrategy.LLM_FALLBACK,
    llm_fallback_threshold=0.5,  # Trigger below 0.5 confidence
)
```

### Issue: LLM API Errors

**Symptom**:
```
OpenAI API Error: Rate limit exceeded
OpenAI API Error: Invalid API key
```

**Solutions**:

1. **Rate limiting**:
```python
import time

class RateLimitedGenerator(OntologyGenerator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_llm_call = 0
        self.min_interval = 1.0  # seconds between calls
    
    def _call_llm(self, *args, **kwargs):
        # Wait if needed
        elapsed = time.time() - self.last_llm_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        
        result = super()._call_llm(*args, **kwargs)
        self.last_llm_call = time.time()
        return result
```

2. **API key issues**:
```python
import os

# Verify API key is set
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set")

# Test API connection
from openai import OpenAI
client = OpenAI(api_key=api_key)
try:
    client.models.list()
    print("API key valid")
except Exception as e:
    print(f"API key invalid: {e}")
```

3. **Fallback to RULE_BASED on errors**:
```python
try:
    context = OntologyGenerationContext(
        extraction_strategy=ExtractionStrategy.LLM_FALLBACK,
    )
    ontology = generator.generate_ontology(text, context)
except OpenAIError as e:
    logger.warning(f"LLM error, falling back to RULE_BASED: {e}")
    context = OntologyGenerationContext(
        extraction_strategy=ExtractionStrategy.RULE_BASED,
    )
    ontology = generator.generate_ontology(text, context)
```

### Issue: LLM Responses Malformed

**Symptom**: JSON parsing errors from LLM responses

**Solution**:
```python
import json
from json.decoder import JSONDecodeError

def parse_llm_response_safe(response: str) -> Dict:
    """Safely parse LLM response with fallback."""
    
    try:
        return json.loads(response)
    except JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        import re
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        
        # Last resort: return empty result
        logger.error(f"Could not parse LLM response: {response[:200]}")
        return {'entities': [], 'relationships': []}
```

## Memory & Resource Constraints

### Issue: Process Killed (OOM)

**Symptom**: Process terminates without error message

**Diagnosis**:
```bash
# Check memory usage
dmesg | grep -i "killed process"  # Linux
# Look for OOM killer messages
```

**Solutions**:

1. **Set memory limits**:
```python
import resource

# Limit memory to 4GB
resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
```

2. **Use streaming mode**:
```python
config = ExtractionConfig(
    enable_streaming=True,        # Process incrementally
    checkpoint_interval=1000,     # Save state every 1000 tokens
    max_entities=50,              # Strict limits
    max_relationships=75,
)
```

3. **Process in smaller chunks**:
```python
# See "Performance Problems" section for chunking strategy
```

### Issue: High CPU Usage

**Symptom**: CPU at 100% for extended period

**Diagnosis**:
```python
import cProfile

profiler = cProfile.Profile()
profiler.enable()

ontology = generator.generate_ontology(text, context)

profiler.disable()
profiler.print_stats(sort='cumtime')
```

**Common Causes**:
- Regex pattern recompilation (see [PERFORMANCE_TUNING_GUIDE.md](PERFORMANCE_TUNING_GUIDE.md))
- Excessive relationship inference
- Unoptimized loops

**Solution**: Apply performance optimizations from tuning guide

### Issue: Disk Space Exhausted

**Symptom**: Errors writing cache or checkpoints

**Solution**:
```python
# Disable caching if disk space limited
config = ExtractionConfig(
    enable_caching=False,
    checkpoint_enabled=False,
)

# OR set custom cache location with more space
config = ExtractionConfig(
    cache_dir="/mnt/large_disk/cache",
)
```

## Validation & Quality Problems

### Issue: Low Overall Quality Score

**Symptom**:
```python
score = critic.evaluate_ontology(ontology, context, text)
print(f"Overall score: {score.overall}")  # Output: 0.35 (low)
```

**Diagnosis - Check individual dimension scores**:
```python
print(f"Completeness: {score.completeness:.2f}")
print(f"Consistency: {score.consistency:.2f}")
print(f"Clarity: {score.clarity:.2f}")
print(f"Granularity: {score.granularity:.2f}")
print(f"Relationship coherence: {score.relationship_coherence:.2f}")
print(f"Domain alignment: {score.domain_alignment:.2f}")
```

**Solutions by dimension**:

1. **Low Completeness** (missing important entities):
```python
# Lower confidence threshold
config = ExtractionConfig(confidence_threshold=0.4)
# Use LLM fallback for better coverage
context = OntologyGenerationContext(extraction_strategy=ExtractionStrategy.LLM_FALLBACK)
```

2. **Low Consistency** (duplicate or conflicting entities):
```python
# Apply deduplication (see "Duplicate Entities" section)
ontology['entities'] = deduplicate_entities(ontology['entities'])
```

3. **Low Clarity** (ambiguous entity types):
```python
# Use more specific entity type patterns
config = ExtractionConfig(
    entity_type_specificity='high',  # Use specific types
)
```

4. **Low Granularity** (too few entities):
```python
# Lower confidence threshold and increase max entities
config = ExtractionConfig(
    confidence_threshold=0.4,
    max_entities=200,
)
```

5. **Low Relationship Coherence** (nonsensical relationships):
```python
# Increase relationship confidence threshold
config = ExtractionConfig(
    relationship_confidence_threshold=0.6,
)
```

6. **Low Domain Alignment** (wrong domain patterns):
```python
# Verify domain is correct
context = OntologyGenerationContext(
    domain="legal",  # Ensure this matches your document type
)
# Add custom domain patterns
config = ExtractionConfig(
    custom_domain_patterns={'legal': [...]},
)
```

### Issue: Refinement Not Improving Quality

**Symptom**: Multiple refinement rounds but score doesn't increase

**Diagnosis**:
```python
mediator = OntologyMediator(generator=generator, critic=critic)
state = mediator.run_refinement_cycle(text, context)

# Check score progression
for i, score in enumerate(state['critic_scores']):
    print(f"Round {i}: {score.overall:.2f}")

# Output might show: 0.65, 0.66, 0.66, 0.66 (stagnant)
```

**Solutions**:

1. **Adjust refinement strategy**:
```python
mediator = OntologyMediator(
    refinement_strategy='aggressive',  # More changes per round
    min_improvement=0.02,              # Smaller threshold
)
```

2. **Add feedback**:
```python
# Provide explicit feedback to guide refinement
feedback = {
    'missing_entities': ['Contract', 'Party A', 'Party B'],
    'incorrect_relationships': [('Alice', 'OWNS', 'Company')],
}

state = mediator.run_refinement_cycle(text, context, feedback=feedback)
```

3. **Increase max rounds**:
```python
mediator.max_rounds = 10  # Allow more iterations
```

### Issue: Extracting Entities from Wrong Domain

**Symptom**: Medical terms extracted from legal document

**Solution**:
```python
# Be explicit about domain
context = OntologyGenerationContext(
    domain="legal",  # Not "medical"
    data_type=DataType.TEXT,
)

# Disable mixed-domain patterns
config = ExtractionConfig(
    strict_domain_matching=True,
    cross_domain_entities=False,
)
```

## Debugging Techniques

### Enable Debug Logging

```python
import logging

# Enable debug logging for graphrag module
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Optionally, enable for specific modules only
logging.getLogger('ipfs_datasets_py.optimizers.graphrag').setLevel(logging.DEBUG)
```

### Inspect Intermediate Results

```python
class DebugGenerator(OntologyGenerator):
    """Generator with intermediate result inspection."""
    
    def generate_ontology(self, text, context):
        print(f"Input: {len(text)} chars")
        
        # Call parent method with breakpoint
        result = super().generate_ontology(text, context)
        
        print(f"Extracted {len(result['entities'])} entities")
        print(f"Inferred {len(result['relationships'])} relationships")
        
        # Inspect first few entities
        for i, entity in enumerate(result['entities'][:5]):
            print(f"Entity {i}: {entity}")
        
        return result

# Use debug generator
generator = DebugGenerator()
```

### Save Intermediate States

```python
import json
import pickle

# Save ontology for later analysis
with open('ontology_debug.json', 'w') as f:
    json.dump(ontology, f, indent=2, default=str)

# Save full state with Python objects
with open('ontology_debug.pkl', 'wb') as f:
    pickle.dump({'ontology': ontology, 'context': context, 'score': score}, f)
```

### Compare with Known Good Output

```python
def compare_ontologies(ont1: Dict, ont2: Dict) -> Dict:
    """Compare two ontologies to identify differences."""
    
    e1_ids = {e['id'] for e in ont1['entities']}
    e2_ids = {e['id'] for e in ont2['entities']}
    
    return {
        'missing_in_ont2': e1_ids - e2_ids,
        'missing_in_ont1': e2_ids - e1_ids,
        'common_entities': e1_ids & e2_ids,
        'entity_count_diff': len(ont1['entities']) - len(ont2['entities']),
    }

# Compare current output with expected
diff = compare_ontologies(ontology, expected_ontology)
print(f"Differences: {diff}")
```

## Getting Help

If you encounter issues not covered in this guide:

1. **Check existing documentation**:
   - [README.md](../ipfs_datasets_py/optimizers/README.md) - Main documentation
   - [PERFORMANCE_TUNING_GUIDE.md](PERFORMANCE_TUNING_GUIDE.md) - Performance optimization
   - [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md) - Complete configuration reference

2. **Search existing issues**: Check the GitHub issue tracker for similar problems

3. **Enable debug logging**: Add `logging.basicConfig(level=logging.DEBUG)` to get detailed information

4. **Create minimal reproducible example**:
```python
from ipfs_datasets_py.optimizers.graphrag import OntologyGenerator, OntologyGenerationContext, DataType, ExtractionStrategy

# Minimal example that reproduces the issue
generator = OntologyGenerator()
context = OntologyGenerationContext(
    data_source="test",
    data_type=DataType.TEXT,
    domain="legal",
    extraction_strategy=ExtractionStrategy.RULE_BASED,
)

text = "Your problematic text here..."
ontology = generator.generate_ontology(text, context)
print(f"Result: {ontology}")
```

5. **Collect diagnostic information**:
```python
import sys
import ipfs_datasets_py

print(f"Python version: {sys.version}")
print(f"Package version: {ipfs_datasets_py.__version__ if hasattr(ipfs_datasets_py, '__version__') else 'unknown'}")
print(f"Config: {generator.config}")
print(f"Context: {context}")
```

## Version History

- **v1.0** (2026-02-23): Initial troubleshooting guide with common issues and solutions
