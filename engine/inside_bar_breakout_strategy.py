"""
Inside Bar Breakout Strategy - Production-Grade Implementation
Implements complete Inside Bar + Breakout strategy for NIFTY Options Trading

Strategy Rules:
1. Use 1-Hour candles (IST timezone). Market hours: 09:15 AM to 03:15 PM IST
2. Detect the most recent inside bar candle (high < previous high, low > previous low)
3. The candle just before the inside bar is the Signal Candle
4. Signal remains active until a new inside bar is detected
5. If any 1-hour candle CLOSES:
   - Above signal high → execute CE trade
   - Below signal low → execute PE trade
6. No 15-min confirmation logic is needed. Only 1-hour candle close matters.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
import pytz
from logzero import logger
import os
import csv

# Import broker and market data modules
from .broker_connector import AngelOneBroker, BrokerInterface
from .market_data import MarketDataProvider


# Configuration
LIVE_MODE = True  # Set to False to test without real trades
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 15
IST = pytz.timezone('Asia/Kolkata')


class InsideBarBreakoutStrategy:
    """
    Production-grade Inside Bar Breakout Strategy implementation.
    """
    
    def __init__(
        self,
        broker: Optional[BrokerInterface] = None,
        market_data: Optional[MarketDataProvider] = None,
        symbol: str = "NIFTY",
        lot_size: int = 75,
        quantity_lots: int = 1,
        live_mode: bool = True,
        csv_export_path: Optional[str] = None,
        config: Optional[Dict] = None
    ):
        """
        Initialize Inside Bar Breakout Strategy.
        
        Args:
            broker: Broker interface instance (AngelOneBroker)
            market_data: MarketDataProvider instance
            symbol: Trading symbol (default: "NIFTY")
            lot_size: Lot size for options (default: 75 for NIFTY)
            quantity_lots: Number of lots per trade (default: 1)
            live_mode: If True, place real trades. If False, simulate only.
            csv_export_path: Optional path to export results CSV
        """
        self.broker = broker
        self.market_data = market_data
        self.symbol = symbol
        self.lot_size = lot_size
        self.quantity_lots = quantity_lots
        self.live_mode = live_mode
        self.csv_export_path = csv_export_path or "logs/inside_bar_breakout_results.csv"
        self.config = config or {}
        
        # Strategy parameters from config
        self.sl_points = self.config.get('strategy', {}).get('sl', 30)  # Stop loss in points
        self.rr_ratio = self.config.get('strategy', {}).get('rr', 1.8)  # Risk-reward ratio
        self.atm_offset = self.config.get('strategy', {}).get('atm_offset', 0)  # Strike offset
        
        # Strategy state
        self.signal_candle_high = None
        self.signal_candle_low = None
        self.signal_candle_date = None
        self.inside_bar_date = None
        self.last_checked_candle_idx = -1
        
        # Ensure CSV directory exists
        if self.csv_export_path:
            os.makedirs(os.path.dirname(self.csv_export_path) or '.', exist_ok=True)
            self._initialize_csv()
        
        logger.info(f"Inside Bar Breakout Strategy initialized (Live Mode: {self.live_mode})")
    
    def _initialize_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if os.path.exists(self.csv_export_path):
            return
        
        headers = [
            'Date', 'Time', 'Signal_Date', 'Signal_High', 'Signal_Low',
            'Current_Price', 'Breakout_Direction', 'Strike', 'Entry_Price',
            'Stop_Loss', 'Take_Profit', 'Order_ID', 'Status', 'Message'
        ]
        
        with open(self.csv_export_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
    
    def _export_to_csv(self, row_data: Dict):
        """Export result row to CSV."""
        if not self.csv_export_path:
            return
        
        try:
            with open(self.csv_export_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    row_data.get('Date', ''),
                    row_data.get('Time', ''),
                    row_data.get('Signal_Date', ''),
                    row_data.get('Signal_High', ''),
                    row_data.get('Signal_Low', ''),
                    row_data.get('Current_Price', ''),
                    row_data.get('Breakout_Direction', ''),
                    row_data.get('Strike', ''),
                    row_data.get('Entry_Price', ''),
                    row_data.get('Stop_Loss', ''),
                    row_data.get('Take_Profit', ''),
                    row_data.get('Order_ID', ''),
                    row_data.get('Status', ''),
                    row_data.get('Message', '')
                ])
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
    
    def _format_date_ist(self, dt: datetime) -> str:
        """
        Format datetime to DD-MMM-YYYY format in IST timezone.
        
        Args:
            dt: Datetime object (may be timezone-aware or naive)
        
        Returns:
            Formatted date string (e.g., "04-Nov-2025")
        """
        # Convert to IST if timezone-aware
        if dt.tzinfo is not None:
            dt_ist = dt.astimezone(IST)
        else:
            # Assume naive datetime is already in IST
            dt_ist = IST.localize(dt) if dt.tzinfo is None else dt
        
        return dt_ist.strftime("%d-%b-%Y")
    
    def _format_datetime_ist(self, dt: datetime) -> str:
        """
        Format datetime to DD-MMM-YYYY HH:MM:SS IST format.
        
        Args:
            dt: Datetime object
        
        Returns:
            Formatted datetime string (e.g., "04-Nov-2025 10:30:00 IST")
        """
        if dt.tzinfo is not None:
            dt_ist = dt.astimezone(IST)
        else:
            dt_ist = IST.localize(dt) if dt.tzinfo is None else dt
        
        return dt_ist.strftime("%d-%b-%Y %H:%M:%S IST")
    
    def _is_market_hours(self, dt: Optional[datetime] = None) -> bool:
        """
        Check if current time is within market hours (09:15 AM to 03:15 PM IST).
        
        Args:
            dt: Datetime to check (default: current time)
        
        Returns:
            True if within market hours, False otherwise
        """
        if dt is None:
            dt = datetime.now(IST)
        elif dt.tzinfo is None:
            dt = IST.localize(dt)
        else:
            dt = dt.astimezone(IST)
        
        # Get time components
        hour = dt.hour
        minute = dt.minute
        
        # Market opens at 09:15
        market_open = datetime(dt.year, dt.month, dt.day, MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, tzinfo=IST)
        # Market closes at 15:15
        market_close = datetime(dt.year, dt.month, dt.day, MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE, tzinfo=IST)
        
        return market_open <= dt <= market_close
    
    def get_hourly_candles(self, window_hours: int = 48, data: Optional[pd.DataFrame] = None) -> Optional[pd.DataFrame]:
        """
        Fetch 1-hour candles from market data provider or use provided data.
        
        Args:
            window_hours: Number of hours of data to fetch (default: 48)
            data: Optional DataFrame with candles (for backtesting mode)
        
        Returns:
            DataFrame with 1-hour OHLC candles or None if error
        """
        # Backtesting mode: use provided data
        if data is not None:
            candles = data.copy()
            # Ensure Date column exists or use index
            if 'Date' not in candles.columns and isinstance(candles.index, pd.DatetimeIndex):
                candles = candles.reset_index()
                if 'Date' not in candles.columns and len(candles.columns) > 0:
                    # Use first datetime column as Date
                    for col in candles.columns:
                        if pd.api.types.is_datetime64_any_dtype(candles[col]):
                            candles.rename(columns={col: 'Date'}, inplace=True)
                            break
            logger.info(f"✅ Using provided {len(candles)} hourly candles (backtesting mode)")
            return candles
        
        # Live mode: fetch from market data provider
        if self.market_data is None:
            logger.error("Market data provider not available and no data provided")
            return None
        
        try:
            # Use market data provider to fetch 1-hour candles
            # include_latest=True for live mode to get current incomplete candle
            candles = self.market_data.get_1h_data(
                window_hours=window_hours,
                use_direct_interval=True,
                include_latest=True  # Include latest incomplete candle for live trading
            )
            
            if candles is None or candles.empty:
                logger.warning("No hourly candles fetched from market data provider")
                return None
            
            # Ensure Date column is datetime
            if 'Date' in candles.columns:
                if not pd.api.types.is_datetime64_any_dtype(candles['Date']):
                    candles['Date'] = pd.to_datetime(candles['Date'])
                
                # Normalize to IST if timezone-aware
                if candles['Date'].dt.tz is not None:
                    candles['Date'] = candles['Date'].dt.tz_convert(IST).dt.tz_localize(None)
            
            # Filter to market hours only
            if 'Date' in candles.columns:
                candles = candles[candles['Date'].apply(self._is_market_hours)]
            
            logger.info(f"✅ Fetched {len(candles)} hourly candles")
            return candles
            
        except Exception as e:
            logger.exception(f"Error fetching hourly candles: {e}")
            return None
    
    def detect_inside_bar(self, candles: pd.DataFrame) -> Optional[Dict]:
        """
        Detect the most recent inside bar candle.
        
        An inside bar is when:
        - current_high < previous_high
        - current_low > previous_low
        
        Args:
            candles: DataFrame with 1-hour OHLC candles
        
        Returns:
            Dictionary with inside bar info or None if not found:
            {
                'inside_bar_idx': int,
                'inside_bar_date': datetime,
                'signal_candle_high': float,
                'signal_candle_low': float,
                'signal_candle_date': datetime
            }
        """
        if candles is None or len(candles) < 2:
            logger.debug("Insufficient candles for inside bar detection (need at least 2)")
            return None
        
        # Scan from most recent to oldest
        # We want the most recent inside bar
        for i in range(len(candles) - 1, 0, -1):
            current_high = candles['High'].iloc[i]
            current_low = candles['Low'].iloc[i]
            prev_high = candles['High'].iloc[i - 1]
            prev_low = candles['Low'].iloc[i - 1]
            
            # Inside bar condition: current is completely inside previous
            is_inside = (current_high < prev_high) and (current_low > prev_low)
            
            if is_inside:
                # Get dates
                if 'Date' in candles.columns:
                    inside_bar_date = candles['Date'].iloc[i]
                    signal_candle_date = candles['Date'].iloc[i - 1]
                else:
                    inside_bar_date = candles.index[i]
                    signal_candle_date = candles.index[i - 1]
                
                result = {
                    'inside_bar_idx': i,
                    'inside_bar_date': inside_bar_date,
                    'signal_candle_high': prev_high,
                    'signal_candle_low': prev_low,
                    'signal_candle_date': signal_candle_date
                }
                
                logger.info(
                    f"✅ Inside Bar detected at {self._format_datetime_ist(inside_bar_date)} | "
                    f"Signal Candle: {self._format_datetime_ist(signal_candle_date)} | "
                    f"High: {prev_high:.2f}, Low: {prev_low:.2f}"
                )
                
                return result
        
        logger.debug("No inside bar pattern detected in candles")
        return None
    
    def check_breakout(
        self,
        candles: pd.DataFrame,
        signal_high: float,
        signal_low: float,
        start_idx: int = 0
    ) -> Optional[str]:
        """
        Check for breakout on 1-hour candle close.
        
        Breakout conditions:
        - Close > signal_high → CE (Call) trade
        - Close < signal_low → PE (Put) trade
        
        Args:
            candles: DataFrame with 1-hour OHLC candles
            signal_high: Signal candle high (breakout level for CE)
            signal_low: Signal candle low (breakout level for PE)
            start_idx: Index to start checking from (default: 0)
        
        Returns:
            "CE" for bullish breakout, "PE" for bearish breakout, or None
        """
        if candles is None or candles.empty:
            return None
        
        # Check candles from start_idx onwards
        for i in range(start_idx, len(candles)):
            close = candles['Close'].iloc[i]
            
            # Get candle date for logging
            if 'Date' in candles.columns:
                candle_date = candles['Date'].iloc[i]
            else:
                candle_date = candles.index[i]
            
            # Bullish breakout: close above signal high
            if close > signal_high:
                logger.info(
                    f"🟢 Breakout Confirmed: CE at {self._format_datetime_ist(candle_date)} | "
                    f"Close: {close:.2f} > Signal High: {signal_high:.2f}"
                )
                return "CE"
            
            # Bearish breakout: close below signal low
            elif close < signal_low:
                logger.info(
                    f"🔴 Breakout Confirmed: PE at {self._format_datetime_ist(candle_date)} | "
                    f"Close: {close:.2f} < Signal Low: {signal_low:.2f}"
                )
                return "PE"
        
        return None
    
    def calculate_strike_price(self, current_price: float, direction: str, atm_offset: int = 0) -> int:
        """
        Calculate option strike price based on current NIFTY price.
        
        Args:
            current_price: Current NIFTY index price
            direction: "CE" for Call, "PE" for Put
            atm_offset: Offset from ATM (0 = ATM, positive = OTM for calls)
        
        Returns:
            Strike price rounded to nearest 50 (NIFTY strikes are multiples of 50)
        """
        # NIFTY strikes are in multiples of 50
        base_strike = round(current_price / 50) * 50
        
        if direction == "CE":
            return int(base_strike + atm_offset)
        elif direction == "PE":
            return int(base_strike - atm_offset)
        else:
            return int(base_strike)
    
    def calculate_sl_tp_levels(
        self,
        entry_price: float,
        stop_loss_points: int,
        risk_reward_ratio: float
    ) -> Tuple[float, float]:
        """
        Calculate Stop Loss and Take Profit levels based on entry and risk parameters.
        
        Args:
            entry_price: Entry price of the option
            stop_loss_points: Stop loss in points
            risk_reward_ratio: Risk-Reward ratio (e.g., 1.8 = 1.8x risk)
        
        Returns:
            Tuple of (stop_loss_price, take_profit_price)
        """
        stop_loss = entry_price - stop_loss_points
        take_profit = entry_price + (stop_loss_points * risk_reward_ratio)
        
        return (stop_loss, take_profit)
    
    def check_margin(self) -> Tuple[bool, float]:
        """
        Check available margin using RMS API.
        
        Returns:
            Tuple of (has_sufficient_margin, available_margin)
        """
        try:
            available_margin = self.broker.get_available_margin()
            
            if available_margin <= 0:
                logger.warning(f"⚠️ No available margin: ₹{available_margin:.2f}")
                return False, available_margin
            
            # Estimate required margin (rough estimate: 1 lot = ~50k for NIFTY options)
            required_margin = self.quantity_lots * 50000  # Conservative estimate
            
            if available_margin >= required_margin:
                logger.info(f"✅ Sufficient margin: ₹{available_margin:,.2f} (Required: ₹{required_margin:,.2f})")
                return True, available_margin
            else:
                logger.warning(
                    f"⚠️ Insufficient margin: Available ₹{available_margin:,.2f}, "
                    f"Required ₹{required_margin:,.2f}"
                )
                return False, available_margin
                
        except Exception as e:
            logger.exception(f"Error checking margin: {e}")
            return False, 0.0
    
    def place_trade(
        self,
        direction: str,
        strike: int,
        current_price: float
    ) -> Dict:
        """
        Place trade via AngelOne API.
        
        Args:
            direction: "CE" for Call, "PE" for Put
            strike: Strike price
            current_price: Current NIFTY price (for logging)
        
        Returns:
            Dictionary with order result:
            {
                'status': bool,
                'order_id': str or None,
                'message': str,
                'response': dict or None
            }
        """
        if not self.live_mode:
            logger.info(f"🔒 LIVE_MODE=False: Simulating trade | Direction: {direction}, Strike: {strike}")
            return {
                'status': True,
                'order_id': f"SIM_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                'message': 'Trade simulated (LIVE_MODE=False)',
                'response': None
            }
        
        try:
            # Check margin before placing order
            has_margin, available_margin = self.check_margin()
            if not has_margin:
                return {
                    'status': False,
                    'order_id': None,
                    'message': f'Insufficient margin: ₹{available_margin:,.2f}',
                    'response': None
                }
            
            # Place order via broker
            logger.info(f"📤 Placing {direction} order: Strike {strike}, Quantity {self.quantity_lots} lots")
            
            order_result = self.broker.place_order(
                symbol=self.symbol,
                strike=strike,
                direction=direction,
                quantity=self.quantity_lots,
                order_type="MARKET",
                transaction_type="BUY"
            )
            
            # Log full response
            logger.info(f"📥 Order Response: {order_result}")
            
            if order_result.get('status'):
                order_id = order_result.get('order_id')
                logger.info(f"✅ Order placed successfully: Order ID {order_id}")
                return {
                    'status': True,
                    'order_id': order_id,
                    'message': 'Order placed successfully',
                    'response': order_result
                }
            else:
                error_msg = order_result.get('message', 'Unknown error')
                logger.error(f"❌ Order placement failed: {error_msg}")
                return {
                    'status': False,
                    'order_id': None,
                    'message': error_msg,
                    'response': order_result
                }
                
        except Exception as e:
            logger.exception(f"Error placing trade: {e}")
            return {
                'status': False,
                'order_id': None,
                'message': f'Error: {str(e)}',
                'response': None
            }
    
    def run_strategy(self, data: Optional[pd.DataFrame] = None) -> Dict:
        """
        Main strategy execution function.
        Runs complete Inside Bar Breakout strategy workflow.
        
        Returns:
            Dictionary with strategy execution result
        """
        try:
            # Get current time in IST
            now_ist = datetime.now(IST)
            current_time_str = self._format_datetime_ist(now_ist)
            
            # Check if market is open
            if not self._is_market_hours():
                logger.info(f"⏸️ Market is closed. Current time: {current_time_str}")
                return {
                    'status': 'market_closed',
                    'message': 'Market is closed',
                    'time': current_time_str
                }
            
            logger.info(f"🚀 Running Inside Bar Breakout Strategy | Time: {current_time_str}")
            
            # Step 1: Fetch hourly candles (or use provided data for backtesting)
            candles = self.get_hourly_candles(window_hours=48, data=data)
            if candles is None or candles.empty:
                return {
                    'status': 'error',
                    'message': 'Failed to fetch hourly candles'
                }
            
            # Step 2: Detect inside bar
            inside_bar_info = self.detect_inside_bar(candles)
            
            if inside_bar_info is None:
                logger.info("📊 No inside bar detected. Waiting for pattern...")
                return {
                    'status': 'no_signal',
                    'message': 'No inside bar pattern detected',
                    'current_price': candles['Close'].iloc[-1] if not candles.empty else None
                }
            
            # Update strategy state
            self.signal_candle_high = inside_bar_info['signal_candle_high']
            self.signal_candle_low = inside_bar_info['signal_candle_low']
            self.signal_candle_date = inside_bar_info['signal_candle_date']
            self.inside_bar_date = inside_bar_info['inside_bar_date']
            
            # Step 3: Check for breakout
            # Start checking from the candle after the inside bar
            start_check_idx = inside_bar_info['inside_bar_idx'] + 1
            
            # Only check new candles (after last checked index)
            if start_check_idx <= self.last_checked_candle_idx:
                start_check_idx = self.last_checked_candle_idx + 1
            
            if start_check_idx >= len(candles):
                logger.info("⏳ Waiting for new candles after inside bar...")
                return {
                    'status': 'waiting',
                    'message': 'Waiting for new candles after inside bar',
                    'signal_date': self._format_date_ist(self.signal_candle_date),
                    'signal_high': self.signal_candle_high,
                    'signal_low': self.signal_candle_low,
                    'current_price': candles['Close'].iloc[-1] if not candles.empty else None
                }
            
            breakout_direction = self.check_breakout(
                candles,
                self.signal_candle_high,
                self.signal_candle_low,
                start_idx=start_check_idx
            )
            
            # Update last checked index
            self.last_checked_candle_idx = len(candles) - 1
            
            # Step 4: Execute trade if breakout confirmed
            if breakout_direction:
                current_price = candles['Close'].iloc[-1]
                strike = self.calculate_strike_price(current_price, breakout_direction, self.atm_offset)
                
                # Get entry price (option premium)
                # In live mode, fetch from broker; in backtest mode, use synthetic or provided
                entry_price = current_price  # Placeholder - should fetch actual option price
                if self.broker and self.live_mode:
                    # Try to fetch actual option price from broker
                    option_price = self.broker.get_option_price(self.symbol, strike, breakout_direction)
                    if option_price:
                        entry_price = option_price
                
                # Calculate SL/TP levels
                stop_loss, take_profit = self.calculate_sl_tp_levels(
                    entry_price,
                    self.sl_points,
                    self.rr_ratio
                )
                
                # Place trade
                trade_result = self.place_trade(breakout_direction, strike, current_price)
                
                # Prepare output
                result = {
                    'status': 'breakout_confirmed',
                    'breakout_direction': breakout_direction,
                    'signal_date': self._format_date_ist(self.signal_candle_date),
                    'signal_high': self.signal_candle_high,
                    'signal_low': self.signal_candle_low,
                    'current_price': current_price,
                    'strike': strike,
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'order_id': trade_result.get('order_id'),
                    'order_status': trade_result.get('status'),
                    'order_message': trade_result.get('message'),
                    'time': current_time_str
                }
                
                # Export to CSV
                self._export_to_csv({
                    'Date': self._format_date_ist(now_ist),
                    'Time': now_ist.strftime("%H:%M:%S"),
                    'Signal_Date': self._format_date_ist(self.signal_candle_date),
                    'Signal_High': f"{self.signal_candle_high:.2f}",
                    'Signal_Low': f"{self.signal_candle_low:.2f}",
                    'Current_Price': f"{current_price:.2f}",
                    'Breakout_Direction': breakout_direction,
                    'Strike': strike,
                    'Entry_Price': f"{entry_price:.2f}",
                    'Stop_Loss': f"{stop_loss:.2f}",
                    'Take_Profit': f"{take_profit:.2f}",
                    'Order_ID': trade_result.get('order_id', ''),
                    'Status': 'SUCCESS' if trade_result.get('status') else 'FAILED',
                    'Message': trade_result.get('message', '')
                })
                
                # Print summary
                self._print_summary(result)
                
                return result
            else:
                # No breakout yet
                current_price = candles['Close'].iloc[-1]
                
                result = {
                    'status': 'no_breakout',
                    'message': 'No breakout yet',
                    'signal_date': self._format_date_ist(self.signal_candle_date),
                    'signal_high': self.signal_candle_high,
                    'signal_low': self.signal_candle_low,
                    'current_price': current_price,
                    'time': current_time_str
                }
                
                # Print summary
                self._print_summary(result)
                
                return result
                
        except Exception as e:
            logger.exception(f"Error running strategy: {e}")
            return {
                'status': 'error',
                'message': f'Error: {str(e)}'
            }
    
    def _print_summary(self, result: Dict):
        """
        Print formatted strategy summary.
        
        Args:
            result: Strategy execution result dictionary
        """
        print("\n" + "="*70)
        print("INSIDE BAR BREAKOUT STRATEGY - EXECUTION SUMMARY")
        print("="*70)
        
        if result.get('status') == 'breakout_confirmed':
            print(f"✅ Inside Bar Detected on {result.get('signal_date', 'N/A')}")
            print(f"Signal Candle: High={result.get('signal_high', 0):.2f}, Low={result.get('signal_low', 0):.2f}")
            print(f"Current Price: {result.get('current_price', 0):.2f}")
            
            direction = result.get('breakout_direction', '')
            if direction == 'CE':
                print(f"🟢 Breakout Confirmed: CE")
            elif direction == 'PE':
                print(f"🔴 Breakout Confirmed: PE")
            
            print(f"Strike: {result.get('strike', 'N/A')}")
            print(f"Entry Price: {result.get('entry_price', 0):.2f}")
            print(f"Stop Loss: {result.get('stop_loss', 0):.2f}")
            print(f"Take Profit: {result.get('take_profit', 0):.2f}")
            print(f"Order ID: {result.get('order_id', 'N/A')}")
            print(f"Order Status: {'SUCCESS' if result.get('order_status') else 'FAILED'}")
            if result.get('order_message'):
                print(f"Message: {result.get('order_message')}")
        
        elif result.get('status') == 'no_breakout':
            print(f"✅ Inside Bar Detected on {result.get('signal_date', 'N/A')}")
            print(f"Signal Candle: High={result.get('signal_high', 0):.2f}, Low={result.get('signal_low', 0):.2f}")
            print(f"Current Price: {result.get('current_price', 0):.2f}")
            print("⏳ No breakout yet")
        
        elif result.get('status') == 'no_signal':
            print("📊 No inside bar pattern detected")
            if result.get('current_price'):
                print(f"Current Price: {result.get('current_price', 0):.2f}")
        
        print(f"Time: {result.get('time', 'N/A')}")
        print("="*70 + "\n")


def create_strategy_from_config(
    broker_config: Dict,
    market_data: Optional[MarketDataProvider] = None,
    live_mode: bool = True
) -> InsideBarBreakoutStrategy:
    """
    Factory function to create InsideBarBreakoutStrategy from configuration.
    
    Args:
        broker_config: Broker configuration dictionary
        market_data: Optional MarketDataProvider instance (creates new if None)
        live_mode: Live mode flag (default: True)
    
    Returns:
        InsideBarBreakoutStrategy instance
    """
    # Create broker instance
    broker = AngelOneBroker(broker_config)
    
    # Create market data provider if not provided
    if market_data is None:
        market_data = MarketDataProvider(broker)
    
    # Create strategy
    strategy = InsideBarBreakoutStrategy(
        broker=broker,
        market_data=market_data,
        symbol="NIFTY",
        lot_size=75,
        quantity_lots=1,
        live_mode=live_mode
    )
    
    return strategy

