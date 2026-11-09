# REF-315 Objective Validation Repair

Date: 2026-07-23
Goal id: G9.S3
Goal title: Adapt execution capacity and validation cost
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-315-objective-gap-8a879779a3eb.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g9-g9-s3.todo.md
Todo vector key: 91e5b542aeb9ace2
Canonical task key: task/v1/088f5e64c6ad42a38ecee5ab7f2dbf14fcb016a0013e67a520c52941b86e1b5f
Canonical task CID: baguqeerabchv4zggvvbkhdwo4wvx6ln7ct6lafvaae7gpjjayuuudododnpq
Merge key: 953a24fb86d6de67
Merge family: goal_packet/ops/ipfs_datasets_py/c20825ca2cad

## Repair Summary

The objective scan filed REF-315 because G9.S3 named its implementation paths,
acceptance statements, and focused commands but did not contain a durable
`objective validation repair` receipt. The gap is in the objective evidence
contract rather than in the scheduler implementations: both required commands
pass, and every G9.S3 acceptance boundary has direct executable coverage.

The existing G9.S3 decomposition remains appropriately bounded:

- REF-042 owns live host and provider capacity, admission, backpressure,
  reservation, heartbeat, and idle-lane behavior.
- REF-043 owns validation classification, stage barriers, weighted parallelism,
  impact selection, pre-merge escalation, and content-addressed result reuse.

A third child goal would duplicate these two independently executable slices.
The objective heap therefore retains G9.S3 as one active subgoal and now links
this receipt as its validation-gate evidence. This repair does not infer
completion from passing tests or manually change supervisor-owned task status.

## G9.S3 Evidence Contract

| Boundary | Authoritative implementation | Executable evidence |
| --- | --- | --- |
| Measured worker capacity | `resource_scheduler.py`, `lease_coordination.py`, `leased_lane.py` | Host samples and heartbeats report CPU, memory, disk, active phase, worker limit, active workers, and available capacity. Idle lanes publish zero occupied capacity and return their slot for reassignment. |
| Host backpressure | `resource_scheduler.py`, `bundle_supervisor.py` | Admission checks CPU, memory, disk, byte headroom, resource class, and worker slots before lease claim or process launch. Scheduling reserves accepted host capacity in deterministic input-priority order. |
| Provider backpressure | `resource_scheduler.py`, `bundle_supervisor.py` | Normalized provider telemetry applies health, backoff, quota, latency, context, token, concurrency, and capability gates. Explicit zero remains exhausted, missing telemetry fails closed for LLM lanes, and non-LLM work remains schedulable. |
| Adaptive concurrency | `resource_scheduler.py`, `bundle_supervisor.py` | Dynamic scheduling starts only admitted lanes, accumulates host/provider reservations, selects providers deterministically, and never exceeds configured host or provider capacity. |
| Cheap-first validation | `validation_commands.py`, `validation_scheduler.py` | Deterministic checks complete before expensive stages; a cheap failure prevents later work from starting. |
| Bounded parallel validation | `validation_scheduler.py` | Independent commands overlap through a weighted budget whose in-flight cost cannot exceed configured capacity. Stage barriers retain deterministic ordering. |
| Safe result reuse | `validation_scheduler.py` | Cache identity binds target commit, normalized command, non-secret relevant environment, dependency manifests/gitlinks, and dirty candidate content. Only successful, non-timeout results are stored durably. |
| Conservative impact selection | `validation_commands.py`, `validation_scheduler.py`, `todo_daemon/implementation_daemon.py` | Selection records matched paths and inclusion rationale, dependency changes conservatively select checks, and pre-merge scope escalates omitted targeted checks before completion. |

The implementation remains fail-closed at the two exhaustion boundaries:

```text
ready lane
  -> host + provider admission
  -> fenced lease and reserved capacity
  -> implementation
  -> cheap validation barrier
  -> bounded targeted validations
  -> broad pre-merge escalation
  -> merge candidate
```

No lane is leased when its required capacity is unavailable, and no candidate
can treat impact-selected validation as its final merge proof without the
configured broader pre-merge checks.

## Shared Goal Packet Coverage

REF-315 is a validation-gate member of
`goal_packet/ops/ipfs_datasets_py/c20825ca2cad`. The complete G9.S1 through
G9.S4 packet was exercised together so capacity and validation behavior is
confirmed against the coordination, planning, and feedback surfaces that
consume it:

| Goal | Shared evidence confirmed |
| --- | --- |
| G9.S1 | Canonical leases fence duplicate execution; the persistent scheduler discovers and releases work without restart; implementation lanes enqueue through the serialized merge train; bounded failures produce durable quarantine receipts. |
| G9.S2 | Dependency receipts govern claimability, conflict coloring separates overlapping work, actual conflict evidence updates weights, and deterministic branch evaluation retains rejected alternatives and rationale. |
| G9.S3 | Live host/provider telemetry controls adaptive lane admission, while cheap-first, bounded, cached, impact-selected validation escalates before merge. |
| G9.S4 | Event-derived snapshots expose the phases and identities consumed by scheduler decisions; incremental AST/evidence reuse and pooled clean worktrees preserve cold/warm equivalence without leaking task mutations. |

This packet-wide result records shared compatibility, not completion of
REF-313, REF-314, or REF-316. Their goal-specific validation receipts remain
separate supervisor work items.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-315-objective-validation-repair.md`
- Canonical backlog evidence: REF-315 in
  `data/refactor_supervisor/refactor_todo.md`
- Existing implementation ownership: REF-042 and REF-043
- Shared packet validation gates: REF-313, REF-314, REF-315, and REF-316
- G9.S3 bundle evidence:
  `data/refactor_supervisor/objective_bundles/refactor-g9-g9-s3.todo.md`

The heap now points to this receipt and the exact missing evidence term. The
canonical todo already points to the same goal, bundle, commands, merge family,
and two existing implementation slices. Generated bundle/index regeneration
and task completion remain supervisor-owned, so this repair does not manually
edit REF-315 status or generated todo-vector data.

## Validation

- PASS — required resource scheduler lane: 28 tests.
- PASS — required validation scheduler lane: 9 tests.
- PASS — combined G9.S1, G9.S2, G9.S3, and G9.S4 packet lane: 194 tests.

All commands exited successfully on 2026-07-23. The only diagnostic was the
existing `pytest-asyncio` deprecation warning for the unset
`asyncio_default_fixture_loop_scope` option.
