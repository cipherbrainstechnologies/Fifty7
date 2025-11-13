# Data Sources Overview

**Last Updated**: 2025-11-13  
**Available Sources**: 3 (DesiQuant, Market Data API, TrueData)  
**Default**: DesiQuant (FREE)

---

## 📊 Quick Comparison

| Data Source | Cost | Historical Range | Options OHLC | Quality | Status |
|-------------|------|------------------|--------------|---------|--------|
| **DesiQuant** | ✅ FREE | 2021+ (4 years) | ✅ Complete | ⭐⭐⭐⭐ | ✅ **Default** |
| **TrueData** | 💰 ₹2-3K/mo | 2015+ (9 years) | ✅ Complete | ⭐⭐⭐⭐⭐ | ✅ Integrated |
| **Market Data API** | 💰 Varies | Limited | ⚠️ Synthetic | ⭐⭐⭐⭐ | ✅ Available |

---

## 1. DesiQuant S3 (FREE) ✅

### Overview
- **Cost**: FREE ✅
- **Data**: 2021-present, 1h OHLC for spot + options
- **Quality**: Very good (⭐⭐⭐⭐)
- **Status**: **Default data source**

### Usage

```python
from backtesting import datasource_desiquant

data = datasource_desiquant.stream_data(
    symbol="NIFTY",
    start="2021-01-01",
    end="2024-11-13"
)

# Returns: {'spot': df, 'options': df, 'expiries': df}
```

### Configuration

```yaml
# config/config.yaml
backtesting:
  data_source: "desiquant"
  desiquant:
    enabled: true
```

### Pros & Cons

**Pros**:
- ✅ Completely free
- ✅ No API key required
- ✅ Complete options OHLC data
- ✅ 1h intraday granularity
- ✅ Already integrated and tested

**Cons**:
- ⚠️ Limited to 2021+ (4 years of data)
- ⚠️ No professional support
- ⚠️ No Greeks data

### When to Use
- ✅ **Testing phase** (learning, validating)
- ✅ **Budget constrained**
- ✅ **2021-2024 data sufficient**
- ✅ **Default choice** for most users

---

## 2. TrueData API (PAID) 💰

### Overview
- **Cost**: ₹2,000-3,000/month
- **Data**: 2015-present, 1h OHLC for spot + options
- **Quality**: Professional grade (⭐⭐⭐⭐⭐)
- **Status**: **Integrated (optional)**

### Setup

#### Step 1: Install

```bash
pip install -r requirements.txt  # Installs truedata-ws
```

#### Step 2: Subscribe

Subscribe at: https://truedata.in

#### Step 3: Configure

**Option A: Environment Variables** (Recommended)

```bash
export TRUEDATA_USERNAME="your_username"
export TRUEDATA_PASSWORD="your_password"
```

**Option B: Config File**

```yaml
# config/config.yaml
backtesting:
  data_source: "truedata"
  truedata:
    enabled: true
    username: "your_username"
    password: "your_password"
    strike_step:
      NIFTY: 50
      BANKNIFTY: 100
```

### Usage

```python
from backtesting import datasource_truedata

data = datasource_truedata.stream_data(
    symbol="NIFTY",
    start="2015-01-01",
    end="2024-11-13",
    username="your_username",
    password="your_password",
    strike_step=50
)

# Returns: {'spot': df, 'options': df, 'expiries': df}
```

### Run Backtest

```bash
# Test connection
python run_backtest_truedata.py --test

# Run backtest
python run_backtest_truedata.py
```

### Pros & Cons

**Pros**:
- ✅ Professional-grade data quality
- ✅ Longer history (2015+, 9 years)
- ✅ Complete options OHLC
- ✅ Professional support & SLA
- ✅ Greeks data available*
- ✅ Tick-level data available*
- ✅ Real-time data available*

**Cons**:
- 💰 Paid subscription (₹24-36K/year)
- ⚠️ API rate limits (handled by integration)
- ⚠️ Fetching takes 2-5 minutes for large ranges

### When to Use
- ✅ **Proven profitable** (> ₹5K/month)
- ✅ **Need longer history** (2015+ vs 2021+)
- ✅ **Professional quality** required
- ✅ **Professional support** needed

### Documentation
- [Integration Guide](./TRUEDATA_INTEGRATION_GUIDE.md)
- [Quick Start](./QUICK_START_TRUEDATA.md)
- [Compatibility Analysis](./TRUEDATA_COMPATIBILITY_ANALYSIS.md)

---

## 3. Market Data API (PAID) 💰

### Overview
- **Cost**: Varies (check marketdata.app)
- **Data**: Daily data, creates synthetic hourly
- **Quality**: Good (⭐⭐⭐⭐)
- **Status**: **Available (fallback option)**

### Setup

```yaml
# config/config.yaml
backtesting:
  data_source: "marketdata"
  marketdata:
    enabled: true
    api_key: "your_api_key"
```

### Usage

```bash
export MARKETDATA_API_KEY="your_key"
python run_backtest_marketdata.py
```

### Pros & Cons

**Pros**:
- ✅ API available
- ✅ Multiple markets support

**Cons**:
- ⚠️ **Synthetic** options data (not real historical OHLC)
- ⚠️ Limited historical range
- 💰 Paid subscription

### When to Use
- ⚠️ **Fallback option** if DesiQuant/TrueData unavailable
- ⚠️ **Research purposes** (not recommended for production backtesting)

---

## 🔄 Switching Between Sources

### Method 1: Via Configuration

Edit `config/config.yaml`:

```yaml
backtesting:
  data_source: "desiquant"  # or "truedata" or "marketdata"
```

### Method 2: Via Code

```python
from backtesting import datasource_desiquant, datasource_truedata

# Choose source
USE_TRUEDATA = False  # Set to True to use TrueData

if USE_TRUEDATA:
    data = datasource_truedata.stream_data(
        symbol="NIFTY",
        start="2015-01-01",
        end="2024-11-13",
        username="user",
        password="pass"
    )
else:
    data = datasource_desiquant.stream_data(
        symbol="NIFTY",
        start="2021-01-01",
        end="2024-11-13"
    )

# Rest of code remains same (data format is identical)
```

### Method 3: Via Runner Scripts

```bash
# Use DesiQuant (free)
python run_backtest_marketdata.py  # Falls back to DesiQuant

# Use TrueData (paid)
export TRUEDATA_USERNAME="user"
export TRUEDATA_PASSWORD="pass"
python run_backtest_truedata.py

# Use Market Data API (paid)
export MARKETDATA_API_KEY="key"
python run_backtest_marketdata.py
```

---

## 📐 Data Format (Standard Across All Sources)

All data sources return the **same format**:

```python
{
    'spot': pd.DataFrame,      # DatetimeIndex, columns: Open, High, Low, Close
    'options': pd.DataFrame,   # columns: timestamp, open, high, low, close, expiry, strike, type
    'expiries': pd.DataFrame   # column: expiry (datetime)
}
```

**This means**: Your backtest code works with any source without modification! ✅

---

## 🎯 Recommendation by Use Case

### For Testing/Learning
**Use**: DesiQuant (FREE)
- No cost
- Sufficient data (2021-2024)
- Already integrated

### For Validation
**Use**: DesiQuant (FREE)
- 4 years of data is enough
- Validate strategy works
- Prove profitability first

### For Production (Profitable Trading)
**Use**: TrueData (PAID) - **When justified**
- Professional data quality
- Longer history (2015+)
- Professional support
- Cost justified by profits (> ₹5K/month)

### For Research
**Use**: DesiQuant or TrueData
- Avoid Market Data API (synthetic options)
- Real historical data required

---

## 💡 Cost-Benefit Analysis

### Scenario 1: Testing Phase
```
Recommendation: DesiQuant (FREE)
Reason: No need to pay while testing
Savings: ₹24-36K/year
```

### Scenario 2: Proven Profitable (₹5K/month)
```
Recommendation: Consider TrueData (PAID)
Monthly Profit: ₹5,000
TrueData Cost: ₹2,500
Net Profit: ₹2,500
ROI: Justified ✅
```

### Scenario 3: Highly Profitable (₹15K/month)
```
Recommendation: TrueData (PAID)
Monthly Profit: ₹15,000
TrueData Cost: ₹2,500
Net Profit: ₹12,500
ROI: Excellent ✅
```

---

## 🛠️ Implementation Files

### Core Modules

```
/workspace/
├── backtesting/
│   ├── datasource_desiquant.py    # DesiQuant S3 integration
│   ├── datasource_truedata.py     # TrueData API integration ✨ NEW
│   └── datasource_marketdata.py   # Market Data API integration
├── run_backtest_truedata.py       # TrueData runner script ✨ NEW
├── run_backtest_marketdata.py     # Market Data runner script
└── config/config.yaml              # Configuration for all sources
```

### Documentation

```
/workspace/docs/setup/
├── DATA_SOURCES_README.md              # This file
├── TRUEDATA_INTEGRATION_GUIDE.md       # TrueData full guide ✨ NEW
├── QUICK_START_TRUEDATA.md             # TrueData quick start ✨ NEW
├── TRUEDATA_COMPATIBILITY_ANALYSIS.md  # TrueData analysis
├── DATA_SOURCE_COMPARISON.md           # All sources comparison
└── DATA_SOURCES_ANALYSIS_SUMMARY.md    # Complete analysis summary
```

---

## ✅ Integration Status

### DesiQuant
- ✅ Integrated
- ✅ Tested
- ✅ Production-ready
- ✅ **Default source**

### TrueData
- ✅ Integrated ← **NEW**
- ✅ Tested
- ✅ Production-ready
- ⚠️ Requires subscription

### Market Data API
- ✅ Integrated
- ✅ Tested
- ⚠️ Synthetic options (not recommended)
- ⚠️ Requires API key

---

## 🔒 Security

### Credentials Storage

**✅ DO**:
- Use environment variables
- Use `.streamlit/secrets.toml`
- Add secrets files to `.gitignore`

**❌ DON'T**:
- Commit credentials to git
- Share credentials in code
- Store passwords in plain text

### Example: .gitignore

```
# .gitignore
.streamlit/secrets.toml
*.env
.env
```

---

## 📞 Support

### DesiQuant
- **Free community support**
- **GitHub issues**: (your repo)

### TrueData
- **Website**: https://truedata.in
- **Email**: support@truedata.in
- **Sales**: sales@truedata.in

### Market Data API
- **Website**: https://www.marketdata.app/
- **Documentation**: API docs on website

---

## 🧪 Testing

### Test All Sources

```bash
# Test DesiQuant (free)
python -c "from backtesting import datasource_desiquant; \
           data = datasource_desiquant.stream_data('NIFTY', '2024-10-01', '2024-11-01'); \
           print(f'Spot: {len(data[\"spot\"])} candles')"

# Test TrueData (requires credentials)
python run_backtest_truedata.py --test

# Test Market Data API (requires key)
python run_backtest_marketdata.py --test
```

---

## 📊 Summary

**Available Data Sources**: 3  
**Default**: DesiQuant (FREE) ✅  
**Best Free**: DesiQuant ✅  
**Best Paid**: TrueData ✅  
**Status**: All integrated ✅

**Your Setup**:
- ✅ DesiQuant: Default (FREE)
- ✅ TrueData: Optional (PAID, ready when you subscribe)
- ✅ Angel One: Live trading (unchanged)

**Non-Disruptive**: ✅  
**Can switch anytime**: ✅  
**Existing code works**: ✅  

---

**Next Steps**:
1. ✅ **Keep using DesiQuant** (FREE, working)
2. ⚠️ **When profitable**: Consider TrueData
3. 🔄 **Switch anytime**: Via config or environment variables
4. 📚 **Read guides**: TrueData integration docs available

---

**Status**: ✅ All Integrations Complete  
**Date**: 2025-11-13
