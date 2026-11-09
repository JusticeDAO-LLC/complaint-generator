# REF-006 Reconciliation Guardrail

Date: 2026-07-21
Fingerprint: fde3722148ab64b3223caf20029a0bf7d0467dad
Kind: main_checkout_dirty
Reason: main_checkout_dirty
Candidate count: 1
Priority: P1
Track: ops

## Main Checkout Status

- ` M scripts/refactor_agent_supervisor.py`

## Main Checkout Evidence

- Path categories: `modified=1`
- Status paths:
  - `scripts/refactor_agent_supervisor.py`
- Name status:
  - `M	scripts/refactor_agent_supervisor.py`
- Diff stat:
  - `scripts/refactor_agent_supervisor.py | 29 +++++++++++++++++++++++++++++`
  - ` 1 file changed, 29 insertions(+)`

## Sample Branches Or Worktrees

- `implementation/ref-004-attempt-1-1784663183` at `/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g1-g1-s2/ref-004-attempt-1-1784663183`

## Why This Blocks Progress

The implementation supervisor can only merge clean inactive implementation
worktrees when the main checkout is safe to mutate. Dirty main checkouts and
dirty backlogged worktrees are preserved until a deliberate reconciliation task
decides whether to commit, merge, discard generated duplicates, or split
unresolved work into follow-up tasks.

## Suggested Repair

Inspect the dirty paths and sampled worktrees, resolve any real work into
reviewable commits or follow-up tasks, rerun the supervisor reconciliation pass,
and verify that either the candidate merge count decreases or the dirty
worktree cleanup skip count decreases.

## Reconciliation Plan

Work surface: `1` candidates, `1` sampled records.

### Suggested Actions

- `classify_main_checkout_changes`: inspect git status, diff stats, submodule status, and generated artifacts before merges
- `preserve_or_split_main_checkout_work`: commit intentional changes or convert unresolved changes into follow-up tasks; never discard unknown work
- `rerun_worktree_reconciliation`: rerun reconcile_backlogged_worktrees once the main checkout is clean enough to mutate

### Safety Constraints

- Do not discard dirty or untracked content unless it is proven redundant with the target ref.
- Prefer commits, merges, or explicit follow-up tasks over destructive cleanup.
- Keep todo, objective, discovery, and strategy files parseable after reconciliation.

### Success Signals

- `candidate_count_decreases`
- `dirty_worktree_group_count_decreases`
- `main_checkout_dirty_becomes_false`
- `cleanup_or_reconciliation_pass_processes_candidates`

## Machine Readable Manifest

```json
{
  "actions": [
    {
      "action": "classify_main_checkout_changes",
      "automation": "inspect git status, diff stats, submodule status, and generated artifacts before merges",
      "scope": "repo_root"
    },
    {
      "action": "preserve_or_split_main_checkout_work",
      "automation": "commit intentional changes or convert unresolved changes into follow-up tasks; never discard unknown work",
      "scope": "repo_root"
    },
    {
      "action": "rerun_worktree_reconciliation",
      "automation": "rerun reconcile_backlogged_worktrees once the main checkout is clean enough to mutate",
      "scope": "backlogged_worktrees"
    }
  ],
  "candidate_count": 1,
  "conflict_path_counts": {},
  "dedupe_key": "reconciliation_guardrail:main_checkout_dirty",
  "fingerprint": "fde3722148ab64b3223caf20029a0bf7d0467dad",
  "kind": "main_checkout_dirty",
  "main_dirty_evidence": {
    "diff_stat": "scripts/refactor_agent_supervisor.py | 29 +++++++++++++++++++++++++++++\n 1 file changed, 29 insertions(+)",
    "name_status": "M\tscripts/refactor_agent_supervisor.py",
    "path_categories": {
      "modified": 1
    },
    "status_paths": [
      "scripts/refactor_agent_supervisor.py"
    ],
    "status_short": [
      " M scripts/refactor_agent_supervisor.py"
    ]
  },
  "reason": "main_checkout_dirty",
  "safety_constraints": [
    "Do not discard dirty or untracked content unless it is proven redundant with the target ref.",
    "Prefer commits, merges, or explicit follow-up tasks over destructive cleanup.",
    "Keep todo, objective, discovery, and strategy files parseable after reconciliation."
  ],
  "sample_branches": [
    "implementation/ref-004-attempt-1-1784663183"
  ],
  "sample_count": 1,
  "sample_status_paths": [
    "scripts/refactor_agent_supervisor.py"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g1-g1-s2/ref-004-attempt-1-1784663183"
  ],
  "success_signals": [
    "candidate_count_decreases",
    "dirty_worktree_group_count_decreases",
    "main_checkout_dirty_becomes_false",
    "cleanup_or_reconciliation_pass_processes_candidates"
  ],
  "top_conflict_paths": []
}
```

## Reconciliation Result

Resolved: 2026-07-21T20:24Z

- Classified the dirty main checkout evidence from this guardrail. The original
  blocker was `scripts/refactor_agent_supervisor.py`; that work was preserved on
  main by the prior reconciliation commit
  `f20703f1bb2a732fa78daf8c031fb315232baa1e`
  (`chore(refactor): preserve merge watchdog pacing`).
- Before the rerun, the current main checkout had a separate generated
  retry-budget guardrail artifact for `refactor-g2-g2-s1`. That output was
  preserved with commit `81ab5a8ff25abe126f321a2894f328c7f0272597`
  (`chore(refactor): preserve ref-005 retry guardrail`) so the reconciliation
  pass could safely mutate main if needed.
- Reran the scoped `refactor/g1/g1-s2` reconciliation-only supervisor pass at
  `2026-07-21T20:24:41Z` with `--worktree-reconciliation-max-merges 1` and
  `--no-worktree-scan-cache`.
- The rerun event records `main_checkout_dirty: false`,
  `raw_main_checkout_dirty: false`, and an empty `main_status_short` list.
- The `main_checkout_dirty` blocker count for this guardrail decreased from
  `1` to `0`. The pass processed one remaining candidate and classified it as a
  separate `preflight_merge_conflict` on `scripts/refactor_agent_supervisor.py`;
  REF-006 no longer owns a dirty-main blocker.

Post-repair evidence source:
`data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/state/agent_refactor_g1_g1_s2_supervisor_events.jsonl`
contains the rerun pass with target signature
`81ab5a8ff25abe126f321a2894f328c7f0272597`,
`candidate_count: 1`, `processed_count: 1`,
`preflight_blocked_count: 1`, and `reconciliation_guardrail_count: 0`.
