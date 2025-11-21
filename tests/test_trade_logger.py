import pandas as pd

from engine.trade_logger import TradeLogger


def test_update_trade_exit_handles_numeric_order_id(tmp_path):
    trades_path = tmp_path / "trades.csv"
    df = pd.DataFrame(
        [
            {
                "timestamp": "2025-11-20T10:18:38.937615",
                "symbol": "NIFTY",
                "tradingsymbol": "NIFTY25NOV2526100CE",
                "strike": 26100,
                "direction": "CE",
                "order_id": 251120000349722,
                "entry": 143.0,
                "sl": 113.0,
                "tp": 197.0,
                "exit": "",
                "pnl": "",
                "status": "open",
                "pre_reason": "Inside Bar 1H breakout on CE side",
                "post_outcome": "",
                "quantity": 2,
            }
        ]
    )
    df.to_csv(trades_path, index=False)

    logger = TradeLogger(trades_file=str(trades_path))

    logger.update_trade_exit(
        "251120000349722",
        exit_price=153.0,
        pnl=1500.0,
        outcome="manual_exit",
        metadata={"org_id": "demo-org", "user_id": "admin", "quantity": 2},
    )

    updated = pd.read_csv(trades_path)
    assert float(updated.loc[0, "exit"]) == 153.0
    assert float(updated.loc[0, "pnl"]) == 1500.0
    assert updated.loc[0, "status"] == "closed"
    assert updated.loc[0, "post_outcome"] == "manual_exit"

