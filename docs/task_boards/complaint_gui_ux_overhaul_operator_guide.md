# Screenshot-led UX campaign operations

The separately scoped `complaint-gui-ux-overhaul` program contains9goals,22subgoals and68tasks, `CIMP-UX-01` through `CIMP-UX-68`. Its human plan is [implementation_plan.md](../ux/complaint_ux_overhaul/implementation_plan.md). The experience contract is [experience_contract.md](../ux/complaint_ux_overhaul/experience_contract.md). The measured before/after record is [before_after_review.md](../ux/complaint_ux_overhaul/before_after_review.md), bound to [screenshot_manifest.json](../ux/complaint_ux_overhaul/baseline/screenshot_manifest.json) and [screenshot_driven_findings.json](../ux/complaint_ux_overhaul/screenshot_driven_findings.json). The earlier GUI60 program remains completed historical evidence and is not rewritten. Completing that 60-task program, its callbacks, or its 132-case history does not complete this program. The 13 baseline screenshot files do not complete it either.

## Configuration

The exact implementation route is `ipfs_accelerate_py.llm_router`, provider `grok_cli`, model `grok-4.7`, fallback disabled. The campaign initially uses one worktree/worker, three attempts,64turns,90-second startup grace,180-second stall limit and900-second implementation/validation budgets. The dedicated watchdog is limited to two recoveries per incident and preserves holds, uncertainty and paid attempts.

Development-provider permission does not authorize a real complaint's egress. Tests use new synthetic data, actual pinned SDKs/Chromium/Node, private HOME/TMP/XDG/orchestration roots and inherited denial of non-Unix sockets. No real external messages, filing, deployments, dependency installation or recursive SDK/CommonCrawl operations are authorized by the plan.

Keep the SDK pins and active specification stable during execution. A capability gap requires a bounded measured compatibility decision, not silent fallback or a floating update. Admins have operations metadata only by default; complaint analysis requires a separate case/key grant. Notes, labels, conversations and model suggestions require explicit adoption before becoming evidence or accepted answers. A user-marked deadline is an attributed reminder, not a derived legal deadline.

The qualified supervisor repair promotes only the Accelerate pin from its initial baseline at a verified stopped boundary. See [watchdog recovery qualification](complaint_gui_ux_overhaul_watchdog_recovery.md) for the exact revision, measured defects, validation and preserved accounting. Report this promoted pin in subsequent SDK inventories; keep the specification and historical baseline unchanged.

## Author, ingest and start

Use a new canonical UID-owned0700state directory and an empty dedicated0700worktree root outside both source and state. Prefer a filesystem with space for the observed cold-checkout estimate plus overhead; the runtime checks capacity again before execution. Use a named local integration branch and commit the specification, generated plan/board, screenshots, contracts and required source before launch. Native workers check out `HEAD`.

Set `UX_ROOT`, `UX_STATE`, `UX_WORKTREES` and `UX_PYTHON` to the actual operator-selected locations. The shared public entry point is:

```bash
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" prepare \
  --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE"
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" doctor \
  --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE" --worktree-root "$UX_WORKTREES"
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" start \
  --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE" --worktree-root "$UX_WORKTREES"
```

`prepare` validates and round-trips the Native formal contract and preserves an existing matching board. It starts no model and completes no task. `doctor` validates current privacy/resources/configuration and credential presence; it does not verify login, quota or actual execution. `start` publishes actual owned process identity, canonical plan/spec generation and worktree binding through normal code. Do not add fields to saved launcher JSON by hand.

## Observe actual work

```bash
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" status \
  --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE"
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" watchdog \
  --install-user-timer --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE"
```

Use the installed campaign-specific unit name returned by the installer. Confirm it is enabled/active and that its observations bind the expected plan ID and exact spec SHA. Require the actual owned launcher and daemon, fresh heartbeat, current canonical task CID/attempt, and Grok work/tool activity or genuine validation. A PID, status label, screenshot, doctor result or saved packet alone is not progress evidence.

Normal `recover` uses the same explicit root/spec/state. Never replace state to obtain a clean result, delete claims/leases by hand, synthesize events/callbacks, reset a budget, signal unrelated processes, or reinterpret application `awaiting_user` as a development worker allowed to wait indefinitely.

## Acceptance and completion

Every task has one focused behavioural module, meaningful positive/negative checks and zero required skips. Screenshot tasks need real DOM/API/cryptographic-state assertions and owned process cleanup. Old132-case GUI acceptance remains historical regression coverage, not the new program's closure. The new grouped UX acceptance controller is delivered by task68; do not treat an unimplemented command as a passing test.

Task68 validates its controller while self-pending. After its actual Native callback and settled queue, the operator runs the full current-source acceptance outside any individual900-second worker. Then invoke the production read-only `campaign_completion.verify_campaign_completion` using this explicit specification and actual state. It must authenticate all68canonical tasks and actual integration/history. No callback or task status is manufactured by this guide or the completion contract.

Preserve unresolved legal/factual/evidentiary gaps and the limitations below. No actionable interview question, parsed IR, screenshot comparison, successful storage write or completed software campaign establishes legal sufficiency or successful filing.

## Primary journeys

The handoff journeys are the measured baseline states, not a redesigned mock. Each one is identified in the before/after review by screenshot id, route, viewport, and file hash:

- Public entry on `/` (`01-home-desktop`).
- Authenticated workspace whose working inquiry still sits under the stale `No case selected` / access-denied header (`02-workspace-desktop`). Preserve that defect.
- One server-issued mediator question with Why, on desktop and mobile (`03-mediator-question-desktop`, `04-mediator-question-mobile`).
- Unsaved evidence composer, not a successful upload (`05-evidence-composer-desktop`, `06-evidence-composer-mobile`).
- Draft panel in a real not-generated state (`07-draft-desktop`).
- Owner case list with a pending lawyer invitation (`08-cases-owner-desktop`).
- Assigned lawyer workspace with no shared content envelope (`09-lawyer-workspace-desktop`).
- Owner and authorized-recipient correspondence (`10-correspondence-owner-desktop`, `11-correspondence-lawyer-mobile`).
- Operational admin account metadata on desktop and mobile (`12-admin-accounts-desktop`, `13-admin-accounts-mobile`).

Chat, split, and rich workspace are views of one encrypted session. Ordinary pages do not lead with raw grant ids, polling intervals, or inquiry hashes. Uncertainty, failure, and access denial stay visible.

## Role, consent, and key boundaries

Owners invite. Recipients accept a real scope and a real key grant. A lawyer role alone grants no case content. Recipient review can proceed while the owner's wallet is locked only when an accepted recipient key grant actually permits it. Operational admins see accounts, roles, assignments, counts, and operational state. Complaint-content review needs a separate case authorization and key access. Admin status, display-role text, and the current UI selection never supply a decryption key.

The signed-in actor is not the canonical encrypted owner. Content-addressing is not encryption. Lock, revocation, rotation, and case or actor switches clear rendered plaintext and abort stale work. A missing key does not mint a replacement case. Browser storage is not the complaint record.

Local processing is the default. Purpose-scoped case consent is explained and persisted before any minimized remote inference, and current membership, keys, consent, and revisions are rechecked before a late result is accepted. Development use of `grok_cli` / `grok-4.7` does not consent to case-data egress. The baseline manifest records `provider_invoked` false. This handoff does not record a live model result.

## Evidence adoption and graph provenance

Receipt of an artifact is not authenticity or relevance. An extracted passage keeps its artifact version, page or span, and extraction lineage; untrusted source text stays data. A comment or annotation is an attributed note on an exact evidence version. It is not new evidence and it is not an intake answer by default. A classifier is a user label or an attributed suggestion. It is not verified support and it is not governing law. A support link is an explicit accepted relationship to a factual assertion or a current legal requirement, and it keeps uncertainty and provenance. A review decision is a current authorized human action on an exact target revision. It is distinct from model output and from machine proof.

The factual graph records what a person asserted and what an explicitly adopted evidence passage supports, including corrections, contradictions, and uncertainty. The legal dependency graph derives requirements from exact admitted legal sources, with jurisdiction, applicable date, source version, and passage identity. A source search hit is discovery. Admission is not applicability. Applicability is not proof. Model prose, a parsed formula, graph consistency, a confidence score, and an unexecuted proof are not governing law. The pinned corpus search `search_us_code_corpus_from_parameters` is callable and its effect qualification is unavailable. Do not describe a corpus result or a prover result that this program has not executed.

Changes to authority, date, jurisdiction, facts, evidence, key access, or consent retire affected stale projections before reuse.

## Finite stopping

Read the ceilings from the current runner and watchdog, and do not raise them in an incident:

- Startup grace is `STARTUP_SECONDS` 90.
- Stall limit is `STALL_SECONDS` 180.
- Implementation and validation budget is `TIMEOUT_SECONDS` 900.
- Task attempts stay at 3. Provider turns stay at `IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS` 64.
- Watchdog recoveries stay at 2 per incident. The preserved watchdog action deadline is 1200000 milliseconds.
- Configured supervisor profile flags are `--implementation-timeout` 900, `--implementation-max-timeout` 900, `--implementation-log-stall-seconds` 180, `--max-task-attempts` 3, `--max-restarts` 5, and `--validation-max-workers` 1.

Product `awaiting_user` is a person waiting. It is not a development worker that may run without progress. Holds, uncertain ledgers, and paid attempts stay in place when a ceiling is hit. A capped, paused, cancelled, saturated, or unavailable interview is not legal sufficiency.

## Scoped recovery commands

Recovery uses the same `UX_ROOT`, specification, and `UX_STATE` as start. It does not retarget another campaign, replace state, delete claims, synthesize callbacks, or reset a budget.

```bash
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" status \
  --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE"
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" stop \
  --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE"
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" recover \
  --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE"
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" watchdog \
  --once --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE"
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" start \
  --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE" --worktree-root "$UX_WORKTREES"
```

`recover` is the public stalled-worker command. `watchdog --once` is one durable progress check for the timer. `watchdog --install-user-timer` installs that campaign's timer and does not recover a foreign validator. Resume is `start` on the same epoch, not a second campaign. Do not signal unrelated processes.

Measured watchdog qualifications, including the Accelerate pin history, stay in [complaint_gui_ux_overhaul_watchdog_recovery.md](complaint_gui_ux_overhaul_watchdog_recovery.md). Quoting that history does not re-qualify it and does not complete `CIMP-UX-67`.

## Tested revisions and limitations

Record these revisions as measured inputs, not as closure:

- Application baseline commit `6f27c60c3b49b8bad49088bd46e788fa31c646eb` from the screenshot manifest.
- Declared SDK pins from [sdk_hook_inventory.json](../ux/complaint_ux_overhaul/sdk_hook_inventory.json): Accelerate `947f873e407efd9b12c551a5e69a9b62819b9c4e` (checkout unavailable), Datasets `b857f28462bfbb9cbf02232a79cdefcaa1ef1bc7`, Kit `0007f735b90215fa611f39aa558eb512a493b8af`. Pins stay exact. This handoff does not float them.
- Baseline Node content hash `5796fd9700e83170bc7ddfdf7f18858c794a9f91cb39dd6f9e95060b292f2563` and Chromium content hash `20ffc88be1c6f7dc8351bebfaca965ff9a07617bddf696f0b67ef85e5868b29a`.

Explicit limitations, each of which blocks a success claim:

- Live model: the baseline capture did not invoke a provider. A development route is not a live case-model result.
- Corpus: `search_us_code_corpus_from_parameters` has no qualified effect on the pinned checkout. An empty-parameter refusal is not a corpus search result.
- Prover: an unexecuted proof, parsed IR, or formal-logic adapter call is not a prover result and is not governing law.
- Remote durability: the inventory probe records `kit_network_enabled` false. A local write, a queue, or a content address is not verified remote durability.

The authoring route for this handoff used the measured manifest, findings, and contract. It does not claim that the model inspected screenshot pixels.
