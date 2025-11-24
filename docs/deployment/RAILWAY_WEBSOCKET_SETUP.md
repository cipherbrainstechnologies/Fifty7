# Railway WebSocket Configuration Guide

**Status**: ✅ WebSocket is **fully implemented** in the codebase  
**Platform**: Railway.app  
**Date**: 2025-01-27

## Overview

The application has WebSocket integration for real-time push updates. However, Railway's single-port architecture requires special configuration.

## Current Implementation

### ✅ What's Already Implemented

1. **WebSocket Server** (`engine/websocket_server.py`)
   - FastAPI-based WebSocket server
   - Real-time event broadcasting
   - State synchronization
   - Auto-reconnect support

2. **WebSocket Client** (`engine/websocket_client.py`)
   - Streamlit dashboard client
   - Message queuing
   - Callback system

3. **Environment Detection**
   - Automatically detects Railway environment
   - Supports localhost and production configurations
   - Uses WSS (secure WebSocket) in production

## Railway Deployment Options

Railway typically exposes **only ONE port per service**. You have three options:

### Option 1: Disable WebSocket (Simplest) ✅ Recommended for Quick Start

**Use this if**: You don't need real-time updates and can use polling instead.

**Steps:**
1. In Railway dashboard, add environment variable:
   ```bash
   WEBSOCKET_ENABLED=false
   ```

2. Update `config/config.yaml`:
   ```yaml
   websocket:
     enabled: false  # Disable WebSocket in production
   ```

**Result**: App works normally with polling-based updates (slower but functional).

---

### Option 2: Separate WebSocket Service (Best for Real-Time) ⭐ Recommended

**Use this if**: You need real-time WebSocket updates.

**Architecture:**
- **Service 1**: Streamlit dashboard (main app)
- **Service 2**: WebSocket server (separate service)

#### Step 1: Create WebSocket Service in Railway

1. In Railway dashboard, click **"New"** → **"Empty Service"**
2. Name it: `nifty-options-websocket`
3. Connect the same GitHub repository
4. Configure:

   **Build Command:**
   ```bash
   pip install -r requirements.txt
   ```

   **Start Command:**
   ```bash
   python -m engine.websocket_server --port $PORT --host 0.0.0.0
   ```

   **Or create a startup script** (`start_websocket.py`):
   ```python
   import os
   from engine.websocket_server import start_websocket_server
   
   port = int(os.getenv("PORT", "8765"))
   start_websocket_server(host="0.0.0.0", port=port)
   
   # Keep running
   import time
   while True:
       time.sleep(1)
   ```

   **Start Command (alternative):**
   ```bash
   python start_websocket.py
   ```

5. **Set Environment Variables:**
   ```bash
   PORT=$PORT  # Railway provides this automatically
   WEBSOCKET_HOST=0.0.0.0
   ```

#### Step 2: Get WebSocket Service URL

After deployment, Railway will provide:
- **Public Domain**: `https://nifty-options-websocket.railway.app`
- Or custom domain if configured

#### Step 3: Configure Main App

In your **main Streamlit service**, add environment variables:

```bash
# WebSocket Configuration
WEBSOCKET_ENABLED=true
WEBSOCKET_PUBLIC_DOMAIN=nifty-options-websocket.railway.app
PUBLIC_URL=https://nifty-options-websocket.railway.app
```

Or add to `config/config.yaml`:
```yaml
websocket:
  enabled: true
  public_domain: "nifty-options-websocket.railway.app"
  uri: "wss://nifty-options-websocket.railway.app/ws"
```

#### Step 4: Configure CORS (Important!)

In the WebSocket service, ensure CORS allows your main app domain:

```python
# In engine/websocket_server.py (already configured)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**For production security**, update to:
```python
allow_origins=[
    "https://your-main-app.railway.app",
    "https://your-custom-domain.com"
]
```

---

### Option 3: Same Port with Path Routing (Advanced) 🔧

**Use this if**: You want everything on one port but need WebSocket support.

**Note**: This requires mounting FastAPI alongside Streamlit, which is more complex. Not currently implemented.

**Future Implementation**: Would require:
- ASGI middleware to route `/ws` to WebSocket server
- Streamlit to run under ASGI server
- More complex deployment setup

---

## Quick Setup Checklist

### For Option 1 (Disable WebSocket):

- [ ] Add `WEBSOCKET_ENABLED=false` to Railway environment variables
- [ ] Or set `websocket.enabled: false` in `config/config.yaml`
- [ ] Deploy and test

### For Option 2 (Separate Service):

- [ ] Create new Railway service for WebSocket
- [ ] Configure build/start commands
- [ ] Get WebSocket service public domain
- [ ] Add `WEBSOCKET_PUBLIC_DOMAIN` to main app environment variables
- [ ] Add `PUBLIC_URL` or `RAILWAY_PUBLIC_DOMAIN` to main app
- [ ] Configure CORS to allow main app domain
- [ ] Deploy both services
- [ ] Test WebSocket connection

---

## Environment Variables Reference

### Main App (Streamlit Service)

```bash
# WebSocket Client Configuration
WEBSOCKET_ENABLED=true
WEBSOCKET_PUBLIC_DOMAIN=your-websocket-service.railway.app
PUBLIC_URL=https://your-websocket-service.railway.app

# Or use Railway-specific variables
RAILWAY_PUBLIC_DOMAIN=your-websocket-service.railway.app
RAILWAY_STATIC_URL=https://your-websocket-service.railway.app

# Broker credentials (existing)
BROKER_TYPE=angel
BROKER_API_KEY=...
# ... other broker vars
```

### WebSocket Service (Separate Service)

```bash
# Port (Railway provides automatically)
PORT=$PORT

# Host binding
WEBSOCKET_HOST=0.0.0.0

# Optional: CORS origins (comma-separated)
CORS_ORIGINS=https://your-main-app.railway.app,https://your-domain.com
```

---

## Testing WebSocket Connection

### 1. Check WebSocket Server Health

Visit: `https://your-websocket-service.railway.app/health`

Should return:
```json
{
  "status": "healthy",
  "connections": 0,
  "timestamp": "2025-01-27T..."
}
```

### 2. Check Main App Logs

In Railway dashboard → Your main app → Logs, look for:
```
[I] WebSocket client initialized and connected to wss://...
```

### 3. Browser Console Test

Open browser console on your main app and check for:
- WebSocket connection errors
- WebSocket messages received

### 4. Test Real-Time Updates

1. Trigger a trade or position update in the app
2. Check if dashboard updates automatically (within 2 seconds)
3. If using polling, updates will be slower (5-15 seconds)

---

## Troubleshooting

### Issue: "Cannot determine WebSocket URI"

**Solution**: Set one of these environment variables:
- `RAILWAY_PUBLIC_DOMAIN`
- `RAILWAY_STATIC_URL`
- `PUBLIC_URL`
- Or configure `websocket.public_domain` in `config.yaml`

### Issue: WebSocket Connection Failed (CORS error)

**Solution**: 
1. Check CORS configuration in `engine/websocket_server.py`
2. Ensure your main app domain is in `allow_origins`
3. Check browser console for specific CORS error

### Issue: WebSocket Server Won't Start

**Solution**:
1. Check Railway logs for port binding errors
2. Ensure `WEBSOCKET_PORT` is set if using separate service
3. Verify `PORT` environment variable is available

### Issue: WebSocket Connects But No Messages

**Solution**:
1. Check Event Bus is enabled: `event_bus.enabled: true` in config
2. Check State Store is enabled: `state_store.enabled: true` in config
3. Verify WebSocket server is subscribed to events (check logs)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Railway Platform                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────┐      ┌──────────────────────┐   │
│  │  Streamlit Service   │      │  WebSocket Service   │   │
│  │  (Main App)          │◄────►│  (Separate)          │   │
│  │                      │ WSS  │                      │   │
│  │  - Dashboard UI      │      │  - FastAPI Server    │   │
│  │  - WebSocket Client  │      │  - WebSocket Server  │   │
│  │  - Port: $PORT       │      │  - Port: $PORT       │   │
│  │  - Domain: *.app     │      │  - Domain: *.app     │   │
│  └──────────────────────┘      └──────────────────────┘   │
│           │                              │                  │
│           │                              │                  │
│           └──────────┬───────────────────┘                  │
│                      │                                      │
│           ┌──────────▼──────────┐                          │
│           │   Event Bus +       │                          │
│           │   State Store       │                          │
│           │   (Shared State)    │                          │
│           └─────────────────────┘                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Code Changes Made

### Files Modified:

1. **`engine/websocket_server.py`**
   - Added `_is_production()` function
   - Added `_get_websocket_host()` function
   - Added `_get_websocket_port()` function
   - Updated `start_websocket_server()` to use environment-aware defaults

2. **`dashboard/ui_frontend.py`**
   - Added `_is_production` detection
   - Added `_get_websocket_uri()` function
   - Updated WebSocket initialization to use environment variables
   - Supports WSS in production, WS in localhost

---

## Next Steps

1. **Choose deployment option** (Option 1 or Option 2 recommended)
2. **Configure Railway environment variables**
3. **Deploy and test**
4. **Monitor logs** for WebSocket connection status
5. **Verify real-time updates** work correctly

---

## References

- Railway Documentation: https://docs.railway.app
- WebSocket Implementation: `memory-bank/ARCHITECTURE_IMPLEMENTATION.md`
- Architecture Overview: `memory-bank/architecture.md`

---

**Last Updated**: 2025-01-27  
**Status**: ✅ Ready for Railway Deployment

