# Complaint supervisor progress watchdog

The `watchdog` command checks one explicit repository, plan and campaign state.
It uses `ipfs_accelerate_py.agent_supervisor.rescue.campaign_watchdog` and Native's
persisted programmatic recovery controller. It makes no direct model calls,
manufactures no task completion, and never resets implementation attempts or
answers complaint questions. A normal Native restart can resume authorized
Grok work within the existing implementation budget.

The older `watch` command observes a single launcher for at most six hours and
closes its orphan after exit. Use the new progress watchdog for recurring checks
and recovery. Avoid running competing recovery controllers for the same campaign.

## Run or install

Use the checkout with its pinned submodules and the Python environment used by
the Native supervisor. Keep the explicit paths from the campaign's launcher.

```bash
python scripts/run_complaint_improvement_supervisor.py watchdog \
  --repo-root "$REPO_ROOT" --spec "$SPEC" --state-dir "$CAMPAIGN_STATE" \
  --once --stop-completed

python scripts/run_complaint_improvement_supervisor.py watchdog \
  --repo-root "$REPO_ROOT" --spec "$SPEC" --state-dir "$CAMPAIGN_STATE" \
  --install-user-timer
```

Without `--once`, the command checks every 60 seconds until it verifies completion.
The installer creates only this campaign's dedicated user service and minutely
calendar timer, verifies the units, enables the timer and runs its first check.
It refuses conflicting or customized unit files, but can atomically upgrade the
exact previous managed service for the same campaign. The timer persists across user
manager restarts; unattended boot operation requires an existing lingering user
manager. The installed service binds the expected plan ID and specification hash.
The timer also checks 60 seconds after the service becomes inactive using a
monotonic interval. This covers calendar gaps during clock changes without
starting competing checks while recovery is still running.

The installer captures a bounded executable PATH: the selected Python and Grok
entrypoint directories, discovered Node/Docker/Git directories and system
executable directories. A Grok symlink keeps its entrypoint directory. This fixes
background services that could not find Grok although interactive startup worked.
It copies no credentials, sources no shell profiles, and leaves validation's
separately sealed executable path unchanged. Missing Grok fails installation
explicitly. The exact previous calendar-only managed timer can be upgraded to
include the monotonic interval. Custom timer settings and campaign-specific
drop-ins remain intact.

The service intentionally uses `KillMode=process`: Native's public `start`
detaches its successor, but detachment does not escape a systemd cgroup. Ending
a watchdog check must not kill the newly started supervisor. Native's verified
public `stop` remains responsible for its process tree and container cleanup.
The service timeout allows bounded Native reconciliation and startup work;
implementation attempts retain their existing 900-second deadline and caps.

Inspect `CAMPAIGN_STATE/watchdog/latest.json` for the last result, reason,
completion evidence, recovery stage and typed `preflight` diagnostics.
`preflight.reasons` distinguishes `grok_executable_missing`,
`provider_auth_material_missing`, `private_runtime_unavailable`,
`worktree_capacity_insufficient` and `resource_capacity_unavailable`. A null
component flag means it was not observed, rather than that it failed. The summary
excludes credential values and raw provider/error bodies. The command prints a
compact summary.
Use `systemctl --user status UNIT.timer` and `journalctl --user -u UNIT.service`,
with the unit name returned by installation, to inspect scheduling and execution.
Disable it with `systemctl --user disable --now UNIT.timer`.

## Recovery decisions

Healthy provider or validation progress is observed without restarting. A
heartbeat or PID alone does not count as work. Startup grace derives from the
actual launch or task-selection time; polling cannot extend it.
An idle selector or blocked queue with logically ready tasks and no active
worker is treated as lack of progress after the stall threshold. A board with
unmet dependencies or an explicit hold remains held.

A recoverable failure must be observed twice, at least 30 seconds apart, with
the same task and progress identity. Changing the owner resets confirmation,
but does not refund the incident's recovery budget. The ledger survives process
restarts and permits at most two recovery actions per incident with a cooldown.

Each action rechecks the campaign, owner, task, progress, holds and attempt maps.
It uses public `stop`, stopped-only `recover`, `doctor`, and `start` in order.
The stop and start compare the exact observed launcher under the launcher lock.
Only verified Native reconciliation permits restarting, and fresh provider or
validation work establishes recovery. Native retains task selection, paid
attempt accounting, validation, merging and its normal completion callback.

An automatic stop is recorded only after Native verifies closure. The record
binds the exact stopped launcher and shutdown proof, allowing a later check to
resume a known automatic stop. An operator stop changes that binding and is
held. Temporary preflight unavailability waits without consuming another repair.
Unknown or interrupted effects remain recorded as uncertain rather than being
repeated blindly.

A stopped ordinary attempt can retain a dead repo-wide claim while its task
is still pending. After the existing launcher, recovery, checkout and settled
merge-queue guards have proved closure, `recover` may use Native's public
`review_quiesced_pending_task_claim` / `reconcile_quiesced_pending_task_claim`
facades. Native independently checks the current task/CID/ordinal, unchanged
workspace, lifecycle, shutdown and claims. This releases only the exact dead
claim. Provider outcome stays unknown: it does not complete a task, settle a
provider callback, refund attempts or grant a new attempt. Normal Native
reconciliation then clears its stale implementation lock. All paid limits,
holds and ordinary selection rules remain in force. The consumer also requires
the full Native task-state payload to remain unchanged across claim release.

An upgraded pinned SDK uses its own public facades automatically. While an
older frozen SDK lacks them, an operator may provision the optional UID-owned
0600 `CAMPAIGN_STATE/pending-task-claim-runtime.json` inside the owned 0700 state
directory. Schema `complaint.pending-task-claim-runtime.v1` binds the exact
repository/state, specification digest, plan ID and plan-file digest, active
SDK root/commit, and approved first-party companion Git root/commit/blob ID and
SHA256. Keep that companion in an immutable proper Git checkout; a sparse
checkout containing its source is sufficient. The consumer verifies actual
Native support-module origins and Git bytes, executes verified companion bytes
under their real canonical module identity, and rechecks the source binding
before and after the public operation. It never adds the companion checkout to
import paths or changes Native package paths or core guards. Native's own Grok
runner import can apply its existing accepted-SDK import bootstrap. A different
already-loaded companion is refused rather than replaced
in-process. Missing runtime preserves the original blocked claim result;
unsafe configuration, changed source or unproved custody fails closed. No
companion is installed or enabled merely by updating this repository.

The additive Native `review_recovery` / `reconcile_recovery` API also handles a
stopped ordinary attempt whose declared outputs are staged. It verifies the
accepted proposal against those exact bytes, the pending task and consumed
ordinal, dead process births, settled queue, authenticated terminal lifecycle
and clean pinned dependencies. Native preserves the candidate in an immutable
commit and rescue ref and retires the old terminal checkout before releasing
the exact claim. It does not complete the task, refund an attempt or grant
another dispatch. The original unchanged-workspace API keeps its narrower
checks.

The Host saves the source-bound request in its private
`pending-candidate-handoffs/` directory before invoking that operation. Recovery
can replay an interruption before or after SDK preservation without skipping
the transfer. An unfinished transfer blocks public start. Materialization
rechecks the released SDK receipt, its digest and candidate manifest, then
creates a fresh registered `rescue/worktree/` checkout under the recorded
worktree root. It verifies the Root Git common directory and independent pinned
dependency clones. If Root advanced, only the exact declared candidate bytes
are transplanted onto the current baseline; overlapping edits are refused.
Fresh Native proposal admission, measured tests and its normal callback are
still required. Creating a worktree grants no task or lifecycle authority.

Validation activity is read from the existing campaign-confined Native catalog
without changing environment routing or creating a missing catalog. Ordinary
validation requires the matching managed child, claim, lease and private log.
Startup reconciliation additionally requires its accepted immutable proposal
and bounded maintenance scope. Only the canonical executor's fresh private
activity pulse proves current validation activity. A heartbeat or provider end
frame cannot substitute for it, and the existing hard deadlines still apply.

Native validation timeouts produce failed measurements. A verified descendant
closure remains a timeout (124); unproved cleanup remains infrastructure failure
(75). A stronger source or policy denial retains denial status (78), with the
executor facts kept as diagnostics rather than authorizing an environment
retry. These outcomes do not settle a callback or change attempt accounting.

An unexpected startup exit can leave public status at `stop_incomplete` before
a new shutdown proof exists. Recovery requires the saved launch birth to be
independently proved dead, a launch that was expected to run, and the current
campaign binding. It then uses the same verified public stop and reconciliation
sequence. Live, reused or unknown identities and operator holds remain refused.

Measured validation explicitly loads a Host-owned, hash-pinned network bootstrap
from its private evidence directory before candidate conftests or collection.
Both collection and execution require before/after libc probes and an owned
network-only proof. The Linux filter permits AF_UNIX sockets and socketpairs,
denies other socket families and x32 socket bypasses, and synchronizes existing
validation threads. Descendant browser/Node processes inherit it. The coordinator,
provider and watchdog processes retain their own execution policies. Python and
pytest startup remain governed by Native's trusted launcher; the plugin's kernel
enforcement begins before conftests. Network proofs supplement source, AST,
JUnit, process and completion evidence rather than replacing those checks.

Place `HOLD` or `OPERATOR_STOP` in `CAMPAIGN_STATE/watchdog/` to prevent automatic
recovery. A temporary maintenance hold prevents dispatch while candidates or
source are reviewed; remove only the maintenance hold you created. Existing
manual holds, cancellation, user-input waits, quarantine,
protected incidents and retry limits remain authoritative. Missing credentials,
legal authority or user answers are reported; the watchdog cannot invent them.

## Completion evidence

All-completed checkboxes alone are insufficient. Completion verification reads
the current canonical Native task identities, authenticates the Native journal,
validates member and callback receipts and historical validation records, checks
commit ancestry, and requires a settled target-bound merge queue with no active
implementation. Input custody is checked before and after the read.

Verified completion creates no recovery incident or new provider work. With
`--stop-completed`, the check closes only the still-matching owned launcher.
Later timer checks continue reporting completed work without restarting it.
Historical execution evidence is explicitly separate from a fresh qualification
of every current source file, live legal corpus, remote model, proof engine or
storage replica.
