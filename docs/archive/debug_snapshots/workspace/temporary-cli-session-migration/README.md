# Temporary CLI Session Migration Bundle

This workspace bundle consolidates the prior complaint work for the temporary CLI intake session into one place under the complaint-generator workspace.

## What Is Included

### Source statefile

- `source-statefile/temporary-cli-session-latest.json`

This is the intake session that drives the current migration.

### Prior research-results complaint packet

- `prior-research-results/chronology/`
- `prior-research-results/emergency_motion_packet/`
- `prior-research-results/full-evidence-review-run/`

This is the curated set of earlier District of Oregon complaint and emergency-motion artifacts that were previously living only under `research_results/evidence_review_20260328_181601/chronology/`.

The bundle also includes a full copied snapshot of the earlier evidence-review run so the complete prior work product is preserved under the workspace folder.

Included items cover:

- federal complaint candidate
- authority and evidence map
- TRO / preliminary injunction motion
- notice, declaration, proposed order, Rule 65 certification, certificate of service
- exhibit index, filing checklist, packet manifest, and Julio declaration template
- the assembled emergency motion packet directory

### Workspace-generated intake-driven work

- `workspace-generated/improve_temporary_session_complaint.py`
- `workspace-generated/improved-complaint-from-temporary-session.md`
- `workspace-generated/improved-complaint-from-temporary-session.summary.json`
- `workspace-generated/did-key-hacc-temp-session.json`
- `workspace-generated/did-key-legacy-temporary-session.json`
- `workspace-generated/evidence/did-key-legacy-temporary-session/`

This is the newer workspace-side work that re-ingests the temporary CLI session into the complaint workspace and produces a more specific complaint draft tied to imported evidence.

## Live Generator Improvements

The complaint generator itself was also improved in the live codebase, not just in copied artifacts.

Relevant live source:

- `scripts/synthesize_hacc_complaint.py`

The key improvements are:

- complaint synthesis now falls back to `state.inquiries` when `conversation_history` is sparse or empty
- factual allegations now prioritize party facts, communication barriers, chronology, and concrete intake facts before readiness boilerplate
- proposed allegations and claim theory now use the same combined intake source
- structured handoff promotion now includes more grounded evidence lines by default

## Evidence Sources Used

The migrated workspace work draws from or references these live source trees in the repo:

- `evidence/`
- `hacc_research/`
- `hacc_website/`
- `legal_data/`
- `research_data/`
- `research_results/`

These source trees were not wholesale duplicated into this bundle because they are large and remain authoritative in place. The bundle instead carries:

- the copied prior complaint packet from `research_results`
- the workspace evidence session generated from selected imports
- the improved workspace draft and its summary metadata

## Practical Starting Points

If you want the best current workspace artifact first, start with:

- `workspace-generated/improved-complaint-from-temporary-session.md`

If you want the earlier federal filing packet and TRO materials, start with:

- `prior-research-results/chronology/formal_complaint_us_district_oregon_federal_filing_candidate_court_ready.md`
- `prior-research-results/chronology/motion_for_tro_and_preliminary_injunction_us_district_oregon_court_ready.md`
- `prior-research-results/emergency_motion_packet/`

## Current Gaps

The main remaining gap is not migration but refinement:

- tie exact dates and named staff to exhibit-level email and document records
- reconcile any conflicting TPV-request timing statements against the imported evidence
- rerun the live synthesis pipeline against the grounded artifacts now that the generator better uses the temporary session intake