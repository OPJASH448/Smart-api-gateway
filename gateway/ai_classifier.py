"""
AI Classifier for Smart API Gateway
Classifies incoming requests and determines the best service to route to.
Uses scoring algorithm for optimal routing when multiple services match.
"""

import os
import google.generativeai as genai
from typing import Dict, Tuple, Optional
from dotenv import load_dotenv
import json

load_dotenv(dotenv_path="services/ai_service/.env")

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY not set in .env")

genai.configure(api_key=GEMINI_API_KEY)

# Initialize model
try:
    model = genai.GenerativeModel("gemini-2.5-flash")
    print("✅ AI Classifier initialized with gemini-2.5-flash")
except Exception as e:
    print(f"⚠️  Model initialization: {e}")
    model = None


class ServiceClassifier:
    """
    Intelligent request classifier that determines which service should handle the request.
    """
    
    # Service profiles with keywords and descriptions
    SERVICE_PROFILES = {
        "auth": {
            "keywords": ["login", "signup", "password", "authenticate", "token", "session", "logout", "user", "identity"],
            "description": "Authentication & user management service",
            "endpoints": ["/auth/login", "/auth/signup", "/auth/logout"]
        },
        "chat": {
            "keywords": ["chat", "message", "conversation", "dialog", "talk", "discussion", "communicate"],
            "description": "Real-time chat and messaging service",
            "endpoints": ["/chat/send", "/chat/history", "/chat/rooms"]
        },
        "ai": {
            "keywords": ["ai", "analyze", "generate", "question", "answer", "summarize", "explain", "intelligent", "smart", "predict"],
            "description": "AI-powered analysis and generation service",
            "endpoints": ["/ai/chat", "/ai/analyze", "/ai/generate"]
        },
        "products": {
            "keywords": ["product", "catalog", "inventory", "price", "buy", "order", "shop", "item", "sku"],
            "description": "Product catalog and ordering service",
            "endpoints": ["/products/list", "/products/search", "/products/order"]
        }
    }
    
    @staticmethod
    def classify_with_ai(request_text: str) -> Dict[str, float]:
        """
        Use Gemini AI to classify the request and score services.
        Returns a dict with service names as keys and confidence scores (0-1) as values.
        """
        if not model:
            return ServiceClassifier._classify_with_keywords(request_text)
        
        prompt = f"""Analyze this request and determine which service should handle it.
        
Available services:
1. auth - Authentication & user management (login, signup, password reset, tokens)
2. chat - Real-time chat & messaging (conversations, messages, channels)
3. ai - AI analysis & generation (questions, summaries, predictions, explanations)
4. products - Product catalog & ordering (shopping, inventory, orders)

Request: "{request_text}"

Respond ONLY with valid JSON (no markdown, no code blocks) with scores 0-1 for each service:
{{"auth": 0.x, "chat": 0.x, "ai": 0.x, "products": 0.x}}

Example: {{"auth": 0.9, "chat": 0.1, "ai": 0.0, "products": 0.0}}"""

        try:
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Clean up if wrapped in code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            scores = json.loads(response_text)
            return scores
        except Exception as e:
            print(f"⚠️  AI classification error: {e}, falling back to keyword matching")
            return ServiceClassifier._classify_with_keywords(request_text)
    
    @staticmethod
    def _classify_with_keywords(request_text: str) -> Dict[str, float]:
        """
        Fallback keyword-based classification when AI is unavailable.
        """
        request_lower = request_text.lower()
        scores = {}
        
        for service_name, profile in ServiceClassifier.SERVICE_PROFILES.items():
            # Count keyword matches
            matches = sum(1 for keyword in profile["keywords"] if keyword in request_lower)
            max_matches = len(profile["keywords"])
            
            # Calculate confidence score (0-1)
            confidence = min(1.0, matches / max(max_matches / 3, 1))
            scores[service_name] = confidence
        
        return scores
    
    @staticmethod
    def classify_request(request_text: str) -> Tuple[str, Dict[str, float]]:
        """
        Classify request and return the best service + all scores.
        
        Returns:
            Tuple of (best_service_name, scores_dict)
        """
        scores = ServiceClassifier.classify_with_ai(request_text)
        
        # Find service with highest score
        best_service = max(scores.items(), key=lambda x: x[1])[0]
        
        return best_service, scores
    
    @staticmethod
    def should_classify(path: str, body: Optional[str] = None) -> bool:
        """
        Determine if request should use AI classification.
        Returns True if content-based routing is needed.
        """
        # Classify POST/PUT requests with bodies
        return body is not None and len(body) > 0


class RoutingScorer:
    """
    Scores and ranks services for optimal routing.
    """
    
    @staticmethod
    def get_optimal_route(classification_scores: Dict[str, float], 
                         service_urls: Dict[str, str]) -> Tuple[str, str]:
        """
        Given classification scores, determine the optimal service URL to route to.
        
        Returns:
            Tuple of (service_name, service_url)
        """
        # Filter only available services
        available_scores = {
            service: score for service, score in classification_scores.items() 
            if service in service_urls
        }
        
        if not available_scores:
            raise ValueError("❌ No available services match the request")
        
        # Get service with highest score
        best_service = max(available_scores.items(), key=lambda x: x[1])[0]
        service_url = service_urls[best_service]
        
        return best_service, service_url
    
    @staticmethod
    def get_routing_info(classification_scores: Dict[str, float]) -> Dict:
        """
        Get detailed routing information for logging/debugging.
        """
        sorted_scores = sorted(
            classification_scores.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        return {
            "primary_service": sorted_scores[0][0],
            "primary_confidence": round(sorted_scores[0][1], 3),
            "alternatives": [
                {"service": svc, "confidence": round(score, 3)} 
                for svc, score in sorted_scores[1:]
                if score > 0.1  # Only show alternatives with >10% confidence
            ]
        }
