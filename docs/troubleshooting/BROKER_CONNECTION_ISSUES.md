# Broker Connection Issues - Troubleshooting Guide

## 🔍 Common Issues

### Issue 1: Market Data API Failures

**Symptoms:**
```
[E] All 3 retries failed for getCandleData
[W] Empty or invalid data in response
[W] Using cached historical data after API failure
```

**Possible Causes:**

1. **Invalid Date/Time Range**
   - Requesting data for future times or when market is closed
   - Market hours: 9:15 AM - 3:30 PM IST (Monday-Friday)
   - Historical data may not be available immediately after market close

2. **Expired or Invalid Credentials**
   - API key expired or invalid
   - Access token expired (tokens expire after 24 hours)
   - Feed token not generated properly

3. **Rate Limiting**
   - Too many API requests in short time
   - Broker API rate limits exceeded

4. **Network/Firewall Issues**
   - Render.com blocking outbound connections
   - Broker API servers unreachable

**Solutions:**

#### Solution 1: Verify Broker Credentials

1. **Check Environment Variables in Render:**
   - Go to Render Dashboard → Your Service → Environment
   - Verify all broker credentials are set correctly:
     ```
     BROKER_TYPE=angel
     BROKER_API_KEY=your_api_key
     BROKER_CLIENT_ID=your_client_id
     BROKER_USERNAME=your_client_id
     BROKER_PWD=your_trading_pin
     BROKER_TOKEN=your_totp_secret
     ```

2. **Test Credentials Locally:**
   ```bash
   # Test locally first
   python -c "from engine.broker_connector import create_broker_interface; broker = create_broker_interface(); print('Connected:', broker is not None)"
   ```

3. **Regenerate API Credentials:**
   - Go to https://smartapi.angelone.in/
   - Verify API key is active
   - Regenerate if expired

#### Solution 2: Check Date/Time Parameters

The error shows requests for:
```
'fromdate': '2025-11-22 17:24', 'todate': '2025-11-22 19:24'
```

**Issues:**
- Market closes at 3:30 PM IST (15:30)
- Requesting data for 5:24 PM - 7:24 PM (after market close)
- No live data available after market hours

**Fix:**
- The system should automatically adjust for market hours
- Check `config/config.yaml` → `market_data.api_delay_minutes` (should be 5)
- Verify timezone is set to IST (Asia/Kolkata)

#### Solution 3: Refresh Session/Token

1. **Manual Token Refresh:**
   - In the dashboard, go to Settings tab
   - Click "Refresh Broker Session"
   - This regenerates the access token

2. **Check Token Expiry:**
   - Access tokens expire after 24 hours
   - System should auto-refresh, but manual refresh helps

#### Solution 4: Check Market Hours

- **Market Hours**: 9:15 AM - 3:30 PM IST (Monday-Friday)
- **No Data Available**: Outside market hours or on weekends
- **Historical Data**: May have delays (5-10 minutes after market close)

---

### Issue 2: WebSocket Connection Failures

**Symptoms:**
```
[W] SmartAPI websocket error: Connection closed
[W] Connection closed due to max retry attempts reached
[I] Connecting SmartAPI websocket (subscriptions=1)
[W] Attempting to resubscribe/reconnect (Attempt 1)...
```

**Possible Causes:**

1. **Feed Token Not Generated**
   - Feed token required for websocket connections
   - Not generated or expired

2. **Network/Firewall Restrictions**
   - Render.com blocking websocket connections
   - Broker websocket servers unreachable

3. **Invalid Subscription**
   - Symbol token invalid
   - Exchange code incorrect

4. **Broker API Issues**
   - Broker websocket service down
   - Rate limiting on websocket connections

**Solutions:**

#### Solution 1: Verify Feed Token

The feed token is automatically generated, but you can verify:

1. **Check Broker Session:**
   - Feed token is generated when broker session is created
   - Ensure broker session is active

2. **Manual Feed Token Refresh:**
   - In dashboard Settings, click "Refresh Broker Session"
   - This regenerates both access token and feed token

#### Solution 2: Check Network Connectivity

1. **Test from Render:**
   - Check Render logs for network errors
   - Verify outbound connections are allowed

2. **Broker API Status:**
   - Check https://smartapi.angelone.in/status (if available)
   - Verify broker API is operational

#### Solution 3: Disable WebSocket (Temporary Workaround)

If websocket keeps failing, you can disable it temporarily:

1. **Edit `config/config.yaml`:**
   ```yaml
   websocket:
     enabled: false  # Disable websocket temporarily
   ```

2. **Redeploy:**
   - Commit and push changes
   - Render will redeploy automatically

**Note:** This disables real-time tick streaming. Market data will still work via REST API polling.

---

## 🔧 Diagnostic Steps

### Step 1: Check Broker Credentials

```bash
# In Render logs, look for:
[I] Broker session generated successfully
[I] Feed token obtained
```

If you see errors about session generation, credentials are invalid.

### Step 2: Check API Response

Look for specific error codes in logs:
- `AB1004`: Invalid date range or no data available
- `AB1005`: Rate limit exceeded
- `AB1006`: Invalid token
- `401/403`: Authentication failed

### Step 3: Verify Timezone

Ensure system timezone is IST:
```python
# Should show Asia/Kolkata
import pytz
print(pytz.timezone('Asia/Kolkata'))
```

### Step 4: Test API Connection

1. **Manual Test:**
   - Use Postman or curl to test SmartAPI endpoints
   - Verify API key and token work

2. **Check Broker Dashboard:**
   - Login to Angel One
   - Verify API app is active
   - Check API usage/limits

---

## 🛠️ Quick Fixes

### Fix 1: Restart Service

Sometimes a simple restart helps:
1. Go to Render Dashboard
2. Click "Manual Deploy" → "Clear build cache & deploy"
3. Wait for redeployment

### Fix 2: Clear Cached State

If cached data is causing issues:
1. In Render, go to your service
2. Open shell/terminal
3. Delete cached state:
   ```bash
   rm -rf data/state/*
   ```

### Fix 3: Increase Retry Delays

If rate limiting is the issue, increase delays in `config/config.yaml`:
```yaml
market_data:
  max_retries: 5  # Increase from 3
  retry_delay_seconds: 10  # Increase from 5
```

---

## 📋 Checklist

Before reporting issues, verify:

- [ ] Broker credentials are correct in Render environment variables
- [ ] API key is active in Angel One SmartAPI dashboard
- [ ] Trading PIN is correct
- [ ] TOTP secret is correct (from authenticator app)
- [ ] Market is open (9:15 AM - 3:30 PM IST, Mon-Fri)
- [ ] Date/time parameters are within market hours
- [ ] Access token is not expired (refresh if needed)
- [ ] Network connectivity from Render to broker API
- [ ] No rate limiting issues
- [ ] Broker API status is operational

---

## 🚨 Emergency Workarounds

### Workaround 1: Use Cached Data Only

If API keeps failing, the system automatically falls back to cached data. This is acceptable for:
- Historical analysis
- Backtesting
- Off-market hours

### Workaround 2: Disable Live Trading

If connections are unstable:
1. Don't enable live trading
2. Use paper trading mode
3. Test with backtesting only

### Workaround 3: Use Alternative Data Source

For backtesting, you can use alternative data sources:
- CSV files
- DesiQuant S3 data
- Market Data API (if configured)

---

## 📞 Getting Help

If issues persist:

1. **Check Logs:**
   - Render Dashboard → Logs tab
   - Look for specific error codes
   - Note timestamps of failures

2. **Test Locally:**
   - Reproduce issue locally
   - Verify credentials work locally

3. **Contact Broker Support:**
   - Angel One SmartAPI support
   - Verify API status and limits

4. **Review Documentation:**
   - `docs/api/API-Documentation-File.md`
   - `docs/strategy/angelone_strategy_resilient.md`

---

## 🔍 Understanding the Logs

### Normal Operation:
```
[I] Broker session generated successfully
[I] Feed token obtained
[I] SmartAPI websocket connected
[I] Successfully fetched candles
```

### Warning (Non-Critical):
```
[W] Empty or invalid data in response
[W] Using cached historical data
```
→ System is working, just using fallback data

### Error (Needs Attention):
```
[E] All 3 retries failed for getCandleData
[E] Cannot call API: No valid session or auth token
```
→ Credentials or connection issue

---

**Last Updated**: 2025-11-22

