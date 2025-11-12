# Strategy Comparison: Original vs New Implementation

## Overview

This document compares the **original strategy** (`engine/strategy_engine.py`) with the **new standalone implementation** (`engine/inside_bar_breakout_strategy.py`).

## Key Differences

### 1. **Architecture**

| Aspect | Original (`strategy_engine.py`) | New (`inside_bar_breakout_strategy.py`) |
|--------|--------------------------------|------------------------------------------|
| **Structure** | Functional (standalone functions) | Object-oriented (class-based) |
| **Purpose** | Core strategy logic (reusable) | Complete production implementation |
| **Dependencies** | Minimal (pandas, numpy, logzero) | Full (broker, market_data, pytz) |
| **Integration** | Used by backtesting & live runner | Standalone runner script |

### 2. **Core Logic**

#### Original Strategy (`strategy_engine.py`)

**Functions:**
- `detect_inside_bar(data_1h, tighten_signal=True)` → Returns list of indices
- `confirm_breakout(data_1h, range_high, range_low, inside_bar_idx, mother_idx=None, ...)` → Returns "CE"/"PE"/None
- `check_for_signal(data_1h, data_15m, config)` → Returns signal dict or None
- `calculate_strike_price(current_price, direction, atm_offset)`
- `calculate_sl_tp_levels(entry_price, sl_points, rr_ratio)`

**Characteristics:**
- ✅ Pure functions (no side effects)
- ✅ Reusable across backtesting and live trading
- ✅ Returns signal dictionaries
- ✅ No broker integration
- ✅ No order placement
- ✅ No CSV export

#### New Strategy (`inside_bar_breakout_strategy.py`)

**Class: `InsideBarBreakoutStrategy`**

**Methods:**
- `get_hourly_candles(window_hours)` → Fetches from market data provider
- `detect_inside_bar(candles)` → Returns dict with inside bar info
- `check_breakout(candles, signal_high, signal_low, start_idx)` → Returns "CE"/"PE"/None
- `place_trade(direction, strike, current_price)` → Places order via broker
- `run_strategy()` → Complete workflow execution

**Characteristics:**
- ✅ Complete production implementation
- ✅ Broker integration (AngelOne API)
- ✅ Market data integration
- ✅ Order placement with margin check
- ✅ CSV export functionality
- ✅ Formatted output (DD-MMM-YYYY dates)
- ✅ LIVE_MODE toggle
- ✅ IST timezone handling
- ✅ Market hours validation

### 3. **Signal Detection Logic**

#### Both Use Same Core Logic:
- ✅ 1-hour candles only
- ✅ Inside bar detection: `current_high < prev_high AND current_low > prev_low`
- ✅ Signal candle = candle before inside bar
- ✅ Breakout on 1-hour candle close
- ✅ No 15-minute confirmation

#### Differences:

| Feature | Original | New |
|---------|----------|-----|
| **Volume Confirmation** | Optional (can skip for NIFTY) | Not implemented (removed) |
| **Range Tightening** | Yes (via `tighten_signal` param) | Yes (built-in) |
| **Signal Persistence** | Not tracked (recalculated each time) | **Tracked in class state** |
| **Breakout Check** | Checks all candles after inside bar | **Only checks new candles** (tracks `last_checked_candle_idx`) |

### 4. **New Features in New Implementation**

#### ✅ **Signal State Management**
```python
# New strategy tracks signal state
self.signal_candle_high = None
self.signal_candle_low = None
self.signal_candle_date = None
self.inside_bar_date = None
self.last_checked_candle_idx = -1
```

**Benefit:** Signal remains active until new inside bar detected (as per requirements)

#### ✅ **Market Hours Validation**
```python
def _is_market_hours(self, dt=None) -> bool:
    # Checks if time is within 09:15 AM to 03:15 PM IST
```

#### ✅ **IST Timezone Handling**
```python
def _format_date_ist(self, dt) -> str:
    # Formats to DD-MMM-YYYY (e.g., "04-Nov-2025")
```

#### ✅ **AngelOne API Integration**
- Live OHLC data fetching
- Margin check via RMS API
- Order placement via `place_order()`
- Full API response logging

#### ✅ **CSV Export**
- Exports results to `logs/inside_bar_breakout_results.csv`
- Includes: Date, Time, Signal_Date, Signal_High, Signal_Low, Current_Price, Breakout_Direction, Strike, Order_ID, Status, Message

#### ✅ **LIVE_MODE Toggle**
```python
LIVE_MODE = True  # Set to False to test without real trades
```

#### ✅ **Formatted Console Output**
```
======================================================================
INSIDE BAR BREAKOUT STRATEGY - EXECUTION SUMMARY
======================================================================
✅ Inside Bar Detected on 04-Nov-2025
Signal Candle: High=26250.00, Low=26200.00
Current Price: 26230.00
🟢 Breakout Confirmed: CE
...
```

### 5. **What's Missing in New Implementation**

#### ❌ **Volume Confirmation**
- Original: Has `volume_threshold_multiplier` parameter
- New: Removed (as per requirements: "No 15-min confirmation logic")

#### ❌ **SL/TP Calculation**
- Original: Calculates stop loss and take profit levels
- New: Not implemented (focuses on entry only)

#### ❌ **Strike Offset**
- Original: Supports `atm_offset` parameter
- New: Uses ATM only (no offset)

### 6. **Backtesting Integration**

#### Current Status: ❌ **NOT Integrated**

**Backtesting Engine** (`engine/backtest_engine.py`):
```python
from engine.strategy_engine import detect_inside_bar  # Uses original
```

**Backtesting still uses:**
- ✅ `detect_inside_bar()` from `strategy_engine.py`
- ✅ Its own breakout logic (not using `confirm_breakout()`)
- ✅ Its own signal detection logic

**New strategy is NOT used in backtesting because:**
- Backtesting needs pure functions (no broker dependencies)
- Backtesting has its own trade simulation logic
- New strategy is designed for live trading only

### 7. **Usage Comparison**

#### Original Strategy (Used by Backtesting & Live Runner)
```python
from engine.strategy_engine import check_for_signal

signal = check_for_signal(data_1h, data_15m, config)
if signal:
    # Handle signal (backtest or live)
    direction = signal['direction']
    strike = signal['strike']
    # ...
```

#### New Strategy (Standalone)
```python
from engine.inside_bar_breakout_strategy import InsideBarBreakoutStrategy

strategy = InsideBarBreakoutStrategy(broker, market_data, ...)
result = strategy.run_strategy()
# Automatically handles: detection, breakout check, order placement
```

## Summary Table

| Feature | Original | New | Backtesting Uses |
|---------|----------|-----|------------------|
| Inside Bar Detection | ✅ | ✅ | ✅ Original |
| Breakout Confirmation | ✅ | ✅ | ❌ Own logic |
| Signal Dictionary | ✅ | ❌ | ✅ Original |
| Broker Integration | ❌ | ✅ | ❌ |
| Order Placement | ❌ | ✅ | ❌ |
| CSV Export | ❌ | ✅ | ❌ |
| Formatted Output | ❌ | ✅ | ❌ |
| LIVE_MODE Toggle | ❌ | ✅ | ❌ |
| Signal State Tracking | ❌ | ✅ | ❌ |
| Market Hours Validation | ❌ | ✅ | ❌ |
| IST Timezone Formatting | ❌ | ✅ | ❌ |
| Volume Confirmation | ✅ | ❌ | ✅ Original |
| SL/TP Calculation | ✅ | ❌ | ✅ Original |

## Recommendations

### For Backtesting:
✅ **Keep using original** `strategy_engine.py` - it's designed for this purpose

### For Live Trading:
✅ **Use new** `inside_bar_breakout_strategy.py` - complete production implementation

### To Integrate New Strategy into Backtesting:
1. Extract pure functions from new strategy (without broker dependencies)
2. Create adapter layer for backtesting
3. Or: Refactor new strategy to separate logic from execution

## Conclusion

The **new strategy** is a **complete production implementation** with:
- ✅ Full broker integration
- ✅ Order placement
- ✅ CSV export
- ✅ Formatted output
- ✅ Signal state management

The **original strategy** remains the **core logic** used by:
- ✅ Backtesting engine
- ✅ Live runner (via `check_for_signal()`)

**They serve different purposes:**
- **Original**: Core strategy logic (reusable)
- **New**: Complete production implementation (standalone)

