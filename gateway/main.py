"""
Smart API Gateway - Phase 1: Core Reverse Proxy
Entry point for the FastAPI gateway server.
"""

import asyncio
import json
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
from gateway.redis_client import redis_client
from gateway.load_balancer import LoadBalancer
from gateway.rate_limiter import RateLimiterManager


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise shared resources on startup; clean up on shutdown."""
    app.state.pool_manager = ConnectionPoolManager()
    await app.state.pool_manager.startup()

    app.state.router = GatewayRouter(settings)
    app.state.logger = GatewayLogger()
    app.state.load_balancer = LoadBalancer(settings)

    # Initialize rate limiter
    if settings.rate_limiter_enabled:
        app.state.rate_limiter = RateLimiterManager(
            algorithm=settings.rate_limiter_algorithm,
            rate=settings.rate_limiter_rate,
            capacity=settings.rate_limiter_capacity,
            window_seconds=settings.rate_limiter_window_seconds,
        )
        print("✅ Rate limiter initialized — protecting against abuse")
    else:
        app.state.rate_limiter = None
        print("⚠️  Rate limiter disabled")

    print("✅ Gateway started — connection pools ready")
    print("✅ Load balancer initialized — metrics tracking enabled")
    yield

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


# ── Middleware: rate limiting ─────────────────────────────────────────────────

@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    """
    Apply rate limiting per IP address.
    Returns 429 Too Many Requests if limit exceeded.
    Adds rate limit headers to all responses for observability.
    """
    rate_limiter: RateLimiterManager = request.app.state.rate_limiter
    client_ip = request.client.host if request.client else "unknown"
    state = {}
    
    # Determine if we should skip rate limiting for this path
    skip_rate_limit = request.url.path in ["/health", "/gateway/routes", "/gateway/metrics", "/gateway/ratelimit"]
    
    # Check rate limit only if enabled and not skipped
    if rate_limiter and settings.rate_limiter_enabled and not skip_rate_limit:
        # Check whitelist
        if client_ip not in settings.rate_limiter_whitelist:
            # Check rate limit
            allowed, state = await rate_limiter.check_limit(client_ip)
            
            if not allowed:
                print(
                    f"🚫 Rate limit exceeded for {client_ip}: "
                    f"{state.get('requests_made', 'N/A')}/{state.get('limit', 'N/A')} "
                    f"in {state.get('window_seconds', 'N/A')}s"
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": f"Too many requests. Limit: {settings.rate_limiter_rate} requests per {settings.rate_limiter_window_seconds} seconds",
                        "retry_after": settings.rate_limiter_window_seconds,
                        "client_ip": client_ip,
                    },
                )
    
    # Get rate limit state for headers (even for skipped endpoints)
    if not state and rate_limiter and settings.rate_limiter_enabled:
        _, state = await rate_limiter.check_limit(client_ip)
    
    # Process the request
    response = await call_next(request)
    
    # Add rate limit headers to all responses for observability
    if rate_limiter and settings.rate_limiter_enabled:
        response.headers["x-ratelimit-limit"] = str(settings.rate_limiter_rate)
        response.headers["x-ratelimit-remaining"] = str(max(0, state.get("tokens_remaining", state.get("requests_made", 0))))
        response.headers["x-ratelimit-reset"] = str(int(time.time()) + settings.rate_limiter_window_seconds)
    
    return response


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


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["Gateway"])
async def health_check():
    return {"status": "ok", "service": "smart-api-gateway", "phase": 3}


@app.get("/gateway/routes", tags=["Gateway"])
async def list_routes(request: Request):
    """Return the current routing table so you can inspect it at runtime."""
    router: GatewayRouter = request.app.state.router
    return {"routes": router.describe()}


@app.get("/gateway/metrics", tags=["Gateway"])
async def get_metrics(request: Request):
    """Return collected metrics and service health scores."""
    load_balancer = request.app.state.load_balancer
    metrics_collector = load_balancer.metrics
    route_table = settings.route_table

    services_health = {}
    for prefix, service_name in route_table.items():
        health = await metrics_collector.get_service_health(service_name)
        services_health[service_name] = health

    return {
        "services": services_health,
        "timestamp": int(time.time()),
    }


@app.get("/gateway/ratelimit", tags=["Gateway"])
async def get_ratelimit_info(request: Request):
    """Return rate limiting configuration and status."""
    if not settings.rate_limiter_enabled:
        return {
            "enabled": False,
            "message": "Rate limiting is disabled",
        }

    client_ip = request.client.host if request.client else "unknown"
    rate_limiter = request.app.state.rate_limiter

    # Check current status for this IP
    _, state = await rate_limiter.check_limit(client_ip)

    return {
        "enabled": True,
        "algorithm": settings.rate_limiter_algorithm,
        "rate": f"{settings.rate_limiter_rate} requests per {settings.rate_limiter_window_seconds} seconds",
        "capacity": settings.rate_limiter_capacity,
        "window_seconds": settings.rate_limiter_window_seconds,
        "whitelist": settings.rate_limiter_whitelist,
        "current_client": {
            "ip": client_ip,
            "status": state,
        },
    }


# ── Catch-all proxy ───────────────────────────────────────────────────────────

@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    tags=["Proxy"],
)
async def proxy(request: Request, full_path: str):
    """
    Core reverse-proxy handler with Redis caching.

    CACHING FLOW
    -----
    Request
      ↓
    Check Redis (GET only)
      ↓
    CACHE HIT? → Return cached response
      ↓
    CACHE MISS → Forward to service
      ↓
    Store response in Redis (TTL: 60s)
      ↓
    Return response

    Cache Key Format: {METHOD}:{PATH}
    Example: GET:/products/1
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

    # 2. Check Redis cache (only for GET requests)
    cache_key = f"{request.method}:{request.url.path}"
    if request.method == "GET":
        try:
            cached_response = await redis_client.get(cache_key)
            if cached_response:
                print(f"✅ CACHE HIT: {cache_key}")
                return JSONResponse(
                    status_code=200,
                    content=json.loads(cached_response),
                )
        except Exception as e:
            print(f"⚠️  Redis cache read error: {e}")
            # Continue to upstream if cache fails

    # 3. Forward the request
    try:
        client: httpx.AsyncClient = pool_manager.get_client(service_name)

        # Re-assemble query string
        target_url = upstream_url
        if request.url.query:
            target_url = f"{upstream_url}?{request.url.query}"

        body = await request.body()

        # Copy headers; strip hop-by-hop headers that must not be forwarded
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

        upstream_response = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            timeout=settings.request_timeout,
        )

        # 4. Cache the response (only for successful GET requests)
        if request.method == "GET" and 200 <= upstream_response.status_code < 300:
            try:
                await redis_client.set(
                    cache_key,
                    upstream_response.text,
                    ex=60,
                )
                print(f"💾 CACHE MISS: {cache_key} → Stored with 60s TTL")
            except Exception as e:
                print(f"⚠️  Redis cache write error: {e}")
                # Continue even if cache write fails

        # 5. Log and record metrics
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

        # Record metrics for load balancing
        load_balancer = request.app.state.load_balancer
        task_type = request.url.path.split("/")[1]  # Extract from path (e.g., "products" from "/products/1")
        await load_balancer.record_request(
            service=service_name,
            task_type=task_type,
            latency_ms=elapsed_ms,
            status_code=upstream_response.status_code,
            complexity="low",  # Can be enhanced to detect from request
            inflight_requests=1,  # Can be enhanced with queue depth
        )
        print(f"📊 Metrics recorded: {service_name} ({task_type}): {elapsed_ms:.0f}ms, status={upstream_response.status_code}")

        # 6. Return upstream response (strip hop-by-hop response headers too)
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
