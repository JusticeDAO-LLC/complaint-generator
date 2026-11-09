# REF-028 Objective Validation Repair

Date: 2026-07-21
Goal id: G1
Goal title: Stabilize repository boundaries
Gap source: data/refactor_supervisor/discovery/2026-07-21-ref-028-objective-gap-08d9b0956fd6.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g1.todo.md
Todo vector key: 5bcc4ed60686d81a
Merge key: 9c3d2b35296e9add
Merge family: objective/G1

## Repair Summary

The objective scan filed REF-028 because G1's parent evidence did not contain
the explicit objective validation repair proof term. G1 already divides the
repository-boundary objective into two bounded, independently validated child
goals:

- G1.S1 documents package ownership, runtime entrypoints, allowed import
  direction, and the shared-code ownership rule. The executable contract is
  configured in `pyproject.toml` and checked by `tests/test_package_imports.py`.
- G1.S2 owns removal of environment-sensitive import path mutation and routing
  optional dependency access behind the IPFS datasets adapter boundary. Static
  and import-time path checks live in `tests/test_package_imports.py`; degraded
  adapter behavior has its own `tests/test_ipfs_adapter_layer.py` lane.

The boundary suite is collectable and proves both halves of the repository
contract: configured layer direction remains synchronized with the architecture
documentation, and named production/script entrypoints do not mutate
`sys.path`. The existing child goals are already smaller than the parent and
name exact validation commands, so this validation-gate repair does not require
another child goal.

This record supplies the missing objective validation repair evidence directly
to G1. The objective heap, generated graph, central todo, and G1 bundle shard
all point to this same proof artifact, keeping the supervisor-fed backlog
aligned with the objective.

## Evidence Covered

- Missing evidence term: objective validation repair
- Boundary contract: `docs/ARCHITECTURE.md` and `pyproject.toml`
- Boundary tests: `tests/test_package_imports.py`
- Adapter degraded-mode lane: `tests/test_ipfs_adapter_layer.py`
- Heap evidence: `data/refactor_supervisor/discovery/2026-07-21-ref-028-objective-validation-repair.md`
- Backlog evidence: REF-028 in `data/refactor_supervisor/refactor_todo.md`
- Bundle evidence: REF-028 in `data/refactor_supervisor/objective_bundles/refactor-g1.todo.md`
- Graph evidence: G1 in `data/refactor_supervisor/objective_graph.json`

## Validation

- PASS — `python -m pytest --collect-only -q` (4,531 tests collected)
- PASS — `python -m pytest tests/test_package_imports.py -q` (5 passed)
