"""
State Persistence for snapshots and event log replay.
Implements state snapshot + event log pattern for crash recovery.
"""

import os
import json
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from logzero import logger
import glob

from .state_store import get_state_store
from .event_bus import get_event_bus


class StatePersistence:
    """
    Manages state snapshots and event log replay for recovery.
    """
    
    def __init__(
        self,
        snapshot_dir: str = "data/state",
        snapshot_interval_minutes: int = 5,
        max_snapshots: int = 100
    ):
        """
        Initialize StatePersistence.
        
        Args:
            snapshot_dir: Directory for state snapshots
            snapshot_interval_minutes: Interval between snapshots
            max_snapshots: Maximum number of snapshots to keep
        """
        self.snapshot_dir = snapshot_dir
        self.snapshot_interval = timedelta(minutes=snapshot_interval_minutes)
        self.max_snapshots = max_snapshots
        self._last_snapshot_time: Optional[datetime] = None
        self._lock = threading.Lock()
        
        # Ensure directory exists
        if not os.path.exists(snapshot_dir):
            os.makedirs(snapshot_dir, exist_ok=True)
        
        logger.info(f"StatePersistence initialized (snapshot_dir: {snapshot_dir})")
    
    def save_snapshot(self, force: bool = False) -> Optional[str]:
        """
        Save current state snapshot.
        
        Args:
            force: Force snapshot even if interval hasn't elapsed
            
        Returns:
            Path to saved snapshot file or None
        """
        now = datetime.utcnow()
        
        with self._lock:
            # Check if interval has elapsed
            if not force and self._last_snapshot_time:
                elapsed = now - self._last_snapshot_time
                if elapsed < self.snapshot_interval:
                    return None
            
            # Get state snapshot
            state_store = get_state_store()
            snapshot = state_store.get_snapshot()
            
            # Generate filename with timestamp
            timestamp = now.strftime('%Y%m%d_%H%M%S')
            filename = f"snapshot_{timestamp}.json"
            filepath = os.path.join(self.snapshot_dir, filename)
            
            # Save snapshot
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(snapshot, f, indent=2, default=str)
                
                self._last_snapshot_time = now
                
                # Cleanup old snapshots
                self._cleanup_old_snapshots()
                
                logger.info(f"State snapshot saved: {filepath}")
                return filepath
                
            except Exception as e:
                logger.exception(f"Failed to save snapshot: {e}")
                return None
    
    def load_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        Load the most recent state snapshot.
        
        Returns:
            Snapshot dictionary or None
        """
        try:
            # Find all snapshot files
            pattern = os.path.join(self.snapshot_dir, "snapshot_*.json")
            snapshots = glob.glob(pattern)
            
            if not snapshots:
                logger.warning("No snapshots found")
                return None
            
            # Sort by modification time (newest first)
            snapshots.sort(key=os.path.getmtime, reverse=True)
            latest = snapshots[0]
            
            # Load snapshot
            with open(latest, 'r', encoding='utf-8') as f:
                snapshot = json.load(f)
            
            logger.info(f"Loaded snapshot: {latest}")
            return snapshot
            
        except Exception as e:
            logger.exception(f"Failed to load snapshot: {e}")
            return None
    
    def restore_from_snapshot(self, snapshot: Optional[Dict[str, Any]] = None) -> bool:
        """
        Restore state from snapshot.
        
        Args:
            snapshot: Snapshot dictionary (None to load latest)
            
        Returns:
            True if restored successfully
        """
        if snapshot is None:
            snapshot = self.load_latest_snapshot()
        
        if snapshot is None:
            logger.warning("No snapshot available for restore")
            return False
        
        try:
            state_store = get_state_store()
            state_store.restore_snapshot(snapshot)
            logger.info("State restored from snapshot")
            return True
            
        except Exception as e:
            logger.exception(f"Failed to restore from snapshot: {e}")
            return False
    
    def _cleanup_old_snapshots(self) -> None:
        """Remove old snapshots beyond max_snapshots limit."""
        try:
            pattern = os.path.join(self.snapshot_dir, "snapshot_*.json")
            snapshots = glob.glob(pattern)
            
            if len(snapshots) <= self.max_snapshots:
                return
            
            # Sort by modification time (oldest first)
            snapshots.sort(key=os.path.getmtime)
            
            # Remove oldest snapshots
            to_remove = snapshots[:-self.max_snapshots]
            for filepath in to_remove:
                try:
                    os.remove(filepath)
                    logger.debug(f"Removed old snapshot: {filepath}")
                except Exception as e:
                    logger.warning(f"Failed to remove snapshot {filepath}: {e}")
                    
        except Exception as e:
            logger.warning(f"Failed to cleanup snapshots: {e}")
    
    def replay_events(
        self,
        event_log_file: str,
        since_timestamp: Optional[str] = None
    ) -> int:
        """
        Replay events from event log file.
        
        Args:
            event_log_file: Path to event log file
            since_timestamp: Only replay events after this timestamp (ISO format)
            
        Returns:
            Number of events replayed
        """
        if not os.path.exists(event_log_file):
            logger.warning(f"Event log file not found: {event_log_file}")
            return 0
        
        event_bus = get_event_bus()
        replayed = 0
        
        try:
            with open(event_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        event = json.loads(line)
                        
                        # Filter by timestamp if provided
                        if since_timestamp:
                            event_ts = event.get('timestamp', '')
                            if event_ts <= since_timestamp:
                                continue
                        
                        # Replay event (but don't persist again)
                        event_type = event.get('type')
                        data = event.get('data', {})
                        
                        if event_type:
                            # Temporarily disable persistence to avoid double-logging
                            was_enabled = event_bus._persist_enabled
                            event_bus._persist_enabled = False
                            
                            try:
                                event_bus.publish(event_type, data)
                            finally:
                                event_bus._persist_enabled = was_enabled
                            
                            replayed += 1
                            
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in event log: {line[:100]}")
                        continue
                    except Exception as e:
                        logger.warning(f"Error replaying event: {e}")
                        continue
            
            logger.info(f"Replayed {replayed} events from {event_log_file}")
            return replayed
            
        except Exception as e:
            logger.exception(f"Failed to replay events: {e}")
            return 0
    
    def restore_with_replay(
        self,
        snapshot: Optional[Dict[str, Any]] = None,
        event_log_file: str = "logs/events.log"
    ) -> bool:
        """
        Restore state from snapshot and replay events since snapshot.
        
        Args:
            snapshot: Snapshot dictionary (None to load latest)
            event_log_file: Path to event log file
            
        Returns:
            True if restored successfully
        """
        # Restore snapshot
        if not self.restore_from_snapshot(snapshot):
            return False
        
        # Get snapshot timestamp
        if snapshot is None:
            snapshot = self.load_latest_snapshot()
        
        snapshot_timestamp = None
        if snapshot and 'snapshot_at' in snapshot:
            snapshot_timestamp = snapshot['snapshot_at']
        
        # Replay events since snapshot
        if snapshot_timestamp:
            self.replay_events(event_log_file, since_timestamp=snapshot_timestamp)
        
        return True


# Convenience function
def get_state_persistence(
    snapshot_dir: str = "data/state",
    snapshot_interval_minutes: int = 5
) -> StatePersistence:
    """Get or create StatePersistence instance."""
    return StatePersistence(
        snapshot_dir=snapshot_dir,
        snapshot_interval_minutes=snapshot_interval_minutes
    )

