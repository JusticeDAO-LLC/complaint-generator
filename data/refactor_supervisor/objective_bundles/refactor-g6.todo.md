# Objective Bundle: refactor/g6

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: bundle objective-generated tasks so parallel daemons can work one lane at a time.
Conflict policy: keep edits inside this bundle when possible; use the LLM merge resolver for semantic conflicts.

## REF-032 Close objective gap: Pay down error-handling and observability debt

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, data/refactor_supervisor/refactor_objective_heap.md
- Validation: python -m pytest --collect-only -q
- Bundle: refactor/g6
- Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g6.todo.md
- Bundle strategy: explicit
- Graph parents: none
- Graph depth: 0
- Parallel lane: refactor/g6
- Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
- Goal id: G6
- Missing evidence: objective validation repair
- Embedding query: Pay down error-handling and observability debt
- AST query: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, mediator/evidence_hooks.py, integrations/ipfs_datasets/search.py, applications/ui_review.py, complaint_generator/ui_optimizer_daemon.py, mediator/state.py, integrations/ipfs_datasets/scraper_daemon.py, scripts/gmail_duckdb_daemon.py, docs/OBSERVABILITY_INDEX.md, docs/observability/TROUBLESHOOTING.md
- Surplus group: objective/G6
- Merge key: de8ccdd4b6a5e381
- Merge family: objective/G6
- Merge role: validation_gate
- Work item count: 1
- Work scope: objective_validation_repair
- Goal packet: 
- Goal packet role: 
- Goal packet goals: 
- Goal packet task count: 0
- Goal packet work item count: 0
- Candidate kind: validation_gate
- Todo vector key: 524c6d1d9430d914
- Repair evidence: data/refactor_supervisor/discovery/2026-07-21-ref-032-objective-validation-repair.md; objective validation repair
- Acceptance: Objective scan filed this gap for G6. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-21-ref-032-objective-gap-3cddb89025f0.md, add code/tests/docs or child goals that prove the missing evidence terms are covered (objective validation repair), and keep the supervisor-fed backlog aligned with the objective heap.  Refine the objective heap if the gap needs smaller child goals.

## REF-333 Close objective gap: Pay down error-handling and observability debt

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, data/refactor_supervisor/refactor_objective_heap.md
- Validation: python -m pytest --collect-only -q
- Bundle: refactor/g6
- Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g6.todo.md
- Bundle strategy: explicit
- Graph parents: none
- Graph depth: 0
- Parallel lane: refactor/g6
- Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
- Predicted files: 
- Changed paths: 
- AST symbols: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, mediator/evidence_hooks.py, integrations/ipfs_datasets/search.py, applications/ui_review.py, complaint_generator/ui_optimizer_daemon.py, mediator/state.py, integrations/ipfs_datasets/scraper_daemon.py, scripts/gmail_duckdb_daemon.py, docs/OBSERVABILITY_INDEX.md, docs/observability/TROUBLESHOOTING.md, data/refactor_supervisor/discovery/2026-07-21-ref-032-objective-validation-repair.md, objective validation repair
- Interfaces: 
- Submodules: 
- Generated artifacts: 
- Allow concurrent with: 
- Goal id: G6
- Canonical task key: task/v1/f1868347c833d8b991b9ed8b39e01c211119c6967c4275f459edaa47a14c4799
- Canonical task CID: baguqeera6gdigr6igpmltenz5wfttya4eeirtruwprbhl5cz5wvepikmi6mq
- Missing evidence: objective validation repair
- Embedding query: Pay down error-handling and observability debt
- AST query: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, mediator/evidence_hooks.py, integrations/ipfs_datasets/search.py, applications/ui_review.py, complaint_generator/ui_optimizer_daemon.py, mediator/state.py, integrations/ipfs_datasets/scraper_daemon.py, scripts/gmail_duckdb_daemon.py, docs/OBSERVABILITY_INDEX.md, docs/observability/TROUBLESHOOTING.md, data/refactor_supervisor/discovery/2026-07-21-ref-032-objective-validation-repair.md, objective validation repair
- Surplus group: objective/G6
- Merge key: de8ccdd4b6a5e381
- Merge family: objective/G6
- Merge role: validation_gate
- Work item count: 1
- Work scope: objective_validation_repair
- Goal packet: 
- Goal packet role: 
- Goal packet goals: 
- Goal packet task count: 0
- Goal packet work item count: 0
- Candidate kind: validation_gate
- Todo vector key: 524c6d1d9430d914
- Acceptance: Objective scan filed this gap for G6. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-333-objective-gap-3cddb89025f0.md, add code/tests/docs or child goals that prove the missing evidence terms are covered (objective validation repair), and keep the supervisor-fed backlog aligned with the objective heap.  Refine the objective heap if the gap needs smaller child goals.
