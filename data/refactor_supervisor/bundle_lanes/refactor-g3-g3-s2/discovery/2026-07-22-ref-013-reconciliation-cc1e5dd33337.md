# REF-013 Reconciliation Guardrail

Date: 2026-07-22
Fingerprint: cc1e5dd33337df0314b663f8b3c8d9296a322fec
Kind: main_checkout_dirty
Reason: main_checkout_dirty
Candidate count: 1
Priority: P1
Track: ops

## Main Checkout Status

- ` M data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
- ` D data/refactor_supervisor/discovery/2026-07-22-ref-057-objective-gap-08d9b0956fd6.md`
- ` M data/refactor_supervisor/objective_bundles/index.json`
- ` M data/refactor_supervisor/objective_bundles/refactor-g1-g1-s1.todo.md`
- ` M data/refactor_supervisor/objective_bundles/refactor-g1.todo.md`
- ` M data/refactor_supervisor/objective_bundles/refactor-g2.todo.md`
- ` M data/refactor_supervisor/objective_bundles/refactor-g3-g3-s1.todo.md`
- ` M data/refactor_supervisor/objective_bundles/refactor-g3.todo.md`
- ` M data/refactor_supervisor/objective_bundles/refactor-g6.todo.md`
- ` M data/refactor_supervisor/objective_bundles/refactor-g7-g7-s1.todo.md`
- ` M data/refactor_supervisor/objective_bundles/refactor-g7.todo.md`
- ` M data/refactor_supervisor/objective_bundles/refactor-g8.todo.md`
- ` M data/refactor_supervisor/objective_bundles/refactor-g9-g9-s2.todo.md`
- ` M data/refactor_supervisor/objective_bundles/refactor-g9-g9-s4.todo.md`
- ` M data/refactor_supervisor/refactor_goals.json`
- ` M data/refactor_supervisor/refactor_objective_heap.md`
- ` M data/refactor_supervisor/refactor_todo.md`
- ` M docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
- `?? data/refactor_supervisor/bundle_lanes/scheduler_decision_metrics.json`
- `?? data/refactor_supervisor/bundle_lanes/scheduler_metrics.json`

## Main Checkout Evidence

- Path categories: `deleted=1, modified=17, untracked=2`
- Status paths:
  - `data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
  - `data/refactor_supervisor/discovery/2026-07-22-ref-057-objective-gap-08d9b0956fd6.md`
  - `data/refactor_supervisor/objective_bundles/index.json`
  - `data/refactor_supervisor/objective_bundles/refactor-g1-g1-s1.todo.md`
  - `data/refactor_supervisor/objective_bundles/refactor-g1.todo.md`
  - `data/refactor_supervisor/objective_bundles/refactor-g2.todo.md`
  - `data/refactor_supervisor/objective_bundles/refactor-g3-g3-s1.todo.md`
  - `data/refactor_supervisor/objective_bundles/refactor-g3.todo.md`
  - `data/refactor_supervisor/objective_bundles/refactor-g6.todo.md`
  - `data/refactor_supervisor/objective_bundles/refactor-g7-g7-s1.todo.md`
  - `data/refactor_supervisor/objective_bundles/refactor-g7.todo.md`
  - `data/refactor_supervisor/objective_bundles/refactor-g8.todo.md`
  - `data/refactor_supervisor/objective_bundles/refactor-g9-g9-s2.todo.md`
  - `data/refactor_supervisor/objective_bundles/refactor-g9-g9-s4.todo.md`
  - `data/refactor_supervisor/refactor_goals.json`
  - `data/refactor_supervisor/refactor_objective_heap.md`
  - `data/refactor_supervisor/refactor_todo.md`
  - `docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
  - `data/refactor_supervisor/bundle_lanes/scheduler_decision_metrics.json`
  - `data/refactor_supervisor/bundle_lanes/scheduler_metrics.json`
- Name status:
  - `M	data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
  - `D	data/refactor_supervisor/discovery/2026-07-22-ref-057-objective-gap-08d9b0956fd6.md`
  - `M	data/refactor_supervisor/objective_bundles/index.json`
  - `M	data/refactor_supervisor/objective_bundles/refactor-g1-g1-s1.todo.md`
  - `M	data/refactor_supervisor/objective_bundles/refactor-g1.todo.md`
  - `M	data/refactor_supervisor/objective_bundles/refactor-g2.todo.md`
  - `M	data/refactor_supervisor/objective_bundles/refactor-g3-g3-s1.todo.md`
  - `M	data/refactor_supervisor/objective_bundles/refactor-g3.todo.md`
  - `M	data/refactor_supervisor/objective_bundles/refactor-g6.todo.md`
  - `M	data/refactor_supervisor/objective_bundles/refactor-g7-g7-s1.todo.md`
  - `M	data/refactor_supervisor/objective_bundles/refactor-g7.todo.md`
  - `M	data/refactor_supervisor/objective_bundles/refactor-g8.todo.md`
  - `M	data/refactor_supervisor/objective_bundles/refactor-g9-g9-s2.todo.md`
  - `M	data/refactor_supervisor/objective_bundles/refactor-g9-g9-s4.todo.md`
  - `M	data/refactor_supervisor/refactor_goals.json`
  - `M	data/refactor_supervisor/refactor_objective_heap.md`
  - `M	data/refactor_supervisor/refactor_todo.md`
  - `M	docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
- Diff stat:
  - `.../bundle_lanes/bundle_lanes.json                 |  32116 +++---`
  - ` ...026-07-22-ref-057-objective-gap-08d9b0956fd6.md |     56 -`
  - ` .../objective_bundles/index.json                   | 106113 +++++++++++++++++-`
  - ` .../objective_bundles/refactor-g1-g1-s1.todo.md    |     88 +`
  - ` .../objective_bundles/refactor-g1.todo.md          |     46 +-`
  - ` .../objective_bundles/refactor-g2.todo.md          |     88 +`
  - ` .../objective_bundles/refactor-g3-g3-s1.todo.md    |      2 +-`
  - ` .../objective_bundles/refactor-g3.todo.md          |     88 +`
  - ` .../objective_bundles/refactor-g6.todo.md          |      2 +-`
  - ` .../objective_bundles/refactor-g7-g7-s1.todo.md    |      4 +-`
  - ` .../objective_bundles/refactor-g7.todo.md          |      2 +-`
  - ` .../objective_bundles/refactor-g8.todo.md          |     88 +`
  - ` .../objective_bundles/refactor-g9-g9-s2.todo.md    |     23 +-`
  - ` .../objective_bundles/refactor-g9-g9-s4.todo.md    |      4 +-`
  - ` data/refactor_supervisor/refactor_goals.json       |    127 +-`
  - ` .../refactor_supervisor/refactor_objective_heap.md |      8 +-`
  - ` data/refactor_supervisor/refactor_todo.md          |    291 +-`
  - ` docs/REFACTOR_SUPERVISOR_TASKBOARD.md              |     29 +-`
  - ` 18 files changed, 125682 insertions(+), 13493 deletions(-)`
- Untracked paths:
  - `data/refactor_supervisor/bundle_lanes/scheduler_decision_metrics.json`
  - `data/refactor_supervisor/bundle_lanes/scheduler_metrics.json`
  - `data/refactor_supervisor/discovery/2026-07-22-ref-058-objective-gap-eac2cf021fa2.md`
  - `data/refactor_supervisor/discovery/2026-07-22-ref-059-objective-gap-1eba844e57d9.md`
  - `data/refactor_supervisor/discovery/2026-07-22-ref-060-objective-gap-8237ed56b27c.md`
  - `data/refactor_supervisor/discovery/2026-07-22-ref-061-objective-gap-6686ce3fc621.md`
  - `data/refactor_supervisor/discovery/2026-07-22-ref-062-objective-gap-f307b3b05fa3.md`
  - `data/refactor_supervisor/discovery/2026-07-22-ref-064-objective-gap-08d9b0956fd6.md`
  - `data/refactor_supervisor/discovery/2026-07-22-ref-065-objective-gap-eac2cf021fa2.md`
  - `data/refactor_supervisor/discovery/2026-07-22-ref-066-objective-gap-1eba844e57d9.md`
  - `data/refactor_supervisor/discovery/2026-07-22-ref-067-objective-gap-8237ed56b27c.md`
  - `data/refactor_supervisor/discovery/2026-07-22-ref-068-objective-gap-6686ce3fc621.md`
  - `data/refactor_supervisor/discovery/2026-07-22-ref-069-objective-gap-f307b3b05fa3.md`

## Sample Branches Or Worktrees

- `implementation/ref-011-e736afb00644-attempt-1-1784703538` at `/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g3-g3-s2/ref-011-e736afb00644-attempt-1-1784703538`

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
  "fingerprint": "cc1e5dd33337df0314b663f8b3c8d9296a322fec",
  "kind": "main_checkout_dirty",
  "main_dirty_evidence": {
    "diff_stat": ".../bundle_lanes/bundle_lanes.json                 |  32116 +++---\n ...026-07-22-ref-057-objective-gap-08d9b0956fd6.md |     56 -\n .../objective_bundles/index.json                   | 106113 +++++++++++++++++-\n .../objective_bundles/refactor-g1-g1-s1.todo.md    |     88 +\n .../objective_bundles/refactor-g1.todo.md          |     46 +-\n .../objective_bundles/refactor-g2.todo.md          |     88 +\n .../objective_bundles/refactor-g3-g3-s1.todo.md    |      2 +-\n .../objective_bundles/refactor-g3.todo.md          |     88 +\n .../objective_bundles/refactor-g6.todo.md          |      2 +-\n .../objective_bundles/refactor-g7-g7-s1.todo.md    |      4 +-\n .../objective_bundles/refactor-g7.todo.md          |      2 +-\n .../objective_bundles/refactor-g8.todo.md          |     88 +\n .../objective_bundles/refactor-g9-g9-s2.todo.md    |     23 +-\n .../objective_bundles/refactor-g9-g9-s4.todo.md    |      4 +-\n data/refactor_supervisor/refactor_goals.json       |    127 +-\n .../refactor_supervisor/refactor_objective_heap.md |      8 +-\n data/refactor_supervisor/refactor_todo.md          |    291 +-\n docs/REFACTOR_SUPERVISOR_TASKBOARD.md              |     29 +-\n 18 files changed, 125682 insertions(+), 13493 deletions(-)",
    "name_status": "M\tdata/refactor_supervisor/bundle_lanes/bundle_lanes.json\nD\tdata/refactor_supervisor/discovery/2026-07-22-ref-057-objective-gap-08d9b0956fd6.md\nM\tdata/refactor_supervisor/objective_bundles/index.json\nM\tdata/refactor_supervisor/objective_bundles/refactor-g1-g1-s1.todo.md\nM\tdata/refactor_supervisor/objective_bundles/refactor-g1.todo.md\nM\tdata/refactor_supervisor/objective_bundles/refactor-g2.todo.md\nM\tdata/refactor_supervisor/objective_bundles/refactor-g3-g3-s1.todo.md\nM\tdata/refactor_supervisor/objective_bundles/refactor-g3.todo.md\nM\tdata/refactor_supervisor/objective_bundles/refactor-g6.todo.md\nM\tdata/refactor_supervisor/objective_bundles/refactor-g7-g7-s1.todo.md\nM\tdata/refactor_supervisor/objective_bundles/refactor-g7.todo.md\nM\tdata/refactor_supervisor/objective_bundles/refactor-g8.todo.md\nM\tdata/refactor_supervisor/objective_bundles/refactor-g9-g9-s2.todo.md\nM\tdata/refactor_supervisor/objective_bundles/refactor-g9-g9-s4.todo.md\nM\tdata/refactor_supervisor/refactor_goals.json\nM\tdata/refactor_supervisor/refactor_objective_heap.md\nM\tdata/refactor_supervisor/refactor_todo.md\nM\tdocs/REFACTOR_SUPERVISOR_TASKBOARD.md",
    "path_categories": {
      "deleted": 1,
      "modified": 17,
      "untracked": 2
    },
    "status_paths": [
      "data/refactor_supervisor/bundle_lanes/bundle_lanes.json",
      "data/refactor_supervisor/discovery/2026-07-22-ref-057-objective-gap-08d9b0956fd6.md",
      "data/refactor_supervisor/objective_bundles/index.json",
      "data/refactor_supervisor/objective_bundles/refactor-g1-g1-s1.todo.md",
      "data/refactor_supervisor/objective_bundles/refactor-g1.todo.md",
      "data/refactor_supervisor/objective_bundles/refactor-g2.todo.md",
      "data/refactor_supervisor/objective_bundles/refactor-g3-g3-s1.todo.md",
      "data/refactor_supervisor/objective_bundles/refactor-g3.todo.md",
      "data/refactor_supervisor/objective_bundles/refactor-g6.todo.md",
      "data/refactor_supervisor/objective_bundles/refactor-g7-g7-s1.todo.md",
      "data/refactor_supervisor/objective_bundles/refactor-g7.todo.md",
      "data/refactor_supervisor/objective_bundles/refactor-g8.todo.md",
      "data/refactor_supervisor/objective_bundles/refactor-g9-g9-s2.todo.md",
      "data/refactor_supervisor/objective_bundles/refactor-g9-g9-s4.todo.md",
      "data/refactor_supervisor/refactor_goals.json",
      "data/refactor_supervisor/refactor_objective_heap.md",
      "data/refactor_supervisor/refactor_todo.md",
      "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
      "data/refactor_supervisor/bundle_lanes/scheduler_decision_metrics.json",
      "data/refactor_supervisor/bundle_lanes/scheduler_metrics.json"
    ],
    "status_short": [
      " M data/refactor_supervisor/bundle_lanes/bundle_lanes.json",
      " D data/refactor_supervisor/discovery/2026-07-22-ref-057-objective-gap-08d9b0956fd6.md",
      " M data/refactor_supervisor/objective_bundles/index.json",
      " M data/refactor_supervisor/objective_bundles/refactor-g1-g1-s1.todo.md",
      " M data/refactor_supervisor/objective_bundles/refactor-g1.todo.md",
      " M data/refactor_supervisor/objective_bundles/refactor-g2.todo.md",
      " M data/refactor_supervisor/objective_bundles/refactor-g3-g3-s1.todo.md",
      " M data/refactor_supervisor/objective_bundles/refactor-g3.todo.md",
      " M data/refactor_supervisor/objective_bundles/refactor-g6.todo.md",
      " M data/refactor_supervisor/objective_bundles/refactor-g7-g7-s1.todo.md",
      " M data/refactor_supervisor/objective_bundles/refactor-g7.todo.md",
      " M data/refactor_supervisor/objective_bundles/refactor-g8.todo.md",
      " M data/refactor_supervisor/objective_bundles/refactor-g9-g9-s2.todo.md",
      " M data/refactor_supervisor/objective_bundles/refactor-g9-g9-s4.todo.md",
      " M data/refactor_supervisor/refactor_goals.json",
      " M data/refactor_supervisor/refactor_objective_heap.md",
      " M data/refactor_supervisor/refactor_todo.md",
      " M docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
      "?? data/refactor_supervisor/bundle_lanes/scheduler_decision_metrics.json",
      "?? data/refactor_supervisor/bundle_lanes/scheduler_metrics.json"
    ],
    "untracked_paths": [
      "data/refactor_supervisor/bundle_lanes/scheduler_decision_metrics.json",
      "data/refactor_supervisor/bundle_lanes/scheduler_metrics.json",
      "data/refactor_supervisor/discovery/2026-07-22-ref-058-objective-gap-eac2cf021fa2.md",
      "data/refactor_supervisor/discovery/2026-07-22-ref-059-objective-gap-1eba844e57d9.md",
      "data/refactor_supervisor/discovery/2026-07-22-ref-060-objective-gap-8237ed56b27c.md",
      "data/refactor_supervisor/discovery/2026-07-22-ref-061-objective-gap-6686ce3fc621.md",
      "data/refactor_supervisor/discovery/2026-07-22-ref-062-objective-gap-f307b3b05fa3.md",
      "data/refactor_supervisor/discovery/2026-07-22-ref-064-objective-gap-08d9b0956fd6.md",
      "data/refactor_supervisor/discovery/2026-07-22-ref-065-objective-gap-eac2cf021fa2.md",
      "data/refactor_supervisor/discovery/2026-07-22-ref-066-objective-gap-1eba844e57d9.md",
      "data/refactor_supervisor/discovery/2026-07-22-ref-067-objective-gap-8237ed56b27c.md",
      "data/refactor_supervisor/discovery/2026-07-22-ref-068-objective-gap-6686ce3fc621.md",
      "data/refactor_supervisor/discovery/2026-07-22-ref-069-objective-gap-f307b3b05fa3.md"
    ]
  },
  "reason": "main_checkout_dirty",
  "safety_constraints": [
    "Do not discard dirty or untracked content unless it is proven redundant with the target ref.",
    "Prefer commits, merges, or explicit follow-up tasks over destructive cleanup.",
    "Keep todo, objective, discovery, and strategy files parseable after reconciliation."
  ],
  "sample_branches": [
    "implementation/ref-011-e736afb00644-attempt-1-1784703538"
  ],
  "sample_count": 1,
  "sample_status_paths": [
    "data/refactor_supervisor/bundle_lanes/bundle_lanes.json",
    "data/refactor_supervisor/discovery/2026-07-22-ref-057-objective-gap-08d9b0956fd6.md",
    "data/refactor_supervisor/objective_bundles/index.json",
    "data/refactor_supervisor/objective_bundles/refactor-g1-g1-s1.todo.md",
    "data/refactor_supervisor/objective_bundles/refactor-g1.todo.md",
    "data/refactor_supervisor/objective_bundles/refactor-g2.todo.md",
    "data/refactor_supervisor/objective_bundles/refactor-g3-g3-s1.todo.md",
    "data/refactor_supervisor/objective_bundles/refactor-g3.todo.md",
    "data/refactor_supervisor/objective_bundles/refactor-g6.todo.md",
    "data/refactor_supervisor/objective_bundles/refactor-g7-g7-s1.todo.md",
    "data/refactor_supervisor/objective_bundles/refactor-g7.todo.md",
    "data/refactor_supervisor/objective_bundles/refactor-g8.todo.md",
    "data/refactor_supervisor/objective_bundles/refactor-g9-g9-s2.todo.md",
    "data/refactor_supervisor/objective_bundles/refactor-g9-g9-s4.todo.md",
    "data/refactor_supervisor/refactor_goals.json",
    "data/refactor_supervisor/refactor_objective_heap.md",
    "data/refactor_supervisor/refactor_todo.md",
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
    "data/refactor_supervisor/bundle_lanes/scheduler_decision_metrics.json",
    "data/refactor_supervisor/bundle_lanes/scheduler_metrics.json"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g3-g3-s2/ref-011-e736afb00644-attempt-1-1784703538"
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
