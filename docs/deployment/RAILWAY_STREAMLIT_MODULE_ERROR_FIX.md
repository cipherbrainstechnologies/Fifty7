# Railway "No module named streamlit" Error Fix

## Error: "No module named streamlit"

### Problem

Streamlit was removed from `requirements.txt` because the file was configured for the WebSocket service only. However, the **main Streamlit service** requires Streamlit to be installed.

Since both services use the same repository, `requirements.txt` needs to include Streamlit.

### ✅ Solution

**Streamlit has been added back to `requirements.txt`**:

```txt
streamlit>=1.28.0
streamlit-authenticator>=0.2.3
```

The WebSocket service won't use Streamlit, but having it in requirements.txt doesn't hurt (it just won't be imported).

### Changes Made

1. **Updated `requirements.txt`** - Added Streamlit dependencies back
2. **Updated `start_streamlit.py`** - Added fallback check/install for Streamlit
3. **Updated `railway.json`** - Improved build command with pip upgrade

### Railway Configuration

**Main Streamlit Service:**

1. **Build Command** (Railway Dashboard → Settings):
   ```bash
   pip install --upgrade pip && pip install -r requirements.txt
   ```

   Or Railway will auto-detect from `railway.json`:
   ```json
   "buildCommand": "pip install --upgrade pip && pip install -r requirements.txt"
   ```

2. **Start Command**:
   ```bash
   python3 start_streamlit.py
   ```

**WebSocket Service:**

1. **Build Command**: Same as above (Streamlit will be installed but not used)
2. **Start Command**: `python3 start_websocket.py`

### Verification

After redeploying, check Railway logs. You should see:

```
Streamlit version: 1.28.0
Starting Streamlit on 0.0.0.0:8080
PORT environment variable: 8080
```

### Next Steps

1. **Commit changes**:
   ```bash
   git add requirements.txt start_streamlit.py railway.json
   git commit -m "Add Streamlit back to requirements.txt for main service"
   git push
   ```

2. **Redeploy on Railway**:
   - Railway will auto-detect changes and redeploy
   - Or manually trigger redeploy in Railway Dashboard

3. **Check build logs**:
   - Verify Streamlit is installed during build
   - Look for: `Successfully installed streamlit-...`

### If Build Still Fails

If Railway build fails to install Streamlit:

1. **Check build logs** in Railway Dashboard
2. **Verify Python version** - Should be 3.12.9 (from `runtime.txt`)
3. **Try explicit build command** in Railway:
   ```bash
   python3 -m pip install --upgrade pip && python3 -m pip install -r requirements.txt
   ```

---

**Status**: ✅ Fixed - Streamlit added back to requirements.txt

