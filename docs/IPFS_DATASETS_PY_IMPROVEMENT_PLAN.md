# IPFS Datasets Py Improvement Plan

Date: 2026-03-10

## Purpose

Define a comprehensive, execution-oriented plan for using the `ipfs_datasets_py` submodule as a core research, storage, graph, and reasoning substrate inside complaint-generator.

This plan is based on the code that already exists in this repository today, not on a hypothetical greenfield design.

## Executive Summary

Complaint-generator already has the beginning of the right architecture:

- `integrations/ipfs_datasets/` exists and already centralizes part of the import boundary
- `mediator/mediator.py` already logs `ipfs_datasets` capability status at startup
- `mediator/evidence_hooks.py` already uses the storage adapter and provenance models
- `mediator/web_evidence_hooks.py` already uses the search adapter
- `mediator/legal_authority_hooks.py` already uses the legal adapter
- `complaint_phases/` already provides the host graph model for knowledge, dependency, legal, and neurosymbolic reasoning

The real opportunity is not to keep sprinkling more direct `ipfs_datasets_py` imports through the repo. The opportunity is to turn the current partial adapter layer into a complete integration plane that does five things well:

1. Acquire and archive evidence and authorities reproducibly.
2. Normalize everything into a shared case artifact model.
3. Enrich the complaint graphs with GraphRAG, search, provenance, and graph database capabilities.
4. Translate legal requirements and extracted facts into formal predicates for theorem-style validation.
5. Expose support coverage, contradictions, and unresolved gaps back to the mediator and drafting flow.

The target state is a complaint generator that can answer:

- what facts have been asserted
- what evidence artifacts support them
- what legal authorities support each claim element
- what historical web evidence exists and what it said at a given time
- what relationships exist across parties, events, exhibits, and authorities
- what is provable, weakly supported, contradictory, or still missing

## Current Baseline

### What is already wired

#### Adapter layer

The repository already contains:

- `integrations/ipfs_datasets/loader.py`
- `integrations/ipfs_datasets/capabilities.py`
- `integrations/ipfs_datasets/storage.py`
- `integrations/ipfs_datasets/search.py`
- `integrations/ipfs_datasets/legal.py`
- `integrations/ipfs_datasets/llm.py`
- `integrations/ipfs_datasets/provenance.py`
- `integrations/ipfs_datasets/types.py`

This means the repo has already moved beyond the earliest stage of integration planning.

#### Mediator and hooks

Current mediator-side integration points:

- `mediator/mediator.py` initializes and logs capability status once at startup
- `mediator/evidence_hooks.py` already uses the storage adapter and provenance records
- `mediator/web_evidence_hooks.py` already uses the search adapter for Brave and Common Crawl access
- `mediator/legal_authority_hooks.py` already uses the legal adapter and normalized authority models
- `mediator/legal_authority_hooks.py` now links legal authorities to claim elements in persistence

#### Internal host model

Complaint-generator already has strong internal structures for organization:

- `complaint_phases/knowledge_graph.py`
- `complaint_phases/dependency_graph.py`
- `complaint_phases/legal_graph.py`
- `complaint_phases/neurosymbolic_matcher.py`
- `complaint_phases/phase_manager.py`

These should remain the canonical complaint-case model. `ipfs_datasets_py` should enrich them, not replace them.

#### Existing direct imports still in the repo

There are still direct `ipfs_datasets_py` imports outside the adapter layer, notably in:

- `complaint_analysis/indexer.py`
- benchmark and profiling scripts
- several tests

That is acceptable for experiments and tests, but it is not the end state for production code.

### What is missing

The current integration is useful but still shallow.

Key missing pieces:

- no graph adapter layer yet
- no logic or theorem-proving adapter layer yet
- no document-processing adapter layer yet
- no unified artifact-to-fact-to-authority-to-predicate pipeline
- no graph database persistence strategy for cross-document legal reasoning
- no formal claim-element coverage matrix shared across evidence and authority flows
- no consistent async job boundary for long-running ingestion and validation tasks
- no operator-facing dashboard for support coverage and provenance review

### Confirmed operational modes

The system needs to support three runtime modes cleanly:

1. Full mode: `ipfs_datasets_py` installed and importable with optional extras present.
2. Partial mode: only some capabilities available, such as storage and search but not logic or graph extras.
3. Degraded mode: no `ipfs_datasets_py`, with complaint-generator still able to run core workflows locally.

These modes should be first-class product states, not edge cases.

## Strategic Integration Goals

### Goal 1: Finish the import boundary

All production integrations with `ipfs_datasets_py` should route through `integrations/ipfs_datasets/`.

That package should own:

- path setup
- optional imports
- compatibility shims
- sync and async bridging
- capability discovery
- normalization of return shapes
- runtime feature flags

### Goal 2: Build a unified legal knowledge plane

All evidence, authorities, search results, parsed documents, graph nodes, and logical predicates should connect through a shared case model and provenance model.

### Goal 3: Make information organization the main product improvement

The real gain from `ipfs_datasets_py` is not just more search. It is better organization of information:

- grouping related artifacts
- deduplicating evidence across sources
- connecting facts to claim elements
- connecting authorities to legal requirements
- connecting timelines to web archives and exhibits
- connecting all of that to complaint drafting

### Goal 4: Turn graph and theorem-proving capabilities into enforcement layers

Graph and logic features should stop being isolated experiments and become decision-support components that directly influence:

- follow-up questions
- support scoring
- contradiction warnings
- draft confidence
- filing readiness

### Goal 5: Keep graceful degradation intact

The integration should improve the system when available, but never make complaint-generator dependent on a fragile or partially initialized submodule.

## Recommended Target Architecture

## Layer 1: Orchestration

Complaint-generator remains the system of record for user workflow and case state.

Primary orchestrator:

- `mediator/mediator.py`

The mediator should continue to own:

- phase progression
- case context
- interactive questioning
- draft generation
- hook orchestration

## Layer 2: Capability and adapter boundary

`integrations/ipfs_datasets/` becomes the only direct integration surface.

Expand it to include:

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
  vector_store.py
  mcp_gateway.py
  provenance.py
  types.py
```

Recommended responsibilities:

- `documents.py`: PDF, OCR, text extraction, chunking
- `graphs.py`: graph extraction, graph storage, graph querying, lineage
- `graphrag.py`: ontology generation, ontology validation, graph refinement
- `logic.py`: FOL, deontic, temporal logic, theorem proving, contradiction checks
- `vector_store.py`: semantic indexing, retrieval, hybrid search
- `mcp_gateway.py`: controlled access to selected MCP tools if needed for background workflows

## Layer 3: Acquisition and archival

All current-web and historical-web retrieval should converge into one acquisition pipeline:

search -> fetch -> archive -> hash -> store -> parse -> graph -> link -> validate

Use `ipfs_datasets_py` for:

- Brave search
- Common Crawl search
- Wayback and archive workflows
- legal dataset scrapers
- content-addressed storage

## Layer 4: Shared case model and provenance

Introduce a persistent case model that spans:

- uploaded exhibits
- scraped pages
- archived snapshots
- legal authorities
- extracted facts
- graph nodes and edges
- formal predicates
- validation runs

Every record should carry provenance and versioned transformation lineage.

## Layer 5: Graph and reasoning services

The graph stack should have four cooperating planes:

1. Complaint graph: people, entities, events, claims, facts.
2. Evidence graph: artifacts, sources, fetches, hashes, archival snapshots, duplicates.
3. Legal graph: statutes, regulations, cases, elements, procedures, defenses.
4. Reasoning graph: predicates, entailments, missing premises, contradictions, proof artifacts.

## Layer 6: Drafting and operator review

Final draft generation should depend on structured support, not raw search output.

Outputs should include:

- complaint draft
- support coverage summary
- contradiction report
- missing-proof report
- provenance-linked exhibit bundle
- authority packet per claim type

## High-Value Integration Workstreams

### Workstream A: Import boundary hardening

Objective: stop integration sprawl and make feature availability predictable.

Actions:

- move remaining production imports behind the adapter layer
- keep benchmarks and tests free to import directly when useful, but document that distinction
- add adapter-level compatibility tests against known `ipfs_datasets_py` module paths
- add a single startup capability report and optional CLI command to print it

Expected benefits:

- less API-drift exposure
- fewer `sys.path` mutations
- clearer degraded-mode behavior

### Workstream B: Unified artifact and authority model

Objective: represent all evidence and authorities using one normalized schema.

Add or formalize types for:

- `CaseArtifact`
- `CaseAuthority`
- `CaseFact`
- `CaseClaimElement`
- `CaseSupportEdge`
- `FormalPredicate`
- `ValidationRun`

Important additions:

- canonical `artifact_id`
- canonical `authority_id`
- stable content hash
- CID when available
- claim-element links
- source-system and acquisition-method fields
- parser and extraction version fields

Expected benefits:

- easier deduplication
- better graph joins
- clearer provenance
- better cross-source support analysis

### Workstream C: Search, web archiving, and historical evidence

Objective: treat web search as evidentiary acquisition, not just discovery.

Use `ipfs_datasets_py` capabilities for:

- current web search
- historical archive search
- archive capture
- URL fetch normalization

Add complaint-specific search workflows:

- employer policy history workflow
- public statements workflow
- product or service terms workflow
- agency notice and guidance workflow
- timeline reconstruction workflow

Required improvements:

- capture fetched page text, not just search metadata
- archive important URLs immediately
- cluster duplicates across Brave, Common Crawl, and archive snapshots
- preserve temporal metadata so claims can be tied to what was visible on a specific date

Expected benefits:

- stronger public-evidence capture
- historical proof for policy changes and statements
- better reproducibility for litigation review

### Workstream D: Legal scrapers and legal dataset integration

Objective: move from raw authority search to claim-element-aware legal support.

Use `ipfs_datasets_py` for:

- US Code retrieval
- Federal Register retrieval
- RECAP and case-law retrieval
- future state and procedural rule expansion where available

Required improvements:

- normalize citations across source systems
- rank controlling authority above merely relevant authority
- store jurisdiction, freshness, and authority type explicitly
- link authorities directly to claim elements and procedural requirements
- add conflict analysis for contradictory or weakly aligned authorities

Expected benefits:

- better authority ranking
- better legal graph quality
- stronger claim-element coverage tracking

### Workstream E: Document ingestion and corpus processing

Objective: treat uploaded files and scraped legal materials as parseable, graphable assets.

Add `integrations/ipfs_datasets/documents.py` to expose:

- file type detection
- PDF text extraction
- OCR fallback
- chunking
- metadata extraction
- document-to-text normalization

Integrate into complaint-generator flows:

- uploaded exhibits in `mediator/evidence_hooks.py`
- scraped web pages from `mediator/web_evidence_hooks.py`
- legal authority text in `mediator/legal_authority_hooks.py`

Expected benefits:

- richer fact extraction from exhibits
- chunk-level provenance
- timeline extraction from emails, letters, policies, notices, and filings

### Workstream F: GraphRAG and graph database integration

Objective: use graph extraction and graph storage to organize case material at scale.

Use `ipfs_datasets_py` graph capabilities for:

- entity extraction
- relationship extraction
- cross-document resolution
- graph lineage tracking
- graph querying and storage

Recommended design choice:

Keep `complaint_phases/` as the canonical in-memory case graph API, but add a graph adapter that can persist enriched graph projections into a backing store when available.

Recommended graph database role:

- store cross-document entities and relations
- support provenance-preserving traversal queries
- support graph-centric retrieval for support analysis
- support operator audit and explanation workflows

Queries we should support:

- what artifacts support claim element X
- what authorities cite or imply requirement Y
- what facts are derived from archived policy page Z
- what events mention defendant A across all evidence
- what elements remain unsupported after all known ingestion

Expected benefits:

- much better organization of evidence and law
- explainable support traces
- better retrieval than flat result lists

### Workstream G: Formal logic and theorem proving

Objective: turn legal sufficiency and contradiction checking into a first-class validation step.

Use `ipfs_datasets_py.logic` for:

- FOL translation
- deontic logic for obligations, permissions, prohibitions
- temporal or deontic-temporal reasoning where appropriate
- external prover bridges such as Z3 and CVC5
- optional interactive prover bridges for advanced formalization
- neurosymbolic coordination

Initial complaint-generator use cases:

- translate claim elements into predicates
- translate extracted facts into grounded predicates
- test whether the fact set satisfies required elements
- flag unsupported logical jumps
- flag contradictory timelines or mutually exclusive assertions
- separate direct evidence from inferred support

Required outputs:

- `provable_elements`
- `partially_supported_elements`
- `unprovable_elements`
- `missing_predicates`
- `contradictory_predicates`
- `facts_without_legal_relevance`
- `authorities_without_fact_support`

Expected benefits:

- earlier quality control
- better denoiser questions
- higher confidence final drafts

### Workstream H: Hybrid retrieval and ranking

Objective: combine keywords, embeddings, graph traversal, and authority structure.

The repo already has the right direction in `complaint_analysis/indexer.py`, but that logic should move behind adapters and become case-aware rather than document-local.

Recommended retrieval stack:

- keyword retrieval for domain-specific legal patterns
- vector retrieval for semantic similarity
- graph traversal for support chains
- authority ranking by jurisdiction and precedential weight
- temporal ranking for historical web evidence

Expected benefits:

- higher precision support discovery
- better organization of large evidence collections
- better search UX for operators

### Workstream I: MCP tool gateway

Objective: use the broad `ipfs_datasets_py` MCP surface selectively, not indiscriminately.

Do not wire the whole MCP tool catalog directly into complaint generation.

Instead, add a narrow gateway for background workflows such as:

- legal dataset ingestion
- graph ingestion
- provenance recording
- bulk archive capture
- deontic or logic validation jobs

Use this only for controlled, auditable backend workflows, not for core user-facing orchestration logic.

Expected benefits:

- access to the wider ecosystem without turning mediator logic into tool-routing glue
- easier audit and permission control

## Proposed End-to-End Pipeline

1. Intake captures complaint text and produces initial claim hypotheses.
2. Knowledge and dependency graphs identify key entities, claim types, and missing requirements.
3. Search workflows generate targeted legal and factual acquisition tasks.
4. Web and legal results are fetched, archived, hashed, and stored as artifacts or authorities.
5. Documents and pages are parsed into text, chunks, and metadata.
6. Graph extraction resolves entities, relationships, and cross-document links.
7. Legal authorities are added to the legal graph and linked to claim elements.
8. Facts and legal elements are translated into predicates.
9. Logic validation identifies supported, unsupported, partial, and contradictory elements.
10. The denoiser generates focused follow-up questions from graph and logic gaps.
11. Draft generation uses only supported facts, linked authorities, and clearly marked inferences.
12. Operator review sees a support coverage report, contradiction report, and provenance bundle.

## Recommended Data Model and Storage Extensions

### Core relational tables

Add or standardize DuckDB tables for:

- `artifacts`
- `artifact_transforms`
- `artifact_chunks`
- `authorities`
- `authority_links`
- `case_facts`
- `claim_elements`
- `claim_element_coverage`
- `graph_nodes`
- `graph_edges`
- `predicates`
- `validation_runs`
- `contradictions`

### Provenance fields required everywhere

Every artifact, authority, chunk, graph node, edge, predicate, and validation record should carry:

- source URL or source origin
- acquisition timestamp
- acquisition method
- source system
- content hash
- CID when available
- parser version
- extraction version
- graph ingestion version
- reasoning version

### Claim-element coverage matrix

This should become the central organizational structure for drafting readiness.

Suggested columns:

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
- last validation run ID

## Concrete File-Level Roadmap

### Phase 0: Finish the integration boundary

Outcome: the repo has one stable production integration layer.

Priority files:

- `integrations/ipfs_datasets/capabilities.py`
- `integrations/ipfs_datasets/loader.py`
- `integrations/ipfs_datasets/search.py`
- `integrations/ipfs_datasets/legal.py`
- `integrations/ipfs_datasets/storage.py`
- new `integrations/ipfs_datasets/documents.py`
- new `integrations/ipfs_datasets/graphs.py`
- new `integrations/ipfs_datasets/graphrag.py`
- new `integrations/ipfs_datasets/logic.py`

Tasks:

- add capability reporting for graph, documents, logic, vector, and MCP gateway features
- document supported runtime modes
- move production-only direct imports behind adapters

Success criteria:

- mediator starts cleanly in full, partial, and degraded modes
- capability output is stable and actionable
- no production module needs local `sys.path` mutation to use `ipfs_datasets_py`

### Phase 1: Normalize acquisition and provenance

Outcome: all external material lands in a shared artifact or authority model.

Priority files:

- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`
- `integrations/ipfs_datasets/provenance.py`
- `integrations/ipfs_datasets/types.py`

Tasks:

- unify search and authority normalization
- archive fetched pages before downstream processing when possible
- persist fetched text, metadata, provenance, and claim-element links
- deduplicate by citation, URL, hash, and semantic similarity

Success criteria:

- web evidence and legal authorities share compatible provenance fields
- search results can be traced to stored artifacts
- claim-element links exist for both evidence and authorities

### Phase 2: Add document and parsing services

Outcome: exhibits and fetched pages become parseable inputs to graph and reasoning stages.

Priority files:

- new `integrations/ipfs_datasets/documents.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`

Tasks:

- parse uploaded documents
- parse fetched pages into stable text and chunk records
- extract timeline, entity, and citation candidates
- store chunk lineage

Success criteria:

- evidence ingestion produces reusable text and chunk artifacts
- provenance survives document parsing

### Phase 3: Graph enrichment and graph database persistence

Outcome: complaint, evidence, and legal material share a richer graph substrate.

Priority files:

- new `integrations/ipfs_datasets/graphs.py`
- new `integrations/ipfs_datasets/graphrag.py`
- `complaint_phases/knowledge_graph.py`
- `complaint_phases/dependency_graph.py`
- `complaint_phases/legal_graph.py`
- `complaint_phases/neurosymbolic_matcher.py`

Tasks:

- enrich complaint graphs with extracted entities and support edges
- persist graph projections into a backing graph store when available
- add traversal queries for support and gap analysis
- resolve entities across multiple artifacts and authorities

Success criteria:

- each claim element can enumerate its supporting facts, artifacts, and authorities
- graph-based gap analysis improves denoiser question quality

### Phase 4: Formal validation and theorem proving

Outcome: legal sufficiency and contradiction analysis are machine-assisted.

Priority files:

- new `integrations/ipfs_datasets/logic.py`
- `complaint_phases/neurosymbolic_matcher.py`
- `complaint_phases/legal_graph.py`
- `mediator/mediator.py`

Tasks:

- define predicate templates by claim type
- translate facts and authorities into structured predicates
- run validation passes against legal elements
- store validation artifacts and contradiction reports
- feed logic-derived gaps back into the denoiser

Success criteria:

- unsupported elements are explicitly surfaced before drafting
- contradiction reports are explainable and provenance-backed

### Phase 5: Operator workflows and productization

Outcome: the integration is usable, inspectable, and measurable.

Priority files:

- mediator reporting and convenience APIs
- dashboard surfaces under repo docs or future UI layers
- background job infrastructure

Tasks:

- add support coverage summaries
- add operator-facing evidence and authority review views
- add async jobs for fetch, parse, graph, and validation stages
- add benchmark and adversarial quality suites

Success criteria:

- workflows do not block on long-running tasks
- support coverage and provenance are inspectable
- benchmark quality improves measurably

## Recommended Implementation Order

### First sprint

Deliver:

1. Expanded adapter skeleton for documents, graphs, GraphRAG, and logic.
2. Capability detection for those features.
3. Cleanup of remaining production import boundary violations.
4. Shared relational schema plan for artifacts, authorities, chunks, coverage, and validation.

This sprint is primarily infrastructural.

### Second sprint

Deliver:

1. Search and archive normalization.
2. Document parsing for uploaded files and fetched pages.
3. Deduplicated artifact persistence with provenance.
4. Claim-element-aware authority linking.

This sprint turns acquisition into structured organization.

### Third sprint

Deliver:

1. Graph enrichment pipeline.
2. Cross-document entity resolution.
3. Graph traversal APIs for support analysis.
4. Coverage matrix generation.

This sprint makes organization and retrieval materially better.

### Fourth sprint

Deliver:

1. Predicate generation.
2. Formal validation.
3. Contradiction reporting.
4. Draft-readiness scoring.

This sprint makes theorem-proving and logic operational.

## Testing Plan

### Unit tests

- capability detection in full, partial, and degraded modes
- adapter normalization for search, archive, authority, and parsing outputs
- provenance generation and merge behavior
- content hash and deduplication logic
- predicate generation from claim elements and facts
- contradiction classification logic

### Integration tests

- upload exhibit -> store -> parse -> graph -> validate
- web search -> fetch -> archive -> store -> graph link
- legal search -> normalize -> link -> legal graph update
- complaint facts -> predicates -> proof report
- degraded mode behavior when graph or logic extras are absent

### Benchmark and quality tests

- support coverage per complaint type
- authority precision and ranking quality
- duplicate clustering quality
- contradiction detection accuracy
- historical evidence retrieval quality
- question quality improvements after graph and logic integration

### Adversarial harness additions

Add scenarios for:

- evidence exists but authorities are weak
- authorities exist but facts are missing
- archived content conflicts with live content
- multiple authorities imply different procedural standards
- contradictory factual narratives from different exhibits

## Risks and Mitigations

### Risk: `ipfs_datasets_py` API drift

Mitigation:

- adapter-only production imports
- compatibility tests against expected module paths
- pinned submodule commit guidance for stable releases

### Risk: optional extras create partial capability ambiguity

Mitigation:

- explicit capability map with degraded reasons
- clear feature gating at mediator and hook boundaries

### Risk: graph and logic layers become opaque

Mitigation:

- store intermediate outputs
- persist provenance everywhere
- expose explanations, not only numeric scores

### Risk: too much reliance on inferred facts

Mitigation:

- label direct evidence vs inferred support
- fail closed on unsupported mandatory elements
- require traceability for final draft assertions

### Risk: long-running workflows block user interactions

Mitigation:

- move fetch, parse, graph, and validation tasks to background jobs
- surface job status and partial results back to mediator

## Success Metrics

We should consider the integration successful when complaint-generator can measure and improve the following:

- average supported claim elements per complaint
- unsupported element count before draft completion
- contradictions detected before final draft
- number of artifacts and authorities linked per claim element
- provenance completeness rate
- duplicate reduction across evidence sources
- time to produce a reviewable authority packet
- time to produce a reviewable exhibit bundle

## Desired End State

At the end of this roadmap, complaint-generator should use `ipfs_datasets_py` as a disciplined subsystem for research, storage, graph enrichment, archival evidence, search, and formal validation.

The system should be able to:

- discover and archive current and historical web evidence
- search and normalize legal authorities across multiple sources
- parse documents and web pages into reusable structured content
- organize artifacts, facts, authorities, and predicates into connected graphs
- use graph database and GraphRAG techniques to improve retrieval and explanation
- use theorem-proving and logic validation to assess sufficiency and contradictions
- generate complaints whose assertions are traceable to evidence and law

That is the highest-value integration path for `ipfs_datasets_py` inside complaint-generator: not a loose set of imports, but an information-organization and validation backbone for verifiable legal complaint generation.