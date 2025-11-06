# Backtest Capital Requirement Bug Analysis

**Date:** 2025-11-06  
**Severity:** CRITICAL  
**Status:** IDENTIFIED - NOT YET FIXED  

---

## Issue Summary

The backtesting engine is calculating capital requirements using **strike price** instead of **option premium**, resulting in inflated capital requirements of **1,80,000+ for a single lot (75 qty)** when the actual requirement should be around **₹5,000-15,000**.

---

## Root Cause

### Location
**File:** `engine/backtest_engine.py`  
**Lines:** 321, 383-390

### Incorrect Code

```python
# Line 321: Calculate strike (correct for strike selection)
strike_for_capital = self._calculate_strike(spot_at_entry, direction)

# Line 383-390: WRONG CALCULATION
# ========== CAPITAL REQUIREMENT CHECK ==========
# Capital required = qty * strike price (margin requirement for options trading)
capital_required = self.lot_qty * strike_for_capital

# Check if current capital is sufficient
if current_capital < capital_required:
    logger.debug(f"Trade skipped due to insufficient capital at {entry_ts}: "
               f"Required: ₹{capital_required:.2f}, Available: ₹{current_capital:.2f}")
    continue
```

---

## Why This Is Wrong

### Options Trading Fundamentals

When **BUYING** options (Call/Put):

1. **You DO NOT pay the strike price** - you pay the **option premium**
2. **Capital Required** = Quantity × Option Premium (NOT Strike Price)
3. **No margin required** for buying options (only premium payment)

### Incorrect Calculation Example

**Current (WRONG) Logic:**
```
Strike Price: ₹24,000 (NIFTY 24000 CE)
Lot Size: 75 qty
Capital Required = 75 × 24,000 = ₹18,00,000
```

**Correct Logic:**
```
Option Premium: ₹150 (NIFTY 24000 CE trading at ₹150)
Lot Size: 75 qty
Capital Required = 75 × 150 = ₹11,250
```

### Impact

This bug causes:

1. **Inflated Capital Requirements:**
   - System thinks ₹1.8 lakh is needed per lot
   - Reality: Only ₹5k-15k needed per lot

2. **Trades Skipped Unnecessarily:**
   - Many valid trades rejected due to "insufficient capital"
   - Drastically reduces backtest trade count
   - Skews backtest results (only first 1-2 trades execute with ₹1L capital)

3. **Incorrect Performance Metrics:**
   - Win rate, P&L, drawdown all calculated on artificially limited trades
   - Cannot assess true strategy performance

---

## Code Flow Analysis

### Where Capital Check Happens

```python
# backtest_engine.py - run_backtest() method

# Step 1: Calculate strike price (line 321)
strike_for_capital = self._calculate_strike(spot_at_entry, direction)

# Step 2: Get option entry premium (line 351-380)
if options_df is not None and expiry_dt is not None:
    strike = strike_for_capital  # Use pre-calculated strike
    opt_slice = self._select_option_slice(
        options_df, expiry_dt, strike, direction, entry_ts
    )
    entry_price = float(opt_slice.iloc[0]['open'])  # THIS IS THE PREMIUM!
    option_path = opt_slice
else:
    # Synthetic premium path
    entry_price = max(1.0, self._synthetic_entry_premium(spot_at_entry))
    option_path = self._build_synthetic_path(...)

# Step 3: WRONG - Check capital using STRIKE instead of PREMIUM (line 382-390)
capital_required = self.lot_qty * strike_for_capital  # BUG HERE!

if current_capital < capital_required:
    logger.debug(f"Trade skipped due to insufficient capital...")
    continue  # Trade skipped!
```

---

## The Fix (Not Yet Applied)

### Correct Calculation

```python
# ========== CAPITAL REQUIREMENT CHECK ==========
# Capital required = qty * option premium (NOT strike price!)
capital_required = self.lot_qty * entry_price  # Use entry_price (premium), NOT strike!

# Check if current capital is sufficient
if current_capital < capital_required:
    logger.debug(f"Trade skipped due to insufficient capital at {entry_ts}: "
               f"Required: ₹{capital_required:.2f}, Available: ₹{current_capital:.2f}")
    continue
```

### Issue: Timing Problem

**The capital check happens BEFORE entry_price is calculated!**

Current order in code:
1. Line 321: Calculate `strike_for_capital`
2. Line 384: Check capital using `strike_for_capital` ❌ (WRONG)
3. Line 351-380: Calculate `entry_price` (option premium) ✅ (TOO LATE!)

**Solution:**
- Move capital check to AFTER `entry_price` is determined
- Use `entry_price` (premium) instead of `strike_for_capital`

---

## Required Changes

### Option 1: Move Capital Check After Entry Price Calculation

```python
# Step 1: Calculate strike
strike_for_capital = self._calculate_strike(spot_at_entry, direction)

# Step 2: Get entry price FIRST
if options_df is not None and expiry_dt is not None:
    strike = strike_for_capital
    opt_slice = self._select_option_slice(
        options_df, expiry_dt, strike, direction, entry_ts
    )
    if opt_slice.empty:
        continue
    entry_price = float(opt_slice.iloc[0]['open'])  # Premium
    option_path = opt_slice
else:
    entry_price = max(1.0, self._synthetic_entry_premium(spot_at_entry))
    option_path = self._build_synthetic_path(...)

# Step 3: NOW check capital using PREMIUM
capital_required = self.lot_qty * entry_price  # CORRECT!

if current_capital < capital_required:
    logger.debug(f"Trade skipped due to insufficient capital at {entry_ts}: "
               f"Required: ₹{capital_required:.2f}, Available: ₹{current_capital:.2f}")
    continue
```

### Option 2: Estimate Premium Before Full Calculation

```python
# Quick premium estimate for capital check
if options_df is not None:
    # Estimate from available option data
    estimated_premium = estimate_option_premium(options_df, strike_for_capital, direction, entry_ts)
else:
    estimated_premium = self._synthetic_entry_premium(spot_at_entry)

# Check capital with estimated premium
capital_required = self.lot_qty * estimated_premium

if current_capital < capital_required:
    continue

# Then proceed with full entry price calculation...
```

---

## Testing Requirements

After fix is applied, verify:

1. **Capital Requirements are Reasonable:**
   - Single lot (75 qty) should require ₹5k-20k (not ₹1.8L)
   - Proportional to option premium, not strike price

2. **More Trades Execute:**
   - With ₹1L capital, should execute 5-10+ trades (not just 1-2)
   - Trades not skipped due to false capital constraints

3. **Backtest Results Change Significantly:**
   - Trade count increases
   - Win rate recalculated over full sample
   - P&L curve reflects all valid trades

4. **Capital Depletion Works Correctly:**
   - Capital reduces by (qty × premium) per trade
   - Realistic capital requirements throughout backtest

---

## Impact Assessment

### Before Fix (Current Behavior)
- ❌ Capital Required: ₹1.8L per lot (WRONG)
- ❌ Trades Executed: 1-2 only (out of 10+ signals)
- ❌ Results: Unreliable, biased sample

### After Fix (Expected Behavior)
- ✅ Capital Required: ₹5-15k per lot (CORRECT)
- ✅ Trades Executed: 8-10+ (full sample)
- ✅ Results: Accurate, representative backtest

---

## Related Issues

1. **Margin Requirement Comment is Misleading:**
   - Line 383 comment says "margin requirement for options trading"
   - Buying options requires NO margin, only premium payment
   - Margin is required only for SELLING options

2. **Strike Selection vs Capital:**
   - `strike_for_capital` variable name implies it's used for capital
   - Should be renamed to just `strike` or `calculated_strike`
   - Capital should always use premium, never strike

---

## Recommendation

**Priority:** CRITICAL - Fix immediately before any production backtest usage

**Action Items:**
1. ✅ Analyze and document the bug (THIS DOCUMENT)
2. ⏳ Move capital check after `entry_price` calculation
3. ⏳ Replace `strike_for_capital` with `entry_price` in capital calculation
4. ⏳ Update comments to reflect correct logic
5. ⏳ Add validation/logging for capital requirements
6. ⏳ Re-run all backtests to get accurate results
7. ⏳ Update strategy performance reports with corrected data

---

## Example Scenario (User's Report)

**User's Concern:**
> "For a single lot = 75 qty of NIFTY, there cannot be a requirement of 1,80,000 capital as NIFTY strike prices are pretty cheap"

**Analysis:**
- ✅ User is CORRECT
- ✅ NIFTY options premiums are typically ₹50-300
- ✅ Capital for 75 qty should be: ₹3,750 - ₹22,500
- ✅ Current calculation: 75 × 24,000 = ₹18,00,000 is WRONG
- ✅ System is using strike price (24,000) instead of premium (₹100-200)

**Conclusion:**
This is a fundamental misunderstanding of options trading mechanics in the backtest engine code.

---

## Next Steps

1. **Review this analysis** - Confirm understanding
2. **Apply the fix** - Modify `backtest_engine.py` as outlined
3. **Test thoroughly** - Verify capital calculations
4. **Re-run backtests** - Get accurate performance data
5. **Update documentation** - Reflect correct behavior

---

**Document Owner:** Cursor AI Agent  
**Last Updated:** 2025-11-06  
