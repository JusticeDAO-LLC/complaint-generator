# IPFS Datasets Py Execution Backlog

Date: 2026-03-12
Status: Active execution backlog

Companion docs:

- `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md`
- `docs/IPFS_DATASETS_PY_NEXT_BATCH_PLAN.md`
- `docs/IPFS_DATASETS_PY_CAPABILITY_MATRIX.md`
- `docs/PAYLOAD_CONTRACTS.md`
- `docs/AGENT_SUPERVISOR_TASK_BOARD.md`

## Purpose

Translate the strategic `ipfs_datasets_py` integration roadmap into execution-sized work packages tied to the current state of complaint-generator.

This backlog assumes the repo already has:

- a working adapter boundary under `integrations/ipfs_datasets/`
- evidence, legal authority, and web evidence mediator flows
- persistent claim-support and follow-up state
- deduplication-aware storage and graph-projection contracts

The goal now is not to sketch a hypothetical architecture. The goal is to finish the high-value workflow integrations that improve legal information organization, graph-backed support analysis, archival reliability, and formal validation.

This now explicitly includes claim-aware legal corpus search across statutes, administrative rules, agency guidance, and case law, plus first-pass authority-treatment and shepherdization workflows so complaint drafting is not built on unchecked authority support.

## Execution Principles

1. Keep `complaint_phases/` as the canonical workflow graph model.
2. Keep `ipfs_datasets_py` optional at runtime and fully supported in degraded mode.
3. Route all production integrations through `integrations/ipfs_datasets/`.
4. Treat provenance, deduplication, and claim-element support as first-class data.
5. Require graph, GraphRAG, and logic features to produce mediator-consumable outputs.
6. Prefer thin vertical slices that improve support coverage, reviewability, or contradiction detection immediately.

## Current Baseline

## Completed or substantially in place

These areas are already present and should be treated as foundation, not future design work:

- adapter boundary for storage, search, legal, provenance, graphs, GraphRAG, and logic capability probing
- mediator capability logging at startup
- evidence, legal authority, and web evidence ingestion using adapter-backed flows
- persistent claim requirements and claim-support links
- evidence and authority deduplication with created or reused metadata
- parsed evidence summaries, chunks, graph metadata, and extracted fact persistence
- parsed legal-authority summaries, authority chunk persistence, and authority fact persistence when text is available
- graph projection metadata propagated through mediator payloads
- graph projection from evidence into complaint-phase knowledge graph state
- unified claim-support fact retrieval across evidence and authorities
- graph-support fallback queries with duplicate collapse and semantic-cluster summaries
- persisted scraper runs, tactic telemetry, and coverage ledgers
- queue-backed scraper job persistence and worker execution
- follow-up planning and cooldown-aware execution history
- review payloads and compact coverage or follow-up summaries for operator-facing inspection
- centralized payload contract documentation

## Still shallow or incomplete

These are the main execution and validation targets:

- shared parse, graph, GraphRAG, and logic contracts are implemented enough to validate as baseline, but supervisor runs should still execute the focused validation commands before closing dependent work
- the shared fact registry covers evidence, authorities, and archived web evidence; remaining work is to keep the same first-class storage shape across future graph artifacts, predicates, and higher-level consumers
- graph snapshot and support-query payloads exist, but external supervisors should treat graph-store-backed execution as capability-dependent and preserve adapter fallback behavior
- review payloads and the dedicated dashboard expose coverage, provenance, timeline, and support-path data; remaining work is validation, product hardening, and keeping contract examples synchronized

## Status Legend

- `Complete`: implemented enough to be treated as baseline
- `In Progress`: partially implemented and actively extendable
- `Planned`: designed but not yet implemented
- `Deferred`: useful but lower priority than current organization and validation work

## Workstream Overview

| ID | Workstream | Status | Priority | Outcome |
|---|---|---|---|---|
| W1 | Adapter hardening | In Progress | P0 | Stable feature detection and runtime-mode handling |
| W2 | Unified acquisition and provenance | In Progress | P0 | Evidence, authorities, and archived web material share one case model |
| W3 | Document and chunk services | In Progress | P0 | Source material becomes reusable parsed corpus data across PDF, DOCX, RTF, HTML, email, and office documents |
| W4 | Graph persistence and support queries | In Progress | P0 | Cross-artifact support can be queried and explained |
| W5 | GraphRAG support analysis | In Progress | P1 | Ontology refinement improves support ranking and gap detection |
| W6 | Formal logic and theorem proving | In Progress | P1 | Claim-element sufficiency and contradiction validation |
| W7 | Retrieval and follow-up optimization | In Progress | P1 | Retrieval is driven by missing support and provenance-aware ranking |
| W8 | Review and operator tooling | In Progress | P1 | Existing coverage, follow-up, and dashboard payloads graduate into richer inspectable review surfaces |
| W9 | Legal corpus search and authority treatment | Planned | P0 | Claim elements can be researched for support, opposition, and authority reliability |
| W10 | Drafting and filing readiness | Planned | P0 | Formal complaint drafts become support-aware, citation-aware, and validation-aware |

<!-- refactor-supervisor:p0-cross-links:start -->
## P0 Refactor Supervisor Cross-Links

This is the canonical mapping from the P0 IPFS roadmap to the generated refactor taskboard. The supervisor copies this marked section into `docs/REFACTOR_SUPERVISOR_TASKBOARD.md` on every seed run. References such as `G3.S1` identify the goal definitions rendered under **Goals** on that board.

| IPFS workstream | Refactor goal(s) | Package coverage | Merge and scope rule |
|---|---|---|---|
| W1 Adapter hardening | [G1.S2](REFACTOR_SUPERVISOR_TASKBOARD.md#g1s2-remove-ad-hoc-import-path-behavior-from-production-surfaces), [G3.S1](REFACTOR_SUPERVISOR_TASKBOARD.md#g3s1-normalize-ipfs-datasets-adapter-payloads) | W1.1 capability reporting maps to G3.S1; W1.2 production import cleanup maps to G1.S2. | Treat the matching supervisor tasks as the same implementation claims: carry both the W and G identifiers instead of queuing duplicates. W1 owns IPFS acceptance details; the goals own repository-boundary and adapter-contract acceptance. |
| W2 Unified acquisition and provenance | [G2.S1](REFACTOR_SUPERVISOR_TASKBOARD.md#g2s1-extract-mediator-service-seams), [G3.S1](REFACTOR_SUPERVISOR_TASKBOARD.md#g3s1-normalize-ipfs-datasets-adapter-payloads) | W2.1-W2.3 and W2.5 supply the shared types and payload contracts covered by G3.S1; mediator-hook changes in W2.2-W2.4 also use the G2.S1 extraction seam. | The functional data/provenance work remains in W2. G2.S1 only owns extracting mediator responsibilities and G3.S1 only owns normalized adapter contracts. W2.4's scraper acquisition queue is explicitly distinct from the refactor supervisor queue in G5.S1. |
| W3 Document and chunk services | [G2.S1](REFACTOR_SUPERVISOR_TASKBOARD.md#g2s1-extract-mediator-service-seams), [G3.S1](REFACTOR_SUPERVISOR_TASKBOARD.md#g3s1-normalize-ipfs-datasets-adapter-payloads) | W3.1-W3.3 are the roadmap detail for G3.S1's shared ingestion-contract task; hook extraction required by W3.2-W3.3 maps to G2.S1. | Merge W3 parse-contract work with the G3.S1 implementation claim. Use G2.S1 only when moving orchestration across module seams, not as a second parsing implementation. |
| W4 Graph persistence and support queries | [G2.S1](REFACTOR_SUPERVISOR_TASKBOARD.md#g2s1-extract-mediator-service-seams), [G3.S2](REFACTOR_SUPERVISOR_TASKBOARD.md#g3s2-clarify-graph-graphrag-and-logic-adapter-boundaries) | W4.1-W4.4 implement the graph persistence/query interfaces named by G3.S2; mediator query-orchestration extraction maps to G2.S1. | One graph contract/query slice carries W4 and G3.S2. G2.S1 is separately scoped to module decomposition and must not reimplement graph behavior. |
| W9 Legal corpus search and authority treatment | [G2.S1](REFACTOR_SUPERVISOR_TASKBOARD.md#g2s1-extract-mediator-service-seams), [G3.S1](REFACTOR_SUPERVISOR_TASKBOARD.md#g3s1-normalize-ipfs-datasets-adapter-payloads), [G3.S2](REFACTOR_SUPERVISOR_TASKBOARD.md#g3s2-clarify-graph-graphrag-and-logic-adapter-boundaries) | W9.1-W9.3 use normalized legal/type contracts under G3.S1; W9.4 uses graph boundaries under G3.S2; mediator extraction uses G2.S1 when needed. | W9 owns new legal-search, treatment, and rule-matching behavior. The refactor goals constrain adapter payloads and module boundaries only, so those refactor claims do not duplicate W9 features. |
| W10 Drafting and filing readiness | [G2.S2](REFACTOR_SUPERVISOR_TASKBOARD.md#g2s2-reduce-application-surface-coupling), [G4.S1](REFACTOR_SUPERVISOR_TASKBOARD.md#g4s1-create-focused-test-lanes-for-refactor-work), [G7.S1](REFACTOR_SUPERVISOR_TASKBOARD.md#g7s1-separate-review-api-contracts-from-display-assembly) | W10.1-W10.2 consume explicit review DTOs under G7.S1; W10.3 application separation maps to G2.S2; W10.4 focused validation maps to G4.S1. | W10 owns drafting/export capability. G7.S1 owns reusable review payload assembly, G2.S2 owns application decoupling, and G4.S1 owns test-lane structure; shared files do not make these duplicate feature tasks. |

Execution rules:

1. Every implementation claim for a mapped package records both IDs, for example `W3.1 / G3.S1`, in its title or task metadata.
2. When the table says to merge, there is one queued implementation claim with the union of acceptance criteria and validation commands, not parallel backlog and refactor copies.
3. When the table explicitly separates scopes, claims may remain separate only if their titles and acceptance criteria name the functional, contract, decomposition, UI, or validation boundary shown above.
4. The P1 workstreams remain roadmap-owned until a supervisor goal explicitly adopts them; this does not affect P0 coverage.
<!-- refactor-supervisor:p0-cross-links:end -->

## W1: Adapter Hardening

Status: In Progress - queue-state inspection and queue-first CLI execution are implemented.
Priority: P0

### Why this matters

The adapter boundary exists, but parts of it still act as capability probes rather than full production-grade contracts.

### Work Package W1.1: Capability reporting cleanup

Status: Complete
Target files:

- `integrations/ipfs_datasets/capabilities.py`
- `integrations/ipfs_datasets/loader.py`
- `mediator/mediator.py`

Tasks:

- ensure `documents`, `knowledge_graphs`, `graphrag`, and `logic_tools` have stable capability entries
- standardize degraded-reason payloads across adapters
- expose a human-readable capability summary helper for diagnostics and docs

Acceptance criteria:

- mediator startup reports the same capability groups across full, partial, and degraded environments
- missing extras produce actionable reason strings rather than generic import failures

Validation:

- adapter unit tests for capability status payloads
- mediator startup smoke checks in degraded mode

### Work Package W1.2: Production import drift cleanup

Status: Complete
Target files:

- `complaint_analysis/indexer.py`
- any remaining production modules importing `ipfs_datasets_py` directly

Tasks:

- replace direct production imports with adapter imports
- remove any production `sys.path` mutation patterns
- document explicit exceptions for tests or benchmark-only files

Acceptance criteria:

- no production code depends on ad hoc submodule-path manipulation

## W2: Unified Acquisition and Provenance

Status: Complete
Priority: P0

### Why this matters

The complaint generator already stores evidence and authorities well enough to deduplicate them. The next step is to treat them as one provenance-rich case model.

### Work Package W2.1: Shared case types expansion

Status: In Progress - queue claim/complete lifecycle hardened
Target files:

- `integrations/ipfs_datasets/types.py`

Tasks:

- formalize `CaseFact`, `CaseClaimElement`, `CaseSupportEdge`, `FormalPredicate`, and `ValidationRun`
- standardize canonical IDs and version fields
- keep evidence and authority records compatible with future graph and logic layers

Acceptance criteria:

- artifacts, authorities, facts, support edges, and predicates share compatible provenance fields

### Work Package W2.2: Provenance normalization pass

Status: Complete
Target files:

- `integrations/ipfs_datasets/provenance.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`

Tasks:

- align evidence, web evidence, and authority provenance fields
- standardize acquisition method, source system, content hash, and archive metadata
- add transform-lineage placeholders for parse, graph extraction, and logic translation stages

Acceptance criteria:

- every stored artifact and authority can be traced to source, acquisition method, and normalization stage

### Work Package W2.3: Shared fact registry

Status: In Progress
Target files:

- schema layer to be selected during implementation
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`
- `mediator/claim_support_hooks.py`

Tasks:

- deepen the existing extracted-fact persistence so archived pages, authorities, and uploaded evidence share one durable corpus contract
- link facts to claim elements, artifacts, authorities, and future graph or logic outputs
- store fact provenance at the chunk or passage level when available and preserve lineage into review payloads

Current state:

- evidence, authority, and archived web evidence facts already flow through one persisted fact substrate in current mediator-backed paths
- archived web evidence now has focused assertions proving that the shared evidence fact API preserves explicit artifact, corpus, and parse-lineage fields for archived captures
- evidence-backed and legal-authority fact rows now persist the core corpus contract as first-class durable columns (`source_family`, `source_record_id`, `source_ref`, `record_scope`, `artifact_family`, `corpus_family`, `content_origin`, parse-quality fields, and passage anchors) with compatibility fallback for older JSON-only rows
- claim-support fact normalization now prefers those durable top-level fact columns and exposes `get_claim_fact_registry_summary(...)` plus per-gap `support_fact_registry_summary` counts for graph and predicate consumers
- persisted and current support-path payloads now carry `support_fact_registry_summary` in path metadata and top-level path details, preserving corpus/source/passages counts through proof-path storage and review retrieval
- typed graph snapshots now persist and return `fact_registry_summary` from graph payloads, metadata, or support facts so graph artifact references retain corpus coverage context
- adapter-level graph snapshot queries now promote `fact_registry_summary` to the top-level queried snapshot and aggregate query result from explicit snapshot metadata, graph payload metadata, or `support_facts`, avoiding nested metadata inspection for graph artifact consumers
- graph-support query summaries now mirror the durable fact-registry count maps (`source_family_counts`, corpus/artifact/content-origin counts, parse-quality counts, source-ref counts, and passage-anchor counts) alongside ranked support matches
- predicate mapping and `prove_claim_elements(...)` now preserve element-level `support_facts`, predicate-level `fact_registry_summary`, aggregate proof-level `fact_registry_summary`, and temporal-reasoning payload registry context
- theorem exports now pass through `fact_registry_summary` from top-level proof results, nested result payloads, or temporal-reasoning payloads so Lean/Coq artifacts retain corpus coverage metadata
- draft-logic proof reports can now carry `fact_registry_summary` from support facts or a precomputed registry summary, and rendered proof reports expose support-fact and passage-anchor counts
- draft quality scoring now uses `fact_registry_summary` as corpus-grounding evidence when coverage percentages are absent and emits targeted suggestions for missing source-backed facts or missing passage anchors
- formal complaint claim payloads now preserve durable registry fields on `supporting_fact_entries` and embed claim-level `fact_registry_summary` under `support_summary` for drafting/proof-review consumers
- remaining backlog work is to apply the same first-class storage shape to future graph artifacts, predicates, and other higher-level consumers

Acceptance criteria:

- claim-element support can enumerate both source artifacts and the specific facts derived from them across all acquisition paths

### Work Package W2.4: Queue-backed acquisition orchestration

Status: In Progress
Target files:

- `mediator/evidence_hooks.py`
- `mediator/mediator.py`
- `scripts/agentic_scraper_cli.py`

Tasks:

- persist scraper queue jobs with claim metadata, timing metadata, and worker ownership
- require workers to claim pending work instead of launching scraper runs unconditionally
- keep queue inspection and one-job execution available through mediator and CLI surfaces
- guard job completion so only claimed/running jobs can be completed or failed, and optional worker identity must match the worker that claimed the row
- aggregate queue-state health counts across all matching jobs while keeping the returned job list bounded for operator previews

Acceptance criteria:

- scraper workers idle or exit cleanly when there is no queued work
- queued work can be inspected, claimed, executed, and marked completed or failed
- queue semantics remain optional and do not break direct bounded-run entrypoints

### Work Package W2.5: Authority treatment, search-program, and citation-history records

Status: In Progress
Target files:

- `integrations/ipfs_datasets/types.py`
- `mediator/legal_authority_hooks.py`
- `mediator/claim_support_hooks.py`

Tasks:

- add durable typed records for authority treatment, citation history, and authority-to-authority relationships
- persist claim-element-aware legal search programs with each stored authority so later review can explain why the authority was collected
- standardize fields such as `treatment_type`, `treatment_source`, `treatment_confidence`, `treatment_date`, and `treatment_explanation`
- keep authority records compatible with later graph and logic workflows that need to distinguish supportive from adverse or unreliable authority

Implemented baseline:

- authority treatment and rule-candidate records already persist as typed child rows
- authority search programs now persist as durable child rows and surface through `search_programs` plus `search_program_summary` on stored authority records
- treatment rows now surface graph-compatible relationship aliases plus `citation_history_summary` for stored authority records and claim-support authority summaries
- legal graph projection now consumes `authority_treatment_edges` directly, preserving stored source/target treatment direction and resolving both numeric IDs and `authority:{id}` aliases
- duplicate/reused authority rows can now receive later rule-candidate extraction outputs without duplicating stable rule IDs

Acceptance criteria:

- stored authorities can carry treatment records without breaking existing authority or support payloads
- stored authorities can carry search-program records without relying only on metadata snapshots
- treatment data is available to support scoring and review payload generation
- authority-to-authority treatment rows can be consumed by legal graph projection without per-consumer field translation

## W3: Document and Chunk Services

Status: In Progress
Priority: P0

### Why this matters

Source material cannot support graph, retrieval, or theorem-proving workflows if it remains opaque bytes or page blobs.

### Work Package W3.1: Document adapter

Status: Complete
Target files:

- `integrations/ipfs_datasets/documents.py`

Tasks:

- wrap file type detection
- wrap PDF and OCR extraction when available
- expose chunking and metadata extraction
- normalize PDF, DOCX, RTF, HTML, email, and office-document parsing behind one adapter contract
- return normalized parse outputs with provenance hooks

Implemented baseline:

- `parse_document_bytes(...)`, `parse_document_file(...)`, and `parse_document_text(...)` now normalize text, HTML, email, RTF, DOCX, XLSX, PPTX, OpenDocument, CSV, legacy DOC, and PDF inputs behind the same summary/chunk/lineage contract
- OOXML and OpenDocument fallbacks extract text from packaged XML when the upstream document stack is unavailable
- legacy DOC and binary PDF inputs stay inside the shared contract with low-quality or empty extraction flags instead of requiring per-format caller branches
- canonical parse entrypoints and `summarize_document_parse(...)` are exported from the root adapter package, and parse summaries now preserve extraction method, quality tier/score, page count, and source fields for both full parse results and metadata-only fallback records

Acceptance criteria:

- one adapter call can convert raw bytes, file paths, or fetched page content into a normalized parse result
- mediator hooks do not need per-format parsing branches outside the adapter layer

Validation:

- compile checks and adapter unit tests in degraded mode
- fixture-driven parse tests for at least text, HTML, and PDF inputs where dependencies are available

### Work Package W3.2: Evidence parse pipeline unification

Status: In Progress
Target files:

- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`

Tasks:

- route parsing through `documents.py`
- normalize chunk metadata and parse lineage
- expose reusable parse summaries rather than hook-local output shapes
- ensure archived captures, live fetches, and uploaded exhibits can all be compared through the same chunk and provenance model

Implemented baseline:

- uploaded evidence and discovered web evidence already persist parse summaries, chunk rows, graph metadata, and extracted facts
- web evidence now lands in the same normalized storage path as other evidence rather than remaining only a search payload
- evidence fact passage anchors now include bounded `source_passage.text` snippets alongside chunk IDs and offsets so review surfaces can show passage text without reopening the chunk table

Acceptance criteria:

- uploaded evidence and fetched web pages produce the same parse contract family

### Work Package W3.3: Legal text parse pipeline

Status: In Progress
Target files:

- `mediator/legal_authority_hooks.py`
- `integrations/ipfs_datasets/legal.py`
- `integrations/ipfs_datasets/documents.py`

Tasks:

- parse authority text into chunked records when full text is available
- extract citation and requirement candidates from parsed authority text
- connect parsed authority text to the legal graph and future predicate translation
- preserve authority-document lineage so review surfaces can trace support back to passage-level source text

Implemented baseline:

- stored legal authority text now flows through `documents.py` for parse summaries and chunk persistence
- authority fact extraction now prefers normalized parsed text over raw content when available
- authority graph entities and relationships are now persisted locally alongside authority facts
- authority fact passage anchors now include bounded `source_passage.text` snippets alongside chunk IDs and offsets for passage-level review/proof traceability
- first-pass authority rule candidates now carry exact parsed passage anchors (`source_passage.text`, chunk id/index, offsets) plus shared parse lineage metadata so future predicate translation and review drilldowns can trace each candidate rule back to source text

Acceptance criteria:

- legal authorities are parseable corpus assets rather than citation-only records when source text exists

## W4: Graph Persistence and Support Queries

Status: In Progress
Priority: P0

### Why this matters

The system already builds useful in-memory graphs. The next step is to persist and query support structure across many artifacts without losing provenance.

### Work Package W4.1: Graph adapter deepening

Status: In Progress
Target files:

- `integrations/ipfs_datasets/graphs.py`

Tasks:

- replace stub persistence with a real graph-snapshot contract
- add support-query entrypoints
- add entity-resolution and lineage hooks
- define graph IDs and graph version semantics

Implemented baseline:

- evidence ingestion already performs graph extraction and stores entity and relationship metadata in DuckDB
- complaint-phase graph projection already exists for evidence-backed support insertion
- legal-authority ingestion now also stores graph entity and relationship metadata locally for later support tracing
- adapter-visible graph payload, graph snapshot, and graph-support result contracts are now typed under `integrations/ipfs_datasets/types.py` and emitted by `integrations/ipfs_datasets/graphs.py`
- graph snapshot payloads now distinguish created versus reused graph content in evidence storage, authority storage, and mediator graph-projection results
- adapter-level fallback snapshots now preserve top-level `fact_registry_summary` derived from explicit metadata, graph payload metadata, or `support_facts`

Acceptance criteria:

- complaint-generator can persist graph snapshots and query support relationships through the adapter without importing submodule internals directly

### Work Package W4.2: Graph projection persistence

Status: In Progress
Target files:

- `mediator/mediator.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`

Tasks:

- persist graph projections for evidence and authorities when graph backends are available
- record whether a graph write created new graph content or reused existing graph structure
- retain lineage from artifact or authority record to graph snapshot

Implemented baseline:

- graph projection metadata is already returned through mediator flows
- evidence graph metadata is already persisted even when a backing graph store is unavailable
- claim-support enrichment now carries graph lineage packets from stored evidence and authority `graph_metadata`, so review-oriented support links and derived fact rows can trace back to adapter snapshot semantics and source records
- `persist_graph_snapshot(...)` now stores graph projections in a queryable adapter-level fallback registry with `adapter_memory` persistence metadata, and `query_graph_snapshot(...)` can retrieve snapshots by `graph_id` or `source_id` even when no upstream graph store is installed
- typed claim-support graph snapshots now also register with the adapter-level snapshot registry, so `persist_typed_graph_snapshot(...)` results can be retrieved through `query_graph_snapshot(...)` while retaining claim type, source kind, and fact-registry metadata

Acceptance criteria:

- every projected support edge can be traced to both the storage record and the graph snapshot that contains it

### Work Package W4.3: Claim-element support queries

Status: In Progress
Target files:

- `mediator/claim_support_hooks.py`
- `mediator/mediator.py`
- `integrations/ipfs_datasets/graphs.py`

Tasks:

- add query APIs for artifacts supporting a claim element
- add query APIs for authorities supporting or contradicting a claim element
- add graph-backed unresolved-gap queries

Implemented baseline:

- claim-element support views already enumerate artifacts, authorities, and fact rows
- enriched support links and derived fact rows now expose `graph_trace` packets for evidence and authority sources
- review payloads now aggregate compact `graph_trace_summary` fields in `claim_coverage_summary` for dashboard and audit surfaces
- claim coverage matrix elements now expose `support_path_summary` with persisted paths plus derived current-trace paths carrying fact IDs, support refs, graph IDs, and trace summaries
- graph snapshot refs now carry compact adapter registry lookup payloads (`graph_snapshot_query` plus `graph_snapshot`) so review/coverage consumers can drill from persisted claim-support snapshot rows into queryable adapter snapshots and fact-registry coverage without issuing a second lookup
- persisted support paths now store and return compact drilldown metadata matching current-trace paths: support refs, support kinds, source families, graph IDs, graph trace counts, and support fact-registry summaries
- rule-fact-targeted follow-up context now carries source authority passage anchors and parse lineage for the top extracted rule snippets that shape fact-gap queries
- mediator unresolved-gap queries now attach `graph_gap_context`, normalized `graph_gap_query`, and claim-level `graph_gap_query_summary` packets so review payloads and dashboards can distinguish graph-backed missing support from empty retrieval lanes without parsing raw GraphRAG results

Acceptance criteria:

- mediator can return graph-backed support traces for review and drafting readiness

### Work Package W4.4: Coverage matrix persistence

Status: In Progress
Target files:

- `claim_support_snapshot` persisted snapshot table
- `mediator/claim_support_hooks.py`
- `mediator/mediator.py`

Tasks:

- persist coverage rows with supporting facts, artifacts, authorities, contradictions, and latest validation state
- make coverage rows the central organization and reporting model

Implemented baseline:

- coverage matrices can now be persisted as `coverage_matrix` snapshots with support-state freshness tokens and retention pruning
- mediator wrappers expose coverage snapshot persistence and latest-snapshot retrieval for review and drafting consumers
- claim-support review payloads now expose coverage-matrix snapshot entries and lifecycle summaries alongside the live recomputed coverage matrix
- coverage-matrix snapshot metadata now carries compact status, support-kind, graph-snapshot-ref, support-path, current-trace-path, and support-quality summaries for operator inspection without loading the full matrix payload
- coverage-matrix snapshot metadata now also distinguishes current-trace versus persisted support paths, graph-linked path counts, support-ref totals, unique support refs, and path-kind mixes for drilldown health checks
- review payload `claim_coverage_matrix_snapshot_summary` now rolls those coverage snapshot path-health fields into a compact lifecycle summary, and the dashboard renders them as coverage snapshot chips
- automatic legal research now persists a fresh coverage-matrix snapshot alongside gap and contradiction diagnostic snapshots

Acceptance criteria:

- drafting and review flows can ask for one authoritative claim-element coverage matrix instead of stitching multiple tables manually

## W5: GraphRAG Support Analysis

Status: In Progress - baseline grounded-rule metadata, graph projection, and formal failure categories are implemented.
Priority: P1

### Why this matters

GraphRAG should improve how the system organizes and ranks support, not just act as a standalone ontology experiment.

### Work Package W5.1: Ontology generation workflow

Status: In Progress
Target files:

- `integrations/ipfs_datasets/graphrag.py`
- `mediator/claim_support_hooks.py`

Tasks:

- generate ontologies from complaint narratives and parsed evidence corpora
- validate generated ontologies before using them for support decisions
- add a normalized ontology-quality payload consumable by complaint phases

Implemented baseline:

- `build_validate_score_ontology(...)` now provides a single adapter-bound workflow that builds, locally falls back when GraphRAG extras are unavailable, validates, refines, scores, and gap-checks ontology output.
- Claim-support reasoning diagnostics now expose `ontology_workflow` and advisory `graphrag_quality` packets per element without changing existing proof-gap counts unless GraphRAG quality enforcement is explicitly enabled.
- Review payload `claim_coverage_summary` entries now aggregate those per-element GraphRAG packets into `ontology_quality_summary`, including availability, validation, score, grade, and gap counts for dashboard and complaint-phase consumers.
- Compact ontology quality packets now include workflow/degraded-mode provenance plus gap type, severity, and follow-up-action count maps; review summaries and dashboard chips aggregate those fields for W5.1 operator triage.

Acceptance criteria:

- at least one complaint workflow can generate and validate an ontology without bypassing the adapter boundary
- the workflow returns `ontology_quality` with validation, count, score, grade, and gap summary fields in degraded mode

### Work Package W5.2: Support-path scoring

Status: In Progress - baseline ranking factors and explanations are implemented for orchestrated records, adapter search results, and claim retrieval sessions.
Target files:

- `integrations/ipfs_datasets/graphrag.py`
- `mediator/claim_support_hooks.py`

Tasks:

- score support paths using ontology structure, graph connectivity, and source quality
- feed scored support paths into claim overview summaries
- distinguish strong support, weak support, duplicate support, and structurally missing support

Implemented baseline:

- `score_support_path_quality(...)` now scores individual support paths with source-quality, graph-connectivity, support-kind coverage, ontology-shape, ontology-alignment, duplicate, and structural-missing signals.
- `get_support_paths_for_element(...)` now attaches per-path `support_quality` and aggregate `quality_summary` payloads.
- Claim coverage matrices and claim overviews now expose `support_quality_summary`, so review consumers can see support quality in addition to support counts.

Acceptance criteria:

- claim overviews can surface support quality, not just support count

### Work Package W5.3: Denoiser and follow-up integration

Status: In Progress
Target files:

- `mediator/claim_support_hooks.py`
- `complaint_phases/denoiser.py`

Tasks:

- turn ontology and graph-quality gaps into follow-up tasks and denoising prompts
- prioritize follow-up work from structural gaps instead of generic missing evidence heuristics

Implemented baseline:

- Mediator question recommendations now inspect support-quality summaries for covered and partially covered elements, adding structural lanes for `graph_quality_gap`, `support_quality_gap`, `source_quality_gap`, and `duplicate_support`.
- Denoiser review prompts now turn GraphRAG support-path quality signals into targeted questions about graph connectivity, source clarity, duplicate support, and direct support-path strengthening.
- Mediator and denoiser recommendation payloads now expose `primary_quality_signal` plus `quality_follow_up_action` so downstream queues can route graph/source/duplicate/support-path follow-up without reinterpreting raw signal counts.
- Review question recommendations now turn advisory GraphRAG `graphrag_quality` gaps into an `ontology_quality_gap` lane with `ontology_quality`, `ontology_gap_types`, quality signal counts, and `improve_ontology_quality` routing metadata, even when GraphRAG quality enforcement is disabled.
- Follow-up plans now retain supported elements that still have advisory ontology-quality gaps, route them through `ontology_quality_gap_closure` / `ontology_quality_gap_targeted`, and expose ontology quality metadata plus summary counters so structural graph remediation is not lost behind generic support-gap retrieval.
- Follow-up execution history now persists and reloads ontology-quality metadata, generic quality signal/action fields, and ontology task counters, and the dashboard merges history quality routing into the follow-up quality signal card.
- Supported ontology-quality follow-up tasks now execute targeted evidence retrieval from their ontology query variants instead of being manual-review-only, while keeping `missing_support_kinds` accurate for count-supported elements.
- Follow-up plan, execution, and history rows now carry normalized `graph_gap_query` packets next to `graph_gap_context`, preserving claim-element identifiers, missing support kinds, graph-hit counts, recommended graph action, and empty-lane state for downstream queue routing.
- Follow-up plan, execution, and history summaries now aggregate those `graph_gap_query` packets into query counts, support-hit/empty counts, result totals, missing-support-kind mixes, and query action/priority maps for dashboard and queue consumers.

Acceptance criteria:

- follow-up tasks are measurably more specific than claim-type-only retrieval prompts

## W6: Formal Logic and Theorem Proving

Status: In Progress
Priority: P1

### Why this matters

The formal logic layer already influences review and follow-up planning through proof-aware diagnostics, contradiction-aware validation states, and reasoning-gap task generation. The remaining gap is to replace placeholder-heavy adapter behavior with grounded, persisted validation workflows.

### Work Package W6.1: Logic adapter implementation

Status: In Progress
Target files:

- `integrations/ipfs_datasets/logic.py`

Tasks:

- implement normalized wrappers for text-to-FOL, deontic translation, proof execution, and contradiction checks
- support graceful fallback when logic backends or prover bridges are unavailable
- normalize proof outputs into complaint-generator-friendly records

Acceptance criteria:

- complaint-generator can call proof and contradiction workflows through a stable adapter contract

### Work Package W6.2: Predicate templates by claim type

Status: In Progress - baseline archive-first capture and metadata propagation are implemented.
Target files:

- `complaint_analysis/`
- `complaint_phases/legal_graph.py`
- `complaint_phases/neurosymbolic_matcher.py`

Tasks:

- define predicate templates for high-value complaint types
- define fact-grounding rules
- define authority-to-rule mappings for obligations, permissions, and prohibitions

Acceptance criteria:

- at least one complaint type can be translated into structured legal predicates end to end

### Work Package W6.3: Formal validation loop

Status: In Progress
Target files:

- `complaint_phases/neurosymbolic_matcher.py`
- `mediator/mediator.py`
- `mediator/claim_support_hooks.py`

Tasks:

- validate grounded facts against claim-element predicates
- surface unsupported and contradictory elements
- persist validation artifacts and feed missing premises back into follow-up planning

Implemented baseline:

- claim-support validation already emits contradiction-aware and proof-aware statuses
- review and dashboard surfaces already expose proof-gap, reasoning, and contradiction summaries
- follow-up planning already consumes proof-decision traces, logic-unprovable outcomes, ontology-invalid signals, and reasoning-gap states
- follow-up history, plan, and execution summaries already carry proof-aware retry and review context plus compact graph-source lineage such as support lane, source family, artifact family, and content-origin counts for operator inspection
- `get_formal_validation_report(...)` now assembles a mediator-visible report from proof diagnostics, predicate counts, formal statuses, theorem-export metadata, and reasoner artifacts before draft generation.
- Formal validation claim and element reports now carry `support_quality_summary`, `primary_quality_signal`, and `quality_follow_up_action` values from the same support-path scoring used by coverage/recommendation flows, so blocked formal premises can be routed directly to graph, source-quality, duplicate-support, or support-path follow-up.
- Formal validation reports now aggregate `support_quality_signal_counts`, `primary_quality_signal_counts`, and `quality_follow_up_action_counts` at claim and report scope so queue builders and dashboards can summarize routing pressure without scanning element payloads.
- Review payload `claim_coverage_summary` entries now mirror formal status, theorem-export readiness, predicate/proof-gap counts, and formal support-quality routing counts so dashboard clients can render compact formal-validation health without traversing the full formal report.
- The claim-support review dashboard now renders a compact formal-validation routing card from those summary fields, including formal proof-gap pressure and quality follow-up routing chips.
- Review payloads now include `question_recommendation_summary` with lane, expected-proof-gain, support-quality signal, primary-quality signal, and quality follow-up action counts so follow-up queues can route recommended questions without scanning each question card.
- The claim-support review dashboard now renders those question recommendation summary counts above the question queue, including lane, proof-gain, and quality follow-up action chips.
- Individual dashboard question cards now render `quality_follow_up_action`, primary quality signal, and quality-signal counts as chips so operators can see why each support-quality question was routed.
- Follow-up task payloads now preserve `support_quality_summary`, `quality_signal_counts`, `primary_quality_signal`, and `quality_follow_up_action`, and plan/execution summaries aggregate those maps for queue routing and operator dashboards.
- The claim-support review dashboard Follow-Up Signals panel now renders plan/execution quality follow-up action counts, falling back to primary/raw quality signal counts when action labels are absent.
- Individual follow-up plan and history rows now render quality follow-up action, primary quality signal, and raw quality-signal count chips so operators can see why each quality remediation item exists.

Acceptance criteria:

- mediator can expose a formal validation report before draft generation

### Work Package W6.4: Authority-derived rule grounding

Status: Complete
Target files:

- `mediator/legal_authority_hooks.py`
- `complaint_phases/legal_graph.py`
- `complaint_phases/neurosymbolic_matcher.py`

Tasks:

- translate statutes, administrative rules, and guidance passages into obligation, prohibition, exception, and procedural-rule candidates
- map authority treatment state into reasoning inputs so weakened or adverse authorities do not count like clean support
- preserve provenance from authority passage to grounded rule candidate

Acceptance criteria:

- at least one authority family can produce grounded rule candidates that participate in claim-element validation
- validation outputs can identify whether a failed premise came from missing facts, missing rules, or adverse authority

Implementation notes:

- `LegalAuthorityStorageHook` now stores a `metadata.grounded_rule` payload on extracted rule candidates with normalized deontic operator, operator family, legal-premise type, authority provenance, claim-element mapping, temporal scope, and treatment influence.
- Authority record retrieval rehydrates treatment-aware grounded-rule metadata so adverse, limiting, questioned, superseded, overruled, or reversed treatment weakens rule candidates without requiring new database columns.
- Rule-candidate summaries now include deontic/operator/grounding-status counts and adverse-treatment totals; legal graph rule-candidate nodes project these fields for downstream ontology and proof workflows.
- Formal validation element reports now include `premise_failure_category` plus authority rule/treatment summaries, allowing consumers to distinguish missing facts, missing rules, adverse authority, contradictions, and unprovable formal premises.

## W7: Retrieval and Follow-Up Optimization

Status: In Progress
Priority: P1

### Why this matters

Follow-up execution and deduplication already exist. The next step is to make retrieval ranking support-aware, graph-aware, and archive-aware.

### Work Package W7.1: Retrieval ranking enrichment

Status: In Progress
Target files:

- `complaint_analysis/indexer.py`
- `integrations/ipfs_datasets/search.py`
- future vector-store adapter if needed

Tasks:

- rank search results by claim-element fit, source quality, authority class, and temporal relevance
- add graph-aware ranking signals once support queries exist
- keep retrieval explainable for operator review

Acceptance criteria:

- search results can explain why they were prioritized for a specific claim element or follow-up task

Implementation notes:

- `RetrievalOrchestrator` query contexts now accept claim-element text, required support kinds, and temporal context, then annotate ranked records with claim-element fit, source quality, authority class, temporal relevance, graph/support quality, archive, and cross-source fusion factors.
- `integrations.ipfs_datasets.search.rank_search_results(...)` provides the same explainable ranking envelope for normalized web/search results; `search_brave_web(...)` and `search_multi_engine_web(...)` apply it while preserving existing optional parameters.
- Claim retrieval sessions persist `retrieval_ranking_factors`, matched query/element terms, and `retrieval_ranking_explanation` in each result's metadata, and replay those fields in element retrieval context.

### Work Package W7.2: Archive-first evidence acquisition

Status: In Progress
Target files:

- `mediator/web_evidence_hooks.py`
- `integrations/ipfs_datasets/search.py`

Tasks:

- archive high-value URLs during acquisition when archive tools are available
- preserve archive result metadata in stored evidence records

Implementation notes:

- `integrations.ipfs_datasets.search.archive_url_snapshot(...)` normalizes Wayback-compatible save responses into archive URL, timestamp, capture source, and historical-capture metadata.
- `WebEvidenceIntegrationHook` attempts archive capture for high-relevance live web results when archive-on-acquire is enabled or the archive helper is injected/mocked, without making archive network calls by default.
- Stored web evidence summaries now count archive attempts, captures, skips, failures, and per-URL archive results. Captured metadata is preserved in storage metadata, parse/provenance lineage, and claim-support link metadata.

### Work Package W7.3: Queue-aware retrieval execution

Status: In Progress
Target files:

- `mediator/evidence_hooks.py`
- `mediator/mediator.py`
- `scripts/agentic_scraper_cli.py`

Tasks:

- make queued acquisition the default operational mode for long-running scraper work
- allow direct bounded execution for debugging and one-off runs
- carry queue state forward into review and reporting surfaces

Acceptance criteria:

- operator-facing worker processes only execute claimed queue items
- queued and completed retrieval work can be inspected without starting new scraper runs
- support payloads can tell whether an evidentiary page came from a live fetch, historical snapshot, or both

Implementation notes:

- `EvidenceStateHook.get_scraper_queue_state(...)` and `Mediator.get_scraper_queue_state(...)` expose inspection-only queue summaries with status counts, ready queued counts, owner/claim mixes, and queued/running/completed/failed rows without claiming jobs.
- `run_agentic_scraper_cycle(...)` now carries `scraper_queue_state` into reporting payloads so operator surfaces can inspect queued work after a bounded run without starting another scraper cycle.
- `scripts/agentic_scraper_cli.py run` now enqueues by default for worker execution; `run --direct` preserves the bounded immediate execution path for debugging and one-off runs. A `queue-state` command reports queue health without claiming work.
- Worker completion metadata records `executed_from_queue`, `worker_id`, and `claimed_job_id` so completed jobs can be audited as claimed queue work.

### Work Package W7.4: Follow-up task quality improvements

Status: Complete
Target files:

- `mediator/claim_support_hooks.py`
- `mediator/mediator.py`

Tasks:

- enrich follow-up tasks with source preferences, time windows, and authority intent
- incorporate contradiction, temporal-rule, treatment, and graph-gap signals into task metadata
- keep cooldown and result-level deduplication intact

Implemented baseline:

- follow-up tasks, execution payloads, and persisted history metadata now expose `graph_gap_context` with graph-support strength, recommended action, priority adjustment, fact/cluster/duplicate counts, source/corpus maps, and fact-registry summary alongside the full ranked graph-support payload
- normalized `graph_gap_query` packets are now shared by unresolved-gap queries, follow-up tasks, execution payloads, and rehydrated history rows so consumers can route graph-backed gap work without parsing raw graph-support payloads
- graph-gap follow-up summaries now include query-level counts and missing-support-kind/action/priority maps from those normalized packets
- follow-up plan, execution, and persisted history summaries now aggregate `graph_gap_context` into graph-gap task counts, support/empty counts, strength/recommended-action/priority-adjustment mixes, fact/cluster/duplicate totals, source/corpus maps, and compact fact-registry summaries for dashboard consumers
- the claim-support review dashboard now renders graph-gap signal cards plus plan, execution, history, task, and history-entry chips from those task-level and aggregate fields

Acceptance criteria:

- follow-up plans, execution payloads, and persisted history expose source preferences, time windows, and authority intent without bypassing duplicate/cooldown safeguards

### Work Package W7.5: Legal search program generation

Status: Planned
Target files:

- `mediator/legal_authority_hooks.py`
- `mediator/claim_support_hooks.py`
- `complaint_analysis/indexer.py`

Tasks:

- generate separate legal search programs for element-definition, fact-pattern, procedural, adverse-authority, and treatment-confirmation searches
- include jurisdiction, forum, time window, claim element, defense theme, and authority family in the generated program metadata
- carry authority intent such as `support`, `oppose`, `procedural`, and `confirm_good_law` into follow-up task generation and execution history

Implemented baseline:

- follow-up task generation already creates typed authority search-program bundles and task-level `authority_intent` values from support, adverse-authority, temporal/procedural, and good-law confirmation context
- follow-up plan/execution summaries aggregate primary authority intent counts alongside program type and authority/rule bias counts
- follow-up plan/execution summaries aggregate authority program jurisdiction, forum, authority-family, defense-theme, and time-window context counts for dashboard and API clients
- live follow-up execution task payloads now expose the selected authority search-program context at task scope, and execution summaries aggregate selected context counts before the history record is reloaded
- follow-up execution records now preserve the selected authority search-program intent, jurisdiction, forum, families, defense themes, and time window, and `follow_up_history_summary` aggregates the selected context counts for review dashboards
- the claim-support review dashboard renders task authority-intent and search-context chips, plan context summary chips, history selected-intent/context chips, and selected-intent/context history summary counts
- authority search-program generation now consumes task-level `graph_gap_query`; graph-backed missing-authority lanes add a `graph_backed_authority_gap` defense theme, preserve compact graph-query metadata in each generated program, and expose graph-gap authority-bias summary counts for review/dashboard consumers
- live authority execution now promotes the selected program's graph-gap bias into `selected_search_program_graph_gap_bias`, persists it in follow-up history, aggregates `selected_authority_graph_gap_bias_counts`, and renders selected graph-gap bias chips in the review dashboard

Acceptance criteria:

- legal follow-up tasks are no longer a single flat query per claim type
- review payloads can explain why a legal search was run, what authority intent it served, and what time/source/defense context shaped the search program

## W9: Legal Corpus Search and Authority Treatment

Status: In Progress
Priority: P0

### Why this matters

The system already finds and stores authorities, but it still treats legal research too much like generic retrieval. For complaint drafting and claim validation, the harder problem is deciding what governs the element, what cuts against it, and whether the cited authority is still safe to rely on.

### Work Package W9.1: Claim-aware legal search programs

Status: Complete
Target files:

- `integrations/ipfs_datasets/legal.py`
- `mediator/legal_authority_hooks.py`

Tasks:

- create normalized search wrappers and mediator search plans for element-definition, fact-pattern, procedural, adverse-authority, and treatment-check searches
- expand authority normalization for `administrative_rule`, `agency_guidance`, `docket_material`, and related authority families
- persist search-program metadata alongside returned authorities
- expose `search_legal_authority_program(...)` so generated programs can be executed by authority family without reinterpreting flat query text

Acceptance criteria:

- the mediator can search the legal corpus for both support and opposition for a specific claim element

### Work Package W9.2: Authority treatment persistence

Status: Complete
Target files:

- `integrations/ipfs_datasets/types.py`
- `mediator/legal_authority_hooks.py`
- schema layer to be selected during implementation

Tasks:

- store authority-treatment rows or metadata edges for `supports`, `adverse`, `limits`, `distinguishes`, `questioned`, `superseded`, and `good_law_unconfirmed`
- persist source, confidence, and explanation for each treatment entry
- keep degraded-mode behavior by allowing empty treatment state when no upstream treatment source is available
- add durable `Authority Record` and `Authority Treatment Edge` shapes that stay compatible with later graph and proof consumers

Acceptance criteria:

- at least one authority can accumulate treatment history and expose graph-compatible treatment edges without breaking existing storage and retrieval flows

### Work Package W9.3: Rule-candidate extraction and fact-pattern matching

Status: Complete
Target files:

- `integrations/ipfs_datasets/types.py`
- `mediator/legal_authority_hooks.py`
- `mediator/claim_support_hooks.py`
- `complaint_analysis/decision_trees.py`

Tasks:

- extract first-pass `Rule Candidate` records from parsed authority text for elements, defenses, exceptions, remedies, and procedural prerequisites
- connect rule candidates to claim elements, predicate templates, and jurisdiction or time-window constraints
- add fact-pattern-to-rule matching so support review can distinguish `authority found but facts do not satisfy the rule` from `authority not found`
- preserve passage-level provenance so operators can inspect the authority text that produced the rule candidate

Acceptance criteria:

- for at least one claim type, the system can link a stored authority passage to a rule candidate and to a claim element
- claim-support outputs can distinguish missing law, adverse law, and missing factual satisfaction with rule-candidate fact-satisfaction counts

### Work Package W9.4: Authority graph and review integration

Status: Complete
Target files:

- `complaint_phases/legal_graph.py`
- `mediator/claim_support_hooks.py`
- `claim_support_review.py`

Tasks:

- add authority-to-authority treatment edges and authority-to-proposition support edges
- add authority-to-rule and rule-to-claim-element edges where the source material is strong enough to justify them
- include supportive, adverse, and uncertain-authority counts in compact review payloads
- allow follow-up planning to request `find_better_authority` or `confirm_good_law` when support exists but treatment confidence is weak

Acceptance criteria:

- review surfaces can show both supporting and adverse authorities plus treatment uncertainty per claim element
- follow-up planning can react when existing authority support is legally weak rather than factually absent

## W8: Review and Operator Tooling

Status: In Progress
Priority: P1

### Why this matters

The integration only improves real legal work if people can inspect coverage, provenance, and contradictions without diving into raw tables.

The repo already has a first review surface through mediator payloads and the review API. The next step is to turn those packets into a fuller workspace rather than inventing the first operator view.

### Work Package W8.1: Support packet reporting

Status: Complete
Target files:

- `mediator/mediator.py`
- `applications/review_api.py`
- reporting or docs surfaces to be selected during implementation

Tasks:

- deepen existing support coverage summaries with direct evidence, authority, fact, and graph-support traces
- expose provenance summaries and bundle manifests
- expose contradiction and missing-support reports
- add timeline, archive-history, and graph-trace drilldown packets for operator review

Acceptance criteria:

- one mediator call can produce a reviewable support packet for a complaint or claim type
- operators can inspect which artifacts, authority passages, archive captures, graph traces, and validation outputs drove a support state

### Work Package W8.2: Background jobs for long-running workflows

Status: Complete
Target files:

- orchestration layer to be selected during implementation

Tasks:

- move archive, parse, graph, and validation work out of blocking flows where necessary
- persist job status, partial results, and failures

Acceptance criteria:

- long-running enrichment can be submitted, inspected, and updated with progress, partial results, and failures without blocking interactive case work

## W10: Drafting and Filing Readiness

Status: In Progress
Priority: P0

### Why this matters

The repository already has a formal complaint document builder, export API, and browser workflow. The missing step is to make drafting consume the same support, authority, graph, and validation signals that the review layer already exposes.

### Work Package W10.1: Claim-section support packets

Status: Complete
Target files:

- `document_pipeline.py`
- `mediator/mediator.py`
- `mediator/claim_support_hooks.py`
- `claim_support_review.py`

Tasks:

- derive section-level support packets for factual allegations, jurisdiction and venue, claims for relief, and requested relief
- map claim-element support status into drafting-ready bundles instead of requiring the document builder to infer readiness ad hoc
- carry provenance, authority-treatment, and validation summaries into document-ready packet shapes

Acceptance criteria:

- the document pipeline can request drafting support bundles from the mediator without re-querying raw support tables directly
- each major complaint section can surface source-backed support status or explicit gaps

### Work Package W10.2: Drafting-time authority and proof guardrails

Status: Complete
Target files:

- `document_pipeline.py`
- `mediator/legal_authority_hooks.py`
- `mediator/claim_support_hooks.py`
- `docs/PAYLOAD_CONTRACTS.md`

Tasks:

- surface warnings for adverse authority, weak treatment confidence, unresolved good-law checks, and missing procedural prerequisites before export
- surface proof-gap and failed-premise warnings where the validation layer can already explain legal insufficiency
- distinguish hard blockers from soft drafting warnings so degraded mode remains usable

Implementation notes:

- `document_pipeline.build_drafting_guardrails(...)` emits stable warning objects from drafting support bundles
- `Mediator.get_drafting_guardrails(...)` exposes guardrails with their source support bundles
- `FormalComplaintDocumentBuilder` embeds guardrails in `drafting_readiness` and preserves artifact generation in degraded mode

Acceptance criteria:

- complaint exports can flag unsupported or legally fragile sections without breaking existing artifact generation
- document payloads expose stable warning objects suitable for UI and CLI consumers

### Work Package W10.3: Browser builder and export workflow integration

Status: Complete
Target files:

- `applications/document_api.py`
- `applications/server.py`
- `templates/document.html`
- `docs/APPLICATIONS.md`

Tasks:

- expose section-level support readiness, warning summaries, and artifact provenance in the `/document` workflow
- let the browser builder show when a complaint section is grounded by evidence, authority, archive captures, graph support, or proof diagnostics
- keep generated artifact download behavior aligned with managed output paths and review-safe payloads

Implementation notes:

- `/api/documents/formal-complaint` now returns a `document_builder_summary` with support statuses, source-family counts, W10.2 guardrail counts, warning-type counts, document grounding metrics, and managed artifact provenance
- `/document` renders the summary in the Drafting Readiness panel before the detailed section/claim cards
- guardrail warning links understand `warning_type` and `element_id` fields so operators can navigate from drafting warnings back to claim-support review

Acceptance criteria:

- the browser builder can render readiness and warning state before or alongside generated artifacts
- operators can navigate from drafting output back to claim-support review without losing context

### Work Package W10.4: Filing-readiness tests and docs

Status: Complete
Target files:

- `tests/test_document_pipeline.py`
- `tests/test_formal_document_pipeline.py`
- `tests/test_review_api.py`
- `tests/test_claim_support_review_template.py`
- `docs/APPLICATIONS.md`
- `docs/PAYLOAD_CONTRACTS.md`

Tasks:

- add focused tests for section support packets, drafting warnings, and document workflow round-trips
- document the contract for drafting warnings, support bundles, and artifact metadata
- confirm degraded mode when graph, authority treatment, or logic extras are unavailable

Implementation notes:

- focused API/template tests now cover support bundles, W10.2 guardrail warnings, W10.3 builder summaries, managed artifact downloads, and degraded-mode exports without optional guardrail extras
- `docs/APPLICATIONS.md` and `docs/PAYLOAD_CONTRACTS.md` document drafting warnings, support bundles, `document_builder_summary`, review links, and artifact metadata
- degraded-mode responses keep generating artifacts and review links while reporting zero guardrail warnings/blockers when graph, authority-treatment, or logic extras are unavailable

Acceptance criteria:

- document export behavior is covered by focused tests instead of only broad endpoint smoke tests
- operator-facing drafting payload changes are documented and stable

## Recommended Sequence

## Immediate sequence

1. Finish the remaining W3 parse-contract completion for all source families and formats.
2. Finish W2.3 shared fact-registry expansion to archived pages and unified corpus semantics.
3. Add W2.5, W9.1, and W9.2 so authorities can carry treatment state and claim-aware legal search intent.
4. Add W9.3 so parsed authority passages produce rule candidates and fact-pattern matching outputs.
5. Deepen W4.1 and W4.4 so graph snapshots and coverage views become a stronger persistent query plane.
6. Advance W6.1, W6.3, and W6.4 from proof-aware placeholder flows to grounded validation runs with authority-derived rules.
7. Stabilize W8.1 support packet reporting around the existing review and dashboard payloads.
8. Add W10.1 and W10.2 so the document pipeline can consume section-level support packets and drafting warnings.

## Next sequence

1. Finish W4.3 claim-element support queries and graph-path drilldown.
2. Add W7.2 archive-first evidence acquisition.
3. Start W7.5 legal search program generation for support, adverse-authority, and treatment-confirmation tasks.
4. Add W9.4 authority graph and review integration.
5. Start W5.1 ontology generation workflow.
6. Add W8 timeline, archive-history, and provenance drilldown packets.
7. Add W10.3 browser builder readiness and warning integration.

## Later sequence

1. Persist W4.4 coverage matrix.
2. Add W5.2 support-path scoring.
3. Add W6.3 formal validation loop.
4. Expose W8.1 support packet reporting.
5. Complete W10.4 filing-readiness testing and payload documentation.

## Suggested Sprint Breakdown

### Sprint 1

- W1.1
- W3.1
- W3.2

Definition of done:

- all evidence and web parsing flows share one normalized parse contract

### Sprint 2

- W2.3
- W2.5
- W9.1
- W9.2

Definition of done:

- facts, authorities, and first-pass treatment records become persistent, provenance-linked records

### Sprint 3

- W9.3
- W4.3
- W4.4
- W4.1
- W4.2
- W7.2

Definition of done:

- claim-element support can be queried across evidence, authorities, archived web sources, and first-pass rule candidates

### Sprint 4

- W5.1
- W5.2
- W5.3

Definition of done:

- GraphRAG contributes support quality and gap signals to follow-up planning

### Sprint 5

- W6.1
- W6.2
- W6.3
- W6.4

Definition of done:

- grounded proof and contradiction signals are stable enough for downstream drafting and review consumers

### Sprint 6

- W10.1
- W10.2
- W10.3
- W10.4

Definition of done:

- the formal complaint builder can show section readiness, drafting warnings, and source-backed support context before export, with at least one complaint type carrying end-to-end formal validation and contradiction reporting into the drafting workflow

### Sprint 7

- W8.1
- W8.2

Definition of done:

- operators can inspect support, provenance, and contradiction outputs through stable interfaces

## Cross-Cutting Validation Requirements

- keep compile checks green for touched Python modules
- add focused tests for adapter degraded mode behavior
- add focused tests for evidence, authority, graph, and follow-up payload contracts
- document all externally visible payload changes in `docs/PAYLOAD_CONTRACTS.md`
- do not ship graph, GraphRAG, or logic features without mediator-visible outputs and review semantics

## Risks and Guardrails

### Risk: graph and logic integration remain shallow stubs

Guardrail:

- require every adapter expansion to land with at least one mediator consumer and one focused test

### Risk: archive and parsing work diverge by source type

Guardrail:

- force uploaded evidence, fetched pages, and legal texts through a shared document contract

### Risk: organization quality lags behind source ingestion volume

Guardrail:

- prioritize fact registry, support queries, and coverage matrix work before adding more retrieval sources

### Risk: environment-specific tooling blocks validation

Guardrail:

- keep degraded-mode tests and compile checks usable without a repo-local virtualenv

## Immediate Next Actions

1. Deepen `integrations/ipfs_datasets/documents.py`.
2. Route `mediator/evidence_hooks.py` and `mediator/web_evidence_hooks.py` through the new document contract.
3. Add typed authority-treatment storage and claim-aware legal search-program metadata in `mediator/legal_authority_hooks.py` and `integrations/ipfs_datasets/types.py`.
4. Extract first-pass rule candidates from parsed authority text and map them to claim elements before deeper theorem-prover work.
5. Expand `integrations/ipfs_datasets/graphs.py` to persist and query graph snapshots.
6. Expand the existing shared fact registry so claim elements, extracted facts, evidence, authorities, archived pages, and future predicates share one durable contract.
