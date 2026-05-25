"""
Pytest configuration for gateway tests.
"""

import pytest


# Use function-scoped event loops for each test
pytestmark = pytest.mark.asyncio


@pytest.fixture
async def redis_cleanup():
    """Clean up Redis before and after each test."""
    from gateway.redis_client import redis_client
    
    # Clear Redis before test
    try:
        await redis_client.flushdb()
    except Exception as e:
        print(f"Warning: Could not flush Redis before test: {e}")
    
    yield
    
    # Clear Redis after test
    try:
        await redis_client.flushdb()
    except Exception as e:
        print(f"Warning: Could not flush Redis after test: {e}")

