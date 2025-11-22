"""
Event Bus for decoupled communication between components.
Implements publish-subscribe pattern for event-driven architecture.
"""

import threading
import time
from typing import Dict, List, Callable, Any, Optional
from datetime import datetime
from collections import defaultdict
from logzero import logger
import json
import os


class EventBus:
    """
    Centralized event bus for publishing and subscribing to events.
    Thread-safe singleton pattern.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(EventBus, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._event_history: List[Dict[str, Any]] = []
        self._max_history = 1000  # Keep last 1000 events
        self._lock = threading.Lock()
        self._persist_enabled = False
        self._event_log_file = None
        self._initialized = True
        
        logger.info("EventBus initialized")
    
    def subscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Subscribe to events of a specific type.
        
        Args:
            event_type: Type of event to subscribe to (e.g., 'trade_executed', 'position_updated')
            callback: Callback function that receives event data dict
        """
        with self._lock:
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)
                logger.debug(f"Subscribed to event type: {event_type}")
    
    def unsubscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Unsubscribe from events of a specific type.
        
        Args:
            event_type: Type of event to unsubscribe from
            callback: Callback function to remove
        """
        with self._lock:
            if event_type in self._subscribers and callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)
                logger.debug(f"Unsubscribed from event type: {event_type}")
    
    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Publish an event to all subscribers.
        
        Args:
            event_type: Type of event being published
            data: Event data dictionary
        """
        event = {
            'type': event_type,
            'data': data,
            'timestamp': datetime.utcnow().isoformat(),
        }
        
        # Add to history
        with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)
        
        # Persist event if enabled
        if self._persist_enabled and self._event_log_file:
            self._persist_event(event)
        
        # Notify subscribers (outside lock to avoid deadlocks)
        subscribers = []
        with self._lock:
            subscribers = self._subscribers[event_type].copy()
            # Also notify wildcard subscribers (*)
            if '*' in self._subscribers:
                subscribers.extend(self._subscribers['*'])
        
        # Call subscribers (outside lock)
        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.exception(f"Error in event subscriber for {event_type}: {e}")
        
        logger.debug(f"Published event: {event_type} to {len(subscribers)} subscriber(s)")
    
    def get_event_history(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent event history.
        
        Args:
            event_type: Filter by event type (None for all)
            limit: Maximum number of events to return
            
        Returns:
            List of event dictionaries
        """
        with self._lock:
            history = self._event_history.copy()
        
        if event_type:
            history = [e for e in history if e['type'] == event_type]
        
        return history[-limit:]
    
    def enable_persistence(self, event_log_file: str = "logs/events.log") -> None:
        """
        Enable event persistence to file for audit trail.
        
        Args:
            event_log_file: Path to event log file
        """
        self._event_log_file = event_log_file
        self._persist_enabled = True
        
        # Ensure directory exists
        directory = os.path.dirname(event_log_file)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        
        logger.info(f"Event persistence enabled: {event_log_file}")
    
    def _persist_event(self, event: Dict[str, Any]) -> None:
        """
        Persist event to log file.
        
        Args:
            event: Event dictionary to persist
        """
        if not self._event_log_file:
            return
        
        try:
            with open(self._event_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            logger.warning(f"Failed to persist event: {e}")
    
    def clear_history(self) -> None:
        """Clear event history."""
        with self._lock:
            self._event_history.clear()
        logger.info("Event history cleared")
    
    def get_subscriber_count(self, event_type: Optional[str] = None) -> int:
        """
        Get number of subscribers for an event type.
        
        Args:
            event_type: Event type (None for total count)
            
        Returns:
            Number of subscribers
        """
        with self._lock:
            if event_type:
                return len(self._subscribers.get(event_type, []))
            return sum(len(callbacks) for callbacks in self._subscribers.values())


# Convenience function to get the singleton instance
def get_event_bus() -> EventBus:
    """Get the singleton EventBus instance."""
    return EventBus()

