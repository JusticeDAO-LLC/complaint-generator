# Codebase Bundle: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-239 Review swallowed exception path in tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:198

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- Validation: python3 -m py_compile tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- Bundle: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-mcp-unit-test_mcplusplus_v39_session84_properties.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- AST symbols: call sequence, call_sequence, circuit breaker config, circuit_breaker_config, concurrent futures, concurrent futures as completed, concurrent futures threadpoolexecutor, concurrent.futures, concurrent.futures.as_completed, concurrent.futures.threadpoolexecutor, fail func, fail_func, hypothesis, hypothesis assume, hypothesis example, hypothesis given, hypothesis healthcheck, hypothesis settings, hypothesis strategies, hypothesis.assume, hypothesis.example, hypothesis.given, hypothesis.healthcheck, hypothesis.settings, hypothesis.strategies, ipfs datasets py logic observability structured logging, ipfs datasets py logic observability structured logging eventtype, ipfs datasets py logic observability structured logging filter logs, ipfs datasets py logic observability structured logging get logger, ipfs datasets py logic observability structured logging jsonlogformatter, ipfs datasets py logic observability structured logging log event, ipfs datasets py logic observability structured logging logcontext, ipfs datasets py logic observability structured logging parse json log file, ipfs datasets py logic security llm circuit breaker, ipfs datasets py logic security llm circuit breaker circuitbreakeropenerror, ipfs datasets py logic security llm circuit breaker circuitstate, ipfs datasets py logic security llm circuit breaker get circuit breaker, ipfs datasets py logic security llm circuit breaker llmcircuitbreaker, ipfs_datasets_py.logic.observability.structured_logging, ipfs_datasets_py.logic.observability.structured_logging.eventtype, ipfs_datasets_py.logic.observability.structured_logging.filter_logs, ipfs_datasets_py.logic.observability.structured_logging.get_logger, ipfs_datasets_py.logic.observability.structured_logging.jsonlogformatter, ipfs_datasets_py.logic.observability.structured_logging.log_event, ipfs_datasets_py.logic.observability.structured_logging.logcontext, ipfs_datasets_py.logic.observability.structured_logging.parse_json_log_file, ipfs_datasets_py.logic.security.llm_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.circuitbreakeropenerror, ipfs_datasets_py.logic.security.llm_circuit_breaker.circuitstate, ipfs_datasets_py.logic.security.llm_circuit_breaker.get_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.llmcircuitbreaker, json, log context data, log_context_data, logging, os, pathlib, pathlib path, pathlib.path, pytest, slow func, slow_func, success func, success_func, tempfile, test circuit breaker always eventually recovers, test circuit breaker thread safe under concurrent load, test context fields never leak between threads, test empty and edge case sequences, test event types always valid enum members, test failure count monotonic or resets, test json output always parses, test latencies always non negative, test metrics consistency, test state transitions form valid dag, test_circuit_breaker_always_eventually_recovers, test_circuit_breaker_thread_safe_under_concurrent_load, test_context_fields_never_leak_between_threads, test_empty_and_edge_case_sequences, test_event_types_always_valid_enum_members
- AST symbol scope: file
- Goal id: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Missing evidence: Review swallowed exception path in tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:198
- Merge key: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Merge family: tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: cdafe5e4909beeb2
- Acceptance: Codebase scan filed this finding from tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:198. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-239-codebase-scan-cdafe5e4909b.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-240 Review swallowed exception path in tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:203

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- Validation: python3 -m py_compile tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- Bundle: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-mcp-unit-test_mcplusplus_v39_session84_properties.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- AST symbols: call sequence, call_sequence, circuit breaker config, circuit_breaker_config, concurrent futures, concurrent futures as completed, concurrent futures threadpoolexecutor, concurrent.futures, concurrent.futures.as_completed, concurrent.futures.threadpoolexecutor, fail func, fail_func, hypothesis, hypothesis assume, hypothesis example, hypothesis given, hypothesis healthcheck, hypothesis settings, hypothesis strategies, hypothesis.assume, hypothesis.example, hypothesis.given, hypothesis.healthcheck, hypothesis.settings, hypothesis.strategies, ipfs datasets py logic observability structured logging, ipfs datasets py logic observability structured logging eventtype, ipfs datasets py logic observability structured logging filter logs, ipfs datasets py logic observability structured logging get logger, ipfs datasets py logic observability structured logging jsonlogformatter, ipfs datasets py logic observability structured logging log event, ipfs datasets py logic observability structured logging logcontext, ipfs datasets py logic observability structured logging parse json log file, ipfs datasets py logic security llm circuit breaker, ipfs datasets py logic security llm circuit breaker circuitbreakeropenerror, ipfs datasets py logic security llm circuit breaker circuitstate, ipfs datasets py logic security llm circuit breaker get circuit breaker, ipfs datasets py logic security llm circuit breaker llmcircuitbreaker, ipfs_datasets_py.logic.observability.structured_logging, ipfs_datasets_py.logic.observability.structured_logging.eventtype, ipfs_datasets_py.logic.observability.structured_logging.filter_logs, ipfs_datasets_py.logic.observability.structured_logging.get_logger, ipfs_datasets_py.logic.observability.structured_logging.jsonlogformatter, ipfs_datasets_py.logic.observability.structured_logging.log_event, ipfs_datasets_py.logic.observability.structured_logging.logcontext, ipfs_datasets_py.logic.observability.structured_logging.parse_json_log_file, ipfs_datasets_py.logic.security.llm_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.circuitbreakeropenerror, ipfs_datasets_py.logic.security.llm_circuit_breaker.circuitstate, ipfs_datasets_py.logic.security.llm_circuit_breaker.get_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.llmcircuitbreaker, json, log context data, log_context_data, logging, os, pathlib, pathlib path, pathlib.path, pytest, slow func, slow_func, success func, success_func, tempfile, test circuit breaker always eventually recovers, test circuit breaker thread safe under concurrent load, test context fields never leak between threads, test empty and edge case sequences, test event types always valid enum members, test failure count monotonic or resets, test json output always parses, test latencies always non negative, test metrics consistency, test state transitions form valid dag, test_circuit_breaker_always_eventually_recovers, test_circuit_breaker_thread_safe_under_concurrent_load, test_context_fields_never_leak_between_threads, test_empty_and_edge_case_sequences, test_event_types_always_valid_enum_members
- AST symbol scope: file
- Goal id: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Missing evidence: Review swallowed exception path in tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:203
- Merge key: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Merge family: tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 640593b50d2e05d7
- Acceptance: Codebase scan filed this finding from tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:203. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-240-codebase-scan-640593b50d2e.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-241 Review swallowed exception path in tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:298

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- Validation: python3 -m py_compile tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- Bundle: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-mcp-unit-test_mcplusplus_v39_session84_properties.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- AST symbols: call sequence, call_sequence, circuit breaker config, circuit_breaker_config, concurrent futures, concurrent futures as completed, concurrent futures threadpoolexecutor, concurrent.futures, concurrent.futures.as_completed, concurrent.futures.threadpoolexecutor, fail func, fail_func, hypothesis, hypothesis assume, hypothesis example, hypothesis given, hypothesis healthcheck, hypothesis settings, hypothesis strategies, hypothesis.assume, hypothesis.example, hypothesis.given, hypothesis.healthcheck, hypothesis.settings, hypothesis.strategies, ipfs datasets py logic observability structured logging, ipfs datasets py logic observability structured logging eventtype, ipfs datasets py logic observability structured logging filter logs, ipfs datasets py logic observability structured logging get logger, ipfs datasets py logic observability structured logging jsonlogformatter, ipfs datasets py logic observability structured logging log event, ipfs datasets py logic observability structured logging logcontext, ipfs datasets py logic observability structured logging parse json log file, ipfs datasets py logic security llm circuit breaker, ipfs datasets py logic security llm circuit breaker circuitbreakeropenerror, ipfs datasets py logic security llm circuit breaker circuitstate, ipfs datasets py logic security llm circuit breaker get circuit breaker, ipfs datasets py logic security llm circuit breaker llmcircuitbreaker, ipfs_datasets_py.logic.observability.structured_logging, ipfs_datasets_py.logic.observability.structured_logging.eventtype, ipfs_datasets_py.logic.observability.structured_logging.filter_logs, ipfs_datasets_py.logic.observability.structured_logging.get_logger, ipfs_datasets_py.logic.observability.structured_logging.jsonlogformatter, ipfs_datasets_py.logic.observability.structured_logging.log_event, ipfs_datasets_py.logic.observability.structured_logging.logcontext, ipfs_datasets_py.logic.observability.structured_logging.parse_json_log_file, ipfs_datasets_py.logic.security.llm_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.circuitbreakeropenerror, ipfs_datasets_py.logic.security.llm_circuit_breaker.circuitstate, ipfs_datasets_py.logic.security.llm_circuit_breaker.get_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.llmcircuitbreaker, json, log context data, log_context_data, logging, os, pathlib, pathlib path, pathlib.path, pytest, slow func, slow_func, success func, success_func, tempfile, test circuit breaker always eventually recovers, test circuit breaker thread safe under concurrent load, test context fields never leak between threads, test empty and edge case sequences, test event types always valid enum members, test failure count monotonic or resets, test json output always parses, test latencies always non negative, test metrics consistency, test state transitions form valid dag, test_circuit_breaker_always_eventually_recovers, test_circuit_breaker_thread_safe_under_concurrent_load, test_context_fields_never_leak_between_threads, test_empty_and_edge_case_sequences, test_event_types_always_valid_enum_members
- AST symbol scope: file
- Goal id: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Missing evidence: Review swallowed exception path in tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:298
- Merge key: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Merge family: tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 9ed9c2dc563c418d
- Acceptance: Codebase scan filed this finding from tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:298. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-241-codebase-scan-9ed9c2dc563c.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-242 Review swallowed exception path in tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:424

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- Validation: python3 -m py_compile tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- Bundle: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-mcp-unit-test_mcplusplus_v39_session84_properties.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- AST symbols: call sequence, call_sequence, circuit breaker config, circuit_breaker_config, concurrent futures, concurrent futures as completed, concurrent futures threadpoolexecutor, concurrent.futures, concurrent.futures.as_completed, concurrent.futures.threadpoolexecutor, fail func, fail_func, hypothesis, hypothesis assume, hypothesis example, hypothesis given, hypothesis healthcheck, hypothesis settings, hypothesis strategies, hypothesis.assume, hypothesis.example, hypothesis.given, hypothesis.healthcheck, hypothesis.settings, hypothesis.strategies, ipfs datasets py logic observability structured logging, ipfs datasets py logic observability structured logging eventtype, ipfs datasets py logic observability structured logging filter logs, ipfs datasets py logic observability structured logging get logger, ipfs datasets py logic observability structured logging jsonlogformatter, ipfs datasets py logic observability structured logging log event, ipfs datasets py logic observability structured logging logcontext, ipfs datasets py logic observability structured logging parse json log file, ipfs datasets py logic security llm circuit breaker, ipfs datasets py logic security llm circuit breaker circuitbreakeropenerror, ipfs datasets py logic security llm circuit breaker circuitstate, ipfs datasets py logic security llm circuit breaker get circuit breaker, ipfs datasets py logic security llm circuit breaker llmcircuitbreaker, ipfs_datasets_py.logic.observability.structured_logging, ipfs_datasets_py.logic.observability.structured_logging.eventtype, ipfs_datasets_py.logic.observability.structured_logging.filter_logs, ipfs_datasets_py.logic.observability.structured_logging.get_logger, ipfs_datasets_py.logic.observability.structured_logging.jsonlogformatter, ipfs_datasets_py.logic.observability.structured_logging.log_event, ipfs_datasets_py.logic.observability.structured_logging.logcontext, ipfs_datasets_py.logic.observability.structured_logging.parse_json_log_file, ipfs_datasets_py.logic.security.llm_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.circuitbreakeropenerror, ipfs_datasets_py.logic.security.llm_circuit_breaker.circuitstate, ipfs_datasets_py.logic.security.llm_circuit_breaker.get_circuit_breaker, ipfs_datasets_py.logic.security.llm_circuit_breaker.llmcircuitbreaker, json, log context data, log_context_data, logging, os, pathlib, pathlib path, pathlib.path, pytest, slow func, slow_func, success func, success_func, tempfile, test circuit breaker always eventually recovers, test circuit breaker thread safe under concurrent load, test context fields never leak between threads, test empty and edge case sequences, test event types always valid enum members, test failure count monotonic or resets, test json output always parses, test latencies always non negative, test metrics consistency, test state transitions form valid dag, test_circuit_breaker_always_eventually_recovers, test_circuit_breaker_thread_safe_under_concurrent_load, test_context_fields_never_leak_between_threads, test_empty_and_edge_case_sequences, test_event_types_always_valid_enum_members
- AST symbol scope: file
- Goal id: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Missing evidence: Review swallowed exception path in tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:424
- Merge key: codebase/quality/tests-mcp-unit-test_mcplusplus_v39_session84_properties
- Merge family: tests/mcp/unit/test_mcplusplus_v39_session84_properties.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: dda87dcfba965181
- Acceptance: Codebase scan filed this finding from tests/mcp/unit/test_mcplusplus_v39_session84_properties.py:424. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-242-codebase-scan-dda87dcfba96.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
