#!/usr/bin/env python
"""Test script to call /ai/chat endpoint through the gateway."""

import httpx
import json

def test_ai_chat():
    # Make a POST request to the /ai/chat endpoint
    prompt = "What are the top 3 benefits of using microservices architecture?"

    response = httpx.post(
        "http://localhost:8000/ai/chat",
        json={"prompt": prompt},
        timeout=30.0
    )

    print("=" * 70)
    print("REQUEST:")
    print("=" * 70)
    print(f"Endpoint: POST http://localhost:8000/ai/chat")
    print(f"Prompt: {prompt}\n")

    print("=" * 70)
    print("RESPONSE:")
    print("=" * 70)
    result = response.json()
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    test_ai_chat()
