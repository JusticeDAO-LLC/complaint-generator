# Consolidate complaint-generator sprawl into versioned module interfaces

<!-- plan_id: baguqeeraij2aoguooiextp3nlk6o6ss5ywi5k7bktaemqo6er54n5audj4hq -->

Implementation tasks begin pending. Completion requires behavioral validation evidence.

## CIMP-CON-01 Move session reports group A out of the repository root

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: CONG-relocate
- Subgoal: CONS-markdown
- Depends on: 
- Outputs: docs/archive/sessions/AUTONOMOUS_SESSION_REPORT.md, docs/archive/sessions/BATCH_254_258_SESSION_SUMMARY.md, docs/archive/sessions/BATCH_305_306_SESSION_SUMMARY.md, docs/archive/sessions/BATCH_328_API_RETURN_TYPES_SUMMARY.md, docs/archive/sessions/BATCH_329_EXCEPTION_HANDLING_SUMMARY.md, docs/archive/sessions/BENCHMARK_SUITE_SESSION_SUMMARY.md, docs/archive/sessions/ITEM_7_COMPLETION_SUMMARY.md, docs/archive/sessions/P3_INFRASTRUCTURE_COMPLETION_SESSION.md, docs/archive/sessions/P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md, tests/test_cimp_con_01.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_01.py
- Acceptance: Each named session reports group A file is absent from the repository root and present at docs/archive/sessions with its recorded byte size. README.md remains at the repository root.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Git mv each of these tracked files into docs/archive/sessions/ and nowhere else: AUTONOMOUS_SESSION_REPORT.md (14822 bytes), BATCH_254_258_SESSION_SUMMARY.md (15081 bytes), BATCH_305_306_SESSION_SUMMARY.md (6799 bytes), BATCH_328_API_RETURN_TYPES_SUMMARY.md (11564 bytes), BATCH_329_EXCEPTION_HANDLING_SUMMARY.md (11919 bytes), BENCHMARK_SUITE_SESSION_SUMMARY.md (10574 bytes), ITEM_7_COMPLETION_SUMMARY.md (9658 bytes), P3_INFRASTRUCTURE_COMPLETION_SESSION.md (6935 bytes), P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md (8334 bytes). The destination file must be the same number of bytes. The repository-root path must not exist afterwards. Keep README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md at the repository root. Write tests/test_cimp_con_01.py with zero skips. Hard-code every name and byte size. Assert each destination file exists and has that exact size, and each old path does not exist. Assert README.md is still a file at the repository root and is not inside docs/archive/sessions. Do not treat an index entry as a substitute for the file.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Git mv each of these tracked files into docs/archive/sessions/ and nowhere else: AUTONOMOUS_SESSION_REPORT.md (14822 bytes), BATCH_254_258_SESSION_SUMMARY.md (15081 bytes), BATCH_305_306_SESSION_SUMMARY.md (6799 bytes), BATCH_328_API_RETURN_TYPES_SUMMARY.md (11564 bytes), BATCH_329_EXCEPTION_HANDLING_SUMMARY.md (11919 bytes), BENCHMARK_SUITE_SESSION_SUMMARY.md (10574 bytes), ITEM_7_COMPLETION_SUMMARY.md (9658 bytes), P3_INFRASTRUCTURE_COMPLETION_SESSION.md (6935 bytes), P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md (8334 bytes).
> The destination file must be the same number of bytes. The repository-root path must not exist afterwards.
> Keep README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md at the repository root.
> Write tests/test_cimp_con_01.py with zero skips. Hard-code every name and byte size. Assert each destination file exists and has that exact size, and each old path does not exist. Assert README.md is still a file at the repository root and is not inside docs/archive/sessions. Do not treat an index entry as a substitute for the file.

## CIMP-CON-02 Move session reports group B out of the repository root

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: CONG-relocate
- Subgoal: CONS-markdown
- Depends on: 
- Outputs: docs/archive/sessions/PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md, docs/archive/sessions/PHASE_2_COMPLETION_SUMMARY.md, docs/archive/sessions/QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md, docs/archive/sessions/QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md, docs/archive/sessions/README_OLD.md, docs/archive/sessions/README_OLD_BACKUP.md, docs/archive/sessions/README_OLD_FULL.md, docs/archive/sessions/SESSION_3_COMPLETE_SUMMARY.md, docs/archive/sessions/SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md, tests/test_cimp_con_02.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_02.py
- Acceptance: Each named session reports group B file is absent from the repository root and present at docs/archive/sessions with its recorded byte size. README.md remains at the repository root.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Git mv each of these tracked files into docs/archive/sessions/ and nowhere else: PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md (10410 bytes), PHASE_2_COMPLETION_SUMMARY.md (5565 bytes), QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md (7895 bytes), QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md (15427 bytes), README_OLD.md (817 bytes), README_OLD_BACKUP.md (16697 bytes), README_OLD_FULL.md (30925 bytes), SESSION_3_COMPLETE_SUMMARY.md (12676 bytes), SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md (8397 bytes). The destination file must be the same number of bytes. The repository-root path must not exist afterwards. Keep README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md at the repository root. Write tests/test_cimp_con_02.py with zero skips. Hard-code every name and byte size. Assert each destination file exists and has that exact size, and each old path does not exist. Assert README.md is still a file at the repository root and is not inside docs/archive/sessions. Do not treat an index entry as a substitute for the file.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Git mv each of these tracked files into docs/archive/sessions/ and nowhere else: PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md (10410 bytes), PHASE_2_COMPLETION_SUMMARY.md (5565 bytes), QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md (7895 bytes), QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md (15427 bytes), README_OLD.md (817 bytes), README_OLD_BACKUP.md (16697 bytes), README_OLD_FULL.md (30925 bytes), SESSION_3_COMPLETE_SUMMARY.md (12676 bytes), SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md (8397 bytes).
> The destination file must be the same number of bytes. The repository-root path must not exist afterwards.
> Keep README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md at the repository root.
> Write tests/test_cimp_con_02.py with zero skips. Hard-code every name and byte size. Assert each destination file exists and has that exact size, and each old path does not exist. Assert README.md is still a file at the repository root and is not inside docs/archive/sessions. Do not treat an index entry as a substitute for the file.

## CIMP-CON-03 Move session reports group C out of the repository root

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: CONG-relocate
- Subgoal: CONS-markdown
- Depends on: 
- Outputs: docs/archive/sessions/SESSION_84_FINAL_SUMMARY.md, docs/archive/sessions/SESSION_84_PHASE4_EXTENDED_SUMMARY.md, docs/archive/sessions/SESSION_84_PHASE4_SUMMARY.md, docs/archive/sessions/SESSION_84_PROGRESS.md, docs/archive/sessions/SESSION_SUMMARY_2024_02_24.md, docs/archive/sessions/SESSION_SUMMARY_2026_02_23.md, docs/archive/sessions/SESSION_SUMMARY_2026_02_24_COMPLETE.md, docs/archive/sessions/SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md, docs/archive/sessions/SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md, tests/test_cimp_con_03.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_03.py
- Acceptance: Each named session reports group C file is absent from the repository root and present at docs/archive/sessions with its recorded byte size. README.md remains at the repository root.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Git mv each of these tracked files into docs/archive/sessions/ and nowhere else: SESSION_84_FINAL_SUMMARY.md (7741 bytes), SESSION_84_PHASE4_EXTENDED_SUMMARY.md (17752 bytes), SESSION_84_PHASE4_SUMMARY.md (13483 bytes), SESSION_84_PROGRESS.md (13783 bytes), SESSION_SUMMARY_2024_02_24.md (10746 bytes), SESSION_SUMMARY_2026_02_23.md (8389 bytes), SESSION_SUMMARY_2026_02_24_COMPLETE.md (13118 bytes), SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md (5478 bytes), SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md (8261 bytes). The destination file must be the same number of bytes. The repository-root path must not exist afterwards. Keep README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md at the repository root. Write tests/test_cimp_con_03.py with zero skips. Hard-code every name and byte size. Assert each destination file exists and has that exact size, and each old path does not exist. Assert README.md is still a file at the repository root and is not inside docs/archive/sessions. Do not treat an index entry as a substitute for the file.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Git mv each of these tracked files into docs/archive/sessions/ and nowhere else: SESSION_84_FINAL_SUMMARY.md (7741 bytes), SESSION_84_PHASE4_EXTENDED_SUMMARY.md (17752 bytes), SESSION_84_PHASE4_SUMMARY.md (13483 bytes), SESSION_84_PROGRESS.md (13783 bytes), SESSION_SUMMARY_2024_02_24.md (10746 bytes), SESSION_SUMMARY_2026_02_23.md (8389 bytes), SESSION_SUMMARY_2026_02_24_COMPLETE.md (13118 bytes), SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md (5478 bytes), SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md (8261 bytes).
> The destination file must be the same number of bytes. The repository-root path must not exist afterwards.
> Keep README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md at the repository root.
> Write tests/test_cimp_con_03.py with zero skips. Hard-code every name and byte size. Assert each destination file exists and has that exact size, and each old path does not exist. Assert README.md is still a file at the repository root and is not inside docs/archive/sessions. Do not treat an index entry as a substitute for the file.

## CIMP-CON-04 Move stale root plans and profile reports into the report archive

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: CONG-relocate
- Subgoal: CONS-markdown
- Depends on: 
- Outputs: docs/archive/reports/AUDIT_DICT_RETURNS_REPORT.md, docs/archive/reports/BATCH_202_PLAN.md, docs/archive/reports/EXTRACTION_PIPELINE_PROFILE_FINAL.md, docs/archive/reports/PARALLEL_VALIDATION_FIX_REPORT.md, docs/archive/reports/UNIFIED_PERFORMANCE_ANALYSIS.md, docs/archive/reports/plan-mcpPlusPlusIntegration.prompt.md, tests/test_cimp_con_04.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_04.py
- Acceptance: Each named plan and profile report is absent from the repository root and present at docs/archive/reports with its recorded byte size. README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, and TODO.md remain at the repository root.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Git mv each of these tracked files into docs/archive/reports/ and nowhere else: AUDIT_DICT_RETURNS_REPORT.md (3979 bytes), BATCH_202_PLAN.md (4452 bytes), EXTRACTION_PIPELINE_PROFILE_FINAL.md (10708 bytes), PARALLEL_VALIDATION_FIX_REPORT.md (4095 bytes), UNIFIED_PERFORMANCE_ANALYSIS.md (12002 bytes), plan-mcpPlusPlusIntegration.prompt.md (6459 bytes). The destination file must be the same number of bytes. The repository-root path must not exist afterwards. Keep README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md at the repository root. Write tests/test_cimp_con_04.py with zero skips. Hard-code every name and byte size. Assert each destination file exists and has that exact size, and each old path does not exist. Assert README.md is still a file at the repository root and is not inside docs/archive/reports. Do not treat an index entry as a substitute for the file. These reports were previously left at the root by calling them non-historical. That exception is withdrawn. Move them.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Git mv each of these tracked files into docs/archive/reports/ and nowhere else: AUDIT_DICT_RETURNS_REPORT.md (3979 bytes), BATCH_202_PLAN.md (4452 bytes), EXTRACTION_PIPELINE_PROFILE_FINAL.md (10708 bytes), PARALLEL_VALIDATION_FIX_REPORT.md (4095 bytes), UNIFIED_PERFORMANCE_ANALYSIS.md (12002 bytes), plan-mcpPlusPlusIntegration.prompt.md (6459 bytes).
> The destination file must be the same number of bytes. The repository-root path must not exist afterwards.
> Keep README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md at the repository root.
> Write tests/test_cimp_con_04.py with zero skips. Hard-code every name and byte size. Assert each destination file exists and has that exact size, and each old path does not exist. Assert README.md is still a file at the repository root and is not inside docs/archive/reports. Do not treat an index entry as a substitute for the file.
> These reports were previously left at the root by calling them non-historical. That exception is withdrawn. Move them.

## CIMP-CON-05 Make archive indexes resolve and retire the weakened archive test

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: CONG-relocate
- Subgoal: CONS-markdown
- Depends on: CIMP-CON-01, CIMP-CON-02, CIMP-CON-03, CIMP-CON-04
- Outputs: docs/archive/sessions/INDEX.md, docs/archive/reports/INDEX.md, docs/architecture/repository_module_map.json, tests/test_cimp_mod_19.py, tests/test_cimp_con_05.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_05.py tests/test_cimp_mod_19.py
- Acceptance: docs/archive/sessions/INDEX.md and docs/archive/reports/INDEX.md link once to every moved file, and every relative link resolves to a file. tests/test_cimp_mod_19.py fails if any of the 27 session names remains at the repository root or is missing from docs/archive/sessions. repository_module_map.json records source_files_moved true and does not claim a moved file still exists at the repository root.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  The previous archive test encoded the wrong contract: tests/test_cimp_mod_19.py currently asserts the 27 session names are still files at the repository root and allows missing archive targets. Replace that contract. Write docs/archive/sessions/INDEX.md with one relative link to each of: AUTONOMOUS_SESSION_REPORT.md, BATCH_254_258_SESSION_SUMMARY.md, BATCH_305_306_SESSION_SUMMARY.md, BATCH_328_API_RETURN_TYPES_SUMMARY.md, BATCH_329_EXCEPTION_HANDLING_SUMMARY.md, BENCHMARK_SUITE_SESSION_SUMMARY.md, ITEM_7_COMPLETION_SUMMARY.md, P3_INFRASTRUCTURE_COMPLETION_SESSION.md, P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md, PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md, PHASE_2_COMPLETION_SUMMARY.md, QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md, QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md, README_OLD.md, README_OLD_BACKUP.md, README_OLD_FULL.md, SESSION_3_COMPLETE_SUMMARY.md, SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md, SESSION_84_FINAL_SUMMARY.md, SESSION_84_PHASE4_EXTENDED_SUMMARY.md, SESSION_84_PHASE4_SUMMARY.md, SESSION_84_PROGRESS.md, SESSION_SUMMARY_2024_02_24.md, SESSION_SUMMARY_2026_02_23.md, SESSION_SUMMARY_2026_02_24_COMPLETE.md, SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md, SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md. Write docs/archive/reports/INDEX.md with one relative link to each of: AUDIT_DICT_RETURNS_REPORT.md, BATCH_202_PLAN.md, EXTRACTION_PIPELINE_PROFILE_FINAL.md, PARALLEL_VALIDATION_FIX_REPORT.md, UNIFIED_PERFORMANCE_ANALYSIS.md, plan-mcpPlusPlusIntegration.prompt.md. Every link must resolve. Do not link a file that is still at the repository root. Update docs/architecture/repository_module_map.json so source_files_moved is true, source_files_rewritten stays false, and root_markdown no longer lists a moved file as a root path that exists. Record the archive path instead. Rewrite tests/test_cimp_mod_19.py so test_module_map_historical_markdown_is_archived asserts each archived name is not a root file and is a file under docs/archive/sessions, and test_archive_index_lists_each_moved_file_once asserts unresolved_index_links returns an empty list. Delete the equality that accepts missing archive files. tests/test_cimp_con_05.py must repeat those path and link checks itself, without calling a helper that can be redefined to ignore missing files. Keep README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, and TODO.md at the root.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> The previous archive test encoded the wrong contract: tests/test_cimp_mod_19.py currently asserts the 27 session names are still files at the repository root and allows missing archive targets. Replace that contract.
> Write docs/archive/sessions/INDEX.md with one relative link to each of: AUTONOMOUS_SESSION_REPORT.md, BATCH_254_258_SESSION_SUMMARY.md, BATCH_305_306_SESSION_SUMMARY.md, BATCH_328_API_RETURN_TYPES_SUMMARY.md, BATCH_329_EXCEPTION_HANDLING_SUMMARY.md, BENCHMARK_SUITE_SESSION_SUMMARY.md, ITEM_7_COMPLETION_SUMMARY.md, P3_INFRASTRUCTURE_COMPLETION_SESSION.md, P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md, PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md, PHASE_2_COMPLETION_SUMMARY.md, QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md, QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md, README_OLD.md, README_OLD_BACKUP.md, README_OLD_FULL.md, SESSION_3_COMPLETE_SUMMARY.md, SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md, SESSION_84_FINAL_SUMMARY.md, SESSION_84_PHASE4_EXTENDED_SUMMARY.md, SESSION_84_PHASE4_SUMMARY.md, SESSION_84_PROGRESS.md, SESSION_SUMMARY_2024_02_24.md, SESSION_SUMMARY_2026_02_23.md, SESSION_SUMMARY_2026_02_24_COMPLETE.md, SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md, SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md.
> Write docs/archive/reports/INDEX.md with one relative link to each of: AUDIT_DICT_RETURNS_REPORT.md, BATCH_202_PLAN.md, EXTRACTION_PIPELINE_PROFILE_FINAL.md, PARALLEL_VALIDATION_FIX_REPORT.md, UNIFIED_PERFORMANCE_ANALYSIS.md, plan-mcpPlusPlusIntegration.prompt.md.
> Every link must resolve. Do not link a file that is still at the repository root.
> Update docs/architecture/repository_module_map.json so source_files_moved is true, source_files_rewritten stays false, and root_markdown no longer lists a moved file as a root path that exists. Record the archive path instead.
> Rewrite tests/test_cimp_mod_19.py so test_module_map_historical_markdown_is_archived asserts each archived name is not a root file and is a file under docs/archive/sessions, and test_archive_index_lists_each_moved_file_once asserts unresolved_index_links returns an empty list. Delete the equality that accepts missing archive files.
> tests/test_cimp_con_05.py must repeat those path and link checks itself, without calling a helper that can be redefined to ignore missing files. Keep README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, and TODO.md at the root.

## CIMP-CON-06 Move root maintenance scripts into scripts/maintenance

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: CONG-relocate
- Subgoal: CONS-root-code
- Depends on: 
- Outputs: scripts/maintenance/add_dedup_factory.py, scripts/maintenance/add_init_vars.py, scripts/maintenance/add_optimization_methods.py, scripts/maintenance/batch_230_benchmark.py, scripts/maintenance/batch_231_llm_fallback_profile.py, scripts/maintenance/complete_optimizer_integration.py, scripts/maintenance/profile_generate_10k.py, scripts/maintenance/update_detect_graph_type.py, tests/test_cimp_con_06.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_06.py
- Acceptance: The eight named maintenance scripts are absent from the repository root and present under scripts/maintenance. No other Python file imports those module names from the repository root.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Git mv these root scripts to scripts/maintenance/: add_dedup_factory.py, add_init_vars.py, add_optimization_methods.py, batch_230_benchmark.py, batch_231_llm_fallback_profile.py, complete_optimizer_integration.py, profile_generate_10k.py, update_detect_graph_type.py. Add scripts/maintenance/__init__.py only if the package needs it; an empty init is acceptable. tests/test_cimp_con_06.py parses every Python file outside external/ and fails if any file still imports one of those module names as a top-level module. Assert each root path is gone and each new path is a non-empty file. Assert main.py is still at the repository root.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Git mv these root scripts to scripts/maintenance/: add_dedup_factory.py, add_init_vars.py, add_optimization_methods.py, batch_230_benchmark.py, batch_231_llm_fallback_profile.py, complete_optimizer_integration.py, profile_generate_10k.py, update_detect_graph_type.py.
> Add scripts/maintenance/__init__.py only if the package needs it; an empty init is acceptable.
> tests/test_cimp_con_06.py parses every Python file outside external/ and fails if any file still imports one of those module names as a top-level module. Assert each root path is gone and each new path is a non-empty file. Assert main.py is still at the repository root.

## CIMP-CON-07 Move root-level checks and tracked debug snapshots out of the root

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: CONG-relocate
- Subgoal: CONS-root-code
- Depends on: 
- Outputs: scripts/legacy_root_checks/test_complaint_mcp_protocol.py, scripts/legacy_root_checks/test_criticscor_comparisons.py, scripts/legacy_root_checks/test_extraction_config_validation.py, scripts/legacy_root_checks/test_main_app_surface.py, scripts/legacy_root_checks/test_parallel_validation_fix.py, scripts/legacy_root_checks/test_pipeline_error_recovery.py, scripts/legacy_root_checks/test_probate_integration.py, docs/archive/debug_snapshots/tmp_validation_llm_draft/validation-user.json, docs/archive/debug_snapshots/tmp_validation_llm_enabled/llm-user.json, docs/archive/debug_snapshots/tmp_workspace_debug/did-key-fallback-238d1d58205943569241ca68b96e5afb.json, docs/archive/debug_snapshots/workspace/improve_temporary_session_complaint.py, docs/archive/debug_snapshots/workspace/temporary-cli-session-migration/README.md, tests/test_cimp_con_07.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_07.py
- Acceptance: The seven root test_*.py files are absent from the repository root and present under scripts/legacy_root_checks, outside pytest collection. The five tracked debug snapshots are absent from tmp_* and workspace/ and present under docs/archive/debug_snapshots with the same byte sizes.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Git mv these root modules to scripts/legacy_root_checks/: test_complaint_mcp_protocol.py, test_criticscor_comparisons.py, test_extraction_config_validation.py, test_main_app_surface.py, test_parallel_validation_fix.py, test_pipeline_error_recovery.py, test_probate_integration.py. Do not put them under tests/, because pytest.ini collects tests/ and these scripts are not the focused suite. Git mv each debug snapshot to docs/archive/debug_snapshots/ while preserving the relative tail: tmp_validation_llm_draft/validation-user.json (9642 bytes) -> docs/archive/debug_snapshots/tmp_validation_llm_draft/validation-user.json, tmp_validation_llm_enabled/llm-user.json (9602 bytes) -> docs/archive/debug_snapshots/tmp_validation_llm_enabled/llm-user.json, tmp_workspace_debug/did-key-fallback-238d1d58205943569241ca68b96e5afb.json (330 bytes) -> docs/archive/debug_snapshots/tmp_workspace_debug/did-key-fallback-238d1d58205943569241ca68b96e5afb.json, workspace/improve_temporary_session_complaint.py (554 bytes) -> docs/archive/debug_snapshots/workspace/improve_temporary_session_complaint.py, workspace/temporary-cli-session-migration/README.md (3963 bytes) -> docs/archive/debug_snapshots/workspace/temporary-cli-session-migration/README.md. tests/test_cimp_con_07.py hard-codes those names and byte sizes. Assert the old paths do not exist, the new files have the exact sizes, and pytest collection roots in pytest.ini do not include scripts/legacy_root_checks. Leave artifacts/ where it is.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Git mv these root modules to scripts/legacy_root_checks/: test_complaint_mcp_protocol.py, test_criticscor_comparisons.py, test_extraction_config_validation.py, test_main_app_surface.py, test_parallel_validation_fix.py, test_pipeline_error_recovery.py, test_probate_integration.py.
> Do not put them under tests/, because pytest.ini collects tests/ and these scripts are not the focused suite.
> Git mv each debug snapshot to docs/archive/debug_snapshots/ while preserving the relative tail: tmp_validation_llm_draft/validation-user.json (9642 bytes) -> docs/archive/debug_snapshots/tmp_validation_llm_draft/validation-user.json, tmp_validation_llm_enabled/llm-user.json (9602 bytes) -> docs/archive/debug_snapshots/tmp_validation_llm_enabled/llm-user.json, tmp_workspace_debug/did-key-fallback-238d1d58205943569241ca68b96e5afb.json (330 bytes) -> docs/archive/debug_snapshots/tmp_workspace_debug/did-key-fallback-238d1d58205943569241ca68b96e5afb.json, workspace/improve_temporary_session_complaint.py (554 bytes) -> docs/archive/debug_snapshots/workspace/improve_temporary_session_complaint.py, workspace/temporary-cli-session-migration/README.md (3963 bytes) -> docs/archive/debug_snapshots/workspace/temporary-cli-session-migration/README.md.
> tests/test_cimp_con_07.py hard-codes those names and byte sizes. Assert the old paths do not exist, the new files have the exact sizes, and pytest collection roots in pytest.ini do not include scripts/legacy_root_checks. Leave artifacts/ where it is.

## CIMP-CON-08 Move intake_status and workflow guidance behind thin root shims

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: CONG-relocate
- Subgoal: CONS-root-code
- Depends on: 
- Outputs: complaint_phases/intake_status.py, complaint_phases/workflow_phase_guidance.py, intake_status.py, workflow_phase_guidance.py, tests/test_cimp_con_08.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_08.py
- Acceptance: The implementation bodies live in complaint_phases and are at least 1600 and 500 lines. The root modules are shims of at most 30 lines and define no function or class.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Git mv intake_status.py to complaint_phases/intake_status.py and workflow_phase_guidance.py to complaint_phases/workflow_phase_guidance.py. Leave a root shim of at most 30 lines that only imports and re-exports the public names from the new modules. The shim must not define a function or class. Do not edit applications/document_api.py or adversarial_harness/optimizer.py in this task. Existing root imports must keep working through the shim. tests/test_cimp_con_08.py parses both root files and both new files. Assert the root files have no FunctionDef or ClassDef and are at most 30 lines, complaint_phases/intake_status.py has at least 1600 lines, and complaint_phases/workflow_phase_guidance.py has at least 500 lines. Assert build_intake_status_summary and build_workflow_phase_plan are defined in the new modules.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Git mv intake_status.py to complaint_phases/intake_status.py and workflow_phase_guidance.py to complaint_phases/workflow_phase_guidance.py.
> Leave a root shim of at most 30 lines that only imports and re-exports the public names from the new modules. The shim must not define a function or class.
> Do not edit applications/document_api.py or adversarial_harness/optimizer.py in this task. Existing root imports must keep working through the shim.
> tests/test_cimp_con_08.py parses both root files and both new files. Assert the root files have no FunctionDef or ClassDef and are at most 30 lines, complaint_phases/intake_status.py has at least 1600 lines, and complaint_phases/workflow_phase_guidance.py has at least 500 lines. Assert build_intake_status_summary and build_workflow_phase_plan are defined in the new modules.

## CIMP-CON-09 Move the document pipeline body out of the repository root

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: CONG-relocate
- Subgoal: CONS-root-code
- Depends on: 
- Outputs: complaint_phases/document_pipeline.py, document_pipeline.py, tests/test_cimp_con_09.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_09.py
- Acceptance: complaint_phases/document_pipeline.py contains the FormalComplaintDocumentBuilder body and is at least 11000 lines. The root document_pipeline.py shim is at most 30 lines and defines no class.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Git mv document_pipeline.py to complaint_phases/document_pipeline.py. Leave a root shim of at most 30 lines that re-exports the public names and defines no function or class. Do not edit mediator/mediator.py. Root imports must keep working through the shim. tests/test_cimp_con_09.py asserts the new module is at least 11000 lines and defines FormalComplaintDocumentBuilder, and the root file is at most 30 lines with no ClassDef.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Git mv document_pipeline.py to complaint_phases/document_pipeline.py.
> Leave a root shim of at most 30 lines that re-exports the public names and defines no function or class. Do not edit mediator/mediator.py. Root imports must keep working through the shim.
> tests/test_cimp_con_09.py asserts the new module is at least 11000 lines and defines FormalComplaintDocumentBuilder, and the root file is at most 30 lines with no ClassDef.

## CIMP-CON-10 Move the document optimization body out of the repository root

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: CONG-relocate
- Subgoal: CONS-root-code
- Depends on: 
- Outputs: complaint_phases/document_optimization.py, document_optimization.py, tests/test_cimp_con_10.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_10.py
- Acceptance: complaint_phases/document_optimization.py contains AgenticDocumentOptimizer and is at least 4700 lines. The root document_optimization.py shim is at most 30 lines and defines no class.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Git mv document_optimization.py to complaint_phases/document_optimization.py. Leave a root shim of at most 30 lines that re-exports the public names and defines no function or class. tests/test_cimp_con_10.py asserts the new module is at least 4700 lines and defines AgenticDocumentOptimizer, and the root file is at most 30 lines with no ClassDef.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Git mv document_optimization.py to complaint_phases/document_optimization.py.
> Leave a root shim of at most 30 lines that re-exports the public names and defines no function or class.
> tests/test_cimp_con_10.py asserts the new module is at least 4700 lines and defines AgenticDocumentOptimizer, and the root file is at most 30 lines with no ClassDef.

## CIMP-CON-11 Move the claim-support review body out of the repository root

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: CONG-relocate
- Subgoal: CONS-root-code
- Depends on: 
- Outputs: mediator/claim_support_review.py, claim_support_review.py, tests/test_cimp_con_11.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_11.py
- Acceptance: mediator/claim_support_review.py holds the review implementation and is at least 6000 lines. The root claim_support_review.py shim is at most 30 lines and defines no function.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Git mv claim_support_review.py to mediator/claim_support_review.py. Leave a root shim of at most 30 lines that re-exports the public names and defines no function or class. Do not edit mediator/mediator.py or mediator/claim_support_hooks.py. tests/test_cimp_con_11.py asserts the new module is at least 6000 lines and defines build_claim_support_review_payload, and the root file is at most 30 lines with no FunctionDef.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Git mv claim_support_review.py to mediator/claim_support_review.py.
> Leave a root shim of at most 30 lines that re-exports the public names and defines no function or class. Do not edit mediator/mediator.py or mediator/claim_support_hooks.py.
> tests/test_cimp_con_11.py asserts the new module is at least 6000 lines and defines build_claim_support_review_payload, and the root file is at most 30 lines with no FunctionDef.

## CIMP-CON-12 Make the applications interface lazily export its public symbols

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-interfaces
- Subgoal: CONS-facades
- Depends on: 
- Outputs: applications/interface.py, tests/test_cimp_con_12.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_12.py
- Acceptance: Importing applications.interface does not import applications.complaint_workspace. applications.interface.SERVER is the same object as applications.server.SERVER. An unknown attribute raises AttributeError.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  applications/interface.py is only an AST catalog. Change it so PUBLIC_SYMBOLS are real lazy exports through module __getattr__, without importing applications.complaint_workspace, mediator.mediator, or document_pipeline at import time. Keep the existing owner modules and PUBLIC_SYMBOLS. Do not add applications.complaint_workspace as an owner. tests/test_cimp_con_12.py imports applications.interface, asserts applications.complaint_workspace is not in sys.modules, asserts interface.SERVER is applications.server.SERVER, and asserts an unknown attribute raises AttributeError. Include a negative case that INTERFACE_VERSION remains 1.0.0.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> applications/interface.py is only an AST catalog. Change it so PUBLIC_SYMBOLS are real lazy exports through module __getattr__, without importing applications.complaint_workspace, mediator.mediator, or document_pipeline at import time.
> Keep the existing owner modules and PUBLIC_SYMBOLS. Do not add applications.complaint_workspace as an owner.
> tests/test_cimp_con_12.py imports applications.interface, asserts applications.complaint_workspace is not in sys.modules, asserts interface.SERVER is applications.server.SERVER, and asserts an unknown attribute raises AttributeError. Include a negative case that INTERFACE_VERSION remains 1.0.0.

## CIMP-CON-13 Export Mediator from mediator.interface and switch the small callers

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-interfaces
- Subgoal: CONS-facades
- Depends on: 
- Outputs: mediator/interface.py, main.py, examples/three_phase_example.py, examples/adversarial_harness_example.py, scripts/run_hacc_adversarial_report.py, scripts/run_hacc_preset_matrix.py, tests/test_cimp_con_13.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_13.py
- Acceptance: from mediator.interface import Mediator returns the Mediator class. main.py and the four named examples and scripts do not import mediator.mediator.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Add Mediator to mediator.interface as a lazy export of mediator.mediator.Mediator. Importing mediator.interface must not import mediator.mediator until Mediator is accessed. Change these callers to import Mediator from mediator.interface, not from mediator.mediator: main.py, examples/three_phase_example.py, examples/adversarial_harness_example.py, scripts/run_hacc_adversarial_report.py, scripts/run_hacc_preset_matrix.py. Do not edit mediator/mediator.py, mediator/hook_runtime.py, or mediator/workflow_service.py. tests/test_cimp_con_13.py parses those five callers and fails if an Import or ImportFrom names mediator.mediator. It also asserts mediator.interface.Mediator is mediator.mediator.Mediator and that a missing attribute raises AttributeError.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Add Mediator to mediator.interface as a lazy export of mediator.mediator.Mediator. Importing mediator.interface must not import mediator.mediator until Mediator is accessed.
> Change these callers to import Mediator from mediator.interface, not from mediator.mediator: main.py, examples/three_phase_example.py, examples/adversarial_harness_example.py, scripts/run_hacc_adversarial_report.py, scripts/run_hacc_preset_matrix.py.
> Do not edit mediator/mediator.py, mediator/hook_runtime.py, or mediator/workflow_service.py.
> tests/test_cimp_con_13.py parses those five callers and fails if an Import or ImportFrom names mediator.mediator. It also asserts mediator.interface.Mediator is mediator.mediator.Mediator and that a missing attribute raises AttributeError.

## CIMP-CON-14 Route hook runtime and workflow service through mediator.interface

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-interfaces
- Subgoal: CONS-callers
- Depends on: CIMP-CON-13
- Outputs: mediator/hook_runtime.py, mediator/workflow_service.py, mediator/interface.py, tests/test_cimp_con_14.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_14.py
- Acceptance: hook_runtime.py and workflow_service.py do not import mediator.mediator or mediator.claim_support_hooks. The names they need are lazy exports on mediator.interface.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  In mediator/hook_runtime.py and mediator/workflow_service.py, replace imports of mediator.mediator and mediator.claim_support_hooks with imports from mediator.interface. Extend mediator.interface with lazy exports for exactly the names those two modules need. Do not import the owner modules until an attribute is accessed. Do not edit mediator/mediator.py or mediator/claim_support_hooks.py. tests/test_cimp_con_14.py parses both callers and fails on any import whose module is mediator.mediator or mediator.claim_support_hooks. Assert each replacement import module is mediator.interface, and assert one exported name is the same object as the owner attribute.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> In mediator/hook_runtime.py and mediator/workflow_service.py, replace imports of mediator.mediator and mediator.claim_support_hooks with imports from mediator.interface.
> Extend mediator.interface with lazy exports for exactly the names those two modules need. Do not import the owner modules until an attribute is accessed. Do not edit mediator/mediator.py or mediator/claim_support_hooks.py.
> tests/test_cimp_con_14.py parses both callers and fails on any import whose module is mediator.mediator or mediator.claim_support_hooks. Assert each replacement import module is mediator.interface, and assert one exported name is the same object as the owner attribute.

## CIMP-CON-15 Route the CLI and phase manager through the complaint_phases interface

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-interfaces
- Subgoal: CONS-facades
- Depends on: 
- Outputs: complaint_phases/interface.py, applications/complaint_cli.py, complaint_phases/phase_manager.py, tests/test_cimp_con_15.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_15.py
- Acceptance: complaint_cli.py and phase_manager.py do not import complaint_phases.denoiser. complaint_phases.interface.ComplaintDenoiser is the denoiser class, loaded lazily.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Make complaint_phases/interface.py lazily export ComplaintDenoiser, project_stopping_policy, publish_authorized_dependency_action, and format_terminal_why from complaint_phases.denoiser. Importing the interface must not import the denoiser module. Change applications/complaint_cli.py and complaint_phases/phase_manager.py to import those names from complaint_phases.interface. Do not edit complaint_phases/denoiser.py. tests/test_cimp_con_15.py parses the two callers and fails if they import complaint_phases.denoiser. Assert the interface attribute ComplaintDenoiser is complaint_phases.denoiser.ComplaintDenoiser, and assert the denoiser module was absent from sys.modules immediately after importing the interface and before the attribute access.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Make complaint_phases/interface.py lazily export ComplaintDenoiser, project_stopping_policy, publish_authorized_dependency_action, and format_terminal_why from complaint_phases.denoiser. Importing the interface must not import the denoiser module.
> Change applications/complaint_cli.py and complaint_phases/phase_manager.py to import those names from complaint_phases.interface. Do not edit complaint_phases/denoiser.py.
> tests/test_cimp_con_15.py parses the two callers and fails if they import complaint_phases.denoiser. Assert the interface attribute ComplaintDenoiser is complaint_phases.denoiser.ComplaintDenoiser, and assert the denoiser module was absent from sys.modules immediately after importing the interface and before the attribute access.

## CIMP-CON-16 Point document and review callers at versioned surfaces

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-interfaces
- Subgoal: CONS-callers
- Depends on: CIMP-CON-08, CIMP-CON-09, CIMP-CON-10, CIMP-CON-11, CIMP-CON-14
- Outputs: complaint_phases/document_surface.py, applications/document_api.py, applications/review_api.py, adversarial_harness/optimizer.py, mediator/interface.py, tests/test_cimp_con_16.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_16.py
- Acceptance: document_api.py does not import the root modules document_pipeline, document_optimization, intake_status, or workflow_phase_guidance. review_api.py does not import the root module claim_support_review. optimizer.py does not import the root module workflow_phase_guidance. complaint_phases.document_surface exposes the moved document entry points lazily at interface version 1.0.0.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Create complaint_phases/document_surface.py with INTERFACE_SCHEMA and INTERFACE_VERSION 1.0.0. Lazily export the public entry points that applications/document_api.py and adversarial_harness/optimizer.py currently import from the root modules, from their new complaint_phases modules. Change applications/document_api.py and adversarial_harness/optimizer.py to import those names from complaint_phases.document_surface. Change applications/review_api.py to import its claim-support review names from mediator.interface, and add those names as lazy exports on mediator.interface from mediator.claim_support_review. Do not import mediator.claim_support_review at interface import time. tests/test_cimp_con_16.py parses the three callers and fails if they import document_pipeline, document_optimization, intake_status, workflow_phase_guidance, or claim_support_review as top-level modules. Assert one document_surface attribute is the same object as the complaint_phases owner attribute.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Create complaint_phases/document_surface.py with INTERFACE_SCHEMA and INTERFACE_VERSION 1.0.0. Lazily export the public entry points that applications/document_api.py and adversarial_harness/optimizer.py currently import from the root modules, from their new complaint_phases modules.
> Change applications/document_api.py and adversarial_harness/optimizer.py to import those names from complaint_phases.document_surface.
> Change applications/review_api.py to import its claim-support review names from mediator.interface, and add those names as lazy exports on mediator.interface from mediator.claim_support_review. Do not import mediator.claim_support_review at interface import time.
> tests/test_cimp_con_16.py parses the three callers and fails if they import document_pipeline, document_optimization, intake_status, workflow_phase_guidance, or claim_support_review as top-level modules. Assert one document_surface attribute is the same object as the complaint_phases owner attribute.

## CIMP-CON-17 Extract the large claim-support review builders

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-extract
- Subgoal: CONS-moved-bodies
- Depends on: CIMP-CON-11
- Outputs: mediator/claim_support_review.py, mediator/claim_support_review_sections.py, tests/test_cimp_con_17.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_17.py
- Acceptance: mediator/claim_support_review_sections.py defines the extracted names and is at least 1600 lines. mediator/claim_support_review.py is at most 4700 lines. The owner module no longer defines those functions. summarize_follow_up_history_claim is still defined in the owner.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  The root shim must stay a shim. Edit the moved body at mediator/claim_support_review.py. Move module-level functions _build_review_workflow_priority, summarize_claim_reasoning_review, build_claim_support_review_payload into mediator/claim_support_review_sections.py. The owner module must import those names and must not define them again. Leave summarize_follow_up_history_claim defined in the owner. The owner file must end at or under 4700 lines. mediator/claim_support_review_sections.py must be at least 1600 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract. Write tests/test_cimp_con_17.py to parse both files with ast. The owner module no longer defines those functions. summarize_follow_up_history_claim is still defined in the owner. Assert the owner line count is <= 4700 and the new module line count is >= 1600. Assert each extracted name is defined in the new module.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> The root shim must stay a shim. Edit the moved body at mediator/claim_support_review.py.
> Move module-level functions _build_review_workflow_priority, summarize_claim_reasoning_review, build_claim_support_review_payload into mediator/claim_support_review_sections.py. The owner module must import those names and must not define them again. Leave summarize_follow_up_history_claim defined in the owner.
> The owner file must end at or under 4700 lines. mediator/claim_support_review_sections.py must be at least 1600 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract.
> Write tests/test_cimp_con_17.py to parse both files with ast. The owner module no longer defines those functions. summarize_follow_up_history_claim is still defined in the owner. Assert the owner line count is <= 4700 and the new module line count is >= 1600. Assert each extracted name is defined in the new module.

## CIMP-CON-18 Extract document-pipeline guidance functions

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-extract
- Subgoal: CONS-moved-bodies
- Depends on: CIMP-CON-09
- Outputs: complaint_phases/document_pipeline.py, complaint_phases/document_pipeline_guidance.py, tests/test_cimp_con_18.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_18.py
- Acceptance: complaint_phases/document_pipeline_guidance.py defines the extracted names and is at least 800 lines. complaint_phases/document_pipeline.py is at most 11200 lines. The owner module no longer defines those functions. _extract_latest_adversarial_priority_findings is still defined in the owner.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Edit the moved body. Leave FormalComplaintDocumentBuilder in complaint_phases/document_pipeline.py. Move module-level functions _build_runtime_workflow_optimization_guidance, build_drafting_guardrails, build_drafting_support_bundles, _build_anchored_chronology_summary_from_case_file into complaint_phases/document_pipeline_guidance.py. The owner module must import those names and must not define them again. Leave _extract_latest_adversarial_priority_findings defined in the owner. The owner file must end at or under 11200 lines. complaint_phases/document_pipeline_guidance.py must be at least 800 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract. Write tests/test_cimp_con_18.py to parse both files with ast. The owner module no longer defines those functions. _extract_latest_adversarial_priority_findings is still defined in the owner. Assert the owner line count is <= 11200 and the new module line count is >= 800. Assert each extracted name is defined in the new module.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Edit the moved body. Leave FormalComplaintDocumentBuilder in complaint_phases/document_pipeline.py.
> Move module-level functions _build_runtime_workflow_optimization_guidance, build_drafting_guardrails, build_drafting_support_bundles, _build_anchored_chronology_summary_from_case_file into complaint_phases/document_pipeline_guidance.py. The owner module must import those names and must not define them again. Leave _extract_latest_adversarial_priority_findings defined in the owner.
> The owner file must end at or under 11200 lines. complaint_phases/document_pipeline_guidance.py must be at least 800 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract.
> Write tests/test_cimp_con_18.py to parse both files with ast. The owner module no longer defines those functions. _extract_latest_adversarial_priority_findings is still defined in the owner. Assert the owner line count is <= 11200 and the new module line count is >= 800. Assert each extracted name is defined in the new module.

## CIMP-CON-19 Delegate document-pipeline readiness methods to a sibling module

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-extract
- Subgoal: CONS-moved-bodies
- Depends on: CIMP-CON-18
- Outputs: complaint_phases/document_pipeline.py, complaint_phases/document_pipeline_readiness.py, tests/test_cimp_con_19.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_19.py
- Acceptance: complaint_phases/document_pipeline_readiness.py defines the extracted names and is at least 950 lines. complaint_phases/document_pipeline.py is at most 10200 lines. Each extracted method has exactly one statement and it is a Return of a Call. build_package remains a method on the class.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Extract those two FormalComplaintDocumentBuilder methods only. The guidance module from CIMP-CON-18 must remain. On class methods _build_drafting_readiness, _build_intake_questioning_phase_guidance, replace each body with exactly one Return of a call to a function of the same name in complaint_phases/document_pipeline_readiness.py. The extracted function performs the old body. Leave build_package defined on the class and do not extract it. The owner file must end at or under 10200 lines. complaint_phases/document_pipeline_readiness.py must be at least 950 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract. Write tests/test_cimp_con_19.py to parse both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. build_package remains a method on the class. Assert the owner line count is <= 10200 and the new module line count is >= 950. Assert each extracted name is defined in the new module.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Extract those two FormalComplaintDocumentBuilder methods only. The guidance module from CIMP-CON-18 must remain.
> On class methods _build_drafting_readiness, _build_intake_questioning_phase_guidance, replace each body with exactly one Return of a call to a function of the same name in complaint_phases/document_pipeline_readiness.py. The extracted function performs the old body. Leave build_package defined on the class and do not extract it.
> The owner file must end at or under 10200 lines. complaint_phases/document_pipeline_readiness.py must be at least 950 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract.
> Write tests/test_cimp_con_19.py to parse both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. build_package remains a method on the class. Assert the owner line count is <= 10200 and the new module line count is >= 950. Assert each extracted name is defined in the new module.

## CIMP-CON-20 Extract document-optimization summary functions

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-extract
- Subgoal: CONS-moved-bodies
- Depends on: CIMP-CON-10
- Outputs: complaint_phases/document_optimization.py, complaint_phases/document_optimization_summaries.py, tests/test_cimp_con_20.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_20.py
- Acceptance: complaint_phases/document_optimization_summaries.py defines the extracted names and is at least 650 lines. complaint_phases/document_optimization.py is at most 4200 lines. The owner module no longer defines those functions. AgenticDocumentOptimizer is still defined in the owner.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  These are module-level functions. Leave class AgenticDocumentOptimizer, including optimize_draft, in the owner. Move module-level functions _build_claim_support_temporal_handoff, _build_claim_reasoning_theorem_export_metadata, _build_anchored_chronology_summary, _build_document_grounding_improvement_summary, _build_document_grounding_lane_outcome_summary, _build_claim_temporal_gap_hints, _build_workflow_targeting_summary into complaint_phases/document_optimization_summaries.py. The owner module must import those names and must not define them again. Leave AgenticDocumentOptimizer defined in the owner. The owner file must end at or under 4200 lines. complaint_phases/document_optimization_summaries.py must be at least 650 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract. Write tests/test_cimp_con_20.py to parse both files with ast. The owner module no longer defines those functions. AgenticDocumentOptimizer is still defined in the owner. Assert the owner line count is <= 4200 and the new module line count is >= 650. Assert each extracted name is defined in the new module.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> These are module-level functions. Leave class AgenticDocumentOptimizer, including optimize_draft, in the owner.
> Move module-level functions _build_claim_support_temporal_handoff, _build_claim_reasoning_theorem_export_metadata, _build_anchored_chronology_summary, _build_document_grounding_improvement_summary, _build_document_grounding_lane_outcome_summary, _build_claim_temporal_gap_hints, _build_workflow_targeting_summary into complaint_phases/document_optimization_summaries.py. The owner module must import those names and must not define them again. Leave AgenticDocumentOptimizer defined in the owner.
> The owner file must end at or under 4200 lines. complaint_phases/document_optimization_summaries.py must be at least 650 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract.
> Write tests/test_cimp_con_20.py to parse both files with ast. The owner module no longer defines those functions. AgenticDocumentOptimizer is still defined in the owner. Assert the owner line count is <= 4200 and the new module line count is >= 650. Assert each extracted name is defined in the new module.

## CIMP-CON-21 Delegate complaint workspace draft methods to a sibling module

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-extract
- Subgoal: CONS-package-giants
- Depends on: 
- Outputs: applications/complaint_workspace.py, applications/complaint_workspace_drafting.py, tests/test_cimp_con_21.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_21.py
- Acceptance: applications/complaint_workspace_drafting.py defines the extracted names and is at least 1250 lines. applications/complaint_workspace.py is at most 18300 lines. Each extracted method has exactly one statement and it is a Return of a Call. improve_draft remains a method on the class.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Extract only those four ComplaintWorkspaceService methods. Do not edit applications/interface.py. On class methods _build_draft, _analyze_complaint_output, sync_mike_final_draft, build_mike_handoff, replace each body with exactly one Return of a call to a function of the same name in applications/complaint_workspace_drafting.py. The extracted function performs the old body. Leave improve_draft defined on the class and do not extract it. The owner file must end at or under 18300 lines. applications/complaint_workspace_drafting.py must be at least 1250 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract. Write tests/test_cimp_con_21.py to parse both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. improve_draft remains a method on the class. Assert the owner line count is <= 18300 and the new module line count is >= 1250. Assert each extracted name is defined in the new module.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Extract only those four ComplaintWorkspaceService methods. Do not edit applications/interface.py.
> On class methods _build_draft, _analyze_complaint_output, sync_mike_final_draft, build_mike_handoff, replace each body with exactly one Return of a call to a function of the same name in applications/complaint_workspace_drafting.py. The extracted function performs the old body. Leave improve_draft defined on the class and do not extract it.
> The owner file must end at or under 18300 lines. applications/complaint_workspace_drafting.py must be at least 1250 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract.
> Write tests/test_cimp_con_21.py to parse both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. improve_draft remains a method on the class. Assert the owner line count is <= 18300 and the new module line count is >= 1250. Assert each extracted name is defined in the new module.

## CIMP-CON-22 Delegate mediator intake-question methods to a sibling module

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-extract
- Subgoal: CONS-package-giants
- Depends on: 
- Outputs: mediator/mediator.py, mediator/intake_question_flow.py, tests/test_cimp_con_22.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_22.py
- Acceptance: mediator/intake_question_flow.py defines the extracted names and is at least 1450 lines. mediator/mediator.py is at most 13600 lines. Each extracted method has exactly one statement and it is a Return of a Call. research_case_automatically remains a method on the class.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Extract only those four Mediator methods. Do not edit mediator/interface.py, hook_runtime.py, or workflow_service.py. On class methods _summarize_intake_evidence_alignment, _annotate_intake_question_candidate, select_intake_question_candidates, process_denoising_answer, replace each body with exactly one Return of a call to a function of the same name in mediator/intake_question_flow.py. The extracted function performs the old body. Leave research_case_automatically defined on the class and do not extract it. The owner file must end at or under 13600 lines. mediator/intake_question_flow.py must be at least 1450 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract. Write tests/test_cimp_con_22.py to parse both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. research_case_automatically remains a method on the class. Assert the owner line count is <= 13600 and the new module line count is >= 1450. Assert each extracted name is defined in the new module.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Extract only those four Mediator methods. Do not edit mediator/interface.py, hook_runtime.py, or workflow_service.py.
> On class methods _summarize_intake_evidence_alignment, _annotate_intake_question_candidate, select_intake_question_candidates, process_denoising_answer, replace each body with exactly one Return of a call to a function of the same name in mediator/intake_question_flow.py. The extracted function performs the old body. Leave research_case_automatically defined on the class and do not extract it.
> The owner file must end at or under 13600 lines. mediator/intake_question_flow.py must be at least 1450 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract.
> Write tests/test_cimp_con_22.py to parse both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. research_case_automatically remains a method on the class. Assert the owner line count is <= 13600 and the new module line count is >= 1450. Assert each extracted name is defined in the new module.

## CIMP-CON-23 Delegate denoiser question-selection methods to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-extract
- Subgoal: CONS-package-giants
- Depends on: 
- Outputs: complaint_phases/denoiser.py, complaint_phases/denoiser_questions.py, tests/test_cimp_con_23.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_23.py
- Acceptance: complaint_phases/denoiser_questions.py defines the extracted names and is at least 1000 lines. complaint_phases/denoiser.py is at most 7900 lines. Each extracted method has exactly one statement and it is a Return of a Call. select_question_candidates remains a method on the class.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Extract only those four ComplaintDenoiser methods. Do not move process_answer. Do not edit complaint_phases/interface.py. On class methods generate_evidence_questions, evaluate_interview_stop, collect_question_candidates, _build_history_follow_up_questions, replace each body with exactly one Return of a call to a function of the same name in complaint_phases/denoiser_questions.py. The extracted function performs the old body. Leave select_question_candidates defined on the class and do not extract it. The owner file must end at or under 7900 lines. complaint_phases/denoiser_questions.py must be at least 1000 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract. Write tests/test_cimp_con_23.py to parse both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. select_question_candidates remains a method on the class. Assert the owner line count is <= 7900 and the new module line count is >= 1000. Assert each extracted name is defined in the new module.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Extract only those four ComplaintDenoiser methods. Do not move process_answer. Do not edit complaint_phases/interface.py.
> On class methods generate_evidence_questions, evaluate_interview_stop, collect_question_candidates, _build_history_follow_up_questions, replace each body with exactly one Return of a call to a function of the same name in complaint_phases/denoiser_questions.py. The extracted function performs the old body. Leave select_question_candidates defined on the class and do not extract it.
> The owner file must end at or under 7900 lines. complaint_phases/denoiser_questions.py must be at least 1000 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract.
> Write tests/test_cimp_con_23.py to parse both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. select_question_candidates remains a method on the class. Assert the owner line count is <= 7900 and the new module line count is >= 1000. Assert each extracted name is defined in the new module.

## CIMP-CON-24 Delegate claim-support hook diagnostics to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: CONG-extract
- Subgoal: CONS-package-giants
- Depends on: 
- Outputs: mediator/claim_support_hooks.py, mediator/claim_support_diagnostics.py, tests/test_cimp_con_24.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_24.py
- Acceptance: mediator/claim_support_diagnostics.py defines the extracted names and is at least 1050 lines. mediator/claim_support_hooks.py is at most 9600 lines. Each extracted method has exactly one statement and it is a Return of a Call. upsert_support_link remains a method on the class.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Extract only those three ClaimSupportHook methods. Do not edit mediator/hook_runtime.py. On class methods _run_element_reasoning_diagnostics, _build_temporal_proof_bundle, _get_temporal_reasoning_context, replace each body with exactly one Return of a call to a function of the same name in mediator/claim_support_diagnostics.py. The extracted function performs the old body. Leave upsert_support_link defined on the class and do not extract it. The owner file must end at or under 9600 lines. mediator/claim_support_diagnostics.py must be at least 1050 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract. Write tests/test_cimp_con_24.py to parse both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. upsert_support_link remains a method on the class. Assert the owner line count is <= 9600 and the new module line count is >= 1050. Assert each extracted name is defined in the new module.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Extract only those three ClaimSupportHook methods. Do not edit mediator/hook_runtime.py.
> On class methods _run_element_reasoning_diagnostics, _build_temporal_proof_bundle, _get_temporal_reasoning_context, replace each body with exactly one Return of a call to a function of the same name in mediator/claim_support_diagnostics.py. The extracted function performs the old body. Leave upsert_support_link defined on the class and do not extract it.
> The owner file must end at or under 9600 lines. mediator/claim_support_diagnostics.py must be at least 1050 lines. Do not satisfy the floor by deleting comments or docstrings from functions you did not extract.
> Write tests/test_cimp_con_24.py to parse both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. upsert_support_link remains a method on the class. Assert the owner line count is <= 9600 and the new module line count is >= 1050. Assert each extracted name is defined in the new module.

## CIMP-CON-25 Rewrite the root docs so they describe the moved tree

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P2
- Goal: CONG-docs
- Subgoal: CONS-current-docs
- Depends on: CIMP-CON-05, CIMP-CON-06, CIMP-CON-07, CIMP-CON-08, CIMP-CON-09, CIMP-CON-10, CIMP-CON-11, CIMP-CON-12, CIMP-CON-13, CIMP-CON-14, CIMP-CON-15, CIMP-CON-16, CIMP-CON-17, CIMP-CON-18, CIMP-CON-19, CIMP-CON-20, CIMP-CON-21, CIMP-CON-22, CIMP-CON-23, CIMP-CON-24
- Outputs: README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, docs/architecture/consolidation_modules.md, tests/test_cimp_con_25.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_25.py
- Acceptance: Every relative link in README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, and TESTING.md resolves to a file. Those docs name docs/archive/sessions, docs/archive/reports, and the moved module paths, and they do not link a bare archived filename at the repository root. The repository root has only README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, and TODO.md as markdown files.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Rewrite README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, and TESTING.md so a reader can find the code after this consolidation. Say that session reports live in docs/archive/sessions, plans and profiles live in docs/archive/reports, and the document pipeline, document optimization, intake status, and workflow guidance bodies live in complaint_phases with root shims. Say claim-support review lives in mediator/claim_support_review.py. Name INTERFACE_SCHEMA complaint-generator/module-interface@1 and INTERFACE_VERSION 1.0.0. The Git remote is endomorphosis/complaint-generator. Write docs/architecture/consolidation_modules.md listing every sibling module this campaign extracted and the owner it was extracted from. tests/test_cimp_con_25.py resolves every relative markdown link in the four root docs and fails if any target is missing. It fails if the root contains any markdown file other than README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md. It fails if any of those docs contains a markdown link whose target is only one of these bare names: AUTONOMOUS_SESSION_REPORT.md, BATCH_254_258_SESSION_SUMMARY.md, BATCH_305_306_SESSION_SUMMARY.md, BATCH_328_API_RETURN_TYPES_SUMMARY.md, BATCH_329_EXCEPTION_HANDLING_SUMMARY.md, BENCHMARK_SUITE_SESSION_SUMMARY.md, ITEM_7_COMPLETION_SUMMARY.md, P3_INFRASTRUCTURE_COMPLETION_SESSION.md, P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md, PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md, PHASE_2_COMPLETION_SUMMARY.md, QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md, QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md, README_OLD.md, README_OLD_BACKUP.md, README_OLD_FULL.md, SESSION_3_COMPLETE_SUMMARY.md, SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md, SESSION_84_FINAL_SUMMARY.md, SESSION_84_PHASE4_EXTENDED_SUMMARY.md, SESSION_84_PHASE4_SUMMARY.md, SESSION_84_PROGRESS.md, SESSION_SUMMARY_2024_02_24.md, SESSION_SUMMARY_2026_02_23.md, SESSION_SUMMARY_2026_02_24_COMPLETE.md, SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md, SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md, AUDIT_DICT_RETURNS_REPORT.md, BATCH_202_PLAN.md, EXTRACTION_PIPELINE_PROFILE_FINAL.md, PARALLEL_VALIDATION_FIX_REPORT.md, UNIFIED_PERFORMANCE_ANALYSIS.md, plan-mcpPlusPlusIntegration.prompt.md. It fails if consolidation_modules.md does not name each extracted sibling module.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Rewrite README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, and TESTING.md so a reader can find the code after this consolidation.
> Say that session reports live in docs/archive/sessions, plans and profiles live in docs/archive/reports, and the document pipeline, document optimization, intake status, and workflow guidance bodies live in complaint_phases with root shims. Say claim-support review lives in mediator/claim_support_review.py. Name INTERFACE_SCHEMA complaint-generator/module-interface@1 and INTERFACE_VERSION 1.0.0. The Git remote is endomorphosis/complaint-generator.
> Write docs/architecture/consolidation_modules.md listing every sibling module this campaign extracted and the owner it was extracted from.
> tests/test_cimp_con_25.py resolves every relative markdown link in the four root docs and fails if any target is missing. It fails if the root contains any markdown file other than README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md. It fails if any of those docs contains a markdown link whose target is only one of these bare names: AUTONOMOUS_SESSION_REPORT.md, BATCH_254_258_SESSION_SUMMARY.md, BATCH_305_306_SESSION_SUMMARY.md, BATCH_328_API_RETURN_TYPES_SUMMARY.md, BATCH_329_EXCEPTION_HANDLING_SUMMARY.md, BENCHMARK_SUITE_SESSION_SUMMARY.md, ITEM_7_COMPLETION_SUMMARY.md, P3_INFRASTRUCTURE_COMPLETION_SESSION.md, P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md, PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md, PHASE_2_COMPLETION_SUMMARY.md, QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md, QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md, README_OLD.md, README_OLD_BACKUP.md, README_OLD_FULL.md, SESSION_3_COMPLETE_SUMMARY.md, SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md, SESSION_84_FINAL_SUMMARY.md, SESSION_84_PHASE4_EXTENDED_SUMMARY.md, SESSION_84_PHASE4_SUMMARY.md, SESSION_84_PROGRESS.md, SESSION_SUMMARY_2024_02_24.md, SESSION_SUMMARY_2026_02_23.md, SESSION_SUMMARY_2026_02_24_COMPLETE.md, SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md, SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md, AUDIT_DICT_RETURNS_REPORT.md, BATCH_202_PLAN.md, EXTRACTION_PIPELINE_PROFILE_FINAL.md, PARALLEL_VALIDATION_FIX_REPORT.md, UNIFIED_PERFORMANCE_ANALYSIS.md, plan-mcpPlusPlusIntegration.prompt.md. It fails if consolidation_modules.md does not name each extracted sibling module.

## CIMP-CON-26 Enforce the consolidation ratchet independently of earlier helpers

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: CONG-closure
- Subgoal: CONS-ratchet
- Depends on: CIMP-CON-25
- Outputs: tests/test_cimp_con_26.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_con_26.py
- Acceptance: The root markdown set is exactly the five current docs, and every archived file is absent at the root and present in its archive at the recorded size. Root Python files are only main.py, run.py, setup.py, and the five shims of at most 30 lines. Owner modules are at or under their line floors and the extracted sibling modules are at or over their minimums. The named production callers do not import the forbidden giant or root modules.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". Use git mv for tracked moves so the bytes stay identical.  Write tests/test_cimp_con_26.py as a standalone ratchet. Do not import helpers from tests/test_cimp_mod_19.py or earlier CIMP-CON tests. Hard-code the names, byte sizes, and line floors from this prompt. If the tree fails a check, fix the tree. Do not relax the check. Root markdown must be exactly README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md. Session files and sizes: AUTONOMOUS_SESSION_REPORT.md 14822, BATCH_254_258_SESSION_SUMMARY.md 15081, BATCH_305_306_SESSION_SUMMARY.md 6799, BATCH_328_API_RETURN_TYPES_SUMMARY.md 11564, BATCH_329_EXCEPTION_HANDLING_SUMMARY.md 11919, BENCHMARK_SUITE_SESSION_SUMMARY.md 10574, ITEM_7_COMPLETION_SUMMARY.md 9658, P3_INFRASTRUCTURE_COMPLETION_SESSION.md 6935, P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md 8334, PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md 10410, PHASE_2_COMPLETION_SUMMARY.md 5565, QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md 7895, QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md 15427, README_OLD.md 817, README_OLD_BACKUP.md 16697, README_OLD_FULL.md 30925, SESSION_3_COMPLETE_SUMMARY.md 12676, SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md 8397, SESSION_84_FINAL_SUMMARY.md 7741, SESSION_84_PHASE4_EXTENDED_SUMMARY.md 17752, SESSION_84_PHASE4_SUMMARY.md 13483, SESSION_84_PROGRESS.md 13783, SESSION_SUMMARY_2024_02_24.md 10746, SESSION_SUMMARY_2026_02_23.md 8389, SESSION_SUMMARY_2026_02_24_COMPLETE.md 13118, SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md 5478, SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md 8261. Each must be absent at the root and present at docs/archive/sessions with that size. Both archive INDEX.md files must have zero unresolved relative links. Report files and sizes: AUDIT_DICT_RETURNS_REPORT.md 3979, BATCH_202_PLAN.md 4452, EXTRACTION_PIPELINE_PROFILE_FINAL.md 10708, PARALLEL_VALIDATION_FIX_REPORT.md 4095, UNIFIED_PERFORMANCE_ANALYSIS.md 12002, plan-mcpPlusPlusIntegration.prompt.md 6459 under docs/archive/reports. Debug snapshots and sizes: tmp_validation_llm_draft/validation-user.json 9642, tmp_validation_llm_enabled/llm-user.json 9602, tmp_workspace_debug/did-key-fallback-238d1d58205943569241ca68b96e5afb.json 330, workspace/improve_temporary_session_complaint.py 554, workspace/temporary-cli-session-migration/README.md 3963 under docs/archive/debug_snapshots with the same relative tails, and the old paths must be gone. Maintenance scripts add_dedup_factory.py, add_init_vars.py, add_optimization_methods.py, batch_230_benchmark.py, batch_231_llm_fallback_profile.py, complete_optimizer_integration.py, profile_generate_10k.py, update_detect_graph_type.py must be under scripts/maintenance and absent at the root. Legacy checks test_complaint_mcp_protocol.py, test_criticscor_comparisons.py, test_extraction_config_validation.py, test_main_app_surface.py, test_parallel_validation_fix.py, test_pipeline_error_recovery.py, test_probate_integration.py must be under scripts/legacy_root_checks and absent at the root. Root Python files must be only main.py, run.py, setup.py, intake_status.py, workflow_phase_guidance.py, document_pipeline.py, document_optimization.py, claim_support_review.py. Each shim must be at most 30 lines and must define no function or class. Line floors, owner <= N and sibling >= M: complaint_phases/document_pipeline.py <= 10200 and document_pipeline_readiness.py >= 950; complaint_phases/document_pipeline_guidance.py >= 800; complaint_phases/document_optimization.py <= 4200 and document_optimization_summaries.py >= 650; mediator/claim_support_review.py <= 4700 and claim_support_review_sections.py >= 1600; applications/complaint_workspace.py <= 18300 and complaint_workspace_drafting.py >= 1250; mediator/mediator.py <= 13600 and intake_question_flow.py >= 1450; complaint_phases/denoiser.py <= 7900 and denoiser_questions.py >= 1000; mediator/claim_support_hooks.py <= 9600 and claim_support_diagnostics.py >= 1050. Parse these callers and fail on a forbidden import module: main.py forbids mediator.mediator; mediator/hook_runtime.py and mediator/workflow_service.py forbid mediator.mediator and mediator.claim_support_hooks; applications/complaint_cli.py and complaint_phases/phase_manager.py forbid complaint_phases.denoiser; applications/document_api.py forbids document_pipeline, document_optimization, intake_status, and workflow_phase_guidance; applications/review_api.py forbids claim_support_review; adversarial_harness/optimizer.py forbids workflow_phase_guidance. Assert applications.interface.SERVER, mediator.interface.Mediator, and complaint_phases.interface.ComplaintDenoiser are the owner objects. This task grants no completion authority and must not edit external/.

Implementation instructions:

> Preserve behavior with shims. Move or extract the named code. A catalog, an index of files that are still at the old path, or a test that allows the old path to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor or a byte size in this prompt.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is edited, keep INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> Use git mv for tracked moves so the bytes stay identical.
> 
> Write tests/test_cimp_con_26.py as a standalone ratchet. Do not import helpers from tests/test_cimp_mod_19.py or earlier CIMP-CON tests. Hard-code the names, byte sizes, and line floors from this prompt. If the tree fails a check, fix the tree. Do not relax the check.
> Root markdown must be exactly README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md.
> Session files and sizes: AUTONOMOUS_SESSION_REPORT.md 14822, BATCH_254_258_SESSION_SUMMARY.md 15081, BATCH_305_306_SESSION_SUMMARY.md 6799, BATCH_328_API_RETURN_TYPES_SUMMARY.md 11564, BATCH_329_EXCEPTION_HANDLING_SUMMARY.md 11919, BENCHMARK_SUITE_SESSION_SUMMARY.md 10574, ITEM_7_COMPLETION_SUMMARY.md 9658, P3_INFRASTRUCTURE_COMPLETION_SESSION.md 6935, P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md 8334, PERFORMANCE_OPTIMIZATION_SESSION_COMPLETE.md 10410, PHASE_2_COMPLETION_SUMMARY.md 5565, QUERY_OPTIMIZER_INTEGRATION_SESSION_WIP.md 7895, QUERY_OPTIMIZER_MODULARIZATION_COMPLETION.md 15427, README_OLD.md 817, README_OLD_BACKUP.md 16697, README_OLD_FULL.md 30925, SESSION_3_COMPLETE_SUMMARY.md 12676, SESSION_4_QUERY_OPTIMIZER_INTEGRATION_COMPLETE.md 8397, SESSION_84_FINAL_SUMMARY.md 7741, SESSION_84_PHASE4_EXTENDED_SUMMARY.md 17752, SESSION_84_PHASE4_SUMMARY.md 13483, SESSION_84_PROGRESS.md 13783, SESSION_SUMMARY_2024_02_24.md 10746, SESSION_SUMMARY_2026_02_23.md 8389, SESSION_SUMMARY_2026_02_24_COMPLETE.md 13118, SESSION_SUMMARY_PERFORMANCE_CYCLE_2.md 5478, SESSION_SUMMARY_PERFORMANCE_PROFILING_PROGRESS.md 8261. Each must be absent at the root and present at docs/archive/sessions with that size. Both archive INDEX.md files must have zero unresolved relative links.
> Report files and sizes: AUDIT_DICT_RETURNS_REPORT.md 3979, BATCH_202_PLAN.md 4452, EXTRACTION_PIPELINE_PROFILE_FINAL.md 10708, PARALLEL_VALIDATION_FIX_REPORT.md 4095, UNIFIED_PERFORMANCE_ANALYSIS.md 12002, plan-mcpPlusPlusIntegration.prompt.md 6459 under docs/archive/reports.
> Debug snapshots and sizes: tmp_validation_llm_draft/validation-user.json 9642, tmp_validation_llm_enabled/llm-user.json 9602, tmp_workspace_debug/did-key-fallback-238d1d58205943569241ca68b96e5afb.json 330, workspace/improve_temporary_session_complaint.py 554, workspace/temporary-cli-session-migration/README.md 3963 under docs/archive/debug_snapshots with the same relative tails, and the old paths must be gone.
> Maintenance scripts add_dedup_factory.py, add_init_vars.py, add_optimization_methods.py, batch_230_benchmark.py, batch_231_llm_fallback_profile.py, complete_optimizer_integration.py, profile_generate_10k.py, update_detect_graph_type.py must be under scripts/maintenance and absent at the root. Legacy checks test_complaint_mcp_protocol.py, test_criticscor_comparisons.py, test_extraction_config_validation.py, test_main_app_surface.py, test_parallel_validation_fix.py, test_pipeline_error_recovery.py, test_probate_integration.py must be under scripts/legacy_root_checks and absent at the root.
> Root Python files must be only main.py, run.py, setup.py, intake_status.py, workflow_phase_guidance.py, document_pipeline.py, document_optimization.py, claim_support_review.py. Each shim must be at most 30 lines and must define no function or class.
> Line floors, owner <= N and sibling >= M: complaint_phases/document_pipeline.py <= 10200 and document_pipeline_readiness.py >= 950; complaint_phases/document_pipeline_guidance.py >= 800; complaint_phases/document_optimization.py <= 4200 and document_optimization_summaries.py >= 650; mediator/claim_support_review.py <= 4700 and claim_support_review_sections.py >= 1600; applications/complaint_workspace.py <= 18300 and complaint_workspace_drafting.py >= 1250; mediator/mediator.py <= 13600 and intake_question_flow.py >= 1450; complaint_phases/denoiser.py <= 7900 and denoiser_questions.py >= 1000; mediator/claim_support_hooks.py <= 9600 and claim_support_diagnostics.py >= 1050.
> Parse these callers and fail on a forbidden import module: main.py forbids mediator.mediator; mediator/hook_runtime.py and mediator/workflow_service.py forbid mediator.mediator and mediator.claim_support_hooks; applications/complaint_cli.py and complaint_phases/phase_manager.py forbid complaint_phases.denoiser; applications/document_api.py forbids document_pipeline, document_optimization, intake_status, and workflow_phase_guidance; applications/review_api.py forbids claim_support_review; adversarial_harness/optimizer.py forbids workflow_phase_guidance.
> Assert applications.interface.SERVER, mediator.interface.Mediator, and complaint_phases.interface.ComplaintDenoiser are the owner objects. This task grants no completion authority and must not edit external/.
