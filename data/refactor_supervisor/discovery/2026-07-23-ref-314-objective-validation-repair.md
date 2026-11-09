# REF-314 Objective Validation Repair

Date: 2026-07-23
Goal id: G9.S2
Goal title: Plan from dependencies, conflicts, and objective value
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-314-objective-gap-de16e332ec42.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g9-g9-s2.todo.md
Todo vector key: 444dacc3555e282d
Canonical task key: task/v1/cb36817ed3f6145d7a9acca89961329062918a577085d1c636ca5e3e2489c994
Canonical task CID: baguqeerazm3ic7wt6ykf26u2zsujsyjssbrjdcsxocc5drrwzjpd4jejzgka
Merge key: cf42c01cca68f418
Merge family: goal_packet/ops/ipfs_datasets_py/c20825ca2cad

## Repair Summary

The objective scan filed REF-314 because G9.S2 named its implementation paths,
acceptance statements, and focused commands but did not contain a durable
`objective validation repair` receipt. The gap is in the objective evidence
contract rather than in the planner implementations: all three required
commands pass, and every G9.S2 acceptance boundary has direct executable
coverage.

The existing G9.S2 decomposition remains complete and appropriately bounded:

- REF-039 owns typed dependency discovery, merge-receipt readiness, critical
  path scheduling, and bounded malformed-graph repairs.
- REF-040 owns complete predicted and observed conflict surfaces, conflict
  coloring, historical weight learning, and auditable lane decisions.
- REF-041 owns strict multi-branch proposal schemas, deterministic evaluation,
  rejected-alternative receipts, and failure-isolated deterministic fallback.

A fourth child goal would duplicate these three independently executable
slices. The objective heap therefore retains G9.S2 as one active subgoal and
now links this validation-gate receipt. This repair does not infer completion
from passing tests or manually change supervisor-owned task status.

## G9.S2 Evidence Contract

| Boundary | Authoritative implementation | Executable evidence |
| --- | --- | --- |
| Explicit prerequisite DAG | `objective_graph.py` | Goal, import, interface, output-input, migration, validation, and direct task prerequisites become typed producer-to-consumer edges. Every edge retains its source field, value, resolution mode, and task aliases as provenance. |
| Merge-proven readiness | `objective_graph.py`, `lease_coordination.py`, `bundle_supervisor.py` | Mutable todo status cannot satisfy a prerequisite. A successful canonical merge receipt unblocks the dependent task; bundle projections map member dependencies to the bundle execution CIDs that actually receive fenced leases and receipts. |
| Objective-value scheduling | `objective_graph.py`, `bundle_supervisor.py` | Stable schedule records expose critical-path length, slack, transitive downstream unlock value, age, configured objective priority, blockers, score, and deterministic sort key. Capacity is applied only after dependency-ready tasks are ordered. |
| Bounded graph repair | `objective_graph.py` | Missing prerequisites and cyclic strongly connected components emit finite structured repair evidence and become unclaimable. Independent acyclic work remains ready, and long generated chains are handled without recursive traversal. |
| Complete conflict surfaces | `conflict_graph.py`, `todo_vector_index.py` | Predicted files and outputs, file-scoped and global AST symbols, interfaces, submodules, generated artifacts, and actual changed paths are normalized into one typed surface per canonical task. Duplicate aliases coalesce conservatively. |
| Conflict-safe lane coloring | `conflict_graph.py`, `bundle_supervisor.py` | Blocking overlap receives a deterministic graph color; overlapping tasks occupy different lanes unless an explicit concurrency override is retained in the audit record. Completed members do not create stale conflicts. |
| Learned conflict weights | `conflict_graph.py` | Actual branch diffs and durable conflict receipts increase path, task-pair, and observed weights. Serialized conflict history carries the learned signal into later planning runs. |
| Explainable placement | `conflict_graph.py` | Every task pair receives a stable co-location, separation, or explicit-override decision with the relevant overlap and learned-history rationale, including disjoint pairs with no conflict edge. |
| Strict branch proposals | `task_proposal_router.py`, `plan_evaluator.py` | Each eligible subgoal can request multiple branches. Every candidate must declare repository-relative predicted files, AST symbols, dependencies, validation commands and proof, bounded risk and objective delta, and finite cost. Unknown or malformed router fields fail schema validation. |
| Deterministic selection | `plan_evaluator.py`, `objective_daemon.py` | Integer-millionth scoring and a stable branch-id tie break select the same branch regardless of candidate order. The selected rationale and all rejected alternatives, scores, and rationales persist in scheduler-visible Profile G data. |
| Non-blocking router fallback | `task_proposal_router.py`, `objective_daemon.py` | Router exceptions, malformed JSON, and empty responses invoke deterministic planning for only the affected subgoal. The error and fallback source are retained while later ready work continues through routed evaluation. |

Dependency readiness and conflict safety are deliberately separate gates:

```text
objective task records
  -> typed dependency DAG and successful-merge closure
  -> objective-value ordering of ready work
  -> complete predicted plus learned conflict graph
  -> conflict-colored execution lanes
  -> schema-validated alternative branches
  -> deterministic selection with rejected-branch receipts
```

No task can become claimable through display status alone, no conflict history
is discarded after one planning cycle, and no LLM-produced branch can bypass
the deterministic schema and evaluator boundary.

## Shared Goal Packet Coverage

REF-314 is a validation-gate member of
`goal_packet/ops/ipfs_datasets_py/c20825ca2cad`. The complete G9.S1 through
G9.S4 packet was exercised together so planning behavior is confirmed against
the coordination, capacity, validation, and lifecycle surfaces that consume
its decisions:

| Goal | Shared evidence confirmed |
| --- | --- |
| G9.S1 | Canonical leases fence duplicate execution; the persistent scheduler discovers and releases work without restart; implementation lanes enqueue through the serialized merge train; bounded failures produce durable quarantine receipts. |
| G9.S2 | Merge receipts govern dependency readiness, objective value orders ready work, complete conflict surfaces color lanes and learn from receipts, and deterministic branch evaluation retains every alternative and rationale. |
| G9.S3 | Live host/provider telemetry controls admission after planning; cheap-first, bounded, cached, impact-selected validation escalates before a selected branch can merge. |
| G9.S4 | Event-derived snapshots expose the same scheduler decisions to operators; incremental AST/evidence reuse and pooled clean worktrees preserve equivalent warm and cold plans without leaking task mutations. |

This packet-wide result records shared compatibility, not completion of
REF-313, REF-315, or REF-316. Their goal-specific validation receipts remain
separate supervisor work items.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-314-objective-validation-repair.md`
- Canonical backlog evidence: REF-314 in
  `data/refactor_supervisor/refactor_todo.md`
- Existing implementation ownership: REF-039, REF-040, and REF-041
- Shared packet validation gates: REF-313, REF-314, REF-315, and REF-316
- G9.S2 bundle evidence:
  `data/refactor_supervisor/objective_bundles/refactor-g9-g9-s2.todo.md`

The heap now points to this receipt and the exact missing evidence term. The
canonical todo already points to the same goal, bundle, commands, merge family,
and three existing implementation slices. Generated bundle/index regeneration
and task completion remain supervisor-owned, so this repair does not manually
edit REF-314 status or generated todo-vector data.

## Validation

- PASS — required dependency planner and objective graph lane: 41 tests.
- PASS — required conflict graph and objective graph lane: 40 tests.
- PASS — required structured plan evaluator lane: 30 tests.
- PASS — combined G9.S1, G9.S2, G9.S3, and G9.S4 packet lane: 195 tests.

All commands exited successfully on 2026-07-23. The only diagnostic was the
existing `pytest-asyncio` deprecation warning for the unset
`asyncio_default_fixture_loop_scope` option.
