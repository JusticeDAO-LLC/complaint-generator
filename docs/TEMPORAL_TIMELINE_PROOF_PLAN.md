# Temporal Timeline Proof Plan

Companion backlog:

- [docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md](./TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md)

This plan describes how to turn collected testimony, documents, web evidence, and authority references into a causal and temporal timeline suitable for temporal deontic first-order logic and DCEC style theorem proving.

The core objective is simple: facts should not only be collected, they should be ordered, normalized, and attached to the legal rules they can satisfy or defeat. A complaint element is not provable merely because supporting text exists. It becomes legally meaningful only when the system can show who acted, what happened, when it happened, what it caused, and how that ordering interacts with the governing law.

## Why This Matters

Many legal claims are time-sensitive by construction.

- Retaliation depends on protected activity occurring before adverse action.
- Notice and cure claims depend on deadlines, grace periods, and sequence.
- Discrimination and hostile environment claims depend on repeated acts across a period.
- Exhaustion, filing, and limitations questions depend on whether actions occurred inside statutory windows.
- Damages and causation depend on harm following breach or unlawful conduct.

If chronology is incomplete or wrong, the system can attach the right facts to the wrong rule and produce invalid proof signals.

## Current Repo Baseline

The repository already has important pieces of this workflow.

- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py) already builds normalized temporal context and exposes `timeline_relation_summary` plus `timeline_consistency_summary`.
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py) already derives element-scoped temporal reasoning context, emits temporal predicates, and now summarizes temporal fact, relation, issue, and warning counts.
- [claim_support_review.py](../claim_support_review.py) already propagates claim-level temporal review summaries and flagged element temporal diagnostics.
- [mediator/mediator.py](../mediator/mediator.py) already includes timeline relation and consistency summaries in intake status payloads and propagates packet-level temporal readiness counts.
- [templates/claim_support_review.html](../templates/claim_support_review.html) already exposes timeline ordering, hybrid reasoning diagnostics, temporal proof handoff, and packet-level temporal readiness chips to operators.

That means the plan should not restart from zero. The next work should formalize the timeline model, unify evidence-to-event normalization, and turn temporal diagnostics into proof-ready legal reasoning.

## Target End State

The desired system should do the following.

1. Normalize each collected evidence item into one or more temporal facts with provenance.
2. Infer or capture temporal relations between facts without forcing a fake total order.
3. Preserve uncertainty explicitly through ranges, approximations, and relative ordering.
4. Attach each temporal fact to claim elements, legal predicates, and possible defenses.
5. Compile the resulting structure into theorem-friendly TDFOL and DCEC representations.
6. Run proof, contradiction, and temporal consistency checks against the governing law.
7. Return operator-visible explanations showing which legal conclusions are blocked by missing or contradictory chronology.
8. Feed the validated timeline into drafting, review, and follow-up question planning.

## Design Principles

### 1. Prefer partial order over forced total order

The timeline model should represent `before`, `after`, `during`, `overlaps`, `meets`, and anchored ranges even when exact timestamps are unavailable. Legal reasoning usually needs correct precedence, not an invented exact minute-by-minute chronology.

### 2. Preserve provenance at every temporal node

Every temporal fact and relation should point back to testimony rows, parsed document spans, web evidence artifacts, or authority references. The proof layer should never reason over orphaned temporal assertions.

### 3. Keep uncertainty explicit

Approximate dates, date ranges, and relative markers such as "two weeks later" should remain first-class data, not lossy strings.

### 4. Separate fact extraction from legal interpretation

The timeline layer should normalize events and relations first. Legal qualification such as protected activity, adverse action, breach, notice, or damages trigger should be attached afterward.

### 5. Make every proof failure actionable

If the theorem layer cannot prove an element because chronology is incomplete, the system should say which event, relation, or anchor is missing and what follow-up would resolve it.

## Canonical Timeline Data Model

The timeline should be built around six core objects.

### 1. Temporal Fact

A normalized event or state assertion derived from evidence.

Required fields:

- `fact_id`
- `claim_type`
- `claim_element_id`
- `event_label`
- `predicate_family`
- `actor`
- `target`
- `start_time`
- `end_time`
- `granularity`
- `is_approximate`
- `is_range`
- `relative_markers`
- `source_artifact_ids`
- `source_span_refs`
- `confidence`
- `validation_status`

Examples:

- employee reported discrimination to HR on 2026-03-10
- termination notice delivered on 2026-03-24
- pay reduction occurred during May 2025

### 2. Temporal Relation

A normalized relation between two temporal facts.

Required fields:

- `relation_id`
- `source_fact_id`
- `target_fact_id`
- `relation_type`
- `inference_mode`
- `source_artifact_ids`
- `confidence`
- `explanation`

Initial relation types should include:

- `before`
- `after`
- `during`
- `overlaps`
- `meets`
- `same_time`
- `causes`
- `supports`
- `contradicts`

### 3. Temporal Anchor

An external or explicit anchor used to ground events.

Examples:

- calendar date from a document
- filing deadline
- payroll period boundary
- protected-activity anchor
- adverse-action anchor

### 4. Temporal Issue

A blocking or cautionary condition.

Initial issue categories should include:

- missing anchor
- contradictory dates
- unsupported ordering
- range overlap ambiguity
- limitations risk
- exhaustion window risk
- causation gap

### 5. Legal Temporal Frame

A claim-specific legal window or ordering rule.

Examples:

- protected activity must precede adverse action
- harassment acts must occur within the actionable period
- notice must be given before termination becomes effective
- complaint must be filed within a limitations window

### 6. Proof Bundle

A claim-element-scoped payload that combines facts, relations, legal frames, contradictions, and theorem exports.

## Processing Pipeline

The timeline workflow should run in eight layers.

### Layer 1. Evidence normalization

Inputs:

- testimony
- uploaded documents
- parsed document chunks
- web evidence
- legal authorities

Work:

- normalize source metadata
- generate stable artifact IDs
- preserve text spans and parse lineage
- extract candidate event phrases and date expressions

Primary files:

- [integrations/ipfs_datasets/documents.py](../integrations/ipfs_datasets/documents.py)
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py)

Acceptance criteria:

1. Every temporal fact can be traced back to at least one evidence artifact.
2. Text span provenance survives parsing and normalization.
3. Testimony and document facts share one common identity model.

### Layer 2. Event extraction

Work:

- convert evidence statements into canonical temporal facts
- identify actor, act, target, and harm
- normalize explicit dates and ranges
- preserve relative markers when no absolute anchor exists

Output:

- canonical temporal fact registry

Acceptance criteria:

1. Every extracted fact has a normalized temporal context object.
2. Approximate and range facts are retained without false precision.
3. Fact extraction supports multiple facts per artifact.

### Layer 3. Relation extraction and ordering

Work:

- derive explicit relations from evidence text
- infer high-confidence relations from anchored dates
- record confidence and inference mode
- build partial-order graph instead of flattening everything into one list

Primary files:

- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py)
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)

Acceptance criteria:

1. The graph supports direct and inferred relations.
2. Relation type counts and previews are persisted for review payloads.
3. Unsupported order assumptions are surfaced as temporal issues, not silently accepted.

### Layer 4. Timeline consistency and issue detection

Work:

- detect missing anchors
- detect contradictory dates and impossible overlaps
- flag relative-only facts that still need anchoring
- compute partial-order readiness for each claim and packet

Existing seam:

- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py) already computes `build_timeline_consistency_summary(...)`

Acceptance criteria:

1. Each claim gets a machine-readable consistency summary.
2. Warnings are categorized and deduplicated.
3. Operator-visible diagnostics match theorem-layer blocking reasons.

### Layer 5. Legal temporal framing

Work:

- define claim-specific temporal rules for each cause of action
- attach legal windows, trigger conditions, and temporal defenses
- distinguish factual order from legally sufficient order

Examples:

- retaliation: protected activity before adverse action, plus causal proximity heuristics
- wage claims: pay period boundaries and delayed payment windows
- housing discrimination: discriminatory act before denial, eviction, or adverse terms
- probate: death, notice, filing, and estate administration sequence

Primary files:

- [complaint_analysis/decision_trees.py](../complaint_analysis/decision_trees.py)
- [complaint_analysis/legal_patterns.py](../complaint_analysis/legal_patterns.py)
- [complaint_analysis/prompt_templates.py](../complaint_analysis/prompt_templates.py)

Acceptance criteria:

1. Each supported claim type defines a temporal rule profile.
2. The rule profile references required events, optional events, and blocking windows.
3. Legal windows can be evaluated independently of UI rendering.

### Layer 6. Formal theorem export

Work:

- compile timeline facts and relations into TDFOL predicates
- compile event and belief structure into DCEC-compatible expressions
- preserve provenance links from formulas back to fact IDs
- emit both machine-focused and operator-preview representations

Examples:

- `Before(report_hr, termination_notice)`
- `Happens(ReportToHR(employee, discrimination), t1)`
- `Happens(DeliverNotice(employer, termination_notice), t2)`
- `t1 < t2`
- `ProtectedActivity(report_hr)`
- `AdverseAction(termination_notice)`

Primary files:

- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [claim_support_review.py](../claim_support_review.py)
- `integrations/ipfs_datasets/logic.py`

Acceptance criteria:

1. Every exported formula can be traced to source facts and relations.
2. Temporal exports distinguish certain from inferred relations.
3. Formula previews exposed in UI are generated from the same payload used by proof execution.

### Layer 7. Proof and contradiction execution

Work:

- evaluate whether legal temporal frames are satisfied
- prove or fail claim elements using the temporalized fact set
- detect contradiction and defense triggers
- return minimal blocking explanations

Outputs:

- proved predicates
- unproved predicates
- blocking temporal issues
- contradiction candidates
- recommended follow-up actions

Acceptance criteria:

1. Each failed proof identifies missing event or ordering requirements.
2. Contradictions are attached to their source facts and relations.
3. Proof status rolls up cleanly from element to claim to packet.

### Layer 8. Operator review and drafting integration

Work:

- expose timeline ordering and temporal proof handoff in the review UI
- show packet-level temporal readiness in `/claim-support-review`, `/document`, and `/document/optimization-trace`
- use missing anchors and ordering gaps to drive follow-up questions
- prevent drafting readiness from overstating unsupported chronology

Primary files:

- [templates/claim_support_review.html](../templates/claim_support_review.html)
- [templates/document.html](../templates/document.html)
- [templates/optimization_trace.html](../templates/optimization_trace.html)

Acceptance criteria:

1. Operators can see which elements are temporally blocked.
2. Follow-up questions can target timeline anchors directly.
3. Document drafting consumes the same temporal readiness state used by proof review.

## Implementation Roadmap

### Milestone 1. Canonical temporal fact registry

Goal:

- unify testimony, documents, and web evidence into one temporal fact contract

Files to target:

- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py)
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [docs/PAYLOAD_CONTRACTS.md](./PAYLOAD_CONTRACTS.md)

Deliverables:

- canonical temporal fact schema
- canonical temporal relation schema
- provenance contract for source artifact and span refs
- migration path from current `temporal_context` payloads

### Milestone 2. Claim-scoped temporal graph assembly

Goal:

- build stable claim-element and claim-level partial-order graphs

Files to target:

- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py)
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [mediator/mediator.py](../mediator/mediator.py)

Deliverables:

- deterministic relation normalization
- issue categories and severity levels
- packet-level aggregation by claim and element

### Milestone 3. Legal temporal rule profiles

Goal:

- define law-facing temporal expectations for each supported claim type

Files to target:

- [complaint_analysis/decision_trees.py](../complaint_analysis/decision_trees.py)
- [complaint_analysis/legal_patterns.py](../complaint_analysis/legal_patterns.py)
- new claim-type rule profile modules under [complaint_analysis](../complaint_analysis/)

Deliverables:

- temporal rule catalog
- limitations and deadline helpers
- claim-type specific temporal sufficiency evaluator

### Milestone 4. Theorem export and proof execution

Goal:

- compile proof bundles into theorem-ready temporal logic payloads and evaluate them

Files to target:

- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- `integrations/ipfs_datasets/logic.py`
- [claim_support_review.py](../claim_support_review.py)

Deliverables:

- proof bundle compiler
- TDFOL export
- DCEC export
- contradiction and blocking explanation payload

### Milestone 5. Human-in-the-loop review and drafting controls

Goal:

- make temporal proof readiness operationally useful

Files to target:

- [templates/claim_support_review.html](../templates/claim_support_review.html)
- [templates/document.html](../templates/document.html)
- [templates/optimization_trace.html](../templates/optimization_trace.html)

Deliverables:

- timeline gap question prompts
- operator approval workflow for disputed chronology
- drafting readiness gates that respect temporal proof failures

## Data Contract Additions

The payload contract should gain explicit structures for the following.

- `temporal_fact_registry`
- `temporal_relation_registry`
- `temporal_issue_registry`
- `legal_temporal_frames`
- `proof_bundles`
- `theorem_exports`
- `timeline_gap_follow_ups`

Each of these should be claim-aware, element-aware, and provenance-aware.

## Proof Semantics

The theorem layer should distinguish four kinds of temporal proof state.

1. Proven chronology
   Facts and relations are sufficiently grounded to satisfy the legal temporal frame.

2. Plausible but unanchored chronology
   Relative ordering exists, but the timeline still lacks enough anchoring to support proof.

3. Contradicted chronology
   Competing evidence or mutually incompatible date claims prevent reliable proof.

4. Legally irrelevant chronology
   The event ordering may be internally consistent but does not satisfy the governing legal rule.

That distinction matters because the system should ask different follow-up questions in each case.

## Follow-Up Planning Rules

Temporal issues should drive specific next actions.

- missing anchor -> request date-bearing document or exact date testimony
- contradictory dates -> ask source-comparison question and request strongest record
- relative-only ordering -> request anchor event or corroborating document
- limitations risk -> elevate urgency and compute filing deadline impact
- causation gap -> request facts linking protected act and later harm

## Validation Strategy

Validation should be split across four levels.

### Unit tests

- date normalization
- range handling
- relation inference
- contradiction detection
- theorem export

### Integration tests

- testimony plus document ingestion into one timeline
- claim-element temporal proof bundles
- packet summary rollups

### Browser tests

- operator visibility of timeline ordering and temporal proof handoff
- document and optimization trace visibility of packet temporal readiness

### Golden regression cases

- retaliation chronology
- harassment over time
- limitations deadline edge cases
- contradictory termination dates
- range-only and approximate-date cases

Recommended regression slice:

```bash
.venv/bin/python -m pytest \
  tests/test_claim_support_hooks.py \
  tests/test_review_api.py \
  tests/test_claim_support_review_dashboard_flow.py \
  tests/test_claim_support_review_playwright_smoke.py \
  tests/test_mediator_three_phase.py \
  tests/test_intake_status.py -q

.venv/bin/python scripts/run_claim_support_review_regression.py --browser on
```

## Risks and Controls

### Risk 1. False temporal precision

Control:

- never replace approximate or relative evidence with fabricated exact timestamps

### Risk 2. Logic layer drift from UI summaries

Control:

- UI previews should render directly from the same payload used by theorem export and proof execution

### Risk 3. Claim-specific legal timing rules remain too generic

Control:

- make temporal rule profiles explicit per claim type rather than embedding them in generic prompts

### Risk 4. Contradictions become opaque to operators

Control:

- every temporal issue must reference the underlying fact IDs, sources, and recommended follow-up path

## Immediate Next Build Slice

The best next slice is not more UI. It is the canonical timeline registry that sits between evidence collection and theorem export.

That slice should do the following.

1. Define canonical temporal fact and relation schemas in the payload contract.
2. Normalize testimony, parsed document facts, and proof leads into one claim-scoped registry.
3. Persist relation provenance and issue categories in `mediator/claim_support_hooks.py`.
4. Add claim-type temporal rule profile scaffolding for retaliation first.
5. Export one proof bundle per claim element with fact IDs, relation IDs, and legal temporal frame IDs.

If that slice lands cleanly, the theorem layer and operator review layer can evolve on top of a stable substrate instead of re-deriving chronology in multiple places.