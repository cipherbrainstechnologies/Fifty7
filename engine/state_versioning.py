"""
State Versioning System for migrations
"""

from typing import Dict, Any, Optional, Callable
from datetime import datetime
from logzero import logger

from .state_store import get_state_store


class StateVersionManager:
    """
    Manages state versioning and migrations.
    """
    
    def __init__(self, state_store=None):
        """
        Initialize state version manager.
        
        Args:
            state_store: StateStore instance (optional)
        """
        self.state_store = state_store or get_state_store()
        self.migrations: Dict[int, Callable] = {}
        self.current_version = 1
    
    def register_migration(self, from_version: int, to_version: int, migration_func: Callable):
        """
        Register a migration function.
        
        Args:
            from_version: Source version
            to_version: Target version
            migration_func: Function to perform migration
        """
        key = (from_version, to_version)
        self.migrations[key] = migration_func
        logger.info(f"Registered migration: {from_version} -> {to_version}")
    
    def migrate(self, target_version: Optional[int] = None) -> bool:
        """
        Migrate state to target version.
        
        Args:
            target_version: Target version (None for latest)
            
        Returns:
            True if migration successful
        """
        if target_version is None:
            target_version = self.current_version
        
        stored_version = self.state_store.get_state('_version') or 1
        
        if stored_version >= target_version:
            logger.info(f"State already at version {stored_version} (target: {target_version})")
            return True
        
        try:
            # Perform step-by-step migration
            current = stored_version
            while current < target_version:
                next_version = current + 1
                migration_key = (current, next_version)
                
                if migration_key in self.migrations:
                    logger.info(f"Migrating state from {current} to {next_version}")
                    migration_func = self.migrations[migration_key]
                    migration_func(self.state_store)
                    current = next_version
                else:
                    logger.warning(f"No migration found: {current} -> {next_version}")
                    # Skip to next version
                    current = next_version
            
            # Update version
            self.state_store.update_state('_version', target_version, metadata={
                'migrated_at': datetime.utcnow().isoformat(),
                'from_version': stored_version,
            })
            
            logger.info(f"State migrated from {stored_version} to {target_version}")
            return True
            
        except Exception as e:
            logger.exception(f"Migration failed: {e}")
            return False
    
    def check_compatibility(self) -> bool:
        """
        Check if stored state version is compatible with current version.
        
        Returns:
            True if compatible, False otherwise
        """
        stored_version = self.state_store.get_state('_version') or 1
        return stored_version <= self.current_version

