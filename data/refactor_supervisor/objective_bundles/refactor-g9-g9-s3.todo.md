# Objective Bundle: refactor/g9/g9-s3

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-42: REF-042 Schedule lanes from live resources and llm_router provider capacity

## REF-042 Schedule lanes from live resources and llm_router provider capacity

- Status: completed
- Completion: manual
- Priority: P1
- Track: G9
- Depends on: REF-037, REF-041
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/resource_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py -q
- Bundle: refactor/g9/g9-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S3
- Missing evidence: Resource class, capability fit, and lane capacity are currently static even when workers are idle or providers are rate-limited.
- AST symbols: UNKNOWN_LIMIT, ProofResourceClass, PROOF_RESOURCE_CLASSES, LEGACY_RESOURCE_CLASSES, DEFAULT_RESOURCE_CLASSES, _RESOURCE_CLASS_ALIASES, normalize_resource_class, resource_pool, _integer, _boolean, _first, _strings, _mapping, HostResourceSnapshot, sample_host_resources, ProviderCapacity, normalize_provider_capacity, normalize_provider_capacities, LaneResourceRequirements, ChildResourceLimits, ResourceLeaseBudget, SupervisorResourceLeaseBudget, ResourcePolicy, AdmissionDecision, ResourceScheduleSnapshot, _ProviderReservation, ResourceAdmissionLease, ResourceScheduler, __all__, TRANSLATION
- Merge key: refactor/g9/g9-s3
- Candidate kind: seed
- Todo vector key: ref-042-schedulelanesfromliveresourcesandllm-routerprovi
- Acceptance: Heartbeats report measured CPU, memory, disk, active phase, and available worker capacity.; Scheduler honors llm_router health, quota, latency, context, and token-budget constraints.; Concurrency scales within configured limits and applies backpressure before provider or host exhaustion.; Idle lanes advertise zero occupied capacity and can be reassigned.

- [x] Task checkbox-43: REF-043 Add impact-selected cached and parallel validation stages

## REF-043 Add impact-selected cached and parallel validation stages

- Status: completed
- Completion: manual
- Priority: P1
- Track: G9
- Depends on: REF-038
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py -q
- Bundle: refactor/g9/g9-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S3
- Missing evidence: Validation commands currently run serially without changed-file impact selection or reusable baseline results.
- AST symbols: INLINE_CODE_COMMAND_RE, ValidationStage, ValidationVerdictKind, ValidationDecisionKind, ValidationRequirementKind, ValidationCommand, DeclaredValidation, ValidationSelectionItem, ValidationSelection, _CHEAP_PATTERNS, _TEST_RUNNER_RE, _ENV_ASSIGNMENT_RE, _GLOBAL_IMPACT_NAMES, _DEPENDENCY_SUFFIXES, _DECLARATION_PREFIXES, normalize_validation_command_text, split_validation_commands, _shell_tokens, _normalize_path, _looks_like_impact_path, infer_validation_impact_paths, classify_validation_command, parse_validation_declaration, build_declared_validations, build_focused_validation_commands, build_validation_commands, is_global_impact_change, _path_related, select_validation_commands, ValidationCommandSpec
- Merge key: refactor/g9/g9-s3
- Candidate kind: seed
- Todo vector key: ref-043-addimpact-selectedcachedandparallelvalidationsta
- Acceptance: Cheap deterministic checks run before expensive tests and fail fast.; Independent validations run in parallel under a bounded resource budget.; Cache keys include target commit, command, relevant environment, and dependency state.; Impact selection is conservative, explainable, and escalates to broader validation before merge completion.
