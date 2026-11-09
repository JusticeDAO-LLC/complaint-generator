# Objective Bundle: refactor/g10/g10-s3

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-206: REF-206 Define an evidence-backed goal lifecycle and completion state machine

## REF-206 Define an evidence-backed goal lifecycle and completion state machine

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-200
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_tracker.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q
- Bundle: refactor/g10/g10-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S3
- Missing evidence: The objective graph currently treats completed task statuses as sufficient even when completion evidence and validation receipts are absent.
- AST symbols: GOAL_COMPLETION_SCHEMA_VERSION, GOAL_COMPLETION_MIGRATION_SCHEMA_VERSION, DEFAULT_EVIDENCE_FRESHNESS_SECONDS, DEFAULT_CLOCK_SKEW_SECONDS, GoalState, _GOAL_STATE_ALIASES, LEGACY_COMPLETED_GOAL_STATES, is_legacy_completed_goal_state, normalize_goal_state, legal_goal_transitions, is_terminal_goal_state, is_schedulable_goal_state, IllegalGoalTransitionError, IllegalGoalTransition, _utc_datetime, _now, _criterion_key, _json_value, _canonical_json, _stable_fingerprint, _string_tuple, _mapping_tuple, _ASSURANCE_ALIASES, _assurance_level, _proof_verdict, _proof_freshness, CONTRADICTION_KINDS, ContradictionEvidence, _PROOF_INVALIDATION_EVENT_FIELDS, _proof_invalidation_mapping
- Merge key: refactor/g10/g10-s3
- Candidate kind: seed
- Todo vector key: ref-206-defineanevidence-backedgoallifecycleandcompletio
- Acceptance: Goals distinguish active, provisionally complete, verified complete, analysis inconclusive, blocked, and reopened states with legal transitions.; Completion evidence names acceptance criterion, producing task or scan, validation receipt, repository tree, freshness, and provenance CID.; Task completion alone can make a goal provisional but cannot make it verified.; Missing, stale, failed, or contradictory evidence fails closed with an actionable reason.

- [x] Task checkbox-207: REF-207 Build goal-to-task, code, AST, acceptance, and validation coverage maps

## REF-207 Build goal-to-task, code, AST, acceptance, and validation coverage maps

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-201, REF-206
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_coverage.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_vector_index.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_coverage.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_coverage.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q
- Bundle: refactor/g10/g10-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S3
- Missing evidence: Goal completion cannot be assessed when acceptance criteria are not mapped to implementation surfaces and proof-producing validations.
- AST symbols: GOAL_COVERAGE_SCHEMA_VERSION, UNMAPPED_GOAL_ID, DEFAULT_FINDING_MIN_SCORE, DEFAULT_EVIDENCE_MAX_AGE_SECONDS, MISSING_ACCEPTANCE_CRITERION, CoverageSurface, _payload, _nested_sources, _items, _field_items, _first, _canonical, _stable_id, _normalized, _tokens, _similarity, _utc, _bool, _freshness_bool, _status_value, _coverage_payload, _scheduled_for_goal, _actionable_finding, _SURFACE_FIELDS, detect_goal_coverage_contradictions, discover_goal_contradictions, CoverageEdge, ValidationReceiptCoverage, AcceptanceCoverage, FindingAssignment
- Merge key: refactor/g10/g10-s3
- Candidate kind: seed
- Todo vector key: ref-207-buildgoal-to-taskcodeastacceptanceandvalidationc
- Acceptance: Every acceptance criterion maps to tasks, predicted and changed files, AST symbols or interfaces, validation commands, and resulting receipts with provenance.; The graph reports uncovered, weakly inferred, stale, contradicted, and verified surfaces separately.; Dynamic codebase findings attach to the most relevant registered goals while preserving a clearly labeled unmapped bucket.; Coverage calculations are deterministic and explain the evidence behind each edge.

- [x] Task checkbox-208: REF-208 Enforce a completion gate using validation, coverage, health, freshness, and exhaustion proof

## REF-208 Enforce a completion gate using validation, coverage, health, freshness, and exhaustion proof

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-204, REF-207
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_coverage.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/audit_scanner.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_task_janitor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_task_janitor.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_task_janitor.py -q
- Bundle: refactor/g10/g10-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S3
- Missing evidence: Goal reconciliation must require proof of the stated objective rather than infer success from a drained or deduplicated task list.
- AST symbols: GOAL_COMPLETION_SCHEMA_VERSION, GOAL_COMPLETION_MIGRATION_SCHEMA_VERSION, DEFAULT_EVIDENCE_FRESHNESS_SECONDS, DEFAULT_CLOCK_SKEW_SECONDS, GoalState, _GOAL_STATE_ALIASES, LEGACY_COMPLETED_GOAL_STATES, is_legacy_completed_goal_state, normalize_goal_state, legal_goal_transitions, is_terminal_goal_state, is_schedulable_goal_state, IllegalGoalTransitionError, IllegalGoalTransition, _utc_datetime, _now, _criterion_key, _json_value, _canonical_json, _stable_fingerprint, _string_tuple, _mapping_tuple, _ASSURANCE_ALIASES, _assurance_level, _proof_verdict, _proof_freshness, CONTRADICTION_KINDS, ContradictionEvidence, _PROOF_INVALIDATION_EVENT_FIELDS, _proof_invalidation_mapping
- Merge key: refactor/g10/g10-s3
- Candidate kind: seed
- Todo vector key: ref-208-enforceacompletiongateusingvalidationcoveragehea
- Acceptance: Verified completion requires all mandatory acceptance criteria covered, required validations successful, evidence fresh, analyzer healthy, and configured exhaustion quorum satisfied.; Partial, skipped, failed, timed-out, duplicate-only, or unsupported analysis cannot satisfy the gate.; The gate emits machine-readable pass and fail reasons plus the exact evidence set it evaluated.; Parent goals aggregate child proof without hiding an inconclusive or reopened descendant.

- [x] Task checkbox-209: REF-209 Detect contradictory evidence and automatically reopen affected goals

## REF-209 Detect contradictory evidence and automatically reopen affected goals

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-208
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_coverage.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_task_janitor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_task_janitor.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_task_janitor.py -q
- Bundle: refactor/g10/g10-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S3
- Missing evidence: A completed goal currently remains completed even when a later codebase scan creates directly relevant work or validation regresses.
- AST symbols: GOAL_COMPLETION_SCHEMA_VERSION, GOAL_COMPLETION_MIGRATION_SCHEMA_VERSION, DEFAULT_EVIDENCE_FRESHNESS_SECONDS, DEFAULT_CLOCK_SKEW_SECONDS, GoalState, _GOAL_STATE_ALIASES, LEGACY_COMPLETED_GOAL_STATES, is_legacy_completed_goal_state, normalize_goal_state, legal_goal_transitions, is_terminal_goal_state, is_schedulable_goal_state, IllegalGoalTransitionError, IllegalGoalTransition, _utc_datetime, _now, _criterion_key, _json_value, _canonical_json, _stable_fingerprint, _string_tuple, _mapping_tuple, _ASSURANCE_ALIASES, _assurance_level, _proof_verdict, _proof_freshness, CONTRADICTION_KINDS, ContradictionEvidence, _PROOF_INVALIDATION_EVENT_FIELDS, _proof_invalidation_mapping
- Merge key: refactor/g10/g10-s3
- Candidate kind: seed
- Todo vector key: ref-209-detectcontradictoryevidenceandautomaticallyreope
- Acceptance: Novel mapped findings, failed required validations, changed evidence surfaces, and invalidated audit receipts reopen verified or provisional goals deterministically.; Reopening records the contradiction, impacted criteria, invalidated evidence, source receipt, and newly scheduled work.; Unrelated findings do not churn completed goals, and repeated identical contradictions are idempotent.; Parent and dependent goal states are recalculated without erasing historical completion receipts.
