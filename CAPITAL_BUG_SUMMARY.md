# Capital Requirement Bug - Executive Summary

## The Problem (In Simple Terms)

**You are absolutely correct!** The backtesting system has a critical bug that calculates capital requirements incorrectly.

---

## What's Wrong

### Current (WRONG) Calculation:
```
Capital Required = Quantity × Strike Price
Example: 75 qty × 24,000 strike = ₹1,80,000 💀 WRONG!
```

### Correct Calculation:
```
Capital Required = Quantity × Option Premium
Example: 75 qty × 150 premium = ₹11,250 ✅ CORRECT!
```

---

## Why This Happened

The code is **confusing strike price with option premium**.

- **Strike Price:** The price at which the option can be exercised (e.g., ₹24,000)
- **Option Premium:** The price you pay to BUY the option (e.g., ₹150)

When you BUY options, you pay the **premium**, not the strike price!

---

## The Bug Location

**File:** `engine/backtest_engine.py`  
**Line 384:**

```python
# WRONG CODE:
capital_required = self.lot_qty * strike_for_capital
# This calculates: 75 × 24000 = 1,80,000

# SHOULD BE:
capital_required = self.lot_qty * entry_price
# This would calculate: 75 × 150 = 11,250
```

---

## Impact on Backtesting

1. **Trades Skipped:** Most trades are rejected as "insufficient capital"
2. **Inaccurate Results:** Only 1-2 trades execute instead of 10+
3. **Biased Metrics:** Win rate, P&L, drawdown all calculated on tiny sample

---

## Realistic Numbers

| Option Premium | Lot Size | Correct Capital | Wrong Capital (Current) |
|---------------|----------|-----------------|------------------------|
| ₹50           | 75       | ₹3,750         | ₹18,00,000            |
| ₹100          | 75       | ₹7,500         | ₹18,00,000            |
| ₹150          | 75       | ₹11,250        | ₹18,00,000            |
| ₹200          | 75       | ₹15,000        | ₹18,00,000            |
| ₹300          | 75       | ₹22,500        | ₹18,00,000            |

---

## Fix Required

**Move the capital check** to happen AFTER the option premium (`entry_price`) is calculated, then use the premium instead of the strike price.

---

## Next Steps

1. ✅ **Analysis Complete** (this document)
2. ⏳ **Apply Fix** to `backtest_engine.py`
3. ⏳ **Re-run Backtests** with corrected logic
4. ⏳ **Verify Results** are realistic

---

**Your observation was spot-on!** NIFTY options are indeed "pretty cheap" (₹50-300 premium range), and requiring ₹1.8L for a single lot makes no sense for option BUYING.

See `BACKTEST_CAPITAL_BUG_ANALYSIS.md` for detailed technical analysis.
