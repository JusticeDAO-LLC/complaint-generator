# Claim Support Review Dashboard File Worklist

Date: 2026-03-14

## Purpose

Translate the Claim Support Review Dashboard milestone plan into file-by-file implementation targets for the earliest and highest-leverage slices.

This is the most execution-oriented companion to:

- `docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_IMPROVEMENT_PLAN.md`
- `docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md`
- `docs/PAYLOAD_CONTRACTS.md`
- `docs/APPLICATIONS.md`

Use this document when selecting the next coding slice for `/claim-support-review`.

## Scope

This worklist focuses on the milestones that now have the clearest implementation entrypoints:

- M0: Question and testimony foundation
- M1: Document intake and decomposition plane
- M2: Fact registry and element support ledger
- M3: Graph snapshot persistence and support paths

Retrieval, proof execution, and full productization remain downstream of these contracts, but the files below are the concrete starting points that determine whether later milestones stay clean.

## M0 File Worklist

### `templates/claim_support_review.html`

Tasks:

- add a question recommendation section that groups prompts by testimony, document request, contradiction resolution, and authority clarification
- add a structured testimony composer with raw narrative, event date, actor, act, target, harm, confidence, and firsthand status
- show why each question matters and which claim element it targets
- surface testimony-backed support counts or chips in the existing element review view
- preserve current manual-resolution and follow-up controls while introducing the new intake sections

Done when:

- operators can answer targeted questions without leaving `/claim-support-review`
- testimony can be entered in structured form without losing raw narrative
- each unresolved element shows targeted questions and visible testimony support

Validation:

- browser-facing review surface tests
- `./.venv/bin/python -m pytest tests/test_review_surface.py tests/test_review_api.py -q`

### `mediator/claim_support_hooks.py`

Tasks:

- add persistence helpers for testimony records, testimony revisions, and question recommendation packets
- normalize testimony-to-element linking so it uses the same claim-support identifiers already present in the review payload
- extend coverage summaries to include testimony-backed support counts
- prepare stable element-ledger outputs so M2 does not require a second contract rewrite

Done when:

- testimony records can be saved, reloaded, and linked to claim elements through stable IDs
- question recommendations and testimony changes are visible in review payloads without recomputing everything from scratch

Validation:

- focused claim-support hook tests
- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py tests/test_review_api.py -q`

### `complaint_phases/denoiser.py`

Tasks:

- promote current gap prompts into question recommendation packets with legal-element targeting and expected proof gain
- distinguish missing-proof prompts from contradiction-resolution prompts
- suppress low-value duplicate questions when similar graph gaps already map to the same legal need

Done when:

- question outputs are recommendation objects rather than loose text prompts
- each recommendation includes a clear legal or contradiction rationale

Validation:

- focused question-ranking tests
- add or extend denoiser tests alongside claim-support hook tests

### `complaint_phases/knowledge_graph.py`

Tasks:

- expose gap summaries in a form that question ranking can consume deterministically
- add or refine timeline, damages, actor-identification, and contradiction-sensitive gap categories
- preserve existing graph-gap outputs used elsewhere in the repo

Done when:

- question planning receives stable, typed gap signals instead of ad hoc string cues

Validation:

- focused knowledge-graph gap tests
- relevant claim-support integration tests

### `complaint_phases/dependency_graph.py`

Tasks:

- ensure dependency edges can explain why one unanswered point blocks a legal element
- provide dependency-aware hints for question ordering and proof-gain scoring

Done when:

- question planners can rank prerequisite questions before downstream or redundant questions

Validation:

- focused dependency-graph tests where available
- claim-support integration tests for question ordering

### `docs/PAYLOAD_CONTRACTS.md`

Tasks:

- document the question recommendation payload family
- document testimony record payloads and testimony-backed support summary fields
- document any new review payload sections for question groups, testimony records, or testimony support counts

Done when:

- frontend and backend slices can evolve against an explicit contract rather than inferred fields

Validation:

- payload contract regression tests if present

### `docs/APPLICATIONS.md`

Tasks:

- update the `/claim-support-review` description from review-only to guided question, testimony, and proof-intake workflow
- note any new dashboard sections or expected operator tasks introduced by M0

Done when:

- application-level docs match the real operator workflow

## M1 File Worklist

### `templates/claim_support_review.html`

Tasks:

- add document upload and linked-document intake controls
- show parse status, parse quality tier, chunk previews, and remediation actions
- attach uploaded artifacts to claim or testimony context in the dashboard view

Done when:

- operators can add supporting materials directly from the dashboard and inspect parse status immediately

Validation:

- browser-facing upload workflow tests
- `./.venv/bin/python -m pytest tests/test_review_surface.py tests/test_review_api.py -q`

### `integrations/ipfs_datasets/documents.py`

Tasks:

- confirm dashboard-ingested uploads and URLs flow through the same parse entrypoints as evidence and web evidence
- preserve chunk IDs, parse quality, and transform lineage needed for dashboard drilldowns
- keep low-quality or partial parses reviewable for remediation

Done when:

- dashboard document intake does not require hook-local parsing branches

Validation:

- focused parse tests
- `./.venv/bin/python -m pytest tests/test_evidence_hooks.py tests/test_web_evidence_hooks.py -q`

### `mediator/evidence_hooks.py`

Tasks:

- add dashboard-facing artifact intake helpers that reuse the shared parse contract
- preserve artifact IDs, chunk references, and remediation signals in stored metadata

Done when:

- dashboard uploads land in the same artifact family as other evidence ingestion paths

Validation:

- focused evidence-hook tests

### `mediator/web_evidence_hooks.py`

Tasks:

- support linked-document or page intake from the dashboard through existing web-evidence storage patterns
- preserve archive and fetch provenance needed for later support-path views

Done when:

- linked materials entered from the dashboard are corpus-compatible with uploaded evidence

Validation:

- focused web-evidence tests

### `mediator/claim_support_hooks.py`

Tasks:

- link newly created artifact records into current claim-support review state
- expose parse quality and chunk summaries through the review payload
- prepare fact-registry hooks so M2 can bind document facts to support ledgers

Done when:

- newly uploaded or linked materials appear in the review payload with enough context for operator action

Validation:

- review API and claim-support hook tests

### `docs/PAYLOAD_CONTRACTS.md`

Tasks:

- document evidence artifact payloads exposed through `/claim-support-review`
- document parse-quality, transform-lineage, and chunk-reference fields used by the dashboard

Done when:

- dashboard document drilldowns rely on a stable contract

## M2 File Worklist

### `mediator/claim_support_hooks.py`

Tasks:

- define or extend durable fact records covering testimony facts, chunk-backed facts, and authority-linked facts
- add fact-to-element, fact-to-artifact, and fact-to-authority associations
- emit an element support ledger keyed by concrete fact IDs
- normalize uncertainty and contradiction states so later proof logic can build on them directly

Done when:

- every element status in the review payload can point to concrete facts and source lineage

Validation:

- focused claim-support hook tests
- `./.venv/bin/python -m pytest tests/test_claim_support_hooks.py tests/test_review_api.py -q`

### `integrations/ipfs_datasets/types.py`

Tasks:

- formalize fact and support-ledger model shapes used by review payloads and later graph or logic workflows
- standardize fields for confidence, provenance, contradiction state, and validation state

Done when:

- testimony, document, and authority facts share one compatible type family

Validation:

- adapter type-shape regression tests where present

### `integrations/ipfs_datasets/provenance.py`

Tasks:

- ensure fact records preserve chunk-level, artifact-level, and transform-lineage provenance in one shape
- keep enough lineage detail to regenerate support explanations without re-parsing

Done when:

- fact-ledger records remain traceable across testimony, uploads, linked pages, and authorities

Validation:

- provenance-oriented hook tests

### `templates/claim_support_review.html`

Tasks:

- add an element support ledger view or drilldown
- show fact IDs, source type, confidence, contradiction state, and supporting source references without overwhelming the default workflow

Done when:

- operators can inspect why an element is marked supported, partial, missing, or uncertain

Validation:

- browser-facing review surface tests

### `docs/PAYLOAD_CONTRACTS.md`

Tasks:

- document fact records, support-ledger payloads, and contradiction-state fields
- document any new review payload drilldowns for element support details

Done when:

- later graph, retrieval, and proof work can build on explicit fact-ledger contracts

## M3 File Worklist

### `integrations/ipfs_datasets/graphs.py`

Tasks:

- persist graph snapshots with stable IDs usable by review payloads
- add support-path and contradiction-path query helpers
- unify graph projections from testimony and document-backed facts

Done when:

- review and follow-up flows can reference reusable graph snapshots instead of one-off extraction output

Validation:

- graph adapter and claim-support integration tests

### `complaint_phases/knowledge_graph.py`

Tasks:

- attach fact and artifact lineage to graph nodes where feasible
- improve entity resolution inputs used to reduce duplicate actors, events, and evidence nodes

Done when:

- graph support paths remain explainable and do not fragment across duplicate nodes unnecessarily

Validation:

- knowledge-graph and claim-support tests

### `complaint_phases/dependency_graph.py`

Tasks:

- align dependency outputs with reusable graph snapshot identifiers and path summaries

Done when:

- dependency explanations can appear inside support-path drilldowns without custom translation layers

Validation:

- dependency and claim-support tests

### `mediator/claim_support_hooks.py`

Tasks:

- expose graph snapshot references and support-path summaries in review payloads
- preserve fallback summaries when graph persistence is unavailable

Done when:

- graph-backed review data is visible without breaking degraded-mode behavior

Validation:

- review API regression tests

### `templates/claim_support_review.html`

Tasks:

- add graph and support-path drilldowns that stay secondary to the main operator workflow
- expose graph references without forcing operators into a graph-first UI

Done when:

- graph detail is available when needed but does not crowd question, testimony, or document intake flows

Validation:

- browser-facing review surface tests

## Slice Selection Guidance

Start with the smallest vertical slice inside M0:

1. `complaint_phases/denoiser.py` recommendation packet shape
2. `mediator/claim_support_hooks.py` testimony persistence and element linking
3. `templates/claim_support_review.html` question plus testimony UI
4. `docs/PAYLOAD_CONTRACTS.md` contract updates

That slice gives the dashboard a real guided-intake loop before document, graph, or proof work deepens.