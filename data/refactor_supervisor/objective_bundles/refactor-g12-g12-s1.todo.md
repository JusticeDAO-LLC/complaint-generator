# Objective Bundle: refactor/g12/g12-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-275: REF-275 Define a canonical formal work-plan contract and logic vocabulary

## REF-275 Define a canonical formal work-plan contract and logic vocabulary

- Status: completed
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-245
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/docs/architecture/AGENT_SUPERVISOR_FORMAL_PLANNING_PROVER_MATRIX_PLAN.md, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_planning_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_logic_vocabulary.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_planning_contracts.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_planning_contracts.py -q
- Bundle: refactor/g12/g12-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S1
- Missing evidence: The supervisor needs a deterministic semantic model of intended work before a language model is asked to implement it.
- AST symbols: FORMAL_PLANNING_CONTRACT_VERSION, PLANNING_CONTRACT_VERSION, SCHEMA_VERSION, FORMAL_WORK_PLAN_SCHEMA, ACTOR_SCHEMA, GOAL_SCHEMA, SUBGOAL_SCHEMA, PLAN_TASK_SCHEMA, PLAN_EVENT_SCHEMA, FLUENT_SCHEMA, PRECONDITION_SCHEMA, EFFECT_SCHEMA, NORM_SCHEMA, TEMPORAL_CONSTRAINT_SCHEMA, EVIDENCE_REQUIREMENT_SCHEMA, PLAN_ASSURANCE_SCHEMA, FormalPlanningValidationError, ActorKind, EventKind, FluentValueType, EffectOperation, NormKind, TemporalConstraintKind, EvidenceRequirementKind, PlanConsistencyLevel, PlanConformanceLevel, T, E, _strings, _optional_int
- Merge key: refactor/g12/g12-s1
- Candidate kind: seed
- Todo vector key: ref-275-defineacanonicalformalwork-plancontractandlogicv
- Acceptance: FormalWorkPlan records actors, goals, subgoals, tasks, events, fluents, preconditions, effects, norms, temporal constraints, evidence requirements, and deterministic identities.; A reviewed DCEC vocabulary models belief, knowledge, intention, obligation, permission, prohibition, delegation, and execution events without deriving formulas from free-form model text.; A reviewed TDFOL vocabulary models dependency ordering, deadlines, liveness, safety, and goal satisfaction over finite supervisor traces.; A versioned frame-logic projection derives bounded worlds, accessibility relations, and relevant evidence-graph neighborhoods without treating graph reachability as code proof.; Plan consistency, plan conformance, and generated-code assurance are separate levels; no plan proof is promoted into a code proof.

- [x] Task checkbox-276: REF-276 Compile objective, taskboard, AST, and policy records into formal plans

## REF-276 Compile objective, taskboard, AST, and policy records into formal plans

- Status: completed
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-250, REF-275
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_plan_compiler.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_plan_compiler.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_plan_compiler.py -q
- Bundle: refactor/g12/g12-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S1
- Missing evidence: Formal plans must be derived from canonical supervisor and AST records rather than reconstructed by an LLM inside its context window.
- AST symbols: CompilationStatus, CompilationIssueSeverity, CompilationIssueCode, CompilationIssue, PlanGraphProjection, PlanCompilationResult, _canonical_safe, _text, _values, _strings, _resource_values, _record, _records, _source_id, _unique_records, _graph_node, _graph_edge, _normalize_bundle, _failure_result, FormalPlanCompiler, _decode_duckdb_value, _optional_nonnegative, _assurance, _evidence_kind, _policy_defaults, _descriptive_metadata, _topological_times, compile_formal_plan, compile_formal_plan_json, compile_formal_plan_duckdb
- Merge key: refactor/g12/g12-s1
- Candidate kind: seed
- Todo vector key: ref-276-compileobjectivetaskboardastandpolicyrecordsinto
- Acceptance: The compiler maps goals, task dependencies, leases, resource needs, changed AST scopes, acceptance criteria, and proof policy into canonical plan predicates and events.; Compilation preserves task, goal, tree, symbol, policy, and evidence CIDs and records every abstraction or unsupported field.; Equivalent JSON and DuckDB inputs produce the same plan identity and graph projection.; Syntax failures, cycles, ambiguous effects, and missing semantics produce explicit unsupported or invalid plan results.

- [x] Task checkbox-277: REF-277 Check formal plans for temporal, deontic, and dependency consistency

## REF-277 Check formal plans for temporal, deontic, and dependency consistency

- Status: completed
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-247, REF-276
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_plan_validator.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_plan_validator.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_plan_validator.py -q
- Bundle: refactor/g12/g12-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S1
- Missing evidence: The supervisor should reject contradictory, unauthorized, impossible, or non-terminating plans before spending model tokens on implementation.
- AST symbols: PlanValidationStatus, ValidationStatus, PlanValidationVerdict, PlanValidationOutcome, ValidationOutcome, PlanCheckKind, FindingDisposition, PlanFindingCode, ValidationBounds, FormalPlanValidationBounds, AppliedValidationBounds, PlanValidationAssumption, PlanAssumption, _assumption, PlanValidationFinding, ValidationFinding, CountermodelState, PlanCountermodel, PlanCheckEvidence, PlanValidationResult, FormalPlanValidationResult, _Cancelled, _TimedOut, _SearchExhausted, _TraceModel, _BudgetGuard, FormalPlanValidator, PlanValidator, BoundedFormalPlanValidator, PlanValidationConfig
- Merge key: refactor/g12/g12-s1
- Candidate kind: seed
- Todo vector key: ref-277-checkformalplansfortemporaldeonticanddependencyc
- Acceptance: Bounded DCEC and TDFOL checks cover dependency readiness, actor authority, unique leases, fencing, required evidence, legal transitions, eventual terminal outcomes, and forbidden merge states.; Contradictions, countermodels, unsupported operators, timeout, and incomplete search remain distinct outcomes.; Native DCEC or TDFOL success is plan-check evidence only unless the exact obligation is reconstructed by an accepted kernel or model checker.; Validation is deterministic, resource bounded, cancellable, and records all assumptions and finite bounds.

- [x] Task checkbox-278: REF-278 Give Codex and Leanstral proof-carrying formal plan capsules

## REF-278 Give Codex and Leanstral proof-carrying formal plan capsules

- Status: completed
- Completion: manual
- Priority: P0
- Track: G12
- Depends on: REF-252, REF-277
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_plan_context.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_plan_context.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_plan_context.py -q
- Bundle: refactor/g12/g12-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G12.S1
- Missing evidence: Language models should receive the verified slice of intended work, not rediscover task semantics and repository-wide dependencies in every prompt.
- AST symbols: FormalPlanContextError, FormalPlanContextBudgetError, FormalPlanResponseError, FormalPlanContextTarget, ImplementationOutcomeStatus, _text, _positive, _strings, _ordered_strings, _canonical_mapping, _canonical_records, _truncate_utf8, _path, _public_value, _public_mapping, FormalPlanContextLimits, FormalPlanContextQuery, FormalPlanSourceExcerpt, FormalPlanGraphSlice, FormalTaskTransition, FormalPlanContextUsage, FormalPlanResponseBinding, FormalPlanContextCapsule, _safe_graph_node, _safe_graph_edge, _graph_records, query_formal_plan_graph, _task_for, _transition_for, _formula_records
- Merge key: refactor/g12/g12-s1
- Candidate kind: seed
- Todo vector key: ref-278-givecodexandleanstralproof-carryingformalplancap
- Acceptance: Capsules contain the selected task transition, assumptions, required preconditions and effects, relevant AST symbols, trusted evidence, counterexamples, allowed paths, tests, and unresolved obligations.; Graph queries enforce row, hop, byte, token, and source-excerpt limits before model invocation.; Model responses bind the plan and task CIDs and cannot alter the theorem, acceptance policy, or authoritative evidence.; Measurements compare capsule size and implementation outcomes against the existing unbounded planning prompt.
