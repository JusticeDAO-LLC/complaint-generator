# Chronology-First Intake and Evidence Next Batch Plan

Date: 2026-03-22
Status: Active next-step execution plan

This document is the concrete follow-on to the broader planning work in:

- [docs/TEMPORAL_TIMELINE_PROOF_PLAN.md](./TEMPORAL_TIMELINE_PROOF_PLAN.md)
- [docs/INTAKE_EVIDENCE_IMPROVEMENT_PLAN.md](./INTAKE_EVIDENCE_IMPROVEMENT_PLAN.md)

Those plans describe the architecture and target end state. This document narrows the scope to the next implementation batches needed to make chronology a first-class execution contract across intake and evidence support.

## What Was Re-Checked

The current implementation already contains the right raw building blocks.

- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py) authors `timeline_anchors`, `timeline_relations`, `temporal_fact_registry`, `event_ledger`, `temporal_relation_registry`, and `temporal_issue_registry` during intake refresh.
- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py) `build_temporal_issue_registry(...)` already authors issue-level `missing_temporal_predicates`, `required_provenance_kinds`, `recommended_resolution_lane`, and `current_resolution_status`.
- [mediator/mediator.py](../mediator/mediator.py) `build_inquiry_gap_context(...)` already consumes chronology pressure from `claim_support_temporal_handoff`, `claim_reasoning_review`, proof artifact status, and document provenance.
- [mediator/mediator.py](../mediator/mediator.py) `_build_alignment_evidence_tasks(...)` already emits chronology-rich task fields such as `event_ids`, `temporal_fact_ids`, `anchor_ids`, `temporal_relation_ids`, `temporal_issue_ids`, `missing_temporal_predicates`, and `required_provenance_kinds`.
- [mediator/mediator.py](../mediator/mediator.py) `_summarize_claim_support_packets(...)` and `_summarize_alignment_evidence_tasks(...)` already expose aggregate temporal readiness counts, but they still work mostly as summaries rather than a stable chronology execution contract.
- [claim_support_review.py](../claim_support_review.py) `summarize_claim_reasoning_review(...)` already exposes claim-level chronology rollups, but it reads those rollups from validation payloads rather than from a dedicated chronology readiness object.
- [document_pipeline.py](../document_pipeline.py) and [applications/document_api.py](../applications/document_api.py) now carry chronology rollups through drafting readiness, filing checklist payloads, packet export, and checklist text export.

The next work should not invent new chronology metadata. It should make the authored intake chronology state operationally authoritative for intake questioning, evidence task generation, readiness scoring, and proof closure.

## Current Diagnosis

### Intake is authoring chronology, but not yet exposing it as a first-class readiness object

The intake case file already holds the raw chronology state. The main gap is that downstream systems still reconstruct chronology readiness from a mixture of summaries, validation payloads, and packet-level temporal rule diagnostics.

Effects:

- chronology pressure is still inferred in multiple places instead of read from one normalized object
- evidence and drafting flows remain vulnerable to summary drift
- readiness gates still rely heavily on counts instead of explicit coverage requirements

### Evidence support is chronology-aware, but task generation still depends on packet-derived temporal rule status

`_build_alignment_evidence_tasks(...)` already emits good chronology fields, but its control flow still starts from element packet fields such as `temporal_rule_status`, `temporal_rule_follow_ups`, and derived formula bundles.

Effects:

- authored intake chronology can influence tasks indirectly, but not as the canonical task source
- it is harder to distinguish authored chronology gaps from proof-engine-derived chronology gaps
- closure criteria are less stable than they should be because they mix authored and derived signals

### Inquiry planning sees chronology, but it still collapses multiple chronology concerns into generic priority terms

`build_inquiry_gap_context(...)` already knows about chronology closure, decision-document precision, and exhibit grounding. That is useful, but it still returns a general-purpose gap context instead of an operator-visible chronology objective ledger.

Effects:

- intake question selection is smarter, but still too summary-oriented
- the system can ask good chronology questions without retaining a durable question-to-issue closure map

## Target for the Next Batches

After the next batches:

1. Intake will expose one authored chronology readiness object derived from the event ledger, anchors, relations, and temporal issue registry.
2. Evidence task generation will consume that readiness object directly, with packet-level temporal diagnostics treated as additive evidence instead of the primary source.
3. Inquiry planning will map each chronology objective to concrete unresolved issue IDs, missing predicates, and provenance requirements.
4. Readiness scoring will consider anchor completeness, predicate completeness, provenance completeness, and resolution status, not only counts and generic rule states.

## Batch 1: Author a Stable Chronology Readiness Contract at Intake

### Goal

Promote authored intake chronology from a collection of registries into one explicit readiness object that downstream code can consume without reconstructing it.

### Primary files

- [complaint_phases/intake_case_file.py](../complaint_phases/intake_case_file.py)
- [intake_status.py](../intake_status.py)

### Work

Add a normalized intake chronology readiness payload, built directly from:

- `event_ledger`
- `timeline_anchors`
- `timeline_relations`
- `temporal_fact_registry`
- `temporal_relation_registry`
- `temporal_issue_registry`

The payload should minimally include:

- `contract_version`
- `event_count`
- `anchored_event_count`
- `unanchored_event_count`
- `relation_count`
- `issue_count`
- `blocking_issue_count`
- `open_issue_count`
- `resolved_issue_count`
- `issue_ids`
- `blocking_issue_ids`
- `missing_temporal_predicates`
- `required_provenance_kinds`
- `resolution_lane_counts`
- `issue_type_counts`
- `anchor_coverage_ratio`
- `predicate_coverage_ratio`
- `provenance_coverage_ratio`
- `ready_for_temporal_formalization`

### Acceptance criteria

1. The readiness object is authored in the intake refresh path, not synthesized later from UI or packet payloads.
2. [intake_status.py](../intake_status.py) preserves this object unchanged in the intake summary boundary.
3. Existing chronology registries remain available; this is additive, not a replacement.

## Batch 2: Make Evidence Task Generation Consume Authored Chronology Readiness

### Goal

Use the authored intake chronology readiness object as the primary source for task closure and chronology follow-up planning.

### Primary files

- [mediator/mediator.py](../mediator/mediator.py)
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)

### Work

Refactor `_build_alignment_evidence_tasks(...)` and nearby alignment summary builders so they:

- read authored chronology readiness first
- attach explicit source attribution for chronology fields, such as `chronology_source: authored_intake_registry` or `chronology_source: proof_diagnostics`
- separate authored unresolved issue IDs from proof-engine-derived issue IDs when both exist
- carry closure criteria directly on the task, for example:
  - `required_anchor_ids`
  - `required_temporal_predicates`
  - `required_provenance_kinds`
  - `closure_issue_ids`
  - `closure_ready_when`

The action type should continue to support `fill_temporal_chronology_gap`, but the task should be explicitly closeable by authored chronology coverage instead of only proof packet rule state.

### Acceptance criteria

1. A temporal task can be generated even when proof-engine metadata is sparse, as long as authored intake chronology gaps exist.
2. A temporal task can be marked operationally closeable from authored readiness improvements before theorem export is rerun.
3. Packet-level reasoning diagnostics remain additive and do not get discarded.

## Batch 3: Add a Chronology Objective Ledger to Intake Question Planning

### Goal

Turn chronology pressure from a generic list of priority terms into a stable mapping from unresolved issue to next question objective.

### Primary files

- [mediator/mediator.py](../mediator/mediator.py)
- [complaint_phases/denoiser.py](../complaint_phases/denoiser.py)

### Work

Extend `build_inquiry_gap_context(...)` so it emits a chronology objective ledger alongside the current priority terms.

Each ledger entry should include:

- `issue_id`
- `issue_type`
- `claim_types`
- `recommended_resolution_lane`
- `missing_temporal_predicates`
- `required_provenance_kinds`
- `preferred_question_objective`
- `preferred_question_type`
- `suggested_prompt_family`
- `blocking`

The denoiser should then be able to rank or rewrite questions against a specific chronology objective rather than only against broad categories such as `timeline` or `documents`.

### Acceptance criteria

1. Timeline questions can be traced back to concrete unresolved issue IDs.
2. Exhibit-grounding questions can be traced back to provenance requirements, not only low exhibit ratios.
3. Repeated chronology questions can be suppressed or escalated using issue-level closure state.

## Batch 4: Tighten Readiness and Proof Closure Scoring Around Chronology Coverage

### Goal

Make chronology readiness operationally meaningful in intake and evidence gates.

### Primary files

- [complaint_phases/phase_manager.py](../complaint_phases/phase_manager.py)
- [mediator/mediator.py](../mediator/mediator.py)
- [claim_support_review.py](../claim_support_review.py)

### Work

Update readiness scoring so it explicitly measures:

- anchor coverage
- predicate coverage
- provenance coverage
- resolution status coverage
- contradiction-adjusted chronology closure

Claim-level and packet-level readiness summaries should report not just counts, but closure ratios and explicit failure reasons.

### Acceptance criteria

1. A claim can be warning or blocked because chronology coverage is incomplete even when generic support counts look acceptable.
2. Review surfaces can explain the difference between:
   - missing facts
   - missing chronology predicates
   - missing provenance kinds
   - unresolved chronology contradictions
3. Drafting readiness, evidence readiness, and theorem readiness all point at the same chronology readiness contract.

## Validation Plan

### Focused tests

- [tests/test_intake_case_file.py](../tests/test_intake_case_file.py)
- [tests/test_mediator_three_phase.py](../tests/test_mediator_three_phase.py)
- [tests/test_claim_support_hooks.py](../tests/test_claim_support_hooks.py)
- [tests/test_document_pipeline.py](../tests/test_document_pipeline.py)

### Regression commands

```bash
.venv/bin/pytest tests/test_intake_case_file.py tests/test_mediator_three_phase.py -q
.venv/bin/pytest tests/test_claim_support_hooks.py tests/test_document_pipeline.py -q
.venv/bin/python scripts/run_claim_support_review_regression.py --browser off
.venv/bin/python scripts/run_claim_support_review_regression.py --browser on
```

## Recommended Implementation Order

1. Batch 1, because it creates the stable authored chronology contract.
2. Batch 2, because task generation should consume that contract before more UI or proof work is added.
3. Batch 3, because question planning should target authored unresolved chronology objectives.
4. Batch 4, because readiness scoring should be updated only after the new contract and task wiring exist.

## Non-Goals for This Batch

The next implementation slice should not:

- replace existing packet or theorem chronology diagnostics
- remove existing summary fields that current review and document surfaces depend on
- force exact timestamps where the intake state only supports a partial order
- move chronology logic into the UI layer

The objective is to make authored chronology state authoritative earlier, not to rebuild the whole temporal proof stack.