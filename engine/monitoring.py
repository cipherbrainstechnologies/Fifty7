"""
Monitoring and metrics for Event Bus and State Store
"""

import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from collections import deque
from logzero import logger

from .event_bus import get_event_bus
from .state_store import get_state_store


class EventBusMetrics:
    """
    Metrics collector for Event Bus.
    """
    
    def __init__(self, event_bus=None, window_size: int = 1000):
        """
        Initialize metrics collector.
        
        Args:
            event_bus: EventBus instance (optional)
            window_size: Number of recent events to track
        """
        self.event_bus = event_bus or get_event_bus()
        self.window_size = window_size
        
        self.event_counts: Dict[str, int] = {}
        self.event_timestamps: deque = deque(maxlen=window_size)
        self.total_events = 0
        self.start_time = datetime.utcnow()
    
    def record_event(self, event_type: str):
        """Record an event for metrics."""
        self.event_counts[event_type] = self.event_counts.get(event_type, 0) + 1
        self.event_timestamps.append(time.time())
        self.total_events += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics.
        
        Returns:
            Metrics dictionary
        """
        now = time.time()
        window_start = now - 60  # Last 60 seconds
        
        recent_events = sum(1 for ts in self.event_timestamps if ts >= window_start)
        events_per_second = recent_events / 60.0 if recent_events > 0 else 0.0
        
        uptime = (datetime.utcnow() - self.start_time).total_seconds()
        
        return {
            'total_events': self.total_events,
            'events_per_second': events_per_second,
            'events_last_minute': recent_events,
            'event_counts': self.event_counts.copy(),
            'subscriber_count': self.event_bus.get_subscriber_count(),
            'uptime_seconds': uptime,
            'timestamp': datetime.utcnow().isoformat(),
        }


class StateStoreMetrics:
    """
    Metrics collector for State Store.
    """
    
    def __init__(self, state_store=None):
        """
        Initialize metrics collector.
        
        Args:
            state_store: StateStore instance (optional)
        """
        self.state_store = state_store or get_state_store()
        
        self.read_count = 0
        self.write_count = 0
        self.read_times: deque = deque(maxlen=1000)
        self.write_times: deque = deque(maxlen=1000)
        self.start_time = datetime.utcnow()
    
    def record_read(self, duration: float):
        """Record a read operation."""
        self.read_count += 1
        self.read_times.append(duration)
    
    def record_write(self, duration: float):
        """Record a write operation."""
        self.write_count += 1
        self.write_times.append(duration)
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics.
        
        Returns:
            Metrics dictionary
        """
        avg_read_time = sum(self.read_times) / len(self.read_times) if self.read_times else 0.0
        avg_write_time = sum(self.write_times) / len(self.write_times) if self.write_times else 0.0
        
        max_read_time = max(self.read_times) if self.read_times else 0.0
        max_write_time = max(self.write_times) if self.write_times else 0.0
        
        uptime = (datetime.utcnow() - self.start_time).total_seconds()
        
        return {
            'read_count': self.read_count,
            'write_count': self.write_count,
            'avg_read_time_ms': avg_read_time * 1000,
            'avg_write_time_ms': avg_write_time * 1000,
            'max_read_time_ms': max_read_time * 1000,
            'max_write_time_ms': max_write_time * 1000,
            'uptime_seconds': uptime,
            'timestamp': datetime.utcnow().isoformat(),
        }


class SystemMonitor:
    """
    Combined system monitor for Event Bus and State Store.
    """
    
    def __init__(self):
        self.event_metrics = EventBusMetrics()
        self.state_metrics = StateStoreMetrics()
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """
        Get all system metrics.
        
        Returns:
            Combined metrics dictionary
        """
        return {
            'event_bus': self.event_metrics.get_metrics(),
            'state_store': self.state_metrics.get_metrics(),
            'timestamp': datetime.utcnow().isoformat(),
        }

