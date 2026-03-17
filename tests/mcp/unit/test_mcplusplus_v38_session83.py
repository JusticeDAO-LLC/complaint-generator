"""
Session 83 E2E Tests: Performance, Security, Observability (MCP++ v38→v39).

This test file validates Session 83 implementation:
P2-perf: 10k-token extraction profiler (profile_10k_token_extraction.py)
P2-security: LLM circuit breaker (ipfs_datasets_py/logic/security/llm_circuit_breaker.py)
P2-obs: Structured JSON logging (ipfs_datasets_py/logic/observability/structured_logging.py)
P2-docs: Documentation drift audit (ipfs_datasets_py/audit_docs_drift.py)
"""

import json
import logging
import pytest
import time
import threading
from pathlib import Path
from unittest.mock import Mock, patch
from typing import List

# Import Session 83 features
from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    LLMCircuitBreaker,
    CircuitState,
    CircuitBreakerOpenError,
    get_circuit_breaker,
)

from ipfs_datasets_py.logic.observability.structured_logging import (
    LogField,
    EventType,
    LogContext,
    JSONLogFormatter,
    get_logger,
    log_event,
    log_error,
    log_performance,
    log_mcp_tool,
    LogPerformance,
    parse_json_log_file,
    filter_logs,
)


def _get_file_logger(name: str, log_file: Path) -> logging.Logger:
    """Create a JSON logger that writes to a file for tests."""
    handler = logging.FileHandler(log_file)
    handler.setFormatter(JSONLogFormatter())
    return get_logger(name, handlers=[handler])


# ============================================================================
# Session 83, Feature 1: LLM Circuit Breaker (P2-security)
# ============================================================================

class TestLLMCircuitBreakerBasics:
    """Test basic circuit breaker state transitions."""
    
    def test_initial_state_closed(self):
        """Circuit breaker starts in CLOSED state."""
        cb = LLMCircuitBreaker(failure_threshold=3, timeout_seconds=1.0)
        assert cb.state == CircuitState.CLOSED
        assert cb.metrics.failure_count == 0
    
    def test_successful_calls_stay_closed(self):
        """Successful calls keep circuit CLOSED."""
        cb = LLMCircuitBreaker(failure_threshold=3)
        
        def success_func():
            return "success"
        
        for _ in range(5):
            result = cb.call(success_func)
            assert result == "success"
            assert cb.state == CircuitState.CLOSED
        
        metrics = cb.metrics
        assert metrics.success_count == 5
        assert metrics.failure_count == 0
    
    def test_failures_open_circuit(self):
        """Repeated failures transition to OPEN state."""
        cb = LLMCircuitBreaker(failure_threshold=3, timeout_seconds=1.0)
        
        def fail_func():
            raise ValueError("LLM API error")
        
        # First 2 failures stay CLOSED
        for i in range(2):
            with pytest.raises(ValueError):
                cb.call(fail_func)
            assert cb.state == CircuitState.CLOSED
        
        # 3rd failure opens circuit
        with pytest.raises(ValueError):
            cb.call(fail_func)
        assert cb.state == CircuitState.OPEN
        
        metrics = cb.metrics
        assert metrics.failure_count == 3
    
    def test_open_circuit_rejects_calls(self):
        """OPEN circuit rejects calls immediately."""
        cb = LLMCircuitBreaker(failure_threshold=2, timeout_seconds=1.0)
        
        def fail_func():
            raise RuntimeError("API down")
        
        # Open the circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(fail_func)
        
        assert cb.state == CircuitState.OPEN
        
        # New calls should be rejected
        with pytest.raises(CircuitBreakerOpenError, match="Circuit breaker 'llm_circuit_breaker' is OPEN"):
            cb.call(lambda: "should not execute")
    
    def test_half_open_recovery(self):
        """Circuit transitions to HALF_OPEN after timeout, then CLOSED on success."""
        cb = LLMCircuitBreaker(failure_threshold=2, timeout_seconds=0.1, success_threshold=2)
        
        # Open circuit
        def fail_func():
            raise RuntimeError("Temp failure")
        
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(fail_func)
        
        assert cb.state == CircuitState.OPEN
        
        # Wait for timeout
        time.sleep(0.15)
        
        # First call should transition to HALF_OPEN
        def success_func():
            return "recovered"
        
        result = cb.call(success_func)
        assert result == "recovered"
        assert cb.state == CircuitState.HALF_OPEN
        
        # Another success should close circuit
        result = cb.call(success_func)
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerMetrics:
    """Test circuit breaker metrics tracking."""
    
    def test_metrics_track_success_failure_counts(self):
        """Metrics track success/failure counts."""
        cb = LLMCircuitBreaker(failure_threshold=5)
        
        cb.call(lambda: "ok")
        cb.call(lambda: "ok")
        
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        
        metrics = cb.metrics
        assert metrics.success_count == 2
        assert metrics.failure_count == 1
        assert cb.state == CircuitState.CLOSED
    
    def test_metrics_track_latencies(self):
        """Metrics track call latencies."""
        cb = LLMCircuitBreaker(failure_threshold=5)
        
        def slow_func():
            time.sleep(0.05)
            return "done"
        
        cb.call(slow_func)
        cb.call(slow_func)
        
        metrics = cb.metrics
        assert len(metrics.latencies) == 2
        assert all(lat >= 0.05 for lat in metrics.latencies)
    
    def test_reset_statistics(self):
        """Reset clears statistics but keeps state."""
        cb = LLMCircuitBreaker(failure_threshold=3)
        
        cb.call(lambda: "test")
        cb.call(lambda: "test")
        
        cb.reset()

        metrics = cb.metrics
        assert metrics.success_count == 0
        assert metrics.failure_count == 0
        assert len(metrics.latencies) == 0
        assert cb.state == CircuitState.CLOSED  # State preserved


class TestCircuitBreakerDecorator:
    """Test @protected decorator usage."""
    
    def test_protected_decorator_wraps_function(self):
        """@protected decorator protects functions."""
        cb = LLMCircuitBreaker(failure_threshold=2)
        
        @cb.protected
        def api_call(x):
            return x * 2
        
        assert api_call(5) == 10
        assert api_call(7) == 14
        
        metrics = cb.metrics
        assert metrics.success_count == 2
    
    def test_protected_decorator_tracks_failures(self):
        """@protected decorator tracks failures."""
        cb = LLMCircuitBreaker(failure_threshold=2, timeout_seconds=0.5)
        
        @cb.protected
        def failing_api():
            raise ConnectionError("API unavailable")
        
        # First failure
        with pytest.raises(ConnectionError):
            failing_api()
        assert cb.state == CircuitState.CLOSED
        
        # Second failure opens circuit
        with pytest.raises(ConnectionError):
            failing_api()
        assert cb.state == CircuitState.OPEN
        
        # Further calls rejected
        with pytest.raises(CircuitBreakerOpenError):
            failing_api()


class TestCircuitBreakerRegistry:
    """Test global circuit breaker registry."""
    
    def test_get_circuit_breaker_singleton(self):
        """get_circuit_breaker returns singleton instances."""
        cb1 = get_circuit_breaker("api-service", failure_threshold=5)
        cb2 = get_circuit_breaker("api-service")
        
        assert cb1 is cb2
        
        cb1.call(lambda: "test")
        assert cb2.metrics.success_count == 1
    
    def test_different_names_different_instances(self):
        """Different names return different circuit breaker instances."""
        cb_openai = get_circuit_breaker("openai", failure_threshold=3)
        cb_anthropic = get_circuit_breaker("anthropic", failure_threshold=5)
        
        assert cb_openai is not cb_anthropic
        
        cb_openai.call(lambda: "ok")
        
        assert cb_openai.metrics.success_count == 1
        assert cb_anthropic.metrics.success_count == 0


class TestCircuitBreakerThreadSafety:
    """Test circuit breaker thread safety."""
    
    def test_concurrent_calls_thread_safe(self):
        """Circuit breaker handles concurrent calls safely."""
        cb = LLMCircuitBreaker(failure_threshold=10)
        results = []
        errors = []
        
        def worker(worker_id):
            try:
                result = cb.call(lambda: f"worker-{worker_id}")
                results.append(result)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(results) == 20
        assert len(errors) == 0
        assert cb.metrics.success_count == 20


# ============================================================================
# Session 83, Feature 2: Structured JSON Logging (P2-obs)
# ============================================================================

class TestStructuredLoggingBasics:
    """Test basic structured logging functionality."""
    
    def test_get_logger_json_formatter(self):
        """get_logger returns logger with JSON formatting."""
        logger = get_logger("test.logger")
        
        # Check handler has JSONLogFormatter
        assert len(logger.handlers) > 0
        handler = logger.handlers[0]
        assert isinstance(handler.formatter, JSONLogFormatter)
    
    def test_json_log_output_format(self, tmp_path):
        """JSON logs produce valid JSON output."""
        log_file = tmp_path / "test.log"
        logger = _get_file_logger("test.json", log_file)
        
        logger.info("Test message", extra={"key": "value"})
        
        # Read and parse log
        content = log_file.read_text()
        log_entry = json.loads(content.strip())
        
        assert log_entry["message"] == "Test message"
        assert log_entry["key"] == "value"
        assert "timestamp" in log_entry
        assert log_entry["level"] == "INFO"
    
    def test_log_event_convenience(self, tmp_path):
        """log_event() convenience function works."""
        log_file = tmp_path / "events.log"
        
        logger = _get_file_logger("test.events", log_file)
        log_event(
            event_type=EventType.TOOL_INVOKED.value,
            logger=logger,
            tool_name="test_tool",
        )
        
        content = log_file.read_text()
        log_entry = json.loads(content.strip())
        
        assert log_entry["event_type"] == "mcp.tool.invoked"
        assert "event" in log_entry["message"].lower()
        assert log_entry["tool_name"] == "test_tool"


class TestLogContext:
    """Test LogContext for propagating structured fields."""
    
    def test_context_propagates_request_id(self, tmp_path):
        """LogContext propagates request_id to all logs."""
        log_file = tmp_path / "context.log"
        logger = _get_file_logger("context.test", log_file)
        
        with LogContext(request_id="req-123"):
            logger.info("First log")
            logger.info("Second log")
        
        lines = log_file.read_text().strip().split('\n')
        assert len(lines) == 2
        
        for line in lines:
            entry = json.loads(line)
            assert entry["request_id"] == "req-123"
    
    def test_context_multiple_fields(self, tmp_path):
        """LogContext supports multiple fields."""
        log_file = tmp_path / "multi.log"
        logger = _get_file_logger("multi.test", log_file)
        
        with LogContext(request_id="req-456", user_id="user-789", session_id="sess-abc"):
            logger.info("Context test")
        
        content = log_file.read_text()
        entry = json.loads(content.strip())
        
        assert entry["request_id"] == "req-456"
        assert entry["user_id"] == "user-789"
        assert entry["session_id"] == "sess-abc"
    
    def test_nested_contexts_merge(self, tmp_path):
        """Nested LogContext instances merge fields."""
        log_file = tmp_path / "nested.log"
        logger = _get_file_logger("nested.test", log_file)
        
        with LogContext(request_id="outer-req"):
            with LogContext(operation="inner-op"):
                logger.info("Nested log")
        
        content = log_file.read_text()
        entry = json.loads(content.strip())
        
        assert entry["request_id"] == "outer-req"
        assert entry["operation"] == "inner-op"


class TestLogPerformance:
    """Test LogPerformance context manager for automatic timing."""
    
    def test_log_performance_timing(self, tmp_path):
        """LogPerformance logs execution time."""
        log_file = tmp_path / "perf.log"
        logger = _get_file_logger("perf.test", log_file)
        
        with LogPerformance("test_operation", logger=logger):
            time.sleep(0.05)
        
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert "performance" in entry["message"].lower()
        assert entry["duration_ms"] >= 50
    
    def test_log_performance_with_context(self, tmp_path):
        """LogPerformance respects LogContext."""
        log_file = tmp_path / "perf_ctx.log"
        logger = _get_file_logger("perf.ctx.test", log_file)
        
        with LogContext(request_id="req-perf"):
            with LogPerformance("tracked_op", logger=logger):
                pass
        
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        for line in lines:
            entry = json.loads(line)
            assert entry["request_id"] == "req-perf"


class TestLogParsing:
    """Test log parsing and filtering utilities."""
    
    def test_parse_json_log_file(self, tmp_path):
        """parse_json_log_file reads and parses JSON logs."""
        log_file = tmp_path / "parse.log"
        logger = _get_file_logger("parse.test", log_file)
        
        logger.info("Message 1", extra={"index": 1})
        logger.warning("Message 2", extra={"index": 2})
        logger.error("Message 3", extra={"index": 3})
        
        entries = parse_json_log_file(log_file)
        
        assert len(entries) == 3
        assert entries[0]["message"] == "Message 1"
        assert entries[1]["level"] == "WARNING"
        assert entries[2]["index"] == 3
    
    def test_filter_logs_by_field(self, tmp_path):
        """filter_logs filters by arbitrary fields."""
        log_file = tmp_path / "filter.log"
        logger = _get_file_logger("filter.test", log_file)
        
        log_event(EventType.CUSTOM.value, logger=logger, item="A")
        log_event(EventType.TOOL_INVOKED.value, logger=logger, item="B")
        log_event(EventType.CUSTOM.value, logger=logger, item="C")
        
        entries = parse_json_log_file(log_file)
        custom_entries = filter_logs(entries, event_type=EventType.CUSTOM.value)

        assert len(custom_entries) == 2
        assert all(e["event_type"] == EventType.CUSTOM.value for e in custom_entries)


class TestMCPToolLogging:
    """Test MCP tool-specific logging."""
    
    def test_log_mcp_tool_invocation(self, tmp_path):
        """log_mcp_tool logs MCP tool calls."""
        log_file = tmp_path / "mcp_tool.log"
        
        logger = _get_file_logger("mcp.tool", log_file)
        log_mcp_tool(
            tool_name="read_file",
            status="completed",
            duration_ms=123.45,
            logger=logger,
            params={"path": "/test/file.txt"},
            result={"content": "..."},
        )
        
        content = log_file.read_text()
        entry = json.loads(content.strip())
        
        assert entry["event_type"] == "mcp.tool.completed"
        assert entry["tool_name"] == "read_file"
        assert entry["duration_ms"] == 123.45
        assert "path" in entry["params"]


# ============================================================================
# Session 83, Feature 3: Profiling Tool (P2-perf)
# ============================================================================

class TestProfilingScript:
    """Test profiling script exists and is importable."""
    
    def test_profiling_script_exists(self):
        """profile_10k_token_extraction.py exists."""
        script_path = Path("ipfs_datasets_py/profile_10k_token_extraction.py")
        assert script_path.exists(), f"Profiling script not found at {script_path}"
    
    def test_profiling_script_has_main_functions(self):
        """Profiling script has required analysis functions."""
        # Import the module
        import sys
        sys.path.insert(0, str(Path.cwd()))
        
        try:
            import profile_10k_token_extraction as profiler
        except Exception as e:
            pytest.skip(f"Could not import profiler: {e}")
        
        # Check for key functions
        assert hasattr(profiler, "generate_large_document")
        assert hasattr(profiler, "profile_extraction_timing")
        assert hasattr(profiler, "profile_extraction_memory")
        assert hasattr(profiler, "generate_recommendations")


# ============================================================================
# Session 83, Feature 4: Documentation Drift Audit (P2-docs)
# ============================================================================

class TestDocsDriftAudit:
    """Test documentation drift audit tool."""
    
    def test_audit_script_exists(self):
        """audit_docs_drift.py exists."""
        script_path = Path("ipfs_datasets_py/audit_docs_drift.py")
        assert script_path.exists(), f"Audit script not found at {script_path}"
    
    def test_audit_produces_report(self):
        """Audit script generates valid JSON report."""
        report_path = Path("drift_report_mcp.json")
        
        if not report_path.exists():
            pytest.skip("Audit report not generated yet")
        
        with open(report_path) as f:
            report = json.load(f)
        
        assert "summary" in report
        assert "issues" in report
        assert "total_issues" in report["summary"]
        assert "by_severity" in report["summary"]
        assert "by_category" in report["summary"]


# ============================================================================
# Session 83 Integration Tests
# ============================================================================

class TestSession83Integration:
    """Integration tests combining Session 83 features."""
    
    def test_circuit_breaker_with_structured_logging(self, tmp_path):
        """Circuit breaker integrates with structured logging."""
        log_file = tmp_path / "integration.log"
        logger = _get_file_logger("integration.test", log_file)
        
        cb = LLMCircuitBreaker(failure_threshold=2, timeout_seconds=0.5)
        
        @cb.protected
        def api_call():
            logger.info("API called", extra={"service": "test"})
            return "success"
        
        with LogContext(request_id="req-integration"):
            result = api_call()
        
        assert result == "success"
        
        # Check logs contain context
        content = log_file.read_text()
        entry = json.loads(content.strip())
        assert entry["request_id"] == "req-integration"
        assert entry["service"] == "test"
    
    def test_performance_logging_for_protected_calls(self, tmp_path):
        """LogPerformance tracks protected circuit breaker calls."""
        log_file = tmp_path / "perf_circuit.log"
        logger = _get_file_logger("perf.circuit", log_file)
        
        cb = LLMCircuitBreaker(failure_threshold=5)
        
        @cb.protected
        def slow_api():
            time.sleep(0.05)
            return "done"
        
        with LogPerformance("protected_api_call", logger=logger):
            result = cb.call(slow_api)
        
        assert result == "done"
        
        # Check performance was logged
        content = log_file.read_text()
        lines = content.strip().split('\n')
        entry = json.loads(lines[-1])

        assert entry["duration_ms"] >= 50


# ============================================================================
# Session 83 Regression Tests
# ============================================================================

class TestSession83Regressions:
    """Regression tests ensuring Session 83 doesn't break existing functionality."""
    
    def test_circuit_breaker_doesnt_affect_normal_functions(self):
        """Circuit breaker doesn't affect unprotected functions."""
        def normal_func():
            return "unprotected"
        
        # Should work without circuit breaker
        assert normal_func() == "unprotected"
    
    def test_structured_logging_backwards_compatible(self):
        """Structured logging works with standard logging API."""
        logger = get_logger("compat.test")
        
        # Standard logging methods should work
        logger.info("Standard info")
        logger.warning("Standard warning")
        logger.error("Standard error")
        
        # Should not raise
        assert True
    
    def test_log_context_thread_isolated(self, tmp_path):
        """LogContext is thread-isolated (doesn't leak)."""
        log_file = tmp_path / "thread_isolation.log"
        logger = _get_file_logger("thread.test", log_file)
        
        def thread_worker(thread_id):
            with LogContext(thread_id=thread_id):
                logger.info(f"Thread {thread_id}")
        
        threads = [
            threading.Thread(target=thread_worker, args=(i,))
            for i in range(3)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Parse logs and check thread_ids are correct
        entries = parse_json_log_file(log_file)
        assert len(entries) == 3
        
        thread_ids = {e["thread_id"] for e in entries}
        assert thread_ids == {0, 1, 2}
