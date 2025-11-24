# Complete Railway Environment Variables Guide

## Overview

**Railway uses environment variables, NOT secrets.toml**. You must add all configuration as environment variables in Railway Dashboard.

---

## ✅ Complete Environment Variables List

### Firebase Configuration (Required for Authentication)

```bash
FIREBASE_API_KEY=AIzaSyCwXmhHAPwA7SL2u4L8XXyyLlU1Aucb8b4
FIREBASE_AUTH_DOMAIN=fifty7-2b2eb.firebaseapp.com
FIREBASE_PROJECT_ID=fifty7-2b2eb
FIREBASE_STORAGE_BUCKET=fifty7-2b2eb.firebasestorage.app
FIREBASE_MESSAGING_SENDER_ID=595848198631
FIREBASE_APP_ID=1:595848198631:web:d4c5a6c8227e4b66526542
FIREBASE_DATABASE_URL=https://fifty7-2b2eb-default-rtdb.firebaseio.com
FIREBASE_ALLOWED_EMAIL=lovesinhchauhan1935@gmail.com
```

### Broker Configuration (Required for Trading)

```bash
BROKER_TYPE=angel
BROKER_API_KEY=sz5neY7b
BROKER_API_SECRET=8a5bd331-9445-4d0e-a975-24ef7c73162a
BROKER_CLIENT_ID=BBGV1001
BROKER_USERNAME=BBGV1001
BROKER_PWD=1935
BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4
```

**Note:** `BROKER_TOKEN` is the TOTP secret (the one that fixes the "TOTP token not configured" error).

### SmartAPI Apps Configuration (Optional but Recommended)

#### Trading App
```bash
SMARTAPI_TRADING_API_KEY=sz5neY7b
SMARTAPI_TRADING_API_SECRET=8a5bd331-9445-4d0e-a975-24ef7c73162a
```

#### Historical Data App
```bash
SMARTAPI_HISTORICAL_API_KEY=oV0N6xt7
SMARTAPI_HISTORICAL_API_SECRET=4ab84310-301a-4114-be83-4b171e322e49
```

#### Publisher App (for WebSocket)
```bash
SMARTAPI_PUBLISHER_API_KEY=MIavKEDZ
SMARTAPI_PUBLISHER_API_SECRET=899402fe-2641-4ffa-9683-545e60329642
```

### Database Configuration (If using PostgreSQL)

```bash
DATABASE_URL=postgresql://postgres:QhxSNKGHpcCIqOuZbqggzcqqyYdHAVsK@turntable.proxy.rlwy.net:17300/railway
PGHOST=turntable.proxy.rlwy.net
PGPORT=17300
PGUSER=postgres
PGPASSWORD=QhxSNKGHpcCIqOuZbqggzcqqyYdHAVsK
PGDATABASE=railway
```

### WebSocket Configuration (If using separate WebSocket service)

```bash
WEBSOCKET_ENABLED=true
WEBSOCKET_PUBLIC_DOMAIN=your-websocket-service.railway.app
PUBLIC_URL=https://your-websocket-service.railway.app
```

---

## 📋 Quick Setup Steps

### Step 1: Go to Railway Dashboard

1. Open https://railway.app
2. Select your **main Streamlit service** (not WebSocket service)
3. Click **"Variables"** tab

### Step 2: Add Environment Variables

Click **"New Variable"** for each variable and add:

1. **All Firebase variables** (8 variables)
2. **All Broker variables** (7 variables) - **Important: BROKER_TOKEN fixes the TOTP error**
3. **SmartAPI Apps variables** (6 variables, optional)
4. **Database variables** (6 variables, if using)
5. **WebSocket variables** (3 variables, if using)

### Step 3: Save and Redeploy

After adding all variables, Railway will automatically redeploy. Check logs to verify:

- ✅ `Loaded broker config from environment variables`
- ✅ `Loaded Firebase config from environment variables`
- ✅ No more "TOTP token not configured" errors

---

## 🔧 Code Updates

The code has been updated to:
1. ✅ Check environment variables **first** (for Railway)
2. ✅ Fall back to secrets.toml (for local development)
3. ✅ Fall back to Streamlit secrets (for Streamlit Cloud)

**Priority Order:**
1. Environment Variables (Railway/Render) ← **You're here**
2. secrets.toml file (Local)
3. Streamlit secrets (Streamlit Cloud)

---

## ❌ Common Errors Fixed

### Error: "TOTP token not configured in secrets.toml"
**Fix:** Add `BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4` environment variable

### Error: "No Firebase config found"
**Fix:** Add all 8 `FIREBASE_*` environment variables

### Error: "Cannot fetch symbol token: No valid session"
**Fix:** Add `BROKER_TOKEN` and all broker credentials

---

## 📝 Values from Your secrets.toml

All values are already in your `.streamlit_disabled/secrets.toml`. Just copy them to Railway environment variables using the format above.

---

**Status**: ✅ Code updated to read from environment variables. **Add all variables to Railway now!**

