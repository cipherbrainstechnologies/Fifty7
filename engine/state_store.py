"""
State Store for centralized state management.
Single source of truth for application state with persistence support.
"""

import threading
import copy
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from logzero import logger
import json
import os


class StateStore:
    """
    Centralized state store with thread-safe access and change notifications.
    Implements single source of truth pattern.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(StateStore, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # State storage (nested dict structure)
        self._state: Dict[str, Any] = {}
        
        # Subscribers for state changes (path -> list of callbacks)
        self._subscribers: Dict[str, List[Callable]] = {}
        
        # State version for migrations
        self._version = 1
        
        # Metadata for state entries
        self._metadata: Dict[str, Dict[str, Any]] = {}
        
        self._lock = threading.Lock()
        self._initialized = True
        
        logger.info("StateStore initialized")
    
    def get_state(self, path: Optional[str] = None) -> Any:
        """
        Get state at a specific path or entire state.
        
        Args:
            path: Dot-separated path (e.g., 'trading.positions') or None for entire state
            
        Returns:
            State value at path or entire state dict
        """
        with self._lock:
            if path is None:
                return copy.deepcopy(self._state)
            
            # Navigate nested dict using dot notation
            parts = path.split('.')
            current = self._state
            
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            
            return copy.deepcopy(current)
    
    def update_state(
        self,
        path: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Update state at a specific path.
        
        Args:
            path: Dot-separated path (e.g., 'trading.positions')
            value: Value to set
            metadata: Optional metadata (timestamp, source, etc.)
        """
        with self._lock:
            # Navigate/create nested structure
            parts = path.split('.')
            current = self._state
            
            for i, part in enumerate(parts[:-1]):
                if part not in current:
                    current[part] = {}
                current = current[part]
            
            # Set value
            old_value = current.get(parts[-1])
            current[parts[-1]] = copy.deepcopy(value)
            
            # Store metadata
            if metadata is None:
                metadata = {}
            metadata.setdefault('updated_at', datetime.utcnow().isoformat())
            metadata.setdefault('version', self._version)
            self._metadata[path] = metadata
            
            # Notify subscribers
            self._notify_subscribers(path, value, old_value)
        
        logger.debug(f"State updated at path: {path}")
    
    def subscribe(
        self,
        path: str,
        callback: Callable[[str, Any, Any], None]
    ) -> None:
        """
        Subscribe to state changes at a specific path.
        
        Args:
            path: Dot-separated path or '*' for all changes
            callback: Callback function(path, new_value, old_value)
        """
        with self._lock:
            if path not in self._subscribers:
                self._subscribers[path] = []
            if callback not in self._subscribers[path]:
                self._subscribers[path].append(callback)
                logger.debug(f"Subscribed to state path: {path}")
    
    def unsubscribe(
        self,
        path: str,
        callback: Callable[[str, Any, Any], None]
    ) -> None:
        """
        Unsubscribe from state changes.
        
        Args:
            path: Path to unsubscribe from
            callback: Callback function to remove
        """
        with self._lock:
            if path in self._subscribers and callback in self._subscribers[path]:
                self._subscribers[path].remove(callback)
                logger.debug(f"Unsubscribed from state path: {path}")
    
    def _notify_subscribers(self, path: str, new_value: Any, old_value: Any) -> None:
        """
        Notify subscribers of state changes.
        
        Args:
            path: Path that changed
            new_value: New value
            old_value: Old value
        """
        # Get subscribers (outside lock to avoid deadlocks)
        subscribers = []
        with self._lock:
            # Exact path match
            if path in self._subscribers:
                subscribers.extend(self._subscribers[path])
            
            # Wildcard subscribers
            if '*' in self._subscribers:
                subscribers.extend(self._subscribers['*'])
            
            # Parent path subscribers (e.g., 'trading' subscribes to 'trading.positions')
            for sub_path, callbacks in self._subscribers.items():
                if sub_path != '*' and sub_path != path and path.startswith(sub_path + '.'):
                    subscribers.extend(callbacks)
        
        # Call subscribers
        for callback in subscribers:
            try:
                callback(path, new_value, old_value)
            except Exception as e:
                logger.exception(f"Error in state subscriber for {path}: {e}")
    
    def delete_state(self, path: str) -> None:
        """
        Delete state at a specific path.
        
        Args:
            path: Dot-separated path to delete
        """
        with self._lock:
            parts = path.split('.')
            current = self._state
            
            for i, part in enumerate(parts[:-1]):
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return  # Path doesn't exist
            
            # Delete the key
            if isinstance(current, dict) and parts[-1] in current:
                old_value = current.pop(parts[-1])
                if path in self._metadata:
                    del self._metadata[path]
                self._notify_subscribers(path, None, old_value)
                logger.debug(f"State deleted at path: {path}")
    
    def get_metadata(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a state path.
        
        Args:
            path: Dot-separated path
            
        Returns:
            Metadata dictionary or None
        """
        with self._lock:
            return copy.deepcopy(self._metadata.get(path))
    
    def clear_state(self) -> None:
        """Clear all state (use with caution)."""
        with self._lock:
            self._state.clear()
            self._metadata.clear()
        logger.warning("State store cleared")
    
    def get_snapshot(self) -> Dict[str, Any]:
        """
        Get a complete snapshot of state and metadata.
        
        Returns:
            Dictionary with 'state', 'metadata', and 'version'
        """
        with self._lock:
            return {
                'state': copy.deepcopy(self._state),
                'metadata': copy.deepcopy(self._metadata),
                'version': self._version,
                'snapshot_at': datetime.utcnow().isoformat(),
            }
    
    def restore_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """
        Restore state from a snapshot.
        
        Args:
            snapshot: Snapshot dictionary from get_snapshot()
        """
        with self._lock:
            if 'state' in snapshot:
                self._state = copy.deepcopy(snapshot['state'])
            if 'metadata' in snapshot:
                self._metadata = copy.deepcopy(snapshot['metadata'])
            if 'version' in snapshot:
                self._version = snapshot['version']
        
        logger.info(f"State restored from snapshot (version: {self._version})")
    
    def set_version(self, version: int) -> None:
        """
        Set state version for migrations.
        
        Args:
            version: Version number
        """
        with self._lock:
            self._version = version
        logger.info(f"State version set to: {version}")


# Convenience function to get the singleton instance
def get_state_store() -> StateStore:
    """Get the singleton StateStore instance."""
    return StateStore()

