# REF-062 Objective Goal Gap

Date: 2026-07-22
Fingerprint: f307b3b05fa35e5cb8871ef2dc06403c421a5792
Goal id: G1.S1
Goal title: Map package ownership and runtime entrypoints
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Priority: P0
Track: ops
Parent goals: G1
Graph depth: 1
Bundle: refactor/g1/g1-s1
Parallel lane: refactor/g1/g1-s1
Bundle strategy: explicit
Goal packet: none
Goal packet role: none
Goal packet goals: none
Goal packet task count: 0
Goal packet work item count: 0
Evidence methods: ast, embedding, exact, path
Embedding query: Map package ownership and runtime entrypoints
AST query: mediator/mediator.py, applications/complaint_workspace.py, tests/test_claim_support_review_playwright_smoke.py, scripts/synthesize_hacc_complaint.py, tests/test_review_api.py, complaint_phases/denoiser.py, A short module ownership map exists., Entrypoints are grouped by CLI, web, mediator, and workflow role., python -m pytest tests/test_package_imports.py -q, docs/ARCHITECTURE.md, pyproject.toml, Architecture docs identify allowed imports., New work has a simple rule for where shared code belongs., python -m pytest tests/test_package_imports.py -q
Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
Predicted files: none
AST symbols: mediator/mediator.py, applications/complaint_workspace.py, tests/test_claim_support_review_playwright_smoke.py, scripts/synthesize_hacc_complaint.py, tests/test_review_api.py, complaint_phases/denoiser.py, A short module ownership map exists., Entrypoints are grouped by CLI, web, mediator, and workflow role., python -m pytest tests/test_package_imports.py -q, docs/ARCHITECTURE.md, pyproject.toml, Architecture docs identify allowed imports., New work has a simple rule for where shared code belongs.
Interfaces: none
Submodules: none
Generated artifacts: none
Allow concurrent with: none

## Goal

Map package ownership and runtime entrypoints

## Missing Evidence

- objective validation repair

## Present Evidence

- mediator/mediator.py: mediator/mediator.py (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact)
- applications/complaint_workspace.py: applications/complaint_workspace.py (path), .complaint_workspace/sessions/demo-user.json (embedding:0.31), .github/workflows/claim-support-regression.yml (exact)
- tests/test_claim_support_review_playwright_smoke.py: tests/test_claim_support_review_playwright_smoke.py (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast)
- scripts/synthesize_hacc_complaint.py: scripts/synthesize_hacc_complaint.py (path), .github/workflows/hacc-unit-regression.yml (exact), .vscode/launch.json (embedding:0.37)
- tests/test_review_api.py: tests/test_review_api.py (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast)
- complaint_phases/denoiser.py: complaint_phases/denoiser.py (path), .github/workflows/claim-support-regression.yml (embedding:0.45), .github/workflows/standard-regression.yml (embedding:0.51)
- A short module ownership map exists.: .vscode/launch.json (ast), docs/LLM_ROUTER.md (ast), docs/REFACTOR_SUPERVISOR_TASKBOARD.md (exact)
- Entrypoints are grouped by CLI: .vscode/tasks.json (ast), adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast)
- web: .complaint_workspace/sessions/did-key-web-inspect.json (exact), .vscode/tasks.json (exact), AUTONOMOUS_SESSION_REPORT.md (exact)
- mediator: mediator (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact)
- and workflow role.: .complaint_workspace/sessions/demo-user.json (ast), docs/ARCHITECTURE.md (embedding:0.31), docs/CHRONOLOGY_FIRST_INTAKE_EVIDENCE_NEXT_BATCH_PLAN.md (ast)
- python -m pytest tests/test_package_imports.py -q: .github/workflows/claim-support-regression.yml (embedding:0.55), .github/workflows/standard-regression.yml (embedding:0.60), .vscode/tasks.json (embedding:0.37)
- docs/ARCHITECTURE.md: docs/ARCHITECTURE.md (path), DOCUMENTATION_INDEX.md (exact), README.md (exact)
- pyproject.toml: pyproject.toml (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact)
- Architecture docs identify allowed imports.: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast)
- New work has a simple rule for where shared code belongs.: SESSION_84_FINAL_SUMMARY.md (ast), SESSION_SUMMARY_2026_02_24_COMPLETE.md (ast), adversarial_harness/complainant.py (ast)

## Suggested Handling

Run and repair the objective validation command until it passes, then record the evidence.
