# Codebase Bundle: codebase/runtime/scripts-run_claim_support_review_regression

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-229 Review swallowed exception path in scripts/run_claim_support_review_regression.py:75

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, scripts/run_claim_support_review_regression.py
- Validation: python3 -m py_compile scripts/run_claim_support_review_regression.py
- Bundle: codebase/runtime/scripts-run_claim_support_review_regression
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-scripts-run_claim_support_review_regression.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/scripts-run_claim_support_review_regression
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: scripts/run_claim_support_review_regression.py
- AST symbols: __future__, __future__.annotations, argparse, build playwright command, build pytest command, build run environment, build_playwright_command, build_pytest_command, build_run_environment, create parser, create_parser, future, future annotations, main, os, pathlib, pathlib path, pathlib.path, playwright chromium available, playwright sync api, playwright sync api sync playwright, playwright.sync_api, playwright.sync_api.sync_playwright, playwright_chromium_available, resolve test targets, resolve_test_targets, subprocess, sys, typing, typing optional, typing sequence, typing.optional, typing.sequence
- AST symbol scope: file
- Goal id: codebase/runtime/scripts-run_claim_support_review_regression
- Missing evidence: Review swallowed exception path in scripts/run_claim_support_review_regression.py:75
- Merge key: codebase/runtime/scripts-run_claim_support_review_regression
- Merge family: scripts/run_claim_support_review_regression.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 75935cbef32fb160
- Acceptance: Codebase scan filed this finding from scripts/run_claim_support_review_regression.py:75. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-229-codebase-scan-75935cbef32f.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
