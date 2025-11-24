# WebSocket Port Binding Fix for Railway

## Summary
Fixed the WebSocket server to properly use Railway's dynamic PORT environment variable instead of hardcoded values.

## Changes Made

### 1. **engine/websocket_server.py**
   - **Simplified `_get_websocket_port()` function:**
     - Now directly uses `os.getenv("PORT")` when available (Railway always provides this)
     - Removed complex logic that tried to use PORT+1
     - Removed hardcoded fallbacks to 8765
     - Uses 8000 as default for local development only
   
   - **Updated production check:**
     - Changed warning from "WebSocket server requires a separate port" to error when PORT is missing
     - Railway provides PORT automatically, so this should never happen in production

### 2. **start_websocket.py** 
   - No changes needed - already correctly reading PORT from environment and passing to `start_websocket_server()`

## How It Works Now

1. **In Railway Production:**
   - Railway sets `PORT` environment variable (e.g., 5432)
   - WebSocket server binds to `0.0.0.0:${PORT}`
   - Railway forwards traffic from `wss://nifty-option-websocket-production.up.railway.app/ws` to this port

2. **In Local Development:**
   - If `PORT` is not set, checks `WEBSOCKET_PORT` (defaults to 8000)
   - Server binds to `127.0.0.1:8000` (or configured port)

## Test Results
All scenarios tested and passing:
- ✅ Railway production with PORT=5432 → Uses 5432
- ✅ Local development without PORT → Uses 8000
- ✅ Local development with WEBSOCKET_PORT=9999 → Uses 9999
- ✅ Production with invalid PORT → Falls back to 8000

## Expected Logs
After deployment, logs should show:
```
Starting WebSocket server on 0.0.0.0:${PORT}
WebSocket server started on wss://0.0.0.0:${PORT}/ws
```

NOT:
```
WebSocket server started on wss://0.0.0.0:8080/ws  # ❌ Wrong
```

## Deployment
The WebSocket service is now fully Railway-compatible and will be reachable at:
`wss://nifty-option-websocket-production.up.railway.app/ws`