# Real-Time Updates & Seamless Data Flow - Complete Guide

## 📋 Overview

This document explains how the system provides **seamless, automatic updates** between backend API data and the frontend dashboard UI, covering all aspects from market data to trade execution.

---

## ⏰ Hourly Confirmation Check (Timeframe Strategy)

### From Memory Documentation

According to `memory-bank/architecture.md`:

> **Live runs continue to use 1-hour candles for detection and confirmation**

### How It Works

1. **Detection Timeframe: 1H**
   - System scans **1-hour candles** for Inside Bar patterns
   - Checks every closed 1H candle for consolidation patterns

2. **Confirmation Timeframe: 1H** (Not 15m for live trading)
   - Monitors every subsequent **1-hour candle** for breakout confirmation
   - Breakout confirmed when 1H candle closes outside mother range
   - Volume confirmation required

3. **Breakout Confirmation Logic:**
   ```
   - Bullish Breakout (CE): Close > range_high AND Volume > threshold
   - Bearish Breakout (PE): Close < range_low AND Volume > threshold
   ```

**Note:** The `config.yaml` shows `confirmation: "15m"`, but according to architecture docs, **live trading uses 1H for both detection and confirmation**. The 15m timeframe may be for backtesting or historical analysis.

---

## 🔄 Real-Time Update Mechanisms

### 1. WebSocket Push Updates (True Real-Time)

**Latency:** < 2 seconds for critical events

**How It Works:**
```
Backend Event → Event Bus → WebSocket Server → Dashboard Client → UI Update
```

**What Updates via WebSocket:**
- ✅ **Trade Execution** - Immediate push when order placed
- ✅ **Position Closed** - Immediate push when trade exits
- ✅ **Daily Loss Breached** - Immediate alert
- ✅ **Signal Detected** - Real-time signal notifications
- ✅ **State Changes** - Position updates, P&L changes

**Configuration:**
```yaml
websocket:
  enabled: true
  host: "127.0.0.1"
  port: 8765
  reconnect_interval: 5  # Auto-reconnect if disconnected
  ping_interval: 30       # Keepalive ping
```

**Status:** ✅ **Fully Implemented** (from `memory-bank/WEBSOCKET_IMPLEMENTATION.md`)

---

### 2. Active P&L Tracker (5-Second Updates)

**Update Frequency:** Every 5 seconds

**What It Tracks:**
- ✅ **Option Prices (LTP)** - Real-time Last Traded Price
- ✅ **Index Prices** - NIFTY spot price updates
- ✅ **Unrealized P&L** - Mark-to-market P&L for open positions
- ✅ **Active Trades** - Current position status

**How It Works:**
```python
# From engine/live_runner.py
ActivePnLTracker (background thread)
  - Samples open trades every 5 seconds
  - Merges WebSocket ticks with REST fallbacks
  - Updates dashboard hero metrics
  - Feeds PositionMonitor for SL/TP checks
```

**Configuration:**
```yaml
market_data:
  pnl_refresh_seconds: 5  # Active P&L refresh interval
  pnl_quote_stale_seconds: 5  # Quote staleness threshold
```

**Status:** ✅ **Fully Implemented**

---

### 3. WebSocket Tick Streaming (Real-Time Quotes)

**Update Frequency:** Tick-by-tick (real-time)

**What It Streams:**
- ✅ **Option Prices** - Live tick-by-tick updates for open positions
- ✅ **NIFTY Index** - Real-time index price movements
- ✅ **LTP Updates** - Last Traded Price for all subscribed symbols

**How It Works:**
```python
# From engine/tick_stream.py
LiveTickStreamer
  - Subscribes to SmartAPI WebSocket
  - Receives tick-by-tick price updates
  - Feeds Active P&L tracker
  - Updates dashboard metrics in real-time
```

**Subscriptions:**
- NIFTY index (always subscribed)
- Open option positions (auto-subscribed when trade opens)
- Auto-unsubscribes when position closes

**Status:** ✅ **Fully Implemented** (from architecture.md line 194)

---

### 4. Auto-Refresh Dashboard (30-Second Polling)

**Update Frequency:** Every 30 seconds (configurable)

**What It Refreshes:**
- ✅ **Market Data** - Latest OHLC candles
- ✅ **Strategy Status** - Algo running/stopped state
- ✅ **Active Trades** - Position updates
- ✅ **Broker Positions** - Reconciliation with broker
- ✅ **Daily P&L** - Cumulative P&L updates

**How It Works:**
```python
# From dashboard/ui_frontend.py
Auto-refresh (when algo running)
  - Triggers market data refresh every 30s
  - Calls st.rerun() to refresh entire page
  - Non-blocking background refresh available
```

**Configuration:**
- Default: 30 seconds
- User can adjust: 5s to 60s
- Can be disabled

**Status:** ✅ **Fully Implemented**

---

### 5. Background API Refresh (10-Second Non-Blocking)

**Update Frequency:** Every 10 seconds (non-blocking)

**What It Refreshes:**
- ✅ **Broker API Data** - Positions, orders, portfolio
- ✅ **Market Data** - OHLC candles (if stale)
- ✅ **State Reconciliation** - Sync with broker

**How It Works:**
```python
# Background thread (doesn't block UI)
background_api_refresh()
  - Runs in separate thread
  - Updates session state
  - No UI flicker
  - Prevents too-frequent refreshes (5s minimum)
```

**Status:** ✅ **Fully Implemented**

---

## 📊 Complete Update Flow

### Scenario 1: Option Price Moves

```
1. SmartAPI WebSocket → Tick Streamer (real-time)
2. Tick Streamer → Active P&L Tracker (every 5s)
3. Active P&L Tracker → Dashboard Metrics (immediate)
4. Dashboard displays updated LTP and P&L
```

**Result:** ✅ **Seamless - Updates within 5 seconds**

---

### Scenario 2: Index (NIFTY) Price Moves

```
1. SmartAPI WebSocket → Tick Streamer (real-time)
2. Tick Streamer → Market Data Provider
3. Market Data Provider → Strategy Engine
4. Strategy Engine → Signal Detection
5. Signal Detected → Event Bus → WebSocket → Dashboard
6. Dashboard shows new signal/breakout
```

**Result:** ✅ **Seamless - Updates within 5 seconds, signals pushed immediately**

---

### Scenario 3: Strategy Detection (Inside Bar + Breakout)

```
1. Market Data Refresh (every 30s or on new candle)
2. Strategy Engine scans 1H candles
3. Inside Bar detected → State Store updated
4. Breakout confirmed → Signal generated
5. Signal → Event Bus → WebSocket → Dashboard
6. Dashboard shows pending signal
```

**Result:** ✅ **Seamless - Detected within 30 seconds, pushed immediately via WebSocket**

---

### Scenario 4: Trade Execution

```
1. Signal confirmed → Live Runner executes trade
2. Order placed → Broker API
3. Trade Executed → Event Bus → WebSocket → Dashboard (< 2s)
4. Position Monitor starts tracking
5. Active P&L Tracker updates every 5s
6. Dashboard shows active trade with live P&L
```

**Result:** ✅ **Seamless - Trade appears in < 2 seconds, P&L updates every 5s**

---

### Scenario 5: Trade Cut-Off/Exit

```
1. SL/TP hit OR Manual exit → Position Monitor detects
2. Position Closed → Event Bus → WebSocket → Dashboard (< 2s)
3. Trade Logger updates exit
4. Daily P&L updated
5. Active P&L Tracker removes from tracking
6. Dashboard shows closed trade with final P&L
```

**Result:** ✅ **Seamless - Exit reflected in < 2 seconds, final P&L updated immediately**

---

## 🎯 Update Latency Summary

| Event Type | Update Method | Latency | Status |
|------------|---------------|---------|--------|
| **Trade Executed** | WebSocket Push | < 2 seconds | ✅ Real-time |
| **Position Closed** | WebSocket Push | < 2 seconds | ✅ Real-time |
| **Option Price (LTP)** | WebSocket Ticks + 5s Poll | 5 seconds | ✅ Near real-time |
| **Index Price** | WebSocket Ticks + 5s Poll | 5 seconds | ✅ Near real-time |
| **Signal Detected** | WebSocket Push | < 2 seconds | ✅ Real-time |
| **Market Data (OHLC)** | Auto-refresh | 30 seconds | ✅ Regular |
| **Broker Positions** | Background refresh | 10 seconds | ✅ Regular |
| **Daily P&L** | Event-driven + 30s refresh | < 2s (events) / 30s (poll) | ✅ Hybrid |

---

## 🔧 Configuration for Optimal Updates

### Recommended Settings

```yaml
# config/config.yaml

market_data:
  pnl_refresh_seconds: 5  # Active P&L updates every 5s
  polling_interval_seconds: 900  # Market data every 15min (for candles)

websocket:
  enabled: true  # Enable real-time push updates
  reconnect_interval: 5
  ping_interval: 30

# Dashboard auto-refresh (in UI)
auto_refresh_interval_sec: 30  # Full page refresh every 30s
background_refresh_interval_sec: 10  # Background API refresh every 10s
```

---

## ✅ What's Seamless vs What's Not

### ✅ Fully Seamless (Automatic, Real-Time)

1. **Option Price Updates** - ✅ Updates every 5 seconds automatically
2. **Index Price Updates** - ✅ Updates every 5 seconds automatically
3. **Trade Execution** - ✅ Pushed immediately (< 2 seconds)
4. **Trade Exit/Cut-Off** - ✅ Pushed immediately (< 2 seconds)
5. **Signal Detection** - ✅ Pushed immediately when detected
6. **Active P&L** - ✅ Updates every 5 seconds automatically
7. **Position Status** - ✅ Updates via WebSocket + polling

### ⚠️ Semi-Seamless (Requires Refresh)

1. **Market Data (OHLC Candles)** - Updates every 30 seconds (auto-refresh)
2. **Historical Trades** - Loads on demand or on refresh
3. **Backtest Results** - Loads on demand
4. **Broker Portfolio** - Updates every 10 seconds (background)

---

## 🚀 How to Verify Seamless Updates

### Test 1: Option Price Movement

1. Open a trade (or have an open position)
2. Watch the "Active P&L" metric in Dashboard
3. **Expected:** Price and P&L update every 5 seconds automatically
4. **No manual refresh needed**

### Test 2: Trade Execution

1. Enable live trading
2. Wait for signal and trade execution
3. **Expected:** Trade appears in Dashboard within 2 seconds
4. **No manual refresh needed**

### Test 3: Trade Exit

1. Have an open position
2. Hit SL/TP or manually exit
3. **Expected:** Position disappears and final P&L shown within 2 seconds
4. **No manual refresh needed**

### Test 4: Strategy Detection

1. Monitor Dashboard during market hours
2. Wait for Inside Bar + Breakout
3. **Expected:** Signal appears in "Pending Signals" within 2 seconds
4. **No manual refresh needed**

---

## 📝 Important Notes

### 1. WebSocket Connection

- WebSocket must be enabled in `config.yaml`
- Server starts automatically with dashboard
- Client connects automatically
- Auto-reconnects if disconnected

### 2. Auto-Refresh Settings

- Auto-refresh is **enabled by default**
- User can disable in Dashboard UI
- Interval is configurable (5s to 60s)
- Only runs when algo is active

### 3. Background Refresh

- Runs in separate thread (non-blocking)
- Prevents UI flicker
- Minimum 5-second interval between refreshes
- Can be disabled

### 4. Market Hours

- Updates are most active during market hours (9:15 AM - 3:30 PM IST)
- Outside market hours, updates are less frequent
- WebSocket may disconnect after market close

---

## 🎯 Summary

### ✅ YES - Backend and Frontend are Seamless!

**Automatic Updates:**
- ✅ Option prices update every 5 seconds
- ✅ Index prices update every 5 seconds  
- ✅ Strategy detection pushes immediately
- ✅ Trade execution pushes immediately
- ✅ Trade exit pushes immediately
- ✅ Active P&L updates every 5 seconds

**No Manual Action Required:**
- ✅ Dashboard refreshes automatically
- ✅ Data flows seamlessly from API to UI
- ✅ Real-time updates via WebSocket
- ✅ Background polling for status updates

**The system is designed for seamless, automatic updates with minimal latency!**

---

**Last Updated:** 2025-11-22  
**Based on:** `memory-bank/architecture.md`, `memory-bank/WEBSOCKET_IMPLEMENTATION.md`, `memory-bank/seamless-trading-architecture.plan.md`

