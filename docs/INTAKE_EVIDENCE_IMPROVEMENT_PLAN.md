# Intake and Evidence Improvement Plan

Date: 2026-03-20
Status: Active roadmap

## Scope

This plan covers the first two complaint workflow phases:

1. Phase 1: intake, where the mediator questions the complainant and turns narrative answers into structured case facts.
2. Phase 2: evidence organization, where the system converts claim-element gaps into concrete support tasks and assembles proof-ready packets for drafting.

The goal is to make the first two phases behave like one proof-building pipeline instead of two loosely connected steps.

## Current Baseline

The repository already has the correct architectural building blocks:

- [complaint_phases/intake_case_file.py](/home/barberb/complaint-generator/complaint_phases/intake_case_file.py) builds `candidate_claims`, `canonical_facts`, `proof_leads`, `contradiction_queue`, `open_items`, and `intake_sections`.
- [complaint_phases/phase_manager.py](/home/barberb/complaint-generator/complaint_phases/phase_manager.py) already emits intake readiness, blockers, evidence next actions, and phase transitions.
- [complaint_phases/denoiser.py](/home/barberb/complaint-generator/complaint_phases/denoiser.py) already generates intake and evidence questions, including alignment-task-driven evidence prompts.
- [mediator/mediator.py](/home/barberb/complaint-generator/mediator/mediator.py) already exposes claim support, support gaps, validation, testimony persistence, support documents, contradiction diagnostics, and evidence-phase orchestration.
- [mediator/claim_support_hooks.py](/home/barberb/complaint-generator/mediator/claim_support_hooks.py) already persists claim elements, support links, follow-up execution, snapshots, and testimony.
- [mediator/evidence_hooks.py](/home/barberb/complaint-generator/mediator/evidence_hooks.py) already provides artifact storage, metadata, graph projection, and fact extraction.
- [intake_status.py](/home/barberb/complaint-generator/intake_status.py) already exposes additive cross-phase summaries used by review and optimization surfaces.

The missing piece is not major new infrastructure. The missing piece is tighter control over how facts, claim elements, proof leads, and evidence tasks are generated, linked, scored, and advanced.

## Current Execution Seams

The current intake-to-evidence path is already concentrated in a small number of functions. Any chronology-first improvement should be wired into these seams instead of creating a parallel workflow.

- [mediator/mediator.py](../mediator/mediator.py) `start_three_phase_process(...)` initializes the knowledge graph, dependency graph, intake case file, timeline sync, and first denoising questions.
- [mediator/mediator.py](../mediator/mediator.py) `process_denoising_answer(...)` is the main Phase 1 update loop. It applies answers, refreshes the intake case file, re-syncs the dependency graph timeline, and recalculates next questions and readiness.
- [mediator/mediator.py](../mediator/mediator.py) `_apply_intake_answer_to_case_file(...)` is the decisive answer-normalization seam. It already appends canonical facts, proof leads, contradiction records, and timeline facts, but it does not yet maintain a first-class event ledger.
- [mediator/mediator.py](../mediator/mediator.py) `advance_to_evidence_phase(...)` builds `claim_support_packets`, then derives `intake_evidence_alignment_summary` and `alignment_evidence_tasks` from the intake handoff.
- [mediator/mediator.py](../mediator/mediator.py) `_summarize_intake_evidence_alignment(...)` and `_build_alignment_evidence_tasks(...)` are the main Phase 2 translation seams from intake structure into evidence work items.
- [complaint_phases/phase_manager.py](../complaint_phases/phase_manager.py) `get_intake_readiness(...)` and `_build_evidence_packet_summary(...)` are the workflow gates. If chronology needs to matter operationally, it has to affect these summaries.
- [intake_status.py](../intake_status.py) `build_intake_case_review_summary(...)` is the cross-phase boundary for review, optimization, and document surfaces. Any new chronology ledger has to survive this builder unchanged.

## Chronology-Specific Gap

The code already captures timeline-adjacent data, but not yet as a canonical timeline object shared by both phases.

- Phase 1 stores chronology mainly as canonical facts, anchor summaries, contradiction records, and dependency-graph diagnostics.
- Phase 2 identifies temporal work mainly by inspecting claim-support packet element metadata such as `temporal_rule_status`, `temporal_rule_blocking_reasons`, and `temporal_rule_follow_ups`.
- The current handoff is therefore summary-driven. It can explain chronology gaps, but it does not yet carry a durable event ledger with stable event IDs, relation IDs, anchor IDs, and provenance links.
- That creates a risk of recomputing chronology from packet summaries instead of carrying forward the exact events and relations the theorem layer will need.
- The next iteration should make timeline state first-class in the intake case file, then let evidence tasks, readiness gates, and proof exports read from that ledger.

## Diagnosis

### Phase 1 weaknesses

- Intake questions are gap-aware, but not consistently proof-objective-aware.
- Answers are not normalized deeply enough into actor, act, target, date, harm, remedy, and proof-source fields.
- `proof_leads` describe that support might exist, but not reliably who controls it, how it can be obtained, or what claim element it would satisfy.
- Contradictions are surfaced, but are not yet managed as a first-class resolution workflow with escalation rules.
- Intake readiness still leans too much on graph presence and gap thresholds instead of claim-element proof readiness.

### Phase 2 weaknesses

- Evidence review is stronger than evidence execution. The system can describe support gaps, but the workflow for closing them is still too implicit.
- `alignment_evidence_tasks` are useful but not yet rich enough to operate as the canonical Phase 2 task board.
- Evidence sufficiency is still too close to presence counting and not explicit enough about support quality, provenance quality, and claim-element closure.
- Testimony exists as a strong fallback lane, but Phase 2 does not yet elevate it as a default continuation path when documentary support is sparse.
- The system can identify weak elements, but it does not always explain the minimum missing fact bundle that would convert a weak element into a draft-ready one.

## Design Principles

1. Every Phase 1 question must improve claim certainty, resolve contradiction, or create an actionable proof path.
2. Every accepted intake answer must become structured state, not just additional narrative text.
3. Every core claim element must map to a minimum fact bundle.
4. Every unresolved minimum fact bundle must map to a concrete evidence task.
5. Every evidence task must map back to intake facts and forward to draftable allegations.
6. Every proof conclusion must retain provenance to artifact, testimony, authority, or explicit inference.
7. Review surfaces should read from normalized status and ledger objects rather than reconstructing logic in the UI layer.

## Router Roles

This roadmap assumes the system continues to use the existing routing stack and clarifies the intended role of each router during the first two phases.

### LLM router

Use the LLM router for:

- complaint-type-aware intake question generation
- contradiction summarization and reconciliation prompts
- structured answer extraction into canonical fact candidates
- claim disambiguation reasoning and explanation strings
- evidence-task query drafting and witness-question drafting
- packet summarization for review and drafting handoff

The LLM router should not be the source of truth for state. It should propose structure and language, while the mediator and phase modules own normalized state.

### Embeddings router

Use the embeddings router for:

- clustering semantically duplicate facts across multiple complainant answers
- matching intake facts to claim elements and existing proof leads
- deduplicating evidence tasks that target the same missing fact bundle
- grouping evidence artifacts, testimony, and support traces around the same event or element
- measuring novelty so the denoiser can suppress repetitive questioning

The embeddings router should act as a similarity and grouping substrate, not as the final legal validator.

### IPFS router

Use the IPFS router for:

- immutable storage of evidence artifacts and extracted derivative records
- versioned snapshots of intake case theory and evidence packets when those states materially change
- reproducible traceability from support packet to stored artifact lineage
- content-addressed persistence for optimization traces and replayable intake or evidence summaries

The IPFS layer should be treated as the persistence and lineage backbone, not as the workflow engine.

## Target State

At the end of this work, the system should behave like this:

- Phase 1 ends with a structured case theory, not just a reduced-gap conversation.
- The mediator can explain why each next question is being asked and what element or contradiction it targets.
- Each leading claim has explicit required elements, a current support status, and a named minimum fact bundle.
- Phase 2 starts with a task board of support objectives instead of a generic "gather more evidence" state.
- Documents, testimony, authority, web captures, and external records are treated as support lanes under one claim-element framework.
- Every core element can be explained in a packet that answers: what facts support it, what sources support those facts, what remains missing, and what next step would most improve the complaint.

## Phase 1 Plan: Intake and Questioning

### 1. Make the intake case file the canonical case-theory object

Expand the structures built in [complaint_phases/intake_case_file.py](/home/barberb/complaint-generator/complaint_phases/intake_case_file.py) so Phase 1 produces an authoritative case-theory record.

Strengthen or add these fields:

- `candidate_claims`: include confidence, reasons, ambiguity flags, and disambiguation prompts.
- `canonical_facts`: include stable ids, claim tags, element tags, confidence, materiality, and provenance hints.
- `proof_leads`: include owner, availability, expected format, retrieval path, authenticity risk, privacy risk, element targets, fact targets, and priority.
- `open_items`: include blocking level, reason, next-question strategy, and element linkage.
- `summary_snapshots`: include diff-friendly iteration summaries for review and optimization trace replay.
- `timeline_anchors`: capture exact dates, ranges, approximations, and sequence-only anchors.
- `harm_profile` and `remedy_profile`: promote harm and requested relief into structured state instead of leaving them as incidental facts.

### 2. Make Phase 1 questions explicitly fact-extractive

Question generation in [complaint_phases/denoiser.py](/home/barberb/complaint-generator/complaint_phases/denoiser.py) should continue to be gap-aware, but each question should have an expected state update contract.

Required question families:

- chronology
- actor or role
- conduct or event
- harm
- remedy
- claim-element satisfaction
- corroboration or proof-source
- contradiction resolution
- claim disambiguation

Each question should carry:

- `question_objective`
- `target_claim_type`
- `target_element_id`
- `expected_update_kind`
- `priority_reason`
- `novelty_score`
- `expected_proof_gain`

### 3. Normalize answers into a minimal fact schema

Upgrade the intake answer application path in [mediator/mediator.py](/home/barberb/complaint-generator/mediator/mediator.py) so accepted answers become structured, cross-phase-usable facts.

Each fact should support:

- `fact_id`
- `text`
- `fact_type`
- `claim_types`
- `element_tags`
- `actor_refs`
- `target_refs`
- `event_date_or_range`
- `location`
- `source_kind`
- `source_ref`
- `confidence`
- `needs_corroboration`
- `materiality`
- `contradiction_group_id`

The important change is not just a richer schema. The important change is to ensure that answer application produces stable, linkable objects that Phase 2 can reason over.

### 3A. Introduce a canonical event ledger during answer application

The current answer path in [mediator/mediator.py](../mediator/mediator.py) already knows when a response is about chronology, evidence, responsible actors, and claim elements. That is the right place to build a first-class event ledger instead of trying to reconstruct one later.

Add or strengthen these structures in the intake case file:

- `event_ledger`: canonical event records with stable `event_id`, actor refs, target refs, event label, date or range, location, and provenance refs
- `timeline_anchors`: explicit anchor objects for exact dates, approximate dates, ranges, deadlines, and sequence-only anchors
- `timeline_relations`: normalized `before`, `after`, `during`, `overlaps`, `meets`, and contradiction-aware relations between event IDs
- `timeline_issues`: unresolved chronology gaps such as missing anchors, contradictory ordering, unsupported sequence assumptions, and limitations risk
- `event_support_refs`: links from events to canonical facts, proof leads, testimony rows, document spans, and later evidence artifacts

Implementation rule:

- `_apply_intake_answer_to_case_file(...)` should append or update event records at the same time it appends canonical facts.
- `sync_intake_timeline_to_graph(...)` should consume the event ledger as the canonical chronology source rather than relying on free-form re-derivation.
- follow-up questions should target missing anchors, missing relations, and contradictory events by stable IDs.

### 4. Add claim-candidate confidence and ambiguity management

Before intake completes, the system should be able to say:

- which claims are leading candidates
- why each one is plausible
- which element gaps remain blocking
- whether the mediator should ask a disambiguation question before evidence organization begins

Implementation focus:

- extend intake matching summaries in [mediator/mediator.py](/home/barberb/complaint-generator/mediator/mediator.py)
- preserve additive summaries through [intake_status.py](/home/barberb/complaint-generator/intake_status.py)
- make `claim_disambiguation_resolved` part of readiness logic in [complaint_phases/phase_manager.py](/home/barberb/complaint-generator/complaint_phases/phase_manager.py)

### 5. Turn contradictions into a managed workflow

Contradictions should become operational objects, not just blockers.

For each contradiction, persist:

- competing fact versions
- contradiction topic
- affected claim types and elements
- severity
- recommended resolution lane
- whether external corroboration is required
- current resolution status

Recommended severity levels:

- `blocking`
- `important`
- `monitor`

Recommended resolution lanes:

- `clarify_with_complainant`
- `capture_testimony`
- `request_document`
- `seek_external_record`
- `manual_review`

### 6. Make testimony a default proof lane, not only a fallback of last resort

The testimony ledger in [mediator/claim_support_hooks.py](/home/barberb/complaint-generator/mediator/claim_support_hooks.py) is already strong enough to support earlier use.

Phase 1 should automatically switch into structured testimony capture when:

- documents are unavailable
- the complainant only has memory-based support
- a contradiction requires witness-level resolution
- proof would materially improve from first-hand narrative decomposition

This path should collect:

- actor
- act
- target
- harm
- event date
- firsthand or secondhand status
- likely corroborators
- likely record locations

### 7. Tighten intake completion criteria

Current readiness in [complaint_phases/phase_manager.py](/home/barberb/complaint-generator/complaint_phases/phase_manager.py) should be extended with semantic gates.

Recommended additional gates:

- `case_theory_coherent`
- `claim_disambiguation_resolved`
- `minimum_proof_path_present`
- `blocking_contradictions_resolved_or_escalated`
- `complainant_summary_confirmed`

Intake should end when the system has enough structured, explainable, element-aware state to drive evidence tasks with low ambiguity.

## Phase 2 Plan: Evidence Organization and Marshalling

### 1. Promote alignment tasks into a first-class evidence task board

The next-action path in [complaint_phases/phase_manager.py](/home/barberb/complaint-generator/complaint_phases/phase_manager.py) already prioritizes `alignment_evidence_tasks`. That object should become the canonical Phase 2 queue.

Each task should include:

- `task_id`
- `claim_type`
- `claim_element_id`
- `claim_element_label`
- `support_status`
- `missing_fact_bundle`
- `preferred_support_kind`
- `preferred_evidence_classes`
- `fallback_support_kinds`
- `intake_origin_refs`
- `recommended_queries`
- `recommended_witness_prompts`
- `success_criteria`
- `source_quality_target`
- `resolution_status`
- `resolution_notes`

### 1A. Derive temporal evidence tasks from event gaps, not only packet status

The current Phase 2 task builder in [mediator/mediator.py](../mediator/mediator.py) correctly marks chronology-specific work when packet elements carry temporal-rule metadata. The next step is to ground those tasks in the same event ledger created during intake.

Each temporal evidence task should additionally carry:

- `event_ids`
- `relation_ids`
- `timeline_issue_ids`
- `anchor_ids`
- `temporal_proof_objective`
- `missing_temporal_predicates`
- `required_provenance_kinds`

That change lets Phase 2 ask for the exact missing chronology proof, for example "anchor the complaint date", "prove protected activity occurred before termination", or "resolve contradictory notice dates", instead of only reporting that a packet element is temporally weak.

### 2. Move from element labels to minimum fact bundles

The most important Phase 2 improvement is to stop treating an element label as the entire proof requirement.

For each core element, the system should define the minimum fact bundle that would make the element draftable.

Examples:

- protected activity: what was reported, to whom, when, and by what channel
- adverse action: what changed, when, by whom, and what harm followed
- causation: sequence, linkage facts, comparator context, or direct statements

The claim-support validation path in [mediator/claim_support_hooks.py](/home/barberb/complaint-generator/mediator/claim_support_hooks.py) should emit both `missing_fact_bundle` and `satisfied_fact_bundle` so evidence tasks and drafting can reason at the same level.

### 3. Strengthen evidence metadata and provenance requirements

Evidence storage already has strong metadata support. The improvement is to make proof usefulness part of the default contract.

Normalize these fields for each artifact or support source:

- source identity
- collection method
- acquisition date
- created date versus event date
- parse quality
- authenticity indicators
- privilege or privacy sensitivity
- linked facts
- linked elements
- contradiction-resolution role

Phase 2 completion should use those fields as readiness signals, not only as passive metadata.

### 4. Unify support lanes under one model

Phase 2 should treat these as equal support lanes:

- documentary evidence
- testimony
- authority
- web capture
- archived web capture
- external institutional record

For each claim element, the system should know:

- which lanes are required
- which lanes are currently covered
- which lane is the cheapest next improvement
- whether current support is draft-ready or merely suggestive

### 5. Make support packets the canonical evidence assembly object

Each claim element packet should contain:

- element summary
- supporting facts
- supporting artifacts
- supporting testimony
- supporting authorities
- support traces and provenance notes
- contradictions
- unresolved gaps
- recommended next evidence
- draft-ready factual narrative

These packets should become the shared object for review, optimization, and drafting, not just a dashboard convenience.

### 6. Drive follow-up execution from task success criteria

The evidence follow-up loop should not stop at query generation. It should execute against task-level success criteria.

For each unresolved task:

- attempt the preferred lane
- broaden to fallback lanes if no new support is found
- stop when retrieval adds no distinct fact coverage
- escalate with a named status if the system is capped out

Recommended escalation states:

- `awaiting_complainant_record`
- `awaiting_third_party_record`
- `awaiting_testimony`
- `needs_manual_legal_review`
- `insufficient_support_after_search`

### 7. Add evidence-phase completion criteria based on support quality

Evidence completion should require more than artifact presence.

Recommended metrics:

- `supported_blocking_element_ratio`
- `credible_support_ratio`
- `high_quality_parse_ratio`
- `resolved_contradiction_ratio`
- `draft_ready_element_ratio`

Evidence should only be considered complete when blocking elements have credible support or an explicit, reviewable escalation path.

## Shared Data Contracts

The following state additions should be preserved through [intake_status.py](/home/barberb/complaint-generator/intake_status.py), optimization traces, and review payloads.

### Intake-side additions

- `candidate_claims[].confidence`
- `candidate_claims[].reasons`
- `candidate_claims[].ambiguity_flags`
- `canonical_facts[].element_tags`
- `canonical_facts[].materiality`
- `proof_leads[].owner`
- `proof_leads[].availability`
- `proof_leads[].element_targets`
- `open_items[].blocking_level`
- `open_items[].next_question_strategy`
- `contradiction_queue[].resolution_lane`

### Evidence-side additions

- `alignment_evidence_tasks[].task_id`
- `alignment_evidence_tasks[].missing_fact_bundle`
- `alignment_evidence_tasks[].fallback_support_kinds`
- `alignment_evidence_tasks[].source_quality_target`
- `claim_support_packets[].elements[].missing_fact_bundle`
- `claim_support_packets[].elements[].satisfied_fact_bundle`
- `claim_support_packets[].elements[].support_quality`
- `claim_support_packet_summary.proof_readiness_score`

## Review and Operator Surfaces

The operator should be able to answer these questions from the existing review and document surfaces:

- What is the current case theory?
- Which claim elements are still weak or contradicted?
- What proof leads exist and who controls them?
- What evidence tasks are currently blocking drafting?
- Which unresolved issues are complainant follow-up issues versus system-search issues?
- Why is the complaint ready or not ready to formalize?

The important architectural rule is to extend normalized status builders and ledger outputs instead of recreating logic inside application modules. That matches the existing review-boundary guidance for this repository.

## Delivery Roadmap

### Milestone 0: Chronology-first intake and evidence handoff

- add a canonical event ledger and stable timeline IDs to the intake case file
- update intake answer application so chronology answers create or update events, anchors, and relations directly
- make evidence alignment summaries carry event, relation, and issue refs into `alignment_evidence_tasks`
- extend readiness and packet summaries so unresolved temporal issues are visible as first-class blockers
- preserve the new fields through [intake_status.py](../intake_status.py), review payloads, persisted document refreshes, and optimization traces

### Milestone 1: Intake structure and question policy

- deepen intake case file schema
- add expected update contracts for questions
- improve answer normalization into canonical facts
- add contradiction workflow metadata
- add stronger intake readiness gates

### Milestone 2: Intake-to-evidence handoff

- enrich `alignment_evidence_tasks`
- attach proof leads to element-level tasks
- add minimum fact bundle outputs to support validation
- preserve new fields through status summaries and trace payloads

### Milestone 3: Evidence sufficiency and lane unification

- unify documents, testimony, authority, and web captures in one support model
- add support quality scoring and proof-readiness scoring
- make support packets the canonical assembly object

### Milestone 4: Review and automation

- drive follow-up execution from task success criteria
- add escalation states and operator visibility
- expose claim-element proof readiness consistently in review, document, and trace surfaces

## Suggested Test Expansion

Add or extend coverage for:

- structured intake fact extraction from answers
- contradiction resolution updating readiness and downstream tasks
- testimony-first progression when documents are unavailable
- proof-lead promotion into evidence tasks
- minimum fact bundle output in support validation
- support-quality gating of evidence completion
- duplicate-question suppression through novelty scoring
- stable preservation of new fields through `intake_status` and optimization traces

Relevant current suites include:

- [tests/test_mediator_three_phase.py](/home/barberb/complaint-generator/tests/test_mediator_three_phase.py)
- [tests/test_intake_status.py](/home/barberb/complaint-generator/tests/test_intake_status.py)
- [tests/test_mediator.py](/home/barberb/complaint-generator/tests/test_mediator.py)
- [tests/test_claim_support_hooks.py](/home/barberb/complaint-generator/tests/test_claim_support_hooks.py)
- [tests/test_document_pipeline.py](/home/barberb/complaint-generator/tests/test_document_pipeline.py)

## Recommended First Implementation Slice

The highest-leverage first slice is:

1. add a canonical `event_ledger`, `timeline_relations`, and `timeline_issues` contract to [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py)
2. make `_apply_intake_answer_to_case_file(...)` in [mediator/mediator.py](../mediator/mediator.py) populate both canonical facts and stable event records, then re-sync the dependency graph from that shared chronology state
3. enrich `_summarize_intake_evidence_alignment(...)` and `_build_alignment_evidence_tasks(...)` in [mediator/mediator.py](../mediator/mediator.py) so temporal tasks carry event IDs, relation IDs, issue IDs, and explicit temporal proof objectives
4. emit minimum fact bundles plus event-linked temporal predicates from [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
5. extend readiness and evidence packet gates in [complaint_phases/phase_manager.py](../complaint_phases/phase_manager.py) so unresolved temporal issues and unsupported ordering become first-class blockers
6. preserve the new chronology ledger fields through [intake_status.py](../intake_status.py), [applications/review_api.py](../applications/review_api.py), and the existing review or document trace payloads

That slice improves both phases without forcing a full workflow redesign up front, and it creates the exact timeline substrate needed by the temporal proof roadmap.
