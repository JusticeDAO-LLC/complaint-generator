# Codebase Bundle: codebase/runtime/examples-codex_multi_run_autopatch

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-111 Review swallowed exception path in examples/codex_multi_run_autopatch.py:972

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, examples/codex_multi_run_autopatch.py
- Validation: python3 -m py_compile examples/codex_multi_run_autopatch.py
- Bundle: codebase/runtime/examples-codex_multi_run_autopatch
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-examples-codex_multi_run_autopatch.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/examples-codex_multi_run_autopatch
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: examples/codex_multi_run_autopatch.py
- AST symbols: __str__, _apply_hunk_to_lines, _apply_patch_transaction, _atomic_write_json, _codex_fix_patch, _dry_run_apply_patch_text, _ensure_dir, _expand_context_window_lines, _extract_update_files, _find_latest_rate_limit_artifact, _find_subsequence, _find_subsequence_relaxed_indent, _find_subsequence_rstrip, _fmt_delta, _generate_codex_patch_for_run, _get_llm_router_backend_config, _load_config, _load_json, _load_json_or_none, _load_session_sgd_report_module, _make_session_backend, _maybe_advance_stage, _normalize_patch_text, _parse_apply_patch, _print_rate_limit_summary, _project_relative_path, _read_text, _restore_undo_record, _run_batch_and_persist, _run_streaming, _select_context_slice_for_failure, _utc_stamp, _validate_python_syntax, _write_undo_record, adversarial harness, adversarial harness adversarialharness, adversarial harness optimizer, adversarial_harness, adversarial_harness.adversarialharness, adversarial_harness.optimizer, apply apply patch text, apply hunk to lines, apply patch transaction, apply_apply_patch_text, argparse, ast, atomic write json, backends, backends llmrouterbackend, backends.llmrouterbackend, base64, clip, codex fix patch, copy, copy deepcopy, copy.deepcopy, dataclasses, dataclasses dataclass, dataclasses.dataclass, datetime, datetime datetime, datetime timezone, datetime.datetime, datetime.timezone, difflib, dry run apply patch text, ensure dir, expand context window lines, extract update files, find latest rate limit artifact, find subsequence, find subsequence relaxed indent, find subsequence rstrip, flush file, flush_file, fmt delta, generate codex patch for run, get llm router backend config, glob, importlib util
- AST symbol scope: file
- Goal id: codebase/runtime/examples-codex_multi_run_autopatch
- Missing evidence: Review swallowed exception path in examples/codex_multi_run_autopatch.py:972
- Merge key: codebase/runtime/examples-codex_multi_run_autopatch
- Merge family: examples/codex_multi_run_autopatch.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 36cf294a133f9569
- Acceptance: Codebase scan filed this finding from examples/codex_multi_run_autopatch.py:972. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-111-codebase-scan-36cf294a133f.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
