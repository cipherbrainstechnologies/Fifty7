"""
Performance optimizations and caching layer
"""

import time
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from functools import lru_cache
from logzero import logger


class TTLCache:
    """
    Time-to-live cache for frequently accessed data.
    """
    
    def __init__(self, default_ttl_seconds: float = 60.0):
        """
        Initialize TTL cache.
        
        Args:
            default_ttl_seconds: Default TTL in seconds
        """
        self.default_ttl = default_ttl_seconds
        self._cache: Dict[str, tuple] = {}  # key -> (value, expiry_time)
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache if not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if expired/not found
        """
        if key not in self._cache:
            return None
        
        value, expiry = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None):
        """
        Set value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: TTL in seconds (None for default)
        """
        ttl = ttl_seconds or self.default_ttl
        expiry = time.time() + ttl
        self._cache[key] = (value, expiry)
    
    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()
    
    def cleanup_expired(self):
        """Remove expired entries."""
        now = time.time()
        expired_keys = [k for k, (_, expiry) in self._cache.items() if now > expiry]
        for key in expired_keys:
            del self._cache[key]


class StateCache:
    """
    Caching layer for StateStore operations.
    """
    
    def __init__(self, state_store=None, default_ttl: float = 30.0):
        """
        Initialize state cache.
        
        Args:
            state_store: StateStore instance (optional)
            default_ttl: Default cache TTL in seconds
        """
        from .state_store import get_state_store
        self.state_store = state_store or get_state_store()
        self.cache = TTLCache(default_ttl=default_ttl)
    
    def get_state(self, path: Optional[str] = None, use_cache: bool = True) -> Any:
        """
        Get state with optional caching.
        
        Args:
            path: State path
            use_cache: Whether to use cache
            
        Returns:
            State value
        """
        cache_key = path or '__all__'
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        
        # Fetch from state store
        value = self.state_store.get_state(path)
        
        if use_cache and value is not None:
            self.cache.set(cache_key, value)
        
        return value
    
    def invalidate(self, path: Optional[str] = None):
        """
        Invalidate cache for a path.
        
        Args:
            path: State path (None for all)
        """
        if path:
            cache_key = path
            if cache_key in self.cache._cache:
                del self.cache._cache[cache_key]
        else:
            self.cache.clear()


# Global cache instance
_state_cache: Optional[StateCache] = None


def get_state_cache() -> StateCache:
    """Get or create StateCache instance."""
    global _state_cache
    if _state_cache is None:
        _state_cache = StateCache()
    return _state_cache

