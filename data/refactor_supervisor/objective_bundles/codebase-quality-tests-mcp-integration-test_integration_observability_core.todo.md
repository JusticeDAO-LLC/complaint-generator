# Codebase Bundle: codebase/quality/tests-mcp-integration-test_integration_observability_core

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-233 Review swallowed exception path in tests/mcp/integration/test_integration_observability_core.py:319

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/mcp/integration/test_integration_observability_core.py
- Validation: python3 -m py_compile tests/mcp/integration/test_integration_observability_core.py
- Bundle: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-mcp-integration-test_integration_observability_core.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/mcp/integration/test_integration_observability_core.py
- AST symbols: __init__, analyze, complaint analyzer, complaint_analyzer, concurrent futures, concurrent futures threadpoolexecutor, concurrent.futures, concurrent.futures.threadpoolexecutor, decide, decision tree, decision_tree, init, ipfs datasets py logic observability metrics prometheus, ipfs datasets py logic observability metrics prometheus get prometheus collector, ipfs datasets py logic observability otel integration, ipfs datasets py logic observability otel integration get otel tracer, ipfs datasets py logic security llm circuit breaker, ipfs datasets py logic security llm circuit breaker get circuit breaker, ipfs_datasets_py.logic.observability.metrics_prometheus, ipfs_datasets_py.logic.observability.metrics_prometheus.get_prometheus_collector, ipfs_datasets_py.logic.observability.otel_integration, ipfs_datasets_py.logic.observability.otel_integration.get_otel_tracer, ipfs_datasets_py.logic.security.llm_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.get_circuit_breaker, mockcomplaintanalyzer, mockcomplaintanalyzer analyze, mockcomplaintanalyzer init, mockcomplaintanalyzer.__init__, mockcomplaintanalyzer.analyze, mockdecisiontree, mockdecisiontree decide, mockdecisiontree init, mockdecisiontree.__init__, mockdecisiontree.decide, mockqueryoptimizer, mockqueryoptimizer init, mockqueryoptimizer optimize, mockqueryoptimizer.__init__, mockqueryoptimizer.optimize, observability, optimize, pytest, query optimizer, query_optimizer, run pipeline, run_pipeline, test analysis pipeline with full observability, test circuit breaker opening recorded, test circuit breaker recovery tracked, test complaint processing pipeline, test concurrent pipeline execution, test failed optimization recorded, test latency correlation across components, test pipeline with partial failure, test successful optimization recorded, test_analysis_pipeline_with_full_observability, test_circuit_breaker_opening_recorded, test_circuit_breaker_recovery_tracked, test_complaint_processing_pipeline, test_concurrent_pipeline_execution, test_failed_optimization_recorded, test_latency_correlation_across_components, test_pipeline_with_partial_failure, test_successful_optimization_recorded, testcircuitbreakerwithobservability, testcircuitbreakerwithobservability test circuit breaker opening recorded, testcircuitbreakerwithobservability test circuit breaker recovery tracked, testcircuitbreakerwithobservability.test_circuit_breaker_opening_recorded, testcircuitbreakerwithobservability.test_circuit_breaker_recovery_tracked, testcomplaintanalysiswithobservability, testcomplaintanalysiswithobservability test analysis pipeline with full observability, testcomplaintanalysiswithobservability.test_analysis_pipeline_with_full_observability, testconcurrentmulticomponentintegration, testconcurrentmulticomponentintegration run pipeline, testconcurrentmulticomponentintegration test concurrent pipeline execution, testconcurrentmulticomponentintegration.run_pipeline, testconcurrentmulticomponentintegration.test_concurrent_pipeline_execution, testmetriccorrelation, testmetriccorrelation test latency correlation across components, testmetriccorrelation.test_latency_correlation_across_components
- AST symbol scope: file
- Goal id: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Missing evidence: Review swallowed exception path in tests/mcp/integration/test_integration_observability_core.py:319
- Merge key: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Merge family: tests/mcp/integration/test_integration_observability_core.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 80867306955090ab
- Acceptance: Codebase scan filed this finding from tests/mcp/integration/test_integration_observability_core.py:319. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-233-codebase-scan-808673069550.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-234 Review swallowed exception path in tests/mcp/integration/test_integration_observability_core.py:391

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/mcp/integration/test_integration_observability_core.py
- Validation: python3 -m py_compile tests/mcp/integration/test_integration_observability_core.py
- Bundle: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-mcp-integration-test_integration_observability_core.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/mcp/integration/test_integration_observability_core.py
- AST symbols: __init__, analyze, complaint analyzer, complaint_analyzer, concurrent futures, concurrent futures threadpoolexecutor, concurrent.futures, concurrent.futures.threadpoolexecutor, decide, decision tree, decision_tree, init, ipfs datasets py logic observability metrics prometheus, ipfs datasets py logic observability metrics prometheus get prometheus collector, ipfs datasets py logic observability otel integration, ipfs datasets py logic observability otel integration get otel tracer, ipfs datasets py logic security llm circuit breaker, ipfs datasets py logic security llm circuit breaker get circuit breaker, ipfs_datasets_py.logic.observability.metrics_prometheus, ipfs_datasets_py.logic.observability.metrics_prometheus.get_prometheus_collector, ipfs_datasets_py.logic.observability.otel_integration, ipfs_datasets_py.logic.observability.otel_integration.get_otel_tracer, ipfs_datasets_py.logic.security.llm_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.get_circuit_breaker, mockcomplaintanalyzer, mockcomplaintanalyzer analyze, mockcomplaintanalyzer init, mockcomplaintanalyzer.__init__, mockcomplaintanalyzer.analyze, mockdecisiontree, mockdecisiontree decide, mockdecisiontree init, mockdecisiontree.__init__, mockdecisiontree.decide, mockqueryoptimizer, mockqueryoptimizer init, mockqueryoptimizer optimize, mockqueryoptimizer.__init__, mockqueryoptimizer.optimize, observability, optimize, pytest, query optimizer, query_optimizer, run pipeline, run_pipeline, test analysis pipeline with full observability, test circuit breaker opening recorded, test circuit breaker recovery tracked, test complaint processing pipeline, test concurrent pipeline execution, test failed optimization recorded, test latency correlation across components, test pipeline with partial failure, test successful optimization recorded, test_analysis_pipeline_with_full_observability, test_circuit_breaker_opening_recorded, test_circuit_breaker_recovery_tracked, test_complaint_processing_pipeline, test_concurrent_pipeline_execution, test_failed_optimization_recorded, test_latency_correlation_across_components, test_pipeline_with_partial_failure, test_successful_optimization_recorded, testcircuitbreakerwithobservability, testcircuitbreakerwithobservability test circuit breaker opening recorded, testcircuitbreakerwithobservability test circuit breaker recovery tracked, testcircuitbreakerwithobservability.test_circuit_breaker_opening_recorded, testcircuitbreakerwithobservability.test_circuit_breaker_recovery_tracked, testcomplaintanalysiswithobservability, testcomplaintanalysiswithobservability test analysis pipeline with full observability, testcomplaintanalysiswithobservability.test_analysis_pipeline_with_full_observability, testconcurrentmulticomponentintegration, testconcurrentmulticomponentintegration run pipeline, testconcurrentmulticomponentintegration test concurrent pipeline execution, testconcurrentmulticomponentintegration.run_pipeline, testconcurrentmulticomponentintegration.test_concurrent_pipeline_execution, testmetriccorrelation, testmetriccorrelation test latency correlation across components, testmetriccorrelation.test_latency_correlation_across_components
- AST symbol scope: file
- Goal id: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Missing evidence: Review swallowed exception path in tests/mcp/integration/test_integration_observability_core.py:391
- Merge key: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Merge family: tests/mcp/integration/test_integration_observability_core.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: e6ab5d27324841c2
- Acceptance: Codebase scan filed this finding from tests/mcp/integration/test_integration_observability_core.py:391. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-234-codebase-scan-e6ab5d273248.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-235 Review swallowed exception path in tests/mcp/integration/test_integration_observability_core.py:512

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/mcp/integration/test_integration_observability_core.py
- Validation: python3 -m py_compile tests/mcp/integration/test_integration_observability_core.py
- Bundle: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-mcp-integration-test_integration_observability_core.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/mcp/integration/test_integration_observability_core.py
- AST symbols: __init__, analyze, complaint analyzer, complaint_analyzer, concurrent futures, concurrent futures threadpoolexecutor, concurrent.futures, concurrent.futures.threadpoolexecutor, decide, decision tree, decision_tree, init, ipfs datasets py logic observability metrics prometheus, ipfs datasets py logic observability metrics prometheus get prometheus collector, ipfs datasets py logic observability otel integration, ipfs datasets py logic observability otel integration get otel tracer, ipfs datasets py logic security llm circuit breaker, ipfs datasets py logic security llm circuit breaker get circuit breaker, ipfs_datasets_py.logic.observability.metrics_prometheus, ipfs_datasets_py.logic.observability.metrics_prometheus.get_prometheus_collector, ipfs_datasets_py.logic.observability.otel_integration, ipfs_datasets_py.logic.observability.otel_integration.get_otel_tracer, ipfs_datasets_py.logic.security.llm_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.get_circuit_breaker, mockcomplaintanalyzer, mockcomplaintanalyzer analyze, mockcomplaintanalyzer init, mockcomplaintanalyzer.__init__, mockcomplaintanalyzer.analyze, mockdecisiontree, mockdecisiontree decide, mockdecisiontree init, mockdecisiontree.__init__, mockdecisiontree.decide, mockqueryoptimizer, mockqueryoptimizer init, mockqueryoptimizer optimize, mockqueryoptimizer.__init__, mockqueryoptimizer.optimize, observability, optimize, pytest, query optimizer, query_optimizer, run pipeline, run_pipeline, test analysis pipeline with full observability, test circuit breaker opening recorded, test circuit breaker recovery tracked, test complaint processing pipeline, test concurrent pipeline execution, test failed optimization recorded, test latency correlation across components, test pipeline with partial failure, test successful optimization recorded, test_analysis_pipeline_with_full_observability, test_circuit_breaker_opening_recorded, test_circuit_breaker_recovery_tracked, test_complaint_processing_pipeline, test_concurrent_pipeline_execution, test_failed_optimization_recorded, test_latency_correlation_across_components, test_pipeline_with_partial_failure, test_successful_optimization_recorded, testcircuitbreakerwithobservability, testcircuitbreakerwithobservability test circuit breaker opening recorded, testcircuitbreakerwithobservability test circuit breaker recovery tracked, testcircuitbreakerwithobservability.test_circuit_breaker_opening_recorded, testcircuitbreakerwithobservability.test_circuit_breaker_recovery_tracked, testcomplaintanalysiswithobservability, testcomplaintanalysiswithobservability test analysis pipeline with full observability, testcomplaintanalysiswithobservability.test_analysis_pipeline_with_full_observability, testconcurrentmulticomponentintegration, testconcurrentmulticomponentintegration run pipeline, testconcurrentmulticomponentintegration test concurrent pipeline execution, testconcurrentmulticomponentintegration.run_pipeline, testconcurrentmulticomponentintegration.test_concurrent_pipeline_execution, testmetriccorrelation, testmetriccorrelation test latency correlation across components, testmetriccorrelation.test_latency_correlation_across_components
- AST symbol scope: file
- Goal id: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Missing evidence: Review swallowed exception path in tests/mcp/integration/test_integration_observability_core.py:512
- Merge key: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Merge family: tests/mcp/integration/test_integration_observability_core.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 6292a282daa76df5
- Acceptance: Codebase scan filed this finding from tests/mcp/integration/test_integration_observability_core.py:512. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-235-codebase-scan-6292a282daa7.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-236 Review swallowed exception path in tests/mcp/integration/test_integration_observability_core.py:521

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/mcp/integration/test_integration_observability_core.py
- Validation: python3 -m py_compile tests/mcp/integration/test_integration_observability_core.py
- Bundle: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-mcp-integration-test_integration_observability_core.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/mcp/integration/test_integration_observability_core.py
- AST symbols: __init__, analyze, complaint analyzer, complaint_analyzer, concurrent futures, concurrent futures threadpoolexecutor, concurrent.futures, concurrent.futures.threadpoolexecutor, decide, decision tree, decision_tree, init, ipfs datasets py logic observability metrics prometheus, ipfs datasets py logic observability metrics prometheus get prometheus collector, ipfs datasets py logic observability otel integration, ipfs datasets py logic observability otel integration get otel tracer, ipfs datasets py logic security llm circuit breaker, ipfs datasets py logic security llm circuit breaker get circuit breaker, ipfs_datasets_py.logic.observability.metrics_prometheus, ipfs_datasets_py.logic.observability.metrics_prometheus.get_prometheus_collector, ipfs_datasets_py.logic.observability.otel_integration, ipfs_datasets_py.logic.observability.otel_integration.get_otel_tracer, ipfs_datasets_py.logic.security.llm_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.get_circuit_breaker, mockcomplaintanalyzer, mockcomplaintanalyzer analyze, mockcomplaintanalyzer init, mockcomplaintanalyzer.__init__, mockcomplaintanalyzer.analyze, mockdecisiontree, mockdecisiontree decide, mockdecisiontree init, mockdecisiontree.__init__, mockdecisiontree.decide, mockqueryoptimizer, mockqueryoptimizer init, mockqueryoptimizer optimize, mockqueryoptimizer.__init__, mockqueryoptimizer.optimize, observability, optimize, pytest, query optimizer, query_optimizer, run pipeline, run_pipeline, test analysis pipeline with full observability, test circuit breaker opening recorded, test circuit breaker recovery tracked, test complaint processing pipeline, test concurrent pipeline execution, test failed optimization recorded, test latency correlation across components, test pipeline with partial failure, test successful optimization recorded, test_analysis_pipeline_with_full_observability, test_circuit_breaker_opening_recorded, test_circuit_breaker_recovery_tracked, test_complaint_processing_pipeline, test_concurrent_pipeline_execution, test_failed_optimization_recorded, test_latency_correlation_across_components, test_pipeline_with_partial_failure, test_successful_optimization_recorded, testcircuitbreakerwithobservability, testcircuitbreakerwithobservability test circuit breaker opening recorded, testcircuitbreakerwithobservability test circuit breaker recovery tracked, testcircuitbreakerwithobservability.test_circuit_breaker_opening_recorded, testcircuitbreakerwithobservability.test_circuit_breaker_recovery_tracked, testcomplaintanalysiswithobservability, testcomplaintanalysiswithobservability test analysis pipeline with full observability, testcomplaintanalysiswithobservability.test_analysis_pipeline_with_full_observability, testconcurrentmulticomponentintegration, testconcurrentmulticomponentintegration run pipeline, testconcurrentmulticomponentintegration test concurrent pipeline execution, testconcurrentmulticomponentintegration.run_pipeline, testconcurrentmulticomponentintegration.test_concurrent_pipeline_execution, testmetriccorrelation, testmetriccorrelation test latency correlation across components, testmetriccorrelation.test_latency_correlation_across_components
- AST symbol scope: file
- Goal id: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Missing evidence: Review swallowed exception path in tests/mcp/integration/test_integration_observability_core.py:521
- Merge key: codebase/quality/tests-mcp-integration-test_integration_observability_core
- Merge family: tests/mcp/integration/test_integration_observability_core.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: e9742a9658476b58
- Acceptance: Codebase scan filed this finding from tests/mcp/integration/test_integration_observability_core.py:521. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-236-codebase-scan-e9742a965847.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
