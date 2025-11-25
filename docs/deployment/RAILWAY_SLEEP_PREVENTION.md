# Railway Sleep Prevention Guide

## Problem
Railway's free tier puts services to sleep after **~10 minutes of inactivity** (no outbound network traffic). This causes:
- Tick streamer stops receiving data
- Live runner stops executing trades
- Frontend can't pull data from sleeping backend
- WebSocket connections are lost

## Root Cause
Railway's **Serverless/App Sleeping** feature automatically puts services to sleep when there's no outbound network traffic for 10+ minutes. This is designed to save resources on the free tier.

## Solutions

### ✅ Solution 1: Disable App Sleeping (Recommended)

**Steps:**
1. Go to Railway Dashboard → Your Service → Settings
2. Find **"Enable App Sleeping"** or **"Serverless"** option
3. **Toggle it OFF**
4. Redeploy your service

**Result:** Service stays awake 24/7, no sleep issues.

**Note:** This may use more resources, but ensures continuous operation for trading.

---

### ✅ Solution 2: Keep-Alive Mechanism (Already Implemented)

The code now includes a **keep-alive monitor** that:
- Logs tick streamer activity every 5 minutes
- Monitors live runner status
- Generates activity logs to keep service active

**However**, this only works if:
- ✅ Tick streamer is connected and receiving ticks (generates outbound traffic to SmartAPI)
- ✅ Live runner is running (generates periodic activity)
- ✅ WebSocket connections are active

**What keeps the service awake:**
1. **Tick Streamer**: Continuously receives data from SmartAPI WebSocket → Generates outbound traffic
2. **Live Runner**: Periodic market checks and trade execution → Generates activity
3. **Keep-Alive Monitor**: Logs status every 5 minutes → Minimal activity

---

### ✅ Solution 3: Railway Health Checks (External Service)

Configure an external health check service to ping your Railway service:

**Option A: Use UptimeRobot (Free)**
1. Sign up at https://uptimerobot.com
2. Create a new monitor:
   - Type: HTTP(s)
   - URL: `https://<your-railway-app>.up.railway.app`
   - Interval: 5 minutes
3. UptimeRobot will ping your service every 5 minutes → Keeps it awake

**Option B: Use cron-job.org (Free)**
1. Sign up at https://cron-job.org
2. Create a new cron job:
   - URL: `https://<your-railway-app>.up.railway.app`
   - Schedule: Every 5 minutes
3. The cron job will ping your service → Keeps it awake

---

### ✅ Solution 4: Upgrade to Railway Pro

Railway Pro ($20/month) **does not have app sleeping** - services stay awake 24/7.

**Benefits:**
- No sleep issues
- Better performance
- Higher resource limits
- Priority support

---

## Recommended Approach

For a **trading system**, I recommend:

1. **Disable App Sleeping** in Railway settings (Solution 1) - Simplest and most reliable
2. **Ensure tick streamer is always connected** - This generates continuous outbound traffic
3. **Start the algo when market is open** - Live runner generates additional activity
4. **Monitor keep-alive logs** - Check that tick streamer stays connected

## Verification

After implementing, check logs for:
```
✅ Keep-alive: Tick streamer active (1 subscriptions, last tick: 2.3s ago)
✅ Keep-alive: Live runner active - generating continuous activity
```

If you see:
```
⚠️ Keep-alive: Tick streamer not connected - service may sleep
⚠️ Keep-alive: No active processes detected
```

Then:
1. Check tick streamer connection status
2. Verify SmartAPI credentials
3. Check if broker session is valid
4. Consider disabling App Sleeping in Railway settings

## Configuration

No additional configuration needed - the keep-alive mechanism is automatically enabled on Railway.

## Troubleshooting

### Service still sleeping?

1. **Check Railway Settings:**
   - Go to Service → Settings
   - Verify "Enable App Sleeping" is OFF
   - If ON, toggle OFF and redeploy

2. **Check Tick Streamer:**
   - Verify it's connected: Look for "SmartAPI websocket connected" in logs
   - Check subscription count: Should show "1 subscriptions" (NIFTY)
   - Verify last tick age: Should be < 60 seconds

3. **Check Live Runner:**
   - Start the algo: This generates continuous activity
   - Verify it's running: Check "Algo Running" status in dashboard

4. **External Health Check:**
   - Set up UptimeRobot or cron-job.org to ping every 5 minutes
   - This ensures service stays awake even if backend has issues

## Next Steps

1. **Disable App Sleeping** in Railway dashboard (if not already done)
2. **Monitor logs** to ensure tick streamer stays connected
3. **Start the algo** during market hours to generate activity
4. **Set up external health check** (optional, but recommended)

---

**Status:** Keep-alive mechanism is **implemented** and will monitor activity. However, for guaranteed 24/7 operation, **disable App Sleeping in Railway settings**.

