"""
Angel One SmartAPI data source for backtesting (spot-only).

Fetches short-window (≈3–6 months) 1H candles directly from the SmartAPI
Historical Data application so we can validate DesiQuant/other sources or run
limited "Angel SmartAPI Backtesting" scenarios.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import pyotp
from logzero import logger

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise SystemExit("tomllib/tomli not available. Install tomli for Python <3.11") from exc

try:
    from SmartApi.smartConnect import SmartConnect
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "smartapi-python is required for Angel SmartAPI backtesting. Install with: pip install smartapi-python"
    ) from exc


DEFAULT_SECRETS_PATH = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"
DEFAULT_SYMBOL_TOKENS = {
    "NIFTY": "99926000",      # NIFTY 50 index
    "NIFTY50": "99926000",
}


def _load_secrets(secrets_path: Optional[str]) -> Dict:
    path = Path(secrets_path) if secrets_path else DEFAULT_SECRETS_PATH
    if not path.exists():
        raise FileNotFoundError(f"Secrets file not found: {path}")
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    logger.info("Loaded SmartAPI secrets from %s", path)
    return data


def _smartconnect_session(api_key: str, username: str, password: str, totp_secret: str) -> SmartConnect:
    if not api_key:
        raise ValueError("SmartAPI api_key missing for Angel SmartAPI Backtesting")
    if not username or not password or not totp_secret:
        raise ValueError("Broker credentials incomplete (need client_id/username, pwd, token)")

    otp = pyotp.TOTP(totp_secret).now()
    smart = SmartConnect(api_key)
    logger.info("Generating SmartAPI session for %s", username)
    session = smart.generateSession(username, password, otp)
    if not session.get("status"):
        raise RuntimeError(f"SmartAPI session failed: {session.get('message', 'UNKNOWN')}")
    return smart


def _format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def _fetch_candles(
    smart: SmartConnect,
    *,
    exchange: str,
    symbol_token: str,
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
) -> pd.DataFrame:
    params = {
        "exchange": exchange,
        "symboltoken": str(symbol_token),
        "interval": interval,
        "fromdate": _format_datetime(start_dt),
        "todate": _format_datetime(end_dt),
    }
    logger.info(
        "Requesting SmartAPI candles token=%s interval=%s %s→%s",
        symbol_token,
        interval,
        params["fromdate"],
        params["todate"],
    )
    response = smart.getCandleData(params)
    if not isinstance(response, dict):
        raise RuntimeError(f"Unexpected SmartAPI response type: {type(response)}")

    if not response.get("status"):
        raise RuntimeError(f"SmartAPI candle fetch failed: {response.get('message', 'UNKNOWN')}")

    data = response.get("data", [])
    if not data:
        logger.warning("SmartAPI returned an empty candle array for the requested window")
        return pd.DataFrame(columns=["Open", "High", "Low", "Close"])

    candles = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    candles["timestamp"] = pd.to_datetime(candles["timestamp"])
    candles = candles.set_index("timestamp").sort_index()
    out = candles.rename(columns=str.capitalize)[["Open", "High", "Low", "Close"]]
    return out


def stream_data(
    *,
    symbol: str = "NIFTY",
    start: Optional[str] = None,
    end: Optional[str] = None,
    interval: str = "ONE_HOUR",
    exchange: str = "NSE",
    symbol_token: Optional[str] = None,
    secrets_path: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Returns dict with NIFTY spot candles and placeholder option/expiry frames.
    """
    secrets = _load_secrets(secrets_path)
    broker = secrets.get("broker", {})
    smartapi_apps = secrets.get("smartapi_apps", {})
    historical_app = smartapi_apps.get("historical", {})

    api_key = historical_app.get("api_key") or broker.get("api_key")
    username = broker.get("client_id") or broker.get("username")
    password = broker.get("pwd")
    totp_secret = broker.get("token")

    smart = _smartconnect_session(api_key, username, password, totp_secret)

    try:
        end_dt = pd.to_datetime(end) if end else datetime.now()
        if isinstance(end_dt, pd.Timestamp):
            end_dt = end_dt.to_pydatetime()
        start_dt = pd.to_datetime(start) if start else end_dt - timedelta(days=90)
        if isinstance(start_dt, pd.Timestamp):
            start_dt = start_dt.to_pydatetime()

        token = symbol_token or DEFAULT_SYMBOL_TOKENS.get(symbol.upper())
        if not token:
            raise ValueError(
                f"No symbol_token provided for {symbol}. "
                "Set backtesting.angel_smartapi.symbol_token in config.yaml."
            )

        spot = _fetch_candles(
            smart,
            exchange=exchange,
            symbol_token=str(token),
            interval=interval,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        return {
            "spot": spot,
            "options": pd.DataFrame({
                "timestamp": pd.to_datetime([]),
                "open": [],
                "high": [],
                "low": [],
                "close": [],
                "expiry": pd.to_datetime([]),
                "strike": [],
                "type": [],
            }),
            "expiries": pd.DataFrame({"expiry": pd.to_datetime([])}),
        }
    finally:
        try:
            smart.terminateSession(username)
        except Exception:
            pass

