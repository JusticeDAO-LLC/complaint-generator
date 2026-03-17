"""Tests for circuit-breaker pattern implementation.

Covers state transitions, failure tracking, recovery behavior, and metrics.
"""

import time
import pytest
from ipfs_datasets_py.optimizers.common.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    CircuitBreakerMetrics,
    circuit_breaker,
)


class TestCircuitBreakerBasics:
    """Test basic circuit-breaker creation and properties."""

    def test_init_default_parameters(self):
        """Test circuit-breaker initializes with correct defaults."""
        breaker = CircuitBreaker()
        assert breaker.name == "circuit_breaker"
        assert breaker.failure_threshold == 5
        assert breaker.recovery_timeout == 60.0
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_active is True

    def test_init_custom_parameters(self):
        """Test circuit-breaker initializes with custom parameters."""
        breaker = CircuitBreaker(
            name="test_cb",
            failure_threshold=3,
            recovery_timeout=30.0,
            expected_exception=ValueError,
        )
        assert breaker.name == "test_cb"
        assert breaker.failure_threshold == 3
        assert breaker.recovery_timeout == 30.0
        assert breaker.expected_exception is ValueError

    def test_initial_metrics(self):
        """Test initial metrics are zeroed."""
        breaker = CircuitBreaker()
        metrics = breaker.metrics()
        assert metrics.total_calls == 0
        assert metrics.successful_calls == 0
        assert metrics.failed_calls == 0
        assert metrics.rejected_calls == 0
        assert metrics.success_rate == 0.0
        assert metrics.failure_rate == 0.0


class TestCircuitBreakerClosedState:
    """Test circuit-breaker behavior in CLOSED state."""

    def test_successful_call(self):
        """Test successful call passes through in CLOSED state."""
        breaker = CircuitBreaker()

        def func_ok():
            return "success"

        result = breaker._execute(func_ok, (), {})
        assert result == "success"

        metrics = breaker.metrics()
        assert metrics.total_calls == 1
        assert metrics.successful_calls == 1
        assert metrics.failed_calls == 0
        assert metrics.success_rate == 100.0

    def test_single_failure_increments_counter(self):
        """Test single failure increments failure counter but stays CLOSED."""
        breaker = CircuitBreaker(failure_threshold=3)

        def func_fail():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})

        assert breaker.state == CircuitState.CLOSED  # Still CLOSED
        metrics = breaker.metrics()
        assert metrics.total_calls == 1
        assert metrics.failed_calls == 1
        assert metrics.success_rate == 0.0
        assert metrics.failure_rate == 100.0

    def test_threshold_not_exceeded_stays_closed(self):
        """Test circuit stays CLOSED until threshold is exceeded."""
        breaker = CircuitBreaker(failure_threshold=3)

        def func_fail():
            raise ValueError("test error")

        # Two failures, threshold is 3
        for _ in range(2):
            with pytest.raises(ValueError):
                breaker._execute(func_fail, (), {})

        assert breaker.state == CircuitState.CLOSED
        metrics = breaker.metrics()
        assert metrics.failed_calls == 2

    def test_failure_counter_resets_on_success(self):
        """Test failure counter resets after successful call."""
        breaker = CircuitBreaker(failure_threshold=3)

        def func_fail():
            raise ValueError("test error")

        def func_ok():
            return "success"

        # Two failures
        for _ in range(2):
            with pytest.raises(ValueError):
                breaker._execute(func_fail, (), {})

        assert breaker.state == CircuitState.CLOSED

        # Successful call resets counter
        breaker._execute(func_ok, (), {})
        assert breaker.state == CircuitState.CLOSED

        # Now need 3 more failures to open
        for _ in range(2):
            with pytest.raises(ValueError):
                breaker._execute(func_fail, (), {})

        assert breaker.state == CircuitState.CLOSED  # Still needs 1 more


class TestCircuitBreakerTransitionToOpen:
    """Test transition from CLOSED to OPEN state."""

    def test_open_on_threshold_exceeded(self):
        """Test circuit opens when failure threshold is exceeded."""
        breaker = CircuitBreaker(failure_threshold=3)

        def func_fail():
            raise ValueError("test error")

        # Fail exactly threshold times
        for _ in range(3):
            with pytest.raises(ValueError):
                breaker._execute(func_fail, (), {})

        assert breaker.state == CircuitState.OPEN

    def test_state_change_recorded(self):
        """Test state changes are recorded in metrics."""
        breaker = CircuitBreaker(failure_threshold=2)

        def func_fail():
            raise ValueError("test error")

        assert breaker.metrics().state_changes == 0

        for _ in range(2):
            with pytest.raises(ValueError):
                breaker._execute(func_fail, (), {})

        assert breaker.metrics().state_changes == 1  # CLOSED → OPEN

    def test_opened_at_timestamp_set(self):
        """Test opened_at timestamp is set when opening."""
        breaker = CircuitBreaker(failure_threshold=1)

        def func_fail():
            raise ValueError("test error")

        assert breaker._opened_at is None

        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})

        assert breaker._opened_at is not None
        assert isinstance(breaker._opened_at, float)
        assert breaker._opened_at <= time.time()


class TestCircuitBreakerOpenState:
    """Test circuit-breaker behavior in OPEN state."""

    def test_open_circuit_rejects_calls(self):
        """Test calls are rejected immediately when circuit is OPEN."""
        breaker = CircuitBreaker(failure_threshold=1)

        def func_fail():
            raise ValueError("test error")

        def func_ok():
            return "success"

        # Open the circuit
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})

        assert breaker.state == CircuitState.OPEN

        # All subsequent calls rejected, even ones that would succeed
        with pytest.raises(CircuitBreakerOpen):
            breaker._execute(func_ok, (), {})

    def test_open_circuit_tracks_rejections(self):
        """Test rejected calls are tracked in metrics."""
        breaker = CircuitBreaker(failure_threshold=1)

        def func_fail():
            raise ValueError("test error")

        def func_ok():
            return "success"

        # Open circuit
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})

        # Reject 3 calls
        for _ in range(3):
            with pytest.raises(CircuitBreakerOpen):
                breaker._execute(func_ok, (), {})

        metrics = breaker.metrics()
        assert metrics.total_calls == 4  # 1 failure + 3 rejections
        assert metrics.failed_calls == 1
        assert metrics.rejected_calls == 3

    def test_open_circuit_includes_recovery_time(self):
        """Test CircuitBreakerOpen exception includes recovery time."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=30.0)

        def func_fail():
            raise ValueError("test error")

        def func_ok():
            return "success"

        # Open circuit
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})

        # Get exception
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            breaker._execute(func_ok, (), {})

        exception = exc_info.value
        assert exception.service_name == "circuit_breaker"
        assert 29 < exception.recovery_time <= 30.0


class TestCircuitBreakerHalfOpen:
    """Test circuit-breaker behavior in HALF_OPEN state."""

    def test_transition_to_half_open_after_timeout(self):
        """Test circuit transitions to HALF_OPEN after recovery timeout."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        def func_fail():
            raise ValueError("test error")

        # Open circuit
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Check state - should be HALF_OPEN now
        assert breaker.state == CircuitState.HALF_OPEN

    def test_successful_call_closes_circuit_from_half_open(self):
        """Test successful call in HALF_OPEN state closes circuit."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        def func_fail():
            raise ValueError("test error")

        def func_ok():
            return "success"

        # Open circuit
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})

        # Wait for recovery
        time.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # Successful call closes circuit
        result = breaker._execute(func_ok, (), {})
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED

    def test_failure_in_half_open_reopens_circuit(self):
        """Test failure in HALF_OPEN state reopens circuit."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        def func_fail():
            raise ValueError("test error")

        def func_ok():
            return "success"

        # Open circuit
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})

        # Wait and transition to HALF_OPEN
        time.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # Failure in HALF_OPEN reopens
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})

        assert breaker.state == CircuitState.OPEN

    def test_state_changes_recorded_for_transitions(self):
        """Test all state transitions are recorded."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        def func_fail():
            raise ValueError("test error")

        def func_ok():
            return "success"

        assert breaker.metrics().state_changes == 0

        # CLOSED → OPEN
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})
        assert breaker.metrics().state_changes == 1

        # Wait and check OPEN → HALF_OPEN
        time.sleep(0.15)
        _ = breaker.state  # Trigger the check
        assert breaker.metrics().state_changes == 2

        # HALF_OPEN → CLOSED
        breaker._execute(func_ok, (), {})
        assert breaker.metrics().state_changes == 3


class TestCircuitBreakerDecorator:
    """Test circuit-breaker as a decorator."""

    def test_decorator_wraps_function(self):
        """Test @circuit_breaker decorator wraps function correctly."""
        @circuit_breaker(name="test", failure_threshold=2)
        def my_func(x):
            return x * 2

        result = my_func(5)
        assert result == 10

    def test_decorator_preserves_function_name(self):
        """Test decorator preserves function name and docstring."""
        @circuit_breaker(name="test")
        def my_func():
            """My docstring."""
            return "result"

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "My docstring."

    def test_decorator_handles_failures(self):
        """Test decorator handles exceptions correctly."""
        @circuit_breaker(name="test", failure_threshold=1)
        def failing_func():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            failing_func()

        # Circuit should be open now
        with pytest.raises(CircuitBreakerOpen):
            failing_func()

    def test_decorator_with_arguments(self):
        """Test decorator with custom arguments."""
        @circuit_breaker(
            name="test_api",
            failure_threshold=3,
            recovery_timeout=0.1,
            expected_exception=TimeoutError,
        )
        def api_call(x):
            return x + 1

        assert api_call(5) == 6


class TestCircuitBreakerMetrics:
    """Test metrics tracking and calculations."""

    def test_success_rate_calculation(self):
        """Test success rate is calculated correctly."""
        breaker = CircuitBreaker(failure_threshold=10)

        def func_ok():
            return "success"

        def func_fail():
            raise ValueError("error")

        # 3 successes
        for _ in range(3):
            breaker._execute(func_ok, (), {})

        # 2 failures
        for _ in range(2):
            with pytest.raises(ValueError):
                breaker._execute(func_fail, (), {})

        metrics = breaker.metrics()
        assert metrics.total_calls == 5
        assert metrics.successful_calls == 3
        assert metrics.failed_calls == 2
        assert metrics.success_rate == 60.0
        assert metrics.failure_rate == 40.0

    def test_last_success_time_updated(self):
        """Test last_success_time is updated on success."""
        breaker = CircuitBreaker()

        def func_ok():
            return "success"

        assert breaker.metrics().last_success_time is None

        before = time.time()
        breaker._execute(func_ok, (), {})
        after = time.time()

        last_success = breaker.metrics().last_success_time
        assert last_success is not None
        assert before <= last_success <= after

    def test_last_failure_time_updated(self):
        """Test last_failure_time is updated on failure."""
        breaker = CircuitBreaker()

        def func_fail():
            raise ValueError("error")

        assert breaker.metrics().last_failure_time is None

        before = time.time()
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})
        after = time.time()

        last_failure = breaker.metrics().last_failure_time
        assert last_failure is not None
        assert before <= last_failure <= after

    def test_metrics_snapshot_is_independent(self):
        """Test metrics() returns independent snapshot."""
        breaker = CircuitBreaker()

        def func_ok():
            return "success"

        breaker._execute(func_ok, (), {})

        snapshot1 = breaker.metrics()
        assert snapshot1.total_calls == 1

        breaker._execute(func_ok, (), {})
        snapshot2 = breaker.metrics()

        # Original snapshot unchanged
        assert snapshot1.total_calls == 1
        # New snapshot updated
        assert snapshot2.total_calls == 2


class TestCircuitBreakerExceptionHandling:
    """Test exception handling and filtering."""

    def test_only_expected_exception_opens_circuit(self):
        """Test only expected_exception type opens circuit."""
        breaker = CircuitBreaker(
            failure_threshold=1, expected_exception=ValueError
        )

        def func_fail_wrong():
            raise TypeError("wrong error")

        def func_fail_right():
            raise ValueError("right error")

        # TypeError doesn't count
        with pytest.raises(TypeError):
            breaker._execute(func_fail_wrong, (), {})

        assert breaker.state == CircuitState.CLOSED

        # ValueError does count
        with pytest.raises(ValueError):
            breaker._execute(func_fail_right, (), {})

        assert breaker.state == CircuitState.OPEN

    def test_unexpected_exception_propagates(self):
        """Test unexpected exceptions propagate without tracking."""
        breaker = CircuitBreaker(expected_exception=ValueError)

        def func_fail():
            raise TypeError("unexpected")

        with pytest.raises(TypeError) as exc_info:
            breaker._execute(func_fail, (), {})

        assert str(exc_info.value) == "unexpected"


class TestCircuitBreakerConcurrency:
    """Test circuit-breaker with concurrent-like scenarios."""

    def test_rapid_failures(self):
        """Test rapid sequential failures open circuit quickly."""
        breaker = CircuitBreaker(failure_threshold=3)

        def func_fail():
            raise ValueError("error")

        # Rapid failures
        for _ in range(3):
            with pytest.raises(ValueError):
                breaker._execute(func_fail, (), {})

        assert breaker.state == CircuitState.OPEN

    def test_multiple_rejection_increments(self):
        """Test multiple rejections while OPEN increment counter."""
        breaker = CircuitBreaker(failure_threshold=1)

        def func_fail():
            raise ValueError("error")

        def func_ok():
            return "success"

        # Open circuit
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})

        # Rapid rejections
        rejection_count = 0
        for _ in range(10):
            try:
                breaker._execute(func_ok, (), {})
            except CircuitBreakerOpen:
                rejection_count += 1

        assert rejection_count == 10
        assert breaker.metrics().rejected_calls == 10


class TestCircuitBreakerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_failure_threshold(self):
        """Test behavior with zero failure threshold."""
        breaker = CircuitBreaker(failure_threshold=0)

        def func_fail():
            raise ValueError("error")

        # First failure opens immediately
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})

        assert breaker.state == CircuitState.OPEN

    def test_very_short_recovery_timeout(self):
        """Test very short recovery timeout."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

        def func_fail():
            raise ValueError("error")

        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})

        # Very quick transition
        time.sleep(0.02)
        assert breaker.state == CircuitState.HALF_OPEN

    def test_function_with_args_and_kwargs(self):
        """Test circuit-breaker preserves args and kwargs."""
        breaker = CircuitBreaker()

        def func_args(a, b, c=None):
            return f"{a},{b},{c}"

        result = breaker._execute(func_args, (1, 2), {"c": 3})
        assert result == "1,2,3"

    def test_return_value_preserved(self):
        """Test circuit-breaker preserves return values."""
        breaker = CircuitBreaker()

        def func_return_dict():
            return {"key": "value", "num": 42}

        result = breaker._execute(func_return_dict, (), {})
        assert result == {"key": "value", "num": 42}

    def test_different_exception_types_all_count(self):
        """Test different exception types all count toward threshold."""
        breaker = CircuitBreaker(failure_threshold=2, expected_exception=Exception)

        def func_fail_1():
            raise ValueError("error1")

        def func_fail_2():
            raise RuntimeError("error2")

        # Different exception types
        with pytest.raises(ValueError):
            breaker._execute(func_fail_1, (), {})

        assert breaker.state == CircuitState.CLOSED

        with pytest.raises(RuntimeError):
            breaker._execute(func_fail_2, (), {})

        assert breaker.state == CircuitState.OPEN  # Both count


class TestCircuitBreakerIntegration:
    """Integration tests with complex scenarios."""

    def test_full_lifecycle(self):
        """Test complete circuit-breaker lifecycle."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        def func_fail():
            raise ValueError("error")

        def func_ok():
            return "success"

        # Phase 1: CLOSED, normal operation
        assert breaker.state == CircuitState.CLOSED
        assert breaker._execute(func_ok, (), {}) == "success"

        # Phase 2: CLOSED, accumulating failures
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})
        assert breaker.state == CircuitState.CLOSED

        # Phase 3: OPEN, failures exceed threshold
        with pytest.raises(ValueError):
            breaker._execute(func_fail, (), {})
        assert breaker.state == CircuitState.OPEN

        # Phase 4: OPEN, rejecting all calls
        with pytest.raises(CircuitBreakerOpen):
            breaker._execute(func_ok, (), {})

        # Phase 5: HALF_OPEN after timeout
        time.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # Phase 6: CLOSED after successful recovery
        assert breaker._execute(func_ok, (), {}) == "success"
        assert breaker.state == CircuitState.CLOSED

    def test_multiple_open_close_cycles(self):
        """Test circuit can be opened and closed multiple times."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)

        def func_fail():
            raise ValueError("error")

        def func_ok():
            return "success"

        for cycle in range(3):
            # Open circuit
            with pytest.raises(ValueError):
                breaker._execute(func_fail, (), {})
            assert breaker.state == CircuitState.OPEN

            # Wait for recovery
            time.sleep(0.1)

            # Close circuit
            assert breaker._execute(func_ok, (), {}) == "success"
            assert breaker.state == CircuitState.CLOSED

    def test_decorator_in_realistic_scenario(self):
        """Test decorator in realistic API call scenario."""
        call_count = {"success": 0, "fail": 0}

        @circuit_breaker(name="api", failure_threshold=2, recovery_timeout=0.05)
        def call_api(should_fail):
            if should_fail:
                call_count["fail"] += 1
                raise ConnectionError("API unavailable")
            call_count["success"] += 1
            return {"status": "ok"}

        # Normal calls
        assert call_api(False) == {"status": "ok"}
        assert call_api(False) == {"status": "ok"}

        # Failures
        with pytest.raises(ConnectionError):
            call_api(True)

        with pytest.raises(ConnectionError):
            call_api(True)

        # Circuit is now open
        with pytest.raises(CircuitBreakerOpen):
            call_api(False)

        # Wait for recovery
        time.sleep(0.1)

        # Recovery succeeds
        assert call_api(False) == {"status": "ok"}
        assert call_api(False) == {"status": "ok"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
