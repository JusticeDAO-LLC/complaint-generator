# Objective Bundle: refactor/g10/g10-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-200: REF-200 Define a typed refill scan result and terminal reason taxonomy

## REF-200 Define a typed refill scan result and terminal reason taxonomy

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on:
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scan_receipts.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/backlog_refinery.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_implementation_supervisor_runner.py -q
- Bundle: refactor/g10/g10-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S1
- Missing evidence: Refill callbacks currently collapse skipped, deduplicated, exhausted, failed, and timed-out scans into the same empty collection.
- AST symbols: REFILL_SCAN_RESULT_SCHEMA_VERSION, SCHEMA_VERSION, CONTRACT_VERSION, SCAN_RECEIPT_SCHEMA, SCAN_RECEIPT_PROJECTION_SCHEMA_VERSION, SCAN_RECEIPT_PROJECTION_SCHEMA, DEFAULT_SCAN_FRESHNESS_SECONDS, EXHAUSTION_QUORUM_SCHEMA_VERSION, EXHAUSTION_QUORUM_SCHEMA, _positive_env_int, DEFAULT_EXHAUSTION_QUORUM_SIZE, DEFAULT_EXHAUSTION_QUORUM, _HEALTHY_REASONS, _SKIPPED_REASONS, T, ScanTerminalReason, ScanMode, ScanSkipReason, _PARSER_FAILURE_REASONS, MAX_REPRESENTATIVE_PATHS_PER_REASON, _count, ScanCoverageCounts, CandidateAccounting, ScanReasonSummary, ScanDetailsArtifact, ScanAccounting, _utc_now, _utc_datetime, _nonempty, _json_value
- Merge key: refactor/g10/g10-s1
- Candidate kind: seed
- Todo vector key: ref-200-defineatypedrefillscanresultandterminalreasontax
- Acceptance: A versioned result contract distinguishes generated, exhausted, duplicate-only, threshold-satisfied, cooldown, disabled, partial, failed, and timed-out outcomes.; The contract records scan mode, analyzer version, repository and tree identity, start and finish timestamps, and whether the result is safe for completion reasoning.; Legacy list-returning callbacks remain supported through an explicit compatibility adapter rather than implicit truthiness.; No empty result is interpreted as goal completion without a typed terminal reason.

- [x] Task checkbox-201: REF-201 Instrument scan inventory, parser coverage, exclusions, and candidate accounting

## REF-201 Instrument scan inventory, parser coverage, exclusions, and candidate accounting

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-200
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scan_receipts.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/backlog_refinery.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py -q
- Bundle: refactor/g10/g10-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S1
- Missing evidence: A zero novel-finding count is not diagnosable without knowing what the analyzer discovered, parsed, skipped, rejected, or failed to inspect.
- AST symbols: REFILL_SCAN_RESULT_SCHEMA_VERSION, SCHEMA_VERSION, CONTRACT_VERSION, SCAN_RECEIPT_SCHEMA, SCAN_RECEIPT_PROJECTION_SCHEMA_VERSION, SCAN_RECEIPT_PROJECTION_SCHEMA, DEFAULT_SCAN_FRESHNESS_SECONDS, EXHAUSTION_QUORUM_SCHEMA_VERSION, EXHAUSTION_QUORUM_SCHEMA, _positive_env_int, DEFAULT_EXHAUSTION_QUORUM_SIZE, DEFAULT_EXHAUSTION_QUORUM, _HEALTHY_REASONS, _SKIPPED_REASONS, T, ScanTerminalReason, ScanMode, ScanSkipReason, _PARSER_FAILURE_REASONS, MAX_REPRESENTATIVE_PATHS_PER_REASON, _count, ScanCoverageCounts, CandidateAccounting, ScanReasonSummary, ScanDetailsArtifact, ScanAccounting, _utc_now, _utc_datetime, _nonempty, _json_value
- Merge key: refactor/g10/g10-s1
- Candidate kind: seed
- Todo vector key: ref-201-instrumentscaninventoryparsercoverageexclusionsa
- Acceptance: Receipts count git roots, tracked files, eligible files, parsed files, cache hits, excluded files, parser failures, raw candidates, seen candidates, deduplicated candidates, and appended tasks.; Every skipped file and parser failure has a bounded reason code plus representative paths, with full details available as a durable artifact.; Candidate accounting balances from raw detection through filtering and task materialization.; Incremental and exhaustive scans report equivalent coverage dimensions.

- [x] Task checkbox-202: REF-202 Persist scan receipts in events, strategy state, status, and scheduler metrics

## REF-202 Persist scan receipts in events, strategy state, status, and scheduler metrics

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-200
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scan_receipts.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/event_log.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/implementation_supervisor_runner.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_implementation_supervisor_runner.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_implementation_supervisor_runner.py -q
- Bundle: refactor/g10/g10-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S1
- Missing evidence: Operators and schedulers currently see only refill counts, so they cannot distinguish healthy exhaustion from an analyzer failure.
- AST symbols: REFILL_SCAN_RESULT_SCHEMA_VERSION, SCHEMA_VERSION, CONTRACT_VERSION, SCAN_RECEIPT_SCHEMA, SCAN_RECEIPT_PROJECTION_SCHEMA_VERSION, SCAN_RECEIPT_PROJECTION_SCHEMA, DEFAULT_SCAN_FRESHNESS_SECONDS, EXHAUSTION_QUORUM_SCHEMA_VERSION, EXHAUSTION_QUORUM_SCHEMA, _positive_env_int, DEFAULT_EXHAUSTION_QUORUM_SIZE, DEFAULT_EXHAUSTION_QUORUM, _HEALTHY_REASONS, _SKIPPED_REASONS, T, ScanTerminalReason, ScanMode, ScanSkipReason, _PARSER_FAILURE_REASONS, MAX_REPRESENTATIVE_PATHS_PER_REASON, _count, ScanCoverageCounts, CandidateAccounting, ScanReasonSummary, ScanDetailsArtifact, ScanAccounting, _utc_now, _utc_datetime, _nonempty, _json_value
- Merge key: refactor/g10/g10-s1
- Candidate kind: seed
- Todo vector key: ref-202-persistscanreceiptsineventsstrategystatestatusan
- Acceptance: Each refill attempt emits one canonical receipt CID and a compact event projection regardless of outcome.; Strategy and status payloads expose the latest successful scan, latest attempted scan, terminal reason, freshness, health, and candidate funnel.; Large per-file details are referenced by artifact path or CID rather than embedded repeatedly in heartbeat files.; Metrics distinguish skipped, duplicate-only, exhausted, partial, and failed scans without breaking older consumers.
