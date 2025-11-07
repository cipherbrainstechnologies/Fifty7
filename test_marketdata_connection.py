#!/usr/bin/env python3
"""
Test Market Data API Connection
Quick script to verify your API key works
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtesting import datasource_marketdata
from logzero import logger

# Your API token
API_TOKEN = "azZCREFyMWh3d0h6RnBOSTF0Qld0UWFMQ1laWURQY2pvU3QtTU9jU1ItMD0"

def test_connection():
    """Test Market Data API connection"""
    logger.info("=" * 80)
    logger.info("MARKET DATA API CONNECTION TEST")
    logger.info("=" * 80)
    logger.info("")
    logger.info(f"API Token: {API_TOKEN[:20]}...{API_TOKEN[-10:]}")
    logger.info("")
    
    try:
        logger.info("Testing connection to api.marketdata.app...")
        success = datasource_marketdata.test_connection(api_key=API_TOKEN)
        
        if success:
            logger.info("")
            logger.info("✓" * 40)
            logger.info("✓ CONNECTION SUCCESSFUL!")
            logger.info("✓ Your API key is working correctly")
            logger.info("✓" * 40)
            logger.info("")
            logger.info("Next Steps:")
            logger.info("1. Run a backtest: python3 run_backtest_marketdata.py")
            logger.info("2. Or use in your code:")
            logger.info("")
            logger.info("   from backtesting import datasource_marketdata")
            logger.info("   data = datasource_marketdata.stream_data(")
            logger.info("       symbol='NIFTY',")
            logger.info("       start='2023-01-01',")
            logger.info("       end='2023-03-31',")
            logger.info("       api_key=API_TOKEN")
            logger.info("   )")
            logger.info("")
            return True
        else:
            logger.error("")
            logger.error("✗" * 40)
            logger.error("✗ CONNECTION FAILED")
            logger.error("✗ Please check your API key")
            logger.error("✗" * 40)
            logger.error("")
            logger.error("Troubleshooting:")
            logger.error("1. Verify your API key at https://www.marketdata.app/")
            logger.error("2. Check your internet connection")
            logger.error("3. Ensure you haven't exceeded rate limits (100/day)")
            logger.error("")
            return False
            
    except Exception as e:
        logger.error("")
        logger.error("✗" * 40)
        logger.error(f"✗ ERROR: {e}")
        logger.error("✗" * 40)
        logger.error("")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
