# REF-030 Objective Validation Repair

Date: 2026-07-21
Goal id: G3
Goal title: Harden adapter contracts and degraded mode
Gap source: data/refactor_supervisor/discovery/2026-07-21-ref-030-objective-gap-1eba844e57d9.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g3.todo.md
Todo vector key: 0f8671bcac0f111f
Merge key: db792db498edee78
Merge family: objective/G3

## Repair Summary

The objective scan filed REF-030 because G3's parent evidence did not contain
the explicit objective validation repair proof term. G3 already divides adapter
contract hardening into two bounded, independently testable child goals:

- G3.S1 owns the stable capability and document payload boundary. Capability
  reports expose consistent provider, availability, module, contract-family,
  error-type, and degraded-reason fields. Document inputs share one normalized
  parse result while supported local fallbacks remain usable when optional
  provider modules are unavailable.
- G3.S2 owns graph persistence/query/provenance and formal-logic status
  boundaries. Graph extraction, snapshot, and support-query results use typed
  payload models and canonical adapter metadata. Logic results expose structured
  implementation status and backend availability instead of requiring callers
  to interpret provider exception strings.

The contract-focused adapter assertions and the complete document fallback
suite pass in degraded mode. The repository-wide collection gate also passes,
proving that every named G3 validation lane remains discoverable. The existing
child goals are already smaller than the parent and name the exact implementation
and test surfaces, so this validation-gate repair does not require another child
goal.

This record supplies the missing objective validation repair evidence directly
to G3. The objective heap, generated graph, central todo, and G3 bundle shard all
point to the same proof artifact, keeping the supervisor-fed backlog aligned
with the objective.

## Evidence Covered

- Missing evidence term: objective validation repair
- Capability and import contract: `integrations/ipfs_datasets/capabilities.py`,
  `integrations/ipfs_datasets/loader.py`, and `integrations/ipfs_datasets/types.py`
- Document degraded-mode contract: `integrations/ipfs_datasets/documents.py`,
  `mediator/evidence_hooks.py`, and `tests/test_document_pipeline_fallbacks.py`
- Graph boundary: `integrations/ipfs_datasets/graphs.py`,
  `complaint_phases/knowledge_graph.py`, and `tests/test_ipfs_adapter_layer.py`
- Logic boundary: `integrations/ipfs_datasets/logic.py`, `lib/formal_logic`, and
  `tests/test_ipfs_adapter_layer.py`
- Heap evidence: `data/refactor_supervisor/discovery/2026-07-21-ref-030-objective-validation-repair.md`
- Backlog evidence: REF-030 in `data/refactor_supervisor/refactor_todo.md`
- Bundle evidence: REF-030 in `data/refactor_supervisor/objective_bundles/refactor-g3.todo.md`
- Graph evidence: G3 in `data/refactor_supervisor/objective_graph.json`

## Validation

- PASS — `python -m pytest --collect-only -q` (4,531 tests collected)
- PASS — `python -m pytest tests/test_ipfs_adapter_layer.py -k 'capability or parse_document or extract_graph_from_text or persist_graph_snapshot or query_graph_support or logic_stubbed' -q` (19 passed, 74 deselected)
- PASS — `python -m pytest tests/test_document_pipeline_fallbacks.py -q` (27 passed)

The full optional formal-logic dependency lane is collectable but cannot execute
in this worktree's shared dependency environment: the resolved external
`ipfs_datasets_py` checkout lacks `ensure_symai_config_for_import`, after which
SymbolicAI attempts to create `/usr/.symai` and receives `PermissionError`. This
environmental dependency failure occurs before the G3 adapter result contract is
called; the in-repository structured logic adapter contract is covered by the
passing focused assertions above.
