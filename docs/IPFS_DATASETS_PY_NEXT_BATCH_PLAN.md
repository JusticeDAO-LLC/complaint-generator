# IPFS Datasets Py Next Batch Plan

Date: 2026-03-12
Status: Near-term execution schedule

## Purpose

Translate the broader `ipfs_datasets_py` roadmap into the next four concrete implementation batches that can be executed in sequence without reopening architecture decisions each time.

This document is intentionally narrower than:

- `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md`
- `docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md`
- `docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md`
- `docs/IPFS_DATASETS_PY_FILE_WORKLIST.md`

Use it when selecting the next coding slice.

## Planning Assumptions

These batches assume the repository already has:

- a stable adapter boundary under `integrations/ipfs_datasets/`
- evidence, web evidence, and legal-authority ingestion flows already using adapter-backed contracts in part
- persisted claim-support, follow-up planning, and review payloads
- review API, CLI, and dashboard surfaces already in place for operator inspection

The aim is to deepen the existing slices, not redesign them.

## Batch Selection Rules

1. Do not start a later batch until the earlier batch exposes a stable mediator-visible output.
2. Keep all production `ipfs_datasets_py` usage behind `integrations/ipfs_datasets/`.
3. Every batch must land with focused tests, not only broad regression runs.
4. Every batch must preserve degraded mode.
5. Every externally visible payload change must update `docs/PAYLOAD_CONTRACTS.md`.

## Batch 1: Adapter Contract Stabilization

### Goal

Stabilize adapter payload shapes and capability reporting so later parse, graph, and validation work does not keep re-breaking callers.

### Primary files

- `integrations/ipfs_datasets/capabilities.py`
- `integrations/ipfs_datasets/loader.py`
- `integrations/ipfs_datasets/legal.py`
- `integrations/ipfs_datasets/search.py`
- `integrations/ipfs_datasets/graphs.py`
- `integrations/ipfs_datasets/logic.py`
- `integrations/ipfs_datasets/types.py`
- `integrations/ipfs_datasets/__init__.py`
- `mediator/mediator.py`
- `tests/test_ipfs_adapter_types.py`

### Work

- normalize capability payloads across documents, graphs, GraphRAG, logic, vector store, and MCP gateway
- standardize degraded-reason fields and success payload families
- remove remaining adapter-specific shape differences that force mediator branching
- confirm production modules do not import `ipfs_datasets_py` internals directly
- expose one stable capability summary helper for diagnostics and startup logging

### Expected output

- one canonical capability-report family
- one canonical degraded-payload family
- stable adapter type shapes that later batches can build on

### Stop condition

- mediator startup behaves the same across full and degraded environments
- adapter tests do not need adapter-specific assertions for payload shape drift

### Suggested validation

```bash
./.venv/bin/python -m pytest tests/test_ipfs_adapter_types.py -q
./.venv/bin/python -m pytest tests/test_ipfs_adapter_layer.py -q
```

## Batch 2: Shared Parse and Provenance Contract

### Goal

Make uploaded evidence, discovered web evidence, archived captures, and legal authority text flow through one parse and lineage contract.

### Primary files

- `integrations/ipfs_datasets/documents.py`
- `integrations/ipfs_datasets/provenance.py`
- `integrations/ipfs_datasets/types.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`

### Work

- route bytes, files, and fetched page content through one canonical parse call
- align parse summary, chunk metadata, and transform lineage fields
- ensure web evidence and legal authority text preserve the same provenance model as uploaded evidence
- normalize PDF, DOCX, RTF, HTML, email, and office-document parsing so hook code does not branch by file type
- deepen the shared fact registry so facts derived from archived pages and authority text look like first-class case facts
- remove hook-local parse-shape assumptions where they still exist

### Expected output

- one parse-result family across evidence, web evidence, and legal authorities
- one provenance model across artifact families
- chunk- and fact-level lineage suitable for later graph and logic consumers
- one document-service contract that can organize heterogeneous exhibits into the same case corpus

### Stop condition

- evidence, web evidence, and legal-authority tests assert the same contract family rather than separate hook-local shapes

### Suggested validation

```bash
./.venv/bin/python -m pytest tests/test_evidence_hooks.py -q
./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py -q
./.venv/bin/python -m pytest tests/test_legal_authority_hooks.py -q
```

## Batch 3: Persistent Support and Graph Query Plane

### Goal

Move from graph extraction metadata and fallback support summaries into persisted, queryable, provenance-backed support traces.

### Primary files

- `integrations/ipfs_datasets/graphs.py`
- `integrations/ipfs_datasets/types.py`
- `mediator/claim_support_hooks.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`
- `mediator/mediator.py`
- `complaint_phases/knowledge_graph.py`
- `complaint_phases/dependency_graph.py`

### Work

- formalize graph snapshot and graph lineage contracts behind the adapter boundary
- expose support-tracing query APIs for claim elements
- deepen coverage-matrix semantics so support is organized around artifacts, authorities, facts, duplicates, and semantic clusters
- preserve lineage from support rows back to source artifacts and graph snapshots
- make graph-backed support traces available to dashboard and review surfaces in a drilldown-friendly shape
- make graph-backed support traces available to review and drafting readiness flows

### Expected output

- graph-backed support queries for claim elements
- a persisted claim-element coverage matrix model that is stronger than stitched summaries
- provenance-backed explanations for covered, partial, and missing states
- review-ready support packets that can later expose timeline, contradiction, and proof-gap drilldowns

### Stop condition

- operator review flows can explain a claim-element coverage state from persisted support traces instead of only raw counts and ad hoc summaries

### Suggested validation

```bash
./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q
./.venv/bin/python -m pytest tests/test_review_api.py -q
./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py tests/test_legal_authority_hooks.py tests/test_claim_support_hooks.py -q
```

## Batch 4: Support Quality and Formal Validation Starter Slice

### Goal

Add the first mediator-consumable support-quality, contradiction, and proof-gap outputs for at least one complaint workflow.

### Primary files

- `integrations/ipfs_datasets/graphrag.py`
- `integrations/ipfs_datasets/logic.py`
- `complaint_phases/legal_graph.py`
- `complaint_phases/neurosymbolic_matcher.py`
- `complaint_phases/phase_manager.py`
- `mediator/claim_support_hooks.py`
- `mediator/mediator.py`
- `docs/PAYLOAD_CONTRACTS.md`

### Work

- expose GraphRAG support-quality or support-path scoring in a normalized adapter payload
- define at least one claim-type-specific predicate template family
- map a small set of extracted facts and authority rules into grounded predicates
- surface proof gaps, missing premises, or contradictions through mediator-visible outputs
- feed those validation signals into review payloads and follow-up planning, even if only for one claim type initially

### Expected output

- support quality stronger than raw support counts
- one starter proof-gap or contradiction payload family
- review surfaces that can distinguish covered, weakly supported, contradictory, and structurally missing support
- a path to operator-facing provenance and contradiction drilldown without redesigning the payload family later

### Stop condition

- at least one complaint flow can emit structured validation output before drafting
- GraphRAG and logic outputs are consumable from mediator review flows rather than isolated adapter demos

### Suggested validation

```bash
./.venv/bin/python -m pytest tests/test_review_api.py -q
./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q
```

Add dedicated focused GraphRAG and logic tests before landing this batch; do not rely only on broad suite coverage.

## Recommended Delivery Order

1. Batch 1
2. Batch 2
3. Batch 3
4. Batch 4

## Recommended Ownership Split

### Track A: Adapter and contract work

- Batch 1
- adapter-heavy portions of Batch 2

### Track B: Mediator and support organization work

- mediator-heavy portions of Batch 2
- Batch 3

### Track C: Reasoning and validation work

- Batch 4 after Batch 3 outputs are stable

## Exit Condition For This Plan

This near-term batch plan is complete when the team can pick the next coding slice without re-litigating:

- which files to touch
- which validation commands to run
- what counts as done for the slice
- what the next slice depends on