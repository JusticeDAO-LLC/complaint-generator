# REF-314 Objective Goal Gap

Date: 2026-07-23
Fingerprint: de16e332ec42364e7199204bd6e2b1a0f12e99f0
Goal id: G9.S2
Goal title: Plan from dependencies, conflicts, and objective value
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Priority: P0
Track: ops
Parent goals: G9
Graph depth: 1
Bundle: refactor/g9/g9-s2
Parallel lane: refactor/g9/g9-s2
Bundle strategy: explicit
Goal packet: goal_packet/ops/ipfs_datasets_py/c20825ca2cad
Goal packet role: packet_member
Goal packet goals: G9.S1, G9.S2, G9.S3, G9.S4
Goal packet task count: 4
Goal packet work item count: 4
Evidence methods: ast, embedding, exact, path
Embedding query: Plan from dependencies, conflicts, and objective value
AST query: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py, Goal, import, interface, output-input, migration, and validation prerequisites become explicit DAG edges with provenance., Only tasks whose prerequisite merge receipts succeeded are claimable., Priority includes critical-path length, slack, downstream unlock value, age, and configured objective priority., Cycles and missing dependencies produce bounded repair evidence rather than deadlock., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_vector_index.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py, Conflict surfaces include all predicted files, AST symbols, interfaces, submodules, and generated artifacts., Lane planning colors the conflict graph so overlapping tasks do not run concurrently unless explicitly allowed., Actual branch diffs and conflict receipts update future conflict weights., Planner output explains every co-location or separation decision., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py, Each eligible subgoal can produce multiple schema-validated plan branches through llm_router., Candidates declare predicted files and symbols, dependencies, validation proof, cost, risk, and expected objective delta., A deterministic evaluator selects a branch and retains rejected alternatives plus rationale., Router failure falls back to deterministic planning without blocking ready work., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q
Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
Predicted files: none
AST symbols: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py, Goal, import, interface, output-input, migration, and validation prerequisites become explicit DAG edges with provenance., Only tasks whose prerequisite merge receipts succeeded are claimable., Priority includes critical-path length, slack, downstream unlock value, age, and configured objective priority., Cycles and missing dependencies produce bounded repair evidence rather than deadlock., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_vector_index.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py, Conflict surfaces include all predicted files, AST symbols, interfaces, submodules, and generated artifacts., Lane planning colors the conflict graph so overlapping tasks do not run concurrently unless explicitly allowed., Actual branch diffs and conflict receipts update future conflict weights., Planner output explains every co-location or separation decision., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py, Each eligible subgoal can produce multiple schema-validated plan branches through llm_router., Candidates declare predicted files and symbols, dependencies, validation proof, cost, risk, and expected objective delta., A deterministic evaluator selects a branch and retains rejected alternatives plus rationale., Router failure falls back to deterministic planning without blocking ready work., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q
Interfaces: none
Submodules: none
Generated artifacts: none
Allow concurrent with: none

## Goal

Plan from dependencies, conflicts, and objective value

## Missing Evidence

- objective validation repair

## Present Evidence

- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py (path), .complaint_workspace/sessions/demo-user.json (ast), AUTONOMOUS_SESSION_REPORT.md (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py (path), .complaint_workspace/sessions/demo-user.json (ast), complaint_generator/local_evidence_import.py (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py (path), .complaint_workspace/sessions/demo-user.json (ast), docs/FEATURE_WIRING_MATRIX.json (ast)
- ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py: ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py (path), .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/standard-regression.yml (embedding:0.64)
- Goal: BATCH_202_PLAN.md (exact), CONTRIBUTING.md (exact), PHASE_2_COMPLETION_SUMMARY.md (exact)
- import: .complaint_workspace/sessions/demo-user.json (exact), .vscode/tasks.json (exact), AUTONOMOUS_SESSION_REPORT.md (exact)
- interface: AUTONOMOUS_SESSION_REPORT.md (exact), BATCH_254_258_SESSION_SUMMARY.md (exact), CONTRIBUTING.md (exact)
- output-input: README_OLD_FULL.md (embedding:0.39), docs/CONFIGURATION.md (embedding:0.39), docs/LEGAL_HOOKS.md (embedding:0.33)
- migration: .complaint_workspace/sessions/demo-user.json (exact), AUDIT_DICT_RETURNS_REPORT.md (exact), BATCH_254_258_SESSION_SUMMARY.md (exact)
- and validation prerequisites become explicit DAG edges with provenance.: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast)
- Only tasks whose prerequisite merge receipts succeeded are claimable.: .vscode/tasks.json (ast), adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast)
- Priority includes critical-path length: .complaint_workspace/sessions/site-sdk-user.json (ast), PHASE_2_COMPLETION_SUMMARY.md (embedding:0.39), adversarial_harness/__init__.py (ast)
- slack: docs/REFACTOR_SUPERVISOR_TASKBOARD.md (exact), ipfs_datasets_py/.github/config/workflow-auto-fix-config.yml (exact), ipfs_datasets_py/.github/workflows/AUTO_HEALING_COMPREHENSIVE_GUIDE.md (exact)
- downstream unlock value: adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast), adversarial_harness/hacc_evidence.py (ast)
- age: .complaint_workspace/sessions/demo-user.json (exact), .complaint_workspace/sessions/site-sdk-user.json (exact), .complaint_workspace/sessions/site-sdk-user2.json (exact)
- and configured objective priority.: .complaint_workspace/sessions/site-sdk-user.json (ast), AUTONOMOUS_SESSION_REPORT.md (ast), SESSION_SUMMARY_2024_02_24.md (embedding:0.35)
- Cycles and missing dependencies produce bounded repair evidence rather than deadlock.: .complaint_workspace/sessions/alias-script-user.json (ast), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/did-key-008c3dbfb02e6dd4bbaaaaab753abb3927af5d5b97a59ac2e30b8f8eb21d4388.json (ast)
- PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q: .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/standard-regression.yml (embedding:0.65), .vscode/tasks.json (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py (path), .complaint_workspace/sessions/demo-user.json (ast), docs/FEATURE_WIRING_MATRIX.json (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_vector_index.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_vector_index.py (path), .complaint_workspace/sessions/demo-user.json (ast), applications/server.py (ast)
- ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py: ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py (path), .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/standard-regression.yml (embedding:0.63)
- Conflict surfaces include all predicted files: .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast)
- AST symbols: .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/hacc_evidence.py (ast), docs/REFACTOR_SUPERVISOR_TASKBOARD.md (exact)
- interfaces: docs/API_REFERENCE.md (exact), docs/APPLICATIONS.md (exact), docs/GRAPHRAG_REFACTORING_ROADMAP.md (exact)
- submodules: .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/canary-ops-validation.yml (exact), .github/workflows/claim-support-regression.yml (exact)
- and generated artifacts.: SESSION_84_PROGRESS.md (embedding:0.39), SESSION_SUMMARY_2026_02_24_COMPLETE.md (embedding:0.52), applications/complaint_cli.py (ast)
- Lane planning colors the conflict graph so overlapping tasks do not run concurrently unless explicitly allowed.: .complaint_workspace/sessions/demo-user.json (ast), .vscode/tasks.json (ast), adversarial_harness/complainant.py (ast)
- Actual branch diffs and conflict receipts update future conflict weights.: adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast), adversarial_harness/demo_autopatch.py (ast)
- Planner output explains every co-location or separation decision.: complaint_generator/local_evidence_import.py (ast), docs/LLM_ROUTER.md (ast), docs/REFACTOR_SUPERVISOR_TASKBOARD.md (exact)
- PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q: .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/standard-regression.yml (embedding:0.65), .vscode/tasks.json (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/demo_autopatch.py (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py (path), .complaint_workspace/sessions/demo-user.json (ast), docs/FEATURE_WIRING_MATRIX.json (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py (path), .complaint_workspace/sessions/demo-user.json (ast), AUTONOMOUS_SESSION_REPORT.md (ast)
- ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py: ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py (path), .complaint_workspace/sessions/demo-user.json (ast), docs/FEATURE_WIRING_MATRIX.json (ast)
- Each eligible subgoal can produce multiple schema-validated plan branches through llm_router.: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast)
- Candidates declare predicted files and symbols: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast)
- dependencies: .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/canary-ops-validation.yml (exact), .github/workflows/claim-support-regression.yml (exact)
- validation proof: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast)
- cost: .complaint_workspace/sessions/site-sdk-user.json (exact), BATCH_328_API_RETURN_TYPES_SUMMARY.md (exact), EXTRACTION_PIPELINE_PROFILE_FINAL.md (exact)
- risk: .complaint_workspace/sessions/demo-user.json (exact), .complaint_workspace/sessions/site-sdk-user.json (exact), .github/pull_request_template.md (exact)
- and expected objective delta.: AUTONOMOUS_SESSION_REPORT.md (ast), TODO.md (embedding:0.35), docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md (embedding:0.33)
- A deterministic evaluator selects a branch and retains rejected alternatives plus rationale.: adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast), adversarial_harness/hacc_evidence.py (ast)
- Router failure falls back to deterministic planning without blocking ready work.: adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast), adversarial_harness/hacc_evidence.py (ast)
- PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q: .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/standard-regression.yml (embedding:0.63), .vscode/tasks.json (ast)

## Suggested Handling

Run and repair the objective validation command until it passes, then record the evidence.
