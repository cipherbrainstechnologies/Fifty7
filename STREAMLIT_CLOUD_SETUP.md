# Streamlit Cloud Deployment - Firebase Configuration

## Setting Up Firebase on Streamlit Cloud

When deploying to Streamlit Cloud, you need to add your Firebase configuration as secrets in the Streamlit Cloud dashboard.

### Step 1: Get Your Firebase Configuration

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project
3. Go to **Project Settings** (gear icon) > **General**
4. Scroll to **Your apps** section
5. Click on your web app (or create one)
6. Copy the Firebase configuration values

### Step 2: Add Secrets to Streamlit Cloud

1. Go to your Streamlit Cloud dashboard: https://share.streamlit.io/
2. Click on your app
3. Click **"⋮" (three dots)** → **"Settings"**
4. Scroll down to **"Secrets"** section
5. Click **"Edit secrets"** or **"Open secrets editor"**

### Step 3: Add Firebase Configuration

**IMPORTANT:** Copy and paste this EXACT format into your Streamlit Cloud secrets editor:

```toml
[firebase]
apiKey = "AIzaSyCwXmhHAPwA7SL2u4L8XXyyLlU1Aucb8b4"
authDomain = "fifty7-2b2eb.firebaseapp.com"
projectId = "fifty7-2b2eb"
storageBucket = "fifty7-2b2eb.firebasestorage.app"
messagingSenderId = "595848198631"
appId = "1:595848198631:web:d4c5a6c8227e4b66526542"
databaseURL = "https://fifty7-2b2eb-default-rtdb.firebaseio.com"
allowedEmail = "lovesinhchauhan1935@gmail.com"
```

**Critical Notes:**
- ✅ Must include `[firebase]` header (with brackets)
- ✅ No spaces around `=` are required, but spaces are fine
- ✅ All values must be in quotes
- ✅ Use your actual values from Firebase Console
- ✅ Make sure `allowedEmail` matches your Firebase user email

### Example Secrets File for Streamlit Cloud

```toml
# Firebase Configuration
[firebase]
apiKey = "AIzaSyC1234567890abcdefghijklmnopqrstuvwxyz"
authDomain = "my-trading-app.firebaseapp.com"
projectId = "my-trading-app"
storageBucket = "my-trading-app.appspot.com"
messagingSenderId = "123456789012"
appId = "1:123456789012:web:abcdef1234567890"
databaseURL = "https://my-trading-app-default-rtdb.firebaseio.com"
allowedEmail = "admin@example.com"

# Broker Configuration (if you also need broker settings)
[broker]
type = "angel"
api_key = "YOUR_BROKER_API_KEY"
client_id = "YOUR_CLIENT_ID"
# ... other broker settings
```

### Step 4: Verify Configuration

1. After saving secrets, Streamlit Cloud will automatically redeploy
2. Check the deployment logs for any errors
3. The app should now use Firebase authentication instead of fallback mode

### Important Notes

⚠️ **Security:**
- Never commit `.streamlit/secrets.toml` to git (it's already in `.gitignore`)
- Streamlit Cloud secrets are encrypted and secure
- The `allowedEmail` field restricts access to only one email address

✅ **Best Practices:**
- Use environment-specific secrets (dev vs production)
- Keep your Firebase API keys secure
- Test authentication after deployment

### Troubleshooting

**Issue: "Firebase configuration not found"**
- ✅ Solution: Make sure you added the `[firebase]` section in Streamlit Cloud secrets
- ✅ Verify all required fields are present (apiKey, authDomain, projectId, etc.)

**Issue: "Authentication not working"**
- ✅ Check that `allowedEmail` matches your Firebase user email
- ✅ Verify Email/Password provider is enabled in Firebase Console
- ✅ Ensure the user account exists in Firebase Authentication

**Issue: "Fallback authentication still showing"**
- ✅ Check Streamlit Cloud secrets are saved correctly
- ✅ Verify the app has been redeployed after adding secrets
- ✅ Check deployment logs for configuration errors

### Quick Reference

**Streamlit Cloud Secrets Location:**
- Dashboard: https://share.streamlit.io/
- Your App → Settings → Secrets

**Firebase Console:**
- Authentication: https://console.firebase.google.com/project/YOUR_PROJECT/authentication
- Project Settings: https://console.firebase.google.com/project/YOUR_PROJECT/settings/general

### Alternative: Use Environment Variables

If you prefer environment variables, you can also set them in Streamlit Cloud:

1. Go to **Settings** → **Environment Variables**
2. Add variables like:
   - `FIREBASE_API_KEY`
   - `FIREBASE_PROJECT_ID`
   - `FIREBASE_ALLOWED_EMAIL`
   - etc.

Then update the code to read from environment variables if secrets are not available.

