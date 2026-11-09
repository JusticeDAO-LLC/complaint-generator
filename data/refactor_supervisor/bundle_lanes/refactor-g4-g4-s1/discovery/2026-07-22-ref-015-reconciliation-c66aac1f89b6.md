# REF-015 Reconciliation Guardrail

Date: 2026-07-22
Fingerprint: 3a2a8187bdd6c81d29b026a91c15be4cd0d6dc4f
Kind: main_checkout_dirty
Reason: main_checkout_dirty
Candidate count: 1
Priority: P1
Track: ops

## Main Checkout Status

- ` M data/refactor_supervisor/bundle_lanes/bundle_lanes.json`

## Main Checkout Evidence

- Path categories: `modified=1`
- Status paths:
  - `data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
- Name status:
  - `M	data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
- Diff stat:
  - `.../bundle_lanes/bundle_lanes.json                 | 5464 ++++++++++----------`
  - ` 1 file changed, 2732 insertions(+), 2732 deletions(-)`

## Sample Branches Or Worktrees

- `rescue/worktree/implementation-ref-013-d4fc48536ac0-attempt-1-1784693051-3c65dce8f628` at `/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g4-g4-s1/ref-013-d4fc48536ac0-attempt-1-1784693051`

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
  "fingerprint": "3a2a8187bdd6c81d29b026a91c15be4cd0d6dc4f",
  "kind": "main_checkout_dirty",
  "main_dirty_evidence": {
    "diff_stat": ".../bundle_lanes/bundle_lanes.json                 | 5464 ++++++++++----------\n 1 file changed, 2732 insertions(+), 2732 deletions(-)",
    "name_status": "M\tdata/refactor_supervisor/bundle_lanes/bundle_lanes.json",
    "path_categories": {
      "modified": 1
    },
    "status_paths": [
      "data/refactor_supervisor/bundle_lanes/bundle_lanes.json"
    ],
    "status_short": [
      " M data/refactor_supervisor/bundle_lanes/bundle_lanes.json"
    ]
  },
  "reason": "main_checkout_dirty",
  "safety_constraints": [
    "Do not discard dirty or untracked content unless it is proven redundant with the target ref.",
    "Prefer commits, merges, or explicit follow-up tasks over destructive cleanup.",
    "Keep todo, objective, discovery, and strategy files parseable after reconciliation."
  ],
  "sample_branches": [
    "rescue/worktree/implementation-ref-013-d4fc48536ac0-attempt-1-1784693051-3c65dce8f628"
  ],
  "sample_count": 1,
  "sample_status_paths": [
    "data/refactor_supervisor/bundle_lanes/bundle_lanes.json"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g4-g4-s1/ref-013-d4fc48536ac0-attempt-1-1784693051"
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
