"""
Smart API Gateway - Phase 3: Retry + Circuit Breaker + Logging + Monitoring
Entry point for the FastAPI gateway server with advanced resilience patterns.
"""

import asyncio
import hashlib
import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from gateway.config import settings
from gateway.router import GatewayRouter
from gateway.connection_pool import ConnectionPoolManager
from gateway.logger import GatewayLogger
from gateway.redis_client import redis_client
from gateway.load_balancer import LoadBalancer
from gateway.rate_limiter import RateLimiterManager
from gateway.retry import retry_with_backoff
from gateway.circuit_breaker import CircuitBreaker
from gateway.database import init_db, get_db
from gateway.models import RequestLog
from gateway.ai_classifier import ServiceClassifier, RoutingScorer
from gateway.request_cache import RequestCache
from collections import deque
from threading import Lock


# ── Global Metrics Storage ────────────────────────────────────────────────────
metrics_lock = Lock()
total_requests = 0
cache_hits = 0
cache_misses = 0
rate_limited_requests = 0
recent_requests = deque(maxlen=50)  # Keep last 50 requests
service_counts = {"auth": 0, "chat": 0, "ai": 0, "products": 0}
service_health = {"auth": "healthy", "chat": "healthy", "ai": "healthy", "products": "healthy"}
request_timestamps = deque(maxlen=300)  # Keep last 300 timestamps (5 minutes at 1 per second)
classification_scores_history = deque(maxlen=100)  # Track recent classifications


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise shared resources on startup; clean up on shutdown."""
    # Initialize database
    try:
        init_db()
        print("✅ Database initialized — PostgreSQL connected")
    except Exception as e:
        print(f"⚠️  Database initialization failed: {e}")
    
    app.state.pool_manager = ConnectionPoolManager()
    await app.state.pool_manager.startup()

    app.state.router = GatewayRouter(settings)
    app.state.logger = GatewayLogger()
    app.state.load_balancer = LoadBalancer(settings)

    # Initialize AI Classifier for intelligent routing
    print("🤖 Initializing AI Classifier (powered by Gemini 2.5 Flash)...")
    app.state.ai_classifier = ServiceClassifier
    app.state.routing_scorer = RoutingScorer
    print("✅ AI Classifier ready — smart routing enabled")

    # Initialize circuit breakers for each service
    app.state.circuit_breakers = {
        "auth": CircuitBreaker("auth_service", failure_threshold=5, recovery_timeout=30.0),
        "chat": CircuitBreaker("chat_service", failure_threshold=5, recovery_timeout=30.0),
        "ai": CircuitBreaker("ai_service", failure_threshold=5, recovery_timeout=30.0),
    }
    print("✅ Circuit breakers initialized — resilience patterns ready")

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
    print("🚀 Phase 3: Advanced Resilience & Monitoring Ready!")
    print("🤖 AI Classification for Intelligent Routing: ENABLED")
    yield

    await app.state.pool_manager.shutdown()
    print("🛑 Gateway shut down — pools closed")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Smart API Gateway",
    description="Phase 3 — Advanced resilience with retry, circuit breaker, logging & monitoring",
    version="3.0.0",
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
    skip_rate_limit = request.url.path in [
        "/health",
        "/gateway/routes",
        "/gateway/metrics",
        "/gateway/metrics/history",
        "/gateway/ratelimit",
    ]
    
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
    request_id = str(uuid.uuid4())
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


@app.post("/gateway/classify", tags=["Gateway AI Classifier"])
async def classify_request(request: Request):
    """
    AI-powered intelligent request classifier.
    
    Analyzes the request content and determines which service should handle it.
    Uses Gemini API to understand request intent and score all services.
    
    Request body:
    {
        "text": "Your request or query text here"
    }
    
    Response example:
    {
        "primary_service": "ai",
        "primary_confidence": 0.92,
        "classification_scores": {
            "ai": 0.92,
            "chat": 0.15,
            "auth": 0.08,
            "products": 0.05
        },
        "routing_info": {...}
    }
    """
    try:
        body = await request.json()
        request_text = body.get("text", "")
        
        if not request_text:
            return JSONResponse(
                status_code=400,
                content={"error": "missing_text", "message": "Request body must contain 'text' field"}
            )
        
        # Classify the request
        best_service, scores = ServiceClassifier.classify_request(request_text)
        routing_info = RoutingScorer.get_routing_info(scores)
        
        return {
            "status": "success",
            "request_text": request_text[:100] + "..." if len(request_text) > 100 else request_text,
            "primary_service": best_service,
            "primary_confidence": round(scores[best_service], 3),
            "classification_scores": {svc: round(score, 3) for svc, score in scores.items()},
            "routing_info": routing_info,
            "timestamp": int(time.time()),
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "classification_error", "message": str(e)}
        )


@app.post("/gateway/smart-route", tags=["Gateway AI Classifier"])
async def smart_route(request: Request):
    """
    AI-powered smart routing endpoint.
    
    Analyzes request and intelligently routes to the optimal service.
    Combines classification scores with service health metrics.
    
    Request body:
    {
        "text": "Your request content",
        "method": "POST",
        "body": {...}  // Optional request body
    }
    
    Response includes:
    - Recommended service
    - Confidence score
    - Routing decision info
    - Service health status
    """
    try:
        body = await request.json()
        request_text = body.get("text", "")
        method = body.get("method", "POST")
        
        if not request_text:
            return JSONResponse(
                status_code=400,
                content={"error": "missing_text", "message": "Request body must contain 'text' field"}
            )
        
        # Step 1: Classify the request
        best_service, scores = ServiceClassifier.classify_request(request_text)
        
        # Step 2: Get routing recommendation
        try:
            service_name, service_url = RoutingScorer.get_optimal_route(scores, settings.service_urls)
        except ValueError as e:
            return JSONResponse(status_code=404, content={"error": "no_available_services", "message": str(e)})
        
        # Step 3: Get service health info (with timeout)
        service_health = {"status": "unknown", "avg_response_time_ms": 0, "success_rate": 0}
        try:
            load_balancer = request.app.state.load_balancer
            health_data = await asyncio.wait_for(
                load_balancer.metrics.get_service_health(service_name),
                timeout=2.0
            )
            service_health = {
                "status": "healthy" if health_data.get("is_healthy") else "degraded",
                "avg_response_time_ms": health_data.get("avg_latency", 0),
                "success_rate": 1.0 - health_data.get("error_rate", 1.0),
                "is_fresh": health_data.get("is_fresh", False),
            }
        except (asyncio.TimeoutError, Exception):
            # If health check fails, still allow routing with unknown status
            pass
        
        # Step 4: Prepare routing response
        routing_info = RoutingScorer.get_routing_info(scores)
        
        return {
            "status": "success",
            "routing_decision": {
                "service": service_name,
                "url": service_url,
                "confidence": round(scores[service_name], 3),
                "method": method,
            },
            "classification": {
                "all_scores": {svc: round(score, 3) for svc, score in scores.items()},
                "routing_info": routing_info,
            },
            "service_health": service_health,
            "timestamp": int(time.time()),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": "routing_error", "message": str(e)}
        )


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


@app.get("/gateway/metrics/history", tags=["Gateway"])
async def get_metrics_history(
    request: Request,
    service: str = Query(None, description="Filter by service name"),
):
    """Return last 20 metrics per service from Redis (no TTL)."""
    load_balancer = request.app.state.load_balancer
    metrics_collector = load_balancer.metrics

    if service:
        return {
            "service": service,
            "metrics": await metrics_collector.get_metrics(service) or [],
        }

    services = list(settings.service_urls.keys())
    return {
        "services": await metrics_collector.get_all_metrics(services),
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


# ── Dashboard: Logs ───────────────────────────────────────────────────────────

@app.get("/dashboard/logs", tags=["Dashboard"])
async def get_logs(
    service: str = Query(None, description="Filter by service name"),
    status_code: int = Query(None, description="Filter by status code"),
    minutes: int = Query(60, description="Last N minutes"),
    db: Session = Depends(get_db),
):
    """
    Get request logs from database.
    
    Query parameters:
    - service: Filter by service (auth, chat, ai)
    - status_code: Filter by status code (200, 429, 500, etc)
    - minutes: Last N minutes (default 60)
    """
    try:
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        query = db.query(RequestLog).filter(RequestLog.timestamp >= cutoff_time)
        
        if service:
            query = query.filter(RequestLog.service == service)
        
        if status_code:
            query = query.filter(RequestLog.status_code == status_code)
        
        logs = query.order_by(RequestLog.timestamp.desc()).limit(1000).all()
        
        return {
            "count": len(logs),
            "time_range": {
                "start": cutoff_time.isoformat(),
                "end": datetime.utcnow().isoformat(),
            },
            "filters": {
                "service": service,
                "status_code": status_code,
                "minutes": minutes,
            },
            "logs": [log.to_dict() for log in logs],
        }
    except Exception as e:
        return {
            "error": "database_error",
            "message": str(e),
            "count": 0,
            "logs": [],
        }


@app.get("/dashboard/stats", tags=["Dashboard"])
async def get_stats(
    minutes: int = Query(60, description="Last N minutes"),
    db: Session = Depends(get_db),
):
    """Get statistics over time period."""
    try:
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        logs = db.query(RequestLog).filter(RequestLog.timestamp >= cutoff_time).all()
        
        stats = {
            "period_minutes": minutes,
            "total_requests": len(logs),
            "avg_response_time_ms": sum(l.response_time_ms for l in logs) / len(logs) if logs else 0,
            "errors": len([l for l in logs if l.status_code >= 400]),
            "error_rate": (len([l for l in logs if l.status_code >= 400]) / len(logs) * 100) if logs else 0,
            "services": {},
            "status_codes": {},
            "retry_stats": {
                "total_retries": sum(l.retry_count for l in logs),
                "avg_retries_per_request": sum(l.retry_count for l in logs) / len(logs) if logs else 0,
            },
            "circuit_breaker_states": {},
        }
        
        for log in logs:
            # By service
            if log.service not in stats["services"]:
                stats["services"][log.service] = {
                    "count": 0,
                    "avg_response_time_ms": 0,
                    "error_count": 0,
                }
            stats["services"][log.service]["count"] += 1
            stats["services"][log.service]["error_count"] += 1 if log.status_code >= 400 else 0
            
            # By status code
            if log.status_code not in stats["status_codes"]:
                stats["status_codes"][log.status_code] = 0
            stats["status_codes"][log.status_code] += 1
            
            # By circuit breaker state
            if log.circuit_breaker_state not in stats["circuit_breaker_states"]:
                stats["circuit_breaker_states"][log.circuit_breaker_state] = 0
            stats["circuit_breaker_states"][log.circuit_breaker_state] += 1
        
        # Calculate avg response time per service
        for log in logs:
            if log.service in stats["services"]:
                total_time = sum(l.response_time_ms for l in logs if l.service == log.service)
                service_count = stats["services"][log.service]["count"]
                stats["services"][log.service]["avg_response_time_ms"] = total_time / service_count if service_count > 0 else 0
        
        return stats
    except Exception as e:
        return {
            "error": "database_error",
            "message": str(e),
        }


@app.get("/dashboard/health", tags=["Dashboard"])
async def check_system_health(request: Request):
    """System health + overview."""
    circuit_breakers = request.app.state.circuit_breakers
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "gateway": "healthy",
            "database": "connected",
            "redis": "connected",
        },
        "circuit_breakers": {
            name: {
                "state": cb.get_state(),
                "failure_count": cb.failure_count,
                "threshold": cb.failure_threshold,
            }
            for name, cb in circuit_breakers.items()
        },
    }


@app.post("/gateway/route-with-cache", tags=["Gateway Intelligent Routing"])
async def route_with_cache(request: Request):
    """
    Complete workflow: Cache Check → Classification → Optimal Routing → Logging
    """
    global total_requests, cache_hits, cache_misses, rate_limited_requests
    
    try:
        body = await request.json()
        request_text = body.get("text", "")
        source = body.get("source", "unknown")
        method = body.get("method", "POST")
        
        # Track metrics
        with metrics_lock:
            total_requests += 1
            request_timestamps.append(time.time())
        
        if not request_text:
            return JSONResponse(
                status_code=400,
                content={"error": "missing_text", "message": "Request must have 'text' field"}
            )
        
        # Step 1: Create request hash for caching
        request_hash = hashlib.md5(
            f"{request_text}:{source}".encode()
        ).hexdigest()
        
        # Step 2: Check Redis cache
        cached_result = await RequestCache.get_cached_classification(request_hash)
        if cached_result:
            with metrics_lock:
                cache_hits += 1
                service_counts[cached_result["service"]] += 1
                recent_requests.append({
                    "source": source,
                    "service": cached_result["service"],
                    "confidence": cached_result["confidence"],
                    "cached": True,
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            return {
                "status": "cached",
                "service": cached_result["service"],
                "confidence": cached_result["confidence"],
                "source": cached_result["source"],
                "cached": True,
                "timestamp": cached_result["timestamp"]
            }
        
        with metrics_lock:
            cache_misses += 1
        
        # Step 3: AI Classification
        best_service, scores = ServiceClassifier.classify_request(request_text)
        
        # Track classification scores
        with metrics_lock:
            classification_scores_history.append({
                "service": best_service,
                "scores": scores,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Step 4: Get optimal route based on metrics
        try:
            if max(scores.values()) == 0:
                service_name = "auth"
                routing_score = 0.5
                metrics_used = 0
            else:
                (service_name, combined_score) = await RequestCache.get_best_service(
                    list(scores.keys()),
                    scores
                )
                routing_score = combined_score
                metrics = await RequestCache.get_last_metrics(service_name)
                metrics_used = len(metrics)
        except Exception as e:
            print(f"[!] Routing error: {e}")
            service_name = best_service
            routing_score = scores.get(best_service, 0)
            metrics_used = 0
        
        service_url = settings.service_urls.get(service_name, f"http://localhost:900{list(settings.service_urls.keys()).index(service_name) + 1}")
        confidence = scores.get(service_name, 0)
        
        # Update service counts
        with metrics_lock:
            service_counts[service_name] += 1
            recent_requests.append({
                "source": source,
                "service": service_name,
                "confidence": confidence,
                "cached": False,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Step 5: Cache the classification
        await RequestCache.cache_classification(request_hash, service_name, confidence, source)
        
        # Step 6: Record metrics
        await RequestCache.record_service_metric(service_name, 0, 200, source)
        
        # Step 7: Log to database (if available)
        try:
            db = next(get_db())
            log_entry = RequestLog(
                request_id=str(uuid.uuid4()),
                source=source,
                service=service_name,
                status_code=200,
                response_time_ms=0,
                timestamp=datetime.utcnow(),
                notes=f"Classification: {confidence:.2f}, Routing: {routing_score:.2f}"
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            print(f"[!] Database logging error: {e}")
        
        return {
            "status": "routed",
            "service": service_name,
            "url": service_url,
            "confidence": round(confidence, 3),
            "source": source,
            "cached": False,
            "routing_score": round(routing_score, 3),
            "metrics_used": metrics_used,
            "classification_scores": {s: round(scores[s], 3) for s in scores},
            "timestamp": int(time.time())
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": "routing_error", "message": str(e)}
        )


# ── Comprehensive Metrics & Dashboard Endpoints ────────────────────────────────

@app.get("/api/metrics", tags=["Dashboard Metrics"])
async def get_metrics():
    """Get comprehensive gateway metrics for dashboard"""
    with metrics_lock:
        total = total_requests if total_requests > 0 else 1
        cache_hit_rate = (cache_hits / total * 100) if total > 0 else 0
        
        # Calculate requests per second (last 60 seconds)
        now = time.time()
        recent_60s = [ts for ts in request_timestamps if now - ts < 60]
        rps = len(recent_60s) / 60 if len(recent_60s) > 0 else 0
        
        return {
            "total_requests": total_requests,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "cache_hit_rate": round(cache_hit_rate, 2),
            "rate_limited": rate_limited_requests,
            "requests_per_second": round(rps, 2),
            "services": service_counts,
            "timestamp": datetime.utcnow().isoformat()
        }


@app.get("/api/metrics/health", tags=["Dashboard Metrics"])
async def get_health():
    """Get service health status"""
    health_data = {}
    for service, port in [("auth", 9001), ("chat", 9002), ("ai", 9003), ("products", 9004)]:
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                response = await client.get(f"http://localhost:{port}/health")
                health_data[service] = "healthy" if response.status_code == 200 else "down"
        except:
            health_data[service] = "down"
    
    with metrics_lock:
        service_health.update(health_data)
    
    return {"services": health_data, "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/metrics/recent", tags=["Dashboard Metrics"])
async def get_recent_requests():
    """Get recent routed requests"""
    with metrics_lock:
        return {
            "requests": list(recent_requests),
            "count": len(recent_requests),
            "timestamp": datetime.utcnow().isoformat()
        }


@app.get("/api/metrics/traffic", tags=["Dashboard Metrics"])
async def get_traffic():
    """Get traffic over time (last 5 minutes, 1 second buckets)"""
    now = time.time()
    buckets = {}
    
    with metrics_lock:
        for ts in request_timestamps:
            bucket = int(ts) - (int(ts) % 10)  # Group by 10-second intervals
            if bucket not in buckets:
                buckets[bucket] = 0
            buckets[bucket] += 1
    
    # Sort and prepare for chart
    sorted_buckets = sorted(buckets.items())
    return {
        "traffic": [{"time": int(k), "requests": v} for k, v in sorted_buckets[-30:]],  # Last 5 minutes
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/dashboard", tags=["Dashboard"])
async def dashboard_data():
    """Complete dashboard data endpoint"""
    with metrics_lock:
        total = total_requests if total_requests > 0 else 1
        cache_hit_rate = (cache_hits / total * 100) if total > 0 else 0
        
        # Calculate requests per second
        now = time.time()
        recent_60s = [ts for ts in request_timestamps if now - ts < 60]
        rps = len(recent_60s) / 60 if len(recent_60s) > 0 else 0
        
        return {
            "summary": {
                "total_requests": total_requests,
                "cache_hits": cache_hits,
                "cache_hit_rate": round(cache_hit_rate, 2),
                "rate_limited": rate_limited_requests,
                "rps": round(rps, 2)
            },
            "services": service_counts,
            "health": service_health,
            "recent_requests": list(recent_requests),
            "timestamp": datetime.utcnow().isoformat()
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

    # 3. Forward the request with retry + circuit breaker
    try:
        client: httpx.AsyncClient = pool_manager.get_client(service_name)
        
        # Get circuit breaker for this service
        circuit_breaker = request.app.state.circuit_breakers.get(
            service_name.split("_")[0],  # Extract service type from name
            request.app.state.circuit_breakers.get("chat")  # Default fallback
        )

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

        # Retry + Circuit Breaker wrapper
        retry_count = 0
        upstream_response = None
        error_message = None
        
        async def make_request():
            nonlocal retry_count
            return await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                timeout=settings.request_timeout,
            )
        
        try:
            upstream_response = await retry_with_backoff(
                lambda: circuit_breaker.call(make_request),
                max_retries=3,
                initial_delay=1.0,
                backoff_factor=2.0
            )
            retry_count = 0
        except Exception as e:
            # Count retries from error
            error_message = str(e)
            print(f"❌ Request failed after retries: {error_message}")
            
            if "Circuit OPEN" in error_message:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "service_unavailable",
                        "message": f"Service {service_name} is temporarily unavailable (circuit open)",
                        "retry_after": 30,
                    },
                )
            
            return JSONResponse(
                status_code=502,
                content={
                    "error": "upstream_unreachable",
                    "service": service_name,
                    "detail": error_message,
                },
            )

        # 4. UPDATE GLOBAL DASHBOARD METRICS
        global total_requests, cache_misses
        with metrics_lock:
            total_requests += 1
            request_timestamps.append(time.time())
            
            # Extract service name from full service_name (e.g., "auth_service" → "auth")
            service_key = service_name.split("_")[0] if "_" in service_name else service_name
            if service_key in service_counts:
                service_counts[service_key] += 1
            
            # Track recent request
            recent_requests.append({
                "source": request.client.host if request.client else "unknown",
                "service": service_key,
                "confidence": 1.0,
                "cached": False,
                "timestamp": datetime.now().isoformat()
            })

        # 5. Cache the response (only for successful GET requests)
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

        # 6. Log and record metrics
        elapsed_ms = (time.monotonic() - request.state.start_time) * 1000
        client_ip = request.client.host if request.client else "unknown"
        
        await logger.log(
            request_id=request.state.request_id,
            method=request.method,
            path=f"/{full_path}",
            service=service_name,
            upstream=upstream_url,
            status=upstream_response.status_code,
            latency_ms=elapsed_ms,
            client_ip=client_ip,
            error=error_message,
            retry_count=retry_count,
            circuit_state=circuit_breaker.get_state(),
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

        # 7. Return upstream response (strip hop-by-hop response headers too)
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
