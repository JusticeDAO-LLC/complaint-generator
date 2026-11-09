# REF-033 Objective Goal Gap

Date: 2026-07-21
Fingerprint: eaafaa004d33471a4676ccd7f714393150415b96
Goal id: G7
Goal title: Rationalize frontend and review surfaces
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Priority: P1
Track: ops
Parent goals: none
Graph depth: 0
Bundle: refactor/g7
Parallel lane: refactor/g7
Bundle strategy: explicit
Goal packet: none
Goal packet role: none
Goal packet goals: none
Goal packet task count: 0
Goal packet work item count: 0
Evidence methods: ast, exact, path
Embedding query: Rationalize frontend and review surfaces
AST query: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, applications/review_api.py, applications/ui_review.py, mediator/claim_support_hooks.py, tests/test_claim_support_review_playwright_smoke.py, tests/test_review_surface_site_playwright.py
Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts

## Goal

Rationalize frontend and review surfaces

## Missing Evidence

- objective validation repair

## Present Evidence

- docs/ARCHITECTURE.md: docs/ARCHITECTURE.md (path), DOCUMENTATION_INDEX.md (exact), README.md (exact)
- docs/REFACTOR_SUPERVISOR_TASKBOARD.md: docs/REFACTOR_SUPERVISOR_TASKBOARD.md (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast)
- applications/review_api.py: applications/review_api.py (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast)
- applications/ui_review.py: applications/ui_review.py (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast)
- mediator/claim_support_hooks.py: mediator/claim_support_hooks.py (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact)
- tests/test_claim_support_review_playwright_smoke.py: tests/test_claim_support_review_playwright_smoke.py (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast)
- tests/test_review_surface_site_playwright.py: tests/test_review_surface_site_playwright.py (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast)

## Suggested Handling

Run and repair the objective validation command until it passes, then record the evidence.
