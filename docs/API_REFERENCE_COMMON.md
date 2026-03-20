# Common Optimizers API Reference

This document provides API reference for common optimizer classes and utilities in `ipfs_datasets_py.optimizers.common`.

## Table of Contents

1. [BaseOptimizer](#baseoptimizer)
2. [OptimizerConfig](#optimizerconfig)
3. [QueryValidationMixin](#queryvalidationmixin)
4. [AsyncBatchProcessor](#asyncbatchprocessor)
5. [PerformanceMetricsCollector](#performancemetricscollector)
6. [Best Practices](#best-practices)

---

## BaseOptimizer

**Module:** `ipfs_datasets_py.optimizers.common.base_optimizer`

Abstract base class for all optimizer implementations.

### Class Definition

```python
from ipfs_datasets_py.optimizers.common import BaseOptimizer

class MyOptimizer(BaseOptimizer):
    """Custom optimizer implementation."""
    
    def generate(self, input_data, context=None):
        """Generate initial artifacts."""
        pass
    
    def optimize(self, artifact, score, feedback, context=None):
        """Optimize artifact based on feedback."""
        pass
```

### Initialization

```python
optimizer = BaseOptimizer(
    config: OptimizerConfig = None,
    metrics_collector: PerformanceMetricsCollector = None,
    enable_caching: bool = True,
    cache_ttl_seconds: int = 3600
)
```

**Parameters:**
- `config` (OptimizerConfig, optional): Configuration object. Default: None
- `metrics_collector` (PerformanceMetricsCollector, optional): Metrics tracker. Default: None
- `enable_caching` (bool): Enable result caching. Default: True
- `cache_ttl_seconds` (int): Cache time-to-live in seconds. Default: 3600

### Abstract Methods

#### generate(input_data: Any, context: Dict[str, Any] = None) → Any

Generate initial artifacts for optimization.

**Must be implemented by subclasses.**

```python
class CustomOptimizer(BaseOptimizer):
    def generate(self, input_data, context=None):
        """Generate artifacts from input."""
        context = context or {}
        # Implementation generates and returns artifacts
        return {
            'artifact': processed_data,
            'metadata': context
        }
```

**Parameters:**
- `input_data` (Any): Input for generation
- `context` (Dict[str, Any], optional): Execution context. Default: None

**Returns:**
- Any: Generated artifact

**Raises:**
- `NotImplementedError`: If not overridden by subclass

#### optimize(artifact: Any, score: float, feedback: Any = None, context: Dict[str, Any] = None) → Any

Optimize artifact based on score and feedback.

**Must be implemented by subclasses.**

```python
class CustomOptimizer(BaseOptimizer):
    def optimize(self, artifact, score, feedback=None, context=None):
        """Optimize artifact."""
        context = context or {}
        if score < 0.7:
            # Improve artifact
            return self.improve_artifact(artifact)
        return artifact
```

**Parameters:**
- `artifact` (Any): Artifact to optimize
- `score` (float): Current score [0, 1]
- `feedback` (Any, optional): Optional feedback for optimization. Default: None
- `context` (Dict[str, Any], optional): Execution context. Default: None

**Returns:**
- Any: Optimized artifact

**Raises:**
- `NotImplementedError`: If not overridden by subclass

### Concrete Methods

#### run(input_data: Any, iterations: int = 1, context: Dict[str, Any] = None) → List[Any]

Run optimization for specified iterations.

```python
optimizer = CustomOptimizer()
results = optimizer.run(
    input_data="Input text",
    iterations=5,
    context={"model": "gpt-4"}
)
```

**Parameters:**
- `input_data` (Any): Input data
- `iterations` (int): Number of optimization iterations. Default: 1
- `context` (Dict[str, Any], optional): Execution context. Default: None

**Returns:**
- List[Any]: Optimization results at each iteration

#### get_metrics() → Dict[str, Any]

Retrieve collected performance metrics.

```python
metrics = optimizer.get_metrics()
# Returns: {
#     'total_calls': 100,
#     'avg_latency_ms': 234.5,
#     'cache_hits': 45,
#     'cache_misses': 55
# }
```

**Returns:**
- Dict[str, Any]: Performance metrics

#### clear_cache() → None

Clear cached results.

```python
optimizer.clear_cache()
```

---

## OptimizerConfig

**Module:** `ipfs_datasets_py.optimizers.common.base_optimizer`

Configuration object for optimizers.

### Initialization

```python
from ipfs_datasets_py.optimizers.common import OptimizerConfig

config = OptimizerConfig(
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    timeout_seconds: int = 30,
    retries: int = 3,
    cache_enabled: bool = True,
    cache_ttl_seconds: int = 3600,
    batch_size: int = 10,
    parallel_enabled: bool = True,
    max_concurrent_tasks: int = 5
)
```

**Parameters:**
- `model` (str): LLM model name. Default: "gpt-4"
- `temperature` (float): Generation temperature [0, 2]. Default: 0.7
- `max_tokens` (int): Maximum tokens per call. Default: 2000
- `timeout_seconds` (int): Request timeout. Default: 30
- `retries` (int): Number of retry attempts. Default: 3
- `cache_enabled` (bool): Enable result caching. Default: True
- `cache_ttl_seconds` (int): Cache time-to-live. Default: 3600
- `batch_size` (int): Batch processing size. Default: 10
- `parallel_enabled` (bool): Enable parallel processing. Default: True
- `max_concurrent_tasks` (int): Max concurrent tasks. Default: 5

### Properties

#### is_valid() → bool

Check if configuration values are semantically valid.

```python
if config.is_valid():
    optimizer = MyOptimizer(config)
else:
    print("Invalid configuration")
```

**Returns:**
- bool: True if configuration is valid

**Validates:**
- temperature ∈ [0, 2]
- max_tokens > 0
- timeout_seconds > 0
- batch_size > 0
- max_concurrent_tasks > 0

#### to_dict() → Dict[str, Any]

Convert configuration to dictionary.

```python
config_dict = config.to_dict()
# Returns: {'model': 'gpt-4', 'temperature': 0.7, ...}
```

**Returns:**
- Dict[str, Any]: Configuration as dictionary

---

## QueryValidationMixin

**Module:** `ipfs_datasets_py.optimizers.common.query_validation`

Mixin class providing query parameter validation methods.

### Integration

```python
from ipfs_datasets_py.optimizers.common import QueryValidationMixin

class CustomOptimizer(QueryValidationMixin):
    def process_query(self, query, threshold, items):
        # Validate parameters
        query = self.validate_string_param(query, "query")
        threshold = self.validate_numeric_param(threshold, "threshold", 0, 1)
        items = self.validate_list_param(items, "items")
        
        # Process with validated parameters
        return {
            'query': query,
            'threshold': threshold,
            'items': items
        }
```

### Provided Methods

#### validate_string_param(value: Any, param_name: str, min_length: int = 1) → str

Validate and sanitize string parameter.

```python
query = optimizer.validate_string_param(user_input, "query", min_length=3)
```

**Parameters:**
- `value` (Any): Value to validate
- `param_name` (str): Parameter name for error messages
- `min_length` (int): Minimum string length. Default: 1

**Returns:**
- str: Sanitized string

**Raises:**
- `ValueError`: If invalid type or length

#### validate_numeric_param(value: Any, param_name: str, min_val: float = None, max_val: float = None) → float

Validate numeric parameter within range.

```python
threshold = optimizer.validate_numeric_param(user_value, "threshold", 0, 1)
```

**Parameters:**
- `value` (Any): Value to validate
- `param_name` (str): Parameter name for error messages
- `min_val` (float, optional): Minimum allowed value. Default: None
- `max_val` (float, optional): Maximum allowed value. Default: None

**Returns:**
- float: Validated number

**Raises:**
- `ValueError`: If not numeric or out of range

#### validate_list_param(value: Any, param_name: str, min_length: int = 1, allowed_types: Tuple = None) → List

Validate list parameter.

```python
items = optimizer.validate_list_param(user_list, "items", min_length=1, 
                                      allowed_types=(str, int))
```

**Parameters:**
- `value` (Any): Value to validate
- `param_name` (str): Parameter name for error messages
- `min_length` (int): Minimum list length. Default: 1
- `allowed_types` (Tuple, optional): Types allowed in list. Default: None

**Returns:**
- List: Validated list

**Raises:**
- `ValueError`: If not a list or invalid content

---

## AsyncBatchProcessor

**Module:** `ipfs_datasets_py.optimizers.common.async_batch`

Concurrent batch processing for both async and sync functions.

### Initialization

```python
from ipfs_datasets_py.optimizers.common import AsyncBatchProcessor

processor = AsyncBatchProcessor(
    max_concurrent: int = 5,
    timeout_seconds: int = 30,
    retry_attempts: int = 3
)
```

**Parameters:**
- `max_concurrent` (int): Maximum concurrent tasks. Default: 5
- `timeout_seconds` (int): Task timeout. Default: 30
- `retry_attempts` (int): Retry failed tasks. Default: 3

### Core Methods

#### process_async(items: List[Any], async_func: Callable[[Any], Coroutine[Any, Any, Any]]) → List[Any]

Process items concurrently using async function.

```python
async def extract_entity(text):
    return await call_llm(text)

texts = ["Text 1...", "Text 2...", "Text 3..."]
results = await processor.process_async(texts, extract_entity)
```

**Parameters:**
- `items` (List[Any]): Items to process
- `async_func` (Callable): Async function to apply to each item

**Returns:**
- List[Any]: Processed results

**Raises:**
- `asyncio.TimeoutError`: If any task exceeds timeout
- `ValueError`: If items list is empty

#### process_sync(items: List[Any], sync_func: Callable[[Any], Any]) → List[Any]

Process items concurrently using sync function (runs in thread pool).

```python
def extract_feature(text):
    return expensive_computation(text)

texts = ["Text 1...", "Text 2...", "Text 3..."]
results = await processor.process_sync(texts, extract_feature)
```

**Parameters:**
- `items` (List[Any]): Items to process
- `sync_func` (Callable): Sync function to apply to each item

**Returns:**
- List[Any]: Processed results

**Raises:**
- `ValueError`: If items list is empty

#### process_with_callback(items: List[Any], async_func: Callable, callback: Callable[[Any], None]) → None

Process items with callback invoked for each result.

```python
results = []

def on_complete(result):
    results.append(result)
    print(f"Completed: {result}")

await processor.process_with_callback(texts, extract_entity, on_complete)
```

**Parameters:**
- `items` (List[Any]): Items to process
- `async_func` (Callable): Async function to apply
- `callback` (Callable): Callback for each result

#### get_stats() → Dict[str, Any]

Get batch processing statistics.

```python
stats = processor.get_stats()
# Returns: {
#     'total_items': 100,
#     'successful': 95,
#     'failed': 5,
#     'avg_time_ms': 234.5,
#     'total_time_ms': 23450.0
# }
```

**Returns:**
- Dict[str, Any]: Processing statistics

---

## PerformanceMetricsCollector

**Module:** `ipfs_datasets_py.optimizers.common.metrics`

Collect and analyze optimizer performance metrics.

### Initialization

```python
from ipfs_datasets_py.optimizers.common import PerformanceMetricsCollector

collector = PerformanceMetricsCollector()
```

### Core Methods

#### record_execution(operation: str, duration_ms: float, success: bool = True, metadata: Dict = None) → None

Record an operation execution.

```python
collector.record_execution(
    operation="entity_extraction",
    duration_ms=234.5,
    success=True,
    metadata={"input_size": 5000, "entity_count": 42}
)
```

**Parameters:**
- `operation` (str): Operation name
- `duration_ms` (float): Execution time in milliseconds
- `success` (bool): Whether operation succeeded. Default: True
- `metadata` (Dict, optional): Additional metadata. Default: None

#### record_cache_hit(operation: str, key: str) → None

Record cache hit.

```python
collector.record_cache_hit("query_optimization", "query_123")
```

**Parameters:**
- `operation` (str): Operation name
- `key` (str): Cache key

#### record_cache_miss(operation: str, key: str) → None

Record cache miss.

```python
collector.record_cache_miss("query_optimization", "query_456")
```

**Parameters:**
- `operation` (str): Operation name
- `key` (str): Cache key

#### get_summary() → Dict[str, Any]

Get performance summary.

```python
summary = collector.get_summary()
# Returns: {
#     'total_executions': 1000,
#     'successful': 950,
#     'failed': 50,
#     'avg_duration_ms': 234.5,
#     'cache_hit_rate': 0.75
# }
```

**Returns:**
- Dict[str, Any]: Performance summary

#### get_operation_stats(operation: str) → Dict[str, Any]

Get statistics for specific operation.

```python
stats = collector.get_operation_stats("entity_extraction")
# Returns: {
#     'count': 100,
#     'avg_duration_ms': 234.5,
#     'min_duration_ms': 105.2,
#     'max_duration_ms': 512.3,
#     'p95_duration_ms': 450.0,
#     'success_rate': 0.95
# }
```

**Parameters:**
- `operation` (str): Operation name

**Returns:**
- Dict[str, Any]: Operation-specific statistics

---

## Best Practices

### 1. Configuration Management

```python
# Good: Use configuration objects
config = OptimizerConfig(
    model="gpt-5.3-codex",
    temperature=0.7,
    max_tokens=2000,
    timeout_seconds=30
)

optimizer = MyOptimizer(config=config)
```

### 2. Error Handling

```python
from ipfs_datasets_py.optimizers.common import BaseOptimizer

try:
    optimizer = MyOptimizer()
    result = optimizer.generate(input_data)
except ValueError as e:
    print(f"Validation error: {e}")
except RuntimeError as e:
    print(f"Execution error: {e}")
```

### 3. Query Validation

```python
from ipfs_datasets_py.optimizers.common import QueryValidationMixin

class QueryOptimizer(QueryValidationMixin):
    def optimize(self, query, threshold):
        # Always validate inputs
        query = self.validate_string_param(query, "query", min_length=3)
        threshold = self.validate_numeric_param(threshold, "threshold", 0, 1)
        
        # Process validated inputs
        return self._optimize_impl(query, threshold)
```

### 4. Batch Processing

```python
import asyncio
from ipfs_datasets_py.optimizers.common import AsyncBatchProcessor

async def process_documents(docs):
    processor = AsyncBatchProcessor(max_concurrent=5)
    
    async def extract(text):
        return await llm.extract_entities(text)
    
    results = await processor.process_async(docs, extract)
    return results

# Run
results = asyncio.run(process_documents(documents))
```

### 5. Metrics Collection

```python
from ipfs_datasets_py.optimizers.common import (
    BaseOptimizer,
    PerformanceMetricsCollector
)

class InstrumentedOptimizer(BaseOptimizer):
    def __init__(self):
        self.metrics = PerformanceMetricsCollector()
        super().__init__(metrics_collector=self.metrics)
    
    def generate(self, input_data, context=None):
        import time
        start = time.perf_counter()
        try:
            result = self._generate_impl(input_data)
            duration_ms = (time.perf_counter() - start) * 1000
            self.metrics.record_execution("generate", duration_ms, success=True)
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            self.metrics.record_execution("generate", duration_ms, success=False)
            raise
```

### 6. Caching Pattern

```python
class CachedOptimizer(BaseOptimizer):
    def __init__(self, enable_caching=True, cache_ttl_seconds=3600):
        super().__init__(
            enable_caching=enable_caching,
            cache_ttl_seconds=cache_ttl_seconds
        )
    
    def generate(self, input_data, context=None):
        # Check cache first
        cache_key = self._make_cache_key(input_data)
        if cached := self._get_cached(cache_key):
            return cached
        
        # Generate and cache
        result = self._generate_impl(input_data)
        self._cache_result(cache_key, result)
        return result
```

---

## Performance Tuning

### Concurrency Tuning

```python
# For I/O-bound operations
processor_io = AsyncBatchProcessor(max_concurrent=20)

# For LLM calls with rate limiting
processor_llm = AsyncBatchProcessor(max_concurrent=5, retry_attempts=3)

# For CPU-intensive operations
processor_cpu = AsyncBatchProcessor(max_concurrent=4)
```

### Timeout Configuration

```python
# Fast operations
config_fast = OptimizerConfig(timeout_seconds=10)

# Standard operations
config_normal = OptimizerConfig(timeout_seconds=30)

# Complex operations
config_complex = OptimizerConfig(timeout_seconds=120)
```

### Batch Size Optimization

```python
# Small batches for fast feedback
config_interactive = OptimizerConfig(batch_size=5)

# Large batches for efficiency
config_bulk = OptimizerConfig(batch_size=100)
```
