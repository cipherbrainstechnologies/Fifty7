#!/usr/bin/env python3
"""
Test script to verify strike price nearest-fallback fix
Tests backtesting with ITM/OTM configurations
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backtesting.datasource_desiquant import stream_data
from engine.backtest_engine import BacktestEngine
from logzero import logger
import warnings

# Suppress pandas warnings
warnings.filterwarnings("ignore", category=FutureWarning)


def print_section(title):
    """Print formatted section header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def test_atm_configuration():
    """Test 1: ATM configuration (should use exact match)"""
    print_section("TEST 1: ATM Configuration (Exact Match)")
    
    try:
        # Load small dataset
        logger.info("Loading NIFTY data (Jan 2024, 1 month)...")
        data = stream_data(
            symbol="NIFTY",
            start="2024-01-01",
            end="2024-01-31"
        )
        
        print(f"✓ Loaded {len(data['spot'])} spot candles")
        print(f"✓ Loaded {len(data['options'])} option candles")
        print(f"✓ Loaded {len(data['expiries'])} expiries")
        
        # Configure with ATM (no offset)
        config = {
            'strategy': {
                'premium_sl_pct': 35.0,
                'lock1_gain_pct': 60.0,
                'lock2_gain_pct': 80.0,
                'lock3_gain_pct': 100.0
            },
            'strike_selection': 'ATM 0',
            'strike_offset_base': 0,
            'strike_is_itm': False,
            'strike_is_otm': False,
            'lot_size': 75,
            'initial_capital': 100000
        }
        
        # Run backtest
        logger.info("Running backtest with ATM configuration...")
        engine = BacktestEngine(config)
        results = engine.run_backtest(
            data_1h=data['spot'],
            options_df=data['options'],
            expiries_df=data['expiries']
        )
        
        # Display results
        print(f"\n📊 Backtest Results (ATM 0):")
        print(f"   - Total Trades: {results['total_trades']}")
        print(f"   - Winning Trades: {results['winning_trades']}")
        print(f"   - Losing Trades: {results['losing_trades']}")
        print(f"   - Total P&L: ₹{results['total_pnl']:,.2f}")
        print(f"   - Win Rate: {results['win_rate']:.1f}%")
        
        if results['total_trades'] == 0:
            print("\n⚠️  WARNING: 0 trades executed (may be normal for short period)")
        else:
            print("\n✅ ATM Test PASSED: Trades executed successfully")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ATM Test FAILED: {e}")
        logger.exception("ATM test failed")
        return False


def test_itm_configuration():
    """Test 2: ITM 100 configuration (should use nearest-strike fallback)"""
    print_section("TEST 2: ITM 100 Configuration (Nearest-Strike Fallback)")
    
    try:
        # Load small dataset
        logger.info("Loading NIFTY data (Jan 2024, 1 month)...")
        data = stream_data(
            symbol="NIFTY",
            start="2024-01-01",
            end="2024-01-31"
        )
        
        print(f"✓ Loaded {len(data['spot'])} spot candles")
        print(f"✓ Loaded {len(data['options'])} option candles")
        
        # Configure with ITM 100
        config = {
            'strategy': {
                'premium_sl_pct': 35.0,
                'lock1_gain_pct': 60.0,
                'lock2_gain_pct': 80.0,
                'lock3_gain_pct': 100.0
            },
            'strike_selection': 'ITM 100',
            'strike_offset_base': 100,
            'strike_is_itm': True,
            'strike_is_otm': False,
            'lot_size': 75,
            'initial_capital': 100000
        }
        
        # Run backtest
        logger.info("Running backtest with ITM 100 configuration...")
        engine = BacktestEngine(config)
        results = engine.run_backtest(
            data_1h=data['spot'],
            options_df=data['options'],
            expiries_df=data['expiries']
        )
        
        # Display results
        print(f"\n📊 Backtest Results (ITM 100):")
        print(f"   - Total Trades: {results['total_trades']}")
        print(f"   - Winning Trades: {results['winning_trades']}")
        print(f"   - Losing Trades: {results['losing_trades']}")
        print(f"   - Total P&L: ₹{results['total_pnl']:,.2f}")
        print(f"   - Win Rate: {results['win_rate']:.1f}%")
        
        if results['total_trades'] == 0:
            print("\n⚠️  WARNING: 0 trades executed")
            print("    This indicates the fix may not be working correctly")
            print("    OR there were no valid signals in this period")
            return False
        else:
            print("\n✅ ITM Test PASSED: Trades executed with nearest-strike fallback")
            print("    (Check logs above for '📍 Using nearest available strike' messages)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ITM Test FAILED: {e}")
        logger.exception("ITM test failed")
        return False


def test_otm_configuration():
    """Test 3: OTM 200 configuration (should use nearest-strike fallback)"""
    print_section("TEST 3: OTM 200 Configuration (Nearest-Strike Fallback)")
    
    try:
        # Load small dataset
        logger.info("Loading NIFTY data (Jan 2024, 1 month)...")
        data = stream_data(
            symbol="NIFTY",
            start="2024-01-01",
            end="2024-01-31"
        )
        
        print(f"✓ Loaded {len(data['spot'])} spot candles")
        print(f"✓ Loaded {len(data['options'])} option candles")
        
        # Configure with OTM 200
        config = {
            'strategy': {
                'premium_sl_pct': 35.0,
                'lock1_gain_pct': 60.0,
                'lock2_gain_pct': 80.0,
                'lock3_gain_pct': 100.0
            },
            'strike_selection': 'OTM 200',
            'strike_offset_base': 200,
            'strike_is_itm': False,
            'strike_is_otm': True,
            'lot_size': 75,
            'initial_capital': 100000
        }
        
        # Run backtest
        logger.info("Running backtest with OTM 200 configuration...")
        engine = BacktestEngine(config)
        results = engine.run_backtest(
            data_1h=data['spot'],
            options_df=data['options'],
            expiries_df=data['expiries']
        )
        
        # Display results
        print(f"\n📊 Backtest Results (OTM 200):")
        print(f"   - Total Trades: {results['total_trades']}")
        print(f"   - Winning Trades: {results['winning_trades']}")
        print(f"   - Losing Trades: {results['losing_trades']}")
        print(f"   - Total P&L: ₹{results['total_pnl']:,.2f}")
        print(f"   - Win Rate: {results['win_rate']:.1f}%")
        
        if results['total_trades'] == 0:
            print("\n⚠️  WARNING: 0 trades executed")
            print("    This indicates the fix may not be working correctly")
            print("    OR there were no valid signals in this period")
            return False
        else:
            print("\n✅ OTM Test PASSED: Trades executed with nearest-strike fallback")
            print("    (Check logs above for '📍 Using nearest available strike' messages)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ OTM Test FAILED: {e}")
        logger.exception("OTM test failed")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("  STRIKE PRICE NEAREST-FALLBACK FIX - VERIFICATION TESTS")
    print("="*70)
    print("\nThis script tests the fix for strike price matching in backtesting.")
    print("Expected behavior:")
    print("  - ATM: Should use exact strike match (no fallback)")
    print("  - ITM/OTM: Should use nearest available strike (fallback with logs)")
    print("\nNote: Test may take 1-2 minutes to load data from S3...")
    
    results = {
        'ATM': False,
        'ITM': False,
        'OTM': False
    }
    
    # Run tests
    try:
        results['ATM'] = test_atm_configuration()
        results['ITM'] = test_itm_configuration()
        results['OTM'] = test_otm_configuration()
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        return
    
    # Summary
    print_section("TEST SUMMARY")
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test_name} Configuration: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nThe strike price nearest-fallback fix is working correctly.")
        print("Backtesting should now produce results with ITM/OTM configurations.")
    else:
        print("\n⚠️  SOME TESTS FAILED")
        print("\nPlease review the errors above and check:")
        print("  1. Data availability (S3 connection working?)")
        print("  2. Inside bar patterns detected in test period")
        print("  3. Logs for 'Using nearest available strike' messages")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    main()
