# Tab Navigation Fix - Auto-Refresh Interruption

## 🐛 Problem

When navigating to tabs other than Dashboard (Backtest, Settings, etc.) and interacting with components (selecting dropdowns, choosing data sources, etc.), the page would automatically redirect back to Dashboard, forcing users to navigate back to complete their action.

## 🔍 Root Cause

The auto-refresh mechanism was triggering `st.rerun()` globally, regardless of which tab the user was on. When `st.rerun()` executed:

1. The entire Streamlit script re-executed from the top
2. Auto-refresh checks happened before tab selection was fully processed
3. This caused the page to reload and potentially reset to Dashboard

## ✅ Solution Implemented

### 1. Tab Selection Moved Earlier

**Before:** Tab selection happened after auto-refresh checks  
**After:** Tab selection happens **before** auto-refresh checks

This ensures the current tab is known before any refresh decisions are made.

### 2. Auto-Refresh Limited to Dashboard Only

**Before:** Auto-refresh triggered on all tabs  
**After:** Auto-refresh **only triggers on Dashboard tab**

```python
# Only auto-refresh if on Dashboard tab
if (st.session_state.get('auto_refresh_enabled', True) and 
    current_main_tab == "Dashboard" and
    time_since_last_interaction > 3.0):
    # ... trigger refresh
```

### 3. User Interaction Tracking

Added interaction tracking to prevent auto-refresh during user actions:

- Tracks when user changes tabs
- Waits 3 seconds after tab change before allowing auto-refresh
- Prevents refresh from interrupting component interactions

### 4. Tab State Preservation

- Tab selection uses `key="selected_main_tab"` which persists in session state
- Tab state is initialized early and preserved across reruns
- Previous tab is tracked to detect tab changes

## 📝 Changes Made

### File: `dashboard/ui_frontend.py`

1. **Moved tab selection earlier** (line ~1592)
   - Tab selection now happens before auto-refresh checks
   - Ensures `current_main_tab` is available for refresh decisions

2. **Added tab check to auto-refresh** (line ~1626)
   ```python
   if (st.session_state.get('auto_refresh_enabled', True) and 
       current_main_tab == "Dashboard" and  # Only on Dashboard
       time_since_last_interaction > 3.0):  # Wait after interaction
   ```

3. **Added interaction tracking** (line ~1619)
   ```python
   # Track tab changes
   if st.session_state.get('_previous_tab') != current_main_tab:
       st.session_state['_last_user_interaction'] = time.time()
       st.session_state['_previous_tab'] = current_main_tab
   ```

4. **Limited market data refresh** (line ~1667)
   ```python
   auto_refresh_active = (
       st.session_state.auto_refresh_enabled
       and current_main_tab == "Dashboard"  # Only on Dashboard
       and time_since_last_interaction > 3.0  # Wait after interaction
       and (...)
   )
   ```

## ✅ Expected Behavior After Fix

### On Dashboard Tab
- ✅ Auto-refresh works normally (every 30 seconds)
- ✅ Data updates automatically
- ✅ No interruption to user actions

### On Other Tabs (Backtest, Settings, etc.)
- ✅ **No auto-refresh** - Page stays on current tab
- ✅ User can interact with components without interruption
- ✅ No automatic redirect to Dashboard
- ✅ Tab selection is preserved across component interactions

### When Switching Tabs
- ✅ Tab change is detected immediately
- ✅ Auto-refresh paused for 3 seconds after tab change
- ✅ Prevents refresh from interrupting tab navigation

## 🧪 Testing

### Test 1: Navigate to Backtest Tab
1. Click "Backtest" in sidebar
2. Select a data source dropdown
3. **Expected:** Page stays on Backtest tab, no redirect to Dashboard

### Test 2: Interact with Components
1. Go to Settings tab
2. Change any setting
3. **Expected:** Page stays on Settings tab, changes are applied

### Test 3: Switch Between Tabs
1. Go to Backtest tab
2. Select data source
3. Switch to Settings tab
4. **Expected:** Both tabs work without redirecting to Dashboard

### Test 4: Dashboard Auto-Refresh
1. Stay on Dashboard tab
2. Wait 30 seconds
3. **Expected:** Page auto-refreshes and stays on Dashboard

## 🔧 Configuration

Auto-refresh behavior can be controlled:

1. **Disable Auto-Refresh:**
   - Toggle "UI Auto" off in Dashboard
   - Or set `auto_refresh_enabled = False` in code

2. **Adjust Refresh Interval:**
   - Use the ⏱ popover in Dashboard
   - Change interval (5s to 180s)

3. **Interaction Delay:**
   - Currently set to 3 seconds
   - Can be adjusted in code if needed

## 📋 Technical Details

### Tab Selection Flow

```
1. Initialize tab state (if not exists)
2. Get previous tab (if exists)
3. Render sidebar radio (with key="selected_main_tab")
4. Detect tab change → Update interaction timestamp
5. Check auto-refresh (only if Dashboard + no recent interaction)
6. Process tab content
```

### Auto-Refresh Conditions

Auto-refresh triggers only when **ALL** conditions are met:
- ✅ `auto_refresh_enabled == True`
- ✅ `current_main_tab == "Dashboard"`
- ✅ `time_since_last_interaction > 3.0 seconds`
- ✅ `live_runner` or `market_data_provider` exists
- ✅ Refresh interval elapsed

## 🚨 Important Notes

1. **Background Refresh Still Works:**
   - Background API refresh (non-blocking) still runs on all tabs
   - This doesn't cause page reloads, only updates data

2. **Manual Refresh:**
   - Manual refresh buttons still work on all tabs
   - They trigger `st.rerun()` but preserve tab selection

3. **Component Interactions:**
   - Some components (buttons, form submissions) naturally trigger reruns
   - Tab selection is preserved via `key="selected_main_tab"`

4. **WebSocket Updates:**
   - WebSocket push updates still work on all tabs
   - They update data without causing page reloads

## ✅ Status

**Fixed:** ✅ Auto-refresh no longer interrupts user actions on non-Dashboard tabs

**Date:** 2025-11-22

---

**Related Issues:**
- Tab navigation interruption
- Auto-refresh causing unwanted redirects
- Component interactions being interrupted

