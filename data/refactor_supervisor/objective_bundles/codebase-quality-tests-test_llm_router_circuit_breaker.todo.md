# Codebase Bundle: codebase/quality/tests-test_llm_router_circuit_breaker

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-304 Review swallowed exception path in tests/test_llm_router_circuit_breaker.py:115

- Status: completed
- Completion: manual
- Priority: P1
- Track: quality
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, tests/test_llm_router_circuit_breaker.py
- Validation: python3 -m py_compile tests/test_llm_router_circuit_breaker.py
- Bundle: codebase/quality/tests-test_llm_router_circuit_breaker
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-quality-tests-test_llm_router_circuit_breaker.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/quality
- Graph depth: 1
- Parallel lane: codebase/quality/tests-test_llm_router_circuit_breaker
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: tests/test_llm_router_circuit_breaker.py
- AST symbols: backend with breaker, backend without breaker, backend_with_breaker, backend_without_breaker, backends llm router backend, backends llm router backend llmrouterbackend, backends.llm_router_backend, backends.llm_router_backend.llmrouterbackend, mock generate text, mock_generate_text, pytest, test circuit breaker can be disabled, test circuit breaker state when disabled, test circuit closes after successful half open call, test circuit opens after failure threshold, test circuit transitions to half open after timeout, test manual reset works, test open circuit rejects calls, test reset when disabled is safe, test retryable errors respect circuit breaker, test stats tracking, test successful call keeps circuit closed, test_circuit_breaker_can_be_disabled, test_circuit_breaker_state_when_disabled, test_circuit_closes_after_successful_half_open_call, test_circuit_opens_after_failure_threshold, test_circuit_transitions_to_half_open_after_timeout, test_manual_reset_works, test_open_circuit_rejects_calls, test_reset_when_disabled_is_safe, test_retryable_errors_respect_circuit_breaker, test_stats_tracking, test_successful_call_keeps_circuit_closed, testllmroutercircuitbreaker, testllmroutercircuitbreaker backend with breaker, testllmroutercircuitbreaker backend without breaker, testllmroutercircuitbreaker mock generate text, testllmroutercircuitbreaker test circuit breaker can be disabled, testllmroutercircuitbreaker test circuit breaker state when disabled, testllmroutercircuitbreaker test circuit closes after successful half open call, testllmroutercircuitbreaker test circuit opens after failure threshold, testllmroutercircuitbreaker test circuit transitions to half open after timeout, testllmroutercircuitbreaker test manual reset works, testllmroutercircuitbreaker test open circuit rejects calls, testllmroutercircuitbreaker test reset when disabled is safe, testllmroutercircuitbreaker test retryable errors respect circuit breaker, testllmroutercircuitbreaker test stats tracking, testllmroutercircuitbreaker test successful call keeps circuit closed, testllmroutercircuitbreaker.backend_with_breaker, testllmroutercircuitbreaker.backend_without_breaker, testllmroutercircuitbreaker.mock_generate_text, testllmroutercircuitbreaker.test_circuit_breaker_can_be_disabled, testllmroutercircuitbreaker.test_circuit_breaker_state_when_disabled, testllmroutercircuitbreaker.test_circuit_closes_after_successful_half_open_call, testllmroutercircuitbreaker.test_circuit_opens_after_failure_threshold, testllmroutercircuitbreaker.test_circuit_transitions_to_half_open_after_timeout, testllmroutercircuitbreaker.test_manual_reset_works, testllmroutercircuitbreaker.test_open_circuit_rejects_calls, testllmroutercircuitbreaker.test_reset_when_disabled_is_safe, testllmroutercircuitbreaker.test_retryable_errors_respect_circuit_breaker, testllmroutercircuitbreaker.test_stats_tracking, testllmroutercircuitbreaker.test_successful_call_keeps_circuit_closed, time, unittest mock, unittest mock magicmock, unittest mock patch, unittest.mock, unittest.mock.magicmock, unittest.mock.patch
- AST symbol scope: file
- Goal id: codebase/quality/tests-test_llm_router_circuit_breaker
- Missing evidence: Review swallowed exception path in tests/test_llm_router_circuit_breaker.py:115
- Merge key: codebase/quality/tests-test_llm_router_circuit_breaker
- Merge family: tests/test_llm_router_circuit_breaker.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 3166acdf30e7fc8b
- Acceptance: Codebase scan filed this finding from tests/test_llm_router_circuit_breaker.py:115. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-304-codebase-scan-3166acdf30e7.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
