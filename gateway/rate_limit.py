"""
Rate Limiter — keeps track of request counts in Redis.
"""

from typing import Tuple
from gateway.database import db_manager

async def is_rate_limited(client_id: str, limit: int, window: int) -> Tuple[bool, int]:
    """
    Check if a client has exceeded their rate limit.
    Returns (is_limited, remaining_requests).
    """
    if not db_manager.redis:
        return False, -1  # Fail open if Redis is down

    key = f"rate_limit:{client_id}"
    
    try:
        # Increment and set expiry if new
        count = await db_manager.redis.incr(key)
        if count == 1:
            await db_manager.redis.expire(key, window)
        
        remaining = max(0, limit - count)
        return count > limit, remaining
    except Exception as e:
        print(f"❌ Rate limit error: {e}")
        return False, -1
