# SmartAPI Multiple Apps Configuration Guide

## 📋 Overview

Your system uses **three separate SmartAPI applications** to optimize API quota usage and separate concerns:

1. **Trading App** - For live trading and order execution
2. **Historical App** - For backtesting and historical data (separate quota)
3. **Publisher App** - For real-time websocket tick data

## 🎯 Why Multiple Apps?

- **Separate Quotas**: Historical data requests don't consume trading API quota
- **Rate Limiting**: Each app has its own rate limits
- **Isolation**: Data fetching failures don't affect trading operations
- **Optimization**: Better performance and reliability

---

## 📝 Current Configuration

### Trading App (Live Trading)
```toml
[smartapi_apps.trading]
api_key = "sz5neY7b"
api_secret = "8a5bd331-9445-4d0e-a975-24ef7c73162a"
```
**Used for:**
- Order placement
- Position management
- Portfolio queries
- Account information
- Live trading operations

### Historical App (Backtesting & Historical Data)
```toml
[smartapi_apps.historical]
api_key = "oV0N6xt7"
api_secret = "4ab84310-301a-4114-be83-4b171e322e49"
```
**Used for:**
- Historical OHLC data fetching
- Backtesting data retrieval
- Market data analysis
- Strategy testing

### Publisher App (Real-time Ticks)
```toml
[smartapi_apps.publisher]
api_key = "MIavKEDZ"
api_secret = "899402fe-2641-4ffa-9683-545e60329642"
```
**Used for:**
- WebSocket connections
- Real-time tick streaming
- Live quote updates
- Market feed subscriptions

---

## ⚙️ Configuration for Render.com

### Option 1: Using Environment Variables (Recommended)

In Render Dashboard → Your Service → Environment tab, add:

#### Trading App
```bash
SMARTAPI_TRADING_API_KEY=sz5neY7b
SMARTAPI_TRADING_API_SECRET=8a5bd331-9445-4d0e-a975-24ef7c73162a
```

#### Historical App
```bash
SMARTAPI_HISTORICAL_API_KEY=oV0N6xt7
SMARTAPI_HISTORICAL_API_SECRET=4ab84310-301a-4114-be83-4b171e322e49
```

#### Publisher App
```bash
SMARTAPI_PUBLISHER_API_KEY=MIavKEDZ
SMARTAPI_PUBLISHER_API_SECRET=899402fe-2641-4ffa-9683-545e60329642
```

### Option 2: Using Streamlit Secrets (For Streamlit Cloud)

If deploying to Streamlit Cloud, add to Secrets:

```toml
[smartapi_apps.trading]
api_key = "sz5neY7b"
api_secret = "8a5bd331-9445-4d0e-a975-24ef7c73162a"

[smartapi_apps.historical]
api_key = "oV0N6xt7"
api_secret = "4ab84310-301a-4114-be83-4b171e322e49"

[smartapi_apps.publisher]
api_key = "MIavKEDZ"
api_secret = "899402fe-2641-4ffa-9683-545e60329642"
```

---

## 🔧 How the System Uses These Apps

### 1. Trading App Usage

**Location:** `engine/broker_connector.py`

```python
# Used for:
- place_order()
- get_positions()
- cancel_order()
- get_order_status()
- modify_order()
```

**Configuration:**
- Primary broker credentials in `[broker]` section
- Falls back to `[smartapi_apps.trading]` if needed

### 2. Historical App Usage

**Location:** `engine/market_data.py`, `backtesting/datasource_smartapi.py`

```python
# Used for:
- getCandleData() API calls
- Historical data fetching
- Backtesting data retrieval
- Market data analysis
```

**Configuration:**
- Loaded from `[smartapi_apps.historical]`
- Falls back to trading app if historical app not available
- Uses same client_id, username, pwd, token as trading app

### 3. Publisher App Usage

**Location:** `engine/tick_stream.py`

```python
# Used for:
- WebSocket connections
- Real-time tick streaming
- Feed token generation
- Live quote subscriptions
```

**Configuration:**
- Loaded from `[smartapi_apps.publisher]`
- Generates feed_token for websocket connections
- Separate from trading operations

---

## 📋 Complete Render Environment Variables

Here's the complete list of environment variables you need in Render:

### Broker Credentials (Required)
```bash
BROKER_TYPE=angel
BROKER_API_KEY=sz5neY7b
BROKER_CLIENT_ID=BBGV1001
BROKER_USERNAME=BBGV1001
BROKER_PWD=1935
BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4
```

### SmartAPI Apps (Optional but Recommended)
```bash
# Trading App (usually same as BROKER_API_KEY)
SMARTAPI_TRADING_API_KEY=sz5neY7b
SMARTAPI_TRADING_API_SECRET=8a5bd331-9445-4d0e-a975-24ef7c73162a

# Historical App (for backtesting)
SMARTAPI_HISTORICAL_API_KEY=oV0N6xt7
SMARTAPI_HISTORICAL_API_SECRET=4ab84310-301a-4114-be83-4b171e322e49

# Publisher App (for websocket)
SMARTAPI_PUBLISHER_API_KEY=MIavKEDZ
SMARTAPI_PUBLISHER_API_SECRET=899402fe-2641-4ffa-9683-545e60329642
```

**Note:** The system will work with just broker credentials, but having separate apps provides better quota management.

---

## 🔍 How to Verify Configuration

### Check 1: Verify Apps are Loaded

In your app logs, look for:
```
[I] Historical SmartAPI app configured
[I] Publisher SmartAPI app configured
```

### Check 2: Test Historical Data

1. Go to Backtest tab
2. Select data source: "angel_smartapi"
3. Run a backtest
4. Check logs for historical app usage

### Check 3: Test WebSocket

1. Start live trading
2. Check logs for:
   ```
   [I] Feed token obtained from publisher app
   [I] SmartAPI websocket connected
   ```

---

## 🚨 Important Notes

### 1. Shared Credentials

All three apps use the **same**:
- `client_id` (BBGV1001)
- `username` (BBGV1001)
- `pwd` (trading PIN)
- `token` (TOTP secret)

Only the `api_key` and `api_secret` differ between apps.

### 2. Fallback Behavior

- If historical app not configured → Falls back to trading app
- If publisher app not configured → WebSocket may not work
- Trading app is always required

### 3. API Quota

- **Trading App**: Limited quota (use for trading only)
- **Historical App**: Separate quota (use for data fetching)
- **Publisher App**: Separate quota (use for websocket)

### 4. Security

- **Never commit** `secrets.toml` to Git
- Use environment variables in Render
- Rotate API keys regularly
- Keep TOTP secret secure

---

## 🛠️ Troubleshooting

### Issue: Historical Data Not Working

**Symptoms:**
- Backtesting fails
- Historical data API errors

**Solution:**
1. Verify `SMARTAPI_HISTORICAL_API_KEY` and `SMARTAPI_HISTORICAL_API_SECRET` are set
2. Check historical app is active in Angel One dashboard
3. Verify credentials are correct

### Issue: WebSocket Not Connecting

**Symptoms:**
- WebSocket connection failures
- Feed token errors

**Solution:**
1. Verify `SMARTAPI_PUBLISHER_API_KEY` and `SMARTAPI_PUBLISHER_API_SECRET` are set
2. Check publisher app is active
3. Refresh broker session in Settings tab

### Issue: Trading App Not Working

**Symptoms:**
- Order placement fails
- Authentication errors

**Solution:**
1. Verify `BROKER_API_KEY` matches trading app key
2. Check all broker credentials are correct
3. Refresh broker session

---

## 📚 Related Documentation

- **Broker Connection Issues**: [`docs/troubleshooting/BROKER_CONNECTION_ISSUES.md`](../troubleshooting/BROKER_CONNECTION_ISSUES.md)
- **Render Environment Variables**: [`docs/deployment/RENDER_ENV_VARIABLES.md`](RENDER_ENV_VARIABLES.md)
- **Hosting Guide**: [`docs/deployment/HOSTING_GUIDE.md`](HOSTING_GUIDE.md)

---

## ✅ Configuration Checklist

Before deploying, ensure:

- [ ] Trading app credentials set (`BROKER_API_KEY`, etc.)
- [ ] Historical app credentials set (optional but recommended)
- [ ] Publisher app credentials set (optional but recommended)
- [ ] All apps are active in Angel One dashboard
- [ ] TOTP secret is correct for all apps
- [ ] Trading PIN is correct
- [ ] Client ID is correct
- [ ] Tested locally with `secrets.toml`
- [ ] Environment variables set in Render
- [ ] No credentials committed to Git

---

**Last Updated**: 2025-11-22

