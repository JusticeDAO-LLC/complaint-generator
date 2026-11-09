# Objective Bundle: refactor/g11/g11-s4

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: bundle objective-generated tasks so parallel daemons can work one lane at a time.
Conflict policy: keep edits inside this bundle when possible; use the LLM merge resolver for semantic conflicts.

- [x] Task checkbox-257: REF-257 Execute proof-plan DAGs with bounded parallelism and cancellation

## REF-257 Execute proof-plan DAGs with bounded parallelism and cancellation

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-252, REF-253, REF-254, REF-255
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_scheduler.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_scheduler.py -q
- Bundle: refactor/g11/g11-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S4
- Missing evidence: Independent obligations should run concurrently, but proof dependencies and conclusive portfolio results must bound unnecessary work.
- AST symbols: _proof_phase, _utc_now, ProofNodeState, ProofStepState, StepState, _STATUS_TO_STATE, _STATE_TO_STATUS, ProofSchedulerConfig, ProofStepPriority, ScheduledProofStep, ProofStepResult, ProofExecutionContext, ProofNodeSnapshot, ProofScheduleSnapshot, ProofScheduleResult, _Lease, _ProofStateStore, ProofScheduler, execute_proof_plan, run_proof_plan, __all__, normalized, PENDING, READY, RUNNING, SUCCEEDED, FAILED, UNSUPPORTED, BLOCKED, CANCELLED
- Merge key: refactor/g11/g11-s4
- Candidate kind: seed
- Todo vector key: ref-257-executeproof-plandagswithboundedparallelismandca
- Acceptance: The scheduler executes ready proof-plan nodes in dependency order and exposes critical-path and downstream-unlock priority.; Independent translator, solver, kernel, validation, and artifact nodes can overlap within configured limits.; Conclusive results cancel redundant portfolio attempts and propagate blocked or unsupported dependencies explicitly.; Restarts recover from durable plan, lease, attempt, and receipt state without duplicate authoritative receipts.

- [x] Task checkbox-258: REF-258 Unify proof, validation, model, and artifact resource admission

## REF-258 Unify proof, validation, model, and artifact resource admission

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-244, REF-257
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/resource_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_resource_scheduler.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_resource_scheduler.py -q
- Bundle: refactor/g11/g11-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S4
- Missing evidence: Nested solver, kernel, test, and model pools can otherwise oversubscribe CPU and memory while each believes it is within its own limit.
- AST symbols: UNKNOWN_LIMIT, ProofResourceClass, PROOF_RESOURCE_CLASSES, LEGACY_RESOURCE_CLASSES, DEFAULT_RESOURCE_CLASSES, _RESOURCE_CLASS_ALIASES, normalize_resource_class, resource_pool, _integer, _boolean, _first, _strings, _mapping, HostResourceSnapshot, sample_host_resources, ProviderCapacity, normalize_provider_capacity, normalize_provider_capacities, LaneResourceRequirements, ChildResourceLimits, ResourceLeaseBudget, SupervisorResourceLeaseBudget, ResourcePolicy, AdmissionDecision, ResourceScheduleSnapshot, _ProviderReservation, ResourceAdmissionLease, ResourceScheduler, __all__, TRANSLATION
- Merge key: refactor/g11/g11-s4
- Candidate kind: seed
- Todo vector key: ref-258-unifyproofvalidationmodelandartifactresourceadmi
- Acceptance: Resource classes distinguish translation, solver, kernel, validation, model-draft, and artifact work.; One supervisor-level lease budget is propagated into child portfolio and kernel limits.; CPU, process, memory, disk, provider quota, context, token, and latency backpressure remain authoritative.; Model concurrency is accounted separately from CPU proof concurrency and idle capacity is reclaimable.

- [x] Task checkbox-259: REF-259 Integrate staged proof checks with the validation scheduler

## REF-259 Integrate staged proof checks with the validation scheduler

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-256, REF-257, REF-258
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_validation_scheduler.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_validation_scheduler.py -q
- Bundle: refactor/g11/g11-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S4
- Missing evidence: Proof checks and tests need one impact-selected, cached, fail-fast pipeline before merge.
- AST symbols: INLINE_CODE_COMMAND_RE, ValidationStage, ValidationVerdictKind, ValidationDecisionKind, ValidationRequirementKind, ValidationCommand, DeclaredValidation, ValidationSelectionItem, ValidationSelection, _CHEAP_PATTERNS, _TEST_RUNNER_RE, _ENV_ASSIGNMENT_RE, _GLOBAL_IMPACT_NAMES, _DEPENDENCY_SUFFIXES, _DECLARATION_PREFIXES, normalize_validation_command_text, split_validation_commands, _shell_tokens, _normalize_path, _looks_like_impact_path, infer_validation_impact_paths, classify_validation_command, parse_validation_declaration, build_declared_validations, build_focused_validation_commands, build_validation_commands, is_global_impact_change, _path_related, select_validation_commands, ValidationCommandSpec
- Merge key: refactor/g11/g11-s4
- Candidate kind: seed
- Todo vector key: ref-259-integratestagedproofcheckswiththevalidationsched
- Acceptance: Cheap deterministic checks precede translation, solver candidates, kernel reconstruction, focused tests, and broad tests.; Independent checks run in parallel under the shared resource budget.; Impact selection explains every included, omitted, escalated, and fallback check.; Validation reports retain separate deterministic, solver, kernel, test, and attestation verdicts.

- [x] Task checkbox-260: REF-260 Persist proof scheduler metrics and queryable receipts

## REF-260 Persist proof scheduler metrics and queryable receipts

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-250, REF-254, REF-257
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/artifact_store.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_metrics.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_metrics.py -q
- Bundle: refactor/g11/g11-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S4
- Missing evidence: Operators and planning policy need proof throughput, trust, cache, context, and resource measurements without loading raw event logs.
- AST symbols: _utc_iso, _parse_time, _record, _records, _text, _first, _integer, _number, _limit_integer, _boolean, _strings, _private_key, safe_public_value, validate_public_projection, normalize_proof_metric_identity, _dimension_key, _duration_ms, _assurance, _base_metrics, _dedupe_rows, _public_obligation, _public_attempt, _public_receipt, _public_dependency, _public_cache_outcome, _public_resource_sample, _extract_plan, _validate_snapshot_shape, ProofMetricsSnapshot, build_proof_metrics_snapshot
- Merge key: refactor/g11/g11-s4
- Candidate kind: seed
- Todo vector key: ref-260-persistproofschedulermetricsandqueryablereceipts
- Acceptance: JSON and DuckDB tables expose obligations, attempts, receipts, dependencies, cache outcomes, resource samples, and assurance counts.; Metrics include queue, solver, kernel, model, validation, merge, cancellation, and cache latency.; Every metric is keyed by canonical goal, subgoal, task, tree, provider, template, and resource class.; Queryable aggregates do not include hidden witnesses or unbounded proof transcripts.
