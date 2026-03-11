# IPFS Datasets Py Milestone Checklist

Date: 2026-03-11

## Purpose

Turn the `ipfs_datasets_py` roadmap into a milestone-by-milestone execution checklist with concrete file targets, acceptance criteria, and validation expectations.

Use this with:

- `docs/IPFS_DATASETS_PY_INTEGRATION.md`
- `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md`
- `docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md`
- `docs/IPFS_DATASETS_PY_DEPENDENCY_MAP.md`
- `docs/IPFS_DATASETS_PY_CAPABILITY_MATRIX.md`

## How To Use This Checklist

- treat each milestone as a release-quality integration slice, not a loose theme
- do not start a later milestone until the earlier milestone exposes stable mediator-visible outputs
- keep `integrations/ipfs_datasets/` as the only production boundary to `ipfs_datasets_py`
- require degraded-mode behavior and focused tests for every milestone

## M0: Adapter and Capability Hardening

Goal:

- stabilize runtime-mode handling and eliminate production import drift before deepening parsing, graphs, or reasoning

Primary files:

- `integrations/ipfs_datasets/capabilities.py`
- `integrations/ipfs_datasets/loader.py`
- `integrations/ipfs_datasets/legal.py`
- `integrations/ipfs_datasets/search.py`
- `integrations/ipfs_datasets/graphs.py`
- `integrations/ipfs_datasets/logic.py`
- `mediator/mediator.py`

Checklist:

- [ ] capability entries are stable for documents, knowledge graphs, GraphRAG, logic tools, vector store, and MCP gateway
- [ ] degraded-reason payloads use a consistent shape across adapters
- [ ] mediator startup logs one consistent capability summary across full, partial, and degraded modes
- [ ] no production module imports `ipfs_datasets_py` internals directly outside `integrations/ipfs_datasets/`
- [ ] direct production `sys.path` mutation is removed or explicitly isolated to tests only

Acceptance criteria:

- complaint-generator starts cleanly with or without optional `ipfs_datasets_py` extras
- missing features degrade into explicit capability payloads rather than import errors

Validation:

- focused adapter tests for capability payloads
- mediator startup smoke checks
- targeted search to confirm no direct production imports remain

## M1: Shared Parse and Corpus Contract

Goal:

- make `documents.py` the canonical parse layer for uploaded evidence, archived pages, and legal texts

Primary files:

- `integrations/ipfs_datasets/documents.py`
- `integrations/ipfs_datasets/types.py`
- `integrations/ipfs_datasets/provenance.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`

Checklist:

- [ ] `documents.py` accepts raw bytes, file paths, and fetched page payloads through one normalized contract
- [ ] parse outputs include normalized text, chunk rows, parse summary, and transform lineage fields
- [ ] evidence ingestion routes through the shared parse contract instead of hook-local parse shapes
- [ ] web evidence ingestion routes through the shared parse contract instead of hook-local parse shapes
- [ ] legal authority text uses the same parse family when source text is available
- [ ] provenance fields align across evidence, archived pages, and authority text
- [ ] the existing fact registry is extended to archived pages and future predicate-bearing artifacts

Acceptance criteria:

- uploaded evidence, discovered web evidence, and parsed authority text produce one contract family for downstream graph and logic consumers

Validation:

- focused parse tests for text, HTML, and PDF where available
- focused mediator tests for evidence, web evidence, and authority parsing payloads
- payload contract updates in `docs/PAYLOAD_CONTRACTS.md` when externally visible fields change

## M2: Persistent Support and Graph Query Plane

Goal:

- move from fallback graph extraction to persisted support traces and reviewable graph-backed support queries

Primary files:

- `integrations/ipfs_datasets/graphs.py`
- `mediator/claim_support_hooks.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`
- `mediator/mediator.py`
- `complaint_phases/knowledge_graph.py`
- `complaint_phases/dependency_graph.py`

Checklist:

- [ ] graph snapshot contracts exist behind the adapter boundary
- [ ] graph persistence semantics distinguish created versus reused graph content
- [ ] support-query APIs can enumerate artifacts, authorities, and facts supporting a claim element
- [ ] graph-support outputs preserve lineage back to source artifacts and authority records
- [ ] coverage-matrix semantics are defined for mediator review and drafting readiness
- [ ] support queries expose duplicate and semantic-cluster context, not just raw counts

Acceptance criteria:

- mediator review flows can explain why a claim element is covered, partial, or missing using provenance-backed support traces

Validation:

- focused graph adapter tests
- claim-support and review payload tests
- regression tests for graph-projection metadata and support summaries

## M3: Support-Quality and Validation Layer

Goal:

- layer GraphRAG scoring and formal validation on top of the stabilized parse, fact, and graph substrates

Primary files:

- `integrations/ipfs_datasets/graphrag.py`
- `integrations/ipfs_datasets/logic.py`
- `complaint_phases/legal_graph.py`
- `complaint_phases/neurosymbolic_matcher.py`
- `complaint_phases/phase_manager.py`
- `mediator/claim_support_hooks.py`
- `mediator/mediator.py`

Checklist:

- [ ] GraphRAG exposes ontology-quality or support-path scoring in a mediator-consumable shape
- [ ] support overviews surface quality signals rather than raw support counts alone
- [ ] follow-up planning can consume graph-quality or ontology-gap signals
- [ ] logic adapter wraps text-to-predicate, contradiction, and proof workflows behind stable normalized outputs
- [ ] at least one complaint type has explicit predicate templates and grounded fact mapping
- [ ] proof-gap and contradiction outputs are persisted or exposed through review surfaces

Acceptance criteria:

- complaint-generator can surface support strength, missing premises, and contradictions before drafting for at least one complaint workflow

Validation:

- focused tests for GraphRAG scoring outputs
- focused tests for logic adapter degraded mode
- mediator tests for contradiction and proof-gap payloads

## M4: Operator Productization

Goal:

- turn the current review payloads into a fuller operator-facing support workspace

Primary files:

- `applications/review_api.py`
- `mediator/mediator.py`
- `mediator/web_evidence_hooks.py`
- `docs/APPLICATIONS.md`
- `docs/PAYLOAD_CONTRACTS.md`
- future application or UI surfaces to be selected during implementation

Checklist:

- [ ] review payloads expose support packets with evidence, authority, fact, provenance, and graph-support detail
- [ ] contradiction and missing-support summaries are operator-visible
- [ ] queued acquisition and enrichment state can be inspected from review surfaces
- [ ] long-running archive, graph, and validation work can move into explicit background workflows where necessary
- [ ] documentation for review and execution routes is aligned with actual payloads and compatibility behavior

Acceptance criteria:

- operators can inspect coverage, contradictions, provenance, and queued enrichment work without consulting raw tables

Validation:

- focused review API tests
- payload contract updates
- application docs updates

## Cross-Milestone Guardrails

- [ ] every milestone lands with at least one mediator-visible consumer
- [ ] every milestone lands with focused tests for touched payloads or adapters
- [ ] every milestone keeps degraded mode supported
- [ ] every externally visible payload change is documented in `docs/PAYLOAD_CONTRACTS.md`
- [ ] no milestone bypasses the adapter boundary to call `ipfs_datasets_py` internals directly from production code

## Recommended Execution Order

1. M0
2. M1
3. M2
4. M3
5. M4

## Exit Condition

The integration can be treated as mature when complaint-generator can acquire, archive, parse, organize, validate, and review legal support through one provenance-preserving workflow across full, partial, and degraded runtime modes.