# Codebase Bundle: codebase/runtime/integrations-ipfs_datasets-loader

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-129 Review swallowed exception path in integrations/ipfs_datasets/loader.py:353

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/loader.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/loader.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-loader
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-loader.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-loader
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/loader.py
- AST symbols: __future__, __future__.annotations, __str__, _build_import_failure, _candidate_ipfs_source_roots, _import_module_preserving_sys_path, _loaded_package_matches, _matches_package_root, _package_dir_for_root, _prime_repo_package, _runner, _should_retry_with_repo_paths, actionable import failure message, actionable_import_failure_message, as dict, as_dict, asyncio, build import failure, build import failure diagnostic, build_import_failure_diagnostic, candidate ipfs source roots, dataclasses, dataclasses dataclass, dataclasses.dataclass, ensure import paths, ensure_import_paths, functools, functools lru cache, functools.lru_cache, future, future annotations, get repo paths, get_repo_paths, import attr optional, import failure message, import failure missing module, import failure type, import module optional, import module preserving sys path, import_attr_optional, import_failure_message, import_failure_missing_module, import_failure_type, import_module_optional, importfailure, importfailure as dict, importfailure str, importfailure.__str__, importfailure.as_dict, importlib, importlib util, importlib.util, loaded package matches, matches package root, optional dependency install command, optional_dependency_install_command, package dir for root, pathlib, pathlib path, pathlib.path, prime repo package, re, repopaths, run async compat, run_async_compat, runner, should retry with repo paths, str, sys, threading, typing, typing any, typing.any
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-loader
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/loader.py:353
- Merge key: codebase/runtime/integrations-ipfs_datasets-loader
- Merge family: integrations/ipfs_datasets/loader.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 992a753ac8550677
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/loader.py:353. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-129-codebase-scan-992a753ac855.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-130 Review swallowed exception path in integrations/ipfs_datasets/loader.py:397

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/loader.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/loader.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-loader
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-loader.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-loader
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/loader.py
- AST symbols: __future__, __future__.annotations, __str__, _build_import_failure, _build_retry_import_failure, _candidate_ipfs_source_roots, _import_module_preserving_sys_path, _loaded_package_matches, _matches_package_root, _package_dir_for_root, _prime_repo_package, _runner, _should_retry_with_repo_paths, actionable import failure message, actionable_import_failure_message, as dict, as_dict, asyncio, build import failure, build import failure diagnostic, build retry import failure, build_import_failure_diagnostic, candidate ipfs source roots, dataclasses, dataclasses dataclass, dataclasses.dataclass, ensure import paths, ensure_import_paths, functools, functools lru cache, functools.lru_cache, future, future annotations, get repo paths, get_repo_paths, import attr optional, import failure message, import failure missing module, import failure type, import module optional, import module preserving sys path, import_attr_optional, import_failure_message, import_failure_missing_module, import_failure_type, import_module_optional, importfailure, importfailure as dict, importfailure str, importfailure.__str__, importfailure.as_dict, importlib, importlib util, importlib.util, loaded package matches, matches package root, optional dependency install command, optional_dependency_install_command, package dir for root, pathlib, pathlib path, pathlib.path, prime repo package, re, repopaths, run async compat, run_async_compat, runner, should retry with repo paths, str, sys, threading, typing, typing any, typing.any
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-loader
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/loader.py:397
- Merge key: codebase/runtime/integrations-ipfs_datasets-loader
- Merge family: integrations/ipfs_datasets/loader.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 9c858e22373c5556
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/loader.py:397. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-130-codebase-scan-9c858e22373c.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-131 Review swallowed exception path in integrations/ipfs_datasets/loader.py:407

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/loader.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/loader.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-loader
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-loader.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-loader
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/loader.py
- AST symbols: __future__, __future__.annotations, __str__, _build_import_failure, _build_retry_import_failure, _candidate_ipfs_source_roots, _import_module_preserving_sys_path, _loaded_package_matches, _matches_package_root, _package_dir_for_root, _prime_repo_package, _runner, _should_retry_with_repo_paths, actionable import failure message, actionable_import_failure_message, as dict, as_dict, asyncio, build import failure, build import failure diagnostic, build retry import failure, build_import_failure_diagnostic, candidate ipfs source roots, dataclasses, dataclasses dataclass, dataclasses.dataclass, ensure import paths, ensure_import_paths, functools, functools lru cache, functools.lru_cache, future, future annotations, get repo paths, get_repo_paths, import attr optional, import failure message, import failure missing module, import failure type, import module optional, import module preserving sys path, import_attr_optional, import_failure_message, import_failure_missing_module, import_failure_type, import_module_optional, importfailure, importfailure as dict, importfailure str, importfailure.__str__, importfailure.as_dict, importlib, importlib util, importlib.util, loaded package matches, matches package root, optional dependency install command, optional_dependency_install_command, package dir for root, pathlib, pathlib path, pathlib.path, prime repo package, re, repopaths, run async compat, run_async_compat, runner, should retry with repo paths, str, sys, threading, typing, typing any, typing.any
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-loader
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/loader.py:407
- Merge key: codebase/runtime/integrations-ipfs_datasets-loader
- Merge family: integrations/ipfs_datasets/loader.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 7a4409f5374e9eb6
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/loader.py:407. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-131-codebase-scan-7a4409f5374e.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
