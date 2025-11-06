# Inside Bar Breakout Strategy - Production Implementation

## Overview

This is a complete, production-grade implementation of the Inside Bar Breakout strategy for NIFTY Options trading using AngelOne SmartAPI.

## Strategy Rules

1. **Timeframe**: 1-Hour candles in IST timezone
2. **Market Hours**: 09:15 AM to 03:15 PM IST
3. **Inside Bar Detection**: 
   - Current candle high < previous candle high
   - Current candle low > previous candle low
4. **Signal Candle**: The candle just before the inside bar
5. **Signal Persistence**: Signal remains active until a new inside bar is detected
6. **Breakout Confirmation**: 
   - If 1-hour candle CLOSES above signal high → Execute CE trade
   - If 1-hour candle CLOSES below signal low → Execute PE trade
7. **No 15-min confirmation**: Only 1-hour candle close matters

## Files Created

### 1. `engine/inside_bar_breakout_strategy.py`
Main strategy implementation module with:
- `InsideBarBreakoutStrategy` class
- Modular functions:
  - `get_hourly_candles()` - Fetch 1-hour candles from market data
  - `detect_inside_bar()` - Detect inside bar patterns
  - `check_breakout()` - Check for breakout on candle close
  - `place_trade()` - Execute trades via AngelOne API
- IST timezone handling
- Formatted output with DD-MMM-YYYY dates
- CSV export functionality
- LIVE_MODE toggle for testing

### 2. `run_inside_bar_strategy.py`
Standalone runner script for executing the strategy.

## Installation

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Configure broker credentials** in `.streamlit/secrets.toml`:
```toml
[broker]
type = "angel"
api_key = "YOUR_API_KEY"
client_id = "YOUR_CLIENT_ID"
username = "YOUR_CLIENT_ID"
pwd = "YOUR_TRADING_PIN"
token = "YOUR_TOTP_QR_SECRET"
```

## Usage

### Basic Usage

```python
from engine.inside_bar_breakout_strategy import InsideBarBreakoutStrategy
from engine.broker_connector import AngelOneBroker
from engine.market_data import MarketDataProvider

# Load broker config
broker_config = {
    'api_key': 'YOUR_API_KEY',
    'client_id': 'YOUR_CLIENT_ID',
    'username': 'YOUR_CLIENT_ID',
    'pwd': 'YOUR_TRADING_PIN',
    'token': 'YOUR_TOTP_QR_SECRET'
}

# Create broker and market data instances
broker = AngelOneBroker(broker_config)
market_data = MarketDataProvider(broker)

# Create strategy
strategy = InsideBarBreakoutStrategy(
    broker=broker,
    market_data=market_data,
    symbol="NIFTY",
    lot_size=75,
    quantity_lots=1,
    live_mode=True,  # Set to False for testing
    csv_export_path="logs/inside_bar_breakout_results.csv"
)

# Run strategy
result = strategy.run_strategy()
```

### Using the Runner Script

```bash
python run_inside_bar_strategy.py
```

## Configuration

### LIVE_MODE Toggle

Edit `engine/inside_bar_breakout_strategy.py`:

```python
LIVE_MODE = True  # Set to False to test without real trades
```

When `LIVE_MODE = False`:
- Orders are simulated (not placed)
- Margin check is skipped
- Full strategy logic is executed
- Useful for testing and backtesting

### Strategy Parameters

Modify in `InsideBarBreakoutStrategy.__init__()`:
- `symbol`: Trading symbol (default: "NIFTY")
- `lot_size`: Lot size for options (default: 75)
- `quantity_lots`: Number of lots per trade (default: 1)
- `live_mode`: Live mode flag (default: True)

## Output Format

### Console Output

```
======================================================================
INSIDE BAR BREAKOUT STRATEGY - EXECUTION SUMMARY
======================================================================
✅ Inside Bar Detected on 04-Nov-2025
Signal Candle: High=26250.00, Low=26200.00
Current Price: 26230.00
🟢 Breakout Confirmed: CE
Strike: 26250
Order ID: 123456789
Order Status: SUCCESS
Message: Order placed successfully
Time: 04-Nov-2025 10:30:00 IST
======================================================================
```

### CSV Export

Results are exported to `logs/inside_bar_breakout_results.csv` with columns:
- Date
- Time
- Signal_Date
- Signal_High
- Signal_Low
- Current_Price
- Breakout_Direction (CE/PE)
- Strike
- Order_ID
- Status
- Message

## API Integration

### AngelOne SmartAPI Features Used

1. **Session Management**: Automatic session generation and refresh
2. **Market Data**: Live OHLC data via `getCandleData` API
3. **Margin Check**: RMS API to check available margin
4. **Order Placement**: `placeOrder` API to execute trades
5. **Error Handling**: Full response logging for debugging

### API Response Logging

All API responses are logged with full details:
```python
logger.info(f"📥 Order Response: {order_result}")
```

## Error Handling

The strategy includes comprehensive error handling:
- Market hours validation
- Margin check before order placement
- API error handling with retries
- CSV export error handling
- Graceful degradation on API failures

## Testing

### Test Mode (LIVE_MODE = False)

1. Set `LIVE_MODE = False` in `inside_bar_breakout_strategy.py`
2. Run the strategy:
```bash
python run_inside_bar_strategy.py
```
3. Strategy will execute all logic but simulate orders

### Live Mode (LIVE_MODE = True)

1. Ensure AngelOne SmartAPI is authenticated
2. Set `LIVE_MODE = True`
3. Run the strategy:
```bash
python run_inside_bar_strategy.py
```
4. Real orders will be placed on breakout confirmation

## Strategy Flow

1. **Check Market Hours**: Validates if market is open (09:15-15:15 IST)
2. **Fetch Hourly Candles**: Gets 1-hour OHLC data from market
3. **Detect Inside Bar**: Scans for most recent inside bar pattern
4. **Set Signal Levels**: Uses candle before inside bar as signal candle
5. **Monitor Breakouts**: Checks each new candle close for breakout
6. **Execute Trade**: Places order when breakout confirmed
7. **Log Results**: Exports to CSV and prints summary

## Important Notes

1. **Signal Persistence**: Signal remains active until a new inside bar is detected
2. **Breakout Timing**: Only checks candles AFTER the inside bar
3. **Candle Close**: Breakout is confirmed only on candle close (not intraday)
4. **Margin Check**: Always checks margin before placing orders
5. **IST Timezone**: All dates and times are in IST timezone

## Troubleshooting

### No Inside Bar Detected
- Ensure sufficient historical data (at least 48 hours)
- Check if market data is being fetched correctly
- Verify market hours (09:15-15:15 IST)

### Order Placement Failed
- Check margin availability
- Verify broker session is active
- Check API credentials in secrets.toml
- Review logs/errors.log for detailed errors

### CSV Export Issues
- Ensure `logs/` directory exists
- Check file permissions
- Verify disk space

## Dependencies

- `pandas>=2.1.0` - Data manipulation
- `numpy>=1.24.0` - Numerical operations
- `pytz>=2023.3` - Timezone support
- `smartapi-python` - AngelOne SmartAPI
- `logzero` - Logging
- `pyyaml>=6.0` - YAML config parsing
- `tomli` or `tomllib` - TOML config parsing

## License

This implementation is part of the NIFTY Options Trading System.

## Support

For issues or questions:
1. Check `logs/errors.log` for detailed error messages
2. Review API response logs in console output
3. Verify broker credentials and session status

