# Railway Deployment Guide for NIFTY Options Trading System

## Architecture Overview

This system uses **two separate Railway services**:

1. **Main Web Service** (`web`) - Streamlit Dashboard
2. **WebSocket Service** (`nifty-option-websocket`) - Real-time updates

## ✅ Deployment Steps

### 1. Main Web Service (Streamlit Dashboard)

**Procfile:** Already configured correctly
```
web: python start_streamlit.py
```

**Railway Configuration:**
1. Create a new Railway service named `web` or `nifty-options-web`
2. Connect your GitHub repository
3. **IMPORTANT:** Remove these environment variables if they exist:
   - `STREAMLIT_SERVER_PORT` (causes conflicts - the app sets this internally)
   - Any other Streamlit-specific port variables
4. Ensure `PORT` is set (Railway sets this automatically)
5. Deploy - Railway will use the Procfile and run `start_streamlit.py`

### 2. WebSocket Service (Real-time Updates)

**Procfile:** Use `Procfile.websocket` or create a separate repository
```
web: python start_websocket.py
```

**Railway Configuration:**
1. Create a new Railway service named `nifty-option-websocket`
2. Two options for deployment:
   
   **Option A: Same Repository (Recommended for simplicity)**
   - Connect the same GitHub repository
   - In Railway service settings, set:
     - **Root Directory**: `/` (same as main)
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `python start_websocket.py` (override Procfile)
   
   **Option B: Separate Repository**
   - Create a new repository for WebSocket service
   - Copy necessary files:
     - `start_websocket.py`
     - `engine/` directory
     - `requirements.txt`
     - `Procfile` (with WebSocket command)
   - Connect this new repository to Railway

3. Ensure `PORT` is set (Railway provides automatically)
4. Deploy

### 3. Environment Variables

**Main Web Service (`web`):**
```bash
# Railway provides automatically
PORT=<assigned-by-railway>

# Your app-specific variables
ANGELONE_API_KEY=<your-key>
ANGELONE_CLIENT_ID=<your-client-id>
ANGELONE_PASSWORD=<your-password>
ANGELONE_TOTP_TOKEN=<your-totp>

# DO NOT SET THESE (causes conflicts):
# ❌ STREAMLIT_SERVER_PORT
# ❌ STREAMLIT_SERVER_ADDRESS
```

**WebSocket Service (`nifty-option-websocket`):**
```bash
# Railway provides automatically
PORT=<assigned-by-railway>

# Optional (if you need to share state between services)
REDIS_URL=<your-redis-url>
```

## 🔧 Troubleshooting

### Issue: "Streamlit server port conflicts"
**Solution:** Remove `STREAMLIT_SERVER_PORT` from Railway environment variables. The app sets this internally using the `PORT` variable.

### Issue: "WebSocket connection failed"
**Solution:** Ensure WebSocket service is deployed separately and accessible at:
```
wss://nifty-option-websocket-production.up.railway.app/ws
```

### Issue: "Railway auto-detects Streamlit incorrectly"
**Solution:** The Procfile forces Railway to use your custom startup script instead of auto-detection.

## 📝 Important Notes

1. **Port Management**: Railway provides only ONE port per service via the `PORT` environment variable
2. **Service Separation**: WebSocket MUST be a separate Railway service (not same port as Streamlit)
3. **Custom Domains**: Configure after successful deployment
4. **Health Checks**: 
   - Streamlit: `https://<your-domain>/`
   - WebSocket: `https://<your-domain>/health`

## 🚀 Deployment Commands

After making changes:

```bash
# Commit your changes
git add .
git commit -m "Configure Railway deployment with Procfile"
git push origin main

# Railway auto-deploys on push
```

## ✅ Verification

1. **Main Web Service**: Visit `https://<your-web-service>.railway.app`
2. **WebSocket Service**: Check health at `https://<your-websocket-service>.railway.app/health`
3. **WebSocket Connection**: Dashboard should connect to `wss://<your-websocket-service>.railway.app/ws`

## 🎯 Final Architecture

```
┌─────────────────────────┐     ┌─────────────────────────┐
│   Main Web Service      │     │   WebSocket Service     │
│   (Streamlit Dashboard) │────▶│   (Real-time Updates)   │
│   Port: $PORT           │     │   Port: $PORT           │
│   Procfile: web         │     │   Separate Service      │
└─────────────────────────┘     └─────────────────────────┘
         ↓                                ↓
   Uses start_streamlit.py        Uses start_websocket.py
```