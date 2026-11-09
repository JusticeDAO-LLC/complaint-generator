# Codebase Bundle: codebase/quality/tests-test_property_based_extraction_testing

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-305 Review swallowed exception path in tests/test_property_based_extraction_testing.py:222

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/test_property_based_extraction_testing.py
- Validation: python3 -m py_compile tests/test_property_based_extraction_testing.py
- Bundle: codebase/quality/tests-test_property_based_extraction_testing
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-test_property_based_extraction_testing.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-test_property_based_extraction_testing
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/test_property_based_extraction_testing.py
- AST symbols: hypothesis, hypothesis assume, hypothesis given, hypothesis settings, hypothesis strategies, hypothesis.assume, hypothesis.given, hypothesis.settings, hypothesis.strategies, ipfs datasets py optimizers graphrag ontology generator, ipfs datasets py optimizers graphrag ontology generator ontologygenerationcontext, ipfs datasets py optimizers graphrag ontology generator ontologygenerator, ipfs_datasets_py.optimizers.graphrag.ontology_generator, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerationcontext, ipfs_datasets_py.optimizers.graphrag.ontology_generator.ontologygenerator, pytest, test any text generates ontology, test confidence scores in valid range, test domain parameter accepted, test entities are list or empty, test entity structure consistency, test extraction idempotent, test handles special characters, test long text handling, test mixed content handling, test numeric content handling, test ontology has required fields, test relationship structure consistency, test relationships are list or empty, test repetitive content handling, test short text handling, test whitespace handling, test_any_text_generates_ontology, test_confidence_scores_in_valid_range, test_domain_parameter_accepted, test_entities_are_list_or_empty, test_entity_structure_consistency, test_extraction_idempotent, test_handles_special_characters, test_long_text_handling, test_mixed_content_handling, test_numeric_content_handling, test_ontology_has_required_fields, test_relationship_structure_consistency, test_relationships_are_list_or_empty, test_repetitive_content_handling, test_short_text_handling, test_whitespace_handling, testpropertybasedconfidencescores, testpropertybasedconfidencescores test confidence scores in valid range, testpropertybasedconfidencescores.test_confidence_scores_in_valid_range, testpropertybaseddomainhandling, testpropertybaseddomainhandling test domain parameter accepted, testpropertybaseddomainhandling.test_domain_parameter_accepted, testpropertybasedentitystructure, testpropertybasedentitystructure test entity structure consistency, testpropertybasedentitystructure.test_entity_structure_consistency, testpropertybasedidempotence, testpropertybasedidempotence test extraction idempotent, testpropertybasedidempotence.test_extraction_idempotent, testpropertybasedlongcontent, testpropertybasedlongcontent test long text handling, testpropertybasedlongcontent.test_long_text_handling, testpropertybasedmixedcontent, testpropertybasedmixedcontent test mixed content handling, testpropertybasedmixedcontent.test_mixed_content_handling, testpropertybasednumericcontent, testpropertybasednumericcontent test numeric content handling, testpropertybasednumericcontent.test_numeric_content_handling, testpropertybasedrelationshipstructure, testpropertybasedrelationshipstructure test relationship structure consistency, testpropertybasedrelationshipstructure.test_relationship_structure_consistency, testpropertybasedrepetitivecontent, testpropertybasedrepetitivecontent test repetitive content handling, testpropertybasedrepetitivecontent.test_repetitive_content_handling, testpropertybasedshortcontent, testpropertybasedshortcontent test short text handling, testpropertybasedshortcontent.test_short_text_handling, testpropertybasedspecialcharacters, testpropertybasedspecialcharacters test handles special characters
- AST symbol scope: file
- Goal id: codebase/quality/tests-test_property_based_extraction_testing
- Missing evidence: Review swallowed exception path in tests/test_property_based_extraction_testing.py:222
- Merge key: codebase/quality/tests-test_property_based_extraction_testing
- Merge family: tests/test_property_based_extraction_testing.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: c80276b2e2641159
- Acceptance: Codebase scan filed this finding from tests/test_property_based_extraction_testing.py:222. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-305-codebase-scan-c80276b2e264.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
