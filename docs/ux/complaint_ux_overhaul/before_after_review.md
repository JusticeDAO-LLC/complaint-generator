# Before and after review

This handoff records the measured synthetic baseline for `complaint-gui-ux-overhaul`. It is the before state and the source-bound story the later shell, evidence, graph, and correspondence work has to preserve. It is not a claim that the redesigned experience has already shipped, and it does not complete the program.

The experience contract is [experience_contract.md](experience_contract.md). The capture binding is [baseline/screenshot_manifest.json](baseline/screenshot_manifest.json). The annotated visual brief is [screenshot_driven_findings.json](screenshot_driven_findings.json). The operator commands and ceilings are in [complaint_gui_ux_overhaul_operator_guide.md](../../task_boards/complaint_gui_ux_overhaul_operator_guide.md).

The authoring route did not ingest screenshot pixels. Hashes, routes, viewports, DOM checks, and the written findings are the visual evidence. Do not treat image similarity or the PNG files alone as acceptance.

The application baseline commit is `6f27c60c3b49b8bad49088bd46e788fa31c646eb`. The capture used synthetic data only. `provider_invoked` is false. `mock_api_used` is false. Transport was actual same-origin HTTP to ASGI over the pinned CDP pipe, with inherited denial of non-Unix sockets (`af_unix_only` true, `af_inet` and `af_inet6` not opened). Same-origin route count was 63 and external aborted count was 0. Owned browser processes were cleaned (`remaining_pids` empty). Node content hash `5796fd9700e83170bc7ddfdf7f18858c794a9f91cb39dd6f9e95060b292f2563`. Chromium content hash `20ffc88be1c6f7dc8351bebfaca965ff9a07617bddf696f0b67ef85e5868b29a`.

Declared SDK pins from [sdk_hook_inventory.json](sdk_hook_inventory.json), decision `cimp-ux-02-retain-declared-pins`:

| Owner | Declared pin | Checkout observed here |
| --- | --- | --- |
| ipfs_accelerate_py | `947f873e407efd9b12c551a5e69a9b62819b9c4e` | unavailable; opaque gitlink, not populated |
| ipfs_datasets_py | `b857f28462bfbb9cbf02232a79cdefcaa1ef1bc7` | present; checked-out commit unavailable (`GitdirPointer`) |
| ipfs_kit_py | `0007f735b90215fa611f39aa558eb512a493b8af` | present; checked-out commit unavailable (`GitdirPointer`) |

## Measured screenshots

All 13 files live under `docs/ux/complaint_ux_overhaul/baseline/`. Diagnostic test panels were not mounted. Hashes are SHA-256 of the PNG bytes recorded in the manifest.

| Id | File | Route | State | Viewport | SHA-256 | Bytes |
| --- | --- | --- | --- | --- | --- | --- |
| `01-home-desktop` | `01-home-desktop.png` | `/` | `public_entry` | 1440x1000 | `a449512c029db6e15affd95d0befe96f9f9ff371ae9950f1959f13f3652b74ef` | 357002 |
| `02-workspace-desktop` | `02-workspace-desktop.png` | `/workspace` | `authenticated_backend_with_existing_stale_workspace_header` | 1440x1000 | `1a9ac6b6dfa301ab2ed1aaf53ca3697c0c44f88f4bfbc5f4428f18931e9e7ba5` | 273615 |
| `03-mediator-question-desktop` | `03-mediator-question-desktop.png` | `/workspace` | `actual_pending_question_and_why` | 1440x1000 | `812501466ebd301af6e7cd2544edc1a84546ad15daa609f90a260748920ad8a4` | 436536 |
| `04-mediator-question-mobile` | `04-mediator-question-mobile.png` | `/workspace` | `same_actual_pending_question` | 390x844 | `bde08ac38ed57a27735ccf4c50834c0601ea554171cd281c5d46697920f49e4e` | 150169 |
| `05-evidence-composer-desktop` | `05-evidence-composer-desktop.png` | `/workspace` | `actual_evidence_composer_unsaved` | 1440x1000 | `c0853943933dc166808981506ff0eec388a20011b4bfb870513060d11ce74e1a` | 472398 |
| `06-evidence-composer-mobile` | `06-evidence-composer-mobile.png` | `/workspace` | `same_actual_evidence_composer_unsaved` | 390x844 | `58dd6975f8438cc4bf0a2fd5ea8a760cca87a106737fe90ed3b65f97026fe595` | 91606 |
| `07-draft-desktop` | `07-draft-desktop.png` | `/workspace` | `actual_draft_not_generated_readiness_visible` | 1440x1000 | `a58e4d8a0269fb7bb484c5acde4466f09ea42a870edbc30de2c4e702ee5ec916` | 375801 |
| `08-cases-owner-desktop` | `08-cases-owner-desktop.png` | `/cases` | `actual_owner_case_and_pending_lawyer_invitation` | 1440x1000 | `4dd238936beceeb6fcb077400a567695a52af64e188c74f06d6a0f194aae80ef` | 101049 |
| `09-lawyer-workspace-desktop` | `09-lawyer-workspace-desktop.png` | `/lawyer-workspace` | `actual_assigned_lawyer_scope_content_not_shared` | 1440x1000 | `a9da87718026d31eec8083b385e0584d6714f4894c2697deccded85034b0e8dc` | 74391 |
| `10-correspondence-owner-desktop` | `10-correspondence-owner-desktop.png` | `/case-messages` | `actual_durable_conversation_message` | 1440x1000 | `935314293fb854bce3c0bd260828a53f7138fb32b4ac502f17f28985dab4359b` | 119706 |
| `11-correspondence-lawyer-mobile` | `11-correspondence-lawyer-mobile.png` | `/case-messages` | `actual_authorized_recipient_conversation` | 390x844 | `9ed66ff031bbd564321f5d681f3feba040c901f6db9f0b17ed1671c40f541416` | 81520 |
| `12-admin-accounts-desktop` | `12-admin-accounts-desktop.png` | `/admin` | `actual_operational_admin_metadata_only` | 1440x1000 | `74699f369b435c1999c27f45e576a2754a3ef78484faca619e943b06cfa571b7` | 131999 |
| `13-admin-accounts-mobile` | `13-admin-accounts-mobile.png` | `/admin` | `same_actual_operational_admin_metadata_only` | 390x844 | `f64c565253f9a3fef6d378180d311dd11944e3b7f6639bacc3297bcf3c7da1a8` | 73948 |

## What the captures show, and what must change

These observations are the before story. The plan requirement is the intended after, and it is not depicted as already true in these files.

`UX-01` on `02-workspace-desktop`, `03-mediator-question-desktop`, and `04-mediator-question-mobile`. Observed: Real authenticated owner pending inquiry is active while persistent case header says No case selected and workspace access-denied banner remains. After: one authenticated case, actor, and privacy context, with the stale failure cleared only after verified success. The working inquiry under that stale header is real. Do not copy the banner forward as the template, and do not pretend the baseline header was already correct.

`UX-02` on `05-evidence-composer-desktop`. Observed: Sidebar says Complete while zero answers are saved and five elements need support. After: transport success, saved state, unresolved interview, review readiness, and legal sufficiency stay distinct. Complete is not a label for an unresolved case.

`UX-03` on `03-mediator-question-desktop` and `04-mediator-question-mobile`. Observed: The pending question is a form surrounded by raw inquiry/objective ids, internal target paths and verbose provenance. Mobile answer controls fall below technical explanation text. After: one current question, compact why and source disclosure, and the same encrypted session in chat and rich modes, including unknown, defer, and correct where the transition contract allows them.

`UX-04` on `05-evidence-composer-desktop` and `06-evidence-composer-mobile`. Observed: Several large guidance panels precede the evidence form; the form exposes one hardcoded claim-element selector and no visible evidence preview/library in this viewport. After: a library and detail view with preview, upload status, versioned comments, classifier proposals, and explicit links. Suggestions stay separate from adopted facts.

`UX-05` on `10-correspondence-owner-desktop` and `11-correspondence-lawyer-mobile`. Observed: Opening a conversation requires raw case/thread/membership ids, versions, and polling interval; senders appear as opaque ids and protocol notes dominate the page. After: a case-scoped timeline with verified actor labels, AI versus human attribution, and transport controls kept off the primary surface.

`UX-06` on `12-admin-accounts-desktop` and `13-admin-accounts-mobile`. Observed: The account table is visibly clipped on mobile; role changes and disable actions sit alongside raw ids. Masked credential remains populated after successful login. After: responsive account summaries, guarded role and status actions, and credentials cleared after verification. Admin metadata is still not case content.

`UX-07` on `09-lawyer-workspace-desktop`. Observed: The scoped lawyer page is a sparse repeated authorization form plus raw revision/request/proposal fields; this baseline has not shared a content envelope. After: an assigned-case review queue and an owner-sharing / recipient-acceptance workflow. Content stays closed until a real grant and key admission.

`UX-08` on `01-home-desktop`, `02-workspace-desktop`, `10-correspondence-owner-desktop`, and `12-admin-accounts-desktop`. Observed: Workspace uses a large branded hero/cards while correspondence/admin use largely default HTML forms and unrelated page structures. After: one shell, shared type and spacing, and honest empty, loading, locked, and unavailable states.

## Primary journeys

1. Enter on `/` (`01-home-desktop`, state `public_entry`) and see a public page, not a case.
2. Open `/workspace` already authenticated (`02-workspace-desktop`). The pending inquiry below the header is real. The header can still say No case selected and access denied. That split is `UX-01`.
3. Answer one server-issued question (`03-mediator-question-desktop`, `04-mediator-question-mobile`, states `actual_pending_question_and_why` and `same_actual_pending_question`). Why is present on the desktop capture. A stale answer must not move the encrypted head. Unknown, defer, pause, cancel, cap, and unavailable stay distinct from legal sufficiency.
4. Open the evidence composer (`05-evidence-composer-desktop`, `06-evidence-composer-mobile`). The form is unsaved. This is not an upload, annotation, classifier, or replica.
5. Open the draft (`07-draft-desktop`, state `actual_draft_not_generated_readiness_visible`). No complaint text was fabricated.
6. Review the owner case list (`08-cases-owner-desktop`, state `actual_owner_case_and_pending_lawyer_invitation`). The owner invites. The invitation is pending.
7. Open the lawyer workspace (`09-lawyer-workspace-desktop`, state `actual_assigned_lawyer_scope_content_not_shared`). Assignment through the UI is not a shared content envelope.
8. Read correspondence as the owner (`10-correspondence-owner-desktop`, state `actual_durable_conversation_message`) and as an authorized recipient (`11-correspondence-lawyer-mobile`, state `actual_authorized_recipient_conversation`). A timeline is a projection, not a new permission.
9. Open operational admin (`12-admin-accounts-desktop`, `13-admin-accounts-mobile`, states `actual_operational_admin_metadata_only` and `same_actual_operational_admin_metadata_only`). The directory is account metadata.

## Role, consent, and key boundaries

A lawyer role alone grants no case content. The recipient needs an accepted scope and a key grant. Review while the owner's wallet is locked is allowed only where that grant permits it. Admins analyze accounts and operational state. They do not receive complaint content from a role label or from the selected row. The signed-in actor and the canonical encrypted owner stay distinct. Missing keys do not create replacement cases. Lock, revocation, rotation, and actor or case switches clear plaintext and refuse late results.

Consent for minimized remote inference is purpose-scoped and persisted, then rechecked with membership, keys, and revisions. The baseline did not invoke a provider. Development authorization for `grok-4.7` is not consent to send a real complaint out.

## Evidence adoption

| Record | Boundary shown by this baseline |
| --- | --- |
| Artifact | Encrypted received source. Receipt is not authenticity or relevance. The evidence captures are unsaved forms, so they are not receipts. |
| Passage | Exact version, page or span, and extraction lineage. Source text stays data. |
| Annotation | Attributed note on an exact version. Not new evidence and not an intake answer by default. |
| Classifier | User label or attributed suggestion. Not verified support and not governing law. |
| Support link | Explicit accepted relationship to a fact or a current legal requirement, with uncertainty and provenance kept. |
| Review decision | Authorized human action on an exact target revision. Distinct from model output and from machine proof. |

`UX-02` and `UX-04` are the before picture of adoption failing in the UI: a Complete label with nothing saved, and a hardcoded claim-element control instead of an explicit link.

## Graph provenance

The factual graph is what a person asserted and what an explicitly adopted passage supports, including contradictions and uncertainty. The legal dependency graph is requirements from admitted sources, with jurisdiction, applicable date, source version, and passage identity. They are different graphs. A draft section should be traceable to a requirement, a law passage, a factual assertion, and an evidence span. The baseline draft is not generated, so that trace is not shown and must not be invented.

A source search hit is discovery. Admission is not applicability. Applicability is not proof. `search_us_code_corpus_from_parameters` is the pinned corpus entry. Its effect qualification is unavailable. An unexecuted proof is not a prover result and is not governing law. Authority, date, jurisdiction, fact, evidence, key, or consent changes retire stale projections before reuse.

## Finite stopping and scoped recovery

Campaign ceilings used by this program are startup grace 90 seconds, stall 180 seconds, implementation and validation 900 seconds, 3 attempts, 64 provider turns, and 2 watchdog recoveries per incident. The operator guide names the public `status`, `stop`, `recover`, `watchdog --once`, and same-epoch `start` commands. Those commands are scoped to one spec and one state directory. They do not reset attempts, holds, or paid budgets. `awaiting_user` is a product wait, not an idle worker.

The watchdog qualification document records later Accelerate pin history. Those commits are not re-tested by this review, and quoting them does not close a task.

## Limitations that stay explicit

- Live model: `provider_invoked` is false. This review does not record a live model result for a case.
- Corpus: the pinned `search_us_code_corpus_from_parameters` effect is unavailable. No corpus result is claimed.
- Prover: no prover was executed. Parsed IR and an unexecuted proof are not proof.
- Remote durability: `kit_network_enabled` is false on the inventory probe. A local write, a queue, or a content address is not verified remote durability.
- Screenshot files and the completed GUI60 program, including its 60 callbacks and 132-case history, do not complete `complaint-gui-ux-overhaul`.

Measured capture limits, copied from the manifest:

- Lawyer assignment is accepted through real UI; owner review envelope is not shared in this baseline, so closed/unavailable content is not depicted as opened.
- The existing workspace header can still show No case selected/access denied after actual backend authentication and case-context bootstrap; the functional pending inquiry below is real.
- Evidence screenshots show genuine unsaved form, not successful upload, annotation, classifier, or replication.
- Draft view is a real blocked/not-generated state; no generated complaint is fabricated.
- All cases, actors, source text, credentials, keys and messages are newly authored synthetic fixtures.
