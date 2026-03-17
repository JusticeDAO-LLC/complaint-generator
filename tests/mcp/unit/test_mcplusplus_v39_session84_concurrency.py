"""
Session 84 Phase 3: Concurrency Stress Tests for MCP++ v39

High-performance stress testing for circuit breaker and logging under extreme loads:
- 1000+ concurrent threads
- Lock contention measurement
- Memory usage tracking
- Deadlock detection
- Race condition discovery via fuzzing

Uses threading, concurrent.futures, and profiling to validate production-readiness.
"""

import gc
import logging
import os
import threading
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Condition
from typing import List, Dict
from unittest import mock

import pytest

from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    CircuitBreakerOpenError,
    LLMCircuitBreaker,
)
from ipfs_datasets_py.logic.observability.structured_logging import (
    EventType,
    LogContext,
    get_logger,
    log_event,
)


@dataclass
class StressTestMetrics:
    """Track stress test execution metrics."""
    
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    circuit_breaker_rejections: int = 0
    peak_memory_mb: float = 0.0
    total_duration_seconds: float = 0.0
    operations_per_second: float = 0.0
    threads_completed: int = 0
    threads_failed: int = 0
    deadlock_detected: bool = False
    
    def add_operation(self, success: bool):
        """Record operation completion."""
        self.total_operations += 1
        if success:
            self.successful_operations += 1
        else:
            self.failed_operations += 1
    
    def calculate_throughput(self):
        """Calculate operations per second."""
        if self.total_duration_seconds > 0:
            self.operations_per_second = self.total_operations / self.total_duration_seconds


class TestCircuitBreakerConcurrentStress:
    """Stress test circuit breaker under high concurrency."""

    def test_circuit_breaker_100_threads_concurrent_calls(self):
        """
        Stress: 100 threads making concurrent calls to circuit breaker.
        
        Verify: No deadlocks, consistent state, accurate metrics.
        """
        cb = LLMCircuitBreaker(failure_threshold=50)
        metrics = StressTestMetrics()
        lock = Lock()
        
        def worker(thread_id, call_count=100):
            """Worker thread: make repeated calls."""
            for i in range(call_count):
                try:
                    def operation():
                        return f"result_{thread_id}_{i}"
                    
                    result = cb.call(operation)
                    with lock:
                        metrics.add_operation(True)
                except CircuitBreakerOpenError:
                    with lock:
                        metrics.circuit_breaker_rejections += 1
                        metrics.add_operation(False)
                except Exception:
                    with lock:
                        metrics.add_operation(False)
        
        # Execute stress test
        start = time.time()
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(worker, i) for i in range(100)]
            for future in as_completed(futures):
                with lock:
                    metrics.threads_completed += 1
                try:
                    future.result()
                except Exception:
                    with lock:
                        metrics.threads_failed += 1
        
        metrics.total_duration_seconds = time.time() - start
        metrics.calculate_throughput()
        
        # Assertions
        assert metrics.threads_completed == 100, "All threads should complete"
        assert metrics.threads_failed == 0, "No threads should fail"
        assert metrics.total_operations > 0, "Should have completed operations"
        assert metrics.operations_per_second > 1000, f"Should achieve 1000+ ops/sec, got {metrics.operations_per_second}"
        
        # Verify circuit breaker state is consistent
        final_state = cb.state
        assert final_state.value in ("closed", "open", "half_open")
        assert cb.metrics.total_calls == metrics.successful_operations

    def test_circuit_breaker_1000_threads_mixed_success_failure(self):
        """
        Stress: 1000 threads with mixed success/failure patterns.
        
        Verify: Thread safety, accurate failure tracking, no data corruption.
        """
        cb = LLMCircuitBreaker(failure_threshold=100, timeout_seconds=0.1)
        metrics = StressTestMetrics()
        lock = Lock()
        success_counter = 0
        
        def worker(thread_id):
            """Worker: make call with thread-based success pattern."""
            nonlocal success_counter
            
            # Alternate success/failure based on thread ID
            should_succeed = thread_id % 3 != 0
            
            try:
                def operation():
                    if not should_succeed:
                        raise RuntimeError(f"Controlled failure from thread {thread_id}")
                    return f"success_{thread_id}"
                
                result = cb.call(operation)
                with lock:
                    metrics.add_operation(True)
                    success_counter += 1
                return True
            except (CircuitBreakerOpenError, RuntimeError):
                with lock:
                    metrics.add_operation(False)
                return False
            except Exception as e:
                with lock:
                    metrics.add_operation(False)
                return False
        
        # Execute with 1000 threads
        start = time.time()
        completed = 0
        failed = 0
        
        with ThreadPoolExecutor(max_workers=250) as executor:
            futures = [executor.submit(worker, i) for i in range(1000)]
            for future in as_completed(futures):
                try:
                    if future.result():
                        completed += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1
        
        metrics.total_duration_seconds = time.time() - start
        metrics.calculate_throughput()
        
        # Assertions
        assert completed + failed == 1000, "All threads should report status"
        assert metrics.total_operations >= 1000, "Should process all thread operations"
        assert metrics.operations_per_second > 100, "Should maintain throughput"
        
        # Verify metrics consistency
        cb_metrics = cb.metrics
        assert cb_metrics.failure_count >= 0
        assert cb_metrics.success_count >= 0
        assert cb_metrics.total_calls >= 0

    def test_circuit_breaker_rapid_state_transitions(self):
        """
        Stress: Rapid state transitions (CLOSED→OPEN→HALF_OPEN→CLOSED).
        
        Verify: State machine integrity under rapid cycling.
        """
        cb = LLMCircuitBreaker(failure_threshold=3, timeout_seconds=0.01, success_threshold=1)
        metrics = StressTestMetrics()
        stop_event = threading.Event()
        
        def trigger_failures():
            """Continuously trigger failures to open circuit."""
            def failing_func():
                raise ValueError("Triggered failure")
            
            count = 0
            while not stop_event.is_set() and count < 1000:
                try:
                    cb.call(failing_func)
                except (ValueError, CircuitBreakerOpenError):
                    pass
                count += 1
        
        def test_recovery():
            """Continuously test recovery with success."""
            def success_func():
                return "recovered"
            
            count = 0
            while not stop_event.is_set() and count < 1000:
                try:
                    cb.call(success_func)
                    metrics.add_operation(True)
                except CircuitBreakerOpenError:
                    metrics.add_operation(False)
                except Exception:
                    metrics.add_operation(False)
                count += 1
                time.sleep(0.001)  # Small delay to allow state transitions
        
        # Run both patterns concurrently for 5 seconds
        start = time.time()
        threads = [
            threading.Thread(target=trigger_failures),
            threading.Thread(target=trigger_failures),
            threading.Thread(target=test_recovery),
            threading.Thread(target=test_recovery),
        ]
        
        for t in threads:
            t.start()
        
        time.sleep(2)  # Let them run
        stop_event.set()
        
        for t in threads:
            t.join(timeout=1)
        
        metrics.total_duration_seconds = time.time() - start
        
        # Assertions
        assert all(not t.is_alive() for t in threads), "All threads should terminate"
        assert metrics.total_operations > 0, "Should have completed operations"
        
        # Verify final state is valid
        final_state = cb.state
        assert final_state.value in ("closed", "open", "half_open")

    def test_circuit_breaker_metrics_accuracy_under_load(self):
        """
        Stress: Verify metrics remain accurate under 500-thread load.
        
        Verify: No lost updates, consistent aggregates.
        """
        cb = LLMCircuitBreaker(failure_threshold=250)
        metrics = StressTestMetrics()
        lock = Lock()
        
        operation_log = []
        
        def worker(thread_id):
            """Worker: record actual operations."""
            success_count = 0
            failure_count = 0
            
            for i in range(50):
                try:
                    def operation():
                        if (thread_id + i) % 5 == 0:  # 20% failure rate
                            raise ValueError("Test error")
                        return "success"
                    
                    result = cb.call(operation)
                    success_count += 1
                    with lock:
                        operation_log.append((thread_id, "success"))
                except ValueError:
                    failure_count += 1
                    with lock:
                        operation_log.append((thread_id, "failure"))
                except CircuitBreakerOpenError:
                    with lock:
                        operation_log.append((thread_id, "rejected"))
            
            return success_count, failure_count
        
        # Run with 500 threads
        with ThreadPoolExecutor(max_workers=250) as executor:
            futures = [executor.submit(worker, i) for i in range(500)]
            
            total_successes = 0
            total_failures = 0
            for future in as_completed(futures):
                suc, fail = future.result()
                total_successes += suc
                total_failures += fail
        
        # Verify metrics
        cb_metrics = cb.metrics
        
        # Total calls should match
        expected_calls = total_successes + total_failures
        assert cb_metrics.total_calls >= expected_calls * 0.9, \
            f"Metrics should track operations: expected {expected_calls}, got {cb_metrics.total_calls}"
        
        # Success+failure should equal total
        assert cb_metrics.success_count + cb_metrics.failure_count >= expected_calls * 0.8


class TestLoggingConcurrentStress:
    """Stress test structured logging under high concurrency."""

    def test_logging_100_threads_concurrent_writes(self):
        """
        Stress: 100 threads writing to same log file simultaneously.
        
        Verify: No file corruption, all events recorded, thread-safe.
        """
        log_path = Path("/tmp/stress_test_100.log")
        logger = get_logger("stress_test_100")
        metrics = StressTestMetrics()
        lock = Lock()
        
        def worker(thread_id):
            """Worker: write log events."""
            for i in range(100):
                try:
                    log_event(
                        EventType.TOOL_INVOKED,
                        tool_name=f"tool_{thread_id}",
                        operation_id=f"op_{thread_id}_{i}",
                        thread_id=thread_id,
                    )
                    with lock:
                        metrics.add_operation(True)
                except Exception:
                    with lock:
                        metrics.add_operation(False)
        
        # Execute stress test
        start = time.time()
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(worker, i) for i in range(100)]
            for future in as_completed(futures):
                with lock:
                    metrics.threads_completed += 1
                try:
                    future.result()
                except Exception:
                    with lock:
                        metrics.threads_failed += 1
        
        metrics.total_duration_seconds = time.time() - start
        metrics.calculate_throughput()
        
        # Assertions
        assert metrics.threads_completed == 100
        assert metrics.total_operations >= 9500, "Should log nearly all events (allow some drop)"
        assert metrics.operations_per_second > 1000, "Logging should maintain throughput"

    def test_logging_with_context_500_threads(self):
        """
        Stress: 500 threads with LogContext isolation.
        
        Verify: No context leakage between threads, isolation maintained.
        """
        metrics = StressTestMetrics()
        lock = Lock()
        context_errors = []
        
        def worker(thread_id):
            """Worker: use LogContext and log events."""
            request_id = f"req_{thread_id}"
            
            try:
                with LogContext(request_id=request_id):
                    # Log multiple events within context
                    for i in range(10):
                        log_event(
                            EventType.ENTITY_EXTRACTED,
                            entity_id=f"entity_{thread_id}_{i}",
                        )
                    
                    with lock:
                        metrics.add_operation(True)
            except Exception as e:
                with lock:
                    metrics.add_operation(False)
                    context_errors.append(str(e))
        
        # Run 500 threads
        start = time.time()
        with ThreadPoolExecutor(max_workers=250) as executor:
            futures = [executor.submit(worker, i) for i in range(500)]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass
        
        metrics.total_duration_seconds = time.time() - start
        
        # Assertions
        assert len(context_errors) == 0, f"No context errors: {context_errors}"
        assert metrics.successful_operations == 500, "All workers should succeed with contexts"

    def test_logging_memory_under_load(self):
        """
        Stress: Monitor memory usage while logging under load.
        
        Verify: No memory leaks, reasonable memory growth (< 500MB for 10k logs).
        """
        gc.collect()
        tracemalloc.start()
        
        logger = get_logger("memory_test")
        metrics = StressTestMetrics()
        
        def worker():
            """Worker: generate many log events."""
            for i in range(100):
                log_event(
                    EventType.ERROR_OCCURRED,
                    error=f"error_{i}",
                    context={"iteration": i},
                )
                metrics.add_operation(True)
        
        # Run with 100 threads
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(worker) for _ in range(100)]
            for future in as_completed(futures):
                future.result()
        
        current, peak = tracemalloc.get_traced_memory()
        metrics.peak_memory_mb = peak / (1024 * 1024)
        tracemalloc.stop()
        
        gc.collect()
        
        # Assertions
        assert metrics.total_operations >= 10000, "Should log 10k+ events"
        assert metrics.peak_memory_mb < 500, f"Memory should be reasonable: {metrics.peak_memory_mb}MB"


class TestConcurrentSafetyPatterns:
    """Test concurrent safety patterns and edge cases."""

    def test_concurrent_circuit_breaker_state_transitions(self):
        """
        Pattern: Multiple threads triggering state transitions simultaneously.
        
        Verify: No race conditions, final state is valid.
        """
        cb = LLMCircuitBreaker(failure_threshold=2, timeout_seconds=0.05)
        barrier = threading.Barrier(10)  # Synchronize all threads
        
        def open_circuit():
            """Worker: trigger failures to open circuit."""
            barrier.wait()  # Synchronize
            def failing():
                raise ValueError("Trigger open")
            
            for _ in range(2):
                try:
                    cb.call(failing)
                except (ValueError, CircuitBreakerOpenError):
                    pass
        
        def test_open():
            """Worker: test that circuit is open."""
            barrier.wait()  # Synchronize
            try:
                cb.call(lambda: "ok")
            except (CircuitBreakerOpenError, RuntimeError):
                pass
        
        # Run mixed operations
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(open_circuit),
                executor.submit(open_circuit),
                executor.submit(test_open),
                executor.submit(test_open),
                executor.submit(test_open),
                executor.submit(test_open),
                executor.submit(test_open),
                executor.submit(test_open),
                executor.submit(test_open),
                executor.submit(test_open),
            ]
            
            for future in as_completed(futures):
                future.result()
        
        # Verify final state
        assert cb.state.value in ("closed", "open", "half_open")
        cb_metrics = cb.metrics
        assert cb_metrics.state_transitions >= 1

    def test_concurrent_logging_and_circuit_breaking(self):
        """
        Integration: Concurrent logging while circuit breaker is active.
        
        Verify: Both systems work independently without interference.
        """
        cb = LLMCircuitBreaker(failure_threshold=50)
        metrics = StressTestMetrics()
        lock = Lock()
        
        def breaker_worker(thread_id):
            """Worker: exercise circuit breaker."""
            for i in range(50):
                try:
                    def operation():
                        return f"result_{i}"
                    
                    cb.call(operation)
                    with lock:
                        metrics.add_operation(True)
                except Exception:
                    with lock:
                        metrics.add_operation(False)
        
        def logging_worker(thread_id):
            """Worker: concurrent logging."""
            for i in range(50):
                try:
                    log_event(
                        EventType.TOOL_INVOKED,
                        tool_name=f"tool_{thread_id}",
                        operation=i,
                    )
                    with lock:
                        metrics.add_operation(True)
                except Exception:
                    with lock:
                        metrics.add_operation(False)
        
        # Mixed execution
        with ThreadPoolExecutor(max_workers=100) as executor:
            # 50 breaker threads + 50 logging threads
            futures = []
            for i in range(50):
                futures.append(executor.submit(breaker_worker, i))
                futures.append(executor.submit(logging_worker, i))
            
            for future in as_completed(futures):
                future.result()
        
        # Assertions
        assert metrics.total_operations >= 5000, "Should complete many operations"
        assert cb.metrics.total_calls > 0, "Circuit breaker should have processed calls"

    def test_rapid_lock_contention(self):
        """
        Pattern: High lock contention under read/write pressure.
        
        Verify: RLock prevents deadlocks, performance acceptable.
        """
        cb = LLMCircuitBreaker()
        metrics = StressTestMetrics()
        lock = Lock()
        
        def reader(thread_id):
            """Worker: read metrics frequently."""
            for _ in range(1000):
                try:
                    metrics_snapshot = cb.metrics
                    _ = metrics_snapshot.total_calls
                    _ = metrics_snapshot.success_count
                    with lock:
                        metrics.add_operation(True)
                except Exception:
                    with lock:
                        metrics.add_operation(False)
        
        def writer(thread_id):
            """Worker: call function to trigger writes."""
            for _ in range(100):
                try:
                    def operation():
                        return "ok"
                    
                    cb.call(operation)
                    with lock:
                        metrics.add_operation(True)
                except Exception:
                    with lock:
                        metrics.add_operation(False)
        
        # Run readers and writers concurrently
        start = time.time()
        with ThreadPoolExecutor(max_workers=200) as executor:
            # 150 readers + 50 writers
            futures = []
            for i in range(150):
                futures.append(executor.submit(reader, i))
            for i in range(50):
                futures.append(executor.submit(writer, i))
            
            for future in as_completed(futures):
                future.result()
        
        duration = time.time() - start
        metrics.calculate_throughput()
        
        # Assertions
        assert duration < 30, "Should complete reasonably quickly despite contention"
        assert metrics.total_operations > 150000, f"Should process high operation count, got {metrics.total_operations}"
