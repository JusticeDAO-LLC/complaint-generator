# GraphRAG Optimizers API Reference

This document provides a complete API reference for the GraphRAG optimizer modules in `ipfs_datasets_py.optimizers.graphrag`.

## Table of Contents

1. [OntologyGenerator](#ontologygenerator)
2. [QueryUnifiedOptimizer](#queryunifiedoptimizer)
3. [WikipediaOptimizer](#wikipediaoptimizer)
4. [StreamingExtractor](#streamingextractor)
5. [QueryBudget](#querybudget)
6. [QueryMetrics](#querymetrics)
7. [Type System](#type-system)
8. [Error Handling](#error-handling)

---

## OntologyGenerator

**Module:** `ipfs_datasets_py.optimizers.graphrag.ontology_generator`

The main class for generating knowledge graph ontologies from unstructured text using LLMs.

### Initialization

```python
from ipfs_datasets_py.optimizers.graphrag import OntologyGenerator

generator = OntologyGenerator(
    extraction_model: str = "gpt-5.3-codex",
    relationship_llm: str = "gpt-5.3-codex",
    entity_llm: str = "gpt-5.3-codex",
    use_batch_extraction: bool = False,
    max_chunk_size: int = 4000,
    use_descriptions: bool = True
)
```

**Parameters:**
- `extraction_model` (str): LLM model for entity extraction. Default: "gpt-5.3-codex"
- `relationship_llm` (str): LLM model for relationship inference. Default: "gpt-5.3-codex"
- `entity_llm` (str): LLM model for entity enrichment. Default: "gpt-5.3-codex"
- `use_batch_extraction` (bool): Enable batch processing mode. Default: False
- `max_chunk_size` (int): Maximum text chunk size in characters. Default: 4000
- `use_descriptions` (bool): Include entity descriptions. Default: True

### Core Methods

#### extract_entities(results: Any) → Dict[str, Any]

Extract all entities from extraction results and return as a dictionary.

```python
results = generator.run_extraction(text="Example text...")
entities = generator.extract_entities(results)
# Returns: {"entity_id": Entity(...), ...}
```

**Parameters:**
- `results` (Any): EntityExtractionResult or list of results

**Returns:**
- Dict[str, Entity]: Mapping of entity IDs to Entity objects

**Raises:**
- `ValueError`: If results structure is invalid

#### infer_relationships(entities: List[Entity]) → List[Relationship]

Infer relationships between entities using the LLM.

```python
entities = [Entity(id="e1", text="Alice", type="PERSON"), 
            Entity(id="e2", text="Bob", type="PERSON")]
relationships = generator.infer_relationships(entities)
```

**Parameters:**
- `entities` (List[Entity]): List of Entity objects

**Returns:**
- List[Relationship]: Inferred relationships between entities

**Raises:**
- `ValueError`: If entity list is empty
- `RuntimeError`: If LLM call fails

#### extract_entities_async(text: str) → EntityExtractionResult

Asynchronously extract entities from text with asyncio support.

```python
import asyncio

async def extract():
    result = await generator.extract_entities_async("Example text...")
    return result

result = asyncio.run(extract())
```

**Parameters:**
- `text` (str): Input text for entity extraction

**Returns:**
- EntityExtractionResult: Entities, relationships, and metadata

**Raises:**
- `ValueError`: If text is empty
- `asyncio.TimeoutError`: If LLM call exceeds timeout

#### extract_batch_async(texts: List[str]) → List[EntityExtractionResult]

Asynchronously extract entities from multiple texts in parallel.

```python
texts = ["Text 1...", "Text 2...", "Text 3..."]
results = await generator.extract_batch_async(texts)
```

**Parameters:**
- `texts` (List[str]): List of input texts

**Returns:**
- List[EntityExtractionResult]: Extraction results for each text

**Raises:**
- `ValueError`: If texts list is empty

#### extract_with_streaming_async(text: str) → AsyncIterator[Entity]

Stream entities as they are extracted, for real-time processing.

```python
async for entity in generator.extract_with_streaming_async("Text..."):
    print(f"Extracted: {entity.text}")
```

**Parameters:**
- `text` (str): Input text for entity extraction

**Yields:**
- Entity: Individual entities as they are extracted

**Raises:**
- `ValueError`: If text is empty

### Statistical Methods

#### history_kurtosis(results: List[Any]) → float

Calculate excess kurtosis (Fisher's definition) of confidence scores across results.

```python
kurtosis = generator.history_kurtosis(results)
# Returns: kurtosis value (>0 = heavy tails, <0 = light tails)
```

**Parameters:**
- `results` (List[Any]): EntityExtractionResult list

**Returns:**
- float: Excess kurtosis value or 0.0 if insufficient data

**Interpretation:**
- Positive: Heavy-tailed distribution (outlier-prone)
- Negative: Light-tailed distribution (outlier-resistant)
- Zero: Normal distribution (NaN values return 0.0)

#### score_ewma(score: float, previous_ewma: float = None, alpha: float = 0.3) → float

Calculate exponentially weighted moving average for quality trend tracking.

```python
# First call
ewma = generator.score_ewma(0.85)  # Returns: 0.85

# Subsequent calls
ewma = generator.score_ewma(0.92, previous_ewma=0.85, alpha=0.3)
# Returns: 0.3 * 0.92 + 0.7 * 0.85 = 0.879
```

**Parameters:**
- `score` (float): Current quality score [0, 1]
- `previous_ewma` (float, optional): Previous EWMA value. Default: None (uses current score)
- `alpha` (float): Smoothing factor (0, 1]. Default: 0.3
  - Higher alpha (0.7-1.0): More responsive to recent scores
  - Lower alpha (0.1-0.3): Smoother trend, less reactive

**Returns:**
- float: EWMA value

**Raises:**
- `ValueError`: If score not in [0, 1] or alpha not in (0, 1]

#### score_ewma_series(scores: List[float], alpha: float = 0.3) → List[float]

Calculate EWMA for a series of scores.

```python
scores = [0.8, 0.85, 0.92, 0.88]
ewma_series = generator.score_ewma_series(scores, alpha=0.3)
# Returns: [0.8, 0.825, 0.8775, 0.8778]
```

**Parameters:**
- `scores` (List[float]): List of quality scores [0, 1]
- `alpha` (float): Smoothing factor. Default: 0.3

**Returns:**
- List[float]: EWMA values for each score

**Raises:**
- `ValueError`: If scores empty or contain invalid values

### Dimension Analysis Methods

#### confidence_min(results: List[Any]) → float

Get minimum confidence score across all entities in results.

```python
min_conf = generator.confidence_min(results)
# Returns: 0.2 (entire distribution min)
```

**Parameters:**
- `results` (List[Any]): EntityExtractionResult list

**Returns:**
- float: Minimum confidence [0, 1], or 0.0 if no results

**Use Case:** Quality floor assessment

#### confidence_max(results: List[Any]) → float

Get maximum confidence score across all entities in results.

```python
max_conf = generator.confidence_max(results)
# Returns: 0.95 (entire distribution max)
```

**Parameters:**
- `results` (List[Any]): EntityExtractionResult list

**Returns:**
- float: Maximum confidence [0, 1], or 0.0 if no results

**Use Case:** Quality ceiling assessment

#### confidence_range(results: List[Any]) → float

Get range (max - min) of confidence scores.

```python
conf_range = generator.confidence_range(results)
# Returns: 0.75 (max - min spread)

# Interpret range
if conf_range < 0.2:
    quality_stability = "Stable"
elif conf_range < 0.5:
    quality_stability = "Moderate"
else:
    quality_stability = "High variance"
```

**Parameters:**
- `results` (List[Any]): EntityExtractionResult list

**Returns:**
- float: Range value, typically 0-1

**Use Case:** Assess consistency/variance in extraction quality

#### confidence_percentile(results: List[Any], percentile: float = 50.0) → float

Get specified percentile using linear interpolation.

```python
# Quartiles
q1 = generator.confidence_percentile(results, 25)   # 25th percentile
median = generator.confidence_percentile(results, 50) # 50th percentile
q3 = generator.confidence_percentile(results, 75)   # 75th percentile

# Custom percentiles
p95 = generator.confidence_percentile(results, 95)  # Top 5%
```

**Parameters:**
- `results` (List[Any]): EntityExtractionResult list
- `percentile` (float): Percentile to calculate (0-100). Default: 50 (median)

**Returns:**
- float: Percentile value [0, 1], or 0.0 if no results

**Percentile Uses:**
- 25th (Q1): Lower quartile
- 50th (Q2): Median
- 75th (Q3): Upper quartile
- 95th: High-confidence threshold

#### confidence_iqr(results: List[Any]) → float

Get interquartile range (Q3 - Q1) for robust spread measurement.

```python
iqr = generator.confidence_iqr(results)
# Returns: 0.4 (75th percentile - 25th percentile)

# Outlier detection
q1 = generator.confidence_percentile(results, 25)
q3 = generator.confidence_percentile(results, 75)
lower_fence = q1 - 1.5 * iqr
upper_fence = q3 + 1.5 * iqr
```

**Parameters:**
- `results` (List[Any]): EntityExtractionResult list

**Returns:**
- float: IQR value [0, 1], or 0.0 if no results

**Use Cases:**
- Robust spread measurement (less affected by outliers than range)
- Outlier detection (Tukey's fences: fence = Q1 - 1.5*IQR, fence = Q3 + 1.5*IQR)
- Distribution shape analysis

### Utility Methods

#### unique_relationship_types(results: List[Any]) → List[str]

Get sorted list of unique relationship types found in results.

```python
rel_types = generator.unique_relationship_types(results)
# Returns: ['KNOWS', 'WORKS_AT', 'LOCATED_IN', ...]
```

**Parameters:**
- `results` (List[Any]): EntityExtractionResult list

**Returns:**
- List[str]: Sorted, unique relationship type names

---

## QueryUnifiedOptimizer

**Module:** `ipfs_datasets_py.optimizers.graphrag.query_unified_optimizer`

Multi-backend query optimizer supporting Wikipedia, IPLD, and other data sources.

### Initialization

```python
from ipfs_datasets_py.optimizers.graphrag import QueryUnifiedOptimizer

optimizer = QueryUnifiedOptimizer(
    backends: List[str] = ["wikipedia", "ipld"],
    cache_dir: str = ".query_cache",
    max_results: int = 100,
    enable_validation: bool = True
)
```

**Parameters:**
- `backends` (List[str]): Query backends to use. Default: ["wikipedia", "ipld"]
- `cache_dir` (str): Directory for query result caching. Default: ".query_cache"
- `max_results` (int): Maximum results per query. Default: 100
- `enable_validation` (bool): Validate queries before execution. Default: True

### Core Methods

#### optimize_query(query: str, context: Dict[str, Any] = None) → str

Optimize a query for better retrieval results.

```python
original = "What organizations filed bankruptcy in Delaware?"
optimized = optimizer.optimize_query(original)
# Returns improved query with better keywords/structure
```

**Parameters:**
- `query` (str): Original query
- `context` (Dict[str, Any], optional): Additional context for optimization

**Returns:**
- str: Optimized query

#### search_wikipedia(query: str, limit: int = 10) → List[Dict[str, Any]]

Search Wikipedia for query topics.

```python
results = optimizer.search_wikipedia("Delaware bankruptcy", limit=10)
# Returns: [{"title": "...", "text": "...", "url": "..."}, ...]
```

**Parameters:**
- `query` (str): Search query
- `limit` (int): Number of results. Default: 10

**Returns:**
- List[Dict[str, Any]]: Wikipedia articles with metadata

#### search_ipld(query: str, limit: int = 10) → List[Dict[str, Any]]

Search IPLD datasets for query topics.

```python
results = optimizer.search_ipld("bankruptcy filings", limit=10)
```

**Parameters:**
- `query` (str): Search query
- `limit` (int): Number of results. Default: 10

**Returns:**
- List[Dict[str, Any]]: IPLD dataset results

#### filter_by_relevance(results: List[Dict], threshold: float = 0.5) → List[Dict]

Filter results by relevance score.

```python
filtered = optimizer.filter_by_relevance(results, threshold=0.7)
```

**Parameters:**
- `results` (List[Dict]): Query results
- `threshold` (float): Minimum relevance score [0, 1]. Default: 0.5

**Returns:**
- List[Dict]: Filtered results

---

## WikipediaOptimizer

**Module:** `ipfs_datasets_py.optimizers.graphrag.wikipedia_optimizer`

Specialized optimizer for Wikipedia-based fact extraction and retrieval.

### Initialization

```python
from ipfs_datasets_py.optimizers.graphrag import WikipediaOptimizer

optimizer = WikipediaOptimizer(
    language: str = "en",
    cache_enabled: bool = True,
    max_section_length: int = 2000
)
```

**Parameters:**
- `language` (str): Wikipedia language code. Default: "en"
- `cache_enabled` (bool): Enable result caching. Default: True
- `max_section_length` (int): Max characters per section. Default: 2000

### Core Methods

#### search(query: str, limit: int = 20) → List[WikipediaArticle]

Search Wikipedia for articles matching query.

```python
articles = optimizer.search("corporate bankruptcy", limit=20)
```

**Parameters:**
- `query` (str): Search query
- `limit` (int): Number of results. Default: 20

**Returns:**
- List[WikipediaArticle]: Matching articles

#### get_sections(article: WikipediaArticle) → Dict[str, str]

Extract structured sections from an article.

```python
sections = optimizer.get_sections(article)
# Returns: {"Introduction": "...", "History": "...", "See also": "..."}
```

**Parameters:**
- `article` (WikipediaArticle): Article to parse

**Returns:**
- Dict[str, str]: Mapping of section names to content

#### extract_infobox(article: WikipediaArticle) → Dict[str, Any]

Extract structured data from article infobox.

```python
infobox = optimizer.extract_infobox(article)
# Returns: {"founded": 2020, "headquarters": "Delaware", ...}
```

**Parameters:**
- `article` (WikipediaArticle): Article to parse

**Returns:**
- Dict[str, Any]: Infobox key-value pairs

---

## StreamingExtractor

**Module:** `ipfs_datasets_py.optimizers.graphrag.streaming_extractor`

Stream-based entity extraction for large documents.

### Initialization

```python
from ipfs_datasets_py.optimizers.graphrag import StreamingExtractor

extractor = StreamingExtractor(
    chunk_size: int = 2000,
    chunk_overlap: int = 100,
    max_concurrent: int = 5
)
```

**Parameters:**
- `chunk_size` (int): Text chunk size. Default: 2000
- `chunk_overlap` (int): Overlap between chunks. Default: 100
- `max_concurrent` (int): Max concurrent extractions. Default: 5

### Core Methods

#### stream_extract(text: str, callback: Callable[[Entity], None] = None) → AsyncIterator[Entity]

Stream entities from text with optional callback.

```python
async for entity in extractor.stream_extract(large_text):
    print(f"Found: {entity.text}")

# With callback
def on_entity(entity):
    print(f"Entity {entity.id}: {entity.text}")

async for _ in extractor.stream_extract(large_text, callback=on_entity):
    pass
```

**Parameters:**
- `text` (str): Input text
- `callback` (Callable, optional): Function to call for each entity

**Yields:**
- Entity: Entities as extracted

#### stream_extract_file(filepath: str) → AsyncIterator[Entity]

Stream extraction from file without loading entire content into memory.

```python
async for entity in extractor.stream_extract_file("large_document.txt"):
    process(entity)
```

**Parameters:**
- `filepath` (str): Path to document file

**Yields:**
- Entity: Entities from file

**Raises:**
- `FileNotFoundError`: If file doesn't exist
- `IOError`: If file can't be read

---

## QueryBudget

**Module:** `ipfs_datasets_py.optimizers.graphrag.query_budget`

Manage API call budgets and rate limiting across query operations.

### Initialization

```python
from ipfs_datasets_py.optimizers.graphrag import QueryBudget

budget = QueryBudget(
    total_calls: int = 1000,
    interval_seconds: int = 60,
    calls_per_interval: int = 100
)
```

**Parameters:**
- `total_calls` (int): Total calls allowed. Default: 1000
- `interval_seconds` (int): Rate limit window. Default: 60 seconds
- `calls_per_interval` (int): Calls allowed per window. Default: 100

### Core Methods

#### check_budget() → bool

Check if budget allows next call.

```python
if budget.check_budget():
    result = api.call()
else:
    print("Budget exhausted, waiting...")
```

**Returns:**
- bool: True if call allowed, False if budget exhausted

#### get_remaining() → Dict[str, int]

Get remaining budget information.

```python
remaining = budget.get_remaining()
# Returns: {"total": 900, "per_interval": 85}
```

**Returns:**
- Dict[str, int]: Remaining calls and interval estimates

#### reset() → None

Reset budget counters.

```python
budget.reset()
```

---

## QueryMetrics

**Module:** `ipfs_datasets_py.optimizers.graphrag.query_metrics`

Track and analyze query performance metrics.

### Initialization

```python
from ipfs_datasets_py.optimizers.graphrag import QueryMetrics

metrics = QueryMetrics()
```

### Core Methods

#### record_query(query: str, latency_ms: float, result_count: int, quality_score: float) → None

Record query execution metrics.

```python
metrics.record_query(
    query="bankruptcy Delaware",
    latency_ms=245.3,
    result_count=42,
    quality_score=0.87
)
```

**Parameters:**
- `query` (str): Query string
- `latency_ms` (float): Query execution time in milliseconds
- `result_count` (int): Number of results returned
- `quality_score` (float): Quality rating [0, 1]

#### get_statistics() → Dict[str, Any]

Get aggregate query statistics.

```python
stats = metrics.get_statistics()
# Returns: {
#     "total_queries": 100,
#     "avg_latency_ms": 234.5,
#     "avg_quality": 0.82,
#     "p95_latency_ms": 450.0
# }
```

**Returns:**
- Dict[str, Any]: Statistical summary

#### get_slow_queries(threshold_ms: float = 500) → List[Dict]

Get queries that exceeded latency threshold.

```python
slow = metrics.get_slow_queries(threshold_ms=500)
```

**Parameters:**
- `threshold_ms` (float): Latency threshold in milliseconds. Default: 500

**Returns:**
- List[Dict]: Queries exceeding threshold

#### get_low_quality_queries(threshold: float = 0.5) → List[Dict]

Get queries with low quality scores.

```python
low_quality = metrics.get_low_quality_queries(threshold=0.6)
```

**Parameters:**
- `threshold` (float): Quality score threshold [0, 1]. Default: 0.5

**Returns:**
- List[Dict]: Queries below quality threshold

---

## Type System

### Entity

```python
class Entity:
    id: str                 # Unique entity identifier
    text: str              # Entity text
    type: str              # Entity type (PERSON, ORG, LOCATION, etc.)
    confidence: float      # Confidence score [0, 1]
    metadata: Dict[str, Any]  # Additional metadata
```

### Relationship

```python
class Relationship:
    source_id: str         # Source entity ID
    target_id: str         # Target entity ID
    type: str              # Relationship type
    confidence: float      # Confidence score [0, 1]
    metadata: Dict[str, Any]  # Additional metadata
```

### EntityExtractionResult

```python
class EntityExtractionResult:
    entities: List[Entity]           # Extracted entities
    relationships: List[Relationship] # Inferred relationships
    confidence: float                # Overall result confidence
    metadata: Dict[str, Any]         # Extraction metadata
```

---

## Error Handling

### Common Exceptions

#### `ValueError`
Raised when input validation fails.

```python
try:
    result = generator.infer_relationships([])  # Empty list
except ValueError as e:
    print(f"Validation error: {e}")
```

#### `RuntimeError`
Raised when LLM operations fail.

```python
try:
    entities = generator.extract_entities(invalid_result)
except RuntimeError as e:
    print(f"Extraction failed: {e}")
```

#### `asyncio.TimeoutError`
Raised when async operations exceed timeout.

```python
import asyncio

try:
    result = await asyncio.wait_for(
        generator.extract_batch_async(texts),
        timeout=30.0
    )
except asyncio.TimeoutError:
    print("Extraction timeout exceeded")
```

### Best Practices

1. **Always validate input:**
   ```python
   if not text.strip():
       raise ValueError("Text cannot be empty")
   ```

2. **Use context managers for resources:**
   ```python
   # TODO: Add context manager support to optimizers
   ```

3. **Handle async cancellation:**
   ```python
   try:
       result = await generator.extract_entities_async(text)
   except asyncio.CancelledError:
       print("Extraction cancelled")
   ```

4. **Monitor budgets:**
   ```python
   if not budget.check_budget():
       raise RuntimeError("Query budget exhausted")
   ```

---

## Integration Examples

### Complete Entity Extraction Pipeline

```python
from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    QueryUnifiedOptimizer,
    QueryMetrics
)

# Initialize components
generator = OntologyGenerator()
optimizer = QueryUnifiedOptimizer()
metrics = QueryMetrics()

# Extract entities
text = "Apple Inc. was founded by Steve Jobs in California."
result = generator.run_extraction(text)
entities = generator.extract_entities(result)

# Infer relationships
relationships = generator.infer_relationships(list(entities.values()))

# Analyze quality
min_conf = generator.confidence_min([result])
max_conf = generator.confidence_max([result])
median = generator.confidence_percentile([result], 50)
iqr = generator.confidence_iqr([result])

# Record metrics
metrics.record_query(
    query=text,
    latency_ms=100.5,
    result_count=len(entities),
    quality_score=median
)
```

### Async Batch Processing with Streaming

```python
import asyncio
from ipfs_datasets_py.optimizers.graphrag import OntologyGenerator

async def process_documents(documents):
    generator = OntologyGenerator()
    
    # Extract all documents in parallel
    results = await generator.extract_batch_async(documents)
    
    # Stream process with monitoring
    all_entities = []
    for result in results:
        async for entity in generator.extract_with_streaming_async(result.text):
            all_entities.append(entity)
            print(f"Processed entity: {entity.text}")
    
    return all_entities

# Run async processing
documents = ["Doc 1...", "Doc 2...", "Doc 3..."]
entities = asyncio.run(process_documents(documents))
```

### Quality Monitoring Workflow

```python
from ipfs_datasets_py.optimizers.graphrag import OntologyGenerator

def monitor_extraction_quality(results):
    generator = OntologyGenerator()
    
    # Statistical analysis
    stats = {
        'min': generator.confidence_min(results),
        'max': generator.confidence_max(results),
        'range': generator.confidence_range(results),
        'median': generator.confidence_percentile(results, 50),
        'q1': generator.confidence_percentile(results, 25),
        'q3': generator.confidence_percentile(results, 75),
        'iqr': generator.confidence_iqr(results),
        'kurtosis': generator.history_kurtosis(results)
    }
    
    # Trend tracking
    scores = [result.confidence for result in results]
    ewma_series = generator.score_ewma_series(scores, alpha=0.3)
    current_trend = ewma_series[-1] if ewma_series else 0.0
    
    return {
        'statistics': stats,
        'trend': current_trend,
        'quality': 'good' if stats['median'] > 0.8 else 'fair' if stats['median'] > 0.6 else 'poor'
    }

# Monitor quality
results = [...]  # extraction results
quality_report = monitor_extraction_quality(results)
print(f"Quality Assessment: {quality_report}")
```

---

## Performance Considerations

### Memory Usage
- Stream large documents using `extract_with_streaming_async()`
- Use batch processing for multiple documents: `extract_batch_async()`
- Implement caching for repeated queries

### API Budgets
- Monitor QueryBudget for rate limiting
- Implement exponential backoff for retries
- Use query optimization to reduce total calls

### Concurrency
- Control concurrent operations with `max_concurrent` parameter
- Use asyncio for non-blocking I/O
- Monitor system resources during batch operations

---

## Version Information

- **ipfs_datasets_py version:** Latest
- **Python version:** ≥ 3.9
- **Dependencies:** pydantic, aiolimiter, httpx
