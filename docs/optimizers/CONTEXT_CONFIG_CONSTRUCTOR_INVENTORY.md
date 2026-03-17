# Context/Config Constructor Inventory (Core Optimizers)

_Last updated: 2026-02-25_

Purpose: baseline signatures for unifying context/config dataclasses across GraphRAG, logic, and agentic optimizer paths.

## GraphRAG Core
- `OntologyGenerator.__init__(ipfs_accelerate_config, use_ipfs_accelerate, logger, llm_backend, enable_semantic_dedup)`
- `OntologyPipeline.__init__(domain, use_llm, max_rounds, logger, metric_sink)`
- `OntologyCritic.__init__(backend_config, use_llm, logger)`
- `OntologyMediator.__init__(...)` (generator/critic/refinement controls)

## Logic Core
- `LogicExtractor.__init__(model, backend, use_ipfs_accelerate, enable_formula_translation, enable_kg_integration, enable_rag_integration)`
- `LogicTheoremOptimizer.__init__(config, llm_backend, extraction_mode, use_provers, enable_caching, domain, metrics_collector, learning_metrics_collector, logger)`

## Agentic Core
- `OptimizerLLMRouter.__init__(preferred_provider, fallback_providers, enable_tracking, enable_caching, cache)`
- `AgenticOptimizer.__init__(...)` (base class with method-specific subclasses)

## Signature Drift Observations
- `domain` is present in pipeline/unified optimizer paths but not consistently first-class in all constructors.
- Logging/metrics injection parameters (`logger`, `metrics_collector`, `metric_sink`) are inconsistent across modules.
- Backend controls (`llm_backend`, provider/backend config, `use_ipfs_accelerate`) are represented with different naming and shapes.
- Some modules center config in typed dataclasses (`OptimizerConfig`), while others still accept broad dict-style config.

## Proposed Minimum Shared Context Fields
- `domain: str`
- `data_source: str | None`
- `data_type: str | None`
- `session_id: str | None`
- `trace_id: str | None`
- `metadata: dict[str, object]`

## Proposed Minimum Shared Backend Config Fields
- `provider: str`
- `model: str`
- `use_llm: bool`
- `timeout_seconds: float`
- `max_retries: int`
- `circuit_failure_threshold: int`

## Next Step
1. Introduce one typed `UnifiedOptimizerContext` dataclass in `optimizers/common/`.
2. Add adapter helpers to map existing constructor kwargs into the dataclass without breaking API compatibility.
3. Add constructor conformance tests for core GraphRAG/logic/agentic entrypoints.

## Progress 2026-02-25
- Added shared metadata normalization helper in `optimizers/common/unified_config.py`:
  - `ensure_shared_context_metadata(...)`
- Added shared backend-config normalization helper in `optimizers/common/unified_config.py`:
  - `ensure_shared_backend_config(...)`
  - `backend_config_from_constructor_kwargs(...)`
- Unified context adapters now ensure minimum shared metadata keys are present:
  - `session_id`
  - `data_source`
  - `data_type`
  - `trace_id`
- Added/updated conformance tests in
  `tests/unit/optimizers/common/test_unified_config.py` to assert:
  - adapter outputs contain shared metadata keys,
  - existing metadata values are preserved,
  - shared backend-config helper fills minimum keys while preserving existing values,
  - helpers are exported via `optimizers.common`.
- Added constructor inventory conformance tests in
  `tests/unit/optimizers/common/test_constructor_inventory_conformance.py`
  using `inspect.signature(...)` subset assertions for core entrypoints:
  - GraphRAG: `OntologyGenerator`, `OntologyPipeline`, `OntologyCritic`, `OntologyMediator`
  - Logic: `LogicExtractor`, `LogicTheoremOptimizer`
  - Agentic: `OptimizerLLMRouter`, `AgenticOptimizer`
- Added adapter-level backend config conformance tests in
  `tests/unit/optimizers/common/test_unified_config.py` for constructor-style kwargs:
  - GraphRAG `OntologyGenerator` mapping (`ipfs_accelerate_config`, `use_ipfs_accelerate`)
  - GraphRAG `OntologyPipeline` mapping (`use_llm`)
  - GraphRAG `OntologyCritic` mapping (`backend_config`, `use_llm`)
  - Logic `LogicExtractor` mapping (`model`, `backend`)
  - Logic `LogicTheoremOptimizer` mapping (`llm_backend`, `llm_backend_config`)
  - Agentic `OptimizerLLMRouter` mapping (`preferred_provider`)
- Added property-based backend adapter invariants in
  `tests/unit/optimizers/common/test_unified_backend_config_hypothesis.py`
  (auto-skip safe when Hypothesis is unavailable):
  - GraphRAG constructor mapping preserves config values,
  - Logic constructor mapping emits required defaults when config is partial,
  - Unknown adapter sources still return full shared backend key set.
- Added backend adapter source-alias registry and alias-equivalence conformance:
  - `supported_backend_config_source_aliases()` in `optimizers/common/unified_config.py`
  - Conformance checks in `tests/unit/optimizers/common/test_unified_config.py`
    ensure alias variants map to identical normalized backend config payloads.

## Backend Adapter Source Aliases (Doc/Code Sync)
- `graphrag_generator`:
  - `graphrag.ontology_generator`
  - `ontology_generator`
  - `graphrag`
- `graphrag_pipeline`:
  - `graphrag.ontology_pipeline`
  - `ontology_pipeline`
- `graphrag_critic`:
  - `graphrag.ontology_critic`
  - `ontology_critic`
- `logic_extractor`:
  - `logic.logic_extractor`
  - `logic_extractor`
- `logic_unified_optimizer`:
  - `logic.unified_optimizer`
  - `logic_theorem_optimizer`
  - `logic_theorem_optimizer.unified_optimizer`
- `agentic_llm_router`:
  - `agentic.llm_router`
  - `optimizer_llm_router`
  - `agentic`
