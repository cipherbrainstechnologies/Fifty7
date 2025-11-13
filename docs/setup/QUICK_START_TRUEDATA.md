# Quick Start: TrueData Integration

**Time to setup**: 5 minutes  
**Status**: Optional (DesiQuant remains default)

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd /workspace
pip install -r requirements.txt
```

This installs `truedata-ws` (TrueData Python SDK).

---

### 2. Set Credentials

**Option A: Environment Variables** (Recommended)

```bash
export TRUEDATA_USERNAME="your_username"
export TRUEDATA_PASSWORD="your_password"
```

**Option B: Config File**

Edit `config/config.yaml`:

```yaml
backtesting:
  truedata:
    enabled: true
    username: "your_username"
    password: "your_password"
```

---

### 3. Test Connection

```bash
python run_backtest_truedata.py --test
```

**Expected output**:
```
Testing TrueData API connection...
Connecting with username: your_username
Fetching spot data for NIFTY from 2024-11-01 to 2024-11-02...
✓ Data fetch complete:
   - Spot: 12 candles
   - Options: 24 candles
   - Expiries: 1 dates
✓ Connection test passed
  Sample data: 12 spot candles
```

---

### 4. Run Backtest

```bash
python run_backtest_truedata.py
```

**That's it!** Your backtest will now use TrueData instead of DesiQuant.

---

## 🔄 Switch Back to DesiQuant (Free)

**Anytime**, just:

```bash
# Remove credentials
unset TRUEDATA_USERNAME
unset TRUEDATA_PASSWORD

# Or disable in config
```

Edit `config/config.yaml`:
```yaml
backtesting:
  truedata:
    enabled: false  # Disable TrueData
```

Script will automatically fall back to DesiQuant (free).

---

## 📊 Compare Data Sources

Run backtests with both sources and compare:

```bash
# Test with DesiQuant (free)
python run_backtest_marketdata.py

# Test with TrueData (paid)
export TRUEDATA_USERNAME="your_username"
export TRUEDATA_PASSWORD="your_password"
python run_backtest_truedata.py
```

Compare:
- Data quality
- Historical range (2015+ vs 2021+)
- Results consistency

---

## ⚙️ Configuration Options

### Strike Step (per symbol)

Edit `config/config.yaml`:

```yaml
backtesting:
  truedata:
    strike_step:
      NIFTY: 50        # NIFTY strikes: 24000, 24050, 24100...
      BANKNIFTY: 100   # BANKNIFTY strikes: 50000, 50100...
      FINNIFTY: 50
      MIDCPNIFTY: 25
```

### Data Source Selection

```yaml
backtesting:
  data_source: "truedata"  # Options: "desiquant", "truedata", "marketdata"
```

---

## 🛠️ Troubleshooting

### Issue: "truedata-ws not installed"

```bash
pip install truedata-ws
```

### Issue: "Credentials not found"

Check environment variables:
```bash
echo $TRUEDATA_USERNAME
echo $TRUEDATA_PASSWORD
```

Set if empty:
```bash
export TRUEDATA_USERNAME="your_username"
export TRUEDATA_PASSWORD="your_password"
```

### Issue: "Connection test failed"

1. **Verify credentials** are correct
2. **Check subscription** is active at https://truedata.in
3. **Test network** connection
4. **Try again** (API might be temporarily unavailable)

---

## 💰 Cost

**TrueData Subscription**:
- Historical Data: ₹2,000-3,000/month
- Subscribe: https://truedata.in

**DesiQuant**:
- FREE ✅

---

## ✅ What's Non-Disruptive

Your existing setup remains **completely unchanged**:

- ✅ DesiQuant is still the default
- ✅ Angel One live trading unaffected
- ✅ Existing backtests still work
- ✅ No code changes required
- ✅ Can switch back anytime

TrueData is **opt-in** and **optional**.

---

## 📚 Full Documentation

- **Integration Guide**: [TRUEDATA_INTEGRATION_GUIDE.md](./TRUEDATA_INTEGRATION_GUIDE.md)
- **Compatibility Analysis**: [TRUEDATA_COMPATIBILITY_ANALYSIS.md](./TRUEDATA_COMPATIBILITY_ANALYSIS.md)
- **Runner Script**: `/workspace/run_backtest_truedata.py`

---

## 🎯 Recommendation

### Now (Testing Phase)
✅ **Use DesiQuant** (FREE)  
- No cost
- Sufficient for validation (2021-2024 data)
- Already working

### Later (When Profitable)
✅ **Consider TrueData** (PAID)  
- Professional data quality
- Longer history (2015+)
- Professional support
- Worth it if profits > ₹5,000/month

---

**Status**: ✅ Integration Complete  
**Default**: DesiQuant (FREE)  
**Ready to use**: TrueData (PAID, when you subscribe)
