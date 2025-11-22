"""
Write-Through Cache Pattern Implementation
Ensures state consistency with async persistence
"""

import threading
import queue
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from logzero import logger

from .state_store import get_state_store
from .event_bus import get_event_bus


class WriteThroughCache:
    """
    Implements write-through cache pattern with async persistence.
    """
    
    def __init__(
        self,
        state_store=None,
        event_bus=None,
        persist_func: Optional[Callable[[str, Any], None]] = None,
    ):
        """
        Initialize write-through cache.
        
        Args:
            state_store: StateStore instance (optional)
            event_bus: EventBus instance (optional)
            persist_func: Function to persist state (async)
        """
        self.state_store = state_store or get_state_store()
        self.event_bus = event_bus or get_event_bus()
        self.persist_func = persist_func
        
        self._write_queue = queue.Queue()
        self._persist_thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
    
    def start(self):
        """Start async persistence thread."""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        self._persist_thread = threading.Thread(target=self._persist_loop, daemon=True)
        self._persist_thread.start()
        logger.info("Write-through cache persistence thread started")
    
    def stop(self):
        """Stop async persistence thread."""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        if self._persist_thread and self._persist_thread.is_alive():
            self._persist_thread.join(timeout=5.0)
        logger.info("Write-through cache persistence thread stopped")
    
    def write(
        self,
        path: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
        sync: bool = False,
    ) -> None:
        """
        Write state through cache (write-through pattern).
        
        Args:
            path: State path
            value: Value to write
            metadata: Optional metadata
            sync: If True, persist synchronously (for critical writes)
        """
        # 1. Write to StateStore (synchronous - always immediate)
        self.state_store.update_state(path, value, metadata=metadata)
        
        # 2. Emit state change event
        self.event_bus.publish('state_changed', {
            'path': path,
            'value': value,
            'metadata': metadata,
            'timestamp': datetime.utcnow().isoformat(),
        })
        
        # 3. Persist (synchronous for critical, async for non-critical)
        if sync or self.persist_func is None:
            # Critical write - persist immediately
            if self.persist_func:
                try:
                    self.persist_func(path, value)
                except Exception as e:
                    logger.exception(f"Sync persistence failed for {path}: {e}")
        else:
            # Non-critical write - queue for async persistence
            self._write_queue.put((path, value, metadata))
    
    def _persist_loop(self):
        """Background thread for async persistence."""
        while self._running and not self._stop_event.is_set():
            try:
                # Get queued writes
                try:
                    path, value, metadata = self._write_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Persist
                if self.persist_func:
                    try:
                        self.persist_func(path, value)
                    except Exception as e:
                        logger.exception(f"Async persistence failed for {path}: {e}")
                
            except Exception as e:
                logger.exception(f"Error in persist loop: {e}")
    
    def read(self, path: Optional[str] = None, max_age_seconds: Optional[float] = None) -> Any:
        """
        Read state from cache with optional staleness check.
        
        Args:
            path: State path (None for entire state)
            max_age_seconds: Maximum age before considered stale
            
        Returns:
            State value or None if stale
        """
        state = self.state_store.get_state(path)
        
        if max_age_seconds and state is not None:
            metadata = self.state_store.get_metadata(path)
            if metadata:
                updated_at = metadata.get('updated_at')
                if updated_at:
                    try:
                        from datetime import datetime
                        updated = datetime.fromisoformat(updated_at)
                        age = (datetime.utcnow() - updated).total_seconds()
                        if age > max_age_seconds:
                            # State is stale - trigger refresh
                            self.event_bus.publish('state_stale', {
                                'path': path,
                                'age_seconds': age,
                                'max_age_seconds': max_age_seconds,
                            })
                            return None
                    except Exception:
                        pass
        
        return state


# Global instance
_write_through_cache: Optional[WriteThroughCache] = None


def get_write_through_cache() -> WriteThroughCache:
    """Get or create WriteThroughCache instance."""
    global _write_through_cache
    if _write_through_cache is None:
        _write_through_cache = WriteThroughCache()
        _write_through_cache.start()
    return _write_through_cache

