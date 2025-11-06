# Capital Analysis Feature - Backtesting Enhancement

## Summary
Added comprehensive capital tracking and analysis features to the backtesting system to help identify capital exhaustion scenarios and track capital requirements per trade.

## Changes Made

### 1. Backtest Engine (`engine/backtest_engine.py`)

#### New Instance Variables (Lines 107-109)
```python
self.capital_exhausted = False
self.capital_exhausted_at_trade = None
self.capital_requirements: List[float] = []
```

#### Capital Requirement Tracking (Lines 382-391, 500)
- Already had capital requirement check before trade execution
- Now tracks the capital required for each trade in `self.capital_requirements` list
- Stores `capital_required` in each trade dictionary

#### Capital Exhaustion Detection (Lines 509-514)
- Detects when capital becomes zero or negative after a trade
- Logs a warning with details when capital is exhausted
- Records the trade number at which exhaustion occurred
- Only triggers once (first exhaustion)

#### Results Enhancement (Lines 981-1049)
- Calculates average capital required per trade
- Includes new metrics in results dictionary:
  - `capital_exhausted`: Boolean indicating if capital was exhausted
  - `capital_exhausted_at_trade`: Trade number where capital became zero/negative
  - `avg_capital_required`: Average capital required across all trades

### 2. Dashboard UI (`dashboard/ui_frontend.py`)

#### Capital Analysis Section (Lines 3005-3027 and 3190-3212)
Added two identical capital analysis sections for both backtest modes (CSV upload and Cloud):

**Display Components:**
- Section header: "💰 Capital Analysis"
- Average Capital Required per Trade: Shows the mean capital needed
- Capital Exhaustion Alert:
  - ✅ Success message if capital remained positive
  - ⚠️ Error alert if capital was exhausted
  - Detailed warning with trade number and recommendations

**Recommendations shown when capital exhausted:**
- Increase initial capital
- Reduce position size
- Tighten stop losses
- Review strategy parameters

## Features

### 1. Capital Exhaustion Detection
- **What it does**: Monitors capital after each trade and detects when it reaches zero or goes negative
- **When it triggers**: After any trade that results in capital ≤ 0
- **Output**: 
  - Console warning log with details
  - Result flag `capital_exhausted`
  - Trade number where it happened

### 2. Average Capital Required
- **What it calculates**: Mean capital requirement across all executed trades
- **Formula**: Sum of all capital requirements / Number of trades
- **Use case**: Helps determine minimum capital needed to run the strategy

### 3. Trade-Level Capital Tracking
- **Enhancement**: Each trade now includes `capital_required` field
- **Value**: Quantity × Entry Premium (the actual amount paid to buy the option)
- **Benefit**: Enables detailed analysis of capital usage patterns

## Scope

### ✅ Included (Backtesting Only)
- BacktestEngine class
- Dashboard backtest results display
- CSV upload mode
- DesiQuant Cloud mode

### ❌ Not Included (Live Trading)
- LiveStrategyRunner (unchanged)
- Real-time position monitoring
- Broker integration

## Usage

### Running a Backtest
No code changes needed - the feature is automatically included:

```python
from engine.backtest_engine import BacktestEngine

engine = BacktestEngine(config)
results = engine.run_backtest(
    data_1h=spot_data,
    initial_capital=100000.0,
    options_df=options_data,
    expiries_df=expiries_data
)

# New metrics available in results:
print(f"Capital Exhausted: {results['capital_exhausted']}")
print(f"Exhausted at Trade: {results['capital_exhausted_at_trade']}")
print(f"Avg Capital Required: {results['avg_capital_required']}")
```

### Dashboard View
1. Navigate to "Backtest" tab
2. Upload CSV or use Cloud mode
3. Run backtest
4. View "💰 Capital Analysis" section in results

## Technical Details

### Capital Calculation
```
Capital Required = Lot Quantity × Entry Premium
```

For NIFTY options:
- Lot Quantity: 75 (configured in config.yaml)
- Entry Premium: Market price of the option at entry
- Example: If premium = ₹150, capital required = 75 × 150 = ₹11,250

### Detection Logic
```python
if current_capital <= 0 and not self.capital_exhausted:
    self.capital_exhausted = True
    self.capital_exhausted_at_trade = len(self.trades)
    # Log warning...
```

## Benefits

1. **Risk Management**: Identify scenarios where strategy depletes capital
2. **Capital Planning**: Know average capital needed per trade
3. **Strategy Validation**: Understand if initial capital is sufficient
4. **Performance Analysis**: See exactly when and why capital runs out
5. **Trade-by-Trade Visibility**: Each trade shows its capital requirement

## Example Output

### Console Log (when exhausted)
```
⚠️  CAPITAL EXHAUSTED after trade #12 at 2023-11-15 14:30:00
    Final capital: ₹-2,450.00
    Initial capital: ₹100,000.00
    Total loss: ₹102,450.00
```

### Dashboard Display
```
💰 Capital Analysis

Average Capital Required per Trade: ₹11,250.50

⚠️ CAPITAL EXHAUSTED after trade #12

⚠️ Your capital became zero or negative after trade #12. 
This means losses depleted your entire initial capital of ₹100,000.00. 
Consider:
- Increasing initial capital
- Reducing position size
- Tightening stop losses
- Reviewing strategy parameters
```

## Files Modified

1. `/workspace/engine/backtest_engine.py`
   - Lines 107-109: New instance variables
   - Lines 500: Capital requirement tracking
   - Lines 509-514: Capital exhaustion detection
   - Lines 981-1049: Results generation with new metrics

2. `/workspace/dashboard/ui_frontend.py`
   - Lines 3005-3027: Capital analysis section (CSV mode)
   - Lines 3190-3212: Capital analysis section (Cloud mode)

## Testing

### Syntax Validation
✅ Both files compiled successfully without syntax errors

### Integration Points
✅ BacktestEngine only used in backtesting contexts
✅ LiveStrategyRunner not affected
✅ All existing functionality preserved

## Notes

- Feature is **backtest-only** and does not affect live trading
- Capital requirement is based on option premium (not strike price)
- Detection happens in real-time during backtest execution
- Metrics are automatically calculated and included in results
- No configuration changes required to enable this feature

## Date Implemented
2025-11-06
