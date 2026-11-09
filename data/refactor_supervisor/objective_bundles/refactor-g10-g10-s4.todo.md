# Objective Bundle: refactor/g10/g10-s4

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-210: REF-210 Generate bounded goals, subgoals, and tasks from uncovered or inconclusive evidence

## REF-210 Generate bounded goals, subgoals, and tasks from uncovered or inconclusive evidence

- Status: completed
- Completion: manual
- Priority: P1
- Track: G10
- Depends on: REF-205, REF-207, REF-209
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_coverage.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_generation.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_generation.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q
- Bundle: refactor/g10/g10-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S4
- Missing evidence: Uncovered acceptance criteria and inconclusive analysis should become reviewable, dependency-linked work instead of silently draining the board.
- AST symbols: GOAL_COVERAGE_SCHEMA_VERSION, UNMAPPED_GOAL_ID, DEFAULT_FINDING_MIN_SCORE, DEFAULT_EVIDENCE_MAX_AGE_SECONDS, MISSING_ACCEPTANCE_CRITERION, CoverageSurface, _payload, _nested_sources, _items, _field_items, _first, _canonical, _stable_id, _normalized, _tokens, _similarity, _utc, _bool, _freshness_bool, _status_value, _coverage_payload, _scheduled_for_goal, _actionable_finding, _SURFACE_FIELDS, detect_goal_coverage_contradictions, discover_goal_contradictions, CoverageEdge, ValidationReceiptCoverage, AcceptanceCoverage, FindingAssignment
- Merge key: refactor/g10/g10-s4
- Candidate kind: seed
- Todo vector key: ref-210-generateboundedgoalssubgoalsandtasksfromuncovere
- Acceptance: Deterministic rules and llm_router proposals can create bounded child goals, subgoals, and tasks from uncovered criteria, unsupported surfaces, or contradiction receipts.; Generated work records parent objective terms, expected evidence delta, dependencies, predicted files and symbols, validation, confidence, cost, and novelty.; Canonical identity and semantic deduplication prevent equivalent goals or tasks from being regenerated across cycles.; Depth, breadth, token, retry, and open-work limits keep autonomous refinement finite and scheduler-aware.

- [x] Task checkbox-211: REF-211 Migrate existing goals and expose trustworthy completion diagnostics

## REF-211 Migrate existing goals and expose trustworthy completion diagnostics

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-202, REF-206, REF-208, REF-209, REF-210
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_tracker.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/implementation_supervisor_runner.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_implementation_supervisor_runner.py -q
- Bundle: refactor/g10/g10-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S4
- Missing evidence: Existing completed goals need a safe migration path and operators need to see confidence and missing proof without reading raw event logs.
- AST symbols: GOAL_COMPLETION_SCHEMA_VERSION, GOAL_COMPLETION_MIGRATION_SCHEMA_VERSION, DEFAULT_EVIDENCE_FRESHNESS_SECONDS, DEFAULT_CLOCK_SKEW_SECONDS, GoalState, _GOAL_STATE_ALIASES, LEGACY_COMPLETED_GOAL_STATES, is_legacy_completed_goal_state, normalize_goal_state, legal_goal_transitions, is_terminal_goal_state, is_schedulable_goal_state, IllegalGoalTransitionError, IllegalGoalTransition, _utc_datetime, _now, _criterion_key, _json_value, _canonical_json, _stable_fingerprint, _string_tuple, _mapping_tuple, _ASSURANCE_ALIASES, _assurance_level, _proof_verdict, _proof_freshness, CONTRADICTION_KINDS, ContradictionEvidence, _PROOF_INVALIDATION_EVENT_FIELDS, _proof_invalidation_mapping
- Merge key: refactor/g10/g10-s4
- Candidate kind: seed
- Todo vector key: ref-211-migrateexistinggoalsandexposetrustworthycompleti
- Acceptance: Legacy completed goals migrate idempotently to provisional or verified state based on available evidence, never by optimistic default.; Status and manifest projections show lifecycle state, confidence, uncovered criteria, stale evidence, analyzer health, exhaustion quorum, and reopen reasons.; Schema versioning and compatibility readers preserve existing boards, events, and automation during rollout.; The migration can be previewed and resumed safely after interruption.

- [x] Task checkbox-212: REF-212 Add end-to-end regression tests for truthful goal completion and autonomous refill

## REF-212 Add end-to-end regression tests for truthful goal completion and autonomous refill

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-203, REF-204, REF-205, REF-208, REF-209, REF-210, REF-211
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_lifecycle_e2e.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_lifecycle_e2e.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py -q
- Bundle: refactor/g10/g10-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S4
- Missing evidence: The completion and refill contract needs system-level regression coverage across restart, concurrency, stale evidence, analyzer failure, and contradiction scenarios.
- AST symbols: CRITERION, _git, _seed_repository, _completion_gate, _evidence, test_stale_fingerprints_cannot_complete_goal_and_reopened_goal_refills_board, test_restart_after_legacy_migration_preserves_lineage_quorum_and_operator_truth, completed, repo, source, objective_path, todo_path, binding, members, discovery_dir, bundle_dir, state_dir, strategy_path, events_path, initial_findings, stale_fingerprint, duplicate_only, projection, now, identity, gate, completion, contradiction, reopening, generated
- Merge key: refactor/g10/g10-s4
- Candidate kind: seed
- Todo vector key: ref-212-addend-to-endregressiontestsfortruthfulgoalcompl
- Acceptance: Tests distinguish threshold skip, cooldown, duplicate-only, healthy exhaustion, parser failure, timeout, partial coverage, and successful generation.; Scenarios prove that stale fingerprints cannot certify completion and that later relevant findings reopen goals and refill the board.; Concurrent serial and bundle supervisors emit one canonical receipt and do not duplicate generated goals or tasks.; Restart and migration preserve evidence lineage, quorum state, dependencies, and truthful operator projections.
