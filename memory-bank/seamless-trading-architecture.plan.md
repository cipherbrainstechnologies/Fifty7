# Seamless Algo Trading Architecture - Best Practices Plan

## Current Architecture Analysis

### Strengths

- Background threads for non-blocking execution (`LiveStrategyRunner`, `ActivePnlTracker`)
- Shared state via Streamlit session state
- Multiple data sources with fallbacks (CSV, Postgres, memory)
- Websocket tick streaming for real-time quotes
- Lock-based synchronization for shared data structures

### Current Limitations

- Streamlit is request-response based (no true push)
- Auto-refresh uses `st.rerun()` which reloads entire page
- Multiple data sources need manual synchronization
- Race conditions possible between threads and UI reads
- No event-driven architecture for state changes
- State persistence limited to CSV/DB (memory state lost on restart)

## Recommended Architecture Patterns

### 1. Event-Driven State Management

**Pattern: Centralized Event Bus**

- Create an event bus (`engine/event_bus.py`) for decoupled communication
- Backend components emit events (trade_executed, position_updated, signal_detected)
- Frontend subscribes to events and updates UI reactively
- Benefits: Loose coupling, easier testing, extensible

**Implementation:**

```
EventBus (singleton)
  - subscribe(event_type, callback)
  - publish(event_type, data)
  - persist_events() for audit trail
```

### 2. State Store Pattern

**Pattern: Single Source of Truth**

- Create `engine/state_store.py` as centralized state manager
- All components read/write through state store
- State store handles persistence, versioning, and access control
- Frontend reads from state store snapshot (no direct backend access)

**Structure:**

```python
StateStore:
  - get_state(path) -> current snapshot
  - update_state(path, value, metadata)
  - subscribe(path, callback) -> changes only
  - persist() -> CSV/DB sync
  - restore() -> bootstrap from persistence
```

### 3. Real-Time Synchronization Strategy

**Pattern: Hybrid Push-Pull Model**

**Phase 1: Immediate (Critical Updates)**

- WebSocket server for real-time push notifications
- Events: trade_executed, position_closed, daily_loss_breached
- Streamlit listens via `st.websocket` or SSE (Server-Sent Events)
- Zero-latency for critical state changes

**Phase 2: Fast Polling (Status Updates)**

- Active P&L: 5s interval (current)
- Runner status: 10s interval
- Market data: 30s interval (configurable)

**Phase 3: Lazy Loading (Historical Data)**

- Trade history: Load on demand
- Backtest results: Cached with TTL
- Analytics: Pre-computed aggregations

### 4. Data Consistency Pattern

**Pattern: Write-Through Cache with Eventual Consistency**

**Write Path:**

1. Backend writes to StateStore
2. StateStore persists to DB/CSV (async)
3. StateStore emits event
4. Frontend receives event and updates UI

**Read Path:**

1. Frontend requests state from StateStore
2. StateStore returns latest snapshot
3. If stale, trigger refresh

**Consistency Guarantees:**

- Critical writes: Synchronous (trade execution, position updates)
- Non-critical writes: Asynchronous (logging, analytics)
- Reads: Eventually consistent with max age metadata

### 5. Frontend State Management

**Pattern: Streamlit State + External State Store**

**Current:** All state in `st.session_state`

**Improved:** Hybrid approach

```
Session State (ephemeral):
  - UI preferences
  - User inputs
  - Component state
  
External State Store (persistent):
  - Trading state
  - Positions
  - P&L data
  - Market data
```

**Benefits:**

- State survives Streamlit reruns
- Multiple dashboard instances share state
- Better debugging and audit trails

## Implementation Recommendations

### Priority 1: Event Bus Foundation

**Files to Create:**

- `engine/event_bus.py` - Central event system
- `engine/state_store.py` - Centralized state management

**Files to Modify:**

- `engine/live_runner.py` - Emit events on state changes
- `engine/trade_logger.py` - Emit trade events
- `dashboard/ui_frontend.py` - Subscribe to events

**Changes:**

1. Replace direct state mutations with event publishing
2. Frontend subscribes to events and updates UI
3. Add event persistence for audit trail

### Priority 2: State Store Integration

**Changes:**

1. Migrate critical state to StateStore
2. Keep UI preferences in session state
3. Add state restore on startup
4. Implement state versioning for migrations

### Priority 3: Real-Time Push Updates

**Option A: Server-Sent Events (Recommended for Streamlit)**

- Create SSE endpoint in separate thread
- Streamlit polls SSE endpoint every 1-2 seconds
- Lower overhead than WebSocket for one-way updates

**Option B: WebSocket Bridge**

- Create FastAPI/Flask server alongside Streamlit
- WebSocket for bidirectional communication
- Streamlit iframe or separate tab for real-time updates

**Option C: Enhanced Auto-Refresh (Current + Smart)**

- Keep current auto-refresh mechanism
- Add smart refresh triggers based on state changes
- Reduce refresh frequency when no changes detected

### Priority 4: State Persistence & Recovery

**Pattern: State Snapshot + Event Log**

**Implementation:**

1. Periodic state snapshots (every 5 minutes)
2. Event log for incremental updates
3. On restart: Load latest snapshot + replay events
4. Reconciliation with broker for consistency

**Files:**

- `engine/state_persistence.py` - Snapshot and replay logic
- `data/state/` - State snapshots directory
- `logs/events.log` - Event log

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Streamlit)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Dashboard  │  │   Controls   │  │   Analytics  │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
└─────────┼──────────────────┼──────────────────┼─────────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
          ┌──────────────────▼──────────────────┐
          │      State Store (Single Source)     │
          │  ┌────────────────────────────────┐ │
          │  │  - Trading State               │ │
          │  │  - Positions                   │ │
          │  │  - P&L Data                    │ │
          │  │  - Market Data                 │ │
          │  └────────────────────────────────┘ │
          └──────────────────┬──────────────────┘
                             │
          ┌──────────────────▼──────────────────┐
          │        Event Bus (Decoupled)         │
          │  ┌────────────────────────────────┐ │
          │  │  - trade_executed              │ │
          │  │  - position_updated            │ │
          │  │  - signal_detected             │ │
          │  │  - state_changed               │ │
          │  └────────────────────────────────┘ │
          └──────────────────┬──────────────────┘
                             │
    ┌────────────────────────┼────────────────────────┐
    │                        │                        │
┌───▼────┐           ┌───────▼───────┐      ┌────────▼─────┐
│ Runner │           │ Trade Logger  │      │ Position Mon │
└───┬────┘           └───────┬───────┘      └────────┬─────┘
    │                        │                       │
    └────────────────────────┼───────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Persistence    │
                    │  (DB + CSV)     │
                    └─────────────────┘
```

## Best Practices Checklist

### Backend

- [ ] All state mutations go through StateStore
- [ ] All significant events published to EventBus
- [ ] Thread-safe operations with proper locking
- [ ] State snapshots for crash recovery
- [ ] Event logging for audit trail

### Frontend

- [ ] Subscribe to relevant events only
- [ ] Debounce/throttle rapid updates
- [ ] Handle stale state gracefully
- [ ] Show loading states during refreshes
- [ ] Persist UI preferences separately

### Synchronization

- [ ] Critical updates pushed immediately
- [ ] Status updates polled at configured intervals
- [ ] Historical data loaded on demand
- [ ] State reconciliation on startup
- [ ] Broker sync for position consistency

### Error Handling

- [ ] Retry logic for transient failures
- [ ] Fallback to cached state on errors
- [ ] User notifications for critical errors
- [ ] Graceful degradation when services unavailable

## Migration Path

### Phase 1: Foundation (Week 1)

1. Implement EventBus
2. Implement StateStore with in-memory backend
3. Integrate with LiveRunner (emit events)
4. Frontend subscribes to events

### Phase 2: Persistence (Week 2)

1. Add state snapshot mechanism
2. Add event logging
3. Implement state restore on startup
4. Add state versioning

### Phase 3: Real-Time (Week 3)

1. Implement SSE endpoint or WebSocket bridge
2. Frontend consumes real-time updates
3. Optimize refresh intervals
4. Add smart refresh triggers

### Phase 4: Optimization (Week 4)

1. Performance tuning
2. Reduce unnecessary updates
3. Add caching layers
4. Comprehensive testing

## Key Files to Modify

### New Files

- `engine/event_bus.py` - Event system
- `engine/state_store.py` - State management
- `engine/state_persistence.py` - State snapshots and restore

### Modified Files

- `engine/live_runner.py` - Emit events, use StateStore
- `engine/trade_logger.py` - Emit trade events
- `engine/position_monitor.py` - Emit position events
- `dashboard/ui_frontend.py` - Subscribe to events, read from StateStore

### Configuration

- `config/config.yaml` - Add state store and event bus config
- State persistence directory structure

## Success Metrics

1. **Latency:** Critical updates visible in < 2 seconds
2. **Consistency:** Zero data loss on restart/recovery
3. **Performance:** UI remains responsive with < 100ms render time
4. **Reliability:** 99.9% uptime for state store and event bus
5. **Maintainability:** New features can be added without touching existing code