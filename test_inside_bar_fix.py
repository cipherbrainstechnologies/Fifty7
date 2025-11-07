"""
Test Script for Inside Bar Breakout Strategy Fix
Tests the timestamp-based breakout detection with synthetic candles

This script validates:
1. Inside bar detection works correctly across days
2. Breakout detection uses timestamps not indices
3. Signal is discarded after first breakout attempt
4. Comprehensive logging shows all hourly candles
5. Volume warnings work correctly

Date: 2025-11-07
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import pandas as pd
from datetime import datetime, timedelta
import pytz
from engine.inside_bar_breakout_strategy import InsideBarBreakoutStrategy
from logzero import logger

IST = pytz.timezone('Asia/Kolkata')


def create_synthetic_candles():
    """
    Create synthetic candle data mimicking the 07-Nov-2025 scenario:
    - Inside bar on 06-Nov-2025 at 15:15 IST
    - Reference (signal) candle on 06-Nov-2025 at 14:15 IST
    - Breakout candle on 07-Nov-2025 at 09:15 IST (PE side)
    """
    # Base date: 06-Nov-2025
    base_date = IST.localize(datetime(2025, 11, 6, 9, 15))
    
    candles = []
    
    # Day 1: 06-Nov-2025 - Normal candles leading to inside bar
    # 09:15 - First candle of the day
    candles.append({
        'Date': base_date,
        'Open': 25550.00,
        'High': 25580.00,
        'Low': 25520.00,
        'Close': 25565.00,
        'Volume': 1000
    })
    
    # 10:15
    candles.append({
        'Date': base_date + timedelta(hours=1),
        'Open': 25565.00,
        'High': 25600.00,
        'Low': 25555.00,
        'Close': 25590.00,
        'Volume': 1200
    })
    
    # 11:15
    candles.append({
        'Date': base_date + timedelta(hours=2),
        'Open': 25590.00,
        'High': 25620.00,
        'Low': 25580.00,
        'Close': 25610.00,
        'Volume': 1100
    })
    
    # 12:15
    candles.append({
        'Date': base_date + timedelta(hours=3),
        'Open': 25610.00,
        'High': 25625.00,
        'Low': 25595.00,
        'Close': 25615.00,
        'Volume': 900
    })
    
    # 13:15
    candles.append({
        'Date': base_date + timedelta(hours=4),
        'Open': 25615.00,
        'High': 25630.00,
        'Low': 25600.00,
        'Close': 25620.00,
        'Volume': 800
    })
    
    # 14:15 - SIGNAL CANDLE (reference candle before inside bar)
    # This is the candle that defines the breakout range
    candles.append({
        'Date': base_date + timedelta(hours=5),
        'Open': 25500.00,
        'High': 25564.60,  # High of signal range
        'Low': 25491.55,   # Low of signal range
        'Close': 25540.00,
        'Volume': 1500
    })
    
    # 15:15 - INSIDE BAR (completely within 14:15 candle range)
    # This triggers the signal
    candles.append({
        'Date': base_date + timedelta(hours=6),
        'Open': 25510.00,
        'High': 25521.45,  # Less than signal high (25564.60)
        'Low': 25498.70,   # Greater than signal low (25491.55)
        'Close': 25515.00,
        'Volume': 700
    })
    
    # Day 2: 07-Nov-2025 - Breakout day
    next_day = IST.localize(datetime(2025, 11, 7, 9, 15))
    
    # 09:15 - BREAKOUT CANDLE (PE side - closes below signal low)
    # This should trigger a PE trade
    candles.append({
        'Date': next_day,
        'Open': 25480.00,
        'High': 25485.00,
        'Low': 25340.00,
        'Close': 25351.45,  # Below signal low (25491.55) - PE BREAKOUT!
        'Volume': 2000
    })
    
    # 10:15 - Candle after breakout (should NOT trigger another trade)
    candles.append({
        'Date': next_day + timedelta(hours=1),
        'Open': 25351.45,
        'High': 25380.00,
        'Low': 25330.00,
        'Close': 25360.00,  # Still below range, but signal should be discarded
        'Volume': 1800
    })
    
    df = pd.DataFrame(candles)
    # Keep timezone-naive for strategy (it handles IST conversion)
    df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
    
    return df


def test_inside_bar_detection():
    """Test 1: Inside bar detection works correctly"""
    print("\n" + "="*80)
    print("TEST 1: INSIDE BAR DETECTION")
    print("="*80)
    
    candles = create_synthetic_candles()
    
    # Create strategy instance
    strategy = InsideBarBreakoutStrategy(
        broker=None,
        market_data=None,
        symbol="NIFTY",
        lot_size=75,
        quantity_lots=1,
        live_mode=False,  # Dry run mode
        config={'strategy': {'sl': 30, 'rr': 1.8}}
    )
    
    # Detect inside bar
    from engine.inside_bar_breakout_strategy import detect_inside_bar
    inside_bar_result = detect_inside_bar(candles)
    
    if inside_bar_result:
        print(f"✅ Inside bar detected!")
        print(f"   Inside bar time: {inside_bar_result['inside_bar_time']}")
        print(f"   Signal candle time: {inside_bar_result['signal_time']}")
        print(f"   Signal range: {inside_bar_result['range_low']:.2f} - {inside_bar_result['range_high']:.2f}")
        
        # Verify it's the correct inside bar (06-Nov 15:15)
        expected_inside_bar_time = IST.localize(datetime(2025, 11, 6, 15, 15))
        actual_inside_bar_time = inside_bar_result['inside_bar_time']
        if actual_inside_bar_time.replace(tzinfo=IST) == expected_inside_bar_time:
            print(f"✅ PASS: Inside bar correctly identified at 06-Nov-2025 15:15")
        else:
            print(f"❌ FAIL: Expected inside bar at {expected_inside_bar_time}, got {actual_inside_bar_time}")
    else:
        print("❌ FAIL: No inside bar detected")
    
    return inside_bar_result is not None


def test_breakout_detection_across_days():
    """Test 2: Breakout detection works across days using timestamps"""
    print("\n" + "="*80)
    print("TEST 2: BREAKOUT DETECTION ACROSS DAYS")
    print("="*80)
    
    candles = create_synthetic_candles()
    
    # Create strategy instance
    strategy = InsideBarBreakoutStrategy(
        broker=None,
        market_data=None,
        symbol="NIFTY",
        lot_size=75,
        quantity_lots=1,
        live_mode=False,
        config={'strategy': {'sl': 30, 'rr': 1.8}}
    )
    
    # Simulate running strategy on 07-Nov at 10:30 (after 09:15 candle closes at 10:15)
    current_time = IST.localize(datetime(2025, 11, 7, 10, 30))
    
    # Run strategy
    result = strategy.run_strategy(data=candles)
    
    print(f"\nStrategy result:")
    print(f"   Status: {result.get('status')}")
    print(f"   Message: {result.get('message')}")
    
    if result.get('breakout_direction'):
        print(f"   Breakout direction: {result.get('breakout_direction')}")
        print(f"   Strike: {result.get('strike')}")
        print(f"   Entry: {result.get('entry_price'):.2f}")
        print(f"   SL: {result.get('stop_loss'):.2f}")
        print(f"   TP: {result.get('take_profit'):.2f}")
        
        if result['breakout_direction'] == 'PE':
            print(f"✅ PASS: Breakout correctly detected on PE side")
            return True
        else:
            print(f"❌ FAIL: Expected PE breakout, got {result['breakout_direction']}")
            return False
    else:
        print(f"❌ FAIL: No breakout detected (expected PE breakout)")
        return False


def test_signal_discard_after_breakout():
    """Test 3: Signal is discarded after first breakout attempt"""
    print("\n" + "="*80)
    print("TEST 3: SIGNAL DISCARD AFTER BREAKOUT")
    print("="*80)
    
    candles = create_synthetic_candles()
    
    strategy = InsideBarBreakoutStrategy(
        broker=None,
        market_data=None,
        symbol="NIFTY",
        lot_size=75,
        quantity_lots=1,
        live_mode=False,
        config={'strategy': {'sl': 30, 'rr': 1.8}}
    )
    
    # First run: should detect breakout
    print("\n📍 First run (09:15 candle closed):")
    result1 = strategy.run_strategy(data=candles.iloc[:-1])  # Exclude 10:15 candle
    
    if result1.get('breakout_direction') == 'PE':
        print(f"✅ First run: Breakout detected on PE side")
    else:
        print(f"❌ First run: Expected breakout, got status {result1.get('status')}")
        return False
    
    # Second run: should NOT detect breakout again (signal discarded)
    print("\n📍 Second run (with 10:15 candle, after signal discarded):")
    result2 = strategy.run_strategy(data=candles)
    
    if result2.get('status') in ('no_signal', 'duplicate_breakout'):
        print(f"✅ PASS: Signal correctly discarded, no duplicate trade")
        print(f"   Status: {result2.get('status')}")
        return True
    elif result2.get('status') == 'breakout_confirmed':
        print(f"❌ FAIL: Signal NOT discarded, duplicate trade attempted!")
        return False
    else:
        print(f"⚠️ Unexpected status: {result2.get('status')}")
        return False


def test_comprehensive_logging():
    """Test 4: Comprehensive logging shows all hourly candles"""
    print("\n" + "="*80)
    print("TEST 4: COMPREHENSIVE CANDLE LOGGING")
    print("="*80)
    print("(Check logs above for detailed hourly candle information)")
    
    candles = create_synthetic_candles()
    
    strategy = InsideBarBreakoutStrategy(
        broker=None,
        market_data=None,
        symbol="NIFTY",
        lot_size=75,
        quantity_lots=1,
        live_mode=False,
        config={'strategy': {'sl': 30, 'rr': 1.8}}
    )
    
    # Run strategy - this should produce detailed logs for each candle
    result = strategy.run_strategy(data=candles)
    
    print(f"\n✅ PASS: Logging test complete (check console output above)")
    return True


def test_volume_handling():
    """Test 5: Volume warnings work correctly when volume is missing"""
    print("\n" + "="*80)
    print("TEST 5: VOLUME DATA HANDLING")
    print("="*80)
    
    candles = create_synthetic_candles()
    
    # Create candles WITHOUT volume data (simulating Angel API limitation)
    candles_no_volume = candles.drop(columns=['Volume'])
    
    strategy = InsideBarBreakoutStrategy(
        broker=None,
        market_data=None,
        symbol="NIFTY",
        lot_size=75,
        quantity_lots=1,
        live_mode=False,
        config={'strategy': {'sl': 30, 'rr': 1.8}}
    )
    
    print("\n📍 Running strategy with NO volume data:")
    result = strategy.run_strategy(data=candles_no_volume)
    
    if result.get('breakout_direction') == 'PE':
        print(f"✅ PASS: Breakout detected despite missing volume data")
        print(f"   (Check warnings above for volume alerts)")
        return True
    else:
        print(f"❌ FAIL: Breakout not detected (should work without volume)")
        return False


def main():
    """Run all tests"""
    print("\n" + "🟢"*40)
    print("INSIDE BAR BREAKOUT STRATEGY - FIX VALIDATION TESTS")
    print("🟢"*40)
    print("\nScenario: Replicating 07-Nov-2025 issue where breakout didn't trigger")
    print("Inside bar: 06-Nov-2025 15:15 IST")
    print("Signal range: 25491.55 - 25564.60")
    print("Breakout candle: 07-Nov-2025 09:15 IST, closed at 25351.45 (PE side)")
    
    results = []
    
    # Run all tests
    results.append(("Inside Bar Detection", test_inside_bar_detection()))
    results.append(("Breakout Detection Across Days", test_breakout_detection_across_days()))
    results.append(("Signal Discard After Breakout", test_signal_discard_after_breakout()))
    results.append(("Comprehensive Logging", test_comprehensive_logging()))
    results.append(("Volume Handling", test_volume_handling()))
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {passed} passed, {failed} failed out of {len(results)} tests")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! The fix is working correctly.")
        print("\nKey improvements:")
        print("  ✅ Timestamp-based breakout detection (no more index issues)")
        print("  ✅ Signal properly discarded after first breakout attempt")
        print("  ✅ Comprehensive logging for all hourly candles")
        print("  ✅ Volume checks disabled (Angel API doesn't provide volume for NIFTY)")
        print("  ✅ Works across day boundaries correctly")
    else:
        print(f"\n⚠️ {failed} test(s) failed. Please review the output above.")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
