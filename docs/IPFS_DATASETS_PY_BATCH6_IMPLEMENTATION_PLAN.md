# IPFS Datasets Py Batch 6 Implementation Plan

Date: 2026-03-12
Status: In progress; drafting-readiness payloads, browser rendering, and focused contracts are implemented in the current checkout

Companion docs:

- `docs/IPFS_DATASETS_PY_IMPROVEMENT_PLAN.md`
- `docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md`
- `docs/IPFS_DATASETS_PY_NEXT_BATCH_PLAN.md`
- `docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md`
- `docs/IPFS_DATASETS_PY_FILE_WORKLIST.md`
- `docs/PAYLOAD_CONTRACTS.md`
- `docs/APPLICATIONS.md`

## Purpose

Turn Batch 6, drafting and export integration, into issue-sized implementation slices that can be executed without reopening the broader roadmap.

This plan assumes the current repository already has:

- a working formal complaint builder in `document_pipeline.py`
- a browser drafting workflow at `/document`
- a document export API in `applications/document_api.py`
- claim-support review, follow-up summaries, authority-treatment summaries, and validation-aware planning already available elsewhere in the system

The goal of Batch 6 is to connect those existing drafting surfaces to the shared support, authority, graph, and validation layers so complaint export is support-aware rather than text-generation-only.

## Batch 6 outcome

At the end of Batch 6, complaint-generator should be able to build a filing draft that can explain, for each major complaint section:

- what source-backed support exists
- what authority support is adverse, uncertain, or procedurally weak
- what factual or legal prerequisites are still missing
- whether proof or contradiction diagnostics raise drafting warnings
- which exhibits, archive captures, and provenance-linked artifacts support the draft

The main success criterion is that the drafting workflow can consume mediator-visible support state directly, rather than reconstructing filing readiness from loosely related summaries.

## Non-goals

Batch 6 should not attempt to:

- redesign the complaint text model from scratch
- replace the review dashboard with the document builder
- implement full theorem-prover workflows end to end
- introduce a new graph-store architecture
- solve all product UX around operator review and drafting in one pass

If a change is primarily about GraphRAG scoring internals, graph persistence redesign, or new theorem-prover bridges, it belongs to earlier technical batches rather than this drafting-integration pass.

## Target files

- `document_pipeline.py`
- `applications/document_api.py`
- `templates/document.html`
- `mediator/mediator.py`
- `mediator/claim_support_hooks.py`
- `claim_support_review.py`
- `docs/PAYLOAD_CONTRACTS.md`
- `docs/APPLICATIONS.md`
- `tests/test_document_pipeline.py`
- `tests/test_claim_support_review_template.py`
- `tests/test_review_api.py`

## Implementation slices

Current implementation status:

- Slice 1 is implemented in the current checkout through `document_pipeline.py` package payloads, mediator-driven support fallback usage, and claim or section readiness synthesis.
- Slice 2 is implemented for the current warning family covering unresolved elements, proof gaps, contradiction signals, adverse authority, authority uncertainty, and procedural-prerequisite warnings.
- Slice 3 is implemented in the `/document` browser workflow, including section metrics, claim warning cards, source drilldown, and deep links into `/claim-support-review`.
- Slice 4 is implemented for the current payload and UI contract through focused tests and documentation updates; broader end-to-end productization can continue incrementally from this baseline.

## Slice 1: Drafting-readiness payloads

Goal:

- expose one mediator-consumable drafting-readiness bundle that maps claim-support state into complaint sections

Primary files:

- `mediator/mediator.py`
- `mediator/claim_support_hooks.py`
- `claim_support_review.py`
- `document_pipeline.py`

Tasks:

- derive section-level readiness for factual allegations, jurisdiction and venue, claims for relief, requested relief, and exhibits
- map existing claim-element support and gap outputs into document-section bundles rather than making the document pipeline infer section readiness ad hoc
- preserve compact counts while also exposing section-level drilldown material that the drafting workflow can consume safely

Done when:

- the document pipeline can request a drafting-readiness bundle from the mediator without reading raw support tables or reconstructing section status from unrelated review payload fragments

Suggested issue title:

- `Add mediator-visible drafting readiness bundles for complaint sections`

## Slice 2: Drafting warnings and guardrails

Goal:

- turn support, authority-treatment, and validation state into explicit drafting warnings before export

Primary files:

- `document_pipeline.py`
- `mediator/legal_authority_hooks.py`
- `mediator/claim_support_hooks.py`
- `docs/PAYLOAD_CONTRACTS.md`

Tasks:

- surface warnings for adverse authority, weak treatment confidence, unresolved good-law confirmation, missing procedural prerequisites, and failed premises
- distinguish hard blockers from soft warnings so degraded mode and partial-support drafting still work
- keep warning objects stable enough for browser, API, and future CLI consumers

Done when:

- exported drafting payloads can identify legally weak or unsupported sections without blocking all artifact generation by default

Suggested issue title:

- `Add support-aware drafting warnings for authority and proof gaps`

## Slice 3: Browser builder readiness rendering

Goal:

- make the `/document` workflow show filing-readiness and support provenance before or alongside generated artifacts

Primary files:

- `templates/document.html`
- `applications/document_api.py`

Tasks:

- render section readiness, warning summaries, and source-backed artifact context in the browser builder
- keep the current builder and preview interactions intact while adding filing-readiness feedback
- preserve navigation between `/document` and `/claim-support-review` as complementary workflows rather than separate silos

Done when:

- operators can see whether a complaint section is grounded, weak, or blocked directly in the browser builder before downloading DOCX or PDF artifacts

Suggested issue title:

- `Render filing readiness and drafting warnings in the document builder`

## Slice 4: Contracts, tests, and documentation

Goal:

- lock the drafting workflow into stable payload and application contracts

Primary files:

- `tests/test_document_pipeline.py`
- `tests/test_claim_support_review_template.py`
- `tests/test_review_api.py`
- `docs/PAYLOAD_CONTRACTS.md`
- `docs/APPLICATIONS.md`

Tasks:

- add focused tests for section readiness, drafting warnings, and document workflow round-trips
- document document-pipeline payloads for warnings, section readiness, and support-bundle metadata
- confirm degraded mode when authority-treatment, graph, or logic enrichments are absent

Done when:

- the document workflow has focused tests and stable documentation rather than relying on incidental coverage from the broader review or application suites

Suggested issue title:

- `Document and validate support-aware formal complaint payloads`

## Recommended execution order

1. Slice 1
2. Slice 2
3. Slice 3
4. Slice 4

This order matters because the browser builder should not render readiness and warning state until the payload family is stable, and the payload family should not stabilize until the mediator and document pipeline agree on section-level support semantics.

## Validation plan

Minimum focused validation after each slice:

```bash
./.venv/bin/python -m pytest tests/test_document_pipeline.py -q
./.venv/bin/python -m pytest tests/test_review_api.py -q
```

Additional browser-workflow validation when template behavior changes:

```bash
./.venv/bin/python -m pytest tests/test_claim_support_review_template.py -q
```

Use the review API slice when document payloads depend on shared support, authority, or validation summaries rather than document-only transforms.

## Stop or go criteria

Go past Batch 6 only when all of the following are true:

- the document pipeline can consume section-level support bundles directly from the mediator or a stable shared payload builder
- document payloads expose stable readiness and warning objects
- the browser drafting workflow can render filing-readiness status without requiring raw JSON inspection
- support-aware drafting remains usable in degraded mode
- focused document, review, and template tests pass

Do not treat Batch 6 as complete if the browser builder still looks support-aware only because it is indirectly reusing unrelated review summaries without a stable section-level contract.

## Risks

### Risk: drafting consumes unstable review payload fragments

Mitigation:

- add an explicit drafting-readiness payload family rather than scraping existing review structures ad hoc

### Risk: warnings become indistinguishable from blockers

Mitigation:

- separate warning severity and recommendation semantics so degraded mode and partial-support exports remain possible

### Risk: browser UX outruns payload maturity

Mitigation:

- land mediator and document-pipeline payload shapes before expanding the `/document` template

### Risk: drafting logic duplicates review logic

Mitigation:

- centralize section-readiness and warning synthesis in mediator or shared payload helpers rather than rebuilding them inside the template or API handler

## Deliverable checklist

- [x] section-level drafting-readiness bundles exist
- [x] drafting warnings distinguish authority, factual, procedural, and proof-related weakness
- [x] document API responses expose readiness and warning state
- [x] `/document` renders filing-readiness status before or alongside artifact generation
- [x] payload contracts and application docs are updated
- [x] focused document, review, and template tests pass

Validated in current checkout:

- `./.venv/bin/python -m pytest tests/test_document_pipeline.py tests/test_claim_support_review_template.py -q`
- `./.venv/bin/python -m pytest tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py tests/test_mediator.py tests/test_cli_commands.py tests/test_formal_document_pipeline.py -q`

## Recommended first coding slice

If Batch 6 starts now, the recommended first coding slice is:

1. `mediator/mediator.py`
2. `mediator/claim_support_hooks.py`
3. `claim_support_review.py`
4. `document_pipeline.py`
5. `tests/test_document_pipeline.py`
6. `tests/test_review_api.py`

That slice has the highest leverage because it defines the section-level readiness bundle the rest of the drafting workflow depends on. Once that contract exists, warning synthesis, browser rendering, and payload documentation become much lower-risk follow-on work.