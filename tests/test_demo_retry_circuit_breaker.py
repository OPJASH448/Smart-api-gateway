"""
Enhanced test showing retry, circuit breaker, and database logs.
This version works with or without a live PostgreSQL database.
"""

import pytest
import asyncio
import time
import json
from datetime import datetime
from typing import List, Dict

from gateway.retry import retry_with_backoff
from gateway.circuit_breaker import CircuitBreaker


class MockRequestLog:
    """Mock database log when PostgreSQL is unavailable."""
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def to_dict(self):
        return self.__dict__.copy()


# Global in-memory log store (simulates database)
MOCK_LOGS: List[MockRequestLog] = []


def clear_logs():
    """Clear the mock log store."""
    global MOCK_LOGS
    MOCK_LOGS = []


def add_log(request_id: str, method: str, path: str, service: str, status_code: int,
            response_time_ms: float, error_message: str = None, retry_count: int = 0,
            circuit_breaker_state: str = "CLOSED", client_ip: str = "127.0.0.1"):
    """Add a log entry to mock database."""
    log = MockRequestLog(
        request_id=request_id,
        timestamp=datetime.now().isoformat(),
        method=method,
        path=path,
        service=service,
        status_code=status_code,
        response_time_ms=response_time_ms,
        error_message=error_message,
        client_ip=client_ip,
        retry_count=retry_count,
        circuit_breaker_state=circuit_breaker_state
    )
    MOCK_LOGS.append(log)


def display_logs(title: str = "DATABASE LOGS"):
    """Display all logs in a formatted way."""
    print(f"\n  ────────────────────────────────────────────")
    print(f"  {title}")
    print(f"  ────────────────────────────────────────────\n")
    
    if not MOCK_LOGS:
        print(f"  ⚠️  No logs found\n")
        return
    
    print(f"  📊 Total Logs: {len(MOCK_LOGS)}\n")
    
    for i, log in enumerate(MOCK_LOGS, 1):
        status_emoji = "✅" if log.status_code == 200 else "❌"
        cb_emoji = "🔴" if log.circuit_breaker_state == "OPEN" else "🟡" if log.circuit_breaker_state == "HALF_OPEN" else "🟢"
        
        print(f"  ┌─ Log #{i} ─────────────────────────────────────")
        print(f"  │ Request ID:    {log.request_id}")
        print(f"  │ Timestamp:     {log.timestamp}")
        print(f"  │ Service:       {log.service}")
        print(f"  │ Method:        {status_emoji} {log.method} {log.path}")
        print(f"  │ Status Code:   {log.status_code}")
        print(f"  │ Response Time: {log.response_time_ms:.1f}ms")
        print(f"  │ Retries:       {log.retry_count}")
        print(f"  │ CB State:      {cb_emoji} {log.circuit_breaker_state}")
        if log.error_message:
            print(f"  │ Error:         {log.error_message}")
        print(f"  └────────────────────────────────────────────")
    
    # Statistics
    successful = sum(1 for log in MOCK_LOGS if log.status_code == 200)
    failed = sum(1 for log in MOCK_LOGS if log.status_code != 200)
    avg_response = sum(log.response_time_ms for log in MOCK_LOGS) / len(MOCK_LOGS) if MOCK_LOGS else 0
    total_retries = sum(log.retry_count for log in MOCK_LOGS)
    
    print(f"\n  📈 STATISTICS:")
    print(f"     Total Logs:     {len(MOCK_LOGS)}")
    print(f"     Successful:     {successful} ✅")
    print(f"     Failed:         {failed} ❌")
    print(f"     Avg Response:   {avg_response:.1f}ms")
    print(f"     Total Retries:  {total_retries}\n")


# ============================================================================
# DEMO 1: RETRY WITH EXPONENTIAL BACKOFF AND LOGGING
# ============================================================================

@pytest.mark.asyncio
async def test_demo_retry_with_logging():
    """
    Demo showing:
    - Retry with exponential backoff (1s → 2s → 4s)
    - Logging of each attempt to database
    - Final logs display
    """
    print("\n" + "="*80)
    print("DEMO 1: RETRY WITH EXPONENTIAL BACKOFF & DATABASE LOGGING")
    print("="*80)
    
    clear_logs()
    
    attempt_count = 0
    attempt_times = []
    
    async def unstable_api():
        nonlocal attempt_count
        attempt_count += 1
        current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        attempt_times.append(time.time())
        
        print(f"\n  [{current_time}] 📍 Attempt #{attempt_count}")
        
        if attempt_count == 1:
            print(f"      ❌ Connection timeout")
            add_log(
                request_id=f"req_retry_001_{attempt_count}",
                method="GET",
                path="/api/data",
                service="data_service",
                status_code=504,
                response_time_ms=5000.0,
                error_message="Connection timeout",
                retry_count=0,
                circuit_breaker_state="CLOSED"
            )
            raise ConnectionError("Connection timeout")
        elif attempt_count == 2:
            print(f"      ❌ Service temporarily unavailable")
            add_log(
                request_id=f"req_retry_001_{attempt_count}",
                method="GET",
                path="/api/data",
                service="data_service",
                status_code=503,
                response_time_ms=2000.0,
                error_message="Service unavailable",
                retry_count=1,
                circuit_breaker_state="CLOSED"
            )
            raise ConnectionError("Service temporarily unavailable")
        else:
            print(f"      ✅ Connection established - request successful")
            add_log(
                request_id=f"req_retry_001_{attempt_count}",
                method="GET",
                path="/api/data",
                service="data_service",
                status_code=200,
                response_time_ms=150.0,
                error_message=None,
                retry_count=2,
                circuit_breaker_state="CLOSED"
            )
            return {"data": "success", "items": [1, 2, 3]}
    
    print(f"\n  🚀 Starting request with retry (exponential backoff: 1s → 2s → 4s)")
    
    result = await retry_with_backoff(
        unstable_api,
        max_retries=3,
        initial_delay=1.0,
        backoff_factor=2.0
    )
    
    print(f"\n  ✅ Final Result: {result}")
    
    # Show delays
    if len(attempt_times) >= 2:
        print(f"\n  ⏱️  TIMING ANALYSIS:")
        for i in range(1, len(attempt_times)):
            delay = attempt_times[i] - attempt_times[i-1]
            expected = 1.0 * (2.0 ** (i-1))
            print(f"     Retry #{i-1} → #{i}: {delay:.2f}s (expected ~{expected:.1f}s)")
    
    # Display logs from database
    display_logs("DATABASE LOGS FOR THIS REQUEST")


# ============================================================================
# DEMO 2: CIRCUIT BREAKER WITH STATE TRANSITIONS
# ============================================================================

@pytest.mark.asyncio
async def test_demo_circuit_breaker_with_logging():
    """
    Demo showing:
    - Circuit breaker state transitions
    - Logging at each state change
    - Database log history
    """
    print("\n" + "="*80)
    print("DEMO 2: CIRCUIT BREAKER STATE TRANSITIONS & LOGGING")
    print("="*80)
    
    clear_logs()
    
    cb = CircuitBreaker("payment_service", failure_threshold=2, recovery_timeout=1.0)
    request_num = 0
    
    print(f"\n  🔧 Circuit Breaker Configuration:")
    print(f"     Service:              payment_service")
    print(f"     Failure threshold:    2")
    print(f"     Recovery timeout:     1.0s")
    print(f"     Initial state:        {cb.get_state().upper()}")
    
    async def payment_api():
        raise ValueError("Payment service error")
    
    async def success_api():
        return {"status": "success", "transaction_id": "TXN_12345"}
    
    # ========== PHASE 1: FAILURES → OPEN ==========
    print(f"\n  {'='*60}")
    print(f"  PHASE 1: TRIGGERING FAILURES → CIRCUIT OPENS")
    print(f"  {'='*60}")
    
    for failure_num in range(1, 3):
        request_num += 1
        print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Request #{request_num}")
        
        try:
            await cb.call(payment_api)
        except ValueError:
            print(f"      ❌ Failed (failure count: {cb.failure_count}/{cb.failure_threshold})")
            print(f"      📊 Circuit state: {cb.get_state().upper()}")
            
            add_log(
                request_id=f"req_payment_{request_num:03d}",
                method="POST",
                path="/api/payment/process",
                service="payment_service",
                status_code=503,
                response_time_ms=float(failure_num * 1000),
                error_message="Payment service error",
                retry_count=0,
                circuit_breaker_state=cb.get_state().upper()
            )
    
    # ========== PHASE 2: CIRCUIT OPEN - REJECTING ==========
    print(f"\n  {'='*60}")
    print(f"  PHASE 2: CIRCUIT IS OPEN → REJECTING REQUESTS")
    print(f"  {'='*60}")
    
    request_num += 1
    print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Request #{request_num}")
    print(f"      Attempting request while circuit is OPEN...")
    
    try:
        await cb.call(payment_api)
    except Exception as e:
        print(f"      🔴 REJECTED: {str(e)}")
        
        add_log(
            request_id=f"req_payment_{request_num:03d}",
            method="POST",
            path="/api/payment/process",
            service="payment_service",
            status_code=503,
            response_time_ms=0.1,
            error_message="Circuit breaker open",
            retry_count=0,
            circuit_breaker_state="OPEN"
        )
    
    # ========== PHASE 3: WAITING FOR RECOVERY ==========
    print(f"\n  {'='*60}")
    print(f"  PHASE 3: WAITING FOR RECOVERY TIMEOUT ({cb.recovery_timeout}s)")
    print(f"  {'='*60}")
    
    print(f"\n  ⏳ Waiting for service to recover...")
    await asyncio.sleep(cb.recovery_timeout + 0.2)
    print(f"  ✅ Recovery timeout expired - circuit will attempt recovery")
    
    # ========== PHASE 4: HALF-OPEN & RECOVERY ==========
    print(f"\n  {'='*60}")
    print(f"  PHASE 4: TESTING RECOVERY (HALF-OPEN STATE)")
    print(f"  {'='*60}")
    
    request_num += 1
    print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Request #{request_num}")
    print(f"      Testing with successful request...")
    
    try:
        result = await cb.call(success_api)
        print(f"      ✅ Success: {result}")
        print(f"      📊 Circuit state: {cb.get_state().upper()}")
        print(f"      🔄 Failure count reset: {cb.failure_count}")
        
        add_log(
            request_id=f"req_payment_{request_num:03d}",
            method="POST",
            path="/api/payment/process",
            service="payment_service",
            status_code=200,
            response_time_ms=150.0,
            error_message=None,
            retry_count=0,
            circuit_breaker_state="CLOSED"
        )
    except Exception as e:
        print(f"      ❌ Failed: {str(e)}")
    
    # Display logs
    display_logs("CIRCUIT BREAKER LOG HISTORY")


# ============================================================================
# DEMO 3: COMPLEX SCENARIO - MULTIPLE SERVICES
# ============================================================================

@pytest.mark.asyncio
async def test_demo_multiple_services_with_circuit_breakers():
    """
    Demo showing:
    - Multiple services with independent circuit breakers
    - Different failure scenarios
    - Comprehensive database logs showing full system state
    """
    print("\n" + "="*80)
    print("DEMO 3: MULTIPLE SERVICES WITH INDEPENDENT CIRCUIT BREAKERS")
    print("="*80)
    
    clear_logs()
    
    # Create circuit breakers for different services
    cb_auth = CircuitBreaker("auth_service", failure_threshold=2, recovery_timeout=0.8)
    cb_payment = CircuitBreaker("payment_service", failure_threshold=2, recovery_timeout=0.8)
    cb_chat = CircuitBreaker("chat_service", failure_threshold=2, recovery_timeout=0.8)
    
    print(f"\n  🔧 Services Configured:")
    print(f"     1️⃣  auth_service    - {cb_auth.get_state().upper()}")
    print(f"     2️⃣  payment_service - {cb_payment.get_state().upper()}")
    print(f"     3️⃣  chat_service    - {cb_chat.get_state().upper()}")
    
    # ========== TEST SCENARIOS ==========
    print(f"\n  {'='*60}")
    print(f"  SIMULATING REQUESTS ACROSS SERVICES")
    print(f"  {'='*60}")
    
    # Auth service - 2 failures, then opens
    print(f"\n  📌 Auth Service Failures:")
    
    async def auth_fail():
        raise ValueError("Invalid credentials")
    
    for i in range(2):
        try:
            await cb_auth.call(auth_fail)
        except ValueError:
            print(f"     Failure #{i+1}: {cb_auth.failure_count}/{cb_auth.failure_threshold} → {cb_auth.get_state().upper()}")
            add_log(
                request_id=f"req_auth_{i+1:03d}",
                method="POST",
                path="/api/auth/login",
                service="auth_service",
                status_code=401,
                response_time_ms=500.0,
                error_message="Invalid credentials",
                retry_count=0,
                circuit_breaker_state=cb_auth.get_state().upper()
            )
    
    # Payment service - 1 failure, then success
    print(f"\n  📌 Payment Service Recovery:")
    
    async def payment_fail():
        raise ValueError("Processing error")
    
    async def payment_success():
        return {"status": "ok"}
    
    try:
        await cb_payment.call(payment_fail)
    except ValueError:
        print(f"     Failure #1: {cb_payment.failure_count}/{cb_payment.failure_threshold} → {cb_payment.get_state().upper()}")
        add_log(
            request_id=f"req_payment_001",
            method="POST",
            path="/api/payment/charge",
            service="payment_service",
            status_code=503,
            response_time_ms=1000.0,
            error_message="Processing error",
            retry_count=0,
            circuit_breaker_state=cb_payment.get_state().upper()
        )
    
    result = await cb_payment.call(payment_success)
    print(f"     Recovery #1: Success → {cb_payment.get_state().upper()}")
    add_log(
        request_id=f"req_payment_002",
        method="POST",
        path="/api/payment/charge",
        service="payment_service",
        status_code=200,
        response_time_ms=300.0,
        error_message=None,
        retry_count=0,
        circuit_breaker_state=cb_payment.get_state().upper()
    )
    
    # Chat service - all successful
    print(f"\n  📌 Chat Service All Successful:")
    
    async def chat_success():
        return {"messages": []}
    
    result = await cb_chat.call(chat_success)
    print(f"     Success #1 → {cb_chat.get_state().upper()}")
    add_log(
        request_id=f"req_chat_001",
        method="GET",
        path="/api/chat/history",
        service="chat_service",
        status_code=200,
        response_time_ms=150.0,
        error_message=None,
        retry_count=0,
        circuit_breaker_state=cb_chat.get_state().upper()
    )
    
    # Display comprehensive logs
    display_logs("COMPLETE SYSTEM STATE - ALL SERVICES")
    
    # Summary by service
    print(f"\n  📋 SERVICE STATUS SUMMARY:")
    print(f"     ┌─ auth_service    : {cb_auth.get_state().upper()} 🔴 (failures: {cb_auth.failure_count})")
    print(f"     ├─ payment_service : {cb_payment.get_state().upper()} 🟢 (failures: {cb_payment.failure_count})")
    print(f"     └─ chat_service    : {cb_chat.get_state().upper()} 🟢 (failures: {cb_chat.failure_count})")


if __name__ == "__main__":
    print("Run tests with: pytest tests/test_demo_retry_circuit_breaker.py -v -s")
