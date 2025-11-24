# Railway Broker Configuration Fix

## Issues Found

1. **Broker env vars using wrong format**: Railway has lowercase keys (`api_key`, `client_id`, `token`) instead of `BROKER_*` format
2. **WebSocket trying to connect to wrong URL**: Connecting to main app instead of WebSocket service
3. **Code updated** to support both formats

---

## ✅ Fix 1: Update Railway Environment Variables

### Current (Wrong Format):
```bash
api_key="0m0sXIBK"
client_id="BBGV1001"
token="3FMVJ5H5DBUAHBVGT5O2ZLBHU4"
type="angel"
```

### Should Be (Preferred Format):
```bash
BROKER_TYPE=angel
BROKER_API_KEY=0m0sXIBK
BROKER_CLIENT_ID=BBGV1001
BROKER_USERNAME=BBGV1001
BROKER_PWD=1935
BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4
BROKER_API_SECRET=8a5bd331-9445-4d0e-a975-24ef7c73162a
```

**Note**: Code now supports BOTH formats, but `BROKER_*` format is preferred.

---

## ✅ Fix 2: Update WebSocket Configuration

### Current Issue:
WebSocket client is trying to connect to main app URL:
```
wss://web-production-cf722.up.railway.app/ws
```

### Should Connect To:
Your WebSocket service URL:
```
wss://nifty-option-websocket-production.up.railway.app/ws
```

### Railway Variables to Update:

**Remove or Update:**
- `PUBLIC_URL="https://nifty-option-websocket-production.up.railway.app"` ✅ (This is correct)

**Add:**
```bash
WEBSOCKET_PUBLIC_DOMAIN=nifty-option-websocket-production.up.railway.app
```

Or if you want to disable WebSocket completely (since it's set to false):
```bash
WEBSOCKET_ENABLED=false  # Already set - this is fine
```

---

## 📋 Complete Railway Environment Variables

### Firebase (Already Correct ✅)
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

### Broker (Need to Add/Fix)
```bash
BROKER_TYPE=angel
BROKER_API_KEY=0m0sXIBK
BROKER_CLIENT_ID=BBGV1001
BROKER_USERNAME=BBGV1001
BROKER_PWD=1935
BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4
BROKER_API_SECRET=8a5bd331-9445-4d0e-a975-24ef7c73162a
```

### WebSocket (Optional - Only if enabling WebSocket)
```bash
WEBSOCKET_ENABLED=false  # Keep false to disable
# OR if enabling:
WEBSOCKET_ENABLED=true
WEBSOCKET_PUBLIC_DOMAIN=nifty-option-websocket-production.up.railway.app
```

---

## 🔧 Action Items

### Step 1: Add Broker Environment Variables

In Railway Dashboard → Your Main Service → Variables:

**Add these (or keep lowercase ones if code update works):**
```bash
BROKER_TYPE=angel
BROKER_API_KEY=0m0sXIBK
BROKER_CLIENT_ID=BBGV1001
BROKER_USERNAME=BBGV1001
BROKER_PWD=1935
BROKER_TOKEN=3FMVJ5H5DBUAHBVGT5O2ZLBHU4
```

**Note**: Code now supports both `BROKER_API_KEY` and `api_key` formats. Using `BROKER_*` format is recommended.

### Step 2: Fix WebSocket Configuration

**Option A: Disable WebSocket (Recommended for now)**
```bash
WEBSOCKET_ENABLED=false  # Already set ✅
```

**Option B: Enable WebSocket (If you want real-time updates)**
```bash
WEBSOCKET_ENABLED=true
WEBSOCKET_PUBLIC_DOMAIN=nifty-option-websocket-production.up.railway.app
```

And make sure your WebSocket service is running and accessible.

### Step 3: Remove Duplicate/Lowercase Variables

**Remove these** (they're duplicates):
```bash
api_key="0m0sXIBK"
client_id="BBGV1001"
token="3FMVJ5H5DBUAHBVGT5O2ZLBHU4"
type="angel"
```

Or keep them if you prefer - code now supports both formats.

---

## ✅ Expected Results

After updating environment variables:

1. ✅ **"TOTP token not configured"** error → Fixed
2. ✅ **"Cannot fetch symbol token"** error → Fixed
3. ✅ **WebSocket connection errors** → Fixed (if disabled) or connecting to correct service (if enabled)
4. ✅ **Broker session will generate** successfully
5. ✅ **Market data will load** successfully

---

**Status**: Code updated to support both formats. **Add BROKER_* variables to Railway!**

