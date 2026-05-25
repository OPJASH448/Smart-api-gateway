#!/usr/bin/env python3
"""
Complete Workflow Test:
1. Make request with source tracking
2. Check Redis cache
3. See optimal routing with scoring formula
4. View service metrics

Maximum workflow demonstration
"""

import httpx
import json
import time
from typing import Dict

API_BASE = "http://localhost:8000"

def print_section(title: str):
    """Print formatted section header"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def test_request_with_source(text: str, source: str, repeat: int = 1):
    """
    Test the /gateway/route-with-cache endpoint
    Shows: cache check → classification → optimal routing → logging
    """
    print(f"[*] Testing request: '{text[:50]}...'")
    print(f"[*] Source: {source}")
    print(f"[*] Requests: {repeat}\n")
    
    results = []
    for i in range(repeat):
        try:
            response = httpx.post(
                f"{API_BASE}/gateway/route-with-cache",
                json={
                    "text": text,
                    "source": source,
                    "method": "POST"
                },
                timeout=10
            )
            
            result = response.json()
            results.append(result)
            
            # Format output
            status = result.get("status", "unknown")
            service = result.get("service", "?").upper()
            confidence = result.get("confidence", 0)
            cached = result.get("cached", False)
            routing_score = result.get("routing_score", 0)
            metrics_used = result.get("metrics_used", 0)
            
            cached_indicator = "[CACHE HIT]" if cached else "[NEW REQUEST]"
            
            print(f"  Request #{i+1}: {cached_indicator}")
            print(f"    Service: {service}")
            print(f"    Confidence: {confidence*100:.1f}%")
            print(f"    Routing Score: {routing_score:.3f}")
            print(f"    Metrics Used: {metrics_used}")
            
            if "classification_scores" in result:
                print(f"    All Scores: {result['classification_scores']}")
            
            print()
            
        except Exception as e:
            print(f"  [!] Error on request #{i+1}: {e}\n")
            return []
    
    return results

def main():
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*78 + "║")
    print("║" + "  SMART API GATEWAY - COMPLETE WORKFLOW TEST".center(78) + "║")
    print("║" + "  Cache → Classification → Optimal Routing → Logging".center(78) + "║")
    print("║" + " "*78 + "║")
    print("╚" + "="*78 + "╝")
    
    # Test 1: Single request from login page
    print_section("TEST 1: Auth Request from Login Page")
    results = test_request_with_source(
        "I need to log in with my username and password",
        "loginpage"
    )
    
    # Test 2: Same request again - should hit cache
    print_section("TEST 2: Same Auth Request Again - Should Hit Cache")
    results = test_request_with_source(
        "I need to log in with my username and password",
        "loginpage"
    )
    if results and results[0].get("cached"):
        print("✅ CACHE HIT SUCCESSFUL!")
    else:
        print("⚠️  Cache miss (first time or Redis not available)")
    
    # Test 3: Multiple requests to build metrics
    print_section("TEST 3: Build Service Metrics - 5 AI Requests")
    results = test_request_with_source(
        "Can you analyze this data and predict future trends?",
        "analytics_page",
        repeat=5
    )
    
    # Test 4: Another service type
    print_section("TEST 4: Product Request from Shop Page")
    results = test_request_with_source(
        "Show me laptops under $1000 and add one to my cart",
        "shop_page"
    )
    
    # Test 5: Complex request
    print_section("TEST 5: Complex Request - Chat from Messaging Page")
    results = test_request_with_source(
        "Send a message to my friend in the group chat",
        "messaging_page"
    )
    
    # Test 6: Build more metrics with different sources
    print_section("TEST 6: Multiple Sources - Same AI Service")
    results = test_request_with_source(
        "What's the weather forecast for tomorrow?",
        "dashboard",
        repeat=3
    )
    
    # Test 7: Different source, same request (cache key includes source)
    print_section("TEST 7: Different Source, Same Text - New Cache Entry")
    results = test_request_with_source(
        "What's the weather forecast for tomorrow?",
        "mobile_app"
    )
    
    # Show routing algorithm in action
    print_section("WORKFLOW SUMMARY")
    print("""
    Complete Workflow Steps:
    
    1. REQUEST RECEIVED:
       - Extract text and source (e.g., "loginpage", "shop_page")
       - Create request hash from (text + source)
    
    2. CACHE CHECK:
       - Look up request_hash in Redis
       - If found: Return cached classification immediately
       - If not found: Continue to step 3
    
    3. AI CLASSIFICATION:
       - Send request to Gemini AI classifier
       - Get confidence scores for all services:
         * auth, chat, ai, products
    
    4. OPTIMAL ROUTING:
       - Apply formula to select best service:
         score = 0.6*latency_norm + 0.3*error_rate_norm + 0.1*load_norm
       - Consider last 20 metrics per service
       - Combine classification (70%) + performance (30%)
    
    5. REDIS CACHING:
       - Cache classification result with TTL=1 hour
       - Store service metrics (last 20 records)
       - Track source for future analysis
    
    6. DATABASE LOGGING:
       - Log routing decision to PostgreSQL
       - Store confidence, routing_score, and source
       - Enable audit trail and analytics
    
    Result: Fast, optimal, intelligent routing with cache efficiency!
    """)

if __name__ == "__main__":
    main()
