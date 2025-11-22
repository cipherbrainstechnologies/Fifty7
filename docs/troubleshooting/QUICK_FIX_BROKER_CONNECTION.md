# Quick Fix: Broker Connection Issues on Render

## 🚨 Immediate Issues from Your Logs

### Issue 1: Market Data API - Requesting Data After Market Close

**Problem:**
```
'fromdate': '2025-11-22 17:24', 'todate': '2025-11-22 19:24'
```

Market closes at **3:30 PM IST**, but system is requesting data for **5:24 PM - 7:24 PM**.

**Quick Fix:**
This is actually **normal behavior** - the system is trying to get the latest data. When market is closed, it will:
1. Try to fetch (fails because market is closed)
2. Fall back to cached data (which it's doing)
3. Use yesterday's data (2025-11-21 15:15:00)

**This is working as designed** - no action needed unless you need live data during market hours.

---

### Issue 2: WebSocket Connection Failures

**Problem:**
```
[W] SmartAPI websocket error: Connection closed
[W] Connection closed due to max retry attempts reached
```

**Quick Fixes (Try in Order):**

#### Fix 1: Refresh Broker Session (Easiest)

1. Go to your Render app: https://nifty-option-trading.onrender.com
2. Navigate to **Settings** tab
3. Click **"Refresh Broker Session"** button
4. Wait 30 seconds for reconnection

#### Fix 2: Verify Environment Variables

1. Go to Render Dashboard → Your Service → **Environment** tab
2. Verify these are set correctly:
   ```
   BROKER_TYPE=angel
   BROKER_API_KEY=<your_key>
   BROKER_CLIENT_ID=<your_id>
   BROKER_USERNAME=<your_id>
   BROKER_PWD=<your_pin>
   BROKER_TOKEN=<your_totp_secret>
   ```
3. **Important:** Make sure there are no extra spaces or quotes
4. Click **"Save Changes"** if you made any edits

#### Fix 3: Restart Service

1. Go to Render Dashboard → Your Service
2. Click **"Manual Deploy"** → **"Clear build cache & deploy"**
3. Wait for redeployment (2-5 minutes)

#### Fix 4: Disable WebSocket Temporarily

If websocket keeps failing and you don't need real-time ticks:

1. Edit `config/config.yaml`:
   ```yaml
   websocket:
     enabled: false  # Change from true to false
   ```

2. Commit and push:
   ```bash
   git add config/config.yaml
   git commit -m "Temporarily disable websocket"
   git push origin main
   ```

3. Render will auto-redeploy

**Note:** This disables real-time tick streaming but market data via REST API will still work.

---

## ✅ Verification Steps

### Step 1: Check if Broker Session is Active

In your app logs, look for:
```
[I] Broker session generated successfully
[I] Feed token obtained
```

If you see errors instead, credentials are wrong.

### Step 2: Test During Market Hours

- **Market Hours:** 9:15 AM - 3:30 PM IST (Monday-Friday)
- Test the connection during market hours
- Outside market hours, API calls will fail (this is normal)

### Step 3: Check API Key Status

1. Go to https://smartapi.angelone.in/
2. Login to your account
3. Check your API app status
4. Verify API key is **Active**
5. Check if there are any rate limits or restrictions

---

## 🔍 Common Causes

### Cause 1: Expired Access Token
- **Solution:** Click "Refresh Broker Session" in Settings

### Cause 2: Invalid Feed Token
- **Solution:** Refresh broker session (regenerates feed token)

### Cause 3: Network/Firewall
- **Solution:** Usually resolves after restart. If persistent, contact Render support.

### Cause 4: Broker API Down
- **Solution:** Check https://smartapi.angelone.in/ for status updates

### Cause 5: Rate Limiting
- **Solution:** Wait 5-10 minutes, then refresh session

---

## 🎯 What's Actually Broken?

Based on your logs:

1. ✅ **Market Data API** - Working (falling back to cache when market closed)
2. ❌ **WebSocket** - Failing to connect (needs feed token refresh)

**Priority:** Fix websocket connection by refreshing broker session.

---

## 📋 Action Plan

**Right Now:**
1. Go to your app → Settings → Click "Refresh Broker Session"
2. Wait 1 minute
3. Check if websocket connects

**If Still Failing:**
1. Verify all environment variables in Render
2. Restart service in Render dashboard
3. Test during market hours (9:15 AM - 3:30 PM IST)

**If Still Failing:**
1. Temporarily disable websocket (see Fix 4 above)
2. App will work without real-time ticks
3. Market data via REST API will still work

---

## 💡 Understanding the Behavior

**Normal Behavior:**
- ✅ API calls fail after market close → Uses cached data
- ✅ WebSocket disconnects → Automatically reconnects
- ✅ Falls back to cached data when API unavailable

**Problem Behavior:**
- ❌ WebSocket never connects (feed token issue)
- ❌ API always fails (credentials issue)
- ❌ No cached data available (first run issue)

Your logs show **normal behavior** for after-market hours, but **websocket connection issues** that need fixing.

---

**Last Updated**: 2025-11-22

