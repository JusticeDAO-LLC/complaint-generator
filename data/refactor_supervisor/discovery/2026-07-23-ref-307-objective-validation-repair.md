# REF-307 Objective Validation Repair

Date: 2026-07-23
Goal id: G11.S1
Goal title: Establish proof contracts, capabilities, and trust policy
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-307-objective-gap-17980a8aba65.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g11-g11-s1.todo.md
Todo vector key: 78e738b038ca0422
Canonical task key: task/v1/e67c6a7f4d6478eca87804c5be1faff4310d48ac1dd3b230ecf2b975d7e01f83
Canonical task CID: baguqeera4z6gu72nmr4ozkdyatc34h5p6qyq2sfmdxj3emhm6k4xlv7ad6bq
Merge key: 8632255e87745d9d
Merge family: goal_packet/ops/ipfs_datasets_py/1334a2482ee2

## Repair Summary

The objective scan filed REF-307 because the supervisor's live objective source
contained G11.S1 and its implementation evidence, but the checked-in objective
heap stopped at G9. The formal-verification implementation was therefore
present and executable while the repository-owned heap could not provide the
synthetic `objective validation repair` term or reproduce the G11 packet
structure.

This repair restores the G11 parent and the five goals in execution packet
`goal_packet/ops/ipfs_datasets_py/1334a2482ee2`:

- G11.S1 owns versioned capability, contract, provider, and policy boundaries.
- G11.S2 owns typed AST scopes, reviewed obligation templates, deterministic
  evidence projections, incremental invalidation, and bounded context capsules.
- G11.S3 owns Hammer translation, trust-aware cache identity, cross-thread and
  cross-process single-flight, independent kernel reconstruction, and focused
  fallbacks.
- G11.S4 owns proof-plan scheduling, one shared CPU/resource budget, staged
  validation, and queryable public metrics.
- G11.S7 owns proof-aware completion, merge promotion, semantic invalidation,
  deterministic goal reopening, and bounded proof-aware planning.

These goals are already decomposed into independently validated REF-244 through
REF-260 and REF-267 through REF-270 implementation slices. Creating additional
child goals would duplicate those bounded scopes rather than improve
deliverability. The heap now names the same paths, acceptance statements, and
validation commands as the supervisor-fed backlog for every goal in this
packet. G11.S5, G11.S6, and G11.S8 belong to separate execution packets and are
not expanded by this validation-gate repair.

The four required G11.S1 lanes pass without optional proof providers being
installed. The complete shared packet suite also passes, directly exercising
the compact execution packet's cross-process lease, cache-binding, AST scope,
blob reuse, bounded capsule, shared CPU budget, and deterministic goal-reopen
evidence terms. No production-code change is needed: the missing behavior was
the repository-owned objective proof contract, not the already-shipped runtime
contracts.

## Evidence Contract

| Goal | Authoritative implementation evidence | Focused proof |
| --- | --- | --- |
| G11.S1 | `formal_verification_capabilities.py`, `formal_verification_contracts.py`, `formal_verification_provider.py`, `formal_verification_policy.py` | 55 tests cover truthful capability health, deterministic identities, evidence-derived assurance, bounded isolation failures, rollout policy, and durable overrides. |
| G11.S2 | `code_proof_obligations.py`, `proof_obligation_templates.py`, `code_evidence_graph.py`, `proof_scope_index.py`, `proof_context.py` | Typed scopes bind exact AST/source identities; blob reuse, deletes, renames, paired projections, trust partitions, and all capsule bounds are tested. |
| G11.S3 | `ipfs_datasets_logic_provider.py`, `formal_verification_cache.py`, `kernel_verification.py`, `proof_fallbacks.py` | Cache keys bind every semantic/trust input; thread/process single-flight is fenced; provider claims cannot replace kernel evidence. |
| G11.S4 | `proof_scheduler.py`, `resource_scheduler.py`, `validation_scheduler.py`, `proof_metrics.py` | Dependency scheduling and restarts share authoritative CPU, process, memory, provider, model, validation, and artifact limits without collapsing verdicts. |
| G11.S7 | `goal_completion.py`, `merge_train.py`, `objective_task_janitor.py`, `plan_evaluator.py` | Proof and validation remain independent; only affected goals reopen; retries, invalidations, and repair work are deterministic and idempotent. |

## Trust Boundary Confirmed

- Capability availability is routing information and never proof success.
- Providers may return candidates and claims but cannot assert authoritative
  assurance.
- Solver and LLM candidates require independent, exact kernel evidence.
- Stale, malformed, poisoned, partial, simulated, timed-out, or unavailable
  evidence fails closed.
- Enforcement cannot silently degrade to shadow mode; an override is explicit,
  content-addressed, actor/reason/scope/tree/policy-bound, and expiring.
- Context capsules exclude repository-wide AST dumps, full graphs, hidden
  witnesses, and unrelated proof transcripts.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-307-objective-validation-repair.md`
- Canonical backlog evidence: REF-307, REF-308, REF-309, REF-310, and REF-311
  in `data/refactor_supervisor/refactor_todo.md`
- Existing implementation ownership: REF-244 through REF-260 and REF-267
  through REF-270 in the canonical backlog
- G11.S1 bundle evidence:
  `data/refactor_supervisor/objective_bundles/refactor-g11-g11-s1.todo.md`

Task completion remains supervisor-owned; this repair does not manually change
REF-307 status.

## Validation

- PASS — capability lane: 12 tests.
- PASS — canonical contract lane: 12 tests.
- PASS — provider protocol lane: 9 tests.
- PASS — policy lane: 22 tests.
- PASS — combined G11.S2, G11.S3, G11.S4, and G11.S7 packet validation:
  157 tests.

The runs emitted only the existing `pytest-asyncio` unset-loop-scope
deprecation warning and four Python multiprocessing warnings about `fork()` in
the cross-process single-flight test. All commands exited successfully.
