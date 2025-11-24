# Railway Two-Service Setup Guide

## Overview

You need **TWO separate Railway services**:

1. **Main Streamlit Service** - Your dashboard app
2. **WebSocket Service** - Real-time push updates

---

## Service 1: Main Streamlit App

### Configuration

**Service Name**: `nifty-options-trader` (or your main app name)

**Service Type**: Web Service

**Build Command**:
```bash
pip install -r requirements.txt
```

**Start Command**:
```bash
python start_streamlit.py
```

**OR** Railway will auto-detect from `Procfile`:
```
web: python start_streamlit.py
```

**Environment Variables**:
```bash
# Broker credentials
BROKER_TYPE=angel
BROKER_API_KEY=...
BROKER_CLIENT_ID=...
# ... other broker vars

# WebSocket client configuration (points to WebSocket service)
WEBSOCKET_ENABLED=true
WEBSOCKET_PUBLIC_DOMAIN=your-websocket-service.railway.app
PUBLIC_URL=https://your-websocket-service.railway.app
```

---

## Service 2: WebSocket Server

### Configuration

**Service Name**: `nifty-options-websocket` (or your WebSocket service name)

**Service Type**: Web Service

**Build Command**:
```bash
pip install -r requirements.txt
```

**Start Command**:
```bash
python start_websocket.py
```

**Environment Variables**:
```bash
# PORT is automatically provided by Railway - don't set it manually!
WEBSOCKET_HOST=0.0.0.0  # Optional, defaults to 0.0.0.0
```

**Important**: Railway automatically provides `PORT` for web services. Don't set it manually!

---

## Quick Checklist

### Main Streamlit Service:
- [ ] Service Type: **Web Service**
- [ ] Start Command: `python start_streamlit.py`
- [ ] Has `Procfile` with: `web: python start_streamlit.py`
- [ ] Environment variables include broker credentials
- [ ] Environment variables include WebSocket client config (pointing to WebSocket service)

### WebSocket Service:
- [ ] Service Type: **Web Service**
- [ ] Start Command: `python start_websocket.py`
- [ ] **No Procfile needed** (or create one with: `web: python start_websocket.py`)
- [ ] Environment variables: Only `WEBSOCKET_HOST=0.0.0.0` (optional)
- [ ] **Do NOT set PORT manually** - Railway provides it

---

## Verification

### Main Streamlit Service Logs Should Show:
```
Starting Streamlit on 0.0.0.0:443
PORT environment variable: 443
```

### WebSocket Service Logs Should Show:
```
Starting WebSocket server on 0.0.0.0:8080
PORT environment variable: 8080
WebSocket server started successfully
INFO:     Uvicorn running on http://0.0.0.0:8080
```

---

## Common Issues

### Issue: "failed to exec pid1: No such file or directory"

**Cause**: Wrong start command or missing script file

**Fix**:
1. Check service is using correct start command:
   - Main service: `python start_streamlit.py`
   - WebSocket service: `python start_websocket.py`
2. Verify both scripts exist in repository
3. Check service type is "Web Service"

### Issue: Main service trying to run WebSocket script

**Cause**: Procfile or start command is wrong

**Fix**: 
- Main service must use `start_streamlit.py`
- WebSocket service must use `start_websocket.py`
- Check Railway service settings → Start Command

---

## Files Reference

- `start_streamlit.py` - For main Streamlit service
- `start_websocket.py` - For WebSocket service
- `Procfile` - Used by main Streamlit service (contains: `web: python start_streamlit.py`)

---

**Status**: ✅ Both services should work independently

