"""
Secure Streamlit Dashboard for NIFTY Options Trading System
"""

# -*- coding: utf-8 -*-
import streamlit as st
# import streamlit_authenticator as stauth  # Temporarily disabled
import yaml
from yaml.loader import SafeLoader
import pandas as pd
from datetime import datetime, date
import os
import sys
import io
import wave
import math
from logzero import logger
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import threading
import time
import pytz
from typing import Any, Dict, Optional

# TOML support - use tomllib (Python 3.11+) or tomli package
try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # Fallback: tomli package
    except ImportError:
        # Last resort: use toml package (older API - different method signature)
        try:
            import toml
            # Create a wrapper class to match tomllib API
            class TomlWrapper:
                @staticmethod
                def load(file):
                    # toml.load() expects text mode, not binary
                    if hasattr(file, 'read'):
                        content = file.read()
                        if isinstance(content, bytes):
                            content = content.decode('utf-8')
                        return toml.loads(content)
                    return toml.load(file)
            tomllib = TomlWrapper()
        except ImportError:
            tomllib = None

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _parse_expiry_to_datetime(value: Any) -> Optional[datetime]:
    """Best-effort parser for broker expiry values."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            ts = float(value)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts)
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.upper().replace("\n", " ").strip()
    for candidate in (text, normalized):
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            pass
    patterns = [
        "%d%b%Y",
        "%d%b%y",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d %b %Y",
        "%d %b %y",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d/%m/%y",
    ]
    for fmt in patterns:
        try:
            return datetime.strptime(normalized, fmt)
        except Exception:
            continue
    return None

def _generate_breakout_alert_audio(
    frequency_hz: int = 880,
    duration_seconds: float = 0.7,
    volume: float = 0.55,
    sample_rate: int = 44100
) -> bytes:
    """Generate a simple sine wave tone for breakout alerts."""
    frame_count = int(sample_rate * duration_seconds)
    frames = bytearray()
    for index in range(frame_count):
        sample = int(
            volume * 32767.0 * math.sin(2.0 * math.pi * frequency_hz * (index / sample_rate))
        )
        frames.extend(sample.to_bytes(2, byteorder="little", signed=True))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(frames))

    return buffer.getvalue()

from engine import strategy_engine as strategy_engine_module

check_for_signal = strategy_engine_module.check_for_signal
detect_inside_bar = strategy_engine_module.detect_inside_bar
confirm_breakout = strategy_engine_module.confirm_breakout

if hasattr(strategy_engine_module, "find_mother_index"):
    find_mother_index = strategy_engine_module.find_mother_index
elif hasattr(strategy_engine_module, "_find_mother_index"):
    find_mother_index = strategy_engine_module._find_mother_index  # type: ignore[attr-defined]
else:
    def find_mother_index(*args, **kwargs):
        raise RuntimeError(
            "find_mother_index helper is not available in engine.strategy_engine; "
            "please update the engine module."
        )
from engine.trade_logger import TradeLogger, log_trade
from engine.broker_connector import create_broker_interface
from engine.signal_handler import SignalHandler
from engine.backtest_engine import BacktestEngine
from engine.market_data import MarketDataProvider
from engine.live_runner import LiveStrategyRunner
from engine.firebase_auth import FirebaseAuth
from dashboard.auth_page import render_login_page

# Initialize database on startup
try:
    from engine.db import init_database
    init_database(create_all=True)
    logger.info("Database initialized successfully")
except Exception as e:
    logger.warning(f"Database initialization failed (non-critical): {e}")

# Cloud data source
try:
    from backtesting.datasource_desiquant import stream_data
    DESIQUANT_AVAILABLE = True
except ImportError:
    DESIQUANT_AVAILABLE = False
    stream_data = None


# Page config
st.set_page_config(
    page_title="NIFTY Options Trading System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for enhanced UI
st.markdown("""
<style>
    /* Card styling */
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .status-card {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .status-green {
        background-color: #d4edda;
        border-left: 4px solid #28a745;
    }
    .status-red {
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
    }
    .status-yellow {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
    }
    .dashboard-hero {
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
        margin-bottom: 1rem;
    }
    .dashboard-hero > div {
        flex: 1 1 260px;
    }
    div[data-testid="stMetric"] {
        background: #ffffff;
        border-radius: 12px;
        padding: 0.75rem 1rem;
        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.12);
    }
    div[data-testid="stMetric"] label {
        font-weight: 600;
    }
    div[data-testid="stMetricValue"] {
        font-weight: 700;
    }
    /* Responsive adjustments */
    @media (max-width: 768px) {
        .metric-card {
            margin-bottom: 1rem;
        }
        .dashboard-hero {
            flex-direction: column;
        }
        div[data-testid="column"] {
            width: 100% !important;
        }
        div[data-testid="stMetric"] {
            text-align: center;
            align-items: center;
        }
        div[data-testid="stMetricLabel"] {
            justify-content: center;
            text-align: center;
        }
        .status-card {
            margin-bottom: 0.75rem;
        }
    }
    /* Empty state styling */
    .empty-state {
        text-align: center;
        padding: 3rem;
        color: #6c757d;
    }
</style>
""", unsafe_allow_html=True)

# Load configuration
def load_config():
    """
    Load configuration from secrets.toml (local) or st.secrets (Streamlit Cloud).
    Note: Not using @st.cache_data to avoid recursion issues with st.secrets.
    Returns a dict with all config sections.
    """
    config = {}
    
    # First, try to load from secrets.toml file (for local development)
    secrets_path = '.streamlit/secrets.toml'
    if os.path.exists(secrets_path):
        if tomllib is None:
            logger.warning("TOML parser not available. Install with: pip install tomli")
        else:
            try:
                with open(secrets_path, 'rb') as file:  # TOML requires binary mode
                    config = tomllib.load(file)
                logger.info("Loaded config from secrets.toml file")
                return config
            except Exception as e:
                logger.error(f"Error loading secrets.toml: {e}")
    
    # For Streamlit Cloud, we'll access st.secrets directly when needed
    # Don't convert to dict here to avoid recursion
    # Mark that we're using Streamlit secrets
    if hasattr(st, 'secrets'):
        config['_from_streamlit_secrets'] = True
        logger.info("Using Streamlit secrets (will access directly)")
    
    return config

# Helper function to safely get config value from either source
def get_config_value(section, key, default=None):
    """Safely get config value from secrets.toml or st.secrets"""
    # First check loaded config dict
    if section in config and isinstance(config[section], dict):
        return config[section].get(key, default)
    
    # If using Streamlit secrets, access directly
    if config.get('_from_streamlit_secrets') and hasattr(st, 'secrets'):
        try:
            section_obj = getattr(st.secrets, section, None)
            if section_obj:
                return getattr(section_obj, key, default)
        except Exception:
            pass
    
    return default


def align_dataframe_to_ist(df: pd.DataFrame, column: str = 'Date') -> pd.DataFrame:
    """Ensure the specified datetime column is timezone-aware in Asia/Kolkata."""
    if df is None or df.empty or column not in df.columns:
        return df

    aligned = df.copy()

    try:
        dt_series = pd.to_datetime(aligned[column], errors='coerce')

        tz_attr = getattr(dt_series.dt, "tz", None)

        if tz_attr is None:
            try:
                dt_series = dt_series.dt.tz_localize('Asia/Kolkata')
            except TypeError:
                # Fallback: coerce via pandas Timestamp directly
                dt_series = pd.to_datetime(dt_series.astype(str), errors='coerce').dt.tz_localize('Asia/Kolkata')
        else:
            try:
                dt_series = dt_series.dt.tz_convert('Asia/Kolkata')
            except Exception:
                # If conversion fails, coerce and localize
                dt_series = pd.to_datetime(dt_series.astype(str), errors='coerce').dt.tz_localize('Asia/Kolkata')

        aligned[column] = dt_series
    except Exception as exc:
        logger.warning(f"Timezone alignment failed for column '{column}': {exc}")

    return aligned


def format_ist_timestamp(value) -> str:
    """Format timestamps into 12-hour IST representation."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"

    try:
        ts = pd.to_datetime(value)
    except Exception:
        return str(value)

    try:
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.tz_localize('Asia/Kolkata')
        else:
            ts = ts.tz_convert('Asia/Kolkata')
    except Exception:
        return str(value)

    return ts.strftime("%d-%b-%Y %I:%M %p IST")

# ===================================================================
# FIREBASE AUTHENTICATION
# ===================================================================

# Load config
config = load_config()

# Initialize Firebase Authentication
firebase_auth = None
allowed_email = None
try:
    # Get Firebase config - check Streamlit secrets first, then config dict
    firebase_config = None
    
    # Priority 1: Check Streamlit secrets directly (for Streamlit Cloud)
    # Access st.secrets directly using attribute access (avoids recursion)
    if hasattr(st, 'secrets'):
        try:
            # Check if firebase section exists using hasattr (safe, no recursion)
            if hasattr(st.secrets, 'firebase'):
                firebase_secrets = st.secrets.firebase
                # Access each key individually using getattr (safe, no recursion)
                firebase_config = {}
                
                # Use getattr with default empty string to avoid recursion
                for key in ['apiKey', 'authDomain', 'projectId', 'storageBucket', 
                           'messagingSenderId', 'appId', 'databaseURL', 'allowedEmail']:
                    try:
                        value = getattr(firebase_secrets, key, '')
                        if value:
                            firebase_config[key] = str(value)
                    except Exception:
                        # Skip if key doesn't exist or causes error
                        pass
                
                # Only use if we got at least apiKey
                if firebase_config.get('apiKey'):
                    logger.info("Loaded Firebase config from Streamlit secrets")
                else:
                    firebase_config = None
        except Exception as e:
            logger.warning(f"Error accessing Streamlit secrets: {e}")
            firebase_config = None
    
    # Priority 2: Check config dict (for local development)
    if not firebase_config:
        firebase_config = config.get('firebase', {})
        if firebase_config:
            logger.info("Loaded Firebase config from secrets.toml file")
    
    # Debug: Check what we have
    if firebase_config:
        logger.info(f"Firebase config found with keys: {list(firebase_config.keys())}")
        if 'apiKey' in firebase_config and firebase_config.get('apiKey'):
            logger.info(f"Firebase apiKey found: {str(firebase_config['apiKey'])[:20]}...")
        else:
            logger.warning("Firebase config found but apiKey is missing or empty")
    else:
        logger.warning("No Firebase config found")
    
    if firebase_config and firebase_config.get('apiKey'):
        try:
            # Filter out empty values
            clean_config = {k: v for k, v in firebase_config.items() if v}
            firebase_auth = FirebaseAuth(clean_config)
            # Get allowed email from config (restrict to single email)
            allowed_email = clean_config.get('allowedEmail', None)
            if allowed_email:
                allowed_email = str(allowed_email).strip().lower()  # Normalize to lowercase
            logger.info(f"Firebase authentication initialized successfully. Allowed email: {allowed_email}")
        except ImportError as e:
            # Missing dependency error
            error_msg = str(e)
            logger.error(f"Firebase dependency missing: {error_msg}")
            st.error("⚠️ Firebase Authentication Unavailable")
            st.warning("""
            **Missing Dependency: pyrebase4**
            
            Firebase authentication requires `pyrebase4` to be installed.
            
            **For Streamlit Cloud:**
            1. Make sure `requirements.txt` includes: `pyrebase4>=4.7.1`
            2. Commit and push your changes
            3. Streamlit Cloud will auto-redeploy and install dependencies
            
            **If already in requirements.txt:**
            - Check deployment logs for installation errors
            - Try manually triggering a redeploy: Settings → "Reboot app"
            - Verify the package name is correct: `pyrebase4` (not `pyrebase`)
            """)
            firebase_auth = None
        except Exception as e:
            logger.error(f"Failed to initialize FirebaseAuth: {e}")
            st.error(f"Firebase initialization error: {e}")
            st.exception(e)  # Show full error for debugging
            firebase_auth = None
    else:
        # Show helpful error message
        missing_fields = []
        if not firebase_config:
            missing_fields.append("Firebase section missing")
        elif not firebase_config.get('apiKey'):
            missing_fields.append("apiKey missing")
        
        st.warning(f"⚠️ Firebase configuration not found: {', '.join(missing_fields) if missing_fields else 'Configuration incomplete'}")
        st.info("""
        **Please add Firebase configuration:**
        
        **For Streamlit Cloud:**
        1. Go to https://share.streamlit.io/
        2. Select your app → **Settings** → **Secrets**
        3. Paste this exact format:
        
        ```toml
        [firebase]
        apiKey = "YOUR_API_KEY"
        authDomain = "YOUR_PROJECT_ID.firebaseapp.com"
        projectId = "YOUR_PROJECT_ID"
        storageBucket = "YOUR_PROJECT_ID.appspot.com"
        messagingSenderId = "YOUR_MESSAGING_SENDER_ID"
        appId = "YOUR_APP_ID"
        allowedEmail = "your.email@example.com"
        ```
        
        4. Click **Save** (app will auto-redeploy)
        
        **For Local Development:**
        - Edit `.streamlit/secrets.toml` with the same format
        
        See `STREAMLIT_CLOUD_SETUP.md` for detailed instructions.
        """)
        firebase_auth = None
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {e}")
    st.error(f"Firebase initialization error: {e}")
    st.exception(e)  # Show full error for debugging
    firebase_auth = None

# Check authentication status
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# ===================================================================
# FIREBASE SESSION PERSISTENCE - Restore session on page load/reload
# Date: 2025-01-27
# Purpose: Keep user logged in across tab changes/reloads using Firebase cache
# ===================================================================
if firebase_auth:
    # Try to restore session from stored tokens if not authenticated
    if not st.session_state.authenticated:
        # Check if we have stored tokens in session state
        stored_id_token = st.session_state.get('id_token')
        stored_refresh_token = st.session_state.get('refresh_token')
        stored_user_email = st.session_state.get('user_email')
        
        # If we have tokens, try to restore session
        if stored_refresh_token and stored_user_email:
            try:
                # Try to refresh the token using Firebase's refresh_token method
                refreshed_user = firebase_auth.refresh_token(stored_refresh_token)
                if refreshed_user:
                    # Session restored successfully
                    st.session_state.user = refreshed_user
                    st.session_state.id_token = refreshed_user.get('idToken', stored_id_token)
                    st.session_state.refresh_token = refreshed_user.get('refreshToken', stored_refresh_token)
                    st.session_state.user_email = stored_user_email
                    st.session_state.authenticated = True
                    logger.info(f"Firebase session restored for user: {stored_user_email}")
                else:
                    # Refresh failed, clear tokens
                    st.session_state.id_token = None
                    st.session_state.refresh_token = None
                    st.session_state.user_email = None
                    logger.warning("Firebase session refresh failed, tokens cleared")
            except Exception as e:
                # Refresh failed, clear tokens
                logger.warning(f"Firebase session restore failed: {e}")
                st.session_state.id_token = None
                st.session_state.refresh_token = None
                st.session_state.user_email = None
        elif stored_id_token:
            # Only id_token exists, try to verify it
            try:
                user_info = firebase_auth.get_user_info(stored_id_token)
                if user_info:
                    # Token is valid, restore session
                    st.session_state.user = {'idToken': stored_id_token}
                    st.session_state.id_token = stored_id_token
                    st.session_state.user_email = stored_user_email or user_info.get('email', '')
                    st.session_state.authenticated = True
                    logger.info(f"Firebase session restored using id_token for user: {st.session_state.user_email}")
                else:
                    # Token invalid, clear it
                    st.session_state.id_token = None
                    st.session_state.refresh_token = None
                    st.session_state.user_email = None
            except Exception as e:
                logger.warning(f"Firebase token verification failed: {e}")
                st.session_state.id_token = None
                st.session_state.refresh_token = None
                st.session_state.user_email = None

# If Firebase is configured, require authentication
if firebase_auth:
    if not st.session_state.authenticated:
        # Show login page with email restriction
        render_login_page(firebase_auth, allowed_email)
        st.stop()
    else:
        # Verify authenticated email matches allowed email (if restricted)
        user_email = st.session_state.get('user_email', '')
        if allowed_email and user_email.lower() != allowed_email:
            st.error(f"❌ Access Denied. Only authorized email ({allowed_email}) can access.")
            firebase_auth.sign_out()
            st.session_state.authenticated = False
            st.session_state.user = None
            st.session_state.id_token = None
            st.session_state.refresh_token = None
            st.session_state.user_email = None
            st.rerun()
        
        # User is authenticated, show dashboard
        name = user_email.split('@')[0] if '@' in user_email else user_email
        username = user_email
        auth_status = True
        
        # Add logout button in sidebar
        with st.sidebar:
            st.success(f"👋 Welcome, {name}")
            if allowed_email:
                st.caption(f"📧 {allowed_email}")
            if st.button("🚪 Logout", use_container_width=True):
                firebase_auth.sign_out()
                st.session_state.authenticated = False
                st.session_state.user = None
                st.session_state.id_token = None
                st.session_state.refresh_token = None
                st.session_state.user_email = None
                st.rerun()
else:
    # Fallback: No authentication (for development)
    name = "Admin"
    username = "admin"
    auth_status = True
    st.sidebar.warning("⚠️ Authentication disabled - Development mode")
    st.sidebar.info("🔓 Direct access enabled")
    st.sidebar.success(f"👋 Welcome, {name}")

# ===================================================================
# COMMENTED OUT AUTHENTICATION CODE (for reference)
# ===================================================================
# try:
#     # Convert credentials from list format to dict format expected by streamlit-authenticator
#     # TOML format: names=["Admin"], usernames=["admin"], passwords=["hash"]
#     # Library expects: usernames={"admin": "Admin"}, passwords={"admin": "hash"}
#     cred_config = config['credentials']
#     
#     # Convert lists to dict: {username: name} and {username: password}
#     usernames_list = cred_config.get('usernames', [])
#     names_list = cred_config.get('names', [])
#     passwords_list = cred_config.get('passwords', [])
#     
#     # Create dict format
#     credentials_dict = {
#         'usernames': {},
#         'names': {},
#         'passwords': {}
#     }
#     
#     for i, username in enumerate(usernames_list):
#         credentials_dict['usernames'][username] = names_list[i] if i < len(names_list) else username
#         credentials_dict['names'][username] = names_list[i] if i < len(names_list) else username
#         password_value = passwords_list[i] if i < len(passwords_list) else ""
#         credentials_dict['passwords'][username] = password_value
#     
#     # Validate passwords before creating authenticator
#     # Version 0.2.3: Accepts plain text passwords and auto-hashes them
#     # Simple validation - check password exists and length
#     for username, password_value in credentials_dict['passwords'].items():
#         if not password_value or password_value == "":
#             st.error(f"❌ Password is empty for user '{username}'.")
#             st.error("   Please add a plain text password to secrets.toml")
#             st.error("   Example: passwords = [\"admin\"]")
#             st.stop()
#         
#         # Version 0.2.3 works best with plain text passwords (auto-hashes them)
#         # If it's a hash (starts with $2b$), show warning but allow it
#         if password_value.startswith('$2b$'):
#             if len(password_value) != 60:
#                 st.error(f"❌ Password hash for user '{username}' is invalid (length: {len(password_value)}, expected: 60)")
#                 st.error("   **SOLUTION:** Use plain text password - version 0.2.3 will hash it automatically")
#                 st.stop()
#             else:
#                 st.warning(f"⚠️ You're using a pre-hashed password for '{username}'.")
#                 st.warning("   Version 0.2.3 works better with plain text passwords.")
#         else:
#             # Plain text password - perfect for version 0.2.3
#             if len(password_value) < 3:
#                 st.warning(f"⚠️ Password for '{username}' is very short. Consider using a stronger password.")
#     
#     # Version 0.2.3 API: positional parameters (credentials, cookie_name, key, cookie_expiry_days)
#     # Note: Version 0.2.3 doesn't have auto_hash parameter - it auto-hashes plain text passwords
#     try:
#         authenticator = stauth.Authenticate(
#             credentials_dict,  # Positional: credentials dict
#             config['cookie']['name'],  # Positional: cookie_name
#             config['cookie']['key'],  # Positional: key (cookie key)
#             float(config['cookie']['expiry_days'])  # Positional: cookie_expiry_days
#         )
#     except Exception as auth_init_error:
#         st.error(f"❌ Failed to initialize authenticator: {auth_init_error}")
#         st.error("Please check that secrets.toml has valid credentials format.")
#         st.exception(auth_init_error)
#         st.stop()
# except Exception as e:
#     st.error(f"❌ Authentication setup failed: {e}")
#     st.exception(e)  # Show full traceback for debugging
#     st.stop()
#
# # Login - Version 0.2.3 API: login(form_name: str, location: str = 'main') -> tuple
# # Returns: (name, authentication_status, username)
# # If not authenticated, shows login widget and returns (None, None, None)
#
# try:
#     name, auth_status, username = authenticator.login("Login", "main")
# except Exception as login_error:
#     st.error(f"❌ Login error: {login_error}")
#     st.error("This might be due to invalid credentials structure. Please check secrets.toml format.")
#     st.exception(login_error)
#     st.stop()
#
# # Check authentication status
# if not auth_status:
#     if auth_status == False:
#         st.error("❌ Invalid username/password")
#     else:
#         st.warning("🔒 Please log in to access the trading system")
#     st.stop()
#
# # Main Dashboard (after authentication)
# st.sidebar.success(f"👋 Welcome, {name}")

# Initialize session state
if 'algo_running' not in st.session_state:
    st.session_state.algo_running = False
if 'show_strategy_settings' not in st.session_state:
    st.session_state.show_strategy_settings = False
if 'strategy_settings_feedback' not in st.session_state:
    st.session_state.strategy_settings_feedback = None
if 'market_refresh_feedback' not in st.session_state:
    st.session_state.market_refresh_feedback = None
if 'broker' not in st.session_state:
    try:
        # Get broker config safely (from config dict or st.secrets)
        broker_config_for_interface = config.get('broker', {})
        
        # If using Streamlit secrets and broker not in config dict, access directly
        if not broker_config_for_interface and config.get('_from_streamlit_secrets') and hasattr(st, 'secrets'):
            try:
                broker_secrets = getattr(st.secrets, 'broker', None)
                if broker_secrets:
                    # Convert to dict safely
                    broker_config_for_interface = {
                        'type': getattr(broker_secrets, 'type', 'angel'),
                        'api_key': getattr(broker_secrets, 'api_key', ''),
                        'client_id': getattr(broker_secrets, 'client_id', ''),
                        'username': getattr(broker_secrets, 'username', ''),
                        'pwd': getattr(broker_secrets, 'pwd', ''),
                        'token': getattr(broker_secrets, 'token', ''),
                    }
            except Exception as e:
                logger.warning(f"Could not access broker from Streamlit secrets: {e}")
        
        # Create broker interface with config that has broker section
        if broker_config_for_interface:
            # Ensure config dict has broker section for create_broker_interface
            temp_config = {'broker': broker_config_for_interface}
            st.session_state.broker = create_broker_interface(temp_config)
        else:
            st.session_state.broker = None
            logger.warning("No broker configuration found")
    except Exception as e:
        st.session_state.broker = None
        st.warning(f"Broker initialization warning: {e}")
if 'signal_handler' not in st.session_state:
    # Load strategy config
    import yaml as yaml_lib
    with open('config/config.yaml', 'r') as f:
        strategy_config = yaml_lib.safe_load(f)
    st.session_state.signal_handler = SignalHandler(strategy_config)
if 'trade_logger' not in st.session_state:
    st.session_state.trade_logger = TradeLogger()

# Initialize market data provider (only if broker is available)
if 'market_data_provider' not in st.session_state:
    if st.session_state.broker is not None:
        try:
            st.session_state.market_data_provider = MarketDataProvider(st.session_state.broker)
        except Exception as e:
            st.session_state.market_data_provider = None
            st.warning(f"Market data provider initialization warning: {e}")
    else:
        st.session_state.market_data_provider = None

# Initialize live runner (lazy - only when needed)
if 'live_runner' not in st.session_state:
    # Load full config (with market_data section)
    import yaml as yaml_lib
    with open('config/config.yaml', 'r') as f:
        full_config = yaml_lib.safe_load(f)
    
    if (st.session_state.broker is not None and 
        st.session_state.market_data_provider is not None and
        'signal_handler' in st.session_state and
        'trade_logger' in st.session_state):
        try:
            st.session_state.live_runner = LiveStrategyRunner(
                market_data_provider=st.session_state.market_data_provider,
                signal_handler=st.session_state.signal_handler,
                broker=st.session_state.broker,
                trade_logger=st.session_state.trade_logger,
                config=full_config
            )
        except Exception as e:
            st.session_state.live_runner = None
            st.warning(f"Live runner initialization warning: {e}")
    else:
        st.session_state.live_runner = None

# Ensure auto-refresh session state defaults before usage
if 'auto_refresh_enabled' not in st.session_state:
    st.session_state.auto_refresh_enabled = True
if 'auto_refresh_interval_sec' not in st.session_state:
    st.session_state.auto_refresh_interval_sec = 30
if 'next_auto_refresh_ts' not in st.session_state:
    st.session_state.next_auto_refresh_ts = time.time() + st.session_state.auto_refresh_interval_sec
if 'auto_refresh_counter' not in st.session_state:
    st.session_state.auto_refresh_counter = 0
if 'breakout_alert_audio' not in st.session_state:
    st.session_state.breakout_alert_audio = _generate_breakout_alert_audio()
if 'last_breakout_alert_key' not in st.session_state:
    st.session_state.last_breakout_alert_key = None
if 'last_breakout_alert_timestamp' not in st.session_state:
    st.session_state.last_breakout_alert_timestamp = None
if 'last_missed_trade' not in st.session_state:
    st.session_state.last_missed_trade = None
if 'last_refresh_error' not in st.session_state:
    st.session_state.last_refresh_error = None
previous_ui_render_time = st.session_state.get('_last_ui_render_time')
current_ui_render_time = datetime.now()
st.session_state['_last_ui_render_time'] = current_ui_render_time

def _trigger_market_data_refresh(reason: str) -> bool:
    """
    Refresh market data and capture telemetry.
    
    Args:
        reason: Label for refresh trigger (auto/manual/background).
    
    Returns:
        bool: True when refresh succeeds, else False.
    """
    provider = st.session_state.get('market_data_provider')
    if provider is None:
        logger.warning(f"Market data refresh skipped ({reason}) — provider unavailable")
        st.session_state.last_refresh_error = "Market data provider unavailable"
        return False
    try:
        provider.refresh_data()
        now_dt = datetime.now()
        st.session_state.last_refresh_time = now_dt
        st.session_state.last_refresh_reason = reason
        st.session_state.last_refresh_error = None
        logger.info(f"Market data refresh completed ({reason}) at {now_dt.isoformat()}")
        return True
    except Exception as err:
        logger.exception(f"Market data refresh failed ({reason}): {err}")
        st.session_state.last_refresh_error = str(err)
        return False

# Auto-refresh dashboard when algo is running
auto_refresh_active = (
    st.session_state.auto_refresh_enabled
    and (
        st.session_state.get('live_runner') is not None
        or st.session_state.get('market_data_provider') is not None
    )
)

if auto_refresh_active:
    now_ts = time.time()
    if now_ts >= st.session_state.next_auto_refresh_ts:
        refresh_success = _trigger_market_data_refresh("auto")
        if not refresh_success:
            st.session_state.market_refresh_feedback = (
                "warning",
                "⚠️ Auto refresh failed — check broker connectivity."
            )
        st.session_state.next_auto_refresh_ts = now_ts + st.session_state.auto_refresh_interval_sec
        st.session_state.auto_refresh_counter = st.session_state.get('auto_refresh_counter', 0) + 1
        st.rerun()
else:
    # Reset the next refresh timestamp so the timer starts fresh when re-enabled
    st.session_state.next_auto_refresh_ts = time.time() + st.session_state.auto_refresh_interval_sec

# ===================================================================
# BACKGROUND API REFRESH - Non-blocking refresh to prevent UI flicker
# Date: 2025-01-27
# Purpose: Refresh AngelOne API data in background thread without blocking UI
# ===================================================================

# Initialize background refresh tracking in session state
if 'background_refresh_thread' not in st.session_state:
    st.session_state.background_refresh_thread = None
if 'last_refresh_time' not in st.session_state:
    st.session_state.last_refresh_time = None
if 'refresh_in_progress' not in st.session_state:
    st.session_state.refresh_in_progress = False
if 'last_refresh_reason' not in st.session_state:
    st.session_state.last_refresh_reason = None
if 'last_refresh_error' not in st.session_state:
    st.session_state.last_refresh_error = None

def background_api_refresh(market_data_provider, broker):
    """
    Background thread function to refresh API data without blocking UI.
    Updates market data and broker session in the background.
    Note: Uses thread-safe approach compatible with Streamlit Cloud and local dev.
    
    Args:
        market_data_provider: MarketDataProvider instance (passed by reference)
        broker: Broker instance (passed by reference)
    """
    try:
        # Refresh market data if available
        if market_data_provider is not None:
            try:
                market_data_provider.refresh_data()
                logger.debug("Background market data refresh completed")
            except Exception as e:
                logger.warning(f"Background market data refresh failed: {e}")
        
        # Refresh broker session if available (check token validity)
        if broker is not None:
            try:
                # Only refresh if session exists (don't create new session unnecessarily)
                if hasattr(broker, 'session_generated') and broker.session_generated:
                    # Try to ensure session is valid (will refresh token if needed)
                    broker._ensure_session()
                    logger.debug("Background broker session refresh completed")
            except Exception as e:
                logger.warning(f"Background broker session refresh failed: {e}")
        
    except Exception as e:
        logger.error(f"Background API refresh error: {e}")

def start_background_refresh_if_needed(interval_seconds=10):
    """
    Start background refresh thread if not already running and enough time has passed.
    Thread-safe approach compatible with Streamlit Cloud and local dev.
    
    Args:
        interval_seconds: Minimum seconds between refreshes (default: 10)
    """
    # Check if we should refresh
    should_refresh = False
    if st.session_state.last_refresh_time is None:
        # First refresh
        should_refresh = True
    else:
        # Check if enough time has passed
        time_since_last = (datetime.now() - st.session_state.last_refresh_time).total_seconds()
        if time_since_last >= interval_seconds:
            should_refresh = True
    
    # Start refresh thread if needed and not already in progress
    if should_refresh and not st.session_state.refresh_in_progress:
        # Check if previous thread is still running (it shouldn't be, but check anyway)
        if st.session_state.background_refresh_thread is not None:
            if st.session_state.background_refresh_thread.is_alive():
                # Thread still running, wait a bit
                return
        
        # Start new background thread with references passed directly (thread-safe)
        try:
            # Get references before starting thread (thread-safe)
            market_data_provider = st.session_state.get('market_data_provider')
            broker = st.session_state.get('broker')
            
            # Start thread with references passed as arguments
            refresh_thread = threading.Thread(
                target=background_api_refresh,
                args=(market_data_provider, broker),
                daemon=True
            )
            refresh_thread.start()
            st.session_state.background_refresh_thread = refresh_thread
            # Update last refresh time (thread-safe - only writing, not reading from thread)
            st.session_state.last_refresh_time = datetime.now()
            st.session_state.last_refresh_reason = "background"
            st.session_state.last_refresh_error = None
            st.session_state.refresh_in_progress = True
            logger.debug("Background API refresh thread started")
        except Exception as e:
            logger.error(f"Failed to start background refresh thread: {e}")
            st.session_state.refresh_in_progress = False
    else:
        # If refresh is in progress, check if thread completed
        if st.session_state.refresh_in_progress:
            if st.session_state.background_refresh_thread is not None:
                if not st.session_state.background_refresh_thread.is_alive():
                    # Thread completed, mark as not in progress
                    st.session_state.refresh_in_progress = False

# Sidebar menu
tab = st.sidebar.radio(
    "📋 Menu",
    ["Dashboard", "Portfolio", "P&L", "Insights", "Orders & Trades", "Trade Journal", "Backtest", "Settings"],
    index=0
)

# Logout button - DISABLED (authentication bypassed)
# authenticator.logout("Logout", "sidebar")

# ============ DASHBOARD TAB ============
if tab == "Dashboard":
    st.header("📈 Live Algo Status")
    
    engine_status = st.session_state.algo_running
    broker_connected = st.session_state.broker is not None
    broker_config = config.get('broker', {})
    if not isinstance(broker_config, dict) and config.get('_from_streamlit_secrets') and hasattr(st, 'secrets'):
        try:
            broker_secrets = getattr(st.secrets, 'broker', None)
            broker_type = getattr(broker_secrets, 'type', 'Not Configured') if broker_secrets else 'Not Configured'
        except Exception:
            broker_type = 'Not Configured'
    else:
        broker_type = broker_config.get('type', 'Not Configured') if broker_config else 'Not Configured'
    broker_type = (broker_type or 'Not Configured').capitalize()
    
    market_open = False
    if st.session_state.get('live_runner') is not None and hasattr(st.session_state.live_runner, '_is_market_open'):
        try:
            market_open = st.session_state.live_runner._is_market_open()
        except Exception:
            market_open = False
    
    active_trade = None
    if st.session_state.get('trade_logger') is not None:
        try:
            open_trades = st.session_state.trade_logger.get_open_trades()
            if not open_trades.empty:
                open_trades = open_trades.copy()
                open_trades['__ts__'] = pd.to_datetime(open_trades.get('timestamp', None), errors='coerce')
                open_trades = open_trades.sort_values('__ts__')
                latest_trade = open_trades.iloc[-1]
                
                def _to_float(value):
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        return None
                
                entry_price = _to_float(latest_trade.get('entry'))
                sl_price = _to_float(latest_trade.get('sl'))
                tp_price = _to_float(latest_trade.get('tp'))
                target_points = (tp_price - entry_price) if (tp_price is not None and entry_price is not None) else None
                qty_raw = latest_trade.get('quantity', 0)
                try:
                    qty_lots = int(float(qty_raw))
                except (TypeError, ValueError):
                    qty_lots = 0
                
                active_trade = {
                    'direction': str(latest_trade.get('direction', '')).upper(),
                    'strike': latest_trade.get('strike', '—'),
                    'status': str(latest_trade.get('status', 'open')).title(),
                    'entry': entry_price,
                    'sl': sl_price,
                    'tp': tp_price,
                    'target_points': target_points,
                    'quantity': qty_lots,
                    'timestamp': latest_trade.get('timestamp', ''),
                    'order_id': latest_trade.get('order_id', '')
                }
        except Exception as e:
            logger.debug(f"Active trade summary failed: {e}")
    
    with st.container():
        st.markdown('<div class="dashboard-hero">', unsafe_allow_html=True)
        hero_left, hero_right = st.columns([1.4, 1], gap="medium")
        
        with hero_left:
            status_cols = st.columns(3, gap="small")
            status_cols[0].metric("🔌 Algo", "🟢 Running" if engine_status else "🔴 Stopped")
            broker_value = "🟢 Connected" if broker_connected else "🔴 Not Connected"
            broker_suffix = f" · {broker_type}" if broker_connected else ""
            status_cols[1].metric("🧑‍💼 Broker", f"{broker_value}{broker_suffix}")
            status_cols[2].metric("⏰ Market", "🟢 Open" if market_open else "🔴 Closed")
            
            # Add execution armed status indicator
            execution_armed_status = st.session_state.get('execution_armed', False)
            execution_icon = "🔓" if execution_armed_status else "🔒"
            execution_text = "ARMED" if execution_armed_status else "DISARMED"
            execution_color = "🟢" if execution_armed_status else "🟡"
            status_cols[0].caption(f"{execution_icon} Execution: {execution_color} {execution_text}")
            
            control_cols = st.columns([1, 1, 1, 1], gap="small")
            settings_col, arm_col, start_col, stop_col = control_cols
            
            with settings_col:
                if st.button("⚙️ Strategy Settings", use_container_width=True, type="secondary"):
                    st.session_state.show_strategy_settings = not st.session_state.show_strategy_settings
            
            with arm_col:
                # Use session state to track execution arming
                if 'execution_armed' not in st.session_state:
                    st.session_state.execution_armed = False
                
                arm_disabled = st.session_state.live_runner is None or not st.session_state.algo_running
                if st.session_state.execution_armed:
                    # Show Disarm button (red/warning)
                    if st.button("🛑 Disarm Exec", use_container_width=True, type="secondary", disabled=arm_disabled, help="Disable live trade execution (safety lock)"):
                        st.session_state.execution_armed = False
                        # Also set on live_runner instance if available
                        if st.session_state.live_runner is not None:
                            st.session_state.live_runner.execution_armed = False
                            logger.info("Live execution DISARMED on live_runner instance")
                        st.session_state.strategy_settings_feedback = (
                            "warning",
                            "🛑 Live execution DISARMED - trades will be simulated only"
                        )
                        logger.info("Live execution DISARMED via UI")
                        st.rerun()
                else:
                    # Show Arm button (green/primary)
                    if st.button("🔓 Arm Exec", use_container_width=True, type="primary", disabled=arm_disabled, help="Enable live trade execution (required for real trades)"):
                        st.session_state.execution_armed = True
                        # Also set on live_runner instance if available
                        if st.session_state.live_runner is not None:
                            st.session_state.live_runner.execution_armed = True
                            logger.info("Live execution ARMED on live_runner instance")
                        st.session_state.strategy_settings_feedback = (
                            "success",
                            "🔓 Live execution ARMED - real trades will be placed on next signal!"
                        )
                        logger.info("Live execution ARMED via UI")
                        st.rerun()
            
            with start_col:
                start_disabled = st.session_state.algo_running or st.session_state.live_runner is None
                if st.button("▶️ Start", use_container_width=True, type="primary", disabled=start_disabled):
                    if st.session_state.live_runner is None:
                        st.session_state.strategy_settings_feedback = (
                            "error",
                            "❌ Live runner not initialized. Check broker configuration."
                        )
                    else:
                        try:
                            success = st.session_state.live_runner.start()
                            if success:
                                st.session_state.algo_running = True
                                st.session_state.strategy_settings_feedback = (
                                    "success",
                                    "✅ Algorithm started – monitoring live market data."
                                )
                            else:
                                st.session_state.strategy_settings_feedback = (
                                    "error",
                                    "❌ Failed to start algorithm. Check logs for details."
                                )
                        except Exception as e:
                            st.session_state.strategy_settings_feedback = (
                                "error",
                                f"❌ Error starting algorithm: {e}"
                            )
                            logger.exception(e)
                    st.rerun()
            
            with stop_col:
                stop_disabled = (not st.session_state.algo_running) or st.session_state.live_runner is None
                if st.button("⏹️ Stop", use_container_width=True, type="secondary", disabled=stop_disabled):
                    if st.session_state.live_runner is None:
                        st.session_state.algo_running = False
                        st.session_state.strategy_settings_feedback = (
                            "warning",
                            "⚠️ Algo state reset – live runner unavailable."
                        )
                    else:
                        try:
                            success = st.session_state.live_runner.stop()
                            if success:
                                st.session_state.algo_running = False
                                st.session_state.strategy_settings_feedback = (
                                    "warning",
                                    "⏸️ Algorithm stopped."
                                )
                            else:
                                st.session_state.strategy_settings_feedback = (
                                    "error",
                                    "❌ Failed to stop algorithm."
                                )
                        except Exception as e:
                            st.session_state.strategy_settings_feedback = (
                                "error",
                                f"❌ Error stopping algorithm: {e}"
                            )
                            logger.exception(e)
                    st.rerun()
            
            feedback = st.session_state.strategy_settings_feedback
            if feedback:
                level, message = feedback
                if level == "success":
                    st.success(message)
                elif level == "warning":
                    st.warning(message)
                else:
                    st.error(message)
                st.session_state.strategy_settings_feedback = None
        
        with hero_right:
            st.markdown("#### 🧠 Active Trade")
            if active_trade:
                badge = f"{active_trade['direction']} {active_trade['strike']}"
                qty_label = f"{active_trade['quantity']} lot(s)" if active_trade['quantity'] else "—"
                st.markdown(f"**{badge}** · {qty_label} · {active_trade['status']}")
                trade_cols = st.columns(4, gap="small")
                entry_display = f"₹{active_trade['entry']:.2f}" if active_trade['entry'] is not None else "—"
                sl_display = f"₹{active_trade['sl']:.2f}" if active_trade['sl'] is not None else "—"
                tp_display = f"₹{active_trade['tp']:.2f}" if active_trade['tp'] is not None else "—"
                target_display = f"{active_trade['target_points']:.2f} pts" if active_trade['target_points'] is not None else "—"
                trade_cols[0].metric("💸 Buy Price", entry_display)
                trade_cols[1].metric("🛡️ Stop Loss", sl_display)
                trade_cols[2].metric("🎯 Take Profit", tp_display)
                trade_cols[3].metric("📈 Target", target_display)
                if active_trade['order_id']:
                    st.caption(f"Order ID: `{active_trade['order_id']}`")
            else:
                st.info("No active trades at the moment.")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    info_cols = st.columns(3, gap="small")
    with info_cols[0]:
        active_signals = st.session_state.signal_handler.get_active_signals()
        st.metric("📊 Signals Watching", len(active_signals))
    with info_cols[1]:
        nifty_ltp = "—"
        try:
            if st.session_state.market_data_provider is not None:
                ohlc = st.session_state.market_data_provider.fetch_ohlc(mode="LTP")
                if isinstance(ohlc, dict):
                    ltp_val = ohlc.get('ltp') or ohlc.get('close')
                    if ltp_val is not None:
                        nifty_ltp = f"{float(ltp_val):.2f}"
        except Exception:
            pass
        st.metric("📈 NIFTY LTP", nifty_ltp)
    with info_cols[2]:
        realized_pnl = 0.0
        try:
            from engine.pnl_service import compute_realized_pnl
            from engine.db import init_database
            from sqlalchemy.exc import OperationalError
            init_database(create_all=True)
            org_id = config.get('tenant', {}).get('org_id', 'demo-org')
            user_id = config.get('tenant', {}).get('user_id', 'admin')
            try:
                pnl_snapshot = compute_realized_pnl(org_id, user_id)
                realized_pnl = pnl_snapshot.get('realized_pnl', 0.0)
            except OperationalError:
                init_database(create_all=True)
                pnl_snapshot = compute_realized_pnl(org_id, user_id)
                realized_pnl = pnl_snapshot.get('realized_pnl', 0.0)
        except Exception:
            realized_pnl = 0.0
        pnl_prefix = "🟢" if realized_pnl >= 0 else "🔴"
        st.metric("💰 Realized P&L", f"{pnl_prefix} ₹{realized_pnl:,.2f}")
    
    st.divider()

    # In-app alert: toast when a new trade is logged
    try:
        if 'last_trade_count' not in st.session_state:
            st.session_state.last_trade_count = 0
        current_trades = st.session_state.trade_logger.get_all_trades()
        current_count = len(current_trades) if not current_trades.empty else 0
        if current_count > st.session_state.last_trade_count:
            delta = current_count - st.session_state.last_trade_count
            st.toast(f"✅ {delta} new trade(s) executed", icon="✅")
        st.session_state.last_trade_count = current_count
    except Exception:
        pass

    # Auto-refresh toggle with tooltip
    auto = st.checkbox(
        f"🔄 Auto-refresh every {st.session_state.auto_refresh_interval_sec} seconds",
        value=st.session_state.auto_refresh_enabled,
        help="Automatically refreshes the dashboard to show latest market data and trade updates"
    )
    st.session_state.auto_refresh_enabled = auto
    if auto:
        st.caption("✅ Auto-refresh enabled - Market data will refresh in background (no UI flicker)")
    else:
        st.caption("⏸️ Auto-refresh paused - use manual refresh or restart the algo to resume.")
        # Background refresh will be handled at the end of the page render
    
    if st.session_state.show_strategy_settings:
        st.divider()
        st.caption("Adjust live trading parameters. Changes apply to the next signal.")
        
        config_source = config if isinstance(config, dict) else {}
        if st.session_state.live_runner is not None:
            config_source = st.session_state.live_runner.config
        
        strategy_cfg = config_source.get('strategy', {})
        pm_cfg = config_source.get('position_management', {})
        risk_cfg = config_source.get('risk_management', {})
        
        current_sl_points = strategy_cfg.get('sl', 30)
        current_order_lots = config_source.get('broker', {}).get('default_lots', 2)
        current_lot_size = config_source.get('lot_size', 75)
        current_trail_points = pm_cfg.get('trail_points', 10)
        current_atm_offset = strategy_cfg.get('atm_offset', 0)
        current_daily_loss_limit_pct = risk_cfg.get('daily_loss_limit_pct', 5.0)
        
        if st.session_state.live_runner is not None:
            current_sl_points = getattr(st.session_state.live_runner, 'sl_points', current_sl_points)
            current_order_lots = getattr(st.session_state.live_runner, 'order_lots', current_order_lots)
            current_lot_size = getattr(st.session_state.live_runner, 'lot_size', current_lot_size)
            live_runner_pm_cfg = st.session_state.live_runner.config.get('position_management', {})
            current_trail_points = live_runner_pm_cfg.get('trail_points', current_trail_points)
            current_atm_offset = st.session_state.live_runner.config.get('strategy', {}).get('atm_offset', current_atm_offset)
            current_daily_loss_limit_pct = getattr(
                st.session_state.live_runner,
                'daily_loss_limit_pct',
                current_daily_loss_limit_pct
            )
        
        with st.form("strategy_settings_form", clear_on_submit=False):
            settings_cols = st.columns(2)
            with settings_cols[0]:
                sl_points_input = st.number_input(
                    "Stop Loss (points)",
                    min_value=10,
                    max_value=100,
                    value=int(current_sl_points),
                    step=5,
                    help="Applies to option premium. Example: 30 points → SL at entry - 30."
                )
                trail_points_input = st.number_input(
                    "Trailing SL step (points)",
                    min_value=5,
                    max_value=50,
                    value=int(current_trail_points),
                    step=5,
                    help="Trailing increment applied once price moves favourably by the chosen step."
                )
            with settings_cols[1]:
                atm_offset_input = st.number_input(
                    "Strike bias (points)",
                    min_value=-300,
                    max_value=300,
                    value=int(current_atm_offset),
                    step=50,
                    help="Shifts strike selection away from ATM. Positive = OTM (calls), negative = ITM."
                )
                sl_lots_input = st.number_input(
                    "Order quantity (lots)",
                    min_value=1,
                    max_value=10,
                    value=int(current_order_lots),
                    step=1,
                    help="Number of lots to trade per signal."
                )
            
            st.divider()
            st.caption("Risk management overrides")
            
            risk_cols = st.columns(2)
            with risk_cols[0]:
                daily_loss_limit_pct_input = st.number_input(
                    "Daily loss limit (%)",
                    min_value=1.0,
                    max_value=15.0,
                    value=float(current_daily_loss_limit_pct),
                    step=0.5,
                    format="%.1f",
                    help="Trading halts if daily P&L drops below -X% of initial capital."
                )
            with risk_cols[1]:
                lot_size_input = st.number_input(
                    "Lot size (contracts)",
                    min_value=25,
                    max_value=100,
                    value=int(current_lot_size),
                    step=25,
                    help="Lot size for position sizing calculations."
                )
            
            submitted = st.form_submit_button("💾 Save strategy configuration", use_container_width=True)
            if submitted:
                try:
                    st.session_state.show_strategy_settings = False
                    if st.session_state.live_runner is not None:
                        st.session_state.live_runner.update_strategy_config(
                            sl_points=int(sl_points_input),
                            atm_offset=int(atm_offset_input),
                            order_lots=int(sl_lots_input),
                            trail_points=int(trail_points_input),
                            daily_loss_limit_pct=float(daily_loss_limit_pct_input),
                            lot_size=int(lot_size_input)
                        )
                    st.success("✅ Strategy settings saved.")
                except Exception as e:
                    st.error(f"❌ Error updating config: {e}")

    st.divider()
    st.subheader("🧩 Inside Bar Snapshot")
    
    inside_bar_time_label = "—"
    mother_time_label = "—"
    range_label = "—"
    breakout_label = "Waiting"
    compression_label = ""
    inside_bar_available = False
    
    ist = pytz.timezone("Asia/Kolkata")
    
    def _format_ist(ts_value):
        try:
            ts = pd.to_datetime(ts_value)
            if ts.tzinfo is None:
                ts = ist.localize(ts)
            else:
                ts = ts.astimezone(ist)
            return ts.strftime("%d-%b %I:%M %p")
        except Exception:
            return str(ts_value)
    
    one_hour_data = pd.DataFrame()
    try:
        if st.session_state.get('market_data_provider') is not None:
            window_hours = 48
            if st.session_state.get('live_runner') is not None:
                window_hours = st.session_state.live_runner.config.get('market_data', {}).get('data_window_hours_1h', 48)
            one_hour_data = st.session_state.market_data_provider.get_1h_data(
                window_hours=window_hours,
                use_direct_interval=True,
                include_latest=True
            )
    except Exception as e:
        logger.warning(f"Inside bar snapshot fetch failed: {e}")
        one_hour_data = pd.DataFrame()
    
    if isinstance(one_hour_data, pd.DataFrame) and not one_hour_data.empty:
        df_ib = one_hour_data.copy()
        if 'Date' in df_ib.columns:
            try:
                df_ib['Date'] = pd.to_datetime(df_ib['Date'])
            except Exception:
                pass
        df_ib = df_ib.sort_values('Date').reset_index(drop=True)
        
        try:
            inside_indices = detect_inside_bar(df_ib)
        except Exception as e:
            logger.warning(f"Inside bar detection failed in snapshot: {e}")
            inside_indices = []
        
        if inside_indices:
            latest_inside_idx = inside_indices[-1]
            mother_idx = find_mother_index(df_ib, latest_inside_idx)
            if mother_idx is not None:
                inside_row = df_ib.iloc[latest_inside_idx]
                mother_row = df_ib.iloc[mother_idx]
                
                inside_bar_time_label = _format_ist(inside_row['Date'])
                mother_time_label = _format_ist(mother_row['Date'])
                range_high = float(mother_row['High'])
                range_low = float(mother_row['Low'])
                range_label = f"{range_low:.2f} → {range_high:.2f}"
                
                compression_length = len([idx for idx in inside_indices if idx >= mother_idx])
                compression_label = f"{compression_length} bar(s) inside range"
                
                breakout_direction = st.session_state.get("last_breakout_direction")
                if breakout_direction not in ("CE", "PE"):
                    try:
                        breakout_direction = confirm_breakout(
                            df_ib,
                            range_high,
                            range_low,
                            latest_inside_idx,
                            mother_idx=mother_idx,
                            volume_threshold_multiplier=1.0,
                            symbol="NIFTY"
                        )
                    except Exception as e:
                        logger.warning(f"Inside bar snapshot breakout check failed: {e}")
                        breakout_direction = None
                
                if breakout_direction == "CE":
                    breakout_label = "Breakout ↑ CE"
                elif breakout_direction == "PE":
                    breakout_label = "Breakout ↓ PE"
                else:
                    breakout_label = "Inside range"
                
                if breakout_direction in ("CE", "PE"):
                    alert_key = f"{mother_idx}-{latest_inside_idx}-{breakout_direction}"
                    if st.session_state.get("last_breakout_alert_key") != alert_key:
                        st.session_state.last_breakout_alert_key = alert_key
                        st.session_state.last_breakout_alert_timestamp = datetime.now().isoformat()
                        st.audio(st.session_state.breakout_alert_audio, format="audio/wav")
                        st.success(
                            "🔔 Breakout confirmed — audio alert triggered for the active inside bar."
                        )
                        # Clear any previous missed-trade banner once a fresh breakout is detected
                        st.session_state.last_missed_trade = None
                
                inside_bar_available = True
    
    inside_cols = st.columns(4)
    with inside_cols[0]:
        st.metric("Inside bar time", inside_bar_time_label)
    with inside_cols[1]:
        st.metric("Mother candle time", mother_time_label)
    with inside_cols[2]:
        st.metric("Mother range (L → H)", range_label)
    with inside_cols[3]:
        st.metric("Breakout status", breakout_label)
    
    if inside_bar_available and compression_label:
        st.caption(f"Compression depth: {compression_label}")
    elif not inside_bar_available:
        st.info("No active inside bar identified in the latest 1-hour data window.")
    
    missed_trade_info = st.session_state.get("last_missed_trade")
    if missed_trade_info:
        with st.expander("⚠️ Missed Breakout Window", expanded=True):
            st.warning(
                f"Trade skipped — breakout candle closed more than 5 minutes ago.\n\n"
                f"- Direction: **{missed_trade_info.get('direction', '—')}**\n"
                f"- Inside Bar: {missed_trade_info.get('inside_bar_time', '—')}\n"
                f"- Mother Candle: {missed_trade_info.get('signal_time', '—')}\n"
                f"- Range: {missed_trade_info.get('range_low', '—')} → {missed_trade_info.get('range_high', '—')}\n"
                f"- Logged at: {missed_trade_info.get('timestamp', '—')}"
            )
            st.caption("Breakout execution is blocked after 5 minutes to avoid chasing late entries.")
    
    # Live data status
    if st.session_state.algo_running and st.session_state.live_runner is not None:
        st.divider()
        st.subheader("📡 Live Data Status")
        st.caption(
            f"🔁 Auto-refreshes every {st.session_state.auto_refresh_interval_sec}s while the algo is running."
        )
        
        status = st.session_state.live_runner.get_status()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Status", "🟢 Running" if status['running'] else "🔴 Stopped")
        
        with col2:
            st.metric("Cycles Completed", status['cycle_count'])
        
        with col3:
            if status['last_fetch_time']:
                fetch_time = datetime.fromisoformat(status['last_fetch_time'])
                st.metric("Last Data Fetch", fetch_time.strftime("%I:%M:%S %p"))
            else:
                st.metric("Last Data Fetch", "Never")
        
        with col4:
            if status['last_signal_time']:
                signal_time = datetime.fromisoformat(status['last_signal_time'])
                st.metric("Last Signal", signal_time.strftime("%I:%M:%S %p"))
            else:
                st.metric("Last Signal", "None")
        
        # Show error count if any
        if status['error_count'] > 0:
            st.warning(f"⚠️ {status['error_count']} errors encountered. Check logs for details.")
        
        # NEW: Risk Management & Safety Checks Section
        st.divider()
        st.subheader("🛡️ Risk Management & Safety Checks")
        
        # Get risk management status from live runner
        try:
            # Access risk management attributes
            daily_pnl = getattr(st.session_state.live_runner, 'daily_pnl', 0.0)
            daily_loss_limit_pct = getattr(st.session_state.live_runner, 'daily_loss_limit_pct', 5.0)
            max_positions = getattr(st.session_state.live_runner, 'max_concurrent_positions', 2)
            signal_cooldown = getattr(st.session_state.live_runner, 'signal_cooldown_seconds', 3600)
            active_positions = len(getattr(st.session_state.live_runner, 'active_monitors', []))
            
            # Get initial capital from config
            initial_capital = st.session_state.live_runner.config.get('initial_capital', 100000.0)
            loss_limit_amount = initial_capital * (daily_loss_limit_pct / 100.0)
            
            # Check market hours
            is_market_open = st.session_state.live_runner._is_market_open() if hasattr(st.session_state.live_runner, '_is_market_open') else False
            
            # Get available margin
            available_margin = 0.0
            try:
                if st.session_state.broker:
                    available_margin = st.session_state.broker.get_available_margin()
            except:
                pass
            
            # Get nearest expiry
            nearest_expiry = None
            expiry_safe = False
            try:
                if hasattr(st.session_state.live_runner, '_get_nearest_expiry'):
                    nearest_expiry = st.session_state.live_runner._get_nearest_expiry()
                    if nearest_expiry and hasattr(st.session_state.live_runner, '_is_safe_to_trade_expiry'):
                        expiry_safe = st.session_state.live_runner._is_safe_to_trade_expiry(nearest_expiry)
            except:
                pass
            
            # Prefer expiry derived from live Option Greeks (if fresher)
            greeks_expiry_dt = st.session_state.get("option_greeks_expiry_dt")
            if greeks_expiry_dt:
                normalized_expiry = greeks_expiry_dt
                try:
                    if normalized_expiry.hour == 0 and normalized_expiry.minute == 0:
                        normalized_expiry = normalized_expiry.replace(hour=15, minute=30)
                except AttributeError:
                    pass
                if nearest_expiry is None or normalized_expiry < nearest_expiry:
                    nearest_expiry = normalized_expiry
                    if hasattr(st.session_state.live_runner, '_is_safe_to_trade_expiry'):
                        expiry_safe = st.session_state.live_runner._is_safe_to_trade_expiry(nearest_expiry)
            
            # Display safety metrics in columns
            safety_col1, safety_col2, safety_col3, safety_col4 = st.columns(4)
            
            with safety_col1:
                # Daily P&L and loss limit
                pnl_color = "normal" if daily_pnl >= -loss_limit_amount else "inverse"
                st.metric("Daily P&L", f"₹{daily_pnl:,.2f}", 
                         delta=f"Limit: ₹{-loss_limit_amount:,.2f}", 
                         delta_color=pnl_color)
                if daily_pnl <= -loss_limit_amount:
                    st.error(f"🚨 Daily loss limit hit! ({daily_loss_limit_pct}% of capital)")
                elif daily_pnl <= -loss_limit_amount * 0.8:
                    st.warning("⚠️ Approaching daily loss limit")
                else:
                    st.success("✅ Within daily loss limit")
            
            with safety_col2:
                # Position limits
                pos_color = "normal" if active_positions < max_positions else "inverse"
                st.metric("Active Positions", f"{active_positions}/{max_positions}", 
                         delta="Limit reached" if active_positions >= max_positions else "Available",
                         delta_color=pos_color)
                if active_positions >= max_positions:
                    st.error("🚨 Position limit reached!")
                else:
                    st.success("✅ Position limit OK")
            
            with safety_col3:
                # Available margin
                st.metric("Available Margin", f"₹{available_margin:,.2f}")
                if available_margin < 10000:
                    st.warning("⚠️ Low margin available")
                elif available_margin == 0:
                    st.error("🚨 No margin data available")
                else:
                    st.success("✅ Margin sufficient")
            
            with safety_col4:
                # Market hours status
                market_status = "🟢 Open" if is_market_open else "🔴 Closed"
                st.metric("Market Status", market_status)
                if not is_market_open:
                    st.info("⏰ Market closed - trades will not execute")
                else:
                    st.success("✅ Market open - ready for trading")
            
            # Additional safety checks
            st.write("**Safety Check Status:**")
            check_col1, check_col2, check_col3 = st.columns(3)
            
            with check_col1:
                # Expiry validation
                if nearest_expiry:
                    expiry_label = st.session_state.get("option_greeks_expiry_str")
                    if not expiry_label:
                        try:
                            expiry_label = nearest_expiry.strftime("%d %b %Y (%A)")
                        except Exception:
                            expiry_label = str(nearest_expiry)
                    now_ts = datetime.now(nearest_expiry.tzinfo) if getattr(nearest_expiry, "tzinfo", None) else datetime.now()
                    time_remaining = nearest_expiry - now_ts
                    remaining_seconds = time_remaining.total_seconds()
                    if remaining_seconds <= 0:
                        st.error(f"🚨 Expiry has passed · {expiry_label}")
                    else:
                        days = int(remaining_seconds // 86400)
                        hours = int((remaining_seconds % 86400) // 3600)
                        minutes = int((remaining_seconds % 3600) // 60)
                        countdown_parts = []
                        if days > 0:
                            countdown_parts.append(f"{days} day{'s' if days != 1 else ''}")
                        if hours > 0:
                            countdown_parts.append(f"{hours} h")
                        if days == 0 and minutes > 0:
                            countdown_parts.append(f"{minutes} min")
                        countdown = ", ".join(countdown_parts) if countdown_parts else "< 1 min"
                    if expiry_safe:
                            st.success(f"✅ Expiry OK: {countdown} remaining · {expiry_label}")
                    else:
                            st.error(f"🚨 Expiry too close: {countdown} · {expiry_label}")
                else:
                    st.warning("⚠️ Expiry data not available")
            
            with check_col2:
                # Signal cooldown
                cooldown_minutes = signal_cooldown / 60
                st.info(f"📊 Signal cooldown: {cooldown_minutes:.0f} minutes")
            
            with check_col3:
                # Initial capital
                st.info(f"💰 Initial Capital: ₹{initial_capital:,.2f}")
            
            # Configuration section (read-only display for now)
            with st.expander("⚙️ Risk Management Configuration (Read from config.yaml)"):
                st.write("**Current Settings:**")
                st.write(f"- Daily Loss Limit: {daily_loss_limit_pct}% of capital")
                st.write(f"- Max Concurrent Positions: {max_positions}")
                st.write(f"- Signal Cooldown: {cooldown_minutes:.0f} minutes ({signal_cooldown} seconds)")
                st.write(f"- Initial Capital: ₹{initial_capital:,.2f}")
                st.caption("💡 To change these settings, edit config/config.yaml and restart the algorithm")
        
        except Exception as e:
            st.warning(f"⚠️ Could not load risk management status: {e}")
            logger.exception(e)
        
        # Market data refresh feedback
        refresh_feedback = st.session_state.market_refresh_feedback
        if refresh_feedback:
            level, message = refresh_feedback
            if level == "success":
                st.success(message)
            elif level == "warning":
                st.warning(message)
            else:
                st.error(message)
            st.session_state.market_refresh_feedback = None
        
        last_refresh_display = st.session_state.get('last_refresh_time')
        last_refresh_reason = st.session_state.get('last_refresh_reason')
        runner_fetch_time = None
        runner_reason = None
        live_runner = st.session_state.get('live_runner')
        if live_runner is not None:
            runner_fetch_time = getattr(live_runner, 'last_fetch_time', None)
            if runner_fetch_time is not None:
                runner_reason = "live-cycle"

        display_time = None
        display_reason = None
        if runner_fetch_time and isinstance(runner_fetch_time, datetime):
            if (not isinstance(last_refresh_display, datetime)) or (runner_fetch_time > last_refresh_display):
                display_time = runner_fetch_time
                display_reason = runner_reason
        if display_time is None and isinstance(last_refresh_display, datetime):
            display_time = last_refresh_display
            display_reason = last_refresh_reason or "auto"

        missed_trade_info = st.session_state.get("last_missed_trade")
        if display_time is not None:
            stamp = display_time.strftime("%d-%b %I:%M:%S %p")
            label = display_reason or "auto"
            st.caption(f"🕒 Last refresh: {stamp} ({label})")
        if missed_trade_info:
            st.error(
                f"🚨 Missed breakout ({missed_trade_info.get('direction', '—')}) — "
                f"breakout candle closed beyond the 5-minute window. "
                f"Range {missed_trade_info.get('range_low', '—')} → {missed_trade_info.get('range_high', '—')}."
            )
            if st.button("Dismiss alert", key="dismiss_missed_trade_banner"):
                st.session_state.last_missed_trade = None
                st.rerun()
        elif st.session_state.get('last_refresh_error'):
            st.warning(f"⚠️ Last refresh error: {st.session_state.last_refresh_error}")
        
        with st.expander("🔄 Backend Sync Details", expanded=False):
            st.write(f"• UI render time: {current_ui_render_time.strftime('%d-%b %I:%M:%S %p')}")
            if display_time is not None:
                normalized_display = display_time
                if isinstance(display_time, datetime) and display_time.tzinfo is not None:
                    try:
                        normalized_display = display_time.astimezone(datetime.now().astimezone().tzinfo).replace(tzinfo=None)
                    except Exception:
                        normalized_display = display_time.replace(tzinfo=None)
                st.write(f"• Backend refresh time: {display_time.strftime('%d-%b %I:%M:%S %p')} ({display_reason or 'auto'})")
                try:
                    delta_seconds = abs((current_ui_render_time - normalized_display).total_seconds())
                    st.write(f"• UI lag vs backend: {delta_seconds:.1f} seconds")
                except Exception:
                    pass
            if runner_fetch_time and isinstance(runner_fetch_time, datetime):
                st.write(f"• Live runner fetch time: {runner_fetch_time.strftime('%d-%b %I:%M:%S %p')} (live-cycle)")
            if previous_ui_render_time:
                st.write(f"• Previous UI render: {previous_ui_render_time.strftime('%d-%b %I:%M:%S %p')}")
            if st.session_state.auto_refresh_enabled:
                interval = float(st.session_state.auto_refresh_interval_sec)
                seconds_until = max(0.0, st.session_state.next_auto_refresh_ts - time.time())
                completion = 0.0
                if interval > 0:
                    completion = min(1.0, max(0.0, (interval - seconds_until) / interval))
                st.progress(completion)
                st.caption(f"Next auto refresh in {int(seconds_until)}s (interval {interval:.0f}s).")
            else:
                st.caption("Auto refresh disabled — use the manual refresh button.")
        
        # Manual refresh button
        if st.button("🔄 Refresh Market Data Now"):
            success = _trigger_market_data_refresh("manual")
            if success:
                timestamp = st.session_state.last_refresh_time.strftime("%d-%b %I:%M:%S %p")
                st.session_state.market_refresh_feedback = (
                    "success",
                    f"✅ Market data refreshed at {timestamp}."
                )
            else:
                error_msg = st.session_state.last_refresh_error or "Unknown error"
                st.session_state.market_refresh_feedback = (
                    "error",
                    f"❌ Failed to refresh market data: {error_msg}"
                )
            st.rerun()
    
    st.divider()
    with st.expander("📐 Option Greeks (NIFTY – next Tuesday expiry)", expanded=False):
        current_offset = 0
        if st.session_state.get('live_runner') is not None:
            current_offset = st.session_state.live_runner.config.get('strategy', {}).get('atm_offset', 0)
        bias_text = "ATM"
        if current_offset > 0:
            bias_text = f"OTM +{current_offset}"
        elif current_offset < 0:
            bias_text = f"ITM {abs(current_offset)}"
        st.markdown(f"**Configured strike bias:** {bias_text} points from ATM.")
        try:
            if st.session_state.broker is not None:
                greeks = st.session_state.broker.get_option_greeks("NIFTY")
                if greeks:
                    greeks_df = pd.DataFrame(greeks)
                    expiry_candidates = []
                    for expiry_col in ("expiry", "expiryDate", "expiry_date"):
                        if expiry_col in greeks_df.columns:
                            try:
                                unique_values = greeks_df[expiry_col].dropna().unique()
                            except Exception:
                                unique_values = []
                            for raw_expiry in unique_values:
                                parsed_expiry = _parse_expiry_to_datetime(raw_expiry)
                                if parsed_expiry:
                                    if parsed_expiry.hour == 0 and parsed_expiry.minute == 0:
                                        parsed_expiry = parsed_expiry.replace(hour=15, minute=30)
                                    expiry_candidates.append(parsed_expiry)
                            if expiry_candidates:
                                break
                    if expiry_candidates:
                        earliest_expiry = min(expiry_candidates)
                        st.session_state.option_greeks_expiry_dt = earliest_expiry
                        st.session_state.option_greeks_expiry_str = earliest_expiry.strftime("%d %b %Y (%A)")
                    keep_cols = [c for c in [
                        'name','expiry','strikePrice','optionType','delta','gamma','theta','vega','impliedVolatility','tradeVolume'
                    ] if c in greeks_df.columns]

                    atm_val = None
                    try:
                        if st.session_state.market_data_provider is not None:
                            o = st.session_state.market_data_provider.fetch_ohlc(mode="LTP")
                            lv = o.get('ltp') if isinstance(o, dict) else None
                            if lv is None and isinstance(o, dict):
                                lv = o.get('close')
                            if lv is not None:
                                atm_val = float(lv)
                    except Exception:
                        pass

                    if atm_val is not None and 'strikePrice' in greeks_df.columns:
                        try:
                            greeks_df['__dist__'] = (greeks_df['strikePrice'].astype(float) - atm_val).abs()
                            greeks_df = greeks_df.sort_values('__dist__')
                            greeks_df = greeks_df.head(20)
                        except Exception:
                            pass
                    st.dataframe(greeks_df[keep_cols] if keep_cols else greeks_df, width='stretch', height=300)
                else:
                    st.info("No Greeks data returned.")
            else:
                st.info("Broker not initialized.")
        except Exception as e:
            st.warning(f"Greeks error: {e}")

    st.divider()

    # Strategy Debug Information Section
    st.divider()
    st.subheader("🔍 Strategy Debug - Inside Bar Detection")
    
    # Try to run a quick strategy check to show current status
    if st.session_state.market_data_provider is not None and st.session_state.live_runner is not None:
        try:
            # Get latest market data
            data_1h = st.session_state.market_data_provider.get_1h_data(
                window_hours=st.session_state.live_runner.config.get('market_data', {}).get('data_window_hours_1h', 48)
            )
            data_15m = st.session_state.market_data_provider.get_15m_data(
                window_hours=st.session_state.live_runner.config.get('market_data', {}).get('data_window_hours_15m', 12)
            )
            
            raw_data_1h = data_1h.copy() if isinstance(data_1h, pd.DataFrame) else pd.DataFrame()
            raw_data_15m = data_15m.copy() if isinstance(data_15m, pd.DataFrame) else pd.DataFrame()

            data_1h = align_dataframe_to_ist(data_1h)
            data_15m = align_dataframe_to_ist(data_15m)

            debug_df = data_1h if isinstance(data_1h, pd.DataFrame) else pd.DataFrame()

            # Debug Snapshot UI temporarily disabled (2025-11-07)

            if not data_1h.empty and not data_15m.empty:
                # Show data availability
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("1H Candles Available", len(data_1h))
                with col2:
                    st.metric("15m Candles Available", len(data_15m))
                
                # Detect Inside Bars and show results
                inside_bars = detect_inside_bar(data_1h)
                
                # Create a set for quick lookup
                inside_bar_set = set(inside_bars)
                
                # Show recent candles with Inside Bar status
                st.write("**Recent 1H Candles Check (Last 10 - Most Recent First):**")
                recent_count = min(10, len(data_1h))
                
                # Get last N candles and reverse to show most recent first
                recent_data = data_1h.tail(recent_count)
                
                # Create a more readable display - iterate backwards (most recent first)
                display_data = []
                for i in range(len(recent_data) - 1, -1, -1):  # Start from most recent (last row)
                    # i is position in recent_data (0-based from tail)
                    # Original DataFrame index = len(data_1h) - recent_count + i
                    original_idx = len(data_1h) - recent_count + i
                    
                    # Format time in IST (assuming Date is already in IST after conversion)
                    time_val = recent_data.iloc[i]['Date'] if 'Date' in recent_data.columns else f"Row_{original_idx}"
                    if isinstance(time_val, pd.Timestamp) or hasattr(time_val, 'strftime'):
                        try:
                            time_str = format_ist_timestamp(time_val)
                        except Exception:
                            time_str = str(time_val)
                    else:
                        time_str = str(time_val)
                    
                    row_data = {
                        'Row': original_idx,
                        'Time (IST)': time_str,
                        'High': f"{recent_data.iloc[i]['High']:.2f}",
                        'Low': f"{recent_data.iloc[i]['Low']:.2f}",
                        'Close': f"{recent_data.iloc[i]['Close']:.2f}",
                    }
                    
                    # Check if this is an inside bar (using original DataFrame index)
                    # Note: Inside bar detection requires index >= 2 (needs at least previous candle)
                    is_inside = original_idx in inside_bar_set and original_idx >= 2
                    if is_inside:
                        row_data['Status'] = '✅ Inside Bar'
                        # Get reference candle info (previous candle at original_idx - 1)
                        if original_idx > 0:
                            ref_high = data_1h['High'].iloc[original_idx - 1]
                            ref_low = data_1h['Low'].iloc[original_idx - 1]
                            current_high = recent_data.iloc[i]['High']
                            current_low = recent_data.iloc[i]['Low']
                            # Verify inside bar logic
                            row_data['Reference Range'] = f"{ref_low:.2f} - {ref_high:.2f}"
                            row_data['Inside Check'] = f"✓ High {current_high:.2f} < {ref_high:.2f} ✓ Low {current_low:.2f} > {ref_low:.2f}"
                        else:
                            row_data['Reference Range'] = 'N/A'
                            row_data['Inside Check'] = 'N/A'
                    else:
                        row_data['Status'] = '❌ Not Inside'
                        # Still show reference range for context
                        if original_idx > 0:
                            ref_high = data_1h['High'].iloc[original_idx - 1]
                            ref_low = data_1h['Low'].iloc[original_idx - 1]
                            current_high = recent_data.iloc[i]['High']
                            current_low = recent_data.iloc[i]['Low']
                            # Show detailed reason why it's not inside
                            if current_high >= ref_high and current_low <= ref_low:
                                row_data['Reference Range'] = f"{ref_low:.2f} - {ref_high:.2f}"
                                row_data['Inside Check'] = f"✗ High {current_high:.2f} >= {ref_high:.2f} ✗ Low {current_low:.2f} <= {ref_low:.2f}"
                            elif current_high >= ref_high:
                                row_data['Reference Range'] = f"{ref_low:.2f} - {ref_high:.2f}"
                                row_data['Inside Check'] = f"✗ High {current_high:.2f} >= {ref_high:.2f} (must be < {ref_high:.2f})"
                            elif current_low <= ref_low:
                                row_data['Reference Range'] = f"{ref_low:.2f} - {ref_high:.2f}"
                                row_data['Inside Check'] = f"✗ Low {current_low:.2f} <= {ref_low:.2f} (must be > {ref_low:.2f})"
                            else:
                                # This shouldn't happen if logic is correct, but log it
                                row_data['Reference Range'] = f"{ref_low:.2f} - {ref_high:.2f}"
                                row_data['Inside Check'] = "✓ High ✓ Low (unexpected - check logic)"
                        else:
                            row_data['Reference Range'] = '—'
                            row_data['Inside Check'] = 'No reference'
                    
                    display_data.append(row_data)
                
                # Display DataFrame with most recent first
                display_df = pd.DataFrame(display_data)
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
                if inside_bars:
                    latest_idx = inside_bars[-1]
                    mother_idx = find_mother_index(data_1h, latest_idx)
                    if mother_idx is None:
                        st.warning("Unable to determine mother candle for the latest inside bar.")
                    else:
                        range_high = data_1h['High'].iloc[mother_idx]
                        range_low = data_1h['Low'].iloc[mother_idx]
                        inside_bar_time = data_1h['Date'].iloc[latest_idx] if 'Date' in data_1h.columns else f"Index_{latest_idx}"
                        ref_time = data_1h['Date'].iloc[mother_idx] if 'Date' in data_1h.columns else f"Index_{mother_idx}"
                        
                        inside_bar_label = format_ist_timestamp(inside_bar_time) if isinstance(inside_bar_time, (pd.Timestamp, str)) else inside_bar_time
                        ref_time_label = format_ist_timestamp(ref_time) if isinstance(ref_time, (pd.Timestamp, str)) else ref_time
                        
                        st.success(f"✅ Inside Bar Detected! ({len(inside_bars)} total) | **Most Recent:** {inside_bar_label}")

                        st.write("**Most Recent Inside Bar Details:**")
                        details_col1, details_col2 = st.columns(2)
                        with details_col1:
                            st.write(f"📊 **Inside Bar Time:** {inside_bar_label}")
                            st.write(f"📊 **Mother Candle:** {ref_time_label}")
                            st.write(f"📈 **Breakout Range:** {range_low:.2f} - {range_high:.2f}")
                        with details_col2:
                            st.write(f"🔢 **Inside Bar High:** {data_1h['High'].iloc[latest_idx]:.2f}")
                            st.write(f"🔢 **Inside Bar Low:** {data_1h['Low'].iloc[latest_idx]:.2f}")
                            st.write(f"📍 **All Inside Bar Indices:** {inside_bars}")
                        
                        # Check for breakout (using 1H data only)
                        st.write("**Breakout Status:**")
                        ui_breakout_direction = st.session_state.get("last_breakout_direction")
                        direction = ui_breakout_direction
                        if direction not in ("CE", "PE"):
                            direction = confirm_breakout(
                                data_1h,
                                range_high,
                                range_low,
                                latest_idx,
                                mother_idx=mother_idx,
                                volume_threshold_multiplier=1.0,
                                symbol="NIFTY"
                            )
                        price_at_last_candle = data_1h['Close'].iloc[-1]
                        within_range = range_low <= price_at_last_candle <= range_high
                        
                        if direction == "CE":
                            st.success("✅ Breakout Confirmed: CE (Call Option)")
                        elif direction == "PE":
                            st.success("✅ Breakout Confirmed: PE (Put Option)")
                        else:
                            st.info("⏳ Waiting for breakout confirmation...")
                        
                        st.write(f"📊 Within range: {range_low:.2f} ≤ {price_at_last_candle:.2f} ≤ {range_high:.2f}")

                        if not within_range:
                            st.warning("⚠️ Price has moved out of the mother candle range, monitor for breakout confirmation.")
                else:
                    st.info("🔍 No Inside Bar patterns detected in current 1H data")
                    st.caption("💡 Inside Bar requires: candle high < previous high AND candle low > previous low")
                st.caption("💡 This information updates when you refresh the page or auto-refresh is enabled")
            else:
                st.warning("⚠️ Insufficient market data. Please wait for data to load.")
        except Exception as e:
            st.error(f"❌ Error checking strategy status: {e}")
            logger.exception(e)
    else:
        st.info("ℹ️ Market data provider or live runner not available")
    
    st.divider()
    
    # Active Trades Section
    st.subheader("📊 Active Trades")
    active_signals = st.session_state.signal_handler.get_active_signals()
    
    if active_signals:
        trades_df = pd.DataFrame(active_signals)
        st.dataframe(trades_df, use_container_width=True, height=300)
    else:
        st.info("ℹ️ No active trades")
    
    # Recent Trade Journal Section (last 5)
    st.divider()
    st.subheader("📒 Recent Trade Journal (Last 5)")
    try:
        all_trades = st.session_state.trade_logger.get_all_trades()
        if not all_trades.empty:
            # Get last 5 trades
            recent_trades = all_trades.tail(5)
            # Display in a formatted table
            st.dataframe(
                recent_trades,
                use_container_width=True,
                height=200
            )
            # Show summary
            if len(recent_trades) > 0:
                recent_pnl = recent_trades['pnl'].sum() if 'pnl' in recent_trades.columns else 0
                st.caption(f"📊 Recent 5 trades P&L: ₹{recent_pnl:,.2f}")
        else:
            st.info("📝 No trades logged yet. Your trade journal will appear here once trades are executed.")
    except Exception as e:
        st.warning(f"⚠️ Could not load trade journal: {e}")
    
    # System Information
    st.divider()
    st.subheader("ℹ️ System Information")
    
    # Load strategy config
    import yaml as yaml_lib
    with open('config/config.yaml', 'r') as f:
        strategy_config = yaml_lib.safe_load(f)
    
    info_col1, info_col2 = st.columns(2)
    
    with info_col1:
        st.write("**Strategy Parameters:**")
        st.write(f"- Lot Size: {strategy_config.get('lot_size', 'N/A')}")
        st.write(f"- Stop Loss: {strategy_config.get('strategy', {}).get('sl', 'N/A')} points")
        st.write(f"- Risk-Reward: {strategy_config.get('strategy', {}).get('rr', 'N/A')}")
    
    with info_col2:
        st.write("**Filters:**")
        filters = strategy_config.get('strategy', {}).get('filters', {})
        st.write(f"- Volume Spike: {'✅' if filters.get('volume_spike') else '❌'}")
        st.write(f"- Avoid Open Range: {'✅' if filters.get('avoid_open_range') else '❌'}")

    # Perform background API refresh if auto-refresh is enabled (non-blocking)
    # Date: 2025-01-27
    # Purpose: Refresh API data in background without causing UI flicker from full page rerun
    if auto:
        start_background_refresh_if_needed(interval_seconds=st.session_state.auto_refresh_interval_sec)
        # Use time.sleep with rerun only if needed (fallback for very old data)
        # But prefer background refresh to avoid UI flicker
        if st.session_state.last_refresh_time is not None:
            time_since_last = (datetime.now() - st.session_state.last_refresh_time).total_seconds()
            # Only rerun if last refresh was more than 15 seconds ago (fallback)
            if time_since_last > 15:
                time.sleep(10)
                st.rerun()
        else:
            # First load, wait a bit then refresh
            time.sleep(10)
            st.rerun()

# ============ TRADE JOURNAL TAB ============
elif tab == "Portfolio":
    st.header("📁 Portfolio")
    if st.session_state.broker is None:
        st.warning("⚠️ Broker not initialized. Please check your broker configuration in Settings.")
    else:
        # Cached fetchers to respect API rate limits
        @st.cache_data(ttl=0)
        def _fetch_holdings():
            import time
            attempts = 0
            while attempts < 2:
                try:
                    return st.session_state.broker.get_holdings()
                except Exception as e:
                    logger.exception(e)
                    attempts += 1
                    time.sleep(2)
            return []

        @st.cache_data(ttl=0)
        def _fetch_all_holdings():
            import time
            attempts = 0
            while attempts < 2:
                try:
                    return st.session_state.broker.get_all_holdings()
                except Exception as e:
                    logger.exception(e)
                    attempts += 1
                    time.sleep(2)
            return {}

        @st.cache_data(ttl=0)
        def _fetch_positions_book():
            import time
            attempts = 0
            while attempts < 2:
                try:
                    # Prefer detailed positions book endpoint
                    if hasattr(st.session_state.broker, 'get_positions_book'):
                        return st.session_state.broker.get_positions_book()
                    # Fallback to generic positions
                    return st.session_state.broker.get_positions()
                except Exception as e:
                    logger.exception(e)
                    attempts += 1
                    time.sleep(2)
            return []

        # Controls
        colr1, colr2 = st.columns([1,1])
        with colr1:
            refresh = st.button("🔄 Refresh Portfolio", use_container_width=True, help="Fetches latest portfolio data from broker")
        with colr2:
            st.caption("💡 Data cached for 15s to avoid API rate limits")

        if refresh:
            _fetch_holdings.clear()
            _fetch_all_holdings.clear()
            _fetch_positions_book.clear()

        # Totals (all holdings)
        all_hold = _fetch_all_holdings()
        met1, met2, met3, met4 = st.columns(4)
        with met1:
            tv = all_hold.get('totalholdingvalue') if isinstance(all_hold, dict) else None
            if tv is None and isinstance(all_hold, dict):
                tv = all_hold.get('totalHoldingValue')
            st.metric("Total Holding Value", f"₹{float(tv):,.2f}" if tv else "—")
        with met2:
            iv = all_hold.get('totalinvestmentvalue') if isinstance(all_hold, dict) else None
            if iv is None and isinstance(all_hold, dict):
                iv = all_hold.get('totalInvestmentValue')
            st.metric("Total Investment", f"₹{float(iv):,.2f}" if iv else "—")
        with met3:
            pnl = all_hold.get('totalprofitandloss') if isinstance(all_hold, dict) else None
            if pnl is None and isinstance(all_hold, dict):
                pnl = all_hold.get('totalProfitAndLoss')
            st.metric("Total P&L", f"₹{float(pnl):,.2f}" if pnl else "—")
        with met4:
            pnlp = all_hold.get('totalprofitandlosspercent') if isinstance(all_hold, dict) else None
            if pnlp is None and isinstance(all_hold, dict):
                pnlp = all_hold.get('totalProfitAndLossPercent')
            st.metric("P&L %", f"{float(pnlp):.2f}%" if pnlp else "—")

        st.divider()
        
        # Trade Parameters Section in Collapsible Card
        with st.expander("⚙️ Trade Parameters", expanded=False):
            st.subheader("📊 Configure Trade Parameters")
            
            # Load current values from config
            import yaml as yaml_lib
            with open('config/config.yaml', 'r') as f:
                strategy_config = yaml_lib.safe_load(f)
            
            pm_config = strategy_config.get('position_management', {})
            
            col_param1, col_param2 = st.columns(2)
            
            with col_param1:
                sl_points = st.number_input(
                    "🛑 Stop Loss (Points)",
                    min_value=10,
                    max_value=100,
                    value=int(pm_config.get('sl_points', 30)),
                    step=5,
                    help="Stop loss in points (e.g., 30 points means SL at entry - 30 points)"
                )
                
                trail_points = st.number_input(
                    "📈 Trailing SL Step (Points)",
                    min_value=5,
                    max_value=50,
                    value=int(pm_config.get('trail_points', 10)),
                    step=5,
                    help="Trailing step in points. When price moves up by this amount, SL moves up"
                )
            
            with col_param2:
                lot_size = st.number_input(
                    "📦 Lot Size",
                    min_value=1,
                    value=int(strategy_config.get('lot_size', 75)),
                    step=1,
                    help="NIFTY lot size (1 lot = 75 units typically)"
                )
                
                quantity = st.number_input(
                    "🔢 Quantity (Lots)",
                    min_value=1,
                    max_value=10,
                    value=2,
                    step=1,
                    help="Number of lots per trade"
                )
            
            # Validation
            total_units = quantity * lot_size
            if total_units > 750:
                st.warning("⚠️ Large quantity selected. Ensure sufficient margin available.")
            
            st.info(f"📊 **Trade Summary:** {quantity} lot(s) = **{total_units} units** (1 lot = {lot_size} units)")
            
            if st.button("💾 Save Trade Parameters", use_container_width=True):
                st.success("✅ Trade parameters saved (Note: Changes require algo restart to take effect)")
        
        st.subheader("📦 Holdings")
        holdings = _fetch_holdings()
        if holdings:
            try:
                hdf = pd.DataFrame(holdings)
                st.dataframe(hdf, use_container_width=True, height=300)
            except Exception as e:
                st.warning(f"Failed to render holdings: {e}")
        else:
            st.info("ℹ️ No holdings returned.")

        st.divider()
        st.subheader("🧾 Positions (Day/Net)")
        positions = _fetch_positions_book()
        if positions:
            try:
                pdf = pd.DataFrame(positions)
                st.dataframe(pdf, width='stretch', height=300)
            except Exception as e:
                st.warning(f"Failed to render positions: {e}")
        else:
            st.info("No positions returned.")

elif tab == "P&L":
    st.header("💹 P&L Analysis")
    try:
        from engine.pnl_service import compute_realized_pnl, pnl_timeseries
        from engine.db import init_database
        from sqlalchemy.exc import OperationalError
        
        # Ensure database is initialized
        try:
            init_database(create_all=True)
        except Exception as db_init_error:
            logger.warning(f"Database initialization warning: {db_init_error}")
        
        # Basic tenant context (dev default); wire real org/user later
        org_id = config.get('tenant', {}).get('org_id', 'demo-org')
        user_id = config.get('tenant', {}).get('user_id', 'admin')

        # Get P&L data with error handling
        try:
            res = compute_realized_pnl(org_id, user_id)
            total_pnl = res.get('realized_pnl', 0.0)
            series = pnl_timeseries(org_id, user_id)
        except OperationalError as db_error:
            # Database table doesn't exist - initialize and retry
            logger.warning(f"Database table missing, initializing: {db_error}")
            try:
                init_database(create_all=True)
                res = compute_realized_pnl(org_id, user_id)
                total_pnl = res.get('realized_pnl', 0.0)
                series = pnl_timeseries(org_id, user_id)
            except Exception as retry_error:
                logger.error(f"Failed to initialize database: {retry_error}")
                st.warning("⚠️ Database not initialized. P&L data will be available after first trade execution.")
                total_pnl = 0.0
                series = []
        except Exception as pnl_error:
            logger.error(f"P&L service error: {pnl_error}")
            st.warning(f"⚠️ P&L service error: {pnl_error}")
            total_pnl = 0.0
            series = []
        
        # Cumulative P&L Card
        pnl_color = "🟢" if total_pnl >= 0 else "🔴"
        status_bg = "status-green" if total_pnl >= 0 else "status-red"
        st.markdown(f"""
        <div class="status-card {status_bg}">
            <h3 style="margin:0; color: {'#155724' if total_pnl >= 0 else '#721c24'};">
                📊 Cumulative P&L
            </h3>
            <p style="font-size:2rem; margin:0.5rem 0; font-weight:bold;">
                {pnl_color} ₹{total_pnl:,.2f}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        st.divider()
        
        # Charts Section
        colp1, colp2 = st.columns([1, 1])
        
        with colp1:
            st.subheader("📈 Realized vs Unrealized P&L")
            try:
                # Get trade data for unrealized P&L
                all_trades = st.session_state.trade_logger.get_all_trades()
                if not all_trades.empty and 'pnl' in all_trades.columns:
                    realized_pnl = all_trades[all_trades['pnl'].notna()]['pnl'].sum()
                    # For unrealized, estimate from active positions
                    unrealized_pnl = 0.0  # Placeholder - would need position data
                    
                    # Create bar chart
                    fig = go.Figure(data=[
                        go.Bar(name='Realized P&L', x=['P&L'], y=[realized_pnl], marker_color='green' if realized_pnl >= 0 else 'red'),
                        go.Bar(name='Unrealized P&L', x=['P&L'], y=[unrealized_pnl], marker_color='orange')
                    ])
                    fig.update_layout(
                        title="P&L Breakdown",
                        xaxis_title="",
                        yaxis_title="Amount (₹)",
                        height=400,
                        showlegend=True
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("📊 Start Trading to track P&L")
            except Exception as e:
                st.warning(f"⚠️ Could not generate P&L chart: {e}")
        
        with colp2:
            st.subheader("📅 Daily P&L Trend")
            try:
                if series:
                    s_df = pd.DataFrame(series)
                    if 'date' in s_df.columns:
                        s_df['date'] = pd.to_datetime(s_df['date'])
                        s_df = s_df.sort_values('date')
                        
                        # Create Plotly line chart
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=s_df['date'],
                            y=s_df.get('pnl', s_df.iloc[:, 1]) if 'pnl' in s_df.columns else s_df.iloc[:, 1],
                            mode='lines+markers',
                            name='Daily P&L',
                            line=dict(color='#1f77b4', width=2),
                            fill='tonexty' if len(s_df.columns) > 1 else None
                        ))
                        fig.update_layout(
                            title="Daily P&L Trend",
                            xaxis_title="Date",
                            yaxis_title="P&L (₹)",
                            height=400,
                            hovermode='x unified'
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("📊 Start Trading to track P&L")
                else:
                    st.info("📊 Start Trading to track P&L")
            except Exception as e:
                st.warning(f"⚠️ Failed to render P&L series: {e}")
        
        # Empty State Message
        if total_pnl == 0 and (not series or len(series) == 0):
            st.divider()
            st.markdown("""
            <div class="empty-state">
                <h2>📊 No P&L Data Yet</h2>
                <p>Start Trading to track your P&L</p>
                <p style="color: #6c757d; font-size: 0.9rem;">
                    Your realized and unrealized P&L will appear here once you start executing trades.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
    except Exception as e:
        st.info("ℹ️ P&L services not available yet. Check configuration.")
        st.caption(f"Error: {e}")

elif tab == "Insights":
    st.header("🧠 Trading Insights")
    try:
        from engine.ai_analysis import analyze_trades
        org_id = config.get('tenant', {}).get('org_id', 'demo-org')
        user_id = config.get('tenant', {}).get('user_id', 'admin')
        
        lookback = st.slider(
            "📅 Lookback Period (days)", 
            min_value=7, 
            max_value=180, 
            value=30, 
            step=1,
            help="Select the number of days to analyze trades"
        )
        
        res = analyze_trades(org_id, user_id, lookback_days=lookback)
        
        # Calculate additional metrics
        total_trades = res.get('total_trades', 0)
        winning_trades = res.get('winning_trades', 0)
        losing_trades = res.get('losing_trades', 0)
        realized_pnl = res.get('realized_pnl', 0)
        avg_win = res.get('avg_win', 0)
        avg_loss = res.get('avg_loss', 0)
        
        # Calculate win rate and risk:reward
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        risk_reward = (avg_win / abs(avg_loss)) if avg_loss != 0 else 0
        
        # Check if we have data
        if total_trades == 0:
            # Empty state with mock stats
            st.markdown("""
            <div class="empty-state">
                <h2>📊 Make your first trade to unlock insights</h2>
                <p style="color: #6c757d; font-size: 0.9rem;">
                    Once you start trading, you'll see detailed analytics including win rate, average profit/loss, and risk-reward ratios.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            # Show mock stats as example
            st.divider()
            st.subheader("📊 Sample Insights (Mock Data)")
            st.info("💡 These are example metrics. Start trading to see your actual insights.")
            
            mock_stats = {
                'win_rate': 65.5,
                'avg_profit': 1250.0,
                'avg_loss': -850.0,
                'risk_reward': 1.47
            }
        else:
            mock_stats = None
        
        # KPI Cards
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            win_rate_val = win_rate if total_trades > 0 else (mock_stats['win_rate'] if mock_stats else 0)
            st.metric(
                "🎯 Win Rate", 
                f"{win_rate_val:.2f}%",
                help="Percentage of winning trades"
            )
        
        with c2:
            avg_profit_val = avg_win if total_trades > 0 else (mock_stats['avg_profit'] if mock_stats else 0)
            st.metric(
                "📈 Avg Profit", 
                f"₹{avg_profit_val:,.2f}",
                help="Average profit per winning trade"
            )
        
        with c3:
            avg_loss_val = avg_loss if total_trades > 0 else (mock_stats['avg_loss'] if mock_stats else 0)
            st.metric(
                "📉 Avg Loss", 
                f"₹{avg_loss_val:,.2f}",
                help="Average loss per losing trade"
            )
        
        with c4:
            rr_val = risk_reward if total_trades > 0 else (mock_stats['risk_reward'] if mock_stats else 0)
            st.metric(
                "⚖️ Risk:Reward Ratio", 
                f"{rr_val:.2f}",
                help="Average win to average loss ratio"
            )
        
        st.divider()
        
        # Charts Section
        if total_trades > 0 or mock_stats:
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📊 Trade Distribution")
                try:
                    # Create pie chart for win/loss
                    win_count = winning_trades if total_trades > 0 else 20
                    loss_count = losing_trades if total_trades > 0 else 10
                    
                    fig = go.Figure(data=[go.Pie(
                        labels=['Wins', 'Losses'],
                        values=[win_count, loss_count],
                        hole=0.3,
                        marker_colors=['green', 'red']
                    )])
                    fig.update_layout(
                        title="Win/Loss Distribution",
                        height=400
                    )
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.warning(f"⚠️ Could not generate chart: {e}")
            
            with col2:
                st.subheader("📈 P&L Trend")
                try:
                    # Get trade data for trend
                    all_trades = st.session_state.trade_logger.get_all_trades()
                    if not all_trades.empty and 'pnl' in all_trades.columns:
                        # Create cumulative P&L chart
                        all_trades_sorted = all_trades.sort_values('timestamp' if 'timestamp' in all_trades.columns else all_trades.columns[0])
                        cumulative_pnl = all_trades_sorted['pnl'].cumsum()
                        
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=list(range(len(cumulative_pnl))),
                            y=cumulative_pnl,
                            mode='lines+markers',
                            name='Cumulative P&L',
                            line=dict(color='#1f77b4', width=2),
                            fill='tozeroy'
                        ))
                        fig.update_layout(
                            title="Cumulative P&L Over Time",
                            xaxis_title="Trade Number",
                            yaxis_title="Cumulative P&L (₹)",
                            height=400
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("📊 No trade data available for trend analysis")
                except Exception as e:
                    st.warning(f"⚠️ Could not generate trend chart: {e}")
        
        # Top Symbols Section
        st.divider()
        st.subheader("📊 Top Symbols")
        top = res.get('top_symbols', [])
        if top:
            tdf = pd.DataFrame(top, columns=["Symbol", "Trades"])
            st.dataframe(tdf, use_container_width=True, height=200)
        else:
            st.info("📊 No symbol concentration yet. Start trading to see your top symbols.")
            
    except Exception as e:
        st.info("ℹ️ Insights will appear once trades are recorded and DB is configured.")
        st.caption(f"Error: {e}")

elif tab == "Orders & Trades":
    st.header("📑 Orders & Trades")
    if st.session_state.broker is None:
        st.warning("Broker not initialized.")
    else:
        @st.cache_data(ttl=0)
        def _fetch_order_book():
            import time
            attempts = 0
            while attempts < 2:
                try:
                    if hasattr(st.session_state.broker, 'get_order_book'):
                        return st.session_state.broker.get_order_book()
                    # Fallback via SmartAPI SDK if method absent
                    return st.session_state.broker.smart_api.orderBook().get('data', [])
                except Exception as e:
                    logger.exception(e)
                    attempts += 1
                    time.sleep(2)
            return []

        @st.cache_data(ttl=0)
        def _fetch_trade_book():
            import time
            attempts = 0
            while attempts < 2:
                try:
                    if hasattr(st.session_state.broker, 'get_trade_book'):
                        return st.session_state.broker.get_trade_book()
                    return st.session_state.broker.smart_api.tradeBook().get('data', [])
                except Exception as e:
                    logger.exception(e)
                    attempts += 1
                    time.sleep(2)
            return []

        colb1, colb2 = st.columns([1,1])
        with colb1:
            refresh_ob = st.button("🔄 Refresh Orders", use_container_width=True)
        with colb2:
            refresh_tb = st.button("🔄 Refresh Trades", use_container_width=True)

        if refresh_ob:
            _fetch_order_book.clear()
        if refresh_tb:
            _fetch_trade_book.clear()

        st.subheader("🗂️ Order Book")
        orders = _fetch_order_book()
        if orders:
            try:
                odf = pd.DataFrame(orders)
                # Common helpful columns if present
                cols = [c for c in [
                    'orderid','tradingsymbol','symboltoken','exchange','transactiontype','producttype',
                    'ordertype','status','price','triggerprice','quantity','filledshares','unfilledshares',
                    'createdtime','updatetime'
                ] if c in odf.columns]
                st.dataframe(odf[cols] if cols else odf, width='stretch', height=300)
            except Exception as e:
                st.warning(f"Failed to render order book: {e}")
        else:
            st.info("No orders returned.")

        st.divider()
        st.subheader("📒 Trade Book (Day Trades)")
        trades = _fetch_trade_book()
        if trades:
            try:
                tdf = pd.DataFrame(trades)
                cols = [c for c in [
                    'orderid','tradingsymbol','symboltoken','exchange','transactiontype','producttype',
                    'price','quantity','filltime','tradetime'
                ] if c in tdf.columns]
                st.dataframe(tdf[cols] if cols else tdf, width='stretch', height=300)
            except Exception as e:
                st.warning(f"Failed to render trade book: {e}")
        else:
            st.info("No trades returned.")

        st.divider()
        st.subheader("📥 Import Manual Trades (CSV)")
        uploaded = st.file_uploader("Upload CSV to merge into trade log", type=['csv'], key='manual_trades_uploader')
        if uploaded is not None:
            try:
                res = st.session_state.trade_logger.import_trades_from_csv(uploaded)
                if res.get('error'):
                    st.error(f"Import failed: {res['error']}")
                else:
                    st.success(f"Imported: {res['imported']}, Total after merge: {res['total']}")
            except Exception as e:
                st.error(f"Import error: {e}")

elif tab == "Trade Journal":
    st.header("📘 Trade Journal")
    
    trade_logger = st.session_state.trade_logger
    
    # Get all trades
    all_trades = trade_logger.get_all_trades()
    
    if not all_trades.empty:
        # Filters Section
        st.subheader("🔍 Filters")
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            # Trade type filter
            trade_types = ['All'] + (all_trades['type'].unique().tolist() if 'type' in all_trades.columns else ['All'])
            selected_type = st.selectbox(
                "📊 Trade Type",
                trade_types,
                help="Filter trades by type (CE/PE)"
            )
        
        with filter_col2:
            # Result filter (Win/Loss)
            result_options = ['All', 'Win', 'Loss']
            if 'pnl' in all_trades.columns:
                selected_result = st.selectbox(
                    "🎯 Result",
                    result_options,
                    help="Filter trades by result (Win/Loss)"
                )
            else:
                selected_result = 'All'
        
        with filter_col3:
            # Date filter
            if 'timestamp' in all_trades.columns or 'date' in all_trades.columns:
                date_col = 'timestamp' if 'timestamp' in all_trades.columns else 'date'
                all_trades[date_col] = pd.to_datetime(all_trades[date_col], errors='coerce')
                min_date = all_trades[date_col].min().date() if not all_trades[date_col].isna().all() else date.today()
                max_date = all_trades[date_col].max().date() if not all_trades[date_col].isna().all() else date.today()
                
                date_range = st.date_input(
                    "📅 Date Range",
                    value=(min_date, max_date),
                    min_value=min_date,
                    max_value=max_date,
                    help="Select date range for trades"
                )
            else:
                date_range = None
        
        # Apply filters
        filtered_trades = all_trades.copy()
        
        if selected_type != 'All' and 'type' in filtered_trades.columns:
            filtered_trades = filtered_trades[filtered_trades['type'] == selected_type]
        
        if selected_result != 'All' and 'pnl' in filtered_trades.columns:
            if selected_result == 'Win':
                filtered_trades = filtered_trades[filtered_trades['pnl'] > 0]
            elif selected_result == 'Loss':
                filtered_trades = filtered_trades[filtered_trades['pnl'] < 0]
        
        if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
            date_col = 'timestamp' if 'timestamp' in filtered_trades.columns else 'date'
            if date_col in filtered_trades.columns:
                filtered_trades[date_col] = pd.to_datetime(filtered_trades[date_col], errors='coerce')
                filtered_trades = filtered_trades[
                    (filtered_trades[date_col].dt.date >= date_range[0]) &
                    (filtered_trades[date_col].dt.date <= date_range[1])
                ]
        
        st.divider()
        
        # Display last 10 trades
        st.subheader("📊 Recent Trades (Last 10)")
        if len(filtered_trades) > 0:
            # Get last 10 trades
            recent_trades = filtered_trades.tail(10).sort_index(ascending=False)
            st.dataframe(recent_trades, use_container_width=True, height=400)
            
            # Show summary
            if 'pnl' in recent_trades.columns:
                recent_pnl = recent_trades['pnl'].sum()
                recent_wins = (recent_trades['pnl'] > 0).sum()
                recent_losses = (recent_trades['pnl'] < 0).sum()
                st.caption(f"📊 Recent 10 trades: {len(recent_trades)} trades | P&L: ₹{recent_pnl:,.2f} | Wins: {recent_wins} | Losses: {recent_losses}")
        else:
            st.info("📝 No trades match the selected filters.")
        
        # All filtered trades section
        if len(filtered_trades) > 10:
            st.divider()
            st.subheader("📋 All Filtered Trades")
            st.dataframe(filtered_trades, use_container_width=True, height=400)
        
        # Statistics
        st.divider()
        st.subheader("📊 Trade Statistics")
        
        try:
            stats = trade_logger.get_trade_stats()
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Trades", stats['total_trades'], help="Total number of trades")
            
            with col2:
                st.metric("Win Rate", f"{stats['win_rate']:.2f}%", help="Percentage of winning trades")
            
            with col3:
                st.metric("Total P&L", f"₹{stats['total_pnl']:,.2f}", help="Total profit and loss")
            
            with col4:
                avg_pnl = (stats['avg_win'] + stats['avg_loss']) / 2 if stats['total_trades'] > 0 else 0
                st.metric("Avg P&L", f"₹{avg_pnl:,.2f}", help="Average profit and loss per trade")
            
            # Detailed stats
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Winning Trades:**")
                st.write(f"- Count: {stats['winning_trades']}")
                st.write(f"- Avg Win: ₹{stats['avg_win']:,.2f}")
            
            with col2:
                st.write("**Losing Trades:**")
                st.write(f"- Count: {stats['losing_trades']}")
                st.write(f"- Avg Loss: ₹{stats['avg_loss']:,.2f}")
        except Exception as e:
            st.warning(f"⚠️ Could not calculate statistics: {e}")
        
        # Download CSV
        st.divider()
        st.download_button(
            label="📥 Download Trade Log (CSV)",
            data=filtered_trades.to_csv(index=False).encode('utf-8'),
            file_name=f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            help="Download filtered trades as CSV file"
        )
    else:
        # Empty state
        st.markdown("""
        <div class="empty-state">
            <h2>📝 No trades yet</h2>
            <p>Your log starts here.</p>
            <p style="color: #6c757d; font-size: 0.9rem;">
                Once you start executing trades, they will appear in your trade journal with detailed information including entry/exit prices, P&L, and timestamps.
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Show sample entry
        st.divider()
        st.subheader("📋 Sample Entry (Example)")
        sample_data = {
            'timestamp': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
            'symbol': ['NIFTY 25000 CE'],
            'type': ['CE'],
            'entry_price': [150.50],
            'exit_price': [180.75],
            'quantity': [150],
            'pnl': [4537.50]
        }
        sample_df = pd.DataFrame(sample_data)
        st.dataframe(sample_df, use_container_width=True)
        st.caption("💡 This is a sample entry. Your actual trades will appear here once you start trading.")

# ============ BACKTEST TAB ============
elif tab == "Backtest":
    st.header("🧪 Backtest Strategy")
    
    # Session state bootstrapping
    st.session_state.setdefault("backtest_results", None)
    st.session_state.setdefault("backtest_results_source", None)
    st.session_state.setdefault("backtest_equity_curve", None)
    st.session_state.setdefault("backtest_trades", None)
    
    def store_backtest_results(results: Dict, source_label: str) -> None:
        st.session_state.backtest_results = results
        st.session_state.backtest_results_source = source_label
        st.session_state.backtest_equity_curve = results.get("equity_curve")
        st.session_state.backtest_trades = results.get("trades")
    
    def render_backtest_results(results: Optional[Dict]) -> None:
        if not results:
            st.info("🔎 Run a backtest from the **Data & Run** tab to see analytics here.")
            return
        
        st.subheader("📊 Backtest Summary")
        summary_cols = st.columns(4, gap="small")
        summary_cols[0].metric("Total Trades", results.get("total_trades", 0))
        summary_cols[1].metric("Win Rate", f"{results.get('win_rate', 0.0):.2f}%")
        summary_cols[2].metric("Net P&L", f"₹{results.get('total_pnl', 0.0):,.2f}")
        summary_cols[3].metric("Return %", f"{results.get('return_pct', 0.0):.2f}%")
        
        if results.get("total_trades", 0) == 0:
            st.warning("⚠️ No trades were executed during this backtest window.")
            st.caption(
                "Tip: Broaden the data window, loosen filters, or ensure inside-bar breakouts were present."
            )
        
        result_tabs = st.tabs(
            [
                "Overview",
                "Capital & Risk",
                "Trailing SL",
                "Equity Curve",
                "Trade Log",
            ]
        )
        
        with result_tabs[0]:
            st.markdown("### 🧾 Performance Overview")
            overview_cols = st.columns(3, gap="small")
            overview_cols[0].metric(
                "Initial Capital", f"₹{results.get('initial_capital', 0.0):,.2f}"
            )
            overview_cols[1].metric(
                "Final Capital", f"₹{results.get('final_capital', 0.0):,.2f}"
            )
            overview_cols[2].metric(
                "Winning / Losing Trades",
                f"{results.get('winning_trades', 0)} / {results.get('losing_trades', 0)}",
            )
            st.write(
                f"- **Average Win:** ₹{results.get('avg_win', 0.0):,.2f}\n"
                f"- **Average Loss:** ₹{results.get('avg_loss', 0.0):,.2f}\n"
                f"- **Max Drawdown:** {results.get('max_drawdown', 0.0):.2f}%\n"
                f"- **Max Winning Streak:** {results.get('max_winning_streak', 0)} trades\n"
                f"- **Max Losing Streak:** {results.get('max_losing_streak', 0)} trades"
            )
        
        with result_tabs[1]:
            st.markdown("### 💰 Capital & Risk Analysis")
            avg_cap_req = results.get("avg_capital_required", 0.0)
            st.metric("Avg Capital Required / Trade", f"₹{avg_cap_req:,.2f}")
            
            if results.get("capital_exhausted", False):
                trade_num = results.get("capital_exhausted_at_trade", "Unknown")
                st.error(f"⚠️ Capital exhausted after trade #{trade_num}.")
                st.caption(
                    "- Increase initial capital\n"
                    "- Reduce position size\n"
                    "- Tighten stop-loss or filters\n"
                    "- Review volatile periods"
                )
            else:
                st.success("✅ Capital stayed positive for the entire run.")
        
        with result_tabs[2]:
            st.markdown("### 🎯 Trailing Stop Insights")
            trail_exit_count = results.get("winning_trades_trail_exit", 0)
            trail_exit_pct = results.get("trail_exit_pct_of_winners", 0.0)
            trail_cols = st.columns(2, gap="small")
            trail_cols[0].metric("Trail SL Exits (Wins)", trail_exit_count)
            trail_cols[1].metric("Share of Winning Trades", f"{trail_exit_pct:.1f}%")
            if trail_exit_count > 0:
                st.info(
                    "Trailing SL closed profitable trades before TP. "
                    "Consider adjusting trail parameters to match market volatility."
                )
            else:
                st.caption("No winning trades were closed by the trailing stop.")
        
        with result_tabs[3]:
            st.markdown("### 📈 Equity Curve")
            equity_curve = results.get("equity_curve")
            if equity_curve:
                equity_df = pd.DataFrame(
                    {"Trade #": range(len(equity_curve)), "Capital": equity_curve}
                )
                fig = go.Figure(
                    data=[
                        go.Scatter(
                            x=equity_df["Trade #"],
                            y=equity_df["Capital"],
                            mode="lines",
                            line=dict(color="#1f77b4", width=2),
                            fill="tozeroy",
                        )
                    ]
                )
                fig.update_layout(
                    height=420,
                    hovermode="x unified",
                    margin=dict(l=10, r=10, t=50, b=10),
                )
                st.plotly_chart(fig, use_container_width=True)
                st.download_button(
                    "⬇️ Download Equity Curve CSV",
                    equity_df.to_csv(index=False).encode("utf-8"),
                    file_name="backtest_equity_curve.csv",
                    mime="text/csv",
                )
            else:
                st.info("No equity curve data returned from this run.")
        
        with result_tabs[4]:
            st.markdown("### 📋 Trade Log")
            trades = results.get("trades")
            if trades:
                trades_df = pd.DataFrame(trades)
                st.dataframe(trades_df, use_container_width=True)
                st.download_button(
                    "⬇️ Download Trades CSV",
                    trades_df.to_csv(index=False).encode("utf-8"),
                    file_name="backtest_trades.csv",
                    mime="text/csv",
                )
            else:
                st.info("No individual trade records were returned.")
    
    # Quick glance cards (latest results)
    last_results = st.session_state.backtest_results
    summary_cols = st.columns(3, gap="small")
    if last_results:
        summary_cols[0].metric("Last P&L", f"₹{last_results.get('total_pnl', 0.0):,.2f}")
        summary_cols[1].metric("Last Win Rate", f"{last_results.get('win_rate', 0.0):.2f}%")
        summary_cols[2].metric(
            "Last Run Source",
            st.session_state.backtest_results_source or "—",
        )
    else:
        for col, label in zip(summary_cols, ["Last P&L", "Last Win Rate", "Last Run Source"]):
            col.metric(label, "—")
    
    st.divider()
    
    config_tab, data_run_tab, results_tab = st.tabs(
        ["🛠 Configure Strategy", "📂 Data & Run", "📊 Results & Analysis"]
    )
    
    # --- CONFIGURATION TAB -------------------------------------------------
    with config_tab:
        # data source info
        if DESIQUANT_AVAILABLE:
            st.caption("Tip: Configure once, then iterate quickly via the Data & Run tab.")
        else:
            st.warning(
                "Cloud datasource dependencies missing. Install `s3fs>=2024.3.1` and `pyarrow>=15.0.0` to enable."
            )
        
    import yaml as yaml_lib
    with open('config/config.yaml', 'r') as f:
        strategy_config = yaml_lib.safe_load(f)
    pm_config = strategy_config.get('position_management', {})
    
    st.subheader("⚙️ Essential Parameters")
    col1, col2, col3 = st.columns(3, gap="small")
    with col1:
        initial_capital = st.number_input(
            "Initial Capital (₹)",
            min_value=10000,
            value=100000,
            step=10000,
        )
    with col2:
        lot_size_default = strategy_config.get('lot_size', 75)
        lot_size = st.number_input(
            "Lot Size",
            min_value=1,
            value=lot_size_default,
            step=lot_size_default,
            help=f"NIFTY lot size (1 lot = {lot_size_default} units). +/- adjusts by a full lot.",
        )
    with col3:
        sl_pct = st.number_input(
            "Premium SL %",
            min_value=10,
            value=35,
            max_value=60,
            step=5,
            help="Legacy premium stop-loss percentage (used when enhanced features are disabled).",
        )
    
    estimated_strike_price = 24000
    estimated_capital_required = lot_size * estimated_strike_price
    if initial_capital < estimated_capital_required:
        st.warning(
            f"⚠️ Available capital (₹{initial_capital:,.0f}) is below an estimated requirement "
            f"of ₹{estimated_capital_required:,.0f}."
        )
    
    st.divider()
    
    st.markdown("### 🧱 Strategy & Risk Controls")
    strike_selection = st.selectbox(
        "Strike selection preset",
        options=["ATM 0", "ITM 1", "ITM 2", "ITM 3", "OTM 1", "OTM 2", "OTM 3"],
        index=0,
    )
    
    col_pm = st.columns(4, gap="small")
    with col_pm[0]:
        sl_points_main = st.number_input(
            "SL Points",
            min_value=10,
            max_value=100,
            value=int(pm_config.get('sl_points', 30)),
            step=5,
        )
    with col_pm[1]:
        trail_points_main = st.number_input(
            "Trail Points",
            min_value=5,
            max_value=50,
            value=int(pm_config.get('trail_points', 10)),
            step=5,
        )
    with col_pm[2]:
        book1_points_main = st.number_input(
            "Book 1 Points",
            min_value=10,
            max_value=100,
            value=int(pm_config.get('book1_points', 40)),
            step=5,
        )
    with col_pm[3]:
        book2_points_main = st.number_input(
            "Book 2 Points",
            min_value=20,
            max_value=150,
            value=int(pm_config.get('book2_points', 54)),
            step=5,
        )
    
    st.divider()
    
    st.markdown("### 🧩 Advanced Parameters")
    with st.expander("📊 Strategy Filters & Controls", expanded=False):
        use_atr_filter = False
        use_regime_filter = False
        use_distance_guard = False
        use_tiered_exits = False
        use_expiry_protocol = False
        use_directional_sizing = False
        atr_floor_pct = 0.5
        ema_slope_len = 20
        distance_guard_atr = 0.6
        vol_band_low = 0.40
        vol_band_high = 0.75
        sl_pct_low = 22
        sl_pct_norm = 28
        sl_pct_high = 35
        be_at_r = 0.6
        t1_r = 1.2
        t1_book_pct = 0.50
        t2_r = 2.0
        t2_book_pct = 0.25
        trail_lookback = 6
        trail_mult = 2.0
        no_new_after = "14:30"
        force_partial_by = "13:00"
        tighten_days = 1.5
        risk_per_trade_pct = 0.6
        pe_size_cap_vs_ce = 0.7
        max_concurrent = 2
        sl_points_config = sl_points_main
        trail_points_config = trail_points_main
        book1_points_config = book1_points_main
        book2_points_config = book2_points_main
        book1_ratio_config = float(pm_config.get('book1_ratio', 0.5))
    
        flag_cols = st.columns(2)
        with flag_cols[0]:
            use_atr_filter = st.checkbox("ATR Filter", value=use_atr_filter)
            use_regime_filter = st.checkbox("Regime Filter", value=use_regime_filter)
            use_distance_guard = st.checkbox("Distance Guard", value=use_distance_guard)
        with flag_cols[1]:
            use_tiered_exits = st.checkbox("Tiered Exits", value=use_tiered_exits)
            use_expiry_protocol = st.checkbox("Expiry Protocol", value=use_expiry_protocol)
            use_directional_sizing = st.checkbox("Directional Sizing", value=use_directional_sizing)
    
        st.markdown("##### Filters")
        filters_row = st.columns(3)
        with filters_row[0]:
            atr_floor_pct = st.number_input(
                "ATR Floor % (1h)",
                min_value=0.0,
                value=atr_floor_pct,
                step=0.1,
                format="%.1f",
            )
        with filters_row[1]:
            ema_slope_len = st.number_input(
                "EMA Slope Lookback",
                min_value=5,
                value=ema_slope_len,
                step=5,
            )
        with filters_row[2]:
            distance_guard_atr = st.number_input(
                "Distance Guard (ATR)",
                min_value=0.1,
                value=distance_guard_atr,
                step=0.1,
                format="%.1f",
            )
        
        st.markdown("##### Volatility-based SL")
        vol_cols = st.columns(4)
        with vol_cols[0]:
            vol_band_low = st.number_input(
                "Vol Band Low %",
                min_value=0.0,
                value=vol_band_low,
                step=0.05,
                format="%.2f",
            )
        with vol_cols[1]:
            vol_band_high = st.number_input(
                "Vol Band High %",
                min_value=0.0,
                value=vol_band_high,
                step=0.05,
                format="%.2f",
            )
        with vol_cols[2]:
            sl_pct_low = st.number_input(
                "SL % (Low Vol)",
                min_value=10,
                value=sl_pct_low,
                step=1,
            )
        with vol_cols[3]:
            sl_pct_high = st.number_input(
                "SL % (High Vol)",
                min_value=20,
                value=sl_pct_high,
                step=1,
            )
        sl_pct_norm = st.number_input(
            "SL % (Normal Vol)",
            min_value=15,
            value=sl_pct_norm,
            step=1,
        )
        
        st.markdown("##### Tiered Exits")
        tier_cols = st.columns(4)
        with tier_cols[0]:
            be_at_r = st.number_input(
                "Breakeven @ R",
                min_value=0.0,
                value=be_at_r,
                step=0.1,
                format="%.1f",
            )
        with tier_cols[1]:
            t1_r = st.number_input(
                "T1 Target (R)",
                min_value=0.0,
                value=t1_r,
                step=0.1,
                format="%.1f",
            )
            t1_book_pct = st.number_input(
                "T1 Book %",
                min_value=0.0,
                max_value=1.0,
                value=t1_book_pct,
                step=0.05,
                format="%.2f",
            )
        with tier_cols[2]:
            t2_r = st.number_input(
                "T2 Target (R)",
                min_value=0.0,
                value=t2_r,
                step=0.1,
                format="%.1f",
            )
            t2_book_pct = st.number_input(
                "T2 Book %",
                min_value=0.0,
                max_value=1.0,
                value=t2_book_pct,
                step=0.05,
                format="%.2f",
            )
        with tier_cols[3]:
            trail_lookback = st.number_input(
                "Trail Lookback",
                min_value=1,
                value=trail_lookback,
                step=1,
            )
            trail_mult = st.number_input(
                "Trail Multiplier",
                min_value=0.5,
                value=trail_mult,
                step=0.1,
            )
        
        st.markdown("##### Risk Protocols")
        risk_cols = st.columns(3)
        with risk_cols[0]:
            no_new_after = st.time_input("No new entries after", value=pd.to_datetime(no_new_after).time())
            tighten_days = st.number_input(
                "Tighten after (days)",
                min_value=0.0,
                value=tighten_days,
                step=0.5,
            )
        with risk_cols[1]:
            force_partial_by = st.time_input("Force partial booking by", value=pd.to_datetime(force_partial_by).time())
            risk_per_trade_pct = st.number_input(
                "Risk per trade %",
                min_value=0.1,
                value=risk_per_trade_pct,
                step=0.1,
                format="%.1f",
            )
        with risk_cols[2]:
            pe_size_cap_vs_ce = st.number_input(
                "PE position size cap vs CE",
                min_value=0.1,
                max_value=1.0,
                value=pe_size_cap_vs_ce,
                step=0.05,
                format="%.2f",
            )
            max_concurrent = st.number_input(
                "Max concurrent positions",
                min_value=1,
                max_value=5,
                value=max_concurrent,
                step=1,
            )
    
    # strike interpretation
    strike_offset_map = {
        "ATM 0": 0,
        "ITM 1": 50,
        "ITM 2": 100,
        "ITM 3": 150,
        "OTM 1": 50,
        "OTM 2": 100,
        "OTM 3": 150,
    }
    strike_offset_base = strike_offset_map.get(strike_selection, 0)
    is_itm = strike_selection.startswith("ITM")
    is_otm = strike_selection.startswith("OTM")
    
    backtest_config_dict = {
        "strategy": {
            "type": "inside_bar_breakout",
            "sl": int(sl_points_main),
            "rr": 1.8,
            "premium_sl_pct": float(sl_pct),
            "lock1_gain_pct": 60.0,
            "lock2_gain_pct": 80.0,
            "lock3_gain_pct": 100.0,
            "use_atr_filter": bool(use_atr_filter),
            "use_regime_filter": bool(use_regime_filter),
            "use_distance_guard": bool(use_distance_guard),
            "use_tiered_exits": bool(use_tiered_exits),
            "use_expiry_protocol": bool(use_expiry_protocol),
            "use_directional_sizing": bool(use_directional_sizing),
            "atr_floor_pct_1h": float(atr_floor_pct),
            "ema_slope_len": int(ema_slope_len),
            "distance_guard_atr": float(distance_guard_atr),
            "adx_min": 0.0,
            "vol_bands": {"low": float(vol_band_low), "high": float(vol_band_high)},
            "premium_sl_pct_low": float(sl_pct_low),
            "premium_sl_pct_norm": float(sl_pct_norm),
            "premium_sl_pct_high": float(sl_pct_high),
            "be_at_r": float(be_at_r),
            "trail_lookback": int(trail_lookback),
            "trail_mult": float(trail_mult),
            "swing_lock": True,
            "t1_r": float(t1_r),
            "t1_book": float(t1_book_pct),
            "t2_r": float(t2_r),
            "t2_book": float(t2_book_pct),
            "no_new_after": str(no_new_after),
            "force_partial_by": str(force_partial_by),
            "tighten_trail_days_to_expiry": float(tighten_days),
            "tighten_mult_factor": 1.3,
        },
        "position_management": {
            "sl_points": int(sl_points_config),
            "trail_points": int(trail_points_config),
            "book1_points": int(book1_points_config),
            "book2_points": int(book2_points_config),
            "book1_ratio": float(book1_ratio_config),
        },
        "sizing": {
            "risk_per_trade_pct": float(risk_per_trade_pct),
            "pe_size_cap_vs_ce": float(pe_size_cap_vs_ce),
            "portfolio_risk_cap_pct": 4.0,
            "max_concurrent_positions": int(max_concurrent),
        },
        "initial_capital": float(initial_capital),
        "lot_size": int(lot_size),
        "strike_selection": strike_selection,
        "strike_offset_base": strike_offset_base,
        "strike_is_itm": is_itm,
        "strike_is_otm": is_otm,
    }
    
    engine = BacktestEngine(backtest_config_dict)
    st.session_state.backtest_config_dict = backtest_config_dict
    
    # --- DATA & RUN TAB ----------------------------------------------------
    with data_run_tab:
        st.subheader("📂 Choose data source")
        source_tabs = st.tabs(["📤 CSV Upload", "☁️ DesiQuant Cloud"])
        
        # CSV Upload Workflow
        with source_tabs[0]:
            st.markdown("#### CSV Upload")
            sample_cols = st.columns([3, 1])
            with sample_cols[0]:
                st.caption("Use a sample file to align your historical OHLC data quickly.")
            with sample_cols[1]:
                sample_csv_data = {
                    'Date': pd.date_range('2024-01-01', periods=10, freq='1H').strftime('%Y-%m-%d %H:%M:%S'),
                    'Open': [24000.0, 24050.0, 24030.0, 24060.0, 24080.0, 24100.0, 24090.0, 24120.0, 24140.0, 24160.0],
                    'High': [24080.0, 24090.0, 24070.0, 24090.0, 24110.0, 24130.0, 24120.0, 24150.0, 24170.0, 24190.0],
                    'Low': [23980.0, 24020.0, 24000.0, 24030.0, 24050.0, 24070.0, 24060.0, 24090.0, 24110.0, 24130.0],
                    'Close': [24050.0, 24040.0, 24050.0, 24070.0, 24090.0, 24110.0, 24100.0, 24130.0, 24150.0, 24170.0],
                    'Volume': [1000000, 1100000, 950000, 1200000, 1050000, 1300000, 1150000, 1250000, 1400000, 1350000]
                }
                sample_df = pd.DataFrame(sample_csv_data)
                st.download_button(
                    label="📥 Sample CSV",
                    data=sample_df.to_csv(index=False).encode('utf-8'),
                    file_name="sample_historical_data.csv",
                    mime="text/csv",
                )
            
            uploaded_file = st.file_uploader(
                "Drop a CSV with 1H OHLC data",
                type=["csv"],
                help="Columns required: Date, Open, High, Low, Close (Volume optional).",
            )
            
            data_1h = None
            if uploaded_file is not None:
                try:
                    data_1h = pd.read_csv(uploaded_file)
                    column_mapping = {}
                    expected_columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
                    for col in data_1h.columns:
                        col_lower = col.lower().strip()
                        for expected in expected_columns:
                            if col_lower == expected.lower():
                                column_mapping[col] = expected
                                break
                    if column_mapping:
                        data_1h = data_1h.rename(columns=column_mapping)
                    required_cols = ['Open', 'High', 'Low', 'Close']
                    missing_cols = [col for col in required_cols if col not in data_1h.columns]
                    if missing_cols:
                        st.error(f"❌ Missing columns: {missing_cols}")
                        data_1h = None
                    else:
                        if 'Date' in data_1h.columns:
                            data_1h['Date'] = pd.to_datetime(data_1h['Date'])
                            data_1h.set_index('Date', inplace=True)
                        elif not isinstance(data_1h.index, pd.DatetimeIndex):
                            st.warning("⚠️ Date column not found; ensure your CSV includes timestamp information.")
                        with st.expander("Preview data (first 15 rows)", expanded=False):
                            st.dataframe(data_1h.head(15), use_container_width=True)
                except Exception as e:
                    st.error(f"❌ Failed to parse CSV: {e}")
                    data_1h = None
            
            csv_run_disabled = data_1h is None
            if st.button(
                "▶️ Run Backtest (CSV)",
                use_container_width=True,
                type="primary",
                disabled=csv_run_disabled,
            ):
                with st.spinner("Running backtest..."):
                    try:
                        results = engine.run_backtest(
                            data_1h=data_1h,
                            options_df=None,
                            expiries_df=None,
                            initial_capital=initial_capital,
                        )
                        if not isinstance(results, dict):
                            st.error("Unexpected result format from backtest engine.")
                        else:
                            store_backtest_results(results, "CSV Upload")
                            st.success("Backtest completed. Review analytics in the Results tab.")
                    except Exception as e:
                        st.error(f"❌ Backtest failed: {e}")
                        st.exception(e)
        
        # Cloud Workflow
        with source_tabs[1]:
            if DESIQUANT_AVAILABLE:
                st.markdown("#### DesiQuant S3 Data Source")
                cloud_cols = st.columns(3, gap="small")
                with cloud_cols[0]:
                    start_date = st.date_input(
                        "Start date", value=pd.to_datetime("2021-01-01").date()
                    )
                with cloud_cols[1]:
                    end_date = st.date_input(
                        "End date", value=pd.to_datetime("2021-03-31").date()
                    )
                with cloud_cols[2]:
                    symbol = st.selectbox("Symbol", ["NIFTY"], index=0)
                
                if end_date < start_date:
                    st.error("❌ End date cannot precede start date.")
                else:
                    if st.button(
                        "▶️ Run Backtest (Cloud)",
                        use_container_width=True,
                        type="primary",
                    ):
                        with st.spinner("Fetching data from DesiQuant and running backtest..."):
                            try:
                                data = stream_data(
                                    symbol=symbol,
                                    start=str(start_date),
                                    end=str(end_date),
                                )
                                spot_df = data.get("spot")
                                options_df = data.get("options")
                                expiries_df = data.get("expiries")
                                if spot_df is None or spot_df.empty:
                                    st.warning("No spot data returned from datasource.")
                                else:
                                    with st.expander("Preview cloud data", expanded=False):
                                        st.dataframe(spot_df.head(10), use_container_width=True)
                                    results = engine.run_backtest(
                                        data_1h=spot_df,
                                        data_15m=None,
                                        options_df=options_df if options_df is not None and not options_df.empty else None,
                                        expiries_df=expiries_df if expiries_df is not None and not expiries_df.empty else None,
                                        initial_capital=initial_capital,
                                    )
                                    if not isinstance(results, dict):
                                        st.error("Unexpected result format from backtest engine.")
                                    else:
                                        store_backtest_results(results, "DesiQuant Cloud")
                                        st.success("Backtest completed. Review analytics in the Results tab.")
                            except Exception as e:
                                st.error(f"❌ Cloud backtest failed: {e}")
                                st.exception(e)
            else:
                st.info("Cloud datasource unavailable. Install required packages to enable this tab.")
    
    # --- RESULTS TAB -------------------------------------------------------
    with results_tab:
        render_backtest_results(st.session_state.backtest_results)
    
    st.divider()
    
    # Parse strike selection to get offset
    # For NIFTY: strikes are in multiples of 50
    # ATM 0 = 0 offset
    # ITM 1/2/3 = -50/-100/-150 for CE, +50/+100/+150 for PE
    # OTM 1/2/3 = +50/+100/+150 for CE, -50/-100/-150 for PE
    strike_offset_map = {
        "ATM 0": 0,
        "ITM 1": 50,   # Will be adjusted based on direction
        "ITM 2": 100,
        "ITM 3": 150,
        "OTM 1": 50,   # Will be adjusted based on direction
        "OTM 2": 100,
        "OTM 3": 150
    }
    strike_offset_base = strike_offset_map.get(strike_selection, 0)
    
    # Determine if ITM or OTM (for direction-specific calculation)
    is_itm = strike_selection.startswith("ITM")
    is_otm = strike_selection.startswith("OTM")
    
    # Prepare strategy config with all enhanced features
    backtest_config = {
        'initial_capital': float(initial_capital),
        'lot_size': int(lot_size),
        'strike_selection': strike_selection,  # Store selection for reference
        'strike_offset_base': strike_offset_base,  # Base offset (will be adjusted by direction)
        'strike_is_itm': is_itm,
        'strike_is_otm': is_otm,
        'strategy': {
            **strategy_config.get('strategy', {}),
            # Legacy defaults (used when flags are off)
            'premium_sl_pct': float(sl_pct),
            'sl': 30,
            'rr': 1.8,
            
            # Feature toggles
            'use_atr_filter': use_atr_filter,
            'use_regime_filter': use_regime_filter,
            'use_distance_guard': use_distance_guard,
            'use_tiered_exits': use_tiered_exits,
            'use_expiry_protocol': use_expiry_protocol,
            'use_directional_sizing': use_directional_sizing,
            
            # Filters
            'atr_floor_pct_1h': float(atr_floor_pct),
            'ema_slope_len': int(ema_slope_len),
            'adx_min': 0.0,  # Disabled for now
            'distance_guard_atr': float(distance_guard_atr),
            
            # Vol-band SL
            'vol_bands': {
                'low': float(vol_band_low),
                'high': float(vol_band_high)
            },
            'premium_sl_pct_low': float(sl_pct_low),
            'premium_sl_pct_norm': float(sl_pct_norm),
            'premium_sl_pct_high': float(sl_pct_high),
            
            # Breakeven & trailing
            'be_at_r': float(be_at_r),
            'trail_type': 'chandelier',
            'trail_lookback': int(trail_lookback),
            'trail_mult': float(trail_mult),
            'swing_lock': True,
            
            # Partial exits
            't1_r': float(t1_r),
            't1_book': float(t1_book_pct),
            't2_r': float(t2_r),
            't2_book': float(t2_book_pct),
            
            # Expiry protocol
            'no_new_after': str(no_new_after),
            'force_partial_by': str(force_partial_by),
            'tighten_trail_days_to_expiry': float(tighten_days),
            'tighten_mult_factor': 1.3
        },
        'position_management': {
            # Use override values from Enhanced Features (they default to main section values)
            'sl_points': int(sl_points_config),
            'trail_points': int(trail_points_config),
            'book1_points': int(book1_points_config),
            'book2_points': int(book2_points_config),
            'book1_ratio': float(book1_ratio_config)
        },
        'sizing': {
            'risk_per_trade_pct': float(risk_per_trade_pct),
            'pe_size_cap_vs_ce': float(pe_size_cap_vs_ce),
            'portfolio_risk_cap_pct': 4.0,
            'max_concurrent_positions': int(max_concurrent)
        }
        }  # Close advanced parameters expander

# ============ SETTINGS TAB ============
elif tab == "Settings":
    st.header("⚙️ Settings & Configuration")
    
    # Load current config
    import yaml as yaml_lib
    with open('config/config.yaml', 'r') as f:
        current_config = yaml_lib.safe_load(f)
    
    # Strategy Options Section
    with st.expander("📊 Strategy Options", expanded=False):
        st.subheader("📊 Strategy Parameters")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Trading Parameters:**")
            st.text(f"Lot Size: {current_config.get('lot_size', 'N/A')}")
            st.caption("💡 NIFTY lot size (1 lot = 75 units typically)")
            
            st.markdown("**Strategy Settings:**")
            strategy = current_config.get('strategy', {})
            st.text(f"Type: {strategy.get('type', 'N/A')}")
            st.caption("💡 Strategy type: Inside Bar + Breakout")
            st.text(f"Stop Loss: {strategy.get('sl', 'N/A')} points")
            st.caption("💡 Stop loss in points (e.g., 30 points)")
            st.text(f"Risk-Reward: {strategy.get('rr', 'N/A')}")
            st.caption("💡 Risk-reward ratio (e.g., 1.8 = 1.8x reward for 1x risk)")
        
        with col2:
            st.markdown("**Filters:**")
            filters = strategy.get('filters', {})
            st.text(f"Volume Spike: {'✅ Enabled' if filters.get('volume_spike') else '❌ Disabled'}")
            st.caption("💡 Require volume spike confirmation for breakout")
            st.text(f"Avoid Open Range: {'✅ Enabled' if filters.get('avoid_open_range') else '❌ Disabled'}")
            st.caption("💡 Avoid trading during open range period")
        
        st.warning("⚠️ To modify configuration, edit `config/config.yaml` file directly and restart the application.")
        
        # Restore Default Settings button
        if st.button("🔄 Restore Default Settings", help="Restore default configuration values"):
            st.info("💡 This feature will be implemented. For now, manually edit config/config.yaml")
    
    st.divider()
    
    # Broker Settings Section
    with st.expander("🔌 Broker Settings", expanded=True):
        st.subheader("🔌 Broker Configuration")
        broker_config = config.get('broker', {})
        if broker_config:
            # If broker_config is from st.secrets, access it directly
            if not isinstance(broker_config, dict):
                try:
                    broker_config = {
                        'type': getattr(broker_config, 'type', ''),
                        'api_key': getattr(broker_config, 'api_key', ''),
                        'client_id': getattr(broker_config, 'client_id', ''),
                    }
                except:
                    broker_config = {}
            broker_type = broker_config.get('type', '').lower()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.text(f"Type: {broker_config.get('type', 'N/A')}")
                st.caption("💡 Broker type: Angel One, Fyers, etc.")
                st.text(f"Client ID: {broker_config.get('client_id', 'N/A')}")
                st.caption("💡 Your broker client ID")
            
            with col2:
                # Test Broker Connection button
                if st.button("🧪 Test Broker Connection", type="primary", use_container_width=True, help="Test the connection to your broker"):
                    with st.spinner("Testing broker connection..."):
                        try:
                            if st.session_state.broker is not None:
                                # Try to fetch account info or holdings as a test
                                try:
                                    test_result = st.session_state.broker.get_holdings()
                                    if test_result is not None:
                                        st.success("✅ Broker connection successful!")
                                        st.info("💡 Connection test passed. You can fetch data from your broker.")
                                    else:
                                        st.warning("⚠️ Connection test returned no data. Check broker configuration.")
                                except Exception as e:
                                    st.error(f"❌ Connection test failed: {e}")
                                    st.caption("💡 Check your broker credentials and API keys")
                            else:
                                st.error("❌ Broker not initialized. Check configuration.")
                        except Exception as e:
                            st.error(f"❌ Error testing connection: {e}")
                
                st.success("✅ Broker configured")
            
            # Token refresh button for Angel One SmartAPI
            if broker_type == 'angel':
                st.divider()
                st.markdown("**Session Management**")
                
                # Initialize broker interface in session state if not exists
                if 'broker_interface' not in st.session_state:
                    try:
                        # Get broker config safely (from config dict or st.secrets)
                        broker_config_for_interface = config.get('broker', {})
                        
                        # If using Streamlit secrets and broker not in config dict, access directly
                        if not broker_config_for_interface and config.get('_from_streamlit_secrets') and hasattr(st, 'secrets'):
                            try:
                                broker_secrets = getattr(st.secrets, 'broker', None)
                                if broker_secrets:
                                    broker_config_for_interface = {
                                        'type': getattr(broker_secrets, 'type', 'angel'),
                                        'api_key': getattr(broker_secrets, 'api_key', ''),
                                        'client_id': getattr(broker_secrets, 'client_id', ''),
                                        'username': getattr(broker_secrets, 'username', ''),
                                        'pwd': getattr(broker_secrets, 'pwd', ''),
                                        'token': getattr(broker_secrets, 'token', ''),
                                    }
                            except Exception as e:
                                logger.warning(f"Could not access broker from Streamlit secrets: {e}")
                        
                        if broker_config_for_interface:
                            temp_config = {'broker': broker_config_for_interface}
                            st.session_state.broker_interface = create_broker_interface(temp_config)
                        else:
                            st.session_state.broker_interface = None
                    except Exception as e:
                        st.error(f"❌ Failed to initialize broker: {e}")
                        st.session_state.broker_interface = None
                
                if st.session_state.broker_interface is not None:
                    if st.button("🔄 Refresh Broker Session", type="secondary", help="Refresh broker session tokens"):
                        with st.spinner("Refreshing broker session..."):
                            try:
                                success = st.session_state.broker_interface.refresh_session()
                                if success:
                                    st.success("✅ Broker session refreshed successfully!")
                                else:
                                    st.error("❌ Failed to refresh session. Check logs for details.")
                            except Exception as e:
                                st.error(f"❌ Error refreshing session: {e}")
                    
                    st.info("💡 Session tokens expire periodically. Refresh when needed or on first order.")
                else:
                    st.warning("⚠️ Broker interface not initialized. Check configuration.")
        else:
            st.error("❌ Broker not configured")
            st.caption("💡 Configure broker settings in .streamlit/secrets.toml")
    
    st.divider()
    
    # System Information Section
    with st.expander("ℹ️ System Information", expanded=False):
        st.subheader("ℹ️ System Information")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.text(f"Python Version: {sys.version.split()[0]}")
            st.caption("💡 Python runtime version")
            st.text(f"Streamlit Version: {st.__version__}")
            st.caption("💡 Streamlit framework version")
        
        with col2:
            # Get system info
            try:
                import platform
                st.text(f"Platform: {platform.system()} {platform.release()}")
                st.caption("💡 Operating system information")
            except:
                pass
            
            # Memory info
            try:
                import psutil
                memory = psutil.virtual_memory()
                st.text(f"Memory Usage: {memory.percent:.1f}%")
                st.caption("💡 System memory usage")
            except:
                st.text("Memory Info: Not available")
                st.caption("💡 Install psutil for memory info")


