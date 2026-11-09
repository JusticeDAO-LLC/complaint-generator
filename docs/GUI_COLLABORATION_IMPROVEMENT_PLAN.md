# Private GUI interview and lawyer collaboration improvement plan

This is a new program built on the completed terminal and mediator work. The
earlier 58-task intake and 44-task mediator programs remain historical, completed
programs. Their boards, claims, attempts, receipts and qualifications are not
reused to complete these GUI tasks.

The executable specification is
`docs/task_boards/complaint_gui_collaboration_spec.json`. It contains **14 goals,
31 subgoals and 60 bounded tasks**. The compiler emits the matching Native
`FormalWorkPlan` and taskboard under the distinct `complaint-gui-collaboration`
namespace. Compilation and ingestion do not constitute task completion.

## Begin with the actual browser journey

The baseline uses source revision `2c1439a7029eb9035338133210d8b43319add8a4` and
its pinned Accelerate, Data and Kit owners. A real Chromium audit used unmodified
assets, pipe control and browser requests dispatched into the actual ASGI app,
with private synthetic cases and inherited non-Unix socket denial. It did not
use the Node suite's canned `mockApi` responses or read real user sessions.

The audit found concrete gaps:

- Nine protected MCP calls were denied, but the GUI reported synchronized/ready.
- Saving the fixed intake form did not enter the shared graph interview.
- Five legacy claim-element labels reflected supplied assertions as supported
  without corroborating evidence; these are not verified legal support.
- Browser synchronization events and per-user summaries persisted case text in
  plaintext localStorage.
- The GUI lacks the shared inquiry's explanation, correction, graph, resume and
  finite-stop controls, and seven visible inputs lacked programmatic labels.

The existing narrative service is a useful foundation: the synthetic public API
created a factual KG and legal dependency graph, returned a pending inquiry and
revision, supported `/why` without recording an answer, and left legal
sufficiency false. Matching-ID answers currently work without an explicit
revision; the missing browser protocol controls must be qualified for stale and
concurrent writes rather than described as universal answering failure.

Task 01 characterizes those boundaries without declaring a working production
GUI. Its fresh Python ASGI/service observations are distinguished from the
pinned manual DOM, storage and accessibility audit. Task 02 then qualifies mandatory browser evidence through Native's actual
measurement path. Real Node/Chromium binaries and arguments must be narrowly
bound, existing network denial preserved, external origins/service workers
denied, and owned descendants cleaned up. Same-origin requests reach real ASGI
handlers. Real browser credentials, headers and Set-Cookie must survive the
bridge, without an independent HTTPX cookie jar or injected actor authority.
Cookies, headers and downloads need explicit fidelity tests. HTTP
interception does not establish WebSocket, SSE or streaming support. Missing
browsers, denied execution, empty collection or skipped required cases fail the
capability check; they cannot become a successful fallback.

## Product behavior and graph grounding

An authenticated user selects or creates a private case, supplies a narrative,
and answers the current mediator inquiry. Every answer carries its question and
case revision. The interface explains the question's purpose and graph target,
permits unknown/deferred answers, and exposes authorized corrections through the
existing supersession and invalidation path. A cold browser/process resume
restores encrypted inquiry and graph state without replaying effects.

The factual knowledge graph records user assertions and evidence revisions with
source IDs, corrections, contradictions and hypothesis status. The legal
dependency graph derives requirements from admitted authorities with source
passages, jurisdiction, effective dates, applicability, burdens and exceptions.
Factual answers affect support for a rule; they do not rewrite the rule.

The GUI offers distinct factual and legal graph views with inspectable support,
contradiction and missing-evidence links. Source acquisition nominates legal
candidates. Explicit authorized admission binds their version and applicability.
Context or source changes invalidate affected requirements, questions and proof
results. Search snippets, generated prose and supplied receipt JSON are not law.

The interview stops when no actionable question remains or a declared limit,
pause, cancellation or unavailable capability applies. It retains research,
factual and evidentiary gaps. Saturation, all fields filled, a parsed IR or a
completed software taskboard never means the complaint is legally sufficient.

## Users, lawyers and administrative operations

Reuse the existing principal and encrypted-owner boundaries, then extend them
deliberately. Current token registration is in memory and current authorization
assumes the actor owns the resource. Existing session paths are principally
user-scoped. Durable principals, server-owned roles, stable independent case
identity and one case action-policy service come before collaborative content.
Actual app assembly and all legacy HTTP/WebSocket, MCP, review, document and
download paths must use that boundary. `trusted_local=True`, credential hashes,
body-supplied roles and a captured global mediator cannot authorize production
multi-user requests.

Task 06 supplies a reusable static route-composition owner called by the actual
app variants. Subsequent case, graph, message and admin APIs declare that owner
in their change scope and must be mounted there. Task 08 initially creates
owner-only cases; membership and key grants are later explicit capabilities.
Account disabling and staff demotion must invalidate existing sessions as well
as deny new requests.

| Actor | Default access |
|---|---|
| Case owner | Own authorized case, collaborators and processing choices |
| Assigned lawyer | Accepted case membership and explicit granted actions/keys |
| Operational admin | Minimal account, role, assignment and operational metadata |
| Unassigned lawyer or stranger | No case content |

A lawyer role alone grants no case access. Owners invite participants; recipients
accept scopes and key access. Keep the actual actor distinct from the canonical
encrypted artifact owner. Existing tenant/case/principal/revision AAD must not be
bypassed by owner impersonation. Introduce recipient-bound key grants, expiry,
revocation, rotation and migration compatibility before shared content opens.
Revocation denies future access; it cannot erase previously downloaded content.

Users and assigned lawyers receive encrypted case conversations, attachments,
review tasks and in-app notifications. Sends and reads are authorized and
idempotent. Messages remain conversations until an explicit accepted action
adopts them as evidence, an intake answer or an allowed model input. Shared
editing uses expected revisions, actor attribution and immutable review history.
The first messaging transport can use qualified HTTP polling; no unqualified
WebSocket shortcut is required. External messages, email/SMS delivery and court
filing are outside this campaign.

Admins can analyze account and assignment operations using minimal scoped
metadata. Administrative authority does not supply an ambient decryption key or
permission to inspect all complaints. Case-content analysis requires a separate
case grant. Notifications, operational logs, browser caches and error reports
must not disclose complaint text, evidence, messages, credentials or keys.

## Reuse pinned submodule owners

Use `ipfs_accelerate_py.llm_router` with provider `grok_cli`, model `grok-4.7`, and
fallback disabled. Development implementation authorization and per-case user
egress consent are separate. Purpose, minimization and current consent/grants
apply before inference and again before accepting late results.

Use the existing mediator hooks and `ipfs_datasets_py` KG, legal-corpus and
formal adapters. Reuse canonical LegalIR, source obligations, contextual
definitions, declaration/applicability and source-correspondence owners at the
declared revisions. Executed proof, conditional/degraded status and unavailable
engines remain distinct. Human review, model suggestions and machine proof are
separate attributed records.

Use `ipfs_kit_py` through the existing private-storage/manifest owners. Encrypt
before storage or replication, commit complete revision sets, verify ciphertext
readback, and distinguish local commit, queued replication, pinning and verified
replicas. Include graphs, inquiries, proof references, grants, messages, audit
events, attachments and derived indexes. Migrate only explicitly selected
authorized cases; verify encrypted readback before cleanup. Missing keys or
backends cannot create an empty replacement case or trigger plaintext fallback.

## Native execution and acceptance

Only `CIMP-GUI-01` is initially ready. Browser GUI tasks depend on Task 02's
qualified evidence. Authenticated case identity/action policy precede content
APIs; membership and key grants precede lawyer collaboration; purpose/consent
precede model-backed interview and extraction. Revocation precedes shared audit
and downstream collaborative operations, and lawyer review follows actual
assignment. The final task depends on every
other task. Each task declares focused outputs, behavioral acceptance and a real
Python pytest command so Native can independently measure collection, case
phases, JUnit, current source and positive AST evidence.

Use a fresh private campaign state, merge queue and dedicated mode-0700 external
worker root. Retain the existing 64-turn, 900-second implementation limits,
three-attempt cap and pool size one. Workers do not install packages, change SDK
pins, deploy, push, read existing private cases or invent runtime input. Required
tests cannot skip. A missing capability produces an honest failure or explicit
product unavailable state, with no fabricated proof of success.

Run `prepare`, `doctor` and `start` with the new explicit specification and state
paths. Install this campaign's own persistent progress watchdog and expected
plan/spec pins. A doctor or PID alone does not establish startup: observe the
actual Grok route, canonical active task/attempt, fresh owned activity, measured
validation, merge and normal completion callback. The watchdog preserves holds
and attempts and uses verified bounded reconciliation; legitimate user-input
waits are different from development workers stalled without progress.

Final acceptance uses actual DOM/application handlers, synthetic local sources,
encrypted persistence, multi-role isolation, stale edits, revocation, failed
dependencies and finite stopping. Historical Native completions are verified
through canonical callbacks and a settled merge queue. Local synthetic GUI
acceptance remains separate from optional future live corpus, model, prover or
remote-replica qualification.
