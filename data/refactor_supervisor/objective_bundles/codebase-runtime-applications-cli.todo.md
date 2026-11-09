# Codebase Bundle: codebase/runtime/applications-cli

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-083 Review swallowed exception path in applications/cli.py:112

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on:
- Outputs: data/agent_supervisor/discovery, applications/cli.py
- Validation: python3 -m py_compile applications/cli.py
- Bundle: codebase/runtime/applications-cli
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-applications-cli.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/applications-cli
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: applications/cli.py
- AST symbols: __init__, _build_local_session_payload, _ensure_session_identity, _format_adversarial_autopatch_output, _format_authority_search_history_summary, _format_authority_search_program_summary, _format_claim_review_output, _format_claim_review_quality_summary, _format_cli_count_labels, _format_execute_follow_up_output, _format_execution_quality_summary, _format_export_complaint_output, _format_follow_up_fact_targeting, _format_follow_up_fact_targeting_summary, _format_follow_up_source_context_summary, _format_history_output, _format_intake_status_summary, _format_search_warning_summary, _format_status_output, _format_temporal_follow_up_summary, _humanize_cli_label, _local_state_dir, _parse_command_options, _resolve_prompt_text, _restore_local_session_payload, _using_temporary_session, adversarial autopatch, adversarial harness demo autopatch, adversarial harness demo autopatch run adversarial autopatch batch, adversarial_autopatch, adversarial_harness.demo_autopatch, adversarial_harness.demo_autopatch.run_adversarial_autopatch_batch, build local session payload, claim review, claim_review, cli, cli adversarial autopatch, cli build local session payload, cli claim review, cli ensure session identity, cli execute follow up, cli export complaint, cli feed, cli format adversarial autopatch output, cli format authority search history summary, cli format authority search program summary, cli format claim review output, cli format claim review quality summary, cli format cli count labels, cli format execute follow up output, cli format execution quality summary, cli format export complaint output, cli format follow up fact targeting, cli format follow up fact targeting summary, cli format follow up source context summary, cli format history output, cli format intake status summary, cli format search warning summary, cli format status output, cli format temporal follow up summary, cli humanize cli label, cli init, cli interpret command, cli local state dir, cli loop, cli parse command options, cli print commands, cli print error, cli print response, cli resolve prompt text, cli restore local session payload, cli resume, cli save, cli using temporary session, cli.__init__, cli._build_local_session_payload, cli._ensure_session_identity, cli._format_adversarial_autopatch_output, cli._format_authority_search_history_summary, cli._format_authority_search_program_summary
- Goal id: codebase/runtime/applications-cli
- Missing evidence: Review swallowed exception path in applications/cli.py:112
- Merge key: codebase/runtime/applications-cli
- Merge family: applications/cli.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Todo vector key: 8418d6dba6f128ff
- Acceptance: Codebase scan filed this finding from applications/cli.py:112. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-083-codebase-scan-8418d6dba6f1.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
