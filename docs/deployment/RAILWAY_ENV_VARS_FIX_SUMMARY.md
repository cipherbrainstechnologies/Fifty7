# Railway Environment Variables Fix - Summary

## 🔍 Issues Identified

1. **Broker variables using wrong format** - Lowercase (`api_key`) instead of `BROKER_API_KEY`
2. **WebSocket connecting to wrong URL** - Main app instead of WebSocket service
3. **Code updated** - Now supports both formats

---

## ✅ Solution: Add Missing Broker Variables

### Current Railway Variables (Wrong Format):
```bash
api_key="0m0sXIBK"          # ❌ Wrong - no BROKER_ prefix
client_id="BBGV1001"        # ❌ Wrong - no BROKER_ prefix  
token="3FMVJ5H5DBUAHBVGT5O2ZLBHU4"  # ❌ Wrong - no BROKER_ prefix
type="angel"                # ❌ Wrong - no BROKER_ prefix
```

### ✅ Add These (Correct Format):

**In Railway Dashboard → Your Main Service → Variables**, add:

```bash
BROKER_TYPE=angel
BROKER_API_KEY=0m0sXIBK
BROKER_CLIENT_ID=BBGV1001
BROKER_USERNAME=BBGV1001
BROKER_PWD=1935
BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4
BROKER_API_SECRET=8a5bd331-9445-4d0e-a975-24ef7c73162a
```

**Note**: Code now supports BOTH formats (lowercase and BROKER_*), but using `BROKER_*` format is recommended and more reliable.

---

## ✅ Fix WebSocket Connection

### Option 1: Disable WebSocket (Simplest)

Keep `WEBSOCKET_ENABLED=false` (already set ✅)

This will stop the connection errors. You'll use polling instead of real-time updates.

### Option 2: Enable WebSocket (If you want real-time)

```bash
WEBSOCKET_ENABLED=true
WEBSOCKET_PUBLIC_DOMAIN=nifty-option-websocket-production.up.railway.app
```

Make sure your WebSocket service is running and accessible.

---

## 📋 Complete Action Items

### Step 1: Add Broker Variables

Add these 7 variables to Railway:
```bash
BROKER_TYPE=angel
BROKER_API_KEY=0m0sXIBK
BROKER_CLIENT_ID=BBGV1001
BROKER_USERNAME=BBGV1001
BROKER_PWD=1935
BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4
BROKER_API_SECRET=8a5bd331-9445-4d0e-a975-24ef7c73162a
```

### Step 2: Verify WebSocket Setting

Keep:
```bash
WEBSOCKET_ENABLED=false
```

This will disable WebSocket client and stop the connection errors.

---

## ✅ Expected Results

After adding `BROKER_*` variables and redeploying:

1. ✅ **"TOTP token not configured"** → **FIXED**
2. ✅ **"Cannot fetch symbol token"** → **FIXED**
3. ✅ **"No valid session"** → **FIXED**
4. ✅ **WebSocket connection errors** → **FIXED** (if WEBSOCKET_ENABLED=false)
5. ✅ **Market data will load** → **FIXED**
6. ✅ **Broker session will generate** → **FIXED**

---

## 📝 Quick Checklist

- [ ] Add `BROKER_TYPE=angel` to Railway
- [ ] Add `BROKER_API_KEY=0m0sXIBK` to Railway
- [ ] Add `BROKER_CLIENT_ID=BBGV1001` to Railway
- [ ] Add `BROKER_USERNAME=BBGV1001` to Railway
- [ ] Add `BROKER_PWD=1935` to Railway
- [ ] Add `BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4` to Railway
- [ ] Verify `WEBSOCKET_ENABLED=false` is set
- [ ] Wait for Railway to redeploy
- [ ] Check logs for "Loaded broker config from environment variables"

---

**After completing these steps, all errors should be resolved!** ✅

