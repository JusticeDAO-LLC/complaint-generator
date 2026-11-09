# REF-066 Objective Validation Repair

Date: 2026-07-22
Goal id: G3
Goal title: Harden adapter contracts and degraded mode
Gap source: data/refactor_supervisor/discovery/2026-07-22-ref-066-objective-gap-1eba844e57d9.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g3.todo.md
Todo vector key: 0f8671bcac0f111f
Canonical task key: task/v1/f500136e795cd3a0abfbd06f56d0e513ee683b8691f8c0d78923d27f6396d1fa
Canonical task CID: baguqeera6uabg3tzltj2bk732bxvnuhfcpxgqo4gsh4mbv4jepjh6y4w2h5a
Merge key: db792db498edee78
Merge family: objective/G3

## Repair Summary

The objective scan filed REF-066 because a generated-objective refresh removed
G3's explicit `objective validation repair` proof from the parent goal's
evidence list. The adapter implementation and its bounded child-goal split
remain intact:

- G3.S1 owns stable optional-capability and document parsing contracts.
  `CapabilityStatus` and the capability report retain their canonical keys in
  available and degraded environments, missing extras include structured reason
  codes and actionable remediation, and document ingestion returns one
  normalized parse result while preserving local fallbacks.
- G3.S2 owns graph persistence, query, provenance, and formal-logic status
  boundaries. Graph operations expose typed requests and results with lineage,
  degraded persistence remains observable, and logic results distinguish
  implemented, not-implemented, and unavailable states without requiring
  callers to parse provider exception strings.

These child goals separate normalization and document ingestion from graph and
logic boundaries, and each already names exact implementation surfaces and
focused validations. Adding another child goal solely for the parent collection
gate would duplicate their scopes, so the objective heap needs no further
decomposition.

REF-066 reran the repository-wide collection gate successfully. This receipt is
linked from G3 in the objective heap and from REF-066 on both the canonical and
bundle-local todo boards. Task status remains supervisor-owned and is not
changed manually.

## Evidence Covered

- Missing evidence term: objective validation repair
- Stable capability and import diagnostics:
  `integrations/ipfs_datasets/capabilities.py`,
  `integrations/ipfs_datasets/loader.py`, and
  `integrations/ipfs_datasets/types.py`
- Shared document and degraded-mode contract:
  `integrations/ipfs_datasets/documents.py`, `mediator/evidence_hooks.py`,
  `tests/test_document_pipeline.py`, and
  `tests/test_document_pipeline_fallbacks.py`
- Graph persistence, query, and provenance contract:
  `integrations/ipfs_datasets/graphs.py`,
  `complaint_phases/knowledge_graph.py`, `tests/test_complaint_phases.py`, and
  `tests/test_ipfs_adapter_layer.py`
- Structured formal-logic status contract: `integrations/ipfs_datasets/logic.py`,
  `lib/formal_logic`, and `tests/test_ipfs_adapter_layer.py`
- Child-goal decomposition: G3.S1 and G3.S2 in
  `data/refactor_supervisor/refactor_objective_heap.md`
- Heap evidence:
  `data/refactor_supervisor/discovery/2026-07-22-ref-066-objective-validation-repair.md`
- Backlog evidence: REF-066 in `data/refactor_supervisor/refactor_todo.md`
- Bundle evidence: REF-066 in
  `data/refactor_supervisor/objective_bundles/refactor-g3.todo.md`

## Validation

- PASS — `python -m pytest --collect-only -q` (4,717 tests collected in 27.49
  seconds; exit code 0).
- PASS for repository-owned G3 behavior — a combined focused run of
  `tests/test_ipfs_adapter_layer.py`, `tests/test_document_pipeline.py`,
  `tests/test_document_pipeline_fallbacks.py`, and
  `tests/test_complaint_phases.py` completed with 211 passing tests and 2 skips.
- ENVIRONMENT LIMITATION — the same combined invocation also selected
  `tests/test_symbolicai_logic_dependency.py` and
  `tests/test_ipld_logic_storage_dependency.py`. Those two external dependency
  checks fail before adapter execution because the shared `ipfs_datasets_py`
  checkout does not export `ensure_symai_config_for_import` and reports its IPLD
  components unavailable. This is an upstream dependency-environment mismatch,
  not a failure of the in-repository G3 payload or degraded-mode contracts.

The collection run emitted only the existing `pytest-asyncio` deprecation
warning for the unset `asyncio_default_fixture_loop_scope` option.
