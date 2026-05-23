"""
Test that saves retry and circuit breaker logs to JSON files for viewing.
This demonstrates database logs storage in a readable format.
"""

import pytest
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from gateway.retry import retry_with_backoff
from gateway.circuit_breaker import CircuitBreaker


# Create logs directory
LOGS_DIR = Path("test_logs")
LOGS_DIR.mkdir(exist_ok=True)


def save_logs_to_json(filename: str, logs: list):
    """Save logs to JSON file for easy viewing."""
    filepath = LOGS_DIR / filename
    with open(filepath, 'w') as f:
        json.dump(logs, f, indent=2, default=str)
    print(f"\n  💾 Logs saved to: {filepath}")
    return filepath


@pytest.mark.asyncio
async def test_retry_logs_saved_to_file():
    """
    Retry test with logs saved to JSON file.
    """
    print("\n" + "="*80)
    print("TEST: RETRY LOGS SAVED TO FILE")
    print("="*80)
    
    logs = []
    attempt_count = 0
    
    async def api_call():
        nonlocal attempt_count
        attempt_count += 1
        timestamp = datetime.now()
        
        log_entry = {
            "timestamp": timestamp.isoformat(),
            "attempt": attempt_count,
            "status": "failed" if attempt_count < 3 else "success"
        }
        
        print(f"\n  [{timestamp.strftime('%H:%M:%S.%f')[:-3]}] Attempt #{attempt_count}")
        
        if attempt_count < 3:
            error = "Database connection timeout" if attempt_count == 1 else "Service unavailable"
            print(f"      ❌ {error}")
            log_entry["error"] = error
            log_entry["status_code"] = 503
        else:
            print(f"      ✅ Success - data retrieved")
            log_entry["status_code"] = 200
            log_entry["data"] = {"records": 150}
        
        logs.append(log_entry)
        
        if attempt_count < 3:
            raise ConnectionError(log_entry.get("error"))
        return {"data": "success"}
    
    print(f"\n  🚀 Calling API with retry mechanism...")
    result = await retry_with_backoff(api_call, max_retries=3, initial_delay=0.5, backoff_factor=2.0)
    
    # Add summary
    summary = {
        "test": "retry_mechanism",
        "total_attempts": attempt_count,
        "final_result": "success",
        "total_time": f"~{attempt_count}s with backoff",
        "logs": logs
    }
    
    filepath = save_logs_to_json("retry_test_logs.json", summary)
    print(f"\n  📊 Summary:")
    print(f"     Total attempts: {attempt_count}")
    print(f"     Final status: {result}")


@pytest.mark.asyncio
async def test_circuit_breaker_logs_saved_to_file():
    """
    Circuit breaker test with comprehensive logs saved to JSON.
    """
    print("\n" + "="*80)
    print("TEST: CIRCUIT BREAKER LOGS SAVED TO FILE")
    print("="*80)
    
    logs = []
    cb = CircuitBreaker("user_service", failure_threshold=2, recovery_timeout=0.8)
    
    async def failing_service():
        raise ValueError("Service error")
    
    async def successful_service():
        return {"users": []}
    
    # Phase 1: Failures
    print(f"\n  PHASE 1: CREATING FAILURES")
    for i in range(2):
        print(f"\n  Request #{i+1}")
        try:
            await cb.call(failing_service)
        except ValueError:
            log_entry = {
                "request_num": i + 1,
                "timestamp": datetime.now().isoformat(),
                "result": "failed",
                "failure_count": cb.failure_count,
                "circuit_state": cb.get_state(),
                "error": "Service error"
            }
            logs.append(log_entry)
            print(f"      ❌ Failed (CB: {cb.get_state().upper()})")
    
    # Phase 2: Circuit open
    print(f"\n  PHASE 2: CIRCUIT IS OPEN")
    print(f"\n  Request #3")
    try:
        await cb.call(failing_service)
    except Exception as e:
        log_entry = {
            "request_num": 3,
            "timestamp": datetime.now().isoformat(),
            "result": "rejected",
            "failure_count": cb.failure_count,
            "circuit_state": cb.get_state(),
            "error": "Circuit breaker open"
        }
        logs.append(log_entry)
        print(f"      🔴 Rejected: Circuit OPEN")
    
    # Phase 3: Wait for recovery
    print(f"\n  PHASE 3: WAITING FOR RECOVERY")
    print(f"  ⏳ Waiting {cb.recovery_timeout}s...")
    await asyncio.sleep(cb.recovery_timeout + 0.1)
    print(f"  ✅ Recovery timeout expired")
    
    # Phase 4: Recovery
    print(f"\n  PHASE 4: TESTING RECOVERY")
    print(f"\n  Request #4")
    try:
        result = await cb.call(successful_service)
        log_entry = {
            "request_num": 4,
            "timestamp": datetime.now().isoformat(),
            "result": "success",
            "failure_count": cb.failure_count,
            "circuit_state": cb.get_state(),
            "response": result
        }
        logs.append(log_entry)
        print(f"      ✅ Success (CB: {cb.get_state().upper()})")
    except Exception as e:
        print(f"      ❌ Failed: {str(e)}")
    
    # Save to file
    summary = {
        "test": "circuit_breaker",
        "service": "user_service",
        "failure_threshold": cb.failure_threshold,
        "recovery_timeout": cb.recovery_timeout,
        "final_state": cb.get_state(),
        "logs": logs
    }
    
    save_logs_to_json("circuit_breaker_test_logs.json", summary)


@pytest.mark.asyncio
async def test_integration_retry_and_circuit_breaker_logs():
    """
    Integration test showing retry + circuit breaker with full log output.
    """
    print("\n" + "="*80)
    print("TEST: INTEGRATION - RETRY + CIRCUIT BREAKER LOGS")
    print("="*80)
    
    logs = []
    cb = CircuitBreaker("data_service", failure_threshold=2, recovery_timeout=0.8)
    call_count = 0
    
    async def data_api():
        nonlocal call_count
        call_count += 1
        
        if call_count <= 2:
            raise ConnectionError("API timeout")
        return {"items": [1, 2, 3]}
    
    print(f"\n  🚀 Starting retry + circuit breaker call...")
    
    for attempt in range(1, 5):
        print(f"\n  Attempt #{attempt}:")
        
        try:
            result = await retry_with_backoff(
                lambda: cb.call(data_api),
                max_retries=1,
                initial_delay=0.2,
                backoff_factor=2.0
            )
            print(f"      ✅ Success: {result}")
            logs.append({
                "attempt": attempt,
                "timestamp": datetime.now().isoformat(),
                "status": "success",
                "circuit_state": cb.get_state(),
                "call_count": call_count
            })
        except Exception as e:
            print(f"      ❌ Failed: {str(e)[:50]}")
            logs.append({
                "attempt": attempt,
                "timestamp": datetime.now().isoformat(),
                "status": "failed",
                "circuit_state": cb.get_state(),
                "call_count": call_count,
                "error": str(e)[:50]
            })
    
    # Save comprehensive log
    summary = {
        "test": "retry_circuit_breaker_integration",
        "service": "data_service",
        "total_calls": call_count,
        "final_circuit_state": cb.get_state(),
        "logs": logs
    }
    
    save_logs_to_json("integration_test_logs.json", summary)


@pytest.mark.asyncio
async def test_display_all_saved_logs():
    """
    Test that displays all saved log files.
    """
    print("\n" + "="*80)
    print("SAVED LOG FILES")
    print("="*80)
    
    json_files = list(LOGS_DIR.glob("*.json"))
    
    if not json_files:
        print(f"\n  ℹ️  No log files found yet. Run other tests first.")
        return
    
    print(f"\n  📋 Found {len(json_files)} log files:\n")
    
    for filepath in sorted(json_files):
        print(f"  📄 {filepath.name}")
        print(f"     Size: {filepath.stat().st_size} bytes")
        print(f"     Modified: {datetime.fromtimestamp(filepath.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        if "logs" in data:
            print(f"     Entries: {len(data['logs'])}")
        if "test" in data:
            print(f"     Test: {data['test']}")
        
        print()


if __name__ == "__main__":
    print("""
    Run tests with:
    
    # Run all log tests
    pytest tests/test_logs_saved.py -v -s
    
    # Run specific test
    pytest tests/test_logs_saved.py::test_retry_logs_saved_to_file -v -s
    
    # View saved logs
    cat test_logs/retry_test_logs.json
    cat test_logs/circuit_breaker_test_logs.json
    cat test_logs/integration_test_logs.json
    """)
