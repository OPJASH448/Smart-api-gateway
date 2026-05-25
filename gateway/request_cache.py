"""
Redis Cache Layer for Smart Routing
Handles request caching, source tracking, and last 20 metrics per service
"""

import json
import time
from typing import Dict, List, Optional, Tuple
from gateway.redis_client import redis_client

class RequestCache:
    """
    Manages request caching with source tracking and service metrics.
    """
    
    REQUEST_CACHE_PREFIX = "cache:request:"
    SERVICE_METRICS_PREFIX = "metrics:service:history:"
    CACHE_TTL = 3600  # 1 hour
    METRICS_HISTORY_MAX = 20
    
    @staticmethod
    async def get_cached_classification(request_hash: str) -> Optional[Dict]:
        """
        Get cached classification result for a request.
        
        Returns:
            {
                "service": "auth",
                "confidence": 0.95,
                "source": "loginpage",
                "timestamp": 1234567890,
                "cached": True
            }
            or None if not cached
        """
        try:
            cache_key = f"{RequestCache.REQUEST_CACHE_PREFIX}{request_hash}"
            cached_data = redis_client.get(cache_key)
            
            if cached_data:
                return json.loads(cached_data)
            return None
        except Exception as e:
            print(f"[!] Cache retrieval error: {e}")
            return None
    
    @staticmethod
    async def cache_classification(
        request_hash: str,
        service: str,
        confidence: float,
        source: str = "unknown"
    ) -> bool:
        """
        Cache a classification result with source information.
        """
        try:
            cache_key = f"{RequestCache.REQUEST_CACHE_PREFIX}{request_hash}"
            cache_data = {
                "service": service,
                "confidence": confidence,
                "source": source,
                "timestamp": int(time.time()),
                "cached": True
            }
            
            redis_client.setex(
                cache_key,
                RequestCache.CACHE_TTL,
                json.dumps(cache_data)
            )
            return True
        except Exception as e:
            print(f"[!] Cache storage error: {e}")
            return False
    
    @staticmethod
    async def record_service_metric(
        service: str,
        latency_ms: float,
        status_code: int,
        source: str = "unknown"
    ) -> bool:
        """
        Record a service metric and maintain last 20 records.
        """
        try:
            metrics_key = f"{RequestCache.SERVICE_METRICS_PREFIX}{service}"
            
            metric_entry = {
                "timestamp": int(time.time()),
                "latency_ms": latency_ms,
                "status": status_code,
                "source": source,
                "success": 200 <= status_code < 300
            }
            
            # Push to Redis list
            redis_client.lpush(metrics_key, json.dumps(metric_entry))
            
            # Keep only last 20 records
            redis_client.ltrim(metrics_key, 0, RequestCache.METRICS_HISTORY_MAX - 1)
            
            # Set TTL on the list
            redis_client.expire(metrics_key, 86400)  # 24 hours
            
            return True
        except Exception as e:
            print(f"[!] Metric recording error: {e}")
            return False
    
    @staticmethod
    async def get_last_metrics(service: str, limit: int = 20) -> List[Dict]:
        """
        Get last N metrics for a service.
        """
        try:
            metrics_key = f"{RequestCache.SERVICE_METRICS_PREFIX}{service}"
            raw_metrics = redis_client.lrange(metrics_key, 0, limit - 1)
            
            metrics = []
            for raw_metric in raw_metrics:
                try:
                    metric = json.loads(raw_metric)
                    metrics.append(metric)
                except:
                    continue
            
            return metrics
        except Exception as e:
            print(f"[!] Metrics retrieval error: {e}")
            return []
    
    @staticmethod
    async def compute_service_score(
        service: str,
        all_services_latencies: Dict[str, float]
    ) -> Tuple[float, Dict]:
        """
        Compute score for a service using the formula:
        score = 0.6 * latency_norm + 0.3 * error_rate_norm + 0.1 * load_norm
        
        Returns:
            (score, metrics_dict)
            Lower score = better service
        """
        metrics = await RequestCache.get_last_metrics(service)
        
        if not metrics:
            # No data = worst score
            return (1.0, {"latency_ms": float("inf"), "error_rate": 1.0, "load": 0})
        
        # Calculate average latency
        latencies = [m.get("latency_ms", 0) for m in metrics]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        
        # Calculate error rate
        successes = sum(1 for m in metrics if m.get("success", False))
        error_rate = 1.0 - (successes / len(metrics)) if metrics else 1.0
        
        # Get min/max latencies across all services for normalization
        min_latency = min(all_services_latencies.values()) if all_services_latencies else 0
        max_latency = max(all_services_latencies.values()) if all_services_latencies else 1
        
        # Normalize latency (0..1)
        latency_norm = (avg_latency - min_latency) / (max_latency - min_latency + 1e-9)
        
        # Error rate is already 0..1
        error_rate_norm = error_rate
        
        # Load norm (placeholder - could use queue depth)
        load_norm = 0.0
        
        # Weighted scoring
        score = (0.6 * latency_norm) + (0.3 * error_rate_norm) + (0.1 * load_norm)
        
        return (score, {
            "latency_ms": avg_latency,
            "error_rate": error_rate,
            "load": load_norm,
            "sample_size": len(metrics)
        })
    
    @staticmethod
    async def get_best_service(
        services: List[str],
        scores_dict: Dict[str, float]
    ) -> Tuple[str, float]:
        """
        Select best service based on classification scores and metrics.
        """
        # Get average latencies for all services
        latencies = {}
        for service in services:
            metrics = await RequestCache.get_last_metrics(service)
            if metrics:
                latencies[service] = sum(m.get("latency_ms", 100) for m in metrics) / len(metrics)
            else:
                latencies[service] = 100  # Default latency
        
        # Compute scores
        service_scores = {}
        for service in services:
            classification_score = scores_dict.get(service, 0)
            routing_score, _ = await RequestCache.compute_service_score(service, latencies)
            
            # Combine: 70% classification, 30% performance metrics
            combined_score = (0.7 * classification_score) + (0.3 * routing_score)
            service_scores[service] = combined_score
        
        # Return service with highest combined score (not lowest!)
        best_service = max(service_scores.items(), key=lambda x: x[1])
        return best_service
