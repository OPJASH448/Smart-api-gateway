# Smart Load Balancing System

## Overview

The gateway now includes an intelligent load balancing system that:
1. **Collects metrics** on every request (latency, errors, freshness)
2. **Stores the last 20 metrics** per service in Redis (no TTL — persistent)
3. **Filters services** by health and freshness
4. **Scores remaining services** with a weighted formula
5. **Routes to the best service** based on the lowest score

## Architecture

### Components

```
request
  ↓
proxy() handler
  ↓
  ├─ Route resolution
  ├─ Redis cache check (GET only)
  ├─ Forward to upstream
  ├─ COLLECT METRICS ← NEW
  │  └─ latency, status, complexity, task_type
  │     stored in Redis: metrics:service:{name}
  ├─ Cache response
  └─ Return response
```

### Files

- **gateway/metrics.py** - `MetricsCollector`: Collects and stores metrics in Redis
- **gateway/load_balancer.py** - `LoadBalancer` + `ServiceScorer`: Filters and scores services
- **gateway/main.py** - Updated proxy handler to record metrics
- **gateway/config.py** - Route table with service URLs

## Metrics Stored

For each request, we store:

```json
{
  "timestamp": 1710000000,
  "service": "products",
  "task_type": "list",
  "latency_ms": 120.5,
  "status": 200,
  "success": true,
  "complexity": "low",
  "inflight_requests": 1
}
```

**Stored in Redis at**: `metrics:service:{service_name}`
**Storage**: Last 20 metrics (rolling window)
**TTL**: None (persistent — manually managed)

## Health Calculation

From the last 20 metrics, we compute:

```python
health = {
    "avg_latency": float,        # Average latency across last 20 requests
    "error_rate": float,         # (errors / total requests)
    "is_healthy": bool,          # error_rate < 50%
    "is_fresh": bool,            # last metric < 60 seconds old
    "last_seen": unix_timestamp,
    "age_seconds": int,
}
```

## Filtering Algorithm

Step 1: Get all services from route table
Step 2: Remove services that:
  - Have error_rate ≥ 50% (unhealthy)
  - Have no metrics (never seen)
  - Have metrics older than 60 seconds (stale)
  - Don't support the requested task_type (for future use)

Result: **Candidate services** that are healthy and fresh

## Scoring Algorithm

For each candidate service, compute:

```
score = 0.6 * latency_norm + 0.3 * error_rate_norm + 0.1 * load_norm

Where:
  latency_norm = (latency - min_latency) / (max_latency - min_latency + 1e-9)
  error_rate_norm = error_rate  # Already 0..1
  load_norm = 0.0  # TODO: Track queue depth
```

**Lower score = better service**

### Weighting Rationale

- **60% Latency**: Fast responses matter most
- **30% Error Rate**: Reliability is critical
- **10% Load**: Future: prioritize less-busy services

## Usage

### 1. Automatic Metrics Collection

Every request automatically records metrics:

```python
await load_balancer.record_request(
    service="products",
    task_type="list",
    latency_ms=120.5,
    status_code=200,
    complexity="low",
    inflight_requests=1,
)
```

### 2. View Service Health

```bash
curl http://localhost:8000/gateway/metrics
```

Response:

```json
{
  "services": {
    "products": {
      "avg_latency": 125.3,
      "error_rate": 0.05,
      "is_healthy": true,
      "is_fresh": true,
      "last_seen": 1710000123,
      "age_seconds": 5
    },
    "chat": {
      "avg_latency": 450.2,
      "error_rate": 0.12,
      "is_healthy": true,
      "is_fresh": false,
      "last_seen": 1709999900,
      "age_seconds": 300
    }
  },
  "timestamp": 1710000200
}
```

### 3. Programmatic Service Selection

```python
load_balancer = request.app.state.load_balancer
best_service = await load_balancer.get_best_service(
    task_type="summarization",
    complexity="high"
)
# Returns: "ai" (or None if no healthy candidates)
```

## Example Flow

### Request 1: First time

```
GET /products/1
  ↓
No metrics yet for "products"
  ↓
Service marked: UNHEALTHY (no history)
  ↓
No candidates → use fallback (default route)
  ↓
Response: 200, latency: 120ms
  ↓
Metrics recorded:
  {timestamp: 1710000000, service: "products", latency_ms: 120, status: 200, ...}
```

### Request 2: After metrics

```
GET /products/1
  ↓
Found 20 metrics for "products"
  ↓
avg_latency: 120, error_rate: 0%, is_fresh: ✓
  ↓
CANDIDATE: products
  ↓
Score: 0.6 * (120/5000) = 0.0144
  ↓
Selected: products
  ↓
Response: 200, latency: 118ms
  ↓
Metrics appended (now 21 metrics, keep last 20)
```

## Future Enhancements

### Phase 2: Complexity Matching

```python
score += 0.08 * complexity_gap_norm

Where:
  complexity_gap_norm = abs(request_complexity - service_complexity) / max
```

If request is "high complexity" but service only handles "low", penalize it.

### Phase 3: Cost Model

```python
score += 0.05 * cost_norm

Track API costs per service and prefer cheaper options.
```

### Phase 4: Advanced Queue Tracking

```python
# Track inflight_requests per service
load_norm = inflight_requests / max_inflight

More busy services get lower priority.
```

### Phase 5: ML-Based Routing

Use historical metrics to predict best service for specific patterns.

## Debugging

### Print Logs

Every request prints:
```
📊 Load Balancing: task_type=products, complexity=low
  ✅ products - CANDIDATE
    Score[products]: 0.0144
🎯 Selected: products (score: 0.0144)
📊 Metrics recorded: products (products): 120ms, status=200
```

### Redis Keys

```bash
# View all metrics
redis-cli KEYS "metrics:service:*"

# View specific service
redis-cli GET "metrics:service:products"
```

Output:
```json
[
  {"timestamp": 1710000000, "service": "products", "latency_ms": 120, ...},
  {"timestamp": 1710000010, "service": "products", "latency_ms": 118, ...},
  ...
]
```

## Testing

### Manual Test

1. Start product service:
   ```bash
   uvicorn services.product_service.main:app --port 9004
   ```

2. Start gateway:
   ```bash
   uvicorn gateway.main:app --reload
   ```

3. Make requests:
   ```bash
   curl http://localhost:8000/products/1
   curl http://localhost:8000/products/2
   curl http://localhost:8000/products/1
   ```

4. Check metrics:
   ```bash
   curl http://localhost:8000/gateway/metrics | python -m json.tool
   ```

## Current Status

✅ Metrics collection
✅ Health calculation
✅ Filtering (healthy + fresh)
✅ Scoring (latency + error + load weighted)
✅ Service selection

⏳ TODO:
- [ ] Complexity matching
- [ ] Queue depth tracking
- [ ] Cost model
- [ ] Multi-service routing decisions
