# Codebase Bundle: codebase/runtime/scripts-refactor_agent_supervisor

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-227 Review swallowed exception path in scripts/refactor_agent_supervisor.py:3241

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, scripts/refactor_agent_supervisor.py
- Validation: python3 -m py_compile scripts/refactor_agent_supervisor.py
- Bundle: codebase/runtime/scripts-refactor_agent_supervisor
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-scripts-refactor_agent_supervisor.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/scripts-refactor_agent_supervisor
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: scripts/refactor_agent_supervisor.py
- AST symbols: __future__, __future__.annotations, _active_todo_task_ids, _append_missing_explicit_seed_tasks, _atomic_write_json, _canonical_projection_status, _collect_counts, _compact_string_list, _durable_canonical_task_statuses, _durable_task_statuses, _ensure_accelerate_import_path, _ensure_text, _goal_evidence, _heartbeat_age_seconds, _implementation_activity_snapshot, _iter_py_files, _json_goal_tree, _load_json_object, _merge_goal_tree_extensions, _paths_from_locations, _payload_strings, _pid_alive, _priority_sort_key, _project_bundle_index_statuses, _project_goal_tree_statuses, _project_task_statuses, _prune_seed_bundle_shard, _queue_counts, _queue_payload_contract, _queued_task_summaries, _read_ipfs_p0_cross_links, _read_text, _release_watchdog_checkout_lock, _render_objective_heap, _render_seed_todo, _resolved_seed_task_ids, _safe_bundle_key, _scan_summary, _seed_status_summary, _status_artifacts, _status_counts, _status_last_error, _status_scan_summary, _statuses_for_canonical_tasks, _stop, _task, _task_ast_symbols, _task_block, _task_checkbox_index, _task_ids_from_queue_payload, _task_queue_class, _taskboard_snapshot, _taskboard_status_by_id, _todo_counts, _todo_task_header_count, _try_acquire_watchdog_checkout_lock, _upstream_artifact_store, _upstream_backlog_runner, _upstream_bundle_completion_receipt_loader, _upstream_bundle_payload_builder, _upstream_bundle_runner, _upstream_objective_runner, _upstream_portal_task_parser, _upstream_task_board_helpers, _validate_ipfs_p0_cross_link_goals, _validate_task_payload_fields, _write_status, _write_taskboard_doc, active bundle keys, active todo task ids, active_bundle_keys, add parallel args, add_parallel_args, append missing explicit seed tasks, argparse, ast, atomic write json, build goals, build parser, build_goals
- AST symbol scope: file
- Goal id: codebase/runtime/scripts-refactor_agent_supervisor
- Missing evidence: Review swallowed exception path in scripts/refactor_agent_supervisor.py:3241
- Merge key: codebase/runtime/scripts-refactor_agent_supervisor
- Merge family: scripts/refactor_agent_supervisor.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 968d225514093e82
- Acceptance: Codebase scan filed this finding from scripts/refactor_agent_supervisor.py:3241. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-227-codebase-scan-968d22551409.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-228 Review swallowed exception path in scripts/refactor_agent_supervisor.py:4008

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, scripts/refactor_agent_supervisor.py
- Validation: python3 -m py_compile scripts/refactor_agent_supervisor.py
- Bundle: codebase/runtime/scripts-refactor_agent_supervisor
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-scripts-refactor_agent_supervisor.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/scripts-refactor_agent_supervisor
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: scripts/refactor_agent_supervisor.py
- AST symbols: __future__, __future__.annotations, _active_todo_task_ids, _append_missing_explicit_seed_tasks, _atomic_write_json, _canonical_projection_status, _collect_counts, _compact_string_list, _durable_canonical_task_statuses, _durable_task_statuses, _ensure_accelerate_import_path, _ensure_text, _goal_evidence, _heartbeat_age_seconds, _implementation_activity_snapshot, _iter_py_files, _json_goal_tree, _load_json_object, _merge_goal_tree_extensions, _paths_from_locations, _payload_strings, _pid_alive, _priority_sort_key, _project_bundle_index_statuses, _project_goal_tree_statuses, _project_task_statuses, _prune_seed_bundle_shard, _queue_counts, _queue_payload_contract, _queued_task_summaries, _read_ipfs_p0_cross_links, _read_text, _release_watchdog_checkout_lock, _render_objective_heap, _render_seed_todo, _resolved_seed_task_ids, _safe_bundle_key, _scan_summary, _seed_status_summary, _status_artifacts, _status_counts, _status_last_error, _status_scan_summary, _statuses_for_canonical_tasks, _stop, _task, _task_ast_symbols, _task_block, _task_checkbox_index, _task_ids_from_queue_payload, _task_queue_class, _taskboard_snapshot, _taskboard_status_by_id, _todo_counts, _todo_task_header_count, _try_acquire_watchdog_checkout_lock, _upstream_artifact_store, _upstream_backlog_runner, _upstream_bundle_completion_receipt_loader, _upstream_bundle_payload_builder, _upstream_bundle_runner, _upstream_objective_runner, _upstream_portal_task_parser, _upstream_task_board_helpers, _validate_ipfs_p0_cross_link_goals, _validate_task_payload_fields, _write_status, _write_taskboard_doc, active bundle keys, active todo task ids, active_bundle_keys, add parallel args, add_parallel_args, append missing explicit seed tasks, argparse, ast, atomic write json, build goals, build parser, build_goals
- AST symbol scope: file
- Goal id: codebase/runtime/scripts-refactor_agent_supervisor
- Missing evidence: Review swallowed exception path in scripts/refactor_agent_supervisor.py:4008
- Merge key: codebase/runtime/scripts-refactor_agent_supervisor
- Merge family: scripts/refactor_agent_supervisor.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: bdd4ee0fdbaf63f6
- Acceptance: Codebase scan filed this finding from scripts/refactor_agent_supervisor.py:4008. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-228-codebase-scan-bdd4ee0fdbaf.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
