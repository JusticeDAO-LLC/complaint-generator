# Objective Bundle: refactor/g11/g11-s8

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-271: REF-271 Add adversarial tests for every proof trust boundary

## REF-271 Add adversarial tests for every proof trust boundary

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-263, REF-266, REF-268, REF-269
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_adversarial.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_cache.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_adversarial.py -q
- Bundle: refactor/g11/g11-s8
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S8
- Missing evidence: Formal-looking artifacts are a new attack surface and must be unable to forge assurance, poison caches, leak witnesses, or bypass merge policy.
- AST symbols: SECRET, TREE, OBLIGATION, PREMISES, KERNEL, TOOLCHAIN, _budget, _key, _kernel_evidence, _solver_evidence, _receipt, _assert_public_reason, test_forged_verified_status_and_provider_claims_fail_closed, test_solver_only_success_never_becomes_a_proof_or_cache_hit, test_stale_tree_changed_premises_and_toolchain_drift_cannot_reuse_receipts, test_empty_and_unidentifiable_premise_bindings_fail_closed, test_cache_poisoning_and_malformed_receipts_are_quarantined, test_incomplete_substituted_and_malicious_prover_output_is_rejected, test_simulated_zkp_and_stale_verification_keys_cannot_promote_assurance, test_hidden_witnesses_never_enter_contracts_flights_or_storage, test_forged_policy_outcome_cannot_bypass_enforcement_merge_gate, test_single_flight_timeout_remains_fail_closed_and_secret_free, test_single_flight_crash_and_cancellation_are_shared_but_never_promoted, test_restart_fences_abandoned_work_and_coordination_never_promotes_verdict, test_duplicate_single_flight_executes_once_without_creating_assurance, test_unknown_rejection_detail_is_never_reflected, forged, attempt, receipt, payload
- Merge key: refactor/g11/g11-s8
- Candidate kind: seed
- Todo vector key: ref-271-addadversarialtestsforeveryprooftrustboundary
- Acceptance: Tests cover forged verified status, solver-only success, stale trees, changed premises, cache poisoning, malformed receipts, and toolchain drift.; Tests reject sorry or admit, theorem substitution, malicious prover output, simulated ZKP promotion, stale verification keys, and hidden-witness leakage.; Timeout, cancellation, crash, restart, and duplicate single-flight cases preserve fail-closed verdicts.; Every rejected artifact emits a bounded actionable reason without exposing secrets.

- [!] Task checkbox-272: REF-272 Exercise an end-to-end parallel proof-aware implementation workflow

## REF-272 Exercise an end-to-end parallel proof-aware implementation workflow

- Status: blocked
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-260, REF-270, REF-271
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_workflow_e2e.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_workflow_e2e.py -q
- Bundle: refactor/g11/g11-s8
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S8
- Missing evidence: The complete task, AST, proof, validation, merge, evidence, and reopen lifecycle must work under concurrent lanes and restart.
- AST symbols: _proof_phase, _utc_now, ProofNodeState, ProofStepState, StepState, _STATUS_TO_STATE, _STATE_TO_STATUS, ProofSchedulerConfig, ProofStepPriority, ScheduledProofStep, ProofStepResult, ProofExecutionContext, ProofNodeSnapshot, ProofScheduleSnapshot, ProofScheduleResult, _Lease, _ProofStateStore, ProofScheduler, execute_proof_plan, run_proof_plan, __all__, normalized, PENDING, READY, RUNNING, SUCCEEDED, FAILED, UNSUPPORTED, BLOCKED, CANCELLED
- Merge key: refactor/g11/g11-s8
- Candidate kind: seed
- Todo vector key: ref-272-exerciseanend-to-endparallelproof-awareimplement
- Acceptance: Fixtures cover cache hit, proof success, counterexample, unsupported fallback, kernel rejection, provider outage, and stale evidence.; Independent obligations and implementation lanes run concurrently without duplicate leases, receipts, merges, or goal transitions.; Shared resource limits remain respected across solver, kernel, test, model, and artifact work.; Restart preserves proof-plan dependencies, single-flight ownership, receipt lineage, and truthful operator state.

- [!] Task checkbox-273: REF-273 Expose shadow, canary, enforcement, and override diagnostics

## REF-273 Expose shadow, canary, enforcement, and override diagnostics

- Status: blocked
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-268, REF-272
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_policy.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_rollout.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_rollout.py -q
- Bundle: refactor/g11/g11-s8
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S8
- Missing evidence: Operators need to know whether proof work is advisory or blocking and why a task, merge, or goal advanced.
- AST symbols: POLICY_VERSION, SCHEMA_VERSION, CHANGED_SCOPE_SCHEMA, PROOF_POLICY_RULE_SCHEMA, PROOF_REQUIREMENT_SCHEMA, POLICY_SELECTION_SCHEMA, FORMAL_VERIFICATION_POLICY_SCHEMA, PROOF_OUTCOME_SCHEMA, VALIDATION_OUTCOME_SCHEMA, OVERRIDE_RECEIPT_SCHEMA, ROLLOUT_TRANSITION_RECEIPT_SCHEMA, REQUIREMENT_GATE_RESULT_SCHEMA, POLICY_GATE_DECISION_SCHEMA, MERGE_PROOF_GATE_RECEIPT_SCHEMA, MAX_SCOPE_ITEMS, MAX_OVERRIDE_LIFETIME_SECONDS, DEFAULT_MAX_OVERRIDE_SECONDS, PolicyValidationError, RiskLevel, InvariantClass, RolloutMode, ProofResultStatus, _enum, _text, _strings, _mapping, _integer, _normalize_git_path, _normalize_path_pattern, _path_matches
- Merge key: refactor/g11/g11-s8
- Candidate kind: seed
- Todo vector key: ref-273-exposeshadowcanaryenforcementandoverridediagnost
- Acceptance: Status and query artifacts show rollout mode, protected scopes, capability health, active plans, assurance, failures, fallbacks, and overrides.; Canary expansion and rollback are configuration changes with durable policy identity.; Overrides are visible, expiring, scope-bounded, and never rewrite the underlying proof verdict.; A provider outage cannot silently switch an enforcement scope to shadow mode.

- [!] Task checkbox-274: REF-274 Benchmark context reduction, cache reuse, and CPU proof throughput

## REF-274 Benchmark context reduction, cache reuse, and CPU proof throughput

- Status: blocked
- Completion: manual
- Priority: P1
- Track: G11
- Depends on: REF-260, REF-272
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_benchmarks.py, ipfs_datasets_py/ipfs_accelerate_py/docs/architecture/AGENT_SUPERVISOR_FORMAL_VERIFICATION_PLAN.md
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_benchmarks.py -q
- Bundle: refactor/g11/g11-s8
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S8
- Missing evidence: Enforcement should expand only when proof evidence reduces model work without unacceptable host or implementation throughput regressions.
- AST symbols: _utc_iso, _parse_time, _record, _records, _text, _first, _integer, _number, _limit_integer, _boolean, _strings, _private_key, safe_public_value, validate_public_projection, normalize_proof_metric_identity, _dimension_key, _duration_ms, _assurance, _base_metrics, _dedupe_rows, _public_obligation, _public_attempt, _public_receipt, _public_dependency, _public_cache_outcome, _public_resource_sample, _extract_plan, _validate_snapshot_shape, ProofMetricsSnapshot, build_proof_metrics_snapshot
- Merge key: refactor/g11/g11-s8
- Candidate kind: seed
- Todo vector key: ref-274-benchmarkcontextreductioncachereuseandcpuproofth
- Acceptance: Benchmarks compare raw repository context with bounded proof capsules by bytes, tokens, retrieval precision, and accepted-task cost.; Cold and warm runs report translation, solver, kernel, cache, model, validation, and merge latency plus CPU and memory use.; Parallel runs detect nested oversubscription and quantify cancellation and single-flight savings.; Documented thresholds gate rollout expansion and identify unsupported or low-value obligation templates.
