# IPFS Datasets Py Enhancement Implementation Plan

## Purpose

This plan describes how to integrate the expanded `ipfs_datasets_py` capabilities (legal datasets tools, search tools, graph tools, vector tools, optimizer tools, and MCP-oriented tools) into complaint-generator in a staged, low-risk way.

The objective is to improve:
- **Robustness**: fewer failures, better fallback behavior, better observability
- **Accuracy**: better legal authority retrieval, evidence relevance, and claim-to-requirement matching
- **Performance**: predictable latency and scalable retrieval/indexing behavior

## Current Baseline (Already in This Repo)

The repository already has meaningful integration points:

- `mediator/web_evidence_hooks.py`
  - Brave + Common Crawl integration
- `mediator/evidence_hooks.py`
  - IPFS evidence storage + DuckDB evidence metadata
- `mediator/legal_authority_hooks.py`
  - Legal scraper wrappers (US Code / Federal Register / RECAP)
- `mediator/legal_corpus_hooks.py`
  - Complaint corpus keyword/pattern retrieval
- `mediator/legal_hooks.py`
  - Classification → statutes → requirements → questions pipeline
- `complaint_phases/*`
  - Three-phase orchestration, graph builders, and neurosymbolic matching

This plan builds on those modules rather than replacing them.

## Guiding Principles

1. **Adapter-first integration**: isolate `ipfs_datasets_py` API usage behind local adapter classes.
2. **Feature flags + graceful degradation**: every enhancement should fail safe.
3. **Incremental rollout**: one capability family at a time with measurable acceptance criteria.
4. **Evidence provenance by default**: persist source metadata and retrieval rationale.
5. **Evaluation-driven**: accuracy and robustness metrics gate promotion between phases.

## Target Architecture (Enhancement Layer)

Add a dedicated integration layer under mediator:

- `mediator/integrations/ipfs_datasets_adapter.py`
  - central capability detection
  - version/capability registry
  - uniform error mapping
- `mediator/integrations/retrieval_orchestrator.py`
  - hybrid retrieval orchestration (lexical + vector + graph + legal sources)
- `mediator/integrations/provenance.py`
  - source attribution, confidence rationale, and audit records
- `mediator/integrations/caching.py`
  - request/result caching for repeated legal/search calls

Existing hooks call these integration services rather than directly importing package internals.

## Workstreams

### Workstream A: Legal Datasets & Authority Retrieval

**Goal:** Improve legal authority coverage and ranking quality.

Scope:
- Extend `LegalAuthoritySearchHook` to support richer query planning.
- Add query decomposition (claim, jurisdiction, timeframe, authority type).
- Add deduplication and authority normalization (citation/title/source).
- Persist retrieval evidence in authority storage tables with confidence and source metadata.

Acceptance criteria:
- Higher authority recall on regression scenarios.
- Stable behavior when one or more providers are unavailable.
- All returned authorities include provenance (`source`, `query`, `retrieved_at`).

### Workstream B: Search Tool Unification

**Goal:** Consolidate web, legal, and corpus search into one strategy.

Scope:
- Use a single retrieval strategy interface across:
  - web evidence search
  - legal corpus search
  - legal authority search
- Introduce score normalization across sources.
- Implement reranking policy for final evidence/authority shortlist.

Acceptance criteria:
- Unified result schema in all search hooks.
- Deterministic top-k behavior for the same input/config.
- Reduced duplicate results across source types.

### Workstream C: Graph Tool Integration

**Goal:** Improve claim support mapping and gap detection.

Scope:
- Ingest extracted entities/relations into complaint phase graphs.
- Add graph enrichment step between Phase 1 and Phase 2.
- Feed legal graph and dependency graph with normalized authority entities.

Acceptance criteria:
- Increased requirement coverage in dependency graph.
- Fewer unresolved high-priority gaps before Phase 3 formalization.
- Graph serialization remains backward compatible.

### Workstream D: Vector Tool Integration

**Goal:** Improve semantic retrieval for evidence and legal authorities.

Scope:
- Add vector index lifecycle (build/update/query) for selected corpora.
- Hybrid retrieval policy:
  - lexical baseline
  - vector expansion
  - optional graph neighborhood expansion
- Add configurable thresholds for semantic matches.

Acceptance criteria:
- Improved retrieval relevance against benchmark prompts.
- Bounded latency under configured budgets.
- Clear disable path when vector backend unavailable.

### Workstream E: Optimizer Tool Integration

**Goal:** Use optimizer pipelines to tune extraction/retrieval quality and cost.

Scope:
- Integrate optimizer invocation into extraction/retrieval configuration flows.
- Add complaint-type-specific optimizer presets.
- Add automatic fallback profile when optimizer step exceeds latency budget.

Acceptance criteria:
- Better quality/cost trade-off on benchmark runs.
- No regression in default complaint-generation workflow when optimizers disabled.

### Workstream F: Observability, Reliability, and Safety

**Goal:** Make behavior explainable and production-ready.

Scope:
- Structured event logs for retrieval plans, source failures, reranking decisions.
- Retry/circuit-breaker semantics for unstable upstream calls.
- Add safety checks for stale/low-confidence authorities and contradictory evidence.

Acceptance criteria:
- Full traceability for each generated complaint’s evidence/legal basis.
- Reduced hard failures in integration tests.

## Implementation Phases

## Phase 0 — Baseline and Contracts (1 sprint)

Deliverables:
- Define integration interfaces and shared result schema.
- Establish feature flags (env/config) for each new capability family.
- Add compatibility matrix doc for supported `ipfs_datasets_py` capabilities.

Key files:
- `mediator/integrations/*` (new)
- `docs/CONFIGURATION.md` (flags)

Gate to Phase 1:
- Existing tests pass unchanged.
- New interfaces covered by unit tests.

## Phase 1 — Retrieval Foundation (1–2 sprints)

Deliverables:
- Adapter integration in:
  - `mediator/web_evidence_hooks.py`
  - `mediator/legal_authority_hooks.py`
  - `mediator/legal_corpus_hooks.py`
- Unified result schema and dedup/rerank pipeline.

Gate to Phase 2:
- Search hooks produce normalized output with provenance.
- Integration tests validate fallback behavior.

## Phase 2 — Vector + Graph Augmentation (1–2 sprints)

Deliverables:
- Hybrid retrieval (lexical + vector + graph signals).
- Graph enrichment handoff into complaint phases.
- Updated denoiser question generation based on enhanced graph gaps.

Gate to Phase 3:
- Measurable gain in requirement coverage and relevance metrics.

## Phase 3 — Optimizer Integration and Tuning (1 sprint)

Deliverables:
- Optimizer profiles per complaint type.
- Latency and quality guardrails.
- Benchmark scripts for repeated tuning runs.

Gate to Phase 4:
- Quality/cost improvement demonstrated on benchmark suite.

## Phase 4 — Hardening and Rollout (1 sprint)

Deliverables:
- Canary rollout using feature flags.
- Expanded regression tests and failure-injection tests.
- Runbook updates and troubleshooting docs.

Exit criteria:
- Production-ready defaults with safe fallbacks.

## Test & Evaluation Strategy

### 1. Unit Tests
- Adapter behavior (capability detection, error mapping)
- Normalization/dedup/reranking logic
- Provenance model validation

### 2. Integration Tests
- End-to-end retrieval through mediator hooks
- Upstream service unavailable / partial failure scenarios
- Graph and vector augmentation toggles on/off

### 3. Quality Regression Suite
- Complaint scenarios by type (employment, probate, civil rights, etc.)
- Metrics:
  - authority recall/precision
  - evidence relevance@k
  - requirement coverage ratio
  - unresolved critical gap count

### 4. Performance Benchmarks
- Retrieval latency p50/p95
- Throughput under concurrent sessions
- Cost and token usage per complaint session

## Suggested Configuration Flags

Add/extend flags similar to:

- `IPFS_DATASETS_ENHANCED_LEGAL=true|false`
- `IPFS_DATASETS_ENHANCED_SEARCH=true|false`
- `IPFS_DATASETS_ENHANCED_GRAPH=true|false`
- `IPFS_DATASETS_ENHANCED_VECTOR=true|false`
- `IPFS_DATASETS_ENHANCED_OPTIMIZER=true|false`
- `RETRIEVAL_RERANKER_MODE=off|basic|hybrid`
- `RETRIEVAL_MAX_LATENCY_MS=<int>`

Defaults should preserve current behavior until each capability is validated.

## Migration & Rollout Plan

1. Ship adapters behind flags (no behavior change by default).
2. Enable enhanced retrieval in staging for selected complaint types.
3. Compare baseline vs enhanced metrics for at least one full benchmark cycle.
4. Promote feature flags gradually to broader traffic.
5. Keep emergency rollback to baseline hooks at all times.

## Risks and Mitigations

- **Risk:** API drift in `ipfs_datasets_py`
  - **Mitigation:** version/capability checks in adapter layer
- **Risk:** Latency regressions from hybrid retrieval
  - **Mitigation:** strict budgets + short-circuit fallback
- **Risk:** Over-reliance on one source type
  - **Mitigation:** source diversity policy + score normalization
- **Risk:** Inconsistent legal citations
  - **Mitigation:** citation normalization + provenance auditing

## Immediate Next Steps (Execution Backlog)

1. Create `mediator/integrations/` package and interface contracts.
2. Implement a minimal adapter for legal + search capabilities.
3. Refactor one hook (`LegalAuthoritySearchHook`) to consume adapter output.
4. Add normalized result schema tests.
5. Run targeted integration tests and benchmark baseline deltas.

---

This plan is intentionally phased to deliver value early while protecting existing workflows. It emphasizes integration safety, measurable quality gains, and strict fallback behavior so complaint-generator can become more robust and accurate without destabilizing production paths.