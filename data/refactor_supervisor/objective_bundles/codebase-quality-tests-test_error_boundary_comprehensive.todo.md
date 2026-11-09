# Codebase Bundle: codebase/quality/tests-test_error_boundary_comprehensive

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-297 Review swallowed exception path in tests/test_error_boundary_comprehensive.py:79

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/test_error_boundary_comprehensive.py
- Validation: python3 -m py_compile tests/test_error_boundary_comprehensive.py
- Bundle: codebase/quality/tests-test_error_boundary_comprehensive
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-test_error_boundary_comprehensive.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-test_error_boundary_comprehensive
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/test_error_boundary_comprehensive.py
- AST symbols: ipfs datasets py optimizers graphrag ontology generator, ipfs datasets py optimizers graphrag ontology generator ontologygenerationcontext, ipfs datasets py optimizers graphrag ontology generator ontologygenerator, ipfs_datasets_py.optimizers.graphrag.ontology_generator, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerationcontext, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerator, pytest, test concurrent context usage, test control characters, test deeply nested relationships, test degradation with corrupted input, test degradation with invalid domain, test domain case sensitivity, test empty text handling, test entities always list, test maximum entity count, test metadata contains info, test mixed script input, test multiple sequential errors, test no corrupt output, test null bytes in text, test numeric text input, test rapid sequential processing, test recovery after error, test relationships always list, test result has valid structure, test single character input, test single word input, test special characters only, test special chars in source, test unicode text input, test unknown domain, test very long input, test whitespace only handling, test_concurrent_context_usage, test_control_characters, test_deeply_nested_relationships, test_degradation_with_corrupted_input, test_degradation_with_invalid_domain, test_domain_case_sensitivity, test_empty_text_handling, test_entities_always_list, test_maximum_entity_count, test_metadata_contains_info, test_mixed_script_input, test_multiple_sequential_errors, test_no_corrupt_output, test_null_bytes_in_text, test_numeric_text_input, test_rapid_sequential_processing, test_recovery_after_error, test_relationships_always_list, test_result_has_valid_structure, test_single_character_input, test_single_word_input, test_special_characters_only, test_special_chars_in_source, test_unicode_text_input, test_unknown_domain, test_very_long_input, test_whitespace_only_handling, testboundaryconditions, testboundaryconditions test deeply nested relationships, testboundaryconditions test maximum entity count, testboundaryconditions test single character input, testboundaryconditions test single word input, testboundaryconditions.test_deeply_nested_relationships, testboundaryconditions.test_maximum_entity_count, testboundaryconditions.test_single_character_input, testboundaryconditions.test_single_word_input, testdatatypevalidation, testdatatypevalidation test control characters, testdatatypevalidation test mixed script input, testdatatypevalidation test numeric text input, testdatatypevalidation test unicode text input, testdatatypevalidation.test_control_characters, testdatatypevalidation.test_mixed_script_input, testdatatypevalidation.test_numeric_text_input, testdatatypevalidation.test_unicode_text_input, testerrormessages
- AST symbol scope: file
- Goal id: codebase/quality/tests-test_error_boundary_comprehensive
- Missing evidence: Review swallowed exception path in tests/test_error_boundary_comprehensive.py:79
- Merge key: codebase/quality/tests-test_error_boundary_comprehensive
- Merge family: tests/test_error_boundary_comprehensive.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 2e7402c528045fef
- Acceptance: Codebase scan filed this finding from tests/test_error_boundary_comprehensive.py:79. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-297-codebase-scan-2e7402c52804.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-298 Review swallowed exception path in tests/test_error_boundary_comprehensive.py:109

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/test_error_boundary_comprehensive.py
- Validation: python3 -m py_compile tests/test_error_boundary_comprehensive.py
- Bundle: codebase/quality/tests-test_error_boundary_comprehensive
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-test_error_boundary_comprehensive.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-test_error_boundary_comprehensive
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/test_error_boundary_comprehensive.py
- AST symbols: ipfs datasets py optimizers graphrag ontology generator, ipfs datasets py optimizers graphrag ontology generator ontologygenerationcontext, ipfs datasets py optimizers graphrag ontology generator ontologygenerator, ipfs_datasets_py.optimizers.graphrag.ontology_generator, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerationcontext, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerator, pytest, test concurrent context usage, test control characters, test deeply nested relationships, test degradation with corrupted input, test degradation with invalid domain, test domain case sensitivity, test empty text handling, test entities always list, test maximum entity count, test metadata contains info, test mixed script input, test multiple sequential errors, test no corrupt output, test null bytes in text, test numeric text input, test rapid sequential processing, test recovery after error, test relationships always list, test result has valid structure, test single character input, test single word input, test special characters only, test special chars in source, test unicode text input, test unknown domain, test very long input, test whitespace only handling, test_concurrent_context_usage, test_control_characters, test_deeply_nested_relationships, test_degradation_with_corrupted_input, test_degradation_with_invalid_domain, test_domain_case_sensitivity, test_empty_text_handling, test_entities_always_list, test_maximum_entity_count, test_metadata_contains_info, test_mixed_script_input, test_multiple_sequential_errors, test_no_corrupt_output, test_null_bytes_in_text, test_numeric_text_input, test_rapid_sequential_processing, test_recovery_after_error, test_relationships_always_list, test_result_has_valid_structure, test_single_character_input, test_single_word_input, test_special_characters_only, test_special_chars_in_source, test_unicode_text_input, test_unknown_domain, test_very_long_input, test_whitespace_only_handling, testboundaryconditions, testboundaryconditions test deeply nested relationships, testboundaryconditions test maximum entity count, testboundaryconditions test single character input, testboundaryconditions test single word input, testboundaryconditions.test_deeply_nested_relationships, testboundaryconditions.test_maximum_entity_count, testboundaryconditions.test_single_character_input, testboundaryconditions.test_single_word_input, testdatatypevalidation, testdatatypevalidation test control characters, testdatatypevalidation test mixed script input, testdatatypevalidation test numeric text input, testdatatypevalidation test unicode text input, testdatatypevalidation.test_control_characters, testdatatypevalidation.test_mixed_script_input, testdatatypevalidation.test_numeric_text_input, testdatatypevalidation.test_unicode_text_input, testerrormessages
- AST symbol scope: file
- Goal id: codebase/quality/tests-test_error_boundary_comprehensive
- Missing evidence: Review swallowed exception path in tests/test_error_boundary_comprehensive.py:109
- Merge key: codebase/quality/tests-test_error_boundary_comprehensive
- Merge family: tests/test_error_boundary_comprehensive.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: d2e342d229461a24
- Acceptance: Codebase scan filed this finding from tests/test_error_boundary_comprehensive.py:109. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-298-codebase-scan-d2e342d22946.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-299 Review swallowed exception path in tests/test_error_boundary_comprehensive.py:139

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/test_error_boundary_comprehensive.py
- Validation: python3 -m py_compile tests/test_error_boundary_comprehensive.py
- Bundle: codebase/quality/tests-test_error_boundary_comprehensive
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-test_error_boundary_comprehensive.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-test_error_boundary_comprehensive
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/test_error_boundary_comprehensive.py
- AST symbols: ipfs datasets py optimizers graphrag ontology generator, ipfs datasets py optimizers graphrag ontology generator ontologygenerationcontext, ipfs datasets py optimizers graphrag ontology generator ontologygenerator, ipfs_datasets_py.optimizers.graphrag.ontology_generator, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerationcontext, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerator, pytest, test concurrent context usage, test control characters, test deeply nested relationships, test degradation with corrupted input, test degradation with invalid domain, test domain case sensitivity, test empty text handling, test entities always list, test maximum entity count, test metadata contains info, test mixed script input, test multiple sequential errors, test no corrupt output, test null bytes in text, test numeric text input, test rapid sequential processing, test recovery after error, test relationships always list, test result has valid structure, test single character input, test single word input, test special characters only, test special chars in source, test unicode text input, test unknown domain, test very long input, test whitespace only handling, test_concurrent_context_usage, test_control_characters, test_deeply_nested_relationships, test_degradation_with_corrupted_input, test_degradation_with_invalid_domain, test_domain_case_sensitivity, test_empty_text_handling, test_entities_always_list, test_maximum_entity_count, test_metadata_contains_info, test_mixed_script_input, test_multiple_sequential_errors, test_no_corrupt_output, test_null_bytes_in_text, test_numeric_text_input, test_rapid_sequential_processing, test_recovery_after_error, test_relationships_always_list, test_result_has_valid_structure, test_single_character_input, test_single_word_input, test_special_characters_only, test_special_chars_in_source, test_unicode_text_input, test_unknown_domain, test_very_long_input, test_whitespace_only_handling, testboundaryconditions, testboundaryconditions test deeply nested relationships, testboundaryconditions test maximum entity count, testboundaryconditions test single character input, testboundaryconditions test single word input, testboundaryconditions.test_deeply_nested_relationships, testboundaryconditions.test_maximum_entity_count, testboundaryconditions.test_single_character_input, testboundaryconditions.test_single_word_input, testdatatypevalidation, testdatatypevalidation test control characters, testdatatypevalidation test mixed script input, testdatatypevalidation test numeric text input, testdatatypevalidation test unicode text input, testdatatypevalidation.test_control_characters, testdatatypevalidation.test_mixed_script_input, testdatatypevalidation.test_numeric_text_input, testdatatypevalidation.test_unicode_text_input, testerrormessages
- AST symbol scope: file
- Goal id: codebase/quality/tests-test_error_boundary_comprehensive
- Missing evidence: Review swallowed exception path in tests/test_error_boundary_comprehensive.py:139
- Merge key: codebase/quality/tests-test_error_boundary_comprehensive
- Merge family: tests/test_error_boundary_comprehensive.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: ca7e00ffc043730b
- Acceptance: Codebase scan filed this finding from tests/test_error_boundary_comprehensive.py:139. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-299-codebase-scan-ca7e00ffc043.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-300 Review swallowed exception path in tests/test_error_boundary_comprehensive.py:159

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/test_error_boundary_comprehensive.py
- Validation: python3 -m py_compile tests/test_error_boundary_comprehensive.py
- Bundle: codebase/quality/tests-test_error_boundary_comprehensive
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-test_error_boundary_comprehensive.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-test_error_boundary_comprehensive
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/test_error_boundary_comprehensive.py
- AST symbols: ipfs datasets py optimizers graphrag ontology generator, ipfs datasets py optimizers graphrag ontology generator ontologygenerationcontext, ipfs datasets py optimizers graphrag ontology generator ontologygenerator, ipfs_datasets_py.optimizers.graphrag.ontology_generator, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerationcontext, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerator, pytest, test concurrent context usage, test control characters, test deeply nested relationships, test degradation with corrupted input, test degradation with invalid domain, test domain case sensitivity, test empty text handling, test entities always list, test maximum entity count, test metadata contains info, test mixed script input, test multiple sequential errors, test no corrupt output, test null bytes in text, test numeric text input, test rapid sequential processing, test recovery after error, test relationships always list, test result has valid structure, test single character input, test single word input, test special characters only, test special chars in source, test unicode text input, test unknown domain, test very long input, test whitespace only handling, test_concurrent_context_usage, test_control_characters, test_deeply_nested_relationships, test_degradation_with_corrupted_input, test_degradation_with_invalid_domain, test_domain_case_sensitivity, test_empty_text_handling, test_entities_always_list, test_maximum_entity_count, test_metadata_contains_info, test_mixed_script_input, test_multiple_sequential_errors, test_no_corrupt_output, test_null_bytes_in_text, test_numeric_text_input, test_rapid_sequential_processing, test_recovery_after_error, test_relationships_always_list, test_result_has_valid_structure, test_single_character_input, test_single_word_input, test_special_characters_only, test_special_chars_in_source, test_unicode_text_input, test_unknown_domain, test_very_long_input, test_whitespace_only_handling, testboundaryconditions, testboundaryconditions test deeply nested relationships, testboundaryconditions test maximum entity count, testboundaryconditions test single character input, testboundaryconditions test single word input, testboundaryconditions.test_deeply_nested_relationships, testboundaryconditions.test_maximum_entity_count, testboundaryconditions.test_single_character_input, testboundaryconditions.test_single_word_input, testdatatypevalidation, testdatatypevalidation test control characters, testdatatypevalidation test mixed script input, testdatatypevalidation test numeric text input, testdatatypevalidation test unicode text input, testdatatypevalidation.test_control_characters, testdatatypevalidation.test_mixed_script_input, testdatatypevalidation.test_numeric_text_input, testdatatypevalidation.test_unicode_text_input, testerrormessages
- AST symbol scope: file
- Goal id: codebase/quality/tests-test_error_boundary_comprehensive
- Missing evidence: Review swallowed exception path in tests/test_error_boundary_comprehensive.py:159
- Merge key: codebase/quality/tests-test_error_boundary_comprehensive
- Merge family: tests/test_error_boundary_comprehensive.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 82bd9c822ff85844
- Acceptance: Codebase scan filed this finding from tests/test_error_boundary_comprehensive.py:159. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-300-codebase-scan-82bd9c822ff8.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-301 Review swallowed exception path in tests/test_error_boundary_comprehensive.py:341

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/test_error_boundary_comprehensive.py
- Validation: python3 -m py_compile tests/test_error_boundary_comprehensive.py
- Bundle: codebase/quality/tests-test_error_boundary_comprehensive
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-test_error_boundary_comprehensive.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-test_error_boundary_comprehensive
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/test_error_boundary_comprehensive.py
- AST symbols: fail first extraction, fail_first_extraction, ipfs datasets py optimizers graphrag ontology generator, ipfs datasets py optimizers graphrag ontology generator ontologygenerationcontext, ipfs datasets py optimizers graphrag ontology generator ontologygenerator, ipfs_datasets_py.optimizers.graphrag.ontology_generator, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerationcontext, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerator, pytest, test concurrent context usage, test control characters, test deeply nested relationships, test degradation with corrupted input, test degradation with invalid domain, test domain case sensitivity, test empty text handling, test entities always list, test maximum entity count, test metadata contains info, test mixed script input, test multiple sequential errors, test no corrupt output, test null bytes in text, test numeric text input, test rapid sequential processing, test recovery after error, test relationships always list, test result has valid structure, test single character input, test single word input, test special characters only, test special chars in source, test unicode text input, test unknown domain, test very long input, test whitespace only handling, test_concurrent_context_usage, test_control_characters, test_deeply_nested_relationships, test_degradation_with_corrupted_input, test_degradation_with_invalid_domain, test_domain_case_sensitivity, test_empty_text_handling, test_entities_always_list, test_maximum_entity_count, test_metadata_contains_info, test_mixed_script_input, test_multiple_sequential_errors, test_no_corrupt_output, test_null_bytes_in_text, test_numeric_text_input, test_rapid_sequential_processing, test_recovery_after_error, test_relationships_always_list, test_result_has_valid_structure, test_single_character_input, test_single_word_input, test_special_characters_only, test_special_chars_in_source, test_unicode_text_input, test_unknown_domain, test_very_long_input, test_whitespace_only_handling, testboundaryconditions, testboundaryconditions test deeply nested relationships, testboundaryconditions test maximum entity count, testboundaryconditions test single character input, testboundaryconditions test single word input, testboundaryconditions.test_deeply_nested_relationships, testboundaryconditions.test_maximum_entity_count, testboundaryconditions.test_single_character_input, testboundaryconditions.test_single_word_input, testdatatypevalidation, testdatatypevalidation test control characters, testdatatypevalidation test mixed script input, testdatatypevalidation test numeric text input, testdatatypevalidation test unicode text input, testdatatypevalidation.test_control_characters, testdatatypevalidation.test_mixed_script_input, testdatatypevalidation.test_numeric_text_input
- AST symbol scope: file
- Goal id: codebase/quality/tests-test_error_boundary_comprehensive
- Missing evidence: Review swallowed exception path in tests/test_error_boundary_comprehensive.py:341
- Merge key: codebase/quality/tests-test_error_boundary_comprehensive
- Merge family: tests/test_error_boundary_comprehensive.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: a988f6f70a4fc4e0
- Acceptance: Codebase scan filed this finding from tests/test_error_boundary_comprehensive.py:341. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-301-codebase-scan-a988f6f70a4f.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-302 Review swallowed exception path in tests/test_error_boundary_comprehensive.py:357

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/test_error_boundary_comprehensive.py
- Validation: python3 -m py_compile tests/test_error_boundary_comprehensive.py
- Bundle: codebase/quality/tests-test_error_boundary_comprehensive
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-test_error_boundary_comprehensive.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-test_error_boundary_comprehensive
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/test_error_boundary_comprehensive.py
- AST symbols: fail first extraction, fail_first_extraction, ipfs datasets py optimizers graphrag ontology generator, ipfs datasets py optimizers graphrag ontology generator ontologygenerationcontext, ipfs datasets py optimizers graphrag ontology generator ontologygenerator, ipfs_datasets_py.optimizers.graphrag.ontology_generator, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerationcontext, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerator, pytest, test concurrent context usage, test control characters, test deeply nested relationships, test degradation with corrupted input, test degradation with invalid domain, test domain case sensitivity, test empty text handling, test entities always list, test maximum entity count, test metadata contains info, test mixed script input, test multiple sequential errors, test no corrupt output, test null bytes in text, test numeric text input, test rapid sequential processing, test recovery after error, test relationships always list, test result has valid structure, test single character input, test single word input, test special characters only, test special chars in source, test unicode text input, test unknown domain, test very long input, test whitespace only handling, test_concurrent_context_usage, test_control_characters, test_deeply_nested_relationships, test_degradation_with_corrupted_input, test_degradation_with_invalid_domain, test_domain_case_sensitivity, test_empty_text_handling, test_entities_always_list, test_maximum_entity_count, test_metadata_contains_info, test_mixed_script_input, test_multiple_sequential_errors, test_no_corrupt_output, test_null_bytes_in_text, test_numeric_text_input, test_rapid_sequential_processing, test_recovery_after_error, test_relationships_always_list, test_result_has_valid_structure, test_single_character_input, test_single_word_input, test_special_characters_only, test_special_chars_in_source, test_unicode_text_input, test_unknown_domain, test_very_long_input, test_whitespace_only_handling, testboundaryconditions, testboundaryconditions test deeply nested relationships, testboundaryconditions test maximum entity count, testboundaryconditions test single character input, testboundaryconditions test single word input, testboundaryconditions.test_deeply_nested_relationships, testboundaryconditions.test_maximum_entity_count, testboundaryconditions.test_single_character_input, testboundaryconditions.test_single_word_input, testdatatypevalidation, testdatatypevalidation test control characters, testdatatypevalidation test mixed script input, testdatatypevalidation test numeric text input, testdatatypevalidation test unicode text input, testdatatypevalidation.test_control_characters, testdatatypevalidation.test_mixed_script_input, testdatatypevalidation.test_numeric_text_input
- AST symbol scope: file
- Goal id: codebase/quality/tests-test_error_boundary_comprehensive
- Missing evidence: Review swallowed exception path in tests/test_error_boundary_comprehensive.py:357
- Merge key: codebase/quality/tests-test_error_boundary_comprehensive
- Merge family: tests/test_error_boundary_comprehensive.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 210a7a9f4f81d3a8
- Acceptance: Codebase scan filed this finding from tests/test_error_boundary_comprehensive.py:357. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-302-codebase-scan-210a7a9f4f81.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-303 Review swallowed exception path in tests/test_error_boundary_comprehensive.py:408

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/test_error_boundary_comprehensive.py
- Validation: python3 -m py_compile tests/test_error_boundary_comprehensive.py
- Bundle: codebase/quality/tests-test_error_boundary_comprehensive
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-test_error_boundary_comprehensive.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-test_error_boundary_comprehensive
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/test_error_boundary_comprehensive.py
- AST symbols: fail first extraction, fail_first_extraction, ipfs datasets py optimizers graphrag ontology generator, ipfs datasets py optimizers graphrag ontology generator ontologygenerationcontext, ipfs datasets py optimizers graphrag ontology generator ontologygenerator, ipfs_datasets_py.optimizers.graphrag.ontology_generator, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerationcontext, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerator, pytest, test concurrent context usage, test control characters, test deeply nested relationships, test degradation with corrupted input, test degradation with invalid domain, test domain case sensitivity, test empty text handling, test entities always list, test maximum entity count, test metadata contains info, test mixed script input, test multiple sequential errors, test no corrupt output, test null bytes in text, test numeric text input, test rapid sequential processing, test recovery after error, test relationships always list, test result has valid structure, test single character input, test single word input, test special characters only, test special chars in source, test unicode text input, test unknown domain, test very long input, test whitespace only handling, test_concurrent_context_usage, test_control_characters, test_deeply_nested_relationships, test_degradation_with_corrupted_input, test_degradation_with_invalid_domain, test_domain_case_sensitivity, test_empty_text_handling, test_entities_always_list, test_maximum_entity_count, test_metadata_contains_info, test_mixed_script_input, test_multiple_sequential_errors, test_no_corrupt_output, test_null_bytes_in_text, test_numeric_text_input, test_rapid_sequential_processing, test_recovery_after_error, test_relationships_always_list, test_result_has_valid_structure, test_single_character_input, test_single_word_input, test_special_characters_only, test_special_chars_in_source, test_unicode_text_input, test_unknown_domain, test_very_long_input, test_whitespace_only_handling, testboundaryconditions, testboundaryconditions test deeply nested relationships, testboundaryconditions test maximum entity count, testboundaryconditions test single character input, testboundaryconditions test single word input, testboundaryconditions.test_deeply_nested_relationships, testboundaryconditions.test_maximum_entity_count, testboundaryconditions.test_single_character_input, testboundaryconditions.test_single_word_input, testdatatypevalidation, testdatatypevalidation test control characters, testdatatypevalidation test mixed script input, testdatatypevalidation test numeric text input, testdatatypevalidation test unicode text input, testdatatypevalidation.test_control_characters, testdatatypevalidation.test_mixed_script_input, testdatatypevalidation.test_numeric_text_input
- AST symbol scope: file
- Goal id: codebase/quality/tests-test_error_boundary_comprehensive
- Missing evidence: Review swallowed exception path in tests/test_error_boundary_comprehensive.py:408
- Merge key: codebase/quality/tests-test_error_boundary_comprehensive
- Merge family: tests/test_error_boundary_comprehensive.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 8330728218c4de91
- Acceptance: Codebase scan filed this finding from tests/test_error_boundary_comprehensive.py:408. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-303-codebase-scan-8330728218c4.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
