# Railway White Screen Debug Guide

## Issue
After successful login, the dashboard shows a blank white screen with no content visible.

## Symptoms
- ✅ Login works correctly
- ✅ All initialization logs show success
- ✅ No error messages in logs
- ❌ Dashboard UI is completely blank
- ❌ Start Algo button doesn't work (or isn't visible)

## Root Cause Analysis

Possible causes:
1. **Silent Exception**: Dashboard rendering code is failing silently
2. **Missing Components**: Required session state variables are None
3. **Streamlit Rendering Issue**: Content not being rendered to page
4. **JavaScript/Browser Issue**: Content rendering but not displaying

## Debugging Steps

### Step 1: Check Railway Logs
Look for:
- `"Rendering Dashboard tab..."` message
- Any exceptions or errors
- Missing import errors

### Step 2: Check Browser Console (F12)
Look for:
- JavaScript errors
- Network errors
- Console warnings

### Step 3: Verify Session State
The dashboard requires:
- `st.session_state.broker` - Broker interface
- `st.session_state.live_runner` - Live strategy runner (may be None)
- `st.session_state.market_data_provider` - Market data provider
- `st.session_state.signal_handler` - Signal handler
- `st.session_state.trade_logger` - Trade logger

### Step 4: Check Sidebar Menu
The sidebar menu should be visible. If not:
- Check if `st.sidebar.radio()` is executing
- Look for errors in sidebar rendering

## Fixes Applied

1. **Added Error Handling**: Dashboard rendering wrapped in try-except
2. **Added Debug Logging**: Logs when dashboard starts rendering
3. **Start Button Fix**: Button no longer disabled when live_runner is None (shows warning instead)
4. **Graceful Degradation**: Dashboard shows errors instead of blank screen

## Expected Behavior After Fix

- ✅ Dashboard header should always appear
- ✅ Error messages should be visible if something fails
- ✅ Start Algo button should be visible (may show warning)
- ✅ Sidebar menu should be visible

## If Still Blank

1. Check Railway logs for "Rendering Dashboard tab..." message
2. Check browser console for errors
3. Try hard refresh (Ctrl+Shift+R or Cmd+Shift+R)
4. Clear browser cache
5. Check if other tabs (Portfolio, Settings) work

## Status
🔧 Debug logging and error handling added. Need to check logs for specific error.

