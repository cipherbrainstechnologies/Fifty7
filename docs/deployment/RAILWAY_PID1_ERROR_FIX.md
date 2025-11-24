# Railway "failed to exec pid1" Error Fix

## Error: "ERROR (catatonit:2): failed to exec pid1: No such file or directory"

### Problem

This error occurs when Railway can't find or execute the start command. Common causes:

1. **Python path not found** - Railway can't find `python` command
2. **Script file missing** - `start_streamlit.py` not in repository
3. **Wrong working directory** - Railway can't find the script
4. **Python version mismatch** - Wrong Python interpreter

### ✅ Solutions

#### Solution 1: Use `python3` instead of `python`

Railway's Python environment might use `python3` instead of `python`.

**Update Procfile:**
```
web: python3 start_streamlit.py
```

**Or in Railway Dashboard → Start Command:**
```bash
python3 start_streamlit.py
```

#### Solution 2: Use Direct Streamlit Command (Alternative)

If the script approach doesn't work, use Streamlit directly with environment variable:

**In Railway Dashboard → Start Command:**
```bash
streamlit run dashboard/ui_frontend.py --server.port=${PORT} --server.address=0.0.0.0
```

**Note**: Railway should expand `${PORT}` in start commands (different from `$PORT`).

#### Solution 3: Use Full Python Path

**In Railway Dashboard → Start Command:**
```bash
/usr/bin/python3 start_streamlit.py
```

Or:
```bash
/usr/local/bin/python3 start_streamlit.py
```

#### Solution 4: Verify File Exists

1. Check that `start_streamlit.py` is committed to Git:
   ```bash
   git ls-files | grep start_streamlit.py
   ```

2. Verify it's in the root directory (not in a subdirectory)

3. Check file permissions (should be readable):
   ```bash
   ls -la start_streamlit.py
   ```

#### Solution 5: Check Railway Service Type

1. Railway Dashboard → Your Service → Settings
2. Verify **Service Type** is **"Web Service"** (not "Empty Service" or other)
3. Railway only provides `PORT` for Web Services

### Recommended Configuration

**Procfile:**
```
web: python3 start_streamlit.py
```

**Railway Dashboard → Start Command:**
```bash
python3 start_streamlit.py
```

**Or if that doesn't work:**
```bash
streamlit run dashboard/ui_frontend.py --server.port=${PORT} --server.address=0.0.0.0
```

### Verification

After fixing, Railway logs should show:
```
Starting Streamlit on 0.0.0.0:443
PORT environment variable: 443
```

Or if using direct command:
```
You can now view your Streamlit app in your browser.
Local URL: http://0.0.0.0:443
```

### Debugging Steps

1. **Check Railway Logs** - Look for the exact error message
2. **Verify Python Version** - Railway should use Python 3.12.9 (from `runtime.txt`)
3. **Check Build Logs** - Ensure `requirements.txt` installed successfully
4. **Test Locally** - Run `python3 start_streamlit.py` locally to verify script works

### Alternative: Use Railway's Nixpacks Detection

Railway can auto-detect Python apps. Try:

1. Remove custom start command
2. Let Railway auto-detect from `Procfile`
3. Or create `railway.json`:
   ```json
   {
     "build": {
       "builder": "NIXPACKS"
     },
     "deploy": {
       "startCommand": "python3 start_streamlit.py",
       "restartPolicyType": "ON_FAILURE",
       "restartPolicyMaxRetries": 10
     }
   }
   ```

---

**Status**: Try `python3` first, then direct Streamlit command if needed

