"""
State Store Integration Helpers
Utilities for migrating components to use StateStore
"""

import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime
from logzero import logger

from .state_store import get_state_store
from .event_bus import get_event_bus


def store_dataframe_state(
    path: str,
    df: pd.DataFrame,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Store pandas DataFrame in StateStore (converts to dict for JSON serialization).
    
    Args:
        path: State path
        df: DataFrame to store
        metadata: Optional metadata
    """
    state_store = get_state_store()
    
    # Convert DataFrame to dict (preserves structure)
    if df.empty:
        state_data = {'empty': True, 'columns': list(df.columns)}
    else:
        state_data = {
            'data': df.to_dict('records'),
            'columns': list(df.columns),
            'index': df.index.tolist(),
            'shape': df.shape,
        }
    
    state_store.update_state(path, state_data, metadata=metadata)


def restore_dataframe_state(path: str) -> pd.DataFrame:
    """
    Restore pandas DataFrame from StateStore.
    
    Args:
        path: State path
        
    Returns:
        Restored DataFrame or empty DataFrame if not found
    """
    state_store = get_state_store()
    state_data = state_store.get_state(path)
    
    if state_data is None or state_data.get('empty'):
        return pd.DataFrame()
    
    try:
        df = pd.DataFrame(state_data.get('data', []))
        if 'index' in state_data and state_data['index']:
            df.index = state_data['index']
        return df
    except Exception as e:
        logger.exception(f"Failed to restore DataFrame from state: {e}")
        return pd.DataFrame()


def emit_state_change_event(path: str, new_value: Any, old_value: Any):
    """
    Emit state change event via Event Bus.
    
    Args:
        path: State path that changed
        new_value: New value
        old_value: Old value
    """
    event_bus = get_event_bus()
    event_bus.publish('state_changed', {
        'path': path,
        'new_value': new_value,
        'old_value': old_value,
        'timestamp': datetime.utcnow().isoformat(),
    })

