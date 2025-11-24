# Railway Streamlit Start Command Fix

## Error: "Invalid value for '--server.port': '$PORT' is not a valid integer"

### Problem

Railway doesn't expand `$PORT` environment variables in start commands like Heroku does. When you use:
```bash
streamlit run dashboard/ui_frontend.py --server.port=$PORT --server.address=0.0.0.0
```

Railway passes the literal string `$PORT` to Streamlit instead of the actual port number.

### ✅ Solution

We've created a startup script (`start_streamlit.py`) that:
1. Reads `PORT` from environment variables
2. Validates it's a valid integer (0-65535)
3. Passes it correctly to Streamlit

### Configuration

**Updated Files:**
- `Procfile` - Now uses: `python start_streamlit.py`
- `render.yaml` - Updated start command
- `start_streamlit.py` - New startup script

### Railway Configuration

In your Railway service settings:

**Start Command:**
```bash
python start_streamlit.py
```

**Or** if Railway auto-detects from Procfile, it will use:
```
web: python start_streamlit.py
```

### How It Works

The `start_streamlit.py` script:
1. Reads `PORT` from Railway environment
2. Validates the port number
3. Sets `STREAMLIT_SERVER_PORT` environment variable
4. Starts Streamlit with correct arguments:
   ```python
   streamlit run dashboard/ui_frontend.py --server.port <actual_port> --server.address 0.0.0.0
   ```

### Verification

After deploying, check Railway logs. You should see:
```
Starting Streamlit on 0.0.0.0:443
PORT environment variable: 443
```

(Note: Port number may vary - Railway assigns it automatically)

### Alternative: Use Environment Variable Directly

Railway also supports setting `STREAMLIT_SERVER_PORT` directly:

1. In Railway Dashboard → Your Service → Variables
2. Add: `STREAMLIT_SERVER_PORT=$PORT` (Railway will expand this in env vars)
3. Use start command: `streamlit run dashboard/ui_frontend.py --server.address=0.0.0.0`

However, the script approach is more reliable and provides better error handling.

---

**Status**: ✅ Fixed - Use `python start_streamlit.py` as start command

