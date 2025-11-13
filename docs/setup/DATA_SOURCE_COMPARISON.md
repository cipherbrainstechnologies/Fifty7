# Backtesting Data Sources Comparison

**Last Updated**: 2025-11-13  
**Strategy**: Inside Bar Breakout (1h intraday)

---

## Quick Verdict Summary

| Data Source | Compatibility | Recommendation |
|-------------|---------------|----------------|
| **DesiQuant S3** | ✅ **FULLY COMPATIBLE** | ✅ **USE THIS** (Primary) |
| **Yahoo Finance** | 🔴 **NOT COMPATIBLE** | ❌ Do Not Use |
| **Investing.com** | 🔴 **NOT COMPATIBLE** | ❌ Do Not Use |
| **Kaggle mlcroissant** | 🔴 **NOT COMPATIBLE** | ❌ Do Not Use |
| **Market Data API** | ⚠️ **PARTIAL** | ⚠️ Alternative (Paid) |

---

## Detailed Comparison Matrix

### Critical Requirements Check

| Feature | DesiQuant | Yahoo Finance | Investing.com | Kaggle | MarketData API |
|---------|-----------|---------------|---------------|--------|----------------|
| **1h Intraday OHLC** | ✅ Yes | ⚠️ Limited | 🔴 **NO** | 🔴 No (daily) | ⚠️ Yes (synthetic) |
| **Options Historical Data** | ✅ Yes | 🔴 **NO** | 🔴 **NO** | ⚠️ Yes (daily) | ⚠️ Limited |
| **Multi-Year History** | ✅ 2021-present | 🔴 2 years max | ⚠️ Daily only | 🔴 2024 only | ⚠️ Varies |
| **All Strikes Coverage** | ✅ Yes | 🔴 **NO** | 🔴 **NO** | ✅ Yes | ⚠️ Limited |
| **Expiry Calendar** | ✅ Full history | 🔴 Current only | 🔴 **NO** | ✅ Yes | ⚠️ Synthetic |
| **Free Access** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | 🔴 Paid tiers |
| **API Stability** | ✅ High | ⚠️ Unofficial | 🔴 **Poor** | ✅ High | ⚠️ Medium |
| **Setup Complexity** | ✅ Low | ✅ Low | ⚠️ Medium | ⚠️ Medium | ⚠️ Medium |

---

## Deal-Breakers by Source

### 🔴 Yahoo Finance
**Critical Issue**: No historical options OHLC data
- Can only get current options chain
- Cannot simulate historical option trades
- Cannot backtest option strategies
- **Verdict**: Unusable for options backtesting

### 🔴 Investing.com
**Critical Issues**: No 1h intraday + No options data
- investpy library provides only daily data
- No historical options data at all
- Web scraping violates ToS and is unreliable
- **Verdict**: Worst option - missing both requirements

### 🔴 Kaggle mlcroissant
**Critical Issue**: Daily data only (not 1h intraday)
- Strategy requires hourly breakout detection
- Entry/exit timing needs 1h precision
- Limited to 2024 data
- **Verdict**: Wrong granularity for current strategy

### ⚠️ Market Data API
**Limitations**:
- Requires paid API key
- Synthetic hourly data (may be daily resampled)
- Limited historical options data
- **Verdict**: Fallback option if DesiQuant unavailable

---

## Data Quality Comparison

### Spot Data (NIFTY Index)

| Metric | DesiQuant | Yahoo Finance | Investing.com | Kaggle |
|--------|-----------|---------------|---------------|--------|
| **Granularity** | 1h true intraday | 1h (limited) | Daily only | Daily |
| **History** | 2021-present | Last 2 years | Multi-year | 2024 only |
| **Completeness** | 99.9% | ~95% | ~90% | ~98% |
| **Quality** | Professional | Consumer | Consumer | Unknown |
| **Gaps** | Rare | Occasional | Occasional | Unknown |

### Options Data

| Metric | DesiQuant | Yahoo Finance | Investing.com | Kaggle |
|--------|-----------|---------------|---------------|--------|
| **Historical OHLC** | ✅ Yes | 🔴 **None** | 🔴 **None** | ⚠️ Daily only |
| **Strike Coverage** | All strikes | N/A | N/A | All strikes |
| **Time Series** | Hourly | **None** | **None** | Daily |
| **Volume/OI** | Limited | Current only | N/A | Unknown |
| **Expiries** | All historical | Current only | N/A | 2024 only |

---

## Use Case Recommendations

### ✅ For Your Current Strategy (1h Inside Bar + Options)
**Use**: **DesiQuant S3**
- Reason: Only source with complete 1h options data
- Alternative: None (other sources incompatible)

### ⚠️ For Daily Timeframe Strategy Development
**Use**: **Kaggle** or **Yahoo Finance**
- Reason: Different strategy needed anyway
- Note: Would require strategy redesign

### ✅ For Live Trading Data
**Use**: **Your Broker API** (AngelOne)
- Yahoo Finance could supplement for index prices
- Not for backtesting

### ✅ For Cross-Validation
**Use**: **Yahoo Finance** spot data
- Validate DesiQuant spot data accuracy
- Correlation should be > 0.99

---

## Integration Status

### ✅ Currently Integrated
- **DesiQuant S3**: `backtesting/datasource_desiquant.py` ✅
- **Market Data API**: `backtesting/datasource_marketdata.py` ✅

### ❌ Not Integrated (Not Recommended)
- **Yahoo Finance**: Not needed (missing options data)
- **Investing.com**: Not suitable (missing both 1h and options data)
- **Kaggle mlcroissant**: Not suitable (wrong granularity)

---

## Cost Analysis

| Source | Setup Cost | Monthly Cost | Data Access |
|--------|------------|--------------|-------------|
| **DesiQuant S3** | $0 | $0 | Free (public bucket) |
| **Yahoo Finance** | $0 | $0 | Free (with limits) |
| **Investing.com** | $0 | $0 | Free (limited) |
| **Kaggle** | $0 | $0 | Free (with account) |
| **Market Data API** | $0 | $30-$100+ | Paid tiers |

**Winner**: DesiQuant (free + best data)

---

## Performance Comparison

### Data Fetch Speed (1 month of data)

| Source | Spot Data | Options Data | Total Time |
|--------|-----------|--------------|------------|
| **DesiQuant** | ~2-5s | ~10-20s | ~15-25s |
| **Yahoo Finance** | ~3-8s | N/A | N/A |
| **Investing.com** | ~5-10s | N/A | N/A |
| **Kaggle** | ~5-15s | ~10-30s | ~15-45s |
| **Market Data API** | ~10-30s | ~30-120s | ~40-150s |

**Note**: Times vary based on network and API rate limits

---

## Reliability Scores (1-10)

| Source | Data Availability | API Stability | Data Quality |
|--------|-------------------|---------------|--------------|
| **DesiQuant** | 9/10 | 9/10 | 9/10 |
| **Yahoo Finance** | 6/10 | 6/10 | 7/10 |
| **Investing.com** | 4/10 | 4/10 | 6/10 |
| **Kaggle** | 7/10 | 8/10 | ?/10 |
| **Market Data API** | 7/10 | 7/10 | ?/10 |

---

## Final Recommendations

### For Current Backtesting Needs:

1. **Primary Source**: **DesiQuant S3** ✅
   - Reason: Only source with complete 1h options data
   - Status: Already integrated and working
   - Action: **Keep using this**

2. **Backup Source**: None needed
   - DesiQuant is reliable enough
   - No comparable alternative exists

3. **Do NOT Integrate**:
   - ❌ Yahoo Finance (missing options data)
   - ❌ Investing.com (missing both 1h and options data)
   - ❌ Kaggle mlcroissant (wrong granularity)

### For Future Considerations:

- If DesiQuant discontinues: Consider paid Market Data API
- If daily strategy needed: Kaggle could be useful
- If live validation needed: Yahoo Finance for spot cross-check

---

## Decision Matrix

```
Need 1h intraday options data?
├── YES → Use DesiQuant S3 ✅
└── NO
    ├── Need daily options data? → Use Kaggle ⚠️
    ├── Need spot data only? → Use Yahoo Finance ⚠️
    └── Need live data? → Use Broker API ✅
```

---

## Summary

**Clear Winner**: **DesiQuant S3**

**Reasons**:
1. ✅ Only source with historical 1h options OHLC
2. ✅ Multi-year coverage (2021-present)
3. ✅ Free and reliable
4. ✅ Already integrated
5. ✅ Professional data quality

**Action**: **Continue using DesiQuant S3** - no changes needed.

---

## Related Documents

- [Yahoo Finance Compatibility Analysis](./YAHOO_FINANCE_COMPATIBILITY_ANALYSIS.md)
- [Investing.com Compatibility Analysis](./INVESTING_COM_COMPATIBILITY_ANALYSIS.md)
- [DesiQuant Implementation](../../backtesting/datasource_desiquant.py)
- [Backtest Engine](../../engine/backtest_engine.py)

