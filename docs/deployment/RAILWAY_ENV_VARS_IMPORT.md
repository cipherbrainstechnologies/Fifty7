# Railway Environment Variables - Bulk Import Guide

## Quick Import

Use the file `railway_env_vars_raw.txt` for direct copy-paste into Railway.

## Step-by-Step Instructions

### Option 1: Bulk Import (Recommended)

1. **Open Railway Dashboard**
   - Go to your Railway project
   - Click on your service (e.g., "web" or "Streamlit")

2. **Navigate to Variables**
   - Click on the **"Variables"** tab
   - Click **"Raw Editor"** or **"Bulk Import"** button

3. **Copy and Paste**
   - Open `railway_env_vars_raw.txt` in your editor
   - Copy **ALL** the content (Ctrl+A, Ctrl+C)
   - Paste into Railway's Raw Editor
   - Click **"Save"** or **"Update Variables"**

4. **Verify**
   - All variables should appear in the Variables list
   - Check that values are correct

### Option 2: Individual Import

If bulk import doesn't work, set variables individually:

1. In Railway → Variables → Click **"+ New Variable"**
2. For each variable:
   - **Name**: e.g., `BROKER_API_KEY`
   - **Value**: e.g., `sz5neY7b`
   - Click **"Add"**

## File Format

Railway accepts variables in this format:
```
KEY1=value1
KEY2=value2
KEY3=value3
```

**Important:**
- ✅ No quotes around values
- ✅ No spaces around `=`
- ✅ One variable per line
- ✅ No empty lines (remove comment lines)

## Variables Included

### Broker Configuration
- `BROKER_TYPE`
- `BROKER_API_KEY`
- `BROKER_API_SECRET`
- `BROKER_CLIENT_ID`
- `BROKER_USERNAME`
- `BROKER_PASSWORD`
- `BROKER_TOKEN`

### SmartAPI Applications
- `SMARTAPI_TRADING_API_KEY`
- `SMARTAPI_TRADING_API_SECRET`
- `SMARTAPI_HISTORICAL_API_KEY`
- `SMARTAPI_HISTORICAL_API_SECRET`
- `SMARTAPI_PUBLISHER_API_KEY`
- `SMARTAPI_PUBLISHER_API_SECRET`

### Firebase Configuration
- `FIREBASE_API_KEY`
- `FIREBASE_AUTH_DOMAIN`
- `FIREBASE_PROJECT_ID`
- `FIREBASE_STORAGE_BUCKET`
- `FIREBASE_MESSAGING_SENDER_ID`
- `FIREBASE_APP_ID`
- `FIREBASE_DATABASE_URL`
- `FIREBASE_MEASUREMENT_ID`
- `FIREBASE_ALLOWED_EMAIL`

### Database Configuration
- `DATABASE_URL`
- `PGHOST`
- `PGPORT`
- `PGUSER`
- `PGPASSWORD`
- `PGDATABASE`

## Notes

⚠️ **Security Warning:**
- These files contain sensitive credentials
- **DO NOT** commit `railway_env_vars_raw.txt` to git
- Keep your secrets secure

📝 **After Import:**
- Railway will automatically redeploy your service
- Check logs to verify all variables are loaded correctly
- Test your application to ensure everything works

## Troubleshooting

**Problem:** Variables not appearing after import
- Check that format is correct (KEY=VALUE)
- Ensure no extra spaces or quotes
- Try importing individually

**Problem:** Application still can't find variables
- Verify variables are in the correct service
- Check variable names match exactly (case-sensitive)
- Redeploy service after adding variables

## Files

- `railway_env_vars.txt` - With comments and sections (for reference)
- `railway_env_vars_raw.txt` - Raw format, ready for copy-paste (use this one!)

