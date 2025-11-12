# Troubleshooting Guide

## Firebase Authentication Issues

### Issue: "pyrebase4 not installed"

**Symptoms:**
- Error message: "Firebase initialization error: pyrebase4 not installed"
- App shows fallback authentication instead of Firebase login

**Solution Steps:**

#### Step 1: Verify requirements.txt

Check that `requirements.txt` includes:
```txt
pyrebase4>=4.7.1
firebase-admin>=6.2.0
```

#### Step 2: Verify Git Commit

Ensure `requirements.txt` is committed and pushed:
```bash
git status requirements.txt
git log --oneline -1 requirements.txt
```

If not committed:
```bash
git add requirements.txt
git commit -m "Add Firebase dependencies"
git push
```

#### Step 3: Force Streamlit Cloud Redeploy

1. Go to https://share.streamlit.io/
2. Select your app
3. Click **"⋮"** (three dots) → **"Settings"**
4. Scroll down and click **"Reboot app"** or **"Redeploy"**
5. Wait for deployment to complete (check deployment logs)

#### Step 4: Check Deployment Logs

1. In Streamlit Cloud, go to your app
2. Click **"Manage app"** → **"Logs"**
3. Look for:
   - `Installing pyrebase4...`
   - `Successfully installed pyrebase4`
   - Any installation errors

#### Step 5: Alternative - Check Package Installation

If pyrebase4 fails to install, try:
- Check if package name is correct: `pyrebase4` (not `pyrebase`)
- Verify Python version compatibility
- Check for conflicting dependencies

### Issue: "KeyError: 'broker'"

**Symptoms:**
- Error: `KeyError: 'broker'` or similar
- App crashes when accessing broker configuration

**Solution:**
- This has been fixed in the latest code
- Ensure you have the latest version deployed
- Broker config is now accessed safely using `.get()` methods

### Issue: "Firebase configuration not found"

**Symptoms:**
- Warning message about Firebase configuration
- App uses fallback authentication

**Solution:**

1. **For Streamlit Cloud:**
   - Go to Settings → Secrets
   - Add `[firebase]` section with your Firebase config
   - Save and wait for redeploy

2. **For Local Development:**
   - Edit `.streamlit/secrets.toml`
   - Add `[firebase]` section

See `STREAMLIT_CLOUD_SETUP.md` for detailed instructions.

## Quick Fixes

### Force Dependency Reinstall

If dependencies aren't installing correctly:

1. **Clear Streamlit Cloud cache:**
   - Settings → Advanced → Clear cache
   - Redeploy

2. **Check requirements.txt format:**
   - Ensure no syntax errors
   - Each package on new line
   - No trailing spaces

3. **Verify package names:**
   - `pyrebase4` (correct)
   - `pyrebase` (wrong - old package)

### Verify Installation in Logs

Check deployment logs for:
```
Collecting pyrebase4>=4.7.1
Downloading pyrebase4-4.7.1-py3-none-any.whl
Successfully installed pyrebase4-4.7.1
```

If you see errors, check:
- Python version compatibility
- Network issues during installation
- Package conflicts

