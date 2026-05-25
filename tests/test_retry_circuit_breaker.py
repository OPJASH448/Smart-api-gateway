import pytest
import asyncio
import time
from gateway.retry import retry_with_backoff
from gateway.circuit_breaker import CircuitBreaker, CircuitState


# ============================================================================
# DAY 6: Retry + Circuit Breaker Tests
# ============================================================================

class TestRetryLogic:
    """Test retry mechanism with exponential backoff."""
    
    @pytest.mark.asyncio
    async def test_retry_succeeds_on_first_attempt(self):
        """Test that function succeeds without retrying."""
        call_count = 0
        
        async def success_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await retry_with_backoff(success_func, max_retries=3)
        assert result == "success"
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self):
        """Test that function succeeds after retrying."""
        call_count = 0
        
        async def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"
        
        result = await retry_with_backoff(failing_then_success, max_retries=3, initial_delay=0.01)
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """Test that exception raised when retries exhausted."""
        call_count = 0
        
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError):
            await retry_with_backoff(always_fails, max_retries=2, initial_delay=0.01)
        
        # Should try: initial + 2 retries = 3 times
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """Test that delays follow exponential backoff pattern."""
        call_times = []
        
        async def failing_func():
            call_times.append(time.time())
            raise ValueError("Fail")
        
        with pytest.raises(ValueError):
            await retry_with_backoff(
                failing_func,
                max_retries=2,
                initial_delay=0.05,
                backoff_factor=2.0
            )
        
        # Should have 3 calls
        assert len(call_times) == 3
        
        # Check delays: should be ~0.05s and ~0.1s
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        
        assert delay1 >= 0.04  # Allow some tolerance
        assert delay2 >= 0.09


class TestCircuitBreaker:
    """Test circuit breaker state transitions."""
    
    @pytest.mark.asyncio
    async def test_circuit_closed_allows_requests(self):
        """Test that CLOSED circuit allows requests through."""
        cb = CircuitBreaker("test_service", failure_threshold=3)
        
        async def success_func():
            return "success"
        
        result = await cb.call(success_func)
        assert result == "success"
        assert cb.get_state() == "closed"
    
    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self):
        """Test that circuit opens after threshold failures."""
        cb = CircuitBreaker("test_service", failure_threshold=2)
        
        async def failing_func():
            raise ValueError("Service error")
        
        # First failure
        with pytest.raises(ValueError):
            await cb.call(failing_func)
        assert cb.failure_count == 1
        assert cb.get_state() == "closed"
        
        # Second failure - opens circuit
        with pytest.raises(ValueError):
            await cb.call(failing_func)
        assert cb.failure_count == 2
        assert cb.get_state() == "open"
    
    @pytest.mark.asyncio
    async def test_circuit_open_rejects_requests(self):
        """Test that OPEN circuit rejects requests immediately."""
        cb = CircuitBreaker("test_service", failure_threshold=1, recovery_timeout=10)
        
        async def failing_func():
            raise ValueError("Service error")
        
        # Fail once to open circuit
        with pytest.raises(ValueError):
            await cb.call(failing_func)
        
        # Circuit is open, next call rejected immediately
        with pytest.raises(Exception) as exc_info:
            await cb.call(failing_func)
        
        assert "Circuit OPEN" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_circuit_half_open_after_timeout(self):
        """Test that circuit enters HALF_OPEN after recovery timeout."""
        cb = CircuitBreaker("test_service", failure_threshold=1, recovery_timeout=0.1)
        
        async def failing_func():
            raise ValueError("Service error")
        
        # Fail once to open circuit
        with pytest.raises(ValueError):
            await cb.call(failing_func)
        
        assert cb.get_state() == "open"
        
        # Wait for recovery timeout
        await asyncio.sleep(0.15)
        
        # Next attempt should try (move to HALF_OPEN)
        with pytest.raises(ValueError):
            await cb.call(failing_func)
        
        # Circuit should be HALF_OPEN after timeout
        # (but still fails because function fails)
    
    @pytest.mark.asyncio
    async def test_circuit_recovers_on_success(self):
        """Test that circuit closes after successful call in HALF_OPEN."""
        cb = CircuitBreaker("test_service", failure_threshold=1, recovery_timeout=0.1)
        
        async def failing_func():
            raise ValueError("Service error")
        
        async def success_func():
            return "success"
        
        # Fail once to open circuit
        with pytest.raises(ValueError):
            await cb.call(failing_func)
        
        assert cb.get_state() == "open"
        
        # Wait for recovery timeout
        await asyncio.sleep(0.15)
        
        # Successful call in HALF_OPEN should close circuit
        result = await cb.call(success_func)
        assert result == "success"
        assert cb.get_state() == "closed"
        assert cb.failure_count == 0


class TestRetryAndCircuitBreakerIntegration:
    """Test retry + circuit breaker together."""
    
    @pytest.mark.asyncio
    async def test_retry_then_circuit_breaker(self):
        """Test retry logic with circuit breaker."""
        call_count = 0
        
        async def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Service error")
        
        cb = CircuitBreaker("test_service", failure_threshold=2)
        
        # Wrapped retry + circuit breaker
        async def call_with_retry():
            return await retry_with_backoff(
                lambda: cb.call(failing_func),
                max_retries=1,
                initial_delay=0.01
            )
        
        with pytest.raises(Exception):
            await call_with_retry()
        
        # Should have attempted retries
        assert call_count >= 1
    
    @pytest.mark.asyncio
    async def test_different_services_independent(self):
        """Test that different services have independent circuit breakers."""
        cb_auth = CircuitBreaker("auth_service", failure_threshold=1)
        cb_chat = CircuitBreaker("chat_service", failure_threshold=1)
        
        async def failing_func():
            raise ValueError("Error")
        
        async def success_func():
            return "success"
        
        # Fail auth service
        with pytest.raises(ValueError):
            await cb_auth.call(failing_func)
        
        assert cb_auth.get_state() == "open"
        assert cb_chat.get_state() == "closed"  # Chat still closed
        
        # Chat service still works
        result = await cb_chat.call(success_func)
        assert result == "success"
