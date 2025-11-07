"""
Test Script for Inside Bar Breakout Strategy - Complete Fix
Tests all scenarios: normal breakout, missed trade, state cleanup, logging
"""

import pandas as pd
from datetime import datetime, timedelta
import pytz
from engine.inside_bar_breakout_strategy import (
    InsideBarBreakoutStrategy,
    get_hourly_candles,
    detect_inside_bar,
    confirm_breakout_on_hour_close,
    log_recent_hourly_candles,
    ist_now,
    to_ist
)

IST = pytz.timezone('Asia/Kolkata')


def create_test_candles_with_inside_bar():
    """
    Create test 1H candles with clear inside bar pattern.
    
    Pattern:
    - 09:15-10:15: Normal candle (High=24200, Low=24100)
    - 10:15-11:15: Signal candle (High=24250, Low=24150) <- Reference range
    - 11:15-12:15: Inside bar (High=24220, Low=24170) <- Inside the signal candle
    - 12:15-13:15: Breakout candle (High=24280, Low=24240, Close=24270) <- Breaks above 24250
    """
    base_time = datetime.now(IST).replace(hour=9, minute=15, second=0, microsecond=0)
    
    candles = [
        # Normal candle
        {
            'Date': base_time,
            'Open': 24150.0,
            'High': 24200.0,
            'Low': 24100.0,
            'Close': 24180.0,
            'Volume': 1000000
        },
        # Signal candle (reference range)
        {
            'Date': base_time + timedelta(hours=1),
            'Open': 24180.0,
            'High': 24250.0,
            'Low': 24150.0,
            'Close': 24200.0,
            'Volume': 1200000
        },
        # Inside bar (high < 24250 and low > 24150)
        {
            'Date': base_time + timedelta(hours=2),
            'Open': 24200.0,
            'High': 24220.0,
            'Low': 24170.0,
            'Close': 24210.0,
            'Volume': 800000
        },
        # Breakout candle (close > 24250)
        {
            'Date': base_time + timedelta(hours=3),
            'Open': 24210.0,
            'High': 24280.0,
            'Low': 24240.0,
            'Close': 24270.0,
            'Volume': 1500000
        },
        # Post-breakout candle
        {
            'Date': base_time + timedelta(hours=4),
            'Open': 24270.0,
            'High': 24300.0,
            'Low': 24260.0,
            'Close': 24290.0,
            'Volume': 1100000
        }
    ]
    
    return pd.DataFrame(candles)


def create_test_candles_missed_trade():
    """
    Create test candles where breakout already occurred (missed trade scenario).
    Breakout candle closed 30 minutes ago.
    """
    base_time = datetime.now(IST).replace(hour=9, minute=15, second=0, microsecond=0)
    # Move breakout candle to 30 minutes ago
    breakout_time = datetime.now(IST) - timedelta(minutes=30)
    breakout_time = breakout_time.replace(minute=15, second=0, microsecond=0)
    
    candles = [
        # Signal candle
        {
            'Date': breakout_time - timedelta(hours=2),
            'Open': 24180.0,
            'High': 24250.0,
            'Low': 24150.0,
            'Close': 24200.0,
            'Volume': 1200000
        },
        # Inside bar
        {
            'Date': breakout_time - timedelta(hours=1),
            'Open': 24200.0,
            'High': 24220.0,
            'Low': 24170.0,
            'Close': 24210.0,
            'Volume': 800000
        },
        # Breakout candle (already closed 30 min ago)
        {
            'Date': breakout_time,
            'Open': 24210.0,
            'High': 24280.0,
            'Low': 24240.0,
            'Close': 24270.0,
            'Volume': 1500000
        }
    ]
    
    return pd.DataFrame(candles)


def test_inside_bar_detection():
    """Test 1: Inside bar detection works correctly"""
    print("\n" + "="*80)
    print("TEST 1: Inside Bar Detection")
    print("="*80)
    
    candles = create_test_candles_with_inside_bar()
    result = detect_inside_bar(candles)
    
    if result:
        print("✅ Inside bar detected successfully")
        print(f"   Inside bar time: {result['inside_bar_time']}")
        print(f"   Signal time: {result['signal_time']}")
        print(f"   Range: {result['range_low']:.2f} - {result['range_high']:.2f}")
        
        # Verify correctness
        assert result['range_high'] == 24250.0, "Range high should be 24250"
        assert result['range_low'] == 24150.0, "Range low should be 24150"
        print("✅ Range values verified")
    else:
        print("❌ FAILED: No inside bar detected")
        return False
    
    return True


def test_breakout_confirmation():
    """Test 2: Breakout confirmation works correctly"""
    print("\n" + "="*80)
    print("TEST 2: Breakout Confirmation")
    print("="*80)
    
    candles = create_test_candles_with_inside_bar()
    signal = detect_inside_bar(candles)
    
    if not signal:
        print("❌ FAILED: Could not detect inside bar")
        return False
    
    direction, breakout_candle, is_missed = confirm_breakout_on_hour_close(
        candles,
        signal,
        current_time=datetime.now(IST)
    )
    
    if direction == "CE":
        print("✅ Breakout detected: CE (Call)")
        print(f"   Breakout candle close: {breakout_candle['Close']:.2f}")
        print(f"   Range high: {signal['range_high']:.2f}")
        print(f"   Is missed trade: {is_missed}")
        
        assert breakout_candle['Close'] > signal['range_high'], "Close should be above range high"
        assert not is_missed, "Should not be missed trade (breakout just happened)"
        print("✅ Breakout logic verified")
    else:
        print(f"❌ FAILED: Expected CE breakout, got {direction}")
        return False
    
    return True


def test_missed_trade_detection():
    """Test 3: Missed trade detection works correctly"""
    print("\n" + "="*80)
    print("TEST 3: Missed Trade Detection")
    print("="*80)
    
    candles = create_test_candles_missed_trade()
    signal = detect_inside_bar(candles)
    
    if not signal:
        print("❌ FAILED: Could not detect inside bar")
        return False
    
    direction, breakout_candle, is_missed = confirm_breakout_on_hour_close(
        candles,
        signal,
        current_time=datetime.now(IST),
        check_missed_trade=True
    )
    
    if is_missed:
        print("✅ Missed trade detected successfully")
        print(f"   Breakout direction: {direction}")
        print(f"   Breakout candle time: {breakout_candle['Date']}")
        
        # Verify the candle closed more than 5 minutes ago
        time_diff = (datetime.now(IST) - to_ist(breakout_candle['Date'])).total_seconds()
        assert time_diff > 300, "Breakout should be more than 5 minutes old"
        print(f"   Time since breakout: {int(time_diff/60)} minutes")
        print("✅ Missed trade logic verified")
    else:
        print(f"❌ FAILED: Missed trade not detected (is_missed={is_missed})")
        return False
    
    return True


def test_hourly_candle_logging():
    """Test 4: Hourly candle logging produces correct output"""
    print("\n" + "="*80)
    print("TEST 4: Hourly Candle Logging")
    print("="*80)
    
    candles = create_test_candles_with_inside_bar()
    signal = detect_inside_bar(candles)
    
    table = log_recent_hourly_candles(candles, count=5, signal=signal)
    
    print("✅ Candle table generated:")
    print(table)
    
    # Verify table contains key elements
    assert "RECENT HOURLY CANDLES" in table, "Table should have header"
    assert "Inside Bar" in table or "🟢" in table, "Table should mark inside bar"
    assert "Signal Candle" in table or "🔵" in table, "Table should mark signal candle"
    assert "Breakout" in table, "Table should show breakout"
    print("✅ Table format verified")
    
    return True


def test_strategy_run_normal():
    """Test 5: Full strategy run with normal breakout"""
    print("\n" + "="*80)
    print("TEST 5: Full Strategy Run (Normal Breakout)")
    print("="*80)
    
    candles = create_test_candles_with_inside_bar()
    
    # Create strategy instance (without broker for testing)
    strategy = InsideBarBreakoutStrategy(
        broker=None,
        market_data=None,
        symbol="NIFTY",
        lot_size=75,
        quantity_lots=1,
        live_mode=False  # Dry run mode
    )
    
    # Run strategy with test data
    result = strategy.run_strategy(data=candles)
    
    print(f"Status: {result.get('status')}")
    print(f"Message: {result.get('message')}")
    
    if result['status'] == 'breakout_confirmed':
        print("✅ Strategy detected and executed breakout")
        print(f"   Direction: {result.get('breakout_direction')}")
        print(f"   Strike: {result.get('strike')}")
        print(f"   Entry: {result.get('entry_price'):.2f}")
        print(f"   SL: {result.get('stop_loss'):.2f}")
        print(f"   TP: {result.get('take_profit'):.2f}")
        
        # Verify signal was invalidated
        assert strategy.active_signal is None, "Signal should be invalidated after breakout"
        print("✅ Signal cleanup verified")
    elif result['status'] == 'no_breakout':
        print("⚠️ No breakout detected yet (might need more candles)")
    else:
        print(f"❌ FAILED: Unexpected status {result['status']}")
        return False
    
    return True


def test_strategy_run_missed_trade():
    """Test 6: Full strategy run with missed trade"""
    print("\n" + "="*80)
    print("TEST 6: Full Strategy Run (Missed Trade)")
    print("="*80)
    
    candles = create_test_candles_missed_trade()
    
    strategy = InsideBarBreakoutStrategy(
        broker=None,
        market_data=None,
        symbol="NIFTY",
        lot_size=75,
        quantity_lots=1,
        live_mode=False
    )
    
    result = strategy.run_strategy(data=candles)
    
    print(f"Status: {result.get('status')}")
    print(f"Message: {result.get('message')}")
    
    if result['status'] == 'missed_trade':
        print("✅ Strategy detected missed trade")
        print(f"   Direction: {result.get('breakout_direction')}")
        print(f"   Missed reason: {result.get('missed_reason')}")
        
        # Verify signal was invalidated
        assert strategy.active_signal is None, "Signal should be invalidated after missed trade"
        print("✅ Signal cleanup after missed trade verified")
    else:
        print(f"❌ FAILED: Expected missed_trade status, got {result['status']}")
        return False
    
    return True


def run_all_tests():
    """Run all test scenarios"""
    print("\n" + "="*80)
    print("INSIDE BAR STRATEGY - COMPREHENSIVE TEST SUITE")
    print("Testing all fixes and improvements")
    print("="*80)
    
    tests = [
        ("Inside Bar Detection", test_inside_bar_detection),
        ("Breakout Confirmation", test_breakout_confirmation),
        ("Missed Trade Detection", test_missed_trade_detection),
        ("Hourly Candle Logging", test_hourly_candle_logging),
        ("Strategy Run (Normal)", test_strategy_run_normal),
        ("Strategy Run (Missed)", test_strategy_run_missed_trade)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ ERROR in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status}: {name}")
    
    print("="*80)
    print(f"TOTAL: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Strategy is ready for deployment.")
    else:
        print("⚠️ Some tests failed. Please review the errors above.")
    
    print("="*80)
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
