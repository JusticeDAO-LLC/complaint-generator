# Objective Bundle: refactor/g7

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: bundle objective-generated tasks so parallel daemons can work one lane at a time.
Conflict policy: keep edits inside this bundle when possible; use the LLM merge resolver for semantic conflicts.

## REF-033 Close objective gap: Rationalize frontend and review surfaces

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, data/refactor_supervisor/refactor_objective_heap.md
- Validation: python -m pytest --collect-only -q
- Bundle: refactor/g7
- Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g7.todo.md
- Bundle strategy: explicit
- Graph parents: none
- Graph depth: 0
- Parallel lane: refactor/g7
- Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
- Goal id: G7
- Missing evidence: objective validation repair
- Embedding query: Rationalize frontend and review surfaces
- AST query: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, applications/review_api.py, applications/ui_review.py, mediator/claim_support_hooks.py, tests/test_claim_support_review_playwright_smoke.py, tests/test_review_surface_site_playwright.py
- Surplus group: objective/G7
- Merge key: 69ba34392fd62c48
- Merge family: objective/G7
- Merge role: validation_gate
- Work item count: 1
- Work scope: objective_validation_repair
- Goal packet: 
- Goal packet role: 
- Goal packet goals: 
- Goal packet task count: 0
- Goal packet work item count: 0
- Candidate kind: validation_gate
- Todo vector key: a6b0c4054bac33c2
- Repair evidence: data/refactor_supervisor/discovery/2026-07-21-ref-033-objective-validation-repair.md; objective validation repair
- Acceptance: Objective scan filed this gap for G7. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-21-ref-033-objective-gap-eaafaa004d33.md, add code/tests/docs or child goals that prove the missing evidence terms are covered (objective validation repair), and keep the supervisor-fed backlog aligned with the objective heap.  Refine the objective heap if the gap needs smaller child goals.

## REF-334 Close objective gap: Rationalize frontend and review surfaces

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, data/refactor_supervisor/refactor_objective_heap.md
- Validation: python -m pytest --collect-only -q
- Bundle: refactor/g7
- Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g7.todo.md
- Bundle strategy: explicit
- Graph parents: none
- Graph depth: 0
- Parallel lane: refactor/g7
- Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
- Predicted files: 
- Changed paths: 
- AST symbols: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, applications/review_api.py, applications/ui_review.py, mediator/claim_support_hooks.py, tests/test_claim_support_review_playwright_smoke.py, tests/test_review_surface_site_playwright.py, data/refactor_supervisor/discovery/2026-07-21-ref-033-objective-validation-repair.md, objective validation repair
- Interfaces: 
- Submodules: 
- Generated artifacts: 
- Allow concurrent with: 
- Goal id: G7
- Canonical task key: task/v1/420c62ea20bc98db3a10c5324d940fa0954edbc7dc00afb8b1ff3899e774b560
- Canonical task CID: baguqeeraiiggf2raxsmnwoqqyuze3fapucku5w6h3qak7ofr744jtz3uwvqa
- Missing evidence: objective validation repair
- Embedding query: Rationalize frontend and review surfaces
- AST query: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, applications/review_api.py, applications/ui_review.py, mediator/claim_support_hooks.py, tests/test_claim_support_review_playwright_smoke.py, tests/test_review_surface_site_playwright.py, data/refactor_supervisor/discovery/2026-07-21-ref-033-objective-validation-repair.md, objective validation repair
- Surplus group: objective/G7
- Merge key: 69ba34392fd62c48
- Merge family: objective/G7
- Merge role: validation_gate
- Work item count: 1
- Work scope: objective_validation_repair
- Goal packet: 
- Goal packet role: 
- Goal packet goals: 
- Goal packet task count: 0
- Goal packet work item count: 0
- Candidate kind: validation_gate
- Todo vector key: a6b0c4054bac33c2
- Acceptance: Objective scan filed this gap for G7. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-334-objective-gap-eaafaa004d33.md, add code/tests/docs or child goals that prove the missing evidence terms are covered (objective validation repair), and keep the supervisor-fed backlog aligned with the objective heap.  Refine the objective heap if the gap needs smaller child goals.
