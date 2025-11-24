# Railway PORT Error Fix Guide

## Error: "PORT variable must be integer between 0 and 65535"

### ✅ Quick Fix

This error occurs when Railway can't validate the PORT environment variable. Here's how to fix it:

---

## If Setting Up WebSocket Service

### Step 1: Check Service Type

1. Go to Railway Dashboard → Your WebSocket Service
2. Click **Settings**
3. Verify **Service Type** is set to **"Web Service"** (not "Empty Service")
4. If it's wrong, you may need to recreate the service as a Web Service

### Step 2: Remove Manual PORT Variable

1. Go to Railway Dashboard → Your Service → **Variables** tab
2. **Delete** any manually set `PORT` variable
3. Railway automatically provides `PORT` for web services - you don't need to set it!

### Step 3: Verify Start Command

In your service settings, **Start Command** should be:
```bash
python start_websocket.py
```

### Step 4: Deploy

Railway will automatically:
- Provide `PORT` environment variable
- Set it to a valid port (typically 443 for HTTPS or a dynamic port)
- Validate it before your code runs

---

## If Running in Main Streamlit Service

**Important**: Railway only exposes ONE port per service.

Your main Streamlit service already uses `PORT` for the Streamlit app. You **cannot** run WebSocket on a separate port in the same service.

### Solution: Disable WebSocket in Main Service

Add this environment variable to your main Streamlit service:

```bash
WEBSOCKET_ENABLED=false
```

Then deploy WebSocket as a **separate Railway service** (see main guide).

---

## Verification

After fixing, check your Railway logs. You should see:

```
Starting WebSocket server on 0.0.0.0:443
PORT environment variable: 443
WebSocket server started successfully
```

(Note: Port number may vary - Railway assigns it automatically)

---

## Still Having Issues?

1. **Check Logs**: Railway Dashboard → Your Service → Logs
2. **Verify Start Command**: Must be `python start_websocket.py`
3. **Service Type**: Must be "Web Service"
4. **No Manual PORT**: Remove any manually set PORT variable

---

**Need More Help?** See `RAILWAY_WEBSOCKET_SETUP.md` for complete setup guide.

