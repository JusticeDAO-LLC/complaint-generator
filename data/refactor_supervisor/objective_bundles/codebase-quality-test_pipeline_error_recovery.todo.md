# Codebase Bundle: codebase/quality/test_pipeline_error_recovery

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-230 Review swallowed exception path in test_pipeline_error_recovery.py:402

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, test_pipeline_error_recovery.py
- Validation: python3 -m py_compile test_pipeline_error_recovery.py
- Bundle: codebase/quality/test_pipeline_error_recovery
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-test_pipeline_error_recovery.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/test_pipeline_error_recovery
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: test_pipeline_error_recovery.py
- AST symbols: ipfs datasets py optimizers graphrag ontology pipeline, ipfs datasets py optimizers graphrag ontology pipeline ontologypipeline, ipfs_datasets_py.optimizers.graphrag.ontology_pipeline, ipfs_datasets_py.optimizers.graphrag.ontology_pipeline.ontologypipeline, pytest, sys, test pipeline ontology valid after error recovery, test pipeline refinement count accurate, test pipeline refinement disabled, test pipeline refinement iteration limit, test pipeline refinement with difficult input, test pipeline result structure always valid, test pipeline with ambiguous entity text, test pipeline with brief input, test pipeline with circular references in text, test pipeline with control characters, test pipeline with custom extraction config, test pipeline with default domain, test pipeline with default parameters, test pipeline with difficult extraction, test pipeline with empty text, test pipeline with extremely long entity name, test pipeline with large text, test pipeline with low confidence threshold, test pipeline with many refinement rounds, test pipeline with mediator active, test pipeline with minimal input, test pipeline with minimal ontology, test pipeline with minimal relationships, test pipeline with nested quotations, test pipeline with none data, test pipeline with null bytes in text, test pipeline with repetitive entities, test pipeline with special characters, test pipeline with unicode text, test pipeline with valid input no crash, test pipeline with very long text, test pipeline with whitespace only, test pipeline without critic, test pipeline without llm backend, test pipeline without mediator, test_pipeline_ontology_valid_after_error_recovery, test_pipeline_refinement_count_accurate, test_pipeline_refinement_disabled, test_pipeline_refinement_iteration_limit, test_pipeline_refinement_with_difficult_input, test_pipeline_result_structure_always_valid, test_pipeline_with_ambiguous_entity_text, test_pipeline_with_brief_input, test_pipeline_with_circular_references_in_text, test_pipeline_with_control_characters, test_pipeline_with_custom_extraction_config, test_pipeline_with_default_domain, test_pipeline_with_default_parameters, test_pipeline_with_difficult_extraction, test_pipeline_with_empty_text, test_pipeline_with_extremely_long_entity_name, test_pipeline_with_large_text, test_pipeline_with_low_confidence_threshold, test_pipeline_with_many_refinement_rounds, test_pipeline_with_mediator_active, test_pipeline_with_minimal_input, test_pipeline_with_minimal_ontology, test_pipeline_with_minimal_relationships, test_pipeline_with_nested_quotations, test_pipeline_with_none_data, test_pipeline_with_null_bytes_in_text, test_pipeline_with_repetitive_entities, test_pipeline_with_special_characters, test_pipeline_with_unicode_text, test_pipeline_with_valid_input_no_crash, test_pipeline_with_very_long_text, test_pipeline_with_whitespace_only, test_pipeline_without_critic, test_pipeline_without_llm_backend, test_pipeline_without_mediator, testpipelineerrorrecoverybasics, testpipelineerrorrecoverybasics test pipeline with custom extraction config, testpipelineerrorrecoverybasics test pipeline with default domain, testpipelineerrorrecoverybasics test pipeline with empty text
- AST symbol scope: file
- Goal id: codebase/quality/test_pipeline_error_recovery
- Missing evidence: Review swallowed exception path in test_pipeline_error_recovery.py:402
- Merge key: codebase/quality/test_pipeline_error_recovery
- Merge family: test_pipeline_error_recovery.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: e61544625f39fd6f
- Acceptance: Codebase scan filed this finding from test_pipeline_error_recovery.py:402. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-230-codebase-scan-e61544625f39.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
