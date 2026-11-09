# REF-034 Reconciliation Guardrail

Date: 2026-07-21
Fingerprint: 21ac8f2f53fc2c0e8eb66551ba6b77d864efa7d9
Kind: preflight_merge_conflict
Reason: preflight_merge_conflict
Candidate count: 2
Priority: P1
Track: ops

## Main Checkout Status

- none

## Main Checkout Evidence

- none

## Sample Branches Or Worktrees

- `implementation/ref-001-attempt-1-1784661950` at `/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-001-attempt-1-1784661950`
  - Conflict paths:
    - `applications/complaint_workspace.py`
    - `docs/ARCHITECTURE.md`
    - `docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
    - `mediator/mediator.py`
    - `scripts/refactor_agent_supervisor.py`
    - `tests/test_package_imports.py`
- `implementation/ref-028-attempt-1-1784669974` at `/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-028-attempt-1-1784669974`
  - Conflict paths:
    - `applications/complaint_workspace.py`
    - `data/refactor_supervisor/discovery/2026-07-21-ref-028-objective-validation-repair.md`
    - `data/refactor_supervisor/objective_graph.json`
    - `data/refactor_supervisor/refactor_objective_heap.md`
    - `tests/test_package_imports.py`

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

Work surface: `2` candidates, `2` sampled records.

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
  "candidate_count": 2,
  "conflict_path_counts": {
    "applications/complaint_workspace.py": 2,
    "data/refactor_supervisor/discovery/2026-07-21-ref-028-objective-validation-repair.md": 1,
    "data/refactor_supervisor/objective_graph.json": 1,
    "data/refactor_supervisor/refactor_objective_heap.md": 1,
    "docs/ARCHITECTURE.md": 1,
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md": 1,
    "mediator/mediator.py": 1,
    "scripts/refactor_agent_supervisor.py": 1,
    "tests/test_package_imports.py": 2
  },
  "dedupe_key": "reconciliation_guardrail:preflight_merge_conflict",
  "fingerprint": "21ac8f2f53fc2c0e8eb66551ba6b77d864efa7d9",
  "kind": "preflight_merge_conflict",
  "main_dirty_evidence": {},
  "reason": "preflight_merge_conflict",
  "safety_constraints": [
    "Do not run conflict-producing merges directly in main without a preflight or isolated resolver plan.",
    "Preserve submodule gitlink intent explicitly; never pick a gitlink side without recording why.",
    "Keep todo, objective, discovery, and strategy files parseable after reconciliation."
  ],
  "sample_branches": [
    "implementation/ref-001-attempt-1-1784661950",
    "implementation/ref-028-attempt-1-1784669974"
  ],
  "sample_count": 2,
  "sample_status_paths": [
    "applications/complaint_workspace.py",
    "docs/ARCHITECTURE.md",
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
    "mediator/mediator.py",
    "scripts/refactor_agent_supervisor.py",
    "tests/test_package_imports.py",
    "data/refactor_supervisor/discovery/2026-07-21-ref-028-objective-validation-repair.md",
    "data/refactor_supervisor/objective_graph.json",
    "data/refactor_supervisor/refactor_objective_heap.md"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-001-attempt-1-1784661950",
    "/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-028-attempt-1-1784669974"
  ],
  "success_signals": [
    "preflight_blocked_count_decreases",
    "conflict_path_count_decreases",
    "reconciled_count_increases",
    "main_checkout_dirty_becomes_false"
  ],
  "top_conflict_paths": [
    "applications/complaint_workspace.py",
    "tests/test_package_imports.py",
    "data/refactor_supervisor/discovery/2026-07-21-ref-028-objective-validation-repair.md",
    "data/refactor_supervisor/objective_graph.json",
    "data/refactor_supervisor/refactor_objective_heap.md",
    "docs/ARCHITECTURE.md",
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
    "mediator/mediator.py",
    "scripts/refactor_agent_supervisor.py"
  ]
}
```

## Resolution

Resolved on 2026-07-21. The configured `llm_router` resolver path was exercised
for both preflight conflicts. `REF-001` contained unique ownership-map work and
was reconciled into `main` by `f4fc518`; the stale `REF-028` tree was already
superseded and was retired by `fa6b295` without changing the current tree. Both
source worktrees and branches were removed after ancestry verification.
