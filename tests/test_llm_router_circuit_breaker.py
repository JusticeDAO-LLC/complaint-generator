"""Tests for circuit breaker functionality in LLMRouterBackend."""

import pytest
import time
from unittest.mock import patch, MagicMock


class TestLLMRouterCircuitBreaker:
    """Test circuit breaker pattern in LLM router backend."""

    @pytest.fixture
    def mock_generate_text(self):
        """Mock the generate_text function."""
        with patch('backends.llm_router_backend.generate_text') as mock:
            yield mock

    @pytest.fixture
    def backend_with_breaker(self, mock_generate_text):
        """Create backend with circuit breaker enabled."""
        from backends.llm_router_backend import LLMRouterBackend
        return LLMRouterBackend(
            id='test',
            provider='openai',
            model='gpt-4',
            circuit_breaker_enabled=True,
            circuit_breaker_failure_threshold=3,
            circuit_breaker_timeout=2,  # Short timeout for faster tests
            retry_max_attempts=1,  # No retries to isolate breaker behavior
        )

    @pytest.fixture
    def backend_without_breaker(self, mock_generate_text):
        """Create backend with circuit breaker disabled."""
        from backends.llm_router_backend import LLMRouterBackend
        return LLMRouterBackend(
            id='test',
            provider='openai',
            model='gpt-4',
            circuit_breaker_enabled=False,
            retry_max_attempts=1,
        )

    def test_circuit_breaker_can_be_disabled(self, backend_without_breaker, mock_generate_text):
        """Circuit breaker can be disabled via config."""
        assert backend_without_breaker.circuit_breaker_enabled is False
        mock_generate_text.return_value = "success"
        
        result = backend_without_breaker("test prompt")
        assert result == "success"

    def test_successful_call_keeps_circuit_closed(self, backend_with_breaker, mock_generate_text):
        """Successful calls keep circuit breaker in CLOSED state."""
        mock_generate_text.return_value = "success"
        
        result = backend_with_breaker("test prompt")
        assert result == "success"
        
        state = backend_with_breaker.get_circuit_breaker_state()
        assert state['state'] == 'CLOSED'
        assert state['failure_count'] == 0

    def test_circuit_opens_after_failure_threshold(self, backend_with_breaker, mock_generate_text):
        """Circuit breaker opens after failure threshold is reached."""
        mock_generate_text.side_effect = Exception("Service unavailable")
        
        # First 3 failures should trigger circuit open
        for i in range(3):
            with pytest.raises(Exception, match="llm_router_error"):
                backend_with_breaker("test prompt")
        
        state = backend_with_breaker.get_circuit_breaker_state()
        assert state['state'] == 'OPEN'
        assert state['failure_count'] >= 3

    def test_open_circuit_rejects_calls(self, backend_with_breaker, mock_generate_text):
        """When circuit is OPEN, calls are rejected immediately."""
        mock_generate_text.side_effect = Exception("Service unavailable")
        
        # Trigger circuit open
        for i in range(3):
            with pytest.raises(Exception):
                backend_with_breaker("test prompt")
        
        # Next call should be rejected by circuit breaker without calling backend
        call_count_before = mock_generate_text.call_count
        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            backend_with_breaker("test prompt")
        
        # generate_text should not have been called again
        assert mock_generate_text.call_count == call_count_before
        
        # Check stats
        stats = backend_with_breaker.get_retry_stats()
        assert stats['circuit_breaker_rejects'] > 0

    def test_circuit_transitions_to_half_open_after_timeout(self, backend_with_breaker, mock_generate_text):
        """Circuit breaker transitions to HALF_OPEN after timeout."""
        mock_generate_text.side_effect = Exception("Service unavailable")
        
        # Trigger circuit open
        for i in range(3):
            with pytest.raises(Exception):
                backend_with_breaker("test prompt")
        
        assert backend_with_breaker.get_circuit_breaker_state()['state'] == 'OPEN'
        
        # Wait for timeout (2 seconds configured)
        time.sleep(2.1)
        
        # Next call should transition to HALF_OPEN
        # We need to catch the exception since the mock still raises
        mock_generate_text.call_count = 0  # Reset counter
        try:
            backend_with_breaker("test prompt")
        except Exception:
            pass
        
        # Should have attempted the call (HALF_OPEN allows试)
        assert mock_generate_text.call_count > 0

    def test_circuit_closes_after_successful_half_open_call(self, backend_with_breaker, mock_generate_text):
        """Circuit breaker closes after successful call in HALF_OPEN state."""
        # First cause failures to open circuit
        mock_generate_text.side_effect = Exception("Service unavailable")
        for i in range(3):
            with pytest.raises(Exception):
                backend_with_breaker("test prompt")
        
        assert backend_with_breaker.get_circuit_breaker_state()['state'] == 'OPEN'
        
        # Wait for timeout
        time.sleep(2.1)
        
        # Now make backend succeed
        mock_generate_text.side_effect = None
        mock_generate_text.return_value = "success"
        
        result = backend_with_breaker("test prompt")
        assert result == "success"
        
        # Circuit should be CLOSED now
        state = backend_with_breaker.get_circuit_breaker_state()
        assert state['state'] == 'CLOSED'
        assert state['failure_count'] == 0

    def test_manual_reset_works(self, backend_with_breaker, mock_generate_text):
        """Manual reset of circuit breaker works."""
        mock_generate_text.side_effect = Exception("Service unavailable")
        
        # Trigger circuit open
        for i in range(3):
            with pytest.raises(Exception):
                backend_with_breaker("test prompt")
        
        assert backend_with_breaker.get_circuit_breaker_state()['state'] == 'OPEN'
        
        # Manually reset
        backend_with_breaker.reset_circuit_breaker()
        
        state = backend_with_breaker.get_circuit_breaker_state()
        assert state['state'] == 'CLOSED'
        assert state['failure_count'] == 0
        assert state['last_failure_time'] is None

    def test_stats_tracking(self, backend_with_breaker, mock_generate_text):
        """Circuit breaker stats are tracked correctly."""
        mock_generate_text.return_value = "success"
        
        # Make some successful calls
        for i in range(5):
            backend_with_breaker("test prompt")
        
        stats = backend_with_breaker.get_retry_stats()
        assert stats['calls_total'] == 5
        assert stats['attempts_total'] == 5
        assert stats['failures_total'] == 0
        assert stats['circuit_breaker_rejects'] == 0

    def test_retryable_errors_respect_circuit_breaker(self, mock_generate_text):
        """Retryable errors still respect circuit breaker."""
        from backends.llm_router_backend import LLMRouterBackend
        backend = LLMRouterBackend(
            id='test',
            provider='openai',
            model='gpt-4',
            circuit_breaker_enabled=True,
            circuit_breaker_failure_threshold=3,
            circuit_breaker_timeout=2,
            retry_max_attempts=2,  # Allow 2 retries
        )
        
        # Simulate rate limit errors (retryable)
        mock_generate_text.side_effect = Exception("429: rate limit exceeded")
        
        # Each call will retry twice, but eventually fail
        for i in range(3):
            with pytest.raises(Exception):
                backend("test prompt")
        
        # Circuit should be open now
        state = backend.get_circuit_breaker_state()
        assert state['state'] == 'OPEN'
        
        # Stats should show retries happened
        stats = backend.get_retry_stats()
        assert stats['retries_total'] > 0

    def test_circuit_breaker_state_when_disabled(self, backend_without_breaker):
        """get_circuit_breaker_state returns DISABLED when circuit breaker is off."""
        state = backend_without_breaker.get_circuit_breaker_state()
        assert state['state'] == 'DISABLED'
        assert state['failure_count'] == 0
        assert state['last_failure_time'] is None

    def test_reset_when_disabled_is_safe(self, backend_without_breaker):
        """reset_circuit_breaker is safe to call when circuit breaker is disabled."""
        # Should not raise an exception
        backend_without_breaker.reset_circuit_breaker()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
