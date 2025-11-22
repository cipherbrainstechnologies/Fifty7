"""
UI Optimization utilities: debounce, throttle, stale state detection
"""

import time
from functools import wraps
from typing import Callable, Any, Optional
from datetime import datetime, timedelta
from logzero import logger


def debounce(wait: float):
    """
    Decorator to debounce function calls.
    
    Args:
        wait: Seconds to wait before executing
        
    Example:
        @debounce(0.5)
        def update_ui():
            pass
    """
    def decorator(fn: Callable) -> Callable:
        last_call = [0]
        
        @wraps(fn)
        def debounced(*args, **kwargs):
            now = time.time()
            if now - last_call[0] >= wait:
                last_call[0] = now
                return fn(*args, **kwargs)
        
        return debounced
    return decorator


def throttle(wait: float):
    """
    Decorator to throttle function calls (execute at most once per wait period).
    
    Args:
        wait: Minimum seconds between executions
        
    Example:
        @throttle(1.0)
        def update_ui():
            pass
    """
    def decorator(fn: Callable) -> Callable:
        last_call = [0]
        
        @wraps(fn)
        def throttled(*args, **kwargs):
            now = time.time()
            if now - last_call[0] >= wait:
                last_call[0] = now
                return fn(*args, **kwargs)
        
        return throttled
    return decorator


class StaleStateDetector:
    """
    Detects stale state and triggers refresh.
    """
    
    def __init__(self, max_age_seconds: float = 30.0):
        """
        Initialize stale state detector.
        
        Args:
            max_age_seconds: Maximum age before state is considered stale
        """
        self.max_age = timedelta(seconds=max_age_seconds)
        self.state_timestamps: dict = {}
    
    def update_timestamp(self, path: str, timestamp: Optional[datetime] = None):
        """
        Update timestamp for a state path.
        
        Args:
            path: State path
            timestamp: Timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        self.state_timestamps[path] = timestamp
    
    def is_stale(self, path: str) -> bool:
        """
        Check if state at path is stale.
        
        Args:
            path: State path
            
        Returns:
            True if stale, False otherwise
        """
        if path not in self.state_timestamps:
            return True
        
        age = datetime.utcnow() - self.state_timestamps[path]
        return age > self.max_age
    
    def get_age(self, path: str) -> Optional[timedelta]:
        """
        Get age of state at path.
        
        Args:
            path: State path
            
        Returns:
            Age as timedelta or None if not found
        """
        if path not in self.state_timestamps:
            return None
        return datetime.utcnow() - self.state_timestamps[path]


class LoadingStateManager:
    """
    Manages loading states for UI components.
    """
    
    def __init__(self):
        self.loading_states: dict = {}
        self.lock = None  # Will be set if threading is needed
    
    def set_loading(self, key: str, loading: bool, message: Optional[str] = None):
        """
        Set loading state for a component.
        
        Args:
            key: Component identifier
            loading: True if loading, False otherwise
            message: Optional loading message
        """
        self.loading_states[key] = {
            'loading': loading,
            'message': message,
            'timestamp': datetime.utcnow().isoformat(),
        }
    
    def is_loading(self, key: str) -> bool:
        """
        Check if component is loading.
        
        Args:
            key: Component identifier
            
        Returns:
            True if loading, False otherwise
        """
        return self.loading_states.get(key, {}).get('loading', False)
    
    def get_loading_message(self, key: str) -> Optional[str]:
        """
        Get loading message for component.
        
        Args:
            key: Component identifier
            
        Returns:
            Loading message or None
        """
        return self.loading_states.get(key, {}).get('message')

