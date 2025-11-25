# NIFTY LTP Tick-by-Tick Update Fixes

## Problem
NIFTY LTP was not updating in real-time - required manual refresh to see price changes. UI rendering was also slow.

## Root Causes Identified

1. **Tick Update Throttling**: Tick streamer was only publishing events when LTP changed, not periodically
2. **UI Rerun Throttling**: Frontend was throttling reruns to 2 seconds for NIFTY
3. **WebSocket Event Flow**: Events were being published but UI wasn't refreshing frequently enough
4. **UI Performance**: Too many reruns causing slow rendering

## Fixes Applied

### 1. Tick Streamer Optimization (`engine/tick_stream.py`)

**Changes:**
- Added throttling variables for tick_update events:
  - `_tick_event_interval = 1.0` seconds (minimum interval for options)
  - `_nifty_event_interval = 0.5` seconds (faster updates for NIFTY index)
  - `_last_tick_event_ts`: Dictionary to track last publish time per symbol

**Behavior:**
- **NIFTY Index**: Publishes tick_update events every **0.5 seconds** OR when LTP changes (whichever comes first)
- **Options**: Publishes only when LTP changes (to reduce spam)
- Ensures continuous updates even when price doesn't change

### 2. Frontend UI Optimization (`dashboard/ui_frontend.py`)

**Changes:**
- Reduced NIFTY rerun throttling from 2 seconds to **1 second**
- Improved cached LTP value usage:
  - Uses cached `_latest_nifty_ltp` if less than 5 seconds old
  - Falls back to tick streamer cache if WebSocket value unavailable
- Added debug logging for NIFTY LTP updates

**WebSocket Event Handler:**
```python
# NIFTY: Rerun every 1 second max for faster updates
if is_nifty:
    if now - last_tick_rerun >= 1.0:
        st.session_state._last_tick_rerun = now
        st.session_state._websocket_trigger_rerun = True
        # Store latest NIFTY LTP immediately
        st.session_state._latest_nifty_ltp = float(ltp)
        st.session_state._latest_nifty_ltp_timestamp = now
```

### 3. Data Flow

```
SmartAPI WebSocket
    ↓ (tick-by-tick, every second or faster)
LiveTickStreamer._on_data()
    ↓ (publishes every 0.5s for NIFTY)
Event Bus.publish('tick_update', {...})
    ↓ (subscribed)
WebSocket Server._subscribe_to_events()
    ↓ (broadcasts to clients)
Frontend WebSocket Client.on_websocket_event()
    ↓ (triggers rerun every 1s for NIFTY)
UI Refresh → NIFTY LTP Updated
```

## Expected Behavior After Fixes

### NIFTY Index LTP
- ✅ Updates **every 0.5-1 second** automatically
- ✅ No manual refresh required
- ✅ Shows latest price from tick streamer
- ✅ Falls back to cached value if WebSocket delayed

### Option LTP (During Trades)
- ✅ Updates when price changes
- ✅ Subscribed automatically when trade opens
- ✅ Real-time P&L calculation

### UI Performance
- ✅ Throttled reruns prevent excessive refreshes
- ✅ Cached values displayed immediately
- ✅ Background refresh for other data (every 10s)

## Testing Checklist

- [ ] NIFTY LTP updates automatically every 1 second
- [ ] No manual refresh needed to see price changes
- [ ] UI remains responsive (no lag/blur)
- [ ] Option LTP updates when trade is open
- [ ] WebSocket connection stays active
- [ ] Fallback to tick streamer cache works if WebSocket fails

## Troubleshooting

### If NIFTY LTP still not updating:

1. **Check WebSocket Connection**:
   - Open browser DevTools → Network → WS tab
   - Verify WebSocket connection is established
   - Check for connection errors

2. **Check Tick Streamer Status**:
   - Look for log messages: `📊 NIFTY tick_update: LTP=...`
   - Verify SmartAPI WebSocket is connected
   - Check `tick_streamer.get_status()` in dashboard

3. **Check Event Bus**:
   - Verify events are being published (check logs)
   - Check Event Bus subscriber count

4. **Check Frontend**:
   - Verify WebSocket client is initialized
   - Check for JavaScript errors in console
   - Verify `_websocket_trigger_rerun` flag is being set

### Performance Issues:

- Reduce `_nifty_event_interval` if updates are too slow
- Increase rerun throttling (1s → 2s) if UI is laggy
- Check Railway logs for resource constraints

## Next Steps (Future Improvements)

1. **Client-Side WebSocket**: Consider using JavaScript WebSocket client instead of Python for faster updates
2. **State Management**: Use React/Streamlit components for reactive UI updates
3. **Caching Strategy**: Implement smarter caching to reduce API calls
4. **Monitoring**: Add metrics for tick update latency and UI refresh rate

