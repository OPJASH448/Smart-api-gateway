# DAY 6 & 7 Implementation Plan
## Retry + Circuit Breaker + Logging + Monitoring

---

## DAY 6: Retry + Circuit Breaker Pattern

### Overview
```
Request → Service Fails
  ↓
Retry 1 (wait 1s) → Fails
  ↓
Retry 2 (wait 2s) → Fails
  ↓
Retry 3 (wait 4s) → Fails
  ↓
Circuit OPEN → Reject immediately
  ↓
(Wait 30s)
  ↓
Circuit HALF_OPEN → Try 1 request
  ↓
If Success → Circuit CLOSED (normal)
If Fail → Circuit OPEN again
```

### Implementation Structure

```
gateway/
├── retry.py                    # Retry logic + exponential backoff
├── circuit_breaker.py          # Circuit breaker per service
└── main.py                     # Integrate into proxy
```

### Code Outline

**gateway/retry.py**
```python
import asyncio
from typing import Callable, TypeVar, Any

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
```

**gateway/circuit_breaker.py**
```python
import asyncio
import time
from enum import Enum
from typing import Callable, Any

class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered

class CircuitBreaker:
    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through circuit breaker."""
        
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
```

**gateway/main.py (Integration)**
```python
from retry import retry_with_backoff
from circuit_breaker import CircuitBreaker

# Create circuit breakers for each service
circuit_breakers = {
    "auth": CircuitBreaker("auth_service"),
    "chat": CircuitBreaker("chat_service"),
    "ai": CircuitBreaker("ai_service"),
}

async def proxy_request(service: str, request):
    """Proxy with retry + circuit breaker."""
    
    cb = circuit_breakers[service]
    
    async def make_request():
        client = pool_manager.get_client(service)
        return await client.request(...)
    
    # Retry with exponential backoff
    return await retry_with_backoff(
        lambda: cb.call(make_request),
        max_retries=3,
        initial_delay=1.0
    )
```

### Testing DAY 6

```bash
# Test with intentionally failing service
pytest tests/test_retry_circuit_breaker.py -v

# Tests should cover:
# ✅ Retry 3 times on failure
# ✅ Exponential backoff (1s → 2s → 4s)
# ✅ Circuit opens after 5 failures
# ✅ Circuit half-opens after timeout
# ✅ Circuit closes on recovery
```

---

## DAY 7: Logging + Monitoring with PostgreSQL

### Setup (Optimal with Docker)

**docker-compose.yml** (Updated)
```yaml
version: '3.9'

services:
  # Existing services...
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # NEW: PostgreSQL for logs
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: gateway_logs
      POSTGRES_USER: gateway
      POSTGRES_PASSWORD: gateway_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-db.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U gateway"]
      interval: 5s
      timeout: 3s
      retries: 5

  gateway:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://gateway:gateway_password@postgres:5432/gateway_logs
      REDIS_URL: redis://redis:6379/0

volumes:
  postgres_data:
```

**init-db.sql** (Create tables)
```sql
-- Request logs table
CREATE TABLE IF NOT EXISTS request_logs (
    id SERIAL PRIMARY KEY,
    request_id UUID NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    method VARCHAR(10),
    path TEXT,
    service VARCHAR(50),
    status_code INT,
    response_time_ms FLOAT,
    error_message TEXT,
    client_ip VARCHAR(45),
    retry_count INT DEFAULT 0,
    circuit_breaker_state VARCHAR(20)
);

-- Create index for fast queries
CREATE INDEX idx_request_id ON request_logs(request_id);
CREATE INDEX idx_timestamp ON request_logs(timestamp);
CREATE INDEX idx_service ON request_logs(service);
```

### Implementation Structure

```
gateway/
├── database.py                 # PostgreSQL connection
├── models.py                   # SQLAlchemy models
├── logger.py                   # Structured logging (UPDATED)
└── main.py                     # Log endpoints
```

### Code Outline

**gateway/database.py**
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://gateway:gateway_password@localhost:5432/gateway_logs"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**gateway/models.py**
```python
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class RequestLog(Base):
    __tablename__ = "request_logs"
    
    id = Column(Integer, primary_key=True)
    request_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow)
    method = Column(String(10))
    path = Column(Text)
    service = Column(String(50))
    status_code = Column(Integer)
    response_time_ms = Column(Float)
    error_message = Column(Text, nullable=True)
    client_ip = Column(String(45))
    retry_count = Column(Integer, default=0)
    circuit_breaker_state = Column(String(20))
    
    def to_dict(self):
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "method": self.method,
            "path": self.path,
            "service": self.service,
            "status_code": self.status_code,
            "response_time_ms": self.response_time_ms,
            "error_message": self.error_message,
            "client_ip": self.client_ip,
            "retry_count": self.retry_count,
            "circuit_breaker_state": self.circuit_breaker_state,
        }
```

**gateway/logger.py** (UPDATED - Structured)
```python
import logging
import json
from datetime import datetime
from database import SessionLocal
from models import RequestLog

class StructuredLogger:
    """Structured JSON logging to PostgreSQL + Console."""
    
    def __init__(self):
        self.db = SessionLocal()
    
    async def log_request(
        self,
        request_id: str,
        method: str,
        path: str,
        service: str,
        status_code: int,
        response_time_ms: float,
        client_ip: str,
        retry_count: int = 0,
        circuit_state: str = "CLOSED",
        error_message: str = None
    ):
        """Log request to PostgreSQL."""
        
        log_entry = RequestLog(
            request_id=request_id,
            method=method,
            path=path,
            service=service,
            status_code=status_code,
            response_time_ms=response_time_ms,
            client_ip=client_ip,
            retry_count=retry_count,
            circuit_breaker_state=circuit_state,
            error_message=error_message
        )
        
        self.db.add(log_entry)
        self.db.commit()
        
        # Also log to console as structured JSON
        print(json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request_id,
            "method": method,
            "path": path,
            "service": service,
            "status_code": status_code,
            "response_time_ms": response_time_ms,
            "retry_count": retry_count,
            "circuit_state": circuit_state,
            "error": error_message
        }))

logger = StructuredLogger()
```

**gateway/main.py** (Endpoints - UPDATED)
```python
from fastapi import FastAPI, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
from models import RequestLog
from datetime import datetime, timedelta

@app.get("/dashboard/logs")
async def get_logs(
    service: str = None,
    status_code: int = None,
    minutes: int = 60,
    db: Session = Depends(get_db)
):
    """
    Get request logs from database.
    
    Query params:
    - service: filter by service (auth, chat, ai)
    - status_code: filter by status code (200, 429, 500, etc)
    - minutes: last N minutes (default 60)
    """
    
    cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
    
    query = db.query(RequestLog).filter(RequestLog.timestamp >= cutoff_time)
    
    if service:
        query = query.filter(RequestLog.service == service)
    
    if status_code:
        query = query.filter(RequestLog.status_code == status_code)
    
    logs = query.order_by(RequestLog.timestamp.desc()).limit(1000).all()
    
    return {
        "count": len(logs),
        "logs": [log.to_dict() for log in logs]
    }

@app.get("/dashboard/stats")
async def get_stats(
    minutes: int = 60,
    db: Session = Depends(get_db)
):
    """Get statistics over time period."""
    
    cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
    
    logs = db.query(RequestLog).filter(RequestLog.timestamp >= cutoff_time).all()
    
    stats = {
        "total_requests": len(logs),
        "avg_response_time_ms": sum(l.response_time_ms for l in logs) / len(logs) if logs else 0,
        "errors": len([l for l in logs if l.status_code >= 400]),
        "services": {},
        "status_codes": {}
    }
    
    for log in logs:
        # By service
        if log.service not in stats["services"]:
            stats["services"][log.service] = 0
        stats["services"][log.service] += 1
        
        # By status code
        if log.status_code not in stats["status_codes"]:
            stats["status_codes"][log.status_code] = 0
        stats["status_codes"][log.status_code] += 1
    
    return stats

@app.get("/dashboard/health")
async def check_health():
    """Health + system overview."""
    
    return {
        "status": "healthy",
        "database": "connected",
        "redis": "connected",
        "services": {
            "auth": "healthy",
            "chat": "healthy",
            "ai": "healthy"
        }
    }
```

---

## Quick Start - DAY 6 & 7

### Setup

```bash
# 1. Update docker-compose.yml with PostgreSQL
# 2. Update requirements.txt with sqlalchemy, psycopg2

# 3. Start everything
docker-compose up --build

# 4. Verify PostgreSQL running
docker-compose exec postgres psql -U gateway -d gateway_logs -c "SELECT * FROM request_logs;"

# 5. Run gateway
python -m gateway.main
```

### Test DAY 6

```bash
pytest tests/test_retry_circuit_breaker.py -v
```

### Test DAY 7

```bash
# Make requests to generate logs
curl http://localhost:8000/health
curl http://localhost:8000/auth/login

# View logs
curl http://localhost:8000/dashboard/logs

# View stats
curl http://localhost:8000/dashboard/stats

# View health
curl http://localhost:8000/dashboard/health
```

---

## Files to Create/Update

### New Files
- `gateway/retry.py` - Retry logic
- `gateway/circuit_breaker.py` - Circuit breaker
- `gateway/database.py` - PostgreSQL connection
- `gateway/models.py` - SQLAlchemy models
- `init-db.sql` - Database schema
- `tests/test_retry_circuit_breaker.py` - Tests
- `tests/test_logging.py` - Logging tests

### Updated Files
- `docker-compose.yml` - Add PostgreSQL
- `requirements.txt` - Add sqlalchemy, psycopg2
- `gateway/main.py` - Add endpoints & integration
- `gateway/logger.py` - Structured logging

---

## Optimal Setup Summary

✅ **Docker Compose** handles everything  
✅ **PostgreSQL** for persistent logs  
✅ **SQLAlchemy** for ORM (easy queries)  
✅ **Structured JSON** logging (console + DB)  
✅ **/dashboard** endpoints for monitoring  
✅ **Circuit Breaker** per service  
✅ **Retry Logic** with exponential backoff  

---

## Expected Behavior

### DAY 6: Retry + Circuit Breaker
```
Request fails → Retry 1 (1s wait)
Request fails → Retry 2 (2s wait)
Request fails → Retry 3 (4s wait)
All failed → Circuit OPEN
5 failures → Circuit OPEN
30s timeout → Circuit HALF_OPEN (test 1 req)
Success → Circuit CLOSED
```

### DAY 7: Logging + Monitoring
```
Every request logged to PostgreSQL with:
- request_id (UUID)
- timestamp
- method, path, service
- status code
- response time
- retry count
- circuit state
- errors

Dashboard shows:
/dashboard/logs → All logs (filterable)
/dashboard/stats → Statistics
/dashboard/health → System health
```

Done! Ready to implement? 🚀
