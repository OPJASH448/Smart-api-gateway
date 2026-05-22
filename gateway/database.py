"""
Database & Redis management for the Smart API Gateway.
"""

import redis.asyncio as redis
from motor.motor_asyncio import AsyncIOMotorClient
from gateway.config import settings

class DatabaseManager:
    def __init__(self):
        self.client = AsyncIOMotorClient(
            settings.database_url,
            serverSelectionTimeoutMS=5000
        )
        self.db = self.client.get_default_database()
        self.redis = None

    async def connect(self):
        """Initialize database and redis connections."""
        try:
            # Test MongoDB connection
            await self.client.admin.command('ping')
            print("✅ MongoDB connected")
        except Exception as e:
            print(f"⚠️  Database connection failed (MongoDB): {e}")
            print("   Gateway will continue without persistent storage.")
        
        try:
            # Initialize Redis
            self.redis = redis.from_url(settings.redis_url, decode_responses=True)
            await self.redis.ping()
            print("✅ Redis connected")
        except Exception as e:
            print(f"⚠️  Redis connection failed: {e}")
            print("   Gateway will continue without caching/rate-limiting.")

    async def disconnect(self):
        """Close connections."""
        if self.redis:
            await self.redis.close()
        self.client.close()
        print("🛑 Database & Redis disconnected")

db_manager = DatabaseManager()
