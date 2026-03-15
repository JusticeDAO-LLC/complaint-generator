# Intake And Evidence Improvement Plan

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