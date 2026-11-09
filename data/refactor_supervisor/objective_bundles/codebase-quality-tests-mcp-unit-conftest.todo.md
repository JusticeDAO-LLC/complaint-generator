# Codebase Bundle: codebase/quality/tests-mcp-unit-conftest

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-237 Review swallowed exception path in tests/mcp/unit/conftest.py:15

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/mcp/unit/conftest.py
- Validation: python3 -m py_compile tests/mcp/unit/conftest.py
- Bundle: codebase/quality/tests-mcp-unit-conftest
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-mcp-unit-conftest.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-mcp-unit-conftest
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/mcp/unit/conftest.py
- AST symbols: ipfs datasets py logic observability metrics prometheus, ipfs datasets py logic observability metrics prometheus get prometheus collector, ipfs datasets py logic observability otel integration, ipfs datasets py logic observability otel integration get otel tracer, ipfs_datasets_py.logic.observability.metrics_prometheus, ipfs_datasets_py.logic.observability.metrics_prometheus.get_prometheus_collector, ipfs_datasets_py.logic.observability.otel_integration, ipfs_datasets_py.logic.observability.otel_integration.get_otel_tracer, pytest, reset observability singletons, reset_observability_singletons
- AST symbol scope: file
- Goal id: codebase/quality/tests-mcp-unit-conftest
- Missing evidence: Review swallowed exception path in tests/mcp/unit/conftest.py:15
- Merge key: codebase/quality/tests-mcp-unit-conftest
- Merge family: tests/mcp/unit/conftest.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: f12b7e9b7bb2394c
- Acceptance: Codebase scan filed this finding from tests/mcp/unit/conftest.py:15. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-237-codebase-scan-f12b7e9b7bb2.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
