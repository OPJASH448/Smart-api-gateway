"""
GatewayLogger — structured, async-friendly request logger.

Each log entry is a JSON line so it's easy to ingest into tools like
Loki, Datadog, or just grep.

Phase 1: writes to stdout + in-memory ring buffer (last 500 entries).
Phase 2 will persist to PostgreSQL and stream to Redis pub/sub.
Phase 3: PostgreSQL structured logging with retry & circuit breaker tracking.
"""

import asyncio
import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

# Try to import database dependencies, graceful fallback if not available
try:
    from gateway.database import SessionLocal
    from gateway.models import RequestLog
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


# Configure Python's root logger to output clean lines
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
log = logging.getLogger("gateway")


class GatewayLogger:
    MAX_BUFFER = 500  # in-memory ring buffer size

    def __init__(self):
        # Ring buffer of recent log entries for the /gateway/logs endpoint (Phase 2)
        self._buffer: deque[dict] = deque(maxlen=self.MAX_BUFFER)
        self._lock = asyncio.Lock()
        self._db_available = DB_AVAILABLE

    async def log(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        service: str,
        upstream: str,
        status: int,
        latency_ms: float,
        client_ip: str = "unknown",
        error: Optional[str] = None,
        retry_count: int = 0,
        circuit_state: str = "CLOSED",
    ) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "method": method,
            "path": path,
            "service": service,
            "upstream": upstream,
            "status": status,
            "latency_ms": round(latency_ms, 2),
            "client_ip": client_ip,
            "retry_count": retry_count,
            "circuit_state": circuit_state,
        }
        if error:
            entry["error"] = error

        async with self._lock:
            self._buffer.append(entry)

        # Emoji-prefixed status for human-readable console output
        icon = "✅" if status < 400 else ("⚠️ " if status < 500 else "❌")
        log.info(
            f"{icon} [{request_id}] {method} {path} → {service} "
            f"| {status} | {latency_ms:.1f}ms | retries={retry_count} | cb={circuit_state}"
        )
        
        # Log to PostgreSQL if available
        if self._db_available:
            try:
                await self._log_to_db(
                    request_id=request_id,
                    method=method,
                    path=path,
                    service=service,
                    status_code=status,
                    response_time_ms=latency_ms,
                    client_ip=client_ip,
                    error_message=error,
                    retry_count=retry_count,
                    circuit_breaker_state=circuit_state,
                )
            except Exception as e:
                # Graceful fallback - don't crash the gateway if DB logging fails
                log.warning(f"Failed to log to database: {str(e)}")

    async def _log_to_db(
        self,
        request_id: str,
        method: str,
        path: str,
        service: str,
        status_code: int,
        response_time_ms: float,
        client_ip: str,
        error_message: Optional[str] = None,
        retry_count: int = 0,
        circuit_breaker_state: str = "CLOSED",
    ) -> None:
        """Log request to PostgreSQL database."""
        try:
            db = SessionLocal()
            log_entry = RequestLog(
                request_id=request_id,
                method=method,
                path=path,
                service=service,
                status_code=status_code,
                response_time_ms=response_time_ms,
                client_ip=client_ip,
                error_message=error_message,
                retry_count=retry_count,
                circuit_breaker_state=circuit_breaker_state,
            )
            db.add(log_entry)
            db.commit()
            db.close()
        except Exception as e:
            # Fail gracefully
            log.warning(f"Database logging error: {str(e)}")

    def recent(self, n: int = 50) -> list[dict]:
        """Return the n most recent log entries (newest last)."""
        entries = list(self._buffer)
        return entries[-n:]

    def stats(self) -> dict:
        """Aggregate stats over the buffered window."""
        entries = list(self._buffer)
        if not entries:
            return {"total": 0}

        total = len(entries)
        errors = sum(1 for e in entries if e["status"] >= 500)
        latencies = [e["latency_ms"] for e in entries]
        avg_latency = sum(latencies) / len(latencies)

        by_service: dict[str, int] = {}
        for e in entries:
            by_service[e["service"]] = by_service.get(e["service"], 0) + 1

        return {
            "total": total,
            "errors": errors,
            "error_rate": round(errors / total * 100, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "by_service": by_service,
        }
