# IPFS Datasets Py Execution Backlog

Date: 2026-03-12
Status: Active execution backlog

Companion docs:

- `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md`
- `docs/IPFS_DATASETS_PY_NEXT_BATCH_PLAN.md`
- `docs/IPFS_DATASETS_PY_CAPABILITY_MATRIX.md`
- `docs/PAYLOAD_CONTRACTS.md`

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

These are the main execution targets:

- `integrations/ipfs_datasets/documents.py` exists but is still a fallback-oriented adapter rather than the shared parse contract for all ingestion paths
- `integrations/ipfs_datasets/graphs.py` is still primarily fallback extraction and stub persistence
- `integrations/ipfs_datasets/graphrag.py` is not yet used in support scoring or denoiser planning
- `integrations/ipfs_datasets/logic.py` still returns `not_implemented` for proof workflows
- the shared fact registry exists for evidence and authorities but does not yet provide one durable corpus service across archived pages, graph artifacts, and future predicates
- no graph-store persistence or query plane exists for multi-artifact support tracing
- review payloads and a dedicated dashboard now exist, but there is still no full contradiction, provenance, timeline, and support-path review workspace

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
| W5 | GraphRAG support analysis | Planned | P1 | Ontology refinement improves support ranking and gap detection |
| W6 | Formal logic and theorem proving | In Progress | P1 | Claim-element sufficiency and contradiction validation |
| W7 | Retrieval and follow-up optimization | In Progress | P1 | Retrieval is driven by missing support and provenance-aware ranking |
| W8 | Review and operator tooling | In Progress | P1 | Existing coverage, follow-up, and dashboard payloads graduate into richer inspectable review surfaces |
| W9 | Legal corpus search and authority treatment | Planned | P0 | Claim elements can be researched for support, opposition, and authority reliability |
| W10 | Drafting and filing readiness | Planned | P0 | Formal complaint drafts become support-aware, citation-aware, and validation-aware |

## W1: Adapter Hardening

Status: In Progress
Priority: P0

### Why this matters

The adapter boundary exists, but parts of it still act as capability probes rather than full production-grade contracts.

### Work Package W1.1: Capability reporting cleanup

Status: In Progress
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

Status: Planned
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

Status: In Progress
Priority: P0

### Why this matters

The complaint generator already stores evidence and authorities well enough to deduplicate them. The next step is to treat them as one provenance-rich case model.

### Work Package W2.1: Shared case types expansion

Status: Planned
Target files:

- `integrations/ipfs_datasets/types.py`

Tasks:

- formalize `CaseFact`, `CaseClaimElement`, `CaseSupportEdge`, `FormalPredicate`, and `ValidationRun`
- standardize canonical IDs and version fields
- keep evidence and authority records compatible with future graph and logic layers

Acceptance criteria:

- artifacts, authorities, facts, support edges, and predicates share compatible provenance fields

### Work Package W2.2: Provenance normalization pass

Status: In Progress
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

Acceptance criteria:

- scraper workers idle or exit cleanly when there is no queued work
- queued work can be inspected, claimed, executed, and marked completed or failed
- queue semantics remain optional and do not break direct bounded-run entrypoints

### Work Package W2.5: Authority treatment and citation-history records

Status: Planned
Target files:

- `integrations/ipfs_datasets/types.py`
- `mediator/legal_authority_hooks.py`
- `mediator/claim_support_hooks.py`

Tasks:

- add durable typed records for authority treatment, citation history, and authority-to-authority relationships
- standardize fields such as `treatment_type`, `treatment_source`, `treatment_confidence`, `treatment_date`, and `treatment_explanation`
- keep authority records compatible with later graph and logic workflows that need to distinguish supportive from adverse or unreliable authority

Acceptance criteria:

- stored authorities can carry treatment records without breaking existing authority or support payloads
- treatment data is available to support scoring and review payload generation

## W3: Document and Chunk Services

Status: In Progress
Priority: P0

### Why this matters

Source material cannot support graph, retrieval, or theorem-proving workflows if it remains opaque bytes or page blobs.

### Work Package W3.1: Document adapter

Status: In Progress
Target files:

- `integrations/ipfs_datasets/documents.py`

Tasks:

- wrap file type detection
- wrap PDF and OCR extraction when available
- expose chunking and metadata extraction
- normalize PDF, DOCX, RTF, HTML, email, and office-document parsing behind one adapter contract
- return normalized parse outputs with provenance hooks

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

Acceptance criteria:

- mediator can return graph-backed support traces for review and drafting readiness

### Work Package W4.4: Coverage matrix persistence

Status: Planned
Target files:

- schema layer to be selected during implementation
- `mediator/claim_support_hooks.py`
- `mediator/mediator.py`

Tasks:

- persist coverage rows with supporting facts, artifacts, authorities, contradictions, and latest validation state
- make coverage rows the central organization and reporting model

Acceptance criteria:

- drafting and review flows can ask for one authoritative claim-element coverage matrix instead of stitching multiple tables manually

## W5: GraphRAG Support Analysis

Status: Planned
Priority: P1

### Why this matters

GraphRAG should improve how the system organizes and ranks support, not just act as a standalone ontology experiment.

### Work Package W5.1: Ontology generation workflow

Status: Planned
Target files:

- `integrations/ipfs_datasets/graphrag.py`
- `complaint_phases/neurosymbolic_matcher.py`

Tasks:

- generate ontologies from complaint narratives and parsed evidence corpora
- validate generated ontologies before using them for support decisions
- add a normalized ontology-quality payload consumable by complaint phases

Acceptance criteria:

- at least one complaint workflow can generate and validate an ontology without bypassing the adapter boundary

### Work Package W5.2: Support-path scoring

Status: Planned
Target files:

- `integrations/ipfs_datasets/graphrag.py`
- `mediator/claim_support_hooks.py`
- `mediator/mediator.py`

Tasks:

- score support paths using ontology structure, graph connectivity, and source quality
- feed scored support paths into claim overview summaries
- distinguish strong support, weak support, duplicate support, and structurally missing support

Acceptance criteria:

- claim overviews can surface support quality, not just support count

### Work Package W5.3: Denoiser and follow-up integration

Status: Planned
Target files:

- `complaint_phases/neurosymbolic_matcher.py`
- `complaint_phases/phase_manager.py`
- `mediator/claim_support_hooks.py`

Tasks:

- turn ontology and graph-quality gaps into follow-up tasks and denoising prompts
- prioritize follow-up work from structural gaps instead of generic missing evidence heuristics

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

Status: Planned
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
- follow-up history, plan, and execution summaries already carry proof-aware retry and review context for operator inspection

Acceptance criteria:

- mediator can expose a formal validation report before draft generation

### Work Package W6.4: Authority-derived rule grounding

Status: Planned
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

## W7: Retrieval and Follow-Up Optimization

Status: In Progress
Priority: P1

### Why this matters

Follow-up execution and deduplication already exist. The next step is to make retrieval ranking support-aware, graph-aware, and archive-aware.

### Work Package W7.1: Retrieval ranking enrichment

Status: Planned
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

### Work Package W7.2: Archive-first evidence acquisition

Status: Planned
Target files:

- `mediator/web_evidence_hooks.py`
- `integrations/ipfs_datasets/search.py`

Tasks:

- archive high-value URLs during acquisition when archive tools are available
- preserve archive result metadata in stored evidence records

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
- distinguish live-web evidence from historical snapshots in support summaries

Acceptance criteria:

- support payloads can tell whether an evidentiary page came from a live fetch, historical snapshot, or both

### Work Package W7.4: Follow-up task quality improvements

Status: In Progress
Target files:

- `mediator/claim_support_hooks.py`
- `mediator/mediator.py`

Tasks:

- enrich follow-up tasks with source preferences, time windows, and authority intent
- incorporate contradiction and graph-gap signals once available
- keep cooldown and result-level deduplication intact

Acceptance criteria:

- repeated follow-up execution produces fewer redundant queries and better targeted results

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

Acceptance criteria:

- legal follow-up tasks are no longer a single flat query per claim type
- review payloads can explain why a legal search was run and what authority intent it served

## W9: Legal Corpus Search and Authority Treatment

Status: Planned
Priority: P0

### Why this matters

The system already finds and stores authorities, but it still treats legal research too much like generic retrieval. For complaint drafting and claim validation, the harder problem is deciding what governs the element, what cuts against it, and whether the cited authority is still safe to rely on.

### Work Package W9.1: Claim-aware legal search programs

Status: Planned
Target files:

- `integrations/ipfs_datasets/legal.py`
- `mediator/legal_authority_hooks.py`

Tasks:

- create normalized search wrappers and mediator search plans for element-definition, fact-pattern, procedural, adverse-authority, and treatment-check searches
- expand authority normalization for `administrative_rule`, `agency_guidance`, `docket_material`, and related authority families
- persist search-program metadata alongside returned authorities

Acceptance criteria:

- the mediator can search the legal corpus for both support and opposition for a specific claim element

### Work Package W9.2: Authority treatment persistence

Status: Planned
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

- at least one authority can accumulate treatment history without breaking existing storage and retrieval flows

### Work Package W9.3: Rule-candidate extraction and fact-pattern matching

Status: Planned
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
- claim-support outputs can distinguish missing law, adverse law, and missing factual satisfaction

### Work Package W9.4: Authority graph and review integration

Status: Planned
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

Status: In Progress
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

Status: Planned
Target files:

- orchestration layer to be selected during implementation

Tasks:

- move archive, parse, graph, and validation work out of blocking flows where necessary
- persist job status, partial results, and failures

Acceptance criteria:

- long-running enrichment no longer blocks interactive case work

## W10: Drafting and Filing Readiness

Status: Planned
Priority: P0

### Why this matters

The repository already has a formal complaint document builder, export API, and browser workflow. The missing step is to make drafting consume the same support, authority, graph, and validation signals that the review layer already exposes.

### Work Package W10.1: Claim-section support packets

Status: Planned
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

Status: Planned
Target files:

- `document_pipeline.py`
- `mediator/legal_authority_hooks.py`
- `mediator/claim_support_hooks.py`
- `docs/PAYLOAD_CONTRACTS.md`

Tasks:

- surface warnings for adverse authority, weak treatment confidence, unresolved good-law checks, and missing procedural prerequisites before export
- surface proof-gap and failed-premise warnings where the validation layer can already explain legal insufficiency
- distinguish hard blockers from soft drafting warnings so degraded mode remains usable

Acceptance criteria:

- complaint exports can flag unsupported or legally fragile sections without breaking existing artifact generation
- document payloads expose stable warning objects suitable for UI and CLI consumers

### Work Package W10.3: Browser builder and export workflow integration

Status: Planned
Target files:

- `applications/document_api.py`
- `applications/server.py`
- `templates/document.html`
- `docs/APPLICATIONS.md`

Tasks:

- expose section-level support readiness, warning summaries, and artifact provenance in the `/document` workflow
- let the browser builder show when a complaint section is grounded by evidence, authority, archive captures, graph support, or proof diagnostics
- keep generated artifact download behavior aligned with managed output paths and review-safe payloads

Acceptance criteria:

- the browser builder can render readiness and warning state before or alongside generated artifacts
- operators can navigate from drafting output back to claim-support review without losing context

### Work Package W10.4: Filing-readiness tests and docs

Status: Planned
Target files:

- `tests/test_document_pipeline.py`
- `tests/test_review_api.py`
- `tests/test_claim_support_review_template.py`
- `docs/APPLICATIONS.md`
- `docs/PAYLOAD_CONTRACTS.md`

Tasks:

- add focused tests for section support packets, drafting warnings, and document workflow round-trips
- document the contract for drafting warnings, support bundles, and artifact metadata
- confirm degraded mode when graph, authority treatment, or logic extras are unavailable

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
