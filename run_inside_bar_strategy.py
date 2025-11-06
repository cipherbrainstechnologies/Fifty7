"""
Standalone runner for Inside Bar Breakout Strategy
Example usage script for production-grade Inside Bar Breakout strategy
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from engine.inside_bar_breakout_strategy import InsideBarBreakoutStrategy, create_strategy_from_config
from engine.broker_connector import AngelOneBroker
from engine.market_data import MarketDataProvider
from logzero import logger
import yaml
from pathlib import Path

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
                    content = file.read().decode('utf-8')
                    return toml.loads(content)
            tomllib = TomlWrapper()
        except ImportError:
            tomllib = None


def load_config():
    """Load configuration from config.yaml and secrets.toml"""
    config_path = Path("config/config.yaml")
    secrets_path = Path(".streamlit/secrets.toml")
    
    # Load YAML config
    config = {}
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    
    # Load TOML secrets
    broker_config = {}
    if secrets_path.exists():
        if tomllib is None:
            logger.warning("TOML parser not available. Install with: pip install tomli")
        else:
            try:
                with open(secrets_path, 'rb') as f:  # TOML requires binary mode
                    secrets = tomllib.load(f)
                    broker_config = secrets.get('broker', {})
            except Exception as e:
                logger.error(f"Error loading secrets.toml: {e}")
    
    return config, broker_config


def main():
    """Main execution function"""
    print("\n" + "="*70)
    print("INSIDE BAR BREAKOUT STRATEGY - PRODUCTION RUNNER")
    print("="*70)
    print("\n⚠️  IMPORTANT: Ensure AngelOne SmartAPI is authenticated before running")
    print("⚠️  Set LIVE_MODE=False in inside_bar_breakout_strategy.py to test without real trades\n")
    
    try:
        # Load configuration
        config, broker_config = load_config()
        
        if not broker_config:
            logger.error("❌ Broker configuration not found in .streamlit/secrets.toml")
            logger.error("Please configure broker credentials before running")
            return
        
        # Create broker instance
        logger.info("🔧 Initializing broker connection...")
        broker = AngelOneBroker(broker_config)
        
        # Create market data provider
        logger.info("📊 Initializing market data provider...")
        market_data = MarketDataProvider(broker)
        
        # Create strategy instance
        # Set live_mode based on LIVE_MODE constant in strategy module
        from engine.inside_bar_breakout_strategy import LIVE_MODE
        
        logger.info(f"🎯 Initializing Inside Bar Breakout Strategy (Live Mode: {LIVE_MODE})...")
        strategy = InsideBarBreakoutStrategy(
            broker=broker,
            market_data=market_data,
            symbol="NIFTY",
            lot_size=config.get('lot_size', 75),
            quantity_lots=1,  # Adjust as needed
            live_mode=LIVE_MODE,
            csv_export_path="logs/inside_bar_breakout_results.csv"
        )
        
        # Run strategy
        logger.info("🚀 Executing strategy...")
        result = strategy.run_strategy()
        
        # Print result summary
        print("\n" + "="*70)
        print("STRATEGY EXECUTION COMPLETE")
        print("="*70)
        print(f"Status: {result.get('status', 'unknown')}")
        print(f"Message: {result.get('message', 'N/A')}")
        
        if result.get('breakout_direction'):
            print(f"Breakout: {result.get('breakout_direction')}")
            print(f"Order ID: {result.get('order_id', 'N/A')}")
        
        print("="*70 + "\n")
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Strategy execution interrupted by user")
    except Exception as e:
        logger.exception(f"❌ Error running strategy: {e}")
        print(f"\n❌ Error: {str(e)}")
        print("Please check logs/errors.log for detailed error information")


if __name__ == "__main__":
    main()

