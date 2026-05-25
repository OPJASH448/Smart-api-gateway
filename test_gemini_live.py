#!/usr/bin/env python
"""Simple test showing full responses from real Gemini API."""

import httpx
import json

def test_prompt(prompt):
    """Test a single prompt."""
    print(f"\n{'='*70}")
    print(f"🔹 PROMPT: {prompt}")
    print(f"{'='*70}\n")
    
    try:
        response = httpx.post(
            "http://localhost:8000/ai/chat",
            json={"prompt": prompt},
            timeout=30.0
        )
        
        result = response.json()
        
        if result.get("status") == "success":
            print(f"✅ Model: {result.get('model')}")
            print(f"📝 Response:\n")
            print(result["response"])
        else:
            print(f"❌ Error: {result.get('error')}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("\n🚀 LIVE GEMINI API TEST\n")
    
    test_prompt("What is circuit breaker pattern in software design?")
    test_prompt("Explain rate limiting and why it's important")
    test_prompt("What is load balancing?")
