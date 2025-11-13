#!/usr/bin/env python3
"""
Example: Run backtest with TrueData API source

This script demonstrates how to use TrueData Professional API as a data source
for backtesting, as an alternative to DesiQuant (free) or Market Data API.

TrueData provides professional-grade historical data with complete options OHLC.
Requires paid subscription: https://truedata.in

Usage:
    # Set credentials via environment variables
    export TRUEDATA_USERNAME="your_username"
    export TRUEDATA_PASSWORD="your_password"
    python run_backtest_truedata.py
    
    # Or set in config.yaml:
    # backtesting:
    #   truedata:
    #     username: "your_username"
    #     password: "your_password"
"""

import os
import sys
import yaml
from logzero import logger
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.backtest_engine import BacktestEngine
from backtesting import datasource_desiquant, datasource_truedata


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def run_backtest_with_truedata():
    """
    Run backtest using TrueData API as data source.
    
    This function demonstrates:
    1. How to fetch data from TrueData API
    2. How to run backtest with the fetched data
    3. How to compare TrueData vs DesiQuant data quality
    """
    
    logger.info("=" * 80)
    logger.info("BACKTEST WITH TRUEDATA API")
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
    
    # Get credentials from environment or config
    username = os.environ.get("TRUEDATA_USERNAME")
    password = os.environ.get("TRUEDATA_PASSWORD")
    
    if not username:
        username = config.get("backtesting", {}).get("truedata", {}).get("username")
    if not password:
        password = config.get("backtesting", {}).get("truedata", {}).get("password")
    
    # Check if TrueData API is enabled
    truedata_enabled = config.get("backtesting", {}).get("truedata", {}).get("enabled", False)
    
    # Decide which source to use
    if truedata_enabled and username and password:
        use_truedata = True
        logger.info("✓ Using TrueData API (credentials found)")
    elif username and password:
        use_truedata = True
        logger.warning("⚠ Using TrueData API but not enabled in config (enable with backtesting.truedata.enabled=true)")
    else:
        use_truedata = False
        logger.warning("⚠ TrueData credentials not found")
        logger.info("")
        logger.info("  To use TrueData API:")
        logger.info("  1. Subscribe at https://truedata.in")
        logger.info("  2. Set environment variables:")
        logger.info("     export TRUEDATA_USERNAME='your_username'")
        logger.info("     export TRUEDATA_PASSWORD='your_password'")
        logger.info("  3. Or add to config.yaml:")
        logger.info("     backtesting.truedata.username")
        logger.info("     backtesting.truedata.password")
        logger.info("")
        logger.info("Falling back to DesiQuant (free, no credentials required)")
    
    # ========== 3. FETCH DATA ==========
    
    # Backtest parameters
    symbol = "NIFTY"
    start_date = "2023-01-01"
    end_date = "2023-03-31"
    initial_capital = 100000.0
    
    # Get strike step from config
    strike_step = config.get("backtesting", {}).get("truedata", {}).get("strike_step", {}).get(symbol, 50)
    
    logger.info("")
    logger.info(f"Backtest Parameters:")
    logger.info(f"  Symbol: {symbol}")
    logger.info(f"  Period: {start_date} to {end_date}")
    logger.info(f"  Initial Capital: ₹{initial_capital:,.2f}")
    logger.info(f"  Strike Step: {strike_step}")
    logger.info("")
    
    # Fetch data based on source selection
    try:
        if use_truedata:
            logger.info("📡 Fetching data from TrueData API...")
            logger.info("   Note: This may take several minutes (fetching all strikes & expiries)")
            logger.info("")
            
            data = datasource_truedata.stream_data(
                symbol=symbol,
                start=start_date,
                end=end_date,
                username=username,
                password=password,
                strike_step=strike_step
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
        
        # Data quality info
        if not spot_1h.empty:
            logger.info(f"  Spot date range: {spot_1h.index.min()} to {spot_1h.index.max()}")
        if not options_1h.empty and 'timestamp' in options_1h.columns:
            logger.info(f"  Options date range: {options_1h['timestamp'].min()} to {options_1h['timestamp'].max()}")
        
        logger.info("")
        
    except Exception as e:
        logger.error(f"Failed to fetch data: {e}")
        logger.error("Please check your credentials and network connection")
        import traceback
        traceback.print_exc()
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
    if use_truedata:
        logger.info(f"📡 Data Source: TrueData Professional API")
        logger.info(f"   Cost: ₹2,000-3,000/month")
        logger.info(f"   Quality: ⭐⭐⭐⭐⭐ Professional Grade")
    else:
        logger.info(f"📡 Data Source: DesiQuant S3 (Free)")
    logger.info("")
    
    logger.info("=" * 80)
    logger.info("BACKTEST COMPLETE")
    logger.info("=" * 80)


def test_api_connection():
    """Test TrueData API connection"""
    logger.info("Testing TrueData API connection...")
    
    config = load_config()
    
    username = os.environ.get("TRUEDATA_USERNAME")
    password = os.environ.get("TRUEDATA_PASSWORD")
    
    if not username:
        username = config.get("backtesting", {}).get("truedata", {}).get("username")
    if not password:
        password = config.get("backtesting", {}).get("truedata", {}).get("password")
    
    if not username or not password:
        logger.error("✗ TrueData credentials not found")
        logger.info("Set TRUEDATA_USERNAME and TRUEDATA_PASSWORD environment variables")
        return False
    
    try:
        logger.info(f"Connecting with username: {username}")
        
        # Try to fetch a small sample
        data = datasource_truedata.stream_data(
            symbol="NIFTY",
            start="2024-11-01",
            end="2024-11-02",
            username=username,
            password=password,
            strike_step=50
        )
        
        if data and data["spot"] is not None and not data["spot"].empty:
            logger.info("✓ Connection test passed")
            logger.info(f"  Sample data: {len(data['spot'])} spot candles")
            return True
        else:
            logger.error("✗ Connection test failed (no data returned)")
            return False
            
    except Exception as e:
        logger.error(f"✗ Connection test failed: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run backtest with TrueData API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test API connection
  python run_backtest_truedata.py --test
  
  # Run backtest with credentials from environment
  export TRUEDATA_USERNAME="your_username"
  export TRUEDATA_PASSWORD="your_password"
  python run_backtest_truedata.py
  
  # Run backtest (falls back to DesiQuant if no credentials)
  python run_backtest_truedata.py

Notes:
  - TrueData requires paid subscription (₹2,000-3,000/month)
  - Subscribe at: https://truedata.in
  - Professional-grade data with complete historical options OHLC
  - Data from 2015+ (longer history than DesiQuant 2021+)
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
        run_backtest_with_truedata()
