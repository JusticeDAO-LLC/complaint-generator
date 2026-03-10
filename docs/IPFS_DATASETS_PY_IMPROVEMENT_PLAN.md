# IPFS Datasets Py Improvement Plan

Date: 2026-03-10

## Purpose

Define a practical, phased plan for turning `ipfs_datasets_py` from a set of direct hook-level imports into a first-class integration layer for complaint generation, legal research, evidence organization, graph reasoning, theorem-assisted validation, and archival search.

This plan is grounded in the current complaint-generator codebase and its existing integration seams:

- `backends/llm_router_backend.py` already uses `ipfs_datasets_py.llm_router`
- `mediator/evidence_hooks.py` already uses `ipfs_datasets_py.ipfs_backend_router`
- `mediator/web_evidence_hooks.py` already uses `ipfs_datasets_py.web_archiving`
- `mediator/legal_authority_hooks.py` already uses `ipfs_datasets_py.legal_scrapers` and `ipfs_datasets_py.web_archiving`
- tests and docs already reference `ipfs_datasets_py.optimizers.graphrag` and `ipfs_datasets_py.logic`

## Executive Summary

The right strategy is not to scatter more direct imports across the codebase. The current system already shows the downside of that approach:

- repeated `sys.path` mutation in multiple files
- per-module optional import logic duplicated across hooks
- IPFS, DuckDB, search, and legal-research data living in parallel stores without a single canonical evidence graph
- graph reasoning in `complaint_phases/` and GraphRAG or logic capabilities in `ipfs_datasets_py` not yet unified
- no capability contract describing what happens when the submodule is missing or partially initialized

The target state should be:

1. A single `ipfs_integrations` layer inside complaint-generator that owns all imports and capability detection.
2. A unified evidence and authority pipeline that stores raw artifacts, normalized metadata, embeddings, graph nodes, and legal citations in a consistent model.
3. Graph and theorem-proving services used to validate complaint completeness, evidence sufficiency, statutory element coverage, and contradiction detection.
4. Search and web-archiving tools feeding the same case graph, not separate ad hoc result lists.
5. A phased rollout that preserves graceful degradation when `ipfs_datasets_py` is unavailable.

## Current State Assessment

### What already exists

- The mediator initializes evidence, legal-authority, and web-evidence hooks in `mediator/mediator.py`.
- Evidence storage already writes metadata to DuckDB and optionally stores bytes in IPFS.
- Legal authority search already queries legal scrapers and Common Crawl.
- Web evidence search already queries Brave Search and Common Crawl.
- The complaint generator already has internal graph structures in `complaint_phases/`:
  - knowledge graph
  - dependency graph
  - legal graph
  - neurosymbolic matcher
- Repo tests and docs already assume GraphRAG and logic modules from `ipfs_datasets_py` are relevant.

### What is missing

- No single integration boundary for `ipfs_datasets_py`
- No shared capability registry for optional features
- No normalized case artifact schema spanning:
  - evidence files
  - legal authorities
  - web results
  - extracted entities
  - graph relationships
  - formal legal predicates
- No orchestration layer that turns search results into verified legal support
- No theorem-prover or logic-validation stage connected to complaint generation
- No import-stable adapter layer to shield complaint-generator from `ipfs_datasets_py` API drift
- No full test matrix for submodule-present vs submodule-absent behavior

### Important operational constraint

In this checkout, `ipfs_datasets_py` is not populated with importable source files. That means the plan must assume three operating modes:

1. `ipfs_datasets_py` fully initialized
2. `ipfs_datasets_py` partially available
3. `ipfs_datasets_py` absent

The integration design should treat those as supported modes, not as edge cases.

## Strategic Goals

### Goal 1: Centralize imports and capability checks

All `ipfs_datasets_py` imports should move behind a single complaint-generator package, for example:

```python
from complaint_generator.ipfs_integrations import services
```

That layer should own:

- path discovery
- submodule detection
- optional imports
- feature flags
- compatibility shims
- typed service wrappers

### Goal 2: Build a unified legal knowledge plane

All data gathered from scrapers, search engines, graph builders, and reasoning tools should land in a shared case model:

- raw artifact store in IPFS or local fallback
- relational metadata in DuckDB
- graph representation for relationships and provenance
- searchable text and embeddings for retrieval
- formal predicates for theorem-style validation

### Goal 3: Turn research into structured complaint support

The complaint generator should not stop at “found some authorities” or “found some evidence.” It should answer:

- which claim elements are covered
- which elements lack factual support
- which authorities support or weaken each element
- which evidence is primary, secondary, or contextual
- which facts are contradicted or unproven

### Goal 4: Make graph and logic capabilities operational

The existing `complaint_phases/` graph logic should be connected to:

- GraphRAG extraction from documents and web content
- legal authority citation graphs
- theorem-proving or logic-validation passes for claim sufficiency
- contradiction detection and missing-premise detection

## Recommended Architecture

### 1. New integration package

Add a new package inside complaint-generator:

```text
integrations/
  ipfs_datasets/
    __init__.py
    capabilities.py
    loader.py
    storage.py
    search.py
    legal.py
    graphs.py
    logic.py
    documents.py
    provenance.py
    types.py
```

Responsibilities:

- `loader.py`: locate submodule, manage import path, expose stable import helpers
- `capabilities.py`: declare what features are available at runtime
- `storage.py`: IPFS and content-addressed artifact operations
- `search.py`: Brave, Common Crawl, and search backend wrappers
- `legal.py`: legal scraper wrappers and authority normalization
- `graphs.py`: GraphRAG and graph-ingestion adapters
- `logic.py`: theorem-prover, logic validator, and predicate conversion adapters
- `documents.py`: PDF and text extraction wrappers
- `provenance.py`: normalize source, timestamp, CID, URL, and derivation metadata
- `types.py`: typed dataclasses or pydantic models for normalized artifacts

This package should be the only place allowed to import from `ipfs_datasets_py` directly.

### 2. Capability registry

Create a single capability object initialized once at startup.

Example capabilities:

- `llm_router`
- `ipfs_storage`
- `legal_scrapers`
- `web_archiving`
- `document_processing`
- `graphrag`
- `logic_tools`
- `zkp_or_prover_tools`

Example shape:

```python
CapabilityStatus(
    available=True,
    module_path="ipfs_datasets_py.web_archiving",
    degraded_reason=None,
)
```

Mediator startup should log this capability map once, instead of logging per-file import failures in multiple hooks.

### 3. Unified case artifact model

Introduce a normalized schema shared by evidence, authorities, and derived graph facts.

Core entities:

- `CaseArtifact`
  - artifact_id
  - cid
  - source_type
  - mime_type
  - content_hash
  - acquisition_method
  - source_url
  - timestamp
- `CaseAuthority`
  - citation
  - authority_type
  - jurisdiction
  - source_system
  - text
  - relevance_score
- `CaseFact`
  - fact_id
  - text
  - extracted_from_artifact_id
  - confidence
  - temporal_scope
- `CaseClaimElement`
  - claim_type
  - element_id
  - element_text
  - required_proof_type
- `CaseSupportEdge`
  - source_node
  - target_node
  - relation_type
  - confidence
  - provenance
- `FormalPredicate`
  - predicate_id
  - predicate_text
  - grounded_fact_ids
  - authority_ids

This creates one path from raw file or web page to formal complaint support.

### 4. Graph composition model

Unify four graph layers:

1. Intake graph
   - people, organizations, dates, events, places
2. Evidence graph
   - artifacts, sources, provenance, duplicates, corroboration
3. Legal graph
   - statutes, elements, rules, defenses, procedural requirements
4. Formal reasoning graph
   - predicates, entailment edges, contradiction edges, missing-premise nodes

The existing `complaint_phases` graphs should become the host model, and `ipfs_datasets_py` GraphRAG and logic outputs should enrich them rather than competing with them.

## High-Value Feature Integrations

### Workstream A: Legal scrapers and legal dataset search

Objective: move from simple query-and-store behavior to authority-aware claim support.

Use `ipfs_datasets_py` for:

- US Code retrieval
- Federal Register retrieval
- RECAP or case-law retrieval
- web legal corpus search

Improve complaint-generator by adding:

- authority normalization into one schema
- citation deduplication across sources
- claim-element-to-authority linking
- jurisdiction filters based on complaint metadata
- authority freshness and controlling-authority ranking
- automated “best supporting authorities” summaries per claim

Recommended mediator changes:

- refactor `mediator/legal_authority_hooks.py` to call `integrations.ipfs_datasets.legal`
- store linked authority IDs on legal graph nodes
- add an authority relevance pass before final complaint drafting
- add an authority conflict pass to catch contradictory precedent or mismatched jurisdiction

### Workstream B: Web archiving and search engines

Objective: treat search as evidence acquisition, not just result listing.

Use `ipfs_datasets_py` for:

- Brave Search for current sources
- Common Crawl for historical sources
- archive tooling for content preservation

Improve complaint-generator by adding:

- source capture pipeline: search result -> fetch -> hash -> store -> index -> graph link
- search strategy templates per claim type
- domain trust scoring
- duplicate clustering across search engines and archive snapshots
- temporal evidence analysis to prove what a site said on a given date

Recommended mediator changes:

- refactor `mediator/web_evidence_hooks.py` to return normalized `CaseArtifact` objects
- add fetch-and-archive step before saving evidence metadata
- connect archived artifacts to claim elements and legal authorities through provenance edges
- add “historical policy change” and “public statement timeline” workflows

### Workstream C: IPFS storage and provenance

Objective: make every artifact reproducible and traceable.

Use `ipfs_datasets_py` for:

- content-addressable storage
- CID retrieval
- pinning or backend routing

Improve complaint-generator by adding:

- immutable storage for every fetched or uploaded artifact
- deterministic content hashing before graph ingestion
- provenance tables for source URL, fetch time, transform pipeline, and derived outputs
- duplicate detection by hash and semantic similarity
- one-click regeneration of evidence bundles for filing or review

Recommended mediator changes:

- refactor `mediator/evidence_hooks.py` to use `integrations.ipfs_datasets.storage`
- store transform lineage: raw bytes -> parsed text -> extracted entities -> predicates
- add bundle manifests for exhibits and authority packets

### Workstream D: GraphRAG and graph database integration

Objective: use `ipfs_datasets_py` graph tooling to improve complaint structure, retrieval, and synthesis.

Use `ipfs_datasets_py` for:

- GraphRAG extraction
- ontology or relationship inference
- graph-oriented semantic retrieval

Improve complaint-generator by adding:

- ingestion of evidence text and legal authorities into the case graph
- hybrid retrieval using graph traversal plus keyword plus embedding search
- graph-based “what facts support this element?” queries
- graph-based “what evidence gaps remain?” queries
- cross-document entity resolution for repeated actors and events

Recommended code touchpoints:

- connect graph enrichment into `complaint_phases/knowledge_graph.py`
- connect rule-element linking into `complaint_phases/legal_graph.py`
- use `complaint_phases/dependency_graph.py` as the place where support edges and missing-premise nodes are materialized
- expose graph queries through mediator convenience methods

### Workstream E: Theorem provers and logic validation

Objective: use formal reasoning to validate whether the complaint is legally coherent and sufficiently supported.

Use `ipfs_datasets_py` logic stack for:

- rule representation
- predicate normalization
- theorem-style validation or logic checks
- contradiction or consistency checks

Potential uses inside complaint-generator:

- convert claim elements into predicates
- convert extracted facts into grounded predicates
- test whether the fact set can satisfy each legal element
- detect unsupported leaps in reasoning
- detect contradictory timelines or mutually exclusive claims
- produce a machine-readable explanation of why a draft is weak or complete

Suggested reasoning outputs:

- `provable_elements`
- `unprovable_elements`
- `missing_predicates`
- `contradictory_predicates`
- `authorities_without_fact_support`
- `facts_without_legal_relevance`

This should feed both the denoiser and the final complaint drafting stage.

### Workstream F: Document processing and legal corpus ingestion

Objective: treat uploaded evidence and scraped legal materials as first-class parseable assets.

Use `ipfs_datasets_py` for:

- PDF processing
- OCR fallback
- text extraction
- document chunking and metadata extraction

Improve complaint-generator by adding:

- upload-time parsing into structured text and metadata
- citation extraction from exhibits
- timeline extraction from letters, emails, and notices
- chunk-level provenance for every extracted entity or predicate
- automatic exhibit summaries with legal relevance labels

## Proposed End-to-End Pipeline

### Target flow

1. Complaint intake generates claim hypotheses and key entities.
2. Search services generate targeted legal and factual searches.
3. Results are fetched, archived, hashed, and stored as artifacts.
4. Documents are parsed into text, metadata, and chunks.
5. GraphRAG extracts entities, relationships, and cross-document links.
6. Legal scrapers fetch authorities and map them to claim elements.
7. Logic adapters convert facts and elements into formal predicates.
8. Reasoning services identify supported, unsupported, and contradictory elements.
9. The denoiser asks targeted follow-up questions for unsupported elements.
10. Final drafting uses the validated support graph to generate the complaint.

### Key rule

Every generated statement in the final complaint should be traceable to:

- user-provided facts
- uploaded or discovered evidence
- legal authority
- or a clearly marked inference

## Phased Delivery Plan

### Phase 0: Stabilize the import boundary

Outcome: safe, observable use of `ipfs_datasets_py` in all environments.

Tasks:

- create `integrations/ipfs_datasets/loader.py`
- remove repeated `sys.path` mutations from hook modules
- centralize optional imports and capability reporting
- add startup diagnostics for submodule state
- define adapter interfaces for storage, search, legal, graph, and logic

Success criteria:

- mediator starts cleanly with or without the submodule
- one capability log replaces duplicate import warnings
- no direct `ipfs_datasets_py` imports remain outside the adapter layer

### Phase 1: Normalize search, storage, and authority ingestion

Outcome: one artifact and authority model across evidence and research.

Tasks:

- normalize search results into shared dataclasses
- add provenance records for web and legal retrieval
- extend DuckDB schema for artifacts, authorities, and derivations
- deduplicate authorities and evidence by hash, URL, and citation
- persist fetched body text and normalized metadata

Success criteria:

- web evidence and legal authorities share common provenance fields
- the same claim can reference both authority IDs and artifact IDs
- duplicate search hits collapse into canonical records

### Phase 2: Integrate GraphRAG into complaint phases

Outcome: graph-driven retrieval and gap analysis.

Tasks:

- ingest parsed artifacts and authority text into graph enrichment services
- connect GraphRAG outputs to knowledge, dependency, and legal graphs
- expose graph traversal queries for support and gap analysis
- add entity-resolution rules across documents and sources

Success criteria:

- each claim element can list supporting facts, artifacts, and authorities
- gap analysis uses graph evidence, not just prompt heuristics
- graph-derived support improves question generation quality

### Phase 3: Add theorem-proving and formal validation

Outcome: complaints are checked for legal sufficiency and internal consistency.

Tasks:

- define claim-element predicate templates per complaint type
- translate extracted facts into normalized predicates
- run logic validation against legal elements
- surface missing-premise and contradiction reports
- feed results into denoiser questions and draft generation

Success criteria:

- unsupported elements are explicitly identified before drafting
- contradictory facts are surfaced early
- final draft can include an internal support report for review

### Phase 4: Productize and optimize

Outcome: robust operator workflows and measurable quality gains.

Tasks:

- build case dashboards around evidence coverage and authority support
- add background jobs for ingestion, parsing, graphing, and validation
- add caching for repeated research workflows
- add benchmark suites for graph and reasoning quality
- add adversarial harness scenarios for weak evidence and conflicting authorities

Success criteria:

- ingestion and analysis can run asynchronously
- quality metrics improve across benchmark complaints
- operators can inspect provenance and support coverage without reading raw tables

## Required Code Changes

### Complaint-generator modules to refactor first

- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`
- `backends/llm_router_backend.py`
- `mediator/mediator.py`

### Complaint-generator modules to enrich next

- `complaint_phases/knowledge_graph.py`
- `complaint_phases/dependency_graph.py`
- `complaint_phases/legal_graph.py`
- `complaint_phases/neurosymbolic_matcher.py`
- `complaint_analysis/` keyword, pattern, and risk modules for predicate templates and retrieval hints

### New schemas and storage work

Add or extend DuckDB tables for:

- artifacts
- artifact_transforms
- authorities
- authority_links
- graph_nodes
- graph_edges
- predicates
- validation_runs
- contradictions
- claim_element_coverage

## Data Model Recommendations

### Evidence and authority provenance

Every artifact or authority should record:

- source URL or origin
- acquisition timestamp
- acquisition tool
- CID or local content hash
- parser version
- extraction version
- graph-ingestion version
- reasoning version

This prevents silent drift and makes results reproducible.

### Claim-element coverage matrix

Create a persistent matrix keyed by:

- complaint ID
- claim type
- legal element
- supporting facts
- supporting authorities
- supporting artifacts
- support strength
- unresolved gaps

This matrix should drive both drafting and user follow-up.

## Testing Plan

### Unit tests

- capability detection with submodule absent
- capability detection with mocked modules present
- normalization of search and scraper results
- provenance generation and deduplication
- graph-link generation for artifacts, facts, and authorities
- predicate generation from claim elements and facts

### Integration tests

- upload evidence -> store -> parse -> graph -> validate
- search web -> archive -> store -> graph link
- search authorities -> normalize -> map to claim elements
- theorem validation over a known complaint scenario
- graceful degradation when one or more `ipfs_datasets_py` capabilities are missing

### Benchmark and quality tests

- retrieval precision for authority search
- evidence deduplication quality
- graph coverage per complaint type
- contradiction-detection accuracy
- complaint-element support coverage before and after integration

### Adversarial harness additions

Add scenarios for:

- evidence exists but legal authority is weak
- authority exists but evidence is missing
- evidence conflicts with user narrative
- archival evidence changes over time
- multiple authorities point to different procedural standards

## Operational Recommendations

### Dependency and environment strategy

- keep `ipfs_datasets_py` optional at runtime
- provide one documented bootstrap command for full integration mode
- make capability status visible in CLI and server startup logs
- support local-only fallback mode for development and CI

### Async and job orchestration

Long-running tasks should move out of synchronous mediator calls:

- web fetching
- archive capture
- PDF parsing and OCR
- graph ingestion
- theorem validation

Use durable background tasks and status tracking rather than blocking interactive flows.

### Observability

Track:

- artifacts fetched per case
- parse success rate
- graph nodes and edges created
- authorities linked per claim element
- unsupported elements remaining
- contradiction count
- average draft support coverage

## Prioritized Backlog

### Highest priority

1. Create the adapter layer and capability registry.
2. Eliminate repeated direct imports and path mutation.
3. Normalize web evidence and legal authority records.
4. Add provenance and claim-element coverage tracking.

### Second priority

1. Connect GraphRAG outputs into complaint-phase graphs.
2. Add hybrid retrieval over artifacts, authorities, and graph nodes.
3. Add authority-to-element linking and jurisdiction-aware ranking.

### Third priority

1. Add theorem-proving and contradiction checks.
2. Add asynchronous ingestion and validation jobs.
3. Add case dashboards and operator review tools.

## Risks and Mitigations

### Risk: API drift in `ipfs_datasets_py`

Mitigation:

- isolate imports behind adapters
- pin known-good versions or commits
- use compatibility tests for all imported modules

### Risk: submodule often missing in developer or CI environments

Mitigation:

- capability-based startup
- fallback local implementations
- tests that explicitly cover missing-submodule mode

### Risk: graph and logic layers become too complex to debug

Mitigation:

- store intermediate artifacts
- record provenance and transformation lineage
- expose explanation objects, not only scores

### Risk: complaint drafting over-relies on inferred facts

Mitigation:

- label inference vs direct evidence
- require source traceability for final draft assertions
- fail closed on unsupported legal elements

## Recommended First Sprint

If this work starts immediately, the first sprint should deliver:

1. `integrations/ipfs_datasets` package skeleton
2. centralized capability detection and startup logging
3. refactors of `mediator/evidence_hooks.py`, `mediator/web_evidence_hooks.py`, and `mediator/legal_authority_hooks.py` to use adapters
4. shared normalized dataclasses for artifacts and authorities
5. DuckDB schema additions for provenance and claim-element coverage
6. tests for submodule-present and submodule-absent modes

That sprint does not need theorem proving yet. It establishes the platform required for everything after it.

## Desired End State

At the end of this roadmap, complaint-generator should be able to:

- discover legal and factual material from multiple external sources
- archive and store it reproducibly
- parse and index it into a unified graph
- connect facts to legal elements and authorities
- reason about what is proven, unproven, or contradictory
- generate complaints whose assertions are traceable to evidence and law

That is the correct integration target for `ipfs_datasets_py`: not a loose dependency, but the research, storage, graph, and logic substrate beneath a verifiable complaint-generation system.