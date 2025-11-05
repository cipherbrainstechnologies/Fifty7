# Firebase Authentication Setup Guide

## Quick Setup Steps

### 1. Create Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click "Add project" or select existing project
3. Enter project name and follow setup wizard
4. Enable Google Analytics (optional)

### 2. Enable Authentication

1. In Firebase Console, go to **Authentication** > **Sign-in method**
2. Enable **Email/Password** provider
3. Click "Save"

### 3. Get Firebase Configuration

1. Go to **Project Settings** (gear icon)
2. Scroll down to **Your apps** section
3. Click **Web** icon (`</>`) to add a web app
4. Register app with a nickname (e.g., "NIFTY Trading System")
5. Copy the Firebase configuration object

### 4. Update secrets.toml

Edit `.streamlit/secrets.toml` and add your Firebase configuration:

```toml
[firebase]
apiKey = "AIzaSyC...your_api_key"
authDomain = "your-project-id.firebaseapp.com"
projectId = "your-project-id"
storageBucket = "your-project-id.appspot.com"
messagingSenderId = "123456789012"
appId = "1:123456789012:web:abcdef123456"
databaseURL = "https://your-project-id-default-rtdb.firebaseio.com"  # Optional

# RESTRICTED ACCESS: Only this email can login
# Set to your authorized email address
allowedEmail = "your.email@example.com"
```

**Important**: Set `allowedEmail` to restrict access to only one email address. Only this email will be able to login.

### 5. Configure Email Templates (Optional)

1. Go to **Authentication** > **Templates**
2. Customize email verification and password reset templates
3. Update email sender display name

### 6. Test Authentication

1. Run your Streamlit app: `streamlit run dashboard/ui_frontend.py`
2. You should see the login page
3. Click "Sign Up" to create a test account
4. Check your email for verification link
5. After verification, you can login

## Features

✅ **Email/Password Authentication**
- Secure login with email and password
- **RESTRICTED ACCESS**: Only one static email can login (configured in secrets.toml)
- Signup is disabled - only authorized email can access

✅ **Email Verification (OTP)**
- Automatic email verification on account creation
- Must verify email before login
- Resend verification email option

✅ **Password Reset**
- Forgot password functionality
- Email-based password reset (only for authorized email)

✅ **Session Management**
- Secure token-based sessions
- Automatic token refresh
- Logout functionality

✅ **Access Control**
- Single static email restriction
- Login form pre-fills with authorized email
- Access denied for unauthorized emails

## Security Notes

- Firebase handles all authentication securely
- Passwords are never stored in your app
- Email verification ensures valid users
- Tokens are stored in session state only

## Troubleshooting

### "Firebase configuration not found"
- Check that `[firebase]` section exists in `.streamlit/secrets.toml`
- Verify all required fields are filled

### "Email not verified"
- Check spam folder for verification email
- Use "Forgot Password" to resend verification

### "Invalid email or password"
- Ensure email is verified first
- Check password matches the one used during signup

### Firebase Admin SDK errors
- Service account is optional for basic auth
- Only needed for admin operations

## Next Steps

1. Install dependencies: `pip install -r requirements.txt`
2. Configure Firebase in `.streamlit/secrets.toml`
3. Run the app and test authentication
4. Customize email templates in Firebase Console

