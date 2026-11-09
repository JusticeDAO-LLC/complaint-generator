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
- `Validation Required`: implemented checklist items exist, but the supervisor should still run the listed validation commands before treating the slice as closed
- `Deferred`: useful but lower priority than current roadmap

## Workstream Overview

| ID | Workstream | Status | Priority | Outcome |
|---|---|---|---|---|
| T0 | Canonical temporal registry | Complete | P0 | One durable fact and relation substrate for chronology |
| T1 | Claim-scoped temporal graph assembly | Validation Required | P0 | Stable partial-order graphs and issue categories per claim |
| T2 | Legal temporal rule profiles | Validation Required | P0 | Claim-type specific timing rules and blocking windows |
| T3 | Theorem export and proof bundles | Validation Required | P0 | Durable TDFOL and DCEC proof payloads with provenance |
| T4 | Temporal contradiction and follow-up planner | Validation Required | P1 | Missing chronology becomes actionable next steps |
| T5 | Review, drafting, and optimization integration | Validation Required | P1 | Temporal proof state becomes an operational readiness gate |
| T6 | Regression and gold-case enforcement | Validation Required | P0 | Chronology behavior is measurable and test-protected |

## T0: Canonical Temporal Registry

Status: Complete
Priority: P0

### Goal

Create one durable schema for temporal facts, relations, anchors, and issues across all evidence sources.

### Primary files

- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py)
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [docs/PAYLOAD_CONTRACTS.md](./PAYLOAD_CONTRACTS.md)

### Checklist

- [x] define canonical `temporal_fact_registry` payload shape
- [x] define canonical `temporal_relation_registry` payload shape
- [x] define canonical `temporal_issue_registry` payload shape
- [x] add provenance fields for artifact IDs, testimony IDs, chunk refs, and source spans
- [x] map current `temporal_context` records into the canonical registry without breaking existing payload consumers
- [x] preserve uncertainty fields such as `is_approximate`, `is_range`, `relative_markers`, and `granularity`

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

Status: Validation Required
Priority: P0

### Goal

Build deterministic claim-level and element-level partial-order graphs from the canonical registry.

### Primary files

- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py)
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [mediator/mediator.py](../mediator/mediator.py)

### Checklist

- [x] normalize relation inference for explicit and inferred `before`, `after`, `during`, `overlaps`, and `same_time` — `build_temporal_relation_registry` now marks explicit relations as `inference_mode="explicit"` and generates inferred `before`/`same_time` relations from date anchors with `inference_mode="derived_from_date_anchors"` for pairs not already covered by an explicit relation
- [x] formalize issue categories such as `missing_anchor`, `contradictory_dates`, `relative_only_ordering`, and `limitations_risk` — `build_temporal_issue_registry` now normalises `temporal_contradictory_dates` → `contradictory_dates`, `temporal_limitations_risk` → `limitations_risk`, etc. from the contradiction queue so rule profiles and downstream consumers see canonical category names
- [x] add issue severity and blocking metadata — `severity` and `blocking` fields on every issue registry entry
- [x] emit deterministic claim-level temporal graph summaries for packets and review payloads — `build_claim_temporal_graphs()` now assembles `claim_temporal_graphs` from canonical fact, relation, and issue registries, and `_get_temporal_reasoning_context()` consumes that graph when mediator status provides it
- [x] preserve relation previews and type counts from the graph, not from UI formatting logic — `relation_type_counts`, `relation_preview`, `warnings`, and readiness trace IDs are carried through graph `consistency_summary` → `temporal_summary` → review payload
- [x] trace temporal readiness to graph IDs — `intake_chronology_readiness` now includes `trace_fact_ids`, `trace_relation_ids`, `trace_issue_ids`, and `claim_temporal_graph_ids` derived from `claim_temporal_graphs`

### Acceptance criteria

- claim-level temporal summaries are reproducible from one graph assembly path
- packet-level temporal readiness is traceable to underlying fact and relation IDs
- temporal warnings align with actual graph issues, not loose heuristics

### Degraded mode expectations

- if relation inference is partial, explicit relations and direct anchors still populate the graph
- graph assembly does not fail closed when some facts lack exact dates

### Suggested focused validation

- `.venv/bin/python -m pytest tests/test_t1_t3_temporal_next_steps.py -q`
- `.venv/bin/python -m pytest tests/test_claim_support_hooks.py tests/test_mediator_three_phase.py -q`
- `.venv/bin/python -m pytest tests/test_review_api.py -q`

## T2: Legal Temporal Rule Profiles

Status: Validation Required
Priority: P0

### Goal

Define explicit legal timing rules per claim type so chronology can be evaluated against the law, not only against itself.

### Primary files

- [complaint_analysis/decision_trees.py](../complaint_analysis/decision_trees.py)
- [complaint_analysis/legal_patterns.py](../complaint_analysis/legal_patterns.py)
- new rule profile modules under [complaint_analysis](../complaint_analysis/)

### Checklist

- [x] define a temporal rule profile contract with required events, optional events, deadlines, and defenses — `TemporalRuleProfileContract`, `TemporalEventRequirement`, and `LegalTemporalWindow` in `complaint_analysis/temporal_rule_profiles.py` expose data-only contracts through `list_temporal_rule_profiles()`, `get_temporal_rule_profile_contract()`, and `get_temporal_rule_profile_for_claim_type()`
- [x] implement the first rule profile for retaliation
- [x] add legal windows for causal proximity, filing, notice, or exhaustion where relevant — EEOC 180/300-day window via `has_limitations_risk` and `limitations_risk_days`
- [x] expose rule-frame IDs in proof payloads so failures can be explained against concrete legal rules — `rule_frame_id` in proof bundles and `temporal_rule_frame_id` in element review items
- [x] document how claim-type timing rules differ from generic timeline consistency warnings — see `_TEMPORAL_ISSUE_FOLLOW_UP_PROFILES` and the profile registry in `complaint_analysis/temporal_rule_profiles.py`; claim-type rules (e.g. `retaliation_temporal_profile_v1`) evaluate ordered role-tagged facts against a legal frame (`retaliation_temporal_frame`) whereas generic timeline warnings come from issue-registry normalization of `missing_anchor`, `contradictory_dates`, and `relative_only_ordering` issue types without a claim-type gate
- [x] expose non-rendering discovery hooks — `get_temporal_rule_question_hints()` in `complaint_analysis/decision_trees.py` and `get_temporal_legal_patterns()` in `complaint_analysis/legal_patterns.py` let intake/review code discover the same profile events and legal timing terms without depending on HTML templates

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

Status: Validation Required
Priority: P0

### Goal

Compile chronology into durable theorem-ready proof bundles with provenance-aware TDFOL and DCEC exports.

### Primary files

- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [claim_support_review.py](../claim_support_review.py)
- `integrations/ipfs_datasets/logic.py`

### Checklist

- [x] define `proof_bundles` keyed by claim type and element ID — `summarize_claim_reasoning_review` now returns durable bundles under `proof_bundles: {"claim_type:element_id": {...}}`, preserving full formula lists, digest metadata, status, rule_frame_id, fact_ids, relation_ids, issue_ids, previews, theorem export metadata, and follow-ups
- [x] emit theorem exports that reference fact IDs, relation IDs, and rule-frame IDs — `theorem_export_metadata` in `_build_temporal_proof_bundle` carries all of these, and `export_theorem_from_proof_bundle()` can reproduce Lean/Coq exports from the persisted bundle alone
- [x] distinguish certain facts from inferred relations in theorem export metadata — `tdfol_formula_certainties` and `dcec_formula_certainties` maps in `theorem_exports`; `inference_mode="derived_from_date_anchors"` relations are marked `inferred`, all others `certain`
- [x] attach blocking explanation payloads to failed proof bundles — `blocking_reasons`, `blocking_explanations`, `missing_fact_roles`, `missing_relations`, and `recommended_follow_ups` are in every proof bundle entry
- [x] expose the same proof bundle previews through review payloads and operator UI — `temporal_proof_bundle_tdfol_preview` and `temporal_proof_bundle_dcec_preview` are derived from bundle previews/formulas, while `proof_bundles` retains the full persisted artifact for drilldown and proof execution

### Acceptance criteria

- theorem exports are reproducible from persisted proof bundles via stable bundle digests and deterministic export timestamps
- formula previews shown to operators come from the same bundle used for proof execution; `run_hybrid_reasoning`, `prove_claim_elements`, and `check_contradictions` prefer bundled formulas when `proof_bundles` are supplied
- proof failures identify concrete missing fact roles, missing relation predicates, affected fact IDs, issue IDs, and required provenance kinds instead of generic insufficiency

### Degraded mode expectations

- if advanced theorem execution is unavailable, proof bundles and preview exports still materialize for review and follow-up planning

### Suggested focused validation

- `.venv/bin/python -m pytest tests/test_claim_support_hooks.py tests/test_review_api.py -q`
- `.venv/bin/python -m pytest tests/test_claim_support_review_dashboard_flow.py -q`

## T4: Temporal Contradiction And Follow-Up Planner

Status: Validation Required
Priority: P1

### Goal

Route temporal proof failures into specific testimony, document, or external-record follow-up actions.

### Primary files

- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [complaint_phases/denoiser.py](../complaint_phases/denoiser.py)
- [mediator/mediator.py](../mediator/mediator.py)
- [intake_status.py](../intake_status.py)

### Checklist

- [x] map issue categories to recommended follow-up lanes — `_TEMPORAL_ISSUE_FOLLOW_UP_PROFILES` in `complaint_analysis/temporal_rule_profiles.py` maps `missing_anchor`, `contradictory_dates`, `limitations_risk`, `temporal_reverse_before`, retaliation-specific, and document-date gap categories to canonical lanes with `follow_up_target` and `proof_criticality`
- [x] add timeline-specific question objectives such as anchor capture, contradiction resolution, and deadline verification — `question_objective` field on every follow-up item (`anchor_capture`, `contradiction_resolution`, `deadline_verification`, `testimony_capture`, `document_verification`)
- [x] rank follow-ups by proof criticality and legal timing impact — `rank_follow_ups()` in `temporal_rule_profiles.py` sorts high-criticality items first; `evaluate_temporal_rule_profile()` returns pre-ranked follow-ups
- [x] expose timeline gap follow-ups in review and optimization payloads — `timeline_gap_follow_ups` field in `summarize_claim_reasoning_review()` output, aggregated via `_aggregate_timeline_gap_follow_ups(proof_bundles)`
- [x] preserve whether follow-up targets testimony, document request, or external corroboration — `follow_up_target` field on every enriched follow-up item (`testimony`, `document_request`, `external_corroboration`, `clarification`)
- [x] emit explicit temporal next-action records for blocking chronology issues — proof bundles, claim-support handoffs, alignment evidence tasks, follow-up task metadata, and intake summaries now preserve `temporal_next_actions` with `next_action`, `affected_rule`, `affected_fact_ids`, `affected_issue_ids`, `temporal_missingness_kind`, `follow_up_target`, and `question_objective`
- [x] route temporal next actions into operator prompts — the denoiser converts `fill_temporal_chronology_gap` tasks into rule-aware timeline questions and keeps temporal gaps separate from ordinary missing support

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

Status: Validation Required
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

- [x] expose proof bundle IDs and legal temporal frame references in review payloads — `temporal_proof_bundle_id`, `temporal_rule_frame_id`, `proof_bundles` dict all present in review output
- [x] add operator drilldowns from packet summaries to blocking facts and relations — `proof_bundles` indexed by `claim_type:element_id` with blocking_reasons, follow-ups, and fact/relation IDs
- [x] gate drafting readiness on legal temporal sufficiency, not only aggregate proof-readiness score — `_build_chronology_blocker_summary` now reads both `temporal_rule_profile_failed_element_count` and `temporal_rule_profile_partial_element_count` from `claim_reasoning_review` and sets `chronology_blocked=True` independently of issue counts
- [x] show chronology-specific blockers in `/document` and `/document/optimization-trace` — `renderChronologyBlockerSummary()` in both `templates/document.html` and `templates/optimization_trace.html`; `document.html` reads from `draft.source_context.chronology_blocker_summary`, trace template derives from `claimReasoningReview` and `claimSupportPacketSummary`, and both surfaces distinguish failed and partial temporal rule elements
- [x] preserve UX parity between packet summary chips and detailed proof-handoff panels

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

Status: Validation Required
Priority: P0

### Goal

Protect chronology behavior with targeted regressions and legal gold cases.

### Primary files

- [tests/test_t1_t3_temporal_next_steps.py](../tests/test_t1_t3_temporal_next_steps.py)
- [tests/test_temporal_rule_profiles.py](../tests/test_temporal_rule_profiles.py)
- [tests/test_claim_support_hooks.py](../tests/test_claim_support_hooks.py)
- [tests/test_review_api.py](../tests/test_review_api.py)
- [tests/test_mediator_three_phase.py](../tests/test_mediator_three_phase.py)
- [tests/test_claim_support_review_dashboard_flow.py](../tests/test_claim_support_review_dashboard_flow.py)
- [tests/test_claim_support_review_playwright_smoke.py](../tests/test_claim_support_review_playwright_smoke.py)
- [tests/test_intake_status.py](../tests/test_intake_status.py)

### Checklist

- [x] add canonical regression cases for retaliation chronology — `test_temporal_rule_profiles.py` (T6.1–T6.13) plus `test_t1_t3_temporal_next_steps.py` inferred-relation and issue-normalisation cases
- [x] add contradictory-date and relative-only-ordering cases — covered in `test_temporal_rule_profiles.py` (T6.5/T6.5b/T6.5c, T6.6, T6.7)
- [x] add deadline and limitations-window cases — covered in `test_temporal_rule_profiles.py` (T6.8/T6.8b, T6.9/T6.9b/T6.9c)
- [x] add theorem-export regression cases tied to proof bundles — `test_t1_t3_temporal_next_steps.py` (test_t3_certain_fact_formulas_annotated_as_certain, test_t3_inferred_relation_formula_annotated_as_inferred, test_t3_dcec_formula_certainties_present, test_t3_proof_bundles_keyed_by_claim_element)
- [x] keep browser smoke coverage for operator-visible timeline and packet readiness state — `test_document_preview_smoke_renders_chronology_blocker_summary` and `test_document_preview_smoke_chronology_blocker_absent_when_no_blockers` in `tests/test_claim_support_review_playwright_smoke.py` cover `#document-chronology-blocker-summary` chip rendering
- [x] enforce gold cases in the focused regression runner — `scripts/run_claim_support_review_regression.py` now includes `tests/test_t1_t3_temporal_next_steps.py`, `tests/test_temporal_rule_profiles.py`, `tests/test_mediator_three_phase.py`, and `tests/test_intake_status.py` in the base slice so payload, proof, mediator, and intake chronology drift fail under the same command

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
