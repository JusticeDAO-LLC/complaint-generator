# Objective Bundle: refactor/g9/g9-s2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-39: REF-039 Materialize a task dependency DAG and schedule its critical path

## REF-039 Materialize a task dependency DAG and schedule its critical path

- Status: completed
- Completion: manual
- Priority: P0
- Track: G9
- Depends on: REF-037
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q
- Bundle: refactor/g9/g9-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S2
- Missing evidence: Goal parents are currently sorting hints while generated Profile G tasks carry no dependency task CIDs.
- AST symbols: DEFAULT_EMBEDDING_DIMENSIONS, DEFAULT_EMBEDDING_MIN_SCORE, DEFAULT_BUNDLE_CLUSTER_MIN_SCORE, DEFAULT_OBJECTIVE_TASK_SUMMARY_PREFIX, parse_python_ast_quietly, DEFAULT_DISCOVERY_OUTPUT_PATH, DEFAULT_SURPLUS_FINDINGS_PER_GOAL, DEFAULT_SURPLUS_MIN_TERMS_PER_TODO, DEFAULT_SCAN_OVERSAMPLE_MULTIPLIER, DEFAULT_TASK_PREFIX, OBJECTIVE_SCAN_ANALYZER_VERSION, DEFAULT_AST_DATASET_MAX_CHARS, AST_DATASET_RECORD_SCHEMA_VERSION, LAUNCH_PLAYWRIGHT_VALIDATION_COMMAND, LAUNCH_PLAYWRIGHT_VALIDATION_MARKERS, LAUNCH_PLAYWRIGHT_VALIDATION_GATE_EVIDENCE, SCAN_SUFFIXES, SKIP_DIRS, _DERIVED_TASK_PLANNING_FIELDS, _bounded_task_planning_metadata, ObjectiveGoal, ObjectiveFinding, ObjectiveTaskRecord, ObjectiveHeapRecord, DEPENDENCY_EDGE_KINDS, SUCCESSFUL_MERGE_RECEIPT_STATUSES, CoverageSurfaceKind, CoverageStatus, _coverage_json_value, _coverage_enum_value
- Merge key: refactor/g9/g9-s2
- Candidate kind: seed
- Todo vector key: ref-039-materializeataskdependencydagandscheduleitscriti
- Acceptance: Goal, import, interface, output-input, migration, and validation prerequisites become explicit DAG edges with provenance.; Only tasks whose prerequisite merge receipts succeeded are claimable.; Priority includes critical-path length, slack, downstream unlock value, age, and configured objective priority.; Cycles and missing dependencies produce bounded repair evidence rather than deadlock.

- [x] Task checkbox-40: REF-040 Build an AST and changed-path conflict graph for lane coloring

## REF-040 Build an AST and changed-path conflict graph for lane coloring

- Status: completed
- Completion: manual
- Priority: P0
- Track: G9
- Depends on: REF-039
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_vector_index.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q
- Bundle: refactor/g9/g9-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S2
- Missing evidence: The current conflict domain uses one path root and lightweight semantic similarity, which misses multi-file and symbol overlap.
- AST symbols: CONFLICT_RECEIPT_STATUSES, AST_BLOB_RECORD_SCHEMA_VERSION, _DERIVED_CONFLICT_METADATA_FIELDS, _source_sha256, _ast_expression_name, _ast_render, _ast_signature, ASTBlobRecord, build_python_ast_blob_record, coerce_ast_blob_record, index_ast_blob_records, _payload, _sources, _items, _field_items, normalize_repo_path, _normalized_paths, _normalized_terms, _gitmodule_paths, _under, _looks_generated, ConflictSurface, _python_symbols, build_conflict_surface, _merge_duplicate_surfaces, _pair_key, ConflictWeightHistory, ConflictEdge, LaneAssignment, LaneDecision
- Merge key: refactor/g9/g9-s2
- Candidate kind: seed
- Todo vector key: ref-040-buildanastandchanged-pathconflictgraphforlanecol
- Acceptance: Conflict surfaces include all predicted files, AST symbols, interfaces, submodules, and generated artifacts.; Lane planning colors the conflict graph so overlapping tasks do not run concurrently unless explicitly allowed.; Actual branch diffs and conflict receipts update future conflict weights.; Planner output explains every co-location or separation decision.

- [x] Task checkbox-41: REF-041 Use llm_router to generate and evaluate structured plan branches

## REF-041 Use llm_router to generate and evaluate structured plan branches

- Status: completed
- Completion: manual
- Priority: P1
- Track: G9
- Depends on: REF-039
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q
- Bundle: refactor/g9/g9-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S2
- Missing evidence: Profile G currently records a single constant-scored plan branch and the LLM proposal router is not part of scheduler decisions.
- AST symbols: PromptBuilder, BootstrapCallback, DEFAULT_OPEN_TASK_STATUSES, DEFAULT_TASK_PROPOSAL_TEST_OUTPUT, TaskProposalRouterError, TaskProposalRouterConfig, TaskProposalRouterCliConfig, TaskProposalRoutePaths, TaskProposalRouteSpec, _repo_path, build_task_proposal_route_paths, _task_values, _task_value, task_metadata_lines, build_task_proposal_prompt, standard_task_proposal_requested_outputs, build_task_proposal_prompt_builder, build_task_proposal_router_cli_config, run_configured_task_proposal_router_cli, ConfiguredTaskProposalRouterRunner, build_configured_task_proposal_router_runner, build_repo_task_proposal_router_runner, build_repo_task_proposal_route_runner, build_repo_task_proposal_route_runner_from_spec, select_proposal_task, _artifact_relative_path, run_task_proposal_router, build_task_proposal_router_parser, run_task_proposal_router_cli, StructuredRouter
- Merge key: refactor/g9/g9-s2
- Candidate kind: seed
- Todo vector key: ref-041-usellm-routertogenerateandevaluatestructuredplan
- Acceptance: Each eligible subgoal can produce multiple schema-validated plan branches through llm_router.; Candidates declare predicted files and symbols, dependencies, validation proof, cost, risk, and expected objective delta.; A deterministic evaluator selects a branch and retains rejected alternatives plus rationale.; Router failure falls back to deterministic planning without blocking ready work.

- [x] Task checkbox-63: REF-063 Recover structured plan branch implementation in the nested supervisor

## REF-063 Recover structured plan branch implementation in the nested supervisor

- Status: completed
- Completion: manual
- Priority: P0
- Track: G9
- Depends on: REF-041
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q
- Bundle: refactor/g9/g9-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S2
- Missing evidence: REF-041 validated nested changes in a lane that did not forward managed submodule paths, so its root merge recorded only taskboard documentation.
- AST symbols: PromptBuilder, BootstrapCallback, DEFAULT_OPEN_TASK_STATUSES, DEFAULT_TASK_PROPOSAL_TEST_OUTPUT, TaskProposalRouterError, TaskProposalRouterConfig, TaskProposalRouterCliConfig, TaskProposalRoutePaths, TaskProposalRouteSpec, _repo_path, build_task_proposal_route_paths, _task_values, _task_value, task_metadata_lines, build_task_proposal_prompt, standard_task_proposal_requested_outputs, build_task_proposal_prompt_builder, build_task_proposal_router_cli_config, run_configured_task_proposal_router_cli, ConfiguredTaskProposalRouterRunner, build_configured_task_proposal_router_runner, build_repo_task_proposal_router_runner, build_repo_task_proposal_route_runner, build_repo_task_proposal_route_runner_from_spec, select_proposal_task, _artifact_relative_path, run_task_proposal_router, build_task_proposal_router_parser, run_task_proposal_router_cli, StructuredRouter
- Merge key: refactor/g9/g9-s2
- Candidate kind: seed
- Todo vector key: ref-063-recoverstructuredplanbranchimplementationinthene
- Acceptance: The structured plan router, evaluator, objective-daemon integration, and focused tests are tracked in the nested ipfs_accelerate_py repository.; Selected and rejected branches remain visible to the scheduler with deterministic fallback when llm_router fails.; The implementation receipt records nested commits and the parent gitlink chain instead of completing from documentation alone.; A prior lane state cannot settle the recovery generation unless its recorded task identities include REF-063.
