# Backtesting Secrets Configuration Fix

## Issue
Backtesting with Angel SmartAPI fails with:
```
FileNotFoundError: Secrets file not found: .streamlit/secrets.toml
```

## Root Cause
The backtesting code (`backtesting/datasource_smartapi.py`) was only looking for `secrets.toml` file, which doesn't exist in production (Railway) deployments.

## Solution

### ✅ Fixed: Environment Variable Support
Updated `backtesting/datasource_smartapi.py` to:
1. **Check for production environment** (Railway, Render, Heroku)
2. **Load from environment variables** if in production
3. **Fall back to secrets.toml** for local development

### Environment Variables for Backtesting

For production (Railway), set these environment variables:

```bash
# Broker credentials (required for SmartAPI backtesting)
BROKER_TYPE=angel
BROKER_API_KEY=your_api_key
BROKER_CLIENT_ID=your_client_id
BROKER_USERNAME=your_username
BROKER_PASSWORD=your_password
BROKER_TOKEN=your_totp_token

# SmartAPI Historical App (optional, for backtesting)
SMARTAPI_HISTORICAL_API_KEY=your_historical_api_key
SMARTAPI_HISTORICAL_API_SECRET=your_historical_api_secret
```

### Local Development

For local development:
1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
2. Fill in your actual credentials
3. **DO NOT commit** `.streamlit/secrets.toml` to git (it's in `.gitignore`)

## Code Changes

The `_load_secrets()` function now:
- Detects production environment automatically
- Loads from environment variables in production
- Falls back to `secrets.toml` for local development
- Provides helpful error messages if neither is available

## Security Note

⚠️ **Never commit `secrets.toml` to git!**

- ✅ `.streamlit/secrets.toml.example` - Template (safe to commit)
- ❌ `.streamlit/secrets.toml` - Actual secrets (in `.gitignore`)

## Status
✅ Fixed - Backtesting now works in production using environment variables

