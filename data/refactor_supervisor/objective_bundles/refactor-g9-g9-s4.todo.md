# Objective Bundle: refactor/g9/g9-s4

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-44: REF-044 Publish authoritative throughput metrics and scheduler state

## REF-044 Publish authoritative throughput metrics and scheduler state

- Status: completed
- Completion: manual
- Priority: P1
- Track: G9
- Depends on: REF-037, REF-038, REF-039
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/event_log.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/supervisor_watchdog.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py -q
- Bundle: refactor/g9/g9-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S4
- Missing evidence: Status is split across launch manifests, wrapper files, lane state, and event logs, so planners cannot measure useful capacity.
- AST symbols: SCHEDULER_SNAPSHOT_SCHEMA_VERSION, SCHEDULER_SNAPSHOT_SCHEMA, LEGACY_SCHEDULER_SNAPSHOT_SCHEMAS, GOAL_COMPLETION_DIAGNOSTICS_SCHEMA_VERSION, GOAL_COMPLETION_DIAGNOSTICS_SCHEMA, SCHEDULER_PHASES, UNKNOWN_IDENTITY, REFILL_SCAN_TERMINAL_REASONS, REFILL_SCAN_SKIPPED_REASONS, REFILL_SCAN_FAILED_REASONS, REFILL_SCAN_SUCCESS_REASONS, _REFILL_SCAN_EVENT_TYPES, _READY_EVENTS, _ACTIVE_EVENTS, _IDLE_EVENTS, _BLOCKED_EVENTS, _VALIDATION_START_EVENTS, _VALIDATION_END_EVENTS, _MERGE_QUEUE_EVENTS, _MERGE_START_EVENTS, _MERGE_END_EVENTS, _RESOLVER_EVENTS, _COMPLETION_EVENTS, _now_iso, _parse_timestamp, _event_time, _seconds, _first_text, normalize_metric_identity, _identity_key
- Merge key: refactor/g9/g9-s4
- Candidate kind: seed
- Todo vector key: ref-044-publishauthoritativethroughputmetricsandschedule
- Acceptance: One event-derived snapshot reports ready, active, idle, blocked, validation, merge, and resolver phases.; Metrics include queue wait, implementation and validation duration, merge wait, conflict and retry rate, completions, tokens, and cost.; Every metric is keyed by canonical goal, subgoal, task, lane, and provider identity.; Scheduler decisions consume the same snapshot exposed to operators.

- [x] Task checkbox-45: REF-045 Make AST scans and implementation workspaces incremental and reusable

## REF-045 Make AST scans and implementation workspaces incremental and reusable

- Status: completed
- Completion: manual
- Priority: P2
- Track: G9
- Depends on: REF-040, REF-042, REF-043, REF-044
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/worktrees.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py -q
- Bundle: refactor/g9/g9-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S4
- Missing evidence: Refill scans reread the tracked codebase and each implementation creates fresh worktree and submodule setup even when inputs are unchanged.
- AST symbols: DEFAULT_EMBEDDING_DIMENSIONS, DEFAULT_EMBEDDING_MIN_SCORE, DEFAULT_BUNDLE_CLUSTER_MIN_SCORE, DEFAULT_OBJECTIVE_TASK_SUMMARY_PREFIX, parse_python_ast_quietly, DEFAULT_DISCOVERY_OUTPUT_PATH, DEFAULT_SURPLUS_FINDINGS_PER_GOAL, DEFAULT_SURPLUS_MIN_TERMS_PER_TODO, DEFAULT_SCAN_OVERSAMPLE_MULTIPLIER, DEFAULT_TASK_PREFIX, OBJECTIVE_SCAN_ANALYZER_VERSION, DEFAULT_AST_DATASET_MAX_CHARS, AST_DATASET_RECORD_SCHEMA_VERSION, LAUNCH_PLAYWRIGHT_VALIDATION_COMMAND, LAUNCH_PLAYWRIGHT_VALIDATION_MARKERS, LAUNCH_PLAYWRIGHT_VALIDATION_GATE_EVIDENCE, SCAN_SUFFIXES, SKIP_DIRS, _DERIVED_TASK_PLANNING_FIELDS, _bounded_task_planning_metadata, ObjectiveGoal, ObjectiveFinding, ObjectiveTaskRecord, ObjectiveHeapRecord, DEPENDENCY_EDGE_KINDS, SUCCESSFUL_MERGE_RECEIPT_STATUSES, CoverageSurfaceKind, CoverageStatus, _coverage_json_value, _coverage_enum_value
- Merge key: refactor/g9/g9-s4
- Candidate kind: seed
- Todo vector key: ref-045-makeastscansandimplementationworkspacesincrement
- Acceptance: AST and evidence records are reused by blob hash and only changed files are reparsed.; Deleted and renamed files invalidate stale evidence deterministically.; Clean worktrees and dependency setups can be pooled without sharing task-local mutations.; Cold and warm paths produce equivalent plans and validation results with measured warm-path savings.
