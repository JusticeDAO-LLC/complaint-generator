# REF-311 Objective Validation Repair

Date: 2026-07-23
Goal id: G11.S7
Goal title: Enforce proof-aware merge and goal completion
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-311-objective-gap-e61b1296fab6.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Declared bundle shard: data/refactor_supervisor/objective_bundles/refactor-g11-g11-s7.todo.md
Todo vector key: 218c3daa27036776
Canonical task key: task/v1/2cdacfdfa355e91f8fbccfca757194be0ee0737939b6512ca150820893cd21f3
Canonical task CID: baguqeeraftnm7x5dkxur7d54z7fhk4muxyhoa43zhg3fclfbkcbare6nehzq
Merge key: 3b99c93fe22575fc
Merge family: goal_packet/ops/ipfs_datasets_py/1334a2482ee2

## Repair Summary

The objective scan filed REF-311 because G11.S7 did not contain the synthetic
`objective validation repair` evidence term. It found the named production and
test paths, but broad lexical matches for individual terms such as `proof
receipt`, `assurance`, `tree`, `stale`, and `policy` were not a durable proof of
the compound completion and promotion assertions.

The checked-in implementation and its focused tests already provide the
complete G11.S7 boundary:

1. Completion evidence binds the canonical obligation, proof plan and receipt,
   authoritative assurance, candidate tree, freshness, provenance, and
   validation identities. Assurance is derived independently of task and
   validation status. Legacy claims remain readable but cannot be upgraded.
2. Merge policy deterministically maps changed paths and AST scopes to proof,
   fallback, and rollout requirements. Shadow mode records its exact
   would-block result, selected canaries and enforcement fail closed, and a
   promotion receipt binds the plan, proof receipts, validations, policy, tree,
   and any bounded operator override.
3. Semantic changes invalidate obligations, receipts, criteria, and dependent
   goals transitively. Only affected provisional or verified goals reopen;
   replay is idempotent, historical receipts remain auditable, and replacement
   tasks retain dependency and conflict edges.
4. Planning candidates declare complete, finite proof impact and cost metadata.
   Priority includes critical path, downstream unlock, risk, freshness, cache
   likelihood, and available resources. Model routing receives only a bounded
   proof capsule, while unsupported and failed obligations create finite,
   semantically deduplicated repair work.

REF-267 through REF-270 already split this goal into those four independently
owned and validated implementation slices. Additional child goals would
duplicate completed scopes, so this repair records the missing objective
evidence instead of creating synthetic implementation work.

## G11.S7 Evidence Contract

| Enforcement boundary | Authoritative implementation | Executable evidence |
| --- | --- | --- |
| Receipt-backed completion | `goal_completion.py`, `formal_verification_contracts.py` | Fourteen tests prove complete identity mapping, evidence-derived assurance, independent validation status, fail-closed stale/unsupported/inconclusive/contradicted outcomes, tamper rejection, descendant aggregation, and conservative legacy decoding. |
| Proof-aware promotion | `merge_train.py`, `formal_verification_policy.py`, `todo_daemon/implementation_daemon.py` | Twelve tests prove deterministic shadow/canary/enforcement behavior, exact typed plan and tree binding, durable fallback and override receipts, cache reuse, policy pinning across retries, malformed identity rejection, and proved-tree preservation through rebase. |
| Semantic invalidation | `goal_completion.py`, `objective_task_janitor.py`, `proof_scope_index.py` | Six tests prove transitive input/obligation/receipt/criterion/goal impact, premise/contradiction/symbol seeds, selective deterministic reopening, replay idempotence, historical auditability, and retained replacement edges. |
| Bounded proof planning | `objective_graph.py`, `plan_evaluator.py`, `proof_context.py` | Twelve tests prove complete finite candidate metadata, multi-factor priority, bounded trust-partitioned router projection, rejected-alternative rationale, and finite deduplicated template/test/premise/manual-review work. |

The four required validation lanes contain 44 tests. Together they exercise the
complete plan-to-promotion-to-reopening lifecycle:

```text
changed scope
  -> policy-selected proof and fallback requirements
  -> bounded proof-aware plan and exact candidate tree
  -> authoritative proof plus independent validation receipts
  -> fail-closed completion and merge promotion
  -> transitive semantic invalidation and selective goal reopening
```

No provider assertion, passing validation alone, legacy assurance string, stale
cache result, timed-out attempt, or rebased unproved tree can cross the
authoritative gate. Retry may reuse only exact valid evidence and cannot repin
the candidate to a weaker policy after failure.

## Shared Goal Packet Coverage

REF-311 is a validation-gate member of
`goal_packet/ops/ipfs_datasets_py/1334a2482ee2`. The packet is one
trust-preserving lifecycle rather than five isolated features:

| Goal | Shared evidence advanced by this repair |
| --- | --- |
| G11.S1 | Versioned capabilities, contracts, provider isolation, and rollout policy define authoritative assurance and ensure availability or provider claims never become proof success. |
| G11.S2 | Exact AST scopes and templates create obligations; blob-keyed reuse, delete/rename invalidation, deterministic evidence projections, and bounded trust-partitioned capsules define their context. |
| G11.S3 | Policy-bounded Hammer requests, independently checked kernel reconstruction, complete cache identity, fenced cross-process single-flight, and explicit fallbacks produce trusted receipts. |
| G11.S4 | Durable dependency scheduling and one supervisor CPU/resource envelope order deterministic checks before translation, solver, kernel, focused/broad validation, and bounded public metrics. |
| G11.S7 | Completion and merge consume the exact receipts without conflating proof, validation, or task status; semantic invalidation then reopens only affected goals and produces finite repair plans. |

This covers the compact execution packet's shared evidence terms: exact task,
scope, obligation, plan, cache, receipt, policy, and tree identities; blob reuse
with delete/rename invalidation; bounded trusted context; cross-thread and
cross-process single-flight; shared CPU limits; deterministic-first validation;
explicit blocked and unsupported propagation; conclusive portfolio
cancellation; receipt-backed completion; fail-closed promotion; and
deterministic affected-goal reopening.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-311-objective-validation-repair.md`
- Canonical backlog evidence: REF-311 in
  `data/refactor_supervisor/refactor_todo.md`
- Existing G11.S7 implementation ownership: REF-267, REF-268, REF-269, and
  REF-270 in the canonical backlog
- Shared packet validation gates: REF-307, REF-308, REF-309, REF-310, and
  REF-311
- Supervisor-declared G11.S7 bundle target:
  `data/refactor_supervisor/objective_bundles/refactor-g11-g11-s7.todo.md`

The heap now points to this receipt and the exact missing evidence term. The
supervisor-fed todo already identifies the same G11.S7 goal, declared bundle
target, four validation commands, merge family, and implementation slices.
Generated bundle regeneration and task completion remain supervisor-owned;
this repair does not manually change REF-311 status or generated indexes.

## Validation

- PASS — receipt-backed goal completion lane: 14 tests.
- PASS — proof-aware merge promotion lane: 12 tests.
- PASS — semantic proof invalidation lane: 6 tests.
- PASS — bounded proof-aware planning lane: 12 tests.
- PASS — combined required G11.S7 validation: 44 tests.
- PASS — G11.S1 fresh-process packet lane: 55 tests.
- PASS — combined G11.S2, G11.S3, G11.S4, and G11.S7 packet lane: 157
  tests.
- PASS — objective evidence rescan: all 70 G11.S7 terms resolve; none remain
  missing.

All required commands and packet validation commands exited successfully. The
runs emitted only the existing `pytest-asyncio` unset-loop-scope deprecation
and four Python multiprocessing warnings about `fork()` in the cross-process
single-flight test. The objective rescan emitted the expected optional
`ipfs_kit_py` degraded-mode warning.
