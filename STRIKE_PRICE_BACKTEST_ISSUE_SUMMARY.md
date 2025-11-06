# Strike Price Calculation Issue - Backtesting Failure Analysis

## Problem Summary
Backtesting is producing **0 trade results** because the calculated strike prices with ITM/OTM offsets do not match the actual strikes available in the historical options data.

---

## Root Cause Analysis

### 1. Strike Calculation Process (backtest_engine.py)

**Line 321**: Calculate strike for capital requirement
```python
strike_for_capital = self._calculate_strike(spot_at_entry, direction)
```

**Lines 539-587**: `_calculate_strike()` method applies offsets:
```python
def _calculate_strike(self, spot_price: float, direction: str) -> int:
    # Base strike (ATM)
    base_strike = round(spot_price / 50) * 50
    
    # Apply offset based on ITM/OTM configuration
    if direction == "CE":
        if self.strike_is_itm:
            offset = -self.strike_offset_base  # Lower strike for ITM Call
        elif self.strike_is_otm:
            offset = self.strike_offset_base   # Higher strike for OTM Call
    elif direction == "PE":
        if self.strike_is_itm:
            offset = self.strike_offset_base   # Higher strike for ITM Put
        elif self.strike_is_otm:
            offset = -self.strike_offset_base  # Lower strike for OTM Put
    
    strike = base_strike + offset
    return int(strike)
```

**Example**: 
- Spot = 23,150
- Base ATM = 23,150 (rounded to 50)
- ITM offset = 100
- For CE: ITM strike = 23,150 - 100 = **23,050**

### 2. Option Data Selection (backtest_engine.py)

**Lines 358-365**: Try to find option data with exact strike match:
```python
opt_slice = self._select_option_slice(
    options_df, expiry_dt, strike, direction, entry_ts
)
if opt_slice.empty:
    # No option data found → SKIP TRADE
    logger.debug(f"No option data found for trade at {entry_ts} ...")
    continue  # ← THIS IS WHY 0 TRADES!
```

**Lines 601-616**: `_select_option_slice()` requires EXACT match:
```python
def _select_option_slice(self, options_df, expiry_dt, atm, direction, entry_ts):
    side = 'CE' if direction == 'CE' else 'PE'
    mask = (
        (options_df['expiry'].dt.date == expiry_dt.date()) &
        (options_df['strike'] == atm) &              # ← EXACT MATCH REQUIRED
        (options_df['type'] == side) &
        (options_df['timestamp'] >= entry_ts)
    )
    return options_df.loc[mask].copy()
```

### 3. Historical Options Data (datasource_desiquant.py)

**Lines 397-464**: Options data loading uses **ATM strikes only**:
```python
def _build_options_frame(symbol, expiries, spot_1h, start, end):
    for e in exps["expiry"]:
        ref_close = float(spot_1h.loc[mask, "Close"].iloc[-1])
        
        # Find nearest listed ATM strike from catalog
        atm = _nearest_listed_strike(ref_close, e, strikes_df)  # ← ATM only!
        
        # Load CE/PE for this ATM strike
        for side in ("CE","PE"):
            # Try ATM ± small offsets (50, 100, 150, ...)
```

**Lines 142-150**: Nearest listed strike logic:
```python
def _nearest_listed_strike(spot: float, expiry: pd.Timestamp, strikes_df: pd.DataFrame):
    day_strikes = strikes_df.loc[strikes_df["expiry"].dt.date == expiry.date(), "strike"]
    target = float(spot)
    s = day_strikes.iloc[(day_strikes - target).abs().argmin()]
    return int(s)  # Returns nearest ATM
```

---

## The Mismatch Problem

### Configuration Values (from dashboard/ui_frontend.py)

When user selects strike in dashboard:
```python
# Lines 2305-2743
strike_selection = st.selectbox("Strike Selection", 
    ["ATM 0", "ITM 50", "ITM 100", "OTM 50", "OTM 100", ...])

strike_offset_base = strike_offset_map.get(strike_selection, 0)
is_itm = strike_selection.startswith("ITM")
is_otm = strike_selection.startswith("OTM")
```

**Example**: User selects **"ITM 100"**
- `strike_offset_base = 100`
- `strike_is_itm = True`
- `strike_is_otm = False`

### What Happens During Backtest

1. **Signal detected**: Spot = 23,150, Direction = CE
2. **Strike calculated**: 23,150 - 100 = **23,050** (ITM Call)
3. **Options data search**: Look for strike **23,050** in options_df
4. **Options data available**: Only has ATM strike **23,150** (or 23,100, 23,200)
5. **Result**: `opt_slice.empty = True` → Trade skipped
6. **Final outcome**: 0 trades executed

---

## Why This Happens

### Data Loading Strategy
The `datasource_desiquant.py` loads **only ATM options** from S3:
- For each expiry, it calculates ATM based on spot price
- Loads CE and PE for that ATM strike (with small ±50/100 fallback)
- Does NOT load full strike chain with ITM/OTM strikes

### Backtest Engine Assumption
The `backtest_engine.py` assumes:
- All calculated strikes exist in options data
- No validation or fallback to nearest available strike
- Hard failure (skip trade) if exact match not found

### Configuration Disconnect
- User configures **ITM 100** or **OTM 50** in dashboard
- Data source only provides **ATM strikes**
- No reconciliation between user config and available data

---

## Impact

### Zero Trades Scenario
```
📊 Backtest Run:
   - Inside bars detected: 15
   - Breakouts detected: 8
   - Strikes calculated: 8
   - Option data found: 0  ← PROBLEM!
   - Trades executed: 0
   - Result: Empty backtest with 0 P&L
```

### Log Evidence
```python
logger.debug(f"No option data found for trade at {entry_ts} 
    (expiry: {expiry_dt}, strike: {strike}, direction: {direction})")
```

This message appears for every potential trade when strikes don't match.

---

## Solution Approaches

### Option 1: Load Full Strike Chain (Data-Heavy)
Modify `datasource_desiquant.py` to load multiple strikes:
```python
# Instead of just ATM
strikes_to_load = [atm - 200, atm - 100, atm, atm + 100, atm + 200]
for strike in strikes_to_load:
    for side in ("CE", "PE"):
        # Load data
```

**Pros**: Supports any ITM/OTM configuration
**Cons**: 5x more data to load, slower, more S3 bandwidth

### Option 2: Fallback to Nearest Available Strike (Recommended)
Modify `_select_option_slice()` to find nearest strike:
```python
def _select_option_slice(self, options_df, expiry_dt, target_strike, direction, entry_ts):
    side = 'CE' if direction == 'CE' else 'PE'
    
    # Get all available strikes for this expiry/type
    candidates = options_df[
        (options_df['expiry'].dt.date == expiry_dt.date()) &
        (options_df['type'] == side) &
        (options_df['timestamp'] >= entry_ts)
    ]['strike'].unique()
    
    if len(candidates) == 0:
        return pd.DataFrame()  # No data at all
    
    # Find nearest strike to target
    nearest_strike = candidates[np.abs(candidates - target_strike).argmin()]
    
    # Select data for nearest strike
    mask = (
        (options_df['expiry'].dt.date == expiry_dt.date()) &
        (options_df['strike'] == nearest_strike) &
        (options_df['type'] == side) &
        (options_df['timestamp'] >= entry_ts)
    )
    
    result = options_df.loc[mask].copy()
    
    # Log if we used fallback
    if nearest_strike != target_strike:
        logger.info(f"Using nearest available strike {nearest_strike} "
                   f"(requested: {target_strike}, diff: {abs(nearest_strike - target_strike)})")
    
    return result
```

**Pros**: Works with existing data, graceful fallback, fast
**Cons**: May not match exact ITM/OTM offset user requested

### Option 3: Restrict Configuration to ATM Only
Force dashboard to only allow ATM selection for backtests:
```python
if backtesting_mode:
    strike_selection = "ATM 0"  # Force ATM for backtests
```

**Pros**: Guaranteed to work, no code changes to backtest engine
**Cons**: Limits backtesting flexibility, can't test ITM/OTM strategies

### Option 4: Validate Config Before Backtest
Add pre-flight check:
```python
def validate_backtest_config(config, options_df):
    available_strikes = options_df['strike'].unique()
    
    # Check if any calculated strikes would match available data
    test_spot = options_df[...].iloc[0]['close']  # sample spot
    test_strike = calculate_strike(test_spot, 'CE')
    
    if test_strike not in available_strikes:
        nearest = available_strikes[np.abs(available_strikes - test_strike).argmin()]
        logger.warning(f"Config strike {test_strike} not available. "
                      f"Nearest: {nearest}. Consider using ATM or loading more strikes.")
        return False
    return True
```

**Pros**: Early warning, prevents wasted backtest runs
**Cons**: Doesn't fix the problem, just alerts user

---

## Recommended Fix

**Implement Option 2** (Fallback to Nearest Strike) because:
1. ✅ Works with existing data infrastructure
2. ✅ Graceful degradation (uses best available)
3. ✅ Logs when fallback is used (transparency)
4. ✅ Fast and efficient
5. ✅ Maintains backtest validity (similar strikes perform similarly)

**Plus Option 4** (Validation) to warn users when significant fallback occurs.

---

## Testing the Fix

### Test Case 1: ATM Configuration
- Config: `strike_offset_base = 0`, `strike_is_itm = False`, `strike_is_otm = False`
- Expected: Exact match, no fallback
- Result: Should work as before

### Test Case 2: ITM 100 Configuration
- Config: `strike_offset_base = 100`, `strike_is_itm = True`
- Spot: 23,150 → Requested strike: 23,050
- Available: 23,150 (ATM only)
- Expected: Use 23,150 with warning log
- Result: Trades executed, results returned

### Test Case 3: OTM 200 Configuration
- Config: `strike_offset_base = 200`, `strike_is_otm = True`
- Spot: 23,150 → Requested strike: 23,350
- Available: 23,150 (ATM only)
- Expected: Use 23,150 with warning log
- Result: Trades executed

---

## Configuration Notes

### Current Config (config/config.yaml)
```yaml
strategy:
  atm_offset: 0  # Only used by live strategy, NOT backtest
```

### Backtest Config (from dashboard)
Passed via `run_backtest()` parameters:
```python
config = {
    'strike_selection': 'ITM 100',
    'strike_offset_base': 100,
    'strike_is_itm': True,
    'strike_is_otm': False
}
```

These values are set in `dashboard/ui_frontend.py` (lines 2730-2743) based on user's dropdown selection.

---

## Immediate Action Required

1. **Modify `_select_option_slice()` in backtest_engine.py** to implement nearest-strike fallback
2. **Add validation logging** to show when fallback is used
3. **Test with ITM/OTM configurations** to verify trades are now executed
4. **Update dashboard** to warn users that ITM/OTM may use nearest available strike

---

## Additional Observations

### Why Logs Show "No option data found"
```python
# backtest_engine.py line 362-364
if opt_slice.empty:
    logger.debug(f"No option data found for trade at {entry_ts} ...")
    continue
```

This debug message appears for EVERY potential trade when strikes don't match, leading to 0 results.

### Capital Calculation is Correct
```python
# Lines 375-383
capital_required = self.lot_qty * strike_for_capital
if current_capital < capital_required:
    continue
```

Capital check happens AFTER option data check, so it's not the issue.

### Signal Detection Works Fine
```python
# Lines 186-193
inside_idxs = detect_inside_bar(data, tighten_signal=False)
if inside_idxs:
    logger.info(f"Found {len(inside_idxs)} inside bar pattern(s)")
```

Inside bars and breakouts are detected correctly. The failure is purely in option data matching.

---

## Conclusion

**Root Cause**: Exact strike matching fails when calculated ITM/OTM strikes don't exist in ATM-only historical data.

**Fix**: Implement nearest-strike fallback in `_select_option_slice()` method.

**Impact**: Will restore backtesting functionality and produce results even with ITM/OTM configurations.

**Priority**: HIGH - Currently blocking all backtesting with non-ATM configurations.
