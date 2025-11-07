import pandas as pd
import pytest
from datetime import datetime
import pytz

from engine import inside_bar_breakout_strategy as strategy_mod
from engine.inside_bar_breakout_strategy import (
    InsideBarBreakoutStrategy,
    get_hourly_candles,
    get_active_signal,
    confirm_breakout_on_hour_close,
)
from engine import market_data as market_data_mod


IST = pytz.timezone("Asia/Kolkata")


def make_synthetic_hourly_df():
    return pd.DataFrame(
        [
            {"Date": pd.Timestamp("2025-11-07 07:15"), "Open": 180.0, "High": 200.0, "Low": 100.0, "Close": 150.0},
            {"Date": pd.Timestamp("2025-11-07 08:15"), "Open": 150.0, "High": 190.0, "Low": 110.0, "Close": 150.0},
            {"Date": pd.Timestamp("2025-11-07 09:15"), "Open": 110.0, "High": 115.0, "Low": 90.0, "Close": 95.0},
            {"Date": pd.Timestamp("2025-11-07 10:15"), "Open": 95.0, "High": 100.0, "Low": 90.0, "Close": 92.0},
        ]
    )


@pytest.fixture
def freeze_ist_now(monkeypatch):
    fixed_now = IST.localize(datetime(2025, 11, 7, 11, 30))
    monkeypatch.setattr(strategy_mod, "ist_now", lambda: fixed_now)
    return fixed_now


def test_breakout_execution_with_synthetic_data(freeze_ist_now):
    raw_df = make_synthetic_hourly_df()
    candles = get_hourly_candles(data=raw_df, current_time=freeze_ist_now)
    signal = get_active_signal(candles)
    assert signal is not None
    assert signal["range_high"] == pytest.approx(200.0)
    assert signal["range_low"] == pytest.approx(100.0)

    direction, latest_closed = confirm_breakout_on_hour_close(candles, signal, current_time=freeze_ist_now)
    assert direction == "PE"
    assert latest_closed is not None
    assert latest_closed["Close"] == pytest.approx(95.0)

    strategy = InsideBarBreakoutStrategy(broker=None, market_data=None, live_mode=False)
    result = strategy.run_strategy(data=raw_df)
    assert result["status"] == "breakout_confirmed"
    assert result["breakout_direction"] == "PE"
    assert result["simulated"] is True


class DummySmartApi:
    def __init__(self, success_payload):
        self.success_payload = success_payload
        self.call_count = 0

    def getCandleData(self, params):
        self.call_count += 1
        if self.call_count == 1:
            return {"status": True, "data": self.success_payload}
        # Simulate AB1004 on subsequent calls
        return {"status": False, "errorcode": "AB1004", "message": "No data"}


class DummyBroker:
    def __init__(self, smart_api):
        self.smart_api = smart_api
        self.api_key = "dummy"
        self.auth_token = "dummy"

    def _ensure_session(self):
        return True

    def _search_symbol(self, exchange, symbol):
        return {}


def test_historical_candles_fallback_after_ab1004(monkeypatch):
    monkeypatch.setattr(market_data_mod, "SmartConnect", object)

    payload = [
        ["2025-11-07 09:15", 180.0, 185.0, 175.0, 182.0, 10000],
        ["2025-11-07 09:16", 182.0, 186.0, 181.0, 184.0, 9500],
    ]
    dummy_api = DummySmartApi(success_payload=payload)
    dummy_broker = DummyBroker(dummy_api)

    provider = market_data_mod.MarketDataProvider(dummy_broker)
    first_df = provider.get_historical_candles(symbol_token="TEST", interval="ONE_MINUTE")
    assert not first_df.empty

    second_df = provider.get_historical_candles(symbol_token="TEST", interval="ONE_MINUTE")
    assert not second_df.empty
    pd.testing.assert_frame_equal(first_df, second_df)
    assert dummy_api.call_count >= 2


def test_get_hourly_candles_completeness_filters():
    raw = pd.DataFrame(
        [
            {"Date": pd.Timestamp("2025-11-07 08:15"), "Open": 100, "High": 110, "Low": 95, "Close": 105},
            {"Date": pd.Timestamp("2025-11-07 09:15"), "Open": 105, "High": 108, "Low": 100, "Close": 107},
        ]
    )

    early_time = IST.localize(datetime(2025, 11, 7, 9, 16))
    late_time = IST.localize(datetime(2025, 11, 7, 10, 16))

    incomplete = get_hourly_candles(data=raw, current_time=early_time)
    assert len(incomplete) == 1

    complete = get_hourly_candles(data=raw, current_time=late_time)
    assert len(complete) == 2
