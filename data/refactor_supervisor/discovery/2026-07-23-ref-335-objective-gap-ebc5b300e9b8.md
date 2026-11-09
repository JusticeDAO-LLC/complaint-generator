# REF-335 Objective Goal Gap

Date: 2026-07-23
Fingerprint: ebc5b300e9b82e139b3c738162f51120a31e71f5
Goal id: G4.S1
Goal title: Create focused test lanes for refactor work
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Priority: P1
Track: ops
Parent goals: G4
Graph depth: 1
Bundle: refactor/g4/g4-s1
Parallel lane: refactor/g4/g4-s1
Bundle strategy: explicit
Goal packet: none
Goal packet role: none
Goal packet goals: none
Goal packet task count: 0
Goal packet work item count: 0
Evidence methods: ast, embedding, exact, path
Embedding query: Create focused test lanes for refactor work
AST query: pytest.ini, Makefile, docs/VERIFICATION_SUMMARY.md, A documented test lane map exists., Each P0 workstream has a named validation command., python -m pytest --collect-only -q, tests, pyproject.toml, Tests catch direct production imports where adapters are required., Tests avoid blocking intentional test-only imports., python -m pytest tests/test_package_imports.py -q, data/refactor_supervisor/discovery/2026-07-22-ref-071-objective-validation-repair.md, objective validation repair
Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
Predicted files: none
AST symbols: pytest.ini, Makefile, docs/VERIFICATION_SUMMARY.md, A documented test lane map exists., Each P0 workstream has a named validation command., python -m pytest --collect-only -q, tests, pyproject.toml, Tests catch direct production imports where adapters are required., Tests avoid blocking intentional test-only imports., python -m pytest tests/test_package_imports.py -q, data/refactor_supervisor/discovery/2026-07-22-ref-071-objective-validation-repair.md, objective validation repair
Interfaces: none
Submodules: none
Generated artifacts: none
Allow concurrent with: none

## Goal

Create focused test lanes for refactor work

## Missing Evidence

- objective validation repair

## Present Evidence

- pytest.ini: pytest.ini (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/hacc-unit-regression.yml (exact)
- Makefile: Makefile (path), .github/workflows/standard-regression.yml (exact), README.md (exact)
- docs/VERIFICATION_SUMMARY.md: docs/VERIFICATION_SUMMARY.md (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast)
- A documented test lane map exists.: applications/server.py (ast), docs/FEATURE_WIRING_MATRIX.json (ast), docs/REFACTOR_SUPERVISOR_TASKBOARD.md (exact)
- Each P0 workstream has a named validation command.: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast)
- python -m pytest --collect-only -q: .github/workflows/hacc-grounding-regression.yml (embedding:0.33), benchmarks/bench_sentence_window_scaling.py (ast), docs/FEATURE_WIRING_MATRIX.json (ast)
- tests: tests (path), .github/pull_request_template.md (exact), .github/workflows/claim-support-regression.yml (exact)
- pyproject.toml: pyproject.toml (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact)
- Tests catch direct production imports where adapters are required.: SESSION_SUMMARY_2026_02_24_COMPLETE.md (ast), adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast)
- Tests avoid blocking intentional test-only imports.: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast)
- python -m pytest tests/test_package_imports.py -q: .github/workflows/claim-support-regression.yml (embedding:0.55), .github/workflows/standard-regression.yml (embedding:0.60), .vscode/tasks.json (embedding:0.37)
- data/refactor_supervisor/discovery/2026-07-22-ref-071-objective-validation-repair.md: data/refactor_supervisor/discovery/2026-07-22-ref-071-objective-validation-repair.md (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast)
- objective validation repair: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast)

## Suggested Handling

Run and repair the objective validation command until it passes, then record the evidence.
