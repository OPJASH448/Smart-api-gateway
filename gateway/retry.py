import asyncio
from typing import Callable, Any, TypeVar

T = TypeVar('T')

async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0
) -> Any:
    """
    Retry function with exponential backoff.
    
    Delays: 1s → 2s → 4s
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retries (default 3)
        initial_delay: Initial delay in seconds (default 1.0)
        backoff_factor: Multiplier for delay after each retry (default 2.0)
    
    Returns:
        Result from func if successful
    
    Raises:
        Exception: If all retries exhausted
    """
    delay = initial_delay
    
    for attempt in range(max_retries + 1):
        try:
            result = await func()
            return result
        except Exception as e:
            if attempt == max_retries:
                raise  # Give up
            
            print(f"⚠️  Attempt {attempt + 1} failed, retrying in {delay}s...")
            await asyncio.sleep(delay)
            delay *= backoff_factor
    
    return None
