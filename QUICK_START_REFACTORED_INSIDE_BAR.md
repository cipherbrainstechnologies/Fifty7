# Quick Start Guide - Refactored Inside Bar Strategy

## 🚀 Getting Started

### 1. Basic Usage (Dry Run)

```python
from engine.inside_bar_breakout_strategy import InsideBarBreakoutStrategy
from engine.broker_connector import AngelOneBroker
from engine.market_data import MarketDataProvider

# Create broker and market data provider
broker = AngelOneBroker(broker_config)
market_data = MarketDataProvider(broker)

# Create strategy (dry run mode)
strategy = InsideBarBreakoutStrategy(
    broker=broker,
    market_data=market_data,
    symbol="NIFTY",
    lot_size=75,
    quantity_lots=1,
    live_mode=False,  # DRY RUN
    csv_export_path="logs/inside_bar_results.csv",
    config={'strategy': {'sl': 30, 'rr': 1.8, 'atm_offset': 0}}
)

# Run strategy
result = strategy.run_strategy()
print(f"Status: {result['status']}")
print(f"Message: {result['message']}")
```

### 2. Live Trading Mode

```python
# Enable live mode (requires LIVE_MODE=True in module)
strategy = InsideBarBreakoutStrategy(
    broker=broker,
    market_data=market_data,
    live_mode=True  # LIVE MODE
)

# ARM execution (safety requirement)
strategy.arm_live_execution()

# Run strategy
result = strategy.run_strategy()
```

### 3. Get Current State (for UI)

```python
# Get JSON-serializable state
state = strategy.get_current_state()

print(f"Active Signal: {state['has_active_signal']}")
if state['has_active_signal']:
    signal = state['signal']
    print(f"Range: {signal['range_low']:.2f} - {signal['range_high']:.2f}")
    print(f"Signal Time: {signal['signal_time']}")
```

---

## 📊 Status Handling

```python
result = strategy.run_strategy()
status = result['status']

if status == 'breakout_confirmed':
    # Trade was placed successfully
    print(f"✅ Trade executed: {result['breakout_direction']}")
    print(f"Order ID: {result['order_id']}")
    print(f"Entry: {result['entry_price']:.2f}")
    
elif status == 'missed_trade':
    # Breakout occurred but system was offline
    print(f"⚠️ Missed trade: {result['breakout_direction']}")
    print(f"Old signal invalidated. Awaiting new inside bar.")
    
elif status == 'missed_trade_new_signal_found':
    # Missed trade, but new inside bar already found
    print(f"⚠️ Missed trade, but NEW inside bar detected")
    print(f"New Range: {result['new_signal_low']:.2f} - {result['new_signal_high']:.2f}")
    
elif status == 'no_breakout':
    # Inside bar active, waiting for breakout
    print(f"⏳ Inside bar active. Awaiting breakout.")
    print(f"Range: {result['signal_low']:.2f} - {result['signal_high']:.2f}")
    
elif status == 'no_signal':
    # No inside bar detected yet
    print("📊 No inside bar pattern detected. Scanning...")
    
elif status == 'duplicate_breakout':
    # Same breakout already processed (idempotency)
    print("⏭️ Duplicate breakout skipped")
    
elif status == 'market_closed':
    # Outside trading hours
    print("⏸️ Market closed")
```

---

## 🧪 Testing

### Test with Historical Data

```python
import pandas as pd

# Create test data
candles = pd.DataFrame([
    {'Date': '2025-11-06 09:15', 'Open': 25550, 'High': 25600, 'Low': 25530, 'Close': 25580, 'Volume': 0},
    {'Date': '2025-11-06 14:15', 'Open': 25520, 'High': 25564.60, 'Low': 25491.55, 'Close': 25540, 'Volume': 0},
    {'Date': '2025-11-06 15:15', 'Open': 25510, 'High': 25521.45, 'Low': 25498.70, 'Close': 25515, 'Volume': 0},
    {'Date': '2025-11-07 09:15', 'Open': 25475, 'High': 25485, 'Low': 25340, 'Close': 25351.45, 'Volume': 0},
])
candles['Date'] = pd.to_datetime(candles['Date'])

# Run strategy with test data
result = strategy.run_strategy(data=candles)
```

### Run Dry Run Scenario

```bash
python3 dry_run_07_nov_scenario.py
```

---

## 🔧 Configuration

### Strategy Parameters

```python
config = {
    'strategy': {
        'sl': 30,           # Stop loss in points
        'rr': 1.8,          # Risk-reward ratio
        'atm_offset': 0     # Strike offset from ATM (0 = ATM)
    }
}

strategy = InsideBarBreakoutStrategy(
    broker=broker,
    market_data=market_data,
    config=config
)
```

### CSV Export

All trades are automatically logged to CSV:
- Path: `logs/inside_bar_breakout_results.csv`
- Columns: Date, Time, Signal_Date, Signal_High, Signal_Low, Current_Price, Breakout_Direction, Strike, Entry_Price, Stop_Loss, Take_Profit, Order_ID, Status, Message

---

## 🎯 Key Methods

### `run_strategy(data: Optional[pd.DataFrame] = None) -> Dict`
Execute one strategy evaluation cycle.

**Parameters**:
- `data`: Optional DataFrame with OHLC data (for backtesting)

**Returns**: Dictionary with status, message, and trade details

### `get_current_state() -> Dict`
Get current strategy state for UI.

**Returns**: JSON-serializable dict with signal status, range, timestamps

### `arm_live_execution() -> bool`
Enable real trade execution (required for live mode).

**Returns**: True if successful

### `disarm_live_execution()`
Disable trade execution (return to dry run).

### `get_active_signal(candles: pd.DataFrame) -> Optional[Dict]`
Get or update active inside bar signal.

**Returns**: Signal dict or None

---

## 📝 Example Output

```
🚀 Running Inside Bar Breakout Strategy | Time: 07-Nov-2025 13:28:04 IST

📦 Loaded 8 hourly candles for analysis
   Date range: 06-Nov-2025 09:15:00 IST to 07-Nov-2025 09:15:00 IST

========================================================================================================================
RECENT HOURLY CANDLES (1H TIMEFRAME - IST)
========================================================================================================================
Timestamp              |     Open |     High |      Low |    Close | Status          | Reference Range
------------------------------------------------------------------------------------------------------------------------
06-Nov-2025 14:15:00 IST | 25520.00 | 25564.60 | 25491.55 | 25540.00 | 🔵 Signal Candle | Range: 25491.55-25564.60
06-Nov-2025 15:15:00 IST | 25510.00 | 25521.45 | 25498.70 | 25515.00 | 🟢 Inside Bar    | Range: 25491.55-25564.60
07-Nov-2025 09:15:00 IST | 25475.00 | 25485.00 | 25340.00 | 25351.45 | 🔴 Breakout PE   | Close < 25491.55
========================================================================================================================

🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴
✅ FIRST BREAKOUT DETECTED (PE) at 07-Nov-2025 10:15:00 IST
   Close 25351.45 < Signal Low 25491.55
   Breakout by 140.10 points
🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴
```

---

## 🛡️ Safety Features

1. **Dual Mode Flag**: `LIVE_MODE` (module) + `live_mode` (instance)
2. **Execution Arming**: Must call `arm_live_execution()`
3. **Duplicate Prevention**: Tracks last breakout timestamp
4. **Market Hours Check**: 09:15-15:15 IST, Mon-Fri
5. **Margin Validation**: Checks available capital before trades

---

## 🔍 Troubleshooting

### "TypeError: Invalid comparison between dtype=datetime64[ns] and datetime"
**Solution**: Fixed in refactored version. Timezone-aware comparison implemented.

### "Same inside bar detected after breakout"
**Solution**: Fixed. New `exclude_before_time` parameter prevents old signal reuse.

### "Breakout not detected"
**Solution**: Check if candle has closed (wait for hourly candle completion). Logs will show "Skipping incomplete candle".

### "LIVE_MODE is False but I want live trading"
**Solution**: Set `LIVE_MODE = True` in `inside_bar_breakout_strategy.py` (line 30), then set `live_mode=True` in constructor, then call `arm_live_execution()`.

---

## 📚 Additional Resources

- **Full Documentation**: `INSIDE_BAR_REFACTORING_COMPLETE_2025_11_07.md`
- **Architecture**: `memory-bank/architecture.md`
- **Test Script**: `dry_run_07_nov_scenario.py`

---

**Last Updated**: 07-Nov-2025  
**Version**: 2.0 (Refactored)  
**Status**: ✅ Production Ready
