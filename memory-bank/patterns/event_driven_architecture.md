# Event-Driven Architecture Pattern

## Overview
The NIFTY Options Trading System uses an event-driven architecture pattern for decoupled communication between components.

## Components

### Event Bus (`engine/event_bus.py`)
- **Purpose**: Centralized publish-subscribe system
- **Pattern**: Singleton pattern for global access
- **Features**:
  - Thread-safe event publishing and subscription
  - Event history (configurable max size)
  - Optional event persistence to log file
  - Wildcard subscriptions (`*`)

### State Store (`engine/state_store.py`)
- **Purpose**: Single source of truth for application state
- **Pattern**: Singleton pattern with nested path-based access
- **Features**:
  - Dot-notation paths (e.g., `trading.positions.order_id`)
  - Change notifications via callbacks
  - State versioning for migrations
  - Metadata tracking (timestamps, source, etc.)

### State Persistence (`engine/state_persistence.py`)
- **Purpose**: Crash recovery via snapshots + event replay
- **Pattern**: Snapshot + Event Log
- **Features**:
  - Periodic state snapshots (configurable interval)
  - Event log replay since last snapshot
  - Automatic cleanup of old snapshots

## Event Types

### Trading Events
- `trade_executed`: Trade placed successfully
- `trade_logged`: Trade written to CSV/DB
- `trade_exit_updated`: Trade exit recorded
- `position_updated`: Position P&L changed
- `position_closed`: Position fully closed
- `signal_detected`: Trading signal generated

### System Events
- `runner_started`: Live runner started
- `runner_stopped`: Live runner stopped
- `daily_loss_breached`: Daily loss limit hit

## Usage Pattern

### Publishing Events
```python
from engine.event_bus import get_event_bus

event_bus = get_event_bus()
event_bus.publish('trade_executed', {
    'order_id': '12345',
    'symbol': 'NIFTY',
    'entry_price': 100.0,
})
```

### Subscribing to Events
```python
def on_trade_executed(event):
    data = event.get('data', {})
    # Handle trade execution
    print(f"Trade executed: {data['order_id']}")

event_bus.subscribe('trade_executed', on_trade_executed)
```

### State Management
```python
from engine.state_store import get_state_store

state_store = get_state_store()

# Update state
state_store.update_state('trading.positions.12345', {
    'order_id': '12345',
    'status': 'open',
})

# Read state
position = state_store.get_state('trading.positions.12345')

# Subscribe to changes
def on_position_change(path, new_value, old_value):
    print(f"Position {path} changed: {old_value} -> {new_value}")

state_store.subscribe('trading.positions.*', on_position_change)
```

## Benefits

1. **Decoupling**: Components don't need direct references
2. **Extensibility**: Easy to add new subscribers
3. **Testability**: Events can be mocked/tested independently
4. **Audit Trail**: Event log provides complete history
5. **Recovery**: State snapshots + replay enable crash recovery

## Configuration

See `config/config.yaml`:
- `event_bus.enabled`: Enable/disable event bus
- `event_bus.persist_events`: Persist events to log file
- `state_store.enabled`: Enable/disable state store
- `state_store.snapshot_interval_minutes`: Snapshot frequency
- `state_store.restore_on_startup`: Restore state on startup

## Migration Notes

- Existing components updated to emit events
- State store integrated for critical state (daily P&L, positions, runner status)
- Dashboard subscribes to events for UI updates
- Backward compatible - existing functionality preserved

