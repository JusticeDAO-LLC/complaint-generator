# Codebase Bundle: codebase/runtime/examples-session_sgd_report

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-116 Review swallowed exception path in examples/session_sgd_report.py:43

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, examples/session_sgd_report.py
- Validation: python3 -m py_compile examples/session_sgd_report.py
- Bundle: codebase/runtime/examples-session_sgd_report
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-examples-session_sgd_report.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/examples-session_sgd_report
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: examples/session_sgd_report.py
- AST symbols: _avg, _dg_counts, _find_session_json_files, _has_question_matching, _kg_counts, _load_json, _maybe_load_json, _safe_int, _session_graph_paths, _summarize_session, _termination_reason, _write_report, argparse, avg, dataclasses, dataclasses dataclass, dataclasses.dataclass, datetime, datetime datetime, datetime utc, datetime.datetime, datetime.utc, dg counts, find session json files, has question matching, json, kg counts, load json, main, maybe load json, os, safe int, session graph paths, sessionsummary, summarize session, termination reason, typing, typing any, typing dict, typing list, typing optional, typing tuple, typing.any, typing.dict, typing.list, typing.optional, typing.tuple, write report
- AST symbol scope: file
- Goal id: codebase/runtime/examples-session_sgd_report
- Missing evidence: Review swallowed exception path in examples/session_sgd_report.py:43
- Merge key: codebase/runtime/examples-session_sgd_report
- Merge family: examples/session_sgd_report.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 504dbdf088b1217d
- Acceptance: Codebase scan filed this finding from examples/session_sgd_report.py:43. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-116-codebase-scan-504dbdf088b1.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-117 Review swallowed exception path in examples/session_sgd_report.py:59

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, examples/session_sgd_report.py
- Validation: python3 -m py_compile examples/session_sgd_report.py
- Bundle: codebase/runtime/examples-session_sgd_report
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-examples-session_sgd_report.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/examples-session_sgd_report
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: examples/session_sgd_report.py
- AST symbols: _avg, _dg_counts, _find_session_json_files, _has_question_matching, _kg_counts, _load_json, _maybe_load_json, _safe_int, _session_graph_paths, _summarize_session, _termination_reason, _write_report, argparse, avg, dataclasses, dataclasses dataclass, dataclasses.dataclass, datetime, datetime datetime, datetime utc, datetime.datetime, datetime.utc, dg counts, find session json files, has question matching, json, kg counts, load json, main, maybe load json, os, safe int, session graph paths, sessionsummary, summarize session, termination reason, typing, typing any, typing dict, typing list, typing optional, typing tuple, typing.any, typing.dict, typing.list, typing.optional, typing.tuple, write report
- AST symbol scope: file
- Goal id: codebase/runtime/examples-session_sgd_report
- Missing evidence: Review swallowed exception path in examples/session_sgd_report.py:59
- Merge key: codebase/runtime/examples-session_sgd_report
- Merge family: examples/session_sgd_report.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 1fafae091ef0e1b2
- Acceptance: Codebase scan filed this finding from examples/session_sgd_report.py:59. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-117-codebase-scan-1fafae091ef0.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
