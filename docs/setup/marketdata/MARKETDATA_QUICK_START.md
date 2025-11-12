# Market Data API - Quick Start Guide

Get up and running with Market Data API for backtesting in 5 minutes.

## Quick Setup (3 Steps)

### 1. Get API Key

Visit [https://www.marketdata.app/](https://www.marketdata.app/) and sign up for free (100 requests/day).

### 2. Set API Key

```bash
export MARKETDATA_API_KEY="your_api_key_here"
```

### 3. Run Test

```bash
python run_backtest_marketdata.py --test
```

Expected output:
```
✓ Market Data API connection successful
```

## Run Your First Backtest

```bash
# Ensure API key is set
export MARKETDATA_API_KEY="your_api_key_here"

# Run backtest
python run_backtest_marketdata.py
```

## Switch Data Sources

Edit `config/config.yaml`:

```yaml
backtesting:
  data_source: "marketdata"  # Change this line
  
  marketdata:
    enabled: true
    api_key: "your_key"  # Or use environment variable
```

**Options:**
- `"desiquant"` - Free, no setup (default)
- `"csv"` - Use your local CSV files  
- `"marketdata"` - Market Data API (this guide)

## Programmatic Usage

```python
from backtesting import datasource_marketdata
from engine.backtest_engine import BacktestEngine

# Fetch data
data = datasource_marketdata.stream_data(
    symbol="NIFTY",
    start="2023-01-01",
    end="2023-03-31",
    api_key="your_key"  # Or read from config/env
)

# Run backtest
config = {
    "strategy": {...},
    "lot_size": 75
}

engine = BacktestEngine(config)
results = engine.run_backtest(
    data_1h=data["spot"],
    options_df=data["options"],
    expiries_df=data["expiries"]
)

print(f"Total P&L: ₹{results['total_pnl']:,.2f}")
```

## Important Notes

### ✅ What's Preserved
- CSV data source (unchanged)
- DesiQuant data source (unchanged)
- Backtest engine (unchanged)
- All existing functionality (unchanged)

### ⚠️ Limitations
- Daily data only (creates synthetic hourly)
- 100 requests/day on free tier
- May not have complete NIFTY data
- Best for daily/swing strategies

### 💡 Recommendations
- **Development:** Use DesiQuant (free, unlimited)
- **Historical Analysis:** Use Market Data API
- **Intraday Strategies:** Use DesiQuant (real 1-min data)

## Troubleshooting

### Connection Failed
```bash
# Check API key
echo $MARKETDATA_API_KEY

# Test with AAPL (no key required)
python run_backtest_marketdata.py --test
```

### Rate Limit Hit
```
API Error: Rate limit exceeded
```

Wait 24 hours or upgrade to paid plan. Use DesiQuant in the meantime:

```yaml
backtesting:
  data_source: "desiquant"  # Switch back
```

## Next Steps

1. ✅ Run test: `python run_backtest_marketdata.py --test`
2. ✅ Run backtest: `python run_backtest_marketdata.py`
3. 📖 Read full docs: `MARKETDATA_API_SETUP.md`
4. 📊 Compare with DesiQuant results
5. 🚀 Choose best source for your needs

## Files Reference

- **Setup Guide:** `MARKETDATA_API_SETUP.md`
- **Implementation Details:** `MARKETDATA_IMPLEMENTATION_SUMMARY.md`
- **Example Script:** `run_backtest_marketdata.py`
- **Data Source Code:** `backtesting/datasource_marketdata.py`
- **Config:** `config/config.yaml`

## Support

- **API Docs:** https://www.marketdata.app/docs/
- **Issue?** Check `MARKETDATA_API_SETUP.md` Troubleshooting section

---

**TL;DR:** Get API key → Set env var → Run `python run_backtest_marketdata.py`
