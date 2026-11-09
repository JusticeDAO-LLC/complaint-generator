# Codebase Bundle: codebase/quality/tests-test_batch_265_path_validation_security

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-296 Replace placeholder runtime path in tests/test_batch_265_path_validation_security.py:302

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/test_batch_265_path_validation_security.py
- Validation: python3 -m py_compile tests/test_batch_265_path_validation_security.py
- Bundle: codebase/quality/tests-test_batch_265_path_validation_security
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-test_batch_265_path_validation_security.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-test_batch_265_path_validation_security
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/test_batch_265_path_validation_security.py
- AST symbols: ipfs datasets py optimizers common path validator, ipfs datasets py optimizers common path validator blocked filenames, ipfs datasets py optimizers common path validator blocked paths, ipfs datasets py optimizers common path validator pathvalidationerror, ipfs datasets py optimizers common path validator safe open, ipfs datasets py optimizers common path validator validate directory path, ipfs datasets py optimizers common path validator validate input path, ipfs datasets py optimizers common path validator validate output path, ipfs_datasets_py.optimizers.common.path_validator, ipfs_datasets_py.optimizers.common.path_validator.blocked_filenames, ipfs_datasets_py.optimizers.common.path_validator.blocked_paths, ipfs_datasets_py.optimizers.common.path_validator.pathvalidationerror, ipfs_datasets_py.optimizers.common.path_validator.safe_open, ipfs_datasets_py.optimizers.common.path_validator.validate_directory_path, ipfs_datasets_py.optimizers.common.path_validator.validate_input_path, ipfs_datasets_py.optimizers.common.path_validator.validate_output_path, os, pathlib, pathlib path, pathlib.path, pytest, pytest raises, pytest.raises, temp workspace, temp_workspace, tempfile, test absolute path outside base denied, test blocked filenames includes passwd, test blocked filenames includes shadow, test blocked filenames includes ssh keys, test blocked paths includes etc, test blocked paths includes proc, test blocked paths includes sys, test directory as input denied, test empty directory check, test empty path denied, test extension validation fail, test extension validation pass, test file as directory denied, test nonempty directory fails empty check, test nonexistent directory denied, test nonexistent file allowed without must exist, test nonexistent file denied with must exist, test null byte in path, test output extension validation, test output in subdirectory, test output path traversal denied, test output to system path denied, test overwrite allowed with flag, test overwrite denied by default, test path traversal multiple parents denied, test path traversal parent denied, test safe open read, test safe open traversal denied, test safe open write, test sensitive filename denied, test sensitive system path denied, test size limit enforcement, test size limit pass, test spaces in path, test symlink allowed with flag, test symlink denied by default, test unicode in path, test valid directory path, test valid output path, test valid relative path, test very long path, test_absolute_path_outside_base_denied, test_blocked_filenames_includes_passwd, test_blocked_filenames_includes_shadow, test_blocked_filenames_includes_ssh_keys, test_blocked_paths_includes_etc, test_blocked_paths_includes_proc, test_blocked_paths_includes_sys, test_directory_as_input_denied, test_empty_directory_check, test_empty_path_denied, test_extension_validation_fail, test_extension_validation_pass, test_file_as_directory_denied
- AST symbol scope: file
- Goal id: codebase/quality/tests-test_batch_265_path_validation_security
- Missing evidence: Replace placeholder runtime path in tests/test_batch_265_path_validation_security.py:302
- Merge key: codebase/quality/tests-test_batch_265_path_validation_security
- Merge family: tests/test_batch_265_path_validation_security.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 4302ea3ff52032a7
- Acceptance: Codebase scan filed this finding from tests/test_batch_265_path_validation_security.py:302. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-296-codebase-scan-4302ea3ff520.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
