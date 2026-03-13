# IPFS Datasets Py File Worklist

Date: 2026-03-12

## Purpose

Translate the `ipfs_datasets_py` milestone plan into file-by-file implementation targets for the earliest milestones.

This is the most execution-oriented companion to:

- `docs/IPFS_DATASETS_PY_INTEGRATION.md`
- `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md`
- `docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md`
- `docs/IPFS_DATASETS_PY_DEPENDENCY_MAP.md`
- `docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md`
- `docs/IPFS_DATASETS_PY_BATCH1_STATUS_AUDIT.md`

Use this document when selecting the next coding slice.

## Scope

This worklist focuses on the highest-value milestones that currently have clear implementation targets:

- M0: Adapter and capability hardening
- M1: Shared parse and corpus contract
- M2: Persistent support and graph query plane
- M4: Operator productization
- M5: Drafting and filing readiness

M3 remains downstream of stabilized parse, support, and graph contracts, but M4 and M5 now have concrete application-layer entrypoints that can be prepared in parallel once their input payloads are stable.

## M0 File Worklist

### `integrations/ipfs_datasets/capabilities.py`

Tasks:

- normalize capability payload shapes across documents, graphs, GraphRAG, logic, vector store, and MCP gateway
- ensure every capability report includes explicit availability plus degraded reason fields
- expose one stable summary helper for mediator and diagnostics surfaces

Done when:

- capability payloads are structurally consistent across adapters
- mediator can render one stable capability summary without adapter-specific branching

Validation:

- focused capability tests
- `./.venv/bin/python -m pytest tests/test_ipfs_adapter_layer.py tests/test_ipfs_adapter_types.py -q`

### `integrations/ipfs_datasets/loader.py`

Tasks:

- centralize import probing behavior
- reduce duplicate per-adapter import-failure handling where practical
- ensure upstream layout drift is reflected as degraded capability output, not import crashes

Done when:

- adapter imports fail closed into explicit degraded status

Validation:

- degraded-mode adapter tests
- `./.venv/bin/python -m pytest tests/test_ipfs_adapter_layer.py -q`

### `integrations/ipfs_datasets/legal.py`

Tasks:

- confirm sync wrapper behavior is consistent across legal scrapers
- normalize degraded and success payloads to one contract family
- isolate any remaining upstream-path assumptions behind adapter functions only

Done when:

- legal acquisition does not leak upstream path or shape differences into mediator hooks

Validation:

- focused legal adapter tests
- `./.venv/bin/python -m pytest tests/test_ipfs_adapter_layer.py -q`

### `integrations/ipfs_datasets/search.py`

Tasks:

- normalize capability and degraded output semantics with other adapters
- keep current-web, archive, and Common Crawl entrypoints aligned on result shapes
- prepare archive metadata fields for M1 and M2 ingestion work

Done when:

- mediator search consumers can rely on one stable result family across acquisition modes

Validation:

- focused search adapter tests
- `./.venv/bin/python -m pytest tests/test_ipfs_adapter_layer.py tests/test_search_hooks.py -q`

### `integrations/ipfs_datasets/graphs.py`

Tasks:

- align capability and degraded responses with the other adapters before deeper graph work starts
- isolate current fallback extraction semantics behind explicit contracts

Done when:

- graph adapter can be safely deepened in M2 without changing caller assumptions twice

Validation:

- focused graph adapter tests
- `./.venv/bin/python -m pytest tests/test_ipfs_adapter_layer.py tests/test_claim_support_hooks.py -q`

### `integrations/ipfs_datasets/logic.py`

Tasks:

- normalize placeholder and degraded payloads so later proof work can evolve without breaking callers

Done when:

- logic adapter exposes stable not-yet-implemented contracts rather than ad hoc placeholders

Validation:

- focused logic adapter degraded-mode tests
- add a dedicated focused logic-adapter test before starting proof workflow work

### `mediator/mediator.py`

Tasks:

- consume the shared capability summary consistently
- remove any direct dependency on upstream module-path quirks

Done when:

- mediator startup behaves the same across full, partial, and degraded environments

Validation:

- startup smoke tests or focused mediator tests
- `./.venv/bin/python -m pytest tests/test_review_api.py tests/test_claim_support_hooks.py -q`

## M1 File Worklist

Status:

- the shared parse contract, typed parse models, and provenance-aligned storage metadata are implemented and validated for evidence, web evidence, and legal authority ingestion

### `integrations/ipfs_datasets/documents.py`

Tasks:

- make one canonical parse contract for bytes, files, and fetched page content
- standardize parse summary, chunk metadata, MIME handling, and transform lineage
- fully encapsulate PDF, DOCX, RTF, HTML, email, and office-document parsing differences behind the adapter layer
- preserve degraded behavior when OCR or PDF extras are unavailable

Current state:

- completed for bytes, files, and web-evidence payload construction; focused adapter and ingestion suites are green

Done when:

- downstream consumers can call one parse API regardless of source family
- downstream consumers do not branch on document format outside the adapter layer

Validation:

- focused parse tests for text, HTML, and PDF where supported
- `./.venv/bin/python -m pytest tests/test_evidence_hooks.py -q`

### `integrations/ipfs_datasets/types.py`

Tasks:

- formalize shared parse-result and corpus-oriented types
- align evidence, authority, and archived-page fields needed by graph and logic consumers

Current state:

- completed for parse chunks, parse summaries, transform lineage, and parse result serialization

Done when:

- parse, fact, and support records share compatible shape expectations

Validation:

- type-shape regression tests where practical
- `./.venv/bin/python -m pytest tests/test_ipfs_adapter_types.py -q`

### `integrations/ipfs_datasets/provenance.py`

Tasks:

- standardize provenance fields for uploaded evidence, discovered web evidence, and legal authority text
- carry parser, extraction, and transform lineage metadata forward in one format

Current state:

- completed for stored parse metadata and document-parse summary metadata via shared provenance helpers
- completed for durable provenance metadata across evidence, archived web evidence, and legal authorities
- completed for claim-support packet and trace summary fallback to provenance-backed normalized record summaries

Done when:

- source lineage survives across storage, parse, fact, and review stages

Validation:

- focused provenance tests
- `./.venv/bin/python -m pytest tests/test_evidence_hooks.py tests/test_legal_authority_hooks.py -q`

### `mediator/evidence_hooks.py`

Tasks:

- remove hook-local parse-shape assumptions in favor of the shared document contract
- preserve parse summaries, chunk rows, facts, and graph metadata using the canonical parse family
- ensure evidence payloads surface consistent lineage fields

Current state:

- completed for evidence ingestion and DuckDB persistence paths; parse metadata now comes from the shared provenance helper

Done when:

- uploaded evidence ingestion uses the same parse semantics as the rest of the corpus pipeline

Validation:

- focused evidence-hook tests
- `./.venv/bin/python -m pytest tests/test_evidence_hooks.py -q`

### `mediator/web_evidence_hooks.py`

Tasks:

- route fetched and discovered page content through the shared parse contract
- preserve archive or fetch provenance in the same lineage model as uploaded evidence
- preserve enough timeline and archive metadata for later operator history and comparison views

Current state:

- completed through evidence-hook storage reuse with explicit `parse_source='web_document'` and request-level parse reporting
- completed for durable archive provenance metadata in stored web evidence and review-facing lineage summaries
- ensure review and follow-up payloads can distinguish live fetches from archived captures

Done when:

- web evidence ingestion is corpus-compatible with uploaded evidence rather than a special case

Validation:

- focused web-evidence tests
- `./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py -q`

### `mediator/legal_authority_hooks.py`

Tasks:

- ensure authority text parsing uses the same parse family when full text exists
- preserve authority parse summaries, chunks, facts, and graph metadata through one normalized contract
- align authority provenance with evidence and archived pages
- capture passage-level provenance needed for future contradiction, support-path, and predicate review

Current state:

- completed for durable provenance metadata distinguishing full-text corpus assets from citation-only fallback records
- completed for propagation of normalized authority source-context metadata into downstream fact, treatment, and rule-candidate provenance clones

Done when:

- legal authorities become corpus assets, not citation-only records, whenever text is available

Validation:

- focused authority-hook tests
- `./.venv/bin/python -m pytest tests/test_legal_authority_hooks.py -q`

## M2 File Worklist

Status:

- the adapter now exposes typed graph payload, graph snapshot, and graph-support result contracts, and created-versus-reused snapshot semantics now flow through evidence, authority, and mediator graph-projection payloads

### `integrations/ipfs_datasets/graphs.py`

Tasks:

- add graph snapshot persistence contracts behind the adapter boundary
- expose support-tracing query entrypoints for claim-element review
- preserve duplicate and semantic-cluster context in support-query results

Current state:

- completed for adapter-visible graph payload, graph snapshot, and graph-support result contracts while preserving the existing dict payload family consumed by mediator callers
- duplicate and semantic-cluster support summaries remain available and are now part of the typed adapter result contract
- created-versus-reused snapshot semantics are now emitted by `persist_graph_snapshot(...)` and threaded into storage metadata plus mediator `graph_projection` payloads

Done when:

- the graph adapter can persist and query support structure without callers reaching into upstream internals

Validation:

- focused graph persistence and query tests
- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py tests/test_review_api.py -q`

### `mediator/claim_support_hooks.py`

Tasks:

- deepen existing unified fact views into support-tracing responses
- expose artifact, authority, fact, and graph-support traces for a claim element
- prepare coverage-matrix semantics for mediator and review consumers

Current state:

- claim-support links and derived fact rows now carry `graph_trace` packets combining source-table identity, record id, graph summary, adapter snapshot semantics, and stored lineage metadata from evidence and authority `graph_metadata`
- review-facing `claim_coverage_summary` payloads now aggregate those traces into compact `graph_trace_summary` counts for graph ids, source tables, statuses, and snapshot creation-versus-reuse

Done when:

- claim support is queryable as a provenance-backed support structure rather than only aggregated counts

Validation:

- focused claim-support tests
- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q`

### `mediator/evidence_hooks.py`

Tasks:

- retain lineage from evidence records into graph snapshots and support traces

Done when:

- evidence-derived support can be traced from stored artifact to graph representation

Validation:

- focused evidence and graph-projection tests
- `./.venv/bin/python -m pytest tests/test_evidence_hooks.py -q`

### `mediator/web_evidence_hooks.py`

Tasks:

- expose graph-backed support traces and archive-context semantics in web evidence review payloads

Done when:

- web evidence support can be reviewed with both source and graph context

Validation:

- focused web-evidence and follow-up tests
- `./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py -q`

### `mediator/legal_authority_hooks.py`

Tasks:

- retain authority-to-graph and authority-to-support lineage in persisted outputs

Done when:

- authority-backed support traces are queryable and reviewable

Validation:

- focused legal-authority tests
- `./.venv/bin/python -m pytest tests/test_legal_authority_hooks.py -q`

### `mediator/mediator.py`

Tasks:

- expose graph-backed support queries and coverage-matrix semantics through stable review calls

Done when:

- mediator review flows can explain covered, partial, and missing claim elements with support traces

Validation:

- focused mediator and review tests
- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py tests/test_review_api.py -q`

### `complaint_phases/knowledge_graph.py`

Tasks:

- align graph snapshot identifiers and lineage semantics with adapter contracts

Done when:

- graph projection and graph persistence share compatible identifiers and timestamps

Validation:

- focused graph-state tests if needed
- `./.venv/bin/python -m pytest tests/test_evidence_hooks.py tests/test_claim_support_hooks.py -q`

### `complaint_phases/dependency_graph.py`

Tasks:

- ensure support-tracing and coverage semantics can map onto dependency relationships cleanly

Done when:

- dependency relationships can be reused by support-query and coverage reporting flows

Validation:

- focused dependency or coverage tests if needed
- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py tests/test_review_api.py -q`

## Slice Selection Rules

- prefer a vertical slice that touches one adapter plus one mediator consumer plus one focused test module
- do not start GraphRAG or theorem-prover work until the M1 and M2 contracts are stable
- when in doubt, pick the next slice that improves operator-visible support explanation rather than only internal plumbing

## M4 File Worklist

### `applications/review_api.py`

Tasks:

- expose richer support-packet drilldown without forcing callers to reconstruct provenance, graph, and validation context client-side
- keep compact summary payloads stable while adding drilldown-ready companions

Done when:

- review clients can retrieve one claim element with enough detail to explain support, contradiction, provenance, and follow-up rationale

Validation:

- focused review API tests
- `./.venv/bin/python -m pytest tests/test_review_api.py -q`

### `claim_support_review.py`

Tasks:

- produce support-packet, contradiction-packet, and timeline-ready summary helpers
- keep packet ordering and compatibility semantics explicit in compact payloads

Done when:

- operator surfaces can depend on stable drilldown-oriented helpers instead of rebuilding packet logic in templates or API handlers

Validation:

- focused review and dashboard tests
- `./.venv/bin/python -m pytest tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py -q`

### `mediator/mediator.py`

Tasks:

- expose stable review and follow-up entrypoints that can be reused by the dashboard and future drafting workflow

Done when:

- application surfaces do not need direct table knowledge to assemble support-review state

Validation:

- focused mediator and review tests
- `./.venv/bin/python -m pytest tests/test_review_api.py tests/test_claim_support_hooks.py -q`

## M5 File Worklist

### `document_pipeline.py`

Tasks:

- consume section-level support bundles rather than relying only on intake and legacy generated-complaint state
- add drafting-warning objects for unsupported facts, adverse authority, weak treatment confidence, and proof gaps
- keep artifact rendering backward compatible for clients that only care about DOCX or PDF output

Done when:

- the document builder can explain which sections are grounded, weak, or blocked before rendering artifacts

Validation:

- focused document-pipeline tests
- `./.venv/bin/python -m pytest tests/test_document_pipeline.py -q`

### `applications/document_api.py`

Tasks:

- expose section readiness and warning metadata in the formal complaint API response
- keep download-link behavior confined to managed artifact directories

Done when:

- API consumers can render drafting readiness without inspecting unrelated review endpoints first

Validation:

- focused document API and review-surface tests
- `./.venv/bin/python -m pytest tests/test_document_pipeline.py -q`

### `templates/document.html`

Tasks:

- render section readiness, drafting warnings, and artifact provenance in a browser-friendly shape
- preserve the existing builder workflow while making support-aware drafting inspectable before export

Done when:

- operators can see where a complaint draft is strong, weak, or blocked directly in the browser builder

Validation:

- focused document template and workflow tests
- `./.venv/bin/python -m pytest tests/test_claim_support_review_template.py tests/test_document_pipeline.py -q`

### `docs/PAYLOAD_CONTRACTS.md`

Tasks:

- document the contract for document section readiness, drafting warnings, and support-bundle metadata

Done when:

- document-workflow payloads are versioned and understandable without reading implementation code

Validation:

- doc updates alongside focused workflow tests

### `docs/APPLICATIONS.md`

Tasks:

- document the browser builder and export workflow as a support-aware drafting surface rather than only an artifact generator

Done when:

- operator docs explain how `/document` relates to claim-support review and export APIs

Validation:

- doc updates alongside focused workflow tests

## Recommended First Coding Slice

1. `integrations/ipfs_datasets/documents.py`
2. `integrations/ipfs_datasets/provenance.py`
3. `mediator/web_evidence_hooks.py`
4. `mediator/legal_authority_hooks.py`
5. focused web-evidence and legal-authority tests

This is the best first slice because it closes the remaining parse and provenance drift for the two source families most likely to fragment the shared corpus contract: archived pages and authority text.