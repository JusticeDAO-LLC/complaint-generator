"""Integration tests for circuit-breaker and lazy-loader components.

Tests the combined behavior of LazyLLMBackend with circuit-breaker protection.
"""

import pytest
from ipfs_datasets_py.optimizers.llm_lazy_loader import (
    LazyLLMBackend,
    get_global_llm_backend,
)
from ipfs_datasets_py.optimizers.common.circuit_breaker import (
    CircuitBreakerOpen,
    CircuitState,
)


@pytest.fixture(autouse=True)
def _reset_llm_state(monkeypatch):
    """Keep tests order-independent when pytest-randomly reorders execution."""
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    get_global_llm_backend.cache_clear()
    yield
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    get_global_llm_backend.cache_clear()


class TestLazyLoaderWithCircuitBreaker:
    """Test LazyLLMBackend with integrated circuit-breaker."""

    def test_circuit_breaker_disabled_by_default_when_llm_disabled(self):
        """Test circuit-breaker is not active when LLM is disabled."""
        backend = LazyLLMBackend(enabled=False)
        assert not backend.is_enabled()
        assert backend.get_circuit_breaker_metrics() is None

    def test_circuit_breaker_enabled_by_default(self):
        """Test circuit-breaker is enabled by default."""
        backend = LazyLLMBackend(backend_type="mock")
        assert backend.is_enabled()
        assert backend.get_circuit_breaker_metrics() is not None

    def test_circuit_breaker_can_be_disabled(self):
        """Test circuit-breaker can be disabled explicitly."""
        backend = LazyLLMBackend(
            backend_type="mock",
            circuit_breaker_enabled=False
        )
        assert backend.get_circuit_breaker_metrics() is None

    def test_successful_calls_tracked(self):
        """Test successful calls are tracked in circuit-breaker metrics."""
        backend = LazyLLMBackend(backend_type="mock")
        
        # Make successful calls
        result = backend.generate(prompt="test")
        assert "test" in result
        
        metrics = backend.get_circuit_breaker_metrics()
        assert metrics["total_calls"] >= 1
        assert metrics["successful_calls"] >= 1
        assert metrics["success_rate"] == 100.0

    def test_single_failure_recorded(self):
        """Test failed calls are tracked in circuit-breaker."""
        backend = LazyLLMBackend(
            backend_type="mock",
            failure_threshold=3
        )
        
        # Create a mock class with failing method
        class FailingBackend:
            def generate(self, **kwargs):
                raise ValueError("Test failure")
        
        backend._initialized = True
        backend._backend = FailingBackend()
        
        # Call should fail
        with pytest.raises(RuntimeError) as exc_info:
            backend.generate(prompt="test")
        
        assert "error" in str(exc_info.value)
        
        metrics = backend.get_circuit_breaker_metrics()
        assert metrics["failed_calls"] >= 1
        assert metrics["failure_rate"] > 0


class TestCircuitBreakerStateQueries:
    """Test circuit-breaker state query methods."""

    def test_is_circuit_breaker_open_when_closed(self):
        """Test is_circuit_breaker_open returns False when CLOSED."""
        backend = LazyLLMBackend(backend_type="mock")
        assert not backend.is_circuit_breaker_open()

    def test_circuit_breaker_open_after_threshold_exceeded(self):
        """Test is_circuit_breaker_open returns True when OPEN."""
        backend = LazyLLMBackend(
            backend_type="mock",
            failure_threshold=1
        )
        
        # Inject failing function
        def failing_call():
            raise ValueError("Test error")
        
        # First failure should open the circuit
        with pytest.raises(ValueError):
            backend._circuit_breaker._execute(failing_call, (), {})
        
        # Now it should be open
        assert backend.is_circuit_breaker_open()

    def test_metrics_include_rejection_count(self):
        """Test metrics include rejection count during OPEN state."""
        backend = LazyLLMBackend(
            backend_type="mock",
            failure_threshold=1,
            recovery_timeout=10.0
        )
        
        # Open circuit with a failure
        def failing_call():
            raise ValueError("Error")
        
        with pytest.raises(ValueError):
            backend._circuit_breaker._execute(failing_call, (), {})
        
        # Now open, try to call - should be rejected
        def ok_call():
            return "ok"
        
        rejection_count = 0
        for _ in range(3):
            try:
                backend._circuit_breaker._execute(ok_call, (), {})
            except CircuitBreakerOpen:
                rejection_count += 1
        
        assert rejection_count == 3
        metrics = backend.get_circuit_breaker_metrics()
        assert metrics["rejected_calls"] >= 3


class TestCircuitBreakerWithMethodCalls:
    """Test circuit-breaker behavior with method forwarding."""

    def test_method_call_with_circuit_protection(self):
        """Test method calls are protected by circuit-breaker."""
        backend = LazyLLMBackend(backend_type="mock")
        
        # Call method
        result = backend.generate(prompt="test")
        assert result is not None
        
        metrics = backend.get_circuit_breaker_metrics()
        assert metrics["successful_calls"] >= 1

    def test_wrapped_method_preserves_return_value(self):
        """Test wrapped methods preserve return values correctly."""
        backend = LazyLLMBackend(backend_type="mock")
        
        result = backend.generate(prompt="hello world")
        assert "hello world" in result
        
        result2 = backend.generate(prompt="foo bar")
        assert "foo bar" in result2

    def test_streaming_with_circuit_protection(self):
        """Test streaming methods can be called through circuit-breaker."""
        backend = LazyLLMBackend(backend_type="mock")
        
        # Stream should work
        stream_gen = backend.stream(prompt="test")
        assert stream_gen is not None


class TestCircuitBreakerCustomConfiguration:
    """Test circuit-breaker with custom configuration."""

    def test_custom_failure_threshold(self):
        """Test circuit-breaker can be configured with custom threshold."""
        backend = LazyLLMBackend(
            backend_type="mock",
            failure_threshold=2,
            recovery_timeout=30.0
        )
        
        metrics = backend.get_circuit_breaker_metrics()
        assert metrics is not None  # Confirm breaker exists
        
        # Inject failing function
        def failing_call():
            raise ValueError("Error")
        
        # One failure - should still be closed
        try:
            backend._circuit_breaker._execute(failing_call, (), {})
        except ValueError:
            pass
        
        assert not backend.is_circuit_breaker_open()
        
        # Two failures - should open
        try:
            backend._circuit_breaker._execute(failing_call, (), {})
        except ValueError:
            pass
        
        assert backend.is_circuit_breaker_open()

    def test_custom_recovery_timeout_setting(self):
        """Test circuit-breaker recovery timeout is configurable."""
        backend = LazyLLMBackend(
            backend_type="mock",
            recovery_timeout=100.0
        )
        
        # The breaker should exist with proper timeout (we can't easily verify
        # the timeout value without accessing private attribute, but we can
        # verify the breaker exists and is functional)
        metrics = backend.get_circuit_breaker_metrics()
        assert metrics is not None


class TestCircuitBreakerDisabledBackend:
    """Test circuit-breaker behavior when backend is disabled."""

    def test_no_circuit_breaker_when_llm_disabled(self):
        """Test no circuit-breaker is created when LLM is disabled."""
        backend = LazyLLMBackend(
            backend_type="mock",
            enabled=False
        )
        
        assert not backend.is_enabled()
        assert backend.get_circuit_breaker_metrics() is None
        assert not backend.is_circuit_breaker_open()

    def test_disabled_backend_raises_runtime_error(self):
        """Test disabled backend raises RuntimeError on access."""
        backend = LazyLLMBackend(
            backend_type="mock",
            enabled=False
        )
        
        with pytest.raises(RuntimeError) as exc_info:
            backend.generate(prompt="test")
        
        assert "disabled" in str(exc_info.value)


class TestCircuitBreakerMetricsAccuracy:
    """Test circuit-breaker metrics accuracy and consistency."""

    def test_metrics_snapshot_accuracy(self):
        """Test metrics snapshots are accurate."""
        backend = LazyLLMBackend(backend_type="mock")
        
        # Make 3 successful calls
        for i in range(3):
            backend.generate(prompt=f"test {i}")
        
        metrics = backend.get_circuit_breaker_metrics()
        assert metrics["total_calls"] >= 3
        assert metrics["successful_calls"] >= 3
        assert metrics["failed_calls"] == 0
        assert metrics["rejected_calls"] == 0

    def test_metrics_decimal_rates(self):
        """Test success/failure rates are calculated correctly."""
        backend = LazyLLMBackend(
            backend_type="mock",
            failure_threshold=10
        )
        
        # Make 4 successful calls
        for _ in range(4):
            backend.generate(prompt="test")
        
        metrics = backend.get_circuit_breaker_metrics()
        # With 4 successful calls, success_rate should be 100%
        assert metrics["success_rate"] == 100.0
        assert metrics["failure_rate"] == 0.0


class TestCircuitBreakerErrorPropagation:
    """Test error handling in circuit-breaker integration."""

    def test_circuit_breaker_open_error_propagates(self):
        """Test CircuitBreakerOpen exceptions are caught and re-raised."""
        backend = LazyLLMBackend(
            backend_type="mock",
            failure_threshold=1,
            recovery_timeout=10.0
        )
        
        # Open the circuit
        def failing_call():
            raise ValueError("Error")
        
        with pytest.raises(ValueError):
            backend._circuit_breaker._execute(failing_call, (), {})
        
        # Now try to call - should get CircuitBreakerOpen
        def ok_call():
            return "ok"
        
        with pytest.raises(CircuitBreakerOpen):
            backend._circuit_breaker._execute(ok_call, (), {})


class TestGlobalBackendWithCircuitBreaker:
    """Test global backend singleton with circuit-breaker."""

    def test_global_backend_has_circuit_breaker(self):
        """Test get_global_llm_backend creates backend with circuit-breaker."""
        from ipfs_datasets_py.optimizers.llm_lazy_loader import get_global_llm_backend
        
        backend = get_global_llm_backend(backend_type="mock")
        
        # Should have circuit-breaker by default
        metrics = backend.get_circuit_breaker_metrics()
        assert metrics is not None

    def test_global_backend_circuit_breaker_disabled_option(self):
        """Test global backend can disable circuit-breaker."""
        from ipfs_datasets_py.optimizers.llm_lazy_loader import get_global_llm_backend
        
        backend = get_global_llm_backend(
            backend_type="mock",
            circuit_breaker_enabled=False
        )
        
        # Circuit-breaker should be disabled
        metrics = backend.get_circuit_breaker_metrics()
        assert metrics is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
