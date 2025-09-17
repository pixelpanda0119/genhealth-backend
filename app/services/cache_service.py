"""
Caching service for GenHealthAI
Improves performance for expensive operations like document processing
"""

import hashlib
import json
import pickle
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
import os
import logging

logger = logging.getLogger(__name__)

class InMemoryCache:
    """Simple in-memory cache with TTL support"""
    
    def __init__(self, default_ttl_seconds: int = 3600):  # 1 hour default
        self._cache: Dict[str, Dict] = {}
        self.default_ttl = default_ttl_seconds
    
    def _is_expired(self, cache_entry: Dict) -> bool:
        """Check if a cache entry has expired"""
        if 'expires_at' not in cache_entry:
            return False
        return datetime.now() > cache_entry['expires_at']
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache"""
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        if self._is_expired(entry):
            del self._cache[key]
            return None
        
        # Update access time for LRU tracking
        entry['last_accessed'] = datetime.now()
        return entry['value']
    
    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Set a value in cache with optional TTL"""
        ttl = ttl_seconds or self.default_ttl
        expires_at = datetime.now() + timedelta(seconds=ttl)
        
        self._cache[key] = {
            'value': value,
            'created_at': datetime.now(),
            'last_accessed': datetime.now(),
            'expires_at': expires_at
        }
        
        # Simple cleanup: remove expired entries when cache gets large
        if len(self._cache) > 1000:
            self._cleanup_expired()
    
    def delete(self, key: str) -> bool:
        """Delete a key from cache"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cache entries"""
        self._cache.clear()
    
    def _cleanup_expired(self) -> None:
        """Remove expired entries from cache"""
        expired_keys = [
            key for key, entry in self._cache.items()
            if self._is_expired(entry)
        ]
        for key in expired_keys:
            del self._cache[key]
        
        logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")

class DocumentProcessingCache:
    """Specialized cache for document processing results"""
    
    def __init__(self, cache_dir: str = "cache", default_ttl_hours: int = 24):
        self.cache_dir = cache_dir
        self.default_ttl = timedelta(hours=default_ttl_hours)
        self.memory_cache = InMemoryCache(default_ttl_seconds=default_ttl_hours * 3600)
        
        # Create cache directory if it doesn't exist
        os.makedirs(cache_dir, exist_ok=True)
    
    def _generate_cache_key(self, file_content: bytes, processing_params: Dict) -> str:
        """Generate a unique cache key based on file content and processing parameters"""
        # Hash file content
        file_hash = hashlib.sha256(file_content).hexdigest()
        
        # Hash processing parameters
        params_str = json.dumps(processing_params, sort_keys=True)
        params_hash = hashlib.sha256(params_str.encode()).hexdigest()
        
        return f"doc_{file_hash}_{params_hash}"
    
    def get_processing_result(self, file_content: bytes, processing_params: Dict) -> Optional[Dict]:
        """Get cached document processing result"""
        try:
            cache_key = self._generate_cache_key(file_content, processing_params)
            
            # Try memory cache first (fastest)
            result = self.memory_cache.get(cache_key)
            if result is not None:
                logger.info(f"Cache hit (memory): {cache_key}")
                return result
            
            # Try disk cache
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")
            if os.path.exists(cache_file):
                # Check if file is not expired
                file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
                if file_age < self.default_ttl:
                    with open(cache_file, 'rb') as f:
                        result = pickle.load(f)
                    
                    # Store in memory cache for faster subsequent access
                    self.memory_cache.set(cache_key, result)
                    logger.info(f"Cache hit (disk): {cache_key}")
                    return result
                else:
                    # Remove expired file
                    os.remove(cache_file)
            
            logger.info(f"Cache miss: {cache_key}")
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving from cache: {e}")
            return None
    
    def set_processing_result(self, file_content: bytes, processing_params: Dict, result: Dict) -> None:
        """Cache document processing result"""
        try:
            cache_key = self._generate_cache_key(file_content, processing_params)
            
            # Store in memory cache
            self.memory_cache.set(cache_key, result)
            
            # Store in disk cache for persistence
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")
            with open(cache_file, 'wb') as f:
                pickle.dump(result, f)
            
            logger.info(f"Cached processing result: {cache_key}")
            
        except Exception as e:
            logger.error(f"Error storing in cache: {e}")
    
    def clear_expired(self) -> None:
        """Clear expired cache entries from disk"""
        try:
            current_time = datetime.now()
            expired_count = 0
            
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.pkl'):
                    file_path = os.path.join(self.cache_dir, filename)
                    file_age = current_time - datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    if file_age > self.default_ttl:
                        os.remove(file_path)
                        expired_count += 1
            
            if expired_count > 0:
                logger.info(f"Cleaned up {expired_count} expired disk cache entries")
                
        except Exception as e:
            logger.error(f"Error cleaning up disk cache: {e}")

# Global cache instances
memory_cache = InMemoryCache()
document_cache = DocumentProcessingCache()

def cache_key_from_params(**kwargs) -> str:
    """Generate a cache key from parameters"""
    params_str = json.dumps(kwargs, sort_keys=True, default=str)
    return hashlib.sha256(params_str.encode()).hexdigest()

def cached_result(cache_key: str, ttl_seconds: int = 3600):
    """Decorator for caching function results"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Try to get from cache first
            result = memory_cache.get(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            memory_cache.set(cache_key, result, ttl_seconds)
            return result
        
        return wrapper
    return decorator
