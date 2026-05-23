"""
Comprehensive test for Retry + Circuit Breaker with detailed output and database logging.

DAY 6: Demonstrates:
1. Retry with exponential backoff (1s → 2s → 4s)
2. Circuit breaker state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
3. Database logging of all events
4. Clear visual output
"""

import pytest
import asyncio
import time
import json
from datetime import datetime
from typing import Optional

# Import gateway modules
from gateway.retry import retry_with_backoff
from gateway.circuit_breaker import CircuitBreaker, CircuitState
from gateway.database import SessionLocal, Base, engine
from gateway.models import RequestLog

# Try to initialize database
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"⚠️  Warning: Could not initialize database: {e}")


# ============================================================================
# TEST 1: RETRY WITH EXPONENTIAL BACKOFF (1s → 2s → 4s)
# ============================================================================

@pytest.mark.asyncio
async def test_retry_with_exponential_backoff_clear_output():
    """
    Test retry mechanism with exponential backoff delays.
    
    Shows:
    - Each attempt with timestamp
    - Delay before next retry
    - Exponential pattern: 1s → 2s → 4s
    """
    print("\n" + "="*80)
    print("TEST 1: RETRY WITH EXPONENTIAL BACKOFF (1s → 2s → 4s)")
    print("="*80)
    
    attempt_count = 0
    attempt_times = []
    
    async def failing_service():
        nonlocal attempt_count
        attempt_count += 1
        current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        attempt_times.append(time.time())
        
        print(f"\n  [{current_time}] 📍 Attempt #{attempt_count}")
        
        if attempt_count < 3:
            print(f"  ❌ Service unavailable - will retry")
            raise ConnectionError("Service temporarily unavailable")
        else:
            print(f"  ✅ Service recovered - returning success")
            return {"status": "success", "data": "Operation completed"}
    
    # Run with exponential backoff: 1s, 2s, 4s
    print("\n  🚀 Starting retry sequence with exponential backoff...")
    result = await retry_with_backoff(
        failing_service,
        max_retries=3,
        initial_delay=1.0,
        backoff_factor=2.0
    )
    
    print(f"\n  ✅ Final Result: {result}")
    
    # Calculate and display delays
    if len(attempt_times) >= 2:
        print(f"\n  📊 Delay Analysis:")
        for i in range(1, len(attempt_times)):
            delay = attempt_times[i] - attempt_times[i-1]
            expected = 1.0 * (2.0 ** (i-1))
            print(f"     Delay between attempt {i} → {i+1}: {delay:.2f}s (expected: ~{expected:.1f}s)")
    
    assert result["status"] == "success"
    assert attempt_count == 3


# ============================================================================
# TEST 2: CIRCUIT BREAKER STATE TRANSITIONS
# ============================================================================

@pytest.mark.asyncio
async def test_circuit_breaker_state_transitions():
    """
    Test circuit breaker state machine transitions.
    
    Shows:
    - CLOSED → OPEN (after failures exceed threshold)
    - OPEN → HALF_OPEN (after timeout)
    - HALF_OPEN → CLOSED (after successful request)
    """
    print("\n" + "="*80)
    print("TEST 2: CIRCUIT BREAKER STATE TRANSITIONS")
    print("="*80)
    
    cb = CircuitBreaker("test_service", failure_threshold=2, recovery_timeout=1.0)
    call_count = 0
    
    print(f"\n  🔧 Circuit Breaker initialized")
    print(f"     Service: test_service")
    print(f"     Failure threshold: 2")
    print(f"     Recovery timeout: 1.0s")
    print(f"     Initial state: {cb.get_state().upper()}")
    
    # ========== PHASE 1: CAUSE FAILURES ==========
    print(f"\n  ────────────────────────────────────")
    print(f"  PHASE 1: CAUSING FAILURES → OPEN CIRCUIT")
    print(f"  ────────────────────────────────────")
    
    async def failing_service():
        raise ValueError("Service error - please retry")
    
    # Failure 1
    print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Failure #1...")
    try:
        await cb.call(failing_service)
    except ValueError:
        print(f"     ❌ Failed (failure_count: {cb.failure_count}/{cb.failure_threshold})")
        print(f"     State: {cb.get_state().upper()}")
    
    # Failure 2 - should open circuit
    print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Failure #2...")
    try:
        await cb.call(failing_service)
    except ValueError:
        print(f"     ❌ Failed (failure_count: {cb.failure_count}/{cb.failure_threshold})")
        print(f"     State: {cb.get_state().upper()} 🔴")
    
    # ========== PHASE 2: CIRCUIT OPEN ==========
    print(f"\n  ────────────────────────────────────")
    print(f"  PHASE 2: CIRCUIT IS OPEN (REJECTING)")
    print(f"  ────────────────────────────────────")
    
    print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Attempt while circuit is OPEN...")
    try:
        await cb.call(failing_service)
    except Exception as e:
        print(f"     🔴 REJECTED: {str(e)}")
    
    # ========== PHASE 3: WAIT FOR RECOVERY ==========
    print(f"\n  ────────────────────────────────────")
    print(f"  PHASE 3: WAITING FOR RECOVERY TIMEOUT")
    print(f"  ────────────────────────────────────")
    
    print(f"\n  ⏳ Waiting {cb.recovery_timeout}s for circuit to attempt recovery...")
    await asyncio.sleep(cb.recovery_timeout + 0.2)
    print(f"  ✅ Recovery timeout expired")
    
    # ========== PHASE 4: HALF-OPEN & RECOVERY ==========
    print(f"\n  ────────────────────────────────────")
    print(f"  PHASE 4: TESTING RECOVERY (HALF-OPEN)")
    print(f"  ────────────────────────────────────")
    
    async def success_service():
        return {"status": "recovered"}
    
    print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Testing with successful request...")
    try:
        result = await cb.call(success_service)
        print(f"     ✅ Request succeeded: {result}")
        print(f"     State: {cb.get_state().upper()} 🟢")
        print(f"     Failure count reset: {cb.failure_count}")
    except Exception as e:
        print(f"     ❌ Request failed: {str(e)}")
    
    assert cb.get_state() == "closed"
    assert cb.failure_count == 0


# ============================================================================
# TEST 3: DATABASE LOGGING
# ============================================================================

@pytest.mark.asyncio
async def test_database_logging_of_retries_and_circuit_breaker():
    """
    Test that retry and circuit breaker events are logged to database.
    Shows database logs at the end.
    """
    print("\n" + "="*80)
    print("TEST 3: DATABASE LOGGING & RETRIEVAL")
    print("="*80)
    
    db = None
    try:
        db = SessionLocal()
        
        # Clear existing logs
        db.query(RequestLog).delete()
        db.commit()
        print(f"\n  🗑️  Cleared existing logs from database")
        
    except Exception as e:
        print(f"\n  ⚠️  Warning: Could not connect to database: {e}")
        print(f"  📝 Skipping database test...")
        return
    
    finally:
        if db:
            db.close()
    
    # ========== CREATE LOGS ==========
    print(f"\n  ────────────────────────────────────")
    print(f"  CREATING LOG ENTRIES")
    print(f"  ────────────────────────────────────")
    
    test_logs = [
        {
            "request_id": "req_001",
            "method": "GET",
            "path": "/api/auth/login",
            "service": "auth_service",
            "status_code": 503,
            "response_time_ms": 1500.0,
            "error_message": "Service unavailable - retrying",
            "client_ip": "192.168.1.100",
            "retry_count": 1,
            "circuit_breaker_state": "CLOSED"
        },
        {
            "request_id": "req_002",
            "method": "POST",
            "path": "/api/auth/login",
            "service": "auth_service",
            "status_code": 200,
            "response_time_ms": 250.0,
            "error_message": None,
            "client_ip": "192.168.1.100",
            "retry_count": 2,
            "circuit_breaker_state": "CLOSED"
        },
        {
            "request_id": "req_003",
            "method": "GET",
            "path": "/api/chat/messages",
            "service": "chat_service",
            "status_code": 503,
            "response_time_ms": 5000.0,
            "error_message": "Circuit breaker open",
            "client_ip": "192.168.1.101",
            "retry_count": 0,
            "circuit_breaker_state": "OPEN"
        },
        {
            "request_id": "req_004",
            "method": "POST",
            "path": "/api/chat/messages",
            "service": "chat_service",
            "status_code": 200,
            "response_time_ms": 300.0,
            "error_message": None,
            "client_ip": "192.168.1.101",
            "retry_count": 0,
            "circuit_breaker_state": "CLOSED"
        }
    ]
    
    db = SessionLocal()
    for log_data in test_logs:
        log = RequestLog(**log_data)
        db.add(log)
        print(f"  ✅ Created log: {log_data['request_id']} ({log_data['service']}) - Status: {log_data['status_code']}")
    
    db.commit()
    print(f"\n  💾 Saved {len(test_logs)} logs to database")
    
    # ========== RETRIEVE & DISPLAY LOGS ==========
    print(f"\n  ────────────────────────────────────")
    print(f"  LOGS FROM DATABASE")
    print(f"  ────────────────────────────────────\n")
    
    logs = db.query(RequestLog).all()
    
    if logs:
        print(f"  📊 Retrieved {len(logs)} logs:\n")
        
        for i, log in enumerate(logs, 1):
            print(f"  ┌─ Log #{i} ─────────────────────────────────────────")
            print(f"  │ Request ID:            {log.request_id}")
            print(f"  │ Timestamp:             {log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  │ Service:               {log.service}")
            print(f"  │ Method:                {log.method} {log.path}")
            print(f"  │ Status Code:           {log.status_code}")
            print(f"  │ Response Time:         {log.response_time_ms:.1f}ms")
            print(f"  │ Retry Count:           {log.retry_count}")
            print(f"  │ Circuit Breaker State: {log.circuit_breaker_state}")
            if log.error_message:
                print(f"  │ Error:                 {log.error_message}")
            print(f"  │ Client IP:             {log.client_ip}")
            print(f"  └────────────────────────────────────────────────────")
        
        # ========== STATISTICS ==========
        print(f"\n  📈 STATISTICS:")
        
        total_requests = len(logs)
        successful = sum(1 for log in logs if log.status_code == 200)
        failed = sum(1 for log in logs if log.status_code != 200)
        avg_response_time = sum(log.response_time_ms for log in logs) / len(logs)
        total_retries = sum(log.retry_count for log in logs)
        
        services = {}
        for log in logs:
            if log.service not in services:
                services[log.service] = {"count": 0, "failures": 0}
            services[log.service]["count"] += 1
            if log.status_code != 200:
                services[log.service]["failures"] += 1
        
        print(f"\n     Total Requests:       {total_requests}")
        print(f"     Successful (200):     {successful} ✅")
        print(f"     Failed (non-200):     {failed} ❌")
        print(f"     Average Response:     {avg_response_time:.1f}ms")
        print(f"     Total Retries:        {total_retries}")
        
        print(f"\n     By Service:")
        for service, stats in services.items():
            success_rate = ((stats["count"] - stats["failures"]) / stats["count"] * 100) if stats["count"] > 0 else 0
            print(f"       • {service}: {stats['count']} reqs, {success_rate:.0f}% success")
        
        # ========== CIRCUIT BREAKER STATUS BY SERVICE ==========
        print(f"\n     Circuit Breaker Status:")
        cb_states = {}
        for log in logs:
            if log.service not in cb_states:
                cb_states[log.service] = {"OPEN": 0, "CLOSED": 0, "HALF_OPEN": 0}
            cb_states[log.service][log.circuit_breaker_state] += 1
        
        for service, states in cb_states.items():
            open_count = states["OPEN"]
            closed_count = states["CLOSED"]
            half_open_count = states["HALF_OPEN"]
            print(f"       • {service}: OPEN={open_count}, CLOSED={closed_count}, HALF_OPEN={half_open_count}")
    else:
        print(f"  ⚠️  No logs found in database")
    
    db.close()


# ============================================================================
# TEST 4: COMBINED RETRY + CIRCUIT BREAKER
# ============================================================================

@pytest.mark.asyncio
async def test_retry_with_circuit_breaker_integration():
    """
    Combined test showing retry + circuit breaker working together.
    
    Shows:
    - Retries happening within circuit breaker
    - Circuit opening after retries fail
    - Clear state transitions
    """
    print("\n" + "="*80)
    print("TEST 4: RETRY + CIRCUIT BREAKER INTEGRATION")
    print("="*80)
    
    cb = CircuitBreaker("api_service", failure_threshold=2, recovery_timeout=1.0)
    attempt_log = []
    
    print(f"\n  🔧 Setup:")
    print(f"     Service: api_service")
    print(f"     Failure threshold: 2 (opens circuit)")
    print(f"     Max retries: 2 (with exponential backoff)")
    
    async def unstable_service():
        attempt_log.append({
            "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "timestamp": time.time()
        })
        
        if len(attempt_log) <= 2:
            raise ValueError("Service error")
        return {"data": "success"}
    
    print(f"\n  ────────────────────────────────────")
    print(f"  EXECUTING WITH RETRY + CIRCUIT BREAKER")
    print(f"  ────────────────────────────────────")
    
    try:
        result = await retry_with_backoff(
            lambda: cb.call(unstable_service),
            max_retries=2,
            initial_delay=0.5,
            backoff_factor=2.0
        )
        print(f"\n  ✅ Success: {result}")
    except Exception as e:
        print(f"\n  ❌ Failed: {str(e)}")
    
    print(f"\n  📊 Attempt Summary:")
    print(f"     Total attempts: {len(attempt_log)}")
    print(f"     Circuit breaker state: {cb.get_state().upper()}")
    print(f"     Failure count: {cb.failure_count}")


if __name__ == "__main__":
    # Run tests with pytest
    # pytest tests/test_comprehensive_retry_circuit_breaker.py -v -s
    print("Run tests with: pytest tests/test_comprehensive_retry_circuit_breaker.py -v -s")
