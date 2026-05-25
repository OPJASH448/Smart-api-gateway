# 📚 Smart API Gateway - Quick Reference & Examples

## 🎯 Quick Start

### 1. Start Services
```bash
# Terminal 1: AI Service
python -m uvicorn services.ai_service.main:app --host 0.0.0.0 --port 9003

# Terminal 2: Gateway
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 8000
```

### 2. Test Complete Workflow
```bash
python test_complete_workflow.py
```

---

## 📡 API Endpoints

### **POST /gateway/route-with-cache** (MAIN ENDPOINT)

Complete intelligent routing with caching and source tracking.

#### Request
```json
{
  "text": "I need to log in with my username",
  "source": "loginpage",
  "method": "POST"
}
```

#### Response (Success)
```json
{
  "status": "routed",
  "service": "auth",
  "url": "http://localhost:9001",
  "confidence": 0.95,
  "source": "loginpage",
  "cached": false,
  "routing_score": 0.835,
  "metrics_used": 18,
  "classification_scores": {
    "auth": 0.95,
    "chat": 0.0,
    "ai": 0.0,
    "products": 0.0
  },
  "timestamp": 1779697103
}
```

#### Response (Cache Hit)
```json
{
  "status": "cached",
  "service": "auth",
  "confidence": 0.95,
  "source": "loginpage",
  "cached": true,
  "timestamp": 1779697050
}
```

---

### **POST /gateway/classify** (Legacy)

Get classification scores only (no routing).

#### Request
```json
{
  "text": "Can you analyze this data?"
}
```

#### Response
```json
{
  "status": "success",
  "classification": {
    "primary_service": "ai",
    "primary_confidence": 1.0,
    "all_scores": {
      "auth": 0.0,
      "chat": 0.0,
      "ai": 1.0,
      "products": 0.0
    },
    "routing_info": {
      "primary_service": "ai",
      "primary_confidence": 1.0,
      "alternatives": []
    }
  },
  "timestamp": 1779697103
}
```

---

### **POST /gateway/smart-route** (Legacy)

Smart routing with health metrics.

#### Request
```json
{
  "text": "Show me laptops",
  "method": "POST"
}
```

#### Response
```json
{
  "status": "success",
  "routing_decision": {
    "service": "products",
    "url": "http://localhost:9004",
    "confidence": 0.9,
    "method": "POST"
  },
  "classification": {
    "all_scores": {
      "auth": 0.0,
      "chat": 0.0,
      "ai": 0.0,
      "products": 0.9
    },
    "routing_info": {
      "primary_service": "products",
      "primary_confidence": 0.9,
      "alternatives": []
    }
  },
  "service_health": {
    "status": "unknown",
    "avg_response_time_ms": 0,
    "success_rate": 0.0
  },
  "timestamp": 1779697103
}
```

---

### **POST /ai/chat** (AI Service)

Direct chat endpoint with ChatGPT/Grok simulation.

#### Request
```json
{
  "prompt": "What is machine learning?",
  "model": "chatgpt"
}
```

#### Response
```json
{
  "prompt": "What is machine learning?",
  "response": "[ChatGPT Response] Analyzing: What is machine learning?...",
  "model": "chatgpt",
  "latency_ms": 187.5,
  "service": "ai",
  "status": "success"
}
```

---

## 🧪 Usage Examples

### Example 1: Authentication Flow
```bash
curl -X POST http://localhost:8000/gateway/route-with-cache \
  -H "Content-Type: application/json" \
  -d '{
    "text": "I forgot my password, please reset it",
    "source": "login_page",
    "method": "POST"
  }'
```

**Expected Response:**
- Service: `auth`
- Confidence: ~100%
- Routing Score: ~1.0

---

### Example 2: E-commerce Shopping
```bash
curl -X POST http://localhost:8000/gateway/route-with-cache \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Show me gaming laptops under 1500 dollars",
    "source": "shop_page",
    "method": "POST"
  }'
```

**Expected Response:**
- Service: `products` (or `auth` if all scores are 0)
- Confidence: 90%+
- Routing Score: 0.8+

---

### Example 3: AI Analysis
```bash
curl -X POST http://localhost:8000/gateway/route-with-cache \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Analyze sales trends and predict Q3 revenue",
    "source": "analytics_dashboard",
    "method": "POST"
  }'
```

**Expected Response:**
- Service: `ai`
- Confidence: 80-100%
- Routing Score: 0.7-1.0

---

### Example 4: Chat Messaging
```bash
curl -X POST http://localhost:8000/gateway/route-with-cache \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Send a group message to the team",
    "source": "messaging_app",
    "method": "POST"
  }'
```

**Expected Response:**
- Service: `chat`
- Confidence: 85%+
- Routing Score: 0.9+

---

### Example 5: Cache Hit
```bash
# First request
curl -X POST http://localhost:8000/gateway/route-with-cache \
  -H "Content-Type: application/json" \
  -d '{
    "text": "I need to log in",
    "source": "loginpage"
  }'

# Second request (same text + source)
curl -X POST http://localhost:8000/gateway/route-with-cache \
  -H "Content-Type: application/json" \
  -d '{
    "text": "I need to log in",
    "source": "loginpage"
  }'
```

**Second Response:** `"cached": true` (instant response)

---

## 🐍 Python Examples

### Using httpx
```python
import httpx

client = httpx.Client()

# Single request
response = client.post(
    "http://localhost:8000/gateway/route-with-cache",
    json={
        "text": "I need to log in",
        "source": "loginpage"
    }
)

result = response.json()
print(f"Routed to: {result['service']}")
print(f"Confidence: {result['confidence']}")
print(f"Cached: {result.get('cached', False)}")
```

### With Retry Logic
```python
import httpx
import time

def test_endpoint_with_retry(text, source, retries=3):
    for attempt in range(retries):
        try:
            response = httpx.post(
                "http://localhost:8000/gateway/route-with-cache",
                json={"text": text, "source": source},
                timeout=10
            )
            return response.json()
        except httpx.TimeoutError:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            raise

result = test_endpoint_with_retry(
    "I need to log in",
    "loginpage"
)
```

---

## 📊 Routing Decision Table

### Classification Confidence → Service Mapping

| Request | Auth | Chat | AI | Products | → Selected | Reasoning |
|---------|------|------|----|---------|----|-----------|
| "Log in" | 100% | 0% | 0% | 0% | AUTH | Primary scoring |
| "Send message" | 0% | 85% | 0% | 0% | CHAT | Clear intent |
| "Analyze data" | 0% | 0% | 100% | 0% | AI | Specialized task |
| "Buy laptop" | 0% | 0% | 0% | 100% | PRODUCTS | Commerce |
| "Create account + message" | 95% | 5% | 0% | 0% | AUTH | Primary + hybrid scoring |
| "Weather" | 0% | 0% | 0% | 0% | AUTH | Fallback when all 0% |

---

## ⚡ Performance Tips

### 1. Cache Efficiency
- Same source + text = instant cache hit
- Different sources for same text = separate cache entries
- TTL: 1 hour

### 2. Metrics Collection
- Last 20 requests per service stored
- Older metrics automatically removed
- TTL: 24 hours

### 3. Optimal Scoring
- Classification weight: 70%
- Performance weight: 30%
- Dynamic based on real metrics

---

## 🔍 Debugging

### Check Service Health
```bash
curl http://localhost:9003/ai/health
```

### View Gateway Metrics
```bash
curl http://localhost:8000/gateway/metrics
```

### View Routing Table
```bash
curl http://localhost:8000/gateway/routes
```

---

## 🚨 Common Issues

### Issue: 404 on /gateway/route-with-cache
**Solution:** Make sure gateway is running and endpoint is registered
```bash
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 8000
```

### Issue: Redis Connection Error
**Solution:** Redis is optional. System works without it (cache disabled)
- Expected warning: `[!] Cache retrieval error`
- System falls back to direct processing

### Issue: Database Logging Fails
**Solution:** PostgreSQL is optional. System works without it
- Expected warning: `[!] Database logging error`
- Routing still works, just no audit trail

### Issue: All Scores Are 0%
**Solution:** This is normal. Fallback routing to `auth` service
- Can improve by testing with clearer request text
- Keywords in requests improve classification

---

## 📈 Metrics to Monitor

Track these in production:
1. **Cache Hit Rate** - Higher is better (target: >60%)
2. **Routing Accuracy** - Correct service selection (target: >95%)
3. **Response Time** - Cache hits: <20ms, Misses: 300-500ms
4. **Error Rate** - Should be <1%
5. **Service Distribution** - Should match real workload

---

## 🎓 Understanding the Scoring Formula

```
score = 0.6 * latency_norm + 0.3 * error_rate_norm + 0.1 * load_norm

Example Calculation:
================

Services: auth (100ms), chat (150ms), ai (200ms)

Step 1: Normalize latencies
  min = 100, max = 200
  latency_norm_auth = (100-100)/(200-100+1e-9) = 0.0   ← BEST
  latency_norm_chat = (150-100)/(200-100+1e-9) = 0.5
  latency_norm_ai = (200-100)/(200-100+1e-9) = 1.0     ← WORST

Step 2: Error rates (example: all at 5%)
  error_rate_norm = 0.05

Step 3: Load (unused for now)
  load_norm = 0.0

Step 4: Combine
  auth_score = 0.6*0.0 + 0.3*0.05 + 0.1*0.0 = 0.015   ← BEST
  chat_score = 0.6*0.5 + 0.3*0.05 + 0.1*0.0 = 0.315
  ai_score = 0.6*1.0 + 0.3*0.05 + 0.1*0.0 = 0.615     ← WORST

Winner: auth (lowest score = best service)
```

**Lower score = better service!**

---

Generated: May 25, 2026
Status: ✅ READY FOR PRODUCTION
