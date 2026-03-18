# Temporal Timeline Proof Execution Backlog

Date: 2026-03-18
Status: Active execution backlog

Companion docs:

- [docs/TEMPORAL_TIMELINE_PROOF_PLAN.md](./TEMPORAL_TIMELINE_PROOF_PLAN.md)
- [docs/PAYLOAD_CONTRACTS.md](./PAYLOAD_CONTRACTS.md)
- [docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_IMPROVEMENT_PLAN.md](./CLAIM_SUPPORT_REVIEW_DASHBOARD_IMPROVEMENT_PLAN.md)
- [docs/INTAKE_EVIDENCE_IMPROVEMENT_PLAN.md](./INTAKE_EVIDENCE_IMPROVEMENT_PLAN.md)

## Purpose

This backlog translates the temporal timeline proof plan into thin implementation slices tied to the current complaint-generator architecture.

The goal is not to invent a second chronology system. The repo already has normalized temporal context, relation summaries, consistency summaries, temporal proof diagnostics, and operator-facing timeline review. The next work is to consolidate those seams into a canonical timeline registry and a proof-oriented legal timing pipeline.

## Execution Principles

1. Prefer partial-order chronology over invented total-order timelines.
2. Preserve provenance for every temporal fact, relation, issue, and theorem export.
3. Keep claim-type temporal rules explicit rather than burying them in prompts.
4. Reuse current mediator and review payload seams instead of adding parallel one-off structures.
5. Make proof failures actionable through follow-up questions and evidence requests.
6. Preserve degraded-mode operation when advanced theorem tooling is unavailable.

## Current Baseline

Completed or substantially in place:

- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py) already builds normalized `temporal_context`, `timeline_relation_summary`, and `timeline_consistency_summary`.
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py) already assembles element-scoped temporal reasoning context and emits `temporal_summary` in reasoning diagnostics.
- [claim_support_review.py](../claim_support_review.py) already rolls temporal fact, relation, issue, warning, and preview data into claim review payloads.
- [mediator/mediator.py](../mediator/mediator.py) already propagates timeline summaries and packet-level temporal proof readiness.
- [templates/claim_support_review.html](../templates/claim_support_review.html), [templates/document.html](../templates/document.html), and [templates/optimization_trace.html](../templates/optimization_trace.html) already expose operator-facing temporal summaries.

Still shallow or incomplete:

- there is no canonical temporal fact registry spanning testimony, parsed documents, web evidence, and authority references
- legal temporal rule profiles are not yet explicit per claim type
- theorem export is previewable but not yet organized around durable proof bundles
- temporal contradiction categories and follow-up actions are not yet a stable contract
- drafting and readiness gates still consume temporal status mostly as summary metrics rather than claim-rule satisfaction results

## Status Legend

- `Complete`: implemented enough to treat as baseline
- `In Progress`: partially implemented and actively extendable
- `Planned`: designed but not yet implemented
- `Deferred`: useful but lower priority than current roadmap

## Workstream Overview

| ID | Workstream | Status | Priority | Outcome |
|---|---|---|---|---|
| T0 | Canonical temporal registry | Planned | P0 | One durable fact and relation substrate for chronology |
| T1 | Claim-scoped temporal graph assembly | Planned | P0 | Stable partial-order graphs and issue categories per claim |
| T2 | Legal temporal rule profiles | Planned | P0 | Claim-type specific timing rules and blocking windows |
| T3 | Theorem export and proof bundles | Planned | P0 | Durable TDFOL and DCEC proof payloads with provenance |
| T4 | Temporal contradiction and follow-up planner | Planned | P1 | Missing chronology becomes actionable next steps |
| T5 | Review, drafting, and optimization integration | Planned | P1 | Temporal proof state becomes an operational readiness gate |
| T6 | Regression and gold-case enforcement | Planned | P0 | Chronology behavior is measurable and test-protected |

## T0: Canonical Temporal Registry

Status: Planned
Priority: P0

### Goal

Create one durable schema for temporal facts, relations, anchors, and issues across all evidence sources.

### Primary files

- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py)
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [docs/PAYLOAD_CONTRACTS.md](./PAYLOAD_CONTRACTS.md)

### Checklist

- [ ] define canonical `temporal_fact_registry` payload shape
- [ ] define canonical `temporal_relation_registry` payload shape
- [ ] define canonical `temporal_issue_registry` payload shape
- [ ] add provenance fields for artifact IDs, testimony IDs, chunk refs, and source spans
- [ ] map current `temporal_context` records into the canonical registry without breaking existing payload consumers
- [ ] preserve uncertainty fields such as `is_approximate`, `is_range`, `relative_markers`, and `granularity`

### Acceptance criteria

- every timeline-capable fact can be represented in a shared registry shape
- relation and issue records are claim-aware and element-aware
- existing timeline summaries can be derived from the canonical registry rather than from ad hoc field inspection

### Degraded mode expectations

- if some provenance fields are unavailable, records still persist with explicit missing provenance markers
- if a source only yields relative ordering, the registry stores that relation without fabricating an anchor

### Suggested focused validation

- `.venv/bin/python -m pytest tests/test_intake_status.py -q`
- `.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q`
- `.venv/bin/python -m pytest tests/test_review_api.py -q`

## T1: Claim-Scoped Temporal Graph Assembly

Status: Planned
Priority: P0

### Goal

Build deterministic claim-level and element-level partial-order graphs from the canonical registry.

### Primary files

- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py)
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [mediator/mediator.py](../mediator/mediator.py)

### Checklist

- [ ] normalize relation inference for explicit and inferred `before`, `after`, `during`, `overlaps`, and `same_time`
- [ ] formalize issue categories such as `missing_anchor`, `contradictory_dates`, `relative_only_ordering`, and `limitations_risk`
- [ ] add issue severity and blocking metadata
- [ ] emit deterministic claim-level temporal graph summaries for packets and review payloads
- [ ] preserve relation previews and type counts from the graph, not from UI formatting logic

### Acceptance criteria

- claim-level temporal summaries are reproducible from one graph assembly path
- packet-level temporal readiness is traceable to underlying fact and relation IDs
- temporal warnings align with actual graph issues, not loose heuristics

### Degraded mode expectations

- if relation inference is partial, explicit relations and direct anchors still populate the graph
- graph assembly does not fail closed when some facts lack exact dates

### Suggested focused validation

- `.venv/bin/python -m pytest tests/test_claim_support_hooks.py tests/test_mediator_three_phase.py -q`
- `.venv/bin/python -m pytest tests/test_review_api.py -q`

## T2: Legal Temporal Rule Profiles

Status: Planned
Priority: P0

### Goal

Define explicit legal timing rules per claim type so chronology can be evaluated against the law, not only against itself.

### Primary files

- [complaint_analysis/decision_trees.py](../complaint_analysis/decision_trees.py)
- [complaint_analysis/legal_patterns.py](../complaint_analysis/legal_patterns.py)
- new rule profile modules under [complaint_analysis](../complaint_analysis/)

### Checklist

- [ ] define a temporal rule profile contract with required events, optional events, deadlines, and defenses
- [ ] implement the first rule profile for retaliation
- [ ] add legal windows for causal proximity, filing, notice, or exhaustion where relevant
- [ ] expose rule-frame IDs in proof payloads so failures can be explained against concrete legal rules
- [ ] document how claim-type timing rules differ from generic timeline consistency warnings

### Acceptance criteria

- at least one claim type can evaluate chronology against an explicit rule profile
- proof failures can identify a missing event, missing ordering relation, or violated legal window
- rule profile evaluation is independent of HTML rendering

### Degraded mode expectations

- if a claim type lacks a rule profile, the system falls back to generic temporal consistency rather than pretending legal sufficiency exists

### Suggested focused validation

- `.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q`
- `.venv/bin/python -m pytest tests/test_review_api.py -q`

## T3: Theorem Export And Proof Bundles

Status: Planned
Priority: P0

### Goal

Compile chronology into durable theorem-ready proof bundles with provenance-aware TDFOL and DCEC exports.

### Primary files

- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [claim_support_review.py](../claim_support_review.py)
- `integrations/ipfs_datasets/logic.py`

### Checklist

- [ ] define `proof_bundles` keyed by claim type and element ID
- [ ] emit theorem exports that reference fact IDs, relation IDs, and rule-frame IDs
- [ ] distinguish certain facts from inferred relations in theorem export metadata
- [ ] attach blocking explanation payloads to failed proof bundles
- [ ] expose the same proof bundle previews through review payloads and operator UI

### Acceptance criteria

- theorem exports are reproducible from persisted proof bundles
- formula previews shown to operators come from the same bundle used for proof execution
- proof failures identify concrete missing facts or relations instead of generic insufficiency

### Degraded mode expectations

- if advanced theorem execution is unavailable, proof bundles and preview exports still materialize for review and follow-up planning

### Suggested focused validation

- `.venv/bin/python -m pytest tests/test_claim_support_hooks.py tests/test_review_api.py -q`
- `.venv/bin/python -m pytest tests/test_claim_support_review_dashboard_flow.py -q`

## T4: Temporal Contradiction And Follow-Up Planner

Status: Planned
Priority: P1

### Goal

Route temporal proof failures into specific testimony, document, or external-record follow-up actions.

### Primary files

- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [complaint_phases/denoiser.py](../complaint_phases/denoiser.py)
- [mediator/mediator.py](../mediator/mediator.py)
- [intake_status.py](../intake_status.py)

### Checklist

- [ ] map issue categories to recommended follow-up lanes
- [ ] add timeline-specific question objectives such as anchor capture, contradiction resolution, and deadline verification
- [ ] rank follow-ups by proof criticality and legal timing impact
- [ ] expose timeline gap follow-ups in review and optimization payloads
- [ ] preserve whether follow-up targets testimony, document request, or external corroboration

### Acceptance criteria

- each blocking temporal issue yields at least one explicit next action
- operators can see why a follow-up is needed and which rule or fact it affects
- follow-up planning distinguishes chronology uncertainty from non-temporal missingness

### Degraded mode expectations

- if ranking signals are weak, deterministic issue-to-lane mapping still emits actionable next steps

### Suggested focused validation

- `.venv/bin/python -m pytest tests/test_mediator_three_phase.py tests/test_intake_status.py -q`
- `.venv/bin/python -m pytest tests/test_claim_support_review_dashboard_flow.py -q`

## T5: Review, Drafting, And Optimization Integration

Status: Planned
Priority: P1

### Goal

Make temporal proof state a first-class readiness input across the review dashboard and document workflows.

### Primary files

- [templates/claim_support_review.html](../templates/claim_support_review.html)
- [templates/document.html](../templates/document.html)
- [templates/optimization_trace.html](../templates/optimization_trace.html)
- [applications/review_api.py](../applications/review_api.py)
- [applications/document_api.py](../applications/document_api.py)

### Checklist

- [ ] expose proof bundle IDs and legal temporal frame references in review payloads
- [ ] add operator drilldowns from packet summaries to blocking facts and relations
- [ ] gate drafting readiness on legal temporal sufficiency, not only aggregate proof-readiness score
- [ ] show chronology-specific blockers in `/document` and `/document/optimization-trace`
- [ ] preserve UX parity between packet summary chips and detailed proof-handoff panels

### Acceptance criteria

- operators can move from summary metrics to concrete chronology blockers in one step
- drafting surfaces do not overstate readiness when critical ordering rules are unproved
- review and document flows consume the same temporal proof payloads

### Degraded mode expectations

- if deep drilldowns are unavailable, summary metrics still report unresolved chronology explicitly

### Suggested focused validation

- `.venv/bin/python -m pytest tests/test_claim_support_review_dashboard_flow.py tests/test_claim_support_review_playwright_smoke.py -q`
- `.venv/bin/python -m pytest tests/test_claim_support_review_template.py -q`

## T6: Regression And Gold-Case Enforcement

Status: Planned
Priority: P0

### Goal

Protect chronology behavior with targeted regressions and legal gold cases.

### Primary files

- [tests/test_claim_support_hooks.py](../tests/test_claim_support_hooks.py)
- [tests/test_review_api.py](../tests/test_review_api.py)
- [tests/test_mediator_three_phase.py](../tests/test_mediator_three_phase.py)
- [tests/test_claim_support_review_dashboard_flow.py](../tests/test_claim_support_review_dashboard_flow.py)
- [tests/test_claim_support_review_playwright_smoke.py](../tests/test_claim_support_review_playwright_smoke.py)
- [tests/test_intake_status.py](../tests/test_intake_status.py)

### Checklist

- [ ] add canonical regression cases for retaliation chronology
- [ ] add contradictory-date and relative-only-ordering cases
- [ ] add deadline and limitations-window cases
- [ ] add theorem-export regression cases tied to proof bundles
- [ ] keep browser smoke coverage for operator-visible timeline and packet readiness state

### Acceptance criteria

- chronology regressions fail on payload drift and UI drift
- at least one gold case proves a legally sufficient ordering path and one gold case fails for an explainable temporal reason

### Suggested focused validation

- `.venv/bin/python -m pytest tests/test_claim_support_hooks.py tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py tests/test_claim_support_review_playwright_smoke.py tests/test_mediator_three_phase.py tests/test_intake_status.py -q`
- `.venv/bin/python scripts/run_claim_support_review_regression.py --browser on`

## Recommended Build Order

1. T0 Canonical temporal registry
2. T1 Claim-scoped temporal graph assembly
3. T2 Legal temporal rule profiles with retaliation first
4. T3 Theorem export and proof bundles
5. T4 Temporal contradiction and follow-up planner
6. T5 Review and drafting integration refinements
7. T6 Gold-case enforcement and broader regression hardening

## Best Next Slice

The strongest next implementation slice is T0 plus the retaliation portion of T2.

That slice is small enough to land safely and large enough to change behavior.

- define the canonical temporal registry contract in [docs/PAYLOAD_CONTRACTS.md](./PAYLOAD_CONTRACTS.md)
- normalize current timeline-capable facts into that registry in [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py)
- persist claim-element-scoped registry entries in [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- add the first explicit retaliation timing rule profile so the system can distinguish generic chronology readiness from legally sufficient chronology

If that slice lands well, the rest of the theorem and review work can build on a stable substrate instead of continuing to derive timeline state opportunistically from summary fields.