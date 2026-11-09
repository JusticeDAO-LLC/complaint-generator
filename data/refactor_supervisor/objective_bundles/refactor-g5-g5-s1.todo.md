# Objective Bundle: refactor/g5/g5-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-15: REF-015 Keep the refactor taskboard synchronized with generated goals and subgoals

## REF-015 Keep the refactor taskboard synchronized with generated goals and subgoals

- Status: completed
- Completion: manual
- Priority: P0
- Track: G5
- Depends on: 
- Outputs: scripts/refactor_agent_supervisor.py, docs/REFACTOR_SUPERVISOR_TASKBOARD.md
- Validation: python scripts/refactor_agent_supervisor.py seed --once
- Bundle: refactor/g5/g5-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G5.S1
- Missing evidence: The requested supervisor needs a refill loop and visible board state.
- AST symbols: PROJECT_ROOT, ACCELERATE_REPO, STATE_ROOT, QUEUE_PATH, GOALS_PATH, OBJECTIVE_PATH, TODO_PATH, BUNDLE_DIR, DATASET_DIR, DISCOVERY_DIR, GRAPH_PATH, STRATEGY_PATH, EVENTS_PATH, REFILL_STATE_PATH, SUPERVISOR_STATE_DIR, WORKTREE_ROOT, BUNDLE_LANE_ROOT, BUNDLE_LANE_MANIFEST, BUNDLE_COORDINATION_PATH, STATUS_PATH, PID_PATH, LOG_PATH, TASKBOARD_DOC_PATH, TASK_PREFIX, TASK_HEADER_PREFIX, TASK_TYPES, MODEL_NAME, _ensure_accelerate_import_path, _task_queue_class, _upstream_objective_runner
- Merge key: refactor/g5/g5-s1
- Candidate kind: seed
- Todo vector key: ref-015-keeptherefactortaskboardsynchronizedwithgenerate
- Acceptance: Queued task count is maintained above the configured floor.; Docs and JSON state are regenerated each cycle.

- [x] Task checkbox-16: REF-016 Record supervisor status, scan metrics, and queue counts for handoff

## REF-016 Record supervisor status, scan metrics, and queue counts for handoff

- Status: completed
- Completion: manual
- Priority: P0
- Track: G5
- Depends on: 
- Outputs: data/refactor_supervisor
- Validation: python scripts/refactor_agent_supervisor.py status
- Bundle: refactor/g5/g5-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G5.S1
- Missing evidence: Long-running automation needs inspectable state and a clean stop path.
- AST symbols: 
- Merge key: refactor/g5/g5-s1
- Candidate kind: seed
- Todo vector key: ref-016-recordsupervisorstatusscanmetricsandqueuecountsf
- Acceptance: Status JSON includes pid, heartbeat, scan summary, and counts.; Stop command terminates the daemon cleanly.
