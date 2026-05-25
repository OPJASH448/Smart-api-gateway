"""
Database Connection Status Check
"""

import os
import sys
from sqlalchemy import text, inspect

# Add gateway to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gateway.database import engine, SessionLocal, Base
from gateway.models import RequestLog

def check_db_connection():
    """Check database connection status."""
    print("=" * 70)
    print("DATABASE CONNECTION STATUS CHECK")
    print("=" * 70)
    
    # Get connection string
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://gateway:gateway_password@localhost:5432/gateway_logs"
    )
    print(f"\n📍 Database URL: {db_url}")
    print(f"   (Password redacted if present)")
    
    # Try to connect
    print("\n🔗 Attempting connection...")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print(f"   ✅ Connection successful!")
            print(f"   Response: {result.fetchone()}")
    except Exception as e:
        print(f"   ❌ Connection failed!")
        print(f"   Error: {e}")
        return False
    
    # Check if tables exist
    print("\n📋 Checking tables...")
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"   Found {len(tables)} table(s):")
        for table in tables:
            print(f"      - {table}")
        
        # Check for request_logs table
        if "request_logs" in tables:
            print(f"\n   ✅ request_logs table EXISTS")
            # Get columns
            columns = inspector.get_columns("request_logs")
            print(f"   Columns ({len(columns)}):")
            for col in columns:
                print(f"      - {col['name']}: {col['type']}")
        else:
            print(f"\n   ⚠️  request_logs table NOT FOUND")
            print(f"   Creating tables...")
            try:
                Base.metadata.create_all(bind=engine)
                print(f"   ✅ Tables created successfully!")
            except Exception as e:
                print(f"   ❌ Failed to create tables: {e}")
                return False
    
    except Exception as e:
        print(f"   ❌ Error checking tables: {e}")
        return False
    
    # Try to query existing logs
    print("\n📊 Checking existing logs...")
    try:
        db = SessionLocal()
        count = db.query(RequestLog).count()
        print(f"   ✅ Query successful!")
        print(f"   Total logs in database: {count}")
        db.close()
    except Exception as e:
        print(f"   ❌ Query failed: {e}")
        return False
    
    print("\n" + "=" * 70)
    print("✅ DATABASE CONNECTION STATUS: ALL SYSTEMS OK")
    print("=" * 70)
    return True

if __name__ == "__main__":
    check_db_connection()
