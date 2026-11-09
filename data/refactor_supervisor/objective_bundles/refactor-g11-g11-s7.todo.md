# Objective Bundle: refactor/g11/g11-s7

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: bundle objective-generated tasks so parallel daemons can work one lane at a time.
Conflict policy: keep edits inside this bundle when possible; use the LLM merge resolver for semantic conflicts.

- [x] Task checkbox-267: REF-267 Map trusted proof receipts into goal completion evidence

## REF-267 Map trusted proof receipts into goal completion evidence

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-245, REF-255, REF-260
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_goal_completion.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_goal_completion.py -q
- Bundle: refactor/g11/g11-s7
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S7
- Missing evidence: A successful implementation or test receipt should not satisfy a proof-required acceptance criterion without fresh trusted proof evidence.
- AST symbols: GOAL_COMPLETION_SCHEMA_VERSION, GOAL_COMPLETION_MIGRATION_SCHEMA_VERSION, DEFAULT_EVIDENCE_FRESHNESS_SECONDS, DEFAULT_CLOCK_SKEW_SECONDS, GoalState, _GOAL_STATE_ALIASES, LEGACY_COMPLETED_GOAL_STATES, is_legacy_completed_goal_state, normalize_goal_state, legal_goal_transitions, is_terminal_goal_state, is_schedulable_goal_state, IllegalGoalTransitionError, IllegalGoalTransition, _utc_datetime, _now, _criterion_key, _json_value, _canonical_json, _stable_fingerprint, _string_tuple, _mapping_tuple, _ASSURANCE_ALIASES, _assurance_level, _proof_verdict, _proof_freshness, CONTRADICTION_KINDS, ContradictionEvidence, _PROOF_INVALIDATION_EVENT_FIELDS, _proof_invalidation_mapping
- Merge key: refactor/g11/g11-s7
- Candidate kind: seed
- Todo vector key: ref-267-maptrustedproofreceiptsintogoalcompletionevidenc
- Acceptance: CompletionEvidence can reference obligation, proof receipt, assurance, tree, freshness, and provenance identities.; Required assurance is evaluated independently from validation success and task status.; Parent goals aggregate child proof requirements without hiding unsupported, inconclusive, stale, or contradicted descendants.; Legacy evidence remains readable but cannot be optimistically upgraded.

- [x] Task checkbox-268: REF-268 Apply risk-selected proof gates before merge promotion

## REF-268 Apply risk-selected proof gates before merge promotion

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-247, REF-259, REF-267
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_policy.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_merge_gate.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_merge_gate.py -q
- Bundle: refactor/g11/g11-s7
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S7
- Missing evidence: Protected supervisor invariants need a durable promotion decision after implementation and before the merge train advances the candidate.
- AST symbols: MergeCallback, _request_value, conflict_fingerprint, MergeTrain, __all__, value, metadata, payload, __init__, _consumer_lease, run_once, process_next, consume_once, drain, run, _recover_abandoned_claims, status, _process_claimed, _metadata_strings, _risk_for_priority, _modeled_invariant_hints, _changed_scopes, _proof_gate_cache_key, _proof_policy_for_request, _default_proof_plan, _atomic_json, _pin_proof_selection, _gate_receipt_type, _read_cached_gate_receipt, _persist_gate_receipt
- Merge key: refactor/g11/g11-s7
- Candidate kind: seed
- Todo vector key: ref-268-applyrisk-selectedproofgatesbeforemergepromotion
- Acceptance: Changed scopes select proof requirements, fallback checks, and rollout mode deterministically.; Shadow records outcomes, canary blocks configured paths, and enforcement fails closed for missing required assurance.; The merge receipt identifies the exact proof plan, receipts, validations, policy, tree, and any operator override.; Retries reuse valid cache evidence and do not weaken policy after a timeout or provider failure.

- [x] Task checkbox-269: REF-269 Invalidate proof evidence and reopen goals after semantic change

## REF-269 Invalidate proof evidence and reopen goals after semantic change

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-251, REF-267
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_task_janitor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_scope_index.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_invalidation.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_invalidation.py -q
- Bundle: refactor/g11/g11-s7
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S7
- Missing evidence: A changed symbol, premise, template, toolchain, policy, or contradiction must revoke affected proof coverage and schedule bounded replacement work.
- AST symbols: GOAL_COMPLETION_SCHEMA_VERSION, GOAL_COMPLETION_MIGRATION_SCHEMA_VERSION, DEFAULT_EVIDENCE_FRESHNESS_SECONDS, DEFAULT_CLOCK_SKEW_SECONDS, GoalState, _GOAL_STATE_ALIASES, LEGACY_COMPLETED_GOAL_STATES, is_legacy_completed_goal_state, normalize_goal_state, legal_goal_transitions, is_terminal_goal_state, is_schedulable_goal_state, IllegalGoalTransitionError, IllegalGoalTransition, _utc_datetime, _now, _criterion_key, _json_value, _canonical_json, _stable_fingerprint, _string_tuple, _mapping_tuple, _ASSURANCE_ALIASES, _assurance_level, _proof_verdict, _proof_freshness, CONTRADICTION_KINDS, ContradictionEvidence, _PROOF_INVALIDATION_EVENT_FIELDS, _proof_invalidation_mapping
- Merge key: refactor/g11/g11-s7
- Candidate kind: seed
- Todo vector key: ref-269-invalidateproofevidenceandreopengoalsaftersemant
- Acceptance: Transitive invalidation records the changed input, affected obligations, receipts, criteria, goals, and source tree.; Affected provisional or verified goals reopen deterministically while unrelated goals remain stable.; Repeated identical invalidations are idempotent and historical receipts remain auditable.; Replacement tasks retain dependency and conflict edges to the invalidated scope.

- [x] Task checkbox-270: REF-270 Make planning proof-aware without expanding model context

## REF-270 Make planning proof-aware without expanding model context

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-252, REF-257, REF-267
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_context.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_aware_planning.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_aware_planning.py -q
- Bundle: refactor/g11/g11-s7
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S7
- Missing evidence: The planner should prioritize proof-critical work, reuse trusted evidence, and generate bounded repair tasks from unsupported or contradicted obligations.
- AST symbols: DEFAULT_EMBEDDING_DIMENSIONS, DEFAULT_EMBEDDING_MIN_SCORE, DEFAULT_BUNDLE_CLUSTER_MIN_SCORE, DEFAULT_OBJECTIVE_TASK_SUMMARY_PREFIX, parse_python_ast_quietly, DEFAULT_DISCOVERY_OUTPUT_PATH, DEFAULT_SURPLUS_FINDINGS_PER_GOAL, DEFAULT_SURPLUS_MIN_TERMS_PER_TODO, DEFAULT_SCAN_OVERSAMPLE_MULTIPLIER, DEFAULT_TASK_PREFIX, OBJECTIVE_SCAN_ANALYZER_VERSION, DEFAULT_AST_DATASET_MAX_CHARS, AST_DATASET_RECORD_SCHEMA_VERSION, LAUNCH_PLAYWRIGHT_VALIDATION_COMMAND, LAUNCH_PLAYWRIGHT_VALIDATION_MARKERS, LAUNCH_PLAYWRIGHT_VALIDATION_GATE_EVIDENCE, SCAN_SUFFIXES, SKIP_DIRS, _DERIVED_TASK_PLANNING_FIELDS, _bounded_task_planning_metadata, ObjectiveGoal, ObjectiveFinding, ObjectiveTaskRecord, ObjectiveHeapRecord, DEPENDENCY_EDGE_KINDS, SUCCESSFUL_MERGE_RECEIPT_STATUSES, CoverageSurfaceKind, CoverageStatus, _coverage_json_value, _coverage_enum_value
- Merge key: refactor/g11/g11-s7
- Candidate kind: seed
- Todo vector key: ref-270-makeplanningproof-awarewithoutexpandingmodelcont
- Acceptance: Plan candidates declare obligation impact, required assurance, proof cost, cache likelihood, dependencies, and expected evidence delta.; Priority accounts for proof critical path, downstream unlock value, risk, freshness, and available resource classes.; The router receives only a bounded proof context capsule and rejected alternatives retain rationale.; Unsupported or failed obligations generate finite template, test, premise, or manual-review work with semantic deduplication.
