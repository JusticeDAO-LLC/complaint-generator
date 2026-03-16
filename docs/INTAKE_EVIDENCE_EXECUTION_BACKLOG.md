# Intake and Evidence Execution Backlog

Date: 2026-03-15
Status: Active execution backlog

Companion docs:

- [docs/INTAKE_EVIDENCE_IMPROVEMENT_PLAN.md](/home/barberb/complaint-generator/docs/INTAKE_EVIDENCE_IMPROVEMENT_PLAN.md)
- [docs/ARCHITECTURE.md](/home/barberb/complaint-generator/docs/ARCHITECTURE.md)
- [docs/EVIDENCE_MANAGEMENT.md](/home/barberb/complaint-generator/docs/EVIDENCE_MANAGEMENT.md)
- [docs/PAYLOAD_CONTRACTS.md](/home/barberb/complaint-generator/docs/PAYLOAD_CONTRACTS.md)

## Purpose

This backlog translates the intake and evidence improvement roadmap into implementation-sized work packages tied to the current complaint-generator architecture.

The emphasis is execution, not redesign. The repo already has the core primitives. The backlog focuses on making Phase 1 and Phase 2 more explicit, more measurable, and more proof-oriented.

## Execution Principles

1. Keep [complaint_phases/phase_manager.py](/home/barberb/complaint-generator/complaint_phases/phase_manager.py) as the canonical workflow controller.
2. Keep normalized state and summaries in mediator and phase modules, not in application-layer request builders.
3. Treat claim-element proof readiness as the organizing principle for both phases.
4. Prefer thin vertical slices that improve behavior immediately and preserve degraded-mode operation.
5. Preserve provenance and lineage across intake facts, support tasks, artifacts, testimony, and support packets.

## Workstream Map

| ID | Workstream | Priority | Outcome |
|---|---|---|---|
| W1 | Intake schema and answer normalization | P0 | Intake emits reusable, structured case facts |
| W2 | Proof-directed question planning | P0 | Questions are ranked by proof gain and novelty |
| W3 | Claim ambiguity and contradiction workflow | P0 | Uncertainty becomes explicit and actionable |
| W4 | Minimum fact bundles and evidence tasks | P0 | Phase 2 can operate on concrete support objectives |
| W5 | Support-lane unification and provenance quality | P1 | Documents, testimony, authority, and web records share one support model |
| W6 | Proof-readiness scoring and phase gates | P0 | Phase transitions depend on real support quality |
| W7 | Review and trace payload expansion | P1 | Operators can inspect why a case is or is not ready |
| W8 | Adversarial and regression enforcement | P0 | Improvements are measurable and test-protected |

## Batch 1: Intake Structure Foundation

Status: Planned
Priority: P0

### Goal

Make Phase 1 emit structured state that can drive evidence tasks directly.

### Primary files

- [complaint_phases/intake_case_file.py](/home/barberb/complaint-generator/complaint_phases/intake_case_file.py)
- [mediator/mediator.py](/home/barberb/complaint-generator/mediator/mediator.py)
- [intake_status.py](/home/barberb/complaint-generator/intake_status.py)

### Tasks

- [ ] expand `proof_leads` with owner, availability, expected format, retrieval path, and target linkage
- [ ] expand `open_items` with blocking level, next-question strategy, and target element metadata
- [ ] add stable `fact_id` and element-link fields to canonical facts
- [ ] preserve new intake fields in `get_three_phase_status()` outputs and `intake_status` summaries

### Acceptance criteria

- a single intake answer can produce structured facts and proof leads with stable references
- unresolved intake work is visible as explicit queue items instead of implicit narrative gaps

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_mediator_three_phase.py -q`
- `./.venv/bin/python -m pytest tests/test_intake_status.py -q`

## Batch 2: Proof-Directed Question Planner

Status: Planned
Priority: P0

### Goal

Make question selection optimize for proof gain, not only generic gap reduction.

### Primary files

- [complaint_phases/denoiser.py](/home/barberb/complaint-generator/complaint_phases/denoiser.py)
- [mediator/mediator.py](/home/barberb/complaint-generator/mediator/mediator.py)

### Tasks

- [ ] add expected update kind and proof-gain metadata to question candidates
- [ ] rank questions by claim criticality, contradiction risk, and novelty
- [ ] suppress duplicate question objectives using semantic similarity or recent-objective tracking
- [ ] emit question reasons for UI, traces, and adversarial scoring

### Router dependencies

- LLM router: structured question phrasing and contradiction clarification prompts
- embeddings router: duplicate-question suppression and similarity clustering

### Acceptance criteria

- the mediator can explain what proof objective each question serves
- repeated questions fall without reducing claim-element coverage

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_mediator.py -q`
- `./.venv/bin/python -m pytest tests/test_mediator_three_phase.py -q`

## Batch 3: Claim Ambiguity and Contradiction Workflow

Status: Planned
Priority: P0

### Goal

Separate missingness from ambiguity and contradiction, and route each one differently.

### Primary files

- [complaint_phases/phase_manager.py](/home/barberb/complaint-generator/complaint_phases/phase_manager.py)
- [mediator/mediator.py](/home/barberb/complaint-generator/mediator/mediator.py)
- [intake_status.py](/home/barberb/complaint-generator/intake_status.py)

### Tasks

- [ ] add contradiction severity and resolution-lane metadata
- [ ] add ambiguity flags for dates, actors, conduct, and injury
- [ ] add readiness blockers for unresolved blocking contradictions and unresolved claim disambiguation
- [ ] route contradictions into testimony, document, or external-record tasks where appropriate

### Acceptance criteria

- intake summaries distinguish contradiction from generic missingness
- blocking contradictions prevent silent advancement to evidence phase

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_mediator.py -q`
- `./.venv/bin/python -m pytest tests/test_intake_status.py -q`

## Batch 4: Minimum Fact Bundles and Evidence Task Board

Status: Planned
Priority: P0

### Goal

Turn support gaps into concrete, element-level evidence tasks.

### Primary files

- [mediator/claim_support_hooks.py](/home/barberb/complaint-generator/mediator/claim_support_hooks.py)
- [mediator/mediator.py](/home/barberb/complaint-generator/mediator/mediator.py)
- [complaint_phases/phase_manager.py](/home/barberb/complaint-generator/complaint_phases/phase_manager.py)
- [complaint_phases/denoiser.py](/home/barberb/complaint-generator/complaint_phases/denoiser.py)

### Tasks

- [ ] emit `missing_fact_bundle` and `satisfied_fact_bundle` per claim element during support validation
- [ ] enrich `alignment_evidence_tasks` with task id, fallback lanes, source-quality target, and resolution notes
- [ ] connect proof leads to target tasks through stable references
- [ ] use prioritized tasks as the canonical Phase 2 next-action source

### Acceptance criteria

- every unresolved element produces an explainable task with a concrete success target
- evidence questioning in Phase 2 is driven from task structure rather than generic prompts

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_mediator_three_phase.py -q`
- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q`

## Batch 5: Support Lane Unification and Provenance Quality

Status: Planned
Priority: P1

### Goal

Make documentary evidence, testimony, authority, and web captures comparable support lanes.

### Primary files

- [mediator/evidence_hooks.py](/home/barberb/complaint-generator/mediator/evidence_hooks.py)
- [mediator/claim_support_hooks.py](/home/barberb/complaint-generator/mediator/claim_support_hooks.py)
- [docs/EVIDENCE_MANAGEMENT.md](/home/barberb/complaint-generator/docs/EVIDENCE_MANAGEMENT.md)

### Tasks

- [ ] normalize provenance fields across artifact and testimony records
- [ ] add support-quality labels that distinguish testimony-only, documentary, corroborated, and contradicted states
- [ ] preserve lane identity and quality through support summaries and snapshots
- [ ] persist meaningful case-theory or support-packet snapshots through the IPFS-backed path when state materially changes

### Router dependencies

- IPFS router: content-addressed snapshots and artifact lineage
- embeddings router: artifact and testimony grouping around shared events or facts

### Acceptance criteria

- support summaries can explain not only whether support exists, but what type and quality of support exists
- operators can trace packet conclusions back to stored source lineage

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py -q`
- `./.venv/bin/python -m pytest tests/test_document_pipeline.py -q`

## Batch 6: Proof-Readiness Gates

Status: Planned
Priority: P0

### Goal

Make Phase 1 and Phase 2 transitions depend on semantic readiness, not just coarse gap counts.

### Primary files

- [complaint_phases/phase_manager.py](/home/barberb/complaint-generator/complaint_phases/phase_manager.py)
- [mediator/mediator.py](/home/barberb/complaint-generator/mediator/mediator.py)

### Tasks

- [ ] add semantic intake gates such as `case_theory_coherent` and `minimum_proof_path_present`
- [ ] add evidence metrics such as `credible_support_ratio` and `draft_ready_element_ratio`
- [ ] gate formalization on proof-readiness score and explicit blocker lists
- [ ] preserve these metrics through review and optimization summaries

### Acceptance criteria

- a case can be complaint-ready but not proof-ready, and that difference is explicit
- unsupported core elements are surfaced before drafting starts

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_document_pipeline.py -q`
- `./.venv/bin/python -m pytest tests/test_parallel_validation_fix.py -q`

## Batch 7: Review and Trace Surfaces

Status: Planned
Priority: P1

### Goal

Expose the new intake and evidence state cleanly to operators and optimizer traces.

### Primary files

- [intake_status.py](/home/barberb/complaint-generator/intake_status.py)
- [applications/review_api.py](/home/barberb/complaint-generator/applications/review_api.py)
- [applications/document_api.py](/home/barberb/complaint-generator/applications/document_api.py)
- [templates/claim_support_review.html](/home/barberb/complaint-generator/templates/claim_support_review.html)
- [templates/document.html](/home/barberb/complaint-generator/templates/document.html)
- [templates/optimization_trace.html](/home/barberb/complaint-generator/templates/optimization_trace.html)

### Tasks

- [ ] expose new confidence, ambiguity, and proof-quality fields in normalized summaries
- [ ] show blocking tasks, contradiction lanes, and proof-readiness signals on review surfaces
- [ ] preserve architecture boundaries by keeping payload shaping out of application-only logic where possible
- [ ] ensure optimizer traces retain the expanded intake and evidence state

### Acceptance criteria

- operators can explain why a case is blocked without inspecting raw graph or ledger rows
- traces can replay the intake-to-evidence progression coherently

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_review_api.py -q`
- `./.venv/bin/python -m pytest tests/test_claim_support_review_playwright_smoke.py -q`

## Batch 8: Validation Harness and Metrics

Status: Planned
Priority: P0

### Goal

Make the improvements measurable in automated runs.

### Primary files

- [adversarial_harness/harness.py](/home/barberb/complaint-generator/adversarial_harness/harness.py)
- [adversarial_harness/critic.py](/home/barberb/complaint-generator/adversarial_harness/critic.py)
- targeted complaint-phase tests

### Tasks

- [ ] add Phase 1 metrics for chronology completeness, contradiction count, duplicate-question rate, and proof-lead density
- [ ] add Phase 2 metrics for support sufficiency, support quality, and proof readiness
- [ ] add fixtures for retaliation, discrimination, housing, and consumer scenarios with distinct proof burdens
- [ ] update critic prompts or scoring rubrics to reward question relevance and proof progress instead of verbosity

### Acceptance criteria

- improvements are visible in adversarial batches, not only in manual demos
- regressions in proof readiness or question precision become test-detectable

### Suggested validation

- `./.venv/bin/python -m pytest tests/test_adversarial_harness.py -q`
- `./.venv/bin/python -m pytest tests/test_document_pipeline.py -q --run-llm`

## Recommended Execution Order

1. Batch 1: Intake structure foundation
2. Batch 2: Proof-directed question planner
3. Batch 3: Claim ambiguity and contradiction workflow
4. Batch 4: Minimum fact bundles and evidence task board
5. Batch 6: Proof-readiness gates
6. Batch 5: Support lane unification and provenance quality
7. Batch 7: Review and trace surfaces
8. Batch 8: Validation harness and metrics

## First Coding Slice Recommendation

The best first coding slice is:

1. expand intake proof leads and open items
2. normalize answer application into element-linked canonical facts
3. enrich alignment evidence tasks with success criteria and fallback lanes
4. emit minimum fact bundles from support validation
5. extend phase gates with proof-readiness metrics

That slice improves intake, evidence organization, and review surfaces at the same time with manageable code churn.
