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

This near-term plan now also assumes the team wants claim-aware legal corpus search and first-pass authority-treatment tracking, not just broader acquisition volume.

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
- keep expanding the shared fact registry so archived pages, authority-derived facts, and later graph or predicate artifacts share one durable support contract without source-specific branches
- make chunk- and fact-level lineage dependable enough for later graph and logic consumers

### Expected output

- one parse-result family across evidence, archived web material, and legal authorities
- one provenance model across artifact families
- one durable corpus shape for artifacts, chunks, and facts

### Stop condition

- evidence, web-evidence, and legal-authority flows assert the same parse and provenance contract family
- downstream consumers can treat archived pages and authority text as ordinary case artifacts, and archived web evidence facts already round-trip through the shared persisted evidence fact path

### Suggested validation

```bash
./.venv/bin/python -m pytest tests/test_evidence_hooks.py -q
./.venv/bin/python -m pytest tests/test_web_evidence_hooks.py -q
./.venv/bin/python -m pytest tests/test_legal_authority_hooks.py -q
./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q
```

## Batch 2: Legal Corpus Search and Authority Treatment

### Goal

Make legal research claim-element-aware so the system can search for support, opposition, procedural requirements, and authority reliability before drafting.

### Primary files

- `integrations/ipfs_datasets/legal.py`
- `integrations/ipfs_datasets/types.py`
- `mediator/legal_authority_hooks.py`
- `mediator/claim_support_hooks.py`
- `claim_support_review.py`

### Work

- create legal search programs for element-definition, fact-pattern, procedural, adverse-authority, and treatment-check searches
- add normalized authority-family and treatment fields so statutes, administrative rules, guidance, and case law can be compared consistently
- persist first-pass authority-treatment records such as `supports`, `adverse`, `limits`, `distinguishes`, and `good_law_unconfirmed`
- add typed `Authority Record`, `Authority Treatment Edge`, and `Rule Candidate` outputs so later graph and logic work does not invent incompatible schemas
- extract first-pass rule candidates and procedural prerequisites from parsed authority text for at least one claim type
- map rule candidates to claim elements strongly enough to distinguish `law found but facts do not satisfy the rule` from `law not found`
- feed authority intent and treatment uncertainty into follow-up planning and compact review payloads
- preserve degraded mode by allowing empty treatment state when upstream treatment sources are unavailable

### Expected output

- per-element legal search plans rather than flat claim-type legal queries
- first-pass authority-treatment records available to review and follow-up logic
- first-pass rule candidates linked to at least one claim-element family
- operator-visible supportive versus adverse authority summaries

### Stop condition

- for at least one claim type, the system can represent both supporting and adverse authority candidates for a claim element
- for at least one claim type, the system can represent a rule candidate derived from authority text and connect it to claim-element review
- compact review payloads can surface treatment-aware legal support signals without breaking existing clients

### Suggested validation

```bash
./.venv/bin/python -m pytest tests/test_legal_authority_hooks.py -q
./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q
./.venv/bin/python -m pytest tests/test_review_api.py -q
```

Add focused tests for typed authority-treatment and rule-candidate payloads before landing this batch; do not rely only on broader hook coverage.

## Batch 3: Durable Support Corpus and Graph Query Hardening

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

## Batch 4: Logic Adapter Grounding and Validation Persistence

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

## Batch 5: Operator Support Packets and Drilldown Workflow

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

## Batch 6: Drafting and Export Integration

### Goal

Make the formal complaint builder and export pipeline consume the same support, authority-treatment, graph, and validation signals that the review layer uses.

### Primary files

- `document_pipeline.py`
- `applications/document_api.py`
- `mediator/mediator.py`
- `mediator/claim_support_hooks.py`
- `claim_support_review.py`
- `templates/document.html`
- `docs/PAYLOAD_CONTRACTS.md`
- `docs/APPLICATIONS.md`

### Work

- derive drafting-ready support packets for factual allegations, jurisdiction and venue, claims for relief, and requested relief
- expose section-level readiness and warning objects for unsupported facts, adverse authority, weak treatment confidence, failed premises, and unresolved procedural prerequisites
- keep exports compatible with degraded mode by distinguishing missing enrichment from actual legal insufficiency
- thread artifact provenance and support-bundle summaries into the browser builder so operators can inspect filing readiness before export
- ensure generated payloads remain download-safe and backward compatible for existing artifact consumers

### Expected output

- a formal complaint workflow that is support-aware rather than text-generation-only
- stable document payload fields for section readiness, warnings, and support provenance
- browser-visible drafting warnings and readiness summaries before or alongside artifacts

### Current status

- implemented in the current checkout for drafting-readiness payloads, browser-side readiness rendering, source drilldown, and review-surface deep links; further work can build on this baseline rather than reopening the initial Batch 6 slice

### Stop condition

- at least one complaint flow can build a filing draft with explicit section-level support or warning metadata derived from claim-support state
- the `/document` workflow can expose support-aware readiness without requiring the operator to inspect raw review payloads first

### Suggested validation

```bash
./.venv/bin/python -m pytest tests/test_document_pipeline.py -q
./.venv/bin/python -m pytest tests/test_review_api.py -q
./.venv/bin/python -m pytest tests/test_claim_support_review_template.py -q
```

## Recommended Delivery Order

1. Batch 1
2. Batch 2
3. Batch 3
4. Batch 4
5. Batch 5
6. Batch 6

## Recommended Ownership Split

### Track A: Parse and corpus work

- Batch 1

### Track B: Support organization and graph work

- Batch 3 after Batch 2 establishes stable authority-treatment and rule-candidate shapes

### Track C: Logic and validation work

- Batch 4 after Batch 2 and Batch 3 outputs are stable

### Track D: Operator productization

- Batch 5 after Batch 3 and Batch 4 stabilize their payloads

### Track E: Drafting and filing-readiness productization

- Batch 6 after Batch 5 makes support packets stable enough to consume from the document pipeline

## Exit Condition For This Plan

This near-term plan is complete when the team can pick the next coding slice without re-litigating:

- which files to touch
- what the slice depends on
- what counts as done
- which focused validations to run

At that point, the repo should be positioned to move from architecture and contract completion into sustained implementation of the graph, proof, and operator-workspace layers.