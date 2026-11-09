# REF-029 Objective Goal Gap

Date: 2026-07-21
Fingerprint: eac2cf021fa2796de39187b438c3c8ad0e0ab6f7
Goal id: G2
Goal title: Decompose oversized orchestration modules
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Priority: P0
Track: ops
Parent goals: none
Graph depth: 0
Bundle: refactor/g2
Parallel lane: refactor/g2
Bundle strategy: explicit
Goal packet: none
Goal packet role: none
Goal packet goals: none
Goal packet task count: 0
Goal packet work item count: 0
Evidence methods: ast, embedding, exact, path
Embedding query: Decompose oversized orchestration modules
AST query: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, mediator/__init__.py, mediator/claim_support_hooks.py, applications/complaint_workspace.py, applications/dashboard_ui.py, playwright/server.js
Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts

## Goal

Decompose oversized orchestration modules

## Missing Evidence

- objective validation repair

## Present Evidence

- docs/ARCHITECTURE.md: docs/ARCHITECTURE.md (path), DOCUMENTATION_INDEX.md (exact), README.md (exact)
- docs/REFACTOR_SUPERVISOR_TASKBOARD.md: docs/REFACTOR_SUPERVISOR_TASKBOARD.md (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast)
- mediator/mediator.py: mediator/mediator.py (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact)
- mediator/__init__.py: mediator/__init__.py (path), .github/workflows/claim-support-regression.yml (embedding:0.54), .github/workflows/standard-regression.yml (exact)
- mediator/claim_support_hooks.py: mediator/claim_support_hooks.py (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact)
- applications/complaint_workspace.py: applications/complaint_workspace.py (path), .complaint_workspace/sessions/demo-user.json (embedding:0.31), .github/workflows/claim-support-regression.yml (exact)
- applications/dashboard_ui.py: applications/dashboard_ui.py (path), .github/workflows/claim-support-regression.yml (embedding:0.39), .github/workflows/standard-regression.yml (embedding:0.43)
- playwright/server.js: playwright/server.js (path), TESTING.md (exact), applications/launcher.py (ast)

## Suggested Handling

Run and repair the objective validation command until it passes, then record the evidence.
