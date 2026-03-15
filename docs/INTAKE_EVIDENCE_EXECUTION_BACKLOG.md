# Intake And Evidence Execution Backlog

Date: 2026-03-15
Status: Active execution backlog

Companion docs:

- `docs/INTAKE_EVIDENCE_IMPROVEMENT_PLAN.md`
- `complaint_phases/README.md`
- `docs/EVIDENCE_MANAGEMENT.md`
- `docs/ARCHITECTURE.md`
- `docs/PAYLOAD_CONTRACTS.md`

## Purpose

Translate the Phase 1 and Phase 2 improvement roadmap into implementation-sized work packages tied to the current state of complaint-generator.

This backlog assumes the repo already has:

- three-phase orchestration under `complaint_phases/phase_manager.py`
- graph-backed intake under `knowledge_graph.py`, `dependency_graph.py`, and `denoiser.py`
- complaint typing and decision tree assets under `complaint_analysis/`
- evidence storage, metadata, and analysis hooks through the mediator and IPFS-backed evidence management
- adversarial harness coverage for question quality and gap behavior

The goal now is not to redesign the system abstractly. The goal is to improve how the mediator gathers facts in intake and how the system organizes evidence into proof-ready support structures for the complaint.

## Execution Principles

1. Keep `complaint_phases/` as the canonical workflow model for intake, evidence, and formalization.
2. Treat proof readiness as the organizing principle for both questioning and evidence collection.
3. Prefer thin vertical slices that improve question quality, chronology quality, or support clarity immediately.
4. Preserve degraded-mode behavior when advanced graph, search, or extraction features are unavailable.
5. Make every transition from Phase 1 to Phase 2 explainable with named blockers and readiness metrics.
6. Make every Phase 2 support decision traceable to facts, artifacts, witnesses, or explicit gaps.

## Current Baseline

## Completed or substantially in place

- `PhaseManager` already tracks phase state, transitions, and coarse completion gates
- `ComplaintDenoiser` already generates gap-driven questions and tracks iterative denoising state
- `KnowledgeGraph` and `DependencyGraph` already support entity extraction, requirement tracking, and gap discovery
- evidence storage already persists artifacts, metadata, graph projections, and extracted facts
- complaint-analysis assets already provide claim typing, keywords, legal patterns, and decision tree material
- adversarial harness already measures question quality, extraction quality, empathy, efficiency, and coverage

## Still shallow or incomplete

- Phase 1 still uses coarse completion rules rather than true intake-readiness gates
- question planning is still gap-aware but not fully proof-objective-aware
- chronology is not yet a first-class event model across sessions
- contradiction and ambiguity tracking are not yet strong enough to block or redirect intake intelligently
- Phase 2 has evidence storage and persistence, but not yet a claim-element-to-evidence proof matrix
- evidence requests are not yet systematically derived from unsatisfied legal requirements
- support sufficiency is not yet explicit enough for formal complaint readiness decisions

## Status Legend

- `Complete`: implemented enough to be treated as baseline
- `In Progress`: partially implemented and actively extendable
- `Planned`: designed but not yet implemented
- `Deferred`: useful but lower priority than the current roadmap

## Workstream Overview

| ID | Workstream | Status | Priority | Outcome |
|---|---|---|---|---|
| W1 | Intake schema and readiness gates | Planned | P0 | Intake becomes structured and complaint-type-aware |
| W2 | Goal-directed question planning | Planned | P0 | Questions are prioritized by proof value |
| W3 | Chronology and event modeling | Planned | P0 | Fact timelines become reliable and queryable |
| W4 | Ambiguity, contradiction, and confidence tracking | Planned | P0 | Uncertainty becomes explicit and actionable |
| W5 | Element-to-evidence matrix | Planned | P0 | Phase 2 can explain support by legal element |
| W6 | Evidence request planning | Planned | P1 | Missing proof becomes concrete next-step evidence asks |
| W7 | Evidence normalization and provenance | Planned | P1 | Evidence becomes a reusable proof substrate |
| W8 | Support sufficiency and readiness scoring | Planned | P0 | Formalization can distinguish strong from weak support |
| W9 | Phase summaries and operator visibility | Planned | P1 | Users and developers can inspect blockers and progress |
| W10 | Adversarial and regression validation | Planned | P0 | Improvements are measurable and test-enforced |

## M0: Intake Readiness Foundation

Status: Planned
Priority: P0

### Goal

Replace generic Phase 1 completion with complaint-aware intake readiness.

### Primary files

- `complaint_phases/phase_manager.py`
- `complaint_phases/dependency_graph.py`
- `complaint_analysis/decision_trees.py`
- `complaint_analysis/complaint_types.py`

### Checklist

- [ ] define a baseline intake schema shared across complaint types
- [ ] add complaint-type-specific required intake fields derived from decision trees and claim elements
- [ ] add `intake_readiness_score` to phase data
- [ ] add named blockers such as `missing_timeline`, `missing_actor`, `missing_injury`, `missing_proof_leads`, and `contradiction_unresolved`
- [ ] replace coarse gap-only transition logic with readiness-based transition logic

### Acceptance criteria

- intake completion can be explained with a score plus named blockers
- complaint types can require different minimum fact sets before entering Phase 2

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_phase_manager.py -q`
- `./.venv/bin/python -m pytest tests/test_probate_integration.py -q`

## M1: Proof-Directed Question Planner

Status: Planned
Priority: P0

### Goal

Make Phase 1 questions target proof gain rather than only graph incompleteness.

### Primary files

- `complaint_phases/denoiser.py`
- `complaint_phases/dependency_graph.py`
- `complaint_phases/knowledge_graph.py`

### Checklist

- [ ] define question objectives such as chronology, actor identity, causation, injury, protected basis, notice, and corroboration
- [ ] rank candidate questions by expected element coverage gain
- [ ] suppress near-duplicate proof objectives across turns
- [ ] track question novelty and proof yield in denoiser state
- [ ] expose question reasons for later UI and adversarial reporting

### Acceptance criteria

- question plans can state what legal or proof objective each question serves
- repetitive questioning decreases without lowering element coverage

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_adversarial_harness.py -q`
- `./.venv/bin/python -m pytest tests/test_sgd_cycle_integration.py -q`

## M2: Chronology And Event Extraction

Status: Planned
Priority: P0

### Goal

Turn timeline capture into a first-class capability.

### Primary files

- `complaint_phases/knowledge_graph.py`
- `complaint_phases/denoiser.py`
- `complaint_phases/phase_manager.py`

### Checklist

- [ ] add explicit event nodes with actor, target, action, date, location, and consequence
- [ ] add event ordering and chronology completeness checks
- [ ] detect key sequencing ambiguities for retaliation, discrimination, and notice-based claims
- [ ] generate chronology-specific follow-up questions when event order is unclear

### Acceptance criteria

- major events are represented as ordered graph objects rather than only free text
- chronology blockers can prevent premature Phase 2 advancement when sequence matters legally

### Suggested validation

- targeted unit tests for event extraction and ordering
- adversarial retaliation smoke runs with chronology assertions

## M3: Ambiguity And Contradiction Layer

Status: Planned
Priority: P0

### Goal

Distinguish missing facts from contradictory or low-confidence facts.

### Primary files

- `complaint_phases/knowledge_graph.py`
- `complaint_phases/denoiser.py`
- `complaint_phases/phase_manager.py`

### Checklist

- [ ] add ambiguity markers for unresolved party identity, dates, injuries, and actions
- [ ] add contradiction markers for conflicting timeline or fact statements
- [ ] track confidence at fact and element level
- [ ] generate clarification questions only when contradiction materially affects proof readiness

### Acceptance criteria

- intake summaries identify unresolved ambiguity separately from raw missingness
- contradiction resolution is visible in phase state and metrics

### Suggested validation

- targeted graph and denoiser tests for ambiguity and contradiction scenarios

## M4: Element-To-Evidence Matrix

Status: Planned
Priority: P0

### Goal

Give Phase 2 a durable proof structure instead of treating evidence as only stored artifacts.

### Primary files

- `complaint_phases/dependency_graph.py`
- `mediator/evidence_hooks.py`
- `mediator/claim_support_hooks.py`
- `docs/PAYLOAD_CONTRACTS.md`

### Checklist

- [ ] define a support matrix keyed by claim element or required fact
- [ ] link each element to supporting facts, evidence artifacts, witnesses, and authorities
- [ ] classify support type as direct, circumstantial, testimony-only, documentary, or missing
- [ ] add support strength labels per element

### Acceptance criteria

- every claim element can be explained with a support row
- formalization can consume the matrix directly rather than reconstructing support ad hoc

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_document_pipeline.py -q`
- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q`

## M5: Evidence Request Planner

Status: Planned
Priority: P1

### Goal

Generate specific next-step evidence asks from proof gaps.

### Primary files

- `complaint_phases/phase_manager.py`
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- review-surface payload builders

### Checklist

- [ ] map unsatisfied requirements to concrete evidence request categories
- [ ] prioritize evidence asks by legal value and likely user availability
- [ ] distinguish user-upload requests from auto-discovery or search tasks
- [ ] store evidence requests as durable plan items rather than only transient suggestions

### Acceptance criteria

- the system can explain which evidence artifact would most improve a weak element
- users receive concrete evidence requests rather than vague “more evidence needed” summaries

### Suggested validation

- support-review and follow-up planner tests
- browser or API tests for evidence-request rendering

## M6: Evidence Normalization And Provenance

Status: Planned
Priority: P1

### Goal

Preserve artifact-level and fact-level provenance strongly enough for proof tracing.

### Primary files

- `mediator/evidence_hooks.py`
- `integrations/ipfs_datasets/provenance.py`
- `docs/EVIDENCE_MANAGEMENT.md`
- `docs/PAYLOAD_CONTRACTS.md`

### Checklist

- [ ] normalize extracted evidence facts to include artifact, chunk, source, and transform lineage
- [ ] distinguish user-supplied, discovered, authority-derived, and inferred support
- [ ] preserve provenance when facts are linked into graphs and support ledgers

### Acceptance criteria

- support rows can trace back to concrete sources and extraction lineage
- provenance survives from ingestion through review and drafting

## M7: Support Sufficiency And Proof Readiness

Status: Planned
Priority: P0

### Goal

Make Phase 2 completion depend on support adequacy, not mere evidence presence.

### Primary files

- `complaint_phases/dependency_graph.py`
- `complaint_phases/phase_manager.py`
- mediator support-summary builders

### Checklist

- [ ] add element-level sufficiency labels: `unsupported`, `weak`, `moderate`, `strong`
- [ ] distinguish testimony-only support from corroborated support
- [ ] add `proof_readiness_score` for Phase 2
- [ ] add named proof blockers for formalization

### Acceptance criteria

- formalization can tell whether a complaint is complaint-ready but not proof-ready
- unsupported core elements are explicit before drafting begins

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_document_pipeline.py -q`
- `./.venv/bin/python -m pytest tests/test_parallel_validation_fix.py -q`

## M8: Phase Summaries And Review Visibility

Status: Planned
Priority: P1

### Goal

Generate reusable structured summaries at the end of intake and evidence phases.

### Primary files

- phase summary emitters in mediator or complaint-phase adapters
- review payload builders
- `docs/PAYLOAD_CONTRACTS.md`

### Checklist

- [ ] produce a compact phase summary with claim theory, timeline, strongest facts, unresolved ambiguity, evidence on hand, and evidence still needed
- [ ] ensure the summary can be consumed by review surfaces, adversarial harness reporting, and complaint drafting
- [ ] add degraded-mode placeholders when graph or evidence enrichment is limited

### Acceptance criteria

- operators and future drafting flows can inspect phase progress without reconstructing it from raw graph state

## M9: Validation Harness And Metrics

Status: Planned
Priority: P0

### Goal

Measure whether the intake and evidence improvements actually help the complaint workflow.

### Primary files

- `adversarial_harness/critic.py`
- `adversarial_harness/harness.py`
- targeted complaint-phase tests

### Checklist

- [ ] add Phase 1 metrics for chronology completeness, contradiction count, duplicate-question rate, and proof-lead density
- [ ] add Phase 2 metrics for element support sufficiency and proof readiness
- [ ] add regression fixtures for retaliation, discrimination, housing, and consumer flows
- [ ] update critic prompts or scoring structures to reflect new phase goals

### Acceptance criteria

- quality improvements are measurable in adversarial batch runs, not just subjectively described
- regressions in intake precision or proof readiness are test-detectable

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_adversarial_harness.py -q`
- `./.venv/bin/python -m pytest tests/test_document_pipeline.py -q --run-llm`

## Recommended Execution Sequence

1. M0: Intake readiness foundation
2. M1: Proof-directed question planner
3. M2: Chronology and event extraction
4. M3: Ambiguity and contradiction layer
5. M4: Element-to-evidence matrix
6. M7: Support sufficiency and proof readiness
7. M5: Evidence request planner
8. M6: Evidence normalization and provenance
9. M8: Phase summaries and review visibility
10. M9: Validation harness and metrics

## First Batch Recommendation

The highest-leverage first coding batch is:

- add intake readiness score and blockers in `PhaseManager`
- add proof-objective question ranking in `ComplaintDenoiser`
- add explicit chronology completeness checks in graph state

This batch improves question quality immediately without forcing a full evidence-contract redesign first.

## Definition Of Done For The First Milestone

The first milestone should be considered complete only if:

- intake no longer advances solely because graph objects exist and gap count fell below a threshold
- the mediator can explain why it is asking each next question
- chronology quality improves in representative adversarial sessions
- named blockers are emitted when intake is not yet ready for evidence organization

## Summary

This backlog turns the improvement plan into a delivery sequence centered on one principle: Phase 1 and Phase 2 should behave like a proof-building pipeline.

If executed in the order above, the mediator will collect better facts, ask more targeted questions, organize supporting material by legal element, and hand later drafting stages a much stronger factual and evidentiary record.