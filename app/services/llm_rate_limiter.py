"""
LLM Rate Limiter for GenHealthAI
Prevents OpenAI API rate limit violations and controls costs
"""

import asyncio
import time
from typing import Dict, Optional
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RateLimit:
    """Rate limit configuration"""
    requests_per_minute: int
    tokens_per_minute: int
    requests_per_day: int
    tokens_per_day: int

@dataclass
class UsageTracker:
    """Track API usage over time"""
    requests_count: int = 0
    tokens_count: int = 0
    last_reset: datetime = None
    
    def __post_init__(self):
        if self.last_reset is None:
            self.last_reset = datetime.now()

class LLMRateLimiter:
    """Rate limiter for LLM API calls with token and request tracking"""
    
    def __init__(self, rate_limits: Dict[str, RateLimit]):
        """
        Initialize rate limiter
        
        Args:
            rate_limits: Dictionary mapping model names to their rate limits
        """
        self.rate_limits = rate_limits
        self.usage_trackers: Dict[str, Dict[str, UsageTracker]] = {}
        self.request_queue: Dict[str, asyncio.Queue] = {}
        self.lock = asyncio.Lock()
    
    def _get_tracker(self, model: str, time_window: str) -> UsageTracker:
        """Get or create usage tracker for model and time window"""
        if model not in self.usage_trackers:
            self.usage_trackers[model] = {}
        
        if time_window not in self.usage_trackers[model]:
            self.usage_trackers[model][time_window] = UsageTracker()
        
        return self.usage_trackers[model][time_window]
    
    def _reset_if_needed(self, tracker: UsageTracker, window_seconds: int):
        """Reset tracker if time window has passed"""
        now = datetime.now()
        if now - tracker.last_reset > timedelta(seconds=window_seconds):
            tracker.requests_count = 0
            tracker.tokens_count = 0
            tracker.last_reset = now
    
    def _can_make_request(self, model: str, estimated_tokens: int) -> tuple[bool, str]:
        """Check if request can be made within rate limits"""
        if model not in self.rate_limits:
            return True, ""
        
        limits = self.rate_limits[model]
        
        # Check minute limits
        minute_tracker = self._get_tracker(model, "minute")
        self._reset_if_needed(minute_tracker, 60)
        
        if minute_tracker.requests_count >= limits.requests_per_minute:
            return False, f"Minute request limit ({limits.requests_per_minute}) exceeded"
        
        if minute_tracker.tokens_count + estimated_tokens > limits.tokens_per_minute:
            return False, f"Minute token limit ({limits.tokens_per_minute}) would be exceeded"
        
        # Check daily limits
        daily_tracker = self._get_tracker(model, "daily")
        self._reset_if_needed(daily_tracker, 24 * 3600)
        
        if daily_tracker.requests_count >= limits.requests_per_day:
            return False, f"Daily request limit ({limits.requests_per_day}) exceeded"
        
        if daily_tracker.tokens_count + estimated_tokens > limits.tokens_per_day:
            return False, f"Daily token limit ({limits.tokens_per_day}) would be exceeded"
        
        return True, ""
    
    def _record_usage(self, model: str, tokens_used: int):
        """Record API usage"""
        # Record for minute window
        minute_tracker = self._get_tracker(model, "minute")
        minute_tracker.requests_count += 1
        minute_tracker.tokens_used += tokens_used
        
        # Record for daily window
        daily_tracker = self._get_tracker(model, "daily")
        daily_tracker.requests_count += 1
        daily_tracker.tokens_used += tokens_used
        
        logger.info(f"Recorded usage for {model}: {tokens_used} tokens")
    
    async def acquire(self, model: str, estimated_tokens: int) -> bool:
        """
        Acquire permission to make an API call
        
        Args:
            model: The model being called
            estimated_tokens: Estimated tokens for the request
            
        Returns:
            True if request can proceed, False if rate limited
        """
        async with self.lock:
            can_proceed, reason = self._can_make_request(model, estimated_tokens)
            
            if not can_proceed:
                logger.warning(f"Rate limit hit for {model}: {reason}")
                return False
            
            # Reserve the tokens
            minute_tracker = self._get_tracker(model, "minute")
            daily_tracker = self._get_tracker(model, "daily")
            
            minute_tracker.requests_count += 1
            minute_tracker.tokens_count += estimated_tokens
            
            daily_tracker.requests_count += 1
            daily_tracker.tokens_count += estimated_tokens
            
            return True
    
    async def record_actual_usage(self, model: str, actual_tokens: int, estimated_tokens: int):
        """
        Record actual token usage and adjust counters
        
        Args:
            model: The model that was called
            actual_tokens: Actual tokens consumed
            estimated_tokens: Previously estimated tokens
        """
        async with self.lock:
            # Adjust the counters with actual usage
            token_diff = actual_tokens - estimated_tokens
            
            minute_tracker = self._get_tracker(model, "minute")
            daily_tracker = self._get_tracker(model, "daily")
            
            minute_tracker.tokens_count += token_diff
            daily_tracker.tokens_count += token_diff
            
            if token_diff != 0:
                logger.info(f"Adjusted token count for {model}: {token_diff} tokens")
    
    def get_usage_stats(self, model: str) -> Dict:
        """Get current usage statistics for a model"""
        if model not in self.usage_trackers:
            return {"minute": {"requests": 0, "tokens": 0}, "daily": {"requests": 0, "tokens": 0}}
        
        minute_tracker = self._get_tracker(model, "minute")
        daily_tracker = self._get_tracker(model, "daily")
        
        self._reset_if_needed(minute_tracker, 60)
        self._reset_if_needed(daily_tracker, 24 * 3600)
        
        return {
            "minute": {
                "requests": minute_tracker.requests_count,
                "tokens": minute_tracker.tokens_count,
                "limits": {
                    "requests": self.rate_limits.get(model, RateLimit(0, 0, 0, 0)).requests_per_minute,
                    "tokens": self.rate_limits.get(model, RateLimit(0, 0, 0, 0)).tokens_per_minute
                }
            },
            "daily": {
                "requests": daily_tracker.requests_count,
                "tokens": daily_tracker.tokens_count,
                "limits": {
                    "requests": self.rate_limits.get(model, RateLimit(0, 0, 0, 0)).requests_per_day,
                    "tokens": self.rate_limits.get(model, RateLimit(0, 0, 0, 0)).tokens_per_day
                }
            }
        }

# Default rate limits based on OpenAI's current limits (adjust as needed)
DEFAULT_RATE_LIMITS = {
    "gpt-4o": RateLimit(
        requests_per_minute=500,
        tokens_per_minute=30000,
        requests_per_day=10000,
        tokens_per_day=1000000
    ),
    "gpt-4": RateLimit(
        requests_per_minute=200,
        tokens_per_minute=10000,
        requests_per_day=5000,
        tokens_per_day=500000
    ),
    "gpt-3.5-turbo": RateLimit(
        requests_per_minute=3500,
        tokens_per_minute=90000,
        requests_per_day=50000,
        tokens_per_day=2000000
    )
}

# Global rate limiter instance
llm_rate_limiter = LLMRateLimiter(DEFAULT_RATE_LIMITS)

async def rate_limited_llm_call(model: str, estimated_tokens: int, llm_function, *args, **kwargs):
    """
    Wrapper for LLM calls with rate limiting
    
    Args:
        model: Model name
        estimated_tokens: Estimated tokens for the request
        llm_function: The actual LLM function to call
        *args, **kwargs: Arguments for the LLM function
    
    Returns:
        Result of the LLM function or None if rate limited
    """
    # Try to acquire permission
    if not await llm_rate_limiter.acquire(model, estimated_tokens):
        logger.warning(f"Request to {model} was rate limited")
        return None
    
    try:
        # Make the actual API call
        result = await llm_function(*args, **kwargs)
        
        # If the result contains actual token usage, record it
        if hasattr(result, 'usage') and hasattr(result.usage, 'total_tokens'):
            actual_tokens = result.usage.total_tokens
            await llm_rate_limiter.record_actual_usage(model, actual_tokens, estimated_tokens)
        
        return result
        
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        # If the call failed, we should return the reserved tokens
        await llm_rate_limiter.record_actual_usage(model, 0, estimated_tokens)
        raise

def estimate_tokens(text: str) -> int:
    """
    Rough estimation of tokens in text
    OpenAI uses ~4 characters per token for English text
    """
    return len(text) // 4 + 100  # Add buffer for prompt overhead
