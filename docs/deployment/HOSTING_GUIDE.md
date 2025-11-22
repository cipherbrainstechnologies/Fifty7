# Complete Hosting Guide - NIFTY Options Trading System

## 📋 Table of Contents

1. [Hosting Options](#hosting-options)
2. [System Requirements](#system-requirements)
3. [Pre-Deployment Checklist](#pre-deployment-checklist)
4. [Hosting Platforms - Detailed Guides](#hosting-platforms)
5. [Configuration Requirements](#configuration-requirements)
6. [Post-Deployment Setup](#post-deployment-setup)
7. [Troubleshooting](#troubleshooting)

---

## 🎯 Hosting Options

### Recommended Platforms

| Platform | Best For | Free Tier | Difficulty | Notes |
|----------|----------|-----------|------------|-------|
| **Streamlit Cloud** | Quick deployment, Streamlit-native | ✅ Yes | ⭐ Easy | Native Streamlit support, automatic HTTPS |
| **Render.com** | Production-ready, flexible | ✅ Yes (with limitations) | ⭐⭐ Medium | Auto-deploy from GitHub, good free tier |
| **Heroku** | Legacy deployments | ❌ No | ⭐⭐ Medium | Paid only, requires credit card |
| **AWS/GCP/Azure** | Enterprise, high scale | ❌ No | ⭐⭐⭐ Hard | Full control, requires cloud expertise |
| **VPS (DigitalOcean, Linode)** | Full control, cost-effective | ❌ No | ⭐⭐⭐ Hard | Manual setup, server management required |

### Quick Recommendation

- **For Beginners**: Use **Streamlit Cloud** (easiest, free, native support)
- **For Production**: Use **Render.com** (good balance of features and ease)
- **For Enterprise**: Use **AWS/GCP** (full control, scalability)

---

## 💻 System Requirements

### Minimum Requirements

- **Python**: 3.10 or higher (3.12.9 recommended - see `runtime.txt`)
- **RAM**: 512 MB minimum (1 GB recommended)
- **Storage**: 1 GB for application + data
- **Network**: Outbound HTTPS access for broker APIs
- **Ports**: 
  - 8501 (Streamlit default)
  - 8765 (WebSocket server, optional)

### Dependencies

All dependencies are listed in `requirements.txt`. Key packages:
- Streamlit >= 1.28.0
- Firebase Admin SDK (for authentication)
- Broker APIs (SmartAPI, etc.)
- WebSocket support (FastAPI, Uvicorn)

---

## ✅ Pre-Deployment Checklist

Before deploying, ensure:

- [ ] **Code is committed to Git** (GitHub/GitLab/Bitbucket)
- [ ] **Python version specified** (`runtime.txt` exists with Python 3.12.9)
- [ ] **Dependencies listed** (`requirements.txt` is complete)
- [ ] **Secrets prepared** (but NOT committed to Git)
- [ ] **Configuration files ready** (`config/config.yaml` configured)
- [ ] **Password hash generated** (run `python utils/generate_password_hash.py`)
- [ ] **Broker credentials obtained** (API keys, tokens, etc.)
- [ ] **Firebase project created** (if using Firebase auth)
- [ ] **Tested locally** (app runs on `localhost:8501`)

---

## 🚀 Hosting Platforms - Detailed Guides

## Option 1: Streamlit Cloud (Recommended for Beginners)

### Why Streamlit Cloud?

- ✅ **Free tier available**
- ✅ **Native Streamlit support** (no configuration needed)
- ✅ **Automatic HTTPS** (SSL certificates)
- ✅ **GitHub integration** (auto-deploy on push)
- ✅ **Zero server management**

### Prerequisites

1. GitHub account
2. Streamlit Cloud account (free at https://share.streamlit.io/)
3. Repository pushed to GitHub

### Step-by-Step Deployment

#### Step 1: Prepare Your Repository

```bash
# Ensure all files are committed
git add .
git commit -m "Ready for Streamlit Cloud deployment"
git push origin main
```

#### Step 2: Create Streamlit Cloud Account

1. Go to https://share.streamlit.io/
2. Sign in with GitHub
3. Authorize Streamlit Cloud to access your repositories

#### Step 3: Deploy Your App

1. Click **"New app"** button
2. Select your repository: `Fifty7` (or your repo name)
3. Select branch: `main`
4. **Main file path**: `dashboard/ui_frontend.py`
5. Click **"Deploy"**

#### Step 4: Configure Secrets

After deployment, configure secrets:

1. Go to your app dashboard
2. Click **"⋮" (three dots)** → **"Settings"**
3. Scroll to **"Secrets"** section
4. Click **"Edit secrets"** or **"Open secrets editor"**

Add your secrets in TOML format:

```toml
# Firebase Configuration (if using Firebase auth)
[firebase]
apiKey = "YOUR_FIREBASE_API_KEY"
authDomain = "YOUR_PROJECT.firebaseapp.com"
projectId = "YOUR_PROJECT_ID"
storageBucket = "YOUR_PROJECT.appspot.com"
messagingSenderId = "YOUR_SENDER_ID"
appId = "YOUR_APP_ID"
databaseURL = "https://YOUR_PROJECT-default-rtdb.firebaseio.com"
allowedEmail = "your-email@example.com"

# Broker Configuration
[broker]
type = "angel"
api_key = "YOUR_API_KEY"
client_id = "YOUR_CLIENT_ID"
username = "YOUR_CLIENT_ID"
pwd = "YOUR_TRADING_PIN"
token = "YOUR_TOTP_SECRET"

# Streamlit Credentials (fallback auth)
[credentials]
names = ["Your Name"]
usernames = ["your_username"]
passwords = ["$2b$12$YOUR_HASHED_PASSWORD"]

[cookie]
name = "nifty_auth"
key = "YOUR_RANDOM_COOKIE_KEY"
expiry_days = 30
```

**Important Notes:**
- Replace all placeholder values with your actual credentials
- Never commit secrets to Git
- Use Firebase auth for production (more secure)

#### Step 5: Verify Deployment

1. Wait for deployment to complete (2-5 minutes)
2. Visit your app URL: `https://your-app-name.streamlit.app`
3. Test authentication
4. Check logs in Streamlit Cloud dashboard

### Streamlit Cloud Configuration

**App URL Format:**
```
https://[app-name]-[username].streamlit.app
```

**Auto-Deploy:**
- Automatically redeploys on every push to main branch
- Manual redeploy available in dashboard

**Limitations (Free Tier):**
- Apps sleep after 1 hour of inactivity
- 1 GB memory limit
- Public apps only (private apps require Team plan)

---

## Option 2: Render.com (Recommended for Production)

### Why Render.com?

- ✅ **Free tier available** (with limitations)
- ✅ **Auto-deploy from GitHub**
- ✅ **Custom domains** (paid plans)
- ✅ **Better performance** than free Streamlit Cloud
- ✅ **More control** over configuration

### Prerequisites

1. GitHub account
2. Render.com account (free at https://render.com)
3. Repository pushed to GitHub

### Step-by-Step Deployment

#### Step 1: Prepare Repository

```bash
# Ensure all files are committed
git add .
git commit -m "Ready for Render deployment"
git push origin main
```

#### Step 2: Create Render Account

1. Go to https://render.com
2. Sign up with GitHub
3. Authorize Render to access your repositories

#### Step 3: Create Web Service

1. Click **"New +"** → **"Web Service"**
2. Connect your GitHub repository: `Fifty7`
3. Click **"Connect"**

#### Step 4: Configure Service

**Basic Settings:**
- **Name**: `nifty-options-trader` (or your preferred name)
- **Region**: Choose closest to your location (Oregon, Frankfurt, Singapore, etc.)
- **Branch**: `main`
- **Runtime**: `Python 3`
- **Instance Type**: `Free` (or upgrade for better performance)

**Build & Deploy Settings:**
- **Build Command**: 
  ```bash
  pip install -r requirements.txt
  ```
- **Start Command**: 
  ```bash
  streamlit run dashboard/ui_frontend.py --server.port=$PORT --server.address=0.0.0.0
  ```

**Important**: Render provides `$PORT` environment variable automatically.

#### Step 5: Configure Environment Variables

Go to **"Environment"** tab and add:

**Required Variables:**

```bash
# Python Version (optional, Render auto-detects)
PYTHON_VERSION=3.12.9

# Streamlit Configuration
STREAMLIT_SERVER_PORT=$PORT
STREAMLIT_SERVER_ADDRESS=0.0.0.0
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
```

**Secrets (Add as Environment Variables):**

For Firebase:
```bash
FIREBASE_API_KEY=your_api_key
FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
FIREBASE_PROJECT_ID=your_project_id
FIREBASE_STORAGE_BUCKET=your_project.appspot.com
FIREBASE_MESSAGING_SENDER_ID=your_sender_id
FIREBASE_APP_ID=your_app_id
FIREBASE_DATABASE_URL=https://your_project-default-rtdb.firebaseio.com
FIREBASE_ALLOWED_EMAIL=your-email@example.com
```

For Broker:
```bash
BROKER_TYPE=angel
BROKER_API_KEY=your_api_key
BROKER_CLIENT_ID=your_client_id
BROKER_USERNAME=your_client_id
BROKER_PWD=your_trading_pin
BROKER_TOKEN=your_totp_secret
```

For Streamlit Auth (fallback):
```bash
STREAMLIT_CREDENTIALS_NAMES=["Your Name"]
STREAMLIT_CREDENTIALS_USERNAMES=["your_username"]
STREAMLIT_CREDENTIALS_PASSWORDS=["$2b$12$your_hashed_password"]
STREAMLIT_COOKIE_NAME=nifty_auth
STREAMLIT_COOKIE_KEY=your_random_cookie_key
STREAMLIT_COOKIE_EXPIRY_DAYS=30
```

**Note**: For array values like `STREAMLIT_CREDENTIALS_NAMES`, you may need to use Render's **"Secret Files"** feature instead, or modify the code to read from environment variables differently.

#### Step 6: Deploy

1. Click **"Create Web Service"**
2. Wait for build to complete (5-10 minutes first time)
3. Your app will be available at: `https://your-service-name.onrender.com`

#### Step 7: Configure Auto-Deploy

- **Auto-Deploy**: Enabled by default
- Any push to `main` branch triggers automatic redeployment
- Manual deploy available in dashboard

### Render.com Configuration Files

You can also create a `render.yaml` file in your repository root:

```yaml
services:
  - type: web
    name: nifty-options-trader
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: streamlit run dashboard/ui_frontend.py --server.port=$PORT --server.address=0.0.0.0
    envVars:
      - key: PYTHON_VERSION
        value: 3.12.9
      - key: STREAMLIT_SERVER_HEADLESS
        value: true
      - key: STREAMLIT_BROWSER_GATHER_USAGE_STATS
        value: false
```

### Render.com Limitations (Free Tier)

- **Spins down** after 15 minutes of inactivity
- **512 MB RAM** limit
- **Limited CPU** resources
- **No custom domains** (free tier)
- **Cold starts** can take 30-60 seconds

**Upgrade Options:**
- **Starter Plan**: $7/month - No spin-down, 512 MB RAM
- **Standard Plan**: $25/month - Better performance, custom domains

---

## Option 3: Heroku

### Prerequisites

1. Heroku account (paid, no free tier)
2. Heroku CLI installed
3. GitHub repository

### Step-by-Step Deployment

#### Step 1: Create Procfile

Create `Procfile` in repository root:

```
web: streamlit run dashboard/ui_frontend.py --server.port=$PORT --server.address=0.0.0.0
```

#### Step 2: Deploy via CLI

```bash
# Login to Heroku
heroku login

# Create app
heroku create your-app-name

# Set environment variables
heroku config:set STREAMLIT_SERVER_HEADLESS=true
heroku config:set BROKER_TYPE=angel
# ... add all other environment variables

# Deploy
git push heroku main
```

#### Step 3: Configure Environment Variables

Use Heroku dashboard or CLI:

```bash
heroku config:set KEY=value
```

---

## Option 4: AWS/GCP/Azure (Enterprise)

### AWS Elastic Beanstalk

1. Create Python environment
2. Upload application
3. Configure environment variables
4. Deploy

### Google Cloud Run

1. Create Dockerfile (see below)
2. Build container image
3. Deploy to Cloud Run
4. Configure environment variables

### Azure App Service

1. Create Python web app
2. Configure deployment from GitHub
3. Set application settings (environment variables)
4. Deploy

**Note**: These platforms require cloud expertise and are beyond the scope of this guide. Refer to platform-specific documentation.

---

## Option 5: VPS (DigitalOcean, Linode, etc.)

### Prerequisites

1. VPS with Ubuntu/Debian
2. SSH access
3. Domain name (optional, for custom domain)

### Step-by-Step Setup

#### Step 1: Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.12
sudo apt install python3.12 python3.12-venv python3-pip -y

# Install Nginx (reverse proxy)
sudo apt install nginx -y
```

#### Step 2: Application Setup

```bash
# Clone repository
git clone https://github.com/yourusername/Fifty7.git
cd Fifty7

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### Step 3: Create Systemd Service

Create `/etc/systemd/system/nifty-trader.service`:

```ini
[Unit]
Description=NIFTY Options Trading System
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/Fifty7
Environment="PATH=/home/your-username/Fifty7/venv/bin"
ExecStart=/home/your-username/Fifty7/venv/bin/streamlit run dashboard/ui_frontend.py --server.port=8501 --server.address=0.0.0.0
Restart=always

[Install]
WantedBy=multi-user.target
```

#### Step 4: Configure Nginx

Create `/etc/nginx/sites-available/nifty-trader`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/nifty-trader /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### Step 5: Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable nifty-trader
sudo systemctl start nifty-trader
```

#### Step 6: SSL with Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

---

## ⚙️ Configuration Requirements

### 1. Environment Variables

All sensitive configuration should be set as environment variables or secrets:

#### Firebase Configuration (if using Firebase auth)

```bash
FIREBASE_API_KEY=...
FIREBASE_AUTH_DOMAIN=...
FIREBASE_PROJECT_ID=...
FIREBASE_STORAGE_BUCKET=...
FIREBASE_MESSAGING_SENDER_ID=...
FIREBASE_APP_ID=...
FIREBASE_DATABASE_URL=...
FIREBASE_ALLOWED_EMAIL=...
```

#### Broker Configuration

```bash
BROKER_TYPE=angel  # or "fyers"
BROKER_API_KEY=...
BROKER_CLIENT_ID=...
BROKER_USERNAME=...
BROKER_PWD=...  # Trading PIN
BROKER_TOKEN=...  # TOTP secret
```

#### Streamlit Configuration

```bash
STREAMLIT_SERVER_PORT=$PORT  # Use $PORT on cloud platforms
STREAMLIT_SERVER_ADDRESS=0.0.0.0
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
```

### 2. Configuration Files

#### `config/config.yaml`

This file should be committed to Git (no secrets):

```yaml
lot_size: 75
strategy:
  type: inside_bar
  sl: 30
  rr: 1.8
  # ... other non-sensitive config
```

#### `.streamlit/secrets.toml` (Local Only)

For local development, create `.streamlit/secrets.toml` (git-ignored):

```toml
[firebase]
# ... Firebase config

[broker]
# ... Broker config

[credentials]
# ... Auth config
```

**Never commit this file to Git!**

### 3. Required Directories

Ensure these directories exist (created automatically by `main.py`):

```
data/
  historical/
  state/
logs/
.streamlit/
```

### 4. Python Version

Specify in `runtime.txt`:
```
python-3.12.9
```

---

## 🔧 Post-Deployment Setup

### 1. Verify Deployment

- [ ] App loads without errors
- [ ] Authentication works
- [ ] Broker connection successful
- [ ] Dashboard displays correctly
- [ ] No errors in logs

### 2. Test Functionality

- [ ] Login/authentication
- [ ] Broker API connection
- [ ] Market data fetching
- [ ] Trade execution (in paper trading mode first!)
- [ ] Trade logging
- [ ] Dashboard features

### 3. Monitor Logs

Check application logs regularly:
- Streamlit Cloud: Dashboard → Logs
- Render: Dashboard → Logs
- VPS: `journalctl -u nifty-trader -f`

### 4. Set Up Monitoring

- **Error Alerts**: Configure email/SMS alerts for errors
- **Uptime Monitoring**: Use services like UptimeRobot
- **Performance Monitoring**: Monitor response times, memory usage

### 5. Backup Strategy

- **Trade Logs**: Export `logs/trades.csv` regularly
- **Configuration**: Version control all config changes
- **State Snapshots**: Backup `data/state/` directory

---

## 🐛 Troubleshooting

### Common Issues

#### Issue 1: App Won't Start

**Symptoms**: Build succeeds but app doesn't load

**Solutions**:
1. Check start command uses `$PORT` and `0.0.0.0`
2. Verify Python version matches `runtime.txt`
3. Check logs for specific errors
4. Ensure all dependencies installed

#### Issue 2: Authentication Not Working

**Symptoms**: Can't login, authentication errors

**Solutions**:
1. Verify secrets/environment variables are set correctly
2. Check password hash is correct (regenerate if needed)
3. Verify Firebase configuration (if using Firebase)
4. Check cookie key is set

#### Issue 3: Broker Connection Fails

**Symptoms**: Can't connect to broker API

**Solutions**:
1. Verify API credentials are correct
2. Check broker API status
3. Verify network access (outbound HTTPS)
4. Check rate limits
5. Test with broker's sandbox first

#### Issue 4: App Spins Down (Render/Free Tier)

**Symptoms**: App takes 30-60 seconds to load after inactivity

**Solutions**:
1. This is normal for free tier
2. Upgrade to paid plan for no spin-down
3. Use uptime monitoring service to ping app every 5 minutes

#### Issue 5: Memory Errors

**Symptoms**: App crashes, out of memory errors

**Solutions**:
1. Upgrade to plan with more RAM
2. Optimize data loading (reduce data window sizes)
3. Implement caching
4. Reduce concurrent operations

#### Issue 6: Port Binding Errors

**Symptoms**: "Address already in use" or port errors

**Solutions**:
1. Ensure using `$PORT` environment variable (cloud platforms)
2. Use `0.0.0.0` as address (not `127.0.0.1`)
3. Check no other service using the port

### Getting Help

1. **Check Logs**: Always check application logs first
2. **Review Documentation**: See `docs/` directory
3. **Test Locally**: Reproduce issue locally if possible
4. **Platform Support**: Contact platform support (Streamlit Cloud, Render, etc.)

---

## 📚 Additional Resources

### Documentation

- **Architecture**: `memory-bank/architecture.md`
- **Deployment**: `docs/deployment/DEPLOYMENT.md`
- **Streamlit Cloud**: `docs/deployment/STREAMLIT_CLOUD_SETUP.md`
- **Local Setup**: `docs/setup/LOCAL_RUN.md`

### External Resources

- **Streamlit Cloud Docs**: https://docs.streamlit.io/streamlit-community-cloud
- **Render Docs**: https://render.com/docs
- **Heroku Docs**: https://devcenter.heroku.com/
- **Python Deployment**: https://docs.python.org/3/deploying/

---

## ✅ Deployment Checklist Summary

Before deploying, ensure:

- [ ] Code committed to Git
- [ ] `runtime.txt` specifies Python version
- [ ] `requirements.txt` is complete
- [ ] Secrets prepared (not in Git)
- [ ] Password hash generated
- [ ] Broker credentials ready
- [ ] Firebase project created (if using)
- [ ] Tested locally
- [ ] Configuration files ready
- [ ] Documentation reviewed

---

## 🎉 Success!

Once deployed, your NIFTY Options Trading System will be accessible at:

- **Streamlit Cloud**: `https://your-app-name.streamlit.app`
- **Render**: `https://your-service-name.onrender.com`
- **Heroku**: `https://your-app-name.herokuapp.com`
- **VPS**: `https://your-domain.com`

**Remember**: Always test in paper trading mode before live trading!

---

**Last Updated**: 2025-01-XX
**Maintained By**: Project Team

