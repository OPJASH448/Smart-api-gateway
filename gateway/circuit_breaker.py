import asyncio
import time
from enum import Enum
from typing import Callable, Any

class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered

class CircuitBreaker:
    """
    Circuit Breaker pattern for handling service failures.
    
    States:
    - CLOSED: Normal operation, requests go through
    - OPEN: Service failing, requests rejected immediately
    - HALF_OPEN: Testing if service recovered, allowing limited requests
    """
    
    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0
    ):
        """
        Initialize circuit breaker.
        
        Args:
            service_name: Name of service being protected
            failure_threshold: Number of failures before opening (default 5)
            recovery_timeout: Seconds before attempting recovery (default 30)
        """
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker.
        
        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
        
        Returns:
            Result from func
        
        Raises:
            Exception: Circuit is OPEN or func fails
        """
        
        if self.state == CircuitState.OPEN:
            # Check if timeout expired
            if (time.time() - self.last_failure_time) > self.recovery_timeout:
                print(f"🔄 {self.service_name}: Circuit HALF_OPEN (testing...)")
                self.state = CircuitState.HALF_OPEN
            else:
                raise Exception(f"🔴 {self.service_name}: Circuit OPEN (rejecting)")
        
        try:
            result = await func(*args, **kwargs)
            
            if self.state == CircuitState.HALF_OPEN:
                print(f"🟢 {self.service_name}: Circuit CLOSED (recovered)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
            
            return result
        
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                print(f"🔴 {self.service_name}: Circuit OPEN ({self.failure_count} failures)")
                self.state = CircuitState.OPEN
            
            raise
    
    def get_state(self) -> str:
        """Get current circuit state."""
        return self.state.value
