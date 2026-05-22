import asyncio
import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

# Store the current event loop to detect changes
_current_loop = None
_pool = None
_redis_client = None

def _get_or_create_client():
    """Get or create Redis client, recreating if event loop has changed."""
    global _current_loop, _pool, _redis_client
    
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    # If event loop has changed (or new loop detected), recreate connection pool
    if loop != _current_loop:
        _current_loop = loop
        # Disconnect old pool if it exists
        if _pool is not None:
            try:
                # Trigger disconnect (don't need to await for cleanup)
                asyncio.create_task(_pool.disconnect()) if loop else None
            except:
                pass
        
        # Create new pool
        _pool = ConnectionPool.from_url(
            "redis://localhost:6379/0",
            decode_responses=True,
            max_connections=10
        )
        _redis_client = redis.Redis(connection_pool=_pool)
    
    return _redis_client

# Lazy wrapper to ensure we always use the current event loop's client
class RedisClientWrapper:
    def __getattr__(self, name):
        """Delegate attribute access to the current client."""
        client = _get_or_create_client()
        return getattr(client, name)

redis_client = RedisClientWrapper()
