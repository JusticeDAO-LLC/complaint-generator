# REF-027 Reconciliation Guardrail

Date: 2026-07-22
Fingerprint: 8e671dee15462088b7865d93c6fb68f81a0a50ac
Kind: main_checkout_dirty
Reason: main_checkout_dirty
Candidate count: 3
Priority: P1
Track: ops

## Main Checkout Status

- ` M data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
- ` M data/refactor_supervisor/refactor_goals.json`
- ` M docs/REFACTOR_SUPERVISOR_TASKBOARD.md`

## Main Checkout Evidence

- Path categories: `modified=3`
- Status paths:
  - `data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
  - `data/refactor_supervisor/refactor_goals.json`
  - `docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
- Name status:
  - `M	data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
  - `M	data/refactor_supervisor/refactor_goals.json`
  - `M	docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
- Diff stat:
  - `.../bundle_lanes/bundle_lanes.json                 | 5464 ++++++++++----------`
  - ` data/refactor_supervisor/refactor_goals.json       |   68 +-`
  - ` docs/REFACTOR_SUPERVISOR_TASKBOARD.md              |   24 +-`
  - ` 3 files changed, 2772 insertions(+), 2784 deletions(-)`

## Sample Branches Or Worktrees

- `rescue/worktree/implementation-ref-009-ef4c59be25cf-attempt-1-1784694550-608927e0bf4d` at `/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-009-ef4c59be25cf-attempt-1-1784694550`
- `rescue/worktree/implementation-ref-016-30a2a7d729bd-attempt-1-1784688023-807bc7a20043` at `/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-016-30a2a7d729bd-attempt-1-1784688023`
- `rescue/worktree/implementation-ref-016-30a2a7d729bd-attempt-1-1784690090-6077ba322261` at `/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-016-30a2a7d729bd-attempt-1-1784690090`

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

Work surface: `3` candidates, `3` sampled records.

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
  "candidate_count": 3,
  "conflict_path_counts": {},
  "dedupe_key": "reconciliation_guardrail:main_checkout_dirty",
  "fingerprint": "8e671dee15462088b7865d93c6fb68f81a0a50ac",
  "kind": "main_checkout_dirty",
  "main_dirty_evidence": {
    "diff_stat": ".../bundle_lanes/bundle_lanes.json                 | 5464 ++++++++++----------\n data/refactor_supervisor/refactor_goals.json       |   68 +-\n docs/REFACTOR_SUPERVISOR_TASKBOARD.md              |   24 +-\n 3 files changed, 2772 insertions(+), 2784 deletions(-)",
    "name_status": "M\tdata/refactor_supervisor/bundle_lanes/bundle_lanes.json\nM\tdata/refactor_supervisor/refactor_goals.json\nM\tdocs/REFACTOR_SUPERVISOR_TASKBOARD.md",
    "path_categories": {
      "modified": 3
    },
    "status_paths": [
      "data/refactor_supervisor/bundle_lanes/bundle_lanes.json",
      "data/refactor_supervisor/refactor_goals.json",
      "docs/REFACTOR_SUPERVISOR_TASKBOARD.md"
    ],
    "status_short": [
      " M data/refactor_supervisor/bundle_lanes/bundle_lanes.json",
      " M data/refactor_supervisor/refactor_goals.json",
      " M docs/REFACTOR_SUPERVISOR_TASKBOARD.md"
    ]
  },
  "reason": "main_checkout_dirty",
  "safety_constraints": [
    "Do not discard dirty or untracked content unless it is proven redundant with the target ref.",
    "Prefer commits, merges, or explicit follow-up tasks over destructive cleanup.",
    "Keep todo, objective, discovery, and strategy files parseable after reconciliation."
  ],
  "sample_branches": [
    "rescue/worktree/implementation-ref-009-ef4c59be25cf-attempt-1-1784694550-608927e0bf4d",
    "rescue/worktree/implementation-ref-016-30a2a7d729bd-attempt-1-1784688023-807bc7a20043",
    "rescue/worktree/implementation-ref-016-30a2a7d729bd-attempt-1-1784690090-6077ba322261"
  ],
  "sample_count": 3,
  "sample_status_paths": [
    "data/refactor_supervisor/bundle_lanes/bundle_lanes.json",
    "data/refactor_supervisor/refactor_goals.json",
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-009-ef4c59be25cf-attempt-1-1784694550",
    "/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-016-30a2a7d729bd-attempt-1-1784688023",
    "/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-016-30a2a7d729bd-attempt-1-1784690090"
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
