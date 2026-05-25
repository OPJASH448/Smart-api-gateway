"""
AI Service - Simplified with ChatGPT and Grok stubs
No external API calls, just fast local responses with simulated latencies
Listens on port 9003
"""

import asyncio
import time
import uvicorn
import random
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AI Service (Simple)", version="1.0.0")

class ChatRequest(BaseModel):
    prompt: str
    model: str = "chatgpt"  # Options: chatgpt, grok

class ChatResponse(BaseModel):
    prompt: str
    response: str
    model: str
    latency_ms: float
    service: str = "ai"
    status: str = "success"

@app.post("/ai/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Simple AI chat endpoint with simulated latencies.
    
    - ChatGPT: 150-250ms (reliable, moderate speed)
    - Grok: 50-100ms (fast but occasionally errors)
    """
    start_time = time.time()
    model = request.model.lower()
    
    # Simulate different latencies and behaviors
    if model == "grok":
        # Grok: Fast but sometimes unreliable
        latency = random.uniform(0.05, 0.1)  # 50-100ms
        await asyncio.sleep(latency)
        
        # 90% success, 10% errors
        if random.random() > 0.9:
            response_text = "[Grok Error: Rate limited]"
        else:
            response_text = f"[Grok Response] Processing: {request.prompt[:50]}..."
    else:
        # ChatGPT: Slower but very reliable
        latency = random.uniform(0.15, 0.25)  # 150-250ms
        await asyncio.sleep(latency)
        response_text = f"[ChatGPT Response] Analyzing: {request.prompt[:50]}..."
    
    elapsed = (time.time() - start_time) * 1000  # Convert to ms
    
    return ChatResponse(
        prompt=request.prompt,
        response=response_text,
        model=model,
        latency_ms=round(elapsed, 2),
        service="ai",
        status="success"
    )

@app.get("/ai/health")
async def health_check():
    """Simple health check endpoint"""
    return {
        "status": "healthy",
        "service": "ai_service",
        "timestamp": int(time.time()),
        "models": ["chatgpt", "grok"]
    }

if __name__ == "__main__":
    print("[+] AI Service started (ChatGPT + Grok stubs, no external APIs)")
    uvicorn.run(app, host="0.0.0.0", port=9003)