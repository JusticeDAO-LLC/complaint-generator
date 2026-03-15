# Intake and Evidence Improvement Plan

## Scope

This plan covers:

1. Phase 1: the initial intake loop where the mediator questions the complainant.
2. Phase 2: the evidence organization loop where facts are marshaled into support for the identified complaint type and claim elements.

The goal is to improve factual completeness, reduce ambiguity, and create a cleaner handoff from intake to claim-support review so the system can reliably marshal facts into a supportable complaint.

## Current Baseline

The repository already has strong building blocks:

- Phase 1 produces a structured intake case file with `candidate_claims`, `canonical_facts`, `proof_leads`, `contradiction_queue`, and `intake_sections` in [complaint_phases/intake_case_file.py](complaint_phases/intake_case_file.py).
- Intake questions already carry metadata such as `question_objective`, `proof_priority`, `phase1_section`, `target_claim_type`, and `target_element_id` in [complaint_phases/denoiser.py](complaint_phases/denoiser.py).
- Intake completion is already gated by readiness criteria and blockers in [complaint_phases/phase_manager.py](complaint_phases/phase_manager.py).
- The mediator already turns claim-support validation and gap analysis into normalized evidence packets in [mediator/mediator.py](mediator/mediator.py).
- Evidence and testimony already have provenance-oriented persistence paths in [mediator/evidence_hooks.py](mediator/evidence_hooks.py) and [mediator/claim_support_hooks.py](mediator/claim_support_hooks.py).
- Intake-to-evidence alignment already exists through `intake_evidence_alignment_summary` and `alignment_evidence_tasks` in [mediator/mediator.py](mediator/mediator.py).

Those are the right primitives. The main issue is that the workflow still needs tighter normalization, stronger intake-to-element linkage, and a more operational evidence assembly loop.

## Key Gaps

### Phase 1 gaps

- Intake answer application is still coarse. Answers are mostly appended as broad fact types like `timeline`, `claim_element`, `responsible_party`, or `supporting_evidence`, but are not consistently decomposed into actor, act, target, date range, location, harm, and remedy fields.
- `proof_leads` capture that evidence may exist, but they do not yet reliably capture availability, custodian, expected format, retrieval path, authenticity risk, or linkage strength to specific claim elements.
- `open_items` and `summary_snapshots` are initialized in the intake case file but are not yet acting as a first-class workflow queue.
- Claim disambiguation is present but still too dependent on early graph extraction; there is room for a more explicit “claim candidate confidence and why” layer before the evidence phase starts.
- Contradiction handling exists, but it should drive a stronger resolution workflow and not only a readiness blocker.

### Phase 2 gaps

- Evidence organization is strong at the review layer, but weaker at the operator workflow layer that turns intake proof leads into concrete acquisition tasks.
- The handoff from intake facts to claim-support packets is element-aware, but not yet fully fact-bundle aware. The system knows an element is weak, but not always which minimum fact bundle is missing.
- Testimony is already persisted as first-class support, but it is not yet clearly integrated as a default intake continuation path when documents are unavailable.
- Evidence completeness focuses on support status counts and contradiction counts; it should also include source quality, provenance sufficiency, and document readability thresholds.
- Follow-up planning exists, but it should be more tightly connected to intake-originated missing facts and proof leads.

## Target State

By the end of this work, the system should behave as follows:

- Phase 1 ends with a structured case theory, not just a denoised narrative.
- Every material fact has a normalized shape, provenance, confidence, and a direct relation to one or more candidate claims and claim elements.
- Every unresolved claim element has an explicit missing-fact explanation and at least one recommended support path: document, testimony, witness, external record, or authority.
- Phase 2 operates from an evidence task board generated from the intake case file and claim-support packets.
- Evidence acquired in Phase 2 is automatically attached back to the supporting facts, claim elements, and contradiction queues it resolves.
- The mediator can explain, for any claim element, what facts support it, what source artifacts support those facts, what remains missing, and what next evidence would materially improve the complaint.

## Improvement Plan

## Phase 1: Intake and Complainant Questioning

### 1. Upgrade the intake case file into the canonical case-theory object

Expand the intake case file so it is the authoritative Phase 1 record instead of a partial summary.

Add or strengthen these structures:

- `fact_participants`: actor, target, witness, custodian, organization roles.
- `timeline_anchors`: exact date, approximate date, date range, order-only marker.
- `harm_profile`: economic harm, professional harm, emotional harm, physical harm, procedural harm.
- `remedy_profile`: money damages, reinstatement, injunction, records correction, declaratory relief.
- `proof_leads`: add `owner`, `availability`, `expected_format`, `retrieval_path`, `authenticity_risk`, `privacy_risk`, `element_targets`, `fact_targets`, and `priority`.
- `open_items`: explicit unresolved issues with `reason`, `blocking_level`, `next_question_strategy`, and `target_element_id`.
- `summary_snapshots`: structured summaries after each major intake iteration so downstream review can compare deltas instead of rereading the entire case state.

Implementation points:

- Extend builders in [complaint_phases/intake_case_file.py](complaint_phases/intake_case_file.py).
- Treat `open_items` as the canonical unresolved-work queue in [complaint_phases/phase_manager.py](complaint_phases/phase_manager.py).

### 2. Make questions explicitly fact-extractive, not just clarifying

The current denoiser already carries strong metadata. The next step is to make the answer contract equally structured.

For each Phase 1 question, define an expected update shape:

- chronology question -> timeline anchor plus event description plus relation to claim.
- actor question -> actor role plus organization plus conduct linkage.
- requirement question -> element-targeted factual predicate.
- evidence question -> proof lead plus availability and source path.
- contradiction question -> resolution, confidence, and superseded fact references.

Implementation points:

- Extend the answer application logic in [mediator/mediator.py](mediator/mediator.py) so `_apply_intake_answer_to_case_file(...)` can produce structured subrecords instead of only generic fact rows.
- Use `question_goal`, `target_element_id`, `phase1_section`, and `expected_update_kind` from [complaint_phases/denoiser.py](complaint_phases/denoiser.py) as the routing contract.

### 3. Introduce a minimal fact schema for intake answers

Each accepted fact should support these fields where available:

- `fact_id`
- `text`
- `fact_type`
- `claim_types`
- `element_tags`
- `actor_ids`
- `target_ids`
- `event_date_or_range`
- `location`
- `source_kind`
- `source_ref`
- `confidence`
- `needs_corroboration`
- `corroboration_priority`
- `contradiction_group_id`
- `materiality`

This keeps intake facts useful for both questioning and later marshaling.

### 4. Add a claim-candidate confidence and ambiguity layer

Before Phase 1 is considered complete, the system should be able to say:

- what the top candidate claims are,
- why each claim is plausible,
- which required elements are still weak,
- whether the system should ask a disambiguation question before proceeding.

Recommended additions:

- `candidate_claim_score`
- `candidate_claim_reasons`
- `disambiguation_needed`
- `disambiguation_questions`

This should be built from existing matching pressure plus the intake registry-backed elements.

Implementation points:

- Extend `_build_intake_matching_pressure_map(...)` and related summaries in [mediator/mediator.py](mediator/mediator.py).
- Surface a disambiguation blocker in readiness scoring in [complaint_phases/phase_manager.py](complaint_phases/phase_manager.py).

### 5. Make contradictions a managed workflow, not just a blocker

The current contradiction queue should become operational.

For every contradiction:

- label the topic,
- store both competing fact versions,
- record affected claim elements,
- mark whether external corroboration is required,
- suggest the best resolution path: testimony, document, witness, or chronology clarification.

Add contradiction severity levels:

- `blocking`: cannot advance without resolution.
- `important`: can advance with warning, but evidence tasks must be created.
- `monitor`: keep in review packet only.

### 6. Capture testimony early as a fallback evidence lane

The repo already has strong testimony persistence in [mediator/claim_support_hooks.py](mediator/claim_support_hooks.py). The first phase should use it earlier.

When the complainant lacks documents, the mediator should pivot automatically to a structured testimony capture flow:

- who observed the event,
- what happened,
- when it happened,
- who else knows,
- what record may exist elsewhere,
- whether the speaker has first-hand or second-hand knowledge.

This prevents Phase 2 from stalling on “no documents yet” and produces usable fact support immediately.

### 7. Tighten Phase 1 completion criteria

Keep the existing readiness checks, but add stronger semantic gates:

- at least one high-confidence candidate claim,
- all blocking claim elements either captured or explicitly queued as evidence tasks,
- at least one proof path for each core claim element,
- all blocking contradictions resolved or escalated,
- a complainant-approved case summary snapshot.

Recommended additions to readiness:

- `case_theory_coherent`
- `claim_disambiguation_resolved`
- `minimum_proof_path_present`
- `complainant_summary_confirmed`

## Phase 2: Organizing Evidence to Support the Complaint

### 1. Create a first-class evidence task board

Phase 2 should start from tasks, not only from gaps.

Each task should represent a specific support objective:

- target claim type,
- target claim element,
- target missing fact bundle,
- preferred evidence class,
- acceptable fallback classes,
- urgency,
- source quality target,
- contradiction-resolving versus support-building purpose.

The existing `alignment_evidence_tasks` are the correct starting point, but they should be expanded into a richer operational object.

Add fields such as:

- `task_id`
- `missing_fact_bundle`
- `preferred_support_kind`
- `preferred_evidence_classes`
- `fallback_support_kinds`
- `intake_origin_refs`
- `recommended_queries`
- `success_criteria`
- `resolution_status`

Implementation points:

- Extend `_build_alignment_evidence_tasks(...)` in [mediator/mediator.py](mediator/mediator.py).
- Feed those tasks directly into evidence questioning in [complaint_phases/denoiser.py](complaint_phases/denoiser.py).

### 2. Move from element coverage to minimum fact bundles

For each claim element, define the minimum facts needed to credibly support it.

Examples:

- protected activity -> what was reported, to whom, when, and how it was documented.
- adverse action -> what action occurred, when, by whom, and what changed.
- causation -> temporal sequence, statements, comparator events, or retaliatory pattern.

Then evaluate evidence against the bundle rather than the element label alone.

This will improve:

- gap explanations,
- evidence recommendations,
- follow-up query generation,
- final complaint drafting quality.

Implementation points:

- Extend claim-support validation output in [mediator/claim_support_hooks.py](mediator/claim_support_hooks.py) to include `missing_fact_bundle` and `satisfied_fact_bundle` per element.
- Mirror that in `claim_support_packets` and evidence-phase status in [mediator/mediator.py](mediator/mediator.py).

### 3. Strengthen evidence intake metadata and provenance

Evidence should be organized not only by file or CID, but by litigation usefulness.

For each evidence item, add or normalize:

- source identity,
- collection method,
- date acquired,
- created date versus event date,
- authenticity indicators,
- parse quality,
- privilege/privacy sensitivity,
- linked claim elements,
- linked canonical facts,
- contradiction-resolving role.

The evidence hooks already contain strong provenance support. The improvement is to require those fields earlier and expose them more consistently in evidence review.

Implementation points:

- Build intake-side defaults that flow into [mediator/evidence_hooks.py](mediator/evidence_hooks.py).
- Use parse-quality and lineage fields as evidence readiness signals, not only as review metadata.

### 4. Unify documents, testimony, authorities, and web captures under one support model

Phase 2 should treat these as support lanes under a single framework:

- documentary evidence,
- structured testimony,
- legal authority,
- discovered web records,
- archived captures,
- external institutional records.

For each element, the system should know:

- which lanes are required,
- which lanes are already covered,
- which lane is the cheapest next improvement,
- whether the current support is legally sufficient or only directionally helpful.

This is already partially modeled by the claim-support summary and validation payloads. The improvement is to make it the default organizing principle of the evidence phase.

### 5. Build evidence packets that map back to facts and forward to drafting

For every claim element, produce a packet containing:

- element summary,
- supporting facts,
- supporting artifacts,
- supporting testimony,
- supporting authorities,
- parse/provenance quality notes,
- contradictions,
- unresolved gaps,
- recommended next evidence,
- draft-ready factual narrative.

This packet should be the shared object used by:

- review UI,
- follow-up planning,
- evidence-phase completion,
- formal complaint drafting.

The existing `support_packets` and `claim_support_packets` provide the foundation. The next step is to make them the canonical evidence assembly output.

### 6. Improve the automatic follow-up loop

The repo already supports follow-up plan generation and execution. Improve the loop so it is driven by evidence task success criteria.

For each unresolved task:

- try the preferred support lane,
- fall back to secondary lanes,
- record why a task remains unresolved,
- stop retrying when retrieval adds no new facts,
- escalate to manual complainant questioning when the system is capped out.

Recommended escalation states:

- `awaiting_complainant_record`
- `awaiting_third_party_record`
- `awaiting_testimony`
- `needs_manual_legal_review`
- `insufficient_support_after_search`

### 7. Add evidence-phase completion criteria based on support quality

Keep the current packet/status checks, but add quality thresholds:

- each blocking element has at least one credible support path,
- contradictions are either resolved or quarantined with drafting warnings,
- critical evidence has acceptable provenance and parse quality,
- missing elements have explicit next actions,
- the final packet set is sufficient for drafting without hallucinated bridging.

Recommended evidence metrics:

- `supported_blocking_element_ratio`
- `credible_support_ratio`
- `high_quality_parse_ratio`
- `resolved_contradiction_ratio`
- `draft_ready_element_ratio`

## Cross-Phase Workstreams

### 1. Shared identifiers and traceability

Use stable ids across intake facts, proof leads, evidence items, testimony, and claim-support packets.

Required trace chains:

- complainant answer -> canonical fact
- canonical fact -> claim element
- claim element -> evidence task
- evidence task -> artifact/testimony/authority
- artifact/testimony/authority -> support trace
- support trace -> drafted allegation

### 2. Status language normalization

Normalize the vocabulary used across readiness, validation, and evidence tasks.

Preferred status families:

- intake item: `missing`, `partial`, `complete`, `contradicted`
- evidence task: `queued`, `in_progress`, `resolved`, `blocked`, `escalated`
- claim element: `supported`, `partially_supported`, `unsupported`, `contradicted`
- drafting readiness: `not_ready`, `conditionally_ready`, `ready`

### 3. Review surfaces and operator visibility

The operator should be able to inspect:

- current case theory,
- unresolved intake blockers,
- contradiction queue,
- proof leads by priority,
- evidence tasks by claim element,
- support packet quality and trace summaries,
- why a complaint is or is not ready to draft.

Use [intake_status.py](intake_status.py) as the starting summary layer and extend it rather than introducing a separate status pathway.

## Delivery Roadmap

### Milestone 1: Harden Phase 1 data capture

- Expand intake case file schema.
- Upgrade `_apply_intake_answer_to_case_file(...)` to structured extraction.
- Turn `open_items` into the active unresolved-work queue.
- Add claim ambiguity and summary-confirmation readiness gates.

### Milestone 2: Improve intake-to-evidence handoff

- Expand `alignment_evidence_tasks` into richer evidence tasks.
- Add minimum fact bundle tracking per claim element.
- Attach proof leads to element-targeted acquisition tasks.

### Milestone 3: Strengthen evidence organization and sufficiency

- Unify evidence, testimony, authority, and web capture lanes in the task model.
- Add provenance and parse-quality thresholds to evidence completion.
- Make support packets the canonical evidence assembly object.

### Milestone 4: Improve automation and review

- Drive follow-up execution from evidence task success criteria.
- Add escalation states for unresolved tasks.
- Extend intake and claim-support review surfaces with packet quality, contradiction resolution, and draft-readiness signals.

## Suggested Tests

Add or expand tests for these scenarios:

- intake answer creates a structured fact with actor, target, date, and element tags.
- contradiction answer resolves the queue and updates downstream readiness.
- missing documents route into testimony capture without losing claim-element linkage.
- proof leads become evidence tasks with stable references.
- evidence task resolution updates claim-support packet status and recommended next step.
- low-quality parse evidence does not count as draft-ready support when better evidence is required.
- follow-up execution stops retrying once it is no longer adding distinct facts.

Relevant current coverage already exists in:

- [tests/test_mediator_three_phase.py](tests/test_mediator_three_phase.py)
- [tests/test_claim_support_hooks.py](tests/test_claim_support_hooks.py)
- [tests/test_web_evidence_hooks.py](tests/test_web_evidence_hooks.py)
- [tests/test_intake_status.py](tests/test_intake_status.py)

## Recommended First Implementation Slice

If this should be delivered incrementally, start with the highest-leverage slice:

1. Expand `proof_leads` and `open_items` in the intake case file.
2. Make Phase 1 answers populate structured fact fields and explicit element linkage.
3. Extend `alignment_evidence_tasks` with success criteria and intake-origin references.
4. Add minimum fact bundle output to claim-support validation.
5. Update evidence completion to require both coverage and support-quality thresholds.

That sequence improves both phases without forcing a full redesign of the mediator.# Intake And Evidence Improvement Plan

## Purpose

This plan covers the first two mediator phases:

1. Phase 1: intake and denoising, where the mediator asks the complainant questions and turns narrative text into structured, claim-relevant facts.
2. Phase 2: evidence organization, where the system maps facts to supporting proof, identifies gaps, and prepares a support package strong enough to formalize into a complaint.

The objective is to make the mediator better at marshalling facts for the actual complaint type in play, reduce vague or repetitive questioning, and produce a stronger fact and evidence record before formalization.

## Current-State Diagnosis

The current architecture already has the right major building blocks:

- `complaint_phases/phase_manager.py` defines the three-phase workflow and completion checks.
- `complaint_phases/denoiser.py` generates gap-filling questions from knowledge and dependency graphs.
- `complaint_phases/knowledge_graph.py` and `complaint_phases/dependency_graph.py` provide the fact and requirement structures.
- `docs/EVIDENCE_MANAGEMENT.md` and existing evidence hooks provide storage, metadata, and CID-backed persistence.
- `complaint_analysis/*` provides complaint typing, decision trees, keywords, and legal pattern extraction.

The main weaknesses are not missing modules but insufficient precision in how they are used during early intake:

- Intake completion is still fairly coarse. The current logic mainly checks for graph existence, low remaining gap count, and denoising convergence.
- Evidence completion is also coarse. It mainly checks that some evidence exists, the graph is enhanced, and evidence gap ratio is below a threshold.
- The denoiser is already useful for entity and gap extraction, but it is not yet consistently optimized around complaint-element coverage, chronology, causation, injury, and proof burden.
- Phase 2 evidence handling is good at storage and retrieval, but less mature at constructing a claim-element-to-evidence matrix that a complaint drafter can rely on.
- Intake and evidence are not yet treated as a single proof-building pipeline. Facts are collected first, evidence later, but the system should be thinking about proof burden from the beginning of intake.

## Design Principles

1. Intake should be claim-element-driven, not just conversation-driven.
2. The mediator should always know why it is asking the next question.
3. Facts should be represented in a form that can be tied directly to evidence and legal elements.
4. Evidence organization should be structured around proving or disproving required elements, not around raw artifact storage alone.
5. The system should explicitly track uncertainty, contradiction, and missing support.
6. Every improvement should be measurable through adversarial sessions, graph metrics, and complaint-quality outcomes.

## Target End State

By the end of the first implementation phase for these improvements, the system should:

- ask fewer but more targeted intake questions;
- capture a reliable chronology of events;
- distinguish actors, actions, harms, protected characteristics, policies, communications, and requested relief;
- maintain a live map of claim elements to known supporting facts;
- convert missing legal elements into evidence requests;
- organize submitted and discovered evidence into a proof matrix;
- expose readiness metrics showing whether the complaint has enough factual and evidentiary support to move to formalization.

## Phase 1 Improvement Plan: Intake And Questioning

### Workstream 1: Intake Objectives And Fact Schema

#### Goal

Define a clear schema for what Phase 1 must extract before it can be considered complete.

#### Improvements

- Introduce a complaint-intake schema that is common across complaint types and then extended per type.
- Require explicit capture of:
  - parties and roles;
  - chronology;
  - locations and forum;
  - challenged acts or omissions;
  - motive or protected basis where relevant;
  - adverse action or injury;
  - notice, reporting, and response steps;
  - witnesses, documents, and other potential evidence;
  - requested relief and immediate risks.
- Add complaint-type-specific minimum required fields derived from `complaint_analysis/decision_trees.py` and claim element models.

#### Primary File Targets

- `complaint_phases/knowledge_graph.py`
- `complaint_phases/dependency_graph.py`
- `complaint_analysis/decision_trees.py`
- `complaint_analysis/complaint_types.py`

#### Acceptance Criteria

- Every intake session produces a structured fact record aligned to the complaint type.
- Required fields differ appropriately by complaint type instead of using the same generic intake bar for all claims.

### Workstream 2: Goal-Directed Question Planner

#### Goal

Replace generic gap filling with a planner that asks questions in the order that most improves complaint readiness.

#### Improvements

- Rank candidate questions by expected proof gain, not only by local graph gaps.
- Add question goals such as:
  - establish timeline;
  - identify respondent and decision-maker;
  - identify protected basis or legal trigger;
  - prove adverse action or injury;
  - establish causation;
  - identify notice and opportunity to cure;
  - identify corroborating evidence.
- Avoid asking multiple questions with the same proof objective if the last answer already supplied the relevant information.
- Add redundancy checks so the mediator does not keep re-asking for dates, documents, or witnesses already supplied.
- Track question quality features directly in Phase 1:
  - specificity;
  - novelty;
  - expected evidentiary value;
  - burden on the complainant.

#### Primary File Targets

- `complaint_phases/denoiser.py`
- `complaint_phases/phase_manager.py`
- `mediator/readme.md` for behavior contract updates

#### Acceptance Criteria

- Intake question sequences show less repetition in adversarial runs.
- Median questions per session drops or stays flat while dependency satisfaction improves.
- Critic feedback shows gains in specificity and coverage.

### Workstream 3: Chronology And Event Modeling

#### Goal

Make the timeline a first-class object instead of something inferred indirectly from free text.

#### Improvements

- Create explicit event nodes for reported incidents.
- Capture event attributes:
  - date or date range;
  - actor;
  - target;
  - action;
  - location;
  - communication channel;
  - immediate consequence.
- Detect missing chronology segments, such as:
  - unknown date of report;
  - unknown date of adverse action;
  - unclear order between complaint, response, and harm.
- Add a chronology-specific question mode that resolves sequencing before moving deeper into evidence.

#### Primary File Targets

- `complaint_phases/knowledge_graph.py`
- `complaint_phases/denoiser.py`
- `complaint_phases/dependency_graph.py`

#### Acceptance Criteria

- Sessions produce an ordered event list for major incidents.
- Retaliation, discrimination, housing, and consumer claims all show cleaner causal sequences in the graph.

### Workstream 4: Contradiction, Ambiguity, And Confidence Tracking

#### Goal

Make uncertainty explicit and actionable.

#### Improvements

- Track unresolved ambiguities, not just missing fields.
- Add contradiction markers for situations like:
  - conflicting dates;
  - unclear responsible actor;
  - injury described differently across turns;
  - witness named but not tied to an event.
- Add intake confidence by fact and by claim element.
- Generate clarification questions only when they materially improve legal or evidentiary readiness.

#### Primary File Targets

- `complaint_phases/knowledge_graph.py`
- `complaint_phases/denoiser.py`
- `complaint_phases/phase_manager.py`

#### Acceptance Criteria

- The mediator can distinguish unknown facts from disputed or internally inconsistent facts.
- Intake summaries explicitly list high-risk ambiguities before advancing to Phase 2.

### Workstream 5: Better Intake Completion Gates

#### Goal

Advance from Phase 1 only when the complaint is factually coherent enough to support evidence collection.

#### Improvements

- Replace simple gap-count thresholds with readiness gates such as:
  - chronology completeness;
  - actor completeness;
  - claim-element baseline coverage;
  - contradiction count below threshold;
  - evidence-lead density above threshold;
  - complainant burden cap reached without meaningful marginal gain.
- Add an explicit `intake_readiness_score` and named blocking reasons.

#### Primary File Targets

- `complaint_phases/phase_manager.py`
- `complaint_phases/dependency_graph.py`

#### Acceptance Criteria

- Phase transitions expose why intake is or is not complete.
- Degraded sessions show named blockers instead of only a raw gap count.

## Phase 2 Improvement Plan: Evidence Organization

### Workstream 6: Claim-Element-To-Evidence Matrix

#### Goal

Organize evidence around the elements that must be proved.

#### Improvements

- Build a support matrix with rows such as:
  - legal element or required fact;
  - supporting facts collected during intake;
  - available evidence artifacts;
  - witness support;
  - authority relevance;
  - remaining proof gap.
- Store support strength per element, not just per claim overall.
- Distinguish direct evidence, circumstantial evidence, witness testimony, documentary proof, and missing proof.

#### Primary File Targets

- `complaint_phases/dependency_graph.py`
- `docs/EVIDENCE_MANAGEMENT.md`
- mediator evidence hooks and support-review payload builders

#### Acceptance Criteria

- Every major claim element has a visible support status.
- Formalization can consume the matrix directly when drafting factual allegations.

### Workstream 7: Evidence Request Planner

#### Goal

Turn Phase 2 into a guided proof-gathering workflow rather than a passive storage step.

#### Improvements

- For each unsatisfied or weakly supported requirement, generate concrete evidence asks such as:
  - upload termination letter;
  - identify HR complaint email;
  - identify witness to meeting on a specific date;
  - provide lease clause, policy, screenshot, or receipt.
- Prioritize evidence requests by expected legal value.
- Group requests into complainant-friendly buckets:
  - documents;
  - communications;
  - witnesses;
  - physical evidence;
  - timeline corroboration;
  - damages proof.

#### Primary File Targets

- `complaint_phases/phase_manager.py`
- mediator follow-up planning and evidence hooks
- `docs/WEB_EVIDENCE_DISCOVERY.md`

#### Acceptance Criteria

- Phase 2 output lists concrete next evidence tasks instead of only abstract gap metrics.
- Users can see why each requested artifact matters.

### Workstream 8: Evidence Normalization And Provenance

#### Goal

Ensure uploaded and discovered evidence is usable as structured proof.

#### Improvements

- Normalize evidence into a common representation:
  - artifact metadata;
  - extracted text or summary;
  - linked people, events, organizations, dates;
  - source provenance;
  - chain of custody or retrieval path where available.
- Distinguish:
  - user-supplied evidence;
  - web-discovered evidence;
  - legal authority;
  - mediator-generated summaries.
- Persist confidence and provenance for extracted facts so downstream formalization knows what is primary evidence versus inference.

#### Primary File Targets

- evidence hooks and payload builders
- `docs/EVIDENCE_MANAGEMENT.md`
- `docs/PAYLOAD_CONTRACTS.md`

#### Acceptance Criteria

- Evidence artifacts are linked to the specific facts they support.
- Provenance survives through storage, review, and complaint drafting.

### Workstream 9: Evidence Sufficiency And Adverse-Fact Handling

#### Goal

Measure whether the evidence package is strong enough and highlight risks honestly.

#### Improvements

- Add per-element sufficiency labels:
  - unsupported;
  - weak;
  - moderate;
  - strong.
- Track adverse or risky evidence, not only supportive proof.
- Distinguish elements supported only by complainant testimony from those corroborated by documents or third parties.
- Add a `proof_readiness_score` for Phase 2 and block formalization when core elements remain unsupported unless the user explicitly accepts a weaker pleading strategy.

#### Primary File Targets

- `complaint_phases/dependency_graph.py`
- evidence analysis hooks
- mediator support-review payload generators

#### Acceptance Criteria

- The system can explain why a complaint is not yet evidence-ready.
- Users and developers can see where the case depends entirely on uncorroborated testimony.

### Workstream 10: Evidence-Aware Graph Enhancement

#### Goal

Use Phase 2 to make the graphs materially better, not just larger.

#### Improvements

- Add evidence-backed fact nodes and link them to event, actor, and claim nodes.
- Mark which graph claims are now supported by which artifacts.
- Update dependency satisfaction based on actual linked evidence, not only stated answers.
- Record when evidence resolves a prior ambiguity or contradiction from intake.

#### Primary File Targets

- `complaint_phases/knowledge_graph.py`
- `complaint_phases/dependency_graph.py`
- evidence ingestion and graph projection logic

#### Acceptance Criteria

- Evidence upload or discovery changes support metrics in a traceable way.
- Graph enhancement is measurable beyond raw evidence count.

## Cross-Cutting Improvements

### Workstream 11: Complaint-Type-Specific Playbooks

Use complaint-analysis taxonomies and decision trees to create tailored intake and evidence playbooks for high-value complaint families first:

- employment discrimination and retaliation;
- housing discrimination;
- consumer fraud;
- wrongful termination;
- healthcare and disability-related claims.

Each playbook should define:

- essential intake fields;
- likely defenses or weak points;
- high-value evidence categories;
- chronology milestones;
- required legal elements and common proof substitutes.

### Workstream 12: Better Session Summaries For Humans And Agents

At the end of each phase, generate a compact structured summary containing:

- current claim theory;
- timeline summary;
- key parties and roles;
- strongest supporting facts;
- unresolved factual ambiguities;
- evidence already available;
- evidence still needed;
- blockers to advancing.

This summary should be reusable by:

- the mediator;
- the support-review surfaces;
- adversarial harness evaluations;
- the formal complaint generator.

### Workstream 13: Evaluation And Metrics

Add metrics that specifically evaluate the success of Phase 1 and Phase 2 improvements.

#### Intake Metrics

- average claim-element baseline coverage after intake;
- chronology completeness rate;
- contradiction count per session;
- duplicate-question rate;
- average number of high-value evidence leads identified during intake.

#### Evidence Metrics

- percent of required elements with at least moderate support;
- percentage of support linked to actual artifacts versus testimony-only;
- evidence request completion rate;
- proof-readiness score by complaint type;
- percentage of formal complaints generated with unresolved critical proof gaps.

#### Validation Channels

- adversarial harness batch runs;
- targeted intake and evidence regression tests;
- support-review payload validation;
- manual gold-set review of representative complaint scenarios.

## Recommended Implementation Sequence

### Slice 1: Strengthen Intake Structure

- Add intake schema and readiness metrics.
- Add chronology and actor completeness checks.
- Improve denoiser question ranking with explicit proof objectives.

### Slice 2: Build Evidence Matrix

- Add claim-element support matrix.
- Link facts to artifacts and witnesses.
- Add named proof gaps and sufficiency labels.

### Slice 3: Evidence Request Workflow

- Generate prioritized evidence asks.
- Feed evidence requests into CLI and review surfaces.
- Add provenance-aware summaries.

### Slice 4: Close The Loop With Formalization

- Pass proof matrix and unresolved-gap metadata into complaint drafting.
- Distinguish strong allegations from provisional allegations.
- Improve adversarial optimization objectives around intake precision and proof readiness.

## Concrete Near-Term Backlog

### Phase 1 Near-Term Tasks

1. Add `intake_readiness_score` and blocking reasons to `PhaseManager`.
2. Extend `ComplaintDenoiser` question ranking to prioritize chronology, causation, injury, and proof leads.
3. Add explicit event extraction and event ordering in the knowledge graph.
4. Define complaint-type-specific required intake fields using complaint-analysis decision trees.
5. Add contradiction and ambiguity tracking to phase data.

### Phase 2 Near-Term Tasks

1. Define a dependency-graph support matrix API.
2. Map evidence artifacts to required elements and supporting facts.
3. Add evidence sufficiency labels and a `proof_readiness_score`.
4. Generate concrete evidence requests from unsatisfied requirements.
5. Add provenance-aware evidence summaries to mediator payloads and dashboards.

## Risks And Constraints

- Over-questioning can degrade complainant experience even if graph completeness improves.
- Some complaint types will never have strong documentary support; the system must distinguish weak evidence from legally impossible evidence.
- Aggressive auto-discovery may produce noisy or irrelevant evidence unless provenance and relevance filters are tightened.
- If Phase 1 and Phase 2 metrics are too generic, the system will appear to improve without materially improving complaint quality.

## Recommended Success Criteria For The First Improvement Milestone

The first milestone should be considered successful only if all of the following are true:

- intake sessions show higher claim-element coverage without increasing repetitive questioning;
- chronology completeness improves materially on adversarial retaliation and discrimination runs;
- Phase 2 outputs a usable element-to-evidence matrix;
- unresolved proof gaps are explicit and prioritized;
- the formal complaint generator receives a stronger, more structured factual support package than it does today.

## Summary

The key change is conceptual: Phase 1 should no longer be treated as only denoising, and Phase 2 should no longer be treated as only storage. Together they should form a proof-building pipeline.

If implemented in the sequence above, the mediator will ask better questions, collect stronger facts, organize support more intelligently, and hand Phase 3 a complaint record that is materially closer to a litigable pleading.