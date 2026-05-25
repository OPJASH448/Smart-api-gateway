# 🎨 Smart API Gateway - Live Dashboard Guide

## 🚀 Quick Start

### **1. Open the Dashboard**
Simply open this file in your browser:
```
file:///c:/Users/kanip/OneDrive/Desktop/smart-api-gateway/dashboard.html
```

Or use a local HTTP server:
```bash
python -m http.server 8888
# Then open: http://localhost:8888/dashboard.html
```

---

## 📊 Dashboard Features

### **Real-Time Metrics**
- ✅ **Total Requests** - Cumulative request count
- ✅ **Requests/Second (RPS)** - Live traffic rate
- ✅ **Cache Hit Rate** - Redis cache efficiency percentage
- ✅ **Rate Limited** - Blocked requests count

### **Live Charts**
- 📈 **Traffic Graph** - Request volume over last 5 minutes
- 🎯 **Service Distribution** - Pie chart showing routing percentages

### **Service Health Status**
- 🔐 AUTH Service
- 💬 CHAT Service
- 🤖 AI Service
- 🛍️ PRODUCTS Service

Each shows:
- Health status (Healthy ✓ or Down ✗)
- Request count routed to that service
- Green/Red status indicator

### **Recent Requests Table**
Last 10 requests showing:
- Source (loginpage, messaging_page, analytics_page, etc.)
- Service routed to
- Confidence score (%)
- Cache hit indicator
- Timestamp

---

## 🔌 Backend Endpoints

All endpoints return real-time metrics:

### **Main Dashboard Endpoint**
```
GET /api/dashboard
```
Returns complete dashboard data:
```json
{
  "summary": {
    "total_requests": 42,
    "cache_hits": 18,
    "cache_hit_rate": 42.86,
    "rate_limited": 0,
    "rps": 2.5
  },
  "services": {
    "auth": 15,
    "chat": 12,
    "ai": 10,
    "products": 5
  },
  "health": {
    "auth": "healthy",
    "chat": "healthy",
    "ai": "healthy",
    "products": "healthy"
  },
  "recent_requests": [
    {
      "source": "loginpage",
      "service": "auth",
      "confidence": 0.95,
      "cached": false,
      "timestamp": "2026-05-25T08:52:09"
    }
  ]
}
```

### **Individual Metrics Endpoints**
```
GET /api/metrics                 # Summary metrics
GET /api/metrics/health          # Service health
GET /api/metrics/recent          # Recent requests
GET /api/metrics/traffic         # Traffic over time
```

---

## 🎬 How to Generate Test Traffic

Run the included traffic generator:

```bash
python generate_traffic.py
```

This will send simulated requests to:
- `loginpage` → Routes to AUTH
- `messaging_page` → Routes to CHAT
- `analytics_page` → Routes to AI
- `shop_page` → Routes to PRODUCTS
- `dashboard` → Mixed routing

---

## 📱 Dashboard Auto-Refresh

The dashboard automatically:
- ✅ Fetches metrics every **2 seconds**
- ✅ Updates all charts and cards in real-time
- ✅ Shows live traffic trends
- ✅ Updates service health status

---

## 🎨 UI Features

### **Responsive Design**
- Desktop: Full grid layout
- Tablet: Adaptive columns
- Mobile: Single column (vertical stacking)

### **Beautiful Styling**
- Gradient background (purple → blue)
- Glassmorphism cards (frosted glass effect)
- Smooth animations and transitions
- Professional color scheme

### **Interactive Elements**
- Hover effects on metric cards
- Clickable charts (Chart.js tooltips)
- Real-time animated counters
- Status indicators (green/red pulses)

---

## 📈 Chart Types

### **Traffic Chart**
- Line chart showing requests over 5 minutes
- 10-second intervals
- Smooth curves with hover tooltips
- Filled area under line

### **Routing Distribution**
- Doughnut chart (pie style)
- Shows percentage of traffic per service
- Color-coded by service
- Legend at bottom

---

## 🔄 Data Flow

```
User Request
    ↓
Gateway receives (/gateway/route-with-cache)
    ↓
Global metrics updated:
  - total_requests++
  - service_counts[service]++
  - recent_requests.append(request_data)
  - request_timestamps.append(now)
    ↓
Dashboard polls every 2 seconds (/api/dashboard)
    ↓
Frontend receives JSON with:
  - summary stats
  - service health
  - recent requests
    ↓
Charts updated in real-time
```

---

## 🛠️ Customization

### **Change Refresh Interval**
In `dashboard.html`, find:
```javascript
setInterval(fetchDashboardData, 2000);  // 2 seconds
```

Change `2000` to desired milliseconds:
- `1000` = 1 second (very frequent)
- `5000` = 5 seconds (less frequent)

### **Change Colors**
Edit CSS variables in `<style>` section:
```css
--primary-color: #667eea;      /* Purple */
--secondary-color: #764ba2;    /* Dark purple */
--success-color: #10b981;      /* Green */
--error-color: #ef4444;        /* Red */
```

### **Add More Metrics**
1. Add tracking in `gateway/main.py`:
   ```python
   with metrics_lock:
       your_metric += 1
   ```

2. Add endpoint to expose it:
   ```python
   @app.get("/api/your-metric")
   async def get_your_metric():
       return {"value": your_metric}
   ```

3. Display in dashboard:
   ```html
   <div class="metric-card">
       <div class="metric-label">YOUR METRIC</div>
       <div class="metric-value" id="yourMetric">0</div>
   </div>
   ```

   ```javascript
   document.getElementById('yourMetric').textContent = data.your_metric;
   ```

---

## ✨ Production Tips

### **Enable CORS** (if accessing from different domain)
In `gateway/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### **Add Authentication**
```python
@app.get("/api/dashboard")
async def dashboard_data(Authorization: str = Header(...)):
    # Verify token
    # Return metrics
```

### **Performance Optimization**
- Cache metrics computation for 1-2 seconds
- Use Redis for distributed metrics
- Implement metric aggregation

### **Alerting**
Add JavaScript alerts for thresholds:
```javascript
if (data.summary.rate_limited > 50) {
    alert('⚠️ High rate limiting detected!');
}
```

---

## 🎯 What Makes This Dashboard Professional

✅ **Real-time Updates** - Live metrics every 2 seconds
✅ **Beautiful UI** - Glassmorphism, gradients, smooth animations
✅ **Responsive Design** - Works on all screen sizes
✅ **Interactive Charts** - Chart.js with hover tooltips
✅ **Service Health** - Visual status indicators
✅ **Recent Activity** - Live request tracking
✅ **No Dependencies** - Pure HTML/CSS/JS + Chart.js
✅ **Fast Load** - Single HTML file, instant loading
✅ **Production Ready** - Clean code, error handling
✅ **Easy to Customize** - Well-commented code

---

## 📸 Screenshot Guide

When running with traffic:

```
┌─────────────────────────────────────────────────────┐
│ Smart API Gateway Dashboard                          │
│ Real-time monitoring & analytics                     │
└─────────────────────────────────────────────────────┘

┌─────────┐ ┌──────┐ ┌──────────┐ ┌──────────┐
│ Requests│ │ RPS  │ │Cache Hit │ │ Limited  │
│   420   │ │ 5.2  │ │   78%    │ │    3     │
└─────────┘ └──────┘ └──────────┘ └──────────┘

[Traffic Graph] [Service Pie Chart]

🔐 AUTH    ✅  💬 CHAT    ✅
🤖 AI      ✅  🛍️ PRODUCTS ✅

Recent Requests:
loginpage      → AUTH      95%  ✓ Cached
messaging_page → CHAT      85%
analytics_page → AI        60%
```

---

## 🚀 Next Steps

1. **Open Dashboard**: Open `dashboard.html` in browser
2. **Generate Traffic**: Run `python generate_traffic.py`
3. **Watch Live Metrics**: See real-time updates
4. **Customize**: Modify colors, metrics, charts
5. **Deploy**: Host on web server with CORS enabled

---

**Status: ✅ Production Ready!**
Your Smart API Gateway Dashboard is fully functional and ready to impress! 🎉
