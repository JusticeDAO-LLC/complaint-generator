# IPFS Datasets Py Execution Backlog

Date: 2026-03-10
Status: Active planning backlog
Companion docs:

- `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md`
- `docs/IPFS_DATASETS_PY_CAPABILITY_MATRIX.md`

## Purpose

Translate the strategic integration plan into implementation-sized work packages that can be executed without re-planning the architecture each time.

This backlog is intentionally organized by deliverable, dependency, and acceptance criteria rather than by abstract themes.

## Execution Principles

1. Keep `complaint_phases/` as the canonical complaint-case model.
2. Keep `ipfs_datasets_py` optional at runtime.
3. Route production imports through `integrations/ipfs_datasets/`.
4. Prefer provenance-preserving data flow over convenience-only shortcuts.
5. Ship integration in thin vertical slices that improve organization and validation immediately.

## Phase 0: Adapter Completion

Goal: complete the adapter boundary so future work is isolated from submodule drift.

### Work Package 0.1: Capability expansion

Priority: P0
Target files:

- `integrations/ipfs_datasets/capabilities.py`
- `integrations/ipfs_datasets/loader.py`

Tasks:

- add capability keys for `documents`, `knowledge_graphs`, `graphrag`, `logic_tools`, `vector_store`, and `mcp_gateway`
- standardize degraded-reason reporting
- add helper for human-readable capability summary

Acceptance criteria:

- mediator startup can report all relevant capability groups in one stable structure
- missing extras produce actionable degraded reasons

Dependencies:

- `ipfs_datasets_py.processors`
- `ipfs_datasets_py.knowledge_graphs`
- `ipfs_datasets_py.optimizers.graphrag`
- `ipfs_datasets_py.logic`
- `ipfs_datasets_py.vector_stores`
- optional `ipfs_datasets_py.mcp_server`

### Work Package 0.2: Adapter skeletons

Priority: P0
Target files:

- `integrations/ipfs_datasets/documents.py`
- `integrations/ipfs_datasets/graphs.py`
- `integrations/ipfs_datasets/graphrag.py`
- `integrations/ipfs_datasets/logic.py`
- `integrations/ipfs_datasets/vector_store.py`
- `integrations/ipfs_datasets/mcp_gateway.py`

Tasks:

- create import-safe adapters with optional import loading
- define normalized return shapes
- add sync wrappers around async-only sources where needed
- add stable `__all__` exports

Acceptance criteria:

- all adapters import cleanly in degraded mode
- adapters expose minimal callable contracts even when backend is unavailable

### Work Package 0.3: Production import cleanup

Priority: P0
Target files:

- `complaint_analysis/indexer.py`
- any production module still importing `ipfs_datasets_py` directly

Tasks:

- replace direct production imports with adapter imports
- remove local `sys.path` manipulation from production code
- keep test and benchmark exceptions explicit

Acceptance criteria:

- no production module depends on ad hoc submodule path insertion

## Phase 1: Unified Acquisition and Provenance

Goal: every evidence and authority record lands in a shared, provenance-rich model.

### Work Package 1.1: Type expansion

Priority: P0
Target files:

- `integrations/ipfs_datasets/types.py`

Tasks:

- add `CaseFact`
- add `CaseClaimElement`
- add `CaseSupportEdge`
- add `FormalPredicate`
- add `ValidationRun`
- add canonical IDs and version fields where missing

Acceptance criteria:

- artifact, authority, fact, support, and predicate records share compatible provenance fields

### Work Package 1.2: Evidence normalization

Priority: P0
Target files:

- `mediator/evidence_hooks.py`
- `integrations/ipfs_datasets/provenance.py`
- `integrations/ipfs_datasets/storage.py`

Tasks:

- add explicit `artifact_id`
- persist content hash and acquisition metadata consistently
- define transform lineage placeholders for parse and extraction stages
- add exhibit-bundle manifest planning hooks

Acceptance criteria:

- uploaded evidence is reproducible by CID or stable content hash
- evidence metadata is shaped consistently for graph ingestion

### Work Package 1.3: Web evidence normalization

Priority: P0
Target files:

- `mediator/web_evidence_hooks.py`
- `integrations/ipfs_datasets/search.py`

Tasks:

- normalize search results into artifact-shaped records
- add fetch-and-archive pipeline boundary
- add domain trust and duplicate-clustering hooks
- preserve temporal discovery metadata

Acceptance criteria:

- search results can flow into storage, parsing, and graph enrichment without custom reshaping

### Work Package 1.4: Legal authority normalization

Priority: P0
Target files:

- `mediator/legal_authority_hooks.py`
- `integrations/ipfs_datasets/legal.py`

Tasks:

- add canonical `authority_id`
- unify citation normalization and source metadata
- persist jurisdiction and claim-element links consistently
- define authority conflict and precedence scoring hooks

Acceptance criteria:

- authority records can be joined directly to claim elements and legal graph nodes

## Phase 2: Document and Corpus Processing

Goal: convert exhibits and fetched pages into structured text, chunks, and extraction candidates.

### Work Package 2.1: Document adapter

Priority: P1
Target files:

- `integrations/ipfs_datasets/documents.py`

Tasks:

- wrap file type detection
- wrap PDF and OCR extraction
- expose chunking and metadata extraction
- return normalized parse outputs with provenance hooks

Acceptance criteria:

- a single adapter call can convert raw bytes or file paths into structured parse output

Dependencies:

- `ipfs_datasets_py.processors`
- likely extras: `pdf`, `file_conversion`, possibly `accelerate`

### Work Package 2.2: Evidence parse pipeline

Priority: P1
Target files:

- `mediator/evidence_hooks.py`

Tasks:

- trigger document parsing after upload for eligible types
- store chunk metadata and parse lineage
- extract timeline, citation, and entity candidates

Acceptance criteria:

- uploaded documents produce reusable parsed content for later search and graph enrichment

### Work Package 2.3: Web page parse pipeline

Priority: P1
Target files:

- `mediator/web_evidence_hooks.py`

Tasks:

- parse fetched pages into chunked text
- preserve archive snapshot metadata alongside parsed content
- connect parsed pages to related artifacts and domains

Acceptance criteria:

- archived or fetched web pages are first-class parseable evidence records

## Phase 3: Graph Enrichment and Organization

Goal: use graph extraction and graph storage to organize case material, not just collect it.

### Work Package 3.1: Graph adapter

Priority: P1
Target files:

- `integrations/ipfs_datasets/graphs.py`

Tasks:

- wrap extraction modules under `ipfs_datasets_py.knowledge_graphs`
- define normalized graph ingestion outputs
- add persistence and query entrypoints
- add entity resolution and lineage hooks

Acceptance criteria:

- complaint-generator can enrich local complaint graphs using adapter outputs without direct dependency on submodule internals

### Work Package 3.2: GraphRAG adapter

Priority: P1
Target files:

- `integrations/ipfs_datasets/graphrag.py`

Tasks:

- wrap ontology generation
- wrap ontology validation
- wrap refinement cycle entrypoints
- define coverage-scoring outputs usable by complaint phases

Acceptance criteria:

- graph enrichment can generate coverage and quality signals that are consumable by denoiser and legal matching workflows

### Work Package 3.3: Knowledge graph enrichment

Priority: P1
Target files:

- `complaint_phases/knowledge_graph.py`
- `complaint_phases/dependency_graph.py`

Tasks:

- ingest extracted entities and relations from parsed artifacts
- add support edges from facts to artifacts
- add missing-premise nodes where graph evidence is insufficient

Acceptance criteria:

- support analysis can enumerate which artifacts and facts back each claim element

### Work Package 3.4: Legal graph enrichment

Priority: P1
Target files:

- `complaint_phases/legal_graph.py`
- `mediator/legal_authority_hooks.py`

Tasks:

- attach authority IDs to legal elements
- add relation types for controlling, persuasive, conflicting, and procedural support
- expose queries by claim type and jurisdiction

Acceptance criteria:

- legal graph nodes are backed by normalized authority records rather than free-form search result blobs

### Work Package 3.5: Coverage matrix

Priority: P1
Target files:

- new persistence/schema layer locations to be chosen during implementation
- `mediator/mediator.py`

Tasks:

- persist claim-element coverage rows
- track supporting facts, artifacts, and authorities
- track unresolved gaps and contradictions

Acceptance criteria:

- mediator can return a claim-element coverage summary for drafting and review

## Phase 4: Logic and Formal Validation

Goal: make theorem-style sufficiency and contradiction checks part of case preparation.

### Work Package 4.1: Logic adapter

Priority: P1
Target files:

- `integrations/ipfs_datasets/logic.py`

Tasks:

- wrap FOL conversion
- wrap deontic conversion
- wrap proof and contradiction entrypoints
- normalize proof outputs into complaint-generator-friendly records

Acceptance criteria:

- complaint-generator can call logic validation through a stable adapter contract

Dependencies:

- `ipfs_datasets_py.logic`
- optional external provers and extras depending on deployment mode

### Work Package 4.2: Predicate templates

Priority: P1
Target files:

- `complaint_analysis/`
- `complaint_phases/legal_graph.py`
- `complaint_phases/neurosymbolic_matcher.py`

Tasks:

- define claim-type predicate templates
- define fact-to-predicate grounding rules
- define authority-to-obligation or prohibition mapping rules

Acceptance criteria:

- at least one complaint type can be translated into structured legal predicates end to end

### Work Package 4.3: Formal validation loop

Priority: P1
Target files:

- `complaint_phases/neurosymbolic_matcher.py`
- `mediator/mediator.py`

Tasks:

- run validation against claim elements
- surface unprovable and contradictory elements
- feed validation gaps into denoising questions

Acceptance criteria:

- mediator can expose a formal validation report before final draft generation

## Phase 5: Retrieval, Review, and Productization

Goal: make the integrated system operable and measurable.

### Work Package 5.1: Hybrid retrieval

Priority: P2
Target files:

- `complaint_analysis/indexer.py`
- `integrations/ipfs_datasets/vector_store.py`
- graph query entrypoints

Tasks:

- combine keyword, vector, graph, and authority ranking
- replace document-local indexing assumptions with case-aware retrieval

Acceptance criteria:

- users and internal services can retrieve support material by claim element, fact cluster, or authority need

### Work Package 5.2: Operator reporting

Priority: P2
Target files:

- `mediator/mediator.py`
- future UI or docs surfaces

Tasks:

- expose support coverage summary
- expose contradiction report
- expose provenance summary and bundle manifests

Acceptance criteria:

- the system can produce a reviewable packet without direct DuckDB inspection

### Work Package 5.3: Background jobs

Priority: P2
Target files:

- orchestration layer to be chosen

Tasks:

- move fetch, parse, graph, and validation jobs out of blocking flows
- persist job status and partial outputs

Acceptance criteria:

- long-running enrichment work no longer blocks interactive questioning or draft review

## Dependency Map

### Minimum viable extras by workstream

| Workstream | Likely `ipfs_datasets_py` module | Likely extras |
|---|---|---|
| Storage | `ipfs_backend_router` | none or local IPFS tooling |
| Search + archives | `web_archiving`, Common Crawl integration | `web_archive`, possibly `api` |
| Legal scrapers | `processors.legal_scrapers` | `legal` |
| Document parsing | `processors` | `pdf`, `file_conversion`, optional `accelerate` |
| Knowledge graphs | `knowledge_graphs` | `knowledge_graphs`, `ipld`, `provenance` |
| GraphRAG | `optimizers.graphrag` | existing optimizer deps |
| Logic | `logic` | `logic`, optional prover-specific tooling |
| Vector retrieval | `vector_stores`, embeddings stack | `vectors`, optional `ml` |
| MCP gateway | `mcp_server` | depends on selected tool families |

### External integration pressure points

Watch carefully:

- async-only scraper APIs
- modules that depend on optional extras indirectly
- deprecated root graph imports versus current subpackages
- MCP tool sprawl creeping into mediator orchestration

## Suggested Sprint Breakdown

### Sprint 1

- Work Packages 0.1, 0.2, 0.3
- Work Package 1.1

Definition of done:

- adapter boundary complete enough to support future work without direct production imports

### Sprint 2

- Work Packages 1.2, 1.3, 1.4
- start 2.1

Definition of done:

- evidence, web, and authority flows share a common normalized persistence model

### Sprint 3

- Work Packages 2.1, 2.2, 2.3
- start 3.1 and 3.2

Definition of done:

- documents and pages become parseable assets feeding graph enrichment

### Sprint 4

- Work Packages 3.1 through 3.5

Definition of done:

- claim-element coverage becomes graph-backed rather than heuristic-only

### Sprint 5

- Work Packages 4.1, 4.2, 4.3

Definition of done:

- at least one complaint type has end-to-end formal validation

### Sprint 6

- Work Packages 5.1, 5.2, 5.3

Definition of done:

- operators can review support coverage, provenance, and contradictions through stable interfaces

## Immediate Next Actions

If implementation starts now, the highest-value sequence is:

1. Add the missing adapter skeletons.
2. Expand capability detection to cover them.
3. Remove the remaining production `sys.path` import pattern from `complaint_analysis/indexer.py`.
4. Expand `types.py` to include facts, support edges, predicates, and validation outputs.
5. Add schema planning for the claim-element coverage matrix.

That sequence creates the foundation for graph, theorem-proving, archive, and graph-database work without requiring a second architecture pass.