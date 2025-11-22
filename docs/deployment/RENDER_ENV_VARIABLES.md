# Render.com Environment Variables Setup Guide

## 📋 Quick Answer

**Do you need to add Streamlit config variables?** 
- **NO, they're optional!** The start command already handles port and address.
- **YES, if you want** to disable telemetry and run headless (recommended but not required).

---

## 🎯 What You Actually Need

### Required (Must Add):
1. **Broker Credentials** - Your trading API keys
2. **Firebase Config** (if using Firebase auth) - Your Firebase project details

### Optional (Recommended but Not Required):
1. **Streamlit Config** - Only 2 variables needed (see below)

---

## 📝 Step-by-Step: Adding Environment Variables in Render

### Step 1: Navigate to Your Service

1. Go to https://dashboard.render.com
2. Click on your service name (e.g., `nifty-options-trader`)
3. Click on **"Environment"** tab in the left sidebar

### Step 2: Add Environment Variables

Click **"Add Environment Variable"** button for each variable:

#### Option A: Minimal Setup (Just Broker - Recommended to Start)

Add only these **REQUIRED** variables:

```bash
BROKER_TYPE=angel
BROKER_API_KEY=your_api_key_here
BROKER_CLIENT_ID=your_client_id_here
BROKER_USERNAME=your_client_id_here
BROKER_PWD=your_trading_pin_here
BROKER_TOKEN=your_totp_secret_here
```

**How to get these values:**
- `BROKER_TYPE`: Use `"angel"` (or `"fyers"` if using Fyers)
- `BROKER_API_KEY`: From your Angel One SmartAPI dashboard
- `BROKER_CLIENT_ID`: Your Angel One client ID (e.g., "BBGV1001")
- `BROKER_USERNAME`: Same as client_id
- `BROKER_PWD`: Your trading PIN (the PIN you use to login to Angel One)
- `BROKER_TOKEN`: TOTP secret from your authenticator app

#### Option B: With Streamlit Config (Optional)

If you want to add the optional Streamlit variables:

```bash
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
```

**What these do:**
- `STREAMLIT_SERVER_HEADLESS=true`: Runs without trying to open a browser (recommended for servers)
- `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false`: Disables Streamlit telemetry (privacy)

**You DON'T need:**
- ❌ `STREAMLIT_SERVER_PORT` - Already set in start command (`--server.port=$PORT`)
- ❌ `STREAMLIT_SERVER_ADDRESS` - Already set in start command (`--server.address=0.0.0.0`)

#### Option C: With Firebase Auth (If Using Firebase)

If you're using Firebase authentication, also add:

```bash
FIREBASE_API_KEY=your_firebase_api_key
FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_STORAGE_BUCKET=your-project.appspot.com
FIREBASE_MESSAGING_SENDER_ID=your_sender_id
FIREBASE_APP_ID=your_app_id
FIREBASE_DATABASE_URL=https://your-project-default-rtdb.firebaseio.com
FIREBASE_ALLOWED_EMAIL=your-email@example.com
```

### Step 3: Save and Redeploy

1. After adding all variables, click **"Save Changes"**
2. Render will automatically trigger a new deployment
3. Wait for deployment to complete (2-5 minutes)

---

## 🔍 Where to Get Each Value

### Broker Credentials (Angel One)

1. **BROKER_API_KEY**:
   - Go to https://smartapi.angelone.in/
   - Login and create an app
   - Copy the API Key

2. **BROKER_CLIENT_ID**:
   - Your Angel One client ID (e.g., "BBGV1001")
   - Found in your Angel One account

3. **BROKER_PWD**:
   - Your trading PIN (the PIN you use for trading)

4. **BROKER_TOKEN**:
   - TOTP secret from your authenticator app
   - Or extract from QR code when setting up 2FA

### Firebase Credentials (If Using)

1. Go to https://console.firebase.google.com/
2. Select your project
3. Go to **Project Settings** → **General**
4. Scroll to **Your apps** section
5. Copy all the configuration values

---

## ✅ Complete Example

Here's what your Render Environment tab should look like (minimum setup):

```
BROKER_TYPE = angel
BROKER_API_KEY = AIzaSyCwXmhHAPwA7SL2u4L8XXyyLlU1Aucb8b4
BROKER_CLIENT_ID = BBGV1001
BROKER_USERNAME = BBGV1001
BROKER_PWD = 1234
BROKER_TOKEN = JBSWY3DPEHPK3PXP
STREAMLIT_SERVER_HEADLESS = true
STREAMLIT_BROWSER_GATHER_USAGE_STATS = false
```

---

## 🚫 What NOT to Add

**Don't add these** - they're already handled:

- ❌ `STREAMLIT_SERVER_PORT` - Port is set via `$PORT` in start command
- ❌ `STREAMLIT_SERVER_ADDRESS` - Address is set to `0.0.0.0` in start command
- ❌ `PYTHON_VERSION` - Render reads from `runtime.txt` automatically

---

## 🔄 After Adding Variables

1. **Save** the environment variables
2. Render will **automatically redeploy** your service
3. Check the **Logs** tab to verify deployment
4. Visit your app URL to test

---

## 🐛 Troubleshooting

### Issue: Variables not working

**Solution**: 
- Make sure you clicked "Save Changes"
- Check variable names are exact (case-sensitive)
- Verify no extra spaces around `=` sign
- Check deployment logs for errors

### Issue: App still not starting

**Solution**:
- Verify start command is: `streamlit run dashboard/ui_frontend.py --server.port=$PORT --server.address=0.0.0.0`
- Check that `$PORT` is used (Render provides this automatically)
- Review logs for specific error messages

### Issue: Broker connection fails

**Solution**:
- Double-check all broker credentials are correct
- Verify API key is active in Angel One dashboard
- Test credentials locally first

---

## 📚 Related Documentation

- **Complete Hosting Guide**: [`HOSTING_GUIDE.md`](HOSTING_GUIDE.md)
- **Quick Reference**: [`QUICK_REFERENCE.md`](QUICK_REFERENCE.md)
- **Streamlit Cloud Setup**: [`STREAMLIT_CLOUD_SETUP.md`](STREAMLIT_CLOUD_SETUP.md)

---

## 💡 Pro Tips

1. **Start Minimal**: Add only broker credentials first, test, then add optional variables
2. **Use Secrets**: Render encrypts environment variables, so they're secure
3. **Test Locally**: Always test with `.streamlit/secrets.toml` locally before deploying
4. **Version Control**: Never commit secrets to Git - use environment variables only

---

**Last Updated**: 2025-01-XX

