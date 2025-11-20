"""
Lightweight SmartAPI websocket streamer for live tick data.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Dict, List, Optional

from logzero import logger

from .symbol_utils import canonicalize_tradingsymbol

try:
    from SmartApi.smartWebSocketV2 import SmartWebSocketV2
except ImportError:  # pragma: no cover - optional dependency
    SmartWebSocketV2 = None


EXCHANGE_CODES = {
    "NSE": 1,
    "BSE": 2,
    "NFO": 3,
    "MCX": 4,
    "NCDEX": 5,
}


class LiveTickStreamer:
    """
    Maintains a SmartAPI websocket connection and caches latest ticks for subscribed tokens.
    """

    def __init__(self, broker, default_symbols: Optional[List[Dict]] = None):
        self.broker = broker
        self.api_key = getattr(broker, "api_key", None)
        self.client_code = (
            getattr(broker, "username", None)
            or getattr(broker, "client_id", None)
            or getattr(broker, "clientCode", None)
        )
        self.feed_token = getattr(broker, "feed_token", None)
        self.enabled = bool(SmartWebSocketV2 and self.api_key and self.client_code)

        self._ws: Optional[SmartWebSocketV2] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._connected = False
        self._stop_event = threading.Event()

        self._subscriptions: Dict[str, Dict] = {}
        self._quotes: Dict[str, Dict] = {}

        self._default_symbols = default_symbols or []

        if not self.enabled:
            logger.warning("LiveTickStreamer disabled (SmartWebSocketV2 not available or broker creds missing)")

    def start(self):
        if not self.enabled:
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="SmartAPI-Ticks", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._ws:
            try:
                self._ws.close_connection()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def subscribe_tradingsymbol(self, tradingsymbol: str, exchange: str = "NFO", token: Optional[str] = None):
        tradingsymbol = canonicalize_tradingsymbol(tradingsymbol)
        if not tradingsymbol:
            return
        if not token:
            try:
                token = self.broker._get_symbol_token(tradingsymbol, exchange)
            except Exception as exc:
                logger.debug(f"Unable to resolve token for {tradingsymbol}: {exc}")
                return
        if not token:
            return

        token = str(token)
        ts_upper = tradingsymbol
        if not ts_upper or ts_upper in {"NAN", "NONE", "NULL"}:
            logger.debug(f"Skipping tick subscription for invalid tradingsymbol: {tradingsymbol!r}")
            return
        exchange = exchange.upper()

        with self._lock:
            self._subscriptions[token] = {
                "tradingsymbol": ts_upper,
                "exchange": exchange,
            }
        if self._connected:
            self._send_subscribe([token])

    def subscribe_underlying(self, symbol: str, token: Optional[str] = None, exchange: str = "NSE"):
        self.subscribe_tradingsymbol(symbol, exchange=exchange, token=token)

    def get_quote(self, tradingsymbol: str) -> Optional[Dict]:
        tradingsymbol = canonicalize_tradingsymbol(tradingsymbol)
        if not tradingsymbol:
            return None
        ts_upper = tradingsymbol
        with self._lock:
            for token, meta in self._subscriptions.items():
                if meta["tradingsymbol"] == ts_upper:
                    return self._quotes.get(token)
        return None

    def get_ltp(self, tradingsymbol: str, default: Optional[float] = None) -> Optional[float]:
        quote = self.get_quote(tradingsymbol)
        if quote and "ltp" in quote:
            return quote["ltp"]
        return default

    # Internal helpers

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._connect()
            except Exception as exc:
                logger.warning(f"Tick streamer connection error: {exc}")
            finally:
                self._connected = False
                if not self._stop_event.is_set():
                    time.sleep(5)

    def _connect(self):
        self._ensure_feed_token()
        if not self.feed_token:
            logger.warning("Tick streamer cannot start without feed token")
            return

        auth_token = getattr(self.broker, "auth_token", None)
        if not auth_token:
            ensure_session = getattr(self.broker, "_ensure_session", None)
            try:
                if callable(ensure_session):
                    ensure_session()
            except Exception as exc:
                logger.warning(f"Tick streamer failed to refresh broker session: {exc}")
            auth_token = getattr(self.broker, "auth_token", None)

        if not auth_token:
            logger.warning("Tick streamer cannot start without broker auth token")
            return

        ws = SmartWebSocketV2(
            auth_token=auth_token,
            api_key=self.api_key,
            client_code=self.client_code,
            feed_token=self.feed_token,
        )

        ws.on_open = self._on_open
        ws.on_data = self._on_data
        ws.on_close = self._on_close
        ws.on_error = self._on_error
        self._ws = ws

        try:
            # Seed default subscriptions before connect
            for symbol in self._default_symbols:
                self.subscribe_tradingsymbol(
                    symbol.get("tradingsymbol") or symbol.get("symbol"),
                    exchange=symbol.get("exchange", "NSE"),
                    token=symbol.get("token"),
                )
            ws.connect()
        except Exception as exc:
            logger.warning(f"Tick streamer connect failed: {exc}")
            try:
                ws.close_connection()
            except Exception:
                pass

    def _ensure_feed_token(self):
        if self.feed_token:
            return
        try:
            if hasattr(self.broker, "_get_feed_token"):
                if getattr(self.broker, "_ensure_session", lambda: True)():
                    self.broker._get_feed_token()
                    self.feed_token = getattr(self.broker, "feed_token", None)
        except Exception as exc:
            logger.debug(f"Unable to refresh feed token: {exc}")

    def _on_open(self, wsapp):
        logger.info("SmartAPI websocket connected")
        self._connected = True
        with self._lock:
            tokens = list(self._subscriptions.keys())
        if tokens:
            self._send_subscribe(tokens)

    def _on_close(self, wsapp):
        logger.info("SmartAPI websocket closed")
        self._connected = False

    def _on_error(self, wsapp, error):
        logger.warning(f"SmartAPI websocket error: {error}")
        self._connected = False

    def _on_data(self, wsapp, message):
        try:
            if isinstance(message, (bytes, bytearray)):
                message = message.decode("utf-8")
            payload = json.loads(message)
        except Exception:
            return

        data_rows = payload.get("data")
        if not data_rows:
            # some payloads send single quote without data key
            data_rows = [payload]

        for row in data_rows:
            token = str(row.get("token") or row.get("tokenID") or row.get("tokenId") or "")
            if not token:
                continue
            ltp = row.get("ltp") or row.get("lastTradedPrice") or row.get("close")
            if ltp is None:
                continue
            try:
                ltp = float(ltp)
            except Exception:
                continue
            ts = row.get("tradingsymbol") or row.get("symbol")
            with self._lock:
                meta = self._subscriptions.get(token)
                if meta:
                    meta_ts = meta.get("tradingsymbol")
                    if meta_ts:
                        ts = meta_ts
                self._quotes[token] = {
                    "ltp": ltp,
                    "timestamp": row.get("exchangeTimestamp") or row.get("timestamp") or time.time(),
                    "tradingsymbol": ts,
                    "token": token,
                }

    def _send_subscribe(self, tokens: List[str]):
        if not tokens or not self._ws:
            return
        exchange_buckets: Dict[int, List[str]] = {}
        with self._lock:
            for token in tokens:
                meta = self._subscriptions.get(token)
                if not meta:
                    continue
                exchange_code = EXCHANGE_CODES.get(meta["exchange"], 3)
                exchange_buckets.setdefault(exchange_code, []).append(token)

        for exchange_code, bucket in exchange_buckets.items():
            payload = {
                "correlationID": f"ticks-{int(time.time()*1000)}",
                "action": 1,
                "mode": 1,  # LTP mode
                "tokenList": [{"exchangeType": exchange_code, "tokens": bucket}],
            }
            try:
                self._ws.subscribe(payload)
                logger.debug(f"Subscribed to tokens {bucket} (exchange {exchange_code})")
            except Exception as exc:
                logger.warning(f"Tick subscribe failed: {exc}")

