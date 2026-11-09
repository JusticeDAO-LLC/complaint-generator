# Codebase Bundle: codebase/quality/tests-conftest

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-231 Review swallowed exception path in tests/conftest.py:223

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/conftest.py
- Validation: python3 -m py_compile tests/conftest.py
- Bundle: codebase/quality/tests-conftest
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-conftest.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-conftest
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/conftest.py
- AST symbols: _candidate_ipfs_dataset_roots, _classify_file, _select_ipfs_dataset_root, _strip_reserved_example_urls, _truthy_env, candidate ipfs dataset roots, classify file, importlib, importlib util, importlib.util, ipfs datasets py, ipfs_datasets_py, os, pytest, pytest addoption, pytest collection modifyitems, pytest configure, pytest ignore collect, pytest_addoption, pytest_collection_modifyitems, pytest_configure, pytest_ignore_collect, re, select ipfs dataset root, strip reserved example urls, sys, truthy env
- AST symbol scope: file
- Goal id: codebase/quality/tests-conftest
- Missing evidence: Review swallowed exception path in tests/conftest.py:223
- Merge key: codebase/quality/tests-conftest
- Merge family: tests/conftest.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: dbed215317024db3
- Acceptance: Codebase scan filed this finding from tests/conftest.py:223. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-231-codebase-scan-dbed21531702.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-232 Review swallowed exception path in tests/conftest.py:289

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/conftest.py
- Validation: python3 -m py_compile tests/conftest.py
- Bundle: codebase/quality/tests-conftest
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-conftest.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-conftest
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/conftest.py
- AST symbols: _candidate_ipfs_dataset_roots, _classify_file, _preload_ipfs_datasets_package, _select_ipfs_dataset_root, _strip_reserved_example_urls, _truthy_env, candidate ipfs dataset roots, classify file, importlib, ipfs datasets py, ipfs_datasets_py, os, preload ipfs datasets package, pytest, pytest addoption, pytest collection modifyitems, pytest configure, pytest ignore collect, pytest_addoption, pytest_collection_modifyitems, pytest_configure, pytest_ignore_collect, re, select ipfs dataset root, strip reserved example urls, sys, truthy env, warnings
- AST symbol scope: file
- Goal id: codebase/quality/tests-conftest
- Missing evidence: Review swallowed exception path in tests/conftest.py:289
- Merge key: codebase/quality/tests-conftest
- Merge family: tests/conftest.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 3e17c950c7ebb0a9
- Acceptance: Codebase scan filed this finding from tests/conftest.py:289. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-232-codebase-scan-3e17c950c7eb.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
