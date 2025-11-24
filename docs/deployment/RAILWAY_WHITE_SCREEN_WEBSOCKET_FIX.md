# Railway White Screen & WebSocket Fix

## Issue
After successful login, the dashboard shows a white screen, and SmartAPI WebSocket connections continuously fail and spam the logs.

## Root Causes

### 1. White Screen After Login
- **Problem**: Dashboard rendering accesses `st.session_state.algo_running` directly without checking if it exists
- **Impact**: If session state initialization fails, `KeyError` crashes the page, resulting in white screen
- **Location**: `dashboard/ui_frontend.py` line 2012

### 2. SmartAPI WebSocket Reconnection Loop
- **Problem**: WebSocket keeps trying to reconnect indefinitely when connection fails
- **Impact**: Logs are flooded with connection errors, making debugging difficult
- **Location**: `engine/tick_stream.py` line 161-171

## Fixes Applied

### 1. Dashboard Error Handling
- **Safe Session State Access**: Changed `st.session_state.algo_running` to `st.session_state.get('algo_running', False)`
- **Wrapped Dashboard Rendering**: Entire Dashboard tab is now wrapped in try-except block
- **User-Friendly Error Display**: Errors are displayed using `st.error()` instead of crashing

### 2. SmartAPI WebSocket Failure Limit
- **Max Failure Count**: Added `_max_failures = 5` to limit reconnection attempts
- **Automatic Disable**: After 5 consecutive failures, tick streamer is automatically disabled
- **Reduced Log Spam**: Failure count is logged with each attempt (e.g., "3/5 failures")

## Code Changes

### `dashboard/ui_frontend.py`
```python
# Before:
engine_status = st.session_state.algo_running

# After:
engine_status = st.session_state.get('algo_running', False)

# Added try-except wrapper around entire Dashboard tab rendering
```

### `engine/tick_stream.py`
```python
# Added failure tracking
self._failure_count = 0
self._max_failures = 5

# Stop after max failures
if self._failure_count >= self._max_failures:
    logger.error("Disabling tick streamer after max failures")
    self.enabled = False
    break
```

## Expected Behavior

After fix:
1. ✅ Dashboard renders even if some session state variables are missing
2. ✅ Errors are displayed to user instead of white screen
3. ✅ SmartAPI WebSocket stops trying after 5 failures
4. ✅ Logs are cleaner and easier to debug

## Testing

1. **White Screen Fix**:
   - Login should show dashboard even if broker isn't initialized
   - Errors should be displayed as error messages, not white screen

2. **WebSocket Fix**:
   - After 5 connection failures, logs should show "Disabling tick streamer"
   - No more continuous reconnection spam in logs

## If Still Experiencing Issues

1. **Check Railway Logs**: Look for the exact error message in dashboard rendering
2. **Verify Session State**: Ensure broker and other session state variables are initialized
3. **Restart Service**: If WebSocket was disabled due to failures, restart the service to re-enable it
4. **Check Broker Config**: Verify broker credentials are correct in environment variables

## Status
✅ Fixed - Dashboard error handling and WebSocket failure limits added

