# REF-316 Objective Validation Repair

Date: 2026-07-23
Goal id: G9.S4
Goal title: Close the scheduler feedback and lifecycle loop
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-316-objective-gap-06d230235392.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g9-g9-s4.todo.md
Todo vector key: 899283a75b3fc5a8
Canonical task key: task/v1/802e447d40cade8eccac219a4ec108215f88fc8a2ed4674f048e160b8f36ccdd
Canonical task CID: baguqeeraqaxei7kazlpi5tfmegne5qiiefpyr7ekf3kgotyerylaxdzwztoq
Merge key: fc6affbc4a9135ba
Merge family: goal_packet/ops/ipfs_datasets_py/c20825ca2cad

## Repair Summary

The objective scan filed REF-316 because G9.S4 named its implementation
surfaces, acceptance statements, and focused commands but did not contain a
durable `objective validation repair` receipt. The missing evidence is an
objective-lifecycle bookkeeping gap, not a scheduler implementation gap: both
required commands pass, and each G9.S4 boundary has direct executable coverage.

The existing G9.S4 decomposition remains complete and appropriately bounded:

- REF-044 owns the event-derived scheduler snapshot, lifecycle and throughput
  metrics, canonical metric identity, operator projection, and the scheduler's
  decision-snapshot linkage.
- REF-045 owns content-addressed AST/evidence reuse, deterministic invalidation,
  measured warm-path savings, and exclusive reuse of clean prepared worktrees
  and dependency setups.

A third child goal would duplicate those two independently executable slices.
The objective heap therefore retains G9.S4 as one active subgoal and now links
this validation-gate receipt. This repair does not infer completion from passing
tests or manually change supervisor-owned task status.

## G9.S4 Evidence Contract

| Boundary | Authoritative implementation | Executable evidence |
| --- | --- | --- |
| Event-derived phase state | `scheduler_metrics.py`, `event_log.py` | One immutable snapshot reduces current and rotated event logs into zero-filled ready, active, idle, blocked, validation, merge, and resolver projections. Timestamped events deterministically supersede undated legacy lane state. |
| Lifecycle throughput | `scheduler_metrics.py` | Per-identity rows derive queue wait, implementation and validation durations, merge wait, attempts, retries, conflicts, completions, tokens, and cost. Rates are zero-safe and completion events are deduplicated. |
| Canonical dimensions | `scheduler_metrics.py` | Every metric row normalizes goal, subgoal, canonical task, lane, and effective provider identity, including rollout-era field aliases. |
| Closed scheduler feedback | `bundle_supervisor.py`, `supervisor_watchdog.py` | Admission decisions reference the exact event snapshot identifier written for operators. Watchdog recovery returns the same projection and defers recovery when a live dynamic scheduler owns the lane. |
| Durable scan evidence | `dataset_store.py`, `objective_graph.py` | Full scan diagnostics are content-addressed and recoverable; AST and evidence records are keyed by source blob, so a warm scan reuses unchanged records and reparses only changed content. |
| Deterministic invalidation | `objective_graph.py` | A rename rebinds reusable blob evidence to the current path, deletion removes stale path evidence, and cold and warm scans produce equivalent plans. |
| Isolated workspace reuse | `todo_daemon/worktrees.py`, `todo_daemon/implementation_daemon.py` | Clean prepared worktrees and populated dependency setups are exclusively leased by setup key and target commit. Successful and failed task paths release their lease; dirty task state is discarded instead of entering the pool. |
| Measured savings | `objective_graph.py`, `todo_daemon/worktrees.py` | Scan statistics expose parsed and reused record counts plus saved parse time, while pool metadata exposes hit, miss, release, and invalidation outcomes without changing validation semantics. |

The scheduler lifecycle is closed through one observable state lineage:

```text
durable daemon events
  -> canonical event-derived snapshot
  -> scheduler admission and deferral decisions
  -> manifest plus operator metrics using the same snapshot id
  -> watchdog observation and bounded recovery
  -> new lifecycle events and the next snapshot
```

Incremental execution preserves the same proof boundary:

```text
target commit + source blobs + dependency setup
  -> reuse unchanged evidence and one exclusively leased clean workspace
  -> parse or prepare only invalidated inputs
  -> unchanged plan and validation semantics
  -> scrub and pool clean state, discard dirty state
```

No scheduler decision can silently diverge from the operator projection, and no
task-local mutation can become a shared warm-path input.

## Shared Goal Packet Coverage

REF-316 is a validation-gate member of
`goal_packet/ops/ipfs_datasets_py/c20825ca2cad`. The complete G9.S1 through
G9.S4 packet was exercised together, proving that the feedback and incremental
runtime paths remain compatible with every upstream scheduler decision:

| Goal | Shared evidence confirmed |
| --- | --- |
| G9.S1 | Canonical leases fence duplicate execution; the persistent scheduler discovers and releases work without restart; implementation lanes enqueue through the serialized merge train; bounded failures produce durable quarantine receipts. |
| G9.S2 | Successful dependency receipts govern claimability, conflict coloring separates overlapping work, actual conflict evidence updates future weights, and deterministic branch evaluation retains rejected alternatives and rationale. |
| G9.S3 | Live host/provider telemetry controls adaptive admission; cheap-first and bounded validation uses target-, environment-, and dependency-aware cache identities and escalates conservatively before merge. |
| G9.S4 | The event snapshot consumed by scheduler decisions is the snapshot exposed to operators; blob-addressed evidence reuse and exclusively leased clean worktrees preserve cold/warm equivalence without task-state leakage. |

This packet-wide result records shared compatibility, not completion of
REF-313, REF-314, or REF-315. Their goal-specific validation receipts remain
separate supervisor work items.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-316-objective-validation-repair.md`
- Canonical backlog evidence: REF-316 in
  `data/refactor_supervisor/refactor_todo.md`
- Existing implementation ownership: REF-044 and REF-045
- Shared packet validation gates: REF-313, REF-314, REF-315, and REF-316
- G9.S4 bundle evidence:
  `data/refactor_supervisor/objective_bundles/refactor-g9-g9-s4.todo.md`

The heap now points to this receipt and the exact missing evidence term. The
canonical todo already points to the same goal, bundle, commands, merge family,
and two existing implementation slices. Generated bundle/index regeneration
and task completion remain supervisor-owned, so this repair does not manually
edit REF-316 status or generated todo-vector data.

## Validation

- PASS — required scheduler metrics lane: 15 tests.
- PASS — required incremental runtime lane: 9 tests.
- PASS — combined G9.S1, G9.S2, G9.S3, and G9.S4 packet lane: 194 tests.

All commands exited successfully on 2026-07-23. The only diagnostic was the
existing `pytest-asyncio` deprecation warning for the unset
`asyncio_default_fixture_loop_scope` option.
