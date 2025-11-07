#!/usr/bin/env python3
"""
Example: Run backtest with Market Data API source

This script demonstrates how to use the Market Data API as a data source
for backtesting, as an alternative to CSV or DesiQuant sources.

Usage:
    # Without API key (uses AAPL for testing)
    python run_backtest_marketdata.py
    
    # With API key (for NIFTY/BANKNIFTY data)
    export MARKETDATA_API_KEY="your_api_key_here"
    python run_backtest_marketdata.py
"""

import os
import sys
import yaml
from logzero import logger
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.backtest_engine import BacktestEngine
from backtesting import datasource_desiquant, datasource_marketdata


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def run_backtest_with_marketdata():
    """
    Run backtest using Market Data API as data source.
    
    This function demonstrates:
    1. How to fetch data from Market Data API
    2. How to run backtest with the fetched data
    3. How to switch between data sources without code changes
    """
    
    logger.info("=" * 80)
    logger.info("BACKTEST WITH MARKET DATA API")
    logger.info("=" * 80)
    
    # ========== 1. LOAD CONFIGURATION ==========
    
    config = load_config()
    
    if not config:
        logger.error("Failed to load configuration file")
        return
    
    # Get data source configuration
    data_source = config.get("backtesting", {}).get("data_source", "desiquant")
    logger.info(f"Configured data source: {data_source}")
    
    # ========== 2. DETERMINE WHICH SOURCE TO USE ==========
    
    # Get API key from environment or config
    api_key = os.environ.get("MARKETDATA_API_KEY")
    if not api_key:
        api_key = config.get("backtesting", {}).get("marketdata", {}).get("api_key")
    
    # Check if Market Data API is enabled
    marketdata_enabled = config.get("backtesting", {}).get("marketdata", {}).get("enabled", False)
    
    # Decide which source to use
    if marketdata_enabled and api_key:
        use_marketdata = True
        logger.info("✓ Using Market Data API (API key found)")
    elif api_key:
        use_marketdata = True
        logger.warning("⚠ Using Market Data API but not enabled in config (enable with backtesting.marketdata.enabled=true)")
    else:
        use_marketdata = False
        logger.warning("⚠ Market Data API key not found")
        logger.info("  To use Market Data API:")
        logger.info("  1. Get API key from https://www.marketdata.app/")
        logger.info("  2. Set environment variable: export MARKETDATA_API_KEY='your_key'")
        logger.info("  3. Or add to config.yaml: backtesting.marketdata.api_key")
        logger.info("")
        logger.info("Falling back to DesiQuant (free, no API key required)")
    
    # ========== 3. FETCH DATA ==========
    
    # Backtest parameters
    symbol = "NIFTY"
    start_date = "2023-01-01"
    end_date = "2023-03-31"
    initial_capital = 100000.0
    
    logger.info("")
    logger.info(f"Backtest Parameters:")
    logger.info(f"  Symbol: {symbol}")
    logger.info(f"  Period: {start_date} to {end_date}")
    logger.info(f"  Initial Capital: ₹{initial_capital:,.2f}")
    logger.info("")
    
    # Fetch data based on source selection
    try:
        if use_marketdata:
            logger.info("📡 Fetching data from Market Data API...")
            logger.info("   Note: Market Data API provides daily data, creating synthetic hourly candles")
            
            data = datasource_marketdata.stream_data(
                symbol=symbol,
                start=start_date,
                end=end_date,
                api_key=api_key
            )
        else:
            logger.info("📡 Fetching data from DesiQuant S3...")
            
            data = datasource_desiquant.stream_data(
                symbol=symbol,
                start=start_date,
                end=end_date
            )
        
        spot_1h = data["spot"]
        options_1h = data["options"]
        expiries = data["expiries"]
        
        logger.info("")
        logger.info(f"✓ Data fetched successfully:")
        logger.info(f"  Spot candles: {len(spot_1h)}")
        logger.info(f"  Option data points: {len(options_1h)}")
        logger.info(f"  Expiry dates: {len(expiries)}")
        logger.info("")
        
    except Exception as e:
        logger.error(f"Failed to fetch data: {e}")
        logger.error("Please check your API key and network connection")
        return
    
    # Validate data
    if spot_1h.empty:
        logger.error("No spot data available for backtesting")
        return
    
    # ========== 4. RUN BACKTEST ==========
    
    logger.info("🔄 Running backtest...")
    logger.info("")
    
    try:
        # Initialize backtest engine
        engine = BacktestEngine(config)
        
        # Run backtest
        results = engine.run_backtest(
            data_1h=spot_1h,
            initial_capital=initial_capital,
            options_df=options_1h if not options_1h.empty else None,
            expiries_df=expiries if not expiries.empty else None
        )
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ========== 5. DISPLAY RESULTS ==========
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 80)
    logger.info("")
    
    # Summary statistics
    logger.info(f"📊 Performance Summary:")
    logger.info(f"  Total Trades: {results['total_trades']}")
    logger.info(f"  Winning Trades: {results['winning_trades']}")
    logger.info(f"  Losing Trades: {results['losing_trades']}")
    logger.info(f"  Win Rate: {results['win_rate']:.2f}%")
    logger.info("")
    
    logger.info(f"💰 P&L Summary:")
    logger.info(f"  Initial Capital: ₹{results['initial_capital']:,.2f}")
    logger.info(f"  Final Capital: ₹{results['final_capital']:,.2f}")
    logger.info(f"  Total P&L: ₹{results['total_pnl']:,.2f}")
    logger.info(f"  Return: {results['return_pct']:.2f}%")
    logger.info("")
    
    logger.info(f"📈 Trade Statistics:")
    logger.info(f"  Average Win: ₹{results['avg_win']:,.2f}")
    logger.info(f"  Average Loss: ₹{results['avg_loss']:,.2f}")
    logger.info(f"  Max Drawdown: {results['max_drawdown']:.2f}%")
    logger.info(f"  Max Win Streak: {results['max_winning_streak']}")
    logger.info(f"  Max Loss Streak: {results['max_losing_streak']}")
    logger.info("")
    
    # Capital analysis
    if "avg_capital_required" in results:
        logger.info(f"💵 Capital Analysis:")
        logger.info(f"  Avg Capital Required: ₹{results['avg_capital_required']:,.2f}")
        if results.get('capital_exhausted', False):
            logger.info(f"  ⚠ Capital Exhausted at Trade #{results['capital_exhausted_at_trade']}")
        logger.info("")
    
    # Trailing SL analysis
    if "trail_exit_pct_of_winners" in results:
        logger.info(f"🎯 Trailing Stop Loss Analysis:")
        logger.info(f"  Winners Cut by Trail SL: {results['winning_trades_trail_exit']}")
        logger.info(f"  % of Winners: {results['trail_exit_pct_of_winners']:.2f}%")
        logger.info("")
    
    # Recent trades
    if results['trades']:
        logger.info("📝 Recent Trades (Last 5):")
        for trade in results['trades'][-5:]:
            direction = trade['direction']
            entry = trade['entry']
            exit = trade['exit']
            pnl = trade['pnl']
            reason = trade['exit_reason']
            
            emoji = "✅" if pnl > 0 else "❌"
            logger.info(
                f"  {emoji} {direction} @ ₹{entry:.2f} → ₹{exit:.2f} "
                f"= ₹{pnl:,.2f} ({reason})"
            )
        logger.info("")
    
    # Data source used
    logger.info(f"📡 Data Source: {'Market Data API' if use_marketdata else 'DesiQuant S3'}")
    logger.info("")
    
    logger.info("=" * 80)
    logger.info("BACKTEST COMPLETE")
    logger.info("=" * 80)


def test_api_connection():
    """Test Market Data API connection"""
    logger.info("Testing Market Data API connection...")
    
    api_key = os.environ.get("MARKETDATA_API_KEY")
    
    success = datasource_marketdata.test_connection(api_key=api_key)
    
    if success:
        logger.info("✓ Connection test passed")
    else:
        logger.error("✗ Connection test failed")
        if not api_key:
            logger.info("Note: No API key provided (only AAPL data available without key)")
    
    return success


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run backtest with Market Data API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test API connection
  python run_backtest_marketdata.py --test
  
  # Run backtest with API key from environment
  export MARKETDATA_API_KEY="your_api_key"
  python run_backtest_marketdata.py
  
  # Run backtest (falls back to DesiQuant if no API key)
  python run_backtest_marketdata.py
        """
    )
    
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test API connection and exit"
    )
    
    args = parser.parse_args()
    
    if args.test:
        # Test connection only
        test_api_connection()
    else:
        # Run full backtest
        run_backtest_with_marketdata()
