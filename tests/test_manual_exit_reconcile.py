import pandas as pd
from unittest.mock import MagicMock

from engine.live_runner import LiveStrategyRunner


def _build_runner():
    market_data = MagicMock(name="MarketDataProvider")
    signal_handler = MagicMock(name="SignalHandler")

    broker = MagicMock(name="Broker")
    broker.get_trade_book.return_value = []
    broker.get_order_book.return_value = []
    broker.get_positions.return_value = []
    broker.get_option_price.return_value = 200.4

    trade_logger = MagicMock(name="TradeLogger")
    trade_logger.get_open_trades.return_value = pd.DataFrame()
    trade_logger.update_trade_exit = MagicMock()
    trade_logger.update_tradingsymbol = MagicMock()

    config = {
        "lot_size": 75,
        "strategy": {"sl": 30, "rr": 1.8},
        "broker": {"type": "angel"},
        "market_data": {"nifty_symbol": "NIFTY"},
    }

    runner = LiveStrategyRunner(
        market_data_provider=market_data,
        signal_handler=signal_handler,
        broker=broker,
        trade_logger=trade_logger,
        config=config,
        tick_streamer=None,
    )
    return runner


def test_reconcile_manual_exit_uses_zero_default_when_position_missing():
    runner = _build_runner()
    order_id = "251120000349722"
    runner.trade_logger.get_open_trades.return_value = pd.DataFrame()

    runner._orders_to_signals = {
        order_id: {
            "tradingsymbol": "NIFTY25NOV2526100CE",
            "symbol": "NIFTY",
            "direction": "CE",
            "strike": 26100,
            "entry": 143.0,
            "executed_qty_lots": 2,
            "lot_size": 75,
        }
    }

    runner._reconcile_manual_exits()

    runner.trade_logger.update_trade_exit.assert_called_once()
    recorded_order = runner.trade_logger.update_trade_exit.call_args[0][0]
    assert recorded_order == order_id
    assert order_id not in runner._orders_to_signals

