# Layperson Docket Workspace UI/UX Plan

## Evidence From Current Audit

Fresh Playwright screenshots were captured at:

- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/screenshots/workspace-homepage.png`
- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/screenshots/workspace-intake.png`
- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/screenshots/workspace-evidence.png`
- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/screenshots/workspace-review.png`
- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/screenshots/workspace-draft.png`
- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/screenshots/workspace-integrations.png`

The bounded router smoke report is at:

- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/reviews/bounded-router-review.json`

The current complaint journey can complete end to end through Playwright, including intake, evidence capture, support review, draft generation, export analysis, UX audit affordances, filing provenance, and markdown/PDF/DOCX packet export.

## Reliability Fixes Completed First

- Provider diagnostics are now lightweight and do not import the heavy router stack just to render browser status.
- Provider diagnostics normalize the public preference order to `codex_cli -> copilot_cli -> openai -> hf_inference_api`.
- Screenshot review now honors `COMPLAINT_GENERATOR_UI_REVIEW_TIMEOUT_SECONDS` and `COMPLAINT_GENERATOR_UI_REVIEW_TIMEOUT_SECONDS_<PROVIDER>`.
- Screenshot review can emit heartbeat lines with `COMPLAINT_GENERATOR_UI_REVIEW_HEARTBEAT_SECONDS`.
- Multimodal and text fallback timeouts now identify the page or router stage that is waiting.

## Main UX Findings

The existing UI has a strong staged mental model, but it is still dense for non-lawyers. The current surfaces explain a lot, often helpfully, but the page length and number of advanced panels can make the safe next action hard to find.

The most important change is to split the experience into two layers:

- A layperson-safe task path that always answers: `Where am I? What should I do next? Why does it matter?`
- An operator/advanced layer for CLI, MCP, Gmail, datasets, provenance, router diagnostics, and audit tooling.

The current bottom stage rail is useful, but it should become a persistent task rail with completion state, blockers, and one primary next action. The rail should work across complaint creation, response creation, and docket review.

## Docket Workspace Target Experience

The docket workspace should be a first-class mode, not only evidence inside a complaint form.

Core surfaces:

- `Docket Overview`: case caption, court, parties, filings count, retrieved documents count, OCR/indexing status, and missing documents.
- `Documents`: searchable table of filings, exhibits, attachments, orders, motions, transcripts, emails, and imported evidence.
- `Document Viewer`: PDF/page viewer with extracted text, page thumbnails, OCR confidence, citations, entities, events, and annotations.
- `Labels`: user and model-generated tags such as `supports claim`, `supports defense`, `needs OCR`, `contains deadline`, `contains admission`, `privilege review`, `key exhibit`.
- `Ask`: chatbot grounded in the docket bundle through `llm_router`, with visible citations and retrieval method.
- `Analysis`: knowledge graph, timeline, claim/defense matrix, Bluebook citations, contradiction candidates, and formal-logic audit outputs.
- `Package`: parquet export status, BM25/vector/KG readiness, IPFS/IPLD identifiers, and Hugging Face upload provenance.

## Document Review Requirements

Each document card should show:

- Human label and filing number.
- Source URL or CourtListener/PACER/RECAP provenance.
- Download status and content hash.
- Page count, OCR status, extracted text status, and vector count.
- BM25 indexed status, KG extracted status, citation extraction status, and formal-logic status.
- Tags, annotations, and claim/defense links.
- Last enrichment timestamp and any failed enrichment stage.

Each document viewer should support:

- Page-level annotation.
- Text span annotation.
- Label application.
- "Connect to fact" and "Connect to claim/defense" actions.
- "Ask about this page/document" chat handoff.
- "Show retrieval trace" for any chatbot answer that cites it.

## Chatbot/RAG Requirements

The chatbot should never answer like a free-floating legal oracle. It should answer from the indexed workspace and show grounding.

Every answer should expose:

- Source documents and page/snippet references.
- Whether retrieval used BM25, vector search, graph traversal, full text, citation resolver, or fallback search.
- Confidence and uncertainty.
- Missing documents or unindexed documents that could change the answer.
- A safe next action, such as "review document 14 attachment 2" or "OCR is missing for this exhibit."

The chatbot should support scoped modes:

- `Ask the whole docket`
- `Ask selected documents`
- `Ask this page`
- `Find evidence for a claim`
- `Find evidence for a defense`
- `Find contradictions`
- `Find deadlines`
- `Find cited legal authorities`

## Implementation Order

1. Add a docket/workspace mode switch and a lightweight docket overview panel.
2. Add document inventory UI backed by the existing packaged docket/operator dashboard data.
3. Add per-document enrichment status fields for OCR, text extraction, BM25, vector count, KG, citation extraction, and formal logic.
4. Add labels and annotations as first-class workspace records, not just display-only UI state.
5. Add document viewer handoffs into chatbot prompts with source scope preserved.
6. Add chat answer provenance cards for source snippets, retrieval method, and missing-index warnings.
7. Add Playwright coverage for docket overview, document selection, annotation, label assignment, and scoped chat handoff.
8. Add multimodal screenshot review as a non-blocking audit lane with heartbeat and deterministic fallback.

## Next Slice Contract

The latest Docket-to-chat screenshot review narrows the next implementation slice to source-grounded document chat and first-class annotations. The Docket lane is now visible enough to anchor the workflow, so the next slice should not expand the dashboard broadly. It should make one selected document trustworthy and reusable.

Prerequisite cleanup before or inside the next slice:

- Replace any raw internal route-index start screen with a small goal-based case hub: start/resume complaint, respond to a docket document, review documents, and ask the case assistant.
- Hide raw DID strings, MCP tool counts, backend IDs, provider names, and gate-version strings from the standard layperson view.
- Add legal-safety framing before any draft generation: the tool organizes facts and drafts documents, but does not provide legal advice.
- Translate review-gate jargon into proof tasks with concrete examples, for example "Missing corroboration for employer knowledge" plus "Attach a dated message or witness statement."
- Replace opaque readiness scores with criteria chips that name missing facts, documents, deadlines, citations, or source support.
- Give every disabled primary action an inline reason and a one-click recovery path.

Must build next:

- A persistent chat scope banner that says whether the assistant is answering from the whole docket, selected documents, one document, one page, or one annotation.
- A selected-document source panel beside chat with title, document type, source/provenance, labels, extracted text preview, and citation targets.
- Assistant answer cards with router path, retrieval method, confidence/source-support state, and citation chips.
- Save actions on answer cards: Save Annotation, Save Deadline, Save Issue, Save Evidence Task, Save Draft Note.
- A real Add Label / Add Annotation flow in the Docket lane that persists at least lightweight browser/workspace records and updates the visible annotation count.
- Deadline extraction or manual deadline capture surfaced as a Docket chip and a Draft/Review blocker when relevant.
- A plain-language document readiness summary that collapses OCR, text extraction, BM25, vector, knowledge graph, citation, and formal-logic statuses into one readable state.
- One readiness-based primary action per selected document, with secondary actions visually demoted.
- A pinned Urgency & Deadlines panel above technical metadata.
- Separate chat actions for Ask Question and Save Answer so users know when something has been committed to the complaint workspace.
- A mobile Docket task strip or sticky primary CTA that keeps the safest next action reachable after scrolling.
- One canonical selected-document card on mobile, with repeated metadata and technical details collapsed behind disclosures.
- Readiness states that cannot contradict required checks; use "Conditionally ready" or "Needs review before draft" when review, deadline, source, or router criteria remain unmet.
- Grouped label taxonomy: Legal Relevance, Workflow State, and Technical Processing.

Defer for later:

- Full PDF editing.
- Perfect OCR correction.
- Complete knowledge-graph visualization.
- Full formal-logic audit UI.
- CAR/IPLD/Hugging Face package management in the layperson path.
- Complex multi-document answer synthesis until single-document citations and save actions are reliable.

The first acceptance test should follow one document end to end:

1. Select a docket document.
2. Add a label.
3. Ask a scoped chat question.
4. See an answer with router path and citation/source state.
5. Save the answer as an annotation or deadline.
6. Return to Docket and see the annotation/deadline reflected on the document.
7. Open Draft or Review and see the saved item available as source support.

## Screenshot Review Notes

The most recent Playwright review artifacts are:

- `artifacts/ui-audit-docket-plan-review-20260420/screenshots/01-workspace-docket.png`
- `artifacts/ui-audit-docket-plan-review-20260420/screenshots/02-document-chat-context.png`
- `artifacts/ui-audit-docket-plan-review-20260420/screenshots/03-review-support.png`
- `artifacts/ui-audit-docket-plan-review-20260420/screenshots/04-draft-response-context.png`
- `artifacts/ui-audit-docket-plan-review-20260420/reviews/iteration-02-chat-single-review.json`
- `artifacts/ui-audit-docket-plan-review-20260422/screenshots/01-docket-current.png`
- `artifacts/ui-audit-docket-plan-review-20260422/screenshots/02-document-chat-current.png`
- `artifacts/ui-audit-docket-plan-review-20260422/screenshots/03-review-current.png`
- `artifacts/ui-audit-docket-plan-review-20260422/screenshots/04-draft-current.png`
- `artifacts/ui-audit-docket-plan-review-20260422/screenshots/05-ux-review-current.png`
- `artifacts/ui-audit-docket-plan-review-20260422/reviews/iteration-03-docket-single-review.json`
- `artifacts/ui-audit-docket-plan-review-20260422/reviews/iteration-03-chat-single-review.json`
- `artifacts/ui-audit-docket-plan-review-20260425/screenshots/01-docket-desktop.png`
- `artifacts/ui-audit-docket-plan-review-20260425/screenshots/02-document-chat-desktop.png`
- `artifacts/ui-audit-docket-plan-review-20260425/screenshots/06-docket-mobile.png`
- `artifacts/ui-audit-docket-plan-review-20260425/reviews/iteration-04-docket-desktop-review.json`
- `artifacts/ui-audit-docket-plan-review-20260425/reviews/iteration-04-chat-desktop-review.json`
- `artifacts/ui-audit-docket-plan-review-20260425/reviews/iteration-04-docket-mobile-review.json`
- `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260425-refresh/router-review.json`

The four-image bundle review hung, while the single-screen document-chat review completed through `multimodal_router` using `codex_cli`. The audit harness should therefore default to one-surface-at-a-time review until bundle execution has reliable timeouts and partial-artifact reporting.

The April 22 single-surface reviews also completed through `multimodal_router` using `codex_cli`. They confirmed that the next slice should prioritize state hierarchy and trust signals: collapse repeated technical statuses, pin deadlines, make one action primary, expose answer citations/confidence/router path, and split asking from saving.

The April 25 single-surface reviews again completed through `multimodal_router` using `codex_cli`. They confirmed the same desktop repairs and added a mobile-first gate: the selected document must fit into one canonical mobile card, expose only two or three high-priority chips before a disclosure, keep one primary action reachable, and dedupe repeated document/status blocks before implementation begins.

The April 25 refresh review completed five page-level `codex_cli` multimodal reviews for the dashboard hub, intake chat, workspace Docket, claim-support Review, and document builder. It adds one more precondition: the first layperson screen cannot be a long internal link index. It needs a goal-based case hub before Docket, annotations, Review, Draft, and chatbot surfaces will feel coherent.

## Acceptance Criteria

- A layperson can identify the next safest action within five seconds on every main surface.
- The first layperson screen presents goal-based case actions, not a raw route list or diagnostics index.
- A docket operator can see whether every document has been downloaded, OCRed, text extracted, indexed, and enriched.
- Selecting a document makes its provenance, text, labels, annotations, and analysis status visible without leaving the workspace.
- A chatbot answer always includes source references or clearly states that no indexed source supports the answer.
- Mobile Docket shows selected document title, readiness, nearest deadline or no-deadline state, and one primary action without repeated cards.
- Playwright captures homepage, complaint workspace, docket overview, document viewer, annotations, labels, chat, and package/export surfaces.
- Router review failures produce heartbeat output and a fallback artifact instead of hanging.

## Screenshot And Router Review Addendum: Docket Chat And Annotation Scope

Date: 2026-04-22

Fresh Playwright screenshots were captured at:

- `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260422/screenshots/workspace-homepage.png`
- `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260422/screenshots/workspace-intake.png`
- `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260422/screenshots/workspace-evidence.png`
- `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260422/screenshots/workspace-review.png`
- `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260422/screenshots/workspace-draft.png`
- `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260422/screenshots/workspace-integrations.png`

The Playwright journey passed:

- `COMPLAINT_UI_SCREENSHOT_DIR=artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260422/screenshots npx playwright test playwright/tests/complaint-flow.spec.js`
- Result: 13 passed.

The router review artifact is:

- `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260422/router-review.json`

Important router finding:

- The review was invoked with `--provider llm_router --model multimodal_router`.
- In `config.llm_router.json`, `llm_router` is a backend type, while registered provider values are currently `codex`, `codex_cli`, and `huggingface_router`.
- Because `llm_router` was treated as a provider override, page review fell back with `Unknown LLM provider: llm_router`.
- Before relying on automated multimodal review as a quality gate, the review command should use a real backend id/provider pair, or the UI review CLI should accept a semantic alias such as `--provider multimodal_router` and resolve it to the configured router backend.

### Visual Review Findings

The current UI has a coherent staged workflow, but the screenshots reinforce that the surface is still too vertically dense for layperson legal work. The homepage is the clearest screen because it shows only a few choices and readiness signals. The intake, evidence, review, draft, and integrations screens become long operational documents, which makes the next safe action harder to find.

Key findings:

- The homepage should become a package capability entry point, not only a complaint generator hero. It should expose four plain-language cards: guided intake, resume complaint/workspace, open docket/document dataset, and profile/personal information.
- The current workspace tabs are useful, but they mix layperson tasks with operator/MCP tooling. A layperson mode should keep the next action, blocker, and source state visible while moving advanced tooling into an expandable operations panel.
- The evidence and review surfaces contain the right ideas, but the page length suggests that document upload, evidence labeling, support matrix, and proof-gap workbench should be separate subsections inside the same workspace.
- The integrations surface is the least layperson-safe because it compresses CLI, MCP, provider diagnostics, UX audit, Gmail, and provenance into one very long operations page. This should become an advanced “System and Exports” area, not a primary complaint step.
- The current screenshots do not yet show a first-class docket document viewer. Docket review, annotation, labeling, and document chat should therefore be implemented as a separate Docket lane instead of being buried inside Evidence.

### Revised Information Architecture

The entry dashboard should present these top-level paths:

- `Start Guided Intake`: a chatbot/interview path that asks denoising questions to clarify parties, dates, protected activity or legal basis, adverse action or harm, evidence, deadlines, requested relief, and uncertainties.
- `Resume Complaint Workspace`: returns to an active complaint or response, with evidence, law, caselaw, generated draft, release gate, and next proof task.
- `Open Docket Dataset`: opens an existing docket/complaint dataset where the user can inspect filings, analyze documents, annotate pages/spans, label evidence, and ask grounded questions.
- `Profile And Personal Information`: manages identity, contact information, reusable party facts, accessibility needs, and filing preferences.

Each path should have its own local subsection navigation:

- Complaint workspace: `Intake`, `Evidence`, `Review`, `Draft`, `Packet`, `Operations`.
- Docket workspace: `Overview`, `Documents`, `Viewer`, `Labels`, `Ask`, `Analysis`, `Package`.
- Profile workspace: `Identity`, `Contacts`, `Case Defaults`, `Privacy`, `Exports`.

### Docket Workspace Priority

The next implementation should not try to finish every dashboard. The highest-value slice is a docket document workspace that can make one document trustworthy and reusable.

Build first:

- Docket Overview with filing/document counts, OCR/indexing status, missing documents, and next best action.
- Document Inventory with document type, source, docket number, page count, OCR status, text extraction status, labels, annotation count, and enrichment status.
- Document Viewer with selected document metadata, page/text preview, OCR confidence, and source provenance.
- Add Label and Add Annotation actions that persist lightweight workspace records.
- Scoped Ask panel with modes: whole docket, selected documents, this document, this page, this annotation.
- Chat answer cards with router path, retrieval method, citation/source chips, confidence, uncertainty, and save actions.

Defer:

- Full PDF redaction/editing.
- Complete graph visualization.
- Full deontic/formal logic UI.
- Complex multi-document synthesis before single-document citation and save flows are reliable.

### Router-Backed Chat Requirements

The document chatbot should never look like a general legal advice box. It should always show scope and grounding.

Required visible state:

- Current scope: whole docket, selected documents, one document, one page, or one annotation.
- Source panel: selected document title, type, source/provenance, labels, extracted text preview, and citation targets.
- Retrieval trace: BM25, vector, graph traversal, full text, citation resolver, OCR fallback, or no indexed source.
- Answer support state: supported, partially supported, unsupported, or blocked by missing OCR/indexing.
- Save actions: Save Annotation, Save Deadline, Save Issue, Save Evidence Task, Save Draft Note.

### Intake Chat Requirements

The intake chatbot should be a denoising interviewer, not a static form.

It should:

- Ask the fewest questions that improve legal clarity.
- Explain why a question matters in plain language.
- Capture uncertainty without forcing false precision.
- Detect likely legal basis, missing parties, missing dates, deadline risks, evidence gaps, harm, and requested relief.
- Handoff answers into the same fact/evidence workspace used by Review, Draft, and Docket.

### Implementation Sequence

1. Add the new entry dashboard card model and route targets.
2. Split layperson task navigation from advanced operations in the existing workspace.
3. Add the Docket lane with overview and document inventory backed by existing packaged docket/operator dashboard data.
4. Add selected-document panel, labels, and annotations as persisted workspace records.
5. Add scoped document chat with visible grounding, router path, citation chips, and save actions.
6. Add Analysis subsections for timeline, knowledge graph, deontic logic analyzer, legal/caselaw links, and contradiction candidates.
7. Add Playwright coverage for entry card routing, docket document selection, label creation, annotation creation, scoped chat, answer save, and Review/Draft handoff.
8. Fix router review configuration so screenshot review can run through the intended multimodal path instead of deterministic fallback.

### Additional Acceptance Tests

- Entry page shows the four top-level paths and each card links to the correct workspace.
- Docket lane shows at least one document with source, status, labels, and annotation count.
- Selecting a docket document updates the source panel and chat scope banner.
- User can add a label and see it persist on the document.
- User can add an annotation and see it persist on the document/page.
- User can ask a scoped document question and receive an answer with router path and source/citation state.
- User can save a chat answer as an annotation or evidence task.
- Review or Draft can see the saved docket item as source support.
- Router screenshot review either uses the configured multimodal backend successfully or reports the provider/config mismatch as a first-class warning in the artifact.

## Corrected Router Review Addendum: Direct Multimodal Findings

Date: 2026-04-25

This pass reused the same Playwright screenshots and ran two follow-up reviews:

- Configured backend review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260425/router-review-backend-codex.json`
- Direct multimodal router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260425/direct-multimodal-codex-review.json`

The configured backend review used `--backend-id llm-router-codex`, resolving to `codex_cli / gpt-5.3-codex-spark`. It produced useful page-level metadata findings, but the selected page-review path reported limited access to the screenshot pixels. The direct `MultimodalRouterBackend` call with `provider=codex_cli` and screenshot `image_paths` succeeded, which means the higher-level UI review wrapper should keep capable Codex multimodal providers on the image-path review path and make provider/config mismatches visible when a run falls back to screenshot metadata.

### Direct Multimodal Assessment

The direct multimodal review rated the current experience as high risk for layperson legal use in its current form. The workflow intent is strong, but critical legal-safety behavior is not visible enough, system internals are too prominent, and docket/document analysis is not yet integrated into the primary path.

Highest-priority findings:

- Hide internal identifiers in layperson mode. The homepage currently exposes `did:key:...` and `MCP TOOLS 31`, which are not meaningful first-use signals for non-lawyers. Replace them with plain status labels such as `Session saved` and `Tools connected`, and move technical details into Operations.
- Add legal-safety framing before drafting. The primary entry actions do not visibly explain that the tool organizes facts and drafts documents but does not provide legal advice. Add a persistent safety banner and require acknowledgment before first draft generation.
- Translate gate language into concrete proof tasks. Terms like `NEEDS_CORROBORATION`, `canonical gate workspace-gate-v1`, and `release gate is not passing yet` should become specific checklist items, for example `Missing corroboration for employer knowledge` with a direct action to attach a dated message or witness statement.
- Compress intake into a progressive denoising interview. The current intake screen shows many adjacent prompt cards and long guidance blocks. Convert it to one question cluster at a time, with autosave, uncertainty capture, and a short `why this matters` note.
- Require evidence provenance and source-quality metadata. Evidence items should capture source, date, who provided it, original file/hash when available, authenticity confidence, and claim-element link.
- Add docket timeline and deadline management as a first-class lane. The screenshots show complaint-building stages but no clear docket events, response deadlines, service dates, or court calendar risk.
- Replace opaque numeric readiness scores with criteria chips. `10/100`-style scoring should become visible completion criteria tied to concrete missing facts, documents, or source support.
- Disabled actions need a reason and recovery path. A locked Builder or export action should say exactly what is missing and provide a one-click jump to the relevant intake, evidence, or review subsection.

### Revised Pre-Implementation Priority

The next implementation should start with safety and comprehension before adding deeper analysis screens:

1. Layperson mode cleanup: hide DID/MCP/gate-version strings, add simple session/tool status, add legal-safety banner, and move provider diagnostics into Operations.
2. Blocker-driven workflow: one global next-action panel, disabled-control reasons, and criteria-based readiness chips.
3. Plain-language gate translation: convert internal release/support states into proof tasks with examples of acceptable evidence.
4. Docket foundation: docket overview, document inventory, deadline/timeline panel, and selected-document source panel.
5. Citation-backed labels and annotations: controlled taxonomy, page/span source requirement, confidence/disputed flags, and visible annotation counts.
6. Grounded document chatbot: scoped modes, mandatory citations, retrieval trace, abstention when unsupported, and save-to-annotation/evidence-task actions.
7. Intake denoising: progressive interviewer, uncertainty handling, date conflict detection, deadline prompts, and handoff into the fact/evidence registry.
8. UI review plumbing: allow `codex_cli` multimodal review when the backend supports image inputs, default bundle review to bounded/single-page mode, and report provider/config mismatch as a visible artifact warning.

### Acceptance Tests Added From Multimodal Review

- Standard user homepage does not show DID strings, raw MCP tool counts, gate versions, backend IDs, or provider internals.
- First draft generation requires visible legal-safety acknowledgment.
- A failing Review gate names the missing proof element and provides an action button to collect the exact kind of evidence needed.
- Builder lock state explains the missing criterion and deep-links to the relevant workspace section.
- Docket workspace computes and displays response/deadline risk from filing/service dates.
- Evidence save requires source/provenance fields and claim-element linkage.
- Annotation creation requires a document, page or text span, label type, and confidence/disputed state.
- Chatbot refuses unsupported case-fact answers and says no indexed source supports the claim.
- Chatbot answers include document/page/span citations or intake field citations.
- Draft paragraphs can be inspected for source support and annotation labels before export.
- Playwright captures the layperson mode and Operations mode separately so technical controls do not leak into the primary user path.

## Refreshed Playwright And Multimodal Review: Page-Level Findings

Date: 2026-04-25

This pass captured the current layperson complaint and docket workflow with Playwright, then reviewed the selected screenshots through `codex_cli / gpt-5.3-codex` via the multimodal router page-review workflow.

Artifacts:

- Screenshots: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260425-refresh/screenshots/`
- Screenshot metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260425-refresh/screenshot-metadata.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260425-refresh/router-review.json`
- Prepared image diagnostics: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260425-refresh/router-review-codex-diagnostics/pages/prepared-images/`

The review selected five high-signal pages: dashboard hub, intake chat, workspace/docket, claim-support review, and document builder. All selected page reviews used `multimodal_router`; two lower-priority pages, workspace annotations and profile, were skipped by the configured page limit and should be recaptured after the first layout pass.

## April 26 Post-Slice-1 Screenshot Recheck

After the first dashboard hub alignment pass, a fresh Playwright run captured the layperson hub, Docket workspace, document chat, claim-support Review, and document Builder for a school-district due-process docket scenario.

Artifacts:

- Screenshots: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426/screenshots/`
- Screenshot metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426/screenshot-metadata.json`
- Hub/chat/review/builder router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426/router-review.json`
- Docket-only router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426/router-review-docket-only.json`

Both router reviews used page-level `multimodal_router` reviews through `codex_cli / gpt-5.3-codex`. The first run selected dashboard hub desktop/mobile, document chat, claim-support Review, and document Builder, but skipped the Docket screenshots under the page limit. A second Docket-only run reviewed Docket desktop and Docket mobile explicitly.

The post-Slice-1 finding is sharper than the April 25 review: the hub is now closer to a layperson-first entry point, but shell clarity still needs another repair pass before deep selected-document Docket work. The mobile Docket screenshot is a blocker: it renders as a small top-left content column with most of the viewport empty, and the router found no visible document list, selected-document panel, annotation/label controls, deadline status, or document-grounded Q&A entry point.

Planning consequence:

- Treat mobile Docket shell repair as the next prerequisite, before adding selected-document behavior.
- Docket mobile must become a full-width single-column workflow with one current task, a document-list or selected-document module above the fold, and persistent Ask, Label, Annotate, and Deadline actions.
- Docket desktop must shift from function cards/internal tooling to task verbs such as "Summarize selected filing", "Extract deadlines", "Label allegations", and "Ask about this document".
- Future screenshot review runs must include an explicit Docket-only router pass when the general page selector skips Docket.

### Updated Core Diagnosis

The backend package capabilities are broader than the current layperson UX communicates. The screenshots show intake, workspace evidence, docket review, annotations, claim-support review, document building, MCP tools, and router paths, but the UI presents them as many equal-weight controls instead of one guided complaint lifecycle.

The largest implementation risk is route fragmentation between the real application dashboard and the Playwright fixture server. The Python dashboard model already defines task-oriented paths and cards, but the Playwright-served `/dashboards` screenshot still appears as a raw internal dashboard index. The implementation must align both surfaces so tests and users see the same layperson-first hub.

### Highest-Priority Findings From The Router

- The dashboard hub is still a raw internal index in the tested surface. It needs four primary cards: Start Complaint, Continue Saved Complaint, Review Docket Or Response, and Profile.
- Duplicate or version-like dashboard links such as `Clean`, `Final`, `Improved`, and `Admin Dashboard Error` should be hidden from the default layperson view and moved into Advanced Operations.
- Intake chat has too many competing primary actions. The active stage should expose one dominant next action, with workspace/review/draft links demoted or gated.
- Intake lacks obvious document-grounded controls beside the composer. Add visible actions for Attach Document, Add Annotation, Cite Source, and Ask About Selected Document.
- Workspace/docket is functionally rich but visually overloaded. It needs a stage-gated task rail, one current task region, collapsible advanced panels, and stronger typography.
- Review and Builder expose draft/export controls before the user can see source grounding, prerequisites, or artifact differences clearly enough.
- Docket document annotation and chatbot pathways exist conceptually, but the entry points are not prominent enough for a layperson trying to analyze, label, and ask questions about docket documents.

### Implementation Sequencing And Ownership

The next coding pass should be split into narrow, verifiable layers. The goal is not to redesign every screen at once; it is to make the layperson path coherent enough that the Docket/document/chat work lands in a safe shell.

1. **Align the dashboard hub across real app and Playwright server.**
   - Primary files: `applications/dashboard_ui.py`, `playwright/server.js`, `tests/test_claim_support_review_template.py`, `tests/test_review_surface_site_playwright.py`, `playwright/tests/navigation.spec.js`.
   - Work: keep legacy IPFS/admin dashboards available, but move them behind Advanced Operations. The default `/dashboards` view should show goal cards first: start/resume complaint, respond to docket document, review documents, ask case assistant, and profile.
   - Acceptance: `/dashboards` and the Playwright fixture both show the same layperson-first hub and do not expose `Clean`, `Final`, admin error pages, or raw dashboard catalogs as first-screen choices.

2. **Create a layperson-safe shell contract.**
   - Primary files: `static/complaint_app_shell.js`, `static/complaint_app_shell.css`, `templates/index.html`.
   - Work: hide DID, MCP tool counts, provider names, gate versions, raw readiness scores, and queue internals from standard mode. Replace them with plain status, criteria chips, and one recovery action.
   - Acceptance: standard mode shows no raw DID/MCP/backend/gate strings, while Operations/Diagnostics still exposes them for maintainers.

3. **Add the legal-safety and blocker translation layer.**
   - Primary files: `templates/index.html`, `static/complaint_app_shell.js`, `templates/workspace.html`, `templates/document.html`, `templates/claim_support_review.html`.
   - Work: add plain legal-safety framing before draft generation, translate `NEEDS_CORROBORATION` and release-gate states into proof tasks, and attach disabled-action reasons with direct links.
   - Acceptance: a blocked Builder or export action names the missing proof item and jumps to the correct Intake, Evidence, Docket, Review, or Draft section.

4. **Make one Docket document trustworthy.**
   - Primary files: `templates/workspace.html`, `static/complaint_mcp_sdk.js`, `static/complaint_mcp_sdk.mjs`, `tests/test_workspace_template_contract.py`, `tests/test_docket_workspace_surface.py`, `playwright/tests/complaint-flow.spec.js`.
   - Work: canonical selected-document card, grouped labels, urgency/deadline block, plain readiness state, persistent label/annotation records, and mobile sticky primary action.
   - Acceptance: one document can be selected, labeled, annotated, checked for deadline risk, and revisited without duplicate cards or contradictory readiness.

5. **Ground document chat and save the result back to workflow.**
   - Primary files: `templates/chat.html`, `static/chat.js`, `applications/review_ui.py`, `playwright/tests/complaint-flow.spec.js`.
   - Work: persistent scope banner, source panel, citation chips, router path/confidence/source-support state, explicit Ask Question vs Save Answer actions.
   - Acceptance: a scoped answer either cites document/page/span support or abstains, and a saved answer updates Docket plus Review/Draft source support.

6. **Recapture screenshots and rerun multimodal page reviews.**
   - Primary files: `applications/ui_review.py`, `playwright/tests/complaint-flow.spec.js`, review artifacts under `artifacts/`.
   - Work: run bounded one-page-at-a-time reviews for dashboard hub, Docket desktop, Docket mobile, document chat, Review, and Builder.
   - Acceptance: router artifacts complete through `multimodal_router` or produce first-class fallback warnings; no silent hangs.

Implementation should begin with steps 1-3 before step 4. Docket/document analysis is the most valuable feature, but the screenshot reviews show that it should not be embedded into a shell that still looks like developer tooling.

### Refined Implementation Gates

Before adding more feature panels, the first implementation slice should satisfy these gates:

1. Single entry hub: `/dashboards` and the Playwright fixture `/dashboards` both render the same task-oriented hub with four primary cards, plain-language descriptions, and advanced/internal tools hidden by default.
2. Single next action: chat, workspace, review, and builder each show exactly one primary action for the current workflow stage.
3. Stage-gated navigation: downstream review, draft, export, and follow-up actions explain missing prerequisites and deep-link to the exact intake, evidence, docket, or review step that repairs the blocker.
4. Document-grounded controls: chat and docket surfaces expose Attach, Label, Annotate, Cite, Ask, and Save Answer controls in user language.
5. Docket source panel: selecting a docket document updates a visible source panel with document title, filing date, role, labels, annotations, citation status, and chatbot scope.
6. Evidence-first review: claim-support review promotes source snippets, confidence/provenance, and human-confirmed vs AI-suggested status before resolution/export actions.
7. Builder grounding: draft paragraphs can reveal linked evidence, annotations, docket documents, and unsupported claims before export.
8. Operations separation: DID, MCP tools, provider IDs, backend status, SDK playground, raw dashboard variants, and error pages are available only in an Advanced or Operations section.
9. Mobile Docket shell: at mobile width, the Docket workspace renders as one full-width column, not a narrow desktop grid fragment, and first paint shows a selected-document or document-list entry point plus Ask, Label, Annotate, and Deadline actions.
10. Docket review coverage: when a general multimodal page-review bundle skips Docket screenshots, run a separate Docket-only router review before approving selected-document implementation.

### Additional Playwright Acceptance Tests

- `/dashboards` shows the four layperson cards and does not show `Admin Dashboard Error`, duplicate dashboard variants, raw MCP counts, or DID strings in default mode.
- The Playwright fixture server and FastAPI dashboard route expose equivalent card labels and primary links.
- Chat shows one primary CTA and visible Attach, Annotate, Cite, and Ask About Selected Document controls near the composer.
- Review links from Chat are disabled or demoted until intake prerequisites are satisfied, with visible recovery text.
- Workspace/docket shows a single current task and a selected-document source panel when a docket item is chosen.
- Mobile workspace/docket uses a full-width single-column layout and does not leave the core Docket UI confined to a small top-left column with empty viewport space.
- Mobile workspace/docket shows document entry, Ask, Label, Annotate, and Deadline controls above the fold or within the first short scroll.
- Docket document selection updates chat scope and citation banner before asking the router a document question.
- Claim-support review displays evidence snippets and provenance before Execute Follow-Up or export controls become primary.
- Builder export labels explain artifact scope and require source-grounding visibility before final export.
- Mobile and desktop screenshots pass text-overlap, minimum hit-area, active-tab contrast, and no-card-nesting checks.

### First Slice Execution Contract

The first implementation slice should stop after the entry hub and shell cleanup unless the tests below are green. That gives the Docket work a stable landing surface instead of mixing route alignment, legal-safety copy, and document UX in one risky patch.

Existing coverage to preserve:

- `tests/test_claim_support_review_template.py::test_review_surface_serves_legacy_pages_with_operator_links` already checks the real FastAPI `/dashboards` hub for goal-oriented cards, hidden admin/error variants, package capability sections, workflow rails, and mobile action rail text.
- `tests/test_review_surface_site_playwright.py::test_review_surface_ipfs_dashboard_shells_render_all_registered_dashboards` and `test_review_surface_ipfs_dashboard_raw_routes_render_all_registered_dashboards` keep legacy dashboard shell/raw routes reachable after the default hub becomes layperson-first.
- `playwright/tests/complaint-flow.spec.js` already verifies the shared workspace hides Profile/Trace/Dashboards from primary navigation and keeps advanced navigation in a separate area.

New or tightened coverage for Slice 1:

- Add a Playwright fixture assertion for `/dashboards` served by `playwright/server.js`: the first screen shows Start Complaint, Continue Saved Complaint, Review Docket Or Response, Ask Case Assistant, and Profile; it does not show raw dashboard variants in the default card set.
- Add a FastAPI/Playwright parity assertion that `applications/dashboard_ui.py` and `playwright/server.js` expose equivalent primary card labels and hrefs.
- Tighten shell assertions so standard mode does not show raw DID strings, raw MCP tool counts, backend IDs, provider names, or gate-version strings outside Operations/Diagnostics.
- Add a disabled-action recovery assertion: a locked Builder/export action names the missing criterion and links to the appropriate repair surface.
- Add screenshot capture for the default dashboard hub at desktop and mobile viewports before Docket changes begin.

Suggested Slice 1 test commands:

- `pytest tests/test_claim_support_review_template.py::test_review_surface_serves_legacy_pages_with_operator_links`
- `pytest tests/test_review_surface_site_playwright.py::test_review_surface_ipfs_dashboard_shells_render_all_registered_dashboards tests/test_review_surface_site_playwright.py::test_review_surface_ipfs_dashboard_raw_routes_render_all_registered_dashboards`
- `npx playwright test playwright/tests/navigation.spec.js playwright/tests/complaint-flow.spec.js`

Definition of done for Slice 1:

- Real FastAPI `/dashboards` and Playwright fixture `/dashboards` both render a layperson-first hub.
- Legacy dashboard routes still render through `/dashboards/ipfs-datasets/{slug}` and `/dashboards/raw/ipfs-datasets/{slug}`.
- Standard layperson mode hides developer identifiers and raw routing/gate internals.
- The app shows one primary next action and at least one concrete recovery path when a downstream action is blocked.
- Fresh desktop/mobile screenshots are ready for the next multimodal page review.

Additional stop line before the selected-document Docket slice:

- The April 26 Docket-only router review must be treated as failing mobile readiness until a new Playwright capture shows a full-width mobile Docket workflow with document selection, annotation/labeling, deadline, and document-grounded question controls visible.
- The next review bundle should include both the general page-review artifact and a Docket-only artifact so a page-cap skip cannot hide Docket regressions.

## April 26 Mobile Docket Shell Repair Slice

Implementation artifacts:

- Final screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshots/04-workspace-docket-mobile-final-empty-state.png`
- Simplified locked-state screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshots/06-workspace-docket-mobile-locked-empty-state.png`
- Loaded-document screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshots/09-workspace-docket-mobile-loaded-document-final.png`
- Source-summary loaded-document screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshots/10-workspace-docket-mobile-source-summary-final.png`
- Final screenshot metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshot-metadata-final-empty-state.json`
- Locked-state screenshot metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshot-metadata-locked-empty-state.json`
- Loaded-document screenshot metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshot-metadata-loaded-document-final.json`
- Source-summary screenshot metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshot-metadata-source-summary-final.json`
- Router reviews:
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/router-review-mobile-shell-repair.json`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/router-review-mobile-action-strip.json`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/router-review-mobile-disabled-empty-state.json`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/router-review-mobile-loaded-document-final.json`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/router-review-mobile-source-summary-final.json`

Changes made:

- Added a current Docket task module above the longer load/status panels.
- Added a mobile action strip for Ask, Label, Annotate, and Deadline actions.
- Disabled the mobile and selected-document actions when no document is selected so empty-state controls do not imply invalid MCP calls.
- Reduced mobile Docket padding and forced the Docket panel/grid/action regions into a single-column mobile contract with no horizontal overflow.
- Made the empty selected-document action area static instead of sticky so it no longer overlays the empty preview.
- Simplified the mobile empty state by hiding duplicate lower action/status panels, hiding the verbose three-step readiness list, and replacing ambiguous disabled buttons with explicit "Locked" labels plus an unlock instruction.
- Simplified the loaded-document mobile state by hiding the load form after a document exists, keeping the top mobile action strip as the only mobile action area, making Ask visually primary, hiding duplicated selected-document chips, and capping the selected preview height.
- Replaced the mobile selected-document wall with one source-summary card and moved technical/router details into a collapsed `Technical document status` disclosure.

Verification:

- `pytest tests/test_workspace_template_contract.py::test_workspace_template_defines_mobile_docket_shell_contract`
- `npx playwright test playwright/tests/navigation.spec.js --grep 'workspace Docket shell stays full-width and actionable on mobile'`
- `npx playwright test playwright/tests/navigation.spec.js --grep 'workspace integrations stay usable on a narrow viewport|workspace Docket shell stays full-width and actionable on mobile'`
- `npx playwright test playwright/tests/navigation.spec.js --grep 'workspace Docket .* mobile'`
- `npx playwright test playwright/tests/complaint-flow.spec.js --grep 'workspace unifies intake, evidence, support review, draft editing, actor/critic audit, and MCP tool visibility'`

Residual router finding:

- The repaired screenshots fix the severe narrow-column/empty-viewport failure and make the core actions visible early. The loaded-document metadata confirms no horizontal overflow, a hidden mobile load form, a hidden duplicate lower action bar, a hidden desktop preview, and collapsed technical details. The loaded-document screenshot is substantially shorter, makes Ask primary, and uses one source-summary card for the selected document. However, the final multimodal router pass still reports a hard warning about density and unclear hierarchy, so the selected-document implementation gate should remain closed until the next slice moves Docket into a dedicated mobile-first route/section or removes the surrounding desktop stage/header chrome from the mobile capture.

Focused gate review:

- Gate review artifact: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/router-review-mobile-source-summary-gate-decision.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`
- Screenshot reviewed: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/screenshots/10-workspace-docket-mobile-source-summary-final.png`
- Prepared image: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-shell-repair/router-review-mobile-source-summary-gate-decision-codex-diagnostics/prepared-images/10-workspace-docket-mobile-source-summary-final.review.jpg`

Gate decision:

- Do not start selected-document behavior yet. The mobile shell is mechanically repaired, but the router still sees high risk that a layperson could ask, label, annotate, or mark a deadline against the wrong document because the selected-document state is not unmistakable near the primary actions.
- The router recommended a next slice with one persistent `Selected document` rail above the actions, one dominant `Ask About Selected Document` CTA, secondary Label/Annotate controls, and a lower-risk Deadline action with confirmation before any write.
- Treat the router's `src/features/...` implementation path suggestions as framework-agnostic component names. In this codebase, the implementation target remains `templates/workspace.html`, the browser MCP SDK path, `tests/test_workspace_template_contract.py`, and `playwright/tests/navigation.spec.js`.

Next implementation slice before deeper behavior:

- Add a mobile selected-document rail immediately above the Docket action strip with title, source, status, and deadline/readiness badge.
- In the empty state, make the same rail say `No document selected` and keep all document-scoped actions locked.
- Split mobile actions by risk: primary Ask, secondary Label/Annotate, tertiary Deadline with a confirmation state before any persisted deadline change.
- Standardize the selected-document status sentence to one user-facing state plus one next step, while keeping technical router/OCR/index state inside collapsed details.
- Add Playwright assertions that the selected-document rail is visible before action controls and that action controls inherit the same selected document name.

Selected-document rail implementation:

- Final screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-selected-rail/screenshots/03-workspace-docket-mobile-selected-rail-final.png`
- Final screenshot metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-selected-rail/screenshot-metadata-selected-rail-final.json`
- Final router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-selected-rail/router-review-mobile-selected-rail-final.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes made:

- Added a mobile `Selected document` rail above the Docket action strip.
- The rail now carries the selected title, source/type, compact review status, draft readiness, and deadline state.
- Added a high-emphasis chat scope chip: `Chat scope: <document title> only.`
- Converted the mobile action stack into ordered actions: Ask, Label, Annotate, Mark Deadline.
- Hid the duplicate selected-document title in the mobile selected-card and renamed the source card title to `Selected source summary`.
- Kept technical router/OCR/index detail collapsed and preserved the existing MCP SDK and router contracts.

Verification:

- `pytest tests/test_workspace_template_contract.py::test_workspace_template_defines_mobile_docket_shell_contract`
- `npx playwright test playwright/tests/navigation.spec.js --grep 'workspace Docket .* mobile'`

Final gate decision:

- Playwright confirms the final mobile rail state has no horizontal overflow, a rail height under 150px, the rail before actions, hidden duplicate selected-card title, ordered action labels, and a document-specific chat scope chip.
- The final multimodal router pass still does not clear the selected-document behavior gate. It reports that the mobile Docket view still reads as too compressed for lay legal use and specifically warns not to clip legal-critical metadata.
- Treat the next prerequisite as a larger mobile architecture slice: Docket should become a single-active mobile surface where the user sees either the document list or the selected-document workbench, with an explicit back/change-document control. Status, deadline, and review-readiness fields must wrap instead of being line-clamped.

Single-active mobile surface implementation:

- Final selected-surface screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-single-surface/screenshots/02-workspace-docket-mobile-single-active-final.png`
- Final selected-surface metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-single-surface/screenshot-metadata-single-active-final.json`
- Final selected-surface router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-single-surface/router-review-mobile-single-active-final.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes made:

- Added a mobile-only Docket view switch with `Back to Documents (n)` and `Viewing Selected`.
- Empty mobile Docket defaults to the document list, disables the selected view, and hides selected-document actions.
- Loaded mobile Docket defaults to the selected-document workbench, hides the document list, and keeps a clear path back to the document list.
- Selected mobile Docket now hides the broad stage banner and long intro copy so the selected rail and actions become the first meaningful task area.
- Legal-critical status/deadline text in the source summary is allowed to wrap instead of being line-clamped.
- Preserved the existing selected document id, MCP SDK calls, `llm_router` / `multimodal_router` handoff shape, and desktop Docket layout.

Verification:

- `pytest tests/test_workspace_template_contract.py::test_workspace_template_defines_mobile_docket_shell_contract`
- `npx playwright test playwright/tests/navigation.spec.js --grep 'workspace Docket .* mobile'`

Updated gate decision:

- Playwright confirms a single active mobile surface: in selected mode the document list is hidden, the stage banner is hidden, the selected workbench is visible, no horizontal overflow is present, and the switch state is explicit.
- The router now recognizes the intended single-active selected-document surface, but still does not clear persistent selected-document behavior. Remaining blockers are action-state clarity and progressive enablement: Label, Annotate, and Deadline need explicit pending/done/blocked states before they become real write actions.
- Next prerequisite before persistent selected-document writes: add a lightweight action-step state model and per-action helper copy derived from existing document metadata, without changing MCP contracts.

Mobile action-state implementation:

- Final screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-action-state/screenshots/02-workspace-docket-mobile-action-state-final.png`
- Final screenshot metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-action-state/screenshot-metadata-action-state-final.json`
- Final router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-action-state/router-review-mobile-action-state-final.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes made:

- Added mobile action-state rows for Ask, Label, Annotate, and Deadline.
- Rendered action-state labels as high-contrast chips: `Next`, `Needs review`, `Pending`, and `Blocked`.
- Kept Ask as the active first step, derived label/annotation state from existing metadata, and disabled Deadline when no response date/deadline exists.
- Added `aria-describedby` from the disabled Deadline button to its unblock helper: `enable after a response date is captured in Annotation`.
- Preserved MCP SDK, selected-document id, and `llm_router` / `multimodal_router` request shapes.

Verification:

- `pytest tests/test_workspace_template_contract.py::test_workspace_template_defines_mobile_docket_shell_contract`
- `npx playwright test playwright/tests/navigation.spec.js --grep 'workspace Docket .* mobile'`

Updated gate decision:

- Playwright confirms explicit action-state text, disabled Deadline semantics, and no horizontal overflow.
- The final router review still does not clear persistent selected-document writes. It says the surface is functionally close, but the next implementation should make the ordered action rail a single canonical stepper with one current step expanded and future steps collapsed or clearly secondary.
- Next prerequisite before real writes: convert the current action-state presentation into a canonical stepper and then implement the first persistent write path, likely Label, behind that stepper.

Mobile canonical stepper implementation:

- Final screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-stepper/screenshots/02-workspace-docket-mobile-stepper-final.png`
- Final screenshot metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-stepper/screenshot-metadata-stepper-final.json`
- Final router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-stepper/router-review-mobile-stepper-final.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes made:

- Converted the mobile selected-document action rail into explicit step cards.
- Marked Ask as the single current step with `aria-current="step"` and `data-step-state="current"`.
- Marked Label, Annotation, and Deadline as secondary/blocked steps with state attributes.
- Hid the extra current-task banner and action-note copy in selected mobile mode so the selected rail plus one stepper is the canonical mobile path.
- Preserved MCP SDK, router contracts, selected-document id flow, and desktop layout.

Verification:

- `pytest tests/test_workspace_template_contract.py::test_workspace_template_defines_mobile_docket_shell_contract`
- `npx playwright test playwright/tests/navigation.spec.js --grep 'workspace Docket .* mobile'`

Updated gate decision:

- Playwright confirms one current step, secondary future steps, no overflow, and hidden duplicate selected-mode framing.
- The final router review still does not clear persistent selected-document writes. It now asks for a stricter status vocabulary and stronger visual dominance for the current task card.
- Next prerequisite before the first real write path: normalize mobile step statuses to `Active`, `Ready`, `Waiting`, and `Blocked`, and visually promote the current step as the one dominant CTA.

Mobile stepper status and microcopy follow-up:

- Final screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-stepper-status/screenshots/04-workspace-docket-mobile-stepper-status-microcopy-final.png`
- Final screenshot metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-stepper-status/screenshot-metadata-stepper-status-microcopy-final.json`
- Final router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260426-mobile-stepper-status/router-review-mobile-stepper-status-microcopy-final.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes reviewed:

- Normalized internal mobile step states to `Active`, `Ready`, `Waiting`, and `Blocked`.
- Replaced the selected-mode toggle label with `Current context: Selected`, disabled it in selected mode, and kept `Back to Documents - 1 item` as the only active header navigation control.
- Shortened the primary Ask CTA to `Ask About Document`.
- Added explicit helper prefixes: `Next:`, `Pending:`, and `Blocked by:`.
- Preserved the existing selected-document id flow and `llm_router` / `multimodal_router` chat/action contract.

Updated gate decision:

- Playwright confirms the microcopy state, selected-document scope, disabled Deadline semantics, and no horizontal overflow.
- The router still holds the persistent-write gate. It says the action order is understandable, but the selected-context control still looks too button-like, the state words are still internal-facing, and the blocked/scope copy should be written as direct layperson instructions.
- Next prerequisite before implementation: make the header one true navigation control plus a read-only selected-document banner such as `Working on: Termination timeline email`; move the document count out of the Back button; map internal state enums to plain-language labels such as `Do this now`, `Available next`, `Waiting on prior step`, and `Cannot continue yet`; rewrite Deadline copy as `Add a response date in Step 3 to set a deadline`; and promote the chat scope helper to `Questions will apply only to this document.`

Mobile layperson stepper follow-up:

- Final polished screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-layperson-stepper/screenshots/03-workspace-docket-mobile-layperson-stepper-polished.png`
- Final polished metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-layperson-stepper/screenshot-metadata-layperson-stepper-polished.json`
- Final polished router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-layperson-stepper/router-review-mobile-layperson-stepper-polished.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes reviewed:

- Moved the selected context out of the active view-switch affordance and kept `Back to Documents` as the only visible header button in selected mode.
- Rendered `Working on: Termination timeline email` as static context with the document count in nearby metadata.
- Converted step-state copy to layperson action language: `Do this now`, `Waiting on prior step`, and `Cannot continue yet`.
- Disabled Step 2 and Step 3 while Step 1 is current, and kept Step 4 blocked until a response date is saved through Step 3.
- Removed duplicate numbering from action labels so the card header carries the step number and the button carries only the action.

Updated gate decision:

- Playwright confirms one header action, no horizontal overflow, selected-document chat scope, disabled Step 2/3/4 controls, and deterministic step order.
- The router still holds the persistent-write gate. It says the flow is close, but Step 1 uses two related intents (`Ask About Document` versus `Ask what this document changes`), disabled steps need explicit `Complete Step X to unlock` prerequisite lines, and card status chips should better align with the stepper.
- Next prerequisite before selected-document writes: normalize every step from one step config source (title, CTA, helper, lock reason, success text), make Step 1 use one intent such as `Ask What This Document Changes`, render explicit unlock lines for Steps 2-4, and then implement the first persistent write boundary behind that clarified gate.

Mobile explicit gate review:

- Screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-explicit-gates/screenshots/01-workspace-docket-mobile-explicit-gates.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-explicit-gates/screenshot-metadata-explicit-gates.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-explicit-gates/router-review-mobile-explicit-gates.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes reviewed:

- Changed Step 1 to `Start Document Chat`, with copy clarifying that chat opens before anything is saved.
- Added a visible Step 1 progression line: `Not started -> Chat started -> Ready to label`.
- Rendered Steps 2-4 as explicit disabled action rows with locked labels and `Complete Step X` unlock rules.
- Standardized top chips to `Step 1: Current`, `Step 2: Locked`, and `Step 4: Locked`.
- Promoted mobile Back navigation back to a 44px target so users do not feel trapped.

Updated gate decision:

- Playwright confirms the explicit gates, current/locked chips, scoped document chat CTA, and no horizontal overflow.
- The router still holds the persistent-write gate. It now asks for a structured completion contract rather than more visual reshuffling: Step 1 must say the exact completion criteria, the selected-document persistence boundary needs one concise status line such as `Nothing saved yet`, and locked rows should be compacted so the screen is not heavy.
- Next prerequisite before selected-document writes: define a step completion schema (`not_started`, `chat_started`, `ready_to_label`, `saved`) that maps existing MCP-backed state into UI copy; render one persistence status row under the active step; and reduce each locked row to one compact reason plus optional details.

Mobile ready-to-label control review:

- Screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-ready-label-control/screenshots/01-workspace-docket-mobile-ready-label-control.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-ready-label-control/screenshot-metadata-ready-label-control.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-ready-label-control/router-review-mobile-ready-label-control.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes reviewed:

- Added explicit Step 1 completion criteria: impact summary present plus user confirms ready to label.
- Added a disabled `Mark Ready To Label` control to expose the eventual first write boundary.
- Added `Save status: not saved yet` next to the active step.
- Rendered all four step chips in order: `Current` and `Locked`.
- Kept Step 2-4 disabled until Step 1 completion.

Updated gate decision:

- Playwright confirms the ready-to-label control, save-status row, all-step chip ordering, disabled Step 2-4 controls, and no horizontal overflow.
- The router still holds the persistent-write gate. It says the screen is close, but the first write should not begin until Step 1 has a real readiness checklist with pass/fail items and a more prominent write lifecycle chip (`idle`, `saving`, `saved`, `error`) bound to the `Mark Ready To Label` action.
- Next prerequisite before selected-document writes: add a checklist above `Mark Ready To Label`, enable that control only when checklist items pass, promote save status to a state chip near the button, and compact Steps 2-4 into informational locked rows until their MCP-backed unlock flags are true.

Mobile actionable checklist review:

- Screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-actionable-checklist/screenshots/01-workspace-docket-mobile-actionable-checklist.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-actionable-checklist/screenshot-metadata-actionable-checklist.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-actionable-checklist/router-review-mobile-actionable-checklist.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes reviewed:

- Added a visible Step 1 gate summary: `Requirements: 0 of 2 complete`.
- Converted the Step 1 checklist into actionable rows: `Open chat to create impact summary` and `Confirm ready to label after impact summary`.
- Promoted save state to `Save: idle - no server write yet`.
- Kept `Mark Ready To Label` disabled until the checklist state can unlock it.
- Preserved the existing MCP request flow and did not add selected-document write behavior.

Updated gate decision:

- Playwright confirms the actionable checklist, lifecycle save chip, ready-to-label control, locked Step 2-4 controls, and no horizontal overflow.
- The router still holds the persistent-write gate. It now says the UI contract exists, but the mobile layout is too dense and the later locked steps still compete with Step 1.
- Next prerequisite before writes: make Step 1 a focused mobile-first action panel with one primary CTA, explicit checklist rows, and adjacent save-state chip; collapse Steps 2-4 into compact locked accordions until eligible; keep the first MCP-backed write behind the `Mark Ready To Label` state machine.

Mobile focused Step 1 review:

- Initial focused screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-focused-step1/screenshots/01-workspace-docket-mobile-focused-step1.png`
- Initial focused metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-focused-step1/screenshot-metadata-focused-step1.json`
- Initial focused router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-focused-step1/router-review-mobile-focused-step1.json`
- Lock-refinement screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-focused-step1/screenshots/02-workspace-docket-mobile-focused-step1-lock-refinement.png`
- Lock-refinement metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-focused-step1/screenshot-metadata-focused-step1-lock-refinement.json`
- Lock-refinement router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-focused-step1/router-review-mobile-focused-step1-lock-refinement.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes reviewed:

- Promoted Step 1 into a focused mobile action panel with a single primary `Start Document Chat` CTA.
- Added a direct next-action line: `Next: ask at least one document-specific question`.
- Strengthened the scope badge to `Chatting about: Termination timeline email. Questions will apply only to this document.`
- Moved `Mark Ready To Label` and the save-state chip into one Step 1 footer row.
- Converted Steps 2-4 into compact locked rows; their write controls are hidden, their summaries use `Locked`, and locked summaries have no pointer interaction.
- Reworded save copy to a policy line: `No selected-document write until Step 1 passes.`

Updated gate decision:

- Playwright confirms no horizontal overflow, a visible selected document, a focused Step 1 action panel, hidden future write controls, and locked Step 2-4 rows with non-interactive headers.
- The router still holds the persistent-write gate, but the blocker is now a product-state contract rather than broad layout structure.
- Remaining prerequisite before the first persistent selected-document write: define one authoritative Step 1 state model that separates ephemeral document-chat progress from the first server-backed selected-document write. The UI should show a single ordered checklist with live pass/fail items, a disabled-button reason derived from the first unmet item, and explicit persistence mode such as `Local draft only until Mark Ready` versus `Ready confirmation saved`.
- Next implementation slice should start by adding that state model and Playwright network assertions that no selected-document write mutation occurs before Step 1 passes.

Mobile Step 1 state-contract review:

- Initial state-contract screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/screenshots/01-workspace-docket-mobile-step1-state-contract.png`
- Initial state-contract metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/screenshot-metadata-step1-state-contract.json`
- Initial state-contract router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/router-review-mobile-step1-state-contract.json`
- Visible-contract screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/screenshots/02-workspace-docket-mobile-step1-state-contract-visible.png`
- Visible-contract metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/screenshot-metadata-step1-state-contract-visible.json`
- Visible-contract router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/router-review-mobile-step1-state-contract-visible.json`
- Reduced-density screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/screenshots/03-workspace-docket-mobile-step1-state-contract-reduced.png`
- Reduced-density metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/screenshot-metadata-step1-state-contract-reduced.json`
- Reduced-density router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-state-contract/router-review-mobile-step1-state-contract-reduced.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes reviewed:

- Added `buildMobileDocketStep1State()` as the single derived state model for Step 1.
- Normalized Step 1 fields: `current_state`, `first_unmet`, `persistence_mode`, `selected_document_write_count`, and `canMarkReady`.
- Added a visible Step 1 state-contract block with `not_started`, `ask one document-specific question first`, `local_until_ready`, and `selected-document writes: 0`.
- Added a three-item checklist: ask one document question, create impact summary, confirm ready to label.
- Changed the primary CTA to `Open Chat And Ask First Question`.
- Added Playwright assertions for one visible Step 1 panel, no selected-document write requests before gate pass, persistence mode, hidden duplicate helper rows, and non-interactive locked rows.

Updated gate decision:

- Playwright confirms the state contract is present and auditable in DOM and screenshot metadata: one visible Step 1 panel, no horizontal overflow, `selected-document writes: 0`, and zero selected-document write requests before Step 1 passes.
- The router still holds the persistent-write gate on readability grounds. It says the state model is technically present, but the mobile screen remains dense and hard to scan for lay users.
- Remaining prerequisite before first persistent write: visually simplify Step 1 further so the first viewport has one compact progress sentence, one readable contract/checklist module, one primary CTA, and far less surrounding status/chip repetition. The top rail chips and locked-step rows should be visually downgraded or moved below the fold until Step 1 has passed.

Mobile Step 1 simplification review:

- Initial simplified screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshots/01-workspace-docket-mobile-step1-simplified.png`
- Initial simplified metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshot-metadata-step1-simplified.json`
- Initial simplified router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/router-review-mobile-step1-simplified.json`
- Copy-final screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshots/02-workspace-docket-mobile-step1-simplified-copy-final.png`
- Copy-final metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshot-metadata-step1-simplified-copy-final.json`
- Copy-final router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/router-review-mobile-step1-simplified-copy-final.json`
- Hierarchy-final screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshots/03-workspace-docket-mobile-step1-simplified-hierarchy-final.png`
- Hierarchy-final metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshot-metadata-step1-simplified-hierarchy-final.json`
- Hierarchy-final router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/router-review-mobile-step1-simplified-hierarchy-final.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes reviewed:

- Hid selected-rail step chips in mobile selected-document mode.
- Hid future locked step rows while Step 1 is current.
- Reduced Step 1 to one visible heading, one `Open Chat` CTA, one unlock sentence, one compact checklist/status token, and one write-count line.
- Hid blocked checklist rows until prerequisite progress makes them relevant.
- Normalized selected-document metadata to `Source: ... • Type: ...`.
- Added `aria-describedby` from `Mark Ready To Label` to the visible unmet-requirement reason.

Current gate decision:

- Playwright confirms one visible Step 1 panel, no horizontal overflow, zero visible future locked steps, hidden rail chips, zero visible blocked checklist rows, and zero selected-document write requests before the gate passes.
- The router still holds the first-write gate. It now describes the remaining work as presentation/state-mapping only and says the existing `ComplaintMcpClient` gating/events should remain unchanged.
- Remaining prerequisite before first persistent selected-document write: continue simplifying the Step 1 visual treatment so the disabled ready action feels like a guided next step rather than a blocked/dead control. The next pass should focus on flatter styling and a clearer enabled-after-chat progression state, not new MCP behavior.

Mobile Step 1 guided-ready follow-up:

- Guided-ready screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshots/04-workspace-docket-mobile-step1-guided-ready-final.png`
- Guided-ready metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshot-metadata-step1-guided-ready-final.json`
- Guided-ready router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/router-review-mobile-step1-guided-ready-final.json`
- Chat-only pre-gate screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshots/05-workspace-docket-mobile-step1-chat-only-final.png`
- Chat-only pre-gate metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/screenshot-metadata-step1-chat-only-final.json`
- Chat-only pre-gate router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-simplified/router-review-mobile-step1-chat-only-final.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes reviewed:

- Recast the pre-gate ready action as `Next After Chat: Mark Ready To Label`.
- Then hid the ready action entirely until it can become actionable, leaving `Open Chat` as the only visible pre-gate action.
- Kept the future ready affordance in DOM/state contract and preserved zero selected-document writes before Step 1 passes.
- Flattened the ready footer styling and kept the recovery message: `After you use Open Chat and ask one document question, Mark Ready To Label appears here.`

Current gate decision:

- Playwright confirms no horizontal overflow, one visible Step 1 panel, zero visible ready buttons pre-gate, zero visible future locked rows, and zero selected-document write requests.
- The router says the page is functionally coherent for pre-gate Step 1, but still too dense/status-heavy to clear the first-write gate.
- Remaining prerequisite before implementation: make the post-chat progression visually obvious without adding MCP behavior. The next review should show the state immediately after a document-chat question is recorded, with `Mark Ready To Label` visible and clearly enabled/disabled by the impact-summary state.

Mobile Step 1 post-chat visual-state review:

- Post-chat screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-post-chat/screenshots/01-workspace-docket-mobile-step1-post-chat.png`
- Post-chat metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-post-chat/screenshot-metadata-step1-post-chat.json`
- Post-chat router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-mobile-step1-post-chat/router-review-mobile-step1-post-chat.json`
- Strategy: `multimodal_router`
- Provider/model: `codex_cli / gpt-5.3-codex`

Changes reviewed:

- Simulated the state after one selected-document chat question: `current_state=chat_started`, first unmet item `create the impact summary from chat`, and `Document updates captured: 0`.
- Kept Step 1 current after the question; Step 2 and Step 3 remain locked until the ready confirmation is saved, not merely until chat starts.
- Made `Mark Ready To Label` visible post-chat with `data-ready-visibility=guided`, but disabled until the impact summary exists.
- Preserved the MCP write gate: Playwright metadata shows zero selected-document write requests and zero captured document updates in the simulated post-chat state.

Current gate decision:

- The router still holds the first-write gate. It agrees the MCP gating should remain unchanged, but says the post-chat mobile view is still too status-heavy and does not make the single unblock action obvious enough for lay users.
- Next prerequisite before wiring any selected-document write: after `question_count > 0` and `impact_summary` is missing, demote `Open Chat` to a secondary action, promote a primary `Generate Impact Summary` action, and collapse the scattered Done/Missing/Waiting/Persistence blocks into one compact three-step progress tracker: ask question done, generate impact summary required, confirm ready to label locked.
- Copy improvement before implementation: replace internal `Mark Ready To Label` phrasing in the disabled state with a clearer locked label such as `Locked: Generate chat impact summary first`, while preserving the eventual explicit confirmation text when the action becomes enabled.

Comprehensive pre-implementation review bundle:

- Mobile pre-chat screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-plan-before-implementation/screenshots/01-mobile-pre-chat-current.png`
- Mobile post-chat screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-plan-before-implementation/screenshots/02-mobile-post-chat-current.png`
- Desktop Docket screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-plan-before-implementation/screenshots/03-desktop-docket-current.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-plan-before-implementation/screenshot-metadata-plan-before-implementation.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-plan-before-implementation/router-review-plan-before-implementation.json`
- Strategy: `page_reviews` across three `multimodal_router` page reviews
- Provider/model: `codex_cli / gpt-5.3-codex`

Plan refinements from the bundle review:

- Keep the selected-document write gate closed. The router flags the current state as a warning, not implementation-ready, because users still must infer too much from repeated status blocks.
- Make one derived UI state drive both mobile and desktop: `questionAsked`, `impactSummaryReady`, `readyEligible`, `readySaved`, `writesCaptured`, and `persistenceMode`.
- Pre-chat mobile should show a compact progression row: `1 Ask document question -> 2 Generate impact summary -> 3 Confirm ready to label`, with Step 3 locked and no selected-document writes.
- Post-chat mobile must switch the primary CTA from `Open Chat` to `Generate Impact Summary` while keeping `Open Chat` secondary. This action may call the scoped chat/summary path, but must not call a selected-document write mutation.
- Replace fragmented `Done` / `Missing` / `Waiting` / `Persistence` boxes with one progress component that shows only the active blocker and one plain-language persistence line: `No document updates saved yet` or `Local draft only until Ready`.
- Add a sticky or near-CTA scope/safety pill: `Scoped to: Termination timeline email • Local draft only until Ready`.
- Desktop Docket needs the same gating vocabulary as mobile. Separate read-only actions such as review/chat from draft-affecting actions such as use-in-draft, label write, annotation write, or ready confirmation.
- Replace dense desktop status chips with a `Needs attention` blocker summary and one remediation action, while keeping full OCR/vector/KG/router diagnostics behind advanced details.

Updated acceptance checks before implementation:

- Pre-chat mobile screenshot shows selected-document scope adjacent to the primary `Open Chat` CTA.
- Post-chat mobile screenshot shows `Generate Impact Summary` as the only primary CTA, with `Open Chat` demoted.
- `Mark Ready To Label` remains hidden or explicitly disabled until `impactSummaryReady=true`.
- Playwright spies or resource checks confirm zero selected-document write requests before the ready gate passes.
- Desktop and mobile use the same blocker labels and do not present draft-affecting actions as equivalent to read-only review actions.

Broader workflow pre-implementation review:

- Mobile Evidence screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/screenshots/01-mobile-evidence-after-document.png`
- Mobile Docket post-chat screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/screenshots/02-mobile-docket-post-chat-gate.png`
- Mobile document-chat context screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/screenshots/03-mobile-document-chat-context.png`
- Desktop Review proof-map screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/screenshots/04-desktop-review-proof-map.png`
- Desktop Draft readiness/export screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/screenshots/05-desktop-draft-readiness-and-export.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/screenshot-metadata-broader-workflow-before-implementation.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-broader-workflow-before-implementation/router-review-broader-workflow-before-implementation.json`
- Strategy: `page_reviews`; the router selected Evidence, Docket, Chat, and Draft as the highest-signal pages and skipped Review in this pass.
- Provider/model: `codex_cli / gpt-5.3-codex`

Plan refinements from the broader bundle:

- Keep the first selected-document write, answer-save, label-save, and annotation-save behavior gated. The broader workflow still has mobile comprehension blockers before persistence is safe.
- Evidence must become a true mobile-first single-column step before Docket writes are introduced. The current compressed mobile Evidence view makes claim-element mapping and the difference between `Import Local Evidence` and `Save Evidence Item` too ambiguous.
- Fix the duplicate `EVIDENCE KIND` presentation before implementation. If the controls represent different data, rename them clearly, for example `Evidence Type` and `Source Type`; otherwise render one control from one source of truth.
- Evidence save should be visibly gated by required metadata and claim-element mapping. The plan should require inline validation and one primary save CTA before adding more document-state writes downstream.
- Docket Step 1 still needs the shared gate presenter from the previous review: one state object, one progress block, one primary action, and no duplicate warning text.
- Document-scoped Chat should open with the selected filing context first, not a generic route index or system dashboard. The first viewport should show the document name, source, prepared question, router/source-scope badge, and `Return to workspace`.
- Generic surfaces such as Profile, Results, Trace, SDK, and Dashboards belong behind an advanced/other surfaces disclosure for layperson document chat.
- Draft readiness should use one canonical verdict banner with blockers, required evidence, and one primary next action. Draft/export controls must not look equivalent when some actions are blocked or risky.

Additional acceptance checks before implementation:

- Mobile Evidence has no horizontal overflow, no duplicate `EVIDENCE KIND` labels, and a single primary save action.
- Saving evidence is blocked until the claim-element selector and required document metadata are present.
- Document-scoped Chat first viewport shows `Selected filing attached` with the document title/source and does not begin with a generic surface index.
- The Docket post-chat state shows one consolidated gate status and one summary-related primary CTA.
- Draft readiness/export shows one canonical gate verdict and does not render enabled-looking controls for blocked/risky actions.

Standalone surface pre-implementation review:

- Mobile Review before-load screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/01-mobile-review-before-load.png`
- Mobile Review loaded screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/02-mobile-review-loaded.png`
- Mobile Builder empty screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/03-mobile-document-builder-empty.png`
- Mobile Builder generated screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/04-mobile-document-builder-generated.png`
- Desktop Builder generated screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/05-desktop-document-builder-generated.png`
- Desktop Optimization Trace screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/06-desktop-optimization-trace.png`
- Desktop Editor Workshop screenshot: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshots/07-desktop-editor-workshop.png`
- Metadata: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/screenshot-metadata-standalone-surfaces-before-implementation.json`
- Router review: `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260427-standalone-surfaces-before-implementation/router-review-standalone-surfaces-before-implementation.json`
- Strategy: `page_reviews`; the router selected Builder empty/generated, Desktop Builder, and Optimization Trace as the highest-signal pages.
- Provider/model: `codex_cli / gpt-5.3-codex`

Plan refinements from standalone surfaces:

- Add an explicit `Guided` versus `Advanced` presentation mode before selected-document persistence. Layperson mode should expose Intake, Evidence, Review, Docket, Chat, and Draft; Trace, SDK, Editor Workshop, raw router settings, and optimization internals should live behind `Advanced tools`.
- Formal Complaint Builder should not be the default place where lay users manage docket-document facts. The plan should keep Docket document analysis/annotation as the source-support workflow and make Builder a later Draft step with one clear `Generate Draft` path.
- Mobile Builder needs a stepper before it can be a layperson-safe continuation: `Case facts -> Court details -> Review support -> Generate draft`. Hide output actions until generation succeeds.
- Advanced optimization fields such as router URL, timeout, JSON LLM config, IPFS trace, request IDs, and trace internals must be collapsed by default and role-gated.
- Builder empty states must be actionable: when no draft exists, show prerequisites and one primary `Generate Draft` CTA; after generation, promote the pleading preview and source/exhibit verification.
- Optimization Trace should be operator-only by default. If linked from layperson flows, it should open as a plain-language readiness summary with a single next action, not raw trace telemetry.
- The Docket implementation sequence remains gated behind the broader shell cleanup: Guided/Advanced split, mobile Evidence cleanup, document-scoped Chat first viewport, Docket gate presenter, then selected-document persistence.

Standalone acceptance checks before implementation:

- In layperson mode, mobile/global navigation hides Trace, SDK, Editor Workshop, Dashboards, router settings, and raw diagnostics behind `Advanced tools`.
- Mobile Builder idle state shows one primary CTA and does not show generated-output controls before a draft exists.
- Mobile Builder generated state shows the pleading preview and supporting exhibits above advanced settings.
- Optimization Trace is not presented as a normal next step for lay users; any link to it is labeled as advanced/operator diagnostics.
- Existing MCP/ComplaintMcpClient payloads remain unchanged; the mode split is presentation/routing only.

## Consolidated Implementation Readiness Roadmap

Date: 2026-04-27

The screenshot/router reviews now converge on one decision: do not start selected-document persistence yet. The next work should be a UI/state-readiness sequence that makes layperson navigation, evidence capture, document-scoped chat, and Docket readiness understandable before any new label, annotation, answer-save, or ready-confirmation mutation is wired.

Implementation order:

1. Guided versus Advanced shell split.
   - Default layperson mode exposes only Intake, Evidence, Review, Docket, Chat, and Draft.
   - Advanced tools contains Trace, SDK, Editor Workshop, Dashboards, raw router settings, raw JSON, model config, IPFS trace, and optimization telemetry.
   - Existing MCP/ComplaintMcpClient routes stay available; only default presentation and navigation weight change.

2. Mobile Evidence cleanup.
   - Convert Evidence to a single-column mobile flow with one primary save action.
   - Remove or rename duplicate `EVIDENCE KIND` controls.
   - Put claim-element mapping directly next to evidence save requirements.
   - Block save locally until required metadata and claim-element mapping are present.

3. Document-scoped Chat first viewport.
   - When opened from Docket, the first visible region must show selected filing title, source/type, prepared question, scope badge, and `Return to workspace`.
   - Generic navigation and diagnostics move below the selected-document chat context or behind advanced disclosure.
   - Asking and saving remain separate concepts: chat may draft an answer, but no annotation/label/write happens without an explicit later action.

4. Shared Docket gate presenter.
   - One derived UI state drives mobile and desktop: `questionAsked`, `impactSummaryReady`, `readyEligible`, `readySaved`, `writesCaptured`, and `persistenceMode`.
   - Pre-chat: primary CTA is `Open Chat`.
   - Post-chat without summary: primary CTA is `Generate Impact Summary`, with `Open Chat` demoted.
   - Summary ready: `Mark Ready To Label` becomes the explicit confirmation boundary.
   - Until that point, selected-document write count and resource requests must remain zero.

5. Draft/readiness affordance cleanup.
   - Draft and export surfaces show one canonical verdict banner with blockers and one primary next action.
   - Draft-affecting actions are visually distinct from read-only review/chat actions.
   - Builder is a later Draft step, not the default place to manage docket-document facts.

6. First selected-document persistence slice.
   - Only after the above pass should the app wire the first write: ready confirmation for the selected document.
   - Labels, annotations, answer-save, and deadline-save remain later slices behind the same state/persistence pattern.

Release gate for starting selected-document persistence:

- Mobile screenshots pass for Evidence, document-scoped Chat, Docket pre-chat, Docket post-chat, and Draft readiness.
- Router review no longer reports high-severity layperson comprehension blockers on the selected-document gate.
- Playwright confirms no selected-document write/resource request before `readyEligible=true`.
- Playwright confirms post-chat primary CTA is `Generate Impact Summary` and `Open Chat` is secondary.
- Playwright confirms advanced/operator surfaces are hidden behind `Advanced tools` in layperson mode.

First prerequisite implementation note:

- Started the Guided versus Advanced shell split for Builder, Review, and Chat.
- Primary navigation on these surfaces now keeps the guided path visible: Landing/Secure Intake, Workspace where available, Chat, Review, and Builder.
- Profile, Results, Trace, Editor Workshop, SDK, and Dashboards remain available through `Advanced tools` disclosures instead of appearing as equal-weight layperson next steps.
- Existing href/session wiring remains intact, including trace and builder/review handoffs; this is a presentation hierarchy change only.
- Selected-document persistence remains gated.

Second prerequisite implementation note:

- Completed the first mobile Evidence cleanup pass.
- The normal Evidence composer now uses clearer layperson labels: `Evidence Type` and `Claim Element This Supports`.
- Gmail and local import drawers now use distinct labels: `Imported Emails Support`, `Imported Items Support`, and `Imported Item Type`, avoiding the duplicate `Evidence Kind` presentation called out in the broader review.
- `Save Evidence Item` now sits inside the primary composer before optional Gmail/local import tools, with helper copy that tells the user to map the item to one claim element before using imports.
- Mobile Evidence CSS now explicitly collapses Evidence banners, decision cards, metrics, guidance, and form fields into a single-column flow.
- Screenshot artifact: `artifacts/mcp-dashboard-ui-review/evidence-mobile-cleanup-20260427/mobile-evidence-cleanup.png`
- Router review artifact: `artifacts/mcp-dashboard-ui-review/evidence-mobile-cleanup-20260427/router-review-evidence-mobile-cleanup.json`
- Selected-document persistence remains gated. The next prerequisite is document-scoped Chat first viewport cleanup.

Third prerequisite implementation note:

- Completed the document-scoped Chat first-viewport cleanup.
- Chat now normalizes Docket handoff payloads that provide root-level `title`, `source`, `document_type`, and `docket_item_id`, so selected filings are named reliably even without a nested `filing` object.
- When Chat is opened with a Docket/document `chat_context`, the generic shared app shell and primary nav are suppressed, and the first content card is `Selected filing attached`.
- The selected filing card shows title, source/type, router scope, prepared question, `Ask About This Filing`, `Return to workspace`, and a persistence warning that no label, annotation, deadline, or answer is saved until the user confirms it back in Docket.
- Generic intake Chat handoffs still keep their normal hero and shared shell behavior.
- Screenshot artifact: `artifacts/mcp-dashboard-ui-review/document-chat-first-viewport-20260427/mobile-document-chat-first-viewport.png`
- Router review artifact: `artifacts/mcp-dashboard-ui-review/document-chat-first-viewport-20260427/router-review-document-chat-first-viewport.json`
- Selected-document persistence remains gated. The next prerequisite is the shared Docket gate presenter.

Fourth prerequisite implementation note:

- Completed the first shared Docket gate presenter pass.
- `buildSharedDocketGatePresenter` now derives the selected-document gate from one Step 1 state object, and desktop/mobile views consume the same current state, first unmet item, ready eligibility, ready-saved flag, persistence mode, and selected-document write count.
- Desktop Docket now shows `Selected document gate` with the same phase sequence used on mobile: pre-chat `Open Chat`, post-chat `Generate Impact Summary` primary with `Open Chat` secondary, impact-ready `Mark Ready To Label`, and saved-ready confirmation.
- `Generate Impact Summary` currently drafts the impact summary locally and explicitly reports that no selected-document write has been sent.
- `Mark Ready To Label` remains a visible confirmation boundary, but persistence is intentionally gated; clicking it reports that no selected-document write has been sent.
- Mobile Docket still shows one current Step 1 panel and keeps label, annotation, and deadline controls locked until the gate state allows later slices.
- Screenshot artifacts: `artifacts/mcp-dashboard-ui-review/docket-gate-presenter-20260427/mobile-docket-gate-post-chat.png` and `artifacts/mcp-dashboard-ui-review/docket-gate-presenter-20260427/desktop-docket-gate-post-chat.png`
- Router review artifact: `artifacts/mcp-dashboard-ui-review/docket-gate-presenter-20260427/router-review-docket-gate-presenter.json`
- Selected-document persistence remains gated. The next prerequisite is Draft/readiness affordance cleanup before the first selected-document ready-confirmation write.

Fifth prerequisite implementation note:

- Completed the Draft/readiness affordance cleanup.
- The upper Draft gate is now a secondary summary (`data-gate-role="secondary-summary"`) instead of a competing authoritative banner.
- The lower Draft rail is now the primary `Canonical filing verdict` (`data-canonical-gate="primary"`) and owns the visible download state.
- The download group now has an explicit `data-download-state` boundary, a plain-language blocker note, and `aria-disabled` state on complaint file download buttons.
- Desktop and mobile screenshots both confirmed the intended blocked state: canonical gate `primary`, download state `blocked`, and blocker text explaining that support, party/court specificity, and the release gate still need work.
- Screenshot artifacts: `artifacts/mcp-dashboard-ui-review/draft-readiness-cleanup-20260427/desktop-draft-readiness.png` and `artifacts/mcp-dashboard-ui-review/draft-readiness-cleanup-20260427/mobile-draft-readiness.png`
- Router review artifact: `artifacts/mcp-dashboard-ui-review/draft-readiness-cleanup-20260427/draft-readiness-router-review.json`
- Router route repair: `provider=llm_router` and `model=multimodal_router` are now resolved as UI-review route aliases before backend calls. The refreshed artifact records `route_alias_resolved: true` and executes page reviews through `codex_cli / gpt-5.3-codex`.
- Follow-up Draft layout repair: the canonical verdict now renders first/full-width in the Draft action rail, action groups use responsive widths, mobile Draft action sections are forced to one column, and the large Draft editor is bounded instead of rendering a 980px blank panel.
- Viewport-scoped follow-up review narrowed the remaining Draft/readiness issues to hierarchy rather than layout: capability chips looked like conflicting peer statuses, the canonical verdict had several equal-weight actions, and packet export still looked primary while downloads were blocked.
- Follow-up hierarchy repair: the Draft verdict now uses explicit labels such as `Filing verdict: BLOCKED`, `Review open`, `Draft open`, and `Downloads blocked`; the canonical card has one `Fix now: ...` primary CTA; secondary Review/Evidence/CLI destinations are visually demoted; packet export stays secondary while the filing verdict is blocked; and formal pleading checks render concrete blocker lines instead of a placeholder.
- Selected-document persistence remains gated. The next implementation slice should rerun the scoped screenshot/router review and only then consider the first selected-document ready-confirmation write with network assertions.

Sixth prerequisite review note:

- Reviewed the Dashboard Hub prerequisite pass with fresh desktop/mobile screenshots and `llm_router` / `multimodal_router` route aliases.
- Screenshot artifacts: `artifacts/mcp-dashboard-ui-review/dashboard-hub-prerequisites-20260428/dashboard-hub-desktop.png` and `artifacts/mcp-dashboard-ui-review/dashboard-hub-prerequisites-20260428/dashboard-hub-mobile.png`
- Router review artifact: `artifacts/mcp-dashboard-ui-review/dashboard-hub-prerequisites-20260428/dashboard-hub-router-review.json`
- Implemented a partial hierarchy cleanup in the JS stub dashboard hub: one primary `Start intake questions` CTA, returning-user links separated from the primary action card, clearer saved-work/docket labels, and prerequisite status lines instead of dense chips.
- Playwright navigation coverage confirms the hub remains reachable, advanced dashboard routes remain available, and Builder Trace navigation opens through the advanced disclosure.
- The router did not clear the dashboard gate. Remaining high findings ask for a more structural decision: either use one unified Intake/Evidence/Review card system with explicit current/available/locked states, or keep intake separate while making resume/docket/profile controls visually secondary but unmistakably interactive with real eligibility state.
- Selected-document persistence remains gated. Do not start the first selected-document write until the dashboard entry model and the Draft/readiness gate both clear scoped screenshot review.

Dashboard gate continuation:

- Converted the JS stub dashboard toward a Step 1/2/3 complaint model and added explicit waiting/disabled guards for later steps.
- Refreshed `dashboard-hub-desktop.png`, `dashboard-hub-mobile.png`, and `dashboard-hub-router-review.json`.
- Playwright navigation checks pass after the change, including the dashboard hub and mounted dashboard routes.
- The router still does not clear the dashboard gate. Remaining high findings now focus on consistency rather than missing structure: the top stepper and lower cards need one shared state vocabulary and render model; the mobile Step 1 row should be the clear primary button; Evidence and Review should be unmistakably disabled with one unlock reason.
- Selected-document persistence remains gated.

Dashboard gate continuation, second review:

- Reworked the JS stub hub again around a shared Step 1/2/3 state object: Intake is `Current`, Evidence and Review are `Locked`, the top stepper and lower cards consume the same labels, and locked cards use a non-navigation status affordance with one unlock reason.
- Refreshed the desktop/mobile screenshots and reran the alias-resolved review at `artifacts/mcp-dashboard-ui-review/dashboard-hub-prerequisites-20260428/dashboard-hub-router-review.json`.
- Router path: `page_reviews`, provider `codex_cli`, model `gpt-5.3-codex`, requested aliases `llm_router` / `multimodal_router`, `route_alias_resolved: true`, selected both dashboard screenshots, skipped `0`.
- Verification: `npx playwright test playwright/tests/navigation.spec.js --grep 'dashboard|document and dashboard'` passes.
- The router still does not clear the dashboard gate. Current high findings are all presentation/state-signaling issues: locked cards still read too active, prerequisite text is duplicated, and mobile Step 2 lock affordance is weak.
- Planning decision: do not start selected-document persistence. The next prerequisite should simplify the hub into one visible first-action panel and one lower-priority locked-state explanation, with no duplicate Step 1 card and no active-looking locked controls.

Dashboard gate continuation, third review:

- Reworked the hub into one explicit Intake/Evidence/Review stage-control grid. Intake is the only enabled action (`Start Intake Questions`); Evidence and Review render as disabled stage controls with inline `To unlock:` text and disabled button labels.
- Tightened the mobile spacing so the disabled controls take less vertical room, and fixed the desktop Intake text squeeze by stacking the active card content.
- Refreshed `dashboard-hub-desktop.png`, `dashboard-hub-mobile.png`, and `dashboard-hub-router-review.json` in `artifacts/mcp-dashboard-ui-review/dashboard-hub-prerequisites-20260428/`.
- Router path: `page_reviews`, provider `codex_cli`, model `gpt-5.3-codex`, aliases `llm_router` / `multimodal_router`, `route_alias_resolved: true`, selected both dashboard screenshots, skipped `0`.
- Verification: `npx playwright test playwright/tests/navigation.spec.js --grep 'dashboard|document and dashboard'` passes.
- The router still does not clear the dashboard gate. Remaining high findings: disabled Evidence/Review controls still read too much like primary actions, the Profile section creates large empty whitespace, and mobile still needs clearer unlock timing/action guidance.
- Selected-document persistence remains gated. The next prerequisite should demote or collapse Profile on the hub and redesign locked stages as secondary progress/status rows that still expose explicit disabled semantics.

April 28 selected-document and Docket Chat review addendum:

- Reviewed the broader Dashboard, Docket, selected-document, readiness, and Docket-scoped Chat states with Playwright screenshots routed through the `multimodal_router` alias. The alias resolved to `page_reviews` through `codex_cli / gpt-5.3-codex`, with `route_alias_resolved: true`.
- Review artifacts:
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260428-plan-review/router-review-general.json`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260428-plan-review/router-review-docket-only.json`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260428-plan-review-v2/router-review-selected-document-states.json`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260428-plan-review-v2/router-review-impact-summary-ready.json`
  - `artifacts/mcp-dashboard-ui-review/layperson-docket-chatbot-20260428-plan-review-v3/router-review-docket-chat-before-after.json`
- The newest router passes agree with the prior dashboard gate: do not start selected-document persistence yet. The blocker is no longer whether the feature exists; it is whether lay users can reliably tell what document is in scope, what state the document is in, what router/fallback state occurred, and what will be written back to the docket.

Refined prerequisite order before the first selected-document write:

1. Dashboard gate simplification.
   - Render one obvious `Start intake questions` action as the first visible next step.
   - Use one compact stage-status strip for Intake, Evidence, and Review.
   - Present Evidence and Review as clearly locked or waiting, with one unlock reason and no active-looking locked controls.

2. Docket selected-document state machine.
   - Drive desktop and mobile Docket from one canonical readiness state.
   - Remove contradictory combinations such as `Mark Ready To Label is ready` next to `Missing: Confirm ready to label`.
   - Do not show `Ready For Draft` while router checks, OCR checks, citation checks, or human review are incomplete. Use `Conditionally ready` or `Needs review before draft` instead.

3. Citation and annotation preflight.
   - Block `Mark Ready` until the selected document has at least one source-supported item: cited excerpt, annotation, or citation-grounded answer.
   - Show the preflight result next to the confirmation action, not in a separate diagnostic region.
   - Distinguish document labeling readiness from filing/export readiness.

4. Docket-scoped Chat contract.
   - Keep a persistent, high-contrast scope banner above the composer before send, during loading, after failure, and after answer: `Answering from: [selected document title]`.
   - Show source/type, selected-document id or docket item id, and the prepared question near the composer.
   - Render answer cards with citation chips or an explicit `No document citation found` state.
   - Add visible router states: `Analyzing selected filing`, `Router retrying`, `Fallback model used`, and actionable failure controls for retry, ask generally, return to Docket, and reselect document.

5. Save-back model.
   - Saving an answer must require an explicit destination: label, annotation, deadline, issue, evidence task, or draft note.
   - After save, Docket must show the selected document id/title, destination, and timestamp.
   - Uncited answers may be saved only as general notes, not as grounded evidence or citation-backed labels.

6. Only then first selected-document ready-confirmation write.
   - The first persistence slice should be ready confirmation only.
   - Label, annotation, answer-save, deadline-save, and draft-note writes remain separate later slices behind the same state and router-failure patterns.

Stop lines for implementation:

- No `Ready For Draft` state may appear while any underlying OCR, router, citation, or review checks are unchecked.
- No readiness card may show both ready and missing/blocked copy at the same time.
- No chat answer may offer a grounded-evidence save unless selected document, citation/source status, destination, and persistence status are all visible.
- No label, annotation, deadline, answer-save, or draft-note persistence should ship until router timeout/failure states have retry and fallback controls.

Playwright acceptance for the next implementation pass:

- Assert that ready and missing readiness messages never coexist on the selected-document gate.
- Assert that `Mark Ready` is disabled until citation, annotation, or source-supported answer preflight passes.
- Assert that the selected-document scope banner remains visible before send, during loading, after router failure, and after answer.
- Simulate router timeout/failure and assert retry, ask generally, return to Docket, and reselect controls.
- Assert that a cited answer can be saved to an explicit destination and that an uncited answer cannot be saved as grounded evidence.
- Assert that save-back updates the Docket selected-document status with document id/title and timestamp.
- Assert that mobile Docket Chat keeps the selected document and composer in the same first working viewport.
- Assert that desktop Docket does not show `Ready For Draft` when OCR, router, citation, or review checks are incomplete.

Definition of done for plan clearance:

- Fresh screenshots cover mobile Docket pre-chat, mobile Docket chat-started, mobile impact-summary-ready, desktop selected-document Docket, and desktop/mobile Docket Chat before-send, failure, cited-answer, and saved states.
- Router review reports no high-severity findings for contradictory readiness, hidden document scope, missing router recovery, or missing citation gating.
- Selected-document persistence remains closed until that screenshot/router review clears.
