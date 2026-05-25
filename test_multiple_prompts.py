#!/usr/bin/env python
"""Test script to call /ai/chat endpoint with multiple prompts."""

import httpx
import json

def test_prompt(prompt: str):
    response = httpx.post(
        "http://localhost:8000/ai/chat",
        json={"prompt": prompt},
        timeout=30.0
    )
    
    result = response.json()
    print(f"\n{'='*70}")
    print(f"PROMPT: {prompt}")
    print(f"{'='*70}")
    print(result["response"])
    print()

if __name__ == "__main__":
    print("🚀 Testing API Gateway /ai/chat endpoint with multiple prompts\n")
    
    test_prompt("Explain API Gateway and its key responsibilities")
    test_prompt("What is REST API and GraphQL?")
    test_prompt("Tell me about microservices")
