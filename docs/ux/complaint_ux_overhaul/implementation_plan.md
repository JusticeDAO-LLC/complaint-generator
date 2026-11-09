# Screenshot-led complaint UX improvement plan

This separately scoped campaign has9goals,22subgoals and68implementation tasks. It starts from6f27c60c and preserves the completed GUI60 program. The specification, generated Native formal plan and open task board use a new namespace; ingestion and startup are not task completion.

The primary design contract is [experience_contract.md](experience_contract.md). [Thirteen actual baseline screenshots](baseline/screenshot_manifest.json) include desktop/mobile owner, mediator, evidence, draft, case, lawyer, correspondence and admin views. [Screenshot findings](screenshot_driven_findings.json) drive the work rather than mockups. The [mediator audit](mediator_hook_source_audit.json) distinguishes source presence from real activation.

## Outcomes

- A case-centred responsive shared shell with chat-only, split and rich workspace modes over one encrypted session.
- Adaptive explainable questions and corrections that update factual assertions while legal requirements remain source-derived.
- A usable evidence library, safe previews, actual versioned comments/classifiers/annotations and explicit fact/requirement links.
- Evidence-cited drafting and human review with readable conflict, source, key and uncertainty states.
- A typed AI/human correspondence timeline, private case messages, reviewer queue and appropriately scoped admin tools.
- Actual Grok4.7/router, Dataset KG/legal/formal and Kit private-durability integrations through measured mediator hooks.

## Baseline findings

- Real authentication and inquiry can work while the visible header still reports No case selected/access denied.
- The oversized hero and developer navigation compete with the actual next task.
- Raw inquiry/objective/source identifiers and diagnostic prose dominate questions, especially on mobile.
- Evidence editing is buried below long guidance and lacks a compact library/detail model.
- Placeholder annotation controls and fixed retaliation labels need actual case-scoped persisted implementations.
- Correspondence exposes manual IDs/polling details rather than clear people and actions.
- Admin mobile tables clip and the sign-in credential stays populated; admin case-content access must remain separately granted.

## Goal and dependency map

| Goal | Subgoals | Tasks |
| --- | --- | --- |
| Establish the measured baseline and a calm case-centred design | Real screenshots and SDK capability baseline; Accessible design system and shared case shell | CIMP-UX-01, CIMP-UX-02, CIMP-UX-03, CIMP-UX-04, CIMP-UX-05, CIMP-UX-06 |
| Unify AI conversation and structured complaint refinement | One canonical interview across chat and rich modes; Explainable questions, corrections, and finite stopping | CIMP-UX-07, CIMP-UX-08, CIMP-UX-09, CIMP-UX-10, CIMP-UX-11, CIMP-UX-12 |
| Make evidence understandable, annotatable, and traceable | Private evidence intake and trustworthy previews; Versioned comments, labels, and classifiers; Explicit evidence-to-fact and evidence-to-requirement links | CIMP-UX-13, CIMP-UX-14, CIMP-UX-15, CIMP-UX-16, CIMP-UX-17, CIMP-UX-18, CIMP-UX-19, CIMP-UX-20, CIMP-UX-21, CIMP-UX-22 |
| Keep factual and legal graphs distinct and grounded | User-assertion graph and contradictions; Admitted legal sources and dependency requirements; Honest formal analysis and proof states | CIMP-UX-23, CIMP-UX-24, CIMP-UX-25, CIMP-UX-26, CIMP-UX-27, CIMP-UX-28, CIMP-UX-29 |
| Keep drafting connected to evidence and review | Cited complaint outline and versioned editor; Human review and unresolved drafting blockers | CIMP-UX-30, CIMP-UX-31, CIMP-UX-32, CIMP-UX-33, CIMP-UX-34 |
| Make AI and human correspondence a coherent case workflow | Typed case timeline, conversations, and inbox; Assigned-lawyer review and owner-controlled collaboration | CIMP-UX-35, CIMP-UX-36, CIMP-UX-37, CIMP-UX-38, CIMP-UX-39, CIMP-UX-40, CIMP-UX-41 |
| Provide appropriate admin tools and usable failure states | Operational administration with explicit content authorization; Responsive, accessible, understandable interfaces | CIMP-UX-42, CIMP-UX-43, CIMP-UX-44, CIMP-UX-45, CIMP-UX-46, CIMP-UX-47, CIMP-UX-48 |
| Activate grounded mediator hooks with explicit SDK ownership | Grok 4.7 routing and consent-bound results; Measured coverage of all thirteen mediator hooks; Encrypted Kit persistence and recovery | CIMP-UX-49, CIMP-UX-50, CIMP-UX-51, CIMP-UX-52, CIMP-UX-53, CIMP-UX-54, CIMP-UX-55, CIMP-UX-56, CIMP-UX-57, CIMP-UX-58, CIMP-UX-59, CIMP-UX-60 |
| Prove the experience and sustain unattended delivery | Screenshot and interaction regression coverage; Owned startup, progress, and finite recovery; Fresh acceptance, operator handoff, and authenticated completion | CIMP-UX-61, CIMP-UX-62, CIMP-UX-63, CIMP-UX-64, CIMP-UX-65, CIMP-UX-66, CIMP-UX-67, CIMP-UX-68 |

## Task details

Each task declares Native DAG dependencies, exact product/test outputs, positive and negative acceptance and one focused validation command. The complete machine-readable source is [the specification](../../task_boards/complaint_gui_ux_overhaul_spec.json).

### CIMP-UX-01: Verify the screenshot baseline through real user and staff flows

Depends on: none.

- Run the inherited pinned Chromium/ASGI capability against synthetic encrypted cases; verify actual owner, lawyer, message, and admin routes, not a mockApi or a diagnostic-only mounted component.
- Bind baseline screenshots to source/runtime/viewport/actor/state and assert real DOM/response semantics and owned cleanup. Characterize the measured stale No case selected/access denied header separately from the genuinely authenticated working inquiry; record that defect rather than falsely asserting baseline UX success. Include desktop and mobile.

Outputs: `tests/test_cimp_ux_01.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_01.py`.

### CIMP-UX-02: Inventory current SDK APIs, mediator owners, and compatibility gaps

Depends on: CIMP-UX-01.

- Observe the actual pinned A/Data/Kit module origins, Git revisions, callable signatures, and all thirteen mediator hooks; distinguish present, callable, active, unavailable, and unsupported.
- Run bounded real adapter probes with synthetic sources and actual private storage; registered disabled operations must remain unavailable until their real dependency/effect path is qualified. Record a deliberate compatibility decision for newer upstream capabilities without floating pins.

Outputs: `docs/ux/complaint_ux_overhaul/sdk_hook_inventory.json`, `tests/test_cimp_ux_02.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_02.py`.

### CIMP-UX-03: Introduce accessible visual tokens, typography, spacing, and components

Depends on: CIMP-UX-01.

- Render the real workspace with a coherent spacing/type/colour system and visible hierarchy; validate computed styles, normal/large-text contrast, focus visibility, and readable error/locked states.
- Use the reviewed screenshot findings and experience contract; preserve actual forms, case authorization, privacy defaults, and functionality while introducing reusable components.

Outputs: `static/complaint_experience_tokens.css`, `templates/workspace.html`, `tests/test_cimp_ux_03.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_03.py`.

### CIMP-UX-04: Build a shared case-centred application shell

Depends on: CIMP-UX-02, CIMP-UX-03.

- Show the selected case, authenticated actor, privacy/lock state, workflow stage, and one primary next action consistently across owner and assigned-reviewer views.
- Provide Overview, Mediator, Evidence, Facts and timeline, Legal requirements, Draft, and Team/messages navigation; hide CLI/MCP/debug panels from ordinary task flows without weakening server policy.

Outputs: `static/complaint_case_shell.js`, `static/complaint_case_shell.css`, `templates/workspace.html`, `templates/cases.html`, `tests/test_cimp_ux_04.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_04.py`.

### CIMP-UX-05: Make navigation and case switching responsive and state-safe

Depends on: CIMP-UX-04.

- Navigate desktop, tablet, and mobile views without lost canonical interview state, unexpected duplicate sessions, or horizontal clipping at 320px.
- Switch cases through the actual case catalog; cancel old requests and clear rendered plaintext on logout, case/actor changes, key lock, and revocation.

Outputs: `static/complaint_case_shell.js`, `static/complaint_case_shell.css`, `templates/cases.html`, `tests/test_cimp_ux_05.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_05.py`.

### CIMP-UX-06: Present first-run, authentication, unlock, and cold-resume entry flows

Depends on: CIMP-UX-05.

- A new user can identify how to begin a complaint; an existing user can select and unlock the correct case and resume the actual pending question.
- Missing keys, denied sessions, and unavailable capabilities are explicit, with no empty-case replacement, ready badge, browser-cache reconstruction, or hidden consent.

Outputs: `templates/workspace.html`, `templates/cases.html`, `static/complaint_case_shell.js`, `tests/test_cimp_ux_06.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_06.py`.

### CIMP-UX-07: Unify chat, split view, and rich workspace modes

Depends on: CIMP-UX-06.

- Switch chat-only, chat-plus-context, and full workspace modes while preserving the exact encrypted session, inquiry ID/revision, evidence selection, and current draft.
- Use the existing actual workspace/MCP handlers and SDK transport; do not introduce a second client-only interview or localStorage complaint store.

Outputs: `templates/workspace.html`, `static/complaint_case_shell.js`, `static/complaint_mcp_sdk.js`, `static/complaint_mcp_sdk.mjs`, `tests/test_cimp_ux_07.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_07.py`.

### CIMP-UX-08: Render the mediator conversation with clear provenance and actions

Depends on: CIMP-UX-07.

- Render user statements, AI questions, model suggestions, and system outcomes as distinct accessible message types, with bounded pending/cancel/retry states.
- Show relevant case/evidence context and useful next actions without exposing prompts, credentials, private invocation internals, or technical actor IDs as primary UX.

Outputs: `templates/workspace.html`, `static/complaint_conversation.js`, `static/complaint_conversation.css`, `tests/test_cimp_ux_08.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_08.py`.

### CIMP-UX-09: Build inquiry cards with Why, unknown, defer, and supporting context

Depends on: CIMP-UX-08.

- Display the server-issued current question and revision, why it matters, linked factual gaps/legal requirements, and allowed answer/unknown/defer actions.
- Why/status actions never save an answer, and the UI cannot substitute a fixed generic intake form for the shared adaptive interview.

Outputs: `templates/workspace.html`, `static/complaint_conversation.js`, `tests/test_cimp_ux_09.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_09.py`.

### CIMP-UX-10: Make answers and corrections update the canonical graphs safely

Depends on: CIMP-UX-09.

- Submit actual question ID and expected revision; an accepted answer/correction updates the persisted factual graph and affected support projection exactly once.
- Stale/conflicting replies remain readable JSON, preserve the current pending inquiry and encrypted head, and cannot repaint a newer case or overwrite admitted legal requirements.

Outputs: `static/complaint_conversation.js`, `static/complaint_mcp_sdk.js`, `applications/complaint_workspace.py`, `tests/test_cimp_ux_10.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_10.py`.

### CIMP-UX-11: Expose finite stopping, unresolved questions, pause, and resume

Depends on: CIMP-UX-10.

- Distinguish no actionable question, user pause, cancellation, cap, saturation, unavailable source/provider, and legal/evidentiary gaps with honest next actions.
- Cold resume returns the same encrypted question/state; no-more-questions, filled forms, or completed software tasks are never labelled legal sufficiency.

Outputs: `static/complaint_conversation.js`, `templates/workspace.html`, `tests/test_cimp_ux_11.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_11.py`.

### CIMP-UX-12: Make privacy and Grok processing consent understandable

Depends on: CIMP-UX-08, CIMP-UX-11.

- Local/private processing remains the default; explain which minimized case data would leave the machine for Grok 4.7 and require actual persisted case/purpose consent.
- Unlock, staff roles, development-provider authorization, or omitted flags cannot create consent; revocation/cancellation is rechecked before late results are displayed or admitted.

Outputs: `templates/workspace.html`, `static/complaint_conversation.js`, `applications/case_consent_api.py`, `tests/test_cimp_ux_12.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_12.py`.

### CIMP-UX-13: Define a case-scoped evidence catalog and lifecycle

Depends on: CIMP-UX-02, CIMP-UX-06.

- Provide real encrypted case/actor-scoped evidence identifiers, artifact versions, source/original filenames, integrity and ingestion status through authorized handlers.
- Separate received, extracted, needs-review, linked, failed, and unavailable; receipt alone is not authenticity, relevance, admissibility, or claim support.

Outputs: `applications/evidence_workspace_api.py`, `applications/case_routes.py`, `integrations/evidence_workspace.py`, `tests/test_cimp_ux_13.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_13.py`.

### CIMP-UX-14: Implement private evidence upload with observable progress

Depends on: CIMP-UX-13.

- Upload actual synthetic files through the private artifact owner, show bounded progress/cancel/retry and post-ingestion status, and survive a safe idempotent retry.
- Reject oversized, disallowed, cross-case, locked, stale, and revoked operations without plaintext logs, public content addressing, ambient admin keys, or success placeholders.

Outputs: `templates/workspace.html`, `static/complaint_evidence.js`, `applications/evidence_workspace_api.py`, `tests/test_cimp_ux_14.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_14.py`.

### CIMP-UX-15: Build an evidence library and detail workbench

Depends on: CIMP-UX-04, CIMP-UX-14.

- Show a searchable/filterable evidence list and useful selected-artifact detail, with status, source, dates, attributed notes, classification, and current complaint links.
- Desktop master/detail and mobile list/detail expose the same authorized server data and preserve selection; empty/error/locked states are actionable.

Outputs: `static/complaint_evidence.js`, `static/complaint_evidence.css`, `templates/workspace.html`, `tests/test_cimp_ux_15.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_15.py`.

### CIMP-UX-16: Render safe document, image, and text previews

Depends on: CIMP-UX-15.

- Preview supported real encrypted synthetic artifacts with page/span anchors, useful zoom and accessible text; unsupported formats show an explicit safe alternative.
- Treat document content as untrusted data: no active HTML/script execution, external fetches, unconsented model input, or cross-case blob/cache reuse.

Outputs: `static/complaint_evidence.js`, `applications/evidence_workspace_api.py`, `tests/test_cimp_ux_16.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_16.py`.

### CIMP-UX-17: Persist comments and annotations on exact evidence versions

Depends on: CIMP-UX-13, CIMP-UX-16.

- Store actual actor-attributed versioned comments/labels/page-span annotations through encrypted case authorization with CAS and idempotency.
- A note remains a note until explicitly adopted; never use caller display-role metadata as authority, synthesize new document evidence from a comment, or default its claim element to causation.

Outputs: `applications/evidence_annotation_store.py`, `applications/evidence_workspace_api.py`, `applications/case_routes.py`, `tests/test_cimp_ux_17.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_17.py`.

### CIMP-UX-18: Replace placeholder label and annotation actions with real editors

Depends on: CIMP-UX-17.

- Desktop/mobile Add label, Add annotation, and deadline-related actions open usable editors and persist through the real evidence annotation API. A user-marked deadline is an attributed reminder, never a derived filing deadline or legal requirement without admitted source, jurisdiction/date/version lineage and review.
- Show author/time/version, saved/pending/conflict states and keyboard focus; no next-implementation-slice status message may substitute for persistence.

Outputs: `static/complaint_evidence.js`, `templates/workspace.html`, `tests/test_cimp_ux_18.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_18.py`.

### CIMP-UX-19: Derive classification choices from current case context

Depends on: CIMP-UX-17, CIMP-UX-25, CIMP-UX-26.

- Offer current factual-gap and admitted legal-requirement identifiers rather than fixed protected_activity/employer_knowledge/causation or HR assumptions.
- Distinguish user labels, AI-suggested classifiers, reviewed acceptance, and unknown legal context; source/version changes retire stale choices and preserve attribution.

Outputs: `integrations/evidence_workspace.py`, `applications/evidence_workspace_api.py`, `static/complaint_evidence.js`, `tests/test_cimp_ux_19.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_19.py`.

### CIMP-UX-20: Create explicit evidence-to-fact and requirement links

Depends on: CIMP-UX-18, CIMP-UX-19, CIMP-UX-23, CIMP-UX-26.

- Link exact evidence artifact/version/page/span to a current factual assertion or sourced requirement using actual ClaimSupportHook owners and explicit acceptance.
- Distinguish allegation, hypothesis, corroboration, contradiction and unavailable support; a client checkbox or classifier does not mint verified legal support.

Outputs: `integrations/evidence_workspace.py`, `applications/evidence_workspace_api.py`, `static/complaint_evidence.js`, `tests/test_cimp_ux_20.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_20.py`.

### CIMP-UX-21: Preserve evidence revisions, duplicate detection, and conflict history

Depends on: CIMP-UX-20.

- A revised or repeated upload retains original/version lineage and offers a deliberate duplicate decision rather than overwriting artifacts or duplicating support silently.
- Concurrent annotations/links return conflict data and retain encrypted history; revoked or rotated access denies late publication and preview.

Outputs: `integrations/evidence_workspace.py`, `applications/evidence_annotation_store.py`, `static/complaint_evidence.js`, `tests/test_cimp_ux_21.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_21.py`.

### CIMP-UX-22: Add evidence search, chronology, and complaint-context filters

Depends on: CIMP-UX-21.

- Filter actual authorized evidence by source/date/type/label/link/review state and navigate a case timeline into the exact artifact and complaint section.
- Search/index results are derived views, never authority or a plaintext persistence substitute; stale indexes cannot expose revoked or foreign content.

Outputs: `static/complaint_evidence.js`, `applications/evidence_workspace_api.py`, `tests/test_cimp_ux_22.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_22.py`.

### CIMP-UX-23: Expose a current factual graph projection for the workspace

Depends on: CIMP-UX-10, CIMP-UX-13.

- Project user-provided assertions and explicit adopted evidence with source/version/span provenance, corrections and contradictions through actual KG adapters.
- Graph hydration must not mutate caller JSON; cached booleans, role labels, and AI inferences cannot become user assertions or verified facts.

Outputs: `applications/complaint_workspace.py`, `applications/complaint_workspace_api.py`, `complaint_phases/knowledge_graph.py`, `tests/test_cimp_ux_23.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_23.py`.

### CIMP-UX-24: Build an understandable facts and timeline interface

Depends on: CIMP-UX-23, CIMP-UX-15.

- Provide an accessible list/timeline alongside an optional graph view, with click-through fact-to-evidence provenance and uncertainty/correction controls.
- Edits reuse the current interview/CAS owner; switching display modes cannot create a second graph, drop unanswered questions, or fabricate corroboration.

Outputs: `static/complaint_facts.js`, `static/complaint_facts.css`, `templates/workspace.html`, `tests/test_cimp_ux_24.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_24.py`.

### CIMP-UX-25: Design legal context and source acquisition/review flows

Depends on: CIMP-UX-02, CIMP-UX-04, CIMP-UX-12.

- Ask for jurisdiction, forum and relevant dates without inventing defaults; source search/review uses actual Dataset legal-source tools and admitted passage identifiers.
- Separate discovery, custody, review/admission, applicability and governing-law decisions; snippets or model text cannot appear as admitted authority.

Outputs: `static/complaint_legal.js`, `templates/workspace.html`, `applications/legal_context_api.py`, `tests/test_cimp_ux_25.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_25.py`.

### CIMP-UX-26: Derive dependency requirements from admitted legal authorities

Depends on: CIMP-UX-25, CIMP-UX-23.

- Build current requirements from exact admitted law/passages with jurisdiction/effective date/version and explicit derivation lineage through real SDK tools.
- Facts affect support for requirements but cannot rewrite law; missing/conflicting authority produces visible unresolved research, not generic hardcoded elements.

Outputs: `complaint_phases/dependency_graph.py`, `applications/complaint_workspace.py`, `applications/legal_analysis_api.py`, `mediator/legal_authority_hooks.py`, `tests/test_cimp_ux_26.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_26.py`.

### CIMP-UX-27: Create a navigable legal-requirement and provenance view

Depends on: CIMP-UX-26, CIMP-UX-20.

- Let users/reviewers follow requirement→law passage→factual assertion→evidence span and see current support, contradictions and missing inputs.
- Make factual graph and legal dependency graph visibly distinct; source admission, AI suggestions and legal sufficiency remain separately labelled.

Outputs: `static/complaint_legal.js`, `static/complaint_legal.css`, `templates/workspace.html`, `tests/test_cimp_ux_27.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_27.py`.

### CIMP-UX-28: Surface source refresh, changed context, and support retirement

Depends on: CIMP-UX-27, CIMP-UX-21.

- A changed authority, date, jurisdiction, consent or evidence version retires stale support and prompts a bounded authorized refresh/review.
- Keep previous versions/audit history without showing old conclusions as current; refusal does not mutate the encrypted case head.

Outputs: `applications/legal_analysis_api.py`, `static/complaint_legal.js`, `tests/test_cimp_ux_28.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_28.py`.

### CIMP-UX-29: Expose conditional IR, formal checks, and genuine proof outcomes

Depends on: CIMP-UX-28, CIMP-UX-54.

- Render actual canonical IR/formal-logic results with source/definition/premise/execution bindings and useful explanations of unavailable/unexecuted/refused states.
- Parsed IR, solver availability, training metrics or caller status packets are never a proof; only a real bound producer result can appear as executed/verified.

Outputs: `static/complaint_legal.js`, `applications/legal_analysis_api.py`, `mediator/hook_runtime.py`, `tests/test_cimp_ux_29.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_29.py`.

### CIMP-UX-30: Build a complaint outline tied to facts, requirements, and evidence

Depends on: CIMP-UX-24, CIMP-UX-27.

- Display the current complaint outline/draft beside relevant facts and evidence, with exact cited artifact/span and admitted authority links.
- Missing support and unresolved legal/factual gaps remain visible; model prose or an evidence label cannot silently complete a requirement.

Outputs: `static/complaint_draft.js`, `templates/workspace.html`, `applications/document_api.py`, `tests/test_cimp_ux_30.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_30.py`.

### CIMP-UX-31: Add a versioned editor with safe saves and revision review

Depends on: CIMP-UX-30.

- Edit and save through the actual case/revision owner with clear saving/saved/conflict states and inspectable differences between draft revisions.
- No content lives only in browser storage; stale/locked/revoked saves cannot overwrite the encrypted head or another actor's changes.

Outputs: `static/complaint_draft.js`, `static/complaint_draft.css`, `applications/document_api.py`, `tests/test_cimp_ux_31.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_31.py`.

### CIMP-UX-32: Present AI suggestions and human review as distinct actions

Depends on: CIMP-UX-31, CIMP-UX-40.

- Reviewers see exact target version, author and AI/human provenance and may propose a bounded change without silently changing the owner's draft.
- Messages, model suggestions and machine proof are separate records; only an explicit authorized owner acceptance adopts a suggestion.

Outputs: `static/complaint_draft.js`, `applications/case_review.py`, `applications/case_review_store.py`, `tests/test_cimp_ux_32.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_32.py`.

### CIMP-UX-33: Connect review comments to evidence and complaint sections

Depends on: CIMP-UX-32, CIMP-UX-17, CIMP-UX-20.

- Support exact evidence-artifact/version/span review targets or an explicitly qualified equivalent in addition to fact/answer/legal-admission/draft targets.
- Comment/accept/reject operations retain current actor, scope, revision, idempotency and audit lineage; no reviewer can borrow the owner's master key.

Outputs: `applications/case_review_store.py`, `applications/case_review.py`, `static/complaint_draft.js`, `tests/test_cimp_ux_33.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_33.py`.

### CIMP-UX-34: Create an honest readiness and next-actions overview

Depends on: CIMP-UX-11, CIMP-UX-28, CIMP-UX-33.

- Summarize unanswered factual questions, missing evidence, unreviewed sources and draft blockers with actionable links into chat or rich workspace.
- No further actionable interview question is an interview outcome, not a promise of legal sufficiency, court readiness or successful filing.

Outputs: `static/complaint_case_shell.js`, `static/complaint_draft.js`, `templates/workspace.html`, `tests/test_cimp_ux_34.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_34.py`.

### CIMP-UX-35: Create a typed correspondence and activity projection

Depends on: CIMP-UX-12, CIMP-UX-17.

- Combine authorized AI-mediator turns, human messages, review decisions and case actions into a stable chronological projection with actual actor/invocation/target/revision lineage.
- Keep original encrypted owners and record types; a unified timeline is a view, not new authority or automatic evidence/answer adoption.

Outputs: `applications/case_correspondence_api.py`, `applications/case_routes.py`, `tests/test_cimp_ux_35.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_35.py`.

### CIMP-UX-36: Build a clear case conversation and message composer

Depends on: CIMP-UX-35, CIMP-UX-04.

- Compose/read real private case messages with human/AI attribution, bounded pending/retry/error states, idempotency and accessible keyboard/focus behaviour.
- No WebSocket/SSE claim until separately qualified; reuse actual HTTP polling and preserve case membership, key access and revocation.

Outputs: `templates/case_messages.html`, `static/complaint_correspondence.js`, `static/complaint_correspondence.css`, `tests/test_cimp_ux_36.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_36.py`.

### CIMP-UX-37: Link correspondence to explicit workflow adoption

Depends on: CIMP-UX-36, CIMP-UX-20, CIMP-UX-33.

- Navigate from a message to the exact evidence, draft or inquiry context and deliberately adopt eligible material through an authorized action.
- Human messages stay conversation by default; AI text cannot acquire human attribution or become evidence/accepted facts just by being displayed.

Outputs: `static/complaint_correspondence.js`, `applications/case_correspondence_api.py`, `applications/case_message_api.py`, `tests/test_cimp_ux_37.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_37.py`.

### CIMP-UX-38: Add an in-app inbox, unread markers, and attention states

Depends on: CIMP-UX-37.

- Show actual unread/review-needed/update notifications without complaint content in global badges, operational logs or unauthorized account views.
- Acknowledge messages through current scoped server state and handle polling cancellation/stale responses; no real email/SMS delivery is included.

Outputs: `static/complaint_correspondence.js`, `templates/cases.html`, `applications/case_correspondence_api.py`, `tests/test_cimp_ux_38.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_38.py`.

### CIMP-UX-39: Build a scoped lawyer case and review queue

Depends on: CIMP-UX-04, CIMP-UX-35.

- Assigned lawyers can prioritize actual authorized cases, review tasks and pending owner actions without receiving every user's complaint by role alone.
- Filter/sort/pagination use server-scoped metadata and meaningful labels, with empty/pending/locked/revoked states and no exposed grant IDs as primary controls.

Outputs: `templates/cases.html`, `static/complaint_reviewer.js`, `applications/case_api.py`, `tests/test_cimp_ux_39.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_39.py`.

### CIMP-UX-40: Compose the lawyer evidence-and-draft review workspace

Depends on: CIMP-UX-39, CIMP-UX-16, CIMP-UX-27, CIMP-UX-31.

- Open the server-issued review workspace into a usable evidence/fact/law/draft layout using the recipient's actual accepted scope and key grant.
- Lawyer review works with the owner wallet locked where supported; mismatched or revoked grants deny access and clear late plaintext.

Outputs: `static/complaint_reviewer.js`, `applications/legal_analysis_api.py`, `tests/test_cimp_ux_40.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_40.py`.

### CIMP-UX-41: Simplify invitations, recipient acceptance, scopes, and revocation

Depends on: CIMP-UX-39, CIMP-UX-60.

- Owners invite participants and recipients explicitly accept actual case/key scopes through understandable dialogs and server-issued versions.
- Replay is idempotent; expired/wrong-case/scope-mismatched invitations and revocation remain denied without ambient ownership or manual grant fabrication.

Outputs: `templates/cases.html`, `static/complaint_reviewer.js`, `applications/case_assignment_api.py`, `tests/test_cimp_ux_41.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_41.py`.

### CIMP-UX-42: Create an operational user and case administration workspace

Depends on: CIMP-UX-04, CIMP-UX-38.

- Provide real account/role/assignment/case-count operational analysis and useful filters for authenticated server-installed admins.
- Admin status alone exposes no narratives, evidence, private messages, exports or keys; content review requires a separate explicit case grant.

Outputs: `templates/admin.html`, `static/complaint_admin.js`, `applications/admin_api.py`, `tests/test_cimp_ux_42.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_42.py`.

### CIMP-UX-43: Expose content-access decisions and administrative audit trails

Depends on: CIMP-UX-42, CIMP-UX-41.

- Distinguish operational administration from separately authorized legal/content review, with attributable assignment/access actions and useful audit metadata.
- Body-supplied roles, approval labels and cached case objects cannot authorize content or bypass key access; tenant/case/actor crossings remain denied.

Outputs: `static/complaint_admin.js`, `applications/admin_api.py`, `applications/case_review.py`, `tests/test_cimp_ux_43.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_43.py`.

### CIMP-UX-44: Unify loading, error, empty, locked, and recovery components

Depends on: CIMP-UX-08, CIMP-UX-15, CIMP-UX-31, CIMP-UX-36, CIMP-UX-42.

- Render actionable domain conflict/unavailable/access/key states consistently, preserve user intent, and expose bounded retry/cancel where permitted.
- A failed call cannot paint ready/supported/verified; technical logs, IDs and stack traces are not ordinary UX and contain no private content.

Outputs: `static/complaint_case_shell.js`, `static/complaint_case_shell.css`, `templates/workspace.html`, `templates/case_messages.html`, `tests/test_cimp_ux_44.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_44.py`.

### CIMP-UX-45: Qualify keyboard, focus, screen-reader structure, and contrast

Depends on: CIMP-UX-44.

- Prove semantic labels/headings, keyboard-complete dialogs/actions, focus return, announcements, reduced motion and contrast on real pages.
- Check chat, evidence annotations, source review, drafting and invitations, including error/locked states and 200% zoom; no inaccessible duplicate hidden controls.

Outputs: `static/complaint_case_shell.css`, `static/complaint_case_shell.js`, `templates/workspace.html`, `templates/cases.html`, `templates/case_messages.html`, `tests/test_cimp_ux_45.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_45.py`.

### CIMP-UX-46: Qualify mobile and tablet task continuity

Depends on: CIMP-UX-45.

- Complete the same case tasks at 1440, 768, 390 and 320px widths without clipped actions, lost context, overflowing legal text or unusable evidence previews.
- Mode/navigation changes retain canonical server state and meaningful reading order; screen size never changes authorization or omits unresolved gaps.

Outputs: `static/complaint_case_shell.css`, `static/complaint_evidence.css`, `static/complaint_draft.css`, `static/complaint_correspondence.css`, `tests/test_cimp_ux_46.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_46.py`.

### CIMP-UX-47: Bound interface requests and stale-result handling

Depends on: CIMP-UX-44, CIMP-UX-12.

- Use actual abort/cancel/lifecycle handling with finite declared request budgets and explicit pending/unavailable results across case/actor/key/consent changes.
- Preserve bridge error abortion, actual Native child reaping and existing worker budgets; queued or cancelled work cannot publish late or masquerade as completion.

Outputs: `static/complaint_mcp_sdk.js`, `static/complaint_mcp_sdk.mjs`, `static/complaint_case_shell.js`, `tests/test_cimp_ux_47.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_47.py`.

### CIMP-UX-48: Measure rendering and large-evidence interface budgets

Depends on: CIMP-UX-46, CIMP-UX-47.

- Exercise bounded realistic synthetic case/evidence/message volumes with useful pagination/lazy details and recorded render/request costs.
- Keep graph provenance, annotations, selection and accessible navigation correct under load; do not solve performance by omitting required data, disabling guards or raising worker deadlines.

Outputs: `static/complaint_evidence.js`, `static/complaint_facts.js`, `static/complaint_case_shell.js`, `tests/test_cimp_ux_48.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_48.py`.

### CIMP-UX-49: Qualify Grok 4.7 application inference through the canonical router

Depends on: CIMP-UX-02, CIMP-UX-12.

- Prove provider grok_cli/model grok-4.7/fallback false through actual llm_router adapter signatures and typed error/cancel/quota paths with bounded synthetic transports.
- Actual case/purpose consent, membership, minimization and current revisions govern dispatch/admission; development-agent Grok permission is never consent to send a complaint.

Outputs: `integrations/ipfs_accelerate/routers.py`, `integrations/ipfs_datasets/llm.py`, `backends/llm_router_backend.py`, `applications/complaint_workspace.py`, `tests/test_cimp_ux_49.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_49.py`.

### CIMP-UX-50: Activate qualified host dispatch for mediator operations

Depends on: CIMP-UX-02, CIMP-UX-49.

- Replace disabled acquire_legal_sources/ingest_private_evidence/refresh_grounding handlers only where actual host targets, saved case consent, private artifact access and derived-index readiness are verified.
- Test positive public dispatch and refused/late/stale/missing-owner paths with real effects and journals; caller booleans, registry presence or invented receipts cannot activate hooks.

Outputs: `mediator/hook_runtime.py`, `applications/complaint_workspace.py`, `tests/test_cimp_ux_50.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_50.py`.

### CIMP-UX-51: Ground classification, statute, requirement, and question hooks

Depends on: CIMP-UX-50, CIMP-UX-26.

- Qualify LegalClassification, StatuteRetrieval, SummaryJudgment and QuestionGeneration hooks against real canonical Dataset/legal tools and current source-bound requirements.
- Preserve factual-vs-legal distinction, explicit unknown context, input DTO immutability and finite inquiry semantics; default claim taxonomies or model text do not create law.

Outputs: `mediator/legal_hooks.py`, `mediator/hook_runtime.py`, `complaint_phases/dependency_graph.py`, `tests/test_cimp_ux_51.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_51.py`.

### CIMP-UX-52: Ground private evidence storage, state, and analysis hooks

Depends on: CIMP-UX-50, CIMP-UX-17, CIMP-UX-57.

- Qualify EvidenceStorage/EvidenceState/EvidenceAnalysis through actual Kit-backed encrypted artifacts and Dataset extraction/chunk/metadata owners under case+actor scope.
- Prove key lock, conflicting revision, source integrity, unsafe content, missing capability and consent refusal without plaintext fallback or annotation-as-evidence conversion.

Outputs: `mediator/evidence_hooks.py`, `mediator/hook_runtime.py`, `integrations/private_storage.py`, `tests/test_cimp_ux_52.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_52.py`.

### CIMP-UX-53: Ground claim support and legal authority hooks

Depends on: CIMP-UX-51, CIMP-UX-52, CIMP-UX-20.

- Qualify ClaimSupport and LegalAuthoritySearch/Storage/Analysis with admitted passages, requirement IDs, source/definition versions and explicit actual support lineage.
- Search hits, stale caches, suggestions and caller support flags cannot be governing authority or verified support; source drift and contradictions retire affected projections.

Outputs: `mediator/claim_support_hooks.py`, `mediator/legal_authority_hooks.py`, `mediator/hook_runtime.py`, `tests/test_cimp_ux_53.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_53.py`.

### CIMP-UX-54: Ground formal and neurosymbolic analysis in actual producers

Depends on: CIMP-UX-53.

- Use real formal-logic/IR/neurosymbolic SDK surfaces and current source/definition/premise bindings, with explicit unavailable/unexecuted outcomes when a producer is missing.
- A parsed formula, structural graph check, classifier score, training metric or fake producer packet never becomes executed proof or legal sufficiency.

Outputs: `mediator/hook_runtime.py`, `complaint_phases/neurosymbolic_matcher.py`, `integrations/ipfs_datasets/logic.py`, `tests/test_cimp_ux_54.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_54.py`.

### CIMP-UX-55: Ground web evidence acquisition and integration hooks

Depends on: CIMP-UX-53, CIMP-UX-12.

- Qualify WebEvidenceSearch/WebEvidenceIntegration with real bounded adapter dispatch, source custody and explicit adoption, retaining acquisition/review/support distinctions.
- Offline assets or remote permission gaps are honest unavailable states; no uncontrolled crawl, CommonCrawl clone/reset, private complaint egress or automatic fact adoption.

Outputs: `mediator/web_evidence_hooks.py`, `mediator/hook_runtime.py`, `integrations/ipfs_datasets/search.py`, `tests/test_cimp_ux_55.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_55.py`.

### CIMP-UX-56: Prove all thirteen hook outcomes across the complaint lifecycle

Depends on: CIMP-UX-51, CIMP-UX-52, CIMP-UX-53, CIMP-UX-54, CIMP-UX-55.

- Exercise each of the thirteen real hooks through its actual workflow entry point with source/runtime/owner/consent/revision bindings and one meaningful negative path.
- Required workflow hooks and the three core registered operations need genuine positive effects plus refusal tests. Explicitly unsupported optional features may be tested unavailable, but that is not completed activation. Missing required capability is a recorded dependency failure, never a metadata-only success.

Outputs: `mediator/hook_runtime.py`, `applications/complaint_workspace.py`, `docs/ux/complaint_ux_overhaul/sdk_hook_inventory.json`, `tests/test_cimp_ux_56.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_56.py`.

### CIMP-UX-57: Qualify durable private evidence and annotation storage

Depends on: CIMP-UX-02, CIMP-UX-13.

- Use actual Kit encryption/durability APIs for evidence, annotations, classification revisions and linkage records with authenticated bindings and bounded recovery.
- Content-addressing is not encryption; queued/local writes are not remote durability. No unqualified replication, raw private CIDs, ambient keys, success flags or plaintext fallback.

Outputs: `integrations/private_storage.py`, `integrations/private_collaboration.py`, `applications/evidence_annotation_store.py`, `tests/test_cimp_ux_57.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_57.py`.

### CIMP-UX-58: Make key unlock, lock, rotation, and revocation coherent in the UI

Depends on: CIMP-UX-57, CIMP-UX-44.

- Actual key state changes consistently clear/reload authorized case content across chat, evidence, graphs, draft and messages with useful recovery guidance.
- Locked/wrong/revoked keys and late operations cannot recreate an empty case, expose cached plaintext, admit stale writes or borrow a different actor's wallet.

Outputs: `static/complaint_case_shell.js`, `static/complaint_evidence.js`, `static/complaint_correspondence.js`, `applications/complaint_workspace.py`, `tests/test_cimp_ux_58.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_58.py`.

### CIMP-UX-59: Prove cold reconstruction and encrypted workflow continuity

Depends on: CIMP-UX-58, CIMP-UX-31, CIMP-UX-37.

- Reconstruct services/wallets from actual encrypted stores and resume pending questions, evidence annotations/links, source context, draft and correspondence without browser caches.
- Test missing/wrong keys, tampered heads, interrupted writes and WAL recovery; state precisely whether durability is local or actually qualified remote storage.

Outputs: `integrations/private_storage.py`, `applications/complaint_workspace.py`, `tests/test_cimp_ux_59.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_59.py`.

### CIMP-UX-60: Qualify recipient-bound collaboration key lifecycle

Depends on: CIMP-UX-57, CIMP-UX-39.

- Prove owner invitation, recipient acceptance, exact scopes/key epochs, rotation, expiry and revocation with actual distinct owner/lawyer wallets.
- Content sharing cannot be inferred from a role/membership label; owner-locked recipient reads work only through real accepted grants and current authorization.

Outputs: `integrations/private_collaboration.py`, `applications/case_assignment_api.py`, `applications/case_review_store.py`, `tests/test_cimp_ux_60.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_60.py`.

### CIMP-UX-61: Capture the redesigned screenshot matrix from real application flows

Depends on: CIMP-UX-22, CIMP-UX-29, CIMP-UX-34, CIMP-UX-38, CIMP-UX-41, CIMP-UX-43, CIMP-UX-46, CIMP-UX-56, CIMP-UX-59.

- Produce fresh desktop/tablet/mobile before-and-after screenshots for actual synthetic owner/lawyer/admin/chat/evidence/draft/correspondence states with viewport, source, runtime and DOM assertions.
- Use real public handlers, pinned Chromium/Node and inherited non-Unix network denial; no mockApi, diagnostic test-only law panel, invented evidence, real user data or unclosed processes.

Outputs: `docs/ux/complaint_ux_overhaul/capture_contract.json`, `tests/gui_ux_overhaul_fixtures.py`, `tests/test_cimp_ux_61.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_61.py`.

### CIMP-UX-62: Qualify visual regression, accessibility, and interaction continuity

Depends on: CIMP-UX-61, CIMP-UX-48.

- Compare actual screenshot/layout landmarks and interaction results across declared widths, keyboard paths and loading/empty/error/locked/stale/revoked variants.
- Image similarity alone cannot pass backend/state/privacy behaviour; reviewed baseline changes require a documented reason and preserve nonempty required cases with zero skips.

Outputs: `scripts/validate_complaint_ux_visuals.py`, `tests/gui_ux_overhaul_fixtures.py`, `tests/test_cimp_ux_62.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_62.py`.

### CIMP-UX-63: Exercise adversarial evidence, role, transport, and late-result cases

Depends on: CIMP-UX-62.

- Prove actual owner/lawyer/admin/stranger isolation, hostile evidence rendering, wrong-case previews/messages/downloads, missing consent and stale key/source/result denial.
- Retain inherited process/network/AST/source/claim guards and explicit unsupported transports; no self-authorizing fixtures or fake custody/proof.

Outputs: `tests/gui_ux_overhaul_security_fixtures.py`, `tests/test_cimp_ux_63.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_63.py`.

### CIMP-UX-64: Exercise complete complaint and human-review journeys

Depends on: CIMP-UX-63.

- Run original complaint→adaptive questions→corrected factual graph→private annotated evidence→source-bound legal requirements→cited draft→lawyer message/review→explicit owner acceptance→cold resume.
- Include unresolved/unknown/cancelled/provider/source/proof/storage failures and deny unauthorized actors; successful UX never implies automatic legal sufficiency or filing.

Outputs: `tests/gui_ux_overhaul_fixtures.py`, `tests/test_cimp_ux_64.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_64.py`.

### CIMP-UX-65: Qualify genuine new-campaign ingestion and startup observations

Depends on: CIMP-UX-01, CIMP-UX-02.

- Use the real compiler/Native parser and independently scoped plan/spec/board/state/worktree identities; observe source_generation/plan/task bindings from the actual publisher.
- Ingestion/PID/doctor-ready is not execution: require real owned launcher/daemon births and bounded provider/validation work without changing old campaigns, task status, receipts or budgets.

Outputs: `integrations/ipfs_accelerate/improvement_runner.py`, `tests/test_cimp_ux_65.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_65.py`.

### CIMP-UX-66: Qualify watchdog recovery and finite owned child lifetimes

Depends on: CIMP-UX-65, CIMP-UX-63.

- Demonstrate actual scoped idle/stall/validation/owner-death recovery, nested child reaping, no foreign-validator contamination and current phase deadlines.
- Keep existing 90/180/900-second grace/stall/execution limits, three attempts/64 turns and two recovery actions per incident; preserve holds, uncertain ledgers and genuine product awaiting-user states.

Outputs: `integrations/ipfs_accelerate/campaign_watchdog.py`, `tests/test_cimp_ux_66.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_66.py`.

### CIMP-UX-67: Publish a useful UX and operations handoff with evidence links

Depends on: CIMP-UX-64, CIMP-UX-66.

- Document the measured before/after screenshots, primary journeys, role/consent/key boundaries, evidence adoption, graph provenance, finite stopping and scoped recovery commands.
- Record actual tested revisions and explicit live-model/corpus/prover/remote-durability limitations; old60 completion and screenshot files do not complete this new program.

Outputs: `docs/ux/complaint_ux_overhaul/before_after_review.md`, `docs/task_boards/complaint_gui_ux_overhaul_operator_guide.md`, `tests/test_cimp_ux_67.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_67.py`.

### CIMP-UX-68: Provide fresh bounded current-source UX acceptance and closure

Depends on: CIMP-UX-67.

- Create a real grouped current-source acceptance CLI with immutable declared selectors, nonempty cases, actual Kernel/AST/DOM/state/source evidence, fresh output custody and no skipped required cases.
- Execute only focused bounded controller behaviour during this task; the full final matrix and production Native completion verifier run outside this task's900-second validation, after its genuine callback. No self-pending circular precondition or caller booleans/saved JSON authority.

Outputs: `scripts/validate_complaint_ux_overhaul.py`, `docs/task_boards/complaint_gui_ux_overhaul_completion_contract.json`, `tests/test_cimp_ux_68.py`.

Validation: `python -m pytest -q --run-llm --run-network --run-heavy tests/test_cimp_ux_68.py`.

## Execution and closure

The implementation route isipfs_accelerate_py.llm_router→grok_cli/grok-4.7, fallback disabled. Development model permission does not authorize a real-case upload. Tests stay local/synthetic and use actual pinned SDK/browser/kernel capabilities.

A fresh private state/worktree root and namespace isolate this program. Normal Native APIs own selection, attempts, validation, merge and callbacks. A dedicated plan/spec-bound minute watchdog observes actual activity and bounded recovery without changing user holds or paid budgets.

Require actual callbacks for these68canonical tasks, settled merge queue and owned lifecycle, then fresh grouped current-source UX acceptance and screenshot/DOM/backend checks outside any individual900-second task. Earlier GUI60 callbacks, screenshots, caller booleans, an open plan and doctor-ready do not complete this program.

Genuine startup requires owned launcher/daemon births, current canonical task/attempt and Grok activity or actual validation.
