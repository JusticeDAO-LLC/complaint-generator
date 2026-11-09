# REF-325 Objective Validation Repair

Date: 2026-07-23
Goal id: G11
Goal title: Make agent-supervisor proof-aware and context-efficient
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-325-objective-gap-c09345b22819.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g11.todo.md
Todo vector key: 2186fdd8e8874734
Canonical task key: task/v1/f0741306f1fb7ccac57002d06d9361ced2b125775cf1f30b06ba7bc56017354a
Canonical task CID: baguqeera6b2bgbxr7n6mvrlqalig3e3bz3jlcjlxlty7gcygxj54kyaxgvfa
Merge key: af49c55a500a854e
Merge family: goal_packet/ops/ipfs_datasets_py/025bf9ec4a21

## Repair Summary

The objective scan filed REF-325 because the G11 parent retained the synthetic
missing evidence term `objective validation repair`. Every named architecture
and implementation path was present, but the parent lacked one durable receipt
that connected the independently proved child goals into the complete
proof-aware supervisor lifecycle.

The runtime work is already fully decomposed:

- G11.S1 owns versioned capabilities, canonical contracts, isolated provider
  operations, evidence-derived assurance, and fail-closed rollout policy.
- G11.S2 owns exact AST scopes, reviewed obligation templates, deterministic
  evidence projections, incremental invalidation, and bounded context
  capsules.
- G11.S3 owns policy-bounded Hammer translation, trusted caching,
  cross-process single-flight, independent kernel reconstruction, and focused
  proof fallbacks.
- G11.S4 owns dependency-aware proof scheduling, one shared resource envelope,
  staged validation, and bounded public metrics.
- G11.S7 owns receipt-backed completion, proof-aware merge promotion,
  selective semantic invalidation, and bounded proof-aware planning.

Those boundaries are implemented by REF-244 through REF-260 and REF-267
through REF-270, and are represented by G11.S1, G11.S2, G11.S3, G11.S4, and
G11.S7 in the objective heap. Additional child goals would duplicate complete,
independently testable scopes. This repair therefore records the missing
parent-level validation proof and updates the heap to use it.

## Cohesive Evidence Contract

| Goal | Authoritative boundary | Executable proof |
| --- | --- | --- |
| G11.S1 | `formal_verification_capabilities.py`, `formal_verification_contracts.py`, `formal_verification_provider.py`, and `formal_verification_policy.py` define truthful routing, canonical identities, provider isolation, trust derivation, and rollout. | 55 tests prove versioned Hammer/TDFOL/external prover/Lean/Leanstral/frame-logic/knowledge-graph/ZKP health, bounded probes, deterministic contracts, all provider operations, and fail-closed policy. |
| G11.S2 | `code_proof_obligations.py`, `proof_obligation_templates.py`, `code_evidence_graph.py`, `proof_scope_index.py`, and `proof_context.py` compile changed code into exact, freshness-indexed obligations and bounded context. | 37 tests prove cold/warm scope identity, blob reuse, rename/delete invalidation, reviewed template selection, equivalent JSON/DuckDB projections, transitive invalidation, trust partitions, and every capsule limit. |
| G11.S3 | `ipfs_datasets_logic_provider.py`, `formal_verification_cache.py`, `kernel_verification.py`, and `proof_fallbacks.py` preserve the candidate/authority boundary through proof execution. | 42 tests prove complete cache binding, fenced thread/process single-flight, policy-bounded Hammer requests, exact independent kernel evidence, corrupt-candidate rejection, and explicit fallback routing. |
| G11.S4 | `proof_scheduler.py`, `resource_scheduler.py`, `validation_scheduler.py`, and `proof_metrics.py` execute proof DAGs beneath one supervisor-owned budget. | 34 tests prove critical-path ordering, bounded overlap, cancellation, restart recovery, CPU/process/memory/provider/context/token/latency backpressure, staged validation, and bounded metrics. |
| G11.S7 | `goal_completion.py`, `merge_train.py`, `objective_task_janitor.py`, and `plan_evaluator.py` consume proof evidence for completion, promotion, invalidation, and repair planning. | 44 tests prove independent proof and validation verdicts, exact tree/policy/plan receipts, fail-closed promotion, idempotent selective reopening, bounded router context, and finite deduplicated repair work. |

Together these lanes prove one lifecycle rather than five disconnected
features:

```text
changed tree and AST scopes
  -> reviewed, content-addressed obligations
  -> bounded trust-partitioned context
  -> policy- and resource-bounded proof plan
  -> untrusted solver candidates
  -> independent kernel evidence and trusted cache receipt
  -> proof-aware completion and merge
  -> transitive invalidation and selective goal reopening
```

## Shared Packet Evidence

The complete 212-test packet run directly covers every shared evidence family
in `goal_packet/ops/ipfs_datasets_py/025bf9ec4a21`:

- Versioned capability and provider protocols cover Hammer, TDFOL, external
  provers, Lean, Leanstral, frame logic, knowledge graphs, ZKP backends, and
  capability/translate/prove/reconstruct/verify/attest operations.
- Capability probes are bounded and cacheable. Availability remains routing
  information and cannot become proof success.
- Obligations and receipts bind exact repository trees, AST scopes, premises,
  translators, solvers, kernels, toolchains, policies, resource budgets, and
  candidate trees.
- Authoritative assurance is derived from current independent evidence.
  Provider assertions, LLM output, ATP/SMT candidates, stale cache entries, and
  simulated attestations cannot upgrade assurance.
- Blob-identical scopes avoid reparsing; deletes and renames deterministically
  invalidate stale records and their bounded dependent reason chains.
- Context capsules distinguish trusted facts, untrusted suggestions,
  unsupported semantics, and required fallbacks while enforcing row, byte,
  token, hop, excerpt, and transcript limits before prompt assembly.
- Cache keys bind every semantic and execution input. Fenced SQLite leases
  deduplicate live proof work across threads and processes.
- One supervisor envelope remains authoritative over CPU, processes, memory,
  disk, provider quota, context, tokens, and latency while model concurrency is
  accounted separately.
- Completion and merge require exact, fresh proof receipts independently of
  task or validation success. Affected provisional or verified goals reopen
  deterministically while unrelated goals remain stable.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Parent heap evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-325-objective-validation-repair.md`
- Child validation evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-307-objective-validation-repair.md`
  through
  `data/refactor_supervisor/discovery/2026-07-23-ref-311-objective-validation-repair.md`
- Canonical backlog anchor: REF-325 in
  `data/refactor_supervisor/refactor_todo.md`
- Current packet members: REF-326, REF-327, REF-328, REF-329, and REF-330
- Existing implementation ownership: REF-244 through REF-260 and REF-267
  through REF-270
- Bundle anchor:
  `data/refactor_supervisor/objective_bundles/refactor-g11.todo.md`

The parent heap now points to this receipt, while each child goal retains its
focused repair evidence and validation commands. The canonical backlog and
bundle shard already declare the same G11 hierarchy, packet members, outputs,
and validation gate. Task completion and generated todo-vector metadata remain
supervisor-owned; this repair does not manually change REF-325 status.

## Validation

- PASS — required G11 parent validation: 55 tests.
  - Capability lane: 12 tests.
  - Canonical contract lane: 12 tests.
  - Provider protocol lane: 9 tests.
  - Policy lane: 22 tests.
- PASS — combined G11.S2, G11.S3, G11.S4, and G11.S7 packet validation:
  157 tests.
- PASS — complete cohesive G11 packet: 212 tests.

All commands exited successfully. The runs emitted only the existing
`pytest-asyncio` unset-loop-scope deprecation warning and four Python
multiprocessing warnings about `fork()` in the cross-process single-flight
test.
