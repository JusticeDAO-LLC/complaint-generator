# Complaint workspace experience contract

This contract guides the new `complaint-gui-ux-overhaul` campaign. It extends the existing implemented case, interview, evidence, graph, draft, review, messaging and private-storage owners. The completed GUI60 program is a baseline, not completion of this new campaign.

## Start with the person's work

A person must be able to answer five questions at any point: Which case am I in? What has the system understood? What needs attention next? Which evidence and law support this part of the draft? Who can see or act on it?

The interface should make those answers visible before exposing implementation details. A calm hierarchy, plain language and progressive disclosure matter more than adding more panels. Explain a consequential choice at the point of action. Keep a clear way to pause, return, correct and undo a proposed change without silently changing the stored complaint.

The baseline images are actual synthetic application captures. Pair them with their source/runtime/state manifest and DOM assertions. They are not mockups or proof that every displayed status is correct. In particular, the baseline contains a working authenticated pending inquiry below a stale `No case selected`/access-denied header. Preserve that observation as a defect, not a template to reproduce.

## A case-centred structure

Use a shared shell across owner and authorized reviewer pages:

- Global access: My cases, Inbox, Account/privacy.
- Current case: a meaningful case label, actual actor/role, lock/privacy state and a readable workflow stage.
- Case tasks: Overview, Mediator, Evidence, Facts and timeline, Legal requirements, Draft, Team and correspondence.
- Context: the selected evidence passage, explanation of the current question, linked law passage, or review target.

Desktop can use a compact navigation rail, a primary task area and an optional contextual side panel. Chat, split view and rich workspace are views over the same canonical session, not separate products. On mobile, use a deliberate case/chat/evidence/draft navigation pattern with secondary tasks in More. Preserve reading order, selected context and focus across modes.

Do not lead ordinary users with CLI/MCP/SDK links, raw grant IDs, polling intervals, inquiry/objective hashes or migration diagnostics. Keep legitimate source citations, integrity detail and advanced diagnostics available in appropriate secondary views. Never hide uncertainty, a failed operation or an access boundary to make a screen look successful.

## Complaint and questions

1. The user can begin with their own narrative, without choosing a generic legal theory first.
2. Show one current server-issued question and understandable rationale. Offer Why, answer, unknown, defer and correction only where supported by the actual transition contract.
3. An answer carries the exact inquiry identity and expected revision. A stale answer leaves the encrypted head, current question and accepted graph state unchanged and offers a useful recovery action.
4. Show what changed in the factual graph after an accepted answer or correction. A factual answer may change support for a legal requirement; it cannot rewrite the law.
5. Preserve the difference between no actionable question, paused, cancelled, capped, saturated and unavailable. Retain unresolved factual, evidentiary and legal research gaps. None of these means legal sufficiency or court readiness.

The visible case/actor/access header and next action must reflect the actual authenticated state. An operational interview must not remain under a stale access-denied banner; an unauthorized interview must never display ready.

## Evidence is a workbench, not a form at the bottom of a page

Prioritize a compact evidence library and selected-artifact view. Support safe upload, ingestion status, previews, source/date/type metadata, version lineage, comments, classifications and complaint links. Make each significant action visible and attributable.

The evidence detail model distinguishes:

| Record | Meaning and adoption boundary |
| --- | --- |
| Artifact/version | The encrypted received source and its immutable/versioned identity. Receipt does not prove authenticity or relevance. |
| Extracted passage | Exact artifact version, page/span and extraction lineage; untrusted source content remains data. |
| Comment/annotation | An attributed note anchored to the exact evidence version; not new evidence or an intake answer by default. |
| Classifier | A user label or clearly attributed AI suggestion; not verified support or governing law. |
| Support link | An explicit accepted relationship to a factual assertion or current legal requirement, retaining uncertainty and provenance. |
| Review decision | A current authorized human action against an exact target revision, distinct from AI output and machine proof. |

Replace fixed retaliation/HR claim-element choices with the actual case's factual gaps and admitted legal requirements. Unknown legal context must remain unknown. Do not default an annotation to causation or manufacture a new document from a note. Add label, Add annotation and deadline controls must persist real versioned records; placeholder status messages do not implement those actions.

Support useful list/detail navigation, filtering and chronology before an optional graph visualization. For supported previews provide accessible text, meaningful page/span anchors and mobile zoom. Disable active source content, remote loads and implicit model use. Unsupported formats get an honest alternative.

## Two graphs and a grounded draft

The factual knowledge graph records what a person asserted and what an explicitly adopted evidence passage supports, with corrections, contradictions and uncertainty. The legal dependency graph derives requirements from exact admitted legal sources, with jurisdiction, applicable date, source version and passage identity. They must be visually and semantically distinct.

Allow a trace from draft section to requirement, law passage, factual assertion and evidence span. Show unresolved research, missing evidence and contradictions beside the draft. A source search hit is discovery; admission is not applicability; applicability is not proof. Model prose, a parsed formula, graph consistency, a confidence score and an unexecuted proof are not governing law or verified legal support.

Use actual Dataset knowledge-graph, legal-source, canonical IR and formal-logic tools through the existing adapters. Show unavailable or unexecuted formal work honestly. Changes to authority, date, jurisdiction, facts, evidence, key access or consent retire affected stale projections before reuse.

Draft editing uses the current encrypted revision with saving/saved/conflict feedback and inspectable differences. AI and human proposals remain proposals until an authorized accepted action adopts them. Do not let an unreadable error, stale response or cached browser object overwrite the current draft.

## Correspondence and collaboration

Provide a coherent chronological correspondence view over actual AI mediator turns, human messages, review decisions and case actions. Preserve the original encrypted domain records and actual actor or model invocation. A timeline is a projection, not a new permission source.

Users must be able to tell who wrote a message, why it appeared, which evidence/draft/question it concerns and what action it requires. Keep conversation distinct from explicit evidence or answer adoption. Notifications expose minimal metadata; they must not leak complaint text or attachments into global badges or operational logs. Use the qualified HTTP polling transport; email, SMS, WebSocket/SSE and court filing are not silently added.

An assigned lawyer needs a usable scoped case/review queue and evidence/draft context. Owners invite; recipients accept real scopes and key grants. A lawyer role alone grants no case content. Recipient review may work while the owner's wallet is locked only where a real accepted recipient key grant permits it.

Operational admins can analyze accounts, roles, assignments, counts and operational state. Complaint-content review requires a separate explicit case authorization and key access. Admin status, display-role text and the UI's current selection never supply a decryption key.

## Privacy and durable continuity

Local processing is the default. Using Grok 4.7 for development does not authorize egress of a real complaint. The application must explain and persist purpose-scoped case consent before minimized remote inference, and recheck current membership, keys, consent and revisions before accepting a late result.

Use actual Kit encryption, authenticated bindings and recovery for evidence, annotations, conversations, drafts and graph state. Content addressing is not encryption; a local write or queued replica is not verified remote durability. Lock, revocation, rotation and case/actor switches clear rendered plaintext and abort stale work. Missing keys do not create replacement cases. Browser storage is not the complaint's durable source of truth.

## Accessibility, states and verification

Qualify desktop1440x1000, tablet768x1024, mobile390x844 and320px reflow, keyboard-only actions, focus return, programmatic labels, contrast, reduced motion and200%zoom. Do not hide essential actions or unresolved gaps on small screens.

For every primary task cover empty, populated, pending, error, denied, locked, revoked, stale and unavailable states where applicable. Keep a helpful next action and preserve intent. Requests, provider work, validation and owned child cleanup remain finite. Product waiting for a human is distinct from a development worker with no progress.

Acceptance pairs screenshots with real DOM, actual API/SDK/cryptographic state and negative access checks. No blank-page screenshot, image-similarity score, canned mock response or caller-owned status packet is sufficient. Use the inherited pinned Chromium/Node pipe-to-ASGI harness and kernel denial of non-Unix sockets. Capture only new synthetic cases and close all owned browser processes.

## Delivery order

Measure and characterize first; implement the shared design and case shell next. Build chat and evidence on the same session, then graph/source/draft context, correspondence and role workspaces. Integrate the mediator's real hook owners and durable encrypted record types. Finish with fresh cross-role screenshots, adversarial journeys and bounded current-source acceptance.

Each Native task has exact output paths, dependencies, meaningful positive and negative validation and the existing900-second budget. Keep one worker initially. A missing required capability is a measured dependency failure, not a completed activation. Do not reset previous campaign history, claims, budgets or holds. Preserve the earlier completed60-task program and its132-case evidence as historical regression coverage.
