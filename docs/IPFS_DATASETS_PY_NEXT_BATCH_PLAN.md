# IPFS Datasets Py Next Batch Plan

Date: 2026-03-12
Status: Near-term execution schedule aligned to current baseline

## Purpose

Translate the broader `ipfs_datasets_py` roadmap into the next four concrete implementation batches that should be executed from the repository's current state.

This document is intentionally narrower than:

- `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md`
- `docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md`
- `docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md`
- `docs/IPFS_DATASETS_PY_FILE_WORKLIST.md`

Use it when selecting the next coding slice.

## Current Baseline

These batches assume the repository already has:

- a stable adapter boundary under `integrations/ipfs_datasets/`
- typed parse and graph contracts through `DocumentParseResult`, `GraphSnapshotResult`, and `GraphSupportResult`
- evidence, web evidence, and legal-authority ingestion using adapter-backed flows
- persisted claim-support links, follow-up history, and compact review payloads
- graph-trace summaries, contradiction diagnostics, reasoning diagnostics, and proof-aware follow-up planning
- review API and dashboard surfaces already in place for operator inspection

The aim is to finish the highest-value workflow integrations from that baseline, not to redesign the architecture.

## Batch Selection Rules

1. Do not start a later batch until the earlier batch exposes a stable mediator-visible output.
2. Keep all production `ipfs_datasets_py` usage behind `integrations/ipfs_datasets/`.
3. Every batch must land with focused tests, not only broad regression runs.
4. Every batch must preserve degraded mode.
5. Every externally visible payload change must update `docs/PAYLOAD_CONTRACTS.md`.

## Batch 1: Parse Completion and Corpus Unification

### Goal

Finish the shared parse contract so uploaded evidence, discovered pages, archived pages, and legal authority text all behave like one case corpus.

### Primary files

- `integrations/ipfs_datasets/documents.py`
- `integrations/ipfs_datasets/provenance.py`
- `integrations/ipfs_datasets/types.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- `mediator/legal_authority_hooks.py`
- `mediator/claim_support_hooks.py`

### Work

- close remaining format-specific gaps for PDF, DOCX, RTF, HTML, email-style text, and office documents inside the adapter layer
- standardize parse quality, OCR usage, page-span, and chunk-offset metadata
- ensure authority text and archived page content preserve the same parse and provenance model as uploaded evidence
- expand the shared fact registry so archived pages and authority-derived facts are first-class support sources rather than adjacent special cases
- make chunk- and fact-level lineage dependable enough for later graph and logic consumers

### Expected output

- one parse-result family across evidence, archived web material, and legal authorities
- one provenance model across artifact families
- one durable corpus shape for artifacts, chunks, and facts

### Stop condition

- evidence, web-evidence, and legal-authority flows assert the same parse and provenance contract family
- downstream consumers can treat archived pages and authority text as ordinary case artifacts

### Suggested validation

```bash
./.venv/bin/python -m pytest tests/test_evidence_hooks.py -q
./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py -q
./.venv/bin/python -m pytest tests/test_legal_authority_hooks.py -q
./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q
```

## Batch 2: Durable Support Corpus and Graph Query Hardening

### Goal

Turn the existing graph snapshot and support-trace work into a more durable claim-element support query plane.

### Primary files

- `integrations/ipfs_datasets/graphs.py`
- `integrations/ipfs_datasets/types.py`
- `mediator/claim_support_hooks.py`
- `mediator/mediator.py`
- `complaint_phases/knowledge_graph.py`
- `complaint_phases/legal_graph.py`
- `claim_support_review.py`

### Work

- deepen graph snapshot persistence beyond created-versus-reused metadata into durable snapshot and lineage handles
- add stronger cross-document entity and event resolution across uploads, archived pages, and authorities
- expose graph-backed support-path queries for claim elements rather than only compact support summaries
- define or persist a stronger coverage-matrix substrate so review and drafting can query one authoritative support view
- keep duplicate and semantic-cluster handling operator-visible, but move the source of truth from stitched summaries toward durable support-query outputs

### Expected output

- graph-backed support queries for claim elements
- stronger persisted support traces and lineage
- a more authoritative coverage-matrix model for review and drafting readiness

### Stop condition

- operator review flows can drill from a claim-element status into graph-backed support paths and persisted support traces without reconstructing context ad hoc

### Suggested validation

```bash
./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q
./.venv/bin/python -m pytest tests/test_review_api.py -q
./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py tests/test_legal_authority_hooks.py tests/test_claim_support_review_dashboard_flow.py -q
```

## Batch 3: Logic Adapter Grounding and Validation Persistence

### Goal

Replace placeholder proof behavior with grounded contradiction, failed-premise, and proof-gap outputs that are persisted and reviewable.

### Primary files

- `integrations/ipfs_datasets/logic.py`
- `integrations/ipfs_datasets/types.py`
- `complaint_phases/neurosymbolic_matcher.py`
- `complaint_phases/legal_graph.py`
- `mediator/claim_support_hooks.py`
- `mediator/mediator.py`
- `docs/PAYLOAD_CONTRACTS.md`

### Work

- implement stable logic-adapter outputs for contradiction checks, support checks, and proof-gap reporting
- define at least one claim-type-specific predicate template family grounded in stored facts and authority-derived rules
- persist validation runs, failed premises, and proof traces in a mediator-consumable shape
- keep degraded mode explicit when theorem-prover extras or upstream bridges are unavailable
- maintain compatibility with the existing review and follow-up payload family while upgrading the source quality of those outputs

### Expected output

- grounded contradiction and proof-gap records
- persisted validation runs with explainable inputs and outputs
- mediator-visible proof signals that are no longer primarily placeholder-driven

### Stop condition

- at least one complaint flow can emit grounded contradiction or failed-premise outputs before drafting
- review flows can inspect validation provenance without reading raw adapter output

### Suggested validation

```bash
./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q
./.venv/bin/python -m pytest tests/test_review_api.py -q
./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py tests/test_legal_authority_hooks.py -q
```

Add dedicated focused logic-adapter tests before landing this batch; do not rely only on broad suite coverage.

## Batch 4: Operator Support Packets and Drilldown Workflow

### Goal

Turn the existing compact review, dashboard, and follow-up summaries into a fuller operator-facing support workspace.

### Primary files

- `applications/review_api.py`
- `claim_support_review.py`
- `mediator/mediator.py`
- `mediator/web_evidence_hooks.py`
- `docs/PAYLOAD_CONTRACTS.md`
- `docs/APPLICATIONS.md`

### Work

- add support packets that combine evidence, authority, fact, provenance, graph-trace, and validation detail per claim element
- add timeline and archive-history drilldown for sourced evidence where historical changes matter
- expose contradiction packets and failed-premise packets in an operator-readable shape
- surface queued acquisition and enrichment state where it materially affects support coverage
- keep the compact summary layer for dashboards, but make drilldown packets first-class review outputs

### Expected output

- richer operator support packets
- provenance and timeline drilldown
- contradiction and failed-premise drilldown without losing existing compact summaries

### Stop condition

- operators can inspect one claim element end-to-end from summary status to artifacts, passages, archived versions, graph support, and validation state

### Suggested validation

```bash
./.venv/bin/python -m pytest tests/test_review_api.py -q
./.venv/bin/python -m pytest tests/test_claim_support_review_dashboard_flow.py -q
./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py tests/test_claim_support_hooks.py tests/test_review_api.py -q
```

## Recommended Delivery Order

1. Batch 1
2. Batch 2
3. Batch 3
4. Batch 4

## Recommended Ownership Split

### Track A: Parse and corpus work

- Batch 1

### Track B: Support organization and graph work

- Batch 2

### Track C: Logic and validation work

- Batch 3 after Batch 2 outputs are stable

### Track D: Operator productization

- Batch 4 after Batch 2 and Batch 3 stabilize their payloads

## Exit Condition For This Plan

This near-term plan is complete when the team can pick the next coding slice without re-litigating:

- which files to touch
- what the slice depends on
- what counts as done
- which focused validations to run

At that point, the repo should be positioned to move from architecture and contract completion into sustained implementation of the graph, proof, and operator-workspace layers.