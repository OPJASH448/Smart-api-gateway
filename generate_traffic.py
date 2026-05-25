#!/usr/bin/env python3
"""Generate test traffic for dashboard demo"""
import httpx
import time

requests = [
    {"text": "I need to log in", "source": "loginpage"},
    {"text": "Send me a message", "source": "messaging_page"},
    {"text": "Analyze this data", "source": "analytics_page"},
    {"text": "Show me products", "source": "shop_page"},
    {"text": "What's the weather", "source": "dashboard"},
]

print("🚀 Generating test traffic for dashboard...")

try:
    for i in range(15):
        for req in requests:
            try:
                response = httpx.post(
                    "http://localhost:8000/gateway/route-with-cache",
                    json=req,
                    timeout=5
                )
                print(f"✓ {req['source']:20} → {response.status_code}")
            except Exception as e:
                print(f"✗ {req['source']:20} → Error: {str(e)[:30]}")
        time.sleep(0.5)
    
    print("\n✅ Test traffic generated! Open the dashboard to see live metrics.")
except KeyboardInterrupt:
    print("\n⏹️ Traffic generation stopped.")
