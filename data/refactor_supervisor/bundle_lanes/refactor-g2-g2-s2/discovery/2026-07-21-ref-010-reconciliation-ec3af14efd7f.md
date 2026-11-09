# REF-010 Reconciliation Guardrail

Date: 2026-07-21
Fingerprint: ec3af14efd7f38b1f92335058e4be95abcd839c8
Kind: preflight_merge_conflict
Reason: preflight_merge_conflict
Candidate count: 1
Priority: P1
Track: ops

## Main Checkout Status

- none

## Main Checkout Evidence

- none

## Sample Branches Or Worktrees

- `implementation/ref-007-attempt-1-1784663183` at `/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g2-g2-s2/ref-007-attempt-1-1784663183`
  - Conflict paths:
    - `scripts/refactor_agent_supervisor.py`

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

- `bundle_preflight_conflicts_by_path`: group blocked branches by shared conflict paths before resolving individual branches
- `resolve_markdown_and_discovery_conflicts_deterministically`: use deterministic append-only markdown/objective/todo merge repair where conflict paths are documentation or discovery files
- `resolve_code_or_submodule_conflicts_in_isolated_worktree`: stage conflicts in a temporary reconciliation worktree or invoke the configured LLM resolver before mutating main
- `rerun_worktree_reconciliation`: rerun reconcile_backlogged_worktrees and confirm preflight_blocked_count decreases

### Safety Constraints

- Do not run conflict-producing merges directly in main without a preflight or isolated resolver plan.
- Preserve submodule gitlink intent explicitly; never pick a gitlink side without recording why.
- Keep todo, objective, discovery, and strategy files parseable after reconciliation.

### Success Signals

- `preflight_blocked_count_decreases`
- `conflict_path_count_decreases`
- `reconciled_count_increases`
- `main_checkout_dirty_becomes_false`

## Machine Readable Manifest

```json
{
  "actions": [
    {
      "action": "bundle_preflight_conflicts_by_path",
      "automation": "group blocked branches by shared conflict paths before resolving individual branches",
      "scope": "backlogged_worktrees"
    },
    {
      "action": "resolve_markdown_and_discovery_conflicts_deterministically",
      "automation": "use deterministic append-only markdown/objective/todo merge repair where conflict paths are documentation or discovery files",
      "scope": "append_only_docs"
    },
    {
      "action": "resolve_code_or_submodule_conflicts_in_isolated_worktree",
      "automation": "stage conflicts in a temporary reconciliation worktree or invoke the configured LLM resolver before mutating main",
      "scope": "code_and_gitlinks"
    },
    {
      "action": "rerun_worktree_reconciliation",
      "automation": "rerun reconcile_backlogged_worktrees and confirm preflight_blocked_count decreases",
      "scope": "backlogged_worktrees"
    }
  ],
  "candidate_count": 1,
  "conflict_path_counts": {
    "scripts/refactor_agent_supervisor.py": 1
  },
  "dedupe_key": "reconciliation_guardrail:preflight_merge_conflict",
  "fingerprint": "ec3af14efd7f38b1f92335058e4be95abcd839c8",
  "kind": "preflight_merge_conflict",
  "main_dirty_evidence": {},
  "reason": "preflight_merge_conflict",
  "safety_constraints": [
    "Do not run conflict-producing merges directly in main without a preflight or isolated resolver plan.",
    "Preserve submodule gitlink intent explicitly; never pick a gitlink side without recording why.",
    "Keep todo, objective, discovery, and strategy files parseable after reconciliation."
  ],
  "sample_branches": [
    "implementation/ref-007-attempt-1-1784663183"
  ],
  "sample_count": 1,
  "sample_status_paths": [
    "scripts/refactor_agent_supervisor.py"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g2-g2-s2/ref-007-attempt-1-1784663183"
  ],
  "success_signals": [
    "preflight_blocked_count_decreases",
    "conflict_path_count_decreases",
    "reconciled_count_increases",
    "main_checkout_dirty_becomes_false"
  ],
  "top_conflict_paths": [
    "scripts/refactor_agent_supervisor.py"
  ]
}
```

## Resolution Evidence

Resolved on 2026-07-21 by merging the stale backlogged branch
`implementation/ref-007-attempt-1-1784663183` into `main` and rerunning the
scoped lane reconciliation pass.

Preflight conflict before resolution:

- Exact preflight command: `git merge-tree --write-tree main implementation/ref-007-attempt-1-1784663183`.
- Result: return code `1`, `CONFLICT (add/add)` in `scripts/refactor_agent_supervisor.py`.

Deliberate merge decision:

- Merged branch commit `c0ab3ee` via merge commit `7792c3e`.
- Kept the `main` side of `scripts/refactor_agent_supervisor.py` for the
  supervisor merge-resolver/watchdog guardrails already preserved on `main`.
- Preserved the stale branch's non-conflicting application changes in
  `applications/complaint_workspace.py` and `applications/review_api.py`.
- Preserved the branch's active-bundle todo parser hunk in follow-up commit
  `f1bb602` because it matches the generated checkbox-plus-heading todo format.

Validation:

- `python -m pytest tests/test_review_api.py -q` passed on the stale branch
  before merge: 36 passed, 1 warning.
- `python -m pytest tests/test_review_api.py -q` failed on `main` before merge:
  2 failed, 34 passed, 1 warning.
- `python -m pytest tests/test_review_api.py -q` passed on `main` after merge:
  36 passed, 1 warning.

Scoped reconciliation rerun:

```sh
PYTHONPATH=/home/barberb/complaint-generator/ipfs_datasets_py/ipfs_accelerate_py \
python -m ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor \
  --once --reconciliation-only \
  --todo-path /home/barberb/complaint-generator/data/refactor_supervisor/objective_bundles/refactor-g2-g2-s2.todo.md \
  --state-dir /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s2/state \
  --state-prefix agent_refactor_g2_g2_s2 \
  --task-prefix REF- \
  --worktree-root /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g2-g2-s2 \
  --worktree-submodule-path ipfs_datasets_py/ipfs_accelerate_py \
  --worktree-reconciliation-max-merges 1 \
  --no-worktree-scan-cache \
  --log-level INFO
```

Result:

- `main_checkout_dirty`: `false`.
- `raw_main_checkout_dirty`: `false`.
- `candidate_count`: decreased from `1` to `0`.
- `preflight_blocked_count`: decreased from `1` to `0`.
- `reconciliation_guardrail_count`: `0`.
- `worktree_cleanup.removed_count`: `1`; the stale worktree
  `ref-007-attempt-1-1784663183` and branch
  `implementation/ref-007-attempt-1-1784663183` were removed after the merge.
