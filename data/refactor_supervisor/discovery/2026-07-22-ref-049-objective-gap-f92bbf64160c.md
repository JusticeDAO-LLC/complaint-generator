# REF-049 Objective Goal Gap

Date: 2026-07-22
Fingerprint: f92bbf64160c53ef86aa921f3fbad578af373fbf
Goal id: G9.S1
Goal title: Establish canonical coordination and merge flow
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Priority: P0
Track: ops
Parent goals: G9
Graph depth: 1
Bundle: refactor/g9/g9-s1
Parallel lane: refactor/g9/g9-s1
Bundle strategy: explicit
Goal packet: none
Goal packet role: none
Goal packet goals: none
Goal packet task count: 0
Goal packet work item count: 0
Evidence methods: ast, embedding, exact, path
Embedding query: Establish canonical coordination and merge flow
AST query: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/persistent_task_queue.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py, Every task has a stable canonical key or CID independent of board path and display id., Legacy markdown tasks migrate idempotently with board namespace provenance., Branches, events, retries, cooldowns, leases, and receipts carry canonical identity., Refill cannot create a second active task for the same canonical work item., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/multi_supervisor_runner.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py, A persistent scheduler discovers new and refilled tasks without restart., Workers claim ready tasks, release drained or blocked leases, and steal conflict-safe work., Lane count remains within configured capacity and no task executes under two accepted leases., The manifest is an authoritative live projection rather than a launch-time snapshot., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py, All implementation lanes enqueue merge candidates instead of racing the target checkout., The train deduplicates by canonical task and commit, rebases on the latest target, and preserves priority plus age fairness., One conflict fingerprint invokes at most one active resolver attempt., Bounded failures enter quarantine with a durable receipt instead of a polling retry loop., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py -q
Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts

## Goal

Establish canonical coordination and merge flow

## Missing Evidence

- objective validation repair

## Present Evidence

- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py (path), .complaint_workspace/sessions/demo-user.json (ast), AUTONOMOUS_SESSION_REPORT.md (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py (path), .complaint_workspace/sessions/demo-user.json (ast), complaint_generator/local_evidence_import.py (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/persistent_task_queue.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/persistent_task_queue.py (path), .complaint_workspace/sessions/demo-user.json (ast), applications/ui_review.py (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py (path), .complaint_workspace/sessions/demo-user.json (ast), SESSION_SUMMARY_2026_02_23.md (ast)
- ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py: ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py (path), .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/standard-regression.yml (embedding:0.62)
- ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py: ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py (path), .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/standard-regression.yml (embedding:0.63)
- Every task has a stable canonical key or CID independent of board path and display id.: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast)
- Legacy markdown tasks migrate idempotently with board namespace provenance.: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast)
- Branches: .github/workflows/canary-ops-validation.yml (exact), .github/workflows/claim-support-regression.yml (exact), .github/workflows/hacc-unit-regression.yml (exact)
- events: .complaint_workspace/sessions/demo-user.json (exact), .complaint_workspace/sessions/site-sdk-user.json (exact), .tmp-demo-output-sessions-fast-2/demo-output-user.json (exact)
- retries: BATCH_329_EXCEPTION_HANDLING_SUMMARY.md (exact), adversarial_harness/README.md (exact), adversarial_harness/complainant.py (ast)
- cooldowns: docs/REFACTOR_SUPERVISOR_TASKBOARD.md (exact), scripts/refactor_agent_supervisor.py (exact), ipfs_datasets_py/.github/scripts/MIGRATION-GUIDE-api-counter.md (ast)
- leases: docs/REFACTOR_SUPERVISOR_TASKBOARD.md (exact), docs/optimizers/STRUCTURED_JSON_LOG_SCHEMA.md (exact), output/hacc_grounded_smoke/grounding_bundle.json (exact)
- and receipts carry canonical identity.: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast)
- Refill cannot create a second active task for the same canonical work item.: adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast), adversarial_harness/hacc_evidence.py (ast)
- PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q: .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/standard-regression.yml (embedding:0.64), .vscode/tasks.json (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py (path), .complaint_workspace/sessions/demo-user.json (ast), docs/FEATURE_WIRING_MATRIX.json (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py (path), .complaint_workspace/sessions/demo-user.json (ast), docs/FEATURE_WIRING_MATRIX.json (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/multi_supervisor_runner.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/multi_supervisor_runner.py (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/session.py (ast)
- ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py: .complaint_workspace/sessions/demo-user.json (ast), docs/FEATURE_WIRING_MATRIX.json (ast), docs/FEATURE_WIRING_MATRIX.md (embedding:0.57)
- A persistent scheduler discovers new and refilled tasks without restart.: .complaint_workspace/sessions/demo-user.json (ast), .vscode/tasks.json (ast), adversarial_harness/complainant.py (ast)
- Workers claim ready tasks: .vscode/tasks.json (ast), DOCUMENTATION_INDEX.md (embedding:0.45), adversarial_harness/complainant.py (ast)
- release drained or blocked leases: adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast), adversarial_harness/hacc_evidence.py (ast)
- and steal conflict-safe work.: docs/CHRONOLOGY_FIRST_INTAKE_EVIDENCE_NEXT_BATCH_PLAN.md (ast), docs/IPFS_DATASETS_PY_NEXT_BATCH_PLAN.md (ast), docs/LLM_ROUTER.md (ast)
- Lane count remains within configured capacity and no task executes under two accepted leases.: adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast), adversarial_harness/hacc_evidence.py (ast)
- The manifest is an authoritative live projection rather than a launch-time snapshot.: .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/session.py (ast), applications/ui_review.py (ast)
- PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py -q: .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/standard-regression.yml (embedding:0.63), .vscode/tasks.json (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py (path), .complaint_workspace/sessions/demo-user.json (ast), applications/ui_review.py (ast)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py: .complaint_workspace/sessions/demo-user.json (ast), docs/ARCHITECTURE.md (embedding:0.31), docs/DOCUMENT_GENERATION_AGENTIC_OPTIMIZATION_PLAN.md (embedding:0.65)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast)
- ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py: .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/standard-regression.yml (embedding:0.67), docs/ARCHITECTURE.md (embedding:0.33)
- All implementation lanes enqueue merge candidates instead of racing the target checkout.: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast)
- The train deduplicates by canonical task and commit: docs/REFACTOR_SUPERVISOR_TASKBOARD.md (exact), integrations/ipfs_datasets/storage.py (ast), playwright/tests/complaint-flow.spec.js (ast)
- rebases on the latest target: .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (embedding:0.32), CONTRIBUTING.md (embedding:0.37)
- and preserves priority plus age fairness.: .complaint_workspace/sessions/site-sdk-user.json (ast), adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast)
- One conflict fingerprint invokes at most one active resolver attempt.: adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast), adversarial_harness/demo_autopatch.py (ast)
- Bounded failures enter quarantine with a durable receipt instead of a polling retry loop.: adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast), adversarial_harness/hacc_evidence.py (ast)
- PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py -q: .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/claim-support-regression.yml (embedding:0.63), .github/workflows/standard-regression.yml (embedding:0.67)

## Suggested Handling

Run and repair the objective validation command until it passes, then record the evidence.
