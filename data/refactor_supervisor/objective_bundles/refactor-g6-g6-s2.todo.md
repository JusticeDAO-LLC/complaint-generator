# Objective Bundle: refactor/g6/g6-s2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-19: REF-019 Standardize daemon status payload shape across UI, scraper, Gmail, and refactor supervisors

## REF-019 Standardize daemon status payload shape across UI, scraper, Gmail, and refactor supervisors

- Status: completed
- Completion: manual
- Priority: P1
- Track: G6
- Depends on: 
- Outputs: complaint_generator/ui_optimizer_daemon.py, integrations/ipfs_datasets/scraper_daemon.py, scripts/gmail_duckdb_daemon.py
- Validation: python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_gmail_duckdb_daemon_cli.py -q
- Bundle: refactor/g6/g6-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G6.S2
- Missing evidence: Multiple daemon surfaces should be inspectable with the same status fields.
- AST symbols: _STOP_REQUESTED, PROJECT_ROOT, _slugify_user_id, _default_artifact_root, _default_pid_file, _default_status_file, _default_log_file, _signal_stop, _pid_is_running, _matching_daemon_pids, _write_json, _load_json, _unique_nonempty, _derive_adversarial_goals, _resolve_runtime_paths, _cycle_dir, _prune_old_cycle_artifacts, _build_status_payload, _write_status, _cleanup_pid_file, _review_json_excerpt, _parse_iso_datetime, _elapsed_seconds, _seconds_until, _classify_error, _extract_optimizer_recommendation_coverage, _extract_optimizer_changed_files, _run_cycle, _run_daemon, _build_run_command
- Merge key: refactor/g6/g6-s2
- Candidate kind: seed
- Todo vector key: ref-019-standardizedaemonstatuspayloadshapeacrossuiscrap
- Acceptance: Status payloads include status, pid, updated_at, artifacts, and last_error where applicable.; Existing CLI tests remain compatible.

- [x] Task checkbox-20: REF-020 Add queue count and last-cycle metrics to long-running automation docs

## REF-020 Add queue count and last-cycle metrics to long-running automation docs

- Status: completed
- Completion: manual
- Priority: P2
- Track: G6
- Depends on: 
- Outputs: docs/OBSERVABILITY_INDEX.md, docs/observability/TROUBLESHOOTING.md
- Validation: python scripts/refactor_agent_supervisor.py status
- Bundle: refactor/g6/g6-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G6.S2
- Missing evidence: Operators need consistent guidance for stalled background workflows.
- AST symbols: 
- Merge key: refactor/g6/g6-s2
- Candidate kind: seed
- Todo vector key: ref-020-addqueuecountandlast-cyclemetricstolong-runninga
- Acceptance: Docs explain where to find pid, log, status, and queue files.; Troubleshooting includes stale running task recovery.
