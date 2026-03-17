# Distributed Ontology Refinement Design

**Author**: GitHub Copilot  
**Date**: 2026-02-24  
**Status**: Design Proposal  
**Priority**: P2

## Overview

For large-scale ontology extraction (10k+ entities, multi-document corpora), the single-threaded adversarial refinement cycle becomes a bottleneck. This design proposes a distributed master-worker architecture for parallelizing ontology refinement across multiple workers.

## Problem Statement

### Current Limitations

1. **Sequential Refinement**: `OntologyMediator.run_refinement_cycle()` processes entities sequentially in a single thread
2. **Memory Constraints**: Large ontologies (10k+ entities) can exhaust memory on a single machine
3. **Time Complexity**: O(n²) relationship inference scales poorly beyond 5k entities
4. **No Parallelism**: Multiple CPU cores sit idle during refinement

### Scale Targets

- **Small**: < 100 entities (current single-threaded is fine)
- **Medium**: 100-1000 entities (benefit from multi-threading)
- **Large**: 1k-10k entities (require distributed processing)
- **Very Large**: 10k+ entities (require sharding + distributed processing)

## Proposed Architecture

### Component Hierarchy

```
Master Coordinator
├── Task Queue (Redis/RabbitMQ)
├── Result Aggregator
├── State Manager (shared ontology state)
└── Worker Pool
    ├── Worker 1 (entity extraction)
    ├── Worker 2 (relationship inference)
    ├── Worker 3 (criticism)
    └── Worker N (refinement)
```

### Key Components

#### 1. Master Coordinator

**Responsibilities**:
- Shard large text documents into chunks with overlap
- Distribute entity extraction tasks to workers
- Merge partial ontologies from workers
- Coordinate refinement rounds
- Track global state and convergence

**API**:
```python
class DistributedOntologyMaster:
    def __init__(
        self,
        num_workers: int = 4,
        task_queue: TaskQueue,
        result_store: ResultStore,
        merge_strategy: MergeStrategy = "weighted_union",
    ) -> None:
        ...
    
    def extract_distributed(
        self,
        documents: List[str],
        context: OntologyGenerationContext,
        max_rounds: int = 5,
    ) -> OntologyDict:
        """
        Distribute extraction across workers and merge results.
        
        Process:
        1. Shard documents into chunks (with overlap)
        2. Submit extraction tasks to queue
        3. Collect partial ontologies
        4. Merge using deduplication
        5. Run distributed refinement
        6. Aggregate final ontology
        """
        ...
    
    def refine_distributed(
        self,
        ontology: OntologyDict,
        context: OntologyGenerationContext,
        max_rounds: int = 5,
    ) -> OntologyDict:
        """
        Distribute refinement across workers.
        
        Process:
        1. Shard entities into batches
        2. Submit criticism tasks to queue
        3. Collect critic scores
        4. Generate improvement suggestions
        5. Apply improvements in parallel
        6. Merge and validate
        """
        ...
```

#### 2. Worker

**Responsibilities**:
- Pull tasks from queue
- Execute extraction/criticism/refinement
- Report results to master
- Handle failures and retries

**API**:
```python
class DistributedOntologyWorker:
    def __init__(
        self,
        worker_id: str,
        task_queue: TaskQueue,
        result_store: ResultStore,
        generator: OntologyGenerator,
        critic: OntologyCritic,
    ) -> None:
        ...
    
    def run(self) -> None:
        """
        Main worker loop:
        1. Poll task queue
        2. Execute task (extract / criticize / refine)
        3. Store result
        4. Report status to master
        """
        ...
    
    def extract_chunk(
        self,
        text_chunk: str,
        context: OntologyGenerationContext,
    ) -> PartialOntology:
        """Extract entities from a text chunk."""
        ...
    
    def criticize_batch(
        self,
        entities: List[Entity],
        relationships: List[Relationship],
        context: OntologyGenerationContext,
    ) -> List[CriticScore]:
        """Criticize a batch of entities/relationships."""
        ...
```

#### 3. Task Queue

**Options**:
- **Redis Streams**: Lightweight, in-memory, good for small-scale
- **RabbitMQ**: Robust message broker, good for medium-scale
- **Celery**: Python task queue with Redis/RabbitMQ backend
- **Ray**: Distributed Python framework with built-in task scheduling

**Recommendation**: Start with **Ray** for simplest integration with Python code.

**Example with Ray**:
```python
import ray

@ray.remote
def extract_chunk_remote(
    text_chunk: str,
    context: OntologyGenerationContext,
) -> PartialOntology:
    generator = OntologyGenerator()
    result = generator.extract_entities(text_chunk, context)
    return {"entities": result.entities, "relationships": result.relationships}

# Usage
ray.init()
chunks = shard_document(large_text, chunk_size=5000)
futures = [extract_chunk_remote.remote(chunk, context) for chunk in chunks]
results = ray.get(futures)
merged_ontology = merge_ontologies(results)
```

#### 4. Merge Strategy

**Challenges**:
- Duplicate entities across chunks (different IDs)
- Inconsistent relationships (cross-chunk references)
- Confidence score harmonization

**Merge Approaches**:

1. **Weighted Union** (default):
   - Merge entities with semantic deduplication
   - Keep relationships with highest confidence
   - Average confidence scores

2. **Intersection** (high-precision):
   - Only keep entities that appear in multiple chunks
   - Require relationship confirmation from multiple workers
   - Higher confidence threshold

3. **Majority Voting** (consensus):
   - Entity appears in >50% of relevant chunks
   - Relationship confirmed by >50% of workers
   - Reduces noise from individual worker errors

**Implementation**:
```python
class OntologyMerger:
    def merge(
        self,
        partial_ontologies: List[PartialOntology],
        strategy: str = "weighted_union",
    ) -> OntologyDict:
        """
        Merge multiple partial ontologies.
        
        Steps:
        1. Collect all entities and relationships
        2. Apply semantic deduplication to entities
        3. Remap relationships to canonical entity IDs
        4. Filter low-confidence relationships
        5. Validate consistency
        """
        ...
```

#### 5. State Management

**Shared State**:
- Current ontology (entities, relationships)
- Refinement round counter
- Convergence metrics (critic scores over time)
- Worker health status

**Options**:
- **Redis**: Fast, in-memory, good for small state
- **PostgreSQL**: Persistent, supports complex queries
- **Shared filesystem**: Simple, works for file-based state

**Recommendation**: **Redis** for fast iteration, with periodic persistence to disk.

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Master Coordinator                                          │
│                                                             │
│ 1. Shard documents into chunks (5k tokens, 500 token overlap)│
│ 2. Submit extraction tasks to queue                        │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ Task Queue (Ray / RabbitMQ / Redis)                        │
│                                                             │
│ Task 1: Extract chunk 1                                    │
│ Task 2: Extract chunk 2                                    │
│ Task 3: Extract chunk 3                                    │
│ ...                                                         │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ Worker Pool                                                 │
│                                                             │
│ Worker 1 ─────> Extract chunk 1 ─────> Result 1           │
│ Worker 2 ─────> Extract chunk 2 ─────> Result 2           │
│ Worker 3 ─────> Extract chunk 3 ─────> Result 3           │
│                                                             │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ Result Aggregator                                           │
│                                                             │
│ 1. Collect partial ontologies                              │
│ 2. Apply semantic deduplication                            │
│ 3. Merge relationships                                      │
│ 4. Compute global critic score                             │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ Refinement Coordinator                                      │
│                                                             │
│ 1. Identify low-quality entities (critic score < threshold)│
│ 2. Submit refinement tasks to queue                        │
│ 3. Collect refined entities                                │
│ 4. Update global ontology                                  │
│ 5. Check convergence (repeat if needed)                    │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Plan

### Phase 1: Foundation (P2, 1 week)

- [ ] Implement `DistributedOntologyMaster` class
- [ ] Implement `DistributedOntologyWorker` class
- [ ] Integrate Ray for task distribution
- [ ] Add document sharding with overlap
- [ ] Implement basic merge strategy (weighted union)

### Phase 2: Refinement (P2, 1 week)

- [ ] Distribute criticism across workers
- [ ] Implement distributed refinement cycle
- [ ] Add convergence detection
- [ ] Add state management with Redis

### Phase 3: Optimization (P3, 1 week)

- [ ] Add alternative merge strategies (intersection, voting)
- [ ] Optimize memory usage (streaming merge)
- [ ] Add worker health monitoring
- [ ] Implement fault tolerance (retry, failover)

### Phase 4: Testing & Documentation (P2, 1 week)

- [ ] Add integration tests for distributed refinement
- [ ] Benchmark scaling (1 worker vs 4 workers vs 8 workers)
- [ ] Document deployment patterns
- [ ] Add CLI support for distributed mode

## Configuration API

```python
from ipfs_datasets_py.optimizers.graphrag import (
    DistributedOntologyMaster,
    DistributedConfig,
)

# Configuration
config = DistributedConfig(
    num_workers=4,
    chunk_size_tokens=5000,
    chunk_overlap_tokens=500,
    merge_strategy="weighted_union",
    max_refinement_rounds=5,
    convergence_threshold=0.05,
    backend="ray",  # or "celery", "multiprocessing"
)

# Initialize master
master = DistributedOntologyMaster(config)

# Process large corpus
documents = load_documents("corpus/")  # 100+ documents, 1M+ tokens
ontology = master.extract_distributed(
    documents=documents,
    context=OntologyGenerationContext(
        data_source="corpus",
        data_type=DataType.TEXT,
        domain="legal",
        extraction_strategy=ExtractionStrategy.HYBRID,
    ),
)

# Ontology is ready for use
print(f"Extracted {len(ontology['entities'])} entities")
print(f"Inferred {len(ontology['relationships'])} relationships")
```

## Performance Targets

| Metric | Single-Threaded | Distributed (4 workers) | Distributed (8 workers) |
|--------|----------------|------------------------|------------------------|
| 10k entities | 5 min | 1.5 min | < 1 min |
| 50k entities | 30 min | 8 min | 4 min |
| 100k entities | 2 hours | 30 min | 15 min |
| Memory | 4 GB | 1 GB/worker | 1 GB/worker |

## Risks & Mitigations

### Risks

1. **Network Overhead**: Serializing/deserializing large ontologies is expensive
   - **Mitigation**: Use efficient serialization (msgpack, protobuf)
   
2. **Duplicate Entity Explosion**: Semantic dedup may fail on edge cases
   - **Mitigation**: Tune threshold, add manual review step
   
3. **Worker Failures**: Workers may crash or hang
   - **Mitigation**: Implement timeout, retry, and failover logic
   
4. **Consistency**: Concurrent updates to shared state may conflict
   - **Mitigation**: Use atomic operations, versioning, or optimistic locking

5. **Debugging Complexity**: Distributed systems are harder to debug
   - **Mitigation**: Add comprehensive logging, metrics, and tracing (OpenTelemetry)

## Alternatives Considered

### 1. Multi-threading (ThreadPoolExecutor)

**Pros**: Simple, no external dependencies  
**Cons**: GIL limits CPU parallelism, memory shared across threads

**Verdict**: Good for I/O-bound tasks (LLM API calls), poor for CPU-bound tasks (entity extraction)

### 2. Multi-processing (ProcessPoolExecutor)

**Pros**: True parallelism, no GIL  
**Cons**: High memory overhead (copies of ontology in each process), IPC overhead

**Verdict**: Good for medium-scale (1k-10k entities), but memory inefficient for very large ontologies

### 3. Dask

**Pros**: Built for large-scale data processing, integrates with pandas/numpy  
**Cons**: Heavyweight, learning curve, overkill for this use case

**Verdict**: Considered for future if data preprocessing becomes a bottleneck

### 4. Ray (Recommended)

**Pros**: Python-native, easy to use, good for ML/AI workloads, built-in fault tolerance  
**Cons**: Additional dependency, cluster setup complexity

**Verdict**: **Best fit** for distributed ontology refinement

## Success Criteria

1. ✅ Process 10k-entity ontology in < 2 minutes on 4 workers
2. ✅ Memory usage stays < 2 GB per worker
3. ✅ Zero data loss (all entities preserved across merge)
4. ✅ Quality delta < 5% vs single-threaded (measured by F1 score)
5. ✅ Graceful degradation (fallback to single-threaded if workers unavailable)

## References

- [Ray Documentation](https://docs.ray.io/)
- [Celery Documentation](https://docs.celeryq.dev/)
- [GraphRAG Architecture](../ARCHITECTURE.md)
- [Performance Tuning Guide](../PERFORMANCE_TUNING_GUIDE.md)

## Changelog

- **2026-02-24**: Initial design proposal (GitHub Copilot)
