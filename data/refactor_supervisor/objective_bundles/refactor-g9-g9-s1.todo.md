# Objective Bundle: refactor/g9/g9-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-36: REF-036 Introduce canonical task identity and a durable supervisor task ledger

## REF-036 Introduce canonical task identity and a durable supervisor task ledger

- Status: completed
- Completion: manual
- Priority: P0
- Track: G9
- Depends on:
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/persistent_task_queue.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q
- Bundle: refactor/g9/g9-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S1
- Missing evidence: Bundle-local numeric task ids currently collide across boards and make global reconciliation ambiguous.
- AST symbols: TASK_IDENTITY_SCHEMA, canonical_json_bytes, canonical_content_cid, normalize_identity_text, normalize_identity_path, normalize_board_namespace, board_namespace_from_path, _mapping_value, _sequence, _task_mapping, TaskIdentity, canonical_task_identity, canonical_bundle_identity, check, digest, raw, text, value, normalized, raw_metadata, metadata, namespaced_alias, short_id, to_dict, display_task_id, namespace, provided_key, provided_cid, explicit_key, semantic_fingerprint
- Merge key: refactor/g9/g9-s1
- Candidate kind: seed
- Todo vector key: ref-036-introducecanonicaltaskidentityandadurablesupervi
- Acceptance: Every task has a stable canonical key or CID independent of board path and display id.; Legacy markdown tasks migrate idempotently with board namespace provenance.; Branches, events, retries, cooldowns, leases, and receipts carry canonical identity.; Refill cannot create a second active task for the same canonical work item.

- [x] Task checkbox-37: REF-037 Replace static bundle launch with a dynamic leased worker pool

## REF-037 Replace static bundle launch with a dynamic leased worker pool

- Status: completed
- Completion: manual
- Priority: P0
- Track: G9
- Depends on: REF-036
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/multi_supervisor_runner.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py -q
- Bundle: refactor/g9/g9-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S1
- Missing evidence: The current bundle supervisor starts the first N lexical bundles once and cannot reclaim idle lanes or discover refilled work.
- AST symbols: logger, COORDINATION_COMPACTION_INTERVAL_CYCLES, COORDINATION_COMPACTION_MIN_BYTES, SCHEDULER_GC_INTERVAL_CYCLES, _MANIFEST_REFERENCED_BUNDLE_FIELDS, _MANIFEST_MEMBER_TASK_FIELDS, _MANIFEST_PROFILE_G_REFERENCE_FIELDS, bundle_member_completion_receipts, BundleLaneSpec, _compact_bundle_manifest_payload, _compact_task_manifest_payload, _lane_manifest_payload, _lane_database_payload, RunningBundleLane, resolve_repo_path, lane_state_prefix, _schedule_int, _schedule_bool, _string_list, _lane_schedule_key, _mapping_list, _execution_slice_members, _first_nonempty, _resource_lane_fields, _TERMINAL_CONFLICT_TASK_STATUSES, _live_bundle_conflict_members, _bundle_conflict_task, _excluded_bundle_keys, _conflict_graph_inputs, _graph_payload
- Merge key: refactor/g9/g9-s1
- Candidate kind: seed
- Todo vector key: ref-037-replacestaticbundlelaunchwithadynamicleasedworke
- Acceptance: A persistent scheduler discovers new and refilled tasks without restart.; Workers claim ready tasks, release drained or blocked leases, and steal conflict-safe work.; Lane count remains within configured capacity and no task executes under two accepted leases.; The manifest is an authoritative live projection rather than a launch-time snapshot.

- [x] Task checkbox-38: REF-038 Integrate a deduplicating single-consumer merge train

## REF-038 Integrate a deduplicating single-consumer merge train

- Status: completed
- Completion: manual
- Priority: P0
- Track: G9
- Depends on: REF-037
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py -q
- Bundle: refactor/g9/g9-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S1
- Missing evidence: Independent lanes currently race to merge and repeatedly retry the same failed branches.
- AST symbols: _PRIORITY_ORDER, _ACTIVE_STATES, _COMMIT_METADATA_KEYS, _CANONICAL_METADATA_KEYS, MergeQueueFullError, MergeRequest, _safe_float, _safe_int, _normalise_priority, _first_metadata_value, _atomic_write_json, MergeQueue, __all__, canonical_identity, dedupe_key, to_dict, from_dict, priority, __init__, _connect, _init_database, _import_legacy_files, _insert, enqueue, dequeue, _fairness_key, complete, fail, requeue, quarantine
- Merge key: refactor/g9/g9-s1
- Candidate kind: seed
- Todo vector key: ref-038-integrateadeduplicatingsingle-consumermergetrain
- Acceptance: All implementation lanes enqueue merge candidates instead of racing the target checkout.; The train deduplicates by canonical task and commit, rebases on the latest target, and preserves priority plus age fairness.; One conflict fingerprint invokes at most one active resolver attempt.; Bounded failures enter quarantine with a durable receipt instead of a polling retry loop.
