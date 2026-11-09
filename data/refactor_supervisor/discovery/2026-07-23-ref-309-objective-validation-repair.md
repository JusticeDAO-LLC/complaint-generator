# REF-309 Objective Validation Repair

Date: 2026-07-23
Goal id: G11.S3
Goal title: Integrate Hammer, kernel reconstruction, and trusted caching
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-309-objective-gap-85e389fef7fe.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g11-g11-s3.todo.md
Todo vector key: 0a16dde0aff29f34
Canonical task key: task/v1/96317038f498a10e070eb52fe340837897feca240bc436f96bf270f3b47d8df0
Canonical task CID: baguqeerasyyxaohutcqq4byowux6gqedpcl75srebpcdn6ll6jyphnd5rxya
Merge key: 3a0837de078b20e1
Merge family: goal_packet/ops/ipfs_datasets_py/1334a2482ee2

## Repair Summary

The objective scan filed REF-309 because G11.S3 did not contain the synthetic
`objective validation repair` evidence term. The scan did find the named
implementation and test paths, but its broad lexical matches for individual
words such as `solver`, `kernel`, `policy`, and `stale` were not sufficient
proof of the goal's compound trust assertions.

The checked-in implementation already provides the complete G11.S3 boundary:

1. A supported, exact obligation is translated through the optional provider
   protocol into a deterministic Hammer request. The request binds premises,
   environment, policy, resource limits, tree, and upstream receipt
   provenance. Unsupported or ambiguous semantics fail closed into declared
   fallbacks.
2. A proof cache key binds every semantic and execution input. Lookup derives
   authoritative assurance from current receipt evidence, rejects untrusted or
   poisoned entries with reason codes, and uses fenced SQLite leases to
   deduplicate proof work across threads and processes.
3. Hammer/ATP/SMT output remains a candidate until an independent Lean, Coq, or
   Isabelle reconstruction packet is checked against the exact theorem,
   candidate, environment, source digest, and toolchain. Provider status text
   cannot raise the verdict.
4. Counterexamples and unsupported obligations become bounded, redacted,
   content-addressed diagnostics and declared focused checks. Shadow mode may
   continue without upgrading assurance; canary and enforcement modes retain
   their blocking requirement.

REF-253 through REF-256 already divide this goal into those four independently
owned and validated implementation slices. Additional child goals would
duplicate finished scopes, so this repair adds the missing objective evidence
record instead of manufacturing another implementation backlog.

## G11.S3 Evidence Contract

| Assurance boundary | Authoritative implementation | Executable evidence |
| --- | --- | --- |
| Hammer adaptation | `ipfs_datasets_logic_provider.py`, `formal_verification_provider.py` | Six provider tests prove deterministic lowering, exact premise/environment locks, bounded solver/resource policy, provenance retention, and typed unsupported fallback. |
| Trusted cache | `formal_verification_cache.py`, `formal_verification_contracts.py` | Ten cache tests mutate every key dimension, freshness and assurance, malformed bindings, solver-only evidence, simulated attestations, and thread/process lease ownership. |
| Kernel reconstruction | `kernel_verification.py`, `formal_verification_contracts.py` | Eighteen tests cover Lean, Coq, and Isabelle; independent provenance; exact theorem and toolchain binding; timeout, mismatch, forbidden declarations, `sorry`, `admit`, corrupt output, and unavailable kernels. |
| Proof fallback | `proof_fallbacks.py`, `validation_commands.py` | Eight tests cover bounded/redacted counterexamples, canonical unsat cores, declared command routing, manual review, rollout behavior, semantic deduplication, and transcript exclusion. |

The four required validation lanes contain 42 tests. They exercise the complete
candidate-to-authority flow without requiring a real external prover:

```text
typed obligation
  -> policy-bounded Hammer request
  -> untrusted portfolio candidate
  -> independently bound kernel reconstruction
  -> evidence-derived receipt
  -> freshness- and assurance-checked cache entry
```

At every incomplete edge, the result remains unsupported, unavailable,
inconclusive, or disproved and routes to an explicit fallback. No availability
probe, provider claim, solver-only candidate, stale cache entry, or simulated
attestation can enter the authoritative receipt path.

## Shared Goal Packet Coverage

REF-309 is a validation-gate member of
`goal_packet/ops/ipfs_datasets_py/1334a2482ee2`. The checked-in heap and
executable lanes cover the packet as one trust-preserving pipeline:

| Goal | Shared evidence advanced by this repair |
| --- | --- |
| G11.S1 | Versioned Hammer capability and provider-operation contracts establish that availability is not assurance and provider claims are not authoritative. |
| G11.S2 | Exact AST scopes, template identities, blob reuse/invalidation, and bounded trust-partitioned capsules supply the inputs used by Hammer and the cache. |
| G11.S3 | Deterministic Hammer requests, fenced trusted caching, independent reconstruction, and explicit proof fallbacks implement the central proof boundary. |
| G11.S4 | One supervisor CPU/resource envelope remains authoritative over translator, portfolio, kernel, validation, model, and artifact work. |
| G11.S7 | Completion and merge gates consume authoritative receipts; semantic invalidation reopens only affected provisional or verified goals. |

The packet therefore covers the compact execution packet's shared terms:
versioned capability and provider protocols; AST scopes; ATP/SMT candidates;
authoritative evidence-derived assurance; blob reuse with delete/rename
invalidation; CPU and resource limits; complete cache identity; bounded
capability probes; trusted context capsules; cross-process single-flight; and
deterministic affected-goal reopening.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-309-objective-validation-repair.md`
- Canonical backlog evidence: REF-309 in
  `data/refactor_supervisor/refactor_todo.md`
- Existing G11.S3 implementation ownership: REF-253, REF-254, REF-255, and
  REF-256 in the canonical backlog
- Shared packet validation gates: REF-307, REF-308, REF-309, REF-310, and
  REF-311
- G11.S3 bundle evidence:
  `data/refactor_supervisor/objective_bundles/refactor-g11-g11-s3.todo.md`

Task completion remains supervisor-owned; this repair does not manually change
REF-309 status or regenerate the supervisor-fed todo vector.

## Validation

- PASS — Hammer provider lane: 6 tests.
- PASS — trust-aware cache lane: 10 tests.
- PASS — independent kernel lane: 18 tests.
- PASS — proof fallback lane: 8 tests.
- PASS — G11.S1 fresh-process packet lane: 55 tests.
- PASS — combined G11.S2, G11.S3, G11.S4, and G11.S7 packet lane: 157 tests.
- PASS — objective rescan: no remaining G11.S3 evidence gap.

The required G11.S3 commands exited successfully. The only warnings were the
existing `pytest-asyncio` unset-loop-scope deprecation and four Python
multiprocessing warnings about `fork()` in the cross-process single-flight
test. The objective rescan also reported the expected optional `ipfs_kit_py`
degraded-mode warning. The G11.S1 lane is intentionally run in a fresh Python
process because its missing-provider test verifies that earlier imports have
not loaded the optional `ipfs_datasets_py` package.
