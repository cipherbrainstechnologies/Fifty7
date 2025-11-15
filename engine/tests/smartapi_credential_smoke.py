"""
SmartAPI credential verification script.

Runs three non-trading checks:
1. Trading app login + token refresh
2. Historical data fetch using historical-only app
3. Publisher app session + feed token retrieval

Usage:
    python -m engine.tests.smartapi_credential_smoke --help
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Tuple

import pyotp
from logzero import logger

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise SystemExit("tomllib/tomli not available. Install tomli for Python <3.11") from exc

try:
    from SmartApi.smartConnect import SmartConnect
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "smartapi-python is required for this smoke test. Install with: pip install smartapi-python"
    ) from exc

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SECRETS_PATH = ROOT_DIR / ".streamlit" / "secrets.toml"


def _load_secrets(secrets_path: Path) -> Dict[str, Any]:
    if not secrets_path.exists():
        raise FileNotFoundError(f"secrets file not found: {secrets_path}")

    with secrets_path.open("rb") as fh:
        data = tomllib.load(fh)
    logger.info("Loaded secrets from %s", secrets_path)
    return data


def _generate_totp(secret: str) -> str:
    if not secret:
        raise ValueError("TOTP secret is required (broker.token)")
    return pyotp.TOTP(secret).now()


def _create_session(
    label: str,
    api_key: str,
    broker_creds: Dict[str, Any],
) -> Tuple[SmartConnect, Dict[str, Any]]:
    if not api_key:
        raise ValueError(f"{label}: api_key missing in secrets")

    username = broker_creds.get("client_id") or broker_creds.get("username")
    password = broker_creds.get("pwd")
    totp_secret = broker_creds.get("token")

    if not username or not password:
        raise ValueError(f"{label}: broker credentials incomplete (need client_id/username + pwd)")

    smart = SmartConnect(api_key)
    otp = _generate_totp(totp_secret)
    logger.info("[%s] Generating SmartAPI session for %s", label, username)
    session_resp = smart.generateSession(username, password, otp)

    if not session_resp.get("status"):
        raise RuntimeError(f"{label}: Session failed - {session_resp.get('message')}")

    data = session_resp.get("data", {}) or {}
    auth_token = data.get("jwtToken")
    refresh_token = data.get("refreshToken")
    logger.info(
        "[%s] Session OK (jwt=%s, refresh=%s)",
        label,
        "yes" if auth_token else "no",
        "yes" if refresh_token else "no",
    )
    return smart, data


def _test_trading_app(broker_creds: Dict[str, Any], trading_app: Dict[str, Any]) -> None:
    smart, session_data = _create_session("Trading", trading_app.get("api_key"), broker_creds)
    refresh_token = session_data.get("refreshToken")
    if not refresh_token:
        logger.warning("[Trading] No refreshToken returned; skipping generateToken check")
        return

    logger.info("[Trading] Generating new JWT via refreshToken")
    token_resp = smart.generateToken(refresh_token)
    if token_resp.get("status"):
        logger.info("[Trading] Token refresh succeeded")
    else:
        logger.warning(
            "[Trading] Token refresh failed: %s", token_resp.get("message", "no message")
        )


def _build_window(hours: int) -> Tuple[str, str]:
    now = datetime.now()
    start = now - timedelta(hours=max(1, hours))
    return start.strftime("%Y-%m-%d %H:%M"), now.strftime("%Y-%m-%d %H:%M")


def _test_historical_app(
    broker_creds: Dict[str, Any],
    historical_app: Dict[str, Any],
    symbol_token: str,
    interval: str,
    hours: int,
) -> None:
    smart, _ = _create_session("Historical", historical_app.get("api_key"), broker_creds)
    from_dt, to_dt = _build_window(hours)
    params = {
        "exchange": "NSE",
        "symboltoken": symbol_token,
        "interval": interval,
        "fromdate": from_dt,
        "todate": to_dt,
    }
    logger.info(
        "[Historical] Fetching candles token=%s interval=%s window=%s→%s",
        symbol_token,
        interval,
        from_dt,
        to_dt,
    )
    response = smart.getCandleData(params)
    if isinstance(response, dict) and response.get("data"):
        candles = response["data"]
        logger.info("[Historical] Retrieved %s candles", len(candles))
    else:
        logger.warning("[Historical] Candle response empty or invalid: %s", response)


def _test_publisher_app(broker_creds: Dict[str, Any], publisher_app: Dict[str, Any]) -> None:
    smart, _ = _create_session("Publisher", publisher_app.get("api_key"), broker_creds)
    logger.info("[Publisher] Requesting feed token")
    feed_resp = smart.getfeedToken()

    if isinstance(feed_resp, str):
        logger.info("[Publisher] Feed token received (string)")
    elif isinstance(feed_resp, dict):
        if feed_resp.get("status"):
            logger.info("[Publisher] Feed token response OK")
        else:
            logger.warning("[Publisher] Feed token request failed: %s", feed_resp.get("message"))
    else:
        logger.warning("[Publisher] Unexpected feed token response type: %s", type(feed_resp))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SmartAPI credential smoke tests")
    parser.add_argument(
        "--secrets",
        type=Path,
        default=DEFAULT_SECRETS_PATH,
        help="Path to secrets TOML (default: %(default)s)",
    )
    parser.add_argument(
        "--symbol-token",
        default="99926000",
        help="Symbol token to use for historical candle fetch (default: NIFTY index 99926000)",
    )
    parser.add_argument(
        "--interval",
        default="ONE_HOUR",
        choices=[
            "ONE_MINUTE",
            "THREE_MINUTE",
            "FIVE_MINUTE",
            "FIFTEEN_MINUTE",
            "THIRTY_MINUTE",
            "ONE_HOUR",
            "ONE_DAY",
        ],
        help="Historical interval to fetch",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=6,
        help="Lookback window (in hours) for historical test (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    secrets = _load_secrets(args.secrets)

    broker_creds = secrets.get("broker", {})
    smartapi_apps = secrets.get("smartapi_apps", {})
    trading_app = smartapi_apps.get("trading", {})
    historical_app = smartapi_apps.get("historical", {})
    publisher_app = smartapi_apps.get("publisher", {})

    missing_sections = [
        name
        for name, section in [
            ("broker", broker_creds),
            ("smartapi_apps.trading", trading_app),
            ("smartapi_apps.historical", historical_app),
            ("smartapi_apps.publisher", publisher_app),
        ]
        if not section
    ]
    if missing_sections:
        raise SystemExit(f"Missing sections in secrets.toml: {', '.join(missing_sections)}")

    logger.info("=== SmartAPI Credential Smoke Tests ===")
    _test_trading_app(broker_creds, trading_app)
    _test_historical_app(
        broker_creds, historical_app, args.symbol_token, args.interval, args.hours
    )
    _test_publisher_app(broker_creds, publisher_app)
    logger.info("=== Smoke tests completed ===")


if __name__ == "__main__":
    main()

