# Codebase Bundle: codebase/runtime/examples-sweep_ranker

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-118 Review swallowed exception path in examples/sweep_ranker.py:20

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, examples/sweep_ranker.py
- Validation: python3 -m py_compile examples/sweep_ranker.py
- Bundle: codebase/runtime/examples-sweep_ranker
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-examples-sweep_ranker.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/examples-sweep_ranker
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: examples/sweep_ranker.py
- AST symbols: _load_json, _parse_weights, _safe_float, argparse, json, load json, main, math, os, parse weights, rank sweep results, rank_sweep_results, safe float, score point, score_point, typing, typing any, typing dict, typing list, typing tuple, typing.any, typing.dict, typing.list, typing.tuple
- AST symbol scope: file
- Goal id: codebase/runtime/examples-sweep_ranker
- Missing evidence: Review swallowed exception path in examples/sweep_ranker.py:20
- Merge key: codebase/runtime/examples-sweep_ranker
- Merge family: examples/sweep_ranker.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 5f056c29355d1e24
- Acceptance: Codebase scan filed this finding from examples/sweep_ranker.py:20. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-118-codebase-scan-5f056c29355d.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
