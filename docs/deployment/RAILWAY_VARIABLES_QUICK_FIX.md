# Railway Variables Quick Fix Guide

## 🔍 Current Issues

1. ❌ **"TOTP token not configured"** - Broker variables are lowercase format, need `BROKER_*` prefix
2. ❌ **WebSocket connection errors** - Connecting to wrong URL (main app instead of WebSocket service)
3. ✅ **Firebase working** - Already configured correctly

---

## ✅ Quick Fix: Update Railway Environment Variables

### Step 1: Add Broker Variables with `BROKER_` Prefix

**In Railway Dashboard → Your Main Service → Variables**, add these:

```bash
BROKER_TYPE=angel
BROKER_API_KEY=0m0sXIBK
BROKER_CLIENT_ID=BBGV1001
BROKER_USERNAME=BBGV1001
BROKER_PWD=1935
BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4
BROKER_API_SECRET=8a5bd331-9445-4d0e-a975-24ef7c73162a
```

**Note**: Code supports both formats (`api_key` and `BROKER_API_KEY`), but `BROKER_*` format is preferred and more reliable.

### Step 2: Fix WebSocket Configuration

**Option A: Disable WebSocket (Recommended for now)**
```bash
WEBSOCKET_ENABLED=false  # Already set ✅
```

**Option B: Enable WebSocket (If you want real-time)**
```bash
WEBSOCKET_ENABLED=true
WEBSOCKET_PUBLIC_DOMAIN=nifty-option-websocket-production.up.railway.app
```

And make sure your WebSocket service is running.

---

## 📋 Complete Variable List

### ✅ Firebase (Already Correct)
Keep these as-is:
```
FIREBASE_API_KEY=AIzaSyCwXmhHAPwA7SL2u4L8XXyyLlU1Aucb8b4
FIREBASE_AUTH_DOMAIN=fifty7-2b2eb.firebaseapp.com
FIREBASE_PROJECT_ID=fifty7-2b2eb
FIREBASE_STORAGE_BUCKET=fifty7-2b2eb.firebasestorage.app
FIREBASE_MESSAGING_SENDER_ID=595848198631
FIREBASE_APP_ID=1:595848198631:web:d4c5a6c8227e4b66526542
FIREBASE_DATABASE_URL=https://fifty7-2b2eb-default-rtdb.firebaseio.com
FIREBASE_ALLOWED_EMAIL=lovesinhchauhan1935@gmail.com
```

### ✅ Database (Already Correct - Railway Auto-Provided)
Keep as-is.

### 🔧 Broker (NEED TO ADD)
Add these new variables:
```
BROKER_TYPE=angel
BROKER_API_KEY=0m0sXIBK
BROKER_CLIENT_ID=BBGV1001
BROKER_USERNAME=BBGV1001
BROKER_PWD=1935
BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4
```

**Important**: You currently have lowercase versions (`api_key`, `client_id`, `token`). 
- **Option 1**: Keep both (code supports both formats)
- **Option 2**: Remove lowercase ones and use only `BROKER_*` format (recommended)

### 🔧 WebSocket
```bash
WEBSOCKET_ENABLED=false  # Keep disabled if you don't need real-time updates
```

---

## 🎯 What Will Be Fixed

After adding `BROKER_*` variables:

1. ✅ **"TOTP token not configured"** → Fixed
2. ✅ **"Cannot fetch symbol token"** → Fixed  
3. ✅ **"No valid session"** → Fixed
4. ✅ **Market data will load** → Fixed
5. ✅ **Broker session will generate** → Fixed

---

## 📝 Summary

**Add these 7 variables to Railway:**
```bash
BROKER_TYPE=angel
BROKER_API_KEY=0m0sXIBK
BROKER_CLIENT_ID=BBGV1001
BROKER_USERNAME=BBGV1001
BROKER_PWD=1935
BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4
BROKER_API_SECRET=8a5bd331-9445-4d0e-a975-24ef7c73162a
```

**After adding, Railway will auto-redeploy and all broker errors should be resolved!** ✅

