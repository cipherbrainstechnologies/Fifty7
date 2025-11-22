# Hosting Quick Reference

## 🚀 Fastest Deployment Options

### Option 1: Streamlit Cloud (5 minutes)

1. Push code to GitHub
2. Go to https://share.streamlit.io/
3. Click "New app" → Select repo → Deploy
4. Add secrets in Settings → Secrets
5. Done! ✅

**URL Format**: `https://your-app-name.streamlit.app`

---

### Option 2: Render.com (10 minutes)

1. Push code to GitHub
2. Go to https://render.com
3. New → Web Service → Connect repo
4. Configure:
   - **Build**: `pip install -r requirements.txt`
   - **Start**: `streamlit run dashboard/ui_frontend.py --server.port=$PORT --server.address=0.0.0.0`
5. Add environment variables
6. Deploy ✅

**URL Format**: `https://your-service-name.onrender.com`

---

## ⚙️ Required Configuration

### Environment Variables (All Platforms)

```bash
# Broker (Required)
BROKER_TYPE=angel
BROKER_API_KEY=your_key
BROKER_CLIENT_ID=your_id
BROKER_USERNAME=your_id
BROKER_PWD=your_pin
BROKER_TOKEN=your_totp_secret

# Firebase (If using Firebase auth)
FIREBASE_API_KEY=...
FIREBASE_PROJECT_ID=...
FIREBASE_ALLOWED_EMAIL=...

# Streamlit (Optional)
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
```

### Files to Check

- ✅ `runtime.txt` - Python version (3.12.9)
- ✅ `requirements.txt` - All dependencies
- ✅ `config/config.yaml` - Strategy config
- ✅ `Procfile` - For Heroku (optional)
- ✅ `render.yaml` - For Render (optional)
- ✅ `Dockerfile` - For Docker deployments (optional)

---

## 📋 Pre-Deployment Checklist

- [ ] Code committed to Git
- [ ] `runtime.txt` exists
- [ ] `requirements.txt` complete
- [ ] Password hash generated (`python utils/generate_password_hash.py`)
- [ ] Secrets prepared (NOT in Git)
- [ ] Tested locally
- [ ] Broker credentials ready

---

## 🔗 Platform-Specific Guides

- **Streamlit Cloud**: See `HOSTING_GUIDE.md` → Option 1
- **Render.com**: See `HOSTING_GUIDE.md` → Option 2
- **Heroku**: See `HOSTING_GUIDE.md` → Option 3
- **VPS**: See `HOSTING_GUIDE.md` → Option 5

---

## 🐛 Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| App won't start | Check start command uses `$PORT` and `0.0.0.0` |
| Auth fails | Verify secrets/environment variables |
| Broker connection fails | Check API credentials and network access |
| App spins down | Normal for free tier, upgrade for no spin-down |
| Memory errors | Upgrade plan or optimize data loading |

---

## 📞 Need Help?

1. Check `docs/deployment/HOSTING_GUIDE.md` for detailed instructions
2. Review application logs
3. Test locally first
4. Contact platform support

---

**Last Updated**: 2025-01-XX

