# IPFS Datasets Py Improvement Plan

Date: 2026-03-11

## Purpose

Define a comprehensive, current-state improvement plan for how the `ipfs_datasets_py` submodule should be used inside complaint-generator to improve legal scraping, legal dataset search, graph-based organization, theorem-prover-backed validation, web archiving, search, and overall information organization.

This plan is based on the repository as it exists now, not on a greenfield rewrite.

## Executive Summary

Complaint-generator already has the foundation for a strong `ipfs_datasets_py` integration:

- an adapter boundary under `integrations/ipfs_datasets/`
- evidence, legal authority, and web evidence mediator hooks already using parts of that adapter layer
- persistent DuckDB support tracking for evidence, authorities, claim elements, and follow-up execution
- a three-phase reasoning model built around knowledge, dependency, and legal graphs
- normalized provenance and deduplication-aware payloads already exposed by mediator APIs

The main opportunity is no longer "add IPFS" or "add search." The opportunity is to turn the current partial integration into a full legal knowledge plane that can:

1. Acquire authoritative and evidentiary material reproducibly.
2. Archive and normalize that material into a shared case model.
3. Organize facts, authorities, artifacts, and timelines in complaint graphs and a backing graph store.
4. Use GraphRAG and graph traversal to improve support discovery and explanation.
5. Translate claim requirements and facts into predicates for theorem-style validation.
6. Feed gaps, contradictions, and support coverage back into the mediator and complaint drafting flow.

The end state should be a complaint generator that can answer, for every claim element:

- what evidence supports it
- what authorities support it
- what historical web records corroborate it
- what facts are still missing
- what contradictions exist
- what is provable, partially supported, or unprovable

## Planning Inputs

This roadmap should be read alongside:

- `docs/IPFS_DATASETS_PY_CAPABILITY_MATRIX.md`
- `docs/PAYLOAD_CONTRACTS.md`
- `docs/EVIDENCE_MANAGEMENT.md`
- `docs/WEB_EVIDENCE_DISCOVERY.md`
- `docs/LEGAL_AUTHORITY_RESEARCH.md`

## Current State Assessment

## What is already integrated

### Adapter boundary

The production import boundary already exists under `integrations/ipfs_datasets/`.

Current adapter modules include:

- `loader.py`
- `capabilities.py`
- `storage.py`
- `search.py`
- `legal.py`
- `llm.py`
- `provenance.py`
- `types.py`
- `graphs.py`
- `graphrag.py`
- `logic.py`

This is an important milestone: complaint-generator already has a place to centralize feature detection, compatibility handling, and degraded mode behavior.

### Mediator-level integration

The mediator stack already uses several of these capabilities:

- `mediator/evidence_hooks.py` uses IPFS-backed storage adapters, provenance, and graph extraction fallbacks
- `mediator/web_evidence_hooks.py` uses search and web evidence ingestion flows
- `mediator/legal_authority_hooks.py` uses legal authority search adapters and normalized authority storage
- `mediator/mediator.py` logs `ipfs_datasets_py` capability status and orchestrates graph projection

### Persistent support organization

Complaint-generator already persists:

- evidence rows
- legal authority rows
- claim requirements
- claim-support links
- follow-up execution history
- deduplication metadata

This is the right substrate for integrating richer graph, archival, and theorem-proving features.

### Internal graph host model

The canonical complaint-case model already lives in `complaint_phases/`:

- knowledge graph
- dependency graph
- legal graph
- neurosymbolic matcher
- phase manager

These should remain the canonical in-memory workflow model. `ipfs_datasets_py` should enrich these components, not replace them.

## What exists but is still shallow

Several adapters now exist but are not yet full workflow integrations:

- `integrations/ipfs_datasets/graphs.py` currently provides extraction and persistence fallbacks, but not robust graph-store workflows
- `integrations/ipfs_datasets/graphrag.py` can probe GraphRAG capabilities, but it is not yet driving mediator support analysis
- `integrations/ipfs_datasets/logic.py` currently advertises logic availability but still returns `not_implemented` payloads for proof workflows

In other words, the package boundary exists, but some high-value features are still only capability shells.

## What is still missing

The largest gaps are now product and workflow gaps, not import gaps:

- no fully integrated end-to-end document parsing workflow across all ingestion paths
- no graph database persistence strategy for multi-artifact legal reasoning
- no production theorem-prover workflow for claim-element validation
- no GraphRAG-backed retrieval or ontology refinement in complaint workflows
- no unified fact registry spanning uploaded evidence, archived pages, and authorities
- no operator-facing case support dashboard
- no async job boundary for long-running fetch, parse, archive, graph, or reasoning work

## Strategic Objective

Use `ipfs_datasets_py` to turn complaint-generator from a complaint drafting workflow with helpful evidence hooks into a structured legal knowledge system that can collect, archive, organize, validate, and explain support for every claim element.

## Integration Principles

1. Keep complaint-generator as the orchestrator.
2. Keep `complaint_phases/` as the canonical workflow graph API.
3. Keep all production `ipfs_datasets_py` usage behind `integrations/ipfs_datasets/`.
4. Make provenance, deduplication, and explainability first-class requirements.
5. Treat graph and theorem-prover features as decision-support layers, not isolated experiments.
6. Preserve full, partial, and degraded runtime modes.

## Capability-by-Capability Integration Plan

## 1. Legal Scrapers and Legal Dataset Search

### Value

Use `ipfs_datasets_py` legal scrapers to build a broader, claim-element-aware legal research layer that covers statutes, regulations, case documents, administrative materials, and future state-level sources.

### Current position

Already partially integrated:

- normalized authority storage exists
- claim-element linking exists
- legal research is already routed through mediator hooks

### Improvement plan

- normalize all legal source results into a single authority model
- add explicit ranking fields for jurisdiction, precedential weight, recency, and controlling-authority likelihood
- expand authority linking beyond claim type into procedural requirement and claim-element granularity
- add conflict detection where authorities weaken, distinguish, or contradict each other
- support state and agency source expansion with per-source provenance and freshness metadata

### Target outcome

For each claim element, the system should be able to enumerate:

- controlling authority
- persuasive authority
- procedural support
- contrary authority
- missing authority coverage

## 2. Web Search, Common Crawl, and Web Archiving

### Value

Use `ipfs_datasets_py` search and archive capabilities to capture public evidence reproducibly and tie it to timelines, exhibits, and claim elements.

### Current position

Already partially integrated:

- web evidence search exists
- discovered evidence is stored, deduplicated, and linked to claim elements
- graph projection metadata is already returned

### Improvement plan

- immediately archive important URLs during evidence acquisition
- preserve fetch timestamp, archive source, and page version metadata
- store normalized page text and chunk lineage for later graph and logic processing
- cluster duplicate evidence across Brave, Common Crawl, Wayback, and direct fetches
- add domain- and timeline-specific workflows for employer policy changes, public statements, agency notices, and terms-of-service history

### Target outcome

The system should be able to answer:

- what a page said on a relevant date
- where that page was found
- whether it was archived
- which claims or facts it supports
- whether a later version contradicts an earlier version

## 3. Graph Database and Knowledge Graph Integration

### Value

Use `ipfs_datasets_py` graph capabilities to organize artifacts, facts, legal authorities, and timelines across many sources while preserving provenance.

### Current position

Complaint-generator already has local knowledge and dependency graph models, and graph projection from evidence is already happening. A graph adapter exists, but backing graph-store workflows are still mostly placeholders.

### Improvement plan

- persist graph projections into a backing graph store when graph backends are available
- separate complaint graph, evidence graph, legal graph, and reasoning graph views while allowing shared entity resolution
- add cross-document entity resolution for parties, organizations, events, exhibits, and authorities
- expose graph traversal queries for support tracing and gap analysis
- record graph lineage so operators can see how a fact or support edge entered the case graph

### Target outcome

Operators and mediator workflows should be able to query:

- all artifacts that support claim element X
- all authorities linked to legal requirement Y
- all events involving defendant Z across evidence and authorities
- all unsupported elements after the latest ingestion pass
- all graph edges derived from archived source A

## 4. GraphRAG and Ontology Refinement

### Value

Use GraphRAG to improve information organization, ontology quality, and retrieval precision for complex legal matters.

### Current position

The GraphRAG adapter exists and can probe generator, validator, and mediator components, but it is not yet part of the case workflow.

### Improvement plan

- generate ontologies from complaint narratives, evidence corpora, and legal authority bundles
- validate ontologies before accepting graph refinements into complaint workflows
- use ontology refinement to improve entity normalization and relationship consistency
- use GraphRAG scoring to prioritize the strongest support paths for each claim element
- use GraphRAG outputs to improve denoiser question generation and follow-up planning

### Target outcome

GraphRAG should help the system distinguish between:

- useful but weak support
- structurally missing support
- duplicate or redundant support
- ontology errors caused by poor extraction or poor entity resolution

## 5. Theorem Provers and Formal Logic

### Value

Use `ipfs_datasets_py.logic` to translate legal requirements and extracted facts into structured predicates, then run contradiction and sufficiency checks.

### Current position

Logic capability detection exists, but proof workflows are not yet implemented.

### Improvement plan

- define claim-type-specific predicate templates for common complaint types
- translate claim elements from the legal graph into formal requirements
- translate extracted facts from evidence and archived pages into grounded predicates
- separate asserted facts from inferred facts
- run contradiction checks on timelines, party roles, and legal element satisfaction
- add optional external-prover tiers for stronger validation when Z3, CVC5, or other bridges are available
- store proof artifacts and failed premises as first-class validation records

### Target outcome

The system should return structured outputs such as:

- `provable_elements`
- `partially_supported_elements`
- `missing_predicates`
- `contradictory_predicates`
- `unsupported_inferences`
- `authorities_without_fact_support`

## 6. Document Parsing and Corpus Services

### Value

Treat all uploaded or discovered content as parseable corpus material rather than opaque files or URLs.

### Current position

Evidence ingestion already stores content and has lightweight parsing and graph extraction support, but there is no dedicated document adapter covering uploaded documents, fetched pages, and legal texts consistently.

### Improvement plan

- deepen `integrations/ipfs_datasets/documents.py` into the shared document contract for all ingestion paths
- standardize file detection, text extraction, OCR fallback, chunking, citation extraction, and metadata extraction
- feed chunk-level outputs into graph extraction, authority linking, and logic translation
- store chunk lineage so every sentence or predicate can be traced to a concrete source slice

### Target outcome

Every important artifact should become a reusable text corpus object with provenance-preserving chunks and downstream graph or logic links.

## 7. Search, Ranking, and Retrieval

### Value

Combine keyword, graph, provenance, and authority-aware retrieval instead of relying on flat search results.

### Current position

Search flows exist, but ranking is still mostly source-local and not deeply informed by graph structure, legal authority quality, or temporal context.

### Improvement plan

- rank evidence by relevance, source quality, claim-element fit, and temporal fit
- rank authorities by jurisdiction, authority class, citation quality, and legal element coverage
- add graph traversal as a retrieval mode for support chains
- add hybrid retrieval across facts, artifacts, authorities, and archived pages
- use follow-up execution history to avoid repeated low-value retrieval work

### Target outcome

Retrieval should become case-aware, provenance-aware, and support-aware.

## 8. Information Organization as a Product Feature

### Value

The most important benefit of this integration is better organization, not just more data.

### Improvement plan

- make claim-element coverage the primary organizational view
- maintain clear separation between raw source material, extracted facts, legal authorities, and inferred support
- expose timeline views backed by archived pages, evidence chunks, and graph relations
- provide support summaries that distinguish new support, reused support, contradictory support, and missing support
- expose provenance-linked review packets for filing and audit workflows

### Target outcome

The complaint generator should organize case information into a reusable support structure rather than a collection of search results, uploads, and notes.

## Target Architecture

## Layer 1: Orchestration

`mediator/mediator.py` remains the workflow orchestrator.

Mediator responsibilities should continue to include:

- phase progression
- case state
- interactive questioning
- follow-up planning and execution
- draft generation
- reporting and review payloads

## Layer 2: Adapter and capability boundary

All production integrations with `ipfs_datasets_py` should continue to flow through `integrations/ipfs_datasets/`.

Target adapter surface:

```text
integrations/ipfs_datasets/
  capabilities.py
  loader.py
  llm.py
  storage.py
  search.py
  legal.py
  documents.py
  graphs.py
  graphrag.py
  logic.py
  provenance.py
  types.py
```

## Layer 3: Acquisition and archival

Target pipeline:

search -> fetch -> archive -> hash -> store -> parse -> graph -> link -> validate

Use `ipfs_datasets_py` for:

- Brave and current-web search
- Common Crawl search
- archive search and capture
- legal source retrieval
- IPFS-backed content-addressed storage

## Layer 4: Shared case model

Introduce or formalize shared structures for:

- case artifacts
- authorities
- facts
- claim elements
- support edges
- predicates
- validation runs
- contradictions

## Layer 5: Graph and reasoning services

Maintain four cooperating graph views:

1. Complaint graph
2. Evidence graph
3. Legal graph
4. Reasoning graph

## Layer 6: Review and drafting

All final drafting should rely on structured support, with review surfaces for:

- support coverage
- contradiction analysis
- provenance bundles
- authority packets
- unresolved gaps

## Recommended Shared Data Model

## Core entities

Standardize or formalize the following concepts across storage and APIs:

- `CaseArtifact`
- `CaseAuthority`
- `CaseFact`
- `CaseClaimElement`
- `CaseSupportEdge`
- `FormalPredicate`
- `ValidationRun`
- `ContradictionRecord`

## Minimum provenance fields

Every artifact, authority, chunk, graph node, edge, predicate, and validation record should carry:

- source origin
- acquisition timestamp
- acquisition method
- source system
- content hash
- CID when available
- parser version
- extraction version
- graph ingestion version
- reasoning version

## Claim-element coverage matrix

The central organizational structure should be a claim-element coverage matrix with fields such as:

- complaint ID
- claim type
- claim element ID
- claim element text
- supporting fact IDs
- supporting artifact IDs
- supporting authority IDs
- support strength
- contradiction count
- unresolved gap summary
- latest validation run ID

## End-to-End Workflow Vision

1. Intake captures complaint text and produces claim hypotheses.
2. Knowledge and dependency graphs identify entities, requirements, and missing support.
3. Search and legal research generate targeted acquisition tasks.
4. Web pages and legal materials are fetched, archived, hashed, and stored.
5. Documents and pages are parsed into normalized text and chunk records.
6. Graph extraction resolves entities, facts, and cross-document links.
7. Authorities are linked to legal requirements and claim elements.
8. Facts and legal elements are translated into predicates.
9. Logic validation identifies supported, partial, unsupported, and contradictory elements.
10. The denoiser generates focused follow-up questions from graph and logic gaps.
11. Draft generation uses supported facts, linked authorities, and clearly marked inferences.
12. Operator review sees support coverage, contradiction analysis, and provenance bundles.

## Workstreams and Deliverables

## Workstream A: Adapter hardening

Objective: make capability availability stable and predictable.

Deliverables:

- remove remaining production direct-import drift
- expand adapter tests for real module-path compatibility
- expose a consistent capability report and CLI diagnostics
- document supported full, partial, and degraded runtime modes

Acceptance criteria:

- mediator startup is stable in all three runtime modes
- no production code needs local `sys.path` mutation
- capability output is consistent and actionable

## Workstream B: Unified acquisition and provenance

Objective: normalize evidence, archived pages, and authorities into one case model.

Deliverables:

- shared provenance schema across evidence and legal authorities
- stronger URL, citation, and content-hash deduplication
- archive-aware storage records for public web evidence
- chunk and transform lineage tables

Acceptance criteria:

- every stored artifact and authority can be traced to a source and acquisition method
- deduplicated records remain distinguishable from newly created records

## Workstream C: Document services

Objective: turn source material into reusable text and chunk corpora.

Deliverables:

- `documents.py` adapter
- chunk-level parsing APIs
- OCR and file-type fallback handling
- citation and timeline extraction helpers

Acceptance criteria:

- uploaded evidence, fetched pages, and authority texts all produce consistent parse outputs

## Workstream D: Graph persistence and graph queries

Objective: back the in-memory complaint graphs with richer graph organization.

Deliverables:

- graph snapshot persistence
- support-tracing query APIs
- cross-document entity resolution
- graph lineage and audit outputs

Acceptance criteria:

- support traces are queryable across artifacts and authorities
- graph outputs preserve provenance

## Workstream E: GraphRAG support analysis

Objective: use ontology refinement and graph validation to improve support organization.

Deliverables:

- ontology generation from complaint and evidence corpora
- ontology validation before graph refinement acceptance
- GraphRAG scoring for support-path ranking
- graph-quality diagnostics integrated with mediator review flows

Acceptance criteria:

- GraphRAG materially improves support ranking or gap detection for at least one complaint workflow

## Workstream F: Formal validation and theorem proving

Objective: make claim sufficiency and contradiction analysis machine-assisted.

Deliverables:

- predicate templates per claim type
- fact-to-predicate and authority-to-rule translation
- contradiction checks and missing-premise outputs
- optional external-prover integration tier

Acceptance criteria:

- claim-element validation emits structured proof-gap outputs before drafting
- contradiction reports are provenance-backed and reviewable

## Workstream G: Retrieval and follow-up planning

Objective: use support structure, not raw search output, to drive follow-up work.

Deliverables:

- hybrid ranking across evidence, authorities, graph relations, and time
- follow-up planning from missing support and contradictions
- cooldown-aware and result-aware retrieval policies

Acceptance criteria:

- follow-up execution prioritizes missing claim-element support instead of repeated generic queries

## Workstream H: Review and operator tooling

Objective: make the integrated system inspectable and usable.

Deliverables:

- support coverage summaries
- provenance-linked evidence review packets
- authority review views
- contradiction and missing-support reports
- background jobs for long-running acquisition and validation work

Acceptance criteria:

- operators can inspect why a claim element is marked covered, partial, or missing

## Phased Roadmap

## Phase 1: Consolidate what already exists

Focus:

- finish adapter hardening
- normalize acquisition and provenance
- close remaining production import drift
- align docs, payloads, and tests around the same contracts

Priority files:

- `integrations/ipfs_datasets/capabilities.py`
- `integrations/ipfs_datasets/search.py`
- `integrations/ipfs_datasets/legal.py`
- `integrations/ipfs_datasets/provenance.py`
- `integrations/ipfs_datasets/types.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`

## Phase 2: Add document and graph services

Focus:

- add document adapter
- deepen graph extraction and graph snapshot persistence
- add graph-support query APIs

Priority files:

- `integrations/ipfs_datasets/documents.py`
- `integrations/ipfs_datasets/graphs.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `complaint_phases/knowledge_graph.py`
- `complaint_phases/dependency_graph.py`

## Phase 3: Add GraphRAG workflows

Focus:

- ontology generation
- ontology validation
- graph-quality diagnostics
- support-path ranking improvements

Priority files:

- `integrations/ipfs_datasets/graphrag.py`
- `complaint_phases/neurosymbolic_matcher.py`
- mediator review/reporting surfaces

## Phase 4: Add theorem-prover-backed validation

Focus:

- predicate templates
- proof-gap reporting
- contradiction analysis
- optional external prover tier

Priority files:

- `integrations/ipfs_datasets/logic.py`
- `complaint_phases/legal_graph.py`
- `complaint_phases/neurosymbolic_matcher.py`
- `mediator/mediator.py`

## Phase 5: Productize case organization

Focus:

- review surfaces
- async jobs
- benchmark and adversarial validation
- support dashboards and operator workflows

Priority files:

- mediator reporting APIs
- docs and examples
- applications and future UI surfaces

## Recommended Near-Term Implementation Order

## Next 2 weeks

1. Finish production import boundary cleanup.
2. Deepen `documents.py` and normalize parsing outputs.
3. Standardize provenance fields and chunk lineage.
4. Add graph snapshot persistence contracts and tests.

## Next 30 days

1. Integrate graph support queries into mediator review flows.
2. Archive important web evidence eagerly and store archive metadata.
3. Expand legal authority normalization and ranking.
4. Introduce a shared fact registry across evidence and authorities.

## Next 60 to 90 days

1. Connect GraphRAG to support-path scoring and denoiser planning.
2. Implement claim-type-specific predicate templates.
3. Add contradiction detection and proof-gap outputs.
4. Build operator-facing support and provenance review views.

## Risks and Guardrails

### Risk: adapter drift from upstream package changes

Mitigation:

- keep capability matrix updated against pinned submodule commits
- add adapter compatibility tests

### Risk: graph and logic features become demos instead of workflow tools

Mitigation:

- require each new graph or logic feature to produce mediator-consumable outputs
- tie feature work to support coverage, contradiction, or follow-up improvements

### Risk: long-running ingestion blocks user workflows

Mitigation:

- move heavy archive, parse, graph, and proof work into async jobs
- keep mediator payloads incremental and status-oriented

### Risk: over-collection without organization

Mitigation:

- organize by claim element, provenance, and support edges first
- do not add new sources without a normalization and review plan

### Risk: degraded mode breaks when optional extras are missing

Mitigation:

- continue treating partial and degraded mode as supported product states
- keep adapter fallbacks explicit and tested

## Success Metrics

The integration should be considered successful when the system can demonstrate:

- higher percentage of claim elements with linked evidence and authorities
- fewer duplicate evidence and authority records per case
- better follow-up query precision
- explainable support traces from claim element to artifact and authority
- contradiction reports that catch real drafting problems before finalization
- stable operation in full, partial, and degraded environments

## Concrete Next Actions

1. Deepen `integrations/ipfs_datasets/documents.py` and route all parsing through it.
2. Expand `integrations/ipfs_datasets/graphs.py` from fallback extraction into graph persistence and support-query workflows.
3. Connect `integrations/ipfs_datasets/graphrag.py` outputs to support scoring and denoiser gap detection.
4. Replace `integrations/ipfs_datasets/logic.py` placeholders with claim-element proof and contradiction workflows.
5. Add a shared fact registry tying evidence, archived pages, and authorities to claim elements.
6. Add operator review endpoints or reports for support coverage, provenance, and contradictions.

## Summary

`ipfs_datasets_py` should not be treated as a bag of useful utilities. It should become the acquisition, archival, graph-enrichment, and formal-reasoning substrate that strengthens complaint-generator's ability to organize legal information.

The repo is already past the earliest stage of integration. Storage, search, provenance, legal authority linking, graph projection, and claim-support persistence are in place. The next stage is to turn the existing adapter and support infrastructure into a deeper system for:

- graph-backed legal knowledge organization
- archive-backed evidence preservation
- claim-element-centered retrieval
- GraphRAG-assisted support analysis
- theorem-prover-backed contradiction and sufficiency validation

That is the most direct path to a complaint generator that is materially better at organizing information, defending its recommendations, and producing filing-ready drafts.
