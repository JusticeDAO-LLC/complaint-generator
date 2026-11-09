# REF-026 Reconciliation Guardrail

Date: 2026-07-22
Fingerprint: fc7e21256d1f56af80ccaa2a28a6acefd2614035
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

- `implementation/ref-023-afeb99061864-attempt-1-1784692590` at `/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g8-g8-s1/ref-023-afeb99061864-attempt-1-1784692590`
  - Conflict paths:
    - `data/refactor_supervisor/objective_bundles/index.json`
    - `data/refactor_supervisor/refactor_goals.json`
    - `docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
    - `scripts/refactor_agent_supervisor.py`
    - `tests/test_refactor_agent_supervisor.py`

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
    "data/refactor_supervisor/objective_bundles/index.json": 1,
    "data/refactor_supervisor/refactor_goals.json": 1,
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md": 1,
    "scripts/refactor_agent_supervisor.py": 1,
    "tests/test_refactor_agent_supervisor.py": 1
  },
  "dedupe_key": "reconciliation_guardrail:preflight_merge_conflict",
  "fingerprint": "fc7e21256d1f56af80ccaa2a28a6acefd2614035",
  "kind": "preflight_merge_conflict",
  "main_dirty_evidence": {},
  "reason": "preflight_merge_conflict",
  "safety_constraints": [
    "Do not run conflict-producing merges directly in main without a preflight or isolated resolver plan.",
    "Preserve submodule gitlink intent explicitly; never pick a gitlink side without recording why.",
    "Keep todo, objective, discovery, and strategy files parseable after reconciliation."
  ],
  "sample_branches": [
    "implementation/ref-023-afeb99061864-attempt-1-1784692590"
  ],
  "sample_count": 1,
  "sample_status_paths": [
    "data/refactor_supervisor/objective_bundles/index.json",
    "data/refactor_supervisor/refactor_goals.json",
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
    "scripts/refactor_agent_supervisor.py",
    "tests/test_refactor_agent_supervisor.py"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g8-g8-s1/ref-023-afeb99061864-attempt-1-1784692590"
  ],
  "success_signals": [
    "preflight_blocked_count_decreases",
    "conflict_path_count_decreases",
    "reconciled_count_increases",
    "main_checkout_dirty_becomes_false"
  ],
  "top_conflict_paths": [
    "data/refactor_supervisor/objective_bundles/index.json",
    "data/refactor_supervisor/refactor_goals.json",
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
    "scripts/refactor_agent_supervisor.py",
    "tests/test_refactor_agent_supervisor.py"
  ]
}
```
