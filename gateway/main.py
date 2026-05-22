"""
Smart API Gateway - Phase 1: Core Reverse Proxy
Entry point for the FastAPI gateway server.
"""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gateway.config import settings
from gateway.router import GatewayRouter
from gateway.connection_pool import ConnectionPoolManager
from gateway.logger import GatewayLogger
from gateway.database import db_manager
from gateway.auth import validate_token
from gateway.rate_limit import is_rate_limited


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise shared resources on startup; clean up on shutdown."""
    # Initialize HTTP pools
    app.state.pool_manager = ConnectionPoolManager()
    await app.state.pool_manager.startup()

    # Initialize DB & Redis
    await db_manager.connect()
    app.state.db = db_manager

    app.state.router = GatewayRouter(settings)
    app.state.logger = GatewayLogger()

    print("✅ Gateway started — connection pools ready")
    yield

    await db_manager.disconnect()
    await app.state.pool_manager.shutdown()
    print("🛑 Gateway shut down — pools closed")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Smart API Gateway",
    description="Phase 1 — Core reverse proxy with async forwarding & connection pooling",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Middleware: request tracing ───────────────────────────────────────────────

@app.middleware("http")
async def request_tracing_middleware(request: Request, call_next):
    """Attach a unique request-ID and measure latency for every request."""
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    request.state.start_time = time.monotonic()

    # Inject tracing header so downstream services can correlate logs
    request.headers.__dict__["_list"].append(
        (b"x-request-id", request_id.encode())
    )

    response = await call_next(request)

    elapsed_ms = (time.monotonic() - request.state.start_time) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{elapsed_ms:.2f}ms"
    return response


@app.middleware("http")
async def gateway_logic_middleware(request: Request, call_next):
    """
    Combined Auth & Rate Limiting middleware.
    Decoupled from the proxy function so it applies to internal routes too.
    """
    path = request.url.path
    is_public = any(path.startswith(p) for p in settings.public_prefixes)
    
    # 1. Authentication
    user_payload = None
    if not is_public:
        try:
            user_payload = validate_token(request)
            if not user_payload:
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized", "message": "Authentication required"}
                )
            # Store payload for potential downstream use (in request.state)
            request.state.user = user_payload
        except HTTPException as e:
            return JSONResponse(status_code=e.status_code, content={"error": "auth_failed", "message": e.detail})

    # 2. Rate Limiting
    client_ip = request.client.host if request.client else "unknown"
    limit_key = user_payload.get("sub") if user_payload else client_ip
    
    is_limited, remaining = await is_rate_limited(
        limit_key, 
        settings.rate_limit_requests, 
        settings.rate_limit_window
    )
    
    if is_limited:
        return JSONResponse(
            status_code=429,
            content={"error": "too_many_requests", "message": "Rate limit exceeded"}
        )

    # 3. Proceed to route or proxy
    response = await call_next(request)
    
    # 4. Inject rate limit headers
    if remaining != -1:
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        
    return response


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["Gateway"])
async def health_check():
    return {"status": "ok", "service": "smart-api-gateway", "phase": 1}


@app.get("/gateway/routes", tags=["Gateway"])
async def list_routes(request: Request):
    """Return the current routing table so you can inspect it at runtime."""
    router: GatewayRouter = request.app.state.router
    return {"routes": router.describe()}


@app.get("/gateway/debug", tags=["Gateway"])
async def debug_status(request: Request):
    """Detailed health check including DB and Redis status."""
    db_ok = False
    redis_ok = False
    
    try:
        # Check MongoDB connection
        await db_manager.client.admin.command('ping')
        db_ok = True
    except:
        db_ok = False

    try:
        if db_manager.redis:
            await db_manager.redis.ping()
            redis_ok = True
    except:
        redis_ok = False

    return {
        "gateway": "ok",
        "database": "connected (MongoDB)" if db_ok else "unavailable",
        "redis": "connected" if redis_ok else "unavailable",
        "config": {
            "environment": settings.environment,
            "port": settings.gateway_port
        }
    }


@app.get("/gateway/cache-test", tags=["Gateway"])
async def cache_test():
    """Simple test to verify Redis is connected."""
    if not db_manager.redis:
        return JSONResponse(
            status_code=503,
            content={"error": "redis_unavailable", "message": "Redis client not initialized"}
        )
    
    try:
        uid = str(uuid.uuid4())[:8]
        await db_manager.redis.set(f"test:{uid}", "working", ex=10)
        val = await db_manager.redis.get(f"test:{uid}")
        return {"redis": "ok", "value": val, "key": f"test:{uid}"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"error": "redis_error", "message": str(e)}
        )


# ── Catch-all proxy ───────────────────────────────────────────────────────────

@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    tags=["Proxy"],
)
async def proxy(request: Request, full_path: str):
    """
    Core reverse-proxy handler.
    Delegates forward to targeted service.
    """
    router: GatewayRouter = request.app.state.router
    pool_manager: ConnectionPoolManager = request.app.state.pool_manager
    logger: GatewayLogger = request.app.state.logger

    # 1. Route resolution
    upstream_url, service_name = router.resolve(request.url.path)
    if upstream_url is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "no_route",
                "message": f"No upstream configured for path: /{full_path}",
                "path": f"/{full_path}",
            },
        )

    # 2. Forward the request
    try:
        client: httpx.AsyncClient = pool_manager.get_client(service_name)

        # Re-assemble query string
        target_url = upstream_url
        if request.url.query:
            target_url = f"{upstream_url}?{request.url.query}"

        body = await request.body()
        user_payload = getattr(request.state, "user", None)

        # Copy headers; strip hop-by-hop headers
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower()
            not in {
                "host",
                "content-length",
                "transfer-encoding",
                "connection",
                "keep-alive",
                "upgrade",
                "proxy-authenticate",
                "proxy-authorization",
                "te",
                "trailers",
            }
        }
        headers["X-Forwarded-For"] = request.client.host if request.client else "unknown"
        headers["X-Forwarded-Host"] = request.headers.get("host", "gateway")
        headers["X-Gateway-Service"] = service_name

        # Inject user context if authenticated (passed from middleware)
        if user_payload:
            headers["X-User-ID"] = str(user_payload.get("sub", ""))
            headers["X-User-Roles"] = ",".join(user_payload.get("roles", []))

        upstream_response = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            timeout=settings.request_timeout,
        )

        # 3. Log
        elapsed_ms = (time.monotonic() - request.state.start_time) * 1000
        await logger.log(
            request_id=request.state.request_id,
            method=request.method,
            path=f"/{full_path}",
            service=service_name,
            upstream=upstream_url,
            status=upstream_response.status_code,
            latency_ms=elapsed_ms,
        )

        # 4. Return upstream response (strip hop-by-hop response headers)
        excluded_response_headers = {"transfer-encoding", "connection"}
        response_headers = {
            k: v
            for k, v in upstream_response.headers.items()
            if k.lower() not in excluded_response_headers
        }

        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=upstream_response.headers.get("content-type"),
        )

    except httpx.ConnectError as exc:
        return JSONResponse(
            status_code=502,
            content={
                "error": "upstream_unreachable",
                "service": service_name,
                "detail": str(exc),
            },
        )
    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={
                "error": "upstream_timeout",
                "service": service_name,
                "timeout_seconds": settings.request_timeout,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=500,
            content={"error": "gateway_error", "detail": str(exc)},
        )


# ── Dev runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "gateway.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
