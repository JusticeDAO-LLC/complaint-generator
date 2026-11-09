# REF-318 Objective Validation Repair

Date: 2026-07-23
Goal id: G3.S2
Goal title: Clarify graph, GraphRAG, and logic adapter boundaries
Gap source: /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-318-objective-gap-f617305438ae.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g3-g3-s2.todo.md
Todo vector key: 338da6f3156a11b3
Canonical task key: task/v1/8046f064d00a75963a1da2737bb7028008434a74abffc350e44731cdf92c6929
Canonical task CID: baguqeeraqbdpazgqbj2zmoq5ujzxxnycqaeegstuvp74guhei4y436jmneuq
Merge key: 52cd2ebe40218635
Merge family: goal_packet/ops/integrations/de7d9d2f5784

## Repair Summary

The objective scan filed REF-318 because G3.S2 had the named implementation
paths, acceptance evidence, and validation commands but no durable
`objective validation repair` receipt. The implementation remains divided
across the two bounded child goals already completed by REF-011 and REF-012:

1. Complaint-phase knowledge graphs own mutable domain entities,
   relationships, gap detection, serialization, and local fact projection.
2. The IPFS datasets graph adapter owns immutable snapshot identity, persistence
   requests, support-query requests, backend protocols, result normalization,
   and degraded fallback behavior.
3. GraphRAG remains an optional enrichment facade. It may generate, validate,
   refine, ingest, or query provider-owned ontologies, but it does not become
   the graph system of record and does not bypass graph persistence or
   provenance contracts.
4. Formal-logic callers use typed operations, capability states, gates, and
   errors. Provider and compatibility strings are interpreted once at the
   adapter boundary rather than throughout callers.

The exact graph and logic validation lanes pass in the current repository.
No smaller child goal is needed: REF-011 fully owns the persistence/query plane,
and REF-012 fully owns capability-gated formal logic. GraphRAG's optional
enrichment role is already isolated in its adapter facade and covered by the
same adapter regression lane.

## Boundary Contract

| Plane | Owner | Contract and non-responsibilities | Executable evidence |
| --- | --- | --- | --- |
| Complaint knowledge graph | `complaint_phases/knowledge_graph.py` | Owns in-memory entities and relationships. It serializes graph identity and lineage, projects local support facts, and calls graph ports for persistence/query; it does not import provider internals or infer backend persistence from provider availability. | `tests/test_complaint_phases.py` round-trips graph identity and entity provenance, persists a snapshot, and proves local fallback support retains graph/query/result lineage. |
| Graph adapter | `integrations/ipfs_datasets/graphs.py` | `GraphPersistenceRequest` and `GraphSupportQuery` define graph/version, snapshot/content identity, entities, relationships, filters, limits, and provenance. Runtime-checkable `GraphPersistence`, `GraphQuery`, and `GraphRepository` protocols separate write and query planes. | `tests/test_ipfs_adapter_layer.py` records exact backend requests, checks stable snapshot IDs and versions, verifies provenance fields, and exercises ranked local support fallback. |
| GraphRAG enrichment | `integrations/ipfs_datasets/graphrag.py` | Normalizes optional ontology/PDF provider calls and reports implemented, unavailable, not-implemented, or error metadata. It enriches graph workflows but owns neither canonical graph storage nor complaint-domain serialization. | `tests/test_ipfs_adapter_layer.py` covers ontology generation/validation/refinement and PDF GraphRAG facade delegation, unavailability, and initialization errors without bypassing the adapter. |
| Formal-logic contract | `lib/formal_logic/capabilities.py`, `integrations/ipfs_datasets/logic.py` | `FormalLogicOperation` and `LogicCapabilityState` are the branching API. Immutable capabilities expose available/degraded/implemented flags; typed gates raise typed unavailable/degraded errors; wire payload compatibility is centralized in `capability_state_from_payload`. | `tests/test_logic_capability_contract.py` covers all three states, strict and degraded gates, stable serialization, conservative conflict resolution, and legacy payload normalization. |
| Optional logic dependencies | repository-owned `ipfs_datasets_py` checkout | SymbolicAI configuration and IPLD storage are dependency health checks. They prove the optional providers used below the logic boundary load correctly; they do not replace the adapter capability contract. | `tests/test_symbolicai_logic_dependency.py` and `tests/test_ipld_logic_storage_dependency.py` both pass. |

The intended flow is:

```text
complaint entities/relationships
  -> graph adapter request (identity + version + provenance)
     -> optional persistence/query backend
     -> normalized backend result
     -> deterministic local query/noop persistence fallback when absent or failed

provider ontology/PDF features
  -> GraphRAG adapter facade
  -> normalized enrichment result
  -> graph adapter before canonical persistence

formal-logic caller
  -> typed operation + capability gate
  -> implemented result, explicit degraded diagnostic, or typed unavailable error
```

## Acceptance Evidence

- **Interfaces specify persistence, query, and provenance fields.**
  `GraphPersistenceRequest`, `GraphSupportQuery`, `GraphProvenance`,
  `GraphPersistence`, and `GraphQuery` make each field and responsibility
  explicit. Snapshot identifiers are derived from canonical graph content,
  graph version, and graph identity.
- **Fallback graph behavior remains covered.** Missing or failing persistence
  returns observable noop/degraded snapshot metadata without losing identity or
  provenance. Missing or failing query backends retain deterministic local
  filtering, scoring, deduplication, semantic clustering, and lineage.
- **Logic status distinguishes unavailable, degraded, and implemented.**
  `LogicCapabilityState` is the canonical enum; capability reports include
  stable counts and operation lists for every state.
- **Callers do not branch on fragile strings.** Callers gate with enum-backed
  `FormalLogicCapability` properties or typed exceptions. Legacy serialized
  strings are normalized only inside `capability_state_from_payload`, including
  conservative handling of conflicting fields.

## Shared Goal Packet Coverage

REF-318 is the member validation gate for
`goal_packet/ops/integrations/de7d9d2f5784`, containing G3.S1 and G3.S2.
Together with the REF-317 anchor receipt, the packet now has durable evidence
for the complete adapter lifecycle:

| Goal | Shared evidence confirmed |
| --- | --- |
| G3.S1 | Stable adapter-group keys and actionable optional-extra reasons feed one evidence, authority, and web parse contract while deterministic fallback parsing preserves existing behavior. |
| G3.S2 | Graph domain, persistence/query, and GraphRAG enrichment responsibilities are separated; identity and provenance survive backend and fallback paths; formal logic exposes typed unavailable, degraded, and implemented decisions. |

This repair does not alter REF-317 or duplicate its source-normalization work.
It supplies the G3.S2-specific receipt while preserving the single cohesive
packet boundary: normalized documents produce provenance-bearing graph inputs,
graph and GraphRAG adapters preserve those contracts, and formal logic consumes
typed graph/proof inputs through capability gates.

## Backlog Alignment

- Missing evidence term: objective validation repair
- Heap evidence:
  `data/refactor_supervisor/refactor_objective_heap.md`
- Repair evidence:
  `data/refactor_supervisor/discovery/2026-07-23-ref-318-objective-validation-repair.md`
- Canonical backlog evidence: REF-318 in
  `data/refactor_supervisor/refactor_todo.md`
- Existing graph implementation ownership: REF-011
- Existing logic implementation ownership: REF-012
- Shared packet validation gates: REF-317 and REF-318
- G3.S2 bundle evidence:
  `data/refactor_supervisor/objective_bundles/refactor-g3-g3-s2.todo.md`

The heap now points to this receipt and the exact missing evidence term. The
supervisor-fed todo already identifies the same goal, bundle, validation
commands, merge family, and child implementation slices. Generated bundle/index
regeneration and task completion remain supervisor-owned, so this repair does
not manually change REF-318 status or generated vector metadata.

## Validation

- PASS — required graph/phase adapter lane:
  `python -m pytest tests/test_complaint_phases.py tests/test_ipfs_adapter_layer.py -q`
  (152 passed).
- PASS — required optional logic dependency lane:
  `python -m pytest tests/test_symbolicai_logic_dependency.py tests/test_ipld_logic_storage_dependency.py -q`
  (2 passed).
- PASS — typed logic contract evidence:
  `python -m pytest tests/test_logic_capability_contract.py -q`
  (7 passed).

All commands exited successfully. Runs emitted only the existing
`pytest-asyncio` deprecation warning for the unset
`asyncio_default_fixture_loop_scope`; there were no failures or skips.
