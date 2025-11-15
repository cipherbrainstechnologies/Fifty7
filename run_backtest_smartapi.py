#!/usr/bin/env python3
"""
Angel SmartAPI Backtesting (spot-only validation).

Fetches 1H spot candles using the SmartAPI Historical Data app and runs the
standard BacktestEngine so you can sanity-check recent months directly against
Angel's feed.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml
from logzero import logger

# Ensure project root on sys.path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from engine.backtest_engine import BacktestEngine
from backtesting import datasource_smartapi


def load_config(config_path: Path = Path("config/config.yaml")) -> dict:
    try:
        with config_path.open("r") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:
        logger.error("Failed to load config.yaml: %s", exc)
        return {}


def default_window(days: int = 60) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def summarize_results(results: dict) -> None:
    logger.info("=" * 80)
    logger.info("ANGEL SMARTAPI BACKTEST RESULTS")
    logger.info("=" * 80)
    if not results.get("total_trades"):
        logger.warning("No trades generated for the requested window.")
        return
    logger.info("Total Trades : %s", results["total_trades"])
    logger.info("Win Rate     : %.2f%%", results["win_rate"])
    logger.info("PnL          : ₹%s", f"{results['total_pnl']:,.2f}")
    logger.info("Return %%     : %.2f%%", results["return_pct"])
    logger.info("Max DD       : %.2f%%", results["max_drawdown"])
    logger.info("Final Capital: ₹%s", f"{results['final_capital']:,.2f}")
    logger.info("=" * 80)


def run_backtest(args: argparse.Namespace) -> None:
    config = load_config()
    backtest_cfg = config.get("backtesting", {})
    angel_cfg = backtest_cfg.get("angel_smartapi", {})

    symbol = args.symbol or angel_cfg.get("symbol", "NIFTY")
    symbol_token = args.symbol_token or angel_cfg.get("symbol_token")
    interval = args.interval or angel_cfg.get("interval", "ONE_HOUR")
    exchange = angel_cfg.get("exchange", "NSE")
    secrets_path = args.secrets or angel_cfg.get("secrets_path")
    initial_capital = float(args.capital or config.get("lot_size", 75) * 3000)

    start_date = args.start
    end_date = args.end
    if not start_date or not end_date:
        start_date, end_date = default_window()

    logger.info("=== Angel SmartAPI Backtesting ===")
    logger.info("Symbol    : %s", symbol)
    logger.info("Interval  : %s", interval)
    logger.info("Window    : %s → %s", start_date, end_date)
    logger.info("Secrets   : %s", secrets_path or datasource_smartapi.DEFAULT_SECRETS_PATH)

    data = datasource_smartapi.stream_data(
        symbol=symbol,
        start=start_date,
        end=end_date,
        interval=interval,
        exchange=exchange,
        symbol_token=symbol_token,
        secrets_path=secrets_path,
    )

    spot = data["spot"]
    if spot.empty:
        logger.warning("SmartAPI returned no spot candles for the requested window. Aborting.")
        return

    logger.info("Spot candles fetched: %d", len(spot))
    if args.show_head:
        logger.info("Sample candles:\n%s", spot.head())

    engine = BacktestEngine(config)
    results = engine.run_backtest(
        data_1h=spot,
        initial_capital=initial_capital,
        options_df=None,
        expiries_df=None,
    )

    summarize_results(results)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Inside Bar strategy backtest using Angel SmartAPI historical candles.",
    )
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    parser.add_argument("--symbol", help="Underlying symbol (default: config backtesting.angel_smartapi.symbol)")
    parser.add_argument("--symbol-token", help="SmartAPI symbol token (default from config)")
    parser.add_argument("--interval", help="SmartAPI interval (e.g., ONE_HOUR)")
    parser.add_argument("--secrets", help="Path to secrets TOML (default .streamlit/secrets.toml)")
    parser.add_argument("--capital", type=float, help="Initial capital for backtest")
    parser.add_argument("--show-head", action="store_true", help="Print head() of fetched candles")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    run_backtest(args)

