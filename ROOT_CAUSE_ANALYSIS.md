# Root Cause Analysis: Why Strategy Still References November 4th Candle

## Summary

The strategy is still referencing November 4th candle instead of today's (November 6th) candle because:

1. **API Failures**: AngelOne API is failing to fetch new historical data
2. **Cached Data Fallback**: When API fails, the system falls back to cached data from November 4th
3. **No Data Refresh**: The cached data buffers are not being cleared or updated with today's data

---

## Evidence from Logs

### 1. API Failures

The logs show repeated API failures:
```
[E 251106 13:50:40] Error occurred while making a POST request to getCandleData
Error: Something Went Wrong, Please Try After Sometime
Response: {'message': 'Something Went Wrong, Please Try After Sometime', 'errorcode': 'AB1004', 'status': False, 'data': None}
```

**Request Examples**:
- `'fromdate': '2025-11-05 23:50', 'todate': '2025-11-06 13:45'` ❌ FAILED
- `'fromdate': '2025-11-06 07:50', 'todate': '2025-11-06 13:45'` ❌ FAILED
- `'fromdate': '2025-11-03 13:50', 'todate': '2025-11-06 13:45'` ❌ FAILED

### 2. All Retries Failed

```
[E 251106 13:50:52 market_data:222] All 3 retries failed for getCandleData
[E 251106 13:50:52 market_data:447] Failed to fetch historical candles after all retries
```

### 3. Cached Data Being Used

When API fails, the system falls back to cached data buffers (`_data_1h`, `_data_15m`) which contain old data from November 4th.

---

## Root Cause Chain

```
1. Strategy requests hourly candles
   ↓
2. Market data provider tries to fetch from API
   ↓
3. API fails (AB1004 error)
   ↓
4. System falls back to cached data buffers
   ↓
5. Cached buffers contain old data from November 4th
   ↓
6. Strategy detects inside bars from November 4th data
   ↓
7. Result: Strategy references November 4th candle instead of today's
```

---

## Why This Happens

### 1. **API Rate Limiting / Errors**
- AngelOne API is returning `AB1004` errors
- This could be due to:
  - Rate limiting (too many requests)
  - API maintenance
  - Network issues
  - Invalid session/token

### 2. **Cached Data Not Cleared**
- When API fails, the system uses cached data
- The cached data is from November 4th (last successful fetch)
- The cache is not being cleared or invalidated when it's too old

### 3. **No Fallback to Current OHLC**
- When historical data fails, the system should:
  - Use current OHLC snapshot to update latest candle
  - Clear old cached data if it's too old (>1 day)
  - Log a warning about using stale data

---

## Solutions

### Immediate Fix

1. **Clear Old Cached Data**:
   - Check if cached data is older than 1 day
   - Clear cache if too old
   - Force fresh data fetch

2. **Better Error Handling**:
   - When API fails, try to fetch current OHLC
   - Update latest candle with current snapshot
   - Log warning about using stale data

3. **Data Validation**:
   - Check if latest candle date is today
   - If not, clear cache and force refresh
   - Warn user about stale data

### Long-term Fix

1. **Cache Invalidation**:
   - Implement cache expiry (e.g., 1 hour for live data)
   - Clear cache when data is too old
   - Force refresh on new trading day

2. **Better Fallback Strategy**:
   - When historical API fails, use current OHLC
   - Build latest candle from current snapshot
   - Merge with existing cache (if recent)

3. **API Retry Logic**:
   - Implement exponential backoff
   - Try different date ranges
   - Use alternative data sources if available

---

## Code Locations to Fix

1. **`engine/market_data.py`**:
   - `get_1h_data()` - Check cache age before using
   - `refresh_data()` - Clear old cache
   - `get_historical_candles()` - Better error handling

2. **`engine/inside_bar_breakout_strategy.py`**:
   - `get_hourly_candles()` - Validate latest candle date
   - Add warning if data is stale

3. **`engine/live_runner.py`**:
   - Check data freshness before processing
   - Force refresh if data is too old

---

## Expected Behavior

1. **On API Success**:
   - Fetch fresh data from API
   - Update cache with new data
   - Latest candle should be today's 10:15 (or current hour)

2. **On API Failure**:
   - Try to fetch current OHLC
   - Update latest candle with current snapshot
   - If cache is >1 day old, clear it
   - Log warning about stale data

3. **On Stale Data**:
   - Detect if latest candle is not today
   - Clear old cache
   - Force fresh data fetch
   - Warn user

---

## Next Steps

1. ✅ **Add Cache Validation**: Check if cached data is too old
2. ✅ **Clear Old Cache**: Remove data older than 1 day
3. ✅ **Better Fallback**: Use current OHLC when historical API fails
4. ✅ **Add Warnings**: Log when using stale data
5. ✅ **Force Refresh**: Clear cache on new trading day

