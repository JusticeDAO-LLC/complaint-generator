# REF-324 Objective Goal Gap

Date: 2026-07-23
Fingerprint: d2eeaaabba5320268eead80e35f45257b6c59975
Goal id: G2.S2
Goal title: Reduce application surface coupling
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Priority: P0
Track: ops
Parent goals: G2
Graph depth: 1
Bundle: refactor/g2/g2-s2
Parallel lane: refactor/g2/g2-s2
Bundle strategy: explicit
Goal packet: none
Goal packet role: none
Goal packet goals: none
Goal packet task count: 0
Goal packet work item count: 0
Evidence methods: ast, embedding, exact, path
Embedding query: Reduce application surface coupling
AST query: applications/complaint_workspace.py, One handler group is isolated., Routes keep the same response shape., python -m pytest tests/test_review_api.py -q, applications/dashboard_ui.py, playwright/server.js, Fixture builders are named and reusable., Playwright smoke tests remain stable., python -m pytest tests/test_claim_support_review_playwright_smoke.py -q
Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
Predicted files: none
AST symbols: applications/complaint_workspace.py, One handler group is isolated., Routes keep the same response shape., python -m pytest tests/test_review_api.py -q, applications/dashboard_ui.py, playwright/server.js, Fixture builders are named and reusable., Playwright smoke tests remain stable., python -m pytest tests/test_claim_support_review_playwright_smoke.py -q
Interfaces: none
Submodules: none
Generated artifacts: none
Allow concurrent with: none

## Goal

Reduce application surface coupling

## Missing Evidence

- objective validation repair

## Present Evidence

- applications/complaint_workspace.py: applications/complaint_workspace.py (path), .complaint_workspace/sessions/demo-user.json (embedding:0.31), .github/workflows/claim-support-regression.yml (exact)
- One handler group is isolated.: .vscode/tasks.json (ast), docs/REFACTOR_SUPERVISOR_TASKBOARD.md (exact), ipfs_datasets_py/.vscode/tasks.json (ast)
- Routes keep the same response shape.: adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast), adversarial_harness/hacc_evidence.py (ast)
- python -m pytest tests/test_review_api.py -q: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .github/workflows/claim-support-regression.yml (embedding:0.58)
- applications/dashboard_ui.py: applications/dashboard_ui.py (path), .github/workflows/claim-support-regression.yml (embedding:0.39), .github/workflows/standard-regression.yml (embedding:0.43)
- playwright/server.js: playwright/server.js (path), TESTING.md (exact), applications/launcher.py (ast)
- Fixture builders are named and reusable.: .complaint_workspace/sessions/demo-user.json (ast), .vscode/launch.json (ast), adversarial_harness/complainant.py (ast)
- Playwright smoke tests remain stable.: SESSION_SUMMARY_2026_02_24_COMPLETE.md (ast), adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast)
- python -m pytest tests/test_claim_support_review_playwright_smoke.py -q: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .github/workflows/claim-support-regression.yml (embedding:0.73)

## Suggested Handling

Run and repair the objective validation command until it passes, then record the evidence.
