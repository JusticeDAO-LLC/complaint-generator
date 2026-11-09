# Claim Support Review Dashboard Improvement Plan

This plan describes how to turn the current `/claim-support-review` surface into a stronger operator workflow for testimony capture, document intake, graph-backed evidence organization, vector retrieval, and legal sufficiency review.

The goal is not only to show coverage, but to make sure the system:

1. asks better questions,
2. captures better testimony,
3. ingests and decomposes uploaded documents into reusable evidence units,
4. builds durable knowledge-graph and vector-index representations,
5. evaluates claim facts against legal requirements using graph and logic layers, and
6. feeds those results back into the dashboard, follow-up planner, and document builder.

## Current Baseline

- [templates/claim_support_review.html](../templates/claim_support_review.html) already provides an operator dashboard with coverage summaries, follow-up execution controls, manual review resolution, and recent follow-up history.
- [docs/APPLICATIONS.md](./APPLICATIONS.md) defines `/claim-support-review` as the operator review dashboard for claim support, parse-quality signals, follow-up execution, recent history, and manual-review resolution.
- [docs/PAYLOAD_CONTRACTS.md](./PAYLOAD_CONTRACTS.md) already exposes a substantial claim-support review contract, including `claim_coverage_summary`, `claim_support_gaps`, `claim_contradiction_candidates`, `claim_reasoning_review`, `follow_up_plan_summary`, and `follow_up_history_summary`.
- [complaint_phases/denoiser.py](../complaint_phases/denoiser.py) can already generate gap-driven questions from the current knowledge graph and dependency graph.
- [complaint_phases/knowledge_graph.py](../complaint_phases/knowledge_graph.py) can detect unsupported claims, missing timeline data, isolated entities, and other graph gaps.
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py) already persists claim requirements, support links, follow-up execution history, and support snapshots in DuckDB.
- [integrations/ipfs_datasets/documents.py](../integrations/ipfs_datasets/documents.py) already provides a real parse contract with normalization, chunking, parse quality signals, and transform lineage.
- [integrations/ipfs_datasets/graphs.py](../integrations/ipfs_datasets/graphs.py) already provides lightweight graph extraction and support clustering.
- [integrations/ipfs_datasets/logic.py](../integrations/ipfs_datasets/logic.py) is still a placeholder seam: the contract exists, but proof and contradiction execution currently returns `not_implemented` when the adapter is available.

This means the repo already has the right seams, but they are not yet composed into one full testimony-to-proof workflow.

## Desired End State

The target workflow for `/claim-support-review` should be:

1. The dashboard loads the current claim and section context.
2. The system identifies proof gaps, contradiction candidates, and low-confidence evidence.
3. The question engine asks a small number of high-value questions tailored to the unresolved legal elements.
4. The user can provide both narrative testimony and supporting documents.
5. Uploaded or referenced documents are parsed, chunked, lineage-tracked, vector-indexed, and graph-linked.
6. Facts extracted from testimony and documents are attached to claim elements and legal elements.
7. Authorities and legal rules are normalized into a law-facing graph.
8. Facts are checked against legal requirements, exceptions, and contradictions.
9. The dashboard reports what is satisfied, what is still missing, what is contradicted, what evidence is weak, and what follow-up question or acquisition step should happen next.
10. The same validated support state feeds the `/document` builder and downstream drafting logic.

## Core Principles

### 1. Keep the adapter boundary intact

As documented in [docs/IPFS_DATASETS_PY_DEPENDENCY_MAP.md](./IPFS_DATASETS_PY_DEPENDENCY_MAP.md), production integration with `ipfs_datasets_py` should continue to flow only through `integrations/ipfs_datasets/*`.

The dashboard plan should not introduce direct production imports of `ipfs_datasets_py` outside that boundary.

### 2. Treat testimony and documents as one evidence substrate

The system should not treat questionnaire answers, uploaded files, web captures, and legal authorities as separate silos. They should all become normalized evidence artifacts with:

- stable IDs,
- parse metadata,
- chunk lineage,
- graph nodes,
- vector embeddings,
- claim-element links, and
- legal sufficiency annotations.

### 3. Ask questions only when they improve proof state

Question generation should be tied to missing legal elements, contradiction resolution, timeline gaps, damages gaps, and evidentiary weakness. It should not be a generic interview loop.

### 4. Make operator review explainable

The dashboard should show why a claim element is missing, contradicted, or weak, which fact and document chunks support that conclusion, and what the next best action is.

## Capability Map

| Need | Current seam | Current status | Needed improvement |
|---|---|---|---|
| Gap-driven questioning | [complaint_phases/denoiser.py](../complaint_phases/denoiser.py) | baseline gap prompts exist | prioritize by legal value, evidence quality, and contradiction impact |
| Claim and evidence graphing | [complaint_phases/knowledge_graph.py](../complaint_phases/knowledge_graph.py), [complaint_phases/dependency_graph.py](../complaint_phases/dependency_graph.py) | core graph structures exist | unify testimony, document chunks, claim elements, and law elements |
| Claim support persistence | [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py) | strong review-state persistence exists | add durable fact registry and evidence-to-proof lineage |
| Document decomposition | [integrations/ipfs_datasets/documents.py](../integrations/ipfs_datasets/documents.py) | parse and chunk contract exists | route all uploaded/supporting documents through one ingestion workflow |
| Graph extraction | [integrations/ipfs_datasets/graphs.py](../integrations/ipfs_datasets/graphs.py) | lightweight graph extraction exists | persist graph snapshots and expose support-path queries |
| Vector retrieval | `integrations/ipfs_datasets/vector_store.py`, document optimization embeddings seam | available in adjacent workflow | add claim-review indexing and retrieval sessions |
| Legal logic/proof | [integrations/ipfs_datasets/logic.py](../integrations/ipfs_datasets/logic.py) | contract exists, implementation is placeholder | implement proof-gap and contradiction checking |
| GraphRAG / ontology support | `integrations/ipfs_datasets/graphrag.py`, `build_ontology`, `validate_ontology` | partially wired | apply to law-element mapping and support scoring |
| Operator dashboard | [templates/claim_support_review.html](../templates/claim_support_review.html) | coverage dashboard exists | expand into testimony/document/proof orchestration surface |

## Main Gaps

1. The dashboard is a review and follow-up surface, but not yet a guided testimony-capture surface.
2. Question generation uses graph gaps, but it does not yet optimize for legal sufficiency, contradiction resolution, or evidentiary quality.
3. The document ingestion contract exists, but the dashboard does not yet expose a first-class document upload and decomposition workflow.
4. The graph adapter can extract graph payloads, but persistent graph query and claim-element proof-path reporting are still limited.
5. The logic adapter exposes the right contract but still does not prove elements or detect contradictions.
6. The current coverage payload is rich, but it does not yet present a canonical “facts applied to law” view per element.
7. Vector search is present elsewhere in the repo, but not yet a first-class retrieval plane for dashboard evidence review and question planning.
8. There is no unified corpus object that consistently links testimony answers, document chunks, evidence facts, authority rules, and legal predicates.

## Recommended Architecture

### Layer 1: Intake and testimony capture

Extend `/claim-support-review` so the operator can enter or edit:

- witness testimony,
- claimant timeline events,
- damages descriptions,
- responsible-party identifications,
- evidence descriptions,
- document uploads or linked documents,
- confidence or certainty markers for testimony.

This should produce a normalized testimony record family, not just transient browser state.

### Layer 2: Document ingestion and decomposition

Every uploaded or linked document should go through [integrations/ipfs_datasets/documents.py](../integrations/ipfs_datasets/documents.py) to generate:

- normalized text,
- document chunks,
- parse quality summary,
- transform lineage,
- document metadata,
- OCR fallback status,
- page-aware provenance,
- chunk-level stable IDs.

The ingestion workflow should emit a stable artifact record that can be linked into claim support, graph extraction, vector indexing, and proof analysis.

### Layer 3: Fact registry and support linking

Build on [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py) to create a broader fact registry contract with:

- fact ID,
- source artifact ID,
- chunk ID or text span,
- extracted proposition text,
- claim type,
- claim element ID,
- confidence,
- provenance metadata,
- contradiction flags,
- validation state.

This should become the shared substrate used by the dashboard, graphs, vector search, proof logic, and drafting.

### Layer 4: Graph construction

Use [integrations/ipfs_datasets/graphs.py](../integrations/ipfs_datasets/graphs.py) and [complaint_phases/knowledge_graph.py](../complaint_phases/knowledge_graph.py) to build:

- testimony graph,
- document graph,
- support graph,
- law graph,
- claim-element satisfaction graph.

The graph model should include at minimum:

- parties,
- acts,
- dates,
- documents,
- factual propositions,
- claim elements,
- legal rules,
- exceptions and defenses,
- support and contradiction edges,
- provenance edges from facts to source chunks.

### Layer 5: Vector retrieval plane

Create a dashboard-facing retrieval session layer over chunk embeddings so the operator and planner can:

- retrieve top evidence chunks for a claim element,
- cluster near-duplicate evidence,
- compare testimony with document text,
- surface semantically related authorities,
- attach retrieved context to question prompts and legal validation.

This should use the same adapter boundary as the existing embeddings router usage in [document_optimization.py](../document_optimization.py).

### Layer 6: Law evaluation and proof

Implement the currently placeholder functions in [integrations/ipfs_datasets/logic.py](../integrations/ipfs_datasets/logic.py) so each claim element can produce:

- provable facts,
- missing predicates,
- contradiction candidates,
- exception or defense triggers,
- uncertain facts,
- proof explanation.

This is the critical layer that turns “coverage” into “facts as applied to law fulfills legal requirements.”

### Layer 7: Dashboard explanation and actioning

The dashboard should present, for each claim element:

- status: supported, partially supported, missing, contradicted, uncertain,
- governing legal rule or element,
- supporting testimony facts,
- supporting document chunks,
- supporting authorities,
- contradiction sources,
- proof-gap explanation,
- recommended next question,
- recommended next acquisition action,
- recommended drafting impact.

## Delivery Workstreams

## Screenshot And Router Review Addendum: Layperson Docket UX

Date: 2026-04-20

This addendum records a pre-implementation UI/UX review pass using Playwright screenshot artifacts from the unified workspace:

- `artifacts/ui-audit-layperson/screenshots/workspace-homepage.png`
- `artifacts/ui-audit-layperson/screenshots/workspace-intake.png`
- `artifacts/ui-audit-layperson/screenshots/workspace-evidence.png`
- `artifacts/ui-audit-layperson/screenshots/workspace-review.png`
- `artifacts/ui-audit-layperson/screenshots/workspace-draft.png`

The screenshot workflow did attempt to route those images through `MultimodalRouterBackend`. The multimodal review and text fallback both timed out, so the saved router artifact at `artifacts/ui-audit-layperson/reviews/iteration-01-review.json` is the deterministic fallback. That timeout is itself a P0 reliability finding: the review/optimizer path must return a bounded artifact and show the fallback reason in the workspace instead of leaving an operator guessing whether visual review actually occurred.

The visual review also expands the product target. The dashboard should not only help an operator review claim support. It should help a layperson create or respond to legal complaints while managing a docket of documents, inspecting and labeling those documents, annotating evidence spans, and asking grounded questions about the docket through `llm_router` and `multimodal_router`.

### Observed UX Risks

1. The current workspace is capability-rich but too dense for a stressed layperson. Intake, evidence, review, draft, Gmail import, MCP examples, release-gate metadata, and generated pleadings appear as long technical panels rather than a small set of obvious next actions.
2. The sticky bottom navigation can cover content in full-page screenshots, especially on intake, evidence, review, and draft. It should reserve layout space or collapse into a safer mobile/action-bar pattern.
3. Evidence intake exposes advanced Gmail, DuckDB, CLI, MCP, OAuth, checkpoint, and JSON-example controls directly in the main layperson path. These should move behind an "Advanced import" or operator mode while the default path stays document/task focused.
4. Review repeats similar proof maps and support cards. Counts are useful, but the user needs one clear answer per element: "what proves this, what is still thin, and what should I do next?"
5. Draft is visually overloaded. The release gate, checklist, composer, recommendations, and full pleading preview compete for attention. The layperson path should show one filing-readiness decision and one primary next action before exposing full document text.
6. Docket management is not yet visible as a primary workflow. There is no first-class list of docket documents, document status, due dates, required response type, annotation progress, or unanswered document questions.
7. Document analysis is not yet anchored in a viewer. A layperson needs to see the actual PDF/image/text page, select a span, apply a label, and ask a question with citations back to that page or span.
8. The chatbot is not presented as a document-grounded assistant. It needs visible scope, cited answers, confidence/fallback state, and a way to turn an answer into a saved annotation, issue, timeline event, or response draft note.
9. Router and optimizer failures are too invisible. If `multimodal_router` times out or falls back to `llm_router`, the UI should say so plainly and preserve a review artifact.
10. Browser regression currently has two pre-implementation blockers: the unified workspace flow tried to click a hidden `#chat-open-profile` link, and the homepage flow expected a stale provider order string. Screenshot review should not depend on brittle hidden controls or outdated provider-order assertions.

### Revised Product Shape

The next UI iteration should treat the workspace as four visible layperson lanes:

1. **Intake**: Tell the story and capture structured facts.
2. **Docket**: Add, triage, inspect, label, and annotate court and evidence documents.
3. **Review**: See what each claim or response issue is supported by, what is thin, and what to do next.
4. **Draft**: Generate or revise a complaint, answer, response, motion, or filing packet only after the record has an explicit readiness posture.

Advanced import, MCP, CLI, DuckDB, provider diagnostics, and optimizer controls should remain discoverable, but they should be secondary operator tools rather than default layperson surface area.

### New Workstream 0: Audit Reliability And Screenshot Review

Priority: P0

Goal: make visual UX review reliable before implementation starts.

Primary files:

- `complaint_generator/ui_ux_workflow.py`
- `playwright/tests/complaint-flow.spec.js`
- `templates/workspace.html`
- `static/complaint_app_shell.js`

Work:

- keep the deterministic fallback, but show fallback status in the workspace UX Audit panel,
- ensure router calls are truly bounded and cannot leave progress stuck at `running_router_review`,
- fix the hidden profile-link browser failure or make the test navigate by URL when the link is intentionally hidden,
- update provider-order expectations so test assertions match the actual configured router order,
- add a screenshot-review test that succeeds with existing screenshots even when the full journey has unrelated failures.

Acceptance criteria:

1. Playwright can capture homepage, intake, evidence, review, draft, docket, document viewer, and chat screenshots in one reliable command.
2. Router review returns either a multimodal result or a deterministic fallback artifact within the configured timeout.
3. The workspace shows whether the latest UX review used `multimodal_router`, `llm_router`, or deterministic fallback.

### New Workstream 1: Docket Command Center

Priority: P0

Goal: make docket documents the organizing object for complaints and responses.

Work:

- add a docket list with document type, source, filing date, response due date, status, and assigned claim/issue labels,
- distinguish court filings, notices, exhibits, correspondence, agency records, and user-uploaded evidence,
- show a primary next action per docket item: inspect, label, annotate, ask, respond, attach to claim, or mark complete,
- let users create a response task from a docket document, including answer/denial/admission, affirmative defense, objection, motion, or records request paths,
- persist docket item state separately from generic evidence records while linking both to the same artifact/chunk provenance.

Acceptance criteria:

1. A layperson can answer "what document needs my attention next?"
2. Each docket document has a clear status and next action.
3. Complaint and response drafting can start from a selected docket item.

### New Workstream 2: Document Viewer, Annotation, And Labeling

Priority: P0

Goal: make document analysis visible, page-aware, and reusable.

Work:

- add a document viewer with page thumbnails, OCR/text layer status, parse quality, and source provenance,
- support span or page annotations with label taxonomy: party, date, deadline, allegation, denial, admission, exhibit, harm, remedy, contradiction, missing proof, legal authority, service issue, and follow-up,
- let users convert an annotation into a timeline event, claim fact, response issue, evidence link, or chatbot question,
- expose confidence and source type on every annotation,
- preserve annotation revisions and reviewer notes.

Acceptance criteria:

1. Users can select a document span and label why it matters.
2. Labels become durable fact/evidence records rather than browser-only notes.
3. Review and Draft can cite annotations by document, page, and span.

### New Workstream 3: Grounded Docket Chat

Priority: P0

Goal: make the chatbot a grounded document assistant, not a generic conversation box.

Work:

- add a chat panel scoped to the selected docket, selected document, selected page, or selected annotation,
- route text questions through `llm_router` and image/page questions through `multimodal_router`,
- require cited answers with document/page/span references whenever source material is available,
- show router state, fallback state, and "not enough evidence" answers plainly,
- let a chat answer become a saved annotation, issue label, timeline event, evidence task, or draft note,
- add suggested prompts for laypeople: "What is this document asking me to do?", "What deadline does this create?", "What allegations do I need to admit, deny, or explain?", "Which pages support my complaint?", and "What should I ask the court for?"

Acceptance criteria:

1. Chat answers cite docket documents and pages.
2. Users can save useful answers into the proof/drafting workflow.
3. Router fallback does not silently change the evidentiary confidence of an answer.

### New Workstream 4: Complaint And Response Drafting

Priority: P0

Goal: support both starting a complaint and responding to documents already in the docket.

Work:

- add a first decision: "I need to start a complaint" vs. "I need to respond to a document",
- for responses, bind the draft to a docket item and extract response obligations, deadlines, allegations, requested relief, and service requirements,
- provide answer/denial/admission and motion/objection-oriented drafting paths,
- keep release-gate checks tied to both legal sufficiency and procedural completeness,
- keep export blocked or warning-gated when required parties, captions, deadlines, signatures, service details, or cited source support are missing.

Acceptance criteria:

1. The user can draft a complaint or a response from the same workspace.
2. Response drafting shows the source docket document and the exact allegations or requests being answered.
3. Export guidance explains procedural blockers in plain language.

### New Workstream 5: Layperson Information Architecture

Priority: P1

Goal: reduce cognitive load without hiding power-user tools.

Work:

- add a mode distinction: Client, Advocate/Operator, and Advanced Tools,
- keep CLI, MCP, DuckDB, provider diagnostics, and optimizer controls in Advanced Tools,
- replace repeated cards with one next-action strip and one proof/readiness summary per lane,
- reserve space for sticky navigation so it does not cover page content,
- simplify copy by removing self-referential workflow language where a direct task label would work,
- make "why this matters legally" available inline for questions, evidence items, and annotations.

Acceptance criteria:

1. A first-time user can identify the next action within five seconds on each lane.
2. Advanced tools remain available without dominating the default task flow.
3. Mobile and narrow desktop screenshots have no sticky-nav overlap.

### Updated Implementation Order

1. Stabilize Playwright screenshot review and router fallback reporting.
2. Add the Docket lane and document-status model.
3. Add the page-aware document viewer with annotation and labeling primitives.
4. Add grounded docket chat with cited answers and save-to-workflow actions.
5. Rework Evidence and Review around a single "what proves this / what is thin / what next" model.
6. Split Draft into complaint-start and response-to-document flows.
7. Move advanced imports and MCP/CLI diagnostics into a secondary advanced-tools lane.

### Second Targeted Screenshot Pass: Docket, Document, Chat

Date: 2026-04-20

A narrower Playwright pass captured the current docket-adjacent surfaces:

- `artifacts/ui-audit-docket-pass/screenshots/workspace-evidence-current.png`
- `artifacts/ui-audit-docket-pass/screenshots/workspace-review-current.png`
- `artifacts/ui-audit-docket-pass/screenshots/workspace-packaged-docket-hidden-in-tools.png`
- `artifacts/ui-audit-docket-pass/screenshots/claim-review-document-intake.png`
- `artifacts/ui-audit-docket-pass/screenshots/document-builder-current.png`
- `artifacts/ui-audit-docket-pass/screenshots/chat-docket-context-current.png`

Those screenshots were sent through `MultimodalRouterBackend` with a tighter docket/document/chat prompt. The multimodal call and text fallback again timed out; the saved artifact is `artifacts/ui-audit-docket-pass/reviews/iteration-02-review.json` with `strategy: deterministic_fallback`. This confirms that the first implementation slice should include visual-audit reliability before using router critique as an automated gate.

The direct visual review from this second pass adds more specific product requirements:

1. **Docket is present but misplaced.** The only explicit packaged-docket UI appears inside `CLI + MCP` as "Packaged Docket Ops." It asks for a bundle manifest path and exposes revalidation/persistence controls. That is useful for an operator, but it is not the layperson docket view. The layperson needs "Documents in my case" first, not "Load packaged legal ops dashboard."
2. **Docket controls are blocked by sticky navigation overlap.** In the packaged-docket screenshot, the stage navigation bar overlays the card content. The layout must reserve space for sticky controls or use a compact action rail that does not cover forms.
3. **Document intake is buried below operator review scaffolding.** The `/claim-support-review` screenshot shows document intake after a long operator sidebar, empty metrics, follow-up controls, and "Review request failed: Not found." A layperson looking for a document would not know whether to load review, fill claim IDs, or upload first.
4. **Chat has a promising filing context but lacks source grounding.** The chat screenshot shows "Ready to answer questions with the selected filing context attached" and labels such as deadline, adverse action, and response needed. It still does not show the actual document page, selected span, citation target, or save buttons for "turn this answer into an annotation / deadline / response issue."
5. **The builder is complaint-first, not docket-response-first.** `/document` describes turning a complaint record into a formal complaint. It does not yet ask whether the user is starting a complaint or responding to a docket document, nor does it bind draft sections to a selected pleading, notice, motion, summons, or agency letter.
6. **Evidence intake and review are close to the right proof model but not a docket model.** They ask what claim element an item strengthens, which is good. They do not yet provide a docket table, document status, response deadline, annotation progress, or per-document unresolved questions.

### Refined UX Target For Layperson Docket Work

The default layperson flow should use this object model and language:

1. **Docket Item**: a document in the case, such as a complaint, summons, notice, exhibit, email, agency letter, court order, motion, or response.
2. **Document Status**: needs review, needs labeling, has deadline, needs response, ready to cite, low-quality OCR, duplicate, or archived.
3. **Annotation**: a page or text span labeled as allegation, admission, denial, deadline, party, date, harm, remedy, exhibit, contradiction, authority, service issue, or follow-up.
4. **Question**: a grounded question asked about one docket item, page, selected span, or group of documents.
5. **Draft Task**: start complaint, answer complaint, respond to motion, object, request records, prepare declaration, or assemble exhibit packet.

The UI should avoid making laypeople work with manifest paths, claim element IDs, execution lanes, queue priority, provider diagnostics, or MCP examples unless they explicitly open Advanced Tools.

### Refined Implementation Slices Before Coding

Slice A: Make the screenshot/router review path dependable.

- Add a small deterministic screenshot-capture target for only Docket, Document Viewer, Chat, Review, and Draft.
- Make router fallback visible in the UX Audit panel and in the generated review artifact.
- Treat router timeout as a warning, not a blocker to saving visual evidence.

Slice B: Promote a Docket tab into the main workspace.

- Add a visible Docket lane between Intake and Evidence/Review.
- Seed it from uploaded documents, review documents, imported local evidence, Gmail documents, and packaged docket manifests.
- Show each docket item with title, type, date, deadline, source, status, labels, annotation count, unanswered questions, and primary next action.

Slice C: Add the document viewer and annotation shell.

- Display the selected document next to its metadata and labels.
- Support page/span annotation records even before advanced PDF rendering is complete.
- Make "Add label," "Ask about this page," "Attach to claim/response," and "Create deadline" the primary actions.

Slice D: Make chat document-scoped.

- Keep the current selected-filing context, but add visible source cards and citation targets.
- Add save actions: save as annotation, save as deadline, save as timeline event, save as response issue, save as evidence task, or save as draft note.
- Require `llm_router` / `multimodal_router` status and fallback messages beside each answer.

Slice E: Split drafting by user intent.

- First ask: "Start a complaint" or "Respond to a document."
- If responding, force selection of a docket item and show the exact document being answered.
- Map extracted allegations, deadlines, requests, defenses, and service requirements into the draft checklist.

### Third Router Check: Single-Image Docket Review

Date: 2026-04-20

A final reduced payload sent one cropped docket screenshot to the router:

- `artifacts/ui-audit-single-docket/screenshots/single-docket-tools.png`

The artifact was written to:

- `artifacts/ui-audit-single-docket/reviews/iteration-03-review.json`

Even this one-image request timed out through both `MultimodalRouterBackend` and the `llm_router` fallback, producing another deterministic fallback. The planning conclusion is now firm: automated visual critique should be a supported capability, but it should not be the first implementation dependency for the Docket UX. The first implementation dependency is a reliable audit harness that saves screenshots, records router status, and lets the team continue with human/direct visual review when the router is unavailable.

### Existing Docket/Router Hooks To Reuse

The next implementation should reuse existing SDK and MCP seams instead of introducing a parallel docket backend. Current browser SDK hooks already include:

- `complaint.get_packaged_docket_operator_dashboard`
- `complaint.load_packaged_docket_operator_dashboard_report`
- `complaint.execute_packaged_docket_proof_revalidation_queue`
- `complaint.persist_packaged_docket_proof_revalidation_queue`
- `complaint.view_docket_dataset`

Those hooks are currently presented as advanced packaged-docket operations. The layperson Docket lane should sit above them and translate their outputs into plain objects:

- docket item,
- document status,
- label set,
- annotation count,
- deadline,
- response needed,
- next action,
- source/citation reference.

The advanced hooks should remain visible in Advanced Tools for operators who need manifests, revalidation queues, refreshed packets, CAR artifacts, and persisted bundles.

### Proposed First-Screen Docket Layout

The Docket lane should open with a compact triage board:

1. **Needs Attention**: documents with deadlines, required responses, missing labels, or low-quality OCR.
2. **Ready To Use**: documents already labeled and citeable.
3. **Questions To Ask**: unanswered document questions queued for chat or reviewer follow-up.
4. **Recently Added**: new uploads, Gmail imports, local evidence imports, and packaged docket items.

Each row should show:

- document title,
- document type,
- source,
- date or deadline,
- labels,
- annotation count,
- router status if analyzed,
- primary action: Review, Label, Ask, Respond, Attach, or Archive.

This is the layperson surface. Manifest paths, queue priority, execution top-k, report format, CAR output, and persistence controls belong below an "Advanced docket operations" disclosure.

### Proposed Document Viewer Shell

The first implementation does not need a perfect PDF editor. It does need a stable shell that can evolve:

1. left rail: docket items and pages,
2. center: page/text preview with selectable spans,
3. right rail: labels, annotations, linked claim/response issues, and chat answers,
4. bottom action bar: Add Label, Ask About Selection, Create Deadline, Attach To Claim, Add To Response Draft.

The annotation schema should be simple at first:

- `annotation_id`,
- `docket_item_id`,
- `page_ref` or `span_ref`,
- `label`,
- `plain_language_note`,
- `source_text`,
- `confidence`,
- `created_from`: manual, `llm_router`, or `multimodal_router`,
- `saved_as`: fact, deadline, issue, evidence task, or draft note.

### Proposed Chat Contract

Document chat should always show its scope before the user sends a question:

- asking about whole docket,
- selected document,
- selected page,
- selected span,
- selected annotation,
- selected response task.

Every answer should include:

- router path: `llm_router`, `multimodal_router`, or fallback,
- citation target when source text/image is available,
- confidence or "not enough source support",
- save actions: Save Annotation, Save Deadline, Save Issue, Save Evidence Task, Save Draft Note.

The chat should not feel like a separate app. It should be a side panel or companion route that keeps the selected docket item visible.

### Implementation Readiness Matrix

The screenshot pass makes the next coding slice smaller than it first looked. The backend already has docket contracts that can power a layperson Docket lane; the work is mostly surfacing them with safer information architecture and adding a few browser-facing hooks.

Existing service contracts to reuse:

- `ComplaintWorkspaceService.view_docket_dataset`
- `ComplaintWorkspaceService.search_docket_dataset`
- `ComplaintWorkspaceService.get_docket_dataset_metadata`
- `ComplaintWorkspaceService.get_docket_dataset_graph`
- packaged docket operator helpers:
  - `get_packaged_docket_operator_dashboard`,
  - `load_packaged_docket_operator_dashboard_report`,
  - `execute_packaged_docket_proof_revalidation_queue`,
  - `persist_packaged_docket_proof_revalidation_queue`.

Existing API and wrapper coverage:

- `applications/complaint_workspace_api.py` already exposes docket dataset view, search, metadata, and graph routes.
- `complaint_generator/workspace.py` already wraps docket view, search, metadata, and graph operations.
- `applications/complaint_workspace.py` already registers MCP tool definitions for `complaint.view_docket_dataset`, `complaint.search_docket_dataset`, `complaint.get_docket_dataset_metadata`, and `complaint.get_docket_dataset_graph`.

Browser SDK gap:

- `static/complaint_mcp_sdk.js` currently treats packaged docket operations and `complaint.view_docket_dataset` as docket sync events.
- It exposes packaged docket helper methods.
- It should add first-class browser methods for:
  - `searchDocketDataset(inputPath, query, options)`,
  - `getDocketDatasetMetadata(inputPath, options)`,
  - `getDocketDatasetGraph(inputPath, options)`,
  - and, if absent from the module build, matching methods in `static/complaint_mcp_sdk.mjs`.
- It should include search, metadata, and graph tools in the docket event set so the Docket lane can refresh consistently after MCP calls.

Tests to lean on before UI work:

- `tests/test_docket_workspace_surface.py` already checks MCP tool registration, service metadata, graph projection, search, PDF ingest hashing, workspace dataset graph behavior, and CLI docket graph behavior.
- `tests/test_ui_review_multimodal.py` already covers multimodal review behavior, router fallbacks, and provider-chain reporting for a smaller UI review surface.
- `tests/test_ui_ux_workflow.py` and `playwright/tests/complaint-flow.spec.js` cover the broader screenshot workflow, but the latest run showed two stale assumptions that should be fixed before treating the full audit as a gate:
  - the hidden `#chat-open-profile` link should not be required as visible in the unified workspace flow,
  - provider-order expectations should reflect the configured/current router order rather than a hard-coded old order.

### First Coding Milestone

Goal: create a first-class Docket lane that a layperson can use without touching manifest paths, CLI controls, queue settings, or operator-only persistence controls.

Files likely touched:

- `templates/workspace.html` for the Docket tab, document list, selected-document panel, document actions, and advanced disclosure.
- `static/complaint_app_shell.js` if the workspace shell behavior already belongs there; otherwise keep the first slice local to `templates/workspace.html` and extract only after the flow stabilizes.
- `static/complaint_mcp_sdk.js` and `static/complaint_mcp_sdk.mjs` for docket search, metadata, graph, and sync-event method coverage.
- `playwright/tests/complaint-flow.spec.js` or a new focused docket workspace spec for screenshot capture and overlap checks.
- `tests/test_docket_workspace_surface.py` only if SDK-facing or route-facing behavior needs a small assertion update.

Suggested data shape for the first visible docket item:

- `docket_item_id`,
- `title`,
- `document_type`,
- `source`,
- `date_filed`,
- `deadline`,
- `status`,
- `labels`,
- `annotation_count`,
- `question_count`,
- `router_status`,
- `primary_action`,
- `source_ref`.

Initial visible states:

- **Needs Review**: newly imported or unanalyzed documents.
- **Important**: documents tied to claims, defenses, deadlines, jurisdiction, service, exhaustion, or retaliation facts.
- **Deadline**: filings, orders, notices, and response due dates.
- **Ready For Draft**: items that can be attached to complaint or response drafting.
- **Needs Source Support**: AI output exists but lacks a citation target or confidence threshold.

First implementation non-goals:

- full PDF annotation editing,
- full-page OCR correction,
- replacing the existing packaged docket pipeline,
- writing new legal strategy logic,
- changing backend docket parsing,
- making chat provide uncited legal advice,
- completing every response-drafting workflow.

### Acceptance Checks For Milestone 1

Playwright/UI:

- Docket appears as a primary workspace tab or first-screen lane, not buried in CLI/MCP tooling.
- A layperson can see document title, type, source, date/deadline, labels, annotation count, router status, and one obvious next action.
- Sticky navigation and bottom actions do not cover content on desktop or mobile screenshots.
- "Ask" opens chat with an explicit `chat_context` for the selected docket item.
- "Respond" or "Use In Draft" opens the Draft lane with the selected docket item referenced.
- Operator controls are moved under an "Advanced docket operations" disclosure.
- Empty states explain the next action without exposing manifest path mechanics as the first required input.

Router/review artifact:

- Screenshot review artifacts should record whether the result came from `multimodal_router`, text fallback, or deterministic fallback.
- A deterministic fallback should still produce actionable findings and should not be reported as a silent pass.
- The UI review workflow should tolerate one screenshot at a time as well as the full workspace bundle, because the current router path timed out on the six-image and one-image docket passes.

Service/SDK:

- Browser SDK exposes docket dataset search, metadata, graph, and view calls.
- Docket search, metadata, and graph calls publish docket sync events consistently.
- Existing service tests continue to pass without changing docket dataset semantics.

### Fourth Screenshot Review: Docket-To-Chat-To-Draft Journey

Date: 2026-04-20

After the first Docket lane implementation pass, Playwright captured a compact layperson journey:

- `artifacts/ui-audit-docket-plan-review-20260420/screenshots/01-workspace-docket.png`
- `artifacts/ui-audit-docket-plan-review-20260420/screenshots/02-document-chat-context.png`
- `artifacts/ui-audit-docket-plan-review-20260420/screenshots/03-review-support.png`
- `artifacts/ui-audit-docket-plan-review-20260420/screenshots/04-draft-response-context.png`

The four-screenshot bundle was sent to the multimodal UI review workflow, but the bundle review exceeded the useful wait budget and had to be stopped. This confirms the earlier reliability finding: the screenshot review workflow must support bounded per-surface review, visible heartbeat/status, and partial artifacts so a hung bundle does not block planning.

A single-screen review of the document chat screenshot succeeded:

- artifact: `artifacts/ui-audit-docket-plan-review-20260420/reviews/iteration-02-chat-single-review.json`
- strategy: `multimodal_router`
- provider: `codex_cli`
- model: `gpt-5.3-codex`

Router summary:

> The page communicates a document-scoped complaint chat, but key trust and workflow signals are weak for a layperson: source grounding is not inspectable, scope is easy to miss, stage/router state is ambiguous, and there is no clear save-to-annotation action.

Human review and router review now agree on the next UX risks:

1. **Docket is improved but still operator-leaning.** It shows document status, router/indexing status, source, labels, and the safer "Review Before Draft" action. It still needs a stronger "what this document affects" summary, explicit deadline extraction, and a visible annotation/label editor instead of a placeholder Add Label action.
2. **Document chat has scope but not inspectable grounding.** The chat shows selected filing context and labels, but does not show the document text/page beside the answer, citation anchors, page/span targets, or confidence/source-support state per answer.
3. **Chat lacks save actions.** The next chat slice must add Save Annotation, Save Deadline, Save Issue, Save Evidence Task, and Save Draft Note actions on assistant answers, with a confirmation showing where the saved item went.
4. **Router path is not visible enough in chat.** The chat surface should show whether an answer used `llm_router`, `multimodal_router`, text fallback, or deterministic fallback, plus whether the answer had enough source support.
5. **Raw technical IDs are too prominent.** Long DID/session identifiers should move into details/diagnostics. The first visible status should say "file attached," "answering from selected filing," "last synced," and "source support ready/not ready."
6. **Review is still a long proof report.** It contains useful proof-readiness details, but the layperson needs a shorter top decision: gather more proof, ask about a document, fix intake/caption, or move to Draft with blockers visible.
7. **Draft is still too dense.** Complaint drafting, response drafting, release-gate diagnostics, export controls, and operator controls compete on one page. Draft needs an intent selector and a simpler release-gate explanation before exposing full diagnostics.
8. **Global navigation is still noisy.** Chat and workspace surfaces expose many routes at once. Advanced routes such as Trace, SDK, Dashboards, and operator tools should collapse behind an advanced menu in the layperson path.

### Revised Next Implementation Slices

Slice 2A: Document chat grounding.

- Add a persistent scope banner above the chat composer: "Answering from selected filing only," file name, labels, and Change Scope.
- Add a document/source side panel for the selected filing with citation jump targets.
- Add per-answer citation chips such as document, page, paragraph, or selected span.
- Add per-answer router metadata: `llm_router`, `multimodal_router`, fallback, confidence, and "not enough source support" state.
- Add save actions for Annotation, Deadline, Issue, Evidence Task, and Draft Note.

Slice 2B: Docket annotations and labels.

- Replace Add Label placeholder with a real label editor.
- Persist a lightweight annotation object with `docket_item_id`, label, note, source text/span, confidence, router path, and saved-as type.
- Surface annotation count and the last saved annotation in the Docket list.
- Extract or manually set deadlines from filings/orders and show them as first-class Docket chips.

Slice 2C: Review compression.

- Add a top "Decision Now" strip: Gather proof, Ask about document, Fix intake/caption, or Draft with blockers.
- De-duplicate repeated proof cards below the fold.
- Link each proof gap to a Docket item, chat question, or evidence upload action.

Slice 2D: Draft intent split.

- Add a first control for "I am drafting a complaint" vs "I am responding to a complaint/order/motion."
- If responding, require a selected Docket item and show the exact document being answered.
- Move full release-gate diagnostics behind details; keep the layperson explanation and primary blocker visible.

Slice 2E: Router review reliability.

- Run multimodal screenshot review one surface at a time by default.
- Save partial artifacts when one page review succeeds and another hangs.
- Show heartbeat/status in the UI review panel: pending, router, text fallback, deterministic fallback, timed out.
- Treat bundle timeout as a review finding, not a hard stop.

### Implementation Gate Before Slice 2

Before starting the next code slice, use this gate to keep the implementation narrow and testable.

Primary user story:

> A layperson selects one docket document, asks a question about it, sees exactly what source the answer relies on, saves the answer as a label/annotation/deadline/issue/draft note, and sees that saved item reflected back in Docket, Review, and Draft.

Required data contract:

- `docket_item_id`
- `document_title`
- `document_type`
- `source_ref`
- `page_ref` or `span_ref`
- `selected_text`
- `label`
- `plain_language_note`
- `saved_as`: annotation, deadline, issue, evidence_task, or draft_note
- `router_path`: `llm_router`, `multimodal_router`, text fallback, or deterministic fallback
- `retrieval_method`: BM25, vector, graph, full_text, citation_resolver, manual, or unavailable
- `confidence`
- `source_support`: supported, partial, unsupported, or not_indexed
- `created_at`

Minimum UI contract:

- Docket document list shows annotation count, deadline count, last saved label, and source-support state.
- Selected document panel shows a source preview and primary action.
- Chat composer shows persistent scope before send.
- Chat answer card shows citations/source state before save actions.
- Save action creates a visible item without leaving the current task.
- Review links proof gaps to saved docket annotations where possible.
- Draft shows whether the selected saved item is being used for a complaint or a response.

Minimum Playwright contract:

- Select document from Docket.
- Add a label.
- Ask about the selected document.
- Assert `chat_context` is present and visible.
- Render an answer card with router/source metadata, even when using a deterministic mocked response.
- Save the answer as an annotation or deadline.
- Return to Docket and assert annotation/deadline count changed.
- Open Review and Draft and assert the saved item is referenced.

Non-goals for Slice 2:

- Full PDF editing.
- Full multi-document RAG synthesis.
- Perfect OCR repair.
- Complete response pleading generation.
- Moving operator packaging, CAR, or provenance controls into the layperson path.

### Fifth Screenshot Review: April 22 Docket And Chat Recheck

Date: 2026-04-22

A fresh Playwright pass captured the current Docket-to-chat review path with a housing/eviction-response scenario:

- `artifacts/ui-audit-docket-plan-review-20260422/screenshots/01-docket-current.png`
- `artifacts/ui-audit-docket-plan-review-20260422/screenshots/02-document-chat-current.png`
- `artifacts/ui-audit-docket-plan-review-20260422/screenshots/03-review-current.png`
- `artifacts/ui-audit-docket-plan-review-20260422/screenshots/04-draft-current.png`
- `artifacts/ui-audit-docket-plan-review-20260422/screenshots/05-ux-review-current.png`

Two bounded single-surface multimodal reviews completed successfully:

- `artifacts/ui-audit-docket-plan-review-20260422/reviews/iteration-03-docket-single-review.json`
  - strategy: `multimodal_router`
  - provider: `codex_cli`
  - model: `gpt-5.3-codex`
  - issues: 8
- `artifacts/ui-audit-docket-plan-review-20260422/reviews/iteration-03-chat-single-review.json`
  - strategy: `multimodal_router`
  - provider: `codex_cli`
  - model: `gpt-5.3-codex`
  - issues: 6

Docket router summary:

> The Docket Command Center page shows core case-routing concepts, but the current presentation is hard for a layperson to act on: status chips are repetitive and ambiguous, action buttons do not clearly indicate prerequisites, and key workflow states (deadlines, enrichment, annotations, and next action readiness) are fragmented across cards.

Chat router summary:

> The page shows a document-scoped complaint chat with useful structure, but key trust and workflow signals are weak or missing: source grounding is vague, confidence is not exposed, citation targets are not actionable, and save-to-workflow actions are unclear.

The April 22 review refines Slice 2 into five concrete UI repairs:

1. **Collapse low-level enrichment noise.** OCR, text extraction, BM25, vectors, knowledge graph, citation extraction, and formal logic should roll up into one plain-language readiness summary such as "Not indexed yet," "Text ready," or "Ready for cited answers." Technical statuses can remain in details.
2. **Pin urgency and deadlines.** The selected document panel should place "Urgency & Deadlines" above enrichment status, with due date, source sentence, confidence, and "Create/Confirm Deadline" action.
3. **Use one readiness-based primary CTA.** The Docket action panel should pick one primary action from the document state: Review Before Draft, Confirm Deadline, Add Label, Ask About Document, or Use In Draft. Other actions stay secondary.
4. **Make chat source grounding inspectable.** Each answer needs citation chips that jump to a document/page/paragraph/span target, plus visible retrieval mode and source-support confidence.
5. **Separate ask from save.** Chat should not blur "ask a question" with "commit this to the workflow." Use explicit Ask Question and Save Answer actions, then show a confirmation naming the destination: Annotation, Deadline, Issue, Evidence Task, or Draft Note.

Updated Slice 2 acceptance checks:

- Docket shows a single readiness summary for each document, with technical enrichment details collapsed.
- Selected document shows a pinned urgency/deadline panel before metadata.
- Only one Docket action is visually primary at a time.
- Chat shows a persistent scope badge with selected document name, date/source when known, retrieval mode, and Change Scope.
- Chat answer cards show citation chips, router path, confidence, and source-support state.
- Ask Question and Save Answer are separate actions.
- Saving an answer updates Docket annotation/deadline counts and creates a visible Review/Draft reference.
- Playwright captures and asserts Docket, document chat, Review, Draft, and UX review artifacts one surface at a time.

### Sixth Screenshot Review: April 25 Desktop And Mobile Recheck

Date: 2026-04-25

A fresh Playwright pass captured the current Docket, document chat, Review, Draft, UX Review, and mobile Docket surfaces:

- `artifacts/ui-audit-docket-plan-review-20260425/screenshots/01-docket-desktop.png`
- `artifacts/ui-audit-docket-plan-review-20260425/screenshots/02-document-chat-desktop.png`
- `artifacts/ui-audit-docket-plan-review-20260425/screenshots/03-review-desktop.png`
- `artifacts/ui-audit-docket-plan-review-20260425/screenshots/04-draft-desktop.png`
- `artifacts/ui-audit-docket-plan-review-20260425/screenshots/05-ux-review-desktop.png`
- `artifacts/ui-audit-docket-plan-review-20260425/screenshots/06-docket-mobile.png`

Three bounded single-surface multimodal reviews completed successfully:

- `artifacts/ui-audit-docket-plan-review-20260425/reviews/iteration-04-docket-desktop-review.json`
  - strategy: `multimodal_router`
  - provider: `codex_cli`
  - model: `gpt-5.3-codex`
  - issues: 7
- `artifacts/ui-audit-docket-plan-review-20260425/reviews/iteration-04-chat-desktop-review.json`
  - strategy: `multimodal_router`
  - provider: `codex_cli`
  - model: `gpt-5.3-codex`
  - issues: 6
- `artifacts/ui-audit-docket-plan-review-20260425/reviews/iteration-04-docket-mobile-review.json`
  - strategy: `multimodal_router`
  - provider: `codex_cli`
  - model: `gpt-5.3-codex`
  - issues: 7

The initial three-surface batch review prepared image diagnostics but exited before producing review summaries. The bounded one-surface review path completed and should remain the default until bundle execution has reliable timeouts and partial-result reporting.

The April 25 review confirms the April 22 direction and adds a mobile-specific warning: the Docket lane is usable on desktop but becomes a long stack of repeated status cards, chip clusters, and competing CTAs on narrow screens.

Refined findings:

1. **Readiness hierarchy is still inverted.** OCR, BM25, vectors, knowledge graph, citations, and formal logic are as prominent as legal readiness signals. Enrichment status should become one plain-language readiness state with details collapsed.
2. **Ready For Draft conflicts with not reviewed/not checked.** The page currently shows "Ready For Draft" while the selected document also says router not reviewed and technical checks not complete. Replace this with "Conditionally ready" or "Needs review before draft" until required criteria are satisfied.
3. **Primary action is still ambiguous.** Docket presents Ask, Use In Draft Anyway, Review Before Draft, and Add Label in the same action group. The UI should choose one canonical CTA from document state and demote the rest.
4. **Deadlines are still too weak.** Deadline visibility is a count, not a due-date decision. Selected documents need a pinned deadline/urgency block with due date, source sentence, confidence, and confirm/create action.
5. **Label taxonomy is mixed.** Legal labels, workflow state, and technical markers currently appear together. Separate them into Legal Relevance, Workflow State, and Technical Processing groups.
6. **Chat still lacks answer-level grounding.** Assistant outputs need per-claim citation chips, selected-document scope at answer time, router path, confidence, and save-to-workflow actions.
7. **Mobile needs its own compact contract.** On mobile, show at most two or three high-priority chips, one sticky primary CTA, one canonical document card, and collapse technical details behind "More status."

Mobile acceptance checks for Slice 2:

- First mobile viewport shows selected document title, readiness state, and one primary next action.
- Search/load controls are collapsed after a document is selected.
- Repeated document cards are deduplicated by `docket_item_id` or source thread.
- Mobile Docket shows at most three visible status chips before a disclosure.
- Technical terms such as manifest, vectors, BM25, and formal logic have plain-language aliases or stay inside details.
- Primary CTA remains reachable after scrolling through selected-document details.
- Playwright captures mobile Docket before and after saving an annotation/deadline.

Implementation gate before Slice 2:

- Desktop and mobile Docket both show one primary next action within the first screen or first short scroll.
- A document cannot display "Ready For Draft" while required review, deadline, source, or router checks are missing; use "Conditionally ready" or "Needs review before draft" with unmet requirements listed.
- Technical enrichment status is collapsed by default into one plain-language readiness state.
- The nearest known deadline date, source, and urgency state are visible near the primary CTA.
- Mobile Docket shows one canonical selected-document card, with repeated document/status blocks deduplicated.
- Document chat answer cards include citation chips, selected scope, router path, confidence/source-support state, and explicit save-to-workflow actions.
- Playwright assertions cover desktop Docket, mobile Docket, document chat, and a saved annotation/deadline round trip before implementation is considered ready to merge.

Cross-surface safety gate before Slice 2:

- The first layperson screen is a case/workflow hub, not a raw internal route index. It should expose a small set of goal-based entries: start/resume complaint, respond to a docket document, review documents, and ask the case assistant.
- The layperson view hides raw DID strings, MCP tool counts, backend IDs, gate versions, provider names, and queue internals unless the user opens Operations or Diagnostics.
- First draft generation requires visible legal-safety framing: the tool organizes facts and drafts documents, but does not provide legal advice.
- Internal gate states such as `NEEDS_CORROBORATION`, `workspace-gate-v1`, and `release gate is not passing yet` are translated into concrete proof tasks with examples of acceptable evidence.
- Disabled actions explain why they are locked and provide a direct recovery path to Intake, Evidence, Docket, Review, or Draft.
- Readiness scores such as `10/100` are replaced or paired with criteria chips tied to missing facts, documents, deadlines, citations, or source support.
- Evidence and docket records expose provenance before draft insertion: source, date, who provided it, confidence, claim-element link, and page/span when available.

April 25 refresh review note:

- `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260425-refresh/router-review.json`
- Reviewed pages: dashboard hub, intake chat, workspace Docket, claim-support Review, and document builder.
- strategy: `page_reviews` with per-page `multimodal_router`
- provider: `codex_cli`
- verdict: `warning`

The refresh confirms that the plan should not begin by adding more panels to already dense screens. The first implementation pass should create a clearer goal-based shell, then place Docket, annotation, Review, Draft, and chatbot work inside that shell with one visible next action per surface.

Immediate implementation sequence:

1. Align `/dashboards` between `applications/dashboard_ui.py` and `playwright/server.js` so both the real app and screenshot fixture show the same layperson-first goal hub.
2. Hide technical identity/router/gate internals from standard mode in `templates/index.html` and `static/complaint_app_shell.js`; keep them available only in Operations/Diagnostics.
3. Add legal-safety framing, proof-task translation, disabled-action reasons, and criteria chips before changing Docket behavior.
4. Implement one trustworthy selected-document Docket flow in `templates/workspace.html`: canonical card, deadline/urgency panel, grouped labels, annotations, and one primary CTA.
5. Ground `templates/chat.html` and `static/chat.js` around selected-document scope, citations, confidence/source-support state, and save-to-workflow actions.
6. Add Playwright checks for dashboard hub, desktop Docket, mobile Docket, document chat, Review/Draft handoff, and multimodal review artifact completion.

Slice 1 stop line:

- Do not begin Docket document implementation until the real FastAPI `/dashboards` route and the Playwright fixture `/dashboards` route expose equivalent layperson-first primary cards.
- Preserve legacy dashboard shell/raw route coverage while hiding those route catalogs from the default layperson first screen.
- Run the focused dashboard/template tests plus `playwright/tests/navigation.spec.js` and `playwright/tests/complaint-flow.spec.js`.
- Capture fresh desktop and mobile dashboard hub screenshots for multimodal review before starting the selected-document Docket work.

### Seventh Screenshot Review: April 26 Post-Slice-1 Hub And Docket Recheck

Date: 2026-04-26

After the Slice 1 hub alignment pass, Playwright captured a fresh layperson scenario for a user reviewing a school-district due-process docket, response deadline, accommodation packet, document chat, claim-support Review, and document Builder.

Artifacts:

- Screenshots: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426/screenshots/`
- Screenshot metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426/screenshot-metadata.json`
- Hub/chat/review/builder router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426/router-review.json`
- Docket-only router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426/router-review-docket-only.json`
- Diagnostics:
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426/router-review-codex-diagnostics/pages/`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426/router-review-docket-only-codex-diagnostics/pages/`

The first review used `page_reviews` with per-page `multimodal_router`, provider `codex_cli`, model `gpt-5.3-codex`, and selected dashboard hub desktop/mobile, document chat desktop, claim-support Review desktop, and document Builder desktop. It skipped Docket desktop/mobile because the page limit selected five other screenshots first. The second Docket-only review used the same router/provider/model path and selected both Docket desktop and Docket mobile with no skipped screenshots.

Refined findings from the April 26 reviews:

1. **The hub is improved but not ready to carry deeper Docket work.** The router found ambiguous primary next actions, locked stages without clear unlock criteria, small/low-contrast body copy, and too much technical tooling near layperson decisions.
2. **Mobile hub still needs a true single-column contract.** The mobile screenshot still shows cramped parallel columns, weak hierarchy, and controls that look informational instead of actionable.
3. **Document chat, Review, and Builder share the same layout weakness.** Large empty regions, narrow active work areas, tiny navigation, and fragmented panels make source grounding and next actions hard to scan.
4. **Desktop Docket does not yet expose the core layperson task.** The Docket page communicates a workspace concept, but selected-document review, annotation/labeling, deadline extraction, and document-grounded Q&A are not visibly prominent.
5. **Mobile Docket is now a hard blocker.** The mobile screenshot shows a severe responsive-layout failure: meaningful content is confined to a narrow top-left column while most of the viewport is empty. The router judged document selection, annotation, deadline extraction, and document-grounded Q&A unusable in that state.

Revised gate before selected-document Docket implementation:

- Do not begin selected-document Docket behavior until the mobile Docket shell renders as a full-width, single-column layperson workflow with no narrow-column/empty-viewport failure.
- Mobile Docket first paint must show a current Docket task, a selected-document or document-list entry point, and visible Ask, Label, Annotate, and Deadline actions in plain language.
- Desktop Docket must rebalance into a purposeful document workflow: document list/context, selected-document viewer/source panel, and assistant/actions. Technical function names stay behind Operations/Diagnostics.
- Playwright must include explicit mobile Docket assertions for full-width layout, visible selected-document controls, and no critical controls stranded outside the first screen or first short scroll.
- The screenshot review workflow must run a Docket-only router pass whenever the multi-page selector skips Docket screenshots.

April 26 mobile Docket shell repair note:

- Implemented a first mobile shell repair in `templates/workspace.html` and `playwright/tests/navigation.spec.js`.
- Added a current-task module, mobile Ask/Label/Annotate/Deadline action strip, disabled empty-state actions, tighter mobile padding, no-horizontal-overflow assertions, and a static empty selected-document action area.
- Final screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshots/04-workspace-docket-mobile-final-empty-state.png`
- Simplified locked-state screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshots/06-workspace-docket-mobile-locked-empty-state.png`
- Loaded-document screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshots/09-workspace-docket-mobile-loaded-document-final.png`
- The loaded-document repair hides the mobile load form after a document exists, removes the duplicate lower action bar, makes Ask visually primary, hides duplicate selected-document chips, and caps the selected preview height.
- Source-summary screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshots/10-workspace-docket-mobile-source-summary-final.png`
- Source-summary metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshot-metadata-source-summary-final.json`
- Source-summary router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/router-review-mobile-source-summary-final.json`
- The source-summary repair replaces the mobile selected-document status wall with one source card and collapsed technical detail disclosure.
- Router follow-up still flags the Docket surface as dense and desktop-influenced, even though the Playwright metadata confirms no horizontal overflow, the mobile load form and lower duplicate action bar are hidden in the loaded-document state, and the technical status is collapsed. This repair reduces the severe layout failure but does not clear the selected-document implementation gate by itself. The next gate should move Docket into a dedicated mobile-first route or hide the surrounding desktop stage/header chrome from mobile captures.

Focused mobile Docket gate review:

- Gate review artifact: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/router-review-mobile-source-summary-gate-decision.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`
- The router's actionable finding is that selected-document behavior should wait until the mobile shell makes the active document unmistakable near the actions. The next slice should add a persistent selected-document rail, keep Ask as the one primary CTA, move Label/Annotate into secondary actions, make Deadline lower-risk with confirmation, and keep router/OCR/index internals collapsed for laypersons.
- The router suggested TypeScript component paths, but those are framework-generic suggestions. In this application, the relevant implementation files remain `templates/workspace.html`, the browser MCP SDK path, `tests/test_workspace_template_contract.py`, and `playwright/tests/navigation.spec.js`.

Selected-document rail follow-up:

- Final screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-selected-rail/screenshots/03-workspace-docket-mobile-selected-rail-final.png`
- Final metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-selected-rail/screenshot-metadata-selected-rail-final.json`
- Final router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-selected-rail/router-review-mobile-selected-rail-final.json`
- Implemented the mobile selected-document rail, compact review/draft/deadline badges, document-specific chat scope chip, ordered Ask/Label/Annotate/Deadline action labels, hidden duplicate mobile selected title, and source-summary title cleanup.
- Playwright confirms no horizontal overflow, rail-before-actions ordering, scoped action text, hidden duplicate selected title, and compact rail/source-summary heights.
- The final router review still does not clear the selected-document behavior gate. It flags the remaining mobile architecture risk: the Docket page should become a single-active mobile surface, with either the document list or selected-document workbench shown at one time, and legal-critical status/deadline fields must wrap instead of being clipped.

Single-active mobile surface follow-up:

- Screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-single-surface/screenshots/02-workspace-docket-mobile-single-active-final.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-single-surface/screenshot-metadata-single-active-final.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-single-surface/router-review-mobile-single-active-final.json`
- Implemented a mobile-only `Back to Documents (n)` / `Viewing Selected` switch. Empty Docket shows only the document list, while loaded Docket opens the selected-document workbench and hides the document list. Selected mode also hides broad stage guidance and allows legal-critical source-summary status text to wrap.
- Playwright confirms the single-active selected surface: document list hidden, selected workbench visible, stage banner hidden, no horizontal overflow, explicit switch state, selected rail before actions.
- The router now acknowledges the intended single-active selected-document surface, but still holds the persistent selected-document behavior gate. The remaining prerequisite is action-state clarity: Label, Annotate, and Deadline need pending/done/blocked state and helper text before becoming real write actions.

Mobile action-state follow-up:

- Screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-action-state/screenshots/02-workspace-docket-mobile-action-state-final.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-action-state/screenshot-metadata-action-state-final.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-action-state/router-review-mobile-action-state-final.json`
- Implemented explicit mobile action-state rows for Ask, Label, Annotate, and Deadline. The states now read as high-contrast chips: `Next`, `Needs review`, `Pending`, and `Blocked`.
- Deadline is disabled when no deadline/response date exists and now points via `aria-describedby` to its unblock helper: `enable after a response date is captured in Annotation`.
- The router still holds the persistent-write gate. It now frames the next prerequisite as a canonical mobile stepper: one current step expanded, future steps secondary/collapsed, then implement the first real selected-document write action behind that stepper.

Mobile canonical stepper follow-up:

- Screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-stepper/screenshots/02-workspace-docket-mobile-stepper-final.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-stepper/screenshot-metadata-stepper-final.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-stepper/router-review-mobile-stepper-final.json`
- Implemented explicit mobile step cards with Ask as the single current step (`aria-current="step"`), future steps as secondary/blocked, and duplicate selected-mode framing hidden.
- The router still holds the persistent-write gate. The next prerequisite is now narrower: normalize the step labels to a stricter vocabulary such as `Active`, `Ready`, `Waiting`, and `Blocked`, then make the current step visually dominant enough to become the first real write gateway.

Mobile stepper status and microcopy follow-up:

- Screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-stepper-status/screenshots/04-workspace-docket-mobile-stepper-status-microcopy-final.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-stepper-status/screenshot-metadata-stepper-status-microcopy-final.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-stepper-status/router-review-mobile-stepper-status-microcopy-final.json`
- Implemented the stricter status vocabulary (`Active`, `Ready`, `Waiting`, `Blocked`), shortened the Ask CTA to `Ask About Document`, disabled the selected-context control in selected mode, and added `Next:`, `Pending:`, and `Blocked by:` helper prefixes.
- Playwright confirms the selected-document mobile state remains scoped, actionable, and free of horizontal overflow.
- The router still holds the persistent-write gate. The next prerequisite is not another backend contract change; it is clearer layperson presentation: render selected context as a read-only `Working on: ...` banner, keep `Back to Documents` as the only header action, move document count to static metadata, translate internal status enums into action-language (`Do this now`, `Available next`, `Waiting on prior step`, `Cannot continue yet`), and rewrite blocked Deadline copy as the exact corrective action.

Mobile layperson stepper follow-up:

- Screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-layperson-stepper/screenshots/03-workspace-docket-mobile-layperson-stepper-polished.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-layperson-stepper/screenshot-metadata-layperson-stepper-polished.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-layperson-stepper/router-review-mobile-layperson-stepper-polished.json`
- Implemented the layperson presentation pass: one visible header action (`Back to Documents`), static `Working on: ...` context, plain-language step states, disabled Step 2/3/4 controls while Step 1 is current, and single step numbering in the card headers.
- Playwright confirms no horizontal overflow and deterministic mobile selected-document gating.
- The router still holds the persistent-write gate. The next prerequisite is to unify Step 1 wording around one expected output, add explicit `Complete Step X to unlock` prerequisite lines for disabled steps, align card status chips with stepper states, and then implement the first persistent selected-document write boundary behind the clarified gate.

Mobile explicit gate review:

- Screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-explicit-gates/screenshots/01-workspace-docket-mobile-explicit-gates.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-explicit-gates/screenshot-metadata-explicit-gates.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-explicit-gates/router-review-mobile-explicit-gates.json`
- Implemented the explicit-gate pass: Step 1 is `Start Document Chat`, the active step explains chat opens before anything is saved, Step 1 exposes a `Not started -> Chat started -> Ready to label` progression, Steps 2-4 are disabled action rows with locked labels, and top chips use `Current` / `Locked` state vocabulary.
- Playwright confirms the selected-document mobile state remains scoped, deterministic, and free of horizontal overflow.
- The router still holds the persistent-write gate. Remaining prerequisite: define explicit completion criteria and persistence states before real selected-document writes, then compact locked rows so the mobile screen does not read like a wall of requirements.

Mobile ready-to-label control review:

- Screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-ready-label-control/screenshots/01-workspace-docket-mobile-ready-label-control.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-ready-label-control/screenshot-metadata-ready-label-control.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-ready-label-control/router-review-mobile-ready-label-control.json`
- Implemented the visible first-write boundary preview: Step 1 completion criteria, disabled `Mark Ready To Label`, `Save status: not saved yet`, ordered `Current` / `Locked` chips, and locked Step 2-4 controls.
- The router still holds the persistent-write gate. The remaining prerequisite is a checklist-driven Step 1 gate and write lifecycle chip before wiring the first MCP-backed selected-document mutation.

Mobile actionable checklist review:

- Screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-actionable-checklist/screenshots/01-workspace-docket-mobile-actionable-checklist.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-actionable-checklist/screenshot-metadata-actionable-checklist.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-actionable-checklist/router-review-mobile-actionable-checklist.json`
- Added `Requirements: 0 of 2 complete`, actionable Step 1 checklist rows, and `Save: idle - no server write yet`.
- The router still holds the persistent-write gate. The next prerequisite is a mobile-first Step 1 action panel and collapsed locked Step 2-4 accordions before the first MCP-backed selected-document write is wired.

## Workstream 1: Better questions

Primary files:

- [complaint_phases/denoiser.py](../complaint_phases/denoiser.py)
- [complaint_phases/knowledge_graph.py](../complaint_phases/knowledge_graph.py)
- [complaint_phases/dependency_graph.py](../complaint_phases/dependency_graph.py)
- [templates/claim_support_review.html](../templates/claim_support_review.html)

Work:

- replace generic missing-info prompts with claim-element-targeted questions,
- rank questions by expected proof gain,
- distinguish testimony questions from document-request questions,
- ask one contradiction-resolution question before broad retrieval when contradictions are blocking,
- add timeline-specific, damages-specific, and actor-identification question types,
- attach a “why this question matters” explanation to each prompt,
- suppress redundant questions when the graph or vector plane already has sufficient support.

Acceptance criteria:

1. Each suggested question maps to at least one unresolved claim element or contradiction.
2. Each question exposes the target legal element and expected benefit.
3. Repeated semantically similar questions are clustered or suppressed.

## Workstream 2: Testimony capture quality

Primary files:

- [templates/claim_support_review.html](../templates/claim_support_review.html)
- mediator review APIs
- future testimony persistence hooks under `mediator/`

Work:

- add a structured testimony composer to the dashboard,
- capture event date, actor, act, target, harm, and source confidence,
- support freeform narrative plus structured extraction preview,
- let the operator mark whether testimony is firsthand, hearsay, or uncertain,
- generate claim-element candidate links before saving,
- persist testimony revisions and review audit history.

Acceptance criteria:

1. Testimony can be stored as structured facts plus raw narrative.
2. Testimony entries can be linked to specific claim elements.
3. The dashboard can show which legal elements each testimony item supports.

## Workstream 3: Document ingestion and decomposition

Primary files:

- [integrations/ipfs_datasets/documents.py](../integrations/ipfs_datasets/documents.py)
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- [templates/claim_support_review.html](../templates/claim_support_review.html)

Work:

- add dashboard upload and document-link intake,
- route every document through the shared parse contract,
- persist parse quality flags and transform lineage,
- generate chunk IDs and chunk-level metadata,
- flag low-quality parses for operator remediation,
- expose chunk previews and source-page references in the dashboard,
- support reparsing and OCR retry workflows.

Acceptance criteria:

1. Uploaded documents produce normalized parse records and chunks.
2. Every chunk has stable provenance back to artifact and source span.
3. Low-quality parses surface explicit remediation recommendations in the dashboard.

## Workstream 4: Fact registry and support matrix

Primary files:

- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [docs/PAYLOAD_CONTRACTS.md](./PAYLOAD_CONTRACTS.md)

Work:

- expand the persisted claim support schema into a broader fact registry,
- store fact-to-chunk, fact-to-claim-element, and fact-to-authority links,
- add durable support packet IDs and proof-path references,
- normalize contradiction and uncertainty states on facts,
- expose a canonical “element support ledger” in the review payload.

Acceptance criteria:

1. The review API can explain every element status using concrete fact IDs.
2. Facts can be traced back to testimony or document chunks.
3. Dashboard summaries can be regenerated from stored data without re-parsing the world.

## Workstream 5: Graph enrichment and persistence

Primary files:

- [integrations/ipfs_datasets/graphs.py](../integrations/ipfs_datasets/graphs.py)
- [complaint_phases/knowledge_graph.py](../complaint_phases/knowledge_graph.py)
- [complaint_phases/dependency_graph.py](../complaint_phases/dependency_graph.py)

Work:

- persist graph snapshots for testimony, evidence, and legal elements,
- add query functions for “show support path to this element”,
- add entity resolution between testimony actors and document entities,
- attach law nodes and rule nodes to claim elements,
- make graph snapshots reusable by review, follow-up, and drafting workflows.

Acceptance criteria:

1. Each claim element can show a graph-backed support path.
2. Graph snapshots can be reused instead of recomputed for every review request.
3. Entity resolution reduces duplicate party/evidence nodes across testimony and documents.

## Workstream 6: Vector indexing and retrieval

Primary files:

- `integrations/ipfs_datasets/vector_store.py`
- [integrations/ipfs_datasets/documents.py](../integrations/ipfs_datasets/documents.py)
- review/follow-up mediator hooks

Work:

- index testimony and document chunks in one retrieval plane,
- add claim-element-scoped retrieval,
- add retrieval explanations in the dashboard,
- store retrieval sessions for repeatability,
- use retrieval results to improve follow-up prompts and proof analysis,
- use vector similarity to detect duplicate or conflicting evidence narratives.

Acceptance criteria:

1. Operators can view the top retrieved chunks for an element.
2. Retrieval sessions are stable enough to debug and replay.
3. The question engine can cite retrieved context when asking follow-up questions.

## Workstream 7: Legal rule graph and logic validation

Primary files:

- [integrations/ipfs_datasets/logic.py](../integrations/ipfs_datasets/logic.py)
- `integrations/ipfs_datasets/graphrag.py`
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)

Work:

- implement `prove_claim_elements`, `check_contradictions`, and related logic adapter behavior,
- normalize legal authorities into rule or predicate structures,
- map legal elements and exceptions into graph nodes,
- run proof-gap detection per claim element,
- expose contradiction explanations and legal-rule explanations,
- distinguish “missing evidence” from “legal rule not satisfied” from “factual contradiction”.

Acceptance criteria:

1. The review payload can state whether an element is unproved, contradicted, or exception-barred.
2. Each result includes a concise explanation of the legal rule or predicate failure.
3. The dashboard can show “facts applied to law” rather than only support counts.

## Workstream 8: Dashboard experience redesign

Primary files:

- [templates/claim_support_review.html](../templates/claim_support_review.html)
- [docs/APPLICATIONS.md](./APPLICATIONS.md)
- [docs/PAYLOAD_CONTRACTS.md](./PAYLOAD_CONTRACTS.md)

Work:

- add separate tabs or sections for Questions, Testimony, Documents, Facts, Graph, Law, and Actions,
- add per-element proof cards with evidence, authority, contradiction, and next-action sections,
- add document-ingestion status and parse-quality panels,
- add graph and retrieval drilldowns without overwhelming the default view,
- preserve deep-link navigation from `/document` into claim and section context,
- keep the current manual-resolution surface but attach it to proof explanations.

Acceptance criteria:

1. Operators can move from question to testimony to proof review without leaving the dashboard.
2. Each unresolved element has a visible next action.
3. The dashboard remains usable for both narrow single-claim review and broad filing readiness review.

## Suggested Milestones

### Milestone 0: Question and testimony foundation

Scope:

- stronger question ranking,
- structured testimony capture,
- question-to-element mapping,
- testimony persistence.

Primary outcome:

The dashboard becomes a guided intake and clarification surface instead of only a post-hoc review screen.

### Milestone 1: Document ingestion plane

Scope:

- dashboard document upload,
- parse contract adoption,
- chunk persistence,
- parse quality remediation.

Primary outcome:

Documents become normalized evidence artifacts rather than opaque attachments.

### Milestone 2: Unified fact and graph substrate

Scope:

- fact registry,
- graph snapshot persistence,
- claim-element support paths,
- testimony/document entity resolution.

Primary outcome:

All support can be traced through one reusable graph-backed corpus.

### Milestone 3: Vector retrieval and review explainability

Scope:

- chunk embeddings,
- element-scoped retrieval,
- retrieval drilldowns,
- duplicate/conflict detection.

Primary outcome:

Operators can see the best evidence chunks and how they were selected.

### Milestone 4: Legal proof and contradiction engine

Scope:

- logic adapter implementation,
- legal rule normalization,
- proof-gap outputs,
- contradiction explanations.

Primary outcome:

The system can explain whether facts satisfy legal elements, not just whether support exists.

### Milestone 5: Full operator productization

Scope:

- redesigned dashboard,
- stable payload contracts,
- evaluation suite,
- `/document` integration,
- queue-backed heavy processing where needed.

Primary outcome:

`/claim-support-review` becomes the canonical operator workflow for evidence sufficiency and legal readiness.

## Data Contracts To Add

The following new payload families are recommended.

### 1. Question Recommendation Contract

Fields:

- question ID,
- question text,
- target claim type,
- target claim element ID,
- question reason,
- expected proof gain,
- question lane (`testimony`, `document_request`, `contradiction_resolution`, `authority_clarification`),
- supporting evidence summary,
- suppression or dedup metadata.

### 2. Testimony Fact Contract

Fields:

- testimony record ID,
- raw narrative,
- extracted structured facts,
- source confidence,
- firsthand status,
- linked claim elements,
- linked artifact IDs,
- contradiction notes,
- created and updated timestamps.

### 3. Evidence Artifact Contract

Fields:

- artifact ID,
- source type,
- filename or URL,
- parse summary,
- transform lineage,
- chunk list or chunk references,
- graph snapshot ID,
- vector index status,
- parse remediation status.

### 4. Element Proof Card Contract

Fields:

- claim element ID,
- legal rule text,
- validation status,
- required predicates,
- satisfied predicates,
- missing predicates,
- contradiction list,
- supporting fact IDs,
- supporting document chunk IDs,
- supporting authority IDs,
- next recommended action.

## Evaluation Plan

The plan should be measured with explicit quality loops.

### Question quality metrics

- percent of questions tied to unresolved legal elements,
- percent of questions answered with usable structured facts,
- duplicate-question suppression rate,
- average proof-gain after each answered question.

### Testimony quality metrics

- fraction of testimony records that produce extractable facts,
- fraction of testimony records linked to at least one claim element,
- contradiction rate between testimony and documents,
- operator correction rate.

### Document pipeline metrics

- parse success rate by format,
- chunk generation rate,
- parse quality tier distribution,
- remediation rate for low-quality parses.

### Proof and sufficiency metrics

- percent of elements with graph-backed support,
- percent of elements with vector-backed retrieval context,
- percent of elements with executable proof status,
- contradiction detection precision on curated fixtures,
- claim-level readiness improvement over baseline.

### Operator experience metrics

- time from review load to first high-value action,
- number of clicks to resolve one missing element,
- percent of unresolved elements with visible next action,
- percent of draft warnings that link to actionable dashboard proof cards.

## Testing Strategy

### Unit tests

- question ranking,
- testimony extraction,
- document parse normalization,
- chunk lineage,
- fact registry linking,
- graph support-path generation,
- proof-gap classification,
- contradiction detection.

### Integration tests

- upload document -> parse -> chunk -> graph -> vector -> review payload,
- answer testimony question -> create fact -> update element proof card,
- authority acquisition -> rule extraction -> proof evaluation,
- `/claim-support-review` -> `/document` context preservation.

### Browser tests

- dashboard question workflow,
- testimony entry and save,
- document upload and parse-quality feedback,
- proof card drilldowns,
- manual resolution with proof explanation.

### Regression tests

- degraded-mode behavior when graphs, logic, or embeddings are unavailable,
- adapter-boundary correctness,
- payload compatibility for existing dashboard clients,
- replayable retrieval and proof snapshots.

## Recommended First Implementation Slice

Implement Milestone 0 first, with one narrow vertical slice:

1. add element-targeted question recommendations,
2. add structured testimony capture to `/claim-support-review`,
3. persist testimony as fact-like records linked to claim elements,
4. show those facts in existing claim-element cards,
5. update `claim_coverage_summary` with testimony-backed support counts.

That slice is the highest leverage because it immediately improves question quality and evidence quality without waiting for full legal-proof implementation.

## Success Criteria

This plan should be considered successful when:

1. `/claim-support-review` can guide operators through testimony and document collection for unresolved legal elements.
2. Uploaded documents are decomposed into reusable chunks with lineage, graph nodes, and vector index entries.
3. The review payload can trace each claim-element decision back to facts, documents, and authorities.
4. The logic layer can distinguish missing support from contradictions and rule failures.
5. `/document` consumes the same validated support state to improve drafting readiness and final complaint quality.

## April 27 Mobile Docket Gate Update

Focused selected-document mobile artifacts:

- Initial focused screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-focused-step1/screenshots/01-workspace-docket-mobile-focused-step1.png`
- Initial focused metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-focused-step1/screenshot-metadata-focused-step1.json`
- Initial focused router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-focused-step1/router-review-mobile-focused-step1.json`
- Lock-refinement screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-focused-step1/screenshots/02-workspace-docket-mobile-focused-step1-lock-refinement.png`
- Lock-refinement metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-focused-step1/screenshot-metadata-focused-step1-lock-refinement.json`
- Lock-refinement router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-focused-step1/router-review-mobile-focused-step1-lock-refinement.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes reviewed:

- Step 1 now renders as the focused mobile action panel with one primary `Start Document Chat` CTA.
- The selected-document scope is reinforced as `Chatting about: Termination timeline email. Questions will apply only to this document.`
- `Mark Ready To Label` and the save-state chip live together in the Step 1 footer.
- Steps 2-4 are compact locked rows with write controls hidden until eligible.
- Locked row headers now say `Locked`, do not use the prior plus affordance, and have no pointer interaction while locked.

Gate decision:

- Playwright confirms no horizontal overflow and verifies the compact locked rows, hidden future write controls, focused Step 1 panel, and non-interactive locked headers.
- The router still holds the persistent-write gate. The remaining blocker is the state contract for first write behavior: the UI needs to distinguish ephemeral document-chat progress from the first server-backed selected-document write.
- Before adding the first selected-document write, implement one authoritative Step 1 checklist with live pass/fail state, disabled-button reason text tied to the first unmet item, and explicit persistence mode such as `Local draft only until Mark Ready` versus `Ready confirmation saved`.
- Add Playwright network assertions that no selected-document write mutation fires before Step 1 passes.

Follow-up state-contract review:

- Initial state-contract screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/screenshots/01-workspace-docket-mobile-step1-state-contract.png`
- Visible-contract screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/screenshots/02-workspace-docket-mobile-step1-state-contract-visible.png`
- Reduced-density screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/screenshots/03-workspace-docket-mobile-step1-state-contract-reduced.png`
- Reduced-density metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/screenshot-metadata-step1-state-contract-reduced.json`
- Reduced-density router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/router-review-mobile-step1-state-contract-reduced.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

State-contract changes:

- Added the derived mobile Step 1 state model with `current_state`, `first_unmet`, `persistence_mode`, `selected_document_write_count`, and `canMarkReady`.
- Added a visible state-contract block and a three-item Step 1 checklist.
- Changed the primary CTA to `Open Chat And Ask First Question`.
- Added Playwright assertions that the pre-gate selected-document write count is zero and no selected-document write request fires before Step 1 passes.

Current gate:

- The state contract is now technically explicit and tested.
- The router still holds the first-write implementation gate because the mobile screen is too dense for a layperson to scan confidently.
- Next prerequisite is a visual simplification pass: keep one compact progress sentence, one readable state/checklist module, one primary CTA, and demote top chips plus locked future steps until Step 1 is complete.

Step 1 simplification follow-up:

- Initial simplified screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshots/01-workspace-docket-mobile-step1-simplified.png`
- Copy-final screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshots/02-workspace-docket-mobile-step1-simplified-copy-final.png`
- Hierarchy-final screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshots/03-workspace-docket-mobile-step1-simplified-hierarchy-final.png`
- Hierarchy-final metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshot-metadata-step1-simplified-hierarchy-final.json`
- Hierarchy-final router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/router-review-mobile-step1-simplified-hierarchy-final.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes reviewed:

- Hid top step chips and future locked rows while Step 1 is current.
- Shortened the primary CTA to `Open Chat`.
- Kept one visible unlock sentence and one compact question status token.
- Renamed the write counter to `Document updates captured: 0`.
- Normalized selected-document metadata and attached the disabled ready reason through `aria-describedby`.

Current gate:

- Playwright confirms one visible Step 1 panel, no horizontal overflow, no visible future locked rows, no visible blocked checklist rows, and zero selected-document write requests before Step 1 passes.
- The router still holds the implementation gate. Remaining blockers are now presentation/state-mapping issues only: the disabled ready action should feel more guided, and Step 1 should use flatter styling with an obvious enabled-after-chat progression state.
- Do not add the first persistent selected-document write until that visual progression state is clear; keep `ComplaintMcpClient` event/gating behavior unchanged.

Guided-ready follow-up:

- Guided-ready screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshots/04-workspace-docket-mobile-step1-guided-ready-final.png`
- Chat-only pre-gate screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshots/05-workspace-docket-mobile-step1-chat-only-final.png`
- Chat-only pre-gate metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshot-metadata-step1-chat-only-final.json`
- Chat-only pre-gate router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/router-review-mobile-step1-chat-only-final.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Current gate:

- Pre-gate mobile Docket now shows only one visible action, `Open Chat`; the future ready action is hidden until it can become actionable.
- Playwright confirms zero selected-document write requests before Step 1 passes.
- The router still holds the first-write gate. It considers the pre-gate state functionally coherent but too status-heavy.
- Next prerequisite is to review the post-chat visual state: after one document-specific question is recorded, the screen should make `Mark Ready To Label` appear as the guided next action while still preserving the MCP write gate.

Post-chat visual-state follow-up:

- Post-chat screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-post-chat/screenshots/01-workspace-docket-mobile-step1-post-chat.png`
- Post-chat metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-post-chat/screenshot-metadata-step1-post-chat.json`
- Post-chat router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-post-chat/router-review-mobile-step1-post-chat.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Current gate:

- The post-chat UI now keeps Step 1 current after one question, shows `Mark Ready To Label` as a guided disabled next action, and keeps selected-document write count/request count at zero.
- The router still holds the first-write gate on layperson comprehension grounds. Its concrete next prerequisite is to make `Generate Impact Summary` the primary post-chat action, demote `Open Chat`, and collapse the current Done/Missing/Waiting/Persistence blocks into one three-step progress tracker.
- Do not wire the first selected-document mutation until the post-chat state has one obvious required action and the ready-to-label control only becomes prominent once the impact summary exists.

Comprehensive pre-implementation bundle:

- Mobile pre-chat screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-plan-before-implementation/screenshots/01-mobile-pre-chat-current.png`
- Mobile post-chat screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-plan-before-implementation/screenshots/02-mobile-post-chat-current.png`
- Desktop Docket screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-plan-before-implementation/screenshots/03-desktop-docket-current.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-plan-before-implementation/screenshot-metadata-plan-before-implementation.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-plan-before-implementation/router-review-plan-before-implementation.json`
- Strategy: `page_reviews` across three `multimodal_router` page reviews
- Provider/model: `codex_cli / gpt-5.3-codex`

Current gate:

- The router keeps the selected-document write gate closed. It specifically calls out confusing readiness hierarchy, too many equal-weight status boxes, and unclear distinction between read-only review/chat actions and draft-affecting write actions.
- The implementation plan should now start with a shared Docket gate presenter: one state object, one progress component, one scope/safety pill, and one primary next action per state.
- The post-chat state should promote `Generate Impact Summary` as the primary action, demote `Open Chat`, and keep `Mark Ready To Label` disabled or visually locked until the impact summary exists.
- Desktop should mirror the same state vocabulary and group actions into `Read-only review` versus `Draft-affecting` controls so lay users do not treat `Use In Draft Anyway` as a safe equivalent to review.
- Verification should include Playwright checks that no selected-document write/resource request fires before the ready gate and that the post-chat primary CTA changes without emitting a write.

Broader workflow pre-implementation bundle:

- Mobile Evidence screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/screenshots/01-mobile-evidence-after-document.png`
- Mobile Docket post-chat screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/screenshots/02-mobile-docket-post-chat-gate.png`
- Mobile document-chat context screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/screenshots/03-mobile-document-chat-context.png`
- Desktop Review proof-map screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/screenshots/04-desktop-review-proof-map.png`
- Desktop Draft readiness/export screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/screenshots/05-desktop-draft-readiness-and-export.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/screenshot-metadata-broader-workflow-before-implementation.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/router-review-broader-workflow-before-implementation.json`
- Strategy: `page_reviews`; Evidence, Docket, Chat, and Draft were selected as highest-signal pages.
- Provider/model: `codex_cli / gpt-5.3-codex`

Current gate:

- The broader workflow review keeps the selected-document write gate closed and adds prerequisites outside the Docket card itself.
- Evidence intake must be mobile-readable before downstream label/annotation writes are introduced: one column, no duplicate `EVIDENCE KIND` controls, required claim-element mapping, and a clear save/import hierarchy.
- Document-scoped Chat must put selected filing context above generic navigation and diagnostics. For answer-save and annotation behavior to be safe, the first viewport must say which filing is attached, what question is being asked, and whether the answer will be saved or only drafted locally.
- Draft readiness/export needs a single canonical gate verdict and clearer blocked/enabled controls, otherwise Docket writes may appear to unlock filing actions prematurely.
- The implementation sequence should therefore be: mobile Evidence cleanup, document-scoped Chat first-viewport cleanup, Docket gate presenter, then selected-document persistence.

Standalone surface pre-implementation bundle:

- Mobile Review before-load screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/01-mobile-review-before-load.png`
- Mobile Review loaded screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/02-mobile-review-loaded.png`
- Mobile Builder empty screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/03-mobile-document-builder-empty.png`
- Mobile Builder generated screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/04-mobile-document-builder-generated.png`
- Desktop Builder generated screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/05-desktop-document-builder-generated.png`
- Desktop Optimization Trace screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/06-desktop-optimization-trace.png`
- Desktop Editor Workshop screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/07-desktop-editor-workshop.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshot-metadata-standalone-surfaces-before-implementation.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/router-review-standalone-surfaces-before-implementation.json`
- Strategy: `page_reviews`; Builder and Optimization Trace were selected as highest-signal pages.
- Provider/model: `codex_cli / gpt-5.3-codex`

Current gate:

- The selected-document write gate remains closed. The standalone review adds a shell-level prerequisite: split layperson and operator surfaces before adding more write-capable Docket controls.
- Formal Complaint Builder, Optimization Trace, Editor Workshop, SDK, Dashboards, router settings, and raw trace internals should not appear as equal-weight layperson navigation options.
- Builder needs a mobile-first guided draft stepper and actionable empty/generated states before it becomes the landing zone for Docket-supported facts.
- Optimization Trace should be advanced/operator-only by default. If exposed to lay users, it must render a plain-language readiness summary rather than raw telemetry.
- Updated implementation order: Guided/Advanced shell split, mobile Evidence cleanup, document-scoped Chat cleanup, Docket gate presenter, then selected-document persistence.

## Consolidated Implementation Readiness Roadmap

Date: 2026-04-27

The repeated Playwright plus `multimodal_router` passes have converged on the same gate: the Review/Docket/Draft system is technically wired, but not yet layperson-safe enough for new selected-document writes. The claim-support dashboard plan should treat Docket persistence as downstream of a broader shell and evidence/readiness cleanup.

Priority sequence:

1. Guided versus Advanced shell split.
   - Layperson path: Intake, Evidence, Review, Docket, Chat, Draft.
   - Advanced/operator path: Optimization Trace, SDK, Editor Workshop, Dashboards, router/model settings, raw JSON, and telemetry.
   - Keep MCP contracts unchanged; this is presentation and routing hierarchy only.

2. Evidence and support intake cleanup.
   - Make mobile Evidence one column, readable, and focused on one save path.
   - Require claim-element mapping before evidence save.
   - Fix duplicate or ambiguous evidence metadata labels.
   - Make status cards actionable with direct remediation links.

3. Document-scoped Chat cleanup.
   - Put selected filing context first when the user enters chat from Docket.
   - Show document title/source, prepared question, local-only persistence state, and return path before generic navigation.
   - Keep ask, summarize, and save as separate visible phases.

4. Docket gate presenter.
   - Use one shared gate state for mobile and desktop.
   - Promote `Generate Impact Summary` after the first document-specific question.
   - Keep `Mark Ready To Label` locked until impact summary exists.
   - Separate read-only review/chat from draft-affecting write controls.

5. Draft/readiness cleanup.
   - Use one canonical verdict banner and one primary next action.
   - Make blocked/enabled export actions unmistakable.
   - Keep Builder as a Draft-stage continuation, not a source-support workspace.

6. Persistence rollout.
   - First write: selected-document ready confirmation only.
   - Later writes: label, annotation, deadline, answer-save, and draft-note persistence.
   - Every write needs Playwright network assertions and screenshot/router review before expansion.

Gate to begin the first write:

- Mobile Evidence, document-scoped Chat, Docket gate, and Draft readiness screenshots pass without high-severity router findings.
- Advanced/operator tools are hidden from layperson mode by default.
- Playwright confirms no selected-document mutation before `readyEligible=true`.
- Post-chat Docket shows `Generate Impact Summary` as primary and `Open Chat` as secondary.
- Review/Draft surfaces do not imply that Docket readiness makes a filing/export safe without support-review gates.

First prerequisite implementation note:

- Started the Guided versus Advanced shell split on the layperson-adjacent Builder, Review, and Chat surfaces.
- Advanced/operator destinations remain reachable, but Profile, Results, Trace, Editor Workshop, SDK, and Dashboards are now grouped behind `Advanced tools` disclosures on those surfaces.
- Core handoffs remain visible for the guided complaint path, and existing MCP/browser href wiring is preserved.
- No selected-document ready, label, annotation, deadline, answer-save, or draft-note persistence was added in this step.

Second prerequisite implementation note:

- Completed the first mobile Evidence cleanup pass.
- The main Evidence composer now presents `Evidence Type`, `Claim Element This Supports`, and the primary `Save Evidence Item` action before optional import tools.
- Gmail/local import controls remain available but are visually and semantically secondary, with labels that distinguish imported-item metadata from the normal saved evidence item.
- Mobile Evidence has targeted single-column CSS for banners, decision cards, workbench metrics, guidance, and form fields.
- Screenshot artifact: `artifacts/mcp-dashboard-ui-review/evidence-mobile-cleanup-20260427/mobile-evidence-cleanup.png`
- Router review artifact: `artifacts/mcp-dashboard-ui-review/evidence-mobile-cleanup-20260427/router-review-evidence-mobile-cleanup.json`
- The selected-document write gate remains closed; the next prerequisite is document-scoped Chat first viewport cleanup.

Third prerequisite implementation note:

- Completed the document-scoped Chat first-viewport cleanup.
- Docket handoffs now render a selected filing card before the generic chat experience, with title, source/type, router scope, prepared question, return path, and a draft-only persistence warning.
- Docket/document Chat suppresses the shared application shell and primary surface nav so the first mobile viewport is about the selected filing, not global workflow diagnostics.
- Generic workspace/intake Chat handoffs still keep the normal shared shell and hero behavior.
- Screenshot artifact: `artifacts/mcp-dashboard-ui-review/document-chat-first-viewport-20260427/mobile-document-chat-first-viewport.png`
- Router review artifact: `artifacts/mcp-dashboard-ui-review/document-chat-first-viewport-20260427/router-review-document-chat-first-viewport.json`
- The selected-document write gate remains closed; the next prerequisite is the shared Docket gate presenter.

Fourth prerequisite implementation note:

- Completed the first shared Docket gate presenter pass.
- Desktop and mobile Docket now use the same derived Step 1 state for selected-document readiness: question asked, impact summary ready, ready eligible, ready saved, persistence mode, and write count.
- Desktop now renders a `Selected document gate` card with the same sequence previously only visible in mobile: `Open Chat`, then `Generate Impact Summary`, then `Mark Ready To Label`.
- `Generate Impact Summary` is local-only in this prerequisite and reports that no selected-document write has been sent.
- `Mark Ready To Label` remains a visible persistence boundary, but the actual selected-document ready-confirmation write is still gated.
- Screenshot artifacts: `artifacts/mcp-dashboard-ui-review/docket-gate-presenter-20260427/mobile-docket-gate-post-chat.png` and `artifacts/mcp-dashboard-ui-review/docket-gate-presenter-20260427/desktop-docket-gate-post-chat.png`
- Router review artifact: `artifacts/mcp-dashboard-ui-review/docket-gate-presenter-20260427/router-review-docket-gate-presenter.json`
- The selected-document write gate remains closed; the next prerequisite is Draft/readiness affordance cleanup.

Fifth prerequisite implementation note:

- Completed the Draft/readiness cleanup pass.
- Draft now separates the duplicate gate surfaces: the top gate is a secondary summary, while the lower `Canonical filing verdict` is the primary decision point for generate/export/download.
- Download controls now sit behind an explicit `data-download-state` boundary with a plain-language blocker note and `aria-disabled` synchronization.
- Focused tests assert the secondary summary role, the primary canonical verdict rail, and the blocked/ready download state.
- Screenshot artifacts: `artifacts/mcp-dashboard-ui-review/draft-readiness-cleanup-20260427/desktop-draft-readiness.png` and `artifacts/mcp-dashboard-ui-review/draft-readiness-cleanup-20260427/mobile-draft-readiness.png`
- Router review artifact: `artifacts/mcp-dashboard-ui-review/draft-readiness-cleanup-20260427/draft-readiness-router-review.json`
- Router route repair: the UI review resolver now treats `provider=llm_router` and `model=multimodal_router` as route aliases, resolves them before backend calls, and records `route_alias_resolved: true`. The refreshed review runs page reviews through `codex_cli / gpt-5.3-codex` instead of failing with `Unknown LLM provider: llm_router`.
- Follow-up Draft layout repair: the canonical verdict now renders first/full-width in the Draft action rail, action groups use responsive widths, mobile Draft action sections are forced to one column, and the Draft editor uses bounded height instead of a 980px blank panel.
- Viewport-scoped Draft screenshots narrowed the issue to decision hierarchy: the page no longer fails as a blank layout, but the canonical verdict still showed conflicting peer chips and too many equal-weight actions.
- Follow-up hierarchy repair: the Draft verdict now says `Filing verdict: BLOCKED`, `Review open`, `Draft open`, and `Downloads blocked`; only the blocker-specific `Fix now: ...` action is primary; secondary destinations are grouped as smaller Review/Evidence/CLI options; packet export is not promoted while the filing verdict is blocked; and formal pleading checks show concrete blocker lines.
- The selected-document write gate remains closed; rerun the scoped screenshot/router review before starting the first selected-document ready-confirmation write with network assertions.

Sixth prerequisite review note:

- Reviewed the Dashboard Hub prerequisite pass with Playwright desktop/mobile screenshots routed through `llm_router` / `multimodal_router`.
- Screenshot artifacts: `artifacts/mcp-dashboard-ui-review/dashboard-hub-prerequisites-20260428/dashboard-hub-desktop.png` and `artifacts/mcp-dashboard-ui-review/dashboard-hub-prerequisites-20260428/dashboard-hub-mobile.png`
- Router review artifact: `artifacts/mcp-dashboard-ui-review/dashboard-hub-prerequisites-20260428/dashboard-hub-router-review.json`
- Partial repair in the JS stub hub: one dominant `Start intake questions` CTA, returning-user links separated from the primary card, clearer saved-work/docket labels, lower-density prerequisite status lines, and updated navigation tests.
- Verification: `npx playwright test playwright/tests/navigation.spec.js --grep 'dashboard|document and dashboard'` passes.
- The router still holds the dashboard gate. Remaining high findings are structural: secondary actions need unmistakable button affordance plus eligibility state, and the hub should either use one unified Intake/Evidence/Review card model or more clearly separate first-time intake from returning-user paths.
- The selected-document write gate remains closed until this dashboard entry model is resolved and rerun through scoped screenshot review.

Dashboard gate continuation:

- The JS stub dashboard now uses a Step 1/2/3 complaint-flow model with Step 2 and Step 3 guarded as waiting/disabled states.
- Refreshed desktop/mobile screenshots and reran the `llm_router` / `multimodal_router` review at `artifacts/mcp-dashboard-ui-review/dashboard-hub-prerequisites-20260428/dashboard-hub-router-review.json`.
- Verification: `npx playwright test playwright/tests/navigation.spec.js --grep 'dashboard|document and dashboard'` passes on rerun.
- The router still holds the gate. Remaining high findings: use one shared step-state render model across the top stepper and lower cards, make mobile Step 1 the clear primary button, and make locked Evidence/Review controls plainly disabled with one unlock reason.
- The selected-document write gate remains closed.

Dashboard gate continuation, second review:

- Reworked the hub toward the shared state model requested by the router: Intake is the current first action, Evidence and Review share the same `Locked` state vocabulary in the stepper and locked cards, and the locked cards no longer expose navigation links as primary actions.
- Refreshed `artifacts/mcp-dashboard-ui-review/dashboard-hub-prerequisites-20260428/dashboard-hub-desktop.png`, `dashboard-hub-mobile.png`, and `dashboard-hub-router-review.json`.
- Router path: `page_reviews` through `codex_cli / gpt-5.3-codex`; requested aliases `llm_router` / `multimodal_router`; `route_alias_resolved: true`; selected both screenshots; skipped `0`.
- Verification: `npx playwright test playwright/tests/navigation.spec.js --grep 'dashboard|document and dashboard'` passes.
- The router still holds the dashboard gate. Remaining high findings are not backend blockers; they are UI hierarchy blockers: locked cards still look too active, prerequisite text repeats in competing locations, and the mobile locked-step affordance is not strong enough for layperson confidence.
- The next plan improvement should simplify the Dashboard Hub before persistence work: one obvious Intake CTA, one compact stage-status strip, and a clearly secondary locked-state explanation that cannot be mistaken for enabled navigation.

Dashboard gate continuation, third review:

- Reworked the hub into a single stateful stage-control grid: Step 1 Intake is enabled, while Step 2 Evidence and Step 3 Review are disabled controls with inline unlock text.
- Fixed the desktop Intake text squeeze by stacking the active card content, and compacted the mobile stage cards so the locked controls are less likely to be stranded below the first viewport.
- Refreshed `dashboard-hub-desktop.png`, `dashboard-hub-mobile.png`, and `dashboard-hub-router-review.json` under `artifacts/mcp-dashboard-ui-review/dashboard-hub-prerequisites-20260428/`.
- Router path: `page_reviews` through `codex_cli / gpt-5.3-codex`; requested aliases `llm_router` / `multimodal_router`; `route_alias_resolved: true`; selected both screenshots; skipped `0`.
- Verification: `npx playwright test playwright/tests/navigation.spec.js --grep 'dashboard|document and dashboard'` passes.
- The router still holds the gate. Remaining high findings: Evidence/Review still visually compete with Intake as disabled primary actions, the Profile utility section looks like empty/missing content, and mobile needs clearer unlock timing/action guidance after Step 1.
- The selected-document write gate remains closed. The next dashboard prerequisite is to demote Profile and recast locked stages as secondary progress/status rows with explicit disabled semantics but less primary-action weight.

Selected-document and Docket Chat cross-reference:

- The fuller April 28 selected-document/Docket Chat addendum now lives in `docs/LAYPERSON_DOCKET_WORKSPACE_UI_UX_PLAN.md`.
- It uses these screenshot-router artifacts as the current planning baseline:
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260428-plan-review/router-review-general.json`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260428-plan-review/router-review-docket-only.json`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260428-plan-review-v2/router-review-selected-document-states.json`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260428-plan-review-v2/router-review-impact-summary-ready.json`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260428-plan-review-v3/router-review-docket-chat-before-after.json`
- Claim-support Review and Draft work must not treat selected-document Docket readiness as filing/export readiness. Docket readiness should remain a document-level state until OCR, router, citation, support-review, and human-review gates are explicitly satisfied.
- Selected-document persistence remains closed until the Docket plan clears contradictory readiness copy, visible Docket-scoped Chat scope, router failure recovery, citation gating, and explicit save-back destinations.
