# REF-310 Objective Validation Repair

Date: 2026-07-23
Goal id: G11.S4
Goal title: Schedule proof work under shared CPU budgets
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-310-objective-gap-75c94fb3a999.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Declared bundle shard: data/refactor_supervisor/objective_bundles/refactor-g11-g11-s4.todo.md
Todo vector key: b9d5cca1397897d0
Canonical task key: task/v1/83193a04ea383fbc23538b86262256805be8df6865007b261a89a5d10a94d7eb
Canonical task CID: baguqeeraqmmtubhkha73yi2trodcmiswqbn6rx3imuahwjq2rgs5ccuu27vq
Merge key: 01f2f83ebb57b160
Merge family: goal_packet/ops/ipfs_datasets_py/1334a2482ee2

## Repair Summary

The objective scan filed REF-310 because G11.S4 did not contain the synthetic
`objective validation repair` evidence term. It found every named production
and test path, but broad lexical matches for individual terms such as `CPU`,
`solver`, `kernel`, `validation`, and `latency` were not a durable proof of the
compound scheduling assertions.

The checked-in implementation and its focused tests already provide the
complete G11.S4 boundary:

1. The proof scheduler executes a durable proof-plan DAG in dependency order,
   ranks ready work by critical path and downstream unlock value, and overlaps
   independent stages only within global, stage, and resource-class limits.
   Conclusive portfolio results cancel redundant work; failed or unsupported
   dependencies propagate explicitly; restart recovery uses fenced leases and
   does not mint duplicate authoritative receipts.
2. One supervisor resource scheduler admits translation, solver, kernel,
   validation, model-draft, and artifact work. Its aggregate lease budget
   remains authoritative over CPU, process, memory, disk, provider quota,
   context, token, and latency limits and is narrowed into child portfolio and
   kernel limits. Model concurrency is separate from CPU proof concurrency,
   and released capacity is immediately reclaimable.
3. Staged validation orders cheap deterministic checks before translation,
   solver, kernel, focused tests, broad tests, and attestation. Independent
   checks share the same resource scheduler; fail-fast behavior prevents
   unnecessary downstream work; impact selection records included, omitted,
   escalated, and fallback decisions without collapsing distinct verdicts.
4. Public JSON and DuckDB projections expose bounded obligations, attempts,
   receipts, dependencies, cache outcomes, resource samples, assurance counts,
   and stage latencies under canonical dimensions. Persistence rejects private
   witness or transcript extensions and keeps attempts and plans distinct.

REF-257 through REF-260 already split this goal into those four independently
owned and validated implementation slices. Additional child goals would
duplicate finished scopes, so this repair records the missing objective
evidence instead of adding synthetic implementation work.

## G11.S4 Evidence Contract

| Scheduling boundary | Authoritative implementation | Executable evidence |
| --- | --- | --- |
| Durable proof DAG | `proof_scheduler.py`, `formal_verification_contracts.py` | Seven tests prove critical-path priority, bounded overlap, stage/resource limits, conclusive cancellation, explicit dependency propagation, restart recovery, and lease fencing. |
| Shared admission | `resource_scheduler.py`, `proof_scheduler.py` | Thirteen tests prove all resource classes, one aggregate CPU/process/memory/disk/provider budget, authoritative live backpressure, child limit propagation, independent model accounting, reclaimable capacity, and admission-before-claim. |
| Staged validation | `validation_commands.py`, `validation_scheduler.py`, `proof_scheduler.py` | Seven tests prove deterministic-first ordering, shared-budget concurrency, complete impact explanations, separate verdicts, fail-fast behavior, and rollout-correct fallbacks. |
| Bounded observability | `proof_metrics.py`, `artifact_store.py`, `scheduler_metrics.py` | Seven tests prove complete records and dimensions, equivalent JSON/DuckDB projections, bounded queries, private-data exclusion on every persistence path, fail-closed receipts, and plan-scoped identity. |

The four required validation lanes contain 34 tests. Together they exercise
the complete scheduling and admission flow:

```text
impact-selected checks
  -> dependency- and priority-ordered proof DAG
  -> one supervisor resource admission envelope
  -> narrowed portfolio and kernel child limits
  -> separate deterministic/solver/kernel/test/attestation verdicts
  -> bounded public metrics and durable receipts
```

No nested pool may independently expand the supervisor lease. A step is not
claimed until resource and provider admission succeeds, a conclusive result
stops redundant attempts, released leases return capacity, and recovery keeps
the persisted plan, attempt, lease, and receipt identities authoritative.

## Shared Goal Packet Coverage

REF-310 is a validation-gate member of
`goal_packet/ops/ipfs_datasets_py/1334a2482ee2`. A fresh 55-test G11.S1 run and
a combined 157-test G11.S2/S3/S4/S7 run verify the packet as one bounded,
trust-preserving pipeline:

| Goal | Shared evidence advanced by this repair |
| --- | --- |
| G11.S1 | Versioned capability, contract, provider, and policy records define the trust and resource inputs consumed by scheduling. Availability and provider claims cannot become proof success. |
| G11.S2 | Exact AST scopes and template identities create obligations; blob-keyed reuse, delete/rename invalidation, and trust-partitioned bounded capsules provide deterministic scheduling inputs. |
| G11.S3 | Hammer portfolios, independently checked kernel candidates, complete cache identities, fenced cross-process single-flight, and explicit fallbacks execute beneath the shared resource envelope. |
| G11.S4 | Durable DAG scheduling, authoritative aggregate admission, deterministic-first staged validation, cancellation, recovery, and bounded metrics implement the packet's execution boundary. |
| G11.S7 | Completion and merge gates consume exact proof and validation receipts; retries preserve policy and tree identity, and invalidation reopens only affected goals. |

This covers the compact execution packet's shared evidence terms: exact
obligation and cache identity; CPU and child resource limits; changed-scope
proof selection; deterministic checks before translation; bounded trusted
context; cross-thread and cross-process single-flight; conclusive portfolio
cancellation; explicit blocked and unsupported propagation; receipt-backed
completion; and deterministic affected-goal reopening.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-310-objective-validation-repair.md`
- Canonical backlog evidence: REF-310 in
  `data/refactor_supervisor/refactor_todo.md`
- Existing G11.S4 implementation ownership: REF-257, REF-258, REF-259, and
  REF-260 in the canonical backlog
- Shared packet validation gates: REF-307, REF-308, REF-309, REF-310, and
  REF-311
- Supervisor-declared G11.S4 bundle target:
  `data/refactor_supervisor/objective_bundles/refactor-g11-g11-s4.todo.md`

The heap now points to this receipt and the exact missing evidence term. The
supervisor-fed todo already identifies the same G11.S4 goal, declared bundle
target, four validation commands, merge family, and implementation slices.
Generated bundle regeneration and task completion remain supervisor-owned;
this repair does not manually change REF-310 status or generated indexes.

## Validation

- PASS — durable proof scheduler lane: 7 tests.
- PASS — shared proof resource scheduler lane: 13 tests.
- PASS — staged proof validation scheduler lane: 7 tests.
- PASS — bounded proof metrics lane: 7 tests.
- PASS — G11.S1 fresh-process packet lane: 55 tests.
- PASS — combined G11.S2, G11.S3, G11.S4, and G11.S7 packet lane: 157 tests.
- PASS — objective evidence rescan: all 83 G11.S4 terms resolve; none remain
  missing.

All required commands and packet validation commands exited successfully. The
runs emitted only the existing `pytest-asyncio` unset-loop-scope deprecation
and four Python multiprocessing warnings about `fork()` in the cross-process
single-flight test. The objective rescan emitted the expected optional
`ipfs_kit_py` degraded-mode warning.
