# Claim Support Review Dashboard Execution Backlog

Date: 2026-03-14
Status: Active execution backlog

Companion docs:

- `docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_IMPROVEMENT_PLAN.md`
- `docs/PAYLOAD_CONTRACTS.md`
- `docs/APPLICATIONS.md`
- `docs/IPFS_DATASETS_PY_DEPENDENCY_MAP.md`

## Purpose

Translate the Claim Support Review Dashboard improvement roadmap into implementation-sized work packages tied to the current state of complaint-generator.

This backlog assumes the repo already has:

- an operator-facing `/claim-support-review` dashboard
- persisted claim-support review state and follow-up history
- a normalized document parse contract under `integrations/ipfs_datasets/documents.py`
- lightweight graph extraction and graph-gap detection
- a placeholder but stable logic adapter seam

The goal now is not to redesign the system abstractly. The goal is to deliver a testimony-to-proof workflow in thin vertical slices that improve question quality, evidence quality, legal explainability, and drafting readiness.

## Execution Principles

1. Keep `integrations/ipfs_datasets/` as the only production boundary to `ipfs_datasets_py`.
2. Treat testimony, uploaded documents, archived pages, and authorities as one evidence substrate.
3. Ask questions only when they improve legal proof state or resolve contradictions.
4. Preserve degraded-mode behavior when graphs, embeddings, or logic tooling are unavailable.
5. Prefer persistent, reviewable artifacts over transient in-memory outputs.
6. Make every element status explainable with concrete facts, chunks, authorities, or proof diagnostics.

## Current Baseline

## Completed or substantially in place

- `/claim-support-review` already exposes coverage summaries, support gaps, contradiction candidates, follow-up summaries, and manual review actions
- `complaint_phases/denoiser.py` can already generate gap-driven questions from graph state
- `complaint_phases/knowledge_graph.py` can already identify unsupported claims, isolated entities, and timeline gaps
- `mediator/claim_support_hooks.py` already persists claim requirements, support links, support snapshots, and follow-up execution history
- `integrations/ipfs_datasets/documents.py` already exposes normalized parse outputs, chunking, quality signals, and transform lineage
- `integrations/ipfs_datasets/graphs.py` already exposes lightweight graph extraction and support clustering
- `integrations/ipfs_datasets/logic.py` already defines the proof contract even though execution is still mostly placeholder

## Still shallow or incomplete

- the dashboard is still review-first rather than guided testimony-first
- testimony is not yet a durable structured record family
- dashboard document intake is not yet a first-class workflow
- there is no canonical fact registry spanning testimony, chunks, authorities, and predicates
- graph snapshots and support-path queries are still limited
- vector retrieval is not yet a first-class review plane for claim elements
- logic proofs and contradiction explanations are not yet implemented behind the existing adapter contract
- the dashboard does not yet present a canonical facts-applied-to-law card per element

## Status Legend

- `Complete`: implemented enough to be treated as baseline
- `In Progress`: partially implemented and actively extendable
- `Planned`: designed but not yet implemented
- `Validation Required`: implemented checklist items exist, but the supervisor should still run the listed validation commands before treating the slice as closed
- `Deferred`: useful but lower priority than the current roadmap

## Workstream Overview

| ID | Workstream | Status | Priority | Outcome |
|---|---|---|---|---|
| W1 | Question planning and testimony intake | Complete | P0 | The dashboard becomes a guided clarification surface tied to legal proof gaps |
| W2 | Document intake and decomposition | Complete | P0 | Uploaded or linked materials become reusable parsed evidence artifacts |
| W3 | Fact registry and support ledger | Complete | P0 | Every element status can be traced to durable fact and chunk records |
| W4 | Graph persistence and support paths | Complete | P1 | Support and contradiction paths become reusable and queryable |
| W5 | Retrieval sessions and evidence ranking | Complete | P1 | Operators can inspect the best chunks and why they were selected |
| W6 | Legal proof and contradiction engine | Complete | P0 | Facts can be evaluated against legal predicates, exceptions, and contradictions |
| W7 | Operator experience and drafting integration | Validation Required | P1 | The dashboard becomes the canonical evidence-readiness workflow feeding `/document` |

## M0: Question And Testimony Foundation

Status: Complete
Priority: P0

### Goal

Make `/claim-support-review` a guided intake and clarification workflow instead of only a post-hoc coverage dashboard.

### Primary files

- `templates/claim_support_review.html`
- `mediator/claim_support_hooks.py`
- `complaint_phases/denoiser.py`
- `complaint_phases/knowledge_graph.py`
- `complaint_phases/dependency_graph.py`
- `docs/PAYLOAD_CONTRACTS.md`
- `docs/APPLICATIONS.md`

### Checklist

- [x] add question recommendation payloads with `question_id`, `target_claim_element_id`, `question_lane`, `question_reason`, and `expected_proof_gain`
- [x] rank questions by unresolved legal value, contradiction impact, and evidentiary weakness
- [x] distinguish testimony questions from document-request questions
- [x] add a structured testimony composer with event date, actor, act, target, harm, confidence, and firsthand status
- [x] preserve raw narrative alongside structured testimony extraction preview
- [x] persist testimony records and revisions through mediator-backed storage
- [x] link testimony items to candidate claim elements before or at save time
- [x] surface testimony-backed support counts in existing coverage summaries

### Acceptance criteria

- every recommended question maps to at least one unresolved element, contradiction, or gap
- testimony can be stored as raw narrative plus structured facts
- the review payload can show which testimony records support which claim elements
- the default dashboard view shows why a question is being asked and what element it targets

### Degraded mode expectations

- if advanced ranking features are unavailable, the system still emits deterministic gap-based questions
- if structured extraction fails, raw narrative is still preserved and reviewable

### Validation

- focused unit tests for question ranking and testimony normalization
- integration tests for question answer -> testimony save -> coverage refresh
- browser tests for testimony entry, edit, and save workflows

### Suggested focused validation

- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q`
- `./.venv/bin/python -m pytest tests/test_review_api.py -q`
- `./.venv/bin/python -m pytest tests/test_review_surface.py -q`

## M1: Document Intake And Decomposition Plane

Status: Complete
Priority: P0

### Goal

Make uploaded or linked materials first-class evidence artifacts routed through one parse contract.

### Primary files

- `templates/claim_support_review.html`
- `integrations/ipfs_datasets/documents.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/claim_support_hooks.py`
- `docs/PAYLOAD_CONTRACTS.md`

### Checklist

- [x] add dashboard document upload and URL intake controls
- [x] route dashboard-ingested materials through `integrations/ipfs_datasets/documents.py`
- [x] persist parse summary, transform lineage, chunk references, and remediation flags
- [x] expose chunk previews, page or span provenance, and parse-quality indicators in review payloads
- [x] add reparsing or OCR retry actions for low-quality document parses
- [x] link created artifacts to claim-support context and testimony threads where applicable

### Acceptance criteria

- uploaded or linked documents produce normalized parse records and chunk references
- every chunk has stable provenance back to artifact and source span or page
- low-quality parses are visible in the dashboard with explicit remediation guidance
- newly created artifacts can be attached to claim elements without custom manual shaping

### Degraded mode expectations

- if advanced parse helpers are unavailable, the dashboard still stores the artifact and marks parse status clearly
- low-confidence or partial parse outputs still remain reviewable rather than silently discarded

### Validation

- focused parse tests for dashboard-ingested documents
- integration tests for upload -> parse -> persisted artifact -> review payload
- browser tests for upload feedback and parse-quality panels

### Suggested focused validation

- `./.venv/bin/python -m pytest tests/test_evidence_hooks.py -q`
- `./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py -q`
- `./.venv/bin/python -m pytest tests/test_review_api.py -q`

## M2: Fact Registry And Element Support Ledger

Status: Complete
Priority: P0

### Goal

Create one durable substrate for testimony facts, document facts, authority facts, and their claim-element links.

### Primary files

- `mediator/claim_support_hooks.py`
- `integrations/ipfs_datasets/types.py`
- `integrations/ipfs_datasets/provenance.py`
- `docs/PAYLOAD_CONTRACTS.md`
- `templates/claim_support_review.html`

### Checklist

- [x] formalize durable fact records with source artifact, chunk or span, proposition text, confidence, and validation state
- [x] add fact-to-element, fact-to-authority, and fact-to-testimony link records
- [x] normalize uncertainty and contradiction flags on facts
- [x] add stable support-packet or proof-path identifiers for review drilldowns
- [x] expose an element support ledger in the review payload keyed by concrete fact IDs
- [x] ensure dashboard summaries can be recomputed from persisted fact records instead of transient parser outputs

### Acceptance criteria

- every element status can be explained by concrete fact IDs and their linked sources
- facts can be traced to testimony, document chunks, or authorities without re-parsing
- support ledgers are stable enough to support review replay and `/document` handoff

### Degraded mode expectations

- if advanced extraction is limited, manually entered testimony facts still populate the ledger
- if some provenance fields are unavailable, the payload distinguishes missing provenance from missing support

### Validation

- unit tests for fact record normalization and support-ledger assembly
- integration tests for testimony and document facts appearing in one review payload
- regression tests for payload compatibility on existing dashboard consumers

### Suggested focused validation

- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q`
- `./.venv/bin/python -m pytest tests/test_payload_contracts.py -q`

## M3: Graph Snapshot Persistence And Support Paths

Status: Complete
Priority: P1

### Goal

Make support paths queryable and reusable across review, follow-up, and drafting workflows.

### Primary files

- `integrations/ipfs_datasets/graphs.py`
- `complaint_phases/knowledge_graph.py`
- `complaint_phases/dependency_graph.py`
- `mediator/claim_support_hooks.py`
- `templates/claim_support_review.html`

### Checklist

- [x] persist testimony, evidence, and law-adjacent graph snapshots with stable IDs
- [x] add query helpers for support-path and contradiction-path lookups per element
- [x] resolve duplicate or near-duplicate actors and entities across testimony and document graphs
- [x] attach provenance edges from facts to chunks and chunks to artifacts
- [x] expose graph snapshot references and support-path summaries in review payloads

### Acceptance criteria

- each claim element can show a graph-backed support path
- review flows can reuse persisted graph snapshots instead of recomputing the world each time
- entity resolution materially reduces duplicate person or document nodes across sources

### Degraded mode expectations

- if graph persistence is unavailable, the system still emits clear fallback support summaries
- graph failures do not block testimony, document intake, or support-ledger persistence

### Validation

- graph adapter tests for snapshot persistence and path queries
- claim-support integration tests for graph-backed review payload fields
- regression tests for support-path drilldowns in dashboard payloads

### Suggested focused validation

- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q`
- `./.venv/bin/python -m pytest tests/test_review_api.py -q`

## M4: Retrieval Sessions And Evidence Ranking

Status: Complete
Priority: P1

### Goal

Make chunk retrieval a first-class review tool for question planning, contradiction resolution, and operator explanation.

### Primary files

- `integrations/ipfs_datasets/vector_store.py`
- `integrations/ipfs_datasets/documents.py`
- `mediator/claim_support_hooks.py`
- `templates/claim_support_review.html`
- `docs/PAYLOAD_CONTRACTS.md`

### Checklist

- [x] index testimony and document chunks in one retrieval plane
- [x] add claim-element-scoped retrieval sessions with stable session IDs
- [x] expose retrieval explanations, scores, and duplicate-cluster hints in the review payload
- [x] use retrieval context to improve question recommendations and follow-up planning
- [x] store enough retrieval metadata to replay or debug a review session

### Acceptance criteria

- operators can inspect the top retrieved chunks for a claim element and see why they ranked highly
- retrieval sessions are replayable enough for diagnostics and regression tests
- question recommendations can cite retrieval context rather than generic gap labels alone

### Degraded mode expectations

- if embeddings or vector search are unavailable, the dashboard falls back to graph and fact-ledger summaries
- retrieval failure surfaces as explicit status rather than silently empty results

### Validation

- focused vector-store tests for claim-element retrieval sessions
- integration tests for retrieval results flowing into review payloads and question recommendations
- browser tests for retrieval drilldowns and duplicate or conflict hints

### Suggested focused validation

- `./.venv/bin/python -m pytest tests/test_m4_retrieval_sessions.py -q`
- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q`

## M5: Legal Proof And Contradiction Engine

Status: Complete
Priority: P0

### Goal

Turn coverage review into facts-applied-to-law validation with proof gaps, exception triggers, and contradiction explanations.

### Primary files

- `integrations/ipfs_datasets/logic.py`
- `integrations/ipfs_datasets/graphrag.py`
- `mediator/claim_support_hooks.py`
- `complaint_phases/legal_graph.py`
- `complaint_phases/neurosymbolic_matcher.py`
- `templates/claim_support_review.html`
- `docs/PAYLOAD_CONTRACTS.md`

### Checklist

- [x] implement `prove_claim_elements` behind the existing adapter contract
- [x] implement contradiction and exception checks with concise proof explanations
- [x] normalize law-element, predicate, and authority-rule references used by proof results
- [x] distinguish missing support, contradiction, exception-barred, and uncertain states per element
- [x] expose element proof cards with required predicates, satisfied predicates, missing predicates, supporting facts, contradiction sources, and next action
- [x] feed proof-state outputs back into question planning and follow-up planning

### Acceptance criteria

- the review payload can state whether an element is supported, partially supported, missing, contradicted, uncertain, or exception-barred
- each proof result includes a concise explanation tied to facts, authorities, or failed predicates
- the dashboard shows facts applied to law rather than only support counts or cluster summaries

### Degraded mode expectations

- if executable proof tooling is unavailable, the payload still preserves rule-shaped placeholders and clear capability status
- proof engine failures do not erase support-ledger, graph, or retrieval results already available

### Validation

- unit tests for proof-gap classification and contradiction handling
- integration tests for authority -> predicate -> proof-card review payloads
- curated fixture tests for contradiction precision and false-positive control

### Suggested focused validation

- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q`
- `./.venv/bin/python -m pytest tests/test_probate_integration.py -q`

## M6: Operator Productization And `/document` Handoff

Status: Validation Required
Priority: P1

### Goal

Make `/claim-support-review` the canonical operator workflow for legal readiness and drafting handoff.

### Primary files

- `templates/claim_support_review.html`
- `templates/document.html`
- `mediator/claim_support_hooks.py`
- `applications/server.py`
- `docs/APPLICATIONS.md`
- `docs/PAYLOAD_CONTRACTS.md`

### Checklist

- [x] redesign the dashboard into clear sections for Questions, Testimony, Documents, Facts, Graph, Law, and Actions
- [x] add per-element proof cards with visible next actions and drilldowns
- [x] preserve deep-link context from `/document` into claim and section review state
- [x] make drafting warnings and readiness summaries reference concrete proof cards and support ledgers
- [x] ensure heavy processing steps can be queued without breaking the interactive dashboard

### Acceptance criteria

- operators can move from question intake to testimony, documents, proof review, and drafting impact without changing workflows
- unresolved elements always expose a visible next action
- `/document` consumes the same validated support state used in dashboard proof review

### Degraded mode expectations

- the dashboard remains usable even when some advanced tabs have reduced capabilities
- deep-link handoff to `/document` still preserves claim and section context without requiring proof tooling
- document handoff still emits reviewable DOCX artifacts with pleading, affidavit, section-heading, factual-group, open-gap, and support-handoff text when the optional styled DOCX renderer dependency is unavailable

### Validation

- browser tests for end-to-end operator flows
- integration tests for `/claim-support-review` -> `/document` context preservation
- regression tests for payload compatibility and heavy-processing queue fallbacks

### Suggested focused validation

- `./.venv/bin/python -m pytest tests/test_document_pipeline.py -q`
- `./.venv/bin/python -m pytest tests/test_review_api.py -q`

## Delivery Order

1. M0 before everything else because question quality and testimony quality are the highest-leverage improvements.
2. M1 next so testimony can be paired with normalized supporting materials.
3. M2 before deep proof work so every later explanation rests on durable fact records.
4. M3 and M4 can proceed in parallel once M2 is stable because both depend on durable facts and artifacts.
5. M5 should begin only after the support ledger and at least minimal graph or retrieval context are reliable.
6. M6 finishes the product workflow after proof outputs are stable enough to surface in operator-facing cards.

## Recommended First Slice

Implement the smallest useful vertical slice inside M0:

- add element-targeted question recommendations
- add structured testimony capture to `/claim-support-review`
- persist testimony as fact-like records linked to claim elements
- surface testimony-backed support counts in existing coverage summaries

That slice improves question quality and evidence quality immediately without waiting for full document, retrieval, or proof infrastructure.
