# How to Disable Railway App Sleeping

## Quick Fix: Disable App Sleeping in Railway Dashboard

Railway's free tier automatically puts services to sleep after ~10 minutes of inactivity. For a trading system that needs to run 24/7, you **MUST disable this feature**.

### Steps:

1. **Go to Railway Dashboard**: https://railway.app/dashboard
2. **Select your service** (the main Streamlit app)
3. **Click "Settings"** tab (gear icon)
4. **Scroll down** to find **"App Sleeping"** or **"Serverless"** section
5. **Toggle OFF** "Enable App Sleeping" or "Serverless"
6. **Save changes** (Railway will automatically redeploy)

### For Both Services:

If you have **two services** (Streamlit + WebSocket):
1. **Main Service** (Streamlit): Disable App Sleeping
2. **WebSocket Service**: Disable App Sleeping

### After Disabling:

- ✅ Service stays awake 24/7
- ✅ Tick streamer continues receiving data
- ✅ Live runner continues executing trades
- ✅ No data loss or missed trades
- ⚠️ Uses more resources (but free tier allows this)

## Alternative: Upgrade to Railway Pro

Railway Pro ($20/month) does NOT have app sleeping - services are always on.

## Verification

After disabling, check logs:
- Should see continuous activity (tick updates, keep-alive messages)
- Service should not show "sleeping" status
- Tick streamer should stay connected

---

**RECOMMENDED:** Disable App Sleeping for both services to ensure 24/7 operation.

