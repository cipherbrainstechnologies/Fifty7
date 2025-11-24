# Railway Firebase Configuration - Environment Variables

## Overview

**For Railway deployment, you must use Environment Variables**, not `secrets.toml` (that's only for local development and Streamlit Cloud).

## ✅ Answer: Yes, you need to add Firebase config as environment variables on Railway

Even though you have Firebase config in `secrets.toml`, Railway **doesn't use that file**. You need to add the values as environment variables.

---

## Railway Environment Variables Setup

### Step 1: Get Your Firebase Values from secrets.toml

From your `.streamlit_disabled/secrets.toml`, you already have:

```toml
[firebase]
apiKey = "AIzaSyCwXmhHAPwA7SL2u4L8XXyyLlU1Aucb8b4"
authDomain = "fifty7-2b2eb.firebaseapp.com"
projectId = "fifty7-2b2eb"
storageBucket = "fifty7-2b2eb.firebasestorage.app"
messagingSenderId = "595848198631"
appId = "1:595848198631:web:d4c5a6c8227e4b66526542"
databaseURL = "https://fifty7-2b2eb-default-rtdb.firebaseio.com"
allowedEmail = "lovesinhchauhan1935@gmail.com"
```

### Step 2: Add to Railway as Environment Variables

1. **Go to Railway Dashboard**: https://railway.app
2. **Select your main Streamlit service** (not the WebSocket service)
3. Click **"Variables"** tab
4. Click **"New Variable"** and add each of these:

**Add these environment variables:**

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

### Step 3: Verify

After adding variables and redeploying, check Railway logs. You should see:

```
[I] Loaded Firebase config from environment variables
[I] Firebase authentication initialized successfully. Allowed email: lovesinhchauhan1935@gmail.com
```

---

## Complete Railway Environment Variables List

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

### Broker Configuration (Also from secrets.toml)

```bash
BROKER_TYPE=angel
BROKER_API_KEY=sz5neY7b
BROKER_API_SECRET=8a5bd331-9445-4d0e-a975-24ef7c73162a
BROKER_CLIENT_ID=BBGV1001
BROKER_USERNAME=BBGV1001
BROKER_PWD=1935
BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4
```

### Database Configuration (Optional)

```bash
DATABASE_URL=postgresql://postgres:QhxSNKGHpcCIqOuZbqggzcqqyYdHAVsK@turntable.proxy.rlwy.net:17300/railway
PGHOST=turntable.proxy.rlwy.net
PGPORT=17300
PGUSER=postgres
PGPASSWORD=QhxSNKGHpcCIqOuZbqggzcqqyYdHAVsK
PGDATABASE=railway
```

---

## How It Works

The code now checks environment variables **first** (for Railway), then falls back to:
1. ✅ Environment variables (Railway, Render, etc.) - **Priority 1**
2. Streamlit secrets (Streamlit Cloud) - Priority 2
3. secrets.toml file (Local development) - Priority 3

---

## Quick Reference

**Local Development**: Uses `.streamlit/secrets.toml`  
**Streamlit Cloud**: Uses Streamlit Cloud Secrets (TOML format)  
**Railway/Render**: Uses Environment Variables (this guide)

---

**Status**: ✅ Code updated to read from environment variables. **Add the Firebase variables to Railway now!**

