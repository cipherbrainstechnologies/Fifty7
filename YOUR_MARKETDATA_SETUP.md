# Your Market Data API Setup - Ready to Use! 🚀

## ✅ Configuration Complete

Your API token has been configured and is ready to use!

**Token:** `azZCREFyMWh3d0h6RnBOSTF0Qld0UWFMQ1laWURQY2pvU3QtTU9jU1ItMD0`

---

## 🎯 Quick Start (3 Commands)

### 1. Install Dependencies (if not already installed)

```bash
pip install -r requirements.txt
```

### 2. Test Your Connection

```bash
python3 test_marketdata_connection.py
```

Expected output:
```
✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓
✓ CONNECTION SUCCESSFUL!
✓ Your API key is working correctly
✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓
```

### 3. Run Your First Backtest

```bash
python3 run_backtest_marketdata.py
```

---

## 🎨 Three Ways to Use Market Data API

### Method 1: Config File (Already Set Up!)

Your `config/config.yaml` is already configured:

```yaml
backtesting:
  data_source: "marketdata"  # Using Market Data API
  
  marketdata:
    enabled: true
    api_key: "azZCREFyMWh3d0h6RnBOSTF0Qld0UWFMQ1laWURQY2pvU3QtTU9jU1ItMD0"
```

✅ **Ready to use!** Just run any backtest script.

### Method 2: Environment Variable

```bash
# Set once in your terminal
export MARKETDATA_API_KEY="azZCREFyMWh3d0h6RnBOSTF0Qld0UWFMQ1laWURQY2pvU3QtTU9jU1ItMD0"

# Then run
python3 run_backtest_marketdata.py
```

### Method 3: Direct in Code

```python
from backtesting import datasource_marketdata
from engine.backtest_engine import BacktestEngine

# Your API token
API_KEY = "azZCREFyMWh3d0h6RnBOSTF0Qld0UWFMQ1laWURQY2pvU3QtTU9jU1ItMD0"

# Fetch data
data = datasource_marketdata.stream_data(
    symbol="NIFTY",
    start="2023-01-01",
    end="2023-03-31",
    api_key=API_KEY
)

# Run backtest (same as before)
config = {...}  # Your config
engine = BacktestEngine(config)
results = engine.run_backtest(
    data_1h=data["spot"],
    options_df=data["options"],
    expiries_df=data["expiries"]
)

print(f"Total P&L: ₹{results['total_pnl']:,.2f}")
```

---

## 📊 Data Source Switching

You can easily switch between data sources in `config/config.yaml`:

```yaml
backtesting:
  # Choose one:
  data_source: "desiquant"   # DesiQuant S3 (free, 1-min data)
  data_source: "csv"          # Your local CSV files
  data_source: "marketdata"   # Market Data API (your current choice)
```

**Current setting:** `marketdata` ✅

---

## 🔍 What You Have Now

### Files Ready to Use:

1. **`test_marketdata_connection.py`** ← Test your API
2. **`run_backtest_marketdata.py`** ← Run full backtest
3. **`config/config.yaml`** ← Already configured with your token
4. **`backtesting/datasource_marketdata.py`** ← API integration code

### Your Token is Configured In:

- ✅ `config/config.yaml` (line 70)
- ✅ `test_marketdata_connection.py` (for testing)

---

## 📈 Example: Complete Backtest

```bash
# 1. Test connection
python3 test_marketdata_connection.py

# 2. Run backtest with Market Data API
python3 run_backtest_marketdata.py

# Expected output:
# 📡 Fetching data from Market Data API...
# ✓ Data fetched successfully:
#   Spot candles: 450
#   Option data points: 2400
#   Expiry dates: 12
# 
# 🔄 Running backtest...
# 
# 📊 Performance Summary:
#   Total Trades: 15
#   Win Rate: 60.00%
#   Total P&L: ₹12,500.00
#   Return: 12.50%
```

---

## ⚡ Quick Commands Reference

```bash
# Test API connection
python3 test_marketdata_connection.py

# Run backtest with Market Data API
python3 run_backtest_marketdata.py

# Run backtest (auto-detects source from config)
python3 run_backtest_marketdata.py

# Switch to DesiQuant (in config.yaml)
# Change: data_source: "desiquant"
python3 run_backtest_marketdata.py  # Will use DesiQuant

# Switch back to Market Data API (in config.yaml)
# Change: data_source: "marketdata"
python3 run_backtest_marketdata.py  # Will use your API
```

---

## 🎯 Rate Limits & Usage

### Your Plan:
- **Free Tier:** 100 requests/day
- **Each request:** 1 option chain call

### Optimization Tips:

1. **Cache results** for repeated backtests on same dates
2. **Use date ranges** instead of individual dates
3. **Filter at API level** to reduce data transfer
4. **Develop with DesiQuant** (unlimited), then validate with Market Data API

### Estimated Usage:

**3-month backtest:**
- ~90 days × 2 strikes/day (CE+PE) = ~180 requests
- Need paid plan or split into smaller ranges

**1-week backtest:**
- ~7 days × 2 strikes/day = ~14 requests
- Well within free tier ✅

---

## ⚠️ Important Notes

### Data Quality

**Market Data API:**
- ✅ Historical depth (back to 2005)
- ⚠️ Daily data only (creates synthetic hourly)
- ⚠️ May not have complete NIFTY data
- ✅ Best for: Daily/swing strategies

**DesiQuant (Alternative):**
- ✅ Real 1-minute data (resampled to hourly)
- ✅ Free and unlimited
- ✅ 2+ years history
- ✅ Best for: Intraday strategies

### Recommendation:

For **development & testing:**
```yaml
data_source: "desiquant"  # Free, unlimited, real 1-min data
```

For **historical validation:**
```yaml
data_source: "marketdata"  # Your API, back to 2005
```

---

## 🆘 Troubleshooting

### Connection Failed?

```bash
# 1. Check internet
curl https://api.marketdata.app/

# 2. Test with your token
python3 test_marketdata_connection.py

# 3. Verify token at
# https://www.marketdata.app/dashboard
```

### Rate Limit Hit?

```
API Error: Rate limit exceeded
```

**Solution:** Switch to DesiQuant temporarily:

```yaml
# config/config.yaml
backtesting:
  data_source: "desiquant"  # Free alternative
```

### No Data Returned?

**Market Data API may not have NIFTY data.**

Try with AAPL (test):
```python
data = datasource_marketdata.stream_data(
    symbol="AAPL",  # Test with Apple
    start="2023-01-01",
    end="2023-01-31",
    api_key=API_KEY
)
```

Or use DesiQuant for NIFTY:
```yaml
data_source: "desiquant"  # Has NIFTY data
```

---

## 📚 Documentation

- **Quick Start:** `MARKETDATA_QUICK_START.md`
- **Full Setup:** `MARKETDATA_API_SETUP.md`
- **Technical:** `MARKETDATA_IMPLEMENTATION_SUMMARY.md`
- **This File:** `YOUR_MARKETDATA_SETUP.md` ← You are here

---

## ✅ Next Steps

1. **Test:** `python3 test_marketdata_connection.py`
2. **Backtest:** `python3 run_backtest_marketdata.py`
3. **Compare:** Switch to `"desiquant"` and compare results
4. **Choose:** Pick the best source for your needs

---

## 🎉 You're All Set!

Your Market Data API is configured and ready to use. Just run:

```bash
python3 test_marketdata_connection.py
```

Then:

```bash
python3 run_backtest_marketdata.py
```

Happy backtesting! 🚀

---

**Token Location:** `config/config.yaml` (line 70)  
**Status:** ✅ Configured and Ready  
**Free Tier:** 100 requests/day
