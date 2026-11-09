# REF-308 Objective Validation Repair

Date: 2026-07-23
Goal id: G11.S2
Goal title: Compile AST changes into obligations and bounded graph context
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-308-objective-gap-bb617b910906.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g11-g11-s2.todo.md
Todo vector key: b544307f3f4b191c
Canonical task key: task/v1/0310500be230a88b3fbd3add00bc8d7f6272a466d3e08e7725f5870b647bdb90
Canonical task CID: baguqeeraamifac7cgcuiwp55hloqbpenp5rhfjdg2pqi45zf6wdqwzd33oia
Merge key: d9423db67c646212
Merge family: goal_packet/ops/ipfs_datasets_py/1334a2482ee2

## Repair Summary

The objective scan filed REF-308 because G11.S2 did not contain the synthetic
`objective validation repair` evidence term. The scan found every named
implementation and test path, but its broad lexical matches for terms such as
`symbol`, `obligation`, `freshness`, and `receipt` were not a durable proof of
the compound AST-to-context assertions.

The checked-in implementation and its focused tests already provide the
complete G11.S2 pipeline:

1. Candidate changes compile into content-addressed Python scopes containing
   exact qualified symbols, imports, calls, transitions, interfaces, source
   hashes, and path coverage. Deletes, renames, generated files, syntax
   failures, non-Python files, and incomplete diffs remain explicit
   conservative scopes rather than disappearing.
2. Only exact, reviewed invariant templates materialize proof obligations.
   Template version and semantic identity bind each obligation and downstream
   cache key; ambiguous, malformed, version-mismatched, or conservative scopes
   fail closed instead of being matched heuristically.
3. Typed AST, task, validation, merge, and proof records project into one
   deterministic provenance graph with equivalent JSON and DuckDB query
   surfaces. Descriptive LLM or GraphRAG enrichment remains non-authoritative
   and cannot manufacture proof, merge, coverage, or completion edges.
4. The proof-scope index maps all semantic inputs to dependent obligations and
   receipts. Blob-identical scopes are reused, while delete, rename, template,
   toolchain, policy, assumption, interface, and dependency changes invalidate
   affected evidence transitively with a bounded reason chain.
5. Exact task, symbol, dependency, obligation, receipt, and contradiction
   neighborhoods become trust-partitioned context capsules. Row, byte, token,
   graph-hop, excerpt, and transcript bounds are enforced before rendering;
   repository-wide ASTs, full graphs, hidden witnesses, and unrelated
   transcripts cannot enter the prompt.

REF-248 through REF-252 already split this goal into those five independently
owned and validated implementation slices. Additional child goals would
duplicate complete scopes, so this repair records the missing objective
evidence instead of adding synthetic implementation work.

## G11.S2 Evidence Contract

| Compilation boundary | Authoritative implementation | Executable evidence |
| --- | --- | --- |
| Typed changed scopes | `code_proof_obligations.py`, `conflict_graph.py` | Nine tests cover exact Python facts, both sides of modifications, blob reuse, cold/warm identity, rename requalification, deletes, generated and malformed inputs, conservative partial diffs, and Git candidate collection. |
| Reviewed obligations | `proof_obligation_templates.py`, `code_proof_obligations.py` | Nine tests cover all initial invariant families, complete declarations, registry identity, mutation rejection, exact shape selection, ambiguity and version failure, materialization identity, cache identity, and fail-closed unsupported semantics. |
| Deterministic evidence graph | `code_evidence_graph.py`, `artifact_store.py` | Nine collected cases cover typed provenance channels, canonical JSON/DuckDB projection equivalence and indexes, forged-authority rejection, and descriptive-only LLM or GraphRAG enrichment across every protected authoritative edge kind. |
| Incremental scope index | `proof_scope_index.py`, `dataset_store.py` | Six tests cover every semantic dimension, transitive bounded invalidation, blob reuse, rename and delete handling, unrelated-evidence stability, and content-addressed persistence. |
| Bounded proof context | `proof_context.py`, `artifact_store.py` | Four tests cover exact selectors and safe hops, trust partitions, prohibited-data exclusion, every pre-render limit, deterministic truncation, and fail-closed impossible budgets. |

The five required validation lanes contain 37 tests. Together they exercise the
complete deterministic pipeline:

```text
candidate diff
  -> exact or conservative AST scopes
  -> exact reviewed template selection
  -> content-addressed proof obligations
  -> deterministic public evidence graph
  -> transitive freshness index
  -> bounded trust-partitioned context capsule
```

No free-form model claim, approximate template match, stale receipt, forged
authority edge, hidden witness, or repository-wide graph can cross these
boundaries. Unchanged blobs preserve canonical scope identities, while every
changed semantic input either invalidates affected evidence or remains an
explicit unsupported scope with required fallback checks.

## Shared Goal Packet Coverage

REF-308 is a validation-gate member of
`goal_packet/ops/ipfs_datasets_py/1334a2482ee2`. The repository-owned heap and
executable lanes cover the packet as one trust-preserving lifecycle:

| Goal | Shared evidence advanced by this repair |
| --- | --- |
| G11.S1 | Versioned capability, contract, provider, and policy records define the assurance, semantic, and trust inputs referenced by obligations and capsules. Availability and provider claims are not authoritative. |
| G11.S2 | Exact AST scopes compile through reviewed templates into content-addressed obligations, deterministic graph records, transitive freshness indexes, and bounded trust-partitioned context. |
| G11.S3 | Hammer translation, independent kernel reconstruction, complete cache identity, fenced cross-process single-flight, and explicit fallbacks consume the exact G11.S2 identities without weakening their trust. |
| G11.S4 | One supervisor resource envelope schedules deterministic checks, translation, solver, kernel, validation, and artifact work over the selected obligations and bounded context. |
| G11.S7 | Completion and merge gates consume exact obligations and receipts; semantic invalidation then reopens only affected goals and preserves unrelated evidence. |

This covers the compact execution packet's shared evidence terms: canonical
scope identities on cold and warm scans; blob reuse with delete and rename
invalidation; reviewed Python reference predicates; all initial invariant
templates including DAG acyclicity and legal transitions; deterministic
JSON/DuckDB projections; exact task, dependency, obligation, receipt, and
contradiction queries; trust-partitioned capsules; every prompt bound; complete
cache and receipt identity; cross-process single-flight; shared CPU limits; and
deterministic affected-goal reopening.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-308-objective-validation-repair.md`
- Canonical backlog evidence: REF-308 in
  `data/refactor_supervisor/refactor_todo.md`
- Existing G11.S2 implementation ownership: REF-248, REF-249, REF-250,
  REF-251, and REF-252 in the canonical backlog
- Shared packet validation gates: REF-307, REF-308, REF-309, REF-310, and
  REF-311
- G11.S2 bundle evidence:
  `data/refactor_supervisor/objective_bundles/refactor-g11-g11-s2.todo.md`

The heap now points to this receipt and the exact missing evidence term. The
supervisor-fed todo already identifies the same G11.S2 goal, bundle target,
five validation commands, merge family, and implementation slices. Generated
bundle/index regeneration and task completion remain supervisor-owned; this
repair does not manually change REF-308 status or generated todo metadata.

## Validation

- PASS — typed changed-scope lane: 9 tests.
- PASS — reviewed obligation-template lane: 9 tests.
- PASS — deterministic evidence-graph lane: 9 tests.
- PASS — incremental proof-scope index lane: 6 tests.
- PASS — bounded proof-context lane: 4 tests.
- PASS — combined required G11.S2 validation: 37 tests.
- PASS — shared G11 packet validation: the adjacent G11.S1, G11.S3, G11.S4,
  and G11.S7 receipts record the complete 212-test packet run.
- PASS — objective evidence rescan: all 97 G11.S2 terms resolve; none remain
  missing.

All required commands exited successfully. The runs emitted only the existing
`pytest-asyncio` unset-loop-scope deprecation warning. The objective rescan
emitted the expected optional `ipfs_kit_py` degraded-mode warning.
