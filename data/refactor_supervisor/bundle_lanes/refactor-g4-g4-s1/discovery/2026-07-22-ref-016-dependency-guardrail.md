# Dependency Guardrail: REF-015

Created: 2026-07-22T04:29:35.421287+00:00
Fingerprint: 956e7e88cb97153337d06c8872b5706bf00dab88
Source task: REF-015 Duplicate task id
Missing dependencies: none
Self-referential dependencies: none
Dependency cycle: none
Duplicate task id: REF-015
Duplicate source lines: 49, 63

## Duplicate Task Titles

- Resolve dirty main checkout blocking 1 worktree merges
- Resolve dirty main checkout blocking 2 worktree merges

## Why This Blocks Progress

The implementation daemon only selects tasks whose dependencies are completed.
When an open task depends on a task id that is not present on the board, or on
itself, or participates in a dependency cycle, the task can remain waiting
indefinitely while the supervisor reports no ready work. Duplicate task ids are
also ambiguous because status maps, dependency resolution, and guardrail
releases all key by task id.

## Suggested Repair

Inspect the source task metadata and either add the missing prerequisite task,
remove the stale dependency, break the dependency cycle, rename duplicate task
ids so each task is unique, or replace stale references with the correct existing
task id. Keep the todo board parseable after the repair.

## Resolution Evidence

Resolved: 2026-07-22

The two REF-015 blocks are separate completed reconciliation snapshots, not two
descriptions of one task. To retain that operational history while restoring an
unambiguous task graph, the later block from original source line 63 was renamed
to the next unused board-local id, REF-017. Its fingerprint, dedupe key,
validation artifact, status, and acceptance metadata remain unchanged. The
first block remains REF-015, so references to the original reconciliation task
continue to resolve to the task that produced the evidence artifact.

The repaired board was parsed with the supervisor's production
`parse_task_file` function and evaluated with `dependency_guardrail_records`.
The result contains five distinct task ids and no dependency guardrail records:

```json
{
  "dependency_guardrail_records": [],
  "duplicate_task_ids": [],
  "missing_dependencies": [],
  "self_referential_dependencies": [],
  "dependency_cycles": [],
  "task_ids": ["REF-013", "REF-014", "REF-015", "REF-017", "REF-016"]
}
```

REF-015's real dependency list is empty. It is already completed, but applying
the daemon's readiness rule to it as an open task leaves no unresolved
dependencies, so it resolves to `ready` immediately. No prerequisite task was
missing and none needed to be invented.

The production `release_completed_guardrail_blocks` routine was also exercised
without writing state, using the repaired board and a copy of the live lane
strategy. It removed REF-015 from `blocked_tasks` and returned:

```json
{
  "follow_up_task_id": "REF-016",
  "guardrail_kind": "dependency_guardrail",
  "reason": "dependency_metadata_resolved",
  "source_task_id": "REF-015"
}
```

This confirms the next supervisor maintenance pass can clear the strategy-level
guardrail as well as seeing REF-015's dependency set as satisfied.
