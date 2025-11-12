# Market Data API Setup for Backtesting

This guide explains how to use the [Market Data API](https://www.marketdata.app/) as an additional data source for backtesting.

## Overview

The Market Data API integration provides an alternative way to fetch historical option chain data for backtesting, complementing the existing CSV and DesiQuant sources.

**Key Features:**
- Historical option chains back to 2005
- Real-time and historical option quotes
- Extensive filtering capabilities (strike, expiration, moneyness, liquidity)
- No local storage required (API-based)

**Important Notes:**
- The implementation does NOT remove or modify CSV or DesiQuant sources
- All three sources (CSV, DesiQuant, Market Data API) remain available
- You can switch between sources via configuration

## Installation

### 1. Install Required Packages

The Market Data API requires the `requests` library:

```bash
pip install requests
```

Or install from requirements.txt:

```bash
pip install -r requirements.txt
```

### 2. Get API Key

1. Visit [https://www.marketdata.app/](https://www.marketdata.app/)
2. Sign up for a free account (100 requests/day free tier)
3. Get your API key from the dashboard

**Note:** You can test the API without a key using AAPL ticker.

## Configuration

### Option 1: Environment Variable (Recommended)

```bash
export MARKETDATA_API_KEY="your_api_key_here"
```

### Option 2: Config File

Edit `config/config.yaml`:

```yaml
backtesting:
  data_source: "marketdata"  # Switch to Market Data API
  
  marketdata:
    enabled: true
    api_key: "your_api_key_here"
    base_url: "https://api.marketdata.app/v1"
    request_delay: 0.2  # Respect rate limits
```

## Usage

### Running Backtest with Market Data API

```bash
# Set API key
export MARKETDATA_API_KEY="your_api_key"

# Run backtest
python run_backtest_marketdata.py
```

### Testing API Connection

```bash
python run_backtest_marketdata.py --test
```

### Switching Between Data Sources

You can switch data sources without code changes:

**Use DesiQuant (default, free):**
```yaml
backtesting:
  data_source: "desiquant"
```

**Use CSV files:**
```yaml
backtesting:
  data_source: "csv"
  csv:
    spot_data_path: "data/historical/nifty_spot_1h.csv"
    options_data_path: "data/historical/nifty_options_1h.csv"
```

**Use Market Data API:**
```yaml
backtesting:
  data_source: "marketdata"
  marketdata:
    enabled: true
    api_key: "your_key"
```

## API Features & Examples

### 1. Live Option Chain

```python
from backtesting import datasource_marketdata

# Get live option chain
data = datasource_marketdata.stream_data(
    symbol="NIFTY",
    start="2023-01-01",
    end="2023-03-31",
    api_key="your_key"
)

spot_1h = data["spot"]        # 1h OHLC for spot
options_1h = data["options"]  # 1h OHLC for options
expiries = data["expiries"]   # Expiry calendar
```

### 2. Historical Option Chain

Fetch historical data for any date back to 2005:

```python
data = datasource_marketdata.stream_data(
    symbol="NIFTY",
    start="2020-01-06",  # Historical date
    end="2020-03-31",
    api_key="your_key"
)
```

### 3. Filtering Options

The API supports extensive filtering (configured in code):

- **By Strike:** Filter specific strike prices
- **By Side:** Call or Put only
- **By Moneyness:** ITM or OTM only
- **By Expiration:** Single date, date range, or DTE
- **By Liquidity:** Min volume, open interest, bid-ask spread

Example filters available in `datasource_marketdata.py`:

```python
source._get_option_chain(
    symbol="NIFTY",
    date="2023-01-15",
    strike=18000,           # Specific strike
    side="call",            # Calls only
    expiration="2023-01-26" # Specific expiry
)
```

## Implementation Details

### Data Structure

The Market Data API source follows the same interface as DesiQuant:

**Returned Data:**
```python
{
    "spot": pd.DataFrame,     # DatetimeIndex with Open/High/Low/Close
    "options": pd.DataFrame,  # timestamp/open/high/low/close/expiry/strike/type
    "expiries": pd.DataFrame  # expiry dates
}
```

### File Structure

```
backtesting/
├── __init__.py
├── datasource_desiquant.py  # DesiQuant S3 source (unchanged)
├── datasource_marketdata.py # NEW: Market Data API source
```

### Strike Selection

Strikes are automatically calculated based on spot price:

- **NIFTY:** Multiples of 50
- **BANKNIFTY:** Multiples of 100
- **FINNIFTY:** Multiples of 50

The system fetches ±500 points around ATM by default.

## Rate Limits & Best Practices

### Free Tier Limits
- **100 requests/day**
- Each date/strike/expiry combination = 1 request
- Use date ranges wisely to minimize requests

### Optimization Tips

1. **Cache Data:** Store fetched data locally to avoid re-fetching
2. **Batch Requests:** Group by expiry dates
3. **Use Filters:** Reduce data volume with API filters
4. **Request Delay:** Built-in 200ms delay between requests

### Cost Estimation

For a 3-month backtest with weekly options:
- ~90 days × 2 strikes (CE+PE) × 1 expiry/week = ~24 requests/week
- Total: ~12 weeks × 24 = ~288 requests

**Recommendation:** Get a paid plan for extensive backtesting.

## Important Limitations

### Current Implementation

⚠️ **Daily Data Only:** Market Data API provides daily option data. The current implementation creates synthetic hourly candles by replicating daily values.

**What this means:**
- Entry/exit prices use daily open/high/low/close
- Intraday price movements are approximated
- Suitable for daily/swing strategies
- May not be accurate for intraday strategies

**Future Enhancement:** Integrate with an intraday options data provider or implement proper interpolation logic.

### Comparison with DesiQuant

| Feature | DesiQuant | Market Data API |
|---------|-----------|-----------------|
| **Data Resolution** | 1-minute (resampled to 1h) | Daily (synthetic 1h) |
| **History** | 2+ years | Back to 2005 |
| **Cost** | Free | 100 req/day free, then paid |
| **Setup** | No key required | API key required |
| **Coverage** | NIFTY, BANKNIFTY, FINNIFTY | US stocks + indices |
| **Best For** | Intraday strategies | Daily/swing strategies |

## Troubleshooting

### Connection Failed

```
MarketDataAPIError: Request failed
```

**Solutions:**
1. Check internet connection
2. Verify API key is correct
3. Check rate limit (100/day on free tier)
4. Ensure API endpoint is accessible

### Empty Data Returned

```
No option data available
```

**Solutions:**
1. Check symbol is supported (NIFTY may not be in Market Data API)
2. Try with AAPL for testing
3. Verify date range is valid
4. Check if options existed on that date

### Rate Limit Exceeded

```
API Error: Rate limit exceeded
```

**Solutions:**
1. Wait for rate limit reset (daily)
2. Upgrade to paid plan
3. Cache previous results
4. Use DesiQuant source for development

## Example: Complete Backtest

```python
#!/usr/bin/env python3
import os
from backtesting import datasource_marketdata
from engine.backtest_engine import BacktestEngine

# Set API key
api_key = os.environ.get("MARKETDATA_API_KEY")

# Fetch data
data = datasource_marketdata.stream_data(
    symbol="NIFTY",
    start="2023-01-01",
    end="2023-03-31",
    api_key=api_key
)

# Run backtest
config = {
    "strategy": {
        "premium_sl_pct": 35.0,
        "lock1_gain_pct": 60.0,
        "lock2_gain_pct": 80.0,
        "lock3_gain_pct": 100.0
    },
    "lot_size": 75,
    "initial_capital": 100000
}

engine = BacktestEngine(config)
results = engine.run_backtest(
    data_1h=data["spot"],
    initial_capital=100000,
    options_df=data["options"],
    expiries_df=data["expiries"]
)

# Print results
print(f"Total Trades: {results['total_trades']}")
print(f"Win Rate: {results['win_rate']:.2f}%")
print(f"Total P&L: ₹{results['total_pnl']:,.2f}")
print(f"Return: {results['return_pct']:.2f}%")
```

## Support

- **Market Data API Docs:** https://www.marketdata.app/docs/
- **API Status:** https://status.marketdata.app/
- **Support Email:** support@marketdata.app

## Next Steps

1. Get your API key from [marketdata.app](https://www.marketdata.app/)
2. Test the connection: `python run_backtest_marketdata.py --test`
3. Run your first backtest: `python run_backtest_marketdata.py`
4. Compare results with DesiQuant source
5. Choose the best source for your strategy

---

**Remember:** This is an ADDITIONAL data source. Your existing CSV and DesiQuant implementations remain unchanged and fully functional.
