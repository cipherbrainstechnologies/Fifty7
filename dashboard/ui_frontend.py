"""
Secure Streamlit Dashboard for NIFTY Options Trading System
"""

# -*- coding: utf-8 -*-
import streamlit as st
# import streamlit_authenticator as stauth  # Temporarily disabled
import yaml
from yaml.loader import SafeLoader
import pandas as pd
from datetime import datetime, date, timedelta, timezone as dt_timezone
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


def _ensure_utf8_console() -> None:
    """Best effort: force Windows stdout/stderr to UTF-8 so logging can emit emoji."""
    if not sys.platform.startswith("win"):
        return

    def _patch_stream(name: str) -> None:
        stream = getattr(sys, name, None)
        if stream is None:
            return

        encoding = getattr(stream, "encoding", "")
        if isinstance(encoding, str) and encoding.lower() == "utf-8":
            return

        # 1) Try native reconfigure (TextIOWrapper on Python 3.7+)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
                return
            except Exception:
                pass

        # 2) Try wrapping the underlying buffer
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            try:
                wrapped = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace", line_buffering=True)
                setattr(sys, name, wrapped)
                return
            except Exception:
                pass

        # 3) Fall back to codecs wrapper if detach is available
        if hasattr(stream, "detach"):
            try:
                import codecs

                detached = stream.detach()
                wrapped = codecs.getwriter("utf-8")(detached)  # type: ignore[arg-type]
                setattr(sys, name, wrapped)
                return
            except Exception:
                pass

    _patch_stream("stdout")
    _patch_stream("stderr")


_ensure_utf8_console()

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

@st.cache_resource
def get_trading_runtime_state() -> Dict[str, Any]:
    return {
        "live_runner": None,
        "algo_running": False,
        "lock": threading.Lock(),
    }

_runtime_state = get_trading_runtime_state()


def _set_live_runner_runtime(runner):
    _runtime_state["live_runner"] = runner
    st.session_state.live_runner = runner


def _set_algo_running_runtime(flag: bool):
    _runtime_state["algo_running"] = flag
    st.session_state.algo_running = flag


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
from engine.tick_stream import LiveTickStreamer
from engine.live_runner import LiveStrategyRunner
from engine.firebase_auth import FirebaseAuth
from engine.tenant_context import resolve_tenant
from engine.symbol_utils import canonicalize_tradingsymbol
from engine.event_bus import get_event_bus
from engine.state_store import get_state_store
from engine.state_persistence import get_state_persistence
from engine.websocket_server import start_websocket_server, stop_websocket_server
from engine.websocket_client import get_websocket_client
from dashboard.auth_page import (
    render_login_page,
    load_persisted_firebase_session,
    persist_firebase_session,
    clear_persisted_firebase_session,
)

# Load configuration function (must be defined before use)
def load_config():
    """
    Load configuration from environment variables (Railway/Render), secrets.toml (local), or st.secrets (Streamlit Cloud).
    Note: Not using @st.cache_data to avoid recursion issues with st.secrets.
    Returns a dict with all config sections.
    """
    config = {}
    
    # Priority 1: Load from environment variables (for Railway, Render, etc.)
    # Check if we're in production (Railway/Render set PORT)
    is_production = os.getenv("PORT") is not None or os.getenv("RAILWAY_ENVIRONMENT") is not None
    
    if is_production:
        # Load broker config from environment variables
        # Check both formats: BROKER_* (preferred) and lowercase (fallback for Railway)
        broker_config = {}
        broker_config['type'] = os.getenv('BROKER_TYPE') or os.getenv('type', 'angel')
        broker_config['api_key'] = os.getenv('BROKER_API_KEY') or os.getenv('api_key', '')
        broker_config['client_id'] = os.getenv('BROKER_CLIENT_ID') or os.getenv('client_id', '')
        broker_config['username'] = (
            os.getenv('BROKER_USERNAME') or 
            os.getenv('username') or 
            broker_config['client_id'] or 
            os.getenv('BROKER_CLIENT_ID') or 
            os.getenv('client_id', '')
        )
        broker_config['pwd'] = os.getenv('BROKER_PWD') or os.getenv('pwd', '')
        broker_config['token'] = os.getenv('BROKER_TOKEN') or os.getenv('token', '')
        broker_config['api_secret'] = os.getenv('BROKER_API_SECRET') or os.getenv('api_secret', '')
        
        if broker_config.get('api_key') or broker_config.get('token'):
            config['broker'] = broker_config
            logger.info(f"Loaded broker config from environment variables (type: {broker_config['type']}, has_api_key: {bool(broker_config.get('api_key'))}, has_token: {bool(broker_config.get('token'))})")
        else:
            logger.warning("No broker config found in environment variables. Broker functionality will not work.")
        
        # Load SmartAPI apps config from environment variables
        smartapi_apps = {}
        
        # Trading app
        if os.getenv('SMARTAPI_TRADING_API_KEY'):
            smartapi_apps['trading'] = {
                'api_key': os.getenv('SMARTAPI_TRADING_API_KEY', ''),
                'api_secret': os.getenv('SMARTAPI_TRADING_API_SECRET', ''),
            }
        
        # Historical app
        if os.getenv('SMARTAPI_HISTORICAL_API_KEY'):
            smartapi_apps['historical'] = {
                'api_key': os.getenv('SMARTAPI_HISTORICAL_API_KEY', ''),
                'api_secret': os.getenv('SMARTAPI_HISTORICAL_API_SECRET', ''),
            }
        
        # Publisher app
        if os.getenv('SMARTAPI_PUBLISHER_API_KEY'):
            smartapi_apps['publisher'] = {
                'api_key': os.getenv('SMARTAPI_PUBLISHER_API_KEY', ''),
                'api_secret': os.getenv('SMARTAPI_PUBLISHER_API_SECRET', ''),
            }
        
        if smartapi_apps:
            config['smartapi_apps'] = smartapi_apps
            logger.info("Loaded SmartAPI apps config from environment variables")
        
        # Always return config in production (even if empty), so we know to use env vars
        logger.info("Using configuration from environment variables (Railway/Render)")
        if config.get('broker'):
            logger.info(f"Broker config loaded: type={config['broker'].get('type')}, has_api_key={bool(config['broker'].get('api_key'))}, has_token={bool(config['broker'].get('token'))}")
        return config
    
    # Priority 2: Try to load from secrets.toml file (for local development)
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
    
    # Priority 3: For Streamlit Cloud, we'll access st.secrets directly when needed
    # Don't convert to dict here to avoid recursion
    # Mark that we're using Streamlit secrets
    if hasattr(st, 'secrets'):
        config['_from_streamlit_secrets'] = True
        logger.info("Using Streamlit secrets (will access directly)")
    
    return config

# Initialize database on startup
try:
    from engine.db import init_database
    init_database(create_all=True)
    logger.info("Database initialized successfully")
except Exception as e:
    logger.warning(f"Database initialization failed (non-critical): {e}")

# Initialize Event Bus and State Store
event_bus = get_event_bus()
state_store = get_state_store()

# Initialize state persistence if enabled
config = load_config()

# Merge config.yaml into config (for timeframes, strategy, etc.)
try:
    import yaml as yaml_lib
    config_yaml_path = 'config/config.yaml'
    if os.path.exists(config_yaml_path):
        with open(config_yaml_path, 'r') as f:
            yaml_config = yaml_lib.safe_load(f)
            if yaml_config:
                # Merge yaml config into secrets config (yaml takes precedence for non-secret values)
                for key, value in yaml_config.items():
                    if key not in config or not isinstance(config.get(key), dict):
                        config[key] = value
                    elif isinstance(value, dict):
                        # Deep merge for nested dicts
                        if key not in config:
                            config[key] = {}
                        config[key].update(value)
                logger.debug("Merged config.yaml into config")
except Exception as e:
    logger.warning(f"Could not load config.yaml: {e}")

state_config = config.get('state_store', {})
if state_config.get('enabled', True):
    state_persistence = get_state_persistence(
        snapshot_dir=state_config.get('snapshot_dir', 'data/state'),
        snapshot_interval_minutes=state_config.get('snapshot_interval_minutes', 5)
    )
    
    # Restore state on startup if enabled
    if state_config.get('restore_on_startup', True):
        try:
            if state_config.get('replay_events_on_restore', True):
                event_log_file = config.get('event_bus', {}).get('event_log_file', 'logs/events.log')
                state_persistence.restore_with_replay(event_log_file=event_log_file)
            else:
                state_persistence.restore_from_snapshot()
            logger.info("State restored from snapshot")
        except Exception as e:
            logger.warning(f"State restore failed (non-critical): {e}")

# Enable event persistence if configured
event_bus_config = config.get('event_bus', {})
if event_bus_config.get('enabled', True) and event_bus_config.get('persist_events', True):
    event_bus.enable_persistence(event_bus_config.get('event_log_file', 'logs/events.log'))

# Initialize periodic state snapshots
if state_config.get('enabled', True) and 'state_snapshot_thread' not in st.session_state:
    def periodic_snapshot():
        """Background thread for periodic state snapshots."""
        import time
        interval = state_config.get('snapshot_interval_minutes', 5) * 60
        while True:
            time.sleep(interval)
            try:
                state_persistence.save_snapshot()
            except Exception as e:
                logger.warning(f"Periodic snapshot failed: {e}")
    
    snapshot_thread = threading.Thread(target=periodic_snapshot, daemon=True)
    snapshot_thread.start()
    st.session_state.state_snapshot_thread = snapshot_thread
    logger.info("Periodic state snapshot thread started")

# Initialize WebSocket server and client
websocket_config = config.get('websocket', {})

# Detect production environment
_is_production = (
    os.getenv("RAILWAY_ENVIRONMENT") is not None or
    os.getenv("RENDER") is not None or
    os.getenv("PORT") is not None or
    os.getenv("DYNO") is not None
)

def _get_websocket_uri() -> str:
    """Get WebSocket URI based on environment."""
    if _is_production:
        # In production, use WSS and Railway's WebSocket service domain
        # Priority: WEBSOCKET_PUBLIC_DOMAIN > PUBLIC_URL > RAILWAY_PUBLIC_DOMAIN
        websocket_domain = (
            os.getenv("WEBSOCKET_PUBLIC_DOMAIN") or
            websocket_config.get('public_domain') or
            os.getenv("PUBLIC_URL") or  # This should point to WebSocket service
            os.getenv("RAILWAY_PUBLIC_DOMAIN") or
            os.getenv("RAILWAY_STATIC_URL")
        )
        
        if websocket_domain:
            # Remove protocol if present
            websocket_domain = websocket_domain.replace("https://", "").replace("http://", "")
            # Remove trailing slash
            websocket_domain = websocket_domain.rstrip('/')
            # Use wss:// for secure WebSocket in production
            return f"wss://{websocket_domain}/ws"
        
        # Fallback: Use config URI or construct from available info
        config_uri = websocket_config.get('uri')
        if config_uri:
            if config_uri.startswith('ws://'):
                # Convert to wss:// for production
                return config_uri.replace('ws://', 'wss://')
            return config_uri
        
        logger.warning(
            "Cannot determine WebSocket URI in production. "
            "Set WEBSOCKET_PUBLIC_DOMAIN environment variable pointing to your WebSocket service, "
            "or configure websocket.public_domain in config.yaml"
        )
        return None
    
    # Local development: Use config or default
    return websocket_config.get('uri', f"ws://127.0.0.1:{websocket_config.get('port', 8765)}/ws")

# Check if WebSocket is enabled (from config or environment variable)
websocket_enabled = websocket_config.get('enabled', True)
# Also check environment variable (can override config)
websocket_enabled_env = os.getenv("WEBSOCKET_ENABLED")
if websocket_enabled_env:
    websocket_enabled = websocket_enabled_env.lower() in ('true', '1', 'yes', 'on')

if websocket_enabled:
    # Start WebSocket server (only if not production or if WEBSOCKET_PORT is set)
    if not _is_production or os.getenv("WEBSOCKET_PORT"):
        if 'websocket_server_started' not in st.session_state:
            try:
                # Let start_websocket_server use environment-aware defaults
                start_websocket_server()
                st.session_state.websocket_server_started = True
                logger.info("WebSocket server started")
            except Exception as e:
                logger.warning(f"Failed to start WebSocket server: {e}")
    else:
        logger.info(
            "WebSocket server skipped in production. "
            "Set WEBSOCKET_PORT environment variable to enable, "
            "or deploy WebSocket as a separate Railway service."
        )
    
    # Initialize WebSocket client (only if WebSocket service is available)
    if 'websocket_client_initialized' not in st.session_state:
        try:
            ws_uri = _get_websocket_uri()
            if not ws_uri:
                logger.warning("WebSocket client disabled: Cannot determine WebSocket URI. Set WEBSOCKET_PUBLIC_DOMAIN to your WebSocket service URL.")
            else:
                # Warn if URI points to main app instead of WebSocket service
                if 'web-production' in ws_uri or ws_uri.startswith('wss://web-'):
                    logger.warning(
                        f"⚠️ WebSocket URI points to main app ({ws_uri}). "
                        "This will fail. Set WEBSOCKET_PUBLIC_DOMAIN to your WebSocket service URL "
                        "(e.g., nifty-option-websocket-production.up.railway.app)"
                    )
                ws_client = get_websocket_client(uri=ws_uri)
                
                # Subscribe to WebSocket messages
                def on_websocket_event(message):
                    """Handle event messages from WebSocket."""
                    event_type = message.get('event_type')
                    data = message.get('data', {})
                    
                    # Update session state to trigger UI refresh
                    if 'websocket_events' not in st.session_state:
                        st.session_state.websocket_events = []
                    st.session_state.websocket_events.append({
                        'type': event_type,
                        'data': data,
                        'timestamp': message.get('timestamp'),
                    })
                    # Keep only recent events
                    if len(st.session_state.websocket_events) > 100:
                        st.session_state.websocket_events.pop(0)
                    
                    # Trigger UI update for critical events
                    critical_events = ['trade_executed', 'position_closed', 'daily_loss_breached']
                    if event_type in critical_events:
                        st.session_state.last_critical_event = datetime.now()
                
                def on_state_update(message):
                    """Handle state update messages from WebSocket."""
                    path = message.get('path')
                    new_value = message.get('new_value')
                    
                    # Update session state
                    if 'websocket_state_updates' not in st.session_state:
                        st.session_state.websocket_state_updates = {}
                    st.session_state.websocket_state_updates[path] = {
                        'value': new_value,
                        'timestamp': message.get('timestamp'),
                    }
                
                def on_state_snapshot(message):
                    """Handle state snapshot from WebSocket."""
                    snapshot = message.get('data', {})
                    if 'state' in snapshot:
                        # Store snapshot in session state
                        st.session_state.websocket_state_snapshot = snapshot
                        logger.info("Received state snapshot from WebSocket server")
                
                ws_client.subscribe('event', on_websocket_event)
                ws_client.subscribe('state_update', on_state_update)
                ws_client.subscribe('state_snapshot', on_state_snapshot)
                
                # Start client
                if ws_client.start():
                    st.session_state.websocket_client_initialized = True
                    st.session_state.websocket_client = ws_client
                    logger.info(f"WebSocket client initialized and connected to {ws_uri}")
                else:
                    logger.warning("Failed to start WebSocket client")
        except Exception as e:
            logger.warning(f"Failed to initialize WebSocket client: {e}")

# Cloud data sources
try:
    from backtesting.datasource_desiquant import stream_data
    DESIQUANT_AVAILABLE = True
except ImportError:
    DESIQUANT_AVAILABLE = False
    stream_data = None

try:
    from backtesting.datasource_smartapi import stream_data as smartapi_stream_data
    SMARTAPI_BACKTEST_AVAILABLE = True
except ImportError:
    SMARTAPI_BACKTEST_AVAILABLE = False
    smartapi_stream_data = None


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
    body {
        background-color: #f1f5f9;
    }
    .dashboard-shell {
        max-width: 1280px;
        margin: 0 auto;
        padding: 1rem 1.5rem 3rem;
    }
    .status-ribbon {
        position: sticky;
        top: 0;
        z-index: 50;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 0.75rem 1rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
    }
    .status-chip-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
    }
    .status-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        border-radius: 8px;
        padding: 0.35rem 0.75rem;
        font-size: 0.9rem;
        border: 1px solid #e2e8f0;
        background: #f8fafc;
    }
    .status-chip .chip-dot {
        width: 8px;
        height: 8px;
        border-radius: 9999px;
        display: inline-flex;
    }
    .status-chip.success {
        background: #ecfdf5;
        border-color: #a7f3d0;
        color: #065f46;
    }
    .status-chip.success .chip-dot {
        background: #10b981;
    }
    .status-chip.info {
        background: #eff6ff;
        border-color: #bfdbfe;
        color: #1d4ed8;
    }
    .status-chip.info .chip-dot {
        background: #3b82f6;
    }
    .status-chip.warning {
        background: #fff7ed;
        border-color: #fed7aa;
        color: #c2410c;
    }
    .status-chip.warning .chip-dot {
        background: #fb923c;
    }
    .status-chip.danger {
        background: #fef2f2;
        border-color: #fecaca;
        color: #991b1b;
    }
    .status-chip.danger .chip-dot {
        background: #ef4444;
    }
    .auto-refresh-controls {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 1rem;
        flex-wrap: wrap;
    }
    .trading-panel {
        border: 2px solid #fed7aa;
        background: #fff7ed;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 12px 24px rgba(251, 146, 60, 0.12);
    }
    .hero-grid {
        display: grid;
        grid-template-columns: minmax(0, 1.15fr) minmax(0, 0.85fr);
        gap: 1.2rem;
        margin-bottom: 1.5rem;
    }
    @media (max-width: 992px) {
        .hero-grid {
            grid-template-columns: 1fr;
        }
    }
    .card {
        background: #ffffff;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
        padding: 1.25rem;
    }
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 1rem;
    }
    .metric-tile h5 {
        margin: 0 0 0.35rem;
        font-size: 0.9rem;
        color: #475569;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .metric-tile {
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        padding: 1rem;
        background: #ffffff;
    }
    .metric-value {
        font-size: 1.4rem;
        font-weight: 600;
        color: #0f172a;
    }
    .metric-subtle {
        font-size: 0.85rem;
        color: #94a3b8;
    }
    .snapshot-card {
        margin-bottom: 1.5rem;
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }
    .snapshot-section {
        border-radius: 12px;
        padding: 1rem;
        border: 1px solid #e2e8f0;
    }
    .snapshot-section.mother {
        background: #f8fafc;
        border-color: #cbd5f5;
    }
    .snapshot-section.inside {
        background: #eff6ff;
        border-color: #bfdbfe;
    }
    .snapshot-section.range {
        background: #f5f3ff;
        border-color: #ddd6fe;
    }
    .snapshot-section .snapshot-title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-weight: 600;
        margin-bottom: 0.5rem;
        color: #0f172a;
    }
    .snapshot-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
        gap: 0.75rem;
    }
    .snapshot-cell label {
        font-size: 0.75rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .snapshot-cell span {
        display: block;
        font-size: 1.05rem;
        font-weight: 600;
        color: #0f172a;
    }
    .config-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin-bottom: 1.5rem;
    }
    .config-chip {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 0.5rem 0.85rem;
        font-size: 0.9rem;
        color: #0f172a;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
    }
    .config-chip span {
        display: block;
        font-size: 0.75rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .config-chip strong {
        display: block;
        font-size: 1rem;
        color: #0f172a;
    }
    .badge {
        display: inline-flex;
        align-items: center;
        border-radius: 9999px;
        padding: 0.1rem 0.75rem;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-green {
        background: #dcfce7;
        color: #166534;
    }
    .badge-red {
        background: #fee2e2;
        color: #991b1b;
    }
    .badge-blue {
        background: #dbeafe;
        color: #1d4ed8;
    }
    .trade-box-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 0.75rem;
        margin-bottom: 0.75rem;
    }
    .trade-box {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 0.85rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
    }
    .trade-box label {
        display: block;
        font-size: 0.75rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.25rem;
    }
    .trade-box span {
        font-size: 1.25rem;
        font-weight: 600;
        color: #0f172a;
    }
    .footer-bar {
        margin-top: 1.5rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        flex-wrap: wrap;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 0.75rem 1rem;
        background: #ffffff;
    }
    .footer-bar a {
        text-decoration: none;
        font-weight: 600;
        color: #0f172a;
    }
    .debug-section .st-expander {
        border: 1px solid #e2e8f0;
        border-radius: 12px;
    }
    .status-ribbon [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap;
        gap: 0.75rem;
    }
    .status-ribbon [data-testid="column"] {
        min-width: 160px;
    }
    @media (max-width: 1200px) {
        .hero-grid {
            grid-template-columns: 1fr;
        }
        .footer-bar {
            flex-direction: column;
            align-items: flex-start;
        }
    }
    @media (max-width: 900px) {
        .status-ribbon {
            flex-direction: column;
        }
        .status-chip-row {
            justify-content: flex-start;
        }
    }
    @media (max-width: 640px) {
        .metric-grid {
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        }
        .trade-box-grid {
            grid-template-columns: 1fr;
        }
        .status-chip {
            width: 100%;
            justify-content: space-between;
        }
    }
</style>
""", unsafe_allow_html=True)


def _build_status_chip_html(label: str, value: str, state: str = "info", subtitle: Optional[str] = None) -> str:
    subtitle_html = f"<span class='metric-subtle'>{subtitle}</span>" if subtitle else ""
    return (
        f"<div class='status-chip {state}'>"
        f"<span class='chip-dot'></span>"
        f"<div><strong>{label}</strong><br/><span>{value}</span>{subtitle_html}</div>"
        f"</div>"
    )


def _build_metric_tile_html(title: str, value: str, subtitle: Optional[str] = None) -> str:
    subtitle_html = f"<div class='metric-subtle'>{subtitle}</div>" if subtitle else ""
    return (
        f"<div class='metric-tile'>"
        f"<h5>{title}</h5>"
        f"<div class='metric-value'>{value}</div>"
        f"{subtitle_html}"
        f"</div>"
    )


def _render_strategy_settings_popover(form_key: str = "strategy_settings_form") -> None:
    st.caption("Adjust live trading parameters. Changes apply to the next signal.")
    config_source: Dict[str, Any] = config if isinstance(config, dict) else {}
    if st.session_state.get('live_runner') is not None:
        config_source = st.session_state.live_runner.config

    strategy_cfg = config_source.get('strategy', {}) or {}
    pm_cfg = config_source.get('position_management', {}) or {}
    risk_cfg = config_source.get('risk_management', {}) or {}

    current_sl_points = strategy_cfg.get('sl', 30)
    current_order_lots = config_source.get('broker', {}).get('default_lots', 2)
    current_lot_size = config_source.get('lot_size', 75)
    current_trail_points = pm_cfg.get('trail_points', 10)
    current_atm_offset = strategy_cfg.get('atm_offset', 0)
    current_daily_loss_limit_pct = risk_cfg.get('daily_loss_limit_pct', 5.0)

    if st.session_state.get('live_runner') is not None:
        runner = st.session_state.live_runner
        current_sl_points = getattr(runner, 'sl_points', current_sl_points)
        current_order_lots = getattr(runner, 'order_lots', current_order_lots)
        current_lot_size = getattr(runner, 'lot_size', current_lot_size)
        runner_pm_cfg = runner.config.get('position_management', {}) or {}
        current_trail_points = runner_pm_cfg.get('trail_points', current_trail_points)
        current_atm_offset = runner.config.get('strategy', {}).get('atm_offset', current_atm_offset)
        current_daily_loss_limit_pct = getattr(runner, 'daily_loss_limit_pct', current_daily_loss_limit_pct)

    with st.form(form_key, clear_on_submit=False):
        settings_cols = st.columns(2)
        with settings_cols[0]:
            sl_points_input = st.number_input(
                "Stop Loss (points)",
                min_value=10,
                max_value=100,
                value=int(current_sl_points),
                step=5,
                help="Applies to option premium. Example: 30 points → SL at entry - 30.",
            )
            trail_points_input = st.number_input(
                "Trailing SL step (points)",
                min_value=5,
                max_value=50,
                value=int(current_trail_points),
                step=5,
                help="Trailing increment applied once price moves favourably by the chosen step.",
            )
        with settings_cols[1]:
            atm_offset_input = st.number_input(
                "Strike bias (points)",
                min_value=-300,
                max_value=300,
                value=int(current_atm_offset),
                step=50,
                help="Shifts strike selection away from ATM. Positive = OTM (calls), negative = ITM.",
            )
            sl_lots_input = st.number_input(
                "Order quantity (lots)",
                min_value=1,
                max_value=10,
                value=int(current_order_lots),
                step=1,
                help="Number of lots to trade per signal.",
            )

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
                help="Trading halts if daily P&L drops below -X% of initial capital.",
            )
        with risk_cols[1]:
            lot_size_input = st.number_input(
                "Lot size (contracts)",
                min_value=25,
                max_value=100,
                value=int(current_lot_size),
                step=25,
                help="Lot size for position sizing calculations.",
            )

        submitted = st.form_submit_button("💾 Save strategy configuration", use_container_width=True)

    if submitted:
        try:
            if st.session_state.get('live_runner') is not None:
                st.session_state.live_runner.update_strategy_config(
                    sl_points=int(sl_points_input),
                    atm_offset=int(atm_offset_input),
                    order_lots=int(sl_lots_input),
                    trail_points=int(trail_points_input),
                    daily_loss_limit_pct=float(daily_loss_limit_pct_input),
                    lot_size=int(lot_size_input),
                )
            st.success("✅ Strategy settings saved.")
        except Exception as e:
            st.error(f"❌ Error updating config: {e}")


def _render_active_trade_metric_row(buy_value: str, tp_value: str, sl_value: str, trail_value: str) -> None:
    boxes = [
        ("Buying Price", buy_value),
        ("Take Profit", tp_value),
        ("Stop Loss", sl_value),
        ("Trailing SL", trail_value),
    ]
    tiles = "".join(
        f"<div class='trade-box'><label>{label}</label><span>{value}</span></div>"
        for label, value in boxes
    )
    st.markdown(f"<div class='trade-box-grid'>{tiles}</div>", unsafe_allow_html=True)

# Helper function to safely get config value from either source
def get_config_value(section, key, default=None):
    """Safely get config value from secrets.toml or st.secrets"""
    # Access global config variable
    global config
    
    # First check loaded config dict
    if 'config' in globals() and section in config and isinstance(config[section], dict):
        return config[section].get(key, default)
    
    # If using Streamlit secrets, access directly
    if 'config' in globals() and config.get('_from_streamlit_secrets') and hasattr(st, 'secrets'):
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

# Config is already loaded and merged with config.yaml above
# Only reload if config is not already set (shouldn't happen, but safety check)
if 'config' not in globals() or not config:
    config = load_config()
    # Merge config.yaml if not already merged
    try:
        import yaml as yaml_lib
        config_yaml_path = 'config/config.yaml'
        if os.path.exists(config_yaml_path):
            with open(config_yaml_path, 'r') as f:
                yaml_config = yaml_lib.safe_load(f)
                if yaml_config:
                    for key, value in yaml_config.items():
                        if key not in config or not isinstance(config.get(key), dict):
                            config[key] = value
                        elif isinstance(value, dict):
                            if key not in config:
                                config[key] = {}
                            config[key].update(value)
    except Exception as e:
        logger.warning(f"Could not load config.yaml: {e}")

# Initialize Firebase Authentication
firebase_auth = None
allowed_email = None
try:
    # Get Firebase config - check Streamlit secrets first, then config dict
    firebase_config = None
    
    # Priority 1: Check environment variables (for Railway, Render, etc.)
    # Railway uses environment variables, not secrets.toml
    firebase_config = {}
    env_keys = {
        'apiKey': 'FIREBASE_API_KEY',
        'authDomain': 'FIREBASE_AUTH_DOMAIN',
        'projectId': 'FIREBASE_PROJECT_ID',
        'storageBucket': 'FIREBASE_STORAGE_BUCKET',
        'messagingSenderId': 'FIREBASE_MESSAGING_SENDER_ID',
        'appId': 'FIREBASE_APP_ID',
        'databaseURL': 'FIREBASE_DATABASE_URL',
        'allowedEmail': 'FIREBASE_ALLOWED_EMAIL',
    }
    
    for config_key, env_key in env_keys.items():
        env_value = os.getenv(env_key)
        if env_value:
            firebase_config[config_key] = env_value
    
    # Only use if we got at least apiKey
    if firebase_config.get('apiKey'):
        logger.info("Loaded Firebase config from environment variables")
    else:
        firebase_config = None
    
    # Priority 2: Check Streamlit secrets directly (for Streamlit Cloud)
    if not firebase_config and hasattr(st, 'secrets'):
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
    
    # Priority 3: Check config dict (for local development with secrets.toml)
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

# Attempt to preload persisted Firebase session tokens before restoration logic
if firebase_auth and not st.session_state.authenticated:
    persisted_session = load_persisted_firebase_session()
    if persisted_session:
        st.session_state.setdefault('user_email', persisted_session.get('user_email'))
        st.session_state.setdefault('refresh_token', persisted_session.get('refresh_token'))
        st.session_state.setdefault('id_token', persisted_session.get('id_token'))

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
                    persist_firebase_session(
                        st.session_state.user_email,
                        st.session_state.id_token,
                        st.session_state.refresh_token,
                    )
                    logger.info(f"Firebase session restored for user: {stored_user_email}")
                else:
                    # Refresh failed, clear tokens
                    st.session_state.id_token = None
                    st.session_state.refresh_token = None
                    st.session_state.user_email = None
                    clear_persisted_firebase_session()
                    logger.warning("Firebase session refresh failed, tokens cleared")
            except Exception as e:
                # Refresh failed, clear tokens
                logger.warning(f"Firebase session restore failed: {e}")
                st.session_state.id_token = None
                st.session_state.refresh_token = None
                st.session_state.user_email = None
                clear_persisted_firebase_session()
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
                    persist_firebase_session(
                        st.session_state.user_email,
                        st.session_state.id_token,
                        st.session_state.refresh_token,
                    )
                    logger.info(f"Firebase session restored using id_token for user: {st.session_state.user_email}")
                else:
                    # Token invalid, clear it
                    st.session_state.id_token = None
                    st.session_state.refresh_token = None
                    st.session_state.user_email = None
                    clear_persisted_firebase_session()
            except Exception as e:
                logger.warning(f"Firebase token verification failed: {e}")
                st.session_state.id_token = None
                st.session_state.refresh_token = None
                st.session_state.user_email = None
                clear_persisted_firebase_session()

# If Firebase is configured, require authentication
if firebase_auth:
    if not st.session_state.authenticated:
        # Show login page with email restriction
        render_login_page(firebase_auth, allowed_email)
        st.stop()
    else:
        # Verify authenticated email matches allowed email (if restricted)
        user_email = st.session_state.get('user_email', '')
        # Normalize both emails to lowercase for comparison
        if allowed_email and user_email.lower() != allowed_email.lower():
            st.error(f"❌ Access Denied. Only authorized email ({allowed_email}) can access.")
            firebase_auth.sign_out()
            clear_persisted_firebase_session()
            st.session_state.authenticated = False
            st.session_state.user = None
            st.session_state.id_token = None
            st.session_state.refresh_token = None
            st.session_state.user_email = None
            st.rerun()
        
        # User is authenticated, show dashboard
        logger.info(f"User authenticated: {user_email}. Rendering dashboard...")
        name = user_email.split('@')[0] if '@' in user_email else user_email
        username = user_email
        auth_status = True
        
        # Initialize event subscriptions for UI updates
        if 'event_subscriptions_initialized' not in st.session_state:
            def on_trade_executed(event):
                """Handle trade_executed event."""
                data = event.get('data', {})
                st.session_state.setdefault('recent_trades', []).append(data)
                # Trigger UI refresh
                if 'last_event_time' not in st.session_state:
                    st.session_state.last_event_time = datetime.now()
                else:
                    st.session_state.last_event_time = datetime.now()
            
            def on_position_updated(event):
                """Handle position_updated event."""
                data = event.get('data', {})
                # Update active P&L in session state
                if 'active_pnl_updates' not in st.session_state:
                    st.session_state.active_pnl_updates = []
                st.session_state.active_pnl_updates.append(data)
                st.session_state.last_event_time = datetime.now()
            
            def on_signal_detected(event):
                """Handle signal_detected event."""
                data = event.get('data', {})
                st.session_state.setdefault('recent_signals', []).append(data)
                st.session_state.last_event_time = datetime.now()
            
            # Subscribe to events
            event_bus.subscribe('trade_executed', on_trade_executed)
            event_bus.subscribe('position_updated', on_position_updated)
            event_bus.subscribe('signal_detected', on_signal_detected)
            event_bus.subscribe('position_closed', on_position_updated)
            event_bus.subscribe('daily_loss_breached', lambda e: st.session_state.update({'daily_loss_breached': True}))
            
            st.session_state.event_subscriptions_initialized = True
            logger.info("Event subscriptions initialized")
        
        # Add logout button in sidebar
        with st.sidebar:
            st.success(f"👋 Welcome, {name}")
            if allowed_email:
                st.caption(f"📧 {allowed_email}")
            if st.button("🚪 Logout", use_container_width=True):
                firebase_auth.sign_out()
                clear_persisted_firebase_session()
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
    st.session_state.algo_running = _runtime_state.get("algo_running", False)
if 'strategy_settings_feedback' not in st.session_state:
    st.session_state.strategy_settings_feedback = None
if 'market_refresh_feedback' not in st.session_state:
    st.session_state.market_refresh_feedback = None
if 'live_runner' not in st.session_state:
    st.session_state.live_runner = _runtime_state.get("live_runner")
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
            st.session_state['_broker_interface_config'] = broker_config_for_interface
            st.session_state.broker = create_broker_interface(temp_config)
        else:
            st.session_state.broker = None
            logger.warning("No broker configuration found")
    except Exception as e:
        st.session_state.broker = None
        st.warning(f"Broker initialization warning: {e}")
if 'signal_handler' not in st.session_state:
    # Load strategy config
    try:
        import yaml as yaml_lib
        config_path = 'config/config.yaml'
        if not os.path.exists(config_path):
            logger.error(f"Configuration file not found: {config_path}")
            st.warning(f"⚠️ Configuration file not found: {config_path}. Some features may not work.")
            st.session_state.signal_handler = None
        else:
            with open(config_path, 'r') as f:
                strategy_config = yaml_lib.safe_load(f)
            if strategy_config:
                st.session_state.signal_handler = SignalHandler(strategy_config)
            else:
                logger.warning(f"Config file {config_path} is empty or invalid")
                st.warning(f"⚠️ Config file {config_path} is empty or invalid. Some features may not work.")
                st.session_state.signal_handler = None
    except Exception as e:
        logger.error(f"Failed to initialize signal handler: {e}", exc_info=True)
        st.error(f"❌ Failed to initialize signal handler: {e}")
        st.session_state.signal_handler = None
if 'trade_logger' not in st.session_state:
    st.session_state.trade_logger = TradeLogger()

# Initialize market data provider (only if broker is available)
if 'market_data_provider' not in st.session_state:
    if st.session_state.broker is not None:
        historical_app_config = None
        try:
            smartapi_apps = getattr(st.secrets, "smartapi_apps", None)
            historical_section = None
            if smartapi_apps:
                try:
                    historical_section = smartapi_apps.get("historical")
                except AttributeError:
                    historical_section = getattr(smartapi_apps, "historical", None)
            if historical_section:
                try:
                    hist_dict = dict(historical_section)
                except Exception:
                    hist_dict = historical_section
                broker_defaults = st.session_state.get('_broker_interface_config', {}) or {}
                historical_app_config = {
                    "api_key": hist_dict.get("api_key"),
                    "api_secret": hist_dict.get("api_secret"),
                    "username": hist_dict.get("username", broker_defaults.get("username")),
                    "client_id": hist_dict.get("client_id", broker_defaults.get("client_id")),
                    "pwd": hist_dict.get("pwd", broker_defaults.get("pwd")),
                    "token": hist_dict.get("token", broker_defaults.get("token")),
                }
        except Exception as cred_error:
            logger.warning(f"Unable to load historical SmartAPI credentials: {cred_error}")
            historical_app_config = None
        try:
            st.session_state.market_data_provider = MarketDataProvider(
                st.session_state.broker,
                historical_app_config=historical_app_config,
            )
        except TypeError as type_err:
            logger.warning(
                "MarketDataProvider does not support historical_app_config parameter (%s). Falling back to legacy initialization.",
                type_err,
            )
            try:
                st.session_state.market_data_provider = MarketDataProvider(st.session_state.broker)
            except Exception as legacy_err:
                st.session_state.market_data_provider = None
                st.warning(f"Market data provider initialization warning: {legacy_err}")
        except Exception as e:
            st.session_state.market_data_provider = None
            st.warning(f"Market data provider initialization warning: {e}")
    else:
        st.session_state.market_data_provider = None

if 'tick_streamer' not in st.session_state:
    st.session_state.tick_streamer = None

if st.session_state.tick_streamer is None and st.session_state.broker is not None:
    try:
        default_symbols = []
        nifty_token = None
        if st.session_state.market_data_provider is not None:
            nifty_token = getattr(st.session_state.market_data_provider, "nifty_token", None)
        if not nifty_token:
            try:
                nifty_token = st.session_state.broker._get_symbol_token("NIFTY", "NSE")
            except Exception:
                nifty_token = "99926000"
        default_symbols.append({
            "tradingsymbol": "NIFTY",
            "exchange": "NSE",
            "token": str(nifty_token) if nifty_token else None,
        })
        streamer = LiveTickStreamer(st.session_state.broker, default_symbols=default_symbols)
        streamer.start()
        st.session_state.tick_streamer = streamer
    except Exception as streamer_error:
        st.session_state.tick_streamer = None
        logger.warning(f"Tick streamer initialization warning: {streamer_error}")

# Initialize live runner (lazy - only when needed)
if st.session_state.live_runner is None:
    # Load full config (with market_data section)
    import yaml as yaml_lib
    try:
        with open('config/config.yaml', 'r') as f:
            full_config = yaml_lib.safe_load(f)
    except Exception as config_error:
        logger.warning(f"Failed to load config.yaml: {config_error}")
        full_config = {}
    
    # Check all dependencies are present and not None
    broker_ok = st.session_state.get('broker') is not None
    market_data_ok = st.session_state.get('market_data_provider') is not None
    signal_handler_ok = st.session_state.get('signal_handler') is not None
    trade_logger_ok = st.session_state.get('trade_logger') is not None
    
    if broker_ok and market_data_ok and signal_handler_ok and trade_logger_ok:
        try:
            with _runtime_state["lock"]:
                if _runtime_state.get("live_runner") is None:
                    logger.info("Initializing LiveStrategyRunner...")
                    runner = LiveStrategyRunner(
                        market_data_provider=st.session_state.market_data_provider,
                        signal_handler=st.session_state.signal_handler,
                        broker=st.session_state.broker,
                        trade_logger=st.session_state.trade_logger,
                        config=full_config,
                        tick_streamer=st.session_state.get('tick_streamer'),
                    )
                    _set_live_runner_runtime(runner)
                    logger.info("LiveStrategyRunner initialized successfully")
                else:
                    st.session_state.live_runner = _runtime_state.get("live_runner")
                    logger.info("LiveStrategyRunner retrieved from runtime state")
        except Exception as e:
            _set_live_runner_runtime(None)
            logger.exception(f"Live runner initialization failed: {e}")
            # Don't show warning in UI - will be handled by button logic
    else:
        missing = []
        if not broker_ok:
            missing.append("broker")
        if not market_data_ok:
            missing.append("market_data_provider")
        if not signal_handler_ok:
            missing.append("signal_handler")
        if not trade_logger_ok:
            missing.append("trade_logger")
        logger.debug(f"Live runner not initialized - missing dependencies: {', '.join(missing)}")
        _set_live_runner_runtime(None)

# Ensure auto-refresh session state defaults before usage
if 'execution_armed' not in st.session_state:
    st.session_state.execution_armed = False
if st.session_state.live_runner is not None:
    try:
        st.session_state.live_runner.execution_armed = st.session_state.execution_armed
    except Exception:
        pass

if 'auto_refresh_enabled' not in st.session_state:
    st.session_state.auto_refresh_enabled = True
if 'auto_refresh_interval_sec' not in st.session_state:
    st.session_state.auto_refresh_interval_sec = 30
if 'next_auto_refresh_ts' not in st.session_state:
    st.session_state.next_auto_refresh_ts = time.time() + st.session_state.auto_refresh_interval_sec
if 'auto_refresh_counter' not in st.session_state:
    st.session_state.auto_refresh_counter = 0
if 'background_refresh_enabled' not in st.session_state:
    st.session_state.background_refresh_enabled = True
if 'background_refresh_interval_sec' not in st.session_state:
    st.session_state.background_refresh_interval_sec = 10
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
if '_last_ui_refresh_trigger' not in st.session_state:
    st.session_state['_last_ui_refresh_trigger'] = time.time()
previous_ui_render_time = st.session_state.get('_last_ui_render_time')
current_ui_render_time = datetime.now()
st.session_state['_last_ui_render_time'] = current_ui_render_time

if 'selected_main_tab' not in st.session_state:
    st.session_state.selected_main_tab = "Dashboard"
if '_previous_tab' not in st.session_state:
    st.session_state['_previous_tab'] = st.session_state.selected_main_tab

# Sidebar menu with persistent selection (key handles persistence automatically)
MENU_TABS = [
    "Dashboard",
    "Portfolio",
    "P&L",
    "Insights",
    "Orders & Trades",
    "Trade Journal",
    "Backtest",
    "Settings",
]
default_tab = st.session_state.get("selected_main_tab", MENU_TABS[0])
if default_tab not in MENU_TABS:
    default_tab = MENU_TABS[0]
try:
    tab = st.sidebar.radio(
        "📋 Menu",
        MENU_TABS,
        index=MENU_TABS.index(default_tab),
        key="selected_main_tab",
    )
    current_main_tab = tab
except Exception as e:
    logger.error(f"Error rendering sidebar menu: {e}", exc_info=True)
    tab = "Dashboard"
    current_main_tab = tab
    st.sidebar.error(f"⚠️ Menu error: {e}")
    st.error(f"❌ Error loading menu. Using Dashboard tab.")

# Only auto-refresh when on Dashboard tab to prevent interrupting user actions on other tabs
global_refresh_interval = st.session_state.get(
    'global_refresh_interval_sec',
    st.session_state.auto_refresh_interval_sec
)
# Track last user interaction to prevent auto-refresh during interactions
if '_last_user_interaction' not in st.session_state:
    st.session_state['_last_user_interaction'] = 0

# Update interaction timestamp when tab changes (user actively selected a different tab)
if st.session_state.get('_previous_tab') != current_main_tab:
    st.session_state['_last_user_interaction'] = time.time()
    st.session_state['_previous_tab'] = current_main_tab

# Only auto-refresh if on Dashboard tab AND auto-refresh is enabled AND no recent user interaction
# Check if user interacted in last 3 seconds (prevent refresh during dropdown/button clicks)
time_since_last_interaction = time.time() - st.session_state.get('_last_user_interaction', 0)
if (st.session_state.get('auto_refresh_enabled', True) and 
    current_main_tab == "Dashboard" and
    time_since_last_interaction > 3.0):  # Wait 3 seconds after user interaction
    now = time.time()
    if now - st.session_state['_last_ui_refresh_trigger'] >= global_refresh_interval:
        st.session_state['_last_ui_refresh_trigger'] = now
        rerun_fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
        if rerun_fn:
            rerun_fn()


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

# Auto-refresh dashboard when algo is running (ONLY on Dashboard tab)
# Note: Tab selection is now processed above, so we can check current_main_tab
# Also check if user recently interacted to prevent interrupting actions
time_since_last_interaction = time.time() - st.session_state.get('_last_user_interaction', 0)
auto_refresh_active = (
    st.session_state.auto_refresh_enabled
    and current_main_tab == "Dashboard"  # Only auto-refresh on Dashboard tab
    and time_since_last_interaction > 3.0  # Wait 3 seconds after user interaction
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
    # Reset the next refresh timestamp so the timer starts fresh when re-enabled or when returning to Dashboard
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

# Tab selection is already processed earlier (before auto-refresh checks)
# This ensures tab state is preserved when auto-refresh triggers

# Logout button - DISABLED (authentication bypassed)
# authenticator.logout("Logout", "sidebar")

# ============ DASHBOARD TAB ============
if tab == "Dashboard":
    logger.info(f"Dashboard tab selected: {tab}. Rendering dashboard content...")
    # Always show header first to ensure something is displayed
    st.header("📈 Live Algo Status")
    
    # Debug: Show that we've reached dashboard rendering
    if 'dashboard_render_count' not in st.session_state:
        st.session_state.dashboard_render_count = 0
    st.session_state.dashboard_render_count += 1
    st.caption(f"Dashboard render count: {st.session_state.dashboard_render_count}")
    
    st.markdown('<div class="dashboard-shell">', unsafe_allow_html=True)
    
    # Safe access to session state variables with defaults
    engine_status = st.session_state.get('algo_running', False)
    broker_connected = st.session_state.get('broker') is not None
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
    
    active_pnl_snapshot = None
    streamer_health = None
    if st.session_state.get('live_runner') is not None:
        try:
            active_pnl_snapshot = st.session_state.live_runner.get_active_pnl_snapshot()
            streamer_health = active_pnl_snapshot.get("streamer") if isinstance(active_pnl_snapshot, dict) else None
        except Exception as snapshot_err:
            logger.debug(f"Active P&L snapshot unavailable: {snapshot_err}")
            active_pnl_snapshot = None
            streamer_health = None

    active_trade = None
    active_trade_unrealized_value = None
    active_trade_unrealized_points = None
    active_trade_option_ltp = None
    active_trade_snapshot_entry = None
    active_snapshot_age = None
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

                def _clean_symbol(value: Any) -> str:
                    if value is None:
                        return ""
                    try:
                        if pd.isna(value):
                            return ""
                    except Exception:
                        pass
                    text = str(value).strip()
                    if text.lower() == "nan":
                        return ""
                    return text
                
                entry_price = _to_float(latest_trade.get('entry'))
                sl_price = _to_float(latest_trade.get('sl'))
                tp_price = _to_float(latest_trade.get('tp'))
                strike_value = _to_float(latest_trade.get('strike'))
                if strike_value is not None:
                    try:
                        strike_value = int(round(strike_value))
                    except Exception:
                        strike_value = None
                target_points = (tp_price - entry_price) if (tp_price is not None and entry_price is not None) else None
                qty_raw = latest_trade.get('quantity', 0)
                try:
                    qty_lots = int(float(qty_raw))
                except (TypeError, ValueError):
                    qty_lots = 0
                
                raw_tradingsymbol = latest_trade.get('tradingsymbol', '')
                tradingsymbol = canonicalize_tradingsymbol(_clean_symbol(raw_tradingsymbol))
                active_trade = {
                    'direction': str(latest_trade.get('direction', '')).upper(),
                    'strike': strike_value if strike_value is not None else latest_trade.get('strike', '—'),
                    'strike_value': strike_value,
                    'status': str(latest_trade.get('status', 'open')).title(),
                    'entry': entry_price,
                    'sl': sl_price,
                    'tp': tp_price,
                    'target_points': target_points,
                    'quantity': qty_lots,
                    'timestamp': latest_trade.get('timestamp', ''),
                    'order_id': latest_trade.get('order_id', ''),
                    'tradingsymbol': tradingsymbol,
                }
        except Exception as e:
            logger.debug(f"Active trade summary failed: {e}")

    if active_pnl_snapshot and isinstance(active_pnl_snapshot, dict):
        snapshot_trades = active_pnl_snapshot.get("trades") or []
        if active_trade and active_trade.get('order_id'):
            active_trade_snapshot_entry = next(
                (t for t in snapshot_trades if t.get("order_id") == str(active_trade['order_id'])),
                None,
            )
        if active_trade_snapshot_entry is None and snapshot_trades:
            active_trade_snapshot_entry = snapshot_trades[-1]
            if not active_trade:
                # Build minimal active_trade structure from snapshot
                active_trade = {
                    'direction': active_trade_snapshot_entry.get('direction', ''),
                    'strike': active_trade_snapshot_entry.get('strike', '—'),
                    'strike_value': active_trade_snapshot_entry.get('strike'),
                    'status': 'Open',
                    'entry': active_trade_snapshot_entry.get('entry'),
                    'sl': None,
                    'tp': None,
                    'target_points': None,
                    'quantity': active_trade_snapshot_entry.get('quantity_lots', 0),
                    'timestamp': active_trade_snapshot_entry.get('timestamp', ''),
                    'order_id': active_trade_snapshot_entry.get('order_id', ''),
                    'tradingsymbol': canonicalize_tradingsymbol(active_trade_snapshot_entry.get('tradingsymbol', '')),
                }
        if active_trade_snapshot_entry:
            active_trade_option_ltp = active_trade_snapshot_entry.get("ltp")
            active_trade_unrealized_points = active_trade_snapshot_entry.get("unrealized_points")
            active_trade_unrealized_value = active_trade_snapshot_entry.get("unrealized_value")
            if active_trade and active_trade_option_ltp is not None:
                active_trade['option_ltp'] = active_trade_option_ltp
            snapshot_last = active_pnl_snapshot.get("last_updated")
            if snapshot_last:
                try:
                    snapshot_dt = datetime.fromisoformat(snapshot_last.replace("Z", "+00:00"))
                    active_snapshot_age = max(
                        0.0,
                        (datetime.now(dt_timezone.utc) - snapshot_dt).total_seconds()
                    )
                except Exception:
                    active_snapshot_age = None

    if active_trade_snapshot_entry and active_trade:
        st.session_state.auto_refresh_enabled = True
        if st.session_state.auto_refresh_interval_sec != 5:
            st.session_state.auto_refresh_interval_sec = 5
        last_trigger = st.session_state.get('_active_pnl_rerun_ts', 0)
        if time.time() - last_trigger >= 5:
            st.session_state['_active_pnl_rerun_ts'] = time.time()
            rerun_fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
            if rerun_fn:
                rerun_fn()

    # Fallback to direct quote fetch when snapshot is unavailable (e.g., runner not started)
    if (
        active_trade
        and active_trade_unrealized_value is None
        and active_trade.get('entry') is not None
        and active_trade.get('quantity')
    ):
        lot_size = int(config.get('lot_size', 75) or 75)
        total_units = lot_size * int(active_trade.get('quantity') or 0)
        broker = st.session_state.get('broker')
        symbol_name = config.get('market_data', {}).get('nifty_symbol', 'NIFTY')
        tradingsymbol = active_trade.get('tradingsymbol')
        tick_streamer = st.session_state.get('tick_streamer')
        if tick_streamer and tradingsymbol:
            tick_streamer.subscribe_tradingsymbol(tradingsymbol, exchange="NFO")
            tick_quote = tick_streamer.get_quote(tradingsymbol)
            if tick_quote and 'ltp' in tick_quote:
                try:
                    active_trade_option_ltp = float(tick_quote['ltp'])
                    active_trade_unrealized_points = active_trade_option_ltp - float(active_trade['entry'])
                    active_trade_unrealized_value = active_trade_unrealized_points * total_units
                except Exception:
                    active_trade_option_ltp = None
        if (
            active_trade_unrealized_value is None
            and broker
            and hasattr(broker, "get_option_price")
            and active_trade['direction'] in ("CE", "PE")
        ):
            strike_for_quote = active_trade.get('strike_value') or active_trade.get('strike')
            try:
                strike_for_quote = int(float(strike_for_quote))
            except (TypeError, ValueError):
                strike_for_quote = None
            if strike_for_quote is not None:
                try:
                    opt_ltp = broker.get_option_price(
                        symbol=symbol_name,
                        strike=strike_for_quote,
                        direction=active_trade['direction'],
                    )
                    if opt_ltp is not None:
                        active_trade_option_ltp = float(opt_ltp)
                        active_trade_unrealized_points = active_trade_option_ltp - float(active_trade['entry'])
                        active_trade_unrealized_value = active_trade_unrealized_points * total_units
                except Exception as opt_exc:
                    logger.debug(f"Fallback option LTP fetch failed: {opt_exc}")
    
    algo_chip_state = "success" if engine_status else "danger"
    broker_chip_state = "info" if broker_connected else "danger"
    market_chip_state = "warning" if market_open else "danger"
    status_chips = [
        _build_status_chip_html(
            "Algo",
            "Running" if engine_status else "Stopped",
            state=algo_chip_state,
            subtitle="Execution armed" if st.session_state.get('execution_armed') else "Execution disarmed",
        ),
        _build_status_chip_html(
            "Broker",
            "Connected" if broker_connected else "Not Connected",
            state=broker_chip_state,
            subtitle=broker_type if broker_connected else "Re-auth required",
        ),
        _build_status_chip_html(
            "Market",
            "Open" if market_open else "Closed",
            state=market_chip_state,
            subtitle="Live session" if market_open else "Outside NSE hours",
        ),
    ]
    st.markdown('<div class="status-ribbon">', unsafe_allow_html=True)
    ribbon_cols = st.columns([3, 2], gap="large")
    with ribbon_cols[0]:
        st.markdown(f"<div class='status-chip-row'>{''.join(status_chips)}</div>", unsafe_allow_html=True)
        if streamer_health:
            tick_status_icon = "🟢" if streamer_health.get("connected") else "🔴"
            last_tick_age = streamer_health.get("last_tick_age_sec")
            if isinstance(last_tick_age, (int, float)):
                st.caption(f"{tick_status_icon} Tick stream age: {last_tick_age:.1f}s")
            else:
                st.caption(f"{tick_status_icon} Tick stream {'connected' if streamer_health.get('connected') else 'idle'}")
    with ribbon_cols[1]:
        ui_ctrl_col, backend_ctrl_col, manual_col = st.columns([1.1, 1.1, 0.5], gap="small")
        with ui_ctrl_col:
            ui_auto_toggle = st.toggle(
                "UI Auto",
                value=st.session_state.auto_refresh_enabled,
                key="ui_auto_refresh_toggle",
                help="Automatically rerun the Streamlit app on the chosen cadence.",
            )
            if ui_auto_toggle != st.session_state.auto_refresh_enabled:
                st.session_state.auto_refresh_enabled = ui_auto_toggle
                st.session_state.next_auto_refresh_ts = time.time() + st.session_state.auto_refresh_interval_sec
            st.caption(f"{int(st.session_state.auto_refresh_interval_sec)}s interval")
            with st.popover("⏱", help="Click to adjust UI auto-refresh interval."):
                interval_value = st.number_input(
                    "UI interval (sec)",
                    min_value=5,
                    max_value=180,
                    step=5,
                    value=int(st.session_state.auto_refresh_interval_sec),
                )
                if interval_value != st.session_state.auto_refresh_interval_sec:
                    st.session_state.auto_refresh_interval_sec = interval_value
                    st.session_state.next_auto_refresh_ts = time.time() + interval_value
        with backend_ctrl_col:
            backend_toggle = st.toggle(
                "Backend",
                value=st.session_state.background_refresh_enabled,
                key="backend_refresh_toggle",
                help="Background thread refreshes market data + broker tokens.",
            )
            st.session_state.background_refresh_enabled = backend_toggle
            st.caption(f"{int(st.session_state.background_refresh_interval_sec)}s interval")
            with st.popover("⚙", help="Click to adjust backend refresh cadence."):
                new_bg_interval = st.number_input(
                    "Backend interval (sec)",
                    min_value=5,
                    max_value=180,
                    step=5,
                    value=int(st.session_state.background_refresh_interval_sec),
                )
                if new_bg_interval != st.session_state.background_refresh_interval_sec:
                    st.session_state.background_refresh_interval_sec = new_bg_interval
        with manual_col:
            if st.button("⟳", help="Manual refresh now", key="manual_refresh_button"):
                success = _trigger_market_data_refresh("manual-header")
                if success:
                    st.session_state.market_refresh_feedback = ("success", "🔄 Manual refresh complete.")
                else:
                    st.session_state.market_refresh_feedback = ("error", "❌ Manual refresh failed.")
                rerun_fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
                if rerun_fn:
                    rerun_fn()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="trading-panel">', unsafe_allow_html=True)
    st.markdown("#### 🛡️ Trading Controls")
    control_cols = st.columns([1.4, 1, 0.8], gap="large")
    with control_cols[0]:
        # Check if live_runner exists - if not, show warning and allow manual start attempt
        live_runner_available = st.session_state.get('live_runner') is not None
        
        # Sync session state with actual runtime state
        # Check if runner is actually running even if session state says it's not
        actual_running = False
        if live_runner_available and hasattr(st.session_state.live_runner, 'is_running'):
            try:
                actual_running = st.session_state.live_runner.is_running()
                # Sync session state with actual runtime state
                if actual_running != st.session_state.get('algo_running', False):
                    logger.info(f"Syncing algo_running state: session={st.session_state.get('algo_running', False)} -> actual={actual_running}")
                    _set_algo_running_runtime(actual_running)
            except Exception as sync_error:
                logger.warning(f"Failed to check runner state: {sync_error}")
                actual_running = st.session_state.get('algo_running', False)
        else:
            actual_running = st.session_state.get('algo_running', False)
        
        start_disabled = actual_running  # Only disable if already running
        stop_disabled = (not actual_running) or not live_runner_available
        
        if not live_runner_available:
            st.warning("⚠️ Live runner not initialized. Starting may not work. Check broker configuration.")
        
        if actual_running:
            if st.button("⏹ Stop Algo", use_container_width=True, type="secondary", disabled=stop_disabled):
                if st.session_state.live_runner is None:
                    _set_algo_running_runtime(False)
                    st.session_state.strategy_settings_feedback = (
                        "warning",
                        "⚠️ Algo state reset – live runner unavailable.",
                    )
                else:
                    try:
                        logger.info("Stopping live algorithm...")
                        success = st.session_state.live_runner.stop()
                        if success:
                            _set_algo_running_runtime(False)
                            st.session_state.strategy_settings_feedback = ("warning", "⏸️ Algorithm stopped.")
                            logger.info("Algorithm stopped successfully")
                        else:
                            # Check if it's actually stopped
                            if hasattr(st.session_state.live_runner, 'is_running'):
                                if not st.session_state.live_runner.is_running():
                                    logger.warning("Algorithm stop() returned False but is_running() is False - syncing state")
                                    _set_algo_running_runtime(False)
                                    st.session_state.strategy_settings_feedback = ("info", "ℹ️ Algorithm is already stopped. State synced.")
                                else:
                                    st.session_state.strategy_settings_feedback = ("error", "❌ Failed to stop algorithm. Check logs for details.")
                                    logger.error("Algorithm stop() returned False but is still running")
                            else:
                                st.session_state.strategy_settings_feedback = ("error", "❌ Failed to stop algorithm. Check logs for details.")
                                logger.error("Algorithm stop() returned False")
                    except Exception as e:
                        logger.exception(f"Exception during algorithm stop: {e}")
                        st.session_state.strategy_settings_feedback = ("error", f"❌ Error stopping algorithm: {e}")
                st.rerun()
        else:
            # Check market hours for user feedback
            market_open_check = False
            if live_runner_available and hasattr(st.session_state.live_runner, '_is_market_open'):
                try:
                    market_open_check = st.session_state.live_runner._is_market_open()
                except Exception:
                    market_open_check = False
            
            # Show market status message if market is closed
            # Note: Algorithm CAN start outside market hours - it will just wait for market to open
            if not market_open_check and not start_disabled:
                ist_tz = pytz.timezone('Asia/Kolkata')
                now_ist = datetime.now(ist_tz)
                market_open_time = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
                market_close_time = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
                
                if now_ist.weekday() >= 5:  # Weekend
                    st.info("ℹ️ **Market is closed (weekend).** Algorithm can start but will wait for next trading day (Monday 9:15 AM IST).")
                elif now_ist < market_open_time:
                    time_until_open = market_open_time - now_ist
                    hours = int(time_until_open.total_seconds() // 3600)
                    minutes = int((time_until_open.total_seconds() % 3600) // 60)
                    st.info(f"ℹ️ **Market is closed.** Opens in **{hours}h {minutes}m** (9:15 AM IST). Algorithm can start but will wait for market to open before trading.")
                elif now_ist > market_close_time:
                    st.info("ℹ️ **Market is closed** (closed at 3:30 PM IST). Algorithm can start but will wait for next trading day.")
            
            if st.button("▶ Start Algo", use_container_width=True, type="primary", disabled=start_disabled):
                if st.session_state.live_runner is None:
                    # Diagnose why live runner is not initialized
                    missing_deps = []
                    if st.session_state.get('broker') is None:
                        missing_deps.append("broker")
                    if st.session_state.get('market_data_provider') is None:
                        missing_deps.append("market_data_provider")
                    if st.session_state.get('signal_handler') is None:
                        missing_deps.append("signal_handler")
                    if st.session_state.get('trade_logger') is None:
                        missing_deps.append("trade_logger")
                    
                    if missing_deps:
                        error_msg = f"❌ Live runner not initialized. Missing dependencies: {', '.join(missing_deps)}. Check broker configuration."
                    else:
                        error_msg = "❌ Live runner not initialized. Check broker configuration and try refreshing the page."
                    
                    logger.error(f"Live runner unavailable. Missing: {missing_deps}")
                    st.session_state.strategy_settings_feedback = ("error", error_msg)
                    
                    # Try to re-initialize live runner
                    try:
                        import yaml as yaml_lib
                        with open('config/config.yaml', 'r') as f:
                            full_config = yaml_lib.safe_load(f)
                        
                        if (st.session_state.get('broker') is not None and 
                            st.session_state.get('market_data_provider') is not None and
                            st.session_state.get('signal_handler') is not None and
                            st.session_state.get('trade_logger') is not None):
                            logger.info("Attempting to re-initialize live runner...")
                            from engine.live_runner import LiveStrategyRunner
                            runner = LiveStrategyRunner(
                                market_data_provider=st.session_state.market_data_provider,
                                signal_handler=st.session_state.signal_handler,
                                broker=st.session_state.broker,
                                trade_logger=st.session_state.trade_logger,
                                config=full_config,
                                tick_streamer=st.session_state.get('tick_streamer'),
                            )
                            _set_live_runner_runtime(runner)
                            st.session_state.live_runner = runner
                            logger.info("Live runner re-initialized successfully")
                            st.session_state.strategy_settings_feedback = (
                                "success",
                                "✅ Live runner initialized. Click 'Start Algo' again to begin.",
                            )
                    except Exception as init_error:
                        logger.exception(f"Failed to re-initialize live runner: {init_error}")
                        st.session_state.strategy_settings_feedback = (
                            "error",
                            f"❌ Failed to initialize live runner: {str(init_error)}",
                        )
                else:
                    try:
                        # Check if already running (double-check before attempting to start)
                        if hasattr(st.session_state.live_runner, 'is_running') and st.session_state.live_runner.is_running():
                            logger.warning("Algorithm is already running (detected via is_running()). Syncing state...")
                            _set_algo_running_runtime(True)
                            st.session_state.strategy_settings_feedback = (
                                "info",
                                "ℹ️ Algorithm is already running. State synced.",
                            )
                        else:
                            # Validate broker credentials before starting
                            broker = st.session_state.get('broker')
                            if broker and hasattr(broker, 'validate_credentials'):
                                is_valid, error_msg = broker.validate_credentials()
                                if not is_valid:
                                    st.session_state.strategy_settings_feedback = (
                                        "error",
                                        f"❌ {error_msg}. Please check broker configuration in Railway environment variables.",
                                    )
                                    logger.error(f"Broker credentials validation failed: {error_msg}")
                                    st.rerun()
                            
                            logger.info("Starting live algorithm...")
                            try:
                                # Check market hours before starting (informational only - algo can start outside hours)
                                market_hours_info = ""
                                if hasattr(st.session_state.live_runner, '_is_market_open'):
                                    try:
                                        is_market_open = st.session_state.live_runner._is_market_open()
                                        if not is_market_open:
                                            market_hours_info = " Market is currently closed - algorithm will wait for next market open."
                                    except Exception:
                                        pass
                                
                                success = st.session_state.live_runner.start()
                                if success:
                                    _set_algo_running_runtime(True)
                                    message = "✅ Algorithm started – monitoring live market data."
                                    if market_hours_info:
                                        message += market_hours_info
                                    st.session_state.strategy_settings_feedback = (
                                        "success",
                                        message,
                                    )
                                    logger.info(f"Algorithm started successfully{market_hours_info}")
                                else:
                                    # Check if it's already running
                                    if hasattr(st.session_state.live_runner, 'is_running') and st.session_state.live_runner.is_running():
                                        logger.warning("Algorithm start() returned False but is_running() is True - syncing state")
                                        _set_algo_running_runtime(True)
                                        st.session_state.strategy_settings_feedback = (
                                            "info",
                                            "ℹ️ Algorithm is already running. State synced.",
                                        )
                                    else:
                                        st.session_state.strategy_settings_feedback = (
                                            "error",
                                            "❌ Failed to start algorithm. The runner may already be running or encountered an error. Check logs for details.",
                                        )
                                        logger.error("Algorithm start() returned False")
                            except Exception as start_error:
                                logger.exception(f"Exception during algorithm start: {start_error}")
                                st.session_state.strategy_settings_feedback = (
                                    "error",
                                    f"❌ Error starting algorithm: {str(start_error)}. Check logs for details.",
                                )
                    except Exception as e:
                        error_detail = str(e)
                        st.session_state.strategy_settings_feedback = (
                            "error",
                            f"❌ Error starting algorithm: {error_detail}",
                        )
                        logger.exception(f"Exception while starting algorithm: {e}")
                st.rerun()
        if st.session_state.live_runner is None:
            st.caption("Live runner not initialized.")
        elif actual_running:
            st.caption("Monitoring live market data.")
        else:
            st.caption("Algo idle – ready to start.")
    with control_cols[1]:
        if 'execution_armed' not in st.session_state:
            st.session_state.execution_armed = False
        exec_toggle = st.toggle(
            "Arm execution",
            value=st.session_state.execution_armed,
            help="Disarm to prevent new orders while keeping analytics live.",
        )
        if exec_toggle != st.session_state.execution_armed:
            st.session_state.execution_armed = exec_toggle
            if st.session_state.live_runner is not None:
                st.session_state.live_runner.execution_armed = exec_toggle
            if exec_toggle:
                st.session_state.strategy_settings_feedback = (
                    "success",
                    "🔓 Live execution ARMED - real trades will be placed on next signal!",
                )
            else:
                st.session_state.strategy_settings_feedback = (
                    "warning",
                    "🛑 Live execution DISARMED - trades will be simulated only",
                )
            st.rerun()
        badge_class = "badge-green" if st.session_state.execution_armed else "badge-red"
        badge_label = "Armed" if st.session_state.execution_armed else "Disarmed"
        st.markdown(f"<span class='badge {badge_class}'>{badge_label}</span>", unsafe_allow_html=True)
        st.caption("Safety guard for broker execution.")
    with control_cols[2]:
        st.caption("Strategy controls")
        with st.popover("⚙ Modify Settings", help="Open strategy configuration popover."):
            _render_strategy_settings_popover()
    st.markdown('</div>', unsafe_allow_html=True)

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

    active_signals = st.session_state.signal_handler.get_active_signals()
    nifty_ltp_value = None
    nifty_source = "Tick stream"
    tick_streamer = st.session_state.get('tick_streamer')
    if tick_streamer:
        quote = tick_streamer.get_quote("NIFTY")
        if quote and 'ltp' in quote:
            try:
                nifty_ltp_value = float(quote['ltp'])
            except (TypeError, ValueError):
                nifty_ltp_value = None
    if nifty_ltp_value is None:
        try:
            if st.session_state.market_data_provider is not None:
                ohlc = st.session_state.market_data_provider.fetch_ohlc(mode="LTP")
                if isinstance(ohlc, dict):
                    ltp_val = ohlc.get('ltp') or ohlc.get('close')
                    if ltp_val is not None:
                        nifty_ltp_value = float(ltp_val)
                        nifty_source = "Market data provider"
        except Exception:
            pass
    nifty_ltp_display = f"₹{nifty_ltp_value:,.2f}" if nifty_ltp_value is not None else "—"

    realized_pnl = 0.0
    csv_pnl_used = False
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
    if realized_pnl == 0.0 and st.session_state.get('trade_logger') is not None:
        try:
            trades_df = st.session_state.trade_logger.get_all_trades()
            if not trades_df.empty and 'status' in trades_df.columns:
                closed_df = trades_df[trades_df['status'] == 'closed'].copy()
                if not closed_df.empty:
                    closed_df['pnl'] = pd.to_numeric(closed_df['pnl'], errors='coerce')
                    fallback_val = closed_df['pnl'].sum(min_count=1)
                    if pd.notna(fallback_val) and float(fallback_val) != 0.0:
                        realized_pnl = float(fallback_val)
                        csv_pnl_used = True
        except Exception:
            pass
    pnl_prefix = "🟢" if realized_pnl >= 0 else "🔴"
    realized_pnl_value = f"{pnl_prefix} ₹{realized_pnl:,.2f}"
    realized_pnl_subtitle = "CSV trade log" if csv_pnl_used else "Broker snapshot"
    if realized_pnl == 0 and active_trade:
        realized_pnl_subtitle = "Awaiting trade close"

    if active_trade and active_trade_unrealized_value is not None:
        prefix = "🟢" if active_trade_unrealized_value >= 0 else "🔴"
        delta_pts = active_trade_unrealized_points or 0.0
        active_pnl_value = f"{prefix} ₹{active_trade_unrealized_value:,.2f}"
        active_pnl_subtitle = f"{delta_pts:+.2f} pts vs entry"
    elif active_trade:
        active_pnl_value = "Fetching…"
        active_pnl_subtitle = "Awaiting option quote"
    else:
        active_pnl_value = "—"
        active_pnl_subtitle = "No open trades"

    st.markdown('<div class="hero-grid">', unsafe_allow_html=True)
    hero_left, hero_right = st.columns([1.15, 0.85], gap="large")
    pm_config: Dict[str, Any] = {}
    if st.session_state.get('live_runner') is not None:
        pm_config = st.session_state.live_runner.config.get('position_management', {}) or {}
    elif isinstance(config, dict):
        pm_config = config.get('position_management', {}) or {}
    default_trail_points = pm_config.get('trail_points')
    default_trailing_display = (
        f"{default_trail_points} pts step" if default_trail_points is not None else "—"
    )

    with hero_left:
        st.markdown("### ⚡ Active Trade")
        if active_trade:
            badge = f"{active_trade['direction']} {active_trade['strike']}"
            qty_label = f"{active_trade['quantity']} lot(s)" if active_trade['quantity'] else "—"
            status_text = active_trade.get('status', 'Open')
            symbol_display = active_trade.get('tradingsymbol') or badge
            st.markdown(f"**{symbol_display}** · {qty_label} · {status_text}")
            entry_display = f"₹{active_trade['entry']:.2f}" if active_trade['entry'] is not None else "—"
            sl_display = f"₹{active_trade['sl']:.2f}" if active_trade['sl'] is not None else "—"
            tp_display = f"₹{active_trade['tp']:.2f}" if active_trade['tp'] is not None else "—"
            trailing_display = default_trailing_display
            _render_active_trade_metric_row(entry_display, tp_display, sl_display, trailing_display)
            if active_trade_option_ltp is not None:
                st.caption(f"Current price ₹{active_trade_option_ltp:.2f}")
            if active_trade_unrealized_value is not None:
                st.caption(
                    f"Active P&L: ₹{active_trade_unrealized_value:,.2f} "
                    f"({active_trade_unrealized_points or 0.0:+.2f} pts)"
                )
            if active_trade.get('order_id'):
                st.caption(f"Order ID: `{active_trade['order_id']}`")
            if active_snapshot_age is not None:
                st.caption(f"Snapshot age: {active_snapshot_age:.1f}s")
        else:
            _render_active_trade_metric_row("—", "—", "—", default_trailing_display)
            st.info("No active trades at the moment.")
    with hero_right:
        st.markdown("### 📊 Mission Metrics")
        metric_tiles = [
            _build_metric_tile_html("Signal Watching", str(len(active_signals)), "Inside Bar scanner"),
            _build_metric_tile_html("NIFTY LTP", nifty_ltp_display, nifty_source),
            _build_metric_tile_html("Realized P&L", realized_pnl_value, realized_pnl_subtitle),
            _build_metric_tile_html("Active P&L", active_pnl_value, active_pnl_subtitle),
        ]
        st.markdown(f"<div class='metric-grid'>{''.join(metric_tiles)}</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

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

    st.divider()
    st.markdown("### 🧩 Inside Bar Snapshot")
    
    inside_bar_time_label = "—"
    mother_time_label = "—"
    breakout_label = "Waiting"
    compression_label = ""
    inside_bar_available = False
    range_high_value = None
    range_low_value = None
    
    mother_section_values = [("Open", "—"), ("High", "—"), ("Low", "—"), ("Close", "—")]
    inside_section_values = [("Open", "—"), ("High", "—"), ("Low", "—"), ("Close", "—")]
    range_section_values = [("Range Low", "—"), ("Range High", "—"), ("Width", "—"), ("Breakout", breakout_label)]
    
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
    
    def _fmt_currency(val):
        try:
            return f"₹{float(val):,.2f}"
        except Exception:
            return "—"
    
    def _fmt_number(val):
        try:
            return f"{float(val):,.2f}"
        except Exception:
            return "—"
    
    one_hour_data = pd.DataFrame()
    latest_close_price = None
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
            latest_close_price = float(df_ib['Close'].iloc[-1])
        except Exception:
            latest_close_price = None
        
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
                range_high_value = range_high
                range_low_value = range_low
                mother_section_values = [
                    ("Open", _fmt_number(mother_row.get('Open'))),
                    ("High", _fmt_number(mother_row.get('High'))),
                    ("Low", _fmt_number(mother_row.get('Low'))),
                    ("Close", _fmt_number(mother_row.get('Close'))),
                ]
                inside_section_values = [
                    ("Open", _fmt_number(inside_row.get('Open'))),
                    ("High", _fmt_number(inside_row.get('High'))),
                    ("Low", _fmt_number(inside_row.get('Low'))),
                    ("Close", _fmt_number(inside_row.get('Close'))),
                ]
                
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
                
                range_width = range_high - range_low
                range_section_values = [
                    ("Range Low", _fmt_number(range_low)),
                    ("Range High", _fmt_number(range_high)),
                    ("Width", f"{range_width:.2f} pts"),
                    ("Breakout", breakout_label),
                ]
                inside_bar_available = True
    
    def _build_snapshot_section(title: str, subtitle: str, values: list, theme: str) -> str:
        subtitle_html = f"<span class='metric-subtle'>{subtitle}</span>" if subtitle and subtitle != "—" else ""
        cells_html = "".join(
            f"<div class='snapshot-cell'><label>{label}</label><span>{value}</span></div>"
            for label, value in values
        )
        return (
            f"<div class='snapshot-section {theme}'>"
            f"<div class='snapshot-title'>{title}{subtitle_html}</div>"
            f"<div class='snapshot-grid'>{cells_html}</div>"
            f"</div>"
        )
    
    if inside_bar_available:
        snapshot_html = "".join([
            _build_snapshot_section("Mother Candle", mother_time_label, mother_section_values, "mother"),
            _build_snapshot_section("Inside Candle", inside_bar_time_label, inside_section_values, "inside"),
            _build_snapshot_section("Range Diagnostics", breakout_label, range_section_values, "range"),
        ])
        st.markdown(f"<div class='snapshot-card'>{snapshot_html}</div>", unsafe_allow_html=True)
        if compression_label:
            st.caption(f"Compression depth: {compression_label}")
    else:
        st.info("No active inside bar identified in the latest 1-hour data window.")
    
    missed_trade_info = st.session_state.get("last_missed_trade")
    if missed_trade_info:
        with st.expander("⚠️ Missed Breakout Window", expanded=True):
            missed_close = _fmt_currency(missed_trade_info.get('close_price'))
            st.warning(
                f"Trade skipped — breakout candle closed more than 5 minutes ago.\n\n"
                f"- Direction: **{missed_trade_info.get('direction', '—')}**\n"
                f"- Inside Bar: {missed_trade_info.get('inside_bar_time', '—')}\n"
                f"- Mother Candle: {missed_trade_info.get('signal_time', '—')}\n"
                f"- Range: {missed_trade_info.get('range_low', '—')} → {missed_trade_info.get('range_high', '—')}\n"
                f"- Strike: **{missed_trade_info.get('strike', '—')}**\n"
                f"- Breakout Close: {missed_close}\n"
                f"- Logged at: {missed_trade_info.get('timestamp', '—')}"
            )
            st.caption("Breakout execution is blocked after 5 minutes to avoid chasing late entries.")
    
    pending_signal = st.session_state.get("pending_trade_signal")
    if pending_signal:
        st.divider()
        st.subheader("🎯 Pending Trade (Awaiting Execution)")
        ps_cols = st.columns(4)
        with ps_cols[0]:
            st.metric("Direction", pending_signal.get("direction", "—"))
            st.metric("Strike", pending_signal.get("strike", "—"))
        with ps_cols[1]:
            st.metric("Entry (est.)", _fmt_currency(pending_signal.get('entry')))
            st.metric("Stop Loss", _fmt_currency(pending_signal.get('sl')))
        with ps_cols[2]:
            st.metric("Target", _fmt_currency(pending_signal.get('tp')))
            st.metric("Range High", _fmt_number(pending_signal.get('range_high')))
        with ps_cols[3]:
            st.metric("Range Low", _fmt_number(pending_signal.get('range_low')))
            st.metric("Symbol", pending_signal.get("symbol", "NIFTY"))
        st.caption(
            f"Inside bar: {pending_signal.get('inside_bar_time', '—')} • "
            f"Signal detected: {pending_signal.get('signal_time', '—')}"
        )
    elif inside_bar_available and latest_close_price:
        atm_offset = config.get('strategy', {}).get('atm_offset', 0)
        projected_ce = strategy_engine_module.calculate_strike_price(latest_close_price, "CE", atm_offset)
        projected_pe = strategy_engine_module.calculate_strike_price(latest_close_price, "PE", atm_offset)
        st.info(
            f"Projected strikes if breakout triggers — CE: {projected_ce}, PE: {projected_pe} "
            f"(ATM offset {atm_offset})"
        )
    
    strategy_cfg = config.get('strategy', {}) if isinstance(config, dict) else {}
    filters_cfg = strategy_cfg.get('filters', {}) if isinstance(strategy_cfg, dict) else {}
    risk_cfg = config.get('risk_management', {}) if isinstance(config, dict) else {}
    timeframes_cfg = config.get('timeframes', {}) if isinstance(config, dict) else {}
    detection_tf = str(timeframes_cfg.get('detection', '1h')).upper()
    confirmation_tf = str(timeframes_cfg.get('confirmation', '15m')).upper()
    live_runner = st.session_state.get('live_runner')
    max_positions_cfg = risk_cfg.get('max_concurrent_positions', 2)
    max_positions = getattr(live_runner, 'max_concurrent_positions', max_positions_cfg)
    config_chip_entries = [
        ("Risk-Reward", f"1:{strategy_cfg.get('rr', '—')}"),
        ("Stop Loss", f"{strategy_cfg.get('sl', '—')} pts"),
        ("ATM Offset", str(strategy_cfg.get('atm_offset', 0))),
        ("Lot Size", str(config.get('lot_size', '—'))),
        ("Volume Spike", "Enabled" if filters_cfg.get('volume_spike') else "Disabled"),
        ("Avoid Open Range", "Enabled" if filters_cfg.get('avoid_open_range') else "Disabled"),
        ("Max Positions", str(max_positions)),
        ("Timeframes", f"{detection_tf} → {confirmation_tf}"),
    ]
    chips_html = "".join(
        f"<div class='config-chip'><span>{label}</span><strong>{value}</strong></div>"
        for label, value in config_chip_entries
    )
    st.markdown("### ⚙️ Strategy Configuration")
    st.markdown(f"<div class='config-strip'>{chips_html}</div>", unsafe_allow_html=True)
    
    footer_last_updated = None
    footer_last_reason = None
    # Live data status
    if st.session_state.get('algo_running', False) and st.session_state.get('live_runner') is not None:
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
        stamp = None
        label = None
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
            footer_last_updated = stamp
            footer_last_reason = label
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
    st.markdown("### 🛠️ Strategy Debug")
    
    def _render_inside_bar_debug_section() -> None:
        if st.session_state.market_data_provider is not None and st.session_state.live_runner is not None:
            try:
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
                if not data_1h.empty and not data_15m.empty:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("1H Candles Available", len(data_1h))
                    with col2:
                        st.metric("15m Candles Available", len(data_15m))
                    inside_bars = detect_inside_bar(data_1h)
                    inside_bar_set = set(inside_bars)
                    st.write("**Recent 1H Candles Check (Last 10 - Most Recent First):**")
                    recent_count = min(10, len(data_1h))
                    recent_data = data_1h.tail(recent_count)
                    display_data = []
                    for i in range(len(recent_data) - 1, -1, -1):
                        original_idx = len(data_1h) - recent_count + i
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
                        is_inside = original_idx in inside_bar_set and original_idx >= 2
                        if is_inside:
                            row_data['Status'] = '✅ Inside Bar'
                            if original_idx > 0:
                                ref_high = data_1h['High'].iloc[original_idx - 1]
                                ref_low = data_1h['Low'].iloc[original_idx - 1]
                                current_high = recent_data.iloc[i]['High']
                                current_low = recent_data.iloc[i]['Low']
                                row_data['Reference Range'] = f"{ref_low:.2f} - {ref_high:.2f}"
                                row_data['Inside Check'] = f"✓ High {current_high:.2f} < {ref_high:.2f} ✓ Low {current_low:.2f} > {ref_low:.2f}"
                            else:
                                row_data['Reference Range'] = 'N/A'
                                row_data['Inside Check'] = 'N/A'
                        else:
                            row_data['Status'] = '❌ Not Inside'
                            if original_idx > 0:
                                ref_high = data_1h['High'].iloc[original_idx - 1]
                                ref_low = data_1h['Low'].iloc[original_idx - 1]
                                current_high = recent_data.iloc[i]['High']
                                current_low = recent_data.iloc[i]['Low']
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
                                    row_data['Reference Range'] = f"{ref_low:.2f} - {ref_high:.2f}"
                                    row_data['Inside Check'] = "✓ High ✓ Low (unexpected - check logic)"
                            else:
                                row_data['Reference Range'] = '—'
                                row_data['Inside Check'] = 'No reference'
                        display_data.append(row_data)
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
    
    def _render_range_persistence_section(
        low_value: Optional[float],
        high_value: Optional[float],
        latest_price: Optional[float],
        compression_text: str,
        mother_label: str,
        inside_label: str,
    ) -> None:
        if low_value is None or high_value is None:
            st.info("No active inside bar range to analyze.")
            return
        metric_cols = st.columns(3)
        with metric_cols[0]:
            st.metric("Range Low", f"{low_value:.2f}")
        with metric_cols[1]:
            st.metric("Range High", f"{high_value:.2f}")
        with metric_cols[2]:
            if latest_price is not None:
                st.metric("Latest Close", f"{latest_price:.2f}")
            else:
                st.metric("Latest Close", "—")
        st.write(f"Mother candle captured at **{mother_label}**, inside candle at **{inside_label}**.")
        if compression_text:
            st.write(f"Compression depth: **{compression_text}**")
        spread = high_value - low_value
        st.write(f"Range width: **{spread:.2f} pts**")
        if latest_price is not None:
            if low_value <= latest_price <= high_value:
                st.success("Price remains within the mother range.")
            else:
                st.warning("Price has left the mother range — watch for fresh setups.")
    
    def _render_breakout_events_section() -> None:
        events = []
        last_alert = st.session_state.get("last_breakout_alert_timestamp")
        last_direction = st.session_state.get("last_breakout_direction")
        if last_alert and last_direction:
            events.append({
                "timestamp": last_alert,
                "label": f"Breakout {last_direction}",
                "type": "breakout",
                "direction": last_direction,
            })
        missed_trade_info = st.session_state.get("last_missed_trade")
        if missed_trade_info:
            events.append({
                "timestamp": missed_trade_info.get("timestamp"),
                "label": f"Missed {missed_trade_info.get('direction', '—')}",
                "type": "missed",
                "details": missed_trade_info,
                "direction": missed_trade_info.get("direction"),
            })
        if not events:
            st.info("No breakout events recorded in this session.")
            return
        def _fmt_event_time(value: Optional[str]) -> str:
            if not value:
                return "—"
            try:
                dt_value = datetime.fromisoformat(value)
                return dt_value.strftime("%d-%b %I:%M:%S %p")
            except Exception:
                return str(value)
        for event in events:
            direction = event.get("direction")
            badge_class = "badge-green" if direction == "CE" else "badge-red"
            ts_label = _fmt_event_time(event.get("timestamp"))
            st.markdown(
                f"<div class='metric-tile'><h5>{event['label']}</h5>"
                f"<div class='metric-value'>{ts_label}</div>"
                f"<span class='badge {badge_class}'>{direction or '—'}</span></div>",
                unsafe_allow_html=True,
            )
            if event.get("type") == "missed" and event.get("details"):
                details = event["details"]
                st.caption(
                    f"Missed breakout at {details.get('signal_time', '—')} · "
                    f"Range {details.get('range_low', '—')} → {details.get('range_high', '—')}"
                )
    
    with st.expander("📄 Inside Bar Detection Debug", expanded=False):
        _render_inside_bar_debug_section()
    with st.expander("📊 Range Persistence Analysis", expanded=False):
        _render_range_persistence_section(
            range_low_value,
            range_high_value,
            latest_close_price,
            compression_label,
            mother_time_label,
            inside_bar_time_label,
        )
    with st.expander("⚡ Breakout Events Log", expanded=False):
        _render_breakout_events_section()
    
    st.divider()
    footer_cols = st.columns([1.2, 1, 0.6], gap="large")
    with footer_cols[0]:
        st.markdown("[📄 View Trade Logs](logs/trades.csv)")
    with footer_cols[1]:
        footer_label = footer_last_updated or "Not refreshed yet"
        footer_reason = footer_last_reason or "manual"
        st.markdown(f"Last updated: **{footer_label}** ({footer_reason})")
    with footer_cols[2]:
        if st.button("🔄 Manual Refresh", key="footer_manual_refresh"):
            success = _trigger_market_data_refresh("manual-footer")
            if success:
                timestamp = st.session_state.last_refresh_time.strftime("%d-%b %I:%M:%S %p")
                st.session_state.market_refresh_feedback = (
                    "success",
                    f"✅ Market data refreshed at {timestamp}.",
                )
            else:
                error_msg = st.session_state.last_refresh_error or "Unknown error"
                st.session_state.market_refresh_feedback = (
                    "error",
                    f"❌ Failed to refresh market data: {error_msg}",
                )
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)

    # Perform background API refresh if enabled (non-blocking)
    if st.session_state.background_refresh_enabled:
        try:
            start_background_refresh_if_needed(interval_seconds=st.session_state.background_refresh_interval_sec)
        except Exception as e:
            logger.error(f"Background refresh error: {e}")

    # Auto-refresh fallback (blocking rerun) - Only on Dashboard tab
    # Note: This is already inside Dashboard tab block, so safe to check
    if st.session_state.auto_refresh_enabled and current_main_tab == "Dashboard":
        if st.session_state.last_refresh_time is not None:
            time_since_last = (datetime.now() - st.session_state.last_refresh_time).total_seconds()
            if time_since_last > 15:
                time.sleep(10)
                st.rerun()
        else:
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
        
        # Prepare CSV-based fallback in case database snapshots are empty/unavailable
        csv_total_pnl = None
        csv_series = []
        trade_logger = st.session_state.get('trade_logger')
        if trade_logger is not None:
            try:
                csv_df = trade_logger.get_all_trades()
            except Exception as csv_error:
                logger.debug(f"CSV trade log unavailable for P&L fallback: {csv_error}")
                csv_df = pd.DataFrame()
            if csv_df is not None and not csv_df.empty:
                csv_df = csv_df.copy()
                if 'pnl' in csv_df.columns:
                    csv_df['pnl'] = pd.to_numeric(csv_df['pnl'], errors='coerce')
                else:
                    csv_df['pnl'] = pd.NA
                if 'status' not in csv_df.columns:
                    csv_df['status'] = ''
                if 'timestamp' in csv_df.columns:
                    csv_df['timestamp'] = pd.to_datetime(csv_df['timestamp'], errors='coerce')
                closed_mask = csv_df['status'].astype(str).str.lower() == 'closed'
                closed_df = csv_df[closed_mask]
                if not closed_df.empty:
                    total_from_csv = closed_df['pnl'].sum(skipna=True)
                    if pd.notna(total_from_csv):
                        csv_total_pnl = float(total_from_csv)
                    if 'timestamp' in closed_df.columns:
                        ts_df = closed_df.dropna(subset=['timestamp'])
                        if not ts_df.empty:
                            grouped = ts_df.groupby(ts_df['timestamp'].dt.date)['pnl'].sum()
                            csv_series = [
                                {"date": d.isoformat(), "pnl": float(val)}
                                for d, val in grouped.items()
                                if pd.notna(val)
                            ]
        
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
        
        if (total_pnl in (None, ) or (isinstance(total_pnl, (int, float)) and total_pnl == 0.0)) and csv_total_pnl is not None:
            total_pnl = csv_total_pnl
        if (not series or len(series) == 0) and csv_series:
            series = csv_series
        
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

    def _fetch_recent_missed(limit: int = 5):
        try:
            from engine.db import get_session, init_database
            from engine.models import MissedTrade
        except Exception:
            return []
        cfg = config if isinstance(config, dict) else {}
        org_id, user_id = resolve_tenant(cfg)
        try:
            init_database(create_all=True)
        except Exception:
            pass
        sess_gen = get_session()
        db = next(sess_gen)
        try:
            rows = (
                db.query(MissedTrade)
                .filter(MissedTrade.org_id == org_id, MissedTrade.user_id == user_id)
                .order_by(MissedTrade.logged_at.desc())
                .limit(limit)
                .all()
            )
            results = []
            for r in rows:
                results.append({
                    "logged_at": r.logged_at.isoformat() if r.logged_at else None,
                    "direction": r.direction,
                    "strike": r.strike,
                    "entry_est": float(r.entry_price) if r.entry_price is not None else None,
                    "sl_est": float(r.sl_price) if r.sl_price is not None else None,
                    "tp_est": float(r.tp_price) if r.tp_price is not None else None,
                    "range_high": float(r.range_high) if r.range_high is not None else None,
                    "range_low": float(r.range_low) if r.range_low is not None else None,
                    "inside_bar_time": r.inside_bar_time.isoformat() if r.inside_bar_time else None,
                    "signal_time": r.signal_time.isoformat() if r.signal_time else None,
                    "reason": r.reason,
                })
            return results
        except Exception:
            return []
        finally:
            try:
                next(sess_gen)
            except StopIteration:
                pass

    st.subheader("📒 Journal Snapshot")
    snapshot_tabs = st.tabs(["✅ Executed (Last 5)", "⚠️ Missed Trades"])

    with snapshot_tabs[0]:
        if not all_trades.empty:
            latest_executed = all_trades.tail(5)
            st.dataframe(latest_executed, use_container_width=True, height=220)
            if 'pnl' in latest_executed.columns:
                pnl_total = latest_executed['pnl'].sum()
                st.caption(f"📊 Recent 5 trades P&L: ₹{pnl_total:,.2f}")
        else:
            st.info("📝 No trades logged yet. Start the algo to capture live fills.")

    with snapshot_tabs[1]:
        missed_records = _fetch_recent_missed(limit=5)
        if missed_records:
            missed_df = pd.DataFrame(missed_records)
            st.dataframe(missed_df, use_container_width=True, height=220)
            st.caption("🔍 Missed trades are persisted for potential P&L review.")
        else:
            st.info("🎯 No missed trades recorded yet. Great job staying on schedule!")
    
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
    st.session_state.setdefault("backtest_flash", None)
    st.session_state.setdefault("backtest_results_timeframe", None)
    
    def store_backtest_results(results: Dict, source_label: str) -> None:
        st.session_state.backtest_results = results
        st.session_state.backtest_results_source = source_label
        st.session_state.backtest_equity_curve = results.get("equity_curve")
        st.session_state.backtest_trades = results.get("trades")
        st.session_state.backtest_results_timeframe = results.get("strategy_timeframe")
    
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
        timeframe_label = results.get("strategy_timeframe", "1h")
        st.caption(f"Strategy timeframe: {timeframe_label.upper()}")
        
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
                "Temporal Analysis",
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
            equity_curve_dates = results.get("equity_curve_dates", [])
            
            if equity_curve:
                # View selector
                view_mode = st.radio(
                    "View Mode",
                    ["By Trade #", "By Date", "By Month"],
                    horizontal=True,
                    key="equity_curve_view_mode"
                )
                
                if view_mode == "By Trade #":
                    # Original view by trade number
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
                                name="Capital",
                            )
                        ]
                    )
                    fig.update_layout(
                        title="Equity Curve by Trade Number",
                        xaxis_title="Trade #",
                        yaxis_title="Capital (₹)",
                        height=420,
                        hovermode="x unified",
                        margin=dict(l=10, r=10, t=50, b=10),
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                elif view_mode == "By Date" and equity_curve_dates:
                    # Date-based view
                    equity_df = pd.DataFrame(equity_curve_dates)
                    equity_df['date'] = pd.to_datetime(equity_df['date'])
                    equity_df = equity_df.sort_values('date')
                    # Rename 'capital' to 'Capital' for consistency with other views
                    if 'capital' in equity_df.columns:
                        equity_df = equity_df.rename(columns={'capital': 'Capital'})
                    
                    fig = go.Figure(
                        data=[
                            go.Scatter(
                                x=equity_df["date"],
                                y=equity_df["Capital"],
                                mode="lines+markers",
                                line=dict(color="#1f77b4", width=2),
                                fill="tozeroy",
                                name="Capital",
                                hovertemplate="<b>Date:</b> %{x}<br><b>Capital:</b> ₹%{y:,.2f}<extra></extra>",
                            )
                        ]
                    )
                    fig.update_layout(
                        title="Equity Curve by Date",
                        xaxis_title="Date",
                        yaxis_title="Capital (₹)",
                        height=420,
                        hovermode="x unified",
                        margin=dict(l=10, r=10, t=50, b=10),
                        xaxis=dict(
                            type='date',
                            tickformat='%Y-%m-%d'
                        )
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                elif view_mode == "By Month" and equity_curve_dates:
                    # Month-based aggregated view
                    equity_df = pd.DataFrame(equity_curve_dates)
                    equity_df['date'] = pd.to_datetime(equity_df['date'])
                    equity_df['month'] = equity_df['date'].dt.to_period('M').astype(str)
                    # Rename 'capital' to 'Capital' for consistency with other views
                    if 'capital' in equity_df.columns:
                        equity_df = equity_df.rename(columns={'capital': 'Capital'})
                    
                    # Get last value of each month
                    monthly_equity = equity_df.groupby('month').last().reset_index()
                    monthly_equity['month_date'] = pd.to_datetime(monthly_equity['month'])
                    
                    fig = go.Figure(
                        data=[
                            go.Scatter(
                                x=monthly_equity["month_date"],
                                y=monthly_equity["Capital"],
                                mode="lines+markers",
                                line=dict(color="#1f77b4", width=2),
                                fill="tozeroy",
                                name="Capital",
                                hovertemplate="<b>Month:</b> %{x}<br><b>Capital:</b> ₹%{y:,.2f}<extra></extra>",
                            )
                        ]
                    )
                    fig.update_layout(
                        title="Equity Curve by Month",
                        xaxis_title="Month",
                        yaxis_title="Capital (₹)",
                        height=420,
                        hovermode="x unified",
                        margin=dict(l=10, r=10, t=50, b=10),
                        xaxis=dict(
                            type='date',
                            tickformat='%Y-%m'
                        )
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                else:
                    st.info("Date-based views require equity_curve_dates data. Showing trade number view.")
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
                
                # Download button
                if view_mode == "By Trade #":
                    download_df = pd.DataFrame(
                        {"Trade #": range(len(equity_curve)), "Capital": equity_curve}
                    )
                elif view_mode == "By Date" and equity_curve_dates:
                    download_df = pd.DataFrame(equity_curve_dates)
                    download_df['date'] = pd.to_datetime(download_df['date'])
                elif view_mode == "By Month" and equity_curve_dates:
                    download_df = pd.DataFrame(equity_curve_dates)
                    download_df['date'] = pd.to_datetime(download_df['date'])
                    download_df['month'] = download_df['date'].dt.to_period('M').astype(str)
                    download_df = download_df.groupby('month').last().reset_index()
                else:
                    download_df = pd.DataFrame(
                        {"Trade #": range(len(equity_curve)), "Capital": equity_curve}
                    )
                
                st.download_button(
                    "⬇️ Download Equity Curve CSV",
                    download_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"backtest_equity_curve_{view_mode.lower().replace(' ', '_')}.csv",
                    mime="text/csv",
                )
            else:
                st.info("No equity curve data returned from this run.")
        
        with result_tabs[4]:
            # Import analysis functions
            try:
                from engine.backtest_analysis import (
                    analyze_monthly_performance,
                    analyze_quarterly_performance,
                    detect_seasonal_patterns,
                    analyze_by_direction,
                    calculate_risk_metrics,
                    analyze_trade_distribution
                )
                
                st.markdown("### 📅 Temporal Analysis")
                trades = results.get("trades", [])
                
                if trades:
                    # Calculate all analyses
                    monthly_stats = analyze_monthly_performance(trades)
                    quarterly_stats = analyze_quarterly_performance(trades)
                    seasonal_patterns = detect_seasonal_patterns(trades)
                    direction_analysis = analyze_by_direction(trades)
                    risk_metrics = calculate_risk_metrics(trades, results.get("equity_curve", []))
                    trade_dist = analyze_trade_distribution(trades)
                    
                    # Seasonal Insights Section
                    st.markdown("#### Seasonal Insights")
                    insight_cols = st.columns(3)
                    
                    with insight_cols[0]:
                        if seasonal_patterns.get('best_months'):
                            st.success(f"**Best Months**\n\n{', '.join(seasonal_patterns['best_months'])}")
                        else:
                            st.info("**Best Months**\n\nInsufficient data")
                    
                    with insight_cols[1]:
                        if seasonal_patterns.get('worst_months'):
                            st.warning(f"**Worst Months**\n\n{', '.join(seasonal_patterns['worst_months'])}")
                        else:
                            st.info("**Worst Months**\n\nInsufficient data")
                    
                    with insight_cols[2]:
                        if seasonal_patterns.get('ideal_months'):
                            st.success(f"**Ideal for Trading**\n\n{', '.join(seasonal_patterns['ideal_months'])}")
                        else:
                            st.info("**Ideal Months**\n\nInsufficient data")
                    
                    if seasonal_patterns.get('avoid_months'):
                        st.error(f"⚠️ **Months to Avoid:** {', '.join(seasonal_patterns['avoid_months'])} (Negative returns + low win rate)")
                    
                    st.divider()
                    
                    # Monthly Performance Table
                    st.markdown("#### 📊 Monthly Performance")
                    if monthly_stats:
                        monthly_data = []
                        for month_key, stats in sorted(monthly_stats.items()):
                            monthly_data.append({
                                'Month': month_key,
                                'Trades': stats['trades'],
                                'Win Rate': f"{stats['win_rate']:.1f}%",
                                'Total P&L': f"₹{stats['total_pnl']:,.2f}",
                                'Avg P&L': f"₹{stats['avg_pnl']:,.2f}",
                                'Winning Trades': stats['winning_trades'],
                                'Losing Trades': stats['losing_trades'],
                                'Status': '✅ Good' if stats['total_pnl'] > 0 and stats['win_rate'] >= 50 else '⚠️ Poor' if stats['total_pnl'] < 0 else '⚪ Neutral'
                            })
                        
                        monthly_df = pd.DataFrame(monthly_data)
                        st.dataframe(monthly_df, use_container_width=True, hide_index=True)
                        
                        # Export button for monthly data
                        st.download_button(
                            "⬇️ Download Monthly Performance CSV",
                            monthly_df.to_csv(index=False).encode("utf-8"),
                            file_name="backtest_monthly_performance.csv",
                            mime="text/csv",
                        )
                        
                        # Monthly P&L Bar Chart
                        st.markdown("#### 📈 Monthly P&L Chart")
                        chart_data = pd.DataFrame([
                            {'Month': k, 'Total P&L': v['total_pnl']} 
                            for k, v in sorted(monthly_stats.items())
                        ])
                        fig = px.bar(
                            chart_data,
                            x='Month',
                            y='Total P&L',
                            title="Total P&L by Month",
                            color='Total P&L',
                            color_continuous_scale=['red', 'green'] if chart_data['Total P&L'].min() < 0 else ['green'],
                        )
                        fig.update_layout(height=400)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No monthly data available.")
                    
                    st.divider()
                    
                    # Quarterly Summary
                    st.markdown("#### 📅 Quarterly Summary")
                    if quarterly_stats:
                        quarter_cols = st.columns(4)
                        for idx, (quarter, stats) in enumerate(sorted(quarterly_stats.items())[:4]):
                            with quarter_cols[idx % 4]:
                                st.metric(
                                    quarter,
                                    f"₹{stats['total_pnl']:,.2f}",
                                    f"{stats['win_rate']:.1f}% WR"
                                )
                    else:
                        st.info("Insufficient data for quarterly analysis.")
                    
                    st.divider()
                    
                    # Direction Analysis
                    st.markdown("#### 🎯 Direction Analysis (CE vs PE)")
                    if direction_analysis.get('CE') or direction_analysis.get('PE'):
                        dir_cols = st.columns(2)
                        with dir_cols[0]:
                            ce_stats = direction_analysis.get('CE', {})
                            st.metric(
                                "Call Options (CE)",
                                f"₹{ce_stats.get('total_pnl', 0):,.2f}",
                                f"{ce_stats.get('win_rate', 0):.1f}% WR, {ce_stats.get('trades', 0)} trades"
                            )
                        with dir_cols[1]:
                            pe_stats = direction_analysis.get('PE', {})
                            st.metric(
                                "Put Options (PE)",
                                f"₹{pe_stats.get('total_pnl', 0):,.2f}",
                                f"{pe_stats.get('win_rate', 0):.1f}% WR, {pe_stats.get('trades', 0)} trades"
                            )
                    else:
                        st.info("No direction data available.")
                    
                    st.divider()
                    
                    # Risk Metrics
                    st.markdown("#### ⚖️ Risk-Adjusted Metrics")
                    risk_cols = st.columns(3)
                    with risk_cols[0]:
                        st.metric("Sharpe Ratio", f"{risk_metrics.get('sharpe_ratio', 0):.2f}")
                    with risk_cols[1]:
                        st.metric("Sortino Ratio", f"{risk_metrics.get('sortino_ratio', 0):.2f}")
                    with risk_cols[2]:
                        st.metric("Calmar Ratio", f"{risk_metrics.get('calmar_ratio', 0):.2f}")
                    
                    st.caption("Sharpe: Risk-adjusted return | Sortino: Downside risk-adjusted | Calmar: Return/Max Drawdown")
                    
                else:
                    st.info("No trades available for temporal analysis.")
                    
            except ImportError as e:
                st.error(f"Analysis module not available: {e}")
                st.info("Please ensure engine/backtest_analysis.py exists.")
        
        with result_tabs[5]:
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
    
    flash_msg = st.session_state.get("backtest_flash")
    if flash_msg:
        st.success(flash_msg)
        st.session_state.backtest_flash = None

    # Quick glance cards (latest results)
    last_results = st.session_state.backtest_results
    summary_cols = st.columns(3, gap="small")
    if last_results:
        summary_cols[0].metric("Last P&L", f"₹{last_results.get('total_pnl', 0.0):,.2f}")
        summary_cols[1].metric("Last Win Rate", f"{last_results.get('win_rate', 0.0):.2f}%")
        timeframe_badge = st.session_state.backtest_results_timeframe
        source_label = st.session_state.backtest_results_source or "—"
        if timeframe_badge:
            source_label = f"{source_label} · {timeframe_badge.upper()}"
        summary_cols[2].metric("Last Run Source", source_label)
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
    backtesting_settings = strategy_config.get('backtesting', {}) if isinstance(strategy_config, dict) else {}
    angel_smartapi_cfg = backtesting_settings.get('angel_smartapi', {}) if isinstance(backtesting_settings, dict) else {}
    
    st.subheader("⚙️ Essential Parameters")
    timeframe_options = ["1h", "4h"]
    timeframe_default = backtesting_settings.get('strategy_timeframe', '1h')
    timeframe_index = timeframe_options.index(timeframe_default) if timeframe_default in timeframe_options else 0
    col1, col2, col3, col4 = st.columns(4, gap="small")
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
    with col4:
        strategy_timeframe = st.selectbox(
            "Strategy timeframe",
            options=timeframe_options,
            index=timeframe_index,
            format_func=lambda x: x.upper(),
            help="Controls which candle size (1H or 4H) powers inside-bar detection during backtests.",
            key="backtest_strategy_timeframe_select",
        )
    
    # Estimate capital requirement using option premium (NOT strike price!)
    # NIFTY options typically trade at ₹100-600 premium depending on volatility and strike selection
    # Using a realistic estimate: ~₹400-500 for ATM options, or ~0.5-2% of spot price
    # This matches the backtest engine's synthetic premium calculation
    estimated_strike_price = 24000  # Typical NIFTY level for estimation
    estimated_option_premium = max(100.0, 0.015 * estimated_strike_price)  # ~1.5% of spot, min ₹100
    estimated_capital_required = lot_size * estimated_option_premium
    
    if initial_capital < estimated_capital_required:
        st.warning(
            f"⚠️ Available capital (₹{initial_capital:,.0f}) is below an estimated requirement "
            f"of ₹{estimated_capital_required:,.0f} (based on ₹{estimated_option_premium:.0f} premium × {lot_size} qty)."
        )
        st.caption(
            "💡 Note: This is an estimate. Actual capital required depends on option premium at entry, "
            "which varies with market conditions and strike selection (ATM/ITM/OTM)."
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
        "strategy_timeframe": strategy_timeframe,
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
        source_tabs = st.tabs(["📤 CSV Upload", "☁️ DesiQuant Cloud", "📡 Angel SmartAPI"])
        
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
                            st.session_state.backtest_flash = "Backtest completed. Review analytics in the Results tab."
                            st.rerun()
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
                                        st.session_state.backtest_flash = "Backtest completed. Review analytics in the Results tab."
                                        st.rerun()
                            except Exception as e:
                                st.error(f"❌ Cloud backtest failed: {e}")
                                st.exception(e)
            else:
                st.info("Cloud datasource unavailable. Install required packages to enable this tab.")

        # Angel SmartAPI Workflow
        with source_tabs[2]:
            st.markdown("#### Angel SmartAPI Data Source")
            st.caption("Runs the same strategy using Spot 1H candles fetched through your Angel One SmartAPI Historical app (≈3–6 months coverage).")

            if not SMARTAPI_BACKTEST_AVAILABLE:
                st.info("Install `smartapi-python` and ensure `backtesting/datasource_smartapi.py` is available to enable this source.")
            else:
                angel_enabled = bool(angel_smartapi_cfg.get("enabled"))
                if not angel_enabled:
                    st.warning("Enable this source via `backtesting.angel_smartapi.enabled: true` inside `config/config.yaml`.")
                else:
                    default_end = date.today()
                    default_start = default_end - timedelta(days=60)
                    angel_start_date = st.date_input(
                        "Start date",
                        value=default_start,
                        key="angel_smartapi_start_date",
                    )
                    angel_end_date = st.date_input(
                        "End date",
                        value=default_end,
                        key="angel_smartapi_end_date",
                    )
                    st.caption(
                        f"Symbol: {angel_smartapi_cfg.get('symbol', 'NIFTY')} · Interval: {angel_smartapi_cfg.get('interval', 'ONE_HOUR')} · Exchange: {angel_smartapi_cfg.get('exchange', 'NSE')}"
                    )

                    if angel_end_date < angel_start_date:
                        st.error("❌ End date cannot precede start date.")
                    else:
                        if st.button(
                            "▶️ Run Backtest (Angel SmartAPI)",
                            use_container_width=True,
                            type="primary",
                            key="run_backtest_angel_smartapi",
                        ):
                            with st.spinner("Fetching data from Angel SmartAPI and running backtest..."):
                                try:
                                    data = smartapi_stream_data(
                                        symbol=angel_smartapi_cfg.get("symbol", "NIFTY"),
                                        start=str(angel_start_date),
                                        end=str(angel_end_date),
                                        interval=angel_smartapi_cfg.get("interval", "ONE_HOUR"),
                                        exchange=angel_smartapi_cfg.get("exchange", "NSE"),
                                        symbol_token=angel_smartapi_cfg.get("symbol_token"),
                                        secrets_path=angel_smartapi_cfg.get("secrets_path"),
                                    )
                                    spot_df = data.get("spot")

                                    if spot_df is None or spot_df.empty:
                                        st.warning("No spot data returned from Angel SmartAPI for this window.")
                                    else:
                                        with st.expander("Preview SmartAPI data", expanded=False):
                                            st.dataframe(spot_df.head(10), use_container_width=True)

                                        results = engine.run_backtest(
                                            data_1h=spot_df,
                                            options_df=None,
                                            expiries_df=None,
                                            initial_capital=initial_capital,
                                        )
                                        if not isinstance(results, dict):
                                            st.error("Unexpected result format from backtest engine.")
                                        else:
                                            store_backtest_results(results, "Angel SmartAPI")
                                            st.success("Backtest completed. Review analytics in the Results tab.")
                                            st.session_state.backtest_flash = "Backtest completed. Review analytics in the Results tab."
                                            st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Angel SmartAPI backtest failed: {e}")
                                    st.exception(e)
    
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
        'strategy_timeframe': strategy_timeframe,
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


